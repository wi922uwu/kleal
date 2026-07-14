# onboarding-service (:7072)

The profile-setup funnel: the messenger-style UI (served at `/`) plus the interests-funnel backend.
Carved from the pre-split `kleal_v2.py` (onboarding half). Calls **llm-service** over HTTP for every
extract/reply/summary turn — it holds **no model keys**.

## API (canonical + legacy alias)
| Path | Alias | Purpose |
|---|---|---|
| `POST /api/onboarding/state` | `/api/v2/state` | critical-field completeness for a profile |
| `POST /api/onboarding/chat` | `/api/v2/chat` | one funnel turn → `{reply,options,profile,crit,…}` |
| `POST /api/onboarding/summary` | `/api/v2/summary` | → `{summary}` |
| `GET /` | | the onboarding UI (HTML) |

The embedded HTML still posts `/api/v2/*`; the gateway aliases those to this service, so the front-end
works unedited. New code should use `/api/onboarding/*`.

## Depends on
`llm-service` (via `shared/llm_client.llm_complete`) · `shared/kleal_lib` (imported as `base`) · `shared/http_util`.

## Env
`ONBOARDING_PORT` (7072) · `V2_MODEL` (model id, default `llama_self`) · `LLM_URL` (http://127.0.0.1:7071) ·
`PROFILE_URL` (baked into the "My Profile" hand-off).

## Run
`ONBOARDING_PORT=7072 LLM_URL=http://127.0.0.1:7071 python app.py`. stdlib only.
