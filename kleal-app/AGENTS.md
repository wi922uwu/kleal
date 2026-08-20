# НАД ПРОЕКТОМ РАБОТАЮТ ДВОЕ. ПРОЧТИ ЭТО ПЕРВЫМ

Один человек ведёт Claude Code, другой — Codex. Оба читают этот файл (Codex — как `AGENTS.md`,
Claude — через `CLAUDE.md`, который его включает). Значит договорённости живут здесь, а не в голове.

## Что уже ломалось

Не гипотеза, а список случившегося:

- **Под стал местом слияния.** Ветка `kleal-app` месяцами не пушилась, и единственным местом, где
  встречался код обоих, был `/root/kleal-app` на поде. Слияние там происходит по правилу «чей `tar`
  приехал последним». 11 августа обнаружилось, что на поде нет `src/home.ts` и `CardStack.tsx`
  вовсе, а `home.tsx` и `api.ts` — чужих версий. Час ушёл на отладку кода, которого на устройстве
  не было.
- **`src/api.ts` правят оба.** В нём и голосовые ручки (`speech`, `mediaUrl`, `VoicePayload`), и
  групповые (`gplan*`, `gintent*`). Выкладка «своей» версии стирает чужую половину.
- **`services/matching/app.py` тоже правят оба.** На поде лежат резервные копии от обеих сторон за
  один день (`*.bak_voice_20260811_005729`, `*.bak_0811_0753`, `*.bak_gplan_20260811`) — это следы
  взаимных перезаписей.

## Правила

**1. Источник правды — git, а не под.** Под — рабочая копия для показа с телефона. Правки, которые
живут только там, считаются потерянными. Пушь ветку; забирай чужое через `git pull`, а не через
`scp` с пода.

**2. Общий файл не ВЫКЛАДЫВАЮТ — его СЛИВАЮТ.** Перед отправкой на под файла из списка ниже:
сверь `sha256sum` с подом, и если он чужой — забери его, наложи свою правку, потом отправляй.
Так `src/api.ts` пережил и голос, и группы 11 августа.

| общий файл | кто ещё в нём живёт |
|---|---|
| `kleal-app/src/api.ts` | голос: `speech`, `mediaUrl`, `VoicePayload`, `multipart` · группы: `group.*` |
| `kleal-app/app/home.tsx`, `src/home.ts` | лента приглашений (голос) · карусель групп |
| `kleal-ms/services/matching/app.py` | матчинг и группы · отдельные ручки голоса |
| `kleal-ms/services/gateway/app.py` | маршруты обеих сторон |

**3. Никогда не лить каталог целиком.** `ops/sync-to-pod.sh` требует явных имён файлов именно
поэтому — снести чужое можно только назвав чужой файл руками. Не обходи это `tar`ом или `rsync`.

**4. Зоны.** Внутри своей зоны можно не спрашивать; в чужую — только через владельца.

- **Голос:** `services/llm`, `services/gateway` (маршруты `/api/speech/*`), голосовой ввод в
  экранах, `home-invites`.
- **Группы и матчинг:** `services/matching`, `app/group.tsx`, `app/gplan.tsx`, `app/ginvite.tsx`,
  `src/groups.ts`, `src/gplan.ts`, `src/ginvites.ts`, `tools/g*_smoke.py`.

**5. Два контура, чтобы перезапуск не ронял чужую проверку.** Прод — порты 70xx (шлюз 7080), стенд
— 71xx (шлюз 7180); оба подняты. Перезапускаешь сервис — перезапускай СВОЙ контур. Приложение
переключается переменной, а не правкой кода:

```
EXPO_PUBLIC_API=https://<адрес-стенда> npx expo start
```

**6. Смоуки — часть правки, а не после неё.** `kleal-ms/tools/*_smoke.py` и
`kleal-app/tools/regressions_test.js` гоняются до выкладки. Они ловят ровно то, что в этом проекте
ломается молча: пустую выдачу вместо ошибки, разъехавшиеся копии, исчезнувшие ручки.

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
  use: `ImageManipulator.ImageManipulator.manipulate()` in `src/photo.ts`, and `mediaTypes:
  ['images']` in `app/chat.tsx` and `app/profile/index.tsx`. Verified present in both 54 and 57; do
  not assume for other versions. Note the doubled name: the module exports a CLASS `ImageManipulator`
  with a static `manipulate`, and there is no flat `ImageManipulator.manipulate`. The profile screen
  once had its own copy written the flat way — changing a photo silently did nothing until the two
  copies were merged into `src/photo.ts`. `tools/regressions_test.js` now fails if a copy comes back.

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

## Переходы: `navigate`, а не `push`

`router.push` кладёт НОВЫЙ экран всегда — даже если такой уже открыт. В приложении почти каждая
кнопка означает «перейти к X», а не «завести ещё один X», поэтому повторное нажатие копило стопку:
профиль можно было открыть двадцать раз подряд, и обратно надо было нажать «назад» столько же.
Особенно легко это было набрать с нижней панели — она видна на девяти экранах.

Правило: `router.navigate(...)` для перехода (он возвращает к уже открытому экрану и кладёт новый
только если такого с такими параметрами в стопке нет), `router.replace(...)` — когда текущий экран
не должен остаться в истории (редиректы, финал онбординга). `router.push` — только если ДВА
одинаковых экрана в стопке действительно нужны; такого места пока нет ни одного.

Нижняя панель вдобавок не реагирует на текущую вкладку: нажатие на неё — промах или привычка, и
открывать по нему нечего.

Что при натягивании UI менять можно свободно: блоки стилей, иконки в `src/components/icons.tsx`,
разметку внутри экранов. Что трогать не надо: обращения к API (`src/api.ts`), разбор ответов
(`looksLikeIntent`, `activityOf`, `splitWhen`, `planWhere`) и переходы между экранами — они
проверены живьём на стенде.


# Как открыть приложение на телефоне

Дев-сервер запускается в ТУННЕЛЬНОМ режиме, а не в LAN:

```
npx expo start --tunnel
```

Почему так. LAN-режим раздаёт телефону адрес вида `exp://192.168.1.3:8081` — он работает только
пока телефон и ноутбук в одной сети. Туннель даёт публичный адрес `exp://…exp.direct`, и телефон
подключается откуда угодно: из мобильного интернета, из другой квартиры, с чужого Wi-Fi. Для этого
в devDependencies лежит `@expo/ngrok` — без него `--tunnel` просто не стартует.

Что важно помнить:

- **Адрес меняется при каждом перезапуске** сервера. Он бесплатный и анонимный, постоянного имени у
  него нет. Новый адрес видно в выводе `expo start` и в манифесте: `curl -H "expo-platform: ios"
  http://127.0.0.1:8081/`.
- **Бекенд у приложения и так публичный** — `src/api.ts` смотрит на туннель стенда
  (`*.trycloudflare.com`), а не на localhost. Поэтому телефону не нужна связь с ноутбуком ни для
  чего, кроме самого бандла.
- **Туннель медленнее LAN.** Первая сборка бандла по туннелю занимает заметно дольше (7,5 МБ идут
  через туннель). Если телефон и ноутбук всё-таки в одной сети и нужна скорость — `npx expo start
  --lan` остаётся быстрым вариантом.

## Если ngrok не работает

Бесплатный анонимный ngrok регулярно отваливается: сначала «Tunnel connection has been closed»,
потом `--tunnel` вовсе перестаёт стартовать с «remote gone away». Это их сервис, а не проект.

Обход — собственный туннель через cloudflared (он уже стоит и используется для бекенда). Expo
поддерживает это официально: переменная `EXPO_PACKAGER_PROXY_URL` заставляет манифест сообщать
телефону публичный адрес вместо localhost.

```
cloudflared tunnel --url http://localhost:8081        # даёт https://…trycloudflare.com
EXPO_PACKAGER_PROXY_URL=https://…trycloudflare.com npx expo start --port 8081
```

Телефону при этом даётся `exp://…trycloudflare.com` (без https://). Проверять надо СНАРУЖИ, а не
по localhost:

```
curl -H "expo-platform: ios" https://…trycloudflare.com/          # debuggerHost должен быть публичным
```

Добавь `--protocol http2`: по умолчанию cloudflared идёт по QUIC (UDP 7844), и там, где UDP режут,
туннель поднимается и тут же рассыпается. В логе это видно как «control stream encountered a
failure while serving».

## Как выглядит умерший туннель

Живой процесс — ещё не живой туннель, и это главная ловушка: `ps` показывает cloudflared, а адрес
отвечает пустотой (`curl` → `000`). Смотреть надо В ЛОГ:

```
ERR failed to serve incoming request error="Unauthorized: Tunnel not found"
```

Значит Cloudflare удалил эфемерный туннель у себя, а клиент бесконечно перезапрашивает имя,
которого больше нет. Само не починится никогда — нужен новый процесс и НОВЫЙ адрес.

Перезапускать надо ОБА: expo тоже, потому что `EXPO_PACKAGER_PROXY_URL` читается один раз на
старте и старый адрес остаётся зашит в манифест. Порядок: убить cloudflared и expo → поднять
cloudflared → взять из лога новый адрес → запустить expo с ним → проверить манифест снаружи.

Бекенд-туннель стенда (`src/api.ts`) — ОТДЕЛЬНЫЙ процесс на поде и умирает независимо. Приложение
при живом expo и мёртвом бекенде открывается и молча не находит никого: проверять оба.
