# -*- coding: utf-8 -*-
"""Kleal Matching Simulator — 3-колоночный стенд «PROD | OLD | NEW» на N синтетических юзерах.

Оркестратор БЕЗ движка: сам не импортит ни один matcher / core_v2 / kleal_* — поэтому ошибка импорта
любой версии не роняет стенд, а превращается в «красную колонку». Три версии крутятся в ОТДЕЛЬНЫХ
процессах-воркерах (`sim_worker.py`), у каждого свой `sys.modules['core_v2']` -> полная изоляция:
  - PROD = живой движок напарника с пода (app a6818949 + core_v2 99a0b38b),
  - OLD  = git HEAD (app_old.py 873214eb + core_v2 35f8e984),
  - NEW  = мой спринт (app.py 0a5b4f8e + тот же core_v2 35f8e984).
Все три ранжируют ОДИН пул из N юзеров (через `KLEAL_USERS`), поэтому разница = движок/обёртка, не данные.
Два попарных диффа: PROD↔OLD = дрейф движка напарника (живое vs git); OLD↔NEW = чисто мой спринт.

Запуск:  SIM_PORT=7090 SIM_USERS=1000 python3 kleal_sim.py
Только :7090 туннелится; воркеры слушают 127.0.0.1 на эфемерных портах. 8 боевых сервисов не трогаются.
"""
import os, sys, json, hashlib, time, socket, subprocess, threading, tempfile, shutil, atexit, signal
import urllib.request, urllib.error, concurrent.futures

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
from gen_users import gen_users, NOW, BCN               # ЕДИНСТВЕННЫЙ импорт «своего» — генератор пула (без движка)

# SRC_ROOT содержит services/ shared/ config/. Локально = корень репо; на поде = /root/kleal-sim.
SRC_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PROD_SRC = os.environ.get("KLEAL_PROD_SRC", "/root/kleal-ms")   # живой движок напарника (read-only источник)
N_USERS = int(os.environ.get("SIM_USERS", "1000"))
PORT = int(os.environ.get("SIM_PORT", "7090"))
WORKER_PY = os.path.join(HERE, "sim_worker.py")
ONLY = set(x.strip() for x in (os.environ.get("SIM_ONLY", "") or "").split(",") if x.strip())  # напр. "old,new"

# ------------------------------------------------------------------ манифест версий (источники файлов)
VERSIONS = [
    {"key": "prod", "label": "PROD (живой под)", "optional": True,
     "app_src": os.path.join(PROD_SRC, "services", "matching", "app.py"),
     "core_src": os.path.join(PROD_SRC, "services", "matching", "core_v2.py"),
     "config_src": os.path.join(PROD_SRC, "config"),
     "shared_src": os.path.join(PROD_SRC, "shared")},
    {"key": "old", "label": "OLD (git HEAD)", "optional": False,
     "app_src": os.path.join(SRC_ROOT, "services", "sim", "app_old.py"),
     "core_src": os.path.join(SRC_ROOT, "services", "matching", "core_v2.py"),
     "config_src": os.path.join(SRC_ROOT, "config"),
     "shared_src": os.path.join(SRC_ROOT, "shared")},
    {"key": "new", "label": "NEW (спринт)", "optional": False,
     "app_src": os.path.join(SRC_ROOT, "services", "matching", "app.py"),
     "core_src": os.path.join(SRC_ROOT, "services", "matching", "core_v2.py"),
     "config_src": os.path.join(SRC_ROOT, "config"),
     "shared_src": os.path.join(SRC_ROOT, "shared")},
]
if ONLY:
    VERSIONS = [v for v in VERSIONS if v["key"] in ONLY]
ORDER = [v["key"] for v in VERSIONS]

WORK = tempfile.mkdtemp(prefix="kleal_sim3_")
POOL_PATH = os.path.join(WORK, "pool.json")
WORKERS = {}                       # key -> {v,label,available,reason,vdir,port,proc,logf,health,respawns,last_spawn}
STOP = threading.Event()


# ------------------------------------------------------------------ сборка version-каталогов (copy, не symlink)
def _copy_pys(src_dir, dst_dir):
    os.makedirs(dst_dir, exist_ok=True)
    n = 0
    if os.path.isdir(src_dir):
        for fn in os.listdir(src_dir):
            sp = os.path.join(src_dir, fn)
            if os.path.isfile(sp) and fn.endswith(".py"):
                try:
                    shutil.copy2(sp, os.path.join(dst_dir, fn)); n += 1
                except Exception:
                    pass
    return n


def _copy_cfg(src_dir, dst_dir):
    os.makedirs(dst_dir, exist_ok=True)
    if os.path.isdir(src_dir):
        for fn in os.listdir(src_dir):
            sp = os.path.join(src_dir, fn)
            if os.path.isfile(sp) and (fn.endswith(".yaml") or fn.endswith(".yml") or fn.endswith(".json")):
                try:
                    shutil.copy2(sp, os.path.join(dst_dir, fn))
                except Exception:
                    pass


def _assemble(v):
    if not (os.path.isfile(v["app_src"]) and os.path.isfile(v["core_src"])):
        return None, "источник недоступен: %s" % v["app_src"]
    vdir = os.path.join(WORK, "versions", v["key"])
    mdir = os.path.join(vdir, "services", "matching")
    os.makedirs(mdir, exist_ok=True)
    try:
        shutil.copy2(v["app_src"], os.path.join(mdir, "app.py"))
        shutil.copy2(v["core_src"], os.path.join(mdir, "core_v2.py"))
    except Exception as e:
        return None, "copy failed: %s" % (str(e)[:120])
    _copy_cfg(v["config_src"], os.path.join(vdir, "config"))
    _copy_pys(v["shared_src"], os.path.join(vdir, "shared"))
    for junk in ("users.json", "kleal_store.json"):     # чтобы рантайм-данные не затеняли инъекцию пула/стора
        try:
            os.remove(os.path.join(mdir, junk))
        except OSError:
            pass
    cfg = os.path.join(vdir, "config", "Kleal_Matching_Core_Config_v2.yaml")
    if not os.path.isfile(cfg):
        return None, "config yaml отсутствует в источнике"
    return vdir, None


def _free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _spawn(v, vdir, port):
    env = dict(os.environ)
    env.update({"SIM_VER": v["key"], "SIM_VER_DIR": vdir, "SIM_WORKER_PORT": str(port),
                "SIM_PARENT_PID": str(os.getpid()), "SIM_NOW": repr(NOW), "KLEAL_USERS": POOL_PATH,
                "KLEAL_STORE": os.path.join(WORK, "store_%s.json" % v["key"]),
                "KLEAL_CORE_CONFIG": os.path.join(vdir, "config", "Kleal_Matching_Core_Config_v2.yaml"),
                "KLEAL_CORE_V2": "1", "KLEAL_MERGE_DEMO": "0", "V2_MODEL": "sim",
                "LLM_URL": "http://127.0.0.1:1", "PYTHONHASHSEED": "0"})
    logf = open(os.path.join(WORK, "worker_%s.log" % v["key"]), "ab", buffering=0)
    kw = {"start_new_session": True} if os.name == "posix" else {}
    proc = subprocess.Popen([sys.executable, "-u", WORKER_PY], env=env, stdout=logf, stderr=logf,
                            stdin=subprocess.DEVNULL, **kw)
    return proc, logf


# ------------------------------------------------------------------ клиент к воркерам (loopback HTTP)
def _wget(port, path, timeout=5):
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _wpost(port, path, obj, timeout=12):
    data = json.dumps(obj).encode("utf-8")
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _poll_health():
    for k, w in WORKERS.items():
        if not w.get("available"):
            continue
        try:
            w["health"] = _wget(w["port"], "/health", timeout=4)
        except Exception as e:
            w["health"] = {"ver": k, "ok": False, "healthy": False, "unreachable": str(e)[:140]}


def _alive(w):
    return bool(w.get("available") and w.get("proc") and w["proc"].poll() is None)


def _fair(k):
    """Колонка «честна» для сравнения только если реально ранжирует ВЕСЬ инъектированный пул
    (from_store + pool_count==N). Иначе движок тихо упал на встроенный ~50-юзерный demo-пул —
    сравнивать его с 1000-пулом других колонок нельзя (это не «дрейф движка»)."""
    if not _alive(WORKERS.get(k, {})):
        return False
    h = WORKERS.get(k, {}).get("health") or {}
    return bool(h.get("from_store")) and int(h.get("pool_count") or 0) == N_USERS


# ------------------------------------------------------------------ жизненный цикл: старт / сторож / стоп
def _boot():
    pool = gen_users(N_USERS)
    with open(POOL_PATH, "w", encoding="utf-8") as f:
        json.dump(pool, f)
    for v in VERSIONS:
        k = v["key"]
        vdir, err = _assemble(v)
        if not vdir:
            WORKERS[k] = {"v": v, "label": v["label"], "available": False, "reason": err, "health": None}
            sys.stderr.write("[sim] %s UNAVAILABLE: %s\n" % (k, err))
            continue
        open(os.path.join(WORK, "store_%s.json" % k), "w").write("{}")
        port = _free_port()
        proc, logf = _spawn(v, vdir, port)
        WORKERS[k] = {"v": v, "label": v["label"], "available": True, "reason": None, "vdir": vdir,
                      "port": port, "proc": proc, "logf": logf, "health": None,
                      "respawns": 0, "last_spawn": time.time()}
        sys.stderr.write("[sim] spawned %s pid=%d port=%d\n" % (k, proc.pid, port))
    # health-gate: готово, когда обязательные (не optional, доступные) воркеры healthy
    need = [v["key"] for v in VERSIONS if not v["optional"] and WORKERS.get(v["key"], {}).get("available")]
    t0 = time.time()
    while time.time() - t0 < 30:
        _poll_health()
        if all((WORKERS.get(k, {}).get("health") or {}).get("healthy") for k in need):
            break
        time.sleep(0.4)
    threading.Thread(target=_watchdog, daemon=True).start()


def _watchdog():
    while not STOP.is_set():
        STOP.wait(10)
        if STOP.is_set():
            break
        _poll_health()
        for k, w in list(WORKERS.items()):
            if not w.get("available"):
                continue
            proc = w.get("proc")
            dead = proc is not None and proc.poll() is not None
            if dead and w.get("respawns", 0) < 2 and (time.time() - w.get("last_spawn", 0) > 30):
                try:
                    port = _free_port()
                    np, lf = _spawn(w["v"], w["vdir"], port)
                    w.update({"proc": np, "logf": lf, "port": port,
                              "respawns": w.get("respawns", 0) + 1, "last_spawn": time.time()})
                    sys.stderr.write("[sim] respawned %s pid=%d port=%d (#%d)\n" % (k, np.pid, port, w["respawns"]))
                except Exception as e:
                    sys.stderr.write("[sim] respawn %s failed: %s\n" % (k, str(e)[:120]))


def _shutdown(*a):
    if STOP.is_set():
        return
    STOP.set()
    for k, w in WORKERS.items():
        proc = w.get("proc")
        if proc and proc.poll() is None:
            try:
                if os.name == "posix":
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                else:
                    proc.terminate()
            except Exception:
                pass
    for k, w in WORKERS.items():
        proc = w.get("proc")
        if proc and proc.poll() is None:
            try:
                proc.wait(timeout=3)
            except Exception:
                try:
                    if os.name == "posix":
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    else:
                        proc.kill()
                except Exception:
                    pass
    try:
        shutil.rmtree(WORK, ignore_errors=True)
    except Exception:
        pass


# ------------------------------------------------------------------ построение интента из формы
def build_intent(f):
    topics = [t.strip().lower() for t in str(f.get("topics") or "").replace(";", ",").split(",") if t.strip()]
    langs = [l.strip().lower() for l in str(f.get("requiredLanguages") or "").replace(";", ",").split(",") if l.strip()]
    try:
        rk = float(f.get("radiusKm") or 15)
    except Exception:
        rk = 15.0
    it = {"type": str(f.get("type") or "social"), "topics": topics or ["coffee"],
          "role": str(f.get("role") or "meet"), "mode": str(f.get("mode") or "offline"),
          "time": str(f.get("time") or "Flexible"), "radiusKm": rk,
          "requiredLanguages": langs, "verifiedOnly": bool(f.get("verifiedOnly")),
          "exactMatchRequired": bool(f.get("exactMatchRequired")),
          "adjacentAllowed": bool(f.get("adjacentAllowed", True)), "broadAllowed": bool(f.get("broadAllowed", True))}
    if f.get("minAge"):
        try:
            it["minAge"] = int(f.get("minAge"))
        except Exception:
            pass
    if f.get("maxAge"):
        try:
            it["maxAge"] = int(f.get("maxAge"))
        except Exception:
            pass
    return it


def build_searcher(f):
    ints = [t.strip().lower() for t in str(f.get("myInterests") or f.get("topics") or "coffee").replace(";", ",").split(",") if t.strip()]
    langs = [l.strip().lower() for l in str(f.get("myLangs") or "en").replace(";", ",").split(",") if l.strip()]
    return {"name": "ME", "vibe": str(f.get("myVibe") or "chill"), "interests": ints or ["coffee"],
            "langs": langs or ["en"], "geo": {"coarseLat": BCN[0], "coarseLon": BCN[1]},
            "coarseLat": BCN[0], "coarseLon": BCN[1],
            # искатель — полноценный участник (в т.ч. для dating: взаимное согласие), verified, принимает
            "datingOk": True, "verified": True, "open": True, "receiving": {"status": "active"}}


# ------------------------------------------------------------------ диффы (в оркестраторе, из слейтов)
def _names(sl):
    return [c.get("name") for c in (sl or [])]


def _keys_of(sl):
    return set(((sl[0].get("_keys") if sl else []) or [])) if sl else set()


def _diff_pair(a, b, compare_scores):
    if a is None or b is None:
        return {"available": False}
    na, nb = _names(a), _names(b)
    sa = {c.get("name"): c for c in a}
    sb = {c.get("name"): c for c in b}
    common = [n for n in na if n in sb]
    setA, setB = set(na), set(nb)
    uni = len(setA | setB) or 1
    ra = {n: i for i, n in enumerate(na)}
    rb = {n: i for i, n in enumerate(nb)}
    moves = [{"name": n, "rank_a": ra[n], "rank_b": rb[n], "delta": rb[n] - ra[n]} for n in common if ra[n] != rb[n]]
    moves.sort(key=lambda x: -abs(x["delta"]))
    out = {"available": True, "order_identical": (na == nb), "count_a": len(a), "count_b": len(b),
           "jaccard": round(len(setA & setB) / uni, 3), "only_a": [n for n in na if n not in sb][:20],
           "only_b": [n for n in nb if n not in sa][:20], "rank_moves": moves[:12], "n_moved": len(moves)}
    if compare_scores:
        deltas = []
        for n in common:
            va, vb = sa[n].get("score"), sb[n].get("score")
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)) and round(va, 4) != round(vb, 4):
                deltas.append({"name": n, "score_a": va, "score_b": vb, "delta": round(vb - va, 4)})
        deltas.sort(key=lambda x: -abs(x["delta"]))
        out["score_deltas"] = deltas[:12]
        out["n_score_changed"] = len(deltas)
        out["new_only_fields"] = sorted(_keys_of(b) - _keys_of(a))[:30]
    return out


def _field_diffs(slates):
    kp, ko, kn = _keys_of(slates.get("prod")), _keys_of(slates.get("old")), _keys_of(slates.get("new"))
    return {"prod_minus_old": sorted(kp - ko)[:30] if slates.get("prod") else None,
            "new_minus_old": sorted(kn - ko)[:30],
            "new_minus_prod": sorted(kn - kp)[:30] if slates.get("prod") else None}


def _union_table(slates):
    has_prod = bool(slates.get("prod"))
    rankmaps = {}
    for k in ORDER:
        sl = slates.get(k) or []
        rankmaps[k] = {c.get("name"): (i, c) for i, c in enumerate(sl)}
    allnames = []
    for k in ORDER:
        for n in _names(slates.get(k)):
            if n not in allnames:
                allnames.append(n)
    rows = []
    for n in allnames[:40]:
        per = {}
        for k in ORDER:
            rc = rankmaps[k].get(n)
            per[k] = {"rank": rc[0], "score": rc[1].get("score"), "tier": rc[1].get("tier")} if rc else None
        in_old = per.get("old") is not None
        in_new = per.get("new") is not None
        in_prod = per.get("prod") is not None
        r_old = per["old"]["rank"] if in_old else None
        r_new = per["new"]["rank"] if in_new else None
        r_prod = per["prod"]["rank"] if in_prod else None
        sprint_diff = (in_old != in_new) or (r_old != r_new)
        drift_diff = has_prod and ((in_prod != in_old) or (r_prod != r_old))
        tint = "sprint" if sprint_diff else ("drift" if drift_diff else "same")
        note = ""
        if in_new and not in_old:
            note = "добавлен спринтом"
        elif in_old and not in_new:
            note = "убран спринтом (гейт)"
        rows.append({"name": n, "per": per, "tint": tint, "note": note})
    return rows


def _pool_mismatch():
    shas = set()
    for k, w in WORKERS.items():
        h = w.get("health") or {}
        ps = h.get("pool_sha")
        if ps:
            shas.add(ps)
    return len(shas) > 1


def _version_meta(k):
    w = WORKERS.get(k, {})
    h = w.get("health") or {}
    return {"key": k, "label": w.get("label"), "available": bool(w.get("available")),
            "alive": _alive(w), "reason": w.get("reason"), "health": h}


# ------------------------------------------------------------------ основной прогон /run
def run_compare(f):
    intent = build_intent(f)
    prof = build_searcher(f)
    ctx = {"now": NOW, "self": "ME", "uid": "ME"}
    _poll_health()                               # свежая health -> актуальные _fair / _pool_mismatch
    live = [(k, WORKERS[k]) for k in ORDER if _alive(WORKERS.get(k, {}))]
    results = {}

    def _do(item):
        k, w = item
        try:
            return k, _wpost(w["port"], "/match", {"intent": intent, "prof": prof, "ctx": ctx}, timeout=12)
        except Exception as e:
            return k, {"ver": k, "slate": [], "count": 0, "error": str(e)[:200], "unreachable": True}

    if live:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(live))) as ex:
            for k, res in ex.map(_do, live):
                results[k] = res

    slates = {k: (results.get(k, {}).get("slate") or []) for k in ORDER}
    fair = {k: _fair(k) for k in ORDER}
    # только пул, ранжировавший ВЕСЬ инъектированный набор, сравним; demo-fallback колонку показываем,
    # но исключаем из диффов/union, чтобы 50-vs-1000 никогда не выдавалось за «дрейф движка».
    fslates = {k: (slates[k] if fair.get(k) else []) for k in ORDER}
    has_prod = "prod" in ORDER and bool(WORKERS.get("prod", {}).get("available")) and bool(fair.get("prod"))
    unfair = [k for k in ORDER if _alive(WORKERS.get(k, {})) and not fair.get(k)]
    out = {"intent": intent, "order": ORDER, "has_prod": has_prod, "unfair": unfair,
           "versions": {k: dict(_version_meta(k), fair=bool(fair.get(k))) for k in ORDER},
           "results": {k: {"count": results.get(k, {}).get("count", 0), "ms": results.get(k, {}).get("ms"),
                           "error": results.get(k, {}).get("error"), "fair": bool(fair.get(k)),
                           "pool_count": (WORKERS.get(k, {}).get("health") or {}).get("pool_count")} for k in ORDER},
           "columns": {k: slates[k][:14] for k in ORDER},
           "diff_old_new": (_diff_pair(fslates.get("old"), fslates.get("new"), compare_scores=True)
                            if (fair.get("old") and fair.get("new")) else {"available": False}),
           "diff_prod_old": (_diff_pair(fslates.get("prod"), fslates.get("old"), compare_scores=False)
                             if (has_prod and fair.get("old")) else {"available": False}),
           "field_diffs": _field_diffs(fslates),
           "union": _union_table(fslates),
           "pool_sha_mismatch": _pool_mismatch()}

    # ---- NEW-only showcases через /diag воркера NEW (только на честных пулах) ----
    new_w = WORKERS.get("new")
    on, nn = _names(fslates.get("old")), _names(fslates.get("new"))
    excluded = [n for n in on if n not in set(nn)]
    if new_w and _alive(new_w) and excluded:
        try:
            d = _wpost(new_w["port"], "/diag", {"op": "policy", "intent": intent, "names": excluded[:24]}, timeout=10)
            out["excluded_reasons"] = d.get("items") if d.get("supported") else None
        except Exception:
            out["excluded_reasons"] = None
    if intent.get("type") == "dating" and nn and new_w and _alive(new_w):
        try:
            out["dating_capsule"] = _wpost(new_w["port"], "/diag", {"op": "capsule", "name": nn[0]}, timeout=10)
        except Exception as e:
            out["dating_capsule"] = {"error": str(e)[:160]}
    gs = f.get("groupSize")
    if gs and new_w and _alive(new_w):
        try:
            if int(gs) > 1:
                out["group"] = _wpost(new_w["port"], "/diag",
                                      {"op": "group", "intent": intent, "prof": prof, "ctx": ctx, "size_min": int(gs)},
                                      timeout=15)
        except Exception as e:
            out["group"] = {"error": str(e)[:160]}
    return out


def run_stability(f, k_runs=4):
    """Прогнать текущий запрос K раз на каждой живой версии и вернуть, стабилен ли порядок (churn)."""
    intent = build_intent(f)
    prof = build_searcher(f)
    ctx = {"now": NOW, "self": "ME", "uid": "ME"}
    out = {}
    for k in ORDER:
        w = WORKERS.get(k, {})
        if not _alive(w):
            out[k] = {"available": False}
            continue
        seqs = []
        try:
            for _ in range(max(2, int(k_runs))):
                r = _wpost(w["port"], "/match", {"intent": intent, "prof": prof, "ctx": ctx}, timeout=12)
                seqs.append([c.get("name") for c in (r.get("slate") or [])])
            stable = all(s == seqs[0] for s in seqs)
            out[k] = {"available": True, "stable": stable, "runs": len(seqs), "n": len(seqs[0]) if seqs else 0}
        except Exception as e:
            out[k] = {"available": True, "error": str(e)[:160]}
    return out


# ------------------------------------------------------------------ UI
HTML = r'''<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Kleal Matching — стенд PROD | OLD | NEW</title>
<style>
:root{--bg:#0f1115;--card:#171a21;--fg:#e7eaf0;--mut:#98a2b3;--bd:#252a33;--prod:#5b8cff;--old:#c98a2b;--new:#2f9e6b;--acc:#5b8cff;--warn:#e0b54a;--bad:#e07a6a}
*{box-sizing:border-box}body{margin:0;font:14px/1.5 ui-sans-serif,system-ui,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--fg)}
.wrap{max-width:1320px;margin:0 auto;padding:20px}
h1{font-size:19px;margin:0 0 4px}.sub{color:var(--mut);margin:0 0 16px;font-size:13px}
.panel{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:14px 16px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
label{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--mut);margin-bottom:3px}
input,select{width:100%;background:#0c0e12;color:var(--fg);border:1px solid var(--bd);border-radius:8px;padding:7px 9px;font:inherit}
.row{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin-top:10px}
.chk{display:flex;gap:6px;align-items:center;font-size:13px;color:var(--fg);text-transform:none;letter-spacing:0}
.chk input{width:auto}
button{background:var(--acc);color:#fff;border:0;border-radius:9px;padding:10px 20px;font:600 14px/1 inherit;cursor:pointer}
button.ghost{background:#0c0e12;color:var(--fg);border:1px solid var(--bd)}
button:hover{filter:brightness(1.08)}
.rail{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px}
@media(max-width:900px){.rail{grid-template-columns:1fr}}
.vc{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:10px 12px;font-size:12px}
.vc h3{margin:0 0 6px;font-size:13px;display:flex;justify-content:space-between;align-items:center}
.vc.prod{border-top:3px solid var(--prod)}.vc.old{border-top:3px solid var(--old)}.vc.new{border-top:3px solid var(--new)}
.dot{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:5px}
.dot.g{background:var(--new)}.dot.a{background:var(--warn)}.dot.r{background:var(--bad)}
.kx{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;color:var(--mut)}
.kx b{color:var(--fg)}
.warnpill{display:inline-block;font-size:11px;padding:1px 7px;border-radius:6px;background:rgba(224,122,106,.14);color:var(--bad);border:1px solid #e07a6a55;margin-top:4px}
.okpill{display:inline-block;font-size:11px;padding:1px 7px;border-radius:6px;background:rgba(47,158,107,.14);color:var(--new);border:1px solid #2f9e6b55;margin-top:4px}
.banner{border-radius:10px;padding:11px 14px;margin:12px 0;font-size:13px;background:#12202b;border:1px solid #23414f}
.banner.bad{background:rgba(224,122,106,.1);border-color:#e07a6a55;color:#f0b6ac}
.banner.warn{background:rgba(224,181,74,.1);border-color:#e0b54a55}
.diffwrap{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:900px){.diffwrap{grid-template-columns:1fr}}
.diff{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:13px 15px}
.diff h2{font-size:14px;margin:0 0 3px}.diff .th{color:var(--mut);font-size:12px;margin:0 0 9px}
.diff.drift{border-left:3px solid var(--old)}.diff.sprint{border-left:3px solid var(--new)}
.metric{display:inline-block;font-size:12px;margin:2px 10px 2px 0}.metric b{color:var(--fg)}
.cols{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:6px}
.cols.two{grid-template-columns:repeat(2,1fr)}
@media(max-width:900px){.cols,.cols.two{grid-template-columns:1fr}}
.col h2{font-size:14px;margin:0 0 8px;display:flex;justify-content:space-between;align-items:center}
.tag{font-size:11px;padding:2px 9px;border-radius:20px;font-weight:700}
.tag.prod{background:rgba(91,140,255,.16);color:var(--prod)}.tag.old{background:rgba(201,138,43,.16);color:var(--old)}.tag.new{background:rgba(47,158,107,.16);color:var(--new)}
.cd{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:8px 10px;margin-bottom:6px}
.cd.prod{border-left:3px solid var(--prod)}.cd.old{border-left:3px solid var(--old)}.cd.new{border-left:3px solid var(--new)}
.cd .nm{font-weight:650}.cd .meta{color:var(--mut);font-size:12px;margin-top:2px}
.pill{display:inline-block;font-size:11px;padding:1px 7px;border-radius:6px;background:#0c0e12;border:1px solid var(--bd);margin:2px 3px 0 0;color:var(--mut)}
.pill.b{color:var(--new);border-color:#2f9e6b55}.pill.p{color:var(--prod);border-color:#5b8cff55}
.excl{color:var(--bad);font-size:12px}.small{color:var(--mut);font-size:12px}
pre{background:#0c0e12;border:1px solid var(--bd);border-radius:8px;padding:9px;overflow:auto;font-size:12px;margin:6px 0}
table{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}
th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--bd)}
th{color:var(--mut);font-weight:600;text-transform:uppercase;font-size:10px;letter-spacing:.04em}
tr.same td{opacity:.62}tr.drift{background:rgba(201,138,43,.07)}tr.sprint{background:rgba(47,158,107,.08)}
.hint{color:var(--mut);font-size:12px;margin-top:6px}
details{margin-top:8px}summary{cursor:pointer;color:var(--mut);font-size:12px}
.mono{font-family:ui-monospace,Menlo,Consolas,monospace}
</style></head><body><div class="wrap">
<h1>Kleal Matching — стенд «PROD | OLD | NEW»</h1>
<p class="sub">__NU__ синтетических юзеров · три изолированных движка · матчинг детерминирован и без LLM. <b>PROD↔OLD</b> = дрейф движка напарника (живое vs git); <b>OLD↔NEW</b> = чисто мой спринт.</p>
<div class="panel">
  <div class="grid">
    <div><label>Темы (через запятую)</label><input id="topics" value="coffee, chess"></div>
    <div><label>Тип</label><select id="type"><option>social</option><option>dating</option><option>games</option><option>networking</option><option>language</option><option>sport</option></select></div>
    <div><label>Роль</label><select id="role"><option>meet</option><option>play</option><option>watch</option><option>discuss</option><option>practise</option></select></div>
    <div><label>Режим</label><select id="mode"><option>offline</option><option>online</option></select></div>
    <div><label>Радиус, км</label><input id="radiusKm" type="number" value="15"></div>
    <div><label>Языки (req)</label><input id="requiredLanguages" placeholder="es"></div>
    <div><label>Мин. возраст</label><input id="minAge" type="number" placeholder="18"></div>
    <div><label>Размер группы (§15)</label><input id="groupSize" type="number" placeholder="0"></div>
    <div><label>Мои интересы</label><input id="myInterests" value="coffee"></div>
    <div><label>Мой вайб</label><select id="myVibe"><option>chill</option><option>social</option><option>deep</option><option>energetic</option></select></div>
  </div>
  <div class="row">
    <span class="chk"><input type="checkbox" id="verifiedOnly"><label style="margin:0">только verified</label></span>
    <span class="chk"><input type="checkbox" id="exactMatchRequired"><label style="margin:0">exact match</label></span>
    <button onclick="runIt()">Сравнить PROD · OLD · NEW</button>
    <button class="ghost" onclick="stab()">Проверка стабильности ×4</button>
  </div>
  <div class="hint">Подсказки: <b>тип=dating</b> — минимизация dating-капсулы у NEW · <b>размер группы ≥3</b> — NEW формирует группу (§15) · редкий язык — NEW отсеет по гейту · смотри провенанс-плашки: core_sha PROD (99a0b38b) ≠ OLD/NEW (35f8e984) — это и есть разные движки.</div>
</div>
<div id="rail" class="rail"></div>
<div id="out"></div>
<script>
function val(id){var e=document.getElementById(id);return e.type==='checkbox'?e.checked:e.value}
function esc(s){return String(s==null?'':s).replace(/[&<>]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[c]})}
function form(){return {topics:val('topics'),type:val('type'),role:val('role'),mode:val('mode'),radiusKm:val('radiusKm'),
  requiredLanguages:val('requiredLanguages'),minAge:val('minAge'),groupSize:val('groupSize'),
  myInterests:val('myInterests'),myVibe:val('myVibe'),verifiedOnly:val('verifiedOnly'),exactMatchRequired:val('exactMatchRequired')}}
var LABEL={prod:'PROD (живой под)',old:'OLD (git HEAD)',new:'NEW (спринт)'};
function railCard(k,v){
  var h=v.health||{},cls=k,ok=h.healthy,dot=ok?'g':(v.available?(h.ok?'a':'r'):'r');
  var s='<div class="vc '+cls+'"><h3><span><span class="dot '+dot+'"></span>'+esc(LABEL[k]||k)+'</span><span class="small">'+(v.available?(ok?'healthy':'degraded'):'н/д')+'</span></h3>';
  if(!v.available){s+='<div class="small">'+esc(v.reason||'источник недоступен')+'</div>';
    s+='<div class="warnpill">колонка отключена</div></div>';return s}
  s+='<div class="kx">app <b>'+esc(h.app_sha||'?')+'</b> · core <b>'+esc(h.core_sha||'?')+'</b></div>';
  s+='<div class="kx">config '+esc(h.config_version||'?')+' <b>'+esc(h.config_sha||'')+'</b> · pool '+esc(h.pool_sha||'?')+' ('+esc(h.pool_count||0)+')</div>';
  if(h.core_v2_enabled===false)s+='<div class="warnpill">LEGACY FALLBACK — core_v2 выкл</div>';
  if(k==='prod'&&h.core_sha&&h.core_sha.indexOf('99a0b38b')!==0)s+='<div class="warnpill">core drift: '+esc(h.core_sha)+' (ожидался 99a0b38b)</div>';
  if(h.deterministic===false)s+='<div class="warnpill">non-deterministic ⚠</div>';
  else if(h.selftest_ok)s+='<div class="okpill">детерминизм ✓ '+esc(h.selftest_digest||'')+'</div>';
  if(h.import_error)s+='<details><summary>import error</summary><pre>'+esc(h.import_error)+'</pre></details>';
  return s+'</div>';
}
function renderRail(d){
  if(!d||!d.versions){return;}
  var order=d.order||['prod','old','new'],h='';
  order.forEach(function(k){h+=railCard(k,d.versions[k]||{available:false})});
  document.getElementById('rail').innerHTML=h;
}
function card(k,c){
  var pills='';
  if(c.score!=null)pills+='<span class="pill">score '+esc(c.score)+'</span>';
  if(c.tier)pills+='<span class="pill">'+esc(c.tier)+'</span>';
  if(c.band)pills+='<span class="pill b">band '+esc(c.band)+'</span>';
  if(c.decision_class)pills+='<span class="pill">'+esc(c.decision_class)+'</span>';
  if(c.policy)pills+='<span class="pill p">policy '+esc(c.policy)+'</span>';
  if(c.readiness)pills+='<span class="pill">'+esc(c.readiness)+'</span>';
  if(c.has_profile_view)pills+='<span class="pill p">profile_view</span>';
  if(c.has_trace)pills+='<span class="pill p">trace</span>';
  if(c.has_completion)pills+='<span class="pill p">completion</span>';
  return '<div class="cd '+k+'"><div class="nm">'+esc(c.name)+' <span class="small">'+(c.km!=null?c.km+' км':'')+'</span></div>'+
    '<div class="meta">'+((c.interests||[]).join(', '))+' · '+esc(c.vibe||'')+' · '+esc(c.age||'')+'</div>'+
    '<div>'+pills+'</div></div>';
}
function diffOldNew(df){
  if(!df||!df.available)return '';
  var h='<div class="diff sprint"><h2>OLD → NEW · твой спринт</h2><p class="th">Тот же core_v2 (35f8e984) + тот же конфиг + тот же kleal_lib — всё, что ниже, на 100% твой спринт.</p>';
  h+='<span class="metric">порядок людей: <b>'+(df.order_identical?'идентичен ✅':'изменился')+'</b></span>';
  h+='<span class="metric">score изменён у: <b>'+(df.n_score_changed||0)+'</b></span>';
  h+='<span class="metric">убрано гейтом NEW: <b>'+((df.only_a||[]).length)+'</b></span>';
  h+='<span class="metric">добавлено NEW: <b>'+((df.only_b||[]).length)+'</b></span>';
  if((df.new_only_fields||[]).length){h+='<div class="small" style="margin-top:8px">Новые поля на карточке NEW:</div>'+
    df.new_only_fields.map(function(x){return '<span class="pill b mono">'+esc(x)+'</span>'}).join(' ');}
  if((df.score_deltas||[]).length){h+='<details><summary>score-дельты ('+df.n_score_changed+')</summary><pre>'+
    df.score_deltas.map(function(x){return x.name+': '+x.score_a+' → '+x.score_b+' ('+(x.delta>0?'+':'')+x.delta+')'}).join('\n')+'</pre></details>';}
  return h+'</div>';
}
function diffProdOld(df,has){
  if(!has)return '<div class="diff drift"><h2>PROD → OLD · дрейф движка напарника</h2><p class="th">PROD-колонка недоступна (нет /root/kleal-ms или не импортится) — сравнение живого движка с git отключено.</p></div>';
  if(!df||!df.available)return '';
  var h='<div class="diff drift"><h2>PROD → OLD · дрейф движка напарника</h2><p class="th">PROD = живой движок напарника (снимок с пода); OLD = git HEAD. Разница здесь — его незакоммиченный дрейф, НЕ твой спринт. Разные core_v2 ⇒ сырые score не сравниваем.</p>';
  h+='<span class="metric">порядок: <b>'+(df.order_identical?'идентичен':'разошёлся')+'</b></span>';
  h+='<span class="metric">Jaccard top: <b>'+esc(df.jaccard)+'</b></span>';
  h+='<span class="metric">сдвинуто по рангу: <b>'+(df.n_moved||0)+'</b></span>';
  h+='<span class="metric">только в PROD: <b>'+((df.only_a||[]).length)+'</b></span>';
  h+='<span class="metric">только в OLD: <b>'+((df.only_b||[]).length)+'</b></span>';
  if((df.rank_moves||[]).length){h+='<details><summary>кто сдвинулся ('+df.n_moved+')</summary><pre>'+
    df.rank_moves.map(function(x){return x.name+': #'+x.rank_a+' (PROD) vs #'+x.rank_b+' (OLD)'}).join('\n')+'</pre></details>';}
  return h+'</div>';
}
function unionTable(rows,order){
  if(!rows||!rows.length)return '';
  var h='<div class="panel"><b>Сводная таблица (по людям)</b> <span class="small">— зелёный: изменил спринт · янтарь: дрейф PROD↔OLD</span><table><tr><th>Кандидат</th>';
  order.forEach(function(k){h+='<th>'+k.toUpperCase()+' ранг·score</th>'});
  h+='<th>примечание</th></tr>';
  rows.forEach(function(r){
    h+='<tr class="'+r.tint+'"><td class="mono">'+esc(r.name)+'</td>';
    order.forEach(function(k){var p=r.per[k];h+='<td>'+(p?('#'+(p.rank+1)+' · '+(p.score==null?'—':p.score)):'<span class="small">—</span>')+'</td>'});
    h+='<td class="small">'+esc(r.note||'')+'</td></tr>';
  });
  return h+'</table></div>';
}
function render(d){
  if(d&&d.error){document.getElementById('out').innerHTML='<div class="banner bad">Ошибка стенда: '+esc(d.error)+'</div>';return;}
  renderRail(d);
  var order=d.order||['prod','old','new'],h='';
  if(d.pool_sha_mismatch)h+='<div class="banner bad"><b>DATA MISMATCH</b> — набор кандидатов у версий различается: различия НЕ чисто движковые. Проверь KLEAL_USERS.</div>';
  if((d.unfair||[]).length)h+='<div class="banner bad"><b>'+d.unfair.join(', ').toUpperCase()+'</b> ранжирует НЕ полный пул (движок упал на встроенный ~50-юзерный demo-набор) — эта колонка исключена из сравнения.</div>';
  if(!d.has_prod)h+='<div class="banner warn">PROD-колонка недоступна для сравнения (нет живого /root/kleal-ms, падает импорт или demo-пул) — стенд работает в режиме OLD↔NEW; история спринта полностью доступна.</div>';
  var zero=order.filter(function(k){var r=(d.results||{})[k]||{};return r.fair&&!r.error&&(r.count||0)===0;});
  var nonzero=order.filter(function(k){var r=(d.results||{})[k]||{};return (r.count||0)>0;});
  if(zero.length&&nonzero.length)h+='<div class="banner warn"><b>'+zero.join(', ').toUpperCase()+'</b> вернул(и) <b>0 кандидатов</b> на этот запрос, а '+nonzero.join('/').toUpperCase()+' — нашли. Это НЕ поломка: движок просто иначе обрабатывает запрос. Известный случай: на <b>type=dating</b> живой PROD-движок напарника отдаёт пусто (git-движок OLD/NEW — нет).</div>';
  h+='<div class="diffwrap">'+diffOldNew(d.diff_old_new)+diffProdOld(d.diff_prod_old,d.has_prod)+'</div>';
  // exclusions с причинами
  if(d.excluded_reasons&&d.excluded_reasons.length){h+='<div class="panel"><b>Кого NEW не показал (OLD показывал) — причина (policy-gate либо ретрив/лимит §7):</b><br>';
    d.excluded_reasons.forEach(function(e){h+='<span class="excl">'+esc(e.name)+' — '+esc(e.decision)+': '+esc(e.reason)+'</span><br>'});h+='</div>';}
  // dating-капсула
  if(d.dating_capsule&&(d.dating_capsule.capsule||d.dating_capsule.raw)){var dc=d.dating_capsule;
    h+='<div class="panel"><b>Dating-капсула ('+esc(dc.name)+'):</b> NEW минимизирует чувствительное (возраст→диапазон, sensitive не отдаётся)<div class="cols two">'+
    '<div><div class="small">OLD-стиль — сырьё</div><pre>'+esc(JSON.stringify(dc.raw,null,1))+'</pre></div>'+
    '<div><div class="small">NEW — минимизированная капсула</div><pre>'+esc(JSON.stringify((dc.capsule||{}).fields||dc.capsule,null,1))+'</pre></div></div></div>';}
  // группа
  if(d.group){h+='<div class="panel"><b>Формирование группы (§15) — умеет только NEW:</b> '+
    (d.group.formed?('сформирована из '+((d.group.members)||[]).join(', ')+' · utility '+esc(d.group.utility)):'—')+
    '<div class="small">'+esc(d.group.note||d.group.error||(d.group.supported===false?'версия не поддерживает':''))+'</div></div>';}
  // три колонки
  var two=order.length<3||!d.has_prod;
  h+='<div class="cols'+(order.length===2?' two':'')+'">';
  order.forEach(function(k){
    var col=d.columns[k]||[],meta=d.results[k]||{};
    h+='<div class="col"><h2>'+esc(LABEL[k]||k)+' <span class="tag '+k+'">'+k.toUpperCase()+'</span></h2>';
    if(meta.error)h+='<div class="warnpill">ошибка: '+esc(meta.error)+'</div>';
    if(meta.fair===false&&!meta.error)h+='<div class="warnpill">demo-пул '+esc(meta.pool_count||'?')+' — исключена из сравнения</div>';
    h+='<div class="small">найдено '+esc(meta.count||0)+(meta.ms!=null?(' · '+meta.ms+' мс'):'')+'</div>';
    h+=(col.length?col.map(function(c){return card(k,c)}).join(''):'<p class="small">'+(meta.error?'—':'движок вернул 0 кандидатов на этот запрос')+'</p>')+'</div>';
  });
  h+='</div>';
  h+=unionTable(d.union,order);
  document.getElementById('out').innerHTML=h;
}
function runIt(){
  document.getElementById('out').innerHTML='<p class="small">Считаю на трёх движках…</p>';
  fetch('/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(form())})
   .then(function(r){return r.json()}).then(render).catch(function(e){document.getElementById('out').innerHTML='<pre>'+esc(e)+'</pre>'});
}
function stab(){
  document.getElementById('out').insertAdjacentHTML('afterbegin','<div class="banner" id="stabb">Проверка стабильности…</div>');
  fetch('/stability',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(form())})
   .then(function(r){return r.json()}).then(function(s){
     var b=document.getElementById('stabb');
     if(s&&s.error){if(b)b.innerHTML='ошибка: '+esc(s.error);return;}
     var h='<b>Стабильность (×4 прогона):</b> ';
     Object.keys(s).forEach(function(k){var v=s[k];h+=k.toUpperCase()+': '+(v.available===false?'н/д':(v.error?('ошибка'):(v.stable?'стабильно ✅':'НЕстабильно ⚠')))+' · '});
     if(b)b.innerHTML=h;
   }).catch(function(e){var b=document.getElementById('stabb');if(b)b.innerHTML='ошибка: '+esc(e)});
}
window.addEventListener('load',runIt);
</script></div></body></html>'''.replace("__NU__", str(N_USERS))

# ------------------------------------------------------------------ HTTP (оркестратор, :7090)
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, (bytes, bytearray)) else json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n).decode("utf-8") or "{}") if n else {}
        except Exception:
            return {}

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            self._send(200, HTML.encode("utf-8"), "text/html")
        elif p == "/health":
            _poll_health()
            self._send(200, {"ok": True, "users": N_USERS, "order": ORDER,
                             "versions": {k: _version_meta(k) for k in ORDER},
                             "pool_sha_mismatch": _pool_mismatch()})
        elif p == "/users":
            self._send(200, {"count": N_USERS, "sample": gen_users(min(N_USERS, 20))})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        p = self.path.split("?")[0]
        if p == "/run":
            try:
                b = self._body()
                self._send(200, run_compare(b if isinstance(b, dict) else {}))
            except Exception as e:
                self._send(200, {"error": str(e)[:300]})
        elif p == "/stability":
            try:
                b = self._body()
                self._send(200, run_stability(b if isinstance(b, dict) else {}))
            except Exception as e:
                self._send(200, {"error": str(e)[:300]})
        else:
            self._send(404, {"error": "not found"})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    atexit.register(_shutdown)
    for _sig in ("SIGTERM", "SIGINT"):
        try:
            signal.signal(getattr(signal, _sig), lambda *a: (_shutdown(), sys.exit(0)))
        except Exception:
            pass
    print("Kleal 3-col Simulator: booting workers (%d users, versions=%s)…" % (N_USERS, ",".join(ORDER)))
    _boot()
    avail = [k for k in ORDER if WORKERS.get(k, {}).get("available")]
    print("Kleal 3-col Simulator on http://127.0.0.1:%d  (available: %s)" % (PORT, ",".join(avail)))
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
