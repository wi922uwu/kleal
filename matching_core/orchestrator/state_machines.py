# -*- coding: utf-8 -*-
"""§14.1 Transaction state machines — Intent / Proposal / Match / Plan.

Все переходы транзакционны, идемпотентны и повторно проверяют policy/TTL/capacity/версии (§0, §14.2).
`assert_transition` — единственный разрешённый способ смены состояния (B.2 state_machine.assert_transition).
"""


class InvalidTransition(Exception):
    pass


# from_state -> набор допустимых to_state. Терминальные состояния — пустой набор.
MACHINES = {
    "intent": {
        "DRAFT": {"CONFIRMED", "CANCELLED"},
        "CONFIRMED": {"SEARCHING", "CANCELLED", "EXPIRED"},
        "SEARCHING": {"WAITING", "SATISFIED", "EXPIRED", "CANCELLED"},
        "WAITING": {"SEARCHING", "SATISFIED", "EXPIRED", "CANCELLED"},
        "SATISFIED": set(), "EXPIRED": set(), "CANCELLED": set(),
    },
    # Вердикт#10: полный жизненный цикл intent (11 состояний). TTL и active/paused/expired нужны уже сейчас.
    "intent_lifecycle": {
        "draft": {"clarification_required", "active", "cancelled"},
        "clarification_required": {"active", "cancelled", "expired"},
        "active": {"searching", "paused", "cancelled", "expired"},
        "searching": {"reserved", "matched", "paused", "active", "cancelled", "expired"},
        "paused": {"active", "searching", "cancelled", "expired"},
        "reserved": {"matched", "searching", "cancelled", "expired"},
        "matched": {"planned", "cancelled", "expired"},
        "planned": {"completed", "cancelled", "expired"},
        "completed": set(), "expired": set(), "cancelled": set(),
    },
    "proposal": {
        "CREATED": {"RESERVED", "WITHDRAWN", "EXPIRED"},
        "RESERVED": {"SENT", "WITHDRAWN", "EXPIRED", "POLICY_REVOKED"},
        "SENT": {"VIEWED", "ACCEPTED", "DECLINED", "COUNTERED", "WITHDRAWN", "EXPIRED", "POLICY_REVOKED"},
        "VIEWED": {"ACCEPTED", "DECLINED", "COUNTERED", "WITHDRAWN", "EXPIRED", "POLICY_REVOKED"},
        "ACCEPTED": set(), "DECLINED": set(), "COUNTERED": set(),
        "WITHDRAWN": set(), "EXPIRED": set(), "POLICY_REVOKED": set(),
    },
    "match": {
        "PENDING_DISCLOSURE": {"MUTUAL", "CANCELLED", "SAFETY_CLOSED"},
        "MUTUAL": {"CHAT_OPEN", "CANCELLED", "SAFETY_CLOSED"},
        "CHAT_OPEN": {"PLANNING", "CANCELLED", "SAFETY_CLOSED"},
        "PLANNING": {"PLANNED", "CANCELLED", "SAFETY_CLOSED"},
        "PLANNED": {"COMPLETED", "CANCELLED", "SAFETY_CLOSED"},
        "COMPLETED": set(), "CANCELLED": set(), "SAFETY_CLOSED": set(),
    },
    "plan": {
        "DRAFT": {"PROPOSED", "CANCELLED"},
        "PROPOSED": {"PARTIALLY_CONFIRMED", "CONFIRMED", "CANCELLED"},
        "PARTIALLY_CONFIRMED": {"CONFIRMED", "CANCELLED"},
        "CONFIRMED": {"CHANGED", "COMPLETED", "CANCELLED", "NO_SHOW"},
        "CHANGED": {"CONFIRMED", "CANCELLED"},
        "COMPLETED": set(), "CANCELLED": set(), "NO_SHOW": set(),
    },
}


def states(machine):
    return set(MACHINES[machine].keys())


def is_terminal(machine, state):
    return not MACHINES[machine].get(state)


def can_transition(machine, frm, to):
    if machine not in MACHINES:
        raise ValueError("unknown machine: %r" % machine)
    if frm not in MACHINES[machine]:
        raise ValueError("unknown %s state: %r" % (machine, frm))
    return to in MACHINES[machine][frm]


def assert_transition(machine, frm, to):
    """Единственный санкционированный переход. Идемпотентно: frm==to для терминала не бросает (retry-safe)."""
    if frm == to:
        return True
    if not can_transition(machine, frm, to):
        raise InvalidTransition("%s: %s -> %s is not allowed" % (machine, frm, to))
    return True


def next_states(machine, frm):
    return set(MACHINES[machine].get(frm, set()))
