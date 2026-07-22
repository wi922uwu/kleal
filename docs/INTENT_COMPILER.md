# Kleal — Intent Compiler и политика уточнений (§5)

Модуль [`shared/kleal_intent.py`](../shared/kleal_intent.py) (`ki`) — детерминированный, **LLM-free**,
keyless. LLM в §5 — только парсер: его вывод недоверенный и проходит валидацию/allowlist/нормализацию/
policy-checks, прежде чем влиять на матчинг. Слой **аддитивный**: не переименовывает/не удаляет плоские
ключи intent, которые читает sha-пиннутый `core_v2.py`, и **не превращает существующий hard-гейт в soft**.

## §5 intro — недоверенный LLM-вывод
`validate_and_normalize(intent, source)` → `(out, report)`, идемпотентно:
- дозаполняет 16 плоских ключей из `kc._FLAT_DEFAULTS` (нейтральные дефолты — не «ужесточённые» дефолты
  парсера, чтобы не фабриковать гейты);
- allowlist: `type`→{dinner,sport,gaming,networking,dating,language,social,other,event} (иначе `social`),
  `role`→{play,watch,discuss,practise,attend,meet} (иначе `meet`), `mode`→{offline,online} (иначе `offline`);
- topics: lower/strip/дедуп/cap 4, **без** таксономии/перевода (off-taxonomy `labubu`/`пиво` выживают);
- numeric clamp fail-open: `radiusKm`∈[1,500], возраст [18,120], `minAge>maxAge`→drop maxAge;
- `requiredLanguages`: **только** усечение `str(l)[:2].lower()` (никаких name→ISO карт — иначе прямой гейт
  «Spanish»→`sp` молча стал бы `es`);
- boolean-коэрция; read-only проверка `kc.validate_intent` (ключи не теряются).

`normalize_for_scoring(intent)` — один идемпотентный хелпер, вызывается в начале **и** `match_candidates`,
**и** `explain_match` (иначе рушится PARITY-гард и дрейфует intent_id).

Подключено: `parse_intent` (обе ветки) и оба входа скоринга.

## §5.1 — Hard vs soft (`extract_constraints`)
Детерминантный EN+RU keyword/regex-магнит по ИСХОДНОМУ тексту. Пишет только НОВЫЕ sibling-ключи:

| Фраза | Извлекается | Вид | Гейт в момент извлечения? |
|---|---|---|---|
| «рядом» / nearby | `preferredNearby`, `softLocationBias` | soft | нет (surface-only) |
| «только по-испански» | `proposedRequiredLanguages=['es']` | hard **после confirm** | **нет** — `requiredLanguages` не пишется |
| «без токсиков» | `moderationPrefs`, `domainConstraints.no_toxicity` | moderation | нет (surface/log) |
| «можно онлайн» | `allowOnlineFallback`, `allowedModes` | fallback-mode | нет — `mode` остаётся offline |
| «вторую половинку» | `proposedType='dating'`, `evergreenGoal` | dating evergreen | **нет** — `type` не меняется |

**Правило подтверждения** (`intent_summary`): любое ограничение sensitive / исключающее большую долю /
влияющее на safety попадает в `constraints_to_confirm`, `requires_confirmation=True`, есть
`may_empty_pool_warning`. `apply_confirmation(intent, confirmed_ids, constraints)` промоутит ТОЛЬКО
подтверждённые: `proposedRequiredLanguages`→`requiredLanguages` (усечение сохраняется),
`proposedType='dating'`→`type='dating'` **без** авто-`verifiedOnly`/`minAge`; ставит §4.2-провенанс
level-2 `user_confirmed_intent_summary`. Эндпоинт **`POST /api/agent/confirm`**.

## §5.2 — Политика уточнений (`clarification_policy`)
Классы гэпов из скомпилированного intent + `minimally_sufficient` + извлечённых constraints:
- **P0 mandatory** (safety/eligibility): dating opt-in pending, games platform/crossplay, неподтверждённый
  required-language.
- **P1 high-value** (>30% pool / открывает tier): time horizon, город/online, 1:1-vs-group, native-vs-level.
- **P2 ranking-only**: тема/глубина/team/skill.
- **P3 cosmetic**: заголовок карточки.

Выбор — **rule-based** (не EVI): каждый гэп — 4 ordinal-фактора {0,1,2} (safety_impact,
candidate_pool_split, supply_unlock, user_control), friction вычитается тай-брейком. Сортировка
(class_rank, 4-факторный кортеж, −friction) → ОДИН верхний гэп = не более одного вопроса. **До первых
результатов** спрашивается только `is_mandatory_safety` (safety_impact==2 ИЛИ dating opt-in) — прочие P0
(platform, язык) корректно **откладываются**. On-refuse: P0 — не запускать sensitive flow + безопасная
альтернатива; P1 — искать с unknown + низкой уверенностью, без скрытого дефолта; P2/P3 — не спрашивать до
результатов / вообще.

## §5.3 — Минимально достаточный intent (`minimally_sufficient`)
Проверка (не стемпит) по §4-блокам: domain+activity/purpose · time horizon или явное «Flexible» ·
mode+format · город/online/fallback · domain-critical поля (по (domain,role)) · fallback+disclosure ·
**TTL+search budget** (уже из §4 `compile_intent.lifecycle`).

## Статус (честно)
**✅ 22 · 🟡 4** (было ✅3·🟡6·⬜11). 🟡: «рядом» и «без токсиков» — surface-only (у sha-пиннутого
`core_v2` нет consumer для ранжирующего сдвига; реальный bias требует правки движка/конфига — нельзя без
слома пина и PARITY); §5.2 P2 (класс/defer есть, ре-ранжирование по ответу — нет); §5.3 domain-critical
(карта есть, апстрим не всегда собирает platform/rank/level/skill).

Тесты: `services/matching/test_core_v2.py` — `C5-*` (20 проверок; `C5-GATE1..3` — **load-bearing**
регрессии: ни один hard-гейт не ослаблен).
