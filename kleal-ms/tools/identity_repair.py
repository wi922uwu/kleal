# -*- coding: utf-8 -*-
"""Перевод хранилища на «личность = id» и разбор записей, которые сделал беспорядок с именами.

    python3 tools/identity_repair.py report                 # только смотреть
    python3 tools/identity_repair.py migrate [--apply]       # таблица users: ключ по id вместо имени
    python3 tools/identity_repair.py plan.json [--apply]     # выполнить план разбора

БЕЗ --apply НИЧЕГО НЕ ПИШЕТСЯ. Сервисы onboarding и matching на время записи ОСТАНОВИТЬ: оба держат
своё состояние в памяти (accounts.json под замком онбординга, SESSION матчинга) и при следующей
записи молча вернули бы старое. Порядок: pg_dump → stop → migrate --apply → plan --apply → start.

ПОЧЕМУ ЭТО ЕСТЬ (26.09.2026, docs/IDENTITY.md). Таблица users держала первичный ключ по ИМЕНИ, и
каждый новый «Иван» при регистрации затирал анкету прежнего; интенты, планы и переписка тоже были
привязаны к имени и становились общими для всех тёзок. После перевода на id записи, сделанные до
него, надо развести по людям — автоматически (правило `_legacy_pid` в матчинге) там, где это
однозначно, и явным планом там, где нет.

Формат плана (аккаунт задаётся маской «первые 2 буквы…@домен», как её печатает `report`, чтобы
почты не приходилось переписывать руками):
{
  "restore_rows": [{"dump": "/var/backups/kleal/kleal-...dump", "id": "on72f4aeea"}],
  "rows_from_accounts": ["сл…@плад.сдмд"],           # анкета из снимка в аккаунте, id от аккаунта
  "own_rows": [{"id": "on9856fa6d", "account": "te…@gmail.com"}],   # строке без владельца — владелец
  "assign": {"_intents": {"in_1788185738027": "on72f4aeea"}}         # запись → id человека
}
После плана всем аккаунтам, владеющим ровно одной строкой, проставляется `person_id`.
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "shared"))


def _env():
    path = "/etc/kleal-infra.env"
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def mask(key):
    u, _, d = str(key).partition("@")
    return (u[:2] + "…@" + d) if d else str(key)[:6] + "…"


def _unescape_copy(s):
    """Текстовый формат COPY: \\\\ → \\, \\t, \\n и прочие. JSON внутри колонки не трогаем иначе."""
    out, i = [], 0
    m = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v", "\\": "\\"}
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s):
            nx = s[i + 1]
            if nx in m:
                out.append(m[nx])
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def row_from_dump(dump, uid):
    """Строка users с данным id из pg_dump (-Fc). Схема дампа — до перевода: name_key, name, row, updated."""
    txt = subprocess.run(["pg_restore", "--data-only", "-t", "users", "-f", "-", dump],
                         capture_output=True, text=True, check=True).stdout
    for line in txt.splitlines():
        parts = line.split("\t")
        for col in parts:
            if col.startswith("{") and '"id"' in col:
                try:
                    row = json.loads(_unescape_copy(col))
                except Exception:
                    continue
                if str(row.get("id") or "") == str(uid):
                    return row
    return None


def main():
    _env()
    import config
    import db
    if not db.ENABLED:
        print("база выключена (KLEAL_DB=%s) — инструмент работает только с Postgres" % db.MODE)
        return 2
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    cmd = args[0] if args else "report"

    if cmd == "migrate":
        rep = db.migrate_users_to_id(apply=apply)
        print(json.dumps(rep, ensure_ascii=False))
        return 0 if rep.get("ok") else 1

    accs = json.load(open(config.ACCOUNTS, encoding="utf-8"))
    users = db.load_users() or []
    by_mask = {}
    for k in accs:
        by_mask.setdefault(mask(k), []).append(k)

    def account(sel):
        """«маска» или «маска#Имя»: имя уточняет маску, когда под неё попадает несколько почт."""
        m, _, nm = str(sel).partition("#")
        keys = by_mask.get(m) or []
        if nm:
            want = " ".join(nm.lower().split())
            keys = [k for k in keys if " ".join(str(accs[k].get("name") or "").lower().split()) == want]
        if len(keys) != 1:
            raise SystemExit("аккаунт %r неоднозначен или не найден: %d" % (sel, len(keys)))
        return keys[0]

    if cmd == "report":
        names = {}
        for k, a in accs.items():
            nm = " ".join(str(a.get("name") or "").lower().split())
            if nm:
                names.setdefault(nm, []).append(k)
        print("режим таблицы users:", db.users_keymode(force=True), "| строк:", len(users),
              "| аккаунтов:", len(accs))
        for nm, keys in sorted(names.items(), key=lambda x: -len(x[1])):
            if len(keys) < 2:
                continue
            print("\nимя %r — аккаунтов %d" % (nm, len(keys)))
            for k in sorted(keys, key=lambda k: accs[k].get("created") or 0):
                a = accs[k]
                owned = [u.get("id") for u in users if u.get("owner") == k]
                print("  %s создан %s  строки=%s  person_id=%s  снимок анкеты=%s" % (
                    mask(k), time.strftime("%m-%d %H:%M", time.gmtime(a.get("created") or 0)),
                    owned, a.get("person_id"), bool(a.get("profile"))))
        return 0

    plan = json.load(open(cmd, encoding="utf-8"))
    print("план:", cmd, "| запись:" if apply else "| СУХОЙ ПРОГОН (без --apply)")
    if apply and db.users_keymode(force=True) != "id":
        raise SystemExit("таблица users ещё с ключом по имени — сначала `migrate --apply`")

    # ПРОВЕРКА ВСЕГО ПЛАНА ДО ПЕРВОЙ ЗАПИСИ. План либо применяется целиком, либо не применяется
    # вовсе: на репетиции шаг 3 споткнулся о неоднозначную маску, когда шаг 2 уже записал строки.
    for item in plan.get("restore_rows") or []:
        if not os.path.exists(item["dump"]):
            raise SystemExit("нет дампа %s" % item["dump"])
    for sel in plan.get("rows_from_accounts") or []:
        if not (accs[account(sel)].get("profile")):
            raise SystemExit("у %s нет снимка анкеты в аккаунте" % sel)
    ids_now = {str(u.get("id")) for u in users}
    ids_later = ids_now | {str(i["id"]) for i in plan.get("restore_rows") or []}
    for item in plan.get("own_rows") or []:
        account(item["account"])
        if str(item["id"]) not in ids_later:
            raise SystemExit("нет строки %s" % item["id"])
    for store_key, mapping in (plan.get("assign") or {}).items():
        if store_key != "_intents":
            raise SystemExit("для %s поле id человека не задано в инструменте" % store_key)
        val = db.kv_get(store_key) or []
        have = {str(r.get("id")) for r in val if isinstance(r, dict)}
        missing = [k for k in mapping if k not in have]
        if missing:
            raise SystemExit("в %s нет записей %s" % (store_key, missing))
        for pid in mapping.values():
            if pid not in ids_later and not str(pid).startswith("on") and not str(pid).startswith("anon:"):
                raise SystemExit("человек %s не существует" % pid)
    print("  план проверен целиком")

    # 1. восстановить затёртые строки из дампа
    for item in plan.get("restore_rows") or []:
        row = row_from_dump(item["dump"], item["id"])
        if row is None:
            raise SystemExit("в дампе нет строки %s" % item["id"])
        have = next((u for u in users if str(u.get("id")) == str(item["id"])), None)
        print("  вернуть строку %s (%s, владелец %s) — сейчас в базе: %s" % (
            row.get("id"), row.get("name"), mask(row.get("owner") or "-"), "есть" if have else "нет"))
        if apply and have is None:
            db.save_user(row)
            users.append(row)

    # 2. анкеты из снимков в аккаунтах
    if plan.get("rows_from_accounts"):
        sys.path.insert(0, os.path.join(ROOT, "services", "onboarding"))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "onb_app", os.path.join(ROOT, "services", "onboarding", "app.py"))
        onb = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(onb)
        for m in plan["rows_from_accounts"]:
            key = account(m)
            if any(u.get("owner") == key for u in users):
                print("  у %s уже есть строка — пропуск" % m)
                continue
            prof = dict(accs[key].get("profile") or {})
            prof.setdefault("name", accs[key].get("name"))
            u = onb._profile_to_user(prof)
            u["interests"] = onb._canon_interests(u.get("interests")) or u.get("interests")
            u["id"] = onb._fresh_uid(key, users)
            u["owner"] = key
            print("  новая строка %s для %s (%s, %s)" % (u["id"], m, u.get("name"), u.get("city") or u.get("area")))
            if apply:
                db.save_user(u)
                users.append(u)

    # 3. владелец строке без владельца
    for item in plan.get("own_rows") or []:
        key = account(item["account"])
        row = next((u for u in users if str(u.get("id")) == str(item["id"])), None)
        if row is None:
            raise SystemExit("нет строки %s" % item["id"])
        if row.get("owner") and row.get("owner") != key:
            raise SystemExit("строка %s уже принадлежит другому аккаунту" % item["id"])
        print("  строка %s (%s) → владелец %s" % (row.get("id"), row.get("name"), item["account"]))
        if apply:
            row["owner"] = key
            db.save_user(row)

    # 4. person_id всем, кто владеет ровно одной строкой
    changed = 0
    for k, a in accs.items():
        owned = [u for u in users if u.get("owner") == k]
        if len(owned) == 1 and a.get("person_id") != owned[0].get("id"):
            a["person_id"] = owned[0].get("id")
            changed += 1
    print("  person_id проставить аккаунтам: %d" % changed)
    if apply and changed:
        tmp = config.ACCOUNTS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(accs, f, ensure_ascii=False)
        os.replace(tmp, config.ACCOUNTS)

    # 5. записи матчинга → id человека
    for store_key, mapping in (plan.get("assign") or {}).items():
        val = db.kv_get(store_key) or []
        n = 0
        for rec in val if isinstance(val, list) else []:
            pid = mapping.get(str(rec.get("id")))
            if pid:
                field = "owner_id" if store_key == "_intents" else None
                if field is None:
                    raise SystemExit("для %s поле id человека не задано в инструменте" % store_key)
                print("  %s %s → %s" % (store_key, rec.get("id"), pid))
                rec[field] = pid
                n += 1
        if n != len(mapping):
            raise SystemExit("в %s найдено %d из %d записей плана" % (store_key, n, len(mapping)))
        if apply:
            db.kv_set(store_key, val)
    print("готово" if apply else "сухой прогон окончен — ничего не записано")
    return 0


if __name__ == "__main__":
    sys.exit(main())
