# -*- coding: utf-8 -*-
"""§10 reciprocity/readiness — states, completion factors, ML boundary (§23.3)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.config import validator as V
from matching_core.reciprocity_readiness import readiness as RD

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def run():
    cfg = V.load_config()
    now = 1752600000.0
    check("RD1 open flag -> open_now", RD.readiness_state({"open": True}, "social_meet", now, cfg) == "open_now")
    check("RD2 open False -> busy", RD.readiness_state({"open": False}, "social_meet", now, cfg) == "busy")
    check("RD3 нет данных -> unknown (≠ openness)", RD.readiness_state({}, "social_meet", now, cfg) == "unknown")
    check("RD4 paused", RD.readiness_state({"receiving": {"status": "paused", "paused_until": now + 100}}, "x", now, cfg) == "paused")
    check("RD5 fatigue -> busy",
          RD.readiness_state({"receiving": {"status": "active", "proposal_budget": {"per_24h": 2}}}, "social_meet", now, cfg, received_24h=2) == "busy")
    check("RD6 домен не разрешён -> passive_discovery",
          RD.readiness_state({"receiving": {"status": "active", "allowed_domains": ["dating"]}}, "social_meet", now, cfg) == "passive_discovery")
    check("RD7 readiness ordering (open_now < busy)", RD.READINESS_RANK["open_now"] < RD.READINESS_RANK["busy"])

    # completion factors — operational only, НЕ соц-рейтинг
    cf = RD.completion_factors({"open": True, "availableMinutes": 60, "minMeetMin": 30, "activePlans": 1})
    check("RD8 completion factors operational", cf["availability_fresh"] and cf["can_meet_min_duration"])
    check("RD9 completion НЕ содержит соц-рейтинга", "social_rating" not in cf and "score" not in cf)

    # ML boundary (§10.3): hard gates/privacy/... остаются deterministic
    m = RD.ml_boundary_manifest()
    check("RD10 hard_gates остаётся deterministic", "hard_gates" in m["stays_deterministic"])
    check("RD11 P_accept требует калибровки", "p_accept" in m["calibration_required_for"])

    print("\n§10 readiness: %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
