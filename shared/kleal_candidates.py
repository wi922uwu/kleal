# -*- coding: utf-8 -*-
"""Kleal — §16 Events / Online rooms / Venues as DISTINCT candidate types (keyless, LLM-free, deterministic,
PILOT-DISABLED scaffolding).

Core principle (§16.0): **an event is NOT «a user with big capacity».** Event / OnlineRoom / Venue are their own
object types, each with its OWN eligibility gate, its OWN DIRECTED user→object ranking (one-way — the object never
scores the user back; NO `reciprocal_score`, NO mutual policy, NO person pipeline), and its OWN data-only
transaction (registration/handoff · join-token/waitlist · selection/booking-handoff). An event/venue can CLOSE an
intent even without a personal match — and the system labels it HONESTLY as an ALTERNATIVE, never «a match with
people» (`is_personal_match:False`, `is_alternative:True`, `tier:'T4'`, `closes_intent_as:'alternative'` stamped at
build time — so «event ≠ user» is structural, not downstream decoration).

Discipline (mirrors kleal_groups / kleal_states EXACTLY): imports ONLY stdlib `hashlib` + `kleal_contracts` (kc) +
`kleal_states` (ks) + `kleal_groups` (kg). NEVER core_v2 / llm_client / app. No FS/clock/random at import OR at
runtime — `now_ts` is injected on every eligibility/ranking/transaction call and threaded into `kc.build_reservation
(now=now_ts)` (which otherwise defaults to `time.time()`). Ranking weights are MODULE-LOCAL heuristics (the
sha-pinned config has no event/room/venue weight block), documented not authoritative — a passed `cfg` never changes
a score. Capacity reuses the §14 `kg.claim_group_seat` → `ks.claim_slot` (single-process; cross-pod atomicity needs
the DB/queue the pilot does not run — blocked_infra). group_formation-style dormant-at-pilot: the algorithm runs
ONLY under an EXACT per-kind override; every payload still carries `enabled:False`.
"""
import hashlib
import kleal_contracts as kc
import kleal_states as ks
import kleal_groups as kg

CANDIDATES_VERSION = "candidates-16.0.0"
CANDIDATE_KINDS = ("event", "room", "venue")
# internal maps — the module NEVER imports or mutates app.PILOT_DECISION_TYPES; #39 wiring adds the (disabled)
# intent_to_venue key + the 'venue' proposal-type/ptype additively. 'event'/'room' already exist there.
DECISION_TYPE_OF_KIND = {"event": "intent_to_event", "room": "intent_to_room", "venue": "intent_to_venue"}
PTYPE_OF_KIND = {"event": "event", "room": "room", "venue": "venue"}
OVERRIDE_KEYS = {"event": "enable_intent_to_event", "room": "enable_intent_to_room", "venue": "enable_intent_to_venue"}

# module-local ranking weights (each sums to 1.0) — NOT config-derived, NOT reciprocal. Documented heuristics.
EVENT_WEIGHTS = {"topic": 0.35, "schedule": 0.25, "distance": 0.15, "price": 0.10, "access": 0.10, "capacity": 0.05}
ROOM_WEIGHTS = {"topic": 0.35, "liveness": 0.25, "moderation": 0.20, "language": 0.10, "platform": 0.10}
VENUE_WEIGHTS = {"distance": 0.25, "availability": 0.20, "noise": 0.20, "price": 0.15, "amenity": 0.10, "accessibility": 0.10}
_WEIGHTS_OF = {"event": EVENT_WEIGHTS, "room": ROOM_WEIGHTS, "venue": VENUE_WEIGHTS}

TOP_N = 10
_RES_TTL = 3600
_EPS = 1e-9


class CandidateError(ValueError):
    """Malformed candidate object; the endpoint catches it and stays enabled:False."""


# ----------------------------------------------------------------------------- deterministic toolkit (reuses kg)
def _id_hash(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()

def _obj_id(o):
    o = o or {}
    return str(o.get("id") or o.get("name") or o.get("title") or "")

def _clamp01(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return 0.0
    if x != x:                      # NaN -> deny-safe 0.0
        return 0.0
    return 0.0 if x < 0 else (1.0 if x > 1 else x)

def _round6(x):
    return round(float(x), 6)

def _list(v):
    if v is None:
        return []
    if isinstance(v, (set, frozenset)):     # sets have no order -> sort for determinism (no PYTHONHASHSEED leak)
        return sorted(str(x) for x in v if x is not None and str(x) != "")
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if x is not None and str(x) != ""]
    return [str(v)]

def _content_key(card):
    """A byte-stable identity of a card's VISIBLE content (name/kind/score/topics/components). The final sort
    tiebreak: two DISTINCT cards can collide on _obj_id (kc._det_id hashes only a field subset) and on score, so
    without a content key a stable sort would leak input order — this makes _sort_key a strict TOTAL order."""
    c = card or {}
    comp = c.get("components") or {}
    parts = [c.get("name"), c.get("kind"), c.get("score")] + _list(c.get("topics")) \
        + ["%s=%s" % (k, comp[k]) for k in sorted(comp)]
    return _id_hash(*parts)

def _sort_key(card):
    s = card.get("score")
    return (-float(s if s is not None else 0.0), _id_hash(_obj_id(card)), _obj_id(card), _content_key(card))

def _tokens(v):
    """Self-contained normalized topic tokens (LLM-free, taxonomy-free)."""
    out = set()
    for t in _list(v):
        for tok in str(t).lower().replace("/", " ").replace("-", " ").replace("_", " ").split():
            if tok:
                out.add(tok)
    return out

def _topic_overlap(obj_topics, intent_topics, topic_fn=None):
    """Directed topic overlap in [0,1]. `topic_fn` is an INJECTED input (mirrors §15 pair_rel); default is a
    self-contained literal-token Jaccard. NEVER app.topical / core_v2. Either side empty -> 0.0 (raw; the caller
    decides neutrality). Deny-safe."""
    if topic_fn is not None:
        try:
            return _clamp01(topic_fn(obj_topics, intent_topics))
        except Exception:
            return 0.0
    a, b = _tokens(obj_topics), _tokens(intent_topics)
    if not a or not b:
        return 0.0
    return len(a & b) / float(len(a | b))


# ----------------------------------------------------------------------------- window math (single epoch unit)
def _norm_windows(raw):
    """Normalize [[s,e],...] to a list of (epoch_s, epoch_e) via kc._parse_iso on BOTH bounds — the module
    accepts ISO strings or numeric epoch, never mixed raw minutes (blocking-issue: one unit end to end)."""
    out = []
    for w in raw or []:
        try:
            s, e = kc._parse_iso(w[0]), kc._parse_iso(w[1])
        except (TypeError, IndexError):
            continue
        if s is not None and e is not None and e > s:
            out.append((float(s), float(e)))
    return out

def _intent_windows(intent):
    it = intent or {}
    tb = it.get("time_block") if isinstance(it.get("time_block"), dict) else {}
    return _norm_windows(tb.get("windows") or it.get("availability") or it.get("windows"))


# ----------------------------------------------------------------------------- neutral-convention term helpers
def _distance_fit(km, radius):
    if radius is None:                                  # constraint absent -> neutral 1.0
        return 1.0
    if km is None:                                      # data absent under a stated constraint -> 0.5
        return 0.5
    try:
        return _clamp01(1.0 - min(float(km) / float(radius), 1.0)) if float(radius) > 0 else 1.0
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.5

def _price_fit(price, budget, paid=None):
    if budget is None:                                  # no budget stated -> neutral
        return 1.0
    if price is None:
        return 1.0 if paid is False else 0.5            # free -> 1.0; unknown price under a budget -> 0.5
    try:
        price, budget = float(price), float(budget)
    except (TypeError, ValueError):
        return 0.5
    if price <= budget:
        return 1.0
    return _clamp01(1.0 - (price - budget) / budget) if budget > 0 else 0.0

def _capacity_term(left, total):
    if (isinstance(left, (int, float)) and not isinstance(left, bool)
            and isinstance(total, (int, float)) and not isinstance(total, bool) and total > 0):
        return _clamp01(left / total)
    return 0.5

def _healthy_liveness(current, max_live, is_live=True):
    if not is_live or current is None or max_live is None:
        return 0.5 if (current is None or max_live is None) else 0.0
    try:
        current, max_live = float(current), float(max_live)
    except (TypeError, ValueError):
        return 0.5
    if max_live <= 0 or current <= 0 or current >= max_live:
        return 0.0
    return _clamp01(1.0 - abs(current / max_live - 0.5) * 2.0)     # peak at ~50% occupancy

def _desired_noise(intent):
    it = intent or {}
    p = (str(it.get("purpose") or (it.get("goal") or {}).get("purpose") or it.get("type") or "") + " "
         + str(it.get("vibe") or "")).lower()
    if any(w in p for w in ("cowork", "work", "study", "focus", "read", "quiet")):
        return "quiet"
    if any(w in p for w in ("party", "dance", "club", "loud", "lively", "celebr")):
        return "lively"
    return "moderate"

def _noise_term(venue_noise, desired):
    vn = str(venue_noise or "moderate")
    if vn == desired:
        return 1.0
    return 0.5 if "moderate" in (vn, desired) else 0.0     # moderate is adjacent to both; quiet<->lively opposite

def _schedule_term(e, it):
    iw = _intent_windows(it)
    if not iw:
        return 1.0                                      # no intent window constrained
    if not (isinstance(e.get("start_ts"), (int, float)) and isinstance(e.get("end_ts"), (int, float))):
        return 0.5
    dur = float(e["end_ts"]) - float(e["start_ts"])
    if dur <= 0:
        return 0.5
    return _clamp01(kg._total_length(kg._intersect(iw, [(float(e["start_ts"]), float(e["end_ts"]))])) / dur)

def _availability_term(vn, it):
    iw = _intent_windows(it)
    if not iw:
        return 1.0
    ow = _norm_windows(vn.get("open_windows"))
    if not ow:
        return 0.5
    tot = kg._total_length(iw)
    return 1.0 if tot <= 0 else _clamp01(kg._total_length(kg._intersect(iw, ow)) / tot)


# ----------------------------------------------------------------------------- §16 object builders (OBJECTS != users)
def _intrinsic(kind):
    return {"kind": kind, "is_personal_match": False, "is_alternative": True, "tier": "T4",
            "closes_intent_as": "alternative", "_contract": CANDIDATES_VERSION}

def build_event(raw, now_ts=None):
    """§16 Event object (NOT a user). start/end normalized to epoch; seats_left derived. Honest-alt labels at source."""
    raw = raw or {}
    start = kc._parse_iso(raw.get("start_ts") if raw.get("start_ts") is not None else raw.get("start"))
    end = kc._parse_iso(raw.get("end_ts") if raw.get("end_ts") is not None else raw.get("end"))
    total, taken = raw.get("seats_total"), raw.get("seats_taken") or 0
    left = (int(total) - int(taken)) if isinstance(total, (int, float)) and not isinstance(total, bool) else raw.get("seats_left")
    d = _intrinsic("event")
    d.update({"id": kc._det_id("event", raw.get("title"), start), "title": raw.get("title"),
              "topics": _list(raw.get("topics") or raw.get("category")), "start_ts": start, "end_ts": end,
              "seats_total": total, "seats_taken": taken, "seats_left": left,
              "km": raw.get("km"), "area": raw.get("city") or raw.get("area"),
              "price": raw.get("price"), "paid": bool(raw.get("paid") or (raw.get("price") or 0) > 0),
              "currency": raw.get("currency"), "age_min": raw.get("age_min"),
              "verified_required": bool(raw.get("verified_required")), "required_language": raw.get("required_language"),
              "languages": _list(raw.get("languages")), "external_url": raw.get("external_url") or raw.get("url"),
              "host_id": raw.get("host_id")})
    return d

def build_room(raw, now_ts=None):
    """§16 Online room object — the same thing §12 _online_fallback describes as a 'Live room' T4 card, here a
    first-class typed object (labels shared, code path separate)."""
    raw = raw or {}
    d = _intrinsic("room")
    d.update({"id": kc._det_id("room", raw.get("platform"), raw.get("title") or raw.get("topic")),
              "title": raw.get("title"), "topics": _list(raw.get("topics") or raw.get("topic")),
              "platform": raw.get("platform"), "max_live": raw.get("max_live"),
              "current_participants": raw.get("current_participants"),
              "is_live": bool(raw.get("is_live", True)),
              "is_moderated": bool(raw.get("is_moderated") or raw.get("has_moderator")),
              "languages": _list(raw.get("languages")), "required_language": raw.get("required_language"),
              "join_url": raw.get("join_url") or raw.get("url"), "mode": "online"})
    return d

def build_venue(raw, now_ts=None):
    """§16 Venue object."""
    raw = raw or {}
    d = _intrinsic("venue")
    d.update({"id": kc._det_id("venue", raw.get("name"), raw.get("area") or raw.get("city")),
              "name": raw.get("name"), "topics": _list(raw.get("amenities") or raw.get("topics")),
              "open_windows": _norm_windows(raw.get("open_windows")), "price": raw.get("price"),
              "price_band": raw.get("price_band"), "currency": raw.get("currency"),
              "noise": raw.get("noise"), "km": raw.get("km"), "area": raw.get("area") or raw.get("city"),
              "step_free": bool(raw.get("step_free")), "wheelchair": bool(raw.get("wheelchair")),
              "accessibility_features": _list(raw.get("accessibility_features")),
              "booking_url": raw.get("booking_url") or raw.get("url"),
              "capacity": raw.get("capacity"), "bookable": bool(raw.get("bookable", True))})
    return d

_BUILDER_OF = {"event": build_event, "room": build_room, "venue": build_venue}

def build_object(kind, raw, now_ts=None):
    """Normalize a raw candidate dict into its typed object (derives seats_left/paid/epoch windows + stamps the
    honest-alt labels). IDEMPOTENT on an already-built object — the wiring layer feeds raw slate dicts through it."""
    b = _BUILDER_OF.get(kind)
    return b(raw, now_ts=now_ts) if b else (raw or {})

def build_candidate_view(obj, kind, purpose):
    """OBJECT-level minimal disclosure (title/topics/time/place/price/url ONLY) — deliberately NOT
    kc.build_profile_view (that is person purpose-binding, §8.3). An object has no person fields to bind."""
    o = obj or {}
    fields = {k: o.get(k) for k in ("title", "name", "topics", "start_ts", "end_ts", "open_windows",
                                    "area", "km", "price", "platform", "noise", "external_url", "join_url",
                                    "booking_url") if o.get(k) is not None}
    return {"view_id": kc._det_id("cv", _obj_id(o), kind, purpose), "kind": kind, "purpose": purpose,
            "is_personal_match": False, "is_alternative": True, "fields": fields, "_contract": CANDIDATES_VERSION}


# ----------------------------------------------------------------------------- eligibility (OWN gate per type = distinct path)
def event_eligibility(event, intent, user, now_ts):
    """§16 Event hard gate (category/schedule/capacity/access). SORTED codes; [] == eligible; deny-safe; the
    access dims (verified/language/paid) are prove-eligible under a STATED requirement. now_ts injected."""
    e, it, u = event or {}, intent or {}, user or {}
    v = []
    ot, itt = _list(e.get("topics")), _list(it.get("topics"))
    if ot and itt and _topic_overlap(ot, itt) == 0:
        v.append("CATEGORY_MISMATCH")
    end = e.get("end_ts")
    if isinstance(end, (int, float)) and not isinstance(end, bool) and now_ts is not None and end <= float(now_ts):
        v.append("SCHEDULE_PAST")
    iw = _intent_windows(it)
    if iw and isinstance(e.get("start_ts"), (int, float)) and isinstance(e.get("end_ts"), (int, float)):
        if kg._total_length(kg._intersect(iw, [(float(e["start_ts"]), float(e["end_ts"]))])) <= 0:
            v.append("SCHEDULE_NO_OVERLAP")
    sl = e.get("seats_left")
    if isinstance(sl, (int, float)) and not isinstance(sl, bool) and sl <= 0:
        v.append("CAPACITY_FULL")
    age_min, age = e.get("age_min"), u.get("age")
    if isinstance(age_min, (int, float)) and isinstance(age, (int, float)) and age < age_min:
        v.append("ACCESS_AGE")
    if e.get("verified_required") and not u.get("verified"):
        v.append("ACCESS_VERIFIED")
    rl = e.get("required_language")
    if rl and rl not in set(_list(u.get("langs") or u.get("languages"))):
        v.append("ACCESS_LANGUAGE")
    if (it.get("free_only") or it.get("freeOnly")) and e.get("paid"):
        v.append("ACCESS_PAID")
    km, radius = e.get("km"), it.get("radiusKm") or it.get("radius_km")
    if isinstance(km, (int, float)) and isinstance(radius, (int, float)) and km > radius:
        v.append("GEO_OUT_OF_RADIUS")
    return sorted(set(v))

def room_eligibility(room, intent, user, now_ts):
    """§16 Online-room hard gate (platform/topic/live_capacity/moderation). An OFFLINE intent is never silently
    swapped to online — MODE_OFFLINE_NO_CONSENT unless allowOnlineFallback (§5.1 row4: the room is an EXPLAINED
    alternative, pre-approved only on consent)."""
    r, it, u = room or {}, intent or {}, user or {}
    v = []
    ot, itt = _list(r.get("topics")), _list(it.get("topics"))
    if ot and itt and _topic_overlap(ot, itt) == 0:
        v.append("TOPIC_MISMATCH")
    allowed = _list(it.get("platforms"))
    if allowed and r.get("platform") and r.get("platform") not in allowed:
        v.append("PLATFORM_UNSUPPORTED")
    if str(it.get("mode") or "") == "offline" and not it.get("allowOnlineFallback"):
        v.append("MODE_OFFLINE_NO_CONSENT")
    cur, mx = r.get("current_participants"), r.get("max_live")
    if isinstance(cur, (int, float)) and isinstance(mx, (int, float)) and cur >= mx:
        v.append("LIVE_CAPACITY_FULL")
    if it.get("requireModeration") and not r.get("is_moderated"):
        v.append("MODERATION_REQUIRED")
    rl = it.get("required_language")
    if rl and rl not in set(_list(r.get("languages"))):
        v.append("LANGUAGE_UNCOVERED")
    return sorted(set(v))

def venue_eligibility(venue, intent, user, now_ts):
    """§16 Venue hard gate (availability/price/noise/distance/accessibility). NOISE is a gate ONLY when the intent
    HARD-requires quiet and the venue is lively; otherwise noise is a soft ranking term. Accessibility is
    prove-eligible under a stated requirement."""
    vn, it = venue or {}, intent or {}
    v = []
    iw, ow = _intent_windows(it), _norm_windows(vn.get("open_windows"))
    if iw and ow and kg._total_length(kg._intersect(iw, ow)) <= 0:
        v.append("UNAVAILABLE")
    price, budget = vn.get("price"), it.get("budget") or it.get("budgetMax")
    if isinstance(price, (int, float)) and isinstance(budget, (int, float)) and price > budget:
        v.append("PRICE_OVER_BUDGET")
    km, radius = vn.get("km"), it.get("radiusKm") or it.get("radius_km")
    if isinstance(km, (int, float)) and isinstance(radius, (int, float)) and km > radius:
        v.append("GEO_OUT_OF_RADIUS")
    if (it.get("requireQuiet") or it.get("quietRequired")) and str(vn.get("noise") or "") == "lively":
        v.append("NOISE_UNACCEPTABLE")
    if it.get("requireStepFree") or it.get("requireAccessible"):
        if not (vn.get("step_free") or vn.get("wheelchair") or vn.get("accessibility_features")):
            v.append("ACCESSIBILITY_REQUIRED")
    return sorted(set(v))

_ELIG_OF = {"event": event_eligibility, "room": room_eligibility, "venue": venue_eligibility}

def check_eligibility(kind, obj, intent, user, now_ts):
    fn = _ELIG_OF.get(kind)
    return fn(obj, intent, user, now_ts) if fn else ["UNKNOWN_KIND"]

def is_eligible(kind, obj, intent, user, now_ts):
    return not check_eligibility(kind, obj, intent, user, now_ts)


# ----------------------------------------------------------------------------- DIRECTED user->object ranking
def _event_terms(e, it, u, topic_fn):
    ot, itt = _list(e.get("topics")), _list(it.get("topics"))
    dims = []
    if e.get("age_min") is not None:
        age = u.get("age")
        dims.append(1.0 if isinstance(age, (int, float)) and age >= e["age_min"] else (0.5 if age is None else 0.0))
    if e.get("verified_required"):
        dims.append(1.0 if u.get("verified") else 0.0)
    if e.get("required_language"):
        dims.append(1.0 if e["required_language"] in set(_list(u.get("langs") or u.get("languages"))) else 0.0)
    access = sum(dims) / len(dims) if dims else 1.0
    return {"topic": 1.0 if not itt else _topic_overlap(ot, itt, topic_fn), "schedule": _schedule_term(e, it),
            "distance": _distance_fit(e.get("km"), it.get("radiusKm") or it.get("radius_km")),
            "price": _price_fit(e.get("price"), it.get("budget") or it.get("budgetMax"), e.get("paid")),
            "access": access, "capacity": _capacity_term(e.get("seats_left"), e.get("seats_total"))}

def _room_terms(r, it, u, topic_fn):
    ot, itt = _list(r.get("topics")), _list(it.get("topics"))
    rl = it.get("required_language")
    lang = 1.0 if not rl else (1.0 if rl in set(_list(r.get("languages"))) else 0.0)
    allowed = _list(it.get("platforms"))
    plat = 1.0 if (not allowed or (r.get("platform") in allowed)) else 0.0
    return {"topic": 1.0 if not itt else _topic_overlap(ot, itt, topic_fn),
            "liveness": _healthy_liveness(r.get("current_participants"), r.get("max_live"), r.get("is_live", True)),
            "moderation": 1.0 if r.get("is_moderated") else 0.0, "language": lang, "platform": plat}

def _venue_terms(vn, it, u, topic_fn):
    ot, itt = _list(vn.get("topics")), _list(it.get("topics"))
    return {"distance": _distance_fit(vn.get("km"), it.get("radiusKm") or it.get("radius_km")),
            "availability": _availability_term(vn, it),
            "noise": _noise_term(vn.get("noise"), _desired_noise(it)),
            "price": _price_fit(vn.get("price"), it.get("budget") or it.get("budgetMax")),
            "amenity": 1.0 if not itt else _topic_overlap(ot, itt, topic_fn),
            "accessibility": 1.0}                          # unsatisfied+required is already ineligible

_TERMS_OF = {"event": _event_terms, "room": _room_terms, "venue": _venue_terms}

def score_candidate(kind, obj, intent, user, now_ts, weights=None, topic_fn=None):
    """DIRECTED user→object score. Returns {score, components, weighted, eligible, violations, kind,
    is_alternative:True, is_personal_match:False}. FEASIBILITY DOMINATES: ineligible -> score None (never a
    number), so it can never be ranked/selected. Weights are module-local; a passed weights dict may override
    for tests but a config is never consulted."""
    viol = check_eligibility(kind, obj, intent, user, now_ts)
    W = weights or _WEIGHTS_OF.get(kind) or {}
    terms = (_TERMS_OF.get(kind) or (lambda *a: {}))(obj or {}, intent or {}, user or {}, topic_fn)
    weighted = {k: W.get(k, 0.0) * terms.get(k, 0.0) for k in W}
    total = _round6(sum(weighted.values()))
    return {"score": None if viol else total, "components": terms, "weighted": weighted,
            "eligible": not viol, "violations": viol, "kind": kind,
            "is_alternative": True, "is_personal_match": False}

def user_event_relevance(event, intent, user, now_ts, weights=None, topic_fn=None):
    return score_candidate("event", event, intent, user, now_ts, weights=weights, topic_fn=topic_fn)

def session_relevance(room, intent, user, now_ts, weights=None, topic_fn=None):
    return score_candidate("room", room, intent, user, now_ts, weights=weights, topic_fn=topic_fn)

def plan_suitability(venue, intent, user, now_ts, weights=None, topic_fn=None):
    return score_candidate("venue", venue, intent, user, now_ts, weights=weights, topic_fn=topic_fn)

def _as_alternative_card(kind, obj, score, components):
    """Package one scored object as a T4 ALTERNATIVE card (same T4 vocabulary as app._online_fallback, SEPARATE
    code path). Never a person/mutual match."""
    o = obj or {}
    return {"name": o.get("title") or o.get("name"), "id": _obj_id(o), "kind": kind, "score": score, "tier": "T4",
            "is_personal_match": False, "is_alternative": True, "closes_intent_as": "alternative",
            "ladder_step": 6, "retrieval_source": 4, "fallback": "alternative",
            "topics": _list(o.get("topics")), "components": components}

def rank_candidates(kind, objects, intent, user, now_ts, top_n=None, weights=None, topic_fn=None):
    """Score each object DIRECTED user→object, DROP the ineligible (score None), sort by (-score, id-hash, id),
    diversify <=3 per topic bucket, cap top_n. O(n log n); one pass per object (no §15 pairwise blow-up)."""
    scored = []
    for o in objects or []:
        r = score_candidate(kind, o, intent, user, now_ts, weights=weights, topic_fn=topic_fn)
        if r["score"] is None:
            continue
        scored.append(_as_alternative_card(kind, o, r["score"], r["components"]))
    scored.sort(key=_sort_key)
    out, buckets = [], {}
    for c in scored:
        b = (c.get("topics") or ["misc"])[0]
        if buckets.get(b, 0) >= 3:
            continue
        buckets[b] = buckets.get(b, 0) + 1
        out.append(c)
    out = out[: int(top_n or TOP_N)]
    for i, c in enumerate(out):
        c["rank"] = i + 1
    return out


# ----------------------------------------------------------------------------- transactions (data-only; §14 capacity)
def claim_seat(ledger, resource_id, seat_ordinal, capacity, claimant):
    """Capacity seat claim — REUSES §14 kg.claim_group_seat (rejects seat_ordinal>=capacity pre-claim; delegates
    to ks.claim_slot on 'resource#seatN'). Single-process; NO bespoke lock."""
    return kg.claim_group_seat(ledger if isinstance(ledger, dict) else {}, resource_id, seat_ordinal, capacity, claimant)

def _seats_used(ledger, resource_id):
    led = ledger if isinstance(ledger, dict) else {}
    return sum(1 for k in led if str(k).startswith(str(resource_id) + "#seat"))

def event_transaction(event, intent, ledger, now_ts, capacity=None, claimant=None):
    """§16 Event transaction — DATA-ONLY. external_url -> external_handoff descriptor; else a seat registration
    (kc.build_reservation(now=now_ts)); a full-house loser -> waitlist via ks.resolve_race('slot_taken')."""
    e = event or {}
    eid = e.get("id") or kc._det_id("event", e.get("title"))
    claimant = claimant or "me"
    out = {"kind": "event", "is_alternative": True, "is_personal_match": False, "enabled": False,
           "proposal_type": "event", "resource_id": eid}
    if e.get("external_url"):
        out.update({"mode": "external_handoff", "url": e.get("external_url"),
                    "handoff_token": kc._det_id("hand", eid, claimant, int(now_ts or 0))})
        return out
    cap = int(capacity if capacity is not None else (e.get("seats_left") if isinstance(e.get("seats_left"), int)
              else (e.get("seats_total") or 0)))
    led = ledger if isinstance(ledger, dict) else {}
    res = claim_seat(led, eid, _seats_used(led, eid), cap, claimant)
    if res["won"]:
        out.update({"mode": "registration", "status": "held",
                    "reservation": kc.build_reservation(res["seat"], claimant, ttl_s=_RES_TTL, now=now_ts)})
    else:
        race = ks.resolve_race("slot_taken")
        out.update({"mode": "waitlist", "state": race["to"], "public_reason": race["public_reason"],
                    "leak": False, "error_code": res["error_code"]})
    return out

def room_transaction(room, intent, ledger, now_ts, capacity=None, claimant=None):
    """§16 Online-room transaction — join_token on a won live seat, else waitlist (deterministic descriptor id,
    NOT a real credential)."""
    r = room or {}
    rid = r.get("id") or kc._det_id("room", r.get("platform"), r.get("title"))
    claimant = claimant or "me"
    out = {"kind": "room", "is_alternative": True, "is_personal_match": False, "enabled": False,
           "proposal_type": "room", "resource_id": rid}
    # capacity = LIVE-remaining (max_live - externally-present), NOT max_live — a room already full has 0 free
    # live slots even with an empty local ledger (mirrors event seats_left = seats_total - seats_taken).
    live_left = max(0, int(r.get("max_live") or 0) - int(r.get("current_participants") or 0))
    cap = int(capacity if capacity is not None else live_left)
    led = ledger if isinstance(ledger, dict) else {}
    res = claim_seat(led, rid, _seats_used(led, rid), cap, claimant)
    if res["won"]:
        out.update({"mode": "join_token", "token": kc._det_id("join", rid, claimant, int(now_ts or 0)),
                    "reservation": kc.build_reservation(res["seat"], claimant, ttl_s=_RES_TTL, now=now_ts)})
    else:
        race = ks.resolve_race("slot_taken")
        out.update({"mode": "waitlist", "state": race["to"], "public_reason": race["public_reason"],
                    "leak": False, "error_code": res["error_code"]})
    return out

def venue_transaction(venue, intent, participants, now_ts, ledger=None):
    """§16 Venue transaction — selection (kc.build_plan, enabled:False) or a booking handoff descriptor
    (kc.build_reservation(now=now_ts))."""
    vn = venue or {}
    vid = vn.get("id") or kc._det_id("venue", vn.get("name"))
    tb = (intent or {}).get("time_block") or (intent or {}).get("time")
    out = {"kind": "venue", "is_alternative": True, "is_personal_match": False, "enabled": False,
           "proposal_type": "venue", "resource_id": vid}
    if vn.get("booking_url"):
        out.update({"mode": "booking_handoff", "booking_url": vn.get("booking_url"),
                    "reservation": kc.build_reservation(vid, "me", ttl_s=_RES_TTL, now=now_ts)})
    else:
        out.update({"mode": "selection",
                    "plan": kc.build_plan(tb, vn.get("name"), list(participants or []))})
    return out

def build_transaction(kind, obj, intent, ledger=None, now_ts=None, capacity=None, claimant=None, participants=None):
    if kind == "event":
        return event_transaction(obj, intent, ledger, now_ts, capacity=capacity, claimant=claimant)
    if kind == "room":
        return room_transaction(obj, intent, ledger, now_ts, capacity=capacity, claimant=claimant)
    if kind == "venue":
        return venue_transaction(obj, intent, participants, now_ts, ledger=ledger)
    return {"kind": kind, "enabled": False, "is_alternative": True, "is_personal_match": False, "error_code": "UNKNOWN_KIND"}


# ----------------------------------------------------------------------------- pilot gate + endpoint body
def is_override_enabled(kind, override):
    """True IFF override is a dict whose EXACT per-kind key (OVERRIDE_KEYS[kind]) is boolean True; anything else
    (None/{}/wrong key/'true'-string) -> False (stays dormant)."""
    return isinstance(override, dict) and override.get(OVERRIDE_KEYS.get(kind)) is True

def dormant_response(kind, intent, note=None):
    return {"decision_type": DECISION_TYPE_OF_KIND.get(kind), "kind": kind, "enabled": False, "override": False,
            "candidates": [], "count": 0, "is_alternative": True, "is_personal_match": False,
            "pilot": {"enabled": False, "note": note or ("%s recommendation is not enabled in this pilot (§16)" % kind)}}

def run_candidates(kind, intent, objects, user, cfg=None, override=None, now_ts=None, ledger=None, topic_fn=None, top_n=None):
    """Gated PER-KIND endpoint body (DISTINCT code path per §16.0). Dormant UNLESS is_override_enabled(kind,...);
    result ALWAYS enabled:False; NEVER mutates PILOT_DECISION_TYPES. `cfg` is accepted for endpoint symmetry but
    NEVER influences a score (§16 ranking is not config-derived). now_ts injected (0.0 sentinel = clock-free)."""
    if kind not in CANDIDATE_KINDS:
        return dormant_response(kind, intent, note="unknown candidate kind")
    if not is_override_enabled(kind, override):
        return dormant_response(kind, intent)
    nt = float(now_ts) if now_ts is not None else 0.0
    try:
        objs = [build_object(kind, o, now_ts=nt) for o in (objects or []) if isinstance(o, dict)]   # raw slate -> typed object
        cards = rank_candidates(kind, objs, intent, user, nt, top_n=top_n, topic_fn=topic_fn)
    except Exception as e:
        return dict(dormant_response(kind, intent, note="candidate error"), error=str(e)[:200])
    return {"decision_type": DECISION_TYPE_OF_KIND.get(kind), "kind": kind, "enabled": False, "override": True,
            "candidates": cards, "count": len(cards), "is_alternative": True, "is_personal_match": False,
            "closes_intent_as": "alternative"}

def _infer_kind(intent):
    it = intent or {}
    if it.get("roomId") or str(it.get("type") or "") == "room":
        return "room"
    if it.get("venueId") or str(it.get("type") or "") == "venue":
        return "venue"
    return "event"

def run_candidate_recommendation(intent, objects, user, cfg=None, kind=None, override=None, now_ts=None, ledger=None, topic_fn=None):
    """Thin UNIFIED dispatcher: resolve the kind, then delegate to the per-kind run_candidates (unified API on the
    outside, DISTINCT code paths inside per §16.0)."""
    return run_candidates(kind or _infer_kind(intent), intent, objects, user, cfg=cfg, override=override,
                          now_ts=now_ts, ledger=ledger, topic_fn=topic_fn)


# ----------------------------------------------------------------------------- introspection (tests/docs)
def summary():
    return {"candidates_version": CANDIDATES_VERSION, "kinds": list(CANDIDATE_KINDS),
            "weight_source": "module_local_heuristic (NOT config, NOT reciprocal)",
            "weight_sums": {k: round(sum(w.values()), 6) for k, w in _WEIGHTS_OF.items()},
            "reuses": ["kleal_contracts", "kleal_states", "kleal_groups"], "enabled": False}
