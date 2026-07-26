# -*- coding: utf-8 -*-
"""§14 (Plan) + §21.2 plan coordination — transitions + version-check."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.plan_coordination import plans as PC

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def run():
    pc = PC.PlanCoordinator()
    p = pc.create("pl1", ["a", "b"], place="Cafe", created_at=0.0)
    check("PC1 создан plan (proposed, v1)", p["state"] == "proposed" and p["version"] == 1)

    r = pc.transition("pl1", "confirmed", 1)
    check("PC2 proposed -> confirmed ok", r["ok"] and r["plan"]["state"] == "confirmed" and r["plan"]["version"] == 2)

    # неверный переход (confirmed -> proposed недопустим)
    bad = pc.transition("pl1", "proposed", 2)
    check("PC3 недопустимый переход -> INVALID_TRANSITION", bad["code"] == "INVALID_TRANSITION")

    # version conflict (устаревшая версия)
    conf = pc.transition("pl1", "completed", 1)
    check("PC4 устаревшая версия -> VERSION_CONFLICT", conf["code"] == "VERSION_CONFLICT")

    ok = pc.transition("pl1", "completed", 2)
    check("PC5 confirmed -> completed ok", ok["ok"] and ok["plan"]["state"] == "completed")

    # completed терминально -> дальше нельзя
    term = pc.transition("pl1", "cancelled", 3)
    check("PC6 из completed нельзя (терминал)", term["code"] == "INVALID_TRANSITION")

    print("\n§14 plans: %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
