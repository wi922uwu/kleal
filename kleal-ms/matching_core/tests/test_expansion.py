# -*- coding: utf-8 -*-
"""§12 controlled expansion — одна ось/шаг, forbidden оси, consent-gating (§23.3)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.orchestrator import expansion as EX

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def run():
    # forbidden оси НИКОГДА не расширяются
    for ax in ("safety", "age", "mutual_consent", "block", "critical_language", "purpose_isolation"):
        if not check("EX forbidden %s -> not allowed" % ax, not EX.allowed({}, ax)):
            break

    # sibling разрешён без consent
    check("EX1 sibling allowed без consent", EX.allowed({}, "sibling"))
    # parent требует broad_consent
    check("EX2 parent без consent -> not allowed", not EX.allowed({}, "parent"))
    check("EX3 parent с broad_consent -> allowed",
          EX.allowed({"fallback": {"consent": {"broad_matching": True}}}, "parent"))

    # один шаг ослабляет одну ось + сохраняет provenance
    step = EX.expand_step({"mode": "offline", "radiusKm": 10}, 1)   # sibling
    check("EX4 шаг возвращает axis+intent+explanation", step and step["axis"] == "sibling" and "intent" in step)
    check("EX5 sibling -> adjacentAllowed", step["intent"].get("adjacentAllowed") is True)

    # parent без consent -> discovery_only (не в inbox), §12.1
    pstep = EX.expand_step({"mode": "offline"}, 2)   # parent, без consent
    check("EX6 parent без consent -> discovery_only", pstep is None or pstep["discovery_only"])

    # time_distance требует fallback consent
    it_fb = {"radiusKm": 10, "fallback": {"allowed_dimensions": ["time", "distance"]}}
    tstep = EX.expand_step(it_fb, 3)
    check("EX7 time_distance c fallback consent -> расширяет радиус", tstep and tstep["intent"]["radiusKm"] > 10)

    # format: offline -> online
    fstep = EX.expand_step({"mode": "offline", "fallback": {"allowed_dimensions": ["format"]}}, 4)
    check("EX8 format: offline -> online", fstep and fstep["intent"]["mode"] == "online")

    # лестница из 7 шагов в правильном порядке
    axes = [a for a, _, _ in EX.EXPANSION_LADDER]
    check("EX9 порядок лестницы (§12.2)",
          axes == ["exact", "sibling", "parent", "time_distance", "format", "alternative_type", "saved_search"])

    # expand_until_useful: останавливается, когда есть результат
    calls = {"n": 0}
    def has_results(it):
        calls["n"] += 1
        return calls["n"] >= 2                       # результат после 2-го шага
    cur, trail = EX.expand_until_useful({"mode": "offline", "radiusKm": 5}, has_results, max_steps=5)
    check("EX10 expand_until_useful остановился на полезном", len(trail) >= 1 and len(trail) <= 5)

    print("\n§12 expansion: %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
