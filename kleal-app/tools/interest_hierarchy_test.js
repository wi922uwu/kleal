// Actual onMapDone + generated shared registry; --json feeds the real matching probe.
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), ts = require('typescript');
const root = path.join(__dirname, '..');
function load(file) {
  const mod = { exports: {} };
  const js = ts.transpileModule(fs.readFileSync(path.join(root, file), 'utf8'), {
    compilerOptions: { target: 7, module: 1 },
  }).outputText;
  Function('require', 'module', 'exports', js)(name => name === './i18n' ? { T: ru => ru }
    : load(path.join(path.dirname(file), name + '.ts')), mod, mod.exports);
  return mod.exports;
}
const { interestChain } = load('src/interests-wheel.ts');
const src = fs.readFileSync(path.join(root, 'app/chat.tsx'), 'utf8');
const ast = ts.createSourceFile('chat.tsx', src, 99, true, ts.ScriptKind.TSX);
let handler, finish;
function visit(n) {
  if (ts.isVariableDeclaration(n) && n.name.getText(ast) === 'onMapDone') handler = n.getText(ast);
  if (ts.isVariableDeclaration(n) && n.name.getText(ast) === 'finishHobbies') finish = n.getText(ast);
  ts.forEachChild(n, visit);
}
visit(ast); assert.ok(handler);
const js = ts.transpileModule('const ' + handler + ';', { compilerOptions: { target: 7 } }).outputText;
const fixtures = [];
for (const selected of [['padel'], ['padel', 'tennis'], ['sports'], ['music'], ['outdoors'], ['my_new_interest']]) {
  let stored = [], displayed = [], sent = '', pushed = [];
  const scope = { interestChain, ownTok: { current: {} }, addConfirmedInterest() {}, setOwnAsk() {}, setOwnNote() {},
    get: () => stored, set: (_p, v) => { stored = v; }, setJustAdded: fn => { displayed = fn(displayed); },
    pushInterests: () => { pushed = [...stored]; }, setMapOpen() {}, interestLabel: k => k,
    send: text => { sent = text; }, botAfter() {} };
  const onMapDone = Function(...Object.keys(scope), js + ';return onMapDone;')(...Object.values(scope));
  onMapDone(selected); onMapDone(selected);
  assert.equal(new Set(stored).size, stored.length, 'idempotent merge');
  assert.deepEqual(displayed, selected, 'map tray stays the selected leaves');
  assert.equal(sent, selected.join(', '), 'agent asks about selected leaves, not inferred parents');
  assert.deepEqual(pushed, stored, 'complete chain delivered');
  let count;
  Function('justAdded', 'botAfter', 'STEP_HOBBIES', 'setTimeout',
    ts.transpileModule('const ' + finish + ';finishHobbies();', { compilerOptions: { target: 7 } }).outputText)(
    displayed, () => {}, { done: n => { count = n; return ''; } }, () => {});
  assert.equal(count, selected.length, 'completion copy counts selected leaves, not matching parents');
  if (selected[0] === 'padel') assert.deepEqual(stored, ['sports', 'racket', ...selected]);
  else assert.deepEqual(stored, selected, 'roots/unknown words do not acquire unrelated ancestors');
  fixtures.push({ selected, stored, displayed, sent });
}
assert.deepEqual(interestChain('more'), ['more'], 'ambiguous service node is not assigned an arbitrary topic');
if (process.argv.includes('--json')) process.stdout.write(JSON.stringify(fixtures));
else console.log('PASS interest hierarchy: real onMapDone, exact parents/no siblings, dedupe, leaf-only tray/agent, roots/unknown/ambiguous');
