# -*- coding: utf-8 -*-
"""Group formation, end to end — the three layers that each independently broke groups.

    python3 tools/groups_smoke.py [http://127.0.0.1:7074]

What was wrong, and what each block here holds to:

1. Asking for a group returned ZERO PEOPLE. `groupSize` routes an intent to the `group_formation`
   decision type; that type is off in the pilot, and the match handler answered with an empty slate
   and a `pilot` note the UI never rendered. The same query without that one field returned eight
   people. A layer being off is a reason not to ASSEMBLE a group — never a reason to hide the people.

2. §15 never received a slate. `run_group_formation` forms a group out of candidates it is GIVEN;
   it does not retrieve. Called without any, it answered NO_FEASIBLE_GROUP, which reads as the
   algorithm rejecting the request when it had simply been handed nobody.

3. The engine only ran behind an exact test-only override. That gate is deliberate and stays — what
   was missing was a PRODUCT switch above it (KLEAL_GROUPS), so the feature turns on and off in one
   place instead of depending on what a caller puts in the request body.
"""
import json
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7074").rstrip("/")
R = {"ok": 0, "fail": 0}
FAILED = []


def call(path, body=None, timeout=180):
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
    print(("  ok   " if cond else "  FAIL ") + name + (("   " + str(detail)[:110]) if detail else ""))


PROF = {"name": "GroupProbe", "interests": {"explicit": ["padel"]}}
CTX = {"self": "GroupProbe"}
PLAIN = {"topics": ["padel"], "type": "sport", "role": "play"}
GROUPY = dict(PLAIN, groupSize=4)

print("=" * 74)
print("1. ASKING FOR A GROUP MUST NOT COST YOU THE PEOPLE")
print("=" * 74)
a = call("/api/agent/match", {"intent": PLAIN, "profile": PROF, "ctx": CTX})
b = call("/api/agent/match", {"intent": GROUPY, "profile": PROF, "ctx": CTX})
na = len(a.get("candidates") or [])
nb = len(b.get("candidates") or [])
check("the plain request finds people", na > 0, "%d" % na)
check("adding groupSize does not empty the slate", nb > 0, "plain=%d group=%d" % (na, nb))
check("the decision type is recognised as group formation",
      (b.get("snapshot") or {}).get("decision_type") == "group_formation",
      (b.get("snapshot") or {}).get("decision_type"))

print()
print("=" * 74)
print("2. THE SLATE BECOMES A GROUP")
print("=" * 74)
g = b.get("group") or {}
live = bool(g.get("group_formation_live"))
if not live:
    print("  (KLEAL_GROUPS is off — asserting the honest-dormant contract instead)")
    check("the group block says it is off, and says why",
          g.get("feasible") is False and "not enabled" in json.dumps(g, ensure_ascii=False),
          json.dumps(g, ensure_ascii=False)[:120])
    check("people are still returned while it is off", nb > 0, nb)
else:
    check("a group was formed", g.get("feasible") is True, g.get("violations") or g)
    mem = g.get("members") or []
    check("it has members", len(mem) >= 2, mem)
    names = {str(c.get("name")) for c in (b.get("candidates") or [])}
    check("every member comes from the ranked slate", set(mem).issubset(names),
          [m for m in mem if m not in names])
    check("the searcher is not in their own group", "GroupProbe" not in mem, mem)
    check("no constraint violations", not (g.get("violations") or []), g.get("violations"))
    check("a utility is reported, so the choice can be argued with", g.get("utility") is not None,
          g.get("utility"))
    check("invitations are prepared but NOT sent by matching",
          isinstance(g.get("invitations"), list) or g.get("invitations") is None,
          type(g.get("invitations")).__name__)

    check("a search does NOT claim seats — it is a read", g.get("reserved") is False, g.get("reserved"))

    print()
    print("  determinism — the same request must not shuffle the company")
    g2 = (call("/api/agent/match", {"intent": GROUPY, "profile": PROF, "ctx": CTX}).get("group") or {})
    check("the same request forms the same group", (g2.get("members") or []) == (g.get("members") or []),
          [g.get("members"), g2.get("members")])

print()
print("=" * 74)
print("3. /api/agent/group RANKS FOR ITSELF WHEN GIVEN NO SLATE")
print("=" * 74)
d = call("/api/agent/group", {"intent": GROUPY, "profile": PROF, "ctx": CTX})
if live:
    check("an empty body no longer means NO_FEASIBLE_GROUP",
          "NO_FEASIBLE_GROUP" not in json.dumps(d.get("violations") or []), d.get("violations"))
    check("it forms a group on its own", bool(d.get("members")), d.get("members"))
    check("and still reserves nothing without an explicit commit", d.get("reserved") is False, d.get("reserved"))
    e = call("/api/agent/group", {"intent": GROUPY, "profile": PROF, "ctx": CTX, "reserve": True})
    check("an explicit commit DOES claim seats", e.get("reserved") is True, e.get("reserved"))
    check("the commit reports the reservations", bool((e.get("reservations") or {}).get("reservations")
                                                      or e.get("reservations")), type(e.get("reservations")).__name__)
else:
    check("dormant response is still honest", d.get("enabled") is False, d)

print()
print("=" * 74)
print("4. THE MANUAL LIFECYCLE STILL WORKS (create -> list -> join -> leave)")
print("=" * 74)
import time
idem = "grp-smoke-%d" % int(time.time())
c = call("/api/agent/group-create", {"host": "GroupProbe", "title": "Padel smoke", "topics": ["padel"],
                                     "when": "Sunday", "area": "Gràcia", "mode": "offline",
                                     "min_size": 2, "max_size": 4, "idem": idem})
gid = (c.get("group") or {}).get("gid") or c.get("gid")
check("a group can be opened", bool(gid), c)
lst = call("/api/agent/groups?self=GroupProbe&limit=50") or {}
check("it appears in the list", any((x.get("gid") == gid) for x in (lst.get("groups") or [])),
      len(lst.get("groups") or []))
j = call("/api/agent/group-join", {"gid": gid, "self": "GroupJoiner", "idem": "j-" + idem})
check("someone can join", j.get("ok") is not False and not j.get("error"), j)
l = call("/api/agent/group-leave", {"gid": gid, "self": "GroupJoiner", "idem": "l-" + idem})
check("someone can leave", l.get("ok") is not False and not l.get("error"), l)

print()
print("=" * 74)
print("RESULT: %d ok, %d failed   (group formation live: %s)" % (R["ok"], R["fail"], live))
for f in FAILED:
    print("   -", f)
sys.exit(1 if R["fail"] else 0)
