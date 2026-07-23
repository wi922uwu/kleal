# -*- coding: utf-8 -*-
"""§16 events/rooms/venues — separate types, C#20 (different transactions/copy)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.retrieval import candidate_types as CT

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def run():
    ev = CT.build_event("e1", category="games", schedule="sat", capacity={"current": 2, "max": 10}, topics=["dota2"])
    check("CT1 event НЕ user (отдельный тип)", ev["kind"] == "event")
    check("CT2 event eligibility ALLOW", CT.event_eligibility({}, ev)[0] == "ALLOW")
    full = CT.build_event("e2", category="games", schedule="sat", capacity={"current": 10, "max": 10})
    check("CT3 полное событие -> BLOCK", CT.event_eligibility({}, full)[0] == "BLOCK")
    check("CT4 user→event relevance (не reciprocal)", CT.user_event_relevance({"topics": ["dota2"]}, ev) == 1.0)

    room = CT.build_room("r1", platform="discord", topic="dota2", live_capacity={"current": 3, "max": 8})
    check("CT5 room session relevance", CT.session_relevance({"topics": ["dota2"]}, room) == 1.0)
    venue = CT.build_venue("v1", availability="eve", price_band="low", noise="quiet", distance_km=1.0)
    check("CT6 venue plan suitability (близко/тихо)", CT.plan_suitability({}, venue) == 1.0)
    loud_far = CT.build_venue("v2", availability="eve", price_band="low", noise="loud", distance_km=20)
    check("CT7 venue далеко+шумно -> ниже", CT.plan_suitability({}, loud_far) < 0.5)

    # C#20: разные transaction + explanation copy у user vs event
    tu, te = CT.candidate_transaction("user"), CT.candidate_transaction("event")
    check("C#20 user/event разные transaction", tu["transaction"] != te["transaction"])
    check("C#20 user/event разные explanation copy", tu["explain_key"] != te["explain_key"])
    check("C#20 event помечен как альтернатива", "alternative" in te["explain_key"])
    check("CT8 все 5 типов кандидатов", set(CT.CANDIDATE_KINDS) == {"user", "ad_hoc_group", "event", "online_room", "venue"})

    print("\n§16 candidate types: %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
