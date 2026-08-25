const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

function loadLogic() {
  const filename = path.join(__dirname, '../src/timeInput.ts');
  const source = fs.readFileSync(filename, 'utf8');
  const javascript = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    fileName: filename,
  }).outputText;
  const mod = { exports: {} };
  new Function('exports', 'require', 'module', '__filename', '__dirname', javascript)(
    mod.exports, require, mod, filename, path.dirname(filename),
  );
  return mod.exports;
}

function run() {
  const T = loadLogic();

  assert.equal(T.sanitizeTimePartInput(''), '');
  assert.equal(T.sanitizeTimePartInput('a0b7'), '07');
  assert.equal(T.sanitizeTimePartInput('123'), '12');

  assert.equal(T.editableTimePartValue('', 'minutes'), null);
  assert.equal(T.editableTimePartValue('0', 'minutes'), 0);
  assert.equal(T.editableTimePartValue('07', 'minutes'), 7);
  assert.equal(T.editableTimePartValue('60', 'minutes'), null);
  assert.equal(T.editableTimePartValue('24', 'hours'), null);

  assert.deepEqual(T.normalizeTimePart('', 'hours', 9), { text: '09', value: 9 });
  assert.deepEqual(T.normalizeTimePart('', 'minutes', 5), { text: '05', value: 5 });
  assert.deepEqual(T.normalizeTimePart('99', 'hours', 0), { text: '23', value: 23 });
  assert.deepEqual(T.normalizeTimePart('99', 'minutes', 0), { text: '59', value: 59 });

  assert.deepEqual(T.parseClockPaste('00:07'), { hours: 0, minutes: 7 });
  assert.deepEqual(T.parseClockPaste(' 9 : 5 '), { hours: 9, minutes: 5 });
  assert.deepEqual(T.parseClockPaste('99:99'), { hours: 23, minutes: 59 });
  assert.equal(T.parseClockPaste('0905'), null);

  for (const [label, total] of [
    ['00:00', 0], ['00:07', 7], ['09:05', 9 * 60 + 5], ['23:59', 23 * 60 + 59],
  ]) {
    const parts = T.splitClock(total);
    assert.equal(`${T.formatTimePart(parts.hours)}:${T.formatTimePart(parts.minutes)}`, label);
  }

  assert.equal(T.replaceTimePart(12 * 60 + 34, 'hours', 0), 34);
  assert.equal(T.replaceTimePart(12 * 60 + 34, 'minutes', 7), 12 * 60 + 7);
  assert.deepEqual(T.splitClock(-1), { hours: 23, minutes: 59 });

  console.log('time input targeted checks passed');
}

if (require.main === module) run();
module.exports = { run };
