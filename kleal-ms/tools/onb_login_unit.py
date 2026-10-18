# -*- coding: utf-8 -*-
"""Вход и профиль онбординга (17.10.2026): три бага, по проверке на каждый.

    python3 -I tools/onb_login_unit.py                  # app.py этой копии
    python3 -I tools/onb_login_unit.py <путь/к/app.py>  # любой другой, например эталон боя

  1. лимит «5 писем в час на адрес» переживает три неверные попытки (и истечение кода);
  2. вход после правки профиля (update_user) отдаёт свежие интересы, сводку и город;
  3. /api/onboarding/chat и /api/onboarding/summary без сессии — отказ, с сессией — работают.

Без сети и без боевых файлов: хранилище — временная папка (KLEAL_DB=json, KLEAL_USERS,
KLEAL_ACCOUNTS, KLEAL_MAIL_OUTBOX, KLEAL_INTEREST_I18N), модель подменена, сервер поднимается
на 127.0.0.1 со случайным портом.
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else
                      os.path.join(HERE, "..", "services", "onboarding", "app.py"))
SRV = os.path.dirname(APP)
SHARED = os.path.abspath(os.path.join(SRV, "..", "..", "shared"))

TMP = tempfile.mkdtemp(prefix="onb_login_unit_")
os.environ.update({
    "KLEAL_DB": "json",
    "KLEAL_USERS": os.path.join(TMP, "users.json"),
    "KLEAL_ACCOUNTS": os.path.join(TMP, "accounts.json"),
    "KLEAL_MAIL_OUTBOX": os.path.join(TMP, "outbox"),
    "KLEAL_INTEREST_I18N": os.path.join(TMP, "interest_i18n.json"),
})
for _k in ("KLEAL_MAIL_PROVIDER", "KLEAL_MAIL_KEY", "KLEAL_SHOW_CODE", "KLEAL_AGE_GATE_ENABLED"):
    os.environ.pop(_k, None)
for _p in (SHARED, SRV):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_spec = importlib.util.spec_from_file_location("onb_app_under_test", APP)
app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(app)

# Модель подменена: считаем вызовы и отвечаем по-разному извлечению и реплике.
CALLS = []


def fake_llm(model, messages, temperature=0.0, *a, **kw):
    CALLS.append(kw.get("tag") or temperature)
    if temperature == 0.1:                               # извлечение профиля в v2_chat
        return "{}"
    if temperature == 0.4:                               # сводка
        return "Анна любит йогу и падел, живёт в Барселоне."
    if temperature == 0.2:                               # перевод интересов: модели «нет»
        raise RuntimeError("no model in unit test")
    return "Чем ещё любишь заниматься?"


app.llm_complete = fake_llm
CODE = "424242"
app._gen_code = lambda: CODE                             # код известен — подбирать нечего

ok = bad = 0


def check(name, cond, extra=""):
    global ok, bad
    if cond:
        ok += 1
        print("  ok   " + name)
    else:
        bad += 1
        print("  FAIL " + name + "   " + str(extra)[:300])


def login(mail):
    if mail in app._CODES:
        app._CODES[mail]["last"] = 0                     # «повтор через 30 с» — не о нём тест
    r = app.request_code(mail, "ru")
    assert r.get("sent") is True, r
    v = app.verify_code(mail, CODE)
    assert v.get("ok") is True, v
    return v


# ---------------------------------------------------------------------------- 1. лимит кодов
print("\n-- 1. лимит писем переживает неверные попытки --")
mail = "limit%d@example.com" % (int(time.time()) % 100000)
sent = 0
for i in range(app.SEND_PER_HOUR + 1):
    r = app.request_code(mail, "ru")
    if r.get("sent"):
        sent += 1
    for _ in range(app.CODE_ATTEMPTS):
        last = app.verify_code(mail, "000000")
    if mail in app._CODES:
        app._CODES[mail]["last"] = 0                     # окно «повтор через 30 с» — не о нём тест
check("три неверные попытки гасят код", last.get("error") == "expired", last)
check("верный код после трёх ошибок уже не входит",
      app.verify_code(mail, CODE).get("error") == "expired")
check("за час ушло не больше %d писем" % app.SEND_PER_HOUR, sent == app.SEND_PER_HOUR, sent)
check("шестой запрос — «too many»", app.request_code(mail, "ru").get("error") == "too many")

mail2 = "expire%d@example.com" % (int(time.time()) % 100000)
sent2 = 0
for i in range(app.SEND_PER_HOUR + 1):
    if app.request_code(mail2, "ru").get("sent"):
        sent2 += 1
    if mail2 in app._CODES:
        app._CODES[mail2]["exp"] = time.time() - 1       # код истёк, человек всё равно жмёт Verify
    app.verify_code(mail2, CODE)
    if mail2 in app._CODES:
        app._CODES[mail2]["last"] = 0
check("истечение кода тоже не обнуляет счёт писем", sent2 == app.SEND_PER_HOUR, sent2)

if mail in app._CODES:
    app._CODES[mail]["first"] = time.time() - 3601       # час прошёл
r = app.request_code(mail, "ru")
check("через час окно открывается снова", r.get("sent") is True, r)
check("и счёт начинается заново", (app._CODES.get(mail) or {}).get("sent") == 1, app._CODES.get(mail))
v = app.verify_code(mail, CODE)
check("свежий верный код входит", v.get("ok") is True, v)
check("код одноразовый", app.verify_code(mail, CODE).get("error") == "expired")

# ---------------------------------------------------------------------------- 2. свежая анкета
print("\n-- 2. вход после правки профиля отдаёт свежие данные --")
who = "anna%d@example.com" % (int(time.time()) % 100000)
v = login(who)
key = app.session_owner(v["token"])["_key"]
PROFILE = {
    "name": "Anna", "age": 29, "gender": "Female", "city": "Barcelona", "country": "Spain",
    "ageVerified18": True, "photoStatus": "uploaded",
    "languages": {"comfortable": ["English", "Spanish"]},
    "interests": {"explicit": ["yoga", "padel", "tennis"], "unused": ["tennis"],
                  "roles": {"padel": "play"}},
    "geo": {"comfortableAreas": ["Gràcia"], "maxDistanceKm": 10},
    "safety": {"publicPlacesOnly": True},
    "permissions": {"useProfileForMatching": True, "allowAdjacentMatches": True},
    "summary": "Старая сводка про йогу.",
}
row = app.register_profile(PROFILE, key)
app.attach_profile_by_token(v["token"], "Anna", PROFILE)

# Сразу после анкеты вход отдаёт ровно привязанную копию — ничего не дописано и не выдумано.
again = login(who)["profile"]
check("без правок вход отдаёт ту же копию", again == PROFILE,
      json.dumps(again, ensure_ascii=False)[:300])

up = app.update_user(row["name"], {"interests": ["yoga", "padel", "hiking"],
                                   "summary": "Новая сводка: йога, падел, походы.",
                                   "area": "Valencia", "langs": ["en", "es", "de"], "age": 30},
                     uid=row["id"])
check("правка профиля прошла", up.get("ok") is True, up)

got = login(who)
p = got.get("profile") or {}
# 18.10.2026, «личность по id», шаг 3: вход отдаёт id человека — телефону не надо узнавать себя по имени.
_row = app.my_profile_row(key) or {}
check("вход отдаёт id своей строки", got.get("id") and got.get("id") == _row.get("id"), (got.get("id"), _row.get("id")))
check("интересы свежие", "hiking" in ((p.get("interests") or {}).get("explicit") or []), p.get("interests"))
check("выключенный интерес не потерян",
      "tennis" in ((p.get("interests") or {}).get("explicit") or []) and
      "tennis" in ((p.get("interests") or {}).get("unused") or []), p.get("interests"))
check("сводка свежая", p.get("summary") == "Новая сводка: йога, падел, походы.", p.get("summary"))
check("город свежий", p.get("city") == "Valencia", p.get("city"))
check("возраст свежий", p.get("age") == 30, p.get("age"))
check("языки — названиями, как в анкете",
      ((p.get("languages") or {}).get("comfortable")) == ["English", "Spanish", "German"],
      p.get("languages"))
check("форма анкеты сохранена (роли, согласия, район)",
      ((p.get("interests") or {}).get("roles") == {"padel": "play"}
       and (p.get("permissions") or {}).get("useProfileForMatching") is True
       and (p.get("geo") or {}).get("comfortableAreas") == ["Gràcia"]), p)
extra = set(p) - set(PROFILE)
check("наружу не ушло ничего лишнего из строки", not extra, sorted(extra))
check("вернувшийся — не новый", got.get("isNew") is False and got.get("hasProfile") is True, got)

# Хранилище недоступно — вход не ломается, отдаётся копия, как раньше.
_real = app._read_users


def _down():
    raise app.UserStorageUnavailable()


app._read_users = _down
try:
    down = login(who)
finally:
    app._read_users = _real
check("хранилище упало — вход всё равно проходит", down.get("ok") is True, down)
check("и отдаёт копию из аккаунта", (down.get("profile") or {}).get("name") == "Anna", down.get("profile"))

# Аккаунт без строки (привязка без регистрации) — копия как есть.
bare = "bare%d@example.com" % (int(time.time()) % 100000)
bv = login(bare)
app.attach_profile_by_token(bv["token"], "Bare", {"name": "Bare", "city": "Lisbon"})
_bl = login(bare)
bp = _bl.get("profile") or {}
check("без строки — id пустой, вход не ломается", _bl.get("ok") and _bl.get("id") == "", _bl.get("id"))
check("без строки в хранилище — копия как есть", bp == {"name": "Bare", "city": "Lisbon"}, bp)

# ---------------------------------------------------------------------------- 3. ручки модели
print("\n-- 3. chat и summary — только с сессией --")
server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.H)
threading.Thread(target=server.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % server.server_address[1]


def post(path, body, tok=""):
    h = {"Content-Type": "application/json"}
    if tok:
        h["Authorization"] = "Bearer " + tok
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode("utf-8"), headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


CHAT = {"messages": [{"role": "user", "content": "люблю йогу"}], "profile": {}, "lang": "ru"}
SUMM = {"profile": PROFILE, "lang": "ru"}
tok = got["token"]
try:
    for path, body in (("/api/onboarding/chat", CHAT), ("/api/onboarding/summary", SUMM),
                       ("/api/v2/chat", CHAT), ("/api/v2/summary", SUMM)):
        n = len(CALLS)
        st, r = post(path, body)
        check("%s без сессии — отказ" % path, st == 200 and r.get("error") == "no session", r)
        check("%s без сессии — модель не звали" % path, len(CALLS) == n, CALLS[n:])
        st, r = post(path, body, "not-a-real-token")
        check("%s с чужим токеном — отказ" % path, r.get("error") == "no session", r)
    n = len(CALLS)
    st, r = post("/api/onboarding/chat", CHAT, tok)
    check("chat с сессией отвечает", st == 200 and bool(r.get("reply")) and not r.get("error"), r)
    check("chat с сессией звал модель", len(CALLS) > n, CALLS[n:])
    n = len(CALLS)
    st, r = post("/api/onboarding/summary", SUMM, tok)
    check("summary с сессией отвечает", st == 200 and "Анна" in str(r.get("summary")), r)
    check("summary с сессией звал модель", len(CALLS) > n, CALLS[n:])
    st, r = post("/api/onboarding/state", {"profile": {}})
    check("state (без модели) по-прежнему открыт", st == 200 and "missing" in r, r)

    # 18.10.2026, шаг 4 «личность по id»: имя — подпись, id строки не меняется.
    _id0 = got.get("id")
    st, r = post("/api/onboarding/profile-update", {"patch": {"name": "Анна-Мария"}}, tok)
    check("имя: смена принята", r.get("ok") and r.get("name") == "Анна-Мария", r)
    check("имя: id строки тот же", (r.get("user") or {}).get("id") == _id0, r.get("user"))
    st, r = post("/api/onboarding/profile-update", {"patch": {"name": "anna@example.com"}}, tok)
    check("имя: почта вместо имени — отказ", r.get("ok") is False and r.get("error") == "bad name", r)
    st, r = post("/api/onboarding/profile-update", {"patch": {"name": "Анна", "age": 31}}, tok)
    check("имя вместе с возрастом: оба сохранены", r.get("ok") and (r.get("user") or {}).get("age") == 31
          and (r.get("user") or {}).get("name") == "Анна", r)
    _re = login(who)
    check("имя: повторный вход отдаёт новое имя", _re.get("name") == "Анна" and (_re.get("profile") or {}).get("name") == "Анна"
          and _re.get("id") == _id0, (_re.get("name"), (_re.get("profile") or {}).get("name"), _re.get("id")))
    st, r = post("/api/onboarding/profile-update", {"patch": {"name": "Кто-то"}})
    check("имя: без входа — отказ", r.get("ok") is False, r)
    tok = _re["token"]

    st, r = post("/api/auth/session", {}, tok)
    check("сессия отдаёт тот же id, что и вход", r.get("ok") and r.get("id") == got.get("id"), (r.get("id"), got.get("id")))

    # 18.10.2026: фото из «Кто ты» — смена и удаление доходят до сервера.
    import base64 as _b64
    jpg = b"\xff\xd8\xff\xe0" + b"\x00" * 900 + b"\xff\xd9"
    durl = "data:image/jpeg;base64," + _b64.b64encode(jpg).decode()
    st, r = post("/api/onboarding/profile-update", {"patch": {"photo": durl}}, tok)
    url = str(r.get("photo") or "")
    check("фото: новое принято", r.get("ok") and url.startswith("/api/onboarding/photo/") and "?v=" in url, r)
    with urllib.request.urlopen(BASE + url, timeout=10) as resp:
        check("фото: отдаётся по новой ссылке", resp.status == 200 and resp.read() == jpg)
    st, r = post("/api/onboarding/profile-update", {"patch": {"photo": "data:image/jpeg;base64,!!!"}}, tok)
    check("фото: испорченное — отказ, старое цело", r.get("ok") is False and r.get("error") == "bad photo", r)
    st, r = post("/api/onboarding/profile-update", {"patch": {"photo": durl, "age": 33}}, tok)
    check("фото вместе с возрастом: возраст тоже сохранён", r.get("ok") and (r.get("user") or {}).get("age") == 33, r)
    st, r = post("/api/onboarding/profile-update", {"patch": {"photo": ""}}, tok)
    check("фото: удаление — пустая ссылка", r.get("ok") and r.get("photo") == "", r)
    try:
        urllib.request.urlopen(BASE + url.split("?")[0], timeout=10)
        gone = False
    except urllib.error.HTTPError as e:
        gone = e.code == 404
    check("фото: после удаления файла нет (404)", gone)
    st, r = post("/api/onboarding/profile-update", {"patch": {"photo": durl}})
    check("фото: без входа — отказ", r.get("ok") is False, r)
finally:
    server.shutdown()
    shutil.rmtree(TMP, ignore_errors=True)

print("\n%s\nРЕЗУЛЬТАТ: %d ok, %d проблем\n%s" % ("=" * 60, ok, bad, "=" * 60))
sys.exit(1 if bad else 0)
