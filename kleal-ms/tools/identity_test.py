# -*- coding: utf-8 -*-
"""Тёзки — разные люди. Сторож правила «личность = id, а не имя» (docs/IDENTITY.md).

    python3 tools/identity_test.py

Без сети и без базы: временные файлы аккаунтов, людей и стора, функции сервисов напрямую.

ЗАЧЕМ. 26.09.2026 четыре аккаунта «Иван» видели интенты друг друга в «Моей активности», а
регистрация каждого нового затирала анкету прежнего: интенты, планы, переписка и сама строка
профиля были привязаны к ИМЕНИ. Этот тест держит оба сценария и всё, что их окружает:
  — регистрация тёзки заводит ОТДЕЛЬНУЮ строку, чужую не трогает;
  — ручки профиля по сессии находят СВОЮ строку, а не первую с таким именем;
  — удаление аккаунта уносит только свою строку;
  — интент одного «Ивана» не виден другому, удалить чужой нельзя;
  — старые интенты без id не отдаются аккаунту, родившемуся позже них;
  — поиск исключает себя по id, а тёзку — показывает;
  — без сессии назваться человеком с аккаунтом нельзя; боту и тесту — можно.
"""
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

ok = bad = 0


def check(name, cond, extra=""):
    global ok, bad
    if cond:
        ok += 1
        print("  ok   %s" % name)
    else:
        bad += 1
        print("  FAIL %s   %s" % (name, str(extra)[:300]))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Req:
    """Минимальный запрос для kleal_auth: только заголовки."""
    def __init__(self, token=""):
        self.headers = {"Authorization": "Bearer " + token} if token else {}
        self.path = "/"


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def main():
    tmp = tempfile.mkdtemp(prefix="kleal_identity_")
    users_p = os.path.join(tmp, "users.json")
    acc_p = os.path.join(tmp, "accounts.json")
    store_p = os.path.join(tmp, "kleal_store.json")
    os.environ.update({"KLEAL_DB": "json", "KLEAL_USERS": users_p, "KLEAL_ACCOUNTS": acc_p,
                       "KLEAL_STORE": store_p, "KLEAL_MAIL_OUTBOX": os.path.join(tmp, "outbox"),
                       # удаление учётки зовёт стирание в матчинге — не в боевой же
                       "MATCH_URL": "http://127.0.0.1:9"})
    os.environ.pop("KLEAL_MAIL_PROVIDER", None)

    now = int(time.time())
    old = now - 40 * 86400          # старый «Иван»: аккаунт родился 40 дней назад
    tok_a, tok_b = "tok-ivan-a", "tok-ivan-b"
    accounts = {
        "ivan-a@example.com": {"login": "ivan-a@example.com", "email": "ivan-a@example.com",
                               "created": old, "name": "Иван",
                               "sessions": {sha(tok_a): {"created": now, "exp": now + 3600, "last": now}}},
        "ivan-b@example.com": {"login": "ivan-b@example.com", "email": "ivan-b@example.com",
                               "created": now - 60,
                               "sessions": {sha(tok_b): {"created": now, "exp": now + 3600, "last": now}}},
    }
    users = [
        {"id": "on_ivan_a", "owner": "ivan-a@example.com", "name": "Иван", "age": 30,
         "city": "Barcelona", "lat": 41.39, "lon": 2.17, "interests": ["coffee", "chess"],
         "langs": ["ru", "en"], "source": "onboarding", "open": True},
        {"id": "seed_bot_1", "name": "Бот Боткин", "age": 29, "city": "Barcelona", "lat": 41.38,
         "lon": 2.16, "interests": ["coffee"], "langs": ["ru", "en"], "source": "onboarding",
         "open": True},
    ]
    json.dump(accounts, open(acc_p, "w"), ensure_ascii=False)
    json.dump({"users": users}, open(users_p, "w"), ensure_ascii=False)
    # Старый интент «Ивана», записанный по имени до id: создан 20 дней назад.
    json.dump({"_intents": [{"id": "in_legacy", "owner": "Иван", "title": "старый кофе",
                             "intent": {"topics": ["coffee"], "mode": "offline"},
                             "created": now - 20 * 86400, "updated": now - 20 * 86400}]},
              open(store_p, "w"), ensure_ascii=False)

    sys.path.insert(0, os.path.join(ROOT, "shared"))

    # ------------------------------------------------------------ онбординг
    print("\n-- онбординг: тёзка регистрируется --")
    sys.path.insert(0, os.path.join(ROOT, "services", "onboarding"))
    onb = load("onb_app", os.path.join(ROOT, "services", "onboarding", "app.py"))
    sys.path.remove(os.path.join(ROOT, "services", "onboarding"))
    # Тест про личность, а не про каталог интересов: каталог собирается из таксономии, которой в
    # временном окружении может не быть, — считаем доверенным любой ключ.
    onb.interest_norm.trusted_interest = lambda key: key
    u = onb.register_profile({"name": "Иван", "age": 25, "city": "Madrid",
                              "interests": {"explicit": ["coffee"]}},
                             owner_key="ivan-b@example.com")
    rows = onb._read_users()
    ivans = [x for x in rows if x.get("name") == "Иван"]
    check("второй «Иван» получил СВОЮ строку", len(ivans) == 2, [x.get("id") for x in ivans])
    check("строка первого «Ивана» не тронута",
          any(x.get("id") == "on_ivan_a" and x.get("city") == "Barcelona" and x.get("age") == 30
              for x in rows), ivans)
    check("у новой строки id от аккаунта, а не от имени", u.get("id") not in ("", "on_ivan_a"), u.get("id"))
    accs = json.load(open(acc_p))
    check("аккаунт запомнил person_id", accs["ivan-b@example.com"].get("person_id") == u.get("id"),
          accs["ivan-b@example.com"])
    b_id = u.get("id")

    print("\n-- онбординг: своя строка по сессии --")
    row_a = onb.my_profile_row("ivan-a@example.com")
    row_b = onb.my_profile_row("ivan-b@example.com")
    check("A видит свою анкету", (row_a or {}).get("id") == "on_ivan_a", row_a)
    check("B видит свою анкету, а не первую с именем «Иван»", (row_b or {}).get("id") == b_id, row_b)
    r = onb.update_user("Иван", {"age": 26}, uid=b_id)
    rows = onb._read_users()
    check("правка B меняет только B",
          next(x for x in rows if x["id"] == b_id).get("age") == 26
          and next(x for x in rows if x["id"] == "on_ivan_a").get("age") == 30, r)

    # ------------------------------------------------------------ матчинг
    print("\n-- матчинг: кто прислал запрос --")
    sys.path.insert(0, os.path.join(ROOT, "services", "matching"))
    m = load("match_app", os.path.join(ROOT, "services", "matching", "app.py"))
    # 26.09.2026 индекс людей назвали `_IDX` — тем же именем, что у словаря категорий, — и подбор
    # несколько часов не узнавал ни одного интереса, а все дымовые проверки были зелёными.
    check("индекс людей не затёр словарь категорий", m.cat_of("coffee")[0] == "social", m.cat_of("coffee"))
    pid_a, name_a = m._identify(Req(tok_a), "Иван")
    pid_b, name_b = m._identify(Req(tok_b), "Иван")
    check("сессия A → id A", pid_a == "on_ivan_a", pid_a)
    check("сессия B → id B", pid_b == b_id, pid_b)
    check("без сессии назваться «Иваном» (у него аккаунт) нельзя", m._identify(Req(), "Иван")[0] == "")
    check("бот без сессии узнаётся по своей строке", m._identify(Req(), "Бот Боткин")[0] == "seed_bot_1")
    check("тест без сессии и без строки — временная личность anon:",
          m._identify(Req(), "Смоук Тестер")[0] == "anon:смоук тестер")
    check("чужой токен ни на кого не указывает", m._identify(Req("мусор"), "Иван")[0] == "")

    print("\n-- матчинг: интенты тёзок раздельны --")
    s = m.save_intent("Иван", {"topics": ["chess"], "mode": "offline", "title": "шахматы"},
                      "шахматы", owner_id=pid_b)
    check("B сохранил интент", s.get("ok") is True, s)
    lb = m.list_intents("Иван", {}, False, owner_id=pid_b)
    la = m.list_intents("Иван", {}, False, owner_id=pid_a)
    check("B видит только свой интент", [x["id"] for x in lb] == [s["id"]], [x["id"] for x in lb])
    check("A не видит интент B", s["id"] not in [x["id"] for x in la], [x["id"] for x in la])
    check("старый интент по имени достался A (аккаунт старше записи)",
          [x["id"] for x in la] == ["in_legacy"], [x["id"] for x in la])
    check("старый интент НЕ достался B (аккаунт моложе записи)",
          "in_legacy" not in [x["id"] for x in lb])
    d = m.delete_intent("Иван", s["id"], owner_id=pid_a)
    check("A не может удалить интент B", d.get("ok") is False, d)
    check("без личности интент не сохраняется",
          m.save_intent("Иван", {"topics": ["x"]}, "x", owner_id="").get("ok") is False)
    check("без личности список пуст", m.list_intents("Иван", {}, False, owner_id="") == [])

    print("\n-- матчинг: поиск и карта --")
    cands = m.match_candidates({"topics": ["coffee"], "type": "social", "role": "meet", "mode": "offline"},
                               {"name": "Иван", "lat": 41.39, "lon": 2.17,
                                "languages": {"comfortable": ["ru", "en"]}},
                               {"self": "Иван", "self_id": pid_a}) or []
    ids = [str(c.get("id") or "") for c in cands]
    check("A не находит сам себя", "on_ivan_a" not in ids, ids)
    feed_a = m.map_feed_payload("offline", self_name="Иван", limit=50, self_id=pid_a)
    feed_ids = [str(i.get("id")) for i in (feed_a.get("items") or [])]
    check("на карте A нет своего интента по id", "in_legacy" not in feed_ids, feed_ids)

    print("\n-- онбординг: удаление аккаунта --")
    onb.delete_account("ivan-b@example.com")
    rows = onb._read_users()
    check("удаление B унесло только B", [x["id"] for x in rows if x.get("name") == "Иван"] == ["on_ivan_a"],
          [x["id"] for x in rows])

    print("\nитог: %d ok, %d FAIL" % (ok, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
