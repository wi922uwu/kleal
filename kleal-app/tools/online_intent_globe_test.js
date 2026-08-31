/* Targeted executable checks for the pure OnlineIntentGlobe adapter. */
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const ts = require('typescript');

const root = path.resolve(__dirname, '..');
const src = path.join(root, 'src');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'kleal-online-globe-'));

for (const name of [
  'country-centroids.ts',
  'online-intent-globe.ts',
  'online-intent-globe.fixtures.ts',
]) {
  const input = fs.readFileSync(path.join(src, name), 'utf8');
  const output = ts.transpileModule(input, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      esModuleInterop: true,
    },
    fileName: name,
  }).outputText;
  fs.writeFileSync(path.join(tmp, name.replace(/\.ts$/, '.js')), output);
}

const {
  buildOnlineIntentGlobeModel,
  onlineIntentGlobeCopy,
} = require(path.join(tmp, 'online-intent-globe.js'));
const { COUNTRY_CENTROIDS } = require(path.join(tmp, 'country-centroids.js'));
const {
  ONLINE_INTENT_GLOBE_FIXTURES,
  largeOnlineIntentGlobeFixture,
} = require(path.join(tmp, 'online-intent-globe.fixtures.js'));

const model = buildOnlineIntentGlobeModel(ONLINE_INTENT_GLOBE_FIXTURES, { locale: 'en' });
assert.strictEqual(model.stats.total, 5, 'only active Online + Hybrid rows with ids remain');
assert.strictEqual(model.stats.online, 3);
assert.strictEqual(model.stats.hybrid, 2, 'Hybrid must be present on the online globe');
assert.strictEqual(model.stats.oneToOne, 3);
assert.strictEqual(model.stats.groups, 2, 'legacy large and explicit group normalize to Group');
assert.strictEqual(model.stats.countries, 3);
assert.strictEqual(model.stats.unknown, 1);

const spain = model.countries.find((country) => country.code === 'ES');
assert(spain, 'Spain country cluster must exist');
assert.strictEqual(spain.count, 2, 'same-country Online + Hybrid intents aggregate together');
assert.strictEqual(spain.hybridCount, 1);
assert.strictEqual(spain.onlineCount, 1);
assert.notStrictEqual(spain.latitude, 1.2345, 'raw intent latitude must never become marker latitude');
assert.notStrictEqual(spain.longitude, 2.3456, 'raw intent longitude must never become marker longitude');
for (const item of spain.intents) {
  for (const forbidden of ['lat', 'lon', 'latitude', 'longitude', 'ip', 'ipCountryCode', 'city', 'area', 'address']) {
    assert(!(forbidden in item), `the view model must not retain ${forbidden}`);
  }
}

assert.strictEqual(model.unknown[0].id, 'unknown-online');
assert.strictEqual(model.unknown[0].countryCode, undefined);
assert(!JSON.stringify(model.unknown[0]).includes('Toronto'), 'timezone/IP hints must not leak into unknown rows');

const privacy = buildOnlineIntentGlobeModel([
  {
    intentId: 'ip-only', mode: 'online', ipCountryCode: 'DE',
    lat: 52.52, lon: 13.405, city: 'Berlin', timezone: 'Europe/Berlin',
  },
  {
    intentId: 'confirmed-code', mode: 'hybrid', countryCode: 'es',
    lat: -54.4208, lon: 3.3464, address: 'private exact place',
  },
  { intentId: 'confirmed-country-field-code', mode: 'online', country: 'DE' },
  { intentId: 'unsupported-code', mode: 'online', countryCode: 'QQ', lat: 0, lon: 0 },
], { locale: 'en' });
assert.strictEqual(privacy.countries.length, 2);
assert.deepStrictEqual(privacy.countries.map((country) => country.code), ['DE', 'ES']);
assert.strictEqual(privacy.unknown.length, 2, 'missing or unsupported explicit country stays honest unknown');
assert(privacy.unknown.some((item) => item.id === 'ip-only'), 'IP country must never be used');

const nested = buildOnlineIntentGlobeModel([
  { id: 'nested-active', intent: { mode: 'hybrid', format: 'group', min_total: 3, max_total: 18, country: 'Россия' } },
  { id: 'nested-archived', intent: { mode: 'online', countryCode: 'GB', status: 'archived' } },
  { id: 'open-false', mode: 'online', countryCode: 'GB', open: false },
  { id: 'unknown-mode', mode: 'teleport', countryCode: 'GB' },
], { locale: 'ru' });
assert.strictEqual(nested.stats.total, 1);
assert.strictEqual(nested.countries[0].code, 'RU');
assert.strictEqual(nested.countries[0].name, 'Россия');
assert.strictEqual(nested.countries[0].intents[0].maxTotal, 18, 'large groups are not narrowed');

const mapFeed = buildOnlineIntentGlobeModel([
  {
    id: 'map-feed-group', title: 'Feed group', mode: 'hybrid', kind: 'group',
    status: 'launched', count: 7, owner: { displayName: 'Feed owner' },
    privacy: 'country_only', country: 'Spain', countryCode: 'ES',
    locationAvailable: true, lat: 40.4637, lng: -3.7492,
  },
  {
    id: 'map-feed-one', title: 'Feed 1:1', mode: 'online', kind: 'one_to_one',
    status: 'launched', count: 1, owner: { displayName: 'Other owner' },
    privacy: 'country_only', locationAvailable: false,
  },
], { locale: 'en' });
assert.strictEqual(mapFeed.stats.groups, 1, 'fork 2 kind=group must remain Group');
assert.strictEqual(mapFeed.stats.oneToOne, 1, 'fork 2 kind=one_to_one must remain 1:1');
assert.strictEqual(mapFeed.countries[0].intents[0].participantCount, 7);
assert.strictEqual(mapFeed.countries[0].intents[0].who, 'Feed owner');
assert.strictEqual(mapFeed.unknown[0].id, 'map-feed-one');
assert(!JSON.stringify(mapFeed.countries[0].intents[0]).includes('40.4637'));

assert(Object.keys(COUNTRY_CENTROIDS).length >= 249, 'country anchor coverage must span the world');

const largeRows = largeOnlineIntentGlobeFixture(5_000);
const large = buildOnlineIntentGlobeModel(largeRows, { locale: 'en' });
assert.strictEqual(large.stats.total, 5_000);
assert.strictEqual(large.countries.length, 2);
assert.strictEqual(large.countries[0].count + large.countries[1].count, 5_000);
assert.strictEqual(large.stats.hybrid, 1_000);
assert.strictEqual(large.stats.groups, 1_667);

const ru = onlineIntentGlobeCopy('ru');
const en = onlineIntentGlobeCopy('en');
assert(ru.unknown(2).includes('2'));
assert(en.worldSummary(7, 3).includes('countries'));
assert.notStrictEqual(ru.emptyTitle, en.emptyTitle, 'language change must update visible copy');

const nativeSource = fs.readFileSync(path.join(src, 'components/OnlineIntentGlobe.native.tsx'), 'utf8');
const webSource = fs.readFileSync(path.join(src, 'components/OnlineIntentGlobe.web.tsx'), 'utf8');
const overlaySource = fs.readFileSync(path.join(src, 'components/OnlineIntentGlobeOverlay.tsx'), 'utf8');
assert(nativeSource.includes('initialCamera={WORLD}'), 'native map must start at the world camera');
assert(nativeSource.includes('altitude: 50_000_000'), 'MapKit world view must use a tested high-altitude camera');
assert(nativeSource.includes('showsUserLocation={false}'), 'online map must never request/show exact user location');
assert(nativeSource.includes('model.countries'), 'native markers must come from country clusters');
assert(webSource.includes('country.longitude + 180'), 'web projection must use only country centroid coordinates');
for (const state of ['online-globe-retry', 'online-globe-empty', 'online-globe-selection']) {
  assert(overlaySource.includes(state), `component state ${state} must stay reachable`);
}
assert(overlaySource.includes('accessibilityLabel'), 'component actions and lists must expose accessible labels');
assert(overlaySource.includes('<FlatList'), 'country clusters must open a virtualized intent list for large sets');

console.log('online intent globe: aggregation/filter/privacy/locale/large-set checks passed');
