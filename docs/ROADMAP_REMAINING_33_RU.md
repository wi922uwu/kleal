# Roadmap: оставшиеся 33 «частично» подпункта

_Оценка «как закрыть» для 33 подпунктов, которые не закрылись чистым аддитивным кодом. Сгруппировано по
**рычагу разблокировки**, а не по типу блокера. Оценки усилий — грубые dev-дни, честно. «Кто нужен» = что
требуется помимо моего кода. Ничего не деплоится/коммитится без подтверждения._

## Сводка по рычагам

| Рычаг | Пунктов | Мой код | Что ещё нужно | Оценка |
|---|--:|---|---|---|
| **A · stdlib-персистентность** (sqlite3 + threading-worker + zoneinfo) | ~16 | да (фундамент + надстройки) | согласие партнёра (общий под) | **12–16 dev-дней** |
| **B · доки + активация dormant** | ~6 | частично (код) + документы | бизнес-решения, запуск пилота | **3–5 dev-дней** + доки |
| **C · правка sha-pinned движка** | 2 | подготовить патч | Dev B пере-пинит v3 | **~1 dev-день** (подготовка) |
| **D · внешние ресурсы** (transport/индексы/данные/юр.) | ~7 | интерфейс/черновик | провайдер + деньги + данные + люди | зависит от внешнего |
| **Итого** | 33 | ~24 закрываемы | 7 уперты во внешнее | |

**Одно решение раскрывает больше всего:** рычаг A — это **один фундамент** (durable sqlite-стор + фоновый
поток), на который ~16 пунктов ложатся как мелкие надстройки. Остаётся stdlib, не трогает sha-pinned движок,
person-slate byte-identical (персистентность аддитивна). Ограничение: **single-node** (истинную мульти-под
атомарность sqlite не даёт — но пилот и есть один под).

---

## Рычаг A — stdlib-персистентность (`sqlite3` + `threading`-worker + `zoneinfo`)

**Фундамент (делается один раз):** `shared/kleal_store.py` — durable sqlite-стор (таблицы: proposals, plans,
searches, intents, reservations, outbox, events, traces, reports, consents, retention) + фоновый `threading`-worker
(consumer outbox, retention/expiry-job, async-исполнитель search-run). **L · 4–6 dev-дней.** Нужно: **согласие
партнёра** (файл БД + фоновый поток на общем поде). Внешнего — нет.

Надстройки на фундамент (каждая ~S · 0.5–1 день):

| ID | Что закрывает | Оценка | Кто нужен |
|---|---|--:|---|
| §14.2 | outbox+trace → sqlite + async-consumer в воркере (at-least-once + дедуп) | S | — |
| B.2 / 21.2 EVENT match_state_changed | worker эмитит match_state_changed из outbox (SSE/poll) | S | — |
| 21.4 notification-failure | retry/relay в воркере (пока sender — заглушка) | S | transport (D) для реальной доставки |
| 21.1 match-orchestrator | персистентный стор proposal/plan/search-run (сейчас в SESSION) | S | — |
| 21.2 intents-confirm | версионируемый intent-ресурс + `/intents/{id}/confirm` | S | — |
| 21.2 searches-idempotency | `search_id`-ресурс + idempotency-дедуп на create | S | — |
| 21.4 async-search / `<2s ack` | worker гоняет поиск; эндпоинт сразу отдаёт `search_id`+accepted | S–M | — |
| 21.4 SLA capacity | кросс-request reservation-стор (UNIQUE) для event/room/group | S | — |
| 21.1 profile-consent | profile_versions + версии согласий + erasure-путь (удаление inferred) | S–M | — |
| 17.1.audit | retention-job (delete-on-expiry) + access-layer (токен/роль) + dating-specific policy_version | M | — |
| 17.1.safety | report-intake + moderation-queue (state machine) + escalation | M | человек-модератор (D) для разбора |
| 19.1 outcome-taxonomy | стадии exposure→consideration→coordination→completion→quality→safety + сигналы (comfort/usefulness/would_repeat/no_show) | S–M | — |
| §20.0 metrics | агрегации по sqlite + базовый `/status`-дашборд (HTML) | M | — |
| 21.1 audit-observability | durable traces + `/replay`-эндпоинт | S | — |
| §8.4 DST | DST-корректная time-feasibility через `zoneinfo` (вместо фикс. offset) | S | routing/H3 — в D |

**Остаётся за рамкой A:** мульти-под атомарность (нужен Postgres/Redis; пилот single-pod), реальный внешний
transport, ANN/geo-индексы (см. D).

---

## Рычаг B — документы + активация уже-построенных dormant-механизмов

| ID | Что закрывает | Оценка | Кто нужен |
|---|---|--:|---|
| 22.3 ops-model | КОД: city-partition фильтр, active-intent cap, manual-review-queue (sqlite), daily-dashboard | M (пересекается с A) | бизнес: кто владелец инцидентов / weekly review |
| 20.2 staged-validation | план валидации + fixture-харнесс шага 1 (labeled cases) | M | запуск shadow/dogfood/пилота = время |
| 22.1 pilot-scope | scope-документ (какие домены/районы) | S | бизнес-решение |
| 19.3 feedback-bias | включить exploration_quota + логировать propensity (механизмы §11 лежат dormant) | S | калибровка ставки = данные (D) |
| §7.1 source-enablement | флипнуть источники 3/4 (groups/events) live | S | решение о запуске (group/event сейчас pilot-off by design) |

_Механизмы §11 (exposure caps / exploration / popularity guard) уже реализованы dormant — активация = флаг
+ калибровка порогов (порог = данные)._

---

## Рычаг C — правка sha-pinned движка (нужен владелец, Dev B)

| ID | Что закрывает | Оценка (подготовки) | Кто нужен |
|---|---|--:|---|
| §9.2 | смешивание known-значения с prior по per-observation confidence (сейчас confidence_k≡1) | S (~0.5 дня) | Dev B пере-пинит v3 core_v2/config + новый PINNED_SHA |
| §18.4 | учитывать complementarity-матрицу (learner↔native) в скоринге language-exchange | S (~0.5 дня) | Dev B пере-пинит v3 |

_Я готовлю точный diff-предложение + новый sha; правило проекта — движок редактирует владелец. Обходить пин
через «второй скорер» в оркестрации нельзя (§23.2.11 запрещает второй источник + сломает byte-identity)._

---

## Рычаг D — реально нужны внешние ресурсы (код не заменит)

| Что | Пункты | Нужно | Оценка |
|---|---|---|---|
| Реальный transport (push/email/SMS) | часть 21.4 notification | провайдер (FCM/SES/Twilio) + креды + интеграция | M после выбора провайдера + **деньги** |
| ANN/geo-индексы (pgvector/PostGIS/H3) | §7.2, 21.1-candidate-retrieval | Postgres+расширения; **на объёме пилота линейный проход уже покрывает функцию** — это оптимизация под скейл | отложить до объёма; **инфра+деньги** |
| Travel-time routing | часть §8.4 | сервис маршрутизации (OSRM/Google) | **внешний сервис** |
| Калиброванные ML-модели | §19.0, 21.1-feedback-learning, ядро 19.3/21.1-allocation | **реальные данные живого пилота** для обучения (интерфейсы-стабы + shadow-харнесс строятся сейчас, сама модель — post-pilot) | **данные/время** |
| Юр. sign-off / DPIA / модерация | 17.1.audit-governance, 20.2-launch, §17.3-adjacent | **DPO/юрист + модераторы** (черновик DPIA + runbook я напишу; sign-off — человек) | **люди** |

---

## Рекомендуемая последовательность

1. **Сначала C (дёшево, 1 день)** — подготовить diff-предложение партнёру по §9.2/§18.4; параллельно ждёт его «да».
2. **Затем A-фундамент** (после согласия партнёра по общему поду) — один durable-стор + worker раскрывает ~16.
3. **Надстройки A + B-код** идут потоком поверх фундамента (reservation/audit/safety/metrics + ops-механизмы).
4. **B-документы** (DPIA-черновик, pilot-scope, ops-runbook, validation-план) — можно писать в любой момент, независимо.
5. **D — отложить** до момента, когда есть провайдер transport / бюджет на инфру / данные живого пилота / юрист.

## Что реально «не закрыть» без внешнего (итоговый честный остаток: ~7)
- живой push/email-transport (провайдер+деньги);
- ANN/geo-индексы и travel-routing под скейл (Postgres/сервис — функция покрыта линейно на пилоте);
- **калиброванная** ML-модель (нужны данные пилота);
- юридический/DPIA sign-off и штат модерации (люди).

Всё остальное (**~24 из 33**) закрываемо: ~16 через один sqlite+worker слой, ~6 через код+документы, 2 через
короткое согласование с владельцем движка.
