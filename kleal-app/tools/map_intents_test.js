const assert = require('assert');
const fs = require('fs');
const path = require('path');
const ts = require('typescript');
const vm = require('vm');

function loadTsModule(relativePath, stubs = {}) {
  const filename = path.join(__dirname, '..', relativePath);
  const source = fs.readFileSync(filename, 'utf8');
  const js = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    fileName: filename,
  }).outputText;
  const module = { exports: {} };
  const localRequire = (request) => stubs[request] || require(request);
  vm.runInNewContext(`(function(require,module,exports){${js}\n})`, { console })(localRequire, module, module.exports);
  return module.exports;
}

const explore = loadTsModule('src/explore.ts', {
  './i18n': { T: (_ru, en) => en },
});
const { buildOfflineIntentMapModel } = loadTsModule('src/offline-map-feed.ts', {
  './explore': explore,
});

const offline = {
  id: 'offline-created-1',
  title: 'Coffee near the park',
  mode: 'offline',
  kind: 'one_to_one',
  status: 'launched',
  address: 'Confirmed meetup address',
  lat: 55.751244,
  lng: 37.618423,
  count: 1,
  owner: { displayName: 'Map test user' },
  privacy: 'exact_intent_location',
  locationAvailable: true,
};

const hybrid = {
  ...offline,
  id: 'hybrid-group-1',
  title: 'Hybrid book club',
  mode: 'hybrid',
  kind: 'group',
  lng: undefined,
  lon: 37.618423,
  count: 8,
};

const rejected = [
  { ...offline, id: 'online', mode: 'online', privacy: 'country_only' },
  { ...offline, id: 'closed', status: 'closed' },
  { ...offline, id: 'deleted', status: 'deleted' },
  { ...offline, id: 'draft', status: 'draft' },
  { ...offline, id: 'profile-coordinate', privacy: 'country_only' },
  { ...offline, id: 'declared-unavailable', locationAvailable: false },
  { ...offline, id: 'bad-lat', lat: 91 },
  { ...offline, id: 'zero-island', lat: 0, lng: 0 },
];

const model = buildOfflineIntentMapModel({
  items: [offline, hybrid, { ...offline }, ...rejected],
  partial: true,
  unavailableCount: 2,
});

assert.deepStrictEqual(Array.from(model.pins, (pin) => pin.id), [offline.id, hybrid.id]);
assert.strictEqual(model.pins[0].mode, 'offline');
assert.strictEqual(model.pins[0].kind, 'one_to_one');
assert.strictEqual(model.pins[0].lon, offline.lng);
assert.strictEqual(model.pins[1].mode, 'hybrid');
assert.strictEqual(model.pins[1].kind, 'group');
assert.strictEqual(model.pins[1].lon, hybrid.lon, 'transitional lon alias remains supported');
assert.strictEqual(model.pins[1].count, 8);
assert.strictEqual(model.partial, true);
assert.strictEqual(model.unavailableCount, 3, 'client does not under-report unavailable rows when metadata is stale');
assert.strictEqual(model.pins.filter((pin) => pin.id === offline.id).length, 1, 'duplicate id is removed');

const missing = buildOfflineIntentMapModel({ items: [
  { ...offline, id: 'missing-coordinates', lng: undefined },
  { ...offline, id: 'explicitly-unavailable', locationAvailable: false },
] });
assert.strictEqual(missing.pins.length, 0);
assert.strictEqual(missing.partial, true);
assert.strictEqual(missing.unavailableCount, 2);

const overlap = explore.stackedAt(model.pins);
assert.strictEqual(overlap.get(explore.pinKey(model.pins[0])), 2, 'same-address intents are exposed as an overlap stack');

const apiSource = fs.readFileSync(path.join(__dirname, '..', 'src/api.ts'), 'utf8');
const mapSource = fs.readFileSync(path.join(__dirname, '..', 'app/map.tsx'), 'utf8');
const nativeMapSource = fs.readFileSync(path.join(__dirname, '..', 'src/components/ExploreMap.native.tsx'), 'utf8');
const detailSource = fs.readFileSync(path.join(__dirname, '..', 'app/map-intent.tsx'), 'utf8');

assert(apiSource.includes('/api/agent/map-feed?view=${view}&limit=${limit}&self=${encodeURIComponent(self)}'));
assert(mapSource.includes("agent.mapFeed(me, 'offline')"), 'Map loads the offline view of the new feed');
assert(!mapSource.includes('agent.explore(me)'), 'Map no longer guesses privacy/mode from legacy explore rows');
assert(mapSource.includes("setView('list')") && mapSource.includes("setView('map')"), 'Map and List share the same feed');
assert(mapSource.includes("pathname: '/map-intent'"), 'marker/card opens exact intent detail');
assert(mapSource.includes('onPress={group ? onOpen : onRespond}'), 'Group marker opens Group detail instead of sending a 1:1 invite');
assert(detailSource.includes("agent.mapFeed(me, 'offline')") && detailSource.includes('item.id === id'), 'detail reloads a still-visible item by id');
assert(mapSource.includes('Location.requestForegroundPermissionsAsync()'));
assert(!/useEffect\s*\(\s*\(\)\s*=>\s*\{?\s*locate\(/.test(mapSource), 'viewing Map does not request location permission');
assert(nativeMapSource.includes('if (seen.has(k)) continue'), 'exact overlaps collapse to one visible marker');
assert(nativeMapSource.includes("stacks?.get(pinKey(p)) || 1"), 'overlap count remains visible');

console.log('map intents targeted regressions: PASS');
