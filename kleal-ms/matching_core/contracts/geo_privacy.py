# -*- coding: utf-8 -*-
"""Вердикт#22 — приватность географии и staged location disclosure.

Жёсткое правило для социального продукта:
  • ranker может использовать точную/приблизительную координату ТОЛЬКО в закрытом backend-контуре;
  • клиент получает район/зону/приблизительное расстояние — НЕ точную точку и НЕ точное расстояние;
  • точная точка не раскрывается до согласованного плана;
  • live-location не участвует в discovery по умолчанию;
  • домашний/рабочий адрес не используется как место первой встречи.
"""

# стадии раскрытия локации (возрастание).
DISCLOSURE_STAGES = ("zone_only", "approx_distance", "area", "agreed_venue", "exact_point")

# банды приблизительного расстояния, отдаваемые клиенту (точное расстояние не раскрываем).
_DISTANCE_BANDS = ((1.0, "<1 km"), (3.0, "~1-3 km"), (7.0, "~3-7 km"), (15.0, "~7-15 km"))


def distance_band(km):
    """Вердикт#22: клиенту — только банда расстояния, не точное значение."""
    if km is None:
        return "unknown"
    for lim, label in _DISTANCE_BANDS:
        if float(km) <= lim:
            return label
    return ">15 km"


def client_location_view(candidate, *, stage="zone_only", km=None, plan_confirmed=False):
    """Вердикт#22: что можно показать КЛИЕНТУ на данной стадии. Точная точка/адрес — только после
    согласованного плана. Возвращает безопасный dict без точной координаты до agreed_venue."""
    view = {"zone": candidate.get("coarse_cell") or candidate.get("zone") or candidate.get("area"),
            "disclosure_stage": stage}
    if stage in ("approx_distance", "area", "agreed_venue", "exact_point"):
        view["approx_distance"] = distance_band(km)
    if stage == "agreed_venue" and plan_confirmed:
        view["venue"] = candidate.get("agreed_venue")           # согласованное нейтральное место
    if stage == "exact_point" and plan_confirmed:
        view["exact_point"] = candidate.get("exact_point")      # точная точка — ТОЛЬКО после плана
    # точная координата НИКОГДА не уходит клиенту вне backend
    view["exact_coord_withheld"] = stage not in ("exact_point",) or not plan_confirmed
    return view


def ranker_may_use_precise():
    """Backend-ranker вправе использовать точную/приблизительную координату (закрытый контур)."""
    return True


def live_location_in_discovery():
    """Вердикт#22: live-location НЕ участвует в discovery по умолчанию."""
    return False


def can_be_first_meeting_place(location_kind):
    """Вердикт#22: домашний/рабочий адрес нельзя использовать как место первой встречи."""
    return str(location_kind).lower() not in ("home", "work", "home_address", "work_address")


def assert_no_exact_point_leak(payload, *, plan_confirmed=False):
    """Guard: в клиентском payload не должно быть exact_point/точной координаты до согласованного плана."""
    if plan_confirmed:
        return True
    for k in ("exact_point", "lat", "lon", "coarseLat", "coarseLon", "home_address", "work_address"):
        if k in (payload or {}):
            raise ValueError("exact location leaked to client before agreed plan: %s" % k)
    return True
