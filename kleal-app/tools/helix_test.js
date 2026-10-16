// Спираль интересов (v2): геометрия без телефона.
//   node tools/helix_test.js
// Проверяет на настоящих 412 занятиях и восьми темах: каждое занятие ровно один раз; ни при каком
// повороте (прокрутка с шагом 7 точек через всю ленту) два пузыря не налезают друг на друга;
// ни один не выходит за край поля шириной 320–430.
const ts = require('typescript');
const fs = require('fs');
const path = require('path');
const assert = require('assert');

const ROOT = path.join(__dirname, '..');
const cache = {};
function load(file) {
  file = path.resolve(file);
  if (cache[file]) return cache[file].exports;
  const src = fs.readFileSync(file, 'utf8');
  const out = ts.transpileModule(src, { compilerOptions: { module: 1, target: 7, jsx: 2, esModuleInterop: true } }).outputText;
  const m = { exports: {} };
  cache[file] = m;
  Function('require', 'module', 'exports', out)((n) => {
    if (n.startsWith('.')) {
      for (const e of ['.ts', '.tsx', '/index.ts']) {
        const p = path.join(path.dirname(file), n + e);
        if (fs.existsSync(p)) return load(p);
      }
    }
    if (n === 'react-native') return { Platform: { OS: 'ios' } };
    return { T: (ru) => ru, getLang: () => 'ru', useLang: () => 'ru' };
  }, m, m.exports);
  return m.exports;
}

const H = load(path.join(ROOT, 'src/helix.ts'));
const { mapPools } = load(path.join(ROOT, 'src/mindmap.ts'));
const pools = mapPools();
const { items, height, topicY } = H.layoutHelix(pools.roots, pools.leaves);
let n = 0;
const ok = (msg) => { n++; console.log('  ok  ', msg); };

// 1. Полнота и единственность.
const leaves = items.filter((i) => i.kind === 'leaf');
const keys = new Set(leaves.map((l) => l.key));
const want = new Set(Object.values(pools.leaves).flat().map((l) => l.key));
assert.strictEqual(keys.size, leaves.length, 'занятие попало в спираль дважды');
assert.deepStrictEqual([...want].filter((k) => !keys.has(k)), [], 'занятие потерялось');
ok(`все ${leaves.length} занятий на месте, каждое один раз`);
assert.deepStrictEqual(Object.keys(topicY), pools.roots.map((r) => r.key));
assert(pools.roots.every((r, i, a) => i === 0 || topicY[r.key] > topicY[a[i - 1].key]));
ok('темы идут по порядку, у каждой своё начало для перехода');

// 2. Ни один пузырь не выходит за край.
for (const w of [320, 360, 375, 390, 402, 430]) {
  const R = H.amplitude(w) * (1 + H.BREATH); // на вдохе размах наибольший
  for (const l of leaves) {
    const half = H.pillWidth(l.label) / 2;
    assert(w / 2 + R + half <= w, `«${l.label}» вылезает справа при ширине ${w}`);
    assert(w / 2 - R - half >= 0, `«${l.label}» вылезает слева при ширине ${w}`);
  }
}
ok('при ширине 320–430 ни один пузырь не выходит за край, даже в крайней точке витка');

// 3. Пузыри не налезают друг на друга ни при каком повороте.
function boxes(scroll, w, breath) {
  const R = H.amplitude(w) * (1 + breath);
  return items.map((it) => {
    if (it.kind === 'head') return { x: w / 2, y: it.y, w: 150, h: 36, who: 'тема ' + it.label };
    const th = H.angle(it.y, scroll, it.strand);
    const s = H.scaleAt(th);
    return { x: w / 2 + R * Math.sin(th), y: it.y, w: H.pillWidth(it.label) * s, h: H.PILL_H * s, who: it.label };
  });
}
let worst = Infinity;
for (const w of [320, 390, 430]) for (const breath of [-H.BREATH, H.BREATH]) {
  for (let scroll = 0; scroll <= height; scroll += 7) {
    const b = boxes(scroll, w, breath).sort((a, c) => a.y - c.y);
    for (let i = 0; i < b.length; i++) {
      for (let j = i + 1; j < b.length && b[j].y - b[i].y < 60; j++) {
        const dy = Math.abs(b[j].y - b[i].y) - (b[i].h + b[j].h) / 2;
        const dx = Math.abs(b[j].x - b[i].x) - (b[i].w + b[j].w) / 2;
        const gap = Math.max(dx, dy);
        worst = Math.min(worst, gap);
        assert(gap >= 0, `«${b[i].who}» и «${b[j].who}» налезают (ширина ${w}, прокрутка ${scroll})`);
      }
    }
  }
}
ok(`ни при каком повороте пузыри не налезают (наименьший зазор ${worst.toFixed(1)} точки)`);

console.log(`\nспираль: ${n} проверки прошли, лента ${Math.round(height)} точек, тем ${pools.roots.length}`);
