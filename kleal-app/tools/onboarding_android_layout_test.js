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
  // Секции-якоря анкеты: окно ленты раздаётся контекстом, ref оболочки — через useImperativeHandle.
  createContext: value => ({ Provider: 'ContextProvider', _value: value }),
  useContext: ctx => ctx._value,
  useImperativeHandle: () => {},
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
  Easing: { out: e => e, in: e => e, cubic: t => t, quad: t => t },
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
  './icons': { IconAlertTriangle: 'IconAlertTriangle', IconClose: 'IconClose' },
  '../interest-label': { interestLabel: k => `label:${k}` },
  // Жидкое стекло и пружина нажатия (макет «First run»): в тесте вёрстки — пустые обёртки.
  'react-native-reanimated': (() => {
    const chain = new Proxy({}, { get: () => () => chain });
    return { __esModule: true, default: { View: 'Animated.View', Text: 'Animated.Text', createAnimatedComponent: x => x },
      useSharedValue: value => ({ value }), useAnimatedStyle: () => ({}), withSpring: v => v, withTiming: v => v, Easing: chain, useReducedMotion: () => false,
      FadeInDown: chain, FadeIn: chain, ZoomIn: chain };
  })(),
  './LiquidGlass': { GlassSurface: 'GlassSurface', GlassBack: 'GlassBack', riseIn: () => undefined, LIQUID: false, usePress: () => ({ style: {}, onPressIn() {}, onPressOut() {} }) },
  './Blob': { Blob: 'Blob' },
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
// Деления едут ОДНИМ слоем (нативный сдвиг слоя, а не 63 своих): позиция деления = его left + сдвиг слоя.
const trackX = tree => flat(nodes(tree).find(n => n.props.importantForAccessibility === 'no-hide-descendants'
  && flat(n.props.style).transform).props.style).transform[0].translateX;

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
      const shift = trackX(tree).value;
      assert.equal(s.left + s.width / 2 + shift, width / 2);
      assert.equal(s.opacity.value, 1);
      assert(ticks.filter(n => flat(n.props.style).opacity.value >= 0.5).length >= 5);
      for (const tick of ticks) {
        const t = flat(tick.props.style);
        const x = t.left + t.width / 2 + shift;
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
  const tick = { transform: [{ translateX: trackX(tree) }] };
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
  // 27.09: протяжка за 18 — «резинка», не дальше 24 точек за краем; отпустил — ровно к краю.
  assert(tick.transform[0].translateX.value > 0 && tick.transform[0].translateX.value <= 24);
  tree.props.onPanResponderRelease(null, { vx: 0 });
  assert.equal(tick.transform[0].translateX.value + 0, 0);
  // Сильный взмах к 80 и дальше встаёт ровно на 80, а не за шкалой.
  tree.props.onPanResponderGrant();
  tree.props.onPanResponderMove(null, { dx: -300 });
  tree.props.onPanResponderRelease(null, { vx: -40 });
  assert.equal(tick.transform[0].translateX.value, -(80 - 18) * 18);
  assert.equal(changes.at(-1), 80);
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
check('0..2 remain disabled; 3/11/40 confirm ALL keys; «add your own» stays on the map', () => {
  for (const count of [0, 1, 2, 3, 11, 40]) {
    const selected = Array.from({ length: count }, (_, i) => `interest-${i}`);
    const calls = [];
    let own = 0;
    const tree = InterestMapActions({ selected, onDone: (...args) => calls.push(args), onOwn: () => own++ });
    const buttons = nodes(tree).filter(n => n.type === 'GlassPill');
    assert.equal(buttons.length, 2);
    assert.equal(buttons[1].props.disabled, count < 3);
    buttons[1].props.onPress();
    assert.deepEqual(calls, count < 3 ? [] : [[selected]]);
    // «Добавить своё» НЕ закрывает карту: только ставит курсор в поле, выбранное не отправляется.
    const before = calls.length;
    buttons[0].props.onPress();
    assert.equal(own, 1);
    assert.equal(calls.length, before);
    assert(buttons.every(n => n.props.style.height === 'auto' && n.props.style.minHeight >= 48 && n.props.labelLines > 1));
  }
});
check('own word being parsed shows in the tray; an ambiguous one asks with options', () => {
  const picked = [], skipped = [];
  const option = { canonical: 'padel', label: 'падел', token: 't1' };
  const tree = InterestMapActions({ selected: ['chess'], onDone() {}, busy: ['падел'],
    ask: { text: 'мяч', question: 'Что именно?', options: [option] },
    onAskPick: o => picked.push(o), onAskSkip: () => skipped.push(1) });
  const all = nodes(tree);
  assert(all.some(n => n.props.testID === 'interest-map-tray'));
  assert(all.some(n => n.type === 'ActivityIndicator'));
  assert(all.some(n => n.props.testID === 'interest-map-ask'));
  const presses = all.filter(n => n.type === 'Pressable' && n.props.accessibilityRole === 'button' && !n.props.accessibilityLabel);
  presses[0].props.onPress();
  presses[1].props.onPress();
  assert.deepEqual(picked, [option]);
  assert.equal(skipped.length, 1);
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
check('onboarding is split into anchor sections: H1 each, bubbles in their own section, widget only in the last', () => {
  const widget = { type: 'StepWidget', props: {}, children: [] };
  const thread = [
    { who: 'bot', text: 'q-name', at: '1', sec: 'start' },
    { who: 'me', text: 'Mateo', at: '1', sec: 'start' },
    { who: 'bot', text: 'q-age', at: '2', sec: 'basics' },
  ];
  const sections = [{ key: 'start', title: 'Имя' }, { key: 'basics', title: 'Возраст и пол' }];
  const tree = ChatShell({ title: 'Profile', pct: 10, thread, sections, widget }, null);
  const scroll = nodes(tree).find(n => n.type === 'ScrollView');
  // Магнит: быстрое торможение и точки притяжения (сами точки появляются после замеров).
  assert.equal(scroll.props.decelerationRate, 'fast');
  const secs = scroll.children.filter(n => n && n.props && typeof n.props.onLayout === 'function');
  assert.equal(secs.length, 2);
  const h1s = nodes(scroll).filter(n => n.props && n.props.accessibilityRole === 'header');
  assert.deepEqual(h1s.map(n => n.children.join('')), ['Имя', 'Возраст и пол']);
  const texts = sec => JSON.stringify(sec);
  assert(texts(secs[0]).includes('Mateo') && !texts(secs[0]).includes('q-age'));
  assert(texts(secs[1]).includes('q-age') && !texts(secs[1]).includes('Mateo'));
  assert(!nodes(secs[0]).includes(widget) && nodes(secs[1]).includes(widget));
  // Без секций лента прежняя, сплошная.
  const plain = ChatShell({ title: 'Chat', pct: null, thread }, null);
  assert.equal(nodes(plain).filter(n => n.props && n.props.accessibilityRole === 'header').length, 0);
  // Анкета помечает реплику этапом и отдаёт секции оболочке; своей прокрутки «в самый низ» у неё нет.
  const chat = read('app/chat.tsx');
  // Этап снимается ДО setThread: функция обновления выполняется позже, после goto, и ответ
  // уехал бы в секцию следующего этапа.
  assert.match(chat, /const sec = stepRef\.current;\s*setThread\(\(t\) => \[\.\.\.t, \{ who, text, at: now\(\), photo, sec \}\]\)/);
  assert(!/setThread\(\(t\) => \[\.\.\.t, \{[^}]*stepRef\.current/.test(chat));
  assert.match(chat, /sections=\{sections\}/);
  assert(!/scroller\.current\?\.scrollToEnd/.test(chat));
});
check('actual onboarding routes actions out of long map/chips widget without capping selection', () => {
  const chat = read('app/chat.tsx');
  assert.match(chat, /footer=\{step === 'hobbies' && mapOpen && !queue && !typing/);
  assert.match(chat, /<InterestMapActions\s+selected=\{mapPicked\}\s+onDone=\{onMapDone\}/);
  const parsed = ts.createSourceFile('chat.tsx', chat, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const hobby = parsed.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === 'HobbyW');
  const mapBranch = hobby.body.statements.find(n => ts.isIfStatement(n) && n.expression.getText(parsed) === 'mapOpen');
  const widget = mapBranch.thenStatement.getText(parsed);
  // Выбранное переехало из ленты в корзину над кнопками (InterestMapActions): под картой оно
  // было за краем экрана. В ленте карты чипов и кнопок больше нет — ей нечем выталкивать действия.
  assert(!/picked\.map\(/.test(widget) && !/<GlassChip/.test(widget));
  assert(!/<Cta[^]*?STEP_HOBBIES\.mapCount/.test(widget));
  assert.match(chat, /<InterestMapActions\s+selected=\{mapPicked\}\s+onDone=\{onMapDone\}\s+onRemove=\{toggleMapPick\}/);
  // Своё слово на карте идёт в корзину, а не в разговор: поле ввода зовёт addOwnOnMap, пока карта открыта.
  assert.match(chat, /onSend=\{onComposer\}/);
  assert.match(chat, /if \(step === 'hobbies' && mapOpen\) \{ addOwnOnMap\(text\); return; \}/);
  assert(!/botAfter\(STEP_HOBBIES\.ownAsk\(\)\)/.test(chat));
});
check('tray shows ALL picked (no cap), each removable, scrolls sideways instead of growing', () => {
  const removed = [];
  const picked = Array.from({ length: 40 }, (_, i) => `interest-${i}`);
  const tree = InterestMapActions({ selected: picked, onDone() {}, onRemove: k => removed.push(k) });
  const tray = nodes(tree).find(n => n.props.testID === 'interest-map-tray');
  assert.equal(tray.type, 'ScrollView');
  assert.equal(tray.props.horizontal, true);
  const tags = nodes(tray).filter(n => n.type === 'Pressable');
  assert.equal(tags.length, 40);
  tags[7].props.onPress();
  assert.deepEqual(removed, ['interest-7']);
  assert(nodes(tags[0]).some(n => n.type === 'Text' && n.children.includes('label:interest-0')));
  assert.equal(nodes(InterestMapActions({ selected: [], onDone() {} })).find(n => n.props.testID === 'interest-map-tray'), undefined);
});
console.log(`\n${checks} onboarding layout/gesture contracts passed (native rendering not simulated).`);
