# -*- coding: utf-8 -*-
"""1:1 meeting plans — the server half of the «1:1 Offline» board (OF.20–OF.25, OF.C3–OF.C5).

    python3 tools/mplan_smoke.py [http://127.0.0.1:7074]

Before this existed the whole meeting lived in a client-side variable, so «Marta will get a
notification», «only your companion sees your status» and «confirm and the address opens» were copy
over an empty wire. These checks are written against the two rules the board actually states:

  1. The exact address is released by the VIEWER'S OWN confirmation — «that works both ways» (OF.C3).
  2. Suggesting another time is a counter: it replaces the terms and BOTH sides confirm again, so a
     yes to Tuesday cannot silently become a yes to Thursday.

The awkward cases are the point. A plan to someone who never accepted an invitation, an address that
must not vanish from the person who typed it, a stale version, a status broadcast about a meeting
nobody agreed to.
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
HOST = "MpHost%d" % S
GUEST = "MpGuest%d" % S
OTHER = "MpOther%d" % S
HOUR = 3600.0


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
    print(("  ok   " if cond else "  FAIL ") + name + (("   " + str(detail)[:140]) if detail else ""))


def match(a, b, tag):
    """Make the two accept each other, which is the gate every plan sits behind."""
    r = call("/api/agent/propose", {"from": a, "to": b, "intent": {"topics": ["coffee"]},
                                    "note": "hi", "idem": "pr%s%d" % (tag, S)})
    rid = r.get("id")
    call("/api/agent/respond", {"id": rid, "decision": "accept", "self": b})
    return rid


def plan(host, guest, tag, **kw):
    body = {"self": host, "to": guest, "title": "Coffee & AI talk", "mode": "offline",
            "starts_at": time.time() + 48 * HOUR, "district": "Gracia",
            "address": "Carrer Verdi 12", "idem": "mp%s%d" % (tag, S)}
    body.update(kw)
    return call("/api/agent/mplan-propose", body)


def get(who, pid):
    from urllib.parse import quote
    return call("/api/agent/mplan?self=%s&id=%s" % (quote(who), quote(pid)))


print("=" * 76)
print("1:1 MEETING PLANS  ->  %s" % BASE)
print("=" * 76)

# ---------------------------------------------------------------- the gate: only a matched pair
print("\n-- the address gate starts at the invitation --")
nm = plan(HOST, GUEST, "nomatch")
check("plan to someone who never accepted -> NOT_MATCHED", nm.get("error") == "NOT_MATCHED", nm)

match(HOST, GUEST, "a")
p = plan(HOST, GUEST, "a")
PID = ((p or {}).get("plan") or {}).get("id")
check("plan to a matched pair is created", p.get("ok") and PID, p)
check("the sender is confirmed by proposing", ((p.get("plan") or {}).get("my_response")) == "confirmed")
check("state is proposed until the other side answers", (p.get("plan") or {}).get("state") == "proposed")

# ---------------------------------------------------------------- OF.C3, the whole point of the screen
print("\n-- «confirm and the exact address opens for you» --")
g = get(GUEST, PID)
gp = g.get("plan") or {}
check("guest sees the district", gp.get("district") == "Gracia", gp.get("district"))
check("guest does NOT see the address before confirming", gp.get("address") == "", gp.get("address"))
check("guest is told an address exists", gp.get("address_set") is True)
check("address_visible_to_me is false for the guest", gp.get("address_visible_to_me") is False)
check("guest's own status reads pending", gp.get("my_response") is None, gp.get("my_response"))

h = (get(HOST, PID).get("plan") or {})
check("host sees the address they typed", h.get("address") == "Carrer Verdi 12", h.get("address"))

out = call("/api/agent/mplan-respond", {"id": PID, "self": GUEST, "action": "confirm"})
check("guest confirms", out.get("ok"), out)
check("plan becomes confirmed", (out.get("plan") or {}).get("state") == "confirmed")
check("both sides counted", (out.get("plan") or {}).get("both_confirmed") is True)
g2 = (get(GUEST, PID).get("plan") or {})
check("address opens for the guest after confirming", g2.get("address") == "Carrer Verdi 12", g2.get("address"))

# ---------------------------------------------------------------- who may touch it
print("\n-- only the two of them --")
o = call("/api/agent/mplan-respond", {"id": PID, "self": OTHER, "action": "confirm"})
check("a stranger cannot answer the plan", o.get("error") == "NOT_A_PARTICIPANT", o)
oo = get(OTHER, PID)
check("a stranger cannot read the plan", oo.get("error") == "NOT_A_PARTICIPANT", oo)
dup = plan(HOST, GUEST, "dup")
check("one live plan per pair", dup.get("error") == "PLAN_EXISTS", dup)

# ---------------------------------------------------------------- OF.21a / OF.21b / OF.C5
# «The current time stays until she does — nothing is cancelled.»  «The old time holds until you
# answer, so there is no rush and nothing is lost if you say no.»  A counter must NOT move the meeting.
print("\n-- OF.21b «until then the old time still stands — nothing is cancelled» --")
OLD = (get(HOST, PID).get("plan") or {}).get("starts_at")
NEW = time.time() + 72 * HOUR
c = call("/api/agent/mplan-respond", {"id": PID, "self": GUEST, "action": "counter",
                                      "starts_at": NEW})
cp = c.get("plan") or {}
check("counter accepted", c.get("ok"), c)
check("the meeting does NOT move yet", abs(float(cp.get("starts_at") or 0) - float(OLD)) < 2,
      (cp.get("starts_at"), OLD))
check("the plan stays confirmed — nothing is cancelled", cp.get("state") == "confirmed", cp.get("state"))
check("nobody's confirmation is torn up", cp.get("both_confirmed") is True)
check("the suggested time is parked beside it",
      abs(float((cp.get("pending") or {}).get("starts_at") or 0) - NEW) < 2, cp.get("pending"))
check("the proposer knows it is theirs", (cp.get("pending") or {}).get("mine") is True)
hp = (get(HOST, PID).get("plan") or {})
check("the other side sees the suggestion as not theirs", (hp.get("pending") or {}).get("mine") is False)
check("and their own confirmation is untouched", hp.get("my_response") == "confirmed")
check("the address stays visible to whoever typed it", hp.get("address") == "Carrer Verdi 12", hp.get("address"))

own = call("/api/agent/mplan-respond", {"id": PID, "self": GUEST, "action": "accept_change"})
check("you cannot accept your own suggestion", own.get("error") == "YOUR_OWN_CHANGE", own)
# Taking it back is a different act: without it a suggestion sits on the other person's screen
# until they answer something you no longer mean.
wd = call("/api/agent/mplan-respond", {"id": PID, "self": GUEST, "action": "reject_change"})
check("but you can withdraw it", (wd.get("plan") or {}).get("pending") is None, wd)
check("and withdrawing changes nothing else", (wd.get("plan") or {}).get("state") == "confirmed")
call("/api/agent/mplan-respond", {"id": PID, "self": GUEST, "action": "counter", "starts_at": NEW})
nt = call("/api/agent/mplan-respond", {"id": PID, "self": GUEST, "action": "counter"})
check("a counter without a new time is refused", nt.get("error") == "NO_NEW_TIME", nt)

rej = call("/api/agent/mplan-respond", {"id": PID, "self": HOST, "action": "reject_change"})
rp = rej.get("plan") or {}
check("saying no to a new time loses nothing", rp.get("state") == "confirmed", rp.get("state"))
check("the original time survives", abs(float(rp.get("starts_at") or 0) - float(OLD)) < 2)
check("the suggestion is gone", rp.get("pending") is None)
none = call("/api/agent/mplan-respond", {"id": PID, "self": HOST, "action": "accept_change"})
check("nothing to accept once it is rejected", none.get("error") == "NO_PENDING_CHANGE", none)

call("/api/agent/mplan-respond", {"id": PID, "self": GUEST, "action": "counter", "starts_at": NEW})
acc = call("/api/agent/mplan-respond", {"id": PID, "self": HOST, "action": "accept_change"})
ap = acc.get("plan") or {}
check("accepting moves the meeting", abs(float(ap.get("starts_at") or 0) - NEW) < 2, ap.get("starts_at"))
check("version bumps only when it actually changes", int(ap.get("version") or 0) == 2, ap.get("version"))
check("both are confirmed on the new hour", ap.get("both_confirmed") is True)
check("plan is confirmed", ap.get("state") == "confirmed")

stale = call("/api/agent/mplan-respond", {"id": PID, "self": HOST, "action": "confirm", "version": 1})
check("a stale version is refused", stale.get("error") == "VERSION_CONFLICT", stale)

# ---------------------------------------------------------------- OF.22 / OF.22a / OF.23
print("\n-- «only your companion sees your status» now actually leaves the device --")
bad = call("/api/agent/mplan-status", {"id": PID, "self": HOST, "status": "teleporting"})
check("an unknown status is refused", bad.get("error") == "BAD_STATUS", bad)
lt = call("/api/agent/mplan-status", {"id": PID, "self": HOST, "status": "late", "eta_min": 15})
check("running late is recorded", lt.get("ok"), lt)
gv = (get(GUEST, PID).get("plan") or {})
check("the other side sees it", (gv.get("their_live") or {}).get("status") == "late", gv.get("their_live"))
check("and how long", (gv.get("their_live") or {}).get("eta_min") == 15)
check("your own status is separate", gv.get("my_live") is None, gv.get("my_live"))
cl = call("/api/agent/mplan-status", {"id": PID, "self": HOST, "status": "late", "eta_min": 9999})
check("an absurd delay is clamped, not stored", ((cl.get("plan") or {}).get("my_live") or {}).get("eta_min") == 180,
      (cl.get("plan") or {}).get("my_live"))
call("/api/agent/mplan-status", {"id": PID, "self": HOST, "status": "here"})
check("arrival overwrites the delay",
      ((get(GUEST, PID).get("plan") or {}).get("their_live") or {}).get("status") == "here")

# ---------------------------------------------------------------- OF.24 -> OF.25
print("\n-- OF.24 «Did it happen» then OF.25 feedback, one record --")
f1 = call("/api/agent/mplan-feedback", {"id": PID, "self": HOST, "happened": True})
check("it happened is recorded", (f1.get("plan") or {}).get("outcome", {}).get("happened") is True, f1)
f2 = call("/api/agent/mplan-feedback", {"id": PID, "self": HOST, "rating": 5, "text": "good"})
mf = (f2.get("plan") or {}).get("my_feedback") or {}
check("rating merges into the same record", mf.get("rating") == 5, mf)
check("and does NOT erase the answer to whether it happened", mf.get("happened") is True, mf)
f3 = call("/api/agent/mplan-feedback", {"id": PID, "self": HOST, "rating": 99})
check("an out-of-range rating is clamped",
      ((f3.get("plan") or {}).get("my_feedback") or {}).get("rating") == 5, f3)
f4 = call("/api/agent/mplan-feedback", {"id": PID, "self": GUEST, "happened": True, "rating": 4})
check("both answered -> the plan is done", (f4.get("plan") or {}).get("state") == "done", f4)

lst = call("/api/agent/mplans?self=" + HOST)
check("a finished plan moves to history",
      any(x.get("id") == PID for x in (lst.get("history") or [])), lst)
check("and is no longer active", not any(x.get("id") == PID for x in (lst.get("plans") or [])))

# ---------------------------------------------------------------- OF.24a: it did not happen
print("\n-- OF.24a «Didn't happen» with a reason ends it for both --")
H2, G2 = HOST + "b", GUEST + "b"
match(H2, G2, "b")
p2 = plan(H2, G2, "b")
PID2 = ((p2.get("plan") or {})).get("id")
early = call("/api/agent/mplan-feedback", {"id": PID2, "self": H2, "happened": True})
check("no feedback before both sides agreed to come", early.get("error") == "NOT_YET", early)
call("/api/agent/mplan-respond", {"id": PID2, "self": G2, "action": "confirm"})
nh = call("/api/agent/mplan-feedback", {"id": PID2, "self": G2, "happened": False,
                                        "reason": "he never showed up"})
np = nh.get("plan") or {}
check("didn't happen is recorded", (np.get("outcome") or {}).get("happened") is False, np.get("outcome"))
check("the reason is kept", (np.get("outcome") or {}).get("reason") == "he never showed up")
check("one side saying no closes it without waiting for the other", np.get("state") == "done", np.get("state"))

# ---------------------------------------------------------------- times that make no sense
print("\n-- a first coffee is not scheduled for the year 31 billion --")
H3, G3 = HOST + "c", GUEST + "c"
match(H3, G3, "c")
past = plan(H3, G3, "past", starts_at=time.time() - HOUR)
check("a plan in the past is refused", past.get("error") == "IN_THE_PAST", past)
far = plan(H3, G3, "far", starts_at=1e18)
check("a plan 31 billion years out is refused", far.get("error") == "TOO_FAR_AHEAD", far)
good = plan(H3, G3, "c")
PID3 = (good.get("plan") or {}).get("id")
check("a sane time is accepted", good.get("ok"), good)

# ---------------------------------------------------------------- status only after both agree
print("\n-- you cannot be on your way to a meeting nobody agreed to --")
ns = call("/api/agent/mplan-status", {"id": PID3, "self": H3, "status": "otw"})
check("status before confirmation -> NOT_CONFIRMED", ns.get("error") == "NOT_CONFIRMED", ns)

# ---------------------------------------------------------------- cancel + idempotency
print("\n-- cancelling, and doing everything twice --")
cn = call("/api/agent/mplan-cancel", {"id": PID3, "self": G3, "reason": "something came up"})
check("either side can cancel", cn.get("ok"), cn)
check("a cancelled plan is cancelled", (cn.get("plan") or {}).get("state") == "cancelled")
again = call("/api/agent/mplan-respond", {"id": PID3, "self": H3, "action": "confirm"})
check("a cancelled plan cannot be confirmed", again.get("error") == "NOT_OPEN", again)
after = plan(H3, G3, "c2")
check("the pair can make a new plan after a cancellation", after.get("ok"), after)

H4, G4 = HOST + "d", GUEST + "d"
match(H4, G4, "d")
k = "idem%d" % S
i1 = call("/api/agent/mplan-propose", {"self": H4, "to": G4, "title": "X",
                                       "starts_at": time.time() + 30 * HOUR, "idem": k})
i2 = call("/api/agent/mplan-propose", {"self": H4, "to": G4, "title": "X",
                                       "starts_at": time.time() + 30 * HOUR, "idem": k})
check("the same idempotency key gives the same plan",
      (i1.get("plan") or {}).get("id") == (i2.get("plan") or {}).get("id"), (i1, i2))
lst4 = call("/api/agent/mplans?self=" + H4)
check("and only one plan exists for the pair",
      len([x for x in (lst4.get("plans") or []) if x.get("state") == "proposed"]) == 1, lst4)

# ---------------------------------------------------------------- OF.20a
# «Thursday 19:00 in Gràcia is agreed. Marta only sees the district until you name a place.»
# Filling in WHERE exactly must not un-agree WHEN.
print("\n-- OF.20a: naming the place does not un-agree the time --")
H5, G5 = HOST + "e", GUEST + "e"
match(H5, G5, "e")
p5 = plan(H5, G5, "e", address="")
PID5 = (p5.get("plan") or {}).get("id")
check("a plan without an exact address is allowed", p5.get("ok"), p5)
check("address_set is false", (p5.get("plan") or {}).get("address_set") is False)
call("/api/agent/mplan-respond", {"id": PID5, "self": G5, "action": "confirm"})
g5 = (get(G5, PID5).get("plan") or {})
check("confirming does not invent an address", g5.get("address") == "" and g5.get("address_set") is False, g5)
upd = call("/api/agent/mplan-address", {"id": PID5, "self": H5,
                                        "address": "Carrer Nou 3", "venue": "Nomad"})
up = upd.get("plan") or {}
check("the host can name the place later", up.get("address_set") is True, upd)
check("the venue is stored", up.get("venue") == "Nomad", up.get("venue"))
check("the agreed time is untouched", up.get("state") == "confirmed" and up.get("both_confirmed") is True, up)
check("no version churn", int(up.get("version") or 0) == 1, up.get("version"))
g5b = (get(G5, PID5).get("plan") or {})
check("the guest, who already confirmed, sees it at once",
      g5b.get("address") == "Carrer Nou 3", g5b.get("address"))
check("and did not have to confirm again", g5b.get("my_response") == "confirmed", g5b.get("my_response"))
str5 = call("/api/agent/mplan-address", {"id": PID5, "self": OTHER, "address": "x"})
check("a stranger cannot set the address", str5.get("error") == "NOT_A_PARTICIPANT", str5)

# A guest who has NOT confirmed must still be kept out of an address someone adds later.
H6, G6 = HOST + "f", GUEST + "f"
match(H6, G6, "f")
p6 = plan(H6, G6, "f", address="")
PID6 = (p6.get("plan") or {}).get("id")
call("/api/agent/mplan-address", {"id": PID6, "self": H6, "address": "Carrer Secret 9"})
g6 = (get(G6, PID6).get("plan") or {})
check("an unconfirmed guest still sees no address", g6.get("address") == "", g6.get("address"))
check("but is told there is one now", g6.get("address_set") is True)

# ---------------------------------------------------------------- часовой пояс собеседника
#
# Спека: «Таймзона в UI — только при РАСХОЖДЕНИИ». Считать расхождение было НЕ С ЧЕМ: свой пояс
# устройство знает, чужой не хранился нигде, и экраны безусловно печатали своё же смещение
# «(GMT+2)». Проверяется весь путь целиком — от анкеты до плана, — потому что пустой пояс
# выглядит РОВНО как работающее правило: строка просто не появляется, и молчание не отличить.
print("\n-- часовой пояс собеседника")
HT, GT = "MpTzHost%d" % S, "MpTzGuest%d" % S
for nm, tz, city in ((HT, "Europe/Madrid", "Barcelona"), (GT, "Europe/London", "London")):
    call("/api/onboarding/register", {"profile": {
        "name": nm, "age": 30, "city": city, "tz": tz,
        "interests": {"explicit": ["coffee"]}, "languages": {"comfortable": ["en"]}}})

u = (call("/api/onboarding/profile", {"name": GT}).get("user") or {})
# register заменяет строку целиком, поэтому пояс обязан ехать и через неё, а не только патчем —
# иначе повторный онбординг стирал бы его молча, как когда-то стирал story.
check("register сохраняет пояс", u.get("tz") == "Europe/London", u.get("tz"))
call("/api/onboarding/profile-update", {"name": GT, "patch": {"tz": "Asia/Tokyo"}})
check("пояс правится патчем",
      (call("/api/onboarding/profile", {"name": GT}).get("user") or {}).get("tz") == "Asia/Tokyo")
call("/api/onboarding/profile-update", {"name": GT, "patch": {"tz": "Europe/London"}})

match(HT, GT, "tz")
PT = (plan(HT, GT, "tz").get("plan") or {}).get("id")
check("план между ними создан", bool(PT))

from urllib.parse import quote as _q
lst = call("/api/agent/mplans?self=%s&with=%s" % (_q(HT), _q(GT)))
check("список отдаёт пояс собеседника", lst.get("peer_tz") == "Europe/London", lst.get("peer_tz"))
plt = next((x for x in lst.get("plans") or [] if x.get("id") == PT), None) or {}
check("в самом плане есть their_tz", plt.get("their_tz") == "Europe/London", plt.get("their_tz"))
byname = {x.get("name"): x.get("tz") for x in plt.get("participants") or []}
check("у каждого участника свой пояс",
      byname.get(HT) == "Europe/Madrid" and byname.get(GT) == "Europe/London", byname)

# Главное, что тут может сломаться незаметно: пояс, посчитанный от ХОЗЯИНА вместо смотрящего.
# Тогда каждый видел бы собственный час «чужим» — и это выглядело бы правдоподобно.
his = call("/api/agent/mplans?self=%s&with=%s" % (_q(GT), _q(HT)))
hpl = next((x for x in his.get("plans") or [] if x.get("id") == PT), None) or {}
check("гость видит пояс ХОЗЯИНА, а не свой", hpl.get("their_tz") == "Europe/Madrid", hpl.get("their_tz"))

# 608 человек зарегистрировались до того, как пояс вообще появился. Для них ответ обязан быть
# пустой строкой, а не ошибкой и не чужим поясом.
unk = call("/api/agent/mplans?self=%s&with=%s" % (_q(HT), _q("НетТакогоЧеловека%d" % S)))
check("неизвестный человек -> пустой пояс, а не ошибка",
      unk.get("ok") and unk.get("peer_tz") == "", unk.get("peer_tz"))
check("без параметра with поля нет вовсе",
      "peer_tz" not in call("/api/agent/mplans?self=%s" % _q(HT)))

print("\n" + "=" * 76)
print("РЕЗУЛЬТАТ: %d ok, %d проблем" % (R["ok"], R["fail"]))
if FAILED:
    for f in FAILED:
        print("  - " + f)
print("=" * 76)
sys.exit(1 if R["fail"] else 0)
