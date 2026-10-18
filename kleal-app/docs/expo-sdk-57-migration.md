# Expo SDK 57 migration — local verification, 2026-09-06

Branch: `codex/expo-sdk-57-20260906`. No push, merge, deployment, production restart or
production data writes were performed. Intermediate SDK55/56 commits are migration
checkpoints, not independently deployable releases.

## Exact baseline and preserved work

The server `/opt/kleal` remains at git HEAD `84a751c0a54477619593f623add962691557f983`
with a dirty frontend. Git HEAD alone does not describe its deployed frontend. Before
implementation, SHA256 of all 165 tracked/untracked frontend paths matched local commit
`46b255e` (the already deployed age ruler). This branch starts from that commit.
Targeted production hashes were checked again before handoff and still matched; Expo
was active. Other worktrees and all production files were left unchanged.

The six wheel-art PNGs were deployed but globally gitignored. They are now tracked,
with SHA256 verified against production, so a clean clone can build the existing mindmap.
No artwork was regenerated. The missing assets were a baseline build issue.

Unchanged from `46b255e`: `src/api.ts`, all backend files, onboarding `app/chat.tsx`,
`src/components/AgeDial.tsx`, `src/age-ruler.ts`, and `assets/sounds/click.wav`.
Mindmap behavior, map-feed privacy filters, intent contracts and search logic are unchanged.

## Versions and necessary changes

- Expo `57.0.20`, React / React DOM `19.2.3`, React Native `0.86.3`, TypeScript `6.0.3`.
- Expo modules use the installed SDK's `bundledNativeModules.json` recommendations.
- Maps `1.27.2`, Reanimated `4.5.1`, Worklets `0.10.1`; the latter two are pinned to
  prevent npm selecting incompatible optional peers via Expo Router's UI dependencies.
- Added direct `expo-file-system` dependency for byte-readable native upload parts.
- `showsPointsOfInterest` → `showsPointsOfInterests` at both native map call sites.
- Removed `StyleSheet.absoluteFillObject` → `StyleSheet.absoluteFill` at 23 call sites
  across 18 files. Both are spreadable style objects; dimensions/appearance are unchanged.
- `usePreventRemove` imports in intent/results now come from
  `expo-router/react-navigation`, preserving the correct navigator context.
  Removed the unused direct `@react-navigation/native` dependency.
- New platform upload helper replaces legacy URI-only FormData parts in voice, video
  and group-report attachments. A native Expo File supplies the actual bytes while
  own JS multipart metadata preserves the existing filename and MIME. No recording
  is copied, renamed or deleted. Web keeps standard Blob handling.
- Expo's dependency migration added the `expo-status-bar` config plugin.
- Updated the three hardcoded SDK54 clipboard/camera/video version assertions to
  SDK57 values. No behavioral regression assertion was removed or weakened.
- No `runtimeVersion`/`sdkVersion` spoof, navigation-check bypass, global fetch fallback,
  global audio-mode change or custom native patch was used.

Official references:

- [SDK57 release](https://expo.dev/changelog/sdk-57)
- [SDK56 release](https://expo.dev/changelog/sdk-56)
- [SDK55 release](https://expo.dev/changelog/sdk-55)
- [Expo Router import migration](https://docs.expo.dev/router/migrate/sdk-55-to-56/)
- [SDK57 FileSystem](https://docs.expo.dev/versions/v57.0.0/sdk/filesystem/)
- [SDK57 Audio](https://docs.expo.dev/versions/v57.0.0/sdk/audio/)

## Verification

Final dependency state was tested after a clean `npm ci --no-audit --no-fund` using
Node `24.19.0`, npm `10.8.2`. Production's read-only observed Node `20.20.2` satisfies
the installed React Native/Metro engine range; npm there is also `10.8.2`.

| Gate | Result |
| --- | --- |
| `npm ci --no-audit --no-fund` | PASS; reproducible lockfile, 661 packages |
| `npx expo install --check` | PASS |
| `npx expo-doctor@latest` | PASS, 21/21 |
| `npx tsc --noEmit` | PASS |
| `node tools/sdk57_migration_test.js` | PASS, five groups, including actual installed Expo multipart serializer |
| `node tools/age_ruler_test.js` | PASS, 7/7 |
| `node tools/interest_keys_test.js` | PASS |
| `node tools/regressions_test.js` | FAIL: same three baseline interest-normalization assertions |
| `npx expo export --platform ios --platform android --output-dir ../.codex/sdk57-native-export` | PASS; iOS 1447 modules / 4.4 MB HBC, Android 1623 modules / 4.6 MB HBC, 54 assets |
| Native Expo Go `57.0.9`, iOS Simulator `26.5` | Core smoke PASS with limitations below |
| Android native / EAS production binary | NOT RUN; Android export is not a native runtime test |
| Backend tests | Not applicable: backend and API contracts unchanged |
| Lint | No configured lint command in baseline |

The baseline interest failures are: Buddy discoveries not queued for confirmation,
missing explicit proposal confirm/cancel UI, and confirmation receipts retained in
profile facts. The runner throws there, so it does not execute its remaining checks.
An uncommitted diagnostic wrapper retained failed status and continued past that
throw on both SDK54 and SDK57: both subsequently hit an existing `parseName` extraction
`SyntaxError: Unexpected token 'export'` at runner line 1260. Between these two baseline
blockers, the final SDK57 checks introduced no new failures. This is not a claim that
the full regression suite is green.

`npm audit` reports 14 moderate, 0 high and 0 critical vulnerabilities in transitive
dependencies (uuid/xcode/ngrok and query-string/decode-uri-component chains). Do not
apply `npm audit fix --force`: npm proposes downgrading Expo to 46 and Router to 5.
These findings remain a release-review item; Doctor does not audit vulnerabilities.

## Native evidence and limitations

Dedicated simulator: `QA Kleal SDK57`, iPhone 17 Pro, UDID
`F7BFBC68-64F3-4567-8B58-86832045112C`. Official client binary version `57.0.9` was
downloaded from Expo's published release URL and installed only on this new simulator.
Other simulators were not reinstalled or stopped.

Native QA used `EXPO_PUBLIC_API=http://127.0.0.1:7197`, a local mock with synthetic
identities, and Metro `8127`. No real sign-in, invitation, registration or search was
sent to production. A temporary dev-only harness seeded a synthetic profile and
exercised upload/audio; it was removed before the final clean install and export.

Observed:

- Expo Go menu reports Kleal SDK `57.0.0`; real app screens render without red screens.
- Age-step hydrates 30, central coral marker/long-short ticks and adjacent gender show.
  Accessibility increment changes 30 → 31; decrement restores 30. Gender selection
  enables Continue; Continue records `30, Мужской`; Back and re-entry retain age 30.
- `click.wav` native player reports `isLoaded:true`, duration `0.03653061224489796`,
  `didJustFinish:true`; selection haptic API resolves; audio resource is released.
- Real native multipart upload returns `{ok:true,bytes:6679}` from the isolated API,
  which checks `qa-click.wav`, `audio/wav` and the RIFF bytes. URI is not sent as file data.
- Offline/Hybrid map displays a stacked marker and two intents; marker → Offline 1:1
  detail → Back works. Online view shows ES with count 2; country cluster lists Online
  and Hybrid; Hybrid detail shows `Гибрид · Группа · 5` and `Испания` without address.
- Intent wizard: Online → 1:1/Group → Group size; increment and Back preserve usable
  navigation; switching to 1:1 remains reachable. Full matching/search/invite E2E was
  not performed against the mock.

Limits: drag/flick synthesis failed with computer-control `noWindowsAvailable`, so
smoothness/snap at high velocity is covered by existing logic tests, not claimed as
new manual verification. Physical sound audibility and haptic feel, background audio
behavior, Dynamic Type on a small phone and Android runtime still need device QA.
Apple Maps displayed its grid with working markers but did not load geographic tiles
in this simulator environment; tile rendering is not marked passed.

Local screenshots (outside git, under the worktree `.codex/evidence/`):

- `sdk57-native-upload.png`
- `sdk57-age-onboarding.png`
- `sdk57-age-resume.png`
- `sdk57-offline-intent.png`
- `sdk57-hybrid-group.png`

A stale Metro after installing/removing dependencies initially produced a misleading
`Cannot find native module 'ExpoAsset'`. Restarting only the local Metro with `--clear`
and reloading Expo Go resolved it. This is a reason to restart the approved Expo
service after the complete dependency migration, not to patch native-module lookup.

## Approval-gated deployment plan (NOT EXECUTED)

1. Obtain Daddy's explicit deployment approval and coordinate the frontend write window
   with all developers. Resolve current production HEAD, dirty files, dependency versions,
   service unit/working directory/ports, and hashes again. Stop if any target changed;
   semantically reconcile those changes first. Do not copy a checkout over production.
2. Review the complete binary diff from `46b255e` to this branch's final commit, including
   `.gitignore`, the six existing assets, source migration, manifests and tests. Generate
   an explicit file allowlist. Do not deploy intermediate commits. No backend targets.
3. Back up exact replaced files, permissions and hashes; record newly absent targets.
   Preserve the SDK54 manifests, exact lockfile and old Linux `node_modules` separately.
   Include the live dirty versions, not files reconstructed from production git HEAD.
4. In an isolated Linux staging directory, install the final lockfile with npm 10.8.2;
   run dependency check, Doctor, TypeScript, targeted tests and both exports. Confirm
   no QA harness/localhost API is baked into the intended server start environment.
   Do not run `npm ci` against the active production node_modules directory.
5. During the approved window, apply only the validated allowlisted patch and switch
   in the staged Linux dependencies. Restart only the resolved `kleal-expo` unit; no
   gateway, onboarding, matching, database or background worker restart is required.
   Keep the current public Expo URL/proxy configuration, unless separately approved.
6. Verify external iOS/Android manifests show SDK57 and real bundles/assets return 200,
   service remains active, and logs have no startup errors. Use Expo Go57 on the actual
   supported phones for age drag/flick/sound/haptics, navigation, files and both maps.
   Resolve the known baseline test and audit findings before calling the release fully
   validated. Native App Store/EAS builds require a separate build/signing verification.

## Rollback plan (NOT EXECUTED)

If startup/native smoke fails, restore the exact backup allowlist plus SDK54 manifests,
lockfile and old Linux node_modules as one coordinated operation. Remove only migration
files recorded as previously absent. Restart only `kleal-expo`; verify external SDK54
manifest, age-ruler/click asset and service health. Never `git reset --hard` a dirty server
or restore a whole source directory over another developer's work.

Expo Go57 cannot open an SDK54 rollback bundle. Keep an approved SDK54 test client or
development build available for rollback verification and communicate this client
compatibility constraint before the deployment window.

## Loop checkpoint

Five focused implementation iterations: preserve baseline assets; SDK55/maps; SDK56/
StyleSheet; SDK57/dependency peers; runtime upload/navigation migration and regression
version assertions. Checkpoint: `.codex/loop-state.json` in the worktree root. Full
loop success is not claimed because the baseline regression blockers and device-QA
limitations remain; do not fix unrelated interest logic as part of an SDK migration.
