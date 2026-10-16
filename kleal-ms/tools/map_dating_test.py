"""Свидание не попадает на общую карту и в «Онлайн» (решение владельца 01.10.2026).

    python3 tools/map_dating_test.py

Лента карты читается без токена — она публична. Проверяет imf.is_dating и build_feed на двух
видах: затея-свидание пропадает, обычная остаётся. Без сети и без стора.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "services", "matching"))
import intent_map_feed as imf

ok = bad = 0
def check(name, cond):
    global ok, bad
    if cond: ok += 1
    else:
        bad += 1; print("FAIL", name)

D = imf.is_dating
check("type dating", D({"type": "dating"}))
check("type Dating", D({"type": " Dating "}))
check("category dating", D({"category": "dating"}))
check("старое свидание по названию ru", D({"title": "Сходить на свидание"}))
check("старое свидание по названию en/es", D({"title": "Go on a date"}) and D({"title": "Tener una cita"}))
check("название записи", D({}, title="Сходить на свидание"))
check("кофе — не свидание", not D({"type": "social", "title": "Выпить кофе"}))
check("«свидание с городом» — не по слову, а по фразе", not D({"title": "Свидание с городом: прогулка"}))
check("не словарь", not D(None) and not D("dating"))

def rec(i, intent, mode):
    return {"id": "t%d" % i, "owner": "Ana%d" % i, "intent": dict(intent, mode=mode), "launched": True,
            "kind": "solo", "ownerOpen": True, "ownerProfile": {"name": "Ana%d" % i, "country": "Spain",
            "countryCode": "ES", "lat": 41.39, "lon": 2.17}}

for view in ("offline", "online"):
    mode = "offline" if view == "offline" else "online"
    recs = [rec(1, {"title": "Выпить кофе", "topics": ["coffee"]}, mode),
            rec(2, {"title": "Сходить на свидание", "topics": ["walk"], "type": "dating"}, mode),
            rec(3, {"title": "Сходить на свидание", "topics": ["coffee"]}, mode)]
    feed = imf.build_feed(recs, view=view, limit=10, geocoder=None, geocode_budget=0)
    titles = [str((it.get("intent") or {}).get("title") or it.get("title") or "") for it in feed.get("items", [])]
    check(view + ": кофе на месте", any("кофе" in t for t in titles))
    check(view + ": свиданий нет", not any("свидан" in t.lower() for t in titles))

print("map_dating_test: %d ok, %d fail" % (ok, bad))
sys.exit(1 if bad else 0)
