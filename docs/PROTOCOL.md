# Kleal — typed agent protocol & outreach orchestration (§13)

Пользовательский агент **не** ведёт свободные разговоры с сотнями LLM — Matching Exchange передаёт
**типизированные события**. Реализовано в [`shared/kleal_protocol.py`](../shared/kleal_protocol.py) (`kp`,
keyless, **LLM-free**, детерминированный) + аддитивная проводка в `matching/app.py`. Единственный LLM-вызов
в пайплайне — `negotiate_one`, и он лишь **формулирует** решение, чей accept/reject бит маппится в типизированное действие.

## §13.1 Девять разрешённых действий
`ACTIONS` = ровно `{ELIGIBILITY_PROBE, PROPOSE_CONNECTION, ASK_INFO, COUNTER_TIME, COUNTER_FORMAT, ACCEPT,
DECLINE, WITHDRAW, EXPIRE}` (`is_action`). Маппинг на текущий пайплайн:
- **PROPOSE_CONNECTION** — карточка в `to_send` (реальное предложение + `kc.build_proposal`).
- **ELIGIBILITY_PROBE** — `decided`-карточка: `passed=True` для queued-overflow (по substring reason, НЕ по
  readiness), `passed=False` для blocked/discovery_only/policy_capped/…; `counter_hint=COUNTER_TIME` при
  `time_infeasible`, `COUNTER_FORMAT` при 'proposals not accepted'.
- **ACCEPT/DECLINE/COUNTER_TIME/COUNTER_FORMAT** — `map_decision_to_action({agree,reply})`: LLM только
  формулирует, типизированное решение выводится детерминированно (agree→ACCEPT; decline+время→COUNTER_TIME;
  decline+формат→COUNTER_FORMAT; иначе DECLINE).
- **ASK_INFO** — есть апстрим как §5.2 clarification (не per-candidate событие). **WITHDRAW** — §14 state
  machine. **EXPIRE** — объявлен через `ttl_seconds/expires_at`.

## §13.1 Message envelope (`build_envelope`)
Оборачивает `kc.build_proposal` в полный конверт, **не пере-деривая** `proposal_id/idempotency_key`:
`{proposal_id, idempotency_key, protocol_version, action, versions{intent, profile_capsule, policy}, purpose,
disclosure_scope, structured_fields, ttl_seconds/expires_at, rendering_key, audit{actor, action, ts,
correlation}}`. Стемпится на `to_send` карточки в `negotiate_candidates`.

## §13.2 Волны (`assign_wave`, cap)
Wave 0 — показать slate (отдельный `/match`, до send-границы). Wave 1 — top open_now, cap из конфига.
Wave 2 — queued-overflow (assignment детерминирован; async re-send по refusal/timeout — **infra**). Wave 3 —
urgent (SOON_WORDS) ИЛИ **user-allowed expansion**: `broadConsent` поднимает cap до `max(base, 3)` **без
хардкода 2/3** (config-derived base сохранён). Дефолт: ≤3 одновременных personal proposals; массовая рассылка
невозможна. Карточки precheck аддитивно несут `action`/`action_detail`/`wave` (NEG1-4/C4-SEND1 byte-identical).

## §13.3 Границы автономности — ENFORCED
`AUTONOMY_BOUNDARIES` = `{can_auto: [compile_draft_intent, retrieval, allowlisted_clarification,
explanation_from_reason_keys, send_within_pre_confirmed_outreach_policy], requires_consent: [...]}`. Не просто
декларация — **принуждено**:
- **expand-hard-constraints + dating** — за `/confirm` (`kc/ki.apply_confirmation`, §5);
- **reveal-new-sensitive-field** — за disclosure-clamp (`build_proposal` + `_revalidate_disclosure`, §8.4);
- **confirm payment/booking/venue** — `guard_no_payment_booking_venue_confirm` (в `negotiate_candidates`
  флипает `agree=False`, `code='NEEDS_CONSENT'`);
- **accept-multiple-conflicting-plans** — `guard_no_conflicting_plans` (overlap окна с активным планом);
- **reinterpret-refusal-as-try-later** — `guard_no_refusal_retry` (+ declined-cooldown hard gate).
Все guard'ы — pure, absent-permissive, с **POSITIVE-firing** тестами (не только absent). Guard'ы живут ТОЛЬКО
в `negotiate_candidates`, не в `_negotiate_precheck` (NEG тесты бьют precheck напрямую).

## Статус (честно): **done_prior 12 · done 9 · partial 7 · blocked_infra 2 · pilot_disabled 1**
- **done:** 9 действий, конверт (все §13.1 поля), wave-assignment + broadConsent cap, 3 guard'а, LLM-free модуль.
- **done_prior:** parallel-cap ≤3 + no-mass-send, auto compile/retrieval/explanation/send-within-policy, idempotency.
- **partial:** ASK_INFO/EXPIRE/COUNTER_* — типизированные ярлыки/хинты, не эмитятся как transitions; reveal-
  sensitive — на уровне stage+purpose, не per-field-newness; payment-guard — defensive/latent.
- **blocked_infra (2):** async Wave-2 re-send scheduler (refusal/timeout trigger); реальный per-message
  transport. **pilot_disabled (1):** group/event действия (§15/§16).

Тесты: `services/matching/test_core_v2.py` — `C13-*` (12 проверок, incl. POSITIVE-firing guard cases + NEG byte-identity).
