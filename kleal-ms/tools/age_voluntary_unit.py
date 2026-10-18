# -*- coding: utf-8 -*-
"""Добровольная проверка возраста и тестовый автопроход (18.10.2026).

    python3 -I tools/age_voluntary_unit.py

Онбординг поднимается тем же серверным слоем, что на бою (shared/serving.KlealServer: он и подключает
обработчик проверки), с временными аккаунтами, людьми и базой проверок; Didit подменён целиком.

Держит:
  — обязательная проверка выключена (KLEAL_AGE_GATE_ENABLED=0), а добровольная работает: статус настоящий,
    старт создаёт сессию у провайдера, подписанное событие принимается (раньше — 503 verification_disabled);
  — сторож допуска (gate) и фильтр поиска НЕ включаются — никого не прячут;
  — тестовый автопроход: только при KLEAL_DEV_KYC_DEMO_AUTH=1, ставит галочку id_verified с пометкой test,
    её можно снять; при 0 — 404 и признака testPass нет; в базу проверок он не пишет;
  — галочка — отдельное поле id_verified; старое verified («сам отметил 18+») не трогается;
  — настоящую галочку (didit) тестовый путь не перекрывает и снять не может;
  — KLEAL_AGE_VOLUNTARY=0 возвращает прежнее поведение (legacy).
"""
import hashlib
import hmac
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
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "..", "services", "onboarding", "app.py")
SRV = os.path.dirname(os.path.abspath(APP))
SHARED = os.path.abspath(os.path.join(SRV, "..", "..", "shared"))
TMP = tempfile.mkdtemp(prefix="age_voluntary_unit_")
WF = str(uuid.uuid4())
os.environ.update({
    "KLEAL_DB": "json", "KLEAL_USERS": os.path.join(TMP, "users.json"),
    "KLEAL_ACCOUNTS": os.path.join(TMP, "accounts.json"), "KLEAL_MAIL_OUTBOX": os.path.join(TMP, "outbox"),
    "KLEAL_INTEREST_I18N": os.path.join(TMP, "interest_i18n.json"),
    "KLEAL_AGE_GATE_ENABLED": "0", "KLEAL_AGE_GATE_FROM": "1", "KLEAL_AGE_REQUIRE_ALL": "1",
    "KLEAL_AGE_DB": os.path.join(TMP, "age.db"), "KLEAL_AGE_BINDING_SECRET": "b" * 40,
    "DIDIT_WORKFLOW_ID": WF, "DIDIT_API_KEY": "test-key", "DIDIT_WEBHOOK_SECRET": "w" * 40,
    "DIDIT_CALLBACK_URL": "https://kleal.test/api/onboarding/age-verification/callback",
    "KLEAL_DEV_KYC_DEMO_AUTH": "1",
})
for _k in ("KLEAL_MAIL_PROVIDER", "KLEAL_MAIL_KEY", "KLEAL_SHOW_CODE", "KLEAL_AGE_VOLUNTARY", "KLEAL_AGE_COHORT_KEYS"):
    os.environ.pop(_k, None)
for _p in (SHARED, SRV):
    if _p not in sys.path:
        sys.path.insert(0, _p)
sys.dont_write_bytecode = True
_spec = importlib.util.spec_from_file_location("onb_age_under_test", APP)
app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(app)
import age_verification as age          # noqa: E402
import age_verification_http as age_http  # noqa: E402
import age_proof                         # noqa: E402
import serving                           # noqa: E402

# Didit подменён: политика проверки есть и актуальна, сессия создаётся.
age_proof.policies = lambda: [{"policy": "test"}]
age_proof.workflow_current = lambda p, fresh=False: True
age_proof.digest = lambda p: "digest-test"
CREATED = []


def fake_provider(method, path, body=None):
    if method == "POST" and path == "session/":
        CREATED.append(body)
        return {"session_id": str(uuid.uuid4()), "vendor_data": body["vendor_data"], "workflow_id": WF,
                "url": "https://verify.didit.me/session/abc"}
    return {"status": "In Progress", "session_id": "x"}


age.provider = fake_provider
app.llm_complete = lambda *a, **k: "{}"
app._gen_code = lambda: "424242"
ok = bad = 0


def check(name, cond, extra=""):
    global ok, bad
    if cond:
        ok += 1
        print("  ok   " + name)
    else:
        bad += 1
        print("  FAIL " + name + "   " + str(extra)[:300])


server = serving.KlealServer(("127.0.0.1", 0), app.H)
threading.Thread(target=server.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % server.server_address[1]
P = age.PREFIX


def call(method, path, body=None, tok="", headers=None):
    h = {"Content-Type": "application/json"}
    if tok:
        h["Authorization"] = "Bearer " + tok
    h.update(headers or {})
    data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
    req = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"null")
        except ValueError:
            return e.code, None


def login(mail):
    assert app.request_code(mail, "ru").get("sent")
    v = app.verify_code(mail, "424242")
    assert v.get("ok"), v
    return v["token"], app.session_owner(v["token"])["_key"]


def onboard(tok, key, name):
    prof = {"name": name, "age": 30, "gender": "Female", "city": "Barcelona", "ageVerified18": True,
            "languages": {"comfortable": ["English"]}, "interests": {"explicit": ["padel"]}}
    app.register_profile(prof, key)
    app.attach_profile_by_token(tok, name, prof)


def row_of(key):
    return app.my_profile_row(key) or {}


try:
    tok, key = login("anna%d@example.com" % (int(time.time()) % 100000))
    onboard(tok, key, "Anna")
    tok2, key2 = login("bob%d@example.com" % (int(time.time()) % 100000))
    onboard(tok2, key2, "Bob")

    print("-- добровольная проверка при выключенной обязательной --")
    st, r = call("GET", P + "/enrollment", tok=tok)
    check("enrollment: не обязательна, но добровольно можно, тестовая кнопка есть",
          r.get("required") is False and r.get("voluntary") is True and r.get("testPass") is True, r)
    st, r = call("GET", P + "/status", tok=tok)
    check("status: настоящий, не legacy; можно начать; допуск не отрезан",
          r.get("status") == "not_started" and r.get("canStart") is True and r.get("admitted") is True
          and r.get("voluntary") is True, r)
    st, r = call("POST", P + "/session", {"language": "ru"}, tok=tok)
    check("session: сессия у провайдера создана, ссылка verify.didit.me",
          st == 200 and r.get("status") == "pending" and str(r.get("url", "")).startswith("https://verify.didit.me/")
          and len(CREATED) == 1, (st, r))
    check("сессия привязана к аккаунту (vendor_data — подпись, не ключ)", CREATED and CREATED[0]["vendor_data"] != key, CREATED)

    print("\n-- сценарий Didit не совпал с утверждённым (18.10: «не получилось начать», потом 429) --")
    tok3, key3 = login("cara%d@example.com" % (int(time.time()) % 100000))
    onboard(tok3, key3, "Cara")
    _wc = age_proof.workflow_current
    age_proof.workflow_current = lambda p, fresh=False: False
    n_before = len(CREATED)
    st, r = call("POST", P + "/session", {"language": "ru"}, tok=tok3)
    check("старт: честный отказ configuration (503)", st == 503 and r.get("error") == "configuration", (st, r))
    st, r = call("POST", P + "/session", {"language": "ru"}, tok=tok3)
    check("повтор сразу — та же ошибка, а не 429", st == 503 and r.get("error") == "configuration", (st, r))
    check("платной сессии не создано", len(CREATED) == n_before, len(CREATED) - n_before)
    st, r = call("GET", P + "/status", tok=tok3)
    check("статус после сбоя — можно начать снова", r.get("status") == "not_started" and r.get("canStart") is True, r)
    age_proof.workflow_current = _wc
    st, r = call("POST", P + "/session", {"language": "ru"}, tok=tok3)
    check("сценарий снова совпал — старт проходит сразу", st == 200 and r.get("url"), (st, r))

    print("\n-- приём событий провайдера --")
    ts = int(time.time())
    evt = {"timestamp": ts, "created_at": ts, "event_id": str(uuid.uuid4()), "webhook_type": "status.updated",
           "session_id": str(uuid.uuid4()), "status": "Approved"}
    sig = hmac.new(os.environ["DIDIT_WEBHOOK_SECRET"].encode(), age.canonical(evt), hashlib.sha256).hexdigest()
    st, r = call("POST", P + "/webhook", json.dumps(evt).encode(),
                 headers={"X-Timestamp": str(ts), "X-Signature-V2": sig})
    check("подписанное событие принимается (раньше 503 verification_disabled)", st == 200 and r.get("ok") is True, (st, r))
    st, r = call("POST", P + "/webhook", json.dumps(evt).encode(),
                 headers={"X-Timestamp": str(ts), "X-Signature-V2": "0" * 64})
    check("неподписанное — отказ 401", st == 401, (st, r))

    print("\n-- допуск и поиск не тронуты --")
    check("gate выключен: никого не держит", age.enabled() is False)
    rows = [{"owner": key, "id": "a"}, {"owner": key2, "id": "b"}, {"id": "c"}]
    check("фильтр поиска (age) пропускает всех", age.filter_candidates(rows) == rows)
    import age_rollout
    check("фильтр поиска (rollout) пропускает всех", age_rollout.filter_candidates(rows) == rows)

    print("\n-- тестовый автопроход --")
    old_verified = row_of(key2).get("verified")
    st, r = call("POST", P + "/test-pass", {}, tok=tok2)
    check("автопроход при флаге 1", st == 200 and r.get("status") == "approved" and r.get("method") == "test", (st, r))
    rw = row_of(key2)
    check("галочка id_verified с пометкой test", rw.get("id_verified") is True and rw.get("id_verified_method") == "test", rw)
    check("старое verified не тронуто", rw.get("verified") == old_verified, (old_verified, rw.get("verified")))
    st, r = call("GET", P + "/status", tok=tok2)
    check("status показывает пройденную тестом", r.get("status") == "approved" and r.get("method") == "test"
          and r.get("over18") is True, r)
    with age.database() as conn:
        n = conn.execute("SELECT count(*) FROM verification WHERE subject=?", (age.subject(key2, app._read_accounts()[key2]),)).fetchone()[0]
    check("в базу проверок автопроход не пишет (не настоящее 18+)", n == 0, n)
    st, r = call("POST", P + "/test-pass", {"undo": True}, tok=tok2)
    rw = row_of(key2)
    check("тестовую галочку можно снять", st == 200 and rw.get("id_verified") is False and "id_verified_method" not in rw, (r, rw))
    st, r = call("GET", P + "/status", tok=tok2)
    check("после снятия — снова не начато", r.get("status") == "not_started", r)
    st, r = call("POST", P + "/test-pass", {})
    check("без входа — отказ", st == 401, (st, r))

    print("\n-- настоящая галочка сильнее тестовой --")
    check("одобрение Didit ставит галочку didit", app._age_on_verified(key, "didit") and row_of(key).get("id_verified_method") == "didit")
    call("POST", P + "/test-pass", {}, tok=tok)
    check("тест не перекрывает didit", row_of(key).get("id_verified_method") == "didit", row_of(key))
    call("POST", P + "/test-pass", {"undo": True}, tok=tok)
    check("и снять настоящую тестовым путём нельзя", row_of(key).get("id_verified") is True
          and row_of(key).get("id_verified_method") == "didit", row_of(key))
    prof = {"name": "Anna", "age": 30, "gender": "Female", "city": "Madrid", "ageVerified18": True,
            "languages": {"comfortable": ["English"]}, "interests": {"explicit": ["padel"]}}
    app.register_profile(prof, key)
    check("повторная анкета галочку не сбрасывает", row_of(key).get("id_verified") is True and row_of(key).get("area") == "Madrid",
          row_of(key))

    print("\n-- флаг тестов выключен --")
    os.environ["KLEAL_DEV_KYC_DEMO_AUTH"] = "0"
    st, r = call("GET", P + "/enrollment", tok=tok2)
    check("признака testPass нет", r.get("testPass") is False, r)
    st, r = call("POST", P + "/test-pass", {}, tok=tok2)
    check("ручка автопрохода — 404", st == 404, (st, r))
    os.environ["KLEAL_DEV_KYC_DEMO_AUTH"] = "1"

    print("\n-- удаление аккаунта стирает запись проверки всегда (решение Ивана 18.10) --")
    import age_rollout as _ar
    os.environ["KLEAL_AGE_REQUIRE_ALL"] = "0"          # вне любой когорты
    acc = app._read_accounts()[key]
    sub = age.subject(key, acc)

    def has_rec():
        with age.database() as conn:
            return conn.execute("SELECT count(*) FROM verification WHERE subject=?", (sub,)).fetchone()[0]
    check("у добровольно проверявшегося запись есть", has_rec() == 1, has_rec())
    check("вне когорты (REQUIRE_ALL=0, когорты нет)", _ar.configured_member(key) is False)
    _ar.begin_delete_account(key, acc)
    _ar.delete_account(key, acc)
    check("удаление стёрло запись при REQUIRE_ALL=0", has_rec() == 0, has_rec())
    with age.database() as conn:
        tomb = conn.execute("SELECT count(*) FROM deleted_subjects WHERE subject=?", (sub,)).fetchone()[0]
    check("и поставило барьер от повторного создания", tomb == 1, tomb)
    try:
        _ar.begin_delete_account(key, acc); _ar.delete_account(key, acc)
        again = True
    except Exception as e:
        again = repr(e)
    check("повторное удаление безопасно", again is True, again)
    _db = os.environ.pop("KLEAL_AGE_DB")
    try:
        _ar.begin_delete_account(key2, app._read_accounts()[key2]); _ar.delete_account(key2, app._read_accounts()[key2])
        nodb = True
    except Exception as e:
        nodb = repr(e)
    os.environ["KLEAL_AGE_DB"] = _db
    check("без KLEAL_AGE_DB ничего не падает", nodb is True, nodb)
    _sec = os.environ.pop("KLEAL_AGE_BINDING_SECRET")
    try:
        _ar.delete_account(key2, app._read_accounts()[key2])
        nosec = True
    except Exception as e:
        nosec = repr(e)
    os.environ["KLEAL_AGE_BINDING_SECRET"] = _sec
    check("без секрета привязки вне когорты — пропуск, не падение", nosec is True, nosec)
    os.environ["KLEAL_AGE_REQUIRE_ALL"] = "1"

    print("\n-- выключатель добровольной проверки --")
    os.environ["KLEAL_AGE_VOLUNTARY"] = "0"
    st, r = call("GET", P + "/status", tok=tok2)
    check("KLEAL_AGE_VOLUNTARY=0 — прежнее поведение (legacy)", r.get("status") == "legacy_exempt", r)
    n0 = len(CREATED)
    st, r = call("POST", P + "/session", {"language": "en"}, tok=tok2)
    check("и сессий у провайдера не создаёт", len(CREATED) == n0 and r.get("status") == "legacy_exempt", r)
    os.environ.pop("KLEAL_AGE_VOLUNTARY", None)
finally:
    server.shutdown()
    shutil.rmtree(TMP, ignore_errors=True)

print("\n%s\nРЕЗУЛЬТАТ: %d ok, %d проблем\n%s" % ("=" * 60, ok, bad, "=" * 60))
sys.exit(1 if bad else 0)
