# Phase 2A — локальный implementation handoff

## A13: исправление отклика с карты после native FAIL, 14.10.2026

**Product freeze после map follow-up; автоматические проверки PASS. Native повтор
выполняет parent. Весь 2A остаётся `in-progress`.** Ранее parent на fresh iOS Expo
воспроизвёл `POST /api/agent/propose` → 409 `search_reference_required`: Free A
с занятым собственным поиском откликался на hybrid D. Карточка оставалась открытой,
обработчик map.tsx выпускал unhandled ApiError. Этот раздел дополняет и уточняет
приведённый ниже предшествующий автоматизированный handoff.

### Новый узкий контракт и product delta

- `src/offline-map-feed.ts` / `src/explore.ts` сохраняют feed `searchId` в пине.
  `app/map.tsx` и `app/map-intent.tsx` вызывают общий `sendIntentReply` в
  `src/invites.ts`: `intent: {targetIntentId: feed.id, targetSearchId: feed.searchId}`
  плюс title для подписи и whitelist публичных полей feed для legacy off/shadow.
  Whitelist не переносит link/Buddy phrase/text/summary/координату человека или
  own-search ID; в enforce весь fallback заменяется каноническим snapshot.
  Отправки `search-command`, вступления
  в группу или человеческого сообщения из этого действия нет.
- `matching/monetization_commands.py` под той же PG transaction проверяет
  канонический intent/group alias, совпадение обеих ссылок, stable recipient ID
  как владельца и active state с фактическим expiry. Snapshot берётся из
  канонического ресурса через public projection, не из присланных title/topics.
  Приватные Buddy text/link и own-search поля `id`/`_searchId` не копируются.
  Legacy detail с одним `targetIntentId` работает; чужой `_searchId` по старому
  own-search контракту по-прежнему отклоняется. Нет новой публикации/Preview
  отвечающего, расхода второго собственного слота или обхода safety/consent.
- Отклик на group — заявка автору, не admission. Старый pending reply принимается
  после паузы/expiry; новая заявка к paused search отклоняется. При замене pending
  заявки той же пары `matching/app.py` сбрасывает прежний own-intent `iid`, а
  provenance защиты обновляется на новый проверенный ресурс атомарно.
- Ошибки обоих UI остаются в карточке с понятным retry; paused/invalid target имеет
  отдельную копию RU/EN/ES. Неуспех не записывает приглашение в кэш. Поздний ответ
  после смены аккаунта не меняет новый кэш/экран. Generation конкретного открытия
  карточки защищает новый target и его spinner от старых success/error/finally,
  в том числе при возвращении к прежнему ID. Успешная серверная заявка не отменяется.
  Кэш хранит reply `targetIntentId`; detail считает «отправлено» по конкретному
  интенту, а не любому приглашению тому же автору с тем же названием.

### Свежая проверка map-delta

**Test-only correction после независимого parent rerun.** В
`.codex/phase2-parent-final-backend.log` parent воспроизвёл flaky equality в
`test_real_http_map_reply_uses_authors_search_without_publishing_responders_search`:
из всего status изменился только `serverTime` на одну секунду. Исправлен только
тест: все поля, кроме этого observation timestamp, по-прежнему сравниваются
строго целиком; отдельно проверяются целочисленный serverTime, его неубывание и
верхняя граница свежим PG clock. Других whole-status equality с таким дефектом
в новых `test_monetization_phase2.py` / `test_monetization_pg.py` не найдено;
проверки grant timestamps и immutable rollback SESSION сохранены.

После исправления полный backend suite: **87 PASS, 15.724s, 0 skipped**,
`.codex/phase2-clock-assertion-backend.log`. Дополнительный запуск того же real HTTP
теста с задержкой перед повторным status-read принудительно пересёк секунду:
**1 PASS**, `FORCED_CLOCK_BOUNDARY before=1791964550 after=1791964551 delta=1`,
`.codex/phase2-clock-boundary-regression.log`. Продуктовые файлы и ранее проверенные
bundles не изменялись; это устранение flake, не ослабление бизнесинвариантов.

В том же isolated PG полный suite: **87 PASS, 15.776s, 0 skipped**,
`.codex/phase2-map-reply-backend.log`. Новые тесты в `tests/test_monetization_phase2.py`:

- `test_real_http_map_reply_uses_authors_search_without_publishing_responders_search`
  — сначала RED на исходном 409, затем PASS через настоящий localhost HTTP и
  bearer auth. Проверяет replay, подмену sender/recipient/reference/payload,
  unknown/malformed target, блокировку, занятый Free search, отсутствие нового
  ресурса/Preview, обновление provenance и acceptance после pause.
- `test_map_group_reply_is_application_not_membership_or_own_search` — group alias,
  mismatch/paused denial и отсутствие добавления участника/собственного поиска.
- `test_map_reply_checks_actual_expiry_but_keeps_existing_reply` — автоматическая
  expiry-пауза автора блокирует новое, но не старое pending обязательство.
- `test_map_reply_public_snapshot_off_and_shadow_remains_legacy_without_grant` —
  off/shadow сохраняют публичные темы/время/название заявки без публикации и Preview;
  enforce отдельно проверен с подменёнными клиентскими полями в real HTTP test.

Отдельный `-k map_` rerun: **5 PASS** (включая прежний hybrid projection test),
`.codex/phase2-map-reply-http.log`. Лог содержит marker с настоящим ID тестовой
HTTP-заявки: `MAP_REPLY_HTTP_PASS searchId=search_7dde70a254c84bf18b6910fe51432fe7
invitationId=rq_1791934177381_4aeb19 sender=a author=d usage=1/0`.
Это disposable synthetic fixture; ID не относится к native/production аккаунтам.

Новая `tools/map_reply_test.js`: **11 PASS**, `.codex/phase2-map-reply-client.log`.
Исполняет реальные оба экрана, adapter, invitation cache и API с synthetic fetch;
проверяет 409/503/retry, stable ID, online group, account switch, смену target того же
автора/названия и A→B→A с новым pending request, whitelist legacy fallback против
private payload/foreign own-search injection. Включена в обычный runner.
Общий runner: **648 ok + 8 прежних acceptance + 11 map cases, 0 FAIL**,
`.codex/phase2-map-reply-regressions.log`. Все прежние 13 client suites повторены:
`.codex/phase2-map-reply-<suite_name>.log`; backend identity **25 PASS**.
TypeScript и staged/unstaged diff check PASS; `.codex/phase2-map-reply-tsc.log` пуст.

Оба Expo exports повторены после generation guard и off/shadow compatibility: PASS. Логи
`.codex/phase2-map-reply-export-ios.log` и `-android.log`; выходные каталоги
`.codex/phase2-map-reply-export-ios` и `-android`. Bundles: iOS
`entry-64abc4f85e4572d80507de9c0753de1e.hbc`, Android
`entry-5536838bdf3e401f6a783d78643e42af.hbc`.

Native повтор A13, полнота обязательного native checklist, полный parent diff audit
и formal review не подменены этими проверками. Parent сообщил, что coordinate
gestures CUA остаются BLOCKED `noWindowsAvailable`; это не PASS. Android full-flow
остаётся отложенным. Native helper `.codex/phase2-native-server.py` не изменялся.
Нет Stripe code/activation, commit/push/deploy/shared service changes.

## Предшествующая автоматизированная приёмка: 14.10.2026

**Автоматизированный handoff выполнен; весь 2A остаётся `in-progress`.** Работа
в прежнем worktree `codex/monetization-phase2a`, baseline
`d633bb7541f97c69690203fe44c8c47f13002e76`. Прежние staged-изменения сохранены.
Ниже текущий результат; отметки FAIL/непройденных автоматических проверок в
исторических разделах не описывают этот новый прогон. Native acceptance, полный
parent diff audit и формальное BMAD review остаются отдельными gates. Android
full-flow отложен пользователем. Stripe в этот handoff не входит.

### Подтверждённые ошибки и изменения

`kleal-app/src/api.ts`:

- Повторная проверка аккаунта и AbortSignal после ожидания записи retry metadata,
  непосредственно перед отправкой. RED воспроизвёл отправку payload аккаунта A
  с `Bearer token-b`, если переключение происходило во время AsyncStorage write.
  После исправления запрос не отправляется; поздний ответ A не вызывает refresh B.
- Отмена до отправки не открывает пояснение Preview и не отправляет команду.
  Отмена после начала отправки сохраняет ключ для явного повтора: сервер мог уже
  выполнить commit. RED воспроизвёл новый commandId после abort и перезагрузки модуля;
  теперь используется исходный ключ. Автоматического replay при загрузке нет.
- Известный HTTP-отказ позволяет отменить действие обычным образом; после потери
  ответа metadata остаются. Payload, bearer и права в metadata не записываются.
- Поздний HTTP 409 после abort не открывает quota sheet отменённого экрана.
  Дополнительный RED→GREEN subcase подтвердил эту ошибку; guard в catch устранил
  её. Все client suites, общий runner, TypeScript и оба exports повторены после него.

`kleal-app/src/monetization-actions.ts`:

- Временный отказ чтения AsyncStorage больше не оставляет навсегда rejected promise:
  следующий явный retry снова читает хранилище. Ошибка всё ещё останавливает отправку.
- Уже отменённый сигнал не оставляет необработанное отклонение внутренней операции.
  Это отдельно воспроизведено при отмене во время чтения metadata.

Новая `tools/monetization_acceptance_test.js` исполняет реальные API/metadata функции
с synthetic storage/fetch; 8 именованных сценариев. Она включена в обычный
`tools/regressions_test.js` отдельным дочерним процессом и обязана завершиться с 0.
Это JS-проверки, не native process-kill, UI/gesture или настоящая запись медиа.

Backend product-файлы не менялись. В `test_monetization_pg.py` и
`test_monetization_phase2.py` добавлены 10 тестов: одновременные meaningful events,
status 503/recovery, серверное время против client query, nonmeaningful reads,
регистрация/KYC observation, 1:1 acceptance, групповой чат, несколько media-инициатив
Preview с последующим expiry, старое приглашение после фактического expiry и выбор
последнего опубликованного поиска, когда keep-search не задан.
Усилены retry после DB outage, счётчик участия в чужой группе и hybrid с настоящим
`starts_at` через 7 дней. Synthetic KYC proof/profile storage изолированы doubles;
это не live KYC approval и не изменение допуска.

### Свежие команды и доказательства

Все команды из корня feature-worktree; Python окружение и Node dependencies прежние.
PG только `127.0.0.1:55439/kleal_monetization_test_phase2a`; каждый тест сам создаёт
и удаляет UUID schema. Нет live migrations, чужих аккаунтов, рестартов или оплаты.

```sh
KLEAL_MONETIZATION_TEST_DSN=postgresql://kleal_test:local_synthetic_only@127.0.0.1:55439/kleal_monetization_test_phase2a .codex/phase2-venv/bin/python -m unittest discover -s kleal-ms/tests -p 'test*.py' -v
.codex/phase2-venv/bin/python kleal-ms/tools/identity_test.py
for test in monetization_test monetization_actions_test monetization_acceptance_test identity_test session_test account_switch_test ginvites_closed_test chat_lifecycle_test conversation_lifecycle_test role_quota_recovery_test interest_confirmation_test interest_hierarchy_test regression_contracts_test; do
  /Users/ivan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node "kleal-app/tools/${test}.js" || exit
done
/Users/ivan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node kleal-app/tools/regressions_test.js
/Users/ivan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node kleal-app/node_modules/typescript/bin/tsc --noEmit --project kleal-app/tsconfig.json
git diff --check
git diff --cached --check
```

- Полный обнаруживаемый backend suite `test*.py`: **83 PASS, 14.757s, 0 skipped**,
  `.codex/phase2-acceptance-backend.log`. До новых тестов независимо выполнены 73 PASS.
- Backend identity: **25 PASS / 0 FAIL**, `.codex/phase2-acceptance-identity-backend.log`.
- Все 13 перечисленных client suites PASS. Лог каждой:
  `.codex/phase2-acceptance-<test>.log`; в том числе 8 новых acceptance, 11 monetization,
  12 regression contracts, identity 25, session 6. JS doubles не выданы за native.
- Обычный regression runner: **648 `ok`, 0 FAIL**, плюс встроенная новая **8-case
  acceptance suite**, `.codex/phase2-acceptance-regressions.log`. Старые проверки,
  включая R01 «Дать ещё время», не ослаблены.
- TypeScript: PASS, exit 0, `.codex/phase2-acceptance-tsc.log`; staged/unstaged
  `git diff --check`: PASS.
- Expo export: PASS iOS и Android. Из `kleal-app/` для каждой платформы выполнено:

```sh
PATH=/Users/ivan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH CI=1 EXPO_NO_TELEMETRY=1 /Users/ivan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/expo/bin/cli export --platform ios --output-dir ../.codex/phase2-acceptance-export-ios
PATH=/Users/ivan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:$PATH CI=1 EXPO_NO_TELEMETRY=1 /Users/ivan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/expo/bin/cli export --platform android --output-dir ../.codex/phase2-acceptance-export-android
```

Логи `.codex/phase2-acceptance-export-ios.log` и `-android.log`;
iOS bundle `entry-6811231c0fe21dbba2d51f5d11581ce6.hbc`, Android
`entry-ad978085f92eda5687070fdc9d0e4723.hbc`. Это export, не store-build или native QA.

### Frozen I/O matrix: тесты, действительно выполненные в этом прогоне

Здесь `PG` = `tests/test_monetization_pg.py`, `P2` = `tests/test_monetization_phase2.py`,
`JS` = `kleal-app/tools/monetization_acceptance_test.js`. Каждый Python identifier
ниже присутствует как `... ok` в свежем backend-логе; все 8 JS сценариев напечатаны
отдельно в acceptance-логе и запускаются обычным regression runner.

| Строка frozen matrix | Исполняемое доказательство | Результат |
|---|---|---|
| Первый meaningful use | PG `test_grant_atomic_exact_duration_and_retry`, `test_rollback_no_phantom_grant_resource_or_outbox`; P2 `test_pending_approval_no_grant_actual_admission_grants`, `test_one_to_one_acceptance_grants_once_but_decline_and_failed_accept_do_not` | PASS local PG |
| Повтор/гонка | PG `test_two_process_meaningful_events_create_one_immutable_grant`, `test_two_process_publication_and_restart_retry`, `test_conflicting_payload_and_scoped_owners` | PASS; отдельные OS processes |
| Квота | P2 `test_group_and_search_share_alias_not_second_slot`, `test_message_allows_response_and_explicit_end_releases_slot_once` | PASS |
| Swap | P2 `test_resume_restores_canonical_payload_and_quota_swap_is_atomic`; PG `test_swap_is_atomic_and_owner_checked` | PASS |
| Expiry | PG `test_expiry_selected_and_no_automatic_restart`, `test_equal_expiry_timestamps_use_stable_resource_id`, `test_expiry_without_choice_keeps_last_published_search`; P2 `test_ready_replay_cannot_bypass_pause_or_expiry` | PASS; серверные часы |
| Неизвестные права | P2 `test_database_failure_returns_retryable_error_without_json_fallback`, `test_v2_unknown_is_retryable_and_recovery_preserves_exact_server_grant`; JS `A03: unknown status…`, `A03: временный отказ чтения…` | PASS; 503/без фиктивного тарифа, retry |
| Старый клиент | P2 `test_real_http_authentication_and_legacy_route_cannot_bypass_quota`, `test_status_notice_keeper_wire_identity_and_validation`, `test_writer_inventory_no_unclassified_save_store_paths` | PASS wire/adapters; установленный native v1 не запускался |
| Смена аккаунта | JS `A02: смена аккаунта во время записи retry metadata…`, `A02: поздний ответ A…`; `monetization_actions_test.js` account isolation/return action | PASS; найденный race исправлен |
| Освобождение чата | P2 `test_message_allows_response_and_explicit_end_releases_slot_once`, `test_end_preserves_active_plan_communication_and_block_replay_is_safe`, `test_nested_report_block_releases_chat_without_plan_and_replay_is_safe` | PASS end/block/replay |
| Конец встречи не закрывает чат | P2 `test_plan_terminal_writers_preserve_chat_and_quota_after_replay`, `test_elapsed_meeting_and_postplan_feedback_preserve_initiator`; PG `test_plan_lifecycle_cannot_be_used_to_close_chat` | PASS; session/initiator/history/quota |
| Смена организатора | P2 `test_role_recipient_quota_rolls_back_owner_and_roster`, `test_auto_vote_and_safety_exit_never_assign_over_quota_owner`, `test_role_quota_decline_returns_choice_to_owner_without_slot_writes`; `role_quota_recovery_test.js` | PASS adapters/JS; native остаётся отдельным |

### A01–A24 / A33–A37: актуальная карта приёмки

`MC` = `monetization_test.js`, `MA` = `monetization_actions_test.js`,
`CC` = `conversation_lifecycle_test.js`, `CL` = `chat_lifecycle_test.js`,
`RC` = `regression_contracts_test.js`, `RQ` = `role_quota_recovery_test.js`.
PASS в этой таблице означает только явно указанный автоматизированный уровень.

| ID | Выполненный тест / проверяемая граница | Статус |
|---|---|---|
| A01 | P2 `test_real_http_authentication_and_legacy_route_cannot_bypass_quota`, `test_status_notice_keeper_wire_identity_and_validation`: настоящий bearer resolver, чужой owner/keeper | PASS HTTP+PG |
| A02 | JS оба `A02`; MC `late result from previous account never overwrites current account`; MA return-action; CL/RQ session/unmount | PASS JS |
| A03 | P2 оба outage-теста из frozen matrix; MC `network, auth and malformed responses never retain active access`; JS оба `A03`; PG concurrent/restart | PASS synthetic; два native устройства не проверены |
| A04 | P2 `test_registration_and_synthetic_kyc_observation_do_not_start_preview`, `test_nonmeaningful_reads_and_draft_leave_eligible_account_without_grant`, `test_draft_does_not_start_preview_publish_does` | PASS; register_profile и KYC state с isolated storage/proof doubles |
| A05 | P2 draft→publish, 1:1 acceptance, pending→approve, `test_pending_invite_survives_actual_expiry_without_reopening_recruitment`, `test_legacy_paused_group_new_join_blocked_existing_waitlist_promoted` | PASS всех mapped meaningful transitions |
| A06 | PG `test_two_process_meaningful_events_create_one_immutable_grant`, `test_grant_atomic_exact_duration_and_retry`, `test_rollback_no_phantom_grant_resource_or_outbox` | PASS |
| A07 | P2 `test_server_clock_ignores_client_clock_timezone_and_duration`; PG exact duration; MC server-expiry | PASS; 1209600 UTC seconds |
| A08 | PG `test_legacy_status_preview_is_audited_once_without_consuming_eligibility`; P2 `test_ambiguous_legacy_links_are_blocked` | PASS synthetic migration |
| A09 | P2 `test_group_and_search_share_alias_not_second_slot`, HTTP legacy gate | PASS |
| A10 | P2 `test_map_hybrid_single_resource_and_paused_on_both_surfaces` теперь с future starts_at; draft и pending→approve проверяют нулевую квоту чужого участника | PASS |
| A11 | PG `test_two_process_publication_and_restart_retry`, конкурентный grant; P2 общая identity group/search | PASS OS processes+PG |
| A12 | PG `test_process_death_rolls_back_database`, rollback/restart; P2 `test_pause_keeps_payload_and_durable_launch_recovers`; JS три `A12` / MA lost-response reload | PASS OS process для PG, module reload для клиента |
| A13 | P2 `test_resume_restores_canonical_payload_and_quota_swap_is_atomic`, `test_buddy_delegates_to_canonical_matching_with_real_ranker`, `test_real_search_route_contracts_match_off_free_and_preview` | PASS |
| A14 | P2 `test_chat_read_reports_canonical_resume_end_block_and_failed_quota`, `test_support_system_and_media_share_correct_quota_semantics`; CC explicit resume without send | PASS |
| A15 | P2 `test_preview_media_initiatives_preserve_safety_and_free_limit_after_expiry`, `test_support_system_and_media_share_correct_quota_semantics`; JS `A15/A35`; CC | PASS synthetic text/voice/video; native media открыт |
| A16 | P2 support/media reply, `test_group_chat_and_manual_coordination_do_not_take_initiative_slot`, Buddy route; PG `test_plan_continuation_does_not_take_new_slot` | PASS; group/support/Buddy не занимают инициативный слот |
| A17 | PG `test_opposite_first_messages_choose_one_initiator`; P2 block/replay, nested reports; CC disabled composer | PASS |
| A18 | P2 terminal writers/elapsed feedback/end replay; PG close reason allowlist; CL archive/id; CC end error/retry | PASS automated; без освобождения от meeting terminal |
| A19 | PG `test_expiry_selected_and_no_automatic_restart`; P2 `test_ready_replay_cannot_bypass_pause_or_expiry` | PASS без cron/app visit |
| A20 | PG selected/no-restart, `test_equal_expiry_timestamps_use_stable_resource_id`, `test_expiry_without_choice_keeps_last_published_search` | PASS selected/fallback/tie |
| A21 | P2 `test_map_hybrid_single_resource_and_paused_on_both_surfaces`, ready replay, legacy paused joins | PASS API feeds/витрины; native rendering открыт |
| A22 | P2 `test_pending_invite_survives_actual_expiry_without_reopening_recruitment`, pending approval/waitlist | PASS actual expiry, ровно один grant, новый набор запрещён |
| A23 | P2 Preview media→expiry, terminal plan/feedback, active-plan continuation, role rollback; PG paused-group transfer | PASS history/logistics/roster сохранены |
| A24 | PG `test_protected_provenance_exact_resource_action`, `test_migration_closed_plan_does_not_guess_current_session`; P2 `test_malicious_protected_references_cannot_create_new_obligations`, `test_terminal_history_never_binds_to_new_session` | PASS resource/action scope |
| A33 | MC `additive navigation and no purchase command in screen`, copy; MA/JS cancel/defer/reload; RQ role→Plus return; RC navigation | PASS JS/source; оставшиеся native entrypoints открыты |
| A34 | MC RU/EN/ES status/notice, RQ/CL copy, RC fixed 44pt back target; экспорт обеих платформ — отдельная проверка сборки | PARTIAL: VoiceOver/TalkBack, малый экран и жесты нельзя доказать JS |
| A35 | 15 foundation tests; P2 v1/v2 HTTP + legacy matching gate + writer inventory; JS `A15/A35` structured errors/retry | PASS wire/adapters; установленный старый native client не проверен |
| A36 | P2 `test_real_ranking_contract_and_safety_are_tier_independent`, `test_real_serving_kyc_denied_is_identical_for_free_and_preview`, nested report/block | PASS actual local ranker/serving with synthetic users; не live provider |
| A37 | P2 `test_flags_off_by_default_and_invalid_fail_closed`, `test_shadow_keeps_legacy_write_without_grant_and_audits`; PG `test_synthetic_backup_restore_and_exact_legacy_rollback` | PASS synthetic; live activation/rollback не разрешены |

### Что осталось родителю

1. Native iOS: owner-picker/recovery и остальные entrypoints wizard/Buddy/maps/results/
   invite/group/Plus, сохранённый план/история после expiry; ранние точечные PASS
   остаются историческими доказательствами, не новым полным native flow.
2. Реальные запись/upload/доставка/воспроизведение voice/video, отказ квоты, повтор
   при потере сети; kill/relaunch приложения, account switch и return/back жесты.
   В этой итерации доказаны только backend payload gate и JS/module restart.
3. Полная UI-проверка RU/EN/ES по потоку, малый экран, Dynamic Type, VoiceOver.
   TalkBack/Android native не пройдены; полный Android flow отложен пользователем.
   Parent сообщил повторный `noWindowsAvailable` на scroll/drag Device Hub; AX clicks
   доступны. Этот инструментальный BLOCKED не заменён снимком/JS PASS.
4. Свежий полный diff/matrix audit, формальное BMAD review, локальная фиксация после
   выполнения gates. Implementer не создавал commit и не управлял эмулятором.

Глобальная projection advisory lock и process RLock остаются ограничением масштаба;
нагрузочный отчёт 12.10 не превращён в production SLO и заново не объявлен свежим.
Scaffold writers в enforce остаются явно запрещёнными; см. writer inventory ниже.
Ни push/deploy/restart, ни KYC admission, ни live migration/payment не выполнялись.

---

## История: результат 13.10.2026

**Статус: частично выполнено, этап 2A ещё не принят.** Полный Android-флоу исключён
пользователем; это не PASS. Ни production, ни платежи, ни допуск KYC не менялись.
Ниже результат закрывающего прохода 12–13 октября; более ранние разделы сохранены
как история проверок, а не как подтверждение нового полного прогона.

### R01 follow-up после разрешения пользователя, 13.10.2026

Пользователь подтвердил «да, возвращаем». В `app/gplan.tsx` восстановлена
«Дать ещё время» рядом с «Закрепить план» для организатора: `proposed`,
`rounds_used_up=true`, `can_fix=true`. Сохранены текущие Confirm/Open chat и Fix.
Кнопка вызывает существующий `onMoreTime`: остаётся на экране, не отправляет API,
не навигирует и не меняет deadline/rounds. Используются прежние строки RU/EN/ES.

В `tools/regression_contracts_test.js` добавлены исполняемые проверки условий
видимости/отсутствия, порядка кнопок, вызовов каждого обработчика и повторных
нажатий настоящего callback из JSX экрана. Проверяется вся копия плана, отсутствие
API/навигации/setter/таймеров и передача `onPress` через реальные P/S до GlassPill.
До исправления проверка воспроизвела отсутствие `moreTime` (RED), после — PASS.
`tools/regressions_test.js` в этой итерации не менялся: R01 сохранён и проходит.

Проверено implementer в feature-worktree, команды из его корня:

```sh
/Users/ivan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node kleal-app/tools/regression_contracts_test.js
/Users/ivan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node kleal-app/tools/regressions_test.js
/Users/ivan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node kleal-app/node_modules/typescript/bin/tsc --noEmit --project kleal-app/tsconfig.json
git diff --check
git diff --cached --check
```

Результат: **12 behavioral contracts PASS**, обычный полный regression runner —
**648 `ok`, 0 FAIL**, TypeScript и обе whitespace-проверки — PASS. Свежие логи:
`.codex/phase2-r01-regressions.log` (включает 12 contracts), `.codex/phase2-r01-tsc.log`.
Native-процессы не запускались; это JS-проверки реальных функций/JSX с UI doubles,
не native rendering/gesture/accessibility. Backend и Expo export заново не запускались:
этот delta затрагивает только кнопку и тесты. Прежние staged-изменения сохранены;
commit/push/deploy, платежей и изменений KYC не было. Итог передан parent для
независимой проверки, общий 2A остаётся `in-progress`.

Parent затем прочитал весь точечный delta R01 и независимо повторил 12 behavioral
contracts, общий runner (**648 ok / 0 FAIL**), TypeScript и diff-check — PASS.
Лог: `.codex/phase2-r01-parent-regressions.log`. Условие показа, прямой callback и
неизменность deadline/rounds подтверждены кодом и исполняемыми проверками;
это закрывает R01, но не заменяет незавершённое общее native/review 2A.

| Пункт закрытия | Результат | Что осталось |
|---|---|---|
| 1. Hybrid/search fallback | PASS: отсутствующий/null title больше не ломает online fallback; проверены missing/null и сохранённый результат | — |
| 2. Регрессии | R01 follow-up: общий клиентский набор 648 PASS, 0 FAIL; 12 поведенческих контрактов и TypeScript PASS, независимо повторены parent. Ранее: 73 backend-теста и Expo export iOS/Android PASS | Backend/export в узком follow-up не повторялись |
| 3. iOS-флоу | Частично: предыдущие подтверждённые Preview/quota/swap/chat/recipient-role сценарии сохранены; свежий Plus/обновление статуса проверены на отдельном iOS-стенде | Полный перечень native-сценариев не закрыт: owner-picker, map-entrypoints, media/process-death и жесты; Android full-flow отложен |
| 4. UI/доступность | Plus проверен RU/EN/ES; крупный шрифт обнаружил и помог исправить обрезанную стрелку «Назад»; фиксированная иконка, цель 44 pt, тест реального компонента PASS | Полная проверка малого экрана, VoiceOver и прокрутки при крупном шрифте не подтверждена |
| 5. Нагрузка | PASS на описанном ниже локальном профиле 1/4/8 процессов: 0 неожиданных ошибок и нарушений квот, retry без дублей, outbox 8→0 | Это не замер production capacity; обнаружена сериализация на общей projection-блокировке |
| 6. Итоговое ревью/фиксация | Отчёт и доказательства сохранены, изменения остаются в отдельном worktree | Полный аудит diff и формальное BMAD review не завершены; релизного коммита нет |

### Дополнительные исправления этого прохода

- При замене интереса старое значение сохраняется до серверного подтверждения; отмена,
  отказ и поздний ответ после смены аккаунта не теряют/не подменяют выбор.
- Для известных листьев MindMap сохраняются реальные родительские категории из реестра;
  неизвестные/неоднозначные значения не получают выдуманных родителей. Счётчик выбора
  продолжает считать выбранные пользователем интересы, а не автоматически добавленных родителей.
- Подтверждения интересов не уходят в общий профильный attach payload.
- Устаревшие проверки приведены к текущим компонентам и дополнены исполняемыми контрактами.
  До разрешения пользователя контракт R01 был сохранён падающим. После подтверждения
  13.10 кнопка восстановлена, текущий R01 PASS; прежние FAIL ниже — история до follow-up.
- `ProfileShell`: текстовый символ стрелки заменён `IconChevronLeft size={24}`, область
  нажатия увеличена до 44×44 pt. На iOS при Accessibility Large иконка больше не обрезается.

### Независимая проверка координатора перед R01 follow-up

- Backend: `unittest discover -s kleal-ms/tests -p 'test_monetization*.py' -v` —
  **73 PASS, 12.737 s** на реальном локальном PostgreSQL, без production-данных.
- Повторены interest confirmation/hierarchy, monetization actions, chat lifecycle,
  conversation lifecycle и role quota recovery — PASS.
- После последнего UI-исправления: `regression_contracts_test.js` — **9 PASS**;
  `regressions_test.js` — **647 PASS / 1 FAIL (R01)**; `tsc --noEmit` — PASS.
- Expo export iOS и Android — PASS; это bundle/export, а не подпись store-build
  и не полное тестирование на устройстве. `git diff --check` — PASS.
- Логи: `.codex/phase2-parent-completion-backend.log`,
  `.codex/phase2-parent-final-regressions.log`,
  `.codex/phase2-parent-final-export-ios.log`,
  `.codex/phase2-parent-final-export-android.log`.

### iOS-доказательства и ограничения

Стенд: Expo Go SDK57, iOS 26.5, отдельный loopback API :7599 и Metro :8088,
синтетические аккаунты и отдельная PG schema. Identity/ranking синтетические;
платежи и реальная KYC-проверка в этот прогон не входят.

Скриншоты находятся в `.codex/phase2-native-qa/20261013-completion/`:

- `plus-ru.png`, `plus-en.png`, `plus-es.png` — обычный шрифт, состояние истёкшего Preview.
- `plus-large-before-fix.png`, `plus-large-fixed.png` — крупный шрифт до/после исправления стрелки.

Управление Device Hub повторно возвращало `noWindowsAvailable` на scroll/drag и
`The element ID is no longer valid` на части системных меню. AX-нажатия и чтение
экрана работали не во всех случаях. Поэтому доступность нижней кнопки реальным свайпом
при крупном шрифте, VoiceOver и весь оставшийся native-перечень не объявляются PASS.
Шрифт возвращён в исходный `large`, язык — RU; собственные API/Metro/bridge остановлены.
Удалена только disposable schema этого прогона: проверено 0 оставшихся совпадений.
Общий контейнер PostgreSQL и чужие процессы не останавливались.

### Что требуется для продолжения приёмки

1. R01 закрыта 13.10.2026: разрешение пользователя, исправление, тесты и независимый
   повтор parent получены. Ожидания решения по этой кнопке больше нет.
2. Пройти недостающие iOS-сценарии через работающее управление устройством и закрыть
   UI/accessibility проверки; Android full-flow остаётся отдельно отложенным.
3. После зелёного прогона завершить полный аудит diff, формальное BMAD review и
   локальную фиксацию. Правила `bmad-build` не позволяют считать этап завершённым
   с неподтверждёнными критериями; статус спецификации оставлен `in-progress`.

---

11.10.2026, revision после native chat/organizer follow-up. Baseline `d633bb7541f97c69690203fe44c8c47f13002e76`, ветка
`codex/monetization-phase2a`, worktree `/Users/ivan/.codex/worktrees/monetization-phase2/kleal`.
**Этап целиком не принят. Enforcement включать нельзя до закрытия пробелов ниже и review.**
Никаких push, production deploy/restart, live migration, платежей или изменений KYC admission не было.

## Реализовано

- Additive PG repository: accounts/grants, owner-scoped command ledger с payload hash,
  resources/aliases, pair sessions, exact plan-session link, protected provenance, audit,
  canonical document projection. Grant, состояние, outbox и ответ команды commit вместе.
- PG server time, Preview 1 209 600 секунд, однократная eligibility, deterministic expiry,
  собственные blocker IDs, atomic swap, приватный отказ передачи роли.
- Первый human message открывает сессию; reply её использует. Только явный end chat или новая
  block закрывают сессию. Конец/отмена/отказ/timeout/feedback плана сохраняют session ID,
  инициатора, историю и занятую квоту. Media идут через тот же writer.
- Явная synthetic-only migration; dry-run по умолчанию. Legacy Preview сохраняется в audit;
  старым чатам не угадывается инициатор по обрезанной истории. Неоднозначные alias отклоняются.
- V2 status/notice/keep-search, совместимый foundation/v1 read; ручной Preview не выдаёт grant
  в enforce. `KLEAL_MONETIZATION_MODE=off|shadow|enforce`, default `off`. Shadow делает rollback
  проверки и сохраняет только audit решения, не меняя legacy результат.
- Единая search-command с pause/resume/swap. Ranking после commit без PG-lock.
  Локальный outbox worker восстанавливает pending launch; lease, retry и first-result-wins.
  Rabbit relay не забирает `monetization.search.launch`. Неуспешный ranking — pending, не фиктивная готовая выдача.
- Map/explore/saved-search/legacy group list учитывают canonical pause. Новые приглашения/join
  запрещены, старое pending admission и waitlist promotion сохранены. Hybrid использует один resource.
- Централизованный client gate, session-scoped responses и pending action, стабильный ключ повторной
  доставки media/text, Preview explanation/notice, foreground refresh, единый Plus без покупки и цены.
  Убран локальный запрет открытия истории; исправлен awaiting approval.

## Исправления после первого handoff

- По уточнению пользователя от 09.10 terminal plan больше не закрывает даже связанную сессию:
  вызов и метод `end_plan` удалены; store API разрешает закрытие только с reason `end_chat`/`block`.
  Plan→session остаётся исторической provenance-связью, не источником освобождения квоты.
  Additive schema и старое поле `terminal_applied` сохранены без очистки прежних данных; уже
  закрытые записи автоматически не открываются. Исторический terminal plan не связывается
  с новой сессией по совпадению пары ни при reconciliation, ни при migration.
  Освобождение по block проверяет реальные новые пары в `_blocks`, включая вложенные
  `report_user` и `gi_report`; replay старой жалобы и unblock не закрывают новую сессию.
- Новая сессия после end проходит обычную квоту; необходимое общение по действующему плану
  сохраняет scoped protected-исключение. Для этого используется существующее определение
  действующего плана `_mp_of`: старый `confirmed` за горизонтом `MP_KEEP_AFTER` не даёт вечное
  исключение новому чату. Само течение времени по-прежнему не закрывает текущую сессию.
- Cached ready launch перед выдачей повторно проверяет expiry/active state. Pause скрывает
  candidates даже при старом body/key. Ranking использует общие `prepare_search`/`render_search`
  для off/shadow/enforce, старых match/plan/confirm/expand и Buddy: compiler, pilot, limit/has_more,
  labels, retrieval, expansion, read-only group formation сохраняются.
- Pending actions сохраняют только account ID, SHA-256 fingerprint операции, ключ, timestamp
  и подтверждённый swap ID. Payload, bearer и grant не сохраняются. После process death явный
  повтор того же действия восстанавливает ключ; автоматического replay нет. Cancel/back/blur/
  unmount отвергают promise; concurrent clicks объединены. Смена аккаунта изолирует metadata.
- `purge_person` — canonical writer; удаляются собственные metadata/resources/session quota,
  исчезнувшие top-level documents действительно удаляются. Чужие жалобы сохраняются. Медиа
  удаляются только durable post-commit cleanup worker с lease/retry и проверкой surviving references.
  Удалённая identity не ломает последующие чужие publish/chat/group writes.
- Safety exit/purge выбирают допустимого преемника. Если такого нет, набор приостанавливается,
  owner освобождён и группа получает explicit recovery; бывший участник не остаётся управляющим.
  Участник может явно принять управление без возобновления набора/занятия нового слота.
- Synthetic-only backup/restore и exact canonical→legacy rollback rehearsal реализованы;
  stale legacy top-level keys не остаются. Никаких live options или activation side effects.
- Native parent-аудит выявил и устранил неверную copy истёкшего Preview, отсутствие статуса
  paused и resume. Resume восстанавливает исходный canonical payload внутри транзакции,
  не заменяет параметры placeholder-объектом. Quota recovery на самом Plus работает inline,
  без зависшего перехода на этот же экран; подтверждённый swap проверен в iOS.
- Отложенное уведомление о grant учитывает текущее server state: если пользователь вернулся
  после expiry, сообщает о завершении, а не о начале Preview. Ack/session guard сохранены.

## Writer inventory

Полный исполняемый перечень — `WRITERS` в `services/matching/monetization_commands.py`.
Транзакционно адаптированы:

- `save_intent`, `delete_intent`, search-command и старые `match/plan/confirm/expand`, Buddy `run_match`.
- `propose/respond/withdraw_request/archive_request`; `send_message/end_thread/message_react/message_delete/thread_mark_read`;
  `block_user/report_user`, inbox/outbox lazy expiry.
- `gi_create/invite/invite_many/respond/invite_cancel/close/report/approve/remove`, все role/takeover/convert/leave,
  `gi_post/gmsg_react/gmsg_delete`; `gp_*` и `mp_*` writes и их sweeps.
- Legacy `group_create/join/leave/recover`, `_expire_due`, `_gi_expire`, `_gi_roles_due`, `_gp_postcall_due`;
  report evidence metadata, admin notify/ban sweep/reset fatigue; feedback/outcome HTTP adapters,
  `purge_person` и durable cleanup.

В enforce остаются явно отклонёнными scaffold writers: `proposal_create`, `proposal_respond`,
`plan_resource`, `plan_transition`, `group_reserve`, `group_accept`, `group_release`,
`agent_transition`, `confirm_completion`, `_append_run_trace`, `_save_search`,
`_delete_saved_search`, `_migrate_identity_v2`; `form_group_from_slate` запрещён с reserve=true,
но read-only formation сохранён. HTTP negotiate/save/save_search/transition scaffolds также fail closed.
Это намеренный documented scope, а не поддержка этих старых writers в enforce.
`_log_proposal`, `_log_exposure`, `_idempotent`, `record_feedback`, `_record_outcome` допускаются
только внутри canonical transaction. AST test классифицирует все top-level `_save_store` callers
как adapted, blocked, transaction-only либо read projection; проверяет установленные wrappers.
Это статическое доказательство inventory текущего файла, не покрытие произвольных будущих писателей.
`_save_store` вне canonical transaction выбрасывает retryable error; JSON fallback отсутствует.
Import не создаёт схему. Startup identity rewrite не запускается в enforce.

## Execution tasks

Нумерация соответствует Execution в утверждённой спецификации; PARTIAL не означает приёмку.

| Task | Состояние handoff | Недостающее |
|---|---|---|
| 1 PG repository/schema | IMPLEMENTED, PG tests PASS, parent повтор PASS | formal review ещё не начат |
| 2 migration | IMPLEMENTED, synthetic tests PASS | только synthetic apply; live adapter не входит |
| 3 v2/flags/v1 | IMPLEMENTED, real loopback wire PASS | установленный старый native client не replayed |
| 4 command writers | IMPLEMENTED для mapped product paths, automated PASS; iOS chat end/resume/block/cancel-plan PASS | scaffold writes явно blocked; остальные native paths открыты |
| 5 expiry/витрины/links | IMPLEMENTED, automated PASS | native карты/витрины; event-end освобождение не требуется по решению 09.10 |
| 6 client contract/actions | IMPLEMENTED, durable reload/API tests/tsc PASS | физический process kill/back/gesture на устройствах |
| 7 entrypoints/media/role | IMPLEMENTED, synthetic media/role PASS; iOS recipient decline/free-slot/retry PASS | остальные screens, реальная запись/доставка media, native owner-picker и Android |
| 8 Plus/copy/accessibility | PARTIAL | native RU/EN/ES, large font, small screen, VoiceOver/TalkBack |
| 9 acceptance tests | PARTIAL | матрица ниже; full regressions остаются FAIL |
| 10 documentation | UPDATED | parent review и native acceptance ещё не завершены |

## Acceptance coverage

| IDs / сценарий | Фактическое доказательство | Статус |
|---|---|---|
| A01/A02 | real loopback HTTP bearer resolver, spoofed owner; client session/account-switch suites | PASS local synthetic |
| A03 | storage failure 503 без JSON; client unknown/late-response tests | PARTIAL, devices not checked |
| A04/A05 | draft без grant; publish, accept, pending→approve, waitlist promotion | PASS adapters; registration/KYC not replayed |
| A06/A07/A11/A12 | true PG, 2 OS processes, opposite messages, process death before commit, restart retry, exact duration, outbox recovery | PASS |
| A08 | legacy status-only audit, repeated identical migration, eligibility сохранена | PASS synthetic |
| A09/A10/A13 | common resource alias, Free group/search quota, pause payload, swap, old match HTTP; real ranker Buddy; hybrid future на двух feeds одним ID | PASS local synthetic; native not replayed |
| A14/A15/A16/A17/A18 | first/reply, opposite first, support/system excluded, voice/video gate, active-plan continuation; только end/block/nested report освобождают; cancel/decline/final leave/timeout/feedback/admin plan cancellation сохраняют session ID, initiator, history, chat_quota; late/replay после end/reopen безопасны | PASS automated; iOS end 503/success/resume/block/cancel-plan PASS; native media/Android остаются открыты |
| A19/A20 | expiry на server read/action, selected keep, stable-ID tie при одинаковом timestamp, no automatic restart; iOS keep→expiry и quota→confirmed swap | PASS automated + перечисленный iOS fixture flow |
| A21/A22 | pending invite survives pause, new invite/join denied, old waitlist admitted, обе map feeds/explore скрывают paused; cached ready replay sanitised | PASS automated; native rendering pending |
| A23/A24 | protected resource/action, malicious foreign/paused refs, historical plan/session provenance, terminal migration no guess, past-plan reopening не обходит квоту, rollback role/roster | PASS automated |
| organizer manual/auto | full-slot refusal and retry, vote rejects quota, eligible heir, owner vacancy+paused recovery, purge and subsequent foreign writes | PASS adapters; iOS recipient quota→decline и quota→own pause→retry PASS; owner-picker проверен JS/API, не native |
| A33/A34 | Plus/action/copy RU/EN/ES tests и TS; iOS RU invite→notice→Preview→Plus→keep→expiry→quota→confirmed swap | PARTIAL; Android, large font, VoiceOver/TalkBack, native EN/ES и остальные entrypoints не проверены |
| A35 | v1 15 tests; real old match+group HTTP gate; v2 notice/keeper validation; unsupported scaffolds fail closed | PASS automated; full installed-client compatibility not checked |
| A36 | real nonempty core ranking/policy in off/shadow/enforce Free/Preview, labels/retrieval/pilot, plan/confirm/expand/group contract; real serving age gate denied identically Free/Preview | PASS synthetic policy cases; no live KYC/provider acceptance claimed |
| A37 | default off, shadow rollback/audit, synthetic migration guards, backup/restore roundtrip, exact canonical→legacy replacement with stale-key removal | PASS synthetic; live rollback remains unauthorised |

## Проверки и окружение

- Python: `.codex/phase2-venv/bin/python`, isolated venv with psycopg; shared node_modules link
  не переустанавливался и не изменялся.
- Docker `kleal-monetization-phase2a-tests`, `postgres:17-alpine`, host bind только
  `127.0.0.1:55439`, DB `kleal_monetization_test_phase2a`. Каждый тест создаёт/удаляет отдельную
  `test_<uuid>` schema; никаких живых аккаунтов/БД. Контейнер оставлен для parent review.
- `KLEAL_MONETIZATION_TEST_DSN=postgresql://kleal_test:local_synthetic_only@127.0.0.1:55439/kleal_monetization_test_phase2a .codex/phase2-venv/bin/python -m unittest discover -s kleal-ms/tests -p 'test_monetization*.py' -v`:
  **70 PASS**, 12.327s после изменения end/block-only, включая новые chat lifecycle регрессии
  и canonical resume payload/quota/swap/replay. До изменения две новые проверки воспроизвели
  дефект: все семь terminal callbacks освобождали слот, старый confirmed план обходил квоту
  после end. Parent независимо повторил актуальные **70 tests: PASS, 12.742s**,
  включая расширенную проверку новой block при связанном active plan, unblock/reopen и replay
  прежней block. Credentials здесь только disposable local Docker fixture.
- `node kleal-app/tools/monetization_test.js`: **11 PASS**, включая server-state copy и active/expired-unacked notices RU/EN/ES;
  `monetization_actions_test.js`: **PASS** (session, safe persisted metadata, simulated module/process reload,
  account isolation, swap, cancel/abort, duplicate resume, production API wrapper double click/lost-response retry).
- `identity_test.js`: **25 PASS**, `session_test.js`: **6 PASS**, `account_switch_test.js`:
  **6 PASS**, `ginvites_closed_test.js`: **13 PASS**. Backend identity suite: **25 PASS**.
- `tsc --noEmit --project kleal-app/tsconfig.json`: **PASS**. Parent повторил актуальные
  11 client tests, actions suite и TypeScript после end/block-only: **PASS**.
- Expo native export iOS/Android: **PASS**, `.codex/phase2-export-revision`, log
  `.codex/phase2-export-revision.log`. Export не является native acceptance.
- `git diff --check`: **PASS**.
- Required `regressions_test.js`: **FAIL** на трёх прежних interest-normalization assertions.
  Это повторено в итерации end/block-only; обычный runner прекращается на этих трёх проверках.
  В прежней итерации остаток выполнен диагностическим AST block runner, без ослабления исходных
  unrelated assertions. Baseline d633 и тот snapshot: одинаковые **58 failing labels**
  (3 imported interest + 55 main), новых/устранённых нет. Полный диагностический прогон сейчас не повторялся.
  В каждом 6 одинаковых block exceptions: imported interest, TS export/import parsing, missing
  `InterestChips.tsx`, `isOther` undefined, TS colon. Это не PASS полного suite.
  Логи `.codex/phase2-revision-regressions.log`, `phase2-regressions-baseline.log`, `phase2-revision-regressions-complete.log`.
- iOS: `QA Kleal SDK57`, iOS 26.5, Expo Go 57, Xcode Device Hub. Parent прошёл руками через UI:
  synthetic sign-in → group invite → предварительное пояснение → accept → однократный Preview
  → Plus → выбор сохраняемого поиска → expiry → refusal занятого слота → confirmed swap.
  После swap wire status подтвердил ровно один активный поиск; старый paused, новый active.
  Поиски и ускоренное expiry подготовлены локальным API, не через мастер и не ожиданием 14 дней.
  Synthetic server на 7599 использовал real PG commands, но stub auth/ranking/policy; это не
  real registration/KYC и не production. Saved-plan continuation и media не пройдены native.
  Screenshot evidence: `.codex/phase2-native-qa/ios-preview-active.png`,
  `.codex/phase2-native-qa/ios-expiry-swap-verified.png` (экраны визуально проверены).
  Исправление expired-unacked alert после этого проверено JS/TS, без отдельного native rerun.
  Android SDK/adb в доступных стандартных путях отсутствует; Android native **BLOCKED**.
  VoiceOver/TalkBack, малый экран и Dynamic Type не проверены.

## Остаточные риски и release gate

1. Parent полностью прочитал staged diff `/tmp/kleal-phase2a-chat-policy.m9So0k` (4781 строк)
   и независимо повторил актуальные backend/client проверки; формальный BMAD review
   ещё не начат, поскольку step-03 acceptance неполон. AST inventory/current adapters закрыты
   автоматическими tests, но это не разрешение включить enforcement; scaffold writers перечислены выше.
   Native account-delete orchestration/auth logout и запись реального media не replayed.
   Точечная автоматическая приёмка нового правила «только end/block» закрыта; это не закрытие
   общей native-приёмки 2A. Общий regressions runner повторно остановился на трёх прежних
   interest-normalization assertions. Документация синхронизирована с новым решением пользователя.
2. Canonical adapter сериализует document projection глобальным PG advisory lock и процессным RLock.
   Ranking не держит PG-lock, но HTTP guard держит process lock. Нужны нагрузочная проверка и
   дальнейшее дробление projection; этот handoff не заявляет production-scale readiness.
3. Решение пользователя от 09.10 заменило прежнее end/block/event-end/cancel на end/block-only.
   Отдельный event-end источник больше не требуется. На real PG проверены сохранение сессии,
   initiator, history и quota при всех mapped terminal transitions, времени и post-plan feedback;
   end/block replay не закрывает новую сессию. Native iOS повтор базового chat flow выполнен
   09.10 (отчёт ниже); replay, все terminal callbacks и media остаются только automated coverage.
   Admin ban продолжает менять safety/plan state, отмена плана не выдаёт коммерческую квоту;
   удаление аккаунта остаётся отдельным canonical cleanup и проверено прежним purge suite.
4. Safety exit/recovery не назначают сверх квоты и не оставляют вышедшего owner; native отображение
   recovery и предложение другого организатора требуют UX acceptance.
5. Hardware back/gesture/focus cleanup и process-death metadata проверены кодом/JS tests, не настоящим
   убийством iOS/Android процесса. Возможности Expo runtime/AsyncStorage и физические gestures
   нельзя считать подтверждёнными одним bundle export.
6. Основные transaction fixtures намеренно изолируют policy/ranking, а отдельные tests включают
   настоящий ranker/policy и serving KYC gate с synthetic users/declined record. Это не live KYC,
   не доказательство всех provider states и не native acceptance. Весь 2A не завершён.
7. Обнаружен существующий corner case `_online_fallback`: hybrid intent с `title=None` и пустой
   выдачей может оставить launch pending из-за конкатенации строки с None. В 2A mini-fix не менялся;
   не следует выдавать такой pending за успешно готовую выдачу. Нужна отдельная regression/fix.
8. Native QA 09.10 воспроизвёл несогласованность архива: после возобновления переписки сервер
   создаёт новую активную сессию и учитывает слот, но список продолжает показывать «Только чтение».
   Нужны синхронизация состояния списка с сервером и понятное действие возобновления; в QA-turn
   продуктовый код не исправлялся. Не объявлять UI полностью принятым.

## Дополнительный native QA: chat-slot policy, 09.10.2026

Проверена локальная ветка `codex/monetization-phase2a`: baseline
`d633bb7541f97c69690203fe44c8c47f13002e76` плюс текущие staged-изменения (не новый релиз).
Эмулятор `QA Kleal SDK57`, iOS 26.5, Expo Go 57. Все действия ниже выполнены через native UI;
результат независимо сверен с реальными PostgreSQL session/quota/documents.

Стенд: только loopback API 7599 и Metro 8088, отдельная schema
`test_6e8942268ef44690a604358ca9e5eb3d`. Аккаунты a/b/c полностью синтетические;
auth, профили, ranking и policy — fixture. Начальное знакомство/принятые приглашения,
истёкший Preview и подтверждённые планы подготовлены тестовыми данными.
Production, KYC, платежи и продуктовые исходники в этом QA-turn не менялись.

| Сценарий | Native действие и проверенный результат | Итог |
|---|---|---|
| Первый инициативный чат Free | Сообщение QA B доставлено, новая session active, initiatedChats 0→1 | PASS |
| Отмена встречи | В плане нажаты «Отменить план» и подтверждение; plan=cancelled, прежняя session и initiator сохранены, quota=1 | PASS |
| Переписка после отмены | Сообщение доставлено с галочкой, история сохранена, та же session, quota=1 | PASS |
| Второй инициативный чат | Отправка QA C открыла quota sheet; ни сообщения, ни новой session в БД нет; после «Не сейчас» локальная реплика помечена неотправленной | PASS |
| Явное завершение | «Действия с разговором» → «Завершить чат»; после undo-таймера session=closed, quota 1→0, история доступна в архиве | PASS |
| Использование свободного слота | Новое сообщение QA C успешно доставлено, новая session, quota 0→1 | PASS |
| Блокировка | Профиль QA C → «Заблокировать»; blocks[a]=[c], session=closed, quota 1→0. Попытка нового сообщения отклонена, UI объяснил блокировку, сообщение не записано | PASS |
| Возобновление старого чата | Из архива QA B отправлено новое сообщение; сервер создал новую session, quota 0→1, старая session осталась closed | PASS backend; FAIL UI-состояние архива |
| Окончание встречи и post-plan | Время плана ускорено на fixture до now−2h. В UI дан ответ «Да, встретились» и оценка; ответ второго участника подан тестовым API. Plan=done; новая session QA B всё ещё active, quota=1; ещё одно сообщение доставлено | PASS в ускоренном fixture, не реальное ожидание |
| Точка входа Plus | Профиль → Настройки → Kleal Plus. Отображаются «Preview завершён · Free», правила Free и «Без оплаты» | PASS |

### Найденный дефект UI — P2

1. Завершить чат QA B, затем открыть его в разделе «Архив / Только чтение».
2. Поле ввода активно; при свободной квоте сообщение отправляется и создаёт новую сессию.
3. Вернуться в «Личные»: QA B остаётся в архиве с подписью «Только чтение», хотя сообщение
   доставлено и бесплатный слот уже занят.

Это не обход квоты: БД корректно учитывает новую инициативу. Проблема в ложной подписи и
несинхронизированном состоянии списка. В исходниках `conversation.tsx` завершение добавляет
локальную archived-пометку, успешная отправка её не снимает, а `messages.tsx` помечает все
архивные строки как read-only. Рекомендуемое исправление: явное возобновление с проверкой
квоты, после успешного ответа сервера обновлять список; историю не удалять.

Дополнительное UX-наблюдение: после блокировки композер остаётся доступен; сообщение
надёжно отклоняется сервером и отображается объяснение, но до отправки состояние не видно.
Это не PASS запрета ввода и не обнаруженный обход блокировки.

### Доказательства и границы

Артефакты в `.codex/phase2-native-qa/20261009-chat-policy/`:
`01-plan-cancelled.png`, `02-chat-after-cancel.png`, `03-second-chat-quota.png`,
`04-ended-chat-history.png`, `05-blocked-message.png`, `06-archive-readonly-label.png`,
`07-reopened-chat-still-archived.png`, `08-plus-free-screen.png`.

БД: первая a/b session `session_f8994115bf8e4ba9b9246bce5ce7d260` сохранена после cancel,
закрыта только explicit end. a/c session `session_be31107e8df14a01907000600fc3e947`
закрыта block. Новая a/b session `session_bc22142367ca48fcb85713475f5b358e` осталась active
после plan `mp_1791575663522_9abe6d` → done. Итоговая quota=1, пять человеческих сообщений;
обе отклонённые попытки в БД отсутствуют.

Не проверены этим native-прогоном: Android (нет SDK/adb), физические устройства,
организатор/recovery, запись голоса/кружка, параллельные клиенты и replay через UI,
отмена undo, реальные сетевые сбои, kill/relaunch, VoiceOver, Dynamic Type, EN/ES.
Ранее пройденные automated tests в этом turn заново не запускались; результат выше
добавляет native evidence, но не заменяет остальные release gates и не означает готовность
всего 2A к production.

После QA остановлены только созданные для этого прогона API, Metro и loopback bridge.
Порты 7599/8088 свободны; teardown удалил только указанную disposable schema
(information_schema подтвердил count=0). Docker-контейнер и остальные рабочие процессы
не трогались. Синтетические данные воспроизводятся fixture; скриншоты и отчёт сохранены.

## Flags, migration и rollback

Default `off` оставляет legacy поведение. `shadow` сохраняет продуктовый legacy результат,
а решения квоты проверяет в откатываемой PG-транзакции, после чего пишет audit.
`enforce` требует `KLEAL_DB=postgres` (не `mirror`), явную миграцию и ready marker.
Пример **только synthetic**: `KLEAL_PG_DSN=<loopback kleal_monetization_test DB> python
kleal-ms/tools/monetization_migrate.py fixture.json --schema test_fixture --apply`;
`test_fixture` оператор заранее создаёт в изолированной test DB. CLI не создаёт
schema, не выбирает `public` и отклоняет отсутствующую schema. Без `--apply` это
dry-run без подключения; `--schema` для dry-run необязателен. После review 17.10
общий guard проверяет actual libpq loopback peer, exact test DB/schema и запрещает
hostaddr/service/multihost DSN/environment overrides; production importer отдельный.

**Не переключать работающий enforce→off вслепую:** legacy store отстаёт от canonical documents.
Безопасный будущий rollback требует stop gated writes, backup PG, validated export canonical
projection в legacy snapshot, проверку владельцев/alias/session obligations и только затем
переключение режима. `tools/monetization_rehearse.py` выполняет это только для loopback
`kleal_monetization_test*` DB и точной `test_*` schema; backup требует synthetic migration marker,
restore — пустую schema и checksum. Backup снимок берётся одним MVCC statement. Rehearsal
обновляет expiry, полностью синхронизирует legacy store, проверяет equality и не меняет flags.
CLI: `.../python kleal-ms/tools/monetization_rehearse.py backup --schema test_<id> --file <new.json>`;
`restore --schema test_<empty_id> --file <snapshot.json>`; `rollback-rehearsal --schema test_<id>`.
DSN только через `KLEAL_MONETIZATION_TEST_DSN`; нет live option. PG/audit не удалять. Live
migration/activation/rollback остаются отдельным разрешением пользователя.

## Native QA follow-up: исправление состояния чата, 11.10.2026

Локальная реализация follow-up в том же worktree; прежние staged-изменения сохранены.
Это исправление найденного 09.10 дефекта, не завершение всей приёмки 2A.

- `thread` и строки `threads` получили additive `chat`: `peerId`, `state`
  (`new/active/closed/legacy`), текущий активный `sessionId` либо `null`, `blocked`,
  дробное `serverTime` PostgreSQL. Чтение не создаёт сессию/слот. В enforce состояние
  читается из `monetization_sessions`, блокировка — из canonical `_blocks` обеих сторон.
  Инициатор и чужие quota IDs наружу не добавлены. Старые закрытые сессии с одинаковым
  секундным `opened` не сортируются как будто их порядок известен: у закрытой пары
  текущей активной сессии нет, поэтому `sessionId=null`. Off/shadow возвращает `legacy`.
- Завершение больше не архивирует оптимистично и не уводит с экрана при ошибке.
  UI ждёт ответ сервера и перечитывает состояние; неопределённый результат повторяется
  с тем же command key. При success показывается сохранённая история закрытого чата;
  при отказе остаются действующий чат и ошибка. Undo-таймер сохранён.
- «Написать снова» открывает композер с пояснением проверки слота. Само нажатие не пишет
  на сервер. После успешной доставки требуется свежий canonical read: лишь active
  состояние возвращает диалог из архива. Старый replay receipt, отказ квоты, отмена
  quota sheet и ошибка сети не объявляются возобновлением.
- Все локальные chat evidence и новые строки списка адресуются по `users.id`;
  ответы из другого аккаунта, unmount и более старые snapshots отбрасываются.
  Поздний callback записи после смены аккаунта/unmount не отправляет сообщение новым токеном.
  Неоднозначные старые пометки по имени не применяются к строкам с известным ID.
  Parent native-повтор дополнительно выявил accepted-intent строку без `whoId`:
  исправлены и её ID/key/dedup, и сопоставление живых/прошлых планов по ID. Behavioral
  regression проверяет одинаковую пару во вкладках «Интенты»/«Личные» и независимость тёзок.
- «Архив» больше не называется «Только чтение» автоматически. Закрытый чат и блокировка
  получают свои подписи; локальная ручная архивация остаётся настройкой списка.
  Из меню закрытого чата открывается история/возобновление, а не ложное локальное снятие
  server-closed состояния. Подтверждённая блокировка отключает текст, voice и video.
- Добавлены RU/EN/ES объяснения закрытия, возобновления, блокировки и ошибки состояния.

Проверено implementer:

- Backend `test_monetization*.py`: **71 PASS, 12.422s**, настоящий isolated PostgreSQL,
  включая новое чтение lifecycle через thread route, отсутствие слота при открытии,
  end→quota refusal→resume, old message/end replay, обе стороны block/unblock, список
  диалогов, сохранение истории и off compatibility. Все данные синтетические.
- Новый `tools/chat_lifecycle_test.js`: **PASS** — исполняемые state/list функции,
  одноимённые ID, account switch, stale responses, отказ/закрытие/replay, ручной архив,
  копия RU/EN/ES.
- Новый `tools/conversation_lifecycle_test.js`: **PASS** — реальные обработчики экрана
  в JS hook harness: explicit resume, quota/network refusal, delivery, end 503/retry,
  подтверждённое закрытие, disabled text/voice/video, поздние callbacks. Native компоненты
  заменены test doubles; это не native/gesture/запись настоящего медиа.
- `monetization_test.js` **11 PASS**, actions **PASS**, identity **25 PASS**, session
  **6 PASS**, account-switch **6 PASS**, ginvites-closed **13 PASS**, TypeScript **PASS**.
- После последнего accepted-intent исправления повторены обе новые client suites и
  TypeScript: **PASS**. Свежие Expo exports iOS/Android: **PASS**, каталоги
  `.codex/phase2-chat-followup-export-ios` и `.codex/phase2-chat-followup-export-android`.
  Это проверка bundle/типов, не Android native acceptance.
- Required `regressions_test.js` снова **FAIL** на прежних трёх interest-normalization
  assertions; unrelated tests не ослаблены. Старый end-chat name-regex в этом runner
  заменён behavioral conversation regression. Сам общий runner до этого блока не дошёл.
- `git diff --check`: **PASS**. Свежий native iOS прогон и прочая acceptance выполняются
  отдельно parent; этот раздел не выдаёт их за завершённые. Android native и остальные
  ранее перечисленные ограничения остаются открытыми. Production/payment/KYC changes нет.

## Native QA follow-up: recovery квоты организатора, 11.10.2026

Исправление native finding из Implementation Notes spec: общий alert называл отмену
«Выбрать другого организатора», а `grole` затем показывал обычную ошибку. Политика квоты
и серверные права не изменены; чатовые product-файлы из предыдущего follow-up не менялись.

- `src/api.ts` передаёт `organizer_search_quota` в контекстный обработчик экрана роли.
  Это лишь presentation hook: тот же серверный gate, persisted command key и retry.
  Глобальный fallback честно называет отмену отменой, без обещания назначения owner.
- Получателю Free доступны «Освободить слот» и «Оставить выбор организатору».
  Первый путь открывает Plus с исходным действием; после паузы **своего** поиска
  явный повтор использует прежний command key. Второй открывает существующее подтверждение
  отказа от роли: только после подтверждения отправляется `accept:false`.
  До успешного server handoff владелец не меняется. Кандидат не получает picker/owner APIs.
- Текущему организатору не предлагается освобождать чужой слот через собственный Plus.
  Выбор другого открывает подтверждение закрытия текущего предложения/голосования,
  после успешного server ответа — действующий picker. Перед командой заново читаются права.
- Recovery проверяет `owner_id`, `to_id`, `by_id`, session/gid и unmount. Поздний ответ,
  alert callback старого аккаунта или смена owner на другом устройстве не открывает picker
  и не отправляет старую команду новым токеном. UI отмена/возврат из Plus не выдаётся за
  сетевую ошибку; настоящая ошибка остаётся видимой.
- Список следующего кандидата, исключение отказавшихся и выбранная строка используют ID
  (`declined_ids`), поэтому одноимённые участники не исчезают из выбора. Copy RU/EN/ES
  хранится в `src/roles.ts`.

Проверено implementer (только локально):

- Новый `tools/role_quota_recovery_test.js`: **PASS**. Выполняет реальные обработчики
  `grole`, production API wrapper и durable-return механизм с подменённым `fetch`/native UI.
  Покрывает три языка, quota→подтверждённый отказ→выбор другим owner ID, отмену alert/Plus,
  quota/503/success одного retry key, сохранение owner, отсутствие прав кандидата,
  смену owner между alert и подтверждением, session switch и unmount. Это не native QA.
- Backend `test_monetization*.py`: **72 PASS, 12.319s**, synthetic isolated PostgreSQL.
  Новый тест проверяет запрет candidate→offer/back, отказ без изменения ресурсов/состава,
  открытый поиск кандидата, прежнего owner и последующий успешный выбор другого участника.
  Существующий тест quota→освобождение своего слота→повтор также PASS.
- TypeScript, monetization (**11**), actions, identity (**25**), session (**6**),
  account-switch (**6**), ginvites-closed (**13**), chat-lifecycle и conversation-lifecycle:
  **PASS**. `git diff --check`: **PASS**.
- Expo exports: **PASS** iOS `.codex/phase2-organizer-recovery-export-ios`
  (`entry-3ab78c996b8387533a21487ce229f6ab.hbc`) и Android
  `.codex/phase2-organizer-recovery-export-android`
  (`entry-095c22e09addabb8444be35ce66ff897.hbc`). Export не заменяет native acceptance.
- Required `tools/regressions_test.js`: прежние **3 FAIL** interest-normalization,
  unrelated assertions не изменялись; runner останавливается до остальных разделов.

Product freeze передан parent для свежего iOS прогона. Fixture/эмулятор implementer
не трогал. Android native, formal review и оставшиеся общие gates 2A не объявлены PASS.
Ни commit, ни push/deploy, ни платежи, ни изменения KYC не выполнялись.

## Независимая проверка parent, 11.10.2026

На свежем bundle текущего worktree, **iOS 26.5 / Expo Go SDK 57**. API только
`127.0.0.1:7599`, настоящий isolated PostgreSQL, синтетические аккаунты A/B/C/D;
auth/профили и внешние parsing/ranking части подменены fixture. Это не production E2E.

| Проверка в эмуляторе | Результат и серверное подтверждение |
|---|---|
| End chat с принудительным HTTP 503 | PASS: видимая ошибка, прежняя active session и quota=1, без ложного архива |
| Подтверждённый End chat | PASS: closed session, quota=0, история сохранена |
| «Написать снова» без отправки | PASS: слот не занят; пояснение о проверке квоты |
| Отправка после End chat | PASS: новая active session, quota=1; «Чат возобновлён», нет ложного архива во вкладках «Личные» и «Интенты» |
| Блокировка | PASS: закрывает session, quota=0, disabled text/video UI; voice disabled подтверждён behavioral test, запись не выполнялась |
| Отмена согласованной встречи | PASS: план cancelled, session `session_5b35d6684ae946b3b00ea3e7b8e8dd84` остаётся active с initiator A, quota=1; новое сообщение успешно доставлено |
| Занятый слот получателя роли | PASS: 409 не меняет owner B, roster или поиск A |
| «Оставить выбор организатору» | PASS: реальное подтверждение отказа, затем declined; owner B, участники и активный собственный поиск A сохранены; generic error отсутствует |
| «Освободить слот» → Plus | PASS: пауза только поиска A, usage.activeSearches=0; предложение всё ещё open, owner B |
| «Продолжить исходное действие» | PASS: accepted, owner A; группа становится единственным активным поиском A, собственный прежний поиск paused; roster не изменился |

Полный набор backend повторён parent после organizer freeze: **72 PASS, 12.899s**.
Независимо повторены `chat_lifecycle_test.js`, `conversation_lifecycle_test.js`,
`role_quota_recovery_test.js`, monetization (11), actions, TypeScript: **PASS**.
Общий `regressions_test.js` повторён: **те же 3 FAIL** interest-normalization,
ранний выход до остальных разделов. Это не зелёный полный suite.

Доказательства: `.codex/phase2-native-qa/20261011-chat-fix/` в этом worktree:
`01-end-server-error.png`, `02-chat-ended.png`, `03-chat-resumed.png`,
`04-active-not-archived.png`, `05-blocked-composer.png`,
`06-organizer-quota.png`, `07-organizer-cancel-bug-before.png`,
`08-plan-cancel-chat-preserved.png`, `09-organizer-quota-fixed.png`,
`10-organizer-decline-confirmation.png`, `11-organizer-transfer-success.png`.
До исправления organizer recovery дефект воспроизведён parent, после — повторены оба выхода.

Следующая открытая приёмка 2A: native media, Android, VoiceOver/TalkBack,
Dynamic Type/малый экран, native EN/ES, остальные entrypoints/карты и process-kill/retry.
Formal BMAD review не начат до закрытия этих gates. Платежи и production не активированы.

Owned Metro, loopback bridge и native fixture остановлены после проверки. Disposable
schema `test_b86ac5e45a4444c0b9b7bdd119acfe75` удалена штатным tearDown;
`information_schema` подтвердил count=0, listeners 7599/8088 отсутствуют. Синтетические
данные воспроизводятся fixture; скриншоты сохранены. PostgreSQL container и чужие
процессы/сервисы не трогались. Основной checkout product-файлов не изменён.

## Completion handoff, 12.10.2026 — fallback, regressions, load

Работа в том же `codex/monetization-phase2a` worktree, база `d633bb7`; прежний staged
delta сохранён. Это **не** полная приёмка 2A. Native/exports/formal review/commit
переданы parent; Android full-flow отложен пользователем. Production, платежи,
KYC admission, emulator, Metro и native fixture implementer не трогал.

### Исправленный продуктовый delta

- `_online_fallback`: отсутствующий или `null` title даёт `Live room: meet`, не
  TypeError/вечный pending. Новый PostgreSQL regression сначала RED в обоих случаях,
  после исправления ready + empty candidates + unapproved room + точный replay PASS.
- Интересы: прежний ключ удаляется только после успешного canonical confirmation;
  unknown не попадает в `justAdded` раньше квитанции. Cancel, duplicate, network,
  rejected сохраняют прежнее. После confirmation изменения отправляются серверу.
  Known labels из ответа сохранены; непроверенные novel labels в общий кэш не идут.
- После каждого await normalize/confirm/interestsChat проверяются исходная session
  и mount. Delayed response старого аккаунта не меняет новый профиль/кэш/список.
- `profileForAttach` клонирует interests и убирает confirmations; register и
  локальный draft сохраняют квитанции. Тип `Profile.interests` теперь описывает их.
- R02: восстановлен утверждённый leaf+parents контракт при завершении выбора карты.
  `interestChain` использует только пути общего generated registry, не соседей;
  неизвестным словам не назначает категорию, неоднозначные `more` не наследуются.
  Для padel записывается sports/racket/padel. Корзина `mapPicked`, `justAdded`,
  реплика агенту и финальный счётчик остаются по выбранным ключам; минимум 3 на
  карте по-прежнему проверяет `mapPicked`, а не длину matching expansion.

### Проверки и точные команды

Команды ниже из корня worktree. В этой сессии использовались:

```sh
NODE=/Users/ivan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node
PY=.codex/phase2-venv/bin/python
export KLEAL_MONETIZATION_TEST_DSN=postgresql://kleal_test:local_synthetic_only@127.0.0.1:55439/kleal_monetization_test_phase2a
$PY -m unittest discover -s kleal-ms/tests -p 'test_monetization*.py' -v
$NODE kleal-app/node_modules/typescript/bin/tsc --noEmit --project kleal-app/tsconfig.json
$NODE kleal-app/tools/regressions_test.js
$NODE kleal-app/tools/interest_confirmation_test.js
$NODE kleal-app/tools/interest_hierarchy_test.js --json | $PY kleal-ms/tools/interest_hierarchy_check.py
$NODE kleal-app/tools/regression_contracts_test.js
for test in monetization_test monetization_actions_test identity_test session_test account_switch_test ginvites_closed_test chat_lifecycle_test conversation_lifecycle_test role_quota_recovery_test; do
  $NODE "kleal-app/tools/${test}.js" || exit
done
git diff --check
```

- Backend: **73 PASS, 12.516s**, настоящие транзакции isolated PostgreSQL. После
  fallback fix старый retry-тест стал доходить до готового ranking: Python tuples
  против JSON arrays давали ложный FAIL. Теперь сравнивается весь JSON-wire payload,
  без удаления полей или ослабления равенства replay.
- TypeScript и diff whitespace: **PASS**.
- Полный ordinary regressions runner достигает последнего раздела: **647 строк
  `ok`, 1 FAIL R01** плюс встроенные behavioral suites. Это НЕ зелёный suite.
  Диагностический bypass `.codex/run-regressions-complete.cjs` не используется
  как доказательство PASS; ранние предварительные зелёные прогоны superseded аудитом R01.
- Monetization **11**, identity **25**, session **6**, account-switch **6**,
  ginvites-closed **13**, actions/lifecycle/conversation/role-recovery suites: **PASS**.
- Новые confirmation tests: known/labels, ready/clarify/cancel, network/rejected/
  duplicate, atomic replacement/delivery, 10 delayed session/unmount cases,
  receipt isolation: **PASS**. Новые UI contracts: **8 PASS**, исполняют реальные
  функции/JSX с synthetic UI; это не native rendering/gesture acceptance.
- R02 RED→GREEN: реальный `onMapDone` и `finishHobbies` проверены для padel,
  padel+tennis, sports/music/outdoors и unknown; dedupe, выбранные листья отдельно.
  JSON результата handler передан настоящим `trusted_interest` и `app.topical`:
  sports/racket/padel находятся, unrelated games не совпадает. **PASS**.
- Python `gplan_screen_smoke.frame_of` приведён к frontend matrix, включая hold,
  feedback, started; фактический серверный smoke по HTTP в этом handoff не запускался.

Логи: `.codex/phase2-completion-backend.log`, `-tsc.log`, `-regressions.log`,
`-client.log`, `-hierarchy.log`; отдельные load JSON ниже. Здесь префикс каждого
сокращённого имени — `.codex/phase2-completion`.

### Старое ожидание → основание → новая исполняемая проверка

В таблице `R` = `kleal-app/tools/regressions_test.js`, `C` = новый
`regression_contracts_test.js`, `I` = новый `interest_confirmation_test.js`,
`H` = новый `interest_hierarchy_test.js`. «Source assertion» означает исполняемую
проверку исходника, **не** поведенческий/native PASS. Ниже учтены также изменения
синтаксиса прежнего harness, чтобы не скрыть смену требований за regex.

| Старый тест/ожидание | Подтверждённое поведение/основание | Проверка теперь |
|---|---|---|
| queueInterestProposals; confirmInterestProposal/closeInterestProposal | cc958d5 убрал подборщик ради разговора; baseline chat документирует auto-ready, выбор только при clarify; граница серверного confirmation сохранена | I: ready/clarify/confirm/skip, failure, замена только после receipt; source routes в interest_normalization_test |
| confirmations не прикрепляются к профилю | Старое требование сохранено, найден реальный defect | I исполняет profileForAttach/Register, проверяет неизменность draft |
| «Все настройки профиля» ожидал disabled onPress ternary | Переход по-прежнему только после register; GlassPill принимает busy | R проверяет GlassPill busy/onPress и destination guarded handler |
| Python frame_of совпадает с frontend набором (включая fix) | Новый baseline добавил hold/feedback/now; can_fix теперь часть proposed, но утрата Give time не признана нормой | Python port + R parity; C matrix из 18 случаев; R01 отдельно ниже |
| LOCK=-56, CANCEL=-80 | Смысл старого теста — cancel дальше lock, не неизменность пикселей | R численно сравнивает абсолютные пороги |
| haloOpacity/haloScale; translateX:back | Громкость ведёт ореол, waveform движется transform; shared values перенесены на UI thread | R voice.level→haloStyle→scale, waveform translateX и запрет width-percent |
| чужое audio всегда pre-download | Baseline voice и matching теперь поддерживают Range/streaming, download остался fallback; не меняется требование проигрывания чужого файла | R проверяет Asset.downloadAsync и fallback/source; native media оставлено parent, regex не доказывает playback |
| clamp строкой; cancelling ? 0 : hintX | Та же граница движения в Reanimated Extrapolation.CLAMP/cancelHint | C исполняет hintStyle на -500/-79/-10/100 и cancel 0/1 |
| retry agent.message(me,other,...cid) | AGENTS/IDENTITY: Peer={name,id}, тот же cid | R peer + cid; identity 25 и conversation/lifecycle suites |
| пузырь mid radius ровно 18 | Смысл — хвост только в конце серии | R actual tail selector и tail radius < mid radius |
| удалить своё по lowercased name | Требование identity из AGENTS: namesake не владелец | R isMe(from,from_id); identity 25 |
| belowTitle без различия owner/participant | План остаётся на паузе; baseline различает owner below/participant onHold | R обе подписи; C pause recovery actions |
| rounds_used_up всегда null для secondary | Сервер can_fix разрешает owner закрепить на последнем раунде; запрещено новое предложение, не Fix | C исчерпание/owner fix/participant no-fix; R RoundBar в форме |
| «дать ещё время» → прежний onMoreTime | debbbf3 и board_intent_3374 GR.30 подтверждают action/no navigation; новый baseline его потерял | **Сохранён FAIL R01**, не заменён voteDecide |
| setAsk1to1 непосредственно onPress | То же открытие consent sheet, после закрытия меню | R setTimeout→setAsk1to1 и прежние checks pending/confirm/respond |
| parseName вручную стирал 3 TypeScript annotations | Функция экспортирована, ручной stripper падал до cases | TS transpiler; прежние реальные parseName CASES без смены ожиданий |
| labelOf вырезал литерал N из interests-wheel | d633: дерево generated из shared registry | Настоящие TS modules и прежние RU/EN key-label cases |
| все sys-коды только c=== в groups.ts; вызов с m.sys inline | Decoder распределён groups.ts + group.tsx switch; f=m.sys | R объединяет обе таблицы, checks передачи f и legacy fallback сохранены |
| inline _mp_frozen для counter/accept_change/reject_change | Смысл freeze сохранён, правила вынесены mplan_rules | R _mp_refusal и frozen=false у трёх Rule, остальные guards сохранены |
| peerLocalTime без dateLocale dependency | Функция теперь локализует время; 6 прежних ожидаемых результатов неизменны | Harness передаёт dateLocale, исполняет ту же функцию |
| plans(me,other); with=...; tz_by_name | AGENTS требует ID, timezone человека нельзя резолвить по имени | R otherPeer/peerQuery/_tz_of обе ручки + identity suite |
| planReachable=canPlan\|\|plan | Archived/readOnly не должен давать action; phase2A lifecycle | R !readOnly и прежний переход в gplan; lifecycle suites |
| imLateSent меняет label | Повтор статуса по-прежнему запрещён; новый UI оставляет Open chat | C фактический ActionsFor locked+imLateSent содержит только Open chat |
| story suggest.filter(...).map | Выбираются только picked, затем server confirmation | R chosen filter/loop/confirmInterest, backend receipt boundary checks сохранены |
| группа: setInfo sheet; topic/time/place/size; interestLabels topics | Baseline gmembers header фиксирует GR.24: отдельная страница с карточкой затеи прежде roster | R actual openInfo→gmembers, порядок card/rows, title/splitWhen/groupPlace/whoNote; native переход не объявлен проверенным |
| ChatShell [s.bub,s.bubMe] exact JSX | Человек остаётся пузырём, агент Markdown | R m.who==='me' и bubMe; Markdown side сохранён |
| Buddy !shown boolean | f9b061b: shown номер строки, чтобы ответ не перезаписал реплику человека | C finish с shown=0 не дублирует, replaceShown того же индекса |
| план снимает streaming reply | Baseline buddy история дефекта «не успел дописать, вылез попап»: вопрос не перебивается, текст остаётся | C question не открывает sheet, ready proposal сохраняет ответ |
| match body {intent,profile,ctx,limit} | Тот же limit с добавленным lang | R limit+lang; прежние has_more/8/page/showMore assertions сохранены |
| trailing offer guard без not _own_ask | Явная просьба выделена, старый запрет попапа над встречным предложением сохранён | R полное guard condition, прежние real stream cases сохранены |
| 9 Caret/FADE checks (inline glyph/tail/list/table-code/fade/last-part/no-code/opacity .3) | aa7e4a0 прямо удалил розовый курсор и faded tail; это смена дизайна до 2A, не новый отказ от требования | C настоящий Markdown: full text/heading/list/code/table, каждый prefix hello, без caret/Animated.Text |
| InterestChips присутствует | cc958d5 удалил chips; MindMap header фиксирует 26.09 новый вид; оба profile routes прежние | R map/no wheel/shared route; C реальные enter/back/toggleLeaf |
| chainOf(path,node) сохраняет всех родителей | Решение Ивана 10.08 не отменено — настоящий дефект R02 | H real onMapDone + connected Python trusted/matching probe; R точная sports/racket/padel цепочка |
| leaf onAdd/onRemove; ветка setPath; whole explicit chip; breadcrumb back; maxHeight260; CHIPS_COPY | Ввод не ограничен конечным деревом после cc958d5; whole sports доступен canonical разговору. Карта теперь темы/страницы/листья, вид изменён 26.09 | C enter/topic/back/toggle; H root/leaf/unknown; onboarding layout selected/remove/bounded tray/min3; mindmap_layout все темы/языки/страницы. Старый pixel maxHeight не переносится на новый вид |
| BottomNav to&&!on; home inline dismissTo | Тот же запрет текущей вкладки и stack collapse, handler вынесен | C canPick/go: current disabled, profile/home, home mascot Buddy |
| returning auth dismissTo home | Baseline auth-code: home ещё нет в stack, replace является redirect входа | R replace home, login exceptions auth/auth-code/intro добавлены только в redirect allowlist; обычные roots запрещены |
| inline Stack.Screen animation none; slide_from_right | SDK57 layout использует SCREENS/TAB и ios_from_right | R все 4 tabs→TAB(none), deep animation, публичный expo-router/react-navigation import |
| historical conversation fixture только norm(name) | ID helper добавлен в приложение, старый harness не определял isOther/pidOf/composerEnabled | Зависимости переданы; прежние cases past/live/nudge не изменены, identity suite отдельно |
| wizard detail→nature→who; prevStep(step) | Baseline GR flow содержит Step N of 3, forward who→lastStep; nature не отдельный обязательный шаг | C actual prevStep/goBack; R прежние clear timer/sheet/cancel-before-back guards с новым signature |
| «Все интенты» отдельной кнопкой allBtn | Baseline заменил самостоятельную кнопку общей нижней панелью | R activity route и usePreventRemove dispatch; C go('profile')/home проверяет общий navigation mechanism |
| @react-navigation/native прямой dependency | SDK57 проект требует публичный экспорт expo-router/react-navigation | R import source; TypeScript PASS; версия документации прочитана до правок |
| backend result == cached Python result | Wire JSON приводит tuple к array; fallback fix сделал ready достижимым вместо pending | Полное JSON-normalized равенство payload; missing/null отдельными subtests |

Историческая запись до разрешения 13.10: R01 **awaiting user** (теперь закрыта
восстановлением кнопки и свежими PASS в начале отчёта). Owner открывает proposed plan после GP_MAX_ROUNDS,
`can_fix=true` (подтверждённых вместе с owner >=GP_FIX_MIN_CONFIRMS). Раньше fix-frame
показывал Fix/Give time; Give time был no-op без продления дедлайна и ухода в чат.
Сейчас owner видит Confirm или Open chat плюс Fix. Callback/строка moreTime остались,
кнопки нет. Замена на voteDecide была бы другой функцией и отклонена аудитом. Ни
кнопку, ни таймеры без решения пользователя в этом handoff не меняли.

### Нагрузочный прогон canonical writer

Новый `kleal-ms/tools/monetization_load.py`. Каждая команда создаёт собственную
`test_load_<uuid>` schema, проверяет loopback + имя `kleal_monetization_test*`,
в конце удаляет только созданную schema и подтверждает count=0. Все три cleanup PASS.
Скрипт не меняет чужие схемы/процессы; schema мигрируется только synthetic fixture.

```sh
$PY kleal-ms/tools/monetization_load.py --workers 1 --owners 8 --attempts 4 > .codex/phase2-completion-load-w1.json
$PY kleal-ms/tools/monetization_load.py --workers 4 --owners 8 --attempts 4 > .codex/phase2-completion-load-w4.json
$PY kleal-ms/tools/monetization_load.py --workers 8 --owners 8 --attempts 4 > .codex/phase2-completion-load-w8.json
```

Окружение: macOS 27.0 arm64, 10 CPU, Python 3.12.14, PostgreSQL 17.11 aarch64
Alpine в существующем Docker container, loopback 55439; каждый процесс pool min1/max2.
Прогоны последовательные. Seed 20261012; **16 owners** (8 Free без Preview eligibility,
8 eligible Preview), по 4 независимых публикации shuffled; затем 16 успешных retry,
8 публикаций с синтетическим ranking outage, один drain. Итого 89 measured commands
за прогон; число реально работавших PID соответствует 1/4/8 в JSON.

Исполняется production `monetization_commands.handle('/api/agent/search-command')`,
canonical transaction/projection/idempotency/quota/outbox. Identity, prepare intent и
ranking синтетические (coffee, hybrid, пустой ranking). **Не** HTTP/auth/model/provider
benchmark; времена не являются production capacity/SLO. Короткий warmup pool до batch;
nearest-rank percentiles; latency измеряется внутри worker, без ожидания executor queue.

| Процессы | Фаза, число команд | p50 / p95 / max, ms | commands/s | Ошибки |
|---:|---|---:|---:|---|
| 1 | publish 64 | 39.958 / 115.157 / 162.608 | 21.267 | 24 ожидаемых search_quota |
| 4 | publish 64 | 128.099 / 289.521 / 298.260 | 26.858 | 24 ожидаемых search_quota |
| 8 | publish 64 | 288.522 / 482.050 / 522.507 | 26.308 | 24 ожидаемых search_quota |
| 1 | replay 16 | 44.286 / 47.662 / 47.662 | 22.388 | 0 |
| 4 | replay 16 | 141.219 / 146.885 / 146.885 | 28.036 | 0 |
| 8 | replay 16 | 282.139 / 288.846 / 288.846 | 27.993 | 0 |
| 1 | outage 8 | 89.081 / 109.228 / 109.228 | 10.592 | 0 неожиданных; 8 durable pending |
| 4 | outage 8 | 301.524 / 311.960 / 311.960 | 13.032 | 0 неожиданных; 8 durable pending |
| 8 | outage 8 | 474.116 / 621.123 / 621.123 | 12.873 | 0 неожиданных; 8 durable pending |
| 1 / 4 / 8 | drain 1 на прогон | 59.391 / 60.062 / 68.512 (по одному sample) | — | 0, восстановлены все 8 |

Итог каждого прогона: **0 неожиданных ошибок, 0 нарушений квоты**; у каждого Free
ровно 1 active, у каждого Preview 5 active; 8 grants ровно по 1209600 секунд;
48 resources = 48 durable commands = 48 outbox events. Replay не создаёт дублей и
равен исходному результату. Перед drain 40 ready/8 pending; после 48 ready, очередь
**8→0**, attempts=0. Все это проверяется assertions, а не только печатается.

Глобальный projection lock — подтверждённое ограничение: p95 acquisition на publish
**0.372 / 103.894 / 223.365 ms** (1/4/8 процессов; включает SQL roundtrip), max
0.530/110.676/237.659 ms. Throughput почти не растёт между 4 и 8, latency растёт.
Каждый adapter command/refresh сериализует и обходит общую проекцию. Это диагностический
результат маленького локального набора, не назначенный за пользователя SLO. Удалять lock
без изменения persistence было бы небезопасно; архитектура в этом handoff не переписана.
