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

# ---------------------------------------------------------------- OF.21a: suggest another time
print("\n-- OF.21a «Suggest another time» is a counter, not a nudge --")
NEW = time.time() + 72 * HOUR
c = call("/api/agent/mplan-respond", {"id": PID, "self": GUEST, "action": "counter",
                                      "starts_at": NEW})
cp = c.get("plan") or {}
check("counter accepted", c.get("ok"), c)
check("version bumped", int(cp.get("version") or 0) == 2, cp.get("version"))
check("plan is back to proposed", cp.get("state") == "proposed", cp.get("state"))
check("the counter-proposer is confirmed", cp.get("my_response") == "confirmed")
hp = (get(HOST, PID).get("plan") or {})
check("the host's yes to the OLD time no longer counts", hp.get("my_response") is None, hp.get("my_response"))
check("host is on the waiting list", HOST in (hp.get("waiting_on") or []), hp.get("waiting_on"))
check("the address stays visible to whoever typed it", hp.get("address") == "Carrer Verdi 12", hp.get("address"))
check("starts_at really moved", abs(float(cp.get("starts_at") or 0) - NEW) < 2, cp.get("starts_at"))

stale = call("/api/agent/mplan-respond", {"id": PID, "self": HOST, "action": "confirm", "version": 1})
check("a stale version is refused", stale.get("error") == "VERSION_CONFLICT", stale)
ok2 = call("/api/agent/mplan-respond", {"id": PID, "self": HOST, "action": "confirm", "version": 2})
check("confirming the current version works", (ok2.get("plan") or {}).get("state") == "confirmed", ok2)

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

# ---------------------------------------------------------------- missing address (OF.20a)
print("\n-- OF.20a: a plan whose exact address is not set yet --")
H5, G5 = HOST + "e", GUEST + "e"
match(H5, G5, "e")
p5 = plan(H5, G5, "e", address="")
PID5 = (p5.get("plan") or {}).get("id")
check("a plan without an exact address is allowed", p5.get("ok"), p5)
check("address_set is false", (p5.get("plan") or {}).get("address_set") is False)
call("/api/agent/mplan-respond", {"id": PID5, "self": G5, "action": "confirm"})
g5 = (get(G5, PID5).get("plan") or {})
check("confirming does not invent an address", g5.get("address") == "" and g5.get("address_set") is False, g5)
upd = call("/api/agent/mplan-respond", {"id": PID5, "self": H5, "action": "counter",
                                        "address": "Carrer Nou 3"})
check("the host can add the address later", (upd.get("plan") or {}).get("address_set") is True, upd)
g5b = (get(G5, PID5).get("plan") or {})
check("adding an address re-opens confirmation", g5b.get("my_response") is None, g5b.get("my_response"))
check("and the guest does not see it until they confirm again", g5b.get("address") == "", g5b.get("address"))

print("\n" + "=" * 76)
print("РЕЗУЛЬТАТ: %d ok, %d проблем" % (R["ok"], R["fail"]))
if FAILED:
    for f in FAILED:
        print("  - " + f)
print("=" * 76)
sys.exit(1 if R["fail"] else 0)
