/** A13: actual map/detail handlers, adapters, invitation cache and API with synthetic transport. Not native QA. */
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const root = path.resolve(__dirname, '..'), ts = require(path.join(root, 'node_modules/typescript'));
function load(file, stubs = {}) {
  const m = { exports: {} };
  const js = ts.transpileModule(fs.readFileSync(path.join(root, file), 'utf8'), {
    compilerOptions: { module: 1, target: 7, jsx: ts.JsxEmit.React, esModuleInterop: true },
  }).outputText;
  Function('React', 'require', 'module', 'exports', js)(stubs.react, name => {
    if (name in stubs) return stubs[name];
    throw new Error('Unmocked ' + name);
  }, m, m.exports);
  return m.exports;
}
const same = (a, b) => a && b && a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
let cells, cursor, dirty, effects, tree, Screen, session, requests, response, row, params, invites;
const React = {
  createElement: (type, props, ...children) => ({ type, props: { ...props, children } }),
  useState(initial) {
    const i = cursor++;
    if (!(i in cells)) cells[i] = { value: typeof initial === 'function' ? initial() : initial };
    const cell = cells[i];
    return [cell.value, value => { const next = typeof value === 'function' ? value(cell.value) : value;
      if (!Object.is(next, cell.value)) { cell.value = next; dirty = true; } }];
  },
  useRef(value) { const i = cursor++; if (!(i in cells)) cells[i] = { current: value }; return cells[i]; },
  useMemo(fn, deps) { const i = cursor++; if (!same(cells[i]?.deps, deps)) cells[i] = { value: fn(), deps }; return cells[i].value; },
  useCallback(fn, deps) { return React.useMemo(() => fn, deps); },
  useEffect(fn, deps) { const i = cursor++; if (!same(cells[i]?.deps, deps)) {
    const prev = cells[i], cell = { deps }; cells[i] = cell;
    effects.push(() => { prev?.cleanup?.(); cell.cleanup = fn(); });
  } },
};
const i18n = { T: (...v) => v[0], getLang: () => 'ru', useLang: () => 'ru', replyLang: () => 'ru' };
const native = { ...Object.fromEntries(['View', 'Text', 'ScrollView', 'Pressable', 'Image', 'ActivityIndicator'].map(n => [n, n])),
  Image: { prefetch: async () => {} }, StyleSheet: { create: x => x },
  Animated: { View: 'View', Value: class { interpolate() { return 1; } }, timing: () => ({ start() {} }) },
  Easing: { linear: x => x, out: x => x, quad: x => x } };
const api = load('src/api.ts', { 'react-native': native,
  '@react-native-async-storage/async-storage': { getItem: async () => null, setItem: async () => {} },
  './i18n': i18n, './interest-label': { registerInterestLabels() {} },
  './monetization-actions': load('src/monetization-actions.ts'),
  './thinking': { whileThinking: promise => promise },
});
const explore = load('src/explore.ts', { './i18n': i18n });
const adapter = load('src/offline-map-feed.ts');
const previousFetch = global.fetch;
global.fetch = async (url, init) => {
  const pathname = new URL(url).pathname;
  let reply = { body: {} };
  if (pathname === '/api/onboarding/profile') reply.body = { user: { id: session.slice(-1) } };
  else if (pathname === '/api/agent/map-feed') reply.body = { items: [row] };
  else {
    assert.equal(pathname, '/api/agent/propose', 'reply must not publish, join or send a human message');
    requests.push({ path: pathname, body: JSON.parse(init.body), token: init.headers.Authorization });
    reply = await response();
  }
  const status = reply.status || 200;
  return { ok: status < 400, status, text: async () => JSON.stringify(reply.body) };
};
function render() { cursor = 0; effects = []; dirty = false; tree = Screen(); const work = effects; effects = []; work.forEach(fn => fn()); }
async function settle() { for (let i = 0; i < 50; i++) { await Promise.resolve(); if (dirty) render(); } }
function nodes(v = tree) { return Array.isArray(v) ? v.flatMap(nodes) : v && typeof v === 'object' ? [v, ...nodes(v.props?.children)] : []; }
const textOf = v => Array.isArray(v) ? v.map(textOf).join(' ') : v && typeof v === 'object' ? textOf(v.props?.children) : String(v || '');
const pinCard = () => nodes().find(n => n.type?.name === 'PinPreview');
function unmount() { for (const c of cells || []) c?.cleanup?.(); cells = []; }
async function mount(screen, kind = 'one_to_one', view = 'offline', owner = 'd') {
  unmount(); session = 'token-a'; api.setSession(session); await api.ensureMe();
  requests = []; response = async () => ({ body: { ok: true, id: 'reply' } });
  row = { id: 'intent-d', searchId: 'search_d', title: 'Native hybrid', mode: 'hybrid', kind,
    status: 'launched', owner: { id: owner, displayName: 'Same' }, intent: { topics: ['coffee'] },
    address: 'Synthetic Madrid venue', lat: 40.4, lng: -3.7, count: 1,
    locationAvailable: true, privacy: 'exact_intent_location' };
  params = { id: row.id, view };
  invites = load('src/invites.ts', { react: React, './api': api, './candidates': { CAP: { limit: 3 } } });
  const stubs = { react: React, 'react-native': native, 'expo-location': {},
    'react-native-reanimated': { View: 'Animated.View' },
    '../src/components/GlobeAsk': { GlobeAsk: 'GlobeAsk' },
    '../src/components/HomeCards': { HomeCard: 'HomeCard', Face: 'Face', Chunk: 'Chunk', metaIcon: x => x },
    '../src/components/Glass': { GlassToast: 'GlassToast' },
    '../src/components/LiquidGlass': { riseIn: () => ({}) },
    'expo-router': { Stack: { Screen: 'Stack' }, useRouter: () => ({ navigate() {}, back() {} }), useLocalSearchParams: () => params },
    'react-native-safe-area-context': { useSafeAreaInsets: () => ({ top: 0, bottom: 0 }) },
    '../src/api': api, '../src/state': { useOnb: () => ({ session, profile: { name: 'Same' } }) },
    '../src/i18n': i18n, '../src/explore': explore, '../src/offline-map-feed': adapter,
    '../src/invites': { ...invites, useInvites() {} }, '../src/theme': load('src/theme.ts'),
    '../src/activity': { intentTitle: r => r.title, intentWhen: () => '' }, '../src/intent': { planWhenLabel: () => '' },
    '../src/online-intent-globe': { buildOnlineIntentGlobeModel: () => ({ locale: 'ru', countries: [], stats: { total: 0 } }), onlineIntentGlobeCopy: () => ({}) },
    '../src/online-map-feed': { confirmedOnlineCountryRows: x => x },
    '../src/components/icons': new Proxy({}, { get: (_o, key) => key }),
    '../src/components/category-icons': { CategoryGlyph: 'Glyph', iconNameFor: () => 'coffee' },
    ...Object.fromEntries(['ExploreMap', 'OnlineIntentGlobe', 'NearbyIntentSheet', 'BottomNav', 'Cover']
      .map(n => ['../src/components/' + n, { [n]: n }])),
  };
  Screen = load('app/' + screen + '.tsx', stubs).default; render(); await settle();
  if (screen === 'map') {
    const nearby = nodes().find(n => n.type === 'NearbyIntentSheet');
    assert.equal(nearby.props.pins[0].searchId, 'search_d');
    nearby.props.onOpen(nearby.props.pins[0]); await settle();
  }
}
function replyHandler(screen) {
  const fn = screen === 'map' ? pinCard().props.onRespond : nodes().find(n => n.type === 'Pressable'
    && [explore.MAP.respond(), explore.MAP.respondToAuthor()].includes(textOf(n).trim()))?.props.onPress;
  assert.ok(fn, 'actual reply handler exists');
  return fn;
}
async function respond(screen) { const pending = replyHandler(screen)(); await settle(); return pending; }
async function select(screen, id) {
  if (screen === 'map') {
    const nearby = nodes().find(n => n.type === 'NearbyIntentSheet');
    nearby.props.onOpen({ ...adapter.buildOfflineIntentMapModel({ items: [row] }).pins[0], id, searchId: 'search_' + id });
  } else { row = { ...row, id, searchId: 'search_' + id }; params = { ...params, id }; render(); }
  await settle();
}
let passed = 0;
async function test(name, run) { await run(); passed++; console.log('PASS ' + name); }
(async () => {
  for (const screen of ['map', 'map-intent']) {
    await test(screen + ': 409/503 keep card without cached invitation; explicit retry uses author reference', async () => {
      await mount(screen);
      for (const [status, error, copy] of [[409, 'search_paused', explore.MAP.respondUnavailable()], [503, 'membership_unavailable', explore.MAP.respondFailed()]]) {
        response = async () => ({ status, body: { ok: false, error } });
        await respond(screen); await settle();
        assert.equal(invites.inviteTo({ name: 'Same', id: 'd' }), undefined);
        const content = screen === 'map' ? pinCard().type(pinCard().props) : tree;
        assert.ok(textOf(content).includes(copy), 'controlled error with retry, no unhandled rejection');
      }
      response = async () => ({ body: { ok: true, id: 'reply' } });
      await respond(screen); await settle();
      assert.equal(invites.inviteTo({ name: 'Same', id: 'd' }).id, 'reply');
      for (const request of requests) {
        assert.equal(request.body.to_id, 'd');
        assert.equal(request.body.intent.targetIntentId, 'intent-d');
        assert.equal(request.body.intent.targetSearchId, 'search_d');
        assert.equal(request.body.intent.title, 'Native hybrid');
        assert.deepEqual(request.body.intent.topics, ['coffee'], 'legacy off/shadow retains the public card');
        for (const key of ['id', 'iid', '_searchId', 'searchId']) assert.ok(!(key in request.body.intent));
      }
      if (screen === 'map') assert.equal(pinCard(), undefined);
      else assert.ok(textOf(tree).includes(explore.MAP.sentWaiting()));
    });
    await test(screen + ': late success from A does not populate B cache or show success', async () => {
      await mount(screen); let release;
      response = () => new Promise(resolve => { release = resolve; });
      const fn = screen === 'map' ? pinCard().props.onRespond : nodes().find(n => n.type === 'Pressable' && textOf(n).trim() === explore.MAP.respond()).props.onPress;
      const pending = fn(); await settle();
      session = 'token-b'; api.setSession(session); render(); await settle();
      release({ body: { ok: true, id: 'late-a' } }); await pending; await settle();
      assert.equal(invites.inviteTo({ name: 'Same', id: 'd' }), undefined);
      assert.ok(!textOf(tree).includes(explore.MAP.sentWaiting()));
      assert.equal(requests[0].token, 'Bearer token-a');
    });
    await test(screen + ': late reply preserves the newly selected target even for the same author/title', async () => {
      await mount(screen); let release;
      response = () => new Promise(resolve => { release = resolve; });
      const pending = replyHandler(screen)(); await settle();
      await select(screen, 'different-intent');
      release({ body: { ok: true, id: 'old-target-reply' } }); await pending; render(); await settle();
      assert.equal(invites.inviteTo({ name: 'Same', id: 'd' }, { id: 'intent-d' }).id, 'old-target-reply', 'sent request remains real');
      assert.equal(invites.inviteTo({ name: 'Same', id: 'd' }, { id: 'different-intent' }), undefined);
      if (screen === 'map') assert.equal(pinCard().props.pin.id, 'different-intent');
      else assert.ok(!textOf(tree).includes(explore.MAP.sentWaiting()));
      assert.ok(replyHandler(screen));
    });
    await test(screen + ': leave and revisit same target rejects old error/finally while a new reply is pending', async () => {
      await mount(screen); let oldRelease, newRelease;
      response = () => new Promise(resolve => { oldRelease = resolve; });
      const old = replyHandler(screen)(); await settle();
      if (screen === 'map') { nodes().find(n => n.type === 'ExploreMap').props.onPick(null); await settle(); }
      else await select(screen, 'other');
      await select(screen, 'intent-d');
      response = () => new Promise(resolve => { newRelease = resolve; });
      const current = replyHandler(screen)(); await settle();
      oldRelease({ status: 503, body: { error: 'membership_unavailable' } }); await old; await settle();
      const content = screen === 'map' ? pinCard().type(pinCard().props) : tree;
      assert.ok(!textOf(content).includes(explore.MAP.respondFailed()), 'old error must not reach the reopened card');
      if (screen === 'map') assert.equal(pinCard().props.sending, true, 'old finally must not stop the new spinner');
      else assert.ok(nodes().some(n => n.type === 'Pressable' && n.props.disabled
        && nodes(n).some(child => child.type === 'ActivityIndicator')), 'old finally must not stop the new spinner');
      newRelease({ body: { ok: true, id: 'current-target-reply' } }); await current; await settle();
      if (screen === 'map') assert.equal(pinCard(), undefined);
      else assert.ok(textOf(tree).includes(explore.MAP.sentWaiting()));
    });
  }
  await test('online group detail replies to the same canonical search without joining', async () => {
    await mount('map-intent', 'group', 'online'); await respond('map-intent'); await settle();
    assert.equal(requests.length, 1); assert.equal(requests[0].body.intent.targetSearchId, 'search_d');
  });
  await test('missing stable recipient fails closed without cache or network', async () => {
    await mount('map', 'one_to_one', 'offline', ''); await respond('map'); await settle();
    assert.equal(requests.length, 0); assert.equal(invites.inviteTo('Same'), undefined);
  });
  await test('public legacy fallback retains time/topics but never turns foreign references into own ones', async () => {
    await mount('map-intent');
    const result = await invites.sendIntentReply('Same', { name: 'Same', id: 'd' }, { id: 'intent-d', searchId: 'search_d',
      title: 'Native hybrid', intent: { topics: ['coffee'], when: 'Saturday', id: 'own-injected', iid: 'own-injected',
        _searchId: 'own-injected', searchId: 'own-injected', link: 'private-link', phrase: 'private Buddy text',
        text: 'private text', summary: 'private summary', exact_point: { lat: 1, lon: 2 } } });
    assert.equal(result.ok, true);
    assert.deepEqual(requests[0].body.intent, { topics: ['coffee'], when: 'Saturday', targetIntentId: 'intent-d', targetSearchId: 'search_d', title: 'Native hybrid' });
  });
  console.log(`Map reply acceptance: ${passed} PASS (synthetic transport, not native)`);
})().catch(error => { console.error(error); process.exitCode = 1; })
  .finally(() => { unmount(); global.fetch = previousFetch; });
