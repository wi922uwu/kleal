// Executable migration contracts. Run with node tools/sdk57_migration_test.js.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
function load(file, overrides = {}) {
  const mod = { exports: {} };
  const js = ts.transpileModule(read(file), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  new Function('require', 'module', 'exports', js)(
    (id) => id in overrides ? overrides[id] : require(id), mod, mod.exports);
  return mod.exports;
}

async function main() {
  const packages = JSON.parse(read('package.json'));
  assert.match(packages.dependencies.expo, /^~57\./);
  assert.equal(packages.dependencies['react-native'], '0.86.3');
  assert.equal(packages.dependencies.react, '19.2.3');
  assert.match(packages.dependencies['expo-file-system'], /^~57\./);
  const config = JSON.parse(read('app.json')).expo;
  assert.equal(config.runtimeVersion, undefined, 'no runtimeVersion disguise');
  assert.equal(config.sdkVersion, undefined, 'SDK derives from installed Expo');
  console.log('ok SDK57 real dependency contract');

  const bytes = new Uint8Array([0, 255, 17, 128]);
  class LocalFile {
    constructor(uri) { this.uri = uri; }
    get name() { return 'cached-recording'; }
    get type() { return 'application/octet-stream'; }
    async bytes() {
      if (this.uri.includes('missing')) throw new Error('FILE_MISSING');
      return bytes;
    }
  }
  const { appendUploadFile } = load('src/upload-file.native.ts', { 'expo-file-system': { File: LocalFile } });
  // Exercise the actual installed Expo serializer, not a copy of its algorithm.
  const { convertFormDataAsync } = load('node_modules/expo/src/winter/fetch/convertFormData.ts', {
    '../../utils/blobUtils': { blobToArrayBufferAsync: (blob) => blob.arrayBuffer() },
  });
  for (const [name, type] of [['voice.m4a', 'audio/mp4'], ['circle.mov', 'video/quicktime'],
    ['circle.mp4', 'video/mp4'], ['evidence.pdf', 'application/pdf']]) {
    const parts = [];
    const form = { append: (...part) => parts.push(part), entries: () => parts.values() };
    await appendUploadFile(form, 'file:///private/cache/source', name, type);
    assert(parts[0][1] instanceof LocalFile, 'native part is a byte-readable File');
    const { body } = await convertFormDataAsync(form, 'test-boundary');
    const text = Buffer.from(body).toString('latin1');
    assert(text.includes(`filename="${name}"`));
    assert(text.includes(`content-type: ${type}`));
    assert(Buffer.from(body).includes(Buffer.from(bytes)), 'actual bytes, not URI');
    assert(!text.includes('private/cache'), 'device path is not sent');
  }
  const missing = [];
  await appendUploadFile({ append: (...part) => missing.push(part) }, 'file:///missing', 'voice.m4a', 'audio/mp4');
  await assert.rejects(convertFormDataAsync({ entries: () => missing.values() }), /FILE_MISSING/);
  await assert.rejects(convertFormDataAsync({ entries: () => [['file', { uri: 'file:///old' }]].values() }), /Unsupported/);
  console.log('ok native multipart bytes, names, MIME, privacy and error propagation');

  const originalFetch = global.fetch;
  try {
    global.fetch = async () => new Response(bytes, { headers: { 'Content-Type': 'application/octet-stream' } });
    const web = load('src/upload-file.ts');
    const form = new FormData();
    await web.appendUploadFile(form, 'blob:test', 'circle.webm', 'video/webm');
    assert.equal(form.get('file').name, 'circle.webm');
    assert.equal(form.get('file').type, 'video/webm');
    assert.deepEqual(new Uint8Array(await form.get('file').arrayBuffer()), bytes);
    global.fetch = async () => new Response('', { status: 404 });
    await assert.rejects(web.appendUploadFile(new FormData(), 'blob:gone', 'x', 'text/plain'), /UPLOAD_FILE_READ_FAILED/);
  } finally { global.fetch = originalFetch; }
  console.log('ok browser multipart and missing-file handling');

  for (const file of ['src/voice.tsx', 'src/videonote.tsx', 'app/group-report.tsx']) {
    assert.match(read(file), /await appendUploadFile\(/, file);
    assert.doesNotMatch(read(file), /form\.append\('file',\s*\{/, file);
  }
  for (const file of ['src/components/ExploreMap.native.tsx', 'src/components/OnlineIntentGlobe.native.tsx']) {
    assert.match(read(file), /showsPointsOfInterests=\{false\}/, file);
  }
  console.log('ok all native upload and map call sites migrated');
  for (const file of ['app/intent.tsx', 'app/results.tsx']) {
    assert.match(read(file), /usePreventRemove.*from 'expo-router\/react-navigation'/, file);
    assert.doesNotMatch(read(file), /from '@react-navigation\//, file);
  }
  console.log('ok navigation guards share the SDK57 router context');
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
