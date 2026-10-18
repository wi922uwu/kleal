/** Real API wrapper + durable storage, synthetic server receipts/session state. */
const assert=require('node:assert/strict');
const {load}=require('./monetization_components_test');
const tick=()=>new Promise(r=>setImmediate(r));
const defer=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {resolve,promise};};
function fixture(disk={value:null},server={receipts:new Map(),publications:0,ends:0,session:'session-one',active:true}){
  const actions=load('src/monetization-actions.ts');
  const state={failure:null,requests:[],finishFailure:false,cleanupFailure:false,reply:null};
  const api=load('src/api.ts',{
    'react-native':{Image:{prefetch:async()=>{}}},
    '@react-native-async-storage/async-storage':{
      getItem:async()=>{if(state.failure==='read')throw Error('read');return disk.value;},
      setItem:async(_key,value)=>{
        if(state.failure==='write'||state.finishFailure&&JSON.parse(value).some(row=>row.acknowledged))throw Error('finish write');
        if(state.cleanupFailure&&JSON.parse(disk.value||'[]').some(row=>row.acknowledged)&&!JSON.parse(value).some(row=>row.acknowledged))throw Error('cleanup write');
        disk.value=value;
      },
    },'./i18n':{getLang:()=> 'en',replyLang:()=> 'en'},'./thinking':{whileThinking:p=>p},
    './interest-label':{registerInterestLabels(){}},'./monetization-actions':actions,
  });
  global.fetch=async(url,init)=>{
    let body;
    if(url.includes('/profile'))body={user:{id:init.headers.Authorization==='Bearer token-a'?'a':'b'}};
    else {
      const request={url,body:JSON.parse(init.body),auth:init.headers.Authorization};state.requests.push(request);
      const key=request.auth+':'+request.body.commandId;
      if(!server.receipts.has(key)){
        if(url.endsWith('/thread-end')){
          if(request.body.sessionId&&request.body.sessionId!==server.session)body={ok:false,error:'chat_session_changed'};
          else{server.active=false;server.ends++;body={ok:true,session:server.session};}
        } else {server.publications++;body={ok:true,id:'publication-'+server.publications};}
        server.receipts.set(key,body);
      }
      body=server.receipts.get(key);
      if(state.reply)await state.reply;
    }
    return {ok:true,status:200,text:async()=>JSON.stringify(body)};
  };
  api.setSession('token-a');return {api,actions,state,disk,server};
}
async function acknowledgement(){
  const one=fixture();await one.api.ensureMe();one.state.finishFailure=true;
  const payload={intent:{topics:['coffee']}};
  await assert.rejects(one.api.api.post('/api/agent/search-command',payload),/finish write/);
  const key=one.state.requests[0].body.commandId;
  assert.equal(one.server.publications,1);assert.ok(!JSON.parse(one.disk.value)[0].acknowledged);
  const restart=fixture(one.disk,one.server);await restart.api.ensureMe();
  restart.state.cleanupFailure=true;
  assert.equal((await restart.api.api.post('/api/agent/search-command',payload)).id,'publication-1');
  assert.equal(restart.state.requests[0].body.commandId,key);assert.equal(one.server.publications,1);
  assert.ok(JSON.parse(one.disk.value).some(row=>row.acknowledged),'completion persisted before success');
  // A death after acknowledgement but before metadata compaction is safe.
  const afterAck=fixture(one.disk,one.server);await afterAck.api.ensureMe();
  assert.equal((await afterAck.api.api.post('/api/agent/search-command',payload)).id,'publication-2');
  assert.notEqual(afterAck.state.requests[0].body.commandId,key);assert.equal(one.server.publications,2);
  const end=fixture();await end.api.ensureMe();end.state.finishFailure=true;
  await assert.rejects(end.api.agent.threadEnd('A',{id:'b',name:'B'},'screen-one',end.server.session),/finish write/);
  const oldKey=end.state.requests[0].body.commandId;assert.equal(end.server.ends,1);assert.equal(end.server.active,false);
  // The canonical session changes after reopen. New end is not an acknowledgement
  // of the old lifecycle, even though self/peer/name are identical.
  end.server.session='session-two';end.server.active=true;
  const reopened=fixture(end.disk,end.server);await reopened.api.ensureMe();
  await reopened.api.agent.threadEnd('A',{id:'b',name:'B'},'screen-two',reopened.server.session);
  assert.equal(end.server.ends,2);assert.equal(end.server.active,false);
  assert.notEqual(reopened.state.requests[0].body.commandId,oldKey);
  console.log('PASS durable acknowledgement failures/restart/new identical publication/new canonical chat lifecycle');
}
async function protective(){
  for(const failure of ['read','write','corrupt']){
    const f=fixture();await f.api.ensureMe();
    if(failure==='corrupt')f.disk.value='{bad';else f.state.failure=failure;
    const pause=defer();f.state.reply=pause.promise;
    const ctrl=new AbortController();
    const pending=f.api.api.post('/api/agent/thread-end',{with_id:'b',sessionId:f.server.session},ctrl.signal);
    const cancelled=assert.rejects(pending,/action_cancelled/);
    await tick();assert.equal(f.state.requests.length,1);const key=f.state.requests[0].body.commandId;
    ctrl.abort();await cancelled;pause.resolve();await tick();f.state.reply=null;
    // Even if storage is still failing, the protective request reaches the server
    // with its known uncertain key. Completion may itself require a later retry.
    const repeat=f.api.api.post('/api/agent/thread-end',{with_id:'b',sessionId:f.server.session});
    if(failure==='write')await assert.rejects(repeat,/finish write/);else await repeat;
    assert.equal(f.state.requests[1].body.commandId,key);assert.equal(f.server.ends,1);
    for(const route of ['message','search-command']){
      const count=f.state.requests.length;
      await assert.rejects(f.api.api.post('/api/agent/'+route,{to_id:'b',text:'private',intent:{topics:['coffee']}}));
      assert.equal(f.state.requests.length,count,'ordinary writes require durability');
    }
    const noSend=new AbortController();noSend.abort();const before=f.state.requests.length;
    await assert.rejects(f.api.api.post('/api/agent/thread-end',{with_id:'b'},noSend.signal),/action_cancelled/);
    assert.equal(f.state.requests.length,before);
    f.api.setSession('token-b');
    const switched=f.api.api.post('/api/agent/thread-end',{with_id:'a',sessionId:f.server.session});
    if(failure==='write')await assert.rejects(switched,/finish write/);else await switched;
    assert.equal(f.state.requests.at(-1).auth,'Bearer token-b');assert.notEqual(f.state.requests.at(-1).body.commandId,key);
  }
  console.log('PASS protective end on read/write/corrupt storage, cancel/retry/account guards; publications/messages stay durable');
}
const oldFetch=global.fetch;
(async()=>{await acknowledgement();await protective();})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>{global.fetch=oldFetch;});
