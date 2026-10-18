/** Real Expo 57 stack reducer + real Boundary/Plus/Conversation/API callbacks. No native claim. */
const assert=require('node:assert/strict');
const {createStack}=require('./expo_stack_harness');
const {fixture,load}=require('./monetization_components_test');
const actions=load('src/monetization-actions.ts');
const originalFetch=global.fetch;
function routeScenario(legacy=false) {
  const stack=createStack(actions.recoveryScreenIdentity,legacy);
  stack.navigate('/plus'); // an older ordinary Plus must not be moved through the native stack
  stack.navigate({pathname:'/conversation',params:{who:'QA A',who_id:'peer-a',title:'Original'}});
  const origin=stack.current, prefix=stack.state.routes.slice();
  const plus={pathname:'/plus',params:{recoveryId:'recovery-1'}};
  stack.navigate(plus);const plusKey=stack.current.key;
  stack.navigate({pathname:'/conversation',params:{who:'QA C',who_id:'peer-c',recoveryId:'recovery-1'}});
  assert.equal(stack.state.routes.find(r=>r.key===origin.key)?.params.who_id,'peer-a','recovery must retain the original conversation and its draft');
  assert.deepEqual(stack.state.routes.slice(0,prefix.length),prefix,'entering recovery never reorders/reparams an old native screen');
  stack.dismissTo(plus);assert.equal(stack.current.key,plusKey);
  assert.deepEqual(stack.state.routes.slice(0,-1),prefix,'return pops C; it never moves Plus above C');
  stack.dismissTo({pathname:'/conversation',params:origin.params});
  assert.equal(stack.current.key,origin.key);assert.deepEqual(stack.current.params,origin.params);
  for(let i=0;i<20;i++) {
    stack.navigate('/plan');stack.navigate({pathname:'/conversation',params:{who:'QA A',who_id:'peer-a'}});
    stack.navigate('/settings/index');stack.navigate('/profile/index');
  }
  for(const name of ['conversation','plus','plan','settings/index','profile/index'])
    assert.ok(stack.state.routes.filter(r=>r.name===name).length<=1,'ordinary screens remain singular: '+name);
}
async function scenario(exit) {
  const f=await fixture(undefined,true);
  const originParams={who:'QA A',who_id:'peer-a',title:'Original',photo:'original-photo'};
  f.stack.navigate('/plus');f.stack.navigate({pathname:'/conversation',params:originParams});
  const originKey=f.stack.current.key;
  let clock=100,active=true,attempts=0;const delivered=new Map();
  f.model.status.usage.initiatedChats=1;
  f.model.status.blockerIds.chats=['session-c'];
  f.model.status.chatBlockers=[{sessionId:'session-c',peerId:'peer-c',peerName:'QA C'}];
  f.model.read=async url=>{
    const u=new URL(url);
    if(u.pathname==='/api/agent/thread') {
      const peer=u.searchParams.get('with_id');
      return {chat:{peerId:peer,state:peer==='peer-c'?(active?'active':'closed'):(delivered.size?'active':'new'),
        sessionId:peer==='peer-c'?(active?'session-c':null):(delivered.size?'session-a':null),blocked:false,serverTime:++clock},messages:[]};
    }
    if(u.pathname==='/api/agent/mplans')return {plans:[],history:[]};
    if(['/api/agent/inbox','/api/agent/outbox'].includes(u.pathname))return {requests:[]};
  };
  f.model.reply=async p=>{
    if(p.url.endsWith('/thread-end')) {
      assert.equal(p.body.with_id,'peer-c');active=false;
      f.model.status.usage.initiatedChats=0;f.model.status.blockerIds.chats=[];f.model.status.chatBlockers=[];
    }
    if(p.url.endsWith('/message')) {
      attempts++;assert.equal(p.body.to_id,'peer-a','never send the pending message to blocker C');
      if(active)return {status:409,body:{error:'chat_quota',blockerIds:['session-c']}};
      delivered.set(p.body.commandId,p.body);return {body:{ok:true,id:'delivered',t:100}};
    }
    return {body:{ok:true}};
  };
  const origin=await f.conversation(originParams);
  const input=()=>origin.nodes().find(n=>n.type==='TextInput');
  input().props.onChangeText('Original pending message');await origin.settle();
  origin.nodes().find(n=>n.type==='SendArrow').props.onPress();await origin.settle();await f.boundary.settle();
  assert.equal(attempts,1);const commandKey=f.posts.find(p=>p.url.endsWith('/message')).body.commandId;
  // Local unsent editor state, alongside the pending bubble, must survive the round trip.
  input().props.onChangeText('Next draft remains local');await origin.settle();
  f.choose(f.PLUS.title());origin.blur();await f.openPlus();
  const plusKey=f.stack.current.key;
  assert.ok(f.actions.returnAction('token-a'));assert.equal(delivered.size,0);
  f.plus.press(f.MONETIZATION.freeSlot()+' · QA C');f.plus.blur();
  assert.equal(f.stack.state.routes.find(r=>r.key===originKey).params.who_id,'peer-a');
  const blocker=await f.conversation(f.stack.current.params);
  assert.equal(f.stack.current.params.who_id,'peer-c');
  if(exit) {
    if(exit==='back'||exit==='gesture') f.stack.back();
    if(exit==='tab') f.stack.navigate('/home');
    if(exit==='account'){f.api.setSession('token-b');f.actions.returnAction('token-b');}
    blocker.blur();await origin.settle();
    assert.equal(f.actions.returnAction(f.api.getSession()),null);assert.equal(delivered.size,0);assert.equal(attempts,1);
  } else {
    blocker.press(blocker.CHATMENU.endChat());await blocker.settle();
    for(let i=0;i<4;i++)await blocker.second();
    assert.equal(active,false);assert.equal(attempts,1,'end does not send pending message');
    const before=f.model.loads;
    blocker.press(f.MONETIZATION.returnToAction());blocker.blur();blocker.unmount();
    assert.equal(f.stack.current.key,plusKey,'POP_TO focuses the same Plus instance');
    assert.equal(f.stack.history.at(-1).type,'POP_TO','return must pop, never move a native screen above C');
    assert.ok(!f.stack.state.routes.some(r=>r.params?.who_id==='peer-c'));
    await f.openPlus();assert.ok(f.model.loads>before,'refocus immediately refreshes freed slot');
    assert.ok(!f.plus.text().includes(f.MONETIZATION.freeSlot()+' · QA C'),'stale blocker removed on focus');
    assert.equal(delivered.size,0,'return waits for explicit Continue');
    f.plus.press(f.MONETIZATION.resume());f.plus.press(f.MONETIZATION.resume());await f.plus.settle();
    assert.equal(f.stack.current.key,originKey);assert.deepEqual(f.stack.current.params,originParams);
    assert.equal(f.stack.history.at(-1).type,'POP_TO','Continue targets captured origin, not a blind back');
    f.plus.blur();origin.focus();await origin.settle();
    assert.equal(input().props.value,'Next draft remains local');
    const message=origin.nodes().find(n=>n.type==='MessageFeed').props.msgs.find(m=>m.text==='Original pending message');
    assert.equal(message.id,'delivered');assert.equal(message.state,undefined);
    assert.equal(attempts,2);assert.equal(delivered.size,1);
    assert.equal([...delivered.values()][0].commandId,commandKey);assert.equal([...delivered.values()][0].text,'Original pending message');
    assert.deepEqual(JSON.parse(f.storage.value),[],'resolved metadata retired');
  }
  blocker.unmount();origin.unmount();f.close();
}
async function cancelledCycles() {
  const stack=createStack(actions.recoveryScreenIdentity),base={who:'QA A',who_id:'peer-a'};
  stack.navigate({pathname:'/conversation',params:base});const originKey=stack.current.key;
  let retries=0;const retiredIds=new Set();
  for(let i=0;i<20;i++) {
    stack.navigate({pathname:'/conversation',params:base});
    const before=stack.state.routes.slice(),focused=stack.current;
    const origin=actions.captureReturnOrigin(stack.navigation);
    assert.equal(stack.current.key,focused.key,'pruning never changes the current route');
    assert.deepEqual(stack.state.routes,before.filter(r=>!retiredIds.has(r.params?.recoveryId)),
      'pruning removes exactly retired overlays, retaining every ordinary key/params in the same order');
    assert.equal(stack.current.key,originKey);assert.deepEqual(origin.params,base);
    const pending=actions.deferAction({session:'token-a',key:'cancel-'+i,operation:'message',payload:{to_id:'peer-a',text:'original'}},async()=>{retries++;},origin).catch(e=>e);
    const plusRoute=actions.returnActionRoute('token-a','plus');stack.navigate(plusRoute);
    actions.navigateReturnAction('token-a','plus','conversation');stack.navigate({...actions.returnActionRoute('token-a','conversation'),params:{...actions.returnActionRoute('token-a','conversation').params,who_id:'peer-c'}});
    actions.blurReturnAction('token-a','plus');
    assert.equal(stack.state.routes.filter(r=>r.params?.recoveryId).length,2,'only the active recovery pair remains');
    // Three legitimate ordinary routes after visiting both home and messages, plus two recovery overlays.
    assert.ok(stack.state.routes.length<=5,'repeated canceled recoveries are bounded');
    const selected=i%2?'/messages':'/home';stack.navigate(selected);const selectedKey=stack.current.key;
    actions.blurReturnAction('token-a','conversation');assert.match((await pending).message,/action_cancelled/);
    retiredIds.add(plusRoute.params.recoveryId);
    assert.equal(stack.current.name,selected.slice(1));assert.equal(stack.current.key,selectedKey,'cancel stays on the chosen tab');
    assert.equal(retries,0);assert.equal(actions.returnAction('token-a'),null);
  }
}
(async()=>{
  routeScenario();assert.throws(()=>routeScenario(true),/original conversation/,'old singular configuration is killed');
  console.log('PASS installed Expo Router stack: exact origin retained, recovery uses pop, ordinary routes bounded; legacy mutation killed');
  await cancelledCycles();console.log('PASS 20 tab-away/re-entry cycles: cancellation stays on selected tab; only retired overlays removed, no retained-key reorder or automatic retry');
  await scenario();console.log('PASS actual A -> Plus -> C -> end -> same Plus refreshed -> Continue -> same A: draft/key retained, one original delivery');
  for(const exit of ['back','gesture','tab','account'])await scenario(exit);
  console.log('PASS recovery Back/gesture-equivalent pop/tab/account cancel, no delivery (not physical native gestures)');
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>{global.fetch=originalFetch;});
