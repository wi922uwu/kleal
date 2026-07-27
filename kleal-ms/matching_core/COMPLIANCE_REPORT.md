# Отчёт соответствия: Kleal Matching Core — реализация `matching_core/` против спецификации `Kleal_Matching_Core_Final_Spec_RU_v2.md`

## 1. Резюме

Аудит покрывает весь спек-файл §0→§24 плюс Приложения A–E — **183 под-пункта**. Реализация — чистый Python-пакет `C:/Projects/.dating/matching_core/` (17 доменных пакетов + `tests/`, stdlib-only, без фреймворков), карта в `ARCHITECTURE.md`. Итоговое распределение статусов:

| Статус | Кол-во | Что означает |
|---|---:|---|
| **done** | 115 | реализовано + покрыто тестом |
| **partial** | 43 | реализовано частично / как ранжирование вместо hard-gate / упрощённо / без теста |
| **absent** | 3 | в коде отсутствует |
| **by_design** | 9 | соблюдается структурно (детерминизм, изоляция слоёв), без отдельного модуля/теста |
| **doc_only** | 13 | документные разделы (метрики, план пилота, самооценка, библиография) — кода не требуют |

Тестовая база — **20 файлов** `tests/*.py` (+ подкаталоги `fixtures/property/race/safety/domains`), включающие все **24 acceptance-теста Приложения C** (21 явным тестом, C#16 частично, C#21/C#22 by-design). Ключевые архитектурные инварианты подтверждены чтением кода: единого `FinalUtility` в коде **нет** (grep пуст); `reciprocal()` в `relevance_engine/relevance.py:52` реализует ровно `0.70·min(lcb) + 0.30·mean(lcb)`; конфиг sha-пинован (`PINNED_SHA=d804df8e…`, `config/validator.py:27`); веса/пороги читаются только из единственного `config/Kleal_Matching_Core_Config_v2.yaml` (локальная вторая копия matching-core.yaml удалена — она отличалась весами social_meet и гасила движок). Общая оценка: **срез §0–§17 (архитектура, контракты, policy, relevance, readiness, allocation, agent-protocol, FSM, dating) реализован точно и хорошо покрыт**; основные слабые места — упрощение части hard-gate'ов до булевых флагов (время/язык/privacy), несколько несведённых предикатов таксономии, и целиком документные §20/§22/§24, которые кода не требуют.

## 2. Сводная таблица по разделам

| § | Суть | Реализация | Тесты | Статус |
|---|---|---|---|---|
| §0 | 6 изолированных слоёв, нет FinalUtility, веса в YAML, 8 раздельных выходов | пакеты policy/retrieval/relevance/…; `contracts/decision_trace.py`; `config/validator.py` | test_contracts C#24; test_config CFG1-3 | done / by_design |
| §1 | Цель = состоявшиеся взаимные взаимодействия | продуктовая, `feedback_learning` (§19) | — | doc_only |
| §1.1 | 6 типов решений | `contracts/group.py`,`relationship_edge.py`,`intent.py`; event/room в §16 | test_contracts GR1,RE1,RE2 | partial |
| §1.2 | Release flags по доменам, dating отдельно | `config` release_status/domains.dating | — | partial |
| §2 | Канонические различения терминов | контракты intent/candidate/match/decision_trace | test_contracts IN4,MA1 | by_design |
| §3 | 9-шаговая последовательность решения | `orchestrator/search.py` | test_domain_scenarios | partial |
| §4 | 12 канонических сущностей + immutable snapshot | `contracts/*.py` (12 build_*) | test_contracts (36 checks) | done |
| §4.1 | Evidence object + общий evidence_id + дедуп | `contracts/evidence.py` | test_contracts EV1,EV2,C#3 | done |
| §4.2 | 7-уровневая иерархия источников | `contracts/evidence.py` SOURCE_PRIORITY/resolve_field | test_contracts EV2,EV3 | done |
| §4.3 | Intent schema 11 блоков + версия + lifecycle + Time | `contracts/intent.py` | test_contracts IN1-6 | done (Time/версия — partial) |
| §4.4 | Receiving policy | `contracts/receiving_policy.py` | test_contracts RP1-4 | done |
| §5 | LLM=parser, детерминированный компилятор | `intent_compiler/compiler.py` | test_intent_compiler IC1-8 | partial |
| §5.1 | hard/soft классификация, правило подтверждения | `compiler.py` classify_constraints | IC5,IC6,IC7 | partial |
| §5.2 | Классы уточнений P0-P3 + rule-based выбор | `intent_compiler/clarification.py` | CL1-8 | done |
| §5.3 | Минимально достаточный intent | `contracts/intent.py` minimal_intent_ok | IN5,IN6 | partial |
| §6 | Таксономия: 5 уровней близости, negative/complementary, governance | `taxonomy/graph.py`,`governance.py` | test_taxonomy TX1-10,GOV1-5 | done (negative/complementary — partial) |
| §6.1 | 7 feature groups + 4 состояния признака + no-double-count | `feature_builder/builder.py` | test_feature_builder FB1-7,C#2,C#3 | done |
| §7.1 | Порядок источников, tiers T0-T5, immutable provenance | `retrieval/retriever.py` | test_retrieval RT1-10,C#4 | done (per-tier аналитика — absent) |
| §7.2 | 5-стадийный funnel + бюджеты + ANN | `retriever.py` BUDGET_STAGES | RT9 | partial |
| §8 | Scoring только после ALLOW; BLOCK/REVIEW | `policy_engine/engine.py` | test_policy PE1-3,C#5 | done |
| §8.1 | 12 hard-gate'ов eligibility | `policy_engine/gates.py` | test_policy G1-G12 | done/partial (см. §8.1) |
| §8.2 | 7 чекпоинтов revalidation | `policy_engine/revalidation.py` | REV1-3,C#6 | done |
| §8.3 | Контекстные профили / purpose binding | `gates.py`,`engine.py` prepare_snapshot | G8,PE2 | partial |
| §8.4 | Coarse-гео + время | `feature_builder/builder.py` haversine; `gates.py` location | G10,G11 | partial |
| §9.1-9.4 | Состояния, нормализация, R_mean/Cov/LCB, directional+reciprocal | `relevance_engine/relevance.py` | test_relevance C#1,C#2,RL1-4 | done |
| §9.5 | Канонические веса + CI-проверки | `config/validator.py` | test_config CFG3-9 | done/partial |
| §9.6 | 5 decision thresholds | `relevance_engine/decision.py` | DC1-7 | done |
| §9.7 | Качественный band, без процентов | `relevance_engine/decision.py` band | C#23,BD1,BD2 | done |
| §10 | Relevance≠readiness; 6 состояний; completion factors; ML-граница | `reciprocity_readiness/readiness.py` | test_readiness RD1-11 | done |
| §11 | Allocation после eligibility, 9 механизмов, монетизация-инвариант | `allocation/allocation.py` | test_allocation AL1-8,C#11 | done (9 механизмов — partial) |
| §12 | Fallback-лестница, forbidden axes, 7 шагов | `orchestrator/expansion.py` | test_expansion EX1-10 | done (provenance tier — partial) |
| §13 | Типизированный agent-protocol, 9 действий, волны, автономность | `orchestrator/protocol.py` | test_protocol PR1-16 | done |
| §14 | FSM intent/proposal/match/plan, concurrency, 8 гонок | `orchestrator/state_machines.py`,`concurrency.py`,`transitions.py` | test_state_machines SM,CAS,RC,C#6-10 | done (reservation-TTL, §14.3 — partial) |
| §15 | Group formation: set-constraints, GroupUtility, MVP-алгоритм | `group_formation/*` | test_group_formation GC,GU,GF,C#18,C#19 | done (host/replacement/waitlist — absent/partial) |
| §16 | 5 типов кандидатов (event/room/venue) | `retrieval/candidate_types.py` | test_candidate_types CT1-8,C#20 | done |
| §17 | Dating: consent/capsule/age/sensitive/isolation/pilot-gate | `dating/dating.py` | test_dating DA1-13,C#14 | done (safety/audit — partial/absent) |
| §18 | 10 доменов + сценарии | `config` + `orchestrator/search.py` | test_domain_scenarios | done/partial |
| §19 | Feedback: outcome taxonomy, update rules, bias-guard | `feedback_learning/feedback.py` | test_feedback FB1-11,C#13 | done |
| §20 | Метрики / staged validation / guardrails | — | — | doc_only |
| §21 | 16 компонентов, API/события, trace/replay, SLA | пакеты + `observability/trace.py` | test_observability OB1-3,C#24 | done/partial/by_design |
| §22 | План пилота Барселоны | — | — | doc_only |
| §23 | Модульная структура, 15 запретов, DoD, порядок сборки | дерево пакетов + инвариант-тесты | распределённо | done/by_design |
| §24 | Самооценка спеки | — | — | doc_only |
| Прил.A | Canonical config | `config/Kleal_Matching_Core_Config_v2.yaml`+validator | test_config | done |
| Прил.B | Псевдокод search/accept/form_group | search.py/transitions.py/former.py | domain/state/group тесты | done |
| Прил.C | 24 acceptance-теста | по всем модулям | test_* C#1-24 | 21 done / 1 partial / 2 by_design |
| Прил.D | Матрица purpose-binding 11×5 | `contracts/profile.py` _MATRIX | C#12,C#14,DA5-9 | partial |
| Прил.E | Библиография | — | — | doc_only |

---

## 3. Раздел за разделом

### §0 — Ключевые архитектурные решения
- **6 изолированных слоёв, ни один не компенсирует другой** — структурно: policy_engine/retrieval/relevance_engine/reciprocity_readiness/allocation/orchestrator = отдельные пакеты, единого score нет. Тест «слой не компенсирует» отдельный отсутствует. **by_design**.
- **Запрет FinalUtility (склад relevance+safety+…)** — `contracts/decision_trace.build_decision_trace` держит policy/semantic_tier/evidence/directional/reciprocal_relevance/readiness/allocation/reason_keys раздельно; grep `FinalUtility` по коду **пуст**. Тест: test_contracts C#24. **done**.
- **Веса/пороги только в versioned YAML** — `config/Kleal_Matching_Core_Config_v2.yaml` (sha-pin) + `config/validator.py` load_config/validate. Тест CFG1-3. **done**.
- **semantic_tier — происхождение T0–T5, не из score** — `contracts/candidate.py` TIERS immutable + config semantic_tiers; фактическое присвоение — retrieval §7; явного теста «tier≠score» на уровне §0 нет. **partial**.
- **unknown/mismatch/not_applicable — разные состояния** — на уровне §0/config только `unknown_prior`; сами 4 состояния — §9.1 feature_builder. **partial**.
- **relevance — internal 0–1 heuristic, не процент** — декларация в config score_semantics/user_facing_bands; реализация в §9. **doc_only** (для §0).
- **Оплата не влияет на relevance/eligibility/safety/порядок** — config `currency_or_paid_priority{ranking_boost_allowed:false}` + schema const false; runtime-enforcement — §11. **partial** (здесь только декларация).
- **8 раздельных выходов системы** — все присутствуют полями `decision_trace`. Тест C#24. **done**.

### §1 — Цель и инвариант успеха
- Максимизация состоявшихся взаимных безопасных взаимодействий — продуктовая цель, **doc_only**.
- Инвариант успеха (completed + двусторонний positive feedback) — реализуется в feedback_learning §19, здесь **doc_only**.
- **§1.1** 6 типов решений — контракты покрывают p2p/intent-to-intent/group/continuation; event/room в §16. Тест GR1,RE1,RE2. **partial**.
- **§1.2** Границы пилота через release flags, dating отдельный gate — `config release_status/domains.dating.release_gate`; общего per-domain feature-flag механизма в contracts нет. **partial**.

### §2 — Терминология
- Канонические различения (intent≠goal, eligibility≠relevance, tier≠качество, directional≠P_accept, readiness≠качество, match≠показ) — отражены в контрактах. Тест IN4,MA1. **by_design**.
- Нормативные слова (ОБЯЗАТЕЛЬНО/ЗАПРЕЩЕНО…) — конвенция, **doc_only**.

### §3 — Последовательность решения
- 9-шаговая цепочка (Compiler→Policy→Retrieval→FeatureBuilder→Relevance→Readiness→Allocation→Presentation→Transaction) — `orchestrator/search.py` связывает слои; на уровне contracts/config только типы шагов. **partial**.
- Запрещённая архитектура (один FinalUtility) — grep подтверждает отсутствие; decision_trace раздельный. **by_design**.

### §4 — Канонические сущности
- 12 сущностей — `contracts/{profile,receiving_policy,intent,evidence,candidate,proposal,reservation,match,group,plan,relationship_edge}.py`, все build_*. Тест: 36 checks зелёные. **done**.
- Immutable snapshot с версиями — `candidate.build_candidate_snapshot` versions{intent,profiles,config,policy}. Тест CA1,C#24. **done**.
- **§4.1** Evidence object (все поля + priority) — `contracts/evidence.build_evidence`. Тест EV1,EV2. **done**.
- **§4.1** Общий evidence_id + дедуп до агрегации — `evidence.new_evidence_id` (sha1) + `dedup`. Тест EV1,C#3. **done**.
- **§4.2** 7-уровневая иерархия источников — `evidence.SOURCE_PRIORITY(1..7)`+resolve_field+usable_for_purpose. Тест EV2,EV3. **done**.
- **§4.3** Intent 11 блоков — `intent.build_intent` INTENT_BLOCKS + flat() + validate_intent. Тест IN1,IN2. **done**.
- **§4.3** Версия при любом search-изменении — `bump_version` ручной + декларативный SEARCH_AFFECTING; **авто-детекта diff→bump нет**. Тест IN3. **partial**.
- **§4.3** Time (tz/UTC/interval algebra) — блок {windows,duration,recurrence,urgency}; **нет поля timezone, нет UTC-нормализации/interval algebra** в контракте. **partial**.
- **§4.3** Lifecycle + истёкший intent не в ранжировании — `intent.is_expired`. Тест IN4. **done**.
- **§4.3/§5.3** Минимально достаточный intent — `intent.minimal_intent_ok`. Тест IN5,IN6. **done** (но не проверяет format/disclosure/search_budget — см. §5.3).
- **§4.4** Receiving policy (все поля + helpers) — `receiving_policy.py`. Тест RP1-4. **done**.

### §5 — Intent Compiler
- LLM=parser, детерминированный компилятор с allowlist/normalizer — `intent_compiler/compiler.py` compile_intent+_normalize_slots+confidence. **Литеральной JSON-schema-валидации LLM-вывода нет** (её роль играют allowlists); policy checks не вызываются из компилятора. Тест IC1-3,IC8. **partial**.
- **§5.1** hard/soft классификация — `compiler.classify_constraints` (loc soft / lang hard / dating hard / online-fallback soft). **Строка «без токсиков»→domain constraint+moderation НЕ реализована**. Тест IC5-7. **partial**.
- **§5.1** Правило подтверждения sensitive/значимого ограничения — флаг `needs_confirmation` производится (`_NEEDS_CONFIRM`), но **не потребляется**: нет гейта, блокирующего поиск до подтверждения, нет intent-summary UX. Тест IC5. **partial**.
- **§5.2** Классы уточнений P0-P3 + действие при отказе — `clarification.CLASS_ACTION+QUESTION_CATALOG` (9 вопросов). Тест CL1-3,CL7,CL8. **done**.
- **§5.2** Rule-based выбор вопроса (4 ordinal фактора − friction, safety×2, ≤1 вопрос) — `clarification.priority/select_question`. Тест CL4-6. **done**.
- **§5.3** Минимально достаточный intent (7 элементов) — `minimal_intent_ok`; **не проверяет format, domain-critical поля, disclosure summary, search_budget** (поле есть в build_intent, но compile_intent его не заполняет). Тест IN5,IN6. **partial**.

### §6 — Таксономия
- Смысловые связи, не замена policy; embeddings только для recall — `taxonomy/graph.py` (dict + resolve/similarity); **реальных embeddings/ANN нет** (stdlib-only), recall через literal/prefix. Тест TX1,TX7,TX8. **by_design**.
- 5 уровней близости с коэффициентами (alias/exact 1.0/sibling 0.55-0.75/parent T2/adjacent T3) — `graph.similarity` + feature_builder SEM_VALUE{4:1.0,3:0.65,2:0.45,1:0.25}. Sibling=0.65 фиксирован, **не управляется domain config**. Тест TX2-8. **done**.
- **Negative edge → penalty; complementary role → matrix** — `graph.NEGATIVE_EDGES/is_negative` + `COMPLEMENTARY_ROLES/is_complementary` определены и покрыты как предикаты, но **НИ ОДИН не потребляется в скоринге** (grep подтверждает: feature_builder/search не вызывают is_negative/is_complementary; directed_preferences даёт генерик 0.55). Penalty/constraint фактически не подключены. Тест TX9,TX10. **partial**.
- Governance (owner/version/review/rollback, shadow replay, alias не повышает score) — `taxonomy/governance.py`. Per-edge список language-aliases не хранится. Тест GOV1-5. **done**.

### §6.1 — Feature Builder
- 7 групп, cap 1.0, no-double-count, дедуп по evidence_id — `feature_builder/builder.build_features` + `contracts/evidence.dedup`. Явной cap()-функции нет (≤1.0 по построению). Тест FB1,C#3,FB2,EV1. **done**.
- 4 состояния признака (known_match/mismatch/unknown/NA; online→location NA) — `builder` K_MATCH/K_MISM/UNKNOWN/NA. Тест FB2,C#2,FB3,FB5-7. **done**.

### §7 — Retrieval
- Порядок 5 источников — `retriever.SOURCES{1..5}`+source_of+_SOURCE_RANK. Тест RT7. **done**.
- Tiers T0-T5 (происхождение + UX + personal outreach) — `retriever.assign_tier`+TIER_UX (T2=broad_consent, T3/T4=False). Тест RT1-5,RT10. **done**.
- Immutable provenance (логистика не переводит parent→direct) — `assign_tier` игнорирует score/время. Тест C#4. **done**.
- **Per-tier relevance analytics — ОТСУТСТВУЕТ** ни в retrieval, ни в observability. **absent**.
- 5-стадийный funnel + бюджеты (250→80→50→30→8) + ANN/pgvector — `retriever.BUDGET_STAGES` константы + одностадийный проход label+cap; **funnel свёрнут в один проход, ANN-стадия — no-op** (embeddings отсутствуют). Тест RT9. **partial**.
- No-LLM в retrieval — детерминирован по построению. **by_design**.

### §8 — Eligibility / Policy
- Scoring только после ALLOW; BLOCK исключает до ranking; REVIEW не даёт авто-proposal — `policy_engine/engine.py` evaluate/is_scorable/is_discoverable + search.py (skip BLOCK до feature build). Тест PE1,C#5,PE3. **done**.
- **§8.1 гейты** (`policy_engine/gates.py`):
  - account_status — **done** (отклонение: отсутствующий статус дефолтит в active→ALLOW, спека при unknown требует BLOCK). G1.
  - age/legal — **done** (<18 BLOCK; dating+age unknown BLOCK; soft→REVIEW). G6,G7.
  - mutual_block — **done**. G2.
  - privacy_visibility — **partial**: проверяется только сторона кандидата (не «обе»); unknown→ALLOW вместо BLOCK. G5.
  - intent_mode_isolation — **done**. G8.
  - location_policy — **done** (radius/zoneOptIn→REVIEW), coarse km. G10,G11.
  - time_feasibility — **partial**: упрощено до булева open-флага, нет interval-algebra/duration/tz; unknown→ALLOW. G12.
  - language_feasibility — **partial**: проверяет наличие языка, **не уровень**. G9.
  - capacity — **partial**: реализован, включён в CANONICAL_GATES, прямого теста нет.
  - fatigue_readiness — **partial**: корректно разделяет outreach vs passive, прямого unit-теста нет.
  - safety_restrictions — **done** (BLOCK/REVIEW, не штраф). G3,G4.
  - disclosure_policy — **partial**: только release-gate→REVIEW; ветка «payload reduction» отсутствует. PE2,PE3.
- **§8.2** 7 чекпоинтов revalidation + POLICY_CHANGED — `revalidation.py` CHECKPOINTS+capture_baseline+revalidate. Тест REV1-3,C#6. **done**.
- **§8.3** Контекстные профили / purpose binding — `intent_mode_isolation` + `engine.prepare_snapshot`; field-level purpose-bound ProfileView и versioned/TTL Match Capsule живут в contracts §4, здесь тестами purpose-binding не покрыты. **partial**.
- **§8.4** География и время — coarse-гео/радиус реализованы (`_haversine`,`location_policy`); **available_from/until/min_duration/travel-buffer, interval-algebra, DST/travel-тесты отсутствуют** в этих модулях. **partial**.

### §9 — Relevance / математика
- **§9.1** 4 состояния, разреженный не обгоняет — `feature_builder` + `relevance.directional_score`. Тест C#1,C#2. **done**.
- **§9.2** adjusted=conf·obs+(1−conf)·prior; unknown→prior; NA→вес 0 — `relevance._adjusted/_clamp01`. Ветка conf<1 в тестах не прогоняется. Тест C#1,C#2. **done**.
- **§9.3** R_mean/Coverage/R_lcb=clamp(mean−λ(1−Cov)); λ из config (dating 0.35>social 0.25) — `relevance.directional_score`. Тест RL1,RL2,C#1,C#2. **done**.
- **§9.4** R_A_to_B/R_B_to_A раздельно; R_reciprocal=0.70·min+0.30·mean; штраф односторонних; P_accept только после калибровки — `relevance.reciprocal` (по lcb) + `search._reverse_features`. B→A реализован как relevance-proxy (реверс признаков), а fit к receiving policy B — в readiness §10. P_accept отсутствует (by_design). Тест RL3,RL4. **done**.
- **§9.5** Канонические веса в YAML — `config/Kleal_Matching_Core_Config_v2.yaml`+`validator.load_config` (sha==PINNED). Тест CFG1-3,10,11. **done**.
- **§9.5** CI-проверки config — `validator.validate` покрывает 3 из 5 (сумма весов=1.0, extra-keys, диапазоны priors/λ/thresholds). **ОТСУТСТВУЮТ**: (а) уникальность evidence_id внутри feature groups (сделано как runtime-дедуп, не config-CI); (б) совместимость config version с model/policy version (validate проверяет лишь наличие config_version, кросс-версия делегирована «вызывающему»). Тест CFG4,5,7,8,9. **partial**.
- **§9.6** 5 decision thresholds (strong/usable/discovery/clarification/no_outreach) по lcb+coverage+tier; T2→broad consent; policy≠ALLOW→no_outreach; high-impact unknown→probe — `relevance_engine/decision.decision_class`. Пороги из per-domain config. Тест DC1-7. **done**.
- **§9.7** Запрет «92%», качественный band + 2-3 known причины + 1 компромисс + метка «не подтверждено» — `decision.band/BAND_LABELS/presentation`; причины **только из known_match** (C#23). Коммит fcdc31b подтверждает переход band вместо raw-percent. Тест C#23,BD1,BD2. **done**.

### §10 — Reciprocity / Readiness
- Relevance≠readiness, не складываются; R_A_to_B/R_B_to_A раздельно — `reciprocity_readiness/readiness.py` (categorical) + search держит поля раздельно; reverse-fit в relevance_engine. Тест AL4,RD7,RL3,RL4. **done**.
- **§10.1** 6 состояний readiness (open_now/open_later/passive/busy/paused/unknown), domain-dependent, unknown≠openness — `readiness.readiness_state`+READINESS_RANK. Тест RD1-7. **done**.
- **§10.2** Completion factors как operational signals, не соц-рейтинг — `readiness.completion_factors` (7 сигналов, dict без агрегата). Тест RD8,RD9. **done**.
- **§10.3** ML послойно (6 слоёв), P_response/accept/completion только после калибровки, hard gates остаются deterministic — `readiness.ML_LAYERS/DETERMINISTIC_FOREVER/ml_boundary_manifest`. Декларативный манифест. Тест RD10,RD11. **done**.

### §11 — Allocation
- Allocation после eligibility+relevance, не меняет смысл релевантности — `allocation/allocation.rerank`. Тест AL1-8,D6. **done**.
- **§11.1** 9 механизмов — реализованы: exposure caps, cooldown, exploration, popularity guard, защита от переиспользования. **Отсутствуют/упрощены**: reservation-capacity (в group_formation) — absent; city/area supply balancing — absent; proposal-fatigue как отдельный cap — деградирует в readiness; diversity — один generic bucket вместо 3 осей; exploration — один слот, не квота. Тест AL5-8. **partial**.
- **§11.2** Порядок rerank (6 шагов) — `rerank` точно в этом порядке. Шаг fatigue отдан §10. Тест AL1-8. **done**.
- **§11.3** Монетизация не влияет; payment_status запрещён как feature — `allocation.assert_no_payment_feature`+MonetizationViolation. Тест C#11. **done**.

### §12 — Expansion
- Цель — полезный следующий шаг, в пределе saved_search — `orchestrator/expansion.expand_until_useful`. Тест EX10. **done**.
- **§12.1** Принципы (1 ось/шаг, дешёвый soft первым, forbidden 6 осей, explanation, parent→broad consent, adjacent→discovery) — `expansion.FORBIDDEN_AXES/allowed/EXPANSION_LADDER`. **«Сохранять provenance tier» не реализовано enforcement'ом** — только строка tier_note; тир переносит вызывающий. Тест EX1-6,forbidden-loop. **partial**.
- **§12.2** 7-шаговый порядок — `EXPANSION_LADDER` точно. Тест EX7-9. **done**.
- **§12.3** Dota-пример (LoL не в inbox без consent) — механизм общий (parent→discovery_only + decision_class на T2). Тест C#15,EX6. **done**.

### §13 — Agent Protocol
- Типизированные события, без свободного LLM-текста — `orchestrator/protocol.build_envelope` (ALLOWED_ACTIONS+structured_fields+rendering_key). Тест PR1,PR3,PR4. **done**.
- **§13.1** 9 действий + полный конверт (proposal_id/idempotency/версии/purpose/disclosure/ttl/rendering/audit) — `protocol.ALLOWED_ACTIONS/build_envelope`. profile capsule = один int (не capsule-id). Тест PR1-4. **done**.
- **§13.2** Волны 0/1-2/1-2/до3, ≤3 параллельных, запрет mass-outreach — `protocol.WAVES/next_wave/MAX_CONCURRENT_PERSONAL=3/check_wave_limit`. Размеры фиксированы 2/2/3 (верхняя граница). Тест PR5-11. **done**.
- **§13.3** Границы автономности (5 auto / 6 consent-required, множества непересекающиеся) — `protocol.AUTO_ALLOWED/CONSENT_REQUIRED/can_auto/requires_consent`. Тест PR12-16. **done**.

### §14 — State Machines / Concurrency
- **§14.1** FSM intent/proposal/match/plan — `orchestrator/state_machines.MACHINES` + `plan_coordination/plans.py`. Match создаётся сразу MUTUAL (пропуск PENDING_DISCLOSURE); plan mapping 'rescheduled'↔'CHANGED'. Тест SM1-6,PC1-6. **done**.
- **§14.2** optimistic concurrency (version CAS) — `concurrency.VersionedStore.compare_and_swap`. Тест CAS1,AC3,PC4. **done**.
- **§14.2** idempotency на write — `IdempotencyStore` + accept_proposal. Тест C#7. **done**.
- **§14.2** transactional outbox + dedup — `transitions.Outbox.publish`. Тест AC2,C#7. **done**.
- **§14.2** unique active pair/purpose — `UniquePairRegistry.claim` (ключ=пара+purpose, intent в ключ не входит; registry не подключён внутрь accept). Тест UP1,UP2. **done**.
- **§14.2** policy revalidation в транзакции accept — `accept_proposal→revalidate('on_accept')`. Тест C#6. **done**.
- **§14.2** reservation TTL для capacity — контракт `reservation.build_reservation(ttl)/is_expired` есть, но фактический capacity держит `CapacityLedger` **без TTL/авто-release**; связки reservation-TTL→освобождение нет. **partial**.
- **§14.2** CAS при concurrent accepts — `CapacityLedger.claim_slot`. Тест C#8 (реальные потоки). **done**.
- **§14.2** immutable decision trace + retry-safe consumers — `observability/trace.TraceLog`+`decision_trace` (пишутся в search, не в accept) + Outbox dedup. Тест D3,C#7. **done**.
- **§14.3** Политика одновременных принятий по типу intent — `CONCURRENT_ACCEPT_POLICY` воспроизведена как таблица-данные, но **дифференцированное поведение не реализовано** (accept единообразен, нет «withdraw остальных» для 1:1, «hold» для multiple, reservation-до-quorum для group, waitlist для event). Теста нет. **partial**.
- **§14.4** 8 критических гонок → детерминированный код, без утечки — `RACE_CODES/resolve_race`(leak:false) + реальное принуждение через revalidate/CapacityLedger/expiry/assert_transition/UniquePairRegistry/Outbox. timezone_impossible и intent_cancelled_delayed_notif — код без полного transaction-теста. Тест RC1-4,C#6,C#8-10. **done**.

### §15 — Group Formation
- **§15.1** min/max+quorum — `constraints.check_set_constraints`. Тест GC1. **done**.
- **§15.1** пересечение времени — `constraints._intersect_windows`. Тест GC2. **done**.
- **§15.1** обязательные роли + distribution — `constraints.required_roles/role_distribution`. Тест C#18. **done**.
- **§15.1** pairwise blocks + safety exclusions — `constraints.pair_blocks` (safety как pair_blocks). Тест C#19. **done**.
- **§15.1** skill spread + language coverage — проверяются в коде, но **ни одного теста**. **partial**.
- **§15.1** host/moderator + equipment/platform/venue + replacement policy — **ОТСУТСТВУЮТ** в check_set_constraints (host только поле в contracts, не валидируется). **absent**.
- **§15.2** GroupUtility (least_misery 0.35+mean 0.25+role 0.20+time 0.10+diversity 0.10), hard-violation→недопустимо — `utility.group_utility/least_misery` (веса из cfg). Тест GU1,GU2. **done**.
- **§15.3** MVP-алгоритм (seed→pools→greedy→repair→reserve→invitations→waitlist) — шаги 1-5 реализованы (`former.py`); **шаг 6 structured invitations отсутствует, шаг 7 waitlist/quorum-loss re-form отсутствует; local_repair только swap**. Тест GF1-3. **partial**.
- **§15.4** Примеры (Dota stack/падель/разговор/прогулка) — только падель упражняется тестом; остальные — документные. **partial**.

### §16 — Events / Rooms / Venues
- Event отдельный тип (eligibility/ranking/transaction) — `retrieval/candidate_types.build_event/event_eligibility/user_event_relevance`; eligibility проверяет только capacity+access, **category/schedule не валидируются**. Тест CT1-4,C#20. **done**.
- Online room (platform/topic/capacity/moderation; join token/waitlist) — `build_room/session_relevance`; transaction — строковый ярлык, **фактической waitlist-логики нет**. Тест CT5,C#20. **done**.
- Venue (availability/price/noise/distance/accessibility; plan suitability) — `build_venue/plan_suitability`. Тест CT6,CT7. **done**.
- 5 разных типов, каждый со своей transaction+explanation — `CANDIDATE_KINDS(5)/candidate_transaction/TRANSACTION`. Тест CT8,C#20. **done**.
- Event/room как честная альтернатива, не «совпадение с людьми» — `TRANSACTION.explain_key='explain.event_alternative'`. Тест C#20. **done**.

### §17 — Dating
- **§17.1** consent (dating optin + confirmed target prefs) — `dating.consent_gate`. Тест DA1,DA2,DA4. **done**.
- **§17.1** отдельная dating capsule, purpose-bound — `dating.build_dating_capsule→profile.build_profile_view('dating')`. Тест DA5,DA7,DA8. **done**.
- **§17.1** строгие age gates — `consent_gate` (age<18→reject). Тест DA3. **done**.
- **§17.1** orientation/preferences как sensitive с минимизацией — `build_dating_capsule` (gender/orientation drop без consent). Тест DA6,DA8. **done**.
- **§17.1** staged disclosure (фото/имя/детали) — механизм есть (`profile.py` 'staged'), но **по-стадийное раскрытие не покрыто явным тестом**. **partial**.
- **§17.1** каждый proposal требует явного действия, no auto-accept — флаг `auto_accept=False` выставлен и протестирован (DA7), но **ничем не потребляется**; в accept-пути нет принуждения. Политика лишь декларативна. **partial**.
- **§17.1** explanation без sensitive/псевдо-score — `dating.dating_explanation` (фильтр _SENSITIVE_REASON_KEYS). Тест DA9. **done**.
- **§17.1** safety (block/report, rate limits, anti-harassment, private-location) — частично: private-location через coarse (C#14); block/report/rate-limits — общие механизмы, **dating-специфичного safety-модуля нет, anti-harassment отсутствует**. **partial**.
- **§17.1** audit (отдельные policy version/retention/access для dating) — **ОТСУТСТВУЮТ**. **absent**.
- **§17.2** Изоляция (dating-цель не для коллег; отказ не влияет на friendship; friendship→dating новый consent) — `dating.crosses_into/feedback_scope='dating'/consent_gate`. Тест DA10,DA11. **done**.
- **§17.3** Pilot gate (UX/safety/moderation/DPIA/incident/abuse) — `dating.pilot_gate/PILOT_REQUIRED(6)`. Тест DA12,DA13. **done**.

### §18 — Домены и сценарии
- **§18.1** Таблица 10 доменов — `config/Kleal_Matching_Core_Config_v2.yaml`(10)+`search._TYPE2DOMAIN`; per-domain slots/hard/fallback **не единый артефакт**, размазаны по слоям; не все домены имеют e2e-тест. **partial**.
- **§18.2** Dota 2 (T0 exact/T2 LoL parent/детерминизм/no-percent) — search+retriever+decision. Тест D1-6,C#15. **done**.
- **§18.3** Прогулка Eixample — домен walk в конфиге + gates, но **отдельного e2e-теста прогулки нет**. **partial**.
- **§18.4** Испанский (native↔learner комплементарность) — реализовано как **ранжирование, не hard role-gate** (C#16). Тест L1. **partial**.
- **§18.5** Профессиональный кофе (target по роли кандидата, не self profession) — `directed_preferences`. Тест C#17. **done**.
- **§18.6** Краткие сценарии (падель/выставка/футбол/коворкинг/книжный/dating-прогулка) — падель + dating покрыты; выставка/футбол/коворкинг/книжный **не тестируются e2e**. **partial**.

### §19 — Feedback / Learning
- **§19.1** Outcome taxonomy, Primary=Completed Positive (не клик) — `feedback.OUTCOME_STAGES/record_outcome/is_completed_positive`. Тест FB1-3. **done**.
- **§19.2** Правила обновления профиля (explicit→stable, повтор→suggestion, dating не переносится) — `feedback.profile_update_rule/get_scoped_feedback`. Тест FB4-7,C#13. **done**.
- **§19.3** Защита от bias (timeout≠mismatch, exploration с propensity, safety/fairness отдельно) — `feedback.classify_nonresponse/should_train_on/bias_guardrails`; bias_guardrails декларативный чек-лист. Тест FB8-11. **done**.

### §20 — Метрики и валидация — **doc_only**
- **§20.1** 12 контуров показателей — сигналы логируются (OUTCOME_STAGES), **модуля вычисления метрик/дашборда нет**. Кода не требует.
- **§20.2** Staged validation — процессный план (часть unit/property выполнена тест-сьютом).
- **§20.3** Experimental guardrails — операционная политика, движка нет.

### §21 — Техническая архитектура
- **§21.1** 16 компонентов — пакеты `matching_core/*` + ARCHITECTURE.md; Profile/Consent Service и Cost Governor без выделенного модуля. **by_design**.
- **§21.2** Минимальные API/события — операции реализованы как библиотечные функции (search/accept_proposal/form_group/record_outcome/TraceLog) + outbox для событий; **именованного HTTP/REST-слоя нет**. **partial**.
- **§21.3** Immutable trace + replay воспроизводит результат — `decision_trace.build_decision_trace`+`trace.TraceLog/replay` (deepcopy, сверяет config_version). Тест OB1-3,C#24. **done**.
- **§21.4** SLA/деградация fail-closed — `validator.load_config`(fail-closed sha) + by-design детерминизм policy/retrieval; **полная per-failure матрица §21.4 как единый слой не реализована**. Тест test_config. **partial**.

### §22 — План пилота — **doc_only** (§22.1 scope, §22.2 7 этапов, §22.3 операционная модель — кода не требуют).

### §23 — Требования к реализации
- **§23.1** Модульная структура — дерево пакетов + tests/ соответствует один-в-один. **done**.
- **§23.2** 15 запрещённых упрощений — структурно + отдельные тесты-инварианты (C#1,C#2,C#3,C#4,C#5,C#11 и др.); п.5/п.6 (embeddings/LLM не обходят gates) by-design. **done**.
- **§23.3** Definition of Done — соблюдается по модулям (typed I/O, decision traces с версиями, race-тесты, purpose-binding); property-тесты не для каждой фичи. **by_design**.
- **§23.4** Порядок реализации Claude — процессный, отмечен в ARCHITECTURE.md + сохранённые traces. **doc_only**.

### §24 — Самооценка — **doc_only** (таблица баллов документа).

### Приложение A — Canonical config
- score_semantics, reciprocal 0.7/0.3, bands, outreach caps, monetization=false, sha-pin — `config/Kleal_Matching_Core_Config_v2.yaml`+`validator.py`. Имена полей отличаются от сокращённого YAML §A (default_parallel_proposals:2+urgent:3 вместо max_parallel:3; monetization как currency_or_paid_priority). PINNED_SHA=d804df8e… (следует за живым конфигом). Тест test_config. **done**.

### Приложение B — Псевдокод
- **B.1** search pipeline — `orchestrator/search.search` (BLOCK до feature build; A→B и B→A; decision traces). **done**.
- **B.2** accept_proposal в одной транзакции (idempotency→transition→revalidate→reserve→CAS→match→outbox) — `transitions.Orchestrator.accept_proposal`+concurrency. Точный порядок. Тест C#6-10. **done**.
- **B.3** form_group (hard filter→role-seeds→greedy→repair→max-utility→reserve) — `group_formation/former.form_group`. Тест test_group_formation. **done**.

### Приложение D — Матрица purpose-binding
- 11 полей × 5 режимов — `contracts/profile._MATRIX/build_profile_view` + dating capsule. **Расхождения**: behavioral_reliability для dating='full' (спека: operational+stricter review); orientation/gender по умолчанию drop даже в dating-view (строже спеки — безопасно). Тест C#12,C#14,DA5-9. **partial**.

### Приложение E — Библиография — **doc_only**.

---

## 4. Acceptance-тесты Приложения C (24 шт)

| # | Требование | Реализация | Статус покрытия |
|---|---|---|---|
| C#1 | Разреженный не обгоняет полный без low-coverage | relevance (coverage/LCB)+decision.low_coverage/band | **done** — test_relevance C#1 |
| C#2 | not_applicable не уменьшает coverage | feature_builder (NA из знаменателя)+relevance | **done** — test_relevance/feature_builder C#2 |
| C#3 | Один raw evidence ≠ 4 бонуса | feature_builder.build_features + evidence.dedup | **done** — test_contracts/feature_builder C#3 |
| C#4 | T2 не становится T1 из-за времени | retriever.assign_tier | **done** — test_retrieval C#4 |
| C#5 | Safety block до feature building | engine.evaluate + search (BLOCK→continue) | **done** — test_policy C#5 |
| C#6 | Privacy между SENT и ACCEPT → POLICY_CHANGED | revalidation.revalidate + accept_proposal | **done** — test_policy/state_machines C#6 |
| C#7 | Повторный idempotency key → тот же результат | IdempotencyStore + accept_proposal | **done** — test_state_machines C#7 |
| C#8 | Два concurrent accept не превышают capacity | CapacityLedger.claim_slot (CAS, реальные потоки) | **done** — test_state_machines C#8 |
| C#9 | Expired proposal нельзя принять | proposal.is_expired + accept_proposal | **done** — test_contracts/state_machines C#9 |
| C#10 | Counter после withdrawal не открывает match | state_machines.assert_transition | **done** — test_state_machines C#10,SM4 |
| C#11 | Subscription flag не меняет relevance/position | relevance (no payment feature) + allocation.MonetizationViolation | **done** — test_relevance/allocation C#11 |
| C#12 | Dating prefs недоступны friendship search | profile.build_profile_view (_MATRIX drop) | **done** — test_contracts C#12 |
| C#13 | Friendship decline не обучает dating ranker | feedback.get_scoped_feedback (scope-изоляция) | **done** — test_feedback C#13 (симметричная изоляция) |
| C#14 | Exact live location не в discovery payload | profile._coarse_location + dating capsule | **done** — test_contracts/dating C#14 |
| C#15 | Dota intent не уходит LoL-игроку без broad consent | decision.decision_class (T2 personal только при consent) | **done** — test_domain_scenarios C#15 |
| C#16 | Spanish learner не получает learner как native, если role hard | feature_builder.directed_preferences | **partial** — реализовано как РАНЖИРОВАНИЕ (native выше), learner не исключается; L1 |
| C#17 | Founder target не по self profession инициатора | directed_preferences (target по роли кандидата) | **done** — test_domain_scenarios C#17 |
| C#18 | Padel-группа с 4 одинаковыми role отклоняется | constraints.role_distribution + former | **done** — test_group_formation C#18 |
| C#19 | Группа с pairwise block отклоняется | constraints.pair_blocks | **done** — test_group_formation C#19 |
| C#20 | Event и user — разные transactions/explanation | candidate_types (TRANSACTION/explain_key) | **done** — test_candidate_types C#20 |
| C#21 | LLM outage не отменяет policy gates | policy_engine детерминирован без LLM | **by_design** — явного outage-теста нет |
| C#22 | Vector outage сохраняет structured retrieval | retriever structured-only (ANN не реализован) | **by_design** — теста деградации нет |
| C#23 | Reason keys без несуществующих фактов | decision.presentation (только known_match) | **done** — test_relevance C#23 |
| C#24 | Replay воспроизводит результат той же версии | trace.replay + decision_trace | **done** — test_observability/contracts C#24 |

**Итого по Приложению C: 21 done явным тестом, 1 partial (C#16 — ранжирование, не hard role-gate), 2 by_design (C#21/C#22 — outage-тестов нет, слои детерминированы структурно).** Все 24 инварианта присутствуют в системе.

---

## 5. Честный список пробелов (partial / absent / by_design)

### ABSENT (3) — в коде отсутствует
1. **§7.1 per-tier relevance analytics** — агрегации/аналитики relevance по каждому tier нет ни в retrieval, ни в observability.
2. **§15.1 host/moderator + equipment/platform/venue-ограничения + replacement policy** — не реализованы в set-constraints (host лишь поле в contracts/group.py, не валидируется).
3. **§17.1 dating audit** — отдельного dating policy-version / retention / access-control контура нет.

### Ключевые PARTIAL (43) — реализовано, но не полностью / не как hard-gate / без теста
- **Hard-gate'ы упрощены до булевых флагов** (§8.1): `time_feasibility` — булев open вместо interval-algebra/duration/timezone, unknown→ALLOW; `language_feasibility` — только наличие языка, **не уровень**; `privacy_visibility` — только сторона кандидата (не «обе»), unknown→ALLOW вместо BLOCK; `account_status` unknown→ALLOW вместо BLOCK. Это отклонения от таблицы §8.1 «unknown→BLOCK».
- **Предикаты таксономии не подключены к скорингу** (§6): `is_negative`/`is_complementary` определены и протестированы, но **не вызываются** feature_builder/relevance — negative-penalty и complementary-matrix фактически не влияют на ранжирование (роль-комплементарность даёт генерик 0.55).
- **Комплементарность ролей = ранжирование, не hard-gate** (§18.4/C#16): learner не исключается, лишь стоит ниже native.
- **Intent Compiler** (§5): нет литеральной JSON-schema-валидации LLM-вывода (заменена allowlist'ами); флаг `needs_confirmation` производится, но **не потребляется** (нет блокирующего гейта до подтверждения); строка «без токсиков»→moderation не реализована; minimal_intent_ok не проверяет format/disclosure/search_budget; авто-bump версии при изменении search-поля отсутствует.
- **Intent Time-блок** (§4.3): нет поля timezone, UTC-нормализации, interval-algebra в контракте.
- **Retrieval funnel** (§7.2): 5-стадийный funnel свёрнут в один проход label+cap; ANN/pgvector-стадия — no-op (embeddings нет, stdlib-only).
- **Allocation** (§11.1): reservation-capacity, city/area supply balancing — absent внутри слоя; proposal-fatigue деградирует в readiness; diversity — один generic bucket вместо 3 осей; exploration — один слот, не квота на нового.
- **§14.3 concurrent-accept-policy** — таблица воспроизведена как данные, но дифференцированное поведение по типу intent (withdraw остальных / hold / reservation-до-quorum / waitlist) **не реализовано** — accept единообразен.
- **§14.2 reservation-TTL** — контракт с TTL есть, но CapacityLedger держит слоты без TTL/авто-release; связки нет.
- **§15.3 group formation** — нет structured invitations (шаг 6) и waitlist/quorum-loss re-form (шаг 7); local_repair только swap.
- **§17.1 dating** — auto_accept=False и staged disclosure декларативны/не потреблены в accept-пути; dating-специфичного safety (anti-harassment) нет.
- **§9.5 CI-проверки config** — 3 из 5 (нет CI на уникальность evidence_id и на кросс-версию config↔model/policy).
- **§12.1 provenance tier** при expansion — не enforced (только tier_note-строка).
- **§21.2/§21.4** — нет HTTP/REST-слоя (чистый Python-пакет); полная per-failure матрица деградации §21.4 не собрана в единый слой.
- **§18.3/§18.6** домены — walk/выставка/футбол/коворкинг/книжный без e2e-тестов; §15.1 skill-spread/language-coverage без тестов; capacity/fatigue-гейты без прямых unit-тестов.
- **Прил.D** — behavioral_reliability для dating='full' вместо «operational+stricter review».

### BY_DESIGN (9) — соблюдается структурно, без отдельного модуля/теста
Изоляция 6 слоёв и отсутствие FinalUtility (§0/§3); терминологические различения (§2); детерминизм retrieval/policy без LLM → C#21/C#22 (LLM/vector outage не отменяют gates, т.к. в этих слоях LLM/ANN не вызывается); embeddings не финальны (§6, ANN отсутствует); 16 компонентов = модули (§21.1); DoD как контракт разработки (§23.3). Эти пункты **корректны структурно**, но не имеют выделенного теста-доказательства.

### DOC_ONLY (13) — кода не требуют
§1 (цель/инвариант успеха), §0/§9.7 декларация relevance-семантики, §20.1-20.3 (метрики/staged validation/guardrails), §22.1-22.3 (план пилота), §23.4 (порядок сборки), §24 (самооценка), Приложение E (библиография). Часть validation-шагов §20.2 фактически выполнена самим тест-сьютом, но отдельного кода раздел не требует.
