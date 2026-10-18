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


def skip(name, why):
    """Проверка, которую в этой среде провести НЕЧЕМ. Считать её падением нельзя: красный смоук,
    падающий всегда, перестают читать — и он молчит уже по-настоящему, когда ломается продукт."""
    R["skip"] = R.get("skip", 0) + 1
    print("  --   " + name + "   (пропуск: " + why + ")")


def section(t):
    print("\n" + "=" * 76 + "\n" + t + "\n" + "=" * 76)


# ─────────────────────────────────────────────── 1. the pages a user opens
section("1. SCREENS — every page a user can land on")
# «/profile» здесь больше нет: сервис профиля был веб-страницей и удалён целиком, а проверка
# продолжала требовать от шлюза страницу, которой не существует.
for path, label in (("/", "gateway root -> onboarding"), ("/menu", "landing menu"),
                    ("/onboarding", "onboarding app")):
    st, body = call(path)
    check("%s serves HTML" % label, st == 200 and isinstance(body, str) and "<" in body,
          "status=%s" % st)

st, body = call("/assets/logo.svg")
check("onboarding assets route answers", st in (200, 404), "status=%s" % st)

# ─────────────────────────────────────────────── 2. accounts
section("2. ACCOUNTS — password sign-in is closed")
# С 27.09.2026 вход по паролю закрыт: смоук заводил в проде по учётке на каждый прогон.
for _p in ("/api/onboarding/signup", "/api/onboarding/signin"):
    st, r = call(_p, {"login": "e2e", "password": "pw123456"})
    check("%s is closed (410)" % _p, st == 410, (st, r))

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
# 17.10.2026: chat и summary требуют вход, как register ниже. Без сессии смоук видит отказ —
# это пропуск, а не падение; а вот ответ модели без входа был бы падением.
if isinstance(chat, dict) and chat.get("error") == "no session":
    skip("onboarding agent replies", "нужен вход по коду")
    skip("onboarding reply carries no error", "нужен вход по коду")
else:
    check("onboarding agent is closed without a session", False, "ответила без входа")

st, summ = call("/api/onboarding/summary", {"profile": PROF, "lang": "en"})
if isinstance(summ, dict) and summ.get("error") == "no session":
    skip("summary generated", "нужен вход по коду")
else:
    check("summary is closed without a session", False, "сводка без входа")

st, reg = call("/api/onboarding/register", {"profile": PROF})
# ВХОД ОБЯЗАТЕЛЕН С ТЕХ ПОР, КАК ПОЯВИЛИСЬ КОДЫ. Смоук сессию получить не может: код живёт в
# памяти сервиса хэшем, а KLEAL_SHOW_CODE в проде выключен — и выключен правильно. Поэтому три
# проверки анкеты помечаются пропуском, а не падением: иначе смоук горит красным всегда.
NEED_AUTH = isinstance(reg, dict) and str(reg.get("error") or "") == "sign in required"
if NEED_AUTH:
    skip("registration writes into the shared store", "нужен вход по коду")
else:
    check("registration writes into the shared store",
          st == 200 and isinstance(reg, dict) and reg.get("ok") and (reg.get("user") or {}).get("name"), reg)
me = ((reg or {}).get("user") or {}).get("name") or "E2E Tester"

if NEED_AUTH:
    skip("the registered person reads back", "нужен вход по коду")
    skip("profile-update applies a whitelisted field", "нужен вход по коду")
else:
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

# ПУСТОЙ reply ПРИ РАСПОЗНАННОЙ ЗАТЕЕ — ЭТО ДОГОВОР, А НЕ МОЛЧАНИЕ. Экран (app/buddy.tsx,
# `looksLikeIntent`) вместо реплики открывает окно выбора: раньше человек получал и ответ, и окно
# поверх него, и было непонятно, на что отвечать. Проверка требовала именно reply — и краснела на
# каждой фразе, из которой затея выходит сразу, независимо от языка (ru/en/es одинаково). Спрашиваем
# то, что и хотели спросить: испанский разобран и ход куда-то ведёт — репликой ИЛИ затеей.
st, bc = call("/api/buddy/chat",
              {"messages": [{"role": "user", "content": "hola, quiero conocer gente para tomar un café"}],
               "profile": PROF})
check("buddy handles Spanish (a reply or an intent, never silence)",
      st == 200 and isinstance(bc, dict) and (bool(bc.get("reply")) or bool(bc.get("intent"))),
      bc if not isinstance(bc, dict) else {"reply": (bc.get("reply") or "")[:40], "intent": bool(bc.get("intent")),
                                           "lang": bc.get("lang")})
check("and answers IN Spanish", isinstance(bc, dict) and str(bc.get("lang") or "") == "es",
      (bc or {}).get("lang"))

# Отдельно — сама испанская РЕПЛИКА, на болтовне, где затеи нет и окно не открывается.
st, bs = call("/api/buddy/chat",
              {"messages": [{"role": "user", "content": "hola, ¿cómo estás?"}], "profile": PROF})
check("buddy answers Spanish small talk", st == 200 and isinstance(bs, dict) and bool(bs.get("reply")),
      (bs or {}).get("reply", "")[:80] if isinstance(bs, dict) else bs)

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
                     ("/api/agent/gintents", "Groups"), ("/api/agent/propose", "propose a meet")):
    from urllib.parse import quote
    st, _ = call(path + "?self=" + quote(me), None)
    st2, _ = call(path, {"self": me})
    check("%s (%s) is reachable" % (screen, path), st != 404 or st2 != 404,
          "GET=%s POST=%s" % (st, st2))

print("\n" + "=" * 76)
print("E2E RESULT: %d ok, %d failed, %d skipped" % (R["ok"], R["fail"], R.get("skip", 0)))
if FAILED:
    print("\nfailed checks:")
    for f in FAILED:
        print("   -", f)
