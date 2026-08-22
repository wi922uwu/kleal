# -*- coding: utf-8 -*-
import os
# This harness ranks AGAINST the synthetic load pool, which live matching now excludes.
os.environ.setdefault("KLEAL_INCLUDE_LOADTEST", "1")
# Мост тем: слепок выученных фраз как фикстура. Без него харнесс мерил движок, который в проде не
# существует, — кросс-языковые связки (кофе<->coffee) живут в выученном, а не в каноне.
os.environ.setdefault("KLEAL_PHRASE_TOPICS",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)), "phrase_topics.seed.json"))

"""Property-based fuzzer for the matching engine (in-process, deterministic by --seed).

Three layers on top of the gold battery:
  1. RANDOM SWEEP — thousands of randomized intents x searcher profiles (RU/EN/mixed/garbage
     topics, every gate parameter, hostile strings) with the hard invariants checked on EVERY
     slate: gates, outreach rules, self-exclusion, bounded scores, valid enums, slate cap.
  2. METAMORPHIC PAIRS — relations that must hold between two related searches:
     verifiedOnly / requiredLanguages / age windows / exactMatchRequired only ever FILTER
     (every returned candidate satisfies the constraint, and no new violator appears);
     broadConsent may only ADD outreach permissions on T2, never change scores.
  3. PERMUTATION — shuffling the stored pool order must not change the slate (total sort order).

Usage: python3 tools/fuzz_matching.py --pool P.json --index I.json [--n 3000] [--seed 7]
Exit 0 iff zero violations. Prints one repro line per violation class.
"""
import argparse, json, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "shared"))
sys.path.insert(0, os.path.join(ROOT, "services", "matching"))
os.environ.setdefault("KLEAL_STORE", "/tmp/fuzz_kleal_store.json")

import app        # noqa: E402
import core_v2    # noqa: E402

NOW_DAY, NOW_NIGHT = 1752600000.0, 1752613200.0

TOPICS_REAL = ["кофе", "coffee", "dota 2", "дота", "падель", "padel", "футбол", "испанский",
               "стартапы", "ai", "прогулка", "книги", "кино", "пиво", "рыбалка", "шахматы",
               "смотреть футбол", "коворкинг", "хайкинг", "йога", "теннис", "labubu",
               "технику apple", "мате", "английский", "продакт", "бег", "сериалы"]
TOPICS_JUNK = ["", " ", "x", "zzqw", "😀🔥", "<script>alert(1)</script>", "'; DROP TABLE users;--",
               "a" * 300, "кофе coffee", "123456", "null", "None", "прив", "ъь"]
TYPES = ["social", "gaming", "sport", "language", "networking", "dating", "dinner", "other", "banana", ""]
ROLES = ["meet", "play", "watch", "discuss", "practise", "attend", "", "pilot"]
MODES = ["offline", "online", "", "banana"]
TIMES = ["Today evening", "tonight", "Tomorrow", "This weekend", "Flexible", "", "когда-нибудь", "25:99"]
GEOS = [{"coarseLat": 41.391, "coarseLon": 2.164}, {"coarseLat": 40.416, "coarseLon": -3.703},
        None, {"coarseLat": "oops", "coarseLon": []}]
BANDS = set(core_v2.BAND_RANK)
READY = set(core_v2.READINESS_RANK)

def rnd_intent(r):
    nt = r.choice([0, 1, 1, 1, 2, 2, 3, 4])
    pool = TOPICS_REAL if r.random() < 0.8 else TOPICS_JUNK
    it = {"topics": [r.choice(pool) for _ in range(nt)],
          "type": r.choice(TYPES), "role": r.choice(ROLES),
          "mode": r.choice(MODES), "time": r.choice(TIMES)}
    if r.random() < 0.15: it["verifiedOnly"] = True
    if r.random() < 0.15: it["requiredLanguages"] = r.sample(["ru", "en", "es", "de", "zz"], r.randint(1, 2))
    if r.random() < 0.15:
        lo = r.choice([-5, 16, 18, 25, 30, 40])
        it["minAge"], it["maxAge"] = lo, r.choice([None, lo - 2, lo + 5, 99])
    if r.random() < 0.10: it["radiusKm"] = r.choice([-5, 0, 1, 15, 99999])
    if r.random() < 0.10: it["exactMatchRequired"] = True
    if r.random() < 0.10: it["adjacentAllowed"] = False
    if r.random() < 0.15: it["broadConsent"] = True
    return it

def rnd_prof(r, names):
    p = {"name": r.choice(["Tester", "ТЕСТЕР", r.choice(names), r.choice(names).upper(), "a" * 200, ""]),
         "vibe": r.choice(["chill", "party", "", None]), "geo": r.choice(GEOS)}
    if r.random() < 0.5:
        p["languages"] = {"comfortable": r.sample(["ru", "en", "es"], r.randint(0, 2))}
    return p

def check_slate(res, it, prof, users, tag_of, viol, repro):
    lname = str(prof.get("name") or "").strip().lower()
    seen = set()
    if len(res) > 8:
        viol("SLATE>8", repro)
    for c in res:
        nm = c.get("name")
        if nm in seen:
            viol("DUPLICATE", repro + " :: " + str(nm))
        seen.add(nm)
        u = users.get(nm, {})
        t = tag_of.get(nm, set())
        if str(nm or "").strip().lower() == lname and lname:
            viol("SELF", repro + " :: " + str(nm))
        if {"minor_16", "paused_user", "blocker", "overloaded", "declined_cd"} & t:
            viol("GATE:" + sorted({"minor_16", "paused_user", "blocker", "overloaded", "declined_cd"} & t)[0],
                 repro + " :: " + str(nm))
        if it.get("verifiedOnly") and not u.get("verified"):
            viol("FILTER:verifiedOnly", repro + " :: " + str(nm))
        reql = {str(l)[:2].lower() for l in (it.get("requiredLanguages") or [])}
        if reql and not reql.issubset({str(l)[:2].lower() for l in (u.get("langs") or [])}):
            viol("FILTER:requiredLanguages", repro + " :: " + str(nm))
        mn, mx = it.get("minAge"), it.get("maxAge")
        if (mn or mx) and isinstance(u.get("age"), int):
            if (mn and u["age"] < mn) or (mx and u["age"] > mx):
                viol("FILTER:ageWindow", repro + " :: " + str(nm))
        if it.get("exactMatchRequired") and c.get("tier") not in ("T0", "T1"):
            viol("FILTER:exactMatch tier=" + str(c.get("tier")), repro + " :: " + str(nm))
        if it.get("adjacentAllowed") is False and c.get("tier") == "T3":
            viol("FILTER:adjacentAllowed", repro + " :: " + str(nm))
        if c.get("can_outreach"):
            if c.get("readiness") != "open_now":
                viol("OUTREACH:not-open", repro + " :: " + str(nm))
            if c.get("tier") not in ("T0", "T1") and not it.get("broadConsent"):
                viol("OUTREACH:tier-consent", repro + " :: " + str(nm))
        lcb, cov, sc = c.get("lcb"), c.get("coverage"), c.get("score")
        if not (isinstance(lcb, (int, float)) and 0 <= lcb <= 1) or \
           not (isinstance(cov, (int, float)) and 0 <= cov <= 1):
            viol("RANGE:lcb/coverage", repro + " :: " + str(nm))
        elif abs(sc - round(lcb * 100, 1)) > 0.01:
            viol("RANGE:score!=lcb*100", repro + " :: " + str(nm))
        if c.get("band") not in BANDS:
            viol("ENUM:band=" + str(c.get("band")), repro + " :: " + str(nm))
        if c.get("readiness") not in READY:
            viol("ENUM:readiness=" + str(c.get("readiness")), repro + " :: " + str(nm))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True)
    ap.add_argument("--index", required=True)
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    app.USERS_PATH = a.pool
    app._users_cache = {"mtime": None, "list": None}
    with open(a.pool, encoding="utf-8") as f:
        pool = json.load(f)["users"]
    users = {u["name"]: u for u in pool}
    with open(a.index, encoding="utf-8") as f:
        index = json.load(f)
    tag_of = {}
    for t, ns in index.items():
        for n in ns:
            tag_of.setdefault(n, set()).add(t)
    names = list(users)
    r = random.Random(a.seed)
    stats = {}
    def viol(kind, repro):
        stats.setdefault(kind, []).append(repro)
    crashes = 0
    # ---- 1. random sweep ----
    for i in range(a.n):
        it, prof = rnd_intent(r), rnd_prof(r, names)
        now = r.choice([NOW_DAY, NOW_NIGHT, NOW_DAY + r.random() * 86400])
        repro = "i=%d" % i
        try:
            res = app.match_candidates(it, prof, {"self": prof.get("name", ""), "now": now})
        except Exception as ex:
            crashes += 1
            viol("CRASH:" + type(ex).__name__, repro + " :: " + json.dumps(it, ensure_ascii=False)[:160])
            continue
        check_slate(res, it, prof, users, tag_of, viol, repro)
        if i % 500 == 0:   # sampled determinism
            res2 = app.match_candidates(it, prof, {"self": prof.get("name", ""), "now": now})
            if json.dumps(res, sort_keys=True) != json.dumps(res2, sort_keys=True):
                viol("NON-DETERMINISTIC", repro)
    # ---- 2. metamorphic pairs ----
    for i in range(300):
        base = {"topics": [r.choice(TOPICS_REAL) for _ in range(r.randint(1, 2))],
                "type": r.choice(["social", "gaming", "sport", "language", "networking"]),
                "role": "meet", "mode": "offline", "time": "Today evening"}
        prof = {"name": "Tester", "vibe": "chill", "geo": GEOS[0]}
        ctx = {"self": "Tester", "now": NOW_DAY}
        repro = "m=%d %s" % (i, base["topics"])
        try:
            r0 = app.match_candidates(dict(base), prof, dict(ctx))
            rc = app.match_candidates(dict(base, broadConsent=True), prof, dict(ctx))
        except Exception as ex:
            crashes += 1
            viol("CRASH-M:" + type(ex).__name__, repro)
            continue
        s0 = {c["name"]: c for c in r0}
        for c in rc:                       # consent must not change relevance, only unlock T2 outreach
            b = s0.get(c["name"])
            if b and (abs(b["lcb"] - c["lcb"]) > 1e-9 or b["band"] != c["band"]):
                viol("CONSENT-CHANGES-SCORE", repro + " :: " + c["name"])
            if b and b.get("can_outreach") and not c.get("can_outreach"):
                viol("CONSENT-REVOKES-OUTREACH", repro + " :: " + c["name"])
    # ---- 3. permutation invariance ----
    base_it = {"topics": ["кофе"], "type": "social", "role": "meet", "mode": "offline", "time": "Today"}
    prof = {"name": "Tester", "vibe": "chill", "geo": GEOS[0]}
    ref = app.match_candidates(base_it, prof, {"self": "Tester", "now": NOW_DAY})
    ref_names = [c["name"] for c in ref]
    for k in range(3):
        shuf = list(pool)
        random.Random(100 + k).shuffle(shuf)
        alt_path = "/tmp/fuzz_pool_shuf%d.json" % k
        with open(alt_path, "w", encoding="utf-8") as f:
            json.dump({"users": shuf}, f, ensure_ascii=False)
        app.USERS_PATH = alt_path
        app._users_cache = {"mtime": None, "list": None}
        alt = app.match_candidates(base_it, prof, {"self": "Tester", "now": NOW_DAY})
        if [c["name"] for c in alt] != ref_names:
            viol("PERMUTATION", "shuffle=%d %s vs %s" % (k, [c["name"] for c in alt][:4], ref_names[:4]))
    app.USERS_PATH = a.pool
    app._users_cache = {"mtime": None, "list": None}
    # ---- report ----
    total = sum(len(v) for v in stats.values())
    print("fuzz: %d searches + 300 metamorphic + 3 permutations | violations: %d | crashes: %d"
          % (a.n, total, crashes))
    for kind in sorted(stats):
        v = stats[kind]
        print("  %-28s x%-4d e.g. %s" % (kind, len(v), v[0][:140]))
    sys.exit(1 if total else 0)

if __name__ == "__main__":
    main()
