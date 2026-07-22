# Kleal — transaction state machines & race protection (§14)

Транзакции подбора — **типизированные конечные автоматы** с оптимистичной конкуренцией, идемпотентностью и
детерминированным разрешением гонок. Реализовано в [`shared/kleal_states.py`](../shared/kleal_states.py) (`ks`,
keyless, **LLM-free**, детерминированный — часы инъектируются, нет FS/секретов/`core_v2`) + аддитивная проводка
в `matching/app.py`. Слой **не меняет** sha-pinned движок и не меняет surfaced slate: все stamps — новые ключи
(`state`/`version`/`txn`/`match_state`), NEG1-4 / C4-SEND1 / C13 остаются byte-identical.

## §14.1 Четыре автомата
`STATE_MACHINES` — ровно 4 машины (states / initial / terminal / transitions), deny-safe валидатор:
- **intent** (7): `DRAFT→CONFIRMED→SEARCHING⇄WAITING→SATISFIED|EXPIRED|CANCELLED`.
- **proposal** (10): `CREATED→(RESERVED)→SENT→VIEWED→ACCEPTED|DECLINED|COUNTERED|WITHDRAWN|EXPIRED|POLICY_REVOKED`.
- **match** (8): `PENDING_DISCLOSURE→MUTUAL→CHAT_OPEN→PLANNING→PLANNED→COMPLETED|CANCELLED|SAFETY_CLOSED`.
- **plan** (8): `DRAFT→PROPOSED→PARTIALLY_CONFIRMED→CONFIRMED⇄CHANGED→COMPLETED|CANCELLED|NO_SHOW` — **`enabled:False`**
  (group/plan выключены в пилоте §1.2/§15/§16; таблица определена для конформанса).

`can_transition/next_state/apply_transition` — легальные рёбра проходят, нелегальные (выход из terminal,
пропуск состояния) и unknown entity/state отбиваются (**deny-safe**). `apply_transition` — **аддитивный**: ставит
`state`, инкрементит `version`, НИКОГДА не трогает `status`/`agree`/`reason`/`name`. `ACTION_TO_STATE` мостит §13
действия на рёбра Proposal и добавляет двух недостающих продюсеров — `WITHDRAW`/`EXPIRE`.

## §14.2 Гарантии (single-process, честно)
- **Optimistic concurrency (CAS).** `check_version`/`compare_and_swap(obj, entity, to, expected_version)` — первый
  accept на ОДНОМ объекте выигрывает (`version→2`), второй с устаревшим `expected_version` → `VERSION_CONFLICT`.
  ⚠️ Per-object CAS **не** обеспечивает 1:1-эксклюзивность между РАЗНЫМИ кандидатами (оба стартуют с `version:1` —
  оба CAS прошли бы). Эксклюзивность между кандидатами держит общий слот (`claim_slot`, ниже), не CAS.
- **Idempotency.** `dedup_key(entity, id, action[, extra])` — **clock-free** и включает **action** (WITHDRAW-после-
  ACCEPT на той же паре ≠ дубликат ACCEPT; §4 `idempotency_key` этого не различал, т.к. опускал action и вшивал
  `int(now)` в `proposal_id`). `dedup(seen, key)` — повтор возвращает СОХРАНЁННЫЙ прежний результат (`DUPLICATE`,
  без повторного применения).
- **Unique active pair.** `unique_active_pair(active, pair, purpose)` — не более одной активной пары на
  (неупорядоченная пара, purpose); дубликат второй волны → `DUPLICATE_PAIR` (первая волна не роняется).
- **Reservation TTL.** `reservation_expired(reservation, now_ts)` — детерминированно по явному `now_ts`.
- **Immutable trace + outbox.** `/api/agent/transition` на успехе аппендит `SESSION['_trace']` (from→to/version/
  action/id) и `SESSION['_outbox']` (append-only, тот же `_save_store`).

## §14.3 Политика одновременных принятий (`concurrent_accept_policy`)
Классификация по типу intent — **дефолт = `multiple_conversations`** (`exclusive:False`), поэтому существующий путь
negotiate (пишет КАЖДОГО согласившегося) остаётся byte-identical; эксклюзивность включается ТОЛЬКО для настоящего
**1:1 fixed-time** (`one_to_one_fixed_time`), которого не строит ни один прежний фикстур:
- `one_to_one_fixed_time` — один слот: первый accept выигрывает, поздний параллельный → **WITHDRAWN (`SLOT_TAKEN`)**,
  и **не** пишется как accepted (must-fix: CAS-loser не сосуществует с активным матчем). Enforced в
  `negotiate_candidates` через общий `SESSION['_match_taken']` (`claim_slot`), под `RLock`.
- `dating_manual_confirm` — `auto_commit:False` (запрет авто-плана держат §13-guards, не эксклюзивность).
- `group_reservation` / `event_capacity` — `enabled:False` (пилот-off §15/§16).
- иначе — `multiple_conversations` (несколько MUTUAL, без авто-плана).

## §14.4 Критические гонки (`resolve_race`) — без утечки
Ровно **8** каноничных гонок → детерминированный `{state, error_code, public_reason, leak:False}`. Кросс-агентная
поверхность (envelope) несёт ТОЛЬКО грубый `public_reason` («no longer available» / «slot unavailable» / «expired»
/ «time not workable»); гранулярная причина гейта (blocked / private profile / not open to dating) остаётся ТОЛЬКО
в owner-only `explain_match`. `policy_revoked`/`privacy_tightened` → `POLICY_CHANGED` (переиспользован verbatim из
§8.2, никогда не переименовывается); `slot_taken` → `SLOT_TAKEN`; `timezone_infeasible` → `TIME_INFEASIBLE`;
`duplicate_replay` → `DUPLICATE`.

## Проводка (аддитивно, byte-identical)
- `_STORE_LOCK` → **`threading.RLock`**: accept-транзакция держит ОДИН лок через revalidate + slot-claim +
  `_record_outcome` (который лок пере-захватывает) без deadlock — закрывает read-then-write окно на границе отправки.
- `negotiate_candidates`: `to_send` штампит `proposal.state = SENT`; на accept — `_stamp_accept` (SENT→ACCEPTED +
  `match_state=MUTUAL`), проигравший слот — `_stamp_txn(..., "slot_taken")` (→WITHDRAWN). `revalidate`/guards путь
  §8/§13 не тронут.
- `kc.build_proposal`: добавлен **статический** `version:1` (эмиттеры Reservation/Match/Edge уже несли `version:1`;
  инкремент живёт ТОЛЬКО за CAS/transition — тесты держат `==1`).
- `/api/agent/transition` — единственная валидированная поверхность WITHDRAW/EXPIRE/COUNTER: dedup → edge-check →
  CAS (при `expected_version`) → trace/outbox. `/api/agent/outcome` — идемпотентен при переданном `idempotency_key`.
- `_match_capsules` несут аддитивный `state` (active→MUTUAL, completed→COMPLETED); int-метрика `matches` не тронута.

## Статус (честно): **done_single_process 7 · partial 6 (blocked_infra) · pilot_disabled 1**
- **done (single-process):** 4 автомата §14.1, deny-safe валидатор, optimistic CAS, idempotency-dedup (clock-free,
  action-aware), §14.3 политика + enforced 1:1-эксклюзивность, 8 гонок §14.4 без утечки.
- **partial / blocked_infra (6):** idempotency-key НЕ на всех write-эндпоинтах (только transition + opt-in outcome);
  **unique-active-pair** — чистый примитив (покрыт тестом), как enforcing-gate в negotiate не встроен (не менять
  slate); transactional outbox — только append `_trace`/`_outbox`, **async-consumer нет**; retry-safe **async**
  consumers / dedup — примитив есть, распределённого потребителя нет; reservation TTL — чистая функция, **реальной
  capacity нет**; cross-entity атомарный commit через сервисы — нужна БД/очередь (пилот их не гоняет).
- **pilot_disabled (1):** Plan-автомат определён для конформанса, `enabled:False` (§15/§16).

## Адверсариал-ревью (после реализации)
6 finders (concurrency / byte-identity / info-leak / state-soundness / test-adequacy) → adversarial verify. 12 находок,
**3 подтверждены** (все low после верификации), исправлены:
- `/api/agent/outcome` идемпотентность была **не атомарной** — check (`_outcome_seen[key]`) и record (`_record_outcome`,
  unconditional append) шли в РАЗНЫХ `with _STORE_LOCK` блоках → под `ThreadingHTTPServer` два одновременных replay
  одного `idempotency_key` могли дважды записать `_outcomes`. **Фикс:** весь check+record+memoize под ОДНИМ RLock
  (как `agent_transition`); memoize только при `ok`.
- `reservation_expired()` был не покрыт тестом → добавлен `C14-RESERVATION-TTL`.
- **Hardening:** `agent_transition` мемоизирует ТОЛЬКО применённый переход — failed edge/CAS не мемоизируется, чтобы
  corrected-retry (новый `expected_version`) не застревал как `DUPLICATE`.
Info-leak инвариант ревью подтвердило **held** (гранулярная причина не доходит до proposal.state/txn/envelope).

Тесты: `services/matching/test_core_v2.py` — `C14-*` (17 проверок: машины/рёбра/CAS/dedup/unique-pair/reservation-TTL/
slot/policy/8-гонок-без-утечки/version:1/keyless + wiring: multiple-vs-exclusive negotiate, transition-endpoint,
capsule-state). Вся сюита **219/219** зелёная, детерминизм подтверждён двойным прогоном.
