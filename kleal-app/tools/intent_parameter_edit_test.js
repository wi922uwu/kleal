#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const ts = require('typescript');

const root = path.resolve(__dirname, '..');
let failed = 0;
function check(name, ok, detail = '') {
  if (ok) console.log(`ok   ${name}`);
  else { failed += 1; console.error(`FAIL ${name}${detail ? `: ${detail}` : ''}`); }
}

function loadTs(rel) {
  const filename = path.join(root, rel);
  const js = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(`(function(require,module,exports){${js}\n})`, { console })(
    (id) => { throw new Error(`unexpected import ${id}`); }, module, module.exports,
  );
  return module.exports;
}

const { beginIntentEdit, applyIntentEdit } = loadTs('src/intent-edit.ts');
const original = {
  mode: 'hybrid', size: 'group', groupSize: 4,
  date: '2026-08-26', minutes: 1200, tz: 'Europe/Moscow',
  sex: 'Female', minAge: 24, maxAge: 37,
  nature: { energy: 'calm', openness: 'slow' },
  district: 'Center', radiusKm: 15, address: 'Old place', lat: 41.1, lon: 2.1,
  link: 'https://old.example/call', untouched: 'sentinel',
};
const edited = {
  ...original,
  mode: 'online', size: '1:1', groupSize: undefined,
  date: '2026-08-28', minutes: 615, tz: 'Europe/London',
  sex: 'Male', minAge: 30, maxAge: 45,
  nature: { energy: 'lively' },
  district: 'North', radiusKm: 9, address: 'New place', lat: 42.2, lon: 3.2,
  link: 'https://new.example/call', untouched: 'changed-by-control',
};

const stable = (target, allowed) => {
  const out = applyIntentEdit(original, edited, target);
  for (const key of Object.keys(original)) {
    if (allowed.includes(key)) continue;
    check(`${target}: ${key} сохраняется`, JSON.stringify(out[key]) === JSON.stringify(original[key]));
  }
  return out;
};

console.log('\nточечный commit сохраняет остальные параметры');
let out = stable('time', ['minutes']);
check('время меняется отдельно', out.minutes === edited.minutes && out.date === original.date);
out = stable('date', ['date']);
check('дата меняется отдельно', out.date === edited.date && out.minutes === original.minutes);
out = stable('timezone', ['tz']);
check('часовой пояс меняется отдельно', out.tz === edited.tz);
out = stable('audience', ['sex', 'minAge', 'maxAge']);
check('аудитория меняется одним атомарным блоком', out.sex === 'Male' && out.minAge === 30 && out.maxAge === 45);
out = stable('place', ['district', 'radiusKm', 'address', 'lat', 'lon']);
check('место меняет адрес, радиус и центр вместе', out.address === 'New place' && out.radiusKm === 9 && out.lat === 42.2);
out = stable('link', ['link']);
check('ссылка меняется отдельно от места', out.link === edited.link && out.address === original.address);
out = stable('mode', ['mode']);
check('режим не стирает сохранённые место и ссылку', out.mode === 'online' && out.address === original.address && out.link === original.link);
out = stable('nature', ['nature']);
check('характер заменяется копией', out.nature.energy === 'lively' && out.nature !== edited.nature);

console.log('\nформат и размер обрабатывают только настоящую зависимость');
out = stable('size', ['size', 'groupSize']);
check('переход в 1:1 очищает несовместимый размер группы', out.size === '1:1' && out.groupSize === undefined);
out = applyIntentEdit(original, { ...edited, size: 'group', groupSize: 12 }, 'size');
check('переход в Group сохраняет явно выбранный большой размер', out.size === 'group' && out.groupSize === 12);
const onlineDependency = applyIntentEdit(original, {
  ...original, mode: 'online', size: 'group', link: 'https://required.example/call',
}, 'mode');
check('смена режима коммитит показанную обязательную ссылку',
  onlineDependency.mode === 'online' && onlineDependency.link === 'https://required.example/call');
const formatDependency = applyIntentEdit(
  { ...original, mode: 'online', size: '1:1', groupSize: undefined, link: '' },
  { ...original, mode: 'online', size: 'group', groupSize: 8, link: 'https://required.example/group' },
  'size',
);
check('смена формата коммитит размер и показанную обязательную ссылку',
  formatDependency.size === 'group' && formatDependency.groupSize === 8
  && formatDependency.link === 'https://required.example/group');
out = applyIntentEdit(original, { ...edited, groupSize: 5 }, 'groupSize');
check('точечный размер остаётся в Group', out.size === 'group' && out.groupSize === 5);

console.log('\ncancel и повторное открытие не протекают в живой draft');
const cancelled = beginIntentEdit(original);
cancelled.minutes = 300;
cancelled.nature.energy = 'lively';
check('cancel не меняет скаляр исходника', original.minutes === 1200);
check('cancel не меняет вложенный характер исходника', original.nature.energy === 'calm');
check('новая сессия снова начинается с сохранённого значения', beginIntentEdit(original).minutes === 1200);

console.log('\nэкран использует explicit edit target и возвращается в summary');
const screen = fs.readFileSync(path.join(root, 'app/intent.tsx'), 'utf8');
const at = screen.indexOf('title={EDIT_SHEET.title()}');
const sheet = at < 0 ? '' : screen.slice(at, screen.indexOf('</EditSheet>', at));
for (const target of ['mode', 'size', 'groupSize', 'date', 'time', 'timezone', 'audience', 'nature', 'place', 'link']) {
  check(`есть target ${target}`, new RegExp(`['\"]${target}['\"]`).test(screen));
}
check('summary передаёт прямое действие строки', /onEditField=\{openEdit\}/.test(screen));
check('save коммитит через белый список target', /applyIntentEdit\(current, edraft, editPick\)/.test(sheet));
check('save не запускает поиск и не сохраняет intent', !/finish\(|intentSave|agent\.match/.test(sheet));
check('save не ведёт по оставшимся шагам', !/setStep\(/.test(sheet));
check('cancel закрывает лист без commit', /cancelLabel=\{DETAILS\.cancel\(\)\}/.test(sheet));
check('обычный мастер сохранил полный маршрут',
  /choose\(\{ mode: k \}, 'size'\)/.test(screen)
  && /k === 'group' \? 'capacity' : 'when'/.test(screen)
  && /onPress=\{toSummary\}/.test(screen));

if (failed) process.exit(1);
console.log('\nintent parameter edit targeted checks passed');
