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


def main():
    if not TOKEN:
        print("no admin token: set KLEAL_ADMIN_TOKEN or put admin_token.txt beside users.json")
        return 2
    for fn in (test_auth, test_destructive_routes_gone, test_health_and_store_agreement,
               test_funnel_arithmetic, test_searcher_profile_carries_age, test_stability,
               test_diversity_discriminates, test_engine_separates_topics, test_lab_still_works):
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
