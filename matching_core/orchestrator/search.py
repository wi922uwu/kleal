# -*- coding: utf-8 -*-
"""Приложение B.1 — Search pipeline, связывающий все слои в единый движок.

Порядок §3: capsule → policy snapshot → retrieval(tier) → policy.evaluate(ALLOW→score, BLOCK→skip до
feature building) → feature build A→B и B→A → directional relevance + reciprocal → readiness → band/
decision → allocation.rerank → transparent slate + immutable decision traces. Детерминирован, без LLM.
"""
from ..policy_engine import engine as POL
from ..policy_engine.engine import ALLOW, BLOCK, REVIEW
from ..retrieval import retriever as RET
from ..feature_builder import builder as FB
from ..feature_builder import unknowns as UNK
from ..relevance_engine import relevance as RL, decision as DE
from ..reciprocity_readiness import readiness as RD
from ..allocation import allocation as AL
from ..contracts import decision_trace as DT

_TYPE2DOMAIN = {"social": "social_meet", "social_meet": "social_meet", "walk": "walk",
                "games": "games", "gaming": "games", "sport": "sport_activity",
                "sport_activity": "sport_activity", "networking": "professional_networking",
                "language": "language_exchange", "language_exchange": "language_exchange",
                "dating": "dating", "culture": "culture_event", "watch": "watch_together",
                "coworking": "coworking"}


def domain_of(intent):
    return _TYPE2DOMAIN.get(str(intent.get("type") or "social").lower(), "social_meet")


def _reverse_features(intent, prof, cand, domain):
    """B→A: подходит ли ИСКАТЕЛЬ под то, что заявил кандидат (§9.4). Собственный intent B — сильнейший сигнал."""
    b_int = next((i for i in (cand.get("intents") or []) if isinstance(i, dict)), None)
    b_topics = ((b_int or {}).get("topics")) or cand.get("interests") or []
    pseudo = {"topics": b_topics, "mode": intent.get("mode"), "role": "meet",
              "time": (b_int or {}).get("time")}
    prof_as_cand = {"interests": prof.get("interests"), "vibe": prof.get("vibe"),
                    "langs": prof.get("langs"), "open": None,
                    "coarse_lat": prof.get("coarse_lat"), "coarse_lon": prof.get("coarse_lon")}
    cand_as_prof = {"vibe": cand.get("vibe"), "interests": cand.get("interests"),
                    "langs": cand.get("langs"),
                    "coarse_lat": cand.get("coarse_lat"), "coarse_lon": cand.get("coarse_lon")}
    return FB.build_features(pseudo, cand_as_prof, prof_as_cand, domain)


def search(intent, prof, pool, cfg, *, purpose="friendship", now=0.0, gate_ctx=None,
           broad_consent=False, budget=80, trace_log=None, search_id="srch"):
    """B.1 полный проход. Возвращает transparent slate (без процентов) + пишет decision traces."""
    domain = domain_of(intent)
    dom_cfg = cfg["domains"].get(domain) or cfg["domains"]["social_meet"]
    priors = RL.priors_from_config(cfg)
    bands = cfg["user_facing_bands"]
    ctx = dict(gate_ctx or {}); ctx.setdefault("blocked", set()); ctx.setdefault("received24", {})
    ctx["domain_cfg"] = dom_cfg
    snapshot = POL.prepare_snapshot(prof.get("name", "me"), purpose, config_version=cfg.get("config_version"))

    labeled = RET.retrieve(intent, pool, budget=budget)
    scored = []
    for r in labeled:
        c = r["cand"]
        verdict = POL.evaluate(intent, c, ctx)
        if verdict["decision"] == BLOCK:
            continue                                          # C#5: не скорится, не показывается
        F_ab = FB.build_features(intent, prof, c, domain)
        d_ab = RL.directional_score(F_ab, dom_cfg, priors)
        d_ba = RL.directional_score(_reverse_features(intent, prof, c, domain), dom_cfg, priors)
        rec = RL.reciprocal(d_ab, d_ba)
        readiness = RD.readiness_state(c, domain, now, cfg,
                                       ctx["received24"].get(str(c.get("name", "")).strip().lower(), 0))
        crit_unknown = UNK.high_impact_unknown(F_ab, intent, domain)   # Вердикт#8: критичный unknown → clarify
        band = DE.band(d_ab["lcb"], d_ab["coverage"], bands)
        dclass = DE.decision_class(d_ab["lcb"], d_ab["coverage"], r["tier"], dom_cfg,
                                   policy=verdict["decision"], broad_consent=broad_consent,
                                   high_impact_unknown=crit_unknown)
        pres = DE.presentation(F_ab, dom_cfg)
        bucket = None
        sem = F_ab["semantic_activity"]
        if sem[0] == FB.K_MATCH and sem[2]:
            bucket = sem[2].split(", ")[0]
        item = {"cand": c, "tier": r["tier"], "source": r["source"], "reciprocal": rec,
                "lcb": d_ab["lcb"], "coverage": d_ab["coverage"], "readiness": readiness,
                "bucket": bucket or (c.get("interests") or ["other"])[0], "policy": verdict["decision"],
                "band": band, "band_label": DE.BAND_LABELS[band][1], "decision_class": dclass,
                "reasons": pres["reasons_en"], "gap": pres["gap_en"],
                "low_coverage": DE.low_coverage(d_ab["coverage"], dom_cfg)}
        scored.append(item)
        if trace_log is not None:
            trace_log.log(DT.build_decision_trace(
                search_id, str(c.get("name", "")), intent_version=(intent.get("version") or 1),
                purpose_id=purpose, policy={"decision": verdict["decision"], "version": verdict["policy_version"]},
                semantic_tier=r["tier"], directional={"a_to_b": d_ab, "b_to_a": d_ba},
                reciprocal_relevance=rec, readiness=readiness, reason_keys=pres["reasons_en"],
                config_version=cfg.get("config_version")))

    slate = AL.rerank(scored, intent, cfg, ctx)
    # transparent slate (§9.7): качественный band, причины, gap — БЕЗ процентов
    return [{"name": s["cand"].get("name"), "tier": s["tier"], "band": s["band"], "band_label": s["band_label"],
             "decision_class": s["decision_class"], "readiness": s["readiness"], "reciprocal": s["reciprocal"],
             "reasons": s["reasons"], "gap": s["gap"], "low_coverage": s["low_coverage"],
             "policy": s["policy"], "allocation": s.get("allocation")} for s in slate]
