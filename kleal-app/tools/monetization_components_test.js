/** Real Boundary/Plus callbacks + real API/actions, synthetic transport. Not native QA. */
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const root = path.resolve(__dirname, '..'), ts = require(path.join(root, 'node_modules/typescript'));
function load(file, stubs = {}, mutation) {
  let source = fs.readFileSync(path.join(root, file), 'utf8');
  if (mutation) { assert.ok(source.includes(mutation[0]), 'mutation target'); source = source.replace(...mutation); }
  const m = { exports: {} };
  const code = ts.transpileModule(source, {compilerOptions:{module:1,target:7,jsx:ts.JsxEmit.React,esModuleInterop:true}}).outputText;
  Function('React','require','module','exports','setInterval','clearInterval','setTimeout','clearTimeout',code)(stubs.react, name => { if(name in stubs) return stubs[name];
    if(name.endsWith('/MonetizationDialog')) return load('src/components/MonetizationDialog.tsx',{react:stubs.react,'react-native':stubs['react-native'],'../theme':load('src/theme.ts')});
    throw Error('Unmocked '+name); },m,m.exports,
    stubs.__timers?.setInterval || setInterval,stubs.__timers?.clearInterval || clearInterval,
    stubs.__timers?.setTimeout || setTimeout,stubs.__timers?.clearTimeout || clearTimeout);
  return m.exports;
}
const tick = () => new Promise(resolve => setImmediate(resolve));
function renderer() {
  let cells=[], cursor=0, effects=[], dirty=false, tree, component;
  const focus=new Set();let focused=true;
  const same=(a,b)=>a && b && a.length===b.length && a.every((v,i)=>Object.is(v,b[i]));
  const React={
    createElement:(type,props,...children)=>typeof type==='function' ? type({...props,children}) : ({type,props:{...props,children}}),
    useState(initial) { const i=cursor++; if(!(i in cells)) cells[i]={value:typeof initial==='function'?initial():initial};
      return [cells[i].value,v=>{const next=typeof v==='function'?v(cells[i].value):v;if(!Object.is(next,cells[i].value)){cells[i].value=next;dirty=true;}}]; },
    useRef(value) { const i=cursor++; if(!(i in cells)) cells[i]={current:value};return cells[i]; },
    useMemo(fn,deps) { const i=cursor++;if(!same(cells[i]?.deps,deps))cells[i]={value:fn(),deps};return cells[i].value; },
    useCallback(fn,deps) { return React.useMemo(()=>fn,deps); },
    useEffect(fn,deps) { const i=cursor++;if(!same(cells[i]?.deps,deps)){const prev=cells[i];cells[i]={deps};effects.push(()=>{prev?.cleanup?.();cells[i].cleanup=fn();});} },
  };
  const render=()=>{cursor=0;effects=[];dirty=false;tree=component();effects.forEach(fn=>fn());};
  const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v && typeof v==='object'?[v,...nodes(v.props?.children)]:[];
  const text=v=>Array.isArray(v)?v.map(text).join(' '):v && typeof v==='object'?text(v.props?.children):String(v||'');
  return {React,nodes:()=>nodes(tree),text:()=>text(tree),mount(fn){component=fn;render();},
    async settle(){for(let i=0;i<8;i++){await tick();if(dirty)render();}},
    rerender:render,
    focusEffect(fn){React.useEffect(()=>{const entry={fn,cleanup:focused?fn():undefined};focus.add(entry);return ()=>{entry.cleanup?.();focus.delete(entry);};},[fn]);},
    blur(){focused=false;for(const entry of focus){entry.cleanup?.();entry.cleanup=undefined;}},
    focus(){if(focused)return;focused=true;for(const entry of focus)entry.cleanup=entry.fn();},
    unmount(){cells.forEach(c=>c.cleanup?.());},
    press(label){const n=nodes(tree).find(n=>n.props.onPress && (text(n.props.children)===label || n.props.label===label || n.props.accessibilityLabel===label));assert.ok(n,'button '+label);assert.ok(!n.props.disabled,'enabled '+label);n.props.onPress();},
  };
}
function membership() { return {ok:true,version:2,phase:'phase2a',state:'free',plan:'free',serverTime:100,
  previewStartedAt:null,expiresAt:null,previewEligible:false,previewNotice:false,enforcementEnabled:true,
  purchaseAvailable:false,restoreAvailable:false,permissions:{publishSearch:true,initiateChat:true,reply:true,groupChat:true,manualCoordination:true,basicFilters:true},
  usage:{activeSearches:0,initiatedChats:0},limits:{activeSearches:1,initiatedChats:1},reasons:{publishSearch:null,initiateChat:null},
  blockerIds:{searches:[],chats:[]},searches:[],keepSearchId:null}; }
async function fixture(mutation,realNavigation=false,platform='ios') {
  const boundary=renderer(), plus=renderer(), alerts=[], routes=[], posts=[];
  const storage={value:null}, actions=load('src/monetization-actions.ts');
  const i18n={T:(...v)=>v[1],dateLocale:()=> 'en',getLang:()=> 'en',replyLang:()=> 'en',useLang(){}};
  const api=load('src/api.ts',{'react-native':{Image:{prefetch:async()=>{}}},
    '@react-native-async-storage/async-storage':{getItem:async()=>storage.value,setItem:async(_k,v)=>{storage.value=v;}},
    './i18n':i18n,'./thinking':{whileThinking:p=>p},'./interest-label':{registerInterestLabels(){}},'./monetization-actions':actions});
  const model={status:membership(),reply:null,loads:0,statusRead:null};
  global.fetch=async(url,init)=>{
    let body,status=200;
    if(url.includes('/profile')) body={user:{id:'a'}};
    else if(init.method!=='POST'){body=await model.read?.(url);if(body===undefined){body=model.statusRead?await model.statusRead():model.status;model.loads++;}}
    else {const p={url,body:JSON.parse(init.body)};posts.push(p);const r=model.reply?await model.reply(p):{body:{ok:true}};body=r.body;status=r.status||200;}
    return {ok:status<400,status,text:async()=>JSON.stringify(body)};
  };
  api.setSession('token-a');await api.ensureMe();
  const labels=load('src/monetization.ts',{'./i18n':i18n});
  const listeners=new Set(),timers=new Map();let clock=0;
  const native={Alert:{alert:(title,message,buttons)=>alerts.push({title,message,buttons})},AppState:{currentState:'active',
    addEventListener:(_event,fn)=>{listeners.add(fn);return {remove(){listeners.delete(fn);}};}},StyleSheet:{create:x=>x},
    Platform:{OS:platform},...Object.fromEntries(['View','Text','Pressable','ActivityIndicator','Modal'].map(n=>[n,n]))};
  if(platform==='web') native.Alert=require(path.join(root,'node_modules/react-native-web/dist/cjs/exports/Alert/index.js'));
  const stack=realNavigation?require('./expo_stack_harness').createStack(actions.recoveryScreenIdentity,mutation==='singular'):null;
  const router=stack || {navigate:to=>routes.push(to),back:()=>routes.push('back'),dismissTo:to=>routes.push(to),replace:to=>routes.push(to),canGoBack:()=>true};
  const navigation=stack?.navigation || {getCurrentRoute:()=>({key:'origin',name:'conversation',params:{who:'Original',who_id:'original'}}),getRootState:()=>undefined,resetRoot(){}};
  const state={useOnb:()=>({session:api.getSession(),profile:{name:'Me'},msg:{}}),markSeen(){},setMsgPrefs(){},syncChatLifecycle:()=>true};
  const Boundary=load('src/components/MonetizationBoundary.tsx',{react:boundary.React,'react-native':native,'expo-router':{router,useNavigationContainerRef:()=>navigation},
    '../api':api,'../state':state,'../monetization':labels,'../monetization-actions':actions},
    mutation==='cancel'?["onPress:() => reject(new Error('action_cancelled'))","onPress:() => resolve()"]:
    mutation==='notice'?["data.previewNotice && !noticing","data.previewNotice && noticing"]:null).MonetizationBoundary;
  const Client=load('src/membership-client.ts',{'./api':api,'./monetization':labels});
  let timerId=0;
  const polling=load('src/polling.ts',{react:plus.React,'react-native':native,
    'expo-router':{useFocusEffect:fn=>plus.focusEffect(fn)},
    __timers:{setInterval:(fn,ms)=>{const id=++timerId;timers.set(id,{fn,ms,next:clock+ms});return id;},clearInterval:id=>timers.delete(id)}});
  const Plus=load('app/plus.tsx',{react:plus.React,'react-native':native,
    'expo-router':{useRouter:()=>router,useFocusEffect:fn=>plus.focusEffect(fn)},'../src/components/ProfileShell':{ProfileShell:'ProfileShell',Card:'Card'},
    '../src/i18n':i18n,'../src/state':state,'../src/api':api,'../src/membership-client':Client,'../src/polling':polling,
    '../src/monetization':labels,'../src/monetization-actions':actions,'../src/theme':load('src/theme.ts')},
    mutation==='swap'?["resumeSearch(search.id,inlineSwap.blockerId)","resumeSearch(search.id,search.id)"]:null).default;
  boundary.mount(Boundary);await boundary.settle();
  return {boundary,plus,actions,api,model,storage,posts,alerts,routes,router,stack,...labels,
    background(value){native.AppState.currentState=value?'background':'active';for(const fn of listeners)fn(native.AppState.currentState);},
    async advance(ms){clock+=ms;for(const t of timers.values())if(clock>=t.next){t.next=clock+t.ms;t.fn();}await plus.settle();},
    async openPlus(){plus.mount(Plus);plus.focus();await plus.settle();},
    async conversation(params){
      const screen=renderer(),timeouts=new Map();let timeoutId=0;
      const chat=load('src/chat.ts',{'./i18n':{...i18n,use12h:()=>false},'./api':api,
        './names':{acc:x=>x,dat:x=>x,gen:x=>x,ins:x=>x}});
      const Conversation=load('app/conversation.tsx',{
        '../src/online-ask':{takeOpener:async()=>null},
        react:screen.React,'react-native':{...native,Platform:{OS:'ios'},Linking:{},
          ...Object.fromEntries(['ScrollView','TextInput','Image','KeyboardAvoidingView'].map(n=>[n,n]))},
        'expo-router':{useFocusEffect:fn=>screen.focusEffect(fn),useRouter:()=>router,useLocalSearchParams:()=>params},
        'react-native-safe-area-context':{useSafeAreaInsets:()=>({top:0,bottom:0})},
        '../src/chat':chat,'../src/messages':load('src/messages.ts',{'./i18n':i18n,'./api':api,'./chat':chat}),'../src/i18n':{...i18n,use12h:()=>false},
        '../src/state':state,'../src/api':api,'../src/monetization-actions':actions,'../src/monetization':labels,
        '../src/chat-lifecycle':load('src/chat-lifecycle.ts'),'../src/intent':{withScheme:x=>x},
        '../src/keyboard':{useKeyboardInset:()=>0,dockBottom:()=>0},
        '../src/polling':{usePolling:fn=>screen.focusEffect(screen.React.useCallback(()=>{void fn();},[]))},
        '../src/components/Sheet':{Sheet:'Sheet',SheetItem:'SheetItem'},'expo-clipboard':{},
        '../src/components/MessageFeed':{MessageFeed:'MessageFeed'},
        '../src/voice':{useVoiceMessage:()=>({phase:'idle'}),VoiceMessageControl:'VoiceMessageControl'},
        '../src/videonote':{VideoNoteButton:'VideoNoteButton'},
        '../src/components/icons':new Proxy({},{get:(_o,k)=>k}),
        '../src/components/Cover':{Cover:'Cover'},'../src/components/LiquidGlass':{GlassIconButton:'GlassIconButton',GlassSurface:'GlassSurface'},
        '../src/components/SendArrow':{SendArrow:'SendArrow'},'../src/components/Ambient':{Ambient:'Ambient'},'../src/theme':load('src/theme.ts'),
        __timers:{setTimeout:(fn,ms)=>{const id=++timeoutId;timeouts.set(id,{fn,ms});return id;},clearTimeout:id=>timeouts.delete(id)},
      }).default;
      screen.mount(Conversation);await screen.settle();
      return {...screen,...chat,async second(){for(const [id,timer] of [...timeouts])if(timer.ms===1000){timeouts.delete(id);timer.fn();}await screen.settle();}};
    },
    choose(label){if(platform==='web') {
      const screen=[boundary,plus].find(screen=>screen.nodes().some(n=>n.type==='Modal'));
      assert.ok(screen,'web dialog');screen.press(label);return;
    }const alert=alerts.at(-1);assert.ok(alert,'dialog');const button=alert.buttons.find(b=>b.text===label);assert.ok(button,'dialog button '+label);button.onPress?.();},
    close(){plus.unmount();boundary.unmount();},
  };
}
async function cancelScenario(mutation) {
  const f=await fixture(mutation);f.model.status.previewEligible=true;
  const task=f.api.api.post('/api/agent/search-command',{operation:'publish',intent:{topics:['coffee']}});
  const outcome=task.then(v=>({value:v}),error=>({error}));await f.boundary.settle();
  assert.equal(f.posts.length,0);f.choose(f.PLUS.cancel());await f.boundary.settle();
  assert.equal(f.posts.length,0,'Cancel must not dispatch');assert.match((await outcome).error?.message||'',/action_cancelled/);
  assert.deepEqual(JSON.parse(f.storage.value),[]);f.close();
}
async function swapScenario(mutation) {
  const f=await fixture(mutation);
  f.model.status.searches=[{id:'paused-target',title:'Target',state:'paused',publishedAt:1},{id:'actual-blocker',title:'Blocker',state:'active',publishedAt:2}];
  f.model.reply=async p=>{
    if(!p.body.swapSearchId)return {status:409,body:{error:'search_quota',blockerIds:['actual-blocker']}};
    f.model.status.searches=f.model.status.searches.map(s=>({...s,state:s.id==='paused-target'?'active':'paused'}));
    return {body:{ok:true}};
  };
  await f.openPlus();f.plus.press(f.MONETIZATION.resumeSearch());await f.plus.settle();
  assert.equal(f.posts.length,1);f.plus.press(f.MONETIZATION.swap());f.choose(f.PLUS.cancel());await f.plus.settle();
  assert.equal(f.posts.length,1,'confirmation cancel has no mutation');
  const loads=f.model.loads;f.plus.press(f.MONETIZATION.swap());f.choose(f.MONETIZATION.continue());await f.plus.settle();
  assert.equal(f.posts.length,2);assert.equal(f.posts[1].body.searchId,'paused-target');
  assert.equal(f.posts[1].body.swapSearchId,'actual-blocker','exact quota blocker, never the target');
  assert.ok(f.model.loads>loads,'success refreshes membership/cards');
  assert.equal(f.plus.nodes().filter(n=>n.type==='Pressable' && n.props.children.some(c=>c?.props?.children?.includes(f.MONETIZATION.pause()))).length,1);
  f.close();
}
async function noticeScenario(mutation,expired=false) {
  const f=await fixture(mutation);
  f.model.status={...membership(),previewStartedAt:1000,expiresAt:1210600,previewNotice:true,
    serverTime:expired?1210700:1100,state:expired?'free':'preview',plan:expired?'free':'plus',
    limits:{activeSearches:expired?1:null,initiatedChats:expired?1:null}};
  f.model.reply=async p=>{if(p.url.endsWith('/notice'))f.model.status.previewNotice=false;return {body:{ok:true}};};
  f.actions.monetizationInteraction().changed();await f.boundary.settle();
  const expected=f.previewNoticePresentation(f.model.status);
  assert.equal(f.alerts.length,1,'real Preview notice must appear');
  assert.equal(f.alerts[0].title,expected.title);assert.equal(f.alerts[0].message,expected.message);
  assert.equal(f.posts.length,0,'notice waits for explicit ack');
  f.actions.monetizationInteraction().changed();await f.boundary.settle();assert.equal(f.alerts.length,1);
  f.choose(f.MONETIZATION.continue());await f.boundary.settle();
  assert.equal(f.posts.length,1);assert.ok(f.posts[0].url.endsWith('/notice'));
  f.actions.monetizationInteraction().changed();await f.boundary.settle();assert.equal(f.alerts.length,1);
  const staleAck=f.alerts[0].buttons[0].onPress;f.api.setSession('token-b');f.boundary.rerender();await f.boundary.settle();
  staleAck();await f.boundary.settle();assert.equal(f.posts.length,1,'A acknowledgement cannot run for B');
  f.close();
}
const originalFetch=global.fetch;
async function main(){
  await cancelScenario();console.log('PASS Boundary Preview Cancel: zero POST and cleared durable metadata');
  {
    const f=await fixture();f.model.status.previewEligible=true;
    const task=f.api.api.post('/api/agent/search-command',{operation:'publish',intent:{topics:['coffee']}});
    await f.boundary.settle();assert.equal(f.posts.length,0);f.choose(f.MONETIZATION.continue());await task;
    assert.equal(f.posts.length,1);assert.equal(f.posts[0].body.operation,'publish');f.close();
  }
  console.log('PASS Boundary Preview Continue: exactly one POST');
  await swapScenario();console.log('PASS Plus paused-search quota, cancel, exact blocker swap and refresh');
  {
    const f=await fixture();let attempts=0;
    f.model.reply=async()=>++attempts===1?{status:409,body:{error:'search_quota',blockerIds:['original-blocker']}}:{body:{ok:true}};
    const task=f.api.api.post('/api/agent/search-command',{operation:'publish',intent:{topics:['original']}});
    await f.boundary.settle();f.choose(f.PLUS.title());await f.openPlus();
    f.plus.press(f.MONETIZATION.swap());f.choose(f.MONETIZATION.continue());await f.plus.settle();await task;
    assert.equal(f.posts.length,2);assert.equal(f.posts[1].body.swapSearchId,'original-blocker');
    assert.equal(f.posts[1].body.commandId,f.posts[0].body.commandId);assert.deepEqual(f.posts[1].body.intent,{topics:['original']});f.close();
  }
  console.log('PASS actual Boundary quota -> Plus pending-action swap preserves original action/key');
  {
    const f=await fixture();let retries=0;
    f.model.status.blockerIds.chats=['session-old'];
    f.model.status.chatBlockers=[{sessionId:'session-old',peerId:'peer-old',peerName:'Old peer'}];
    const pending=f.actions.deferAction({session:'token-a',key:'chat',operation:'message',payload:{text:'original'},reason:'chat_quota'},async()=>{retries++;return {ok:true};});
    await f.openPlus();f.plus.press(f.MONETIZATION.freeSlot()+' · Old peer');f.plus.blur();
    assert.equal(f.routes.at(-1).pathname,'/conversation');
    assert.equal(f.routes.at(-1).params.who_id,'peer-old');assert.ok(f.routes.at(-1).params.recoveryId);
    assert.ok(f.actions.recoveryAction('token-a','conversation'));
    assert.equal(retries,0);assert.ok(f.actions.navigateReturnAction('token-a','conversation','plus'));
    f.actions.blurReturnAction('token-a','conversation');await f.openPlus();
    assert.equal(retries,0,'returning to Plus does not automatically dispatch');f.plus.press(f.MONETIZATION.resume());await f.plus.settle();await pending;
    assert.equal(retries,1);f.close();
  }
  console.log('PASS actual Plus free-slot and explicit return/retry preserve one pending action');
  for(const exit of ['blur','cancel','account']) {
    const f=await fixture();let retries=0;
    const result=f.actions.deferAction({session:'token-a',key:exit,operation:'message',payload:{},reason:'chat_quota'},async()=>{retries++;}).catch(e=>e);
    await f.openPlus();if(exit==='blur')f.plus.blur();else if(exit==='cancel')f.plus.press(f.MONETIZATION.cancelAction());else{f.api.setSession('other');f.actions.returnAction('other');}
    assert.match((await result).message,/action_cancelled/);assert.equal(retries,0);assert.equal(f.actions.returnAction(f.api.getSession()),null);f.close();
  }
  console.log('PASS Plus blur/cancel/account change cancel without retry');
  await noticeScenario();await noticeScenario(undefined,true);
  await assert.rejects(noticeScenario('notice'),/real Preview notice must appear/);
  console.log('PASS actual active/expired Preview notice, exact copy, explicit ack, account guard and condition mutation');
  {
    const f=await fixture();await f.openPlus();const loads=f.model.loads;
    await f.advance(60000);assert.ok(f.model.loads>loads,'focused interval refreshes');
    f.background(true);const paused=f.model.loads;await f.advance(120000);assert.equal(f.model.loads,paused,'background pauses');
    f.model.status={...membership(),state:'plus',plan:'plus',limits:{activeSearches:null,initiatedChats:null},
      entitlementSources:[{source:'manual',expiresAt:500}],plusExpiresAt:500};
    f.background(false);await f.plus.settle();assert.ok(f.plus.text().includes(f.membershipPresentation(f.model.status).status));
    f.model.status=membership();await f.advance(60000);assert.ok(f.plus.text().includes(f.membershipPresentation(f.model.status).status),'revocation appears');
    let late;f.model.statusRead=()=>new Promise(resolve=>{late=resolve;});await f.advance(60000);
    f.api.setSession('token-b');late({...membership(),state:'plus',plan:'plus',limits:{activeSearches:null,initiatedChats:null}});
    await f.plus.settle();assert.ok(!f.plus.text().includes(f.membershipPresentation({...membership(),state:'plus',plan:'plus'}).status),'late A never shows for B');
    f.plus.blur();const hidden=f.model.loads;await f.advance(60000);assert.equal(f.model.loads,hidden,'blur pauses');f.close();
  }
  console.log('PASS actual Plus focus/foreground fake clock refresh, revoke and stale account response');
  {
    const f=await fixture();f.model.status.recoverableGroups=[{gid:'legacy-exact',title:'Historical group',model:'legacy'}];
    await f.openPlus();assert.ok(f.plus.text().includes(f.MONETIZATION.legacyRecovery()));
    f.plus.press(f.MONETIZATION.recoverGroup());await f.plus.settle();
    assert.equal(f.posts.length,1);assert.ok(f.posts[0].url.endsWith('/group-recover'));assert.equal(f.posts[0].body.gid,'legacy-exact');
    assert.equal(f.routes.length,0,'legacy group never navigates to the modern room');f.close();
  }
  await assert.rejects(cancelScenario('cancel'),/Cancel must not dispatch/);
  await assert.rejects(swapScenario('swap'),/exact quota blocker/);
  console.log('PASS mutation proof: real Cancel reject->resolve and blockerId->searchId are killed');
}
module.exports={fixture,load,renderer};
if(require.main===module)main().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>{global.fetch=originalFetch;});
