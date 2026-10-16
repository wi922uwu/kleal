# -*- coding: utf-8 -*-
"""Выбор финальной версии плана — договор борда «GR · Offline — new layout», кадр GR.29a.

    python3 tools/gr_rounds_unit.py

Три раунда: план организатора, встречное Jane, встречное Marc. Организатор закрепляет любую из
трёх; согласие считается по выбранной версии, «один организатор» по-прежнему не закрепляется.
"""
import importlib.util
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = os.path.join(ROOT, "services", "matching")
TMP = tempfile.mkdtemp(prefix="kleal-rounds-")
os.environ["KLEAL_STORE"] = os.path.join(TMP, "store.json")
os.environ["KLEAL_REPORT_EVIDENCE_DIR"] = os.path.join(TMP, "evidence")
sys.path.insert(0, SERVICE)
spec = importlib.util.spec_from_file_location("matching_rounds", os.path.join(SERVICE, "app.py"))
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

ok = fail = 0


def check(name, condition, detail=""):
    global ok, fail
    if condition:
        ok += 1
    else:
        fail += 1
        print("FAIL %-60s %s" % (name, str(detail)[:300]))


def three_rounds(marc_confirms_r1=False):
    now = time.time()
    g = {"id": "gr-rounds", "title": "BBQ by the beach", "owner": "Mateo", "state": "ready_to_plan",
         "min_total": 3, "max_total": 3, "updated": now, "version": 1, "mode": "offline",
         "members": [{"name": "Mateo", "state": "joined", "joined": now - 90},
                     {"name": "Jane", "state": "joined", "joined": now - 60},
                     {"name": "Marc", "state": "joined", "joined": now - 30}]}
    app.SESSION.clear()
    app.SESSION["_gintents"] = [g]
    app.SESSION["_gplans"] = []
    app.SESSION["_gmsgs"] = []
    app.SESSION["_gvotes"] = []
    r = app.gp_begin(g["id"], "Mateo", "Thu 23 July, 19:00", "Barceloneta", starts_at=now + 50 * 3600)
    pid = r["plan"]["id"]
    if marc_confirms_r1:
        app.gp_respond(pid, "Marc", "confirm")
    app.gp_respond(pid, "Jane", "counter", when="Fri 24 July, 20:00", starts_at=now + 73 * 3600)
    app.gp_respond(pid, "Marc", "counter", when="Fri 24 July, 20:30", starts_at=now + 73.5 * 3600)
    return g, app._gp_find(pid)


g, p = three_rounds()
log = p.get("rounds_log") or []
check("three versions logged", [r["round"] for r in log] == [1, 2, 3], log)
check("authors logged", [r["by"] for r in log] == ["Mateo", "Jane", "Marc"], log)
check("terms logged", log[1]["when"] == "Fri 24 July, 20:00" and log[0]["when"] == "Thu 23 July, 19:00", log)
pub = app._gp_public(p, "Mateo")["rounds_log"]
check("public rounds_log", len(pub) == 3 and pub[2]["by"] == "Marc", pub)

check("GR.29: organiser can fix before confirming", app._gp_public(p, "Mateo")["can_fix"] is True)

# 1. Без выбора — закрепляется текущая (Marc + Mateo).
r = app.gp_fix(p["id"], "Mateo")
check("default fix = latest", r.get("ok") and p["when"] == "Fri 24 July, 20:30" and p["state"] == "confirmed", r)

# 2. Выбор версии Jane: согласие Jane + Mateo — закрепляется со сроком и местом раунда 2.
g, p = three_rounds()
r = app.gp_fix(p["id"], "Mateo", round_no=2)
check("pick round 2 fixes Jane's terms", r.get("ok") and p["when"] == "Fri 24 July, 20:00"
      and p.get("fixed_round") == 2, (r.get("error"), p.get("when")))
check("round 2 confirmers are Jane and Mateo", sorted(app._gp_confirms(p)) == ["Jane", "Mateo"], app._gp_confirms(p))
check("Marc asked to stay or leave", "silent_stay_or_leave" in
      [(m.get("sys") or {}).get("code") for m in app.SESSION["_gmsgs"]])

# 3. Своя первая версия, которую никто не подтверждал, — указ: отказ, план не тронут.
g, p = three_rounds()
r = app.gp_fix(p["id"], "Mateo", round_no=1)
check("pick own unconfirmed round 1 refused", r.get("error") == "ALONE" and p["state"] == "proposed"
      and p["when"] == "Fri 24 July, 20:30", (r.get("error"), p["state"], p["when"]))

# 4. Если Marc подтвердил первую версию, пока она была текущей, — её можно закрепить.
g, p = three_rounds(marc_confirms_r1=True)
r = app.gp_fix(p["id"], "Mateo", round_no=1)
check("round 1 with Marc's confirm fixes", r.get("ok") and p["when"] == "Thu 23 July, 19:00", (r.get("error"), p["when"]))

# 5. Несуществующий раунд.
g, p = three_rounds()
check("unknown round refused", app.gp_fix(p["id"], "Mateo", round_no=7).get("error") == "NO_SUCH_ROUND")

print("ROUNDS RESULT: %d ok, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
