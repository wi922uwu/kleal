/** Render/gesture contracts, not a substitute for Android GPU/device QA. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const ROOT = process.env.ONBOARDING_SOURCE_ROOT || path.join(__dirname, '..');
const read = file => fs.readFileSync(path.join(ROOT, file), 'utf8');
const flat = value => Array.isArray(value) ? Object.assign({}, ...value.map(flat)) : (value || {});
const nodes = tree => !tree || typeof tree !== 'object' ? [] : [tree, ...(tree.children || []).flatMap(nodes)];
const effects = [];
const cleanups = [];
let width = 360;
let language = 'ru';
let haptics = 0;
let appStateChange;
const React = {
  createElement: (type, props, ...children) => ({ type, props: props || {}, children: children.flat(Infinity) }),
  forwardRef: fn => fn,
  useEffect: fn => effects.push(fn),
  useCallback: fn => fn,
  useMemo: fn => fn(),
  useRef: value => ({ current: value }),
  useState: value => [value, () => {}],
};
class Value {
  constructor(value) { this.value = value; this.listeners = new Map(); }
  setValue(value) { this.value = value; this.listeners.forEach(fn => fn({ value })); }
  stopAnimation(fn) { fn?.(this.value); }
  addListener(fn) { this.listeners.set(fn, fn); return fn; }
  removeListener(fn) { this.listeners.delete(fn); }
  interpolate({ inputRange: input, outputRange: output }) {
    return { get value() {
      const v = this.source.value;
      let i = 0;
      while (i < input.length - 2 && v > input[i + 1]) i++;
      const t = Math.max(0, Math.min(1, (v - input[i]) / (input[i + 1] - input[i])));
      return output[i] + t * (output[i + 1] - output[i]);
    }, source: this };
  }
}
const animate = (value, opts) => ({ start(fn) { if (opts.toValue != null) value.setValue(opts.toValue); fn?.({ finished: true }); } });
const native = {
  View: 'View', Text: 'Text', ScrollView: 'ScrollView', Image: 'Image', Pressable: 'Pressable',
  KeyboardAvoidingView: 'KeyboardAvoidingView', ActivityIndicator: 'ActivityIndicator',
  StyleSheet: { create: x => x, absoluteFill: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 }, hairlineWidth: 1 },
  Platform: { OS: 'android', select: x => x.android },
  useWindowDimensions: () => ({ width, height: 640, fontScale: 2 }),
  AppState: { currentState: 'active', addEventListener: (_, fn) => { appStateChange = fn; return { remove() {} }; } },
  PanResponder: { create: handlers => ({ panHandlers: handlers }) },
  Animated: { Value, View: 'Animated.View', Text: 'Animated.Text', createAnimatedComponent: x => x,
    spring: animate, timing: animate, decay: animate, sequence: steps => ({ start: () => steps.forEach(s => s.start()) }) },
};
const i18n = { useLang: () => language, T: (ru, en, es) => language === 'ru' ? ru : language === 'es' ? es || en : en };
const modules = { react: React, 'react-native': native, 'react-native-svg': { __esModule: true, default: 'Svg', Line: 'Line' },
  'expo-blur': { BlurView: 'BlurView' }, 'expo-audio': { createAudioPlayer: () => null },
  'react-native-safe-area-context': { useSafeAreaInsets: () => ({ top: 24, bottom: 32 }) },
  '../i18n': i18n, '../api': { mediaUrl: x => x }, '../haptics': { hTick: () => haptics++, hCommit() {}, hTap() {} },
  './Composer': { Composer: 'Composer' }, './Ambient': { Ambient: 'Ambient' }, './Logo': { LogoFace: 'LogoFace' },
  './Markdown': { __esModule: true, default: 'Markdown' }, './Thinking': { Thinking: 'Thinking' },
  './icons': { IconAlertTriangle: 'IconAlertTriangle' },
};
function load(file, extra = {}) {
  const output = ts.transpileModule(read(file), { compilerOptions: { jsx: ts.JsxEmit.React, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true } }).outputText;
  const mod = { exports: {} };
  const imports = { ...modules, ...extra };
  Function('require', 'module', 'exports', output)(name => {
    if (name.endsWith('.wav')) return 1;
    assert(name in imports, `Unmocked import ${name} in ${file}`);
    return imports[name];
  }, mod, mod.exports);
  return mod.exports;
}
modules['../theme'] = load('src/theme.ts');
modules['../age-ruler'] = load('src/age-ruler.ts');
const { AgeDial } = load('src/components/AgeDial.tsx');
let checks = 0;
function check(label, fn) { fn(); checks++; console.log(`PASS ${label}`); }

check('age 33 renders 63 native ticks outside an SVG mask', () => {
  const tree = AgeDial({ value: 33, onChange() {} });
  const ticks = nodes(tree).filter(n => /^age-ruler-tick-/.test(n.props.testID || ''));
  assert.equal(ticks.length, 63);
  assert(ticks.every(n => n.type === 'Animated.View'));
  assert(!/\bMask\b|AnimatedGroup/.test(read('src/components/AgeDial.tsx')));
  assert(nodes(tree).some(n => flat(n.props.style).overflow === 'hidden'));
  assert(nodes(tree).some(n => n.props.importantForAccessibility === 'no-hide-descendants'
    && flat(n.props.style).position === 'absolute'));
});
check('18..80 at 280/320/360/390/768pt: selected tick centered, visible neighbours and fixed edges', () => {
  for (width of [280, 320, 360, 390, 768]) {
    for (let age = 18; age <= 80; age++) {
      const tree = AgeDial({ value: age, onChange() {} });
      const ticks = nodes(tree).filter(n => /^age-ruler-tick-/.test(n.props.testID || ''));
      const selected = ticks.find(n => n.props.testID === `age-ruler-tick-${age}`);
      const s = flat(selected.props.style);
      assert.equal(s.left + s.width / 2 + s.transform[0].translateX.value, width / 2);
      assert.equal(s.opacity.value, 1);
      assert(ticks.filter(n => flat(n.props.style).opacity.value >= 0.5).length >= 5);
      for (const tick of ticks) {
        const t = flat(tick.props.style);
        const x = t.left + t.width / 2 + t.transform[0].translateX.value;
        if (x <= 0 || x >= width) assert.equal(t.opacity.value, 0);
        assert(t.width >= 1.5);
      }
    }
  }
  width = 360;
});
check('half-year drag stays continuous, releases snap, bounds and background release remain', () => {
  effects.length = 0;
  const changes = [], dragging = [];
  const tree = AgeDial({ value: 33, onChange: v => changes.push(v), onDragChange: v => dragging.push(v) });
  effects.splice(0).forEach(fn => { const done = fn(); if (done) cleanups.push(done); });
  const tick = flat(nodes(tree).find(n => n.props.testID === 'age-ruler-tick-33').props.style);
  tree.props.onPanResponderGrant();
  tree.props.onPanResponderMove(null, { dx: -9 });
  assert.equal(tick.transform[0].translateX.value, -279);
  assert.equal(changes.at(-1), 34);
  tree.props.onPanResponderRelease(null, { vx: 0 });
  assert.equal(tick.transform[0].translateX.value, -288);
  assert.deepEqual(dragging, [true, false]);
  assert(haptics > 0);
  tree.props.onAccessibilityAction({ nativeEvent: { actionName: 'decrement' } });
  assert.equal(changes.at(-1), 33);
  tree.props.onPanResponderGrant();
  tree.props.onPanResponderMove(null, { dx: 5000 });
  assert.equal(changes.at(-1), 18);
  appStateChange('background');
  assert.equal(dragging.at(-1), false);
  cleanups.splice(0).forEach(fn => fn());
});

// Use the actual localized map strings without importing the unrelated onboarding parser.
const onbSource = read('src/onboarding.ts');
const hobbyStart = onbSource.indexOf('export const STEP_HOBBIES');
assert(hobbyStart >= 0);
const hobbyEnd = onbSource.indexOf('\n};', hobbyStart);
const hobbyJS = ts.transpileModule(onbSource.slice(hobbyStart, hobbyEnd + 3), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
const hobbyModule = { exports: {} };
Function('T', 'exports', hobbyJS)(i18n.T, hobbyModule.exports);
modules['../onboarding'] = hobbyModule.exports;
modules['./Glass'] = { GlassPill: 'GlassPill' };
const { InterestMapActions } = load('src/components/InterestMapActions.tsx');
check('0..2 remain disabled; 3/11/40 confirm ALL keys; own path works without raising minimum', () => {
  for (const count of [0, 1, 2, 3, 11, 40]) {
    const selected = Array.from({ length: count }, (_, i) => `interest-${i}`);
    const calls = [];
    const tree = InterestMapActions({ selected, onDone: (...args) => calls.push(args) });
    const buttons = nodes(tree).filter(n => n.type === 'GlassPill');
    assert.equal(buttons.length, 2);
    assert.equal(buttons[1].props.disabled, count < 3);
    buttons[1].props.onPress();
    assert.deepEqual(calls, count < 3 ? [] : [[selected]]);
    buttons[0].props.onPress();
    assert.deepEqual(calls.at(-1), [selected, true]);
    assert(buttons.every(n => n.props.style.height === 'auto' && n.props.style.minHeight >= 48 && n.props.labelLines > 1));
  }
});
check('RU/EN/ES labels retain count and actions after removal', () => {
  for (language of ['ru', 'en', 'es']) {
    const buttons = nodes(InterestMapActions({ selected: Array(11).fill('x'), onDone() {} })).filter(n => n.type === 'GlassPill');
    assert(buttons[0].props.label.length);
    assert(buttons[1].props.label.includes('11'));
    assert.equal(nodes(InterestMapActions({ selected: ['a', 'b'], onDone() {} })).filter(n => n.type === 'GlassPill')[1].props.disabled, true);
  }
});
const { GlassPill, GlassChip } = load('src/components/Glass.tsx');
check('wrapped Glass action grows and default one-line buttons are unchanged', () => {
  const action = GlassPill({ label: 'Long action', labelLines: 3, style: { height: 'auto', minHeight: 48 } });
  const label = nodes(action).find(n => n.type === 'Text');
  assert.equal(label.props.numberOfLines, 3);
  assert.equal(flat(label.props.style).flexShrink, 1);
  assert.equal(flat(label.props.style).lineHeight, undefined);
  assert.equal(flat(action.props.style({ pressed: false })).height, 'auto');
  assert.equal(nodes(GlassPill({ label: 'Default' })).find(n => n.type === 'Text').props.numberOfLines, 1);
});
check('selected map chips wrap/grow with 44pt targets; other chips keep their default', () => {
  let removed = false;
  const chip = GlassChip({ label: 'Long selected interest', on: true, wrapLabel: true, onPress: () => { removed = true; } });
  const style = flat(chip.props.style({ pressed: false }));
  assert.equal(style.height, 'auto');
  assert.equal(style.minHeight, 44);
  assert.equal(style.maxWidth, '100%');
  assert.equal(nodes(chip).find(n => n.type === 'Text').props.numberOfLines, undefined);
  assert.equal(flat(nodes(chip).find(n => n.type === 'Text').props.style).lineHeight, undefined);
  chip.props.onPress();
  assert(removed);
  assert.equal(nodes(GlassChip({ label: 'Default' })).find(n => n.type === 'Text').props.numberOfLines, 1);
});
const { ChatShell } = load('src/components/ChatShell.tsx');
check('footer is a sibling after bounded ScrollView and before safe-area Composer, never absolute', () => {
  const footer = { type: 'TestActions', props: {}, children: [] };
  const tree = ChatShell({ title: 'Profile', pct: 50, thread: [], widget: { type: 'Widget' }, footer }, null);
  const all = nodes(tree);
  const scroll = all.find(n => n.type === 'ScrollView');
  assert.equal(flat(scroll.props.style).flex, 1);
  assert.equal(flat(scroll.props.style).minHeight, 0);
  assert(!nodes(scroll).includes(footer));
  assert.equal(scroll.props.keyboardShouldPersistTaps, 'handled');
  assert.equal(scroll.props.keyboardDismissMode, 'on-drag');
  assert(all.indexOf(scroll) < all.indexOf(footer));
  const composer = all.find(n => n.type === 'Composer');
  assert(all.indexOf(footer) < all.indexOf(composer));
  assert.equal(composer.props.bottomInset, 32);
  const holder = all.find(n => n.children?.includes(footer));
  assert.equal(flat(holder.props.style).flexShrink, 0);
  assert.notEqual(flat(holder.props.style).position, 'absolute');
  const standard = ChatShell({ title: 'Chat', pct: null, thread: [] }, null);
  const standardScroll = nodes(standard).find(n => n.type === 'ScrollView');
  assert.equal(standardScroll.props.style, undefined);
  assert.equal(standardScroll.props.keyboardDismissMode, undefined);
});
check('actual onboarding routes actions out of long map/chips widget without capping selection', () => {
  const chat = read('app/chat.tsx');
  assert.match(chat, /footer=\{step === 'hobbies' && mapOpen && !queue && !typing/);
  assert.match(chat, /<InterestMapActions selected=\{mapPicked\} onDone=\{onMapDone\}/);
  const parsed = ts.createSourceFile('chat.tsx', chat, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const hobby = parsed.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === 'HobbyW');
  const mapBranch = hobby.body.statements.find(n => ts.isIfStatement(n) && n.expression.getText(parsed) === 'mapOpen');
  const widget = mapBranch.thenStatement.getText(parsed);
  assert.match(widget, /picked\.map\(/);
  assert.match(widget, /<GlassChip[^\n]*wrapLabel/);
  assert(!/picked\.slice\(/.test(widget));
  assert.match(widget, /onPress=\{\(\) => onMapPick\?\.\(k\)\}/);
  assert(!/<Cta[^]*?STEP_HOBBIES\.mapCount/.test(widget));
});
console.log(`\n${checks} onboarding layout/gesture contracts passed (native rendering not simulated).`);
