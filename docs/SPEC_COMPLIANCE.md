# Kleal — отчёт о реализации по подпунктам спеки

_Проверено по коду (28 агентов, состязательная проверка). Для done/partial указан файл:функция. «Не реализовано» — по scope прототипа._

## Итог

| | Подпунктов |
|---|--:|
| ✅ Реализовано | 176 |
| 🟡 Частично | 141 |
| ⬜ Не реализовано | 169 |
| **Всего** | **486** |

> **Доработка раздела «частично» (47 подпунктов → done).** По deep-dive-аудиту из 80 «частично» ровно **47**
> оказались закрываемыми чистым аддитивным кодом (без правки sha-pinned движка, byte-identical person-slate). Все
> **47 закрыты** батчами (`CP1–CP10`, 41 новый тест; вся сюита **305/305** зелёная, детерминизм — двойной прогон):
> §17 dating-safeguards (capsule/consent/disclosure/isolation/explanation/mode-scoped-feedback), §18 per-domain
> critical-slot гейты + min-duration + per-domain ladder, §14.3 dating-manual-confirm, §12.1 пошаговое расширение,
> §15.4 domain-паки, §21.2 эндпоинты (proposals/respond/plans/compile/expand), §21.1 plan-coordinator/match-capsule,
> §21.3 decision-trace, §21.4 config-health, §22.2.0/§23.4.1 contract-registry+schema, §23.2.7/.10/.11/.13 +
> §22.2.3 (детерминированный negotiate, band-not-percent, freeze-weights, idempotent writes), §23.4.2/.5/.7/.8,
> §1.0b completion-confirm, §1.1 condition-merge, §8.1 zone-REVIEW, §19.2 decay/drop-inferred, C.13/C.16/C.17/C.21,
> B.1 search-pipeline, D.0 purpose-binding. Оставшиеся 33 «частично» блокирует инфра (23) / калибровка (4) /
> процесс (4) / движок (2) — не код (см. [отчёт-разбор](CANDIDATE_TYPES.md) и артефакт «Детальная доработка»).


## §0–§3 Резюме / Цель / Принципы / Архитектура

_Базовая проверка: ✅ 13 · 🟡 17 · ⬜ 7._
_После реализации §0–§3 (2026-07-17, слой оркестрации `matching/app.py`, без правки `core_v2.py`/конфига): **✅ 20 · 🟡 12 · ⬜ 5**._

> **Обновлено 2026-07-17 — что реализовано в §0–§3** (тесты: `services/matching/test_core_v2.py`
> PAY1–2, PILOT1–3, IDENT1–3, SNAP1, OUT1–3, REVIEW1–2, ALLOC1–2 — все зелёные):
>
> - **§0 решение 10 → ✅** — payment-инвариант теперь читается из конфига (`currency_or_paid_priority`)
>   и принуждается/виден: `app.py:_payment_invariant` / `PAYMENT_INVARIANT`, отдаётся в
>   `GET /api/agent/weights` и в снапшоте. Если конфиг когда-либо включит буст — `ok=False` (проверка, не допущение).
> - **§0 таблица выходов → ✅ (8/8)** — добавлены недостающие 2 выхода: `policy_decision` теперь
>   три-состояние **ALLOW / REVIEW / BLOCK** (`app.py:_policy_decision`) и типизированный
>   **`allocation_action`** на каждой карточке (`app.py:_allocation_action`: propose / discovery_only /
>   discovery_expanded / review_required).
> - **§1 инвариант успеха → ✅** — жизненный цикл исхода
>   (proposed/accepted/declined/completed/expired_no_response), объект **match** при взаимном accept после
>   ревалидации, метрика **completed_interactions**; **молчание нейтрально, не негатив**
>   (`app.py:_record_outcome` / `_success_metrics`; `POST /api/agent/outcome`, `GET /api/agent/outcomes`).
> - **§2 термины → ✅** — «match = взаимное согласие после ревалидации» и «success = состоявшееся
>   взаимодействие» теперь смоделированы (см. выше).
> - **§1.2 dating gate → ✅** — `release_gate=separate_safety_legal_track` теперь принуждается:
>   dating + неверифицированный кандидат → **REVIEW** (виден в discovery, без авто-outreach).
> - **§1.2 пилот → ✅** — `PILOT_DECISION_TYPES` + `_pilot_enabled`: person/intent — живые;
>   group/event/room/continuation **объявлены и выключены** (запрос → честный «не в этом пилоте»).
> - **§2 нормативные слова → ✅** — [docs/NORMATIVE.md](NORMATIVE.md): MUST/MUST NOT/SHOULD §0–§3 → точки принуждения в коде.
> - **§3 шаг1 / §4.3 identity → частично↑** — детерминированный `intent_id`+`version`+`domain`+`status`
>   (`app.py:_intent_identity`) и **снапшот версий** intent/config/policy/data на каждый запрос
>   (`app.py:_request_snapshot`), в ответах `/api/agent/match` и `/plan`. Осталось: шаг подтверждения/уточнения интента.
>
> **Осталось ⬜ (5) — это пост-пилотные слои, а не забытые пункты** (теперь явно помечены
> pilot-disabled): `§0 решение 7`, `§1.1 group formation` (§15), `§1.1 intent-to-event`,
> `§1.1 intent-to-room` (§16), `§1.1 relationship continuation` (§14).
> **Осталось 🟡 (12)** — частичные пункты, чьё полное закрытие живёт в своих разделах: §0 реш.6 (типизированный
> agent-протокол — §13), §0 реш.8 (отдельный dating-профиль/consent/disclosure — §4/§8), §0 реш.9 / §3 шаг9
> (transaction-orchestrator, TTL/idempotency/reservation — §14), §3 шаг2 (пофилдовый profile-view — §4),
> §3 шаг7 (fairness/exposure во времени), §1.1 intent-to-intent (полное слияние условий), §1.2 passive
> outreach (лимит 7д), §1 цель/таблица контуров (активная оптимизация).

### Базовая проверка (детально)

_✅ 13 · 🟡 17 · ⬜ 7_


**Реализовано (полностью / частично):**

- ✅ **§0 шесть слоёв** — 6 независимых слоёв; ни один не компенсирует другой. Присутствуют eligibility(_hard_gates до скоринга), retrieval(assign_tier/T5-drop), relevance(directional_score), reciprocity/readiness, allocation(_slate/sort), presentation(_presentation). readiness и allocation не входят в score, гейты жёсткие. Transaction-слой тонкий. — `app.py:match_candidates:611 / core_v2.py:search:545`
- ✅ **§0 решение 1** — Веса/пороги только в versioned YAML. core_v2.load_config читает sha-pinned YAML (веса доменов, priors, λ, floors, bands); движок не содержит настраиваемых чисел relevance. Каветы: SEM_VALUE/GEO_BANDS — «observed-value anchors» в коде; legacy WEIGHTS-словарь отдельно. — `core_v2.py:load_config:100`
- ✅ **§0 решение 2** — Semantic tier = происхождение, не зависит от score. assign_tier определяет T0–T3/T5 по реципрокности и таксономическому перекрытию (retrieval), а не по итоговому score; score в тир не входит. — `core_v2.py:assign_tier:358`
- ✅ **§0 решение 3** — unknown/mismatch/not_applicable — разные состояния; разреженный профиль не выигрывает. build_features даёт 4 состояния; в directional_score NA исключён из знаменателя, UNKNOWN даёт prior и снижает coverage, а lcb=mean−λ(1−cov) штрафует низкое покрытие — пустой профиль не обгоняет подтверждённый. — `core_v2.py:directional_score:327`
- ✅ **§0 решение 4** — relevance = внутренняя эвристика 0–1, не вероятность/не процент. directional_score возвращает mean/lcb в 0–1; acceptance_probability отсутствует. Легаси-поле score=lcb*100 в карточке есть, но пользователю показывается band, не процент (§9.7). — `core_v2.py:directional_score:349`
- ✅ **§0 решение 5** — Пользователь видит уровень + 2–3 причины + 1 gap + объяснение расширения. _presentation отдаёт 2–3 причины (только known_match) и один gap; assign_band даёт качественный уровень; расширение помечается тегами fallback (broader/alternative). — `core_v2.py:_presentation:497 / assign_band:470`
- ✅ **§1.1 person-to-person** — Поиск одного человека для общения/активности. Основной сценарий движка: match_candidates→core_v2.search ранжирует людей под intent пользователя. — `app.py:match_candidates:611`
- ✅ **§3 шаг3** — Retrieval по источникам + присвоение semantic_tier. load_candidates собирает из store+demo-пула; assign_tier присваивает T0–T3/T5 по перекрытию. — `app.py:load_candidates:317 / core_v2.py:assign_tier:358`
- ✅ **§3 шаг4** — Feature Builder: уникальные evidence groups без double count. build_features строит 7 групп с одной агрегированной субфичей на группу; alias/parent-чтения одного интереса сворачиваются в один matched-набор (нет двойного счёта). — `core_v2.py:build_features:199`
- ✅ **§3 шаг5** — Relevance: A→B, B→A, coverage и conservative score. directional_score считает mean/coverage/lcb; reverse_features даёт B→A; reciprocal_score = 0.7*min+0.3*mean по консервативным lcb. — `core_v2.py:directional_score:327 / reverse_features:315 / reciprocal_score:352`
- ✅ **§3 шаг6** — Readiness + receiving policy → допустим ли outreach сейчас. readiness_state выводит категориальный статус из receiving policy/quiet-hours/fatigue; в search can_outreach комбинирует тир/consent + open_now + floors. Не смешивается с relevance. — `core_v2.py:readiness_state:427 / search:582`
- ✅ **§3 шаг8** — Presentation: причины и gaps без скрытых данных. _presentation формирует 2–3 причины только из known_match (без выдуманных фактов) и единственный топ-gap; скрытые данные не раскрываются. — `core_v2.py:_presentation:497`
- ✅ **§3 запрещённая архитектура** — Нет единого FinalUtility (relevance+safety+response+fairness+оплата+fatigue). Единой сводной формулы нет: safety — жёсткий гейт, readiness/allocation — порядок/гейт, а не слагаемые score; сортировка использует band/readiness/reciprocal кортежем, не суммой. — `core_v2.py:search:619 / directional_score:327`
- 🟡 **§0 Главное решение** — Не «совместимость людей», а закрытие конкретного intent + честный показ расширения. Движок оценивает релевантность к конкретному intent (topics), а не процент совместимости; safety/eligibility — жёсткие гейты до скоринга; расширение честно помечается band/tier/fallback. Нагрузка учитывается только со стороны получателя, разрешённого profile-view (приватность) нет. — `core_v2.py:search / app.py:_hard_gates:428`
- 🟡 **§0 решение 6** — Agent-to-agent = структурированный протокол, не свободные LLM-диалоги. Предчек детерминирован и структурирован (eligibility+tier/consent+readiness+волны/кап), но само решение accept/reject делегируется LLM-промпту negotiate_one — это противоречит «не свободные LLM-диалоги». — `app.py:_negotiate_precheck:768 / negotiate_one:731`
- 🟡 **§0 решение 8** — Dating: отдельный профиль/receiving policy/consent/disclosure/release gate. Есть eligibility-гейт (datingOk, дефолтные verifiedOnly/minAge=18) и отдельный домен dating с весами; release_gate в конфиге — только данные. Отдельного профиля, consent/disclosure и enforcement release gate нет. — `app.py:_hard_gates:437 / core_v2.py:infer_domain:148`
- 🟡 **§0 решение 9** — Переходы proposal/match/plan транзакционны, идемпотентны, ревалидируют policy/TTL/capacity/версии. _negotiate_precheck на границе отправки повторно проверяет eligibility+tier/consent+readiness+capacity(волны, received_24h). Нет идемпотентности, TTL, reservation/match-объектов и проверки версий. — `app.py:_negotiate_precheck:768`
- 🟡 **§0 решение 10** — Оплата подписки не влияет на relevance/eligibility/safety/порядок. В коде матчинга нет понятия оплаты/подписки, поэтому инвариант держится структурно (в скоринг не подаётся ни одного платёжного входа); но флаг currency_or_paid_priority в конфиге кодом не читается, явного enforcement нет. — `core_v2.py:directional_score:327`
- 🟡 **§0 таблица выходов** — 8 типизированных выходов системы. Реализованы 6/8: semantic_tier, relevance_score(mean/lcb), evidence_coverage(+unknowns), reciprocal_relevance, readiness_state, explanation_keys. policy_decision только ALLOW/BLOCK (REVIEW нет); отдельного allocation_action нет — только slate/wave-кап. — `core_v2.py:search:598`
- 🟡 **§1 цель** — Максимизировать состоявшиеся взаимодействия; набор проверяемых решений, а не одна формула. Реализовано как цепочка промежуточных проверок (гейты→тиры→band→readiness), единой псевдовероятностной формулы нет. Активной оптимизации именно «состоявшихся взаимодействий» (обучение/оптимизация) нет. — `core_v2.py:search:545`
- 🟡 **§1 таблица контуров** — 7 контуров: что решают / чего не делают. Выполнено: eligibility без штрафа совместимости, retrieval без embeddings, relevance к intent (не симпатия), allocation не меняет relevance. Частично/нет: «предпочтение не в hard gate без подтверждения», «молчание ≠ отказ», transaction-revalidation. — `app.py:_hard_gates:428 / core_v2.py:search:619`
- 🟡 **§1 инвариант успеха** — Успех = completed interaction + двусторонний feedback; молчание ≠ негатив. Есть только односторонний feedback-стор (accept/reject владельца) для legacy-скорера; понятия completed interaction и двустороннего успеха нет. Молчание негативом не записывается (пишется лишь при явном accept/reject). — `app.py:record_feedback:226`
- 🟡 **§1.1 intent-to-intent** — Объединение двух активных запросов с совместимыми условиями. Реципрокность частично: _reciprocal учитывает собственный активный intent кандидата, reverse_features/reciprocal_score считают B→A. Полноценного join двух активных запросов как единицы с согласованием условий нет. — `app.py:_reciprocal:456 / core_v2.py:reciprocal_score:352`
- 🟡 **§1.2 passive outreach** — Passive outreach только после проверки receiving policy. readiness_state читает receiving.passive_outreach и allowed_domains и понижает до passive_discovery; в search персональный outreach отделён от discovery. Отдельного flow «пассивной рассылки» и лимита 7д (max_passive_...) нет. — `core_v2.py:readiness_state:427 / search:581`
- 🟡 **§1.2 dating gate** — Dating проходит отдельный safety/legal gate. Есть eligibility-гейт (datingOk + ужесточённые дефолты age/verified); release_gate=separate_safety_legal_track в конфиге не enforced кодом. — `app.py:_hard_gates:437`
- 🟡 **§2 термины** — Понятийная модель/различия терминов воплощены в коде. Различия реализованы: eligibility≠relevance, tier≠качество, unknown≠match, directional relevance≠вероятность, evidence coverage, readiness≠качество. Match как «взаимное согласие после ревалидации» и success как «состоявшееся взаимодействие» — не реализованы. — `core_v2.py:directional_score:327 / assign_tier:358`
- 🟡 **§3 шаг1** — Intent Compiler: структурированный intent + фиксация version. parse_intent/_fallback_parse строят структурированный intent (title/type/topics/role/mode/gates). Версионирования intent нет, отдельного шага подтверждения/уточнений тоже нет. — `app.py:parse_intent:407`
- 🟡 **§3 шаг2** — Policy Engine: разрешённый profile view + ALLOW/BLOCK/REVIEW. _hard_gates даёт ALLOW/BLOCK (в trace policy=ALLOW). REVIEW-состояния нет; «разрешённого profile view» (пофилдовое раскрытие/disclosure) нет. — `app.py:_hard_gates:428 / core_v2.py:search:612`
- 🟡 **§3 шаг7** — Allocation: slate и волны (fairness/fatigue/exposure). _slate диверсифицирует (≤3/бакет, top-8) и сортирует; волны и параллельный кап есть в _negotiate_precheck, fatigue — через received_24h. Учёта fairness/exposure во времени нет. — `core_v2.py:_slate:530 / app.py:_negotiate_precheck:781`
- 🟡 **§3 шаг9** — Transaction Orchestrator: proposal/reservation + revalidation на каждом переходе. На границе отправки _negotiate_precheck ревалидирует по live-стору (eligibility+consent+readiness+кап) и логирует proposal. Reservation/match-объектов, многошаговой state machine, TTL и идемпотентности нет. — `app.py:_negotiate_precheck:768 / _log_proposal:211`

**⬜ Не реализовано (7):** `§0 решение 7`, `§1.1 group formation`, `§1.1 intent-to-event`, `§1.1 intent-to-room`, `§1.1 relationship continuation`, `§1.2 пилот`, `§2 нормативные слова`

## §4 Канонические контракты данных

_Базовая проверка: ✅ 1 · 🟡 17 · ⬜ 10._
_После реализации §4 (2026-07-17, новый модуль [`shared/kleal_contracts.py`](../shared/kleal_contracts.py) + оркестрация; без правки `core_v2.py`/конфига): **✅ 17 · 🟡 9 · ⬜ 0** (Group/Plan — declared_disabled)._

> **Обновлено 2026-07-17 — реализован раздел §4** (полный разбор: [docs/CONTRACTS.md](CONTRACTS.md);
> тесты `services/matching/test_core_v2.py` секция `C4-*`, 29 проверок, вся сюита 89/89 зелёная).
> Дизайн прошёл field-inventory + состязательный ревью (11 агентов, 9 must-fix свёрнуты).
>
> **Стало ✅:** UserProfile (`build_user_profile`), ProfileView (`build_profile_view`, purpose-bound §8.3),
> ReceivingPolicy (`build_receiving_policy`, §4.4 superset + новые поля enforced на границе отправки),
> Intent + все 11 блоков §4.3 (`compile_intent`), Evidence + §4.1 объект + §4.2 семиуровневая иерархия
> (`build_evidence` + `FEATURE_GROUP_SOURCE`), Match (`build_match` → `/outcomes.match_capsules`),
> RelationshipEdge (`build_relationship_edge`, advisory), Proposal (`build_proposal`, idempotency+clamp),
> §4.3 Identity/Goal/Mode&format/Fallback/**Lifecycle-TTL** (истёкший intent не ранжируется).
>
> **Осталось 🟡 (9)** — частичные, потому что апстрим-онбординг ещё не собирает данные (фабриковать
> нельзя): CandidateSnapshot (богатое evidence только в explain), Reservation (нет capacity в
> person-to-person), §4.3 Time (только urgency+timezone), §4.3 Location (нет safe_zones/travel_time),
> §4.3 Target (нет level), §4.3 Social (pressure/style — плейсхолдеры), §4.3 Domain details (нет
> platform/rank/ticket/equipment), §4.3 Disclosure (минимальный stage_map → clamp консервативно no-op),
> §4.4 новые поля (disclosure_stage-clamp частично).
>
> **⬜ → 0**: `ProfileView / Evidence / Proposal / Reservation / Match / Group / Plan / §4.1 Evidence
> object / §4.3 Disclosure / §4.3 Lifecycle` — все реализованы как контракты (Group/Plan определены с
> `enabled=False`, т.к. это пилот-выключенные типы решений §15/§16).

### Базовая проверка (детально)

_✅ 1 · 🟡 17 · ⬜ 10_


**Реализовано (полностью / частично):**

- ✅ **§4 UserProfile** — UserProfile — базовые явные факты и настройки. Реальная сущность профиля есть: name/id, age, langs, area(city), km/lat/lon(geo), interests, vibe, role, verified, datingOk; admin нормализует ту же форму пользователя в стор. — `services/admin/app.py:_norm_user (l.78-132)`
- 🟡 **§4 intro: purpose-bound minimal representations + immutable snapshot (data/policy/config versions)** — Минимальные purpose-bound представления + immutable snapshot с версиями. Конфиг sha-пиннится (PINNED_SHA) и config_version кладётся в trace каждого кандидата. Профили не минимальны/не purpose-bound; immutable per-request snapshot с версиями data/policy отсутствует. — `services/matching/core_v2.py:load_config (l.100-107) + search (trace.config_version l.615)`
- 🟡 **§4 ReceivingPolicy** — ReceivingPolicy — условия пассивного рассмотрения. Есть объект receiving со status/allowed_domains/quiet_hours/proposal_budget/passive_outreach; readiness_state и is_paused его читают. Нет geography(location_scope), disclosure_stage, allowed_proposal_types. — `services/admin/app.py:_receiving_from_form (l.51-75) + services/matching/core_v2.py:readiness_state/is_paused (l.414-459)`
- 🟡 **§4 Intent** — Intent — подтверждённая текущая задача. parse_intent/_fallback_parse дают type/topics/time/mode/format/role/place/radiusKm и fallback-флаги. Нет TTL/lifecycle, version, а domain выводится отдельно (не хранится на intent). — `services/matching/app.py:_fallback_parse (l.379-405)`
- 🟡 **§4 CandidateSnapshot** — CandidateSnapshot — результат feature building для версии intent. Карточка+trace несут source/tier (provenance), агрегаты a_to_b/b_to_a, unknowns и config_version. Формального immutable snapshot с версиями данных нет. — `services/matching/core_v2.py:search (out card+trace l.598-615)`
- 🟡 **§4 RelationshipEdge** — RelationshipEdge — история пары (new/contact/friend/repeat/avoid/block, cooldown). Реализованы только block (blocksMe/blocked) и avoid+cooldown (declinedOwnerDaysAgo < COOLDOWN_DAYS=7) как хард-гейты. Нет объекта-ребра, состояний contact/friend/repeat, scope. — `services/matching/app.py:_hard_gates (l.431-433, COOLDOWN_DAYS l.162)`
- 🟡 **§4.1 общий evidence_id из одной фразы + дедуп Feature Builder до агрегации** — Дедупликация aliases/tags/nodes из одной фразы перед агрегацией. Feature Builder схлопывает alias/parent-чтения одного интереса в единый matched-set (без двойного счёта). Общего evidence_id нет — дедуп идёт по нормализованным строкам, не по источнику. — `services/matching/core_v2.py:build_features (semantic_activity matched set l.207-217)`
- 🟡 **§4.2 Иерархия источников (7 приоритетов, confidence/freshness/decay)** — Приоритет источников признаков. Есть лишь неявный приоритет: reverse_features предпочитает активный intent кандидата его interests, parse_intent — LLM-парс перед fallback. Нет уровней memory/observed/inference и полей confidence/freshness/decay. — `services/matching/core_v2.py:reverse_features (b_topics из intents ... or interests l.319-321)`
- 🟡 **§4.3 Identity (intent_id, user_id, version, domain, status; version++ при изменении)** — Intent Identity-блок. Из блока присутствует лишь domain — выводится infer_domain при каждом поиске. intent_id/user_id/version/status отсутствуют, версионирования нет. — `services/matching/core_v2.py:infer_domain (l.146-164)`
- 🟡 **§4.3 Goal (activity, purpose, desired outcome; purpose разделяет social/networking/dating)** — Intent Goal-блок. activity задаётся topics/type; type=dating отделяет dating (гейт datingOk, domain=dating). Явных полей purpose и desired outcome нет. — `services/matching/app.py:_fallback_parse (type l.396-397) + core_v2.py:infer_domain (l.148)`
- 🟡 **§4.3 Time (timezone, windows, duration, recurrence, urgency; UTC + interval algebra)** — Intent Time-блок. На intent только свободнотекстовая метка time ('Today evening'/'Flexible'). Нет timezone/windows/duration/recurrence/UTC; interval algebra есть лишь для quiet_hours в readiness. — `services/matching/app.py:_fallback_parse (time l.388-389) + core_v2.py:_in_quiet_hours (l.397-403)`
- 🟡 **§4.3 Location (city, coarse cell, radius/travel time, safe zones; клиенту не даётся точная координата)** — Intent Location-блок. Есть radiusKm (хард-гейт по km), чтение огрублённых координат (coarseLat/coarseLon, не точная точка) и дистанция по GEO_BANDS. Нет travel time и safe zones; фактического огрубления координат в matching-коде нет (поля приходят уже как coarse*). — `services/matching/core_v2.py:_latlon/GEO_BANDS (l.172,185-194) + services/matching/app.py:_hard_gates (radiusKm l.447-449)`
- 🟡 **§4.3 Mode & format (online/offline/hybrid, 1:1/group/event/room; явный/подтверждённый)** — Intent Mode & format-блок. Есть mode (offline|online) и свободнотекстовый format; mode_format сверяет форматы кандидата; online делает location not_applicable. Нет hybrid и enum room/event. — `services/matching/core_v2.py:build_features (mode_format l.251-258, online->NA l.234-236)`
- 🟡 **§4.3 Target (directed preferences, required roles, level; unknown != openness)** — Intent Target-блок. role (play/watch/discuss/...) = directed preference, requiredLanguages как required-условие; при неизвестной роли кандидата directed_preferences=unknown (не match). Поля level нет. — `services/matching/core_v2.py:build_features (directed_preferences l.260-272)`
- 🟡 **§4.3 Social context (vibe, pressure level, communication style; inferred временный/editable)** — Intent Social context-блок. Реализован только vibe (VIBE_CLASH-матрица в social_context). Нет pressure level и communication style; пометки inferred/editable отсутствуют. — `services/matching/core_v2.py:build_features (social_context, VIBE_CLASH l.274-284)`
- 🟡 **§4.3 Domain details (platform/server/rank; language level; ticket; equipment; mandatory→clarification)** — Intent Domain details-блок. Онбординг собирает platform/rank(games), skill level(sport), target level(language), industry/goal и при отсутствующем обязательном поле задаёт уточняющий вопрос (mandatory→clarification); matching domain_constraints использует языковую пару и entities-сообщество. Нет ticket/equipment. — `services/matching/core_v2.py:build_features (domain_constraints l.286-306) + services/onboarding/app.py (clarification l.169-183)`
- 🟡 **§4.3 Fallback (allowed dimensions and consent; система не расширяет запрещённые измерения)** — Intent Fallback-блок. Есть adjacentAllowed/exactMatchRequired/broadAllowed; _expand_fallback релаксирует adjacency и помечает результат 'broader' (не молча), broadConsent гейтит T2-outreach в search. Формального перечня разрешённых измерений с consent нет. — `services/matching/app.py:_expand_fallback (l.634-648) + core_v2.py:search (broadConsent gate l.581)`
- 🟡 **§4.4 Receiving policy JSON (status, allowed_domains, passive_outreach, quiet_hours, proposal_budget, location_scope, allowed_proposal_types, disclosure_stage, paused_until)** — Объект receiving policy. Строится/читается status, allowed_domains, quiet_hours{start,end,tz_offset_min}, proposal_budget.per_24h, passive_outreach; paused_until учитывается is_paused. Нет location_scope, allowed_proposal_types, disclosure_stage; per_7d не применяется. — `services/admin/app.py:_receiving_from_form (l.51-75) + services/matching/core_v2.py:readiness_state/is_paused (l.414-459)`

**⬜ Не реализовано (10):** `§4 ProfileView`, `§4 Evidence`, `§4 Proposal`, `§4 Reservation`, `§4 Match`, `§4 Group`, `§4 Plan`, `§4.1 Evidence object (evidence_id/source/scope/confidence/freshness/sensitivity/...)`, `§4.3 Disclosure (что показать на каждом этапе; user + purpose-binding policy)`, `§4.3 Lifecycle (created_at, expires_at, search budget; истёкший intent вне ranking)`

## §5 Intent Compiler и политика уточнений

_Базовая проверка: ✅ 3 · 🟡 6 · ⬜ 11._
_После реализации §5 (2026-07-17, новый модуль [`shared/kleal_intent.py`](../shared/kleal_intent.py) + оркестрация; без правки `core_v2.py`/конфига): **✅ 22 · 🟡 4** (по гранулярной карте 26 подпунктов)._

> **Обновлено 2026-07-17 — реализован раздел §5** (разбор: [docs/INTENT_COMPILER.md](INTENT_COMPILER.md);
> тесты `services/matching/test_core_v2.py` секция `C5-*`, 20 проверок incl. load-bearing block-gate
> регрессии; вся сюита 109/109 зелёная). Дизайн прошёл field-inventory + состязательный ревью (9 агентов,
> 9 must-fix свёрнуты).
>
> **Стало ✅:** §5 intro — LLM как недоверенный парсер: `parse_intent` гонит и LLM-, и fallback-выход через
> `ki.validate_and_normalize` (schema-complete 16 ключей, allowlist type/role/mode, numeric clamp,
> requiredLanguages 2-char **truncation-only**). §5.1 — hard/soft извлечение всех 5 строк таблицы
> (`extract_constraints`): «рядом»→soft, «только по-испански»→hard **после подтверждения** (не пишет
> requiredLanguages до `/confirm`), «без токсиков»→moderation, «можно онлайн»→fallback-mode (mode остаётся
> offline), «вторую половинку»→dating evergreen (type=dating только после подтверждения). Правило
> подтверждения — `intent_summary` + новый эндпоинт **`POST /api/agent/confirm`**. §5.2 — политика уточнений
> P0/P1/P2/P3, rule-based выбор ОДНОГО вопроса по 4 ordinal-факторам − friction, «≤1 вопрос до первых
> результатов, кроме mandatory safety» (предикат по safety, не по классу P0). §5.3 — `minimally_sufficient`
> по скомпилированным §4-блокам; TTL+search budget уже из §4.
>
> **Ключевой инвариант (защищён тестами):** ни один существующий hard-гейт не ослаблен —
> requiredLanguages/radiusKm/dating остаются BLOCK; §5.1 «soft» пишет только НОВЫЕ sibling-ключи; dating
> не автотайтенится (нет авто-verifiedOnly/minAge).
>
> **Осталось 🟡 (4):** §5.1 «рядом» (soft-location — surface-only, у sha-пиннутого `core_v2` нет
> consumer для ранжирующего сдвига), §5.1 «без токсиков» (moderation — surface/log, нет toxicity-фичи),
> §5.2 P2 ranking-only (класс/defer есть, ре-ранжирование по ответу — нет), §5.3 domain-critical
> (карта (domain,role)→поля есть, но апстрим-онбординг не всегда собирает platform/rank/level/skill).

### Базовая проверка (детально)

_✅ 3 · 🟡 6 · ⬜ 11_


**Реализовано (полностью / частично):**

- ✅ **§5.3 domain и activity/purpose** — В intent есть домен и цель активности. intent содержит type (домен/активность) и role/topics (цель); type ограничен допустимым множеством. — `services/matching/app.py:_fallback_parse:396-405`
- ✅ **§5.3 временной горизонт или явное «без точного времени»** — Поле времени с явным «Flexible». Поле time: инференс today/tomorrow/weekend, дефолт «Flexible» = без точного времени. — `services/matching/app.py:_fallback_parse:388-389,402`
- ✅ **§5.3 mode и participation format** — В intent есть mode и формат участия. intent содержит mode (offline/online) и format («1:1 or small group»). — `services/matching/app.py:_fallback_parse:401-402`
- 🟡 **§5 интро: недоверенный LLM → schema-validation + allowlists + normalizers + policy** — LLM как парсер, вывод проходит валидацию/allowlist/нормализацию. filtration приводит category/type к разрешённым множествам, topics→lowercase и обрезка до 4; parse_intent докидывает недостающие поля из fallback и нормализует topics. Формальной JSON-schema валидации нет; policy-check (hard-gates) применяется отдельно на этапе скоринга. — `services/filtration/app.py:categorize:119-130; services/matching/app.py:parse_intent:414-420`
- 🟡 **§5.1 «Только по-испански» → required language hard gate после summary confirmation** — Язык как hard-gate после подтверждения summary. Hard-gate по языку есть (requiredLanguages ⊆ языки кандидата), но парсер не заполняет requiredLanguages из фразы (дефолт []), а шага summary-подтверждения нет. — `services/matching/app.py:_hard_gates:444-446; _fallback_parse:405`
- 🟡 **§5.1 «Найти вторую половинку» → evergreen dating goal + dating mode** — Датинг-цель требует dating mode. Детект dating по ключевым словам → type=dating, ужесточение (verifiedOnly, minAge=18) и hard-gate на dating opt-in кандидата (datingOk). «Evergreen»/TTL не моделируется. — `services/matching/app.py:_fallback_parse:386,396,404; _hard_gates:437`
- 🟡 **§5.3 город/online либо разрешённый location fallback** — Город/online или location fallback. Есть mode online и radiusKm, но place — свободная строка с дефолтом «Public places nearby», без города и без policy location-fallback. — `services/matching/app.py:_fallback_parse:399,402-404`
- 🟡 **§5.3 минимальный набор domain-critical полей** — Domain-critical поля в intent. В intent из buddy попадает category (плюс subcategory из filtration); структурных domain-critical полей (платформа/ранг, native vs same-level) в intent нет. — `services/buddy/app.py:_build_intent:143; services/filtration/app.py:categorize:129`
- 🟡 **§5.3 fallback policy и disclosure summary** — Политика fallback и disclosure summary. Fallback-policy присутствует как флаги exactMatchRequired/adjacentAllowed/broadAllowed; disclosure summary в intent отсутствует. — `services/matching/app.py:_fallback_parse:405`

**⬜ Не реализовано (11):** `§5.1 «Желательно рядом» → soft location preference`, `§5.1 «Без токсиков» → domain constraint + moderation preference`, `§5.1 «Можно онлайн» → allowed fallback mode`, `§5.1 Правило подтверждения (sensitive/safety-ограничение → intent summary + confirm)`, `§5.2 P0 mandatory (без ответа не запускать sensitive flow, предложить альтернативу)`, `§5.2 P1 high value (unknown + lower confidence, без скрытого default)`, `§5.2 P2 ranking only (не спрашивать до первых результатов)`, `§5.2 P3 cosmetic (не спрашивать)`, `§5.2 Rule-based выбор вопроса (4 ordinal-фактора, минус friction)`, `§5.2 Не более одного вопроса до первых результатов (кроме mandatory safety)`, `§5.3 TTL и search budget`

## §6 Таксономия, evidence и смысловое расширение

_Базовая проверка: ✅ 3 · 🟡 13 · ⬜ 2._
_После реализации §6 (новый модуль [`shared/kleal_taxonomy.py`](../shared/kleal_taxonomy.py), read-only enrichment; без правки `core_v2.py`/конфига): **✅ 13 · ⬜ 0 · заблокировано sha-пином 6**._

> **Обновлено — реализован раздел §6** (разбор: [docs/TAXONOMY.md](TAXONOMY.md); тесты
> `services/matching/test_core_v2.py` секция `C6-*`, 18 проверок incl. negative-controls + PARITY-ENRICH;
> вся сюита 126/126 зелёная). Дизайн прошёл field-inventory + состязательный ревью (9 агентов, 8 must-fix
> свёрнуты: lazy-guarded-FS, guarded explain-hook, **не-вакуумный** alias-invariant через живой `graph_txn`,
> двухрежимный shadow-replay с negative-controls, additive-only дисциплина).
>
> **Закрыты оба ⬜:** §6 **Complementary role** — типизированная матрица (support↔carry, learner↔native…),
> `similarity:False`, не similarity; §6 **Governance** — 6 полей на ребро (owner/version/language_aliases/
> review_state/evidence/rollback) + `validate()` + shadow-replay (Mode B над живым скорером) + инвариант
> «alias не повышает score пары» (фальсифицируемый, с negative-control).
>
> **Стало ✅ также:** типизированные рёбра alias/exact/sibling/parent/adjacent (зеркало движкового `best`),
> `literal_token_share` для off-taxonomy (не выдуманное exact-ребро), **объяснение расширения**
> (`expand`: interest→sub→broad + онтологическая цепочка), alias+канон = один `evidence_id`,
> no-double-count нарратив, expansion-chain на карточках.
>
> **Заблокировано sha-пином (6)** — требуют координированного Dev-B version-bump `core_v2`/конфига, НЕ
> отдаётся read-only слоем: `SEM_VALUE {4:1.0,3:0.65,2:0.45,1:0.25}` как domain-config-параметр; sibling
> 0.55–0.75 из domain config; negative-edge как новый штраф скоринга; богатые per-group subfeatures с явной
> агрегацией; embedding recall; внутренности no-double-count остальных 6 групп. (Правка даже пробела в
> sha-пиннутом YAML валит `load_config` и роняет сервис на legacy — поэтому это осознанно вне слоя.)

### Базовая проверка (детально)

_✅ 3 · 🟡 13 · ⬜ 2_


**Реализовано (полностью / частично):**

- ✅ **§6 edge: Exact entity (1.0 внутри semantic subfeature, не суммировать с alias)** — Точное совпадение сущности = 1.0, без суммирования с alias. SEM_VALUE[4]=1.0 для exact/alias, и это ОДНА агрегированная subfeature semantic_activity (topical возвращает единственный best-tier), поэтому exact и alias не складываются. — `services/matching/core_v2.py:SEM_VALUE L171; build_features L207-217`
- ✅ **§6.1 семь feature groups определены** — Семь feature groups как в спеке. FEATURE_KEYS точно совпадает со спекой: semantic_activity, time_feasibility, location_feasibility, mode_format, directed_preferences, social_context, domain_constraints. Все используются в build_features и directional_score. — `services/matching/core_v2.py:FEATURE_KEYS L33-34; directional_score L332-345`
- ✅ **§6.1 один source statement учитывается один раз (no double count)** — Один statement — один учёт, без двойного счёта. Каждая группа даёт единственное значение, а semantic_activity сводит alias/parent-прочтения одного интереса в один matched-набор через topical (единственный best-tier), поэтому exact+alias+parent не превращаются в четыре независимых бонуса. — `services/matching/core_v2.py:build_features L200-217; app.py:topical L138-152`
- 🟡 **§6 edge: Alias (Dota 2 ↔ DOTA — одна сущность, тот же evidence_id)** — Alias-рёбра: варианты сводятся к одной сущности. SYNONYMS + _norm нормализуют алиасы к каноничной форме (soccer→football, lol→league, cs2→cs, ps5→playstation), поэтому алиас = та же сущность и не даёт отдельного бонуса. Понятия evidence_id нет. — `services/matching/app.py:SYNONYMS L76-91 / _norm L104-106; topical L138-152`
- 🟡 **§6 edge: Direct sibling (0.55–0.75 по domain config, только если broad allowed)** — Сиблинг-ребро с коэффициентом из domain config. Совпадение по под-категории даёт best=3 → SEM_VALUE[3]=0.65 (в диапазоне 0.55–0.75), тир T2; но 0.65 — жёсткая константа, НЕ параметр domain config, а «broad allowed» действует лишь как consent-гейт на outreach (T2), не на само значение. — `services/matching/core_v2.py:SEM_VALUE L171, assign_tier L366; search T2-gate L566,L581; app.py:topical L146`
- 🟡 **§6 edge: Parent (Dota 2 → MOBA → games, semantic_tier T2, объяснить расширение)** — Родительская категория → T2 с объяснением расширения. Совпадение по broad-категории даёт best=2 → SEM_VALUE[2]=0.45 и тир T2 (assign_tier). Причина показывается общей фразой «близкая тема / related topic»; настоящей цепочки-объяснения расширения (Dota→MOBA→games) нет. — `services/matching/core_v2.py:assign_tier L363-367; _REASON semantic_activity L478-479; app.py:topical L147`
- 🟡 **§6 edge: Adjacent purpose (кофе ↔ прогулка, T3, не personal push без consent)** — Смежная цель → T3, без личного пуша без согласия. ADJACENCY (связи между broad-категориями) даёт best=1 → тир T3; T3 никогда не проходит outreach_tier_ok (personal push исключён), а discovery T3 гейтится intent.adjacentAllowed. Но смежность грубая (broad↔broad), «смежная цель» как альтернативный social plan не моделируется. — `services/matching/core_v2.py:search L564,L581-584; app.py:ADJACENCY L95-98, topical L148`
- 🟡 **§6 edge: Negative edge (ranked competitive ↔ casual, penalty/constraint)** — Негативное ребро как штраф/ограничение. VIBE_CLASH (competitive↔chill, calm↔competitive и др.) даёт known_mismatch=0.25 в social_context; ROLE_CONFLICT штрафует конфликт ролей. Это матрицы штрафов, а не типизированное taxonomy-ребро; общая категория при этом не считается достаточной (mismatch понижает). — `services/matching/core_v2.py:VIBE_CLASH L173-174, build_features social_context L281-282; app.py:ROLE_CONFLICT L425`
- 🟡 **§6.1 subfeatures с фиксированной агрегацией и cap 1.0** — Subfeatures внутри группы с cap 1.0. На группу — ОДНА агрегированная subfeature; все значения по построению ≤1.0 (SEM_VALUE, geo-bands, ролевые/вайб значения), directional_score даёт взвешенное среднее ≤1. Множественных subfeatures с явной агрегацией внутри группы нет; явного min(1.0,·) тоже нет (cap соблюдается структурно). — `services/matching/core_v2.py:build_features L199-308; directional_score L327-350`
- 🟡 **§6.1 semantic_activity: не суммировать exact+alias+parent как 4 бонуса (вкл. embedding recall)** — semantic_activity без двойного счёта; embedding recall. topical возвращает единственный best-tier (exact/alias/parent/adjacent не складываются) — двойной счёт исключён. Embedding recall не реализован вовсе (эмбеддингов нет), recall только по словарной таксономии + _wshare. — `services/matching/core_v2.py:build_features L207-219; app.py:topical L138-152, _wshare L127-136`
- 🟡 **§6.1 time_feasibility: не суммировать start_time + текстовый тег evening** — time_feasibility без двойного счёта времени. Группа даёт одно значение только из флага cand.open + факта наличия intent.time; overlap/duration/recurrence/urgency и разбор start_time/evening-тегов не вычисляются, поэтому суммировать нечего (тривиально не дублируется). — `services/matching/core_v2.py:build_features L221-230`
- 🟡 **§6.1 location_feasibility: не суммировать район + координата + distance tags** — location_feasibility без тройного счёта дистанции. Считается одна дистанция (haversine по координатам или поле km) → одно значение по GEO_BANDS; отдельных «район», «координата», «distance tag» как независимых бонусов нет. Safe coarse zone/mode отдельно не моделируются. — `services/matching/core_v2.py:build_features L232-249, GEO_BANDS L172`
- 🟡 **§6.1 mode_format: не суммировать несколько синонимов small group** — mode_format без суммирования синонимов формата. Единственная проверка online/offline (mode в cand.formats или any/both) → одно значение; 1:1/group и синонимы «small group» не моделируются, суммирования синонимов нет. — `services/matching/core_v2.py:build_features L251-258`
- 🟡 **§6.1 directed_preferences: self profession ≠ target profession** — directed_preferences — целевая роль, не self-атрибут. Сопоставляется заявленная intent.role (цель) с cand.role — направленно, не берётся профессия самого искателя как target. Но моделируются лишь роли play/watch/meet; level/audience/profession отсутствуют. — `services/matching/core_v2.py:build_features L260-272`
- 🟡 **§6.1 social_context: LLM personality labels без подтверждения не суммируются** — social_context без неподтверждённых LLM-меток. Используется только сохранённое поле vibe (mv/cv) + матрица VIBE_CLASH; неподтверждённые LLM-метки личности вообще не поступают в скоринг, значит и не учитываются. — `services/matching/core_v2.py:build_features L274-284`
- 🟡 **§6.1 domain_constraints: общая категория вместо обязательного domain field не засчитывается** — domain_constraints не подменяет обязательное поле категорией. При отсутствии обязательного поля (platform/server/level ещё не собираются) группа отдаёт unknown/NA, а не кредитует общую категорию; для language_exchange проверяется реальная языковая пара, для games/sport — совпадение entity/community. Сами domain-поля в основном не собираются. — `services/matching/core_v2.py:build_features L286-306`

**⬜ Не реализовано (2):** `§6 edge: Complementary role (support ↔ carry; learner ↔ native, role matrix, не similarity)`, `§6 Governance (owner/version/aliases/review/evidence/rollback per edge; shadow replay; alias не повышает score пары)`

## §7 Candidate retrieval и semantic tiers

_Базовая проверка: ✅ 6 · 🟡 7 · ⬜ 3._
_После реализации §7 (read-only слой в `services/matching/app.py`; без правки `core_v2.py`/конфига): **✅ 12 · 🟡 2 · blocked_infra 1 · pilot_disabled 1**._

> **Обновлено — реализован раздел §7** (разбор: [docs/RETRIEVAL.md](RETRIEVAL.md); тесты `C7-*`, 8 проверок
> incl. фальсифицируемая slate-safety; вся сюита 134/134 зелёная). Дизайн — field-inventory + состязательный
> ревью (инвентарь точно разметил, какие тесты идут через `load_candidates` vs прямой `core_v2.search`, и
> подтвердил: тотальная сортировка в `search` делает порядок retrieval невидимым для slate — изменить его
> может только выбрасывание overlapping-кандидата).
>
> **Несущая гарантия:** retrieval-бюджет (дефолт 500 ≫ ~100-стора) на пилотном масштабе **не срабатывает**;
> когда режет — отбрасывает только no-overlap хвост (T5), который движок и так не показывает; `_expand_fallback`
> получает полный пул. `C7-BUDGET-BITE`: бюджет 2 из 5 реально режет, slate byte-identical.
>
> **Стало ✅:** источники 1/2/5 (`retrieval_source` на карточках, из реципрокности/прямого интереса/adjacent);
> источник 4 как **T4 alternative_solution_type** (онлайн-комната); tier-table T4 назначается; staged
> structured-retrieval budget (механизм + порядок); **аналитика relevance ВНУТРИ каждого tier**
> (`explain.tier_analytics` — закрыт ⬜); 7-этапный retrieval-отчёт в ответе.
>
> **🟡 partial (2):** hard_prefilter (SQL/PostGIS/H3 — infra; детерминированный in-mem prefilter + бюджет —
> stdlib-эквивалент); agent_probe (negotiate top-5, не таргетированный probe top 1-3 неизвестных полей).
> **blocked_infra (1):** ANN recall — pgvector embeddings, вне stdlib-прототипа. **pilot_disabled (1):**
> источник 3 — группы с capacity (§15).

### Базовая проверка (детально)

_✅ 6 · 🟡 7 · ⬜ 3_


**Реализовано (полностью / частично):**

- ✅ **§7.1 источник 5: parent/adjacent только при разрешённом расширении** — Источник 5 — расширение под контролем. search() отбрасывает T3 (adjacent) при adjacentAllowed=False и T2 (parent) при exactMatchRequired; расширение включается только в _expand_fallback (adjacentAllowed=True, exactMatchRequired=False + сброшенный discovery-floor). — `services/matching/core_v2.py:search (564-567); services/matching/app.py:_expand_fallback (634-643)`
- ✅ **§7.1 personal outreach по tier (T0/T1 да; T2 при broad consent; T3–T5 нет)** — Personal outreach по tier. outreach_tier_ok = tier∈{T0,T1} или (T2 и broadConsent); can_outreach дополнительно требует readiness=open_now и порогов lcb/coverage. Тот же тир/consent-гейт продублирован на границе отправки в _outreach_ok. — `services/matching/core_v2.py:search (581-584); services/matching/app.py:_outreach_ok (758-766)`
- ✅ **§7.1 semantic tier immutable provenance (логистика не повышает tier)** — Tier — неизменяемый provenance. tier вычисляется assign_tier только из топикального/реципрокного совпадения, независимо от модификаторов и логистики, и кладётся в card.tier/trace как provenance; score-модификаторы его не меняют. — `services/matching/core_v2.py:assign_tier (358); search trace (612-615)`
- ✅ **§7.2 Feature build: canonical evidence groups; 30-80→10-30; без LLM** — Feature build. build_features строит 7 канонических групп доказательств (semantic/time/geo/mode/role/vibe/domain) со статусами known_match/known_mismatch/unknown/not_applicable, детерминированно и без LLM. Бюджетного среза 30-80→10-30 как такового нет (сужение идёт позже через disc_ok), но канонические группы реализованы полностью. — `services/matching/core_v2.py:build_features (199-308)`
- ✅ **§7.2 Ranking/slate: relevance + reciprocity + allocation; 10-30→3-8; без LLM** — Ranking/slate. directional_score (lcb/coverage) + reciprocal_score + assign_band + _slate (allocation: TOP_N=8, ≤3 на bucket) — полностью детерминированно, без LLM, выдача до 8. — `services/matching/core_v2.py:search (568-620); _slate (530-542)`
- ✅ **§7.2 Explanation: reason keys → natural language; только финальный slate** — Explanation (reason keys→NL). _presentation переводит reason keys подтверждённых (known_match) фич в RU/EN формулировки (+ верхний gap) шаблонно, без LLM; в ответе остаются только элементы финального slate. Спека допускает и шаблон, и модель. — `services/matching/core_v2.py:_presentation (497-525); search (585)`
- 🟡 **§7.1 источник 1: активные intent с точным/прямым совпадением** — Источник 1 — активные intent. Собственные активные intent кандидата (c.intents) распознаются _reciprocal как реципрокное совпадение и дают tier T0, сортируемый первым. Отдельного приоритезированного «источника» извлечения нет — один общий пул load_candidates, tier назначается при обходе. — `services/matching/core_v2.py:assign_tier (359); services/matching/app.py:_reciprocal (456)`
- 🟡 **§7.1 источник 2: пользователи с активным receiving policy и прямым интересом** — Источник 2 — receiving policy + прямой интерес. receiving policy кандидата читается (readiness_state) для доступности/outreach, прямой интерес (best>=4) даёт tier T1. Но политика — гейт доступности и сортировки, а не отдельный источник извлечения. — `services/matching/core_v2.py:readiness_state (427); assign_tier (363)`
- 🟡 **§7.1 источник 4: события и комнаты как альтернатива закрыть intent** — Источник 4 — события/комнаты. Отдельного источника событий/групп-кандидатов нет. При 0 кандидатов _online_fallback предлагает создать голосовую/watch-комнату как альтернативу — это UI-CTA, а не извлечённый кандидат. — `services/matching/app.py:_online_fallback (677)`
- 🟡 **§7.1 таблица tier: назначение T0–T5 как provenance** — Таблица semantic tiers T0–T5. assign_tier даёт T0 (реципрокный intent), T1 (точный best>=4), T2 (parent/sibling), T3 (adjacent), T5 (нет overlap). T4 «alternative solution type» тайрингом не назначается — метка T4 ставится только fallback'ом на ближайших людей, не на событиях/группах. — `services/matching/core_v2.py:assign_tier (358-369); TIER_KIND (371)`
- 🟡 **§7.2 Hard prefilter: SQL/PostGIS/H3, status, TTL, privacy; 1000→100-250; без LLM** — Hard prefilter. _hard_gates — детерминированные исключения до скоринга (paused/block, cooldown, pending, 18+, dating-opt-in, verified, age range, язык, radiusKm), без LLM. Нет SQL/PostGIS/H3-индексов, TTL, privacy-полей и бюджетных срезов 1000→250; проход по всему пулу в памяти. — `services/matching/app.py:_hard_gates (428-452)`
- 🟡 **§7.2 Structured retrieval: domain indexes, active intents, taxonomy; 100-250→30-80; без LLM** — Structured retrieval. Домен выводится (infer_domain), таксономия и активные intent используются для тайринга по всему пулу, без LLM. Индексов и бюджетных срезов 100-250→30-80 нет — полный скан. — `services/matching/core_v2.py:infer_domain (146-164); assign_tier (358)`
- 🟡 **§7.2 Agent probe: allowlisted unknowns; только top 1-3; малая модель/шаблон** — Agent probe. negotiate_candidates шлёт LLM-негоциацию (negotiate_one) верхним кандидатам с параллельным капом 2/3 из конфига. Но берётся top-5 (top = cands[:5]), не 1-3, и это переговоры accept/reject, а не таргетированный probe именно неизвестных allowlisted-полей. — `services/matching/app.py:negotiate_candidates (826-828); _negotiate_precheck cap (781-782)`

**⬜ Не реализовано (3):** `§7.1 источник 3: существующие группы с capacity`, `§7.1 аналитика relevance внутри каждого tier`, `§7.2 ANN recall: pgvector embeddings внутри пула; +top 50; без LLM`

## §8 Eligibility, privacy, safety, purpose binding

_Базовая проверка (УСТАРЕЛА — ссылалась на до-рефакторный app.py и помечала ⬜ уже сделанное в §0/§4/§6): ✅ 5 · 🟡 9 · ⬜ 18._
_После реализации §8 + сверки: **done_prior_section 10 · done 6 · partial 12 · blocked_infra 5** (33 подпункта)._

> **Обновлено — реализован раздел §8** (разбор: [docs/ELIGIBILITY.md](ELIGIBILITY.md); тесты `C8-*`, 12
> проверок incl. `C8-GENPOOL-IDENTITY` — byte-identity над реальным `_gen_pool`; вся сюита 146/146 зелёная).
> Дизайн — field-inventory + состязательный ревью (must-fix: cross-purpose из **своих** intents кандидата,
> shared helper retrieval+send, новые гейты **последними** в `_hard_gates`, позитивный byte-identity тест).
>
> **Сверка устаревшего базового отчёта:** уже сделано РАНЬШЕ (baseline ошибочно ⬜/🟡): REVIEW-статус
> (`_policy_decision` — §0); §8.3 контекстные профили + purpose binding + Match Capsule (`build_profile_view`/
> `DOMAIN_TO_CONTEXT`/`PURPOSE_FIELDS`/`build_match` — §4/§6); §8.2 #1 (перед slate) и #2 (перед отправкой).
>
> **Стало ✅ (в §8):** §8.1 гейты account_status / privacy-visibility / safety-restrictions (BLOCK; absent→ALLOW);
> intent-mode isolation (`_cross_purpose_blocked`, retrieval+send, из своих intents); age/location REVIEW
> (opt-in `soft_eligibility`, дефолт сохраняет BLOCK); §8.2 `revalidate` + **POLICY_CHANGED** + `POST
> /api/agent/revalidate` + #3 (profile-open) + #4 (on-accept re-gate); §8.4 reveal-ladder (exact place только
> после Match Capsule), home/work-scrub из карточки, slot-feasibility skeleton.
>
> **partial / DORMANT (12):** гейты по НОВЫМ полям (account/privacy/safety/mode) — additive-safe, но дремлют,
> пока admin/onboarding не пишут поля в стор; account_status unknown⇒ALLOW (осознанное отклонение от
> unknown⇒BLOCK); #5 shared-chat / #6 reveal-contact enforcement — cross-service (buddy/profile); #7 без
> event-bus (синхронная перечитка). **blocked_infra (5):** suspension-бэкенд, H3-cells, полная
> interval-algebra + DST/travel-mode, per-user исходный timezone.

### Базовая проверка (детально)

_✅ 5 · 🟡 9 · ⬜ 18_


**Реализовано (полностью / частично):**

- ✅ **§8 intro: scoring только после ALLOW** — Скоринг стартует только после решения ALLOW. match_candidates прогоняет _hard_gates по каждому кандидату и в _core.search передаёт только прошедших — оценка идёт исключительно по ALLOW-пулу. — `services/matching/app.py:match_candidates:619-629`
- ✅ **§8.1 gate: mutual block** — Гейт взаимной блокировки. Двусторонняя проверка: список owner-blocked (gate_ctx['blocked']) и флаг кандидата blocksMe дают BLOCK. — `services/matching/app.py:_hard_gates:431`
- ✅ **§8.1 gate: fatigue / receiving readiness** — Гейт усталости/готовности приёма (BLOCK для outreach, не для discovery). readiness_state даёт busy при received_24h>=cap, а также quiet-hours/paused; отправка блокируется при readiness!=open_now, но кандидат остаётся видимым в подборке. — `services/matching/core_v2.py:readiness_state:427-459; services/matching/app.py:_negotiate_precheck:799-809`
- ✅ **§8.2 #1: перед добавлением в slate** — Повторная проверка перед добавлением кандидата в slate. match_candidates заново прогоняет _hard_gates по каждому кандидату непосредственно перед скорингом и формированием slate. — `services/matching/app.py:match_candidates:620-629`
- ✅ **§8.2 #2: перед отправкой proposal** — Повторная проверка непосредственно перед отправкой proposal. _negotiate_precheck пере-резолвит кандидата из live-стора и повторяет _hard_gates + _outreach_ok + readiness на границе отправки. — `services/matching/app.py:_negotiate_precheck:768-824`
- 🟡 **§8 intro: BLOCK не в ranking/explanation/probe** — Заблокированный не попадает в ранжирование, объяснение и probe. BLOCK не входит в eligible и переотсеивается перед negotiate. Но explain_match всё же перечисляет заблокированных в excluded с причиной гейта. — `services/matching/app.py:match_candidates:623-625; _negotiate_precheck:792-795; explain_match:920-922`
- 🟡 **§8.1 gate: age / legal eligibility** — Гейт возраста и legal eligibility. Жёсткий пол 18+ (MIN_AGE) и диапазон minAge/maxAge реализованы как BLOCK; при заданном диапазоне неизвестный возраст блокируется. Базовый пол при age=None не блокирует, состояния REVIEW нет. — `services/matching/app.py:_hard_gates:435-443`
- 🟡 **§8.1 gate: intent mode isolation** — Изоляция режимов intent (friendship/dating/professional/language). Изолирован только dating: кандидат без datingOk блокируется. Прочие режимы не проверяются; receiving.allowed_domains лишь понижает до passive_discovery, не блокирует ретрив. — `services/matching/app.py:_hard_gates:437; services/matching/core_v2.py:readiness_state:447-449`
- 🟡 **§8.1 gate: location policy** — Гейт локации (зона допустима без точного адреса). Радиус-гейт блокирует offline-кандидата при km>radiusKm по грубой дистанции (не точный адрес); §12-fallback расширяет зону. «Вне радиуса» — жёсткий BLOCK, состояния REVIEW нет. — `services/matching/app.py:_hard_gates:447-451; _expand_fallback:634-648`
- 🟡 **§8.1 gate: language feasibility** — Гейт языковой совместимости. _hard_gates блокирует, если requiredLanguages из intent не подмножество языков кандидата. Уровень владения не моделируется; при пустом requiredLanguages гейт не срабатывает. — `services/matching/app.py:_hard_gates:444-446`
- 🟡 **§8.1 gate: capacity** — Гейт вместимости (user/group/event/room). Есть только пер-юзер лимит: pending>=MAX_PENDING(6) → BLOCK, а proposal_budget.per_24h даёт readiness=busy. Вместимости групп/событий/room нет. — `services/matching/app.py:_hard_gates:434; services/matching/core_v2.py:readiness_state:443-446`
- 🟡 **§8.2 #7: после изменения состояния** — Ревалидация после изменения privacy/block/suspension/age/capacity/intent version. Событийного триггера нет; но перед отправкой кандидат заново читается из live-стора, поэтому изменившиеся block/age/capacity/radius перепроверяются на send-границе. — `services/matching/app.py:_negotiate_precheck:776-792`
- 🟡 **§8.4: retrieval по зоне/радиусу, точная локация не в payload** — Ретрив по зоне/H3/району/радиусу; точная live-локация не в payload. Используются грубые coarseLat/coarseLon и km + радиус-гейт + GEO_BANDS (точную live-локацию демо-пул не хранит; _latlon умеет читать и lat/lon, если поданы). H3-cell и район не реализованы. — `services/matching/core_v2.py:_latlon:185-194; GEO_BANDS:172; services/matching/app.py:_hard_gates:447-451`
- 🟡 **§8.4: UTC + исходный tz, сравнение после нормализации** — Хранение времени в UTC с исходным timezone и сравнение после нормализации. quiet-hours считаются по epoch now_ts + фиксированный tz_offset_min (по умолчанию 120, Мадрид-лето) в local minutes; сравнение — после нормализации. Настоящего per-user исходного timezone / UTC-хранения нет. — `services/matching/core_v2.py:readiness_state:451-456; _in_quiet_hours:397-403`

**⬜ Не реализовано (18):** `§8 intro: статус REVIEW`, `§8.1 gate: account_status`, `§8.1 gate: privacy visibility`, `§8.1 gate: time feasibility`, `§8.1 gate: safety restrictions`, `§8.1 gate: disclosure policy`, `§8.2 #3: при открытии профиля после задержки`, `§8.2 #4: при принятии proposal`, `§8.2 #5: перед созданием общего чата`, `§8.2 #6: перед раскрытием места/контактов`, `§8.2: код POLICY_CHANGED`, `§8.3: контекстные профили`, `§8.3: purpose binding полей`, `§8.3: Match Capsule`, `§8.4: домашний/рабочий адрес не точка discovery`, `§8.4: available_from/until, min_duration, дорожный буфер`, `§8.4: DST/поездки/travel mode в тестах`, `§8.4: раскрытие места после взаимного согласия`

## §9 Математическая модель: relevance, evidence и uncertainty

_Базовая проверка: ✅ 18 · 🟡 8 · ⬜ 2._
_После верификации + §9.5/§9.6 слоя: **done_core_v2 15 · done 4 · partial 8 · blocked_sha_pinned 1 · blocked_calibration 1** (29 подпунктов)._

> **Обновлено — §9 верифицирован + добавлен CI/decision-class слой** (разбор: [docs/RELEVANCE_MATH.md](RELEVANCE_MATH.md);
> тесты `C9-*`, 17 проверок; вся сюита 163/163 зелёная). Дизайн — формула-за-формулой ревью core_v2 vs §9
> (6 агентов, must-fix: T2-no-consent→no_personal_outreach, REVIEW→no_personal_outreach до clarification,
> `.get()`-guards, non-mutating validator).
>
> **Проверено EXACT в sha-пиннутом core_v2 (done_core_v2):** §9.1 четыре состояния (NA исключён из
> знаменателя, unknown→prior понижает coverage), §9.3 R_mean/Coverage/R_lcb=clamp(mean−λ(1−cov)), §9.4
> directional + reciprocal=0.7·min+0.3·mean, «reciprocal — НЕ вероятность» (нет P_accept), веса только в
> config, §9.7 band не процент. §9.2 — EXACT кроме `confidence_k` (свёрнут к 1.0).
>
> **Стало ✅ (в §9, orchestration-слой):** §9.5 CI-валидатор (`_validate_math_config`, read-only, НЕ мутирует
> config): evidence_id-uniqueness + config↔policy↔engine version-compat + band-cut ranges + non-mutating
> echoes load_config; виден в `weights.config_ci`. §9.6 read-only `decision_class` 5-way
> (strong/usable/discovery/clarification/no_personal_outreach) из движковых сигналов, аддитивно, slate
> byte-identical. Math-инвариант тесты.
>
> **partial (8):** decision_class на slate-пути консервативен (полная точность в explain); band-cut CI
> дублирует статический schema.json; и т.п. **blocked_sha_pinned (1):** `confidence_k`-blend (в запечатанном
> движке). **blocked_calibration (1):** `P_accept/P_response/P_completion` (нужны данные калибровки + версия модели).

### Базовая проверка (детально)

_✅ 18 · 🟡 8 · ⬜ 2_


**Реализовано (полностью / частично):**

- ✅ **§9.1 четыре состояния признака** — known_match / known_mismatch / unknown / not_applicable для каждой feature group. build_features присваивает каждой из 7 групп ровно одно из 4 состояний (K_MATCH/K_MISM/UNKNOWN/NA). directional_score: unknown→prior, known→наблюдаемое значение, not_applicable исключается из знаменателя. — `services/matching/core_v2.py:build_features (199-308), directional_score (327-350)`
- ✅ **§9.1 инвариант: unknown ≠ совпадение, sparse не обгоняет full** — unknown снижает coverage; разреженный профиль не обгоняет заполненный. unknown добавляет w*prior в acc, но не в kw, поэтому coverage падает и группа попадает в unknowns. Тест C1b проверяет, что полный профиль по lcb выше разреженного. — `services/matching/core_v2.py:directional_score (340-345); test_core_v2.py C1a-C1e (58-66)`
- ✅ **§9.2 диапазон [0,1] для observed values и priors** — все наблюдаемые значения и priors в [0,1]. Якоря наблюдений (SEM_VALUE, GEO_BANDS, mismatch-константы 0.05..0.25) лежат в [0,1]. Priors из YAML, load_config валидирует unknown_prior в диапазоне 0..1. — `services/matching/core_v2.py SEM_VALUE/GEO_BANDS (171-172); load_config (112-115)`
- ✅ **§9.3 R_mean = Σ(w·adjusted)/Σw** — взвешенное среднее relevance по применимым группам. directional_score копит acc = Σ w·adjusted по всем не-NA группам и делит на tw = Σ w, возвращая mean. — `services/matching/core_v2.py:directional_score (346-350)`
- ✅ **§9.3 Coverage = Σ(w·known)/Σw** — доля веса, подтверждённого известными признаками. kw копит вес только для known_match/known_mismatch (не для unknown), coverage = kw/tw. — `services/matching/core_v2.py:directional_score (343-348)`
- ✅ **§9.3 R_lcb = clamp(mean − λ_domain·(1−Coverage), 0, 1)** — консервативная нижняя оценка; λ из конфига, выше для dating/safety. lcb = max(0,min(1, mean − lam·(1−cov))), lam = uncertainty_lambda домена из YAML. В конфиге dating=0.35, games/sport/lang/networking=0.3 против culture=0.22 — выше для чувствительных доменов. — `services/matching/core_v2.py:directional_score (329,349); config/Kleal_Matching_Core_Config_v2.yaml uncertainty_lambda (54,82,124,181)`
- ✅ **§9.4 раздельные R_A_to_B и R_B_to_A** — направленная релевантность в обе стороны. search считает d_ab по build_features(A→B) и d_ba по reverse_features (псевдо-intent из активного интента B либо его интересов как receiving-предпочтений). — `services/matching/core_v2.py:search (568-571), reverse_features (315-324)`
- ✅ **§9.4 R_reciprocal = 0.70·min + 0.30·mean** — двусторонняя релевантность, штрафующая односторонние пары. reciprocal_score(a,b) = round(0.7·min(lcb) + 0.3·mean(lcb),4) над консервативными lcb обеих сторон; используется в trace и в сортировке слейта. — `services/matching/core_v2.py:reciprocal_score (352-355), search (572,619)`
- ✅ **§9.4 запрет P_accept/P_response/P_completion без калибровки** — reciprocal не выдаётся как вероятность принятия. Код нигде не вычисляет и не показывает P_accept/P_response/P_completion; работает только rule-based lcb/reciprocal. config score_semantics фиксирует acceptance_probability как отсутствующую в MVP. — `services/matching/core_v2.py scoring (327-355); config score_semantics (249)`
- ✅ **§9.5 веса не дублируются в коде** — единственный набор весов — в canonical config. core_v2 не содержит tunable-весов доменов (только семантические якоря наблюдений); веса групп берутся из cfg['domains'][d]['weights'] YAML. — `services/matching/core_v2.py:directional_score (328), search (550); config domains.*.weights (46-53 и т.д.)`
- ✅ **§9.5 CI: сумма весов домена = 1.0** — проверка нормировки весов каждого домена. load_config суммирует 7 весов домена и падает с ConfigError при |сумма−1.0|>1e-6; тест V2 проверяет отказ на сломанной сумме. — `services/matching/core_v2.py:load_config (124-126); test_core_v2.py V2 (159-167)`
- ✅ **§9.5 CI: отсутствие неизвестных feature keys** — запрет чужих ключей в весах домена. load_config сравнивает ключи весов с FEATURE_KEYS и падает при лишних ключах. — `services/matching/core_v2.py:load_config (121-123)`
- ✅ **§9.6 no personal outreach (ниже порогов / нет consent / receiving policy запрещает)** — решение «без персонального аутрича». can_outreach=False при несоответствии tier/consent, readiness≠open_now или lcb/cov ниже outreach-порогов. readiness_state даёт passive_discovery/busy/paused/open_later, запрещая персональный аутрич. — `services/matching/core_v2.py:search (581-584), readiness_state (427-459)`
- ✅ **§9.6 пороги версионируются** — decision thresholds как версионируемая конфигурация. Все floors и bands лежат в sha-pinned YAML с config_version; load_config сверяет sha256 и наличие config_version, при расхождении бросает ConfigError (откат на legacy у вызывающего). — `services/matching/core_v2.py:load_config (100-136), PINNED_SHA (31)`
- ✅ **§9.7 запрет показа «92% совместимости»** — нельзя показывать сырой процент совместимости. profile UI функцией mBand отображает качественный ярлык (Top/Strong/Broad/Maybe), а не процент; внутренний score (lcb*100) наружу как процент не выводится. — `services/profile/app.py:mBand (1098-1102), scr_matchchat (1110)`
- ✅ **§9.7 2–3 подтверждённые причины (без выдуманных фактов)** — к результату прилагаются 2–3 known_match причины. _presentation берёт до 3 групп только со статусом known_match, отсортированных по вкладу w·v; тест C23 подтверждает, что для unknown-групп причины не выдумываются. — `services/matching/core_v2.py:_presentation (497-506); test_core_v2.py C23 (141-145)`
- ✅ **§9.7 один существенный компромисс** — к результату прилагается один компромисс/пробел. _presentation возвращает один gap (gap_ru/gap_en): топ known_mismatch по весу, иначе топовый unknown. — `services/matching/core_v2.py:_presentation (517-525)`
- ✅ **§9.7 числовой процент только после калибровки/approval** — процент допустим лишь после калибровки и formal approval. Процент нигде не показывается; пользователю выводится только качественный band. config score_semantics фиксирует relevance как внутреннюю эвристику, не human-compatibility-процент. — `services/profile/app.py:mBand (1096-1102); config score_semantics (245)`
- 🟡 **§9.2 нормализация: adjusted = conf×obs + (1−conf)×prior** — confidence-взвешенное смешивание наблюдения и prior для known. Реализованы ветки unknown→prior и not_applicable→вес 0. Для known берётся наблюдаемое значение напрямую (acc += w*v), т.е. confidence_k неявно равен 1; отдельного confidence_k и смешивания с prior нет. — `services/matching/core_v2.py:directional_score (336-345)`
- 🟡 **§9.5 CI: диапазоны priors, penalties и thresholds** — валидация диапазонов числовых параметров конфига. Проверяются диапазоны 0..1 для unknown_prior и для порогов (uncertainty_lambda, outreach/discovery min_lcb/coverage). Penalties (mismatch-значения 0.05/0.25/0.2/0.15/0.1) захардкожены в core_v2, в конфиге отсутствуют и не валидируются. — `services/matching/core_v2.py:load_config (112-131); mismatch-константы build_features (219,228,258,270,282,293)`
- 🟡 **§9.6 strong personal candidate (ALLOW, lcb≥0.72, cov≥0.70, T0–T1)** — порог «сильного» персонального кандидата. Есть единый outreach-гейт: tier T0/T1 (или T2+consent) + open_now + lcb≥outreach_min_lcb + cov≥outreach_min_coverage домена. Отдельного уровня «strong» с порогами 0.72/0.70 нет — используется один доменный порог (social_meet 0.66/0.6). — `services/matching/core_v2.py:search (581-584); config outreach_min_lcb/coverage (55,57)`
- 🟡 **§9.6 usable personal candidate (lcb≥0.58, cov≥0.55, T0–T2, broad consent при T2)** — порог «пригодного» персонального кандидата. outreach_tier_ok = T0/T1 либо T2 при broadConsent — часть про consent реализована. Но двухуровневого разделения strong/usable с порогами 0.58/0.55 нет: единый доменный outreach-порог. — `services/matching/core_v2.py:search (581-584)`
- 🟡 **§9.6 discovery only (lcb≥0.45, tier T3–T4 или низкое coverage)** — уровень «только в подборке». disc_ok по discovery_min_lcb/coverage домена; слабые непрямые кандидаты (не T0/T1) отсекаются, прямые остаются как needs_clarification. Тир T4 (alternative solution type) в assign_tier не моделируется (только T0–T3, T5). — `services/matching/core_v2.py:search (573-578), assign_tier (358-369)`
- 🟡 **§9.6 clarification / probe (high-impact unknown, top 1–3)** — решение «уточнение/зондирование». Прямые T0/T1 ниже discovery-порога остаются видимыми с band=needs_clarification и can_outreach=False. Активного probe (задать вопрос) и ограничения на top 1–3 high-impact-unknown кандидата нет. — `services/matching/core_v2.py:search (575-578,595)`
- 🟡 **§9.7 четыре пользовательских бэнда** — Особенно близко / Хороший / Более широкий / Альтернативный способ. assign_band + BAND_LABELS дают especially_close/strong_option/broader_option с точными русскими подписями. Четвёртый спековый бэнд «Альтернативный способ закрыть запрос» (T4) не реализован — вместо него «Нужно уточнение» (needs_clarification). — `services/matching/core_v2.py:assign_band (470-475), BAND_LABELS (462-467)`
- 🟡 **§9.7 отметка «часть данных ещё не подтверждена»** — пометка неполноты данных при необходимости. Есть band «Нужно уточнение», список unknowns и текст gap про неподтверждённые поля. Отдельной явной отметки «часть данных ещё не подтверждена» как самостоятельного элемента нет. — `services/matching/core_v2.py:_presentation gap (517-525), search unknowns (610)`

**⬜ Не реализовано (2):** `§9.5 CI: уникальность evidence_id внутри feature groups`, `§9.5 CI: совместимость config version с model/policy version`

## §10 Reciprocity, readiness и вероятность результата

_Базовая проверка: ✅ 5 · 🟡 4 · ⬜ 11._
_После верификации + §10.2/§10.3 слоя: **done_core_v2 8 · done 6 · partial 5 · pilot_disabled 1 · blocked_calibration 4** (24 подпункта)._

> **Обновлено — §10 верифицирован + добавлены completion_factors / ml_boundary** (разбор:
> [docs/READINESS_COMPLETION.md](READINESS_COMPLETION.md); тесты `C10-*`, 11 проверок; вся сюита 174/174
> зелёная). Дизайн — верификация core_v2 vs §10 (6 агентов, verdict go).
>
> **Проверено EXACT в sha-пиннутом core_v2 (done_core_v2):** §10 intro relevance⟂readiness (не суммируются
> — readiness это гейт+ключ сортировки, не слагаемое lcb); §10.1 все шесть состояний readiness
> (open_now/open_later/passive_discovery/busy/paused/unknown), domain-dependent; reciprocity 0.7·min+0.3·mean.
>
> **Стало ✅ (в §10, orchestration-слой, read-only):** §10.1 `readiness_explain` (объяснение 6 состояний на
> карточке + в `weights.readiness_states`); §10.2 `completion_factors` — **прозрачные** сигналы
> (availability_fresh / capacity_headroom+active_plans / technical_compat), **БЕЗ агрегата** (`aggregate_score:
> None`), явные `excludes` (safety/sensitive/single-review по реальным именам, ни одно значение не течёт);
> §10.3 `ml_boundary` — 6-слойный roadmap, `P_response/P_accept/P_completion = absent_by_design` (не стабятся),
> инвариант **no_model_in_gates** (рантайм-статика: в гейтах нет `llm_complete`).
>
> **partial (5):** 4 из 7 completion-сигналов ждут сбора данных (response_latency, no_show, candidate-side
> min_duration, budget-context). **pilot_disabled (1):** host/venue/room (group/event). **blocked_calibration
> (4):** calibrated P_response/P_accept/P_completion + learning-to-rank (нужны данные + версия модели).

### Базовая проверка (детально)

_✅ 5 · 🟡 4 · ⬜ 11_


**Реализовано (полностью / частично):**

- ✅ **§10 (intro): relevance и readiness не складываются** — Readiness отдельно от relevance. readiness_state — отдельная функция; в search() она вычисляется после скоринга и участвует только в can_outreach и как вторичный ключ сортировки слейта, не входя в lcb/coverage/reciprocal. Комментарий 374-376 цитирует спеку «эти величины не складываются». — `core_v2.py:search:579-620 (sort key 619), readiness_state:427; comment 374-376,617-618`
- ✅ **§10.1 таблица состояний (open_now/open_later/passive_discovery/busy/paused/unknown)** — Шесть состояний receiving readiness. Все 6 состояний возвращаются readiness_state и присутствуют в READINESS_LABELS; источники по приоритету: paused → receiving.status busy → proposal_budget → allowed_domains → quiet_hours → passive_outreach → open_now, иначе legacy open-флаг, иначе unknown. paused исключается из retrieval (search:559), unknown не даёт personal outreach. — `core_v2.py:readiness_state:427-459, READINESS_LABELS:377-384, is_paused:414-425`
- ✅ **§10.1 readiness зависит от домена** — Доменно-зависимая готовность. readiness_state принимает параметр domain; при непустом allowed_domains, если запрошенный домен не в списке, возвращается passive_discovery — открыт для одного домена, закрыт для другого. — `core_v2.py:readiness_state:447-449`
- ✅ **§10.2 запрет: safety/sensitive/единичный негатив не становятся непрозрачным рейтингом** — Нет непрозрачного соц-рейтинга. В core_v2-скоринге нет completion-скора или соц-рейтинга: search() не использует feedback/reports, safety не превращается в балл. record_feedback лишь хранит accept/reject в сессионном сторе и в скоринг не попадает. — `core_v2.py:search:557-620 (нет feedback/rating), app.py:record_feedback:226-230`
- ✅ **§10.3 запрет: hard gates/privacy/purpose binding/block/capacity/disclosure остаются deterministic policy** — Гейты/политика остаются детерминированными. Скоринг и гейты полностью детерминированы, ML в ранжировании нет: hard gates, block, capacity (proposal budget), domain/tier-binding — код-политика, а не модель. — `app.py:_hard_gates:428-438, core_v2.py:search:558-584, readiness_state:427-459`
- 🟡 **§10.2 (intro): completion — не отдельный балл, прозрачные operational signals** — Нет completion-балла, прозрачные сигналы. Отдельного «балла completion» нет; readiness строится на прозрачных сигналах (received_24h, тихие часы, paused/busy). Большинство перечисленных operational signals не реализовано. — `core_v2.py:readiness_state:443-458, app.py:_proposals_received_24h:221`
- 🟡 **§10.2 сигнал: актуальность availability** — Актуальность доступности. quiet_hours и receiving.status/paused_until отражают текущую доступность и гейтят outreach, но свежесть/актуальность самих availability-данных как отдельный сигнал не отслеживается. — `core_v2.py:readiness_state:450-456, is_paused:414-425`
- 🟡 **§10.2 сигнал: capacity и число активных планов** — Ёмкость / активные планы. proposal_budget.per_24h + _proposals_received_24h переводят человека в busy при перегрузе за сутки (proposal fatigue). Это счётчик ПОЛУЧЕННЫХ предложений, а не число активных планов/встреч. — `core_v2.py:readiness_state:443-446, app.py:_proposals_received_24h:221, _log_proposal:211`
- 🟡 **§10.3 слой 1: intent classification + slot extraction** — ML-слой 1 (интент/слоты). parse_intent через LLM извлекает topics/mode/role/time (slot extraction) с детерминированным _fallback_parse. Это hand-prompt LLM, а не обучаемая/калиброванная модель. — `app.py:parse_intent:407-423, _fallback_parse:379-405`

**⬜ Не реализовано (11):** `§10.1 механизмы open_later «сохранить, отправить позже» и unknown-probe`, `§10.2 сигнал: согласование минимальной длительности`, `§10.2 сигнал: response latency band`, `§10.2 сигнал: recent no-show reliability`, `§10.2 сигнал: техническая совместимость для online`, `§10.2 сигнал: наличие host/venue/room для group/event`, `§10.3 слой 2: candidate retrieval recall (learned)`, `§10.3 слой 3: calibrated P_response`, `§10.3 слой 4: calibrated P_accept по направлениям/доменам`, `§10.3 слой 5: calibrated P_completion`, `§10.3 слой 6: learning-to-rank + off-policy evaluation`

## §11 Allocation/fairness + §12 Controlled expansion

_Базовая проверка (§11+§12 вместе): ✅ 11 · 🟡 15 · ⬜ 7._
_После реализации §11 (allocation-слой в app.py, read-only/dormant): §11 = **done_core_v2 4 · done 1 · partial 5 · pilot_disabled 7 · blocked_calibration 1**. (§12 — уже во многом ✅ ранее; отдельно не трогал.)_

> **Обновлено — реализован §11 allocation/fairness** (разбор: [docs/ALLOCATION.md](ALLOCATION.md); тесты
> `C11-*`, 7 проверок; вся сюита 181/181 зелёная). Дизайн — design+ревью (6 агентов, must-fix: no-op
> возвращает тот же объект списка, within-band demote переприменяет frozen sort key, никакого write-back в
> score, trace без payment/propensity, per-branch dormancy тест).
>
> **Несущая гарантия:** `_allocate` — no-op при пилотных дефолтах (`ALLOCATION_CONFIG`: cap 1e9 / quota 0 /
> guard off), возвращает тот же slate; кусается только под `ctx['allocation']` override (не sha-пиннутый
> конфиг). `C11-ALLOC-NOOP/-BRANCH` (byte-identical) + `C11-ALLOC-BITE` (тесная cap режет только over-exposed,
> порядок выживших сохранён). RCV5/RCV9/R1-7/PARITY зелёные.
>
> **Стало ✅ (в §11):** §11.1 per-user exposure caps (`_exposure` лог + dormant cap), popularity-guard +
> protection-of-responsive (within-band **demote-only**, никогда не boost), exploration quota (off by
> default, не фабрикует), general per-pair cooldown (dormant); §11.2 step-6 **allocation_trace**
> (position/exposure/fatigue/reasons, **propensity absent_by_design**, ноль payment). §11.3 payment invariant
> — `C11-PAY-ALLOC` (внедрённый payment_status не меняет ни slate, ни trace).
>
> **pilot_disabled (7):** reservation-capacity (группы/urgent) + city/area supply-balancing (нужна group/city
> инфра §15/§16); часть механизмов dormant-by-design. **partial (5):** capacity-exceeded оставлен как
> `readiness=busy` (видим, RCV5) вместо буквального drop — осознанная byte-identity интерпретация; diversity
> по одной оси. **blocked_calibration (1):** propensity/acceptance-probability.

> **Обновлено — реализован §12 controlled expansion** (разбор: [docs/EXPANSION.md](EXPANSION.md); тесты
> `C12-*`, 10 проверок; вся сюита 191/191 зелёная). §12 = **done_prior 8 · done 8 · partial 3 ·
> pilot_disabled 2**. Дизайн — design+ревью (6 агентов, verdict go).
>
> **Стало ✅ (в §12):** упорядоченная **лестница** `expansion_ladder` (7 шагов §12.2, one-axis-per-step в
> ПЛАНЕ, cheapest-first, provenance сохранён, parent→broad-consent, adjacent→discovery; в ответе
> `/match`,`/plan`,`/confirm` как `expansion`); **теги** ladder_step на исполняемых fallback/online-room
> карточках (`_tag_ladder`, PURE/exception-safe — never-dead-end не тронут); §12.3 **Dota-пример** (T0/T1/T2/
> T4/No-supply; LoL≠personal-proposal без consent); §12.2 шаг 7 **saved-search + notify** (SESSION store +
> `POST /save_search`(+/check read-only,/delete) + `GET /saved_searches`; НЕ users.json) — заменил `wait` заглушку.
>
> **Честно:** план one-axis, но исполняемый `_expand_fallback` всё ещё multi-axis (тегируется после факта).
> **partial (3):** движок не разделяет sibling/parent тир (обе T2, sha-pinned); auto time/distance —
> client-override; 1:1→group — §15. **pilot_disabled (2):** event/room/group как retrieved candidates
> (§15/§16) — стоит онлайн-комната T4.


**Реализовано (полностью / частично):**

- ✅ **§11 (принцип)** — Allocation отделён от relevance и не меняет смысл пары. Релевантность (lcb/reciprocal) считается отдельно; readiness — только порядок в слейте, _slate — только диверсификация, кэпы — только выдача. Ни один allocation-сигнал не входит в scoring. — `core_v2.py:search (out.sort/_slate); core_v2.py:directional_score`
- ✅ **§11.1 proposal fatigue caps** — Кэпы усталости от предложений. received_24h >= cap -> readiness 'busy'; лог полученных предложений на 24ч, кэп из receiving.proposal_budget.per_24h или config max_proposals_received_per_user_24h (деф. 4). Блокирует can_outreach и отправку. — `core_v2.py:readiness_state (l.443-446); app.py:_log_proposal/_proposals_received_24h`
- ✅ **§11.2 (2) сорт по reciprocal+readiness** — Шаг 2: сортировка по reciprocal relevance и классу readiness. Слейт сортируется ключом (band, READINESS_RANK, -reciprocal, -lcb, -coverage, name) — класс readiness и reciprocal relevance учтены (band впереди). — `core_v2.py:search l.619-620 (out.sort)`
- ✅ **§11.2 (3) diversity constraints** — Шаг 3: применить diversity-ограничения. _slate: <=3 на bucket при >2 buckets, срез top-8. — `core_v2.py:_slate (PER_BUCKET=3/TOP_N=8)`
- ✅ **§11.3 инвариант монетизации** — payment_status запрещён как relevance/reciprocity/safety/allocation feature. В коде matching нет ни одного payment/subscription-признака (grep по app.py+core_v2.py пуст); scoring — только 7 feature-групп. Конфиг декларирует ranking_boost_allowed:false и safety_priority_affected_by_payment:false. — `core_v2.py:build_features/directional_score (нет payment-инпутов)`
- ✅ **§12.1 не ослаблять safety/age/consent/block/language/purpose** — Не ослаблять safety, age, consent, block, critical language, purpose isolation. Fallback работает поверх того же hard-gate-eligible пула; _relaxed_cfg обнуляет ТОЛЬКО discovery-floor (веса/λ/outreach-floor нетронуты). Age/block/language/radius (hard gates) и tier/consent-гейт не ослабляются. — `app.py:_expand_fallback/_relaxed_cfg l.353-364`
- ✅ **§12.1 сохранять provenance tier** — Сохранять provenance tier при расширении. В fallback tier по-прежнему из assign_tier (provenance); alt-ветка помечает T4 = alternative solution type. Скор не подменяет tier. — `app.py:_expand_fallback l.643/660; core_v2.py:assign_tier`
- ✅ **§12.1 явно объяснять компромисс** — Явно объяснять компромисс расширения. Broader-карточки: fallback='broader' + note 'Broader match — a wider or adjacent category'; alt-карточки: note про 'different category'; online-fallback note про необходимость расширить поиск. — `app.py:_expand_fallback l.646-647/665 (note/fallback); app.py:_online_fallback l.690`
- ✅ **§12.1 outreach в parent tier -> broad consent** — Персональный outreach в parent tier требует broad consent. outreach_tier_ok = T0/T1 или (T2 и broadConsent); дублируется в _outreach_ok на границе отправки (_negotiate_precheck). — `core_v2.py:search l.581 (outreach_tier_ok); app.py:_outreach_ok l.766`
- ✅ **§12.1 adjacent -> discovery, не inbox** — Adjacent-результаты идут в discovery, а не в inbox. T3 (adjacent) никогда не проходит outreach_tier_ok -> can_outreach=False (только discovery); _negotiate_precheck отбивает с 'discovery only'. Конфиг: T3 personal_outreach:false. — `core_v2.py:search l.581-584; app.py:_negotiate_precheck l.796-798/_outreach_ok`
- ✅ **§12.2 (1) exact entity/role, то же время/зона** — Шаг 1: exact entity/role при том же времени и зоне. Базовый поиск приоритезирует T0/T1 (свой intent / прямой интерес) с учётом time_feasibility и location_feasibility feature-групп. — `core_v2.py:assign_tier l.358-369/search`
- 🟡 **§11.1 cooldown повторных предложений паре** — Cooldown на повторные предложения той же паре. Есть 7-дневный cooldown, но только когда кандидат ранее отклонил владельца (declinedOwnerDaysAgo<COOLDOWN_DAYS). Общего per-pair cooldown на повторную отправку не declined-паре нет. — `app.py:_hard_gates l.433 (COOLDOWN_DAYS=7)`
- 🟡 **§11.1 diversity slate** — Diversity slate по source type / semantic tier / интерпретации intent. Диверсификация есть (_slate: <=3 на bucket при >2 buckets), но ось bucket = широкая интерес-категория (cat_of), а НЕ source type / semantic tier / интерпретация intent из спеки. — `core_v2.py:_slate; core_v2.py:search l.587 (bucket=cat_of)`
- 🟡 **§11.1 защита отзывчивых** — Защита от систематического переиспользования самых отзывчивых. Прямой защиты по отзывчивости (acceptance-rate) нет; частичный эффект даёт per-24h fatigue-кэп полученных предложений, ограничивающий перегрузку любого одного человека. — `core_v2.py:readiness_state l.445-446 (received_24h>=cap)`
- 🟡 **§11.2 (1) удалить BLOCK/expired/capacity-exceeded** — Шаг 1: удалить BLOCK/expired/capacity-exceeded. BLOCK/paused удаляются (hard gates + is_paused), T5-неперекрытие отсеивается. Но 'expired' (proposal TTL) не реализован, а capacity-exceeded становится readiness 'busy' и ОСТАЁТСЯ в выдаче (ранжируется ниже), а не удаляется. — `app.py:match_candidates/_hard_gates; core_v2.py:search l.559-563 (is_paused, tier=='T5')`
- 🟡 **§11.2 (4) exposure/fatigue caps** — Шаг 4: применить exposure/fatigue-кэпы. Fatigue-кэп применяется через readiness ('busy' по received_24h), влияя на порядок и can_outreach; exposure-кэпов (показы) нет. — `core_v2.py:readiness_state; core_v2.py:search l.579-584`
- 🟡 **§11.2 (6) propensity+причины allocation** — Шаг 6: зафиксировать propensity и причины allocation. Карточка несёт decision trace (tier, policy=ALLOW, domain, a_to_b/b_to_a, reciprocal, band, readiness) и текстовые reasons/note. Propensity (acceptance_probability) не считается — в конфиге помечен как absent в MVP. — `core_v2.py:search l.612-615 (trace); core_v2.py:_presentation`
- 🟡 **§12.1 одна ось за шаг** — Расширять за шаг только одну ось. Авто-fallback ослабляет несколько ограничений разом (adjacentAllowed + discovery-floor), а не одну ось за шаг. Поштучное расширение по одной оси доступно только вручную через override / кнопки online-fallback. — `app.py:_expand_fallback l.642-643; app.py:_online_fallback`
- 🟡 **§12.2 (порядок в целом)** — Типовой ступенчатый порядок расширения. Ступенчатой лестницы exact->sibling->parent->time/dist->format->event->saved-search нет. Есть один расширяющий проход (_expand_fallback) + online-fallback с опциями room/online/wait. — `app.py:_expand_fallback; app.py:_online_fallback`
- 🟡 **§12.2 (2) sibling/closely related** — Шаг 2: direct sibling / closely related entity. Fallback включает adjacent/related (T2/T3) при пустом слейте, но не как отдельный второй шаг лестницы. — `app.py:_expand_fallback l.642-643`
- 🟡 **§12.2 (3) parent activity/category** — Шаг 3: parent activity/category. T2 (parent, topical best 2-3) появляется в fallback как discovery без personal outreach без consent, но не как отдельная упорядоченная ступень. — `app.py:_expand_fallback; core_v2.py:assign_tier l.366-367`
- 🟡 **§12.2 (4) больше времени/расстояния в пределах consent** — Шаг 4: увеличить время/расстояние в пределах consent. Авто-расширение радиуса/времени не выполняется (radiusKm hard gate остаётся). Есть лишь ручная кнопка 'Widen the distance' в online-fallback (применяется через override в agent_plan). — `app.py:_online_fallback l.687 (suggestion radius); app.py:agent_plan l.695-699 (override)`
- 🟡 **§12.2 (5) смена формата 1:1->group / offline->online** — Шаг 5: смена формата (1:1->small group, offline->online). offline->online предлагается (_online_fallback: voice room / watch together, кнопки). 1:1->small group не реализовано (group formation отсутствует). — `app.py:_online_fallback l.680-683`
- 🟡 **§12.2 (6) event/room/group как alternative** — Шаг 6: event/room/group как альтернативный тип решения. Предлагается 'Live room' (voice/watch) как альтернатива. Реальных event/room/group-сущностей и group queue нет. — `app.py:_online_fallback l.681-683 (room)`
- 🟡 **§12.2 (7) сохранённый поиск + уведомить позже** — Шаг 7: сохранённый поиск и уведомление позже. Есть опция-кнопка 'Keep searching in the background'/'wait', но фактического сохранённого поиска и последующего уведомления нет — id 'wait' нигде не обрабатывается (чистая заглушка UI). — `app.py:_online_fallback l.688 (suggestion wait)`
- 🟡 **§12.3 пример Dota 2** — Пример Dota 2 (гарантия: LoL != personal proposal без consent). Ключевая гарантия соблюдена: LoL-игрок к запросу Dota получает tier T2 (sibling/parent topical) -> personal outreach только при broadConsent, иначе discovery. Но строки T4 (Dota room / group queue) и 'No supply' (сохранить поиск/уточнить) реализованы лишь как заглушки online-fallback. — `core_v2.py:assign_tier/topical; app.py:_online_fallback`

**⬜ Не реализовано (7):** `§11.1 per-user exposure caps`, `§11.1 exploration quota`, `§11.1 popularity concentration guard`, `§11.1 reservation capacity`, `§11.1 city/area supply balancing`, `§11.2 (5) exploration позиция`, `§12.1 сначала дешёвый soft-constraint`

## §13 Agent protocol + §14 Transaction state machines

_Базовая проверка (§13+§14 вместе): ✅ 5 · 🟡 6 · ⬜ 20._
_После реализации §13 (typed-protocol слой): §13 = **done_prior 12 · done 9 · partial 7 · blocked_infra 2 · pilot_disabled 1**._
_После реализации §14 (transaction state machines): §14 = **done_single_process 7 · partial/blocked_infra 6 · pilot_disabled 1** (13 подпунктов ушли из ⬜: 7→✅, 6→🟡)._

> **Обновлено — реализован §13 typed agent protocol** (разбор: [docs/PROTOCOL.md](PROTOCOL.md); новый модуль
> [`shared/kleal_protocol.py`](../shared/kleal_protocol.py), keyless+LLM-free; тесты `C13-*`, 12 проверок;
> вся сюита 200/200 зелёная). Дизайн — design+ревью (6 агентов, must-fix: config-derived cap (не хардкод),
> additive-only stamp, guard'ы только в negotiate_candidates, overflow по reason-substring, POSITIVE-firing guard тесты).
>
> **Стало ✅ (в §13):** §13.1 **9 типизированных действий** (`ACTIONS`) + `type_action`/`map_decision_to_action`
> (LLM только формулирует); §13.1 полный **message envelope** (`build_envelope` — versions/purpose/disclosure/
> TTL/rendering_key/audit, не пере-деривает proposal_id/idempotency_key); §13.2 **wave-assignment** (Wave
> 0/1/2/3) + `broadConsent` поднимает cap до max(base,3) без хардкода; §13.3 **enforced guards**
> (`guard_no_payment_booking_venue_confirm` / `guard_no_conflicting_plans` / `guard_no_refusal_retry` —
> флипают agree→False + `code=NEEDS_CONSENT`) + AUTONOMY_BOUNDARIES manifest. Аддитивно — NEG1-4/C4-SEND1 byte-identical.
>
> **Честно:** partial (7) — ASK_INFO/EXPIRE/COUNTER_* типизированные ярлыки/хинты, не transitions; reveal-
> sensitive на уровне stage; payment-guard defensive/latent. **blocked_infra (2):** async Wave-2 re-send
> scheduler; per-message transport. **pilot_disabled (1):** group/event действия (§15/§16).

> **Обновлено — реализован §14 transaction state machines & race protection** (разбор:
> [docs/STATE_MACHINES.md](STATE_MACHINES.md); новый модуль [`shared/kleal_states.py`](../shared/kleal_states.py),
> keyless+LLM-free; тесты `C14-*`, 16 проверок; вся сюита 218/218 зелёная, детерминизм — двойной прогон). Дизайн —
> design+ревью (6 агентов, must-fix: RLock против deadlock; 1:1-эксклюзивность через ОБЩИЙ per-intent слот, не
> per-object CAS; dedup-ключ с action; CAS-loser не пишется accepted; envelope несёт только грубый public_reason).
>
> **Стало ✅ (в §14, single-process):** §14.1 **4 автомата** (`STATE_MACHINES` intent/proposal/match/plan) +
> deny-safe валидатор (`can_transition`/`next_state`/`apply_transition`, аддитивно, version-bump); §14.2 **optimistic
> concurrency** (`compare_and_swap`), **idempotency** (`dedup`, clock-free + action-aware),
> **compare-and-swap при concurrent accept**; §14.3 **политика по типу intent** (`concurrent_accept_policy`) +
> enforced **1:1 fixed-time эксклюзивность** (проигравший → WITHDRAWN/`SLOT_TAKEN`, НЕ accepted); §14.4 **8 гонок**
> (`resolve_race`) → детерминированный `{state,error_code}` **без утечки** (только грубый public_reason). Аддитивно —
> NEG1-4/C4-SEND1/C13 byte-identical; sha-pinned движок не тронут.
>
> **Честно (partial/blocked_infra, 6):** idempotency-key НЕ на всех write-эндпоинтах (только `/transition` +
> opt-in `/outcome`, оба — атомарная check+act под ОДНИМ RLock, после адверсариал-ревью); **unique-active-pair** —
> чистый примитив (покрыт тестом), как enforcing-gate в negotiate не встроен (не менять slate); transactional outbox —
> append `_trace`/`_outbox`, **async-consumer нет**; retry-safe **async** consumers/dedup — примитив есть,
> распределённого потребителя нет; reservation TTL — чистая функция, **реальной capacity нет**; cross-entity атомарный
> commit через сервисы — нужна БД/очередь. **pilot_disabled (1):** Plan-автомат определён для конформанса, `enabled:False`.
>
> **Адверсариал-ревью (6 finders → verify):** 12 находок, 3 подтверждены (все low после верификации), исправлены:
> (1+2) `/api/agent/outcome` идемпотентность была не атомарной (check и record в РАЗНЫХ lock-блоках → под
> ThreadingHTTPServer два одновременных replay могли дважды записать outcome) — сведено в один RLock-блок, как
> `agent_transition`; (3) `reservation_expired()` не был покрыт — добавлен `C14-RESERVATION-TTL`. Плюс hardening:
> `agent_transition` мемоизирует ТОЛЬКО применённый переход (failed edge/CAS не мемоизируется → corrected-retry не
> застревает как DUPLICATE). Info-leak инвариант ревью подтвердило **held**.

**Реализовано (полностью / частично):**

- ✅ **§13.2 лимит ≤3 одновременных personal proposals + urgent-расширение + запрет массовой рассылки** — Ограничение параллельных предложений. Кандидаты режутся до top-5, параллельная волна ограничена cap из конфига (default_parallel_proposals=2, urgent_same_day_parallel_proposals=3 при 'today/tonight/evening/tomorrow'); лишние помечаются 'queued for the next wave'. Массовая рассылка невозможна. — `services/matching/app.py:_negotiate_precheck (cap l.781-782, соответствует config/Kleal_Matching_Core_Config_v2.yaml l.206-207), negotiate_candidates (top=cands[:5] l.827)`
- ✅ **§13.3 авто: компиляция черновика intent** — Автоматическая сборка intent из свободного текста. parse_intent (LLM) с детерминированным _fallback_parse строит структурный intent (topics/role/mode/time + gate-параметры) из запроса пользователя. — `services/matching/app.py:parse_intent (l.407) / _fallback_parse (l.379)`
- ✅ **§13.3 авто: retrieval** — Автоматический retrieval по пулу. match_candidates фильтрует пул hard-gates (l.620-625) и передаёт eligible-кандидатов в core_v2.search для скоринга и ранжирования. — `services/matching/app.py:match_candidates (l.611); services/matching/core_v2.py:search (l.545)`
- ✅ **§13.3 авто: explanation из reason keys** — Формирование объяснения из ключей причин. _presentation собирает 2-3 подтверждённые причины из словаря _REASON (только known_match, st==K_MATCH, без выдуманных фактов) + один top-gap; отдаются как reasons_ru/en. — `services/matching/core_v2.py:_presentation + _REASON (l.477-525)`
- ✅ **§13.3 авто: отправка только в рамках подтверждённой outreach policy** — Отправка предложения только по outreach-политике. Перед отправкой _outreach_ok проверяет tier/consent (T0/T1; T2 только при broadConsent; T3+ нет), а readiness_state — receiving-политику адресата (busy/quiet hours→open_later, proposal budget, allowed_domains, passive_outreach); всё ревалидируется на границе отправки. — `services/matching/app.py:_outreach_ok (l.758) / _negotiate_precheck (l.796-804); services/matching/core_v2.py:readiness_state (l.427)`
- 🟡 **§13.3 авто: allowlisted clarification** — Разрешённые уточняющие вопросы. Есть фиксированный набор gap-типов (_GAP, 7 ключей), из которого _presentation возвращает один верхний 'gap' (например 'time not confirmed') как подсказку для карточки. Сам вопрос из allowlist никому не задаётся — это лишь пассивный ярлык. — `services/matching/core_v2.py:_presentation (gap_en, l.497-525) / _GAP (l.487-495)`
- 🟡 **§13.3 запрет: расширять hard constraints без согласия** — Автозапрет расширения жёстких ограничений. Fallback-расширение (_relaxed_cfg) снижает только discovery-порог; hard-gates и outreach-floor не трогаются, поэтому жёсткие ограничения авто-не расширяются. Отдельного consent-механизма для их расширения нет. — `services/matching/app.py:_relaxed_cfg (l.353-365) / _expand_fallback (l.634-643, тот же eligible-пул)`
- 🟡 **§13.3 запрет: соглашаться на dating contact без согласия** — Автозапрет dating-контакта. Hard-gate блокирует dating-intent, если у адресата нет datingOk (глобальный opt-in). Это единый флаг-согласие, а не подтверждение каждого mutual-контакта, как требует спека. — `services/matching/app.py:_hard_gates (dating, l.437)`
- 🟡 **§13.3 запрет: переинтерпретировать отказ как «попробовать позже»** — Автозапрет повторной попытки после отказа. Явной повторной отправки отклонённым нет; hard-gate 'recently declined (cooldown)' блокирует кандидата с declinedOwnerDaysAgo < COOLDOWN_DAYS, то есть недавний отказ не переигрывается сразу. Полноценной модели состояния отказа нет. — `services/matching/app.py:_hard_gates (declinedOwnerDaysAgo, l.432-433)`
- 🟡 **§14.2 policy revalidation в той же транзакции, что acceptance** — Ревалидация политики при принятии. _negotiate_precheck пере-резолвит каждого кандидата из живого стора и заново прогоняет hard-gates + outreach/receiving-гейты на границе ОТПРАВКИ (не доверяя списку клиента). Это ревалидация перед отправкой, а не внутри транзакции acceptance (транзакции accept нет). — `services/matching/app.py:_negotiate_precheck (l.768-824)`
- 🟡 **§14.2 immutable decision trace** — Неизменяемый след решения. core_v2.search кладёт в каждую карточку 'trace' (tier/policy/domain/оба направления скоринга/band/readiness/config_version); детерминируемо при фиксированных ctx.now и config_version. `/api/agent/transition` теперь также аппендит append-only `SESSION['_trace']` (from→to/version/action/id) на каждом валидированном переходе. Персистентного per-транзакция immutable-лога через БД пока нет. — `services/matching/core_v2.py:search (trace); services/matching/app.py:agent_transition (l.1809)`
- ✅ **§14.1 состояния Intent/Proposal/Match** — Три активных автомата с точными состояниями/рёбрами (intent 7, proposal 10, match 8), deny-safe валидатор (терминалы — стоки, unknown → False), аддитивный `apply_transition` (ставит state + инкремент version, не трогает status/agree/reason). — `shared/kleal_states.py:STATE_MACHINES / can_transition / apply_transition`
- 🟡 **§14.1 состояния Plan** — Автомат Plan (8 состояний) ОПРЕДЕЛЁН для конформанса, но `enabled:False` — group/plan выключены в пилоте (§1.2/§15/§16). — `shared/kleal_states.py:STATE_MACHINES['plan']`
- ✅ **§14.2 optimistic concurrency через version** — `check_version`/`compare_and_swap` — монотонный `version`, CAS-предикат; первый accept на объекте выигрывает (version→2), устаревший expected → VERSION_CONFLICT. `build_proposal` теперь несёт статический `version:1`. — `shared/kleal_states.py:compare_and_swap; shared/kleal_contracts.py:build_proposal (l.424)`
- ✅ **§14.2 compare-and-swap при concurrent accepts** — На границе accept negotiate_candidates держит один RLock через revalidate+slot+record; per-object CAS отбивает второй accept на ТОМ ЖЕ объекте, общий per-intent слот (`claim_slot`) — на разных кандидатах. — `services/matching/app.py:negotiate_candidates (l.1796-1805); shared/kleal_states.py:claim_slot`
- 🟡 **§14.2 уникальные ограничения на active pair/purpose** — `unique_active_pair(active, pair, purpose)` — не более одной активной пары на (неупорядоченная пара, purpose); дубликат → DUPLICATE_PAIR, первая волна не роняется. Чистый примитив (покрыт `C14-UNIQUE-PAIR`), доступен вызывающим; как enforcing-gate в `negotiate_candidates` НЕ встроен (чтобы не менять surfaced slate) — реальная уникальность на write-пути будет с персистентным стором proposal'ов (blocked_infra). — `shared/kleal_states.py:unique_active_pair`
- ✅ **§14.3 политика одновременных принятий по типу intent** — `concurrent_accept_policy`: дефолт multiple_conversations (byte-identical), 1:1-fixed-time → эксклюзив (проигравший WITHDRAWN/SLOT_TAKEN, НЕ accepted), dating → manual_confirm (no auto-commit), group/event → pilot-disabled. Enforced в accept-петле. — `shared/kleal_states.py:concurrent_accept_policy; services/matching/app.py:negotiate_candidates (l.1795-1804)`
- ✅ **§14.4 критические race-cases (детерминированный state/error, без утечки инфо)** — `resolve_race` — ровно 8 гонок → детерминированный {state, error_code, public_reason, leak:False}; кросс-агентная поверхность несёт только грубый public_reason, гранулярная причина гейта остаётся в owner-only explain. POLICY_CHANGED переиспользован verbatim. — `shared/kleal_states.py:resolve_race / _RACES`
- 🟡 **§14.2 idempotency key на write-эндпоинтах** — `dedup_key` (clock-free, включает action) + `dedup` (повтор → сохранённый прежний результат, DUPLICATE). Применён к `/api/agent/transition` и opt-in к `/api/agent/outcome` (при переданном idempotency_key). НЕ на всех write-путях. — `shared/kleal_states.py:dedup_key / dedup; services/matching/app.py:agent_transition / do_POST outcome`
- 🟡 **§14.2 transactional outbox для событий/уведомлений** — `/transition` аппендит `SESSION['_outbox']` (append-only) в том же `_save_store`. Реального async-consumer / доставки нет — только запись строки. — `services/matching/app.py:agent_transition (_outbox)`
- 🟡 **§14.2 reservation TTL для capacity** — `reservation_expired(reservation, now_ts)` — детерминированный TTL-чек по явному now_ts; `build_reservation` несёт version+ttl+expires_at. Реальной capacity-системы (holds/квоты) в пилоте нет. — `shared/kleal_states.py:reservation_expired; shared/kleal_contracts.py:build_reservation`
- 🟡 **§14.2 retry-safe consumers и deduplication** — Примитив дедупликации (`dedup`) есть и покрыт тестом; распределённого retry-safe консьюмера (at-least-once + идемпотентная обработка на приёмнике) нет — нужна очередь/БД. — `shared/kleal_states.py:dedup (blocked_infra: async consumer)`

**⬜ Не реализовано (7):** `§13 intro: типизированные события (не свободные LLM-разговоры)`, `§13.1 набор действий (ELIGIBILITY_PROBE/PROPOSE_CONNECTION/ASK_INFO/COUNTER_*/ACCEPT/DECLINE/WITHDRAW/EXPIRE)`, `§13.1 конверт сообщения (proposal_id, idempotency_key, версии intent/profile/policy, purpose, disclosure scope, TTL, rendering key, audit metadata)`, `§13.2 волновая оркестрация (Wave 0/1/2/3, запуск по refusal/timeout/capacity)`, `§13.3 запрет: раскрывать новое чувствительное поле без согласия`, `§13.3 запрет: подтверждать платёж/бронирование/private venue`, `§13.3 запрет: принимать несколько конфликтующих планов`
> _(§13-подпункты выше уже покрыты реализацией §13 — см. блок «Стало ✅ (в §13)» и записи `C13-*`; строки оставлены для трассируемости к исходной базовой проверке. Все 13 §14-подпунктов вынесены из ⬜ выше.)_

## §15 Group Formation + §16 Events/rooms/venues + §17 Dating

_✅ 1 · 🟡 7 · ⬜ 16 (базовая проверка)._
_После реализации §15 (group formation core): §15 = **done 10 · done_config_derived 2 · pilot_disabled 2 · partial 2 · blocked_infra 1** (4 крупных подпункта ушли из ⬜: 3→✅, 1→🟡)._
_После реализации §16 (event/room/venue candidate types): §16 = **pilot_disabled 6 · done_prior 2 · partial 2 · blocked_infra 2 · done 1** (5 крупных подпунктов ушли из ⬜ → ✅ как pilot-disabled scaffolding)._

> **Обновлено — реализован §15 Group Formation Core** (разбор: [docs/GROUP_FORMATION.md](GROUP_FORMATION.md);
> новый модуль [`shared/kleal_groups.py`](../shared/kleal_groups.py), keyless+LLM-free+no-FS/clock/random; тесты
> `C15G-*`, 21 проверка; вся сюита 240/240 зелёная, детерминизм — двойной прогон). Дизайн+ревью (6 агентов,
> go_with_fixes / sound_with_fixes): 11 must-fix + 3 blocking — все применены. Адверсариал-ревью реализации
> (5 finders → verify): 20 находок, 4 подтверждены (все low, pilot-off вне живого потока) и исправлены —
> `_common_window` истинное пересечение интервалов (не bounding-span); `greedy` feasibility-режим (нет ложного
> NO_FEASIBLE_GROUP); 2 слабых теста укреплены; NaN-guard.
>
> **Стало ✅ (в §15, PILOT-DISABLED scaffolding):** §15.1 **set-level hard-constraints** (`check_set_constraints`/
> `set_feasible` — 13 кодов, deny-safe); §15.2 **GroupUtility** — веса **config-derived** из sha-pinned
> `cfg['group_formation']['utility_weights']` (никогда не хардкод), **feasibility доминирует** (infeasible →
> `utility=None`, никогда не выбирается), **least_misery = МИН направленной удовлетворённости**, config-ключи —
> источник истины (`SPEC_ALIAS` документирует расхождение с прозой); §15.3 **детерминированный MVP** (seed → feasible
> pools → greedy marginal-gain → strict-improve local repair с iter-cap → reserve); **App C #8 last-seat capacity**
> reuses §14 (`ks.claim_slot`, без нового lock; `filled` ≤ capacity by construction); §15.3.7 replacement (data-only);
> закрыт пропуск sum-to-1.0 валидации group-блока (не редактируя sha-pinned yaml/core_v2). Аддитивно — **byte-identical
> person-to-person slate** (`core_v2`/`match_candidates`/`negotiate` не ссылаются на модуль, `C15G-11`).
>
> **Честно:** **pilot_disabled (2):** §15.3.6 structured invitations (сконструированы, не отправлены); живая проводка в
> buddy→filtration→matching (новый gated `POST /api/agent/group` возвращает `enabled:False` без ТОЧНОГО override
> `{'enable_group_formation':True}`). **partial (2):** §15.4 конкретные domain-packs (Dota/Padel/Conversation/Walk —
> generic role/diversity/skill-spread есть, паки за §37+); candidate↔candidate pair_rel матрица (core_v2 даёт только
> initiator↔candidate; модуль берёт n×n как ВХОД). **blocked_infra (1):** кросс-процессная/мульти-под атомарность
> последнего места (нужна БД/очередь).

**Реализовано (полностью / частично):**

- ✅ **§15.1 set-level hard constraints (min/max size, time overlap, capacity, mandatory roles, pairwise blocks/safety, host/moderator, skill spread, language coverage, equipment/platform/venue, quorum)** — `check_set_constraints` возвращает SORTED коды нарушений (deny-safe: неизвестный constraint → no-op, никогда false-pass на block/safety); `filter_hard_set_constraints` — per-member prefilter. — `shared/kleal_groups.py:check_set_constraints / set_feasible / filter_hard_set_constraints`
- ✅ **§15.2 GroupUtility = 0.35·least_misery + 0.25·mean_pair_fit + 0.20·role_coverage + 0.10·time_overlap + 0.10·diversity_value** — веса **config-derived** из `cfg['group_formation']['utility_weights']` (WEIGHT_KEYS = точные config-ключи, `SPEC_ALIAS` документирует прозу); каждый компонент в [0,1]; **feasibility доминирует** (`utility=None` при нарушении); **least_misery = min направленной удовлетворённости**; pair relevance — ВХОД. Закрыта sum-to-1.0 валидация (пропуск `core_v2.load_config`) в `load_group_params`/`validate_group_config_block` — без правки sha-pinned файла. — `shared/kleal_groups.py:group_utility / group_utility_components / load_group_params`
- ✅ **§15.3 MVP-алгоритм (seed → feasible pools → greedy marginal gain → local repair → reservations → waitlist/quorum)** — детерминированный `form_group` (App B.3): seed по `(-relevance,id_hash)`, greedy на TOTAL utility, local_repair strict-improve (delta>1e-9) с `MAX_REPAIR_ITERS` капом (доказуемая терминация), cross-seed tie по `group_signature`. Last-seat capacity (App C #8) reuses §14 `ks.claim_slot` (single-process; `filled`≤capacity by construction). — `shared/kleal_groups.py:form_group / greedy_marginal_add / local_repair / reserve_members / claim_group_seat`
- 🟡 **§15.4 примеры (Dota stack / падель / разговорная группа / прогулка)** — generic role_coverage / diversity_axis / skill_spread / language coverage / equipment поддержаны и покрыты тестами (Dota carry/support/mid/offlane формируется, missing-role → нет группы); конкретные per-domain constraint-packs (rank spread, court booking, native/learner, маршрут) отложены на §37-wiring. — `shared/kleal_groups.py:generate_role_complete_seeds / diversity_value`; тест `C15G-16`
- ✅ **§16 таблица — тип User (mutual policy + directed fit → reciprocal relevance → proposal→mutual contact)** — Кандидат типа User. Полностью реализован пайплайн подбора людей: hard-gates по mutual-политике, тир по реципрокному/направленному сигналу, реципрокная релевантность, proposal→взаимный контакт с реваидацией receiving-policy перед отправкой. — `services/matching/app.py:_hard_gates(429), _base_tier(468), _negotiate_precheck(765); core_v2.py:reciprocal_score(352)`
- 🟡 **§16 закрытие — событие честно называть альтернативой, а не «совпадением с людьми»** — Честная подача альтернативы. Не-совпадения честно помечаются как «alternative»/«broader suggestion» (bucket T4, note «no direct match right now»), а _online_fallback пишет «No offline matches … go live/broaden». Но реальных событий/площадок нет — альтернативой служат только другие люди или live-room. — `services/matching/app.py:_expand_fallback(~655), _online_fallback(677)`
- 🟡 **§17.1 consent — отдельное включение режима + явное подтверждение target preferences** — Consent режима dating. Есть тумблер «Dating mode» (выкл по умолчанию) и candidate-opt-in флаг datingOk; поиск type=dating хард-гейтом требует datingOk у кандидата. Явного подтверждения target preferences (пол/ориентация цели) нигде не собирается. — `services/profile/app.py:818; services/matching/app.py:_hard_gates(437)`
- 🟡 **§17.1 age — строгие legal/age gates, несовершеннолетние исключены** — Возрастные гейты. Глобальный hard-gate «под 18» (MIN_AGE=18) плюс для dating parse выставляет minAge=18 и verifiedOnly=true. Но verified — самодекларируемый флаг (по умолчанию true), реального legal/ID-гейта нет (verify — заглушка «coming soon»). — `services/matching/app.py:_hard_gates(436), _fallback_parse(404)`
- 🟡 **§17.1 outreach — каждый proposal требует явного действия; no auto-accept** — Явное действие на каждый proposal. Перед отправкой каждое предложение реваидируется, применяются receiving-policy, readiness и cap параллельных предложений (нет массовой авто-рассылки). Отдельного для dating правила «no auto-accept» нет; согласие получателя решает агент-негоциатор, механика общая для всех доменов. — `services/matching/app.py:_negotiate_precheck(765)`
- 🟡 **§17.1 explanation — не выводить чувствительные причины и псевдопсихологический score** — Объяснение без sensitive/score. Показывается качественная band, а не процент; причины строятся только из known_match фиксированного набора (интересы/время/гео/формат/роль/вайб) — чувствительные признаки структурно не попадают. Реализовано системно для всех доменов, не как dating-специфичный enforced-safeguard. — `services/matching/core_v2.py:_presentation(497), assign_band(470)`
- 🟡 **§17.1 safety — block/report, rate limits, anti-harassment, private-location safeguards** — Безопасность dating. Есть block (blocksMe/blocked), cooldown после отказа и cap открытых/суточных предложений (rate-limit). Report — нефункциональная заглушка «coming soon»; анти-харассмент и private-location safeguards для dating не реализованы. — `services/matching/app.py:_hard_gates(431); services/profile/app.py:1465`
- 🟡 **§17.2 изоляция — dating goal не используется для коллег/языковых/спорт-групп** — Изоляция цели dating. type=dating маппится в домен dating (infer_domain) и хард-гейтом требует datingOk, поэтому dating-цель матчит только opt-in людей и не смешивается с другими доменами. Но данные не изолированы (нет отдельной капсулы) — изоляция только на уровне маршрутизации цели. — `services/matching/core_v2.py:infer_domain(148); services/matching/app.py:_hard_gates(437)`

> **Обновлено — реализован §16 Events/rooms/venues** (разбор: [docs/CANDIDATE_TYPES.md](CANDIDATE_TYPES.md); новый
> модуль [`shared/kleal_candidates.py`](../shared/kleal_candidates.py), keyless+LLM-free+no-FS/clock/random; тесты
> `C16-*`, 24 проверки; вся сюита 264/264 зелёная). PILOT-DISABLED conformance-scaffolding: `intent_to_event/room/
> venue` = False, алгоритм под ТОЧНЫМ per-kind override, результат всегда `enabled:False`. Дизайн+ревью (6 агентов):
> 10 must-fix + 3 blocking применены (единый epoch-юнит; `now_ts` обязателен; feasibility→`score=None`; веса
> module-local; событие≠user структурно; venue-enum additive). Адверсариал-ревью реализации (5 finders → verify):
> 17 находок, 4 подтверждены и исправлены — `_sort_key` content-hash tiebreak (permutation-invariance при коллизии
> id), `room_transaction` live_left вместо max_live, 2 doc/test-мелочи. Byte-identical person-slate; §12 fallback и
> sha-pinned engine/config не тронуты.

- ✅ **§16.0 отдельные типы кандидатов (событие ≠ «пользователь с большой capacity»)** — Event/Room/Venue — свои типы объектов со СВОИМ eligibility/ranking/transaction (distinct code paths); ранкинг направленный `user→object`, никогда reciprocal; `is_personal_match:False` штампуется при build (структурно, не decoration). Pilot-disabled scaffolding. — `shared/kleal_candidates.py:score_candidate / _TERMS_OF; тест C16-EVENT-NOT-USER`
- ✅ **§16 таблица — тип Ad-hoc group** — set feasibility+quorum → group utility → reservations. Реализован в §15 (`kleal_groups`, задачи #36/#37). — `shared/kleal_groups.py`
- ✅ **§16 таблица — тип Event (category/schedule/capacity/access → user→event relevance → registration/handoff)** — `build_event` + `event_eligibility` (SCHEDULE_PAST/CAPACITY_FULL/ACCESS_*/GEO/CATEGORY_MISMATCH) + `user_event_relevance` (module-local веса) + `event_transaction` (registration через `kc.build_reservation` / external_handoff / waitlist через §14). Pilot-disabled. — `shared/kleal_candidates.py:build_event / event_eligibility / user_event_relevance / event_transaction`
- ✅ **§16 таблица — тип Online room (platform/topic/live capacity/moderation → session relevance → join token/waitlist)** — `build_room` + `room_eligibility` (MODE_OFFLINE_NO_CONSENT честная альтернатива §5.1 / PLATFORM/LIVE_CAPACITY/MODERATION/TOPIC) + `session_relevance` + `room_transaction` (join_token/waitlist). Pilot-disabled. — `shared/kleal_candidates.py:build_room / room_eligibility / session_relevance / room_transaction`
- ✅ **§16 таблица — тип Venue (availability/price/noise/distance/accessibility → plan suitability → booking handoff)** — `build_venue` + `venue_eligibility` (UNAVAILABLE/PRICE/GEO/NOISE-только-hard/ACCESSIBILITY prove-eligible) + `plan_suitability` + `venue_transaction` (selection через `kc.build_plan` enabled:False / booking_handoff). Pilot-disabled; `venue` добавлен аддитивно в PROPOSAL_TYPES/_PTYPE_OF_DECISION/PILOT_DECISION_TYPES{intent_to_venue:False}. — `shared/kleal_candidates.py:build_venue / venue_eligibility / plan_suitability / venue_transaction`

**⬜ Не реализовано (7):** `§17.1 profile — отдельная dating capsule; purpose-bound данные`, `§17.1 orientation/preferences — хранение/обработка как чувствительного контура с минимизацией`, `§17.1 disclosure — staged profile disclosure (фото/имя/детали по настройкам)`, `§17.1 audit — отдельные policy version, retention, access controls`, `§17.2 изоляция — отказ в dating не влияет на ranking в friendship`, `§17.2 переход friendship → dating требует нового взаимного consent`, `§17.3 gate для пилота — отдельные UX/safety/moderation/DPIA/legal/incident/abuse-тесты перед запуском`

## §18 Доменные сценарии + §19 Feedback + §20 Метрики

_✅ 3 · 🟡 18 · ⬜ 25_


**Реализовано (полностью / частично):**

- ✅ **§18.3 walk: no nearby-now без policy** — Не предлагать «рядом сейчас» без receiving policy. readiness_state без receiving policy и без open-сигнала даёт unknown, а can_outreach требует readiness=='open_now', т.е. близость никогда не выводит открытость; paused исключается из выдачи. — `core_v2.py:readiness_state L436-440; core_v2.py:search L582 can_outreach; is_paused L414`
- ✅ **§18.6 dating-прогулка: только из dating mode** — Dating запускается только из dating; нет неявной романтики. infer_domain сначала проверяет type=='dating' → домен dating (раньше проверки walk-слов), поэтому «погулять» в friendship-режиме даёт walk/social, не dating. _hard_gates требует datingOk только при type=='dating'. — `core_v2.py:infer_domain L148-152; app.py:_hard_gates L437`
- ✅ **§20.2(2) unit/property tests** — Гейты, веса, monotonicity, unknown, state transitions. test_core_v2.py покрывает gate-before-scoring (C5), валидацию весов/config (V1/V2), coverage/unknown/no-double-count (C1-C3), tier-provenance (C4), монотонность по evidence (C1b), переходы readiness (RCV1-9) и send-гейты (NEG1-4); suite прогоняется и падает на регрессиях. — `services/matching/test_core_v2.py L57-339`
- 🟡 **§18.1 обзор доменов** — 10 доменов: slots / hard-примеры / fallback. Config задаёт ровно 10 доменов, infer_domain их выбирает, а веса/пороги домена реально применяются через dom_cfg при скоринге. Per-domain схем слотов/hard-примеров/fallback в коде нет. — `core_v2.py:infer_domain (L146); core_v2.py:search L550 dom_cfg; config domains L44-185 (10 доменов)`
- 🟡 **§18.2 Dota: strong/broader/rejected** — Классификация активный-intent / без-intent / отказ. assign_tier даёт T0 (свой активный intent = strong) и T1 (прямой интерес = broader); readiness_state без policy не обещает available-now (unknown). Cross-region consent и отбраковка по server/LoL не реализованы. — `core_v2.py:assign_tier L358; core_v2.py:readiness_state L427`
- 🟡 **§18.3 walk: hard/soft веса** — Домен walk: приоритет района/времени/длительности. infer_domain по walk/стрелл/прогул/гуля даёт домен walk; config walk поднимает location(0.22)/time(0.20). Отдельного сбора маршрута/accessibility/min-duration нет. — `core_v2.py:infer_domain L152; config domains.walk L59-72`
- 🟡 **§18.3 walk: exact/direct/parent** — Типы кандидатов exact/direct/parent-alternative. exact=T0 (активный walk-intent) и direct=T1 (интерес без intent) присутствуют через assign_tier. Parent/alternative (walking group, публичное событие) не моделируются — только люди. — `core_v2.py:assign_tier L358`
- 🟡 **§18.4 язык: feasibility пары** — Hard-проверка языковой пары. _hard_gates по requiredLanguages блокирует отсутствие языка; build_features для language_exchange скорит пересечение языковых КОДОВ запроса и кандидата. Это одно-направленное совпадение кода, без native/learner feasibility. — `app.py:_hard_gates L444-446; core_v2.py:build_features L289-293`
- 🟡 **§18.4 язык: fallback / «любит Испанию»** — Fallback advanced/group + «любит Испанию» ≠ языковая роль. domain_constraints требует совпадения языкового КОДА через LANG_WORDS, а не темы; спец-fallback (advanced speaker, moderated group, event) не реализован — только generic broaden в _expand_fallback. — `core_v2.py:build_features L289-293 (LANG_WORDS L175)`
- 🟡 **§18.5 нетворкинг: hard purpose/geo/role/lang** — Критичные гейты профцели/гео/роли/языка. Домен professional_networking в config поднимает directed_preferences(0.25); гео/язык гейтируются _hard_gates (radiusKm, requiredLanguages). Professional purpose и founder/leadership как hard-гейт отсутствуют. — `config domains.professional_networking L129-142; app.py:_hard_gates L444-451`
- 🟡 **§18.5 нетворкинг: directed fit + B open to A** — Профессия инициатора ≠ target role; проверка открытости B к A. reverse_features+reciprocal_score отдельно проверяют, подходит ли инициатор под предпочтения B, а readiness_state — открыт ли B; directed_preferences независимы от профессии инициатора. Таксономии профессий/target-role нет. — `core_v2.py:reverse_features L315; reciprocal_score L352; readiness_state L427`
- 🟡 **§18.6 футбол: типы кандидатов + exact start** — person/fan group/venue; важность точного старта. infer_domain по watch/смотреть даёт watch_together; config поднимает time_feasibility(0.25) выше semantic — время важнее любви к спорту. Типы кандидатов (fan group, venue) не моделируются — только люди. — `core_v2.py:infer_domain L156; config domains.watch_together L143-156`
- 🟡 **§18.6 коворкинг: тишина/часы/venue** — Низкая социальность; ранг по режиму/часам/venue. infer_domain по cowork/поработ даёт coworking; config понижает social_context(0.12), поднимает time(0.2)/location(0.18). Поля тишина/часы/venue отдельно не собираются и не скорятся. — `core_v2.py:infer_domain L154; config domains.coworking L157-170`
- 🟡 **§18.6 обычная встреча: тема soft + пояснение расширения** — Тема soft, время/район primary, явное объяснение расширения. _expand_fallback при отсутствии тематических кандидатов возвращает более широкие/adjacent варианты с явной пометкой note «Broader match». Но веса social_meet не выражают «тема soft/время primary» (semantic 0.18 = time 0.18). — `app.py:_expand_fallback L634-648; config domains.social_meet L45-58`
- 🟡 **§19.1 outcome taxonomy** — Стадии exposure→consideration→…→safety и их сигналы. Хранятся лишь два сигнала: record_feedback пишет accepted/rejected по кандидату, _log_proposal логирует факт/время отправки предложения (для fatigue). Стадии exposure/coordination/completion/quality/safety и поля позиция/source/tier/config-version/propensity не собираются. — `app.py:record_feedback L226; app.py:_log_proposal L211`
- 🟡 **§19.2 явное изменение → stable preference** — Явная правка обновляет устойчивое предпочтение. Явные правки профиля персистятся onboarding-ом в общий store (users.json, атомарная запись) и читаются matching через load_candidates, влияя на матчинг. Типизированного объекта stable-preference нет. — `services/onboarding/app.py L1261-1278 (запись users.json); app.py:load_candidates L317`
- 🟡 **§19.2 одно поведение ≠ вечный вывод** — Одно поведение не создаёт постоянный вывод. В активном движке v2 обратная связь не потребляется вовсе (core_v2.search не принимает feedback, комментарий L17), т.е. поведение не создаёт вывод — но это следствие отсутствия механизма, а не явный safeguard; legacy-скорер наоборот даёт постоянные fb_accept/fb_reject. — `core_v2.py:search L545 (нет feedback-аргумента); app.py:match_candidates_legacy L575-579`
- 🟡 **§19.3 shadow/replay до включения** — Оценка моделей shadow/replay перед включением. Есть детерминированный replay: ctx.now пиннится, сортировка стабильна, config sha-pin (тест C24); ранжирование (search) отделено от отправки (_negotiate_precheck), так что можно ранжировать без proposals. Формального shadow-харнеса и логов нет. — `core_v2.py:search L555 (пин now); test_core_v2.py L148-150 (C24)`
- 🟡 **§20.2(3) shadow mode** — Core ранжирует без отправки; human review. Ранжирование отделено от отправки; explain_match возвращает human-review диагностику по каждому кандидату (matched/considered/excluded + разбор фич-групп с contribution). Формального shadow-режима/логирования нет. — `app.py:explain_match L882-981`
- 🟡 **§20.2(4) internal dogfood + synthetic supply** — Ограниченная команда + synthetic supply. Синтетический supply реализован: _gen_pool детерминированно генерирует пул из 50 пользователей как фолбэк при пустом/отсутствующем store. Фреймворка dogfood нет. — `app.py:_gen_pool L254-302; load_candidates L330-331`
- 🟡 **§20.2(7) ML migration + rollback** — ML только после выборки/calibration/rollback plan. Rollback-план реализован: KLEAL_CORE_V2=0 → legacy scorer, битый/подменённый config → авто-фолбэк (CORE_V2=False, fail-safe); config score_semantics помечает acceptance_probability как «только после калибровки, отсутствует в rule-based MVP». Сам ML/калибровка не реализованы. — `app.py:CORE_V2 L351 + match_candidates L615-616; config score_semantics L249`

**⬜ Не реализовано (25):** `§18.2 Dota: compiled intent`, `§18.2 Dota: clarification`, `§18.3 walk: clarification`, `§18.4 язык: directed roles A/B`, `§18.4 язык: комплементарность`, `§18.5 нетворкинг: fallback adjacent roles`, `§18.6 падель: capacity/reservation`, `§18.6 выставка: event-invite`, `§19.1 Completed Positive Interaction`, `§19.2 repeated → suggestion + подтверждение`, `§19.2 negative feedback контекстен`, `§19.2 confidence/source/purpose/decay/deletion`, `§19.2 dating feedback не в prof/social`, `§19.3 exposure/position bias`, `§19.3 не только по ответившим`, `§19.3 «не увидел» vs «отказал»`, `§19.3 timeout ≠ несовпадение`, `§19.3 exploration + propensity log`, `§19.3 safety/fairness отдельно от uplift`, `§20.1 система показателей`, `§20.2(1) schema simulation`, `§20.2(5) Barcelona closed pilot`, `§20.2(6) controlled expansion`, `§20.3 нет ложного улучшения`, `§20.3 структура эксперимента`

## §21 Тех.архитектура/API/observability + §22 Пилот + §23 Контракт + §24 Самооценка

_✅ 25 · 🟡 38 · ⬜ 31_


**Реализовано (полностью / частично):**

- ✅ **§21.1 Feature Builder** — evidence groups, dedup, unknown/applicability. build_features: 7 групп × состояния known/unknown/na, один агрегированный субпризнак на группу; na исключается из знаменателя в directional_score. — `services/matching/core_v2.py:build_features/199`
- ✅ **§21.1 Relevance Engine** — directional scores, coverage, LCB. directional_score: mean=acc/tw, coverage=kw/tw, lcb=clamp(mean-λ(1-cov),0,1). — `services/matching/core_v2.py:directional_score/327`
- ✅ **§21.1 Reciprocity/Readiness** — reverse fit и receiving state. reverse_features + reciprocal_score (0.7·min+0.3·mean) и readiness_state по receiving-policy/quiet-hours/fatigue. — `services/matching/core_v2.py:reciprocal_score/352`
- ✅ **§21.4 LLM compiler unavailable → fallback** — template/parser fallback. parse_intent при любом исключении LLM (try/except) откатывается на _fallback_parse (шаблон/парсер). — `services/matching/app.py:parse_intent/421`
- ✅ **§21.4 stale profile → revalidate, no proposal** — revalidate; не создавать proposal. _negotiate_precheck ре-резолвит кандидата из live-стора и повторно прогоняет hard-gates + outreach-гейт перед отправкой; неподходящий не получает proposal. — `services/matching/app.py:_negotiate_precheck/787`
- ✅ **§22.2 Этап 1 Rule-based core** — compiler, retrieval, gates, directional relevance. parse_intent + load_candidates + _hard_gates + directional_score присутствуют; offline-набор acceptance-тестов в test_core_v2.py. — `services/matching/test_core_v2.py`
- ✅ **§22.2 Этап 2 Transparent discovery** — slate, reasons, list/map, no personal outreach. _slate + reasons + bands + explore_plans (карта реальных планов с lat/lon); personal outreach отделён флагом can_outreach. — `services/matching/app.py:explore_plans/850`
- ✅ **§22.3 Никакого автоматического массового outreach** — без mass outreach. negotiate_candidates берёт только топ-5 (cands[:5]), precheck ограничивает параллельные предложения до 2/3 — массовой рассылки нет. — `services/matching/app.py:_negotiate_precheck/781`
- ✅ **§23.2 #1 не сводить к одному match_score** — слои раздельны. tier/coverage/lcb/reciprocal/band хранятся и отдаются раздельно в карточке search(). — `services/matching/core_v2.py:search/598`
- ✅ **§23.2 #2 не выводить semantic tier из score** — tier = provenance. assign_tier строит тир из provenance (own-intent reciprocal / topical overlap), не из score. — `services/matching/core_v2.py:assign_tier/358`
- ✅ **§23.2 #3 unknown не считать совпадением** — unknown = prior + ↓coverage. В directional_score unknown добавляет доменный prior в acc, но не увеличивает kw → снижает coverage; value совпадения не даёт. — `services/matching/core_v2.py:directional_score/340`
- ✅ **§23.2 #4 не мешать safety/payment с relevance** — safety/payment отдельно. Hard-gates отделены от скоринга; ranking_boost_allowed:false; платёж не входит в relevance. — `config/Kleal_Matching_Core_Config_v2.yaml:5`
- ✅ **§23.2 #5 embeddings не финальная истина** — без embeddings как истины. Эмбеддингов нет; истина — детерминированная таксономия/фичи. — `services/matching/core_v2.py:build_features/207`
- ✅ **§23.2 #6 LLM не обходит hard gates** — gates до LLM/скоринга. Hard-gates выполняются до скоринга и повторно в precheck перед отправкой; LLM только парсит/ведёт переговоры. — `services/matching/app.py:_negotiate_precheck/792`
- ✅ **§23.2 #9 не переносить dating data в др. режимы** — изоляция dating. infer_domain изолирует dating; hard-gate datingOk; конфиг dating под release_gate. — `services/matching/core_v2.py:infer_domain/148`
- ✅ **§23.2 #12 нет proposal без receiving policy+revalidation** — receiving-policy + revalidation при send. _negotiate_precheck обязательно ре-резолвит из стора, ре-гейтит и проверяет readiness/receiving перед каждой отправкой. — `services/matching/app.py:_negotiate_precheck/768`
- ✅ **§23.2 #14 не повышать ranking за подписку** — без pay-to-rank. ranking_boost_allowed:false в конфиге; логики платежей/подписки в скоринге нет. — `config/Kleal_Matching_Core_Config_v2.yaml:5`
- ✅ **§23.2 #15 не использовать точную live location** — coarse geo в discovery. _latlon первым предпочитает coarseLat/coarseLon; расстояние по haversine; explore_plans оффсетит координаты реальных юзеров. — `services/matching/core_v2.py:_latlon/185`
- ✅ **§23.3 DoD: unknown/not_applicable handled** — обработка unknown/na. Состояния known/unknown/na реализованы; na исключается из знаменателя, unknown идёт через prior. — `services/matching/core_v2.py:build_features/199`
- ✅ **§23.3 DoD: unit и property tests** — unit+property. test_core_v2.py содержит property-тесты C1-C3 (coverage/unknown/no-double-count), V1-V2 (config), C24/PARITY. — `services/matching/test_core_v2.py:7`
- ✅ **§23.3 DoD: privacy/safety test** — privacy/safety-тесты. Safety-тесты C5 (gate-before-scoring), C15 (tier/consent), NEG1-4 (send-gates), RCV1-9 (receiving/readiness). — `services/matching/test_core_v2.py:8`
- ✅ **§23.3 DoD: domain fixture ≥2 сценария** — доменные фикстуры. Store-регрессии R1-R7 + доменные кейсы C4/C23 покрывают несколько сценариев. — `services/matching/test_core_v2.py:9`
- ✅ **§23.3 DoD: UX copy отделён от решения** — UX-copy vs system decision. BAND_LABELS/READINESS_LABELS/_REASON/_GAP держат ru/en-тексты отдельно от машинного решения (band/readiness/state). — `services/matching/core_v2.py:BAND_LABELS/462`
- ✅ **§23.4 #3 compiler/retrieval/feature builder** — компилятор/ретривал/фичи. parse_intent + load_candidates + build_features присутствуют. — `services/matching/core_v2.py:build_features/199`
- ✅ **§23.4 #4 deterministic relevance + transparent results** — детерм. relevance + прозрачность. directional_score (детерминированный) + slate/bands/reasons. — `services/matching/core_v2.py:directional_score/327`
- 🟡 **§21.1 Intent Compiler** — raw text → canonical draft + confidence + clarification. parse_intent (LLM→JSON) + _fallback_parse строят intent из текста. Нет confidence, slots и clarification-вопросов. — `services/matching/app.py:parse_intent/407`
- 🟡 **§21.1 Profile/Consent Service** — profile signals, purpose grants, deletion, versions. admin _norm_user + delete_user (CRUD профилей) + receiving-policy как согласие на приём. Полей version/purpose grants нет. — `services/admin/app.py:_norm_user/111`
- 🟡 **§21.1 Taxonomy Registry** — concepts, edges, distances, forbidden expansions. TAXONOMY (концепты) + ADJACENCY (рёбра) + дистанции-тиры через topical(). Реестра forbidden expansions нет. — `services/matching/app.py:TAXONOMY/23`
- 🟡 **§21.1 Candidate Retrieval** — SQL/geo/vector/source pools. load_candidates читает общий JSON-стор (mtime-кэш) + fallback demo-пул; гео через haversine. SQL/vector-пулов нет. — `services/matching/app.py:load_candidates/317`
- 🟡 **§21.1 Policy Engine** — ALLOW/BLOCK/REVIEW + disclosure. _hard_gates даёт бинарный ALLOW/BLOCK + причину. Состояния REVIEW и disclosure-слоя нет. — `services/matching/app.py:_hard_gates/428`
- 🟡 **§21.1 Allocation Engine** — diversity, caps, exploration, fairness. _slate: диверсификация ≤3/бакет (PER_BUCKET), топ-8. Exploration и fairness отсутствуют. — `services/matching/core_v2.py:_slate/530`
- 🟡 **§21.1 Match Orchestrator** — search run, waves, reservations, proposals. negotiate_candidates + _negotiate_precheck с cap параллельной волны. Reservations и search-run/idempotency нет. — `services/matching/app.py:_negotiate_precheck/768`
- 🟡 **§21.1 Feedback & Learning** — outcome events, training sets, memory suggestions. record_feedback пишет accepted/rejected в файловый стор. Training sets и memory suggestions отсутствуют. — `services/matching/app.py:record_feedback/226`
- 🟡 **§21.1 Audit/Observability** — decision trace, replay, SLA, incident data. trace в карточке + полный explain_match; ctx.now пинится для детерминированного replay. SLA-метрик/incident-данных нет. — `services/matching/core_v2.py:search/612`
- 🟡 **§21.2 POST /intents/compile** — draft, slots, confidence, clarification. /api/agent/plan парсит текст в intent и сразу зовёт кандидатов. Отдельного draft, slots, confidence и clarification нет. — `services/matching/app.py:agent_plan/693`
- 🟡 **§21.2 POST /searches** — search run с idempotency key. /api/agent/match запускает поиск и возвращает slate. Idempotency-key и search-id отсутствуют. — `services/matching/app.py:do_POST/1018`
- 🟡 **§21.2 POST /searches/{id}/expand** — разрешить конкретную ось расширения. agent_plan override даёт явный выбор оси (radiusKm/exactMatchRequired/adjacentAllowed/mode), а _expand_fallback авто-расширяет при пустом slate. Но нет привязки к search-id (поиск stateless). — `services/matching/app.py:agent_plan/695`
- 🟡 **§21.2 POST /proposals** — создать reservation/proposal. /api/agent/negotiate шлёт предложения через precheck-гейты. Reservation-объекта и idempotency нет. — `services/matching/app.py:negotiate_candidates/826`
- 🟡 **§21.2 POST /interactions/{id}/feedback** — structured outcomes. /api/agent/feedback пишет accepted/rejected. Interaction-id и структурированных outcome-полей нет. — `services/matching/app.py:record_feedback/226`
- 🟡 **§21.3 Decision trace (JSON-форма)** — полный аудируемый след решения. trace содержит tier, policy:"ALLOW", domain, a_to_b/b_to_a, reciprocal, band, readiness, config_version. Нет search_id/candidate_id/intent_version/profile_versions/purpose_id/policy.version/evidence[]/allocation/reason_keys/model_versions. — `services/matching/core_v2.py:search/612`
- 🟡 **§21.4 taxonomy/config mismatch → stop+alert** — stop search run; не смешивать версии. load_config ловит sha-рассинхрон/невалидность и не грузит v2. Но вместо stop+alert система молча откатывается на legacy-скорер (другая версия). — `services/matching/core_v2.py:load_config/106`
- 🟡 **§21.4 overload → queue/cap concurrent** — queue/background, cap concurrent runs. cap параллельных предложений (волна 2/3) в precheck. Очереди/фонового поиска и cap на число одновременных search-run нет. — `services/matching/app.py:_negotiate_precheck/781`
- 🟡 **§21.4 pilot goal: async, real progress, no decorative %** — <2s ack, async, реальные стадии. «Без декоративного процента» на UI соблюдён — наружу отдаются банды (assign_band). Async-поиск, стадии прогресса и <2s ack не реализованы. — `services/matching/core_v2.py:assign_band/470`
- 🟡 **§22.1 Рекомендуемый scope доменов** — walks/coffee/language/networking/games; sport/dating отдельно. Домены walk/social_meet/language_exchange/professional_networking/games в YAML + infer_domain; dating под release_gate=separate_safety_legal_track. Реального supply/пилота нет. — `services/matching/core_v2.py:infer_domain/146`
- 🟡 **§22.2 Этап 0 Contracts** — schemas, config registry, state machines, policy matrix. schema.json + config + load_config-валидатор + sha-pin + матрица semantic_tiers; determinism-тест как replayable example. State machines отсутствуют. — `services/matching/core_v2.py:load_config/100`
- 🟡 **§22.2 Этап 3 Controlled proposals** — waves, receiving policy, idempotency, revalidation. Волны (cap 2/3) + receiving-policy + revalidation в precheck. Idempotency нет; race-тестов нет. — `services/matching/app.py:_negotiate_precheck/768`
- 🟡 **§22.2 Этап 4 Plans/outcomes** — plan states, feedback, completion. record_feedback пишет исход. Plan states и completion отсутствуют. — `services/matching/app.py:record_feedback/226`
- 🟡 **§22.3 Explicit feedback без длинной анкеты** — короткий явный feedback. record_feedback принимает только accept/reject — без длинной анкеты; но это единственный канал исхода. — `services/matching/app.py:record_feedback/226`
- 🟡 **§23.1 Обязательная модульная структура** — matching-core/ с contracts/config/…/tests. Есть config/ (yaml + schema.json), валидатор в core_v2.load_config, tests реализованы одним тест-файлом. Остальные модули свёрнуты в app.py + core_v2.py; contracts/*.ts и по-модульных директорий нет. — `config/schema.json`
- 🟡 **§23.2 #7 нет свободных agent-диалогов вместо событий** — protocol events, не диалоги. Precheck даёт протокольные гейты, но negotiate_one — свободный LLM-диалог агента B, который и выносит accept/reject. — `services/matching/app.py:negotiate_one/731`
- 🟡 **§23.2 #10 не показывать проценты без калибровки** — банды вместо процентов. Наружу (profile/карточка) показывается качественный band. Но в card-контракте остаётся score=round(lcb*100,1) — некалиброванный процент. — `services/matching/core_v2.py:search/600`
- 🟡 **§23.2 #11 веса в одном месте** — single source of weights. v2-веса/пороги живут только в sha-pinned YAML. Но legacy-скорер держит отдельный изменяемый WEIGHTS-словарь + /api/agent/weights — второй источник. — `services/matching/app.py:WEIGHTS/168`
- 🟡 **§23.3 DoD: typed input/output contract** — типизированный контракт I/O. schema.json типизирует конфиг + фиксированный card-контракт. Python-код без типов, TS-контрактов доменных объектов нет. — `config/schema.json`
- 🟡 **§23.3 DoD: explicit purpose и policy decision** — явные purpose+policy. policy:"ALLOW" пишется в trace; purpose приближён domain'ом, отдельного purpose_id нет. — `services/matching/core_v2.py:search/612`
- 🟡 **§23.3 DoD: config/model/policy version logged** — логирование версий. config_version есть в trace/meta. Версии модели и policy не логируются. — `services/matching/core_v2.py:search/615`
- 🟡 **§23.3 DoD: deterministic reason keys** — детерминированные reason keys. Причины детерминированы из known_match-признаков, но это ru/en-фразы (_REASON), а не канонические reason_keys вида "same_time". — `services/matching/core_v2.py:_presentation/497`
- 🟡 **§23.3 DoD: degradation behavior** — поведение при деградации. Есть LLM-fallback (parse_intent) и config-fallback (v2→legacy). Прочие деградации (vector/policy/timeout/notification) не реализованы. — `services/matching/app.py:parse_intent/421`
- 🟡 **§23.3 DoD: observable events + dashboard field** — события + поле дашборда. Есть decision trace на карточке/в explain_match. Событий и dashboard-полей нет. — `services/matching/core_v2.py:search/612`
- 🟡 **§23.4 #1 сначала contracts + config validator** — порядок: контракты/валидатор. config + load_config-валидатор (sha-pin + кросс-проверки) реализованы. Контрактов как .ts нет. — `services/matching/core_v2.py:load_config/100`
- 🟡 **§23.4 #2 затем policy engine + state machine** — policy + state machine. Policy как _hard_gates реализован. State machine отсутствует. — `services/matching/app.py:_hard_gates/428`
- 🟡 **§23.4 #5 orchestration/proposals** — оркестрация/предложения. negotiate_candidates + precheck реализуют отправку. Reservations/idempotency нет. — `services/matching/app.py:negotiate_candidates/826`
- 🟡 **§23.4 #7 ML-интерфейсы заранее, без фейк-вероятностей** — ML-заглушки без случайных вероятностей. Фейковых/случайных вероятностей нет — всё детерминировано, конфиг честно помечает acceptance_probability absent in MVP. Но и заранее созданных ML-интерфейсов/заглушек нет. — `config/Kleal_Matching_Core_Config_v2.yaml:249`
- 🟡 **§23.4 #8 fixture suite на каждом этапе + сохранять traces** — прогон фикстур + сохранение trace. Fixture suite есть, trace формируется в карточке/explain. Traces не персистятся отдельно по каждому прогону. — `services/matching/test_core_v2.py`

**⬜ Не реализовано (31):** `§21.1 Match Capsule Builder`, `§21.1 Group Formation Core`, `§21.1 Plan Coordinator`, `§21.1 Cost Governor`, `§21.2 POST /intents/{id}/confirm`, `§21.2 GET /searches/{id}`, `§21.2 POST /proposals/{id}/respond`, `§21.2 POST /groups/form`, `§21.2 POST /plans`, `§21.2 EVENT policy_changed`, `§21.2 EVENT match_state_changed`, `§21.2 EVENT exposure_logged`, `§21.4 vector index unavailable → structured only`, `§21.4 policy service unavailable → fail closed`, `§21.4 notification failure → outbox retry`, `§21.4 ranking timeout → partial/waiting`, `§22.2 Этап 5 Closed Barcelona pilot`, `§22.2 Этап 6 Group formation`, `§22.2 Этап 7 Calibrated ML`, `§22.3 Город/районы partitioned`, `§22.3 Ограниченное число активных intent/юзер`, `§22.3 Ручной review слабых/редких доменов`, `§22.3 Ежедневный dashboard supply/demand`, `§22.3 Incident owner для privacy/safety/races`, `§22.3 Weekly taxonomy/config review`, `§23.2 #8 не ранжировать группы средним pair score`, `§23.2 #13 нет write без idempotency/version`, `§23.3 DoD: race/idempotency test для write`, `§23.4 #6 group formation — отдельный модуль`, `§24 Самооценка (таблица 10 критериев, итог 98/100)`, `§24 Два незакрытых пункта (правовая оценка в Испании + эмпирическая калибровка)`

## Приложения A–E (config, псевдокод, acceptance tests, purpose-binding, источники)

_✅ 15 · 🟡 16 · ⬜ 28_


**Реализовано (полностью / частично):**

- ✅ **§A canonical config + sha-pin** — Единый machine-readable config, sha-verify + валидация. load_config читает YAML, сверяет sha (PINNED_SHA=21505ccb… совпадает с checksum config), парсит mini-YAML и валидирует: сумма 7 весов каждого домена=1.0, priors и пороги в [0,1], наличие semantic_tiers/user_facing_bands. — `services/matching/core_v2.py:load_config:100-136 (PINNED_SHA:31)`
- ✅ **§A score_semantics: reciprocal formula** — Реципрокность 0.7*min+0.3*mean. reciprocal_score = 0.7*lo + 0.3*(lo+hi)/2, где lo=min(lcb), (lo+hi)/2=mean(lcb) над консервативными оценками — точная формула спеки. — `services/matching/core_v2.py:reciprocal_score:352-355`
- ✅ **§A score_semantics: relevance/coverage/lcb** — relevance_lcb=clamp(mean-λ(1-cov)), ranges [0,1]. directional_score: mean=acc/tw, coverage=kw/tw, lcb=max(0,min(1,mean-lam*(1-cov))); значения в [0,1]. — `services/matching/core_v2.py:directional_score:327-350`
- ✅ **§A calibrated_probability disabled** — acceptance_probability отсутствует в MVP. Карточка/trace из search не содержат калиброванной вероятности — только lcb/coverage/band, что соответствует enabled_in_mvp:false. — `services/matching/core_v2.py:search:598-616 (no probability field)`
- ✅ **§A outreach: max parallel personal proposals** — Кап параллельных персональных предложений (2/urgent 3). _negotiate_precheck берёт cap из config: default_parallel_proposals=2 либо urgent_same_day_parallel_proposals=3 при 'soon'-времени, и режет волну (sent>=cap → queued). Подтверждено тестами NEG2/NEG3. — `services/matching/app.py:_negotiate_precheck:780-815; config:206-207`
- ✅ **§A outreach: allowed tiers + broad consent** — Персональный outreach только T0/T1; T2 — по broad consent. outreach_tier_ok = T0/T1 всегда, T2 только при broadConsent, T3+ никогда — и в slate (search), и на границе отправки (_outreach_ok). — `services/matching/core_v2.py:search:581; services/matching/app.py:_outreach_ok:758-766`
- ✅ **§C.1 sparse не обгоняет full** — Разреженный профиль не выигрывает без low-coverage отметки. unknown добавляет prior и снижает coverage → lcb ниже, band не поднимается до especially_close. Покрыто тестом C1a-e. — `services/matching/core_v2.py:directional_score:340-350; test_core_v2.py:58-66`
- ✅ **§C.2 not_applicable != unknown** — not_applicable не снижает coverage. Состояние NA пропускается (continue) до tw, исключаясь из знаменателя; тест C2 подтверждает online (гео=NA) даёт coverage выше offline с unknown-гео. — `services/matching/core_v2.py:directional_score:337-338; test_core_v2.py:69-74`
- ✅ **§C.3 нет двойного счёта** — Один evidence не даёт вес exact+tag+category+embedding. Одна агрегированная субфича на группу; алиасы одного интереса схлопываются в matched-set (тест C3: coffe/coffee/coffees не дают прибавки). Embedding-слоя нет. — `services/matching/core_v2.py:build_features:207-219; test_core_v2.py:77-83`
- ✅ **§C.4 tier — провенанс, не скор** — T2 не становится T1 из-за хорошего времени. assign_tier определяет тир по таксономии/реципрокности, независимо от времени/гео/скора; тест C4 держит sibling на T2 при идеальном времени. — `services/matching/core_v2.py:assign_tier:358-369; test_core_v2.py:104-108`
- ✅ **§C.5 safety-block до feature building** — Заблокированный кандидат не скорится. Hard-gates отсеивают в match_candidates до вызова search, paused отсекается в начале цикла search до build_features; тест C5 (paused/minor/self не в результатах). — `services/matching/app.py:match_candidates:620-625; core_v2.py:search:559`
- ✅ **§C.15 T2 outreach нужен consent** — Dota-intent не шлётся LoL-игроку без broad consent. Sibling→T2, personal outreach запрещён без broadConsent и в slate, и на отправке; тесты C15 + R2/R4. — `services/matching/core_v2.py:search:581-584; app.py:_outreach_ok:758-766; test_core_v2.py:131-138`
- ✅ **§C.21 LLM outage не отменяет gates** — Отказ LLM не отключает policy-гейты. Скоринг и hard-gates полностью детерминированы без LLM; LLM только в parse_intent/negotiate, оба с детерминированными fallback (_fallback_parse, negotiate_one). — `services/matching/app.py:_hard_gates:428-452; _fallback_parse:379; negotiate_one:752-756`
- ✅ **§C.23 reason keys без выдуманных фактов** — В причинах только реальные подтверждённые факты. _presentation формирует reasons только по known_match-группам, а gap — по known_mismatch/unknown; тест C23 (нет vibe/nearby/role/format/constraints для unknown-групп). — `services/matching/core_v2.py:_presentation:497-525; test_core_v2.py:141-145`
- ✅ **§C.24 replay по trace** — Реплей воспроизводит результат на той же версии config. Движок детерминирован (без рандома/LLM), ctx.now пинится, trace содержит config_version, config sha-запинён; тест C24 сверяет два прогона. — `services/matching/core_v2.py:search:555,612-615; test_core_v2.py:147-150`
- 🟡 **§A user_presentation: bands, no exact %** — Качественные bands вместо процента. 4 band'а (assign_band+BAND_LABELS) реализованы, карточка несёт band/band_ru/band_en; но legacy-поле score=lcb*100 всё ещё в карточке (search:600). — `services/matching/core_v2.py:assign_band:470-475; search:600 (score=round(lcb*100,1))`
- 🟡 **§A monetization: no ranking boost** — Оплата не влияет на ранжирование. Инвариант держится по построению: скоринг детерминирован только по 7 фичам, полей subscription/payment в модели и в directional_score нет. Активного guard'а или теста нет; ranking_boost_allowed:false лишь декларирован в config/schema (не исполняемый код). — `services/matching/core_v2.py:directional_score:327-350 (нет платёжных входов)`
- 🟡 **§B.1 search pipeline** — Псевдокод основного поиска. Реализованы feature building, directional/reciprocal score, allocation-rerank (_slate диверсификация), presentation (reasons+gap), load+валидация config; hard-gates ALLOW/BLOCK перед скорингом. Нет purpose-bound capsule, per-tier retrieval-budget цикла с ранним break, policy snapshot/REVIEW и audit.log_search. — `services/matching/core_v2.py:search:545-623; services/matching/app.py:match_candidates:611-632`
- 🟡 **§C.6 privacy change SENT→ACCEPT → POLICY_CHANGED** — Ревалидация приватности на переходе принятия. Политика/eligibility ревалидируются против ЖИВОГО стора на границе ОТПРАВКИ предложения; но состояний SENT/ACCEPT и кода POLICY_CHANGED нет. — `services/matching/app.py:_negotiate_precheck:787-798`
- 🟡 **§C.11 subscription не меняет relevance** — Флаг подписки не влияет на relevance/позицию. Скоринг детерминирован только по 7 фичам; поля subscription в модели нет, инвариант держится по построению, но отдельного флага/теста нет. — `services/matching/core_v2.py:directional_score:327-350`
- 🟡 **§C.12 dating prefs не в friendship search** — Dating-предпочтения недоступны дружескому поиску. datingOk читается только при intent.type=='dating' (hard-gate), social/friendship поиск его не использует; но полноценной purpose-изоляции dating-полей нет. — `services/matching/app.py:_hard_gates:437`
- 🟡 **§C.13 friendship decline не учит dating ranker** — Отказ в дружбе не обучает dating-ранкер. В core_v2 фидбэк не влияет на relevance (инвариант, строка 17); record_feedback только сохраняет в сессию. Кросс-purpose обучения нет, но стор фидбэка глобальный, отдельного dating-ранкера/scoping нет. — `services/matching/core_v2.py:17; app.py:record_feedback:225-229`
- 🟡 **§C.14 exact live location не в payload** — Точная живая локация не попадает в discovery. Матч-карточка отдаёт только грубую дистанцию km, _latlon предпочитает coarseLat/coarseLon; но explore_plans возвращает lat/lon (пусть приближённые/смещённые от area-центра). — `services/matching/core_v2.py:_latlon:185-194; app.py:explore_plans:867-874`
- 🟡 **§C.22 vector outage сохраняет structured retrieval** — Отказ вектора не ломает структурный ретривал. Векторного/embedding-ретривала нет; ретривал полностью структурный (таксономия topical/cat_of), потому работает без вектора — но это по отсутствию слоя, а не спроектированный fallback. — `services/matching/app.py:topical:138; cat_of:108`
- 🟡 **§D возраст** — Purpose-условное использование возраста. Возраст используется только как eligibility hard-gate (MIN_AGE, minAge/maxAge), никогда как relevance-фича; но не purpose-условно (нет точного возраста по consent для dating, age-mode для games). — `services/matching/app.py:_hard_gates:435-443`
- 🟡 **§D пол / orientation (не использовать)** — Гендер/ориентация выключены по умолчанию. Полей gender/orientation в модели пользователя нет (grep — 0 совпадений) — не используются нигде; «не использовать» выполнено по отсутствию, отдельного sensitive-контура для dating нет. — `services/admin/app.py:_norm_user:111+ (нет gender/orientation)`
- 🟡 **§D языки** — Языки: feasibility и core-role для language. langs используются как communication feasibility (requiredLanguages hard-gate) и как core-поле language_exchange (domain_constraints); staged/purpose-matrix различий нет. — `services/matching/app.py:_hard_gates:444-446; core_v2.py:build_features:287-298`
- 🟡 **§D interests** — Интересы: core-фича; для dating только подтверждённые. interests — основная semantic-фича во всех доменах; для dating используются «как есть», без фильтра «только подтверждённые dating-relevant». — `services/matching/core_v2.py:build_features:204-219`
- 🟡 **§D exact availability** — Доступность только по текущему intent. Доступность берётся из intent.time + open/receiving.quiet_hours (time_feasibility/readiness); «current intent only» жёстко не enforced. — `services/matching/core_v2.py:build_features:221-230; readiness_state:427-459`
- 🟡 **§D location** — Только грубая зона/venue. Используются грубые coarseLat/coarseLon и полосы GEO_BANDS, карточка отдаёт km; venue и staged-disclosure для dating нет. — `services/matching/core_v2.py:_latlon:185-194; GEO_BANDS:172`
- 🟡 **§D behavioral reliability** — Поведенческая надёжность только операционно. Сигналы надёжности (blocksMe/pending/declinedOwnerDaysAgo/feedback) используются только как операционные gate'ы, не как relevance; «stricter review» для dating нет. — `services/matching/app.py:_hard_gates:430-434`

**⬜ Не реализовано (28):** `§A outreach: max_agent_probes_per_search:3`, `§B.2 accept_proposal`, `§B.3 form_group`, `§C.7 идемпотентный accept`, `§C.8 concurrent capacity`, `§C.9 expired proposal`, `§C.10 counter после withdrawal`, `§C.16 language role hard (learner/native)`, `§C.17 founder target по target, не self`, `§C.18 padel group role/side отклонение`, `§C.19 group pairwise block`, `§C.20 event vs user транзакции/copy`, `§D имя/публичный аватар (по disclosure)`, `§D профессия`, `§D inferred memory (soft+decay)`, `§E.1 Product/Technical Spec v1`, `§E.2 Expert Audit v1`, `§E.3 Карта интента + условия мэтчинга`, `§E.4 GDPR (EU) 2016/679`, `§E.5 EDPB Guidelines ADM/Profiling`, `§E.6 EU AI Act (EU) 2024/1689`, `§E.7 Xia et al. Reciprocal Recommendation`, `§E.8 Su, Bayoumi, Joachims`, `§E.9 Yang et al. Reciprocal Recommenders`, `§E.10 Tomita, Yokoyama Fair Reciprocal`, `§E.11 Basu Roy et al. Group Formation`, `§E.12 Hayashi et al. Off-Policy Eval`, `§E.13 PostGIS/H3/pgvector`
