# -*- coding: utf-8 -*-
"""Детерминированный генератор синтетического пула пользователей для стенда матчинга.

Единственный источник пула. sha1/hashlib-сидинг => одинаковый вывод во всех процессах и прогонах
(seed-independent). Оркестратор (`kleal_sim.py`) вызывает `gen_users(N)` РАЗ, пишет в `pool.json`,
и раздаёт этот файл всем воркерам через env `KLEAL_USERS`. Воркеры этот модуль не импортируют —
они читают готовый `pool.json`. Извлечено дословно из прежнего `kleal_sim.py`."""
import hashlib, math

NOW = 1752600000.0                                  # пиннутые часы -> детерминизм TTL/времени
BCN = (41.3874, 2.1686)                             # центр «поиска» (Барселона)

TOPICS = ["coffee", "chess", "dota", "football", "hiking", "spanish", "coding", "art", "music", "cooking",
          "yoga", "photography", "cycling", "boardgames", "wine", "books", "startups", "padel", "running",
          "jazz", "climbing", "tennis", "design", "gaming", "travel", "dancing", "meditation", "catalan",
          "cinema", "languages"]
VIBES = ["chill", "social", "deep", "energetic"]
LANGS = ["en", "es", "ca", "fr", "de", "it", "ru"]
ROLES = ["meet", "play", "watch", "discuss", "practise"]


def _h(i, salt):
    return int(hashlib.sha1(("%d:%s" % (i, salt)).encode("utf-8")).hexdigest(), 16)


def _offset(base, km, deg):
    lat, lon = base
    dlat = (km / 111.0) * math.cos(math.radians(deg))
    dlon = (km / (111.0 * math.cos(math.radians(lat)))) * math.sin(math.radians(deg))
    return round(lat + dlat, 5), round(lon + dlon, 5)


def gen_users(n):
    out = []
    for i in range(n):
        ni = 2 + _h(i, "nt") % 3
        ints = list(dict.fromkeys(TOPICS[_h(i, "t%d" % k) % len(TOPICS)] for k in range(ni)))
        nl = 1 + _h(i, "nl") % 2
        langs = list(dict.fromkeys(LANGS[_h(i, "l%d" % k) % len(LANGS)] for k in range(nl)))
        km = round((_h(i, "km") % 1600) / 100.0, 1)             # 0..16 км
        lat, lon = _offset(BCN, km, _h(i, "ang") % 360)
        u = {"name": "U%04d" % (i + 1), "interests": ints, "vibe": VIBES[_h(i, "v") % 4],
             "langs": langs, "age": 18 + _h(i, "age") % 42, "km": km, "lat": lat, "lon": lon,
             "coarseLat": lat, "coarseLon": lon, "role": ROLES[_h(i, "r") % len(ROLES)],
             "open": (_h(i, "o") % 5 != 0), "datingOk": (_h(i, "d") % 3 == 0),
             "verified": (_h(i, "ver") % 2 == 0), "source": "onboarding"}
        if _h(i, "rc") % 2 == 0:
            u["receiving"] = {"status": "active"}
        out.append(u)
    return out
