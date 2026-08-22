# -*- coding: utf-8 -*-
"""§5 intent compiler + clarification — §5.1 hard/soft, §5.2 P0-P3 (§23.3)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.intent_compiler import compiler as IC, clarification as CL

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def run():
    # --- compile: normalize + allowlists ---
    out = IC.compile_intent({"topics": ["Dota 2", "MOBA"], "type": "games", "mode": "weird",
                             "format": "1:1", "requiredLanguages": ["English"], "city": "Barcelona",
                             "time": [["20:00", "23:00"]], "radiusKm": 10},
                            intent_id="i1", user_id="u1", created_at=0.0, ttl_sec=3600)
    check("IC1 topics lowercased", out["flat"]["topics"] == ["dota 2", "moba"])
    check("IC2 недопустимый mode -> offline (allowlist)", out["flat"]["mode"] == "offline")
    check("IC3 requiredLanguages нормализованы", out["intent"]["domain_details"]["requiredLanguages"] == ["en"])
    check("IC4 TTL проставлен", out["intent"]["lifecycle"]["expires_at"] == 3600.0)
    # §5.1 hard/soft + подтверждение
    check("IC5 requiredLanguages -> hard + needs_confirm (§5.1)",
          "requiredLanguages" in out["hard"] and "requiredLanguages" in out["needs_confirmation"])
    soft = IC.compile_intent({"topics": ["coffee"], "type": "social_meet", "location_preference": "soft",
                              "mode": "online"}, intent_id="i2", user_id="u1", created_at=0.0, ttl_sec=10)
    check("IC6 'желательно рядом' -> soft location", "location" in soft["soft"])
    check("IC7 online -> soft fallback", "mode_online_fallback" in soft["soft"])
    check("IC8 confidence 0..1", 0.0 <= out["confidence"] <= 1.0)

    # --- §5.2 clarification ---
    check("CL1 dating_optin = P0", CL.classify("dating_optin")["klass"] == "P0")
    check("CL2 time_window = P1", CL.classify("time_window")["klass"] == "P1")
    check("CL3 exact_topic = P2", CL.classify("exact_topic")["klass"] == "P2")
    # mandatory P0 выбирается даже среди P1 (safety не подчиняется лимиту одного вопроса)
    sel = CL.select_question(["time_window", "dating_optin", "area"])
    check("CL4 P0 mandatory выбран поверх P1", sel["key"] == "dating_optin" and sel["klass"] == "P0")
    # только P1 среди missing -> берём лучший P1 по приоритету
    sel2 = CL.select_question(["time_window", "area", "format_1to1_group"])
    check("CL5 лучший P1 по приоритету", sel2 and sel2["klass"] == "P1")
    # P2/P3 не спрашиваем до результатов
    sel3 = CL.select_question(["exact_topic", "card_name"], before_results=True)
    check("CL6 P2/P3 не до результатов (§5.2)", sel3 is None)
    # action on refusal
    check("CL7 P1 refusal = search unknown", CL.classify("time_window")["action_on_refusal"] == "search_with_unknown_lower_confidence")
    check("CL8 P0 refusal = block sensitive", CL.classify("dating_optin")["action_on_refusal"] == "block_sensitive_flow_offer_safe_alternative")

    print("\n§5 intent compiler: %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
