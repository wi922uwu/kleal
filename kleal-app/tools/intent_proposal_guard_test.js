const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const src = fs.readFileSync(path.join(__dirname, '../src/buddy.ts'), 'utf8');
const start = src.indexOf('export function looksLikeIntent');
const end = src.indexOf('\n}', start) + 2;
const mod = {exports:{}};
const js = ts.transpileModule(src.slice(start, end), {compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
Function('exports', js)(mod.exports);
const accepts = mod.exports.looksLikeIntent;
const intent = {topics:['cinema'], title:'Поговорить про кино'};
assert.equal(accepts({intent}), true);
for (const flags of [{refused:'policy'}, {valid:false}, {rankable:false}]) {
  const input = {...flags,intent};
  const before = JSON.stringify(input);
  assert.equal(accepts(input), false);
  assert.equal(JSON.stringify(input), before);
}
assert.equal(accepts({intent:{...intent,rankable:false}}), false);
for(const input of [null,{}, {intent:null}]) assert.equal(accepts(input),false);
const screen=fs.readFileSync(path.join(__dirname,'../app/buddy.tsx'),'utf8');
const guard=screen.slice(screen.indexOf('if (r?.refused)'),screen.indexOf('if (looksLikeIntent(r))'));
for(const clear of ["setSheet(false)","setTopic('')","setWhat('')","setSeen(null)"]) assert.ok(guard.includes(clear));
console.log('PASS refused/invalid envelopes, valid proposals, input immutability and stale sheet cleanup');
const create=fs.readFileSync(path.join(__dirname,'../app/create.tsx'),'utf8');
assert.ok(create.includes('if (r?.ready && looksLikeIntent(r))'));
assert.ok(/if \(r\?\.refused \|\| r\?\.valid === false\) \{\s*setReady\(null\);\s*setSumOpen\(false\);/.test(create));
console.log('PASS builder clears stale ready state and rejects contradictory ready responses');
