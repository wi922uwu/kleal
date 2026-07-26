# -*- coding: utf-8 -*-
"""Аудит P0#1 — Authoritative end-to-end orchestrator.

ЕДИНЫЙ production entrypoint для поиска. Все production-flows проходят через `run_search`; порядок
обязательных стадий фиксирован (`SEARCH_STAGES`) и трассируется, а `_Run.enforce` гарантирует, что ни
одна стадия не пропущена (fail-closed). Публичный `orchestrator.search.search()` делегирует сюда, поэтому
нельзя случайно «обойти» защитный/продуктовый слой в другом flow.

Стадии (Аудит §1):
  intent_snapshot → pre_policy → retrieval → typed_relevance → reciprocity → readiness → allocation →
  expansion_decision → presentation      (поиск)
  proposal_authorization → revalidation → transaction → plan   (outreach — отдельные entrypoints ниже)

Отдельные пункты аудита (2,3,5,6,8,9,16) ужесточают КОНКРЕТНЫЕ стадии внутри этого оркестратора —
но сама точка входа и «no-bypass» контракт задаются здесь.
"""
from ..policy_engine import engine as POL
from ..policy_engine.engine import ALLOW, BLOCK, REVIEW
from ..retrieval import retriever as RET
from ..feature_builder import builder as FB
from ..feature_builder import unknowns as UNK
from ..relevance_engine import relevance as RL, decision as DE
from ..reciprocity_readiness import readiness as RD
from ..reciprocity_readiness import reciprocity as RC
from ..allocation import allocation as AL
from ..contracts import decision_trace as DT
from ..policy_engine import revalidation as REV
from ..observability import trace as OB
from . import expansion as EX

# Фиксированный порядок обязательных стадий поиска. Изменение порядка/состава — осознанное решение.
SEARCH_STAGES = ("intent_snapshot", "pre_policy", "retrieval", "typed_relevance", "reciprocity",
                 "readiness", "allocation", "expansion_decision", "presentation")
# Стадии outreach/транзакции — отдельные entrypoints ЭТОГО ЖЕ оркестратора (см. authorize_and_send/commit_*).
OUTREACH_STAGES = ("proposal_authorization", "revalidation", "transaction", "plan")

_TYPE2DOMAIN = {"social": "social_meet", "social_meet": "social_meet", "walk": "walk",
                "games": "games", "gaming": "games", "sport": "sport_activity",
                "sport_activity": "sport_activity", "networking": "professional_networking",
                "language": "language_exchange", "language_exchange": "language_exchange",
                "dating": "dating", "culture": "culture_event", "watch": "watch_together",
                "coworking": "coworking"}


class PipelineError(Exception):
    """Fail-closed: нарушение контракта оркестратора (пропущенная стадия / отсутствующий snapshot и т.п.)."""


# Аудит #7 — токен авторизации dating. Его держит ТОЛЬКО `run_dating_search`; generic `run_search`
# отказывается исполнять dating-intent без этого токена (нельзя обойти dating-контур).
_DATING_AUTH = object()


# Аудит P0#2 — purpose выводится ТОЛЬКО из confirmed intent snapshot (type/purpose), не из аргумента.
_TYPE2PURPOSE = {"dating": "dating", "games": "games", "gaming": "games", "sport": "sport",
                 "sport_activity": "sport", "networking": "networking",
                 "professional_networking": "networking", "language": "language",
                 "language_exchange": "language", "social": "friendship", "social_meet": "friendship",
                 "walk": "friendship", "culture": "friendship", "culture_event": "friendship",
                 "watch": "friendship", "watch_together": "friendship", "coworking": "networking"}


def purpose_of(intent):
    """Аудит #2: purpose из immutable intent snapshot (явный intent.purpose > маппинг type). None если не выводится."""
    p = intent.get("purpose")
    if p:
        return str(p).lower()
    return _TYPE2PURPOSE.get(str(intent.get("type") or "").lower())


def broad_consent_of(intent):
    """Аудит #2: broad_consent берётся из consent snapshot интента (fallback.consent.broad_matching), не из аргумента."""
    return bool(((intent.get("fallback") or {}).get("consent") or {}).get("broad_matching"))


# Аудит #10 — ТРИ разных разрешения: retrieval eligibility ≠ present-as-fallback ≠ outreach.
# present-permission по expansion_policy: exact_only=0 · allow_family=1 · allow_adjacent=2 · event_fallback=3.
_POLICY_RANK = {"exact_only": 0, "allow_family": 1, "allow_adjacent_after_confirmation": 2, "event_fallback_allowed": 3}
_TIER_PRESENT_MIN = {"T0": 0, "T1": 0, "T2": 1, "T3": 2, "T4": 3}   # какой минимум политики нужен, чтобы ПОКАЗАТЬ tier


def may_present(tier, intent):
    """Аудит #10: разрешено ли ПОКАЗАТЬ tier как fallback (не «попал в retrieval-пул», а «можно презентовать»).
    exact_only не показывает T2/T3, даже если они уже в пуле — «пользователь запросил exact» соблюдается."""
    from . import expansion as EX
    return _POLICY_RANK.get(EX.expansion_policy(intent), 1) >= _TIER_PRESENT_MIN.get(tier, 9)


def permission_layers(tier, intent, decision_class):
    """Аудит #10: три разрешения одним снимком (для трассировки/UI)."""
    return {"retrieval_eligible": tier in ("T0", "T1", "T2", "T3", "T4"),
            "present_permission": may_present(tier, intent),
            "outreach_permission": DE.is_personal(decision_class)}


class _Run:
    """Трекер одного прогона: фиксирует пройденные стадии; enforce() ловит пропуск обязательной стадии."""

    def __init__(self, search_id):
        self.search_id = search_id
        self.done = []

    def stage(self, name):
        self.done.append(name)
        return name

    def enforce(self, required):
        missing = [s for s in required if s not in self.done]
        if missing:
            raise PipelineError("pipeline bypass: mandatory stages skipped: %s" % missing)


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


# Аудит #6 — typed dispatch для T4. Нормализация kind (retriever) -> candidate_types.
_KIND_ALIASES = {"room": "online_room", "group": "ad_hoc_group"}


def _typed_eligibility(intent, cand, kind):
    from ..retrieval import candidate_types as CT
    if _KIND_ALIASES.get(kind, kind) == "event":
        return CT.event_eligibility(intent, cand)
    return "ALLOW", None


def _typed_relevance(intent, cand, kind):
    """Аудит #6: РЕЛЕВАНТНОСТЬ T4 считается СВОЕЙ typed-моделью, не person feature model. None -> нет
    typed-модели для этого kind (group = set-level слой, ещё не в live) -> кандидат исключается."""
    from ..retrieval import candidate_types as CT
    k = _KIND_ALIASES.get(kind, kind)
    if k == "event":
        return CT.user_event_relevance(intent, cand)
    if k == "online_room":
        return CT.session_relevance(intent, cand)
    if k == "venue":
        return CT.plan_suitability(intent, cand)
    return None                                   # ad_hoc_group / неизвестное -> исключаем (не person-модель)


def _typed_transaction(kind):
    from ..retrieval import candidate_types as CT
    try:
        return CT.candidate_transaction(_KIND_ALIASES.get(kind, kind))
    except ValueError:
        return {"transaction": "alternative", "explain_key": "explain.alternative"}


def typed_dispatch(intent, t4_labeled, *, limit=3):
    """Аудит #6: cross-type lane. T4-кандидаты скорятся своими typed-функциями и возвращаются ОТДЕЛЬНО
    от person top-N (а не подмешиваются в него). Некорректно person-моделью T4 больше не считается."""
    alts = []
    for r in t4_labeled:
        c = r["cand"]; kind = str(c.get("kind") or "").lower()
        elig, _why = _typed_eligibility(intent, c, kind)
        if elig != "ALLOW":
            continue
        rel = _typed_relevance(intent, c, kind)
        if rel is None:
            continue                              # нет typed-модели -> исключаем, НЕ person-скорим (аудит #6)
        txn = _typed_transaction(kind)
        alts.append({"name": c.get("name") or c.get("id"), "kind": kind, "tier": "T4",
                     "typed_relevance": rel, "transaction": txn["transaction"],
                     "explain_key": txn["explain_key"], "decision_class": "discovery_only",
                     "note": "alternative way to close intent (typed model, not person scoring)"})
    alts.sort(key=lambda x: -x["typed_relevance"])
    return alts[:limit]


def run_search(intent, prof, pool, cfg, *, now, search_id, purpose=None, gate_ctx=None,
               broad_consent=None, budget=80, trace_log=None, _dating_authorized=None, mode="production"):
    """Аудит P0#1/#2/#7 — единственный авторитетный проход поиска. `now` и `search_id` ОБЯЗАТЕЛЬНЫ;
    purpose/broad_consent берутся из confirmed intent snapshot; рассинхрон аргумента и snapshot →
    fail-closed. dating-intent через generic search (без dating-обёртки) ЗАПРЕЩЁН. Возвращает
    {slate, alternatives, stages, search_id, purpose, domain, prefilter}."""
    # ---- Аудит #2: contract enforcement ДО любой работы (fail-closed) ----
    if now is None:
        raise PipelineError("now (injected clock) is mandatory (Audit #2)")
    if not search_id or not str(search_id).strip():
        raise PipelineError("search_id (unique run id) is mandatory (Audit #2)")
    snap_purpose = purpose_of(intent)
    if not snap_purpose:
        raise PipelineError("confirmed intent has no derivable purpose (Audit #2)")
    if purpose is not None and str(purpose).lower() != snap_purpose:
        raise PipelineError("purpose arg %r != intent snapshot purpose %r — fail-closed (Audit #2)"
                            % (purpose, snap_purpose))
    purpose = snap_purpose
    snap_bc = broad_consent_of(intent)
    if broad_consent is not None and bool(broad_consent) != snap_bc:
        raise PipelineError("broad_consent arg %r != intent snapshot consent %r — fail-closed (Audit #2)"
                            % (broad_consent, snap_bc))
    broad_consent = snap_bc
    # Аудит #7 (+review#B): dating нельзя запускать через generic search в обход dating-обёртки. Гейт
    # срабатывает по ЛЮБОМУ признаку dating — derived purpose ИЛИ domain (иначе intent {type:dating,
    # purpose:friendship} обошёл бы гейт по purpose, но всё равно шёл бы в dating-домен). fail-closed.
    if (purpose == "dating" or domain_of(intent) == "dating") and _dating_authorized is not _DATING_AUTH:
        raise PipelineError("dating search must go through run_dating_search (consent → target-pref → "
                            "capsule → bilateral gates → stricter limits), not generic search — fail-closed (Audit #7)")
    # Аудит #16: decision trace ОБЯЗАТЕЛЕН в production (поиск ведёт к человеку/proposal). Auto-create,
    # если не передан; отключить (trace_log=None) можно ТОЛЬКО в benchmark/test-режиме.
    if trace_log is None and mode == "production":
        trace_log = OB.TraceLog()
    if trace_log is None and mode not in ("benchmark", "test"):
        raise PipelineError("decision trace is mandatory in production (Audit #16): pass trace_log or mode='benchmark'")

    run = _Run(search_id)

    # 1. intent_snapshot — зафиксировать домен/конфиг/purpose-snapshot (contract enforced выше, Аудит #2)
    run.stage("intent_snapshot")
    domain = domain_of(intent)
    dom_cfg = cfg["domains"].get(domain) or cfg["domains"]["social_meet"]
    priors = RL.priors_from_config(cfg)
    bands = cfg["user_facing_bands"]
    ctx = dict(gate_ctx or {}); ctx.setdefault("blocked", set()); ctx.setdefault("received24", {})
    ctx["domain_cfg"] = dom_cfg
    snapshot = POL.prepare_snapshot(prof.get("name", "me"), purpose, config_version=cfg.get("config_version"))

    # 2. pre_policy — Аудит #3: cheap hard-eligibility prefilter по ВСЕМУ пулу ДО budget truncation.
    run.stage("pre_policy")
    eligible_pool, prefilter_stats = POL.hard_prefilter(intent, pool, ctx)

    # 3. retrieval — tier-провенанс + бюджет ПОСЛЕ префильтра (budget режет уже допустимый пул)
    run.stage("retrieval")
    labeled = RET.retrieve(intent, eligible_pool, budget=budget)

    # Аудит #6: T4 (event/room/venue/group) НЕ идёт в person feature model — отдельная typed-дорожка.
    t4_labeled = [r for r in labeled if r["tier"] == "T4"]
    person_labeled = [r for r in labeled if r["tier"] != "T4"]

    scored = []
    present_gated = 0
    for r in person_labeled:
        c = r["cand"]
        # policy.evaluate (BLOCK → не скорится/не показывается; REVIEW-семантику фиксирует Аудит #8)
        verdict = POL.evaluate(intent, c, ctx)
        if verdict["decision"] == BLOCK:
            continue
        # Аудит #10: retrieval-eligible ≠ permission-to-present. exact_only не показывает T2/T3 из пула.
        if not may_present(r["tier"], intent):
            present_gated += 1
            continue
        # 4. typed_relevance (Аудит #6 добавит typed dispatch по kind; пока — person-модель)
        F_ab = FB.build_features(intent, prof, c, domain)
        d_ab = RL.directional_score(F_ab, dom_cfg, priors)
        d_ba = RL.directional_score(_reverse_features(intent, prof, c, domain), dom_cfg, priors)
        # 5. reciprocity — Аудит #5: reciprocity_view вместо голой §9.4-формулы. Активная взаимность
        # (встречный active intent) и пассивный interest fit считаются РАЗНО; для пассива обратная сторона
        # берётся из mean_b (не lcb_b), чтобы неизвестность не штрафовалась дважды поверх R_lcb.
        cls = RC.classify_reciprocity(intent, c)
        rv = RC.reciprocity_view(d_ab, d_ba, active_counter_intent=cls["active_reciprocity"])
        rec = rv["value"]
        # 6. readiness
        readiness = RD.readiness_state(c, domain, now, cfg,
                                       ctx["received24"].get(str(c.get("name", "")).strip().lower(), 0))
        crit_unknown = UNK.high_impact_unknown(F_ab, intent, domain)
        band = DE.band(d_ab["lcb"], d_ab["coverage"], bands)
        dclass = DE.decision_class(d_ab["lcb"], d_ab["coverage"], r["tier"], dom_cfg,
                                   policy=verdict["decision"], broad_consent=broad_consent,
                                   high_impact_unknown=crit_unknown)
        # Аудит #8: fail-closed семантика policy. BLOCK уже отсеян выше. REVIEW → НИКОГДА personal outreach;
        # допустима только quarantined discovery / manual review. ALLOW → обычный decision_class.
        quarantined = False
        if verdict["decision"] == REVIEW:
            dclass = "discovery_only"
            quarantined = True
        if DE.is_personal(dclass) and verdict["decision"] != ALLOW:
            raise PipelineError("policy semantics violated: personal outreach on non-ALLOW verdict (Audit #8)")
        pres = DE.presentation(F_ab, dom_cfg)
        sem = F_ab["semantic_activity"]
        bucket = sem[2].split(", ")[0] if (sem[0] == FB.K_MATCH and sem[2]) else None
        scored.append({"cand": c, "tier": r["tier"], "source": r["source"], "reciprocal": rec,
                       "reciprocity_kind": rv["kind"], "uncertainty": rv["uncertainty"],
                       "lcb": d_ab["lcb"], "coverage": d_ab["coverage"], "readiness": readiness,
                       "bucket": bucket or (c.get("interests") or ["other"])[0], "policy": verdict["decision"],
                       "band": band, "band_label": DE.BAND_LABELS[band][1], "decision_class": dclass,
                       "quarantined": quarantined, "reasons": pres["reasons_en"], "gap": pres["gap_en"],
                       "low_coverage": DE.low_coverage(d_ab["coverage"], dom_cfg),
                       "revalidation_baseline": REV.capture_baseline(c, intent)})  # Аудит #9: baseline для before_send
        if trace_log is not None:                    # Аудит #16 сделает trace обязательным в production
            trace_log.log(DT.build_decision_trace(
                search_id, str(c.get("name", "")), intent_version=(intent.get("version") or 1),
                purpose_id=purpose, policy={"decision": verdict["decision"], "version": verdict["policy_version"]},
                semantic_tier=r["tier"], directional={"a_to_b": d_ab, "b_to_a": d_ba},
                reciprocal_relevance=rec, readiness=readiness, reason_keys=pres["reasons_en"],
                config_version=cfg.get("config_version")))
    # Аудит #6: T4 — своя typed-модель, отдельная cross-type lane (не в person top-N).
    # Аудит #10: T4 презентуется только если expansion_policy разрешает event-fallback.
    alternatives = typed_dispatch(intent, t4_labeled) if may_present("T4", intent) else []
    run.stage("typed_relevance"); run.stage("reciprocity"); run.stage("readiness")

    # 7. allocation (только person-кандидаты; T4 не подмешивается)
    run.stage("allocation")
    ctx["exploration_min_lcb"] = float(dom_cfg["discovery_min_lcb"])          # Аудит #12: exploration floor = доменный
    ctx["exploration_min_coverage"] = float(dom_cfg["discovery_min_coverage"])
    ranked = AL.rerank(scored, intent, cfg, ctx)

    # 8. expansion_decision (Аудит #10 разведёт retrieval-eligibility vs present-as-fallback vs outreach)
    run.stage("expansion_decision")

    # 9. presentation — прозрачный slate (§9.7): band + причины + gap, без процентов
    run.stage("presentation")
    slate = [{"name": s["cand"].get("name"), "tier": s["tier"], "band": s["band"], "band_label": s["band_label"],
              "decision_class": s["decision_class"], "readiness": s["readiness"], "reciprocal": s["reciprocal"],
              "reciprocity_kind": s["reciprocity_kind"], "uncertainty": s["uncertainty"],
              "reasons": s["reasons"], "gap": s["gap"], "low_coverage": s["low_coverage"],
              "policy": s["policy"], "quarantined": s.get("quarantined", False),
              "revalidation_baseline": s["revalidation_baseline"],
              "allocation": s.get("allocation")} for s in ranked]

    run.enforce(SEARCH_STAGES)                       # no-bypass: все обязательные стадии пройдены
    prefilter_stats = dict(prefilter_stats); prefilter_stats["present_gated"] = present_gated  # Аудит #10
    return {"slate": slate, "alternatives": alternatives, "stages": run.done, "search_id": search_id,
            "purpose": purpose, "domain": domain, "prefilter": prefilter_stats,
            "expansion_policy": EX.expansion_policy(intent), "mode": mode,
            "traces": (len(trace_log.all()) if trace_log is not None else 0)}


def run_dating_search(user, intent, prof, pool, cfg, *, now, search_id, consents=None, gate_ctx=None,
                      budget=80, trace_log=None, mode="production"):
    """Аудит #7 — ЕДИНСТВЕННЫЙ санкционированный путь для dating. Контур:
    dating consent → target preference validation → dating capsule → bilateral preference gates →
    stricter limits → generic safe primitives (с токеном авторизации). Обойти его generic-поиском нельзя."""
    from ..dating import dating as DAT
    if purpose_of(intent) != "dating":
        raise PipelineError("run_dating_search вызван с не-dating intent (Audit #7)")
    # 1. dating consent (opt-in + target_preferences_confirmed + 18+)
    ok, why = DAT.consent_gate(user, intent)
    if not ok:
        raise PipelineError("dating consent failed: %s (Audit #7)" % why)
    # 2. target preference validation
    if not user.get("target_preferences_confirmed"):
        raise PipelineError("dating target preferences not confirmed (Audit #7)")
    # 3. dating capsule (purpose-bound view, sensitive-минимизация, no auto-accept)
    capsule = DAT.build_dating_capsule(user, consents=consents)
    # 4. bilateral preference gate — взаимная проверка предпочтений A↔B (кандидаты без prefs проходят)
    a_prefs = user.get("target_preferences") or {}
    a_profile = {"gender": user.get("gender"), "age": user.get("age"), "langs": user.get("langs")}
    gated = [c for c in (pool or [])
             if DAT.mutual_preference_ok(a_prefs, a_profile, c.get("target_preferences") or {},
                                         {"gender": c.get("gender"), "age": c.get("age"), "langs": c.get("langs")})[0]]
    # 5. stricter limits — dating rate limits дают более узкий budget
    dl = DAT.dating_rate_limits()
    strict_budget = min(int(budget), max(8, int(dl.get("proposals_per_24h", 2)) * 4))
    # 6. generic safe primitives С токеном авторизации dating
    res = run_search(intent, prof, gated, cfg, now=now, search_id=search_id, gate_ctx=gate_ctx,
                     budget=strict_budget, trace_log=trace_log, _dating_authorized=_DATING_AUTH, mode=mode)
    res["dating"] = {"capsule_sensitive_minimized": capsule.get("sensitive_minimized"),
                     "auto_accept": capsule.get("auto_accept"), "rate_limits": dl,
                     "bilateral_gated_pool": len(gated), "input_pool": len(pool or [])}
    return res


def authorize_and_send(*, candidate, intent, cfg, now, baseline=None, gate_ctx=None,
                       receiving_eligible=True, active_prefs_ok=True, within_limits=True,
                       requires_user_action=False, user_action_taken=False):
    """Аудит #9 — outreach entrypoint (стадии proposal_authorization → revalidation → transaction).
    Между search и «Send invite» кандидат мог измениться (pause / privacy / block / receiving policy /
    другой план / исчерпанная capacity). Порядок:
      1) proposal authorization — ДЕТЕРМИНИРОВАННОЕ решение (receiving/readiness/purpose/prefs/limits/policy);
      2) revalidation 'before_send' — САМЫЙ важный недостающий checkpoint (сверка с baseline + свежий policy);
      3) send — только если оба прошли. Иначе — предсказуемый код, а не молчаливая отправка (fail-closed)."""
    from . import agent_decision as AD
    domain = domain_of(intent)
    ctx = dict(gate_ctx or {}); ctx.setdefault("blocked", set()); ctx.setdefault("received24", {})

    # stage 1: proposal authorization (не LLM)
    verdict = POL.evaluate(intent, candidate, ctx)
    readiness = RD.readiness_state(candidate, domain, now, cfg,
                                   ctx["received24"].get(str(candidate.get("name", "")).strip().lower(), 0))
    auth = AD.can_reach_candidate(receiving_eligible=receiving_eligible, readiness=readiness,
                                  purpose_ok=(verdict["decision"] == ALLOW), active_prefs_ok=active_prefs_ok,
                                  within_limits=within_limits, deterministic_policy=verdict["decision"],
                                  requires_explicit_user_action=requires_user_action,
                                  user_action_taken=user_action_taken)
    if not auth["allowed"]:
        return {"sent": False, "stage": "proposal_authorization",
                "code": "USER_ACTION_REQUIRED" if auth["requires_user_action"] else "NOT_AUTHORIZED",
                "blockers": auth["blockers"]}

    # stage 2: revalidation 'before_send' — Аудит #9 (самый важный недостающий checkpoint)
    if baseline is None:
        baseline = REV.capture_baseline(candidate, intent)
    rv = REV.revalidate(baseline, candidate, intent, ctx, checkpoint="before_send")
    if not rv["ok"]:
        return {"sent": False, "stage": "revalidation_before_send", "code": rv["code"],
                "changed": rv["changed"], "decision": rv["decision"]}

    # stage 3: authorized + revalidated -> send
    return {"sent": True, "stage": "transaction", "code": "SENT", "checkpoint": "before_send"}
