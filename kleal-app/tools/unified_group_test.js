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

function loadTs(rel, mocks = {}) {
  const filename = path.join(root, rel);
  const js = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const module = { exports: {} };
  const localRequire = (id) => {
    if (Object.prototype.hasOwnProperty.call(mocks, id)) return mocks[id];
    throw new Error(`unexpected import ${id} from ${rel}`);
  };
  vm.runInNewContext(`(function(require,module,exports){${js}\n})`, { console })(localRequire, module, module.exports);
  return module.exports;
}

const i18n = { T: (_ru, en) => en, getLang: () => 'en', plural: () => 'people' };
const intent = loadTs('src/intent.ts', { './i18n': i18n });

check('top level contains exactly 1:1 and Group',
  JSON.stringify(intent.SIZES.map((x) => x[0])) === JSON.stringify(['1:1', 'group']));

for (const legacy of ['small', 'large', 'small-group', 'large-group', 'smallGroup', 'largeGroup', 'group-plus', 'party', 'crowd']) {
  check(`legacy ${legacy} normalizes to Group`, intent.normalizeIntentSize(legacy) === 'group');
}
check('unknown value with groupSize stays Group', intent.normalizeIntentSize('old-format', 12) === 'group');
check('1:1 never receives the group branch', intent.normalizeIntentSize('one_on_one') === '1:1');
check('legacy small starts at the group floor', intent.initialGroupSize('small') === 3);
check('legacy large preserves its old lower bound', intent.initialGroupSize('large') === 6);
check('explicit large group size survives up to 20', intent.initialGroupSize('large', 20) === 20);
check('oversized legacy route is bounded by the published ceiling', intent.initialGroupSize('large', 99) === 20);
check('summary names one unified group and its chosen size',
  /group of 12/.test(intent.intentSummaryText({
    topic: 'Coffee', size: 'large', groupSize: 12, minAge: 20, maxAge: 30,
    dateKey: 'today', minutes: 1200,
  })));

const groups = loadTs('src/groups.ts', {
  './i18n': i18n,
  './intent': intent,
  './chat': {},
});
for (const format of ['group', 'small', 'large', 'smallGroup', 'largeGroup', 'group-plus']) {
  check(`saved format ${format} opens group results`, groups.isGroupIntent({ format }));
}
check('legacy route with only groupSize opens group results', groups.isGroupIntent({ format: 'old', groupSize: 10 }));
check('saved 1:1 stays out of group results', !groups.isGroupIntent({ format: '1:1' }));

(async () => {
  let createOpts;
  const ginvites = loadTs('src/ginvites.ts', {
    react: { useEffect: () => {}, useState: () => [0, () => {}] },
    './api': {
      newIdem: () => 'idem',
      group: {
        create: async (_from, _title, _intent, _idem, opts) => {
          createOpts = opts;
          return {
            ok: true,
            group: {
              gid: 'g1', members: [{ name: 'Owner' }], invites: [],
              joined_count: 1, min_total: opts.min_total, max_total: opts.max_total,
              invite_cap: 3, full: false,
            },
          };
        },
        invite: async () => ({ ok: true, invite: { id: 'i1' } }),
        get: async () => ({ group: null }),
      },
    },
  });
  const sent = await ginvites.sendGroupInvite('Owner', 'Guest', {
    format: 'group', groupSize: 20, topics: ['coffee'], mode: 'online',
  }, 'Coffee');
  check('invitation creation forwards a legacy/Plus size without client-side narrowing',
    sent.ok && createOpts && createOpts.min_total === 3 && createOpts.max_total === 20,
    JSON.stringify(createOpts));

  if (failed) process.exit(1);
  console.log('\nunified Group targeted checks passed');
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
