# -*- coding: utf-8 -*-
"""Вердикт (внешний ревью) — Батч V-P0: закрытие десяти P0-замечаний.
#1 T5-терминал+nearby block · #3 LLM provenance · #4 agent-decision guard · #5+6 active/passive
взаимность · #8 critical unknown · #9 expansion_policy · #10 intent lifecycle."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.orchestrator import expansion as EX
from matching_core.orchestrator import agent_decision as AD
from matching_core.orchestrator import state_machines as SM
from matching_core.reciprocity_readiness import reciprocity as RC
from matching_core.feature_builder import unknowns as UNK
from matching_core.feature_builder.builder import UNKNOWN, K_MATCH, NA
from matching_core.intent_compiler import compiler as CO
from matching_core.contracts import intent as IC

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def run():
    # ---------- #1 T5-терминал: НЕ персональная выдача нерелевантных ----------
    it_family = {"expansion_policy": "allow_family", "fallback": {}}
    resp = EX.no_topical_overlap_response(it_family, has_alt_types=True,
                                          nearby_open=[{"name": "Ann"}, {"name": "Bob"}])
    check("#1 personal_outreach жёстко False", resp["personal_outreach"] is False)
    check("#1 честный терминал: последний шаг honest_no_result", resp["steps"][-1] == "honest_no_result")
    check("#1 предлагает расширение (не молча)", "offer_expansion_consent" in resp["steps"])
    blk = resp["nearby_open_block"]
    check("#1 блок 'рядом' отделён от результатов intent", blk and blk["separated_from_intent_results"] is True)
    check("#1 из блока 'рядом' личное приглашение ЗАПРЕЩЕНО", blk["personal_invite_allowed"] is False)
    check("#1 личное приглашение требует нового подтверждения", blk["requires_new_confirmation"] is True)
    # exact_only: не предлагаем расширение и не подмешиваем событие (alt_types не разрешён политикой)
    it_exact = {"expansion_policy": "exact_only", "fallback": {}}
    r2 = EX.no_topical_overlap_response(it_exact, has_alt_types=True, nearby_open=None)
    check("#1 exact_only: нет offer_expansion_consent", "offer_expansion_consent" not in r2["steps"])
    check("#1 exact_only: нет event-fallback", "relevant_event_group_room" not in r2["steps"])
    check("#1 нет nearby -> блока нет", r2["nearby_open_block"] is None)

    # ---------- #9 expansion_policy как жёсткая граница ----------
    check("#9 exact_only разрешает только exact", EX.policy_allows_axis(it_exact, "exact")
          and not EX.policy_allows_axis(it_exact, "sibling") and not EX.policy_allows_axis(it_exact, "parent"))
    check("#9 allow_family разрешает parent, но не time_distance",
          EX.policy_allows_axis(it_family, "parent") and not EX.policy_allows_axis(it_family, "time_distance"))
    it_evt = {"expansion_policy": "event_fallback_allowed", "fallback": {}}
    check("#9 event_fallback разрешает alternative_type", EX.policy_allows_axis(it_evt, "alternative_type"))
    check("#9 saved_search разрешён при любой политике", EX.policy_allows_axis(it_exact, "saved_search"))
    check("#9 expand_step(sibling) при exact_only -> None", EX.expand_step(it_exact, 1) is None)
    check("#9 default policy = allow_family", EX.expansion_policy({"fallback": {}}) == "allow_family")
    # поле доезжает через build_intent -> flat
    itf = IC.flat(IC.build_intent("i", "u", "games", topics=["chess"], expansion_policy="exact_only"))
    check("#9 build_intent+flat несут expansion_policy", itf["expansion_policy"] == "exact_only")

    # ---------- #5+6 active vs passive взаимность + один штраф неизвестности ----------
    a = {"mean": 0.8, "coverage": 0.9, "lcb": 0.78}
    b = {"mean": 0.7, "coverage": 0.3, "lcb": 0.40}          # низкий lcb из-за НЕИЗВЕСТНОСТИ, не несовместимости
    va = RC.reciprocity_view(a, b, active_counter_intent=True)
    vp = RC.reciprocity_view(a, b, active_counter_intent=False)
    check("#5 active -> заполнен active_reciprocity, passive=None",
          va["active_reciprocity"] is not None and va["passive_interest_fit"] is None)
    check("#5 passive -> заполнен passive_interest_fit, active=None",
          vp["passive_interest_fit"] is not None and vp["active_reciprocity"] is None)
    check("#6 passive НЕ штрафует неизвестность дважды (использует mean_b) -> value выше active",
          vp["value"] > va["value"])
    check("#6 uncertainty хранится ОТДЕЛЬНО", abs(vp["uncertainty"] - 0.7) < 1e-9)
    # классификация вида взаимности из интента/кандидата
    intent = {"topics": ["chess"]}
    active_cand = {"name": "x", "intents": [{"topics": ["chess"]}]}
    passive_cand = {"name": "y", "interests": ["chess"]}
    check("#5 classify: встречный активный intent -> active",
          RC.classify_reciprocity(intent, active_cand)["kind"] == "active")
    check("#5 classify: только профильный интерес -> passive",
          RC.classify_reciprocity(intent, passive_cand)["kind"] == "passive")

    # ---------- #8 три класса неизвестности; критичный блокирует outreach ----------
    feats_crit = {"time_feasibility": (UNKNOWN, None, ""), "semantic_activity": (K_MATCH, 1.0, "chess"),
                  "location_feasibility": (UNKNOWN, None, "")}
    it_timed = {"time": {"windows": [["20:00", "22:00"]]}, "mode": "offline"}
    cl = UNK.classify_unknowns(feats_crit, it_timed, "games")
    check("#8 unknown времени при заявленном времени -> outreach_blocking",
          cl["by_field"]["time_feasibility"] == "outreach_blocking")
    check("#8 unknown локации -> coverage_reducing (не блок)",
          cl["by_field"]["location_feasibility"] == "coverage_reducing")
    check("#8 critical -> blocks_outreach True", cl["blocks_outreach"] is True and "time_feasibility" in cl["critical"])
    # без заявленного времени тот же unknown НЕ критичен
    cl2 = UNK.classify_unknowns({"time_feasibility": (UNKNOWN, None, "")}, {"time": "flexible", "mode": "offline"}, "games")
    check("#8 unknown времени при flexible -> НЕ блокирует", cl2["blocks_outreach"] is False)
    check("#8 high_impact_unknown предикат", UNK.high_impact_unknown(feats_crit, it_timed, "games") is True)
    # review-regress: unknown из НЕзаполненного опционального поля кандидата (formats/entities) НЕ блокирует
    # outreach — иначе сильный T0/T1 молча уходит в 'clarification' (formats/entities почти никогда не заявлены)
    feats_opt = {"mode_format": (UNKNOWN, None, ""), "domain_constraints": (UNKNOWN, None, "")}
    check("#8 mode_format unknown при обычном mode -> НЕ критично",
          UNK.classify_unknowns(feats_opt, {"mode": "offline"}, "games")["blocks_outreach"] is False)
    check("#8 domain_constraints unknown в games без явного требования -> НЕ критично",
          UNK.classify_unknowns({"domain_constraints": (UNKNOWN, None, "")}, {"mode": "online"}, "games")["blocks_outreach"] is False)
    check("#8 но ЯВНОЕ требование формата/платформы -> критично",
          UNK.classify_unknowns(feats_opt, {"mode": "offline", "format_required": True, "platform_required": True}, "games")["blocks_outreach"] is True)

    # ---------- #3 LLM provenance: explicit/inferred/defaulted + confidence + raw_text + tax_version ----------
    res = CO.compile_intent({"topics": ["chess"], "type": "games", "requiredLanguages": ["es"], "mode": None},
                            intent_id="i1", user_id="u1", raw_text="хочу шахматы на испанском",
                            taxonomy_version="tax-v1", provenance={"requiredLanguages": "inferred"},
                            field_confidence={"topics": 0.95})
    fields = res["fields"]
    check("#3 explicit-поле с явной уверенностью", fields["topics"]["source"] == "explicit" and fields["topics"]["confidence"] == 0.95)
    check("#3 inferred-поле", fields["requiredLanguages"]["source"] == "inferred")
    check("#3 defaulted-поле (mode=None)", fields["mode"]["source"] == "defaulted")
    check("#3 raw_text и taxonomy_version сохранены", res["raw_text"] == "хочу шахматы на испанском" and res["taxonomy_version"] == "tax-v1")
    check("#3 provenance записан в сам intent", res["intent"]["provenance"]["raw_text"] == "хочу шахматы на испанском")
    check("#3 низкая уверенность по HARD-полю -> requires_clarification",
          "requiredLanguages" in res["low_confidence_hard"] and res["requires_clarification"] is True)
    # review-regress: hard-токен dating_mode резолвится в слот 'type' -> низкая уверенность dating тоже флагается
    resd = CO.compile_intent({"type": "dating", "topics": ["x"]}, intent_id="i2", user_id="u2",
                             provenance={"type": "inferred"}, field_confidence={"type": 0.3})
    check("#3 низкая уверенность по инференсу dating -> requires_clarification",
          "dating_mode" in resd["low_confidence_hard"] and resd["requires_clarification"] is True)

    # ---------- #4 agent-decision: LLM не решает за агента ----------
    try:
        AD.assert_llm_role("decide_agent_agreement"); raised = False
    except AD.LLMBoundaryViolation:
        raised = True
    check("#4 LLM-роль 'решить за агента' -> запрещена", raised)
    check("#4 LLM-роль 'составить приглашение' -> разрешена", AD.assert_llm_role("compose_invitation") is True)
    okd = AD.can_reach_candidate(receiving_eligible=True, readiness="open_now", purpose_ok=True,
                                 active_prefs_ok=True, within_limits=True, deterministic_policy="ALLOW")
    check("#4 все детерминированные условия -> allowed", okd["allowed"] is True)
    blk4 = AD.can_reach_candidate(receiving_eligible=True, readiness="passive_discovery", purpose_ok=True,
                                  active_prefs_ok=True, within_limits=True, deterministic_policy="ALLOW")
    check("#4 passive_discovery -> нет personal outreach", blk4["allowed"] is False and "not_ready_for_outreach" in blk4["blockers"])
    dat = AD.can_reach_candidate(receiving_eligible=True, readiness="open_now", purpose_ok=True,
                                 active_prefs_ok=True, within_limits=True, deterministic_policy="ALLOW",
                                 requires_explicit_user_action=True, user_action_taken=False)
    check("#4 требуется явное действие пользователя (dating) -> requires_user_action", dat["requires_user_action"] is True)

    # ---------- #10 полный lifecycle intent ----------
    check("#10 11 lifecycle-состояний", len(IC.LIFECYCLE_STATES) == 11 and "clarification_required" in IC.LIFECYCLE_STATES)
    check("#10 draft->active допустим", SM.assert_transition("intent_lifecycle", "draft", "active") is True)
    check("#10 completed терминально", not SM.can_transition("intent_lifecycle", "completed", "active"))
    try:
        SM.assert_transition("intent_lifecycle", "completed", "active"); bad = False
    except SM.InvalidTransition:
        bad = True
    check("#10 недопустимый переход бросает", bad)
    exp_it = IC.build_intent("i", "u", "games", topics=["chess"], created_at=0, expires_at=100)
    check("#10 lifecycle_state: TTL истёк -> expired", IC.lifecycle_state(exp_it, now=200) == "expired")
    check("#10 participates_in_ranking: активный до TTL -> True", IC.participates_in_ranking(exp_it, now=50) is True)
    check("#10 participates_in_ranking: истёкший -> False", IC.participates_in_ranking(exp_it, now=200) is False)

    print("\nБатч V-P0 (вердикт, 10 P0): %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
