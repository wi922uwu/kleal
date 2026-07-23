# -*- coding: utf-8 -*-
"""Вердикт#27 — координация нескольких активных intent одного пользователя.

Пользователь одновременно может искать теннис, практиковать испанский, быть открыт к кофе, искать
проф-знакомства. Нужно: не смешивать contextual profiles; какой intent даёт обратную взаимность;
можно ли предложить человеку ДРУГОЙ его intent; лимит активных intent; приоритет + TTL. Опасно брать
«произвольный» активный запрос для обратной оценки — нужен СОВМЕСТИМЫЙ по purpose intent.
"""
from ..contracts import intent as IC

MAX_ACTIVE_INTENTS = 5                       # лимит одновременно активных intent (антиспам/ясность)

# purpose каждого intent (для изоляции contextual profile).
_TYPE2PURPOSE = {"dating": "dating", "social_meet": "friendship", "walk": "friendship",
                 "culture_event": "friendship", "watch_together": "friendship", "games": "games",
                 "sport_activity": "sport", "professional_networking": "networking",
                 "coworking": "networking", "language_exchange": "language"}


def _purpose_of(intent):
    f = IC.flat(intent) if intent.get("identity") else intent
    return f.get("purpose") or _TYPE2PURPOSE.get(f.get("type") or f.get("domain"), "friendship")


def active_intents(intents, now=None):
    """Только участвующие в ranking (active/searching, не истёкшие) — Вердикт#10/#27."""
    out = []
    for it in intents or []:
        if it.get("identity") and not IC.participates_in_ranking(it, now):
            continue
        out.append(it)
    return out


def enforce_limit(intents, now=None, *, limit=MAX_ACTIVE_INTENTS):
    """Вердикт#27: лимит активных intent. Возвращает (kept[], overflow[]) по приоритету (свежесть/urgency)."""
    act = active_intents(intents, now)
    ranked = sorted(act, key=_priority_key, reverse=True)
    return ranked[:limit], ranked[limit:]


def _priority_key(intent):
    f = IC.flat(intent) if intent.get("identity") else intent
    urgency = {"now": 3, "today": 2, "soon": 1}.get((f.get("time") or {}).get("urgency"), 0)
    created = (f.get("lifecycle") or {}).get("created_at") or 0
    return (urgency, created)


def select_for_reverse_reciprocity(searcher_intent, candidate_intents, now=None):
    """Вердикт#27: для обратной взаимности брать НЕ произвольный активный запрос кандидата, а СОВМЕСТИМЫЙ
    по purpose с запросом искателя. Возвращает лучший совместимый intent кандидата или None."""
    want = _purpose_of(searcher_intent)
    compatible = [it for it in active_intents(candidate_intents, now) if _purpose_of(it) == want]
    if not compatible:
        return None
    return sorted(compatible, key=_priority_key, reverse=True)[0]


def may_offer_other_intent(candidate, other_intent):
    """Вердикт#27: можно ли предложить человеку ДРУГОЙ его intent — только если receiving policy этого
    purpose разрешает (не смешиваем контексты молча). Возвращает bool."""
    from ..contracts import receiving_policy as RP
    pol = candidate.get("receiving_purpose_policy")
    if not pol:
        return False                          # нет явного согласия по этому purpose -> нельзя
    ok, _ = RP.receiving_decision(pol, _purpose_of(other_intent), channel="direct_invites")
    return ok


def contextual_profile_for(intent, profiles_by_purpose):
    """Вердикт#27: для каждого intent — СВОЙ contextual profile (данные не смешиваются)."""
    return (profiles_by_purpose or {}).get(_purpose_of(intent))
