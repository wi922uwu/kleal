/** Real Messages component and usePolling with a deterministic AppState/clock. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),ts=require(path.join(root,'node_modules/typescript'));
function load(file,stubs={}){const m={exports:{}};const js=ts.transpileModule(fs.readFileSync(path.join(root,file),'utf8'),{compilerOptions:{module:1,target:7,jsx:ts.JsxEmit.React,esModuleInterop:true}}).outputText;
  Function('React','require','module','exports',js)(stubs.react,n=>{if(n in stubs)return stubs[n];throw Error('Unmocked '+n);},m,m.exports);return m.exports;}
let cells=[],cursor=0,effects=[],dirty=false,tree,captured,token='a-token',prefs={},routes=[],seq=0,threadRequests=[];
const same=(a,b)=>a&&b&&a.length===b.length&&a.every((v,i)=>Object.is(v,b[i]));
const React={createElement:(type,props,...children)=>({type,props:{...props,children}}),
  useState(initial){const i=cursor++;if(!(i in cells))cells[i]={value:typeof initial==='function'?initial():initial};return [cells[i].value,v=>{const next=typeof v==='function'?v(cells[i].value):v;if(!Object.is(next,cells[i].value)){cells[i].value=next;dirty=true;}}];},
  useRef(value){const i=cursor++;if(!(i in cells))cells[i]={current:value};return cells[i];},
  useMemo(fn,deps){const i=cursor++;if(!same(cells[i]?.deps,deps))cells[i]={value:fn(),deps};return cells[i].value;},
  useCallback(fn,deps){return React.useMemo(()=>fn,deps);},
  useEffect(fn,deps){const i=cursor++;if(!same(cells[i]?.deps,deps)){const prev=cells[i];cells[i]={deps};effects.push(()=>{prev?.cleanup?.();cells[i].cleanup=fn();});}},
};
const timers=new Map(),listeners=new Set();let now=0;
const originalInterval=global.setInterval,originalClear=global.clearInterval;
global.setInterval=(fn,ms)=>{const id=++seq;timers.set(id,{fn,ms,at:now+ms});return id;};global.clearInterval=id=>timers.delete(id);
const AppState={currentState:'active',addEventListener:(_e,fn)=>{listeners.add(fn);return {remove:()=>listeners.delete(fn)};}};
const change=s=>{AppState.currentState=s;listeners.forEach(fn=>fn(s));};
const advance=ms=>{now+=ms;for(const t of timers.values())if(t.at<=now){t.at=now+t.ms;t.fn();}};
const router={useFocusEffect:fn=>React.useEffect(fn,[fn]),useRouter:()=>({navigate:to=>routes.push(to),dismissTo:to=>routes.push(to)})};
const polling=load('src/polling.ts',{react:React,'react-native':{AppState},'expo-router':router});
const i18n={T:(...v)=>v[1],getLang:()=> 'en',useLang:()=> 'en',dateLocale:()=> 'en',use12h:()=>false};
const actions=load('src/monetization-actions.ts');
const api={getSession:()=>token,isMe:(_name,id)=>id==='a',pidOf:(r,f)=>r[f+'_id'],mediaUrl:x=>x,
  agent:{plans:async()=>({plans:[],history:[]}),inbox:async()=>({requests:[]}),outbox:async()=>({requests:[{id:'pair',from:'A',from_id:'a',to:'B',to_id:'b',status:'accepted'}]}),
    threads:()=>new Promise(resolve=>threadRequests.push(resolve)),safety:async()=>({blocked:[]})},
  group:{mine:async()=>({groups:[]}),plans:async()=>({plans:[],history:[]})}};
const messages=load('src/messages.ts',{'./i18n':i18n,'./api':api,'./chat':{klealText:()=>''}});
const batches=[];
const state={useOnb:()=>({session:'a-token',profile:{name:'A'},msg:prefs}),setMsgPrefs:fn=>{prefs=fn(prefs);dirty=true;},syncChatLifecycles:(chats,_session,_delivered,fn)=>{batches.push(chats);prefs=fn(prefs);dirty=true;return true;}};
const native={...Object.fromEntries(['View','Text','ScrollView','Pressable','TextInput','Image','ActivityIndicator'].map(x=>[x,x])),StyleSheet:{create:x=>x}};
const Screen=load('app/messages.tsx',{react:React,'react-native':native,'react-native-safe-area-context':{useSafeAreaInsets:()=>({top:0,bottom:0})},'expo-router':router,
  '../src/messages':{...messages,inboxRows:arg=>{captured=arg;return messages.inboxRows(arg);}},'../src/api':api,
  '../src/chat':{CHAT:{},planWhen:()=>'',sysLine:()=>''},'../src/groups':{groupSysLine:()=>''},'../src/i18n':i18n,'../src/state':state,
  '../src/components/icons':new Proxy({},{get:(_o,k)=>k}),'../src/components/BottomNav':{BottomNav:'BottomNav'},
  '../src/components/Sheet':{Sheet:'Sheet',SheetItem:'SheetItem'},'../src/chat-lifecycle':load('src/chat-lifecycle.ts'),
  '../src/polling':polling,'../src/theme':load('src/theme.ts'),'../src/components/LiquidGlass':{GlassBack:'GlassBack',GlassSurface:'GlassSurface'},
  '../src/components/Ambient':{Ambient:'Ambient',GLOW_FORM:{}},'../src/navScroll':{useNavCollapse:()=>({})},'../src/monetization-actions':actions,
  '../src/monetization':{MONETIZATION:{returnToAction:()=> 'return-to-action'}}}).default().type;
function render(){cursor=0;effects=[];dirty=false;tree=Screen();effects.forEach(fn=>fn());}
async function settle(){for(let i=0;i<16;i++){await Promise.resolve();if(dirty)render();}}
const reply=(text,count=1)=>({threads:Array.from({length:count},(_,index)=>({who:'B',who_id:index?'b'+index:'b',last:text,t:now,
  chat:{peerId:index?'b'+index:'b',state:'active',sessionId:'s'+index,serverTime:now,blocked:false}}))});
const nodes=(v=tree)=>Array.isArray(v)?v.flatMap(nodes):v&&typeof v==='object'?[v,...nodes(v.props?.children)]:[];
const text=v=>Array.isArray(v)?v.map(text).join(' '):v&&typeof v==='object'?text(v.props?.children):String(v||'');
function press(label){const n=nodes().find(n=>n.type==='Pressable'&&text(n.props.children)===label);assert.ok(n,'button '+label);n.props.onPress();}
(async()=>{
  let retried=0;const original=actions.deferAction({session:token,key:'original',operation:'message',payload:{text:'original'},reason:'chat_quota'},async()=>{retried++;return {};});
  actions.navigateReturnAction(token,'plus','messages');actions.blurReturnAction(token,'plus');
  render();await settle();assert.equal(threadRequests.length,1);
  advance(15001);await settle();assert.equal(threadRequests.length,2);
  advance(15001);await settle();assert.equal(threadRequests.length,3);
  threadRequests[0](reply('first slow response',50));await settle();
  assert.equal(batches.length,1);assert.equal(batches[0].length,50,'one actual poll submits one batch of 50 validated lifecycles');
  assert.equal(captured.threads[0].last,'first slow response','slow list response is not starved by newer STARTS');
  threadRequests[2](reply('latest applied'));await settle();threadRequests[1](reply('late older'));await settle();
  assert.equal(captured.threads[0].last,'latest applied','older completion cannot replace applied list');
  change('background');assert.equal(timers.size,0);advance(60000);await settle();assert.equal(threadRequests.length,3);
  change('active');await settle();assert.equal(threadRequests.length,4,'foreground immediately refreshes');
  threadRequests[3](reply('foreground'));await settle();assert.equal(captured.threads[0].last,'foreground');
  const recoveryId=actions.returnActionRoute(token,'plus').params.recoveryId;
  nodes().find(n=>n.type==='Pressable'&&n.props.key==='private').props.onPress();await settle();
  const row=nodes().find(n=>n.type==='Pressable'&&typeof n.props.onLongPress==='function');assert.ok(row,'private peer row');
  row.props.onPress();assert.equal(routes.at(-1).pathname,'/conversation');
  assert.equal(routes.at(-1).params.who_id,'b');assert.equal(routes.at(-1).params.recoveryId,recoveryId);
  assert.equal(retried,0);actions.blurReturnAction(token,'messages');
  // Return to the list in the same explicit recovery, then exercise its own return callback.
  actions.navigateReturnAction(token,'conversation','messages');actions.blurReturnAction(token,'conversation');render();await settle();
  press('return-to-action');assert.equal(routes.at(-1).pathname,'/plus');assert.ok(routes.at(-1).params.recoveryId);assert.equal(retried,0);
  cells.forEach(c=>c.cleanup?.());assert.ok(actions.recoveryAction(token,'plus'));await actions.resumeReturnAction(token);await original;assert.equal(retried,1);
  assert.equal(timers.size,0);assert.equal(listeners.size,0);
  // A keyed account remount invalidates old component callbacks.
  cells=[];render();await settle();assert.equal(threadRequests.length,5);
  token='other-account';threadRequests[4](reply('foreign'));await settle();
  assert.ok(!captured.threads.some(r=>r.last==='foreign'));
  token='a-token';advance(15001);await settle();assert.equal(threadRequests.length,6);
  cells.forEach(c=>c.cleanup?.());threadRequests[5](reply('unmounted'));await settle();
  assert.ok(!captured.threads.some(r=>r.last==='unmounted'));
  console.log('PASS real Messages/usePolling: >15s overlap, latest-applied ordering, background/foreground, stale account/unmount, explicit recovery return');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>{global.setInterval=originalInterval;global.clearInterval=originalClear;});
