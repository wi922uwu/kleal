# -*- coding: utf-8 -*-
"""§6.1/§9.1 feature builder — 7 групп, 4 состояния, C#2/#3 (§23.3)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.feature_builder import builder as FB

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def run():
    prof = {"vibe": "chill", "interests": ["dota2"], "coarse_lat": 41.4, "coarse_lon": 2.1}
    cand = {"interests": ["dota", "lol"], "vibe": "chill", "open": True, "km": 2.0, "role": "carry"}

    F = FB.build_features({"topics": ["dota2"], "mode": "offline", "time": {"windows": [["20:00", "22:00"]]},
                           "role": "support"}, prof, cand, "games")
    # 7 групп присутствуют
    check("FB1 семь групп", set(F.keys()) == set(FB.FEATURE_KEYS))
    # C#3: semantic_activity — ОДНА агрегированная величина (alias dota + sibling lol не дают 2 бонуса)
    st, val, _ = F["semantic_activity"]
    check("C#3 semantic_activity одна величина (exact=1.0, не сумма)", st == FB.K_MATCH and val == 1.0)
    # unknown ≠ match: пустые интересы -> unknown
    Fu = FB.build_features({"topics": ["dota2"], "mode": "offline"}, prof, {"interests": []}, "games")
    check("FB2 нет интересов -> unknown (≠ match)", Fu["semantic_activity"][0] == FB.UNKNOWN)
    # C#2: online -> location not_applicable
    Fo = FB.build_features({"topics": ["dota2"], "mode": "online"}, prof, cand, "games")
    check("C#2 online -> location not_applicable", Fo["location_feasibility"][0] == FB.NA)
    # time: open=True -> known_match
    check("FB3 open -> time known_match", F["time_feasibility"][0] == FB.K_MATCH)
    # directed_preferences: support↔carry complementary -> match
    check("FB4 complementary role -> match", F["directed_preferences"][0] == FB.K_MATCH)
    # role=meet -> not_applicable
    Fm = FB.build_features({"topics": ["dota2"], "mode": "offline", "role": "meet"}, prof, cand, "games")
    check("FB5 role=meet -> directed_preferences NA", Fm["directed_preferences"][0] == FB.NA)
    # vibe clash -> known_mismatch
    Fv = FB.build_features({"topics": ["dota2"], "mode": "offline"}, {"vibe": "party", "interests": ["x"]},
                           dict(cand, vibe="chill"), "games")
    check("FB6 vibe clash -> known_mismatch", Fv["social_context"][0] == FB.K_MISM)
    # geo band: 2км -> высокое значение (known_match)
    check("FB7 близко -> location known_match", F["location_feasibility"][0] == FB.K_MATCH)

    print("\n§6.1 feature builder: %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
