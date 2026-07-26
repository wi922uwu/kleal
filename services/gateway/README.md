# gateway (:7080)

The single public entry point. One cloudflared tunnel points here; it is the only process bound to
`0.0.0.0`. Reverse-proxies by path prefix — **no business logic, no keys, no state**.

## Routes (order matters — specific prefixes before the `/` fallback)

| Prefix | → | Note |
|---|---|---|
| `/menu` | local landing | two-button page |
| `/api/agent/*` | matching :7074 | path unchanged (profile JS hard-codes these) |
| `/api/onboarding/*`, `/api/v2/*` | onboarding :7072 | `/api/v2/*` = legacy alias |
| `/profile`, `/profile/*` | profile :7073 | prefix **stripped** |
| `/onboarding`, `/onboarding/*` | onboarding :7072 | prefix **stripped** |
| `/` and everything else | onboarding :7072 | default |

## Env
`HUB_PORT` (7080) · `HUB_ONB` · `HUB_PROF` · `HUB_MATCH` — upstream base URLs.

## Run
`HUB_PORT=7080 python app.py` (usually launched by `run_all.py`). stdlib only.
