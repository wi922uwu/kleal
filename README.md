# Kleal

Kleal is a social matching product for finding people and organizing online,
offline, and hybrid meetups. A user builds a profile and interests, creates an
intent, receives ranked candidates, sends invitations, agrees on meeting
details, and continues in a direct or group chat.

This repository snapshot reflects the version deployed on production on
22 August 2026. It supersedes the original single-file Python prototype that
still remains in the repository for historical reference.

## Current product

The production version consists of two source trees:

| Path | Purpose |
|---|---|
| `kleal-app/` | Expo 54 / React Native application using Expo Router. |
| `kleal-ms/` | Python services and deterministic matching core. The production host currently runs the matching service from this tree. |

The mobile application includes authentication and onboarding, profile and
interest editing, Buddy, intent creation, candidate results, direct and group
invitations, plans, messages, voice and video notes, safety and moderation,
post-meeting feedback, and online/offline/hybrid meeting flows.

## Data flow

```text
Expo Go / mobile client
        |
        v
https://aiopenware.com
        |
        +--> matching API on 127.0.0.1:7074
        +--> media and application API routes

Intent -> filtration/canonicalization -> deterministic matching
       -> candidate selection -> invitation -> plan -> chat -> feedback
```

The Expo client uses `https://aiopenware.com` as its default API base. Override
it for an isolated environment with `EXPO_PUBLIC_API`.

## Production server

These values describe the active environment at the time of this snapshot.

| Item | Value |
|---|---|
| Host | `157.230.52.87` |
| SSH | `ssh root@157.230.52.87` |
| Public API/domain | `https://aiopenware.com` |
| Expo Go URL | `exp://aiopenware.com:8081` |
| Expo source | `/opt/kleal/kleal-app` |
| Backend source | `/opt/kleal/kleal-ms` |
| Expo systemd unit | `kleal-expo.service` |
| Matching systemd unit | `kleal@matching.service` |
| Expo/Metro internal port | `8082` |
| Expo public nginx port | `8081` |
| Matching internal port | `7074` |

The matching API listens only on loopback. Nginx exposes the public application
and proxies Expo traffic from port `8081` to Metro on port `8082`.

Useful read-only checks:

```bash
systemctl status kleal-expo.service kleal@matching.service
ss -ltnp | grep -E ':7074|:8081|:8082'
curl http://127.0.0.1:7074/health
```

Production environment files are stored outside the repository under `/etc`.
Credentials, API keys, user accounts, matching state, photos, voice/video
uploads, email outbox files, logs, and backups are intentionally not committed.

## Run the Expo app

Requirements: Node.js, npm, and Expo Go compatible with Expo SDK 54.

```bash
cd kleal-app
npm ci
npx expo start
```

To use another backend:

```bash
EXPO_PUBLIC_API=https://your-api.example npx expo start
```

Open the QR code with Expo Go. The production QR encodes
`exp://aiopenware.com:8081` and is reachable outside the developer's local
network.

## Run the backend

The services are standard Python applications. From `kleal-ms/`:

```bash
python services/matching/app.py
```

The complete development stack can be managed with:

```bash
bash ops/run.sh all
bash ops/run.sh status
bash ops/run.sh stop
```

Default service ports are defined in `kleal-ms/shared/config.py`:

| Service | Port |
|---|---:|
| LLM | 7071 |
| Onboarding | 7072 |
| Profile | 7073 |
| Matching | 7074 |
| Buddy | 7075 |
| Filtration | 7076 |
| Admin | 7077 |
| Gateway | 7080 |

Service contracts are documented in `kleal-ms/shared/contracts.md`. Model keys
must remain in the LLM service environment and must never be committed.

## Verification

```bash
# Expo type check
cd kleal-app
npx tsc --noEmit

# Export bundles without publishing
npx expo export --platform android
npx expo export --platform ios

# Matching core tests
cd ../kleal-ms
for test in matching_core/tests/test_*.py; do python "$test" || exit 1; done
python -m compileall services shared matching_core
```

Some integration tests under `kleal-ms/tools/` expect running services and
runtime fixtures. Run them against an isolated environment, not production.

## Deployment and collaboration

Production is shared with another developer. Before changing any deployed
file:

1. Read the current file from `/opt/kleal` and record its SHA-256 hash.
2. Apply a narrow change against that current version.
3. Recheck the hash immediately before upload; stop if it changed.
4. Back up only the files being replaced.
5. Restart only the affected systemd unit and run health/smoke checks.
6. Never overwrite the whole production tree from a stale local checkout.

Git branches for Codex work use the `codex/` prefix. Production runtime data is
the source of test state, but source changes should be reviewed through pull
requests before they become the new repository baseline.

## Legacy prototype

The root-level `kleal_v2.py`, `kleal_profile.py`, and related launch scripts are
the previous browser prototype. They are not the source currently served to
Expo Go. New product work belongs in `kleal-app/` and `kleal-ms/`.
