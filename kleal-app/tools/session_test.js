/**
 * Мёртвая сессия — это вход, а не пустое приложение. Сторож checkSession (src/state.ts).
 *
 *     node tools/session_test.js
 *
 * Аудит 27.09.2026: токен восстанавливался с диска вслепую, сервер на мёртвый токен отвечает
 * пустыми списками, и человек после истечения сессии (90 дней) или её отзыва видел пустое
 * приложение. Без сети и без телефона: src/state.ts и src/api.ts переводятся в JS на лету,
 * хранилище и react — заглушки, fetch подменён.
 */
const path = require('path'), fs = require('fs'), Module = require('module');
const APP = path.resolve(__dirname, '..');
const ts = require(path.join(APP, 'node_modules', 'typescript'));
const SRC = path.join(APP, 'src');
let disk = null;
const stubs = {
  'react-native': { Image: { prefetch: () => Promise.resolve() } },
  'react': { useEffect() {}, useState(v) { return [v, () => {}]; } },
  '@react-native-async-storage/async-storage': {
    default: { getItem: async () => disk, setItem: async (k, v) => { disk = v; } },
    getItem: async () => disk, setItem: async (k, v) => { disk = v; },
  },
  './i18n': { getLang: () => 'ru', replyLang: () => 'ru', T: (a) => a },
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
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true } });
  m._compile(out.outputText, filename);
};
let ok = 0, bad = 0;
const check = (n, c, x) => { if (c) { ok++; console.log('  ok   ' + n); } else { bad++; console.log('  FAIL ' + n + '   ' + JSON.stringify(x)); } };
let reply = null, fail = false;
global.fetch = async (url) => {
  if (fail) throw new Error('network down');
  return { ok: true, status: 200, headers: { get: () => 'application/json' },
           json: async () => reply, text: async () => JSON.stringify(reply) };
};
(async () => {
  const st = require(path.join(SRC, 'state.ts'));
  const api = require(path.join(SRC, 'api.ts'));
  const signedIn = JSON.stringify({ slide: 0, step: 5, login: 'a@x.test', authMethod: 'code', session: 'tok-1',
                                    done: true, profile: { name: 'Иван', age: 30 } });

  console.log('\n-- сервер: сессии нет --');
  disk = signedIn; reply = { ok: false, error: 'no session' };
  await st.restore();
  const lost = await st.checkSession();
  const s1 = JSON.parse(disk);
  check('потеря сессии замечена', lost === true, lost);
  check('вход стёрт', s1.login === null && s1.session === null, s1);
  check('анкета и «пройдено» остались', s1.done === true && s1.profile && s1.profile.name === 'Иван', s1);
  check('токен из запросов убран', api.getSession() === '', api.getSession());

  console.log('\n-- сервер: сессия жива --');
  disk = signedIn; reply = { ok: true, login: 'a@x.test' };
  await st.restore();
  check('живая сессия не трогается', (await st.checkSession()) === false && JSON.parse(disk || signedIn).session === 'tok-1');

  console.log('\n-- нет сети --');
  disk = signedIn; fail = true;
  await st.restore();
  check('без сети из аккаунта не выходим', (await st.checkSession()) === false && api.getSession() === 'tok-1');
  console.log('\nитог: ' + ok + ' ok, ' + bad + ' FAIL');
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
