# -*- coding: utf-8 -*-
"""Kleal — typed agent protocol & outreach orchestration (spec §13).

The user agent does NOT hold free conversations with hundreds of LLMs: the Matching Exchange passes TYPED
events. This module is the deterministic, LLM-free spine of that protocol — the nine allowed actions, the
message envelope, the wave assignment, and the §13.3 autonomy-boundary guards. It imports NO model access
(no llm_client / MODEL_ID); the ONLY LLM call in the pipeline stays negotiate_one, which merely PHRASES a
decision whose accept/reject bit maps here to a typed action. Keyless, stdlib-only.
"""
import time

# ----------------------------------------------------------------------------- §13.1 the nine allowed actions
ACTIONS = ("ELIGIBILITY_PROBE", "PROPOSE_CONNECTION", "ASK_INFO", "COUNTER_TIME", "COUNTER_FORMAT",
           "ACCEPT", "DECLINE", "WITHDRAW", "EXPIRE")
ALLOWED_ACTIONS = frozenset(ACTIONS)

def is_action(a):
    return a in ALLOWED_ACTIONS

PROTOCOL_VERSION = "agent-protocol-13.0.0"

def type_action(card, in_to_send):
    """Classify a pre-check card into a typed §13.1 action, PURE over its EXISTING keys (never reads/writes
    name/agree/reason beyond substring inspection). A to_send member is a PROPOSE_CONNECTION; the cap
    overflow (detected by the 'queued for the next wave' reason substring — NOT by readiness, which stays
    open_now) is a wave-deferred probe that PASSED; every other decided card is a failed ELIGIBILITY_PROBE,
    with a counter_hint when the block is a negotiable time/format mismatch."""
    c = card if isinstance(card, dict) else {}
    if in_to_send:
        return {"action": "PROPOSE_CONNECTION", "passed": True, "counter_hint": None}
    reason = str(c.get("reason") or "").lower()
    rdy = str(c.get("readiness") or "")
    if "queued for the next wave" in reason:
        return {"action": "ELIGIBILITY_PROBE", "passed": True, "counter_hint": None, "wave_deferred": True}
    counter = None
    if rdy == "time_infeasible" or "feasible time slot" in reason:
        counter = "COUNTER_TIME"
    elif "proposals not accepted" in reason:
        counter = "COUNTER_FORMAT"
    return {"action": "ELIGIBILITY_PROBE", "passed": False, "counter_hint": counter}

_COUNTER_TIME_KW = ("time", "reschedule", "later", "tonight", "tomorrow", "another day", "evening", "earlier")
_COUNTER_FORMAT_KW = ("online", "voice", "video", "group", "1:1", "format", "call", "in person")

def map_decision_to_action(negotiate_result):
    """Map the LLM negotiate_one output {agree, reply} to a typed action (PURE — no model call). The LLM only
    phrases; the accept/reject/counter bit is the typed decision. agree -> ACCEPT; a decline that offers a
    different time/format -> COUNTER_TIME / COUNTER_FORMAT; otherwise DECLINE."""
    v = negotiate_result if isinstance(negotiate_result, dict) else {}
    if v.get("agree"):
        return "ACCEPT"
    reply = str(v.get("reply") or "").lower()
    if any(k in reply for k in _COUNTER_TIME_KW):
        return "COUNTER_TIME"
    if any(k in reply for k in _COUNTER_FORMAT_KW):
        return "COUNTER_FORMAT"
    return "DECLINE"

# ----------------------------------------------------------------------------- §13.1 message envelope
def build_envelope(proposal, snapshot, purpose=None, disclosure=None, action="PROPOSE_CONNECTION",
                   structured_fields=None, rendering_key=None, now=None):
    """Wrap a kc.build_proposal object into the full §13.1 typed message envelope. NEVER re-derives
    proposal_id / idempotency_key (they come from the proposal) — only ADDS versions, purpose, disclosure
    scope, structured fields, a stable human-readable rendering KEY, and a per-message audit block."""
    proposal = proposal or {}
    snap = snapshot or {}
    now = float(now if now is not None else time.time())
    action = action if is_action(action) else "PROPOSE_CONNECTION"
    env = dict(proposal)                                  # keeps proposal_id/idempotency_key/payload/TTL/status
    env["protocol_version"] = PROTOCOL_VERSION
    env["action"] = action
    env["versions"] = {"intent": snap.get("intent_version") or proposal.get("intent_id"),
                       "profile_capsule": snap.get("config_version"),   # the scored capsule's config version
                       "policy": snap.get("policy_version")}
    env["purpose"] = purpose
    env["disclosure_scope"] = disclosure if disclosure is not None else proposal.get("allowed_disclosure")
    env["structured_fields"] = structured_fields if structured_fields is not None else proposal.get("payload")
    env["rendering_key"] = rendering_key or ("proposal.%s" % action.lower())
    env["audit"] = {"actor": proposal.get("from_user") or "me", "action": action,
                    "ts": now, "correlation": proposal.get("proposal_id")}
    return env

# ----------------------------------------------------------------------------- §13.2 wave orchestration
def assign_wave(card, ctx=None):
    """Assign a §13.2 wave to a card. Wave 1 = a top open_now candidate proposed now; Wave 2 = the cap
    overflow (deferred, re-sent on refusal/timeout/capacity — the ASSIGNMENT is deterministic, the async
    re-send trigger is infra); Wave 3 = urgent intent or user-allowed expansion. (Wave 0 = 'show the slate
    first' is the separate /match path, upstream of the send boundary.)"""
    c = card if isinstance(card, dict) else {}
    ctx = ctx or {}
    if "queued for the next wave" in str(c.get("reason") or "").lower():
        return {"wave": 2, "size": "1-2", "trigger": "refusal/timeout/insufficient_capacity (assignment; async re-send = infra)"}
    if ctx.get("urgent") or ctx.get("expansion"):
        return {"wave": 3, "size": "up_to_3", "trigger": "urgent intent or user-allowed expansion"}
    return {"wave": 1, "size": "1-2", "trigger": "top candidates, high coverage, receiving=open_now"}

# ----------------------------------------------------------------------------- §13.3 autonomy boundaries
AUTONOMY_BOUNDARIES = {
    "can_auto": ["compile_draft_intent", "retrieval", "allowlisted_clarification",
                 "explanation_from_reason_keys", "send_within_pre_confirmed_outreach_policy"],
    "requires_consent": ["expand_hard_constraints", "reveal_new_sensitive_field", "agree_to_dating_contact",
                         "confirm_payment_booking_or_private_venue", "accept_multiple_conflicting_plans",
                         "reinterpret_refusal_as_try_later"],
    "note": "boundaries in requires_consent are ENFORCED: expand-hard-constraints + dating behind /confirm "
            "(kc/ki.apply_confirmation), reveal-sensitive behind the disclosure clamp, and the three below by guards.",
}

_PAYMENT_BOOKING_KEYS = ("confirm_payment", "payment", "charge", "booking", "reservation_confirm",
                         "exact_venue", "private_venue", "venue_address")

def guard_no_payment_booking_venue_confirm(envelope):
    """§13.3: the agent may NOT auto-confirm a payment, a booking, or an exact private venue. Absent-permissive:
    OK unless the message actually carries such a confirmation field. Returns (ok, reason)."""
    env = envelope if isinstance(envelope, dict) else {}
    fields = env.get("structured_fields") if isinstance(env.get("structured_fields"), dict) else {}
    for k, v in list(env.items()) + list(fields.items()):
        if str(k).lower() in _PAYMENT_BOOKING_KEYS and v:
            return False, "requires user consent: %s (payment/booking/venue not auto-confirmed)" % k
    return True, None

def guard_no_conflicting_plans(candidate_name, active_plans, new_window=None):
    """§13.3: the agent may NOT auto-accept multiple CONFLICTING plans. Absent-permissive: OK unless an
    existing active plan's window overlaps the new one. active_plans = [{window:{from,until}, ...}]. Returns
    (ok, reason)."""
    if not new_window or not isinstance(new_window, dict):
        return True, None
    nf, nu = new_window.get("from"), new_window.get("until")
    if nf is None or nu is None:
        return True, None
    for p in (active_plans or []):
        w = (p or {}).get("window") or {}
        pf, pu = w.get("from"), w.get("until")
        if pf is not None and pu is not None and not (nu <= pf or nf >= pu):
            return False, "requires user consent: conflicts with an existing plan window"
    return True, None

def guard_no_refusal_retry(declined_recently):
    """§13.3: a refusal must NOT be silently reinterpreted as 'try later'. Absent-permissive: OK unless this
    recipient declined within the cooldown (declined_recently is truthy). Returns (ok, reason). (The declined
    cooldown is ALSO a hard gate; this is the explicit protocol-level guard.)"""
    if declined_recently:
        return False, "requires user consent: recipient declined recently — not a silent 'try later'"
    return True, None
