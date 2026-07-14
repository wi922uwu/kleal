# profile-service (:7073)

The "main page" / Agent-Home + profile screens (the "agent memory" card, intents, discovery/explore
map, match chat). **Static** — no LLM, no server-side logic. Its client JS calls the buddy API at
`/api/agent/*`, which the gateway routes to **matching-service**, so this stays a pure front-end.

It receives the finished onboarding profile via a base64 URL param (`/profile?p=<...>`).

## Endpoint
`GET /` → the profile / Agent-Home UI (HTML). Reached publicly at `<gateway>/profile`.

## Env
`PROFILE_PORT` (7073).

## Run
`PROFILE_PORT=7073 python app.py`. stdlib only. Verbatim copy of the old `kleal_profile.py`.
