# -*- coding: utf-8 -*-
"""Kleal — Intent Compiler & clarification policy (spec §5).

Deterministic, LLM-free, keyless. The LLM is a parser only (§5): its output is UNTRUSTED and passes
through this module's schema-validation / allowlists / normalizers / policy checks before it can drive
matching. This layer is ADDITIVE — it never renames or drops a flat intent key the sha-pinned core_v2.py
reads, and it never turns an existing hard BLOCK gate (requiredLanguages / radiusKm / dating datingOk /
verifiedOnly / minAge) into a soft one.

Public surface:
  validate_and_normalize(intent, source) -> (out, report)   §5 intro: untrusted-output hardening
  normalize_for_scoring(intent) -> out                       one idempotent helper for BOTH scoring entries
  extract_constraints(text, intent) -> (out, constraints)    §5.1 hard/soft phrase table (additive)
  intent_summary(intent, constraints) -> dict                §5.1 confirmation rule (data-modelled)
  apply_confirmation(intent, confirmed_ids, constraints) -> out   promote confirmed sensitive constraints
  clarification_policy(intent, constraints, has_results) -> dict  §5.2 P0-P3 + one rule-based question
  minimally_sufficient(intent) -> dict                       §5.3 checklist over the compiled §4 blocks
"""
import re, time
import kleal_contracts as kc

# --------------------------------------------------------------------------- allowlists / clamps
# TYPE allowlist = union of the parser prompt enum + every type core_v2.infer_domain maps, so a valid
# type is never coerced away (which would silently change the domain). Off-list -> deny-safe 'social'.
TYPE_ALLOWLIST = {"dinner", "sport", "gaming", "networking", "dating", "language", "social", "other", "event"}
ROLE_ALLOWLIST = {"play", "watch", "discuss", "practise", "attend", "meet"}
MODE_ALLOWLIST = {"offline", "online"}
RADIUS_MAX_KM, AGE_FLOOR, AGE_CEIL, TOPIC_CAP = 500.0, 18, 120, 4
# §15 MVP band on TOTAL headcount (the asker included), so one above kleal_groups._MAX_MVP_SIZE,
# which counts SEATS. The value is duplicated rather than imported because this module deliberately
# depends on nothing but kc. Not to be confused with core_v2.TOP_N — that is how many people a
# person-to-person search returns, and it stays at 8.
GROUP_SIZE_MIN, GROUP_SIZE_MAX = 2, 13

def _domain_critical(domain, role):
    """§5.3 minimal domain-critical fields, keyed by the ACTUAL core_v2 domain (infer_domain emits
    'sport_activity', not 'sport_play'/'sport_watch') + role."""
    if domain == "games":
        return ["platform", "rank"]
    if domain == "sport_activity":
        return ["skill"] if role == "play" else (["team"] if role == "watch" else [])
    if domain == "language_exchange":
        return ["level"]
    if domain == "professional_networking":
        return ["industry", "goal"]
    if domain == "dating":
        return ["dating_opt_in"]
    return []

# --------------------------------------------------------------------------- §5 intro: normalize
def _clamp_num(v, lo, hi, as_int=False):
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    n = max(lo, min(hi, n))
    return int(n) if as_int else n

def validate_and_normalize(intent, source="llm"):
    """§5 intro (i)-(iv): treat the intent as untrusted output. Completes the 16 flat keys from
    kc._FLAT_DEFAULTS ONLY (never the parser's tightened defaults — no manufactured gates), allowlists
    type/role/mode (off-list -> deny-safe), clamps numerics fail-open, truncates language codes to 2 chars
    (NO name->ISO map — that would flip the directly-set requiredLanguages gate), coerces booleans.
    IDEMPOTENT. Returns (out, report); report lists actions + rejected values (never raises)."""
    out = dict(intent or {})
    report = []
    for k, dv in kc._FLAT_DEFAULTS.items():        # complete contract from the neutral defaults only
        if k not in out:
            out[k] = list(dv) if isinstance(dv, list) else dv

    t = str(out.get("type") or "").strip().lower()
    if t not in TYPE_ALLOWLIST:
        report.append("type %r off-allowlist -> social" % out.get("type"))
        t = "social"
    out["type"] = t
    r = str(out.get("role") or "").strip().lower()
    if r not in ROLE_ALLOWLIST:
        report.append("role %r off-allowlist -> meet" % out.get("role")); r = "meet"
    out["role"] = r
    m = str(out.get("mode") or "").strip().lower()
    if m not in MODE_ALLOWLIST:
        report.append("mode %r off-allowlist -> offline" % out.get("mode")); m = "offline"
    out["mode"] = m

    # topics: lowercase/strip, drop empties, order-preserving dedup, cap 4. NO taxonomy/translation —
    # off-taxonomy interests (labubu / пиво / технику apple) must survive verbatim.
    seen, toks = set(), []
    src = out.get("topics") if isinstance(out.get("topics"), list) else []
    for x in src:
        s = str(x).strip().lower()
        if s and s not in seen:
            seen.add(s); toks.append(s)
    out["topics"] = toks[:TOPIC_CAP]

    out["radiusKm"] = _clamp_num(out.get("radiusKm"), 1.0, RADIUS_MAX_KM) if out.get("radiusKm") is not None else None
    mn = _clamp_num(out.get("minAge"), AGE_FLOOR, AGE_CEIL, as_int=True) if out.get("minAge") is not None else None
    mx = _clamp_num(out.get("maxAge"), AGE_FLOOR, AGE_CEIL, as_int=True) if out.get("maxAge") is not None else None
    if mn is not None and mx is not None and mn > mx:
        report.append("minAge>maxAge -> drop maxAge"); mx = None
    out["minAge"], out["maxAge"] = mn, mx
    # requiredLanguages: 2-char truncation only, dedup, order-preserving. Directly-set gate semantics kept.
    rl = out.get("requiredLanguages")
    if not isinstance(rl, list):
        rl = []
    seen2, langs = set(), []
    for l in rl:
        c = str(l)[:2].lower()
        if c and c not in seen2:
            seen2.add(c); langs.append(c)
    out["requiredLanguages"] = langs
    for b in ("verifiedOnly", "exactMatchRequired", "adjacentAllowed", "broadAllowed"):
        out[b] = bool(out.get(b))

    # groupSize — the §15 routing key, written by an untrusted parser, so coerce and clamp to the MVP
    # band. Absent stays ABSENT (never materialised as None): the key is outside the 16-key contract
    # and every non-group intent must normalise to the bytes it did before groups existed, or every
    # intent_id in the store shifts.
    if "groupSize" in out:
        gs = out.get("groupSize")
        if gs is None or gs == "":
            gs = None
        else:
            try:
                gs = int(float(gs))
            except (TypeError, ValueError):
                report.append("groupSize %r not a number -> dropped" % out.get("groupSize")); gs = None
            else:
                if not (GROUP_SIZE_MIN <= gs <= GROUP_SIZE_MAX):
                    report.append("groupSize %d outside [%d,%d] -> clamped" % (gs, GROUP_SIZE_MIN, GROUP_SIZE_MAX))
                    gs = max(GROUP_SIZE_MIN, min(GROUP_SIZE_MAX, gs))
        if gs is None:
            out.pop("groupSize", None)
        else:
            out["groupSize"] = gs
    if "group" in out and not out.get("group"):
        out.pop("group", None)                     # same reason: a falsy flag must not survive as a key

    errs = kc.validate_intent(out)                 # read-only guard: no key dropped/renamed
    if errs:
        report.append("validate_intent: " + "; ".join(errs))
    return out, report

def normalize_for_scoring(intent):
    """ONE idempotent helper invoked identically at the top of BOTH match_candidates and explain_match, so
    the explain-vs-search PARITY guard holds and intent_id/idempotency keys don't drift across compile sites."""
    return validate_and_normalize(intent or {}, source="structured")[0]

# --------------------------------------------------------------------------- §5.1 hard/soft constraints
_LANG_PHRASE = {"spanish": "es", "espanol": "es", "español": "es", "испанск": "es", "castellano": "es",
                "english": "en", "английск": "en", "catalan": "ca", "català": "ca", "каталон": "ca",
                "french": "fr", "француз": "fr", "german": "de", "немецк": "de", "italian": "it",
                "итальянск": "it", "russian": "ru", "русск": "ru", "portuguese": "pt"}
_ONLY_LANG_RE = re.compile(r"(?:only|just|only in|solo|только(?: по| на| в)?)\s+([a-zа-яёÀ-ɏ]+)", re.I)

def extract_constraints(text, intent, now=None):
    """§5.1: magnet the ORIGINAL free-text query onto ADDITIVE sibling keys (never the 16 gate keys).
    Returns (out, constraints). Each constraint: {id, phrase, kind, field, proposed_value, sensitive,
    excludes_large_share, safety_impact}. No hard gate is created here — sensitive ones are promoted only
    by apply_confirmation() after the user confirms the summary."""
    out = dict(intent or {})
    low = str(text or "").lower()
    cons = []

    # row1 «рядом» -> SOFT location preference (summary-only this iteration; NO radiusKm/mode write)
    if re.search(r"nearby|close by|walking distance|near me|рядом|поблизости|недалеко", low):
        out["preferredNearby"] = True
        out["softLocationBias"] = {"weight": "low"}
        cons.append({"id": "soft_nearby", "phrase": "prefers nearby", "kind": "soft",
                     "field": "preferredNearby", "proposed_value": True,
                     "sensitive": False, "excludes_large_share": False, "safety_impact": 0})

    # row2 «только по-испански» -> required language HARD gate, but only AFTER confirmation
    m = _ONLY_LANG_RE.search(low)
    if m:
        for kw, code in _LANG_PHRASE.items():
            if kw in m.group(1) or m.group(1).startswith(code):
                out["proposedRequiredLanguages"] = [code]
                cons.append({"id": "req_lang", "phrase": "only %s" % code, "kind": "hard_after_confirm",
                             "field": "requiredLanguages", "proposed_value": [code],
                             "sensitive": True, "excludes_large_share": True, "safety_impact": 0})
                break

    # row3 «без токсиков» -> moderation preference + soft domain constraint (surface/log only)
    if re.search(r"no toxic|no drama|chill only|non.?toxic|без токсик|без драм|токсичн|без агресс", low):
        out["moderationPrefs"] = ["no_toxicity"]
        dc = out.get("domainConstraints") if isinstance(out.get("domainConstraints"), dict) else {}
        dc["no_toxicity"] = True
        out["domainConstraints"] = dc
        cons.append({"id": "mod_no_toxic", "phrase": "prefers low-conflict", "kind": "moderation",
                     "field": "moderationPrefs", "proposed_value": ["no_toxicity"],
                     "sensitive": False, "excludes_large_share": False, "safety_impact": 0})

    # row4 «можно онлайн» -> allowed FALLBACK mode (mode stays offline; no silent swap)
    if re.search(r"can do online|open to online|online (?:is )?ok|online too|можно(?: и)? онлайн|онлайн тоже|удал[её]нно", low):
        out["allowOnlineFallback"] = True
        out["allowedModes"] = ["offline", "online"]
        cons.append({"id": "online_fallback", "phrase": "online ok as fallback", "kind": "fallback_mode",
                     "field": "allowOnlineFallback", "proposed_value": True,
                     "sensitive": False, "excludes_large_share": False, "safety_impact": 0})

    # row5 «вторую половинку» -> evergreen dating GOAL + proposed dating mode (type=dating only after confirm)
    if re.search(r"soulmate|second half|long.?term partner|the one|life partner|serious relationship|"
                 r"вторую половинку|вторую половину|серь[её]зны[ех] отношени|спутник жизни|свою любовь", low):
        out["proposedType"] = "dating"
        out["evergreenGoal"] = "dating"
        cons.append({"id": "dating_evergreen", "phrase": "looking for a long-term partner",
                     "kind": "dating_evergreen", "field": "type", "proposed_value": "dating",
                     "sensitive": True, "excludes_large_share": False, "safety_impact": 2})
    return out, cons

def _summary_items(constraints):
    return [c for c in (constraints or [])
            if c.get("sensitive") or c.get("excludes_large_share") or (c.get("safety_impact") or 0) > 0]

def intent_summary(intent, constraints):
    """§5.1 confirmation rule (data-modelled — there is no interactive loop). Any constraint that excludes a
    large share, reveals sensitive preferences, or affects safety is listed in constraints_to_confirm and
    the summary requires_confirmation. may_empty_pool_warning flags a pending hard constraint that could
    legitimately empty the eligible pool (§12 never-dead-end)."""
    intent = intent or {}
    done = set((intent.get("_confirmed") or {}).get("ids") or [])   # already-confirmed -> no longer pending
    items = [c for c in _summary_items(constraints) if c.get("id") not in done]
    soft = [c["phrase"] for c in (constraints or []) if c.get("kind") in ("soft", "moderation", "fallback_mode")]
    evergreen = [c["phrase"] for c in (constraints or []) if c.get("kind") == "dating_evergreen"]
    pending_hard = any(c.get("kind") == "hard_after_confirm" and c.get("id") not in done for c in (constraints or []))
    return {
        "intent_id": (intent.get("identity") or {}).get("intent_id"),
        "headline": intent.get("title") or (", ".join(intent.get("topics") or []) or "a meetup"),
        "domain": (intent.get("identity") or {}).get("domain"),
        "mode": intent.get("mode"), "topics": intent.get("topics"),
        "time": intent.get("time"), "place": intent.get("place"),
        "disclosure": (intent.get("disclosure") or {}).get("stage_map"),
        "soft_preferences": soft, "evergreen_goals": evergreen,
        "constraints_to_confirm": items, "requires_confirmation": bool(items),
        "may_empty_pool_warning": bool(pending_hard),
    }

def apply_confirmation(intent, confirmed_ids, constraints, now=None):
    """Promote ONLY the confirmed sensitive constraints. requiredLanguages keeps 2-char truncation
    semantics; proposedType='dating' -> type='dating' with NO age/verification side effects. Unconfirmed
    sensitive constraints stay soft/absent (never a silent hard gate). Stamps §4.2 level-2 provenance."""
    out = dict(intent or {})
    confirmed = set(confirmed_ids or [])
    promoted = []
    for c in (constraints or []):
        if c.get("id") not in confirmed:
            continue
        if c.get("kind") == "hard_after_confirm" and c.get("field") == "requiredLanguages":
            out["requiredLanguages"] = [str(x)[:2].lower() for x in (c.get("proposed_value") or [])]
            promoted.append(c["id"])
        elif c.get("kind") == "dating_evergreen":
            out["type"] = "dating"                 # promote proposed dating mode; no verifiedOnly/minAge side effects
            # §17.1 consent — a structured record of the explicit dating opt-in + any confirmed target preferences
            # (appears ONLY once the dating_opt_in constraint is confirmed; never inferred).
            out["dating_consent"] = {"opt_in": True, "target_prefs": dict(c.get("target_prefs") or {}),
                                     "at": kc._iso(now if now is not None else time.time())}
            promoted.append(c["id"])
        elif c.get("kind") == "outreach_consent":  # ONLY an explicit outreach-broadening consent flips this
            out["broadConsent"] = True
            promoted.append(c["id"])
    out["_confirmed"] = {"ids": promoted, "at": kc._iso(now if now is not None else time.time()),
                         "source": "user_confirmed_intent_summary"}
    return out

# --------------------------------------------------------------------------- §5.3 minimally sufficient
def minimally_sufficient(intent):
    """§5.3 checklist over the ALREADY-COMPILED §4 blocks. Verification-only (does not stamp). TTL+search
    budget are already provided by kc.compile_intent lifecycle (§4)."""
    intent = intent or {}
    ident = intent.get("identity") or {}
    goal = intent.get("goal") or {}
    mf = intent.get("mode_format") or {}
    loc = intent.get("location_block") or {}
    fb = intent.get("fallback") or {}
    disc = intent.get("disclosure") or {}
    lc = intent.get("lifecycle") or {}
    domain, role = ident.get("domain"), intent.get("role")
    checks = {
        "domain_activity_purpose": bool(ident.get("domain") and goal.get("activity") is not None and goal.get("purpose")),
        "time_horizon": bool(intent.get("time")),                        # 'Flexible' = explicit no-time (valid)
        "mode_format": bool(mf.get("mode") and mf.get("format")),
        "location_or_online_fallback": bool(loc.get("city") or intent.get("allowOnlineFallback") or intent.get("mode") == "online"),
        "domain_critical": all(intent.get(f) is not None or (intent.get("domain_details") or {}).get(f) is not None
                               for f in _domain_critical(domain, role)),
        "fallback_and_disclosure": bool(fb.get("allowed_dimensions") is not None and disc.get("stage_map")),
        "ttl_and_budget": bool(lc.get("ttl_seconds") and lc.get("search_budget")),
    }
    missing = [k for k, ok in checks.items() if not ok]
    return {"ok": not missing, "missing": missing, "present": [k for k, ok in checks.items() if ok]}

# --------------------------------------------------------------------------- §5.2 clarification policy
_CLASS_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

def _gap(ref, cls, question, refuse, safety, pool, supply, control, friction):
    return {"ref": ref, "cls": cls, "question": question, "refuse_action": refuse,
            "factors": {"safety_impact": safety, "candidate_pool_split": pool,
                        "supply_unlock": supply, "user_control": control},
            "friction": friction}

def _detect_gaps(intent, constraints):
    intent = intent or {}
    ident = intent.get("identity") or {}
    domain, role = ident.get("domain"), intent.get("role")
    gaps = []
    ids = {c.get("id") for c in (constraints or [])}
    # --- P0 mandatory (safety / eligibility-blocking) ---
    if intent.get("proposedType") == "dating" and intent.get("type") != "dating":
        gaps.append(_gap("dating_opt_in", "P0", "Are you looking for dating specifically?",
                         "stay in friendship/social discovery (do not set type=dating)", 2, 2, 1, 2, 1))
    if domain == "games" and not (intent.get("platform") or (intent.get("domain_details") or {}).get("platform")):
        gaps.append(_gap("platform_crossplay", "P0", "Which platform do you play on (and is crossplay ok)?",
                         "search without a crossplay assumption and flag it", 0, 2, 2, 1, 1))
    if intent.get("proposedRequiredLanguages") and not intent.get("requiredLanguages"):
        gaps.append(_gap("required_language", "P0", "Do you need someone who speaks only that language?",
                         "do not apply the language hard gate; search broader", 0, 2, 0, 2, 1))
    # --- P1 high value (>30% pool / opens a tier) ---
    if not intent.get("time") or str(intent.get("time")).lower() == "flexible":
        gaps.append(_gap("time_horizon", "P1", "When would you like to meet — today, this week, flexible?",
                         "search with time unknown + lower confidence (no hidden default)", 0, 2, 1, 1, 1))
    if not ((intent.get("location_block") or {}).get("city") or intent.get("allowOnlineFallback") or intent.get("mode") == "online"):
        gaps.append(_gap("location", "P1", "Which area works, or is online ok?",
                         "search with location unknown; do not inject a restrictive radius", 0, 2, 1, 1, 1))
    if not (intent.get("mode_format") or {}).get("format"):
        gaps.append(_gap("format", "P1", "One-on-one or a small group?",
                         "search with format unknown + lower confidence", 0, 1, 1, 2, 1))
    if domain == "language_exchange" and not (intent.get("level") or (intent.get("domain_details") or {}).get("level")):
        gaps.append(_gap("language_level", "P1", "Native speaker or same-level practice partner?",
                         "search with level unknown + lower confidence", 0, 2, 1, 1, 1))
    # --- P2 ranking-only ---
    for f in _domain_critical(domain, role):
        if f in ("skill", "team", "rank") and not (intent.get(f) or (intent.get("domain_details") or {}).get(f)):
            gaps.append(_gap("detail_" + f, "P2", "Any preference on %s?" % f,
                             "do not ask before first results (offer as a post-results refinement)", 0, 0, 1, 1, 1))
    # --- P3 cosmetic ---
    if not intent.get("title"):
        gaps.append(_gap("card_title", "P3", None, "do not ask", 0, 0, 0, 0, 2))
    return gaps

def _is_mandatory_safety(gap):
    """B1: only a mandatory-SAFETY gap may be asked before first results — NOT every P0 (platform /
    required-language are eligibility, not safety, and must defer)."""
    return (gap.get("factors", {}).get("safety_impact") == 2) or gap.get("ref") == "dating_opt_in"

def clarification_policy(intent, constraints=None, has_results=None):
    """§5.2: detect P0-P3 gaps, pick AT MOST ONE question rule-based (no EVI formula) over four ordinal
    factors minus friction, and enforce 'no question before first results except mandatory safety'."""
    gaps = _detect_gaps(intent, constraints)
    if not gaps:
        return {"gaps": [], "question": None, "deferred": False, "top": None,
                "before_results_rule": "no gaps"}
    def _key(g):
        f = g["factors"]
        return (_CLASS_RANK.get(g["cls"], 9),
                -f["safety_impact"], -f["candidate_pool_split"], -f["supply_unlock"], -f["user_control"],
                g["friction"])
    gaps_sorted = sorted(gaps, key=_key)
    top = gaps_sorted[0]
    question, deferred = top.get("question"), False
    if top["cls"] == "P3" or question is None:                       # cosmetic never asked
        question, deferred = None, True
    elif not has_results and not _is_mandatory_safety(top):          # B1 pre-results safety predicate
        question, deferred = None, True
    return {"gaps": gaps_sorted, "top": {"ref": top["ref"], "cls": top["cls"]},
            "question": question, "deferred": deferred,
            "before_results_rule": "asked (mandatory safety)" if (question and not has_results) else
                                   ("deferred until first results" if deferred and top["cls"] != "P3" else "asked")}
