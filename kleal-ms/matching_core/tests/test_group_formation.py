# -*- coding: utf-8 -*-
"""§15 group formation — set constraints, least_misery, former (C#18/#19; §23.2 п.8)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.group_formation import constraints as GC, utility as GU, former as GF

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def _m(mid, side=None, roles=None, langs=None, skill=None, bucket=None, win="18:00-22:00"):
    a, b = win.split("-")
    return {"id": mid, "side": side, "roles": roles or ([side] if side else []),
            "langs": langs or ["en"], "skill": skill, "bucket": bucket or mid,
            "time_windows": [[a, b]]}


def matrix_rel(mat, default=0.7):
    def f(a, b):
        return mat.get((a["id"], b["id"]), default)
    return f


def run():
    # --- set constraints ---
    padel = {"size_min": 4, "size_max": 4, "role_distribution": {"left": 2, "right": 2}, "min_common_window_min": 60}
    good4 = [_m("a", "left"), _m("b", "left"), _m("c", "right"), _m("d", "right")]
    ok, viol = GC.check_set_constraints(good4, padel)
    check("GC1 корректный padel (2 left/2 right) feasible", ok and viol == [])

    # C#18: 4 одинаковых side отклоняются даже при высоких pair scores
    bad4 = [_m("a", "left"), _m("b", "left"), _m("c", "left"), _m("d", "left")]
    ok2, viol2 = GC.check_set_constraints(bad4, padel)
    check("C#18 4 одинаковых side отклонены", (not ok2) and any("role_distribution" in x for x in viol2))

    # C#19: pairwise block отклоняет группу
    ok3, viol3 = GC.check_set_constraints(good4, dict(padel, pair_blocks=[("a", "c")]))
    check("C#19 pairwise block отклоняет", (not ok3) and "pairwise_block" in viol3)

    # time overlap: нет пересечения -> insufficient
    no_overlap = [_m("a", "left", win="08:00-09:00"), _m("b", "left", win="20:00-21:00"),
                  _m("c", "right", win="08:00-09:00"), _m("d", "right", win="20:00-21:00")]
    ok4, viol4 = GC.check_set_constraints(no_overlap, padel)
    check("GC2 нет time overlap -> insufficient_time_overlap", "insufficient_time_overlap" in viol4)

    # --- §15.2 least_misery: группа с одним плохим участником НЕ выигрывает по среднему ---
    cons3 = {"size_min": 3, "size_max": 3}
    g_bad = [_m("a"), _m("b"), _m("x")]     # x плохо совместим со всеми
    g_even = [_m("p"), _m("q"), _m("r")]    # все средне
    rel_bad = matrix_rel({("a", "b"): 0.9, ("b", "a"): 0.9, ("a", "x"): 0.2, ("x", "a"): 0.2,
                          ("b", "x"): 0.2, ("x", "b"): 0.2}, default=0.2)
    rel_even = matrix_rel({}, default=0.6)
    u_bad = GU.group_utility(g_bad, rel_bad, cons3)
    u_even = GU.group_utility(g_even, rel_even, cons3)
    lm_bad = GU.least_misery(g_bad, rel_bad)
    check("GU1 least_misery(bad) низкий", lm_bad == 0.2)
    check("§23.2 п.8: ровная группа (least_misery) > группы с плохим участником", u_even > u_bad)
    check("GU2 infeasible -> None", GU.group_utility([_m("a")], rel_even, cons3) is None)

    # --- former (B.3): формирует допустимую группу ---
    pool = [_m("a", "left"), _m("b", "left"), _m("c", "right"), _m("d", "right"), _m("e", "left")]
    res = GF.form_group({}, pool, padel, matrix_rel({}, default=0.8))
    check("GF1 сформирована допустимая группа", res is not None and len(res["members"]) == 4)
    check("GF2 у группы есть utility и reservations", res["utility"] is not None and len(res["reservations"]) == 4)
    check("GF3 группа проходит set constraints", GC.check_set_constraints(res["group"], padel)[0])

    # C#18 на уровне former: пул только из left -> допустимой группы нет
    only_left = [_m("a", "left"), _m("b", "left"), _m("c", "left"), _m("d", "left")]
    check("C#18 former: пул из одних left -> None", GF.form_group({}, only_left, padel, matrix_rel({}, default=0.9)) is None)

    # C#19 на уровне former: все пары заблокированы -> None
    blocked_cons = {"size_min": 3, "size_max": 3, "pair_blocks": [("a", "b"), ("a", "c"), ("b", "c")]}
    trio = [_m("a"), _m("b"), _m("c")]
    check("C#19 former: все пары заблокированы -> None", GF.form_group({}, trio, blocked_cons, matrix_rel({}, default=0.9)) is None)

    print("\n§15 group formation: %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
