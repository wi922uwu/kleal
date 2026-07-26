# CLAUDE.md — Kleal

Shared brain for anyone (human or Claude) working in this repo. Keep it short and accurate.

## What this is
Kleal — an AI-agent social/matchmaking **prototype**, split into microservices so two devs can work in
parallel. Services are single-file Python `http.server` apps (**stdlib only**, no frameworks) with
HTML/CSS/JS embedded in raw `r'''...'''` strings. Full rationale in [README.md](README.md); frozen
inter-service contracts in [shared/contracts.md](shared/contracts.md).

`dating/` is a **separate real-product monorepo** (NestJS/Expo/Vite) — the source of the design specs.
**Do not modify it**; it is reference only.

## Services (each: `services/<name>/app.py` + README + requirements)
| Service | Port | Does | Owner |
|---|---|---|---|
| gateway | 7080 | single public entry; prefix routing; `/menu` | Dev A |
| llm | 7071 | **only holder of model URLs + API keys**; `POST /llm/complete`, `GET /llm/models` | Dev A |
| onboarding | 7072 | **Archivist** agent — onboarding funnel: profile + intents; UI + `/api/onboarding/*` (+`/api/v2/*` alias) | Dev A |
| buddy | 7075 | **Buddy** agent — general chatbot (ChatGPT-like); routes to filtration+matching when the user wants to meet; `/api/buddy/chat` | Dev B |
| filtration | 7076 | **Filtration** agent — magnetises a request to existing categories (labubu→toys); `/api/filter/categorize` | Dev B |
| matching | 7074 | **Matching** agent — signals → ranked candidates by scoring; `/api/agent/*`. Reads users from the shared store (falls back to the built-in 50-pool) | Dev B |
| admin | 7077 | test-mode **admin panel** — user CRUD; **no token**, runs on its OWN separate cloudflared tunnel (not behind the gateway); writes the shared user store; deploy via `build/deploy_admin.py` | Dev A/B |
| profile | 7073 | "main page" / Agent-Home UI (static; hosts the buddy chat) | Dev B |

**User store:** admin-service writes `KLEAL_USERS` (a JSON file; local + pod default `services/matching/users.json` / `/root/kleal-ms/users.json`; compose = named volume `userdata`), matching-service reads it (mtime-cached, falls back to `_gen_pool()`). So admin edits change who gets matched. Gitignored (runtime data). Admin token is a secret → only in `.env`.

**The 4 agents (llm/gateway/profile are infra, not agents):**
1. **Archivist** (onboarding) — builds/edits the user's profile + intents; runs at first launch / profile edits.
2. **Buddy** (buddy) — the general chatbot the user just talks to (broad engagement; web-research via MCP later). When the user wants to meet someone it hands off ↓.
3. **Filtration** (filtration) — categorises the request into existing categories (`labubu`→`toys_collectibles`), extracts canonical topics + `type`/`role`.
4. **Matching** (matching) — deterministic scoring over the categorised intent → best people. (Internally also runs the LLM negotiator + intro sub-steps.)

Flow when the user wants to meet: **buddy → `POST /api/filter/categorize` → build intent → `POST /api/agent/match`**.

## Run
```bash
cp .env.example .env      # SELF_BASE (self-hosted vLLM) and/or AITUNNEL_KEY
python run_all.py         # → http://127.0.0.1:7080   ( --no-llm skips llm-service )
# or: docker compose up --build
```

## Hard rules — do not break
- **Secrets live ONLY in llm-service.** onboarding/matching/profile/gateway must contain **zero** key
  references — they reach models via `shared/llm_client.llm_complete` (HTTP → llm-service). `run_all.py`
  and docker-compose scrub keys from every non-llm service. Sanity check:
  `grep -rIE "AITUNNEL_KEY|SELF_KEY|Bearer" services/{onboarding,matching,profile,gateway}` → nothing.
- **Frozen API paths.** `/api/agent/*` names are hard-coded by the profile frontend — never rename.
  `/api/v2/*` is a legacy alias kept at the gateway; new onboarding code uses `/api/onboarding/*`.
- **Gateway route order matters** — specific prefixes (`/api/agent/`, `/api/onboarding/`, `/profile`,
  `/onboarding`) must be tested **before** the generic `/` default, or API calls fall through.
- **Never commit** `.env` or real keys. Never print the SSH key or the tunnel URL into git.

## Where things live
- `shared/llm_client.py` — the only model access (replaces the old `base.call_llm`)
- `shared/kleal_lib.py` — keyless helpers/prompts; imported as `base` in onboarding-service
- `shared/http_util.py` — `send` / `send_json` / `read_json`
- `legacy/` — the pre-split monolith (reference/rollback; nothing imports it)
- `build/` — pod deploy generators

## Matching engine (services/matching)
100% **deterministic** ranking (no randomness, no LLM in scoring): hard gates → base tier
(reciprocal 85 / exact 70 / adjacent 55 / related 40 / broad 30) → capped modifiers (role, vibe, lang,
availability, entity affinity, geo, feedback ±) → id-hash tiebreak → diversify (≤3 per bucket, top 10).
The LLM is used **only** to parse the free-text query and for agent-to-agent negotiation. Session store
(feedback loop) is file-backed at `services/matching/kleal_store.json` (gitignored).

## Deploy (RunPod pod, PTY-only SSH + cloudflared)
```bash
python build/deploy_microservices.py
ssh -tt -i ~/.ssh/id_ed25519 <POD>@ssh.runpod.io < build/_deploy_ms.sh   # <POD> host: ask the team
```
Ships to `/root/kleal-ms/` (chunked gzip+base64, sha256+ast verify), kills the old processes, launches
all 5, and **keeps the cloudflared tunnel on :7080** so the public URL is unchanged. The trycloudflare
URL is **ephemeral** (changes on tunnel restart) — scrape it from `/root/cf7080.log`; do not hardcode it
in git. Pod ports mirror local; llm-service points `SELF_BASE` at the self-hosted vLLM on `:8002`.

## Gotchas
- Windows: the Bash tool is Git Bash (POSIX sh); use PowerShell for native cmds. Cyrillic POST bodies →
  send UTF-8 bytes; `Invoke-WebRequest` needs `-UseBasicParsing`.
- Raw-string regex: inside `r'''...'''` write `\D`, not `\\D`.
- Deploy sha gate: compare with `awk '{print $1}'`, not `cut -d" "` (breaks inside nested quotes).
- After editing a service, **restart it** — HTML is built at import time, so a running server serves stale HTML.
- Reset the matching feedback loop after tests: delete `services/matching/kleal_store.json`.

## Memory
- Per-machine auto-memory notebook lives under `~/.claude/projects/.../memory/` (run `/memory` to view).
  Not shared via git — cross-team knowledge goes **here in CLAUDE.md**.
- `.mcp.json` adds a project knowledge-graph memory server (`@modelcontextprotocol/server-memory`) —
  approve it on first launch. Its data file `.claude/memory.json` is per-dev (gitignored).
