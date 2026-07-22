# Kleal — Events / Online rooms / Venues как отдельные типы кандидатов (§16)

Ключевой принцип §16.0: **событие — НЕ «пользователь с большой capacity».** Event / OnlineRoom / Venue — свои
типы объектов, у каждого СВОЙ eligibility-гейт, СВОЙ **направленный** ранкинг `user→object` (одностороннний — объект
не оценивает пользователя в ответ; никакого `reciprocal_score`, mutual-policy, person-пайплайна) и СВОЙ data-only
transaction. Событие/площадка могут **закрыть intent даже без персонального совпадения** — и система честно называет
это **альтернативой**, а не «совпадением с людьми». Реализовано в
[`shared/kleal_candidates.py`](../shared/kleal_candidates.py) (`kct`, keyless, LLM-free, детерминированный,
no FS/clock/random) + аддитивная **gated** проводка в `matching/app.py`. Pilot-disabled: `intent_to_event`/
`intent_to_room`/`intent_to_venue` = False; алгоритм запускается ТОЛЬКО под точным per-kind override, результат всегда
`enabled:False`. User и Ad-hoc group уже покрыты (§4–§13 person-пайплайн и §15 `kleal_groups`).

Дисциплина: `kct` импортирует только stdlib `hashlib` + `kc` + `ks` + `kg`; **никогда** core_v2/llm_client/app.
`now_ts` инъектируется везде (в т.ч. в `kc.build_reservation(now=now_ts)`). Веса ранкинга — **module-local**
эвристики (в sha-pinned конфиге нет event/room/venue-блока), переданный `cfg` НЕ меняет score.

## §16.0 «Событие ≠ пользователь» — структурно
`is_personal_match:False` штампуется на объекте при build; на объектах НЕТ reciprocal/mutual-поля. Ранкинг —
`user_event_relevance` / `session_relevance` / `plan_suitability` — читает только object→сравнение, никогда обратный
сигнал. Тест `C16-EVENT-NOT-USER`: подмешивание фейкового `intents`/`receiving`/`wants` не меняет score; огромный
`seats_total` не ранжируется как high-capacity user.

## Три типа (Eligibility | Ranking | Transaction)
| Тип | Eligibility (hard-гейт, distinct path) | Ranking (directed user→object) | Transaction (data-only) |
|---|---|---|---|
| **Event** | category/schedule/capacity/access: `CATEGORY_MISMATCH`, `SCHEDULE_PAST`, `SCHEDULE_NO_OVERLAP`, `CAPACITY_FULL`, `ACCESS_AGE/VERIFIED/LANGUAGE/PAID`, `GEO_OUT_OF_RADIUS` | `user_event_relevance` = 0.35·topic + 0.25·schedule + 0.15·distance + 0.10·price + 0.10·access + 0.05·capacity | registration (`kc.build_reservation`) / external_handoff (`handoff_token`) / waitlist |
| **Online room** | platform/topic/live-capacity/moderation: `TOPIC_MISMATCH`, `PLATFORM_UNSUPPORTED`, `MODE_OFFLINE_NO_CONSENT`, `LIVE_CAPACITY_FULL`, `MODERATION_REQUIRED`, `LANGUAGE_UNCOVERED` | `session_relevance` = 0.35·topic + 0.25·liveness + 0.20·moderation + 0.10·language + 0.10·platform | join_token (+reservation) / waitlist |
| **Venue** | availability/price/noise/distance/accessibility: `UNAVAILABLE`, `PRICE_OVER_BUDGET`, `GEO_OUT_OF_RADIUS`, `NOISE_UNACCEPTABLE`, `ACCESSIBILITY_REQUIRED` | `plan_suitability` = 0.25·distance + 0.20·availability + 0.20·noise + 0.15·price + 0.10·amenity + 0.10·accessibility | selection (`kc.build_plan`, enabled:False) / booking_handoff |

**Feasibility доминирует:** любой eligibility-код → `score=None` (не число); `rank_candidates` дропает
score-None ДО сортировки — ineligible не может ранжироваться/побеждать (как `kg.group_utility`). **Deny-safe:**
topic/category-гейт срабатывает ТОЛЬКО когда ОБЕ стороны объявили topics И directed overlap==0 (никакого
over-matching). `MODE_OFFLINE_NO_CONSENT`: offline-intent не подменяется на online молча — комната честная
альтернатива, разрешённая только при `allowOnlineFallback` (§5.1). Прове-eligible гейты (verified/accessibility) при
STATED-требовании и неизвестном атрибуте → violation, не false-pass.

## Honest-alternative
Каждый built-объект / ranked-карточка / transaction несёт `is_personal_match:False`, `is_alternative:True`, `kind`,
`tier:'T4'`, `closes_intent_as:'alternative'`, `ladder_step:6`, `retrieval_source:4` — та же T4-лексика, что у
существующего §12 `_online_fallback`, но ОТДЕЛЬНЫЙ код-путь. Событие закрывает intent как альтернативу, никогда как
«совпадение с людьми».

## Capacity (App C #8) — reuses §14
`claim_seat` → `kg.claim_group_seat` → `ks.claim_slot` на составном ключе `resource#seatN`; отклоняет
`seat_ordinal>=capacity` ДО claim; проигравший на последнем месте → `ks.resolve_race('slot_taken')` (WITHDRAWN /
грубый public_reason / `leak:False`) + waitlist; `filled` ≤ capacity by construction. **Single-process**
(кросс-под атомарность — blocked_infra). Transactions — только дескрипторы (registration/join-token/booking), без
реальных внешних вызовов (как §15 invitations «сконструированы, не отправлены»).

## Gating (dormant-at-pilot / falsifiable-under-EXACT-override)
1. **Global** не тронут: `PILOT_DECISION_TYPES['intent_to_event'/'room'/'venue']=False`; модуль НИКОГДА их не флипает.
2. **Module** — чистая библиотека без import-side-effects.
3. **Endpoint** — три per-kind `POST /api/agent/event|room|venue`, тело `run_candidates`, dormant если не
   `is_override_enabled(kind, override)` (нужен ТОЧНЫЙ `{'enable_intent_to_<kind>':True}` bool). Read-only ранкинг
   (без reservation-side-effect). Сырые slate-объекты нормализуются через `build_object` (lcb-аналог §15).
4. **Additive enums:** `#39` добавил `venue` в `kc.PROPOSAL_TYPES`, `app._PTYPE_OF_DECISION`, `PILOT_DECISION_TYPES
   {intent_to_venue:False}` — всё pilot-off; existing person-enums сохранены (`C16-VENUE-ENUM-ADDITIVE`).

**Byte-identical person-to-person slate:** `core_v2.search`/`match_candidates`/`negotiate` не ссылаются на `kct`
(`C16-BYTE-IDENTICAL-PERSON-SLATE`); §12 fallback не тронут; sha-pinned `core_v2.py`/yaml не редактированы.

## Статус (честно): **pilot_disabled 6 · done_prior 2 · partial 2 · blocked_infra 2 · done 1**
- **pilot_disabled (реализовано как scaffolding, выключено в пилоте):** §16.0 distinct types; Event/Room/Venue
  (build + eligibility + directed ranking + transaction); honest-alt typing; per-kind gated endpoints.
- **done_prior:** Ad-hoc group (§15 `kleal_groups`); T4 honest-alternative лексика на fallback-слое (§12).
- **partial:** конкретные domain-констрейнт-паки (§18-детали); candidate↔candidate pair_rel матрица (сейчас
  directed user→object; n×n — вход).
- **blocked_infra (2):** кросс-под capacity-атомарность; живой event/room/venue retrieval-feed (§7 источник 4
  `events_and_rooms` остаётся `enabled:False` — объекты подаются вызывающим).
- **done:** byte-identical person-slate + untouched §12 fallback + sha-pinned engine/config unedited.

**Дизайн-ревью** (6 агентов, go_with_fixes / sound_with_fixes): 10 must-fix + 3 blocking применены (единый epoch-юнит
через `kc._parse_iso`; `now_ts` обязателен без fallback; feasibility→`score=None`, дроп до сортировки; веса
module-local; honest-alt на источнике; reuse kg-хелперов; venue-enum additive; событие≠user структурно).

**Адверсариал-ревью реализации** (5 finders → verify, 17 находок, 4 подтверждены; исправлены): (1+2 medium — тот же
баг двумя dimensions) `_sort_key` не был строгим тотальным порядком — при коллизии `kc._det_id` id (два event с
одинаковым title+start, разными topics) + равном score stable-sort зависел от перестановки → добавлен
**content-hash tiebreak** (`_content_key`); (3 low) `room_transaction` брал `max_live` вместо `live_left =
max_live − current_participants` (полная комната ложно давала join_token) → исправлено; заодно устаревший
комментарий deploy-скрипта и мис-названный тест C16-CAPACITY-ROOM. Плюс hardening: `_list` сортирует set-входы
(no PYTHONHASHSEED-leak), `_capacity_term` bool-guard на total, `int(now_ts or 0)` в transactions, тесты
EVENT-NOT-USER/DIRECTED-ONEWAY усилены (score сырых dict'ов с reciprocal-полями), добавлен `C16-DETERMINISM-COLLISION`.

Тесты: `services/matching/test_core_v2.py` — `C16-*` (**24 проверки**). Вся сюита **264/264** зелёная, детерминизм —
двойной прогон. Live HTTP smoke `/api/agent/event|room|venue`: dormant по умолчанию, falsifiable под точным override
(event score 0.92 = точная взвешенная сумма), `enabled:False` всегда; person-slate healthy.
