# Expo HAS CHANGED

Read the exact versioned docs at https://docs.expo.dev/versions/v54.0.0/ before writing any code.

## Why SDK 54 and not the latest

The project was scaffolded on SDK 57 (the current `latest`) and then deliberately moved **down** to
SDK 54, because Expo Go holds exactly one SDK and the phone we test on runs 54. This is a temporary
compromise for the ability to open the app by scanning a QR code, not a technical preference.

Consequences to keep in mind:

- **We are three SDKs behind on a project a few days old.** Upgrading back up is real work that has
  to happen before release, and it gets harder the longer it waits. It is a line in ROADMAP.md.
- **Expo Go ends the moment we add anything with custom native code** — maps, push notifications,
  any module outside the bundled set. At that point the answer is a development build (`eas.json`
  already has the profiles), and the reason for staying on 54 disappears with it.
- When bumping the SDK, check these two call sites first — both APIs moved recently and both are in
  use: `ImageManipulator.manipulate()` in `app/chat.tsx`, and `mediaTypes: ['images']` in the same
  file. Verified present in both 54 and 57; do not assume for other versions.
