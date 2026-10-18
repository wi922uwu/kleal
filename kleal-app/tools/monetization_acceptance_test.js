/** Автоматизированная приёмка 2A: настоящий API/metadata код, synthetic transport; не native QA. */
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const root = path.resolve(__dirname, '..'), ts = require(path.join(root, 'node_modules/typescript'));
function load(file, stubs = {}) {
  const m = { exports: {} };
  const out = ts.transpileModule(fs.readFileSync(path.join(root, file), 'utf8'), {
    compilerOptions: { module: 1, target: 7, esModuleInterop: true },
  }).outputText;
  Function('require', 'module', 'exports', out)(name => {
    if (name in stubs) return stubs[name];
    throw new Error('Unmocked ' + name);
  }, m, m.exports);
  return m.exports;
}
const defer = () => {
  let resolve, reject;
  const promise = new Promise((a, b) => { resolve = a; reject = b; });
  return { promise, resolve, reject };
};
const tick = () => new Promise(resolve => setImmediate(resolve));
async function fixture(disk = { value: null }) {
  const actions = load('src/monetization-actions.ts');
  const state = { requests: [], reads: 0, writes: 0, storageRead: null, storageWrite: null, response: null };
  const api = load('src/api.ts', {
    'react-native': { Image: { prefetch: async () => {} } },
    '@react-native-async-storage/async-storage': {
      getItem: async () => { state.reads++; if (state.storageRead) await state.storageRead(); return disk.value; },
      setItem: async (_key, value) => { state.writes++; if (state.storageWrite) await state.storageWrite(); disk.value = value; },
    },
    './i18n': { getLang: () => 'en', replyLang: () => 'en' },
    './thinking': { whileThinking: promise => promise },
    './interest-label': { registerInterestLabels() {} }, './monetization-actions': actions,
  });
  global.fetch = async (url, init) => {
    let response;
    if (url.includes('/api/onboarding/profile')) {
      response = { body: { user: { id: init.headers.Authorization === 'Bearer token-a' ? 'a' : 'b' } } };
    } else {
      const request = { url, headers: init.headers, body: JSON.parse(init.body || '{}') };
      state.requests.push(request);
      response = state.response ? await state.response(request) : { body: { ok: true } };
    }
    const status = response.status || 200;
    return { ok: status < 400, status, text: async () => JSON.stringify(response.body) };
  };
  api.setSession('token-a'); await api.ensureMe();
  return { api, actions, state, disk };
}
let passed = 0;
async function test(name, run) { await run(); passed++; console.log('PASS ' + name); }
const previousFetch = global.fetch;
(async () => {
  await test('A02: смена аккаунта во время записи retry metadata не отправляет чужое действие', async () => {
    const { api, state } = await fixture(), storage = defer();
    state.storageWrite = async () => { if (state.writes === 2) await storage.promise; };
    const pending = api.api.post('/api/agent/message', { to_id: 'peer', text: 'private A' });
    const rejected = assert.rejects(pending, /account_changed/);
    await tick(); assert.equal(state.writes, 2);
    api.setSession('token-b'); storage.resolve(); await rejected;
    assert.deepEqual(state.requests, [], 'payload A не должен уйти с bearer B');
  });
  await test('A03: временный отказ чтения metadata восстанавливается явным retry без перезапуска', async () => {
    const { api, state } = await fixture();
    state.storageRead = async () => { throw new Error('synthetic storage outage'); };
    await assert.rejects(api.api.post('/api/agent/message', { to_id: 'b', text: 'retry' }), /storage outage/);
    assert.equal(state.requests.length, 0);
    state.storageRead = null;
    await api.api.post('/api/agent/message', { to_id: 'b', text: 'retry' });
    assert.equal(state.reads, 2); assert.equal(state.requests.length, 1);
  });
  await test('A03: unknown status не отправляет публикацию, retry использует тот же commandId', async () => {
    const { api, actions, state, disk } = await fixture();
    actions.configureMonetization({ before: async () => { throw new Error('membership_unknown'); } });
    const body = { operation: 'publish', intent: { topics: ['coffee'] } };
    await assert.rejects(api.api.post('/api/agent/search-command', body), /membership_unknown/);
    assert.equal(state.requests.length, 0);
    const key = JSON.parse(disk.value)[0].key;
    actions.configureMonetization({ before: async () => {} });
    await api.api.post('/api/agent/search-command', body);
    assert.equal(state.requests[0].body.commandId, key);
  });
  await test('A12/A33: отмена до отправки очищает metadata; перезапуск не оживляет отмену', async () => {
    const first = await fixture();
    first.actions.configureMonetization({ before: async () => { throw new Error('action_cancelled'); } });
    const body = { operation: 'publish', intent: { topics: ['coffee'] } };
    await assert.rejects(first.api.api.post('/api/agent/search-command', body), /action_cancelled/);
    await tick(); assert.equal(first.state.requests.length, 0); assert.deepEqual(JSON.parse(first.disk.value), []);
    const second = await fixture(first.disk);
    assert.equal(second.actions.returnAction('token-a'), null);
    assert.equal(second.state.requests.length, 0, 'нет автоматического replay при загрузке');
    await second.api.api.post('/api/agent/search-command', body);
    assert.equal(second.state.requests.length, 1);
  });
  await test('A12/A33: abort во время загрузки metadata не открывает пояснение и не пишет на сервер', async () => {
    const { api, actions, state } = await fixture(), read = defer(), ctrl = new AbortController();
    let explanations = 0;
    state.storageRead = () => read.promise;
    actions.configureMonetization({ before: async () => { explanations++; } });
    const pending = api.api.post('/api/agent/search-command', { operation: 'publish', intent: {} }, ctrl.signal);
    const rejected = assert.rejects(pending, /action_cancelled/);
    ctrl.abort(); read.resolve(); await rejected; await tick();
    assert.equal(explanations, 0); assert.equal(state.requests.length, 0);
  });
  await test('A02: поздний ответ A после входа B отброшен до changed callback', async () => {
    const { api, actions, state } = await fixture(), reply = defer(); let changes = 0;
    state.response = () => reply.promise;
    actions.configureMonetization({ changed: () => { changes++; } });
    const pending = api.api.post('/api/agent/message', { to_id: 'peer', text: 'A' });
    const rejected = assert.rejects(pending, /account_changed/);
    await tick(); api.setSession('token-b'); reply.resolve({ body: { ok: true } });
    await rejected; assert.equal(changes, 0);
    assert.equal(state.requests[0].headers.Authorization, 'Bearer token-a');
  });
  await test('A12: abort после отправки сохраняет commandId для явного повтора после reload', async () => {
    for (const late of ['network', 'quota']) {
      const first = await fixture(), reply = defer(), ctrl = new AbortController(); let prompts = 0;
      first.state.response = () => reply.promise;
      first.actions.configureMonetization({ blocked: async () => { prompts++; throw new Error('action_cancelled'); } });
      const body = { operation: 'publish', intent: { topics: ['coffee'] } };
      const pending = first.api.api.post('/api/agent/search-command', body, ctrl.signal);
      const rejected = assert.rejects(pending, /action_cancelled/);
      await tick(); const key = first.state.requests[0].body.commandId;
      ctrl.abort(); await rejected;
      if (late === 'network') reply.reject(Object.assign(new Error('Aborted'), { name: 'AbortError' }));
      else reply.resolve({ status: 409, body: { ok: false, error: 'search_quota' } });
      await tick(); assert.equal(prompts, 0, 'поздний 409 не открывает quota sheet отменённого экрана');
      const second = await fixture(first.disk);
      assert.equal(second.state.requests.length, 0);
      await second.api.api.post('/api/agent/search-command', body);
      assert.equal(second.state.requests[0].body.commandId, key, 'сервер мог сохранить первую публикацию до отмены транспорта');
    }
  });
  await test('A15/A35: text voice video проходят одинаковый 503/quota/retry gate', async () => {
    for (const media of [{ text: 'text' }, { voice: { id: 'voice', transcript: 'voice' } }, { video: { id: 'video' } }]) {
      const { api, state } = await fixture();
      const body = { to_id: 'peer', client_id: 'media-' + Object.keys(media)[0], ...media };
      state.response = async () => ({ status: 503, body: { ok: false, error: 'membership_unavailable', retryable: true } });
      await assert.rejects(api.api.post('/api/agent/message', body), e => e.status === 503 && e.body.retryable);
      const key = state.requests[0].body.commandId;
      state.response = async () => ({ status: 409, body: { ok: false, error: 'chat_quota', blockerIds: ['own-session'] } });
      await assert.rejects(api.api.post('/api/agent/message', body), e => e.body.error === 'chat_quota');
      state.response = null; await api.api.post('/api/agent/message', body);
      assert.equal(state.requests.length, 3);
      state.requests.forEach(r => { assert.equal(r.body.commandId, key); assert.deepEqual(r.body[Object.keys(media)[0]], Object.values(media)[0]); });
    }
  });
  await test('R10: duplicate quota resume cancel receipt retains exact key for explicit retry', async () => {
    const {api,actions,state,disk}=await fixture(), first=defer(), receipt=defer();
    let publications=0; const receipts=new Map();
    state.response=async request=>{
      if(state.requests.length===1) { await first.promise; return {status:409,body:{error:'search_quota',blockerIds:['occupied']}}; }
      if(!receipts.has(request.body.commandId)) { publications++; receipts.set(request.body.commandId,{ok:true,id:'one'}); await receipt.promise; }
      return {body:receipts.get(request.body.commandId)};
    };
    actions.configureMonetization({blocked:(action,retry)=>actions.deferAction(action,retry)});
    const body={operation:'publish',intent:{topics:['coffee']}};
    const one=api.api.post('/api/agent/search-command',body), two=api.api.post('/api/agent/search-command',body);
    const settled=Promise.allSettled([one,two]); await tick(); first.resolve(); await tick();
    const key=state.requests[0].body.commandId;
    const resume=actions.resumeReturnAction('token-a'); const resumed=Promise.allSettled([resume]); await tick();
    actions.cancelReturnAction(); await tick();
    assert.equal(JSON.parse(disk.value)[0].key,key);
    receipt.resolve(); await settled; await resumed; await tick();
    assert.equal(JSON.parse(disk.value)[0].key,key,'late success remains a retry fence');
    await api.api.post('/api/agent/search-command',body);
    assert.equal(state.requests.at(-1).body.commandId,key); assert.equal(publications,1);
  });
  console.log(`${passed} acceptance tests PASS (synthetic transport, не native)`);
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => { global.fetch = previousFetch; });
