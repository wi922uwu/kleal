# -*- coding: utf-8 -*-
# Acceptance tests for Matching Core v2 (spec "Kleal_Matching_Core_Final_Spec_RU_v2", appendix C).
# Stdlib only, no framework: `python3 services/matching/test_core_v2.py` -> PASS/FAIL lines, exit 1 on failure.
import os, sys, json, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "shared"))
sys.path.insert(0, HERE)

import core_v2
import app  # taxonomy helpers + gates + the match_candidates wrapper

CFG = core_v2.load_config(os.path.join(ROOT, "config", "Kleal_Matching_Core_Config_v2.yaml"))
H = {"topical": app.topical, "cat_of": app.cat_of, "reciprocal": app._reciprocal,
     "role_conflict": app.ROLE_CONFLICT}

BCN = {"coarseLat": 41.3874, "coarseLon": 2.1686}
NEARBY = {"coarseLat": 41.3950, "coarseLon": 2.1750}

FAILURES = []
def check(name, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + name + (("  -- " + str(detail)) if (detail and not cond) else ""))
    if not cond:
        FAILURES.append(name)

def run(intent, prof, cands, ctx=None):
    return core_v2.search(intent, prof, ctx or {}, cands, H, CFG)[0]

def by_name(res, name):
    return next((c for c in res if c["name"] == name), None)

# ---------------------------------------------------------------- fixtures
INTENT_COFFEE = {"type": "social", "topics": ["coffee"], "role": "meet", "mode": "offline",
                 "time": "Today evening"}
PROF_RICH = {"name": "Tester", "vibe": "chill", "geo": BCN, "interests": ["coffee"],
             "languages": {"comfortable": ["en"]}}

FULL = {"name": "Full", "interests": ["coffee"], "vibe": "chill", "langs": ["en"],
        "geo": NEARBY, "open": True}
SPARSE = {"name": "Sparse", "interests": ["coffee"]}

# ---------------------------------------------------------------- appendix C #1: sparse never beats full
res = run(INTENT_COFFEE, PROF_RICH, [FULL, SPARSE])
f, s = by_name(res, "Full"), by_name(res, "Sparse")
check("C1a both direct candidates surface", f is not None and s is not None)
check("C1b full profile outranks sparse (lcb)", f and s and f["lcb"] > s["lcb"],
      (f or {}).get("lcb"))
check("C1c sparse has lower coverage + unknown list", s and s["coverage"] < f["coverage"]
      and len(s["unknowns"]) > len(f["unknowns"]))
check("C1d sparse is flagged, not silently strong", s and (s["band"] != "especially_close"))
check("C1e slate order: full before sparse", res and res[0]["name"] == "Full")

# ---------------------------------------------------------------- appendix C #2: not_applicable != unknown
online = dict(INTENT_COFFEE, mode="online")            # location group -> not_applicable
nogeo = {"name": "NoGeo", "interests": ["coffee"], "vibe": "chill", "langs": ["en"], "open": True}
cov_online = by_name(run(online, PROF_RICH, [nogeo]), "NoGeo")["coverage"]
cov_offline = by_name(run(INTENT_COFFEE, PROF_RICH, [nogeo]), "NoGeo")["coverage"]
check("C2 not_applicable (online) keeps coverage above unknown-geo offline", cov_online > cov_offline,
      (cov_online, cov_offline))

# ---------------------------------------------------------------- appendix C #3: no double count
one = {"name": "One", "interests": ["coffee"], "vibe": "chill", "geo": NEARBY, "open": True, "langs": ["en"]}
dup = {"name": "Dup", "interests": ["coffee", "coffe", "coffees"], "vibe": "chill", "geo": NEARBY,
       "open": True, "langs": ["en"]}                   # alias-ish spellings of the same interest
r = run(INTENT_COFFEE, PROF_RICH, [one, dup])
o, d = by_name(r, "One"), by_name(r, "Dup")
check("C3 aliases of one interest give no extra score", o and d and abs(o["lcb"] - d["lcb"]) < 1e-9,
      ((o or {}).get("lcb"), (d or {}).get("lcb")))

# ---------------------------------------------------------------- appendix C #4: tier is provenance
# pick two same-sub-category words from the live taxonomy (sibling, not exact)
sib_topic = sib_interest = None
for _b, _subs in app.TAXONOMY.items():
    for _s, _ws in _subs.items():
        for _i in range(len(_ws)):
            for _j in range(len(_ws)):
                # true siblings: same sub-category but NOT the same entity (no alias/prefix overlap)
                if _i != _j and not app.same_topic(_ws[_i], _ws[_j]):
                    sib_topic, sib_interest = _ws[_i], _ws[_j]
                    break
            if sib_topic:
                break
        if sib_topic:
            break
    if sib_topic:
        break
sib = {"name": "Sib", "interests": [sib_interest], "vibe": "chill", "geo": NEARBY, "open": True,
       "langs": ["en"]}
r = run({"type": "social", "topics": [sib_topic], "mode": "offline", "time": "Today"},
        PROF_RICH, [sib])
sc = by_name(r, "Sib")
check("C4 sibling stays T2 despite perfect time/geo", (sc is None) or sc["tier"] == "T2",
      (sc or {}).get("tier"))

# ---------------------------------------------------------------- appendix C #5: policy blocks pre-scoring
tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
json.dump([
    {"name": "Good", "interests": ["coffee"], "vibe": "chill", "langs": ["en"], "geo": NEARBY,
     "source": "onboarding"},
    {"name": "Paused", "interests": ["coffee"], "paused": True, "source": "onboarding"},
    {"name": "Minor", "interests": ["coffee"], "age": 16, "source": "onboarding"},
    {"name": "Tester", "interests": ["coffee"], "source": "onboarding"},   # the searcher themselves
], tmp); tmp.close()
old_users, app.USERS_PATH = app.USERS_PATH, tmp.name
app._users_cache = {"mtime": None, "list": None}
wr = app.match_candidates(INTENT_COFFEE, PROF_RICH, {"self": "Tester"})
names = {c["name"] for c in wr}
check("C5a paused candidate never scored", "Paused" not in names, names)
check("C5b under-18 candidate never scored", "Minor" not in names, names)
check("C5c searcher excluded from own results", "Tester" not in names, names)
check("C5d eligible candidate passes gates into core", "Good" in names, names)
check("C5e wrapper returns v2 fields", all(("band" in c and "lcb" in c) for c in wr))
app.USERS_PATH = old_users
app._users_cache = {"mtime": None, "list": None}

# ---------------------------------------------------------------- appendix C #15: T2 outreach needs consent
rich_sib = dict(sib, open=True)
base_int = {"type": "social", "topics": [sib_topic], "mode": "offline", "time": "Today"}
r_no = by_name(run(base_int, PROF_RICH, [rich_sib]), "Sib")
r_yes = by_name(run(dict(base_int, broadConsent=True), PROF_RICH, [rich_sib]), "Sib")
check("C15a parent/sibling candidate: no personal outreach without broad consent",
      (r_no is None) or r_no["can_outreach"] is False, (r_no or {}).get("can_outreach"))
check("C15b tier unchanged by consent flag", (r_yes is None) or r_yes["tier"] == "T2")

# ---------------------------------------------------------------- appendix C #23: reasons = real facts only
r = run(INTENT_COFFEE, {"name": "Empty"}, [SPARSE])     # searcher with no vibe/geo either
sp = by_name(r, "Sparse")
bad = [x for x in ((sp or {}).get("reasons_en") or [])
       if any(w in x for w in ("vibe", "nearby", "open", "role", "format", "constraints"))]
check("C23 no invented reasons for unknown groups", sp is not None and not bad, bad)

# ---------------------------------------------------------------- appendix C #24: determinism / replay
a = json.dumps(run(INTENT_COFFEE, PROF_RICH, [FULL, SPARSE, one, dup]), sort_keys=True)
b = json.dumps(run(INTENT_COFFEE, PROF_RICH, [FULL, SPARSE, one, dup]), sort_keys=True)
check("C24 identical inputs replay to identical slate", a == b)

# ---------------------------------------------------------------- config validator negatives
try:
    core_v2.load_config(os.path.join(ROOT, "config", "Kleal_Matching_Core_Config_v2.yaml"),
                        expect_sha="0" * 64)
    check("V1 sha mismatch rejected", False)
except core_v2.ConfigError:
    check("V1 sha mismatch rejected", True)
tampered = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
with open(os.path.join(ROOT, "config", "Kleal_Matching_Core_Config_v2.yaml"), encoding="utf-8") as fsrc:
    tampered.write(fsrc.read().replace("semantic_activity: 0.18", "semantic_activity: 0.5", 1))
tampered.close()
try:
    core_v2.load_config(tampered.name, expect_sha=None)
    check("V2 broken weight sums rejected", False)
except core_v2.ConfigError:
    check("V2 broken weight sums rejected", True)

# ---------------------------------------------------------------- store-shaped regressions (real users)
STORE = [
    {"name": "ivan", "interests": ["технику apple", "рыбалку", "инсайты"], "vibe": "chill",
     "langs": ["ru"], "geo": BCN, "source": "onboarding"},
    {"name": "Petya", "interests": ["технику apple"], "vibe": "chill", "langs": ["ru"],
     "geo": NEARBY, "source": "onboarding"},
    {"name": "John", "interests": ["dota 2"], "vibe": "chill", "langs": ["en"], "source": "onboarding"},
    {"name": "Burmaldik", "interests": ["пить пиво", "рыбачить"], "vibe": "chill", "langs": ["ru"],
     "source": "onboarding"},
]
T = {"name": "Tester", "vibe": "chill", "geo": BCN}
apple = run({"type": "social", "topics": ["apple", "технику apple"], "mode": "offline",
             "time": "Today"}, T, STORE)
check("R1 apple finds Petya and ivan", {"Petya", "ivan"} <= {c["name"] for c in apple},
      [c["name"] for c in apple])
check("R2 apple does NOT surface John/Burmaldik",
      not ({"John", "Burmaldik"} & {c["name"] for c in apple}))
coffee = run(INTENT_COFFEE, T, STORE)
check("R3 coffee finds nobody (no false John via adjacency)", coffee == [],
      [c["name"] for c in coffee])
dota = run({"type": "gaming", "topics": ["dota", "dota 2"], "role": "play", "mode": "offline",
            "time": "tonight"}, T, STORE)
jd = by_name(dota, "John")
check("R4 dota finds John (direct interest)", jd is not None and jd["tier"] in ("T0", "T1"),
      [c["name"] for c in dota])
check("R5 sparse games data -> honest needs_clarification, no auto-outreach",
      jd is not None and jd["band"] == "needs_clarification" and jd["can_outreach"] is False,
      (jd or {}).get("band"))
beer = run({"type": "social", "topics": ["пиво", "beer"], "mode": "offline", "time": "Today"}, T, STORE)
check("R6 пиво finds Burmaldik (raw-word fallback)", by_name(beer, "Burmaldik") is not None,
      [c["name"] for c in beer])
apple_srt = [c["name"] for c in apple]
check("R7 bands sort before clarification cases",
      all(core_v2.BAND_RANK[apple[i]["band"]] <= core_v2.BAND_RANK[apple[i + 1]["band"]]
          for i in range(len(apple) - 1)), apple_srt)

print()
if FAILURES:
    print("FAILED: %d test(s): %s" % (len(FAILURES), ", ".join(FAILURES)))
    sys.exit(1)
print("ALL TESTS PASSED (%s, config %s)" % ("core v2", CFG["config_version"]))
