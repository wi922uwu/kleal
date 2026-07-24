# -*- coding: utf-8 -*-
"""Аудит P0#1 — authoritative end-to-end orchestrator: единый entrypoint, фиксированные стадии, no-bypass."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.config import validator as V
from matching_core.orchestrator import pipeline as P
from matching_core.orchestrator import search as S
from matching_core.observability import trace as OB

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def run():
    cfg = V.load_config()
    intent = {"type": "games", "topics": ["dota2"], "mode": "online", "role": "support", "version": 1}
    me = {"name": "me", "interests": ["dota2"], "vibe": "calm", "langs": ["en"]}
    pool = [
        {"name": "p_dota", "interests": ["dota2"], "intents": [{"topics": ["dota2"]}], "role": "support", "open": True, "langs": ["en"], "vibe": "calm"},
        {"name": "p_lol", "interests": ["lol"], "role": "support", "open": True, "langs": ["en"], "vibe": "calm"},
    ]

    # 1. run_search — авторитетный проход: возвращает slate + прошёл ВСЕ обязательные стадии
    res = P.run_search(intent, me, pool, cfg, purpose="games", now=1.0, search_id="run1")
    check("P1 run_search вернул slate", isinstance(res.get("slate"), list) and len(res["slate"]) >= 1)
    check("P1 прошли ВСЕ обязательные стадии", all(s in res["stages"] for s in P.SEARCH_STAGES))
    check("P1 порядок стадий соблюдён (intent_snapshot первым, presentation последним)",
          res["stages"][0] == "intent_snapshot" and res["stages"][-1] == "presentation")

    # 2. публичный search() делегирует в оркестратор (тот же slate)
    slate2 = S.search(intent, me, pool, cfg, purpose="games", now=1.0, search_id="run1")
    check("P1 search() делегирует в pipeline (совпадает по именам)",
          [x["name"] for x in slate2] == [x["name"] for x in res["slate"]])

    # 3. no-bypass: enforce ловит пропущенную обязательную стадию (fail-closed)
    r = P._Run("x")
    for st in P.SEARCH_STAGES[:-1]:   # прошли все, кроме presentation
        r.stage(st)
    try:
        r.enforce(P.SEARCH_STAGES); raised = False
    except P.PipelineError:
        raised = True
    check("P1 no-bypass: пропуск обязательной стадии -> PipelineError", raised)
    # полный проход стадий не бросает
    r2 = P._Run("y"); [r2.stage(st) for st in P.SEARCH_STAGES]
    try:
        r2.enforce(P.SEARCH_STAGES); ok_full = True
    except P.PipelineError:
        ok_full = False
    check("P1 полный набор стадий -> enforce проходит", ok_full)

    # 4. trace по-прежнему работает через оркестратор
    tl = OB.TraceLog()
    P.run_search(intent, me, pool, cfg, purpose="games", now=1.0, search_id="run2", trace_log=tl)
    check("P1 decision traces пишутся через оркестратор", len(tl.all()) >= 1)

    # ---- Аудит P0#2: loose-параметры убраны, fail-closed ----
    def raises(fn):
        try:
            fn(); return False
        except (P.PipelineError, TypeError):
            return True

    check("P2 purpose из intent snapshot (games), не из умолчания",
          P.purpose_of({"type": "games"}) == "games" and P.purpose_of({"type": "dating"}) == "dating")
    check("P2 явный intent.purpose приоритетнее type", P.purpose_of({"type": "games", "purpose": "friendship"}) == "friendship")
    check("P2 нет выводимого purpose -> None", P.purpose_of({"type": "??unknown??"}) is None)
    # mismatch purpose arg vs snapshot -> fail-closed
    check("P2 mismatch purpose(dating vs games-intent) -> PipelineError",
          raises(lambda: P.run_search(intent, me, pool, cfg, purpose="dating", now=1.0, search_id="x")))
    # confirmed dating intent НЕ может стать friendship (purpose из snapshot; сам поиск dating — только через обёртку, #7)
    check("P2 dating-intent -> purpose=dating (не friendship)",
          P.purpose_of({"type": "dating", "topics": ["coffee"]}) == "dating")
    # intent без выводимого purpose -> ошибка
    check("P2 intent без purpose -> PipelineError",
          raises(lambda: P.run_search({"topics": ["x"]}, me, pool, cfg, now=1.0, search_id="x")))
    # now / search_id обязательны
    check("P2 now=None -> PipelineError", raises(lambda: P.run_search(intent, me, pool, cfg, now=None, search_id="x")))
    check("P2 search_id пустой -> PipelineError", raises(lambda: P.run_search(intent, me, pool, cfg, now=1.0, search_id="")))
    check("P2 отсутствие now/search_id (обязательные kwargs) -> TypeError",
          raises(lambda: P.run_search(intent, me, pool, cfg)))
    # broad_consent берётся из intent snapshot; mismatch аргумента -> fail-closed
    check("P2 broad_consent из snapshot (default False)", P.broad_consent_of(intent) is False)
    check("P2 broad_consent из fallback.consent.broad_matching",
          P.broad_consent_of({"fallback": {"consent": {"broad_matching": True}}}) is True)
    check("P2 mismatch broad_consent(True vs snapshot False) -> PipelineError",
          raises(lambda: P.run_search(intent, me, pool, cfg, broad_consent=True, now=1.0, search_id="x")))

    # ---- Аудит P0#3: hard-eligibility prefilter ДО budget truncation ----
    from matching_core.policy_engine import engine as POL
    # Сценарий из аудита: первые budget кандидатов заблокированы, хорошие допустимые — за хвостом.
    # Строим пул: 6 заблокированных dota-игроков (blocksMe) + 1 допустимый dota-игрок В КОНЦЕ. budget=3.
    big_intent = {"type": "games", "topics": ["dota2"], "mode": "online", "version": 1}
    blocked = [{"name": "blk%d" % i, "interests": ["dota2"], "role": "support", "open": True,
                "langs": ["en"], "blocksMe": True} for i in range(6)]
    good = {"name": "good_dota", "interests": ["dota2"], "role": "support", "open": True, "langs": ["en"]}
    pool_bt = blocked + [good]
    res_bt = P.run_search(big_intent, me, pool_bt, cfg, now=1.0, search_id="bt", budget=3)
    check("P3 prefilter убрал 6 hard-BLOCK до бюджета", res_bt["prefilter"]["dropped_hard"] == 6
          and res_bt["prefilter"]["eligible"] == 1)
    check("P3 допустимый кандидат за хвостом НЕ потерян бюджетом",
          "good_dota" in [x["name"] for x in res_bt["slate"]])
    # прямой контракт префильтра
    elig, st = POL.hard_prefilter(big_intent, pool_bt, {"blocked": set()})
    check("P3 hard_prefilter: eligible=1 из 7", st["eligible"] == 1 and st["input"] == 7)
    check("P3 hard_blocked ловит blocksMe", POL.hard_blocked(big_intent, blocked[0], {}) is True
          and POL.hard_blocked(big_intent, good, {}) is False)

    # ---- Аудит P0#4: единый semantic source of truth (canonical авторитетен, seed — fallback) ----
    from matching_core.taxonomy import graph as TX, canonical as CAN
    from matching_core.retrieval import retriever as RET
    check("P4 canonical доступен как источник", CAN.AVAILABLE and len(CAN.NODES) >= 400)
    check("P4 known-пара через canonical (dota2/lol=3)", TX.similarity(["dota2"], ["lol"])[0] == 3)
    check("P4 exact через canonical (dota2/dota2=4)", TX.similarity(["dota2"], ["dota2"])[0] == 4)
    check("P4 canonical ловит 'кино'->cinema (seed давал 0)", TX.similarity(["кино"], ["cinema"])[0] >= 3)
    check("P4 seed fallback для off-taxonomy литерала (labubu==labubu=4)", TX.similarity(["labubu"], ["labubu"])[0] == 4)
    check("P4 нет ложного матча несвязанных (labubu/dota2=0)", TX.similarity(["labubu"], ["dota2"])[0] == 0)
    # единый источник: assign_tier (retriever) и build_features идут через ЭТОТ же resolver
    check("P4 tier через тот же resolver (reciprocal dota2 -> T0)",
          RET.assign_tier({"topics": ["dota2"]}, {"interests": ["dota2"], "intents": [{"topics": ["dota2"]}]}) == "T0")

    # ---- Аудит P0#5: reciprocity_view в живом ranking (active vs passive, без двойного штрафа) ----
    from matching_core.reciprocity_readiness import reciprocity as RCm
    from matching_core.relevance_engine import relevance as RLm
    pool5 = [{"name": "active", "interests": ["dota2"], "intents": [{"topics": ["dota2"]}], "open": True, "langs": ["en"], "vibe": "calm"},
             {"name": "passive", "interests": ["dota2"], "open": True, "langs": ["en"], "vibe": "calm"}]
    res5 = P.run_search({"type": "games", "topics": ["dota2"], "mode": "online", "version": 1}, me, pool5, cfg, now=1.0, search_id="r5")
    kinds = {x["name"]: x.get("reciprocity_kind") for x in res5["slate"]}
    check("P5 slate несёт reciprocity_kind + uncertainty",
          all(("reciprocity_kind" in x and "uncertainty" in x) for x in res5["slate"]))
    check("P5 встречный active intent -> kind=active", kinds.get("active") == "active")
    check("P5 без встречного intent -> kind=passive", kinds.get("passive") == "passive")
    a = {"mean": 0.8, "coverage": 0.9, "lcb": 0.78}; b = {"mean": 0.7, "coverage": 0.3, "lcb": 0.40}
    vp = RCm.reciprocity_view(a, b, active_counter_intent=False)["value"]
    va = RCm.reciprocity_view(a, b, active_counter_intent=True)["value"]
    old = RLm.reciprocal(a, b)
    check("P5 passive НЕ штрафует неизвестность дважды (value > старой §9.4-формулы)", vp > old)
    check("P5 active == §9.4-формула (обратная совместимость)", abs(va - old) < 1e-9)

    # ---- Аудит P0#6: typed dispatch T4 (не person-моделью; отдельная alternatives-дорожка) ----
    pool6 = [
        {"name": "person_dota", "interests": ["dota2"], "open": True, "langs": ["en"], "vibe": "calm"},
        {"name": "DotaEvent", "kind": "event", "topics": ["dota2"], "category": "games",
         "capacity": {"current": 0, "max": 50}, "access": "open"},
        {"name": "DotaGroup", "kind": "group", "interests": ["dota2"]},   # group -> нет typed-модели -> исключён
    ]
    # expansion_policy=event_fallback_allowed -> T4-альтернативы РАЗРЕШЕНЫ к показу (Аудит #10)
    res6 = P.run_search({"type": "games", "topics": ["dota2"], "mode": "online", "version": 1,
                         "expansion_policy": "event_fallback_allowed"}, me, pool6, cfg, now=1.0, search_id="r6")
    slate_names = [x["name"] for x in res6["slate"]]
    alt_names = [x["name"] for x in res6["alternatives"]]
    check("P6 person -> в person top-N", "person_dota" in slate_names)
    check("P6 T4 event НЕ в person top-N (не person-скорится)", "DotaEvent" not in slate_names)
    check("P6 T4 event -> в alternatives через typed model", "DotaEvent" in alt_names)
    check("P6 alternatives несут typed_relevance + transaction",
          all(("typed_relevance" in a and "transaction" in a) for a in res6["alternatives"]))
    check("P6 group (нет typed-модели) исключён, НЕ person-скорится",
          "DotaGroup" not in slate_names and "DotaGroup" not in alt_names)
    check("P6 typed_relevance события через свою модель (dota2 -> 1.0)",
          next((a["typed_relevance"] for a in res6["alternatives"] if a["name"] == "DotaEvent"), None) == 1.0)

    # ---- Аудит P0#7: generic dating запрещён без dating-обёртки ----
    dintent = {"type": "dating", "topics": ["coffee"], "mode": "offline", "radiusKm": 10,
               "minAge": 25, "maxAge": 40, "version": 1}
    dpool = [{"name": "dcand", "interests": ["coffee"], "open": True, "langs": ["en"], "vibe": "social",
              "age": 30, "datingOk": True}]
    duser = {"name": "me", "interests": ["coffee"], "age": 30, "dating_optin": True, "target_preferences_confirmed": True}
    check("P7 generic run_search(dating) без токена -> PipelineError",
          raises(lambda: P.run_search(dintent, duser, dpool, cfg, now=1.0, search_id="d")))
    check("P7 generic search()-shim с dating -> PipelineError",
          raises(lambda: S.search(dintent, duser, dpool, cfg, now=1.0, search_id="d")))
    rd = P.run_dating_search(duser, dintent, duser, dpool, cfg, now=1.0, search_id="dw")
    check("P7 dating-обёртка работает (slate + dating meta)", isinstance(rd.get("slate"), list) and "dating" in rd)
    check("P7 обёртка без dating_optin -> PipelineError (consent)",
          raises(lambda: P.run_dating_search({"name": "m", "age": 30}, dintent, duser, dpool, cfg, now=1.0, search_id="d")))
    check("P7 обёртка с не-dating intent -> PipelineError",
          raises(lambda: P.run_dating_search(duser, {"type": "games", "topics": ["dota2"]}, duser, dpool, cfg, now=1.0, search_id="d")))

    # ---- Аудит P0#8: fail-closed семантика REVIEW (BLOCK/REVIEW/ALLOW) ----
    from matching_core.relevance_engine import decision as DE
    pool8 = [
        {"name": "good", "interests": ["dota2"], "intents": [{"topics": ["dota2"]}], "open": True, "langs": ["en"], "vibe": "calm"},
        {"name": "rev", "interests": ["dota2"], "open": True, "langs": ["en"], "vibe": "calm", "safetyFlags": ["review"]},
        {"name": "blk", "interests": ["dota2"], "open": True, "langs": ["en"], "vibe": "calm", "blocksMe": True},
    ]
    res8 = P.run_search({"type": "games", "topics": ["dota2"], "mode": "online", "version": 1}, me, pool8, cfg,
                        now=1.0, search_id="r8", gate_ctx={"blocked": set()})
    by = {x["name"]: x for x in res8["slate"]}
    check("P8 BLOCK -> отсутствует в slate (never present)", "blk" not in by)
    check("P8 REVIEW -> присутствует, но quarantined=True", "rev" in by and by["rev"]["quarantined"] is True)
    check("P8 REVIEW -> discovery_only, НИКОГДА personal",
          by["rev"]["decision_class"] == "discovery_only" and not DE.is_personal(by["rev"]["decision_class"]))
    check("P8 REVIEW несёт policy=REVIEW", by.get("rev", {}).get("policy") == "REVIEW")
    check("P8 ALLOW -> normal (policy=ALLOW, может быть personal)", "good" in by and by["good"]["policy"] == "ALLOW")
    check("P8 инвариант: personal outreach ТОЛЬКО при ALLOW",
          all((not DE.is_personal(x["decision_class"])) or x["policy"] == "ALLOW" for x in res8["slate"]))
    check("P8 семантика зафиксирована в decision.POLICY_SEMANTICS",
          set(DE.POLICY_SEMANTICS) == {"BLOCK", "REVIEW", "ALLOW"})

    # ---- Аудит P0#9: revalidation перед отправкой proposal ----
    gintent = {"type": "games", "topics": ["dota2"], "mode": "online", "version": 1}
    cand9 = {"name": "c9", "interests": ["dota2"], "intents": [{"topics": ["dota2"]}], "open": True,
             "langs": ["en"], "vibe": "calm", "visibility": "public", "accountStatus": "active"}
    res9 = P.run_search(gintent, me, [cand9], cfg, now=1.0, search_id="r9")
    item9 = next((x for x in res9["slate"] if x["name"] == "c9"), None)
    check("P9 slate несёт revalidation_baseline", item9 is not None and "revalidation_baseline" in item9)
    base = item9["revalidation_baseline"]
    # 1) кандидат не менялся -> proposal authorization + before_send OK -> SENT
    s_ok = P.authorize_and_send(candidate=cand9, intent=gintent, cfg=cfg, now=2.0, baseline=base, gate_ctx={"blocked": set()})
    check("P9 unchanged кандидат -> SENT", s_ok["sent"] is True and s_ok["code"] == "SENT")
    # 2) МЕЖДУ search и send изменилось monitored-поле (capacity, не блокирующее) -> revalidation before_send ловит
    drifted = dict(cand9); drifted["capacity"] = {"current": 0, "max": 10}
    s_reval = P.authorize_and_send(candidate=drifted, intent=gintent, cfg=cfg, now=2.0, baseline=base, gate_ctx={"blocked": set()})
    check("P9 дрейф состояния после search -> POLICY_CHANGED, НЕ отправлено",
          s_reval["sent"] is False and s_reval["code"] == "POLICY_CHANGED" and s_reval["stage"] == "revalidation_before_send")
    check("P9 revalidation указывает изменённое поле", "capacity" in s_reval.get("changed", []))
    # 3) кандидат заблокировал -> proposal authorization (policy BLOCK) ловит раньше -> НЕ отправлено
    blocked = dict(cand9); blocked["blocksMe"] = True
    s_auth = P.authorize_and_send(candidate=blocked, intent=gintent, cfg=cfg, now=2.0, baseline=base, gate_ctx={"blocked": set()})
    check("P9 кандидат заблокировал -> НЕ отправлено (fail-closed)", s_auth["sent"] is False)
    # 4) кандидат на паузе -> readiness не open -> authorization не пускает
    paused = dict(cand9); paused["paused"] = True
    s_paused = P.authorize_and_send(candidate=paused, intent=gintent, cfg=cfg, now=2.0, baseline=base, gate_ctx={"blocked": set()})
    check("P9 кандидат на паузе -> НЕ отправлено", s_paused["sent"] is False)
    check("P9 OUTREACH_STAGES: revalidation перед transaction",
          list(P.OUTREACH_STAGES)[:3] == ["proposal_authorization", "revalidation", "transaction"])

    print("\nАудит P0#1..#9 (ВЕСЬ P0): %d passed, %d failed" % (R["pass"], R["fail"]))

    # ---- Аудит P1#10: retrieval eligibility ≠ present-as-fallback ≠ outreach ----
    # Пул: T1(exact dota2) + T2(lol, parent) + T3(coffee, adjacent-ish). exact_only не должен показать T2/T3.
    pool10 = [
        {"name": "exact", "interests": ["dota2"], "open": True, "langs": ["en"], "vibe": "calm"},
        {"name": "family", "interests": ["lol"], "open": True, "langs": ["en"], "vibe": "calm"},
        {"name": "adjacent", "interests": ["coffee"], "open": True, "langs": ["en"], "vibe": "calm"},
    ]
    base_intent = lambda ep: {"type": "games", "topics": ["dota2"], "mode": "online", "version": 1, "expansion_policy": ep}
    names = lambda res: [x["name"] for x in res["slate"]]
    r_exact = P.run_search(base_intent("exact_only"), me, pool10, cfg, now=1.0, search_id="e1")
    r_family = P.run_search(base_intent("allow_family"), me, pool10, cfg, now=1.0, search_id="e2")
    check("P10 exact_only: показан только exact T1 (T2/T3 в пуле, но НЕ презентованы)",
          "exact" in names(r_exact) and "family" not in names(r_exact))
    check("P10 exact_only: present_gated > 0 (retrieval-eligible, но не presentable)", r_exact["prefilter"]["present_gated"] >= 1)
    check("P10 allow_family: T2 (family) презентован", "family" in names(r_family))
    # три разрешения различимы (по уровням политики)
    check("P10 may_present T2: нет при exact_only, есть при allow_family",
          (not P.may_present("T2", base_intent("exact_only"))) and P.may_present("T2", base_intent("allow_family")))
    check("P10 may_present T3: нет при allow_family, есть при allow_adjacent",
          (not P.may_present("T3", base_intent("allow_family"))) and P.may_present("T3", base_intent("allow_adjacent_after_confirmation")))
    check("P10 may_present T4: только при event_fallback_allowed",
          (not P.may_present("T4", base_intent("allow_adjacent_after_confirmation"))) and P.may_present("T4", base_intent("event_fallback_allowed")))
    pl = P.permission_layers("T3", base_intent("exact_only"), "discovery_only")
    check("P10 три слоя различны: retrieval_eligible=True, present=False, outreach=False",
          pl["retrieval_eligible"] and (not pl["present_permission"]) and (not pl["outreach_permission"]))

    # ---- Аудит P1#11: readiness больше не primary в сортировке ----
    from matching_core.allocation import allocation as AL11

    def _al_item(name, dclass, readiness, rec):
        return {"cand": {"name": name}, "decision_class": dclass, "readiness": readiness, "reciprocal": rec,
                "lcb": 0.7, "coverage": 0.7, "bucket": "b", "policy": "ALLOW", "tier": "T1"}
    ranked11 = AL11.rerank([_al_item("open_weak", "no_outreach", "open_now", 0.3),
                            _al_item("busy_strong", "strong_personal", "busy", 0.9)], {}, ctx={})
    o11 = [x["cand"]["name"] for x in ranked11]
    check("P11 качество (strong_personal, busy) ВЫШЕ open_now/no_outreach", o11.index("busy_strong") < o11.index("open_weak"))
    r2 = AL11.rerank([_al_item("a1", "usable_personal", "busy", 0.8),
                      _al_item("a2", "usable_personal", "open_now", 0.8)], {}, ctx={})
    o2 = [x["cand"]["name"] for x in r2]
    check("P11 при равном качестве+reciprocal readiness — лишь тай-брейк (open_now раньше busy)", o2.index("a2") < o2.index("a1"))
    check("P11 DCLASS_RANK: strong_personal < no_outreach", AL11.DCLASS_RANK["strong_personal"] < AL11.DCLASS_RANK["no_outreach"])

    # ---- Аудит P1#12: quality floor для exploration ----
    ee = AL11.exploration_eligible
    check("P12 floor: выше min lcb+coverage -> eligible",
          ee({"lcb": 0.8, "coverage": 0.8, "decision_class": "discovery_only"}, 0.5, 0.5) is True)
    check("P12 floor: ниже min relevance -> НЕ eligible",
          ee({"lcb": 0.2, "coverage": 0.8, "decision_class": "discovery_only"}, 0.5, 0.5) is False)
    check("P12 floor: ниже min coverage -> НЕ eligible",
          ee({"lcb": 0.8, "coverage": 0.2, "decision_class": "discovery_only"}, 0.5, 0.5) is False)
    check("P12 floor: no_outreach -> НЕ eligible (не обходит consent/policy)",
          ee({"lcb": 0.9, "coverage": 0.9, "decision_class": "no_outreach"}, 0.5, 0.5) is False)
    # review#E (tautology-фикс): проверяем ПОВЕДЕНИЕ дефолтного floor (0.4), а не hasattr; доменный floor
    # переопределяет через ctx в pipeline.run_search.
    check("P12 дефолтный floor=0.4 реально применяется (не просто определён)",
          AL11.EXPLORATION_MIN_LCB == 0.4 and AL11.EXPLORATION_MIN_COVERAGE == 0.4
          and AL11.exploration_eligible({"lcb": 0.5, "coverage": 0.5, "decision_class": "discovery_only"}) is True
          and AL11.exploration_eligible({"lcb": 0.3, "coverage": 0.5, "decision_class": "discovery_only"}) is False)
    # review#C/#E: exploration теперь РЕАЛЬНО срабатывает через РЕЗЕРВ слотов (main_cap = TOP_N - QUOTA).
    # 8 свежих (zero-exposure) кандидатов, разные bucket/tier (проходят diversity-caps): главный цикл берёт 6,
    # exploration добирает 2 зарезервированных; sub-floor 'low' НЕ exploration-flagged (floor). non-vacuous.
    expl_pool = []
    for i in range(8):
        it = _al_item("fresh%d" % i, "discovery_only", "open_now", 0.6)
        it["bucket"] = "bf%d" % i; it["tier"] = "T%d" % (i % 4); it["source"] = i   # разные diversity-оси
        it["lcb"] = 0.7; it["coverage"] = 0.7
        expl_pool.append(it)
    low = _al_item("low", "discovery_only", "open_now", 0.6)
    low["bucket"] = "blow"; low["tier"] = "T0"; low["source"] = 99; low["lcb"] = 0.2; low["coverage"] = 0.2
    expl_pool.append(low)
    rz = AL11.rerank(expl_pool, {}, ctx={"exploration_min_lcb": 0.5, "exploration_min_coverage": 0.5})
    flagged = [x for x in rz if x.get("allocation", {}).get("exploration")]
    check("P12 exploration РЕАЛЬНО срабатывает (path не dead-code)", len(flagged) >= 1)
    check("P12 все exploration-кандидаты проходят floor (non-vacuous)",
          flagged and all(AL11.exploration_eligible(x, 0.5, 0.5) for x in flagged))
    check("P12 sub-floor кандидат НЕ exploration-flagged",
          "low" not in [y["cand"]["name"] for y in flagged])

    # ---- Аудит P1#13: field-specific hard-confidence (не один 0.6) ----
    from matching_core.intent_compiler import compiler as CO13
    lc = CO13.low_confidence_hard_fields
    check("P13 dating (explicit-only) inferred@0.9 -> всё равно уточнение",
          "dating_mode" in lc({"type": {"source": "inferred", "confidence": 0.9}}, ["dating_mode"]))
    check("P13 dating explicit@0.5 -> ок",
          "dating_mode" not in lc({"type": {"source": "explicit", "confidence": 0.5}}, ["dating_mode"]))
    check("P13 format inferred@0.7 (<0.8) -> уточнение",
          "format" in lc({"format": {"source": "inferred", "confidence": 0.7}}, ["format"]))
    check("P13 format inferred@0.85 (>=0.8) -> ок",
          "format" not in lc({"format": {"source": "inferred", "confidence": 0.85}}, ["format"]))
    check("P13 activity subtype inferred@0.7 (>=0.65) -> ок",
          "activity" not in lc({"activity": {"source": "inferred", "confidence": 0.7}}, ["activity"]))
    check("P13 requiredLanguages inferred@0.7 (<0.8) -> уточнение",
          "requiredLanguages" in lc({"requiredLanguages": {"source": "inferred", "confidence": 0.7}}, ["requiredLanguages"]))
    check("P13 explicit@0.3 всегда ок",
          "requiredLanguages" not in lc({"requiredLanguages": {"source": "explicit", "confidence": 0.3}}, ["requiredLanguages"]))
    check("P13 правила field-specific (dating=explicit, format=0.8, activity=0.65)",
          CO13.FIELD_CONFIDENCE_RULE["dating_mode"] == "explicit" and CO13.FIELD_CONFIDENCE_RULE["format"] == 0.8
          and CO13.FIELD_CONFIDENCE_RULE["activity"] == 0.65)

    # ---- Аудит P1#14: один вопрос ЗА TURN (не один за весь pre-search) ----
    from matching_core.intent_compiler import clarification as CL
    missing3 = ["required_language", "time_window", "area"]   # P0 + P1 + P1 (три обязательных unknown)
    # 1) за один turn — ровно один вопрос (mandatory P0 первым)
    q1 = CL.next_question_turn(missing3)
    check("P14 один вопрос за turn (P0 mandatory первым)", q1 is not None and q1["key"] == "required_language" and q1["klass"] == "P0")
    # 2) после ответа на первый — следующий (не тот же)
    q2 = CL.next_question_turn(missing3, answered={"required_language"})
    check("P14 после ответа — следующий вопрос (не повтор)", q2 is not None and q2["key"] != "required_language")
    # 3) все три разрешаются за три turn'а (по одному), а не «один за весь flow»
    seq = CL.clarification_sequence(missing3)
    keys = [q["key"] for q in seq]
    check("P14 три обязательных unknown -> три вопроса (по одному за turn)", len(seq) == 3 and set(keys) == set(missing3))
    check("P14 порядок: P0 раньше P1", keys[0] == "required_language")
    # 4) когда всё отвечено -> None (можно запускать поиск)
    check("P14 всё покрыто -> вопросов нет", CL.next_question_turn(missing3, answered=set(missing3)) is None)

    # ---- Аудит P1#15: один lifecycle source of truth ----
    from matching_core.orchestrator import state_machines as SM15
    from matching_core.contracts import intent as IC15
    check("P15 набор состояний единый (machine == intent.LIFECYCLE_STATES)",
          set(SM15.MACHINES["intent_lifecycle"].keys()) == set(IC15.LIFECYCLE_STATES))
    check("P15 lifecycle_state — read-only проекция (маркер)", IC15.LIFECYCLE_STATE_IS_PROJECTION is True)
    it15 = IC15.build_intent("i", "u", "games", topics=["x"])
    it15b = SM15.advance_intent_lifecycle(it15, "searching")
    check("P15 транзиция через авторитетный автомат: active->searching", IC15.lifecycle_state(it15b) == "searching")
    check("P15 проекция не мутирует исходный intent", IC15.lifecycle_state(it15) == "active")
    try:
        SM15.advance_intent_lifecycle(IC15.build_intent("i", "u", "games", topics=["x"]), "completed"); bad15 = False
    except SM15.InvalidTransition:
        bad15 = True
    check("P15 невалидная транзиция (active->completed) -> InvalidTransition", bad15)
    exp15 = IC15.build_intent("i", "u", "games", topics=["x"], created_at=0, expires_at=100)
    check("P15 TTL-overlay в проекции: истёкший -> expired", IC15.lifecycle_state(exp15, now=200) == "expired")

    # ---- Аудит P1#16: decision trace обязателен в production ----
    pool16 = [{"name": "t16", "interests": ["dota2"], "intents": [{"topics": ["dota2"]}], "open": True, "langs": ["en"], "vibe": "calm"}]
    gi16 = {"type": "games", "topics": ["dota2"], "mode": "online", "version": 1}
    # production без trace_log -> trace создаётся автоматически (обязателен)
    r_prod = P.run_search(gi16, me, pool16, cfg, now=1.0, search_id="t16")   # mode=production по умолчанию
    check("P16 production auto-создаёт decision trace (>0)", r_prod["mode"] == "production" and r_prod["traces"] >= 1)
    # benchmark-режим -> trace можно НЕ создавать (0)
    r_bench = P.run_search(gi16, me, pool16, cfg, now=1.0, search_id="t16b", mode="benchmark")
    check("P16 benchmark-режим: trace отключаем (0)", r_bench["mode"] == "benchmark" and r_bench["traces"] == 0)
    # переданный trace_log используется в production
    tl16 = OB.TraceLog()
    r_ext = P.run_search(gi16, me, pool16, cfg, now=1.0, search_id="t16e", trace_log=tl16)
    check("P16 переданный trace_log наполняется", len(tl16.all()) >= 1 and r_ext["traces"] >= 1)

    print("\nАудит P0(1-9)+P1(10-16): %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
