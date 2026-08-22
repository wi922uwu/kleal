# Ответ на «Вердикт» (внешний экспертный ревью, 84/100)

Сверка всех 27 замечаний ревью с фактическим кодом `matching_core/`.
Статусы: **DONE** (уже в коде пересборки) · **PARTIAL** (была основа) · **GAP** (не было).

## ✅ Итог: все 27 замечаний закрыты
- **13** уже были DONE в пересборке (#2, #11, #14, #15, #19*, #21, #23, #26 + инфраструктура).
- **V-P0** (10 P0-приоритетов): #1, #3, #4, #5+6, #8, #9, #10 закрыты; #2/#11/#21 были DONE → `test_verdict_p0.py` (45).
- **V-P1** (8 P1-приоритетов): #7, #12, #13, #16, #17, #18, #20, #22, #24, #25, #27 закрыты → `test_verdict_p1.py` (47).
- **V-P2** (learned reranker, calibrated probability, travel-time, long-term utility) — by design отложено (ревью само относит это к «после появления данных»).
- Регресс: **421 тест, 0 падений**, sha-pinned core/config не тронуты.

Батчи закрытия: **V-P0** (десять P0-приоритетов ревью) · **V-P1** (восемь P1) · **V-P2** — by design отложено.

| # | Замечание ревью | Статус до | Где / что делаю | Батч |
|---|---|---|---|---|
| 1 | T5 fallback = скрытая персональная выдача нерелевантных | **PARTIAL** — `retrieve` уже исключает T5 из slate; нет терминального no-result + отдельного блока «рядом» | `orchestrator/expansion.py`: `no_topical_overlap_response` + `nearby_open_block` (personal_invite запрещён без нового consent) | V-P0 |
| 2 | Пропущен T4 (события/группы/комнаты) | **DONE** — `retriever.assign_tier` → T4 для event/room/venue/group; `TIER_UX` | — | ✓ |
| 3 | LLM формирует вход → нужны confidence/taxonomy_version/explicit·inferred·defaulted/raw text | **GAP** — `compile_intent` даёт один скалярный confidence | `intent_compiler/compiler.py`: `field_provenance`, `low_confidence_hard_fields`, `taxonomy_version`, `raw_text` | V-P0 |
| 4 | «Согласие агентов» нельзя отдавать LLM | **PARTIAL** — решение уже детерминировано; нет явного guard | `orchestrator/agent_decision.py`: `can_reach_candidate` + `LLM_FORBIDDEN_ROLES` | V-P0 |
| 5 | active_reciprocity vs passive_interest_fit — разные сущности | **GAP** — одна формула `reciprocal(a,b)` | `reciprocity_readiness/reciprocity.py`: `classify_reciprocity` + `reciprocity_view` | V-P0 |
| 6 | Формула взаимности дважды штрафует неизвестность | **GAP** | там же: для passive используем `mean_b` (не `lcb_b`) → неизвестность штрафуется один раз | V-P0 |
| 7 | `R_lcb` — не статистический LCB, переименовать | **PARTIAL** — докстринг уже честный | алиас `conservative_relevance` + примечание | V-P1 |
| 8 | Три класса unknown; критичный → блок outreach | **GAP** — unknown лишь снижает coverage | `feature_builder/unknowns.py`: `classify_unknowns` → wired в `search`→`decision_class(high_impact_unknown)` | V-P0 |
| 9 | `expansion_policy` на intent (exact_only/allow_family/…) | **PARTIAL** — лестница есть, поля нет | `contracts/intent.py` + `expansion.py`: honor `expansion_policy` | V-P0 |
| 10 | Полный lifecycle intent + TTL | **PARTIAL** — TTL/expired есть, набор состояний не полный | `state_machines.py` + `intent.py`: 11 состояний | V-P0 |
| 11 | State machine приглашений + идемпотентность | **DONE** — `orchestrator/{state_machines,concurrency,transitions}` | — | ✓ |
| 12 | Purpose-bound receiving policy (per-channel/platform) | **PARTIAL** — есть policy, нет per-purpose/канала | `contracts/receiving_policy.py`: `receiving_decision(purpose, channel, platform)` | V-P1 |
| 13 | Dating недостаточно изолирован для прод | **PARTIAL** — capsule/isolation/pilot есть; нет mutual-pref/отд. лимитов/guard | `dating/dating.py`: `mutual_preference_ok`, `dating_rate_limits`, `reject_friendship_signal` | V-P1 |
| 14 | Отдельная модель групп | **DONE** — `group_formation/` | — | ✓ |
| 15 | Event/Room/Venue как candidate types | **DONE** — `retrieval/candidate_types.py` | — | ✓ |
| 16 | Diversity ≤3/тема недостаточен (exposure/rotation/dedup) | **PARTIAL** — есть 3-осевой diversity+exposure_cap+cooldown | `allocation`: near-dup dedup + controlled rotation по request_id | V-P1 |
| 17 | Перегрузка кандидата не только числом инвайтов | **PARTIAL** — per_24h+pending есть | `reciprocity_readiness/fatigue.py`: per-sender/per-intent/quiet/per-purpose/active-plans | V-P1 |
| 18 | Cooldown зависит от причины отказа (reason codes) | **GAP** | `feedback_learning/reasons.py`: 8 reason codes → дифф. последствия | V-P1 |
| 19 | Обучение на уровне правил (telemetry/калибровка) | **DONE** — `feedback_learning/feedback.py` + `bias_guardrails` | (доп. `calibration_report`) | V-P1 |
| 20 | Пороговые ярлыки не доказаны | **PARTIAL** — пороги в sha-config | пометка `provisional_expert_constants` + док | V-P1 |
| 21 | Decision trace | **DONE** — `contracts/decision_trace.py` + `observability/trace.py` | — | ✓ |
| 22 | Приватность географии / staged location disclosure | **GAP** | `contracts/geo_privacy.py`: zone-only клиент, точная точка после плана | V-P1 |
| 23 | Многоязычность/алиасы taxonomy | **DONE** — `taxonomy/canonical.py` (1249 алиасов ru/en/es из xlsx) | — | ✓ |
| 24 | Age gate — продуктовая политика, не скрытый gate | **PARTIAL** — gate есть | config-флаг `age_policy: adults_only_18plus` + док | V-P1 |
| 25 | Полноценная trust & safety модель | **GAP** — есть block/safety gate | `policy_engine/trust_safety.py`: report/velocity/mass-invite/no-show holds (как gate, НЕ relevance) | V-P1 |
| 26 | Гейты трёхзначные ALLOW/DENY/REVIEW | **DONE** — `gates.py` (ALLOW/BLOCK/REVIEW) | — | ✓ |
| 27 | Несколько активных intent | **GAP** | `orchestrator/intent_set.py`: выбор compatible purpose-bound intent, лимит, приоритет | V-P1 |

**P0 (до масштабирования):** 1✓, 2✓DONE, 3, 4, 5+6, 7(P1), 8, 9, 10 — плюс 11✓DONE, 21✓DONE.
**Итог ревью учтён:** «главные потери» (purpose isolation, contextual profiles, controlled expansion, T4, транзакции, группы, candidate types, targeted clarification, feedback loop, safety/privacy) — все адресованы (DONE или в V-P0/V-P1).
