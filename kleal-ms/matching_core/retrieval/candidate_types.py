# -*- coding: utf-8 -*-
"""§16 Events, rooms и venues — отдельные типы кандидатов.

Нельзя считать событие «пользователем с большой capacity» (§16). У каждого типа своя eligibility,
ranking-семантика и transaction; event/room/venue закрывают intent как АЛЬТЕРНАТИВА (T4), честно
названная «другой способ», а не «совпадение с людьми» (§16, C#20 — разные transactions и explanation copy).
"""

CANDIDATE_KINDS = ("user", "ad_hoc_group", "event", "online_room", "venue")

# C#20: у каждого типа своя transaction и свой explanation rendering key.
TRANSACTION = {
    "user":         {"transaction": "proposal_to_mutual_contact", "explain_key": "explain.user"},
    "ad_hoc_group": {"transaction": "reservations_to_group_confirmation", "explain_key": "explain.group"},
    "event":        {"transaction": "registration_or_external_handoff", "explain_key": "explain.event_alternative"},
    "online_room":  {"transaction": "join_token_or_waitlist", "explain_key": "explain.room_alternative"},
    "venue":        {"transaction": "selection_or_booking_handoff", "explain_key": "explain.venue"},
}


def build_event(event_id, *, category, schedule, capacity, access="open", topics=None):
    return {"id": event_id, "kind": "event", "category": category, "schedule": schedule,
            "capacity": dict(capacity), "access": access, "topics": list(topics or [])}


def build_room(room_id, *, platform, topic, live_capacity, moderation="on"):
    return {"id": room_id, "kind": "online_room", "platform": platform, "topic": topic,
            "live_capacity": dict(live_capacity), "moderation": moderation}


def build_venue(venue_id, *, availability, price_band, noise, distance_km, accessible=True):
    return {"id": venue_id, "kind": "venue", "availability": availability, "price_band": price_band,
            "noise": noise, "distance_km": distance_km, "accessible": accessible}


def event_eligibility(intent, event):
    """category/schedule/capacity/access (§16). Возвращает (ALLOW/BLOCK, reason)."""
    cap = event.get("capacity") or {}
    if int(cap.get("current", 0)) >= int(cap.get("max", 10 ** 9)):
        return "BLOCK", "event full"
    if event.get("access") == "closed":
        return "BLOCK", "access closed"
    return "ALLOW", None


def user_event_relevance(intent, event):
    """user→event relevance (НЕ reciprocal — событие не «отвечает» пользователю). 0..1 по совпадению темы."""
    from ..taxonomy import graph as TX
    topics = [str(t).lower() for t in (intent.get("topics") or [])]
    ev_topics = [str(t).lower() for t in (event.get("topics") or [event.get("category")])]
    best = TX.similarity(topics, ev_topics)[0]
    return round({4: 1.0, 3: 0.7, 2: 0.5, 1: 0.3, 0: 0.1}[best], 3)


def session_relevance(intent, room):
    from ..taxonomy import graph as TX
    best = TX.similarity([str(t).lower() for t in (intent.get("topics") or [])],
                         [str(room.get("topic") or "").lower()])[0]
    return round({4: 1.0, 3: 0.7, 2: 0.5, 1: 0.3, 0: 0.1}[best], 3)


def plan_suitability(intent, venue):
    """venue → plan suitability: близость/шум/доступность (не «релевантность человека»)."""
    dist = float(venue.get("distance_km") or 99)
    s = 1.0 if dist <= 2 else (0.7 if dist <= 5 else (0.4 if dist <= 15 else 0.1))
    if venue.get("noise") == "loud":
        s *= 0.8
    if not venue.get("accessible", True):
        s *= 0.5
    return round(s, 3)


def candidate_transaction(kind):
    """C#20: разные transaction + explanation copy у event/user/group/room/venue."""
    if kind not in TRANSACTION:
        raise ValueError("unknown candidate kind: %r" % kind)
    return dict(TRANSACTION[kind])
