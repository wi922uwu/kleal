#!/usr/bin/env python3
"""Перенести реестр полей в приложение.

Реестр живёт один — kleal-ms/shared/fields.json. Приложение не может его импортировать напрямую:
Metro не выпускает сборку за пределы каталога проекта, а копия, которую правят руками, перестаёт
быть копией в первый же день. Поэтому файл ГЕНЕРИРУЕТСЯ, помечен как сгенерированный, и его
свежесть проверяет tools/check_fields.py.

    python3 tools/sync_fields.py          # обновить
    python3 tools/sync_fields.py --check   # только проверить, что копия свежая (код возврата 1 если нет)
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "kleal-ms", "shared", "fields.json")
DST = os.path.join(ROOT, "kleal-app", "src", "fields.generated.ts")

HEAD = """/**
 * СГЕНЕРИРОВАННЫЙ ФАЙЛ. Не править руками.
 *
 * Источник: kleal-ms/shared/fields.json
 * Обновить: python3 tools/sync_fields.py
 *
 * Реестр полей профиля — единственное место, где написано, как называется та или иная вещь про
 * человека в приложении и в строке пользователя на сервере. Пользоваться им нужно через src/fields.ts,
 * а не читать отсюда напрямую.
 */

export type FieldFact = {
  meaning: string;
  /** Путь в профиле приложения. null — приложение этот факт не хранит. */
  app: string | null;
  /** Ключ в строке users.json. null — на сервере такого поля нет. */
  row: string | null;
  patchable: boolean;
  quirks: string[];
};

export const FIELDS_VERSION = %(version)d;

export const FIELDS: Record<string, FieldFact> = %(facts)s;
"""


def build():
    with open(SRC, "r", encoding="utf-8") as f:
        reg = json.load(f)
    facts = {}
    for name, f in reg["facts"].items():
        facts[name] = {
            "meaning": f.get("meaning", ""),
            "app": f.get("app"),
            "row": f.get("row"),
            "patchable": bool(f.get("patchable")),
            "quirks": list(f.get("quirks") or []),
        }
    body = json.dumps(facts, ensure_ascii=False, indent=2)
    return HEAD % {"version": int(reg.get("version") or 1), "facts": body}


def main():
    out = build()
    check = "--check" in sys.argv
    old = ""
    if os.path.exists(DST):
        with open(DST, "r", encoding="utf-8") as f:
            old = f.read()
    if old == out:
        print("копия свежая: %s" % os.path.relpath(DST, ROOT))
        return 0
    if check:
        print("УСТАРЕЛО: %s расходится с реестром. Запустите python3 tools/sync_fields.py"
              % os.path.relpath(DST, ROOT))
        return 1
    os.makedirs(os.path.dirname(DST), exist_ok=True)
    with open(DST, "w", encoding="utf-8") as f:
        f.write(out)
    print("обновлено: %s" % os.path.relpath(DST, ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
