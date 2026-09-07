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
    fileName: file,
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.React, esModuleInterop: true },
  }).outputText;
  new Function('require', 'module', 'exports', code)(
    (id) => id in overrides ? overrides[id] : require(id), mod, mod.exports);
  return mod.exports;
}
const welcome = load('src/welcome.ts');
const { createWelcomeSession, welcomeAxis, welcomeTarget, welcomePull, welcomePullComplete, welcomeWaveContains } = welcome;
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
  assert.match(screen, /style=\{\[s\.sheet, \{ height: sheetHeight \}\]\}/);
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
check('SVG hit area includes both edges/crest/fill but excludes the white corners', () => {
  for (const width of [320, 375, 393, 430]) {
    for (const [x, y] of [[0, 833], [width, 833], [width / 2, 721], [width / 2, 880]]) {
      assert.equal(welcomeWaveContains(x, y, width, 700, 900), true);
    }
    assert.equal(welcomeWaveContains(0, 800, width, 700, 900), false);
    assert.equal(welcomeWaveContains(width, 800, width, 700, 900), false);
    assert.equal(welcomeWaveContains(width / 2, 719, width, 700, 900), false);
    assert.equal(welcomeWaveContains(width / 2, 679, width, 700, 900, 42), true);
  }
  assert.equal(welcomeWaveContains(-1, 850, 390, 700, 900), false);
  assert.equal(welcomeWaveContains(20, 901, 390, 700, 900), false);
  assert.equal(welcomeWaveContains(20, 850, 0, 700, 900), false);
});

// Exercise Intro's actual PanResponder config, including RN's pre-grant y0=0 and
// dx/dy reset on grant. Helper-only axis tests could not detect the phone defect.
function renderIntro({ index = 2, width = 390, height = 844, fontScale = 1, reduced = false } = {}) {
  let config, stateIndex = 0;
  const session = createWelcomeSession(), shared = [], animations = [], springs = [], calls = [];
  const effects = [];
  const react = {
    createElement: (type, props, ...children) => ({ type, props: props || {}, children }),
    useRef: (current) => ({ current }), useMemo: (fn) => fn(), useCallback: (fn) => fn,
    useEffect: () => {},
    useState: (initial) => [stateIndex++ === 1 ? index : initial, () => {}],
  };
  const i18n = { useLang: () => 'ru', T: (ru) => ru };
  const copy = load('src/onboarding.ts', { './i18n': i18n });
  const { default: Intro } = load('app/intro.tsx', {
    react,
    'react-native': {
      AccessibilityInfo: {}, Image: 'Image', Pressable: 'Pressable', ScrollView: 'ScrollView',
      Text: 'Text', View: 'View', StyleSheet: { create: (s) => s },
      PanResponder: { create: (c) => { config = c; return { panHandlers: {} }; } },
      useWindowDimensions: () => ({ width, height, fontScale }),
    },
    'expo-router': {
      useRouter: () => ({ navigate: (url) => calls.push(url), replace: (url) => calls.push(url) }),
      useFocusEffect: (fn) => effects.push(fn),
    },
    'react-native-safe-area-context': { useSafeAreaInsets: () => ({ top: 59, bottom: 34 }) },
    'react-native-reanimated': {
      View: 'AnimatedView', cancelAnimation: () => {}, interpolate: () => 1,
      runOnJS: (fn) => fn, useReducedMotion: () => reduced,
      useSharedValue: (value) => { const v = { value }; shared.push(v); return v; },
      useAnimatedStyle: (fn) => ({ evaluate: fn }),
      withSpring: (value) => { springs.push(value); return value; },
      withTiming: (value, options, callback) => { animations.push({ value, callback }); return value; },
    },
    'react-native-svg': { default: 'Svg', Path: 'Path' },
    '../src/onboarding': copy, '../src/i18n': i18n,
    '../src/state': { getState: () => ({ login: null, done: false }) },
    '../src/theme': { color: {}, font: {}, radius: {}, space: { xl: 20, lg: 16 }, type: {}, displayFamily: () => '' },
    '../src/haptics': { makePull: () => ({ grab() {}, move() {}, release() {} }) },
    '../src/welcome': { ...welcome, createWelcomeSession: () => session },
    '../assets/art/usp-friends-v2.jpg': 'fixed-welcome-photo',
  });
  const tree = Intro();
  const cleanup = effects[0]();
  session.settle(session.begin(), index);
  shared[0].value = index;
  return { config, tree, session, progress: shared[0], lift: shared[1], animations, springs, calls, cleanup,
    restY: height - Math.max(160, height * .24, 134), height, width };
}
const event = (x, y, touches = 1) => ({ nativeEvent: { pageX: x, pageY: y, touches: Array(touches).fill({ pageX: x, pageY: y }) } });
const preGrant = { y0: 0, x0: 0, dx: 0, dy: 0, vx: 0, vy: 0 };
for (const spot of ['crest', 'left', 'right', 'body', 'text']) {
  check('actual responder owns ' + spot + ' and follows full finger distance before single completion', () => {
    const h = renderIntro();
    const x = spot === 'left' ? 1 : spot === 'right' ? h.width - 1 : h.width / 2;
    const y = spot === 'crest' ? h.restY + 21 : spot === 'body' ? h.height - 90 : h.height - 50;
    const c = h.config;
    assert.equal(c.onStartShouldSetPanResponderCapture(event(x, y), preGrant), true);
    c.onPanResponderGrant(event(x, y), preGrant);
    for (const distance of [12, 35, 70, 120]) {
      c.onPanResponderMove(event(x, y - distance), preGrant);
      assert.equal(h.lift.value, distance);
      assert.deepEqual(h.calls, []);
    }
    c.onPanResponderRelease(event(x, y - 120, 0), preGrant);
    assert.deepEqual(h.calls, [], 'must not navigate before fill animation completes');
    assert.equal(h.lift.value, h.restY + 160, 'curve and fill cover the top of the screen');
    const finish = h.animations.at(-1).callback;
    finish(true); finish(true);
    assert.deepEqual(h.calls, ['/auth']);
  });
}
check('white corner/text scroll never starts wave, horizontal still pages with grant delta reset', () => {
  const h = renderIntro(), c = h.config;
  assert.equal(c.onStartShouldSetPanResponderCapture(event(1, h.restY + 50), preGrant), false);
  assert.equal(c.onMoveShouldSetPanResponderCapture(event(1, h.restY - 70), preGrant), false);
  c.onStartShouldSetPanResponderCapture(event(100, 500), preGrant);
  assert.equal(c.onMoveShouldSetPanResponderCapture(event(120, 500), preGrant), true);
  c.onPanResponderGrant(event(120, 500), preGrant);
  assert.equal(h.progress.value, 2 - 20 / h.width);
  c.onPanResponderRelease(event(190, 500, 0), preGrant);
  h.animations.at(-1).callback(true);
  assert.equal(h.session.index, 1);
  assert.deepEqual(h.calls, []);
});
for (const ending of ['short', 'terminate', 'multitouch', 'second-touch-capture', 'diagonal']) {
  check(ending + ' returns wave and never navigates', () => {
    const h = renderIntro(), c = h.config, x = h.width / 2, y = h.height - 50;
    c.onStartShouldSetPanResponderCapture(event(x, y), preGrant);
    c.onPanResponderGrant(event(x, y), preGrant);
    const dx = ending === 'diagonal' ? 40 : 0, dy = ending === 'short' ? -40 : ending === 'diagonal' ? -40 : -100;
    c.onPanResponderMove(event(x + dx, y + dy), preGrant);
    if (ending === 'terminate') c.onPanResponderTerminate();
    if (ending === 'multitouch') c.onPanResponderStart(event(x, y + dy, 2), preGrant);
    if (ending === 'second-touch-capture') c.onStartShouldSetPanResponderCapture(event(x, y + dy, 2), preGrant);
    c.onPanResponderRelease(event(x + dx, y + dy, 0), preGrant);
    assert.deepEqual(h.springs, [0]);
    assert.equal(h.lift.value, 0);
    assert.deepEqual(h.calls, []);
    assert.equal(h.animations.length, 0);
  });
}
check('tap anywhere black is an alternative and duplicate releases cannot restart it', () => {
  const h = renderIntro(), c = h.config, x = 1, y = h.height - 50;
  c.onStartShouldSetPanResponderCapture(event(x, y), preGrant);
  c.onPanResponderGrant(event(x, y), preGrant);
  c.onPanResponderRelease(event(x, y, 0), preGrant);
  c.onPanResponderRelease(event(x, y, 0), preGrant);
  assert.equal(h.animations.length, 1);
  h.animations[0].callback(true);
  assert.deepEqual(h.calls, ['/auth']);
});
check('root window offset and a re-grabbed spring preserve hit area and finger continuity', () => {
  const h = renderIntro(), c = h.config;
  h.tree.props.ref.current = { measureInWindow: (fn) => fn(20, 40) };
  h.tree.props.onLayout();
  h.lift.value = 30;
  const x = h.width / 2 + 20, y = h.restY + 21 - 30 + 40;
  assert.equal(c.onStartShouldSetPanResponderCapture(event(x, y), preGrant), true);
  c.onPanResponderGrant(event(x, y), preGrant);
  c.onPanResponderMove(event(x, y - 12), preGrant);
  assert.equal(h.lift.value, 42);
  c.onPanResponderTerminate();
  assert.equal(h.lift.value, 0);
});
check('Reduce Motion keeps spatial motion off and uses the same guarded completion', () => {
  const h = renderIntro({ reduced: true }), c = h.config, x = h.width / 2, y = h.height - 50;
  c.onStartShouldSetPanResponderCapture(event(x, y), preGrant);
  c.onPanResponderGrant(event(x, y), preGrant);
  c.onPanResponderMove(event(x, y - 100), preGrant);
  assert.equal(h.lift.value, 0);
  c.onPanResponderRelease(event(x, y - 100, 0), preGrant);
  assert.deepEqual(h.calls, ['/auth']);
  assert.equal(h.animations.length, 0);
});
check('white panel height is identical at all page positions, including accessibility text sizes', () => {
  const findSheet = (node) => {
    if (node?.props?.testID === 'welcome-sheet') return node;
    return node?.children?.flat(Infinity).map(findSheet).find(Boolean);
  };
  for (const width of [320, 375, 393]) for (const fontScale of [1, 2.2]) {
    const heights = [0, 1, 2].map(index => findSheet(renderIntro({ index, width, fontScale }).tree).props.style[1].height);
    assert.equal(new Set(heights).size, 1);
  }
  assert.doesNotMatch(read('app/intro.tsx'), /height:.*progress\.value/);
});
function findNode(node, id) {
  if (node?.props?.testID === id) return node;
  return node?.children?.flat(Infinity).map(child => findNode(child, id)).find(Boolean);
}
check('wave stays visible at the same height through every fractional page transition', () => {
  const h = renderIntro({ index: 0 });
  const wave = findNode(h.tree, 'welcome-wave');
  assert.equal(wave.props.pointerEvents, 'none');
  assert.equal(wave.props.accessible, false);
  for (const progress of [0, .5, 1, 1.5, 2]) {
    h.progress.value = progress;
    assert.equal(wave.props.style[2].evaluate().transform[0].translateY, h.restY);
  }
});
for (const index of [0, 1]) {
  check(`page ${index + 1} wave ignores taps and upward pulls without exposing Start`, () => {
    for (const dy of [0, -150]) {
      const h = renderIntro({ index }), c = h.config, x = h.width / 2, y = h.height - 50;
      assert.equal(findNode(h.tree, 'welcome-start'), undefined);
      assert.equal(c.onStartShouldSetPanResponderCapture(event(x, y), preGrant), false);
      assert.equal(c.onMoveShouldSetPanResponderCapture(event(x, y + dy), preGrant), false);
      c.onPanResponderRelease(event(x, y + dy, 0), preGrant);
      assert.equal(h.lift.value, 0);
      assert.deepEqual(h.calls, []);
      assert.deepEqual(h.animations, []);
    }
  });
  check(`page ${index + 1} still pages horizontally from inactive black surface`, () => {
    const h = renderIntro({ index }), c = h.config, x = h.width / 2, y = h.height - 50;
    assert.equal(c.onStartShouldSetPanResponderCapture(event(x, y), preGrant), false);
    assert.equal(c.onMoveShouldSetPanResponderCapture(event(x - 80, y), preGrant), true);
    c.onPanResponderGrant(event(x - 80, y), preGrant);
    c.onPanResponderRelease(event(x - 80, y, 0), preGrant);
    h.animations.at(-1).callback(true);
    assert.equal(h.session.index, index + 1);
    assert.equal(h.lift.value, 0);
    assert.deepEqual(h.calls, []);
  });
}
console.log(`All ${count} welcome checks passed`);
