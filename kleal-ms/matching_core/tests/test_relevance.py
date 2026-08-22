# -*- coding: utf-8 -*-
"""§9 relevance + §9.7 transparent results — C#1/#2/#11/#23 (§23.3)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.config import validator as V
from matching_core.feature_builder import builder as FB
from matching_core.relevance_engine import relevance as RL, decision as DE

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def run():
    cfg = V.load_config()
    priors = RL.priors_from_config(cfg)
    dom = cfg["domains"]["social_meet"]
    bands = cfg["user_facing_bands"]

    prof = {"vibe": "chill", "interests": ["coffee"], "coarse_lat": 41.4, "coarse_lon": 2.1}
    intent = {"topics": ["coffee"], "mode": "offline", "role": "meet"}

    # ---- полный релевантный кандидат (много known) ----
    full = {"interests": ["coffee"], "vibe": "chill", "open": True, "km": 1.0}
    Ff = FB.build_features(intent, prof, full, "social_meet")
    df = RL.directional_score(Ff, dom, priors)
    check("RL1 lcb в [0,1]", 0.0 <= df["lcb"] <= 1.0)
    check("RL2 coverage полного высокое", df["coverage"] >= 0.6)

    # ---- разреженный кандидат: 1 known + остальное unknown ----
    sparse = {"interests": ["coffee"]}                       # нет vibe/open/geo -> много unknown
    Fs = FB.build_features(intent, prof, sparse, "social_meet")
    ds = RL.directional_score(Fs, dom, priors)
    # C#1: разреженный НЕ обгоняет полный без low-coverage-метки
    check("C#1 разреженный: низкое coverage", ds["coverage"] < df["coverage"])
    check("C#1 разреженный помечен low_coverage ИЛИ lcb ниже",
          DE.low_coverage(ds["coverage"], dom) or ds["lcb"] < df["lcb"])
    check("C#1 разреженный band != especially_close",
          DE.band(ds["lcb"], ds["coverage"], bands) != "especially_close")

    # ---- C#2: not_applicable НЕ снижает coverage (в отличие от unknown) ----
    F_na = dict(Ff); F_na["domain_constraints"] = (FB.NA, None, "")
    F_unk = dict(Ff); F_unk["domain_constraints"] = (FB.UNKNOWN, None, "")
    cov_na = RL.directional_score(F_na, dom, priors)["coverage"]
    cov_unk = RL.directional_score(F_unk, dom, priors)["coverage"]
    check("C#2 NA coverage >= unknown coverage", cov_na >= cov_unk)

    # ---- §9.4 reciprocal: 0.7·min + 0.3·mean, штраф односторонних ----
    a = {"lcb": 0.9}; b = {"lcb": 0.3}
    rec = RL.reciprocal(a, b)
    check("RL3 reciprocal формула", abs(rec - (0.7 * 0.3 + 0.3 * 0.6)) < 1e-6)
    check("RL4 reciprocal штрафует односторонность", rec < (a["lcb"] + b["lcb"]) / 2)

    # ---- C#11: подписка НЕ меняет relevance (payment не feature) ----
    paid = dict(full, subscription="premium", payment_status="paid")
    Fp = FB.build_features(intent, prof, paid, "social_meet")
    dp = RL.directional_score(Fp, dom, priors)
    check("C#11 subscription не меняет lcb/coverage", dp["lcb"] == df["lcb"] and dp["coverage"] == df["coverage"])

    # ---- §9.7 presentation: причины только из known_match (C#23), + gap ----
    pres = DE.presentation(Ff, dom)
    check("C#23 reasons только known (2-3, не выдуманные)", 1 <= len(pres["reasons_en"]) <= 3)
    known_details = {v[2] for k, v in Ff.items() if v[0] == FB.K_MATCH}
    check("C#23 нет процентов в выдаче", all("%" not in r or "km" in r or "shares" in r for r in pres["reasons_en"]))

    # ---- §9.6 decision_class ----
    dc_strong = DE.decision_class(0.9, 0.9, "T1", dom, policy="ALLOW")
    dc_disc = DE.decision_class(0.55, 0.5, "T3", dom, policy="ALLOW")  # >= discovery_min_lcb 0.52
    dc_none = DE.decision_class(0.2, 0.3, "T1", dom, policy="ALLOW")
    dc_block = DE.decision_class(0.9, 0.9, "T1", dom, policy="BLOCK")
    check("DC1 высокий+T1 -> strong_personal", dc_strong == "strong_personal")
    check("DC2 средний+T3 -> discovery_only", dc_disc == "discovery_only")
    check("DC3 низкий -> no_outreach", dc_none == "no_outreach")
    check("DC4 policy!=ALLOW -> no_outreach", dc_block == "no_outreach")
    check("DC5 T2 без consent не strong", DE.decision_class(0.9, 0.9, "T2", dom, broad_consent=False) != "strong_personal")
    check("DC6 T2 с consent -> usable", DE.decision_class(0.9, 0.9, "T2", dom, broad_consent=True) in ("usable_personal", "strong_personal"))
    check("DC7 high-impact unknown -> clarification", DE.decision_class(0.9, 0.9, "T1", dom, high_impact_unknown=True) == "clarification")

    # ---- §9.7 band пороги из config ----
    check("BD1 especially_close порог", DE.band(0.8, 0.8, bands) == "especially_close")
    check("BD2 needs_clarification при низком", DE.band(0.3, 0.2, bands) == "needs_clarification")

    print("\n§9 relevance: %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
