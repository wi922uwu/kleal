// Исходы приглашений в группу — «Can’t make it» / «Invite closed» (борд «0 · Create the intent»,
// GR.14d/14e/17a) из src/ginvites.ts.
//
//   node tools/ginvites_closed_test.js
//
// Модуль транспилируется из настоящего исходника; сервер подменён: группа отдаётся из фикстур.
const fs = require('fs');
const path = require('path');
const ts = require('typescript');

const ROOT = path.join(__dirname, '..');
const src = fs.readFileSync(path.join(ROOT, 'src/ginvites.ts'), 'utf8');
const js = ts.transpileModule(src, { compilerOptions: { target: 'ES2019', module: ts.ModuleKind.CommonJS } }).outputText;

let fixture = null;
const api = {
  group: { get: async () => ({ ok: true, group: fixture }) },
  newIdem: () => 'idem',
  peerName: (p) => (typeof p === 'string' ? p : String((p && p.name) || '')),
  peerId: (p) => (typeof p === 'string' ? '' : String((p && p.id) || '')),
  pidOf: (row, field) => String((row || {})[field + '_id'] || (field === 'name' ? (row || {}).id : '') || ''),
};
const react = { useEffect: () => {}, useState: (v) => [v, () => {}] };
const mod = { exports: {} };
new Function('module', 'exports', 'require', js)(mod, mod.exports, (n) => (n === './api' ? api : n === 'react' ? react : require(n)));
const G = mod.exports;

let ok = 0, failed = 0;
function check(name, cond, detail) {
  if (cond) { ok++; console.log('  ok   ' + name); }
  else { failed++; console.log('  FAIL ' + name + (detail ? '\n         ' + detail : '')); }
}

const me = { name: 'Mateo', id: 'u_mateo' };
const jane = { name: 'Jane', id: 'u_jane' }, marc = { name: 'Marc', id: 'u_marc' }, elly = { name: 'Elly', id: 'u_elly' };
const T0 = 1791000000;   // секунды, как отдаёт сервер

(async () => {
  // 1. Сервер отдаёт закрытые отдельным полем.
  fixture = {
    gid: 'gi_1', full: true, max_total: 3, members: [me, { name: 'Jane', id: 'u_jane', joined_at: T0 + 180 }, marc],
    invites: [],
    invites_closed: [
      { id: 'a', to: 'Elly', to_id: 'u_elly', state: 'declined', closed_at: T0 + 300 },
      { id: 'b', to: 'Kai', to_id: 'u_kai', state: 'closed', closed_at: T0 + 400 },
      { id: 'c', to: 'Ana', to_id: 'u_ana', state: 'expired', closed_at: T0 + 500 },
      { id: 'd', to: 'Leo', to_id: 'u_leo', state: 'withdrawn', closed_at: T0 + 600 },
      { id: 'e', to: 'Jane', to_id: 'u_jane', state: 'declined', closed_at: T0 + 10 },
    ],
  };
  await G.adoptGroup('Mateo', 'gi_1');
  check('отказ → Can’t make it', G.groupStatusFor(elly) === 'declined');
  check('время исхода — с сервера, в мс', G.groupStatusAt(elly) === (T0 + 300) * 1000, String(G.groupStatusAt(elly)));
  check('закрыто в полной группе → Invite closed «группа собралась»',
    G.groupStatusFor({ name: 'Kai', id: 'u_kai' }) === 'closed' && G.groupClosedOf({ name: 'Kai', id: 'u_kai' }).why === 'full');
  check('истёк срок → Invite closed «не ответил вовремя»', G.groupClosedOf({ name: 'Ana', id: 'u_ana' })?.why === 'expired');
  check('своя отмена (withdrawn) → снова «Invite», а не закрыто (GR.14b)',
    G.groupStatusFor({ name: 'Leo', id: 'u_leo' }) === undefined);
  check('вступивший главнее старого отказа', G.groupStatusFor(jane) === 'joined');
  check('вступил в — joined_at с сервера', G.groupStatusAt(jane) === (T0 + 180) * 1000);

  // 2. Старый сервер без поля: пропавшая открытая строка угадывается (группа не полна → отказ).
  fixture = { gid: 'gi_2', full: false, max_total: 3, members: [me],
    invites: [{ id: 'i1', to: 'Elly', to_id: 'u_elly', state: 'sent', at: T0, expires_at: T0 + 12 * 3600 }] };
  await G.adoptGroup('Mateo', 'gi_2');
  check('открытое приглашение — pending', G.groupStatusFor(elly) === 'pending');
  check('срок набора — expires_at', G.groupEndsAt() === (T0 + 12 * 3600) * 1000);
  fixture = { gid: 'gi_2', full: false, max_total: 3, members: [me], invites: [] };
  await G.syncGroup('Mateo');
  check('без invites_closed пропажа читается как отказ (догадка)', G.groupStatusFor(elly) === 'declined');

  // 3. Сервер с полем: пропажа без исхода — своя отмена, не отказ.
  fixture = { gid: 'gi_3', full: false, max_total: 3, members: [me],
    invites: [{ id: 'i2', to: 'Marc', to_id: 'u_marc', state: 'sent', at: T0 }], invites_closed: [] };
  await G.adoptGroup('Mateo', 'gi_3');
  fixture = { gid: 'gi_3', full: false, max_total: 3, members: [me], invites: [], invites_closed: [] };
  await G.syncGroup('Mateo');
  check('с invites_closed не угадываем: исчезло без исхода → снова «Invite»', G.groupStatusFor(marc) === undefined);

  // 4. Ответ без списков вовсе не объявляет всех отказавшимися.
  fixture = { gid: 'gi_4', full: false, max_total: 3, members: [me],
    invites: [{ id: 'i3', to: 'Elly', to_id: 'u_elly', state: 'sent', at: T0 }] };
  await G.adoptGroup('Mateo', 'gi_4');
  fixture = { gid: 'gi_4', full: false, max_total: 3, members: [me] };
  await G.syncGroup('Mateo');
  check('ответ без invites — не повод ставить «Can’t make it»', G.groupStatusFor(elly) !== 'declined');

  // 5. Пригласили снова — открытая строка главнее старого исхода.
  fixture = { gid: 'gi_5', full: false, max_total: 3, members: [me],
    invites: [{ id: 'i4', to: 'Ana', to_id: 'u_ana', state: 'sent', at: T0 + 900 }],
    invites_closed: [{ id: 'c', to: 'Ana', to_id: 'u_ana', state: 'expired', closed_at: T0 + 500 }] };
  await G.adoptGroup('Mateo', 'gi_5');
  check('новое приглашение после истёкшего — pending', G.groupStatusFor({ name: 'Ana', id: 'u_ana' }) === 'pending');

  console.log(`\nginvites_closed_test: ${ok} ok, ${failed} fail`);
  process.exitCode = failed ? 1 : 0;
})();
