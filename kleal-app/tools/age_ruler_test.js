/** Targeted contract checks for the onboarding age ruler. Run from kleal-app with Node. */
const assert = require('assert');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const ts = require('typescript');

const ROOT = path.join(__dirname, '..');
const read = (relative) => fs.readFileSync(path.join(ROOT, relative), 'utf8');

function loadPureModule(relative) {
  const source = read(relative);
  const output = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const mod = { exports: {} };
  Function('require', 'module', 'exports', output)(require, mod, mod.exports);
  return mod.exports;
}

const ruler = loadPureModule('src/age-ruler.ts');
const dial = read('src/components/AgeDial.tsx');
const chat = read('app/chat.tsx');
const state = read('src/state.ts');
const summary = read('app/summary.tsx');

console.log('\nonboarding age ruler');

assert.equal(ruler.AGE_MIN, 18);
assert.equal(ruler.AGE_MAX, 80);
assert.equal(ruler.clampAge(undefined), 28);
assert.equal(ruler.clampAge(17), 18);
assert.equal(ruler.clampAge(80.8), 80);
assert.equal(ruler.clampAge(28.6), 29);
console.log('  ok   adult range, fallback and clamp stay deterministic');

for (let age = ruler.AGE_MIN; age <= ruler.AGE_MAX; age += 1) {
  const offset = ruler.ageToOffset(age);
  assert.equal(ruler.offsetToAge(offset), age);
  assert.equal(ruler.snapAgeOffset(offset + 3), offset);
}
assert.equal(ruler.ageToOffset(18), 0);
assert.equal(ruler.ageToOffset(28), -180);
assert.equal(ruler.ageToOffset(80), -1116);
assert.equal(ruler.offsetToAge(1000), 18);
assert.equal(ruler.offsetToAge(-10000), 80);
console.log('  ok   offset to age mapping round-trips and snaps at both bounds');

const feedback = (overrides = {}) => ruler.shouldEmitAgeFeedback({
  previousAge: 28,
  nextAge: 29,
  now: 1000,
  lastFeedbackAt: 0,
  userInitiated: true,
  appActive: true,
  ...overrides,
});
assert.equal(feedback(), true);
assert.equal(feedback({ nextAge: 28 }), false);
assert.equal(feedback({ userInitiated: false }), false);
assert.equal(feedback({ appActive: false }), false);
assert.equal(feedback({ now: 1054, lastFeedbackAt: 1000 }), false);
assert.equal(feedback({ now: 1055, lastFeedbackAt: 1000 }), true);
console.log('  ok   click and haptic gate dedupes and ignores hydration/background');

for (const locale of ['ru', 'en', 'es']) {
  const copy = ruler.ageRulerCopy(locale, 28);
  assert(copy.label && copy.value.includes('28') && copy.hint && copy.increment && copy.decrement);
}
assert.equal(ruler.ageRulerCopy('ru', 21).value, '21 год');
assert.equal(ruler.ageRulerCopy('ru', 22).value, '22 года');
assert.equal(ruler.ageRulerCopy('ru', 25).value, '25 лет');
assert(/accessibilityRole="adjustable"/.test(dial));
assert(/accessibilityValue=\{\{ min: AGE_MIN, max: AGE_MAX, now: selected/.test(dial));
assert(/onAccessibilityAction=\{onAccessibilityAction\}/.test(dial));
assert(/maxFontSizeMultiplier=\{1\.6\}/.test(dial));
console.log('  ok   adjustable accessibility and RU/EN/ES copy are wired');

assert(/offset\.setValue\(gestureStart\.current \+ gesture\.dx\)/.test(dial));
assert(/Animated\.decay\(offset/.test(dial) && /deceleration: FRICTION/.test(dial));
assert(/age % 5 === 0/.test(dial) && /LONG_TICK_HEIGHT/.test(dial));
assert(/stroke=\{color\.primary\}/.test(dial) && /toValue: ageToOffset\(next\)/.test(dial));
console.log('  ok   continuous drag, inertial flick, long ticks and coral snap marker stay wired');

assert(/createAudioPlayer\(require\('\.\.\/\.\.\/assets\/sounds\/click\.wav'\)\)/.test(dial));
assert(/player\.current\?\.remove\(\)/.test(dial));
assert(/AppState\.addEventListener/.test(dial));
assert(/hTick\(\)/.test(dial));
assert(!/setAudioModeAsync/.test(dial));
const sound = fs.readFileSync(path.join(ROOT, 'assets/sounds/click.wav'));
assert.equal(sound.subarray(0, 4).toString('ascii'), 'RIFF');
assert.equal(crypto.createHash('sha256').update(sound).digest('hex'),
  'f8b9acd3bc8cd01f2f3328b8705265ed035d76b008c791d5f4b51d412ce0def4');
console.log('  ok   supplied click asset is local and audio lifetime is bounded');

const basics = chat.slice(chat.indexOf('function BasicsW'), chat.indexOf('/** A.06'));
assert(/clampAge\(st\.profile\.age\)/.test(basics));
assert(/locale=\{replyLang\(\)\}/.test(basics));
assert.equal((basics.match(/maxFontSizeMultiplier=\{1\.6\}/g) || []).length, 2);
assert(/basicsLabel: \{ lineHeight: 24 \}/.test(chat));
assert(/set\('age', age\)/.test(basics));
assert(/disabled=\{!sex\}/.test(basics));
assert(basics.indexOf("set('age', age)") < basics.indexOf("goto('area'"));
assert(/return \{ \.\.\.state\.profile, tz: deviceTz\(\) \}/.test(state));
assert(/onboarding\.register\(profileForRegister\(\)\)/.test(summary));
console.log('  ok   profile hydration, gender gate and registration payload preserve age');

console.log('все проверки age ruler прошли');
