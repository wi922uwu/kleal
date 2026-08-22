# -*- coding: utf-8 -*-
"""§13 agent protocol — typed actions, envelope, waves, autonomy (§23.3)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.orchestrator import protocol as PR

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def run():
    # §13.1 замкнутый набор действий
    check("PR1 9 разрешённых действий", len(PR.ALLOWED_ACTIONS) == 9 and "PROPOSE_CONNECTION" in PR.ALLOWED_ACTIONS)
    env = PR.build_envelope("PROPOSE_CONNECTION", proposal_id="p1", idempotency_key="k1",
                            intent_version=7, profile_version=3, policy_version="pol-2.0.0",
                            purpose="friendship.walk", disclosure_scope="limited")
    check("PR2 envelope содержит версии+purpose+ttl+rendering", env["versions"]["intent"] == 7
          and env["purpose"] == "friendship.walk" and env["ttl_sec"] and env["rendering_key"])
    check("PR3 свободный текст запрещён (только structured_fields)", "free_text" not in env and "message" not in env)
    try:
        PR.build_envelope("FREE_CHAT", proposal_id="p", idempotency_key="k", intent_version=1,
                          profile_version=1, policy_version="p", purpose="x", disclosure_scope="y")
        check("PR4 недопустимое действие -> raise", False)
    except PR.ProtocolViolation:
        check("PR4 недопустимое действие -> ProtocolViolation (§13.1)", True)

    # §13.2 волны
    check("PR5 wave 0 size 0", PR.WAVES[0]["size"] == 0)
    check("PR6 next_wave 0->1", PR.next_wave(0) == 1)
    check("PR7 next_wave 1->2 при отказе", PR.next_wave(1, declined_or_timeout=True) == 2)
    check("PR8 next_wave 2->3 при expansion", PR.next_wave(2, expansion_allowed=True) == 3)
    check("PR9 после 3 волн нет", PR.next_wave(3, urgent=True) is None)
    # §13.2 не более 3 одновременных personal proposals (защита от mass outreach)
    check("PR10 <=3 concurrent -> ok", PR.check_wave_limit(3))
    try:
        PR.check_wave_limit(50); check("PR11 mass outreach -> raise", False)
    except PR.ProtocolViolation:
        check("PR11 mass outreach (>3) -> ProtocolViolation (§13.2)", True)

    # §13.3 границы автономности
    check("PR12 can_auto compile/retrieval", PR.can_auto("compile_draft") and PR.can_auto("retrieval"))
    check("PR13 requires_consent dating_contact", PR.requires_consent("dating_contact"))
    check("PR14 requires_consent expand hard constraints", PR.requires_consent("expand_hard_constraints"))
    check("PR15 requires_consent reinterpret decline", PR.requires_consent("reinterpret_decline_as_later"))
    check("PR16 auto НЕ пересекается с consent-required", PR.AUTO_ALLOWED.isdisjoint(PR.CONSENT_REQUIRED))

    print("\n§13 protocol: %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
