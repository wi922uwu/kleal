#!/usr/bin/env python3
"""Доля карточек, где в темах есть слово, не сводимое ни в какой ключ.

ЗАЧЕМ ОТДЕЛЬНАЯ МЕРКА. Клиент рисует чипы карточки из `topics` (kleal-app/src/buddy.ts, topicsOf),
и то же поле уходит в поиск. Значит несводимое слово человек ВИДИТ: «дюбит», «улице», «year»,
«girl» в живых затеях владельца. Батарея это почти не судит — `МУСОР В ТЕМАХ` ловит только
служебные слова из стоп-листа.
"""
import json, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/opt/kleal/kleal-ms")
from services.buddy.app import norm_topic  # noqa: E402

URL = "http://127.0.0.1:7075/buddy/chat"


def post(p, tries=2):
    for a in range(tries):
        try:
            req = urllib.request.Request(URL, data=json.dumps(p).encode(),
                                         headers={"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=150).read().decode())
        except Exception:
            if a + 1 >= tries:
                return {}
    return {}


def walk(sc):
    msgs, last = [], None
    for s in sc.get("says") or []:
        msgs.append({"role": "user", "content": s})
        r = post({"user_id": "dirt-" + str(sc.get("label")), "messages": msgs,
                  "lang": sc.get("lang") or "ru", "profile": {}})
        if not r:
            return None
        msgs.append({"role": "assistant", "content": r.get("reply") or ""})
        if r.get("intent"):
            last = r["intent"]
    return last


def main():
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    scen = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8") if l.strip()][:n]
    with ThreadPoolExecutor(max_workers=6) as pool:
        cards = list(pool.map(walk, scen))
    built = dirty = 0
    tops_tot = dirt_tot = 0
    ex = []
    for sc, it in zip(scen, cards):
        if not it:
            continue
        built += 1
        tops = [str(t) for t in (it.get("topics") or [])]
        bad = [t for t in tops if not norm_topic(t)]
        tops_tot += len(tops)
        dirt_tot += len(bad)
        if bad:
            dirty += 1
            if len(ex) < 8:
                ex.append("«%s» темы=%s мусор=%s" % (it.get("title"), tops, bad))
    print("МУСОР В ТЕМАХ: сценариев %d, собралось %d" % (len(scen), built))
    print("   карточек с несводимой темой: %d  (%.3f)" % (dirty, dirty / max(built, 1)))
    print("   тем всего %d, из них несводимых %d  (%.3f)" % (tops_tot, dirt_tot, dirt_tot / max(tops_tot, 1)))
    for e in ex:
        print("     ", e)


if __name__ == "__main__":
    main()
