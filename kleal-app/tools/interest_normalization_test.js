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
const interestsScreen = read('app/profile/interests.tsx');
const personality = read('app/profile/personality.tsx');
const onboardingBackend = read('../kleal-ms/services/onboarding/app.py');

check('Buddy discoveries are queued for confirmation instead of written as raw interests',
  /await queueInterestProposals\(added\)/.test(chat) &&
  !/for \(const a of added\)[\s\S]{0,300}set\('interests\.explicit'/.test(chat));
check('both profile interest entry points lead to the guarded conversation',
  (interestsScreen.match(/\/chat\?step=hobbies&back=\/profile\/interests/g) || []).length === 2);
check('story-derived interests cross the same normalizer boundary',
  /profileApi\.normalizeInterest/.test(personality) && /profileApi\.confirmInterest/.test(personality));
check('proposal UI has explicit confirm and cancel paths',
  /confirmInterestProposal\(option\)/.test(chat) && /onPress=\{closeInterestProposal\}/.test(chat));
check('API separates normalize from confirm',
  /interest-normalize/.test(api) && /interest-confirm/.test(api));
check('backend blocks unconfirmed direct profile updates',
  /"unconfirmed interests"/.test(onboardingBackend) && /interest_norm\.trusted_interest/.test(onboardingBackend));
check('only confirmed canonical values enter local profile state',
  /export function addConfirmedInterest/.test(profile) && /interests\.confirmations/.test(profile));
check('confirmation receipts are not attached as durable profile facts',
  /delete p\.interests\.confirmations/.test(state));

if (failed) throw new Error(failed + ' interest normalization source checks failed');
