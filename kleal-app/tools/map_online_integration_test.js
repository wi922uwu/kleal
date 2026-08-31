const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const ts = require('typescript');

const root = path.resolve(__dirname, '..');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'kleal-online-map-integration-'));
for (const name of ['country-centroids.ts', 'online-intent-globe.ts', 'online-map-feed.ts']) {
  const source = fs.readFileSync(path.join(root, 'src', name), 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    fileName: name,
  }).outputText;
  fs.writeFileSync(path.join(tmp, name.replace(/\.ts$/, '.js')), output);
}

const { buildOnlineIntentGlobeModel } = require(path.join(tmp, 'online-intent-globe.js'));
const { confirmedOnlineCountryRows } = require(path.join(tmp, 'online-map-feed.js'));

const unsafeCityProjection = {
  id: 'city-derived-country', mode: 'online', kind: 'one_to_one', status: 'launched',
  title: 'Talk remotely', count: 1, owner: { displayName: 'City profile' },
  privacy: 'country_only', locationAvailable: true, country: 'Portugal', countryCode: 'PT',
};
const confirmedCountry = {
  ...unsafeCityProjection,
  id: 'confirmed-country',
  countrySource: 'confirmed_profile_country',
};
const nestedUntrusted = {
  id: 'nested-untrusted',
  intent: { mode: 'hybrid', kind: 'group', countryCode: 'ES', country: 'Spain' },
  locationAvailable: true,
};
const unsupportedProvenance = {
  ...unsafeCityProjection,
  id: 'unsupported-provenance',
  countrySource: 'confirmed_intent_country',
};

const model = buildOnlineIntentGlobeModel(
  confirmedOnlineCountryRows([unsafeCityProjection, confirmedCountry, nestedUntrusted, unsupportedProvenance]),
  { locale: 'en' },
);
assert.deepStrictEqual(model.countries.map((country) => country.code), ['PT']);
assert.deepStrictEqual(model.countries[0].intents.map((item) => item.id), ['confirmed-country']);
assert.deepStrictEqual(model.unknown.map((item) => item.id).sort(), [
  'city-derived-country', 'nested-untrusted', 'unsupported-provenance',
]);

const screen = fs.readFileSync(path.join(root, 'app/map.tsx'), 'utf8');
const detail = fs.readFileSync(path.join(root, 'app/map-intent.tsx'), 'utf8');
assert(screen.includes("agent.mapFeed(me, 'online')"), 'Search shell loads the online map-feed view');
assert(screen.includes('confirmedOnlineCountryRows(onlineRows)'), 'country provenance gate runs before globe adapter');
assert(screen.includes('<OnlineIntentGlobe'), 'Online globe is wired as a Search view');
assert(screen.includes('contentInsets={{ top: insets.top + 8, bottom: insets.bottom + 140 }}'));
assert(screen.includes("params: { id: item.id, view: 'online' }"), 'globe navigation carries only intent id and feed view');
assert(detail.includes("params.view === 'online'"));
assert(detail.includes('confirmedOnlineCountryRows((response as any)?.items || [])'));

console.log('online map-feed integration: provenance/wiring/navigation checks passed');
