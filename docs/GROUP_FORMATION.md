# Kleal — Group Formation Core (§15)

Группа оценивается как **множество**, а не как среднее парных совпадений (§15). Реализовано в
[`shared/kleal_groups.py`](../shared/kleal_groups.py) (`kg`, keyless, **LLM-free**, детерминированный, no FS/clock/
random) + аддитивная **gated** проводка в `matching/app.py`. Это **conformance-scaffolding**: `group_formation`
**выключен** в пилоте (§1.2/§15), поэтому ничего здесь не встроено в живой person-to-person поток —
алгоритм запускается ТОЛЬКО под явным test-only override и всегда возвращает `enabled:False`.

Дисциплина: `kg` импортирует только stdlib `hashlib` + `kleal_contracts` (kc) + `kleal_states` (ks); **никогда**
`core_v2`/`llm_client`. `now_ts` инъектируется (в т.ч. в `kc.build_reservation`, который иначе берёт `time.time()`).
Pair relevance — строго **вход** (§15.2): модуль НЕ пересчитывает R_{i→j}.

## §15.1 Set-level hard constraints (`check_set_constraints`/`set_feasible`)
SORTED коды нарушений (пусто = feasible), deny-safe (неизвестный constraint → no-op, никогда false-pass на
block/safety): `SIZE_MIN`/`SIZE_MAX`/`QUORUM`/`CAPACITY_EXCEEDED`/`MANDATORY_ROLE_UNMET`/`PAIR_BLOCKED`/
`SAFETY_EXCLUDED`/`HOST_MISSING`/`SKILL_SPREAD`/`LANGUAGE_UNCOVERED`/`EQUIPMENT_MISSING`/`PLATFORM_UNSUPPORTED`/
`TIME_OVERLAP_INSUFFICIENT`. `filter_hard_set_constraints` — per-member prefilter (universally-infeasible
отсеиваются), сортировка по `(-relevance, id_hash, id)`.

## §15.2 GroupUtility — **config-derived**
`GroupUtility(G) = w_lm·least_misery + w_mmr·mean_pair_fit + w_rc·role_coverage + w_to·time_overlap +
w_dv·diversity_value`, где ВСЕ пять `w_*` читаются из sha-pinned `cfg['group_formation']['utility_weights']`
через `load_group_params` (yaml: 0.35/0.25/0.20/0.10/0.10). **Никогда не хардкодятся.**
- **Config-ключи — источник истины.** `WEIGHT_KEYS` привязаны к ТОЧНЫМ config-ключам
  (`least_misery`,`mean_member_relevance`,`role_coverage`,`time_overlap`,`diversity_budget`); `SPEC_ALIAS`
  документирует расхождение с прозой §15.2 (config `mean_member_relevance`≡spec `mean_pair_fit`;
  `diversity_budget`≡`diversity_value`) — чтобы ни один вес не был молча обнулён.
- **least_misery = МИНИМУМ направленной удовлетворённости** (не среднее) — защита от «высокое среднее прячет
  одного явно неподходящего». С pair-матрицей — min по всем направленным рёбрам; star-fallback (pair_rel None) —
  min по `member['relevance']` (card `lcb`).
- **Feasibility доминирует:** если `check_set_constraints(G)` непусто → `group_utility.utility = None` (не число);
  `max_by_utility`/`form_group` трактуют None как «никогда не выбирается» — infeasible-группа с максимальными
  компонентами НИКОГДА не побеждает.
- **HARD/SOFT split:** mandatory roles / min_duration — HARD-гейты; `role_coverage` (полный wishlist) и
  `time_overlap` (нормируется к `ideal_duration_min`) — SOFT-термы. `diversity_value` — normalized Gini-Simpson по
  `diversity_axis` (missing axis → 0.0, консервативно; 0.10 soft-терм, никогда не источник infeasibility).
- Валидатор `load_group_params` закрывает пропуск `core_v2.load_config` (тот НЕ проверяет sum-to-1.0 для
  group-блока) — **не редактируя** sha-pinned yaml/core_v2; read-only `validate_group_config_block` — на load-time.

## §15.3 MVP algorithm (`form_group`, App B.3) — детерминированный
Первый оператор: `if not enabled_override: return dormant_response(...)` — тело недостижимо в пилоте.
1. **seed** — `filter_hard_set_constraints` (домен+время);
2. **feasible pools** — per-member + per-group hard-гейты;
3. **greedy** — `greedy_marginal_add`: макс. marginal gain по TOTAL utility (least_misery немонотонен), tie →
   низший `(id_hash,id)`, gains округлены 6dp;
4. **local repair** — `local_repair`: ADD/SWAP/REMOVE только строго-улучшающие (delta>EPS=1e-9), жёсткий кап
   `MAX_REPAIR_ITERS = 2·size_max·(|feasible|+1)` ⇒ доказуемая терминация, без циклов;
5. **reserve** — `reserve_members` + `claim_group_seat` (§15.3.5 + App C #8, ниже);
6. **invitations** — `build_group_invitations` (purpose-bound `kc.build_profile_view`, СКОНСТРУИРОВАНЫ, не
   отправлены — в пилоте нет мессенджинга);
7. **waitlist/quorum** — `replacement_policy` (data-only: `on_refusal:waitlist`, `on_quorum_loss:cancel_or_reform`).

Детерминизм: seed по `(-relevance,id_hash)`; greedy/repair tie по `(id_hash,id)`; cross-seed tie по
`group_signature` (sha1 отсортированных id); 6dp округление; `now_ts` инъектируется. Одинаковый вход (в любом
порядке кандидатов) → **byte-identical** группа. Heuristic MVP — «best found», не глобальный оптимум.

## App C #8 — гонка последнего места (`claim_group_seat`/`reserve_members`) — **reuses §14**
`claim_group_seat` отклоняет `seat_ordinal >= capacity` ДО claim (`CAPACITY_EXCEEDED`), затем first-claim-wins
атомарная вставка `ks.claim_slot` по составному ключу `group_id#seatN` — **без нового lock**. Проигравший на
последнем месте → `ks.resolve_race('slot_taken')` (WITHDRAWN / грубый public_reason / `leak:False`) + waitlist;
`filled` **никогда** не превышает capacity по построению. **Single-process** (кросс-процессная/мульти-под
атомарность требует БД/очереди — blocked_infra). Внутри модуля резервирование — один детерминированный
sorted-проход (реальной same-seat контенции нет; «concurrent» — конструкция теста).

## Gating (dormant-at-pilot / falsifiable-under-tight-override)
Четыре слоя держат `group_formation` выключенным, оставаясь falsifiable:
1. **Global** не тронут — `PILOT_DECISION_TYPES['group_formation']=False`, honest-empty `/api/agent/match` ветка,
   `/status` — без изменений; модуль НИКОГДА не флипает флаг.
2. **Module** — чистая библиотека без import-side-effects; unit-тестируема изолированно.
3. **Top gate** — `form_group` короткозамыкает на `dormant_response`, если нет override; даже под override результат
   несёт `enabled:False`.
4. **Endpoint** — НОВЫЙ аддитивный `POST /api/agent/group` (не переименование frozen `/api/agent/*`); тело —
   `run_group_formation`, dormant если не `is_override_enabled(override)` — требуется ТОЧНЫЙ `{'enable_group_formation':
   True}` (bool). Non-bool truthy → dormant. Override per-request, test-only, не персистится, не меняет global state.
   Wiring-адаптер маппит card `lcb`→`relevance` лоссless (прочие поля сохранены).

**Byte-identical person-to-person slate:** `core_v2.search`/`match_candidates`/`negotiate` НЕ импортируют и не
вызывают `kg` (статически проверено `C15G-11`). sha-pinned `core_v2.py` + yaml не редактированы.

## Статус (честно): **done 10 · done_config_derived 2 · pilot_disabled 2 · partial 2 · blocked_infra 1**
- **done:** §15.1 hard-constraints, §15.2 feasibility-dominates + least_misery=min, §15.3.1-5 seed/pools/greedy/
  repair/reserve, §15.3.7 replacement (data-only), App C #8 last-seat (single-process), config sum-to-1.0 gap.
- **done_config_derived:** §15.2 веса из sha-pinned config; sum-to-1.0 валидатор.
- **pilot_disabled (2):** §15.3.6 structured invitations (сконструированы, не отправлены); живая проводка в
  buddy→filtration→matching (endpoint `enabled:False` без точного override).
- **partial (2):** §15.4 конкретные domain-packs (generic role/diversity/skill-spread есть; Dota/Padel/
  Conversation/Walk паки — за §37+); candidate↔candidate pair_rel матрица (core_v2 сейчас даёт только
  initiator↔candidate; модуль берёт n×n как ВХОД, симметричную сборку делает wiring).
- **blocked_infra (1):** кросс-процессная/мульти-под атомарность последнего места (нужна БД/очередь).

**Дизайн-ревью** (6 агентов, go_with_fixes / sound_with_fixes): 11 must-fix + 3 blocking — все применены
(clock-leak в build_reservation → `now_ts` обязателен; feasibility via `utility=None`; config-ключи как источник;
size-key map `supported_size_*`→internal; drop `compare_and_swap` — только `ks.claim_slot`; override — точный ключ;
zero `core_v2` import; strict-improve+iter-cap терминация; capacity-тест — order-INDEPENDENT инварианты).

**Адверсариал-ревью реализации** (5 finders → verify, 20 находок, 4 подтверждены — все low, pilot-off держит их вне
живого потока; исправлены): (1) `_common_window` считал bounding-span, а не ИСТИННОЕ пересечение множеств интервалов
→ член с двумя разрозненными окнами `[[0,10],[100,110]]` ложно читался доступным через разрыв, `TIME_OVERLAP_
INSUFFICIENT` мог не сработать — переписано на `_intersect`/`_total_length` (true set-intersection); (2)
`greedy_marginal_add` брал только строго-улучшающие add → группа, которой нужен utility-нейтральный филлер до
`size_min`/quorum, ложно возвращала `NO_FEASIBLE_GROUP` — добавлен FEASIBILITY-режим (добавляет лучший
прогрессирующий по feasibility член, даже при нулевом/отрицательном marginal, пока не станет feasible, затем
positive-gain-only); (3-4) два слабых теста укреплены (C15G-06 теперь реально проверяет utility ≥ known-feasible;
C15G-14 линкует `WEIGHT_KEYS` к РЕАЛЬНЫМ ключам yaml). Плюс hardening: `directed_relevance` NaN→0.0;
`reserve_members` тест — non-vacuous (ровно capacity). Байт-идентичность slate и info-leak — held.

Тесты: `services/matching/test_core_v2.py` — `C15G-*` (**21 проверка**). Вся сюита **240/240** зелёная, детерминизм —
двойной прогон. Live HTTP smoke `/api/agent/group`: dormant по умолчанию, falsifiable под точным override
(utility 0.76875 = точная config-взвешенная сумма), `enabled:False` всегда.
