# -*- coding: utf-8 -*-
"""Свести интересы всей популяции к английским ключам; подписи — в общий словарь.

    python3 tools/migrate_interests_en.py --dry-run     # показать, ничего не менять
    python3 tools/migrate_interests_en.py               # перевести и сохранить (бэкап обязателен)
    python3 tools/migrate_interests_en.py --labels      # дозаполнить ru/es подписи у ключей

ПОРЯДОК ВНУТРИ ПРОГОНА. Сначала ОДИН проход по уникальным формулировкам: словарь, канон
(только дословные совпадения с узлом), затем модель батчами по 12 — так «craft beer» семнадцати
человек переводится один раз. Только потом переписываются строки людей: на этом шаге всё уже
в словаре, и to_en не делает ни одного сетевого вызова.

ЧТО СОХРАНЯЕТСЯ. Собственная формулировка человека становится подписью её языка и не
перезаписывается сгенерированной (правило learn в shared/interest_i18n.py). Дубли после
свёртки схлопываются: у кого лежало «sketch» и «sketching», останется один «drawing» — это
машинные ручки и сворачиваются они в один честный ключ.

ИДЕМПОТЕНТНО: второй запуск находит все слова в словаре и меняет ноль строк.
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "shared"))

import db                # noqa: E402
import interest_i18n as ii   # noqa: E402
from llm_client import llm_complete  # noqa: E402
import config            # noqa: E402

BATCH = 12


def translate(batch):
    sys_p = ("You translate personal interests for a social app. For EVERY input line return one "
             "object {\"en\",\"ru\",\"es\"}: a short natural interest phrase (max 4 words) in each "
             "language, preserving the SPECIFIC meaning (sea fishing, not fishing). No extra text — "
             "answer with a JSON array only, same order and count as the input lines.")
    raw = llm_complete(config.MODEL_ID, [{"role": "system", "content": sys_p},
                                         {"role": "user", "content": "\n".join(batch)}], 0.2)
    # Батч из одного слова модель отдаёт голым объектом — принимаем оба вида (см. onboarding).
    try:
        rows = json.loads(raw[raw.index("["):raw.rindex("]") + 1])
        if isinstance(rows, list) and len(rows) == len(batch):
            return rows
    except Exception:
        pass
    try:
        one = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        return [one] if isinstance(one, dict) and len(batch) == 1 else []
    except Exception:
        return []
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--labels", action="store_true",
                    help="только дозаполнить ru/es подписи существующих ключей")
    a = ap.parse_args()

    users = db.load_users() or []
    print("людей: %d, хранилище: %s, словарь: %s" % (len(users), db.MODE, ii.PATH))

    if a.labels:
        # -------- фаза Б: подписи для ключей, у которых их ещё нет --------
        need = []
        data = ii._load()
        keys = sorted({ii._norm(w) for u in users for w in (u.get("interests") or []) if str(w).strip()})
        for k in keys:
            row = data.get(k) or {}
            if not row.get("ru") or not row.get("es"):
                need.append(k)
        print("ключей всего: %d, без полных подписей: %d" % (len(keys), len(need)))
        if a.dry_run:
            return 0
        done = 0
        for i in range(0, len(need), BATCH):
            batch = need[i:i + BATCH]
            for k, row in zip(batch, translate(batch) or [{}] * len(batch)):
                if (row or {}).get("ru") or (row or {}).get("es"):
                    ii.learn(k, ru=(row or {}).get("ru"), es=(row or {}).get("es"))
                    done += 1
            print("   %d/%d…" % (min(i + BATCH, len(need)), len(need)))
        print("дозаполнено: %d" % done)
        return 0

    # -------- фаза А, шаг 1: выучить все уникальные формулировки --------
    uniq, seen = [], set()
    for u in users:
        for w in (u.get("interests") or []):
            w = " ".join(str(w or "").split())
            k = w.lower()
            if w and k not in seen:
                seen.add(k)
                uniq.append(w)
    print("уникальных формулировок: %d" % len(uniq))
    free = ii.to_en(uniq)                       # словарь + канон + латиница, БЕЗ модели
    unresolved = [w for w in uniq if not ii.key_of(w) and ii.lang_of(w) != "en"]
    print("после словаря и канона осталось перевести моделью: %d" % len(unresolved))
    if not a.dry_run:
        for i in range(0, len(unresolved), BATCH):
            batch = unresolved[i:i + BATCH]
            ii.to_en(batch, translate=translate)
            print("   %d/%d…" % (min(i + BATCH, len(unresolved)), len(unresolved)))

    # -------- фаза А, шаг 2: переписать строки (всё уже в словаре) --------
    changed, backup = [], {}
    for u in users:
        old = [str(w) for w in (u.get("interests") or [])]
        if not old:
            continue
        new = ii.to_en(old)[:8]
        if new != old:
            backup[u.get("name")] = old
            if not a.dry_run:
                u["interests"] = new
                changed.append(u)
    print("строк к изменению: %d из %d" % (len(backup), len(users)))
    for nm, old in list(backup.items())[:6]:
        print("   %-24s %s" % (str(nm)[:24], " | ".join(old[:3])[:60]))
        print("   %-24s -> %s" % ("", " | ".join(ii.to_en(old)[:3])[:60]))
    if a.dry_run or not changed:
        return 0
    bpath = os.path.join(ROOT, "interests_backup.%d.json" % int(time.time()))
    with open(bpath, "w", encoding="utf-8") as f:
        json.dump(backup, f, ensure_ascii=False, indent=0)
    print("бэкап прежних интересов: %s" % bpath)
    for u in changed:
        db.save_user(u)
    print("сохранено строк: %d" % len(changed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
