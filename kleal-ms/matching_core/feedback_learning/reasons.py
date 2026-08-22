# -*- coding: utf-8 -*-
"""Вердикт#18 — reason codes для отказа и дифференцированный кулдаун.

Один универсальный 7-дневный cooldown теряет информацию: «не могу сегодня» ≠ «не хочу общаться с этим
человеком» ≠ «не присылайте такие предложения» ≠ «заблокировать». Разные причины → разные последствия.
"""

# 8 канонических reason codes (§18).
REASON_CODES = ("not_now", "wrong_time", "wrong_activity", "wrong_format", "too_far",
                "not_interested_in_person", "do_not_suggest_again", "safety_block")

# последствие каждого кода: scope (что именно приглушается) + cooldown (сек) + флаги.
# scope: 'time_slot' (можно предложить другой слот) · 'activity' · 'format' · 'distance' ·
#        'person' (этого человека больше не показывать) · 'purpose' (отключить этот purpose) · 'safety'.
_DAY = 86400
CONSEQUENCE = {
    "not_now":                  {"scope": "time_slot", "cooldown_sec": _DAY,      "retry_other_slot": True},
    "wrong_time":               {"scope": "time_slot", "cooldown_sec": 2 * _DAY,  "retry_other_slot": True},
    "wrong_activity":           {"scope": "activity",  "cooldown_sec": 3 * _DAY,  "retry_other_activity": True},
    "wrong_format":             {"scope": "format",    "cooldown_sec": 3 * _DAY,  "retry_other_format": True},
    "too_far":                  {"scope": "distance",  "cooldown_sec": 3 * _DAY,  "retry_if_closer": True},
    "not_interested_in_person": {"scope": "person",    "cooldown_sec": 365 * _DAY, "never_show_person": True},
    "do_not_suggest_again":     {"scope": "purpose",   "cooldown_sec": 365 * _DAY, "disable_purpose": True},
    "safety_block":             {"scope": "safety",    "cooldown_sec": 3650 * _DAY, "route_to_safety": True,
                                 "never_show_person": True},
}


def consequence(reason_code):
    """Вердикт#18: последствие отказа по reason code. Неизвестный код -> консервативный not_now."""
    return dict(CONSEQUENCE.get(reason_code, CONSEQUENCE["not_now"]))


def cooldown_until(reason_code, now):
    """Момент, до которого пара/purpose/слот приглушены, исходя из reason code."""
    return float(now) + consequence(reason_code)["cooldown_sec"]


def suppress_scope(reason_code):
    """Что именно приглушается: time_slot/activity/format/distance/person/purpose/safety.
    Позволяет НЕ прятать человека, когда отказ был лишь про время/формат/дистанцию."""
    return consequence(reason_code)["scope"]


def is_person_level_block(reason_code):
    """Скрывать ли самого человека (person/safety), а не только конкретное предложение."""
    c = consequence(reason_code)
    return bool(c.get("never_show_person"))


def routes_to_safety(reason_code):
    """Передавать ли в safety flow (§25/§18)."""
    return bool(consequence(reason_code).get("route_to_safety"))
