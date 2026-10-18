/** Actual API/invitation/state implementations; synthetic transport and local storage. */
const assert=require('node:assert/strict');
const {load}=require('./monetization_components_test');
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const defer=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {resolve,promise};};
function fixture(disk={value:null},server={receipts:new Map(),count:0}) {
  const actions=load('src/monetization-actions.ts');
  const state={failure:null,requests:[],lose:false,readGate:null,replyGate:null,before:0};
  const api=load('src/api.ts',{
    'react-native':{Image:{prefetch:async()=>{}}},
    '@react-native-async-storage/async-storage':{
      getItem:async()=>{if(state.readGate)await state.readGate;if(state.failure==='read')throw Error('storage read');return disk.value;},
      setItem:async(_key,value)=>{if(state.failure==='write')throw Error('storage write');disk.value=value;},
    },'./i18n':{getLang:()=> 'en',replyLang:()=> 'en'},'./thinking':{whileThinking:p=>p},
    './interest-label':{registerInterestLabels(){}},'./monetization-actions':actions,
  });
  actions.configureMonetization({before:async()=>{state.before++;}});
  global.fetch=async(url,init)=>{
    let body;
    if(url.includes('/profile'))body={user:{id:init.headers.Authorization==='Bearer token-a'?'a':'b'}};
    else {
      const request={url,body:JSON.parse(init.body),auth:init.headers.Authorization};state.requests.push(request);
      const key=request.auth+':'+request.body.commandId;
      if(!server.receipts.has(key))server.receipts.set(key,{ok:true,id:'result-'+(++server.count)});
      body=server.receipts.get(key);
      if(state.replyGate)await state.replyGate;
      if(state.lose)throw Error('lost receipt');
    }
    return {ok:true,status:200,text:async()=>JSON.stringify(body)};
  };
  const invites=load('src/invites.ts',{react:{useEffect(){},useState:x=>[x,()=>{}]},'./api':api,'./candidates':{CAP:{limit:10}}});
  api.setSession('token-a');return {api,actions,state,disk,server,invites};
}

async function mapReply(){
  const f=fixture();await f.api.ensureMe();
  const peer={name:'Same',id:'b'},target={id:'intent-b',searchId:'search-b',title:'Coffee',intent:{topics:['coffee']}};
  f.state.lose=true;
  assert.equal((await f.invites.sendIntentReply('A',peer,target)).ok,false);
  assert.equal(f.state.requests.length,1);const original=f.state.requests[0].body;
  assert.ok(original.commandId);assert.equal(original.commandId,original.idem);
  assert.equal(original.to_id,'b');assert.equal(original.intent.targetIntentId,'intent-b');assert.equal(original.intent.targetSearchId,'search-b');
  assert.equal(f.server.count,1);assert.equal(f.state.before,0,'a reply is not a new search or Preview trigger');
  assert.ok(!f.disk.value.includes('Coffee'));
  const restart=fixture(f.disk,f.server);await restart.api.ensureMe();
  assert.equal((await restart.invites.sendIntentReply('A',peer,target)).ok,true);
  assert.equal(restart.state.requests[0].body.commandId,original.commandId);assert.equal(f.server.count,1);
  // A completed operation has been durably acknowledged; another explicit reply
  // is a separate command, even with identical transport fields.
  assert.equal((await restart.invites.sendIntentReply('A',peer,target)).ok,true);
  assert.notEqual(restart.state.requests[1].body.commandId,original.commandId);assert.equal(f.server.count,2);
  const guard=fixture();await guard.api.ensureMe();guard.state.failure='write';
  assert.equal((await guard.invites.sendIntentReply('A',peer,target)).ok,false);assert.equal(guard.state.requests.length,0);
  const gate=defer();guard.state.failure=null;guard.state.replyGate=gate.promise;
  const pending=guard.invites.sendIntentReply('A',peer,target);await tick();
  guard.api.setSession('token-b');gate.resolve();assert.equal((await pending).ok,false);
  assert.equal(guard.state.requests.length,1);assert.equal(guard.state.requests[0].auth,'Bearer token-a');
  console.log('PASS actual map reply -> proposal durability, lost receipt/restart, new explicit command, account guards');
}

async function protective(){
  const cases=[
    api=>api.agent.respondInvite('invite','A','decline',1),
    api=>api.group.respondInvite('ginvite','A',false,'decline-group'),
    api=>api.group.roleRespond('gid','A',false,'decline-role'),
    api=>api.api.post('/api/agent/mplan-cancel',{id:'plan',self:'A'}),
    api=>api.group.planCancel('gplan','A','cancel-group'),
  ];
  for(const failure of ['read','write','corrupt'])for(const invoke of cases){
    const f=fixture();await f.api.ensureMe();
    if(failure==='corrupt')f.disk.value='{bad';else f.state.failure=failure;
    f.state.lose=true;
    await assert.rejects(invoke(f.api),/lost receipt/);
    assert.equal(f.state.requests.length,1);const key=f.state.requests[0].body.commandId;
    assert.equal(f.state.before,0);f.state.lose=false;
    if(failure==='write')await assert.rejects(invoke(f.api),/storage write/);else await invoke(f.api);
    assert.equal(f.state.requests[1].body.commandId,key);assert.equal(f.server.count,1,'unknown command retains its key');
    f.api.setSession('token-b');
    if(failure==='write')await assert.rejects(invoke(f.api),/storage write/);else await invoke(f.api);
    assert.equal(f.state.requests.at(-1).auth,'Bearer token-b');assert.notEqual(f.state.requests.at(-1).body.commandId,key);
  }
  for(const failure of ['read','write','corrupt']){
    const f=fixture();await f.api.ensureMe();
    if(failure==='corrupt')f.disk.value='{bad';else f.state.failure=failure;
    for(const positive of [()=>f.api.agent.respondInvite('i','A','accept'),()=>f.api.group.roleRespond('g','A',true,'accept'),
      ()=>f.api.api.post('/api/agent/propose',{to_id:'b',intent:{targetIntentId:'i'}}),
      ()=>f.api.api.post('/api/agent/message',{to_id:'b',text:'private'}),
      ()=>f.api.api.post('/api/agent/search-command',{intent:{topics:['coffee']}})])await assert.rejects(positive());
    assert.equal(f.state.requests.length,0);
  }
  const f=fixture();await f.api.ensureMe();const read=defer();f.state.readGate=read.promise;f.state.failure='read';
  const pending=assert.rejects(f.api.agent.respondInvite('invite','A','decline'),/account_changed/);
  await tick();f.api.setSession('token-b');read.resolve();await pending;assert.equal(f.state.requests.length,0);
  assert.equal(f.actions.protectiveOperation('/api/agent/respond',{decision:'accept',accept:false}),false);
  assert.equal(f.actions.protectiveOperation('/api/agent/gintent-role-respond',{accept:'false'}),false);
  console.log('PASS exact negative wrappers on read/write/corrupt storage, uncertain keys/session switch; positive actions require durability');
}

async function batchLifecycle(){
  let writes=0,notifications=0;
  const state=load('src/state.ts',{
    react:{useEffect(){},useState:x=>[x,()=>{}]},'./api':{setSession(){},setMyId(){},onMyId:()=>()=>{}},
    '@react-native-async-storage/async-storage':{getItem:async()=>null,setItem:async()=>{writes++;}},
  });
  const lifecycle=load('src/chat-lifecycle.ts');
  await state.restore();state.signedIn({login:'a@test.local',session:'token-a',authMethod:'code',profile:{name:'A'},isNew:false});
  state.subscribe(()=>notifications++);
  const chats=Array.from({length:50},(_,index)=>({peerId:'peer-'+index,state:'closed',sessionId:null,blocked:false,serverTime:1}));
  writes=notifications=0;
  assert.equal(state.syncChatLifecycles(chats,'token-a'),true);assert.equal(writes,1);assert.equal(notifications,1);
  writes=notifications=0;
  state.syncChatLifecycles(chats.map(chat=>({...chat,serverTime:5})),'token-a');
  assert.equal(writes,0);assert.equal(notifications,0);assert.equal(state.msgPrefs().chats['peer-0'].serverTime,5);
  assert.equal(state.syncChatLifecycle({...chats[0],state:'active',sessionId:'stale',serverTime:4},'token-a'),false);
  assert.equal(lifecycle.canComposeChat(state.msgPrefs().chats['peer-0'],false),false);
  state.syncChatLifecycles([{...chats[0],state:'active',sessionId:'new',serverTime:6},{...chats[1],serverTime:2}],'token-a');
  assert.equal(writes,1);assert.equal(notifications,1);assert.equal(state.msgPrefs().chats['peer-1'].serverTime,5);
  const before=JSON.stringify(state.msgPrefs());
  assert.equal(state.syncChatLifecycles(chats,'token-b'),false);assert.equal(JSON.stringify(state.msgPrefs()),before);
  state.signedIn({login:'b@test.local',session:'token-b',authMethod:'code',profile:{name:'B'},isNew:false});
  writes=notifications=0;
  assert.equal(state.syncChatLifecycles(chats,'token-a'),false);assert.equal(writes,0);assert.equal(notifications,0);
  console.log('PASS 50 lifecycle rows -> one write/notification; clock-only zero writes, per-peer ordering and closed/session safety');
}
const oldFetch=global.fetch;
(async()=>{await mapReply();await protective();await batchLifecycle();})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>{global.fetch=oldFetch;});
