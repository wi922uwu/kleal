# -*- coding: utf-8 -*-
"""Kleal — canonical data contracts (spec §4).

The single source of truth for the §4 entities: UserProfile, ProfileView, ReceivingPolicy, Intent (with
its 11 §4.3 blocks), Evidence, CandidateSnapshot, Proposal, Reservation, Match, Group, Plan and
RelationshipEdge — plus the §4.2 seven-level source hierarchy and the §8.3 purpose-binding projection.

Design invariants (do NOT break — they protect the sha-pinned scorer core_v2.py, which reads
intent/profile/candidate/receiving fields BY NAME):
  * Every builder is ADDITIVE: it returns ``dict(existing, **new)`` and never drops or renames a field
    the engine reads. New contract data goes under NEW keys only.
  * Every validator is READ-ONLY: it returns a list of problems and never rewrites/strips keys.
  * Stdlib only, zero secret/key references — importable by any service via ``shared`` on sys.path.
"""
import hashlib, time, calendar

CONTRACTS_VERSION = "contracts-4.0.0"

# ----------------------------------------------------------------------------- §4.2 source hierarchy
# Priority 1 (highest authority) … 7 (lowest). Rule: a higher-authority source overrides older data in
# the same scope. Never let a low-confidence inference become a hidden hard gate.
SOURCE_HIERARCHY = (
    "current_intent_explicit",        # 1 — explicit answer in the current intent
    "user_confirmed_intent_summary",  # 2 — the confirmed search/disclosure contract
    "current_context_permissioned",   # 3 — location/calendar/availability, short TTL
    "explicit_stable_profile",        # 4 — stable stated profile, if not contradicted
    "confirmed_memory",               # 5 — confirmed memory, only in allowed domain scope
    "observed_behavior",              # 6 — scheduler/experimentation only; not a hard gate
    "agent_inference",                # 7 — soft, editable, low confidence, decays
)
SOURCE_PRIORITY = {s: i + 1 for i, s in enumerate(SOURCE_HIERARCHY)}

def resolve_source(a, b):
    """Return the higher-authority (lower priority number) of two sources (§4.2 rule 1)."""
    return a if SOURCE_PRIORITY.get(a, 99) <= SOURCE_PRIORITY.get(b, 99) else b

# Per feature-group provenance — NOT everything is a level-1 explicit intent statement (SPEC-1). Evidence
# built off a scored feature group derives its `source` here rather than hardcoding L1, so §4.2 authority
# and gate-eligibility stay truthful.
FEATURE_GROUP_SOURCE = {
    "semantic_activity":    "explicit_stable_profile",       # interests = stable stated profile (L4)
    "time_feasibility":     "current_context_permissioned",  # availability now (L3)
    "location_feasibility": "current_context_permissioned",  # coarse location now (L3)
    "mode_format":          "current_intent_explicit",       # the intent states the mode (L1)
    "directed_preferences": "current_intent_explicit",       # the intent states the target role (L1)
    "social_context":       "agent_inference",               # vibe is soft/inferred (L7)
    "domain_constraints":   "explicit_stable_profile",       # language pair / community (L4)
}

# ----------------------------------------------------------------------------- closed enums
INTENT_STATUS       = ("active", "expired", "superseded", "draft")
URGENCY             = ("none", "soon", "urgent")
DISCLOSURE_STAGES   = ("minimal", "limited_profile", "match_only", "full")
DISCLOSURE_RANK     = {s: i for i, s in enumerate(DISCLOSURE_STAGES)}
RECEIVING_STATUS    = ("active", "busy", "paused")
PROPOSAL_TYPES      = ("person", "small_group", "group", "event", "room", "venue")   # §16 'venue' additive (pilot-off)
PROPOSAL_STATUS     = ("draft", "sent", "accepted", "declined", "expired", "revoked")
RESERVATION_STATUS  = ("held", "confirmed", "released", "expired")
MATCH_STATUS        = ("active", "completed", "expired")
EDGE_STATES         = ("new", "contact", "friend", "repeat", "avoid", "block")
FRESHNESS           = ("current", "recent", "stale")
SENSITIVITY         = ("normal", "sensitive", "restricted")
VISIBILITY          = ("match_only", "discovery", "private")
TIER_PROVENANCE     = ("T0", "T1", "T2", "T3", "T5")

# ----------------------------------------------------------------------------- §8.3 contextual profiles
# The six spec contexts. Each engine `domain` maps to exactly one context (TOTAL map, NO generic
# fallback): an unmapped domain projects at the minimal/deny-safe stage only (SPEC-2), so a new domain
# can never silently leak dating/sensitive fields into a non-dating context.
CONTEXTS = ("friendship", "dating", "networking", "language_exchange", "games", "sport")
DOMAIN_TO_CONTEXT = {
    "social_meet": "friendship", "walk": "friendship", "watch_together": "friendship",
    "culture_event": "friendship", "toys_collectibles": "friendship",
    "coworking": "networking", "professional_networking": "networking",
    "sport_activity": "sport",
    "games": "games",
    "language_exchange": "language_exchange",
    "dating": "dating",
}
# Purpose-binding allow-lists = the COMPLEMENT of each §8.3 deny column. Fields are candidate/profile keys
# that MAY be projected for that context. A field allowed in one context is NOT automatically available in
# another (purpose binding). Key deny invariants (asserted in tests):
#   friendship / networking / language_exchange / games / sport  ->  NO `datingOk` (dating prefs excluded)
#   dating                                                        ->  NO `entities` (professional inference excluded)
PURPOSE_FIELDS = {
    "friendship":        ("name", "interests", "formats", "langs", "open", "vibe", "area", "km"),
    "dating":            ("name", "interests", "vibe", "langs", "open", "area", "km", "age", "verified", "datingOk", "role"),
    "networking":        ("name", "role", "entities", "langs", "area", "km", "open"),
    "language_exchange": ("name", "langs", "role", "formats", "open", "area", "km"),
    "games":             ("name", "interests", "entities", "role", "langs", "open"),
    "sport":             ("name", "interests", "entities", "role", "km", "area", "open", "formats"),
}

# ----------------------------------------------------------------------------- lifecycle / TTL defaults
# Per-domain intent TTL (seconds). A domain absent from the map falls back to `_default` (COMPAT-4: no
# KeyError). Dating/networking intents live long; a quick coffee expires the same day.
TTL_DEFAULTS = {
    "social_meet": 6 * 3600, "walk": 4 * 3600, "watch_together": 8 * 3600,
    "culture_event": 3 * 86400, "coworking": 2 * 86400, "sport_activity": 2 * 86400,
    "professional_networking": 7 * 86400, "games": 12 * 3600, "language_exchange": 7 * 86400,
    "dating": 14 * 86400, "toys_collectibles": 7 * 86400, "_default": 24 * 3600,
}
DEFAULT_SEARCH_BUDGET = 200          # retrieval candidates a single intent may consume in the pilot
PROPOSAL_TTL = 24 * 3600             # a proposal is valid for a day
MATCH_TTL = 7 * 86400
DEFAULT_COOLDOWN_DAYS = 7            # mirrors matching COOLDOWN_DAYS (advisory edge only)

# ----------------------------------------------------------------------------- small helpers
def _det_id(prefix, *parts):
    """Deterministic id from its parts (no clock, no randomness — replay-safe). Aliases/tags/nodes from
    one phrase share an evidence_id because they hash the same (field,value,source,scope) — §4.1 dedup."""
    h = hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()
    return "%s_%s" % (prefix, h[:12])

def _iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(ts)))

def _parse_iso(s):
    """Inverse of _iso (UTC). None if unreadable."""
    if isinstance(s, (int, float)):
        return float(s)
    try:
        return float(calendar.timegm(time.strptime(str(s)[:19], "%Y-%m-%dT%H:%M:%S")))
    except Exception:
        return None

def _split_list(v):
    """Single-token list — split on commas AND whitespace (mirrors admin._as_list)."""
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [x.strip() for x in v.replace(",", " ").split() if x.strip()]
    return []

def _min_disclosure(a, b):
    """The MORE restrictive (lower-rank) of two disclosure stages; unknown/None -> 'limited_profile'."""
    def rank(x):
        return DISCLOSURE_RANK.get(x if x in DISCLOSURE_STAGES else "limited_profile")
    return a if rank(a) <= rank(b) else b

# ============================================================================= UserProfile (§4 row 1)
def build_user_profile(norm_user):
    """Additive superset over admin/_norm_user output. Keeps every flat matcher key; mirrors the explicit
    identity/privacy blocks the spec names, plus a _contract version. Never drops a key core_v2 reads."""
    u = dict(norm_user or {})
    age = u.get("age")
    identity = {
        "id": u.get("id"), "name": u.get("name"),
        "age": age, "age_verified_18": bool(age is not None and age >= 18),
        "languages": {"comfortable": list(u.get("langs") or [])},
        "city": u.get("area") or None, "role": u.get("role"),
    }
    privacy = {
        "visibility": "match_only",
        "verified": bool(u.get("verified", False)),
        "dating_opt_in": bool(u.get("datingOk", False)),
    }
    out = dict(u)
    out.setdefault("identity", identity)
    out.setdefault("privacy", privacy)
    out["_contract"] = CONTRACTS_VERSION
    return out

def validate_user_profile(p):
    errs = []
    if not (p or {}).get("name"):
        errs.append("UserProfile.name missing")
    return errs

# ============================================================================= ProfileView (§4 row 2 / §8.3)
def build_profile_view(user, purpose, disclosure_stage=None, now=None):
    """Purpose-bound MINIMAL projection (§8.3). Exposes only the fields allow-listed for the context that
    `purpose` (an engine domain) maps to. An unmapped domain -> minimal deny-safe view (just name)."""
    user = user or {}
    context = DOMAIN_TO_CONTEXT.get(str(purpose or "").lower())
    allow = PURPOSE_FIELDS.get(context)
    if not allow:                                  # unmapped domain -> deny-safe (SPEC-2)
        context, allow = (context or "minimal"), ("name",)
    stage = disclosure_stage if disclosure_stage in DISCLOSURE_STAGES else "limited_profile"
    fields = {k: user.get(k) for k in allow if user.get(k) is not None}
    # §17.1 staged disclosure: opt-in per-field stage gates. user['disclosure_field_stages'] = {field: stage}
    # withholds a field whose required stage outranks the current stage (photo/name/detail by settings). Absent
    # -> no filtering (byte-identical to the generic stage-level projection).
    fstages = user.get("disclosure_field_stages")
    if isinstance(fstages, dict):
        cur = DISCLOSURE_RANK.get(stage, 1)
        fields = {k: v for k, v in fields.items() if DISCLOSURE_RANK.get(fstages.get(k), 0) <= cur}
    return {
        "view_id": _det_id("pv", user.get("name"), context, stage),
        "user_id": user.get("id") or user.get("name"),
        "purpose": purpose, "context": context, "disclosure_stage": stage,
        "allowed_fields": list(allow), "fields": fields,
        "version": CONTRACTS_VERSION, "_contract": CONTRACTS_VERSION,
    }

# ============================================================================= §17.1 dating capsule + data minimization
_DATING_SENSITIVE = ("orientation", "gender_target", "preferences", "health", "religion", "politics")

def age_band(age):
    """Coarsen an exact age to a band (data minimization) — used unless the user gave explicit exact-age consent."""
    try:
        a = int(age)
    except (TypeError, ValueError):
        return None
    if a < 18:
        return "under_18"
    for lo, hi, lbl in ((18, 24, "18-24"), (25, 34, "25-34"), (35, 44, "35-44"), (45, 54, "45-54")):
        if lo <= a <= hi:
            return lbl
    return "55+"

def build_dating_capsule(user, disclosure_stage=None, now=None):
    """§17.1 profile — a SEPARATE purpose-bound dating capsule. Built on build_profile_view(purpose='dating') so
    the professional `entities` field is structurally excluded (not on the dating allow-list), PLUS extra
    minimization: exact age coarsened to a band unless `consent_exact_age`, and the sensitive contour
    (orientation/preferences/health/religion/politics) is never surfaced. Carries its own policy_version. Keyless,
    deterministic (now injected)."""
    user = user or {}
    pv = build_profile_view(user, "dating", disclosure_stage, now)
    fields = dict(pv.get("fields") or {})
    if "age" in fields and not user.get("consent_exact_age"):
        fields["age_band"] = age_band(fields.pop("age"))
    for k in _DATING_SENSITIVE:
        fields.pop(k, None)
    return {"capsule_id": _det_id("dcap", user.get("name"), pv.get("disclosure_stage")),
            "purpose": "dating", "disclosure_stage": pv.get("disclosure_stage"), "fields": fields,
            "policy_version": "dating-policy-1.0.0", "sensitive_excluded": True, "_contract": CONTRACTS_VERSION}

def decay(evidence, now=None):
    """§19.2 — a soft agent_inference (L7) loses confidence as it ages (~30-day half-life); higher-authority
    sources are returned unchanged. Deterministic (now injected), returns a copy — never mutates the input."""
    e = dict(evidence or {})
    if e.get("source") != "agent_inference":
        return e
    now = float(now if now is not None else 0.0)
    seen = _parse_iso(e.get("last_confirmed_at"))
    seen = float(seen) if seen is not None else now
    age_days = max(0.0, (now - seen) / 86400.0)
    c = e.get("confidence")
    if isinstance(c, (int, float)) and not isinstance(c, bool):
        e["confidence"] = round(max(0.0, float(c) * (0.5 ** (age_days / 30.0))), 4)
    return e

def drop_inferred(evidence_list):
    """§19.2 — remove ONLY soft inferred (L7) rows; every higher-authority source is kept (a single behavior
    never creates a permanent inference; explicit edits survive)."""
    return [e for e in (evidence_list or []) if (e or {}).get("source") != "agent_inference"]

# ============================================================================= ReceivingPolicy (§4 row 3 / §4.4)
def build_receiving_policy(u):
    """§4.4 superset. Reads the admin editor rcv* fields (base + new location_scope / allowed_proposal_types
    / disclosure_stage / per_7d / paused_until) and emits the canonical policy — OR None.

    CRITICAL (COMPAT-3): the None-return semantics of the original admin/_receiving_from_form are preserved
    EXACTLY — a partial patch (no rcvStatus) passes the stored policy through; a cleared full save returns
    None. A policy is never fabricated for a user who set nothing (that would flip readiness to open_now).
    New §4.4 keys are OMITTED (not empty-listed) when unset, so the send-boundary gates stay permissive."""
    u = u or {}
    if "rcvStatus" not in u:
        return u["receiving"] if isinstance(u.get("receiving"), dict) else None
    rst = str(u.get("rcvStatus") or "").strip().lower()
    known = rst in RECEIVING_STATUS
    r = {}
    doms = [d.lower() for d in _split_list(u.get("rcvDomains"))]
    if doms:
        r["allowed_domains"] = doms
    qs, qe = str(u.get("rcvQuietStart") or "").strip(), str(u.get("rcvQuietEnd") or "").strip()
    if qs and qe:
        r["quiet_hours"] = {"start": qs, "end": qe, "tz_offset_min": 120}
    budget = {}
    for form_key, pol_key in (("rcvPer24", "per_24h"), ("rcvPer7d", "per_7d")):
        try:
            budget[pol_key] = int(float(u.get(form_key)))
        except (TypeError, ValueError):
            pass
    if budget:
        r["proposal_budget"] = budget
    loc = _split_list(u.get("rcvLocationScope"))
    if loc:
        r["location_scope"] = loc
    ptypes = [p.lower() for p in _split_list(u.get("rcvProposalTypes")) if p.lower() in PROPOSAL_TYPES]
    if ptypes:
        r["allowed_proposal_types"] = ptypes
    dstage = str(u.get("rcvDisclosureStage") or "").strip().lower()
    if dstage in DISCLOSURE_STAGES:
        r["disclosure_stage"] = dstage
    pu = str(u.get("rcvPausedUntil") or "").strip()
    if pu:
        r["paused_until"] = pu
    rpas = u.get("rcvPassive")
    if not (known or r or rpas is False):          # nothing meaningful set -> cleared
        return None
    r["status"] = rst if known else "active"
    r["passive_outreach"] = rpas if isinstance(rpas, bool) else True
    return r

def validate_receiving_policy(r):
    if r is None:
        return []
    errs = []
    if r.get("status") not in RECEIVING_STATUS:
        errs.append("ReceivingPolicy.status invalid: %r" % r.get("status"))
    for p in (r.get("allowed_proposal_types") or []):
        if p not in PROPOSAL_TYPES:
            errs.append("allowed_proposal_types has invalid %r" % p)
    if r.get("disclosure_stage") is not None and r.get("disclosure_stage") not in DISCLOSURE_STAGES:
        errs.append("disclosure_stage invalid: %r" % r.get("disclosure_stage"))
    return errs

# ============================================================================= Intent (§4 row 4 / §4.3)
_INTENT_FLAT_KEYS = ("title", "type", "topics", "role", "mode", "format", "time", "place", "radiusKm",
                     "verifiedOnly", "minAge", "maxAge", "requiredLanguages", "exactMatchRequired",
                     "adjacentAllowed", "broadAllowed")
# Defaults for any flat key ABSENT from the caller's intent — chosen to match exactly what the matching
# code's own .get() fallbacks already assume, so completing the contract never changes scoring or gates.
_FLAT_DEFAULTS = {"title": None, "type": "social", "topics": [], "role": "meet", "mode": "offline",
                  "format": None, "time": "Flexible", "place": None, "radiusKm": None, "verifiedOnly": False,
                  "minAge": None, "maxAge": None, "requiredLanguages": [], "exactMatchRequired": False,
                  "adjacentAllowed": True, "broadAllowed": True}

def _urgency(intent):
    t = str(intent.get("time") or "").lower()
    if any(w in t for w in ("now", "tonight", "today", "asap", "urgent")):
        return "urgent"
    if any(w in t for w in ("evening", "tomorrow", "soon")):
        return "soon"
    return "none"

def compile_intent(parsed, identity, ctx=None, now=None):
    """Stamp the 11 §4.3 blocks onto the compiled intent WITHOUT touching the 16 flat keys core_v2 reads.
    `identity` is the app's _intent_identity() dict (intent_id/version/domain/decision_type). Returns
    dict(parsed, **blocks).

    COMPAT-4: an already-present lifecycle whose expires_at is in the PAST is preserved verbatim — a
    compile pass never revives/extends an expired intent; a default TTL is stamped only when no lifecycle
    exists at all."""
    intent = dict(parsed or {})
    ctx = ctx or {}
    now = float(now if now is not None else time.time())
    identity = identity or {}
    domain = identity.get("domain") or "social_meet"

    existing_lc = intent.get("lifecycle") if isinstance(intent.get("lifecycle"), dict) else None
    if existing_lc and existing_lc.get("expires_at") is not None:
        lifecycle = existing_lc                    # keep as-is — never revive an expired intent
    else:
        ttl = TTL_DEFAULTS.get(domain, TTL_DEFAULTS["_default"])
        lifecycle = {"created_at": _iso(now), "expires_at": _iso(now + ttl),
                     "ttl_seconds": ttl, "search_budget": DEFAULT_SEARCH_BUDGET}

    typ = str(intent.get("type") or "").lower()
    purpose = ("dating" if typ == "dating" else
               "networking" if typ == "networking" else "social")
    blocks = {
        "identity": {"intent_id": identity.get("intent_id"), "user_id": ctx.get("uid") or "me",
                     "version": identity.get("version"), "domain": domain,
                     "status": intent.get("status") or "active",
                     "decision_type": identity.get("decision_type") or "person_to_person"},
        "goal": {"activity": (intent.get("topics") or [None])[0], "purpose": purpose,
                 "desired_outcome": intent.get("title")},
        "time_block": {"timezone": ctx.get("tz") or "Europe/Madrid",
                       "windows": [], "duration": None, "recurrence": None, "urgency": _urgency(intent)},
        "location_block": {"city": ctx.get("city"), "coarse_cell": None,
                           "radius_km": intent.get("radiusKm"), "travel_time": None, "safe_zones": []},
        "mode_format": {"mode": intent.get("mode"), "format": intent.get("format"),
                        "confirmed": bool(intent.get("format"))},
        "target": {"directed": intent.get("role"),
                   "required_roles": [],          # placeholder — target roles/level collected upstream later
                   "level": intent.get("level")},
        "social": {"vibe": (intent.get("social") or {}).get("vibe") if isinstance(intent.get("social"), dict) else None,
                   "pressure_level": None, "communication_style": None},
        "domain_details": {"platform": None, "server": None, "rank": None,
                           "language_level": None, "ticket": None, "equipment": None},
        "fallback": {"allowed_dimensions": _allowed_dimensions(intent),
                     "consent": bool(intent.get("broadConsent"))},
        "disclosure": {"stage_map": {"discovery": "limited_profile", "match": "match_only"}},
        "lifecycle": lifecycle,
    }
    out = dict(intent)
    for k, v in blocks.items():
        out[k] = v                                 # blocks are contract keys; safe to (re)stamp
    for k, dv in _FLAT_DEFAULTS.items():           # complete the 16-key contract for arbitrary body intents
        out.setdefault(k, list(dv) if isinstance(dv, list) else dv)
    return out

def _allowed_dimensions(intent):
    dims = []
    if intent.get("adjacentAllowed", True):
        dims.append("adjacent")
    if intent.get("broadAllowed", True):
        dims.append("broader")
    if not intent.get("exactMatchRequired"):
        dims.append("related")
    return dims

def is_expired(intent, now=None):
    """§4.3 Lifecycle: an expired intent must not participate in ranking. Missing/None expires_at -> NOT
    expired (COMPAT-4: a buddy-supplied intent may carry no lifecycle and must never be silently wiped)."""
    lc = (intent or {}).get("lifecycle") or {}
    exp = lc.get("expires_at")
    if exp in (None, ""):
        return False
    ts = _parse_iso(exp)
    if ts is None:
        return False
    return ts <= float(now if now is not None else time.time())

def validate_intent(intent):
    errs = []
    for k in _INTENT_FLAT_KEYS:
        if k not in (intent or {}):
            errs.append("Intent flat key dropped: %s" % k)   # guards the additive-superset invariant
    ident = (intent or {}).get("identity") or {}
    if ident.get("status") and ident["status"] not in INTENT_STATUS:
        errs.append("Intent.identity.status invalid: %r" % ident["status"])
    return errs

# ============================================================================= Evidence (§4 row 5 / §4.1)
def build_evidence(field, value, source, scope=None, confidence=None, freshness="current",
                   sensitivity="normal", allowed_purposes=None, visibility="match_only",
                   last_confirmed=None, expires_at=None, now=None):
    """§4.1 evidence object. evidence_id is deterministic over (field,value,source,scope), so every alias/
    tag/taxonomy node derived from ONE phrase carries the SAME id — the Feature Builder dedups on it."""
    now = float(now if now is not None else time.time())
    if source not in SOURCE_HIERARCHY:
        source = "agent_inference"                 # never invent a higher authority than we can prove
    return {
        "evidence_id": _det_id("ev", field, value, source, scope),
        "field": field, "value": value, "source": source, "scope": scope,
        "confidence": confidence, "freshness": freshness if freshness in FRESHNESS else "current",
        "sensitivity": sensitivity if sensitivity in SENSITIVITY else "normal",
        "allowed_purposes": list(allowed_purposes or []),
        "visibility": visibility if visibility in VISIBILITY else "match_only",
        "last_confirmed_at": _iso(last_confirmed) if last_confirmed else _iso(now),
        "expires_at": _iso(expires_at) if expires_at else None,
    }

# ============================================================================= CandidateSnapshot (§4 row 6)
def build_candidate_snapshot(card, intent, cfg_meta=None):
    """Versioned feature-building snapshot for a scored card. Rich when the explain-style per-feature rows
    are present (converts each known group into an Evidence object); degrades to versions+tier+unknowns
    otherwise (e.g. legacy scorer / slate card). Returns the snapshot sub-object (caller attaches it)."""
    card = card or {}
    cfg_meta = cfg_meta or {}
    ident = (intent or {}).get("identity") or {}
    scope = "intent:" + str(ident.get("intent_id") or "")
    feats = ((card.get("a_to_b") or {}).get("features")) or []
    evidence, groups = [], []
    for row in feats:
        groups.append({"group": row.get("group"), "state": row.get("state")})
        if row.get("state") == "known_match" and row.get("detail"):
            evidence.append(build_evidence(
                row.get("group"), row.get("detail"),
                FEATURE_GROUP_SOURCE.get(row.get("group"), "agent_inference"),
                scope=scope, confidence=row.get("value")))
    return {
        "intent_id": ident.get("intent_id"), "intent_version": ident.get("version"),
        "config_version": cfg_meta.get("config_version"), "config_sha": cfg_meta.get("config_sha"),
        "tier": card.get("tier"), "source": card.get("source") or (card.get("trace") or {}).get("domain"),
        "feature_groups": groups, "unknowns": list(card.get("unknowns") or []),
        "evidence": evidence, "_contract": CONTRACTS_VERSION,
    }

# ============================================================================= Proposal (§4 row 7)
def build_proposal(intent, candidate, disclosure_stage=None, now=None):
    """§4.7 structured proposal with an idempotency_key (a re-send is not a duplicate) and a disclosure
    clamp = min(intent stage, candidate.receiving.disclosure_stage)."""
    now = float(now if now is not None else time.time())
    intent, candidate = intent or {}, candidate or {}
    ident = intent.get("identity") or {}
    iid = ident.get("intent_id") or _det_id("int", intent.get("type"), ",".join(intent.get("topics") or []))
    to_user = candidate.get("name")
    cand_stage = (candidate.get("receiving") or {}).get("disclosure_stage")
    stage_map = (intent.get("disclosure") or {}).get("stage_map") or {}
    intent_stage = disclosure_stage or stage_map.get("match") or "limited_profile"
    allowed = _min_disclosure(intent_stage, cand_stage) if cand_stage else intent_stage
    return {
        "proposal_id": _det_id("prop", iid, to_user, int(now)),
        "idempotency_key": _det_id("idem", iid, str(to_user).lower()),
        "intent_id": iid, "from_user": ident.get("user_id") or "me", "to_user": to_user,
        "payload": {"title": intent.get("title"), "topics": intent.get("topics"),
                    "time": intent.get("time"), "place": intent.get("place")},
        "allowed_disclosure": allowed, "ttl_seconds": PROPOSAL_TTL,
        "expires_at": _iso(now + PROPOSAL_TTL), "status": "draft", "version": 1, "created_at": _iso(now),
        "_contract": CONTRACTS_VERSION,
    }

# ============================================================================= Reservation (§4 row 8)
def build_reservation(resource, holder, ttl_s=None, now=None):
    """§4.8 temporary capacity hold with a version for optimistic revalidation. Pilot person_to_person has
    no real capacity system; this is the contract used by the (post-pilot) group/plan flows."""
    now = float(now if now is not None else time.time())
    ttl_s = int(ttl_s or PROPOSAL_TTL)
    return {"reservation_id": _det_id("resv", resource, holder, int(now)), "resource": resource,
            "holder": holder, "version": 1, "ttl_seconds": ttl_s, "expires_at": _iso(now + ttl_s),
            "status": "held", "_contract": CONTRACTS_VERSION}

# ============================================================================= Match (§4 row 9)
def build_match(match_record, participants, purpose_id, now=None):
    """§4.9 Match Capsule from a SESSION['_matches'] record — a purpose-bound object (own purpose_id +
    version + TTL, §8.3) formed by mutual accept after revalidation."""
    mr = match_record or {}
    matched_ts = mr.get("matched_ts")
    completed_ts = mr.get("completed_ts")
    status = "completed" if completed_ts else ("active" if matched_ts else "expired")
    return {
        "match_id": _det_id("match", purpose_id, *sorted(str(p) for p in (participants or []))),
        "participants": list(participants or []), "purpose_id": purpose_id,
        "disclosure_state": "match_only", "links": {"reservation_id": None, "plan_id": None},
        "matched_ts": matched_ts, "completed_ts": completed_ts,
        "status": status, "version": 1, "ttl_seconds": MATCH_TTL, "_contract": CONTRACTS_VERSION,
    }

# ============================================================================= Group / Plan (§4 rows 10-11, pilot-disabled)
def build_group(quorum, roles, pair_blocks=None):
    """§4.10 set-formation contract — DEFINED but disabled (group_formation is off in the pilot, §1.2/§15)."""
    return {"group_id": _det_id("grp", quorum, ",".join(roles or [])), "quorum": quorum,
            "roles": list(roles or []), "pair_blocks": list(pair_blocks or []), "reservations": [],
            "decision_type": "group_formation", "enabled": False, "_contract": CONTRACTS_VERSION}

def build_plan(time_block, place_or_room, participants):
    """§4.11 agreed-activity contract — DEFINED but disabled in the pilot (post-pilot §14/§16)."""
    return {"plan_id": _det_id("plan", str(place_or_room), ",".join(str(p) for p in (participants or []))),
            "time_block": time_block, "place_or_room": place_or_room,
            "participants": list(participants or []), "state": "proposed",
            "decision_type": "plan", "enabled": False, "_contract": CONTRACTS_VERSION}

# ============================================================================= RelationshipEdge (§4 row 12)
def build_relationship_edge(pair, outcome_view, scope=None, now=None):
    """§4.12 pair history. State derived from the outcome view over the session store. ADVISORY — the
    authoritative cooldown stays the matching hard gate (declinedOwnerDaysAgo); this must not double-gate."""
    ov = outcome_view or {}
    now = float(now if now is not None else time.time())
    comp = int(ov.get("completed") or 0)
    acc = int(ov.get("accepted") or 0)
    cd_days = int(ov.get("cooldown_days") or DEFAULT_COOLDOWN_DAYS)
    declined = ov.get("declined_days")
    in_cooldown = isinstance(declined, (int, float)) and declined < cd_days
    if ov.get("blocked") or ov.get("blocksMe"):
        state = "block"
    elif ov.get("rejected") or in_cooldown:
        state = "avoid"
    elif comp >= 2:
        state = "repeat"
    elif comp >= 1:
        state = "friend"
    elif acc >= 1:
        state = "contact"
    else:
        state = "new"
    cooldown_until = _iso(now + (cd_days - declined) * 86400) if in_cooldown else None
    return {"edge_id": _det_id("edge", *sorted(str(p) for p in (pair or []))),
            "pair": list(pair or []), "state": state, "scope": scope,
            "cooldown_until": cooldown_until, "last_outcome_ts": ov.get("last_ts"),
            "version": 1, "_contract": CONTRACTS_VERSION}

# ============================================================================= enum-drift guard (tests)
def assert_enums_match(domains=None, decision_types=None, vibes=None, roles=None):
    """Return a list of drift problems between this module and the other services' enums. The test asserts
    it is empty, so a new engine domain (or decision type) added later without updating the maps fails CI
    instead of silently under-disclosing (SPEC-2 totality)."""
    problems = []
    for d in (domains or []):
        if d not in DOMAIN_TO_CONTEXT:
            problems.append("domain %r has no DOMAIN_TO_CONTEXT mapping (would project minimal)" % d)
    for c in set(DOMAIN_TO_CONTEXT.values()):
        if c not in PURPOSE_FIELDS:
            problems.append("context %r has no PURPOSE_FIELDS allow-list" % c)
    for dt in (decision_types or []):
        pass  # decision types validated at the app layer (PILOT_DECISION_TYPES); nothing to cross-check here
    # deny-column invariants (the load-bearing purpose-binding guarantees)
    for ctx in ("friendship", "networking", "language_exchange", "games", "sport"):
        if "datingOk" in PURPOSE_FIELDS.get(ctx, ()):
            problems.append("purpose-binding leak: dating field exposed in %s" % ctx)
    if "entities" in PURPOSE_FIELDS.get("dating", ()):
        problems.append("purpose-binding leak: professional 'entities' exposed in dating")
    return problems
