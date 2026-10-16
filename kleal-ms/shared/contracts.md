# Kleal cross-service contracts

The frozen part of the system. Four source files point here (`services/matching/app.py`,
`services/onboarding/app.py`, `shared/kleal_lib.py`, `shared/llm_client.py`) and until now the
file did not exist. Read this before renaming anything under `/api/`, changing a user-store
field, or editing `shared/`.

Everything here is verified against the running services, not against intent.

---

## 1. Topology

Every application service binds `127.0.0.1`. The public edge is **nginx** (`:80`/`:443`, certbot,
`aiopenware.com`), which proxies `/` to the gateway.

> **Проверено 2026-08-27; прежняя формулировка была неверна.** Здесь стояло «one public door …
> exactly one tunnel points at it». Туннель cloudflared заменён на nginx с сертификатом, и наружу
> сейчас смотрят `443`, `80`, `8081` (nginx → Expo `:8082`), `7080` (шлюз **дополнительно** висит
> на `0.0.0.0` — вход в обход TLS), `22` и `25672` (межузловой порт RabbitMQ). Кроме того, nginx
> уводит `/admin` и `/api/admin/` **прямо в админку `:7077`, мимо шлюза**, — то есть «одна дверь»
> не выполняется и на уровне маршрутизации.

```
browser ──► gateway :7080 ──► onboarding :7072   (also the default route for "/")
                          ├─► profile    :7073
                          ├─► matching   :7074
                          ├─► buddy      :7075
                          └─► filtration :7076
                                  │
   admin :7077 (own tunnel, token-gated, NOT proxied by the gateway)
                                  │
   every service ──► :17071 ──[туннель]──► ПОД llm :7071 ──► vLLM :8002

   ВНИМАНИЕ: 17071, а не 7071. Модель живёт на ДРУГОЙ машине (RunPod 195.26.233.30:24309),
   связь — юнит kleal-llm-tunnel: autossh -L 17071:127.0.0.1:7071. В юните сервисов стоит
   LLM_URL=http://127.0.0.1:17071.
   На дроплете при этом крутится СВОЙ kleal@llm на 127.0.0.1:7071, к которому никто не
   обращается и который упал бы при обращении: его SELF_BASE смотрит на localhost:8002/v1,
   а vLLM на дроплете нет. Не перепутать с живым.
```

Ports, URLs and store paths come from **`shared/config.py`** and nowhere else. Old environment
variable names (`HUB_ONB`, `HUB_FILTER`, …) are still honoured as aliases.

The gateway does **not** proxy `/api/admin/*`. The admin panel is reached on its own tunnel.

---

## 2. Endpoint names are frozen

The profile-service frontend hard-codes matching's endpoint names, and the onboarding frontend
hard-codes onboarding's. Renaming a route silently breaks a screen — there is no shared client
and no compile step to catch it. **If a route must be renamed, keep the old name as an alias in
the same dispatcher.**

### onboarding — canonical name is `/api/onboarding/*`

`state · chat · summary · signup · signin · attach · register · profile · profile-update · receiving`

`/api/v2/*` is a compatibility alias from the pre-split `kleal_v2.py` era. It is rewritten to the
canonical name once, at the top of `do_POST`, so a phone still holding a cached bundle keeps
working. Do not add new routes under `/api/v2/`.

### buddy — served under both `/api/buddy/*` and bare `/*`

`chat · intent-build · launch · intro · persona · ghostwrite · resummary · profile-edit ·
feedback · onboard · state · health`

### filtration

`POST /api/filter/categorize` — `{text}` → `{topics, category, subcategory, type, domain, role, isNew, note}`.
This is the shared vocabulary: matching resolves candidate interests through it, so a change to
`topics` output changes ranking.
`GET /api/filter/categories` — the category list. Introspection only, nothing calls it.

### matching — `/api/agent/*`

`match · plan · explain · explore · map-feed · intro · negotiate · feedback · save · weights · pool` plus the
restored `intents · intent-save · intent-delete · propose · respond · withdraw · request-archive ·
message · inbox · outbox · thread · threads · groups · group-create · group-join · group-leave`
and the diagnostics `funnel · stability · diversity · learn · admin/person · admin/cohorts ·
admin/proposals · admin/compare · admin/fatigue-reset`.

`explain` is two tools chosen by whether a `candidate` is named: with one, the per-pair decision
trace; without, the slate-wide diagnostic. See §6.

---

## 3. The user store

One file, `kleal-ms/users.json`, resolved by `config.USERS`. **Onboarding is its only writer**
on the registration path; the admin panel also edits it; matching reads it.

This has broken twice by drift: two services independently computed the path, one landed on
`services/matching/users.json` and the others on `<kleal-ms>/users.json`, so a restart without
`KLEAL_USERS` split the store — registrations went into a file the matcher never read, and
nothing reported it. Never recompute this path locally; import it.

**A person is the row's `id`, never its `name`** (since 2026-09-26, `docs/IDENTITY.md`). The
Postgres table is keyed by `id`; `name_key` is a plain index; namesakes are normal. An account owns
exactly one row (`row.owner`, and `person_id` in the account). Every service learns "who is
calling" from the session (`kleal_auth.caller_person`), never from a name in the body.

Row shape (35 fields, all of which have at least one reader — audited 2026-09-01):

| group | fields |
|---|---|
| identity | `id` `name` `age` `gender` `verified` `source` |
| interests | `interests` `vibe` `goals` `role` `formats` `langs` |
| geo | `area` `country` `lat` `lon` `radiusKm` `km` |
| availability | `open` `paused` `pending` `lastActiveDays` `receiving` |
| safety | `safety` `datingOk` `dealBreakers` `blocksMe` `declinedOwnerDaysAgo` |
| agent memory | `summary` `story` `personality` `persona` `intents` `entities` |

Notes that matter:

- **`km` is `None` for every real person, by design.** A stored distance is meaningless — it
  depends on who is looking. It is computed only for the demo pool. Comparing it to a float
  raised `TypeError` and made every search return zero candidates; guard with `isinstance`.
- `country` is the confirmed country-level profile fact. `/api/agent/map-feed?view=online` may
  expose it and a public country centroid; it must never substitute or return `lat`/`lon` from the
  profile row. Existing rows created before this field remain valid and may be reported as
  unavailable until the profile is saved again.
- **`gender` has no reader in matching.** Onboarding collects it and `tools/` writes it, but the
  ranking never consults it, so the "Кто" selector in the UI currently does nothing.
- `summary` / `story` / `personality` / `persona` / `intents` / `entities` are empty across the
  whole seeded pool. They are written on real registrations, not by the seeder — do not conclude
  from a seeded store that they are unused.
- `source` distinguishes seeded rows (`"seed"`) from real sign-ups. `tools/seed_barcelona.py`
  replaces only `source == "seed"` rows and never touches real ones.

`accounts.json` (login → password hash → attached profile) is separate and is **never** committed.

---

## 4. `shared/` is a frozen contract

| module | who imports it | rule |
|---|---|---|
| `config.py` | every service | the only place a port, URL or store path is written down |
| `kleal_lib.py` | onboarding, matching, buddy, filtration | keyless helpers + the extractor prompt |
| `llm_client.py` | onboarding, matching, buddy, filtration | the only way to reach a model |
| `http_util.py` | everyone | JSON request/response boilerplate |

`shared/` wins over a service-local file of the same name: each service does
`sys.path.insert(0, ../../shared)` **after** Python has put the script's own directory on the
path, so the explicit insert takes precedence. Service-local copies of these modules are
therefore dead weight, not overrides — three such stale copies were found in
`services/matching/` and removed.

Editing `shared/` is a cross-service event: `kleal_lib.py` carries the extractor prompt that
defines the profile schema, so a change there changes what every service stores about a person.

---

## 5. Model access

No service except `llm-service` may hold a key or a model base URL. Everyone else calls
`llm_complete(model_id, messages, temperature)` or `llm_stream(...)` from `shared/llm_client.py`,
where `model_id` is a key of llm-service's `MODELS` table (`config.MODEL_ID`, default
`llama_self`), never a provider model name.

`llm_complete` **raises** on transport failure. That is deliberate: callers have their own
fallbacks (filtration degrades to its keyword magnet, buddy to a canned reply), and swallowing
the error inside the client would disable all of them at once.

---

## 6. Known issues

### Fixed 2026-07-27 — kept here because the failure mode will recur

The rewrite of matching **renamed its API** and the profile frontend was never updated, so 16
routes 404'd and three screens (My Intents, Messages, Groups) were dead in the shipped build,
along with 9 diagnostic routes the admin panel proxies to. All 25 are restored, verified against
the running service.

The renames were: `propose → proposal`, `respond → proposal/respond`,
`intents/intent-save/intent-delete → saved_searches/save_search/save_search/delete`,
`groups/group-* → group`. Both spellings now exist; the restored ones are what the UI calls.

**This is why §2 says endpoint names are frozen.** There is no shared client and no compile step,
so a rename is only discovered by a person clicking the screen — or by `tools/e2e_smoke.py`, which
exists now and goes through the gateway exactly like a browser. Run it after touching any route.

Two engine-level gaps came from the same rewrite and are also fixed: `matching_core_engine` is a
drop-in for `core_v2`, and app.py reaches the engine only through `_core.*`, so any name `core_v2`
exports and the adapter does not is a crash waiting for its code path (`_in_quiet_hours`,
`ALL_DOMAINS`, `explain` were all missing). And `match_candidates` had lost its `diag` parameter,
which broke the admin funnel outright.

### Intent map feed

`GET /api/agent/map-feed?view=offline|online&self=<name>&limit=<n>` returns
`{items, partial, unavailableCount}` from the persisted intent stores.

Each item has `id`, `title`, `mode`, `kind`, `status`, `count`, `owner`, `privacy` and, when
available, its view-specific location. The offline view contains only offline/hybrid intents and
uses `address` + `lat`/`lng` from the intent venue. The online view contains only online/hybrid
intents and uses confirmed profile `country`/`countryCode`, `countrySource` set to
`confirmed_profile_country`, plus a public country centroid. City, area, device geo, IP and raw
intent country fields are never country fallbacks. It never returns an address or owner/profile
coordinates. Missing or unconfirmed country data is represented by
`locationAvailable:false` and response metadata; fake coordinates are forbidden.

### Fixed 2026-09-26: the message endpoints were unauthenticated

`inbox`, `outbox`, `threads`, `thread` took `self` as an ordinary query parameter, so anyone who
knew a name could read that person's inbox and private messages. Matching now resolves the caller
from the session (`self._pid`); `self` in the query or body is ignored for anyone who has an
account. Without a token only an unowned bot row or a temporary `anon:<name>` can act. Stored
person fields hold ids; responses carry the display name plus `<field>_id`. Peers are addressed by
`to_id` / `with_id` / `who_id` / `name_id`; a bare name is accepted only when it is unambiguous,
otherwise `AMBIGUOUS_PERSON`. Guards: `tools/identity_test.py`, `tools/identity_http_test.py`.
Details and what is still name-based: `docs/IDENTITY.md`.

### Fixed 2026-09-27: what a stranger could see and do (audit)

Each item has a guard in `tools/` that fails if it comes back.

- **Groups by id.** `/api/agent/gintent?gid=` returned the whole group to anyone, without a
  session, and group ids are listed in the public map feed: roster, time, **meeting place and call
  link**. `_gi_public(g, me)` is now role-aware: owner/member — everything; invitee — roster and
  time, no place/link; stranger — a teaser without people or plan. Guard: `privacy_test.py`.
- **Service-only matching endpoints** were public: `learn`/`learn-phrases` (shared category
  vocabulary), `outcome`/`transition`/`proposal` (engine logs that feed ranking), `save` (any JSON
  into the store), `negotiate`/`intro` (model calls), `explain`/`funnel`/`diversity`. The gateway
  now answers 404 for them (`_SERVICE_ONLY` in `services/gateway/app.py`); Buddy, the worker and the
  admin panel call matching directly on 127.0.0.1:7074. **A new internal endpoint goes on that list.**
- **Account deletion** from the app removed only the row and the account; intents stayed on the
  map, chats/plans/groups and the photo stayed on the server. Onboarding now calls
  `/api/agent/admin/purge` (by id, BEFORE deleting the row — matching cannot resolve a deleted id
  by the row) and deletes the photo; `purge_person` also covers groups, marks, evidence and media
  files. Guard: `privacy_test.py`.
- **Sign-in code rate limit** read the FIRST `X-Forwarded-For` hop, which the client sets. It reads
  `X-Real-IP` (set by nginx) now.
- **Password sign-in** (`/api/onboarding/signup`, `signin`) is closed with 410. The app has not used
  it since 2026-09-14; `e2e_smoke` created one prod account per run with it (263 of them).
- **Model endpoints** have a per-IP limit in nginx (`conf.d/kleal-model-limit.conf`: 60/min,
  burst 30, 6 concurrent) — Buddy, onboarding chat/summary, `agent/plan|match`, filtration,
  transcription. Mobile carriers put many people behind one IP — keep the limit generous.
- **Group close and group report (S10/S11)** had client screens and contract tests
  (`tools/s10_group_close_unit.py`, `tools/s11_group_report_unit.py`, written 2026-08-18) but no
  server half: both buttons always failed. Implemented against those tests; evidence files live in
  `kleal-ms/evidence/` (not served) and reach moderators only through the admin panel.
- **The app never re-checked its session** and showed empty screens after expiry or revocation.
  `checkSession()` in `kleal-app/src/state.ts` signs out on `no session` and keeps the profile.
  Guard: `kleal-app/tools/session_test.js`.
- **Two globals with one name** broke matching silently on 2026-09-26 (`_IDX`). Guard:
  `tools/dup_names_check.py`.

### Open: `gender` is collected and never used

Onboarding stores it and `tools/` writes it, but matching contains no reference to it at all, so
the "Кто" selector in the UI has no effect on results.

### Open: the `core_v2.py` rollback path has no tests

Its three suites tested pre-rewrite internals (`propose()`, `group_create()`, the old `_hard_gates`
arity) and were removed rather than bent to agree with code they were not written for. The engine
in use (`matching_core`) has 543 of its own checks; the rollback path has none.

## Приглашения в группу: исход и срок (04.10.2026, агент логики)
- `GET /api/agent/gintent` организатору: `invites` — ТОЛЬКО открытые (sent/viewed/awaiting_approval), с `at`, `expires_at`; его длину экраны читают как «открытых». Закрытые — отдельным полем `invites_closed` (до 50, старые первыми): `state` в словаре клиента — declined | expired | withdrawn | closed, сырое состояние в `reason`, время исхода `closed_at`. Принятые не отдаются (человек в `members`, там `joined_at`).
- `withdrawn` = организатор отменил в живой группе (место свободно, GR.14b). Ответ в закончившуюся группу и переход в 1:1 тоже ставят withdrawn, но наружу это `closed`.
- Точный адрес (`address`) — организатору и бывшему организатору, пока он в группе (GR.44f/44l); остальным район.
- `GI_INVITE_TTL` = 12 ч (борд «Ends in 12h», решение владельца). Срок пишется в строку при отправке.
- Пушей в продукте нет (ни токенов, ни отправки): GR.56/56a не реализованы. Сторож: `tools/gr_invites_closed_unit.py`.

## Раунды плана 1:1 (06.10.2026, агент логики; борд «1:1 · Offline — new layout», B/C)
- До подтверждения: раунд 1 — план хозяина, каждое встречное (`counter`) — новый раунд, максимум 3 (`NO_ROUNDS_LEFT`). Поля плана: `round`, `max_rounds`, `rounds_log[]`, `round_ends_at`, `can_fix`, `final_by_host`, `fixed`, `cancel_kind`, `expired_silent`.
- На каждый ход 6 ч (`round_ends_at`). Молчание до подтверждения закрывает план без последствий: `state=cancelled`, `cancel_kind=expired_no_answer`, строка `plan_expired {by}`. Планы до 06.10 срока не имеют.
- После 3-го раунда хозяин выбирает версию: `mplan-respond action=fix round=N` (один раз, `ALREADY_FIXED`); гость `stay` (→ confirmed) или `leave` (→ cancelled, `cancel_kind=left_final`, без последствий); молчит 6 ч — как `leave`.
- После подтверждения встречное — перенос: `pending.expires_at` +6 ч, по истечении снимается, встреча стоит (`plan_change_expired`).
- Время наступает на чтении: `_mp_sweep` в GET mplan/mplans и в `mp_respond`. Новые sys-коды: `plan_fixed`, `plan_left`, `plan_expired`, `plan_change_expired`.
- OF.19e: `GET /api/agent/mplan-alternatives?iid=&title=&except_id=` — кто принял МОЁ приглашение по этой затее, `free` = нет живого плана с ним.
- Смоук `tools/mplan_smoke.py` на бою пишет тестовые планы в живое хранилище — гонять на временной копии службы (MATCHING_PORT, KLEAL_STORE в /tmp, KLEAL_MQ=off, KLEAL_DB=json).

## Приглашения 1:1: выбор из ответивших (11.10.2026, агент логики; борд «1:1 · Offline — new layout», раздел A)
- `POST /api/agent/respond {decision:"accept", flow:"pick"}` → `answered` («ответил, ждёт выбора», поля `answered_at`, `pick_by`): чат и план НЕ открываются (держатся на `accepted`), соседи не гасятся. Без `flow` — прежнее «первое да» (старый клиент).
- `POST /api/agent/request-pick {id}` — только отправитель; выбранный → `accepted`, остальные открытые (`REQ_OPEN` = pending, answered) этого отправителя по той же затее (iid, иначе название) → `not_picked`, `trace.reason="picked_other"`; получателю `not_picked` виден, `withdrawn` — нет.
- До выбора: `decline` на answered = передумал (`trace.reason="changed_mind"`); `withdraw` работает и на answered; блокировка и бан закрывают и answered.
- Срок выбора (решение владельца): `pick_by` = ответ + min(6 ч, половина до встречи), не меньше 30 мин; не выбрал → `expired`, `trace.reason="host_silent"`, без последствий.
- Пол участника (`participants[].gender`) отдаётся только в плане 1:1 его двоим участникам; в выдаче и `person_card` его нет.
- Сторож: `tools/req_pick_unit.py`.
- Главная: `GET /api/agent/home-invites?pick=1` добавляет к pending заявки 1:1 со `status: answered` (`pick_by`) и свежий `not_picked` (сутки, `reason`, `closed_at`); без `pick=1` — только pending. У строк 1:1 есть `status` и `expires_at`.

## План 1:1: поля под борд «1:1 · Online» (11.10.2026, агент логики)
- `POST /api/agent/mplan-ask {id, what, cancel:true}` снимает просьбу «выбери место / проведи звонок»: попросивший забирает (`plan_ask_pulled`), попрошенный отказывается (`plan_ask_declined`); `NO_ASK`, если снимать нечего. План не меняется.
- В плане: `link_by`, `address_by` (кто дал вход); `feedback_expires_at` = начало + 24 ч (только показ, само ничего не засчитывается); `participants[].joined` (статус here); `join_closes_at` и `nobody_joined` — только у звонка: за 15 минут никто не вошёл. Это пометка, не исход.
- Пояс собеседника до плана: `tz` в карточках выдачи, в строках inbox/outbox и в `from` у home-invites.
