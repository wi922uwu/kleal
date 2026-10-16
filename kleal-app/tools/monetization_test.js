// Offline behavioral tests for the foundation controller and response contract.
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), Module = require('node:module');
const APP = path.resolve(__dirname, '..'), SRC = path.join(APP, 'src');
const ts = require(path.join(APP, 'node_modules/typescript'));
let language = 0, session = 'alice', sent = [];
const free = () => ({ ok: true, state: 'free', plan: 'free', source: 'none', serverTime: 1000,
  previewStartedAt: null, expiresAt: null, canStartPreview: true, previewEnabled: true, previewDays: 14,
  purchaseAvailable: false, restoreAvailable: false, enforcementEnabled: false, phase: 'foundation',
  products: [{ id: 'plus_monthly', period: 'month', referencePriceCents: 1199, currency: 'EUR' },
    { id: 'plus_annual', period: 'year', referencePriceCents: 8999, currency: 'EUR' }] });
const preview = () => ({ ...free(), state: 'preview', plan: 'plus', source: 'preview',
  canStartPreview: false, previewStartedAt: 1000, expiresAt: 1210600 });
const stubs = {
  './i18n': { T: (...values) => values[language], dateLocale: () => ['ru-RU', 'en-GB', 'es-ES'][language] },
  './api': { getSession: () => session, api: {
    get: async (url) => { sent.push({ url }); return free(); },
    post: async (url, body) => { sent.push({ url, body }); return preview(); },
  } },
};
function load(name) {
  const file = path.join(SRC, name + '.ts');
  const m = new Module(file, module);
  m.filename = file;
  m.require = (request) => stubs[request] || (request === './monetization' ? monetization : require(request));
  m._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText, file);
  return m.exports;
}
const monetization = load('monetization');
const { MembershipClient } = load('membership-client');
let count = 0;
async function test(name, fn) { await fn(); count++; console.log('PASS ' + name); }
const defer = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };

(async () => {
  await test('accepts only consistent foundation states', () => {
    assert.equal(monetization.isMembership(free()), true);
    assert.equal(monetization.isMembership(preview()), true);
    assert.equal(monetization.isMembership({ ...preview(), state: 'expired', plan: 'free', serverTime: 1210600 }), true);
    for (const value of [null, {}, { ...free(), purchaseAvailable: true }, { ...free(), plan: 'plus' },
      { ...preview(), previewEnabled: false }, { ...preview(), canStartPreview: true },
      { ...preview(), expiresAt: 0 }, { ...preview(), state: 'paid' }, { ...free(), products: [] },
      { ...free(), serverTime: NaN }, { ...free(), products: [null, null] }]) {
      assert.equal(monetization.isMembership(value), false, JSON.stringify(value));
    }
  });
  await test('prices and copy exist in RU, EN and ES', () => {
    for (language = 0; language < 3; language++) {
      assert.match(monetization.referencePrice(free().products[0]), /11[,.]99/);
      assert.match(monetization.referencePrice(free().products[1]), /89[,.]99/);
      assert.ok(monetization.expiresLabel(1791331200));
      for (const [key, value] of Object.entries(monetization.PLUS)) {
        assert.equal(typeof value, 'function', key);
        assert.ok(value(key === 'period' ? 'month' : 'date'), key);
      }
    }
    language = 0;
  });
  await test('uses authenticated API without client identity or duration', async () => {
    sent = []; const client = new MembershipClient();
    await client.load(); await client.start();
    assert.deepEqual(sent, [{ url: '/api/onboarding/monetization/status' },
      { url: '/api/onboarding/monetization/preview', body: { consent: true } }]);
    assert.equal(client.view.data.state, 'preview');
  });
  await test('does not grant optimistically and deduplicates double taps', async () => {
    const pending = defer(); let calls = 0;
    const client = new MembershipClient(() => session, { get: async () => free(), start: () => { calls++; return pending.promise; } });
    await client.load(); const result = client.start();
    assert.equal(client.view.data, null); assert.equal(client.view.busy, true);
    await client.start(); assert.equal(calls, 1);
    pending.resolve(preview()); await result;
    assert.equal(client.view.data.state, 'preview');
  });
  await test('late result from previous account never overwrites current account', async () => {
    const first = defer(); let owner = 'alice', calls = 0;
    const client = new MembershipClient(() => owner, { get: () => ++calls === 1 ? first.promise : Promise.resolve(free()), start: async () => preview() });
    const old = client.load(); owner = 'bob'; await client.load();
    first.resolve(preview()); await old;
    assert.equal(client.view.session, 'bob'); assert.equal(client.view.data.state, 'free');
  });
  await test('logout clears membership and sends no request', async () => {
    let owner = 'alice', calls = 0;
    const client = new MembershipClient(() => owner, { get: async () => { calls++; return preview(); }, start: async () => preview() });
    await client.load(); owner = ''; await client.load();
    assert.equal(calls, 1); assert.equal(client.view.data, null); assert.equal(client.view.error, 'sign_in');
  });
  await test('server expiry overrides previously active Preview', async () => {
    let response = preview();
    const client = new MembershipClient(() => 'alice', { get: async () => response, start: async () => response });
    await client.load(); response = { ...response, state: 'expired', plan: 'free', serverTime: 1210600 };
    await client.load(); assert.equal(client.view.data.plan, 'free'); assert.equal(client.view.data.canStartPreview, false);
  });
  await test('network, auth and malformed responses never retain active access', async () => {
    let response = preview(), error;
    const client = new MembershipClient(() => 'alice', { get: async () => { if (error) throw error; return response; }, start: async () => response });
    await client.load(); error = { status: 401 }; await client.load();
    assert.equal(client.view.error, 'sign_in'); assert.equal(client.view.data, null);
    error = new Error('offline'); await client.load(); assert.equal(client.view.error, 'network');
    error = null; response = { ...preview(), purchaseAvailable: true }; await client.load();
    assert.equal(client.view.error, 'network'); assert.equal(client.view.data, null);
    response = free(); await client.load(); assert.equal(client.view.error, null);
  });
  await test('dispose and React StrictMode resubscribe can load again', async () => {
    const first = defer(); let calls = 0;
    const client = new MembershipClient(() => 'alice', { get: () => ++calls === 1 ? first.promise : Promise.resolve(free()), start: async () => preview() });
    const old = client.load(); client.dispose();
    let notifications = 0; client.subscribe(() => { notifications++; });
    await client.load(); first.resolve(preview()); await old;
    assert.equal(client.view.data.state, 'free'); assert.equal(client.view.busy, false);
    assert.equal(notifications, 2);
  });
  await test('additive navigation and no purchase command in screen', () => {
    const screen = fs.readFileSync(path.join(APP, 'app/plus.tsx'), 'utf8');
    assert.match(fs.readFileSync(path.join(SRC, 'settings.ts'), 'utf8'), /to: '\/plus'/);
    assert.match(fs.readFileSync(path.join(APP, 'app/_layout.tsx'), 'utf8'), /\['plus'\]/);
    assert.match(screen, /<ProfileShell/);
    assert.match(screen, /<Button disabled label=\{PLUS.purchase\(\)\}/);
    assert.doesNotMatch(screen, /router.push|AsyncStorage|\/purchase|\/restore/);
  });
  console.log(`\n${count} monetization tests PASS`);
})().catch((error) => { console.error(error); process.exitCode = 1; });
