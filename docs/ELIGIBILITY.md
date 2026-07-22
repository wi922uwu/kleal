# Kleal — eligibility, privacy, safety, purpose binding (§8)

Реализовано в [`services/matching/app.py`](../services/matching/app.py). Скоринг стартует **только после
ALLOW**; BLOCK не попадает в ranking/probe; REVIEW = не предлагать автоматически до ответа пользователя /
проверки safety-трека. Всё аддитивно — новые гейты срабатывают ТОЛЬКО на присутствующем ограничительном
значении и по умолчанию ALLOW при отсутствии поля, поэтому демо-пул и все фикстуры остаются byte-identical.

## Важно: базовый отчёт был устаревшим
`docs/SPEC_COMPLIANCE.md §8` (✅5·🟡9·⬜18) ссылался на до-рефакторный `app.py` и помечал ⬜ пункты, уже
сделанные в прошлых секциях. Реально **уже сделано** (не в §8, а раньше):
- **REVIEW-статус** (три-state `_policy_decision` ALLOW/REVIEW/BLOCK) — §0;
- **§8.3 контекстные профили + purpose binding + Match Capsule** — §4/§6 (`build_profile_view`,
  `DOMAIN_TO_CONTEXT`, `PURPOSE_FIELDS` deny-complement, `build_match`);
- **§8.2 #1 (перед slate)** и **#2 (перед отправкой)** — `match_candidates` / `_negotiate_precheck`.

## §8.1 Канонические gates (12)
Уже были: mutual-block, fatigue/receiving-readiness, age/legal (18+ и диапазон), dating mode-isolation,
location/radius, language feasibility, capacity (per-user). **Добавлено в §8:**
| Gate | Поле | Результат |
|---|---|---|
| account_status | `accountStatus∈{suspended,deactivated,banned,deleted}` / `suspended=True` | BLOCK (absent→ALLOW*) |
| privacy visibility | `visibility` / `privacy.visibility == 'private'` | BLOCK (absent→ALLOW) |
| safety restrictions | `safetyFlags ∩ {banned,csam_block,legal_hold,restricted}` | BLOCK; `sensitivity=='restricted'`/`'review'`→REVIEW |
| intent-mode isolation | `_cross_purpose_blocked` — purpose пары dating↔{friendship/networking/language/games/sport} | BLOCK (из **своих** intents кандидата) |
| age / location REVIEW | opt-in `intent.soft_eligibility` | age-unknown/out-of-radius BLOCK→REVIEW |

\* account_status спека требует unknown⇒BLOCK; демо/фикстуры не несут поля, поэтому unknown⇒ALLOW —
осознанное отклонение, помечено PARTIAL/DORMANT; включается флагом, когда бэкенд гарантирует `active` на
каждой строке.

**Cross-purpose isolation** (`_cross_purpose_blocked`) — **shared helper**, вызывается и в `_policy_decision`
(retrieval BLOCK), и в `_negotiate_precheck` (send BLOCK), поэтому пара не проскочит через
`/api/agent/negotiate`. Purpose кандидата берётся **только из `c['intents']`** (не из datingOk/receiving/
interests) — гарантия byte-identity над реальным `_gen_pool` (тест `C8-GENPOOL-IDENTITY`, dating и non-dating).

## §8.2 Точки ревалидации (7) + POLICY_CHANGED
`revalidate(intent, candidate, checkpoint)` (read-only, тот же gate-stack) → `{decision, code, reason,
readiness, disclosure}`. `code == 'POLICY_CHANGED'` тогда и только тогда, когда живое решение **строже**
базовой линии вызывающего (никогда не продолжать молча старую транзакцию).
- **#1 slate, #2 send** — были (retrieval + send boundary).
- **#3 profile-open** — `POST /api/agent/revalidate`.
- **#4 on-accept** — re-gate в `negotiate_candidates`: при POLICY_CHANGED кандидат не записывается как match.
- **#5 shared-chat, #6 reveal-place/contact** — решение отдаётся (`revalidate` + disclosure-ladder), но
  создание чата / раскрытие контактов живёт в buddy/profile → enforcement там (PARTIAL/cross-service).
- **#7 state-change** — синхронная перечитка live-стора; event-bus авто-ре-эвал → BLOCKED_INFRA.
Эндпоинт: `POST /api/agent/revalidate`; коды/чекпоинты видны в `GET /api/agent/weights`.

## §8.4 География и время
- **home/work — никогда не точка discovery**: `_PRECISE_LOCATION_KEYS` вычищаются из каждой карточки в
  `_stamp_contracts` (no-op сегодня; жёсткий барьер, когда апстрим начнёт их собирать). Retrieval — только
  грубые `km`/coarse-coord → GEO_BANDS.
- **slot feasibility** (`_time_feasible`): absent-permissive; при окнах с обеих сторон — UTC-нормализация по
  `tz_offset_min` + overlap ≥ min_duration + travel_buffer. PARTIAL: DST-таблицы/travel-routing — infra.
- **exact place только после взаимного согласия** (`_revalidate_disclosure`): `exact_place_ok` = full-stage
  **И** существует Match Capsule (взаимный accept). Тест `C8-REVEAL`.
- **H3-cell / район** — BLOCKED_INFRA (нет H3-библиотеки в stdlib).

## Статус (честно) — базовый ✅5·🟡9·⬜18 (устаревший) → **done_prior 10 · done 6 · partial 12 · blocked_infra 5**
- **done (в §8):** account_status/privacy/safety гейты, cross-purpose isolation (retrieval+send),
  age/location REVIEW (opt-in), `revalidate`+POLICY_CHANGED+#3/#4, reveal-ladder, home/work-scrub, time-skeleton.
- **done_prior:** REVIEW-статус, §8.3 (контекстные профили/purpose-binding/Match Capsule), #1/#2.
- **partial/DORMANT:** новые гейты по полям (account/privacy/safety/mode) — additive-safe, но **дремлют**,
  пока admin/onboarding не начнут писать поля в стор; #5/#6 enforcement cross-service; #7 без event-bus.
- **blocked_infra:** реальный suspension-бэкенд, H3-cells, полная interval-algebra + DST/travel-mode,
  per-user исходный timezone.

Тесты: `services/matching/test_core_v2.py` — `C8-*` (12 проверок incl. `C8-GENPOOL-IDENTITY` — byte-identity
над реальным `_gen_pool`, и `C8-REVAL` POLICY_CHANGED).
