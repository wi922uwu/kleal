# Matching Core — полное описание работы

Документ описывает **фактическое** поведение матчинга в этом репозитории (ветка `feat/microservices-split`),
строго по коду `services/matching/core_v2.py`, `services/matching/app.py` и
`config/Kleal_Matching_Core_Config_v2.yaml`. Только то, что реализовано и исполняется. Разделено на:

- **Движок** — `core_v2.py` (35f8e984), sha-pinned, детерминированный, без LLM. Считает скоринг ALLOW-кандидатов.
- **Обвязка** — `app.py`: политика-гейты (§8), ретрив (§7), аллокация (§11), контракты (§4) вокруг движка.

Активный путь — `KLEAL_CORE_V2=1` (по умолчанию включён). При `KLEAL_CORE_V2=0` или невалидном конфиге
работает легаси-скорер v1 (см. §18 ниже) — это откат, не основной режим.

---

## 1. Инварианты (что гарантируется кодом)

1. **100% детерминизм.** Нет `random`, нет обращения к LLM в скоринге. При фиксированном `ctx.now` и пуле —
   один и тот же слейт байт-в-байт (двойной прогон совпадает). LLM участвует ТОЛЬКО на краях (парсинг
   free-text запроса и agent-negotiate top-кандидатов) — не в ранжировании.
2. **`semantic_tier` — это провенанс, НЕ score.** Тир (T0–T5) отражает, *как* кандидат найден (по совпадению
   тем/взаимности), и никогда не выводится из числового relevance. (`core_v2.py:10`, `score_semantics` в конфиге.)
3. **`unknown` ≠ match.** Незаполненный признак даёт доменный `unknown_prior` и **снижает coverage**, поэтому
   разреженный профиль не может «тихо» обойти подтверждённый. (`directional_score`, `core_v2.py:340`.)
4. **`not_applicable` исключается из знаменателя** — не понижает coverage (онлайн-интент → гео не применимо и т.п.).
   (`core_v2.py:337`.)
5. **Веса/приоры/пороги живут ТОЛЬКО в sha-pinned YAML.** В `core_v2.py` нет тюнимых relevance-чисел, кроме
   observed-value якорей (`SEM_VALUE`, `GEO_BANDS`). Рантайм-тюнер `/api/agent/weights` заморожен (read-only).
6. **Feedback не меняет relevance.** История accept/reject — это гейт/лернинг, не модификатор скоринга.
7. **Scoring только после ALLOW.** Хард-гейты политики (§8) отсекают неподходящих ДО скоринга; движок видит
   только eligible-пул.

---

## 2. Конфиг (`config/Kleal_Matching_Core_Config_v2.yaml`)

- **sha-pinned**: `PINNED_SHA = 21505ccb4add…` (`core_v2.py:31`). `load_config` считает sha256 файла и при
  несовпадении бросает `ConfigError` → обвязка падает на легаси (спека §21.4: «config mismatch → stop, don't mix»).
- **Парсер — свой мини-YAML** (`parse_mini_yaml`, `core_v2.py:57`): поддерживает вложенные map, списки скаляров,
  скаляры. Без PyYAML — чтобы (а) не тянуть зависимость на под, (б) не словить YAML-1.1 сюрприз (неквотированный
  `09:00` иначе читается как 540).
- **Валидация при загрузке** (`load_config`, `core_v2.py:100`): `config_version` обязателен; у всех 7
  feature-групп `unknown_prior` ∈ [0,1]; у каждого домена веса — только из 7 канонических ключей и **сумма = 1.0**
  (±1e-6); `uncertainty_lambda`, пороги outreach/discovery ∈ [0,1]; секции `semantic_tiers` и `user_facing_bands`
  присутствуют. В валидный cfg дописывается `cfg["_sha256"]`.

Секции конфига (всё, что реально читается движком):

| секция | что задаёт |
|---|---|
| `config_version` | `matching-core-2.0.0` |
| `currency_or_paid_priority` | `ranking_boost_allowed: false` — подписка не влияет на relevance/eligibility/safety |
| `feature_groups` (7) | диапазон и `unknown_prior` каждой группы (0.4–0.5) |
| `domains` (10) | по домену: `weights` (сумма 1.0), `uncertainty_lambda`, 4 порога outreach/discovery |
| `semantic_tiers` (T0–T5) | права: `personal_outreach` / `discovery` по тиру |
| `outreach` | параллельные предложения, лимиты 24h/7d, TTL, тихие часы, волны |
| `group_formation` | размеры 3–8, кворум, веса utility (§15) |
| `user_facing_bands` (4) | пороги `min_lcb`/`min_coverage` для бэндов |
| `score_semantics` | текстовые инварианты (score ≠ процент совместимости, tier ≠ из score) |

**10 доменов**: `social_meet, walk, games, language_exchange, sport_activity, culture_event,
professional_networking, watch_together, coworking, dating` (`core_v2.py:387 ALL_DOMAINS`). У `dating` —
`release_gate: separate_safety_legal_track` (см. §4 REVIEW).

---

## 3. Пайплайн end-to-end (`match_candidates`, `app.py:1253`)

Порядок ровно такой (шаги 2–3, 7, 10–14 — обвязка/спринт; шаг 8 — sha-pinned движок):

1. `if not CORE_V2:` → легаси-скорер (§18).
2. `ki.normalize_for_scoring(intent)` — §5 нормализация недоверенного ввода (идемпотентно).
3. **Lifecycle §4.3**: `kc.is_expired(intent, now)` → `[]` если интент протух; `kc.compile_intent(...)` —
   канонические блоки + TTL.
4. `gate_ctx, self_name = _gate_ctx_and_self(ctx, prof)` — контекст гейтов (blocked-set, feedback) + имя искателя.
5. **Хард-гейты §8**: по каждому из `load_candidates()`: пропустить себя; `_policy_decision` → `BLOCK` пропускаем,
   иначе кладём в `eligible` и запоминаем `policy_by[name] = ALLOW|REVIEW`.
6. Пин `ctx.now` (детерминизм) + `received24` (счётчики усталости от предложений → readiness).
7. **Ретрив §7**: `_retrieve(intent, eligible, budget)` → `retrieved` пул + `source_by`. Бюджет по умолчанию 500.
8. **Скоринг**: `slate, _meta = _core.search(intent, prof, ctx, retrieved, _H, _CORE_CFG)` — сердце (см. §7–§13 ниже).
9. **Never-empty §12**: если `slate` пуст, а `eligible` не пуст → `_expand_fallback(...)` по ПОЛНОМУ пулу.
10. `_apply_policy(slate, policy_by)` — штампует `policy` (ALLOW/REVIEW), `allocation_action`, `decision_class`;
    REVIEW → `can_outreach=False`.
11. `_allocate(slate, ctx, retrieved)` — §11 аллокация (на пилотных дефолтах DORMANT — трейс есть, поведение не меняет).
12. `_stamp_contracts(slate, intent, ctx)` — §4 оверлеи: purpose-bound `profile_view`, версионированный
    `snapshot`, парный `relationship` (per-card, ошибка одного не роняет слейт).
13. `retrieval_source` провенанс на каждую карту (§7.1).
14. `_stamp_allocation_trace(...)` — §11.2 read-only причины аллокации.
15. `return slate`.

`_H` (инъекция таксономии в движок, `app.py:1030`):
`{'topical': topical, 'cat_of': cat_of, 'reciprocal': _reciprocal, 'role_conflict': ROLE_CONFLICT}` — движок
не знает про таксономию, обвязка передаёт свои функции, чтобы источник таксономии был один.

---

## 4. Хард-гейты и трёхзначная политика §8 (`app.py`)

`_hard_gates(intent, c, gate_ctx)` (`app.py:729`) — дешёвые детерминированные исключения ДО скоринга,
возвращает `(ok, reason)`. Проверки по порядку:

- `paused` → «on a break»; в blocked-set или `blocksMe` → «blocked»;
- `declinedOwnerDaysAgo < COOLDOWN_DAYS (=7)` → «recently declined (cooldown)»;
- `pending >= MAX_PENDING (=6)` → «too many open invites»;
- `age < MIN_AGE (=18)` → «under 18»;
- `type=dating` и `!datingOk` → «not open to dating»;
- `verifiedOnly` и `!verified` → «not verified»;
- `minAge/maxAge`: нет возраста → «age unknown»; вне диапазона → «below/above age range»;
- `requiredLanguages` не ⊆ языков кандидата → «missing a required language»;
- `mode=offline` и `km > radiusKm` → «outside the radius».

**§8.1 доп. канонические гейты** (дописаны последними, срабатывают ТОЛЬКО при наличии ограничительного значения —
поэтому на фикстурах без этих полей слейт байт-идентичен):
- `accountStatus ∈ {suspended,deactivated,banned,deleted}` или `suspended=True` → «account not active»;
- `visibility=private` → «private profile»;
- `safetyFlags ∩ {banned,csam_block,legal_hold,restricted}` → «safety restriction»;
- **§18** доменные критические слоты `{server,platform,ticket,industry}`: если ОБА (интент и кандидат) заявили слот
  и они различаются → «domain slot mismatch»;
- `minDurationMin > availableMinutes` → «window shorter than requested duration».

`_policy_decision` (`app.py:773`) — **трёхзначный** вердикт (не boolean):
- **BLOCK** — жёсткое исключение (не скорится, не показывается);
- **REVIEW** — виден в discovery, но НЕ авто-предлагается; должен пройти отдельный safety/legal-трек. Кейсы:
  cross-purpose-изоляция; `sensitivity=restricted` / `safetyFlags` содержит `review`; домен с
  `release_gate=separate_safety_legal_track` и `!verified` (напр. dating unverified); а также §8.1 «soft»-семантика
  (`soft_eligibility`/`zoneOptIn`) для «age unknown»/«outside radius» → REVIEW вместо BLOCK.
- **ALLOW** — чист для скоринга и личного аутрича.

`evaluate_policy` (`app.py:800`) — единый типизированный фасад (§23.4.2): прогоняет тот же стек по порядку и
возвращает `{decision, reason, eligible, gate_reason, cross_purpose_blocked, disclosure, policy_version}`.
Нового поведения не добавляет — только унифицированная поверхность. (Именно это зовёт 3-колоночный стенд
для панели причин исключения.)

---

## 5. Ретрив §7 (`app.py`)

`RETRIEVAL_BUDGET = {"prefilter":500, "structured":500}` (`app.py:1157`).

**5 источников** (`RETRIEVAL_SOURCES`, `app.py:1172`): 1 `active_intent_match`, 2 `active_receiving_direct_interest`,
5 `parent_adjacent_expansion` — **включены**; 3 `groups_with_capacity`, 4 `events_and_rooms` — **declared, но
pilot-disabled** (не-пилотные типы решений; возвращают 0 кандидатов, не фейкаются).

**7 стадий** (`RETRIEVAL_STAGES`, `app.py:1160`), честно помеченные:
`hard_prefilter` (in-memory гейты+гео; SQL/PostGIS/H3 = infra, отложено) → `structured_retrieval` (taxonomy
overlap + active intents, по источникам, обрезка бюджетом) → `ann_recall` (pgvector — **infra, нет в
stdlib-прототипе**, `status: blocked_infra`) → `feature_build` (`core_v2.build_features`) → `ranking_slate`
(`core_v2` + `_slate`) → `explanation` (reason-ключи → NL) → `agent_probe` (negotiate top 1–3, LLM small).

`_retrieve(intent, eligible, budget)` (`app.py:1200`): каждому eligible-кандидату присваивает §7.1 источник
(`_retrieval_source`: 1 reciprocal, 2 `best>=4`, 5 `best 1–3`, 0 нет пересечения), сортирует по приоритету
(`_SOURCE_RANK`: 1→2→5→0), обрезает бюджетом. **Порядок ретрива не влияет на видимый слейт** (движок полностью
пересортирует), а обрезка режет только «no-overlap хвост», который движок и так дропает (T5) — поэтому для любого
eligible-пула ≤ бюджета слейт байт-идентичен.

---

## 6. Определение домена (`infer_domain`, `core_v2.py:146`)

`type=dating` → `dating`; ключевые слова в topics/title: walk/прогул → `walk`, cowork/поработ → `coworking`,
watch/смотреть → `watch_together`; иначе `_TYPE2DOMAIN` (gaming→games, sport→sport_activity, networking→
professional_networking, language→language_exchange); иначе по broad-категории первого топика (`_BROAD2DOMAIN`);
дефолт `social_meet`. Домен выбирает набор весов и порогов.

---

## 7. Модель признаков §6 (`build_features`, `core_v2.py:199`)

**7 групп признаков × 4 состояния.** Состояния: `known_match`, `known_mismatch`, `unknown`, `not_applicable`
(`core_v2.py:167`). По одной агрегированной подфиче на группу; алиас/родитель одного интереса схлопываются в один
matched-набор (без двойного счёта).

1. **`semantic_activity`** — тир совпадения тем через инъектированный `topical` (см. §10). `best>=1` → `known_match`
   со значением `SEM_VALUE = {4:1.0, 3:0.65, 2:0.45, 1:0.25}`; `best=0` → `known_mismatch` (0.05); нет тем/интересов
   → `unknown`.
2. **`time_feasibility`** — единственный живой сигнал сейчас: флаг `open`. `open=True` → match (0.85 если время
   задано, иначе 0.7); `open=False` при заданном времени → mismatch (0.25); иначе `unknown` (не «тихий» матч).
3. **`location_feasibility`** — расстояние ОТНОСИТЕЛЬНО искателя (haversine по coarse-гео, иначе поле `km`).
   `mode=online` → `not_applicable` (исключается из знаменателя). Гео-полосы `GEO_BANDS`:
   ≤1.5км→1.0, ≤3.5→0.85, ≤7→0.65, ≤15→0.45, иначе 0.15; ≥0.45 = match, иначе mismatch.
4. **`mode_format`** — если кандидат не задал форматы → `unknown` (не предполагаем совместимость); совпало → 1.0.
5. **`directed_preferences`** — только если интент реально таргетит роль (не `meet`). Совпало → 1.0; конфликт
   ролей (`ROLE_CONFLICT`) → mismatch 0.15; иначе мягкий match 0.55; нет роли у кандидата → `unknown`;
   роль `meet`/пусто → `not_applicable`.
6. **`social_context`** — вайб. Совпал → 1.0; клэш (`VIBE_CLASH`: chill↔party, calm↔energetic, introvert↔extrovert,
   competitive↔chill, calm↔competitive) → mismatch 0.25; иначе мягкий 0.55; нет вайба → `unknown`.
7. **`domain_constraints`** — обязательные поля домена: для `language_exchange` — совпадение языковой пары; при
   заданных `requiredLanguages` — match (хард-гейт уже отсёк реальные несовпадения); для games/sport — общая
   entity/community; иначе `not_applicable`.

`reverse_features` (`core_v2.py:315`) — то же, но B→A: подходит ли ИСКАТЕЛЬ под то, что заявил кандидат. Сильнейший
сигнал — собственный активный интент кандидата; иначе его интересы как standing-предпочтения. Разреженные данные
кандидата → низкий reverse-coverage → консервативный reciprocal.

---

## 8. Направленный скоринг §9 (`directional_score`, `core_v2.py:327`)

Для домена берутся веса `W` и `λ = uncertainty_lambda`. По 7 группам (с весом > 0):
- `not_applicable` → пропуск (вне знаменателя);
- `unknown` → в числитель идёт `w · unknown_prior`, вес добавляется в total, но НЕ в known;
- иначе → `w · value` в числитель, вес в known.

Итог:
```
mean     = Σ(w·v) / Σw_total          # взвешенное среднее relevance
coverage = Σw_known / Σw_total        # доля веса, подкреплённого известными фактами
lcb      = clamp(mean − λ·(1 − coverage), 0, 1)   # консервативная нижняя граница
```
`lcb` — то, что показывается как **score = round(lcb·100, 1)**. Это внутренняя эвристика, НЕ процент совместимости.

---

## 9. Реципрокность §9.4 (`reciprocal_score`, `core_v2.py:352`)

По консервативным оценкам обеих сторон:
```
reciprocal = 0.7·min(lcb_A, lcb_B) + 0.3·mean(lcb_A, lcb_B)
```
Штрафует однобокие пары (сильный интерес одной стороны при слабом другой). Это ключ сортировки слейта (см. §13).

---

## 10. Тиры §7 (`assign_tier`, `core_v2.py:358`) + таксономия

`topical(topics, interests)` (`app.py:147`) → `(best, matched)`, где `best`: 4 = точное/алиас, 3 = та же
подкатегория, 2 = та же broad-категория, 1 = смежная (по `ADJACENCY`), 0 = нет. Off-taxonomy строки
(«labubu», «рыбалка») матчатся литеральным общим словом (`_wshare`). `cat_of` (`app.py:117`) — только точное
совпадение словаря или префикс ≥5 (никаких сырых подстрок: нет «art» в «party»).

`assign_tier`:
- `reciprocal(intent, cand)` (у кандидата свой активный интент совпал по под-кат/точно) → **T0**;
- иначе по `best`: `>=4`→**T1**, `2..3`→**T2**, `1`→**T3**, `0`→**T5**.
- **T4** назначается не здесь, а на fallback-пути (§12, «alternative solution»).

`TIER_KIND = {T0:reciprocal, T1:exact, T2:related, T3:adjacent}` → поле `kind` на карте.

**Тир делает три вещи** (в `search`, `core_v2.py:561`):
1. **Провенанс-ярлык** (`tier`+`kind`) — почему человек тут.
2. **Жёсткий фильтр видимости**: `T5` — всегда `continue`; `T3` — `continue` если `adjacentAllowed=false`;
   `T2` — `continue` если `exactMatchRequired`; слабый И косвенный (не T0/T1, ниже discovery-порогов) — `continue`.
3. **Права на аутрич** (config `semantic_tiers`): `outreach_tier_ok = tier∈{T0,T1}` или `T2 + broadConsent`.
   `can_outreach = outreach_tier_ok AND readiness=open_now AND lcb>=outreach_min_lcb AND coverage>=outreach_min_coverage`.
   T3/T4 — только discovery, личный аутрич запрещён. (Это и есть чип `no_personal_outreach` у обвязки, §11.)

---

## 11. Готовность приёма §10.1 (`readiness_state`, `core_v2.py:427`)

Отвечает «можно ли обратиться к человеку СЕЙЧАС для этой цели» — и НИКОГДА не подмешивается в relevance
(это ordering + статус доступности). Состояния (`READINESS_LABELS`): `open_now, open_later (тихие часы),
passive_discovery (только в подборке), busy, paused, unknown`. `paused`-люди **вообще уходят из ретрива**.

Источники по приоритету: канонический §4.4 `receiving`-объект пользователя → иначе демо-флаг `open` как явный
сигнал → иначе `unknown` (и unknown ≠ открытость: без политики/пробы личного аутрича нет). Учитываются:
`status=busy`; усталость (`received_24h >= cap`, cap из `proposal_budget.per_24h` или конфига 4) → busy;
`allowed_domains` не содержит домен → passive_discovery; тихие часы (`quiet_hours`, дефолт 22:00–09:00, с
`tz_offset_min`) → open_later; `passive_outreach=False` → passive_discovery.

---

## 12. Пользовательские бэнды §9.7 (`assign_band`, `core_v2.py:470`)

Из `lcb` + `coverage` по порогам `user_facing_bands` (по убыванию):
- `especially_close` — lcb≥0.78, cov≥0.75;
- `strong_option` — lcb≥0.66, cov≥0.6;
- `broader_option` — lcb≥0.52, cov≥0.4;
- иначе `needs_clarification`.

`BAND_LABELS` дают RU/EN текст. Бэнд — это «насколько сильное совпадение», в отличие от тира («какого рода») и
score («сырое число»). Прямые T0/T1, не прошедшие discovery-пороги, остаются видимыми как `needs_clarification`.

---

## 13. Слейт и аллокация §11 (`_slate`, `core_v2.py:530`)

Внутри `search` карты сортируются ключом:
```
(BAND_RANK, READINESS_RANK, −reciprocal, −lcb, −coverage, name)
```
т.е. сначала бэнд, потом класс готовности (ordering, не relevance!), затем реципрокная релевантность, затем lcb,
coverage, и наконец имя — **стабильный тай-брейк** (детерминизм).

`_slate` (диверсификация §11): `TOP_N=8`, `PER_BUCKET=3`. Если бакетов (категорий) > 2 — не больше 3 из одного
бакета; если ≤2 (сфокусированный поиск) — не режем по бакету (кап = TOP_N). Отсюда стабильные **8** результатов.

---

## 14. Объяснения §9.7 (`_presentation`, `core_v2.py:497`)

2–3 подтверждённые причины (**только `known_match`** — никогда выдуманные факты), отсортированные по вкладу
`w·value`, + одна главная «дыра» (top `known_mismatch`, иначе top `unknown`). Есть RU/EN тексты и легаси-фразы
(«shares X», «similar vibe», «very close»), которые понимает buddy-humanizer.

---

## 15. Контракт карты (что возвращает движок, `core_v2.py:598`)

Каждая карта в слейте:
- **Легаси-контракт** (его рендерят buddy/profile UI): `name, score (=lcb·100), tier, kind, km, vibe, open,
  verified, age, interests, role, dealBreakers, reasons, agree, note, bucket`.
- **Core v2**: `band, band_ru, band_en, reasons_ru/en, gap_ru/en, coverage, lcb, reciprocal, unknowns,
  can_outreach, readiness, readiness_ru/en, trace{tier, policy:ALLOW, domain, a_to_b, b_to_a, reciprocal, band,
  readiness, config_version}`.
- **Оверлеи обвязки/спринта** (добавляются в `match_candidates` после движка): `policy (ALLOW/REVIEW),
  allocation_action, decision_class, retrieval_source, allocation_trace, profile_view, snapshot, relationship,
  completion_factors, readiness_explain, taxonomy_edge`.

Возвращается: `(_slate(out), meta)`, где `meta = {core:"v2", config_version, domain, config_sha}`.

---

## 16. Never-empty / fallback §12 (`_expand_fallback`, `app.py:1463`)

Если движок вернул пусто, но eligible-кандидаты есть — расширение по ПОЛНОМУ пулу (не урезанному бюджетом):
relaxed-проход через `_core.search` с клоном конфига (`_RELAXED_CFG`: discovery-пороги = 0, но веса/λ/outreach-пороги
те же, **хард-гейты НИКОГДА не ослабляются**), даёт «broader»; если topical-overlap нулевой — ближайшие доступные
как «alternative» (тир T4). Пул из одних загейченных → честно пусто.

---

## 17. Детерминизм и воспроизводимость

- `ctx.now` пиннится (`match_candidates` ставит `now` в ctx) — никакие стенные часы не входят в скоринг
  (`readiness`/TTL берут `ctx.now`).
- Тай-брейк по `name` в сортировке слейта — тотальный порядок.
- `id`-хэш и sha используют `hashlib` (не встроенный `hash()`), поэтому не зависят от `PYTHONHASHSEED`.
- Двойной прогон одного запроса даёт идентичный слейт (проверяется тестами и стендом «Проверка стабильности»).

---

## 18. Откат: легаси-скорер v1 (`match_candidates_legacy`, `app.py:940`)

При `KLEAL_CORE_V2=0` или невалидном/несовпавшем по sha конфиге работает старый скорер (не основной путь):
- `_base_tier` (`app.py:900`): reciprocal→85, exact→70(+`tier_exact_step`·overlap), adjacent→55, related→40,
  broad→30 (значения из `WEIGHTS`, `app.py:216`);
- capped-модификаторы: lang +6, vibe +5, mood_open +3, fresh +2, geo 8/5/2, fb_accept +8 / fb_reject −20,
  entity +10, time_fit ±, role ±;
- `_tier_label` (`app.py:918`): ярлык T0–T5 **из порога score** (thr_t0=85 … thr_t4=30) — здесь тир ВЫВОДИТСЯ из
  score (в отличие от core_v2, где тир — провенанс);
- `_diversify` (`app.py:923`): `diversity_max=3` на бакет, `top_n=10`.

Рантайм-тюнер `set_weights` (`app.py:230`) **заморожен** (§23.2.11): не мутирует `WEIGHTS`, только эхо — единственный
источник весов в основном пути — sha-pinned YAML.

---

## 19. Карта функций (навигация)

| что | где |
|---|---|
| Загрузка+валидация конфига | `core_v2.py:100 load_config`, `:57 parse_mini_yaml` |
| Определение домена | `core_v2.py:146 infer_domain` |
| Построение признаков A→B / B→A | `core_v2.py:199 build_features`, `:315 reverse_features` |
| Направленный score / reciprocal | `core_v2.py:327 directional_score`, `:352 reciprocal_score` |
| Тиры | `core_v2.py:358 assign_tier` (+ `app.py:147 topical`, `:889 _reciprocal`) |
| Готовность приёма | `core_v2.py:427 readiness_state`, `:414 is_paused` |
| Бэнды | `core_v2.py:470 assign_band` |
| Слейт/диверсификация | `core_v2.py:530 _slate` |
| Объяснения | `core_v2.py:497 _presentation` |
| **Главный вход движка** | `core_v2.py:545 search` |
| **Оркестрация (вход обвязки)** | `app.py:1253 match_candidates` |
| Хард-гейты / политика | `app.py:729 _hard_gates`, `:773 _policy_decision`, `:800 evaluate_policy` |
| Ретрив | `app.py:1200 _retrieve`, `:1157 RETRIEVAL_BUDGET`, `:1160/1172 stages/sources` |
| Never-empty | `app.py:1463 _expand_fallback` |
| Аллокация §11 | `app.py:1094 _allocate`, `:1061 _alloc_cfg` |
| Легаси-скорер (откат) | `app.py:940 match_candidates_legacy` |

---

_Источник истины — код по ссылкам выше и sha-pinned `config/Kleal_Matching_Core_Config_v2.yaml` (21505ccb).
Всё описанное — фактически реализовано и исполняется на активном пути `KLEAL_CORE_V2=1`. Стадии, помеченные
`blocked_infra` (ann_recall/pgvector) и `pilot-disabled` (источники ретрива 3/4: группы/события), присутствуют в
коде как объявленные и отключённые — не как работающие._
