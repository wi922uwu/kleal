# Kleal — controlled expansion и гарантия ответа (§12)

Цель fallback — **полезный следующий шаг**, а не случайный человек любой ценой. Реализовано в
[`services/matching/app.py`](../services/matching/app.py). Никакого изменения выданного slate или
never-dead-end поведения: лестница — это **аддитивный план + теги**, saved-search — новый store/endpoint.

## Уже сделано (never-dead-end + инварианты §12.1)
- **`_expand_fallback`** — поиск НИКОГДА не тупик, пока кто-то eligible: фаза 1 «broader» (adjacent/parent
  через сброс discovery-floor `_RELAXED_CFG`), фаза 2 «alternative» (ближайшие люди, T4). `NONEMPTY1/2`.
- **safety/age/consent/block/critical-language/purpose НЕ ослабляются** — fallback над тем же hard-gate
  пулом; `_RELAXED_CFG` зануляет ТОЛЬКО discovery-floor (веса/λ/outreach-floor/гейты нетронуты).
- **provenance tier сохранён** (`assign_tier`); **явно объясняется** компромисс (`note`/`fallback` теги);
  **parent-outreach только при broad consent**; **adjacent → discovery, не inbox** (T3 никогда не outreach).

## §12.2 Лестница расширения (`expansion_ladder`) — ordered PLAN
Read-only план из 7 шагов, surfaced в ответе `/match`,`/plan`,`/confirm` как `expansion`. Каждый шаг:
`{step, axis, relaxes (ОДНА soft-ось), provenance_tier, outreach{mode, broad_consent_required, note},
cost_rank (== step, cheapest-first), applicable, explanation_ru/en}`.

| # | Ось | Статус |
|---|---|---|
| 1 | exact entity/role @ time+zone (T0/T1) | done_prior — базовый slate |
| 2 | adjacent/sibling (T2/T3) | done — discovery, broad consent для personal |
| 3 | parent category (T2) | done/partial — движок не разделяет sibling(best3) и parent(best2), обе T2; план различает, тир нет |
| 4 | увеличить время/радиус | partial — client-override (`agent_plan(override)`), не в авто-fallback |
| 5 | смена формата | partial — offline→online (done, §5.1); 1:1→group pilot_disabled (§15) |
| 6 | event/room/group как alternative | pilot_disabled — онлайн-комната (T4/alternative_solution_type); реальные event/room как кандидаты §15/§16 |
| 7 | сохранённый поиск + уведомить | **done** — см. ниже |

**Честно:** план — one-axis-per-step; исполняемый `_expand_fallback` всё ещё ослабляет **две оси разом**
(adjacentAllowed + exactMatchRequired) и карточки помечаются **после факта** (`_tag_ladder`:
broader+T3→2, broader+T2→3, alternative→3, room→6). Тег добавляется PURE + exception-safe (иначе тупик).

## §12.3 Пример Dota 2
`dota_example` в ответе: T0 (активный Dota-intent support, тот же server/time) · T1 (подтверждённый Dota +
games receiving) · T2 (другие MOBA — **только более широкий вариант, не «почти Dota»**) · T4 (Dota room /
watch party / group queue) · No-supply (unranked ok? другой вечер? сохранить поиск?). LoL-игрок **не**
получит personal proposal под видом близкого Dota-совпадения без явного broad-consent на parent-expansion.

## §12.2 шаг 7: saved search + notify-later
`SESSION[uid].saved_searches` (в gitignored `kleal_store.json`, **НЕ** users.json). Эндпоинты:
`POST /api/agent/save_search` (persist), `POST /save_search/check` (re-run поиска **read-only** над ТЕКУЩИМ
hard-gate пулом — block/pause/age/consent с момента сохранения соблюдены, никогда не ослаблены; `ready`
только при РЕАЛЬНОМ non-fallback совпадении), `POST /save_search/delete`, `GET /saved_searches`. Заменяет
UI-заглушку `wait`. «Notify later» = persist + on-demand `/check` pull-hook (реальный async-push — отдельная
инфра).

## Статус (честно): **done_prior 8 · done 8 · partial 3 · pilot_disabled 2**
partial: parent≠sibling тир (sha-pinned), auto time/distance (client-override), 1:1→group (§15).
pilot_disabled: event/room/group как retrieved candidates (§15/§16) — стоит онлайн-комната.

Тесты: `services/matching/test_core_v2.py` — `C12-*` (10 проверок).
