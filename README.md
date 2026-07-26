# Kleal — microservices

Kleal is an AI-agent social/matchmaking prototype. It used to be three single-file Python apps; it is
now split into **five small services** behind one **gateway**, so two developers can each own services
and work in parallel without stepping on each other.

```
                         ┌───────────────────────── one public URL (cloudflared) ──────────────────┐
                         │                          gateway  :7080                                 │
                         │        routes by path prefix; the only 0.0.0.0-bound process            │
                         └───┬──────────────┬───────────────────────┬───────────────┬──────────────┘
              / , /onboarding│   /profile    │   /api/agent/*        │ /api/onboarding/* (+ /api/v2/*)
                             ▼               ▼                       ▼               ▼
                    onboarding :7072   profile :7073        matching :7074     onboarding :7072
                        (funnel UI)     ("main page")        (buddy agent)        (funnel API)
                             │                                     │
                             └──────────────┬──────────────────────┘
                                            ▼   HTTP  (keyless — shared/llm_client.py)
                                       llm  :7071   ← the ONLY holder of API keys / model URLs
                                            ▼
                                     vLLM / aitunnel models
```

## Services

| Service | Port | Responsibility | Frontend? | Owner |
|---|---|---|---|---|
| **gateway** | 7080 | Single public entry; routes by path prefix; serves `/menu`. No logic, no keys. | — | Dev A |
| **llm** | 7071 | The only service with model URLs + **API keys**. Exposes `POST /llm/complete`, `GET /llm/models`. | — | Dev A |
| **onboarding** | 7072 | Profile-setup funnel: messenger UI + `/api/onboarding/*`. Calls llm over HTTP. | ✅ | Dev A |
| **matching** | 7074 | Buddy agent: intent parse → ranked candidates → agent negotiation. `/api/agent/*`. | — | Dev B |
| **profile** | 7073 | The "main page" / Agent-Home + profile screens. Static; its JS calls `/api/agent/*`. | ✅ | Dev B |

Contracts between services are frozen in [`shared/contracts.md`](shared/contracts.md).

## Run it

```bash
cp .env.example .env          # fill SELF_BASE (self-hosted vLLM) and/or AITUNNEL_KEY
python run_all.py             # boots all 5 → open http://127.0.0.1:7080
#  --no-llm  skips llm-service for pure front-end work
```

or with Docker:

```bash
docker compose up --build     # gateway published on :7080, the rest internal-only
```

## Layout

```
run_all.py            docker-compose.yml   docker/Dockerfile   .env.example
shared/               llm_client.py · http_util.py · kleal_lib.py · contracts.md
services/
  gateway/  llm/  onboarding/  matching/  profile/     # each: app.py + README.md + requirements.txt
legacy/               the pre-split single-file prototype (kept for reference / rollback)
build/                pod deploy generators (chunked gzip+base64 over PTY-SSH + cloudflared)
dating/               SEPARATE real-product monorepo (NestJS/Expo/Vite) — untouched by this repo's tooling
```

## The two seams that keep the teams decoupled

1. **Keys live only in `llm-service`.** Onboarding and matching reach models via `shared/llm_client.py`
   (HTTP), so they hold no secrets — `run_all.py` and docker-compose scrub the keys from every other
   service's environment. Proof: `grep -rIE "AITUNNEL_KEY|SELF_KEY|Bearer" services/onboarding services/matching services/profile services/gateway` returns nothing.
2. **The buddy API (`/api/agent/*`) has one producer and one consumer**, both Dev B (matching produces,
   profile's JS consumes). The onboarding API and the gateway routing table are Dev A's.

See [`shared/contracts.md`](shared/contracts.md) for the exact HTTP interfaces, and each service's own
`README.md` for how to run and change it in isolation.
