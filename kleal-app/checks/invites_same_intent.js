// Правило «та же затея или другая» из src/invites.ts, проверенное в чистом виде:
//   node checks/invites_same_intent.js
// Вынесено ИЗ src, чтобы Metro никогда не втянул его в бандл.
const norm = (s) => String(s || '').trim().toLowerCase();
function sameIntent(row, it) {
  if (!it) return true;
  const rid = String(row.iid || '').trim();
  const iid = String(it.id || '').trim();
  if (rid && iid) return rid === iid;
  const a = norm(row.title || ''), b = norm(it.title || '');
  // Названия нет ни у одной стороны — сравнивать нечем, и объявлять затеи разными на пустом месте
  // нельзя: так «Открыть чат» превратилось бы в «Пригласить» у всех старых заявок разом.
  return !a || !b ? true : a === b;
}
let fails = 0;
const check = (name, got, want) => {
  const ok = got === want;
  console.log((ok ? "  ok   " : "СБОЙ  ") + name + "  -> " + got + " (ждали " + want + ")");
  if (!ok) fails++;
};
const acc = { id: 'rq1', to: 'Марта', status: 'accepted', updated: 1, iid: '', title: 'Поиграть в падель' };
const wid = { id: 'rq2', to: 'Марта', status: 'accepted', updated: 1, iid: 'i_padel', title: 'Поиграть в падель' };
const old = { id: 'rq3', to: 'Марта', status: 'accepted', updated: 1, iid: '', title: '' };
check('та же затея по названию', sameIntent(acc, { title: 'Поиграть в падель' }), true);
check('та же, но регистр и пробелы', sameIntent(acc, { title: '  поиграть в ПАДЕЛЬ ' }), true);
check('ДРУГАЯ затея -> зовём заново', sameIntent(acc, { title: 'Сходить в кино' }), false);
check('опознаватель сильнее названия', sameIntent(wid, { id: 'i_kino', title: 'Поиграть в падель' }), false);
check('тот же опознаватель', sameIntent(wid, { id: 'i_padel', title: 'что угодно' }), true);
check('старая заявка без названия — как раньше', sameIntent(old, { title: 'Сходить в кино' }), true);
check('затеи не дали — как раньше', sameIntent(acc, null), true);
check('у затеи нет названия — как раньше', sameIntent(acc, { title: '' }), true);
console.log(fails ? ("СБОЕВ: " + fails) : "правило «та же затея или другая»: всё зелёное");
process.exit(fails ? 1 : 0);
