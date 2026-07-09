# Buddy — Kleal app interface + agent

The app the user lands in **after** kleal_v2 onboarding (option A): a bottom tab-bar
(`My Intents · Search · [Buddy] · Messages · Profile`) whose center button is **Buddy**,
the conversational agent that turns a social intent into matched people.

Onboarding stays in **kleal_v2** (`:7072`). When onboarding finishes it redirects here with
the collected profile in the URL as `?p=<base64 utf-8 json>` — the same handoff kleal_v2
already uses for the profile card. This app decodes it (`web/state.js`), shows the tab-bar,
and Buddy uses the profile as context + for matching.

## Layout

```
buddy/
  api.py        HTTP server: static file serving (web/) + JSON API
  agent.py      Buddy tool-dispatch loop (chat ↔ find_people ↔ compose)
  llm.py        OpenAI-compatible client, model via env (LLM_BASE/LLM_KEY/LLM_MODEL)
  matching.py   intent normalization (filtration) + candidate scoring (thin sheet-03)
  tools.py      find_people tool (schema + executor)
  store.py      SQLite: profiles + conversation history
  prompts.py    Buddy persona + tool rules + profile-summary prompt
  web/          static frontend (documented, split by concern)
    index.html  app shell
    styles.css  design tokens + components (mockup palette)
    icons.js    inline-SVG icon set
    state.js    profile from ?p= handoff → Buddy shape → persist + /buddy/onboard
    chat.js     Buddy tab (POST /buddy/chat)
    profile.js  Profile tab (renders the collected profile)
    app.js      tab-bar controller (no onboarding here — that's kleal_v2)
```

## Endpoints
- `GET  /`               → the app (web/index.html)
- `GET  /<asset>`        → static file from web/
- `GET  /buddy/health`
- `POST /buddy/onboard`  `{user_id, profile}` → persist (matchable) + LLM summary
- `POST /buddy/chat`     `{user_id, message}` → `{reply, intent, matches, tool_call}`

## Run locally
```bash
python3 run_buddy_local.py           # :8090 (seeds demo profiles; set SELF_BASE to the pod :8002 tunnel for the LLM)
```
Model/endpoint via env: `LLM_BASE`, `LLM_KEY`, `LLM_MODEL`, `BUDDY_TOOL_MODE` (prompt|native).

## kleal_v2 → Buddy handoff (option A)
kleal_v2 bakes `BUDDY_URL` (env) into its HTML and, on onboarding "Done", redirects to
`BUDDY_URL/?p=<base64 profile>`. Deploy Buddy first, then start kleal_v2 with
`BUDDY_URL=<buddy tunnel>`.
