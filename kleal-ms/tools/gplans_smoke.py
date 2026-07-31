# -*- coding: utf-8 -*-
"""Group plans, layer 2: confirmation, counter-proposals, votes, the two-hour lock, feedback.

    python3 tools/gplans_smoke.py [http://127.0.0.1:7074]

Written against the daily, whose two decided points are the ones most easily got wrong: THREE
confirmations are enough (not everyone), and a vote is a majority OF THOSE WHO VOTED (so a tie
leaves the plan alone). Both are asserted here with the awkward cases, not the flattering ones.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7074").rstrip("/")
R = {"ok": 0, "fail": 0}
FAILED = []
S = int(time.time() * 1000) % 100000000 + os.getpid()
OWN = "GpOwner%d" % S
M = ["GpM%d_%d" % (S, i) for i in range(5)]


def call(path, body=None, timeout=120):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return {"_http": e.code, "_body": e.read().decode("utf-8", "replace")[:200]}
    except Exception as e:
        return {"_err": "%s: %s" % (type(e).__name__, str(e)[:140])}


def check(name, cond, detail=""):
    R["ok" if cond else "fail"] += 1
    if not cond:
        FAILED.append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (("   " + str(detail)[:120]) if detail else ""))


def group(n_members, max_total=6, tag=""):
    """A group intent with n_members people in the chat besides the organiser."""
    c = call("/api/agent/gintent-create", {"self": OWN, "title": "План " + tag,
                                           "intent": {"topics": ["coffee"]},
                                           "max_total": max_total, "idem": "c%s%d" % (tag, S)})
    gid = ((c or {}).get("group") or {}).get("gid")
    who = M[:n_members]
    b = call("/api/agent/gintent-invite", {"gid": gid, "self": OWN, "to": who,
                                           "idem": "i%s%d" % (tag, S)})
    for x in (b.get("sent") or []):
        call("/api/agent/ginvite-respond", {"id": x["id"], "self": x["to"], "accept": True})
    return gid, who


print("=" * 76)
print("1. «СОЗДАТЬ ПЛАН» ДОСТУПЕН ТОЛЬКО ПРИ ТРЁХ")
print("=" * 76)
g2, w2 = group(1, tag="a")                       # организатор + один = двое
early = call("/api/agent/gplan-begin", {"gid": g2, "self": OWN, "when": "сб 19:00"})
check("при двоих план создать нельзя", early.get("error") == "NEED_THREE", early)

gid, who = group(3, tag="b")                     # организатор + трое = четверо
st = call("/api/agent/gintent?gid=%s&self=%s" % (gid, OWN))
check("в чате четверо", ((st.get("group") or {}).get("joined_count")) == 4,
      (st.get("group") or {}).get("joined_count"))
notown = call("/api/agent/gplan-begin", {"gid": gid, "self": who[0], "when": "сб 19:00"})
check("план начинает только создатель", notown.get("error") == "NOT_ORGANIZER", notown)

START = time.time() + 24 * 3600
p = call("/api/agent/gplan-begin", {"gid": gid, "self": OWN, "when": "сб 19:00",
                                    "place": "Nomad Coffee", "starts_at": START,
                                    "idem": "pb%d" % S})
PID = ((p or {}).get("plan") or {}).get("id")
pl = (p or {}).get("plan") or {}
check("план предложен всему составу", bool(PID), p)
check("предложивший считается подтвердившим", pl.get("confirmed_count") == 1, pl.get("confirmed"))
check("нужно ещё двое", pl.get("needs") == 2, pl.get("needs"))
dup = call("/api/agent/gplan-begin", {"gid": gid, "self": OWN, "when": "вс"})
check("второй план на тот же интент не создать", dup.get("error") == "PLAN_EXISTS", dup)

print()
print("=" * 76)
print("2. ВСТРЕЧНОЕ ПРЕДЛОЖЕНИЕ ОБНУЛЯЕТ УТВЕРЖДЕНИЕ")
print("=" * 76)
call("/api/agent/gplan-respond", {"id": PID, "self": who[0], "action": "confirm"})
mid = call("/api/agent/gplan-respond", {"id": PID, "self": who[1], "action": "counter",
                                        "when": "сб 20:00"})
pl = (mid or {}).get("plan") or {}
check("встречное предложение принято", mid.get("countered") is True, mid.get("error"))
check("время заменено", pl.get("when") == "сб 20:00", pl.get("when"))
check("версия выросла", pl.get("version") == 2, pl.get("version"))
check("прежние подтверждения обнулены — согласие было на другой вечер",
      pl.get("confirmed_count") == 1 and pl.get("confirmed") == [who[1]], pl.get("confirmed"))
check("план снова на утверждении", pl.get("state") == "proposed", pl.get("state"))

print()
print("=" * 76)
print("3. ТРЁХ ПОДТВЕРЖДЕНИЙ ДОСТАТОЧНО — МОЛЧАЩИЕ НЕ ДЕРЖАТ")
print("=" * 76)
r1 = call("/api/agent/gplan-respond", {"id": PID, "self": OWN, "action": "confirm"})
check("после двух подтверждений план ещё не создан",
      ((r1.get("plan") or {}).get("state")) == "proposed", (r1.get("plan") or {}).get("state"))
r2 = call("/api/agent/gplan-respond", {"id": PID, "self": who[0], "action": "confirm",
                                       "idem": "pc%d" % S})
pl = (r2 or {}).get("plan") or {}
check("на третьем подтверждении план создан", pl.get("state") == "confirmed", pl.get("state"))
check("состав плана — те, кто подтвердил", sorted(pl.get("confirmed") or []) == sorted([OWN, who[0], who[1]]),
      pl.get("confirmed"))
check("четвёртый молчал и в план не попал", who[2] not in (pl.get("confirmed") or []), pl.get("confirmed"))
outsider = call("/api/agent/gplan-respond", {"id": PID, "self": "Посторонний%d" % S,
                                             "action": "confirm"})
check("посторонний план не подтверждает", outsider.get("error") == "NOT_A_MEMBER", outsider)

print()
print("=" * 76)
print("4. ГОЛОСОВАНИЕ: БОЛЬШИНСТВО ОТ ПРОГОЛОСОВАВШИХ, НИЧЬЯ — ПЛАН СТОИТ")
print("=" * 76)
v = call("/api/agent/gplan-vote-open", {"id": PID, "self": who[0], "kind": "cancel",
                                        "idem": "vo%d" % S})
VID = ((v or {}).get("vote") or {}).get("id")
check("голосование открыто", bool(VID), v)
check("созвавший уже проголосовал за", ((v.get("vote") or {}).get("yes")) == 1, v.get("vote"))
second = call("/api/agent/gplan-vote-open", {"id": PID, "self": OWN, "kind": "edit"})
check("второе голосование одновременно нельзя", second.get("error") == "VOTE_IN_PROGRESS", second)
call("/api/agent/gplan-vote", {"id": VID, "self": OWN, "yes": False})
res = call("/api/agent/gplan-vote", {"id": VID, "self": who[1], "yes": False})
vv = (res or {}).get("vote") or {}
check("голоса посчитаны", (vv.get("yes"), vv.get("no")) == (1, 2), [vv.get("yes"), vv.get("no")])
call("/api/agent/gplan-vote", {"id": VID, "self": who[2], "yes": True})
st = call("/api/agent/gplans?self=%s" % OWN)
plan_now = next((x for x in (st.get("plans") or []) if x.get("id") == PID), None)
check("при 2:2 план НЕ отменён — ничья не большинство",
      bool(plan_now) and plan_now.get("state") == "confirmed",
      plan_now and plan_now.get("state"))

print()
print("=" * 76)
print("5. ГОЛОСОВАНИЕ ЗА ПЕРЕНОС ПРОХОДИТ")
print("=" * 76)
v2 = call("/api/agent/gplan-vote-open", {"id": PID, "self": OWN, "kind": "edit",
                                         "when": "вс 12:00", "place": "Парк"})
V2 = ((v2 or {}).get("vote") or {}).get("id")
for n in (who[0], who[1]):
    call("/api/agent/gplan-vote", {"id": V2, "self": n, "yes": True})
last = call("/api/agent/gplan-vote", {"id": V2, "self": who[2], "yes": False})
check("голосование закрылось, когда высказались все",
      ((last.get("vote") or {}).get("state")) == "passed", (last.get("vote") or {}).get("state"))
st = call("/api/agent/gplans?self=%s" % OWN)
plan_now = next((x for x in (st.get("plans") or []) if x.get("id") == PID), None)
check("время перенесено", plan_now and plan_now.get("when") == "вс 12:00", plan_now and plan_now.get("when"))
check("план остался подтверждённым — перенос не отправляет на новый круг",
      plan_now and plan_now.get("state") == "confirmed", plan_now and plan_now.get("state"))
check("проголосовавшие против в составе не остались",
      who[2] not in (plan_now.get("confirmed") or []), plan_now.get("confirmed"))

print()
print("=" * 76)
print("6. ДВА ЧАСА ДО ВСТРЕЧИ — ВСЁ ЗАМИРАЕТ")
print("=" * 76)
gid2, who2 = group(3, tag="c")
soon = time.time() + 3600                      # через час: уже внутри двухчасового окна
too_late = call("/api/agent/gplan-begin", {"gid": gid2, "self": OWN, "when": "через час",
                                           "starts_at": soon, "idem": "pl%d" % S})
check("план внутри окна не заводится — его некому подтвердить",
      too_late.get("error") == "TOO_LATE", too_late)

# Ровно на границе: план начинается через два часа с минутой, трое подтверждают, затем время
# сдвигается голосованием так, что встреча оказывается внутри окна.
p2 = call("/api/agent/gplan-begin", {"gid": gid2, "self": OWN, "when": "сегодня",
                                     "starts_at": time.time() + 2 * 3600 + 600,
                                     "idem": "pb2%d" % S})
P2 = ((p2 or {}).get("plan") or {}).get("id")
check("а за границей окна — заводится", bool(P2), p2)
for n in who2[:2]:
    call("/api/agent/gplan-respond", {"id": P2, "self": n, "action": "confirm"})
st2 = call("/api/agent/gplans?self=%s" % OWN)
pl2 = next((x for x in (st2.get("plans") or []) if x.get("id") == P2), None)
check("план подтверждён тремя", pl2 and pl2.get("state") == "confirmed", pl2 and pl2.get("state"))
# Переносим встречу внутрь окна голосованием — это законный путь, и после него всё замирает.
v3 = call("/api/agent/gplan-vote-open", {"id": P2, "self": OWN, "kind": "edit",
                                         "when": "через час", "starts_at": soon})
V3 = ((v3 or {}).get("vote") or {}).get("id")
for n in who2:
    call("/api/agent/gplan-vote", {"id": V3, "self": n, "yes": True})
late = call("/api/agent/gplan-respond", {"id": P2, "self": who2[2], "action": "confirm"})
check("после переноса внутрь окна подтвердить нельзя", late.get("error") == "LOCKED", late)
vlate = call("/api/agent/gplan-vote-open", {"id": P2, "self": OWN, "kind": "cancel"})
check("и отменить нельзя", vlate.get("error") == "LOCKED", vlate)
inv_late = call("/api/agent/gintent-invite", {"gid": gid2, "self": OWN, "to": M[4]})
check("новых людей больше не зовут", inv_late.get("error") == "LOCKED", inv_late)

print()
print("=" * 76)
print("7. ПОСЛЕ ВСТРЕЧИ — ОБРАТНАЯ СВЯЗЬ И ИСТОРИЯ")
print("=" * 76)
conf = [x for x in (call("/api/agent/gplans?self=%s" % OWN).get("plans") or []) if x.get("id") == PID]
parts = (conf[0].get("confirmed") if conf else []) or []
check("в плане трое", len(parts) == 3, parts)
f1 = call("/api/agent/gplan-feedback", {"id": PID, "self": parts[0], "happened": True,
                                        "text": "хорошо посидели", "idem": "f1%d" % S})
check("первый ответил", f1.get("ok") is True, f1)
check("план ещё не в истории", (f1.get("answered"), f1.get("of")) == (1, 3),
      [f1.get("answered"), f1.get("of")])
nope = call("/api/agent/gplan-feedback", {"id": PID, "self": M[4], "happened": True})
check("не участник фидбэк не оставляет", nope.get("error") == "NOT_A_PARTICIPANT", nope)
for n in parts[1:]:
    last = call("/api/agent/gplan-feedback", {"id": PID, "self": n, "happened": False,
                                              "reason": "дождь"})
check("когда ответили все — план закрыт", ((last.get("plan") or {}).get("state")) == "done",
      (last.get("plan") or {}).get("state"))
hist = call("/api/agent/gplans?self=%s" % parts[0].replace(" ", "+"))
check("и уехал в историю", any(x.get("id") == PID for x in (hist.get("history") or [])),
      [x.get("id") for x in (hist.get("history") or [])])
check("из активных пропал", not any(x.get("id") == PID for x in (hist.get("plans") or [])))

print()
print("=" * 76)
print("РЕЗУЛЬТАТ: %d ok, %d проблем" % (R["ok"], R["fail"]))
for f in FAILED:
    print("   -", f)
sys.exit(1 if R["fail"] else 0)
