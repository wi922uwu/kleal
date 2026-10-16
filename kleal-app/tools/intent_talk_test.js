// GR.12a «скажи Kleal, что поменять» — разбор реплики в правку сводки (src/intent-talk.ts).
//
//   node tools/intent_talk_test.js
//
// Модуль транспилируется из настоящего исходника, часы — фиксированные: суббота 3 октября 2026, 14:00.
const fs = require('fs');
const path = require('path');
const ts = require('typescript');

const ROOT = path.join(__dirname, '..');
const src = fs.readFileSync(path.join(ROOT, 'src/intent-talk.ts'), 'utf8');
const js = ts.transpileModule(src, { compilerOptions: { target: 'ES2019', module: ts.ModuleKind.CommonJS } }).outputText;
const mod = { exports: {} };
new Function('module', 'exports', js)(mod, mod.exports);
const { parseIntentChange } = mod.exports;

let ok = 0, failed = 0;
function check(name, cond, detail) {
  if (cond) { ok++; console.log('  ok   ' + name); }
  else { failed++; console.log('  FAIL ' + name + (detail ? '\n         ' + detail : '')); }
}

const NOW = new Date(2026, 9, 3, 14, 0);           // сб 3 октября 2026, 14:00
const D = { size: 'group', groupSize: 3, date: '2026-10-03', minutes: 19 * 60, sex: 'Any', minAge: 25, maxAge: 35, radiusKm: 15 };
const P = (t, d = D) => parseIntentChange(t, d, NOW);
const S = (r) => JSON.stringify(r);

let r;
r = P('move it to Sunday at 8pm');
check('en: день недели и 8pm', r && r.patch.date === '2026-10-04' && r.patch.minutes === 20 * 60, S(r));
r = P('tomorrow 18:30');
check('en: tomorrow + 18:30', r && r.patch.date === '2026-10-04' && r.patch.minutes === 18 * 60 + 30, S(r));
r = P('давай в понедельник в 7');
check('ru: «в понедельник в 7» → пн 19:00', r && r.patch.date === '2026-10-05' && !('minutes' in r.patch), S(r));
r = P('в субботу в 7');
check('то же, что уже стоит, — правок нет, но понято', r && !Object.keys(r.patch).length && r.touched.includes('when'), S(r));
r = P('перенеси на 24 октября в 19.30');
check('ru: «24 октября в 19.30»', r && r.patch.date === '2026-10-24' && r.patch.minutes === 19 * 60 + 30, S(r));
r = P('mañana a las 9 de la noche');
check('es: mañana a las 9 de la noche', r && r.patch.date === '2026-10-04' && r.patch.minutes === 21 * 60, S(r));
r = P('el 12/10 por la tarde');
check('es: 12/10 por la tarde', r && r.patch.date === '2026-10-12' && r.patch.minutes === 15 * 60, S(r));
r = P('today at 10am');
check('прошедшее время сегодня — отказ «past»', r && r.problem === 'past' && !Object.keys(r.patch).length, S(r));
r = P('only women 25-30');
check('en: women 25–30', r && r.patch.sex === 'Female' && r.patch.minAge === 25 && r.patch.maxAge === 30, S(r));
r = P('ищу парней от 30 до 40');
check('ru: парни 30–40', r && r.patch.sex === 'Male' && r.patch.minAge === 30 && r.patch.maxAge === 40, S(r));
r = P('любой возраст, кто угодно');
check('ru: любой возраст и пол', r && r.patch.sex === 'Any' && r.patch.minAge === 0 && r.patch.maxAge === 0, S(r));
r = P('make it 4 people');
check('en: 4 people', r && r.patch.groupSize === 4, S(r));
r = P('на 8 человек');
check('ru: 8 человек — выше Free → plus', r && r.problem === 'plus' && !r.patch.groupSize, S(r));
r = P('one-on-one instead');
check('формат 1:1 из группы — «format»', r && r.problem === 'format', S(r));
r = P('within 5 km');
check('радиус 5 km', r && r.patch.radiusKm === 5, S(r));
r = P('Friday for 8pm');
check('«for 8pm» не размер группы', r && !r.patch.groupSize && r.patch.minutes === 20 * 60, S(r));
r = P('до 20:00 не получится, давай в 21');
check('«до 20:00» не возраст', r && r.patch.minAge === undefined, S(r));
r = P('call it Sunset grill');
check('название', r && r.title === 'Sunset grill' && r.touched.includes('what'), S(r));
r = P('назови Пятничный бег');
check('ru: название целиком, без разбора дня внутри', r && r.title === 'Пятничный бег' && !r.patch.date, S(r));
r = P('hmm not sure');
check('непонятное → null', r === null, S(r));
r = P('vamos en la playa');
check('es: место словами не правится → null', r === null, S(r));

console.log(`\nintent_talk_test: ${ok} ok, ${failed} fail`);
process.exitCode = failed ? 1 : 0;
