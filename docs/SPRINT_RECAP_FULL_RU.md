# Kleal Matching Core v2 — полный рекап спринта

_Супер-подробный разбор всех доработок по спеке, проверенный по реальному коду (11 агентов сверили модули + тесты + доки). Для каждого подпункта: что требует спека -> что построено (file:function) -> как работает -> ключевые решения -> тесты -> статус._

**Сквозное:** 10 новых keyless / LLM-free модулей `shared/kleal_*` + расширенный `services/matching/app.py`; sha-pinned `core_v2.py` + config НЕ редактировались; person-slate byte-identical; детерминизм (двойной прогон); **305 acceptance-тестов**; всё локально, ничего не задеплоено / не закоммичено.

## Оглавление
1. §4 Канонические контракты данных
2. §5 Intent Compiler + §6 Таксономия
3. §7 Candidate retrieval + §8 Eligibility/privacy/safety/purpose binding
4. §9 Математическая модель relevance / evidence / uncertainty
5. §10 Reciprocity/readiness + §11 Allocation/fairness
6. §12 Controlled expansion + §13 Agent protocol
7. §14 Transaction state machines и защита от гонок
8. §15 Group Formation Core
9. §16 Events, rooms и venues — отдельные типы кандидатов
10. §17 Dating — защитные механизмы
11. Закрытие 47 «частично» подпунктов (CP1-CP10) + §21-23 (API/observability/registry) + доработки §0-§3/§18-§20

---

## §4 — Канонические контракты данных (Kleal Matching Core v2)

Единый источник истины — модуль `shared/kleal_contracts.py` (`CONTRACTS_VERSION = "contracts-4.0.0"`, stdlib-only, **zero secret/key references**, keyless и LLM-free — импортируется любым сервисом через `shared` на `sys.path`). Документация — `docs/CONTRACTS.md`. Тесты — секции `C4-*` (~29 проверок), `CP2-*`, `CP9-*` в `services/matching/test_core_v2.py`. Ничего не задеплоено — всё локально; sha-пиннутый `core_v2.py` + config **не редактировались** (билдеры аддитивны, чтобы движок продолжал читать поля по имени).

### Несущий инвариант (защита sha-пиннутого скорера)
- **что требует спека**: контракты не должны ломать движок скоринга.
- **что построено**: docstring-инвариант модуля + все билдеры/валидаторы в `shared/kleal_contracts.py`.
- **как работает**: каждый билдер **аддитивен** — возвращает `dict(existing, **new)`, кладёт новые данные только под новыми ключами, никогда не удаляет/переименовывает поле, которое `core_v2.py` читает по имени. Каждый валидатор **read-only** — возвращает список проблем, ничего не переписывает. Ответ фронтенду остаётся backward-compatible superset (карточка обрастает `snapshot`/`profile_view`/`relationship`/`proposal`).
- **ключевые решения**: byte-identity скорера сохраняется, потому что дефолты плоских ключей интента (`_FLAT_DEFAULTS`) выбраны так, чтобы совпадать с `.get()`-фолбэками кода — дозаполнение контракта не меняет scoring/gates.
- **тесты**: `C4-INTENT1`, `C4-RECV1`.
- **статус**: done.

#### §4.2 Иерархия источников (7 уровней) + провенанс feature-групп
- **что требует спека**: 7-уровневая иерархия авторитетности источников данных; высший источник перекрывает старые данные того же scope.
- **что построено**: `SOURCE_HIERARCHY` (кортеж из 7), `SOURCE_PRIORITY`, `resolve_source(a,b)` — `shared/kleal_contracts.py:33`; плюс `FEATURE_GROUP_SOURCE` (`kleal_contracts.py:40`).
- **как работает**: `SOURCE_HIERARCHY` = `current_intent_explicit(1)` … `agent_inference(7)`. `resolve_source` возвращает источник с меньшим priority-числом (высшая власть). `FEATURE_GROUP_SOURCE` привязывает провенанс каждой scored feature-group: `semantic_activity`/`domain_constraints` → `explicit_stable_profile` (L4), `time_feasibility`/`location_feasibility` → `current_context_permissioned` (L3), `mode_format`/`directed_preferences` → `current_intent_explicit` (L1), `social_context` → `agent_inference` (L7).
- **ключевые решения**: Evidence НЕ хардкодит L1 (`SPEC-1`) — иначе soft-инференция (vibe) стала бы скрытым hard-gate с ложной авторитетностью; провенанс config-derived из карты групп.
- **тесты**: `C4-EV2` (7 уровней; невалидный источник → `agent_inference`), `C4-INT4` (explain-evidence НЕ единообразно L1), `C4-INT5` (источник всегда из 7-уровневой иерархии).
- **статус**: done.

#### §4 Сущность 1 — UserProfile
- **что требует спека**: канонический профиль пользователя (identity + privacy).
- **что построено**: `build_user_profile` (`kleal_contracts.py:142`) + `validate_user_profile:164`.
- **как работает**: аддитивный superset над выводом `admin/_norm_user`. Сохраняет каждый плоский matcher-ключ и добавляет под-блоки `identity` (id/name/age/`age_verified_18`/languages.comfortable/city/role) и `privacy` (visibility=`match_only`/verified/`dating_opt_in`) через `setdefault`, плюс `_contract`. Никогда не роняет ключ, который читает core_v2.
- **ключевые решения**: `setdefault` — не перетирает уже стемпленные блоки; `age_verified_18` вычисляется детерминированно из age.
- **тесты**: покрыт косвенно интеграцией `C4-INT*` (профили из store).
- **статус**: done.

#### §4 Сущность 2 — ProfileView / §8.3 Purpose binding
- **что требует спека**: purpose-bound минимальная проекция профиля; поле, разрешённое в одном контексте, не доступно автоматически в другом.
- **что построено**: `build_profile_view` (`kleal_contracts.py:171`), карты `CONTEXTS`, `DOMAIN_TO_CONTEXT`, `PURPOSE_FIELDS`.
- **как работает**: `DOMAIN_TO_CONTEXT` — **тотальная** карта engine-домен → один из 6 контекстов (friendship/dating/networking/language_exchange/games/sport). Незамапленный домен → minimal deny-safe view (только `name`, `SPEC-2`). `PURPOSE_FIELDS[context]` = allow-list = дополнение deny-колонки §8.3. Проецируются только не-None поля из allow-list. Возвращает `view_id`/`context`/`disclosure_stage`/`allowed_fields`/`fields`.
- **ключевые решения**: deny-safe тотальность — новый домен без маппинга не может молча слить dating/sensitive поля; ключевые deny-инварианты: friendship/networking/language_exchange/games/sport → нет `datingOk`; dating → нет профессионального `entities`.
- **тесты**: `C4-PV1` (friendship без datingOk), `C4-PV2` (dating без entities), `C4-PV3` (незамапленный → minimal), `C4-PV4` (все не-dating контексты без datingOk), `C4-INT2` (интеграция: purpose-bound friendship без утечки).
- **статус**: done.

#### §4.3 Intent (+11 блоков) + Lifecycle/TTL
- **что требует спека**: intent-схема с 11 блоками (identity/goal/time/location/mode/target/social/domain_details/fallback/disclosure/lifecycle) + TTL/expiry; истёкший intent не ранжируется.
- **что построено**: `compile_intent` (`kleal_contracts.py:329`), `is_expired:396`, `validate_intent:408`, `TTL_DEFAULTS`, `_FLAT_DEFAULTS`, `_urgency`, `_allowed_dimensions`.
- **как работает**: `compile_intent(parsed, identity, ctx, now)` сохраняет 16 плоских ключей (дозаполняет отсутствующие `_FLAT_DEFAULTS`, совпадающими с `.get()`-фолбэками кода — scoring не меняется) и стемпит 11 блоков. TTL берётся из `TTL_DEFAULTS[domain]` (`_default` = 24ч при отсутствии домена, COMPAT-4 без KeyError). `is_expired`: отсутствующий/пустой `expires_at` → НЕ истёк; распарсенный прошлый timestamp → истёк. Компиляция **никогда не оживляет** уже истёкший lifecycle (сохраняет его verbatim).
- **ключевые решения**: детерминизм — `now` инжектится; buddy-интенты без lifecycle не стираются молча (COMPAT-4); дозаполнение контракта byte-identity к скорингу.
- **тесты**: `C4-INTENT1` (16 плоских ключей), `C4-INTENT2` (11 блоков), `C4-INTENT3` (валидатор чист), `C4-INTENT4` (не оживляет expired), `C4-INTENT5` (is_expired: missing/fresh/past), `C4-INT3` (истёкший intent → honest empty slate).
- **статус**: done (частичные под-блоки — см. ниже: time windows/duration/recurrence, location safe_zones/travel_time, target level, social pressure/style, domain_details platform/rank/ticket — плейсхолдеры, т.к. апстрим-онбординг ещё не собирает эти данные, а фабриковать нельзя → partial).

#### §4.4 ReceivingPolicy
- **что требует спека**: политика приёма предложений (домены/тихие часы/бюджеты/типы/локация/disclosure).
- **что построено**: `build_receiving_policy` (`kleal_contracts.py:250`) + `validate_receiving_policy:297`.
- **как работает**: superset над старым admin-маппингом, читает `rcv*`-поля формы и эмитит каноническую политику ИЛИ None. **Точная семантика None сохранена** (COMPAT-3): патч без `rcvStatus` → сквозная передача сохранённой `receiving`; очищенное full-save → None; политика никогда не фабрикуется для пользователя, ничего не задавшего (иначе readiness ложно флипнулась бы в open_now). Новые §4.4-поля (`location_scope`, `allowed_proposal_types`, `disclosure_stage`, `proposal_budget.per_7d`, `paused_until`) — **omitted-when-unset**, чтобы send-boundary gates оставались permissive.
- **ключевые решения**: absent-field-permissive; omitted-not-empty-listed; сохранение критической None-семантики оригинального `_receiving_from_form`.
- **тесты**: `C4-RECV1` (патч → passthrough), `C4-RECV2` (cleared → None), `C4-RECV3` (новые поля + база целы), `C4-RECV4` (валидатор чист), `C4-SEND1` (send-boundary: person отклонён когда разрешён только `group`; permissive default отправляет).
- **статус**: done.

#### §4.1 Evidence (+ дедупликация)
- **что требует спека**: evidence-объект; алиасы/теги из одной фразы дедуплицируются.
- **что построено**: `build_evidence` (`kleal_contracts.py:419`), `_det_id:109`.
- **как работает**: `evidence_id` детерминистичен над `(field,value,source,scope)` через sha1 — все алиасы/теги/taxonomy-ноды из ОДНОЙ фразы несут ОДИН id (Feature Builder дедупит по нему). Невалидный source падает к `agent_inference` (никогда не изобретаем авторитет выше доказуемого). Поля normalized через enum-guards (freshness/sensitivity/visibility).
- **ключевые решения**: no-clock/no-randomness id — replay-safe детерминизм; консервативный fallback source.
- **тесты**: `C4-EV1` (одинаковый tuple → одинаковый id; разный value → разный id), `C4-EV2`.
- **статус**: done.

#### §4 Сущность 6 — CandidateSnapshot
- **что требует спека**: версионированный feature-building снапшот scored-карточки.
- **что построено**: `build_candidate_snapshot` (`kleal_contracts.py:439`).
- **как работает**: богатый снапшот когда присутствуют per-feature explain-строки (каждая known группа → Evidence-объект с провенансом из `FEATURE_GROUP_SOURCE`); деградирует до versions+tier+unknowns иначе (legacy scorer / slate-карточка). Несёт `config_version`/`config_sha` из cfg_meta.
- **ключевые решения**: config-derived версии из sha-пиннутого config; degrade-gracefully.
- **тесты**: `C4-INT1` (каждая slate-карточка несёт snapshot), `C4-INT4` (провенанс).
- **статус**: partial (богатое evidence только в explain, где есть per-feature rows — апстрим ещё не всегда даёт detail-строки).

#### §4.7 Proposal
- **что требует спека**: структурированное предложение с идемпотентностью и disclosure-clamp.
- **что построено**: `build_proposal` (`kleal_contracts.py:465`), `_min_disclosure:135`.
- **как работает**: `idempotency_key` детерминистичен над `(intent_id, to_user.lower())` — re-send не дубликат. `allowed_disclosure` = min(intent stage, candidate.receiving.disclosure_stage) — более рестриктивная из двух. Payload — title/topics/time/place; TTL=`PROPOSAL_TTL` (24ч).
- **ключевые решения**: стабильный idempotency-key при повторной отправке; disclosure-clamp к более строгому.
- **тесты**: `C4-PROP1` (idempotency стабилен через re-send с разным now; clamp к minimal).
- **статус**: done (disclosure-clamp консервативно no-op т.к. stage_map минимальный → partial по глубине).

#### §4.8 Reservation
- **что требует спека**: временный hold ёмкости с версией для оптимистичной ревалидации.
- **что построено**: `build_reservation` (`kleal_contracts.py:489`).
- **как работает**: контракт-стаб — `reservation_id`/resource/holder/version/ttl/expires_at/status=`held`. В person_to_person пилоте реальной capacity-системы нет; используется post-pilot group/plan потоками.
- **ключевые решения**: контракт определён заранее чтобы group/plan-флоу имел стабильную форму.
- **тесты**: покрыт формой в CP9-REGISTRY manifest.
- **статус**: partial (нет capacity-системы в person-to-person пилоте).

#### §4.9 Match
- **что требует спека**: purpose-bound Match-капсула по взаимному accept.
- **что построено**: `build_match` (`kleal_contracts.py:499`).
- **как работает**: строит капсулу из записи `SESSION['_matches']` — `match_id` детерминистичен над `(purpose_id, sorted participants)`, статус = completed/active/expired по timestamp'ам, свой purpose_id/version/TTL (`MATCH_TTL` 7д).
- **ключевые решения**: COMPAT-1 — метрика успеха `matches` остаётся int, а `match_capsules` — list объектов Match (разные вещи, не смешиваются).
- **тесты**: `C4-CAP1` (matches остаётся int; match_capsules — list Match-объектов с match_id).
- **статус**: done.

#### §4.10/§4.11 Group / Plan (declared_disabled)
- **что требует спека**: set-formation (Group) и agreed-activity (Plan) контракты.
- **что построено**: `build_group` (`kleal_contracts.py:515`), `build_plan:521`.
- **как работает**: контракты полностью определены, но возвращают `enabled=False` — group_formation выключен в пилоте (§1.2/§15/§16), plan — post-pilot (§14/§16). `group_id`/`plan_id` детерминистичны.
- **ключевые решения**: pilot-disabled — форма зафиксирована, поведение выключено (declared_disabled, не отсутствует).
- **тесты**: форма в CP9-REGISTRY manifest; интеграция plan — CP10-PLAN-COORD (`enabled:False`).
- **статус**: pilot_disabled.

#### §4.12 RelationshipEdge
- **что требует спека**: история пары (состояние отношений).
- **что построено**: `build_relationship_edge` (`kleal_contracts.py:529`), `EDGE_STATES`.
- **как работает**: выводит state из outcome-view над session-store по приоритету block > avoid > repeat(≥2 completed) > friend(≥1 completed) > contact(≥1 accepted) > new. `edge_id` детерминистичен над sorted(pair). Считает `cooldown_until` при активном cooldown.
- **ключевые решения**: **advisory** — авторитетный cooldown остаётся matching hard-gate (`declinedOwnerDaysAgo`); edge не должен double-gate.
- **тесты**: `C4-EDGE1` (полный порядок приоритета состояний).
- **статус**: done.

#### Enum-drift guard (CI-защита)
- **что требует спека**: тотальность карт (нет молчаливого under-disclosure при новом домене).
- **что построено**: `assert_enums_match` (`kleal_contracts.py:558`) + enum-кортежи (INTENT_STATUS/PROPOSAL_TYPES/DISCLOSURE_STAGES и т.д.).
- **как работает**: возвращает список drift-проблем — домен без `DOMAIN_TO_CONTEXT`, контекст без `PURPOSE_FIELDS`, deny-column утечки (datingOk вне dating, entities в dating). Тест ассертит пустой список — новый engine-домен без обновления карт валит CI, а не молча под-раскрывает.
- **ключевые решения**: fail-CI-loud вместо silent-deny (SPEC-2 тотальность).
- **тесты**: `C4-ENUMS` (каждый core-домен имеет context+allow-list).
- **статус**: done.

### §17.1 расширения контрактов (тесты CP2-*)
Реализованы в том же `shared/kleal_contracts.py` (keyless, детерминизм через инжект `now`).

#### CP2 — Dating-капсула + минимизация чувствительного
- **что требует спека (§17.0/§17.1.profile)**: отдельная purpose-bound dating-капсула с data-минимизацией.
- **что построено**: `build_dating_capsule` (`kleal_contracts.py:212`), `age_band:199`, `_DATING_SENSITIVE`.
- **как работает**: строится поверх `build_profile_view(purpose='dating')` → профессиональный `entities` структурно исключён (не в allow-list); плюс экстра-минимизация: exact age коарсится в band через `age_band` (если нет `consent_exact_age`); чувствительный контур (orientation/gender_target/preferences/health/religion/politics) никогда не поверхностится. Свой `policy_version` + `sensitive_excluded=True`.
- **ключевые решения**: purpose-binding + data-minimization по умолчанию; exact-age только по явному consent; keyless/детерминизм.
- **тесты**: `CP2-DATING-CAPSULE` (нет entities/orientation; age_band=`25-34` без consent; age=29 при consent).
- **статус**: done.

#### CP2 — Staged disclosure (per-field stage gates)
- **что требует спека (§17.1.disclosure)**: поэтапное раскрытие по полям.
- **что построено**: `disclosure_field_stages`-логика внутри `build_profile_view` (`kleal_contracts.py:184`), `DISCLOSURE_RANK`.
- **как работает**: `user['disclosure_field_stages'] = {field: stage}` удерживает поле, чей требуемый stage выше текущего; отсутствие — no-op (byte-identical к generic stage-проекции).
- **ключевые решения**: opt-in per-field; absent → byte-identity к базовой проекции.
- **тесты**: `CP2-DISCLOSURE` (поле `match_only` скрыто на limited_profile, видно на match_only; name всегда есть; нефильтрованный view неизменён).
- **статус**: done.

#### CP2 — Decay инференции (§19.2)
- **что требует спека**: soft agent_inference теряет уверенность со временем; explicit-правки выживают.
- **что построено**: `decay` (`kleal_contracts.py:229`), `drop_inferred:244`.
- **как работает**: `decay` — только L7 `agent_inference` теряет confidence по ~30-дневному half-life (`0.5**(age_days/30)`); высшие источники возвращаются без изменений; возвращает копию (не мутирует вход, детерминизм через `now`). `drop_inferred` удаляет только L7-строки.
- **ключевые решения**: одна поведенческая инференция никогда не становится постоянной; explicit выживает; детерминизм.
- **тесты**: `CP2-DECAY` (60д = 2 half-life → confidence ≈0.2; L4 untouched=0.9; drop_inferred удаляет только inferred).
- **статус**: done.

### §22.2.0 / §23.4.1 реестр и схема (тесты CP9-*)
Реализованы в `shared/kleal_contract_registry.py` (импорт `kcr`), опирается на `kleal_contracts`.

#### CP9 — Registry manifest (§22.2.0)
- **что требует спека**: stage-0 манифест всех entity-билдеров + версии config/contract/state.
- **что построено**: `manifest` (`kleal_contract_registry.py:22`), `ENTITY_BUILDERS`.
- **как работает**: возвращает `entities` (все §4-билдеры), `contracts_version`, `states_version`, `config_version`+`config_sha` (config-derived), `proposal_types`, `contexts`.
- **ключевые решения**: единый machine-readable реестр; версии тянутся из sha-пиннутого config, не хардкодятся.
- **тесты**: `CP9-REGISTRY` (манифест содержит все §4-сущности + совпадающие config/contracts версии).
- **статус**: done.

#### CP9 — Schema mirror + валидация (§23.4.1)
- **что требует спека**: machine-checkable draft-07 схема purpose-binding контрактов.
- **что построено**: `contracts_schema` (`kleal_contract_registry.py:36`), `validate_profile_view:57`.
- **как работает**: схема выводится из ТЕХ ЖЕ allow-lists, что использует движок (`PURPOSE_FIELDS`/`DISCLOSURE_STAGES`/`CONTEXTS`). `validate_profile_view` — read-only: проверяет required-ключи, что `fields` ⊆ allow-list контекста (purpose binding), и enum disclosure_stage.
- **ключевые решения**: схема config-derived из одного источника с движком — контракт машинно-проверяем, не только проза.
- **тесты**: `CP9-SCHEMA` (валидная проекция → []; поле вне allow-list, напр. datingOk во friendship → ловится).
- **статус**: done.

> Примечание: `CP9-CONFIG-HEALTH` и `CP9-EVAL-POLICY` относятся к §21.4/§23.4.2 (health-снапшот и policy-facade в `services/matching/app.py`), а не к §4-контрактам; в §4-контексте релевантны CP9-REGISTRY и CP9-SCHEMA.

### Итоговый статус §4 (по `docs/CONTRACTS.md`)
✅ 17 · 🟡 9 · ⬜ 0. Group/Plan — declared_disabled (контракт определён, `enabled=False`). Партиалы (🟡) — там, где апстрим-онбординг ещё не собирает данные, а фабриковать их нельзя (CandidateSnapshot rich-evidence, Reservation capacity, §4.3 time windows/location safe_zones/target level/social pressure/domain_details). Всё — локально, keyless, детерминистично; sha-пиннутый core_v2+config не тронуты, person-slate байт-идентичен.

---

> Дисциплина фактов: оба модуля (`shared/kleal_intent.py` `ki`, `shared/kleal_taxonomy.py` `kt`) — **keyless и полностью LLM-free** (детерминированные; LLM в §5 — только парсер, его вывод недоверенный). Sha-пиннутый движок `core_v2.py` + YAML-конфиг (`PINNED_SHA 21505ccb`) **не тронуты** ни строкой. Person-slate **byte-identical** при enrichment ON/OFF (тест `C6-PARITY-ENRICH`) и при нормализации (`C5-GATE1..3` — hard-гейты не ослаблены). Всё построено как **аддитивный слой поверх** запечатанного скоринга. **Ничего не задеплоено** — весь код локальный (`data/taxonomy/*.json` на под сознательно не шипается, слой честно деградирует до in-code нарратива).

Общая архитектура: §5 (`ki`) валидирует/нормализует intent и ведёт политику уточнений перед матчингом; §6 (`kt`) — строго read-only нарратор/governor над скорером, инъекция через `app.bind_engine(...)` (строки `services/matching/app.py:202-203`), без `import app` (нет цикла), без FS на импорте.

---

## §5 — Intent Compiler и политика уточнений (`shared/kleal_intent.py`)

#### §5 intro — недоверенный LLM-вывод: валидация/нормализация

- **что требует спека**: выход LLM-парсера недоверенный — прогнать через schema-validation / allowlist / нормализацию, прежде чем он повлияет на матчинг.
- **что построено**: `validate_and_normalize(intent, source) -> (out, report)` — `kleal_intent.py:validate_and_normalize` (стр. 54-112); идемпотентная обёртка `normalize_for_scoring(intent)` — `kleal_intent.py:normalize_for_scoring` (стр. 114-117).
- **как работает**: дозаполняет 16 плоских ключей **только** из `kc._FLAT_DEFAULTS` (нейтральные дефолты, не «ужесточённые» дефолты парсера — чтобы не фабриковать гейты); allowlist `type`→`TYPE_ALLOWLIST` иначе `social`, `role`→`ROLE_ALLOWLIST` иначе `meet`, `mode`→`MODE_ALLOWLIST` иначе `offline`; topics lower/strip/order-preserving-dedup/cap 4 **без** таксономии/перевода; numeric clamp fail-open (`radiusKm`∈[1,500], age [18,120], `minAge>maxAge`→drop maxAge); boolean-коэрция. Возвращает `(out, report)`, никогда не бросает; финальная read-only проверка `kc.validate_intent` (ключи не теряются/не переименовываются).
- **ключевые решения**: `requiredLanguages` — **только** усечение `str(l)[:2].lower()`, никаких name→ISO карт (иначе прямой гейт «Spanish»→`sp` молча стал бы `es` и изменил семантику гейта). Идемпотентность — иначе дрейфует `intent_id` и рушится explain-vs-search PARITY-гард. Слой аддитивный: не переименовывает/не дропает ни одного плоского ключа, что читает `core_v2`.
- **как подключено**: `parse_intent` прогоняет **обе** ветки (LLM-успех и fallback) через `validate_and_normalize` (`app.py:668-686`); `normalize_for_scoring` вызывается идентично в начале и `match_candidates` (`app.py:1260`), и `explain_match` (`app.py:2155`) — единая точка компиляции для PARITY.
- **тесты**: `C5-GATE1/2/3` (load-bearing: hard-гейты language/radius/dating всё ещё BLOCK-ают), `C5-NORM1` (off-enum deny-safe + dedup + clamp), `C5-NORM2` (2-char truncation, НЕ name→ISO), `C5-NORM3` (идемпотентность + все 16 ключей сохранены), `C5-NORM4` (dating не авто-ужесточается — нет инъекции verifiedOnly/minAge).
- **статус**: done.

#### §5.1 — Hard vs soft ограничения (`extract_constraints`)

- **что требует спека**: магнитить исходный free-text на hard/soft ограничения; sensitive/крупно-исключающие/safety — только через подтверждение.
- **что построено**: `extract_constraints(text, intent, now) -> (out, constraints)` — `kleal_intent.py:126-180`; детерминированный EN+RU keyword/regex-магнит (`_LANG_PHRASE`, `_ONLY_LANG_RE`).
- **как работает**: 5-рядная таблица, пишет **только новые sibling-ключи**, ни один из 16 gate-ключей не трогается: (1) «рядом/nearby»→`preferredNearby`+`softLocationBias` (soft); (2) «только по-испански»→`proposedRequiredLanguages=['es']` (kind `hard_after_confirm`, `requiredLanguages` НЕ пишется); (3) «без токсиков»→`moderationPrefs`+`domainConstraints.no_toxicity` (moderation); (4) «можно онлайн»→`allowOnlineFallback`+`allowedModes` (`mode` остаётся offline, без молчаливой подмены); (5) «вторую половинку/soulmate»→`proposedType='dating'`+`evergreenGoal` (`type` не меняется). Каждый constraint — dict с `{id, phrase, kind, field, proposed_value, sensitive, excludes_large_share, safety_impact}`.
- **ключевые решения**: ни один hard-гейт не создаётся в момент извлечения — sensitive ограничения промоутятся только `apply_confirmation` после подтверждения summary. Детерминизм — чистый regex/keyword, без LLM.
- **тесты**: `C5-EXT1` (5-рядный магнит, аддитивные ключи), `C5-EXT2` («only spanish» не пишет `requiredLanguages`, предлагает `es`), `C5-EXT3` («online ok» не свапает mode), `C5-EXT4` («soulmate» → proposed dating, type/гейт не сработали).
- **статус**: done для 3 рядов; **partial** для «рядом» и «без токсиков» — surface-only (у sha-пиннутого `core_v2` нет consumer для ранжирующего сдвига; реальный bias требовал бы правки движка — нельзя без слома пина/PARITY).

#### §5.1 — Правило подтверждения (`intent_summary`) + промоут (`apply_confirmation`)

- **что требует спека**: любое ограничение, исключающее большую долю / раскрывающее sensitive-предпочтения / влияющее на safety — должно быть подтверждено пользователем.
- **что построено**: `intent_summary(intent, constraints) -> dict` — `kleal_intent.py:186-207`; `apply_confirmation(intent, confirmed_ids, constraints, now) -> out` — `kleal_intent.py:209-234`.
- **как работает**: `intent_summary` собирает `constraints_to_confirm` (по предикату `_summary_items`: sensitive ИЛИ excludes_large_share ИЛИ safety_impact>0), уже-подтверждённые (`intent._confirmed.ids`) выпадают; ставит `requires_confirmation` и `may_empty_pool_warning` (флаг pending hard-гейта, способного легально опустошить пул — §12 never-dead-end). `apply_confirmation` промоутит **только** подтверждённые ids: `proposedRequiredLanguages`→`requiredLanguages` (усечение сохраняется), `dating_evergreen`→`type='dating'` **без** авто-`verifiedOnly`/`minAge`, плюс структурный §17.1 `dating_consent` (opt_in, target_prefs, iso-время) — появляется только при подтверждении, никогда не выводится; стемпит §4.2-провенанс level-2 `user_confirmed_intent_summary`.
- **ключевые решения**: неподтверждённые sensitive-ограничения остаются soft/absent — никогда не становятся молчаливым hard-гейтом. `type=dating` промоутится **без** side-effects на возраст/верификацию (изоляция dating-контура). Эндпоинт **`POST /api/agent/confirm`** (`app.py:2366-2387`).
- **тесты**: `C5-CONF1` («only spanish» блокирует не-носителя ТОЛЬКО после `/confirm`), `C5-CONF2` (confirmed dating → type=dating без verifiedOnly/minAge, source stamped), `C5-SUMM1` (summary требует confirm и перечисляет sensitive + may_empty_pool_warning), `C5-SUMM2` (уже-подтверждённое выпадает из summary — нет ре-промпта).
- **статус**: done.

#### §5.2 — Политика уточнений (`clarification_policy`)

- **что требует спека**: детектировать пробелы, задать не более одного вопроса, не спрашивать до первых результатов кроме обязательного safety.
- **что построено**: `clarification_policy(intent, constraints, has_results) -> dict` — `kleal_intent.py:315-337`; детектор `_detect_gaps` (стр. 271-308), предикат `_is_mandatory_safety` (стр. 310-313), фабрика `_gap`.
- **как работает**: `_detect_gaps` классифицирует пробелы P0/P1/P2/P3 — P0 mandatory (dating opt-in pending, games platform/crossplay, неподтверждённый required-language), P1 high-value (time horizon, город/online, 1:1-vs-group, native-vs-level), P2 ranking-only (skill/team/rank), P3 cosmetic (заголовок). Выбор **rule-based** (не EVI-формула): каждый gap несёт 4 ordinal-фактора {0,1,2} (`safety_impact, candidate_pool_split, supply_unlock, user_control`), `friction` — тай-брейк; сортировка `(class_rank, −4 фактора, friction)` → один верхний gap = максимум один вопрос. До первых результатов (`has_results=False`) спрашивается только `_is_mandatory_safety` (safety_impact==2 ИЛИ ref==`dating_opt_in`); прочие P0 (platform, язык) корректно откладываются (`deferred=True`).
- **ключевые решения**: rule-based ordinal вместо непрозрачной EVI-формулы — детерминизм + объяснимость. B1-фикс: не каждый P0 — safety (platform/язык — eligibility, не safety → defer до результатов). On-refuse action на каждый gap записан (безопасная альтернатива, без скрытого дефолта).
- **тесты**: `C5-CLAR1` (dating opt-in P0-safety спрашивается до результатов), `C5-CLAR2` (games platform P0-non-safety откладывается pre-results, спрашивается after-results), `C5-CLAR3` (максимум ОДИН вопрос при нескольких gap-ах).
- **статус**: done; **partial** для P2 — класс/defer есть, ре-ранжирование по ответу нет (нельзя без правки движка).

#### §5.3 — Минимально достаточный intent (`minimally_sufficient`)

- **что требует спека**: чеклист «intent минимально достаточен для матчинга».
- **что построено**: `minimally_sufficient(intent) -> {ok, missing, present}` — `kleal_intent.py:237-260`; хелпер domain-critical `_domain_critical` (стр. 30-43).
- **как работает**: verification-only (не стемпит) по уже-скомпилированным §4-блокам: `domain+activity/purpose`, `time_horizon` (явное «Flexible» валидно), `mode+format`, `location_or_online_fallback`, `domain_critical` (поля по (domain,role) — games→platform/rank, sport→skill/team, language→level, networking→industry/goal, dating→dating_opt_in), `fallback+disclosure`, `ttl_and_budget` (уже из §4 `compile_intent.lifecycle`). Возвращает списки missing/present.
- **ключевые решения**: config-derived — `_domain_critical` кейзится по РЕАЛЬНОМУ `core_v2.infer_domain` домену (`sport_activity`, не `sport_play`), чтобы чеклист совпадал с движком.
- **тесты**: `C5-MIN1` (online intent минимально достаточен — ttl+budget присутствуют через §4 lifecycle), `C5-INT1` (`_section5_addendum` несёт intent_summary+clarification+minimally_sufficient, слейт не ломается).
- **статус**: done; **partial** для domain-critical (карта есть, апстрим не всегда собирает platform/rank/level/skill).

#### Интеграция §5 в матчинг/эндпоинты

- **что построено**: `_section5_addendum(intent, text, cands)` — `app.py:1546-1552` — аддитивные ключи ответа (summary + clarification + minimally_sufficient), не мутирует intent/слейт; вкраплён в `agent_plan` (`app.py:1566`), explain (`app.py:2088`) и `/api/agent/confirm` (`app.py:2382`).
- **тесты**: `C5-INT1`. **статус**: done.

---

## §6 — Governed taxonomy / evidence / expansion (`shared/kleal_taxonomy.py`)

Модуль `kt` — строго read-only. **Никогда** не пересчитывает tier/score: движок (`core_v2.assign_tier`/`SEM_VALUE`/`directional_score`, `app.topical`) — единственный источник истины. Всё — аддитивные метаданные карточки (`taxonomy_edge`/`expansion_chain`/`complementary`), governance и фальсифицируемые доказательства. `bind_engine(**fns)` (стр. 30-33) инъектит движковые функции + `graph_txn`; при не-вызванном bind все публичные функции no-op-ят. Онтология `data/taxonomy/*.json` грузится лениво, mtime-кэшируется, каждый read guarded → при любой ошибке пустая онтология + чистый in-code нарратив (честный pod default: data не задеплоена).

#### §6 — Типизированные рёбра (`edge_type`, `edge_for`)

- **что требует спека**: классифицировать связь topic↔interest типизированным ребром (exact/alias/sibling/parent/adjacent), объяснить.
- **что построено**: `edge_type(a, b)` — `kleal_taxonomy.py:117-154`; `edge_for(topics, interests)` — стр. 177-201; advisory-зеркала `_SEM_VALUE_MIRROR`/`_BEST_TO_TYPE`/`_BEST_TO_TIER`/`_EDGE_NOTE` (стр. 41-52).
- **как работает**: классификация через **тот же движковый reducer** `topical([a],[b]) → best`, затем метка. best≥4: `exact_entity` (идентичная сырая форма) / `alias` (разная форма, один канон через SYNONYMS: `norm(a)==norm(b)`) / `literal_token_share` (off-taxonomy shared word — `cat_of` пуст → НЕ выдуманное exact-ребро); 3→`direct_sibling`; 2→`parent`; 1→`adjacent_purpose`; 0→`none`. `semantic_tier` — advisory-зеркало `assign_tier` (T2 сворачивает sibling(3)+parent(2); **T4 никогда** не эмитится). `edge_for` выбирает единственное лучшее ребро — зеркалит single-best-tier reducer движка. `_enrich_edge_from_ontology` доливает `ontology_relation/tier/explanation`; при расхождении tier — `governance_finding`, движок предпочитается.
- **ключевые решения**: byte-identity — `kt` не считает score, лишь зеркалит; при отсутствии онтологии edge собирается из движка (source `in_code`). advisory-флаг на всех зеркалах.
- **тесты**: `C6-EDGE1` (exact_entity, best 4, T1), `C6-EDGE2` (soccer~football → alias, не exact), `C6-EDGE3` (labubu → literal_token_share, не фабрикованный exact), `C6-EDGE4` (parent T2, никогда T4), `C6-EDGE5` (no overlap → none/0).
- **статус**: done.

#### §6 — Объяснение расширения (`expand`) — «обязательно объяснить»

- **что требует спека**: parent/sibling-матч обязан объяснить цепочку расширения.
- **что построено**: `expand(topic)` — `kleal_taxonomy.py:204-226`; онтологическое обогащение `_enrich_expand_from_ontology` (стр. 228-251).
- **как работает**: `cat_of(topic)` → цепочка interest→sub_category→broad_category (in-code, авторитетно), `explanation` = `"a → b → c"`. Онтология доливает `ontology_chain` (обход `interests.json.parent_id`, guard ≤8, cycle-safe). На карточку `expansion_chain` кладётся `enrich_card` только для parent/sibling (best 2/3). При drift домена — `governance_finding`, движок предпочитается.
- **тесты**: `C6-EXPAND1` (цепочка interest→sub→broad, in-code bucket, «→» в explanation). **статус**: done.

#### §6 — Комплементарные роли (`complementary`) — МАТРИЦА, не similarity

- **что требует спека**: комплементарные роли (подходящие друг к другу), это НЕ similarity-скор.
- **что построено**: `complementary(role_a, role_b)` — `kleal_taxonomy.py:268-285`; матрица `_COMPLEMENT` (стр. 256-266); онтологический фолбэк `_complement_from_ontology`.
- **как работает**: типизированное ребро из hardcoded-матрицы (support↔carry, tank↔healer, learner↔native, cofounder↔engineer, mentor↔mentee…) + role/team/game/project/language edges онтологии; `similarity: False`. Одинаковые роли (`ra==rb`) и конфликтные (play↔watch = `ROLE_CONFLICT`) → None. Чисто метаданные, в скоринг не идут.
- **ключевые решения**: явный `similarity: False` — семантически комплемент ≠ похожесть; play↔watch не должен ложно стать комплементом.
- **тесты**: `C6-COMPL1` (support↔carry типизирован, similarity=False), `C6-COMPL2` (play↔watch — конфликт → None).
- **статус**: done.

#### §6 — Governance (`governance_of`, `validate`)

- **что требует спека**: каждое ребро под управлением — owner/version/aliases/review_state/evidence/rollback.
- **что построено**: `governance_of(edge)` — `kleal_taxonomy.py:303-334`; read-only валидатор `validate(edge)` — стр. 336-346.
- **как работает**: приклеивает 6 полей: `owner` (`matching-engine@app.py` для in-code / `ontology@data/taxonomy` для JSON), `version` (`matching-core-2.0.0`), `language_aliases` (ru/en/es из `aliases.json`, ≤6), `review_state` (`in_code`/`active`), `evidence` (`kc.build_evidence("taxonomy.node", canon, ...)` — keyed на **канонический узел**, так alias и канон коллапсируют в ОДИН `evidence_id`, §4.1 dedup), `rollback` (`sha-pinned:21505ccb — Dev-B core_v2 version bump` / drop-edge-row). `validate` проверяет наличие 6 полей + легальный review_state, никогда не мутирует.
- **ключевые решения**: evidence keyed на node/канон, не на surface form — alias «soccer» и exact «football» дают один evidence_id. Rollback in-code рёбер прямо ссылается на sha-пин — правка требует координированного version-bump с Dev B.
- **тесты**: `C6-GOV1` (6 полей + легальный review_state), `C6-EVID-ONE-ID` (alias+канон = один evidence_id).
- **статус**: done.

#### §6 — Фальсифицируемые доказательства (`alias_invariant`, `shadow_replay`) — TEST-ONLY

- **что требует спека**: добавление alias не должно повышать score существующей пары; изменение графа проходит shadow replay.
- **что построено**: `alias_invariant(fixture_pairs, alias_to_add)` — `kleal_taxonomy.py:349-371`; `shadow_replay(mode, edits, replay_fn, fields)` — стр. 373-404; канал правки `graph_txn` — `app.py:174-200` (единственный санкционированный, под `_GRAPH_LOCK`, restore в `finally`).
- **как работает**: `alias_invariant` пишет `best_before` через инъектированный `topical`, транзакционно добавляет alias в **живой** граф через `graph_txn` (движок реально резолвит), пишет `best_after`, требует `after ≤ before` для всех пар. `shadow_replay` — Mode A (`ontology`): edit к reference-данным, что скоринг не читает → replay обязан быть byte-identical на 4 gate-полях (band/tier/lcb/can_outreach) — доказывает additive-only; Mode B (`graph`): правка живого SYNONYMS/TAXONOMY/ADJACENCY через `graph_txn` → diff полей — реальный гейт над живым скорером. Оба с negative-control.
- **ключевые решения**: `graph_txn` транзиентно меняет реальный score → **только offline/тесты**, никогда в живом хендлере (явно задокументировано `app.py:170-171`). Negative-controls делают доказательства фальсифицируемыми (не вакуумными).
- **тесты**: `C6-ALIAS-INV` (benign alias — ничего не поднял), `C6-ALIAS-INV-NEG` (dota→coffee поднимает coffee~dota 0→4, инвариант ловит ok=False), `C6-SHADOW-A-NEG` (детектор ловит diff), `C6-SHADOW-B` (live-graph edit детектится над реальным скорером), `C6-SHADOW-B-RESTORE` (`graph_txn` восстановил граф, dota~coffee снова no-match).
- **статус**: done.

#### §6 — Enrichment surface (`enrich_card`) + PARITY

- **что построено**: `enrich_card(topics, cand_interests, role_a, role_b)` — `kleal_taxonomy.py:407-425`; вызывается в `match_candidates` (`app.py:1347`) и explain (`app.py:2256`) через `setdefault`.
- **как работает**: собирает `taxonomy_edge`/`expansion_chain` (для best 2/3)/`complementary`, fully guarded → `{}` на любой ошибке, так НИКОГДА не опустошит слейт и не изменит score. Ключи доливаются через `setdefault` — не перетирают движковые.
- **тесты**: `C6-BIND` (kt связан с реальной таксономией), `C6-PARITY-ENRICH` — band/tier/lcb/can_outreach **byte-identical** при enrichment ON vs OFF (`kt._ENGINE.clear()` = OFF), при этом `taxonomy_edge` присутствует ON и отсутствует OFF.
- **статус**: done.

---

### Сводный статус

- **§5**: 22 ✅ / 4 🟡 (partial). Partial: «рядом» и «без токсиков» surface-only, §5.2 P2 ре-ранжирование, §5.3 domain-critical апстрим-сбор — все требуют правки sha-пиннутого движка/конфига (нельзя без слома пина и PARITY).
- **§6**: 13 ✅ / 0 ⬜ / 6 blocked_sha_pinned. Blocked требуют Dev-B version-bump `core_v2`/конфига (SEM_VALUE-как-config, sibling 0.55–0.75 из domain config, negative-edge как штраф скоринга, богатые per-group subfeatures, embedding recall, внутренности 6 групп) — сознательно не отдаются read-only слоем.
- Тесты: `services/matching/test_core_v2.py` — блок `C5-*` (~20 проверок, вкл. load-bearing `C5-GATE1..3`) и блок `C6-*` (18 проверок, вкл. negative-controls, `C6-EVID-ONE-ID`, `C6-PARITY-ENRICH`). Всё локально, движок и конфиг не тронуты.

---

Все функции живут в `services/matching/app.py` как **read-only, keyless, LLM-free** слой поверх запечатанного скорера `core_v2.py` (sha-пиннут, не тронут). Слой строго аддитивен: новые гейты и провенанс не меняют детерминированный score/tier/band, а person-slate остаётся byte-identical на реальном `_gen_pool`. Всё локально, ничего не задеплоено.

## §7 — Candidate retrieval

#### §7.1 Порядок источников (5 retrieval sources)
- **что требует спека:** кандидаты извлекаются из 5 источников в фиксированном порядке приоритета (собственный активный intent → прямой интерес → группы → события/комнаты → parent/adjacent расширение).
- **что построено:** константа `RETRIEVAL_SOURCES` (app.py:1172) + провенанс-функция `_retrieval_source` (app.py:1180), ранжирующая таблица `_SOURCE_RANK` (app.py:1198).
- **как работает:** `_retrieval_source(intent, c, best)` возвращает источник на карточку: `1` если собственный активный intent кандидата реципрокно совпал (`_reciprocal`), `2` при прямом подтверждённом интересе (topical `best>=4`), `5` при parent/sibling/adjacent (`best 1..3`), `0` — no-overlap хвост. Источники 3 (groups_with_capacity) и 4 (events_and_rooms) объявлены, но `enabled:False` — pilot-disabled, извлекают ноль кандидатов, а не фейкятся.
- **ключевые решения:** источник кандидата резолвится детерминированно из topical-overlap; keyless (без LLM); источники 3/4 честно отключены под пилот (`kleal_intent.PILOT_DECISION_TYPES`), источник 4 выражен как T4-альтернатива, а не как поддельный человек.
- **тесты:** `C7-SOURCE` (каждая карточка несёт source ∈{1,2,5}), `C7-SOURCE2` (direct-interest Cora → source 2, не хвост), `C7-SOURCES-DISABLED` (3 и 4 объявлены, но disabled; 1 enabled).
- **статус:** done (источники 1/2/5 live; 3/4 pilot_disabled).

#### §7.1 Tier-таблица T0–T5 (immutable provenance) + T4 alternative-solution
- **что требует спека:** семантические tier — неизменяемый provenance; релевантность мерится отдельно внутри каждого tier; должен существовать «alternative solution type» (не человек), закрывающий intent.
- **что построено:** назначение tier делает запечатанный `core_v2.assign_tier` (T0 reciprocal / T1 exact / T2 parent+sibling / T3 adjacent / T5 none); `_online_fallback` (app.py:1523) выражает T4; `_tier_analytics` (app.py:1221).
- **как работает:** `_online_fallback` возвращает объект `room` с `tier:"T4"`, `kind:"alternative_solution_type"`, `retrieval_source:4`, `ladder_step:6` и без personal outreach — онлайн-комната как другой способ закрыть intent, когда 0 offline-кандидатов. `_tier_analytics` агрегирует explain-строки по tier: count + lcb mean/min/max + coverage_mean, измеряя relevance СТРОГО внутри каждого tier (аналитика никогда не повышает tier).
- **ключевые решения:** tier — immutable provenance от запечатанного ядра, логистика его не трогает; T4 — не персона (никакого личного контакта); `_online_fallback` уважает `allowOnlineFallback` (§5.1 row4 — offline никогда молча не подменяется на online).
- **тесты:** `C7-T4` (online-room → T4 / alternative_solution_type / source 4, без outreach), `C7-TIER-ANALYTICS` (per-tier распределение).
- **статус:** done.

#### §7.2 Семиэтапный retrieval-конвейер + бюджеты
- **что требует спека:** staged retrieval-пайплайн (hard prefilter → structured → ANN recall → feature build → ranking/slate → explanation → agent probe) с бюджетами на каждом этапе.
- **что построено:** декларативная таблица `RETRIEVAL_STAGES` (app.py:1160), бюджеты `RETRIEVAL_BUDGET` (app.py:1157), фактический staged-cut `_retrieve` (app.py:1200), отчёт `_retrieval_report` (app.py:1242).
- **как работает:** `_retrieve(intent, eligible, budget)` метит каждого eligible-кандидата §7.1-источником, сортирует по retrieval-приоритету (`reciprocal → direct → adjacent → no-overlap tail` через `_SOURCE_RANK`, вторичный ключ `-best`, затем имя) и режет по бюджету, возвращая `(retrieved, source_by, stats)`. Вызывается из `match_candidates` (app.py:1279) между построением `eligible` и `_core.search`. Дефолтный бюджет `500` ≫ прод-стора (~100), поэтому на пилоте — no-op.
- **ключевые решения:** **несущая гарантия byte-identity slate** — `core_v2.search` делает тотальную пересортировку, поэтому порядок retrieval невидим; бюджет-cut отбрасывает только no-overlap хвост (best=0 → T5), который движок и так не показывает; `_expand_fallback` (never-dead-end §12) получает ПОЛНЫЙ eligible-пул, не урезанный бюджетом (app.py:1282). ANN/pgvector-этап честно помечен `status: blocked_infra` (вне stdlib-прототипа); hard_prefilter — детерминированный in-mem stand-in для SQL/PostGIS/H3.
- **тесты:** `C7-STAGES` (все 7 этапов присутствуют, ANN честно blocked_infra), `C7-BUDGET-NOOP` (дефолтный бюджет — no-op), `C7-BUDGET-BITE` (фальсифицируемо: бюджет 2 из 5 реально режет, но `_names_bands` slate идентичен дефолтному — отброшены только 3 no-overlap хвоста).
- **статус:** done (ANN recall — blocked_infra; agent_probe — partial: сейчас negotiate top-5, не таргетированный probe).

## §8 — Eligibility / privacy / safety / purpose binding

Инвариант входа: скоринг стартует ТОЛЬКО после ALLOW; BLOCK не попадает в ranking/probe; REVIEW = discoverable, но не auto-proposable. В `match_candidates` (app.py:1266-1274) цикл по `load_candidates()` вызывает `_policy_decision`, пропускает BLOCK, а ALLOW+REVIEW складывает в `eligible` с картой `policy_by`.

#### §8.1 Канонические hard-gates
- **что требует спека:** набор дешёвых детерминированных исключений до скоринга (block, cooldown, age/legal, dating-mode, radius, language, capacity + account/privacy/safety).
- **что построено:** `_hard_gates` (app.py:729) возвращает `(ok, reason)`.
- **как работает:** по порядку проверяет `paused`, взаимный block (`blocked`/`blocksMe`), cooldown после отказа, `MAX_PENDING`, `MIN_AGE` (18+), dating-open, verifiedOnly, age-range, required-languages, offline-radius. **Добавлены в §8 (в самый конец, чтобы старые reason-tuple не сдвинулись):** `account_status` (`accountStatus∈{suspended,deactivated,banned,deleted}` или `suspended=True` → "account not active"), privacy `visibility=='private'` → "private profile", `safetyFlags ∩ _SAFETY_BLOCK` → "safety restriction". Каждый новый гейт срабатывает ТОЛЬКО на присутствующем ограничительном значении.
- **ключевые решения:** absent-field → ALLOW (byte-identity демо-пула и фикстур); осознанное отклонение от спеки — спека требует account unknown⇒BLOCK, но фикстуры не несут поля, поэтому unknown⇒ALLOW (partial/DORMANT, включается флагом когда бэкенд гарантирует `active`). Новые гейты аппендятся последними, чтобы существующие reason-строки не менялись.
- **тесты:** `C8-ACCT`, `C8-PRIV`, `C8-SAFE` (present-bad → BLOCK; absent → ALLOW).
- **статус:** done (гейты по новым полям — DORMANT, пока admin/onboarding не пишут поля в стор).

#### §8.1 Cross-purpose / intent-mode isolation
- **что требует спека:** изоляция по назначению — dating не должен смешиваться с friendship/networking/language/games/sport.
- **что построено:** `_cross_purpose_blocked` (app.py:711) — shared helper; пары `_XPURPOSE_BLOCK` (app.py:701), маппинг `_TYPE_PURPOSE`.
- **как работает:** резолвит purpose intent-а по `type`, затем сканирует СОБСТВЕННЫЕ активные intents кандидата (`c['intents']`); возвращает `True` (BLOCK) если пара (ip, cp) ∈ запрещённых. Вызывается и в `_policy_decision` (retrieval BLOCK, app.py:789), и в `_negotiate_precheck` (send BLOCK, app.py:1693) — одна и та же логика на обеих границах.
- **ключевые решения:** purpose кандидата берётся ТОЛЬКО из его own-intents (не из datingOk/receiving/interests) → кандидат без own-intent-purpose возвращает False (ALLOW), поэтому реальный `_gen_pool` byte-identical; shared helper гарантирует, что пара не проскочит через `/api/agent/negotiate`.
- **тесты:** `C8-XPURPOSE` (dating↔friendship → BLOCK), `C8-XPURPOSE-ALLOW`, `C8-GENPOOL-IDENTITY` (slate byte-identical при гейте ON vs OFF на реальном `_gen_pool`, dating и non-dating).
- **статус:** done.

#### §8.1 Три-state policy decision (ALLOW / REVIEW / BLOCK)
- **что требует спека:** policy_decision — не boolean, а три-состояние; REVIEW = discoverable но не auto-proposable до отдельного safety/legal-трека; age⇒BLOCK-или-REVIEW, location⇒REVIEW-или-zone-expansion.
- **что построено:** `_policy_decision` (app.py:773); применение — `_apply_policy` (app.py:1291).
- **как работает:** сначала `_hard_gates`; при неудаче — если `intent.soft_eligibility`/`c.zoneOptIn` и причина ∈ {"age unknown","outside the radius"} → **REVIEW** (opt-in), иначе BLOCK. Затем cross-purpose → BLOCK; `sensitivity=='restricted'`/`"review" in safetyFlags` → REVIEW (soft safety); для domain c `release_gate` и неверифицированного кандидата → REVIEW. `_apply_policy` штампует карту: REVIEW принудительно `can_outreach=False` + note.
- **ключевые решения:** default absent⇒прежний BLOCK (byte-identity counts/slate); softer-семантика — строго opt-in по полю intent/candidate; release_gate читается из sha-пиннутого config (config-derived, не хардкод).
- **тесты:** `C8-SAFE` (sensitivity=restricted → REVIEW), `C8-SOFT-ELIG`, `CP4-ZONE` (out-of-radius + zoneOptIn → REVIEW; без него → BLOCK).
- **статус:** done.

#### §8.1 Domain-critical slots + min-duration (§18 hard slots)
- **что требует спека:** per-domain критичные слоты (server/platform/ticket/industry) — жёсткое исключение при обоюдном объявлении и различии; минимальная длительность встречи.
- **что построено:** `_DOMAIN_CRITICAL_SLOTS` (app.py:727) + блок в `_hard_gates` (app.py:763-770).
- **как работает:** для каждого слота, если И intent И кандидат объявили значение И они отличаются (case-insensitive) → BLOCK "domain slot mismatch: <slot>". Отдельно `minDurationMin` vs `availableMinutes` → BLOCK "window shorter than requested duration".
- **ключевые решения:** absent-permissive by construction — срабатывает только при двустороннем объявлении, поэтому ни одна текущая person-фикстура не тронута (byte-identical).
- **тесты:** `CP4-DOMAIN-SLOT` (server EU vs NA → BLOCK; absent → pass; "EU" vs "eu" → pass), `CP4-MIN-DURATION`.
- **статус:** done.

#### §8.2 Точки ревалидации (7 checkpoints) + POLICY_CHANGED
- **что требует спека:** политика ре-валидируется в 7 точках (slate, send, profile-open, on-accept, shared-chat, reveal-place, reveal-contact, state-change); нельзя молча продолжать старую транзакцию, если live-решение стало строже.
- **что построено:** `revalidate` (app.py:1782), чекпоинты `_REVAL_CHECKPOINTS` (app.py:704), ранги `_DEC_RANK`; отдельно `_negotiate_precheck` (app.py:1661) для send-границы.
- **как работает:** `revalidate(intent, candidate, checkpoint)` пере-резолвит кандидата против LIVE-стора, прогоняет тот же gate-stack (`_policy_decision` + `readiness_state`), сравнивает с baseline вызывающего; `code=='POLICY_CHANGED'` тогда и только тогда, когда живое решение СТРОЖЕ (`_DEC_RANK` вырос ИЛИ был open_now, стал не-open). Возвращает `{checkpoint, decision, readiness, disclosure, allocation_action, code, reason}`. `#1 slate`/`#2 send` были ранее (retrieval + send boundary); `#3 profile_open`/`#4 accept` — здесь; `#5/#6` отдают решение (disclosure-ladder), но enforcement чата/раскрытия — в buddy/profile (cross-service); `#7 state_change` — синхронная перечитка стора (event-bus авто-ре-эвал = blocked_infra). Эндпоинт `POST /api/agent/revalidate`.
- **ключевые решения:** read-only, тот же gate-stack (без дублирования логики); POLICY_CHANGED строго монотонен (только ужесточение) — детерминированно.
- **тесты:** `C8-REVAL` (clean → code OK; кандидат, которого live-стор теперь блокирует → POLICY_CHANGED + decision BLOCK).
- **статус:** done (#5/#6 partial cross-service; #7 без event-bus).

#### §8.2 Send-boundary re-gate (`_negotiate_precheck`) — NEG-регрессия
- **что требует спека:** никакого proposal без ре-проверки eligibility + receiving-policy непосредственно перед отправкой; `/api/agent/negotiate` принимает клиентские кандидаты verbatim.
- **что построено:** `_negotiate_precheck` (app.py:1661), вызывается из `negotiate_candidates` (app.py:1832).
- **как работает:** каждый клиентский кандидат пере-резолвится против LIVE-стора, прогоняется через `_hard_gates` (при провале → `code:"POLICY_CHANGED"`, decided без отправки), `_cross_purpose_blocked`, pair-cooldown, `_outreach_ok` (tier/consent), `readiness_state`, `_receiving_send_gate`, `_time_feasible`; параллельная волна кэпится из config (default 2, urgent 3, broadConsent поднимает до 3). Возвращает `(to_send, decided)`.
- **ключевые решения:** never-trust-caller (re-resolve против live-стора); cap — config-derived (`outreach.default_parallel_proposals`), не хардкод; агент рассуждает по LIVE-профилю (merge interests/vibe/open/dealBreakers из стора).
- **тесты:** `NEG1` (busy → никогда не получает proposal), `NEG2` (cap=2 из config, A3 queued), `NEG3` (urgent → cap 3), `NEG4` (open_now-но-ineligible двусторонний block дропается на send-границе).
- **статус:** done.

#### §8.3 Purpose-bound ProfileView + evaluate_policy facade
- **что требует спека:** контекстные профили с purpose binding (поля видны только релевантному контексту); единый типизированный policy-verdict.
- **что построено:** `_stamp_contracts` (app.py:1329) навешивает `profile_view` через `kc.build_profile_view` (context-allowlist); `evaluate_policy` (app.py:800) — унифицированный фасад (§23.4.2).
- **как работает:** `evaluate_policy(intent, c, gate_ctx)` прогоняет весь стек по порядку (`_hard_gates → cross-purpose → _policy_decision → disclosure clamp`) и возвращает один объект `{decision, reason, eligible, gate_reason, cross_purpose_blocked, disclosure, policy_version:"policy-2.0.0"}`, воспроизводя per-gate verdict byte-for-byte без нового поведения. `build_profile_view` проецирует карточку по `DOMAIN_TO_CONTEXT`, отсекая поля вне allow-list контекста (datingOk не попадёт в friendship-view).
- **ключевые решения:** фасад НЕ добавляет поведения (только унифицирует surface); проекция валидируется схемой-зеркалом.
- **тесты:** `CP9-EVAL-POLICY` (dating no-opt-in → BLOCK; clean совпадает с `_policy_decision`), `CP9-SCHEMA` (поле вне context-allowlist ловится).
- **статус:** done.

#### §8.4 География и время
- **что требует спека:** home/work — никогда не точка discovery; slot-feasibility с travel-buffer; exact place только после взаимного согласия; H3-cell/район.
- **что построено:** `_PRECISE_LOCATION_KEYS`-скраб в `_stamp_contracts` (app.py:1353), `_time_feasible` (app.py:1753), `_revalidate_disclosure` (app.py:1770), `_to_utc_min` (app.py:1745).
- **как работает:** из каждой возвращаемой карточки удаляются точные ключи (home/work/address/exact_lat/…) — no-op сегодня (фикстуры их не несут), жёсткий барьер на будущее. `_time_feasible` absent-permissive: гейтит только при окнах с ОБЕИХ сторон, UTC-нормализуя по `tz_offset_min`, требуя `overlap ≥ min_duration + travel_buffer`. `_revalidate_disclosure` отдаёт `exact_place_ok=True` только при `allowed=='full'` И существовании mutual-accept Match Capsule (взаимное согласие), клампится `receiving.disclosure_stage` кандидата.
- **ключевые решения:** retrieval работает только с грубыми `km`/coarse-coord → GEO_BANDS; DST-таблицы/travel-routing и H3-cells = blocked_infra (нет библиотек в stdlib); disclosure-ladder завязан на реальный mutual-accept.
- **тесты:** `C8-TIME` (absent → feasible; disjoint окна → не feasible), `C8-REVEAL` (exact place заблокирован до mutual Match Capsule), `C8-SCRUB` (home/work/exact-coords не выживают на карточке).
- **статус:** done (interval-algebra/DST/travel-mode и H3 — partial/blocked_infra).

---

Раздел §9 распадается на два слоя. Вся собственно **математика** (§9.1–9.4, §9.7) реализована ТОЧНО внутри sha-пиннутого `services/matching/core_v2.py` (движок не трогали — byte-identity сохранена). На orchestration-слое `services/matching/app.py` добавлены только **read-only обвязки**: CI-валидаторы конфига (§9.5) и производный ярлык решения (§9.6). Все модули keyless/LLM-free, детерминированы (double-run C24/PARITY), ничего не задеплоено — всё локально. Ниже — поподпунктно.

Сквозные факты: `core_v2.py` + `Kleal_Matching_Core_Config_v2.yaml` sha-пиннуты и не изменялись; веса живут ТОЛЬКО в YAML (в коде — лишь observed-value anchors `SEM_VALUE`/`GEO_BANDS`, не веса); person-slate byte-identical; ни в одном модуле §9 нет `llm_complete`/model-вызовов; порядок slate детерминирован (C24 «identical inputs replay to identical slate»).

#### §9.1 Четыре состояния признака (known_match / known_mismatch / unknown / not_applicable)

- **что требует спека:** каждый признак — одно из 4 состояний; `unknown` понижает coverage, `not_applicable` исключается из знаменателя, разреженный профиль не должен обгонять заполненный.
- **что построено:** `core_v2.build_features` (core_v2.py:199) размечает 7 групп в `{group: (state, value, detail)}`; потребляется в `core_v2.directional_score` (core_v2.py:327). Константы состояний — `K_MATCH/K_MISM/UNKNOWN/NA` (core_v2.py:167).
- **как работает:** для 7 evidence-групп (semantic_activity, time_feasibility, location_feasibility, mode_format, directed_preferences, social_context, domain_constraints) билдер даёт состояние + значение [0,1] + человекочитаемую деталь. В скорере: `NA` → `continue` до прибавления веса к `tw` (полностью вне знаменателя, core_v2.py:337-338); `UNKNOWN` → в знаменатель `tw` попадает, в числитель идёт `w*prior`, но НЕ увеличивает `kw` (coverage, core_v2.py:340-342); известное — `acc += w*v`, `kw += w`.
- **ключевые решения:** детерминизм (никакой случайности); честность — `unknown` это не «открытость», а понижение coverage, поэтому онлайн-интенты делают геогруппу `NA` (исключают), а не молчаливым матчем.
- **тесты:** `C1a–C1e` (оба кандидата всплывают, полный профиль обгоняет разреженный по lcb, у разреженного ниже coverage + список unknown, разреженный НЕ помечен especially_close, порядок slate Full→Sparse); `C9-NA-EXCLUDED`.
- **статус:** done (в core_v2).

#### §9.2 Нормализация наблюдения (unknown→prior, NA→вес 0, всё в [0,1])

- **что требует спека:** привести наблюдение к [0,1]; `adjusted = confidence_k·observed + (1−confidence_k)·prior`.
- **что построено:** нормализация внутри `core_v2.directional_score` (core_v2.py:340-345); priors берутся из config (`feature_groups[k].unknown_prior`).
- **как работает:** `unknown → prior`, `NA → вес 0`, известное значение входит СЫРЫМ (`acc += w*float(v)`, core_v2.py:344). Формула confidence-blend свёрнута к `confidence_k = 1.0` — per-observation confidence не моделируется, т.к. в данных нет сигнала достоверности.
- **ключевые решения:** config-derived priors (не хардкод); упрощение confidence_k=1.0 — сознательное, движок sha-запечатан и данных confidence нет.
- **тесты:** `C9-FORMULA` (явно проверяет «known value enters RAW, §9.2 conf=1»).
- **статус:** partial — точно, кроме confidence-blend → **blocked_sha_pinned** (запечатанный движок + нет данных confidence).

#### §9.3 R_mean / Coverage / R_lcb

- **что требует спека:** `R_mean = Σ(w·adj)/Σw`, `Coverage = Σ(w·known)/Σw`, `R_lcb = clamp(R_mean − λ_domain·(1−Coverage), 0, 1)`.
- **что построено:** `core_v2.directional_score` (core_v2.py:327-350) → возвращает `{mean, coverage, lcb, unknowns}`.
- **как работает:** один проход по `FEATURE_KEYS`, `tw`=сумма активных весов (без NA), `kw`=сумма весов known, `acc`=взвешенная сумма adjusted-значений. `mean=acc/tw`, `cov=kw/tw`, `lcb=max(0,min(1, mean − lam*(1−cov)))` (core_v2.py:348-349); `lam` = `dom_cfg["uncertainty_lambda"]` из config (для dating выше). Все выходы округлены до 4 знаков; `tw<=0` → нулевой результат.
- **ключевые решения:** λ config-derived per-domain; lcb — консервативная нижняя граница (низкое покрытие → штраф), чтобы разреженный кандидат не выигрывал.
- **тесты:** `C9-FORMULA` пересчитывает mean/cov/lcb вручную и сверяет байт-в-байт; `C1` (lcb-ранжирование).
- **статус:** done (в core_v2).

#### §9.4 Направленное + двустороннее (reciprocal), НЕ вероятность принятия

- **что требует спека:** `R_A→B` и `R_B→A` раздельно; `R_reciprocal = 0.70·min + 0.30·mean`; это НЕ P(accept).
- **что построено:** `core_v2.reciprocal_score(a, b)` (core_v2.py:352-355); обратная сторона строится через `core_v2.reverse_features` (core_v2.py:315) + `_profile_as_candidate` (core_v2.py:310).
- **как работает:** A→B и B→A считаются отдельными вызовами `directional_score`; reciprocal берёт `lo=min(lcb)`, `hi=max(lcb)` и даёт `round(0.7*lo + 0.3*(lo+hi)/2, 4)`, штрафуя односторонние пары. Разреженные данные B → низкое обратное покрытие → консервативный reciprocal (спека §10: unknown ≠ openness).
- **ключевые решения:** работает поверх консервативных `lcb`, а не сырых mean; инвариант «не вероятность» — `P_accept/P_response/P_completion` нигде не вычисляются.
- **тесты:** `C9-RECIP` (`0.7*0.6 + 0.3*(0.6+0.9)/2`, границы [0,1]); `C9-NO-PACCEPT` (ни на одной карте нет P_accept/P_response/P_completion/acceptance_probability).
- **статус:** done (в core_v2); введение вероятностей — **blocked_calibration**.

#### §9.5 Канонические веса + CI-валидаторы конфига

- **что требует спека:** веса каноничны и живут в config; CI должен ловить рассогласования (уникальность evidence_id, совместимость версий, диапазоны).
- **что построено:** boot-валидатор `core_v2.load_config` (core_v2.py:100-136) + добавленный read-only CI `app._validate_math_config` (app.py:846-885); поверхность — `GET /api/agent/weights` → поле `config_ci` (app.py:2302-2304).
- **как работает:** `load_config` при загрузке проверяет sha-пин, `config_version`, каждый `unknown_prior∈[0,1]`, для каждого домена — отсутствие неизвестных feature keys и сумму 7 весов = 1.0 (±1e-6), диапазоны λ/floors; иначе `ConfigError` → откат на legacy-скорер. `_validate_math_config` добавляет то, чего `load_config` не делает: (a) уникальность `evidence_id` внутри feature groups (guard активен — сегодня 0 ids); (b) совместимость MAJOR-версий config↔policy↔engine + `schema_version` в allowlist `("1.0",)`; (c) диапазоны band-cut `min_lcb/min_coverage/max_coverage∈[0,1]`; плюс НЕмутирующие эхо-проверки весов и priors. Возвращает health-dict `{ok, checks, errors, ...}`, НИКОГДА не мутирует cfg и не переписывает `_sha256`, никогда не бросает.
- **ключевые решения:** веса только в YAML (в коде — anchors, не веса); валидатор строго read-only, чтобы sha-пин держался; config-derived allowlist.
- **тесты:** `C9-CI-OK` (зелёный на пиннутом config), `C9-CI-PURE` (не мутирует, sha цел), `C9-CI-VER` (MAJOR-mismatch ловится), `C9-CI-SCHEMA` (schema вне allowlist), `C9-CI-BAND` (band-cut вне [0,1]), `C9-CI-EVID` (дубль evidence_id); `V1` (sha mismatch → reject), `V2` (битая сумма весов → reject).
- **статус:** done — веса-в-config, load_config-проверки и 6 CI-проверок; частично: band-cut CI дублирует статически `config/schema.json`.

#### §9.6 Пороги решений пилота → read-only ярлык `decision_class`

- **что требует спека:** 5-way таксономия решения по кандидату (strong / usable / discovery / clarification / no-outreach) на порогах пилота.
- **что построено:** `app._decision_class(card)` (app.py:821-844); привязка на slate-пути (app.py:2243-2244) и в `explain_match` (app.py:1305); плюс `probe_unknowns` (top-1..3 unknown по весу, app.py:2245-2246); список классов в `/api/agent/weights.decision_classes` (app.py:2300).
- **как работает:** тотальная функция, все чтения через `.get()`. Ярлык ПРОИЗВОДНЫЙ от уже проставленных движком решений `{policy, tier, band, can_outreach, why_no_outreach}` — НИЧЕГО не перепороговывает (флэтовые 0.72/0.58/0.45 из спеки иллюстративны; реальные per-domain floors уже свёрнуты в config → в `can_outreach`/`band`). Приоритет: REVIEW → `no_personal_outreach`; `can_outreach`+T0/T1+especially_close → `strong_personal_candidate`; прочий `can_outreach` → `usable_personal_candidate` (вкл. T2+consent); «broad consent» в why → `no_personal_outreach` (T2 без согласия — НЕ discovery); T3/T4 или «discovery only»/«below outreach floor» → `discovery_only`; `needs_clarification` → `clarification`; иначе → `no_personal_outreach`. Аддитивно — band/tier/lcb/can_outreach и порядок slate остаются byte-identical.
- **ключевые решения:** read-only производность (не дублирует пороги), deny-safe fallthrough для разреженной slate-карты без `why_no_outreach`.
- **тесты:** `C9-DCLASS-STRONG/USABLE/T2NOCONSENT/DISCOVERY/REVIEW/CLARIFY` (6 приоритетных кейсов), `C9-DCLASS-TOTAL` (каждая slate+explain карта несёт класс из 5-set), `C9-NO-PACCEPT`.
- **статус:** done в §9; partial: на slate-пути консервативен (без `why_no_outreach` падает в `no_personal_outreach`; полная точность в `explain`).

#### §9.7 Что показывается пользователю (band, не percent)

- **что требует спека:** наружу — только качественные band'ы по (lcb, coverage), никаких «92% совместимости».
- **что построено:** `core_v2.assign_band(lcb, cov, bands)` (core_v2.py:470-475) + `BAND_LABELS`/`BAND_RANK` (core_v2.py:462-468); band-cuts берутся из config `user_facing_bands`.
- **как работает:** кандидат размещается в especially_close/strong_option/broader_option по порогам `min_lcb`+`min_coverage`, иначе `needs_clarification`. На карту идёт `band`/`band_en`, а не число; сортировка slate — по `BAND_RANK`, затем readiness/reciprocal/lcb/coverage/name (app.py:2264). Фикс percent→band уже отгружен (commit fcdc31b).
- **ключевые решения:** config-derived band-cuts; никакого сырого percent наружу (privacy/анти-misrepresentation инвариант).
- **тесты:** `CP6-BAND` (§23.2.10 — карта несёт качественный band, ни `compatibility_percent`/`match_percent`/`compatibility`); `C1d` (разреженный ≠ especially_close).
- **статус:** done (в core_v2).

#### Итоговый статус раздела

- **done (core_v2, sha-пиннут):** §9.1 состояния, §9.3 mean/cov/lcb, §9.4 reciprocal, §9.7 band — точная реализация формул.
- **done (обвязка в §9, app.py):** §9.5 CI-валидатор (evidence_id-uniqueness + version-compat + band-cut) поверх load_config; §9.6 decision_class 5-way + probe_unknowns; math-инвариантные тесты.
- **partial:** §9.6 на slate-пути консервативен; §9.5 band-cut CI дублирует статически `config/schema.json`.
- **blocked_sha_pinned:** §9.2 `confidence_k`-blend (свёрнут к 1.0).
- **blocked_calibration:** §9.4 `P_accept/P_response/P_completion` (сознательно absent-by-design).
- **Тесты §9:** `services/matching/test_core_v2.py`, блок `C9-*` (~17 проверок: C9-FORMULA, C9-NA-EXCLUDED, C9-RECIP, C9-CI-OK/PURE/VER/SCHEMA/BAND/EVID, C9-DCLASS-STRONG/USABLE/T2NOCONSENT/DISCOVERY/REVIEW/CLARIFY/TOTAL, C9-NO-PACCEPT) + смежные C1a–e, V1, V2, CP6-BAND.
- Документация: `docs/RELEVANCE_MATH.md` (формула-за-формулой сверка).

---

## §10 — Reciprocity / Readiness / вероятность результата · §11 — Allocation / Fairness / рыночная ликвидность

Общая дисциплина по обоим разделам: новые модули `shared/kleal_completion.py` и `shared/kleal_ml_boundary.py` — **keyless / LLM-free** (ни одного обращения к `llm_complete`, ни одного model-URL). Ядро ранжирования (`core_v2.py`) и его config **sha-пиннуты и не тронуты** — весь §10/§11-код живёт на orchestration-слое (`services/matching/app.py`) как read-only / post-relevance надстройка. Person-slate остаётся **byte-identical** при пилотных дефолтах; поведение **детерминировано** (двойной прогон даёт тот же слейт). Всё локально, ничего не задеплоено.

---

# §10 — Reciprocity, readiness, completion

#### §10 intro: relevance ⟂ readiness (никогда не суммируются)

- **Что требует спека:** релевантность («подходит ли кандидат задаче») и readiness («готов ли человек получать предложение сейчас») — ортогональны, не складываются в один балл.
- **Что построено:** реализовано в sha-пиннутом ядре (`core_v2.search` / `directional_score` / `readiness_state`); orchestration только объясняет. Документировано в `docs/READINESS_COMPLETION.md`.
- **Как работает:** readiness входит в решение двумя раздельными путями — (1) как **гейт** (`can_outreach` требует `open_now`, тот же гейт на send-границе) и (2) как **отдельный ключ сортировки** `READINESS_RANK` в кортеже `(BAND_RANK, READINESS_RANK, −reciprocal, −lcb, −coverage, name)`, но **не как слагаемое `lcb`**. Reciprocity `0.7·min+0.3·mean` — это relevance-величина (§9.4), не readiness.
- **Ключевые решения:** детерминизм — фиксированный tuple-sort; инвариант «readiness не подмешивается в lcb».
- **Тесты:** RCV5 (busy виден), RCV9 (порядок), R1-7, PARITY.
- **Статус:** done_core_v2.

#### §10.1 — шесть состояний receiving-readiness + read-only объяснение

- **Что требует спека:** ровно шесть состояний готовности принимать предложения, domain-dependent; только одно разрешает personal outreach.
- **Что построено:** эмиссия — `core_v2.readiness_state` (пиннут); объяснение — словарь `READINESS_EXPLAIN` в `shared/kleal_completion.py`.
- **Как работает:** шесть состояний `open_now / open_later / passive_discovery / busy / paused / unknown`. `READINESS_EXPLAIN` для каждого несёт `meaning_en`, `outreach_allowed` (True только у `open_now`) и `domain_dependent`. Домен-зависимость: через `receiving.allowed_domains` человек может быть `open_now` к language-practice, но `passive_discovery` к dating. Стемпится на карточку как `readiness_explain` (`app.py:1352`, `app.py:2261`), список видно в `GET /api/agent/weights.readiness_states` (`app.py:2305`).
- **Ключевые решения:** модуль **только объясняет, не пересчитывает** readiness (единственный источник истины — пиннутое ядро); keyless.
- **Тесты:** `C10-READINESS` (все шесть объяснены; passive_discovery/open_later/busy/paused/unknown запрещают outreach), `C10-INT` (каждая карточка слейта несёт `readiness_explain`).
- **Статус:** done_core_v2 (эмиссия) + done (объяснение).

#### §10.2 — completion factors: прозрачные сигналы, НЕ социальный рейтинг

- **Что требует спека:** completion-готовность как набор **прозрачных именованных операционных сигналов**, а не непрозрачный «балл человека»; safety/sensitive/single-review не участвуют.
- **Что построено:** `completion_factors(candidate, intent, now_ts, received_24h)` в `shared/kleal_completion.py` (+ хелпер `_sig`, константа `EXCLUDES`, `MAX_PENDING=6`).
- **Как работает:** возвращает dict `{signals[], not_collected, excludes, aggregate_score: None, note}`. Читает **только** `lastActiveDays` (≤3 → `availability_fresh` fresh/stale/unknown), `pending` vs MAX_PENDING (`capacity_headroom` has_headroom/near/at_capacity + `active_plans`), `receiving.proposal_budget` (`proposal_budget`), и `formats` для online-интента (`technical_compat` compatible/incompatible/**unknown**/not_applicable). Каждый сигнал `transparent:true`. **`aggregate_score` жёстко `None`** — агрегата нет by design. Из 7 спека-сигналов данные есть у 3; остальные честно в `not_collected`: `response_latency` (молчание/`expired_no_response` остаётся НЕЙТРАЛЬНЫМ, не читается как latency), `recent_no_show` (decline-cooldown — это гейт, не рейтинг), `min_duration_capability` (intent-side only), `host_venue_room` (post-pilot). Стемпится на карточки: `app.py:1350`, `app.py:2260`.
- **Ключевые решения:** инвариант «не непрозрачный рейтинг» реализован **by construction** — `EXCLUDES` перечисляет РЕАЛЬНЫЕ имена запрещённых полей (`safetyFlags/sensitivity/accountStatus/suspended`, `blocksMe/declinedOwnerDaysAgo`, `slots/visibility`), и ни одно их значение не попадает в signals; online-совместимость при отсутствии `formats` = **unknown**, а не «предполагаем совместимо»; read-only, никогда не кормит скоринг; keyless.
- **Тесты:** `C10-CF-NOAGG` (нет aggregate score), `C10-CF-EXCLUDES` (не течёт safety/sensitive/single-review value), `C10-CF-SIGNALS` (сигналы присутствуют, transparent:true), `C10-CF-NOTCOLLECTED` (latency/no_show честно not_collected, не из молчания), `C10-CF-TECH` (online без formats → unknown), `C10-INT` (`aggregate_score is None` на каждой карточке).
- **Статус:** done (3 сигнала) / partial (4 сигнала ждут сбора данных) / pilot_disabled (host/venue/room).

#### §10.3 — граница перехода к ML (декларативный манифест, в пилоте ML не запускается)

- **Что требует спека:** объявить 6-слойный ML-роадмап; калиброванные вероятности отсутствуют пока нет данных+версии модели; hard gates / privacy / purpose-binding / block / capacity / disclosure остаются детерминированной политикой и не отдаются модели.
- **Что построено:** `ML_BOUNDARY` + `assert_no_model_in_gates()` + типизированные стабы `feature_vector / predict_response / predict_acceptance / predict_completion / model_version` в `shared/kleal_ml_boundary.py`.
- **Как работает:** `roadmap` — 6 слоёв: L1 intent-classification, L2 retrieval-recall = `future`; L3 P_response, L4 P_accept (по направлениям+доменам), L5 P_completion, L6 LTR+off-policy-eval = `blocked_calibration`. `probabilities` жёстко `{P_response/P_accept/P_completion: "absent_by_design"}` — **никогда не стабятся в placeholder-число** (стабы возвращают сентинел `absent_by_design` и `probability:None`, `model_version:absent_by_design`; `model_version()` → `{scoring:"rule_based_deterministic", ml:"absent_by_design"}`). `deterministic_policy` перечисляет 6 политик с указанием `where` (реальные функции: `_hard_gates`, `_cross_purpose_blocked`, `build_proposal` clamp и т.д.), все `model_driven:False`; `assert_no_model_in_gates()` возвращает пустой список = инвариант держится. Видно в `weights.ml_boundary` (`app.py:2306`).
- **Ключевые решения:** **absent_by_design вместо фабрикации** (нет случайных float’ов вместо калиброванной модели); инвариант **no_model_in_gates** проверяется рантайм-статикой над исходниками; keyless, no model access.
- **Тесты:** `C10-ML` (6 слоёв, статусы только future/blocked_calibration), `C10-ML-PROB` (P_* буквально absent_by_design, не число), `C10-ML-DET` (политики покрывают gates/privacy/purpose/block/capacity/disclosure, ни одна не model-driven), `C10-NOMODEL` (в исходниках гейт/policy/readiness/tier-функций нет `llm_complete`/model-вызова).
- **Статус:** done (декларация + инвариант) / blocked_calibration (4 калиброванных слоя).

---

# §11 — Allocation, fairness, market liquidity

Весь §11 реализован в `services/matching/app.py` как **post-relevance / post-policy** слой поверх пиннутого `core_v2.search`. Документация — `docs/ALLOCATION.md`.

#### Несущая гарантия: slate byte-identical при пилотных дефолтах

- **Что требует спека:** allocation решает кому/сколько показов после eligibility+relevance и **никогда не меняет смысл релевантности пары** (§11 intro).
- **Что построено:** `ALLOCATION_CONFIG` (пилотные дефолты) + `_alloc_cfg(ctx)` + `_alloc_is_default(cfg)` + `_allocate(slate, ctx, pool)` (`app.py:1049-1124`).
- **Как работает:** `_allocate` вызывается в `match_candidates` (`app.py:1284`) поверх готового слейта. Все дефолты — no-op (cap = 1e9, quota = 0, guard off, cooldown 0). `_alloc_is_default(cfg)` при точном совпадении с дефолтом заставляет `_allocate` **вернуть тот же объект списка** → byte-identity. Механизмы кусаются только при явном `ctx['allocation']` override — **через ctx, не через sha-пиннутый конфиг**, поэтому sha ядра не меняется. `_allocate` читает exposure/outcomes/area в ЛОКАЛЬНУЮ логику и **никогда не пишет обратно** в lcb/reciprocal/mean/coverage/score.
- **Ключевые решения:** override через ctx (как §7 retrieval-budget), а не через config → sha сохранён; детерминизм; никакого feedback в релевантность.
- **Тесты:** `C11-ALLOC-NOOP` (дефолт → byte-identical), `C11-ALLOC-NOOP-BRANCH` (инертный non-default cap=1000 прогоняет все ветки, но ничего не меняет — per-branch dormancy), `C11-ALLOC-BITE` (тесная cap режет только over-exposed, порядок выживших не меняется), `C11-PAY-ALLOC`, RCV5/RCV9/R1-7/PARITY зелёные.
- **Статус:** done_core_v2 (базовый слейт) + done (allocation-обёртка).

#### §11.1 — девять механизмов ликвидности/справедливости

- **Что требует спека:** 9 механизмов: proposal-fatigue caps, per-pair cooldown, diversity slate, per-user exposure caps, popularity-concentration guard, защита самых отзывчивых, exploration quota, reservation capacity, city/area supply balancing.
- **Что построено:** exposure-лог `_log_exposure` / `_exposures_in_window` / `_responsive_counts` (`app.py:316-338`); `_within_band_demote` (`app.py:1071`); ветки в `_allocate`; pair-cooldown на send-границе (`app.py:1696-1699`).
- **Как работает по механизмам:**
  - **proposal-fatigue caps** — `readiness=busy` при received_24h≥cap (done_core_v2).
  - **per-user exposure caps** — `_log_exposure(name)` пишет per-name impression-лог (7-дневное окно, как `_proposals`), в `_allocate` `exposure_cap_per_window` удаляет over-exposed tail сохраняя порядок (done; dormant).
  - **popularity-concentration guard + защита отзывчивых** — `_within_band_demote`: **demote-only, ВНУТРИ band, переприменяя FROZEN sort key** (`READINESS_RANK, −reciprocal, −lcb, −coverage, name`), чтобы open_now/reciprocal precedence нельзя было нарушить. Popular = exposure > `popularity_min_exposure`; responsive = exposure > `responsive_max_exposure` И есть accepted/completed outcomes (`_responsive_counts`). **Никогда не boost** — boost был бы reputation-score-в-ранжирование, что §11 запрещает (done; dormant).
  - **exploration quota** — `_allocate` append из pool отсортированного по наименьшей exposure; quota 0 → никого; **никогда не фабрикует при пустом пуле** (done; dormant).
  - **city/area supply balancing** — `supply_max_per_area` роняет surplus по area (pilot_disabled/partial; `area` разрежён в демо).
  - **per-pair cooldown** — declined-cooldown (hard gate) + общий `pair_cooldown_days` на send-границе: если пара уже получала предложение в окне → `readiness=pair_cooldown`, `agree=False` (done/partial; 0 = off).
  - **diversity slate** — `core_v2._slate` по одной оси (broad-interest bucket ≤3); source-type/tier оси — dormant (done_core_v2/partial).
  - **reservation capacity** — pilot_disabled (нужны group/reservation-сущности §15).
- **Ключевые решения:** exposure пишется на **send-границе** (`negotiate_candidates`, рядом с `_log_proposal`, `app.py:1838`), НЕ в `match_candidates` → match остаётся чистым детерминированным replay; demote-only чтобы не превратить репутацию в ранжирующий boost.
- **Тесты:** `C11-ALLOC-BITE` (exposure cap), `C11-ALLOC-EXPLORE-OFF` (quota 0 → нет карточек), `C11-ALLOC-NOOP-BRANCH` (все ветки инертны).
- **Статус:** done_core_v2 4 · done 1 · partial 5 · pilot_disabled 7.

#### §11.2 — порядок rerank (6 шагов) + allocation_trace

- **Что требует спека:** зафиксированный порядок: (1) убрать block/expired/capacity, (2) sort по reciprocity+readiness, (3) diversity, (4) exposure/fatigue caps, (5) exploration-позиция, (6) propensity + причины allocation.
- **Что построено:** шаги 1-3 в пиннутом ядре; 4-5 в `_allocate`; шаг 6 — `_stamp_allocation_trace(slate, ctx, cfg)` (`app.py:1126`), вызывается в `match_candidates` (`app.py:1288`).
- **Как работает:** шаг 1 — block (`_policy_decision`), expired (`kc.is_expired`), T5 (движок); **capacity-exceeded оставлен как видимый `readiness=busy` (RCV5), а не буквально удалён** — осознанная byte-identity интерпретация. `_stamp_allocation_trace` стемпит на каждую карточку `allocation_trace` = `{position, bucket, tier, readiness_class, exposure_count, fatigue_state, diversity_bucket, exploration, propensity:None, propensity_status:"absent_by_design", allocation_reasons[]}` — **аддитивно, ничего не reorder/drop/add**. `allocation_reasons` собирается из policy=REVIEW / отсутствия can_outreach / fallback / exploration.
- **Ключевые решения:** **propensity absent_by_design** — нет acceptance-probability прокси (§9.4/§10.3); `exposure_count`/`fatigue_state` легитимно ВАРЬИРУЮТСЯ между двумя одинаковыми вызовами (логи растут), поэтому любой full-card/replay diff обязан ИСКЛЮЧАТЬ `allocation_trace` — это задокументировано в самой docstring.
- **Тесты:** `C11-ALLOC-TRACE` (каждая карточка несёт trace: position + propensity absent_by_design + exploration False), `C11-ALLOC-NOPROP-NOPAY` (в trace ноль payment-ключей и ноль acceptance-probability прокси).
- **Статус:** done (шаги 2-6) / partial (шаг 1 capacity как busy).

#### §11.3 — инвариант монетизации (payment_status запрещён как feature)

- **Что требует спека:** `payment_status` не может быть relevance/reciprocity/safety/allocation-фичей; подписка меняет лимиты/инструменты, но не порядок.
- **Что построено:** `_payment_invariant(cfg)` → `PAYMENT_INVARIANT` (`app.py:557-564`), читает пиннутый ключ `currency_or_paid_priority` из config.
- **Как работает:** возвращает `{ranking_boost_allowed, safety_priority_affected_by_payment, enforced:True, ok, note}`; `ok = (not boost) and (not safety)`. В движке и в `_allocate` **нет ни одного платёжного входа** (grep пуст). Отдаётся в ответах (`app.py:2282`, `2294`) и в weights.
- **Ключевые решения:** значение config-derived (читает уже-пиннутый ключ, config-edit/sha-change не нужен); при нарушении surfaces `ok=False`, а не молча honours.
- **Тесты:** `C11-PAY-ALLOC` — внедрённые `payment_status="premium"` / `subscription="paid"` не меняют ни порядок/членство слейта, ни bands, ни trace.
- **Статус:** done_core_v2.

---

### Итоговый статус
- **§10:** done_core_v2 8 · done 6 · partial 5 · pilot_disabled 1 · blocked_calibration 4. Тесты `C10-*` (11 проверок).
- **§11:** done_core_v2 4 · done 1 · partial 5 · pilot_disabled 7 · blocked_calibration 1 (propensity). Тесты `C11-*` (7 проверок).

### Файлы (абсолютные пути)
- `C:\Projects\.dating\shared\kleal_completion.py` — `completion_factors`, `READINESS_EXPLAIN`, `EXCLUDES`, `_sig`
- `C:\Projects\.dating\shared\kleal_ml_boundary.py` — `ML_BOUNDARY`, `assert_no_model_in_gates`, `feature_vector`/`predict_*`/`model_version`
- `C:\Projects\.dating\services\matching\app.py` — `_log_exposure`/`_exposures_in_window`/`_responsive_counts` (316-338), `_payment_invariant`/`PAYMENT_INVARIANT` (557-564), `ALLOCATION_CONFIG`/`_alloc_cfg`/`_alloc_is_default`/`_within_band_demote`/`_allocate`/`_stamp_allocation_trace` (1049-1150), pair-cooldown send-boundary (1696-1699), exposure-log send-boundary (1838), стемпинг completion/readiness (1350-1352, 2260-2261), weights (2305-2306)
- `C:\Projects\.dating\services\matching\test_core_v2.py` — `C10-*` (~985-1040), `C11-*` (~1042-1097)
- `C:\Projects\.dating\docs\READINESS_COMPLETION.md`, `C:\Projects\.dating\docs\ALLOCATION.md`

---

# §12 Controlled expansion + §13 Agent protocol — функциональный рекап

Всё описанное — локально, ничего не задеплоено. Ядро скоринга (`core_v2.py` + `config/`) sha-pinned и не тронуто; вся работа §12/§13 — **аддитивная надстройка** над ним (`services/matching/app.py`) плюс новый keyless/LLM-free модуль `shared/kleal_protocol.py`. Инвариант «person-slate byte-identical» соблюдён: precheck-карточки получают только НОВЫЕ ключи, порядок/членство/agree/reason/readiness/reply не трогаются (NEG1-4 / C4-SEND1 остаются byte-identical). Детерминизм: `kleal_protocol` — pure, LLM-вызов в пайплайне ровно один (`negotiate_one`) и он лишь ФОРМУЛИРУЕТ, а accept/reject-бит выводится детерминированно.

---

## §12 — Controlled expansion (лестница расширения, never-dead-end, saved search)

Файлы: `services/matching/app.py` (`expansion_ladder`, `_expand_fallback`, `_expand_stepwise`, `expand_one_axis`, `_tag_ladder`, `_ladder_step_for_card`, `_online_fallback`, saved-search); `docs/EXPANSION.md`. Тесты: `C12-*` (10 проверок) + `CP8-STEPWISE/EXPAND`.

#### §12.2 Лестница расширения как read-only PLAN
- **что требует спека:** упорядоченная лестница расширения, каждый шаг ослабляет ОДНУ soft-ось, cheapest-first; safety/age/consent/block/language/purpose никогда не ослабляются.
- **что построено:** константа `_LADDER` (7 шагов) + `expansion_ladder(intent, ctx)` — `services/matching/app.py:1403`; индекс `_LADDER_BY_STEP` (`:1394`).
- **как работает:** возвращает `{ladder:[...], dota_example, principles}`. Каждый шаг — `{step, axis, relaxes (одна ось), provenance_tier, outreach{mode, broad_consent_required, note}, cost_rank(==step), applicable, explanation_ru/en}`. `applicable` вычисляется из intent (шаг 2 — при `not exact` и adjacent/related-dims или `adjacentAllowed`; шаг 3 — parent при `broadAllowed`; шаг 4 — при `radiusKm`/offline; шаг 5 — при `allowOnlineFallback`/offline). Если шагу нужен broad consent, а его нет — в `outreach.note` пишется «broad consent not given — discovery only (no inbox)». Ничего не пере-скорит и не мутирует intent/slate.
- **7 шагов:** 1 exact entity/role @time+zone (T0/T1) · 2 adjacent/sibling (T2/T3, discovery+consent) · 3 parent category (T2, discovery+consent) · 4 widen time/radius · 5 change format (1:1→group / offline→online) · 6 event/room/group alternative (T4) · 7 saved search + notify.
- **ключевые решения:** план ЧЕСТНО декларирует расхождение с исполнителем — `principles.executed_fallback = "multi-axis..., tagged after the fact"`, `one_axis_per_step_in_plan=True`; `never_relaxes` = safety/age/mutual_consent/block/critical_language/purpose_isolation. Provenance-тир НЕ пере-выставляется (sha-pinned движок).
- **тесты:** `C12-LADDER-ORDER` (7 шагов, cost_rank==step по возрастанию, relaxes — строка), `C12-LADDER-CONSENT` (шаги 2/3 = discovery + broad_consent_required + note), `C12-LADDER-INVARIANTS` (`never_relaxes` набор + multi-axis executed), `C12-LADDER-STEP6` (T4 event/room/group).
- **статус:** done (план); честно partial по исполнению (шаги 3/4/5 частично, шаг 6 pilot_disabled на уровне реальных event/room).

#### §12.1 Never-dead-end fallback (двух-осевой исполнитель)
- **что требует спека:** поиск не должен упираться в тупик, пока кто-то eligible; fallback — полезный следующий шаг, не случайный человек.
- **что построено:** `_expand_fallback(intent, prof, ctx, eligible)` — `services/matching/app.py:1463`.
- **как работает:** над ТЕМ ЖЕ hard-gate-eligible пулом. Фаза 1: пере-скор с `adjacentAllowed=True, exactMatchRequired=False` и сброшенным discovery-floor (`_RELAXED_CFG`) — карточки помечаются `fallback="broader"` + note. Фаза 2 (нет топикового пересечения нигде): ближайшие доступные (не paused) люди сортируются по `open`→`km`→имя, отдаются как T4 `kind="alternative"` с `can_outreach=False`, band `needs_clarification`. Все карточки прогоняются через `_tag_ladder`.
- **ключевые решения:** `_RELAXED_CFG` зануляет ТОЛЬКО discovery-floor — веса/λ/outreach-floor/гейты нетронуты. Safety/age/consent/block/language/purpose НЕ ослабляются (fallback над тем же пулом). Alternative-карточки — не outreach (T4 никогда не в inbox).
- **тесты:** `C12-TAG` (zero-overlap карточки помечены ladder_step ∈{2,3}, `can_outreach=False`, never-dead-end сохранён).
- **статус:** done_prior (сам fallback) + done (теги).

#### §12.2 Тегирование исполненного fallback ладдер-шагом
- **что требует спека:** объяснимый компромисс — UI должен сказать, что поиск расширен, а не подсунуть случайного.
- **что построено:** `_ladder_step_for_card(card)` (`:1436`) + `_tag_ladder(cards)` (`:1450`).
- **как работает:** `_ladder_step_for_card` PURE + exception-safe (только `c.get()`): `fallback=="broader"` → 2 при tier T3 (adjacent→discovery), иначе 3 (T2 sibling/parent); `fallback=="alternative"` → 3; `kind=="alternative_solution_type"` → 6. `_tag_ladder` аддитивно ставит `ladder_step/ladder_axis/ladder_relaxes` через `setdefault`, без переупорядочивания/выбрасывания.
- **ключевые решения:** exception-safe и PURE специально — ошибка тегирования не должна регрессировать never-dead-end в пустой slate; теги — «после факта», потому что исполнитель ослабляет две оси разом (adjacent + exactness).
- **тесты:** `C12-TAG` (ladder_step проставлен).
- **статус:** done.

#### §12.1 One-axis-per-step stepwise (истинно одна ось за шаг)
- **что требует спека:** каждый шаг ослабляет РОВНО одну ось, cheapest-first, стоп на первом шаге, давшем ≥ min_cards.
- **что построено:** `_expand_stepwise(intent, prof, ctx, eligible, min_cards=1)` — `services/matching/app.py:1506`.
- **как работает:** шаги (2: `adjacentAllowed=True`), (3: +`broadAllowed=True`), (4: +`exactMatchRequired=False`) — каждый добавляет ровно одну ось поверх предыдущего; первый, давший ≥ min_cards, возвращается как `(cards, step)`, карточки помечены `fallback="broader"` + правильным `ladder_step`. Пул byte-identical, ширится только discovery-breadth.
- **ключевые решения:** в отличие от `_expand_fallback` (adjacent+exactness сразу), здесь шаг 2 ослабляет ТОЛЬКО adjacency — это spec-faithful one-axis-per-step. Над тем же hard-gate пулом (`_RELAXED_CFG` — только floor).
- **тесты:** `CP8-STEPWISE` (шаг 2 = adjacency-only, НЕ exactMatchRequired; карточки с истинным ladder_step).
- **статус:** done.

#### §21.2 Одно-осевой expand endpoint
- **что требует спека:** явно применить один заявленный axis расширения; safety/age/consent фиксированы.
- **что построено:** `expand_one_axis(body)` — `services/matching/app.py:2093` (POST `/searches/{id}/expand`).
- **как работает:** маппинг `_AXIS`: adjacent→`adjacentAllowed`, parent→`broadAllowed`, exactness→`exactMatchRequired=False`, radius→`radiusKm*2`. Возвращает `{axis, changed_keys, candidates, ladder_step, explanation}` — только один изменённый ключ.
- **ключевые решения:** никогда не ослабляет две оси разом (в отличие от `_expand_fallback`); safety/age/consent неизменны.
- **тесты:** `CP8-EXPAND` (adjacent → `changed_keys==["adjacentAllowed"]`, `ladder_step==2`, exactness не сброшена).
- **статус:** done.

#### §12.3 Пример Dota 2
- **что требует спека:** LoL-игрок не должен получить personal proposal под видом «почти Dota» без явного broad-consent.
- **что построено:** константа `_DOTA_EXAMPLE` (`:1395`), возвращается в `expansion_ladder` как `dota_example`.
- **как работает:** строки T0 (активный Dota-support, тот же server/time) · T1 (подтверждённый Dota + games receiving) · T2 (другие MOBA — «only as a broader option, never 'almost Dota'») · T4 (Dota room/watch party) · No supply (unranked? другой вечер? сохранить поиск?).
- **тесты:** `C12-DOTA` (T2 = broader-only, есть No-supply строка).
- **статус:** done (иллюстративная константа).

#### §12.2 шаг 7: saved search + notify-later
- **что требует спека:** сохранить поиск и уведомить позже; re-run read-only над текущим hard-gate пулом.
- **что построено:** `_save_search`, `_list_saved_searches`, `_check_saved_searches`, `_delete_saved_search` (+ эндпоинты `/api/agent/save_search`, `/save_search/check`, `/save_search/delete`, `/saved_searches`).
- **как работает:** persist в `SESSION[uid].saved_searches` (gitignored `kleal_store.json`, НЕ users.json); `/check` пере-запускает поиск READ-ONLY над ТЕКУЩИМ hard-gate пулом (block/pause/age/consent соблюдены, `ready` только при реальном non-fallback совпадении). Заменяет UI-заглушку `wait`.
- **ключевые решения:** «Notify later» = persist + on-demand pull-hook; реальный async-push — отдельная инфра. Стор именно session-file, не users.json.
- **тесты:** `C12-SAVED` (persist id+watching), `C12-SAVED-CHECK` (read-only re-run), `C12-SAVED-DELETE`. Плюс `C12-TAG-ONLINE` (online room = ladder_step 6/T4; «save this search» suggestion = step 7 c `action=save_search`).
- **статус:** done.

#### §12 Статус (честно из docs/EXPANSION.md)
done_prior 8 · done 8 · partial 3 (parent≠sibling тир — движок обе кладёт в T2, sha-pinned; auto time/distance — только client-override; 1:1→group §15) · pilot_disabled 2 (event/room/group как retrieved candidates §15/§16; стоит онлайн-комната).

---

## §13 — Typed agent protocol & outreach orchestration

Файлы: `shared/kleal_protocol.py` (модуль `kp`, keyless, LLM-free, детерминированный) + аддитивная проводка в `services/matching/app.py` (`_negotiate_precheck`, `negotiate_candidates`); `docs/PROTOCOL.md`. Тесты: `C13-*` (12 проверок).

#### §13.1 Девять разрешённых действий
- **что требует спека:** агент обменивается ТИПИЗИРОВАННЫМИ событиями, не свободными разговорами с сотнями LLM; ровно 9 действий.
- **что построено:** `ACTIONS`/`ALLOWED_ACTIONS`/`is_action` — `shared/kleal_protocol.py:13`.
- **как работает:** `ACTIONS = (ELIGIBILITY_PROBE, PROPOSE_CONNECTION, ASK_INFO, COUNTER_TIME, COUNTER_FORMAT, ACCEPT, DECLINE, WITHDRAW, EXPIRE)`; `is_action` — членство во frozenset. `PROTOCOL_VERSION="agent-protocol-13.0.0"`.
- **тесты:** `C13-ACTIONS` (набор ровно спековый; `is_action("ACCEPT")`, не `is_action("LIKE")`).
- **статус:** done.

#### §13.1 Классификация карточки в типизированное действие
- **что требует спека:** каждое решение пайплайна маппится в одно из 9 типизированных действий.
- **что построено:** `type_action(card, in_to_send)` — `shared/kleal_protocol.py:22`.
- **как работает:** PURE над существующими ключами. `in_to_send` → `PROPOSE_CONNECTION, passed=True`. Иначе: reason-substring «queued for the next wave» → `ELIGIBILITY_PROBE, passed=True, wave_deferred=True` (по reason, НЕ по readiness — которая остаётся open_now); `readiness=="time_infeasible"`/«feasible time slot» → `counter_hint="COUNTER_TIME"`; «proposals not accepted» → `COUNTER_FORMAT`; прочее → `ELIGIBILITY_PROBE, passed=False`.
- **ключевые решения:** wave-deferred overflow — это ПРОШЕДШИЙ probe, детектится по reason-substring, а не по readiness; чистая функция → детерминизм.
- **тесты:** `C13-TYPE` (to_send→PROPOSE; queued→passed probe; blocked→failed; time→COUNTER_TIME hint).
- **статус:** done.

#### §13.1 LLM-decision → типизированное действие
- **что требует спека:** LLM только формулирует; accept/reject/counter-бит — типизированное детерминированное решение.
- **что построено:** `map_decision_to_action(negotiate_result)` — `shared/kleal_protocol.py:45`.
- **как работает:** PURE, без модельного вызова. `agree` → `ACCEPT`; decline с ключевыми словами времени (`_COUNTER_TIME_KW`) → `COUNTER_TIME`; формата (`_COUNTER_FORMAT_KW`) → `COUNTER_FORMAT`; иначе `DECLINE`. Вход — `{agree, reply}` от `negotiate_one`.
- **ключевые решения:** типизированный бит выводится из agree + substring, а не из свободного текста LLM — replay-стабильно.
- **тесты:** `C13-MAP` (agree→ACCEPT; reschedule→COUNTER_TIME; online/voice→COUNTER_FORMAT; else→DECLINE).
- **статус:** done.

#### §13.1 Message envelope
- **что требует спека:** типизированный конверт сообщения с версиями/purpose/disclosure/audit; не пере-деривать идентификаторы.
- **что построено:** `build_envelope(...)` — `shared/kleal_protocol.py:60`; стемпится в `negotiate_candidates` (`app.py:1842`).
- **как работает:** оборачивает `kc.build_proposal`-объект: копирует его (сохраняя proposal_id/idempotency_key/payload/TTL/status), ДОБАВЛЯЕТ `protocol_version`, `action`, `versions{intent, profile_capsule(config_version), policy}`, `purpose`, `disclosure_scope` (fallback на `allowed_disclosure`), `structured_fields` (fallback на payload), стабильный `rendering_key` (`proposal.<action>`), `audit{actor, action, ts, correlation=proposal_id}`.
- **ключевые решения:** НИКОГДА не пере-деривает proposal_id/idempotency_key (идемпотентность §4.7 приходит из proposal); неизвестный action схлопывается к PROPOSE_CONNECTION.
- **тесты:** `C13-ENVELOPE` (все §13.1 поля + сохранение proposal ids).
- **статус:** done.

#### §13.2 Волны outreach + cap
- **что требует спека:** волновая рассылка (top open_now сейчас; overflow отложенно; urgent/expansion — расширенная), ограниченный параллелизм, нет массовой рассылки.
- **что построено:** `assign_wave(card, ctx)` — `shared/kleal_protocol.py:84`; cap-логика в `_negotiate_precheck` (`app.py:1668-1678, 1722-1728`).
- **как работает:** `assign_wave`: reason «queued for the next wave» → wave 2 (assignment детерминирован, async re-send = infra); `ctx.urgent`/`ctx.expansion` → wave 3; иначе wave 1. Cap в precheck из конфига (`default_parallel_proposals`=2, `urgent_same_day_parallel_proposals`=3 по `SOON_WORDS`); при `broadConsent` (не urgent) `cap=max(cap,3)` — сохраняя config-derived базу, без хардкода 2/3. Переполнение сверх cap → карточка decided с reason «queued for the next wave».
- **ключевые решения:** дефолт ≤3 одновременных personal proposal — массовая рассылка невозможна; base cap config-derived; wave 0 (показать slate) — отдельный `/match` до send-границы.
- **тесты:** `C13-WAVE` (queued→wave2, urgent/expansion→wave3, default→wave1), `C13-CAP-CONSENT` (broadConsent поднимает cap до 3 без urgent).
- **статус:** done.

#### §13.2 Аддитивный стемп action/detail/wave на precheck-карточках
- **что требует спека:** типизация не должна ломать существующий slate.
- **что построено:** цикл в конце `_negotiate_precheck` — `app.py:1738-1741`.
- **как работает:** для to_send и decided ставит `c["action"]` (строка), `c["action_detail"]` (dict от `type_action`), `c["wave"]` (от `assign_wave`) — только новые ключи.
- **ключевые решения:** byte-identity инвариант — не трогает name/agree/reason/readiness/reply, членство, порядок (NEG1-4 / C4-SEND1 остаются byte-identical). Guard'ы намеренно живут только в `negotiate_candidates`, не в precheck.
- **тесты:** `C13-STAMP` (каждая карточка несёт action+wave+action_detail; default cap всё ещё 2; to_send[0]→PROPOSE/wave1, decided[0]→ELIGIBILITY_PROBE/wave2).
- **статус:** done.

#### §13.3 Границы автономности — ENFORCED
- **что требует спека:** явный манифест can_auto/requires_consent; consent-required действия принудительно заблокированы.
- **что построено:** `AUTONOMY_BOUNDARIES` (`kp:98`) + три guard'а: `guard_no_payment_booking_venue_confirm` (`:111`), `guard_no_conflicting_plans` (`:121`), `guard_no_refusal_retry` (`:137`); проводка в `negotiate_candidates` (`app.py:1867-1872`).
- **как работает:** guard'ы pure, absent-permissive, возвращают `(ok, reason)`. Payment/booking/venue — сканит envelope + structured_fields на `_PAYMENT_BOOKING_KEYS`, при заполненном поле → `False`. Conflicting-plans — блокирует, если окно нового плана перекрывает активное (`not (nu<=pf or nf>=pu)`). Refusal-retry — `False`, если `declined_recently`. В `negotiate_candidates` при провале guard'а карточка получает `agree=False, code="NEEDS_CONSENT", action="DECLINE"`.
- **ключевые решения:** не просто декларация — принуждено: expand-hard-constraints+dating за `/confirm`; reveal-sensitive за disclosure-clamp; три оставшихся — guard'ами. Absent-permissive (defensive/latent), с POSITIVE-firing тестами. Guard'ы в `negotiate_candidates`, а не в precheck (чтобы NEG-тесты precheck остались byte-identical).
- **тесты:** `C13-GUARD-PAY` (confirm_payment/exact_venue→False, чистый envelope→True), `C13-GUARD-CONFLICT` (overlap→False, no-overlap/no-window→True), `C13-GUARD-REFUSAL` (recent refusal→False), `C13-BOUNDARIES` (requires_consent ⊇ 6 пунктов + модуль LLM-FREE: нет `import llm_client`, нет `llm_complete`).
- **статус:** done (принуждение); payment-guard честно defensive/latent (нет фикстуры с payment-полем в реальном потоке).

#### §13.1 Проводка типов в реальный send-путь
- **что построено:** в `negotiate_candidates` (`app.py:1841-1856`): состояние proposal `CREATED→SENT` (§14.1), стемп envelope с `action="PROPOSE_CONNECTION"`, после негоциации `c["action"]=map_decision_to_action(c)`; при accept — revalidate + guards + §14.3 slot-claim/dating-hold.
- **как работает:** LLM `negotiate_one` формулирует reply, но verdict детерминирован (availability + score≥45); типизированное действие выводится из результата. ACCEPT ведёт к re-gate и §14 записи под одним reentrant-локом.
- **статус:** done (типизация); ASK_INFO/EXPIRE/COUNTER_* — партиалы (типизированные ярлыки/хинты, не эмитятся как transitions).

#### §13 Статус (честно из docs/PROTOCOL.md)
done_prior 12 · done 9 (9 действий, конверт, wave+broadConsent cap, 3 guard'а, LLM-free модуль) · partial 7 (ASK_INFO/EXPIRE/COUNTER_* как ярлыки; reveal-sensitive на уровне stage+purpose; payment-guard latent) · blocked_infra 2 (async Wave-2 re-send scheduler; реальный per-message transport) · pilot_disabled 1 (group/event действия §15/§16).

---

## §14 — Транзакционные конечные автоматы и защита от гонок

Слой реализован в новом keyless / **LLM-free** модуле `shared/kleal_states.py` (импортируется как `ks`) плюс аддитивная проводка в `services/matching/app.py`. Модуль — набор **чистых функций над обычными dict**: нет часов на уровне модуля (время всегда инъектируется вызывающим), нет FS, нет доступа к `core_v2`/config, нет секретов/модели. Sha-pinned движок (`core_v2` + config) **не тронут**; person-slate остаётся **byte-identical** — все штампы (`state`/`version`/`txn`/`match_state`) добавляются как новые ключи, старые surfaced-поля (`agree`/`reason`/`readiness`/`name`/`status`) никогда не мутируются. Всё локально, ничего не задеплоено. Детерминизм подтверждён двойным прогоном; сюита `test_core_v2.py` — 219/219, из них 17 проверок `C14-*`. Документ: `docs/STATE_MACHINES.md`.

`STATES_VERSION = "states-14.0.0"`.

#### §14.1 Четыре lifecycle-автомата (`STATE_MACHINES`)

- **Что требует спека:** четыре конечных автомата — Intent / Proposal / Match / Plan — с состояниями, начальным, терминальными и легальными рёбрами.
- **Что построено:** словарь `STATE_MACHINES` в `shared/kleal_states.py` + deny-safe валидатор `machine` / `initial_state` / `is_terminal` / `can_transition` / `next_state` / `apply_transition`.
- **Как работает:** ровно 4 машины с полями `states`/`initial`/`terminal`/`transitions`/`enabled`. **intent** (7 состояний: `DRAFT→CONFIRMED→SEARCHING⇄WAITING→SATISFIED|EXPIRED|CANCELLED`), **proposal** (10: `CREATED→(RESERVED)→SENT→VIEWED→ACCEPTED|DECLINED|COUNTERED|WITHDRAWN|EXPIRED|POLICY_REVOKED`), **match** (8: `PENDING_DISCLOSURE→MUTUAL→CHAT_OPEN→PLANNING→PLANNED→COMPLETED|CANCELLED|SAFETY_CLOSED`), **plan** (8: `DRAFT→PROPOSED→PARTIALLY_CONFIRMED→CONFIRMED⇄CHANGED→…`). `can_transition(entity,frm,to)` возвращает True только для объявленного ребра; неизвестный entity/state или выход из терминала → False (**deny-safe**). `apply_transition(obj,entity,to)` — аддитивный: на легальном ребре ставит `obj['state']=to` и инкрементит `obj['version']`, на нелегальном возвращает `{ok:False, error_code:"ILLEGAL_TRANSITION"}` **без мутации объекта**; clock-free (timestamp ставит вызывающий).
- **Ключевые решения:** таблицы декларативны и deny-safe; проводка аддитивна ради byte-identity; `plan` определён для конформанса, но `enabled:False` (group/plan выключены в пилоте §1.2/§15/§16).
- **Тесты:** `C14-MACHINES`, `C14-EDGES`, `C14-APPLY`.
- **Статус:** done (Plan — pilot_disabled).

#### §13 action → proposal-ребро (`ACTION_TO_STATE` / `next_state`)

- **Что требует спека:** типизированные §13-действия должны отображаться на переходы Proposal-автомата.
- **Что построено:** словарь `ACTION_TO_STATE` + `next_state(entity,current,action)` в `shared/kleal_states.py`.
- **Как работает:** `PROPOSE_CONNECTION→SENT`, `ACCEPT→ACCEPTED`, `DECLINE→DECLINED`, `COUNTER_TIME`/`COUNTER_FORMAT→COUNTERED`, `WITHDRAW→WITHDRAWN`, `EXPIRE→EXPIRED`, `POLICY_CHANGED→POLICY_REVOKED`. `next_state` берёт целевое состояние по действию и возвращает его только если ребро легально из `current`, иначе `None`.
- **Ключевые решения:** добавлены два недостающих продюсера, которые §13 оставлял просто метками — `WITHDRAW`/`EXPIRE`; мэппинг `kp.map_decision_to_action` (agree→ACCEPT, counter→COUNTER_*) не тронут.
- **Тесты:** `C14-NEXT`.
- **Статус:** done.

#### §14.2 Оптимистичная конкуренция — CAS (`check_version` / `compare_and_swap`)

- **Что требует спека:** optimistic concurrency control по версии объекта.
- **Что построено:** `check_version(obj,expected)` и `compare_and_swap(obj,entity,to,expected_version)`.
- **Как работает:** CAS проверяет, что текущая `version` объекта равна той, что вычитал вызывающий; при совпадении делает `apply_transition` (version→2), при устаревшей — `{ok:False, error_code:"VERSION_CONFLICT"}` с удержанием состояния. Первый accept на **одном** объекте выигрывает, второй параллельный проигрывает.
- **Ключевые решения:** явно задокументировано ограничение — per-object CAS **не** даёт 1:1-эксклюзивности между РАЗНЫМИ кандидатами (оба стартуют с `version:1`, оба CAS прошли бы); эксклюзивность между кандидатами держит общий слот (`claim_slot`), а не CAS.
- **Тесты:** `C14-CAS`.
- **Статус:** done (single-process).

#### §14 Идемпотентность — clock-free dedup (`dedup_key` / `dedup`)

- **Что требует спека:** идемпотентность/де-дуп повторных нотификаций.
- **Что построено:** `dedup_key(entity,entity_id,action,extra=None)` + `dedup(seen,key,result)`; в matching-сервисе — обёртка `_idempotent(...)` (`app.py`) поверх `ks.dedup_key`.
- **Как работает:** ключ = `txn:entity|id|ACTION(|extra)` — **replay-stable** и **включает action**, поэтому WITHDRAW-после-ACCEPT на той же паре не схлопывается как дубликат ACCEPT. `dedup` при первом появлении ключа записывает `result` и возвращает `{duplicate:False}`, при повторе — СОХРАНЁННЫЙ прежний результат с `error_code:"DUPLICATE"` без повторного применения.
- **Ключевые решения:** ключ намеренно clock-free и не использует `proposal_id` (в него вшит `int(now)`), иначе повтор был бы неотличим; §4 `idempotency_key` опускал action — здесь исправлено.
- **Тесты:** `C14-DEDUP`.
- **Статус:** done (single-process).

#### §14.2 Уникальная активная пара (`unique_active_pair` / `mark_active_pair`)

- **Что требует спека:** не более одной активной proposal/match на неупорядоченную пару + purpose.
- **Что построено:** `unique_active_pair(active,pair,purpose)`, `mark_active_pair(...)`, `_pair_key(...)` (сортированный неупорядоченный ключ + опциональный purpose).
- **Как работает:** ключ строится из отсортированных lower-cased участников; если он уже в `active` (set/dict/list) — `{ok:False, error_code:"DUPLICATE_PAIR"}`, иначе OK. Дубликат второй волны отбивается, первая волна не роняется (её нет в `active` на момент проверки). Другой purpose — отдельный ключ, проходит.
- **Ключевые решения:** чистый примитив; как enforcing-gate в negotiate НЕ встроен, чтобы не менять slate.
- **Тесты:** `C14-UNIQUE-PAIR`.
- **Статус:** partial — примитив покрыт тестом, но не подключён как гейт в основной путь.

#### Reservation TTL (`reservation_expired`)

- **Что требует спека:** истечение резервации по TTL.
- **Что построено:** `reservation_expired(reservation, now_ts)`.
- **Как работает:** детерминированно по ЯВНОМУ `now_ts`: если есть `created_ts`+`ttl_seconds` (числа), возвращает `now_ts >= created_ts+ttl`; иначе (не-dict, нет created-эпохи) — False (deny-safe).
- **Ключевые решения:** без модульных часов — replay-детерминизм; реальной capacity/резервации в пилоте нет.
- **Тесты:** `C14-RESERVATION-TTL` (добавлен по итогам ревью, ранее был непокрыт).
- **Статус:** partial (чистая функция; реальной capacity нет — blocked_infra).

#### §14.3 Политика одновременных принятий (`concurrent_accept_policy` / `claim_slot`)

- **Что требует спека:** как разрешать одновременные accept на один intent в зависимости от его типа.
- **Что построено:** `concurrent_accept_policy(intent)` + общий слот `claim_slot(taken,intent_id,claimant)`; проводка в `negotiate_candidates` (`app.py:1854–1890`).
- **Как работает:** классификатор читает purpose/format/time и возвращает политику: `dating_manual_confirm` (exclusive, `auto_commit:False`), `event_capacity`/`group_reservation` (`enabled:False`, пилот-off), `one_to_one_fixed_time` (exclusive, один слот), иначе **дефолт** `multiple_conversations` (`exclusive:False`). Для 1:1 fixed-time `claim_slot` через общий `SESSION['_match_taken']` под `RLock`: первый claimant выигрывает, другой параллельный → `SLOT_TAKEN` и НЕ пишется как accepted (нет сосуществующего матча); тот же claimant повторно — идемпотентно `won:True`. Для dating accept **удерживается** (`NEEDS_MANUAL_CONFIRM`, без `_record_outcome`/`_stamp_accept`, agree сохранён).
- **Ключевые решения:** дефолт = multiple намеренно, чтобы существующий negotiate-путь (пишет каждого согласившегося) остался byte-identical; эксклюзивность включается только для настоящего 1:1 fixed-time, которого не строит ни один прежний фикстур.
- **Тесты:** `C14-SLOT`, `C14-POLICY`, `C14-NEG-MULTIPLE`, `C14-NEG-EXCLUSIVE`.
- **Статус:** done (single-process); group/event — pilot_disabled.

#### §14.4 Разрешение восьми критических гонок без утечки (`resolve_race`)

- **Что требует спека:** таблица канонических гонок → детерминированный исход, который никогда не раскрывает приватную причину.
- **Что построено:** словарь `_RACES` (8 кейсов) + `resolve_race(case,current_state,entity)`; в matching — `_stamp_txn(card,race_case)` (`app.py:1809`).
- **Как работает:** 8 кейсов (`policy_revoked_before_accept`, `blocked_before_send`, `privacy_tightened`, `slot_taken`, `duplicate_pair`, `duplicate_replay`, `reservation_expired`, `timezone_infeasible`) → `{case,entity,from,to,applied,error_code,public_reason,leak:False}`. `applied=True` только если целевое ребро легально из `current_state`; иначе исход рапортуется, но не форсируется. Кросс-агентная поверхность (envelope) несёт ТОЛЬКО грубый `public_reason` («no longer available» / «slot unavailable» / «expired» / «time not workable»); гранулярная причина гейта (blocked / private profile / not open to dating) остаётся только в owner-only `explain_match`.
- **Ключевые решения:** `leak:False` инвариант; `POLICY_CHANGED` переиспользован **verbatim** из §8.2 (никогда не переименовывается); неизвестный кейс → deny-safe OK/no-op.
- **Тесты:** `C14-RACE`.
- **Статус:** done.

#### Валидированная поверхность переходов — `agent_transition` + `/api/agent/transition`

- **Что требует спека:** единая валидированная точка WITHDRAW/EXPIRE/COUNTER с идемпотентностью и аудитом.
- **Что построено:** `agent_transition(body)` (`app.py:1894`), маршрут `/api/agent/transition` (`app.py:2422`), ресурсные обёртки `proposal_create`/`proposal_respond`/`plan_resource`.
- **Как работает:** под единым реентерабельным `_STORE_LOCK`: строит `dedup_key` → если ключ виден, возвращает прежний результат `DUPLICATE` без повтора; иначе edge-check (нет легальной цели → `ILLEGAL_TRANSITION`), при `expected_version` → `compare_and_swap` (стейл → `VERSION_CONFLICT`), иначе `apply_transition`. На успехе аппендит неизменяемый `SESSION['_trace']` (from→to/version/action/id) и append-only `SESSION['_outbox']`, затем `_save_store()`. Мемоизируется **только применённый** переход — failed edge/CAS не мемоизируется, чтобы corrected-retry (новый `expected_version`) не застрял как DUPLICATE. Stateless по объекту (пилот не держит кросс-запросный proposal-store — это blocked_infra; вызывающий round-trip’ит объект).
- **Ключевые решения:** clock-free → replay-детерминизм; один RLock закрывает read-then-write окно.
- **Тесты:** `C14-TRANSITION`.
- **Статус:** done (single-process); transactional outbox — только append `_trace`/`_outbox`, async-consumer нет (blocked_infra).

#### Идемпотентность `/api/agent/outcome` (атомарная)

- **Что требует спека:** повтор записи исхода не должен дважды аппендить метрики.
- **Что построено:** ветка `/api/agent/outcome` (`app.py:2405`), использует `ks.dedup_key("outcome", name, stage, extra=idem)`.
- **Как работает:** если передан `idempotency_key` — check (`_outcome_seen[key]`) + record (`_record_outcome`) + memoize идут под ОДНИМ `_STORE_LOCK` (RLock, `_record_outcome` пере-захватывает безопасно); повтор возвращает прежние метрики с `DUPLICATE`, мемоизация только при `ok`. Без ключа — прежний append без изменений.
- **Ключевые решения:** по итогам адверсариал-ревью (подтверждённая low-находка) check и record были в РАЗНЫХ lock-блоках → под `ThreadingHTTPServer` два параллельных replay могли дважды записать `_outcomes`; фикс — весь блок под одним RLock.
- **Тесты:** покрыто через `C14-*`/outcome-проверки; сюита 219/219.
- **Статус:** partial — idempotency-key не на всех write-эндпоинтах (только transition + opt-in outcome + `_idempotent`-обёртка feedback).

#### `build_proposal` version:1 и capsule-state

- **Что требует спека:** объекты несут счётчик оптимистичной конкуренции; match-капсулы отражают состояние.
- **Что построено:** `kc.build_proposal` получил статический `version:1`; `_match_capsules` несут аддитивный `state`; `_stamp_accept` ставит `SENT→ACCEPTED` + `match_state=MUTUAL`.
- **Как работает:** `build_proposal` теперь несёт `version:1` рядом со `status:'draft'`; инкремент версии живёт ТОЛЬКО за CAS/transition (тесты держат `==1` для эмиттеров). Match-капсулы: active→`MUTUAL`, completed→`COMPLETED`; целочисленная метрика `matches` не тронута.
- **Ключевые решения:** config-derived/аддитивно, byte-identity сохранена.
- **Тесты:** `C14-PROPOSAL-VERSION`, `C14-CAPSULE-STATE`.
- **Статус:** done.

#### Keyless / LLM-free инвариант

- **Что требует спека (проектная дисциплина):** секреты только в llm-service; модуль без модели.
- **Что построено / тесты:** `C14-STATES-KEYLESS` подтверждает, что `shared/kleal_states.py` не содержит ссылок на ключи и не имеет доступа к модели.
- **Статус:** done.

### Сводный статус (по `docs/STATE_MACHINES.md`)
**done (single-process) 7:** 4 автомата §14.1, deny-safe валидатор, optimistic CAS, idempotency-dedup (clock-free, action-aware), §14.3 политика + enforced 1:1-эксклюзивность, 8 гонок §14.4 без утечки. **partial / blocked_infra 6:** idempotency-key не на всех write-эндпоинтах; unique-active-pair как гейт не встроен; transactional outbox без async-consumer; retry-safe async consumers; reservation TTL без реальной capacity; cross-entity атомарный commit через сервисы (нужна БД/очередь). **pilot_disabled 1:** Plan-автомат (`enabled:False`, §15/§16). Тесты: 17 проверок `C14-*`, сюита 219/219 зелёная, детерминизм — двойной прогон.

---

## §15 Group Formation Core — детальный функциональный рекап

Модуль `shared/kleal_groups.py` (импортируется в `services/matching/app.py` как `kg`) + доки `docs/GROUP_FORMATION.md`. Это **conformance-scaffolding**: группа оценивается как МНОЖЕСТВО (не как среднее парных матчей), `group_formation` **выключен в пилоте** (§1.2/§15), ничего не встроено в живой person-to-person поток. Алгоритм запускается ТОЛЬКО под явным test-only override и всегда возвращает `enabled:False`. Всё локально, ничего не задеплоено. Дисциплина: модуль импортирует ТОЛЬКО stdlib `hashlib` + `kleal_contracts` (kc) + `kleal_states` (ks); НИКОГДА `core_v2`/`llm_client` (keyless, LLM-free). Sha-pinned `core_v2.py`+yaml не редактировались. Тесты: `services/matching/test_core_v2.py`, блок `C15G-*` (**21 проверка**, C15G-01…20 + 08b), детерминизм — двойной прогон.

#### §15.1 — Set-level hard constraints (гейты уровня множества)
- **что требует спека:** группа проходит набор жёстких ограничений уровня множества (размер, кворум, роли, блоки, безопасность, язык, оборудование, время), нарушение → группа невозможна.
- **что построено:** `kleal_groups.py:check_set_constraints` (+ обёртка `set_feasible`), пер-членный префильтр `filter_hard_set_constraints`.
- **как работает:** `check_set_constraints(group, constraints, params, now_ts)` возвращает ОТСОРТИРОВАННЫЙ список кодов нарушений (пусто == feasible): `SIZE_MIN`/`SIZE_MAX`/`QUORUM`/`CAPACITY_EXCEEDED`/`MANDATORY_ROLE_UNMET`/`PAIR_BLOCKED`/`SAFETY_EXCLUDED`/`HOST_MISSING`/`SKILL_SPREAD`/`LANGUAGE_UNCOVERED`/`EQUIPMENT_MISSING`/`PLATFORM_UNSUPPORTED`/`TIME_OVERLAP_INSUFFICIENT`. Языки/оборудование покрываются ОБЪЕДИНЕНИЕМ членов; skill-spread = `max(level)-min(level) > max_skill_spread`; время — жёсткий гейт при `min_duration_min` через истинное пересечение окон. `filter_hard_set_constraints` дропает только универсально-невозможных членов (safety-excluded, неверная `required_platform`, отсутствие всего `required_equipment`, level вне `level_band`) и сортирует по `(-relevance, id_hash, id)`.
- **ключевые решения:** deny-safe — неизвестный/неуказанный constraint = no-op, НИКОГДА не false-pass на block/safety. `now_ts` принимается ради clock-free симметрии сигнатуры (гейты используют окна членов, не настенные часы). Коды отсортированы для детерминизма.
- **тесты:** C15G-04 (feasibility-доминирование по 6 кодам), C15G-07 (mandatory vs role_coverage), C15G-18 (LANGUAGE_UNCOVERED/SKILL_SPREAD/HOST_MISSING/EQUIPMENT_MISSING независимо), C15G-19 (TIME_OVERLAP_INSUFFICIENT).
- **статус:** done.

#### §15.2 — GroupUtility (config-derived, feasibility-dominates)
- **что требует спека:** оценка группы = взвешенная сумма 5 компонент (least_misery, mean_pair_fit, role_coverage, time_overlap, diversity), веса из конфига; невозможная группа не имеет полезности.
- **что построено:** компоненты `least_misery`/`mean_pair_fit`/`role_coverage`/`time_overlap`/`diversity_value`, агрегатор `group_utility_components`, гейтованный `group_utility`; веса через `load_group_params`/`validate_group_config_block`/`_check_block`.
- **как работает:** `GroupUtility(G) = 0.35·least_misery + 0.25·mean_pair_fit + 0.20·role_coverage + 0.10·time_overlap + 0.10·diversity_value`, все веса читаются из sha-pinned `cfg['group_formation']['utility_weights']` (`config/Kleal_Matching_Core_Config_v2.yaml:220-229`), НИКОГДА не хардкодятся. `group_utility` при непустом `check_set_constraints` возвращает `utility=None` (не число) — feasibility ДОМИНИРУЕТ. `least_misery` = МИНИМУМ направленной удовлетворённости (защита от «высокое среднее прячет одного неподходящего»); `diversity_value` = normalized Gini-Simpson `(1-Σp²)/(1-1/N)` по `diversity_axis` (missing axis → 0.0). Каждая компонента ∈ [0,1], итог округляется до 6 знаков.
- **ключевые решения:** config-ключи — источник истины: `WEIGHT_KEYS` привязаны к ТОЧНЫМ именам yaml, `SPEC_ALIAS` документирует расхождение с прозой (`mean_member_relevance`≡`mean_pair_fit`, `diversity_budget`≡`diversity_value`), чтобы вес не был молча обнулён по неверному имени. `load_group_params`/`_check_block` закрывают пропуск `core_v2.load_config` (тот НЕ проверяет sum-to-1.0 для group-блока) БЕЗ редактирования sha-pinned yaml; read-only `validate_group_config_block` — на load-time (`app.py:536` `_GROUP_CFG_PROBLEMS`), raising-вариант — только в try/except эндпоинта. missing axis / infeasible → консервативный ноль/None, никогда «бесплатная» полезность.
- **тесты:** C15G-01 (полезность = ручная сумма по cfg-весам, сдвиг cfg → точная дельта), C15G-02 (least_misery=min, `[0.7]*3` > `[0.9,0.9,0.2]`), C15G-03 (диапазоны/нормализация компонент), C15G-04 (utility=None при нарушении), C15G-12 (sum≠1.0 → GroupConfigError; size-key propagation), C15G-14 (WEIGHT_KEYS == реальные ключи yaml, SPEC_ALIAS, weighted keyed by config names).
- **статус:** done (§15.2 веса — done_config_derived).

#### §15.2 — Pair relevance как ВХОД (никогда не пересчитывается)
- **что требует спека:** направленная релевантность R_{i→j} — вход в модуль формирования групп, не его собственное вычисление.
- **что построено:** `directed_relevance`, `member_from_card` (адаптер), star-fallback внутри `least_misery`/`mean_pair_fit`.
- **как работает:** `directed_relevance(pair_rel, a, b)` принимает `dict{(a,b):R}` | dict-of-dicts | callable | None; отсутствующее ребро → 0.0 (deny-safe: unknown ≠ openness), NaN → 0.0, клампится в [0,1]. Когда `pair_rel is None`, компоненты падают на star-fallback (min/mean по `member['relevance']`). Адаптер `member_from_card` маппит card `lcb` (направленный консервативный estimate) → `relevance` лоссless. Модуль НИКОГДА не строит n×n симметричную матрицу — это делает wiring-слой (task #37).
- **ключевые решения:** строгое разделение вход/вычисление — модуль не имеет доступа к core_v2, поэтому релевантность обязана приходить извне; deny-safe 0.0 на неизвестном ребре (незнание ≠ открытость).
- **тесты:** C15G-15 (явная pair_rel матрица драйвит least_misery; missing ребро → 0.0; star-fallback только при None).
- **статус:** done (симметричная n×n сборка из core_v2 — partial, за wiring).

#### §15.3 — MVP formation algorithm (детерминированный)
- **что требует спека:** seed → feasible pools → greedy marginal gain → local repair → reserve; лучшая найденная feasible-группа.
- **что построено:** `form_group` оркестрирует `filter_hard_set_constraints` → `generate_role_complete_seeds` → `greedy_marginal_add` → `local_repair` → `set_feasible`/`max_by_utility`; хелперы `_best_for_role`, `check_set_constraints_role_only`.
- **как работает:** первый оператор `form_group` — `if not enabled_override: return dormant_response(...)`, тело недостижимо в пилоте. Seed — минимальные множества, покрывающие ВСЕ mandatory-роли (deduped по `group_signature`, capped `max_seeds=16`); нет mandatory ролей → top-K feasible-синглтонов по id_hash. `greedy_marginal_add`: в FEASIBILITY-режиме (пока нарушение только `_SHORTFALL`=SIZE_MIN/QUORUM/MANDATORY_ROLE_UNMET) добавляет член, лучше всего ПРОГРЕССИРУЮЩИЙ к feasibility даже при нулевом/отрицательном marginal; затем OPTIMISE-режим — только positive-gain (least_misery немонотонен, поэтому gain на TOTAL utility). `local_repair`: строго-улучшающие ADD/SWAP/REMOVE (delta > EPS=1e-9). `max_by_utility` выбирает лучшую feasible-группу по seed'ам. Одинаковый вход (в любом порядке кандидатов) → **byte-identical** группа.
- **ключевые решения:** детерминизм — seed по `(-relevance,id_hash,id)`; greedy/repair tie по `(id_hash,id)`; cross-seed exact-tie → меньший `group_signature` (sha1 отсортированных id, permutation-proof); 6dp округление; стабильный sha1 `_id_hash` вместо солёного `hash()`; `now_ts` инъектируется. Терминация доказуема: greedy добавляет ≤1 члена за проход до `size_max`; repair кап `MAX_REPAIR_ITERS = 2·size_max·(|feasible|+1)`. FEASIBILITY-режим добавлен после адверсариал-ревью (иначе группа, которой нужен utility-нейтральный филлер до size_min, ложно возвращала NO_FEASIBLE_GROUP).
- **тесты:** C15G-05 (permutation-invariance, json byte-identity), C15G-06 (никогда не хуже known-feasible + в size-границах), C15G-16 (role-complete Dota формируется; недостающая роль → нет группы), C15G-20 (zero-value фillers достигают feasibility, нет ложного NO_FEASIBLE_GROUP).
- **статус:** done.

#### §15.3.5 + App C #8 — reservations + гонка последнего места (reuses §14)
- **что требует спека:** резервирование мест с атомарным разрешением гонки за последнее место (App C acceptance #8).
- **что построено:** `claim_group_seat`, `reserve_members` (переиспользуют `ks.claim_slot` и `ks.resolve_race` из §14, `kc.build_reservation` из §4).
- **как работает:** `claim_group_seat(ledger, group_id, seat_ordinal, capacity, claimant)` отклоняет `seat_ordinal >= capacity` ДО claim (`CAPACITY_EXCEEDED`), затем first-claim-wins атомарная вставка через `ks.claim_slot` по составному ключу `group_id#seatN` — БЕЗ нового lock. `reserve_members` назначает места в один ДЕТЕРМИНИРОВАННЫЙ sorted-проход; каждый принятый член claim'ит следующее место + `kc.build_reservation(now=now_ts)`; проигравший последнее место → `ks.resolve_race('slot_taken')` (WITHDRAWN / грубый public_reason / `leak:False`) + waitlist. `filled` НИКОГДА не превышает capacity по построению.
- **ключевые решения:** переиспользование §14-примитива (не bespoke lock); `now_ts` ОБЯЗАТЕЛЕН и инъектируется (иначе `kc.build_reservation` берёт `time.time()` — clock-leak, исправлено в дизайн-ревью); info-leak:False на проигравшем.
- **тесты:** C15G-08 (ровно один победитель, другой → SLOT_TAKEN, order-independent; claim≥capacity → CAPACITY_EXCEEDED; source содержит `claim_slot`), C15G-08b (3 члена / capacity 2 → filled==2, 1 rejected с leak:False + coarse reason).
- **статус:** done для single-process; кросс-процессная/мульти-под атомарность — **blocked_infra** (нужна БД/очередь, которых пилот не запускает).

#### §15.3.6/7 — invitations + replacement policy
- **что требует спека:** purpose-bound структурированные приглашения; политика замены (waitlist при отказе, cancel/reform при потере кворума).
- **что построено:** `build_group_invitations`, `replacement_policy`.
- **как работает:** `build_group_invitations(members, intent)` строит purpose-bound инвайты через `kc.build_profile_view` (clock-safe), purpose = domain/goal интента — СКОНСТРУИРОВАНЫ, НЕ отправлены (в пилоте нет мессенджинга). `replacement_policy` — DATA-ONLY (без исполнения): `on_refusal:waitlist`, `on_quorum_loss:cancel_or_reform`, отсортированный feasible-remainder waitlist по `(-relevance,id_hash,id)`.
- **ключевые решения:** pilot-disabled — инвайты как данные, не сообщения (нет messaging-инфраструктуры); replacement — чистая политика-данные, никакой side-effect.
- **тесты:** C15G-17 (below-quorum → нет группы; replacement_policy data-only с отсортированным waitlist `["D","C"]`).
- **статус:** §15.3.7 replacement — done (data-only); §15.3.6 structured invitations — **pilot_disabled** (сконструированы, не отправлены).

#### §15.4 — Domain constraint packs
- **что требует спека:** конкретные пер-доменные пресеты ограничений (dota/padel/conversation/walk).
- **что построено:** `DOMAIN_PACKS` + `pack_for(domain)`.
- **как работает:** плоские декларативные dict-пресеты: `dota` (4 mandatory-роли carry/support/mid/offlane, size 5, max_skill_spread 2), `padel` (4-местный корт, capacity 4, required_equipment racket), `conversation` (require_moderator, diversity_axis lang_role), `walk` (size 2-8, min_duration_min 30). Потребляются `form_group` по тому же enabled_override-пути. `pack_for` возвращает копию (пустой dict для неизвестного домена).
- **ключевые решения:** пресеты как данные — generic role/diversity/skill-spread механизмы уже работают; полная проводка доменов за §37+.
- **тесты:** C15G-16 (role-complete Dota stack формируется).
- **статус:** partial (generic-механизмы есть; полная доменная проводка — за §37).

#### Gating — dormant-at-pilot / falsifiable-under-override
- **что требует спека:** group_formation выключен в пилоте, но фальсифицируемо тестируется.
- **что построено:** `dormant_response`, `is_override_enabled`, `run_group_formation` + аддитивный эндпоинт `POST /api/agent/group` (`app.py:2429`).
- **как работает:** четыре слоя. (1) Global не тронут — `PILOT_DECISION_TYPES['group_formation']=False` (`app.py:574`), honest-empty `/api/agent/match` без изменений, модуль НИКОГДА не флипает флаг. (2) Module — чистая библиотека без import-side-effects. (3) Top gate — `form_group` короткозамыкает на dormant без override, даже под override результат несёт `enabled:False`. (4) Endpoint — НОВЫЙ аддитивный `POST /api/agent/group` (не переименование frozen `/api/agent/*`); тело `run_group_formation`, dormant если не `is_override_enabled` — требуется ТОЧНЫЙ `{'enable_group_formation': True}` (bool); non-bool truthy → dormant. Override per-request, test-only, не персистится. `load_group_params` в эндпоинте обёрнут в try/except → dormant при плохом конфиге (плохой конфиг не активирует group formation).
- **ключевые решения:** falsifiable-under-tight-override — алгоритм реально прогоняется под точным ключом, но результат всегда `enabled:False`; live-smoke даёт `utility 0.76875` (точная config-взвешенная сумма). Byte-identical person-to-person slate: `core_v2.search`/`match_candidates`/`negotiate` НЕ импортируют и не вызывают `kg` (статически проверено).
- **тесты:** C15G-09 (no/empty/wrong-key override → enabled:False, group:None), C15G-10 (falsifiable под точным override: группа + utility∈(0,1] + reservations, enabled:False; non-bool truthy → dormant), C15G-11 (byte-identical slate: sha-pinned engine + match/negotiate не ссылаются на group-модуль).
- **статус:** pilot_disabled (живая проводка в buddy→filtration→matching — endpoint enabled:False без точного override).

#### Discipline — keyless / LLM-free / no-side-effect
- **что требует спека:** дисциплина модуля (детерминизм, keyless, no FS/clock/random).
- **что построено:** статические инварианты всего `kleal_groups.py`.
- **как работает:** модуль импортирует ТОЛЬКО `hashlib`+`kc`+`ks`; отсутствие `import time`/`import os`/`import random` доказывает no-clock/FS/randomness на уровне исходника (любой `time.time()` был бы NameError); `hashlib` даёт детерминизм. Ноль ссылок на ключи/Bearer/llm_client/core_v2.
- **ключевые решения:** keyless/LLM-free — как у соседних §-модулей (kleal_states/kleal_contracts); детерминизм через sha1, не солёный hash().
- **тесты:** C15G-13 (keyless / LLM-free / no core_v2 / no FS / no clock / no randomness; uses hashlib).
- **статус:** done.

---

**Сводный статус (из docs/GROUP_FORMATION.md):** done 10 · done_config_derived 2 · pilot_disabled 2 · partial 2 · blocked_infra 1. Дизайн-ревью (6 агентов): 11 must-fix + 3 blocking — все применены. Адверсариал-ревью реализации (5 finders → verify, 20 находок, 4 подтверждены, все low): исправлены `_common_window` (истинное пересечение множеств интервалов вместо bounding-span), `greedy_marginal_add` (FEASIBILITY-режим против ложного NO_FEASIBLE_GROUP), `directed_relevance` NaN→0.0, укреплены C15G-06/C15G-14. Суита 240/240 зелёная, детерминизм — двойной прогон.

**Ключевые файлы:** `C:\Projects\.dating\shared\kleal_groups.py`, `C:\Projects\.dating\docs\GROUP_FORMATION.md`, `C:\Projects\.dating\services\matching\test_core_v2.py` (C15G-01…20, 08b), `C:\Projects\.dating\services\matching\app.py` (эндпоинт `/api/agent/group` строки 2429-2455; load-time валидатор строки 533-536), конфиг `C:\Projects\.dating\config\Kleal_Matching_Core_Config_v2.yaml:220-229` + `C:\Projects\.dating\config\schema.json:112-119`.

---

## §16 Events / Rooms / Venues как ОТДЕЛЬНЫЕ типы кандидатов

Всё реализовано в новом keyless / LLM-free модуле `shared/kleal_candidates.py` (`CANDIDATES_VERSION = "candidates-16.0.0"`, импортируется как `kct`) + аддитивная **gated**-проводка в `services/matching/app.py`. Модуль импортирует ТОЛЬКО stdlib `hashlib` + `kleal_contracts` (kc) + `kleal_states` (ks) + `kleal_groups` (kg); никогда `core_v2` / `llm_client` / `app`. Нет FS/clock/random ни на import, ни на runtime — `now_ts` инъектируется в каждый вызов. sha-pinned `core_v2.py` и yaml-конфиг НЕ редактировались; person-to-person slate байт-идентичен. Всё лежит локально, ничего не задеплоено. Тесты: `services/matching/test_core_v2.py`, блок `C16-*` (24 проверки), сюита зелёная, детерминизм проверяется двойным прогоном перестановок.

#### §16.0 «Событие ≠ пользователь с большой capacity» — структурно

- **что требует спека:** Event/OnlineRoom/Venue — свои типы объектов, не «user with big capacity»; у каждого свой гейт, свой направленный ранкинг и своя транзакция; объект может закрыть intent, но честно как альтернатива, не как «совпадение с людьми».
- **что построено:** `kct._intrinsic(kind)` (`shared/kleal_candidates.py:217`) + все три билдера `build_event`/`build_room`/`build_venue`.
- **как работает:** `_intrinsic` штампует на КАЖДОМ built-объекте `is_personal_match:False`, `is_alternative:True`, `tier:"T4"`, `closes_intent_as:"alternative"`, `_contract`. На объектах физически нет `reciprocal_score`/mutual-полей; направленные скореры (`user_event_relevance`/`session_relevance`/`plan_suitability`) читают только сторону объекта, никакого обратного object→user сигнала.
- **ключевые решения:** «event ≠ user» вшито в структуру на этапе build, а не наклеено downstream; huge `seats_total` не даёт high-capacity boost (capacity лишь один термин с весом 0.05).
- **тесты:** `C16-EVENT-NOT-USER` (подмешивание `intents`/`receiving`/`wants`/`mutual_policy` на объект не меняет score; seats_total=99999 не выигрывает), `C16-DIRECTED-ONEWAY` (object-side `wants`/`preference`/`seeks` не меняют score для event/room/venue), `C16-HONEST-ALTERNATIVE-INTRINSIC`.
- **статус:** pilot_disabled (реализовано как scaffolding).

#### Object builders (raw dict → типизированный объект)

- **что требует спека:** нормализовать сырые кандидаты в типизированные объекты с деривацией мест/цены/окон.
- **что построено:** `build_event` (`:221`), `build_room` (`:240`), `build_venue` (`:255`), диспетчер `build_object` (`:272`), плюс минимальный `build_candidate_view` (`:278`).
- **как работает:** `build_event` парсит start/end через `kc._parse_iso` в epoch, деривит `seats_left = seats_total − seats_taken`, `paid`; `build_room` нормализует platform/max_live/current_participants/moderation; `build_venue` нормализует `open_windows` через `_norm_windows`, noise, accessibility-флаги. `build_object` идемпотентен на уже-built объекте (wiring прогоняет raw slate). `build_candidate_view` — object-level минимальное раскрытие (title/topics/time/place/price/url), НЕ `kc.build_profile_view` (у объекта нет person-полей для purpose-binding).
- **ключевые решения:** единый epoch-юнит везде через `kc._parse_iso` (никаких «сырых минут»), детерминированные id через `kc._det_id`.
- **тесты:** `C16-OBJECT-VIEW` (view отдаёт только object-поля, distinct от `kc.build_profile_view`).
- **статус:** pilot_disabled.

#### Eligibility — свой hard-гейт на каждый тип (distinct code path)

- **что требует спека:** у каждого типа свой eligibility-гейт по своим измерениям.
- **что построено:** `event_eligibility` (`:290`), `room_eligibility` (`:323`), `venue_eligibility` (`:347`), диспетчеры `check_eligibility`/`is_eligible` (`:371`).
- **как работает:** каждый возвращает ОТСОРТИРОВАННЫЙ список violation-кодов (`[]` == eligible), deny-safe. Event: `CATEGORY_MISMATCH`, `SCHEDULE_PAST`, `SCHEDULE_NO_OVERLAP`, `CAPACITY_FULL`, `ACCESS_AGE/VERIFIED/LANGUAGE/PAID`, `GEO_OUT_OF_RADIUS`. Room: `TOPIC_MISMATCH`, `PLATFORM_UNSUPPORTED`, `MODE_OFFLINE_NO_CONSENT`, `LIVE_CAPACITY_FULL`, `MODERATION_REQUIRED`, `LANGUAGE_UNCOVERED`. Venue: `UNAVAILABLE`, `PRICE_OVER_BUDGET`, `GEO_OUT_OF_RADIUS`, `NOISE_UNACCEPTABLE`, `ACCESSIBILITY_REQUIRED`.
- **ключевые решения:** topic/category-гейт срабатывает ТОЛЬКО когда обе стороны объявили topics И directed overlap==0 (no over-matching); `MODE_OFFLINE_NO_CONSENT` — offline-intent не подменяется на online молча (нужен `allowOnlineFallback`, §5.1); noise — гейт лишь при hard-requireQuiet + lively-venue, иначе мягкий термин; prove-eligible гейты (verified/accessibility) при stated-требовании и неизвестном атрибуте дают violation, не false-pass.
- **тесты:** `C16-ELIG-EVENT`, `C16-ELIG-ROOM`, `C16-ELIG-VENUE`, `C16-TOPIC-GATE-DENYSAFE`.
- **статус:** pilot_disabled.

#### Directed user→object ranking (одностороннний, не reciprocal)

- **что требует спека:** направленный ранкинг user→object без обратной оценки, без person-пайплайна.
- **что построено:** термин-функции `_event_terms`/`_room_terms`/`_venue_terms` (`:380`–`:413`), общий `score_candidate` (`:417`) + семантические алиасы `user_event_relevance`/`session_relevance`/`plan_suitability` (`:431`–`:438`), `rank_candidates` (`:449`).
- **как работает:** `score_candidate` сначала зовёт `check_eligibility`; если есть violations → `score = None` (никогда число). Иначе взвешенная сумма module-local весов: Event = 0.35·topic + 0.25·schedule + 0.15·distance + 0.10·price + 0.10·access + 0.05·capacity; Room = 0.35·topic + 0.25·liveness + 0.20·moderation + 0.10·language + 0.10·platform; Venue = 0.25·distance + 0.20·availability + 0.20·noise + 0.15·price + 0.10·amenity + 0.10·accessibility. `rank_candidates` дропает score-None ДО сортировки, сортирует по `_sort_key`, диверсифицирует ≤3 на topic-bucket, кап `TOP_N=10`, проставляет `rank`. Термины используют нейтральные helpers (`_distance_fit`, `_price_fit`, `_capacity_term`, `_healthy_liveness` — пик при ~50% occupancy, `_noise_term`, `_schedule_term`, `_availability_term`).
- **ключевые решения:** feasibility доминирует (ineligible = None, не может ранжироваться/выигрывать); веса module-local `EVENT_WEIGHTS/ROOM_WEIGHTS/VENUE_WEIGHTS` (каждый суммируется в 1.0), НЕ config-derived — переданный `cfg` не меняет score; `topic_fn` — чистый инъектируемый вход (по умолчанию self-contained literal-token Jaccard, никогда `app.topical`/`core_v2`); O(n log n), один проход на объект (нет §15 pairwise blow-up).
- **тесты:** `C16-WEIGHTS-SUM`, `C16-FEASIBILITY-DOMINATES`, `C16-NOT-CONFIG-WEIGHTED`, `C16-TOPIC-INJECTED`.
- **статус:** pilot_disabled.

#### Детерминизм ранкинга (byte-identical, strict total order)

- **что требует спека:** детерминированный вывод без clock/random.
- **что построено:** `_sort_key` (`:89`) + `_content_key` (`:79`), helpers `_id_hash`/`_obj_id`.
- **как работает:** сортировка по кортежу `(-score, sha1(obj_id), obj_id, content_key)`. `_content_key` хеширует видимый контент карточки (name/kind/score/topics/components) — это финальный tiebreak, гарантирующий strict TOTAL order, чтобы два РАЗНЫХ объекта, коллизирующих на `kc._det_id` id (одинаковый title+start, разные topics) при равном score, не зависели от порядка входа stable-sort.
- **ключевые решения:** content-hash tiebreak добавлен по итогам адверсариал-ревью (medium-баг: без него stable-sort протекал input order); `_list` сортирует set-входы (no PYTHONHASHSEED-leak).
- **тесты:** `C16-DETERMINISM` (byte-identical по перестановкам входа), `C16-DETERMINISM-COLLISION` (json-dump двух перестановок коллизирующих объектов идентичны).
- **статус:** done (в рамках модуля).

#### Транзакции — data-only, capacity через §14

- **что требует спека:** своя data-only транзакция на тип (registration/handoff · join-token/waitlist · selection/booking-handoff), без реальных внешних вызовов.
- **что построено:** `event_transaction` (`:482`), `room_transaction` (`:507`), `venue_transaction` (`:530`), диспетчер `build_transaction` (`:546`); capacity через `claim_seat` (`:473`) → `kg.claim_group_seat` → `ks.claim_slot`.
- **как работает:** Event: при `external_url` → `external_handoff` с детерминированным `handoff_token`; иначе seat-registration через `kc.build_reservation(now=now_ts)`; проигравший на последнем месте → `waitlist` через `ks.resolve_race('slot_taken')` (грубый public_reason, `leak:False`). Room: `join_token` на выигранный live-seat, иначе waitlist; capacity = `live_left = max(0, max_live − current_participants)`, НЕ raw max_live. Venue: `selection` через `kc.build_plan(enabled:False)` или `booking_handoff`-дескриптор. Все payload несут `enabled:False`.
- **ключевые решения:** переиспользование §14 capacity (`kg.claim_group_seat` отклоняет `seat_ordinal>=capacity` до claim), single-process — кросс-под атомарность blocked_infra; токены/резервации — детерминированные дескрипторы, НЕ реальные креды; `int(now_ts or 0)` вместо clock; room live_left-фикс по итогам ревью (полная комната ложно давала join_token).
- **тесты:** `C16-CAPACITY-EVENT` (2 претендента на 1 место → registration + waitlist; `claim_seat` reject ordinal>=capacity), `C16-CAPACITY-ROOM` (full room → waitlist, свободная → join_token, capacity от max_live−current), `C16-TRANSACTION-DATA-ONLY` (venue selection = build_plan enabled:False; reservation version+ttl+expires_at от инъектированного now_ts).
- **статус:** partial (алгоритм готов; кросс-под атомарность blocked_infra).

#### Pilot-gating и per-kind эндпоинты

- **что требует спека:** функционал есть, но выключен в пилоте; не должен ломать существующие person-решения.
- **что построено:** `is_override_enabled` (`:557`), `dormant_response` (`:562`), `run_candidates` (`:567`), `_infer_kind` (`:585`), унифицированный диспетчер `run_candidate_recommendation` (`:593`); эндпоинт `/api/agent/event|room|venue` в `services/matching/app.py:2456`.
- **как работает:** `run_candidates` дормантен (enabled:False, candidates:[]) ПОКА нет `is_override_enabled(kind, override)` — нужен ТОЧНЫЙ `{'enable_intent_to_<kind>':True}` boolean True (None/{}/wrong-key/'true'-string → dormant). Под точным override гоняет build→rank, но результат ВСЕГДА `enabled:False`, `override:True`. Эндпоинт (`app.py:2461`) резолвит kind из пути, принимает `intent`/`objects`(или `candidates`)/`user`, передаёт `cfg=_CORE_CFG` (для симметрии, но score не влияет), `now_ts = body.now or time.time()` (инъекция снаружи модуля). Read-only ранкинг, без reservation side-effect.
- **ключевые решения:** модуль НИКОГДА не мутирует `app.PILOT_DECISION_TYPES`; `cfg` принят для симметрии эндпоинта, но §16-ранкинг не config-derived; сырые slate прогоняются через `build_object`.
- **тесты:** `C16-PILOT-DISABLED-DEFAULT`, `C16-OVERRIDE-FALSIFIABLE`, `C16-CLOSES-INTENT-WITHOUT-PERSON`, `C16-PILOT-FLAGS-UNTOUCHED`.
- **статус:** pilot_disabled.

#### Аддитивная проводка venue-enum (intent_to_venue) в app.py

- **что требует спека:** `intent_to_venue` в decision-types добавить, не сломав person-enums.
- **что построено:** `PILOT_DECISION_TYPES` (`app.py:575-577`) с `intent_to_event/room/venue = False`; `_decision_type` (`app.py:588-590`) распознаёт `eventId`/`type==event`, `roomId`, `venueId`/`type==venue`; `_PTYPE_OF_DECISION` (`app.py:1633-1634`) мапит venue→"venue"; `venue` добавлен в `kc.PROPOSAL_TYPES`.
- **как работает:** `event`/`room` уже существовали в PILOT_DECISION_TYPES; PR #39 добавил `intent_to_venue:False` + proposal-type/ptype `venue` АДДИТИВНО. Все три флага объявлены-но-выключены (никогда не флипаются True в git).
- **ключевые решения:** additive — существующие person-enums сохранены как preserved subset; `intent_to_venue` остаётся disabled.
- **тесты:** `C16-VENUE-ENUM-ADDITIVE` (venue в `kc.PROPOSAL_TYPES`, `_PTYPE_OF_DECISION[intent_to_venue]=="venue"`, `PILOT_DECISION_TYPES[intent_to_venue] is False`, `_decision_type({venueId})=="intent_to_venue"`, `_pilot_enabled` False).
- **статус:** pilot_disabled.

#### Изоляция от sha-pinned engine и person-slate

- **что требует спека:** новый модуль не должен затрагивать sha-pinned engine и person-пайплайн.
- **что построено:** дисциплина импортов + guard-тесты.
- **как работает:** `core_v2`, `app.match_candidates`, `app.negotiate_candidates` НЕ ссылаются на `kleal_candidates`; §12 `_online_fallback` не тронут (та же T4-лексика, но отдельный код-путь).
- **ключевые решения:** byte-identical person-slate, keyless/LLM-free, sha-pinned core_v2+config неизменны.
- **тесты:** `C16-BYTE-IDENTICAL-PERSON-SLATE` (kleal_candidates отсутствует в исходниках core_v2/match/negotiate), `C16-NO-FORBIDDEN-IMPORTS` (нет core_v2/app/FS/clock/random/llm_complete; только hashlib+kc+ks+kg).
- **статус:** done.

---

**Итоговый статус (§16):** pilot_disabled по всем боевым способностям (distinct types, build+eligibility+directed ranking+transaction на каждый тип, honest-alt typing, per-kind gated endpoints); done по детерминизму/изоляции/enum-аддитивности; partial по transaction (алгоритм готов, кросс-под capacity-атомарность и живой retrieval-feed §7 source 4 — blocked_infra, объекты подаются вызывающим). Документация — `docs/CANDIDATE_TYPES.md`.

---

## §17 Dating — защитные механизмы (Matching Core v2)

Обзор: весь слой §17 — **keyless, LLM-free, детерминированный**. Реализован двумя частями: чистые контракты в `shared/kleal_contracts.py` (+ `shared/kleal_intent.py` для consent), и гейты/скоуп/редакция в `services/matching/app.py`. Sha-pinned `core_v2.py` + `config/` **не тронуты**; все построенное — ADDITIVE-надстройка над скорером (новые ключи, никогда не переименовывает/не роняет поле, которое читает движок). Person-slate остаётся **byte-identical** для существующих фикстур и демо-пула (гейты стреляют только на присутствующем restrictive-значении, default-ALLOW на отсутствии). Всё **локально, ничего не задеплоено**.

#### §17.1 Dating-капсула (отдельный purpose-bound профиль)

- **что требует спека**: dating-профиль — отдельная purpose-связанная капсула, из которой структурно исключена профессиональная инференция и сенситивный контур.
- **что построено**: `build_dating_capsule(user, disclosure_stage, now)` — `shared/kleal_contracts.py:212`; опирается на `build_profile_view(..., "dating", ...)` (`kleal_contracts.py:171`) и allow-list `PURPOSE_FIELDS["dating"]` (`kleal_contracts.py:85`).
- **как работает**: капсула строится поверх purpose-view с purpose=`"dating"`, поэтому поле `entities` (профессиональные сущности) **структурно отсутствует** — его нет в dating allow-list. Далее применяется дополнительная минимизация: точный возраст коарсится в band, а сенситивный контур `_DATING_SENSITIVE = (orientation, gender_target, preferences, health, religion, politics)` (`kleal_contracts.py:197`) всегда вычищается (`fields.pop`). Возвращает `{capsule_id, purpose:"dating", disclosure_stage, fields, policy_version:"dating-policy-1.0.0", sensitive_excluded:True}`.
- **ключевые решения**: byte-identity исключения `entities` достигается через purpose-binding (комплемент deny-колонки §8.3), а не ad-hoc фильтром; собственный `policy_version` = версионирование политики отдельно от контрактов; детерминизм — `now` инжектится, `capsule_id` через `_det_id` (sha1 без часов/рандома); keyless.
- **тесты**: `CP2-DATING-CAPSULE` (test_core_v2.py:1766) — проверяет отсутствие `entities` и `orientation`, `sensitive_excluded is True`, `age_band=="25-34"`, отсутствие сырого `age`; `CP10-CAPSULE` (:1985) и `CP10-D0` (:1998) фиксируют purpose-binding матрицу.
- **статус**: done.

#### Data minimization — коарсинг возраста (age_band)

- **что требует спека**: точный возраст не раскрывается без явного согласия — минимизируется в диапазон.
- **что построено**: `age_band(age)` — `shared/kleal_contracts.py:199`.
- **как работает**: маппит int-возраст в банды `under_18 / 18-24 / 25-34 / 35-44 / 45-54 / 55+`; нечитаемый вход -> `None`. В `build_dating_capsule` (`:221`): если `age` присутствует и **нет** `consent_exact_age`, точный `age` удаляется (`fields.pop("age")`) и заменяется на `age_band`; при явном `consent_exact_age=True` — точный возраст сохраняется, `age_band` не добавляется.
- **ключевые решения**: минимизация по умолчанию (deny-safe), точный возраст — только по opt-in consent-флагу; чистая функция, детерминированная, config-независимая.
- **тесты**: `CP2-DATING-CAPSULE` (test_core_v2.py:1766-1769) — обе ветки: без consent -> band, с `consent_exact_age=True` -> `age==29` и `age_band` отсутствует.
- **статус**: done.

#### §17.1 Staged disclosure — пофилдовые стадии раскрытия (disclosure_field_stages)

- **что требует спека**: пофилдовое раскрытие по стадиям (photo/name/detail видны только начиная с настроенной стадии).
- **что построено**: обработка `user["disclosure_field_stages"]` внутри `build_profile_view` — `shared/kleal_contracts.py:184-187`; ранги стадий `DISCLOSURE_STAGES/DISCLOSURE_RANK` (`:53-54`).
- **как работает**: `disclosure_field_stages = {field: required_stage}`; поле удерживается, если его required-стадия **выше** текущей (`DISCLOSURE_RANK.get(fstages.get(k),0) <= cur`). Например поле, помеченное `match_only`, скрыто на `limited_profile` и появляется на `match_only`. `name` всегда сохраняется. Если ключ отсутствует — фильтр не применяется (byte-identical со stage-level проекцией).
- **ключевые решения**: opt-in per-field (отсутствие карты -> нет фильтрации, обратная совместимость); детерминированное сравнение по рангам; keyless.
- **тесты**: `CP2-DISCLOSURE` (test_core_v2.py:1771-1775) — `interests` тег `match_only` скрыт на `limited_profile`, присутствует на `match_only`, `name` всегда есть, unfiltered view не изменён.
- **статус**: done.

#### §17.1 Consent — структурный dating-opt-in (никогда не инференция)

- **что требует спека**: dating-режим включается только по явному согласию пользователя; согласие фиксируется структурно, никогда не выводится.
- **что построено**: `apply_confirmation(intent, confirmed_ids, constraints, now)` — `shared/kleal_intent.py:209`, ветка `dating_evergreen` (`:222-228`); детекция кандидата `extract_constraints` row5 (`kleal_intent.py:172-179`); P0-гейт `dating_opt_in` в `clarification_policy`/`_detect_gaps` (`:278-280`).
- **как работает**: свободный текст («вторую половинку»/soulmate) даёт **soft** constraint `{id:dating_evergreen, sensitive:True, proposed_value:"dating"}` — но `type` не переключается. Только когда пользователь подтвердит id, `apply_confirmation` ставит `type="dating"` и записывает структурный блок `dating_consent = {opt_in:True, target_prefs, at:iso}`. Без подтверждения `dating_consent` **отсутствует**, `type` остаётся прежним. Побочных эффектов на `verifiedOnly`/`minAge` нет.
- **ключевые решения**: consent — только L2 (`user_confirmed_intent_summary`), никогда L7-инференция; отделение «предложить» от «включить» (never a silent hard gate); детерминизм (`now` инжектится); keyless (LLM только парсит текст, вывод untrusted и проходит через этот слой).
- **тесты**: `CP3-CONSENT` (test_core_v2.py:1786-1790) — блок появляется только после confirm, несёт `opt_in` + `target_prefs.minAge==25`, при пустом confirm отсутствует.
- **статус**: done.

#### §17.2 Isolation — mode-scoped feedback (dating не течёт в friendship)

- **что требует спека**: отказ/сигнал в одном режиме не должен влиять на ранжирование/ребро в другом режиме.
- **что построено**: `record_feedback(name, decision, uid, purpose=None)` — `services/matching/app.py:356`; `_relationship_edge(name, uid, scope)` — `app.py:1308`.
- **как работает**: `record_feedback` при заданном `purpose` пишет ключ `"name::purpose"` (например `Zed::dating`), при `purpose=None` — bare-name (byte-identical со старым domain-agnostic поведением). `_relationship_edge` при заданном `scope` сначала ищет purpose-scoped ключ `name::scope`, затем откатывается на bare-name. Итог: dating-decline переводит в `avoid` только dating-ребро, friendship-ребро остаётся не `avoid`; legacy bare-decline по-прежнему применяется ко всем режимам. Edge строится через `kc.build_relationship_edge` (advisory, не авторитетный — реальный cooldown/block остаётся hard-gate).
- **ключевые решения**: purpose-scoping опционален (обратная совместимость / byte-identity legacy); edge advisory-only, не двойной гейт; детерминизм — состояние из session-store, без рандома.
- **тесты**: `CP1-ISOLATION` (test_core_v2.py:1722-1728) — dating-decline «Zed» -> dating-ребро `avoid`, social-ребро НЕ `avoid`; bare-decline «Wyn» -> social-ребро `avoid`.
- **статус**: done.

#### §17 / §0.8 Dating как gated contour — hard-gate + release-gate

- **что требует спека**: dating — отдельный gated-контур: без opt-in — BLOCK; при opt-in — допуск только через отдельный safety/legal трек.
- **что построено**: `_hard_gates` dating-условие (`app.py:738`: `type=='dating' and not c['datingOk'] -> 'not open to dating'`); `_policy_decision` release-gate (`app.py:793-797`); `evaluate_policy` фасад (`app.py:800`); cross-purpose isolation `_cross_purpose_blocked` (`app.py:711`, матрица `_XPURPOSE_BLOCK` :701).
- **как работает**: dating-intent против кандидата без `datingOk` -> BLOCK. При `datingOk` но unverified и config-домене с `release_gate=separate_safety_legal_track` -> **REVIEW** (discoverable, но не auto-proposable). `evaluate_policy` прогоняет весь стек по порядку (`_hard_gates -> cross-purpose -> _policy_decision -> disclosure-clamp`) и отдаёт единый typed-объект `{decision, reason, eligible, cross_purpose_blocked, disclosure, policy_version:"policy-2.0.0"}`, воспроизводя per-gate исход byte-for-byte. Cross-purpose: dating спарен с friendship/networking/language/games/sport в `_XPURPOSE_BLOCK`; purpose кандидата читается ТОЛЬКО из его собственных активных интентов, не из `datingOk`/receiving/interests.
- **ключевые решения**: release-gate — config-derived (читается из `_CORE_CFG.domains[domain].release_gate`, sha-pinned конфиг не тронут); tri-state ALLOW/REVIEW/BLOCK вместо boolean; opt-in-only (absent -> unchanged BLOCK, byte-identity); детерминированный gates-стек, LLM-независимый.
- **тесты**: `CP10-DATING-CONTOUR` (test_core_v2.py:1988-1990) — no `datingOk` -> BLOCK, `datingOk+verified` -> ALLOW; `CP1-OUTAGE` (:1758) — при упавшем LLM gate `not open to dating` всё равно стреляет и slate byte-identical.
- **статус**: done.

#### §17.1 Explanation — редакция сенситивной dating-причины

- **что требует спека**: сенситивная причина отказа никогда не показывается не-владельцу; заменяется на coarse public reason.
- **что построено**: `_redact_dating_reason(reason, domain)` + карта `_DATING_REDACT` — `services/matching/app.py:1987-1992`.
- **как работает**: в dating-домене причины `not open to dating` / `private profile` / `not verified` маппятся в `"no longer available"`; вне dating-домена причина не меняется (owner-only поверхности сохраняют детали); несенситивная причина проходит без изменений. Отдельно live-путь negotiate использует coarse-причину `POLICY_REVOKED` через `_stamp_txn` (`app.py:1864`).
- **ключевые решения**: редакция только в dating-скоупе (owner видит детали в своих поверхностях); детерминированный маппинг по замкнутой карте.
- **тесты**: `CP10-REDACT` (test_core_v2.py:1966-1969) — dating -> `no longer available`, social_meet -> без изменений, `good fit` в dating -> без изменений.
- **статус**: partial — функция определена и покрыта тестом, но как автономный helper; в текущем live response-пути negotiate не вызывается (coarse-причина там идёт через `_stamp_txn`/POLICY_REVOKED). Готова к точечной привязке к внешней explanation-поверхности.

#### §14.3 Dating — ручное подтверждение матча (no auto-commit)

- **что требует спека**: в dating агент не имеет права авто-фиксировать матч по accept второй стороны — требуется явное подтверждение пользователя.
- **что построено**: ветка `dating_manual_confirm` в negotiate-цикле — `app.py:1885-1888`; политика из `ks.concurrent_accept_policy(intent)` (`app.py:1854`).
- **как работает**: если `accept_policy.auto_commit is False and policy=="dating_manual_confirm"`, кандидат помечается `code="NEEDS_MANUAL_CONFIRM"`, `manual_confirm_required=True` и **удерживается** — без `_record_outcome`/`_stamp_accept`, матч в `_matches` не записывается. Обычный (non-dating) accept идёт по неизменному byte-identical пути.
- **ключевые решения**: dating-исключительность из общей политики согласия; матч не материализуется без пользователя (защита от авто-обязательства); детерминизм — политика выводится из intent.
- **тесты**: `CP5-DATING-NOAUTO` (test_core_v2.py:1835-1836) — dating-intent не авто-коммитит: `_matches` пуст, есть `NEEDS_MANUAL_CONFIRM`.
- **статус**: done.

#### §19.2 Decay / drop_inferred (сопутствующая минимизация инференции)

- **что требует спека**: мягкая agent-инференция (L7) теряет уверенность со временем; одиночное поведение не создаёт постоянного вывода.
- **что построено**: `decay(evidence, now)` (`kleal_contracts.py:229`) и `drop_inferred(evidence_list)` (`kleal_contracts.py:244`).
- **как работает**: `decay` уменьшает `confidence` только для `source=="agent_inference"` по полураспаду ~30 дней (`0.5 ** (age_days/30)`), возвращает копию, источники выше по авторитету не трогает. `drop_inferred` удаляет только L7-строки, сохраняя все вышестоящие. Оба детерминированы (`now` инжектится), не мутируют вход.
- **ключевые решения**: только L7 распадается/дропается (explicit-правки выживают); чистые функции, keyless.
- **тесты**: `CP2-DECAY` (test_core_v2.py:1779-1783) — 60д = 2 полураспада -> `confidence≈0.2`, L4-источник `0.9` не тронут, `drop_inferred` оставляет только non-inferred.
- **статус**: done.

---

### Сводный статус §17
- Реализованы и покрыты тестами (done): dating-капсула, age_band-минимизация, staged disclosure, consent-opt-in, mode-isolation feedback, gated contour (BLOCK/REVIEW/release-gate), manual-confirm, decay/drop_inferred.
- Partial: `_redact_dating_reason` (готовый протестированный helper, не привязан к live-negotiate response-пути).
- Инварианты соблюдены: keyless / LLM-free, sha-pinned core_v2+config не тронуты, person-slate byte-identical, детерминизм (инжект `now`, sha1-id без рандома), pilot-gates (dating manual-confirm; venue/group — off). Всё локально, ничего не задеплоено.
- Ключевые файлы: `C:\Projects\.dating\shared\kleal_contracts.py`, `C:\Projects\.dating\shared\kleal_intent.py`, `C:\Projects\.dating\services\matching\app.py`, тесты `C:\Projects\.dating\services\matching\test_core_v2.py`.

---

# Раздел: закрытие 47 «частично»-подпунктов (батчи CP1–CP10) + §21–23 (API/observability/registry) + доработки §0–§3/§18–§20

_Дисциплина фактов, действующая на весь раздел:_ всё закрыто **аддитивным keyless-кодом** (модули `shared/kleal_*` и хелперы `services/matching/app.py` не держат ни ключей, ни `MODEL_ID`-доступа, ни FS-мутаций пула); **sha-pinned движок `core_v2.py` + `config/*.yaml` не тронуты** — новые слои читают их наружу, но не переписывают `_sha256`; **person-slate байт-идентичен** (все гейты absent-permissive → field-less фикстуры и демо-пул из 50 не меняются); **всё детерминировано** (double-run стабильность, LLM заглушаем без сдвига вердикта); **ничего не задеплоено** — только локально, суита `test_core_v2.py` зелёная. Единственный LLM-вызов в конвейере остаётся `negotiate_one` (фразирование), причём accept/reject-бит детерминирован.

Каждый CP-батч — это «отбивка» одного класса блокеров; ниже — по подпунктам с точными `file:function`-ссылками.

---

## Батч CP1 — изоляция режимов, презентация карточки, языковой гейт, устойчивость к отказу LLM

#### CP1-ISOLATION — §17.2/§C.13 изоляция ребра dating vs friendship
- **что требует спека:** отказ в dating-режиме не должен «протекать» на дружеское ребро.
- **что построено:** `app.py:record_feedback` — необязательный параметр `purpose` скоупит ключ фидбэка (`"%s::%s" % (name, purpose)`); ребро в SESSION-стор пишется per-mode.
- **как работает:** dating-decline пишет ключ `name::dating` → «avoid» только на dating-ребре; голый legacy-decline (`purpose=None`) остаётся байт-идентичным доменно-агностичным ключом и применяется ко всем режимам. Вход — `(name, decision, purpose)`, выход — bool.
- **ключевые решения:** `purpose=None` сохраняет прежнее поведение (byte-identity legacy); изоляция аддитивна.
- **тесты:** `CP1-ISOLATION`.
- **статус:** done.

#### CP1-PRESENT — §0.5 форма user-facing карточки
- **что требует спека:** карточка несёт ≤3 подтверждённых причины и РОВНО один «gap» (скаляр, не список).
- **что построено:** формирование `reasons_en`/`gap_en` в конвейере карточки (`run`→card-shaping).
- **как работает:** карточка кандидата отдаёт `reasons_en` (list ≤3) и `gap_en` (скаляр/None). Инвариант: gap никогда не список.
- **ключевые решения:** презентация выведена из уже принятых решений, не новый скоринг.
- **тесты:** `CP1-PRESENT`.
- **статус:** done.

#### CP1-LANG — §C.16 гейт requiredLanguages
- **что требует спека:** обязательный язык — жёсткий гейт.
- **что построено:** ветка в `app.py:_hard_gates` (проверка `requiredLanguages` против `c['langs']`).
- **как работает:** кандидат с языком проходит; без него — `(False, "missing a required language")`. Absent-permissive: пустой `requiredLanguages` → пропуск.
- **ключевые решения:** истинное native/learner-различие — это in-engine скоринг (вне scope, см. §18.4 в рычаге C); здесь зафиксирован только гейт присутствия.
- **тесты:** `CP1-LANG`.
- **статус:** partial (гейт done; native/learner — pinned-engine, отложено).

#### CP1-OUTAGE — §C.21 устойчивость к отказу LLM
- **что требует спека:** отказ LLM не отключает гейты и не искажает детерминированный slate.
- **что построено:** гейты/скоринг LLM-независимы; `parse_intent` (`app.py:668`) при исключении LLM падает в `_fallback_parse`.
- **как работает:** при `llm_complete`→RuntimeError жёсткий гейт dating всё равно даёт `(False, "not open to dating")`, а slate байт-идентичен прогону с живым LLM.
- **ключевые решения:** LLM — только untrusted-парсер; вся политика детерминирована.
- **тесты:** `CP1-OUTAGE`.
- **статус:** done.

---

## Батч CP2 — dating-капсула, disclosure-стадии, decay инференса

#### CP2-DATING-CAPSULE — §17.0/§17.1.profile
- **что требует спека:** dating-капсула исключает профессиональные `entities` + сенситив-контур; точный возраст → band без явного согласия.
- **что построено:** `kc.build_dating_capsule` (shared/kleal_contracts.py).
- **как работает:** из юзера строится капсула, где `entities`/`orientation` отсутствуют, `sensitive_excluded=True`, `age`→`age_band` («25-34»); при `consent_exact_age=True` — обратно `age=29`, без band.
- **ключевые решения:** сенситив исключён by construction; коарсенинг возраста — privacy-минимизация.
- **тесты:** `CP2-DATING-CAPSULE`.
- **статус:** done (в рамках аддитивных §17-хелперов; полный §17-wiring — задачи #40/#41 pending).

#### CP2-DISCLOSURE — §17.1.disclosure
- **что требует спека:** поле, помеченное `match_only`, скрыто на `limited_profile`, видно на `match_only`; имя всегда сохраняется.
- **что построено:** `kc.build_profile_view` + `disclosure_field_stages`.
- **как работает:** `interests` с тегом `match_only` отсутствует в `limited_profile`-view, присутствует в `match_only`-view; `name` есть всегда; нефильтрованный view не меняется.
- **тесты:** `CP2-DISCLOSURE`.
- **статус:** done.

#### CP2-DECAY — §19.2 затухание мягкого инференса
- **что требует спека:** мягкий `agent_inference` (L7) теряет confidence с возрастом (~30-дневный half-life); источник выше авторитетом не трогается.
- **что построено:** `kc.build_evidence` + `kc.decay` + `kc.drop_inferred`.
- **как работает:** `decay` на 60d (=2 half-life) даёт `*0.25` (0.8→~0.2); `explicit_stable_profile` (0.9) не меняется; `drop_inferred` удаляет только inferred-строки.
- **ключевые решения:** детерминированная временная функция; никаких данных пилота не требуется.
- **тесты:** `CP2-DECAY`.
- **статус:** done.

---

## Батч CP3 — dating-consent, ML-стабы, доменные паки

#### CP3-CONSENT — §17.1.consent
- **что требует спека:** структурный `dating_consent` (opt_in + target_prefs) появляется ТОЛЬКО после подтверждённого dating-opt-in; никогда не инферится.
- **что построено:** `ki.apply_confirmation` (shared/kleal_intent.py).
- **как работает:** при подтверждении id `dop` (kind `dating_evergreen`) intent→`type=dating`, `dating_consent.opt_in=True`, `target_prefs.minAge=25`; без подтверждения `dating_consent` отсутствует.
- **ключевые решения:** consent — за явным `/confirm`-барьером (§13.3 requires_consent), не инференс.
- **тесты:** `CP3-CONSENT`.
- **статус:** done.

#### CP3-ML-STUBS — §23.4.7 типизированные ML-интерфейсы
- **что требует спека:** ML-интерфейсы объявлены заранее как типизированные стабы, возвращают `absent_by_design`, НИКОГДА не фабрикуют float; инвариант no-model-in-gates держится.
- **что построено:** `shared/kleal_ml_boundary.py` — `feature_vector`, `predict_response`, `predict_acceptance`, `predict_completion`, `model_version`, `assert_no_model_in_gates`, манифест `ML_BOUNDARY`.
- **как работает:** каждый predict-стаб отдаёт `{status:"absent_by_design", probability:None}`; `model_version().scoring=="rule_based_deterministic"`, `.ml=="absent_by_design"`; `assert_no_model_in_gates()==[]` (все 6 политик помечены `model_driven:False`).
- **ключевые решения:** калиброванная вероятность требует данных пилота + версии модели — никогда не подставляется 0.5; keyless, без доступа к модели.
- **тесты:** `CP3-ML-STUBS`.
- **статус:** pilot_disabled (интерфейсы done, модели absent-by-design).

#### CP3-PACKS — §15.4 конкретные доменные паки
- **что требует спека:** доменные паки формируют осуществимые группы при покрытии и отвергают при невыполненном обязательном ограничении.
- **что построено:** `kg.form_group` + `kg.pack_for` + `kg.load_group_params` (shared/kleal_groups.py).
- **как работает:** padel-пак с 4 участниками (racket) → группа; 3 → None; dota role-complete → группа; dota без обязательной роли → None. `enabled_override=True` включает pilot-off-механизм только для теста.
- **ключевые решения:** группы pilot-off by design; форма детерминирована set-constraints.
- **тесты:** `CP3-PACKS`.
- **статус:** pilot_disabled (движок done, флоу выключен).

---

## Батч CP4 — доменные жёсткие слоты, min-duration, зональный opt-in

#### CP4-DOMAIN-SLOT — §18.0/§18.2/§18.5
- **что требует спека:** явный конфликт доменно-критичного слота (server/platform/ticket/industry) — жёсткое исключение; отсутствие слота оставляет ALLOW байт-идентичным.
- **что построено:** `_DOMAIN_CRITICAL_SLOTS` (`app.py:727`) + ветка в `_hard_gates`.
- **как работает:** обе стороны объявили `server` и они различны → `(False, "domain slot mismatch: server")`; кандидат без слота → pass; регистронезависимо («EU» vs «eu» → pass).
- **ключевые решения:** absent-permissive by construction (пул не задет).
- **тесты:** `CP4-DOMAIN-SLOT`.
- **статус:** done.

#### CP4-MIN-DURATION — §18.3
- **что требует спека:** кандидат с окном короче запрошенного минимума исключается; отсутствие — pass.
- **что построено:** ветка `minDurationMin` vs `availableMinutes` в `_hard_gates`.
- **как работает:** `minDurationMin=60`, `availableMinutes=30` → `(False, "window shorter than requested duration")`; 90 → pass; отсутствие поля → pass.
- **тесты:** `CP4-MIN-DURATION`.
- **статус:** done.

#### CP4-ZONE — §8.1 зональный opt-in
- **что требует спека:** кандидат вне радиуса С zone-opt-in → REVIEW (обнаружим, но не proposable); без него — прежний BLOCK.
- **что построено:** ветка `zoneOptIn` в `app.py:_policy_decision`.
- **как работает:** `radiusKm=5`, `km=40`, `zoneOptIn=True` → `REVIEW`; без opt-in → `BLOCK`.
- **ключевые решения:** REVIEW — discovery-only, не даёт personal outreach.
- **тесты:** `CP4-ZONE`.
- **статус:** done.

---

## Батч CP5 — dating без авто-коммита

#### CP5-DATING-NOAUTO — §14.3
- **что требует спека:** dating-intent НЕ авто-коммитит матч на accept партнёра B — держится в `NEEDS_MANUAL_CONFIRM`, не записывается как accepted-match.
- **что построено:** ветка в `app.py:negotiate_candidates` (dating-purpose → hold).
- **как работает:** даже при `negotiate_one→agree:True` и `revalidate→OK` для dating-purpose `SESSION['_matches']` остаётся пустым, а карта несёт `code=="NEEDS_MANUAL_CONFIRM"`.
- **ключевые решения:** §13.3 — «agree_to_dating_contact» в requires_consent; авто-коммит запрещён.
- **тесты:** `CP5-DATING-NOAUTO`.
- **статус:** done.

---

## Батч CP6 — детерминизм переговоров, заморозка весов, идемпотентность, качественный band

#### CP6-NEGOTIATE-DET — §23.2.7
- **что требует спека:** accept/reject-вердикт детерминирован (readiness+score), идентичен при заглушенном LLM; LLM только фразирует reply.
- **что построено:** `app.py:negotiate_one` (1598).
- **как работает:** `avail = readiness=='open_now' or open`; `agree = avail and score>=45`. reply-фразирование в try/except вокруг `llm_complete` — исключение не флипает вердикт. `open_now/score80→True`, `score10→False`, `busy/score90→False`.
- **ключевые решения:** free-text ограничен полем `reply`; verdict replay-стабилен.
- **тесты:** `CP6-NEGOTIATE-DET`.
- **статус:** done.

#### CP6-WEIGHTS-FROZEN — §23.2.11
- **что требует спека:** единственный источник весов — sha-pinned config; рантайм-тюнер заморожен, тело запроса не создаёт второй источник весов.
- **что построено:** `app.py:set_weights` (230) — теперь только read-only echo, `return dict(WEIGHTS)`, без мутации.
- **как работает:** `set_weights({"tier_broad":99999})` возвращает текущие веса и не меняет `WEIGHTS`; `get_weights()` до и после равны.
- **ключевые решения:** запрет «второго скорера» (§23.2.11) → защита byte-identity; обход через оркестрацию нельзя.
- **тесты:** `CP6-WEIGHTS-FROZEN`.
- **статус:** done.

#### CP6-IDEMPOTENT — §23.2.13/§22.2.3
- **что требует спека:** запись, мемоизированная по idempotency-ключу, при повторе возвращает прежний результат (DUPLICATE) без повторного применения side-effect; без ключа — обычный прогон.
- **что построено:** `app.py:_idempotent` (340) + `ks.dedup_key`, стор `SESSION['_write_seen']`.
- **как работает:** первый вызов с ключом `k1` → producer (`n=1`); повтор → `{duplicate:True, error_code:"DUPLICATE", n:1}` без запуска producer; `None`-ключ → producer прогоняется (`n=2`).
- **ключевые решения:** file-backed мемо; falsy-ключ прозрачен.
- **тесты:** `CP6-IDEMPOTENT`.
- **статус:** done.

#### CP6-BAND — §23.2.10
- **что требует спека:** наружу — качественный band, никогда калиброванный compatibility-percent.
- **что построено:** card-shaping (band выставляется, percent-ключей нет).
- **как работает:** карта несёт `band`, но не содержит `compatibility_percent`/`match_percent`/`compatibility`.
- **ключевые решения:** совпадает с коммитом fcdc31b (профиль показывает band, не сырой процент).
- **тесты:** `CP6-BAND`.
- **статус:** done.

---

## Батч CP7 — §21.2 proposal/plan-ресурсы + §23.4.5 reservation

#### CP7-PROPOSAL — §21.2 создание/ответ proposal
- **что требует спека:** create идемпотентен (тот же ключ → тот же `proposal_id`); respond гонит валидированный §14-переход.
- **что построено:** `app.py:proposal_create` (1933), `proposal_respond` (1950); стор `SESSION['_proposal_store']` по `idempotency_key`, индекс `_proposal_by_id`.
- **как работает:** `build_proposal`→state `SENT`; повтор той же (intent,candidate) → тот же id + `duplicate:True` (нет дубль-строки). `respond({action:"WITHDRAW"})` грузит по id, гонит `agent_transition` → `SENT→WITHDRAWN`.
- **ключевые решения:** file-backed персист; переход через §14-примитивы (`ks.next_state`).
- **тесты:** `CP7-PROPOSAL`.
- **статус:** done.

#### CP7-PLAN — §21.2 plan-ресурс с version-check
- **что требует спека:** create → version-checked update поднимает version; устаревший `expected_version` → VERSION_CONFLICT.
- **что построено:** `app.py:plan_resource` (1966); стор `_plan_store`.
- **как работает:** create → `kc.build_plan` (enabled:False, pilot-off), `version=1`; update `to:"PROPOSED", expected_version:1` → `version=2, ok:True`; повторный stale `expected_version:1` → `error_code:"VERSION_CONFLICT"`.
- **ключевые решения:** Plan-стейт-машина pilot-off (`kc.build_plan enabled:False`) — это только аддитивная обвязка ресурса; CAS через `ks.compare_and_swap`.
- **тесты:** `CP7-PLAN`.
- **статус:** partial/pilot_disabled (обвязка done, plan-флоу выключен).

#### CP7-RESERVE — §23.4.5 1:1 reservation
- **что требует спека:** 1:1-резервации переиспользуют §14-примитивы; второй конкурентный клейм → SLOT_TAKEN; истёкший TTL детектируется.
- **что построено:** `ks.claim_slot`, `ks.reservation_expired` (shared/kleal_states.py).
- **как работает:** `claim_slot(led,"i1","a")→won:True`; второй `→won:False, error_code:"SLOT_TAKEN"`; `reservation_expired({created_ts:1000, ttl_seconds:60}, now=2000)→True`.
- **ключевые решения:** cross-request UNIQUE-семантика на stdlib-структуре (single-node пилот).
- **тесты:** `CP7-RESERVE`.
- **статус:** done.

---

## Батч CP8 — §12.1 пошаговое расширение, §21.2 compile/expand

#### CP8-STEPWISE — §12.1
- **что требует спека:** расширение релаксирует РОВНО одну ось за шаг (шаг 2 = только adjacency, НЕ exactMatchRequired); карты помечены истинным `ladder_step`.
- **что построено:** `app.py:_expand_stepwise`.
- **как работает:** возвращает `(cards, step)`; все карты несут `ladder_step==step`; шаг 2 меняет только adjacency, не роняет exactness.
- **тесты:** `CP8-STEPWISE`.
- **статус:** done.

#### CP8-COMPILE — §21.2 `/intents/compile`
- **что требует спека:** один объект, связывающий intent + clarification + minimally_sufficient + snapshot.
- **что построено:** `app.py:compile_endpoint` (2081).
- **как работает:** parse (`parse_intent`) → `kc.compile_intent` → `_section5_addendum`; отдаёт `{intent, draft, slots, intent_summary, clarification, minimally_sufficient, snapshot}` за один round-trip.
- **тесты:** `CP8-COMPILE`.
- **статус:** done.

#### CP8-EXPAND — §21.2 `/searches/{id}/expand`
- **что требует спека:** применяет РОВНО одну объявленную ось (adjacent) — репортит единственный изменённый ключ и шаг лестницы; не роняет exactness вместе.
- **что построено:** `app.py:expand_one_axis` (2093), карта `_AXIS`.
- **как работает:** `axis:"adjacent"` → `changed_keys==["adjacentAllowed"]`, `ladder_step==2`, кандидаты пересчитаны на `relaxed` intent; safety/age/consent зафиксированы.
- **ключевые решения:** одна ось за раз (не как двойной `_expand_fallback`).
- **тесты:** `CP8-EXPAND`.
- **статус:** done.

---

## Батч CP9 — §21.4 health, §23.4.2 policy-facade, §22.2.0 registry, §23.4.1 schema

#### CP9-CONFIG-HEALTH — §21.4 SLA/alerting
- **что требует спека:** снапшот запроса раскрывает config-health для SLA/алертинга.
- **что построено:** `app.py:_request_snapshot` (615), блок `config_health`.
- **как работает:** снапшот несёт `config_health={core_v2, error, group_drift, degraded}`; при здоровом конфиге `core_v2:True`, `degraded:False`.
- **ключевые решения:** health выводится из уже загруженного pinned-конфига (`_CORE_CFG`, `_CORE_ERR`, `_GROUP_CFG_PROBLEMS`), конфиг не мутируется.
- **тесты:** `CP9-CONFIG-HEALTH`.
- **статус:** done.

#### CP9-EVAL-POLICY — §23.4.2 унифицированный policy-фасад
- **что требует спека:** единый типизированный facade воспроизводит per-gate-вердикт байт-в-байт.
- **что построено:** `app.py:evaluate_policy` (800).
- **как работает:** прогоняет стек ПО ПОРЯДКУ (`_hard_gates`→`_cross_purpose_blocked`→`_policy_decision`→`_revalidate_disclosure`), отдаёт один объект `{decision, reason, eligible, gate_reason, cross_purpose_blocked, disclosure, policy_version}`. Dating без opt-in → BLOCK; чистый кейс → совпадает с `_policy_decision`.
- **ключевые решения:** НЕ добавляет поведения — только унифицирует поверхность.
- **тесты:** `CP9-EVAL-POLICY`, `CP10-DATING-CONTOUR`.
- **статус:** done.

#### CP9-REGISTRY — §22.2.0 stage-0 манифест
- **что требует спека:** stage-0-манифест перечисляет каждый §4-builder сущности + версии config/contract/state.
- **что построено:** `shared/kleal_contract_registry.py:manifest` + `ENTITY_BUILDERS`.
- **как работает:** `manifest(cfg)` отдаёт `registry_version`, `contracts_version`, `states_version`, `config_version/_sha[:12]`, `entities` (11 builder-ов: evidence, profile_view, receiving_policy, intent, candidate_snapshot, proposal, reservation, match, group, plan, relationship_edge), `state_machines`, `proposal_types`, `contexts`.
- **ключевые решения:** контракты authored BEFORE engine — машинно-проверяемо; keyless, без FS/модели.
- **тесты:** `CP9-REGISTRY`.
- **статус:** done.

#### CP9-SCHEMA — §23.4.1 draft-07 зеркало контракта
- **что требует спека:** проекция `build_profile_view` валидируется против schema-mirror; поле вне allow-list контекста ловится.
- **что построено:** `kleal_contract_registry.py:contracts_schema` + `validate_profile_view`; файл `config/schema.json`.
- **как работает:** схема выведена из ТЕХ ЖЕ allow-list-ов, что использует движок (`kc.PURPOSE_FIELDS/DISCLOSURE_STAGES/CONTEXTS`); валидный friendship-view проходит (`[]`), а подсунутый `datingOk` (вне friendship allow-list) даёт непустой список проблем.
- **ключевые решения:** контракт машинно-проверяем, не проза; single source of truth = те же allow-list.
- **тесты:** `CP9-SCHEMA`.
- **статус:** done.

---

## Батч CP10 — §1.1/§1.0b/§17.1/§18.1/§21/§23/§B.1/§C.17/§D.0

#### CP10-MERGE — §1.1 intent_to_intent
- **что требует спека:** слияние условий двух intent — пересечение тем + общее время; нет общей темы → not feasible.
- **что построено:** `app.py:merge_conditions` (1994).
- **как работает:** `topics = ta∩tb` (sorted), `feasible=bool(topics)`, `time` только если совпадает, `roles=[a.role,b.role]`. `["coffee","books"]∩["coffee","games"]→["coffee"]`; несовпадающие темы → `feasible:False`.
- **тесты:** `CP10-MERGE`.
- **статус:** done.

#### CP10-PLAN-COORD — §21.1 Plan Coordinator
- **что требует спека:** пересекающиеся intent → конкретный `build_plan` (enabled:False); нет общей темы → нет плана.
- **что построено:** `app.py:coordinate_plan` (2004).
- **как работает:** через `merge_conditions`; при feasible собирает `time_block`+public place+участников → `kc.build_plan` (`enabled:False`, `decision_type:"plan"`); нет общей темы → `plan:None`.
- **ключевые решения:** только вычисление; персист — инфра; plan pilot-off.
- **тесты:** `CP10-PLAN-COORD`.
- **статус:** pilot_disabled.

#### CP10-COMPLETION — §1.0b двусторонний confirm
- **что требует спека:** завершённое взаимодействие требует ДВУСТОРОННЕГО подтверждения; одна сторона (даже повторно) не завершает.
- **что построено:** `app.py:confirm_completion` (2016); стор `_completion_confirms`.
- **как работает:** пишет per-party флаг; `completed_ts` в `_matches` ставится только когда `a AND b`. `a`→False, `a` снова→False, `b`→True, `completed_ts` установлен. Молчание одной стороны никогда не завершает и никогда не негатив.
- **ключевые решения:** success = completed two-sided, не клик/impression.
- **тесты:** `CP10-COMPLETION`.
- **статус:** done.

#### CP10-RUNTRACE — §23.4.8 bounded run-trace
- **что требует спека:** каждый прогон добавляет извлекаемый decision-trace в ограниченный стор.
- **что построено:** `app.py:_append_run_trace` (2047); `SESSION['_run_traces']` (bounded 200).
- **как работает:** аппендит `{intent_id, intent_version, config_version}`, возвращает длину; два прогона → 1,2; список сохраняется file-backed.
- **тесты:** `CP10-RUNTRACE`.
- **статус:** done.

#### CP10-REDACT — §17.1.explanation
- **что требует спека:** сенситивная dating-причина редактируется в грубую публичную для dating-домена; вне dating — без изменений.
- **что построено:** `app.py:_redact_dating_reason` (1989) + карта `_DATING_REDACT`.
- **как работает:** для `domain=="dating"`: «not open to dating»→«no longer available»; для `social_meet` — без изменений; несенситивная «good fit» — без изменений.
- **ключевые решения:** owner-only surfaces сохраняют детали; редакция только для не-владельца в dating.
- **тесты:** `CP10-REDACT`.
- **статус:** done.

#### CP10-DOMAIN-LADDER — §18.1 доменная лестница
- **что требует спека:** walk-intent получает walk-специфичный порядок fallback, отличный от generic.
- **что построено:** `app.py:domain_ladder` (2076) + `_DOMAIN_LADDER` (games/walk/language_exchange/professional_networking).
- **как работает:** через `_core.infer_domain`; walk → `["same area/time","another zone/time","small group"]`; неизвестный домен → generic `["broaden topic","widen zone/time","alternative"]`. Read-only план — generic-лестница всё равно исполняется.
- **тесты:** `CP10-DOMAIN-LADDER`.
- **статус:** done.

#### CP10-DTRACE — §21.3 унифицированный decision-trace
- **что требует спека:** единый trace несёт search_id/candidate_id/purpose_id/policy.version/model_versions.
- **что построено:** `app.py:_decision_trace` (2036).
- **как работает:** детерминированные id через `kc._det_id`; `model_versions={scoring:"rule_based_deterministic", llm:"parse_only"}`; `policy.version` из снапшота.
- **ключевые решения:** LLM = parse-only; всё derived из снапшота.
- **тесты:** `CP10-DTRACE`.
- **статус:** done.

#### CP10-PIPELINE — §B.1 provenance-обёртка
- **что требует спека:** search-pipeline-обёртка возвращает ТЕ ЖЕ карты байт-идентично + provenance-tier-trace.
- **что построено:** `app.py:_search_pipeline` (2059).
- **как работает:** read-only проход по уже размеченному slate под высоким retrieval-бюджетом; отдаёт `cards` (те же) + `trace={tiers, strong_count(T0+T1), enough_strong, budget, used, broke_early}`. Никого не пере-скорит и не роняет.
- **ключевые решения:** byte-identity slate — ключевой инвариант.
- **тесты:** `CP10-PIPELINE`.
- **статус:** done.

#### CP10-CAPSULE — §21.1 disclosed match-capsule
- **что требует спека:** disclosed-view purpose-bound: friendship-капсула опускает `datingOk`, dating-капсула опускает профессиональные `entities`.
- **что построено:** `app.py:match_capsule_disclosed` (2031) → `kc.build_profile_view` per участник.
- **как работает:** `social_meet`-капсула не содержит `datingOk`; `dating`-капсула не содержит `entities`.
- **тесты:** `CP10-CAPSULE`, `CP10-D0`.
- **статус:** done.

#### CP10-DATING-CONTOUR — §0.8 gated-контур
- **что требует спека:** dating — gated-контур: нет `datingOk`→BLOCK; `datingOk+verified`→ALLOW (opt-in + release gate).
- **что построено:** через `evaluate_policy` + `_policy_decision` release-gate (`app.py:795`).
- **как работает:** dating без datingOk → BLOCK; с datingOk+verified → ALLOW.
- **тесты:** `CP10-DATING-CONTOUR`.
- **статус:** done.

#### CP10-C17 — §C.17 target-role от кандидата
- **что требует спека:** целевая роль матчится от КАНДИДАТА vs intent, не от собственной профессии инициатора.
- **что построено:** логика ранжирования (роль читается из кандидата).
- **как работает:** порядок кандидатов идентичен при двух разных self-профессиях инициатора (founder vs designer).
- **тесты:** `CP10-C17`.
- **статус:** done.

#### CP10-D0 — §D.0 purpose-binding матрица
- **что требует спека:** dating опускает профессиональные `entities`, friendship опускает `datingOk`, networking сохраняет `entities`.
- **что построено:** `kc.build_profile_view` + `PURPOSE_FIELDS`/`DOMAIN_TO_CONTEXT`.
- **как работает:** dating-view без `entities`; social_meet-view без `datingOk`; professional_networking-view с `entities`.
- **тесты:** `CP10-D0`.
- **статус:** done.

#### CP10-DOD — §23.3 (subset) Definition-of-Done поверхность
- **что требует спека:** снапшот штампует policy_version + decision_type; записи поддерживают идемпотентность.
- **что построено:** `_request_snapshot` (policy_version="policy-2.0.0", decision_type), идемпотентность через `_idempotent`.
- **как работает:** снапшот несёт `policy_version` и непустой `decision_type`; идемпотентность доказана `CP6-IDEMPOTENT`.
- **тесты:** `CP10-DOD` (+ CP6-IDEMPOTENT).
- **статус:** done.

---

## §21–23 — API-ресурсы, observability, registry (сводно)

- **§21.1 Match-orchestrator / Plan-coordinator / Match-capsule builder** — `coordinate_plan`, `match_capsule_disclosed`, proposal/plan-сторы в SESSION (`_proposal_store`/`_plan_store`/`_matches`). Персист file-backed (single-node пилот). Тесты: CP7-*, CP10-PLAN-COORD/CAPSULE. Статус: done (durable multi-pod — рычаг A, отложено).
- **§21.2 ресурсные эндпоинты** — `proposal_create`/`proposal_respond`/`plan_resource`/`compile_endpoint`/`expand_one_axis`. Идемпотентность create, version-check update, one-axis expand. Тесты: CP7-*, CP8-*. Статус: done.
- **§21.3 unified decision trace** — `_decision_trace`. Статус: done.
- **§21.4 health/SLA** — `config_health` в `_request_snapshot`; async-search/`<2s ack`/notification-retry — рычаг A (worker), pending. Тесты: CP9-CONFIG-HEALTH. Статус: partial.
- **§22.2.0 contract registry** — `kleal_contract_registry.manifest`. Тесты: CP9-REGISTRY. Статус: done.
- **§22.2.3 idempotency** — `_idempotent`. Тесты: CP6-IDEMPOTENT. Статус: done.
- **§23.2.7/.10/.11/.13** — детерминизм negotiate, band-не-percent, freeze-весов, idempotent-writes. Тесты: CP6-*. Статус: done.
- **§23.4.1 schema mirror** — `contracts_schema`/`validate_profile_view` + `config/schema.json`. Тесты: CP9-SCHEMA. Статус: done.
- **§23.4.2 policy facade** — `evaluate_policy`. Тесты: CP9-EVAL-POLICY. Статус: done.
- **§23.4.5 reservations** — `ks.claim_slot`/`reservation_expired`. Тесты: CP7-RESERVE. Статус: done.
- **§23.4.7 ML-стабы** — `kleal_ml_boundary`. Тесты: CP3-ML-STUBS. Статус: pilot_disabled.
- **§23.4.8 run-trace** — `_append_run_trace`. Тесты: CP10-RUNTRACE. Статус: done.

## Доработки §0–§3 / §18–§20 (сводно)

- **§0.5 презентация карточки** — ≤3 reasons + single scalar gap. Тест: CP1-PRESENT. Done.
- **§0.8 dating-контур** — gated. Тест: CP10-DATING-CONTOUR. Done.
- **§0 output-table allocation_action** — `app.py:_allocation_action` (typed действие из уже принятых решений: review_required/propose/discovery_expanded/discovery_only). Done.
- **§1.0b two-sided completion** — `confirm_completion`. Тест: CP10-COMPLETION. Done.
- **§1.1 intent_to_intent merge** — `merge_conditions`. Тест: CP10-MERGE. Done.
- **§17.1 disclosure/consent/explanation/profile** — `build_dating_capsule`, `build_profile_view`, `apply_confirmation`, `_redact_dating_reason`. Тесты: CP2-*/CP3-CONSENT/CP10-REDACT. Done (полный §17-wiring #40/#41 — pending).
- **§17.2 isolation** — per-purpose feedback-ключ. Тест: CP1-ISOLATION. Done.
- **§18.0/.2/.3/.5 domain-slots + min-duration** — `_DOMAIN_CRITICAL_SLOTS`, min-duration-гейт. Тесты: CP4-DOMAIN-SLOT/MIN-DURATION. Done.
- **§18.1 domain-ladder** — `domain_ladder`. Тест: CP10-DOMAIN-LADDER. Done.
- **§18.4 complementarity (learner↔native)** — рычаг C (правка sha-pinned движка, готовит Dev B). Статус: partial/blocked-on-owner.
- **§19.2 decay** — `kc.decay`/`drop_inferred`. Тест: CP2-DECAY. Done.
- **§19.0/§19.3 калиброванные модели/feedback-bias** — рычаг D/B (данные пилота + exploration_quota dormant). Статус: pilot_disabled.
- **§20 metrics/staged-validation** — `_success_metrics`, `_match_capsules`; полный `/status`-дашборд + staged-validation — рычаг A/B, pending. Статус: partial.

## Итоговый статус раздела

- **Закрыто чисто (done):** подавляющее большинство CP1–CP10 подпунктов (изоляция, disclosure, decay, consent, domain-slots, min-duration, zone, dating-noauto, negotiate-det, weights-frozen, idempotent, band, proposal/plan/reserve, compile/expand/stepwise, config-health, eval-policy, registry, schema, merge, completion, run-trace, redact, domain-ladder, dtrace, pipeline, capsule, contour, C17, D0, DoD).
- **pilot_disabled (движок есть, флоу выключен by design):** ML-модели (§10.3/§23.4.7), группы (§15.4), plan-флоу (§21.1), calibrated feedback (§19).
- **partial / уперто во внешнее:** native/learner complementarity (§18.4, рычаг C — владелец движка); durable multi-pod persistence, async-search, real transport, metrics-дашборд (рычаг A/D); native/learner in-engine scoring (§C.16). Roadmap этих остатков — `docs/ROADMAP_REMAINING_33_RU.md` (честный остаток ~7 уперты во внешнее: transport-провайдер+деньги, ANN/geo-индексы, calibrated-ML на данных пилота, юр./DPIA sign-off + модерация).
- **Инварианты соблюдены во всех правках:** keyless/LLM-free, sha-pinned `core_v2`+config не тронуты, person-slate байт-идентичен, детерминизм (double-run), всё локально — ничего не задеплоено.

---
