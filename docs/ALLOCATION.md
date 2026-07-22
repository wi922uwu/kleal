# Kleal — allocation, fairness, рыночная ликвидность (§11)

Реализовано в [`services/matching/app.py`](../services/matching/app.py) как **post-relevance / post-policy**
слой. Allocation решает, **кому и сколько показов/предложений** выдать после eligibility+relevance — и
**никогда не меняет смысл релевантности пары** (§11 intro) и **никогда не читает payment_status** (§11.3).

## Несущая гарантия: slate byte-identical при пилотных дефолтах
Финальный slate строит `core_v2.search` (sort `(BAND_RANK, READINESS_RANK, −reciprocal, −lcb, −coverage,
name)` → `_slate` диверсификация ≤3/bucket → top-8) — **sha-пиннут**. `_allocate(slate, ctx, pool)` работает
поверх, но **все механизмы — no-op при дефолтах** `ALLOCATION_CONFIG` (cap = 1e9, quota = 0, guard off), и
`_alloc_is_default(cfg)` возвращает **тот же объект списка**. Кусается только при явном `ctx['allocation']`
override (через ctx, **не** через sha-пиннутый конфиг — sha не меняется). Проверено фальсифицируемо:
`C11-ALLOC-NOOP`/`-BRANCH` (byte-identical, включая per-branch dormancy) + `C11-ALLOC-BITE` (тесная cap режет
только over-exposed, порядок выживших не меняется). RCV5 (busy виден), RCV9 (порядок), R1-7, PARITY зелёные.

## §11.1 Механизмы (9)
| Механизм | Статус |
|---|---|
| proposal-fatigue caps | **done_core_v2** — `readiness=busy` при received_24h≥cap |
| cooldown повторных предложений паре | **done/partial** — declined-cooldown (hard gate) + общий `pair_cooldown_days` (dormant, 0) на send-границе |
| diversity slate | **done_core_v2/partial** — `_slate` по одной оси (broad interest bucket); source-type/tier оси — dormant reorder |
| per-user exposure caps | **done** — `_exposure` лог (per-name, как `_proposals`) + dormant cap в `_allocate` |
| popularity-concentration guard | **done** — within-band **demote-only** (переприменяет frozen sort key), dormant |
| защита самых отзывчивых | **done** — `responsive_max_exposure` demote-only (никогда не boost — это был бы reputation-score в ранжирование, запрещён) |
| exploration quota | **done** — `_allocate` append (quota 0 → никого; никогда не фабрикует при пустом пуле) |
| reservation capacity (группы/urgent) | **pilot_disabled** — нужны group/reservation-сущности (§15) |
| city/area supply balancing | **pilot_disabled/partial** — `supply_max_per_area` dormant; `area` разрежён в демо |

Exposure-лог пишется на **send-границе** (`negotiate_candidates`, рядом с `_log_proposal`), НЕ в
`match_candidates` — так match остаётся чистым (детерминированный replay).

## §11.2 Порядок rerank (6 шагов)
1. Удалить BLOCK/expired/capacity-exceeded — BLOCK (`_policy_decision`), expired (`kc.is_expired`), T5
   (движок). **capacity-exceeded оставлен как `readiness=busy` (ВИДИМ, RCV5), а не буквально удалён** —
   осознанная byte-identity интерпретация (не «чинить» в drop). **done/partial**.
2. Sort по reciprocal+readiness — **done_core_v2** (frozen sort key).
3. Diversity — **done_core_v2** (`_slate`).
4. Exposure/fatigue caps — **done** (fatigue done_core_v2; exposure dormant).
5. Ограниченная exploration позиция — **done** (`_allocate`, quota 0 by default).
6. Propensity + причины allocation — **done** (`allocation_trace`): `{position, bucket, tier,
   readiness_class, exposure_count, fatigue_state, diversity_bucket, exploration, propensity:null,
   propensity_status:'absent_by_design', allocation_reasons[]}`. **propensity absent_by_design** (нет
   acceptance-probability — §9.4/§10.3). `allocation_trace` варьируется между вызовами (лог растёт) — любой
   full-card/replay diff обязан ИСКЛЮЧАТЬ его.

## §11.3 Инвариант монетизации — done_core_v2
`payment_status` запрещён как relevance/reciprocity/safety/allocation feature. В движке и `_allocate` нет ни
одного платёжного входа (grep пуст); `PAYMENT_INVARIANT` из sha-пиннутого конфига. Тест `C11-PAY-ALLOC`:
внедрённый `payment_status/subscription` не меняет ни slate, ни trace.

## Статус (честно): **done_core_v2 4 · done 1 · partial 5 · pilot_disabled 7 · blocked_calibration 1**
Механизмы присутствуют и dormant (кусаются под override); reservation-capacity + supply-balancing честно
pilot_disabled (нужна group/city инфра); propensity — blocked_calibration.

Тесты: `services/matching/test_core_v2.py` — `C11-*` (7 проверок).
