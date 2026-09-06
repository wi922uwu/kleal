// Run with node tools/welcome_flow_test.js. No server or account writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
function load(file, overrides = {}) {
  const mod = { exports: {} };
  const code = ts.transpileModule(read(file), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  new Function('require', 'module', 'exports', code)(
    (id) => id in overrides ? overrides[id] : require(id), mod, mod.exports);
  return mod.exports;
}
const { createWelcomeSession, welcomeAxis, welcomeTarget, welcomePull, welcomePullComplete } = load('src/welcome.ts');
let count = 0;
function check(name, fn) { fn(); count++; console.log('PASS ' + name); }
for (const lang of ['ru', 'en']) {
  const { SLIDES } = load('src/onboarding.ts', { './i18n': { T: (ru, en) => lang === 'ru' ? ru : en } });
  check(lang + ' exact photo3 -> photo2 -> photo1 order', () => {
    const slides = SLIDES();
    assert.deepEqual(slides.map(s => s.art), ['searching', 'primary', 'match']);
    assert.match(slides[0].title, lang === 'ru' ? /^Ищем людей/ : /^Find people/);
    assert.match(slides[1].title, lang === 'ru' ? /^Скажи Kleal/ : /^Tell Kleal/);
    assert.match(slides[2].title, lang === 'ru' ? /^Меньше переписки/ : /^Less social/);
  });
}
check('fresh focus and re-entry reset ephemeral index to zero', () => {
  const session = createWelcomeSession();
  assert.equal(session.begin(), null);
  session.focus();
  session.settle(session.begin(), 2);
  assert.equal(session.index, 2);
  session.blur();
  session.focus();
  assert.equal(session.index, 0);
  assert.equal(session.available, true);
});
check('late slide callback cannot change re-entered screen', () => {
  const session = createWelcomeSession();
  session.focus();
  const stale = session.begin();
  session.blur();
  session.focus();
  assert.equal(session.settle(stale, 2), false);
  assert.equal(session.index, 0);
});
check('late wave callback after blur cannot navigate', () => {
  const session = createWelcomeSession();
  session.focus();
  const token = session.begin();
  session.blur();
  assert.equal(session.complete(token), false);
});
check('double tap / duplicate completion navigates once', () => {
  const session = createWelcomeSession();
  session.focus();
  const token = session.begin();
  assert.equal(session.begin(), null);
  assert.equal(session.complete(token), true);
  assert.equal(session.complete(token), false);
  assert.equal(session.begin(), null);
});
check('resize / reduce motion interruption cancels in-flight navigation', () => {
  const session = createWelcomeSession();
  session.focus();
  const token = session.begin();
  session.interrupt();
  assert.equal(session.complete(token), false);
  assert.equal(session.available, true);
});
check('axis lock distinguishes horizontal/vertical/ambiguous and first slides', () => {
  assert.equal(welcomeAxis(-60, 10, true), 'horizontal');
  assert.equal(welcomeAxis(60, -10, true), 'horizontal');
  assert.equal(welcomeAxis(10, -60, true), 'vertical');
  assert.equal(welcomeAxis(10, -60, false), null);
  assert.equal(welcomeAxis(30, -30, true), null);
  assert.equal(welcomeAxis(2, -3, true), null);
});
check('swipe threshold, velocity, boundaries and last-page backward gesture', () => {
  assert.equal(welcomeTarget(0, -80, -0.1), 1);
  assert.equal(welcomeTarget(1, -10, -0.8), 2);
  assert.equal(welcomeTarget(1, -10, -0.1), 1);
  assert.equal(welcomeTarget(1, -2, -2), 1);
  assert.equal(welcomeTarget(2, 80, 0.1), 1);
  assert.equal(welcomeTarget(0, 80, 1), 0);
  assert.equal(welcomeTarget(2, -80, -1), 2);
});
check('short/cancelled pull never completes; finger threshold is deterministic', () => {
  for (const dy of [10, 0, -1, -30, -69]) assert.equal(welcomePullComplete(dy), false);
  for (const dy of [-70, -180]) assert.equal(welcomePullComplete(dy), true);
  assert.equal(welcomePull(-42, 800), 42);
  assert.equal(welcomePull(-900, 800), 800);
  assert.equal(welcomePull(30, 800), -10);
});
check('screen keeps account read-only and gates completed users', () => {
  const screen = read('app/intro.tsx');
  assert.doesNotMatch(screen, /\bpatch\(|\breset\(|st\.slide|AsyncStorage/);
  assert.match(screen, /account\.login && account\.done/);
  assert.match(screen, /router\.replace\('\/home'\)/);
  assert.match(screen, /session\.complete\(token\)\) router\.navigate\('\/auth'\)/);
  assert.match(read('app/index.tsx'), /st\.login && st\.done \? '\/home' : '\/intro'/);
});
check('fixed photo, stable panes and accessible alternatives are wired', () => {
  const screen = read('app/intro.tsx');
  assert.equal((screen.match(/<Image /g) || []).length, 1);
  assert.match(screen, /key=\{slide\.art\}/);
  assert.match(screen, /style=\{\[s\.sheet, sheetStyle\]\}/);
  assert.match(screen, /style=\{\[s\.pages,/);
  assert.match(screen, /onStartShouldSetPanResponder: \(\) => false/);
  assert.match(screen, /onPanResponderTerminate:/);
  assert.match(screen, /reduceMotionChanged/);
  assert.match(screen, /onAccessibilityAction=/);
  assert.match(screen, /minHeight: 44/);
  assert.match(screen, /onPress=\{start\}/);
  assert.match(screen, /cancelAnimation\(progress\)/);
  assert.match(screen, /if \(finished\) runOnJS/);
  assert.match(screen, /accessibilityValue=\{\{ text:/, 'pager announces a page, not an incorrect percentage');
  assert.match(screen, /key=\{measurementKey\}/, 'native text reflows after a live Dynamic Type change');
  const layout = read('app/_layout.tsx');
  assert.match(layout.slice(layout.indexOf('const ART_FIRST'), layout.indexOf('const ART_HOME')), /usp-friends-v2/);
});
console.log(`All ${count} welcome checks passed`);
