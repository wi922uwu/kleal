# -*- coding: utf-8 -*-
# ============================== KLEAL MATCHING CORE v2 — scoring engine ==============================
# Spec-faithful engine per "Kleal_Matching_Core_Final_Spec_RU_v2" (July 2026), §§6-12:
#   7 feature groups x 4 feature states (known_match / known_mismatch / unknown / not_applicable)
#   -> directional relevance R_mean, evidence Coverage, conservative R_lcb = clamp(R_mean - λ(1-Cov))
#   -> reverse direction B->A -> reciprocal 0.7*min + 0.3*mean -> user-facing bands (no raw percents)
#   -> allocation slate (diversity) -> presentation (2-3 confirmed reasons + one gap) + decision trace.
#
# Invariants from the spec's §23.2 this file enforces:
#   - semantic tier (T0-T5) is RETRIEVAL PROVENANCE (how the candidate was found), never derived
#     from the score;
#   - unknown is NOT a match: it contributes the domain prior and *lowers* coverage, so a sparse
#     profile can't outrank a confirmed one silently;
#   - not_applicable is excluded from the denominator (doesn't lower coverage);
#   - weights/priors/thresholds live ONLY in config/Kleal_Matching_Core_Config_v2.yaml (sha-pinned);
#     this file contains no tunable relevance numbers except observed-value anchors;
#   - feedback history does NOT mutate relevance (it stays a gate/learning concern, spec §19).
#
# app.py keeps: policy hard gates (run BEFORE this engine — spec: scoring only after ALLOW),
# taxonomy helpers (injected via `H`), HTTP routes, and the legacy v1 scorer as rollback
# (env KLEAL_CORE_V2=0). This module is import-safe: stdlib only, no I/O besides load_config().

import hashlib, math

# ------------------------------------------------------------------ config: mini-YAML + validation
# The canonical config uses a restricted YAML subset (nested maps, scalar lists, scalars). A tiny
# deterministic parser avoids a PyYAML dependency on the pod AND YAML-1.1 surprises (PyYAML reads
# the unquoted quiet-hour 09:00 as sexagesimal int 540). The file is sha-pinned, so the exact
# bytes this parser was written against are guaranteed.

PINNED_SHA = "21505ccb4add960291a742084b36d25289ffc93c9870a80b8cba3295010e9c5b"

FEATURE_KEYS = ("semantic_activity", "time_feasibility", "location_feasibility", "mode_format",
                "directed_preferences", "social_context", "domain_constraints")

class ConfigError(Exception):
    pass

def _scalar(s):
    t = s.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "'\"":
        return t[1:-1]
    low = t.lower()
    if low in ("true", "yes"):  return True
    if low in ("false", "no"):  return False
    if low in ("null", "~", ""): return None
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        pass
    return t

def parse_mini_yaml(text):
    lines = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        lines.append((len(raw) - len(raw.lstrip(" ")), raw.strip()))
    pos = [0]

    def block(indent):
        first_i, first_s = lines[pos[0]]
        if first_s.startswith("- "):                       # list of scalars
            out = []
            while pos[0] < len(lines):
                i, s = lines[pos[0]]
                if i != indent or not s.startswith("- "):
                    break
                out.append(_scalar(s[2:]))
                pos[0] += 1
            return out
        out = {}
        while pos[0] < len(lines):
            i, s = lines[pos[0]]
            if i < indent:
                break
            if i > indent:
                raise ConfigError("unexpected indent: %r" % s)
            if ":" not in s:
                raise ConfigError("bad line: %r" % s)
            k, v = s.split(":", 1)
            k, v = k.strip(), v.strip()
            pos[0] += 1
            if v == "":
                if pos[0] < len(lines) and (lines[pos[0]][0] > i or
                        (lines[pos[0]][0] == i and lines[pos[0]][1].startswith("- "))):
                    out[k] = block(lines[pos[0]][0])   # child map, or a list at the key's own indent
                else:
                    out[k] = None
            else:
                out[k] = _scalar(v)
        return out

    return block(0) if lines else {}

def load_config(path, expect_sha=PINNED_SHA):
    """Read + sha-verify + parse + validate the canonical YAML. Raises ConfigError on ANY problem —
    the caller falls back to the legacy scorer (spec §21.4: config mismatch -> stop, don't mix)."""
    with open(path, "rb") as f:
        blob = f.read()
    sha = hashlib.sha256(blob).hexdigest()
    if expect_sha and sha != expect_sha:
        raise ConfigError("config sha mismatch: got %s…, spec pins %s…" % (sha[:12], expect_sha[:12]))
    cfg = parse_mini_yaml(blob.decode("utf-8"))
    if not cfg.get("config_version"):
        raise ConfigError("config_version missing")
    fg = cfg.get("feature_groups") or {}
    for k in FEATURE_KEYS:
        p = (fg.get(k) or {}).get("unknown_prior")
        if not isinstance(p, (int, float)) or not (0.0 <= p <= 1.0):
            raise ConfigError("bad unknown_prior for feature group %r" % k)
    doms = cfg.get("domains") or {}
    if not doms:
        raise ConfigError("domains missing")
    for d, dc in doms.items():
        w = (dc or {}).get("weights") or {}
        extra = set(w) - set(FEATURE_KEYS)
        if extra:
            raise ConfigError("unknown feature keys in domain %r: %s" % (d, sorted(extra)))
        s = sum(float(w.get(k, 0) or 0) for k in FEATURE_KEYS)
        if abs(s - 1.0) > 1e-6:
            raise ConfigError("weights of domain %r sum to %.4f, must be 1.0" % (d, s))
        for t in ("uncertainty_lambda", "outreach_min_lcb", "discovery_min_lcb",
                  "outreach_min_coverage", "discovery_min_coverage"):
            v = dc.get(t)
            if not isinstance(v, (int, float)) or not (0.0 <= v <= 1.0):
                raise ConfigError("bad %s in domain %r" % (t, d))
    for req in ("semantic_tiers", "user_facing_bands"):
        if not isinstance(cfg.get(req), dict):
            raise ConfigError("%s missing" % req)
    cfg["_sha256"] = sha
    return cfg

# ------------------------------------------------------------------ domain inference
# The engine's domains are the spec's; buddy/matching intents carry looser types+topics.
_TYPE2DOMAIN = {"gaming": "games", "sport": "sport_activity", "networking": "professional_networking",
                "language": "language_exchange", "dating": "dating"}
_BROAD2DOMAIN = {"games": "games", "sports": "sport_activity", "outdoors": "sport_activity",
                 "culture": "culture_event", "music": "culture_event",
                 "learning": "language_exchange", "tech": "professional_networking"}

def infer_domain(intent, cat_of):
    t = str(intent.get("type") or "").lower()
    if t == "dating":
        return "dating"
    topics = [str(x).lower() for x in (intent.get("topics") or [])]
    blob = " ".join(topics + [str(intent.get("title") or "")]).lower()
    if any(w in blob for w in ("walk", "stroll", "прогул", "гуля")):
        return "walk"
    if any(w in blob for w in ("cowork", "поработ")):
        return "coworking"
    if "watch" in blob or "смотреть" in blob:
        return "watch_together"
    if t in _TYPE2DOMAIN:
        return _TYPE2DOMAIN[t]
    for x in topics:
        b = cat_of(x)[0]
        if b in _BROAD2DOMAIN:
            return _BROAD2DOMAIN[b]
    return "social_meet"

# ------------------------------------------------------------------ feature builder (A -> B)
K_MATCH, K_MISM, UNKNOWN, NA = "known_match", "known_mismatch", "unknown", "not_applicable"

# Observed-value anchors for the ONE aggregated subfeature per group (not tunable weights — the
# per-group weighting comes from the YAML; these are the spec §6 semantic distances).
SEM_VALUE = {4: 1.0, 3: 0.65, 2: 0.45, 1: 0.25}   # exact/alias > sibling > parent > adjacent
GEO_BANDS = ((1.5, 1.0), (3.5, 0.85), (7.0, 0.65), (15.0, 0.45))
VIBE_CLASH = {("chill", "party"), ("calm", "energetic"), ("introvert", "extrovert"),
              ("competitive", "chill"), ("calm", "competitive")}
LANG_WORDS = {"spanish": "es", "espanol": "es", "испан": "es", "english": "en", "англ": "en",
              "french": "fr", "франц": "fr", "german": "de", "нем": "de", "russian": "ru",
              "русск": "ru", "catalan": "ca", "italian": "it", "италь": "it", "japanese": "ja"}

def _haversine(a, b):
    R = 6371.0088
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return round(2 * R * math.asin(min(1.0, math.sqrt(h))), 2)

def _latlon(obj):
    if not isinstance(obj, dict):
        return None
    for src in (obj.get("geo") if isinstance(obj.get("geo"), dict) else None, obj):
        if not isinstance(src, dict):
            continue
        for la, lo in (("coarseLat", "coarseLon"), ("coarseLat", "coarseLng"), ("lat", "lon"), ("lat", "lng")):
            if isinstance(src.get(la), (int, float)) and isinstance(src.get(lo), (int, float)):
                return (float(src[la]), float(src[lo]))
    return None

def _lang_codes(seq):
    return {str(l)[:2].lower() for l in (seq or []) if str(l).strip()}

def build_features(intent, prof, cand, domain, H, role_conflict):
    """A->B evidence for the 7 groups -> {group: (state, value, detail)}. One aggregated subfeature
    per group; alias/parent readings of the same interest collapse into one matched set (no double
    count, spec §6.1)."""
    F = {}
    topics = [str(t).lower() for t in (intent.get("topics") or [])]
    ints = [str(x).lower() for x in (cand.get("interests") or [])]

    # 1. semantic_activity — taxonomy tiers via injected `topical` (exact 4 … adjacent 1)
    if not topics or not ints:
        F["semantic_activity"] = (UNKNOWN, None, "")
    else:
        best, matched = H["topical"](topics, ints)
        if best >= 1:
            # show the candidate's ORIGINAL interest strings, not the space-stripped normal forms
            orig = [str(o) for o in (cand.get("interests") or [])
                    if str(o).lower().replace(" ", "") in matched]
            names = ", ".join(sorted(orig)[:3]) or ", ".join(sorted(matched)[:3])
            F["semantic_activity"] = (K_MATCH, SEM_VALUE[best], names)
        else:
            F["semantic_activity"] = (K_MISM, 0.05, "")

    # 2. time_feasibility — nobody stores confirmed availability yet; the only live signal is the
    # demo-pool 'open' flag. Real store users -> unknown (prior), NOT a silent match.
    tspec = str(intent.get("time") or "").strip().lower()
    has_time = bool(tspec) and tspec != "flexible"
    if cand.get("open") is True:
        F["time_feasibility"] = (K_MATCH, 0.85 if has_time else 0.7, "open now")
    elif cand.get("open") is False and has_time:
        F["time_feasibility"] = (K_MISM, 0.25, "may be busy")
    else:
        F["time_feasibility"] = (UNKNOWN, None, "")

    # 3. location_feasibility — searcher-relative distance (NOT a hardcoded city centre); online
    # intents make the group not_applicable (excluded from the denominator entirely)
    mode = str(intent.get("mode") or "").lower()
    if mode == "online":
        F["location_feasibility"] = (NA, None, "")
    else:
        me, him = _latlon(prof), _latlon(cand)
        km = _haversine(me, him) if (me and him) else (
            float(cand["km"]) if isinstance(cand.get("km"), (int, float)) else None)
        if km is None:
            F["location_feasibility"] = (UNKNOWN, None, "")
        else:
            v = 0.15
            for lim, val in GEO_BANDS:
                if km <= lim:
                    v = val
                    break
            F["location_feasibility"] = ((K_MATCH if v >= 0.45 else K_MISM), v, "%.1f km" % km)

    # 4. mode_format — candidates rarely declare formats; unknown, not assumed compatible
    fmts = [str(x).lower() for x in (cand.get("formats") or [])]
    if not mode or not fmts:
        F["mode_format"] = (UNKNOWN, None, "")
    elif any(mode in f for f in fmts) or any(f in ("any", "both") for f in fmts):
        F["mode_format"] = (K_MATCH, 1.0, mode)
    else:
        F["mode_format"] = (K_MISM, 0.2, "")

    # 5. directed_preferences — only when the intent actually targets a role (play/watch/…)
    irole = str(intent.get("role") or "meet").lower()
    crole = str(cand.get("role") or "").lower()
    if irole in ("", "meet"):
        F["directed_preferences"] = (NA, None, "")
    elif not crole:
        F["directed_preferences"] = (UNKNOWN, None, "")
    elif irole == crole:
        F["directed_preferences"] = (K_MATCH, 1.0, irole)
    elif (irole, crole) in role_conflict:
        F["directed_preferences"] = (K_MISM, 0.15, crole)
    else:
        F["directed_preferences"] = (K_MATCH, 0.55, crole)

    # 6. social_context — vibe compatibility; clash matrix, otherwise mild positive
    mv = str(prof.get("vibe") or "").lower()
    cv = str(cand.get("vibe") or "").lower()
    if not mv or not cv:
        F["social_context"] = (UNKNOWN, None, "")
    elif mv == cv:
        F["social_context"] = (K_MATCH, 1.0, cv)
    elif (mv, cv) in VIBE_CLASH or (cv, mv) in VIBE_CLASH:
        F["social_context"] = (K_MISM, 0.25, cv)
    else:
        F["social_context"] = (K_MATCH, 0.55, cv)

    # 7. domain_constraints — the domain's mandatory fields (language pair, platform/community…)
    clangs = _lang_codes(cand.get("langs"))
    reql = _lang_codes(intent.get("requiredLanguages"))
    if domain == "language_exchange":
        want = {code for w, code in LANG_WORDS.items() for t in topics if w in t}
        if want:
            hit = want & clangs
            F["domain_constraints"] = (K_MATCH, 1.0, ",".join(sorted(hit))) if hit else (K_MISM, 0.1, "")
        else:
            F["domain_constraints"] = (UNKNOWN, None, "")
    elif reql:
        # the hard gate already blocked true mismatches; surviving candidates confirmed the requirement
        F["domain_constraints"] = (K_MATCH, 1.0, ",".join(sorted(reql)))
    elif domain in ("games", "sport_activity"):
        ents = " | ".join(str(e).lower() for e in (cand.get("entities") or []))
        if ents and any(t in ents for t in topics):
            F["domain_constraints"] = (K_MATCH, 0.8, "same community")
        else:
            F["domain_constraints"] = (UNKNOWN, None, "")    # platform/server/level not collected yet
    else:
        F["domain_constraints"] = (NA, None, "")              # no mandatory domain fields for this intent

    return F

def _profile_as_candidate(prof):
    langs = ((prof.get("languages") or {}).get("comfortable")) or prof.get("langs") or []
    return {"interests": prof.get("interests") or [], "vibe": prof.get("vibe"),
            "langs": langs, "geo": prof.get("geo"), "open": None, "role": prof.get("role")}

def reverse_features(intent, prof, cand, domain, H, role_conflict):
    """B->A: does the searcher fit what B declared? B's own active intent (topics) is the strongest
    signal; otherwise B's interests act as their standing preferences. Sparse B data -> low reverse
    coverage -> conservative reciprocal (honest, spec §10: unknown is not openness)."""
    b_int = next((i for i in (cand.get("intents") or []) if isinstance(i, dict)), None)
    b_topics = [str(t).lower() for t in ((b_int or {}).get("topics") or [])] or \
               [str(x).lower() for x in (cand.get("interests") or [])]
    pseudo_intent = {"topics": b_topics, "mode": intent.get("mode"),
                     "time": (b_int or {}).get("time"), "role": (b_int or {}).get("role") or "meet"}
    return build_features(pseudo_intent, cand, _profile_as_candidate(prof), domain, H, role_conflict)

# ------------------------------------------------------------------ relevance (spec §9)
def directional_score(F, dom_cfg, priors):
    W = dom_cfg["weights"]
    lam = float(dom_cfg["uncertainty_lambda"])
    tw = kw = acc = 0.0
    unknowns = []
    for k in FEATURE_KEYS:
        w = float(W.get(k, 0) or 0)
        if w <= 0:
            continue
        st, v, _d = F.get(k, (UNKNOWN, None, ""))
        if st == NA:
            continue                                   # excluded from the denominator (spec §9.1)
        tw += w
        if st == UNKNOWN:
            acc += w * float(priors[k])
            unknowns.append(k)
        else:
            acc += w * float(v)
            kw += w
    if tw <= 0:
        return {"mean": 0.0, "coverage": 0.0, "lcb": 0.0, "unknowns": unknowns}
    mean, cov = acc / tw, kw / tw
    lcb = max(0.0, min(1.0, mean - lam * (1.0 - cov)))
    return {"mean": round(mean, 4), "coverage": round(cov, 4), "lcb": round(lcb, 4), "unknowns": unknowns}

def reciprocal_score(a, b):
    """Spec §9.4 over the conservative estimates: 0.7*min + 0.3*mean, penalises one-sided pairs."""
    lo, hi = min(a["lcb"], b["lcb"]), max(a["lcb"], b["lcb"])
    return round(0.7 * lo + 0.3 * (lo + hi) / 2.0, 4)

# ------------------------------------------------------------------ tiers (provenance, spec §7)
def assign_tier(intent, cand, topics, H):
    if H["reciprocal"](intent, cand):
        return "T0"                                    # candidate's own active intent matches
    ints = [str(x).lower() for x in (cand.get("interests") or [])]
    best = H["topical"](topics, ints)[0] if (topics and ints) else 0
    if best >= 4:
        return "T1"                                    # direct confirmed interest
    if best in (2, 3):
        return "T2"                                    # sibling / parent category
    if best == 1:
        return "T3"                                    # adjacent context only
    return "T5"                                        # no meaningful overlap -> never shown

TIER_KIND = {"T0": "reciprocal", "T1": "exact", "T2": "related", "T3": "adjacent"}

# ------------------------------------------------------------------ presentation (spec §9.7)
BAND_LABELS = {
    "especially_close":    ("Особенно близко к вашему запросу", "Especially close to your request"),
    "strong_option":       ("Хороший вариант", "Strong option"),
    "broader_option":      ("Более широкий вариант", "Broader option"),
    "needs_clarification": ("Нужно уточнение", "Needs clarification"),
}
BAND_RANK = {"especially_close": 0, "strong_option": 1, "broader_option": 2, "needs_clarification": 3}

def assign_band(lcb, cov, bands):
    for name in ("especially_close", "strong_option", "broader_option"):
        b = bands.get(name) or {}
        if lcb >= float(b.get("min_lcb", 1)) and cov >= float(b.get("min_coverage", 1)):
            return name
    return "needs_clarification"

_REASON = {
    "semantic_activity":   lambda d: (("общее: %s" % d, "shares %s" % d) if d else
                                      ("близкая тема", "related topic")),
    "time_feasibility":    lambda d: ("открыт(а) к встрече сейчас", "open to meet now"),
    "location_feasibility":lambda d: ("рядом (%s)" % d, "nearby (%s)" % d),
    "mode_format":         lambda d: ("совпадает формат", "format fits"),
    "directed_preferences":lambda d: ("подходящая роль (%s)" % d, "matching role (%s)" % d),
    "social_context":      lambda d: ("похожий вайб", "similar vibe"),
    "domain_constraints":  lambda d: ("совпадают условия (%s)" % d, "constraints fit (%s)" % d),
}
_GAP = {
    "semantic_activity":   ("интересы не заполнены", "interests not filled in"),
    "time_feasibility":    ("время не подтверждено", "time not confirmed"),
    "location_feasibility":("район не указан", "area unknown"),
    "mode_format":         ("формат не уточнён", "format not set"),
    "directed_preferences":("роль не указана", "role unknown"),
    "social_context":      ("вайб не указан", "vibe unknown"),
    "domain_constraints":  ("детали (платформа/уровень) не указаны", "domain details unknown"),
}

def _presentation(F, d_ab, dom_cfg):
    """2-3 confirmed reasons (known_match only — never invented facts) + the single top gap."""
    W = dom_cfg["weights"]
    known = [(float(W.get(k, 0)) * float(v), k, d)
             for k, (st, v, d) in F.items() if st == K_MATCH and float(W.get(k, 0)) > 0]
    known.sort(key=lambda x: -x[0])
    rs_ru, rs_en, legacy = [], [], []
    for _wv, k, d in known[:3]:
        ru, en = _REASON[k](d)
        rs_ru.append(ru); rs_en.append(en)
        if k == "semantic_activity" and d:
            legacy.append("shares " + d)               # exact legacy phrasing buddy.humanize knows
        elif k == "social_context":
            legacy.append("similar vibe")
        elif k == "location_feasibility" and d:
            legacy.append("very close (%s)" % d)
        elif k == "time_feasibility":
            legacy.append("open to meet")
        else:
            legacy.append(en)
    gaps = [(float(W.get(k, 0)), k) for k, (st, v, d) in F.items()
            if st == K_MISM and float(W.get(k, 0)) > 0]
    if not gaps:
        gaps = [(float(W.get(k, 0)), k) for k in d_ab["unknowns"]]
    gaps.sort(key=lambda x: -x[0])
    gap_ru = gap_en = None
    if gaps:
        gap_ru, gap_en = _GAP[gaps[0][1]]
    return rs_ru, rs_en, legacy, gap_ru, gap_en

# ------------------------------------------------------------------ allocation (slate diversity)
TOP_N, PER_BUCKET = 8, 3        # slate size params (allocation layer, not relevance — spec §11)

def _slate(items):
    buckets = {it.get("bucket") or "other" for it in items}
    cap = PER_BUCKET if len(buckets) > 2 else TOP_N
    seen, out = {}, []
    for it in items:
        b = it.get("bucket") or "other"
        if seen.get(b, 0) >= cap:
            continue
        seen[b] = seen.get(b, 0) + 1
        out.append(it)
        if len(out) >= TOP_N:
            break
    return out

# ------------------------------------------------------------------ main entry
def search(intent, prof, ctx, candidates, H, cfg):
    """Score policy-ALLOWED candidates. Returns (slate, meta). `H` injects the taxonomy helpers
    from app.py: {'topical', 'cat_of', 'reciprocal', 'role_conflict'} — taxonomy stays single-sourced."""
    intent, prof, ctx = intent or {}, prof or {}, ctx or {}
    domain = infer_domain(intent, H["cat_of"])
    dom_cfg = cfg["domains"].get(domain) or cfg["domains"]["social_meet"]
    priors = {k: (cfg["feature_groups"][k] or {}).get("unknown_prior", 0.5) for k in FEATURE_KEYS}
    bands = cfg["user_facing_bands"]
    role_conflict = H.get("role_conflict") or set()
    topics = [str(t).lower() for t in (intent.get("topics") or [])]
    out = []
    for c in candidates:
        tier = assign_tier(intent, c, topics, H)
        if tier == "T5":
            continue                                    # no meaningful overlap -> never proposed
        if tier == "T3" and not intent.get("adjacentAllowed", True):
            continue
        if tier == "T2" and intent.get("exactMatchRequired"):
            continue
        F = build_features(intent, prof, c, domain, H, role_conflict)
        d_ab = directional_score(F, dom_cfg, priors)
        d_ba = directional_score(reverse_features(intent, prof, c, domain, H, role_conflict),
                                 dom_cfg, priors)
        rec = reciprocal_score(d_ab, d_ba)
        disc_ok = (d_ab["lcb"] >= float(dom_cfg["discovery_min_lcb"]) and
                   d_ab["coverage"] >= float(dom_cfg["discovery_min_coverage"]))
        if not disc_ok and tier not in ("T0", "T1"):
            continue                                    # weak AND indirect -> drop; direct matches
        #                                                 stay visible as "needs clarification"
        band = assign_band(d_ab["lcb"], d_ab["coverage"], bands) if disc_ok else "needs_clarification"
        outreach_tier_ok = tier in ("T0", "T1") or (tier == "T2" and bool(intent.get("broadConsent")))
        can_outreach = (outreach_tier_ok and
                        d_ab["lcb"] >= float(dom_cfg["outreach_min_lcb"]) and
                        d_ab["coverage"] >= float(dom_cfg["outreach_min_coverage"]))
        rs_ru, rs_en, legacy_reasons, gap_ru, gap_en = _presentation(F, d_ab, dom_cfg)
        matched = F["semantic_activity"][2] or ""
        bucket = (H["cat_of"](matched.split(", ")[0])[0] if matched else
                  H["cat_of"]((c.get("interests") or ["x"])[0])[0]) or "other"
        km_txt = F["location_feasibility"][2] if F["location_feasibility"][0] in (K_MATCH, K_MISM) else ""
        km = float(km_txt.split(" ")[0]) if km_txt else c.get("km")
        agree = bool(can_outreach and c.get("open") is not False)
        note = ("Agent agreed — " + (legacy_reasons[0] if legacy_reasons else "good fit")) if agree else \
               ("Agent: needs clarification" if band == "needs_clarification" else "Agent: fit too weak")
        band_ru, band_en = BAND_LABELS[band]
        out.append({
            # ---- legacy card contract (buddy/_card + profile UI keep rendering) ----
            "name": c.get("name"), "score": round(d_ab["lcb"] * 100, 1), "tier": tier,
            "kind": TIER_KIND.get(tier, "related"), "km": km, "vibe": c.get("vibe"),
            "open": c.get("open"), "verified": c.get("verified"), "age": c.get("age"),
            "interests": c.get("interests") or [], "role": c.get("role"),
            "dealBreakers": c.get("dealBreakers"), "reasons": legacy_reasons or rs_en,
            "agree": agree, "note": note, "bucket": bucket,
            # ---- Matching Core v2 (spec) ----
            "band": band, "band_ru": band_ru, "band_en": band_en,
            "reasons_ru": rs_ru, "reasons_en": rs_en, "gap_ru": gap_ru, "gap_en": gap_en,
            "coverage": d_ab["coverage"], "lcb": d_ab["lcb"], "reciprocal": rec,
            "unknowns": d_ab["unknowns"], "can_outreach": can_outreach,
            "trace": {"tier": tier, "policy": "ALLOW", "domain": domain,
                      "a_to_b": d_ab, "b_to_a": d_ba, "reciprocal": rec,
                      "band": band, "config_version": cfg.get("config_version")},
        })
    out.sort(key=lambda x: (BAND_RANK[x["band"]], -x["reciprocal"], -x["lcb"], -x["coverage"],
                            str(x["name"])))
    meta = {"core": "v2", "config_version": cfg.get("config_version"), "domain": domain,
            "config_sha": cfg.get("_sha256", "")[:12]}
    return _slate(out), meta
