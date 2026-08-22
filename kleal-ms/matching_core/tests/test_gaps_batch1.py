# -*- coding: utf-8 -*-
"""Закрытие partial/absent — Батч 1: §9.5 CI, §14.2 TTL, §11.1 allocation, §7.1/§7.2."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.config import validator as V
from matching_core.orchestrator import concurrency as CC
from matching_core.allocation import allocation as AL
from matching_core.retrieval import retriever as RT

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def item(name, rec=0.8, tier="T1", source=1, bucket="b", cov=0.7, policy="ALLOW", resource=None):
    return {"cand": {"name": name}, "reciprocal": rec, "readiness": "open_now", "tier": tier,
            "source": source, "bucket": bucket, "lcb": 0.7, "coverage": cov, "policy": policy, "resource": resource}


def run():
    cfg = V.load_config()

    # ---- §9.5 CI: version compat + evidence_id uniqueness ----
    ok, pr = V.check_version_compat(cfg, policy_version="pol-2.0.0", model_version="ic-2.1")
    check("B1.1 version compat: major совпал -> ok", ok and pr == [])
    bad, pr2 = V.check_version_compat(cfg, policy_version="pol-9.0.0")
    check("B1.2 version compat: major разошёлся -> problem", (not bad) and pr2)
    u, dups = V.check_evidence_id_uniqueness({"semantic_activity": ["ev_1"], "time_feasibility": ["ev_1"]})
    check("B1.3 evidence_id в 2 группах -> duplicate (double-count guard)", (not u) and len(dups) == 1)
    u2, _ = V.check_evidence_id_uniqueness({"semantic_activity": ["ev_1"], "time_feasibility": ["ev_2"]})
    check("B1.4 разные evidence_id -> ok", u2)

    # ---- §14.2 CapacityLedger TTL + auto-release ----
    cl = CC.CapacityLedger()
    ok1, _ = cl.claim_slot("g1", 1, now=0.0, ttl_sec=10)
    check("B1.5 первый claim ok", ok1)
    ok2, _ = cl.claim_slot("g1", 1, now=5.0, ttl_sec=10)
    check("B1.6 второй claim пока держится -> отказ", not ok2)
    ok3, _ = cl.claim_slot("g1", 1, now=11.0, ttl_sec=10)      # первый истёк -> авто-release
    check("B1.7 после TTL авто-release -> claim снова ok", ok3)
    check("B1.8 in_use учитывает TTL", cl.in_use("g1", now=11.0) == 1)

    # ---- §11.1 allocation: reservation-capacity ----
    s = AL.rerank([item("a", resource="grp:full"), item("b")], {}, ctx={"reservation_full": {"grp:full"}})
    check("B1.9 reservation full убирает кандидата", "a" not in [x["cand"]["name"] for x in s])

    # 3-осевая diversity: tier cap (PER_TIER=4) ограничивает много одинаковых tier
    many_t2 = [item("t%d" % i, rec=0.9 - i * 0.01, tier="T2", bucket="b%d" % i) for i in range(6)]
    st = AL.rerank(many_t2, {}, ctx={})
    check("B1.10 tier cap (<=%d T2)" % AL.PER_TIER, sum(1 for x in st if x["tier"] == "T2") <= AL.PER_TIER)

    # area supply balancing
    area_items = [item("u%d" % i, rec=0.9 - i * 0.01, bucket="b%d" % i) for i in range(6)]
    sa = AL.rerank(area_items, {}, ctx={"area_of": {"u%d" % i: "Eixample" for i in range(6)}, "area_cap": 2})
    check("B1.11 area cap (<=2 из зоны)", len(sa) <= 2)

    # exploration quota (до 2)
    hot = [item("hot%d" % i, rec=0.9 - i * 0.01, bucket="B", cov=0.8) for i in range(2)]
    new = [item("new%d" % i, rec=0.3, bucket="B", cov=0.5) for i in range(3)]
    se = AL.rerank(hot + new, {}, ctx={"exposure": {"hot0": 5, "hot1": 5}})
    check("B1.12 exploration quota <= 2", sum(1 for x in se if x.get("allocation", {}).get("exploration")) <= AL.EXPLORATION_QUOTA)

    # ---- §7.2 явный funnel + §7.1 per-tier analytics ----
    pool = [{"name": "d", "interests": ["dota2"], "intents": [{"topics": ["dota2"]}]},
            {"name": "p", "interests": ["chess"]}, {"name": "x", "interests": ["spanish"]}]  # spanish=learning, не смежен games -> T5
    labeled, stats = RT.retrieve_staged({"topics": ["dota2"]}, pool, budget=10)
    check("B1.13 funnel stats: стадии присутствуют", stats["hard_prefilter"] == 3 and stats["ann_recall"]["status"] == "no_op_stdlib")
    check("B1.14 T5 (no-overlap) отфильтрован structured", stats["structured_retrieval"] == 2)
    ta = RT.tier_analytics([{"tier": "T0", "lcb": 0.8, "coverage": 0.7}, {"tier": "T0", "lcb": 0.6, "coverage": 0.5},
                            {"tier": "T2", "lcb": 0.4, "coverage": 0.4}])
    check("B1.15 per-tier analytics агрегирует", ta["T0"]["count"] == 2 and ta["T0"]["mean_lcb"] == 0.7 and ta["T2"]["count"] == 1)

    print("\nБатч 1 (partial-closure): %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
