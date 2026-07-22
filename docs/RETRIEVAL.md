# Kleal — candidate retrieval и semantic tiers (§7)

Реализовано в [`services/matching/app.py`](../services/matching/app.py) как **read-only слой над
запечатанным скорером** (`core_v2.py` sha-пиннут). Слот: между построением `eligible` (после hard-gates) и
`_core.search`. Ничего в детерминированном score/tier не меняется — всё аддитивно.

## Несущая гарантия: slate не меняется
`core_v2.search` делает **тотальную** сортировку (`BAND_RANK, READINESS_RANK, -reciprocal, -lcb, -coverage,
name`) + `_slate` диверсификацию (TOP_N=8). Поэтому **порядок retrieval невидим** для выданного slate —
изменить его может только **выбрасывание** overlapping-кандидата. Retrieval-бюджет устроен так, что:
- дефолт `500` ≫ прод-стора (~100) — на пилотном масштабе **никогда не срабатывает** (no-op);
- сортировка по retrieval-приоритету (reciprocal → direct → parent/adjacent → **no-overlap хвост**) — если
  бюджет всё же режет, отбрасывается только no-overlap хвост (best=0 → T5), который движок и так не
  показывает → slate byte-identical;
- `_expand_fallback` (§12) получает **полный** eligible-пул, не урезанный бюджетом — иначе never-dead-end
  сломался бы.

Проверено фальсифицируемо: `C7-BUDGET-BITE` — бюджет `2` из `5` реально режет, но slate идентичен дефолтному
(отброшены только 3 no-overlap).

## §7.1 Порядок источников (`_retrieval_source`, `RETRIEVAL_SOURCES`)
Каждой карточке аддитивно ставится `retrieval_source`:
| # | Источник | Статус |
|---|---|---|
| 1 | active_intent_match — собственный активный intent кандидата реципрокно совпал (`_reciprocal`) | ✅ live |
| 2 | active_receiving_direct_interest — прямой интерес (best≥4) | ✅ live |
| 3 | groups_with_capacity | ⛔ pilot-disabled (§15 group formation) — retrieves zero |
| 4 | events_and_rooms | ⛔ pilot-disabled (§16); выражен как **T4 alternative** (онлайн-комната) |
| 5 | parent_adjacent_expansion — parent/sibling/adjacent (best 1-3), только при разрешённом расширении | ✅ live |

## §7.1 Таблица tier T0–T5 (immutable provenance)
Tier назначает `core_v2.assign_tier` (T0 реципрокный / T1 exact / T2 parent+sibling / T3 adjacent / T5
none) — неизменяемый provenance, логистика его не повышает. **T4 alternative-solution-type** — не человек, а
другой способ закрыть intent: помечает онлайн-комнату в `_online_fallback` (`tier:"T4",
kind:"alternative_solution_type", retrieval_source:4`, без personal outreach).

**Аналитика внутри каждого tier** (`_tier_analytics`, в ответе `explain_match.tier_analytics`): по каждому
tier — count + распределение lcb (mean/min/max) + coverage_mean. Спека требует мерить relevance **отдельно
внутри tier** — реализовано.

## §7.2 Retrieval budgets (`RETRIEVAL_STAGES`, `_retrieve`)
Семиэтапный конвейер задокументирован в ответе (`retrieval.stages`), фактический staged-cut — на этапе
structured_retrieval:
| Этап | Механизм | Пилот | LLM |
|---|---|---|---|
| hard_prefilter | in-memory policy gates + geo radius (**SQL/PostGIS/H3 = infra, отложено**) | 1000→100-250 | нет |
| structured_retrieval | taxonomy overlap + active intents, order by source, cap by budget | 100-250→30-80 | нет |
| ann_recall | pgvector embeddings — **INFRA, вне stdlib-прототипа** (`status: blocked_infra`) | +top 50 | нет |
| feature_build | `core_v2.build_features` (7 канонических групп) | 30-80→10-30 | нет |
| ranking_slate | `core_v2` directional/reciprocal + `_slate` TOP_N=8 | 10-30→3-8 | нет |
| explanation | reason keys → NL (`_presentation`), только финальный slate | — | опц. |
| agent_probe | negotiate top-кандидатов | top 1-3 | small |

## Статус (честно) — было ✅6·🟡7·⬜3 → стало ✅12 · 🟡2 · blocked_infra 1 · pilot_disabled 1
- **✅ добавлено:** источники 1/2/5 (retrieval_source), источник 4 как T4-альтернатива, tier-table T4,
  structured-retrieval staged-budget (с гарантией неизменности slate), **аналитика relevance внутри tier**
  (закрыт ⬜), staged-pipeline отчёт.
- **🟡 partial:** hard_prefilter (SQL/PostGIS/H3 — infra; детерминированный in-mem prefilter + бюджет —
  stdlib-эквивалент), agent_probe (сейчас negotiate top-5, не таргетированный probe top 1-3 неизвестных).
- **blocked_infra:** ANN recall (pgvector embeddings) — вне stdlib-прототипа.
- **pilot_disabled:** источник 3 (группы с capacity) — §15.

Тесты: `services/matching/test_core_v2.py` — `C7-*` (8 проверок, включая **C7-BUDGET-BITE** — фальсифицируемая
гарантия неизменности slate под режущим бюджетом).
