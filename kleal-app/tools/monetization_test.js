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
    assert.deepEqual(sent, [{ url: '/api/onboarding/monetization/v2/status' },
      { url: '/api/onboarding/monetization/preview', body: { consent: true } }]);
    assert.equal(client.view.data.state, 'preview');
  });
  await test('Plus states and active/expired unacked notices render accurately in RU EN ES', () => {
    const v2={ok:true,version:2,phase:'phase2a',state:'free',plan:'free',serverTime:1000,
      previewStartedAt:null,expiresAt:null,previewEligible:true,previewNotice:false,enforcementEnabled:true,
      purchaseAvailable:false,restoreAvailable:false,
      permissions:{publishSearch:true,initiateChat:true,reply:true,groupChat:true,manualCoordination:true,basicFilters:true},
      usage:{activeSearches:0,initiatedChats:0},limits:{activeSearches:1,initiatedChats:1},
      reasons:{publishSearch:null,initiateChat:null},blockerIds:{searches:[],chats:[]},searches:[],keepSearchId:null};
    const {PLUS,MONETIZATION,membershipPresentation:present}=monetization;
    for(language=0;language<3;language++) {
      assert.deepEqual(present(v2),{status:PLUS.free(),notice:MONETIZATION.previewInfo(),timing:null,plusTiming:null,sources:[]});
      assert.equal(present({...v2,previewEligible:false}).notice,null);
      const active={...v2,state:'preview',plan:'plus',previewEligible:false,previewStartedAt:1000,expiresAt:1210600,
        limits:{activeSearches:null,initiatedChats:null}};
      assert.deepEqual(present(active),{status:PLUS.preview(),notice:null,timing:PLUS.until(monetization.expiresLabel(1210600)),plusTiming:null,sources:[]});
      const ended={...v2,previewEligible:false,previewStartedAt:1000,expiresAt:1210600,serverTime:1210600};
      assert.deepEqual(present(ended),{status:PLUS.expired(),notice:null,timing:PLUS.endedOn(monetization.expiresLabel(1210600)),plusTiming:null,sources:[]});
      assert.deepEqual(present({...ended,state:'plus',plan:'plus',limits:{activeSearches:null,initiatedChats:null}}),
        {status:PLUS.active(),notice:null,timing:null,plusTiming:null,sources:[]});
      const manual={...ended,state:'plus',plan:'plus',limits:{activeSearches:null,initiatedChats:null},
        plusExpiresAt:1300000,entitlementSources:[{source:'manual',expiresAt:1300000}]};
      assert.equal(monetization.isMembershipV2(manual),true);
      assert.deepEqual(present(manual),{status:PLUS.active(),notice:null,timing:null,
        plusTiming:PLUS.plusUntil(monetization.expiresLabel(1300000)),sources:[PLUS.manualSource()]});
      assert.equal(monetization.isMembershipV2({...manual,plusExpiresAt:manual.expiresAt}),false);
      assert.equal(monetization.isMembershipV2({...manual,entitlementSources:[{source:'manual',expiresAt:1000}]}),false);
      assert.equal(monetization.isMembershipV2({...manual,entitlementSources:[{source:'unknown',expiresAt:1300000}]}),false);
      const mixed={...active,plusExpiresAt:1300000,entitlementSources:[{source:'preview',expiresAt:1210600},{source:'manual',expiresAt:1300000}]};
      assert.equal(monetization.isMembershipV2(mixed),true);
      assert.equal(present(mixed).timing,PLUS.until(monetization.expiresLabel(1210600)));
      assert.equal(present(mixed).plusTiming,PLUS.plusUntil(monetization.expiresLabel(1300000)));
      const startNotice=monetization.previewNoticePresentation({...active,previewNotice:true});
      assert.equal(startNotice.title,MONETIZATION.previewStarted());
      assert.equal(startNotice.message,PLUS.until(monetization.expiresLabel(active.expiresAt))+'\n\n'+PLUS.preserved());
      const expiredNotice=monetization.previewNoticePresentation({...ended,previewNotice:true});
      assert.equal(expiredNotice.title,PLUS.expired());
      assert.equal(expiredNotice.message,PLUS.endedOn(monetization.expiresLabel(ended.expiresAt))+'\n\n'+PLUS.preserved());
      assert.notEqual(expiredNotice.title,MONETIZATION.previewStarted());
      assert.equal(monetization.previewNoticePresentation({...active,previewNotice:false}),null);
      assert.equal(monetization.previewNoticePresentation({...ended,previewNotice:false}),null);
      assert.equal(monetization.previewNoticePresentation(v2),null);
      assert.equal(monetization.searchStateLabel('active'),MONETIZATION.searchActive());
      assert.equal(monetization.searchStateLabel('paused'),MONETIZATION.searchPaused());
      assert.equal(monetization.searchStateLabel('draft'),MONETIZATION.searchDraft());
      assert.ok(MONETIZATION.resumeSearch());
    }
    language=0;
    const screen=fs.readFileSync(path.join(APP,'app/plus.tsx'),'utf8');
    assert.match(screen,/membershipPresentation\(data\)/);
    assert.match(screen,/searchStateLabel\(search.state\)/);
    assert.match(screen,/operation:'resume',searchId/);
    assert.match(screen,/quotaPresentation:'inline'/);
    assert.match(screen,/MONETIZATION.resumeSearch\(\)/);
    const boundary=fs.readFileSync(path.join(SRC,'components/MonetizationBoundary.tsx'),'utf8');
    assert.match(boundary,/previewNoticePresentation\(data\)/);
    assert.match(boundary,/show\(notice.title,notice.message/);
    assert.match(boundary,/if \(!active \|\| session !== getSession\(\)\) return;/);
    assert.match(boundary,/v2\/notice.*commandId:`notice_\$\{data.previewStartedAt\}`/);
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
    assert.match(screen, /MONETIZATION\.freeRules\(\)/);
    assert.match(screen, /resumeReturnAction/);
    assert.doesNotMatch(screen, /router.push|AsyncStorage|\/purchase|\/restore/);
  });
  console.log(`\n${count} monetization tests PASS`);
})().catch((error) => { console.error(error); process.exitCode = 1; });
