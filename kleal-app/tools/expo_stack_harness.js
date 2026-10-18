/** Installed Expo Router reducers, with native rendering imports stubbed only. */
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..'), ts = require(path.join(root, 'node_modules/typescript'));
const vendor = path.join(root, 'node_modules/expo-router/build');
function expression(file, find) {
  const source = fs.readFileSync(file, 'utf8');
  const ast = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  let match;
  function visit(node) { if (find(node)) match = node; ts.forEachChild(node, visit); }
  visit(ast); assert.ok(match, 'source node in '+file); return match.getText(ast);
}
const singularSource = expression(path.join(vendor,'useScreens.js'), n=>ts.isFunctionDeclaration(n)&&n.name?.text==='getSingularId');
const getSingularId = Function(singularSource+';return getSingularId;')();
const original = require(path.join(vendor,'react-navigation/routers/StackRouter.js'));
const stubs = {
  'react/jsx-runtime':{}, 'react':{}, 'nanoid/non-secure':{nanoid:()=>String(++sequence)},
  './withLayoutContext':{withLayoutContext:()=>()=>{}},
  '../fork/native-stack/createNativeStackNavigator':{createNativeStackNavigator:()=>({Navigator:()=>{}})},
  '../link/preview/LinkPreviewContext':{}, '../navigationParams':require(path.join(vendor,'navigationParams.js')),
  '../useScreens':{getSingularId}, './stack-utils':{}, '../react-navigation/native':original,
  '../utils/children':{}, '../views/Protected':{},
};
let sequence=0;
const mod={exports:{}};
Function('require','module','exports',fs.readFileSync(path.join(vendor,'layouts/StackClient.js'),'utf8'))(
  name=>{assert.ok(name in stubs,'native-only dependency '+name);return stubs[name];},mod,mod.exports);

function createStack(recoveryScreenIdentity, legacy=false) {
  const file=path.join(root,'app/_layout.tsx');
  const screensSource=expression(file,n=>ts.isVariableDeclaration(n)&&n.name.getText()==='SCREENS');
  const screens=Function('TAB','FADE','return '+screensSource.slice(screensSource.indexOf('=')+1))({},{});
  const singular=expression(file,n=>ts.isJsxAttribute(n)&&n.name.getText()==='dangerouslySingular');
  const evaluate=singular.includes('=')?Function('name','recoveryScreenIdentity','return '+singular.slice(singular.indexOf('{')+1,-1)):()=>true;
  const routeNames=screens.map(([name])=>name), routeParamList={},routeGetIdList={};
  for(const name of routeNames) {
    const value=legacy?true:evaluate(name,recoveryScreenIdentity);
    routeGetIdList[name]=typeof value==='function'?({params})=>value(name,params||{}):value?opts=>getSingularId(name,opts):undefined;
  }
  const options={routeNames,routeParamList,routeGetIdList};
  const reducer=mod.exports.StackRouter({initialRouteName:'home'});
  let state=reducer.getInitialState(options), changed=()=>{};const history=[];
  const dispatch=action=>{history.push(action);const before=state;state=reducer.getStateForAction(state,action,options)||state;changed(before,state);};
  const action=(type,to)=>dispatch({type,payload:{name:typeof to==='string'?to.slice(1):to.pathname.slice(1),params:typeof to==='string'?undefined:to.params}});
  return {get state(){return state;},get current(){return state.routes[state.index];},options,history,
    onChange(fn){changed=fn;}, navigate:to=>action('NAVIGATE',to),dismissTo:to=>action('POP_TO',to),replace:to=>action('REPLACE',to),
    back:()=>dispatch({type:'GO_BACK'}),canGoBack:()=>state.index>0,
    navigation:{getCurrentRoute:()=>state.routes[state.index],getRootState:()=>state,resetRoot:next=>dispatch({type:'RESET',payload:next})},
  };
}
module.exports={createStack};
