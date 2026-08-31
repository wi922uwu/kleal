# -*- coding: utf-8 -*-
"""Связать существующие строки профилей с аккаунтами: проставить поле `owner`.

ЗАЧЕМ. Личность в этом проекте до 28.08 была ИМЕНЕМ: строка находилась по имени из тела запроса,
а идентификатор считался как sha1(имя). Проверки владельца теперь опираются на поле `owner`, но у
живых строк его нет — оно появляется только у тех, кто зарегистрировался после правки. Пока связки
нет, включение проверок выкинуло бы из поиска всех, кто вошёл раньше.

СВЯЗЬ БЕРЁТСЯ ИЗ АККАУНТА, а не угадывается: `attach_profile` записывает в аккаунт имя анкеты,
которую к нему привязали. Это единственная существующая память о том, чей профиль, и подменить её
из запроса нельзя.

ЧТО ПРОПУСКАЕТСЯ МОЛЧА — НИЧЕГО. Любая неоднозначность (два аккаунта на одно имя, две строки на
одно имя) не связывается и попадает в отчёт: угадать здесь значит отдать чужой профиль.

Запуск: python3 link_owners.py            — только показать
        python3 link_owners.py --apply    — записать
"""
import collections
import json
import os
import shutil
import sys
import time

sys.path.insert(0, "shared")
sys.path.insert(0, ".")

APPLY = "--apply" in sys.argv


def nk(x):
    return str(x or "").strip().lower()


acc = json.load(open("accounts.json", encoding="utf-8"))
raw = json.load(open("users.json", encoding="utf-8"))
rows = raw["users"] if isinstance(raw, dict) and "users" in raw else raw

claim = collections.defaultdict(list)
for key, a in acc.items():
    nm = nk((a or {}).get("name"))
    if nm:
        claim[nm].append(key)

by_name = collections.defaultdict(list)
for u in rows:
    by_name[nk(u.get("name"))].append(u)

link, already, no_row, amb_acc, amb_row = [], 0, 0, [], []
for nm, keys in claim.items():
    if len(keys) > 1:
        amb_acc.append(nm)
        continue
    if nm not in by_name:
        no_row += 1
        continue
    if len(by_name[nm]) > 1:
        amb_row.append(nm)
        continue
    row = by_name[nm][0]
    if row.get("owner"):
        already += 1
        continue
    link.append((row, keys[0]))

print("аккаунтов: %d, из них с именем: %d" % (len(acc), len(claim)))
print("строк: %d, уже с owner: %d" % (len(rows), sum(1 for u in rows if u.get("owner"))))
print()
print("СВЯЖЕТСЯ:                      %d" % len(link))
print("уже связано:                   %d" % already)
print("аккаунт есть, строки нет:      %d" % no_row)
print("два аккаунта на одно имя:      %d  (пропуск)" % len(amb_acc))
print("две строки на одно имя:        %d  (пропуск)" % len(amb_row))

if not APPLY:
    print("\nэто был показ. Записать: --apply")
    sys.exit(0)
if not link:
    print("\nсвязывать нечего")
    sys.exit(0)

for row, key in link:
    row["owner"] = key

shutil.copy2("users.json", "users.json.bak_owners_%s" % time.strftime("%Y%m%d_%H%M%S"))
wrote_db = False
try:
    import db
    if db.ENABLED:
        db.save_users(rows)
        wrote_db = True
        print("\nв базу записано (одной транзакцией)")
except Exception as e:
    print("\nбаза не приняла (%s: %s) — пишу только файл" % (type(e).__name__, str(e)[:100]))

tmp = "users.json.tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(raw, f, ensure_ascii=False)
os.replace(tmp, "users.json")
print("файл записан. База: %s" % ("да" if wrote_db else "НЕТ"))
