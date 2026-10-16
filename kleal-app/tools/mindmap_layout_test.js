/**
 * Карта интересов: пузыри не налезают друг на друга, на тему в центре и за край поля — на всех
 * восьми темах, трёх языках и двух ширинах экрана (обычный и узкий). Размер пузыря считается по
 * подписи (src/mindmapLayout.ts), поэтому проверять надо на настоящих подписях, а не на выборке.
 */
const assert = require('assert');
const ts = require('typescript');
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const cache = {};
function load(f) {
  f = path.resolve(ROOT, f);
  if (cache[f]) return cache[f].exports;
  const out = ts.transpileModule(fs.readFileSync(f, 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true, jsx: ts.JsxEmit.React } }).outputText;
  const mod = { exports: {} };
  cache[f] = mod;
  const req = (n) => {
    if (n.startsWith('.')) {
      const p = path.resolve(path.dirname(f), n);
      for (const e of ['.ts', '.tsx', '/index.ts']) if (fs.existsSync(p + e)) return load(p + e);
    }
    if (n === 'react-native') return { Platform: { OS: 'ios' }, NativeModules: {}, Dimensions: { get: () => ({ width: 402, height: 874 }) } };
    if (n.includes('async-storage')) return { __esModule: true, default: { getItem: async () => null, setItem: async () => {} } };
    try { return require(n); } catch { return {}; }
  };
  Function('require', 'module', 'exports', out)(req, mod, mod.exports);
  return mod.exports;
}
const i18n = load('src/i18n.ts');
const mm = load('src/mindmap.ts');
const L = load('src/mindmapLayout.ts');

let checks = 0;
let pagesChecked = 0;
const dedupe = (list) => {
  const seen = new Map();
  for (const b of list) { const id = b.label.trim().toLowerCase(); if (!seen.has(id)) seen.set(id, b); }
  return [...seen.values()];
};
function checkLayout(p, tag) {
  for (let i = 0; i < p.length; i++) {
    const q = p[i];
    const [W, H] = tag.size;
    assert(q.x - q.d / 2 >= 0 && q.x + q.d / 2 <= W && q.y - q.d / 2 >= 0 && q.y + q.d / 2 <= H, `${tag.name}: «${q.label}» за краем`);
    assert(Math.hypot(q.x - W / 2, q.y - H / 2) >= L.NODE_D / 2 + q.d / 2 - 0.5, `${tag.name}: «${q.label}» на теме в центре`);
    assert(q.d >= 52, `${tag.name}: «${q.label}» меньше пальца`);
    const longest = Math.max(...q.text.split('\n').map((s) => s.length));
    // Подпись помещается ПРИ СВОЁМ КЕГЛЕ, без ужатия на телефоне, и кегль читаемый.
    assert(longest * 0.62 * q.font <= q.d - 2 * L.LEAF_PAD, `${tag.name}: «${q.label}» не влезает в пузырь ${q.d} при кегле ${q.font}`);
    assert(q.font >= L.FONT_MIN, `${tag.name}: «${q.label}» кегль ${q.font}`);
    for (let j = i + 1; j < p.length; j++) {
      const o = (p[i].d + p[j].d) / 2 - Math.hypot(p[i].x - p[j].x, p[i].y - p[j].y);
      assert(o <= 0.5, `${tag.name}: «${p[i].label}» налезает на «${p[j].label}» на ${o.toFixed(1)}`);
    }
    checks++;
  }
}
// Поле карты в анкете: высота 440 минус строка над полем (44) = 396; ширина — обычный и узкий экран.
for (const [W, H] of [[370, 396], [343, 396]]) {
  for (const lang of ['ru', 'en', 'es']) {
    i18n.setLang(lang);
    const pools = mm.mapPools();
    assert.equal(pools.roots.length, 8, 'восемь тем');
    for (const p of L.topicSpots(pools.roots.length, W, H)) {
      assert(p.x - L.NODE_D / 2 - 20 >= 0 && p.x + L.NODE_D / 2 + 20 <= W, `тема за краем по ширине (${lang} ${W})`);
      assert(p.y - L.NODE_D / 2 - 18 >= 0 && p.y + L.NODE_D / 2 + L.NODE_LABEL_H + 6 <= H, `тема за краем по высоте (${lang} ${W})`);
    }
    for (const r of pools.roots) {
      const items = dedupe(pools.leaves[r.key]);
      const keys = items.map((b) => b.key);
      const label = new Map(items.map((b) => [b.key, b.label]));
      const lay = (page, name) => { checkLayout(L.leafSpots(page.map((k) => ({ key: k, label: label.get(k) })), W, H), { name: `${lang} ${W} ${r.key} ${name}`, size: [W, H] }); pagesChecked++; };
      // Первая подборка, потом шесть «другие» подряд без выбранного.
      let pg = L.nextPage(keys, [], 0);
      assert.equal(pg.keys.length, Math.min(L.PAGE, keys.length), `${r.key}: в подборке ${L.PAGE}`);
      lay(pg.keys, 'подборка 1');
      // Листаем до конца очереди: каждая подпись темы должна хоть раз оказаться на поле.
      const seenKeys = new Set(pg.keys);
      const pagesAll = Math.ceil(keys.length / L.PAGE) + 1;
      for (let n = 2; n <= pagesAll; n++) {
        const nx = L.nextPage(keys, [], pg.next, pg.keys);
        if (keys.length >= 2 * L.PAGE) assert(!nx.keys.some((k) => pg.keys.includes(k)), `${r.key}: «другие» повторили прежнее`);
        pg = nx;
        pg.keys.forEach((k) => seenKeys.add(k));
        lay(pg.keys, `подборка ${n}`);
      }
      assert.equal(seenKeys.size, keys.length, `${r.key}: «другие» показали не всё (${seenKeys.size} из ${keys.length})`);
      // Выбрано восемь: они остаются, рядом — свежие.
      const keep = keys.slice(0, Math.min(8, keys.length));
      const withKeep = L.nextPage(keys, keep, pg.next, pg.keys);
      assert(keep.every((k) => withKeep.keys.includes(k)), `${r.key}: выбранные пропали при обновлении`);
      assert(withKeep.keys.length >= Math.min(keys.length, keep.length + 3), `${r.key}: свежих меньше трёх`);
      lay(withKeep.keys, 'восемь выбранных');
    }
  }
}
console.log(`все ${checks} пузырей в ${pagesChecked} подборках карты интересов на местах`);
