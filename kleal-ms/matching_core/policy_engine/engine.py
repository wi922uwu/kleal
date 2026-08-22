# -*- coding: utf-8 -*-
"""§8 Policy Engine — единый tri-state вердикт (ALLOW/BLOCK/REVIEW).

Scoring начинается ТОЛЬКО после ALLOW (§8). BLOCK → кандидат не попадает ни в ranking, ни в
explanation, ни в agent probe (C#5: safety block исключает до feature building). REVIEW → виден в
discovery, но personal proposal запрещён до ответа пользователя / проверки сервиса безопасности.
"""
from .gates import CANONICAL_GATES, ALLOW, BLOCK, REVIEW
from . import gates as _G

# Аудит #3: дешёвый hard-eligibility subset — гоняется по ВСЕМУ пулу ДО budget truncation, чтобы бюджет
# не отрезал допустимых кандидатов раньше policy. Только definite-hard field-гейты (без feature building).
HARD_ELIGIBILITY_GATES = (_G.account_status, _G.mutual_block, _G.safety_restrictions, _G.age_legal,
                          _G.intent_mode_isolation, _G.language_feasibility, _G.location_policy, _G.capacity)


def hard_blocked(intent, candidate, ctx=None):
    """True, если кандидат получает definite BLOCK от cheap hard-eligibility subset (для префильтра)."""
    ctx = ctx or {}
    for gate in HARD_ELIGIBILITY_GATES:
        if gate(intent, candidate, ctx)[0] == BLOCK:
            return True
    return False


def hard_prefilter(intent, pool, ctx=None):
    """Аудит #3: cheap hard-eligibility prefilter по ВСЕМУ пулу ДО retrieval-бюджета. Убирает definite-BLOCK
    кандидатов; ALLOW/REVIEW проходят (полная policy.evaluate — позже, на retrieved-срезе). Так budget
    режет уже ДОПУСТИМЫЙ пул, а не теряет хороших кандидатов за хвостом заблокированных.
    Возвращает (eligible_pool, stats)."""
    ctx = ctx or {}
    eligible = [c for c in (pool or []) if not hard_blocked(intent, c, ctx)]
    return eligible, {"input": len(pool or []), "eligible": len(eligible),
                      "dropped_hard": len(pool or []) - len(eligible)}


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
