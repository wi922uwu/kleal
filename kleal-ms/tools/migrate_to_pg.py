# -*- coding: utf-8 -*-
"""Перенести users.json и kleal_store.json в PostgreSQL — и проверить, что перенеслось.

    python3 tools/migrate_to_pg.py            # перенести и сверить
    python3 tools/migrate_to_pg.py --check    # только сверить, ничего не писать

ИДЕМПОТЕНТНО: повторный запуск переписывает те же строки теми же значениями. Это важно не ради
удобства, а ради порядка выкладки — перенос делается ДО переключения флага, на живом сервисе,
который в это время продолжает писать в файлы; второй прогон догоняет то, что изменилось между.

СВЕРКА ОБЯЗАТЕЛЬНА И ИДЁТ ПО СОДЕРЖИМОМУ, а не по числу строк. Совпадение количеств — это ровно
та проверка, которая пропускает подмену: 714 строк с пустыми профилями тоже 714.
"""
import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "shared"))
sys.path.insert(0, os.path.join(ROOT, "services", "matching"))

os.environ.setdefault("KLEAL_DB", "postgres")      # инструмент всегда работает с базой
import db  # noqa: E402


def _norm_numbers(v):
    """Привести числа к канону перед сравнением.

    JSONB хранит числа как numeric — точно, но в своей записи: `1e+18` из файла читается обратно
    как `1000000000000000000`. Значение то же, текст другой, и сверка по тексту объявила бы
    расхождение там, где не потеряно ничего. Проверено на живом переносе: ровно два плана из
    восьмидесяти одного, оба — тестовые «встречи через 31 миллиард лет» из mplan_smoke.

    Целое, записанное как float, становится int; остальное не трогаем — округлять настоящие
    дроби значило бы прятать настоящую потерю.
    """
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, dict):
        return {k: _norm_numbers(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_norm_numbers(x) for x in v]
    return v


def _digest(v):
    return hashlib.sha256(json.dumps(_norm_numbers(v), ensure_ascii=False, sort_keys=True,
                                     default=str).encode()).hexdigest()


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", default=os.path.join(ROOT, "users.json"))
    ap.add_argument("--store", default=os.path.join(ROOT, "services", "matching", "kleal_store.json"))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()

    print("база: %s" % db.DSN.split("@")[-1])
    db.ensure_schema()

    data = _read_json(a.users, {})
    users = data.get("users") if isinstance(data, dict) else data
    users = users if isinstance(users, list) else []
    store = _read_json(a.store, {})

    print("в файлах: %d человек, %d ключей состояния" % (len(users), len(store)))

    if not a.check:
        n = db.save_users(users)
        print("перенесено людей: %d" % n)
        keys = db.save_store(store)
        print("перенесено ключей состояния: %d" % keys)

    # ---- сверка по содержимому ------------------------------------------------------------
    bad = []
    got_users = db.load_users() or []
    by_key = {" ".join(str(u.get("name") or "").lower().split()): u for u in got_users}
    for u in users:
        k = " ".join(str(u.get("name") or "").lower().split())
        if not k:
            continue
        if k not in by_key:
            bad.append("нет в базе: %s" % u.get("name"))
        elif _digest(by_key[k]) != _digest(u):
            bad.append("расходится: %s" % u.get("name"))

    got_store = db.load_store() or {}
    for k, v in store.items():
        if k not in got_store:
            bad.append("нет ключа состояния: %s" % k)
        elif _digest(got_store[k]) != _digest(v):
            bad.append("расходится ключ состояния: %s" % k)

    print("\nв базе: %d человек, %d ключей состояния" % (len(got_users), len(got_store)))
    if bad:
        print("РАСХОЖДЕНИЙ: %d" % len(bad))
        for b in bad[:20]:
            print("   " + b)
        return 1
    print("сверка по содержимому: всё совпало")
    return 0


if __name__ == "__main__":
    sys.exit(main())
