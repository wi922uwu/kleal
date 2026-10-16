# -*- coding: utf-8 -*-
"""Вердикт#22 — приватность географии и staged location disclosure.

Жёсткое правило для социального продукта:
  • ranker может использовать точную/приблизительную координату ТОЛЬКО в закрытом backend-контуре;
  • клиент получает район/зону/приблизительное расстояние — НЕ точную точку и НЕ точное расстояние;
  • точная точка не раскрывается до согласованного плана;
  • live-location не участвует в discovery по умолчанию;
  • домашний/рабочий адрес не используется как место первой встречи.

ЧЬЯ ТОЧКА — ВАЖНЕЕ, ЧЕМ ТОЧНОСТЬ ТОЧКИ. Правила выше писались про ЧЕЛОВЕКА: где он живёт, где
работает, где находится сейчас. Всё это закрыто, и никакая стадия раскрытия этого не меняет до
согласованного плана.

Но у затеи есть ВТОРОЙ вид точки, и он противоположен по смыслу: адрес места встречи, который
человек назвал сам и ровно затем, чтобы туда пришли. Прятать его — не приватность, а поломка:
по зоне в полкилометра на встречу не придёшь, а карта открытых затей существует именно для того,
чтобы понять, куда идти. Это тот же принцип, что уже записан ниже в `can_be_first_meeting_place`:
дом и работа местом встречи быть не могут, площадка — может, и она не является частной точкой
человека.

Поэтому здесь два класса, и путать их нельзя:

  ЧАСТНАЯ ТОЧКА (`home`, `work`, `live`, метка профиля, координаты кандидата) — огрублена всегда,
  на карту не идёт, в клиентском ответе является утечкой;

  ПЛОЩАДКА (`venue`) — адрес, опубликованный автором затеи вместе с самой затеей. Идёт клиенту
  точной; иначе затея на карте оказывается там, где живёт автор, а не там, где встреча.

Различение введено после живого случая: подсказки по адресам начали приносить в затею настоящую
координату места, и без этого правила её пришлось бы либо огрублять (карта врёт), либо публиковать
вместе с домашней (утечка). Ни то, ни другое не годится, потому что это РАЗНЫЕ точки.
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


# Виды точек, которые человек публикует САМ как место встречи. Всё остальное считается частным.
PUBLISHABLE_KINDS = ("venue", "agreed_venue", "meeting_place", "event")


def is_publishable_point(location_kind):
    """Можно ли отдать клиенту ТОЧНУЮ координату этого вида точки.

    Единственное «да» — площадка, названная автором затеи. Дом, работа, текущее положение и метка
    профиля остаются закрытыми при любой стадии раскрытия: их человек не публиковал, он ими живёт.
    """
    return str(location_kind or "").strip().lower() in PUBLISHABLE_KINDS


def can_be_first_meeting_place(location_kind):
    """Вердикт#22: домашний/рабочий адрес нельзя использовать как место первой встречи."""
    return str(location_kind).lower() not in ("home", "work", "home_address", "work_address")


def assert_no_exact_point_leak(payload, *, plan_confirmed=False, location_kind=None):
    """Guard: в клиентском payload нет точной ЧАСТНОЙ координаты до согласованного плана.

    `location_kind` называет, ЧЬЯ это точка. Без него поведение прежнее — всё считается частным:
    старые вызовы ничего не теряют, а новый смысл надо запросить явно, а не получить молча.

    Площадку (`venue`) сторож пропускает: она опубликована автором затеи и обязана дойти до карты
    точной. Домашний и рабочий адрес не пропускаются НИКОГДА, даже если их назвали площадкой, —
    иначе правило обходится одним словом в поле; `can_be_first_meeting_place` запрещает их и как
    место встречи.
    """
    if plan_confirmed:
        return True
    private_always = ("exact_point", "coarseLat", "coarseLon", "home_address", "work_address")
    for k in private_always:
        if k in (payload or {}):
            raise ValueError("exact location leaked to client before agreed plan: %s" % k)
    if is_publishable_point(location_kind):
        return True
    for k in ("lat", "lon"):
        if k in (payload or {}):
            raise ValueError("exact location leaked to client before agreed plan: %s" % k)
    return True
