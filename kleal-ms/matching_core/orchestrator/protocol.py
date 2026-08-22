# -*- coding: utf-8 -*-
"""§13 Agent protocol и outreach orchestration.

Пользовательский агент НЕ ведёт свободные разговоры с сотнями LLM (§13, §23.2 п.7). Matching Exchange
передаёт ТИПИЗИРОВАННЫЕ события с версиями/purpose/TTL/idempotency. Массовая рассылка запрещена (§13.2).
"""

# §13.1 разрешённые действия (замкнутый набор).
ALLOWED_ACTIONS = ("ELIGIBILITY_PROBE", "PROPOSE_CONNECTION", "ASK_INFO", "COUNTER_TIME",
                   "COUNTER_FORMAT", "ACCEPT", "DECLINE", "WITHDRAW", "EXPIRE")

# §13.2 волны предложений.
WAVES = {
    0: {"size": 0, "trigger": "show_slate_to_user_if_choice_needed"},
    1: {"size": 2, "trigger": "top_candidates_high_coverage_open_now"},
    2: {"size": 2, "trigger": "after_decline_timeout_or_low_capacity"},
    3: {"size": 3, "trigger": "user_allowed_expansion_or_urgent"},
}
MAX_CONCURRENT_PERSONAL = 3                        # §13.2: один intent -> не более 3 одновременных personal proposals

# §13.3 границы автономности.
AUTO_ALLOWED = frozenset({"compile_draft", "retrieval", "allowlisted_clarification",
                          "explanation_from_reason_keys", "send_within_confirmed_policy"})
CONSENT_REQUIRED = frozenset({"expand_hard_constraints", "reveal_new_sensitive_field", "dating_contact",
                              "confirm_payment_booking_venue", "accept_multiple_conflicting_plans",
                              "reinterpret_decline_as_later"})


class ProtocolViolation(Exception):
    pass


def build_envelope(action, *, proposal_id, idempotency_key, intent_version, profile_version,
                   policy_version, purpose, disclosure_scope, structured_fields=None, ttl_sec=720 * 60,
                   rendering_key=None, audit=None):
    """§13.1: типизированное сообщение протокола. Свободный текст запрещён — только structured fields
    + rendering_key (human copy отделён от системного решения, §23.3)."""
    if action not in ALLOWED_ACTIONS:
        raise ProtocolViolation("action not allowed: %r" % action)
    return {
        "action": action, "proposal_id": proposal_id, "idempotency_key": idempotency_key,
        "versions": {"intent": intent_version, "profile": profile_version, "policy": policy_version},
        "purpose": purpose, "disclosure_scope": disclosure_scope,
        "structured_fields": structured_fields or {}, "ttl_sec": ttl_sec,
        "rendering_key": rendering_key or ("render.%s" % action.lower()),
        "audit": audit or {},
    }


def next_wave(current_wave, *, declined_or_timeout=False, expansion_allowed=False, urgent=False):
    """Определить следующую волну (§13.2)."""
    if current_wave == 0:
        return 1
    if current_wave == 1 and declined_or_timeout:
        return 2
    if current_wave == 2 and (expansion_allowed or urgent):
        return 3
    return None                                    # дальше волн нет


def check_wave_limit(active_personal_proposals):
    """§13.2: не более 3 одновременных personal proposals; иначе ProtocolViolation (защита от mass outreach)."""
    if active_personal_proposals > MAX_CONCURRENT_PERSONAL:
        raise ProtocolViolation("mass outreach forbidden: %d concurrent personal proposals" % active_personal_proposals)
    return True


def can_auto(operation):
    """§13.3: агент может делать автоматически."""
    return operation in AUTO_ALLOWED


def requires_consent(operation):
    """§13.3: агент НЕ может без отдельного согласия."""
    return operation in CONSENT_REQUIRED
