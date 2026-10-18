// Consume actual HTTP JSON supplied by the backend suite. No duplicate schema.
const fs=require('node:fs'),path=require('node:path'),ts=require('typescript');
const source=fs.readFileSync(path.join(__dirname,'../src/monetization.ts'),'utf8');
const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
const loaded={exports:{}};
Function('require','module','exports',js)(name=>{
  if(name==='./i18n')return {T:(...args)=>args[0],dateLocale:()=> 'en'};
  throw new Error('unexpected dependency '+name);
},loaded,loaded.exports);
const values=JSON.parse(fs.readFileSync(0,'utf8'));
if(!Array.isArray(values)||!values.length||!values.every(loaded.exports.isMembershipV2)){
  console.error('Actual HTTP status rejected by production isMembershipV2');process.exitCode=1;
}
