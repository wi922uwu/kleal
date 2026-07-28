# -*- coding: utf-8 -*-
"""§4.3 Intent schema (+ §5.3 минимально достаточный intent, §4.3 Lifecycle/TTL).

Intent — текущая, ограниченная по времени задача (не evergreen goal). Версия увеличивается при ЛЮБОМ
изменении, влияющем на поиск (§4.3). Истёкший intent не участвует в ranking (§4.3 Lifecycle).
"""

# 11 канонических блоков §4.3.
INTENT_BLOCKS = ("identity", "goal", "time", "location", "mode", "target",
                 "social_context", "domain_details", "fallback", "disclosure", "lifecycle")

# Поля, изменение которых влияет на поиск -> обязателен bump версии (§4.3 identity rule).
SEARCH_AFFECTING = ("domain", "activity", "purpose", "topics", "time", "location", "mode",
                    "format", "target", "role", "requiredLanguages", "radiusKm")

# Вердикт#10 + Аудит#15: ЕДИНЫЙ канонический набор lifecycle-состояний intent (11). Это single source
# набора состояний; `orchestrator.state_machines` строит автомат intent_lifecycle РОВНО над ним и при
# импорте проверяет, что не разошёлся (двух независимых списков состояний больше нет).
LIFECYCLE_STATES = ("draft", "clarification_required", "active", "searching", "paused", "reserved",
                    "matched", "planned", "completed", "expired", "cancelled")
_ACTIVE_LIFECYCLE = frozenset({"active", "searching", "paused", "reserved"})

# Аудит#15: авторитет состояния — state machine. lifecycle_state() ниже — ТОЛЬКО read-only проекция;
# менять состояние можно ЛИШЬ через orchestrator.state_machines.advance_intent_lifecycle (assert_transition).
LIFECYCLE_STATE_IS_PROJECTION = True
LIFECYCLE_AUTHORITY = "orchestrator.state_machines.intent_lifecycle"


def lifecycle_state(intent, now=None):
    """Аудит#15: READ-ONLY ПРОЕКЦИЯ авторитетного состояния (transitions — только через state_machines).
    Читает сохранённое `lifecycle.state` (обновляемое ТОЛЬКО автоматом) и накладывает TTL-overlay: истёкший
    по времени intent проецируется как 'expired'. Сам по себе состояние НЕ меняет."""
    if now is not None and is_expired(intent, now):
        return "expired"
    lc = (intent.get("lifecycle") or {})
    st = lc.get("state") or intent.get("identity", {}).get("status")
    return st if st in LIFECYCLE_STATES else "active"


def participates_in_ranking(intent, now=None):
    """Вердикт#10 + §4.3: в ranking участвуют только НЕ истёкшие активные интенты (не paused-навсегда/
    matched/completed/cancelled). Устаревшие запросы не рекомендуются."""
    st = lifecycle_state(intent, now)
    return st in ("active", "searching")


def build_intent(intent_id, user_id, domain, *, activity=None, purpose=None, topics=None,
                 time=None, location=None, mode="offline", fmt="1:1", target=None,
                 social_context=None, domain_details=None, fallback=None, disclosure=None,
                 created_at=None, expires_at=None, search_budget=None, version=1, status="active",
                 expansion_policy=None):
    fb = fallback or {"allowed_dimensions": [], "consent": {}}
    if expansion_policy:                               # Вердикт#9: политика расширения на самом intent
        fb = dict(fb); fb["expansion_policy"] = expansion_policy
    return {
        "identity": {"intent_id": intent_id, "user_id": user_id, "version": int(version),
                     "domain": domain, "status": status},
        "goal": {"activity": activity, "purpose": purpose, "topics": list(topics or [])},
        "time": time or {"windows": [], "duration": None, "recurrence": None, "urgency": None},
        "location": location or {"city": None, "coarse_cell": None, "radiusKm": None, "safe_zones": []},
        "mode": {"mode": mode, "format": fmt},
        "target": target or {"directed_preferences": None, "required_roles": None, "level": None},
        "social_context": social_context or {"vibe": None, "pressure": None, "style": None},
        "domain_details": domain_details or {},
        "fallback": fb,
        "disclosure": disclosure or {"stages": {}},
        "lifecycle": {"created_at": created_at, "expires_at": expires_at, "search_budget": search_budget},
    }


def flat(intent):
    """Плоский вид для скоринга/гейтов (совместимо с движком): domain/topics/mode/... на верхнем уровне."""
    idn, goal = intent.get("identity", {}), intent.get("goal", {})
    return {
        "intent_id": idn.get("intent_id"), "user_id": idn.get("user_id"), "version": idn.get("version"),
        "domain": idn.get("domain"), "status": idn.get("status"),
        "type": idn.get("domain"), "activity": goal.get("activity"), "purpose": goal.get("purpose"),
        "topics": goal.get("topics") or [], "mode": intent.get("mode", {}).get("mode"),
        "format": intent.get("mode", {}).get("format"),
        "time": intent.get("time", {}), "location": intent.get("location", {}),
        "radiusKm": (intent.get("location") or {}).get("radiusKm"),
        "target": intent.get("target", {}), "role": (intent.get("target") or {}).get("required_roles"),
        "requiredLanguages": (intent.get("domain_details") or {}).get("requiredLanguages") or [],
        "domain_details": intent.get("domain_details", {}), "fallback": intent.get("fallback", {}),
        "disclosure": intent.get("disclosure", {}), "lifecycle": intent.get("lifecycle", {}),
        "expansion_policy": (intent.get("fallback") or {}).get("expansion_policy"),   # Вердикт#9
    }


def bump_version(intent):
    """§4.3: любое изменение, влияющее на поиск, увеличивает version."""
    intent = dict(intent)
    intent["identity"] = dict(intent.get("identity", {}))
    intent["identity"]["version"] = int(intent["identity"].get("version", 1)) + 1
    return intent


def is_expired(intent, now):
    """§4.3 Lifecycle: истёкший intent не участвует в ranking."""
    exp = (intent.get("lifecycle") or {}).get("expires_at")
    if exp is None:
        return False
    try:
        return float(now) >= float(exp)
    except (TypeError, ValueError):
        return False


def validate_intent(intent):
    idn = intent.get("identity") or {}
    if not idn.get("intent_id") or not idn.get("user_id"):
        raise ValueError("intent.identity missing intent_id/user_id")
    if not idn.get("domain"):
        raise ValueError("intent.identity.domain required")
    if not isinstance(idn.get("version"), int) or idn["version"] < 1:
        raise ValueError("intent.identity.version must be int >= 1")
    return True


def minimal_intent_ok(intent):
    """§5.3 минимально достаточный intent: domain+activity/purpose, время-или-explicit-none, mode+format,
    город/online-или-fallback, disclosure, TTL. Возвращает (ok, missing[])."""
    f = flat(intent)
    missing = []
    if not f.get("domain"):
        missing.append("domain")
    if not (f.get("activity") or f.get("purpose") or f.get("topics")):
        missing.append("activity/purpose")
    t = f.get("time") or {}
    if not (t.get("windows") or t.get("flexible") or t.get("no_specific_time")):
        missing.append("time-or-explicit-none")
    if not f.get("mode"):
        missing.append("mode")
    loc = f.get("location") or {}
    if not (loc.get("city") or f.get("mode") == "online" or (f.get("fallback") or {}).get("allowed_dimensions")):
        missing.append("city/online/fallback")
    if (intent.get("lifecycle") or {}).get("expires_at") is None:
        missing.append("ttl")
    return (len(missing) == 0, missing)
