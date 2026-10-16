/**
 * Свидание доезжает до поиска ТИПОМ. Сторож пути create → intent → match.
 *
 *     node tools/dating_type_test.js
 *
 * 26.09.2026 мерка показала «свидание дошло до поиска» 0 из 7: построитель отдаёт
 * `intent.type = 'dating'`, а create.tsx передавал в мастер только темы и заголовок, и мастер
 * слал в поиск затею без типа. Поиск искал свидание как обычную встречу — без ворот `datingOk`.
 * Без сети и без телефона: функция берётся из src/buddy.ts, экраны проверяются по исходнику.
 */
const path = require('path'), fs = require('fs');
const APP = path.resolve(__dirname, '..');
const ts = require(path.join(APP, 'node_modules', 'typescript'));
const read = (p) => fs.readFileSync(path.join(APP, p), 'utf8');

let ok = 0, bad = 0;
const check = (name, cond) => { if (cond) { ok++; } else { bad++; console.log('FAIL', name); } };

// 1. datingOf из настоящего src/buddy.ts.
const buddy = read('src/buddy.ts');
const m = buddy.match(/export function datingOf[\s\S]*?\n}\n/);
check('datingOf объявлена в src/buddy.ts', !!m);
if (m) {
  const js = ts.transpileModule(m[0].replace(/^export /, ''), { compilerOptions: { target: 'ES2019' } }).outputText;
  const datingOf = new Function(js + '\nreturn datingOf;')();
  check('dating → true', datingOf({ intent: { type: 'dating' } }) === true);
  check('Dating с пробелами → true', datingOf({ intent: { type: ' Dating ' } }) === true);
  check('social → false', datingOf({ intent: { type: 'social' } }) === false);
  check('нет типа → false', datingOf({ intent: {} }) === false);
  check('нет затеи → false', datingOf({}) === false && datingOf(null) === false);
}

// 2. create.tsx кладёт тип в состояние и передаёт мастеру.
const create = read('app/create.tsx');
check('create: ready несёт dating', /dating:\s*datingOf\(r\)/.test(create));
const next = create.match(/const next = \(\) => router\.navigate\(\{[\s\S]*?\n  \}\);/);
check('create: next() найден', !!next);
check('create: next() передаёт type dating', !!next && /type:\s*'dating'/.test(next[0]));

// 3. intent.tsx читает тип и кладёт его в затею, которая уходит в поиск и сохраняется.
const intent = read('app/intent.tsx');
check('intent: читает params.type', /params\.type/.test(intent));
const fin = intent.match(/const finish = async \(\) => \{[\s\S]*?agent\.match\(intent/);
check('intent: finish() найден', !!fin);
check('intent: finish() кладёт type dating в intent', !!fin && /type:\s*'dating'/.test(fin[0]));
check('intent: тип только для свиданий', !!fin && /dating \? \{ type: 'dating' \}/.test(fin[0]));

console.log(`dating_type_test: ${ok} ok, ${bad} fail`);
process.exit(bad ? 1 : 0);
