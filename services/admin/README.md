# admin-service (:7077)

A token-gated **admin panel** to view / add / edit / delete the platform's users while the app runs in
**test mode**. Lives at its own address — `<gateway>/admin` — on the same server. Users are stored in a
shared JSON file (`KLEAL_USERS`) that the **matching agent reads**, so admin edits directly change who
gets matched. On first run it seeds itself from the matching agent's demo pool (`GET /api/agent/pool`).

## UI
`GET /admin` → the admin page (token sign-in → users table with search, add form, inline flag toggles,
edit, delete, and "Reset to demo pool").

## API (all require `X-Admin-Token: <ADMIN_TOKEN>`)
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/admin/ping` | validate the token |
| GET | `/api/admin/users` | list users |
| POST | `/api/admin/users` | add a user |
| POST | `/api/admin/user/<id>` | update (merge) a user |
| POST | `/api/admin/user/<id>/delete` | delete a user |
| POST | `/api/admin/reseed` | reset the store to the demo pool |

Every stored user is normalised to a complete, matching-safe record (`_norm_user`).

## Env
`ADMIN_PORT` (7077) · **`ADMIN_TOKEN`** (set a real one in `.env`; default `changeme-admin`) ·
`MATCH_URL` (for seeding) · `KLEAL_USERS` (shared store path — must match matching-service's `KLEAL_USERS`).

## Security note
The panel can delete users, so it is protected by `ADMIN_TOKEN`. Because it sits behind the public
gateway, set a strong `ADMIN_TOKEN` and treat it as a secret. Test-mode tool.

## Run
`ADMIN_PORT=7077 ADMIN_TOKEN=... MATCH_URL=http://127.0.0.1:7074 python app.py`. stdlib only.
