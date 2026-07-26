# -*- coding: utf-8 -*-
"""§7 retrieval + semantic tiers — C#4 (tier immutable, не из логистики) (§23.3)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.retrieval import retriever as RT

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def run():
    intent = {"topics": ["dota2"], "mode": "offline"}
    direct = {"name": "d", "interests": ["dota"], "open": True}                       # exact -> T1
    reciprocal = {"name": "r", "interests": ["dota2"], "intents": [{"topics": ["dota2"]}]}  # T0
    parent = {"name": "p", "interests": ["chess"]}                                    # parent(games) -> T2
    adjacent = {"name": "a", "interests": ["labubu"]}                                 # none -> T5 (не показ)
    event = {"name": "e", "kind": "room", "interests": ["dota2"]}                     # T4

    check("RT1 reciprocal exact -> T0", RT.assign_tier(intent, reciprocal) == "T0")
    check("RT2 direct interest -> T1", RT.assign_tier(intent, direct) == "T1")
    check("RT3 parent category -> T2", RT.assign_tier(intent, parent) == "T2")
    check("RT4 event/room -> T4", RT.assign_tier(intent, event) == "T4")
    check("RT5 no overlap -> T5", RT.assign_tier(intent, adjacent) == "T5")

    # C#4: T2 кандидат НЕ становится T1 из-за хорошего времени/логистики (tier — provenance, не score)
    parent_good_time = dict(parent, open=True, km=0.1)
    check("C#4 T2 не -> T1 из-за времени/близости", RT.assign_tier(intent, parent_good_time) == "T2")

    # retrieve: T5 не входит; порядок по приоритету источника; бюджет режет хвост
    pool = [adjacent, parent, direct, reciprocal, event]
    got = RT.retrieve(intent, pool, budget=10)
    tiers = [g["tier"] for g in got]
    names = [g["cand"]["name"] for g in got]
    check("RT6 T5 не в выдаче", "T5" not in tiers and "a" not in names)
    check("RT7 порядок: T0/T1 источники раньше", names[0] in ("r", "d"))
    check("RT8 tier immutable в результате", all("tier" in g for g in got))
    # budget cap
    small = RT.retrieve(intent, pool, budget=1)
    check("RT9 budget=1 режет до 1", len(small) == 1)
    # tier UX / outreach права
    check("RT10 T0/T1 personal outreach, T3/T4 нет",
          RT.TIER_UX["T0"][1] is True and RT.TIER_UX["T3"][1] is False and RT.TIER_UX["T2"][1] == "broad_consent")

    print("\n§7 retrieval: %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
