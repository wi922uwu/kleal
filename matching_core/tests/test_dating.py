# -*- coding: utf-8 -*-
"""§17 dating mode — consent/capsule/isolation/pilot-gate (C#12/#13)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.dating import dating as DA
from matching_core.contracts import profile as PR

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def run():
    user = PR.build_user_profile("u1", name="Ann", age=29, gender="f", orientation="straight",
                                 interests=["coffee"], dating_preferences={"age_range": [25, 35]},
                                 geo={"exact_lat": 41.1, "exact_lon": 2.2, "coarse_area": "Eixample"},
                                 dating_optin=True, target_preferences_confirmed=True)

    # consent gate
    ok, _ = DA.consent_gate(user, {"type": "dating"})
    check("DA1 consent gate ok (optin+confirmed+18+)", ok)
    check("DA2 без optin -> reject", not DA.consent_gate(dict(user, dating_optin=False), {"type": "dating"})[0])
    check("DA3 несовершеннолетний -> reject", not DA.consent_gate(dict(user, age=16), {"type": "dating"})[0])
    check("DA4 не dating intent -> reject", not DA.consent_gate(user, {"type": "social_meet"})[0])

    # capsule: минимизация
    cap = DA.build_dating_capsule(user)
    f = cap["fields"]
    check("DA5 age -> band без consent_exact_age", f.get("age_band") == "25-34" and "age" not in f)
    check("DA6 gender/orientation НЕ отдаются без sensitive consent (§17.1)", "gender" not in f and "orientation" not in f)
    check("C#14 точная локация не в capsule", "exact_lat" not in (f.get("location") or {}))
    check("DA7 no auto-accept", cap["auto_accept"] is False and cap["sensitive_minimized"])
    cap2 = DA.build_dating_capsule(user, consents={"consent_share_sensitive": True, "consent_exact_age": True})
    check("DA8 с consent -> gender + точный возраст", cap2["fields"].get("gender") == "f" and cap2["fields"].get("age") == 29)

    # explanation без чувствительных причин / псевдо-скора (§17.1)
    ex = DA.dating_explanation(["shares coffee", "compatibility_score high", "orientation match", "same_time"])
    check("DA9 explanation убирает sensitive/pseudo-score", ex == ["shares coffee", "same_time"])

    # §17.2 изоляция
    check("DA10 dating feedback scope отдельный", DA.feedback_scope() == "dating")
    check("DA11 dating не пересекается в friendship", DA.crosses_into("friendship") is True and DA.crosses_into("dating") is False)

    # §17.3 pilot gate
    en, missing = DA.pilot_gate({"ux_ready": True})
    check("DA12 pilot gate: не хватает review -> не включён", (not en) and len(missing) == 5)
    en2, _ = DA.pilot_gate({k: True for k in DA.PILOT_REQUIRED})
    check("DA13 pilot gate: все флаги -> включён", en2)

    print("\n§17 dating: %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
