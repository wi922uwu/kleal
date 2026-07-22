# -*- coding: utf-8 -*-
"""Генерик-воркер для 3-колоночного стенда матчинга (PROD | OLD | NEW).

Запускается ОРКЕСТРАТОРОМ (`kleal_sim.py`) по одному экземпляру на версию. Импортирует РОВНО ОДНУ
версию `app.py` из своего version-каталога, поэтому его приватный `sys.modules['core_v2']` — это
движок именно этой версии. Изоляция гарантируется границей процесса (у PROD core_v2=99a0b38b, у
OLD/NEW=35f8e984 — сосуществуют по памяти ОС, а не по совпадению). Слушает ТОЛЬКО 127.0.0.1 на
эфемерном порту, недостижим ни через какой туннель, не трогает 8 боевых сервисов.

Управление — через env:
  SIM_VER=prod|old|new   SIM_VER_DIR=<abs versions/<v>>   SIM_WORKER_PORT=<port>   SIM_NOW=<float>
  KLEAL_USERS=<pool.json> KLEAL_STORE=<store_<v>.json> KLEAL_CORE_CONFIG=<vdir/config/*.yaml>
  KLEAL_CORE_V2=1 LLM_URL=http://127.0.0.1:1 PYTHONHASHSEED=0 V2_MODEL=sim
"""
import os, sys, json, time, hashlib, threading, traceback

VER = os.environ.get("SIM_VER", "?")
VDIR = os.environ.get("SIM_VER_DIR", "")
PORT = int(os.environ.get("SIM_WORKER_PORT", "0"))
NOW = float(os.environ.get("SIM_NOW", "1752600000.0"))
BCN = (41.3874, 2.1686)

# --- заморозить стенные часы ДО импорта движка (belt-and-suspenders детерминизм для чёрного ящика PROD).
#     Процесс изолирован, так что это ни на что снаружи не влияет. time.sleep/monotonic не трогаем.
_real_time = time.time
try:
    time.time = lambda: NOW
except Exception:
    pass

# --- сделать так, чтобы голые импорты (`import app`, `import core_v2`, `import kleal_lib`) находили
#     файлы ИМЕННО этой версии. MDIR попадает в sys.path[0] -> app + core_v2 резолвятся отсюда;
#     app.py:8 сам добавит VDIR/shared для kleal_*.
MDIR = os.path.join(VDIR, "services", "matching")
SDIR = os.path.join(VDIR, "shared")
for _p in (SDIR, MDIR):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
os.environ.setdefault("KLEAL_CORE_CONFIG", os.path.join(VDIR, "config", "Kleal_Matching_Core_Config_v2.yaml"))

APP = None
APP_OK = False
IMPORT_ERR = None
_BOOT_T0 = _real_time()
try:
    import app as APP                              # НЕ __main__ => серверный guard внутри app.py не сработает
    APP_OK = True
except Exception:
    IMPORT_ERR = traceback.format_exc()[-1800:]    # НЕ выходим — держим /health, чтобы оркестратор узнал ПОЧЕМУ


def _sha_file(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return None


def _has_mod_attr(name, attr):
    try:
        m = __import__(name)
        return hasattr(m, attr)
    except Exception:
        return False


# --------------------------------------------------------- runtime-провенанс + возможности (считаем раз)
APP_SHA = CORE_SHA = CONFIG_SHA = CONFIG_VER = None
CORE_V2_ON = None
CAPS = {"can_match": False, "can_explain": False, "can_capsule": False, "can_group": False}
POOL_SHA = None
POOL_COUNT = 0
FROM_STORE = False
DETERMINISTIC = None
SELFTEST_OK = False
SELFTEST_DIGEST = None
UMAP = {}


def _load_umap():
    global UMAP
    try:
        with open(os.environ.get("KLEAL_USERS", ""), "r", encoding="utf-8") as f:
            lst = json.load(f)
        UMAP = {u.get("name"): u for u in lst if isinstance(u, dict)}
    except Exception:
        UMAP = {}


if APP_OK:
    try:
        APP_SHA = _sha_file(getattr(APP, "__file__", ""))
        _core = getattr(APP, "_core", None)
        CORE_SHA = _sha_file(getattr(_core, "__file__", "")) if _core is not None else None
        _cfg = getattr(APP, "_CORE_CFG", None) or {}
        CONFIG_SHA = (_cfg.get("_sha256") or "") or (_sha_file(os.environ.get("KLEAL_CORE_CONFIG", "")) or "")
        CONFIG_VER = _cfg.get("config_version")
        CORE_V2_ON = bool(getattr(APP, "CORE_V2", False))
        CAPS["can_match"] = hasattr(APP, "match_candidates")
        CAPS["can_explain"] = hasattr(APP, "evaluate_policy")
        CAPS["can_capsule"] = _has_mod_attr("kleal_contracts", "build_dating_capsule")
        CAPS["can_group"] = _has_mod_attr("kleal_groups", "form_group")
    except Exception:
        IMPORT_ERR = (IMPORT_ERR or "") + "\n[provenance] " + traceback.format_exc()[-600:]
    try:
        cands = APP.load_candidates()
        FROM_STORE = (APP._users_cache.get("list") is not None)
        POOL_COUNT = len(cands) if isinstance(cands, list) else 0
        # Fingerprint the candidate set the engine ACTUALLY ranked (not the source file): if a version
        # silently falls back to its built-in ~50-user demo pool, its POOL_SHA diverges -> the orchestrator's
        # DATA-MISMATCH guard fires. Hashing KLEAL_USERS would be byte-identical for all three regardless.
        _names = sorted(str(c.get("name")) for c in (cands or []) if isinstance(c, dict))
        POOL_SHA = hashlib.sha256(json.dumps(_names, ensure_ascii=False).encode("utf-8")).hexdigest()
        _load_umap()
    except Exception:
        IMPORT_ERR = (IMPORT_ERR or "") + "\n[pool] " + traceback.format_exc()[-600:]

# --------------------------------------------------------- канонический интент для selftest (детерм.)
CANNED_INTENT = {"type": "social", "topics": ["coffee"], "role": "meet", "mode": "offline",
                 "time": "Flexible", "radiusKm": 15.0, "requiredLanguages": [],
                 "verifiedOnly": False, "exactMatchRequired": False,
                 "adjacentAllowed": True, "broadAllowed": True}
CANNED_PROF = {"name": "ME", "vibe": "chill", "interests": ["coffee"], "langs": ["en"],
               "geo": {"coarseLat": BCN[0], "coarseLon": BCN[1]}, "coarseLat": BCN[0], "coarseLon": BCN[1]}
CANNED_CTX = {"now": NOW, "self": "ME", "uid": "ME"}

_ENGINE_LOCK = threading.Lock()                    # движок одной версии — строго однопоточно (детерм. + без гонок глобалов)


def _digest(slate):
    key = [[c.get("name"), round(float(c.get("score") or 0), 4)] for c in (slate or []) if isinstance(c, dict)]
    return hashlib.sha256(json.dumps(key, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]


def _run_match(intent, prof, ctx):
    with _ENGINE_LOCK:
        return APP.match_candidates(dict(intent), dict(prof), dict(ctx)) or []


if APP_OK and CAPS["can_match"]:
    try:
        _r1 = _run_match(CANNED_INTENT, CANNED_PROF, CANNED_CTX)
        _r2 = _run_match(CANNED_INTENT, CANNED_PROF, CANNED_CTX)
        _n1 = [c.get("name") for c in _r1]
        _n2 = [c.get("name") for c in _r2]
        DETERMINISTIC = (_digest(_r1) == _digest(_r2)) and (_n1 == _n2)
        SELFTEST_OK = bool(_r1) and bool(DETERMINISTIC)
        SELFTEST_DIGEST = _digest(_r1)
    except Exception:
        SELFTEST_OK = False
        DETERMINISTIC = False
        IMPORT_ERR = (IMPORT_ERR or "") + "\n[selftest] " + traceback.format_exc()[-600:]

BOOT_MS = int((_real_time() - _BOOT_T0) * 1000)


def _project(c):
    """Витрина+сравнение: белый список полей + список имён ключей (для field-set диффа), без тяжёлых тел."""
    if not isinstance(c, dict):
        return {"name": str(c)}
    pol = c.get("policy")
    return {"name": c.get("name"), "km": c.get("km"), "interests": c.get("interests"),
            "vibe": c.get("vibe"), "age": c.get("age"), "verified": c.get("verified"),
            "score": c.get("score"), "tier": c.get("tier"), "kind": c.get("kind"),
            "band": c.get("band_en") or c.get("band"),
            "decision_class": c.get("decision_class"),
            "readiness": c.get("readiness_en") or c.get("readiness"),
            "policy": (pol.get("decision") if isinstance(pol, dict) else pol),
            "reasons": (c.get("reasons_en") or c.get("reasons") or [])[:3],
            "has_profile_view": "profile_view" in c,
            "has_trace": ("decision_trace" in c or "trace" in c),
            "has_completion": "completion_factors" in c,
            "_keys": sorted(k for k in c.keys() if not str(k).startswith("_"))}


def _health():
    healthy = bool(APP_OK and CAPS["can_match"] and SELFTEST_OK and FROM_STORE and POOL_COUNT > 0)
    return {"ver": VER, "ok": APP_OK, "import_error": IMPORT_ERR,
            "app_sha": (APP_SHA or "")[:12], "core_sha": (CORE_SHA or "")[:12],
            "config_sha": (CONFIG_SHA or "")[:12], "config_version": CONFIG_VER,
            "core_v2_enabled": CORE_V2_ON, "pool_sha": (POOL_SHA or "")[:16],
            "pool_count": POOL_COUNT, "from_store": FROM_STORE, "caps": CAPS,
            "deterministic": DETERMINISTIC, "selftest_ok": SELFTEST_OK,
            "selftest_digest": SELFTEST_DIGEST, "boot_ms": BOOT_MS, "port": PORT, "healthy": healthy}


def _match(body):
    if not (APP_OK and CAPS["can_match"]):
        return {"ver": VER, "slate": [], "count": 0, "error": "engine unavailable (import failed)"}
    intent = body.get("intent") or {}
    prof = body.get("prof") or CANNED_PROF
    ctx = body.get("ctx") or CANNED_CTX
    t0 = _real_time()
    try:
        slate = _run_match(intent, prof, ctx)
    except Exception as e:
        return {"ver": VER, "slate": [], "count": 0, "error": str(e)[:300]}
    return {"ver": VER, "count": len(slate), "ms": int((_real_time() - t0) * 1000),
            "slate": [_project(c) for c in slate]}


def _diag(body):
    """NEW-only помощники, недостижимые через границу процесса: policy/capsule/group. PROD/OLD -> supported:false."""
    op = body.get("op")
    if op == "policy":
        if not CAPS["can_explain"]:
            return {"supported": False}
        intent = body.get("intent") or {}
        try:
            gctx = APP._gate_ctx_and_self({})[0]
        except Exception:
            gctx = {"feedback": {}, "blocked": set()}
        items = []
        for nm in (body.get("names") or [])[:24]:
            c = UMAP.get(nm) or {"name": nm}
            try:
                v = APP.evaluate_policy(intent, c, gctx) or {}
                dec = v.get("decision")
                rsn = v.get("reason") or v.get("gate_reason")
                if not rsn:
                    # ALLOW == policy passed: the candidate was dropped by §7 retrieval / diversify / top-N cap,
                    # NOT by a policy gate — do not mislabel it 'gated'.
                    blocked = str(dec).upper() not in ("ALLOW", "PASS", "OK", "NONE", "")
                    rsn = "gated" if blocked else "не гейт политики — убран ретривом/ранжированием/лимитом"
                items.append({"name": nm, "decision": dec, "reason": rsn})
            except Exception as e:
                items.append({"name": nm, "decision": "?", "reason": str(e)[:120]})
        return {"supported": True, "items": items}
    if op == "capsule":
        if not CAPS["can_capsule"]:
            return {"supported": False}
        nm = body.get("name")
        u = UMAP.get(nm) or {}
        try:
            import kleal_contracts as kc
            cap = kc.build_dating_capsule(u)
            raw = {k: u.get(k) for k in ("age", "interests", "langs", "datingOk", "vibe")}
            return {"supported": True, "name": nm, "capsule": cap, "raw": raw}
        except Exception as e:
            return {"supported": True, "error": str(e)[:200]}
    if op == "group":
        if not CAPS["can_group"]:
            return {"supported": False}
        intent = body.get("intent") or {}
        prof = body.get("prof") or CANNED_PROF
        ctx = body.get("ctx") or CANNED_CTX
        try:
            gs = max(2, int(body.get("size_min") or 3))
        except Exception:
            gs = 3
        try:
            import kleal_groups as kg
            slate = _run_match(intent, prof, ctx)
            top = [c for c in slate if isinstance(c, dict)][:min(8, max(4, gs + 2))]
            members = [kg.member_from_card(c) for c in top]
            params = kg.load_group_params(getattr(APP, "_CORE_CFG", None))
            g = kg.form_group(intent, members, {"size_min": gs, "size_max": gs + 1}, params, enabled_override=True) or {}
            return {"supported": True, "formed": bool(g.get("group")),
                    "members": g.get("members"), "utility": g.get("utility"),
                    "note": "СТАРАЯ версия групп не умеет (отдаёт людей списком); НОВАЯ формирует набор как множество (§15)."}
        except Exception as e:
            return {"supported": True, "error": str(e)[:200]}
    return {"supported": False, "error": "unknown op"}


# --------------------------------------------------------- HTTP (127.0.0.1 only)
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socketserver


class _H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _read_body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}
        except Exception:
            return {}

    def do_GET(self):
        if self.path.split("?")[0] == "/health":
            self._send(200, _health())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        p = self.path.split("?")[0]
        body = self._read_body()
        if p == "/match":
            self._send(200, _match(body if isinstance(body, dict) else {}))
        elif p == "/diag":
            self._send(200, _diag(body if isinstance(body, dict) else {}))
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *a):
        pass


class _Server(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def _parent_dead():
    """Кросс-платформенно: жив ли оркестратор? POSIX — переусыновление в init (getppid==1);
    Windows — опрос записанного SIM_PARENT_PID (getppid там не станет 1)."""
    try:
        if os.name == "posix":
            return os.getppid() == 1
        pp = int(os.environ.get("SIM_PARENT_PID", "0") or "0")
        if pp <= 0:
            return False
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pp)          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return True                                # родителя не открыть -> считаем мёртвым
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return bool(ok) and code.value != 259          # 259 = STILL_ACTIVE
    except Exception:
        return False


def _watch_parent():
    # оркестратор умер -> не оставлять сирот (держащих loopback-порт и version-каталоги)
    while True:
        try:
            time.sleep(2.0)
            if _parent_dead():
                os._exit(0)
        except Exception:
            try:
                time.sleep(2.0)
            except Exception:
                pass


if __name__ == "__main__":
    t = threading.Thread(target=_watch_parent, daemon=True)
    t.start()
    sys.stderr.write("[sim_worker %s] port=%d app_ok=%s healthy=%s boot_ms=%d core_sha=%s\n"
                     % (VER, PORT, APP_OK, _health()["healthy"], BOOT_MS, (CORE_SHA or "")[:8]))
    sys.stderr.flush()
    _Server(("127.0.0.1", PORT), _H).serve_forever()
