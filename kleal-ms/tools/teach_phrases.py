# -*- coding: utf-8 -*-
"""Научить матчинг темам всех интересов популяции — один прогон.

    python3 tools/teach_phrases.py [https://aiopenware.com] [--limit N] [--workers 8]

ЗАЧЕМ. Мост через темы фильтрации работает только по РАЗОБРАННЫМ фразам: пока фраза матчингу
незнакома, `topic_bridge` честно отвечает «нет», и «опционы» не находят ни «finanzas», ни
«economía». Разбирать их в момент поиска нельзя — это вызов модели на каждый интерес каждого
кандидата, то есть секунды на запрос. Поэтому разбор делается заранее и один раз.

ЧТО ИМЕННО ДЕЛАЕТСЯ. Берутся ВСЕ различные интересы из users.json, каждый спрашивается у
фильтрации (тот же вызов, что и при регистрации, так что кэш у неё тёплый), и пара «фраза -> темы»
уезжает в матчинг ручкой /api/agent/learn-phrases.

Прогон идёмпотентен: уже известные фразы с тем же набором тем не перезаписываются, и повторный
запуск ничего не портит. Пустой ответ фильтрации не запоминается — «не понял» не должен затирать
то, что понято раньше.
"""
import argparse
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def post(base, path, body, timeout=120):
    r = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                               headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=timeout).read().decode())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base", nargs="?", default="https://aiopenware.com")
    ap.add_argument("--users", default=os.path.join(ROOT, "users.json"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--batch", type=int, default=100)
    a = ap.parse_args()
    base = a.base.rstrip("/")

    with open(a.users, encoding="utf-8") as f:
        data = json.load(f)
    users = data.get("users") if isinstance(data, dict) else data

    seen, phrases = set(), []
    for u in users or []:
        for it in (u.get("interests") or []):
            p = " ".join(str(it).lower().split())
            if p and p not in seen:
                seen.add(p)
                phrases.append(str(it))
    if a.limit:
        phrases = phrases[:a.limit]
    print("людей: %d, различных интересов: %d" % (len(users or []), len(phrases)))

    def ask(text):
        try:
            d = post(base, "/api/filter/categorize", {"text": text}, timeout=120)
            ts = [str(t).lower().strip() for t in (d.get("topics") or []) if str(t).strip()]
            return {"phrase": text, "topics": ts} if ts else None
        except Exception:
            return None

    print("спрашиваем фильтрацию, потоков %d…" % a.workers)
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        items = [x for x in ex.map(ask, phrases) if x]
    print("разобрано: %d из %d" % (len(items), len(phrases)))
    if not items:
        print("нечему учить — проверь, жива ли фильтрация")
        return 1

    added = 0
    for i in range(0, len(items), a.batch):
        chunk = items[i:i + a.batch]
        try:
            r = post(base, "/api/agent/learn-phrases", {"items": chunk}, timeout=120)
            added += int(r.get("added") or 0)
            print("  пачка %-4d новых: %-5s всего известно: %s"
                  % (i // a.batch + 1, r.get("added"), r.get("known")))
        except Exception as e:
            print("  пачка %d не прошла: %s" % (i // a.batch + 1, str(e)[:100]))
    print("\nвыучено новых фраз: %d" % added)
    return 0


if __name__ == "__main__":
    sys.exit(main())
