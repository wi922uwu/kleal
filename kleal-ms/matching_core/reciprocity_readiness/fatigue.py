# -*- coding: utf-8 -*-
"""Вердикт#17 — перегрузка кандидата не исчерпывается числом открытых приглашений.

Человек с пятью приглашениями и десятками пассивных рекомендаций формально «не перегружен», но
фактически испытывает fatigue. Ограничиваем по нескольким осям: приглашений в сутки, от одного
пользователя, по одному intent, слабых T2/T3, повторных показов, в тихие часы, по разным purpose,
одновременных активных планов.
"""

# провизорные лимиты (Вердикт#20 — вынести в config при калибровке).
LIMITS = {
    "per_24h": 4, "per_sender_24h": 1, "per_intent": 1, "weak_tier_24h": 2,
    "impressions_24h": 12, "quiet_hours": 0, "per_purpose_24h": 3, "active_plans": 2,
}
_WEAK_TIERS = frozenset({"T2", "T3"})


def fatigue_state(load, *, tier=None, in_quiet_hours=False, limits=None):
    """Вердикт#17: многомерная проверка перегрузки. load — снимок счётчиков получателя. Возвращает
    {overloaded, reasons[], blocking_axis|None}. Любая пробитая ось делает outreach нежелательным."""
    L = dict(LIMITS); L.update(limits or {})
    reasons = []

    def hit(axis, val, lim):
        if lim is not None and int(val or 0) >= int(lim):
            reasons.append("%s>=%s" % (axis, lim))

    hit("per_24h", load.get("received_24h"), L["per_24h"])
    hit("per_sender_24h", load.get("from_sender_24h"), L["per_sender_24h"])
    hit("per_intent", load.get("for_intent"), L["per_intent"])
    hit("per_purpose_24h", load.get("for_purpose_24h"), L["per_purpose_24h"])
    hit("impressions_24h", load.get("impressions_24h"), L["impressions_24h"])
    hit("active_plans", load.get("active_plans"), L["active_plans"])
    if tier in _WEAK_TIERS:
        hit("weak_tier_24h", load.get("weak_tier_24h"), L["weak_tier_24h"])
    if in_quiet_hours:
        reasons.append("quiet_hours")                 # тихие часы: не докучаем даже под лимитами
    return {"overloaded": bool(reasons), "reasons": reasons,
            "blocking_axis": reasons[0] if reasons else None}


def may_send(load, *, tier=None, in_quiet_hours=False, limits=None):
    """True, если по всем осям fatigue outreach допустим."""
    return not fatigue_state(load, tier=tier, in_quiet_hours=in_quiet_hours, limits=limits)["overloaded"]
