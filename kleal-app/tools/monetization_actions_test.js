const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), Module = require('node:module');
const root = path.resolve(__dirname,'..');
const ts = require(path.join(root,'node_modules/typescript'));
function load(name,stubs={}) {
  const file=path.join(root,'src',name+'.ts'), m=new Module(file,module);
  m.filename=file; m.require=q=>stubs[q] || require(q);
  m._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,file);
  return m.exports;
}
const m=load('monetization-actions');
const billing=load('monetization',{'./i18n':{T:(...v)=>v[0],dateLocale:()=> 'en-GB'}});
let owner='a',seq=0;
const actions=new m.PendingActions(()=>owner,()=>`id-${++seq}`);
(async()=>{
  assert.equal(m.fingerprint('abc'),'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
  assert.equal(m.fingerprint(''),'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855');
  let disk=null,account='account-a',token='bearer-never-persist',writes=0;
  const persistence={account:async()=>account,read:async()=>disk,write:async raw=>{disk=raw;writes++;}};
  const first=new m.PendingActions(()=>token,()=>`durable-${++seq}`,persistence);
  const payload={text:'private message never persist',to_id:'b'};
  const durable=await first.durable('message',payload);
  await first.patch(durable,{swapSearchId:'search-safe-ref'});
  assert.ok(writes>0);
  assert.ok(!disk.includes(token)); assert.ok(!disk.includes(payload.text)); assert.ok(!disk.includes('preview'));
  // Simulate process death: there is no surviving JS action/promise, only metadata.
  const restarted=new m.PendingActions(()=>token,()=>`durable-${++seq}`,persistence);
  const retry=await restarted.durable('message',payload);
  assert.equal(retry.key,durable.key);assert.equal(retry.patch.swapSearchId,'search-safe-ref');
  assert.notEqual((await restarted.durable('message',{...payload,text:'different'})).key,retry.key);
  account='account-b';token='other-bearer';
  assert.notEqual((await restarted.durable('message',payload)).key,retry.key);
  account='account-a';token='bearer-new-session';
  const cancelled=await restarted.durable('message',payload);cancelled.cancel();
  // Flush serialized storage write; explicit cancellation cannot be revived.
  await restarted.patch(cancelled,{});
  const afterCancel=new m.PendingActions(()=>token,()=>`durable-${++seq}`,persistence);
  assert.notEqual((await afterCancel.durable('message',payload)).key,retry.key);
  const one=actions.begin('publish',{intent:{topics:['coffee']},idem:'random1'});
  assert.equal(one,actions.begin('publish',{intent:{topics:['coffee']},idem:'random2'}));
  assert.notEqual(one,actions.begin('publish',{intent:{topics:['padel']}}));
  owner='b'; assert.equal(actions.current(one),false);
  const other=actions.begin('publish',{intent:{topics:['coffee']}});
  assert.notEqual(one.key,other.key);
  assert.equal(await actions.finish(one),false);
  assert.equal(await actions.finish(other),true);
  assert.notEqual(actions.begin('publish',{intent:{topics:['coffee']}}).key,other.key);
  const video=actions.begin('message',{client_id:'media-retry',video:{id:'v'}});
  assert.equal(video.key,'media-retry');
  let resumed=0;
  const awaiting=m.deferAction(video,async()=>{resumed++;return {ok:true};});
  assert.equal(m.returnAction('b').key,'media-retry');
  await m.resumeReturnAction('b'); assert.equal((await awaiting).ok,true); assert.equal(resumed,1);
  const obsolete=m.deferAction(video,async()=>{resumed++;});
  const rejected=assert.rejects(obsolete,/action_cancelled/);
  assert.equal(m.returnAction('new-account'),null); await rejected;
  await m.resumeReturnAction('new-account'); assert.equal(resumed,1);
  let release;
  const wait=new Promise(resolve=>{release=resolve;});
  const duplicate=m.deferAction(video,async()=>{resumed++;await wait;return {ok:true};});
  const r1=m.resumeReturnAction('b'),r2=m.resumeReturnAction('b');
  release();await Promise.all([r1,r2,duplicate]);assert.equal(resumed,2);
  const blur=m.deferAction(video,async()=>{});
  const blurred=assert.rejects(blur,/action_cancelled/);m.cancelReturnAction();await blurred;
  const ctrl=new AbortController();let aborted=0;
  const waiting=m.abortableAction(new Promise(()=>{}),ctrl.signal,()=>aborted++);
  const abortedWait=assert.rejects(waiting,/action_cancelled/);ctrl.abort();await abortedWait;assert.equal(aborted,1);
  const plus=fs.readFileSync(path.join(root,'app/plus.tsx'),'utf8');
  assert.match(plus,/useFocusEffect\(useCallback\(\(\)=>\(\)=>\{dialog\.dismiss\(\);blurReturnAction/);
  const v2={ok:true,version:2,phase:'phase2a',state:'preview',plan:'plus',serverTime:1000,
    previewStartedAt:1000,expiresAt:1210600,previewEligible:false,previewNotice:true,
    enforcementEnabled:true,purchaseAvailable:false,restoreAvailable:false,
    permissions:{publishSearch:true,initiateChat:true,reply:true,groupChat:true,manualCoordination:true,basicFilters:true},
    usage:{activeSearches:2,initiatedChats:2},limits:{activeSearches:null,initiatedChats:null},
    reasons:{publishSearch:null,initiateChat:null},blockerIds:{searches:['s1'],chats:[]},searches:[],keepSearchId:null};
  assert.equal(billing.isMembership(v2),true);
  for (const bad of [{...v2,expiresAt:1210601},{...v2,serverTime:NaN},{...v2,permissions:{}},
    {...v2,purchaseAvailable:true},{...v2,limits:{}},{...v2,reasons:{}},
    {...v2,usage:{activeSearches:-1,initiatedChats:0}}])
    assert.equal(billing.isMembership(bad),false);
  for(const p of ['/api/agent/message','/api/agent/search-command','/api/agent/gintent-role-respond'])
    assert.equal(m.gatedOperation(p,{}),true);
  assert.equal(m.gatedOperation('/api/agent/thread',{}),false);
  // Execute the production API wrapper, not just the metadata class.
  let apiDisk=null,requests=[],failReply=false,releaseReply=null,quotaReply=false;
  const sideEffects=new Set();
  const apiStubs={
    'react-native':{Image:{prefetch:async()=>{}}},
    '@react-native-async-storage/async-storage':{getItem:async()=>apiDisk,setItem:async(_key,value)=>{apiDisk=value;}},
    './i18n':{getLang:()=> 'en',replyLang:()=> 'en'},
    './interest-label':{registerInterestLabels:()=>{}},'./monetization-actions':m,
    './thinking': { whileThinking: promise => promise },
  };
  global.fetch=async(url,options)=>{
    let value;
    if(url.includes('/api/onboarding/profile')) value={user:{id:'synthetic-account'}};
    else {
      requests.push(JSON.parse(options.body));
      if(!quotaReply)sideEffects.add(requests.at(-1).commandId);
      if(releaseReply) await releaseReply;
      if(failReply) throw new Error('synthetic lost response');
      value=quotaReply ? {ok:false,error:'search_quota',blockerIds:['search-existing']} : {ok:true};
    }
    const quota=value.error==='search_quota';
    return {ok:!quota,status:quota?409:200,headers:{get:()=> 'application/json'},json:async()=>value,text:async()=>JSON.stringify(value)};
  };
  let production=load('api',apiStubs);production.setSession('synthetic-token');await production.ensureMe();
  let releaseNetwork;releaseReply=new Promise(resolve=>{releaseNetwork=resolve;});
  const send1=production.api.post('/api/agent/message',{to_id:'b',text:'duplicate'});
  const send2=production.api.post('/api/agent/message',{to_id:'b',text:'duplicate'});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(requests.length,1);releaseNetwork();await Promise.all([send1,send2]);releaseReply=null;
  failReply=true;
  await assert.rejects(production.api.post('/api/agent/message',{to_id:'b',text:'lost response'}));
  const originalKey=requests.at(-1).commandId;
  for(let i=0;i<125;i++)await assert.rejects(production.api.post('/api/agent/message',{to_id:'b',text:'unknown '+i}));
  const beforeReplay=sideEffects.size;
  const actualNow=Date.now;
  Date.now=()=>actualNow()+8*86400000;
  production=load('api',apiStubs);production.setSession('synthetic-token');
  failReply=false;
  await production.api.post('/api/agent/message',{to_id:'b',text:'lost response'});
  Date.now=actualNow;
  assert.equal(requests.at(-1).commandId,originalKey);
  assert.equal(sideEffects.size,beforeReplay,'8 days + 125 unresolved commands + restart never execute the original twice');
  assert.ok(!apiDisk.includes('synthetic-token'));assert.ok(!apiDisk.includes('lost response'));
  // A command originated on Plus must reject inline, not defer navigation to
  // the screen that is already awaiting it. It still uses the normal wire gate.
  let blockedCalls=0;
  m.configureMonetization({blocked:async()=>{blockedCalls++;throw new Error('must not navigate');}});
  quotaReply=true;
  await assert.rejects(production.api.post('/api/agent/search-command',
    {operation:'resume',searchId:'search-paused'},undefined,{quotaPresentation:'inline'}),
    error=>error.body.error==='search_quota');
  assert.equal(blockedCalls,0);assert.equal(m.returnAction('synthetic-token'),null);
  assert.ok(requests.at(-1).commandId);assert.equal(requests.at(-1).quotaPresentation,undefined);
  quotaReply=false;
  await production.api.post('/api/agent/search-command',
    {operation:'resume',searchId:'search-paused',swapSearchId:'search-existing'},undefined,{quotaPresentation:'inline'});
  assert.equal(requests.at(-1).swapSearchId,'search-existing');
  m.configureMonetization({});
  console.log('PASS session, operation retries, media cid, return action, v2 validation, shared gate');
})().catch(e=>{console.error(e);process.exitCode=1;});
