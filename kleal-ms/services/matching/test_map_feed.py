#!/usr/bin/env python3
"""Targeted map-feed contract and HTTP-path regressions."""
import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SHARED = os.path.join(ROOT, "shared")
for path in (HERE, SHARED):
    if path not in sys.path:
        sys.path.insert(0, path)

import intent_map_feed as mf


FAILS = []


def check(name, ok, got=None):
    print(("  ok  " if ok else "FAIL  ") + name + ("" if ok else " -> %r" % (got,)))
    if not ok:
        FAILS.append(name)


def rec(iid, mode, *, kind="one_to_one", owner="Ana", address=None, lat=None, lng=None,
        country="Spain", status=None, launched=1, count=1, title=None, owner_profile=None):
    intent = {"mode": mode, "format": "group" if kind == "group" else "1:1",
              "topics": ["coffee"], "title": title or (mode + " coffee")}
    if address is not None:
        intent["address"] = address
    if lat is not None:
        intent["lat"] = lat
    if lng is not None:
        intent["lon"] = lng
    if country is not None:
        intent["country"] = country
    return {
        "id": iid, "owner": owner, "title": intent["title"], "intent": intent,
        "kind": kind, "status": status, "launched": launched, "count": count,
        "ownerProfile": owner_profile or {"id": "u_" + owner.lower(), "name": owner,
                                           "country": country, "lat": 12.345, "lon": 67.89},
    }


# 1. Mode split and venue/country privacy.
offline = rec("off", "offline", address="Carrer A, 1", lat=41.40, lng=2.17)
hybrid = rec("hyb", "hybrid", address="Carrer B, 2", lat=41.41, lng=2.18)
online = rec("on", "online", address="must-not-leak", lat=11.11, lng=22.22)

off_feed = mf.build_feed([offline, hybrid, online], "offline", geocode_budget=0)
check("offline view contains only offline and hybrid",
      [x["id"] for x in off_feed["items"]] == ["off", "hyb"], off_feed)
check("offline point is the intent venue", off_feed["items"][0]["lat"] == 41.40 and
      off_feed["items"][0]["lng"] == 2.17, off_feed["items"][0])
check("offline exposes the explicitly published address only",
      off_feed["items"][0].get("address") == "Carrer A, 1" and
      off_feed["items"][0]["privacy"] == "exact_intent_location", off_feed["items"][0])

on_feed = mf.build_feed([offline, hybrid, online], "online", geocode_budget=0)
check("online view contains only hybrid and online",
      [x["id"] for x in on_feed["items"]] == ["hyb", "on"], on_feed)
check("online never exposes address", all("address" not in x for x in on_feed["items"]), on_feed)
check("online uses country centroid, never intent or owner coordinates",
      all((x["lat"], x["lng"]) == (40.4637, -3.7492) for x in on_feed["items"]), on_feed)
check("online privacy is explicit country-only",
      all(x["privacy"] == "country_only" for x in on_feed["items"]), on_feed)

city_country = rec("city-country", "online", country=None,
                   owner_profile={"name": "Porto user", "area": "Porto", "lat": 90, "lon": 90})
city_feed = mf.build_feed([city_country], "online", geocode_budget=0)
check("known profile city provides country-level fallback without profile coordinates",
      city_feed["items"][0].get("countryCode") == "PT" and
      (city_feed["items"][0].get("lat"), city_feed["items"][0].get("lng")) == (39.3999, -8.2245),
      city_feed)
unknown_country = rec("unknown-country", "online", country=None,
                      owner_profile={"name": "Unknown", "area": "Atlantis", "lat": 10, "lon": 20})
unknown_feed = mf.build_feed([unknown_country], "online", geocode_budget=0)
check("unknown country is marked unavailable instead of using profile coordinates",
      unknown_feed["partial"] and "lat" not in unknown_feed["items"][0] and
      "lng" not in unknown_feed["items"][0], unknown_feed)

# 2. Missing geodata is represented, never fabricated.
missing = rec("missing", "offline", address="Unknown venue", lat=None, lng=None)
miss_feed = mf.build_feed([missing], "offline", geocode_budget=0)
check("missing point remains in data for list view", len(miss_feed["items"]) == 1, miss_feed)
check("missing point has no fake coordinates",
      "lat" not in miss_feed["items"][0] and "lng" not in miss_feed["items"][0], miss_feed)
check("missing point is reflected in response metadata",
      miss_feed["partial"] is True and miss_feed["unavailableCount"] == 1 and
      miss_feed["items"][0]["locationAvailable"] is False, miss_feed)
limited_feed = mf.build_feed([
    rec("limited-visible", "offline", address="Visible, 1", lat=41, lng=2),
    rec("limited-hidden", "offline", address="Hidden missing", lat=None, lng=None),
], "offline", limit=1, geocode_budget=0)
check("limit metadata describes only returned items",
      [x["id"] for x in limited_feed["items"]] == ["limited-visible"] and
      limited_feed["partial"] is False and limited_feed["unavailableCount"] == 0,
      limited_feed)

# 3. Dedupe, inactive/unlaunched filtering, and both cardinalities.
group = rec("group-live", "offline", kind="group", owner="Ivan", address="Placa, 1",
            lat=41.39, lng=2.16, count=4, title="Board games")
duplicate = rec("standing-search-copy", "offline", kind="group", owner="Ivan", address="Placa, 1",
                lat=41.39, lng=2.16, count=1, title="Board games")
closed = rec("closed", "offline", status="closed", address="Closed, 1", lat=1, lng=1)
draft = rec("draft", "offline", launched=None, address="Draft, 1", lat=1, lng=1)
one = rec("one", "offline", address="One, 1", lat=40, lng=3)
mixed = mf.build_feed([group, duplicate, closed, draft, one], "offline", geocode_budget=0)
check("semantic duplicate is removed in addition to id dedupe",
      [x["id"] for x in mixed["items"]] == ["group-live", "one"], mixed)
check("group and one-to-one kinds/counts survive projection",
      mixed["items"][0]["kind"] == "group" and mixed["items"][0]["count"] == 4 and
      mixed["items"][1]["kind"] == "one_to_one" and mixed["items"][1]["count"] == 1, mixed)
check("closed and unlaunched intents do not appear",
      not ({"closed", "draft"} & {x["id"] for x in mixed["items"]}), mixed)
check("projection is idempotent", mixed == mf.build_feed(
    [group, duplicate, closed, draft, one], "offline", geocode_budget=0), mixed)


# 4. Geocoder retry/cache and persistence preparation.
class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


calls = {"n": 0}


def flaky(_req, timeout=None):
    calls["n"] += 1
    if calls["n"] == 1:
        raise OSError("temporary provider failure")
    return Response([{"lat": "41.42", "lon": "2.19",
                      "address": {"country": "Spain", "country_code": "es"}}])


with tempfile.TemporaryDirectory() as td:
    cache = os.path.join(td, "geo.json")
    geo = mf.SafeGeocoder(cache_path=cache, attempts=2, opener=flaky)
    found = geo.geocode("Carrer Cache, 3")
    found_again = geo.geocode("carrer cache, 3")
    check("geocoder retries a transient failure", calls["n"] == 2 and found["lat"] == 41.42, found)
    check("successful geocode is cached and retry-idempotent",
          calls["n"] == 2 and found_again == found and os.path.exists(cache), calls)
    prepared = mf.prepare_persisted_intent(
        {"mode": "hybrid", "address": "Carrer Cache, 3"},
        {"country": "Spain", "area": "Barcelona"}, geo)
    check("save preparation snapshots country and venue point",
          prepared.get("country") == "Spain" and prepared.get("countryCode") == "ES" and
          prepared.get("lat") == 41.42 and prepared.get("lon") == 2.19, prepared)

    failed_calls = {"n": 0}

    def always_fails(_req, timeout=None):
        failed_calls["n"] += 1
        raise OSError("provider down")

    failing_geo = mf.SafeGeocoder(cache_path=os.path.join(td, "negative.json"), attempts=2,
                                  opener=always_fails)
    check("provider failure is non-raising", failing_geo.geocode("Nowhere, 1") is None, failed_calls)
    failing_geo.geocode("Nowhere, 1")
    check("negative cache prevents retry storms on repeated API refresh",
          failed_calls["n"] == 2, failed_calls)


# 5. Real app collector and HTTP route, using isolated stores only.
with tempfile.TemporaryDirectory() as td:
    store_path = os.path.join(td, "store.json")
    users_path = os.path.join(td, "users.json")
    with open(store_path, "w", encoding="utf-8") as fh:
        json.dump({}, fh)
    users = [
        {"id": "u_ana", "name": "Ana", "source": "onboarding", "open": True,
         "country": "Spain", "area": "Barcelona", "lat": 99.0, "lon": 88.0,
         "intents": [{"id": "legacy-on", "mode": "online", "format": "1:1",
                      "topics": ["books"], "title": "Legacy reading", "open": True}]},
        {"id": "u_ivan", "name": "Ivan", "source": "onboarding", "open": True,
         "country": "Portugal", "area": "Lisboa", "lat": 77.0, "lon": 66.0},
        {"id": "u_me", "name": "Viewer", "source": "onboarding", "open": True,
         "country": "France", "area": "Paris"},
    ]
    with open(users_path, "w", encoding="utf-8") as fh:
        json.dump({"users": users}, fh)
    os.environ["KLEAL_STORE"] = store_path
    os.environ["KLEAL_USERS"] = users_path
    os.environ["KLEAL_DB"] = "json"
    os.environ["KLEAL_MQ"] = "none"
    os.environ["KLEAL_GEOCODE_CACHE"] = os.path.join(td, "http-geocode.json")
    os.environ["KLEAL_MAP_GEOCODE_BUDGET"] = "0"

    import app as matching

    matching.SESSION = {"_intents": []}
    matching._save_store = lambda: None
    same_topic_offline = {"mode": "offline", "format": "1:1", "topics": ["coffee"],
                          "role": "meet", "date": "2026-09-05", "time": "18:00"}
    same_topic_online = {"mode": "online", "format": "1:1", "topics": ["coffee"],
                         "role": "meet", "date": "2026-09-05", "time": "18:00"}
    first_save = matching.save_intent("Retry user", same_topic_offline, "Coffee", launched=True)
    retry_save = matching.save_intent("Retry user", same_topic_offline, "Coffee", launched=True)
    second_mode = matching.save_intent("Retry user", same_topic_online, "Coffee", launched=True)
    check("intent-save retry merges the same full intent",
          first_save.get("id") == retry_save.get("id") and len(matching.SESSION["_intents"]) == 2,
          matching.SESSION["_intents"])
    check("same topics in a different mode persist as a distinct intent",
          second_mode.get("id") != first_save.get("id") and
          {x["intent"]["mode"] for x in matching.SESSION["_intents"]} == {"offline", "online"},
          matching.SESSION["_intents"])

    matching.SESSION = {
        "_intents": [
            {"id": "saved-off", "owner": "Ana", "title": "Saved offline", "launched": 1,
             "intent": {"mode": "offline", "format": "1:1", "topics": ["coffee"],
                        "address": "Saved, 1", "lat": 41.5, "lon": 2.2}},
            {"id": "saved-online", "owner": "Ivan", "title": "Saved online", "launched": 1,
             "intent": {"mode": "online", "format": "1:1", "topics": ["tech"]}},
            {"id": "mine", "owner": "Viewer", "title": "Mine", "launched": 1,
             "intent": {"mode": "offline", "format": "1:1", "topics": ["coffee"],
                        "address": "Mine, 1", "lat": 1, "lon": 1}},
        ],
        "_gintents": [
            {"id": "group-off", "owner": "Ivan", "title": "Group offline", "created": 1,
             "state": "searching", "mode": "offline", "topics": ["games"],
             "intent": {"mode": "offline", "format": "group", "topics": ["games"],
                        "address": "Group, 1", "lat": 38.7, "lon": -9.1},
             "members": [{"name": "Ivan", "state": "joined"},
                         {"name": "Ana", "state": "active"}]},
        ],
    }
    matching._users_cache = {"mtime": None, "list": None}

    server = matching.ThreadingHTTPServer(("127.0.0.1", 0), matching.H)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:%d" % server.server_port
    try:
        with urllib.request.urlopen(base + "/api/agent/map-feed?view=offline&self=Viewer", timeout=3) as r:
            first = json.loads(r.read().decode("utf-8"))
        with urllib.request.urlopen(base + "/api/agent/map-feed?view=offline&self=Viewer", timeout=3) as r:
            retry = json.loads(r.read().decode("utf-8"))
        with urllib.request.urlopen(base + "/api/agent/map-feed?view=online&self=Viewer", timeout=3) as r:
            online_http = json.loads(r.read().decode("utf-8"))
        check("real GET endpoint returns persisted 1:1 and group offline intents",
              {x["id"] for x in first["items"]} == {"saved-off", "group-off"}, first)
        check("real endpoint excludes viewer's own intent", "mine" not in {x["id"] for x in first["items"]}, first)
        check("real GET is retry/idempotency safe", first == retry, retry)
        check("real online feed includes persisted and legacy launched/public paths",
              {x["id"] for x in online_http["items"]} == {"saved-online", "legacy-on"}, online_http)
        check("real online response cannot leak stored profile coordinates",
              all((x.get("lat"), x.get("lng")) in ((39.3999, -8.2245), (40.4637, -3.7492))
                  for x in online_http["items"]), online_http)
        try:
            urllib.request.urlopen(base + "/api/agent/map-feed?view=invalid", timeout=3)
            invalid_code = 200
        except urllib.error.HTTPError as exc:
            invalid_code = exc.code
        check("invalid feed view is rejected", invalid_code == 400, invalid_code)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


print()
if FAILS:
    print("FAILED %d: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("ALL PASS (%d checks)" % 30)
