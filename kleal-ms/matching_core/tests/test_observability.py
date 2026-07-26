# -*- coding: utf-8 -*-
"""§21.3 observability — trace log + replay (C#24)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.config import validator as V
from matching_core.contracts import decision_trace as DT
from matching_core.observability import trace as OB

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def run():
    cfg = V.load_config()
    log = OB.TraceLog()
    tr = DT.build_decision_trace("s1", "u1", intent_version=7, config_version=cfg["config_version"],
                                 semantic_tier="T1",
                                 directional={"a_to_b": {"lcb": 0.8, "coverage": 0.8}, "b_to_a": {"lcb": 0.7}})
    log.log(tr)
    check("OB1 trace найден", log.find("s1", "u1") is not None)
    # immutable: изменение оригинала не трогает лог
    tr["semantic_tier"] = "T5"
    check("OB2 trace immutable в логе", log.find("s1", "u1")["semantic_tier"] == "T1")

    # C#24: replay воспроизводит band по той же версии конфига
    rp = OB.replay(log.find("s1", "u1"), cfg)
    check("C#24 replay воспроизводит band детерминированно", rp["band"] == "especially_close")
    check("C#24 версия конфига совпадает", rp["version_match"] is True)
    # другой конфиг-версии -> version_match False
    rp2 = OB.replay(log.find("s1", "u1"), dict(cfg, config_version="matching-core-9.9.9",
                                               user_facing_bands=cfg["user_facing_bands"]))
    check("OB3 иная версия конфига -> version_match False", rp2["version_match"] is False)

    print("\n§21 observability: %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
