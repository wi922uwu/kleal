# -*- coding: utf-8 -*-
"""§8 policy engine — unit + safety/privacy tests (§23.3 DoD; C#5/#6)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.policy_engine import engine as PE, gates as G, revalidation as REV

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


CLEAN = {"name": "b", "age": 30, "verified": True, "langs": ["en", "es"], "km": 3.0, "open": True}
SOCIAL = {"type": "social_meet", "mode": "offline", "time": {}, "topics": ["coffee"]}


def run():
    ctx = {"blocked": set(), "received24": {}}

    # --- отдельные gates ---
    check("G1 account suspended -> BLOCK", G.account_status(SOCIAL, {"suspended": True}, ctx)[0] == G.BLOCK)
    check("G2 mutual block -> BLOCK", G.mutual_block(SOCIAL, {"name": "b", "blocksMe": True}, ctx)[0] == G.BLOCK)
    check("G3 safety hard -> BLOCK", G.safety_restrictions(SOCIAL, {"safetyFlags": ["legal_hold"]}, ctx)[0] == G.BLOCK)
    check("G4 safety soft -> REVIEW", G.safety_restrictions(SOCIAL, {"safetyFlags": ["review"]}, ctx)[0] == G.REVIEW)
    check("G5 private -> BLOCK", G.privacy_visibility(SOCIAL, {"visibility": "private"}, ctx)[0] == G.BLOCK)
    check("G6 under 18 -> BLOCK", G.age_legal(SOCIAL, {"age": 16}, ctx)[0] == G.BLOCK)
    check("G7 dating age unknown -> BLOCK", G.age_legal({"type": "dating"}, {"age": None}, ctx)[0] == G.BLOCK)
    check("G8 dating not open -> BLOCK", G.intent_mode_isolation({"type": "dating"}, {"datingOk": False}, ctx)[0] == G.BLOCK)
    check("G9 missing language -> BLOCK",
          G.language_feasibility({"requiredLanguages": ["ru"]}, {"langs": ["en"]}, ctx)[0] == G.BLOCK)
    check("G10 outside radius -> BLOCK",
          G.location_policy({"mode": "offline", "radiusKm": 5, "type": "x"}, {"km": 20}, ctx)[0] == G.BLOCK)
    check("G11 outside radius + zoneOptIn -> REVIEW",
          G.location_policy({"mode": "offline", "radiusKm": 5, "zoneOptIn": True}, {"km": 20}, ctx)[0] == G.REVIEW)
    check("G12 time slot conflict -> BLOCK",
          G.time_feasibility({"time": {"windows": [["20:00", "22:00"]]}}, {"open": False}, ctx)[0] == G.BLOCK)

    # --- evaluate: агрегация tri-state ---
    v_ok = PE.evaluate(SOCIAL, CLEAN, ctx)
    check("PE1 чистый кандидат -> ALLOW", v_ok["decision"] == PE.ALLOW and PE.is_scorable(v_ok))

    # C#5: safety block исключает ДО feature building -> decision BLOCK, гейт = safety, дальше не идём
    v_block = PE.evaluate(SOCIAL, dict(CLEAN, safetyFlags=["banned"]), ctx)
    check("C#5 safety block -> BLOCK до скоринга", v_block["decision"] == PE.BLOCK and not PE.is_scorable(v_block))
    check("C#5 BLOCK -> не discoverable", not PE.is_discoverable(v_block))

    # REVIEW: dating release_gate + unverified -> REVIEW (discoverable, не scorable)
    v_rev = PE.evaluate({"type": "dating", "datingOk": True, "age": 30},
                        dict(CLEAN, verified=False, datingOk=True),
                        dict(ctx, domain_cfg={"release_gate": "separate_safety_legal_track"}))
    check("PE2 dating unverified -> REVIEW", v_rev["decision"] == PE.REVIEW)
    check("PE3 REVIEW discoverable, не scorable", PE.is_discoverable(v_rev) and not PE.is_scorable(v_rev))

    # --- §8.2 revalidation (C#6): privacy изменилась между SENT и ACCEPT -> POLICY_CHANGED ---
    baseline = REV.capture_baseline(CLEAN, {"version": 1})
    same = REV.revalidate(baseline, CLEAN, {"version": 1}, ctx, "on_accept")
    check("REV1 без изменений -> OK", same["ok"] and same["code"] == "OK")
    changed = REV.revalidate(baseline, dict(CLEAN, visibility="private"), {"version": 1}, ctx, "before_chat")
    check("C#6 privacy changed -> POLICY_CHANGED", changed["code"] == "POLICY_CHANGED" and "visibility" in changed["changed"])
    ver = REV.revalidate(baseline, CLEAN, {"version": 2}, ctx, "on_accept")
    check("REV2 intent version bump -> POLICY_CHANGED", ver["code"] == "POLICY_CHANGED")
    try:
        REV.revalidate(baseline, CLEAN, {"version": 1}, ctx, "bogus_checkpoint")
        check("REV3 неизвестный checkpoint -> raise", False)
    except ValueError:
        check("REV3 неизвестный checkpoint -> raise", True)

    print("\n§8 policy: %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
