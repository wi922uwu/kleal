# Kleal — нормативный словарь (§2) и точки принуждения

Спека §2 задаёт нормативные слова: **ДОЛЖЕН** (MUST) / **НЕ ДОЛЖЕН** (MUST NOT) / **СЛЕДУЕТ**
(SHOULD). Этот файл переводит нормативные утверждения §0–§3 в конкретные места кода, где они
принуждаются. Здесь описано **только то, что реально реализовано** — каждая строка ссылается на
существующую функцию.

Легенда: `matching/app.py` — оркестрация (гейты, политика, снапшот, исходы); `matching/core_v2.py` —
детерминированный движок скоринга (не изменяется, sha-пиннится); `config/*.yaml` — единственный источник
весов/порогов.

## MUST — обязательные инварианты

| Нормативное утверждение (§) | Принуждение (файл:функция) |
|---|---|
| Eligibility/safety — **жёсткие гейты ДО скоринга**; ни один слой не компенсирует другой (§0, §1, §3) | `app.py:_policy_decision` → `_hard_gates` (вызывается до `core_v2.search`) |
| `policy_decision` — **три состояния** ALLOW / REVIEW / BLOCK, не булево (§0 таблица, §3 шаг2) | `app.py:_policy_decision`, `_apply_policy` |
| Оплата подписки **НЕ влияет** на relevance/eligibility/safety/порядок (§0 реш.10, §11.3) | `app.py:_payment_invariant`, `PAYMENT_INVARIANT` (читает `currency_or_paid_priority`; в скоринг не подаётся ни один платёжный вход) |
| Relevance — эвристика 0..1, **НЕ вероятность и не процент** (§0 реш.4) | `core_v2.py:directional_score`; пользователю показывается band, не процент — `core_v2.py:assign_band` (§9.7) |
| `unknown` ≠ `mismatch` ≠ `not_applicable` — **разные состояния**; пустой профиль не выигрывает (§0 реш.3) | `core_v2.py:build_features` (4 состояния), `directional_score` (NA вне знаменателя, lcb штрафует низкое покрытие) |
| Semantic tier = **происхождение** свидетельства, не качество/не score (§0 реш.2) | `core_v2.py:assign_tier` |
| **Молчание ≠ отказ**: `expired_no_response` нейтрально и не идёт в понижающий рейтинг фидбек (§1 инвариант) | `app.py:_record_outcome`, `_success_metrics` (`silence_is_negative=False`) |
| Успех = **состоявшееся взаимодействие** + двусторонний accept, а не клик/показ (§1, §2) | `app.py:_success_metrics` (`completed_interactions`), `_record_outcome` (match при `accepted`) |
| Политика **ревалидируется на границе отправки** (§8.2) | `app.py:_negotiate_precheck` (повторно `_hard_gates` + `_outreach_ok` + readiness + кап волн) |
| В пилоте обслуживаются **только разрешённые типы решений**; остальные объявлены и выключены (§1.2) | `app.py:PILOT_DECISION_TYPES`, `_pilot_enabled`, `_decision_type` |
| Конфиг **sha-пиннится**; несовпадение → остановка (не смешивать версии) (§21.4) | `core_v2.py:load_config` (`PINNED_SHA`, `ConfigError`) |
| Каждый результат несёт **снапшот версий** intent/config/policy/data (§4 intro) | `app.py:_request_snapshot`, `_intent_identity` |

## MUST NOT — запреты

| Запрет (§) | Как обеспечен |
|---|---|
| **Нет единой сводной FinalUtility** (relevance+safety+response+fairness+оплата+fatigue одной формулой) (§3) | `core_v2.py:search` возвращает 6 раздельных выходов; safety — гейт, readiness/allocation — порядок/гейт, а не слагаемые; сортировка кортежем band→readiness→reciprocal→lcb→cov, не суммой |
| Payment **не даёт ranking boost** и не меняет safety-приоритет | `app.py:_payment_invariant` → `ok=False`, если конфиг когда-либо включит буст (проверяется, а не предполагается) |
| REVIEW-кандидат **не получает авто-outreach** | `app.py:_apply_policy` (принудительно `can_outreach=False`), `explain_match` (та же ветка) |
| Предпочтение (preference) **не становится hard-gate без подтверждения** | hard-гейты в `_hard_gates` — только eligibility/safety/явные требования интента; мягкие сигналы идут в скоринг, не в гейт |

## SHOULD — рекомендуемое поведение

| Рекомендация (§) | Реализация |
|---|---|
| Поиск **не должен упираться в пустоту**, пока кто-то eligible (§12) | `app.py:_expand_fallback` (шире/смежные → «другая категория», всё помечено `fallback`) |
| Пользователю **следует** показывать уровень + 2–3 причины + 1 gap + пометку расширения (§0 реш.5) | `core_v2.py:_presentation`, `assign_band`; карточка несёт `reasons`/`gap`/`fallback` |
| Каждому кандидату **следует** присвоить типизированный `allocation_action` (§0 таблица) | `app.py:_allocation_action` (propose / discovery_only / discovery_expanded / review_required) |

## Что объявлено, но выключено в пилоте (не MUST для пилота)

Типы решений §1.1 вне пилота — это отдельные слои (§14–§16), а не забытые пункты. Они присутствуют в
`PILOT_DECISION_TYPES` со значением `false`, и запрос такого типа получает честный «не в этом пилоте», а не
пустой ответ:

- `group_formation` — формирование групп (§15)
- `intent_to_event` — привязка к событию (§16)
- `intent_to_room` — привязка к комнате (§16)
- `relationship_continuation` — продолжение отношений/история пары (§14)

Живые в пилоте: `person_to_person`, `intent_to_intent` (реципрокность; полное слияние условий двух активных
интентов — частично).
