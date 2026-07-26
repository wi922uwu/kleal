# llm-service (:7071)

The **only** service that holds model base-URLs and API keys. It exposes a tiny, keyless completion
API so onboarding and matching never see a secret. Internal only (bind `127.0.0.1`); never routed
through the gateway.

## API
| Method | Path | Body → Response |
|---|---|---|
| POST | `/llm/complete` | `{model, messages, temperature?}` → `200 {content}` · `502 {content:"",error}` on model failure |
| GET | `/llm/models` | → `[{id,label,info}]` |

`model` is a registry id (`llama_self`, `llama70`, `mistral32`, …). The `502` on failure is deliberate:
`shared/llm_client.py` re-raises it so callers' existing fallbacks fire.

## Env (secrets — from `.env`, never committed)
`SELF_BASE` / `SELF_KEY` (self-hosted vLLM, the default `llama_self`) · `AITUNNEL_KEY` / `AITUNNEL_BASE`
(the 6 external comparison models) · `LLM_PORT` (7071).

## Run
`LLM_PORT=7071 SELF_BASE=... python app.py`. stdlib only. Adding a model = one line in `MODELS`.
