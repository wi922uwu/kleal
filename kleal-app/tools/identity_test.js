/**
 * Тёзки в приложении — сторож правила «личность = id» (kleal-ms/docs/IDENTITY.md).
 *
 *     node tools/identity_test.js
 *
 * Без сети и без телефона: src/api.ts и src/plan-chat.ts переводятся в JS на лету, react-native и
 * соседние модули — заглушки, fetch перехвачен. Проверяет, что собеседник уезжает в запрос с id
 * (`to_id`, `with_id`, `name_id`, `who_id`, `to_ids`), что «я ли это» решается по id и что встреча
 * двух «Иванов» открывает чат со вторым, а не с самим собой.
 */
const path = require('path'), fs = require('fs'), Module = require('module');
const APP = path.resolve(__dirname, '..');
const ts = require(path.join(APP, 'node_modules', 'typescript'));
const SRC = path.join(APP, 'src');
const stubs = {
  'react-native': { Image: { prefetch: () => Promise.resolve() } },
  './i18n': { getLang: () => 'ru', replyLang: () => 'ru', T: (a) => a, dateLocale: () => 'ru', use12h: () => false, plural: () => '' },
  './interest-label': { registerInterestLabels: () => {} },
};
const origResolve = Module._resolveFilename;
Module._resolveFilename = function (req, parent, ...rest) {
  if (stubs[req]) return 'STUB:' + req;
  if (req.startsWith('.') && parent && parent.filename && parent.filename.startsWith(SRC)) {
    const base = path.resolve(path.dirname(parent.filename), req);
    for (const ext of ['.ts', '.tsx']) if (fs.existsSync(base + ext)) return base + ext;
  }
  return origResolve.call(this, req, parent, ...rest);
};
const origLoad = Module._load;
Module._load = function (req, parent, isMain) {
  if (stubs[req]) return stubs[req];
  return origLoad.call(this, req, parent, isMain);
};
require.extensions['.ts'] = function (m, filename) {
  const out = ts.transpileModule(fs.readFileSync(filename, 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React } });
  m._compile(out.outputText, filename);
};
let ok = 0, bad = 0;
const check = (name, cond, extra) => { if (cond) { ok++; console.log('  ok   ' + name); } else { bad++; console.log('  FAIL ' + name + '   ' + JSON.stringify(extra)); } };
const sent = [];
global.fetch = async (url, opts) => {
  sent.push({ url, body: opts && opts.body ? JSON.parse(opts.body) : null });
  const reply = url.includes('/api/onboarding/profile') ? { user: { id: 'on_me', name: 'Иван' } } : { ok: true, messages: [] };
  return { ok: true, status: 200, headers: { get: () => 'application/json' }, json: async () => reply, text: async () => JSON.stringify(reply) };
};
(async () => {
  const api = require(path.join(SRC, 'api.ts'));
  const pc = require(path.join(SRC, 'plan-chat.ts'));
  const last = () => sent[sent.length - 1];

  console.log('\n-- тела запросов --');
  await api.agent.message('Анна', { name: 'Иван', id: 'on_b' }, 'привет');
  check('message: to + to_id', last().body.to === 'Иван' && last().body.to_id === 'on_b', last().body);
  await api.agent.message('Анна', 'Иван', 'привет');
  check('message строкой: to без to_id', last().body.to === 'Иван' && !('to_id' in last().body), last().body);
  await api.agent.thread('Анна', { name: 'Иван', id: 'on_b' }, 5);
  check('thread GET: with + with_id', /with=%D0%98%D0%B2%D0%B0%D0%BD&with_id=on_b&since=5/.test(last().url), last().url);
  await api.agent.plans('Анна', { name: 'Иван', id: 'on_b' });
  check('mplans GET: with_id', /with_id=on_b/.test(last().url), last().url);
  await api.agent.plans('Анна');
  check('mplans без собеседника: без with', !/with=/.test(last().url), last().url);
  await api.agent.propose('Анна', { name: 'Иван', id: 'on_b' }, {});
  check('propose: to_id', last().body.to_id === 'on_b', last().body);
  await api.agent.block('Анна', { name: 'Иван', id: 'on_b' }, true);
  check('block: name + name_id', last().body.name === 'Иван' && last().body.name_id === 'on_b', last().body);
  await api.agent.report('Анна', { name: 'Иван', id: 'on_b' }, 'spam');
  check('report: name_id', last().body.name_id === 'on_b', last().body);
  await api.agent.person('Анна', { name: 'Иван', id: 'on_b' });
  check('person: name_id', last().body.name_id === 'on_b', last().body);
  await api.agent.threadRead('Анна', { name: 'Иван', id: 'on_b' });
  check('thread-read: with_id', last().body.with_id === 'on_b', last().body);
  await api.agent.threadEnd('Анна', { name: 'Иван', id: 'on_b' });
  check('thread-end: with_id', last().body.with_id === 'on_b', last().body);
  await api.agent.planPropose('Анна', { name: 'Иван', id: 'on_b' }, { starts_at: 1 });
  check('mplan-propose: to_id', last().body.to_id === 'on_b' && last().body.starts_at === 1, last().body);
  await api.group.invite('g1', 'Анна', [{ name: 'Иван', id: 'on_a' }, 'Дина'], 'i1');
  check('gintent-invite списком: to[] и to_ids[] по местам',
        JSON.stringify(last().body.to) === '["Иван","Дина"]' && JSON.stringify(last().body.to_ids) === '["on_a",""]', last().body);
  await api.group.approve('g1', 'Анна', { name: 'Иван', id: 'on_a' }, 'i2');
  check('gintent-approve: who_id', last().body.who_id === 'on_a', last().body);
  await api.group.remove('g1', 'Анна', { name: 'Иван', id: 'on_a' }, 'spam', 'i3');
  check('gintent-remove: who_id + reason', last().body.who_id === 'on_a' && last().body.reason === 'spam', last().body);

  console.log('\n-- кто я --');
  check('без сессии id неизвестен', api.myId() === '');
  check('без id — по имени', api.isMe('Иван', 'on_other', 'Иван') === true);
  api.setSession('tok');
  await api.ensureMe();
  check('ensureMe взял id из профиля', api.myId() === 'on_me', api.myId());
  check('тёзка с другим id — не я', api.isMe('Иван', 'on_other', 'Иван') === false);
  check('мой id — я', api.isMe('Иван', 'on_me', 'Иван') === true);
  check('строка без id — по имени', api.isMe('иван ', '', 'Иван') === true);
  api.setSession('tok2');
  check('смена входа сбросила id', api.myId() === '');
  api.setSession('tok');
  await api.ensureMe();

  console.log('\n-- план тёзок --');
  const plan = { id: 'mp1', participants: [{ name: 'Иван', name_id: 'on_me' }, { name: 'Иван', id: 'on_b' }] };
  const ref = pc.planChatPeerRef(plan, 'Иван');
  check('встреча двух «Иванов»: собеседник — второй, по id', ref.id === 'on_b' && ref.name === 'Иван', ref);
  const tgt = await pc.preparePlanChat(plan, 'Иван', api.agent.thread);
  check('переход в чат несёт who_id', tgt.params.who_id === 'on_b', tgt);
  check('и чтение треда ушло с with_id', /with_id=on_b/.test(last().url), last().url);
  console.log('\nитог: ' + ok + ' ok, ' + bad + ' FAIL');
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
