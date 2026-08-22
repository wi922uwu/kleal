# -*- coding: utf-8 -*-
"""Проверить засеянную популяцию: ЖИВЫМ поиском и цифрами по хранилищу.

    python3 tools/cohort_check.py [адрес-шлюза] [--users путь]

ЗАЧЕМ ОТДЕЛЬНО ОТ СМОУКОВ. Смоуки проверяют ПОВЕДЕНИЕ сервера: что заявка создаётся, что чужой
адрес не виден. Они пройдут и на пустом хранилище — им хватает двух людей, которых они заводят
сами. Здесь проверяется ПОПУЛЯЦИЯ: есть ли в ней кого искать и правда ли она разная.

Это ровно тот отказ, который не выглядит отказом: поиск по плохому посеву отвечает «никого не
нашлось» — тем же ответом, что и при честно пустой выдаче. Отличить одно от другого можно только
цифрами, поэтому они здесь и считаются.

Запускать НА СЕРВЕРЕ: цифры берутся из users.json напрямую, чтобы не зависеть от админского
токена и не тащить 600 человек по сети.
"""
import argparse
import collections
import json
import os
import sys
import urllib.request

R = {"ok": 0, "fail": 0}
BAD = []


def check(name, cond, detail=""):
    R["ok" if cond else "fail"] += 1
    if not cond:
        BAD.append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (("   " + str(detail)[:170]) if detail else ""))


def post(gw, path, body, timeout=180):
    req = urllib.request.Request(gw + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


# Запросы намеренно бьют в РАЗНЫЕ ветки таксономии и на разных языках. Популяция, в которой
# находится только «кофе», бесполезна ровно так же, как пустая, — но выглядит рабочей.
QUERIES = [
    ("скалолазание", {"topics": ["climbing", "bouldering"], "type": "sport", "role": "play"}),
    ("настолки", {"topics": ["boardgames"], "type": "gaming", "role": "play"}),
    ("испанский язык", {"topics": ["spanish", "language"], "type": "language", "role": "practise"}),
    ("стартапы", {"topics": ["startups", "networking"], "type": "professional", "role": "meet"}),
    ("бар вечером", {"topics": ["bar", "drinks"], "type": "social", "role": "meet"}),
    ("прогулка с собакой", {"topics": ["dogs", "walk"], "type": "outdoor", "role": "meet"}),
    ("музей", {"topics": ["museum", "art"], "type": "culture", "role": "attend"}),
    ("плавание", {"topics": ["swimming"], "type": "sport", "role": "play"}),
    ("кино дома", {"topics": ["movies", "series"], "type": "watch", "role": "watch"}),
    ("волонтёрство", {"topics": ["volunteering", "community"], "type": "social", "role": "meet"}),
]

PROF = {"name": "ПроверкаПопуляции", "age": 30, "gender": "", "city": "Barcelona",
        "geo": {"located": True, "coarseLat": 41.3915, "coarseLon": 2.1630, "maxDistanceKm": 30},
        "languages": {"comfortable": ["en", "es", "ru"]},
        "interests": {"explicit": ["coffee"]}}


def live_search(gw):
    print("\n-- живой поиск по разным веткам")
    empty = []
    for name, intent in QUERIES:
        try:
            m = post(gw, "/api/agent/match", {"intent": intent, "profile": PROF,
                                              "ctx": {"self": PROF["name"]}})
        except Exception as e:
            check("поиск «%s»" % name, False, "%s: %s" % (type(e).__name__, str(e)[:90]))
            empty.append(name)
            continue
        cands = (m or {}).get("candidates") or []
        check("«%s» -> %d человек" % (name, len(cands)), len(cands) >= 3,
              "меньше трёх — по этой ветке популяции фактически нет")
        if not cands:
            empty.append(name)
    check("пустых веток нет", not empty, "пусто по: %s" % ", ".join(empty))


def numbers(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    rows = d.get("users") if isinstance(d, dict) else d
    print("\n-- цифры популяции (%s)" % path)

    check("людей в популяции", len(rows) >= 400, len(rows))

    ints = collections.Counter(i for x in rows for i in (x.get("interests") or []))
    check("разных интересов", len(ints) >= 200, len(ints))
    if ints:
        w, n = ints.most_common(1)[0]
        check("нет одного интереса на всех", n < len(rows) * 0.25,
              "самый частый «%s» у %.0f%%" % (w, 100.0 * n / len(rows)))
    # Уникальный интерес — признак того, что людей ПИСАЛИ, а не размножили из списка.
    once = sum(1 for _, n in ints.items() if n == 1)
    check("есть интересы, встречающиеся один раз", once >= 100, once)

    check("городов", len({x.get("area") for x in rows}) >= 8, len({x.get("area") for x in rows}))

    tzs = {x.get("tz") for x in rows if x.get("tz")}
    check("часовых поясов", len(tzs) >= 8, len(tzs))
    check("пояс есть почти у всех", sum(1 for x in rows if x.get("tz")) >= len(rows) * 0.9,
          sum(1 for x in rows if x.get("tz")))
    # Жёсткое «Мадрид всем» держалось ровно до появления людей из других поясов.
    offs = {(x.get("receiving") or {}).get("quiet_hours", {}).get("tz_offset_min") for x in rows}
    check("тихие часы считаны по своему поясу, а не по одному", len(offs) >= 5, sorted(offs))

    check("персона заполнена у большинства",
          sum(1 for x in rows if (x.get("persona") or {}).get("axes")) >= len(rows) * 0.8)
    check("история есть у большинства",
          sum(1 for x in rows if x.get("story")) >= len(rows) * 0.8)

    # Перекос по одной оси характера значит, что «характеры» написаны формально.
    ax = collections.Counter()
    for x in rows:
        for k, v in ((x.get("persona") or {}).get("axes") or {}).items():
            ax[(k, v)] += 1
    for axis in ("energy", "group", "planning"):
        vals = {v: n for (k, v), n in ax.items() if k == axis}
        tot = sum(vals.values()) or 1
        top = max(vals.values()) if vals else 0
        check("ось %s не схлопнута в одно значение" % axis, vals and top < tot * 0.7,
              {k: v for k, v in sorted(vals.items(), key=lambda t: -t[1])})

    ages = [x.get("age") for x in rows if isinstance(x.get("age"), int)]
    check("возраст разбросан", ages and (max(ages) - min(ages)) >= 30,
          "%d–%d" % (min(ages), max(ages)) if ages else "нет")
    g = collections.Counter(x.get("gender") for x in rows)
    check("пол не однороден", len([v for v in g.values() if v > 5]) >= 2, dict(g))
    langs = collections.Counter(l for x in rows for l in (x.get("langs") or []))
    check("языков больше пяти", len(langs) >= 5, dict(langs.most_common(8)))
    check("романтике открыто меньшинство",
          0 < sum(1 for x in rows if x.get("datingOk")) < len(rows) * 0.5,
          sum(1 for x in rows if x.get("datingOk")))

    # Одинаковое начало текстов — самый честный признак «одного автора на всех».
    starts = collections.Counter(" ".join(str(x.get("summary") or "").split()[:3]).lower()
                                 for x in rows if x.get("summary"))
    if starts:
        w, n = starts.most_common(1)[0]
        check("тексты начинаются по-разному", n < len(rows) * 0.05,
              "«%s» — у %d человек" % (w, n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gateway", nargs="?", default="https://aiopenware.com")
    ap.add_argument("--users", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "users.json"))
    a = ap.parse_args()

    print("=" * 76)
    print("ПОПУЛЯЦИЯ  ->  %s" % a.gateway)
    print("=" * 76)
    numbers(a.users)
    live_search(a.gateway)

    print("\n" + "=" * 76)
    print("РЕЗУЛЬТАТ: %d ok, %d проблем" % (R["ok"], R["fail"]))
    for b in BAD:
        print("  - " + b)
    print("=" * 76)
    sys.exit(1 if R["fail"] else 0)


if __name__ == "__main__":
    main()
