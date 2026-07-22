# Kleal — reciprocity, readiness, вероятность результата (§10)

**§10 intro + §10.1 + reciprocity уже реализованы в sha-пиннутом `core_v2.py`.** На orchestration-слое
добавлены только read-only объяснение готовности, прозрачные completion-факторы (§10.2) и декларация
ML-границы (§10.3). Проверено `C10-*`.

## §10 intro: relevance ⟂ readiness — EXACT (не складываются)
Relevance = «подходит ли кандидат задаче» (`lcb`/band из `directional_score`). Readiness = «готов ли
человек получать предложение сейчас». **Никогда не суммируются:** readiness — это (1) гейт
(`can_outreach` требует `open_now`; send-boundary тоже) и (2) отдельный ключ сортировки
(`READINESS_RANK` в кортеже `(BAND_RANK, READINESS_RANK, −reciprocal, −lcb, −coverage, name)`), но не
слагаемое `lcb`. Reciprocity `0.7·min+0.3·mean` — тоже relevance-величина (§9.4).

## §10.1 Шесть состояний receiving readiness — EXACT (`core_v2.readiness_state`)
`open_now` / `open_later` / `passive_discovery` / `busy` / `paused` / `unknown` — все шесть эмитятся,
**domain-dependent** (через `receiving.allowed_domains`: открыт к language practice, закрыт к dating →
`passive_discovery` для закрытого домена). Только `open_now` разрешает personal outreach.
`kcf.READINESS_EXPLAIN` **объясняет** каждое состояние на карточке (`readiness_explain`) — не пересчитывает.
Видно в `GET /api/agent/weights.readiness_states`.

## §10.2 Completion factors — ПРОЗРАЧНЫЕ сигналы, НЕ социальный рейтинг
`kcf.completion_factors(candidate, intent)` — набор независимых **именованных** operational-сигналов;
**НЕТ агрегата / «балла человека»** (`aggregate_score: None`). Из семи спека-сигналов данные есть у трёх:
| Сигнал | Источник | Состояния |
|---|---|---|
| availability_fresh | `lastActiveDays` (≤3) | fresh / stale / unknown |
| capacity_headroom + active_plans | `pending` vs MAX_PENDING=6, `receiving.proposal_budget` | has_headroom / near / at_capacity |
| technical_compat | `formats` при online-интенте | compatible / incompatible / **unknown** (не предполагаем) / not_applicable |

Остальные честно `not_collected`: `response_latency` (нет поля; **молчание/`expired_no_response`
нейтрально, НЕ читается как latency**), `recent_no_show` (нет истории; decline-cooldown — это гейт, не
рейтинг), `min_duration_capability` (только на стороне искателя), `host_venue_room` (post-pilot).

**Инвариант «не непрозрачный социальный рейтинг»** (тесты `C10-CF-*`): completion_factors **НИКОГДА** не
читает safety-reports / sensitive-inferences / single-negative-reviews. Исключаемые поля перечислены явно и
по РЕАЛЬНЫМ именам (`excludes`): `safetyFlags/sensitivity/accountStatus/suspended`,
`blocksMe/declinedOwnerDaysAgo`, `slots/visibility` — и ни одно их значение не попадает в сигналы.

## §10.3 Переход к ML — декларация границы (`kmlb.ML_BOUNDARY`)
6-слойный roadmap (§10.3): L1 intent-classification, L2 retrieval-recall = `future`; L3 P_response, L4
P_accept (по направлениям+доменам), L5 P_completion, L6 LTR+off-policy = `blocked_calibration`.
**`P_response/P_accept/P_completion` = `absent_by_design`** — не стабятся в placeholder-вероятность (тест
`C10-ML-PROB`). Инвариант **no_model_in_gates**: hard gates / privacy / purpose binding / block / capacity
/ disclosure остаются детерминированной политикой и не отдаются модели — проверено **рантайм-статикой**
(`C10-NOMODEL`: в исходниках гейтов нет `llm_complete`). Видно в `weights.ml_boundary`.

## Статус (честно): **done_core_v2 8 · done 6 · partial 5 · pilot_disabled 1 · blocked_calibration 4**
- **done_core_v2:** §10 intro (relevance⟂readiness), 6 состояний readiness, domain-dependence, reciprocity.
- **done (в §10):** readiness_explain, completion_factors (3 доступных сигнала, no-rating инвариант),
  ml_boundary + no_model_in_gates, P_* absent_by_design.
- **partial (5):** 4 из 7 completion-сигналов ждут сбора данных (response_latency, no_show, min_duration
  capability со стороны кандидата, budget-context).
- **pilot_disabled (1):** host/venue/room для group/event.
- **blocked_calibration (4):** calibrated P_response/P_accept/P_completion + learning-to-rank (нужны данные
  + версия модели).

Тесты: `services/matching/test_core_v2.py` — `C10-*` (11 проверок).
