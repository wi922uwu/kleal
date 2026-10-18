/** Run the actual screen handlers against synthetic API responses; this is not native QA. */
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const root = path.resolve(__dirname, '..'), ts = require(path.join(root, 'node_modules/typescript'));
function load(file, stubs) {
  const m = { exports: {} };
  const out = ts.transpileModule(fs.readFileSync(path.join(root, file), 'utf8'), {
    compilerOptions: { module: 1, target: 7, jsx: ts.JsxEmit.React, esModuleInterop: true },
  }).outputText;
  Function('React', 'require', 'module', 'exports', out)(stubs.react, name => {
    if (name in stubs) return stubs[name];
    throw new Error('Unmocked ' + name);
  }, m, m.exports);
  return m.exports;
}
const i18n = { T: (...v) => v[0], getLang: () => 'ru', useLang() {}, dateLocale: () => 'ru', use12h: () => false };
const lifecycle = load('src/chat-lifecycle.ts', {});
let token = 'a-token', prefs = {}, server, history, messageMode, endMode, messagesSent = [], ends = [], threadReply;
let cells, cursor, effects, dirty, tree, polls, voiceCallback, voiceDisabled, seq = 0;
const timers = new Map();
const nativeSetTimeout = global.setTimeout, nativeClearTimeout = global.clearTimeout;
global.setTimeout = (fn, ms) => { const id = ++seq; timers.set(id, { fn, ms }); return id; };
global.clearTimeout = id => timers.delete(id);
const same = (a, b) => a && b && a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
const React = {
  createElement: (type, props, ...children) => ({ type, props: { ...props, children } }),
  useState(initial) {
    const i = cursor++;
    if (!(i in cells)) cells[i] = { value: typeof initial === 'function' ? initial() : initial };
    return [cells[i].value, value => { const next = typeof value === 'function' ? value(cells[i].value) : value;
      if (!Object.is(next, cells[i].value)) { cells[i].value = next; dirty = true; } }];
  },
  useRef(value) { const i = cursor++; if (!(i in cells)) cells[i] = { current: value }; return cells[i]; },
  useMemo(fn, deps) { const i = cursor++; if (!same(cells[i]?.deps, deps)) cells[i] = { value: fn(), deps }; return cells[i].value; },
  useCallback(fn, deps) { return React.useMemo(() => fn, deps); },
  useEffect(fn, deps) {
    const i = cursor++;
    if (!same(cells[i]?.deps, deps)) {
      const prev = cells[i]; cells[i] = { deps };
      effects.push(() => { prev?.cleanup?.(); cells[i].cleanup = fn(); });
    }
  },
};
const api = {
  getSession: () => token, ensureMe: async () => 'a', isMe: (_n, id) => id === 'a',
  pidOf: (r, f) => r[f + '_id'] || '', newIdem: prefix => prefix + ++seq, mediaUrl: x => x,
  agent: {
    thread: async () => threadReply ? threadReply() : { chat: { ...server, serverTime: ++seq }, messages: history, peer_read_at: 0 },
    plans: async () => ({ plans: [], history: [] }),
    inbox: async () => ({ requests: [] }),
    outbox: async () => ({ requests: [{ from: 'A', from_id: 'a', to: 'B', to_id: 'b', status: 'accepted', intent: {} }] }),
    threadRead: async () => ({ ok: true }),
    message: async (...args) => {
      messagesSent.push(args);
      if (messageMode === 'quota') throw Object.assign(new Error('chat_quota'), { body: { error: 'chat_quota' } });
      if (messageMode === 'blocked') throw Object.assign(new Error('BLOCKED'), { body: { error: 'BLOCKED' } });
      if (messageMode === 'network') throw new Error('network');
      server = { ...server, state: 'active', sessionId: 'new-session' };
      return { ok: true, id: 'message-' + seq, t: 100 };
    },
    threadEnd: async (...args) => {
      ends.push(args);
      if (endMode === 'error') throw new Error('503');
      if (endMode === 'business') return { ok: false, error: 'NOT_MATCHED' };
      server = { ...server, state: 'closed', sessionId: null };
      return { ok: true };
    },
  },
};
const chat = load('src/chat.ts', { './i18n': i18n, './api': api, './names': { acc: x => x, dat: x => x, gen: x => x, ins: x => x } });
const state = {
  useOnb: () => ({ session: 'a-token', profile: { name: 'A' }, msg: prefs }), markSeen() {},
  setMsgPrefs: fn => { prefs = fn(prefs); dirty = true; },
  syncChatLifecycle: (c, session) => {
    if (session !== token) return false;
    prefs = { ...prefs, chats: { ...prefs.chats, [c.peerId]: c } };
    return true;
  },
};
const native = Object.fromEntries(['View', 'Text', 'ScrollView', 'Pressable', 'TextInput', 'Image', 'ActivityIndicator', 'KeyboardAvoidingView'].map(n => [n, n]));
const stubs = {
  '../src/online-ask': { takeOpener: async () => null },
  react: React, 'react-native': { ...native, StyleSheet: { create: x => x }, Platform: { OS: 'ios' }, Linking: {} },
  'react-native-safe-area-context': { useSafeAreaInsets: () => ({ top: 0, bottom: 0 }) },
  'expo-router': { useFocusEffect:fn=>React.useEffect(fn,[fn]), useRouter: () => ({ navigate() {}, dismissTo() {}, replace() {} }), useLocalSearchParams: () => ({ who: 'B', who_id: 'b' }) },
  '../src/monetization-actions': load('src/monetization-actions.ts',{}),
  '../src/chat': chat, '../src/messages': load('src/messages.ts', { './i18n': i18n, './api': api, './chat': chat }),
  '../src/i18n': i18n, '../src/state': state, '../src/api': api,
  '../src/chat-lifecycle': lifecycle,
  '../src/intent': { withScheme: x => x },
  '../src/keyboard': { useKeyboardInset: () => 0, dockBottom: () => 0 },
  '../src/polling': { usePolling: fn => polls.push(fn) },
  '../src/monetization': { MONETIZATION: { chatQuota: () => 'chat_quota', unknown: () => 'unknown', returnToAction:()=> 'return-to-action' } },
  '../src/components/Sheet': { Sheet: 'Sheet', SheetItem: 'SheetItem' },
  'expo-clipboard': {}, '../src/components/MessageFeed': { MessageFeed: 'MessageFeed' },
  '../src/voice': { useVoiceMessage: (cb, disabled) => { voiceCallback = cb; voiceDisabled = disabled; return { phase: 'idle', disabled }; }, VoiceMessageControl: 'VoiceMessageControl' },
  '../src/videonote': { VideoNoteButton: 'VideoNoteButton' },
  '../src/components/icons': new Proxy({}, { get: (_o, key) => key }),
  '../src/components/Cover': { Cover: 'Cover' },
  '../src/components/LiquidGlass': { GlassIconButton: 'GlassIconButton', GlassSurface: 'GlassSurface' },
  '../src/components/SendArrow': { SendArrow: 'SendArrow' },
  '../src/theme': load('src/theme.ts', {}),
  '../src/components/Ambient': { Ambient: 'Ambient' },
};
const Screen = load('app/conversation.tsx', stubs).default().type;
function render() {
  cursor = 0; effects = []; polls = []; dirty = false;
  tree = Screen(); const pending = effects; effects = []; pending.forEach(fn => fn());
}
async function settle() {
  for (let i = 0; i < 16; i++) { await Promise.resolve(); if (dirty) render(); }
}
function nodes(v = tree) {
  if (Array.isArray(v)) return v.flatMap(nodes);
  if (!v || typeof v !== 'object') return [];
  return [v, ...nodes(v.props?.children)];
}
const find = type => nodes().find(n => n.type === type);
const textOf = v => Array.isArray(v) ? v.map(textOf).join(' ') : v && typeof v === 'object' ? textOf(v.props?.children) : String(v || '');
const press = label => {
  const node = nodes().find(n => n.props?.onPress && (n.props.label === label || textOf(n.props.children) === label));
  assert.ok(node, 'button ' + label); node.props.onPress();
};
async function mount(stateName = 'closed',initialReply=null) {
  cells = []; prefs = {}; token = 'a-token'; timers.clear(); messagesSent = []; ends = []; threadReply = initialReply;
  messageMode = 'ok'; endMode = 'ok';
  server = { peerId: 'b', state: stateName, sessionId: stateName === 'active' ? 'old-session' : null, blocked: false };
  history = [{ id: 'old-message', from: 'A', to: 'B', from_id: 'a', to_id: 'b', text: 'saved history', t: 10 }];
  render(); await settle();
}
async function send(text) {
  find('TextInput').props.onChangeText(text); await settle();
  find('TextInput').props.onSubmitEditing(); await settle();
}
async function end() {
  press(chat.CHATMENU.endChat()); await settle();
  for (let n = 0; n < 4; n++) {
    const entry = [...timers].find(([, t]) => t.ms === 1000);
    assert.ok(entry, 'undo timer'); timers.delete(entry[0]); entry[1].fn(); await settle();
  }
}
(async () => {
  for(const invalid of [undefined,{}, {peerId:'elsewhere',state:'active',sessionId:'s',blocked:false,serverTime:1000},
    {peerId:'b',state:'closed',sessionId:'stale-active',blocked:false,serverTime:1000},
    {peerId:'b',state:'active',sessionId:'s',blocked:'false',serverTime:1000}]) {
    await mount('active',async()=>({chat:invalid,messages:history}));
    assert.equal(find('TextInput').props.editable,false,'initial accepted request cannot substitute for lifecycle evidence');
    assert.equal(voiceDisabled,true);assert.equal(find('VideoNoteButton').props.disabled,true);
    for(const initial of ['active','closed']) {
      await mount(initial);
      threadReply=async()=>({chat:invalid,messages:history});await polls[1]();await settle();
      assert.equal(find('TextInput').props.editable,false,'HTTP success without pair evidence must fail closed');
      assert.equal(voiceDisabled,true);assert.equal(find('VideoNoteButton').props.disabled,true);
      assert.ok(find('MessageFeed').props.msgs.some(m=>m.text==='saved history'));
      await send('unsafe');assert.equal(messagesSent.length,0);
      threadReply=null;await polls[1]();await settle();
      assert.equal(find('TextInput').props.editable,initial==='active','closed pair still needs explicit resume');
    }
  }
  await mount('legacy');assert.equal(find('TextInput').props.editable,true,'valid legacy lifecycle remains supported');
  await mount();
  assert.equal(messagesSent.length, 0, 'opening history does not create a session');
  assert.equal(find('TextInput').props.editable, false);
  press(chat.CHAT.resumeChat()); await settle();
  assert.equal(find('TextInput').props.editable, true);
  assert.ok(textOf(tree).includes(chat.CHAT.resumeNote()));
  messageMode = 'quota'; await send('refused');
  assert.equal(prefs.chats.b.state, 'closed');
  assert.ok(find('MessageFeed').props.msgs.some(m => m.text === 'refused' && m.state === 'failed'));
  assert.ok(textOf(tree).includes('chat_quota'));
  messageMode = 'network'; await send('network refusal');
  assert.equal(prefs.chats.b.state, 'closed');
  messageMode = 'ok'; await send('resumed');
  assert.equal(prefs.chats.b.state, 'active');
  assert.ok(textOf(tree).includes(chat.CHAT.chatResumed()));
  assert.ok(find('MessageFeed').props.msgs.some(m => m.text === 'saved history'));
  endMode = 'error'; await end();
  assert.equal(prefs.chats.b.state, 'active', 'failed end cannot archive');
  assert.ok(textOf(tree).includes(chat.CHAT.endFailed()));
  const retryKey = ends[0][2]; endMode = 'ok'; await end();
  assert.equal(ends[1][2], retryKey, 'uncertain end retries with the same command identity');
  assert.equal(prefs.chats.b.state, 'closed');
  assert.equal(find('TextInput').props.editable, false);
  assert.ok(textOf(tree).includes(chat.CHAT.chatClosed()));
  await mount('active'); server.blocked = true; server.state = 'closed'; server.sessionId = null;
  await polls[1](); await settle();
  assert.equal(find('TextInput').props.editable, false);
  assert.equal(voiceDisabled, true);
  assert.equal(find('VideoNoteButton').props.disabled, true);
  await send('blocked'); assert.equal(messagesSent.length, 0);
  assert.ok(textOf(tree).includes(chat.CHAT.chatBlocked()));
  await mount('active'); const staleVoice = voiceCallback; token = 'other-account';
  staleVoice({ transcript: 'late voice', id: 'v' }); await settle();
  assert.equal(messagesSent.length, 0, 'late recording callback cannot send under another account');
  await mount('active'); const unmountedVoice = voiceCallback;
  cells.forEach(c => c.cleanup?.());
  unmountedVoice({ transcript: 'late voice after leaving', id: 'v' }); await settle();
  assert.equal(messagesSent.length, 0, 'unmounted screen cannot send');
  // Three polls overlap (each may exceed 4 seconds). A newer START must not starve
  // the first completed response; only a newer APPLIED response supersedes it.
  await mount('active');
  const pending=[];threadReply=()=>new Promise(resolve=>pending.push(resolve));
  const first=polls[1](),second=polls[1](),third=polls[1]();
  const response=(id,time)=>({chat:{peerId:'b',state:'active',sessionId:'s',blocked:false,serverTime:time},messages:[{id,from:'B',from_id:'b',text:id,t:time}]});
  pending[0](response('first-slow',1000));await first;await settle();
  assert.ok(find('MessageFeed').props.msgs.some(m=>m.id==='first-slow'),'slow response is applied despite newer pending polls');
  pending[2](response('newer-applied',1002));await third;await settle();
  pending[1](response('late-older',1001));await second;await settle();
  assert.ok(find('MessageFeed').props.msgs.some(m=>m.id==='newer-applied'));
  assert.ok(!find('MessageFeed').props.msgs.some(m=>m.id==='late-older'));
  const oldAccount=polls[1]();token='other-account';pending[3](response('old-account',1003));await oldAccount;await settle();
  assert.ok(!find('MessageFeed').props.msgs.some(m=>m.id==='old-account'));
  await mount('active');const pendingPeer=[];threadReply=()=>new Promise(resolve=>pendingPeer.push(resolve));
  const oldPeer=polls[1]();cells.forEach(c=>c.cleanup?.());pendingPeer[0](response('old-pair',1004));await oldPeer;await settle();
  assert.ok(!find('MessageFeed').props.msgs.some(m=>m.id==='old-pair'),'keyed pair unmount rejects late poll');
  const actions=stubs['../src/monetization-actions'];let retries=0;
  const action=actions.deferAction({session:'a-token',key:'recovery',operation:'message',payload:{text:'original'},reason:'chat_quota'},async()=>{retries++;return {};});
  assert.ok(actions.navigateReturnAction('a-token','plus','conversation'));actions.blurReturnAction('a-token','plus');
  await mount('active');await end();assert.equal(retries,0,'ending another chat never auto-replays');
  press('return-to-action');assert.equal(retries,0);assert.ok(actions.recoveryAction('a-token','plus'));
  await actions.resumeReturnAction('a-token');await action;assert.equal(retries,1);
  console.log('PASS conversation handlers: explicit resume, quota/network failure, confirmed delivery/end, end retry, blocked text/voice/video, stale media callbacks');
  console.log('PASS conversation overlapping slow polls, latest-applied ordering, account/pair stale responses, recovery end then explicit retry');
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => {
  global.setTimeout = nativeSetTimeout; global.clearTimeout = nativeClearTimeout;
});
