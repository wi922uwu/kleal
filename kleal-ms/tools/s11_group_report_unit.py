# -*- coding: utf-8 -*-
"""Focused S11 group safety-exit contract test. Uses an isolated store and evidence directory."""
import importlib.util
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = os.path.join(ROOT, "services", "matching")
TMP = tempfile.mkdtemp(prefix="kleal-s11-")
os.environ["KLEAL_STORE"] = os.path.join(TMP, "store.json")
os.environ["KLEAL_REPORT_EVIDENCE_DIR"] = os.path.join(TMP, "evidence")
sys.path.insert(0, SERVICE)
spec = importlib.util.spec_from_file_location("matching_s11", os.path.join(SERVICE, "app.py"))
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

ok = fail = 0


def check(name, condition, detail=""):
    global ok, fail
    if condition:
        ok += 1
    else:
        fail += 1
        print("FAIL %-56s %s" % (name, str(detail)[:240]))


now = time.time() - 60
g = {
    "id": "s11-main", "title": "Sunset walk", "topics": ["walking"],
    "owner": "Anna", "state": "planning", "min_total": 3, "max_total": 5,
    "members": [
        {"name": "Anna", "state": "joined", "joined": now},
        {"name": "Marc", "state": "joined", "joined": now + 1},
        {"name": "Jane", "state": "joined", "joined": now + 2},
    ],
    "updated": now, "version": 1,
}
app.SESSION.clear()
app.SESSION["_gintents"] = [g]
app.SESSION["_gplans"] = [{"id": "plan-s11", "gid": g["id"], "state": "proposed",
                            "when": "Saturday", "confirmed": ["Anna"]}]
app.SESSION["_gmsgs"] = [
    {"id": "before", "gid": g["id"], "frm": "Marc", "text": "hello",
     "t": now + 10, "u": now + 10, "kind": "msg"},
]
app.SESSION["_reports"] = []

check("unknown reason rejected", app.gi_report(g["id"], "Anna", "other").get("error") == "INVALID_REASON")
check("outsider cannot report", app.gi_report(g["id"], "Sofia", "rule_violation").get("error") == "NOT_A_MEMBER")

evidence = {
    "id": "a" * 32,
    "url": "/api/agent/report-evidence/%s.pdf" % ("a" * 32),
    "name": "timeline.pdf", "mime_type": "application/pdf", "size": "1200",
}
bad_evidence = dict(evidence, url="https://example.com/private-file")
result = app.gi_report(g["id"], "Anna", "harassment_or_threats", "Repeated threats",
                       [bad_evidence, evidence], "s11-once")
check("report is accepted", result.get("ok") is True and result.get("case_no", "").startswith("KLEAL-"), result)
check("idempotent retry returns same case",
      app.gi_report(g["id"], "Anna", "harassment_or_threats", idem="s11-once") == result)
check("only one case persisted", len(app.SESSION["_reports"]) == 1, app.SESSION["_reports"])
row = app.SESSION["_reports"][0]
check("case is marked as S11", row.get("source") == "group_s11" and row.get("state") == "received", row)
check("arbitrary evidence URL is discarded", len(row.get("evidence") or []) == 1
      and row["evidence"][0].get("url") == evidence["url"], row.get("evidence"))
check("details are private", not any("threat" in str(m).lower() for m in app.SESSION["_gmsgs"]), app.SESSION["_gmsgs"])
check("room sees only neutral departure", any((m.get("sys") or {}).get("code") == "left"
      for m in app.SESSION["_gmsgs"]), app.SESSION["_gmsgs"])
check("organiser role transfers", g.get("owner") == "Marc", g)
check("group drops below quorum", g.get("state") == "below_quorum", g)

archive = app.gi_thread(g["id"], "Anna")
check("reporter keeps read-only history", archive.get("ok") is True
      and archive.get("group", {}).get("read_only") is True, archive)
check("history is frozen before departure", [m.get("id") for m in archive.get("messages") or []] == ["before"], archive)
check("reporter cannot post after safety exit", app.gi_post(g["id"], "Anna", "after").get("ok") is not True)

stored = app.report_evidence_store("proof.pdf", "application/pdf", b"proof")
check("supported evidence is stored", stored.get("ok") is True and os.path.exists(
      os.path.join(os.environ["KLEAL_REPORT_EVIDENCE_DIR"], stored.get("url", "").rsplit("/", 1)[-1])), stored)
check("unsupported evidence is rejected",
      app.report_evidence_store("proof.exe", "application/octet-stream", b"proof").get("error")
      == "UNSUPPORTED_EVIDENCE_TYPE")

print("S11 RESULT: %d ok, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
