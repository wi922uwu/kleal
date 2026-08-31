# OnlineIntentGlobe integration note

`OnlineIntentGlobe` is the standalone second view for the Search Map/List shell. It renders active
Online and Hybrid intents as one country cluster per confirmed country, and keeps country-less rows
in an explicit “country not provided” list. It owns no API call, router, BottomNav, Map/List switch,
or backend code.

## Public surface

```tsx
import { OnlineIntentGlobe } from '../src/components/OnlineIntentGlobe';
import { buildOnlineIntentGlobeModel } from '../src/online-intent-globe';

const lang = useLang();
const model = useMemo(
  () => buildOnlineIntentGlobeModel(mapFeed?.items || [], { locale: lang }),
  [mapFeed?.items, lang],
);

<OnlineIntentGlobe
  model={model}
  status={loading ? 'loading' : failed ? 'error' : 'ready'}
  onRetry={load}
  onOpenIntent={(item) => openIntent(item.id)}
  contentInsets={{ top: insets.top + 80, bottom: insets.bottom + 140 }}
/>
```

Minimal props are `model` and `status`. `onRetry` enables the error action. `onOpenIntent` is the
single navigation seam: country marker → country list is internal; tapping an intent calls the
owner without inventing a route. `contentInsets` reserves the shared screen chrome and defaults to
the device safe area when omitted.

## Adapter contract

`buildOnlineIntentGlobeModel(rows, { locale })` accepts explore-like objects. It reads:

- identity: `intentId`, `intent_id`, or `id`;
- mode: `mode`, `meetingMode`, `meeting_mode`, `locationMode`, or `location_mode`;
- country: explicit `countryCode`, `country_code`, or `country` (string or `{ code, name }`);
- format: `format`, `kind`, or `size`, with `count` preserved as `participantCount` and
  `groupSize`, `min_total`/`minTotal`, and `max_total`/`maxTotal` preserved for Group;
- display-only summary fields: `title`, `who`/`name`, `owner.displayName`, `topics`, and
  `when`/`time`;
- lifecycle: `open`, `deleted`, `deletedAt`/`deleted_at`, and `status`.

Those fields may be top-level or inside `intent`. Only `online`/`remote` and `hybrid`/`mixed` modes
are retained. Offline-only and explicit inactive/closed/deleted rows are excluded. Old
`small`/`large` format values normalize to the one user-facing `group` format without narrowing
`groupSize` or `max_total`.

The adapter deliberately never reads `lat`, `lon`, `latitude`, `longitude`, `ipCountryCode`, IP,
timezone, locale, city, area, address, venue, or device location. A supported mode/id without a
confirmed supported country goes into `model.unknown`; it is never assigned a random marker.

## Feed integration status (2026-09-01)

The current production `/api/agent/explore` response builder emits `intentId`, `title`, `who`,
`age`, `topics`, `role`, `when`, `area`, `verified`, optional `photo`/`dist`, and exact meeting
`lat`/`lon`. It does **not** emit `mode`, `format`, `country`, `countryCode`, group size, or lifecycle
state. Therefore the current live rows cannot truthfully populate this globe: without a confirmed
Online/Hybrid mode they are excluded, and coordinates must not be repurposed. The integration owner
needs an additive backend contract or another already-authoritative feed that supplies mode and
country. This branch intentionally does not change the backend or `src/api.ts`.

Fork 2 has now prepared that additive contract in its separate local commit `186fe6e`:
`GET /api/agent/map-feed?view=online&self=<name>&limit=<n>` returns `{ items, partial,
unavailableCount }`. Its online items expose `id`, `title`, `mode`, `kind`, `status`, `count`,
`owner`, `privacy: "country_only"`, explicit `country`/`countryCode` when available, and
`locationAvailable`. Pass only `response.items` into this adapter. `kind: "one_to_one"|"group"`,
`count`, and `owner.displayName` are covered by the targeted test. The adapter still ignores the
feed's public centroid `lat`/`lng` and resolves its own static display anchor from the confirmed
country code, so no exact/profile coordinates can accidentally cross the component boundary.

That fork does not yet include the client API wrapper or Map/List screen wiring. Those remain the
integration owner's files; this component branch deliberately does not edit them.

Hybrid belongs in both adapters: keep it in the existing Offline/Hybrid map feed and also pass it
to this Online/Hybrid model. Do not partition it away at the screen switch.

## States and QA

The component handles `loading`, `error`/retry, derived empty, ready summary, country markers,
country list, and unknown-country list. Country marker labels/counts, lists, actions, and disabled
detail callbacks are accessible. Russian/English copy and country names come from `model.locale`.

Deterministic fixtures live in `src/online-intent-globe.fixtures.ts`. Run:

```bash
node tools/online_intent_globe_test.js
```

The test covers same-country aggregation, Online + Hybrid, Offline/inactive/deleted filtering,
1:1 + Group (including large groups), coordinate/IP non-use, unknown country, nested contract
fields, Russian/English, full country-anchor coverage, and a 5,000-row set.

Country display anchors come from Natural Earth 5.1.1 label coordinates plus explicit anchors for
eleven ISO territories missing as independent rows. They are static country-level display points,
not user or intent positions.
