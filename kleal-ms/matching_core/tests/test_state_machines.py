# -*- coding: utf-8 -*-
"""§14 state machines + orchestrator — transition/race/idempotency tests (§23.3; C#6/#7/#8/#9/#10)."""
import os
import sys
import threading

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.orchestrator import state_machines as SM, transitions as TR, concurrency as CC
from matching_core.policy_engine import revalidation as REV

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


CAND = {"name": "b", "age": 30, "verified": True, "langs": ["en"], "km": 2.0, "open": True}
INTENT = {"type": "social_meet", "mode": "offline", "time": {}, "version": 1}


def _prop(pid, status="SENT", expires_at=1000.0):
    return {"proposal_id": pid, "from": "a", "to": "b", "status": status,
            "expires_at": expires_at, "version": 1}


def run():
    # --- state machine transitions ---
    check("SM1 valid proposal SENT->ACCEPTED", SM.can_transition("proposal", "SENT", "ACCEPTED"))
    check("SM2 invalid EXPIRED->ACCEPTED", not SM.can_transition("proposal", "EXPIRED", "ACCEPTED"))
    check("SM3 terminal COMPLETED", SM.is_terminal("match", "COMPLETED"))
    try:
        SM.assert_transition("proposal", "WITHDRAWN", "ACCEPTED"); check("SM4 withdrawn->accept raises", False)
    except SM.InvalidTransition:
        check("SM4 withdrawn->accept raises (C#10)", True)
    check("SM5 idempotent frm==to", SM.assert_transition("match", "MUTUAL", "MUTUAL"))
    check("SM6 all machines terminal-closed",
          all(SM.is_terminal(m, s) for m in SM.MACHINES for s in SM.MACHINES[m] if not SM.MACHINES[m][s]))

    ctx = {"blocked": set(), "received24": {}}
    baseline = REV.capture_baseline(CAND, INTENT)

    # --- happy path accept (B.2) ---
    orc = TR.Orchestrator()
    orc.register_proposal(_prop("p1"))
    r = orc.accept_proposal("p1", "b", "idem-1", candidate=CAND, intent=INTENT, baseline=baseline, ctx=ctx, now=10)
    check("AC1 accept -> ACCEPTED + match", r["ok"] and r["code"] == "ACCEPTED" and r["match"]["status"] == "MUTUAL")
    check("AC2 outbox событие опубликовано", len(orc.outbox.events) == 1)
    check("AC3 proposal стал ACCEPTED (CAS)", orc.proposals.get("p1")["status"] == "ACCEPTED")

    # --- C#7 idempotency: повтор с тем же ключом -> тот же результат, без второго события ---
    r2 = orc.accept_proposal("p1", "b", "idem-1", candidate=CAND, intent=INTENT, baseline=baseline, ctx=ctx, now=10)
    check("C#7 повтор idem -> тот же результат", r2 == r and len(orc.outbox.events) == 1)

    # --- C#9 expired нельзя принять ---
    orc.register_proposal(_prop("p2", expires_at=100.0))
    rexp = orc.accept_proposal("p2", "b", "idem-2", candidate=CAND, intent=INTENT, baseline=baseline, ctx=ctx, now=200)
    check("C#9 expired -> EXPIRED", (not rexp["ok"]) and rexp["code"] == "EXPIRED")

    # --- C#10 counter/withdrawn после -> INVALID_TRANSITION ---
    orc.register_proposal(_prop("p3", status="WITHDRAWN"))
    rwd = orc.accept_proposal("p3", "b", "idem-3", candidate=CAND, intent=INTENT, baseline=baseline, ctx=ctx, now=10)
    check("C#10 accept withdrawn -> INVALID_TRANSITION", rwd["code"] == "INVALID_TRANSITION")

    # --- C#6 policy changed на accept ---
    orc.register_proposal(_prop("p4"))
    rpc = orc.accept_proposal("p4", "b", "idem-4", candidate=dict(CAND, visibility="private"),
                              intent=INTENT, baseline=baseline, ctx=ctx, now=10)
    check("C#6 privacy changed -> POLICY_CHANGED", rpc["code"] == "POLICY_CHANGED")

    # --- C#8 два concurrent accept последнего слота (capacity=1) через реальные потоки ---
    orc2 = TR.Orchestrator()
    orc2.register_proposal(_prop("g1"))
    orc2.register_proposal(_prop("g2"))
    results = {}

    def worker(pid, key):
        results[pid] = orc2.accept_proposal(pid, "b", key, candidate=CAND, intent=INTENT, baseline=baseline,
                                            ctx=ctx, now=10, resource="group:slot", capacity_max=1)

    t1 = threading.Thread(target=worker, args=("g1", "k1"))
    t2 = threading.Thread(target=worker, args=("g2", "k2"))
    t1.start(); t2.start(); t1.join(); t2.join()
    oks = [pid for pid, r in results.items() if r["ok"]]
    caps = [pid for pid, r in results.items() if r["code"] == "CAPACITY_EXCEEDED"]
    check("C#8 ровно один accept последнего слота", len(oks) == 1 and len(caps) == 1)

    # --- unique pair / CAS conflict ---
    reg = CC.UniquePairRegistry()
    check("UP1 первый claim ok", reg.claim("a", "b", "friendship"))
    check("UP2 дубль пары отклонён (§14.4)", not reg.claim("b", "a", "friendship"))
    vs = CC.VersionedStore(); vs.put("x", {"version": 1, "s": "A"})
    try:
        vs.compare_and_swap("x", 5, {"s": "B"}); check("CAS1 неверная версия -> conflict", False)
    except CC.VersionConflict:
        check("CAS1 неверная версия -> VersionConflict", True)

    # --- resolve_race детерминированные коды ---
    check("RC1 privacy race -> POLICY_CHANGED", TR.resolve_race("privacy_changed_before_accept")["code"] == "POLICY_CHANGED")
    check("RC2 last slot -> CAPACITY_EXCEEDED", TR.resolve_race("both_took_last_slot")["code"] == "CAPACITY_EXCEEDED")
    check("RC3 duplicate pair -> DUPLICATE_PAIR", TR.resolve_race("two_waves_duplicate_pair")["code"] == "DUPLICATE_PAIR")
    check("RC4 все 8 гонок покрыты", len(TR.RACE_CODES) == 8)

    print("\n§14 state machines: %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
