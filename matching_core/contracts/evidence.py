# -*- coding: utf-8 -*-
"""§4.1 Evidence object + §4.2 иерархия источников.

Каждый признак имеет источник. Все aliases/tags/taxonomy nodes из ОДНОЙ фразы делят общий
`evidence_id` — Feature Builder дедуплицирует их до агрегации (§4.1, acceptance test C#3: один raw
evidence не даёт вес одновременно exact entity + tag + category + embedding).
"""
import hashlib

# §4.2 Иерархия источников: приоритет 1 (сильнейший) … 7 (слабейший).
SOURCE_PRIORITY = {
    "current_intent_explicit": 1,   # явный ответ в текущем intent — побеждает всё в scope intent
    "confirmed_intent_summary": 2,  # подтверждённая пользователем сводка — контракт поиска/disclosure
    "current_context_granted": 3,   # локация/календарь/availability с разрешением; короткий TTL
    "stable_profile_explicit": 4,   # явный стабильный профиль, если не противоречит текущему intent
    "confirmed_memory": 5,          # подтверждённая память только в разрешённом domain scope
    "observed_behavior": 6,         # только scheduler/experimentation; НЕ hard gate, НЕ sensitive inference
    "agent_inference": 7,           # soft, editable, low confidence, decay; никогда не скрытый hard gate
}
FRESHNESS = ("current", "recent", "stale")
SENSITIVITY = ("normal", "sensitive", "restricted")


def new_evidence_id(field, value, scope, source):
    """Детерминированный id ПО ИСХОДНОМУ УТВЕРЖДЕНИЮ (field+value+scope+source) — чтобы алиасы/теги
    одной фразы получили ОДИН id и схлопнулись при дедупе (§4.1)."""
    h = hashlib.sha1(("%s|%s|%s|%s" % (field, value, scope, source)).encode("utf-8")).hexdigest()
    return "ev_" + h[:16]


def build_evidence(field, value, source, scope="", confidence=1.0, freshness="current",
                   sensitivity="normal", allowed_purposes=None, visibility="match_only",
                   last_confirmed_at=None, expires_at=None, evidence_id=None):
    if source not in SOURCE_PRIORITY:
        raise ValueError("unknown evidence source: %r" % source)
    if not (0.0 <= float(confidence) <= 1.0):
        raise ValueError("confidence out of [0,1]: %r" % confidence)
    if freshness not in FRESHNESS:
        raise ValueError("bad freshness: %r" % freshness)
    if sensitivity not in SENSITIVITY:
        raise ValueError("bad sensitivity: %r" % sensitivity)
    return {
        "evidence_id": evidence_id or new_evidence_id(field, value, scope, source),
        "field": field, "value": value, "source": source, "scope": scope,
        "confidence": float(confidence), "freshness": freshness, "sensitivity": sensitivity,
        "allowed_purposes": list(allowed_purposes or []), "visibility": visibility,
        "last_confirmed_at": last_confirmed_at, "expires_at": expires_at,
        "priority": SOURCE_PRIORITY[source],
    }


def dedup(evidence_list):
    """§4.1: схлопнуть до уникальных `evidence_id`. Из дублей одного id оставить наиболее приоритетный
    (меньший priority) и наиболее свежий. Гарантирует: один source statement учитывается один раз."""
    by_id = {}
    for e in (evidence_list or []):
        eid = e.get("evidence_id")
        cur = by_id.get(eid)
        if cur is None or e.get("priority", 9) < cur.get("priority", 9):
            by_id[eid] = e
    return list(by_id.values())


def resolve_field(evidence_list, field):
    """§4.2: для поля вернуть победившее evidence по иерархии источников (приоритет 1 бьёт всё).
    Явный ответ в текущем intent (priority 1) побеждает старые данные в scope этого intent."""
    cands = [e for e in (evidence_list or []) if e.get("field") == field]
    if not cands:
        return None
    cands.sort(key=lambda e: (e.get("priority", 9), FRESHNESS.index(e.get("freshness", "stale"))))
    return cands[0]


def usable_for_purpose(evidence, purpose):
    """Evidence применимо к purpose, если allowed_purposes пуст (общее) или содержит purpose.
    Purpose binding (§8.3) НЕ переносит поле одного режима в другой автоматически."""
    ap = evidence.get("allowed_purposes") or []
    return (not ap) or (purpose in ap)
