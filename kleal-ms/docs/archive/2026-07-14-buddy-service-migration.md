# buddy-service — what changed (2026-07-14)

Our standalone Buddy (the `buddy/` package in this repo, which ran as its own service on `:8090`) was folded
into the microservice stack. It is no longer a separate app: its brain now lives in
`kleal-ms/services/buddy/app.py`, and the parts that duplicated the stack were dropped in favour of the
services that already own them.

| our old buddy (`/buddy`, :8090) | where it went |
|---|---|
| `llm.py` (OpenAI client + key) | dropped → `shared/llm_client.py` → **llm-service** owns the keys |
| `api.py` (own HTTP server) | dropped → `shared/http_util.py` + the gateway |
| `store.py` (own SQLite + 5 seeded fake profiles) | dropped → **matching-service** owns the candidate pool |
| `matching.py` (our thin scorer) | dropped → **matching-service** ranks (gates, tiers, weights, geo, feedback) |
| `agent.py` / `prompts.py` (conversation, tool-call, intent) | **kept** → merged into `services/buddy/app.py` |
| RU→EN normalisation, humanised reasons | **kept + extended** (see below) |

Result: buddy holds no keys, no user DB, no ranker. It converses, remembers, canonicalises, and orchestrates
`filtration → matching`.

## What buddy adds on top of the previous version

1. **A deterministic search trigger — buddy chats by default, searches only on an explicit ask.**
   The 70B's own `"match"` flag is unreliable in *both* directions: it answered *"find me someone to play dota
   tonight"* with a chat question (missed a real ask), yet it also fired on plain talk like *"мы вчера поиграли
   в футбол вместе"* and *"давай сыграем в шахматы"* (a game with Buddy!). An early fix keyed off
   `signals.interest`, but the model extracts `interest` for almost any activity mention, so that over-fired.
   The trigger is now two-tiered and independent of the flag's noise (`wants_people()`): a **STRONG** ask
   (найди / ищу с кем / find me / who wants / teammate…) always searches; a softer **COMPANION** cue
   (с кем / кто-нибудь / someone to…) searches only if the model *also* flagged match. Bare activity words
   ("поиграть", "футбол", "together") never trigger on their own. Net effect: Kleal is a conversationalist
   first and only creates an intent when the user actually asks to meet people.
2. **Canonicalisation before matching.** matching resolves `topics` against its **English** `TAXONOMY`; an
   unresolvable topic makes `_base_tier` return `none` for *every* candidate — zero matches, no error anywhere.
   Two things reach it that it cannot resolve: Russian words (filtration's LLM usually translates, but its
   deterministic fallback scans `[a-zA-Z]+`, so on Cyrillic it yields nothing) and the novel items filtration
   is proud of ("labubu"). Buddy now maps topics onto the ranker's vocabulary, falls back to a category
   bridge, and if nothing is rankable it **says so** instead of silently returning an empty list.
3. **Replies in the user's language** (machine fields stay English — filtration and matching are EN-only).
4. **Session memory**: `{user_id, message}` mode, so a thin client does not have to replay the thread.
   The profile UI's stateless `{messages, profile, signals}` mode is unchanged.
5. **`/launch`** — the Figma "Launch search" step: match **+ negotiation**, so cards carry real accept/decline
   verdicts from each candidate's agent. (It also repairs a stale `note`: matching computes `note` at scoring
   time and negotiation only overwrites `agree`, so a declined candidate came back still saying
   *"Agent agreed"*.)
6. **`/onboard`**, **`/intro`**, **`/feedback`**, **`/health`**, **`/state`**; humanised match reasons
   (engine-speak → card copy); CORS + bare `/buddy/*` aliases; lenient JSON repair for truncated 70B output.

The response is a **superset** — `{reply, signals, match:{intent, top, candidates, fallback}}` is unchanged, so
the profile UI keeps rendering exactly as before; `{intent, matches, tool_call, category, lang}` are additive.

## Edit with Kleal — change the profile by talking (2026-07-15)

The profile-service "Profile" button (in the buddy-chat header) opens a dedicated **editor chat**: the user
changes their own profile in natural language ("добавь теннис", "город Мадрид", "убери футбол") and Kleal
applies it, with a **confirm step** before every change.

- **Backend** — a separate endpoint `POST /api/buddy/profile-edit {message, profile}` → `{reply, patch}`,
  kept out of `/chat` so the editor prompt can't leak into the conversational/match agent. `patch` is a
  list of `{op, field, value, label}`. Set-fields (`name, location, languages, formats, availability,
  safety, vibe, summary`) carry the full new value; list-fields (`interests, goals`) carry one item with
  `op add|remove`. `_validate_patch` drops unknown fields / empty values (so the model can't touch anything
  outside the whitelist). Non-edit messages ("what's the weather?") return `patch:[]` and just reply.
- **Frontend** — `scr_profileedit` (reuses the chat UI). The reply is a confirmation *question*; the patch
  renders as a card with the human `label`s + **Отмена / Применить**. Only on Применить does
  `applyProfilePatch` mutate `DATA` (the frontend owns the profile) and `saveState()` persist it.
  `fullProfileForEdit` sends the current values (semantic shape) so the agent reasons over real state;
  `applyProfilePatch` maps semantic fields back onto `DATA` (snapshot rows, `interests`, `goals`,
  `matchingPaths`). The backend never sees `DATA`'s internal shape — clean separation.
- **Verified** e2e through the gateway: RU edits produce correct patches ("убери футбол" matched the
  English `Football`), the confirm→apply flow updates the profile and the change shows on the profile screen.

## Create intent — conversational collection (2026-07-15)

The "Create Intent" flow used to POST any text straight to matching's parser → an intent card was built
from *anything*, even random letters, with no follow-up. Now it's a short dialogue.

- **Backend** — `POST /api/buddy/intent-build {messages, profile}` → `{reply, valid, ready, intent}`.
  Validates (gibberish → `valid:false`, never builds), asks for the one missing essential (usually "when?"),
  and only at activity + rough-time returns `ready:true` with a **canonical** intent (same `_categorize` +
  `build_intent` as `/chat`, so matching can rank it). Two safeguards: a **backstop** forces `ready` once the
  user has answered a follow-up and a real activity is recognised (the 70B otherwise interrogates forever —
  group size, exact place…); the **rankable guard** refuses to `ready` a topic matching can't score.
- **Frontend** — `scr_intentchat` is a chat (`intentMsgs`) until enough detail; then `buildIntentCard` calls
  `/api/agent/match` and renders the spec card + Launch. All create-intent entry points route to
  `openCreateIntent`. Card copy + negotiation statuses localised to RU to match the dialogue.
- **Verified** e2e: gibberish is refused with a re-ask (no card), a full one-line request builds the card in
  one turn, and a two-turn activity→time reaches ready via the backstop.

## For Dev A / Dev B — two things worth knowing

- **`BROAD_OF` in `services/buddy/app.py` mirrors `TAXONOMY` in `services/matching/app.py`.** Duplication is a
  smell; it lives in buddy only because buddy is the one that must guarantee a rankable query. The right home
  is `shared/taxonomy.py`, imported by both — happy to move it whenever you want.
- **filtration's deterministic fallback is Cyrillic-blind** (`re.findall(r"[a-zA-Z]+", ...)`) and its `topics`
  are not validated against matching's taxonomy, so a category can be perfect while the ranker still sees
  nothing. Buddy compensates, but the durable fix belongs in filtration.

Backup of the previous buddy on the pod: `services/buddy/app.py.bak_20260714_2218`.
