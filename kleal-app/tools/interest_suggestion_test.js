const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..');
const read = (name) => fs.readFileSync(path.join(ROOT, name), 'utf8');

function run() {
  const api = read('src/api.ts');
  const intent = read('app/intent.tsx');
  const prompt = read('src/components/InterestSuggestionPrompt.tsx');
  const adapter = read('src/interest-suggestions.ts');
  const layout = read('app/_layout.tsx');

  assert.match(api, /event_id:\s*eventId/);
  assert.match(api, /interest-suggestion-action/);
  assert.match(intent, /newIdem\('interest-evidence'\)/);
  assert.match(intent, /explicitInterests\(st\.profile\)/);
  assert.match(intent, /offerInterestSuggestion\(r\.interest_suggestion\)/);
  assert.match(adapter, /return addInterests\(\[key\]\)/);
  assert.match(adapter, /return pushInterests\(\)/);
  assert.ok(adapter.indexOf('addInterests') < adapter.indexOf("interestSuggestionAction") ||
            !adapter.includes('interestSuggestionAction'));
  assert.match(prompt, /if \(!saved\) throw/);
  assert.ok(prompt.indexOf('confirmSuggestedInterest') < prompt.indexOf("suggestion.id, 'confirm'"));
  assert.match(prompt, /suggestion.id, 'dismiss'/);
  assert.match(prompt, /C\.dismiss\(\)/);
  assert.match(layout, /<InterestSuggestionPrompt \/>/);

  console.log('interest suggestion client checks passed');
}

if (require.main === module) run();
module.exports = { run };
