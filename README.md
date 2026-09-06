# Kleal

AI social agent: a person says what they want to do, and the agent finds them real people
to do it with. Everything the user touches is a chat with the agent.

The product is a set of small, single-file Python services (`http.server`, stdlib only —
no framework, no build step). Each service owns one concern and embeds its own UI as one
HTML document, so any service can be deployed by copying one file.

## Services

Every application service binds `127.0.0.1`. The public edge is **nginx** on `:80`/`:443`
(certbot, `aiopenware.com`), which proxies `/` to the gateway.

> **Verified 2026-08-27, and the older wording was wrong.** This used to read "only the gateway is
> public — one tunnel, one URL". The ephemeral cloudflared tunnel is gone, replaced by nginx with a
> real certificate, and the public surface is now larger than one port:
>
> | bound | what | note |
> |---|---|---|
> | `:443`, `:80` | nginx site `kleal` | `/` → gateway `:7080`; `/admin` and `/api/admin/` go **straight to admin `:7077`, bypassing the gateway** |
> | `:8081` | nginx site `kleal-expo` | → Expo dev server `:8082` |
> | `:7080` | gateway, **also bound to `0.0.0.0`** | reachable without TLS — redundant now that nginx fronts it |
> | `:22` | ssh | |
> | `:25672` | RabbitMQ inter-node port | not mentioned anywhere else in this repo |

| Service | Port | What it owns |
|---|---|---|
| `gateway` | 7080 | The single public entry point. Routing only — no logic, no state, no keys. |
| `llm` | 7071 | The only holder of model endpoints/keys. **On the droplet this unit is dead weight** — see the note under the request flow. |
| `onboarding` | 7072 | Sign-up funnel + accounts + the write path into the user store. |
| `profile` | 7073 | The profile card and every post-onboarding screen (intents, search, messages). |
| `matching` | 7074 | Intent → ranked candidates → agent negotiation. Owner: Dev B. |
| `buddy` | 7075 | The conversational agent: free text → confirmed intent → launch a search. |
| `filtration` | 7076 | Text → canonical topics/category. The shared vocabulary everything matches on. |
| `admin` | 7077 | Operator panel: the store, cohorts, and a matching lab. Token-gated. |

Request flow: `app → nginx :443 → gateway :7080 → service → :17071 → pod llm :7071 → vLLM :8002`.

**Two hosts, and the model is not on this one.** The droplet holds every service and all data; the
RunPod box (`195.26.233.30:24309`) holds only the GPU and the model. The link between them is one
systemd unit, `kleal-llm-tunnel`: `autossh -L 17071:127.0.0.1:7071 -p 24309 root@195.26.233.30`.

So the port every service actually calls is **`17071`, not `7071`** — the unit sets
`LLM_URL=http://127.0.0.1:17071`, and that forwards to the llm-service **on the pod**.

The droplet nevertheless runs its own `kleal@llm` on `127.0.0.1:7071`. Nothing points at it, and it
would fail if anything did: its `SELF_BASE` defaults to `http://localhost:8002/v1`, and no vLLM
listens on 8002 here. It is a running unit with no purpose — do not mistake it for the live one.

## Run

```bash
cd kleal-ms && ops/run.sh all
```

`ops/run.sh <service>` starts one; `ops/run.sh all` starts the set in dependency order.
Ports and inter-service URLs come from `shared/config.py` — the single source of truth.

The model itself is self-hosted on the pod: `ops/start_llama.sh` (vLLM, Llama-3.3-70B AWQ
on :8002). `llm-service` is the only thing that talks to it.

## Contracts

`shared/contracts.md` is the frozen part: endpoint names other teams' code hard-codes,
the user-store row shape, and the rules for changing either. Read it before renaming
anything under `/api/`.

## Layout

```
kleal-ms/
  services/<name>/app.py    one service, one file, UI included
  services/<name>/test_*.py its tests (stdlib assert, no pytest needed)
  shared/config.py          ports, URLs, store paths — single source of truth
  shared/contracts.md       the frozen cross-service contracts
  shared/kleal_lib.py       keyless helpers shared by onboarding + matching
  shared/llm_client.py      the only way to reach llm-service
  shared/http_util.py       JSON request/response boilerplate
  config/                   matching config (sha-pinned YAML) + interest taxonomy
  docs/                     the matching-core specification
  ops/                      start scripts (local and pod)
  tools/                    seeding, evaluation and corpus harnesses
```

## Config

No secrets are committed. Everything is environment-overridable; the defaults in
`shared/config.py` are what the pod actually runs.

- `SELF_BASE` / `SELF_KEY` — the self-hosted OpenAI-compatible endpoint (vLLM).
- `KLEAL_USERS` — the shared user store. Every service must resolve to the *same* file.
- `KLEAL_ADMIN_TOKEN` — admin panel auth; generated per box, never committed.
