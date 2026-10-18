/** Execute server-evidence reconciliation and list rendering with synthetic accounts only. */
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const root = path.resolve(__dirname, '..'), ts = require(path.join(root, 'node_modules/typescript'));
const load = (file, stubs) => {
  const m = { exports: {} };
  const js = ts.transpileModule(fs.readFileSync(path.join(root, file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true },
  }).outputText;
  Function('require', 'module', 'exports', js)(name => {
    if (name in stubs) return stubs[name];
    throw new Error('Unmocked: ' + name);
  }, m, m.exports);
  return m.exports;
};
const lifecycle = load('src/chat-lifecycle.ts', {});
const state = load('src/state.ts', {
  react: { useEffect() {}, useState: x => [x, () => {}] },
  '@react-native-async-storage/async-storage': { getItem: async () => null, setItem: async () => {} },
  './api': { setSession() {}, setMyId() {}, onMyId: () => () => {} },
});
let language = 0;
const i18n = { T: (...v) => v[language], getLang: () => ['ru', 'en', 'es'][language], dateLocale: () => 'en', use12h: () => false };
const messages = load('src/messages.ts', {
  './i18n': i18n, './api': { isMe: (_name, id) => id === 'a', pidOf: (r, f) => r[f + '_id'] },
  './chat': { klealText: () => '' },
});
const chat = load('src/chat.ts', { './i18n': i18n, './api': { isMe: () => false },
  './names': { acc: x => x, dat: x => x, gen: x => x, ins: x => x } });
state.signedIn({ login: 'a@test.local', session: 'session-a', authMethod: 'code', profile: { name: 'Same' }, isNew: false });
const evidence = (overrides = {}) => ({ peerId: 'b', state: 'closed', sessionId: null, blocked: false, serverTime: 1, ...overrides });
assert.equal(lifecycle.chatLifecycle(evidence()).state, 'closed');
assert.equal(lifecycle.chatLifecycle(evidence(), 'c'), null);
for (const bad of [{}, evidence({ state: 'active', sessionId: null }), evidence({ sessionId: 'stale-active' }), evidence({ serverTime: NaN }), evidence({ blocked: 1 })])
  assert.equal(lifecycle.chatLifecycle(bad), null);
const rows = messages.threadRows([{ who: 'Same', who_id: 'b', last: 'history' }, { who: 'Same', who_id: 'c', last: 'other' }]);
assert.notEqual(rows[0].key, rows[1].key, 'namesakes have distinct row keys');
const b = rows.find(r => r.whoId === 'b'), c = rows.find(r => r.whoId === 'c');
state.setMsgPrefs(() => ({ archived: ['id:b', 'th:id:b', 'id:c', 'same'] }));
assert.equal(state.syncChatLifecycle(evidence(), 'session-a'), true);
assert.equal(messages.bucketOf(b, state.msgPrefs()), 'archived');
assert.equal(lifecycle.canComposeChat(evidence(), false), false);
assert.equal(lifecycle.canComposeChat(evidence(), true), true, 'arming permits a gated send, not a lifecycle mutation');
assert.equal(state.msgPrefs().chats.b.state, 'closed');
// No receipt/read on network failure or quota refusal: the archive stays unchanged.
const archived = JSON.stringify(state.msgPrefs());
assert.equal(state.syncChatLifecycle(evidence({ state: 'active', sessionId: 'new', serverTime: 2 }), 'other-session', true), false);
assert.equal(JSON.stringify(state.msgPrefs()), archived);
// An old successful command receipt followed by a current CLOSED read cannot resume the UI.
state.syncChatLifecycle(evidence({ serverTime: 2 }), 'session-a', true);
assert.equal(messages.bucketOf(b, state.msgPrefs()), 'archived');
state.syncChatLifecycle(evidence({ state: 'active', sessionId: 'new', serverTime: 3 }), 'session-a', true);
assert.equal(messages.bucketOf(b, state.msgPrefs()), 'normal');
assert.equal(messages.bucketOf(c, state.msgPrefs()), 'archived', 'resuming B must not change namesake C');
assert.equal(b.teaser, 'history', 'history is retained');
const acceptedInvites = [
  { id: 'ab', from: 'Same', from_id: 'a', to: 'Same', to_id: 'b', status: 'accepted', updated: 10 },
  { id: 'ac', from: 'Same', from_id: 'c', to: 'Same', to_id: 'a', status: 'accepted', updated: 10 },
];
const acceptedRows = messages.intentRows('Same', [], acceptedInvites, acceptedInvites).forming;
assert.equal(acceptedRows.length, 2, 'accepted pairs deduplicate by peer ID, not name');
const acceptedB = acceptedRows.find(r => r.whoId === 'b');
assert.equal(acceptedB.key, b.key, 'intent and private tabs identify the same pair');
assert.equal(messages.bucketOf(acceptedB, state.msgPrefs()), 'normal', 'old name archive cannot hide a resumed accepted-intent row');
assert.equal(messages.bucketOf(acceptedRows.find(r => r.whoId === 'c'), state.msgPrefs()), 'archived');
const withPlan = messages.intentRows('Same', [{ other: 'Same', other_id: 'b', updated: 11 }], acceptedInvites, []).forming;
assert.deepEqual(withPlan.map(r => r.whoId), ['c'], 'a namesake plan hides only its own accepted pair');
const withHistory = messages.intentRows('Same', [], acceptedInvites, [], [{ other: 'Same', other_id: 'b', updated: 11 }]).forming;
assert.deepEqual(withHistory.map(r => r.whoId), ['c'], 'a namesake past plan cannot hide another new agreement');
const listThreads = [{ who: 'Same', who_id: 'b', last: 'B only', unread: 2, t: 20 },
  { who: 'Same', who_id: 'c', last: 'C only', unread: 7, t: 21 }];
const listRows = messages.inboxRows({ me: 'Same', ru: false, plans: [], history: [], inbox: acceptedInvites,
  outbox: [], threads: listThreads, groups: [], gplans: [], ghistory: [], gmsgs: {}, seen: {},
  planWhen: () => '', sysLine: () => '', gSysLine: () => '' });
for (const [id, count, text] of [['b', 2, 'B only'], ['c', 7, 'C only']]) {
  const row = listRows.find(r => r.whoId === id);
  assert.equal(row.count, count, 'new inbox layout uses exact peer ID for unread count');
  assert.ok(row.teaser.includes(text), 'new inbox layout never shows the namesake history');
  assert.equal(messages.threadRows(listThreads).find(r => r.whoId === id).count, count);
}
assert.deepEqual(messages.searchInbox(listRows, {}, listThreads, 'Same', 'C only').messages.map(r => r.whoId), ['c']);
assert.equal(state.syncChatLifecycle(evidence({ serverTime: 2.5 }), 'session-a'), false, 'late closed poll cannot overwrite resume');
assert.equal(messages.bucketOf(b, state.msgPrefs()), 'normal');
state.syncChatLifecycle(evidence({ state: 'closed', blocked: true, serverTime: 4 }), 'session-a');
assert.equal(lifecycle.canComposeChat(state.msgPrefs().chats.b, true), false);
assert.equal(messages.bucketOf(b, state.msgPrefs()), 'archived');
state.syncChatLifecycle(evidence({ state: 'closed', serverTime: 5 }), 'session-a');
assert.equal(lifecycle.canComposeChat(state.msgPrefs().chats.b, false), false, 'unblock does not reopen');
assert.equal(lifecycle.canComposeChat(state.msgPrefs().chats.b, true), true);
state.setMsgPrefs(m => ({ ...m, archived: ['same'] }));
assert.equal(messages.bucketOf(c, state.msgPrefs()), 'normal', 'ambiguous legacy name is not an ID');
const manual = { ...c, teaser: 'latest message' };
assert.equal(messages.archiveTeaser(manual, { archived: ['id:c'] }), 'latest message', 'manual archive is not read-only');
for (language = 0; language < 3; language++) {
  for (const key of ['chatClosed', 'resumeChat', 'resumeNote', 'chatResumed', 'chatBlocked', 'endingChat', 'endFailed', 'chatStateRetry'])
    assert.equal(typeof chat.CHAT[key](), 'string');
  assert.ok(messages.archiveTeaser(b, state.msgPrefs()));
}
state.signedIn({ login: 'other@test.local', session: 'session-other', authMethod: 'code', profile: { name: 'Same' }, isNew: false });
assert.equal(state.syncChatLifecycle(evidence({ state: 'active', sessionId: 'new', serverTime: 10 }), 'session-a', true), false);
assert.deepEqual(state.msgPrefs(), {}, 'late account-A responses never enter account B');
// Observed peers preserve unresolved legacy marks; only saved peer-ID proof applies a binding.
const legacy={muted:['unique','th:unique','g:keep'],archived:['unique','same'],left:['th:unique','same']};
const peers=[{name:'Unique',id:'u'},{name:'Same',id:'b'},{name:'Same',id:'c'}];
const observed=messages.migrateLegacyMsgPrefs(legacy,peers);
assert.equal(messages.bucketOf({key:'id:u',who:'Unique',whoId:'u'},observed),'normal','one peer in a partial list is not proof');
const migrated=messages.migrateLegacyMsgPrefs(legacy,peers,[{name:'Unique',id:'u',source:'saved_peer_id'}]);
assert.deepEqual(migrated.muted,legacy.muted);
assert.deepEqual(migrated.archived,legacy.archived);assert.deepEqual(migrated.left,legacy.left);
assert.equal(messages.bucketOf({key:'id:u',who:'Unique',whoId:'u'},migrated),'left','original ID proof preserves legacy marks');
const late=messages.migrateLegacyMsgPrefs(observed,[{name:'Unique',id:'namesake'}]);
assert.equal(messages.bucketOf({key:'id:u',who:'Unique',whoId:'u'},late),'normal');
assert.ok(late.muted.includes('unique'));assert.ok(!late.muted.includes('id:u'));
const revoked=messages.migrateLegacyMsgPrefs(migrated,[{name:'Unique',id:'namesake'}]);
assert.equal(messages.bucketOf({key:'id:u',who:'Unique',whoId:'u'},revoked),'normal','late contradiction revokes only derived binding');
assert.ok(revoked.muted.includes('unique'));assert.equal(revoked.legacyProofs.unique,undefined);
assert.equal(migrated.legacyPeers.same,null);
assert.equal(messages.migrateLegacyMsgPrefs(migrated,peers),migrated,'repeat polling is idempotent');
const narrowed=messages.migrateLegacyMsgPrefs(migrated,[{name:'Same',id:'c'}]);
assert.ok(narrowed.archived.includes('same'));assert.ok(!narrowed.archived.includes('id:c'),'later subset cannot rebind ambiguous legacy marker');
assert.ok(!messages.migrateLegacyMsgPrefs({archived:['unknown']},[{name:'Unknown',id:''}]).archived.includes('id:'));
state.setMsgPrefs(()=>migrated);
state.patch({session:null}); // same-owner relogin keeps local migration, just as durable state restore.
state.signedIn({login:'other@test.local',session:'relogin',authMethod:'code',isNew:false});
assert.deepEqual(state.msgPrefs(),migrated);
state.reset(); // explicit logout intentionally clears account-local preferences.
state.signedIn({login:'new@test.local',session:'new',authMethod:'code',isNew:false});
assert.deepEqual(state.msgPrefs(),{});
assert.deepEqual(messages.migrateLegacyMsgPrefs(state.msgPrefs(),[{name:'Unique',id:'different'}]).archived,undefined);
console.log('PASS chat lifecycle: resume, receipt replay, quota/error preservation, end, block, namesakes, stale polls, account switch, RU/EN/ES');
console.log('PASS legacy muted/archive/left: unresolved observations, proven binding, late namesakes, missing IDs, subset polls, relogin and logout isolation');
