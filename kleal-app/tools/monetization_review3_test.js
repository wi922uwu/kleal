/** Реальные API/экраны/interest writer; web Alert из установленного RN Web. */
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),ts=require('typescript');
const {fixture,load}=require('./monetization_components_test');
const tick=()=>new Promise(r=>setImmediate(r));
const defer=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {resolve,reject,promise};};
async function bounded(promise){
  let timer;
  try{return await Promise.race([promise,new Promise((_resolve,reject)=>{timer=setTimeout(()=>reject(Error('caller promise did not settle')),1000);})]);}
  finally{clearTimeout(timer);}
}
async function webDialogs(){
  for(const choice of ['cancel','continue','switch','unmount']){
    const f=await fixture(undefined,false,'web');f.model.status.previewEligible=true;
    const outcome=f.api.api.post('/api/agent/search-command',{intent:{topics:['coffee']}}).then(value=>({value}),error=>({error}));
    await f.boundary.settle();assert.equal(f.posts.length,0);assert.equal(f.alerts.length,0,'RN Web Alert has no mock implementation');
    assert.ok(f.boundary.text().includes(f.MONETIZATION.previewInfo()));
    if(choice==='switch'){f.api.setSession('token-b');f.boundary.rerender();await f.boundary.settle();}
    else if(choice==='unmount')f.boundary.unmount();
    else f.choose(choice==='cancel'?f.PLUS.cancel():f.MONETIZATION.continue());
    await f.boundary.settle();const result=await bounded(outcome);
    assert.equal(f.posts.length,choice==='continue'?1:0,choice);
    assert.equal(!!result.value,choice==='continue',choice);f.close();
  }
  for(const exit of ['switch','unmount']){
    const f=await fixture(undefined,false,'web');
    f.model.reply=async()=>({status:409,body:{error:'search_quota',blockerIds:['active']}});
    const outcome=f.api.api.post('/api/agent/search-command',{intent:{topics:['coffee']}}).then(value=>({value}),error=>({error}));
    await f.boundary.settle();assert.equal(f.posts.length,1);assert.ok(f.boundary.text().includes(f.MONETIZATION.searchQuota()));
    if(exit==='switch'){f.api.setSession('token-b');f.boundary.rerender();await f.boundary.settle();}else f.boundary.unmount();
    assert.ok((await bounded(outcome)).error);assert.equal(f.posts.length,1);assert.equal(f.routes.length,0);f.close();
  }
  const f=await fixture(undefined,false,'web');
  f.model.status.searches=[{id:'paused',title:'Paused',state:'paused',publishedAt:1},{id:'blocker',title:'Blocker',state:'active',publishedAt:1}];
  f.model.reply=async p=>p.body.swapSearchId?{body:{ok:true}}:{status:409,body:{error:'search_quota',blockerIds:['blocker']}};
  await f.openPlus();f.plus.press(f.MONETIZATION.resumeSearch());await f.plus.settle();
  f.plus.press(f.MONETIZATION.swap());await f.plus.settle();f.choose(f.PLUS.cancel());await f.plus.settle();assert.equal(f.posts.length,1);
  f.plus.press(f.MONETIZATION.swap());await f.plus.settle();f.choose(f.MONETIZATION.continue());await f.plus.settle();
  assert.equal(f.posts[1].body.swapSearchId,'blocker');f.close();
  for(const platform of ['web','ios'])for(const exit of ['switch','unmount','blur']){
    const stale=await fixture(undefined,false,platform);
    stale.model.status.searches=[{id:'paused',title:'Paused',state:'paused',publishedAt:1},{id:'blocker',title:'Blocker',state:'active',publishedAt:1}];
    stale.model.reply=async()=>({status:409,body:{error:'search_quota',blockerIds:['blocker']}});
    await stale.openPlus();stale.plus.press(stale.MONETIZATION.resumeSearch());await stale.plus.settle();
    stale.plus.press(stale.MONETIZATION.swap());await stale.plus.settle();
    const text=node=>!node?'':typeof node==='object'?(node.props?.children||[]).flat(Infinity).map(text).join(''):String(node);
    const confirm=platform==='web'?stale.plus.nodes().find(node=>node.type==='Pressable'&&text(node)===stale.MONETIZATION.continue()).props.onPress
      :stale.alerts.at(-1).buttons.find(button=>button.text===stale.MONETIZATION.continue()).onPress;
    if(exit==='switch')stale.api.setSession('token-b');else if(exit==='unmount')stale.plus.unmount();else stale.plus.blur();
    confirm();await stale.plus.settle();assert.equal(stale.posts.length,1,'stale swap callback '+platform+'/'+exit);stale.close();
  }
  const notice=await fixture(undefined,false,'web');
  notice.model.status={...notice.model.status,state:'preview',plan:'plus',previewStartedAt:1000,expiresAt:1210600,serverTime:1100,
    previewNotice:true,limits:{activeSearches:null,initiatedChats:null}};
  notice.actions.monetizationInteraction().changed();await notice.boundary.settle();assert.equal(notice.posts.length,0);
  assert.ok(notice.boundary.text().includes(notice.previewNoticePresentation(notice.model.status).message));
  notice.choose(notice.MONETIZATION.continue());await notice.boundary.settle();assert.equal(notice.posts.length,1);notice.close();
  console.log('PASS actual web Preview/quota promises settle on session/unmount; consent/notice/swap and stale web/native swap guards');
}
async function foundation(){
  const f=await fixture(undefined,false,'web');
  const free={ok:true,phase:'foundation',state:'free',plan:'free',source:'none',serverTime:1100,previewStartedAt:null,expiresAt:null,
    canStartPreview:true,previewEnabled:true,previewDays:14,purchaseAvailable:false,restoreAvailable:false,enforcementEnabled:false,
    products:[{id:'plus_monthly',period:'month',referencePriceCents:1199,currency:'EUR'},{id:'plus_annual',period:'year',referencePriceCents:8999,currency:'EUR'}]};
  f.model.status=free;await f.openPlus();assert.ok(f.plus.text().includes(f.PLUS.start()));
  assert.ok(!f.plus.text().includes(f.PLUS.unavailable()));
  f.plus.press(f.PLUS.start());await f.plus.settle();f.choose(f.PLUS.cancel());await f.plus.settle();assert.equal(f.posts.length,0);
  f.model.reply=async()=>{f.model.status={...free,state:'preview',plan:'plus',source:'preview',previewStartedAt:1000,expiresAt:1210600,canStartPreview:false};return {body:f.model.status};};
  f.plus.press(f.PLUS.start());await f.plus.settle();f.choose(f.PLUS.confirm());await f.plus.settle();
  assert.equal(f.posts.length,1);assert.equal(f.posts[0].body.consent,true);assert.ok(f.posts[0].url.endsWith('/preview'));
  assert.ok(f.plus.text().includes(f.PLUS.preview()));assert.ok(!f.plus.text().includes(f.PLUS.unavailable()));
  assert.ok(!f.plus.text().includes(f.PLUS.start()));f.close();
  console.log('PASS foundation explicit consent/start, active Preview copy, no purchase');
}
function apiFixture(failure){
  const actions=load('src/monetization-actions.ts'),state={requests:[],failure,disk:failure==='corrupt'?'{bad':failure==='shape'?'{}':null,network:false};
  const api=load('src/api.ts',{'react-native':{Image:{prefetch:async()=>{}}},
    '@react-native-async-storage/async-storage':{getItem:async()=>{if(state.failure==='read')throw Error('read');return state.disk;},
      setItem:async(_k,v)=>{if(state.failure==='write')throw Error('write');state.disk=v;}},
    './i18n':{getLang:()=> 'en',replyLang:()=> 'en'},'./thinking':{whileThinking:p=>p},'./interest-label':{registerInterestLabels(){}},'./monetization-actions':actions});
  global.fetch=async(url,init)=>{
    if(url.includes('/profile'))return {ok:true,status:200,text:async()=>JSON.stringify({user:{id:init.headers.Authorization==='Bearer a'?'a':'b'}})};
    state.requests.push({url,body:JSON.parse(init.body),auth:init.headers.Authorization});
    if(state.network)throw Error('network');
    return {ok:true,status:200,text:async()=>JSON.stringify({ok:true})};
  };
  api.setSession('a');return {api,state};
}
async function protective(){
  for(const failure of ['read','write','corrupt','shape']){
    for(const route of ['block','group-leave','gintent-leave']){
      const {api,state}=apiFixture(failure);await api.ensureMe();state.network=true;
      await assert.rejects(api.api.post('/api/agent/'+route,{to_id:'b',gid:'g'}));
      assert.equal(state.requests.length,1);const key=state.requests[0].body.commandId;
      state.network=false;
      const retry=api.api.post('/api/agent/'+route,{to_id:'b',gid:'g'});
      if(failure==='write')await assert.rejects(retry,/write/);else await retry;
      assert.equal(state.requests[1].body.commandId,key,'known uncertain safety key survives '+failure);
      const before=state.requests.length;
      await assert.rejects(api.api.post('/api/agent/search-command',{intent:{topics:['coffee']}}));
      assert.equal(state.requests.length,before,'publication still requires durable metadata');
      api.setSession('b');const switched=api.api.post('/api/agent/'+route,{to_id:'b',gid:'g'});
      if(failure==='write')await assert.rejects(switched,/write/);else await switched;
      assert.notEqual(state.requests.at(-1).body.commandId,key);assert.equal(state.requests.at(-1).auth,'Bearer b');
    }
  }
  console.log('PASS actual block/group leaves reach server on read/write/corrupt failures; uncertain keys/account isolation/publication durability');
}
async function interestWrites(){
  let state={session:'a',done:true,profile:{name:'A',interests:{explicit:['old'],confirmations:{}}}},writes=[];
  const profile=load('src/profile.ts',{'./i18n':{T:(...x)=>x[1],getLang:()=> 'en'},'./onboarding':{},'./languages':{},
    './state':{getState:()=>state,set:(p,v)=>{state.profile.interests[p.split('.')[1]]=v;},subscribe(){},profileForAttach(){}},
    './api':{profile:{update:async(name,patch)=>{const d=defer();writes.push({name,patch,d});return d.promise;}}},
    './fields':{patchFor:()=>JSON.parse(JSON.stringify({interests:state.profile.interests}))},'./interest-label':{interestLabel:k=>k}});
  const old=profile.pushInterests();await tick();assert.equal(writes.length,1);
  state.profile.interests={explicit:['old','new'],confirmations:{new:'receipt'}};
  const newer=profile.pushInterests();await tick();assert.equal(writes.length,1,'new request waits for older write');
  writes[0].d.resolve({ok:true});await old;await tick();assert.equal(writes.length,2);
  assert.deepEqual(writes[1].patch.interests,state.profile.interests);writes[1].d.resolve({ok:true});await newer;
  state.profile.interests.explicit.push('third');const failed=profile.pushInterests();await tick();writes[2].d.reject(Error('network'));assert.equal(await failed,false);
  const retry=profile.pushInterests();await tick();writes[3].d.resolve({ok:true});assert.equal(await retry,true);
  state.profile.interests.explicit.push('fourth');const inFlight=profile.pushInterests();await tick();
  const queued=profile.pushInterests();state={session:'b',done:true,profile:{name:'B',interests:{explicit:['b'],confirmations:{}}}};
  const b=profile.pushInterests();writes[4].d.resolve({ok:true});assert.equal(await inFlight,false);assert.equal(await queued,false);
  await tick();assert.equal(writes[5].name,'B');assert.deepEqual(writes[5].patch.interests.explicit,['b']);writes[5].d.resolve({ok:true});await b;
  state.done=false;assert.equal(await profile.pushInterests(),false);assert.equal(writes.length,6,'no registration write');
  state.done=true;profile.addConfirmedInterest('b','B','late-valid-receipt');assert.equal(state.profile.interests.confirmations.b,'late-valid-receipt');
  console.log('PASS real pushInterests queue/full receipts/error retry/account switch/pre-registration and existing-canonical late receipt');
}
function archiveRows(){
  const source=fs.readFileSync(path.join(__dirname,'../app/messages.tsx'),'utf8');
  const ast=ts.createSourceFile('messages.tsx',source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);
  let declaration;
  (function visit(node){if(ts.isVariableDeclaration(node)&&node.name.getText(ast)==='rowView')declaration=node.getText(ast);ts.forEachChild(node,visit);})(ast);
  assert.ok(declaration,'actual messages row renderer');
  const js=ts.transpileModule('const '+declaration+';', {compilerOptions:{target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.React}}).outputText;
  for(const [index,lang] of ['ru','en','es'].entries()){
    const messages=load('src/messages.ts',{'./i18n':{T:(...values)=>values[index],getLang:()=>lang,dateLocale:()=>lang,use12h:()=>false},
      './api':{isMe:()=>false,pidOf:x=>x},'./chat':{klealText:()=>''}});
    const prefs={chats:{},archived:[]};
    const scope={React:{createElement:(type,props,...children)=>({type,props:{...props,children}})},
      isMuted:()=>false,isUnread:()=>false,prefs,OPEN_DAYS:7,MSG:messages.MSG,shortDay:()=>'',
      Pressable:'Pressable',View:'View',Text:'Text',Image:'Image',IconBellOff:'IconBellOff',IconPerson:'IconPerson',
      IconImagePlaceholder:'IconImagePlaceholder',Hl:'Hl',s:{},color:{},open(){},setMenuRow(){},rowTime:()=>'',mediaUrl:x=>x,q:'',archiveTeaser:messages.archiveTeaser};
    const render=Function(...Object.keys(scope),js+';return rowView;')(...Object.values(scope));
    const text=node=>!node||typeof node!=='object'?'':[node.props?.text||'',...(node.props?.children||[]).flat(Infinity).map(text)].join(' ');
    const row={key:'thread:b',whoId:'b',kind:'thread',title:'B',teaser:'ordinary latest message',t:0};
    for(const [lifecycle,expected] of [
      [{state:'closed'},['Чат завершён · можно написать снова','Chat ended · you can write again','Chat finalizado · puedes volver a escribir'][index]],
      [{state:'closed',blocked:true},['Переписка заблокирована','Messaging blocked','Mensajes bloqueados'][index]]]){
      prefs.chats.b=lifecycle;const rendered=text(render(row,{arch:true}));assert.ok(rendered.includes(expected),lang+': '+rendered);
      assert.ok(!rendered.includes(row.teaser),'lifecycle label replaces teaser');
    }
    prefs.chats={};prefs.archived=[row.key];assert.ok(text(render(row,{arch:true})).includes(row.teaser),'local archive keeps teaser');
    prefs.archived=[];assert.ok(text(render(row)).includes(row.teaser),'normal row keeps teaser');
  }
  console.log('PASS actual messages row renders closed/blocked RU/EN/ES and preserves local-archive/normal teaser');
}
const fetch=global.fetch;
(async()=>{await webDialogs();await foundation();await protective();await interestWrites();archiveRows();})()
  .catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>{global.fetch=fetch;});
