# -*- coding: utf-8 -*-
"""Удалённому из группы пишет Kleal — борд «GR · Offline — new layout», кадр GR.52.

    python3 tools/gr_removed_unit.py
"""
import importlib.util
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = os.path.join(ROOT, "services", "matching")
TMP = tempfile.mkdtemp(prefix="kleal-removed-")
os.environ["KLEAL_STORE"] = os.path.join(TMP, "store.json")
os.environ["KLEAL_REPORT_EVIDENCE_DIR"] = os.path.join(TMP, "evidence")
sys.path.insert(0, SERVICE)
spec = importlib.util.spec_from_file_location("matching_removed", os.path.join(SERVICE, "app.py"))
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


now = time.time()
g = {"id": "gr-rm", "title": "BBQ by the beach", "owner": "Mateo", "state": "ready_to_plan",
     "min_total": 3, "max_total": 3, "updated": now, "version": 1,
     "members": [{"name": "Mateo", "state": "joined", "joined": now - 90},
                 {"name": "Jane", "state": "joined", "joined": now - 60},
                 {"name": "Marc", "state": "joined", "joined": now - 30}]}
app.SESSION.clear()
app.SESSION["_gintents"] = [g]
app.SESSION["_gplans"] = []
app.SESSION["_gmsgs"] = []
r = app.gi_remove(g["id"], "Mateo", "Jane", "Rude in the chat")
check("removed", r.get("ok"), r)
th = app.thread("Jane", app.SAFETY_SENDER)
check("Kleal wrote to Jane once", len(th) == 1 and th[0].get("code") == "group_removed", th)
m = th[0] if th else {}
check("names organiser and group", m.get("by") == "Mateo" and m.get("title") == "BBQ by the beach"
      and "Mateo removed you from BBQ by the beach" in m.get("text", ""), m)
check("reason is not shared", "Rude" not in str(m), m)
row = next((t for t in app.threads_for("Jane") if t.get("who") == app.SAFETY_SENDER), {})
check("Messages preview carries the code", row.get("code") == "group_removed" and row.get("by") == "Mateo", row)
check("room line stays neutral", [(x.get("sys") or {}).get("code") for x in app.SESSION["_gmsgs"]] == ["removed"],
      app.SESSION["_gmsgs"])

check("peer 'Kleal' resolves to the Kleal thread", app._peer("", "Kleal", "Jane") == app.SAFETY_SENDER)
check("thread by resolved peer is not empty", len(app.thread("Jane", app._peer("", "Kleal", "Jane"))) == 1)

print("REMOVED RESULT: %d ok, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
