# -*- coding: utf-8 -*-
"""Панель модерации и тёзки — сторож правила «личность = id» (docs/IDENTITY.md).

    python3 tools/identity_admin_test.py

Сам поднимает матчинг и панель на свободных портах с временными файлами (KLEAL_DB=json) — боевые
данные не трогает. ЗАЧЕМ: до 27.09.2026 пауза и бан «Ивана» по имени ложились на ПЕРВОГО «Ивана»
в базе, а не на того, на кого пожаловались; карточка брала id первого тёзки.
"""
import hashlib, json, os, socket, subprocess, sys, tempfile, time, urllib.request, urllib.parse, urllib.error
root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ok = bad = 0
def check(n, c, x=""):
    global ok, bad
    if c: ok += 1; print("  ok   " + n)
    else: bad += 1; print("  FAIL %s   %s" % (n, str(x)[:300]))
def sha(s): return hashlib.sha256(s.encode()).hexdigest()
def port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
tmp = tempfile.mkdtemp(); now = int(time.time())
acc = {"a@x.test": {"email": "a@x.test", "created": now - 9e5, "name": "Иван", "person_id": "on_a", "sessions": {}},
       "b@x.test": {"email": "b@x.test", "created": now - 60, "name": "Иван", "person_id": "on_b", "sessions": {}},
       "c@x.test": {"email": "c@x.test", "created": now - 9e5, "name": "Анна", "person_id": "on_c",
                    "sessions": {sha("tok-c"): {"created": now, "exp": now + 3600, "last": now}}}}
base = {"age": 30, "city": "Barcelona", "lat": 41.39, "lon": 2.17, "langs": ["ru", "en"],
        "interests": ["coffee"], "source": "onboarding", "open": True}
users = [dict(base, id="on_a", owner="a@x.test", name="Иван"), dict(base, id="on_b", owner="b@x.test", name="Иван"),
         dict(base, id="on_c", owner="c@x.test", name="Анна")]
up = tmp + "/u.json"
json.dump({"users": users}, open(up, "w"), ensure_ascii=False)
json.dump(acc, open(tmp + "/a.json", "w"), ensure_ascii=False)
EV = "0123456789abcdef0123456789abcdef"
os.makedirs(tmp + "/evidence")
open(tmp + "/evidence/%s.pdf" % EV, "wb").write(b"%PDF evidence")
json.dump({"_reports": [{"id": "rp1", "by": "on_c", "about": "on_b", "reason": "spam", "at": now},
                        {"id": "rg1", "kind": "group", "gid": "gi_x", "group_title": "Бар", "by": "on_c",
                         "about": "", "reason": "harassment_or_threats", "case_no": "G-ABC123",
                         "evidence": [{"id": EV, "name": "screen.pdf", "mime_type": "application/pdf", "size": 13}],
                         "at": now}],
           "_evidence": {EV: {"id": EV, "by": "on_c", "name": "screen.pdf", "mime_type": "application/pdf",
                              "size": 13, "file": EV + ".pdf", "at": now}}},
          open(tmp + "/s.json", "w"), ensure_ascii=False)
pm, pa = port(), port()
TOK = "admin-test-token"
env = dict(os.environ, KLEAL_DB="json", KLEAL_USERS=up, KLEAL_ACCOUNTS=tmp + "/a.json", KLEAL_STORE=tmp + "/s.json",
           KLEAL_ROOT=root, MATCHING_PORT=str(pm), ADMIN_PORT=str(pa), MATCH_URL="http://127.0.0.1:%d" % pm,
           KLEAL_ADMIN_TOKEN=TOK, LLM_URL="http://127.0.0.1:9", FILTER_URL="http://127.0.0.1:9",
           KLEAL_EVIDENCE_DIR=tmp + "/evidence")
procs = [subprocess.Popen([sys.executable, "services/matching/app.py"], cwd=root, env=env,
                          stdout=open(tmp + "/m.log", "w"), stderr=subprocess.STDOUT),
         subprocess.Popen([sys.executable, "services/admin/app.py"], cwd=root, env=env,
                          stdout=open(tmp + "/ad.log", "w"), stderr=subprocess.STDOUT)]
def call(url, body=None, hdr=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 method="POST" if body is not None else "GET",
                                 headers=dict({"Content-Type": "application/json"}, **(hdr or {})))
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode() or "{}")
A = lambda path, body=None: call("http://127.0.0.1:%d%s" % (pa, path), body, {"X-Admin-Token": TOK})
def row(uid): return next(u for u in json.load(open(up))["users"] if u["id"] == uid)
q = urllib.parse.quote
try:
    for p in (pm, pa):
        for _ in range(120):
            try: urllib.request.urlopen("http://127.0.0.1:%d/health" % p, timeout=2); break
            except Exception: time.sleep(1)
    print("\n-- карточка --")
    r = A("/api/admin/person?name=" + q("Иван"))
    check("по имени тёзок — выбор, а не первый попавшийся",
          r.get("error") == "AMBIGUOUS_PERSON" and sorted(c["id"] for c in r.get("candidates") or []) == ["on_a", "on_b"], r)
    r = A("/api/admin/person?name=%s&id=on_b" % q("Иван"))
    check("по id — карточка нового «Ивана»", r.get("id") == "on_b", r)
    r = A("/api/admin/person?name=" + q("Анна"))
    check("однозначное имя по-прежнему работает", r.get("id") == "on_c", r)
    print("\n-- пауза --")
    r = A("/api/admin/person/verb", {"name": "Иван", "verb": "pause"})
    check("пауза по имени тёзок — отказ", r.get("ok") is False and r.get("error") == "AMBIGUOUS_PERSON", r)
    r = A("/api/admin/person/verb", {"name": "Иван", "id": "on_b", "verb": "pause"})
    check("пауза по id прошла", r.get("ok") is True, r)
    check("на паузе новый «Иван», старый — нет", row("on_b").get("paused") and not row("on_a").get("paused"),
          (row("on_a").get("paused"), row("on_b").get("paused")))
    print("\n-- бан --")
    r = A("/api/admin/ban", {"name": "Иван", "on": True})
    check("бан по имени тёзок — отказ", r.get("ok") is False, r)
    r = A("/api/admin/ban", {"name": "Иван", "id": "on_b", "on": True})
    check("бан по id прошёл", r.get("ok") is True and r.get("id") == "on_b", r)
    check("забанен новый «Иван», старый — нет",
          row("on_b").get("accountStatus") == "banned" and row("on_a").get("accountStatus") != "banned",
          (row("on_a").get("accountStatus"), row("on_b").get("accountStatus")))
    r = A("/api/admin/ban", {"name": "Иван", "id": "on_b", "on": False})
    check("снятие бана по id", r.get("ok") is True and row("on_b").get("accountStatus") != "banned", r)
    print("\n-- жалобы и ответ --")
    r = A("/api/admin/reports")
    rep = next((x for x in r.get("reports") or [] if x.get("id") == "rp1"), {})
    check("в жалобе есть id обоих", rep.get("about_id") == "on_b" and rep.get("by_id") == "on_c", rep)
    r = A("/api/admin/notify", {"to": "Анна", "to_id": "on_c", "text": "Мы разобрались", "ref": "rp1"})
    check("ответ модератора ушёл по id", r.get("ok") is True, r)
    th = call("http://127.0.0.1:%d/api/agent/threads" % pm, None, {"Authorization": "Bearer tok-c"}).get("threads") or []
    check("и пришёл Анне", any("разобрались" in str(t.get("last") or "") for t in th), th)
    print("\n-- жалоба на группу --")
    r = A("/api/admin/reports")
    g = next((x for x in r.get("reports") or [] if x.get("id") == "rg1"), {})
    check("жалоба на группу в очереди, с группой и файлом",
          g.get("kind") == "group" and g.get("group_title") == "Бар" and (g.get("evidence") or [{}])[0].get("id") == EV, g)
    req = urllib.request.Request("http://127.0.0.1:%d/api/admin/evidence/%s" % (pa, EV), headers={"X-Admin-Token": TOK})
    check("панель отдаёт файл по токену", urllib.request.urlopen(req, timeout=30).read() == b"%PDF evidence")
    try:
        urllib.request.urlopen("http://127.0.0.1:%d/api/admin/evidence/%s" % (pa, EV), timeout=30)
        check("без токена файла нет", False)
    except urllib.error.HTTPError as e:
        check("без токена файла нет", e.code == 401, e.code)

    print("\n-- лаборатория --")
    r = A("/api/admin/match-test", {"self": "on_b", "intent": {"topics": ["coffee"], "mode": "offline"}, "limit": 5})
    check("поиск от имени по id узнаёт человека", r.get("searcherKnown") is True, {k: r.get(k) for k in ("searcherKnown", "error")})
finally:
    for p in procs: p.terminate()
print("\nитог: %d ok, %d FAIL   (журналы %s)" % (ok, bad, tmp))
sys.exit(1 if bad else 0)
