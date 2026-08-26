// Source-level contract for Profile -> Interests free-text confirmation flow.
const fs = require('fs');
const path = require('path');
const ROOT = path.join(__dirname, '..');
const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');

let failed = 0;
const check = (name, ok) => {
  if (ok) console.log('  ok   ' + name);
  else { failed++; console.log('  FAIL ' + name); }
};

console.log('\nfree-text interests require semantic confirmation');
const chat = read('app/chat.tsx');
const api = read('src/api.ts');
const profile = read('src/profile.ts');
const state = read('src/state.ts');

check('hobby composer no longer writes raw text into interests.explicit',
  !/if \(step === 'hobbies'\)[\s\S]{0,260}set\('interests\.explicit'/.test(chat));
check('both own-interest entry points use the normalizer',
  /if \(step === 'hobbies'\)[\s\S]{0,180}normalizeOwnInterest\(text\)/.test(chat) &&
  /onAdd=\{\(v\) => \{[\s\S]{0,100}addOwnInterest\(v\)/.test(chat));
check('proposal UI has explicit confirm and cancel paths',
  /confirmOwnInterest\(option\)/.test(chat) && /setInterestDialog\(null\)/.test(chat));
check('API separates normalize from confirm',
  /interest-normalize/.test(api) && /interest-confirm/.test(api));
check('only confirmed canonical values enter local profile state',
  /export function addConfirmedInterest/.test(profile) && /interests\.confirmations/.test(profile));
check('confirmation receipts are not attached as durable profile facts',
  /delete p\.interests\.confirmations/.test(state));

if (failed) throw new Error(failed + ' interest normalization source checks failed');
