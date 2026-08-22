# -*- coding: utf-8 -*-
"""§8.2 Точки обязательной повторной проверки policy.

Eligibility НЕ вечное свойство пары. Если состояние изменилось, операция завершается предсказуемым
кодом `POLICY_CHANGED`, а не молча продолжает старую транзакцию (C#6: privacy между SENT и ACCEPT).
"""
from .engine import evaluate, ALLOW

# §8.2 — семь обязательных чекпоинтов.
CHECKPOINTS = (
    "before_slate",            # 1. перед добавлением в slate
    "before_send",             # 2. перед отправкой proposal
    "profile_open_after_delay",  # 3. открытие профиля после задержки
    "on_accept",               # 4. при принятии proposal
    "before_chat",             # 5. перед созданием общего чата
    "before_reveal_location",  # 6. перед раскрытием точного места/контактов
    "on_state_change",         # 7. после privacy/block/suspension/age-mode/capacity/intent version
)

# Поля, изменение которых обязано вызвать re-check (§8.2 п.7).
_MONITORED = ("visibility", "blocksMe", "accountStatus", "suspended", "capacity", "safetyFlags", "datingOk")


def capture_baseline(candidate, intent):
    """Снимок отслеживаемых полей на момент предыдущего ALLOW (для сравнения на следующем чекпоинте)."""
    b = {k: candidate.get(k) for k in _MONITORED}
    b["intent_version"] = (intent.get("version") if isinstance(intent, dict) else None)
    return b


def revalidate(baseline, candidate, intent, ctx=None, checkpoint="before_send"):
    """Возвращает {ok, code, changed, decision}. code == POLICY_CHANGED, если:
      - текущий policy-вердикт больше НЕ ALLOW, ИЛИ
      - изменилось любое monitored-поле или версия intent (§8.2 п.7)."""
    if checkpoint not in CHECKPOINTS:
        raise ValueError("unknown revalidation checkpoint: %r" % checkpoint)
    changed = [k for k in _MONITORED if baseline.get(k) != candidate.get(k)]
    if baseline.get("intent_version") != (intent.get("version") if isinstance(intent, dict) else None):
        changed.append("intent_version")
    verdict = evaluate(intent, candidate, ctx)
    if changed or verdict["decision"] != ALLOW:
        return {"ok": False, "code": "POLICY_CHANGED", "changed": changed,
                "decision": verdict["decision"], "checkpoint": checkpoint}
    return {"ok": True, "code": "OK", "changed": [], "decision": ALLOW, "checkpoint": checkpoint}
