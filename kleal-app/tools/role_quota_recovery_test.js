/** Actual role-screen + API handlers with synthetic fetch. Not a native UI pass. */
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const root = path.resolve(__dirname, '..'), ts = require(path.join(root, 'node_modules/typescript'));
function load(file, stubs) {
  const m = { exports: {} };
  const out = ts.transpileModule(fs.readFileSync(path.join(root, file), 'utf8'), {
    compilerOptions: { module: 1, target: 7, jsx: ts.JsxEmit.React, esModuleInterop: true },
  }).outputText;
  Function('require', 'module', 'exports', out)(name => {
    if (name in stubs) return stubs[name];
    if (name.endsWith('/MonetizationDialog')) return load('src/components/MonetizationDialog.tsx', {react: React, 'react-native': native, '../theme': load('src/theme.ts', {})});
    throw new Error('Unmocked ' + name);
  }, m, m.exports);
  return m.exports;
}
let lang = 0;
const i18n = { T: (...v) => v[lang], getLang: () => ['ru', 'en', 'es'][lang], useLang: () => ['ru', 'en', 'es'][lang], replyLang: () => 'ru', dateLocale: () => 'ru' };
const roles = load('src/roles.ts', { './i18n': i18n });
const { ROLE } = roles;
const billing = load('src/monetization.ts', { './i18n': i18n });
const { MONETIZATION, PLUS } = billing;
const actions = load('src/monetization-actions.ts', {});
const platform=process.env.KLEAL_ROLE_PLATFORM || 'web';
let disk = null, actor = 'b', session, group, quota, requests, alerts, navigations, params, postFailure, deferredReply, focused=true;
let cells = [], cursor, effects, dirty, tree, polls;
const same = (a, b) => a && b && a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
const React = {
  createElement: (type, props, ...children) => ({ type, props: { ...props, children } }),
  useState(initial) {
    const i = cursor++;
    if (!(i in cells)) cells[i] = { value: typeof initial === 'function' ? initial() : initial };
    const cell = cells[i];
    return [cell.value, value => { const next = typeof value === 'function' ? value(cell.value) : value;
      if (!Object.is(next, cell.value)) { cell.value = next; dirty = true; } }];
  },
  useRef(value) { const i = cursor++; if (!(i in cells)) cells[i] = { current: value }; return cells[i]; },
  useMemo(fn, deps) { const i = cursor++; if (!same(cells[i]?.deps, deps)) cells[i] = { value: fn(), deps }; return cells[i].value; },
  useCallback(fn, deps) { return React.useMemo(() => fn, deps); },
  useEffect(fn, deps) {
    const i = cursor++;
    if (!same(cells[i]?.deps, deps)) {
      const prev = cells[i], cell = { deps }; cells[i] = cell;
      effects.push(() => { prev?.cleanup?.(); cell.cleanup = fn(); });
    }
  },
};
const native = { Platform:{OS:platform}, ...Object.fromEntries(['View', 'Text', 'ScrollView', 'Pressable', 'Image', 'ActivityIndicator', 'Modal'].map(n => [n, n])),
  Image: { prefetch: async () => {} }, StyleSheet: { create: x => x }, Alert: { alert: (...args) => alerts.push(args) } };
if(platform==='web') native.Alert=require(path.join(root,'node_modules/react-native-web/dist/cjs/exports/Alert/index.js'));
const api = load('src/api.ts', {
  'react-native': native, '@react-native-async-storage/async-storage': { getItem: async () => disk, setItem: async (_k, v) => { disk = v; } },
  './i18n': i18n, './interest-label': { registerInterestLabels() {} }, './monetization-actions': actions,
  './thinking': { whileThinking: promise => promise },
});
function publicGroup(id = actor) {
  return { ...structuredClone(group), i_am_owner: group.owner_id === id, i_am_member: true,
    can_hand_over: group.owner_id === id && group.role_offer?.state !== 'open' && group.takeover?.state !== 'open' };
}
global.fetch = async (url, options) => {
  const pathname = new URL(url).pathname;
  const sentActor = options.headers.Authorization?.split(':').at(-1);
  let value = { ok: true }, status = 200;
  if (pathname === '/api/onboarding/profile') value = { user: { id: sentActor, name: 'Same' } };
  else if (pathname === '/api/agent/gintent') value = { ok: true, group: publicGroup(sentActor) };
  else {
    const payload = JSON.parse(options.body); requests.push({ pathname, payload, actor: sentActor });
    if (deferredReply) await deferredReply;
    if (postFailure) throw new Error('synthetic 503');
    if (pathname === '/api/agent/gintent-role-respond') {
      if (sentActor !== group.role_offer?.to_id || group.role_offer.state !== 'open') value = { ok: false, error: 'NO_OPEN_OFFER' };
      else if (payload.accept && quota) { status = 409; value = { ok: false, error: 'organizer_search_quota' }; }
      else {
        group.role_offer.state = payload.accept ? 'accepted' : 'declined'; group.role_offer.closed_at = Date.now() / 1000;
        if (payload.accept) { group.owner_id = sentActor; group.role_from = { who: 'Same', who_id: 'a', how: 'offer' }; }
        else group.role_offer.declined_ids = [sentActor];
        value = { ok: true, group: publicGroup(sentActor) };
      }
    } else if (pathname === '/api/agent/gintent-role-offer') {
      assert.equal(sentActor, group.owner_id, 'only the owner can offer a role');
      assert.ok(payload.to_id, 'role offer must carry recipient ID');
      group.role_offer = { to: 'Same', to_id: payload.to_id, by: 'Same', by_id: sentActor, state: 'open', at: Date.now() / 1000 };
      value = { ok: true, group: publicGroup(sentActor) };
    } else if (pathname === '/api/agent/gintent-takeover-back') {
      assert.equal(sentActor, group.owner_id);
      if (payload.hand && quota) { status = 409; value = { ok: false, error: 'organizer_search_quota' }; }
      else { group.takeover.state = 'stopped'; value = { ok: true, group: publicGroup(sentActor) }; }
    } else if (pathname === '/api/agent/gintent-role-withdraw') {
      assert.equal(sentActor, group.owner_id);
      group.role_offer.state = 'withdrawn'; value = { ok: true, group: publicGroup(sentActor) };
    } else if (pathname === '/api/agent/search-command') {
      assert.equal(sentActor, 'b'); assert.equal(payload.operation, 'pause'); quota = false;
    } else throw new Error('Unexpected API ' + pathname);
  }
  return { ok: status === 200, status, headers: { get: () => 'application/json' }, text: async () => JSON.stringify(value) };
};
const router = {
  navigate: target => navigations.push(target), dismissTo: target => navigations.push(target),
  canGoBack: () => true, back: () => navigations.push('back'),
  setParams: values => { params = { ...params, ...values }; dirty = true; },
};
const stubs = {
  react: React, 'react-native': native, 'react-native-safe-area-context': { useSafeAreaInsets: () => ({ top: 0 }) },
  'expo-router': { useRouter: () => router, useLocalSearchParams: () => params, useIsFocused: () => focused,
    useNavigationContainerRef:()=>({getCurrentRoute:()=>({key:'role',name:'grole',params}),getRootState:()=>undefined,resetRoot(){}}) },
  '../src/i18n': i18n, '../src/api': api, '../src/state': { useOnb: () => ({ session, profile: { name: 'Same' } }) },
  '../src/roles': roles, '../src/monetization': billing, '../src/monetization-actions': actions,
  '../src/navScroll': { useNavCollapse: () => () => {} },
  '../src/groups': { ROOM: { andList: x => x.join(', '), nameAge: x => x, infoTitle: () => '', gone: () => 'gone', aboutUnset: () => '', roleOrganiser: () => 'organizer' }, GINVITE: { exactSpot: () => '' }, groupPlace: () => '', groupCallLine: () => '', isOnlineGroup: () => false },
  '../src/gplan': { elapsed: () => 0, hoursLeft: () => 1 }, '../src/polling': { usePolling: fn => polls.push(fn) },
  '../src/components/icons': new Proxy({}, { get: (_o, key) => key }), '../src/theme': load('src/theme.ts', {}),
  '../src/components/Cover': { Cover: 'Cover' }, '../src/components/Glass': { GlassPill: 'GlassPill' },
  '../src/components/LiquidGlass': { GlassBack: 'GlassBack', GlassSurface: 'GlassSurface' },
  '../src/components/BottomNav': { BottomNav: 'BottomNav' }, '../src/components/Sheet': { Sheet: 'Sheet', SheetText: 'SheetText' },
};
params = { gid: 'g' }; session = 'test:b';
const Wrapper = load('app/grole.tsx', stubs).default, Screen = Wrapper().type;
function render() {
  cursor = 0; effects = []; polls = []; dirty = false;
  tree = Screen({ session }); const pending = effects; effects = []; pending.forEach(fn => fn());
}
async function settle() { for (let i = 0; i < 100; i++) { await Promise.resolve(); if (dirty) render(); } }
function nodes(v = tree) {
  if (Array.isArray(v)) return v.flatMap(nodes);
  if (!v || typeof v !== 'object' || (v.type === 'Sheet' && !v.props.visible)) return [];
  return [v, ...nodes(v.props?.children)];
}
const textOf = v => Array.isArray(v) ? v.map(textOf).join(' ') : v && typeof v === 'object' ? textOf(v.props?.children) : String(v || '');
const button = label => nodes().find(n => n.props?.label === label && n.props.onPress);
const press = label => { const n = button(label); assert.ok(n, 'button ' + label); n.props.onPress(); };
const latestDialog = () => {
  if(platform!=='web') return alerts.at(-1);
  const modal=nodes().find(n=>n.type==='Modal'); if(!modal) return;
  const children=nodes(modal),texts=children.filter(n=>n.type==='Text').map(textOf);
  return [texts[0],texts[1],children.filter(n=>n.type==='Pressable').map(n=>({text:textOf(n),onPress:n.props.onPress}))];
};
const alertPress = label => { const b = latestDialog()?.[2].find(b => b.text === label); assert.ok(b, 'alert button ' + label); b.onPress(); };
const sheet = () => nodes().find(n => n.type === 'Sheet');
function unmount() { for (const c of cells) c?.cleanup?.(); cells = []; }
async function mount(id = 'b', mode = 'offer', reset = true) {
  unmount(); actor = id; session = 'test:' + id; api.setSession(session); await api.ensureMe();
  if (reset) {
    group = { gid: 'g', title: 'Group', owner: 'Same', owner_id: 'a', members: ['a', 'b', 'c'].map(id => ({ name: 'Same', id })),
      role_offer: mode === 'offer' ? { state: 'open', to: 'Same', to_id: 'b', by: 'Same', by_id: 'a', at: Date.now() / 1000 } : undefined,
      takeover: mode === 'vote' ? { state: 'open', by: 'Same', by_id: 'b' } : undefined };
  }
  quota = true; requests = []; alerts = []; navigations = []; params = { gid: 'g' }; postFailure = false; deferredReply = null;
  focused=true;
  actions.configureMonetization({ blocked: async () => { throw new Error('generic quota handler must not run'); } });
  render(); await settle();
}
async function take() { press(ROLE.takeRole()); await settle(); }
function noError() { assert.ok(!textOf(tree).includes(ROLE.actionFailed()), 'cancellation is not a network error'); }
(async () => {
  for (lang = 0; lang < 3; lang++) {
    await mount(); await take();
    assert.equal(group.owner_id, 'a'); assert.equal(latestDialog()[1], ROLE.quotaOwn());
    assert.ok(!latestDialog()[2].some(b => b.text === MONETIZATION.chooseOther()), 'recipient is not offered owner rights');
    alertPress(ROLE.returnChoice()); await settle();
    assert.equal(sheet().props.title, ROLE.keepWithTitle('Same')); noError();
    assert.equal(requests.length, 1, 'alternative opens confirmation without silently declining');
    press(ROLE.keepWithBtn('Same')); await settle();
    assert.equal(group.role_offer.state, 'declined'); assert.equal(group.owner_id, 'a');
    assert.equal(group.members.length, 3); assert.equal(quota, true, 'decline does not pause own or group search');
    assert.deepEqual(requests.map(r => r.payload.accept), [true, false]); noError();
    // Owner sees the different participant despite all three display names being equal.
    await mount('a', 'offer', false);
    assert.ok(button(ROLE.offerTo('Same')));
    press(ROLE.offerTo('Same')); await settle();
    assert.equal(requests.at(-1).payload.to_id, 'c'); assert.equal(group.owner_id, 'a');
  }
  lang = 0;
  await mount(); await take(); alertPress(PLUS.cancel()); await settle();
  noError(); assert.equal(group.role_offer.state, 'open'); assert.equal(group.owner_id, 'a');
  await take(); alertPress(MONETIZATION.freeSlot()); await settle();
  assert.equal(navigations.at(-1).pathname, '/plus');assert.ok(navigations.at(-1).params.recoveryId);
  const acceptKey = requests.at(-1).payload.commandId;
  // Plus return/gesture cancellation leaves the invitation available and no error.
  actions.cancelReturnAction(); await settle(); noError();
  assert.equal(group.role_offer.state, 'open');
  await take(); alertPress(MONETIZATION.freeSlot()); await settle();
  const retryKey = requests.at(-1).payload.commandId;
  assert.notEqual(acceptKey, retryKey, 'explicit cancellation retires old command');
  postFailure = true;
  await assert.rejects(actions.resumeReturnAction(session)); await settle();
  assert.equal(actions.returnAction(session).key, retryKey); assert.equal(group.owner_id, 'a');
  postFailure = false;
  await assert.rejects(actions.resumeReturnAction(session), e => e.body.error === 'organizer_search_quota');
  if(platform==='web') assert.equal(latestDialog(),undefined,'retry stays on Plus without reopening dialog');
  else assert.equal(alerts.length, 3, 'retry stays on Plus and does not reopen quota dialog');
  await api.api.post('/api/agent/search-command', { operation: 'pause', searchId: 'own-search' }, undefined, { quotaPresentation: 'inline' });
  await actions.resumeReturnAction(session); await settle();
  assert.equal(group.owner_id, 'b'); assert.equal(group.role_offer.state, 'accepted'); noError();
  const repeated = requests.filter(r => r.pathname.endsWith('role-respond') && r.payload.commandId === retryKey);
  assert.equal(repeated.length, 4, 'network, quota and successful retries use the exact same command');
  // Owner cannot fix the candidate's quota by pausing the owner's own search.
  await mount('a', 'vote'); press(ROLE.handTo('Same')); await settle();
  assert.equal(latestDialog()[1], ROLE.quotaOther());
  assert.ok(!latestDialog()[2].some(b => b.text === MONETIZATION.freeSlot()));
  alertPress(MONETIZATION.chooseOther()); await settle();
  assert.equal(sheet().props.title, MONETIZATION.chooseOther());
  press(MONETIZATION.continue()); await settle();
  assert.equal(group.takeover.state, 'stopped'); assert.equal(params.pick, '1');
  press(ROLE.offerTo('Same')); await settle();
  assert.equal(requests.at(-1).payload.to_id, 'c'); assert.equal(group.owner_id, 'a'); noError();
  // A role change on another device while confirmation is open revokes the picker.
  await mount('a', 'vote'); press(ROLE.handTo('Same')); await settle();
  alertPress(MONETIZATION.chooseOther()); await settle();
  group.owner_id = 'c';
  press(MONETIZATION.continue()); await settle();
  assert.equal(requests.length, 1, 'fresh owner check prevents closing someone else’s vote');
  assert.notEqual(params.pick, '1'); assert.equal(group.takeover.state, 'open');
  // Ordinary request errors remain visible, unlike cancellation.
  await mount(); postFailure = true; await take();
  assert.ok(textOf(tree).includes(ROLE.actionFailed())); assert.equal(group.owner_id, 'a');
  // A spoofed pick parameter never grants a recipient the owner picker.
  await mount(); params.pick = '1'; render(); await settle(); assert.equal(button(ROLE.offerTo('Same')), undefined);
  assert.equal(roles.roleQuotaRecovery({ ...publicGroup(), i_am_owner: true }, 'b').alternative, 'decline');
  assert.equal(roles.roleQuotaRecovery(publicGroup(), '').alternative, '');
  // Same-name account switch while alert is open: old callbacks cannot navigate/mutate.
  await take(); const stale = latestDialog()[2]; const oldKey = Wrapper().props.key;
  actor = 'c'; session = 'test:c'; api.setSession(session); assert.notEqual(Wrapper().props.key, oldKey);
  for (const b of stale) b.onPress(); await settle();
  assert.equal(navigations.length, 0); assert.equal(requests.length, 1); noError();
  // Unmount while a role request is in flight: no late group/route update or quota alert.
  await mount(); let release; deferredReply = new Promise(r => { release = r; });
  press(ROLE.takeRole()); await settle(); unmount(); const oldTree = tree;
  release(); await settle(); assert.equal(tree, oldTree); assert.equal(alerts.length, 0); assert.equal(navigations.length, 0);
  for(const exit of ['blur','unmount','proposal']){
    await mount();await take();const late=latestDialog()[2];
    if(exit==='blur'){focused=false;render();await settle();}
    else if(exit==='unmount')unmount();
    else group.role_offer.state='withdrawn';
    late.find(b=>b.text===MONETIZATION.freeSlot()).onPress();await settle();
    assert.equal(requests.length,1,exit);assert.equal(navigations.length,0,exit);assert.equal(actions.returnAction(session),null,exit);
    if(exit!=='unmount')assert.ok(!button(ROLE.takeRole())?.props.disabled,'pending action settled after '+exit);
  }
  if(platform==='web')assert.equal(alerts.length,0,'installed RN Web Alert remained a no-op');
  console.log('PASS role quota recovery: RU/EN/ES decline, owner selection by ID, cancel, own-slot durable retry, stale account/unmount guards');
})().catch(e => { console.error(e); process.exitCode = 1; }).finally(() => { unmount(); actions.cancelReturnAction(); });
