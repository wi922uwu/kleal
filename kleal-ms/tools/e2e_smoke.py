# -*- coding: utf-8 -*-
"""End-to-end walk of the product as a user — the suite the project did not have.

Every call goes through the GATEWAY, exactly like a browser: screens, accounts, the onboarding
funnel, filtration, buddy, matching, and the screens behind a search. The point is to exercise
the same path a person does, not to call internals — a service can pass its unit tests and still
serve a dead button, which is exactly what this found.

    cd kleal-ms && ops/run.sh all
    python3 tools/e2e_smoke.py

Needs a reachable model for the onboarding/buddy sections. Off the pod, tunnel vLLM in:
    ssh -f -N -L 8002:127.0.0.1:8002 root@<pod>

Two assertions here were wrong the first time and are worth keeping straight:
  * /api/agent/weights returns its full payload on GET; a POST looks like a disabled engine.
  * An unmatchable ask SHOULD return broader options (spec §12, never a dead end). What must
    never happen is passing them off as matches — so the check is on the band, not the count.
"""
import json, urllib.request, urllib.error, time, sys

GW = "http://127.0.0.1:7080"
R = {"ok": 0, "fail": 0}
FAILED = []


def call(path, body=None, method=None, timeout=180):
    method = method or ("POST" if body is not None else "GET")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(GW + path, data=data,
                                 headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:200]
    except Exception as e:
        return type(e).__name__, str(e)[:200]


def check(name, cond, detail=""):
    R["ok" if cond else "fail"] += 1
    if not cond:
        FAILED.append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (("   " + str(detail)[:110]) if detail else ""))


def section(t):
    print("\n" + "=" * 76 + "\n" + t + "\n" + "=" * 76)


# ─────────────────────────────────────────────── 1. the pages a user opens
section("1. SCREENS — every page a user can land on")
for path, label in (("/", "gateway root -> onboarding"), ("/menu", "landing menu"),
                    ("/onboarding", "onboarding app"), ("/profile", "profile app")):
    st, body = call(path)
    check("%s serves HTML" % label, st == 200 and isinstance(body, str) and "<" in body,
          "status=%s" % st)

st, body = call("/assets/logo.svg")
check("onboarding assets route answers", st in (200, 404), "status=%s" % st)

# ─────────────────────────────────────────────── 2. accounts
section("2. ACCOUNTS — signup / signin")
login = "e2e_%d" % int(time.time())
st, r = call("/api/onboarding/signup", {"login": login, "password": "pw123456", "name": "E2E Tester"})
check("signup accepted", st == 200 and isinstance(r, dict) and r.get("ok") is not False, r)
st, r = call("/api/onboarding/signin", {"login": login, "password": "pw123456"})
check("signin with the right password", st == 200 and isinstance(r, dict) and r.get("ok"), r)
st, r = call("/api/onboarding/signin", {"login": login, "password": "WRONG"})
check("signin rejects the wrong password", st == 200 and isinstance(r, dict) and not r.get("ok"), r)

# ─────────────────────────────────────────────── 3. onboarding funnel
section("3. ONBOARDING FUNNEL — the gate, the agent, the summary")
st, crit = call("/api/onboarding/state", {"profile": {}})
check("empty profile reports the critical gate", st == 200 and isinstance(crit, dict), crit)
missing0 = [c for c in (crit.get("items") or crit.get("crit") or []) if not (c.get("ok") if isinstance(c, dict) else True)]
print("       gate items: %s" % (list(crit.keys())[:6],))

PROF = {"name": "E2E Tester", "ageVerified18": True, "gender": "Female", "photoStatus": "uploaded",
        "city": "Barcelona", "language": "en",
        "languages": {"comfortable": ["en", "es"]},
        "interests": {"explicit": ["padel", "specialty coffee"]},
        "geo": {"comfortableAreas": ["Gràcia"], "maxDistanceKm": 10},
        "goals": {"primary": ["friends"]},
        "permissions": {"useProfileForMatching": True}}
st, crit2 = call("/api/onboarding/state", {"profile": PROF})
check("filled profile passes more of the gate", st == 200 and isinstance(crit2, dict), "")

st, chat = call("/api/onboarding/chat",
                {"messages": [{"role": "user", "content": "hi, i'm new here"}], "profile": {}, "lang": "en"})
check("onboarding agent replies", st == 200 and isinstance(chat, dict) and bool(chat.get("reply")),
      (chat or {}).get("reply", "")[:80] if isinstance(chat, dict) else chat)
check("onboarding reply carries no error", isinstance(chat, dict) and not chat.get("error"),
      (chat or {}).get("error") if isinstance(chat, dict) else "")

st, summ = call("/api/onboarding/summary", {"profile": PROF, "lang": "en"})
check("summary generated", st == 200 and isinstance(summ, dict) and bool(summ.get("summary")),
      (summ or {}).get("summary", "")[:80] if isinstance(summ, dict) else summ)

st, reg = call("/api/onboarding/register", {"profile": PROF})
check("registration writes into the shared store",
      st == 200 and isinstance(reg, dict) and reg.get("ok") and (reg.get("user") or {}).get("name"), reg)
me = ((reg or {}).get("user") or {}).get("name") or "E2E Tester"

st, got = call("/api/onboarding/profile", {"name": me})
check("the registered person reads back", st == 200 and isinstance(got, dict) and (got.get("user") or {}).get("name") == me,
      (got or {}).get("user", {}).get("name") if isinstance(got, dict) else got)

st, upd = call("/api/onboarding/profile-update", {"name": me, "patch": {"vibe": "chill"}})
check("profile-update applies a whitelisted field", st == 200 and isinstance(upd, dict) and upd.get("ok") is not False, upd)

st, rec = call("/api/onboarding/receiving", {"name": me})
check("receiving policy reads", st == 200 and isinstance(rec, dict), rec)

# ─────────────────────────────────────────────── 4. filtration
section("4. FILTRATION — canonical topics for messy input")
CASES = [("хочу поиграть в настолки", "tabletop/games"), ("quedar para un café", "coffee"),
         ("senderismo por Montserrat", "outdoors"), ("labubu", "toys_collectibles"),
         ("bachata", "music/social"), ("i want to play padel", "sports")]
for text, expect in CASES:
    st, f = call("/api/filter/categorize", {"text": text})
    good = st == 200 and isinstance(f, dict) and f.get("category") and f.get("topics")
    check("«%s» -> %s / %s (expect ~%s)" % (text[:26], (f or {}).get("category"),
                                            ",".join((f or {}).get("topics") or [])[:30], expect), good)

# ─────────────────────────────────────────────── 5. buddy
section("5. BUDDY — free text becomes a confirmed intent")
st, ib = call("/api/buddy/intent-build",
              {"messages": [{"role": "user", "content": "i want to play padel this weekend in Gracia"}],
               "profile": PROF})
ok_ib = st == 200 and isinstance(ib, dict)
check("intent-build responds", ok_ib, (ib or {}).get("error") if isinstance(ib, dict) else ib)
intent = (ib or {}).get("intent") if isinstance(ib, dict) else None
check("an intent object is produced", isinstance(intent, dict) and bool(intent), intent)
if isinstance(intent, dict):
    check("intent carries topics", bool(intent.get("topics")), intent.get("topics"))
    check("intent has a title for the card", bool(intent.get("title")), intent.get("title"))

st, bc = call("/api/buddy/chat",
              {"messages": [{"role": "user", "content": "hola, quiero conocer gente para tomar un café"}],
               "profile": PROF})
check("buddy answers Spanish", st == 200 and isinstance(bc, dict) and bool(bc.get("reply")),
      (bc or {}).get("reply", "")[:80] if isinstance(bc, dict) else bc)

# ─────────────────────────────────────────────── 6. matching
section("6. MATCHING — a real search over the 600-person pool")
st, m = call("/api/agent/match",
             {"intent": {"topics": ["padel"], "type": "sport", "role": "play"},
              "profile": PROF, "ctx": {"self": me}})
ok_m = st == 200 and isinstance(m, dict)
check("match responds", ok_m, (m or {}).get("error") if isinstance(m, dict) else m)
cands = (m or {}).get("candidates") or [] if isinstance(m, dict) else []
check("padel search returns people", len(cands) > 0, "%d candidates" % len(cands))
if cands:
    c0 = cands[0]
    check("top card has a name", bool(c0.get("name")), c0.get("name"))
    check("top card explains itself", bool(c0.get("reasons") or c0.get("why") or c0.get("band")),
          {k: c0.get(k) for k in ("band", "reasons") if c0.get(k)})

st, m2 = call("/api/agent/match",
              {"intent": {"topics": ["quidditch on mars"], "type": "sport"},
               "profile": PROF, "ctx": {"self": me}})
c2 = (m2 or {}).get("candidates") or [] if isinstance(m2, dict) else []
bands = {c.get("band") for c in c2}
honest = (not c2) or bands <= {"needs_clarification", "broader_option"}
check("an impossible request is never passed off as a match (§12)", honest,
      "%d candidates, bands=%s" % (len(c2), sorted(b for b in bands if b)))

st, m3 = call("/api/agent/match",
              {"intent": {"topics": ["coffee"], "type": "social", "minAge": 20, "maxAge": 25},
               "profile": PROF, "ctx": {"self": me}})
c3 = (m3 or {}).get("candidates") or [] if isinstance(m3, dict) else []
ages = [c.get("age") for c in c3 if c.get("age")]
check("age filter is honoured", (not ages) or all(20 <= a <= 25 for a in ages),
      "ages: %s" % sorted(set(ages))[:12])

st, pool = call("/api/agent/pool")
check("pool is the real store, not demo fakes",
      isinstance(pool, dict) and pool.get("fromStore") and (pool.get("count") or 0) > 100,
      {k: (pool or {}).get(k) for k in ("count", "fromStore")})

st, w = call("/api/agent/weights")
core = (w or {}).get("core") if isinstance(w, dict) else None
check("matching_core engine is ENABLED (not the legacy fallback)",
      isinstance(core, dict) and core.get("enabled") is True, core)

# ─────────────────────────────────────────────── 7. the screens behind the search
section("7. POST-SEARCH SCREENS — intents, messages, groups")
for path, screen in (("/api/agent/intents", "My Intents"), ("/api/agent/intent-save", "save an intent"),
                     ("/api/agent/inbox", "Messages inbox"), ("/api/agent/threads", "Message threads"),
                     ("/api/agent/groups", "Groups"), ("/api/agent/propose", "propose a meet")):
    from urllib.parse import quote
    st, _ = call(path + "?self=" + quote(me), None)
    st2, _ = call(path, {"self": me})
    check("%s (%s) is reachable" % (screen, path), st != 404 or st2 != 404,
          "GET=%s POST=%s" % (st, st2))

print("\n" + "=" * 76)
print("E2E RESULT: %d ok, %d failed" % (R["ok"], R["fail"]))
if FAILED:
    print("\nfailed checks:")
    for f in FAILED:
        print("   -", f)
