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

_CITY_COUNTRY = {
    # The exact countries/cities currently offered by AreaPicker.
    "barcelona": "ES", "madrid": "ES", "valencia": "ES", "sevilla": "ES",
    "malaga": "ES", "bilbao": "ES", "palma": "ES", "zaragoza": "ES",
    "lisboa": "PT", "lisbon": "PT", "porto": "PT", "faro": "PT",
    "coimbra": "PT", "braga": "PT", "funchal": "PT",
    "roma": "IT", "rome": "IT", "milano": "IT", "milan": "IT", "napoli": "IT",
    "torino": "IT", "firenze": "IT", "bologna": "IT", "venezia": "IT", "palermo": "IT",
    "berlin": "DE", "munchen": "DE", "munich": "DE", "hamburg": "DE", "koln": "DE",
    "cologne": "DE", "frankfurt": "DE", "stuttgart": "DE", "dusseldorf": "DE",
    "leipzig": "DE",
    "paris": "FR", "lyon": "FR", "marseille": "FR", "toulouse": "FR", "nice": "FR",
    "bordeaux": "FR", "nantes": "FR", "lille": "FR",
}


def _fold(value):
    raw = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(ch for ch in raw if not unicodedata.combining(ch)).lower().split())


_COUNTRY_ALIASES = {}
for _code, _row in _COUNTRIES.items():
    _COUNTRY_ALIASES[_fold(_code)] = _code
    _COUNTRY_ALIASES[_fold(_row["name"])] = _code
    for _alias in _row.get("aliases") or ():
        _COUNTRY_ALIASES[_fold(_alias)] = _code


def country_info(country=None, country_code=None, city=None):
    """Return canonical country data without consulting owner coordinates."""
    code = _COUNTRY_ALIASES.get(_fold(country_code)) or _COUNTRY_ALIASES.get(_fold(country))
    if not code and city:
        code = _CITY_COUNTRY.get(_fold(city))
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
    if not out.get("country"):
        info = country_info(
            owner_profile.get("country"), owner_profile.get("countryCode"),
            owner_profile.get("area") or owner_profile.get("city"),
        )
        if info:
            out["country"] = info.get("country")
            if info.get("countryCode"):
                out["countryCode"] = info["countryCode"]
    address, lat, lng = _venue(out)
    if normalize_mode(out.get("mode")) in ("offline", "hybrid") and address and (
            lat is None or lng is None) and geocoder is not None:
        found = geocoder.geocode(address)
        if found:
            out["lat"], out["lon"] = found["lat"], found["lng"]
            if not out.get("country") and found.get("country"):
                out["country"] = found["country"]
            if not out.get("countryCode") and found.get("countryCode"):
                out["countryCode"] = found["countryCode"]
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


def owner_profile_for(users, owner):
    """Return the coordinate-free owner projection used by persistence enrichment."""
    return owner_profiles(users).get(_fold(owner)) or {}


def collect_sources(users, saved_intents, group_intents, self_name=""):
    """Unify all current persistence paths into plain map-feed records.

    Groups come first so their canonical group id and live participant count win semantic dedupe
    over the standing-search copy that precedes group creation.
    """
    me = _fold(self_name)
    owners = owner_profiles(users)
    out = []

    for group in group_intents or []:
        if not isinstance(group, dict):
            continue
        owner = str(group.get("owner") or "").strip()
        if not owner or (me and _fold(owner) == me):
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
            "ownerProfile": owners.get(_fold(owner)) or {},
        })

    for row in saved_intents or []:
        if not isinstance(row, dict):
            continue
        owner = str(row.get("owner") or "").strip()
        if not owner or (me and _fold(owner) == me):
            continue
        intent = row.get("intent") if isinstance(row.get("intent"), dict) else {}
        profile = owners.get(_fold(owner)) or {}
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
        if not owner or (me and _fold(owner) == me):
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
        item = {
            "id": item_id,
            "title": title[:160],
            "mode": mode,
            "kind": kind,
            "status": "launched",
            "count": _count(record, kind),
            "owner": owner_card,
        }

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
            info = country_info(
                intent.get("country") or owner_profile.get("country"),
                intent.get("countryCode") or owner_profile.get("countryCode"),
                owner_profile.get("area") or owner_profile.get("city"),
            )
            if info:
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
