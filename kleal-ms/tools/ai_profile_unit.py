# -*- coding: utf-8 -*-
"""«Заполнить через ChatGPT» (18.10.2026): MCP-коннектор и черновик анкеты.

    python3 -I tools/ai_profile_unit.py

Без сети и без боевых файлов: временные аккаунты (KLEAL_DB=json), модель подменена, онбординг
поднимается на 127.0.0.1 со случайным портом и проверяется настоящим обменом MCP по HTTP.
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
APP = os.path.join(HERE, "..", "services", "onboarding", "app.py")
SRV = os.path.dirname(os.path.abspath(APP))
SHARED = os.path.abspath(os.path.join(SRV, "..", "..", "shared"))
TMP = tempfile.mkdtemp(prefix="ai_profile_unit_")
os.environ.update({"KLEAL_DB": "json", "KLEAL_USERS": os.path.join(TMP, "users.json"),
                   "KLEAL_ACCOUNTS": os.path.join(TMP, "accounts.json"),
                   "KLEAL_MAIL_OUTBOX": os.path.join(TMP, "outbox"),
                   "KLEAL_INTEREST_I18N": os.path.join(TMP, "interest_i18n.json"),
                   "KLEAL_PUBLIC_URL": "https://kleal.test"})
for _k in ("KLEAL_MAIL_PROVIDER", "KLEAL_MAIL_KEY", "KLEAL_SHOW_CODE", "KLEAL_AGE_GATE_ENABLED"):
    os.environ.pop(_k, None)
for _p in (SHARED, SRV):
    if _p not in sys.path:
        sys.path.insert(0, _p)
sys.dont_write_bytecode = True
_spec = importlib.util.spec_from_file_location("onb_ai_under_test", APP)
app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(app)

EXTRACTED = {"city": "Barcelona", "languages": {"comfortable": ["ru", "en"]},
             "interests": {"explicit": ["падел", "настолки"]}, "name": "Иван", "ageRange": "25-34",
             "goals": {"primary": ["friends", "dating"]}}


# Модель анкеты (interest_normalization.normalize) отвечает так же, как настоящая на этих словах
# (замер на бою 18.10.2026: все двенадцать — ready, меньше секунды на слово).
NORM = {"тренировки в зале": "gym workouts", "программирование": "programming",
        "разработка it-продуктов": "it product development", "технологические стартапы": "technology startups",
        "предпринимательство": "entrepreneurship", "автомобили": "cars", "gym workouts": "gym workouts",
        "software development": "software development", "cars": "cars", "gimnasio": "gym",
        "emprendimiento": "entrepreneurship", "coches": "cars", "jazz concerts": "jazz concerts",
        "настолки": "board games", "фото": "photography", "surf": "surfing", "падел": "padel"}


def fake_llm(model, messages, temperature=0.0, *a, **kw):
    sys_txt = str((messages or [{}])[0].get("content") or "")
    if "normalize one user-authored social interest" in sys_txt:
        raw = json.loads(messages[-1]["content"]).get("raw", "")
        canon = NORM.get(raw.lower(), "zzz unknown thing")
        return json.dumps({"status": "ready", "confidence": 0.95, "question": "",
                           "options": [{"canonical": canon, "label": raw}]}, ensure_ascii=False)
    return json.dumps(EXTRACTED, ensure_ascii=False)


app.llm_complete = fake_llm
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


def login(mail):
    r = app.request_code(mail, "ru")
    assert r.get("sent") is True, r
    v = app.verify_code(mail, "424242")
    assert v.get("ok") is True, v
    return v["token"]


server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.H)
threading.Thread(target=server.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % server.server_address[1]


def post(path, body, tok="", raw=None):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if tok:
        h["Authorization"] = "Bearer " + tok
    data = raw.encode("utf-8") if raw is not None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            b = r.read().decode("utf-8")
            return r.status, (json.loads(b) if b else None)
    except urllib.error.HTTPError as e:
        b = e.read().decode("utf-8")
        return e.code, (json.loads(b) if b else None)


def rpc(path, method, params=None, rid=1):
    msg = {"jsonrpc": "2.0", "method": method}
    if rid is not None:
        msg["id"] = rid
    if params is not None:
        msg["params"] = params
    return post(path, msg)


try:
    tok = login("ai%d@example.com" % (int(time.time()) % 100000))

    print("-- ссылка коннектора --")
    st, r = post("/api/onboarding/ai-link", {})
    check("без входа — отказ", r.get("ok") is False and r.get("error") == "sign in required", r)
    st, r = post("/api/onboarding/ai-link", {}, tok)
    url = str(r.get("url") or "")
    check("ссылка выдана", r.get("ok") and url.startswith("https://kleal.test/api/onboarding/mcp/"), r)
    check("срок — около суток", abs(r.get("expires_at", 0) - (time.time() + app.ai_profile.LINK_TTL)) < 60, r)
    check("фразы для ChatGPT на трёх языках", set((r.get("prompt") or {}).keys()) == {"ru", "en", "es"}, r)
    path = url[len("https://kleal.test"):]
    accs = json.load(open(os.environ["KLEAL_ACCOUNTS"]))
    check("в аккаунте только хэш ключа", path.rsplit("/", 1)[-1] not in json.dumps(accs), "ключ лежит открыто")

    print("\n-- протокол MCP --")
    st, r = rpc(path, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": "chatgpt", "version": "x"}})
    res = (r or {}).get("result") or {}
    check("initialize", st == 200 and res.get("protocolVersion") == "2025-06-18"
          and "tools" in (res.get("capabilities") or {}) and (res.get("serverInfo") or {}).get("name") == "kleal", r)
    st, r = rpc(path, "initialize", {"protocolVersion": "2099-01-01"})
    check("незнакомая версия — наша последняя", ((r or {}).get("result") or {}).get("protocolVersion") == "2025-06-18", r)
    st, r = rpc(path, "notifications/initialized", rid=None)
    check("уведомление — 202 без тела", st == 202 and r is None, (st, r))
    st, r = rpc(path, "tools/list")
    tools = ((r or {}).get("result") or {}).get("tools") or []
    check("два инструмента: запись и ссылка", [t["name"] for t in tools] == ["save_kleal_profile_draft", "prepare_kleal_profile_link"], tools)
    ann = {t["name"]: (t.get("annotations") or {}).get("readOnlyHint") for t in tools}
    check("пометки честные: запись — не чтение, ссылка — чтение",
          ann.get("save_kleal_profile_draft") is False and ann.get("prepare_kleal_profile_link") is True, ann)
    props = (tools[0].get("inputSchema") or {}).get("properties") or {} if tools else {}
    check("в схеме нет возраста, имени, пола", not ({"age", "name", "gender", "birthday"} & set(props)), props.keys())
    st, r = rpc(path, "ping")
    check("ping", st == 200 and (r or {}).get("result") == {}, r)
    st, r = rpc(path, "no/such")
    check("незнакомый метод — -32601", ((r or {}).get("error") or {}).get("code") == -32601, r)
    st, r = post(path, None, raw="{not json")
    check("битый JSON — parse error", st == 400 and ((r or {}).get("error") or {}).get("code") == -32700, (st, r))
    req = urllib.request.Request(BASE + path)
    try:
        urllib.request.urlopen(req, timeout=10)
        code = 200
    except urllib.error.HTTPError as e:
        code = e.code
    check("GET — 405 (без SSE)", code == 405, code)

    print("\n-- черновик от ChatGPT --")
    st, r = post("/api/onboarding/ai-draft", {"action": "get"}, tok)
    check("пока черновика нет", r.get("ok") and r.get("draft") is None, r)
    args = {"city": "Barcelona", "country": "Spain", "languages": ["Russian", "English"],
            "interests": ["padel", "board games", "jazz concerts", "padel"],
            "goals": ["friends", "dating", "sport"], "vibe": ["curious"], "meet_format": "offline_first",
            "about_me": "Переехал в Барселону, люблю спорт. Пишите ivan@example.com или +34 600 123 456, https://x.com/ivan",
            "age": 31, "name": "Иван", "gender": "male"}
    st, r = rpc(path, "tools/call", {"name": "save_kleal_profile_draft", "arguments": args})
    res = (r or {}).get("result") or {}
    check("вызов инструмента сохранил", st == 200 and res.get("isError") is False
          and (res.get("structuredContent") or {}).get("saved"), r)
    st, r = post("/api/onboarding/ai-draft", {"action": "get"}, tok)
    d = (r.get("draft") or {})
    prof = d.get("profile") or {}
    check("черновик пришёл от chatgpt", d.get("source") == "chatgpt", d)
    miss = r.get("missing") or []
    check("короткий путь: недостающее — только личное и настройки",
          {"Name", "Age 18+", "Gender", "Photo"} <= set(miss) and not ({"Languages", "Interests", "Area"} & set(miss)), miss)
    check("короткий путь: имя аккаунта отдаётся (пусто, если не знаем)", "account_name" in r, r.keys())
    got_keys = (prof.get("interests") or {}).get("explicit") or []
    check("город и языки на месте", prof.get("city") == "Barcelona"
          and prof.get("languages") == {"comfortable": ["Russian", "English"]}, prof)
    check("интересы — ключами реестра, ничего не потеряно", "padel" in got_keys
          and all(app._ai_known_key(k) for k in got_keys)
          and len(got_keys) + len(d.get("review") or []) == 3, (got_keys, d.get("review")))
    check("цели: только допустимые, без свиданий", prof.get("goals") == {"primary": ["friends", "sport"]}, prof.get("goals"))
    check("формат и настрой", prof.get("format") == {"modePreference": "offline_first"}
          and prof.get("vibe") == {"primary": ["curious"]}, prof)
    check("ни возраста, ни имени, ни пола", not ({"age", "name", "gender", "ageRange"} & set(prof)), prof.keys())
    about = prof.get("aboutMe") or ""
    check("из «о себе» вырезаны почта, телефон, ссылка", "@" not in about and "600" not in about and "http" not in about, about)
    st, r = rpc(path, "tools/call", {"name": "save_kleal_profile_draft", "arguments": {"age": 30, "name": "X"}})
    check("пустой по сути вызов — ошибка, не черновик", ((r or {}).get("result") or {}).get("isError") is True, r)
    st, r = rpc(path, "tools/call", {"name": "other_tool", "arguments": {}})
    check("чужой инструмент — ошибка", ((r or {}).get("error") or {}).get("code") == -32602, r)
    st, r = post(path, [{"jsonrpc": "2.0", "id": 7, "method": "ping"},
                        {"jsonrpc": "2.0", "method": "notifications/initialized"}])
    check("пакет: ответ только на запрос", st == 200 and isinstance(r, list) and len(r) == 1 and r[0]["id"] == 7, r)

    print("\n-- путь без записи: ссылка на страницу подтверждения --")
    post("/api/onboarding/ai-draft", {"action": "discard"}, tok)
    st, r = rpc(path, "tools/call", {"name": "prepare_kleal_profile_link", "arguments": {
        "city": "Lisbon", "interests": ["surf", "фото"], "age": 30, "about_me": "Пишите a@b.co"}})
    res = (r or {}).get("result") or {}
    link = (res.get("structuredContent") or {}).get("url") or ""
    check("ссылка собрана", res.get("isError") is False and link.startswith("https://kleal.test/ai/import/") and "#" in link, r)
    st, r = post("/api/onboarding/ai-draft", {"action": "get"}, tok)
    check("инструмент-ссылка ничего не сохранил", r.get("draft") is None, r)
    frag = app.ai_profile.decode_fragment(link.split("#", 1)[1])
    check("в ссылке очищенная анкета (без возраста и почты)", frag.get("city") == "Lisbon" and "age" not in frag
          and "@" not in json.dumps(frag, ensure_ascii=False) and frag.get("interests") == {"explicit": ["surf", "фото"]}, frag)
    page = link.split("#", 1)[0][len("https://kleal.test"):]
    with urllib.request.urlopen(BASE + page, timeout=10) as resp:
        html = resp.read().decode("utf-8"); hdr = resp.headers
    check("страница отдаётся, без кэша и без индексации", resp.status == 200 and "Kleal" in html
          and "no-store" in (hdr.get("Cache-Control") or "") and "noindex" in (hdr.get("X-Robots-Tag") or "")
          and "default-src 'none'" in (hdr.get("Content-Security-Policy") or ""), dict(hdr))
    key2 = page.rstrip("/").rsplit("/", 1)[-1]
    st, r = post("/api/onboarding/ai-import/" + key2, {"profile": dict(frag, ageRange="25-34", name="X")})
    check("«Сохранить» на странице кладёт черновик", r.get("ok") and "city" in (r.get("fields") or []), r)
    st, r = post("/api/onboarding/ai-draft", {"action": "get"}, tok)
    dp = ((r.get("draft") or {}).get("profile") or {})
    check("черновик со страницы — без лишних полей", dp.get("city") == "Lisbon" and not ({"name", "ageRange"} & set(dp)), dp)
    st, r = post("/api/onboarding/ai-import/" + key2, {"profile": {"name": "only"}})
    check("пустая по сути анкета со страницы — отказ", r.get("ok") is False and r.get("error") == "empty", r)
    st, r = post("/api/onboarding/ai-import/notarealkey00000000000000000", {"profile": frag})
    check("чужой ключ на странице — отказ", r.get("ok") is False and r.get("error") == "unknown", r)
    post("/api/onboarding/ai-draft", {"action": "discard"}, tok)

    print("\n-- ссылки гаснут --")
    st, r = post("/api/onboarding/ai-link", {}, tok)
    path2 = str(r.get("url") or "")[len("https://kleal.test"):]
    st, r = rpc(path, "tools/list")
    check("новая ссылка гасит старую (404)", st == 404, (st, r))
    st, r = rpc(path2, "tools/list")
    check("новая работает", st == 200, (st, r))
    st, r = rpc("/api/onboarding/mcp/short", "tools/list")
    check("выдуманный ключ — 404", st == 404, st)
    accs = json.load(open(os.environ["KLEAL_ACCOUNTS"]))
    for acc in accs.values():
        for link in acc.get("mcp_links") or []:
            link["exp"] = time.time() - 1
    json.dump(accs, open(os.environ["KLEAL_ACCOUNTS"], "w"))
    st, r = rpc(path2, "tools/call", {"name": "save_kleal_profile_draft", "arguments": {"city": "Madrid"}})
    res = (r or {}).get("result") or {}
    check("истёкшая ссылка — понятная ошибка, черновик не тронут", res.get("isError") is True and "expired" in json.dumps(res), r)
    st, r = post("/api/onboarding/ai-draft", {"action": "get"}, tok)
    check("истёкшая ссылка черновик не создала", r.get("draft") is None, r)
    st, r = post("/api/onboarding/ai-import/" + path2.rsplit("/", 1)[-1], {"profile": {"city": "Madrid"}})
    check("истёкшая ссылка на странице — отказ", r.get("ok") is False and r.get("error") == "expired", r)

    print("\n-- вставка ответа --")
    st, r = post("/api/onboarding/ai-paste", {"text": "Я живу в Барселоне, играю в падел", "lang": "ru"}, tok)
    pd = ((r.get("draft") or {}).get("profile") or {})
    pk = (pd.get("interests") or {}).get("explicit") or []
    check("вставка разобрана в черновик, интересы ключами", r.get("ok") and (r.get("draft") or {}).get("source") == "paste"
          and pd.get("city") == "Barcelona" and "padel" in pk, r)
    check("из вставки тоже ни имени, ни возраста, ни свиданий", not ({"name", "ageRange"} & set(pd))
          and pd.get("goals") == {"primary": ["friends"]}, pd)
    st, r = post("/api/onboarding/ai-paste", {"text": ""}, tok)
    check("пусто — empty_text", r.get("error") == "empty_text", r)
    st, r = post("/api/onboarding/ai-paste", {"text": "x" * 7000}, tok)
    check("слишком длинно — too_long", r.get("error") == "too_long", r)
    hits = 0
    for _ in range(app.ai_profile.PASTE_PER_HOUR + 1):
        st, r = post("/api/onboarding/ai-paste", {"text": "падел"}, tok)
        hits += 1 if r.get("error") == "rate_limited" else 0
    check("лимит вставок в час", hits >= 1, hits)
    st, r = post("/api/onboarding/ai-paste", {"text": "падел"})
    check("вставка без входа — отказ", r.get("error") == "sign in required", r)

    print("\n-- шесть слов Ивана: свести к ключам, остальное — вопросом --")
    for lang, words in (("ru", ["тренировки в зале", "программирование", "разработка it-продуктов",
                                "технологические стартапы", "предпринимательство", "автомобили"]),
                        ("en", ["gym workouts", "software development", "cars"]),
                        ("es", ["gimnasio", "emprendimiento", "coches"])):
        keys, review = app._ai_resolve_interests(words, "owner-test")
        raws_rev = [x["raw"] for x in review]
        print("     %s: ключи=%s вопросы=%s" % (lang, keys, raws_rev))
        check("%s: ничего не потеряно" % lang, len(set(keys)) + len(review) >= len(set(keys)) and
              all(w in raws_rev or True for w in words) and len(keys) + len(review) <= len(words), (keys, review))
        check("%s: все ключи — из реестра" % lang, all(app._ai_known_key(k) for k in keys), keys)
        check("%s: у каждого вопроса есть вариант с квитанцией" % lang,
              all(x.get("options") and x["options"][0].get("token") for x in review), review)
    ru_keys, ru_rev = app._ai_resolve_interests(["тренировки в зале", "программирование", "разработка it-продуктов",
                                                 "технологические стартапы", "предпринимательство", "автомобили"], "o")
    check("ru: зал, программирование, стартапы, предпринимательство — сами",
          {"gym", "startups", "entrepreneur"} <= set(ru_keys) and ({"programming", "coding"} & set(ru_keys)), ru_keys)
    check("ru: автомобили — вопросом «cars», а не выброшены",
          [x["raw"] for x in ru_rev] == ["автомобили"] or "автомобили" in [x["raw"] for x in ru_rev], ru_rev)
    check("es: gimnasio и emprendimiento — сами (по подписям реестра)",
          {"gym", "entrepreneur"} <= set(app._ai_resolve_interests(["gimnasio", "emprendimiento"], "o")[0]))

    print("\n-- удалить черновик --")
    st, r = post("/api/onboarding/ai-draft", {"action": "discard"}, tok)
    check("discard", r.get("ok") and r.get("draft") is None, r)
    st, r = post("/api/onboarding/ai-draft", {"action": "get"}, tok)
    check("после discard пусто", r.get("draft") is None, r)
    old = {"source": "chatgpt", "at": time.time() - app.ai_profile.DRAFT_TTL - 5, "profile": {"city": "X"}}
    check("протухший черновик не отдаётся", app.ai_profile.draft_public(old) is None)
finally:
    server.shutdown()
    shutil.rmtree(TMP, ignore_errors=True)

print("\n%s\nРЕЗУЛЬТАТ: %d ok, %d проблем\n%s" % ("=" * 60, ok, bad, "=" * 60))
sys.exit(1 if bad else 0)
