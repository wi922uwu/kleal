# admin-service (:7077)

An **admin panel** to view / add / edit / delete the platform's users while the app runs in **test
mode**. It runs on its **own address** — a **separate cloudflared tunnel**, NOT behind the main app
gateway — so it is reachable only at its own URL. Users are stored in a shared JSON file (`KLEAL_USERS`)
that the **matching agent reads**, so admin edits directly change who gets matched. On first run it seeds
itself from the matching agent's demo pool (`GET /api/agent/pool`).

## UI
`GET /admin` (or `/`) → users table with search, add form, inline flag toggles, edit, delete, and
"Reset to demo pool". No login.

## API (no auth — protected by the separate/obscure URL)
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/admin/users` | list users |
| POST | `/api/admin/users` | add a user |
| POST | `/api/admin/user/<id>` | update (merge) a user |
| POST | `/api/admin/user/<id>/delete` | delete a user |
| POST | `/api/admin/reseed` | reset the store to the demo pool |

Every stored user is normalised to a complete, matching-safe record (`_norm_user`).

## Env
`ADMIN_PORT` (7077) · `MATCH_URL` (for seeding) · `KLEAL_USERS` (shared store path — must equal
matching-service's `KLEAL_USERS`).

## Security note
No token: the protection is the separate, hard-to-guess tunnel URL (test-mode tool). Keep that URL
private; anyone with it can add/delete users. Deployed via `build/deploy_admin.py` (its own tunnel,
does not touch the main app).

## Run
`ADMIN_PORT=7077 MATCH_URL=http://127.0.0.1:7074 python app.py`. stdlib only.
