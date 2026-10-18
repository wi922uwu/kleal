/** Четвёртый review: реальные API callbacks и экран Plus, без native PASS. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),ts=require('typescript');
const {fixture,load}=require('./monetization_components_test');
const defer=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {resolve,promise};};
const outcome=p=>p.then(value=>({value}),error=>({error}));
async function bounded(p){let timer;try{return await Promise.race([p,new Promise((_r,reject)=>timer=setTimeout(()=>reject(Error('unsettled caller')),1000))]);}finally{clearTimeout(timer);}}
async function subscribers(){
  for(const cancel of ['second','first','already']){
    const f=await fixture(),reply=defer();f.model.reply=()=>reply.promise;
    const firstSignal=new AbortController(),secondSignal=new AbortController();
    const body={intent:{topics:['coffee']}};
    const first=outcome(f.api.api.post('/api/agent/search-command',body,firstSignal.signal));
    await f.boundary.settle();assert.equal(f.posts.length,1);
    const key=f.posts[0].body.commandId;
    if(cancel==='already')secondSignal.abort();
    const second=outcome(f.api.api.post('/api/agent/search-command',body,secondSignal.signal));
    await f.boundary.settle();
    (cancel==='first'?firstSignal:secondSignal).abort();
    assert.equal((await bounded(cancel==='first'?first:second)).error.message,'action_cancelled');
    assert.equal(JSON.parse(f.storage.value)[0].key,key,'other caller retains durable identity');
    reply.resolve({body:{ok:true,receipt:key}});
    assert.equal((await bounded(cancel==='first'?second:first)).value.receipt,key);
    assert.equal(f.posts.length,1,'dedup performs one POST');f.close();
  }
  console.log('PASS each deduplicated caller observes its own abort; remaining caller gets one committed receipt');
}
async function decline(){
  const f=await fixture(undefined,false,'web');f.model.status.previewEligible=true;
  const loads=f.model.loads;f.model.statusRead=()=>{throw Error('membership unavailable');};
  await f.api.agent.respondInvite('invite','Me','decline');await f.boundary.settle();
  assert.equal(f.posts.length,1);assert.equal(f.posts[0].body.decision,'decline');
  assert.equal(f.model.loads,loads);assert.equal(f.boundary.nodes().some(n=>n.type==='Modal'),false);
  // Success refresh is allowed, but a decline never waits for membership/consent.
  f.model.statusRead=null;f.model.status.previewEligible=true;
  const accept=outcome(f.api.agent.respondInvite('invite','Me','accept'));await f.boundary.settle();
  assert.equal(f.posts.length,1);assert.ok(f.boundary.text().includes(f.MONETIZATION.previewInfo()));
  f.choose(f.PLUS.cancel());await f.boundary.settle();assert.ok((await bounded(accept)).error);
  assert.equal(f.posts.length,1);f.close();
  console.log('PASS actual invitation decline bypasses Preview consent; accept still needs explicit consent');
}
async function previewFailure(){
  const f=await fixture(undefined,false,'web');
  const free={ok:true,phase:'foundation',state:'free',plan:'free',source:'none',serverTime:1100,previewStartedAt:null,expiresAt:null,
    canStartPreview:true,previewEnabled:true,previewDays:14,purchaseAvailable:false,restoreAvailable:false,enforcementEnabled:false,
    products:[{id:'plus_monthly',period:'month',referencePriceCents:1199,currency:'EUR'},{id:'plus_annual',period:'year',referencePriceCents:8999,currency:'EUR'}]};
  f.model.status=free;await f.openPlus();
  f.model.reply=async()=>({status:503,body:{error:'monetization_unavailable'}});
  f.plus.press(f.PLUS.start());await f.plus.settle();f.choose(f.PLUS.confirm());await f.plus.settle();
  assert.ok(f.plus.text().includes(f.MONETIZATION.unknown()));assert.ok(!f.plus.text().includes(f.PLUS.preview()));
  await f.advance(60000);assert.ok(f.plus.text().includes(f.MONETIZATION.unknown()),'polling GET Free cannot erase failed POST');
  f.model.reply=async()=>{f.model.status={...free,state:'preview',plan:'plus',source:'preview',previewStartedAt:1000,expiresAt:1210600,canStartPreview:false};return {body:f.model.status};};
  f.plus.press(f.PLUS.start());await f.plus.settle();f.choose(f.PLUS.confirm());await f.plus.settle();
  assert.equal(f.posts.length,2);assert.ok(f.plus.text().includes(f.PLUS.preview()));assert.ok(!f.plus.text().includes(f.MONETIZATION.unknown()));f.close();
  const labels=load('src/monetization.ts',{'./i18n':{T:(...v)=>v[1],dateLocale:()=> 'en'}});
  const {MembershipClient}=load('src/membership-client.ts',{'./api':{},'./monetization':labels});
  let fail=true;const client=new MembershipClient(()=> 'a',{get:async()=>free,start:async()=>{if(fail)throw Error('503');return free;}});
  assert.equal(await client.start(),false);fail=false;assert.equal(await client.start(),true);
  console.log('PASS foundation POST failure persists through polling; caller result and explicit retry are truthful');
}
function capacity(){
  const src=fs.readFileSync(path.join(__dirname,'../app/intent.tsx'),'utf8');
  const ast=ts.createSourceFile('intent.tsx',src,99,true,ts.ScriptKind.TSX),buttons=[],cancels=[];
  (function visit(node){if(ts.isJsxSelfClosingElement(node)&&node.tagName.getText(ast)==='GlassPill'){
    const attrs=Object.fromEntries(node.attributes.properties.filter(ts.isJsxAttribute).map(a=>[a.name.getText(ast),a.initializer?.expression]));
    if(attrs.label&&['WIZ.keepFive()','WIZ.getPlus()'].includes(attrs.label.getText(ast)))buttons.push(attrs);
    if(attrs.label?.getText(ast)==='WIZ.cancel()'&&attrs.onPress?.getText(ast)==='() => setGroupSizeOpen(false)')cancels.push(attrs);
  }ts.forEachChild(node,visit);})(ast);
  assert.equal(buttons.length,2);assert.ok(buttons.every(b=>b.label.getText(ast)==='WIZ.keepFive()'));
  for(let lang=0;lang<3;lang++){
    const data=load('src/intent.ts',{'./i18n':{T:(...v)=>v[lang],getLang:()=>['ru','en','es'][lang]},'./groups':{},'./interest-label':{}});
    assert.ok(data.WIZ.plusTitle());assert.ok(!data.WIZ.plusTitle().includes('Plus'));
  }
  for(const [index,b] of buttons.entries())for(const target of index===0?['edit','draft']:['edit']){let draft={title:'draft'},edraft={title:'edit'},open=true;
    const callback=ts.transpileModule('const callback='+b.onPress.getText(ast),{compilerOptions:{target:7}}).outputText;
    const scope={setGroupSizeOpen:v=>open=v,setDraft:fn=>draft=fn(draft),setEdraft:fn=>edraft=fn(edraft),groupSizeTarget:target,GROUP_FREE_MAX_TOTAL:5};
    Function(...Object.keys(scope),callback+';callback();')(...Object.values(scope));
    assert.equal(open,false);assert.equal((target==='edit'?edraft:draft).groupSize,5);
    assert.equal(edraft.title,'edit');assert.equal(draft.title,'draft');
    assert.deepEqual(target==='edit'?draft:edraft,{title:target==='edit'?'draft':'edit'});
  }
  assert.equal(cancels.length,2);
  for(const b of cancels){let open=true;
    const callback=ts.transpileModule('const callback='+b.onPress.getText(ast),{compilerOptions:{target:7}}).outputText;
    // No draft/edit setter or router is available: cancel must only close capacity.
    Function('setGroupSizeOpen',callback+';callback();')(value=>open=value);assert.equal(open,false);
  }
  console.log('PASS both capacity callbacks select allowed size and preserve drafts; neutral RU/EN/ES title');
}
const original=global.fetch;
(async()=>{await subscribers();await decline();await previewFailure();capacity();})().catch(e=>{console.error(e);process.exitCode=1;}).finally(()=>{global.fetch=original;});
