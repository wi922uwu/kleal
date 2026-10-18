// Поведенческие проверки нынешних компонентов вместо удалённых имён/JSX и ручного стирания TS.
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const ts = require('typescript'), root = path.join(__dirname, '..');
const read = p => fs.readFileSync(path.join(root, p), 'utf8');
const React = { Fragment: 'Fragment', useMemo: fn => fn(), createElement: (type, props, ...children) =>
  typeof type === 'function' ? type({ ...props, children }) : { type, props: { ...props, children } } };
function declarations(file, names, scope = {}) {
  const src = read(file), ast = ts.createSourceFile(file, src, 99, true, ts.ScriptKind.TSX), found = new Map();
  function visit(n) {
    if ((ts.isVariableDeclaration(n) || ts.isFunctionDeclaration(n)) && n.name && names.includes(n.name.getText(ast))) {
      assert.ok(!found.has(n.name.getText(ast)), 'ambiguous ' + n.name.getText(ast));
      const binding = ts.isVariableDeclaration(n) ? (n.parent.flags & ts.NodeFlags.Const ? 'const ' : 'let ') : '';
      found.set(n.name.getText(ast), binding + n.getText(ast).replace(/^export /, '') + ';');
    }
    ts.forEachChild(n, visit);
  }
  visit(ast); names.forEach(n => assert.ok(found.has(n), file + ':' + n));
  const js = ts.transpileModule(names.map(n => found.get(n)).join('\n'), {
    compilerOptions: { target: 7, jsx: ts.JsxEmit.React },
  }).outputText;
  return Function(...Object.keys(scope), js + '\nreturn {' + names.join(',') + '};')(...Object.values(scope));
}
// Берём настоящий callback, переданный экраном в Actions, а не повторяем его в тесте.
function jsxCallback(file, component, prop, scope = {}) {
  const ast = ts.createSourceFile(file, read(file), 99, true, ts.ScriptKind.TSX), found = [];
  function visit(n) {
    if ((ts.isJsxSelfClosingElement(n) || ts.isJsxOpeningElement(n)) && n.tagName.getText(ast) === component) {
      for (const attr of n.attributes.properties) {
        if (ts.isJsxAttribute(attr) && attr.name.getText(ast) === prop) found.push(attr.initializer?.expression);
      }
    }
    ts.forEachChild(n, visit);
  }
  visit(ast); assert.equal(found.length, 1, `${component}.${prop}`); assert.ok(found[0]);
  const js = ts.transpileModule('const callback = ' + found[0].getText(ast), { compilerOptions: { target: 7 } }).outputText;
  return Function(...Object.keys(scope), js + '\nreturn callback;')(...Object.values(scope));
}
const nodes = v => Array.isArray(v) ? v.flatMap(nodes) : v && typeof v === 'object' ? [v, ...nodes(v.props?.children)] : [];
const labels = tree => nodes(tree).map(n => n.props?.label).filter(Boolean);
const copy = new Proxy({}, { get: (_, name) => () => name });
let count = 0;
function test(name, fn) { fn(); count++; console.log('PASS ' + name); }

test('group frame matrix: closed/hold/feedback/started/choices/vote precede general state', () => {
  const { frameOf } = declarations('app/gplan.tsx', ['frameOf']);
  const cases = [[null, 'none'], [{ state: 'cancelled' }, 'closed'], [{ state: 'cancelled', hold: { closed: true } }, 'holdClosed'],
    [{ state: 'done', my_feedback: true }, 'answered'], [{ state: 'done' }, 'closed'],
    [{ state: 'confirmed', feedback_due: true }, 'feedback'], [{ state: 'confirmed', feedback_due: true, my_feedback: true }, 'answered'],
    [{ state: 'confirmed', started: true }, 'now'], [{ state: 'locked' }, 'locked'],
    [{ state: 'below_quorum' }, 'below'], [{ state: 'below_quorum', hold: { ask: true } }, 'holdAsk'],
    [{ state: 'confirmed', stay_or_leave: true }, 'stayOrLeave'], [{ state: 'confirmed', accept_or_leave: true }, 'acceptOrLeave'],
    [{ state: 'proposed', can_fix: true }, 'proposed'], [{ state: 'confirmed' }, 'confirmed']];
  cases.forEach(([plan, expected]) => assert.equal(frameOf({ plan }), expected));
  assert.equal(frameOf({ plan: {}, vote: { state: 'open' } }), 'voteOpen');
  assert.equal(frameOf({ plan: {}, vote: { state: 'closed' }, isOwner: true }), 'voteDecide');
  assert.equal(frameOf({ plan: {}, vote: { state: 'closed' }, isOwner: false }), 'voteWait');
});
test('group actions: no forbidden suggestion, fix only owner, late once, explicit pause recovery', () => {
  const { ActionsFor } = declarations('app/gplan.tsx', ['ActionsFor'], { React, GPLAN: copy, P: 'Primary', S: 'Secondary', Text: 'Text', s: {} });
  const base = { mode: 'view', view: 'proposed', plan: { rounds_used_up: true }, owner: 'a' };
  assert.deepEqual(labels(ActionsFor(base)), ['confirm']);
  assert.deepEqual(labels(ActionsFor({ ...base, isOwner: true, plan: { ...base.plan, can_fix: true } })), ['confirm', 'fix', 'moreTime']);
  assert.deepEqual(labels(ActionsFor({ ...base, plan: {} })), ['confirm', 'suggest']);
  assert.deepEqual(labels(ActionsFor({ ...base, view: 'locked', imLateSent: true })), ['openChat']);
  const pause = labels(ActionsFor({ ...base, view: 'below', isOwner: true, canConvert: true }));
  assert.ok(pause.includes('inviteMore') && pause.includes('switchTo1to1') && pause.includes('cancelPlan'));
});
test('R01: дать ещё время доступно только организатору proposed с rounds_used_up и can_fix', () => {
  const { ActionsFor, frameOf } = declarations('app/gplan.tsx', ['ActionsFor', 'frameOf'], {
    React, GPLAN: copy, P: 'Primary', S: 'Secondary', Text: 'Text', s: {},
  });
  const base = { mode: 'view', owner: 'a', proposer: 'a', isOwner: true,
    plan: { state: 'proposed', rounds_used_up: true, can_fix: true } };
  const render = a => ActionsFor({ ...a, view: frameOf(a) });
  for (const isOwner of [false, true]) for (const rounds_used_up of [undefined, false, true]) for (const can_fix of [undefined, false, true]) {
    const a = { ...base, isOwner, plan: { ...base.plan, rounds_used_up, can_fix } };
    const expected = isOwner && rounds_used_up === true && can_fix === true;
    const rendered = labels(render(a));
    assert.equal(rendered.includes('moreTime'), expected, JSON.stringify(a));
    if (expected) assert.deepEqual(rendered.slice(-2), ['fix', 'moreTime']);
  }
  const otherPlans = [null, {}, { state: 'confirmed' }, { state: 'locked' }, { state: 'below_quorum' },
    { state: 'cancelled' }, { state: 'done' }, { started: true }, { feedback_due: true },
    { feedback_due: true, my_feedback: {} }, { stay_or_leave: true }, { accept_or_leave: true },
    { state: 'below_quorum', hold: { ask: true } }, { state: 'cancelled', hold: { closed: true } }];
  for (const patch of otherPlans) {
    const plan = patch === null ? null : { ...base.plan, ...patch };
    // Пустое серверное состояние не должно наследовать proposed от fixture.
    if (patch && !Object.keys(patch).length) delete plan.state;
    assert.ok(!labels(render({ ...base, plan })).includes('moreTime'), JSON.stringify(patch));
  }
  for (const mode of ['create', 'suggest', 'update', 'link', 'details']) {
    assert.ok(!labels(render({ ...base, mode })).includes('moreTime'), mode);
  }
  for (const state of ['open', 'closed']) for (const isOwner of [false, true]) {
    assert.ok(!labels(render({ ...base, isOwner, vote: { state } })).includes('moreTime'));
  }
  assert.ok(!labels(render({ ...base, hybrid: true, plan: { ...base.plan, details_ready: false } })).includes('moreTime'));
});
test('R01: нажатия вызывают свои обработчики; Confirm/Open chat и Fix сохранены', () => {
  const { ActionsFor } = declarations('app/gplan.tsx', ['ActionsFor'], { React, GPLAN: copy, P: 'Primary', S: 'Secondary', Text: 'Text', s: {} });
  for (const my_response of [undefined, 'confirmed']) {
    const calls = [], args = { mode: 'view', view: 'proposed', isOwner: true, owner: 'a',
      plan: { state: 'proposed', rounds_used_up: true, can_fix: true, my_response } };
    for (const name of ['onMoreTime', 'onConfirm', 'onOpenChat', 'onFix', 'onSuggestOpen']) args[name] = () => calls.push(name);
    const buttons = nodes(ActionsFor(args)).filter(n => n.props?.label);
    assert.deepEqual(buttons.map(n => n.props.label), [my_response ? 'openChat' : 'confirm', 'fix', 'moreTime']);
    for (const [label, handler] of [['moreTime', 'onMoreTime'], ['fix', 'onFix'], [my_response ? 'openChat' : 'confirm', my_response ? 'onOpenChat' : 'onConfirm']]) {
      buttons.find(n => n.props.label === label).props.onPress();
      assert.deepEqual(calls.splice(0), [handler]);
    }
  }
});
test('R01: настоящий callback оставляет экран, deadline и раунды без изменений; RU/EN/ES', () => {
  const calls = [], record = name => (...args) => calls.push([name, ...args]);
  const plan = { id: 'plan-r01', state: 'proposed', rounds_used_up: true, can_fix: true,
    round: 3, max_rounds: 3, deadline: 1800000000, round_ends_at: 1800000000, starts_at: 1800007200,
    rounds_log: [{ round: 3, starts_at: 1800007200 }] };
  const before = JSON.stringify(plan), mode = 'view';
  const spy = prefix => new Proxy({}, { get: (_, name) => record(`${prefix}.${String(name)}`) });
  const actual = jsxCallback('app/gplan.tsx', 'Actions', 'onMoreTime', {
    plan, mode, gid: 'group-r01', me: 'a', router: spy('router'), gapi: spy('gapi'),
    setPlan: record('setPlan'), setMode: record('setMode'), load: record('load'),
    fetch: record('fetch'), setTimeout: record('setTimeout'), setInterval: record('setInterval'),
  });
  const translations = [['ru', 'Дать ещё время'], ['en', 'Give it more time'], ['es', 'Dale más tiempo']];
  for (const [index, [lang, expected]] of translations.entries()) {
    const { GPLAN } = declarations('src/gplan.ts', ['GPLAN'], { T: (...parts) => parts[index] });
    // P/S исполняются тоже: onPress должен дойти до фактической кнопки GlassPill.
    const scopedReact = { ...React, useContext: () => false };
    const { ActionsFor } = declarations('app/gplan.tsx', ['P', 'S', 'ActionsFor'], {
      React: scopedReact, GPLAN, GlassPill: 'GlassPill', DockBusy: {}, Text: 'Text', s: {},
    });
    const args = { mode, view: 'proposed', plan, isOwner: true, owner: 'a', onMoreTime: actual };
    const button = nodes(ActionsFor(args)).find(n => n.props?.label === expected);
    assert.equal(button?.type, 'GlassPill', lang); assert.equal(button.props.onPress, actual);
    assert.equal(button.props.onPress(), undefined); assert.equal(button.props.onPress(), undefined);
    assert.deepEqual(calls, [], lang + ': нет API, навигации, таймера или setter');
    assert.equal(JSON.stringify(plan), before, lang + ': deadline/rounds и остальные поля сохранены');
    assert.equal(args.mode, 'view');
    assert.deepEqual(labels(ActionsFor(args)), [GPLAN.confirm(), GPLAN.fix(), expected]);
  }
});
test('navigation: current tab cannot be picked, home and tab routes collapse stack, home mascot opens Buddy', () => {
  let calls = [];
  const scope = { active: 'messages', pathRef: { current: '/profile' }, stillRef: { current: true }, agentRef: { current: null }, router: {
    navigate: x => calls.push(['navigate', x]), dismissTo: x => calls.push(['dismissTo', x]),
  } };
  const { canPick, go } = declarations('src/components/BottomNav.tsx', ['ROUTE', 'pendingPop', 'canPick', 'goNow', 'go'], scope);
  assert.equal(canPick('messages'), false); assert.equal(canPick('profile'), true);
  go('profile'); assert.deepEqual(calls, [['dismissTo', '/home'], ['navigate', '/profile']]);
  calls = []; go('home'); assert.deepEqual(calls, [['dismissTo', '/home']]);
  calls = []; scope.pathRef.current = '/home'; go('home'); assert.deepEqual(calls, [['navigate', '/buddy']]);
});
test('wizard back: actual detail path, sheets before steps, cancellation before navigation', () => {
  const calls = [], scope = { lastStep: 'place', step: 'place', groupOnline: false, draft: { size: 'one' },
    spotOpen: false, changing: false, groupSizeOpen: false, tzOpen: false, editOpen: false, busy: false,
    ackTimer: { current: null }, clearTimeout() {}, scroller: { current: { scrollTo() {} } },
    router: { back: () => calls.push('exit') } };
  ['setSpotOpen', 'setChanging', 'setTalk', 'setGroupSizeOpen', 'setTzOpen', 'setEditOpen', 'setAck', 'setStep', 'cancelSearch'].forEach(n => scope[n] = value => calls.push([n, value]));
  const get = () => declarations('app/intent.tsx', ['prevStep', 'goBack'], scope);
  const { prevStep } = get();
  assert.deepEqual(['summary', 'place', 'who', 'when', 'size', 'how'].map(x => prevStep(x)), ['place', 'who', 'when', 'size', 'how', null]);
  get().goBack(); assert.deepEqual(calls.splice(0), [['setStep', 'who']]);
  scope.editOpen = true; get().goBack(); assert.deepEqual(calls.splice(0), [['setTzOpen', false], ['setEditOpen', false]]);
  scope.editOpen = false; scope.busy = true; get().goBack(); assert.deepEqual(calls.splice(0), [['cancelSearch', undefined]]);
  scope.busy = false; scope.step = 'how'; get().goBack(); assert.deepEqual(calls.splice(0), ['exit']);
});
test('Buddy stream: one answer, cleans same row, question postpones sheet, ready proposal preserves answer', () => {
  let calls = [];
  const scope = { useCallback: fn => fn, looksLikeIntent: r => !!r.intent,
    intentPhrase: () => 'phrase', intentTitle: () => 'title', intentDesc: () => 'desc', BUDDY: copy };
  ['setSheet', 'setTopic', 'setWhat', 'setSeen', 'setTurns', 'say', 'replaceShown'].forEach(n => scope[n] = (...args) => calls.push([n, ...args]));
  const { finish } = declarations('app/buddy.tsx', ['finish'], scope);
  finish({}, 'answer', 'input', [], 0);
  assert.equal(calls.filter(x => x[0] === 'say').length, 0);
  assert.deepEqual(calls[0], ['replaceShown', 0, 'answer']);
  calls = []; finish({ intent: {} }, 'Question?', 'input', [], 0);
  assert.equal(calls.filter(x => x[0] === 'setSheet' && x[1] === true).length, 0);
  assert.ok(calls.some(x => x[0] === 'replaceShown'));
  calls = []; finish({ intent: {} }, 'Ready.', 'input', [], 0);
  assert.ok(calls.some(x => x[0] === 'replaceShown')); assert.ok(calls.some(x => x[0] === 'setSheet' && x[1]));
});
test('voice hint transform clamps movement and cancellation stops it', () => {
  for (const x of [-500, -79, -10, 100]) for (const cancelling of [0, 1]) {
    const { hintStyle } = declarations('src/voice.tsx', ['hintStyle'], { dx: { value: x }, HINT_TRAVEL: -79,
      cancelHint: { value: cancelling }, useAnimatedStyle: fn => fn(), Extrapolation: { CLAMP: 'clamp' },
      interpolate: (v, input, output) => { const t = Math.max(0, Math.min(1, (v - input[0]) / (input[1] - input[0]))); return output[0] + t * (output[1] - output[0]); },
    });
    const moved = hintStyle.transform[0].translateX;
    assert.ok(moved >= -79 && moved <= 0); if (cancelling) assert.equal(Math.abs(moved), 0);
  }
});
test('MindMap: enter a topic, select/remove its leaf, return without leaving the screen', () => {
  const calls = [], value = { setValue() {} }, animation = { start: fn => fn?.() };
  const scope = { busy: { current: false }, roots: [{ key: 'sports' }], open: 'sports',
    hCommit() {}, hTap() {}, wave() {}, glide: value, shown: value, bloom: value, ease: 'ease',
    Easing: { in: v => v, out: v => v, quad: 'quad' }, Animated: { parallel: () => animation }, run: () => animation,
    setGliding() {}, pageOf: () => ['padel'], setPage: p => calls.push(['page', p]),
    setOpen: k => calls.push(['open', k]), selected: [],
    itemOf: key => ({ key, keys: [key] }), isOn: () => false, onToggle: k => calls.push(['toggle', k]) };
  const load = () => declarations('src/components/MindMap.tsx', ['enter', 'back', 'toggleLeaf'], scope);
  load().enter(0); assert.deepEqual(calls.splice(0), [['page', ['padel']], ['open', 'sports']]);
  scope.busy.current = false; load().toggleLeaf('padel'); assert.deepEqual(calls.splice(0), [['toggle', 'padel']]);
  scope.selected = ['padel']; scope.isOn = () => true;
  load().toggleLeaf('padel'); assert.deepEqual(calls.splice(0), [['toggle', 'padel']]);
  load().back(); assert.deepEqual(calls.splice(0), [['open', null]]); assert.equal(scope.busy.current, false);
});
test('Markdown renders complete and incremental blocks without cursor or faded text', () => {
  const source = read('src/components/Markdown.tsx'), m = { exports: {} };
  const theme = { color: {}, radius: {}, space: {}, type: new Proxy({}, { get: () => ({ fontSize: 16 }) }) };
  const mocks = { react: React, 'react-native': { View: 'View', Text: 'Text', ScrollView: 'ScrollView',
    useWindowDimensions: () => ({ fontScale: 1 }), StyleSheet: { create: x => x } }, '../theme': theme };
  const js = ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.React, module: 1, target: 7, esModuleInterop: true } }).outputText;
  Function('React', 'require', 'module', 'exports', js)(mocks.react, n => { assert.ok(n in mocks, n); return mocks[n]; }, m, m.exports);
  const textOf = v => Array.isArray(v) ? v.map(textOf).join('') : v && typeof v === 'object' ? textOf(v.props?.children) : String(v ?? '');
  for (const [input, expected] of [['hello', ['hello']], ['# Header\n\n- one\n- two', ['Header', 'one', 'two']],
    ['```\ncode\n```', ['code']], ['| A | B |\n| --- | --- |\n| a | b |', ['A', 'B', 'a', 'b']]]) {
    const tree = m.exports.default({ text: input });
    expected.forEach(part => assert.ok(textOf(tree).includes(part), 'missing rendered content: ' + part));
    assert.ok(nodes(tree).every(n => n.type !== 'Animated.Text'));
    assert.ok(!JSON.stringify(tree).includes('caret'));
  }
  for (let i = 1; i <= 5; i++) assert.equal(textOf(m.exports.default({ text: 'hello'.slice(0, i) })), 'hello'.slice(0, i));
});
test('profile navigation uses a fixed-size icon and a 44pt accessible back target', () => {
  let back = 0;
  const scope = { React, View: 'View', Text: 'Text', Pressable: 'Pressable', ScrollView: 'ScrollView',
    IconChevronLeft: 'IconChevronLeft', useSafeAreaInsets: () => ({ top: 0, bottom: 0 }),
    useKeyboardInset: () => 0, dockBottom: () => 0, T: ru => ru,
    useLang: () => 'ru', heading: () => ({}), Ambient: 'Ambient', GLOW_FORM: [],
    StyleSheet: { create: x => x }, color: {}, rad: {}, space: {}, type: {},
    Animated: { View: 'Animated.View' }, Platform: { select: x => x.ios },
    usePress: () => ({}), hTap: () => {}, GlassSurface: 'GlassSurface' };
  // Partner moved the back control into the shared glass component. Execute
  // that real chain and retain the fixed icon / accessible 44pt requirements.
  scope.GlassBack = declarations('src/components/LiquidGlass.tsx', ['s', 'GlassIconButton', 'GlassBack'], scope).GlassBack;
  const { ProfileShell } = declarations('src/components/ProfileShell.tsx', ['s', 'ProfileShell'], scope);
  const tree = ProfileShell({ title: 'Kleal Plus', onBack: () => back++ });
  const button = nodes(tree).find(n => n.props?.accessibilityLabel === 'Назад');
  assert.equal(button.props.accessibilityRole, 'button');
  const surface = nodes(button).find(n => n.type === 'GlassSurface');
  const dimensions = Object.assign({}, ...surface.props.style.filter(Boolean));
  assert.ok(dimensions.width >= 44 && dimensions.height >= 44);
  const icon = nodes(button).find(n => n.type === 'IconChevronLeft');
  assert.equal(icon.props.size, 22);
  assert.equal(nodes(button).some(n => n.type === 'Text'), false, 'an icon must not scale as a glyph');
  button.props.onPress(); assert.equal(back, 1);
});
console.log(`${count} актуальных поведенческих контрактов пройдены; native rendering не проверяется.`);
