// Черновик анкеты принадлежит аккаунту (владелец, 27.09: «перезашёл с новой почтой — кинуло на
// тот же этап, что был на другой почте»).
//   node tools/account_switch_test.js
const ts = require('typescript');
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const ROOT = path.join(__dirname, '..');
function load(file, mocks) {
  const src = fs.readFileSync(path.join(ROOT, file), 'utf8');
  const out = ts.transpileModule(src, { compilerOptions: { module: 1, target: 7, esModuleInterop: true } }).outputText;
  const m = { exports: {} };
  Function('require', 'module', 'exports', out)((n) => {
    if (n in mocks) return mocks[n];
    throw new Error('unmocked ' + n);
  }, m, m.exports);
  return m.exports;
}
let session = null;
const fresh = () => load('src/state.ts', {
  react: { useEffect() {}, useState: (v) => [v, () => {}] },
  '@react-native-async-storage/async-storage': { __esModule: true, default: { setItem: async () => {}, getItem: async () => null } },
  './api': { setSession: (t) => { session = t; }, auth: { session: async () => ({ ok: false, error: 'no session' }) } },
});

let n = 0;
const ok = (msg) => { n++; console.log('  ok  ', msg); };

(async () => {
  // 1. Та же почта после протухшей сессии — анкета продолжается с того же места.
  let S = fresh();
  S.signedIn({ login: 'Anna@Mail.ru', session: 't1', authMethod: 'code', profile: null, isNew: true });
  S.set('name', 'Анна'); S.set('age', 31);
  assert.equal(await S.checkSession(), true, 'мёртвая сессия выходит из аккаунта');
  assert.equal(S.getState().login, null);
  assert.equal(S.getState().profile.name, 'Анна', 'черновик после протухания остаётся');
  S.signedIn({ login: ' anna@mail.ru ', session: 't2', authMethod: 'code', profile: null, isNew: true });
  assert.equal(S.getState().profile.name, 'Анна');
  assert.equal(S.getState().profile.age, 31);
  ok('та же почта (регистр и пробелы не важны) после протухшей сессии — черновик на месте');

  // 2. Другая почта — чистый лист: ни имени, ни возраста, ни этапа прошлого человека.
  S.signedIn({ login: 'boris@mail.ru', session: 't3', authMethod: 'code', profile: null, isNew: true });
  assert.deepEqual(S.getState().profile, {});
  assert.equal(S.getState().done, false);
  assert.equal(S.getState().owner, 'boris@mail.ru');
  assert.equal(S.getState().session, 't3');
  ok('другая почта — черновик прошлого человека стёрт, анкета с нуля');

  // 3. Прошлый аккаунт анкету закончил — новый её НЕ пропускает.
  S = fresh();
  S.signedIn({ login: 'done@mail.ru', session: 't4', authMethod: 'code', profile: { name: 'Готовый' }, isNew: false });
  assert.equal(S.getState().done, true);
  S.setMsgPrefs(() => ({ muted: ['кто-то'] }));
  S.signedIn({ login: 'new@mail.ru', session: 't5', authMethod: 'google', profile: null, isNew: true });
  assert.equal(S.getState().done, false, 'новый аккаунт проходит анкету');
  assert.deepEqual(S.getState().profile, {});
  assert.deepEqual(S.getState().msg || {}, {}, 'пометки переписок прошлого аккаунта не переезжают');
  ok('прошлый закончил анкету — новый всё равно её проходит, чужие пометки переписок стёрты');

  // 4. Вернувшийся аккаунт получает свой профиль с сервера и сразу «пройдено».
  S.signedIn({ login: 'done@mail.ru', session: 't6', authMethod: 'code', profile: { name: 'Готовый' }, isNew: false });
  assert.equal(S.getState().profile.name, 'Готовый');
  assert.equal(S.getState().done, true);
  ok('вернувшийся — свой профиль с сервера и сразу в приложение');

  // 5. Состояние из прошлых версий (без owner) с живым логином — это его черновик.
  S = fresh();
  S.patch({ login: 'old@mail.ru', session: 'x', profile: { name: 'Старый' } });
  S.signedIn({ login: 'old@mail.ru', session: 'y', authMethod: 'code', profile: null, isNew: true });
  assert.equal(S.getState().profile.name, 'Старый');
  S.patch({ login: null, owner: null, profile: { name: 'Ничей' } });
  S.signedIn({ login: 'x@mail.ru', session: 'z', authMethod: 'code', profile: null, isNew: true });
  assert.deepEqual(S.getState().profile, {}, 'черновик без владельца чужому не отдаётся');
  ok('старое состояние без владельца: свой логин — продолжить, неизвестный — чистый лист');

  // 6. Вход идёт только через signedIn; запуск ведёт вошедшего посреди анкеты в анкету.
  for (const f of ['app/auth-code.tsx', 'app/auth.tsx']) {
    const src = fs.readFileSync(path.join(ROOT, f), 'utf8');
    assert(/signedIn\(\{/.test(src) && !/\bpatch\(\{\s*login:/.test(src), f + ': вход мимо signedIn');
  }
  const idx = fs.readFileSync(path.join(ROOT, 'app/index.tsx'), 'utf8');
  assert(/st\.login && st\.session \? '\/chat'/.test(idx));
  ok('оба входа (код и Google/Apple) идут через signedIn; вошедший посреди анкеты возвращается в неё');

  console.log(`\nсмена аккаунта: ${n} проверок прошли`);
})().catch((e) => { console.error(e); process.exit(1); });
