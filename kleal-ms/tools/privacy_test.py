# -*- coding: utf-8 -*-
"""Приватность: что видит посторонний. Сторож находок аудита 27.09.2026.

    python3 tools/privacy_test.py

Сам поднимает матчинг на свободном порту с временными файлами (KLEAL_DB=json, KLEAL_GROUPS=1) —
боевые данные не трогает.

1. ГРУППА ПО ID. До 27.09 `/api/agent/gintent?gid=` отдавал группу любому, даже без входа, а id
   групп лежат в открытой ленте карты: посторонний видел состав, время, МЕСТО встречи и ссылку на
   звонок. Теперь: участник — всё; приглашённый — состав и время, без места и ссылки; посторонний —
   витрину без людей и без плана.
2. СЛУЖЕБНЫЕ РУЧКИ МАТЧИНГА снаружи были открыты без входа — в том числе пишущие в общий словарь
   категорий и в журналы движка. Шлюз их закрывает; все адреса приложения проходят.
3. УДАЛЕНИЕ УЧЁТКИ из приложения стирало только анкету и учётку: интенты оставались на карте,
   переписка, группы и фото — на сервере. Теперь уходит всё, что человек оставил.
4. ЗАВЕРШИТЬ ГРУППУ И ПОЖАЛОВАТЬСЯ НА ГРУППУ — ручек не было с 14.09, обе кнопки приложения
   всегда отвечали ошибкой; пожаловаться на группу было невозможно. Договор — S10/S11
   (tools/s10_group_close_unit.py, tools/s11_group_report_unit.py); здесь — сквозь HTTP.
"""
import hashlib
import importlib.util
import re
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
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


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    tmp = tempfile.mkdtemp(prefix="kleal_privacy_")
    now = int(time.time())
    tok = "tok-privacy-del"
    sha = hashlib.sha256(tok.encode()).hexdigest()
    tok_rep = "tok-privacy-rep"
    acc = {"del@x.test": {"email": "del@x.test", "created": now - 9e5, "name": "Удалёнов",
                          "person_id": "on_del", "sessions": {sha: {"created": now, "exp": now + 3600, "last": now}}},
           "rep@x.test": {"email": "rep@x.test", "created": now - 9e5, "name": "Жалобин", "person_id": "on_rep",
                          "sessions": {hashlib.sha256(tok_rep.encode()).hexdigest():
                                       {"created": now, "exp": now + 3600, "last": now}}}}
    row = {"id": "on_del", "owner": "del@x.test", "name": "Удалёнов", "age": 30, "city": "Barcelona",
           "lat": 41.39, "lon": 2.17, "interests": ["coffee"], "langs": ["ru", "en"],
           "source": "onboarding", "open": True, "photo": "/api/onboarding/photo/on_del.jpg"}
    os.makedirs(os.path.join(tmp, "photos"))
    open(os.path.join(tmp, "photos", "on_del.jpg"), "wb").write(b"\xff\xd8\xff")
    voice_dir = os.path.join(tmp, "voice")
    os.makedirs(voice_dir)
    vname = "0123456789abcdef0123456789abcdef.m4a"
    open(os.path.join(voice_dir, vname), "wb").write(b"voice")
    # Голосовое удаляемого в группе — заранее, в хранилище: через API нужен настоящий аудиофайл.
    seed = {"_gmsgs": [{"id": "gm_voice", "gid": "gi_seed", "frm": "on_del", "text": "",
                        "voice": {"url": "/api/agent/voice/" + vname}, "t": now, "u": now}]}
    row_rep = dict(row, id="on_rep", owner="rep@x.test", name="Жалобин", photo="")
    for name, body in (("users.json", {"users": [row, row_rep]}), ("accounts.json", acc), ("store.json", seed)):
        json.dump(body, open(os.path.join(tmp, name), "w"), ensure_ascii=False)
    port, oport = free_port(), free_port()
    env = dict(os.environ, KLEAL_DB="json", KLEAL_GROUPS="1",
               KLEAL_USERS=os.path.join(tmp, "users.json"),
               KLEAL_ACCOUNTS=os.path.join(tmp, "accounts.json"),
               KLEAL_STORE=os.path.join(tmp, "store.json"), KLEAL_VOICE_DIR=voice_dir,
               KLEAL_EVIDENCE_DIR=os.path.join(tmp, "evidence"),
               MATCHING_PORT=str(port), ONBOARDING_PORT=str(oport),
               MATCH_URL="http://127.0.0.1:%d" % port, LLM_URL="http://127.0.0.1:9")
    log = open(os.path.join(tmp, "server.log"), "w")
    srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "services", "matching", "app.py")],
                           cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    onb = subprocess.Popen([sys.executable, os.path.join(ROOT, "services", "onboarding", "app.py")],
                           cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = "http://127.0.0.1:%d" % port

    def call(path, body=None, token=None, at=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request((at or base) + path, data=data, method="POST" if data else "GET",
                                     headers={"Content-Type": "application/json"})
        if token:
            req.add_header("Authorization", "Bearer " + token)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as e:
            return {"_http": e.code}

    try:
        for b in (base, "http://127.0.0.1:%d" % oport):
            for _ in range(120):
                try:
                    urllib.request.urlopen(b + "/health", timeout=2)
                    break
                except Exception:
                    time.sleep(1)
        stamp = int(time.time())
        own, mem, inv = "ПрОрг%d" % stamp, ["ПрУч%d_%d" % (stamp, i) for i in range(3)], "ПрЗван%d" % stamp

        print("\n-- группа с планом: место и ссылка --")
        c = call("/api/agent/gintent-create", {"self": own, "title": "Кофе", "intent": {"topics": ["coffee"],
                                               "mode": "hybrid"}, "max_total": 8})
        gid = (c.get("group") or {}).get("gid")
        sent = call("/api/agent/gintent-invite", {"gid": gid, "self": own, "to": mem}).get("sent") or []
        for x in sent:
            call("/api/agent/ginvite-respond", {"id": x["id"], "self": x["to"], "accept": True})
        call("/api/agent/gintent-invite", {"gid": gid, "self": own, "to": inv})
        pb = call("/api/agent/gplan-begin", {"gid": gid, "self": own, "when": "сб 19:00", "mode": "hybrid",
                                             "place": "Nomad Coffee, Carrer de Pujades 95",
                                             "link": "https://meet.example/secret",
                                             "starts_at": time.time() + 3 * 86400})
        check("план с местом и ссылкой заведён", bool((pb.get("plan") or {}).get("id")), pb)

        def view(who):
            q = "/api/agent/gintent?gid=%s" % gid + ("&self=%s" % urllib.request.quote(who) if who else "")
            return call(q).get("group") or {}

        m = view(mem[0])
        check("участник видит место и ссылку",
              (m.get("plan") or {}).get("place") and (m.get("plan") or {}).get("link"), m.get("plan"))
        i = view(inv)
        check("приглашённый видит, кто внутри", len(i.get("members") or []) == 4, i.get("members"))
        check("приглашённый видит время", (i.get("plan") or {}).get("when") == "сб 19:00", i.get("plan"))
        check("приглашённый НЕ видит места и ссылки",
              not (i.get("plan") or {}).get("place") and not (i.get("plan") or {}).get("link"), i.get("plan"))
        for who, label in (("", "без входа"), ("ПрЧужой%d" % stamp, "чужой")):
            s = view(who)
            check("посторонний (%s) видит витрину" % label, s.get("gid") == gid and s.get("title") == "Кофе", s)
            check("посторонний (%s) не видит людей" % label,
                  not s.get("members") and not s.get("departed") and not s.get("awaiting_approval"), s)
            check("посторонний (%s) не видит плана" % label, not s.get("plan"), s.get("plan"))

        print("\n-- служебные ручки снаружи закрыты --")
        sys.path.insert(0, os.path.join(ROOT, "shared"))
        spec = importlib.util.spec_from_file_location("gw", os.path.join(ROOT, "services", "gateway", "app.py"))
        gw = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gw)
        for path in ("/api/agent/learn", "/api/agent/learn-phrases", "/api/agent/outcome",
                     "/api/agent/transition", "/api/agent/proposal", "/api/agent/save",
                     "/api/agent/explain", "/api/agent/negotiate"):
            check("шлюз закрывает %s" % path, gw.route(path)[0] == "BLOCK", gw.route(path))
        app = os.path.join(os.path.dirname(ROOT), "kleal-app")
        if os.path.isdir(app):
            client = set()
            for dp, dn, fn in os.walk(app):
                if "node_modules" in dp:
                    continue
                for f in fn:
                    if f.endswith((".ts", ".tsx")):
                        client |= set(m.rstrip("/") for m in re.findall(
                            r"""['"`](/api/[A-Za-z0-9_\-/]+)""", open(os.path.join(dp, f), encoding="utf-8").read()))
            shut = sorted(c for c in client if gw.route(c)[0] == "BLOCK")
            check("ни один адрес приложения не закрыт (%d)" % len(client), not shut, shut)

        print("\n-- удаление учётки уносит всё --")
        s = call("/api/agent/intent-save", {"intent": {"topics": ["coffee"], "mode": "offline"},
                                            "title": "кофе"}, token=tok)
        check("у удаляемого есть интент", s.get("ok") is True, s)
        other = "ПрДруг%d" % stamp
        pr = call("/api/agent/propose", {"from": other, "to": "Удалёнов", "to_id": "on_del", "intent": {}})
        call("/api/agent/respond", {"id": pr.get("id"), "decision": "accept"}, token=tok)
        call("/api/agent/message", {"to": other, "text": "привет"}, token=tok)
        g2 = (call("/api/agent/gintent-create", {"self": other, "title": "Бег",
                                                 "intent": {"topics": ["running"]}}).get("group") or {}).get("gid")
        iv = call("/api/agent/gintent-invite", {"gid": g2, "self": other, "to": "Удалёнов", "to_id": "on_del"})
        call("/api/agent/ginvite-respond", {"id": (iv.get("invite") or {}).get("id"), "accept": True}, token=tok)
        call("/api/agent/gintent-post", {"gid": g2, "text": "я в группе"}, token=tok)
        before = call("/api/agent/gintent?gid=%s&self=%s" % (g2, urllib.request.quote(other))).get("group") or {}
        check("удаляемый в группе", len(before.get("members") or []) == 2, before.get("members"))
        d = call("/api/onboarding/delete-account", {}, token=tok, at="http://127.0.0.1:%d" % oport)
        check("учётка удалена", d.get("ok") is True and d.get("profile") and d.get("account"), d)
        check("стирание в матчинге прошло", isinstance(d.get("purged"), dict), d.get("purged"))
        after = call("/api/agent/gintent?gid=%s&self=%s" % (g2, urllib.request.quote(other))).get("group") or {}
        check("из группы ушёл", len(after.get("members") or []) == 1, after.get("members"))
        gth = call("/api/agent/gintent-thread?gid=%s&self=%s" % (g2, urllib.request.quote(other))).get("messages") or []
        check("его реплик в группе нет", not any("я в группе" in str(m.get("text")) for m in gth),
              [m.get("text") for m in gth])
        th = call("/api/agent/thread?self=%s&with_id=on_del" % urllib.request.quote(other)).get("messages") or []
        check("переписки с ним нет", not th, th)
        mf = call("/api/agent/map-feed?view=offline&limit=200").get("items") or []
        check("его интента нет на карте", not any("кофе" == str(i.get("title")) for i in mf),
              [i.get("title") for i in mf][:5])
        check("фото стёрто", not os.path.exists(os.path.join(tmp, "photos", "on_del.jpg")))
        check("файл его голосового стёрт", not os.path.exists(os.path.join(voice_dir, vname)))

        print("\n-- завершить группу --")
        org, m1, m2, late = ("ПрГлава%d" % stamp, "ПрПервый%d" % stamp, "ПрВторой%d" % stamp,
                             "ПрПоздний%d" % stamp)
        g3 = (call("/api/agent/gintent-create", {"self": org, "title": "Шахматы",
                                                 "intent": {"topics": ["chess"]}}).get("group") or {}).get("gid")
        for x in call("/api/agent/gintent-invite", {"gid": g3, "self": org, "to": [m1, m2]}).get("sent") or []:
            call("/api/agent/ginvite-respond", {"id": x["id"], "self": x["to"], "accept": True})
        call("/api/agent/gintent-invite", {"gid": g3, "self": org, "to": late})
        own = call("/api/agent/gintent?gid=%s&self=%s" % (g3, urllib.request.quote(org))).get("group") or {}
        check("организатору видна кнопка «Завершить», пока плана нет", own.get("can_end") is True, own.get("can_end"))
        nope = call("/api/agent/gintent-close", {"gid": g3, "self": m1})
        check("закрыть может только организатор", nope.get("error") == "NOT_ORGANIZER", nope)
        cl = call("/api/agent/gintent-close", {"gid": g3, "self": org})
        check("организатор закрыл группу",
              cl.get("ok") is True and (cl.get("group") or {}).get("state") == "closed_by_owner", cl)
        arch = call("/api/agent/gintent-thread?gid=%s&self=%s" % (g3, urllib.request.quote(m1)))
        check("участнику осталась история только для чтения",
              arch.get("ok") is True and (arch.get("group") or {}).get("read_only_reason") == "group_closed", arch)
        post = call("/api/agent/gintent-post", {"gid": g3, "self": m1, "text": "ау"})
        check("в закрытую группу не пишут", post.get("ok") is False, post)
        gi = call("/api/agent/gintents?self=%s" % urllib.request.quote(late))
        check("приглашение позднего погасло", not (gi.get("invites") or []), gi.get("invites"))
        th = call("/api/agent/thread?self=%s&with=%s" % (urllib.request.quote(late), urllib.request.quote(org))).get("messages") or []
        check("позднему объяснили, почему", any((m.get("sys") or {}).get("code") == "group_closed_invite" for m in th),
              [(m.get("sys") or {}).get("code") for m in th])
        again = call("/api/agent/gintent-close", {"gid": g3, "self": org})
        check("повторное закрытие — вежливый отказ", again.get("error") == "ALREADY_CLOSED", again)
        g5 = (call("/api/agent/gintent-create", {"self": org, "title": "Йога",
                                                 "intent": {"topics": ["yoga"]}}).get("group") or {}).get("gid")
        for x in call("/api/agent/gintent-invite", {"gid": g5, "self": org, "to": [m1, m2]}).get("sent") or []:
            call("/api/agent/ginvite-respond", {"id": x["id"], "self": x["to"], "accept": True})
        call("/api/agent/gplan-begin", {"gid": g5, "self": org, "when": "ср 09:00",
                                        "starts_at": time.time() + 3 * 86400})
        withplan = call("/api/agent/gintent-close", {"gid": g5, "self": org})
        check("при плане группу не закрыть — только голосованием", withplan.get("error") == "PLAN_EXISTS", withplan)

        print("\n-- пожаловаться на группу --")
        g4 = (call("/api/agent/gintent-create", {"self": org, "title": "Бар",
                                                 "intent": {"topics": ["bars"]}}).get("group") or {}).get("gid")
        iv4 = call("/api/agent/gintent-invite", {"gid": g4, "self": org, "to": "Жалобин", "to_id": "on_rep"})
        call("/api/agent/ginvite-respond", {"id": (iv4.get("invite") or {}).get("id"), "accept": True}, token=tok_rep)
        boundary = "kleal%d" % stamp
        blob = b"%PDF-1.4 evidence"
        mp = ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"screen.pdf\"\r\n"
              "Content-Type: application/pdf\r\n\r\n" % boundary).encode() + blob + ("\r\n--%s--\r\n" % boundary).encode()
        req = urllib.request.Request(base + "/api/agent/report-evidence", data=mp, method="POST",
                                     headers={"Content-Type": "multipart/form-data; boundary=%s" % boundary,
                                              "Authorization": "Bearer " + tok_rep})
        up = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
        check("файл к жалобе принят", up.get("ok") is True and up.get("id") and up.get("url"), up)
        rp = call("/api/agent/gintent-report", {"gid": g4, "reason": "harassment_or_threats",
                                                "text": "угрожал в чате", "evidence": [up]}, token=tok_rep)
        check("жалоба принята, есть номер дела", rp.get("ok") is True and str(rp.get("case_no", "")).startswith("KLEAL-"), rp)
        after = call("/api/agent/gintent?gid=%s&self=%s" % (g4, urllib.request.quote(org))).get("group") or {}
        check("пожаловавшийся вышел из группы", "Жалобин" not in [m.get("name") for m in after.get("members") or []],
              after.get("members"))
        bad_r = call("/api/agent/gintent-report", {"gid": g4, "reason": "whatever"}, token=tok_rep)
        check("причина только из списка", bad_r.get("error") == "INVALID_REASON", bad_r)
        stranger = call("/api/agent/gintent-report", {"gid": g4, "self": "ПрЧужак%d" % stamp,
                                                      "reason": "fake_profile"})
        check("посторонний на группу не жалуется", stranger.get("error") == "NOT_A_MEMBER", stranger)
        q = call("/api/agent/admin/reports")
        row = next((r for r in q.get("reports") or [] if r.get("id") == rp.get("id")), {})
        check("жалоба в очереди модератора", row.get("kind") == "group" and row.get("group_title") == "Бар", row)
        check("и с файлом", [e.get("id") for e in row.get("evidence") or []] == [up.get("id")], row.get("evidence"))
        got = urllib.request.urlopen(base + "/api/agent/admin/evidence/" + up["id"], timeout=30).read()
        check("модератор открывает файл", got == blob, len(got))
    finally:
        for proc in (srv, onb):
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()
    print("\nитог: %d ok, %d FAIL" % (ok, bad))
    if bad:
        print("журнал сервиса: %s" % os.path.join(tmp, "server.log"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
