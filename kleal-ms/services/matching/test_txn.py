# -*- coding: utf-8 -*-
"""Spec §14 (transaction state machines) acceptance tests, run against the REAL service module.

Covers Appendix C #6 (policy changes between SENT and ACCEPT), #7 (same idempotency key -> same
result) and #9 (an expired proposal cannot be accepted), plus version compare-and-swap, withdrawal
and the "a settled proposal never flips" rule.

  python3 services/matching/test_txn.py      # exit 0 only when every check passes
"""
import os, sys, time, json, tempfile
d = tempfile.mkdtemp()
os.environ["KLEAL_STORE"] = os.path.join(d, "s.json")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as M

M.SESSION.clear(); M.SESSION["_requests"] = []
ok = fails = 0
def chk(name, cond):
    global ok, fails
    if cond: ok += 1; print("  ok   %s" % name)
    else: fails += 1; print("  FAIL %s" % name)

# --- #7 idempotency -------------------------------------------------------------
r1 = M.propose("Ann", "Bob", {"type": "walk"}, "hi", idem="k1")
r2 = M.propose("Ann", "Bob", {"type": "walk"}, "hi", idem="k1")
chk("propose is idempotent", r1 == r2 and r1["ok"])
rid = r1["id"]
chk("proposal has version+expiry", r1["version"] == 1 and r1["expires_at"] > time.time())

a1 = M.respond(rid, "accept", "Bob", idem="a1")
a2 = M.respond(rid, "accept", "Bob", idem="a1")
chk("accept is idempotent", a1 == a2 and a1["ok"] and a1["status"] == "accepted")

# --- concurrent accept / already resolved --------------------------------------
a3 = M.respond(rid, "decline", "Bob")
chk("settled proposal cannot be flipped", (not a3["ok"]) and a3["error"] == "ALREADY_RESOLVED"
    and M.inbox("Bob")[0]["status"] == "accepted")

# --- version compare-and-swap ---------------------------------------------------
r3 = M.propose("Cid", "Bob", {"type": "coffee"}, "", idem="k2")
bad = M.respond(r3["id"], "accept", "Bob", version=99)
chk("stale version rejected", bad["error"] == "VERSION_CONFLICT")
good = M.respond(r3["id"], "accept", "Bob", version=r3["version"])
chk("correct version accepted", good["ok"])

# --- #9 expired cannot be accepted ---------------------------------------------
r4 = M.propose("Dee", "Bob", {"type": "run"}, "")
for r in M._requests():
    if r["id"] == r4["id"]: r["expires_at"] = time.time() - 1
e = M.respond(r4["id"], "accept", "Bob")
chk("expired proposal rejected", e["error"] == "EXPIRED" and e["status"] == "expired")
chk("expiry visible in inbox", any(x["id"] == r4["id"] and x["status"] == "expired" for x in M.inbox("Bob")))

# --- #6 POLICY_CHANGED between SENT and ACCEPT ---------------------------------
POOL = [{"name": "Eve", "age": 30}, {"name": "Bob", "age": 30}]
M.load_candidates = lambda: POOL
r5 = M.propose("Eve", "Bob", {"type": "walk"}, "")
M.SESSION["me"] = {"blocked": ["Eve"], "feedback": {}}      # Bob blocks Eve after it was sent
pc = M.respond(r5["id"], "accept", "Bob")
chk("blocked-after-send is revoked", pc["error"] == "POLICY_CHANGED" and pc["status"] == "policy_revoked")

M.SESSION["me"] = {"blocked": [], "feedback": {}}
POOL[:] = [{"name": "Eve", "age": 30}, {"name": "Bob", "age": 30, "open": False}]
r6 = M.propose("Eve", "Bob", {"type": "walk"}, "")
pc2 = M.respond(r6["id"], "accept", "Bob")
chk("recipient closed after send is revoked", pc2["error"] == "POLICY_CHANGED")

POOL[:] = [{"name": "Eve", "age": 30}, {"name": "Bob", "age": 30}]
r7 = M.propose("Eve", "Bob", {"type": "walk"}, "")
chk("clean policy still accepts", M.respond(r7["id"], "accept", "Bob")["ok"])

# --- withdraw -------------------------------------------------------------------
r8 = M.propose("Eve", "Bob", {"type": "walk"}, "")
chk("recipient cannot withdraw", not M.withdraw_request(r8["id"], "Bob")["ok"])
w = M.withdraw_request(r8["id"], "Eve", idem="w1")
chk("sender withdraws", w["ok"] and w["status"] == "withdrawn")
chk("withdraw idempotent", M.withdraw_request(r8["id"], "Eve", idem="w1") == w)
chk("withdrawn cannot be accepted", M.respond(r8["id"], "accept", "Bob")["error"] == "ALREADY_RESOLVED")

# --- non-recipient cannot answer ------------------------------------------------
r9 = M.propose("Eve", "Bob", {"type": "walk"}, "")
chk("sender cannot self-accept", not M.respond(r9["id"], "accept", "Eve")["ok"])

print("\n%d ok, %d failed" % (ok, fails))
sys.exit(1 if fails else 0)
import os, sys, time, json, tempfile
d = tempfile.mkdtemp()
os.environ["KLEAL_STORE"] = os.path.join(d, "s.json")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as M

M.SESSION.clear(); M.SESSION["_requests"] = []
ok = fails = 0
def chk(name, cond):
    global ok, fails
    if cond: ok += 1; print("  ok   %s" % name)
    else: fails += 1; print("  FAIL %s" % name)

# --- #7 idempotency -------------------------------------------------------------
r1 = M.propose("Ann", "Bob", {"type": "walk"}, "hi", idem="k1")
r2 = M.propose("Ann", "Bob", {"type": "walk"}, "hi", idem="k1")
chk("propose is idempotent", r1 == r2 and r1["ok"])
rid = r1["id"]
chk("proposal has version+expiry", r1["version"] == 1 and r1["expires_at"] > time.time())

a1 = M.respond(rid, "accept", "Bob", idem="a1")
a2 = M.respond(rid, "accept", "Bob", idem="a1")
chk("accept is idempotent", a1 == a2 and a1["ok"] and a1["status"] == "accepted")

# --- concurrent accept / already resolved --------------------------------------
a3 = M.respond(rid, "decline", "Bob")
chk("settled proposal cannot be flipped", (not a3["ok"]) and a3["error"] == "ALREADY_RESOLVED"
    and M.inbox("Bob")[0]["status"] == "accepted")

# --- version compare-and-swap ---------------------------------------------------
r3 = M.propose("Cid", "Bob", {"type": "coffee"}, "", idem="k2")
bad = M.respond(r3["id"], "accept", "Bob", version=99)
chk("stale version rejected", bad["error"] == "VERSION_CONFLICT")
good = M.respond(r3["id"], "accept", "Bob", version=r3["version"])
chk("correct version accepted", good["ok"])

# --- #9 expired cannot be accepted ---------------------------------------------
r4 = M.propose("Dee", "Bob", {"type": "run"}, "")
for r in M._requests():
    if r["id"] == r4["id"]: r["expires_at"] = time.time() - 1
e = M.respond(r4["id"], "accept", "Bob")
chk("expired proposal rejected", e["error"] == "EXPIRED" and e["status"] == "expired")
chk("expiry visible in inbox", any(x["id"] == r4["id"] and x["status"] == "expired" for x in M.inbox("Bob")))

# --- #6 POLICY_CHANGED between SENT and ACCEPT ---------------------------------
POOL = [{"name": "Eve", "age": 30}, {"name": "Bob", "age": 30}]
M.load_candidates = lambda: POOL
r5 = M.propose("Eve", "Bob", {"type": "walk"}, "")
M.SESSION["me"] = {"blocked": ["Eve"], "feedback": {}}      # Bob blocks Eve after it was sent
pc = M.respond(r5["id"], "accept", "Bob")
chk("blocked-after-send is revoked", pc["error"] == "POLICY_CHANGED" and pc["status"] == "policy_revoked")

M.SESSION["me"] = {"blocked": [], "feedback": {}}
POOL[:] = [{"name": "Eve", "age": 30}, {"name": "Bob", "age": 30, "open": False}]
r6 = M.propose("Eve", "Bob", {"type": "walk"}, "")
pc2 = M.respond(r6["id"], "accept", "Bob")
chk("recipient closed after send is revoked", pc2["error"] == "POLICY_CHANGED")

POOL[:] = [{"name": "Eve", "age": 30}, {"name": "Bob", "age": 30}]
r7 = M.propose("Eve", "Bob", {"type": "walk"}, "")
chk("clean policy still accepts", M.respond(r7["id"], "accept", "Bob")["ok"])

# --- withdraw -------------------------------------------------------------------
r8 = M.propose("Eve", "Bob", {"type": "walk"}, "")
chk("recipient cannot withdraw", not M.withdraw_request(r8["id"], "Bob")["ok"])
w = M.withdraw_request(r8["id"], "Eve", idem="w1")
chk("sender withdraws", w["ok"] and w["status"] == "withdrawn")
chk("withdraw idempotent", M.withdraw_request(r8["id"], "Eve", idem="w1") == w)
chk("withdrawn cannot be accepted", M.respond(r8["id"], "accept", "Bob")["error"] == "ALREADY_RESOLVED")

# --- non-recipient cannot answer ------------------------------------------------
r9 = M.propose("Eve", "Bob", {"type": "walk"}, "")
chk("sender cannot self-accept", not M.respond(r9["id"], "accept", "Eve")["ok"])

print("\n%d ok, %d failed" % (ok, fails))
sys.exit(1 if fails else 0)
