# matching-service (:7074)

The buddy/matching agent. Free-text query → structured intent → **hard gates** → base tier
(reciprocal / exact / adjacent / related / broad) → capped modifiers → diversify → ranked candidates,
then LLM **agent-to-agent** intro/negotiation. Deterministic scoring (no randomness, no LLM in the
ranking); the LLM is used only to parse the query and to negotiate. Carved from `kleal_v2.py`
(matching half).

## API — `/api/agent/*` (names FROZEN; the profile UI hard-codes them)
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/agent/plan` | `{query,profile,ctx?,override?}` → intent + candidates (+`fallback` if none) |
| POST | `/api/agent/feedback` | `{name,decision}` → record accept/reject (learning loop) |
| GET/POST | `/api/agent/weights` | read / live-tune scoring weights |
| POST `/api/agent/save` · GET `/api/agent/load` | | server-side mirror of client state |
| POST | `/api/agent/intro` | `{intent,candidate}` → intro + icebreaker |
| POST | `/api/agent/negotiate` | `{intent,candidates}` → per-candidate verdicts |

## State
File-backed session store at `KLEAL_STORE` (default `./kleal_store.json`, gitignored) — holds the
feedback loop + mirrored UI state. Single-replica (JSON file; move to a DB before scaling).

## Depends on
`llm-service` (parse/intro/negotiate) · `shared/kleal_lib._extract_json` · `shared/http_util`.

## Env
`MATCHING_PORT` (7074) · `V2_MODEL` (default `llama_self`) · `LLM_URL` · `KLEAL_STORE`.

## Run
`MATCHING_PORT=7074 LLM_URL=http://127.0.0.1:7071 python app.py`. stdlib only.
