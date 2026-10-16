# Kleal Matching Core — чистая пересборка по спеке (§0–§24)

Реализация **строго по** `Kleal_Matching_Core_Final_Spec_RU_v2.md`. Модульная структура — по §23.1,
порядок сборки — по §23.4, инварианты — §23.2, Definition of Done — §23.3. Питон, stdlib-only,
детерминированный, без LLM в скоринге. Веса/пороги — только в sha-pinned `config/Kleal_Matching_Core_Config_v2.yaml`.

---

## §0. Главное решение (инвариант системы)
Matching Core **не считает «совместимость людей»**. Он находит реалистичный способ закрыть конкретный
`intent`, соблюдая взаимные ограничения, приватность, безопасность, доступность и допустимую нагрузку —
и честно показывает, где точное совпадение, а где поиск был расширен.

**Шесть независимых слоёв (§0/§3), ни один не компенсирует другой:**
`eligibility/policy → retrieval → relevance → reciprocity/readiness → allocation → transaction/presentation`.
Высокий смысловой fit НЕ отменяет block, отсутствие consent или заполненную capacity.

**Выходы системы — раздельные величины (§0), НЕ складываются в один `FinalUtility`:**
`policy_decision (ALLOW/BLOCK/REVIEW)` · `semantic_tier (T0–T5)` · `relevance_score (0–1 internal)` ·
`evidence_coverage (0–1)` · `reciprocal_relevance (0–1, не вероятность)` · `readiness_state` ·
`allocation_action` · `explanation_keys`.

## §1. Цель и границы
Цель — максимизировать число **состоявшихся, взаимно полезных, безопасных** взаимодействий (не клики/лайки).
**Инвариант успеха:** качественный outcome = completed interaction с положительным двусторонним feedback
либо добровольным повтором. **Отсутствие feedback ≠ негативный исход.**

## §2. Ключевые термины (§2)
`intent` (текущая задача, TTL) ≠ evergreen goal · `eligibility` (детерминированное право) ≠ высокая
релевантность · `semantic_tier` (путь нахождения) ≠ качество · `directional relevance` ≠ вероятность
принятия · `readiness` (готов сейчас) ≠ качество человека · `match` (взаимное согласие после ре-проверки)
≠ показ.

## §3. Последовательность принятия решения
1. Intent Compiler → подтверждённый structured intent + version.
2. Policy Engine → разрешённый profile view + ALLOW/BLOCK/REVIEW.
3. Retrieval → кандидаты по источникам + `semantic_tier`.
4. Feature Builder → уникальные evidence groups без double-count.
5. Relevance Engine → A→B (и B→A где допустимо) + coverage + conservative LCB.
6. Readiness/receiving policy → допустим ли outreach сейчас.
7. Allocation → slate + волны (fairness, fatigue, exposure).
8. Presentation → причины и gaps без скрытых данных.
9. Transaction Orchestrator → proposal/reservation + revalidation на каждом переходе.

---

## §23.1. Обязательная модульная структура (реализуется как Python-пакеты)
```
matching_core/
  contracts/    §4  — profile, intent, candidate, proposal, match, plan, decision_trace, evidence,
                       receiving_policy, relationship_edge, reservation, group
  config/       §9.5 — Kleal_Matching_Core_Config_v2.yaml (sha-pinned, лежит в <kleal-ms>/config/), schema.json, validator.py
  intent_compiler/  §5   taxonomy/ §6   retrieval/ §7   policy_engine/ §8
  feature_builder/  §6.1/§9.1        relevance_engine/ §9        reciprocity_readiness/ §10
  allocation/ §11   orchestrator/ §13/§14   group_formation/ §15   plan_coordination/ §14
  feedback_learning/ §19   observability/ §21.3 (decision trace)
  tests/ { fixtures, property, race, safety, domains }
```

## §23.2. Запрещённые упрощения (инварианты — не нарушать)
1. один `match_score`; 2. tier из score; 3. unknown как совпадение; 4. смешивать
safety/trust/fairness/payment с relevance; 5. embeddings как финальная истина; 6. LLM обходит hard gates;
7. свободные agent-диалоги вместо protocol events; 8. ранжировать группы средним pair score; 9. переносить
dating-данные в другие режимы; 10. проценты без калибровки; 11. веса в нескольких местах; 12. proposal без
receiving policy + revalidation; 13. write без idempotency/version; 14. ranking за подписку; 15. точная live
location в discovery.

## §23.3. Definition of Done (для каждого модуля)
typed input/output · explicit purpose + policy decision · config/model/policy version logged ·
unknown/not_applicable handled · deterministic reason keys · unit + property tests · race/idempotency test
для write-flow · privacy/safety test · ≥2 доменных фикстуры · degradation behavior · observable events ·
UX-copy отделён от системного решения.

## §23.4. Порядок реализации + прогресс
- [x] **0. Фундамент** — эта структура + инварианты (§0–§3, §23).
- [x] **1. contracts + config validator** (§4, §9.5, §21.3) — 12 контрактов + validator; 47 тестов (11+36).
- [x] **2. policy engine + state machines** (§8, §14) — 12 gates + tri-state + revalidation; 4 автомата + orchestrator; 42 теста (21+21).
- [x] **3. intent compiler / taxonomy / retrieval / feature builder** (§5, §6, §7, §6.1) — 4 модуля; 52 теста (16+9+16+11).
- [x] **4. deterministic relevance + transparent results** (§9, §9.7) — directional/reciprocal + decision/bands/presentation; 20 тестов.
- [x] **5. reciprocity/readiness + allocation + expansion + protocol** (§10, §11, §12, §13) — readiness/completion/ML-граница + rerank/fairness + expansion-ladder + typed protocol; 47 тестов (11+9+11+16).
- [x] **6. group formation** (§15) — set-constraints + least_misery utility + former (seed→greedy→repair→reserve); 12 тестов.
- [x] **7. events-rooms/venues (§16) / dating (§17) / feedback-learning (§19) / observability-trace (§21) / plans (§14) / ML-граница (§10.3)** — 6 модулей; 49 тестов.
- [x] **8. search() пайплайн (B.1) end-to-end + доменные фикстуры (§18) + decision traces** — `orchestrator/search.py` связывает все слои; 10 e2e-тестов.

**ЗАВЕРШЕНО. 25 сьютов, 428 зелёных тестов. Покрыто ~20/24 acceptance-тестов Приложения C явными тестами
(C#16 — как ранжирование, не hard-gate; C#21/#22 — by-design: policy/retrieval детерминированы без LLM/ANN).**

**+ Закрытие партиалов (батчи 1–3): 328→ тесты.
+ Ответ на внешний «Вердикт» (84/100) — все 27 замечаний закрыты (V-P0 45 + V-P1 47 тестов),
см. историю коммитов (разбор внешнего ревью удалён как устаревший, 2026-08-27). Новые модули: `orchestrator/{agent_decision,intent_set}`,
`reciprocity_readiness/{reciprocity,fatigue}`, `feature_builder/unknowns`, `feedback_learning/reasons`,
`contracts/geo_privacy`, `policy_engine/trust_safety`; расширены expansion/allocation/compiler/dating/
receiving_policy/state_machines/gates/decision/relevance.
+ Adversarial pre-ship review (16 агентов): найдено/подтверждено и исправлено 6 дефектов
(critical: high_impact_unknown глушил сильные T0/T1; trust velocity-cap; dedup до сортировки; off-taxonomy
prefix-fuzzy→фальшивый T1; vacuous-тест; dating low-conf токен) + 7 regression-тестов.**

_На каждом шаге: fixture suite зелёная + сохранённые decision traces (§23.4.8)._
