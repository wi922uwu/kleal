# -*- coding: utf-8 -*-
"""Убрать из сохранённых интересов концептуальные ручки, дописанные машиной.

ЧТО СЛУЧИЛОСЬ. `_canon_interests` дописывает интересам английские ручки от фильтрации, и стоп-лист
GENERIC часть из них пропустил: у человека с «mercado gastronómico» в интересах появилось голое
`market`, у «conversation group» — `talk`. Ранкер сравнивает буквально, поэтому поиск про акции
находил гастрономический рынок ПЕРВЫМ ТИРОМ: `market` == `market`, точнее некуда. Слова-понятия
льстят любому запросу своей области и врут через границу областей.

ЧТО ДЕЛАЕТ. Удаляет интерес, только если ОБА условия сразу:
  1) он из второй волны GENERIC (market/talk/quiet/business/product/trip/language) — список
     повторён здесь намеренно узким: чистим то, в чём уверены, а не всё, что похоже;
  2) он ВЫВОДИМ из другого интереса того же человека (лежит в темах моста для соседней фразы) —
     то есть доказуемо дописан машиной, а не введён человеком.

Никогда не трогает ничего другого. Всё удалённое пишется в резервную копию рядом с users.json —
откат это один запуск tools/restore-скрипта по этой копии (или руками: append обратно).

  python3 tools/strip_generic_handles.py --dry-run   # показать, ничего не менять
  python3 tools/strip_generic_handles.py             # вычистить и сохранить через db

Хранилище — через shared/db, тем же режимом, что у сервисов (KLEAL_DB), так что json/postgres/
mirror обслуживаются одинаково и «кнопка Сохранить» ни для кого не врёт.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "shared"))
sys.path.insert(0, os.path.join(ROOT, "services", "matching"))

import db  # noqa: E402

# Первая волна — найдена по жалобе на выдачу («Акции» приводили гастрономический рынок).
# Вторая — отобрана при разборе дыр таксономии: слова, которым разборщики ОТКАЗАЛИ в узле и
# в алиасе именно как понятиям-зонтикам («fitness накрывает всю семью тренировок», «design
# одинаково подходит столяру и интерфейсному дизайнеру»). Тот же критерий, независимая оценка.
#
# Проверено на живой выдаче: запрос «дизайн интерфейсов» ставил в первый ярус столяра с ручкой
# `design` от «design collaboration», а людей с настоящим `ux design` — во второй.
STRIP = {
    "market", "talk", "quiet", "business", "product", "trip", "language",
    "fitness", "job", "data", "management", "clothes", "socialize", "nature", "family",
    "digital", "team", "performance", "training", "money", "design",
    # Найдено на живом экране: разговор про форекс приводил людей с ЯЗЫКОВЫМ обменом. Ручка
    # `exchange` дописана к «catalan language exchange», а тема запроса про валютный рынок тоже
    # свелась к `exchange` — два машинных расширения встретились на общем слове и дали точное
    # совпадение. Слово уже считается многозначным в _wshare и запрещено в алиасах; в профилях
    # ему тоже не место.
    "exchange", "обмен", "intercambio",
}


def _norm(s):
    return " ".join(str(s or "").lower().split())


def _phrase_topics():
    path = os.environ.get("KLEAL_PHRASE_TOPICS",
                          os.path.join(ROOT, "services", "matching", "phrase_topics.json"))
    try:
        with open(path, encoding="utf-8") as f:
            return {k: set(v) for k, v in json.load(f).items()}
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    pt = _phrase_topics()
    if not pt:
        print("мост тем пуст — выводимость проверить нечем, отказываюсь гадать")
        return 2
    users = db.load_users() or []
    print("людей: %d, режим хранилища: %s" % (len(users), db.MODE))

    touched, log = [], []
    for u in users:
        ints = [str(w) for w in (u.get("interests") or [])]
        norms = [_norm(w) for w in ints]
        drop = set()
        for i, w in enumerate(norms):
            if w not in STRIP:
                continue
            for j, o in enumerate(norms):
                if j != i and w in (pt.get(o) or ()):
                    drop.add(i)
                    break
        if not drop:
            continue
        removed = [ints[i] for i in sorted(drop)]
        kept = [ints[i] for i in range(len(ints)) if i not in drop]
        log.append({"name": u.get("name"), "removed": removed})
        print("   %-28s − %s" % (str(u.get("name"))[:28], ", ".join(removed)))
        if not a.dry_run:
            u["interests"] = kept
            touched.append(u)

    print("затронуто людей: %d" % len(log))
    if a.dry_run or not log:
        return 0

    backup = os.path.join(ROOT, "strip_handles.%d.json" % int(time.time()))
    with open(backup, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=1)
    print("резервная копия удалённого: %s" % backup)
    for u in touched:
        db.save_user(u)
    print("сохранено: %d" % len(touched))
    return 0


if __name__ == "__main__":
    sys.exit(main())
