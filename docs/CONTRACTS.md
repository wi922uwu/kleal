# Kleal — канонические контракты данных (§4)

Единый источник истины для §4 — модуль [`shared/kleal_contracts.py`](../shared/kleal_contracts.py)
(`CONTRACTS_VERSION = "contracts-4.0.0"`, stdlib-only, без ключей). Здесь описано **только то, что
реально реализовано**; каждая строка ссылается на существующую функцию.

## Несущий инвариант (защищает sha-пиннутый core_v2.py)
`core_v2.py` читает поля intent/profile/candidate/receiving **по имени** и не редактируется. Поэтому:

- **Каждый билдер аддитивен** — возвращает `dict(existing, **new)`; новые данные кладутся только под
  **новыми** ключами, ни одно поле, которое читает движок, не удаляется и не переименовывается.
- **Каждый валидатор read-only** — возвращает список проблем, ничего не переписывает и не вычищает.
- Ответ фронтенду остаётся **backward-compatible superset**: карточка обрастает новыми под-ключами
  (`snapshot` / `profile_view` / `relationship` / `proposal`), старые поля не трогаются.

## 12 сущностей (§4) → билдер → где подключено

| Сущность | Билдер (`kc.*`) | Где стемпится |
|---|---|---|
| UserProfile | `build_user_profile` | `admin/_norm_user` (аддитивно: identity/privacy/_contract) |
| ProfileView | `build_profile_view` | `matching/_stamp_contracts` → `card.profile_view` (purpose-bound, §8.3) |
| ReceivingPolicy | `build_receiving_policy` | `admin/_receiving_from_form` (делегирует; §4.4 superset) |
| Intent (+11 блоков §4.3) | `compile_intent` | `matching`: `/match`, `agent_plan`, `match_candidates` |
| Evidence | `build_evidence` | `matching/explain_match` → `matched[].evidence` (§4.1) |
| CandidateSnapshot | `build_candidate_snapshot` | `matching/_stamp_contracts` → `card.snapshot` |
| Proposal | `build_proposal` | `matching/negotiate_candidates` → `card.proposal` |
| Reservation | `build_reservation` | контракт-стаб (реальный capacity — пост-пилот §15) |
| Match | `build_match` | `matching/_match_capsules` → `/api/agent/outcomes.match_capsules` |
| Group | `build_group` | контракт определён, `enabled=False` (пилот-выкл, §16) |
| Plan | `build_plan` | контракт определён, `enabled=False` (пост-пилот §14/§16) |
| RelationshipEdge | `build_relationship_edge` | `matching/_relationship_edge` (advisory; хард-гейт остаётся авторитетным) |

## §4.2 Иерархия источников (7 уровней)
`SOURCE_HIERARCHY` (1 = высшая власть … 7 = низшая) + `SOURCE_PRIORITY` + `resolve_source(a,b)`.
Evidence НЕ хардкодит уровень 1: провенанс каждой feature-group берётся из `FEATURE_GROUP_SOURCE` —
`semantic_activity`/`domain_constraints` → `explicit_stable_profile` (L4), `time`/`location` →
`current_context_permissioned` (L3), `mode_format`/`directed_preferences` → `current_intent_explicit`
(L1), `social_context` → `agent_inference` (L7). Так §4.2-правило «высший источник перекрывает старые
данные» не искажает eligibility.

## §8.3 Purpose binding (ProfileView)
`DOMAIN_TO_CONTEXT` — **тотальная** карта engine-домен → один из 6 контекстов
(friendship/dating/networking/language_exchange/games/sport); незамапленный домен проецируется как
**minimal** (deny-safe, только `name`). `PURPOSE_FIELDS[context]` — allow-list = **дополнение deny-колонки
§8.3**. Гарантии (проверяются тестами `C4-PV*`):
- `datingOk` не показывается ни в одном контексте, кроме `dating`;
- профессиональный признак `entities` не показывается в `dating`.
Проекция обёрнута в try/except в `_stamp_contracts`: сбой деградирует до отсутствующего под-ключа, а не
до пустого slate.

## §4.3 Intent schema
`compile_intent(parsed, identity, ctx, now)` сохраняет 16 плоских ключей (и **дозаполняет** отсутствующие
дефолтами, совпадающими с `.get()`-фолбэками кода — поэтому scoring не меняется) и стемпит 11 блоков:
identity / goal / time_block / location_block / mode_format / target / social / domain_details / fallback
/ disclosure / lifecycle. **Lifecycle/TTL**: `TTL_DEFAULTS[domain]`; `is_expired()` — отсутствующий
`expires_at` = НЕ истёк (buddy-интенты без lifecycle не стираются молча), истёкший intent не ранжируется
(`match_candidates` → `[]`). Компиляция **никогда не оживляет** уже истёкший lifecycle.

## §4.4 Receiving policy
`build_receiving_policy` — superset над старым admin-маппингом, с сохранением **точной семантики None**
(патч без `rcvStatus` → сквозная передача сохранённой политики; очищенное сохранение → None; политика
не фабрикуется для пользователя, ничего не задавшего). Новые поля (`location_scope`,
`allowed_proposal_types`, `disclosure_stage`, `proposal_budget.per_7d`, `paused_until`) —
omitted-when-unset и **принуждаются на границе отправки** в `matching/_receiving_send_gate`
(absent-field-permissive): тип предложения, локация, 7-дневный бюджет (по существующему логу `_proposals`).

## Статус подпунктов §4 (честно)
**✅ 17 · 🟡 9 · ⬜ 0** (было ✅1 · 🟡17 · ⬜10). Group/Plan — **declared_disabled** (контракт определён,
`enabled=False`, пилот-выкл).

Частичные (🟡) — потому что апстрим (онбординг) ещё не собирает данные, а фабриковать их нельзя:
CandidateSnapshot (богатое evidence только в explain, где есть per-feature rows), Reservation (нет
capacity-системы в person-to-person), §4.3 Time (windows/duration/recurrence — только urgency+timezone),
§4.3 Location (safe_zones/travel_time не собираются), §4.3 Target (level не собирается), §4.3 Social
(pressure_level/communication_style — плейсхолдеры), §4.3 Domain details (platform/rank/ticket/equipment
не собираются), §4.3 Disclosure (stage_map минимальный, поэтому disclosure-clamp консервативно no-op).

Тесты: `services/matching/test_core_v2.py` — секция `C4-*` (29 проверок: enum-drift, intent-компиляция,
lifecycle/expiry, receiving None-семантика, purpose-binding, evidence-dedup, edge-состояния, proposal-
идемпотентность, интеграция match/explain/negotiate, COMPAT-1 `matches` int vs `match_capsules` list).
