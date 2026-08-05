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

# Эти экраны — UX-каркас, а не готовый вид

Поток O.01–O.04 (главная → разговор с Бадди → окно выбора → создание интента) собран как
**каркас поведения**. Вид поверх него будет натянут отдельно, поэтому всё сделано так, чтобы
переоформление не задевало логику:

- **Копия — в `src/*.ts`, не в экранах.** `src/buddy.ts`, `src/home.ts`, `src/onboarding.ts`,
  `src/profile.ts`, `src/intent.ts`. Ни одной строки текста прямо в JSX.
- **Оформление — одним блоком внизу файла**, после пометки `// ===== вид`. Логика выше него не
  зависит ни от одного размера и ни от одного цвета.
- **Своих цветов и отступов нет** — только токены из `src/theme.ts`. Перекрасить приложение
  значит поменять токены, а не искать литералы по экранам.
- **Правила живут на сервере, где им место.** Например «построитель интента не спрашивает про
  время, место и пол» — это `INTENT_BUILD_PROMPT` в `services/buddy/app.py`, а не проверка в
  клиенте: иначе клиент и сервер разошлись бы при первой же правке промпта.

Что при натягивании UI менять можно свободно: блоки стилей, иконки в `src/components/icons.tsx`,
разметку внутри экранов. Что трогать не надо: обращения к API (`src/api.ts`), разбор ответов
(`looksLikeIntent`, `activityOf`, `splitWhen`, `planWhere`) и переходы между экранами — они
проверены живьём на стенде.
