# -*- coding: utf-8 -*-
"""Kleal — §14 Transaction state machines & race protection (keyless, LLM-free, deterministic).

The spec (§14) defines FOUR lifecycle state machines (Intent / Proposal / Match / Plan), optimistic
concurrency, idempotency, a unique-active-pair rule, per-intent-type concurrent-accept policy, and a
table of race resolutions that never leak a private reason. This module implements exactly that surface
as PURE functions over plain dicts — no clock at module scope, no FS, no core_v2/config, no model access.
It mirrors the additive/read-only discipline of `kleal_contracts`: it NEVER mutates status/agree/reason
and never renames a publicly-advertised code (POLICY_CHANGED is reused verbatim).

What is honestly deliverable here (single-process, in the matching service's own gitignored store):
  - the 4 transition tables + a deny-safe validator (`can_transition`/`next_state`/`apply_transition`),
  - optimistic-concurrency CAS on a monotone `version` (`check_version`/`compare_and_swap`),
  - idempotency de-dup on a clock-free entity+action key (`dedup_key`/`dedup`),
  - unique-active-pair enforcement (`unique_active_pair`),
  - §14.3 per-intent-type concurrent-accept policy (`concurrent_accept_policy`),
  - §14.4 the eight race cases -> a deterministic {state, error_code, public_reason, leak:False} (`resolve_race`).

What this module does NOT pretend to be (see docs/STATE_MACHINES.md — blocked_infra): a transactional
outbox with an async consumer, cross-entity atomic commit across services, or real group/event capacity.
Those need a DB/queue the pilot does not run; the Plan machine is defined for conformance but `enabled:False`.
"""

STATES_VERSION = "states-14.0.0"

# ----------------------------------------------------------------------------- §14.1 the four machines
# Each: states (tuple), initial, terminal (no outgoing edges), transitions {from: [allowed to,...]}.
STATE_MACHINES = {
    # Intent lifecycle (§5 draft/confirm + §10.1 pause maps onto WAITING; SATISFIED/EXPIRED/CANCELLED terminal).
    "intent": {
        "states": ("DRAFT", "CONFIRMED", "SEARCHING", "WAITING", "SATISFIED", "EXPIRED", "CANCELLED"),
        "initial": "DRAFT",
        "terminal": ("SATISFIED", "EXPIRED", "CANCELLED"),
        "transitions": {
            "DRAFT":     ["CONFIRMED", "CANCELLED"],
            "CONFIRMED": ["SEARCHING", "EXPIRED", "CANCELLED"],
            "SEARCHING": ["WAITING", "SATISFIED", "EXPIRED", "CANCELLED"],
            "WAITING":   ["SEARCHING", "SATISFIED", "EXPIRED", "CANCELLED"],
            "SATISFIED": [], "EXPIRED": [], "CANCELLED": [],
        },
        "enabled": True,
    },
    # Proposal lifecycle (§13 typed actions produce these; POLICY_REVOKED is the §8.2 revalidation terminal).
    "proposal": {
        "states": ("CREATED", "RESERVED", "SENT", "VIEWED", "ACCEPTED", "DECLINED",
                   "COUNTERED", "WITHDRAWN", "EXPIRED", "POLICY_REVOKED"),
        "initial": "CREATED",
        "terminal": ("ACCEPTED", "DECLINED", "WITHDRAWN", "EXPIRED", "POLICY_REVOKED"),
        "transitions": {
            "CREATED":   ["RESERVED", "SENT", "WITHDRAWN", "EXPIRED", "POLICY_REVOKED"],
            "RESERVED":  ["SENT", "WITHDRAWN", "EXPIRED", "POLICY_REVOKED"],
            "SENT":      ["VIEWED", "ACCEPTED", "DECLINED", "COUNTERED", "WITHDRAWN", "EXPIRED", "POLICY_REVOKED"],
            "VIEWED":    ["ACCEPTED", "DECLINED", "COUNTERED", "WITHDRAWN", "EXPIRED", "POLICY_REVOKED"],
            "COUNTERED": ["SENT", "ACCEPTED", "DECLINED", "WITHDRAWN", "EXPIRED", "POLICY_REVOKED"],
            "ACCEPTED": [], "DECLINED": [], "WITHDRAWN": [], "EXPIRED": [], "POLICY_REVOKED": [],
        },
        "enabled": True,
    },
    # Match lifecycle (§4.9 capsule; mutual accept -> ... -> COMPLETED; SAFETY_CLOSED is the block/safety terminal).
    "match": {
        "states": ("PENDING_DISCLOSURE", "MUTUAL", "CHAT_OPEN", "PLANNING", "PLANNED",
                   "COMPLETED", "CANCELLED", "SAFETY_CLOSED"),
        "initial": "PENDING_DISCLOSURE",
        "terminal": ("COMPLETED", "CANCELLED", "SAFETY_CLOSED"),
        "transitions": {
            "PENDING_DISCLOSURE": ["MUTUAL", "CANCELLED", "SAFETY_CLOSED"],
            "MUTUAL":   ["CHAT_OPEN", "CANCELLED", "SAFETY_CLOSED"],
            "CHAT_OPEN": ["PLANNING", "CANCELLED", "SAFETY_CLOSED"],
            "PLANNING": ["PLANNED", "CANCELLED", "SAFETY_CLOSED"],
            "PLANNED":  ["COMPLETED", "CANCELLED", "SAFETY_CLOSED"],
            "COMPLETED": [], "CANCELLED": [], "SAFETY_CLOSED": [],
        },
        "enabled": True,
    },
    # Plan lifecycle (§4.11) — DEFINED for conformance but pilot-disabled (group/plan is off §1.2/§15/§16).
    "plan": {
        "states": ("DRAFT", "PROPOSED", "PARTIALLY_CONFIRMED", "CONFIRMED", "CHANGED",
                   "COMPLETED", "CANCELLED", "NO_SHOW"),
        "initial": "DRAFT",
        "terminal": ("COMPLETED", "CANCELLED", "NO_SHOW"),
        "transitions": {
            "DRAFT":     ["PROPOSED", "CANCELLED"],
            "PROPOSED":  ["PARTIALLY_CONFIRMED", "CONFIRMED", "CHANGED", "CANCELLED"],
            "PARTIALLY_CONFIRMED": ["CONFIRMED", "CHANGED", "CANCELLED"],
            "CONFIRMED": ["CHANGED", "COMPLETED", "CANCELLED", "NO_SHOW"],
            "CHANGED":   ["PARTIALLY_CONFIRMED", "CONFIRMED", "CANCELLED"],
            "COMPLETED": [], "CANCELLED": [], "NO_SHOW": [],
        },
        "enabled": False,
    },
}

# ----------------------------------------------------------------------------- error codes (§14 vocabulary)
# POLICY_CHANGED is reused VERBATIM from §8.2 (advertised in GET /api/agent/weights reason_codes) — never rename.
ERROR_CODES = ("OK", "POLICY_CHANGED", "INTENT_NOT_ACTIVE", "SLOT_TAKEN", "EXPIRED",
               "DUPLICATE_PAIR", "DUPLICATE", "TIME_INFEASIBLE", "ILLEGAL_TRANSITION", "VERSION_CONFLICT")

# ----------------------------------------------------------------------------- §13 action -> proposal edge
# Maps a §13 typed ACTION onto the Proposal target state. Adds the two producers §13 left as labels
# (WITHDRAW/EXPIRE); leaves kp.map_decision_to_action's agree->ACCEPT / counter->COUNTER_* mapping untouched.
ACTION_TO_STATE = {
    "PROPOSE_CONNECTION": "SENT",
    "ACCEPT":             "ACCEPTED",
    "DECLINE":            "DECLINED",
    "COUNTER_TIME":       "COUNTERED",
    "COUNTER_FORMAT":     "COUNTERED",
    "WITHDRAW":           "WITHDRAWN",
    "EXPIRE":             "EXPIRED",
    "POLICY_CHANGED":     "POLICY_REVOKED",
}


# ----------------------------------------------------------------------------- validator (deny-safe)
def machine(entity):
    return STATE_MACHINES.get(str(entity or "").lower())

def initial_state(entity):
    m = machine(entity)
    return m["initial"] if m else None

def is_terminal(entity, state):
    m = machine(entity)
    return bool(m) and state in m["terminal"]

def can_transition(entity, frm, to):
    """True iff `to` is a declared successor of `frm` for `entity`. Unknown entity/state -> False (deny-safe)."""
    m = machine(entity)
    if not m or frm not in m["transitions"]:
        return False
    return to in m["transitions"].get(frm, [])

def next_state(entity, current, action):
    """The Proposal state a §13 action drives to, or None if that edge is illegal from `current`."""
    to = ACTION_TO_STATE.get(str(action or "").upper())
    if to is None:
        return None
    cur = current or initial_state(entity)
    return to if can_transition(entity, cur, to) else None

def apply_transition(obj, entity, to):
    """ADDITIVE state move on a plain dict: on a legal edge set obj['state']=to and bump obj['version'];
    on an illegal edge return an error dict WITHOUT mutating obj. Never touches status/agree/reason/name.
    Clock-free — the caller stamps any timestamp (kc._iso) so this stays replay-deterministic."""
    cur = obj.get("state") or initial_state(entity)
    if not can_transition(entity, cur, to):
        return {"ok": False, "error_code": "ILLEGAL_TRANSITION", "state": cur, "entity": entity}
    obj["state"] = to
    obj["version"] = int(obj.get("version", 1)) + 1
    return {"ok": True, "obj": obj, "state": to, "version": obj["version"], "error_code": "OK"}


# ----------------------------------------------------------------------------- optimistic concurrency (CAS)
def check_version(obj, expected):
    """CAS predicate: the object's current version equals the version the caller last read."""
    try:
        return int(obj.get("version", 1)) == int(expected)
    except (TypeError, ValueError):
        return False

def compare_and_swap(obj, entity, to, expected_version):
    """Version-gated transition. A stale expected_version -> VERSION_CONFLICT (a second concurrent writer on
    the SAME object loses). NOTE (§14.3): CAS on ONE proposal cannot enforce 1:1 exclusivity between two
    DIFFERENT candidates — each proposal starts at version 1 so both would pass. Exclusivity between distinct
    candidates is enforced by the shared per-intent slot marker (`claim_slot`), not by this per-object CAS."""
    if not check_version(obj, expected_version):
        return {"ok": False, "error_code": "VERSION_CONFLICT", "state": obj.get("state"),
                "version": int(obj.get("version", 1))}
    return apply_transition(obj, entity, to)


# ----------------------------------------------------------------------------- idempotency (clock-free dedup)
def dedup_key(entity, entity_id, action, extra=None):
    """A REPLAY-stable key = entity|id|action(|extra). Composed from action so a WITHDRAW-after-ACCEPT on the
    same pair is NOT collapsed as a duplicate of the ACCEPT (the §4 idempotency_key omits action). Never uses a
    proposal_id (it embeds int(now)); a caller-supplied idempotency_key may be passed as `extra`."""
    parts = [str(entity or ""), str(entity_id or ""), str(action or "").upper()]
    if extra is not None:
        parts.append(str(extra))
    return "txn:" + "|".join(parts)

def dedup(seen, key, result=None):
    """First sight of `key` -> record `result`, return {'duplicate':False}. A replay -> return the STORED prior
    result with error_code DUPLICATE and no re-apply. `seen` is a plain dict living in the caller's SESSION."""
    if not isinstance(seen, dict):
        return {"duplicate": False, "first": True}
    if key in seen:
        prior = seen.get(key)
        return {"duplicate": True, "error_code": "DUPLICATE", "result": prior}
    seen[key] = result if result is not None else {"ts": None}
    return {"duplicate": False, "first": True, "result": seen[key]}


# ----------------------------------------------------------------------------- unique active pair
def _pair_key(pair, purpose=None):
    ps = sorted(str(p or "").strip().lower() for p in (pair or []) if str(p or "").strip())
    base = "|".join(ps)
    return base + ("::" + str(purpose) if purpose else "")

def unique_active_pair(active, pair, purpose=None):
    """§14.2: at most one ACTIVE proposal/match per (unordered pair, purpose). `active` is a set/dict of pair
    keys the caller already holds open. Returns {ok, error_code} — a duplicate second wave -> DUPLICATE_PAIR
    (the first-wave send is never dropped: it is not yet in `active` when it is checked)."""
    key = _pair_key(pair, purpose)
    have = key in active if isinstance(active, (set, dict)) else key in (active or [])
    if have:
        return {"ok": False, "error_code": "DUPLICATE_PAIR", "pair_key": key}
    return {"ok": True, "error_code": "OK", "pair_key": key}

def mark_active_pair(active, pair, purpose=None):
    key = _pair_key(pair, purpose)
    if isinstance(active, set):
        active.add(key)
    elif isinstance(active, dict):
        active[key] = True
    return key


# ----------------------------------------------------------------------------- reservation TTL / expiry
def reservation_expired(reservation, now_ts):
    """Deterministic TTL check over an EXPLICIT now_ts (never a module clock). Uses created_ts+ttl_seconds if
    present, else compares an ISO expires_at only when the caller passes a comparable epoch via created_ts."""
    if not isinstance(reservation, dict):
        return False
    ttl = reservation.get("ttl_seconds")
    created = reservation.get("created_ts")
    if isinstance(created, (int, float)) and isinstance(ttl, (int, float)):
        return float(now_ts) >= float(created) + float(ttl)
    return False


# ----------------------------------------------------------------------------- §14.3 concurrent-accept policy
# For 1:1 fixed-time the second accept is exclusive (WITHDRAW the loser); multiple-conversations allows several
# MUTUAL; dating requires manual confirm (no auto-commit); group/event use reservation/capacity (pilot-off).
_MULTIPLE = {"policy": "multiple_conversations", "exclusive": False, "auto_commit": True,
             "note": "several MUTUAL matches may coexist; no auto-plan"}
def concurrent_accept_policy(intent):
    """Classify how simultaneous accepts on ONE intent must be resolved. DEFAULT is multiple_conversations
    (exclusive:False) so the existing negotiate path — which records every agreed candidate — is byte-identical;
    exclusivity ONLY engages for a genuine 1:1 fixed-time intent, which no existing fixture constructs."""
    intent = intent or {}
    goal = (intent.get("goal") or {})
    purpose = str(goal.get("purpose") or intent.get("purpose") or "").lower()
    fmt = str(intent.get("format") or goal.get("format") or "").lower()
    time_s = str(intent.get("time") or (intent.get("payload") or {}).get("time") or "").lower()
    fixed_time = bool(time_s) and not any(w in time_s for w in ("flex", "any", "whenever", "later", "tbd", "open"))
    is_1to1 = ("1:1" in fmt) or ("one-on-one" in fmt) or ("one on one" in fmt)
    is_group = ("group" in fmt) or ("small group" in fmt and not is_1to1)
    is_event = ("event" in fmt) or ("event" in purpose)
    if "dat" in purpose or "romance" in purpose or "romantic" in purpose:
        return {"policy": "dating_manual_confirm", "exclusive": True, "auto_commit": False,
                "note": "romantic: manual confirmation required; agent may not auto-commit a plan"}
    if is_event:
        return {"policy": "event_capacity", "exclusive": False, "auto_commit": False,
                "note": "capacity-bound; pilot-disabled (§16)", "enabled": False}
    if is_group:
        return {"policy": "group_reservation", "exclusive": False, "auto_commit": False,
                "note": "quorum/reservation; pilot-disabled (§15)", "enabled": False}
    if is_1to1 and fixed_time:
        return {"policy": "one_to_one_fixed_time", "exclusive": True, "auto_commit": True,
                "note": "one slot: the first accept wins; a later concurrent accept is WITHDRAWN (SLOT_TAKEN)"}
    return dict(_MULTIPLE)

def claim_slot(taken, intent_id, claimant):
    """Shared per-intent slot for an exclusive (1:1 fixed-time) intent. `taken` is a dict {intent_id: winner}
    living in the caller's SESSION. First claim wins; a later DIFFERENT claimant loses with SLOT_TAKEN. The SAME
    claimant re-claiming is idempotent (won:True) — a retry of the winner is not a loss."""
    if not isinstance(taken, dict):
        return {"won": True, "error_code": "OK", "winner": claimant}
    iid = str(intent_id or "")
    cur = taken.get(iid)
    if cur is None:
        taken[iid] = claimant
        return {"won": True, "error_code": "OK", "winner": claimant}
    if str(cur) == str(claimant):
        return {"won": True, "error_code": "OK", "winner": cur}
    return {"won": False, "error_code": "SLOT_TAKEN", "winner": cur}


# ----------------------------------------------------------------------------- §14.4 race resolution table
# Eight canonical races -> a DETERMINISTIC terminal/next state + a coarse PUBLIC reason. leak:False always: the
# cross-agent surface (the envelope) shows only the opaque public_reason; the granular gate reason (blocked /
# private profile / not open to dating) stays ONLY in the owner's explain_match panel, never here.
_RACES = {
    # case: (entity, target_state, error_code, public_reason)
    "policy_revoked_before_accept": ("proposal", "POLICY_REVOKED", "POLICY_CHANGED", "no longer available"),
    "blocked_before_send":         ("proposal", "WITHDRAWN",      "POLICY_CHANGED", "no longer available"),
    "privacy_tightened":           ("proposal", "POLICY_REVOKED", "POLICY_CHANGED", "no longer available"),
    "slot_taken":                  ("proposal", "WITHDRAWN",      "SLOT_TAKEN",     "slot unavailable"),
    "duplicate_pair":              ("proposal", "WITHDRAWN",      "DUPLICATE_PAIR", "already in progress"),
    "duplicate_replay":            ("proposal", None,             "DUPLICATE",      "already processed"),
    "reservation_expired":         ("proposal", "EXPIRED",        "EXPIRED",        "expired"),
    "timezone_infeasible":         ("proposal", "DECLINED",       "TIME_INFEASIBLE","time not workable"),
}
RACE_CASES = tuple(_RACES.keys())

def resolve_race(case, current_state=None, entity="proposal"):
    """Map one of the 8 canonical §14.4 races to its deterministic outcome. Returns
    {case, entity, from, to, applied, error_code, public_reason, leak:False}. `applied` is True only if the
    target edge is legal from current_state (else the terminal is still reported but not force-applied — the
    caller keeps the object where it is and surfaces the code). Unknown case -> deny-safe OK/no-op."""
    spec = _RACES.get(str(case or ""))
    if not spec:
        return {"case": case, "entity": entity, "from": current_state, "to": current_state,
                "applied": False, "error_code": "OK", "public_reason": None, "leak": False}
    ent, to, code, reason = spec
    cur = current_state or initial_state(ent)
    applied = bool(to) and can_transition(ent, cur, to)
    return {"case": case, "entity": ent, "from": cur, "to": (to if applied else cur),
            "applied": applied, "error_code": code, "public_reason": reason, "leak": False}


# ----------------------------------------------------------------------------- introspection (tests/docs)
def summary():
    return {
        "states_version": STATES_VERSION,
        "machines": {k: {"n_states": len(v["states"]), "terminal": list(v["terminal"]), "enabled": v["enabled"]}
                     for k, v in STATE_MACHINES.items()},
        "error_codes": list(ERROR_CODES),
        "race_cases": list(RACE_CASES),
    }
