# -*- coding: utf-8 -*-
# Kleal admin-service — an admin panel to view / add / edit / delete the platform's users while the app
# runs in TEST MODE. It runs on its OWN address (a separate cloudflared tunnel, not behind the main
# gateway). Users are stored in a shared JSON file (KLEAL_USERS) that the matching agent reads, so admin
# edits directly change who gets matched. Seeds itself once from the matching agent's demo pool.
#
# NO auth: protection is the obscure/separate URL only (test-mode tool). Holds no model keys.
import os, hashlib, hmac
import sys
import json
import uuid
import threading
import re                                      # лаборатория: запасной разбор фразы на слова
import urllib.request
from urllib.parse import quote
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "..", "..", "shared"), os.path.join(_HERE, "shared")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
import config                                  # the one topology table (ports/URLs/store paths)
from http_util import send, send_json, read_json
import ops                                     # операционный слой: база, очередь, мост тем
try:
    import db                                  # хранилище людей: то же, что у матчинга
except Exception:
    db = None
from ui import PAGE                            # страница — отдельным файлом, см. её шапку

PORT = config.PORTS["admin"]
MATCH_URL = config.MATCH_URL
BUDDY_URL = config.BUDDY_URL
# THE shared store, resolved once in shared/config.py. This used to be computed here as well, and
# pointed at services/matching/users.json, so a restart without KLEAL_USERS silently split the store:
# the panel edited one file while the matcher read another, and nothing said so. (The health bar now
# says so anyway — but a path that cannot disagree beats a warning that it did.)
STORE = config.USERS
_LOCK = threading.Lock()
_seeded = {"done": False}

# The panel can edit and delete real people and can run searches as them. It was open to anyone with
# the URL. A token is the minimum; it is generated and printed once rather than defaulted to
# something, so the panel is never accidentally open — and never accidentally locked out either.
_TOKEN_FILE = config.ADMIN_TOKEN_FILE


def _admin_token():
    t = os.environ.get("KLEAL_ADMIN_TOKEN", "").strip()
    if t:
        return t
    try:
        with open(_TOKEN_FILE, "r", encoding="utf-8") as f:
            t = f.read().strip()
        if t:
            return t
    except Exception:
        pass
    t = hashlib.sha256(os.urandom(32)).hexdigest()[:24]
    try:
        with open(_TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(t)
        os.chmod(_TOKEN_FILE, 0o600)
    except Exception:
        pass
    return t


ADMIN_TOKEN = _admin_token()

VIBES = ["calm", "energetic", "intellectual", "creative", "competitive", "chill", "social", "introvert", "extrovert"]
ROLES = ["play", "watch", "discuss", "practise", "attend", "meet"]


# ---------------- user normalisation (every stored user is complete + matching-safe) ----------------
def _as_list(v):
    """Single-token list (interests, languages, topics) — split on commas AND whitespace."""
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [x.strip() for x in v.replace(",", " ").split() if x.strip()]
    return []


def _as_phrases(v):
    """Multi-word phrase list (deal-breakers, communities) — split ONLY on commas."""
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        return [x.strip() for x in v.split(",") if x.strip()]
    return []


# Kept byte-identical to onboarding's table (onboarding/app.py:1552) on purpose: the two services
# write the same users.json, and a language spelled differently by each writer is a person who
# silently stops matching when their row is touched by the other one.
_LANG_CODES = {"english": "en", "spanish": "es", "german": "de", "french": "fr", "portuguese": "pt",
               "italian": "it", "russian": "ru", "catalan": "ca", "ukrainian": "uk", "polish": "pl",
               "английский": "en", "испанский": "es", "немецкий": "de", "французский": "fr",
               "португальский": "pt", "итальянский": "it", "русский": "ru", "каталанский": "ca",
               "serbian": "sr", "сербский": "sr", "swedish": "sv", "шведский": "sv",
               "sp": "es"}   # legacy typo written by an older build; repair, do not drop
# Valid codes are ISO 639-1, NOT the keys of the name table above. Deriving them from that table
# was a bug caught only by counting the live store: 30 of the 31 codes in users.json are real
# (hi, ar, da, ko, zh, nl, ja, he, cs, el, th, vi, id ...) and simply have no English/Russian NAME
# entry, so the narrower check would have deleted a real language from anyone the admin touched —
# a worse bug than the one being fixed. The only genuinely broken code in the store is "sp", two
# rows, both real onboarding profiles; it is repaired by the alias table.
_LANG_VALID = set("""en es de fr pt it ru ca uk pl sr sv hi ar da ko zh fi nl tr no ja hu ro
he cs el th vi id bg hr sk sl et lv lt is ga cy sq mk bs be az ka hy fa ur bn ta te ml kn mr pa gu
si ne my km lo ms tl sw af zu am ku ps tg uz kk ky mn ta la eo""".split())


def _lang_code(x):
    x = str(x or "").strip().lower()
    if not x:
        return ""
    if x in _LANG_CODES:
        return _LANG_CODES[x]
    return x if (len(x) == 2 and x in _LANG_VALID) else ""


def _norm_user(u, keep_id=None, fill_defaults=True):
    """Normalise a user row.

    `fill_defaults` is False for edits of an EXISTING person. The defaults below are reasonable for
    a row being invented in the Add form and actively harmful for one being edited: saving a real
    person to flip one checkbox used to give them `coffee` if they listed no interests, `en` if
    their languages were never collected, a 2.0 km distance, a "chill" vibe, age 28, and an entity
    named "<Interest> scene" that nobody ever joined. The panel then reported the profile it had
    just authored, and the person card exists to report exactly those fields as MISSING.
    """
    u = u or {}

    def _int(v, d):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return d

    def _keep(key, value, default):
        """Absent stays absent on an edit; only a brand-new row gets the default."""
        if value:
            return value
        return default if fill_defaults else (u.get(key) if key in u else value)

    interests = [x.lower() for x in _as_list(u.get("interests"))]
    interests = interests or (["coffee"] if fill_defaults else [])
    # Truncating to two characters is wrong for most language names — Portuguese becomes "po",
    # German "ge", Serbian "se" — and none of those is a code the matcher compares against, so the
    # person matched nobody on language. This is the WRITE path: a wrong code here is stored in
    # users.json and outlives the session that typed it.
    langs = [c for c in (_lang_code(x) for x in _as_list(u.get("langs") or u.get("languages"))) if c]
    langs = langs or (["en"] if fill_defaults else [])
    try:
        km = round(float(u.get("km", 2.0 if fill_defaults else None)), 1)
    except (TypeError, ValueError):
        km = 2.0 if fill_defaults else None
    vibe = str(u.get("vibe") or ("chill" if fill_defaults else "")).lower()
    role = str(u.get("role") or "meet").lower()
    deal = _as_phrases(u.get("dealBreakers"))[:6]
    ents = _as_phrases(u.get("entities"))[:6]
    if not ents and fill_defaults and interests:
        ents = [interests[0].capitalize() + " scene"]
    # own active intent -> makes this person a RECIPROCAL (T0) match. From an `intents` list, or the form's ownIntent* fields.
    intents = u.get("intents") if isinstance(u.get("intents"), list) else []
    oi_topics = [t.lower() for t in _as_list(u.get("ownIntentTopics"))][:3]
    if oi_topics:
        oi_type = str(u.get("ownIntentType") or "social").lower()
        oi_role = str(u.get("ownIntentRole") or "meet").lower()
        intents = [{"type": oi_type, "topics": oi_topics, "role": oi_role if oi_role in ROLES else "meet"}]
    dcd = u.get("declinedOwnerDaysAgo")
    dcd = int(dcd) if str(dcd).strip().lstrip("-").isdigit() else None
    out = {
        "id": keep_id or u.get("id") or ("u" + uuid.uuid4().hex[:8]),
        "name": (str(u.get("name") or "").strip() or "User"),
        "interests": interests[:6],
        "vibe": (vibe if vibe in VIBES else ("chill" if fill_defaults else vibe)),
        "langs": langs[:4],
        "area": str(u.get("area") or "").strip(),
        "km": km, "lat": u.get("lat"), "lon": u.get("lon"),
        "open": bool(u.get("open", True)),
        "role": role if role in ROLES else "meet",
        "datingOk": bool(u.get("datingOk", False)),
        # An unknown age is a hard gate for dating and every age-range search. Inventing 28 here
        # made those people quietly eligible on a number the panel made up.
        "age": _int(u.get("age", 28 if fill_defaults else None), 28 if fill_defaults else None),
        "verified": bool(u.get("verified", True)),
        "paused": bool(u.get("paused", False)),
        "pending": _int(u.get("pending"), 0),
        "blocksMe": bool(u.get("blocksMe", False)),
        "lastActiveDays": _int(u.get("lastActiveDays"), 0),
        "declinedOwnerDaysAgo": dcd,
        "intents": intents,
        "entities": ents,
        "dealBreakers": deal,
    }
    # Preserve fields this form doesn't know about — receiving policy (matching's readiness engine
    # reads it), geo, tags, source, summary... An admin edit/toggle must never silently strip data
    # that other services own.
    for k, v in (u or {}).items():
        if k not in out:
            out[k] = v
    return out


# ---------------- store (atomic writes) ----------------
def _read():
    """Люди — ОТТУДА ЖЕ, ОТКУДА ИХ ЧИТАЕТ МАТЧИНГ.

    Панель читала файл напрямую. Пока файл был единственным хранилищем, это работало; с переездом
    на базу матчинг стал читать её, а панель осталась у файла — и показывала бы вчерашнюю
    популяцию, не сказав об этом ни словом. Хуже: правка уезжала в файл, которого никто не
    читает, то есть кнопка «Сохранить» врала.
    """
    if db is not None and db.ENABLED:
        try:
            rows = db.load_users()
            if rows:
                return rows
        except Exception as e:
            print("[admin] postgres недоступен, читаю файл: %s: %s" % (type(e).__name__, str(e)[:120]))
    try:
        with open(STORE, "r", encoding="utf-8") as f:
            data = json.load(f)
        lst = data.get("users") if isinstance(data, dict) else data
        return lst if isinstance(lst, list) else []
    except Exception:
        return []


def _write(users, touched=None):
    """И записываются они туда же. `touched` — один человек вместо всей популяции: правка
    Sofia не имеет отношения к строкам остальных семисот."""
    wrote = False
    if db is not None and db.ENABLED:
        try:
            if touched is not None:
                db.save_user(touched)
            else:
                db.save_users(users)
            wrote = True
        except Exception as e:
            print("[admin] запись в postgres не удалась, падаю на файл: %s: %s"
                  % (type(e).__name__, str(e)[:120]))
    if wrote and not db.MIRROR_JSON:
        return
    tmp = STORE + ".tmp"
    os.makedirs(os.path.dirname(os.path.abspath(STORE)), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"users": users}, f, ensure_ascii=False)
    os.replace(tmp, STORE)


def _seed_if_empty():
    """First run: pull the matching agent's demo pool so admins have something to curate."""
    if _seeded["done"] or os.path.exists(STORE):
        _seeded["done"] = True
        return
    users = []
    try:
        with urllib.request.urlopen(MATCH_URL + "/api/agent/pool", timeout=8) as r:
            users = (json.loads(r.read().decode("utf-8")) or {}).get("users") or []
    except Exception:
        users = []
    users = [_norm_user(u, keep_id=u.get("id")) for u in users]
    with _LOCK:
        if not os.path.exists(STORE):
            _write(users)
    _seeded["done"] = True


def list_users():
    _seed_if_empty()
    return _read()


def add_user(u):
    with _LOCK:
        users = _read()
        nu = _norm_user(u)
        users.append(nu)
        _write(users, touched=nu)
        return nu


def update_user(uid, patch):
    with _LOCK:
        users = _read()
        for i, u in enumerate(users):
            if u.get("id") == uid:
                merged = dict(u)
                merged.update(patch or {})
                # Editing an existing person never invents the fields they never gave.
                users[i] = _norm_user(merged, keep_id=uid, fill_defaults=False)
                _write(users, touched=users[i])
                return users[i]
    return None


VERBS = ("pause", "unpause", "unverify", "verify")


def apply_verb(name, verb):
    """The three narrow verbs that replaced the edit form.

    They patch ONE key on the raw row and deliberately do NOT go through `_norm_user`, which
    rewrites a person on every save: it substitutes `coffee` for empty interests, `en` for missing
    languages, km 2.0, vibe "chill", and invents an entity called "<Interest> scene". Saving a row
    just to pause someone used to fabricate the very data the person card exists to report as
    missing — the panel would show a clean profile it had authored itself.
    """
    if verb not in VERBS:
        return {"ok": False, "error": "unknown verb"}
    want = str(name or "").strip().lower()
    with _LOCK:
        users = _read()
        for i, u in enumerate(users):
            if str(u.get("name", "")).strip().lower() != want:
                continue
            row = dict(u)
            if verb in ("pause", "unpause"):
                r = dict(row.get("receiving") or {}) if isinstance(row.get("receiving"), dict) else {}
                if verb == "pause":
                    r["status"] = "paused"
                    r.pop("paused_until", None)      # indefinite: is_paused() reads a missing
                    row["paused"] = True             # paused_until as "still paused"
                else:
                    r["status"] = "active"
                    r.pop("paused_until", None)
                    row.pop("paused", None)
                row["receiving"] = r
            elif verb == "unverify":
                row["verified"] = False
            elif verb == "verify":
                row["verified"] = True
            users[i] = row
            _write(users, touched=row)
            return {"ok": True, "name": row.get("name"), "verb": verb,
                    "verified": bool(row.get("verified")),
                    "receiving": row.get("receiving"), "paused": bool(row.get("paused"))}
    return {"ok": False, "error": "no such person"}


def delete_user(uid):
    with _LOCK:
        users = _read()
        n = len(users)
        gone = next((u for u in users if u.get("id") == uid), None)
        users = [u for u in users if u.get("id") != uid]
        if len(users) != n:
            # Удаление — единственное место, где база должна УБРАТЬ строку, а не переписать её:
            # без этого человек исчезал бы из файла и оставался в поиске.
            if db is not None and db.ENABLED and gone is not None:
                try:
                    db.delete_user(gone.get("name"))
                except Exception as e:
                    print("[admin] не смог удалить из postgres: %s" % str(e)[:120])
            _write(users)
            return True
    return False


def _match_post(path, payload, timeout=30):
    """Call the matching service (read-only endpoints). Returns its JSON or {'error': ...}."""
    req = urllib.request.Request(MATCH_URL + path, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"error": "%s: %s" % (type(e).__name__, str(e)[:160])}


def _match_get(path, timeout=20):
    """Read-only GET against the matching service — health and pool provenance."""
    try:
        with urllib.request.urlopen(MATCH_URL + path, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"_error": "%s: %s" % (type(e).__name__, str(e)[:160])}


E2E_PHRASES = ["хочу выпить кофе", "хочу поиграть в падл", "хочу обсудить стартапы",
               "хочу сходить на выставку", "ищу с кем побегать утром", "хочу поиграть в доту"]


def e2e_probe(prof, phrases=None, timeout=300):
    """The whole app path — free text -> buddy -> intent -> matching — not just the ranker.

    Every diagnostic before this one entered at the ranker with a hand-built intent, so it could
    only ever exonerate the ranker. «Мне попадаются одни и те же люди» is a complaint about the
    path the app actually takes, and the two most likely culprits sit BEFORE the ranker: a topic
    that fails to resolve (every unresolvable topic returns the same fallback crowd) and an intent
    that comes back not rankable at all.
    """
    phrases = [str(p).strip() for p in (phrases or E2E_PHRASES) if str(p).strip()][:12]
    rows, seen = [], {}

    def _chat(msgs):
        req = urllib.request.Request(
            BUDDY_URL + "/api/buddy/chat",
            data=json.dumps({"messages": msgs, "profile": prof}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _cards(res):
        cards = res.get("matches") if isinstance(res.get("matches"), list) else []
        if not cards:
            blk = res.get("match") if isinstance(res.get("match"), dict) else {}
            cards = blk.get("candidates") if isinstance(blk.get("candidates"), list) else []
        return [str(c.get("name") or "") for c in cards if isinstance(c, dict) and c.get("name")]

    for ph in phrases:
        # Buddy asks up to two clarifying questions before it searches — that is the designed
        # behaviour, not a failure. A one-shot probe read every one of those as "no topic" and
        # would have sent someone hunting a resolver bug that does not exist. So the probe holds
        # the conversation the way a person does, and reports how many turns it took.
        msgs, res, turns, err = [{"role": "user", "content": ph}], None, 0, None
        for turn in range(3):
            try:
                res = _chat(msgs)
            except Exception as e:
                err = "%s: %s" % (type(e).__name__, str(e)[:120])
                break
            turns = turn + 1
            if _cards(res):
                break
            reply = str(res.get("reply") or "")
            if not reply:
                break
            msgs = msgs + [{"role": "assistant", "content": reply},
                           {"role": "user", "content": "не важно, на твой выбор — давай искать"}]
        if err or res is None:
            rows.append({"phrase": ph, "error": err or "no response", "names": []})
            continue
        intent = res.get("intent") if isinstance(res.get("intent"), dict) else {}
        names = _cards(res)
        for n in names:
            seen[n] = seen.get(n, 0) + 1
        rows.append({"phrase": ph, "topics": intent.get("topics") or [],
                     "rankable": intent.get("rankable"), "turns": turns,
                     "asked": turns > 1,
                     "n": len(names), "names": names[:8]})
    withres = [r for r in rows if r.get("names")]
    order = sorted(seen.items(), key=lambda kv: -kv[1])
    # Two searches sharing most of their slate is the complaint, stated exactly.
    worst = None
    for i in range(len(withres)):
        for j in range(i + 1, len(withres)):
            a, b = set(withres[i]["names"]), set(withres[j]["names"])
            if not a or not b:
                continue
            ov = len(a & b) / float(min(len(a), len(b)))
            if worst is None or ov > worst["overlap"]:
                worst = {"a": withres[i]["phrase"], "b": withres[j]["phrase"],
                         "overlap": round(ov, 2), "shared": sorted(a & b)[:8]}
    return {"ok": True, "phrases": len(rows), "withResults": len(withres),
            "unrankable": [r["phrase"] for r in rows if r.get("rankable") is False],
            "noTopics": [r["phrase"] for r in rows if not r.get("topics") and not r.get("error")],
            "errors": [r for r in rows if r.get("error")],
            "distinctPeople": len(seen),
            "topRepeats": [{"name": n, "times": t} for n, t in order[:8] if t > 1],
            "worstPair": worst, "rows": rows}


def _searcher_profile(body):
    """Profile of the person running the search: a store user by name/id, or a custom dict.
    Shaped the way the matching engine reads it (name/vibe/geo/langs/interests)."""
    who = str(body.get("self") or "").strip().lower()
    if who:
        for u in _read():
            if str(u.get("name", "")).strip().lower() == who or str(u.get("id", "")) == who:
                # age and formats were missing. `_hard_gates` refuses any dating intent when the
                # SEARCHER's age is unknown, so the lab returned a confident zero for a whole class of
                # searches and looked like an engine result.
                return {"name": u.get("name"), "vibe": u.get("vibe"), "geo": u.get("geo"),
                        "langs": u.get("langs") or [], "interests": u.get("interests") or [],
                        "role": u.get("role"), "km": u.get("km"), "age": u.get("age"),
                        "formats": u.get("formats") or [], "verified": u.get("verified"),
                        "lat": u.get("lat"), "lon": u.get("lon"),
                        "radiusKm": u.get("radiusKm")}, u
    p = body.get("profile") if isinstance(body.get("profile"), dict) else {}
    p.setdefault("name", body.get("self") or "Tester")
    return p, None


def _qs(handler, key, default=""):
    """Один параметр запроса. В файле их разбирали трижды и каждый раз по-своему — эта копия
    хотя бы одна на всех новых ручек."""
    from urllib.parse import unquote
    raw = handler.path.split("?", 1)[1] if "?" in handler.path else ""
    for kv in raw.split("&"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            if k == key:
                return unquote(v.replace("+", " "))
    return default


def _path(handler):
    return handler.path.split("?", 1)[0]


class H(BaseHTTPRequestHandler):
    def _authed(self):
        """The page itself is served without the token — it has to be, so a browser can ask for one.
        Every API call needs it. Constant-time compare, so the check is not a guessing oracle."""
        got = self.headers.get("X-Admin-Token") or ""
        if not hmac.compare_digest(str(got), ADMIN_TOKEN):
            send_json(self, 401, {"ok": False, "error": "unauthorized"})
            return False
        return True

    def do_GET(self):
        p = _path(self)
        if p == "/admin" or p == "/admin/" or p == "/":
            # Новая страница. Прежняя осталась в файле и доступна по ?legacy=1 — не из
            # сентиментальности: у неё пять разделов, отлаженных на живых данных, и если новая
            # где-то соврёт, откат должен быть длиной в один параметр, а не в выкладку.
            if "legacy=1" in (self.path.split("?", 1)[1] if "?" in self.path else ""):
                return send(self, 200, HTML, "text/html")
            return send(self, 200, PAGE, "text/html")
        if not self._authed():
            return
        if p == "/api/admin/ping":
            # Отвечает не только «жив», но и чем сейчас живёт система: шапка панели показывает
            # режим хранилища и очереди, чтобы «почему цифры не сходятся» не начиналось с догадок.
            st = ops.storage()
            q = ops.queue()
            send_json(self, 200, {"ok": True, "storage": st.get("mode"), "queue": q.get("mode")})
        elif p == "/api/admin/ops":
            send_json(self, 200, ops.overview())
        elif p == "/api/admin/dead":
            send_json(self, 200, ops.dead_list(int(_qs(self, "limit", "25") or 25)))
        elif p == "/api/admin/bridge":
            send_json(self, 200, ops.bridge(_qs(self, "q")))
        elif p == "/api/admin/users":
            u = list_users()
            send_json(self, 200, {"count": len(u), "users": u})
        elif p == "/api/admin/health":
            # What system am I even looking at: engine, config, pool provenance, which users.json.
            w = _match_get("/api/agent/weights")
            pl = _match_get("/api/agent/pool")
            err = (w or {}).get("_error") or (pl or {}).get("_error")
            send_json(self, 200, {"ok": not err, "core": (w or {}).get("core"),
                                  "count": (pl or {}).get("count"),
                                  "fromStore": (pl or {}).get("fromStore"),
                                  "bySource": (pl or {}).get("bySource"), "store": (pl or {}).get("store"),
                                  "adminStore": os.path.abspath(STORE), "error": err})
        elif p == "/api/admin/person":
            from urllib.parse import unquote
            q = dict(kv.split("=", 1) for kv in self.path.split("?", 1)[-1].split("&") if "=" in kv) \
                if "?" in self.path else {}
            nm = unquote(q.get("name", "").replace("+", " "))
            rep = _match_get("/api/agent/admin/person?name=" + quote(nm))
            # The row id, so the verbs have something to target — the engine's report is keyed by name.
            for u in _read():
                if str(u.get("name", "")).strip().lower() == nm.strip().lower():
                    rep["id"] = u.get("id")
                    break
            send_json(self, 200, rep)
        elif p == "/api/admin/cohorts":
            send_json(self, 200, _match_get("/api/agent/admin/cohorts", timeout=40))
        elif p == "/api/admin/proposals":
            send_json(self, 200, _match_get("/api/agent/admin/proposals"))
        else:
            send_json(self, 404, {})

    def do_POST(self):
        p = _path(self)
        if not self._authed():
            return
        body = read_json(self)
        if p == "/api/admin/dead/retry":
            # Единственное действие панели над очередью — и оно НЕ разрушительное: сообщение
            # публикуется заново, а из мёртвой снимается только после успешной публикации.
            # Кнопки «очистить» здесь нет намеренно: молча выбросить работу — ровно то, от чего
            # уходили, заводя очередь.
            send_json(self, 200, ops.dead_retry(int((body or {}).get("limit") or 50)))
        elif p == "/api/admin/bridge/teach":
            send_json(self, 200, ops.bridge_teach((body or {}).get("phrase")))
        elif p == "/api/admin/users":
            send_json(self, 200, {"ok": True, "user": add_user(body)})
        elif p.startswith("/api/admin/user/") and p.endswith("/delete"):
            uid = p[len("/api/admin/user/"):-len("/delete")]
            send_json(self, 200, {"ok": delete_user(uid)})
        elif p.startswith("/api/admin/user/"):
            uid = p[len("/api/admin/user/"):]
            u = update_user(uid, body)
            send_json(self, 200 if u else 404, {"ok": bool(u), "user": u})
        elif p == "/api/admin/match-test":
            # Matching lab: run a real search as any stored person. Read-only — nothing is written,
            # no proposals are sent (that is /api/agent/negotiate, deliberately not exposed here).
            prof, rec = _searcher_profile(body)
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            # ЛАБОРАТОРИЯ СОБИРАЕТ ИНТЕНТ САМА, если ей дали фразу.
            #
            # Раньше ручка ждала готовый объект интента, а страница слала одну строку — и поиск
            # уходил БЕЗ ЕДИНОЙ ТЕМЫ. Движок честно отвечал «никого по теме» и падал в широкие
            # предложения, а выглядело это как «матчинг сломан».
            #
            # Темы берём у фильтрации — тем же вызовом, что делает приложение, — и кладём рядом
            # ФРАЗУ: по ней работает мост тем, и без неё «опционы» разбираются как «варианты
            # выбора». Лаборатория обязана повторять путь продукта, иначе она проверяет не его.
            q = str(body.get("query") or "").strip()
            if q and not (intent.get("topics") or []):
                topics = []
                try:
                    fr = urllib.request.Request(
                        config.FILTER_URL + "/api/filter/categorize",
                        data=json.dumps({"text": q}).encode("utf-8"),
                        headers={"Content-Type": "application/json"})
                    with urllib.request.urlopen(fr, timeout=30) as rr:
                        topics = [str(t).lower().strip()
                                  for t in ((json.loads(rr.read().decode()) or {}).get("topics") or [])
                                  if str(t).strip()]
                except Exception:
                    topics = []
                if not topics:
                    # Фильтрация молчит — не выдумываем: берём слова фразы, как их взял бы
                    # запасной путь движка. Пустой поиск честнее умного, но неверного.
                    topics = [w for w in re.findall(r"[\w\-]{3,}", q.lower())][:4]
                intent = dict(intent, topics=topics, phrase=q)
                intent.setdefault("mode", "offline")
                intent.setdefault("format", "1:1")
                intent.setdefault("time", "today")
            ctx = {"self": prof.get("name") or "", "uid": "admin-lab"}
            if body.get("now"):
                ctx["now"] = float(body["now"])
            # СКОЛЬКО ПОКАЗЫВАТЬ. Движок по умолчанию отдаёт ровно восемь (TOP_N в
            # matching_core/allocation), и ручка /api/agent/match умеет больше только если ей
            # передать `limit` — приложение так и делает кнопкой «Расширить поиск». Лаборатория
            # его не передавала, поэтому «всего восемь» выглядело как потолок системы, хотя это
            # был потолок ЗАПРОСА. Верхняя граница 48 — та же, что у движка.
            try:
                lim = int(body.get("limit") or 0)
            except (TypeError, ValueError):
                lim = 0
            lim = max(0, min(48, lim))
            payload = {"intent": intent, "profile": prof, "ctx": ctx}
            if lim:
                payload["limit"] = lim
            r = _match_post("/api/agent/match", payload)
            send_json(self, 200, {"ok": "error" not in r, "searcher": prof,
                                  "searcherKnown": bool(rec), "topics": intent.get("topics") or [],
                                  "intent": r.get("intent", intent), "limit": lim or 8,
                                  "hasMore": bool(r.get("has_more")),
                                  "candidates": r.get("candidates") or [], "error": r.get("error")})
        elif p == "/api/admin/funnel":
            # «Почему никого нет»: the shape of the search, not its result.
            prof, rec = _searcher_profile(body)
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            ctx = {"self": prof.get("name") or "", "uid": "admin-lab"}
            if body.get("now"):
                ctx["now"] = float(body["now"])
            r = _match_post("/api/agent/funnel", {"intent": intent, "profile": prof, "ctx": ctx,
                                                  "now": body.get("now")})
            r["searcher"] = prof
            r["searcherKnown"] = bool(rec)
            send_json(self, 200, r)
        elif p in ("/api/admin/diversity", "/api/admin/stability"):
            # Both answer questions about a SET of searches rather than one, which is the shape of
            # «мне попадаются одни и те же люди». Read-only, like everything else in the lab.
            prof, rec = _searcher_profile(body)
            payload = {"profile": prof, "intent": body.get("intent") or {}}
            if p.endswith("diversity"):
                payload["topics"] = body.get("topics") or []
            else:
                payload["runs"] = body.get("runs") or 4
                if body.get("now"):
                    payload["now"] = body["now"]
            r = _match_post("/api/agent/" + p.rsplit("/", 1)[-1], payload, timeout=180)
            r["searcherKnown"] = bool(rec)
            send_json(self, 200, r)
        elif p == "/api/admin/compare":
            prof, rec = _searcher_profile(body)
            r = _match_post("/api/agent/admin/compare",
                            {"intent": body.get("intent") or {}, "profile": prof,
                             "ctx": {"self": prof.get("name") or "", "uid": "admin-lab"}}, timeout=180)
            r["searcherKnown"] = bool(rec)
            send_json(self, 200, r)
        elif p == "/api/admin/e2e":
            prof, rec = _searcher_profile(body)
            r = e2e_probe(prof, body.get("phrases"))
            r["searcherKnown"] = bool(rec)
            send_json(self, 200, r)
        elif p == "/api/admin/person/verb":
            send_json(self, 200, apply_verb(body.get("name"), str(body.get("verb") or "")))
        elif p == "/api/admin/person/fatigue-reset":
            send_json(self, 200, _match_post("/api/agent/admin/fatigue-reset",
                                             {"name": body.get("name")}))
        elif p == "/api/admin/explain":
            # Why did (or didn't) B show up for A's search — full per-feature decision trace.
            prof, _rec = _searcher_profile(body)
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            ctx = {"self": prof.get("name") or "", "uid": "admin-lab"}
            if body.get("now"):
                ctx["now"] = float(body["now"])
            r = _match_post("/api/agent/explain", {"intent": intent, "profile": prof, "ctx": ctx,
                                                   "candidate": body.get("candidate")})
            send_json(self, 200, r)
        # /api/admin/clear and /api/admin/reseed are GONE. They deleted the live store — the one the
        # matcher reads and real onboarded people live in — with no auth, no backup and no audit, and
        # reseed called os.remove() BEFORE it knew a demo pool was reachable. Rebuilding fixtures is a
        # shell command on the box, not a button one click from real data.
        else:
            send_json(self, 404, {})

    def log_message(self, *a):
        pass


HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Kleal Admin</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Inter,sans-serif;background:#f6f7f9;color:#181b22}
.top{background:#fff;border-bottom:1px solid #e7e8ec;padding:14px 22px;display:flex;align-items:center;gap:14px;position:sticky;top:0;z-index:5}
.logo{font-weight:800;color:#f5455c;font-size:20px;letter-spacing:-.02em}
.pill{font-size:12px;color:#6b7180;background:#f1f2f5;border-radius:20px;padding:3px 10px}
.wrap{max-width:1180px;margin:22px auto;padding:0 22px}
.card{background:#fff;border:1px solid #e7e8ec;border-radius:14px;padding:18px;margin-bottom:18px;box-shadow:0 1px 2px rgba(20,20,40,.04)}
h2{font-size:15px;margin-bottom:12px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:end}
label{display:block;font-size:12px;color:#6b7180;margin-bottom:4px}
input,select{border:1px solid #dfe1e7;border-radius:9px;padding:8px 10px;font:inherit;background:#fff;min-width:120px}
input:focus,select:focus{outline:none;border-color:#f5455c}
button{border:none;border-radius:9px;padding:9px 14px;font:inherit;font-weight:600;cursor:pointer;background:#f5455c;color:#fff}
button.ghost{background:#f1f2f5;color:#181b22}
button.mini{padding:4px 9px;font-size:12px;font-weight:600}
button.danger{background:#fdecee;color:#e5384f}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:9px 8px;border-bottom:1px solid #eef0f3;white-space:nowrap}
th{color:#8a909c;font-weight:600;font-size:11.5px;text-transform:uppercase;letter-spacing:.03em}
td.wrap2{white-space:normal;max-width:220px}
.flag{display:inline-block;width:22px;height:22px;border-radius:6px;text-align:center;line-height:22px;cursor:pointer;font-size:12px;user-select:none;background:#f1f2f5;color:#b7bcc6}
.flag.on{background:#e9f9f0;color:#1f9d57}
.flag.warn.on{background:#fff2e8;color:#d9700f}
.tag{display:inline-block;background:#fde7eb;color:#c32b40;border-radius:6px;padding:1px 7px;margin:1px 3px 1px 0;font-size:11.5px}
.muted{color:#8a909c}
.bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;gap:12px;flex-wrap:wrap}
.search{min-width:220px}
.gate{max-width:360px;margin:12vh auto;text-align:center}
.toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#181b22;color:#fff;padding:9px 16px;border-radius:10px;opacity:0;transition:.2s;pointer-events:none;font-size:13px}
.toast.show{opacity:1}
.tabler{overflow-x:auto}
.sec{font-size:11px;color:#8a909c;text-transform:uppercase;letter-spacing:.04em;margin:16px 0 6px;font-weight:700}
.chk{display:flex;align-items:center;gap:6px;margin:0;font-size:13px}
.chk input{min-width:auto}
.adv{border-top:1px dashed #e7e8ec;margin-top:14px;padding-top:6px}
.advtog{cursor:pointer;color:#f5455c;font-size:12px;font-weight:600;user-select:none}
/* --- Matching lab --- */
.tabs{display:flex;gap:6px;margin-left:8px}
.hbar{padding:7px 14px;background:#fff;border-bottom:1px solid #e8e8ee;font-size:12.5px;display:flex;
  align-items:center;gap:6px;flex-wrap:wrap}
.hbar .sep{color:#c9ccd6}
.funnel{margin-top:14px;border-top:1px solid #eee;padding-top:8px}
.frow{display:flex;align-items:baseline;gap:10px;padding:5px 0;border-bottom:1px dashed #f0f0f4}
.frow.sub{padding-left:16px;border-bottom:0;color:#7a7f8c;font-size:13px}
.frow .fl{flex:1;min-width:0}
.frow .fn{width:64px;text-align:right;font-variant-numeric:tabular-nums;font-weight:700}
.frow.sub .fn{font-weight:500}
.frow .fnote{width:210px;font-size:12px}
.tab{padding:6px 13px;border-radius:9px;font-size:13px;font-weight:600;cursor:pointer;background:transparent;color:#6b7180;border:1px solid transparent}
.tab.on{background:#fde7eb;color:#c32b40;border-color:#f7c9d2}
.band{display:inline-block;border-radius:6px;padding:2px 8px;font-size:11.5px;font-weight:700;white-space:nowrap}
.band.especially_close{background:#e9f9f0;color:#12854a}
.band.strong_option{background:#eaf3ff;color:#1c62c4}
.band.broader_option{background:#fff5e6;color:#a86400}
.band.needs_clarification{background:#f1f2f5;color:#6b7180}
.tierb{display:inline-block;border-radius:5px;padding:1px 6px;font-size:11px;font-weight:700;background:#f1f2f5;color:#5b6170}
.tierb.T0,.tierb.T1{background:#e9f9f0;color:#1f9d57}
.rdy{font-size:11.5px;color:#6b7180}
.rdy.open_now{color:#1f9d57;font-weight:600}
.rdy.paused,.rdy.busy{color:#c32b40}
.yes{color:#1f9d57;font-weight:700}.no{color:#b7bcc6}
.preset{background:#f1f2f5;color:#3a3f4b;font-weight:600;font-size:12px;padding:5px 10px;border-radius:8px;cursor:pointer;border:none}
.preset:hover{background:#e7e8ec}
.trace{background:#fbfbfc;border:1px solid #e7e8ec;border-radius:12px;padding:14px;margin-top:12px}
.stepr{display:flex;gap:8px;align-items:baseline;font-size:12.5px;padding:3px 0;border-bottom:1px dashed #eef0f3}
.stepr b{min-width:190px;display:inline-block}
.ok{color:#1f9d57;font-weight:700}.bad{color:#e5384f;font-weight:700}
.fstate{font-size:11px;border-radius:5px;padding:1px 6px;font-weight:600}
.fstate.known_match{background:#e9f9f0;color:#1f9d57}
.fstate.known_mismatch{background:#fdecee;color:#e5384f}
.fstate.unknown{background:#fff5e6;color:#a86400}
.fstate.not_applicable{background:#f1f2f5;color:#8a909c}
.metric{display:inline-block;margin-right:14px;font-size:12px;color:#6b7180}
.metric b{color:#181b22;font-size:13px}
.drop{background:#fdecee;color:#a3243a;border-radius:9px;padding:10px 12px;font-size:13px;font-weight:600}
.hint{font-size:11.5px;color:#8a909c;margin-top:3px}
</style></head><body>
<div id="app"></div>
<div class="toast" id="toast"></div>
<script>
let TOK=sessionStorage.getItem('kleal_admin_tok')||'', USERS=[], Q='', editing=null;
let HEALTH=null, FUN=null, FUNBUSY=false;
let TAB='users', LAB={running:false,res:null,err:null,trace:null,traceFor:'',lastIntent:null,searcher:null};
const $=s=>document.querySelector(s), esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function toast(m){const t=$('#toast');t.textContent=m;t.classList.add('show');clearTimeout(t._t);t._t=setTimeout(()=>t.classList.remove('show'),1800);}
async function api(path,opts){opts=opts||{};opts.headers=Object.assign({'Content-Type':'application/json','X-Admin-Token':TOK},opts.headers||{});const r=await fetch(path,opts);if(r.status===401){TOK='';sessionStorage.removeItem('kleal_admin_tok');gate();throw new Error('unauthorized');}return r.json();}
// ---- «Почему никого нет»: the shape of a search instead of its result ----
async function runFunnel(){
  const who=(gv('#f_who')||'').trim(), topics=(gv('#f_topics')||'').trim();
  if(!topics){ toast('Укажи темы'); return; }
  FUNBUSY=true; render();
  const intent={topics:topics.split(',').map(t=>t.trim()).filter(Boolean),
                role:gv('#f_role')||'meet', mode:gv('#f_mode')||'offline', time:gv('#f_time')||'tomorrow'};
  try{ FUN=await api('/api/admin/funnel',{method:'POST',body:JSON.stringify({self:who,intent})}); }
  catch(e){ FUN={ok:false,error:String(e&&e.message||e)}; }
  FUNBUSY=false; render();
}
function funnelView(){
  const f=(FUN&&FUN.funnel)||null, sc=(f&&f.scored)||{}, g=(f&&f.gates)||{};
  const row=(label,n,note)=>`<div class="frow"><div class="fl">${label}</div>
      <div class="fn">${n==null?'—':n}</div><div class="fnote muted">${note||''}</div></div>`;
  const drops=(obj)=>Object.keys(obj||{}).filter(k=>k!=='_in').sort((a,b)=>obj[b]-obj[a])
      .map(k=>`<div class="frow sub"><div class="fl">− ${k}</div><div class="fn">${obj[k]}</div><div></div></div>`).join('');
  const meta=(f&&f.meta)||{};
  return `<div class="card">
    <h3>Почему никого нет</h3>
    <div class="muted" style="margin-bottom:10px">Тот же путь, что и в реальном поиске. Ничего не пишет и никому ничего не отправляет.</div>
    <div class="grid2">
      <label>Искатель (имя из базы)<input id="f_who" value="${(LFF.who||'').replace(/"/g,'&quot;')}" placeholder="оставь пустым — гость без профиля"></label>
      <label>Темы через запятую<input id="f_topics" value="${(LFF.topics||'').replace(/"/g,'&quot;')}" placeholder="padel, coffee"></label>
      <label>Роль<select id="f_role">${['meet','play','watch','discuss','practise','attend'].map(r=>`<option ${LFF.role===r?'selected':''}>${r}</option>`).join('')}</select></label>
      <label>Режим<select id="f_mode">${['offline','online','hybrid'].map(r=>`<option ${LFF.mode===r?'selected':''}>${r}</option>`).join('')}</select></label>
    </div>
    <button class="primary" onclick="runFunnel()" ${FUNBUSY?'disabled':''}>${FUNBUSY?'Считаю…':'Построить воронку'}</button>
    ${FUN&&FUN.error?`<div class="err">${FUN.error}</div>`:''}
    ${f?`<div class="funnel">
      ${row('В пуле', f.pool, 'loadtest-строки уже исключены')}
      ${row('Минус сам искатель', f.self!=null?-f.self:0, '')}
      ${row('Прошли жёсткие гейты', f.eligible, Object.keys(g).length?'':'никого не отсеяли')}
      ${drops(g)}
      ${row('Дошли до оценки', sc._in, '')}
      ${drops(sc)}
      ${row('В выдаче', f.slate, 'слейт ограничен восемью')}
      <div class="muted" style="margin-top:10px">домен <b>${meta.domain||'?'}</b> · ${meta.core||'?'} · ${meta.config_version||''} · ${meta.config_sha||''}
      ${FUN.searcherKnown===false?' · <b style="color:#c0392b">искатель не найден в базе — считалось от гостя</b>':''}</div>
    </div>`:''}
  </div>`;
}
let LFF={who:'',topics:'',role:'meet',mode:'offline'};
let DIV=null, DIVBUSY=false, STAB=null, STABBUSY=false;
const DIV_DEFAULT='padel, coffee, football, dota, yoga, books, photography, cooking, music, hiking, chess, wine';

// «Одни и те же люди» is a claim about a SET of searches, so no single search can settle it.
async function runDiversity(){
  const who=(gv('#f_who')||'').trim();
  const list=((gv('#d_topics')||DIV_DEFAULT).split(',').map(t=>t.trim()).filter(Boolean)).slice(0,24);
  if(!list.length){ toast('Укажи темы'); return; }
  DIVBUSY=true; render();
  try{ DIV=await api('/api/admin/diversity',{method:'POST',body:JSON.stringify({self:who,topics:list,
        intent:{role:gv('#f_role')||'meet',mode:gv('#f_mode')||'offline',time:'tomorrow'}})}); }
  catch(e){ DIV={ok:false,error:String(e&&e.message||e)}; }
  DIVBUSY=false; render();
}
// Same search N times. Our tie-break is a name hash, so any drift is time-dependent — and drift is
// indistinguishable, from the outside, from "random people".
async function runStability(){
  const who=(gv('#f_who')||'').trim(), topics=(gv('#f_topics')||'').trim();
  if(!topics){ toast('Заполни темы в блоке выше'); return; }
  STABBUSY=true; render();
  try{ STAB=await api('/api/admin/stability',{method:'POST',body:JSON.stringify({self:who,runs:4,
        intent:{topics:topics.split(',').map(t=>t.trim()).filter(Boolean),
                role:gv('#f_role')||'meet',mode:gv('#f_mode')||'offline',time:'tomorrow'}})}); }
  catch(e){ STAB={ok:false,error:String(e&&e.message||e)}; }
  STABBUSY=false; render();
}
function diagCards(){
  const d=DIV, st=STAB;
  const verdict=(good,txt)=>`<b style="color:${good?'#2f9e6b':'#c0392b'}">${txt}</b>`;
  return `<div class="card">
    <h3>Разнообразие выдачи</h3>
    <div class="muted" style="margin-bottom:8px">Гоняет список тем от лица искателя и считает, сколько РАЗНЫХ людей вернулось. Отвечает на «мне попадаются одни и те же».</div>
    <label>Темы через запятую<input id="d_topics" value="${((DIVT!=null?DIVT:DIV_DEFAULT)).replace(/"/g,'&quot;')}"></label>
    <button class="primary" onclick="runDiversity()" ${DIVBUSY?'disabled':''}>${DIVBUSY?'Гоняю…':'Проверить разнообразие'}</button>
    ${d&&d.error?`<div class="err">${d.error}</div>`:''}
    ${d&&d.ok?`<div class="funnel">
      ${['Запросов|'+d.queries,'С выдачей|'+d.withResults,'Разных людей|'+d.distinctPeople,
         'Показан больше раза|'+d.shownMoreThanOnce].map(x=>{const[a,b]=x.split('|');
         return `<div class="frow"><div class="fl">${a}</div><div class="fn">${b}</div><div></div></div>`;}).join('')}
      <div class="frow"><div class="fl">Вердикт</div><div class="fn"></div><div class="fnote">${
        d.distinctPeople >= d.withResults*4 ? verdict(true,'разнообразно') : verdict(false,'подозрительно однообразно')}</div></div>
      ${(d.emptyTopics&&d.emptyTopics.length)?`<div class="frow sub"><div class="fl">пустые темы: ${d.emptyTopics.join(', ')}</div><div class="fn">${d.emptyTopics.length}</div><div></div></div>`:''}
      ${(d.topRepeats||[]).slice(0,6).map(r=>`<div class="frow sub"><div class="fl">повтор: ${r.name}</div><div class="fn">${r.times}</div><div></div></div>`).join('')}
    </div>`:''}
  </div>
  <div class="card">
    <h3>Стабильность ×4</h3>
    <div class="muted" style="margin-bottom:8px">Один и тот же запрос четыре раза подряд. Дрейф выдачи снаружи выглядит как «случайные люди».</div>
    <button class="primary" onclick="runStability()" ${STABBUSY?'disabled':''}>${STABBUSY?'Гоняю…':'Проверить стабильность'}</button>
    ${st&&st.error?`<div class="err">${st.error}</div>`:''}
    ${st&&st.ok?`<div class="funnel">
      <div class="frow"><div class="fl">Кандидатов в выдаче</div><div class="fn">${st.n}</div><div></div></div>
      <div class="frow"><div class="fl">Состав не менялся</div><div class="fn"></div><div class="fnote">${verdict(st.stableSet,st.stableSet?'да':'НЕТ')}</div></div>
      <div class="frow"><div class="fl">Порядок не менялся</div><div class="fn"></div><div class="fnote">${verdict(st.stableOrder,st.stableOrder?'да':'НЕТ')}</div></div>
      ${(st.drift&&st.drift.length)?`<div class="frow sub"><div class="fl">появлялись/исчезали: ${st.drift.join(', ')}</div><div class="fn">${st.drift.length}</div><div></div></div>`:''}
    </div>`:''}
  </div>`+e2eCard()+compareCard();
}
// The Core v2 fallback is silent: a config whose sha does not match drops the whole system onto the
// legacy scorer with no error anywhere, and the only symptom is that different people appear.
let CMP=null, CMPBUSY=false;
async function runCompare(){
  const who=($('#f_who')&&$('#f_who').value.trim())||'';
  const topics=(($('#f_topics')&&$('#f_topics').value)||'кофе').split(',').map(s=>s.trim()).filter(Boolean);
  CMPBUSY=true; render();
  try{ CMP=await api('/api/admin/compare',{method:'POST',body:JSON.stringify({self:who,
        intent:{topics:topics, role:'meet', mode:'offline', time:'tomorrow'}})}); }
  catch(e){ CMP={ok:false,error:String(e&&e.message||e)}; }
  CMPBUSY=false; render();
}
function compareCard(){
  const c=CMP;
  return `<div class="card"><h3>Core v2 против легаси-скорера</h3>
    <div class="muted" style="margin-bottom:8px">Один запрос, два движка. Откат на легаси происходит МОЛЧА — при несовпадении sha конфига — и снаружи выглядит просто как «стали попадаться другие люди». Берёт тему из формы воронки выше.</div>
    <button class="primary" onclick="runCompare()" ${CMPBUSY?'disabled':''}>${CMPBUSY?'Считаю…':'Сравнить движки'}</button>
    ${c&&(c.error||c._error)?`<div class="err">${c.error||c._error}</div>`:''}
    ${c&&c.ok?`<div class="funnel">
      ${_kv('Core v2 включён', c.core.enabled?('да · '+(c.core.config_version||'')+' · '+(c.core.config_sha||'')):'<b style="color:#c0392b">НЕТ — сейчас работает легаси</b>')}
      ${_kv('в выдаче: v2 / легаси', c.new.n+' / '+c.old.n)}
      ${_kv('совпадение составов', Math.round(c.jaccard*100)+'%')}
      ${_kv('первый в списке сменился', c.topChanged?'<b style="color:#b7791f">да</b>':'нет')}
      ${c.onlyNew.length?`<div class="frow"><div class="fl">только в v2</div><div class="fn">${c.onlyNew.length}</div><div class="fnote">${c.onlyNew.join(', ')}</div></div>`:''}
      ${c.onlyOld.length?`<div class="frow"><div class="fl">только в легаси</div><div class="fn">${c.onlyOld.length}</div><div class="fnote">${c.onlyOld.join(', ')}</div></div>`:''}
      ${(c.moved||[]).map(m=>`<div class="frow sub"><div class="fl">${m.name}</div><div class="fn">${m.old}→${m.new}</div><div class="fnote">${m.delta>0?'выше на '+m.delta:'ниже на '+(-m.delta)}</div></div>`).join('')}
      ${Object.keys(c.errors||{}).length?`<div class="frow"><div class="fl" style="color:#c0392b">ошибки движков</div><div class="fn"></div><div class="fnote">${JSON.stringify(c.errors)}</div></div>`:''}
    </div>`:''}
  </div>`;
}
// Everything above enters at the ranker with a hand-built intent, so it can only ever exonerate
// the ranker. This one types the phrase the user types.
let E2E=null, E2EBUSY=false, E2ET=null;
const E2E_DEFAULT='хочу выпить кофе, хочу поиграть в падл, хочу обсудить стартапы, хочу сходить на выставку, ищу с кем побегать утром, хочу поиграть в доту';
async function runE2E(){
  const who=($('#f_who')&&$('#f_who').value.trim())||'';
  const list=(($('#e_ph')&&$('#e_ph').value)||E2E_DEFAULT).split(',').map(s=>s.trim()).filter(Boolean);
  E2EBUSY=true; render();
  try{ E2E=await api('/api/admin/e2e',{method:'POST',body:JSON.stringify({self:who,phrases:list})}); }
  catch(e){ E2E={ok:false,error:String(e&&e.message||e)}; }
  E2EBUSY=false; render();
}
function e2eCard(){
  const e=E2E;
  return `<div class="card">
    <h3>Сквозная проверка: текст → бадди → выдача</h3>
    <div class="muted" style="margin-bottom:8px">Остальные проверки начинаются с готового интента и поэтому могут только оправдать ранжирование. Эта пишет ту же фразу, что пишет человек — и ловит две причины «одних и тех же людей», которые лежат ДО ранжирования: тема не разрезолвилась и интент вернулся неранжируемым.</div>
    <label>Фразы через запятую<input id="e_ph" value="${((E2ET!=null?E2ET:E2E_DEFAULT)).replace(/"/g,'&quot;')}"></label>
    <button class="primary" onclick="runE2E()" ${E2EBUSY?'disabled':''}>${E2EBUSY?'Гоняю (это долго — на каждую фразу зовётся модель)…':'Прогнать сквозь бадди'}</button>
    ${e&&e.error?`<div class="err">${e.error}</div>`:''}
    ${e&&e.ok?`<div class="funnel">
      ${_kv('фраз',e.phrases)}${_kv('с выдачей',e.withResults)}${_kv('разных людей',e.distinctPeople)}
      ${e.unrankable.length?`<div class="frow"><div class="fl" style="color:#c0392b">интент неранжируем</div><div class="fn">${e.unrankable.length}</div><div class="fnote">${e.unrankable.join(' · ')}</div></div>`:''}
      ${e.noTopics.length?`<div class="frow"><div class="fl" style="color:#c0392b">тема не разрезолвилась</div><div class="fn">${e.noTopics.length}</div><div class="fnote">${e.noTopics.join(' · ')}</div></div>`:''}
      ${e.errors.length?`<div class="frow"><div class="fl" style="color:#c0392b">ошибки</div><div class="fn">${e.errors.length}</div><div class="fnote">${e.errors.map(x=>x.phrase+': '+x.error).join(' · ')}</div></div>`:''}
      ${e.worstPair?`<div class="frow"><div class="fl">самая похожая пара выдач</div><div class="fn">${Math.round(e.worstPair.overlap*100)}%</div><div class="fnote">«${e.worstPair.a}» и «${e.worstPair.b}»${e.worstPair.shared.length?' · общие: '+e.worstPair.shared.join(', '):''}</div></div>`:''}
      ${(e.topRepeats||[]).map(r=>`<div class="frow sub"><div class="fl">повтор: <span onclick="openPerson('${String(r.name).replace(/'/g,"\\'")}')" style="text-decoration:underline;cursor:pointer">${r.name}</span></div><div class="fn">${r.times}</div><div></div></div>`).join('')}
    </div>
    <div class="sec">По фразам</div><div class="funnel">
      ${e.rows.map(r=>`<div class="frow"><div class="fl">«${r.phrase}»</div><div class="fn">${r.error?'—':r.n}</div>
        <div class="fnote">${r.error?('<span style="color:#c0392b">'+r.error+'</span>'):
          ((r.topics&&r.topics.length?'темы: '+r.topics.join(', '):'<span style="color:#c0392b">без темы</span>')
           +(r.rankable===false?' · <span style="color:#c0392b">неранжируем</span>':'')
           +(r.asked?(' · бадди переспросил, ходов: '+r.turns):''))}</div></div>
        ${(r.names&&r.names.length)?`<div class="frow sub"><div class="fl muted">${r.names.join(', ')}</div><div class="fn"></div><div></div></div>`:''}`).join('')}
    </div>`:''}
  </div>`;
}
let DIVT=null;

// ---------------------------------------------------------------- person card + cohorts (stage 2)
// The 3038-row table could show every field and still not answer the only two questions worth
// asking about a person: can anyone find them, and can they find anyone. Both are computed by the
// engine itself (/api/agent/admin/person) so the panel can never disagree with what search does.
let PERSON=null, PBUSY=false, PNAME='', COH=null, COHBUSY=false;
async function openPerson(name){
  PNAME=String(name||'').trim(); if(!PNAME) return;
  TAB='person'; PBUSY=true; PERSON=null; render();
  try{ PERSON=await api('/api/admin/person?name='+encodeURIComponent(PNAME)); }
  catch(e){ PERSON={ok:false,error:String(e&&e.message||e)}; }
  PBUSY=false; render();
}
async function loadCohorts(){
  COHBUSY=true; render();
  try{ COH=await api('/api/admin/cohorts'); }catch(e){ COH={ok:false,error:String(e&&e.message||e)}; }
  COHBUSY=false; render();
}
async function personVerb(verb){
  if(!PERSON||!PERSON.name) return;
  const label={pause:'поставить на паузу',unpause:'снять с паузы',unverify:'снять верификацию',
               verify:'верифицировать','fatigue':'сбросить счётчик предложений'}[verb]||verb;
  if(!confirm(label+': '+PERSON.name+'?')) return;
  const url=(verb==='fatigue')?'/api/admin/person/fatigue-reset':'/api/admin/person/verb';
  const body=(verb==='fatigue')?{name:PERSON.name}:{name:PERSON.name,verb:verb};
  const r=await api(url,{method:'POST',body:JSON.stringify(body)});
  if(r&&r.ok===false){ toast(r.error||'не вышло'); return; }
  toast('готово');
  await openPerson(PERSON.name);          // re-read from the engine: never trust the local echo
  load();
}
// The actual daily workflow: someone says «мне никогда не попадается X». Open X, name the person
// who is searching and what they asked for, and read which step dropped X — instead of guessing
// from a slate that simply doesn't contain them.
let PPAIR=null, PPAIRBUSY=false, PMINE=null, PMINEBUSY=false;
async function personPair(){
  if(!PERSON||!PERSON.name) return;
  const who=($('#pp_self')&&$('#pp_self').value.trim())||'', topic=($('#pp_topic')&&$('#pp_topic').value.trim())||'';
  if(!who){ toast('чей это поиск?'); return; }
  PPAIRBUSY=true; PPAIR=null; render();
  const intent={topics:topic?topic.split(',').map(s=>s.trim()).filter(Boolean):[],
                role:'meet', mode:'offline', time:'tomorrow'};
  try{ PPAIR=await api('/api/admin/explain',{method:'POST',
        body:JSON.stringify({self:who, intent:intent, candidate:PERSON.name})}); }
  catch(e){ PPAIR={ok:false,error:String(e&&e.message||e)}; }
  PPAIRBUSY=false; render();
}
async function personMine(){
  if(!PERSON||!PERSON.name) return;
  const topic=($('#pp_topic')&&$('#pp_topic').value.trim())||'';
  PMINEBUSY=true; PMINE=null; render();
  const intent={topics:topic?topic.split(',').map(s=>s.trim()).filter(Boolean):[],
                role:'meet', mode:'offline', time:'tomorrow'};
  try{ PMINE=await api('/api/admin/funnel',{method:'POST',
        body:JSON.stringify({self:PERSON.name, intent:intent})}); }
  catch(e){ PMINE={ok:false,error:String(e&&e.message||e)}; }
  PMINEBUSY=false; render();
}
function pairView(){
  const nm=PERSON&&PERSON.name||'';
  let out=`<div class="card"><h3>Проверить в конкретном запросе</h3>
    <div class="muted" style="margin-bottom:8px">«Мне никогда не попадается ${nm}» — вот на каком шаге ${nm} выпадает из этого поиска. И наоборот: кого находит сам ${nm}.</div>
    <label>Кто ищет<input id="pp_self" value="${(PPSELF||'').replace(/"/g,'&quot;')}" placeholder="Ivan"></label>
    <label>Тема<input id="pp_topic" value="${(PPTOPIC||'кофе').replace(/"/g,'&quot;')}" placeholder="кофе"></label>
    <button class="primary" onclick="personPair()" ${PPAIRBUSY?'disabled':''}>${PPAIRBUSY?'Считаю…':'Почему не показался'}</button>
    <button onclick="personMine()" ${PMINEBUSY?'disabled':''}>${PMINEBUSY?'Считаю…':'Кого находит сам'}</button>`;
  if(PPAIR&&(PPAIR.error||PPAIR.ok===false)) out+=`<div class="err">${PPAIR.error||'не вышло'}</div>`;
  const t=PPAIR&&PPAIR.trace;
  if(t){
    out+=`<div class="sec">${t.name}: ${t.shown?'<b style="color:#2f9e6b">показался бы</b>':'<b style="color:#c0392b">не показался</b>'}</div>
      <div class="funnel">
      ${(t.steps||[]).map(s=>`<div class="frow"><div class="fl">${s.step}</div>
        <div class="fn">${s.ok?'<span style="color:#2f9e6b">✓</span>':'<span style="color:#c0392b">✗</span>'}</div>
        <div class="fnote">${(s.detail!=null?String(s.detail):'')}</div></div>`).join('')}
      ${t.drop_reason?`<div class="frow"><div class="fl"><b>выпал</b></div><div class="fn"></div><div class="fnote" style="color:#c0392b">${t.drop_reason}</div></div>`:''}
      </div>`;
  }
  const f=PMINE&&PMINE.funnel;
  if(PMINE&&PMINE.error) out+=`<div class="err">${PMINE.error}</div>`;
  if(f){
    const gates=Object.keys(f.gates||{});
    out+=`<div class="sec">Что видит сам ${nm}</div><div class="funnel">
      ${_kv('в базе', f.pool)}${_kv('дошло до скоринга', f.eligible)}${_kv('в выдаче', f.slate)}
      ${gates.map(g=>`<div class="frow sub"><div class="fl">отсеяно: ${g}</div><div class="fn">${f.gates[g]}</div><div></div></div>`).join('')}
      ${PMINE.searcherKnown===false?`<div class="frow sub"><div class="fl" style="color:#b7791f">этого искателя нет в базе — искали с пустым профилем</div><div class="fn"></div><div></div></div>`:''}
      </div>`;
  }
  return out+'</div>';
}
let PPSELF='', PPTOPIC='кофе';
function _kv(k,v){return `<div class="frow"><div class="fl">${k}</div><div class="fn">${
  (v===null||v===undefined||v==='')?'<span class="muted">не собрано</span>':v}</div><div></div></div>`;}
function personView(){
  const p=PERSON;
  const search=`<div class="card"><h3>Карточка человека</h3>
    <div class="muted" style="margin-bottom:8px">Почему этого человека никто не находит — и почему он сам никого не находит. Это разные вопросы с разными ответами.</div>
    <label>Имя<input id="p_name" value="${String(PNAME||'').replace(/"/g,'&quot;')}" placeholder="Nadia"></label>
    <button class="primary" onclick="openPerson($('#p_name').value)" ${PBUSY?'disabled':''}>${PBUSY?'Смотрю…':'Открыть'}</button>
  </div>`;
  if(!p) return search+cohortsView();
  if(p.ok===false) return search+`<div class="card"><div class="err">${p.error||'не найден'}</div></div>`+cohortsView();
  const id=p.identity||{}, pol=p.policy||{}, qh=pol.quietHours||{};
  const badge=(p.blocks&&p.blocks.length)?'<b style="color:#c0392b">невидим</b>'
             :(p.inPool?'<b style="color:#2f9e6b">виден в поиске</b>':'<b style="color:#b7791f">не в пуле</b>');
  const list=(arr,cls)=>(arr&&arr.length)?arr.map(b=>`<div class="frow sub"><div class="fl" style="color:${cls}">${b.ru}</div><div class="fn"></div><div></div></div>`).join(''):
    '<div class="frow sub"><div class="fl muted">ничего</div><div class="fn"></div><div></div></div>';
  const rd=p.readiness||{};
  const rdRows=Object.keys(rd).map(k=>`<div class="frow sub"><div class="fl">${k}</div><div class="fn">${rd[k]}</div><div></div></div>`).join('');
  return search+`<div class="card">
    <h3>${p.name} — ${badge}</h3>
    <div class="funnel">
      ${_kv('источник строки', id.source)}
      ${_kv('город', id.area)}
      ${_kv('возраст', id.age===null||id.age===undefined?null:Math.round(id.age))}
      ${_kv('координаты', (id.lat===null||id.lon===null)?null:(id.lat.toFixed(3)+', '+id.lon.toFixed(3)))}
      ${_kv('радиус, км', id.radiusKm)}
      ${_kv('языки', (id.langs||[]).join(', '))}
      ${_kv('интересы', (id.interests||[]).join(', '))}
      ${_kv('верифицирован', id.verified?'да':'нет')}
      ${_kv('согласие на dating', id.datingOk?'да':'нет')}
      ${_kv('своих интентов', id.ownIntents)}
    </div>
    <div class="sec">Жёстко блокирует показ</div><div class="funnel">${list(p.blocks,'#c0392b')}</div>
    <div class="sec">Сужает — выпадает из части запросов</div><div class="funnel">${list(p.warnings,'#b7791f')}</div>
    <div class="sec">Его собственный поиск</div><div class="funnel">${list(p.outbound,'#b7791f')}</div>
    <div class="sec">Политика приёма</div>
    <div class="funnel">
      ${_kv('политика задана', pol.hasPolicy?'да':'нет — читается как «доступность не настроена»')}
      ${_kv('статус', pol.status)}
      ${_kv('разрешённые домены', (pol.allowedDomains===null||pol.allowedDomains===undefined)?null:(pol.allowedDomains.length?pol.allowedDomains.join(', '):'пусто — ни одного предложения'))}
      ${_kv('пассивные предложения', pol.passiveOutreach===false?'выключены':(pol.passiveOutreach===true?'разрешены':null))}
      ${_kv('лимит предложений / сутки', pol.budgetPer24h+(pol.budgetExplicit?' (задан явно)':' (по умолчанию)'))}
      ${_kv('получено за 24 ч', pol.received24h)}
      ${_kv('тихие часы', qh.start+'–'+qh.end+' (местное сейчас '+qh.localTime+(qh.inQuietNow?', СЕЙЧАС тихий час':'')+')')}
    </div>
    <div class="sec">Готовность по доменам</div><div class="funnel">${rdRows}</div>
    <div class="sec">Действия</div>
    <div class="muted" style="margin-bottom:8px">Три узких глагола вместо формы редактирования: форма пересохраняла всю строку и по дороге дописывала человеку интересы, язык и «сцену», которых он не указывал.</div>
    <button onclick="personVerb('pause')">На паузу</button>
    <button onclick="personVerb('unpause')">Снять с паузы</button>
    <button onclick="personVerb(${id.verified?"'unverify'":"'verify'"})">${id.verified?'Снять верификацию':'Верифицировать'}</button>
    <button onclick="personVerb('fatigue')">Сбросить счётчик предложений</button>
  </div>`+pairView()+cohortsView();
}
function cohortsView(){
  return `<div class="card"><h3>Когорты</h3>
    <div class="muted" style="margin-bottom:8px">Сохранённые запросы к базе. На эти вопросы таблица из 3000 строк не отвечает.</div>
    <button class="primary" onclick="loadCohorts()" ${COHBUSY?'disabled':''}>${COHBUSY?'Считаю…':'Пересчитать'}</button>
    ${COH&&COH.error?`<div class="err">${COH.error||COH._error}</div>`:''}
    ${COH&&COH.ok?`<div class="funnel">${COH.cohorts.map(c=>`
      <div class="frow"><div class="fl">${c.label}</div><div class="fn">${c.count}</div>
        <div class="fnote">${c.total?Math.round(c.count*100/c.total):0}%</div></div>
      ${c.sample.length?`<div class="frow sub"><div class="fl muted" style="cursor:pointer">${
        c.sample.slice(0,12).map(n=>`<span onclick="openPerson('${String(n).replace(/'/g,"\\'")}')" style="text-decoration:underline">${n}</span>`).join(', ')}${c.count>12?' …':''}</div><div class="fn"></div><div></div></div>`:''}
    `).join('')}</div>`:''}
  </div>`;
}

// ---------------------------------------------------------------- proposals registry (stage 3)
// Four different failures look identical from outside — отклонили, истекло без ответа, отозвано
// политикой на приёме, и вообще не создалось. Only the trace tells them apart.
let PROPS=null, PROPBUSY=false, PROPVIEW='all';
async function loadProposals(){
  PROPBUSY=true; render();
  try{ PROPS=await api('/api/admin/proposals'); }catch(e){ PROPS={ok:false,error:String(e&&e.message||e)}; }
  PROPBUSY=false; render();
}
function setPropView(v){PROPVIEW=v;render();}
function proposalsView(){
  const p=PROPS;
  const head=`<div class="card"><h3>Реестр предложений</h3>
    <div class="muted" style="margin-bottom:8px">Кто кому предложил встречу и что с этим стало. Только чтение — этот файл пишется без tmp+replace, читатель, который пишет, обрежет запрос на лету.</div>
    <button class="primary" onclick="loadProposals()" ${PROPBUSY?'disabled':''}>${PROPBUSY?'Читаю…':'Обновить'}</button>
    ${p&&(p.error||p._error)?`<div class="err">${p.error||p._error}</div>`:''}
    ${p&&p.ok?`<div class="funnel">
      ${_kv('всего', p.total)}
      ${_kv('истекает меньше чем через 12 ч', p.expiringSoon)}
      ${_kv('истекло без ответа', p.expiredUnanswered)}
      ${_kv('отозвано политикой', p.policyRevoked)}
      ${Object.keys(p.byStatus||{}).map(k=>`<div class="frow sub"><div class="fl">${k}</div><div class="fn">${p.byStatus[k]}</div><div></div></div>`).join('')}
    </div>
    <div style="margin-top:10px">
      ${['all|все','soon|истекает <12ч','revoked|отозвано политикой','expired|истекло без ответа']
        .map(x=>{const[k,l]=x.split('|');return `<button class="${PROPVIEW===k?'primary':''}" onclick="setPropView('${k}')">${l}</button>`;}).join('')}
    </div>`:''}
  </div>`;
  if(!p||!p.ok) return head;
  let rows=p.requests||[];
  if(PROPVIEW==='soon') rows=rows.filter(r=>r.expiresInHours!==null&&r.expiresInHours>0&&r.expiresInHours<12&&(r.status==='pending'||r.status==='sent'));
  if(PROPVIEW==='revoked') rows=rows.filter(r=>r.policyRevoked);
  if(PROPVIEW==='expired') rows=rows.filter(r=>r.expired);
  if(!rows.length) return head+`<div class="card"><div class="muted">Ни одного предложения в этой выборке.</div></div>`;
  return head+`<div class="card"><h3>${rows.length} предложени${rows.length===1?'е':'й'}</h3>
    <div class="funnel">${rows.slice(0,120).map(r=>`
      <div class="frow"><div class="fl"><span onclick="openPerson('${String(r.from||'').replace(/'/g,"\\'")}')" style="text-decoration:underline;cursor:pointer">${r.from||'?'}</span> → <span onclick="openPerson('${String(r.to||'').replace(/'/g,"\\'")}')" style="text-decoration:underline;cursor:pointer">${r.to||'?'}</span></div>
        <div class="fn">${r.status}</div>
        <div class="fnote">${r.ageHours!==null?r.ageHours+' ч назад':''}${r.expiresInHours!==null?' · истекает через '+r.expiresInHours+' ч':''}${r.expired?' · <b style="color:#c0392b">истекло</b>':''}</div></div>
      ${r.note?`<div class="frow sub"><div class="fl muted">«${r.note}»</div><div class="fn"></div><div></div></div>`:''}
      ${r.trace.length?`<div class="frow sub"><div class="fl muted">след: ${r.trace.join(' → ')}</div><div class="fn"></div><div></div></div>`:''}
      ${r.configVersion?`<div class="frow sub"><div class="fl muted">конфиг: ${r.configVersion}</div><div class="fn"></div><div></div></div>`:''}
    `).join('')}</div>
    ${rows.length>120?`<div class="muted">показаны первые 120 из ${rows.length}</div>`:''}
  </div>`;
}
const VIBES=["calm","energetic","intellectual","creative","competitive","chill","social","introvert","extrovert"];
const ROLES=["play","watch","discuss","practise","attend","meet"];

async function load(){const r=await api('/api/admin/users');USERS=r.users||[];render();loadHealth();}
// What system am I looking at. Everything here already existed behind /api/agent/weights and
// /api/agent/pool — the panel had simply never asked.
async function loadHealth(){ try{ HEALTH=await api('/api/admin/health'); }catch(e){ HEALTH={error:String(e&&e.message||e)}; } render(); }
function healthBar(){
  if(!HEALTH) return '<div class="hbar muted">проверяю движок…</div>';
  const c=HEALTH.core||{}, st=HEALTH.store||{}, src=HEALTH.bySource||{};
  const bad=v=>`<b style="color:#c0392b">${v}</b>`, good=v=>`<b>${v}</b>`;
  // Unreachable is not the same as disabled. Painting a red «ВЫКЛЮЧЕН» because the request failed is
  // the false alarm that teaches an operator to ignore this bar.
  const engine = (HEALTH.ok===false || !HEALTH.core)
      ? `<b style="color:#b7791f">движок не отвечает${HEALTH.error?' · '+HEALTH.error:''}</b>`
      : (c.enabled ? good('Core v2 '+(c.config_version||'')+' · '+(c.config_sha||''))
                   : bad('Core v2 ВЫКЛЮЧЕН — легаси-скорер'+(c.error?(' · '+c.error):'')));
  const parts=Object.keys(src).sort((a,b)=>src[b]-src[a]).map(k=>k+' '+src[k]).join(' · ');
  // The admin's own default store path differs from onboarding's; a restart without KLEAL_USERS
  // would split the store in two and nothing would say so. So it says so.
  const split = (st.path && HEALTH.adminStore && st.path!==HEALTH.adminStore);
  const age = st.mtime ? Math.round((Date.now()/1000-st.mtime)/60) : null;
  return `<div class="hbar">${engine}
    <span class="sep">·</span>ищет по <b>${HEALTH.count!=null?HEALTH.count:'?'}</b>${parts?` <span class="muted">(${parts})</span>`:''}${
      (HEALTH.count!=null&&USERS.length>HEALTH.count)?` <span class="muted">— ещё ${USERS.length-HEALTH.count} loadtest исключены из поиска</span>`:''}
    <span class="sep">·</span><span class="muted" title="${st.path||''}">хранилище ${st.path?st.path.split('/').slice(-2).join('/'):'?'}${age!=null?', изменено '+age+' мин назад':''}</span>
    ${split?`<span class="sep">·</span>${bad('РАСХОЖДЕНИЕ ПУТЕЙ: движок и панель читают разные файлы')}`:''}
    ${HEALTH.error?`<span class="sep">·</span>${bad(HEALTH.error)}`:''}</div>`;
}
const gv=id=>{const e=$(id);return e?e.value:'';}, gc=id=>{const e=$(id);return e?e.checked:false;};
async function saveUser(){
  const u={name:gv('#f_name'),age:+gv('#f_age')||28,area:gv('#f_area'),interests:gv('#f_int'),vibe:gv('#f_vibe'),
    langs:gv('#f_lang'),km:+gv('#f_km')||2,role:gv('#f_role'),
    dealBreakers:gv('#f_deal'),entities:gv('#f_ent'),
    ownIntentType:gv('#f_oit'),ownIntentTopics:gv('#f_oitop'),ownIntentRole:gv('#f_oirole'),
    open:gc('#f_open'),verified:gc('#f_ver'),datingOk:gc('#f_dat'),paused:gc('#f_pau'),blocksMe:gc('#f_blk'),
    pending:+gv('#f_pend')||0,lastActiveDays:+gv('#f_last')||0,declinedOwnerDaysAgo:gv('#f_cool')};
  if(!u.name.trim()){toast('Name required');return;}
  if(editing){await api('/api/admin/user/'+editing,{method:'POST',body:JSON.stringify(u)});toast('Updated');}
  else{await api('/api/admin/users',{method:'POST',body:JSON.stringify(u)});toast('User added');}
  editing=null;await load();
}
function editRow(id){const u=USERS.find(x=>x.id===id);if(!u)return;editing=id;render();setTimeout(()=>{
  const sv=(id,val)=>{const e=$(id);if(e)e.value=(val==null?'':val);}, sc=(id,val)=>{const e=$(id);if(e)e.checked=!!val;};
  sv('#f_name',u.name);sv('#f_age',u.age);sv('#f_area',u.area);sv('#f_int',(u.interests||[]).join(', '));
  sv('#f_vibe',u.vibe);sv('#f_lang',(u.langs||[]).join(', '));sv('#f_km',u.km);sv('#f_role',u.role);
  sv('#f_deal',(u.dealBreakers||[]).join(', '));sv('#f_ent',(u.entities||[]).join(', '));
  const oi=(u.intents||[])[0]||{};sv('#f_oit',oi.type||'social');sv('#f_oitop',(oi.topics||[]).join(', '));sv('#f_oirole',oi.role||'meet');
  sc('#f_open',u.open);sc('#f_ver',u.verified);sc('#f_dat',u.datingOk);sc('#f_pau',u.paused);sc('#f_blk',u.blocksMe);
  sv('#f_pend',u.pending);sv('#f_last',u.lastActiveDays);sv('#f_cool',u.declinedOwnerDaysAgo);
  window.scrollTo(0,0);},0);}
function toggleAdv(){const a=$('#advbox');if(a)a.style.display=(a.style.display==='none'?'block':'none');}
async function delRow(id){const u=USERS.find(x=>x.id===id);if(!confirm('Delete '+(u?u.name:'user')+'?'))return;await api('/api/admin/user/'+id+'/delete',{method:'POST'});toast('Deleted');await load();}
async function toggle(id,field){const u=USERS.find(x=>x.id===id);if(!u)return;await api('/api/admin/user/'+id,{method:'POST',body:JSON.stringify({[field]:!u[field]})});await load();}

function gate(){
  $('#app').innerHTML=`<div class="top"><span class="logo">kleal</span><span class="pill">admin · test mode</span></div>
    <div class="gate card"><h2>Admin sign-in</h2><p class="muted" style="margin-bottom:12px">Enter the admin token.</p>
    <input id="tok" type="password" placeholder="Admin token" style="width:100%;margin-bottom:10px"><br>
    <button onclick="tryLogin()">Enter</button></div>`;
  setTimeout(()=>{const i=$('#tok');i.focus();i.onkeydown=e=>{if(e.key==='Enter')tryLogin();};},0);
}
async function tryLogin(){TOK=$('#tok').value.trim();const r=await fetch('/api/admin/ping',{headers:{'X-Admin-Token':TOK}}).then(x=>x.json()).catch(()=>({}));
  if(r&&r.ok){sessionStorage.setItem('kleal_admin_tok',TOK);load();}else{toast('Wrong token');}}

// ============================ Matching lab ============================
// Runs REAL searches through the matching service (same engine the app uses) and shows the
// per-feature decision trace, so a tester can see exactly why someone did or didn't match.
const PRESETS=[
  ['Кофе (RU)',{topics:'кофе',type:'social',role:'meet',time:'Today evening'}],
  ['Coffee (EN)',{topics:'coffee',type:'social',role:'meet',time:'Today evening'}],
  ['Дота вечером',{topics:'дота, dota 2',type:'gaming',role:'play',time:'tonight'}],
  ['Падель завтра',{topics:'падель, padel',type:'sport',role:'play',time:'Tomorrow 19:00'}],
  ['Прогулка',{topics:'прогулка, погулять',type:'social',role:'meet',time:'Today evening'}],
  ['Испанский',{topics:'испанский, практика языка',type:'language',role:'practise',time:'Flexible'}],
  ['Стартапы + AI',{topics:'стартапы, ai, кофе',type:'networking',role:'discuss',time:'This week'}],
  ['Смотреть Барсу',{topics:'смотреть футбол, барса',type:'social',role:'watch',time:'tonight'}],
  ['Книги',{topics:'книги, кофе',type:'social',role:'discuss',time:'This weekend'}],
  ['Свидание',{topics:'прогулки, кино',type:'dating',role:'meet',time:'This weekend'}],
];
// Was a hardcoded epoch (a fixed moment in July 2025), so "quiet hours" tested a date in the past
// rather than the rule. Pin 23:00 of TODAY instead — still deterministic within a session, still
// inside the 22:00-09:00 window, but it moves with the calendar.
function nowQuiet(){ const d=new Date(); d.setHours(23,0,0,0); return Math.floor(d.getTime()/1000); }
function labIntent(){
  const topics=gv('#l_topics').split(',').map(s=>s.trim()).filter(Boolean);
  const it={topics:topics,type:gv('#l_type'),role:gv('#l_role'),mode:gv('#l_mode'),time:gv('#l_time')||'Flexible'};
  const rk=+gv('#l_radius'); if(rk>0) it.radiusKm=rk;
  const rl=gv('#l_langs').split(',').map(s=>s.trim()).filter(Boolean); if(rl.length) it.requiredLanguages=rl;
  const mn=+gv('#l_minage'), mx=+gv('#l_maxage'); if(mn>0) it.minAge=mn; if(mx>0) it.maxAge=mx;
  if(gc('#l_ver')) it.verifiedOnly=true;
  if(gc('#l_consent')) it.broadConsent=true;
  if(gc('#l_exact')) it.exactMatchRequired=true;
  if(!gc('#l_adj')) it.adjacentAllowed=false;
  return it;
}
function labBody(extra){
  const b={self:gv('#l_self'),intent:labIntent()};
  if(gc('#l_quiet')) b.now=nowQuiet();
  return Object.assign(b,extra||{});
}
function applyPreset(i){const p=PRESETS[i][1];
  const s=(id,v)=>{const e=$(id);if(e)e.value=v;};
  s('#l_topics',p.topics);s('#l_type',p.type);s('#l_role',p.role);s('#l_time',p.time);
  runLab();
}
// Signature of the form as it was when the search ran. Without it a stale result silently looks
// like the answer to whatever is typed now (type "Рыбалка" over a coffee run -> coffee people).
function labSig(){const b=labBody();return JSON.stringify([b.self,b.intent,b.now||0]);}
async function runLab(){
  // READ THE FORM FIRST. render() rebuilds the DOM and restores field values asynchronously
  // (setTimeout 0), so reading after it returned the freshly-rendered default — every search
  // silently ran on "кофе" no matter what was typed.
  const sig=labSig(), shown=gv('#l_topics'), body=labBody();
  LAB.running=true;LAB.err=null;LAB.trace=null;render();
  try{
    const r=await api('/api/admin/match-test',{method:'POST',body:JSON.stringify(body)});
    LAB.res=r.candidates||[];LAB.err=r.error||null;LAB.lastIntent=r.intent||null;
    LAB.searcher=r.searcher||null;LAB.searcherKnown=!!r.searcherKnown;
    LAB.sig=sig;LAB.ranTopics=shown;LAB.ranWhen=(r.intent&&r.intent.time)||'';
  }catch(e){
    // the banner must never be left spinning: say what went wrong and keep the old table visible
    LAB.err='Матчинг-сервис не ответил ('+String(e&&e.message||e)+'). Нажми «Запустить матчинг».';
  }
  // whatever happened, this run is over — stale is recomputed from the CURRENT form
  LAB.stale=(!!LAB.sig&&labSig()!==LAB.sig);
  LAB.running=false;render();
}
async function explain(name){
  LAB.traceFor=name;LAB.trace='loading';render();
  try{
    const r=await api('/api/admin/explain',{method:'POST',body:JSON.stringify(labBody({candidate:name}))});
    LAB.trace=r.ok?(r.trace||null):{error:r.error||'failed'};
  }catch(e){LAB.trace={error:String(e)};}
  render();
}
function explainTyped(){const n=gv('#l_who').trim();if(!n){toast('Впиши имя человека');return;}explain(n);}
function traceView(t){
  if(t==='loading') return '<div class="trace muted">Считаю трейс…</div>';
  if(!t) return '';
  if(t.error) return `<div class="trace"><div class="drop">${esc(t.error)}</div></div>`;
  const steps=(t.steps||[]).map(s=>`<div class="stepr"><span class="${s.ok?'ok':'bad'}">${s.ok?'✓':'✗'}</span>
      <b>${esc(s.step)}</b><span class="muted">${esc(s.detail||'')}</span></div>`).join('');
  const feats=(t.features||[]).map(f=>`<tr>
      <td>${esc(f.label_ru)}</td>
      <td><span class="fstate ${f.state}">${f.state}</span></td>
      <td>${f.value==null?'<span class="muted">prior '+f.prior+'</span>':f.value}</td>
      <td class="muted">${f.weight.toFixed(2)}</td>
      <td class="muted wrap2">${esc(f.detail||'')}</td></tr>`).join('');
  const ab=t.a_to_b||{}, ba=t.b_to_a||{};
  return `<div class="trace">
    <div class="bar"><h2 style="margin:0">Трейс: ${esc(t.name)}</h2>
      <span class="muted" style="font-size:12px">домен ${esc(t.domain||'—')} · ${esc(t.config_version||'')}</span></div>
    ${t.drop_reason?`<div class="drop">Не показан: ${esc(t.drop_reason)}</div>`:
      `<div><span class="metric">Уровень <b>${esc(t.band_ru||t.band||'')}</b></span>
        <span class="metric">Tier <b>${esc(t.tier||'')}</b></span>
        <span class="metric">Готовность <b>${esc(t.readiness_ru||t.readiness||'')}</b></span>
        <span class="metric">Можно писать <b class="${t.can_outreach?'yes':'no'}">${t.can_outreach?'да':'нет'}</b></span></div>`}
    <div class="sec">Шаги решения</div>${steps}
    ${feats?`<div class="sec">Признаки (7 групп, спека §6.1)</div><div class="tabler"><table>
      <thead><tr><th>Группа</th><th>Состояние</th><th>Значение</th><th>Вес</th><th>Детали</th></tr></thead>
      <tbody>${feats}</tbody></table></div>`:''}
    ${ab.mean!=null?`<div class="sec">Итог</div>
      <span class="metric">A→B mean <b>${ab.mean}</b></span>
      <span class="metric">coverage <b>${ab.coverage}</b></span>
      <span class="metric">lcb <b>${ab.lcb}</b></span>
      <span class="metric">B→A lcb <b>${ba.lcb!=null?ba.lcb:'—'}</b></span>
      <span class="metric">взаимность <b>${t.reciprocal!=null?t.reciprocal:'—'}</b></span>
      ${(ab.unknowns||[]).length?`<div class="hint">Не хватает данных: ${ab.unknowns.map(esc).join(', ')}</div>`:''}
      ${t.gap_ru?`<div class="hint">Компромисс: ${esc(t.gap_ru)}</div>`:''}`:''}
  </div>`;
}
function labView(){
  const opts=USERS.slice().sort((a,b)=>String(a.name).localeCompare(String(b.name)))
    .map(u=>`<option value="${esc(u.name)}">${esc(u.name)}${(u.intents||[]).length?' ↔':''}</option>`).join('');
  const rows=(LAB.res||[]).map((c,i)=>`<tr>
      <td class="muted">${i+1}</td>
      <td><b>${esc(c.name)}</b></td>
      <td><span class="tierb ${esc(c.tier)}">${esc(c.tier)}</span></td>
      <td><span class="band ${esc(c.band||'')}">${esc(c.band_ru||c.band||'')}</span></td>
      <td><span class="rdy ${esc(c.readiness||'')}">${esc(c.readiness_ru||c.readiness||'')}</span></td>
      <td class="${c.can_outreach?'yes':'no'}">${c.can_outreach?'да':'нет'}</td>
      <td>${c.score}</td>
      <td class="muted">${c.coverage!=null?c.coverage:'—'}</td>
      <td class="wrap2">${(c.reasons_ru||c.reasons||[]).slice(0,3).map(esc).join(' · ')}
        ${c.gap_ru?`<div class="hint">${esc(c.gap_ru)}</div>`:''}</td>
      <td class="wrap2 muted">${(c.interests||[]).slice(0,4).map(i=>`<span class="tag">${esc(i)}</span>`).join('')}</td>
      <td style="text-align:right"><button class="ghost mini" onclick="explain('${esc(c.name).replace(/'/g,"\\'")}')">Трейс</button></td>
    </tr>`).join('');
  return `<div class="wrap">
    <div class="card"><h2>Кто ищет</h2>
      <div class="row">
        <div style="flex:1;min-width:240px"><label>Искатель (профиль берётся из базы)</label>
          <select id="l_self" style="width:100%">${opts}</select>
          <div class="hint">Интересы, гео, вайб и языки берутся из его карточки. Сам себя он никогда не найдёт.</div></div>
        <label class="chk" style="align-self:end;padding-bottom:8px"><input id="l_quiet" type="checkbox"> ночь (тихие часы 23:00)</label>
      </div>
      <div class="sec">Запрос</div>
      <div class="row">
        <div style="flex:1;min-width:260px"><label>Темы (через запятую)</label><input id="l_topics" style="width:100%" placeholder="кофе, книги" value="кофе"></div>
        <div><label>Тип</label><select id="l_type">${['social','gaming','sport','language','networking','dating','dinner','other'].map(v=>`<option>${v}</option>`).join('')}</select></div>
        <div><label>Роль</label><select id="l_role">${ROLES.map(v=>`<option${v==='meet'?' selected':''}>${v}</option>`).join('')}</select></div>
        <div><label>Режим</label><select id="l_mode"><option>offline</option><option>online</option></select></div>
        <div><label>Время</label><input id="l_time" style="min-width:130px" value="Today evening"></div>
      </div>
      <div class="adv"><span class="advtog" onclick="toggleAdv2()">▸ Границы поиска (гейты и согласия)</span>
        <div id="advbox2" style="display:none;margin-top:10px"><div class="row">
          <div><label>Радиус, км</label><input id="l_radius" type="number" style="min-width:100px" placeholder="—"></div>
          <div><label>Обязательные языки</label><input id="l_langs" style="min-width:130px" placeholder="es"></div>
          <div><label>Возраст от</label><input id="l_minage" type="number" style="min-width:100px" placeholder="—"></div>
          <div><label>до</label><input id="l_maxage" type="number" style="min-width:80px" placeholder="—"></div>
        </div><div class="row" style="margin-top:8px">
          <label class="chk"><input id="l_ver" type="checkbox"> только верифицированные</label>
          <label class="chk"><input id="l_consent" type="checkbox"> согласие на широкий поиск (T2 outreach)</label>
          <label class="chk"><input id="l_exact" type="checkbox"> только точные совпадения</label>
          <label class="chk"><input id="l_adj" type="checkbox" checked> разрешить смежные (T3)</label>
        </div></div>
      </div>
      <div class="row" style="margin-top:12px">
        ${PRESETS.map((p,i)=>`<button class="preset" onclick="applyPreset(${i})">${esc(p[0])}</button>`).join('')}
      </div>
      <div class="row" style="margin-top:12px;justify-content:space-between">
        <div style="display:flex;gap:8px;align-items:end">
          <div><label>Проверить конкретного человека</label><input id="l_who" placeholder="имя из базы" style="min-width:200px"></div>
          <button class="ghost" onclick="explainTyped()">Почему не нашёлся?</button>
        </div>
        <button onclick="runLab()">${LAB.running?'Ищу…':'Запустить матчинг'}</button>
      </div>
    </div>
    ${LAB.err?`<div class="card"><div class="drop">Ошибка: ${esc(LAB.err)}</div></div>`:''}
    ${LAB.res?`<div class="card" ${LAB.stale?'style="opacity:.55"':''}>
      ${(LAB.stale||LAB.running)?`<div class="drop" style="margin-bottom:12px">${LAB.running?'Обновляю результат…':'Форма изменена — обновлю через секунду'} (показан прошлый — «${esc(LAB.ranTopics||'')}»)</div>`:''}
      <div class="bar"><h2 style="margin:0">Результат по запросу «${esc(LAB.ranTopics||'')}» — ${LAB.res.length} кандидат(ов)</h2>
        <span class="muted" style="font-size:12px">${LAB.searcher?('от лица '+esc(LAB.searcher.name)):''}
          ${LAB.ranWhen?(' · '+esc(LAB.ranWhen)):''}${LAB.searcherKnown===false?' · профиль не из базы':''}</span></div>
      ${LAB.res.length?`<div class="tabler"><table>
        <thead><tr><th>#</th><th>Имя</th><th>Tier</th><th>Уровень</th><th>Готовность</th><th>Писать</th>
          <th>Score</th><th>Cov</th><th>Почему</th><th>Интересы</th><th></th></tr></thead>
        <tbody>${rows}</tbody></table></div>`
        :`<p class="muted" style="padding:14px 2px">Никто не подошёл. Это честный ответ движка: значит, у людей в базе нет реального пересечения с запросом (или их срезали гейты). Впиши имя ниже и нажми «Почему не нашёлся?», чтобы увидеть причину по конкретному человеку.</p>`}
    </div>`:''}
    ${traceView(LAB.trace)}
    <p class="muted" style="font-size:12px">Лаборатория гоняет тот же движок, что и приложение (Matching Core v2). Ничего не пишется в базу и никому не отправляются предложения.</p>
  </div>`;
}
function toggleAdv2(){const a=$('#advbox2');if(a)a.style.display=(a.style.display==='none'?'block':'none');}
function setTab(t){TAB=t;render();}
// Editing any field re-runs the search automatically (debounced). Marking the old result "stale"
// and waiting for a click was still a trap: you type "рыбалка" and the coffee table just sits there.
let LAB_T=null;
function labTouched(){
  if(!LAB.sig&&!LAB.res)return;
  const st=(labSig()!==LAB.sig);
  if(st!==LAB.stale){LAB.stale=st;render();}
  clearTimeout(LAB_T);
  LAB_T=setTimeout(()=>{if(labSig()!==LAB.sig)runLab();},600);
}
function wireLab(){
  ['l_self','l_topics','l_type','l_role','l_mode','l_time','l_radius','l_langs','l_minage','l_maxage']
    .forEach(id=>{const e=$('#'+id);if(!e)return;e.oninput=labTouched;e.onchange=labTouched;});
  ['l_quiet','l_ver','l_consent','l_exact','l_adj'].forEach(id=>{const e=$('#'+id);if(e)e.onchange=labTouched;});
  const t=$('#l_topics');if(t)t.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();runLab();}};
  const w=$('#l_who');if(w)w.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();explainTyped();}};
}

function render(){
  if(!TOK) return gate();          // no token -> the sign-in card, not a console that cannot load
  const q=Q.toLowerCase();
  const rows=USERS.filter(u=>!q||(u.name+' '+(u.interests||[]).join(' ')+' '+u.vibe).toLowerCase().includes(q));
  const flag=(u,f,label,warn)=>`<span class="flag ${warn?'warn':''} ${u[f]?'on':''}" title="${label}" onclick="toggle('${u.id}','${f}')">${u[f]?(warn?'❚':'✓'):'·'}</span>`;
  // keep the lab form's current values across re-renders (render() rebuilds the whole DOM)
  const LF={};
  if(TAB==='lab'){['l_self','l_topics','l_type','l_role','l_mode','l_time','l_radius','l_langs',
    'l_minage','l_maxage','l_who'].forEach(id=>{const e=$('#'+id);if(e)LF[id]=e.value;});
    ['l_quiet','l_ver','l_consent','l_exact','l_adj'].forEach(id=>{const e=$('#'+id);if(e)LF[id]=e.checked;});}
  const head=`<div class="top"><span class="logo">kleal</span><span class="pill">admin · test mode</span>
    <div class="tabs">
      <button class="tab ${TAB==='users'?'on':''}" onclick="setTab('users')">Люди</button>
      <button class="tab ${TAB==='lab'?'on':''}" onclick="setTab('lab')">Матчинг-лаборатория</button>
      <button class="tab ${TAB==='funnel'?'on':''}" onclick="setTab('funnel')">Диагностика</button>
      <button class="tab ${TAB==='person'?'on':''}" onclick="setTab('person')">Карточка</button>
      <button class="tab ${TAB==='props'?'on':''}" onclick="setTab('props')">Предложения</button>
    </div>
    <span class="muted" style="margin-left:auto" title="строк в файле; движок ищет не по всем — см. полосу ниже">${USERS.length} строк в файле</span>
    </div>${healthBar()}`;
  if(TAB==='person'){
    // render() rebuilds the DOM, so the three inputs have to survive their own re-render —
    // otherwise typing a searcher's name and clicking would search for an empty string.
    const pv=$('#p_name'); const keep=pv?pv.value:null;
    const s1=$('#pp_self'); if(s1) PPSELF=s1.value;
    const s2=$('#pp_topic'); if(s2) PPTOPIC=s2.value;
    const ae=document.activeElement, aid=(ae&&ae.id)||'';
    $('#app').innerHTML=head+'<div class="wrap">'+personView()+'</div>';
    setTimeout(()=>{const e=$('#p_name'); if(e&&keep!=null&&!e.value)e.value=keep;
      if(e)e.onkeydown=ev=>{if(ev.key==='Enter'){ev.preventDefault();openPerson(e.value);}};
      const a=$('#pp_self'); if(a){ if(PPSELF)a.value=PPSELF; a.oninput=()=>{PPSELF=a.value;};
        a.onkeydown=ev=>{if(ev.key==='Enter'){ev.preventDefault();personPair();}}; }
      const b=$('#pp_topic'); if(b){ if(PPTOPIC)b.value=PPTOPIC; b.oninput=()=>{PPTOPIC=b.value;};
        b.onkeydown=ev=>{if(ev.key==='Enter'){ev.preventDefault();personPair();}}; }
      if(aid){const f=$('#'+aid); if(f)f.focus();}
      if(!COH&&!COHBUSY)loadCohorts();},0);
    return;
  }
  if(TAB==='props'){
    $('#app').innerHTML=head+'<div class="wrap">'+proposalsView()+'</div>';
    setTimeout(()=>{if(!PROPS&&!PROPBUSY)loadProposals();},0);
    return;
  }
  if(TAB==='funnel'){
    // same caret discipline as the lab: render() rebuilds everything
    ['who','topics','role','mode'].forEach(k=>{const e=$('#f_'+k); if(e) LFF[k]=e.value;});
    const ae2=document.activeElement, aid2=(ae2&&ae2.id)||'';
    const de=$('#d_topics'); if(de) DIVT=de.value;
    const ee=$('#e_ph'); if(ee) E2ET=ee.value;
    $('#app').innerHTML=head+'<div class="wrap">'+funnelView()+diagCards()+'</div>';
    setTimeout(()=>{ ['who','topics','role','mode'].forEach(k=>{const e=$('#f_'+k); if(e&&LFF[k]!=null) e.value=LFF[k];});
      const de2=$('#d_topics'); if(de2&&DIVT!=null) de2.value=DIVT;
      const ee2=$('#e_ph'); if(ee2&&E2ET!=null) ee2.value=E2ET;
      if(aid2){const f=$('#'+aid2); if(f) f.focus();} },0);
    return;
  }
  if(TAB==='lab'){
    // render() rebuilds the DOM, so remember where the caret was — otherwise auto-refresh would
    // yank the cursor out of the field mid-word.
    const ae=document.activeElement, aid=(ae&&ae.id)||'', asel=(ae&&ae.selectionStart!=null)?[ae.selectionStart,ae.selectionEnd]:null;
    $('#app').innerHTML=head+labView();
    setTimeout(()=>{Object.keys(LF).forEach(id=>{const e=$('#'+id);if(!e)return;
      if(typeof LF[id]==='boolean')e.checked=LF[id];else e.value=LF[id];});
      if(aid){const f=$('#'+aid);if(f){f.focus();if(asel&&f.setSelectionRange){try{f.setSelectionRange(asel[0],asel[1]);}catch(_e){}}}}
      const adv=$('#advbox2');
      if(adv&&(LF.l_radius||LF.l_langs||LF.l_minage||LF.l_maxage||LF.l_ver||LF.l_consent||LF.l_exact||LF.l_adj===false))adv.style.display='block';
      const t=$('#l_topics'); if(t&&!t.value)t.value='кофе';
      wireLab();},0);
    return;
  }
  $('#app').innerHTML=head+`
  <div class="wrap">
    <div class="card"><h2>${editing?'Edit user':'Add user'}</h2>

      <div class="sec">Basics &amp; location</div>
      <div class="row">
        <div><label>Name</label><input id="f_name"></div>
        <div><label>Age</label><input id="f_age" type="number" style="min-width:74px" value="28"></div>
        <div><label>Area / city</label><input id="f_area" style="min-width:130px" placeholder="Barcelona"></div>
        <div><label>Distance km</label><input id="f_km" type="number" step="0.1" style="min-width:90px" value="2"></div>
        <div><label>Languages</label><input id="f_lang" style="min-width:110px" placeholder="en, es" value="en"></div>
      </div>

      <div class="sec">Interests &amp; personality</div>
      <div class="row">
        <div style="flex:1;min-width:220px"><label>Interests (comma)</label><input id="f_int" style="width:100%" placeholder="chess, coffee"></div>
        <div><label>Preferred role</label><select id="f_role">${ROLES.map(v=>`<option>${v}</option>`).join('')}</select></div>
        <div><label>Vibe</label><select id="f_vibe">${VIBES.map(v=>`<option>${v}</option>`).join('')}</select></div>
        <div style="flex:1;min-width:200px"><label>Communities (comma)</label><input id="f_ent" style="width:100%" placeholder="Casa del Chess club"></div>
      </div>

      <div class="sec">Active intent — makes them a reciprocal (T0) match</div>
      <div class="row">
        <div><label>Intent type</label><select id="f_oit"><option value="">— none —</option>${['sport','gaming','networking','language','dating','social','other'].map(v=>`<option>${v}</option>`).join('')}</select></div>
        <div style="flex:1;min-width:220px"><label>Intent topics (comma)</label><input id="f_oitop" style="width:100%" placeholder="chess (leave blank for no active intent)"></div>
        <div><label>Intent role</label><select id="f_oirole">${ROLES.map(v=>`<option>${v}</option>`).join('')}</select></div>
      </div>

      <div class="sec">Safety &amp; matching flags</div>
      <div class="row">
        <label class="chk"><input id="f_open" type="checkbox" checked> open to meet</label>
        <label class="chk"><input id="f_ver" type="checkbox" checked> verified</label>
        <label class="chk"><input id="f_dat" type="checkbox"> dating opt-in</label>
        <label class="chk"><input id="f_pau" type="checkbox"> paused</label>
        <div style="flex:1;min-width:200px"><label>Deal-breakers (comma)</label><input id="f_deal" style="width:100%" placeholder="no smokers, no late nights"></div>
      </div>

      <div class="adv"><span class="advtog" onclick="toggleAdv()">▸ Advanced state (anti-spam / activity)</span>
        <div id="advbox" style="display:none;margin-top:10px"><div class="row">
          <div><label>Open invites (pending)</label><input id="f_pend" type="number" style="min-width:120px" value="0" title="≥6 = overloaded, gated out"></div>
          <div><label>Last active (days ago)</label><input id="f_last" type="number" style="min-width:130px" value="0" title="≤3 = 'recently active' bonus"></div>
          <div><label>Declined me (days ago)</label><input id="f_cool" type="number" style="min-width:150px" placeholder="blank = no" title="<7 = cooldown, gated out"></div>
          <label class="chk" style="align-self:end;padding-bottom:8px"><input id="f_blk" type="checkbox"> blocks me</label>
        </div></div>
      </div>

      <div class="row" style="margin-top:14px;justify-content:flex-end">
        ${editing?`<button class="ghost" onclick="editing=null;render()">Cancel</button>`:''}
        <button onclick="saveUser()">${editing?'Save changes':'Add user'}</button>
      </div>
    </div>
    <div class="card">
      <div class="bar"><h2 style="margin:0">Users</h2>
        <input class="search" placeholder="Search name / interest / vibe…" value="${esc(Q)}" oninput="Q=this.value;render()"></div>
      <div class="tabler"><table>
        <thead><tr><th>Name</th><th>Age</th><th>Area</th><th>Interests</th><th>Vibe</th><th>Langs</th><th>km</th><th>Role</th>
          <th title="open">Op</th><th title="verified">Vf</th><th title="dating">Dt</th><th title="paused">Pa</th><th></th></tr></thead>
        <tbody>${rows.map(u=>`<tr>
          <td><b>${esc(u.name)}</b>${(u.intents||[]).length?'<span class="tag" title="has an active intent — reciprocal match" style="background:#e9f9f0;color:#1f9d57">↔</span>':''}</td><td>${u.age}</td>
          <td class="muted">${esc(u.area||'—')}</td>
          <td class="wrap2">${(u.interests||[]).map(i=>`<span class="tag">${esc(i)}</span>`).join('')}</td>
          <td>${esc(u.vibe)}</td><td class="muted">${(u.langs||[]).join(', ')}</td><td>${u.km}</td><td class="muted">${esc(u.role)}</td>
          <td>${flag(u,'open','open to meet')}</td><td>${flag(u,'verified','verified')}</td>
          <td>${flag(u,'datingOk','dating opt-in')}</td><td>${flag(u,'paused','paused',true)}</td>
          <td style="text-align:right"><button class="ghost mini" onclick="openPerson('${String(u.name||'').replace(/'/g,"\\'")}')" title="почему его не находят">Карточка</button>
            <button class="ghost mini" onclick="editRow('${u.id}')">Edit</button>
            <button class="danger mini" onclick="delRow('${u.id}')">Delete</button></td></tr>`).join('')
          ||`<tr><td colspan="13" class="muted" style="padding:22px;text-align:center">No users. Add one above or reset to the demo pool.</td></tr>`}
        </tbody></table></div>
    </div>
    <p class="muted" style="font-size:12px">Changes take effect for the matching agent within a few seconds (shared user store). Test mode.</p>
  </div>`;
}
if(TOK) load().catch(()=>toast('Load failed — is the server up?')); else gate();
</script></body></html>'''


if __name__ == "__main__":
    print("Kleal admin-service on http://127.0.0.1:%d  (store=%s, seed from %s)" % (PORT, STORE, MATCH_URL))
    print("ADMIN TOKEN: %s   (from %s — set KLEAL_ADMIN_TOKEN to override)" % (ADMIN_TOKEN, _TOKEN_FILE))
    ThreadingHTTPServer((config.BIND_HOST, PORT), H).serve_forever()
