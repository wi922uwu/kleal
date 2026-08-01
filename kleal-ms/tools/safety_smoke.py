# -*- coding: utf-8 -*-
"""Block and report — OF.13b «Sheet · Profile options».

    python3 tools/safety_smoke.py [http://127.0.0.1:7074]

Both controls used to be toasts. «Заблокировать» removed the person from a local JavaScript array and
said «Заблокировано»; «Пожаловаться» said «Спасибо. Центр безопасности посмотрит.» Nothing was sent
anywhere: the blocked person kept seeing the profile, kept being able to invite, and reappeared in the
next search, because that list was rebuilt from the server every time.

So these checks are about the routes a block has to close, not about the button. A block that only
filters search results is a peephole — the direct routes stay open, and those are the ones that matter
to someone who wants to be left alone.
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
A = "SafeA%d" % S
B = "SafeB%d" % S
C = "SafeC%d" % S


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


print("=" * 76)
print("SAFETY: BLOCK & REPORT  ->  %s" % BASE)
print("=" * 76)

print("\n-- a block closes what is already open --")
inv = call("/api/agent/propose", {"from": A, "to": B, "intent": {"topics": ["coffee"]},
                                  "idem": "sa%d" % S})
RID = inv.get("id")
check("an invitation is open before the block", inv.get("ok"), inv)
call("/api/agent/respond", {"id": RID, "decision": "accept", "self": B})
pl = call("/api/agent/mplan-propose", {"self": A, "to": B, "title": "Coffee",
                                       "starts_at": time.time() + 48 * 3600,
                                       "district": "Gracia", "idem": "sp%d" % S})
PID = (pl.get("plan") or {}).get("id")
check("and a plan exists", pl.get("ok"), pl)

bl = call("/api/agent/block", {"self": B, "name": A, "idem": "bl%d" % S})
check("block succeeds", bl.get("ok"), bl)
check("the plan between them is cancelled", (bl.get("closed") or {}).get("plans") == 1, bl.get("closed"))
after = call("/api/agent/mplan?self=%s&id=%s" % (quote(B), quote(PID)))
check("and really is cancelled", (after.get("plan") or {}).get("state") == "cancelled", after)

print("\n-- and every route to reach the person --")
msg = call("/api/agent/message", {"from": A, "to": B, "text": "hi"})
check("a blocked sender cannot message", msg.get("error") == "BLOCKED", msg)
msg2 = call("/api/agent/message", {"from": B, "to": A, "text": "hi"})
check("nor can the blocker — a block is two-sided", msg2.get("error") == "BLOCKED", msg2)
inv2 = call("/api/agent/propose", {"from": A, "to": B, "intent": {"topics": ["coffee"]}})
check("a blocked sender cannot invite", inv2.get("error") == "BLOCKED", inv2)
pl2 = call("/api/agent/mplan-propose", {"self": A, "to": B, "title": "X",
                                        "starts_at": time.time() + 48 * 3600})
check("an old acceptance does not let a plan through", pl2.get("error") == "BLOCKED", pl2)

print("\n-- and the search itself, against a real person in the pool --")


def slate(searcher):
    r = call("/api/agent/match", {"intent": {"topics": ["coffee"], "mode": "offline"},
                                  "profile": {"name": searcher, "city": "Barcelona",
                                              "lat": 41.40, "lon": 2.16, "languages": ["en"]},
                                  "ctx": {"self": searcher, "now": 1785600000}})
    return [str(c.get("name")) for c in (r.get("candidates") or [])]


before = slate(C)
victim = before[0] if before else None
check("the pool returns somebody to block", bool(victim), before[:3])
if victim:
    call("/api/agent/block", {"self": C, "name": victim})
    after_names = slate(C)
    check("a blocked person leaves the search", victim not in after_names, after_names[:3])
    check("and the rest of the slate survives", len(after_names) >= max(0, len(before) - 1),
          (len(before), len(after_names)))
    call("/api/agent/block", {"self": C, "name": victim, "on": False})
    check("unblocking brings them back", victim in slate(C), victim)

print("\n-- unblocking gives the routes back --")
un = call("/api/agent/block", {"self": B, "name": A, "on": False})
check("unblock succeeds", un.get("ok"), un)
check("the list is empty again", not (un.get("blocked") or []), un.get("blocked"))
msg3 = call("/api/agent/message", {"from": A, "to": B, "text": "hi again"})
check("messages work again", msg3.get("ok"), msg3)
check("but the cancelled plan stays cancelled",
      (call("/api/agent/mplan?self=%s&id=%s" % (quote(B), quote(PID))).get("plan") or {}).get("state")
      == "cancelled")

print("\n-- reporting --")
rp = call("/api/agent/report", {"self": C, "name": A, "reason": "harassment",
                                "text": "kept messaging after I said no", "idem": "rp%d" % S})
check("a report is accepted", rp.get("ok") and rp.get("id"), rp)
sf = call("/api/agent/safety?self=" + quote(C))
mine = sf.get("reports") or []
check("it is stored, not just acknowledged", len(mine) == 1, sf)
check("with the reason", mine and mine[0].get("reason") == "harassment", mine)
check("and the text", mine and mine[0].get("text").startswith("kept messaging"), mine)
check("reporting also blocks — you should not have to keep meeting them",
      A.lower() in [str(x).strip().lower() for x in (sf.get("blocked") or [])], sf.get("blocked"))
bad = call("/api/agent/report", {"self": C, "name": A, "reason": "because"})
check("an unknown reason falls back rather than being stored raw", bad.get("ok"), bad)
sf2 = call("/api/agent/safety?self=" + quote(C))
check("and is filed as 'other'", (sf2.get("reports") or [])[-1].get("reason") == "other",
      (sf2.get("reports") or [])[-1])

print("\n-- the awkward inputs --")
self_b = call("/api/agent/block", {"self": A, "name": A})
check("you cannot block yourself", self_b.get("error") == "TWO_PEOPLE_REQUIRED", self_b)
self_r = call("/api/agent/report", {"self": A, "name": A})
check("nor report yourself", self_r.get("error") == "TWO_PEOPLE_REQUIRED", self_r)
twice = call("/api/agent/block", {"self": C, "name": B})
twice2 = call("/api/agent/block", {"self": C, "name": B})
check("blocking twice does not duplicate the entry",
      (twice2.get("blocked") or []).count(B.lower()) == 1, twice2)
case = call("/api/agent/block", {"self": C, "name": B.upper()})
check("case does not create a second entry",
      len([x for x in (case.get("blocked") or []) if x == B.lower()]) == 1, case)
noone = call("/api/agent/block", {"self": C, "name": ""})
check("an empty name is refused", noone.get("error") == "TWO_PEOPLE_REQUIRED", noone)

print("\n" + "=" * 76)
print("РЕЗУЛЬТАТ: %d ok, %d проблем" % (R["ok"], R["fail"]))
if FAILED:
    for f in FAILED:
        print("  - " + f)
print("=" * 76)
sys.exit(1 if R["fail"] else 0)
