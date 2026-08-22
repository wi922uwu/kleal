# -*- coding: utf-8 -*-
"""Вердикт#4 — решение «можно ли обратиться к кандидату» НЕ отдаётся LLM.

Если LLM на финальном этапе сам решает, «согласен» ли агент кандидата, возникает скрытый второй скоринг:
непрозрачный, недетерминированный, зависящий от формулировки приглашения, предвзятый, невоспроизводимый.
Поэтому решение строится ТОЛЬКО из детерминированных источников (receiving policy, readiness, purpose,
активные предпочтения, лимиты, deterministic policy, явное действие пользователя когда нужно).

LLM РАЗРЕШЕНО: составить приглашение, кратко объяснить предложение, извлечь структурированное решение
пользователя, проверить достаточность данных. LLM ЗАПРЕЩЕНО: решать, можно ли обратиться, принимать/
отклонять кандидата «по впечатлению», переставлять кандидатов, считать score.
"""

LLM_ALLOWED_ROLES = ("compose_invitation", "explain_proposal", "extract_user_decision", "check_data_sufficiency")
LLM_FORBIDDEN_ROLES = ("decide_agent_agreement", "accept_or_reject_by_impression", "reorder_candidates",
                       "compute_score", "override_hard_gate")


class LLMBoundaryViolation(Exception):
    pass


def assert_llm_role(role):
    """Guard: любой вызов LLM внутри matching обязан объявить роль из allowlist. forbidden → исключение."""
    if role in LLM_FORBIDDEN_ROLES:
        raise LLMBoundaryViolation("LLM role not allowed in matching decisions: %r" % role)
    if role not in LLM_ALLOWED_ROLES:
        raise LLMBoundaryViolation("unknown LLM role: %r" % role)
    return True


def can_reach_candidate(*, receiving_eligible, readiness, purpose_ok, active_prefs_ok,
                        within_limits, deterministic_policy, requires_explicit_user_action=False,
                        user_action_taken=False):
    """Детерминированное решение можно ли обратиться. Никакого «мнения LLM».
    Возвращает {allowed, requires_user_action, basis, blockers}.

      receiving_eligible   — receiving policy разрешает этот тип предложения (§4.4);
      readiness            — состояние из readiness.py ('open_now'/'open_later'/'passive_discovery'/...);
      purpose_ok           — purpose binding не нарушен (§8.3);
      active_prefs_ok      — активные предпочтения кандидата допускают этот запрос;
      within_limits        — лимиты (fatigue/budget) не превышены;
      deterministic_policy — итог gate-движка ('ALLOW'/'BLOCK'/'REVIEW');
      requires_explicit_user_action — для этого шага нужно явное действие пользователя (напр. dating)."""
    blockers = []
    if deterministic_policy == "BLOCK":
        blockers.append("policy_block")
    if deterministic_policy == "REVIEW":
        blockers.append("policy_review")
    if not receiving_eligible:
        blockers.append("receiving_not_eligible")
    if not purpose_ok:
        blockers.append("purpose_mismatch")
    if not active_prefs_ok:
        blockers.append("active_prefs_disallow")
    if not within_limits:
        blockers.append("limits_exceeded")
    # passive_discovery/busy/paused → нет personal outreach (только подборка)
    if readiness not in ("open_now", "open_later"):
        blockers.append("not_ready_for_outreach")

    basis = ["receiving_policy", "readiness", "purpose_binding", "active_preferences",
             "limits", "deterministic_policy"]
    if blockers:
        return {"allowed": False, "requires_user_action": False, "basis": basis, "blockers": blockers}
    if requires_explicit_user_action and not user_action_taken:
        return {"allowed": False, "requires_user_action": True, "basis": basis + ["explicit_user_action"],
                "blockers": ["awaiting_user_confirmation"]}
    return {"allowed": True, "requires_user_action": False, "basis": basis, "blockers": []}
