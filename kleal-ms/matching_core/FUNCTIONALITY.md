# Matching Core — полный функционал (как есть сейчас)

> **Важно про честность охвата.** Ниже явно разделено: **[в пайплайне]** — модули, которые реально вызывает
> `search()` (живой ранкинг); **[отдельный слой]** — реализованные, юнит-тестируемые, вызываемые модули,
> которые в единый `search()`-цикл пока не встроены (работают на других стадиях: сборка интента, транзакции,
> fallback, группы, dating, safety, feedback). Оба вида — рабочий код, но это разные стадии.

---

## 1. Архитектура: шесть независимых слоёв

Нет единого «FinalUtility». Оценка кандидата раскладывается на независимые слои, которые НЕ складываются в
одно число:

1. **Eligibility / policy** — детерминированные гейты ДО скоринга.
2. **Retrieval** — кандидаты + иммутабельный semantic tier (провенанс).
3. **Relevance** — направленная релевантность (эвристика 0..1, не «процент»).
4. **Reciprocity / readiness** — взаимность и готовность принимать сейчас (отдельно от релевантности).
5. **Allocation** — справедливость/разнообразие/экспозиция ПОСЛЕ eligibility+relevance.
6. **Transaction / presentation** — state-machines, транзакции, прозрачная выдача, decision trace.

### Карта модулей
| Пакет | Модули | Отвечает за |
|---|---|---|
| `contracts/` | evidence, profile, intent, proposal, reservation, match, group, plan, relationship_edge, candidate, decision_trace, receiving_policy, time_algebra, geo_privacy | Канонические структуры данных (§4) |
| `intent_compiler/` | compiler, clarification | Компиляция недоверенного ввода в canonical intent (§5) |
| `taxonomy/` | graph, canonical, governance | Смысловые отношения тем/ролей/языков (§6) |
| `retrieval/` | retriever, candidate_types | Отбор кандидатов + tiers (§7), типы event/room/venue (§16) |
| `policy_engine/` | gates, engine, revalidation, trust_safety | Гейты, tri-state, повторная валидация, trust&safety (§8, §25) |
| `feature_builder/` | builder, unknowns | 7 групп × 4 состояния, классы неизвестности (§6.1/§9.1, #8) |
| `relevance_engine/` | relevance, decision | R_mean/Coverage/R_lcb, band/decision_class (§9) |
| `reciprocity_readiness/` | readiness, reciprocity, fatigue | Готовность, активная/пассивная взаимность, перегрузка (§10, #5/6/17) |
| `allocation/` | allocation | rerank, diversity, exposure, rotation (§11) |
| `orchestrator/` | search, expansion, protocol, state_machines, concurrency, transitions, agent_decision, intent_set | Сборка пайплайна, расширение, протокол, транзакции (§12–§14, B.1/B.2) |
| `group_formation/` | constraints, utility, former | Формирование группы как множества (§15) |
| `dating/` | dating | Изолированный dating-контур (§17) |
| `feedback_learning/` | feedback, reasons | Outcome-таксономия, reason codes (§19, #18) |
| `observability/` | trace | Иммутабельный decision-trace log + replay (§21) |
| `plan_coordination/` | plans | Координация плана с version-check (§14/§21.2) |
| `config/` | validator | sha-pinned загрузка + валидация конфига (§9.5) |

---

## 2. Живой пайплайн `search()` (Приложение B.1)

`search(intent, prof, pool, cfg, *, purpose="friendship", now=0.0, gate_ctx=None, broad_consent=False, budget=80, trace_log=None, search_id="srch")`

Порядок (детерминированный, без LLM):
1. `domain_of(intent)` → один из 10 доменов; берётся `dom_cfg` + priors + bands из конфига.
2. `policy_engine.prepare_snapshot(...)` — снимок политики/версий.
3. **[в пайплайне]** `retriever.retrieve(intent, pool, budget)` — метит каждого кандидата source + **иммутабельным tier**, отбрасывает `T5`, режет бюджетом.
4. Для каждого кандидата: `policy_engine.evaluate(...)` — если **BLOCK**, кандидат не скорится и не показывается.
5. **[в пайплайне]** `feature_builder.build_features(A→B)` и обратные фичи `B→A`.
6. **[в пайплайне]** `relevance.directional_score` (A→B и B→A) + `relevance.reciprocal`.
7. **[в пайплайне]** `feature_builder.unknowns.high_impact_unknown(...)` — критичный unknown → в `decision_class`.
8. **[в пайплайне]** `readiness.readiness_state(...)`.
9. **[в пайплайне]** `decision.band`, `decision.decision_class`, `decision.presentation`, `decision.low_coverage`.
10. **[в пайплайне]** `allocation.rerank(...)` — diversity/fairness/exposure, top-8.
11. **[в пайплайне]** `decision_trace.build_decision_trace(...)` в `trace_log` (если передан).

Возврат: прозрачный slate — `name, tier, band, band_label, decision_class, readiness, reciprocal, reasons,
gap, low_coverage, policy, allocation`. **Без процентов совместимости.**

---

## 3. Контракты данных (§4)

- **Evidence** (`contracts/evidence.py`): объект факта с `evidence_id`, приоритет источника (`SOURCE_PRIORITY` — 7 уровней), freshness, sensitivity, allowed_purposes, visibility. `dedup`, `resolve_field` (побеждает высший приоритет), `usable_for_purpose`.
- **UserProfile / ProfileView** (`contracts/profile.py`): профиль + **purpose-bound проекция** (`build_profile_view(user, purpose, disclosure_stage, consents)`) по Приложению D (purpose binding), `age_band` (диапазон вместо точного возраста), whitelisting полей по purpose.
- **Intent** (`contracts/intent.py`): 11 блоков (`INTENT_BLOCKS`), `flat()` для скоринга, `bump_version` (любое search-affecting изменение), `is_expired`, `minimal_intent_ok` (§5.3), **`LIFECYCLE_STATES` — 11 состояний**, `lifecycle_state(now)` (TTL→`expired`), `participates_in_ranking(now)` (в ранкинге только `active`/`searching`), поле `expansion_policy`.
- **Proposal / Reservation / Match / Plan / Group / RelationshipEdge / Candidate**: билдеры + статусы (`STATUS`, `PLAN_STATE`, `GROUP_STATE`, `EDGE_TYPES`), `is_expired`, `in_cooldown`. RelationshipEdge — advisory metadata, НЕ authoritative gate.
- **time_algebra** **[в пайплайне через гейт]**: `to_utc_min`, `windows_overlap(min_duration_min, a_tz, b_tz)` — UTC-нормализация окон + пересечение + длительность + DST через разные tz.
- **geo_privacy** **[отдельный слой]** (Вердикт#22): `distance_band` (клиенту — банда, не точное), `client_location_view(stage, plan_confirmed)` (точная точка только после согласованного плана), `live_location_in_discovery()→False`, `can_be_first_meeting_place` (домашний/рабочий адрес нельзя), `assert_no_exact_point_leak`.

---

## 4. Intent Compiler (§5) — [отдельный слой, стадия сборки интента]

`compiler.py`: LLM — только parser, его вывод недоверенный.
- `validate_schema` (типы слотов), `classify_constraints` (hard/soft/needs_confirm), `compile_intent(...)` → canonical draft intent.
- **Провенанс полей** (Вердикт#3): `field_provenance` помечает каждое поле `explicit | inferred | defaulted` + confidence; `compile_intent` сохраняет `raw_text` и `taxonomy_version` в самом интенте; `low_confidence_hard_fields` → обязательное уточнение при низкой уверенности по hard-полям (`HARD_CONFIDENCE_MIN = 0.6`).
- `blocking_clarifications(compiled, domain)` — незаполненные канонические hard-слоты блокируют запуск.

`clarification.py` (§5.2): классы вопросов P0–P3, `QUESTION_CATALOG` + rule-based приоритет (safety весит больше), `select_question` / `select_slot_question` (не более одного вопроса до результатов, кроме mandatory safety), `slots_catalog(domain)` из канонической таксономии.

---

## 5. Таксономия (§6)

- **`graph.py`** **[в пайплайне]** — основной резолвер тем при скоринге: seed `TAXONOMY` (6 broad × sub × слова), `SYNONYMS` (алиасы), `ADJACENCY`, `NEGATIVE_EDGES`, `COMPLEMENTARY_ROLES`. `similarity(topics, interests)` → уровень **4 exact/alias · 3 sibling · 2 parent · 1 adjacent · 0 none** + matched-набор. Off-taxonomy: литеральное совпадение → 4, префиксная морфо-близость → 2 (не фальшивый exact).
- **`canonical.py`** **[в пайплайне частично]** — каноническая таблица из xlsx, загружена в stdlib-json: **405 нод, 1204 алиаса (ru/en/es), 10 доменов со слотами**. Используется в: `intent_mode_isolation` (blocked_cross_purpose), `feature_builder` (complementary), `clarification` (slots). Функции: `resolve_node`, `similarity_nodes`, `purpose_blocked`, `is_complementary_nodes`, `slots_for_domain`, `hard_slots`. Это **аддитивное обогащение** поверх seed-графа (основной similarity в скоринге — `graph.similarity`).
- **`governance.py`** **[отдельный слой]** — каждое ребро имеет owner/version/review/evidence/rollback; `shadow_replay`, `add_alias` (не должен ломать существующую пару), `validate_governance`.

---

## 6. Retrieval + semantic tiers (§7) — [в пайплайне]

`retriever.py`:
- **`assign_tier(intent, cand)`** — tier из **происхождения, НЕ из score**:
  - **T0** — встречный активный intent кандидата + точное совпадение темы (реципрок);
  - **T1** — прямой интерес (точное совпадение) без встречного активного интента;
  - **T2** — родительская/родственная категория (similarity 2–3);
  - **T3** — смежный контекст (similarity 1);
  - **T4** — кандидат-НЕчеловек (`kind ∈ event/room/venue/group`) как альтернативный способ закрыть intent;
  - **T5** — пересечения нет (по умолчанию **не показывается**).
- `retrieve(...)` — метит source + tier, отбрасывает `T5` (`allowed_tiers` по умолчанию T0–T4), сортирует по приоритету источника, режет бюджетом.
- `retrieve_staged(...)` — 5-стадийный funnel со счётчиками (ANN помечен как no-op в stdlib-прототипе).
- `tier_analytics(...)` — распределение relevance ОТДЕЛЬНО внутри каждого tier.

`candidate_types.py` (§16) **[отдельный слой]**: модели `build_event/build_room/build_venue`, функции `event_eligibility`, `user_event_relevance`, `session_relevance`, `plan_suitability`, `candidate_transaction`. Юнит-тестировано; в person-скоринговый цикл `search()` пока не встроено (search присваивает T4 не-людям, но их type-specific relevance-функции внутри B.1 не вызывает).

---

## 7. Policy Engine (§8)

**`gates.py`** **[в пайплайне]** — 12 канонических гейтов ДО скоринга, tri-state **ALLOW / BLOCK / REVIEW**:
`account_status`, `mutual_block`, `safety_restrictions`, `privacy_visibility` (обе стороны + strict-unknown), `age_legal`, `intent_mode_isolation` (dating не мешается + `canonical.purpose_blocked`), `language_feasibility` (по коду **и уровню**), `time_feasibility` (interval-algebra через `time_algebra`), `location_policy` (радиус без раскрытия точки), `capacity`, `fatigue_readiness`, `disclosure_policy`. «Результат при неизвестности» из таблицы §8.1 соблюдён (для большинства unknown → BLOCK). `AGE_POLICY` — 18+ объявлена как продуктовая политика.

**`engine.py`** **[в пайплайне]**: `evaluate(...)` прогоняет гейты → единый вердикт; `is_scorable`/`is_discoverable`; `prepare_snapshot`.

**`revalidation.py`** **[отдельный слой]** (§8.2): `capture_baseline`, `revalidate(baseline, cand, intent, ctx, checkpoint)` по чек-поинтам (`CHECKPOINTS`) → `POLICY_CHANGED` при расхождении. Вызывается в accept-транзакции.

**`trust_safety.py`** **[отдельный слой]** (Вердикт#25): `evaluate_trust(account)` → отдельное решение `ALLOW / LIMIT_OUTREACH / REDUCE_VISIBILITY / REVIEW / BLOCK` по сигналам (reports/velocity/mass-invite/no-show/identity_duplicate/moderation_hold). `outreach_cap` (velocity срезает лимит независимо от «победившего» action), `assert_trust_not_relevance` (trust НЕ может стать relevance-фичёй).

---

## 8. Feature Builder (§6.1/§9.1) — [в пайплайне]

`builder.py`: **7 групп фич** — `semantic_activity, time_feasibility, location_feasibility, mode_format,
directed_preferences, social_context, domain_constraints`. Каждая — одно из **4 состояний**:
`known_match / known_mismatch / unknown / not_applicable`. Один source-statement не даёт двойной бонус
(алиасы схлопнуты); `online` → location = `not_applicable` (исключается из знаменателя). `SEM_VALUE`, `GEO_BANDS`,
`VIBE_CLASH`, `ROLE_CONFLICT`.

`unknowns.py` (Вердикт#8) **[в пайплайне]**: `classify_unknowns` → **три класса** `neutral / coverage_reducing /
outreach_blocking`. Критично (→ блок outreach) только при ЯВНОМ требовании интента (время-окна; явный
`format_required`; `requiredLanguages`/`platform_required`), НЕ из-за незаполненного опционального поля кандидата.
`high_impact_unknown` → в `decision_class`.

---

## 9. Relevance Engine (§9) — [в пайплайне]

`relevance.py`:
- `directional_score(features, dom_cfg, priors)` → `R_mean`, `Coverage`, **`R_lcb = clamp(R_mean − λ·(1−Coverage), 0, 1)`**. `not_applicable` вне знаменателя; unknown использует prior и снижает coverage.
- `reciprocal(a, b)` = **`0.70·min(lcb) + 0.30·mean(lcb)`** — штраф односторонним парам.
- `conservative_relevance` + `LCB_HONEST_NAMES` (Вердикт#7: R_lcb — не статистический LCB, а coverage-adjusted эвристика).

`decision.py`:
- `band(lcb, coverage, bands_cfg)` → качественный уровень: **especially_close / strong_option / broader_option / needs_clarification** (пороги из конфига).
- `decision_class(...)` → **strong_personal / usable_personal / discovery_only / clarification / no_outreach** (пороги из домена; `high_impact_unknown` → `clarification`; T2 в персоналку только с `broad_consent`).
- `presentation(...)` → 2–3 подтверждённые причины (только known_match) + один gap. `THRESHOLDS_PROVISIONAL` + `threshold_provenance` (Вердикт#20: пороги — провизорные экспертные константы).

---

## 10. Reciprocity / Readiness (§10)

- **`readiness.py`** **[в пайплайне]**: `readiness_state(...)` → `open_now / open_later / passive_discovery / busy / paused / unknown` (из receiving policy → флаг open → unknown; unknown ≠ открытость). `completion_factors` (прозрачные operational-сигналы, не соц-рейтинг). `ml_boundary_manifest` (что может стать ML-слоем, а что остаётся deterministic).
- **`reciprocity.py`** **[отдельный слой]** (Вердикт#5/6): `classify_reciprocity` (active vs passive), `reciprocity_view(a, b, active_counter_intent)` — для пассива использует `mean_b` (неизвестность штрафуется один раз), `uncertainty` хранится отдельно. Это уточнённая модель; в `search()` пока используется базовый `relevance.reciprocal` (§9.4).
- **`fatigue.py`** **[отдельный слой]** (Вердикт#17): `fatigue_state(load, tier, in_quiet_hours)` — многомерная перегрузка (per_24h / per_sender / per_intent / weak_tier / impressions / per_purpose / active_plans / тихие часы).

---

## 11. Allocation (§11) — [в пайплайне]

`allocation.py` → `rerank(items, intent, cfg, ctx)`:
1. Убрать BLOCK/expired/capacity/**cooldown**/**ignored**/exposure-cap/reservation-full.
2. Сорт: readiness-class → reciprocal → lcb → coverage → **controlled rotation** (тай-брейк по request_id) → имя.
3. Diversity по **3 осям** (bucket/tier/source) + popularity-cap + **area-balancing**.
4. **Near-dup dedup** (opt-in, ПОСЛЕ сортировки — остаются лучшие) + exposure/fatigue caps.
5. **Exploration-квота** (до 2 новых с нулевой экспозицией).
6. propensity + причины. Top-8.

Гварды: `assert_no_payment_feature` — `MonetizationViolation`, если payment/subscription попал в allocation-фичи.
Константы: `TOP_N=8, PER_BUCKET=3, PER_TIER=4, PER_SOURCE=5, POPULARITY_CAP=3, AREA_CAP_DEFAULT=4, EXPLORATION_QUOTA=2`.

---

## 12. Controlled expansion + T5-терминал (§12) — [отдельный слой, fallback]

`expansion.py`:
- `EXPANSION_LADDER` — по одной оси за шаг: exact → sibling → parent(broad_consent) → time_distance/format(fallback_consent) → alternative_type → saved_search. `FORBIDDEN_AXES` (safety/age/consent/block/critical_language/purpose_isolation) не ослабляются никогда.
- **`expansion_policy(intent)`** (Вердикт#9): `exact_only / allow_family / allow_adjacent_after_confirmation / event_fallback_allowed` (если не задано — выводится из уже данного fallback-consent). `policy_allows_axis`, `allowed`, `expand_step`, `expand_until_useful`.
- **T5-терминал** (Вердикт#1): `no_topical_overlap_response(...)` — при отсутствии пересечения НЕ выдаёт случайного человека; возвращает лестницу шагов (`NO_MATCH_LADDER`: предложить расширение → событие/группа → фоновый поиск → открытый intent → честный no-result) + `nearby_open_block` (отдельный блок «рядом», где `personal_invite_allowed=False`, `requires_new_confirmation=True`).

---

## 13. Протокол и транзакции (§13–§14) — [отдельный слой]

- **`protocol.py`** (§13): `ALLOWED_ACTIONS` (типизированный набор), `build_envelope(...)` (idempotency/версии/purpose/disclosure/ttl), волны (`WAVES`, `next_wave`, `check_wave_limit`, `MAX_CONCURRENT_PERSONAL`), `can_auto`/`requires_consent`.
- **`state_machines.py`** (§14.1): автоматы `intent`, **`intent_lifecycle` (11 состояний)**, `proposal`, `match`, `plan`; `assert_transition` — единственный санкционированный переход (идемпотентно).
- **`concurrency.py`** (§14.2): `VersionedStore` (optimistic CAS), `IdempotencyStore` (повтор idem-key → тот же результат), `UniquePairRegistry` (две волны не создают дубль пары), `CapacityLedger` (атомарный claim слота + TTL авто-освобождение).
- **`transitions.py`** (§14.3/§14.4 + B.2): `Orchestrator.accept_proposal(...)` — accept в одной транзакции (idempotency → assert_transition → revalidate → capacity CAS → version CAS → match → outbox). Дифференцированные одновременные принятия: **dating** без подтверждения → `DATING_CONFIRM_REQUIRED` (no auto-commit); **1:1 fixed-time** отзывает прочие активные предложения искателя. `resolve_race` — 8 гонок → детерминированный код без утечки данных. `Outbox` — dedup по event_id.
- **`agent_decision.py`** (Вердикт#4): `can_reach_candidate(...)` — решение «можно ли обратиться» строго из детерминированных источников (receiving policy/readiness/purpose/prefs/limits/policy/явное действие). `assert_llm_role` — LLM запрещены роли decide-agent-agreement/reorder/score (`LLM_FORBIDDEN_ROLES`), разрешены compose/explain/extract/check-data (`LLM_ALLOWED_ROLES`).
- **`intent_set.py`** (Вердикт#27): несколько активных интентов — `active_intents`, `enforce_limit` (`MAX_ACTIVE_INTENTS=5`), `select_for_reverse_reciprocity` (берёт СОВМЕСТИМЫЙ по purpose, не произвольный), `may_offer_other_intent`, `contextual_profile_for`.
- **`plan_coordination/plans.py`**: `PlanCoordinator.create/transition` с version-check.

---

## 14. Группы (§15) — [отдельный слой]

`group_formation/`:
- **`constraints.py`**: `check_set_constraints(members, constraints, pair_blocks)` — группа проверяется как **множество** (размер/quorum/роли/pairwise-blocks/общий язык), `common_window_min` (пересечение окон всех).
- **`utility.py`**: `group_utility(...)` — **least_misery** (не среднее парных совпадений), `load_weights`.
- **`former.py`**: `form_group(...)` — seeds → greedy marginal add → local repair → reserve. Не вызывается из `search()` (тот — 1:1 ранкинг людей).

---

## 15. Dating (§17) — [отдельный слой]

`dating/dating.py` — отдельный режим, не «ещё веса поверх friendship»:
- `consent_gate` (явный opt-in + подтверждённые target-preferences + 18+), `build_dating_capsule` (purpose-bound view, sensitive-минимизация, `auto_accept=False`), `dating_explanation` (без чувствительных причин), `pilot_gate` (`PILOT_REQUIRED` — все review-флаги), `feedback_scope` (изоляция), `crosses_into` (dating не мешается с другими режимами).
- Вердикт#13: `mutual_preference_ok` (взаимная проверка предпочтений A→B и B→A), `dating_rate_limits` (`DATING_RATE_LIMITS` — строже friendship), `is_dating_signal` (friendship-поведение ≠ dating-сигнал), `assert_no_friendship_to_dating_autoexpand` (авто-расширение friendship→dating запрещено).

---

## 16. Feedback / learning (§19) — [отдельный слой]

`feedback_learning/feedback.py`: `OUTCOME_STAGES` (exposure→consideration→proposal→coordination→completion→
quality→safety), `record_outcome` со scope-изоляцией, `is_completed_positive` (primary outcome = состоявшееся
позитивное взаимодействие, не клик/лайк), `profile_update_rule` (одно поведение ≠ вечный вывод), `get_scoped_feedback`
(dating-decline не виден friendship-ранкеру), `classify_nonresponse`/`should_train_on` (timeout ≠ отказ),
`bias_guardrails`.

`reasons.py` (Вердикт#18): `REASON_CODES` — 8 кодов (`not_now, wrong_time, wrong_activity, wrong_format,
too_far, not_interested_in_person, do_not_suggest_again, safety_block`); `consequence`/`cooldown_until`/`suppress_scope`/
`is_person_level_block`/`routes_to_safety` — дифференцированные последствия (другой слот завтра / другую активность
можно / скрыть человека / отключить purpose / в safety-flow).

---

## 17. Observability (§21) — [в пайплайне при переданном trace_log]

`observability/trace.py`: `TraceLog` (иммутабельный лог), `replay(trace, cfg)`.
`contracts/decision_trace.py`: `build_decision_trace(...)` — след одного `(search, candidate)`: gates, версия taxonomy/
config/policy, tier, evidence, directional (A→B, B→A), reciprocal, readiness, allocation, reason_keys — для отладки/
жалоб/воспроизводимости.

---

## 18. Config (§9.5)

`config/validator.py`: `load_config(expect_sha=…)` — **sha-pinned** загрузка + `validate` (сумма весов, наличие
доменов/порогов). `config_health`, `check_version_compat` (major-version), `check_evidence_id_uniqueness`.
- **10 доменов:** social_meet, walk, games, language_exchange, sport_activity, culture_event, professional_networking, watch_together, coworking, dating.
- **7 групп фич** с весами (пример games: semantic 0.25, domain_constraints 0.25, time 0.15, mode_format 0.15, directed 0.1, social 0.1, location 0.0).
- **Пороги band (глобальные):** especially_close `lcb≥0.78, cov≥0.75` · strong_option `0.66/0.60` · broader_option `0.52/0.40` · needs_clarification иначе.
- **Пороги домена (пример games):** `uncertainty_lambda=0.3`, outreach `lcb≥0.72, cov≥0.70`, discovery `lcb≥0.58, cov≥0.50`.

---

## 19. Инварианты (гарантии, проверяются тестами)

1. Нет единого FinalUtility — 6 раздельных слоёв.
2. Semantic tier — иммутабельный провенанс, **никогда не из score**.
3. `unknown ≠ match`: unknown использует prior и снижает coverage.
4. `not_applicable` исключается из знаменателя релевантности.
5. payment/subscription — **никогда** не relevance/allocation-фича (`MonetizationViolation`).
6. Dating изолирован (нет friendship→dating авто-расширения, purpose-bound).
7. LLM не считает score и не решает за агента; гейты детерминированы.
8. Конфиг sha-pinned; пороги — из конфига, не хардкод.
9. Никаких «процентов совместимости» в выдаче — только качественный band.
10. T5 не показывается как персональная рекомендация.

---

## 20. Границы (чего сейчас НЕТ — честно)

- **ML-ранжирование** — нет (by design MVP); есть только декларативная ML-граница (`ml_boundary_manifest`).
- **Калиброванные вероятности / learned reranker / travel-time** — нет (V-P2, «после появления данных»).
- **Встроенность в единый `search()`** — ряд слоёв (reciprocity_view, fatigue, trust_safety, geo_privacy, expansion,
  протокол/транзакции, группы, candidate_types, dating, feedback) реализованы и тестируются, но вызываются на
  СВОИХ стадиях, а не внутри одного `search()`-цикла (см. пометки [отдельный слой]).
- **Реальная БД/сеть/persist** — нет; хранилища in-memory (VersionedStore/IdempotencyStore/CapacityLedger).
- **ANN/embeddings retrieval** — помечен как no-op в stdlib-прототипе (`retrieve_staged`).
- **HTTP/REST-слой** над движком — в самом пакете нет (есть тест-стенд `sim/serve.py`, см. ниже).

---

## 21. Как запустить / посмотреть

- **Симулятор (текст):** `python matching_core/sim/simulate.py` — прогон по общему пулу на 6 интентах + инварианты.
- **Ручной стенд (браузер):** `python matching_core/sim/serve.py` → http://127.0.0.1:7099 — форма интента/профиля/пула, на каждый «Match» реально гоняется `search()`.
- **Тесты:** `for f in matching_core/tests/test_*.py; do python "$f"; done` → 25 сьютов / 428 зелёных.

_Сопутствующий документ в пакете: `ARCHITECTURE.md` (чеклист сборки §0–§24). Отчёты о ревью июля 2026 (`VERDICT_RESPONSE`, `COMPLIANCE_REPORT`, `INTEGRATION_REPORT`) удалены 2026-08-27: они описывали состояние, которого больше нет, и читались как действующее описание. Ищи в истории git._
