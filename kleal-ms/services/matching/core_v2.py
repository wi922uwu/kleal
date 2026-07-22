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

import hashlib, math, time

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
# exact/alias 1.0; sibling 0.6 (spec §6 range 0.55-0.75); parent/broad 0.3; adjacent 0.15.
# Parent must sit far below exact: with equal semantic/social weights (social_meet 0.18/0.18),
# a higher parent anchor lets a same-vibe brunch person outscore a walker on a walk query.
SEM_VALUE = {4: 1.0, 3: 0.6, 2: 0.3, 1: 0.15}
GEO_FAR_KM = 25.0                                  # beyond this, distance stops discriminating

def _geo_value(km):
    """Continuous distance feasibility. Four fixed bands quantised everyone inside a neighbourhood
    onto the SAME value, so whole slates tied on one score and the order fell back to the alphabet
    (every "Lopez" first). A smooth ramp keeps "closer is better" meaningful at street level."""
    return round(max(0.1, min(1.0, 1.0 - float(km) / GEO_FAR_KM)), 4)
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
            # `matched` now carries the candidate's own strings, so the card quotes them verbatim
            names = ", ".join(sorted(str(m) for m in matched)[:3])
            # multi-topic intents: someone matching MORE of the asked topics must outrank a
            # one-topic overlap ("стартапы+ai+кофе" -> a founder beats a coffee-only person).
            # Single aggregated subfeature, capped at 1.0 — still no double count (spec §6.1).
            value = SEM_VALUE[best]
            if len(topics) > 1:
                # only EXACT topic hits count as covering an asked topic — a russian speaker
                # sub-matching "spanish" hasn't covered the spanish ask
                hits = sum(1 for t in topics if H["topical"]([t], ints)[0] >= 4)
                value = round(value * (0.6 + 0.4 * max(1, hits) / len(topics)), 4)
            F["semantic_activity"] = (K_MATCH, value, names)
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
            v = _geo_value(km)
            F["location_feasibility"] = ((K_MATCH if v >= 0.45 else K_MISM), v, "%.1f km" % km)

    # 4. mode_format — does the candidate accept this plan's mode (online/offline)?
    # Only the mode-bearing formats count: online / offline / hybrid (and legacy any/both). A person
    # who ticked only sizes (1:1, small group) has NOT stated an online/offline preference, so that
    # stays UNKNOWN rather than a penalty. 'hybrid' means both — it matches either mode. A genuine
    # opposite-only declaration (offline-only on an online plan) is the one case that is penalised.
    _MODE_FMTS = ("online", "offline", "hybrid", "any", "both")
    fmts = [str(x).lower() for x in (cand.get("formats") or []) if str(x).lower() in _MODE_FMTS]
    if not mode or not fmts:
        F["mode_format"] = (UNKNOWN, None, "")
    elif mode in fmts or any(f in ("hybrid", "any", "both") for f in fmts):
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
        # Neutral vibes sat at 0.55, so an identical vibe string was worth 0.45 — MORE than the
        # spread topical coverage can produce. A person sharing 1 of 3 asked topics outranked one
        # sharing 2 of 3 purely because their vibe label matched. Vibe is context, not the ask.
        F["social_context"] = (K_MATCH, 0.8, cv)

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
            "langs": langs, "geo": prof.get("geo"), "open": None, "role": prof.get("role"),
            "formats": prof.get("formats") or []}     # so B->A can judge the searcher's mode too

def reverse_features(intent, prof, cand, domain, H, role_conflict):
    """B->A: does the searcher fit what B declared? B's own active intent (topics) is the strongest
    signal; otherwise B's interests act as their standing preferences. Sparse B data -> low reverse
    coverage -> conservative reciprocal (honest, spec §10: unknown is not openness)."""
    b_int = next((i for i in (cand.get("intents") or []) if isinstance(i, dict)), None)
    b_topics = [str(t).lower() for t in ((b_int or {}).get("topics") or [])] or \
               [str(x).lower() for x in (cand.get("interests") or [])]
    pseudo_intent = {"topics": b_topics, "mode": intent.get("mode"),
                     "time": (b_int or {}).get("time"), "role": (b_int or {}).get("role") or "meet"}
    a_as_cand = _profile_as_candidate(prof)
    # Spec §4.2 source hierarchy: A's CURRENT intent is the strongest evidence about A — B's side
    # judges the searcher by what they are asking for right now, not only by stored profile
    # interests. Without this, an empty searcher profile makes every B->A semantic unknown and
    # prior noise (not the match) ends up ordering the slate.
    a_as_cand["interests"] = list(a_as_cand.get("interests") or []) + \
                             [str(t) for t in (intent.get("topics") or [])]
    return build_features(pseudo_intent, cand, a_as_cand, domain, H, role_conflict)

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

# ------------------------------------------------------------------ receiving readiness (spec §10.1)
# Readiness answers "may this person be approached NOW for this purpose" — it NEVER mixes into
# relevance (spec §10: "эти величины не складываются"). It gates can_outreach, orders the slate
# (§11.2) and is shown as an availability status; paused people leave retrieval entirely.
READINESS_LABELS = {
    "open_now":          ("открыт(а) сейчас", "open now"),
    "open_later":        ("не сейчас — тихие часы", "later (quiet hours)"),
    "passive_discovery": ("только в подборке", "discovery only"),
    "busy":              ("сейчас занят(а)", "busy right now"),
    "paused":            ("на паузе", "paused"),
    "unknown":           ("доступность не настроена", "availability not set"),
}
READINESS_RANK = {"open_now": 0, "open_later": 1, "unknown": 2, "passive_discovery": 3, "busy": 4,
                  "paused": 5}
ALL_DOMAINS = ("social_meet", "walk", "games", "language_exchange", "sport_activity",
               "culture_event", "professional_networking", "watch_together", "coworking", "dating")

def _hhmm_to_min(s):
    try:
        h, m = str(s).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None

def _in_quiet_hours(now_min, start, end):
    a, b = _hhmm_to_min(start), _hhmm_to_min(end)
    if a is None or b is None or now_min is None:
        return False
    if a <= b:
        return a <= now_min < b
    return now_min >= a or now_min < b                 # window wraps midnight (22:00 -> 09:00)

def _parse_ts(v):
    """paused_until: epoch seconds or 'YYYY-MM-DDTHH:MM' (pod-local). None if unreadable."""
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return time.mktime(time.strptime(str(v)[:16], "%Y-%m-%dT%H:%M"))
    except Exception:
        return None

def is_paused(cand, now_ts=None):
    """True when the person opted out of retrieval (legacy flag, receiving.status, paused_until)."""
    if cand.get("paused"):
        return True
    r = cand.get("receiving")
    if not isinstance(r, dict):
        return False
    if str(r.get("status") or "").lower() == "paused":
        pu = _parse_ts(r.get("paused_until"))
        return True if pu is None else (pu > (now_ts or time.time()))
    pu = _parse_ts(r.get("paused_until"))
    return bool(pu and pu > (now_ts or time.time()))

def readiness_state(cand, domain, now_ts, cfg, received_24h=0):
    """Spec §10.1 states. Sources, in order: receiving policy (canonical §4.4 object on the user),
    else the demo-pool legacy 'open' flag as an explicit availability signal, else unknown —
    and unknown is NOT openness: no personal outreach without a policy or a probe."""
    if is_paused(cand, now_ts):
        return "paused"
    r = cand.get("receiving")
    out_cfg = (cfg or {}).get("outreach") or {}
    if not isinstance(r, dict):
        if cand.get("open") is True:
            return "open_now"
        if cand.get("open") is False:
            return "busy"
        return "unknown"
    if str(r.get("status") or "").lower() == "busy":
        return "busy"
    # Opt-outs must fail CLOSED. Truthiness read `per_24h: 0` and `allowed_domains: []` as
    # "not set" and fell back to the permissive default — so a user who explicitly asked for zero
    # proposals, or allowed no domain at all, became MORE reachable than someone who set nothing.
    pb = (r.get("proposal_budget") or {}).get("per_24h")
    cap = pb if isinstance(pb, (int, float)) and not isinstance(pb, bool) else \
        (out_cfg.get("max_proposals_received_per_user_24h") or 4)
    if received_24h >= int(cap):
        return "busy"                                   # proposal fatigue: overloaded today
    doms = r.get("allowed_domains")
    if isinstance(doms, list) and domain not in doms:
        return "passive_discovery"                      # visible in discovery, no personal proposals
    q = r.get("quiet_hours") or {}
    defaults = out_cfg.get("quiet_hours_local") or ["22:00", "09:00"]
    if now_ts:
        # pilot: fixed local offset (Europe/Madrid summer = UTC+120min) stored on the policy
        local_min = int((now_ts // 60 + int(q.get("tz_offset_min", 120))) % 1440)
        if _in_quiet_hours(local_min, q.get("start") or defaults[0], q.get("end") or defaults[-1]):
            return "open_later"
    if r.get("passive_outreach") is False:
        return "passive_discovery"
    return "open_now"

# ------------------------------------------------------------------ presentation (spec §9.7)
BAND_LABELS = {
    "especially_close":    ("Особенно близко к вашему запросу", "Especially close to your request"),
    "strong_option":       ("Хороший вариант", "Strong option"),
    "broader_option":      ("Более широкий вариант", "Broader option"),
    "needs_clarification": ("Нужно уточнение", "Needs clarification"),
}
BAND_RANK = {"especially_close": 0, "strong_option": 1, "broader_option": 2, "needs_clarification": 3}

def assign_band(lcb, cov, bands, sem=None):
    """Bands answer two different questions and must not be conflated: how GOOD the fit is
    (lcb) and how much of it is CONFIRMED (coverage). "Needs clarification" means the data is
    thin — the config says so explicitly (needs_clarification.max_coverage). It used to be the
    catch-all for anything below the top three, so a candidate with 0.88 coverage and one
    unknown field was told to "clarify" when nothing was missing; they are simply a weaker fit."""
    # A badge must not outrun the topical evidence. semantic_activity is at most ~21% of the score, so
    # time + distance + format + vibe alone could carry an adjacency-only candidate to «Хороший
    # вариант» (measured: lcb 0.735, coverage 1.0, topical contributing 4.4%). The two confident bands
    # now require a real topical match — same broad category or better, SEM_VALUE[3] = 0.6 — while the
    # candidate stays visible as a broader option. Nothing is hidden; the claim is just made honest.
    top_ok = sem is None or float(sem) >= 0.6
    for name in ("especially_close", "strong_option", "broader_option"):
        b = bands.get(name) or {}
        if name in ("especially_close", "strong_option") and not top_ok:
            continue
        if lcb >= float(b.get("min_lcb", 1)) and cov >= float(b.get("min_coverage", 1)):
            return name
    thin = float((bands.get("needs_clarification") or {}).get("max_coverage", 0.39))
    return "needs_clarification" if cov <= thin else "broader_option"

# Human-readable values for detail strings that would otherwise leak engine tokens into the copy
_ROLE_RU = {"play": "поиграть", "watch": "посмотреть", "discuss": "обсудить",
            "practise": "попрактиковаться", "attend": "сходить", "meet": "встретиться"}
_DETAIL_RU = {"same community": "то же сообщество", "open now": "свободен(на)"}
_LANG_RU = {"es": "испанский", "en": "английский", "ru": "русский", "fr": "французский",
            "de": "немецкий", "it": "итальянский", "ca": "каталанский", "pt": "португальский"}

def _ru_detail(d):
    """Translate a detail token for Russian copy — 'same community', a role or a language code
    used to appear verbatim inside otherwise-Russian reasons."""
    s = str(d or "")
    if s in _DETAIL_RU:  return _DETAIL_RU[s]
    if s in _ROLE_RU:    return _ROLE_RU[s]
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if parts and all(p in _LANG_RU for p in parts):
        return ", ".join(_LANG_RU[p] for p in parts)
    return s

_REASON = {
    # NOTE: time_feasibility is only rendered when the group is a known_match, i.e. the person
    # really is open now — the card used to claim "открыт(а) к встрече сейчас" next to a
    # readiness chip that said "занят", because the wording ignored the actual state.
    "semantic_activity":   lambda d: (("общее: %s" % d, "shares %s" % d) if d else
                                      ("близкая тема", "related topic")),
    "time_feasibility":    lambda d: ("свободен(на) в это время", "free at that time"),
    "location_feasibility":lambda d: ("рядом (%s)" % str(d).replace(" km", " км"), "nearby (%s)" % d),
    "mode_format":         lambda d: ("совпадает формат", "format fits"),
    "directed_preferences":lambda d: ("подходящая роль (%s)" % _ru_detail(d),
                                      "matching role (%s)" % d),
    "social_context":      lambda d: ("похожий вайб", "similar vibe"),
    "domain_constraints":  lambda d: ("совпадают условия (%s)" % _ru_detail(d),
                                      "constraints fit (%s)" % d),
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
# A verified CONFLICT is not missing data. Saying "роль не указана" about someone whose role the
# engine checked and found opposite is a false statement about a real person (spec §23.2: reasons
# and gaps must be facts the system actually established).
_GAP_MISMATCH = {
    "semantic_activity":   (lambda d: ("интересы не совпадают", "interests don't overlap")),
    "time_feasibility":    (lambda d: ("время может не совпасть", "time may not work")),
    "location_feasibility":(lambda d: ("далеко%s" % ((" — " + d) if d else ""),
                                       "far away%s" % ((" — " + d) if d else ""))),
    "mode_format":         (lambda d: ("формат не совпадает", "format doesn't match")),
    "directed_preferences":(lambda d: ("другая роль%s" % ((" (%s)" % d) if d else ""),
                                       "different role%s" % ((" (%s)" % d) if d else ""))),
    "social_context":      (lambda d: ("другой вайб%s" % ((" (%s)" % d) if d else ""),
                                       "different vibe%s" % ((" (%s)" % d) if d else ""))),
    "domain_constraints":  (lambda d: ("условия не совпадают", "constraints don't match")),
}

REASONS_SHOWN = 3      # what a card displays
REASONS_POOL = 5       # what the slate diversifier gets to choose from


def _presentation(F, d_ab, dom_cfg, readiness=None):
    """Confirmed reasons (known_match only — never invented facts) + the single top gap.

    Returns up to REASONS_POOL, weight-ordered. Callers that do not diversify must trim to
    REASONS_SHOWN themselves — a card still shows three."""
    W = dom_cfg["weights"]
    known = [(float(W.get(k, 0)) * float(v), k, d)
             for k, (st, v, d) in F.items() if st == K_MATCH and float(W.get(k, 0)) > 0]
    # never claim availability that contradicts the readiness chip on the same card: the legacy
    # 'open' flag and the receiving policy can disagree (open=True but quiet hours / busy)
    if readiness and readiness != "open_now":
        known = [x for x in known if x[1] != "time_feasibility"]
    known.sort(key=lambda x: -x[0])
    # keys travel WITH the strings: reasons come back weight-ordered, so the UI cannot know what a given
    # row is about from its position. Titling row 2 "Подходит по времени" put a distance under a time label.
    rs_ru, rs_en, legacy, keys = [], [], [], []
    for _wv, k, d in known[:REASONS_POOL]:
        ru, en = _REASON[k](d)
        rs_ru.append(ru); rs_en.append(en); keys.append(k)
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
    # a confirmed conflict outranks missing data as "the one thing to flag", and is worded as
    # a conflict — with the value the engine actually saw
    mism = [(float(W.get(k, 0)), k, d) for k, (st, v, d) in F.items()
            if st == K_MISM and float(W.get(k, 0)) > 0]
    gap_ru = gap_en = None
    if mism:
        mism.sort(key=lambda x: -x[0])
        _w, k, d = mism[0]
        gap_ru, gap_en = _GAP_MISMATCH[k](d)
    else:
        unk = [(float(W.get(k, 0)), k) for k in d_ab["unknowns"]]
        if unk:
            unk.sort(key=lambda x: -x[0])
            gap_ru, gap_en = _GAP[unk[0][1]]
    return rs_ru, rs_en, legacy, gap_ru, gap_en, keys

# ------------------------------------------------------------------ allocation (slate diversity)
TOP_N, PER_BUCKET = 8, 3        # slate size params (allocation layer, not relevance — spec §11)


def _shared_first(ints, F):
    """Put the interests the match is actually BASED on at the front of the list.

    Every card surface shows the first two or three of these. Order them as stored and the evidence
    can be invisible: a card said «общее: art» above the tags padel / hiking / yoga, because `art`
    was the person's fourth interest and never made the cut. The claim was true and looked like
    nonsense. Reordering only — nothing added, nothing hidden, relevance untouched."""
    d = str(((F or {}).get("semantic_activity") or (None, None, ""))[2] or "").lower()
    if not d:
        return list(ints)
    hit = {w.strip() for w in d.split(",") if w.strip()}
    if not hit:
        return list(ints)
    lead = [i for i in ints if str(i).strip().lower() in hit]
    rest = [i for i in ints if str(i).strip().lower() not in hit]
    return lead + rest


def _diversify_reasons(slate):
    """A reason every card in the slate carries says nothing about this particular person.

    Reasons come back weight-ordered, which is the right global order and the wrong one for a
    reader: a role-matched slate led all eight cards with «подходящая роль (обсудить)», so people
    who differ in topics, distance and vibe looked interchangeable. Compare the RENDERED strings,
    not the feature keys — every card here matched on the same three features and differed only in
    what those features contained («общее: ai, ml» vs «общее: ai, startups»), so a key-level
    comparison finds nothing to promote. Universal lines rotate to the back; nothing is removed and
    nothing is reworded. Presentation order only, never relevance (spec §11)."""
    n = len(slate)
    if n < 3:
        return
    freq = {}
    for x in slate:
        for t in set(x.get("reasons_ru") or []):
            freq[t] = freq.get(t, 0) + 1
    common = {t for t, c in freq.items() if c == n}
    for x in slate:
        ru = list(x.get("reasons_ru") or [])
        order = range(len(ru))
        if common and len(ru) > 1 and (set(ru) - common):
            order = sorted(range(len(ru)), key=lambda i: (ru[i] in common, i))
        for fld in ("reasons_ru", "reasons_en", "reasons", "reason_keys"):
            v = x.get(fld)
            if isinstance(v, list) and len(v) == len(ru):
                x[fld] = [v[i] for i in order][:REASONS_SHOWN]

def _slate(items, home_bucket=None):
    """Diversity is applied WITHIN a band and never promotes a lower band (spec §11: allocation
    must not change pair relevance). Inside one band the per-bucket cap is SOFT: if the only
    remaining same-band candidates are from a capped bucket, relevance wins and they fill the
    slot — a focused search ("кофе") must not swap coffee people for adjacent-category padding.
    The query's OWN bucket is never capped at all: capping it evicted top-ranked exact matches
    (a dinner search shipped 3 diners and 5 strangers) — variety is for the padding, not the ask."""
    out, i, n = [], 0, len(items)
    while len(out) < TOP_N and i < n:
        j = i
        while j < n and items[j]["band"] == items[i]["band"]:
            j += 1
        group, take = items[i:j], TOP_N - len(out)
        picked, seen, skipped = [], {}, []
        for it in group:
            if len(picked) >= take:
                break
            b = it.get("bucket") or "other"
            if b != home_bucket and seen.get(b, 0) >= PER_BUCKET:
                skipped.append(it)
                continue
            seen[b] = seen.get(b, 0) + 1
            picked.append(it)
        for it in skipped:                       # soft cap: backfill from the same band only
            if len(picked) >= take:
                break
            picked.append(it)
        chosen = {id(x) for x in picked}
        out.extend(x for x in group if id(x) in chosen)   # keep the relevance order
        i = j
    return out

# ------------------------------------------------------------------ main entry
FEATURE_LABELS = {
    "semantic_activity":    ("Интерес / активность", "Interest / activity"),
    "time_feasibility":     ("Время", "Time"),
    "location_feasibility": ("Расстояние", "Distance"),
    "mode_format":          ("Формат", "Format"),
    "directed_preferences": ("Роль", "Role"),
    "social_context":       ("Вайб", "Vibe"),
    "domain_constraints":   ("Условия домена", "Domain constraints"),
}

def explain(intent, prof, ctx, cand, H, cfg):
    """Full decision trace for ONE candidate — the same code path as search(), but every drop point
    records WHY instead of silently skipping. Powers the admin Matching lab (spec §21.3 decision
    trace: reproducible, per-feature, with config version). Never mutates state."""
    intent, prof, ctx = intent or {}, prof or {}, ctx or {}
    domain = infer_domain(intent, H["cat_of"])
    dom_cfg = cfg["domains"].get(domain) or cfg["domains"]["social_meet"]
    priors = {k: (cfg["feature_groups"][k] or {}).get("unknown_prior", 0.5) for k in FEATURE_KEYS}
    role_conflict = H.get("role_conflict") or set()
    topics = [str(t).lower() for t in (intent.get("topics") or [])]
    now_ts = ctx.get("now") or time.time()
    received24 = ctx.get("received24") or {}
    steps = []
    def step(name, ok, detail=""):
        steps.append({"step": name, "ok": bool(ok), "detail": detail})

    out = {"name": cand.get("name"), "domain": domain, "config_version": cfg.get("config_version"),
           "steps": steps, "shown": False, "drop_reason": None}

    paused = is_paused(cand, now_ts)
    step("retrieval: not paused", not paused, "receiving.status/paused_until" if paused else "")
    if paused:
        out["drop_reason"] = "paused — left retrieval for this purpose (§10.1)"
        return out

    tier = assign_tier(intent, cand, topics, H)
    out["tier"] = tier
    best, matched = H["topical"](topics, [str(x).lower() for x in (cand.get("interests") or [])])
    step("tier (provenance)", tier != "T5",
         "%s — topical overlap level %d%s" % (tier, best, (" on " + ", ".join(sorted(matched)[:3])) if matched else ""))
    if tier == "T5":
        out["drop_reason"] = "no meaningful topical overlap (T5) — never proposed"
        return out
    if tier == "T3" and not intent.get("adjacentAllowed", True):
        step("search breadth", False, "adjacentAllowed=false drops T3")
        out["drop_reason"] = "adjacent matches disabled for this search"
        return out
    if intent.get("exactMatchRequired") and tier not in ("T0", "T1"):
        step("search breadth", False, "exactMatchRequired keeps only T0/T1")
        out["drop_reason"] = "exact-match-only search: %s dropped" % tier
        return out

    F = build_features(intent, prof, cand, domain, H, role_conflict)
    d_ab = directional_score(F, dom_cfg, priors)
    d_ba = directional_score(reverse_features(intent, prof, cand, domain, H, role_conflict),
                             dom_cfg, priors)
    rec = reciprocal_score(d_ab, d_ba)
    W = dom_cfg["weights"]
    out["features"] = [{
        "group": k, "label_ru": FEATURE_LABELS[k][0], "label_en": FEATURE_LABELS[k][1],
        "state": F[k][0], "value": F[k][1], "detail": F[k][2], "weight": float(W.get(k, 0) or 0),
        "prior": priors[k],
    } for k in FEATURE_KEYS]
    out["a_to_b"], out["b_to_a"], out["reciprocal"] = d_ab, d_ba, rec

    disc_ok = (d_ab["lcb"] >= float(dom_cfg["discovery_min_lcb"]) and
               d_ab["coverage"] >= float(dom_cfg["discovery_min_coverage"]))
    step("discovery thresholds", disc_ok or tier in ("T0", "T1"),
         "lcb %.3f vs %.2f, coverage %.3f vs %.2f" % (d_ab["lcb"], float(dom_cfg["discovery_min_lcb"]),
                                                      d_ab["coverage"], float(dom_cfg["discovery_min_coverage"])))
    if not disc_ok and tier not in ("T0", "T1"):
        out["drop_reason"] = "below discovery thresholds and not a direct match"
        return out

    band = assign_band(d_ab["lcb"], d_ab["coverage"], cfg["user_facing_bands"]) if disc_ok else "needs_clarification"
    readiness = readiness_state(cand, domain, now_ts, cfg,
                                received24.get(str(cand.get("name", "")).strip().lower(), 0))
    outreach_tier_ok = tier in ("T0", "T1") or (tier == "T2" and bool(intent.get("broadConsent")))
    thr_ok = (d_ab["lcb"] >= float(dom_cfg["outreach_min_lcb"]) and
              d_ab["coverage"] >= float(dom_cfg["outreach_min_coverage"]))
    can_outreach = bool(outreach_tier_ok and readiness == "open_now" and thr_ok)
    step("readiness", readiness == "open_now", "%s (%s)" % (readiness, READINESS_LABELS[readiness][1]))
    step("outreach tier/consent", outreach_tier_ok,
         "%s%s" % (tier, "" if outreach_tier_ok else " needs broadConsent" if tier == "T2" else " never allows outreach"))
    step("outreach thresholds", thr_ok,
         "lcb %.3f vs %.2f, coverage %.3f vs %.2f" % (d_ab["lcb"], float(dom_cfg["outreach_min_lcb"]),
                                                      d_ab["coverage"], float(dom_cfg["outreach_min_coverage"])))
    rs_ru, rs_en, _legacy, gap_ru, gap_en, rkeys = _presentation(F, d_ab, dom_cfg, readiness)
    rs_ru, rs_en, rkeys = rs_ru[:REASONS_SHOWN], rs_en[:REASONS_SHOWN], rkeys[:REASONS_SHOWN]
    out.update({"shown": True, "band": band, "band_ru": BAND_LABELS[band][0],
                "band_en": BAND_LABELS[band][1], "readiness_en": READINESS_LABELS[readiness][1],
                "readiness": readiness, "readiness_ru": READINESS_LABELS[readiness][0],
                "can_outreach": can_outreach, "score": round(d_ab["lcb"] * 100, 1),
                "reasons_ru": rs_ru, "reasons_en": rs_en, "reason_keys": rkeys, "gap_ru": gap_ru, "gap_en": gap_en})
    return out

def search(intent, prof, ctx, candidates, H, cfg, diag=None):
    """Score policy-ALLOWED candidates. Returns (slate, meta). `H` injects the taxonomy helpers
    from app.py: {'topical', 'cat_of', 'reciprocal', 'role_conflict'} — taxonomy stays single-sourced."""
    intent, prof, ctx = intent or {}, prof or {}, ctx or {}
    domain = infer_domain(intent, H["cat_of"])
    dom_cfg = cfg["domains"].get(domain) or cfg["domains"]["social_meet"]
    priors = {k: (cfg["feature_groups"][k] or {}).get("unknown_prior", 0.5) for k in FEATURE_KEYS}
    bands = cfg["user_facing_bands"]
    role_conflict = H.get("role_conflict") or set()
    topics = [str(t).lower() for t in (intent.get("topics") or [])]
    now_ts = ctx.get("now") or time.time()             # pin ctx.now for deterministic replay
    received24 = ctx.get("received24") or {}           # {name_lower: proposals received last 24h}
    out = []
    # Every `continue` below is an answer to «почему я никого не вижу», and every one of them used to
    # be thrown away. `diag` is an optional counter the caller passes in; when absent this is exactly
    # the loop it always was.
    def _drop(reason):
        if diag is not None:
            diag[reason] = diag.get(reason, 0) + 1
    if diag is not None:
        diag["_in"] = diag.get("_in", 0) + len(candidates)
    for c in candidates:
        if is_paused(c, now_ts):
            _drop("paused")
            continue                                    # paused leaves retrieval for this purpose (§10.1)
        tier = assign_tier(intent, c, topics, H)
        if tier == "T5":
            _drop("no topical overlap (T5)")
            continue                                    # no meaningful overlap -> never proposed
        if tier == "T3" and not intent.get("adjacentAllowed", True):
            _drop("adjacent not allowed (T3)")
            continue
        if intent.get("exactMatchRequired") and tier not in ("T0", "T1"):
            _drop("exact match required")
            continue                                    # exact-only search: no siblings AND no adjacent
        F = build_features(intent, prof, c, domain, H, role_conflict)
        d_ab = directional_score(F, dom_cfg, priors)
        d_ba = directional_score(reverse_features(intent, prof, c, domain, H, role_conflict),
                                 dom_cfg, priors)
        rec = reciprocal_score(d_ab, d_ba)
        disc_ok = (d_ab["lcb"] >= float(dom_cfg["discovery_min_lcb"]) and
                   d_ab["coverage"] >= float(dom_cfg["discovery_min_coverage"]))
        if not disc_ok and tier not in ("T0", "T1"):
            _drop("below discovery thresholds")
            continue                                    # weak AND indirect -> drop; direct matches
        #                                                 stay visible as "needs clarification"
        _sem = (F.get("semantic_activity") or (None, 0.0, ""))
        band = (assign_band(d_ab["lcb"], d_ab["coverage"], bands,
                            _sem[1] if _sem[0] == K_MATCH else 0.0)
                if disc_ok else "needs_clarification")
        readiness = readiness_state(c, domain, now_ts, cfg,
                                    received24.get(str(c.get("name", "")).strip().lower(), 0))
        outreach_tier_ok = tier in ("T0", "T1") or (tier == "T2" and bool(intent.get("broadConsent")))
        can_outreach = (outreach_tier_ok and readiness == "open_now" and
                        d_ab["lcb"] >= float(dom_cfg["outreach_min_lcb"]) and
                        d_ab["coverage"] >= float(dom_cfg["outreach_min_coverage"]))
        rs_ru, rs_en, legacy_reasons, gap_ru, gap_en, rkeys = _presentation(F, d_ab, dom_cfg, readiness)
        matched = F["semantic_activity"][2] or ""
        bucket = (H["cat_of"](matched.split(", ")[0])[0] if matched else
                  H["cat_of"]((c.get("interests") or ["x"])[0])[0]) or "other"
        km_txt = F["location_feasibility"][2] if F["location_feasibility"][0] in (K_MATCH, K_MISM) else ""
        km = float(km_txt.split(" ")[0]) if km_txt else c.get("km")
        agree = bool(can_outreach)
        note = ("Agent agreed — " + (legacy_reasons[0] if legacy_reasons else "good fit")) if agree else \
               ("Agent: not reachable now (%s)" % READINESS_LABELS[readiness][1]
                if readiness != "open_now" else
                ("Agent: needs clarification" if band == "needs_clarification" else "Agent: fit too weak"))
        band_ru, band_en = BAND_LABELS[band]
        rdy_ru, rdy_en = READINESS_LABELS[readiness]
        out.append({
            # ---- legacy card contract (buddy/_card + profile UI keep rendering) ----
            "name": c.get("name"), "score": round(d_ab["lcb"] * 100, 1), "tier": tier,
            "kind": TIER_KIND.get(tier, "related"), "km": km, "vibe": c.get("vibe"),
            "open": c.get("open"), "verified": c.get("verified"), "age": c.get("age"),
            "interests": _shared_first(c.get("interests") or [], F), "role": c.get("role"),
            "dealBreakers": c.get("dealBreakers"), "reasons": legacy_reasons or rs_en,
            "agree": agree, "note": note, "bucket": bucket,
            # ---- Matching Core v2 (spec) ----
            "band": band, "band_ru": band_ru, "band_en": band_en,
            "reasons_ru": rs_ru, "reasons_en": rs_en, "reason_keys": rkeys, "gap_ru": gap_ru, "gap_en": gap_en,
            "coverage": d_ab["coverage"], "lcb": d_ab["lcb"], "reciprocal": rec,
            "unknowns": d_ab["unknowns"], "can_outreach": can_outreach,
            "readiness": readiness, "readiness_ru": rdy_ru, "readiness_en": rdy_en,
            "lastActiveDays": c.get("lastActiveDays"),   # allocation tie-break only, never relevance
            "trace": {"tier": tier, "policy": "ALLOW", "domain": domain,
                      "a_to_b": d_ab, "b_to_a": d_ba, "reciprocal": rec,
                      "band": band, "readiness": readiness,
                      "config_version": cfg.get("config_version")},
        })
    # slate order (§11.2): band, readiness class, then provenance tier — a direct match (T0/T1)
    # precedes broader ones (T2/T3) inside a band (§7: expansion never masquerades as direct) —
    # then a reciprocal+directional composite (pure reciprocal is noisy when reverse data is
    # sparse, and allocation must not let that noise reorder quality).
    # Final tie-break: recency of activity (an operational signal, spec §10.2 — never a relevance
    # feature), then a stable name hash. Sorting by name alphabetically gave every slate the same
    # surname bias ("Lopez" always first) and made exposure unfair (§11 fairness), so equal
    # candidates are shuffled deterministically instead — same input, same order, no alphabet.
    tier_rank = {"T0": 0, "T1": 1, "T2": 2, "T3": 3, "T4": 4}
    out.sort(key=lambda x: (BAND_RANK[x["band"]], READINESS_RANK[x["readiness"]],
                            tier_rank.get(x["tier"], 5),
                            -round(0.6 * x["reciprocal"] + 0.4 * x["lcb"], 6),
                            -x["coverage"],
                            min(int(x.get("lastActiveDays") or 9), 9),
                            hashlib.sha1(str(x["name"]).encode("utf-8")).hexdigest()))
    meta = {"core": "v2", "config_version": cfg.get("config_version"), "domain": domain,
            "config_sha": cfg.get("_sha256", "")[:12]}
    home = None                                   # the category the user actually asked about
    for t in topics:
        home = H["cat_of"](t)[0]
        if home:
            break
    sl = _slate(out, home)
    _diversify_reasons(sl)
    return sl, meta
