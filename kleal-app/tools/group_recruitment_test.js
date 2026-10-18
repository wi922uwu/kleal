/** Executes the actual group inviteMore handler and invitation-cap JSX callbacks. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),ts=require(path.join(root,'node_modules/typescript'));
const read=file=>fs.readFileSync(path.join(root,file),'utf8');
function find(file,predicate){const ast=ts.createSourceFile(file,read(file),99,true,ts.ScriptKind.TSX),found=[];
  function visit(n){if(predicate(n,ast))found.push(n.getText(ast));ts.forEachChild(n,visit);}visit(ast);assert.equal(found.length,1,file);return found[0];}
function evaluate(source,scope){const code=ts.transpileModule(source,{compilerOptions:{target:7,jsx:ts.JsxEmit.React,module:1}}).outputText;
  return Function(...Object.keys(scope),code)(...Object.values(scope));}
function load(file,stubs){const m={exports:{}};evaluate(read(file),{module:m,exports:m.exports,require:n=>{assert.ok(n in stubs,n);return stubs[n];}});return m.exports;}
const nodes=v=>Array.isArray(v)?v.flatMap(nodes):v && typeof v==='object'?[v,...nodes(v.props?.children)]:[];
(async()=>{
  const source=find('app/group.tsx',(n,a)=>ts.isVariableDeclaration(n)&&n.name.getText(a)==='inviteMore');
  for(const allowed of [true,false]){
    const ranked=[],results=[],routes=[],adopted=[],errors=[];
    const handler=evaluate('const '+source+'; return inviteMore;',{adopting:false,gid:'group-existing',g:{title:'untrusted display',topics:['not canonical']},
      me:'Owner',st:{profile:{languages:{comfortable:['en']}}},setAdopting(){},setErr:e=>errors.push(e),setInfo(){},
      adoptGroup:async(...args)=>{adopted.push(args);return allowed;},
      agent:{match(){throw Error('must not publish');},matchGroup:async(...args)=>{ranked.push(args);return {intent:{_searchId:'canonical',topics:['coffee']},candidates:[{id:'peer'}]};}},
      setResults:r=>results.push(r),openResults:r=>routes.push(r),router:'router',ROOM:{gone:()=> 'gone'},GROUP:{sendFailed:()=> 'failed'}});
    await handler();assert.deepEqual(adopted,[['Owner','group-existing']]);
    if(allowed){assert.equal(ranked.length,1);assert.equal(ranked[0][0],'group-existing');assert.equal(results[0].intent._searchId,'canonical');assert.deepEqual(routes,['router']);}
    else {assert.deepEqual(ranked,[]);assert.deepEqual(results,[]);assert.deepEqual(errors,['gone']);}
  }
  console.log('PASS actual group inviteMore adopts the same group and ranks only its canonical reference');
  let lang=0;const i18n={T:(...v)=>v[lang],getLang:()=>['ru','en','es'][lang]};
  const groups=load('src/groups.ts',{'./i18n':i18n,'./api':{myId:()=> 'a'},'./intent':{normalizeIntentSize:()=> 'group'}});
  const candidates=load('src/candidates.ts',{'./i18n':i18n,'./names':{acc:x=>x,dat:x=>x,gen:x=>x,ins:x=>x},'./interest-label':{interestLabels:x=>x}});
  const sheet=find('app/results.tsx',(n,a)=>ts.isJsxElement(n)&&n.openingElement.tagName.getText(a)==='Sheet'
    && n.openingElement.attributes.properties.some(p=>p.name?.getText(a)==='visible'&&p.initializer?.expression?.getText(a)==='capOpen'));
  const React={Fragment:'Fragment',createElement:(type,props,...children)=>({type,props:{...props,children}})};
  for(lang=0;lang<3;lang++)for(const gmode of [false,true]){
    const updates=[],routes=[];
    const tree=evaluate('return '+sheet+';',{React,Sheet:'Sheet',SheetText:'SheetText',GlassPill:'GlassPill',capOpen:true,
      setCapOpen:v=>updates.push(v),gmode,GR14:groups.GR14,CAP:candidates.CAP,gc:{open:3,cap:3},GROUP_FREE_MAX_TOTAL:6,
      pendingOut:[1,2,3],s:{btn48:{}},router:{navigate:v=>routes.push(v)}});
    const buttons=nodes(tree).filter(n=>n.type==='GlassPill');assert.equal(buttons.length,1);
    assert.equal(tree.props.title,groups.GR14.capTitle());assert.ok(!tree.props.title.includes('Plus'));
    const note=nodes(tree).find(n=>n.type==='SheetText').props.note;
    assert.ok(note.includes('Free')&&note.includes('Plus'));assert.ok(!/[€$]|6[.,]99/.test(note));
    buttons[0].props.onPress();assert.deepEqual(updates,[false]);assert.deepEqual(routes,[]);
  }
  console.log('PASS actual invitation-cap dialogs RU/EN/ES preserve capacity, offer return and never promise Plus relief');
})().catch(e=>{console.error(e);process.exitCode=1;});
