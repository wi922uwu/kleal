# -*- coding: utf-8 -*-
"""§4 Reservation — временное удержание capacity/слота (для групп и срочных intent, §11.1).

TTL + version; истёкшая reservation освобождает слот. Используется, чтобы два concurrent accept
последнего слота не превысили capacity (C#8) — фактическая проверка в orchestrator/group (§14.3).
"""


def build_reservation(reservation_id, resource, holder, *, ttl_sec=20 * 60, created_at=None, version=1):
    expires_at = (float(created_at) + ttl_sec) if created_at is not None else None
    return {"reservation_id": reservation_id, "resource": resource, "holder": holder,
            "created_at": created_at, "expires_at": expires_at, "version": int(version), "status": "held"}


def is_expired(reservation, now):
    exp = reservation.get("expires_at")
    return bool(exp is not None and float(now) >= float(exp))
