# -*- coding: utf-8 -*-
"""Privacy-safe map-feed projection for persisted Kleal intents.

This module is deliberately independent from the matching scorer. It accepts
plain persisted rows and produces one of two read models:

* ``offline``: offline + hybrid intents at the explicitly selected venue point;
* ``online``: online + hybrid intents at a country centroid.

Owner/profile coordinates are never a fallback. Missing location is represented
as metadata, not a made-up point. Address geocoding is best-effort, bounded and
cacheable so a provider outage cannot make intent persistence fail.
"""
import hashlib
import json
import os
import threading
import time
import unicodedata
import urllib.parse
import urllib.request

try:                                    # сторож координат живёт в matching_core
    from matching_core.contracts.geo_privacy import assert_no_exact_point_leak as _GEO_GUARD
except Exception:                       # его отсутствие не должно ронять карту
    _GEO_GUARD = None


INACTIVE_STATUSES = frozenset({
    "archived", "cancelled", "canceled", "closed", "completed", "converted_1to1",
    "declined", "deleted", "draft", "expired", "failed", "paused", "withdrawn",
})
ACTIVE_GROUP_STATES = frozenset({"searching", "chat_open", "ready_to_plan", "planning"})


# Country points are public country centroids, not user-derived coordinates.
_COUNTRIES = {
    "ES": {"name": "Spain", "lat": 40.4637, "lng": -3.7492,
           "aliases": ("spain", "espana", "espana", "espagne", "испания")},
    "PT": {"name": "Portugal", "lat": 39.3999, "lng": -8.2245,
           "aliases": ("portugal", "portuguesa", "португалия")},
    "IT": {"name": "Italy", "lat": 41.8719, "lng": 12.5674,
           "aliases": ("italy", "italia", "italie", "италия")},
    "DE": {"name": "Germany", "lat": 51.1657, "lng": 10.4515,
           "aliases": ("germany", "deutschland", "allemagne", "германия")},
    "FR": {"name": "France", "lat": 46.2276, "lng": 2.2137,
           "aliases": ("france", "francia", "frankreich", "франция")},
    "GB": {"name": "United Kingdom", "lat": 55.3781, "lng": -3.4360,
           "aliases": ("united kingdom", "uk", "great britain", "britain", "великобритания")},
    "US": {"name": "United States", "lat": 37.0902, "lng": -95.7129,
           "aliases": ("united states", "united states of america", "usa", "us", "сша")},
}

def _fold(value):
    raw = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(ch for ch in raw if not unicodedata.combining(ch)).lower().split())


# СВИДАНИЕ НА ОБЩУЮ КАРТУ НЕ ПОПАДАЕТ (решение владельца 01.10.2026). Свидания — только по желанию
# и отдельным контуром (спека Matching Core: dating isolated), а лента карты и «Онлайна» читается без
# токена — то есть видна всему интернету. Тип ставит мастер (`type: 'dating'`) с 01.10; затеи,
# сохранённые раньше, типа не несут, но построитель всегда называет свидание одной из трёх фраз.
_DATING_TITLES = {"сходить на свидание", "go on a date", "tener una cita"}


def is_dating(intent, title=None):
    """Затея — свидание: по типу, категории, домену или по названию, которое даёт построитель."""
    if not isinstance(intent, dict):
        return False
    for key in ("type", "category", "domain"):
        if _fold(intent.get(key)) == "dating":
            return True
    return any(_fold(t) in _DATING_TITLES for t in (intent.get("title"), intent.get("activity"), title) if t)


_COUNTRY_ALIASES = {}
for _code, _row in _COUNTRIES.items():
    _COUNTRY_ALIASES[_fold(_code)] = _code
    _COUNTRY_ALIASES[_fold(_row["name"])] = _code
    for _alias in _row.get("aliases") or ():
        _COUNTRY_ALIASES[_fold(_alias)] = _code


def country_info(country=None, country_code=None):
    """Return canonical country data from an explicit country fact only."""
    code = _COUNTRY_ALIASES.get(_fold(country_code)) or _COUNTRY_ALIASES.get(_fold(country))
    row = _COUNTRIES.get(code)
    if row:
        return {"country": row["name"], "countryCode": code,
                "lat": row["lat"], "lng": row["lng"]}
    clean = str(country or "").strip()
    if clean:
        return {"country": clean, "countryCode": str(country_code or "").upper()[:2] or None}
    return None


def normalize_mode(value):
    mode = _fold(value).replace("-", "_").replace(" ", "_")
    if mode in ("online", "remote", "call", "video", "virtual"):
        return "online"
    if mode in ("hybrid", "mixed", "offline_online", "online_offline"):
        return "hybrid"
    return "offline"


def normalize_kind(intent, explicit=None):
    raw = _fold(explicit or (intent or {}).get("format") or (intent or {}).get("kind"))
    if raw in ("group", "group_intent", "group_formation"):
        return "group"
    try:
        if int((intent or {}).get("groupSize") or 0) >= 3:
            return "group"
    except (TypeError, ValueError):
        pass
    return "one_to_one"


def persistence_key(intent):
    """Retry identity for an intent save, without collapsing distinct plans.

    Topics+role alone used to merge an online and an offline plan (or two dates) into one row.
    This key includes the user-visible dimensions while remaining stable across JSON key order.
    """
    intent = intent if isinstance(intent, dict) else {}
    payload = {
        "topics": sorted(_fold(x) for x in (intent.get("topics") or intent.get("tags") or []) if _fold(x)),
        "role": _fold(intent.get("role")),
        "mode": normalize_mode(intent.get("mode")),
        "kind": normalize_kind(intent),
        "address": _fold(intent.get("address")),
        "date": _fold(intent.get("date")),
        "time": _fold(intent.get("time")),
        "when": _fold(intent.get("when")),
        "title": _fold(intent.get("title")),
    }
    return "map-v1:" + hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _number(value, low, high):
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if low <= num <= high else None


def _venue(intent):
    venue = intent.get("venue") if isinstance(intent.get("venue"), dict) else {}
    address = str(intent.get("address") or venue.get("address") or "").strip()
    lat = _number(intent.get("lat") if intent.get("lat") is not None else venue.get("lat"), -90, 90)
    lng = _number(
        intent.get("lng") if intent.get("lng") is not None else
        intent.get("lon") if intent.get("lon") is not None else
        venue.get("lng") if venue.get("lng") is not None else venue.get("lon"),
        -180, 180,
    )
    if lat == 0 and lng == 0:
        lat = lng = None
    return address, lat, lng


class SafeGeocoder:
    """A bounded Nominatim adapter with successful-result cache and retry."""

    def __init__(self, cache_path=None, timeout=1.25, attempts=2, opener=None,
                 endpoint="https://nominatim.openstreetmap.org/search"):
        self.cache_path = str(cache_path or "").strip()
        self.timeout = max(0.1, min(float(timeout), 5.0))
        self.attempts = max(1, min(int(attempts), 3))
        self.opener = opener or urllib.request.urlopen
        self.endpoint = endpoint
        self._lock = threading.Lock()
        self._cache = self._load()

    def _load(self):
        if not self.cache_path:
            return {}
        try:
            with open(self.cache_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _persist(self):
        if not self.cache_path:
            return
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.cache_path)), exist_ok=True)
            tmp = self.cache_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._cache, fh, ensure_ascii=False, sort_keys=True)
            os.replace(tmp, self.cache_path)
        except Exception:
            pass

    def geocode(self, address):
        key = _fold(address)
        if not key:
            return None
        with self._lock:
            cached = self._cache.get(key)
        if isinstance(cached, dict):
            if cached.get("missing"):
                if float(cached.get("retryAfter") or 0) > time.time():
                    return None
                with self._lock:
                    self._cache.pop(key, None)
            else:
                return dict(cached)

        params = urllib.parse.urlencode({
            "q": str(address).strip(), "format": "jsonv2", "limit": 1,
            "addressdetails": 1,
        })
        req = urllib.request.Request(
            self.endpoint + "?" + params,
            headers={"User-Agent": "KlealMapFeed/1.0 (location adapter)"},
        )
        for _attempt in range(self.attempts):
            try:
                response = self.opener(req, timeout=self.timeout)
                if hasattr(response, "__enter__"):
                    with response as opened:
                        raw = opened.read()
                else:
                    raw = response.read()
                rows = json.loads(raw.decode("utf-8"))
                row = rows[0] if isinstance(rows, list) and rows else None
                lat = _number((row or {}).get("lat"), -90, 90)
                lng = _number((row or {}).get("lon"), -180, 180)
                if lat is None or lng is None or (lat == 0 and lng == 0):
                    continue
                addr = row.get("address") if isinstance(row.get("address"), dict) else {}
                result = {"lat": lat, "lng": lng}
                if addr.get("country"):
                    result["country"] = str(addr["country"])
                if addr.get("country_code"):
                    result["countryCode"] = str(addr["country_code"]).upper()[:2]
                with self._lock:
                    self._cache[key] = result
                    self._persist()
                return dict(result)
            except Exception:
                continue
        # A provider outage must not trigger another pair of network calls on every map refresh.
        # This is intentionally short-lived: an unavailable address can recover without migration.
        with self._lock:
            self._cache[key] = {"missing": True, "retryAfter": time.time() + 300}
            self._persist()
        return None


def prepare_persisted_intent(intent, owner_profile=None, geocoder=None):
    """Snapshot country and best-effort venue coordinates without mutating input."""
    out = dict(intent or {})
    owner_profile = owner_profile if isinstance(owner_profile, dict) else {}
    # Never bless client-supplied or city-derived country. Only the profile's explicit country
    # fact is snapshotted, with provenance that the online projector can verify later.
    info = country_info(owner_profile.get("country"), owner_profile.get("countryCode"))
    if info:
        out["country"] = info.get("country")
        if info.get("countryCode"):
            out["countryCode"] = info["countryCode"]
        else:
            out.pop("countryCode", None)
        out["countrySource"] = "confirmed_profile_country"
    else:
        out.pop("countrySource", None)
    address, lat, lng = _venue(out)
    if normalize_mode(out.get("mode")) in ("offline", "hybrid") and address and (
            lat is None or lng is None) and geocoder is not None:
        found = geocoder.geocode(address)
        if found:
            out["lat"], out["lon"] = found["lat"], found["lng"]
            # Venue country is not an owner-country fact and cannot position an online card.
            if found.get("country"):
                out["venueCountry"] = found["country"]
            if found.get("countryCode"):
                out["venueCountryCode"] = found["countryCode"]
    return out


def _active(record, intent):
    if record.get("deleted"):
        return False
    status = _fold(record.get("status") or intent.get("status") or "active").replace(" ", "_")
    if status in INACTIVE_STATUSES:
        return False
    state = _fold(record.get("state")).replace(" ", "_")
    if state and record.get("kind") == "group" and state not in ACTIVE_GROUP_STATES:
        return False
    if record.get("ownerOpen") is False or intent.get("open") is False:
        return False
    return bool(record.get("legacyPublic") or record.get("launched"))


def _fingerprint(record, intent, owner_name, mode, kind):
    bits = {
        "owner": _fold(owner_name),
        "title": _fold(record.get("title") or intent.get("title")),
        "mode": mode,
        "kind": kind,
        "address": _fold(intent.get("address")),
        "country": _fold(intent.get("country")),
        "when": _fold(intent.get("when") or intent.get("time") or intent.get("date")),
        "topics": sorted(_fold(x) for x in (intent.get("topics") or intent.get("tags") or []) if _fold(x)),
    }
    return hashlib.sha1(json.dumps(bits, sort_keys=True).encode("utf-8")).hexdigest()


def _stable_id(record, intent, fingerprint):
    value = record.get("id") or intent.get("id") or intent.get("intent_id")
    return str(value) if value else "legacy_" + fingerprint[:16]


def _owner_card(record):
    owner = record.get("ownerProfile") if isinstance(record.get("ownerProfile"), dict) else {}
    name = str(record.get("owner") or owner.get("name") or "").strip()
    card = {"displayName": name or "Someone"}
    if owner.get("id"):
        card["id"] = str(owner["id"])
    if owner.get("photo"):
        card["photo"] = str(owner["photo"])
    return card, owner


def _owner_projection(candidate):
    """A deliberately coordinate-free owner view."""
    candidate = candidate if isinstance(candidate, dict) else {}
    return {
        "id": candidate.get("id"),
        "name": candidate.get("name"),
        "photo": candidate.get("photo"),
        "open": candidate.get("open", True),
        "country": candidate.get("country"),
        "countryCode": candidate.get("countryCode"),
        "area": candidate.get("area") or candidate.get("city"),
    }


def owner_profiles(users):
    return {
        _fold(row.get("name")): _owner_projection(row)
        for row in users or []
        if isinstance(row, dict) and row.get("source") != "seed" and _fold(row.get("name"))
    }


def owner_profiles_by_id(users):
    """Автор по ID. Личность — id строки, а не подпись: по подписи тёзки получали чужое лицо и
    чужую страну на карточке (docs/IDENTITY.md)."""
    return {
        str(row.get("id")): _owner_projection(row)
        for row in users or []
        if isinstance(row, dict) and row.get("source") != "seed" and str(row.get("id") or "")
    }


def owner_profile_for(users, owner, owner_id=""):
    """Return the coordinate-free owner projection used by persistence enrichment."""
    if owner_id:
        return owner_profiles_by_id(users).get(str(owner_id)) or {}
    return owner_profiles(users).get(_fold(owner)) or {}


def _mine(record_owner_id, record_owner, self_id, me):
    """Это запись того, кто смотрит? По id, когда он известен у обеих сторон; по подписи — только
    для старых записей без id и только если у смотрящего нет id."""
    if self_id and record_owner_id:
        return str(record_owner_id) == str(self_id)
    if self_id:
        return False
    return bool(me) and _fold(record_owner) == me


def collect_sources(users, saved_intents, group_intents, self_name="", self_id=""):
    """Unify all current persistence paths into plain map-feed records.

    Groups come first so their canonical group id and live participant count win semantic dedupe
    over the standing-search copy that precedes group creation.
    """
    me = _fold(self_name)
    owners = owner_profiles(users)
    owners_by_id = owner_profiles_by_id(users)
    out = []

    for group in group_intents or []:
        if not isinstance(group, dict):
            continue
        owner = str(group.get("owner") or "").strip()
        owner_id = str(group.get("owner_id") or "")
        if not owner or _mine(owner_id, owner, self_id, me):
            continue
        raw = group.get("intent") if isinstance(group.get("intent"), dict) else {}
        intent = dict(raw)
        for key in ("title", "mode", "topics"):
            if group.get(key) is not None:
                intent.setdefault(key, group.get(key))
        count = sum(1 for member in (group.get("members") or [])
                    if isinstance(member, dict) and member.get("state") in ("joined", "active"))
        out.append({
            "id": group.get("id"), "owner": owner, "title": group.get("title"),
            "intent": intent, "kind": "group", "state": group.get("state"),
            "status": group.get("status"), "launched": group.get("created") or True,
            "count": count, "ownerOpen": True,
            "ownerProfile": (owners_by_id.get(owner_id) if owner_id else owners.get(_fold(owner))) or {},
            # Время, район и размеры комнаты живут в САМОЙ группе, а не в её интенте: у ста двух
            # групп из ста восемнадцати времени больше нет нигде. Кладём их в запись, а не внутрь
            # интента, нарочно: отпечаток записи считается по интенту, и подмешивание в него
            # развалило бы склейку группы с её же поисковой копией — на карте появились бы дубли.
            "when": group.get("when"), "area": group.get("area"),
            "minTotal": group.get("min_total"), "maxTotal": group.get("max_total"),
        })

    for row in saved_intents or []:
        if not isinstance(row, dict):
            continue
        owner = str(row.get("owner") or "").strip()
        owner_id = str(row.get("owner_id") or "")
        if not owner or _mine(owner_id, owner, self_id, me):
            continue
        intent = row.get("intent") if isinstance(row.get("intent"), dict) else {}
        profile = (owners_by_id.get(owner_id) if owner_id else owners.get(_fold(owner))) or {}
        out.append({
            "id": row.get("id"), "owner": owner, "title": row.get("title"),
            "intent": intent, "kind": normalize_kind(intent),
            "status": row.get("status"), "launched": row.get("launched"),
            "ownerOpen": profile.get("open", True), "ownerProfile": profile,
        })

    for candidate in users or []:
        if not isinstance(candidate, dict) or candidate.get("source") == "seed":
            continue
        owner = str(candidate.get("name") or "").strip()
        if not owner or _mine(str(candidate.get("id") or ""), owner, self_id, me):
            continue
        for intent in candidate.get("intents") or []:
            if not isinstance(intent, dict) or intent.get("open") is False:
                continue
            status = _fold(intent.get("status") or "active").replace(" ", "_")
            topics = intent.get("topics") or intent.get("tags") or []
            if status in INACTIVE_STATUSES or not any(_fold(topic) for topic in topics):
                continue
            out.append({
                "id": intent.get("id") or intent.get("intent_id"), "owner": owner,
                "title": intent.get("title"), "intent": intent,
                "kind": normalize_kind(intent), "status": intent.get("status"),
                "legacyPublic": True, "ownerOpen": candidate.get("open", True),
                "ownerProfile": _owner_projection(candidate),
            })
    return out


# ── Открытая часть интента ───────────────────────────────────────────────────────────────
#
# ЧТО ВИДИТ ЧУЖОЙ ЧЕЛОВЕК. До этого лента отдавала только название, автора и точку — карточка
# интента на карте читалась как заглушка: ни времени, ни темы, ни того, что вообще задумано.
# Теперь рядом с элементом едет открытая часть самого интента: ровно то, что автор опубликовал
# СОЗНАТЕЛЬНО, чтобы на встречу можно было прийти. Поля собраны по списку, а не переносом всего
# объекта: в интенте лежит и служебное, и личное, и один такой перенос стал бы утечкой.
#
# Чего здесь нет намеренно:
#   phrase  — собственные слова автора Бадди: это разговор, а не объявление;
#   link    — ссылка на онлайн-встречу: её присылают после согласия, иначе зайдёт кто угодно;
#   lat/lon/radiusKm — точка и радиус поиска живут на уровне элемента и только для офлайна,
#                      где место встречи опубликовано (Вердикт#22: домашняя точка — никогда).
#
# ЛЕНТА ЧИТАЕТСЯ БЕЗ ТОКЕНА (см. обработчик /api/agent/map-feed: личность берётся из заголовка,
# а если его нет — из параметра). Значит всё, что попадёт сюда, опубликовано для всего
# интернета, а не «для пользователей приложения». Отсюда и короткий список: только то, что
# описывает САМУ ВСТРЕЧУ.
#
# Чего здесь нет и почему:
#   sex, minAge, maxAge, radiusKm — это про ПОИСК и про людей, а не про встречу: «ищет женщин
#                                   22–34» на открытой карточке превращает затею в объявление;
#   phrase                        — собственные слова автора Бадди: это разговор, не объявление;
#   link                          — ссылку на звонок присылает организатор после согласия;
#   time                          — СТРОКА ПОИСКА, а не время для глаз: у половины записей это
#                                   «tomorrow 11:55» и «Aug 30 16:00». Показать её русскому или
#                                   испанцу значит показать английский. Время берётся только из
#                                   `when` (его автор видел сам) или собирается на телефоне из
#                                   `dateKey` + `minutes` тем же кодом, что подписывает свои затеи;
#   place, area                   — это ГОРОД ПРОФИЛЯ автора, а не место встречи: мастер пишет
#                                   `intent.place = профиль.город`, а `area` группы — копия того
#                                   же поля. Под подписью «место встречи» карточка назвала бы
#                                   домашний город автора местом свидания. Место встречи — это
#                                   `address`, и только он;
#   summary                       — на живых данных его нет ни у одного интента, а собирать его
#                                   из полей значило бы дописать за автора то, чего он не писал.
_PUBLIC_FIELDS = ("title", "topics", "when", "dateKey", "minutes", "mode", "format", "kind", "groupSize")
# Место встречи — только у офлайна и гибрида, и только НАЗВАННОЕ автором место, а не его город.
_PUBLIC_PLACE_FIELDS = ("address", "venue_name", "venueName")


def public_intent(intent, view="offline", record=None):
    """Открытая часть интента для карточки на карте — по списку полей, а не переносом объекта."""
    intent = intent if isinstance(intent, dict) else {}
    record = record if isinstance(record, dict) else {}
    out = {}
    for key in _PUBLIC_FIELDS:
        value = intent.get(key)
        if value is None or value == "":
            continue
        if key == "topics":
            topics = [str(x).strip()[:60] for x in (value if isinstance(value, (list, tuple)) else [])
                      if str(x).strip()]
            if topics:
                # Три темы, как и везде на выдаче: длинный список тем — это уже профиль автора.
                out["topics"] = topics[:3]
            continue
        if key == "minutes":
            try:
                num = int(value)
            except (TypeError, ValueError):
                continue
            if 0 <= num <= 1439:
                out["minutes"] = num
            continue
        if key in ("groupSize", "minutes"):
            try:
                out[key] = int(value)
            except (TypeError, ValueError):
                pass
            continue
        out[key] = str(value).strip()[:300]
    if not out.get("topics"):
        tags = intent.get("tags")
        topics = [str(x).strip()[:60] for x in (tags if isinstance(tags, (list, tuple)) else []) if str(x).strip()]
        if topics:
            out["topics"] = topics[:3]
    if str(view).strip().lower() != "online":
        for key in _PUBLIC_PLACE_FIELDS:
            value = intent.get(key)
            if value:
                out.setdefault(key, str(value).strip()[:300])
    # Размеры комнаты группа держит у себя, а не в интенте: без них не собрать «n из m».
    # Время и район группы (`record["when"]`, `record["area"]`) НЕ берутся сознательно —
    # см. список выше: первое английское, второе про город автора.
    for src, dst in (("minTotal", "minTotal"), ("maxTotal", "maxTotal")):
        try:
            value = int(record.get(src))
        except (TypeError, ValueError):
            continue
        if value > 0:
            out[dst] = value
    return out


# Ключи, которых в ответе не должно быть НИКОГДА: это точка человека, а не место встречи.
_PRIVATE_KEYS = ("exact_point", "coarseLat", "coarseLon", "home_address", "work_address")


def _assert_publishable(item, view):
    """Последняя проверка перед выдачей: лучше упасть на сборке, чем доехать до чужого экрана.

    Сторож из matching_core зовётся только для офлайна и только со словом `venue`: там точка —
    это площадка, названная автором, и она публикуется намеренно. Для онлайна он не годится
    вовсе: там в элементе стоит ПУБЛИЧНЫЙ центроид страны, а сторож считает любую пару lat/lon
    частной и уронил бы каждый ответ глобуса. Поэтому у онлайна своя проверка — отсутствие
    места; а список частных ключей проверяется в обоих видах.
    """
    for key in _PRIVATE_KEYS:
        if key in item:
            raise ValueError("private point leaked to map feed: %s" % key)
    if view == "online":
        for key in ("address", "venue_name", "venueName"):
            if key in item or key in (item.get("intent") or {}):
                raise ValueError("meeting place leaked into the online view: %s" % key)
    elif _GEO_GUARD is not None:
        _GEO_GUARD(item, location_kind="venue")


def _count(record, kind):
    if kind != "group":
        return 1
    try:
        return max(1, int(record.get("count") or 1))
    except (TypeError, ValueError):
        return 1


def build_feed(records, view, limit=60, geocoder=None, geocode_budget=4):
    """Project persisted intent rows into the stable map-feed response."""
    view = str(view or "offline").strip().lower()
    if view not in ("offline", "online"):
        raise ValueError("view must be offline or online")
    try:
        limit = max(1, min(200, int(limit)))
    except (TypeError, ValueError):
        limit = 60
    budget = max(0, int(geocode_budget or 0))
    items = []
    unavailable = 0
    seen_ids = set()
    seen_fingerprints = set()

    for record in records or []:
        if not isinstance(record, dict):
            continue
        intent = record.get("intent") if isinstance(record.get("intent"), dict) else {}
        if not _active(record, intent):
            continue
        if is_dating(intent, record.get("title")):
            continue
        mode = normalize_mode(intent.get("mode") or record.get("mode"))
        if view == "offline" and mode not in ("offline", "hybrid"):
            continue
        if view == "online" and mode not in ("online", "hybrid"):
            continue
        kind = normalize_kind(intent, record.get("kind"))
        owner_card, owner_profile = _owner_card(record)
        fingerprint = _fingerprint(record, intent, owner_card["displayName"], mode, kind)
        item_id = _stable_id(record, intent, fingerprint)
        if item_id in seen_ids or fingerprint in seen_fingerprints:
            continue

        title = str(record.get("title") or intent.get("title") or "").strip()
        if not title:
            topics = intent.get("topics") or intent.get("tags") or []
            title = str(topics[0]).strip() if topics else "Meetup"
        public = public_intent(intent, view, record)
        item = {
            "id": item_id,
            "title": title[:160],
            "mode": mode,
            "kind": kind,
            "status": "launched",
            "count": _count(record, kind),
            "owner": owner_card,
            # Открытая часть самого интента: по ней экран рисует настоящую карточку.
            "intent": public,
        }
        # Сколько мест осталось в комнате — считается здесь, а не на телефоне: состав участников
        # наружу не отдаётся вовсе, а число свободных мест — открытый факт про саму затею.
        if kind == "group" and public.get("maxTotal"):
            item["seatsLeft"] = max(0, int(public["maxTotal"]) - int(item["count"]))
        # Время и темы дублируются на верхнем уровне: их читают уже существующие сборщики
        # моделей в приложении, и менять их ради вложенного объекта незачем.
        if public.get("when") or public.get("time"):
            item["when"] = public.get("when") or public.get("time")
        if public.get("topics"):
            item["topics"] = public["topics"]

        if view == "offline":
            item["privacy"] = "exact_intent_location"
            address, lat, lng = _venue(intent)
            if address:
                item["address"] = address[:300]
            if (lat is None or lng is None) and address and geocoder is not None and budget > 0:
                budget -= 1
                found = geocoder.geocode(address)
                if found:
                    lat, lng = found.get("lat"), found.get("lng")
            if lat is not None and lng is not None:
                item["lat"], item["lng"] = lat, lng
                item["locationAvailable"] = True
            else:
                item["locationAvailable"] = False
                unavailable += 1
        else:
            item["privacy"] = "country_only"
            # Live profile country is authoritative. Persisted country is accepted only when the
            # backend stamped its provenance; raw intent fields, area and city are untrusted.
            profile_country = owner_profile.get("country")
            profile_code = owner_profile.get("countryCode")
            if profile_country or profile_code:
                info = country_info(profile_country, profile_code)
            elif intent.get("countrySource") == "confirmed_profile_country":
                info = country_info(intent.get("country"), intent.get("countryCode"))
            else:
                info = None
            if info:
                item["countrySource"] = "confirmed_profile_country"
                if info.get("country"):
                    item["country"] = info["country"]
                if info.get("countryCode"):
                    item["countryCode"] = info["countryCode"]
                if info.get("lat") is not None and info.get("lng") is not None:
                    item["lat"], item["lng"] = info["lat"], info["lng"]
                    item["locationAvailable"] = True
                else:
                    item["locationAvailable"] = False
                    unavailable += 1
            else:
                item["locationAvailable"] = False
                unavailable += 1

        _assert_publishable(item, view)
        items.append(item)
        seen_ids.add(item_id)
        seen_fingerprints.add(fingerprint)
        if len(items) >= limit:
            break

    return {
        "items": items,
        "partial": bool(unavailable),
        "unavailableCount": unavailable,
    }
