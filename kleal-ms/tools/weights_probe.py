# -*- coding: utf-8 -*-
import os
# Инструмент меряет ранжирование по синтетическому пулу, который живой матчинг из выдачи исключает.
os.environ.setdefault("KLEAL_INCLUDE_LOADTEST", "1")
"""ГДЕ В БАЛЛЕ ЛЕЖИТ ИНФОРМАЦИЯ, А ГДЕ ВЕС ТРАТИТСЯ ВПУСТУЮ.

Балл кандидата — взвешенная сумма семи групп признаков (§9.3):
`mean = Σ(w·adjusted)/Σw`, `lcb = mean − λ·(1−coverage)`, и на экране показывается `lcb·100`.
Веса заданы руками в `config/Kleal_Matching_Core_Config_v2.yaml` по каждому домену.

Беда, которую видно батареей и не видно глазами: **48 % баллов в выдаче совпадают** (проверка
`granularity`, порог 70 %); на запросе «кофе» у восьми человек три разных балла. Когда баллы
сравнялись, порядок внутри полосы решает сортировка, а не смысл, — и «самый подходящий» человек
оказывается первым случайно.

Вес имеет смысл ровно настолько, насколько группа РАЗЛИЧАЕТ людей одной выдачи. Группа, которая у
всех восьмерых показывает одно и то же (или всегда «неизвестно» и подставляется prior), баллов не
двигает, а вес забирает — и отнимает его у той группы, которая различает. Этот инструмент считает
по каждой группе:

  ЗНАЮ      — доля карточек, где состояние known_match/known_mismatch (а не unknown/NA);
  ЗНАЧЕНИЙ  — сколько РАЗНЫХ значений группа принимает внутри одной выдачи (в среднем);
  РАЗМАХ    — max−min значения внутри выдачи (в среднем);
  РЫЧАГ     — w/Σw · РАЗМАХ · 100: на сколько баллов экрана группа способна развести
              лучшего и худшего в ОДНОЙ выдаче. Это и есть её реальный вклад в порядок.

Запуск (из настоящего дерева — конфиг ищется относительно `services/matching/app.py`):

    python3 tools/weights_probe.py --pool /tmp/pool.json [--json out.json] [--probes кофе,футбол]

Читает только: `match_candidates` (какая выдача) и `explain_match` (из чего сложился балл) —
те же функции, что у продукта. Ничего не пишет и веса не меняет.
"""
import argparse
import json
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "shared"))
sys.path.insert(0, os.path.join(ROOT, "services", "matching"))
os.environ.setdefault("KLEAL_STORE", os.path.join("/tmp", "weights_probe_store.json"))
os.environ["KLEAL_DB"] = "json"        # живую базу не трогаем ни на чтение, ни на запись

import app        # noqa: E402

NOW_OPEN = 1752600000.0                # 19:20 по месту — рабочие часы, как у батареи
TESTER = {"name": "Tester", "vibe": "chill", "geo": {"coarseLat": 41.391, "coarseLon": 2.164},
          "languages": {"comfortable": ["ru", "en"]}, "interests": []}

# Те же запросы, на которых батарея меряет гранулярность, — чтобы число «48 %» и эта таблица
# говорили об одном и том же.
PROBES = [["кофе"], ["coffee"], ["дота", "dota 2"], ["падель"], ["футбол"], ["книги"],
          ["испанский"], ["стартапы", "ai"], ["прогулка"], ["кино"], ["хайкинг"], ["рыбалка"],
          ["пиво"], ["йога"], ["шахматы"], ["коворкинг"], ["фотография"], ["бег"]]

KNOWN = ("known_match", "known_mismatch")


def load_pool(path):
    app.USERS_PATH = path
    app._users_cache = {"mtime": None, "list": None}
    with open(path, encoding="utf-8") as f:
        return json.load(f)["users"]


def slate_features(topics, now=NOW_OPEN):
    """(домен, [карточка]) — люди ИЗ ВЫДАЧИ вместе с разбором их балла.

    Выдачу даёт `match_candidates`, разбор — `explain_match`; сшиваем по имени. Брать один только
    разбор нельзя: он сортирует иначе (без класса решения и ротации), и «топ-8 разбора» — не те
    восемь человек, которых увидит живой человек."""
    intent = {"topics": topics, "type": "social", "role": "meet", "mode": "offline",
              "time": "Today evening"}
    ctx = {"self": TESTER["name"], "now": now}
    res = app.match_candidates(dict(intent), TESTER, dict(ctx))
    ex = app.explain_match(dict(intent), TESTER, dict(ctx)) or {}
    by_name = {m.get("name"): m for m in (ex.get("matched") or [])}
    cards = []
    for c in res:
        m = by_name.get(c.get("name"))
        if not m:
            continue                   # в выдаче есть, в разборе нет — считать по нему нечего
        cards.append({"name": c.get("name"), "score": c.get("score"),
                      "rows": (m.get("a_to_b") or {}).get("features") or []})
    return ex.get("domain"), (ex.get("domain_config") or {}).get("weights") or {}, cards


def spread(cards, key):
    """(доля «знаю», среднее число значений, средний размах, средний рычаг) по одной группе."""
    vals, known, tw_share, rng = [], 0, [], []
    for c in cards:
        row = next((r for r in c["rows"] if r.get("group") == key), None)
        if row is None or row.get("state") == "not_applicable":
            continue
        if row.get("state") in KNOWN:
            known += 1
        if row.get("value") is not None:
            vals.append(float(row["value"]))
        tw = sum(float(r.get("weight") or 0) for r in c["rows"] if r.get("state") != "not_applicable")
        if tw > 0:
            tw_share.append(float(row.get("weight") or 0) / tw)
    if not vals:
        return 0.0, 0, 0.0, 0.0
    return (known / float(len(cards)), len(set(round(v, 4) for v in vals)),
            max(vals) - min(vals), (statistics.fmean(tw_share) if tw_share else 0.0) * (max(vals) - min(vals)) * 100.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True)
    ap.add_argument("--json", default=None)
    ap.add_argument("--probes", default=None, help="через запятую: только эти темы")
    a = ap.parse_args()
    load_pool(a.pool)
    probes = [[t] for t in a.probes.split(",")] if a.probes else PROBES

    per_probe, agg = [], {}
    t0 = time.time()
    for topics in probes:
        domain, weights, cards = slate_features(topics)
        if len(cards) < 3:
            print("  %-14s — карточек %d, пропускаю" % (topics[0], len(cards)))
            continue
        scores = [c["score"] for c in cards]
        row = {"probe": topics[0], "domain": domain, "n": len(cards),
               "distinct_scores": len(set(scores)), "groups": {}}
        for k in app._core.FEATURE_KEYS:
            kn, nvals, rng, lever = spread(cards, k)
            row["groups"][k] = {"known": round(kn, 2), "values": nvals,
                                "range": round(rng, 3), "lever": round(lever, 2),
                                "weight": float(weights.get(k, 0) or 0)}
            d = agg.setdefault(k, {"known": [], "values": [], "range": [], "lever": [], "w": []})
            d["known"].append(kn); d["values"].append(nvals)
            d["range"].append(rng); d["lever"].append(lever); d["w"].append(float(weights.get(k, 0) or 0))
        per_probe.append(row)
        print("  %-14s %-16s %d карточек, разных баллов %d" %
              (topics[0], domain, row["n"], row["distinct_scores"]))

    print("\n%-22s %6s %6s %8s %7s %7s" % ("группа", "вес", "знаю", "значений", "размах", "рычаг"))
    print("-" * 62)
    order = sorted(agg.items(), key=lambda kv: -statistics.fmean(kv[1]["lever"]))
    for k, d in order:
        print("%-22s %6.2f %6.0f%% %8.1f %7.2f %7.2f"
              % (k, statistics.fmean(d["w"]), 100 * statistics.fmean(d["known"]),
                 statistics.fmean(d["values"]), statistics.fmean(d["range"]),
                 statistics.fmean(d["lever"])))
    tot = sum(statistics.fmean(d["lever"]) for _k, d in agg.items())
    dead = [k for k, d in agg.items() if statistics.fmean(d["lever"]) < 0.5]
    print("-" * 62)
    print("сумма рычагов: %.2f балла — столько баллов отделяют лучшего от худшего в одной выдаче" % tot)
    if dead:
        print("вес впустую (рычаг < 0.5 балла): %s — суммарно %.2f веса"
              % (", ".join(dead), sum(statistics.fmean(agg[k]["w"]) for k in dead)))
    sc = [r["distinct_scores"] for r in per_probe]
    n = [r["n"] for r in per_probe]
    print("разных баллов: %d из %d карточек (%.0f%%), худший запрос — «%s»: %d из %d"
          % (sum(sc), sum(n), 100.0 * sum(sc) / max(1, sum(n)),
             min(per_probe, key=lambda r: r["distinct_scores"])["probe"],
             min(sc), per_probe[min(range(len(sc)), key=lambda i: sc[i])]["n"]))
    print("(%d запросов за %.0f с)" % (len(per_probe), time.time() - t0))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"per_probe": per_probe,
                       "summary": {k: {m: round(statistics.fmean(v), 4) for m, v in d.items()}
                                   for k, d in agg.items()}}, f, ensure_ascii=False, indent=1)
        print("подробности: %s" % a.json)


if __name__ == "__main__":
    main()
