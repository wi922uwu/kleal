# -*- coding: utf-8 -*-
"""Spec §15 (Group Formation Core) acceptance tests against the REAL service module.

Checks the SET-level rules that make a group different from a proposal: capacity as a hard
constraint (no double-booking the last seat), quorum, waitlist promotion on a drop, pairwise
safety exclusions against every member, host succession, and least-misery group utility.

  python3 services/matching/test_groups.py
"""
import os, sys, time, tempfile, threading
os.environ["KLEAL_STORE"] = os.path.join(tempfile.mkdtemp(), "s.json")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as M

POOL = [{"name": "Host", "age": 30, "interests": ["football"], "languages": ["ru"]},
        {"name": "Ann",  "age": 28, "interests": ["football"], "languages": ["ru", "en"]},
        {"name": "Bob",  "age": 35, "interests": ["football"], "languages": ["en"]},
        {"name": "Cid",  "age": 41, "interests": ["chess"],    "languages": ["es"]},
        {"name": "Kid",  "age": 15, "interests": ["football"], "languages": ["ru"]}]
M.load_candidates = lambda: POOL
M.SESSION.clear(); M.SESSION["_groups"] = []; M.SESSION["me"] = {"blocked": [], "feedback": {}}

ok = fails = 0
def chk(name, cond):
    global ok, fails
    if cond: ok += 1; print("  ok   %s" % name)
    else: fails += 1; print("  FAIL %s" % name)

g = M.group_create("Host", "Футбол в парке", ["football"], "Сегодня вечером",
                   "Москва", "offline", 3, 3, idem="g1")["group"]
gid = g["gid"]
chk("host is a member from the start", g["members"] == ["Host"] and g["size"] == 1)
chk("below quorum -> forming", g["state"] == "forming")
chk("create is idempotent", M.group_create("Host", "x", ["football"], idem="g1")["group"]["gid"] == gid)

chk("join", M.group_join(gid, "Ann")["ok"])
after = M.group_join(gid, "Bob")["group"]
chk("quorum reached -> full at capacity", after["state"] == "full" and after["size"] == 3)
chk("re-join is a no-op, not a duplicate", M.group_join(gid, "Ann")["group"]["size"] == 3)

w = M.group_join(gid, "Cid")
chk("over capacity -> waitlist", w["ok"] and w.get("waitlisted") and w["group"]["waitlist"] == ["Cid"])

# a minor must not get in through anyone's group (§15.1 safety exclusions, pairwise)
g2 = M.group_create("Host", "Другая", ["football"], min_size=2, max_size=4)["group"]
r = M.group_join(g2["gid"], "Kid")
chk("minor excluded from the set", (not r["ok"]) and r["error"] == "NOT_ELIGIBLE")

M.SESSION["me"]["blocked"] = ["Bob"]
g3 = M.group_create("Host", "Третья", ["football"], min_size=2, max_size=4)["group"]
chk("blocked person cannot join", M.group_join(g3["gid"], "Bob")["error"] == "NOT_ELIGIBLE")
M.SESSION["me"]["blocked"] = []

# concurrent race for the last seat: exactly one winner, the other waitlisted
g4 = M.group_create("Host", "Гонка", ["football"], min_size=2, max_size=2)["group"]
res = {}
def race(who):
    res[who] = M.group_join(g4["gid"], who)
ts = [threading.Thread(target=race, args=(n,)) for n in ("Ann", "Bob")]
[t.start() for t in ts]; [t.join() for t in ts]
seated = [n for n in ("Ann", "Bob") if not res[n].get("waitlisted")]
chk("exactly one wins the last seat", len(seated) == 1)
final = M.group_list("Host")
g4f = [x for x in final if x["gid"] == g4["gid"]][0]
chk("capacity never exceeded under a race", g4f["size"] == 2 and len(g4f["waitlist"]) == 1)

# leaving promotes from the waitlist and re-forms rather than cancelling
left = M.group_leave(gid, "Bob")
chk("waitlist promoted on a drop", left["ok"] and left["promoted"] == "Cid"
    and "Cid" in left["group"]["members"])
chk("stale version rejected", M.group_join(gid, "Bob", version=1)["error"] == "VERSION_CONFLICT")

hostleft = M.group_leave(gid, "Host")
chk("group survives its host", hostleft["group"]["host"] != "Host" and hostleft["group"]["size"] == 2)
for n in list(hostleft["group"]["members"]):
    last = M.group_leave(gid, n)
chk("empty group is cancelled", last["group"]["state"] == "cancelled")
chk("cancelled groups leave the list", all(x["gid"] != gid for x in M.group_list("Host")))
chk("cancelled group cannot be joined", M.group_join(gid, "Ann")["error"] == "CANCELLED")

# §15.2 least misery: the weakest link must not be averaged away
g5 = M.group_create("Host", "Футбол", ["football"], min_size=2, max_size=4)["group"]
M.group_join(g5["gid"], "Ann")
u_good = M.group_utility([x for x in M._groups() if x["id"] == g5["gid"]][0])
M.group_join(g5["gid"], "Cid")                     # chess person in a football group
u_mixed = M.group_utility([x for x in M._groups() if x["id"] == g5["gid"]][0])
chk("utility is computed", u_good["utility"] is not None and u_mixed["utility"] is not None)
chk("least_misery drops when a misfit joins", u_mixed["least_misery"] <= u_good["least_misery"])
chk("least_misery <= mean_pair_fit", u_mixed["least_misery"] <= u_mixed["mean_pair_fit"])

print("\n%d ok, %d failed" % (ok, fails))
sys.exit(1 if fails else 0)
