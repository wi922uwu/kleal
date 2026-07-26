# -*- coding: utf-8 -*-
"""Закрытие partial — Батч 3: §4.3 interval-algebra, §8.1 hardening (time/language/privacy/unknown), §14.3."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.contracts import time_algebra as TA
from matching_core.policy_engine import gates as G
from matching_core.orchestrator import transitions as TR
from matching_core.policy_engine import revalidation as REV

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def run():
    # ---- §4.3 interval algebra ----
    ok, mins = TA.windows_overlap([["20:00", "22:00"]], [["21:00", "23:00"]], min_duration_min=30)
    check("TA1 пересечение окон (60 мин >= 30)", ok and mins == 60)
    ok2, _ = TA.windows_overlap([["08:00", "09:00"]], [["20:00", "21:00"]])
    check("TA2 нет пересечения", not ok2)
    ok3, m3 = TA.windows_overlap([["20:00", "22:00"]], [["20:30", "21:00"]], min_duration_min=90)
    check("TA3 пересечение есть, но < min_duration", (not ok3) and m3 == 30)
    # DST/tz: cand в UTC+2, локально 22:00-24:00 == 20:00-22:00 UTC -> пересекается с intent 20:00-22:00 UTC
    okz, mz = TA.windows_overlap([["20:00", "22:00"]], [["22:00", "23:59"]], a_tz=0, b_tz=120)
    check("TA4 tz/DST-нормализация даёт пересечение", okz and mz >= 100)

    # ---- §8.1 time_feasibility через interval algebra ----
    ivt = {"time": {"windows": [["20:00", "22:00"]]}}
    check("G-T1 окна пересекаются -> ALLOW",
          G.time_feasibility(ivt, {"availability": {"windows": [["21:00", "23:00"]]}}, {})[0] == G.ALLOW)
    check("G-T2 окна НЕ пересекаются -> BLOCK",
          G.time_feasibility(ivt, {"availability": {"windows": [["08:00", "09:00"]]}}, {})[0] == G.BLOCK)
    check("G-T3 fallback open=False (демо) -> BLOCK", G.time_feasibility(ivt, {"open": False}, {})[0] == G.BLOCK)

    # ---- §8.1 language level ----
    li = {"requiredLanguages": [{"code": "es", "level": "c1"}]}
    check("G-L1 уровень ниже требуемого -> BLOCK", G.language_feasibility(li, {"langs": [{"code": "es", "level": "a2"}]}, {})[0] == G.BLOCK)
    check("G-L2 достаточный уровень -> ALLOW", G.language_feasibility(li, {"langs": [{"code": "es", "level": "native"}]}, {})[0] == G.ALLOW)
    check("G-L3 нет языка -> BLOCK", G.language_feasibility(li, {"langs": [{"code": "en", "level": "c2"}]}, {})[0] == G.BLOCK)
    check("G-L4 совместимость: коды-строки без уровня", G.language_feasibility({"requiredLanguages": ["ru"]}, {"langs": ["ru", "en"]}, {})[0] == G.ALLOW)

    # ---- §8.1 privacy обе стороны + strict unknown ----
    check("G-P1 сторона искателя private -> BLOCK", G.privacy_visibility({}, {"name": "b"}, {"searcher_visibility": "private"})[0] == G.BLOCK)
    check("G-P2 strict + unknown visibility -> REVIEW", G.privacy_visibility({}, {"name": "b"}, {"strict_unknown": True})[0] == G.REVIEW)
    check("G-P3 default permissive (unknown -> ALLOW)", G.privacy_visibility({}, {"name": "b"}, {})[0] == G.ALLOW)
    check("G-A1 strict + account unknown -> REVIEW", G.account_status({}, {"name": "b"}, {"strict_unknown": True})[0] == G.REVIEW)

    # ---- §14.3 concurrent-accept differentiated ----
    orc = TR.Orchestrator()
    cand = {"name": "b", "age": 30, "verified": True, "langs": ["en"], "km": 2, "open": True}
    intent = {"type": "social_meet", "mode": "offline", "time": {}, "version": 1}
    base = REV.capture_baseline(cand, intent)
    # 1:1 fixed-time: accept одного -> прочие предложения искателя withdrawn
    orc.register_proposal({"proposal_id": "p1", "from": "a", "to": "b", "status": "SENT", "expires_at": 1e9, "version": 1})
    orc.register_proposal({"proposal_id": "p2", "from": "a", "to": "c", "status": "SENT", "expires_at": 1e9, "version": 1})
    r = orc.accept_proposal("p1", "b", "k1", candidate=cand, intent=intent, baseline=base, ctx={"blocked": set()},
                            now=10, intent_type="1to1_fixed_time")
    check("§14.3 1:1: accept -> прочие withdrawn", r["ok"] and "p2" in r["withdrawn"] and orc.proposals.get("p2")["status"] == "WITHDRAWN")

    # dating: no auto-commit без подтверждения (кандидат dating-готов: datingOk)
    dintent = {"type": "dating", "mode": "offline", "time": {}, "version": 1}
    dcand = {"name": "d", "age": 30, "verified": True, "langs": ["en"], "km": 2, "open": True, "datingOk": True}
    dbase = REV.capture_baseline(dcand, dintent)
    orc.register_proposal({"proposal_id": "pd", "from": "a", "to": "d", "status": "SENT", "expires_at": 1e9, "version": 1})
    rd = orc.accept_proposal("pd", "d", "k2", candidate=dcand, intent=dintent, baseline=dbase,
                             ctx={"blocked": set()}, now=10, intent_type="dating", dating_confirmed=False)
    check("§14.3 dating без confirm -> DATING_CONFIRM_REQUIRED (no auto-commit)", rd["code"] == "DATING_CONFIRM_REQUIRED")
    rd2 = orc.accept_proposal("pd", "d", "k3", candidate=dcand, intent=dintent, baseline=dbase,
                              ctx={"blocked": set()}, now=10, intent_type="dating", dating_confirmed=True)
    check("§14.3 dating с confirm -> ACCEPTED", rd2["ok"] and rd2["code"] == "ACCEPTED")

    print("\nБатч 3 (gate hardening + time + §14.3): %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
