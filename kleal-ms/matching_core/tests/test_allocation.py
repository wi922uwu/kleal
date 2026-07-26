# -*- coding: utf-8 -*-
"""§11 allocation — rerank order, diversity, exposure/cooldown, C#11 monetization (§23.3)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.allocation import allocation as AL

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def item(name, rec, readiness="open_now", bucket="b", lcb=0.8, cov=0.7, policy="ALLOW"):
    return {"cand": {"name": name}, "reciprocal": rec, "readiness": readiness, "bucket": bucket,
            "lcb": lcb, "coverage": cov, "policy": policy, "tier": "T1"}


def run():
    # (1) BLOCK убирается; порядок по reciprocal
    items = [item("a", 0.5), item("b", 0.9), item("c", 0.7, policy="BLOCK")]
    slate = AL.rerank(items, {}, ctx={})
    names = [s["cand"]["name"] for s in slate]
    check("AL1 BLOCK убран", "c" not in names)
    check("AL2 порядок по reciprocal (b раньше a)", names.index("b") < names.index("a"))
    check("AL3 propensity убывает по позиции", slate[0]["allocation"]["propensity"] >= slate[-1]["allocation"]["propensity"])

    # readiness class — ordering: busy позже open_now при равном reciprocal
    it2 = [item("x", 0.8, readiness="busy"), item("y", 0.8, readiness="open_now")]
    s2 = AL.rerank(it2, {}, ctx={})
    check("AL4 readiness class: open_now раньше busy", s2[0]["cand"]["name"] == "y")

    # diversity: >2 бакета -> не более 3 из одного
    many = [item("n%d" % i, 0.9 - i * 0.01, bucket="hot") for i in range(6)] + \
           [item("m1", 0.5, bucket="b2"), item("m2", 0.5, bucket="b3")]
    s3 = AL.rerank(many, {}, ctx={})
    hot = [s for s in s3 if s["bucket"] == "hot"]
    check("AL5 diversity: <=3 из бакета hot", len(hot) <= AL.PER_BUCKET)

    # exposure cap убирает переэкспонированных
    s4 = AL.rerank([item("a", 0.9), item("b", 0.8)], {}, ctx={"exposure": {"a": 99}, "exposure_cap": 50})
    check("AL6 exposure cap убрал 'a'", "a" not in [s["cand"]["name"] for s in s4])

    # cooldown убирает пару
    s5 = AL.rerank([item("a", 0.9), item("b", 0.8)], {}, ctx={"cooldown_pairs": {"a"}})
    check("AL7 cooldown убрал 'a'", "a" not in [s["cand"]["name"] for s in s5])

    # C#11 monetization: payment feature в allocation -> MonetizationViolation
    bad = item("z", 0.9); bad["_allocation_features"] = {"payment_status": "paid"}
    try:
        AL.rerank([bad], {}, ctx={}); check("C#11 payment feature -> raise", False)
    except AL.MonetizationViolation:
        check("C#11 payment feature в allocation -> MonetizationViolation (§11.3)", True)

    # exploration слот для нового кандидата (нулевая экспозиция)
    s6 = AL.rerank([item("hot1", 0.9, bucket="B"), item("newbie", 0.4, bucket="B", cov=0.5)], {},
                   ctx={"exposure": {"hot1": 5}})
    check("AL8 exploration включает нового кандидата", any(s.get("exploration") for s in s6) or "newbie" in [x["cand"]["name"] for x in s6])

    print("\n§11 allocation: %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
