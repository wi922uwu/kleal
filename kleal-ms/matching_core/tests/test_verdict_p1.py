# -*- coding: utf-8 -*-
"""Вердикт — Батч V-P1: #12 purpose-bound receiving policy · #16 exposure/dedup/rotation · #17 fatigue ·
#18 reason codes · #22 geo-privacy · #25 trust&safety · #27 multiple intents · #7/#20/#24 naming/docs."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.contracts import receiving_policy as RP
from matching_core.contracts import geo_privacy as GP
from matching_core.feedback_learning import reasons as RS
from matching_core.policy_engine import trust_safety as TS
from matching_core.reciprocity_readiness import fatigue as FT
from matching_core.orchestrator import intent_set as ISET
from matching_core.allocation import allocation as AL
from matching_core.relevance_engine import relevance as RL, decision as DE
from matching_core.policy_engine import gates as G
from matching_core.dating import dating as DAT

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def _item(name, rec, bucket="b", band="strong_option", tier="T1", reasons=("shares chess",)):
    return {"cand": {"name": name}, "reciprocal": rec, "readiness": "open_now", "bucket": bucket,
            "band": band, "lcb": 0.8, "coverage": 0.7, "policy": "ALLOW", "tier": tier, "reasons": list(reasons)}


def run():
    # ---------- #12 purpose-bound receiving policy ----------
    pol = RP.build_purpose_policy({"friendship": {"direct_invites": True, "group_invites": True},
                                   "networking": {"direct_invites": False},
                                   "games": {"direct_invites": True, "platforms": ["PC"]}})
    check("#12 friendship direct -> ok", RP.receiving_decision(pol, "friendship")[0] is True)
    check("#12 networking direct отключён -> нет", RP.receiving_decision(pol, "networking")[0] is False)
    check("#12 games на PS5 (не разрешённая платформа) -> нет", RP.receiving_decision(pol, "games", platform="PS5")[0] is False)
    check("#12 games на PC -> ok", RP.receiving_decision(pol, "games", platform="PC")[0] is True)
    check("#12 dating не opted-in: direct нет, group допустим",
          RP.receiving_decision(pol, "dating")[0] is False and RP.receiving_decision(pol, "dating", channel="group_invites")[0] is True)

    # ---------- #18 reason codes -> дифференцированные последствия ----------
    check("#18 8 reason codes", len(RS.REASON_CODES) == 8)
    check("#18 not_now: retry другого слота, cooldown 1 день",
          RS.consequence("not_now")["retry_other_slot"] and RS.consequence("not_now")["cooldown_sec"] == 86400)
    check("#18 wrong_time приглушает только слот (не человека)", RS.suppress_scope("wrong_time") == "time_slot" and not RS.is_person_level_block("wrong_time"))
    check("#18 not_interested_in_person -> скрыть человека", RS.is_person_level_block("not_interested_in_person"))
    check("#18 do_not_suggest_again -> отключить purpose", RS.consequence("do_not_suggest_again")["disable_purpose"])
    check("#18 safety_block -> в safety flow + скрыть", RS.routes_to_safety("safety_block") and RS.is_person_level_block("safety_block"))
    check("#18 cooldown_until считает по коду", RS.cooldown_until("not_now", 0) == 86400)

    # ---------- #22 geo-privacy staged disclosure ----------
    check("#22 клиенту — банда расстояния, не точное", GP.distance_band(0.5) == "<1 km" and GP.distance_band(None) == "unknown")
    zv = GP.client_location_view({"coarse_cell": "z9", "exact_point": (1, 2)}, stage="zone_only", km=0.5)
    check("#22 zone_only: точная координата withheld", zv.get("exact_point") is None and zv["exact_coord_withheld"] is True)
    ev = GP.client_location_view({"exact_point": (1, 2)}, stage="exact_point", km=0.5, plan_confirmed=True)
    check("#22 exact_point только после согласованного плана", ev.get("exact_point") == (1, 2) and ev["exact_coord_withheld"] is False)
    check("#22 live-location не в discovery", GP.live_location_in_discovery() is False)
    check("#22 домашний адрес не место первой встречи", GP.can_be_first_meeting_place("home") is False and GP.can_be_first_meeting_place("park") is True)
    try:
        GP.assert_no_exact_point_leak({"exact_point": (1, 2)}); leaked = False
    except ValueError:
        leaked = True
    check("#22 guard ловит утечку точной точки до плана", leaked)

    # ---------- #25 trust & safety (как gate, НЕ relevance) ----------
    check("#25 чистый аккаунт -> ALLOW", TS.evaluate_trust({})["action"] == TS.ALLOW)
    check("#25 moderation hold -> BLOCK", TS.evaluate_trust({"moderation_hold": True})["action"] == TS.BLOCK)
    check("#25 5 репортов -> BLOCK", TS.evaluate_trust({"reports_total": 5})["action"] == TS.BLOCK)
    check("#25 массовая рассылка -> LIMIT_OUTREACH", TS.evaluate_trust({"invites_last_1h": 12})["action"] == TS.LIMIT)
    check("#25 повторные отказы -> REDUCE_VISIBILITY", TS.evaluate_trust({"rejection_rate": 0.9})["action"] == TS.REDUCE_VISIBILITY)
    check("#25 outreach_cap: LIMIT срезает лимит", TS.outreach_cap({"invites_last_1h": 12}, 9) == 3 and TS.outreach_cap({"moderation_hold": True}, 9) == 0)
    # review-regress: velocity-cap НЕ маскируется co-occurring REDUCE_VISIBILITY (спамер с высоким rejection)
    check("#25 velocity-cap не теряется при co-occurring reduce-visibility",
          TS.outreach_cap({"invites_last_1h": 20, "distinct_recipients_1h": 9, "rejection_rate": 0.9}, 9) == 3)
    try:
        TS.assert_trust_not_relevance(["semantic_activity", "reports_24h"]); mixed = False
    except ValueError:
        mixed = True
    check("#25 trust-сигнал НЕ может быть relevance-фичёй", mixed)

    # ---------- #17 многомерная перегрузка (fatigue) ----------
    check("#17 чистая нагрузка -> не перегружен", FT.may_send({"received_24h": 0}))
    check("#17 превышен per_24h -> перегружен", FT.fatigue_state({"received_24h": 4})["overloaded"])
    check("#17 тихие часы -> не докучаем", FT.fatigue_state({}, in_quiet_hours=True)["overloaded"])
    check("#17 слабый T2 + лимит слабых -> перегружен", FT.fatigue_state({"weak_tier_24h": 2}, tier="T2")["overloaded"])
    check("#17 второй инвайт от того же отправителя -> перегружен", FT.fatigue_state({"from_sender_24h": 1})["overloaded"])

    # ---------- #27 несколько активных intent ----------
    games = {"type": "games", "domain": "games", "lifecycle": {"created_at": 5}}
    dating = {"type": "dating", "domain": "dating", "lifecycle": {"created_at": 9}}
    cand_intents = [games, dating]
    sel = ISET.select_for_reverse_reciprocity({"type": "games"}, cand_intents)
    check("#27 обратная взаимность берёт СОВМЕСТИМЫЙ по purpose intent", sel is games)
    check("#27 несовместимый purpose -> None", ISET.select_for_reverse_reciprocity({"type": "language_exchange"}, cand_intents) is None)
    kept, overflow = ISET.enforce_limit([dict(games) for _ in range(7)])
    check("#27 лимит активных intent = 5", len(kept) == 5 and len(overflow) == 2)
    cand = {"receiving_purpose_policy": RP.build_purpose_policy({"games": {"direct_invites": True}})}
    check("#27 предложить другой intent только с согласия по его purpose",
          ISET.may_offer_other_intent(cand, {"type": "games"}) is True and ISET.may_offer_other_intent({}, {"type": "games"}) is False)

    # ---------- #16 dedup (opt-in) + controlled rotation ----------
    dups = [_item("a", 0.9), _item("b", 0.8), _item("c", 0.7), _item("d", 0.6)]   # одинаковый dup_key
    s_nodedup = AL.rerank([dict(x) for x in dups], {}, ctx={})
    s_dedup = AL.rerank([dict(x) for x in dups], {}, ctx={"dedup_near_duplicates": True})
    check("#16 без dedup -> все 4", len(s_nodedup) == 4)
    check("#16 dedup near-dup -> не более 2", len(s_dedup) == 2)
    # review-regress: dedup идёт ПОСЛЕ сортировки -> остаются ЛУЧШИЕ (highest reciprocal), а не первые по входу
    unsorted_dups = [_item("anna", 0.10), _item("bob", 0.50), _item("carl", 0.95)]   # same dup_key, вход не по score
    kept_names = [s["cand"]["name"] for s in AL.rerank([dict(x) for x in unsorted_dups], {}, ctx={"dedup_near_duplicates": True})]
    check("#16 dedup сохраняет лучший из группы (carl 0.95), не первого по входу",
          "carl" in kept_names and "anna" not in kept_names)
    check("#16 rotation детерминирована между процессами (crc32) и различает seed",
          AL._rotation_rank(dups[0], "r1") != AL._rotation_rank(dups[0], "r2"))
    check("#16 static seed -> rotation выключена (тай-брейк на имя)", AL._rotation_rank(dups[0], "static") == 0)
    check("#16 ignored_pairs -> cooldown после игнорирования",
          "a" not in [s["cand"]["name"] for s in AL.rerank([dict(x) for x in dups], {}, ctx={"ignored_pairs": {"a"}})])

    # ---------- #7/#20/#24 честное именование + провизорность + возрастная политика ----------
    check("#7 conservative_relevance == R_lcb", RL.conservative_relevance({"lcb": 0.73}) == 0.73)
    check("#20 пороги помечены как provisional_expert_constants", DE.threshold_provenance()["proven"] is False and DE.THRESHOLDS_PROVISIONAL)
    check("#24 18+ объявлена как продуктовая политика", G.AGE_POLICY["declared_product_policy"] and G.AGE_POLICY["kind"] == "adults_only_18plus")

    # ---------- #13 dating: взаимная проверка + отдельные лимиты + friendship-guard ----------
    check("#13 отдельные (строже) dating rate limits", DAT.dating_rate_limits()["proposals_per_24h"] == 2)
    a_pref = {"gender": "f", "min_age": 25, "max_age": 35}
    b_prof = {"gender": "f", "age": 30, "langs": ["es"]}
    b_pref = {"gender": "m", "min_age": 28, "max_age": 40}
    a_prof = {"gender": "m", "age": 33, "langs": ["es"]}
    check("#13 взаимная проверка предпочтений: обе стороны подходят -> ok", DAT.mutual_preference_ok(a_pref, a_prof, b_pref, b_prof)[0] is True)
    check("#13 односторонний интерес (B не подходит A) -> нет", DAT.mutual_preference_ok(a_pref, a_prof, {"gender": "f"}, a_prof)[0] is False)
    check("#13 friendship-поведение НЕ dating-сигнал", DAT.is_dating_signal("friendship_message") is False and DAT.is_dating_signal("dating_like") is True)
    try:
        DAT.assert_no_friendship_to_dating_autoexpand("friendship", "dating"); expanded = False
    except ValueError:
        expanded = True
    check("#13 авто-расширение friendship->dating запрещено", expanded)

    print("\nБатч V-P1 (вердикт, 8 P1): %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
