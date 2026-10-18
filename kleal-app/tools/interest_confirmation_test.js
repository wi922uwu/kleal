// Исполняет реальные обработчики интересов; UI и сеть заменены синтетическими ответами.
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), ts = require('typescript');
const root = path.join(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'app/chat.tsx'), 'utf8');
const ast = ts.createSourceFile('chat.tsx', source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const names = ['recordNovel', 'replaceConfirmed', 'absorbNovel', 'confirmPending', 'skipPending', 'absorbAdded', 'send'];
const declarations = new Map();
function visit(n) {
  if (ts.isVariableDeclaration(n) && names.includes(n.name.getText(ast))) declarations.set(n.name.getText(ast), n.getText(ast));
  ts.forEachChild(n, visit);
}
visit(ast);
assert.equal(declarations.size, names.length);
let interests, receipts, added, pending, normalize, confirmation, calls, writes, session, labels, chatResponse;
const alive = { current: true };
const scope = {
  alive, getState: () => ({ session }),
  getLang: () => 'ru', registerInterestLabels: (v, lang) => { assert.equal(lang, 'ru'); Object.assign(labels, v); },
  step: 'hobbies', hobbyThread: { current: [] }, say() {}, noticeWritten() {}, setChips() {}, setTyping() {},
  interestLabel: k => k, profileForAttach: () => ({}), T: ru => ru,
  buddyApi: { interestsChat: () => chatResponse() },
  get: p => p==='interests.confirmations'?receipts:interests,
  set: (_p, v) => { interests = v; },
  setJustAdded: fn => { added = fn(added); },
  setPending: fn => { pending = typeof fn === 'function' ? fn(pending) : fn; },
  pushInterests: () => { writes.push([...interests]); },
  isKnownInterest: key => key === 'coffee',
  replyLang: () => 'ru', botAfter() {}, CONFIRM_INTEREST: { unclear: () => 'unclear' },
  addConfirmedInterest: (key, _label, token) => { assert.ok(token);receipts[key]=token; if (!interests.includes(key)) interests.push(key); },
  profileApi: {
    normalizeInterest: async () => { calls.push('normalize'); return normalize(); },
    confirmInterest: async () => { calls.push('confirm'); return confirmation(); },
  },
};
const js = ts.transpileModule(names.map(n => 'const ' + declarations.get(n) + ';').join('\n'), {
  compilerOptions: { target: ts.ScriptTarget.ES2020 },
}).outputText;
const handlers = Function(...Object.keys(scope), js + '\nreturn { absorbAdded, confirmPending, skipPending, send };')(...Object.values(scope));
const option = { canonical: 'sea_fishing', label: 'Морская рыбалка', token: 'synthetic-receipt' };
function reset() {
  interests = ['fishing']; receipts={};added = ['fishing']; pending = []; calls = []; writes = [];
  session = 'account-a'; alive.current = true; labels = {};
  normalize = () => ({ status: 'ready', options: [option] });
  confirmation = () => ({ ok: true, ...option });
}
async function run() {
  for(const via of ['existing','duplicate','pending']) {
    for(const confirmed of [false,true]) {
      reset();interests.push('sea_fishing');if(confirmed)receipts.sea_fishing='earlier-valid-receipt';
      normalize=()=>({status:'duplicate',canonical:'sea_fishing'});
      if(via==='pending')await handlers.confirmPending({text:'alias',replaces:'fishing'});
      else await handlers.absorbAdded([{key:via==='existing'?'sea_fishing':'alias',replaces:'fishing'}]);
      assert.equal(interests.includes('fishing'),!confirmed,via+':'+confirmed);
    }
  }
  reset();interests.push('sea_fishing');
  await handlers.absorbAdded([{key:'sea_fishing',replaces:'fishing'}]);
  assert.deepEqual(interests,['sea_fishing']);assert.equal(receipts.sea_fishing,option.token);
  reset();
  await handlers.absorbAdded([{ key: 'coffee', label: 'Авторский кофе', replaces: 'fishing' }]);
  assert.deepEqual(interests, ['coffee']); assert.deepEqual(added, ['coffee']); assert.deepEqual(calls, []);
  assert.deepEqual(labels, { coffee: 'Авторский кофе' });
  reset();
  await handlers.absorbAdded([{ key: 'морская рыбалка', replaces: 'fishing' }]);
  assert.deepEqual(calls, ['normalize', 'confirm']); assert.deepEqual(interests, ['sea_fishing']);
  assert.deepEqual(added, ['sea_fishing']); assert.deepEqual(writes.at(-1), ['sea_fishing']);
  for (const failure of ['normalize', 'confirm', 'rejected', 'duplicate']) {
    reset();
    if (failure === 'normalize') normalize = () => { throw Error('network'); };
    if (failure === 'confirm') confirmation = () => { throw Error('network'); };
    if (failure === 'rejected') confirmation = () => ({ ok: false });
    if (failure === 'duplicate') normalize = () => ({ status: 'duplicate' });
    await handlers.absorbAdded([{ key: 'морская рыбалка', replaces: 'fishing' }]);
    assert.deepEqual(interests, ['fishing'], failure); assert.deepEqual(added, ['fishing'], failure);
  }
  reset(); normalize = () => ({ status: 'clarify', question: 'Какая?', options: [option] });
  await handlers.absorbAdded([{ key: 'рыбалка', replaces: 'fishing' }]);
  assert.deepEqual(interests, ['fishing']); assert.equal(pending.length, 1); assert.deepEqual(calls, ['normalize']);
  handlers.skipPending(pending[0]); assert.equal(pending.length, 0); assert.deepEqual(interests, ['fishing']);
  await handlers.absorbAdded([{ key: 'рыбалка', replaces: 'fishing' }]);
  await handlers.confirmPending(pending[0], option);
  assert.deepEqual(interests, ['sea_fishing']); assert.deepEqual(added, ['sea_fishing']);
  assert.equal(pending.length, 0); assert.deepEqual(writes.at(-1), ['sea_fishing']);

  // A delayed network result belongs to its starting session, never a newly logged-in account.
  for (const stage of ['normalize', 'confirm', 'pending-confirm', 'pending-normalize']) {
    for (const invalidation of ['session', 'unmount']) {
      reset();
      let resolve;
      const delayed = () => new Promise(r => { resolve = r; });
      if (stage.endsWith('normalize')) normalize = delayed; else confirmation = delayed;
      const task = stage.startsWith('pending')
        ? handlers.confirmPending({ text: 'рыбалка', replaces: 'fishing' }, stage === 'pending-confirm' ? option : undefined)
        : handlers.absorbAdded([{ key: 'рыбалка', replaces: 'fishing' }]);
      while (!resolve) await Promise.resolve();
      if (invalidation === 'session') session = 'account-b'; else alive.current = false;
      interests = ['new-account-interest']; added = []; pending = []; writes = [];
      resolve(stage.endsWith('normalize') ? { status: 'ready', options: [option] } : { ok: true, ...option });
      await task;
      assert.deepEqual(interests, ['new-account-interest'], stage + ':' + invalidation);
      assert.deepEqual(added, []); assert.deepEqual(pending, []); assert.deepEqual(writes, []);
    }
  }
  for (const invalidation of ['session', 'unmount']) {
    reset(); let resolve;
    chatResponse = () => new Promise(r => { resolve = r; });
    const task = handlers.send('кофе');
    if (invalidation === 'session') session = 'account-b'; else alive.current = false;
    interests = ['new-account-interest']; writes = [];
    resolve({ reply: 'Coffee', added: [{ key: 'coffee', label: 'Кофе' }] });
    await task;
    assert.deepEqual(interests, ['new-account-interest']); assert.deepEqual(writes, []); assert.deepEqual(labels, {});
  }

  const stateJs = ts.transpileModule(fs.readFileSync(path.join(root, 'src/state.ts'), 'utf8'), {
    compilerOptions: { target: 7, module: 1, esModuleInterop: true },
  }).outputText;
  const m = { exports: {} };
  const mocks = { react: {}, '@react-native-async-storage/async-storage': { default: { setItem: async () => {}, getItem: async () => null }, __esModule: true }, './api': { setSession() {}, setMyId() {}, onMyId: () => () => {} } };
  Function('require', 'module', 'exports', stateJs)(name => { assert.ok(name in mocks, name); return mocks[name]; }, m, m.exports);
  m.exports.patch({ profile: { photo: 'private-photo', interests: { explicit: ['sea_fishing'], confirmations: { sea_fishing: option.token } } } });
  assert.equal(m.exports.profileForAttach().interests.confirmations, undefined);
  assert.equal(m.exports.profileForAttach().photo, undefined);
  assert.equal(m.exports.profileForRegister().interests.confirmations.sea_fishing, option.token);
  assert.equal(m.exports.getState().profile.interests.confirmations.sea_fishing, option.token);
  console.log('PASS интересы: known labels/normalized/clarify/cancel/network/rejected, atomic replacement, delivery, session/unmount guards, receipt isolation');
}
run().catch(e => { console.error(e); process.exitCode = 1; });
