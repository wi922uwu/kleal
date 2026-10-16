# -*- coding: utf-8 -*-
"""Тёзки через HTTP с настоящими сессиями: переписка, заявки, планы, группы, блок, перевод старых записей.

    python3 tools/identity_http_test.py

Сам поднимает сервис матчинга на свободном порту с временными файлами (KLEAL_DB=json) — боевые
данные не трогает. Сторож правила «личность = id» (docs/IDENTITY.md) там, где его нарушение было
видно людям: 26.09.2026 по одному имени «Иван» любой читал чужую переписку, а четыре аккаунта
«Иван» видели общие интенты.
"""
import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

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


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    tmp = tempfile.mkdtemp(prefix="kleal_idhttp_")
    now = int(time.time())
    old, mid = now - 40 * 86400, now - 20 * 86400
    TOK = {"A": "tok-ivan-old", "B": "tok-ivan-new", "C": "tok-anna"}
    acc = {
        "a@x.test": {"email": "a@x.test", "created": old, "name": "Иван", "person_id": "on_a",
                     "sessions": {sha(TOK["A"]): {"created": now, "exp": now + 3600, "last": now}}},
        "b@x.test": {"email": "b@x.test", "created": now - 60, "name": "Иван", "person_id": "on_b",
                     "sessions": {sha(TOK["B"]): {"created": now, "exp": now + 3600, "last": now}}},
        "c@x.test": {"email": "c@x.test", "created": old, "name": "Анна", "person_id": "on_c",
                     "sessions": {sha(TOK["C"]): {"created": now, "exp": now + 3600, "last": now}}},
    }
    base = {"age": 30, "city": "Barcelona", "lat": 41.39, "lon": 2.17, "interests": ["coffee"],
            "langs": ["ru", "en"], "source": "onboarding", "open": True}
    users = [dict(base, id="on_a", owner="a@x.test", name="Иван"),
             dict(base, id="on_b", owner="b@x.test", name="Иван"),
             dict(base, id="on_c", owner="c@x.test", name="Анна"),
             dict(base, id="on_d", name="Дина")]
    # СТАРЫЕ записи по ИМЕНАМ — как в хранилище до перевода: заявка и переписка «Иван» ↔ «Анна»,
    # сделанные, когда второго «Ивана» ещё не было.
    store = {
        "_requests": [{"id": "rq_legacy", "from": "Анна", "to": "Иван", "status": "accepted",
                       "created": mid, "updated": mid, "version": 2, "intent": {}}],
        "_messages": [{"id": "m_legacy", "pair": "анна|иван", "from": "Иван", "to": "Анна",
                       "text": "старое привет", "t": mid, "u": mid}],
        "_blocks": {},
    }
    paths = {k: os.path.join(tmp, k) for k in ("users.json", "accounts.json", "store.json")}
    json.dump({"users": users}, open(paths["users.json"], "w"), ensure_ascii=False)
    json.dump(acc, open(paths["accounts.json"], "w"), ensure_ascii=False)
    json.dump(store, open(paths["store.json"], "w"), ensure_ascii=False)
    port = free_port()
    env = dict(os.environ, KLEAL_DB="json", KLEAL_USERS=paths["users.json"],
               KLEAL_ACCOUNTS=paths["accounts.json"], KLEAL_STORE=paths["store.json"],
               MATCHING_PORT=str(port), LLM_URL="http://127.0.0.1:9")
    log = open(os.path.join(tmp, "server.log"), "w")
    srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "services", "matching", "app.py")],
                           cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    BASE = "http://127.0.0.1:%d" % port
    try:
        for _ in range(120):
            try:
                urllib.request.urlopen(BASE + "/health", timeout=2)
                break
            except Exception:
                time.sleep(1)

        def call(path, body=None, who=None):
            data = json.dumps(body).encode("utf-8") if body is not None else None
            req = urllib.request.Request(BASE + path, data=data, method="POST" if data else "GET",
                                         headers={"Content-Type": "application/json"})
            if who:
                req.add_header("Authorization", "Bearer " + TOK[who])
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8") or "{}")

        q = urllib.parse.quote

        print("\n-- перевод старых записей по именам --")
        th_a = call("/api/agent/threads?self=" + q("Иван"), who="A").get("threads") or []
        th_b = call("/api/agent/threads?self=" + q("Иван"), who="B").get("threads") or []
        check("старую переписку видит старый «Иван»", [t.get("who") for t in th_a] == ["Анна"], th_a)
        check("новый «Иван» старую переписку НЕ видит", th_b == [], th_b)
        check("собеседник отдаётся подписью И id", (th_a[:1] or [{}])[0].get("who_id") == "on_c", th_a)

        print("\n-- без сессии чужое не читается --")
        anon = call("/api/agent/threads?self=" + q("Иван")).get("threads") or []
        check("без токена по имени «Иван» переписки нет", anon == [], anon)
        inbox = call("/api/agent/inbox?self=" + q("Иван")).get("requests") or []
        check("без токена по имени «Иван» входящих нет", inbox == [], inbox)
        w = call("/api/agent/message", {"from": "Иван", "to": "Анна", "text": "подделка"})
        check("без токена писать от имени «Иван» нельзя", w.get("ok") is False, w)

        print("\n-- тёзки в переписке --")
        amb = call("/api/agent/propose", {"from": "Анна", "to": "Иван", "intent": {}}, who="C")
        check("позвать «Ивана» без id нельзя — их двое", amb.get("error") == "AMBIGUOUS_PERSON", amb)
        pr = call("/api/agent/propose", {"to": "Иван", "to_id": "on_b", "intent": {"topics": ["chess"]}},
                  who="C")
        check("по id — можно", pr.get("ok") is True, pr)
        ib_b = call("/api/agent/inbox", who="B").get("requests") or []
        ib_a = call("/api/agent/inbox", who="A").get("requests") or []
        check("приглашение пришло новому «Ивану»", [r.get("id") for r in ib_b] == [pr.get("id")], ib_b)
        check("старому «Ивану» оно не пришло", pr.get("id") not in [r.get("id") for r in ib_a], ib_a)
        check("отправитель в заявке — подписью и id",
              (ib_b[:1] or [{}])[0].get("from") == "Анна" and (ib_b[:1] or [{}])[0].get("from_id") == "on_c",
              ib_b)
        stolen = call("/api/agent/respond", {"id": pr.get("id"), "decision": "accept"}, who="A")
        check("старый «Иван» не может принять чужое приглашение", stolen.get("ok") is False, stolen)
        acc_b = call("/api/agent/respond", {"id": pr.get("id"), "decision": "accept"}, who="B")
        check("новый «Иван» принимает своё", acc_b.get("ok") is True, acc_b)
        sm = call("/api/agent/message", {"to": "Анна", "to_id": "on_c", "text": "привет от нового"}, who="B")
        check("новый «Иван» пишет Анне", sm.get("ok") is True, sm)
        msgs_c_b = call("/api/agent/thread?with=%s&with_id=on_b" % q("Иван"), who="C").get("messages") or []
        msgs_c_a = call("/api/agent/thread?with=%s&with_id=on_a" % q("Иван"), who="C").get("messages") or []
        check("у Анны две разные переписки с двумя «Иванами»",
              [m.get("text") for m in msgs_c_b] == ["привет от нового"]
              and [m.get("text") for m in msgs_c_a] == ["старое привет"], (msgs_c_a, msgs_c_b))
        leak = call("/api/agent/thread?with=%s&with_id=on_c" % q("Анна"), who="A").get("messages") or []
        check("старый «Иван» не видит переписку нового с Анной",
              "привет от нового" not in [m.get("text") for m in leak], leak)

        print("\n-- старое приложение: подпись без id, но связь только с одним из тёзок --")
        pd = call("/api/agent/propose", {"from": "Дина", "to": "Иван", "to_id": "on_b", "intent": {}})
        check("Дина (бот без сессии) зовёт нового «Ивана» по id", pd.get("ok") is True, pd)
        call("/api/agent/respond", {"id": pd.get("id"), "decision": "accept"}, who="B")
        md = call("/api/agent/message", {"from": "Дина", "to": "Иван", "text": "без id"})
        check("пишет «Ивану» без id — доходит тому, с кем связь", md.get("ok") is True, md)
        tb = call("/api/agent/thread?with=%s&with_id=on_d" % q("Дина"), who="B").get("messages") or []
        check("и это новый «Иван»", "без id" in [m.get("text") for m in tb], tb)
        ta = call("/api/agent/thread?with=%s" % q("Дина"), who="A").get("messages") or []
        check("старый «Иван» этого не видит", "без id" not in [m.get("text") for m in ta], ta)
        rd = call("/api/agent/thread?self=%s&with=%s" % (q("Дина"), q("Иван"))).get("messages") or []
        check("Дина читает переписку с «Иваном» без id", "без id" in [m.get("text") for m in rd], rd)

        print("\n-- план 1:1 --")
        mp = call("/api/agent/mplan-propose", {"to": "Анна", "to_id": "on_c", "starts_at": now + 3 * 86400,
                                               "when": "пт 19:00", "district": "Gràcia"}, who="B")
        check("новый «Иван» предлагает Анне встречу", mp.get("ok") is True, mp)
        pa = call("/api/agent/mplans", who="A").get("plans") or []
        pb = call("/api/agent/mplans", who="B").get("plans") or []
        check("план видит только новый «Иван»", len(pb) == 1 and pa == [], (pa, pb))
        part = [(x.get("name"), x.get("name_id") or x.get("id")) for x in (pb[:1] or [{}])[0].get("participants") or []]
        check("участники — подписью и id", ("Иван", "on_b") in part and ("Анна", "on_c") in part, part)

        print("\n-- группа --")
        g = call("/api/agent/gintent-create", {"intent": {"topics": ["coffee"], "title": "Кофе"}}, who="C")
        gid = (g.get("group") or {}).get("gid")
        check("Анна создаёт группу", bool(gid), g)
        inv = call("/api/agent/gintent-invite", {"gid": gid, "to": "Иван", "to_id": "on_a"}, who="C")
        check("зовёт старого «Ивана» по id", inv.get("ok") is True, inv)
        gi_b = call("/api/agent/gintents", who="B")
        gi_a = call("/api/agent/gintents", who="A")
        inv_ids_a = [(i.get("invite") or {}).get("id") for i in (gi_a.get("invites") or [])]
        inv_ids_b = [(i.get("invite") or {}).get("id") for i in (gi_b.get("invites") or [])]
        my_inv = (inv.get("invite") or {}).get("id")
        check("приглашение в группу — у старого, не у нового",
              my_inv in inv_ids_a and my_inv not in inv_ids_b, (inv_ids_a, inv_ids_b))
        steal = call("/api/agent/ginvite-respond", {"id": my_inv, "accept": True}, who="B")
        check("новый «Иван» не может принять чужое приглашение в группу", steal.get("ok") is False, steal)
        join = call("/api/agent/ginvite-respond", {"id": my_inv, "accept": True}, who="A")
        check("старый принимает", join.get("ok") is True, join)
        post_b = call("/api/agent/gintent-post", {"gid": gid, "text": "я тут?"}, who="B")
        check("новый «Иван» не пишет в чужую группу", post_b.get("ok") is False, post_b)
        th = call("/api/agent/gintent-thread?gid=" + gid, who="A")
        lines = [m.get("text") for m in (th.get("messages") or th.get("thread") or [])]
        check("в строке «вступил» — подпись, а не id",
              any("Иван joined" in (t or "") for t in lines) and not any("on_a" in (t or "") for t in lines),
              lines)

        print("\n-- блок --")
        bl = call("/api/agent/block", {"name": "Иван", "name_id": "on_b"}, who="C")
        check("Анна блокирует нового «Ивана» по id", bl.get("ok") is True, bl)
        m2 = call("/api/agent/message", {"to": "Анна", "to_id": "on_c", "text": "ещё"}, who="B")
        check("ему писать нельзя", m2.get("error") == "BLOCKED", m2)
        m3 = call("/api/agent/message", {"to": "Анна", "to_id": "on_c", "text": "я старый"}, who="A")
        check("а старому «Ивану» блок не мешает", m3.get("ok") is True, m3)
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except Exception:
            srv.kill()
    print("\nитог: %d ok, %d FAIL" % (ok, bad))
    if bad:
        print("журнал сервиса: %s" % os.path.join(tmp, "server.log"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
