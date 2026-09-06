# Welcome Wave Gesture Follow-up

This report supersedes the gesture and panel-height claims in
`welcome-flow-sdk57-qa.md`. The physical-iPhone bug was real; the previous
helper-only checks and accessibility paging did not prove that dragging worked.

## Baseline and Isolation

Production was inspected read-only over SSH on 7 September 2026. The running
Expo unit uses `/opt/kleal/kleal-app`, SDK 57. Its git HEAD is `84a751c`, but its
dirty frontend contains the SDK upgrade, welcome, conversation, profile,
settings, API and map changes. The exact frontend snapshot was captured locally
as `b749573` before this fix. The snapshot also includes the six deployed wheel
PNG assets that the server's broad `*.png` ignore rule otherwise hides.

Worktree: `/Users/ivan/Projects/kleal-welcome-wave-gesture-sdk57`.
Branch: `codex/welcome-wave-gesture-sdk57-20260907`.
Only the subsequent feature commit is the welcome fix; do not deploy or merge
the snapshot wholesale. No backend or persistent account data changed.

The following server hashes were unchanged at initial and final read-only checks:

| File | SHA-256 |
| --- | --- |
| `app/intro.tsx` | `a2d6503b0a04314062f24c5e9015252a41a1a18989580b5c517cc603ebc659dd` |
| `src/welcome.ts` | `9c541008014d548f291e743331bbcc62ab4504f3fc506dd73e0093c9f4720cd9` |
| `src/onboarding.ts` | `a43cd8eede1f192f58e8fa976f7751c11c39d40d9c72b83dae8f8538453014a3` |
| `app/_layout.tsx` | `597abfa753afe8874fbd8547af037a3a9a368d8975139d1eb25adbbc599c84ac` |

## Cause and Change

React Native 0.86's `PanResponder` initializes `gestureState.y0` to zero. The
old `onMoveShouldSetPanResponderCapture` tested `g.y0 >= restY` before
`onResponderGrant` populated `y0`. Every upward pull was therefore rejected.
Additionally, RN resets `dx/dy` when the responder is granted, losing the first
part of a drag if those deltas are used for finger-follow.

The root now captures native initial page coordinates and owns a touch at start
when it is on the actual black SVG fill. A shared path constant and matching
cubic hit-test cover the crest, sides, lower body and CTA text without claiming
transparent white corners. Page-coordinate deltas preserve full finger travel
across responder grant. A window-offset measurement keeps hit-testing local.

- Vertical movement follows the finger; an upward release of at least 70pt
  completes the wave over the entire screen, then navigates to `/auth` once.
- Short, ambiguous, terminated or multi-touch gestures return the wave.
- Horizontal gestures still page, including backward from the black surface.
- A spring can be re-grabbed without snapping the wave away from the finger.
- Tap anywhere on black and the existing accessible Start button are alternatives.
- The existing focus/session tokens prevent double or stale navigation.
- All three pages reserve the same final-wave height, so paging no longer raises
  the white panel. Shared text measurement, large-text scrolling, fixed photo,
  and photo3 -> photo2 -> photo1 copy order remain intact.

## Verification

Commands run from `kleal-app/` using the bundled Node 24 runtime:

| Gate | Result |
| --- | --- |
| `node tools/welcome_flow_test.js` | PASS, 28 checks |
| `node tools/sdk57_migration_test.js` | PASS |
| `node node_modules/typescript/bin/tsc --noEmit` | PASS |
| `node node_modules/expo/bin/cli export --platform ios` | PASS |
| `node node_modules/expo/bin/cli export --platform android` | PASS |
| `git diff --check` | PASS |
| `node tools/regressions_test.js` | FAIL, identical baseline: three unrelated interest-normalization source assertions |
| Lint | No configured lint command |

The new tests instantiate **Intro's actual responder configuration**, not only
the axis helper. They deliver pre-grant `y0=0` and zeroed `dx/dy`, exercise all
five black start regions, exact finger distance, cancellation, second-touch
capture, horizontal grant, tap duplication, spring re-grab, window offsets,
Reduce Motion and a stable panel at all three indices.

The general runner stops at queued Buddy discoveries, proposal confirm/cancel,
and durable receipt assertions. These already failed before the patch and were
not modified or bypassed. The whole repository is not claimed green.

## Native QA

Own Expo Go 57.0.9 / iOS 26.5 devices:

- iPhone 17 Pro: `F7D545B3-32C1-47B1-A39A-4BEDDA91089B`.
- iPhone 13 mini: `959C9839-8BDB-48DF-B1A7-65EAE0DE5D53`.

Own Metro: `8175`, private dependency copy and private Metro cache.
API override: `http://127.0.0.1:17999` (unavailable intentionally, no production
requests/account writes). Other Metro ports `8157`/`8173` and other Simulators
were preserved. Initial shared-dependency cache and ExpoAsset cold-start errors
were resolved by an isolated dependency copy/cache and cold restart of only our
Expo Go; no application workaround or foreign restart was used.

Evidence directory: `/Users/ivan/.codex/qa-artifacts/kleal-welcome-wave-20260907/`.

| Scenario | Result | Evidence and observation |
| --- | --- | --- |
| 17 Pro RU page1 -> page2 -> page3 | PASS | `01-pro-first.png`, `03-pro-second.png`, `04-pro-third.png`: same white-panel top and fixed photo; changed only copy/indicator/wave |
| 17 Pro Start tap -> full-screen black -> auth | PASS | `05-pro-start-alternative.mp4`, `06-pro-auth.png`; native black-fill frame observed before auth |
| 13 mini normal size | PASS | `07-mini-first.png`, `12-mini-third-normal.png`; text and CTA do not overlap |
| 13 mini RU Accessibility Large | PASS for layout and AX paging | `08-mini-large-first.png`, `10-mini-large-second.png`, `11-mini-large-third.png`, `09-mini-large-pages.mp4`: stable top across all3, complete titles and reachable Start; long body uses the retained scroll viewport |
| 13 mini return from Large to normal | PASS | `12-mini-third-normal.png`, text reflows without clipping title |
| 13 mini EN page1 -> page2 -> page3, re-entry reset | PASS | `13-mini-en-first.png`, `14-mini-en-third.png`; copy order and same top observed; cold re-entry opens page1 |
| 13 mini EN accessibility Start -> auth | PASS | `15-mini-en-auth.png`; existing sign-in screen opens |
| Physical native drag / short pull / cancel | BLOCKED for manual evidence | CUA `drag` repeatedly returned `noWindowsAvailable`, including after raising the Simulator window; no injected native touchmove evidence obtained |
| Large-text manual vertical scrolling | BLOCKED for gesture evidence | Same coordinate-input limitation; existing ScrollView and complete AX text retained, not claimed manually scrolled |
| Android native / physical phone | NOT RUN | Android export passed, not a native-device gesture test |

`02-pro-native-drag.mp4` contains the failed coordinate-input attempts and AX
paging, **not a successful swipe demonstration**. The earlier
`wave-native-gesture.mp4` records setup errors, not passing QA. Do not use either
as release proof of finger-follow. AX actions and tap are explicitly separate.

## Phone Acceptance Still Required

On the local/review build, page to the third slide, then independently start an
upward pull at the crest, left/right black edges, black body and Start text.
Confirm the wave moves with the finger; release below 70pt and it springs back;
release above 70pt and it covers the status-bar region before exactly one auth
transition. Interrupt a long pull and check it returns. Swipe horizontally from
black to page2 and forward again, then repeat with larger text. The OS home
gesture at the extreme bottom remains owned by iOS. No physical swipe PASS is
claimed until this check is performed.

No commit was pushed, no production file was replaced, and no production
service was restarted. Before an authorized integration, recheck these server
hashes and apply only the welcome feature diff to the current runtime.

Loop: two focused iterations (gesture/layout fix, then second-touch cancellation
and responder-lifecycle coverage). Stopped with the best local state: targeted,
type and build gates pass, but physical-drag QA is unavailable and the general
runner retains its baseline failures. This is not a claim of full release QA.
