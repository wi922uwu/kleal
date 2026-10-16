# -*- coding: utf-8 -*-
import os
# This harness ranks AGAINST the synthetic load pool, which live matching now excludes.
os.environ.setdefault("KLEAL_INCLUDE_LOADTEST", "1")
# Мост тем: слепок выученных фраз как фикстура. Без него харнесс мерил движок, который в проде не
# существует, — кросс-языковые связки (кофе<->coffee) живут в выученном, а не в каноне.
os.environ.setdefault("KLEAL_PHRASE_TOPICS",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)), "phrase_topics.seed.json"))

"""Matching-quality evaluation harness (gold battery over the loadtest pool).

Runs spec-derived scenarios (§18 domain cases + gates/readiness/honesty invariants) against the
REAL matching service code (in-process import of services/matching/app.py — same file the pod
runs), on the deterministic pool from tools/gen_test_users.py. Expectations reference recipe TAGS,
so the battery survives regeneration.

Usage:
  python3 tools/eval_matching.py --pool P.json --index I.json [--battery extra.json] [--json out.json]
                                 [--once] [--snapshot before.json] [--compare before.json]

Before/after: run once with --snapshot before.json on the old code, then on the new code with
--compare before.json; the DRIFT line names every scenario whose ranking view changed. Determinism
across processes is the same command run twice: a clean --compare is the proof.

Per-scenario checks: include_any / exclude / top1 / order / forbid_outreach / nonempty / tier caps.
Global invariants on EVERY result: no minors, no paused, no blockers, no self, determinism,
outreach only at open_now + T0/T1 (or T2+consent), score==lcb*100, band fields present.
Exit 0 only when every scenario and invariant passes.
"""
import argparse, json, os, shutil, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "shared"))
sys.path.insert(0, os.path.join(ROOT, "services", "matching"))

# EVERY RUN OWNS ITS STATE. The store used to default to one shared /tmp file that survived between
# runs, so run N started with whatever run N-1 had left in it (exposure, outcomes, write-dedup keys)
# and "the same code" never saw the same input twice. A fresh directory per process closes that; an
# explicit KLEAL_STORE still wins for anyone who wants to replay against a captured store.
# The phrase fixture is COPIED for the same reason: the engine rewrites its phrase file atomically
# (learn_phrases) and must never be able to touch the committed seed.
_RUN_DIR = tempfile.mkdtemp(prefix="eval_matching_")
# THE DB MODE IS PART OF THE STATE. With the production environment loaded (KLEAL_DB=postgres) the
# temp store above is ignored and the engine reads the LIVE user table — the slate fills with real
# people the tag index has never heard of, and 98 of 108 scenarios fail on MISS. Measured
# 2026-09-14. A harness ranks its own pool, so the json store is forced, not defaulted.
os.environ["KLEAL_DB"] = "json"
os.environ.setdefault("KLEAL_STORE", os.path.join(_RUN_DIR, "store.json"))
_SEED = os.environ["KLEAL_PHRASE_TOPICS"]
if os.path.exists(_SEED):
    shutil.copy(_SEED, os.path.join(_RUN_DIR, "phrase_topics.json"))
    os.environ["KLEAL_PHRASE_TOPICS"] = os.path.join(_RUN_DIR, "phrase_topics.json")

import app        # noqa: E402  (matching service; safe to import — server starts only under __main__)
import core_v2    # noqa: E402

NOW_OPEN = 1752600000.0    # local (UTC+120) 19:20 — open hours
NOW_QUIET = 1752613200.0   # local 23:00 — inside default quiet window

# ---------------------------------------------------------------- seed battery (spec §18 + edges)
def _i(topics, typ="social", role="meet", mode="offline", time_="Today evening", **kw):
    d = {"topics": topics, "type": typ, "role": role, "mode": mode, "time": time_}
    d.update(kw)
    return d

TESTER = {"name": "Tester", "vibe": "chill", "geo": {"coarseLat": 41.391, "coarseLon": 2.164},
          "languages": {"comfortable": ["ru", "en"]}, "interests": []}

SEED_BATTERY = [
    # --- games (§18.2) ---
    dict(id="g1_dota_ru", intent=_i(["дота", "dota 2"], "gaming", "play", time_="tonight"),
         expect=dict(include_any=["dota_active"], top1=["dota_active", "dota_interest"],
                     forbid_outreach=["lol_only", "valorant_cs"], order=[["dota_active", "lol_only"]])),
    dict(id="g2_dota_en", intent=_i(["dota 2", "ranked"], "gaming", "play", time_="tonight"),
         expect=dict(include_any=["dota_active"], forbid_outreach=["lol_only"],
                     order=[["dota_active", "lol_only"]])),
    dict(id="g3_chess_ru", intent=_i(["шахматы"], "gaming"),
         expect=dict(include_any=["chess_board"], exclude=["dota_active", "valorant_cs"])),
    dict(id="g4_fifa_ru", intent=_i(["фифа", "приставка"], "gaming", "play"),
         expect=dict(include_any=["fifa_console"])),
    # --- sport (§18.6 падель) ---
    dict(id="s1_padel", intent=_i(["падель", "padel"], "sport", "play", time_="Tomorrow 19:00"),
         expect=dict(include_any=["padel"], top1=["padel"], forbid_outreach=["tennis"])),
    dict(id="s2_football_ru", intent=_i(["футбол"], "sport", "play"),
         expect=dict(include_any=["football_play"], order=[["football_play", "barca_fans"]])),
    dict(id="s3_running", intent=_i(["бег"], "sport", "play", time_="Tomorrow 08:00"),
         expect=dict(include_any=["running"])),
    dict(id="s4_yoga", intent=_i(["йога"], "sport", "practise"),
         expect=dict(include_any=["yoga"])),
    # --- language exchange (§18.4) ---
    dict(id="l1_spanish_ru", intent=_i(["испанский", "практика языка"], "language", "practise"),
         expect=dict(include_any=["spanish_native"],
                     order=[["spanish_native", "spanish_learner"]])),
    dict(id="l2_english", intent=_i(["английский", "разговорный клуб"], "language", "practise"),
         expect=dict(include_any=["english_club"])),
    # --- culture (§18.6) ---
    dict(id="c1_macba", intent=_i(["выставка", "macba", "art"], time_="Saturday"),
         expect=dict(include_any=["art_museum"])),
    dict(id="c2_cinema_ru", intent=_i(["кино"]),
         expect=dict(include_any=["cinema"])),
    dict(id="c3_books_coffee", intent=_i(["книги", "кофе"]),
         expect=dict(include_any=["books"])),
    # --- social ---
    dict(id="so1_coffee_ru", intent=_i(["кофе"]),
         expect=dict(include_any=["coffee_ru", "coffee_en"], exclude=["dota_interest", "fishing"],
                     cross_lang=["coffee_en"])),
    dict(id="so2_coffee_en", intent=_i(["coffee"]),
         expect=dict(include_any=["coffee_en"], exclude=["dota_interest"], cross_lang=["coffee_ru"])),
    dict(id="so3_walk_eixample", intent=_i(["прогулка", "погулять"], time_="Today evening"),
         # dating_closed people with "прогулки" interests are ordinary walkers — legit winners too
         expect=dict(include_any=["walk_eixample"],
                     top1=["walk_eixample", "dating_open", "dating_closed"])),
    dict(id="so4_beer_ru", intent=_i(["пиво"], time_="tonight"),
         expect=dict(include_any=["beer_pub"])),
    # --- professional networking (§18.5) ---
    dict(id="n1_ai_founders", intent=_i(["стартапы", "ai", "кофе"], "networking", "discuss"),
         expect=dict(include_any=["founder_ai"], top1=["founder_ai", "dev_it", "product_ux"])),
    dict(id="n2_product", intent=_i(["продакт", "ux"], "networking", "discuss"),
         expect=dict(include_any=["product_ux"])),
    # --- watch together (§18.6 Барса) ---
    dict(id="w1_barca", intent=_i(["смотреть футбол", "барса"], time_="tonight"),
         expect=dict(include_any=["barca_fans"], order=[["barca_fans", "football_play"]])),
    # --- outdoors ---
    dict(id="o1_fishing_ru", intent=_i(["рыбалка"], time_="This weekend"),
         expect=dict(include_any=["fishing"], exclude=["coffee_en", "dota_interest"])),
    dict(id="o2_hiking", intent=_i(["хайкинг", "горы"], time_="This weekend"),
         expect=dict(include_any=["hiking"])),
    # --- coworking (§18.6) ---
    dict(id="cw1_cowork", intent=_i(["коворкинг", "поработать"], time_="Tomorrow morning"),
         expect=dict(include_any=["cowork_poblenou"])),
    # --- dating isolation (§17) ---
    # dating requires a known adult age on BOTH sides (spec §17) — hence the explicit profile
    dict(id="d1_dating_gate", intent=_i(["прогулки", "кино"], "dating"),
         profile=dict(TESTER, age=30),
         expect=dict(only_dating_ok=True, include_any=["dating_open"])),
    dict(id="d2_dating_no_age", intent=_i(["прогулки", "кино"], "dating"),
         expect=dict(empty=True)),                    # searcher age unknown -> fail closed
    dict(id="d3_dating_minor", intent=_i(["прогулки", "кино"], "dating"),
         profile=dict(TESTER, age=15), expect=dict(empty=True)),   # minor never reaches adults
    # --- off-taxonomy honesty ---
    dict(id="ot1_apple", intent=_i(["технику apple", "apple"]),
         expect=dict(include_any=["apple_tech"], exclude=["dev_it", "mate_tea", "labubu"])),
    dict(id="ot2_labubu", intent=_i(["labubu"]),
         expect=dict(include_any=["labubu"], exclude=["apple_tech"])),
    dict(id="ot3_mate", intent=_i(["мате"]),
         expect=dict(include_any=["mate_tea"], exclude=["coffee_ru"])),
    # --- readiness / receiving (§10.1) ---
    dict(id="gr1_busy_visible", intent=_i(["падель", "padel"], "sport", "play"),
         expect=dict(no_outreach_tags_if_present=["busy_user", "no_policy"])),
    dict(id="gr2_quiet_hours", intent=_i(["кофе"]), now=NOW_QUIET,
         expect=dict(readiness_at_most=dict(night_quiet="open_later"))),
    dict(id="gr3_domain_scoped_games", intent=_i(["dota 2"], "gaming", "play"),
         expect=dict(readiness_exact=dict(games_only_recv="open_now"))),
    dict(id="gr3b_domain_scoped_coffee", intent=_i(["coffee"]),
         expect=dict(readiness_exact=dict(games_only_recv="passive_discovery"))),
    # --- sparse honesty (§9, acceptance #1) ---
    dict(id="sp1_sparse_flagged", intent=_i(["coffee"]),
         expect=dict(sparse_below_full=("sparse_one", "coffee_en"))),
]

# ---------------------------------------------------------------- engine glue
def load_pool(pool_path):
    app.USERS_PATH = pool_path
    app._users_cache = {"mtime": None, "list": None}
    with open(pool_path, encoding="utf-8") as f:
        users = json.load(f)["users"]
    return users

def run_match(intent, prof, now):
    t0 = time.perf_counter()
    out = app.match_candidates(intent, prof, {"self": prof.get("name", ""), "now": now})
    return out, (time.perf_counter() - t0) * 1000.0

def explain_slate(cx, sc, prof, now, top=8):
    """The per-feature breakdown behind a slate — the same explain_match the admin diagnostic uses.

    An ORDER or TOP1 failure names WHO is out of place, not WHY. Reading the engine by hand for
    that is slow and error-prone (and was, twice); this prints, per person, what each feature group
    contributed and what evidence it saw, next to the pool tags the expectation was written in."""
    ex = app.explain_match(sc["intent"], prof, {"self": prof.get("name", ""), "now": now})
    if ex.get("self_gate"):
        print("      explain: searcher gated — %s" % ex["self_gate"]); return
    rows = ex.get("matched") or []
    # explain_match sorts by (band, readiness, -reciprocal, -lcb, -coverage, name); the real slate adds
    # decision class and rotation on top, so the ORDER here is close to but not identical to the slate.
    print("      explain %s [%s]: %d matched, %d considered, %d excluded" %
          (sc["id"], ex.get("domain"), len(rows), len(ex.get("considered") or []), len(ex.get("excluded") or [])))
    for m in rows[:top]:
        t = ",".join(sorted(tags(cx, m["name"])))[:40]
        ab, ba = m.get("a_to_b") or {}, m.get("b_to_a") or {}
        print("      %-18s %-3s %-18s A->B lcb=%.3f mean=%.3f cov=%.2f | B->A lcb=%.3f cov=%.2f | recip=%.3f  [%s]" %
              (m["name"], m.get("tier"), m.get("band"),
               float(ab.get("lcb") or 0), float(ab.get("mean") or 0), float(ab.get("coverage") or 0),
               float(ba.get("lcb") or 0), float(ba.get("coverage") or 0), float(m.get("reciprocal") or 0), t))
        for r in (ab.get("features") or []):
            if r["state"] == "not_applicable":
                continue
            print("         %-22s %-13s v=%-6s w=%-5s +%-7s %s" %
                  (r["group"], r["state"], r["value"], r["weight"], r["contribution"], str(r.get("detail") or "")[:44]))


# THE RANKING VIEW IS THE CONTRACT — not the whole card. Every check below reads exactly these
# fields, and the engine documents that other card fields may legitimately differ between two
# identical calls (allocation_trace: "exposure_count/fatigue_state legitimately VARY ... any
# full-card / replay diff MUST exclude it"). Comparing full cards is how a wall-clock stamp in one
# evidence field once marked 100 of 108 scenarios NON-DETERMINISTIC while names, tiers and scores
# were byte-identical. Determinism and before/after drift are judged on this view only.
RANK_KEYS = ("name", "tier", "band", "score", "can_outreach", "readiness")

def rank_view(res):
    return [[c.get(k) for k in RANK_KEYS] for c in res]

# ---------------------------------------------------------------- checks
class Ctx:
    def __init__(self, users, index):
        self.tag_of = {}
        for tag, names in index.items():
            for n in names:
                self.tag_of.setdefault(n, set()).add(tag)
        self.index = index
        self.users = {u["name"]: u for u in users}

def tags(cx, name):
    return cx.tag_of.get(name, set())

def evaluate(cx, sc, res):
    """-> list of failure strings for one scenario."""
    F = []
    e = sc.get("expect") or {}
    names = [c["name"] for c in res]
    byname = {c["name"]: c for c in res}
    have_tag = lambda t: [n for n in names if t in tags(cx, n)]
    # scenario-specific
    for t in e.get("include_any", []):
        if not have_tag(t):
            F.append("MISS include_any:%s (0 of %d in slate)" % (t, len(cx.index.get(t, []))))
    for t in e.get("exclude", []):
        hit = have_tag(t)
        if hit:
            F.append("FALSE-MATCH exclude:%s -> %s" % (t, hit[:3]))
    for t in e.get("cross_lang", []):
        if not have_tag(t):
            F.append("CROSS-LANG-MISS %s (RU<->EN vocabulary gap)" % t)
    if e.get("top1") and names:
        if not (tags(cx, names[0]) & set(e["top1"])):
            F.append("TOP1 %s has tags %s, wanted %s" % (names[0], sorted(tags(cx, names[0])), e["top1"]))
    for a, b in e.get("order", []):
        ia = min((names.index(n) for n in have_tag(a)), default=None)
        ib = min((names.index(n) for n in have_tag(b)), default=None)
        if ia is not None and ib is not None and ia > ib:
            F.append("ORDER %s(#%d) below %s(#%d)" % (a, ia, b, ib))
    for t in e.get("forbid_outreach", []):
        bad = [n for n in have_tag(t) if byname[n].get("can_outreach")]
        if bad:
            F.append("OUTREACH-VIOLATION %s -> %s" % (t, bad[:3]))
    for t in e.get("no_outreach_tags_if_present", []):
        bad = [n for n in have_tag(t) if byname[n].get("can_outreach")]
        if bad:
            F.append("OUTREACH-VIOLATION(readiness) %s -> %s" % (t, bad[:3]))
    for t, st in (e.get("readiness_exact") or {}).items():
        for n in have_tag(t):
            if byname[n].get("readiness") != st:
                F.append("READINESS %s: %s got %s want %s" % (t, n, byname[n].get("readiness"), st))
    for t, st in (e.get("readiness_at_most") or {}).items():
        for n in have_tag(t):
            if byname[n].get("readiness") not in (st,):
                F.append("READINESS %s: %s got %s want %s" % (t, n, byname[n].get("readiness"), st))
    if e.get("nonempty") and not names:
        F.append("EMPTY result")
    if e.get("empty") and names:
        F.append("EXPECTED EMPTY, got %s" % names[:3])
    if e.get("only_dating_ok"):
        bad = [n for n in names if not cx.users.get(n, {}).get("datingOk")]
        if bad:
            F.append("DATING-LEAK non-datingOk in dating search: %s" % bad[:3])
    if e.get("sparse_below_full"):
        sp, full = e["sparse_below_full"]
        isp = min((names.index(n) for n in have_tag(sp)), default=None)
        ifl = min((names.index(n) for n in have_tag(full)), default=None)
        if isp is not None:
            c = byname[names[isp]]
            if not c.get("unknowns"):
                F.append("SPARSE not flagged with unknowns: %s" % names[isp])
            if ifl is not None and isp < ifl:
                F.append("SPARSE %s outranks full %s" % (names[isp], names[ifl]))
    return F

def invariants(cx, sc, res, prof):
    """Hard, scenario-independent rules (spec gates + presentation contract)."""
    F = []
    for c in res:
        u = cx.users.get(c["name"], {})
        t = tags(cx, c["name"])
        if "minor_16" in t:
            F.append("GATE minor in results: %s" % c["name"])
        if "paused_user" in t:
            F.append("GATE paused in results: %s" % c["name"])
        if "blocker" in t:
            F.append("GATE blocker in results: %s" % c["name"])
        if "overloaded" in t:
            F.append("GATE overloaded(pending>=6) in results: %s" % c["name"])
        if c["name"] == prof.get("name"):
            F.append("SELF-MATCH: %s" % c["name"])
        if c.get("can_outreach"):
            if c.get("readiness") != "open_now":
                F.append("OUTREACH w/o open_now: %s (%s)" % (c["name"], c.get("readiness")))
            if c.get("tier") not in ("T0", "T1") and not sc.get("intent", {}).get("broadConsent"):
                F.append("OUTREACH at %s w/o consent: %s" % (c.get("tier"), c["name"]))
        if abs((c.get("score") or 0) - round((c.get("lcb") or 0) * 100, 1)) > 0.01:
            F.append("SCORE!=lcb*100: %s" % c["name"])
        for k in ("band", "band_ru", "readiness", "reasons_ru", "tier"):
            if k not in c:
                F.append("FIELD missing %s: %s" % (k, c["name"]))
                break
    return F

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True)
    ap.add_argument("--index", required=True)
    ap.add_argument("--battery", action="append", default=[],
                    help="extra battery JSON files (list of scenario dicts)")
    ap.add_argument("--json", default=None, help="write machine-readable results here")
    ap.add_argument("--only", default=None, help="comma-separated scenario ids")
    ap.add_argument("--once", action="store_true",
                    help="call the engine once per scenario (skips the in-process determinism check)")
    ap.add_argument("--snapshot", default=None,
                    help="write the ranking view of every scenario here (the 'before' of a before/after)")
    ap.add_argument("--compare", default=None,
                    help="a previous --snapshot; scenarios whose ranking view changed are listed as DRIFT")
    ap.add_argument("--explain", default=None,
                    help="comma-separated scenario ids: print the top-8 with per-feature contributions "
                         "(explain_match, the same engine) — the 'why' behind an ORDER/TOP1 failure")
    a = ap.parse_args()
    users = load_pool(a.pool)
    with open(a.index, encoding="utf-8") as f:
        index = json.load(f)
    cx = Ctx(users, index)
    battery = list(SEED_BATTERY)
    for path in a.battery:
        with open(path, encoding="utf-8") as f:
            battery += json.load(f)
    if a.only:
        keep = set(a.only.split(","))
        battery = [s for s in battery if s["id"] in keep]
    results, failures, lat = [], [], []
    snapshot, total_cards = {}, 0
    for sc in battery:
        prof = sc.get("profile") or TESTER
        now = sc.get("now") or NOW_OPEN
        try:
            res, ms = run_match(sc["intent"], prof, now)
            if a.once:
                det = True
            else:
                res2, _ = run_match(sc["intent"], prof, now)
                det = rank_view(res) == rank_view(res2)
        except Exception as ex:
            failures.append((sc["id"], ["CRASH: %r" % ex]))
            results.append(dict(id=sc["id"], crash=repr(ex)))
            continue
        lat.append(ms)
        F = evaluate(cx, sc, res) + invariants(cx, sc, res, prof)
        if not det:
            F.append("NON-DETERMINISTIC result")
        status = "PASS" if not F else "FAIL"
        print("%-5s %-24s %2d cand %6.1fms  %s" %
              (status, sc["id"], len(res), ms, ("; ".join(F[:3]) if F else "")))
        results.append(dict(id=sc["id"], ok=not F, failures=F, ms=round(ms, 1),
                            slate=[(c["name"], c.get("tier"), c.get("band"), c.get("readiness"),
                                    c.get("can_outreach")) for c in res[:8]]))
        snapshot[sc["id"]] = rank_view(res)
        total_cards += len(res)
        if a.explain and sc["id"] in set(a.explain.split(",")):
            explain_slate(cx, sc, prof, now)
        if F:
            failures.append((sc["id"], F))
    # --- ranking granularity guard -------------------------------------------------------------
    # Distinct scores per slate. When this collapses, the top-8 order becomes arbitrary and the
    # "best" person is not distinguishable (it was 42% before the continuous-distance fix).
    gr_c = gr_d = 0
    PROBES = [["кофе"], ["coffee"], ["дота", "dota 2"], ["падель"], ["футбол"], ["книги"],
              ["испанский"], ["стартапы", "ai"], ["прогулка"], ["кино"], ["хайкинг"], ["рыбалка"],
              ["пиво"], ["йога"], ["шахматы"], ["коворкинг"], ["фотография"], ["бег"]]
    worst = ("", 0, 0)
    for topics in PROBES:
        res, _ms = run_match({"topics": topics, "type": "social", "role": "meet",
                              "mode": "offline", "time": "Today evening"}, TESTER, NOW_OPEN)
        if len(res) < 3:
            continue
        scores = [c.get("score") for c in res]
        d = len(set(scores))
        gr_c += len(scores); gr_d += d
        if worst[1] == 0 or d < worst[1]:
            worst = (topics[0], d, len(scores))
    gran = 100.0 * gr_d / max(1, gr_c)
    GRAN_MIN = 70.0
    gran_ok = gran >= GRAN_MIN
    print("\n%-5s granularity: %.0f%% distinct scores (min %.0f%%) | worst probe '%s': %d/%d distinct"
          % ("PASS" if gran_ok else "FAIL", gran, GRAN_MIN, worst[0], worst[1], worst[2]))
    if not gran_ok:
        failures.append(("ranking_granularity",
                         ["granularity %.0f%% below %.0f%% — slates tie and order is arbitrary" % (gran, GRAN_MIN)]))
        results.append(dict(id="ranking_granularity", ok=False,
                            failures=["granularity %.0f%%" % gran]))
    else:
        results.append(dict(id="ranking_granularity", ok=True, granularity=round(gran, 1)))

    # A HARNESS MUST FAIL, NOT SWALLOW. A run whose every slate came back empty measured nothing —
    # once that happened silently: a wrong `now` type made every call raise inside a try/except,
    # and "ranking unchanged" was really "the same error text twice".
    if battery and total_cards == 0:
        failures.append(("snapshot_empty", ["SNAPSHOT EMPTY: every slate empty — measuring nothing"]))
        results.append(dict(id="snapshot_empty", ok=False, failures=["SNAPSHOT EMPTY"]))
    print("cards in snapshot: %d" % total_cards)
    if a.snapshot:
        with open(a.snapshot, "w", encoding="utf-8") as f:
            json.dump(dict(keys=list(RANK_KEYS), cards=total_cards, scenarios=snapshot), f,
                      ensure_ascii=False, indent=1)
    if a.compare:
        with open(a.compare, encoding="utf-8") as f:
            prev = json.load(f).get("scenarios") or {}
        drift = [sid for sid, view in snapshot.items() if sid in prev and prev[sid] != view]
        missing = [sid for sid in prev if sid not in snapshot]
        print("\nDRIFT vs %s: %d scenario(s) ranked differently%s"
              % (a.compare, len(drift), (" — " + ", ".join(drift[:12])) if drift else ""))
        if missing:
            print("  (%d scenario(s) in the previous snapshot are absent now: %s)" % (len(missing), ", ".join(missing[:8])))
    n_ok = sum(1 for r in results if r.get("ok"))
    hard = sum(1 for _id, fs in failures for f in fs
               if f.startswith(("GATE", "SELF", "OUTREACH", "DATING", "SCORE", "CRASH", "NON-DET")))
    print("\n== %d/%d scenarios pass | hard violations: %d | latency avg %.1fms p95 %.1fms (pool=%d) =="
          % (n_ok, len(results), hard, sum(lat) / max(1, len(lat)),
             sorted(lat)[int(0.95 * (len(lat) - 1))] if lat else 0, len(users)))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(dict(passed=n_ok, total=len(results), hard=hard, results=results),
                      f, ensure_ascii=False, indent=1)
    sys.exit(0 if n_ok == len(results) else 1)

if __name__ == "__main__":
    main()
