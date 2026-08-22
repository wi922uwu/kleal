# -*- coding: utf-8 -*-
"""Adversarial pass over group intents and plans. Run ON the pod, against prod.

Not the happy path — the shapes my own smoke tests are structurally blind to: concurrency, states
reached by an unusual order of events, and people acting after they stopped being members.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request

GW = "http://127.0.0.1:7074"
S = int(time.time() * 1000) % 100000000 + os.getpid()
FOUND, OK = [], [0]


def call(path, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(GW + path, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return {"_http": e.code}
    except Exception as e:
        return {"_err": "%s: %s" % (type(e).__name__, str(e)[:120])}


def ok(n, d=""):
    OK[0] += 1
    print("  ok    %s%s" % (n, ("   " + str(d)[:100]) if d else ""))


def bug(n, d=""):
    FOUND.append((n, str(d)[:300]))
    print("  BUG   %s   %s" % (n, str(d)[:160]))


def mkgroup(tag, n=3, mx=6):
    own = "H%s%d" % (tag, S)
    mem = ["H%s%d_%d" % (tag, S, i) for i in range(n)]
    gid = ((call("/api/agent/gintent-create",
                 {"self": own, "title": tag, "intent": {"topics": ["coffee"]},
                  "max_total": mx}) or {}).get("group") or {}).get("gid")
    b = call("/api/agent/gintent-invite", {"gid": gid, "self": own, "to": mem})
    for x in (b.get("sent") or []):
        call("/api/agent/ginvite-respond", {"id": x["id"], "self": x["to"], "accept": True})
    return own, mem, gid


print("=" * 78)
print("1. ГОНКА ЗА ТРЕТЬЕ ПОДТВЕРЖДЕНИЕ")
print("=" * 78)
own, mem, gid = mkgroup("a", 4)
pid = ((call("/api/agent/gplan-begin", {"gid": gid, "self": own, "when": "сб",
                                        "starts_at": time.time() + 86400}) or {})
       .get("plan") or {}).get("id")
res = []
bar = threading.Barrier(3)


def conf(who):
    bar.wait()
    res.append(call("/api/agent/gplan-respond", {"id": pid, "self": who, "action": "confirm"}))


ts = [threading.Thread(target=conf, args=(m,)) for m in mem[:3]]
[t.start() for t in ts]
[t.join() for t in ts]
st = [(r.get("plan") or {}).get("state") for r in res]
final = call("/api/agent/gplans?self=%s" % own)
p = next((x for x in (final.get("plans") or []) if x.get("id") == pid), None)
if not p:
    bug("план исчез после параллельных подтверждений", final)
elif p.get("state") != "confirmed":
    bug("три подтверждения не создали план", p)
elif len(p.get("confirmed") or []) != 4:
    bug("состав после гонки не сходится", p.get("confirmed"))
else:
    ok("параллельные подтверждения дают один согласованный состав", p.get("confirmed"))

print()
print("=" * 78)
print("2. УШЕДШИЙ И УДАЛЁННЫЙ ПРОДОЛЖАЮТ ДЕЙСТВОВАТЬ?")
print("=" * 78)
own, mem, gid = mkgroup("b", 3)
pid = ((call("/api/agent/gplan-begin", {"gid": gid, "self": own, "when": "сб",
                                        "starts_at": time.time() + 86400}) or {})
       .get("plan") or {}).get("id")
for m in mem[:2]:
    call("/api/agent/gplan-respond", {"id": pid, "self": m, "action": "confirm"})
call("/api/agent/gintent-leave", {"gid": gid, "self": mem[0]})
r = call("/api/agent/gplan-respond", {"id": pid, "self": mem[0], "action": "counter", "when": "пн"})
if r.get("ok"):
    bug("ушедший переписал условия плана", r)
else:
    ok("ушедший не меняет план", r.get("error"))
r = call("/api/agent/gplan-vote-open", {"id": pid, "self": mem[0], "kind": "cancel"})
if r.get("ok"):
    bug("ушедший созвал голосование", r)
else:
    ok("ушедший не созывает голосование", r.get("error"))
r = call("/api/agent/gintent-post", {"gid": gid, "self": mem[0], "text": "я всё ещё тут"})
if r.get("ok"):
    bug("ушедший пишет в чат", r)
else:
    ok("ушедший не пишет в чат", r.get("error"))

# состав плана после ухода подтвердившего
pl = next((x for x in (call("/api/agent/gplans?self=%s" % own).get("plans") or [])
           if x.get("id") == pid), None)
if pl and mem[0] in (pl.get("confirmed") or []):
    bug("ушедший остался в составе подтверждённого плана",
        {"confirmed": pl.get("confirmed"), "state": pl.get("state")})
else:
    ok("состав плана пересчитан после ухода", pl and pl.get("confirmed"))

print()
print("=" * 78)
print("3. СОЗДАТЕЛЬ УХОДИТ — ГРУППА ОСИРОТЕЛА?")
print("=" * 78)
own, mem, gid = mkgroup("c", 3)
r = call("/api/agent/gintent-leave", {"gid": gid, "self": own})
if not r.get("ok"):
    ok("создатель не может просто уйти", r.get("error"))
else:
    inv = call("/api/agent/gintent-invite", {"gid": gid, "self": mem[0], "to": "Кто-то%d" % S})
    beg = call("/api/agent/gplan-begin", {"gid": gid, "self": mem[0], "when": "сб",
                                          "starts_at": time.time() + 86400})
    if not inv.get("ok") and not beg.get("ok"):
        bug("создатель ушёл, и группу больше некому вести",
            {"invite": inv.get("error"), "plan": beg.get("error"),
             "members": len((r.get("group") or {}).get("members") or [])})
    else:
        ok("после ухода создателя группа управляема", [inv.get("ok"), beg.get("ok")])

print()
print("=" * 78)
print("4. ГОЛОСОВАНИЕ: СОСТАВ МЕНЯЕТСЯ ПОСРЕДИ")
print("=" * 78)
own, mem, gid = mkgroup("d", 3)
pid = ((call("/api/agent/gplan-begin", {"gid": gid, "self": own, "when": "сб",
                                        "starts_at": time.time() + 86400}) or {})
       .get("plan") or {}).get("id")
for m in mem:
    call("/api/agent/gplan-respond", {"id": pid, "self": m, "action": "confirm"})
v = call("/api/agent/gplan-vote-open", {"id": pid, "self": own, "kind": "cancel"})
vid = ((v or {}).get("vote") or {}).get("id")
call("/api/agent/gplan-vote", {"id": vid, "self": mem[0], "yes": False})
call("/api/agent/gintent-leave", {"gid": gid, "self": mem[1]})     # ушёл, не проголосовав
r = call("/api/agent/gplan-vote", {"id": vid, "self": mem[2], "yes": False})
vv = (r or {}).get("vote") or {}
if vv.get("state") == "open" and not vv.get("waiting"):
    bug("голосование не закрылось, хотя ждать больше некого", vv)
elif vv.get("state") == "passed":
    bug("голосование прошло при 1 за и 2 против", vv)
else:
    ok("выход посреди голосования обработан", {"state": vv.get("state"),
                                               "yes": vv.get("yes"), "no": vv.get("no")})
r = call("/api/agent/gplan-vote", {"id": vid, "self": mem[1], "yes": True})
if r.get("ok") and (r.get("vote") or {}).get("my_vote") is True:
    bug("ушедший проголосовал", r.get("vote"))
else:
    ok("ушедший не голосует", r.get("error") or (r.get("vote") or {}).get("state"))

print()
print("=" * 78)
print("5. СОСТОЯНИЯ, ДОСТИГНУТЫЕ НЕОБЫЧНЫМ ПОРЯДКОМ")
print("=" * 78)
own, mem, gid = mkgroup("e", 3)
pid = ((call("/api/agent/gplan-begin", {"gid": gid, "self": own, "when": "сб",
                                        "starts_at": time.time() + 86400}) or {})
       .get("plan") or {}).get("id")
for m in mem:
    call("/api/agent/gplan-respond", {"id": pid, "self": m, "action": "confirm"})
r = call("/api/agent/gplan-respond", {"id": pid, "self": mem[0], "action": "counter", "when": "пн"})
if r.get("ok"):
    pl = (r.get("plan") or {})
    bug("встречное предложение развалило уже подтверждённый план",
        {"state": pl.get("state"), "confirmed": pl.get("confirmed")})
else:
    ok("подтверждённый план встречным предложением не переписать", r.get("error"))

v = call("/api/agent/gplan-vote-open", {"id": pid, "self": own, "kind": "cancel"})
vid = ((v or {}).get("vote") or {}).get("id")
for m in mem:
    call("/api/agent/gplan-vote", {"id": vid, "self": m, "yes": True})
after = next((x for x in (call("/api/agent/gplans?self=%s" % own).get("history") or [])
              if x.get("id") == pid), None)
if after and after.get("state") == "cancelled":
    ok("голосование действительно отменило план")
else:
    bug("голосование за отмену план не отменило",
        next((x for x in (call("/api/agent/gplans?self=%s" % own).get("plans") or [])
              if x.get("id") == pid), None))
r = call("/api/agent/gplan-vote-open", {"id": pid, "self": own, "kind": "edit", "when": "вт"})
if r.get("ok"):
    bug("голосование по отменённому плану открылось", r)
else:
    ok("по отменённому плану не голосуют", r.get("error"))
r = call("/api/agent/gplan-feedback", {"id": pid, "self": own, "happened": True})
if r.get("ok"):
    bug("фидбэк по отменённому плану принят", r)
else:
    ok("по отменённому плану фидбэка нет", r.get("error"))
r = call("/api/agent/gplan-begin", {"gid": gid, "self": own, "when": "новый",
                                    "starts_at": time.time() + 86400})
if r.get("ok"):
    ok("после отмены группа может собрать новый план")
else:
    bug("после отмены новый план невозможен — группа заперта", r)

print()
print("=" * 78)
print("5b. ПАДЕНИЕ НИЖЕ КВОРУМА ПОСЛЕ УХОДА")
print("=" * 78)
own, mem, gid = mkgroup("q", 3)
pid = ((call("/api/agent/gplan-begin", {"gid": gid, "self": own, "when": "сб",
                                        "starts_at": time.time() + 86400}) or {})
       .get("plan") or {}).get("id")
for m in mem[:2]:
    call("/api/agent/gplan-respond", {"id": pid, "self": m, "action": "confirm"})
call("/api/agent/gintent-leave", {"gid": gid, "self": mem[0]})
pl = next((x for x in (call("/api/agent/gplans?self=%s" % own).get("plans") or [])
           if x.get("id") == pid), None)
if not pl:
    bug("план пропал из активных после ухода одного", None)
elif pl.get("state") == "confirmed" and len(pl.get("confirmed") or []) < 3:
    bug("план считается подтверждённым, а подтвердивших меньше трёх", pl)
elif pl.get("state") == "below_quorum":
    ok("план честно помечен как упавший ниже кворума", pl.get("confirmed"))
else:
    ok("состав пересчитан", {"state": pl.get("state"), "confirmed": pl.get("confirmed")})

print()
print("=" * 78)
print("6. ВРАЖДЕБНЫЙ ВВОД")
print("=" * 78)
own, mem, gid = mkgroup("f", 3)
CASES = [
    ("starts_at строкой", {"when": "x", "starts_at": "завтра"}, True),
    ("starts_at в прошлом", {"when": "x", "starts_at": time.time() - 99999}, True),
    ("starts_at отрицательный", {"when": "x", "starts_at": -5}, True),
    ("starts_at огромный", {"when": "x", "starts_at": 1e18}, True),
    ("when на 50к символов", {"when": "A" * 50000, "starts_at": time.time() + 86400}, True),
    ("gid не существует", {"gid": "нет-такого", "when": "x"}, False),
    ("self пустой", {"self": "", "when": "x"}, False),
]
for label, extra, fresh in CASES:
    if fresh:                       # своя группа на случай — иначе PLAN_EXISTS съедает проверку
        o, _, g = mkgroup("f%d" % (abs(hash(label)) % 9999), 3)
        body = dict({"gid": g, "self": o}, **extra)
    else:
        body = dict({"gid": gid, "self": own}, **extra)
    r = call("/api/agent/gplan-begin", body)
    if isinstance(r.get("_err"), str) or r.get("_http", 200) >= 500:
        bug("сервис упал на: " + label, r)
    elif label == "when на 50к символов" and r.get("ok"):
        n = len(((r.get("plan") or {}).get("when")) or "")
        (ok if n <= 200 else bug)("длинный текст обрезан: " + label, n)
    else:
        ok(label, r.get("error") or "принято")

r = call("/api/agent/gintent-invite", {"gid": gid, "self": own, "to": ["A%d" % S] * 50})
if isinstance(r.get("_err"), str):
    bug("сервис упал на батче из 50 одинаковых", r)
else:
    sent = len(r.get("sent") or [])
    (ok if sent <= 1 else bug)("батч из 50 одинаковых имён не создал 50 приглашений", sent)

print()
print("=" * 78)
print("7. ЧУЖОЕ ГОЛОСОВАНИЕ И ЧУЖОЙ ПЛАН")
print("=" * 78)
o1, m1, g1 = mkgroup("g", 3)
o2, m2, g2 = mkgroup("h", 3)
p1 = ((call("/api/agent/gplan-begin", {"gid": g1, "self": o1, "when": "сб",
                                       "starts_at": time.time() + 86400}) or {})
      .get("plan") or {}).get("id")
for m in m1:
    call("/api/agent/gplan-respond", {"id": p1, "self": m, "action": "confirm"})
v = call("/api/agent/gplan-vote-open", {"id": p1, "self": o1, "kind": "cancel"})
vid = ((v or {}).get("vote") or {}).get("id")
r = call("/api/agent/gplan-vote", {"id": vid, "self": o2, "yes": True})
if r.get("ok") and (r.get("vote") or {}).get("my_vote") is True:
    bug("посторонний проголосовал в чужой группе", r.get("vote"))
else:
    ok("в чужом голосовании не голосуют", r.get("error"))
r = call("/api/agent/gplan-feedback", {"id": p1, "self": o2, "happened": True})
if r.get("ok"):
    bug("посторонний оставил фидбэк по чужому плану", r)
else:
    ok("чужой фидбэк отклонён", r.get("error"))

print()
print("=" * 78)
print("ИТОГ: %d ok, %d проблем" % (OK[0], len(FOUND)))
for n, d in FOUND:
    print("   - %s\n     %s" % (n, d))
