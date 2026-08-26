# Matching Core v2 — what changed in matching-service (2026-07-16)

The product side shipped the **final normative Matching Core spec** (`docs/Kleal_Matching_Core_Final_Spec_RU_v2.md`,
53 pp; the .zip package also carries PDF/DOCX + diagrams). Its §23 is an implementation contract with
15 forbidden simplifications — and the v1 scorer violated 8 of them (single additive `match_score`,
tier labels derived FROM the score, no unknown/coverage semantics, geo/lang/vibe mixed into relevance,
raw percentages in the UI, weights in code, no receiving policy, unversioned writes). So scoring was
rebuilt per the spec, **in place and behind a flag** — nothing else in the service moved.

## What runs now

`services/matching/app.py` still owns: HTTP routes (frozen names), taxonomy (`TAXONOMY/cat_of/topical/
_wshare`), **policy hard gates** (spec: scoring only after ALLOW), store loading, negotiation, explore.
The **scoring** is delegated to `services/matching/core_v2.py`:

- 7 feature groups × 4 states (`known_match / known_mismatch / unknown / not_applicable`);
  unknown uses the domain prior and LOWERS coverage — a sparse profile can't silently outrank a
  confirmed one; `not_applicable` is excluded from the denominator entirely.
- `R_mean`, `Coverage`, conservative `R_lcb = clamp(R_mean − λ_domain·(1−Coverage))`, reverse
  direction B→A, reciprocal `0.7·min + 0.3·mean`.
- **Tier T0–T5 = retrieval provenance** (how the candidate was found: own active intent / direct
  interest / sibling-parent / adjacent), never derived from the score. Personal outreach: T0/T1 only,
  T2 needs `intent.broadConsent`.
- **Bands instead of percentages** (spec §9.7): `especially_close / strong_option / broader_option /
  needs_clarification` + 2–3 confirmed reasons (`reasons_ru/en`) + one `gap_ru/en`. Direct matches
  (T0/T1) that miss discovery thresholds stay visible as `needs_clarification` — honest, not hidden.
- Distance is **searcher-relative** (profile/ctx geo), no more Barcelona-centre hardcode; feedback
  history no longer mutates relevance (it stays a gate/learning concern, spec §19).
- Per-candidate `trace` (directional scores, tier, band, config version) — the spec's decision-trace.

**Weights/priors/λ/thresholds live ONLY in `config/Kleal_Matching_Core_Config_v2.yaml`**
(`config_version: matching-core-2.0.0`, sha-pinned `21505ccb…`; the loader refuses a tampered file).
Do not fork weights into code — that's forbidden simplification #11. Config changes = new file +
new `config_version` + re-pin `core_v2.PINNED_SHA`.

## Compatibility & rollback (Dev A / Dev B)

- `/api/agent/match|plan` responses are a **superset** of the old card contract — `name, score
  (=lcb·100 for legacy UIs), tier, kind, km, reasons, agree, note, bucket…` all still present.
  Negotiate/feedback/explore/weights endpoints untouched.
- **Rollback:** start matching with `KLEAL_CORE_V2=0` → the untouched legacy scorer
  (`match_candidates_legacy`) runs. A missing/invalid config auto-falls-back too (fail-safe).
  `GET /api/agent/weights` shows which engine is live (`core.enabled/config_version/error`).
- POST `/api/agent/weights` still tunes the LEGACY weights only; the v2 engine deliberately has no
  runtime weight mutation (versioned YAML is the single source).
- profile-UI shows qualitative bands now (`bandLabel()`); if a candidate has no `band` (legacy
  response) it falls back to the old `score%` rendering, so the UI works with either engine.

## Tests

`python3 services/matching/test_core_v2.py` — 26 checks: the applicable acceptance tests from the
spec's appendix C (#1 sparse-vs-full, #2 not_applicable, #3 no-double-count, #4 tier-not-from-score,
#5 policy-before-scoring, #15 no T2 outreach without consent, #23 reasons-are-facts, #24 replay
determinism), config-validator negatives (sha mismatch, broken weight sums), and store-shaped
regressions (apple/coffee/dota/пиво). Run it before touching scoring.

## Receiving policy + readiness (added 2026-07-16, spec §4.4 / §10.1)

Every store user now carries a `receiving` object (canonical §4.4 shape): `status`
(active|busy|paused), `allowed_domains`, `passive_outreach`, `quiet_hours{start,end,tz_offset_min}`,
`paused_until`. Onboarding writes an ACTIVE default at registration (dating excluded unless the
user opted in); the 4 pre-existing users were backfilled the same shape.

- **Readiness** (`core_v2.readiness_state`): `open_now / open_later (quiet hours) / passive_discovery
  (domain not allowed or passive_outreach=false) / busy (manual or proposal budget spent) / paused /
  unknown`. Per spec it NEVER mixes into relevance — it only gates `can_outreach` (open_now required),
  orders the slate after band (§11.2), and shows as an availability chip. `paused` (incl.
  `paused_until` in the future) leaves retrieval and Explore entirely; busy/quiet people stay
  discoverable. **No policy at all = `unknown` = no personal outreach** (unknown is not openness);
  the demo pool's legacy `open` flag maps True→open_now / False→busy.
- **Enforcement** (`_negotiate_precheck` in matching): every negotiate re-resolves candidates
  against the LIVE store, refuses non-open_now people without calling the LLM, caps the parallel
  wave from the canonical config (2 default / 3 urgent same-day), and logs each sent proposal into
  matching's kleal_store (`_proposals`) — that log feeds the per-24h fatigue budget
  (`max_proposals_received_per_user_24h`, default 4 → readiness `busy`).
- **API**: `POST /api/onboarding/receiving` | `/api/v2/receiving` (onboarding service) —
  `{name}` reads the policy, `{name, receiving:{...}}` applies a WHITELISTED patch atomically.
  The profile UI's "Доступность" toggle (Открыт/Занят/Пауза) uses it; candidate cards show the
  readiness chip when someone isn't open right now.

## NOT implemented yet (deliberately, staged per spec §22)

- proposal/match/plan **transaction state machines** with idempotency+revalidation (negotiate is
  still the demo stub; proposals aren't persisted entities with TTL/waves yet) — stage 3–4;
- allocation caps (exposure/exploration) beyond slate diversity + the proposal-fatigue budget — stage 3;
- group formation, events/rooms as candidate types, the dating isolated contour — stages 6+;
- intent compiler per §5 (buddy's build_intent still plays that role);
- quiet-hours use a fixed pilot tz offset (`tz_offset_min`, default UTC+120 = Madrid summer) —
  real per-user timezones arrive with the plan coordinator.
