# legacy — the pre-split single-file prototype

These are the original Kleal prototype apps, kept for reference and rollback. The project has since
been split into microservices under [`../services/`](../services) + [`../shared/`](../shared) +
[`../services/gateway/`](../services/gateway) — see the top-level [README](../README.md). New work
should happen in the microservices, not here.

| File | Was | Now lives in |
|---|---|---|
| `kleal_v2.py` | onboarding funnel **+** buddy/matching backend in one process (:7072) | split → `services/onboarding/` + `services/matching/` |
| `kleal_profile.py` | profile / Agent-Home UI (:7073) | `services/profile/app.py` (verbatim) |
| `kleal_hub.py` | reverse-proxy hub (:7080) | `services/gateway/app.py` |
| `llm_demo_local.py` | LLM helpers + 7-model comparison demo | keys/`call_llm` → `services/llm/`; keyless helpers → `shared/kleal_lib.py` |
| `run_v2_local.py`, `run_local_demo.py` | local launchers for the above | replaced by `../run_all.py` |

Nothing in the microservices imports from this folder; it is a frozen snapshot.
