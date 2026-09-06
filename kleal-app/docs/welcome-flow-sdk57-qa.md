# Welcome SDK57

Base: `d16df41`, Expo SDK57. The deployed `/opt/kleal` git HEAD is older than
its dirty runtime. Before editing and again before final verification, actual
`app/intro.tsx`, `app/_layout.tsx`, `src/onboarding.ts`, `src/state.ts`, and
`package.json` matched this base byte-for-byte. No production writes occurred.

## Cause and behavior

The old intro read `state.slide`, wrote each page change through `patch`, and
restored that number from `kleal.onboarding`. Its focus handler reset the wave
but not the page. The new pager owns ephemeral state and never writes account,
profile, onboarding step, or stored slide data. Focus resets to page zero;
completed signed-in accounts retain the existing Home gate.

Order is `searching -> primary -> match` (user photos 3, 2, 1). One preloaded,
fixed image remains behind one white panel. Text panes stay mounted across page
changes. Their shared progress drives the text translation, indicator, panel
height and final wave reveal. Text measurements share a viewport; large text
can scroll independently without triggering the wave.

The final wave uses an axis lock and a 70pt upward threshold. Short/terminated
pulls return with a spring; completion/tap/accessibility activation transitions
once to the existing `/auth` flow. Focus tokens reject stale callbacks after
blur or layout changes. Reduce Motion removes spatial completion/paging motion.

## Checks

- `node tools/welcome_flow_test.js`: 12 executable lifecycle, gesture, order and
  source integration checks passed.
- `node tools/sdk57_migration_test.js`: passed.
- TypeScript: passed.
- Expo export iOS and Android: passed.
- `git diff --check`: passed.
- General `tools/regressions_test.js`: blocked by the same three baseline
  interest-normalization assertions before the rest of that suite runs:
  queued Buddy discoveries, explicit proposal confirm/cancel, durable receipts.
  These unrelated checks were not weakened or bypassed.

## Native evidence

Own Simulator: `A5607ABD-F74A-4D82-A712-36E5E2704BBB`, iPhone 17 Pro,
iOS 26.5 / Expo Go 57, Metro `8171`. The test API was `127.0.0.1:17999`,
not production. Existing Simulator/Metro instances were preserved.

Evidence directory:
`/Users/ivan/.codex/qa-artifacts/kleal-welcome-sdk57-20260906/`

| Scenario | Result | Evidence / observation |
| --- | --- | --- |
| Fresh first page, RU copy | PASS | `01-first-ru.png` |
| Restored `slide=2` opens at first page | PASS | `06-restored-slide2-starts-first.png` |
| Account/profile/step preserved | PASS | `07-state-preserved.png`; fixture state remained unchanged |
| Completed account bypass | PASS | `08-completed-account-home.png`; local API unavailable by design |
| RU Accessibility Large | PASS | `05-first-large-ru.png`; reflow also checked live in both directions |
| EN page sequence and accessibility next/activate | PASS | `09-second-en.png`, `welcome-page-and-start-animation.mp4` |
| Start tap enters existing auth screen | PASS | `04-auth-after-start.png` |
| Re-enter intro after auth | PASS | first page, restored wave, responsive controls |
| Reduce Motion | PASS | `welcome-reduce-motion.mp4`; system preference enabled on own Simulator |
| Finger-tracking / cancelled physical drag | BLOCKED | CUA `drag` sent touch-start but no root touch-move; no native swipe PASS claimed |
| iPhone 13 mini / Accessibility Large | BLOCKED | Expo Go57 installed and bundle loaded on own `6BCF63B5-FA5D-42EA-BF89-73C302A06C1B`, then Mac lock prevented manual UI verification |

The gesture/cancellation/axis and stale-callback paths are covered by executable
tests, but a real-phone drag check remains necessary. The unsuccessful gesture
recording is `welcome-gestures.mp4`; it is diagnostic evidence, not a successful
swipe demonstration. Temporary touch logs and the local account fixture route
were removed from application source before final gates.

The app's language contract remains RU/EN. Spanish devices keep the existing
EN fallback; no global Spanish UI translation is introduced by this change.
No backend/API/schema or persisted account migration is needed.

Independent fork review could not run: its task ended with system error
`This request was blocked by our safety systems. Reason: Potentially unintended activity.`
No independent QA pass is claimed. The local implementation and completed tests
are available for review, but the two native limitations above remain open.
