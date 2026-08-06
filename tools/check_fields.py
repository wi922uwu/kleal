#!/usr/bin/env python3
"""Сторож единого источника правды.

Проверяет три вещи:

  1. Копия реестра в приложении свежая (иначе приложение и сервер расходятся молча).
  2. Ключи строки пользователя, которые реально лежат в users.json, описаны в реестре, — и наоборот,
     реестр не обещает полей, которых в данных нет.
  3. Экраны приложения не пишут серверные имена полей строкой мимо адаптера.

Пункт 3 намеренно ПРЕДУПРЕЖДАЕТ, а не валит: в бекенде 31 тысяча строк, писавшихся до реестра, и
переписать их разом — отдельная работа с риском. Но новое расхождение видно сразу, а это и было
целью: расхождения должны находиться при правке, а не через неделю по жалобе.

    python3 tools/check_fields.py                     # проверить всё
    python3 tools/check_fields.py --users <файл>      # плюс сверить с настоящим хранилищем
    python3 tools/check_fields.py --strict            # предупреждения тоже считать ошибкой
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "kleal-ms", "shared"))
import fields as F  # noqa: E402

APP = os.path.join(ROOT, "kleal-app")

# Где серверным именам полей быть МОЖНО: сам реестр, адаптеры, генератор и этот сторож.
ALLOWED = (
    "kleal-app/src/fields.ts",
    "kleal-app/src/fields.generated.ts",
    "kleal-ms/shared/fields.py",
    "kleal-ms/shared/fields.json",
    "tools/sync_fields.py",
    "tools/check_fields.py",
)

# Имена, которые в приложении не должны появляться строкой: это ИМЕНА СЕРВЕРА. Взяты из реестра,
# а не выписаны здесь, — иначе сторож сам стал бы вторым источником правды.
def server_only_keys():
    out = set()
    for name, f in F.FACTS.items():
        row, app = f.get("row"), f.get("app")
        if row and app and str(row).split(".")[0] != str(app).split(".")[0]:
            out.add(str(row).split(".")[0])
    return sorted(out)


def sh(cmd):
    return subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True, text=True).stdout


def check_generated():
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "sync_fields.py"), "--check"],
                       cwd=ROOT, capture_output=True, text=True)
    return r.returncode == 0, r.stdout.strip()


def check_store(path):
    """Сверить реестр с настоящими данными. Читает файл, ничего не меняет."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    users = data.get("users") if isinstance(data, dict) else data
    users = users or []
    seen = {}
    for u in users:
        if isinstance(u, dict):
            for k in u:
                seen[k] = seen.get(k, 0) + 1
    known = set(F.all_row_keys())
    unknown = sorted(k for k in seen if k not in known)
    missing = sorted(k for k in known if k not in seen)
    return len(users), seen, unknown, missing


def check_literals():
    hits = []
    for key in server_only_keys():
        out = sh("grep -rn \"['\\\"]%s['\\\"]\" kleal-app/app kleal-app/src 2>/dev/null" % key)
        for line in out.splitlines():
            path = line.split(":", 1)[0]
            if any(path.startswith(a) for a in ALLOWED):
                continue
            hits.append((key, line.strip()[:150]))
    return hits


def main():
    users_path = None
    if "--users" in sys.argv:
        users_path = sys.argv[sys.argv.index("--users") + 1]
    strict = "--strict" in sys.argv
    problems, warnings = [], []

    ok, msg = check_generated()
    print("1. копия реестра в приложении:", "свежая" if ok else "УСТАРЕЛА")
    if not ok:
        problems.append(msg)

    print("2. поля реестра: %d фактов, %d ключей строки" % (len(F.FACTS), len(F.all_row_keys())))
    if users_path:
        n, seen, unknown, missing = check_store(users_path)
        print("   хранилище %s: %d строк" % (users_path, n))
        if unknown:
            warnings.append("в данных есть поля, которых нет в реестре: %s" % ", ".join(unknown))
        if missing:
            warnings.append("реестр обещает поля, которых нет ни в одной строке: %s" % ", ".join(missing))
        for w in (unknown, missing):
            pass
        print("   неописанных полей: %d, обещанных но отсутствующих: %d" % (len(unknown), len(missing)))

    hits = check_literals()
    print("3. серверные имена полей строкой в приложении: %d" % len(hits))
    for key, line in hits[:20]:
        warnings.append("«%s» мимо адаптера: %s" % (key, line))

    if warnings:
        print("\nПРЕДУПРЕЖДЕНИЯ:")
        for w in warnings:
            print("  -", w)
    if problems:
        print("\nОШИБКИ:")
        for p in problems:
            print("  -", p)

    return 1 if problems or (strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
