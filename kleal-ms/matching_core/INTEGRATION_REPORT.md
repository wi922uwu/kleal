# INTEGRATION_REPORT — ответ на «Аудит текущего Matching Core»

Аудит: архитектура ~94/100, но исполняемый end-to-end pipeline не собран — исправленные модули жили
отдельно и не были в живом `search()`. Задача: собрать authoritative end-to-end контракт и устранить
runtime-несостыковки, **не переписывая**. Все 17 пунктов закрыты.

**Единый production entrypoint:** [`orchestrator/pipeline.py`](orchestrator/pipeline.py) → `run_search`
(поиск), `run_dating_search` (dating), `authorize_and_send` (outreach). `orchestrator/search.search()`
делегирует в него. **Тесты:** 27 сьютов, **541 зелёный, 0 падений**; ключевые — `tests/test_pipeline.py`
(P0/P1 property-тесты) и `tests/test_integration_e2e.py` (7 полных сценариев flow).

Для каждого пункта: **где · entrypoint · тест · какой старый bypass невозможен**.

## P0

| # | Где исправлено | Production entrypoint гарантирует | Тест | Старый bypass теперь невозможен |
|---|---|---|---|---|
| **1** authoritative orchestrator | `pipeline.py` (`run_search`, `_Run.enforce`, `SEARCH_STAGES`) | Единственная реализация скоринга; `enforce(SEARCH_STAGES)` бросает при пропуске стадии | `test_pipeline` P1 (no-bypass) | Нельзя выполнить скоринг в обход стадий — `search()` больше не содержит своей копии логики |
| **2** нет loose-параметров | `pipeline.run_search` (contract enforcement) | purpose/broad_consent из intent snapshot; `now`/`search_id` обязательны; mismatch → `PipelineError` | `test_pipeline` P2 | Подтверждённый dating/networking-intent не может молча стать `friendship` |
| **3** eligibility до budget | `policy_engine.engine.hard_prefilter` → `pipeline` стадия `pre_policy` | Cheap hard-eligibility по ВСЕМУ пулу ДО retrieval-бюджета | `test_pipeline` P3 | Budget не отрезает допустимого кандидата за хвостом заблокированных (ложный no-result) |
| **4** единый semantic source | `taxonomy/graph.similarity` (canonical-first) | Canonical авторитетен; seed — только fallback; один resolver для similarity/tier/features | `test_pipeline` P4 | Нет двух параллельных семантических истин; seed не может «параллельно» решить известную канону пару |
| **5** reciprocity_view в live | `pipeline` (`classify_reciprocity` + `reciprocity_view`) | active/passive взаимность в самом ranking; passive — `mean_b` | `test_pipeline` P5 | Неизвестность у пассивного кандидата не штрафуется дважды поверх `R_lcb` |
| **6** typed dispatch T4 | `pipeline.typed_dispatch` + `_typed_relevance` | T4 не person-моделью; своя typed-функция; отдельная `alternatives`-дорожка | `test_pipeline` P6 · `e2e` E2E6 | Событие/комната/группа не попадают в person top-N и не оцениваются person feature model |
| **7** dating не в обход wrapper | `pipeline` (`_DATING_AUTH`, `run_dating_search`) | Токен авторизации; generic dating без него → `PipelineError` | `test_pipeline` P7 · `e2e` E2E2 | Нельзя запустить dating-скоринг мимо consent/capsule/bilateral-gates/limits |
| **8** fail-closed REVIEW | `pipeline` (REVIEW→quarantined) + `decision.is_personal` | BLOCK→never; REVIEW→только quarantined discovery, никогда personal; runtime-guard | `test_pipeline` P8 | REVIEW-кандидат не может получить personal outreach |
| **9** revalidation before-send | `pipeline.authorize_and_send` (`revalidate("before_send")`) | Перед отправкой — proposal auth + revalidation baseline↔current | `test_pipeline` P9 · `e2e` E2E1/E2E3 | Нельзя отправить proposal без свежей проверки состояния кандидата |

## P1

| # | Где исправлено | Production entrypoint гарантирует | Тест | Старый bypass теперь невозможен |
|---|---|---|---|---|
| **10** expansion в permissions | `pipeline.may_present` / `permission_layers` | retrieval-eligible ≠ present-as-fallback ≠ outreach; present гейтится expansion_policy | `test_pipeline` P10 · `e2e` E2E7 | При exact-запросе система не может сама показать adjacent T3 из пула |
| **11** readiness-sort пересмотрен | `allocation.rerank` (`DCLASS_RANK` первым) | Порядок: quality(decision_class)→reciprocal→readiness→lcb→coverage | `test_pipeline` P11 | `open_now` не поднимает посредственного кандидата над сильным-но-занятым |
| **12** quality floor exploration | `allocation.exploration_eligible` | exploration только выше min relevance/coverage, не `no_outreach`, tier/decision_class неизменны | `test_pipeline` P12 | exploration-слот не промоутит кандидата ниже floor / того, кому нельзя писать |
| **13** field-specific confidence | `compiler.FIELD_CONFIDENCE_RULE` / `low_confidence_hard_fields` | Правило на поле: dating/safety/sensitive — explicit only; format 0.8; activity 0.65 | `test_pipeline` P13 | Нельзя молча принять inferred dating/safety/sensitive-поле «на 0.61» |
| **14** один вопрос за turn | `clarification.next_question_turn` / `clarification_sequence` | ≤1 основной вопрос за turn; после ответа — пересчёт и следующий | `test_pipeline` P14 | Конфликт «блокируют запуск» vs «один вопрос» устранён (несколько unknown — за несколько turn) |
| **15** один lifecycle source | `intent.LIFECYCLE_STATES` (single) + `state_machines.advance_intent_lifecycle` | State machine — авторитет; `lifecycle_state()` — read-only проекция; дрейф ловится на импорте | `test_pipeline` P15 | Нет двух автоматов/списков состояний; состояние меняет только `assert_transition` |
| **16** trace обязателен в prod | `pipeline.run_search` (`mode="production"` auto-trace) | Production auto-создаёт decision trace; отключаемо только benchmark/test | `test_pipeline` P16 | Нельзя выполнить production-поиск без аудируемого следа |
| **17** end-to-end тесты | `tests/test_integration_e2e.py` (7 сценариев) | Прогон полного flow через реальные entrypoints | `e2e` E2E1–E2E7 (15 ассертов) | Исправления доказанно защищают user-flow, а не лежат отдельными модулями |

## Что сохранено (аудит просил НЕ переписывать)
Нет единого FinalUtility · immutable tier · 4 состояния evidence · unknown≠match · purpose-bound ProfileView ·
T5 terminal · separation relevance/readiness/allocation · payment не влияет · deterministic gates · LLM только
parse/explain · transaction idempotency+CAS+outbox · groups как set · isolated dating · geo privacy · reason
codes · human-readable bands. Всё на месте.

## Статус
- **НЕ задеплоено, НЕ в PR** — по требованию; ждёт апрув.
- Регресс: **27 сьютов / 541 зелёный / 0 падений**. sha-pinned config не тронут.
