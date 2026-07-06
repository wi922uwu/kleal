# Kleal — Onboarding + Profile prototypes

Single-file prototypes for the Kleal onboarding flow and the "agent memory" profile card, built to match the Figma designs. Each app is a self-contained Python `http.server` with embedded HTML/CSS/JS.

## Apps

| File | What | Port |
|---|---|---|
| `kleal_v2.py` | Messenger-style onboarding: splash → basics → location (auto-geo + map) → language → interests funnel (LLM, per-type domain questions) → safety → text summary → menu. | 7072 |
| `kleal_profile.py` | "My Kleal Profile" card (Figma V3): Overview hub + Interests / Your personality / Goals / Safety & Privacy, Edit Signal, drill-in nav. Static, no LLM. | 7073 |
| `llm_demo_local.py` | LLM backend + a 7-model comparison demo. `kleal_v2` reuses its extractor / LLM helpers. | 7071 |

The onboarding hands the finished profile to the profile card via a base64 URL param (`/?p=<...>`), so the two run independently and connect cross-origin.

## Run

```bash
# profile card (static, no LLM needed)
python kleal_profile.py                 # http://localhost:7073

# onboarding (needs an OpenAI-compatible LLM endpoint via SELF_BASE)
python run_v2_local.py                  # http://localhost:7072
```

On the onboarding splash, the **"Emulate onboarding"** button fills a realistic profile and jumps straight to the filled card.

## Config (environment variables)

- `SELF_BASE` / `SELF_KEY` — self-hosted, OpenAI-compatible LLM endpoint (e.g. vLLM serving Llama-3.3-70B) used by the interests funnel.
- `AITUNNEL_KEY` / `AITUNNEL_BASE` — optional, only for the model-comparison demo in `llm_demo_local.py`.
- `PROFILE_URL` — public URL of the profile app, baked into the onboarding "My Profile" handoff (needed when the two apps sit behind separate tunnels).
- `V2_PORT` / `PROFILE_PORT` / `DEMO_PORT` — ports.

**No secrets are committed** — set your own keys via the environment.

## Deploy

`build/deploy_bundle_to_pod.py` generates a remote bash script (gzip + base64 chunks) that deploys both apps to a RunPod pod over PTY-only SSH, wires the profile URL into the onboarding handoff, and opens cloudflared tunnels. Pipe the generated `build/_deploy_bundle.sh` into `ssh -tt ...`.
