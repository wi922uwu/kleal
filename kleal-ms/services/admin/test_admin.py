# -*- coding: utf-8 -*-
"""Admin panel + matching-probe tests. Run ON the box, against the live services:

    KLEAL_ADMIN_TOKEN=$(cat admin_token.txt) python3 services/admin/test_admin.py

Every assertion here exists because something was actually wrong. They are regression
tests first and coverage second — a test that would have passed before the fix is not
worth the seconds it costs.
"""
import json
import os
import sys
import urllib.error
import urllib.request

ADMIN = os.environ.get("ADMIN_URL", "http://127.0.0.1:7077").rstrip("/")
MATCH = os.environ.get("MATCH_URL", "http://127.0.0.1:7074").rstrip("/")
TOKEN = os.environ.get("KLEAL_ADMIN_TOKEN") or ""
if not TOKEN:
    for p in ("admin_token.txt", os.path.join(os.path.dirname(__file__), "..", "..", "admin_token.txt")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                TOKEN = f.read().strip()
            if TOKEN:
                break
        except Exception:
            pass

_fails = []
_ran = [0]


def check(name, cond, detail=""):
    _ran[0] += 1
    if cond:
        print("  ok   %s" % name)
    else:
        print("  FAIL %s   %s" % (name, detail))
        _fails.append(name)


def _req(url, data=None, token=None, timeout=180):
    """Returns (status, parsed_json_or_text)."""
    body = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Admin-Token"] = token
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8")
            try:
                return r.status, json.loads(raw)
            except ValueError:
                return r.status, raw
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:
        return 0, str(e)


# The searcher used throughout. Deliberately a complete profile: an INCOMPLETE one hides
# the very gate bugs these tests exist to catch.
SEARCHER = {"name": "Ivan", "area": "Belgrade", "lat": 44.8125, "lon": 20.4612, "radiusKm": 25,
            "interests": ["ai", "startups"], "langs": ["ru"], "age": 33, "verified": True,
            "formats": ["offline"]}
INTENT = {"topics": ["coffee"], "role": "meet", "mode": "offline", "time": "tomorrow"}


def test_auth():
    print("\n[auth] the panel used to be open to anyone with the URL")
    st, _ = _req(ADMIN + "/api/admin/users")
    check("API refuses without a token", st == 401, "got %s" % st)
    st, _ = _req(ADMIN + "/api/admin/users", token="wrong-token-entirely")
    check("API refuses a wrong token", st == 401, "got %s" % st)
    st, page = _req(ADMIN + "/")
    check("the page itself still serves (that is where you type the token)",
          st == 200 and isinstance(page, str) and "Kleal" in page, "got %s" % st)
    st, _ = _req(ADMIN + "/api/admin/users", token=TOKEN)
    check("API accepts the real token", st == 200, "got %s" % st)


def test_destructive_routes_gone():
    print("\n[safety] two routes deleted the live store with no auth, no backup, no audit")
    for r in ("clear", "reseed"):
        st, _ = _req(ADMIN + "/api/admin/" + r, data={}, token=TOKEN)
        check("/api/admin/%s no longer exists" % r, st == 404, "got %s" % st)


def test_health_and_store_agreement():
    print("\n[health] the panel and the engine once read DIFFERENT users.json files")
    st, h = _req(ADMIN + "/api/admin/health", token=TOKEN)
    check("health responds", st == 200 and isinstance(h, dict), "got %s" % st)
    if not isinstance(h, dict):
        return
    core = h.get("core") or {}
    check("engine reports itself enabled", bool(core.get("enabled")), json.dumps(core)[:120])
    check("config sha is reported", bool(core.get("config_sha")), json.dumps(core)[:120])
    eng_path = (h.get("store") or {}).get("path")
    check("panel and engine read the SAME store",
          eng_path and eng_path == h.get("adminStore"),
          "engine=%s admin=%s" % (eng_path, h.get("adminStore")))
    src = h.get("bySource") or {}
    check("pool provenance is broken down by source", bool(src), json.dumps(src)[:120])
    check("loadtest rows are NOT in the searchable pool", "loadtest" not in src, json.dumps(src)[:120])


def test_funnel_arithmetic():
    print("\n[funnel] «почему никого нет» — the numbers have to add up, or it is decoration")
    st, r = _req(ADMIN + "/api/admin/funnel",
                 data={"self": "Nadia", "intent": INTENT}, token=TOKEN)
    check("funnel responds", st == 200 and isinstance(r, dict) and r.get("funnel"), "got %s" % st)
    f = (r or {}).get("funnel") or {}
    if not f:
        return
    gates = sum((f.get("gates") or {}).values())
    check("pool − self − gated == eligible",
          f.get("pool", 0) - f.get("self", 0) - gates == f.get("eligible"),
          "pool=%s self=%s gated=%s eligible=%s" % (f.get("pool"), f.get("self"), gates, f.get("eligible")))
    scored = f.get("scored") or {}
    check("everything eligible reached scoring", scored.get("_in") == f.get("eligible"),
          "_in=%s eligible=%s" % (scored.get("_in"), f.get("eligible")))
    drops = sum(v for k, v in scored.items() if k != "_in")
    check("scored − engine drops == slate (or the slate cap of 8)",
          scored.get("_in", 0) - drops >= f.get("slate", 0) and f.get("slate", 0) <= 8,
          "in=%s drops=%s slate=%s" % (scored.get("_in"), drops, f.get("slate")))
    meta = f.get("meta") or {}
    check("the search reports which engine and config ran it",
          meta.get("core") and meta.get("config_version") and meta.get("domain"),
          json.dumps(meta)[:120])


def test_searcher_profile_carries_age():
    print("\n[lab] the lab could not test a dating search: the searcher had no age")
    st, r = _req(ADMIN + "/api/admin/funnel",
                 data={"self": "Nadia", "intent": INTENT}, token=TOKEN)
    prof = (r or {}).get("searcher") or {}
    check("searcher profile carries age", prof.get("age") is not None, json.dumps(prof)[:160])
    check("searcher profile carries formats", "formats" in prof, json.dumps(prof)[:160])
    check("a known searcher is recognised as known", (r or {}).get("searcherKnown") is True,
          str((r or {}).get("searcherKnown")))


def test_stability():
    print("\n[stability] drift is indistinguishable, from outside, from «random people»")
    for topic in ("coffee", "padel", "books"):
        st, r = _req(MATCH + "/api/agent/stability",
                     data={"profile": SEARCHER, "runs": 4,
                           "intent": dict(INTENT, topics=[topic])})
        ok = isinstance(r, dict) and r.get("ok")
        check("%s: stability probe responds" % topic, st == 200 and ok, "got %s" % st)
        if not ok:
            continue
        check("%s: same set across 4 runs" % topic, r.get("stableSet") is True,
              "drift=%s" % (r.get("drift"),))
        check("%s: same order across 4 runs" % topic, r.get("stableOrder") is True, "")


def test_diversity_discriminates():
    print("\n[diversity] «мне попадаются одни и те же люди» — as a number")
    topics = ["padel", "coffee", "football", "dota", "yoga", "books", "photography", "cooking"]
    st, r = _req(MATCH + "/api/agent/diversity",
                 data={"profile": SEARCHER, "intent": {"role": "meet", "mode": "offline",
                                                       "time": "tomorrow"},
                       "topics": topics})
    ok = isinstance(r, dict) and r.get("ok")
    check("diversity probe responds", st == 200 and ok, "got %s" % st)
    if not ok:
        return
    runs = r.get("withResults") or 0
    check("every topic returned somebody", not r.get("emptyTopics"), str(r.get("emptyTopics")))
    # The real assertion: different topics must not return the same faces. With 8 slots per
    # slate, anything below 2 distinct people per query is the complaint being true.
    check("distinct people >= 4x the number of queries",
          r.get("distinctPeople", 0) >= runs * 4,
          "distinct=%s runs=%s" % (r.get("distinctPeople"), runs))
    worst = max([x["times"] for x in (r.get("topRepeats") or [])] or [0])
    check("no single person appears in most slates", worst <= max(2, runs // 2),
          "worst=%s of %s" % (worst, runs))


def test_engine_separates_topics():
    print("\n[engine] two unrelated topics must not return the same people")
    seen = {}
    for topic in ("football", "books"):
        st, r = _req(MATCH + "/api/agent/match",
                     data={"intent": dict(INTENT, topics=[topic]), "profile": SEARCHER,
                           "ctx": {"self": "Ivan", "uid": "test"}})
        seen[topic] = {c.get("name") for c in ((r or {}).get("candidates") or [])}
        check("%s returns candidates" % topic, bool(seen[topic]), "got %s" % st)
    if all(seen.values()):
        overlap = seen["football"] & seen["books"]
        check("football and books share at most 1 person", len(overlap) <= 1, str(sorted(overlap)))


def test_lab_still_works():
    print("\n[lab] the matching lab itself")
    st, r = _req(ADMIN + "/api/admin/match-test",
                 data={"self": "Nadia", "intent": INTENT}, token=TOKEN)
    check("match-test responds", st == 200 and isinstance(r, dict), "got %s" % st)
    check("match-test returns candidates", bool((r or {}).get("candidates")),
          json.dumps((r or {}).get("error"))[:120])
    cands = (r or {}).get("candidates") or []
    if cands:
        c = cands[0]
        check("candidate carries a band", bool(c.get("band")), json.dumps(c)[:120])
        check("candidate carries reasons", bool(c.get("reasons_ru") or c.get("reasons")),
              json.dumps(c)[:120])
        # The fix that made cards stop looking arbitrary: the interest a match is based on
        # must be visible among the first three tags.
        ru = (c.get("reasons_ru") or [""])[0]
        if ru.startswith("общее:"):
            claimed = [w.strip() for w in ru.replace("общее:", "").split(",") if w.strip()]
            shown = [str(i).lower() for i in (c.get("interests") or [])[:3]]
            check("the shared interest is visible in the shown tags",
                  any(x in shown for x in claimed), "%s vs %s" % (claimed, shown))


def test_person_card():
    print("\n[person] «почему этого человека никто не находит» — and the mirror question")
    st, r = _req(ADMIN + "/api/admin/person?name=Nadia", token=TOKEN)
    check("person card responds", st == 200 and isinstance(r, dict) and r.get("ok"), "got %s" % st)
    if not (isinstance(r, dict) and r.get("ok")):
        return
    for k in ("identity", "policy", "readiness", "blocks", "warnings", "outbound", "verdict"):
        check("card carries %s" % k, k in r, json.dumps(sorted(r.keys()))[:140])
    ident = r.get("identity") or {}
    # The whole point: a missing value is reported as missing. A fabricated default here would hide
    # the exact gate that drops the person — which is what the edit form used to do on every save.
    check("a missing coordinate is null, not invented",
          ("lat" in ident) and (ident["lat"] is None or isinstance(ident["lat"], float)),
          json.dumps(ident)[:160])
    check("readiness is reported for every domain",
          len(r.get("readiness") or {}) >= 8, str(len(r.get("readiness") or {})))
    check("the panel knows the row id, so the verbs have a target", bool(r.get("id")), str(r.get("id")))
    st, r2 = _req(ADMIN + "/api/admin/person?name=NoSuchPersonAtAll", token=TOKEN)
    check("an unknown name is an honest miss, not a blank card",
          st == 200 and isinstance(r2, dict) and r2.get("ok") is False, json.dumps(r2)[:120])


def test_verbs_do_not_fabricate():
    print("\n[verbs] the edit form fabricated data on save — the verbs must not")
    st, before = _req(ADMIN + "/api/admin/person?name=Nadia", token=TOKEN)
    if not (isinstance(before, dict) and before.get("ok")):
        return check("baseline card readable", False, json.dumps(before)[:120])
    b_id = before.get("identity") or {}
    st, r = _req(ADMIN + "/api/admin/person/verb", data={"name": "Nadia", "verb": "pause"}, token=TOKEN)
    check("pause applies", st == 200 and (r or {}).get("ok"), json.dumps(r)[:120])
    st, mid = _req(ADMIN + "/api/admin/person?name=Nadia", token=TOKEN)
    keys = [x.get("key") for x in ((mid or {}).get("blocks") or [])]
    check("a paused person reads as invisible, with the reason named", "paused" in keys, str(keys))
    st, r = _req(ADMIN + "/api/admin/person/verb", data={"name": "Nadia", "verb": "unpause"}, token=TOKEN)
    check("unpause applies", st == 200 and (r or {}).get("ok"), json.dumps(r)[:120])
    st, after = _req(ADMIN + "/api/admin/person?name=Nadia", token=TOKEN)
    a_id = (after or {}).get("identity") or {}
    keys = [x.get("key") for x in ((after or {}).get("blocks") or [])]
    check("unpause removes the block", "paused" not in keys, str(keys))
    # The regression that matters: a round-trip through the verbs must not add interests, languages,
    # coordinates, a vibe or an invented "<Interest> scene" that the person never gave.
    for f in ("lat", "lon", "interests", "langs", "age", "area"):
        check("round-trip leaves %s untouched" % f, b_id.get(f) == a_id.get(f),
              "%r -> %r" % (b_id.get(f), a_id.get(f)))
    st, r = _req(ADMIN + "/api/admin/person/verb", data={"name": "Nadia", "verb": "delete"}, token=TOKEN)
    check("an unlisted verb is refused (the verb list is the whole safety model)",
          (r or {}).get("ok") is False, json.dumps(r)[:120])
    st, r = _req(ADMIN + "/api/admin/person/verb", data={"name": "NoSuchPerson", "verb": "pause"}, token=TOKEN)
    check("a verb on an unknown person is refused", (r or {}).get("ok") is False, json.dumps(r)[:120])
    st, r = _req(ADMIN + "/api/admin/person/fatigue-reset", data={"name": "Nadia"}, token=TOKEN)
    check("fatigue reset responds with what it cleared",
          st == 200 and (r or {}).get("ok") and "cleared" in (r or {}), json.dumps(r)[:120])


def test_pair_trace():
    print("\n[pair] «мне никогда не попадается X» — which step actually dropped X")
    st, r = _req(ADMIN + "/api/admin/explain",
                 data={"self": "Ivan", "intent": dict(INTENT), "candidate": "Nadia"}, token=TOKEN)
    check("explain responds", st == 200 and isinstance(r, dict), "got %s" % st)
    tr = (r or {}).get("trace") or {}
    check("the trace names the person", tr.get("name"), json.dumps(r)[:140])
    steps = tr.get("steps") or []
    check("the trace is a sequence of steps, not a verdict", len(steps) >= 3, str(len(steps)))
    check("every step says whether it passed", all("ok" in s for s in steps), json.dumps(steps)[:160])
    check("every step explains itself", all(s.get("step") for s in steps), json.dumps(steps)[:160])
    # A person who is NOT shown must always come with the reason. A trace that ends in
    # `shown: false` and no drop_reason is the silent zero this whole panel exists to kill.
    if tr.get("shown") is False:
        check("a person who is not shown always carries a reason",
              bool(tr.get("drop_reason")) or any(s.get("ok") is False for s in steps),
              json.dumps(tr)[:200])
    st, r2 = _req(ADMIN + "/api/admin/explain",
                  data={"self": "Ivan", "intent": dict(INTENT), "candidate": "NoSuchPerson"}, token=TOKEN)
    check("an unknown candidate is an honest miss", (r2 or {}).get("ok") is False, json.dumps(r2)[:120])
    # The mirror question — what this person's own search sees — has to reconcile with the funnel.
    st, r3 = _req(ADMIN + "/api/admin/funnel", data={"self": "Nadia", "intent": dict(INTENT)}, token=TOKEN)
    f = (r3 or {}).get("funnel") or {}
    check("«кого находит сам» reuses the funnel and still balances",
          f and f.get("pool", 0) - f.get("self", 0) - sum((f.get("gates") or {}).values()) == f.get("eligible"),
          json.dumps(f)[:160])


def test_cohorts():
    print("\n[cohorts] the questions a 3000-row table cannot answer")
    st, r = _req(ADMIN + "/api/admin/cohorts", token=TOKEN, timeout=60)
    check("cohorts respond", st == 200 and (r or {}).get("ok"), json.dumps(r)[:120])
    if not (r or {}).get("ok"):
        return
    by = {c["key"]: c for c in r.get("cohorts") or []}
    for k in ("no_interests", "no_intents", "no_age", "no_coords", "paused", "loadtest"):
        check("cohort %s exists" % k, k in by, str(sorted(by.keys())))
    check("cohorts are computed over the RAW store, so they can be ABOUT excluded rows",
          (by.get("loadtest") or {}).get("count", 0) > 0,
          "loadtest=%s of %s" % ((by.get("loadtest") or {}).get("count"), r.get("total")))
    for c in r.get("cohorts") or []:
        if c["count"] and not c["sample"]:
            check("cohort %s names examples" % c["key"], False, "count=%s sample=[]" % c["count"])
    check("every cohort count is within the store", all(c["count"] <= r["total"] for c in r["cohorts"]), "")


def test_proposals_registry():
    print("\n[proposals] declined, expired, revoked-by-policy and never-created look identical outside")
    st, r = _req(ADMIN + "/api/admin/proposals", token=TOKEN)
    check("registry responds", st == 200 and (r or {}).get("ok"), json.dumps(r)[:120])
    if not (r or {}).get("ok"):
        return
    check("registry counts by status", isinstance(r.get("byStatus"), dict), json.dumps(r)[:120])
    check("status counts sum to the total", sum((r.get("byStatus") or {}).values()) == r.get("total"),
          "%s vs %s" % (sum((r.get("byStatus") or {}).values()), r.get("total")))
    for k in ("expiringSoon", "expiredUnanswered", "policyRevoked"):
        check("registry separates %s" % k, isinstance(r.get(k), int), json.dumps(r)[:120])
    for row in (r.get("requests") or [])[:5]:
        check("a request names both sides", bool(row.get("from")) and bool(row.get("to")),
              json.dumps(row)[:140])
        check("a request carries an immutable trace", isinstance(row.get("trace"), list),
              json.dumps(row)[:140])


def test_registry_is_read_only():
    print("\n[proposals] the ledger is written without tmp+replace — a reader that writes truncates it")
    st, a = _req(ADMIN + "/api/admin/proposals", token=TOKEN)
    st, b = _req(ADMIN + "/api/admin/proposals", token=TOKEN)
    check("two consecutive reads agree (nothing mutated in between)",
          (a or {}).get("total") == (b or {}).get("total"),
          "%s vs %s" % ((a or {}).get("total"), (b or {}).get("total")))


def main():
    if not TOKEN:
        print("no admin token: set KLEAL_ADMIN_TOKEN or put admin_token.txt beside users.json")
        return 2
    for fn in (test_auth, test_destructive_routes_gone, test_health_and_store_agreement,
               test_funnel_arithmetic, test_searcher_profile_carries_age, test_stability,
               test_diversity_discriminates, test_engine_separates_topics, test_lab_still_works,
               test_person_card, test_verbs_do_not_fabricate, test_pair_trace, test_cohorts,
               test_proposals_registry, test_registry_is_read_only):
        try:
            fn()
        except Exception as e:
            check("%s crashed" % fn.__name__, False, "%s: %s" % (type(e).__name__, str(e)[:160]))
    print("\n%d checks, %d failed" % (_ran[0], len(_fails)))
    if _fails:
        print("failed: " + ", ".join(_fails))
        return 1
    print("ALL ADMIN TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
