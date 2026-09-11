const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
function compile(source) {
  const mod = { exports: {} };
  const js = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
  } }).outputText;
  Function('require', 'exports', 'module', js)(require, mod.exports, mod);
  return mod.exports;
}
const mdSource = read('src/components/Markdown.tsx');
const md = compile(mdSource.slice(mdSource.indexOf('type Inline ='), mdSource.indexOf('function Rich(')));
let count = 0;
function test(name, fn) { fn(); count++; console.log('ok', name); }
test('blank lines retain a single ordered list', () => {
  const blocks = md.parseBlocks('1. Вода\n\n1. Соль\n\n1. Пельмени\n\n1. Подать');
  assert.equal(blocks.length, 1);
  assert.equal(blocks[0].items.length, 4);
  assert.equal(blocks[0].start, 1);
});

test('explicit start, repeated 1 and skipped labels follow Markdown list counters', () => {
  for (const input of ['3. A\n4. B\n9. C', '3) A\n\n1) B\n\n1) C']) {
    const [list] = md.parseBlocks(input);
    assert.equal(list.start, 3);
    assert.deepEqual(list.items.map((it) => it[0].text), ['A', 'B', 'C']);
  }
  assert.equal(md.parseBlocks('0. Zero\n1. One')[0].start, 0);
});
test('continuation paragraphs belong to their item; outside paragraph terminates the list', () => {
  const b = md.parseBlocks('1. First\nwrapped line\n\n   Another paragraph\n\n2. Second\n\nOutside\n\n1. New list');
  assert.deepEqual(b.map((v) => v.kind), ['ol', 'p', 'ol']);
  assert.deepEqual(b[0].items[0], [{ kind: 'p', text: 'First wrapped line' }, { kind: 'p', text: 'Another paragraph' }]);
  assert.equal(b[0].items[1][0].text, 'Second');
  assert.equal(b[2].start, 1);
});
test('nested ordered and bullet lists retain hierarchy and independent counters', () => {
  const [b] = md.parseBlocks('1. Parent\n   4. Nested\n\n   1. Next\n      - Bullet\n      - More\n\n2. Sibling');
  assert.equal(b.items.length, 2);
  const nested = b.items[0][1];
  assert.equal(nested.start, 4);
  assert.equal(nested.items.length, 2);
  assert.equal(nested.items[1][1].kind, 'ul');
  assert.equal(nested.items[1][1].items.length, 2);
  assert.equal(b.items[1][0].text, 'Sibling');
});
test('bullet loose lists, tabs, parentheses and marker changes', () => {
  assert.equal(md.parseBlocks('- A\n\n- B')[0].items.length, 2);
  assert.equal(md.parseBlocks('- Parent\n\t1) Child')[0].items[0][1].kind, 'ol');
  assert.deepEqual(md.parseBlocks('1. Ordered\n- Bullet').map((b) => b.kind), ['ol', 'ul']);
  assert.equal(md.parseBlocks('  1. Leading spaces')[0].kind, 'ol');
});
test('streaming every character keeps completed items stable and preserves partial markers', () => {
  const input = '1. Alpha\n\n1. Beta\n\n1. Gamma';
  for (let end = 9; end <= input.length; end++) {
    const b = md.parseBlocks(input.slice(0, end));
    assert.equal(b[0].kind, 'ol');
    assert.equal(b[0].start, 1);
    assert.equal(b[0].items[0][0].text, 'Alpha');
    assert(b[0].items.length <= 3);
  }
  assert.equal(md.parseBlocks('1. Alpha\n\n2')[1].text, '2');
  assert.equal(md.parseBlocks('1. Alpha\n\n2.')[0].items.length, 2);
});
test('ordinary numbers, fenced code, tables, quote and inline formatting are unchanged', () => {
  assert.deepEqual(md.parseBlocks('Price 1.5\n2026-09-12'), [{ kind: 'p', text: 'Price 1.5 2026-09-12' }]);
  assert.deepEqual(md.parseBlocks('```\n1. code\n\n1. code\n```'), [{ kind: 'code', text: '1. code\n\n1. code' }]);
  assert.deepEqual(md.parseBlocks('# Title\n\n> quote\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n---').map((b) => b.kind), ['h', 'quote', 'table', 'hr']);
  assert.deepEqual(md.parseInline('**a** и *b*'), [{ text: 'a', bold: true }, { text: ' и ' }, { text: 'b', italic: true }]);
  assert.deepEqual(md.parseInline('unfinished **'), [{ text: 'unfinished **' }]);
});
test('item code and quote do not become sibling lists', () => {
  const [list] = md.parseBlocks('1. Intro\n\n   ```\n   1. literal\n   ```\n\n   > Quote\n\n2. End');
  assert.deepEqual(list.items[0].map((b) => b.kind), ['p', 'code', 'quote']);
  assert.equal(list.items[0][1].text, '1. literal');
});
test('bounded nesting and large lists do not lose siblings', () => {
  const large = Array.from({ length: 500 }, (_, i) => `1. Item ${i}`).join('\n\n');
  assert.equal(md.parseBlocks(large)[0].items.length, 500);
  assert.doesNotThrow(() => md.parseBlocks(Array.from({ length: 80 }, (_, i) => '   '.repeat(i) + '1. Deep').join('\n')));
});

// Render the actual shared component through React DOM server using native host stubs.
test('rendered 1-12 markers, nested counters and hanging-indent columns', () => {
  const React = require('react');
  const { renderToStaticMarkup } = require('react-dom/server');
  const theme = compile(read('src/theme.ts'));
  const host = (tag) => ({ children, style }) => React.createElement(tag, {
    'data-native-style': JSON.stringify(style),
  }, children);
  const stub = { View: host('div'), Text: host('span'), ScrollView: host('section'),
    StyleSheet: { create: (s) => s }, useWindowDimensions: () => ({ fontScale: 1.8 }) };
  const mod = { exports: {} };
  const output = ts.transpileModule(mdSource, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React, esModuleInterop: true,
  } }).outputText;
  Function('require', 'exports', 'module', output)((id) => id === 'react-native' ? stub : id === '../theme' ? theme : require(id), mod.exports, mod);
  const html = renderToStaticMarkup(React.createElement(mod.exports.default, {
    text: Array.from({ length: 12 }, (_, i) => `1. Value${i}`).join('\n\n'),
  }));
  const labels = [...html.matchAll(/>(\d+\.)<\/span>/g)].map((m) => m[1]);
  assert.deepEqual(labels, Array.from({ length: 12 }, (_, i) => `${i + 1}.`));
  assert.match(html, /minWidth/);
  assert.match(html, /flex/);
  const nested = renderToStaticMarkup(React.createElement(mod.exports.default, { text: '1. A\n   4. B\n   1. C\n2. D' }));
  assert.deepEqual([...nested.matchAll(/>(\d+\.)<\/span>/g)].map((m) => m[1]), ['1.', '4.', '5.', '2.']);
});

const chat = compile(read('src/plan-chat.ts'));
const fixture = { id: 'plan-1', title: 'Online meetup', other: 'Wrong route peer', mode: 'online',
  participants: [{ name: 'Self' }, { name: 'Peer' }], starts_at: 1900000000, state: 'confirmed', link: '' };
test('plan participant wins over stale route/other, self/group/malformed plans never guess a peer', () => {
  assert.equal(chat.planChatPeer(fixture, ' self '), 'Peer');
  assert.equal(chat.planChatPeer(null, 'Self'), '');
  assert.equal(chat.planChatPeer(fixture, 'Stranger'), '');
  assert.equal(chat.planChatPeer({ ...fixture, participants: [{ name: 'Self' }] }, 'Self'), '');
  assert.equal(chat.planChatPeer({ ...fixture, participants: [...fixture.participants, { name: 'Third' }] }, 'Self'), '');
  assert.equal(chat.planChatPeer({ ...fixture, participants: [...fixture.participants, {}] }, 'Self'), '');
  assert.equal(chat.planChatPeer({ id: 'old', other: 'Peer' }, 'Self'), 'Peer');
  assert.equal(chat.planChatPeer({ id: 'old', other: 'Self' }, 'Self'), '');
});
test('RU/EN/ES copy and UI reachability before place/link and during lock', () => {
  for (const locale of ['ru', 'en', 'es']) assert(Object.values(chat.planChatCopy(locale)).every(Boolean));
  const screen = read('app/plan.tsx');
  assert.match(screen, /\{needsWhere \? \([\s\S]*?onPress=\{openChat\}/);
  assert.match(screen, /const needsWhere = !!plan && settling/);
  assert.match(screen, /accessibilityState=\{\{ disabled: openingChat, busy: openingChat \}\}/);
  assert.match(screen, /if \(chatRequest.current \|\| !chatContext.current\) return/);
  assert.match(screen, /useFocusEffect\(useCallback/);
  assert.match(screen, /chatContext.current = Symbol\(chatContextKey\)/);
  assert.match(screen, /return \(\) => \{ chatContext.current = null; \}/);
  assert.match(screen, /if \(context === chatContext.current\) router.dismissTo\(target\)/);
  const action = screen.slice(screen.indexOf('const openChat ='), screen.indexOf('/** Ссылка, как её отдал'));
  assert.doesNotMatch(action, /planPropose|planRespond|planAddress|planAsk|threadEnd|\.message\(|setPlan\(/);
  assert.match(read('app/gplan.tsx'), /onOpenChat=\{\(\) => router.dismissTo\(\{ pathname: '\/group', params: \{ gid \}/);
});

(async () => {
  const before = JSON.stringify(fixture);
  let calls = 0;
  for (const mode of ['online', 'offline', 'hybrid']) {
    const target = await chat.preparePlanChat({ ...fixture, mode }, 'Self', async (self, who) => {
      assert.equal(self, 'Self'); assert.equal(who, 'Peer'); calls++; return { messages: [] };
    });
    assert.deepEqual(target, { pathname: '/conversation', params: { who: 'Peer', title: 'Online meetup' } });
  }
  assert.equal(calls, 3);
  assert.equal(JSON.stringify(fixture), before);
  for (const value of [null, {}, { ok: false, messages: [] }, { error: 'BLOCKED', messages: [] }]) {
    await assert.rejects(chat.preparePlanChat(fixture, 'Self', async () => value), /CHAT_UNAVAILABLE/);
  }
  await assert.rejects(chat.preparePlanChat(fixture, 'Self', async () => { throw Error('network'); }), /network/);
  await assert.rejects(chat.preparePlanChat(null, 'Self', async () => { throw Error('should not request'); }), /CHAT_UNAVAILABLE/);
  // Execute the actual screen callback with controlled promises: no reimplementation of its guard.
  const screen = read('app/plan.tsx');
  const callback = screen.slice(screen.indexOf('const openChat ='), screen.indexOf('/** Ссылка, как её отдал'));
  const callbackJS = ts.transpileModule(callback, { compilerOptions: { target: ts.ScriptTarget.ES2020 } }).outputText;
  for (const outcome of ['success', 'blur', 'refocus', 'error']) {
    let resolve, requestCount = 0;
    const response = new Promise((r) => { resolve = r; });
    const navigated = [], errors = [], busy = [];
    const context = { current: Symbol('plan') };
    const guard = { current: false };
    const open = Function('preparePlanChat', 'plan', 'me', 'agent', 'router', 'chatRequest', 'chatContext',
      'setOpeningChat', 'setChatError', 'planChatCopy', 'getLang', callbackJS + '\nreturn openChat;')(
      chat.preparePlanChat, fixture, 'Self', { thread: () => { requestCount++; return response; } },
      { dismissTo: (target) => navigated.push(target) }, guard, context,
      (value) => busy.push(value), (value) => errors.push(value), chat.planChatCopy, () => 'ru');
    const pending = open();
    await open(); // second tap during the first preflight
    assert.equal(requestCount, 1);
    if (outcome === 'blur') context.current = null;
    if (outcome === 'refocus') context.current = Symbol('same plan, different visit');
    resolve(outcome === 'error' ? { error: 'BLOCKED' } : { messages: [] });
    await pending;
    assert.equal(navigated.length, outcome === 'success' ? 1 : 0);
    assert.equal(errors.filter(Boolean).length, outcome === 'error' ? 1 : 0);
    assert.equal(guard.current, false);
    assert.equal(JSON.stringify(fixture), before);
  }
  console.log(`PASS ${count} groups plus async plan route/error/immutability and 4 callback race cases`);
})().catch((error) => { console.error(error); process.exitCode = 1; });
