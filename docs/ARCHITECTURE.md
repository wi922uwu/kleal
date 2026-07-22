# Kleal Matching Core — architecture map (→ spec `Kleal_Matching_Core_Final_Spec_RU_v2`)

This document maps our **Python micro-services prototype** onto the spec's mandatory module
structure (§23.1) and component list (§21.1), so the correspondence is verifiable.

**Why our layout differs from §23.1's `matching-core/` tree.** The spec prescribes a TS-style
multi-directory module. Kleal is intentionally a set of single-file `http.server` services
(see [CLAUDE.md](../CLAUDE.md)), so the spec's *layer separation* is realised two ways: **across
services** (gateway / llm / onboarding / filtration / matching / buddy / admin / profile) and
**within the matching engine**, where [`core_v2.py`](../services/matching/core_v2.py) is sectioned
by exactly the spec's layers. Copying the 15-directory tree verbatim would contradict the service
architecture and add no separation we don't already have — so we align by *responsibility*, not by
folder name.

Legend: ✅ implemented & faithful · 🟡 partial · 🟥 absent (out of prototype scope) · ⭐ exceeds a bare prototype.

## §23.1 module → our code

| Spec module | Our realization | Status |
|---|---|---|
| `contracts/` (profile, intent, candidate, proposal, match, plan, decision-trace) | ad-hoc dicts; shapes documented in [Data contracts](#data-contracts) below; decision-trace = `card.trace` + `explain` | 🟡 typed contracts absent; shapes documented |
| `config/` (matching-core.yaml, **schema.json**, validator) | [`config/Kleal_Matching_Core_Config_v2.yaml`](../config/Kleal_Matching_Core_Config_v2.yaml) + [`config/schema.json`](../config/schema.json) + runtime validator `core_v2.load_config` (sha-pin + weight-sum + ranges) | ✅ |
| `intent-compiler/` | `onboarding/app.py` (Archivist) · `filtration/app.py` (categorise) · `buddy/app.py` · `matching.parse_intent` / `_fallback_parse` | 🟡 spread across services; no P0–P3 clarification policy (§5) |
| `taxonomy/` | `matching/app.py`: `TAXONOMY`, `topical`, `cat_of`, `same_topic` · `core_v2`: `SEM_VALUE`, `infer_domain`, `_TYPE2DOMAIN`, `_BROAD2DOMAIN`, `ALL_DOMAINS` · `filtration` (25 categories) | 🟡 hand-rolled, diverges from the canonical 401-node graph |
| `retrieval/` | `matching.load_candidates` (mtime-cached store) + `_gen_pool` fallback | 🟡 flat person pool; no tiered/ANN retrieval (§7.2) |
| `policy-engine/` | `matching._hard_gates` (paused, block, cooldown, capacity, 18+, dating opt-in, verified, age-band, language, radius) + `_outreach_ok` (tier/consent) | 🟡 binary gate; no ALLOW/BLOCK/**REVIEW** tri-state; no privacy/purpose-binding gate |
| `feature-builder/` | `core_v2.build_features` / `reverse_features` (7 groups, 4 states, no double-count) | ✅ |
| `relevance-engine/` | `core_v2.directional_score` (R_mean, Coverage, `R_lcb = clamp(mean − λ(1−cov))`) | ✅ byte-faithful to §9 |
| `reciprocity-readiness/` | `core_v2.reciprocal_score` (0.7·min+0.3·mean) · `readiness_state` / `is_paused` / `_in_quiet_hours` (6 states, receiving policy §4.4) | ✅ |
| `allocation/` | `core_v2._slate` (diversity ≤3/bucket, top `TOP_N`) | 🟡 diversity only; no exposure caps / exploration / fairness (§11) |
| `orchestrator/` | `matching.match_candidates` · `core_v2.search` · `agent_plan` · `negotiate_candidates` / `_negotiate_precheck` (re-gated send boundary, §8.2) | 🟡 synchronous; no search_id/state, no idempotent proposal txn |
| `group-formation/` | — (config block `group_formation` present, unused) | 🟥 out of scope (§15) |
| `plan-coordination/` | — | 🟥 out of scope (§14 plan states) |
| `feedback-learning/` | `matching.record_feedback` + file-backed session store (`kleal_store.json`); v2 keeps feedback OUT of relevance (§19) | 🟡 no learning loop / bias controls |
| `observability/` | `core_v2.search` → `card.trace` (§21.3 subset) · ⭐ **`matching.explain_match` + `/api/agent/explain`** · ⭐ **admin Matching Lab** (per-feature breakdown, gated-out reasons, domain weights) | ⭐ exceeds baseline |
| `tests/` (fixtures, property, race, safety, domains) | [`services/matching/test_core_v2.py`](../services/matching/test_core_v2.py) — see [Test categories](#test-categories) | 🟡 one runnable file, categorised by comment sections |

Presentation (spec §9.7) lives in `core_v2._presentation` + `BAND_LABELS` + `assign_band`; the user
sees a **qualitative band**, never a raw percent (enforced end-to-end incl. `profile/app.py mBand()`).

## §21.1 components → our services

| Component | Service / file |
|---|---|
| Intent Compiler | onboarding + buddy + filtration + `matching.parse_intent` |
| Profile/Consent Service | admin (`_norm_user`, receiving policy §4.4) + shared user store `KLEAL_USERS` |
| Match Capsule Builder | 🟥 (no purpose-bound capsule; features built inline) |
| Taxonomy Registry | `matching.TAXONOMY` + `filtration` categories |
| Candidate Retrieval | `matching.load_candidates` |
| Policy Engine | `matching._hard_gates` / `_outreach_ok` |
| Feature Builder | `core_v2.build_features` |
| Relevance Engine | `core_v2.directional_score` |
| Reciprocity/Readiness | `core_v2.reciprocal_score` / `readiness_state` |
| Allocation Engine | `core_v2._slate` |
| Match Orchestrator | `matching.match_candidates` / `search` / `negotiate` |
| Group Formation Core | 🟥 |
| Plan Coordinator | 🟥 |
| Feedback & Learning | `matching.record_feedback` + store |
| Cost Governor | `llm/app.py` (single model-access holder; routing/keys) |
| Audit/Observability | `card.trace` + `explain_match` + admin Matching Lab |

## Data contracts

The spec's `contracts/` are typed objects; we use plain dicts. Their real shapes:

- **Intent** — `{type, topics[], role, mode, time, title, requiredLanguages[], minAge, maxAge, verifiedOnly,
  radiusKm, broadConsent, exactMatchRequired, adjacentAllowed}` (no `intent_id`/`version`/`purpose_id`/TTL).
- **Candidate / user** — `{name, interests[], vibe, langs[], area, km, lat, lon, open, role, datingOk, age,
  verified, paused, pending, blocksMe, lastActiveDays, declinedOwnerDaysAgo, intents[], entities[],
  dealBreakers[], formats[], receiving{}}` (normalised by `admin._norm_user`).
- **ReceivingPolicy (§4.4)** — `{status, allowed_domains[], passive_outreach, quiet_hours{start,end,tz_offset_min},
  proposal_budget{per_24h}, paused_until}`.
- **Match card** — `{name, score, band, band_en/ru, tier, kind, km, reasons/_en/_ru, gap_en/ru, coverage, lcb,
  reciprocal, readiness/_en/_ru, can_outreach, unknowns[], trace{}}`.
- **Decision-trace (§21.3)** — our `card.trace` = `{tier, policy:"ALLOW", domain, a_to_b{mean,coverage,lcb,unknowns},
  b_to_a, reciprocal, band, readiness, config_version}`. Missing vs spec: `search_id`, `intent_version`,
  `profile_versions`, `purpose_id`, structured `evidence[]`, `model_versions` (no persisted immutable trace).

## Config (§23.1 `config/`)

- `Kleal_Matching_Core_Config_v2.yaml` — the single source of weights/thresholds/limits, **sha-256 pinned**
  (`21505ccb4add…`). Byte-identical to the spec package.
- `schema.json` — formal structure contract (this repo). Validates with any draft-07 validator.
- **validator** — `core_v2.load_config()` is the *runtime* validator: it checks the sha pin, that every
  domain's 7 weights sum to 1.0, prior/threshold ranges, and rejects unknown feature keys. On any failure it
  falls back to the legacy scorer (⚠️ §21.4 says *stop the run* instead — a known deviation).

## Test categories (§23.1 `tests/`)

`test_core_v2.py` is one runnable suite; its groups map to the spec's categories:

| Spec category | Our tests |
|---|---|
| `fixtures/` | `mk()`, `RECV_ACTIVE`, temp store setup |
| `property/` | C1–C3 (coverage / unknown / no-double-count), V1–V2 (config validation), RCV2b (readiness ⟂ relevance), **PARITY** (`search()` ≡ `explain_match()`) |
| `safety/` | C5 (gate-before-scoring), C15 (tier/consent outreach), NEG1–NEG4 (proposal-send gates), RCV1–9 (readiness / receiving policy) |
| `domains/` | R1–R7 (store regression across chess/coffee/dota/…), C4 (tier provenance), C23 (no invented reasons) |
| `race/` | 🟥 none — no transaction layer (App C tests 6–10 unmodeled) |

## §23.2 forbidden-simplification compliance

| # | Rule | Status |
|---|---|---|
| 1 | one `match_score` | ✅ band/tier/lcb kept separate |
| 2 | tier from score | ✅ `assign_tier` = provenance |
| 3 | unknown = match | ✅ prior + lowers coverage |
| 4 | mix safety/payment w/ relevance | ✅ gates separate; no payment field |
| 5 | embeddings as truth | ✅ (no embedding layer) |
| 6 | LLM bypasses gates | ✅ gates + scoring are LLM-free |
| 7 | free agent-to-agent dialogs | 🟥 `negotiate` uses a free LLM (§13 wants typed events) |
| 8 | rank groups by mean | ✅ n/a (no groups) |
| 9 | dating data cross-mode | 🟥 dating is a domain flag, not an isolated capsule (§17) |
| 10 | percents without calibration | ✅ fixed — qualitative band only |
| 11 | weights in multiple places | ✅ single sha-pinned config |
| 12 | proposal w/o receiving + reval | ✅ fixed — `_negotiate_precheck` re-gates |
| 13 | write w/o idempotency/version | 🟥 no transaction/idempotency layer (§14) |
| 14 | ranking for subscription | ✅ no payment concept anywhere |
| 15 | exact live location in discovery | ✅ coarse km only |

## Beyond the spec baseline (recent work)

- **Observability (§21.3):** `/api/agent/explain` + the admin **Matching Lab** turn the decision trace into
  an inspectable tool — per-feature-group state/value/weight/contribution, the `mean − λ(1−cov)` maths,
  both directions, gated-out candidates *with the gate reason*, considered-but-filtered, and the inferred
  domain's weights/floors. This is richer than the spec's static trace object.
- **Guard:** a `PARITY` test asserts `explain_match` never drifts from `search()` (band/tier/outreach/lcb).
- **Config contract:** `config/schema.json` adds the declarative half of §23.1 `config/`.

## Implementation phase (§22.2)

Roughly **Phase 1–2** (rule-based core + transparent discovery): the deterministic scoring slice §6–§12 is
faithful; Phase 3+ (transactional proposals, plans, group formation, calibrated ML) are the 🟥 rows above.
