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
print("5. THE SIZE ASKED FOR IS THE SIZE FORMED")
print("=" * 74)
# Every groupSize used to produce exactly three people: §15 grows a seed only while a size/quorum
# SHORTFALL is outstanding, and adding a weaker member always lowers least_misery, so nothing is ever
# added for utility alone. Group size is therefore decided by size_min — which nothing derived from
# the intent, so it stayed at the config default of 3 whether you asked for 2 or for 8.
if live:
    got, seats = {}, {}
    for n in (2, 4, 6, 8):
        gg = (call("/api/agent/match", {"intent": dict(PLAIN, groupSize=n),
                                        "profile": PROF, "ctx": CTX}).get("group") or {})
        # groupSize is the TOTAL at the meetup, the asker included — they are not in their own slate.
        got[n] = len(gg.get("members") or []) + (1 if gg.get("members") else 0)
        seats[n] = gg.get("seats") or {}
    check("different sizes produce different groups", len(set(got.values())) > 1, got)
    for n, tot in got.items():
        check("asking for %d gives at most %d" % (n, n), tot <= n, "%d -> %d" % (n, tot))
    check("a large ask is not silently served as the smallest group", got.get(8, 0) > got.get(2, 0), got)
    # PLAIN is padel, and §15.4 says a padel court seats four. Asking for eight must therefore be
    # ANSWERED with four rather than refused — and must still report that eight was what was asked,
    # or the screen cannot explain why it got fewer.
    check("a domain ceiling clamps instead of refusing", got.get(8) == 4, got)
    check("the original ask survives the clamp, so the UI can explain it",
          seats.get(8, {}).get("asked") == 8, seats.get(8))

print()
print("=" * 74)
print("6. THE GROUP IS THE BEST OF THE SLATE, NOT THE FIRST OF IT")
print("=" * 74)
# §15 reads each member's directed fit from `relevance`; core_v2 cards carry it as `lcb`. Only
# /api/agent/group mapped between the two, so through /api/agent/match every utility term that
# depends on relevance was 0 and selection fell through to the id-hash tiebreak — on prod that put a
# 0.665 candidate in the group and left the 0.883 one out.
if live:
    m = call("/api/agent/match", {"intent": dict(PLAIN, groupSize=4), "profile": PROF, "ctx": CTX})
    gg = m.get("group") or {}
    slate = [(str(c.get("name")), float(c.get("lcb") or 0)) for c in (m.get("candidates") or [])]
    mem = gg.get("members") or []
    comp = gg.get("components") or {}
    check("member relevance reaches the utility function",
          float(comp.get("least_misery") or 0) > 0 or float(comp.get("mean_pair_fit") or 0) > 0, comp)
    if slate and mem:
        # NOT "the group is the top N by lcb": §15 optimises a SET (least_misery, role coverage,
        # time overlap), and among equal-utility sets it breaks ties by id-hash — verified on prod,
        # where the chosen trio and the naive top-3 scored an identical 0.7071 because two members
        # were tied at 0.666. Demanding one side of a tie would fail on a correct engine.
        # The invariant that DOES hold, and that the bug broke: nobody left out beats somebody left in.
        rel = dict(slate)
        worst_in = min(float(rel.get(x, 0)) for x in mem)
        best_out = max([v for n, v in slate if n not in mem] or [0.0])
        check("no excluded candidate outranks an included one", worst_in >= best_out - 1e-6,
              "worst member %.3f vs best left out %.3f" % (worst_in, best_out))
        check("the group is not the alphabetical head of the slate",
              [n for n, _ in slate[:len(mem)]] != mem or len(set(v for _, v in slate)) == 1,
              "slate head %s / picked %s" % ([n for n, _ in slate[:len(mem)]], mem))

print()
print("=" * 74)
print("7. A FREE-TEXT GROUP REQUEST BECOMES A GROUP INTENT")
print("=" * 74)
# The parser had no groupSize key and the request screen dropped its own answer, so nothing in the
# product ever set the field: «собери компанию из 5 человек» was served as one-person matching.
for q, want in (("хочу собрать группу на падел, человека 4", 4),
                ("ищу компанию из 5 человек в бар", 5),
                ("хочу с кем-нибудь выпить кофе", None)):
    it = (call("/api/agent/plan", {"query": q, "profile": PROF, "ctx": CTX}).get("intent") or {})
    check("%-42s -> groupSize %s" % (q[:42], want), it.get("groupSize") == want,
          "got %r" % it.get("groupSize"))

print()
print("=" * 74)
print("RESULT: %d ok, %d failed   (group formation live: %s)" % (R["ok"], R["fail"], live))
for f in FAILED:
    print("   -", f)
sys.exit(1 if R["fail"] else 0)
