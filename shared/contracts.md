# Kleal service contracts (frozen)

These are the **only** ways the services talk to each other. Treat them as frozen APIs — changing
one is a cross-team event. Everything else inside a service is that team's to refactor freely.

---

## 1. LLM contract — `llm-service` (owner: Dev A)

The keyless model gateway. Base URLs and API keys live **only** inside `llm-service`; callers use
`shared/llm_client.py` and never see a key.

| Method | Path | Body | Response |
|---|---|---|---|
| POST | `/llm/complete` | `{model, messages:[{role,content}], temperature?}` | `200 {content}` — assistant text (`""` if the model returned nothing). `502 {content:"",error}` on model failure so the caller's fallback fires. |
| GET | `/llm/models` | — | `200 [{id,label,info}]` |

`model` is a **MODELS id** (e.g. `"llama_self"`), not a URL. Internal only (`127.0.0.1:7071` /
compose DNS `llm:7071`) — **never** exposed through the gateway.

Client: `from llm_client import llm_complete; llm_complete("llama_self", messages, 0.4)`.

---

## 2. Agent contract — `matching-service` (owner: Dev B)

The buddy-agent API. **Path names are FROZEN** — the profile-service frontend hard-codes them.
Reached by the profile UI through the gateway (`/api/agent/*`, path unchanged); also callable
server-to-server.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/agent/plan` | `{query,profile,ctx?,override?}` → structured intent + ranked candidates (+`fallback` if none) |
| POST | `/api/agent/feedback` | `{name,decision}` → record accept/reject (the learning loop) |
| GET/POST | `/api/agent/weights` | read / live-tune the scoring weights |
| POST | `/api/agent/save` · GET `/api/agent/load` | server-side mirror of the client UI state |
| POST | `/api/agent/intro` | `{intent,candidate}` → agent-to-agent intro + icebreaker |
| POST | `/api/agent/negotiate` | `{intent,candidates}` → per-candidate accept/reject verdicts |

---

## 3. Onboarding contract — `onboarding-service` (owner: Dev A)

The funnel APIs. Canonical paths are `/api/onboarding/*`; the legacy `/api/v2/*` paths are kept as a
**gateway alias** so the existing embedded HTML keeps working unedited.

| Method | Path (+ alias) | Purpose |
|---|---|---|
| POST | `/api/onboarding/state` (`/api/v2/state`) | `{profile}` → critical-field completeness |
| POST | `/api/onboarding/chat` (`/api/v2/chat`) | `{messages,profile}` → `{reply,options,profile,crit,...}` |
| POST | `/api/onboarding/summary` (`/api/v2/summary`) | `{profile}` → `{summary}` |

---

## Shared code (`shared/`)

`llm_client.py`, `http_util.py`, `kleal_lib.py` are copied into each service image at build (never a
runtime mount) so a shared edit can't silently break a running service. `kleal_lib.py` holds the
keyless deterministic helpers/prompts the onboarding funnel needs (`parse_reply`, `_extract_json`,
`sanitize_output`, …). It is imported as `base` in onboarding-service. Keep it small and stable.
