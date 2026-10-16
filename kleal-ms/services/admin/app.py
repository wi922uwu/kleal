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
import time
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
import ops
import settings                               # живые настройки: промпты, температура, модель
import llm_client                             # список моделей и живая проба                                     # операционный слой: база, очередь, мост тем
try:
    import db                                  # хранилище людей: то же, что у матчинга
except Exception:
    db = None
from ui import PAGE                            # страница — отдельным файлом, см. её шапку
import battery_tree                            # склад ветвей батареи: копится, не режется

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

# ВРЕМЕННЫЙ ПАРОЛЬ ВМЕСТО ТОКЕНА — до выхода в прод.
#
# Токен длинный, лежит в файле на боксе и каждый раз его надо откуда-то доставать; пока панелью
# пользуются двое своих, это трение без выгоды. Пароль принимается НАРЯДУ с токеном, а не вместо
# него: всё, что ходит с токеном (сама панель из другого места, скрипты), продолжает работать.
#
# ЧЕМ ЭТО ПЛОХО, ЧТОБЫ НЕ ЗАБЫТЬ. Панель открыта из интернета на /admin, и восьмизначный пароль
# держит только случайного прохожего: перебор такого — минуты. Это осознанная временная мера на
# время разработки, и снимать её надо ДО первых живых людей.
#
# Убрать: `KLEAL_ADMIN_PASSWORD=` (пусто) в окружении службы — останется только токен.
ADMIN_PASSWORD = os.environ.get("KLEAL_ADMIN_PASSWORD", "15271987").strip()

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
# Таблица языков общая на всё дерево — см. shared/langs.py. Здесь лежала её дословная копия.
from langs import LANG_CODES as _LANG_CODES
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


def _row_for(users, uid="", name=""):
    """Строка человека для действия модератора: (строка, отказ).

    ПО ID (kleal-ms/docs/IDENTITY.md). По имени — только если такой человек один: тёзки — норма,
    и прежний поиск «первая строка с этим именем» банил, ставил на паузу и верифицировал не того
    из двух «Иванов». Для тёзок — отказ со списком, чтобы модератор выбрал сам."""
    uid = str(uid or "").strip()
    if uid:
        hit = next((u for u in users if str(u.get("id") or "") == uid), None)
        return (hit, None) if hit else (None, {"ok": False, "error": "NOT_FOUND"})
    want = str(name or "").strip().lower()
    if not want:
        return None, {"ok": False, "error": "NAME_REQUIRED"}
    same = [u for u in users if str(u.get("name", "")).strip().lower() == want]
    if len(same) == 1:
        return same[0], None
    if not same:
        return None, {"ok": False, "error": "NOT_FOUND"}
    return None, {"ok": False, "error": "AMBIGUOUS_PERSON",
                  "candidates": [{"id": u.get("id"), "name": u.get("name"), "age": u.get("age"),
                                  "area": u.get("area") or u.get("city"), "owned": bool(u.get("owner"))}
                                 for u in same[:10]]}


def apply_verb(name, verb, uid=""):
    """The three narrow verbs that replaced the edit form.

    They patch ONE key on the raw row and deliberately do NOT go through `_norm_user`, which
    rewrites a person on every save: it substitutes `coffee` for empty interests, `en` for missing
    languages, km 2.0, vibe "chill", and invents an entity called "<Interest> scene". Saving a row
    just to pause someone used to fabricate the very data the person card exists to report as
    missing — the panel would show a clean profile it had authored itself.
    """
    if verb not in VERBS:
        return {"ok": False, "error": "unknown verb"}
    with _LOCK:
        users = _read()
        hit, no = _row_for(users, uid, name)
        if no:
            return no
        for i, u in enumerate(users):
            if u is not hit:
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
            return {"ok": True, "name": row.get("name"), "id": row.get("id"), "verb": verb,
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
                    # По id: удаление по имени стирало бы заодно всех тёзок (docs/IDENTITY.md).
                    db.delete_user(uid=gone.get("id"))
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


def _onb_post(path, payload, timeout=30):
    """Позвать онбординг. Через него идут ВСЕ действия с учётками: он единственный, кто пишет
    accounts.json, и делает это под своим замком. Если бы панель писала файл сама, обычный трафик
    (онбординг обновляет отметку «последний вход») мог бы перезаписать её правку целиком — и
    отозванная сессия молча вернулась бы."""
    req = urllib.request.Request(config.ONBOARDING_URL + path,
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json",
                                          "X-Admin-Token": ADMIN_TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, str(e)[:160])}


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
        rows = _read()
        # Сперва точный id: по имени нашёлся бы первый из тёзок (kleal-ms/docs/IDENTITY.md).
        by_id = [u for u in rows if str(u.get("id", "")).lower() == who]
        for u in by_id or [u for u in rows if str(u.get("name", "")).strip().lower() == who]:
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



# ──────────────────────────────────────────────────────────────────────────────── пульт
# Раньше ни промпта, ни температуры, ни модели в панели не было вовсе: промпт правился на боксе
# и перезапуском сервиса, температура была россыпью чисел в коде, модель — переменной окружения.
# Здесь они собраны в одно место, и это главное, ради чего панель переделывалась.

# ──────────────────────────────────────────────────────────────────── жалобы и учётки
# ПОЧЕМУ РЕШЕНИЕ МОДЕРАТОРА ЛЕЖИТ ОТДЕЛЬНО, А НЕ В САМОЙ ЖАЛОБЕ. Список жалоб живёт в памяти
# матчинга и пишется оттуда целым ключом. Допиши панель статус прямо в строку — и следующая
# жалоба, поданная кем угодно, стёрла бы все пометки разом, потому что матчинг записал бы ключ
# своей копией из памяти. Поэтому у панели свой ключ, которого матчинг не касается вовсе.
REPORT_ACTIONS_KEY = "_reports_actions"


def _report_actions():
    try:
        return db.kv_get(REPORT_ACTIONS_KEY) or {}
    except Exception:
        return {}


def _report_action_save(rid, patch):
    cur = _report_actions()
    if not isinstance(cur, dict):
        cur = {}
    row = dict(cur.get(rid) or {})
    row.update(patch)
    row["at"] = time.time()
    cur[rid] = row
    db.kv_set(REPORT_ACTIONS_KEY, cur)
    return row


def _reports_view(qs):
    """Очередь жалоб + то, что модератор с ними уже сделал."""
    rep = _match_get("/api/agent/admin/reports" + (qs or ""), timeout=25)
    acts = _report_actions()
    for r in (rep.get("reports") or []):
        r["action"] = acts.get(r.get("id")) or None
    rep["handled"] = sum(1 for r in (rep.get("reports") or []) if r.get("action"))
    return rep


def _ban(name, on=True, uid=""):
    """Запрет на продукт — двумя полями строки человека, потому что гейтов в движке два.

    `accountStatus` закрывает выдачу поиска, но НЕ закрывает групповые пути: приглашение в группу
    и согласие там проверяются другим гейтом, который про этот статус не знает. Он знает поле
    `blocksMe`. Поэтому ставятся оба — иначе «забаненный» продолжал бы попадать в группы, и это
    выглядело бы как дыра в модерации, а было бы просто разными воротами.

    Пауза — не то же самое: она добровольная, человек ставит её себе сам и снимает когда хочет.
    """
    with _LOCK:
        users = _read()
        hit, no = _row_for(users, uid, name)
        if no:
            return no
        idx = users.index(hit)
        if on:
            hit["accountStatus"] = "banned"
            hit["blocksMe"] = True
            hit["banned_at"] = time.time()
        else:
            hit.pop("accountStatus", None)
            hit.pop("banned_at", None)
            hit["blocksMe"] = False
        users[idx] = hit
        # Той же записью, что и глаголы: одна строка, без нормализации — она дописывала людям
        # интересы и языки, которых те не называли.
        _write(users, touched=hit)
    # Открытое закрывает сам матчинг: приглашения и встречи живут в его памяти.
    swept = _match_post("/api/agent/admin/ban-sweep", {"id": hit.get("id"), "name": hit.get("name")}) \
        if on else {"ok": True}
    return {"ok": True, "banned": bool(on), "name": hit.get("name"), "id": hit.get("id"),
            "swept": swept.get("closed")}


def _settings_view():
    """Что настроено + что умеет код + история правок."""
    cat = settings.catalog()
    cur = settings.all()
    prompts = []
    for name in sorted(cat.keys()):
        row = cat.get(name) or {}
        over = ((cur.get("prompts") or {}).get(name))
        prompts.append({
            "name": name,
            "service": row.get("service") or name.split(".")[0],
            "chars": row.get("chars") or 0,
            "overridden": isinstance(over, str) and len(over.strip()) >= 20,
            "default": row.get("default") or "",
            "value": over if isinstance(over, str) else "",
        })
    try:
        updated = db.kv_updated(settings.KEY)
    except Exception:
        updated = 0
    return {"ok": True, "prompts": prompts, "model": cur.get("model") or {},
            "history": list(reversed((cur.get("_history") or [])[-30:])), "updated": updated,
            "catalog_empty": not cat,
            # Температуры, которые стоят в коде: без них ползунок «на всё» выглядит как
            # единственная правда, а лестница разговора 0.35→0.2→0.1 существует не случайно.
            "code_temps": [
                {"tag": "buddy.chat", "value": 0.35, "note": "разговор с Буди; на повторах 0.2 и 0.1"},
                {"tag": "buddy.intent_build", "value": 0.35, "note": "сборка интента из разговора"},
                {"tag": "onboarding.funnel", "value": 0.45, "note": "вопросы онбординга"},
                {"tag": "matching.intro", "value": 0.6, "note": "знакомство агентов"},
            ]}


def _model_view():
    """Модель: что выбрано, что доступно, и чем это подтверждается."""
    cur = (settings.all().get("model") or {})
    try:
        models = llm_client.llm_models()
    except Exception:
        models = []
    return {"ok": True, "models": models, "current": cur,
            "code_default": os.environ.get("V2_MODEL", "llama_self")}


def _model_probe(body):
    """Спросить модель и засечь время. Ничего не пишет."""
    t0 = time.time()
    try:
        txt = llm_client.llm_complete(
            (body.get("model") or settings.model_id(os.environ.get("V2_MODEL", "llama_self"))),
            [{"role": "system", "content": "Answer with one short sentence."},
             {"role": "user", "content": body.get("text") or "Скажи одно короткое предложение по-русски."}],
            float(body.get("temperature") or 0.3))
        return {"ok": True, "ms": int((time.time() - t0) * 1000), "text": str(txt)[:400]}
    except Exception as e:
        return {"ok": False, "ms": int((time.time() - t0) * 1000),
                "error": "%s: %s" % (type(e).__name__, str(e)[:200])}


# `_accounts_view` убрана: панель больше не читает accounts.json сама. Файл принадлежит
# онбордингу — он один его пишет под своим замком, — и два читателя разного возраста
# рано или поздно расходятся в том, сколько у человека живых входов.

def _path(handler):
    return handler.path.split("?", 1)[0]


# ─────────────────────────────────────────────────────────────────── батарея сценариев
#
# Батарея гоняется службой `kleal-battery` и пишет три файла: кольцо событий (каждая реплика
# человека, каждый ответ Kleal, каждая собранная затея и каждая беда), таблицу кругов и пул
# сценариев. Админка их только ЧИТАЕТ — управлять прогоном отсюда нельзя намеренно: кнопка
# «перезапустить» в панели означала бы, что измерение зависит от того, кто на него смотрит.
BATTERY_LIVE = "/root/kleal-archive/battery-live.jsonl"
BATTERY_HIST = "/root/kleal-archive/battery-history.tsv"
BATTERY_POOL = "/root/kleal-archive/scenarios.jsonl"
BATTERY_ROUNDS = "/root/kleal-archive/battery-rounds.jsonl"


# Склад ветвей: один на процесс, складка в фоне. Заводится при импорте, чтобы ручка отвечала и в
# тестах, где `__main__` не запускается; поток стартует только из `__main__`.
TREE = battery_tree.Store()


def battery_state(since=0.0, limit=1500):
    """События после `since`, последние круги и размер пула. Всё дешёвое: хвосты файлов."""
    events = []
    try:
        with open(BATTERY_LIVE, encoding="utf-8") as f:
            # Хвост, а не весь файл: кольцо подрезает сама батарея, но между подрезками оно растёт,
            # и панель не должна за это платить.
            for line in f.readlines()[-7200:]:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if float(row.get("t") or 0) > since:
                    events.append(row)
    except FileNotFoundError:
        pass
    hist = []
    try:
        rows = [l.rstrip("\n").split("\t") for l in open(BATTERY_HIST, encoding="utf-8")]
        hist = [r for r in rows[1:] if len(r) >= 11][-12:]
    except FileNotFoundError:
        pass
    pool = 0
    try:
        with open(BATTERY_POOL, encoding="utf-8") as f:
            pool = sum(1 for _ in f)
    except FileNotFoundError:
        pass
    # «Жива» — по свежести событий, а не по systemctl: панели довольно следа работы, спрашивать
    # систему ей незачем. Две минуты с запасом: круг из шестидесяти идёт около минуты.
    fresh = False
    try:
        fresh = (time.time() - os.path.getmtime(BATTERY_LIVE)) < 120
    except OSError:
        pass
    # Подробности кругов — то, из чего панель строит диаграммы: виды бед, языки, сложность.
    rounds = []
    try:
        for line in open(BATTERY_ROUNDS, encoding="utf-8").readlines()[-80:]:
            try:
                rounds.append(json.loads(line))
            except Exception:
                continue
    except FileNotFoundError:
        pass
    # СКОЛЬКО ПРОГОНОВ ПРОШЛО ВСЕГО — для сердца круга. В `rounds` едут последние восемьдесят
    # (из них рисуются графики), а прошло их может быть и тысяча: строка на прогон, файл крошечный.
    total = 0
    try:
        with open(BATTERY_ROUNDS, "rb") as f:
            total = sum(1 for _ in f)
    except FileNotFoundError:
        pass
    return {"events": events[-limit:], "history": hist, "pool": pool, "rounds": rounds,
            "rounds_total": total, "talks": getattr(TREE, "count", 0),
            "alive": fresh, "now": time.time()}


class H(BaseHTTPRequestHandler):
    def _authed(self):
        """The page itself is served without the token — it has to be, so a browser can ask for one.
        Every API call needs it. Constant-time compare, so the check is not a guessing oracle.

        Пароль проверяется ТАК ЖЕ, как токен, и обе проверки идут ВСЕГДА — без раннего выхода:
        иначе время ответа само рассказывает, что именно совпало."""
        got = str(self.headers.get("X-Admin-Token") or "")
        ok_token = hmac.compare_digest(got, ADMIN_TOKEN)
        ok_pass = bool(ADMIN_PASSWORD) and hmac.compare_digest(got, ADMIN_PASSWORD)
        if not (ok_token or ok_pass):
            send_json(self, 401, {"ok": False, "error": "unauthorized"})
            return False
        return True

    def do_GET(self):
        p = _path(self)
        if p == "/admin" or p == "/admin/" or p == "/":
            # Одна страница, один адрес. Токен для неё не нужен — браузеру надо на чём-то его
            # спросить; всё, что за ней, без токена не отвечает.
            return send(self, 200, PAGE, "text/html")
            return send(self, 200, PAGE, "text/html")
        if not self._authed():
            return
        if p == "/api/admin/ping":
            # Отвечает не только «жив», но и чем сейчас живёт система: шапка панели показывает
            # режим хранилища и очереди, чтобы «почему цифры не сходятся» не начиналось с догадок.
            st = ops.storage()
            q = ops.queue()
            send_json(self, 200, {"ok": True, "storage": st.get("mode"), "queue": q.get("mode")})
        elif p == "/api/admin/card":
            # ВТОРАЯ МОДЕЛЬ: обучение и живая работа. Ручка сводит три источника — сводку обучения
            # (её пишет обучающий прогон), опрос самой модели и журнал её ответов, который ведёт
            # сборщик. Ничего не считает: панель должна показывать то, что есть, а не своё мнение.
            import json as _j, urllib.request as _u
            _sum = {}
            try:
                _sum = _j.load(open("/root/kleal-archive/ft-summary.json", encoding="utf-8"))
            except Exception as _e:
                _sum = {"__нет": str(_e)[:80]}
            _alive, _why = False, ""
            try:
                _alive = bool(_j.loads(_u.urlopen("http://127.0.0.1:17073/", timeout=4)
                                       .read().decode()).get("ok"))
            except Exception as _e:
                _why = str(_e)[:80]
            _calls = []
            try:
                with open("/root/kleal-archive/card-model.jsonl", encoding="utf-8") as _f:
                    _lines = _f.readlines()[-60:]
                for _l in reversed(_lines):
                    try:
                        _calls.append(_j.loads(_l))
                    except Exception:
                        pass
            except Exception:
                pass
            _ms = sorted(int(c.get("ms") or 0) for c in _calls if c.get("ms"))
            send_json(self, 200, {"alive": _alive, "why": _why, "summary": _sum,
                                  "calls": _calls,
                                  "median_ms": (_ms[len(_ms) // 2] if _ms else None),
                                  "total": len(_calls)})
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
        elif p == "/api/admin/battery":
            # Довод `since` — отметка времени последнего показанного события: панель просит только
            # новое, а не перечитывает кольцо целиком каждые полторы секунды.
            _q = dict(kv.split("=", 1) for kv in self.path.split("?", 1)[-1].split("&") if "=" in kv) \
                if "?" in self.path else {}
            try:
                _since = float(_q.get("since") or 0)
            except (TypeError, ValueError):
                _since = 0.0
            send_json(self, 200, battery_state(_since))
        elif p == "/api/admin/battery/tree":
            # ДАННЫЕ КОПЯТСЯ, А НЕ ПЕРЕЗАПИСЫВАЮТСЯ (владелец, 17.09.2026). Кольцо событий батарея
            # подрезает сама, и прошлые круги в панели исчезали. Склад `battery_tree` дописывает
            # каждую законченную ветвь и не режет; панель рисует из него кольца прошлых кругов.
            _q = dict(kv.split("=", 1) for kv in self.path.split("?", 1)[-1].split("&") if "=" in kv) \
                if "?" in self.path else {}
            try:
                _since = float(_q.get("since") or 0)
                _limit = max(1, min(20000, int(_q.get("limit") or 6000)))
            except (TypeError, ValueError):
                _since, _limit = 0.0, 6000
            _scen = str(_q.get("scen") or "").strip()
            if _scen:
                # РАЗГОВОР ОДНОЙ ВЕТКИ, С РЕПЛИКАМИ. В кольца слова не едут (там нужна форма), но
                # когда человек щёлкнул по ветке, он хочет прочитать сам диалог. Кольцо событий для
                # этого коротко: у ветки из прошлого круга в панели оставалась одна строка вместо
                # разговора (снято владельцем 17.09.2026).
                try:
                    _t0 = float(_q.get("t0")) if _q.get("t0") else None
                except (TypeError, ValueError):
                    _t0 = None
                return send_json(self, 200, {"branch": TREE.find(_scen, _t0), "now": time.time()})
            if _q.get("rounds"):
                # ХОЛОДНЫЙ СТАРТ: панель просит столько ПРОГОНОВ, сколько рисует дугами. Считать
                # их строками нельзя — прогон бывает и в 60 сценариев, и в 480, и после обновления
                # страницы часть дуг просто не приезжала: картинка выглядела сброшенной.
                try:
                    _n = max(1, min(60, int(_q.get("rounds"))))
                except (TypeError, ValueError):
                    _n = 16
                return send_json(self, 200, {"branches": TREE.rounds_tail(_n), "now": time.time()})
            send_json(self, 200, {"branches": TREE.tail(_since, _limit), "now": time.time()})
        elif p == "/api/admin/person":
            from urllib.parse import unquote
            q = dict(kv.split("=", 1) for kv in self.path.split("?", 1)[-1].split("&") if "=" in kv) \
                if "?" in self.path else {}
            nm = unquote(q.get("name", "").replace("+", " "))
            uid = unquote(q.get("id", "").replace("+", " "))
            # Человек — по id; имя — только однозначное. Для тёзок и матчинг, и мы отвечаем
            # AMBIGUOUS_PERSON со списком, и страница даёт выбрать (kleal-ms/docs/IDENTITY.md).
            hit, no = _row_for(_read(), uid, nm)
            if no and no.get("error") == "AMBIGUOUS_PERSON":
                return send_json(self, 200, no)
            rep = _match_get("/api/agent/admin/person?name=" + quote(nm)
                             + ("&id=" + quote(str(hit.get("id") or "")) if hit else ""))
            if hit:
                rep["id"] = hit.get("id")      # цель для глаголов, бана и удаления
            send_json(self, 200, rep)
        elif p == "/api/admin/cohorts":
            send_json(self, 200, _match_get("/api/agent/admin/cohorts", timeout=40))
        elif p == "/api/admin/proposals":
            send_json(self, 200, _match_get("/api/agent/admin/proposals"))
        elif p == "/api/admin/settings":
            # Весь пульт одним ответом: что настроено, что умеет код и когда это трогали.
            # Одним, а не тремя: страница рисует раздел целиком, и три запроса дали бы три
            # разных момента времени — «сохранил, а не изменилось» ровно отсюда и берётся.
            send_json(self, 200, _settings_view())
        elif p == "/api/admin/model":
            send_json(self, 200, _model_view())
        elif p == "/api/admin/accounts":
            # Учётки спрашиваем у онбординга: файл принадлежит ему, и только он видит его целиком.
            send_json(self, 200, _onb_post("/api/auth/admin/accounts", {"q": _qs(self, "q", "")}))
        elif p == "/api/admin/reports":
            send_json(self, 200, _reports_view("?" + (self.path.split("?", 1)[1] if "?" in self.path else "")))
        elif p.startswith("/api/admin/evidence/"):
            # Файл к жалобе на группу. Матчинг хранит его в закрытой папке и отдаёт только по
            # внутреннему адресу; сюда — по токену панели (проверен выше, в _authed).
            eid = p.rsplit("/", 1)[-1]
            if not re.match(r"^[0-9a-f]{32}$", eid):
                return send_json(self, 404, {})
            try:
                req = urllib.request.Request(MATCH_URL.rstrip("/") + "/api/agent/admin/evidence/" + eid,
                                             headers={"X-Admin-Token": ADMIN_TOKEN})
                with urllib.request.urlopen(req, timeout=60) as r:
                    data, ctype = r.read(), r.headers.get("Content-Type") or "application/octet-stream"
            except Exception:
                return send_json(self, 404, {"ok": False, "error": "NO_SUCH_FILE"})
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", "attachment")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)
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
        elif p == "/api/admin/settings":
            # Пишем ПОПРАВКУ, а не весь слепок: две вкладки, открытые рядом, иначе затирали бы
            # правки друг друга целиком. None у поля означает «вернуть как в коде».
            try:
                send_json(self, 200, {"ok": True, "settings": settings.save(body or {})})
            except Exception as e:
                send_json(self, 400, {"ok": False, "error": "%s: %s" % (type(e).__name__, e)})
        elif p == "/api/admin/ban":
            send_json(self, 200, _ban((body or {}).get("name"), bool((body or {}).get("on", True)),
                                      (body or {}).get("id") or ""))
        elif p == "/api/admin/notify":
            # Ответ модератора человеку. Пишет его матчинг: переписки живут в его памяти.
            send_json(self, 200, _match_post("/api/agent/admin/notify",
                                             {"to": (body or {}).get("to"),
                                              "to_id": (body or {}).get("to_id") or "",
                                              "text": (body or {}).get("text"),
                                              "ref": (body or {}).get("ref") or ""}))
        elif p == "/api/admin/report/action":
            # Решение по жалобе + необязательный ответ тому, кто пожаловался.
            b = body or {}
            rid = str(b.get("id") or "")
            if not rid:
                return send_json(self, 400, {"ok": False, "error": "ID_REQUIRED"})
            sent = None
            if b.get("answer") and b.get("to"):
                sent = _match_post("/api/agent/admin/notify",
                                   {"to": b.get("to"), "to_id": b.get("to_id") or "",
                                    "text": b.get("answer"), "ref": rid})
            row = _report_action_save(rid, {"status": str(b.get("status") or "handled"),
                                            "note": str(b.get("note") or "")[:600],
                                            "answered": bool(sent and sent.get("ok"))})
            send_json(self, 200, {"ok": True, "action": row, "sent": sent})
        elif p == "/api/admin/account/resolve":
            send_json(self, 200, _onb_post("/api/auth/admin/resolve", {"account": (body or {}).get("account")}))
        elif p == "/api/admin/account/revoke":
            send_json(self, 200, _onb_post("/api/auth/admin/revoke",
                                           {"account": (body or {}).get("account"),
                                            "session": (body or {}).get("session")}))
        elif p == "/api/admin/account/delete":
            # Удаление учётки — три шага, и порядок важен. Сперва спрашиваем, КОГО удаляем:
            # без однозначной связи «учётка → строка» удалять нельзя, тёзки неразличимы.
            b = body or {}
            who = _onb_post("/api/auth/admin/resolve", {"account": b.get("account")})
            if not who.get("ok"):
                return send_json(self, 400, who)
            revoked = _onb_post("/api/auth/admin/revoke", {"account": b.get("account")})
            # Стираем по id строки, которую онбординг связал с учёткой: по имени стёрлись бы записи тёзки.
            purged = _match_post("/api/agent/admin/purge", {"id": who.get("id") or "", "name": who.get("name")}) \
                if (who.get("id") or who.get("name")) else {"ok": True, "purged": {}}
            gone = _onb_post("/api/auth/admin/delete", {"account": b.get("account")})
            send_json(self, 200, {"ok": bool(gone.get("ok")), "resolved": who,
                                  "revoked": revoked, "purged": purged, "deleted": gone})
        elif p == "/api/admin/model/probe":
            # Живая проба: спросить у модели одно короткое предложение и засечь время. Это
            # единственный честный ответ на «модель вообще отвечает» — /health у сервиса
            # возвращает константу и врёт, когда канал к поду лежит.
            send_json(self, 200, _model_probe(body or {}))
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
            send_json(self, 200, apply_verb(body.get("name"), str(body.get("verb") or ""), body.get("id") or ""))
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


# ВТОРАЯ ПАНЕЛЬ УДАЛЕНА ОТСЮДА. Здесь лежали 873 строки разметки — целая ещё одна админка,
# отдававшаяся по адресу `/admin?legacy=1`. Её держали как «откат длиной в один параметр», но
# цена оказалась другой: ВСЁ управление людьми — пауза, верификация, правка, удаление — жило
# только на ней, о её существовании надо было знать, а основная панель умела лишь смотреть.
# Две панели с разными возможностями — это не запасной вариант, а одна, разрезанная пополам.
# Управление переехало в ui.py, к спискам и карточкам, там, где людей и находят.


if __name__ == "__main__":
    print("Kleal admin-service on http://127.0.0.1:%d  (store=%s, seed from %s)" % (PORT, STORE, MATCH_URL))
    battery_tree.start_folding(TREE)
    print("ADMIN TOKEN: %s   (from %s — set KLEAL_ADMIN_TOKEN to override)" % (ADMIN_TOKEN, _TOKEN_FILE))
    if ADMIN_PASSWORD:
        # Сам пароль в журнал не пишем: журнал читают и пересылают. Пишем только то, что он включён.
        print("ADMIN PASSWORD: включён (временно, до прода; убрать — KLEAL_ADMIN_PASSWORD=)")
    import serving  # очередь подключений на 128, а не на 5 — см. shared/serving.py
    serving.KlealServer((config.BIND_HOST, PORT), H).serve_forever()
