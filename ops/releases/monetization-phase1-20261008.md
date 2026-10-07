# Monetization phase 1 — test deployment

Deployed on 2026-10-08 with user approval to aiopenware.com.

The runtime contains uncommitted collaborator changes not represented by the repository head. This release is stored as an exact narrow patch plus before/after SHA-256 manifest, not as a replacement repository snapshot. Do not copy an entire checkout over production.

11 files deployed; only 3 existing source files changed. Onboarding and Expo were restarted. Preview is explicitly test-only; real payments and product quota enforcement remain off.

Verification: backend 15/15, client 10/10, typecheck and mobile exports passed; public iOS and Android bundles contain the new screen/API. Physical-device QA remains manual. Five pre-existing interest test failures remain unchanged.

Production backup: `/var/backups/kleal/monetization-phase1-20261008-6048e742`. New service configuration: `/etc/systemd/system/kleal@onboarding.service.d/95-monetization-preview.conf`. Isolated test state: `/var/lib/kleal/monetization-preview-test/preview.sqlite3`.

Rollback: first verify the deployed hashes still match the release manifest. Restore the three existing files from backup; withdraw the eight additions and the new service drop-in into a recoverable backup, preserving any new collaborator edits and test DB. Reload systemd and restart only onboarding and Expo, then check public API/Expo availability.
