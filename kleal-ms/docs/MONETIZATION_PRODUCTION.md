# Free / Plus без оплаты: локальный release candidate

17.10.2026. Источник требований — утверждённый
`spec-monetization-production-no-payments.md`. Этот документ описывает реализацию,
локальные доказательства и ещё НЕ пройденные release gates. Production не менялся;
push, remote commands, переключения flags и перезапуски сервисов не выполнялись.
Исторические `MONETIZATION_PHASE2A.md` и `PHASE2A_ACCEPTANCE_2026-10-14.md` описывают
донор, а не native/production-приёмку текущего кандидата.

## Baseline и перенос

- Worktree: `/Users/ivan/.codex/worktrees/monetization-prod-no-payments/kleal`.
- Ветка: `codex/monetization-prod-no-payments-20261016`.
- Baseline: `de4c8356c7791de56aa19ba6bc311352517d2ee4` — локальная фиксация
  read-only source snapshot, НЕ подтверждение текущего live HEAD.
- Донор: `9ba190a621d1e169256fbaab653e785c7aae2744` относительно
  `d633bb7541f97c69690203fe44c8c47f13002e76`, 59-file delta.
- SHA-256 `.codex/production-baseline-20261016/manifest.json`:
  `9248679111536901fd83b7abd2d7a64f88fd1c18216e103f8bed363cd7d743d8`.
  Это source inventory, НЕ backup БД/файлов/секретов/assets.

Перенос выполнен по delta, не заменой директорий. В пересечениях сохранены новая
навигация/scroll/transitions, новый двухвкладочный inbox/ActCard, новые UI primitives,
`whileThinking`, обработка group role и server `pick_request`. На это наложены
session isolation, canonical actions, quotas и закрытие/возобновление чатов 2A.
Inbox непрочитанных и preview исправлен на `personKey(name,id)`, включая тёзок.
`pick_request` закреплён реальным adapter-тестом: выбирается только отвеченный
получатель, остальные ответы на этот iid становятся `not_picked`, replay не
повторяет meaningful use, чужой actor не может выбрать ответ.

## Реализовано

- Независимые основания Plus: Preview, legacy paid expiry, manual grants.
  `plusExpiresAt` — максимальный действующий срок; `expiresAt` остаётся сроком
  Preview. Клиент RU/EN/ES показывает сроки и источники раздельно.
- `shared/monetization_admin.py`: закрытый ledger/audit/idempotency, точный
  `users.id`, finite UTC expiry, operator/reason/key; revoke только конкретного
  grant. Read-only view показывает всех users, даже без membership-строки.
- Tombstone удаления закрывает новые grants/commands до медленного cleanup;
  grant/revoke сериализованы с canonical writers. В staged/legacy-фазе grant
  отклоняется. Preview при manual grant/revoke не переписывается.
- Production import отделён от synthetic-инструментов. После независимого review
  их guards усилены общим `monetization_safety.py`: actual loopback peer и exact
  test DB/schema; synthetic CLI не допускают hostaddr/service/multihost overrides.
- Явный ownership store keys, aliases/lifecycle validation, сохранение анонимных
  и orphan-историй без создания им users/accounts/grants. Неоднозначная активная
  связь блокирует import. Исторический личный чат импортируется protected без
  выдуманного инициатора; explicit end/block сохраняет closed-состояние.
- Durable DB fence и общий advisory lock; старым writers запрещены insert,
  update, rename и delete matching-owned store keys. Иностранные keys не трогаются.
- Targeted source manifest, drift verification, private backup, изолированный
  restore rehearsal, staged activation, HTTP/bundle smoke primitives, откат через
  экспорт ТЕКУЩЕГО canonical state с сохранением новых записей/профилей/чужих keys.
  Старый DB snapshot никогда не восстанавливается поверх живых записей.

`ops/monetization_release.py` — host-local примитивы, не автоматический SSH deploy.
Проверка exact systemd inventory обязательна; процессы coordinator останавливает
и запускает отдельно. Инструмент не угадывает имена units и не меняет KYC admission.

## Локальные проверки

### Review loop 4: R43–R54, 17.10.2026

Локальная re-derivation завершена; независимый повтор и native-приёмка остаются
за координатором. KEEP R1–R42 восстановлен из единственного сохранённого patch
`8e0d0a762406153e7095d01098169a9eed4017a45720b8f3b17314eb675b07ad`.
Основной checkout, assets, реальный index и production не менялись. SHA-256
`git diff --cached --binary` остался
`988ede944c1b90deaa82e98de708fbdd8e583d8da3acf25ede09c22faa3dccfc`.

- R43/R44/R54: role quota использует общий web/native dialog. Проверены реальные
  callbacks при installed RNWeb Alert no-op, blur/unmount/account/proposal guards
  и прежний exact-origin recovery. У каждого deduplicated caller свой abort;
  оставшийся получает единственный receipt. Последний abort сохраняет uncertain
  key даже после позднего HTTP409; повторный cleanup идемпотентен. Отказ от
  приглашения по фактическому decision='decline' не требует Preview consent.
- R45/R46: Buddy сохраняет полный исходный matching payload и key до dispatch;
  изменение города/языка не меняет bytes pending retry. Новый explicit launch
  получает UUID. Готовый canonical receipt/conflict проверяется до parser/geocoder;
  подготовка нового запроса остаётся вне projection lock, commit повторно
  проверяет fingerprint и отдаёт актуальный safety-filtered receipt.
- R47: единственный live group controller на search resource; другая группа с
  тем же alias отклоняется атомарно. Terminal исторические aliases сохраняются,
  но не паузят и не передают ресурс живой replacement-группы. Free/Plus и оба
  legacy/canonical group model покрыты PG-проверками.
- R48/R49: failed foundation activation остаётся видимой после GET Free;
  MembershipClient возвращает различимый success/failure, ручной retry работает.
  Оба capacity-листа нейтральны RU/EN/ES, без ложного Plus upsell; Keep 5 и Cancel
  сохраняют create/edit drafts, остальные Plus entrypoints не изменены.
- R50/R53: malformed intent/ctx/override/profile отклоняются безопасным HTTP400
  до prepare во всех modes; валидный query-only plan работает. Off/shadow
  pause/resume возвращают phase2_not_enabled без публикации или Preview.
- R51/R52: транзакционные lock/statement deadlines 3/10 секунд и pool acquire
  5 секунд. SET LOCAL не меняет глобальные/default параметры БД; rollback,
  retryable503 и clock-after-lock сохранены. Operator savepoints не коммитят
  внешнюю транзакцию. Backup v2 включает last_value/is_called поддерживаемых
  sequences, checksum и точный rehearsal; v1 и tampering отклоняются до DDL.

| Проверка | Результат / лог |
|---|---|
| Full backend, все прежние 144 + 10 новых | 154 PASS, 49.663 s, 0 skipped — `/tmp/kleal-review4-backend.log` |
| Общий frontend runner | PASS — `/tmp/kleal-review4-client.log` |
| 17 scoped suites, прежние 16 сохранены | PASS — `/tmp/kleal-review4-scoped.log` |
| Усиленные subscriber/decline/Preview/capacity callbacks | PASS — `/tmp/kleal-review4-focused-client.log` |
| Role callbacks с web Alert no-op и native Alert семантикой | PASS — включены в общий runner для web и ios |
| TypeScript | PASS — `/tmp/kleal-review4-tsc.log` |
| Offline iOS + Android exports | PASS — `/tmp/kleal-review4-export.log`, output `/tmp/kleal-review4-export.gDv9cp/` |

Первый полный прогон выявил и исправил преждевременный commit operator decorator,
слишком короткий deadline для R6 и повторный cleanup uncertain abort. Старые
assertions не ослаблялись; итоговые прогоны выше зелёные. Новые backend проверки
используют только localhost PostgreSQL и временные test_<uuid> schemas.
Своих fixture/Metro dev servers не запускалось; export не является native PASS.
Физический Android, повтор изменённых native paths и все production/operator
gates по-прежнему отдельно. Push/deploy/live grants не выполнялись.

### Review loop 3: R29–R42, 17.10.2026

Локальный implementation candidate, ещё до независимого повторного review и
native проверки координатора. Положительные R1–R28 изменения восстановлены из
сохранённого code/test patch `f74469f30fbb36d8e8ef37cfd65e044ef860a0c873608eb66449cc0505438308`.
Index, approved assets, основной checkout и production не изменялись. Все статусы
«открыто» в исторических секциях ниже относятся к моменту того handoff, а не
отменяют последующие подтверждённые результаты.

- R29/R37: общий dialog сохраняет native Alert и даёт web явные кнопки через
  Modal (у установленного RN Web Alert пуст). Preview/quota promises завершаются
  при cancel, смене session и unmount; старые swap callbacks не работают после
  смены аккаунта даже до rerender, unmount или blur. Foundation учитывает
  previewEnabled/canStartPreview/state и сохраняет explicit consent/start;
  enforce meaningful-use не превращён в ручной старт. Покупки не включены.
- R30/R31/R32/R41: group ranking во всех трёх modes использует существующую
  canonical группу и её темы; swap только с собственным другим active blocker;
  cached receipt применяет прежний receiving policy helper без расширения его
  семантики; проверенный commandId/idem/fallback доходит до legacy writer receipt.
- R33: Buddy сохраняет canonical intent/searchId, retry key и pending contract,
  корректно передаёт structured HTTP 409/503 через реальный HTTPError. Pending
  возвращается как retryable 503, не успешная пустая выдача; raw exceptions скрыты.
- R34: storage read/write/corrupt failures не блокируют только block и group leave.
  Известный uncertain key сохраняется; публикация по-прежнему требует durable
  metadata. Сохранён flush barrier отмены: ожидание queued write не перезаписывает
  повреждённый disk state.
- R35/R36: реальные полные profile interest writes сериализованы, queued write
  читает свежий список и receipts; session/error/pre-registration guards сохранены.
  Replacement на уже существующий canonical отдельно проверяет confirmation;
  duplicate без receipt не удаляет old, поздняя валидная confirmation сохраняется.
- R38/R39/R40: строки архива используют lifecycle teaser RU/EN/ES, local archive
  не запрещает писать. Canonical adapter коммитит только whitelist terminal
  denial transition policy_revoked/group_full/withdrawn и его receipt; любые
  произвольные partial mutations при ok=false откатываются. Active pair можно
  завершить после archive/исчезновения legacy request, с одним событием и без
  потери истории; чужой peer отклоняется.
- R42: настоящий matching entrypoint subprocess выполняет pending launch и cleanup
  без drain вызова из теста; только disposable schema и synthetic media, referenced
  media сохраняется. Тестовый adapter подменяет только ranking/identity data,
  сохраняя actual libpq/localhost/schema guards. Native/production hooks не добавлены.

Доказательства: `/tmp/kleal-review3-final.GdVGHR/`.

| Проверка | Результат / лог |
|---|---|
| Full backend | 144 PASS, 41.895 s, 0 skipped — `backend.log` |
| Общий frontend runner | PASS — `regressions.log` |
| 16 scoped suites | PASS — `scoped.log` |
| Дополненный R29/R38 actual callbacks/render | PASS — `review3-frontend.log` |
| TypeScript | PASS — `tsc.log` |
| Offline iOS + Android export | PASS — `export.log`, output `export/` |
| Без startup call (runtime source mutation в subprocess) | ожидаемый FAIL: pending != ready, 12.280 s — `mutation-without-start.log` |
| Без drain_cleanup в реальном loop source | ожидаемый FAIL: launch ready, synthetic media осталась, 12.324 s — `mutation-without-cleanup.log` |

R29 caller завершение проверяется bounded Promise race, поэтому подвисший await
не может дать ложный PASS при выходе Node без активных handles. Оба R42 mutation
прогона завершились exit 1; обычный startup case в full backend — PASS. Production
исходники во время mutation probes не правились. Новый review3 backend содержит
10 реальных PG/HTTP/subprocess tests; предыдущие suites сохранены.

Команды из корня worktree (PATH/Python такие же, как ниже в R28):

```sh
KLEAL_MONETIZATION_TEST_DSN=postgresql://kleal_test:local_synthetic_only@127.0.0.1:55439/kleal_monetization_test_phase2a /Users/ivan/.codex/worktrees/monetization-phase2/kleal/.codex/phase2-venv/bin/python -m unittest discover -s kleal-ms/tests -p 'test_monetization*.py' -v
cd kleal-app
node tools/regressions_test.js
for test in identity session account_switch monetization monetization_actions monetization_acceptance monetization_components chat_lifecycle conversation_lifecycle role_quota_recovery group_recruitment recovery_navigation messages_polling monetization_review3 interest_confirmation interest_hierarchy; do node tools/${test}_test.js || exit; done
node node_modules/typescript/bin/tsc --noEmit
CI=1 EXPO_OFFLINE=1 node node_modules/expo/bin/cli export --platform ios --platform android --output-dir /tmp/kleal-review3-final.GdVGHR/export
```

Открыто: независимый repeat/review координатора, новый native повтор изменённых
R29–R42 сценариев, full Android и все production/operator gates. Это не live и не
native acceptance текущей версии. Подтверждённые координатором R27/R28 native
recovery/cancel/re-entry/foreground/account-switch результаты остаются историческим
PASS; этот implementation worker не повторял и не отменял их.

### R28: исправлена identity только synthetic native fixture, 17.10.2026

Актуальная спецификация фиксирует независимый native PASS координатора для R27:
A → Plus → C → end → Plus → Continue → тот же A, интерактивная кнопка, исчезнувший
blocker, HTTP 0 сообщений до Continue и ровно 1 `Native R27 exact return` в A / 0
в C после. После R28 координатор также подтвердил iOS cancel, tab-away/re-entry,
exactly-once доставку, foreground grant/expiry и B Plus → logout → C Free без
переноса прав/поисков/pending action. Это evidence spec и QA отчёта координатора,
не новый native прогон implementation worker.

R28 меняет только `tools/monetization_native_fixture.py`, новый
`tests/test_monetization_native_fixture.py` и этот отчёт; frontend/R27 не менялись.
Account-bound profile/session/enrollment и остальные mocked onboard/auth ответы
выбирают аккаунт через существующий `kleal_auth.owner_key` по bearer, hash и expiry
внутри patched synthetic accounts. Name/email body больше не выбирают identity;
нет fallback к A. Missing/unknown/expired bearer возвращает 401. OTP request/verify
отдельно выбирают явно указанный test login (a–d / `@example.test`), даже при чужом
attached bearer; missing/unknown login возвращает 400. Production auth/KYC не менялся.

Wire RED (`.codex/r28-wire-red-20261017.log`) подтвердил: synthetic-b + profile
`name=QA B` возвращал `id=a`. GREEN проверяет B с именем и пустым именем
(ensureMe-style), C, попытку выбрать A через body email, session B, missing/unknown/
expired bearer и explicit OTP B. Проверяются `id` и `owner_id`: реальный matching
wire serializer превращает `owner` в display name, не canonical ID. Новый unittest
запускает настоящий CLI `--smoke --port 0` в subprocess и отдельно проверяет в PG,
что ровно его UUID schema удалена. RED cleanup также прошёл. Существующие guards,
loopback bind и finally cleanup сохранены; родительские 7607/8097 не затронуты.

Финальные логи: `.codex/r28-final-backend-20261017.log` — **134 PASS**, 34.984 s,
0 skipped; `r28-final-wire-20261017.log` — wire PASS и cleanup; общий regressions,
13 scoped suites, TypeScript и оба exports — PASS в `r28-final-{regressions,scoped,
tsc,export}-20261017.log`. Export directory: `.codex/r28-final-export-20261017/`,
iOS 1908 / Android 2001 modules. `git diff --check` — PASS.

Точные команды из корня worktree:

```sh
export KLEAL_MONETIZATION_TEST_DSN=postgresql://kleal_test:local_synthetic_only@127.0.0.1:55439/kleal_monetization_test_phase2a
export PATH=/Users/ivan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH
/Users/ivan/.codex/worktrees/monetization-phase2/kleal/.codex/phase2-venv/bin/python -m unittest discover -s kleal-ms/tests -p test_monetization_native_fixture.py -v > .codex/r28-wire-green-20261017.log 2>&1
/Users/ivan/.codex/worktrees/monetization-phase2/kleal/.codex/phase2-venv/bin/python -m unittest discover -s kleal-ms/tests -p 'test_monetization*.py' -v > .codex/r28-final-backend-20261017.log 2>&1
/Users/ivan/.codex/worktrees/monetization-phase2/kleal/.codex/phase2-venv/bin/python kleal-ms/tools/monetization_native_fixture.py --smoke --port 0 > .codex/r28-final-wire-20261017.log 2>&1
cd kleal-app
node tools/regressions_test.js > ../.codex/r28-final-regressions-20261017.log 2>&1
for test in identity session account_switch monetization monetization_actions monetization_acceptance monetization_components chat_lifecycle conversation_lifecycle role_quota_recovery group_recruitment recovery_navigation messages_polling; do node tools/${test}_test.js || exit; done > ../.codex/r28-final-scoped-20261017.log 2>&1
node node_modules/typescript/bin/tsc --noEmit > ../.codex/r28-final-tsc-20261017.log 2>&1
CI=1 node node_modules/expo/bin/cli export --platform ios --platform android --output-dir ../.codex/r28-final-export-20261017 > ../.codex/r28-final-export-20261017.log 2>&1
git diff --check
```

Последующий independent check координатора и описанная выше R28 native матрица
пройдены. Исправление fixture не является изменением production auth. Full Android,
новый R29–R42 native повтор и production gates остаются открытыми;
index/assets/production implementation worker не менял.

### R27: отдельная идентичность recovery и точный возврат, 17.10.2026

Изменение поверх review2-кандидата, только working tree. Индекс, approved assets,
родительские native fixture/Metro и production не менялись. BMAD renderer повторно
не запускался. На момент этого handoff native recovery **FAIL** оставался открытым;
последующий результат координатора указан в R28 выше. Следующие JS/PG/export
результаты сами по себе не являются native PASS.

- В установленном Expo Router 57.0.19 воспроизведена старая семантика: общий
  `dangerouslySingular=true` переиспользует route key исходного чата A для C и
  переставляет существующий Plus в стеке. RED сохранён в
  `.codex/r27-navigation-red-20261017.log`. Это подтверждает потерю identity в JS,
  но не доказывает единственную причину наблюдённого native freeze.
- Только Plus/Conversation внутри конкретного recovery получают отдельный
  `recoveryId`. Все обычные screens сохраняют singular identity. Boundary и role
  recovery захватывают origin path/params; возврат C → Plus и Continue → origin
  используют `dismissTo` / настоящий `POP_TO`, без перестановки прежних native keys
  или слепого `back()`. Старый маршрут через messages переносит ту же identity.
- После обычного Back/gesture/tab-away/account switch pending action отменяется
  без retry. При tab-away пользователь остаётся на выбранной вкладке. При следующем
  явном recovery entry удаляются только overlays с уже retired recoveryId; текущий
  origin и все обычные routes сохраняют key/params/order. Это deletion-only RESET,
  а не глобальный сброс навигации. Отдельный тест повторяет 20 циклов с home/messages:
  только одна активная recovery-пара, ни одного автоматического retry.
- Новый harness загружает настоящие установленные StackClient/StackRouter и
  getSingularId, читает конфигурацию `_layout.tsx`; заглушены native rendering/import
  boundary, не алгоритм reducer. Возврат старой глобальной identity ломает тест.
  Реальные Boundary/Plus/Conversation/API callbacks проверяют A → Plus → C → end →
  тот же Plus с немедленным focus refresh → двойное нажатие Continue → тот же A:
  editor draft сохранён, commandId/text исходные, ровно один успешный delivery в A,
  ни одного в C. Back/gesture-equivalent POP/tab/account проверены отдельно.

Финальные локальные результаты и логи (корень worktree, `.codex/`):

| Проверка | Результат / лог |
| --- | --- |
| Полный backend, isolated PostgreSQL | 133 PASS, 32.730 s, 0 skipped; `r27-final-backend-20261017.log` |
| Общий regressions runner | PASS; `r27-final-regressions-20261017.log` |
| 13 scoped JS suites | PASS; `r27-final-scoped-20261017.log` |
| TypeScript | PASS; `r27-final-tsc-20261017.log` |
| Expo iOS / Android exports | PASS; `r27-final-export-20261017.log`, directory `r27-final-export-20261017/` |

Точные команды из корня worktree:

```sh
export KLEAL_MONETIZATION_TEST_DSN=postgresql://kleal_test:local_synthetic_only@127.0.0.1:55439/kleal_monetization_test_phase2a
export PATH=/Users/ivan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH
/Users/ivan/.codex/worktrees/monetization-phase2/kleal/.codex/phase2-venv/bin/python -m unittest discover -s kleal-ms/tests -p 'test_monetization*.py' -v > .codex/r27-final-backend-20261017.log 2>&1
cd kleal-app
node tools/regressions_test.js > ../.codex/r27-final-regressions-20261017.log 2>&1
for test in identity session account_switch monetization monetization_actions monetization_acceptance monetization_components chat_lifecycle conversation_lifecycle role_quota_recovery group_recruitment recovery_navigation messages_polling; do node tools/${test}_test.js || exit; done > ../.codex/r27-final-scoped-20261017.log 2>&1
node node_modules/typescript/bin/tsc --noEmit > ../.codex/r27-final-tsc-20261017.log 2>&1
CI=1 node node_modules/expo/bin/cli export --platform ios --platform android --output-dir ../.codex/r27-final-export-20261017 > ../.codex/r27-final-export-20261017.log 2>&1
git diff --check
```

Исторически на этом handoff были открыты независимое чтение/повтор координатора
и native переходы; последующие R27/R28 результаты указаны выше. Full Android flow
и production gates остаются открыты. Экспорт не заменяет ни физические жесты, ни
native screen lifecycle. Старый `r27-regressions-20261017.log` сохраняет FAIL от fixture
без `dismissTo`; заглушка дополнена новым API, утверждения поведения сохранены.

### Review loop 2: повторная реализация R12–R26, 17.10.2026

Текущая реализация проверена локально; native/production PASS не заявляется.
Сохранённый review1-кандидат восстановлен только в working tree как KEEP/regression
foundation; ошибочные границы ниже переработаны. Index и approved assets не менялись.
Ни BMAD renderer, ни native управление, ни commit/push/deploy не повторялись.

- R12–R14: `rank_group` ранжирует существующую canonical группу по её ID и
  capacity, не создавая вторую публикацию; настоящий `inviteMore` использует этот
  маршрут. Удаление standalone intent оставляет terminal tombstone и command/alias
  fence, блокирует старый replay и новый resume, минимизирует старые результаты;
  живой group alias сохраняется. Ошибки read-snapshot/схемы/соединения возвращают
  структурированный JSON 503, а не traceback/HTML.
- R15: unresolved retry metadata больше не вытесняется сроком 7 дней или сотней
  следующих операций. Проверены потеря ответа, 125 последующих неизвестных исходов,
  8 дней, reload и тот же commandId без второго server-side effect.
- R16 уточняет прежнее R9: частичный список peers НЕ доказывает уникальность имени.
  Runtime caller передаёт только наблюдения, без `saved_peer_id` proof, поэтому
  старые name/th:name marks сохранены **unresolved**, но автоматически не применены
  к ID. Настоящий сохранённый исходный ID допускается отдельным proof-контрактом;
  тест отличает preserved unresolved от applied proven binding, проверяет позднего
  тёзку, отмену производной связи и account isolation. Невосстановимый исходный ID
  не выдумывается. Старое утверждение о миграции по однозначному текущему списку
  ниже — история review1, не поведение текущего кандидата.
- R17–R19: member-only legacy `_groups` vacancy видна в status/Plus и имеет
  отдельный quota-aware recover action, без перехода в modern room. Blocker содержит
  точную собственную peer destination независимо от последних сообщений/50 threads;
  Plus ведёт к нужному чату, исходная отправка остаётся явной. Invitation-cap sheet
  и shared copy RU/EN/ES честно описывают одинаковый Free/Plus cap; Plus upsell и
  старое обещание «€6.99 / unlimited invites» удалены. Реальные callbacks проверены.
- R20: batch resource/account/manual/deletion projection, batch document save и
  skipping unchanged reconciliation убрали per-owner/per-resource SQL под lock.
  Для 4/100/890 owners, включая owner documents: snapshot 7/7/7 SQL, canonical
  writer 21/21/21 SQL; snapshot 3.23/2.66/8.90 ms. Это O(1) число SQL, не O(1)
  объём/CPU и не production-capacity обещание. Barrier/rollback/ranking/expiry
  regressions сохранены. Bounded 2-worker load использует настоящие
  `SessionProjection`, canonical adapter, PostgreSQL и safety callback slots.
- R21–R23: smoke поддерживает явные GET/POST, ожидаемый status и JSON body;
  POST ограничен denial probes, credentials только из env, body ≤64 KiB. Реальный
  HTTP handler проверен на quota/KYC denial без записей. Synthetic snapshot v2
  включает users, deletions, manual grants/admin commands/admin audit и точные
  sequence positions (включая gaps); checksum/restore/replay/new grant проверены.
  Неполный v1 не принимается. Restore остаётся только в пустой isolated test schema.
- R24–R26: Plus обновляется раз в 60 s только в focus/foreground, сразу после
  возвращения и с session guard. Реальная Boundary проверена для active/expired
  notices, точного ack, повторного открытия, смены аккаунта и убиваемой condition
  mutation. Missing/malformed/foreign lifecycle закрывает text/voice/video composer
  даже после прежнего valid ответа; история остаётся, повторная проверка доступна.

Результаты текущей версии:

| Проверка | Результат / лог в `.codex/` |
| --- | --- |
| Полный backend, настоящий isolated PostgreSQL | 133 PASS, 32.116 s, 0 skipped; `review2-backend-final-20261017.log` |
| Полный regressions runner | PASS; `review2-regressions-final-20261017.log` |
| 11 scoped JS suites | PASS; `review2-scoped-20261017.log` |
| TypeScript | PASS; `review2-tsc-20261017.log` |
| Expo iOS / Android export | PASS, 1802 / 2001 modules; `review2-export-20261017.log`, directory `review2-export-20261017/` |
| Standalone bounded load, 2 workers × 2 owners/cohort × 2 attempts | PASS; `review2-load-20261017.json`, 0 unexpected errors, cleanup confirmed |

В load: 8 contended commands, 2 ожидаемых `search_quota`, p50/p95 56.46/67.249 ms,
projection-lock p95 16.024 ms; replay equality, один Preview grant, точные 14 дней,
durable pending/recovery и пустой outbox проверены. Это synthetic identity/ranking,
не HTTP/model/native benchmark. Локальные схемы создавались и удалялись только в
`127.0.0.1:55439/kleal_monetization_test_phase2a`; public/live не использовались.

Первый final regressions log (`review2-regressions-20261017.log`) сохраняет FAIL:
старый fixture задавал closed+active sessionId. Fixture приведён к реальному wire
closed+null; старое сочетание добавлено отдельным invalid-case. Unread assertion не
ослаблена. Только повторный `review2-regressions-final-20261017.log` является PASS.

Точные команды (из корня worktree; абсолютные runtime paths не меняют shell profile):

```sh
export KLEAL_MONETIZATION_TEST_DSN=postgresql://kleal_test:local_synthetic_only@127.0.0.1:55439/kleal_monetization_test_phase2a
export PATH=/Users/ivan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH
/Users/ivan/.codex/worktrees/monetization-phase2/kleal/.codex/phase2-venv/bin/python -m unittest discover -s kleal-ms/tests -p 'test_monetization*.py' -v > .codex/review2-backend-final-20261017.log 2>&1
/Users/ivan/.codex/worktrees/monetization-phase2/kleal/.codex/phase2-venv/bin/python kleal-ms/tools/monetization_load.py --workers 2 --owners 2 --attempts 2 > .codex/review2-load-20261017.json 2> .codex/review2-load-20261017.stderr.log
cd kleal-app
node tools/regressions_test.js > ../.codex/review2-regressions-final-20261017.log 2>&1
for test in identity session account_switch monetization monetization_actions monetization_acceptance monetization_components chat_lifecycle conversation_lifecycle role_quota_recovery group_recruitment; do node tools/${test}_test.js || exit; done > ../.codex/review2-scoped-20261017.log 2>&1
node node_modules/typescript/bin/tsc --noEmit > ../.codex/review2-tsc-20261017.log 2>&1
CI=1 node node_modules/expo/bin/cli export --platform ios --platform android --output-dir ../.codex/review2-export-20261017 > ../.codex/review2-export-20261017.log 2>&1
git diff --check
```

Открыто: independent review/repeat координатора; native acceptance этой версии
(координатор сообщил блокировку экраном Mac); fresh production drift/inventory,
private full backup/restore rehearsal, утверждённый smoke inventory, deploy/import/
activation и rollback gates. Старые native записи и source manifests ниже не
подтверждают текущую версию. Safe unresolved name-only prefs требуют настоящего
исходного ID, которого нынешний runtime не предоставляет.

### Review loop 1: повторная реализация R1–R11, 17.10.2026

Это новая локальная версия поверх сохранённого кандидата. Прежний native PASS
ниже относится к прежней версии; изменённые recovery/polling/Plus пути требуют
повторной native-приёмки координатором. Commit/push/deploy/remote/native control
в этом implementation handoff не выполнялись. Frozen intent, лимиты, правила
Preview, ranking quality и KYC admission не менялись.

- R1: return-action переживает только явные Plus → messages → conversation →
  Plus переходы. Есть видимая кнопка возврата; закрытие другого чата не повторяет
  исходное сообщение. Обычный blur/Back/gesture/tab-away/cancel/account change
  отменяет recovery. Реальные Plus/messages/conversation callbacks исполнены
  синтетическим component harness, это не доказательство физических жестов.
- R2: новое начало poll больше не отменяет ещё не применённый старый ответ.
  Сравнивается latest-applied generation; conversation также проверяет serverTime.
  Keyed session/pair unmount и session guard отбрасывают чужую позднюю доставку.
  Реальный usePolling проверен с >15-секундным перекрытием и AppState
  background/foreground; conversation — с несколькими отложенными ответами.
- R3: resume берёт canonical group/source alias, включая legacy `_groups` без
  `payload.intent`, сохраняет owner/min/max capacity. Исторический terminal/locked
  state ставит pause только при переходе. Настоящий ranker/parser-compatible
  preparation проверен для group resume, не только stub render_search.
- R4: присутствующие commandId/idem валидируются до prepare для всех search
  routes, включая legacy публикации; command keys строго string/nonempty/≤160.
  Оба alias проверяются, даже если второй валиден. Отсутствующий ключ старого
  search клиента получает стабильный digest; invalid key не создаёт outbox/job.
- R5: request-wide `_STORE_LOCK` удалён (включая off). Canonical adapters держат
  короткую транзакцию над private thread-local SESSION projection, публикуют её
  только после commit. HTTP читает consistent read-only MVCC snapshot без advisory
  lock. Worker ranking выполняется вне DB/in-process locks на отдельной проекции
  и закреплённом pool snapshot. Geocoder preparation вынесен до canonical writer.
  Перед записью/повтором receipt заново применяются актуальные block/deletion и
  существующие `_policy_decision` gates; REVIEW штампуется `_apply_policy` и не
  разрешает outreach. Это не повторный scoring и не обещание неизменного профиля
  после отправки ответа. Legacy name-only cards связаны с canonical IDs приватным
  `_candidate_refs` receipt metadata, не новым wire-полем; неоднозначные bindings
  не угадываются. Generated room alternative/fallback и существующий pilot-disabled
  people fallback сохраняют контракт. Off/shadow ranking parity, deepcopy,
  JSON serialization и db.save_store dictionary consumers проверены.
- R6: clock_timestamp читается после advisory/row lock wait; barrier tests
  подтверждают post-expiry отказ и Preview start после освобождения lock.
- R7: чужой receipt с удалённым участником заменяется redacted response, но
  key/payload hash fence остаётся, replay не выполняет side effect снова.
  Используются точные structural identity fields, включая profile_view.user_id,
  direct candidate id и private canonical binding; произвольные тексты, display
  names и nested media IDs не являются совпадением. Дополнительно найдена связанная
  причина: gi_approve/gi_remove ошибочно выбирали recipient `who` как actor раньше
  `frm`. Приоритет actor исправлен и воспроизведён в approval→purge→replay тесте.
- R8: inbox/outbox/internal sweeps сохраняют atomic reconciliation без нового
  бессрочного полного receipt на каждый poll; explicit command replay сохранён.
- R9: muted/archived/left name/th:name мигрируют в ID только по однозначным данным
  текущего аккаунта. Ambiguous marks сохраняются; remembered ambiguity не позволяет
  привязать их к случайному тёзке при следующем неполном ответе. Проверены relogin,
  logout/new account и повторная миграция.
- R10: duplicate durable не заменяет uncertainty-aware cancel. Cancel во время
  dispatch, даже с поздним successful receipt, сохраняет прежний retry key до
  явного повтора; synthetic server подтверждает одну publication.
- R11: новый executable harness загружает настоящие Boundary/Plus/API/actions:
  Preview Cancel — zero POST и очищенная metadata; Continue — один POST; quota
  confirmation Cancel — без mutation; swap — точный blockerId; success — refresh
  карточек. In-memory mutations reject→resolve и blockerId→search.id действительно
  ломают соответствующие сценарии. Component suite включён в regressions runner.

Негативное доказательство: первоначальные новые backend regressions воспроизвели
invalid key/prepare, missing group payload, repeated terminal pause, dirty SESSION,
receipt growth, меняющийся ranking snapshot и foreign receipt/actor проблемы.
Исправления проверены после RED. Прежние tier/ranking ожидания не ослаблялись.

Локальные результаты review1:

| Проверка | Результат |
| --- | --- |
| `python -m unittest discover -s kleal-ms/tests -p 'test_monetization*.py' -v` | 124 PASS, 27.354 s, 0 skipped; реальный isolated PostgreSQL |
| Новые `test_monetization_review1.py` | 14 тестов: barriers, group/ranker, safety, purge, keys, passive log, mapping compatibility |
| `node tools/regressions_test.js` | PASS: 648 прежних checks плюс executable acceptance/components/messages suites |
| `node tools/monetization_acceptance_test.js` | 9 PASS, включая duplicate→quota→resume→cancel→receipt→retry |
| `node tools/identity_test.js` | 25 PASS |
| `node tools/monetization_test.js` | 11 PASS |
| actions / role recovery / chat lifecycle / conversation lifecycle | PASS |
| `node node_modules/typescript/bin/tsc --noEmit` | PASS |
| Expo public iOS / Android export | PASS: 1920 / 2001 modules |
| `git diff --check` | PASS |

Логи текущего цикла: `.codex/review1-backend-final-20261017.log`,
`.codex/review1-regressions-20261017.log`,
`.codex/review1-export-{ios,android}-20261017.log`.
Exports находятся в `.codex/review1-export-{ios,android}-20261017/`.
Локальный PG — только `127.0.0.1:55439/kleal_monetization_test_phase2a`,
изолированные `test_<uuid>` schemas; public/live не использовались.

Осталось: независимый повторный review; повтор затронутых native сценариев;
операторские fresh production drift/manifest/backup/restore/deploy/import/activation
gates. Старые source manifests не описывают эту версию. Exports и synthetic tests
не являются production-ready/live/native PASS.

### Актуализация assets и сборок, 17.10.2026

После отдельного разрешения пользователя read-only скачаны ровно 16 недостающих
production assets (13 изображений, 3 шрифта). SHA-256 до/после передачи и локальные
SHA совпали; `.codex/approved-assets-20261017.json` фиксирует пути/размеры/hashes.
Production файлы, настройки, БД и сервисы не менялись. Assets добавлены в index
точными путями; общий `.gitignore` не менялся. Финальный кандидат — 86 staged files.

iOS export — PASS (1920 modules), Android export — PASS (2001 modules).
Координатор повторил regressions (648 PASS), TypeScript и diff check — PASS.
Логи: `.codex/verified-{ios,android}-export-20261017.log`,
`.codex/parent-assets-regressions-20261017.log`, `.codex/parent-assets-tsc-20261017.log`.
Ниже сохранена история исходного handoff с ранее отсутствовавшими assets.

Native QA остаётся BLOCKED, не PASS: CUA/Device Hub возвращает
`timeoutReached (-10005)` после действия и повторного подключения/reset.
Отдельный simulator `QA Free Plus 20261017` (BE83C80B-08F0-40EC-8DD2-58717713BB4F)
создан, Expo Go установлен, но полный UI flow не пройден. Свои Metro/fixture
остановлены штатно, synthetic schema удалена; новый simulator выключен без удаления,
старое QA-устройство не выключалось. Для следующей попытки использовать новые
свободные порты (например 7607/8097): старый QA-клиент продолжал обращаться к 7599.
Эта блокировка устранена перезапуском Device Hub. Актуальный native результат ниже;
формальный BMAD review и операторская выкладка остаются открытыми.

### Native iOS: PASS после восстановления Device Hub

17.10.2026 координатор прошёл CUA UI на QA Free Plus 20261017, iPhone 17 Pro,
iOS 26.5 / Expo Go SDK57. Текущий release bundle, fixture 7607 / Metro 8097,
изолированная schema `test_af8eaf9abdd04840a043a67f2476b029`.
Для IPv4 loopback Metro запущен с Node `--dns-result-order=ipv4first`: без этого
localhost слушал только ::1, а manifest ссылался на 127.0.0.1. Код не менялся.

PASS: Free-экран без покупки; manual Plus с отдельным сроком/источником;
expiry и автоматический refresh после background; Free resume refusal;
подтверждённая атомарная замена поиска; Plus resume нескольких поисков;
keeper при expiry; отсутствие auto-resume после нового Plus; logout A → B без
чужих прав/поисков. Offline «Не сейчас» не отправляет отклик; paused target
показывает контролируемый отказ, после resume повтор успешно отправлен.
Hybrid/online detail отображает receipt. Реальный outbox содержит правильные
target ссылки; reply B не тратит слоты и не запускает Preview. Существующая
семантика одного pending invitation на пару сохранена: следующий target той же
пары атомарно заменяет предыдущий, не создаёт вторую pending запись.

Auth/KYC/users/ranking остаются synthetic. Это НЕ live admission, production,
physical-device или полный Android PASS. Полный отчёт координатора:
`_bmad-output/implementation-artifacts/monetization-production-local-qa-20261017.md`
в основном checkout. Формальное ревью и fresh production gates ещё обязательны.

### Исправления после независимого ревью, 17.10.2026

Сначала новыми тестами воспроизведены оба дефекта (RED), затем внесены узкие
backend-исправления; клиентские файлы в этом цикле не изменялись.

- `below_quorum`, `planning`, `planned` явно включены в разрешённый production
  lifecycle. По реальной state machine это живые состояния набора: пауза или
  подтверждение встречи не закрывают recruitment. Search остаётся active и
  занимает квоту; новый участник после accept ждёт approval. Unknown lifecycle
  по-прежнему блокирует import, в том числе у anon. Тесты проверяют registered
  и anon группы, общий intent/group alias, старые plans/invites и downgrade без
  изменения существующих договорённостей при import→activate→rollback.
- Проверяется настоящий порядок onboarding: сначала committed `begin_delete`,
  затем matching purge. Только отдельный внутренний deletion path пропускает
  обычный pause удаляемого intent до передачи shared resource; `account()` и
  обычные entitlement/writer проверки не ослаблены. Допустимому организатору
  передаётся active resource с его quota check, при занятой квоте сохраняется
  paused recovery. Также запрещено назначать уже удаляемого наследника.
- Удаляются obsolete aliases удалённых собственных intents; живой group alias
  сохраняется. Payload переданного ресурса заменяется surviving group projection,
  а не хранит приватный удалённый intent. Повторный purge и unrelated-user writes
  проверены, включая rollback failed purge и post-commit media cleanup.

Политика данных в новом manual/admin ledger при удалении: `begin_delete` в одной
транзакции стирает manual grants, admin audit и cached admin commands ТОЛЬКО
точного subject. В последнем случае ownership берётся из server-generated
`result.status.ownerId`, не из имени или substring. Другие grant/audit/command
строки не меняются. Operator/reason/expiry/history удалённого subject не
сохраняются. Остаётся только `monetization_deletions(owner_id, started)` как
durable запрет late/replayed grants и восстановления прав; автоматического TTL
у него нет. Existing third-party reports/group records сохраняются по прежнему
контракту удаления, а не стираются глобально.

Целевой suite после lifecycle/delete-фикса: 16 PASS. Полный backend этого этапа:
105 PASS, 19.294 s, включая test удаляемого наследника.
Логи review-цикла: `.codex/monetization-production-review-fixes-backend.log` и
`.codex/monetization-production-review-fixes-backend-final.log`.
Старый local source manifest предшествует этим исправлениям и не должен
использоваться как hash текущего кандидата; перед release создать новый manifest.

### Release-safety после review

До исправления новыми regression-тестами подтверждены network-peer и metadata
дефекты. После исправления production/safety suite: 13 PASS, включая настоящий
subprocess CLI и PostgreSQL import в существующую изолированную schema.

- До подключения synthetic/rehearsal CLI отвергают `hostaddr`, `service`,
  `servicefile`, multi-host/port и `PGHOSTADDR`/`PGSERVICE`/`PGSERVICEFILE` overrides.
  После подключения и до записи проверяются actual `conn.info.hostaddr`
  (libpq `PQhostaddr`), explicit loopback host, test DB и `test_*` schema.
  Docker через `127.0.0.1:55439` допустим: SQL `inet_server_addr()` внутри
  контейнера `172.17.0.2` не заменяет фактический client endpoint.
- Synthetic migrate теперь требует `--schema test_fixture` при `--apply`.
  Schema должна уже существовать; CLI её не создаёт, не выбирает `public`
  и не расширяет production import. Тест проверяет missing/invalid/nonexistent
  schema и успешную CLI-команду с существующей schema. Точный пример — в
  `MONETIZATION_PHASE2A.md`, раздел Flags, migration и rollback.
- Source manifest v2 содержит `beforeMetadata`, `afterMetadata`, `installMetadata`
  с mode/uid/gid. Existing files сохраняют исходную metadata, новые — явно
  проверенную metadata candidate. Backup bytes хранятся с mode 0600 в private
  backup directory; исходные mode/uid/gid сохраняются в release-manifest.json.
  Старый v1 manifest больше не принимается.
- Install сначала готовит ВСЕ temp files и проверяет chown/chmod, затем повторно
  проверяет contents+metadata перед каждой atomic replacement. Невозможность
  сохранить ownership/permissions останавливает работу до первой замены.
  Restore использует исходную metadata manifest, не текущую metadata target;
  любое постороннее изменение bytes или mode/uid/gid останавливает замену.
- Interrupted-install regression действительно прерывает работу после первой
  замены до второй — в обоих порядках existing-first/new-first. Restore возвращает
  старые bytes+metadata, удаляет только добавленные manifest files, сохраняет
  unrelated файл и отказывается перезаписывать concurrent edit.

Важно: локальный test manifest и live release manifest — разные artifacts.
У snapshot на Mac uid/gid локальные, они НЕ являются production ownership.
Live manifest создаётся на deployment host из свежего `stat` LIVE_ROOT после
source-hash agreement и узкого reconciliation. Candidate на том же host должен
иметь согласованную metadata новых файлов. Затем `verify` проверяет живые
bytes+mode/uid/gid. Нельзя переносить Mac ownership в live manifest или обходить
проверку ради установки. В этом review-цикле remote/live stat НЕ выполнялся.

Повторный backend до CLI ergonomics: 109 PASS, 19.408 s;
`.codex/monetization-production-safety-backend.log`. Loopback fixture `--smoke`
PASS; это wire-only, НЕ native UI PASS. Bounded load `--workers 2 --owners 2
--attempts 2`: invariants PASS, unexpectedErrors=0, cleanupConfirmed=true;
`.codex/monetization-production-safety-load.json`. Итоговый полный backend после
CLI ergonomics: 110 PASS, 19.917 s, без skipped;
`.codex/monetization-production-safety-final.log`.

### Исходный handoff реализации, 16.10.2026

| Проверка | Результат текущего кандидата |
| --- | --- |
| Полный backend unittest + реальный isolated PG | PASS: 99 tests, 18.545 s |
| Production import → activate → новые writes → export rollback | PASS внутри production suite |
| Private backup → restore только в пустой test schema → checksum | PASS внутри production suite |
| Manual mixed sources, конкретный revoke, idempotency, deletion, downgrade | PASS внутри admin suite |
| Общий client regression runner | PASS: 648 ok, 0 FAIL |
| Identity | PASS: 25 ok, 0 FAIL |
| Monetization client | PASS: 11 tests; RU/EN/ES, expiry, session switch |
| Actions, chat/conversation lifecycle, map reply, acceptance, role recovery | PASS; также исполняются общим regression runner |
| TypeScript | PASS, exit 0 |
| Native fixture self-smoke | PASS только loopback HTTP/PG; UI НЕ проверен |
| Expo iOS/Android export | BLOCKED: baseline missing binary assets, см. ниже |
| iOS/Expo Go текущего кандидата | НЕ выполнен; blocked bundle, затем отдельная приёмка координатора |
| Полный Android flow | Отложен пользователем; export его не заменяет |
| Независимое ревью / fresh live сверка / deploy / live smoke | НЕ выполнены; release gates остаются открытыми |

Полные логи: `.codex/monetization-production-backend.log` и
`.codex/monetization-production-regressions.log`. Первоначальные 632 ok в
промежуточном сообщении были подсчётом только второго PTY chunk: полный повтор
с логом содержит 648. Проверки не удалялись. Пять устаревших structural assertions
runner приведены к свежему peer UI (`inboxRows`, `ActCard`, новый `onPress`,
JSX-вызов `AGE_PRESETS.map`); unread дополнительно запускает поведенческий
`chat_lifecycle_test.js`. Это не освобождает от export/native gates.

Backend выдаёт существующие warnings `psycopg_pool.open` и unclosed taxonomy file;
ошибок/пропущенных PG tests в указанном запуске нет.

Воспроизведение на этом Mac (из worktree):

```sh
export PATH=/Users/ivan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH
export KLEAL_MONETIZATION_TEST_DSN=postgresql://kleal_test:local_synthetic_only@127.0.0.1:55439/kleal_monetization_test_phase2a
/Users/ivan/.codex/worktrees/monetization-phase2/kleal/.codex/phase2-venv/bin/python -m unittest discover -s kleal-ms/tests -p 'test*.py' -q
cd kleal-app
node tools/regressions_test.js
node tools/identity_test.js
node tools/monetization_test.js
node tools/monetization_actions_test.js
node tools/chat_lifecycle_test.js
node node_modules/typescript/bin/tsc --noEmit
CI=1 node node_modules/expo/bin/cli export --platform ios --platform android --output-dir ../.codex/production-export
```

Используется уже существующий локальный test PG на 55439; каждый backend test
создаёт и удаляет собственную `test_<uuid>` schema. `kleal-app/node_modules` —
локальный untracked symlink на dependencies другого worktree, не release-файл
и не часть index. Не включать его через `git add .`, tar каталога или manifest.

## Отсутствующие бинарные assets: жёсткий gate

Совместный export остановился с `Unable to resolve module
../assets/art/wheel/sneaker.png from app/_layout.tsx`. Статическая проверка всех
literal image/font/sound requires обнаружила 16 уникальных отсутствующих путей
относительно `kleal-app/assets/`:

```text
art/wheel/sneaker.png
art/wheel/padel.png
art/wheel/gamepad.png
art/wheel/cherries.png
art/wheel/laptop.png
art/wheel/disco.png
fonts/TASAOrbiter-700.ttf
fonts/TASAOrbiter-600.ttf
fonts/Doto-700.ttf
art/buddy/create-mesh.png
art/home/bg.jpg
art/logo-mark-body.png
art/home/decor-smiley.png
art/home/decor-headphones.png
art/home/decor-martini.png
art/home/decor-note.png
```

Исторические копии wheel/fonts/home существуют в других локальных worktrees,
но `create-mesh.png` и `logo-mark-body.png` локальным поиском Projects/worktrees
не найдены. Неполный старый набор не подмешан; заглушки и изменения require ради
зелёного export не использовались. Нужен полный актуальный binary manifest и
точные файлы от координатора/свежей согласованной сверки. Исходники require:

| Файл в kleal-app | SHA-256 кандидата |
| --- | --- |
| app/_layout.tsx | `3aee30c84e656f74abd7a0f8b22ed6b8283dbfd15aa3aa51ba1c9a448f7381a9` |
| app/buddy.tsx | `b820e0c3d8e0baa3429b881799a3a73c3c2df7fc6c4d2c2bb35abcdbb510a571` |
| app/home.tsx | `526aa1524ba2b1212d63748e69c1f01d8d6fb3cecfb7727cf0dbe6f3388bff87` |
| src/components/KlealAgent.tsx | `295c0bd3b8b2e4a29ff8716e82c6ca72da70319609e2d7bbc9c01f1308a2c8eb` |
| src/wheel.ts | `8db1528b12fe4236069dbb3d957156e6d40d98df6315f9407772b32f9f407750` |

Отдельно добавлен требуемый AgeDial `sounds/click.wav` из immutable phase2 донора,
SHA-256 `f8b9acd3bc8cd01f2f3328b8705265ed035d76b008c791d5f4b51d412ce0def4`.
Он совпадает с уже имевшимся `tick.wav`; исходный `/Users/ivan/Downloads/click.wav`
сейчас отсутствует. Это подтверждение локального provenance, не свежести production.

## Готовность native fixture

`tools/monetization_native_fixture.py` импортирует matching и tests из ТЕКУЩЕГО
worktree, а не из старого phase2 checkout. Auth/KYC admission, users, parsing и
ranking синтетические; PG transactions, manual ledger, matching adapters и v2
wire реальные. Слушает только 127.0.0.1, использует test-DSN guard и удаляет свою
schema при штатном завершении/Ctrl-C. Не использовать SIGKILL; после аварии
координатор удаляет только явно напечатанную schema после проверки её принадлежности.

Из worktree, с test DSN из блока выше:

```sh
/Users/ivan/.codex/worktrees/monetization-phase2/kleal/.codex/phase2-venv/bin/python kleal-ms/tools/monetization_native_fixture.py --smoke --port 0
/Users/ivan/.codex/worktrees/monetization-phase2/kleal/.codex/phase2-venv/bin/python kleal-ms/tools/monetization_native_fixture.py --port 7599
```

После восстановления точных assets, в отдельном терминале из `kleal-app`:

```sh
EXPO_PUBLIC_API=http://127.0.0.1:7599 CI=1 node node_modules/expo/bin/cli start --localhost --port 8088
```

Expo Go SDK57 на iOS Simulator открывает `exp://127.0.0.1:8088`.
На физическом iPhone loopback Mac недоступен; этот helper не публикуется в LAN,
поэтому physical-device QA требует отдельно согласованного защищённого стенда.
Вход: `a@example.test` или `b@example.test`, код `123456`. Settings/logout и новый
вход проверяют account switch, возврат из background — обновление status.

Локальные fixture actions (НЕ production endpoints):

```sh
curl -fsS http://127.0.0.1:7599/qa/state
curl -fsS -X POST -H 'Content-Type: application/json' -d '{"owner":"a"}' http://127.0.0.1:7599/qa/expire
curl -fsS -X POST -H 'Content-Type: application/json' -d '{"owner":"a"}' http://127.0.0.1:7599/qa/grant
curl -fsS -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:7599/qa/maps
```

Grant даёт только A manual Plus на 5 минут; expire завершает его manual/Preview
и запрещает повторный Preview только внутри disposable fixture. B остаётся Free
до собственного meaningful use. Maps создаёт offline/online/hybrid intents D
около Madrid. Проверить native: A Free quota, manual Plus с независимым сроком,
expiry/keeper без auto-resume, B без прав A, background/relogin, map reply на
затее D и API/store receipt. Wire `--smoke` всё это UI-поведение не доказывает.

## Операторский CLI

Ни одного публичного HTTP grant/revoke маршрута нет. CLI запускает оператор с
закрытыми DB credentials в окружении, после миграции и активации. ID не имя/email.
Команды ниже — шаблон, `REAL_USER_ID` и `UTC_EXPIRY` надо заменить явно; срока
по умолчанию нет. Без `--apply` grant/revoke только проверяют и показывают change
и before-state. Status не создаёт account и не применяет downgrade.

```sh
python kleal-ms/tools/monetization_admin.py status
python kleal-ms/tools/monetization_admin.py status --user-id REAL_USER_ID
python kleal-ms/tools/monetization_admin.py grant --user-id REAL_USER_ID --expires UTC_EXPIRY --operator OPERATOR_ID --reason 'Approved support grant' --key UNIQUE_KEY
# После проверки ровно тот же payload/key:
python kleal-ms/tools/monetization_admin.py grant --user-id REAL_USER_ID --expires UTC_EXPIRY --operator OPERATOR_ID --reason 'Approved support grant' --key UNIQUE_KEY --apply
python kleal-ms/tools/monetization_admin.py revoke --user-id REAL_USER_ID --grant-id MANUAL_GRANT_ID --operator OPERATOR_ID --reason 'Approved revocation' --key NEW_UNIQUE_KEY
# После preview повторить revoke с --apply.
```

UTC_EXPIRY имеет вид `2026-11-01T00:00:00Z`, обязательно будущее на момент первой
команды. Один idempotency key с другим payload даёт conflict. Revoke другого
аккаунта/несуществующего grant, новый grant удаляемому ID, anon/name вместо ID
отклоняются. Повтор уже сохранённой команды возвращает её исходный результат,
поэтому текущие права затем смотреть через status.

## Cutover: обязательный порядок, пока НЕ исполнен

Следующий этап выполняет координатор после независимого diff review, восстановления
assets, повторных exports и native gates. Никакие результаты выше не разрешают
пропустить свежую сверку. Перед записью нужны approved окно/rollback owner и:

1. Свежие source/config/asset hashes и live DB inventory. Сверить с кандидатом,
   все чужие изменения узко перенести, повторить affected tests. Разобрать
   неоднозначные active links из preflight; importer их не угадывает.
2. На deployment host после source-hash agreement создать точечный manifest
   `manifest --root LIVE_ROOT --candidate CANDIDATE
   --paths EXPLICIT_CHANGED_FILES --file PRIVATE_MANIFEST`; затем `verify --root
   LIVE_ROOT --file PRIVATE_MANIFEST`. Точный список, никаких целых каталогов,
   node_modules, .git, секретов или snapshot replacement. SHA before/after,
   свежие production mode/uid/gid каждого исходного файла и checksum обязательны.
   Локальный snapshot/manifest с Mac uid/gid для live install не подходит.
   Metadata новых candidate files согласовать на deployment host. Новые бинарные
   artifacts и оба публичных bundle также должны иметь проверенный manifest.
3. Подготовить backup всей согласованной state-поверхности: users/store_kv/outbox, canonical
   tables, legacy Preview SQLite (если есть), account/session JSON, env/unit
   config и изменяемые source/bundles/assets с владельцем/правами. Проверить место
   и закрытое хранилище вне repo. Предварительный online snapshot не является
   точной резервной копией rows + sequences: sequence state не подчиняется MVCC.
4. Зафиксировать JSON `KLEAL_RELEASE_SERVICES` с точными проверенными loaded unit
   names для ролей `onboarding`, `matching`, `buddy`, `worker`, `life`, `admin`.
   Остановить ВСЕ writers, включая вне-systemd operator CLI; проверить отсутствие
   иных процессов/cron. `require_stopped` проверяет LoadState/ActiveState и fail
   closed, если inventory неполон. Старый код может fallback в JSON после ошибки
   PG, поэтому trigger сам по себе не заменяет остановку writers.
5. После остановки writers выполнить `backup --file PRIVATE_DB_BACKUP`: CLI
   проверяет настоящий require_stopped до чтения snapshot и записи файла.
   Все известные таблицы и точные last_value/is_called sequences сохраняются;
   unknown tables блокируют копирование. Выполнить restore rehearsal именно этой
   окончательной копии в пустой loopback `kleal_monetization_test*` DB / `test_*`
   schema, проверить checksum таблиц и sequences. В этом же окне повторить hashes
   и read-only production dry-run. Любой
   drift/alias/lifecycle issue останавливает cutover ДО активации. Указать legacy
   Preview evidence явно `--legacy-preview PRIVATE_JSON`, если ledger существует;
   старый status-only Preview сохраняется в provenance, не становится новым grant.
6. `install --root LIVE_ROOT --candidate CANDIDATE --file PRIVATE_MANIFEST
   --backup-dir NEW_PRIVATE_SOURCE_BACKUP --apply`: backup всех целевых старых
   файлов сделан до первой записи; install только exact paths, atomic file replace.
7. `tools/monetization_production.py import --expected-hash EXACT_DRY_RUN_HASH
   --apply` на том же DSN/evidence. В одной транзакции: table/advisory fence,
   проверка snapshot, additive schema, canonical import, durable legacy trigger,
   `release_state=staged`. Старые данные/внешние keys не переписываются.
8. Пока все writers остановлены, согласованно выставить во всех пишущих сервисах
   `KLEAL_DB=postgres`, тот же DSN, `KLEAL_MONETIZATION_MODE=enforce`; mirror/JSON
   недопустимы. Не менять KYC flags. `activate --file PRIVATE_DRY_RUN_EVIDENCE
   --apply` проверяет snapshotHash provenance и переводит staged→enforce.
9. Запустить только согласованный новый набор сервисов. Health + authenticated
   v2/quota + старый route + KYC-denial smoke; источник/срок Plus для точного ID,
   service states, фактические SHA обоих публичных bundles. `smoke --file
   PRIVATE_SMOKE_JSON` проверяет явно заданные URL/method/status/top-level JSON/SHA256;
   POST с JSON `body` допускается только для ожидаемого 4xx denial (quota/KYC),
   GET не принимает body. Для POST нельзя подставлять успешную публикацию;
   credentials берёт только из названных env vars. Это helper, не готовый
   production smoke inventory: составить его по реальным paths/auth/KYC cohort.
   Пока smoke и DB/foreign-state сверка не прошли, release не объявляется PASS.

Все команды `ops/monetization_release.py` используют `--file`; DB команды требуют
`KLEAL_PG_DSN`. `dry-run` выводит JSON с `ok`, `issues`, `snapshotHash`, ownership,
preserved rows, `wouldPause`; сохранить evidence приватно. Не использовать
`wouldPause` как разрешение игнорировать `ok=false`.

## Согласованный rollback с новыми writes

1. Снова остановить весь проверенный набор writers/CLI. Сделать НОВЫЙ backup
   canonical БД и текущих файлов; зафиксировать новые записи и source hashes.
2. `tools/monetization_production.py export` — preview. Затем
   `ops/monetization_release.py rollback --file PRIVATE_DRY_RUN_EVIDENCE --apply`.
   Экспортирует только ТЕКУЩИЕ canonical-owned documents, отражает текущую pause
   проекцию после expiry, сохраняет новые сообщения/историю, не обновляет users и
   чужие keys. Проверяет, что fenced legacy keys не менялись; иначе СТОП для
   согласования, не overwrite. Result содержит projectionHash/foreignHash.
3. Только после успешного export выполнить `restore-files --root LIVE_ROOT
   --backup-dir PRIVATE_SOURCE_BACKUP --file PRIVATE_MANIFEST --apply` и вернуть
   согласованные старые config/bundles из их точечных проверенных backups. Source
   restore проверяет before/after hashes, останавливается при чужом drift,
   убирает только exact originally-absent новые файлы из manifest.
4. Canonical tables/audit не удалять: они сохраняют след новых действий. Триггер
   отключает fencing только через подтверждённый `release_state=legacy`.
   Согласованно вернуть старый runtime mode, запустить writers, повторить
   health/auth/KYC/history/profile/interest smoke и сравнение с новым backup.
   Нельзя просто выключить flag на работающих смешанных версиях.

DB restore primitive специально запрещает non-loopback/live/nonempty schemas.
Проверенная копия старого backup — recovery rehearsal, не средство отката поверх
новых записей. При partial install до import использовать source restore только
при остановленных writers и подтверждённом отсутствии canonical activation.
