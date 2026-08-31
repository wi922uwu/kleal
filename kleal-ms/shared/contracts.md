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

`match · plan · explain · explore · intro · negotiate · feedback · save · weights · pool` plus the
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

Row shape (34 fields, all of which have at least one reader — audited 2026-07-27):

| group | fields |
|---|---|
| identity | `id` `name` `age` `gender` `verified` `source` |
| interests | `interests` `vibe` `goals` `role` `formats` `langs` |
| geo | `area` `lat` `lon` `radiusKm` `km` |
| availability | `open` `paused` `pending` `lastActiveDays` `receiving` |
| safety | `safety` `datingOk` `dealBreakers` `blocksMe` `declinedOwnerDaysAgo` |
| agent memory | `summary` `story` `personality` `persona` `intents` `entities` |

Notes that matter:

- **`km` is `None` for every real person, by design.** A stored distance is meaningless — it
  depends on who is looking. It is computed only for the demo pool. Comparing it to a float
  raised `TypeError` and made every search return zero candidates; guard with `isinstance`.
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

### Open: the message endpoints are unauthenticated

`inbox`, `outbox`, `threads`, `thread` take `self` as an ordinary query parameter, so anyone who
knows a name can read that person's inbox, their thread list and the **full text of their private
messages**. Verified against prod: a message was planted between two people and read back by a
third, unauthenticated call.

Not a regression — they behaved this way before the rewrite too. There is no session anywhere in
the stack: sign-in lives in onboarding and matching never learns who is calling. Closing it means
carrying a session or token across services, which is a design decision, not a patch.

### Open: `gender` is collected and never used

Onboarding stores it and `tools/` writes it, but matching contains no reference to it at all, so
the "Кто" selector in the UI has no effect on results.

### Open: the `core_v2.py` rollback path has no tests

Its three suites tested pre-rewrite internals (`propose()`, `group_create()`, the old `_hard_gates`
arity) and were removed rather than bent to agree with code they were not written for. The engine
in use (`matching_core`) has 543 of its own checks; the rollback path has none.
