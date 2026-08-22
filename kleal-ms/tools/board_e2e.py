# -*- coding: utf-8 -*-
"""The whole «1:1 Offline» board walked as a journey, not as a list of endpoints.

    python3 tools/board_e2e.py [http://127.0.0.1:7074]

The per-endpoint suites (mplan_smoke, safety_smoke) each prove one thing in isolation. What they
cannot catch is a board that works screen by screen and breaks between screens: an invitation that
never arrives in the other account's inbox, a plan that is confirmed on one side and pending on the
other, an address that opens for the wrong person, a delay nobody receives.

So this walks the three rows of the board end to end, with two real accounts talking to one server:

    row 1  OF.11 -> OF.14 -> OF.18 -> OF.20 -> OF.21 -> OF.22 -> OF.23 -> OF.24 -> OF.25
    row 2  OF.16 declined · OF.20a address later · OF.21a/b counter · OF.22a late · OF.24a no-show
    row 3  OF.C1 invited -> OF.C2 chat -> OF.C3 confirm -> OF.C4 they're late -> OF.C5 new time

Every assertion is made from BOTH sides where the board draws both sides. Reading a state back from
the account that wrote it proves nothing about whether it arrived.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import quote

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7074").rstrip("/")
R = {"ok": 0, "fail": 0}
FAILED = []
S = int(time.time() * 1000) % 100000000 + os.getpid()
A = "BoardA%d" % S          # Dmitry's side — the host
B = "BoardB%d" % S          # Marta's side — the guest
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
    print(("  ok   " if cond else "  FAIL ") + name + (("   " + str(detail)[:130]) if detail else ""))


def plan_of(who, pid):
    return (call("/api/agent/mplan?self=%s&id=%s" % (quote(who), quote(pid))).get("plan") or {})


def inbox(who):
    return (call("/api/agent/inbox?self=" + quote(who)).get("requests") or [])


def outbox(who):
    return (call("/api/agent/outbox?self=" + quote(who)).get("requests") or [])


print("=" * 78)
print("BOARD «1:1 Offline» END TO END  ->  %s" % BASE)
print("=" * 78)

# ================================================================= ROW 1 — the happy path
print("\n### ROW 1 — create, invite, chat, plan, meet, feedback")

print("\nOF.11 Searching — the request produces a slate")
m = call("/api/agent/match", {"intent": {"topics": ["coffee"], "mode": "offline", "time": "today evening"},
                              "profile": {"name": A, "city": "Barcelona", "lat": 41.40, "lon": 2.16,
                                          "languages": ["en"]},
                              "ctx": {"self": A, "now": 1785600000}})
cands = m.get("candidates") or []
check("the search returns candidates", len(cands) > 0, len(cands))
check("OF.12 — the slate is capped at eight for 1:1", len(cands) <= 8, len(cands))
check("every candidate carries what the card shows",
      all(c.get("name") for c in cands), [c.get("name") for c in cands[:3]])

print("\nOF.14 Invite sent — and it ARRIVES in the other account")
inv = call("/api/agent/propose", {"from": A, "to": B, "intent": {"topics": ["coffee"], "title": "Coffee",
                                                                 "place": "Gracia", "time": "Thursday evening"},
                                  "note": "hey", "idem": "e2e_inv%d" % S})
RID = inv.get("id")
check("the invitation is stored", inv.get("ok") and RID, inv)
mine = [r for r in inbox(B) if r.get("id") == RID]
check("OF.C1 — it is in the guest's inbox", len(mine) == 1, [r.get("id") for r in inbox(B)][:3])
check("with the sender's name", mine and mine[0].get("from") == A)
check("and what the meetup is", mine and (mine[0].get("intent") or {}).get("title") == "Coffee")
check("the sender sees it as pending", any(r.get("id") == RID and r.get("status") == "pending"
                                           for r in outbox(A)))

print("\nOF.14 — the 4-second undo really withdraws it")
und = call("/api/agent/propose", {"from": A, "to": B + "z", "intent": {"topics": ["coffee"]},
                                  "idem": "e2e_und%d" % S})
call("/api/agent/withdraw", {"id": und.get("id"), "self": A})
check("a withdrawn invitation leaves the guest's inbox",
      not any(r.get("id") == und.get("id") for r in inbox(B + "z")))

print("\nOF.C1 -> OF.18 — the guest joins and a chat opens")
acc = call("/api/agent/respond", {"id": RID, "decision": "accept", "self": B})
check("the guest accepts", acc.get("ok") and acc.get("status") == "accepted", acc)
check("the sender's copy flips too",
      any(r.get("id") == RID and r.get("status") == "accepted" for r in outbox(A)))
call("/api/agent/message", {"from": A, "to": B, "text": "hey, coffee thursday?"})
call("/api/agent/message", {"from": B, "to": A, "text": "yes"})
th = call("/api/agent/thread?self=%s&with=%s" % (quote(B), quote(A)))
msgs = th if isinstance(th, list) else (th.get("messages") or [])
check("OF.C2 — both messages are in the guest's thread", len(msgs) == 2, msgs)
check("in the order they were sent", [x.get("from") for x in msgs] == [A, B], msgs)

print("\nOF.20 Plan proposed — the guest sees the district, not the address")
WHEN = time.time() + 48 * HOUR
p = call("/api/agent/mplan-propose", {"self": A, "to": B, "title": "Coffee & AI talk", "mode": "offline",
                                      "starts_at": WHEN, "district": "Gracia",
                                      "address": "Carrer de Verdi 12", "venue": "Nomad",
                                      "idem": "e2e_p%d" % S})
PID = (p.get("plan") or {}).get("id")
check("the plan is created", p.get("ok") and PID, p)
gv = plan_of(B, PID)
check("OF.C3 — the guest sees it", gv.get("id") == PID)
check("with the district", gv.get("district") == "Gracia")
check("and NOT the address", gv.get("address") == "", gv.get("address"))
check("but is told one exists", gv.get("address_set") is True)
check("the host still sees what they typed", plan_of(A, PID).get("address") == "Carrer de Verdi 12")

print("\nOF.C3 -> OF.21 — confirming opens the address for the guest")
call("/api/agent/mplan-respond", {"id": PID, "self": B, "action": "confirm"})
gv = plan_of(B, PID)
check("the plan is confirmed", gv.get("state") == "confirmed", gv.get("state"))
check("on the host's side too", plan_of(A, PID).get("state") == "confirmed")
check("the address is now open to the guest", gv.get("address") == "Carrer de Verdi 12")
check("and the venue with it", gv.get("venue") == "Nomad")

print("\nOF.22 / OF.22a / OF.C4 — running late travels between accounts")
call("/api/agent/mplan-status", {"id": PID, "self": A, "status": "otw"})
check("OF.22 — the guest sees «on the way»",
      (plan_of(B, PID).get("their_live") or {}).get("status") == "otw")
call("/api/agent/mplan-status", {"id": PID, "self": A, "status": "late", "eta_min": 12})
gl = plan_of(B, PID).get("their_live") or {}
check("OF.C4 — the guest sees the delay", gl.get("status") == "late", gl)
check("and how long", gl.get("eta_min") == 12)
check("the host's own view calls it theirs, not the other's",
      (plan_of(A, PID).get("my_live") or {}).get("status") == "late"
      and plan_of(A, PID).get("their_live") is None)

print("\nOF.23 -> OF.24 -> OF.25 — it happened, and both said so")
call("/api/agent/mplan-status", {"id": PID, "self": A, "status": "here"})
check("OF.23 — arrival is visible", (plan_of(B, PID).get("their_live") or {}).get("status") == "here")
call("/api/agent/mplan-feedback", {"id": PID, "self": A, "happened": True})
call("/api/agent/mplan-feedback", {"id": PID, "self": A, "rating": 5})
fb = plan_of(A, PID).get("my_feedback") or {}
check("OF.24 then OF.25 write to one record", fb.get("happened") is True and fb.get("rating") == 5, fb)
call("/api/agent/mplan-feedback", {"id": PID, "self": B, "happened": True, "rating": 4})
check("both answered -> done", plan_of(A, PID).get("state") == "done")
check("and it is history for BOTH",
      any(x.get("id") == PID for x in (call("/api/agent/mplans?self=" + quote(A)).get("history") or []))
      and any(x.get("id") == PID for x in (call("/api/agent/mplans?self=" + quote(B)).get("history") or [])))

# ================================================================= ROW 2 — the alternatives
print("\n### ROW 2 — the branches that are not the happy path")

print("\nOF.16 — «Marta can’t this time»")
A2, B2 = A + "n", B + "n"
r2 = call("/api/agent/propose", {"from": A2, "to": B2, "intent": {"topics": ["coffee"]},
                                 "idem": "e2e_dec%d" % S})
call("/api/agent/respond", {"id": r2.get("id"), "decision": "decline", "self": B2})
check("the sender learns of the decline",
      any(x.get("id") == r2.get("id") and x.get("status") == "declined" for x in outbox(A2)))
# A declined invitation stays in the recipient's inbox as their own history — they are the one who
# declined it. What must NOT survive is its being actionable.
check("and it is no longer actionable for the guest",
      not any(x.get("id") == r2.get("id") and x.get("status") == "pending" for x in inbox(B2)),
      [x.get("status") for x in inbox(B2)])
blocked = call("/api/agent/mplan-propose", {"self": A2, "to": B2, "title": "x",
                                            "starts_at": time.time() + 24 * HOUR})
check("a declined invitation does not let a plan through", blocked.get("error") == "NOT_MATCHED", blocked)

print("\nOF.20a — the exact place named after the time is agreed")
A3, B3 = A + "a", B + "a"
r3 = call("/api/agent/propose", {"from": A3, "to": B3, "intent": {"topics": ["coffee"]}, "idem": "e2e_a%d" % S})
call("/api/agent/respond", {"id": r3.get("id"), "decision": "accept", "self": B3})
p3 = call("/api/agent/mplan-propose", {"self": A3, "to": B3, "title": "Coffee", "starts_at": time.time() + 30 * HOUR,
                                       "district": "Gracia", "idem": "e2e_pa%d" % S})
PID3 = (p3.get("plan") or {}).get("id")
call("/api/agent/mplan-respond", {"id": PID3, "self": B3, "action": "confirm"})
v_before = plan_of(A3, PID3).get("version")
call("/api/agent/mplan-address", {"id": PID3, "self": A3, "address": "Carrer Nou 3", "venue": "Nomad"})
after = plan_of(A3, PID3)
check("naming the place keeps the plan confirmed", after.get("state") == "confirmed", after.get("state"))
check("and does not force anyone to confirm again", after.get("version") == v_before, after.get("version"))
check("the guest, who already agreed, sees it at once",
      plan_of(B3, PID3).get("address") == "Carrer Nou 3")

print("\nOF.21a / OF.21b / OF.C5 — the counter that cancels nothing")
OLD = plan_of(A3, PID3).get("starts_at")
NEW = time.time() + 55 * HOUR
call("/api/agent/mplan-respond", {"id": PID3, "self": B3, "action": "counter", "starts_at": NEW})
a_view, b_view = plan_of(A3, PID3), plan_of(B3, PID3)
check("OF.21b — the meeting has NOT moved", abs(a_view.get("starts_at") - OLD) < 2, a_view.get("starts_at"))
check("nothing was cancelled", a_view.get("state") == "confirmed", a_view.get("state"))
check("OF.C5 — the other side sees the suggestion as not theirs",
      (a_view.get("pending") or {}).get("mine") is False, a_view.get("pending"))
check("and the proposer sees it as theirs", (b_view.get("pending") or {}).get("mine") is True)
call("/api/agent/mplan-respond", {"id": PID3, "self": A3, "action": "reject_change"})
check("saying no leaves the evening untouched",
      abs(plan_of(A3, PID3).get("starts_at") - OLD) < 2 and plan_of(A3, PID3).get("state") == "confirmed")
call("/api/agent/mplan-respond", {"id": PID3, "self": B3, "action": "counter", "starts_at": NEW})
call("/api/agent/mplan-respond", {"id": PID3, "self": A3, "action": "accept_change"})
both = plan_of(B3, PID3)
check("accepting moves it for both", abs(both.get("starts_at") - NEW) < 2, both.get("starts_at"))
check("and both are confirmed on the new hour", both.get("both_confirmed") is True)

print("\nOF.24a — it did not happen")
A4, B4 = A + "x", B + "x"
r4 = call("/api/agent/propose", {"from": A4, "to": B4, "intent": {"topics": ["coffee"]}, "idem": "e2e_x%d" % S})
call("/api/agent/respond", {"id": r4.get("id"), "decision": "accept", "self": B4})
p4 = call("/api/agent/mplan-propose", {"self": A4, "to": B4, "title": "Coffee",
                                       "starts_at": time.time() + 20 * HOUR, "idem": "e2e_px%d" % S})
PID4 = (p4.get("plan") or {}).get("id")
call("/api/agent/mplan-respond", {"id": PID4, "self": B4, "action": "confirm"})
call("/api/agent/mplan-feedback", {"id": PID4, "self": B4, "happened": False, "reason": "no_show"})
o4 = plan_of(A4, PID4)
check("one «no» closes it without waiting for the other", o4.get("state") == "done", o4.get("state"))
check("and the reason is kept", (o4.get("outcome") or {}).get("reason") == "no_show", o4.get("outcome"))

# ================================================================= safety, mid-flow
print("\n### Safety cuts across the whole board, not just search")
A5, B5 = A + "s", B + "s"
r5 = call("/api/agent/propose", {"from": A5, "to": B5, "intent": {"topics": ["coffee"]}, "idem": "e2e_s%d" % S})
call("/api/agent/respond", {"id": r5.get("id"), "decision": "accept", "self": B5})
p5 = call("/api/agent/mplan-propose", {"self": A5, "to": B5, "title": "Coffee",
                                       "starts_at": time.time() + 40 * HOUR, "district": "Gracia",
                                       "address": "Somewhere 1", "idem": "e2e_ps%d" % S})
PID5 = (p5.get("plan") or {}).get("id")
call("/api/agent/mplan-respond", {"id": PID5, "self": B5, "action": "confirm"})
check("a confirmed plan exists before the block", plan_of(B5, PID5).get("state") == "confirmed")
call("/api/agent/block", {"self": B5, "name": A5})
check("blocking cancels the meeting", plan_of(B5, PID5).get("state") == "cancelled")
check("the blocked side cannot message", call("/api/agent/message", {"from": A5, "to": B5, "text": "?"})
      .get("error") == "BLOCKED")
check("nor start another plan",
      call("/api/agent/mplan-propose", {"self": A5, "to": B5, "title": "y",
                                        "starts_at": time.time() + 40 * HOUR}).get("error") == "BLOCKED")

print("\n" + "=" * 78)
print("РЕЗУЛЬТАТ: %d ok, %d проблем" % (R["ok"], R["fail"]))
if FAILED:
    for f in FAILED:
        print("  - " + f)
print("=" * 78)
sys.exit(1 if R["fail"] else 0)
