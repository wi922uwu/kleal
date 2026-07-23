# -*- coding: utf-8 -*-
"""§8 Policy Engine — единый tri-state вердикт (ALLOW/BLOCK/REVIEW).

Scoring начинается ТОЛЬКО после ALLOW (§8). BLOCK → кандидат не попадает ни в ranking, ни в
explanation, ни в agent probe (C#5: safety block исключает до feature building). REVIEW → виден в
discovery, но personal proposal запрещён до ответа пользователя / проверки сервиса безопасности.
"""
from .gates import CANONICAL_GATES, ALLOW, BLOCK, REVIEW


def evaluate(intent, candidate, ctx=None):
    """Прогоняет канонические gates В ПОРЯДКЕ. Первый BLOCK останавливает (кандидат исключён).
    Иначе если был REVIEW — REVIEW. Иначе ALLOW. Возвращает typed verdict (§23.3 typed I/O)."""
    ctx = ctx or {}
    review_reason = None
    per_gate = []
    for gate in CANONICAL_GATES:
        decision, reason = gate(intent, candidate, ctx)
        per_gate.append({"gate": gate.__name__, "decision": decision, "reason": reason})
        if decision == BLOCK:
            return {"decision": BLOCK, "reason": reason, "gate": gate.__name__,
                    "per_gate": per_gate, "policy_version": "pol-2.0.0"}
        if decision == REVIEW and review_reason is None:
            review_reason = (gate.__name__, reason)
    if review_reason:
        return {"decision": REVIEW, "reason": review_reason[1], "gate": review_reason[0],
                "per_gate": per_gate, "policy_version": "pol-2.0.0"}
    return {"decision": ALLOW, "reason": None, "gate": None,
            "per_gate": per_gate, "policy_version": "pol-2.0.0"}


def is_scorable(verdict):
    """§8: скорится только ALLOW. REVIEW виден в discovery, но не для personal outreach."""
    return verdict["decision"] == ALLOW


def is_discoverable(verdict):
    return verdict["decision"] in (ALLOW, REVIEW)


def prepare_snapshot(actor_id, purpose_id, *, policy_version="pol-2.0.0", config_version=None):
    """§8.2/§14.2: immutable снимок policy на момент старта search run — база для revalidation."""
    return {"actor_id": actor_id, "purpose_id": purpose_id, "policy_version": policy_version,
            "config_version": config_version}
