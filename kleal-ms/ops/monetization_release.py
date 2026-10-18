#!/usr/bin/env python3
"""Host-local, manifest-scoped release primitives. No SSH, recursive sync or live
defaults. This module never restores an old snapshot onto a nonempty schema.
Use the documented coordinator sequence; preparation is not deployment evidence.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import urllib.request
import urllib.error
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'tools'),str(Path(__file__).resolve().parents[1]/'shared')]
import monetization_store as ms
import monetization_production as production
import monetization_safety as safety

BASE_TABLES=('users','store_kv','outbox')
CANONICAL=('monetization_meta','monetization_accounts','monetization_commands','monetization_resources',
           'monetization_aliases','monetization_sessions','monetization_plan_sessions','monetization_protected',
           'monetization_documents','monetization_audit','monetization_deletions','monetization_manual_grants',
           'monetization_admin_commands','monetization_admin_audit','monetization_owned_keys')
WRITER_ROLES={'onboarding','matching','buddy','worker','life','admin'}
SEQUENCE_TABLES=('outbox','monetization_audit','monetization_admin_audit')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def metadata(path):
    if not path.exists(): return None
    info=path.stat()
    if not stat.S_ISREG(info.st_mode): raise ValueError('regular release file required')
    return {'mode':stat.S_IMODE(info.st_mode),'uid':info.st_uid,'gid':info.st_gid}


def target(root,relative):
    root=Path(root).resolve();path=root/relative
    if not relative or Path(relative).is_absolute() or '..' in Path(relative).parts or path.is_symlink() or root not in path.resolve().parents:
        raise ValueError('manifest path must be a regular file inside the exact root')
    return path


def make_manifest(baseline,candidate,paths):
    if not paths or len(paths)!=len(set(paths)): raise ValueError('explicit unique file paths required')
    files=[]
    for rel in paths:
        before=target(baseline,rel);after=target(candidate,rel)
        if not after.is_file(): raise ValueError('candidate file missing: '+rel)
        if sha(before)==sha(after): continue
        original=metadata(before);proposed=metadata(after)
        files.append({'path':rel,'before':sha(before),'after':sha(after),
                      'beforeMetadata':original,'afterMetadata':proposed,
                      'installMetadata':original or proposed})
    result={'version':2,'files':files};result['checksum']=ms.digest(result)
    return result


def validate_manifest(manifest):
    if manifest.get('version')!=2 or ms.digest({k:v for k,v in manifest.items() if k!='checksum'})!=manifest.get('checksum'):
        raise ValueError('invalid manifest')
    if not manifest.get('files') or len({x['path'] for x in manifest['files']})!=len(manifest['files']):
        raise ValueError('empty or duplicate release manifest')
    for entry in manifest['files']:
        for field in ('beforeMetadata','afterMetadata','installMetadata'):
            value=entry.get(field)
            if field=='beforeMetadata' and entry.get('before') is None and value is None: continue
            if not isinstance(value,dict) or set(value)!= {'mode','uid','gid'} or any(
                type(n) is not int or n<0 for n in value.values()) or value['mode']>0o7777:
                raise ValueError('invalid release metadata')
        if entry['installMetadata']!=(entry['beforeMetadata'] or entry['afterMetadata']):
            raise ValueError('install metadata must preserve original or reviewed new-file metadata')


def file_matches(path,entry,side):
    content='after' if side=='installed' else side
    field='installMetadata' if side=='installed' else side+'Metadata'
    return sha(path)==entry[content] and metadata(path)==entry[field]


def verify_manifest(root,manifest,side):
    validate_manifest(manifest)
    if side not in ('before','after','installed'): raise ValueError('invalid manifest side')
    drift=[x['path'] for x in manifest['files'] if not file_matches(target(root,x['path']),x,side)]
    if drift: raise ValueError('source drift: '+', '.join(drift))
    return {'ok':True,'files':len(manifest['files']),'checksum':manifest['checksum']}


def writer_states():
    units=json.loads(os.environ.get('KLEAL_RELEASE_SERVICES','{}'))
    if set(units)!=WRITER_ROLES or len(set(units.values()))!=len(units):
        raise ValueError('exact verified unit inventory required in KLEAL_RELEASE_SERVICES')
    result={}
    for role,unit in sorted(units.items()):
        if not re.fullmatch(r'[A-Za-z0-9_@.-]+\.service',unit): raise ValueError('invalid unit name')
        p=subprocess.run(['systemctl','show',unit,'--property=LoadState,ActiveState'],capture_output=True,text=True,check=False)
        properties=dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
        state=properties.get('ActiveState')
        if p.returncode or properties.get('LoadState')!='loaded' or state not in ('active','inactive','failed'):
            raise ValueError('cannot establish writer state: '+unit)
        result[unit]=state
    return result


def require_stopped():
    states=writer_states()
    if any(s=='active' for s in states.values()): raise ValueError('writers must be stopped by the coordinator before cutover')
    return states


def backup(conn):
    """One MVCC statement captures all supported tables. Unknown tables stop the release."""
    ms.bounded_transaction(conn)
    tables=[r[0] for r in conn.execute('select tablename from pg_tables where schemaname=current_schema() order by tablename').fetchall()]
    if set(tables)-set(BASE_TABLES+CANONICAL): raise ValueError('unknown tables; extend reviewed backup inventory first')
    if not set(BASE_TABLES)<=set(tables): raise ValueError('base tables missing')
    parts=["'%s',coalesce((select jsonb_agg(to_jsonb(r) order by to_jsonb(r)::text) from %s r),'[]'::jsonb)"%(t,t) for t in tables]
    result={'version':2,'tables':conn.execute('select jsonb_build_object('+','.join(parts)+')').fetchone()[0], 'sequences':{}}
    from psycopg import sql
    # The coordinator has fenced writers. Sequence state is non-MVCC and must be
    # captured explicitly; max(id) loses rollbacks, deleted rows and setval(false).
    for table in SEQUENCE_TABLES:
        if table not in tables: continue
        sequence=conn.execute("select pg_get_serial_sequence(%s,'id')",(table,)).fetchone()[0]
        if not sequence: raise ValueError('supported sequence missing')
        result['sequences'][table]=list(conn.execute(sql.SQL('select last_value,is_called from {}').format(sql.Identifier(*sequence.split('.')))).fetchone())
    sequences={row[0] for row in conn.execute('select sequencename from pg_sequences where schemaname=current_schema()')}
    if sequences != {table+'_id_seq' for table in result['sequences']}:
        raise ValueError('unknown sequences; extend reviewed backup inventory first')
    result['checksum']=ms.digest(result)
    return result


def restore_rehearsal(conn,snapshot):
    safety.guard(conn)
    if conn.execute('select 1 from information_schema.tables where table_schema=current_schema() limit 1').fetchone():
        raise ValueError('restore requires empty schema')
    payload={k:v for k,v in snapshot.items() if k!='checksum'}
    if (payload.get('version')!=2 or ms.digest(payload)!=snapshot.get('checksum')
        or not set(BASE_TABLES)<=set(payload.get('tables',{}))
        or set(payload.get('tables',{}))-set(BASE_TABLES+CANONICAL)
        or set(payload.get('sequences',{})) != set(SEQUENCE_TABLES)&set(payload.get('tables',{}))):
        raise ValueError('invalid snapshot')
    for value in payload['sequences'].values():
        if not isinstance(value,list) or len(value)!=2 or type(value[0]) is not int or value[0]<1 or type(value[1]) is not bool:
            raise ValueError('invalid sequence state')
    ms.bounded_transaction(conn)
    conn.execute(ms.db.SCHEMA)
    if set(payload['tables'])&set(CANONICAL): conn.execute(ms.SCHEMA)
    if 'monetization_owned_keys' in payload['tables']: conn.execute('create table monetization_owned_keys(key text primary key)')
    for table in BASE_TABLES+CANONICAL:
        for row in payload['tables'].get(table,[]):
            conn.execute('insert into '+table+' select * from json_populate_record(null::'+table+',%s)',(json.dumps(row),))
    for table,(last,called) in payload['sequences'].items():
        conn.execute("select setval(pg_get_serial_sequence(%s,'id'),%s,%s)",(table,last,called))
    if 'monetization_owned_keys' in payload['tables']: conn.execute(production.FENCE_SQL)
    restored=backup(conn)
    # Additive empty tables created by SCHEMA are expected; every captured table must match.
    if any(restored['tables'].get(k)!=v for k,v in payload['tables'].items()): raise ValueError('restore verification failed')
    if any(restored['sequences'].get(k)!=v for k,v in payload['sequences'].items()): raise ValueError('sequence restore verification failed')
    return {'ok':True,'restoredChecksum':snapshot['checksum']}


def sync_directory(path):
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
    try: os.fsync(fd)
    finally: os.close(fd)


def sync_parents(path,root):
    path,root=Path(path).resolve(),Path(root).resolve()
    while True:
        sync_directory(path)
        if path==root: break
        if root not in path.parents: raise ValueError('directory outside release root')
        path=path.parent
    sync_directory(root.parent)


def save_private(path,value):
    with os.fdopen(os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'w') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2)
        stream.flush();os.fsync(stream.fileno())
    sync_directory(Path(path).parent)


def prepare_file(path,data,meta):
    """Сначала bytes+owner+mode во временном файле; ошибка не меняет target."""
    with os.fdopen(os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'wb') as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())
    try:
        os.chown(path,meta['uid'],meta['gid'])
        # chown может сбрасывать special mode bits: chmod обязательно после него.
        os.chmod(path,meta['mode'])
        if metadata(path)!=meta: raise ValueError('cannot preserve release metadata')
        with path.open('rb') as stream: os.fsync(stream.fileno())
        sync_directory(path.parent)
    except BaseException:
        path.unlink()
        raise


def install(root,candidate,manifest,backup_dir):
    require_stopped();verify_manifest(root,manifest,'before');verify_manifest(candidate,manifest,'after')
    backup_dir=Path(backup_dir);backup_dir.mkdir(mode=0o700,parents=False,exist_ok=False)
    save_private(backup_dir/'release-manifest.json',manifest)
    for entry in manifest['files']:
        rel=entry['path'];dst=target(root,rel);src=target(candidate,rel);saved=target(backup_dir,rel)
        if dst.exists():
            saved.parent.mkdir(parents=True,exist_ok=True)
            with os.fdopen(os.open(saved,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'wb') as stream:
                stream.write(dst.read_bytes())
                stream.flush();os.fsync(stream.fileno())
            sync_parents(saved.parent,backup_dir)
    sync_parents(backup_dir,backup_dir)
    verify_manifest(root,manifest,'before')
    prepared=[]
    try:
        # Проверяем возможность сохранить ВСЮ metadata до первой замены.
        for entry in manifest['files']:
            dst=target(root,entry['path']);src=target(candidate,entry['path'])
            if not file_matches(src,entry,'after'): raise ValueError('candidate drift: '+entry['path'])
            dst.parent.mkdir(parents=True,exist_ok=True)
            temporary=dst.with_name(dst.name+'.monetization-release-new')
            prepare_file(temporary,src.read_bytes(),entry['installMetadata']);prepared.append((entry,dst,temporary))
            sync_parents(dst.parent,Path(root))
        verify_manifest(root,manifest,'before')
        for entry,dst,temporary in prepared:
            if not file_matches(dst,entry,'before'): raise ValueError('source metadata/content drift: '+entry['path'])
            if not file_matches(temporary,entry,'installed'): raise ValueError('prepared release drift')
            os.replace(temporary,dst)
            sync_directory(dst.parent)
        verify_manifest(root,manifest,'installed')
    finally:
        for _,_,temporary in prepared:
            if temporary.exists(): temporary.unlink()
    return {'ok':True,'backup':str(backup_dir),'files':len(manifest['files'])}


def restore_files(root,backup_dir,manifest):
    """Only after current canonical→legacy export; handles partial installs too."""
    require_stopped()
    validate_manifest(manifest)
    if json.loads((Path(backup_dir)/'release-manifest.json').read_text())!=manifest:
        raise ValueError('backup metadata manifest mismatch')
    for entry in manifest['files']:
        dst=target(root,entry['path'])
        if not any(file_matches(dst,entry,side) for side in ('before','installed')):
            raise ValueError('rollback source metadata/content drift: '+entry['path'])
        if entry['before'] is not None and sha(target(backup_dir,entry['path']))!=entry['before']:
            raise ValueError('backup source checksum mismatch')
    prepared=[]
    try:
        for entry in manifest['files']:
            dst=target(root,entry['path'])
            if file_matches(dst,entry,'before'): continue
            temporary=None
            if entry['before'] is not None:
                temporary=dst.with_name(dst.name+'.monetization-rollback-new')
                prepare_file(temporary,target(backup_dir,entry['path']).read_bytes(),entry['beforeMetadata'])
            prepared.append((entry,dst,temporary))
        for entry,dst,temporary in prepared:
            if not file_matches(dst,entry,'installed'): raise ValueError('rollback source metadata/content drift: '+entry['path'])
            if temporary:
                if not file_matches(temporary,entry,'before'): raise ValueError('prepared rollback drift')
                os.replace(temporary,dst)
            else: dst.unlink()
            sync_directory(dst.parent)
        return verify_manifest(root,manifest,'before')
    finally:
        for _,_,temporary in prepared:
            if temporary and temporary.exists(): temporary.unlink()


class NoSmokeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never copy credentials or replay a probe onto another endpoint, even
        # on the same origin. The operator must provide the final reviewed URL.
        raise ValueError('smoke redirects are forbidden')


def smoke(checks):
    """Explicit expected HTTP code/body or bundle SHA; credentials come only from env."""
    if not checks: raise ValueError('explicit health/auth/KYC/quota/bundle smoke inventory required')
    results=[]
    for check in checks:
        method=check.get('method','GET')
        status=check.get('status')
        if method not in ('GET','POST') or type(status) is not int or not 100<=status<=599:
            raise ValueError('explicit supported method/expected status required')
        if method=='POST' and (not 400<=status<500 or not isinstance(check.get('body'),dict)):
            raise ValueError('POST smoke requires an explicit denial status and JSON body')
        if method=='GET' and 'body' in check: raise ValueError('GET smoke must not carry a body')
        def credential_field(value):
            return isinstance(value,dict) and any(k.lower() in ('authorization','token','password','secret','api_key','apikey')
                or credential_field(v) for k,v in value.items()) or isinstance(value,list) and any(credential_field(v) for v in value)
        if 'headers' in check or credential_field(check.get('body')):
            raise ValueError('credentials must come from headersEnv')
        data=json.dumps(check['body']).encode() if method=='POST' else None
        if data and len(data)>65536: raise ValueError('bounded smoke body required')
        headers={h:os.environ[e] for h,e in check.get('headersEnv',{}).items()}
        if data is not None: headers['Content-Type']='application/json'
        request=urllib.request.Request(check['url'],method=method,data=data,headers=headers)
        try:
            with urllib.request.build_opener(NoSmokeRedirect()).open(request,timeout=20) as response: code,body=response.status,response.read()
        except urllib.error.HTTPError as e: code,body=e.code,e.read()
        if 300<=code<400: raise ValueError('smoke redirects are forbidden')
        if code!=check['status']: raise ValueError('smoke HTTP mismatch: '+check['name'])
        if check.get('sha256') and hashlib.sha256(body).hexdigest()!=check['sha256']: raise ValueError('bundle digest mismatch')
        if 'json' in check:
            value=json.loads(body)
            if any(value.get(k)!=v for k,v in check['json'].items()): raise ValueError('smoke body mismatch: '+check['name'])
        results.append({'name':check['name'],'ok':True})
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',choices=('manifest','verify','backup','restore-rehearsal','install','restore-files','activate','rollback','smoke'))
    p.add_argument('--root',type=Path);p.add_argument('--candidate',type=Path);p.add_argument('--file',type=Path,required=True)
    p.add_argument('--paths',nargs='+');p.add_argument('--backup-dir',type=Path);p.add_argument('--apply',action='store_true')
    a=p.parse_args()
    if a.operation=='manifest':
        result=make_manifest(a.root,a.candidate,a.paths);save_private(a.file,result)
    elif a.operation=='verify': result=verify_manifest(a.root,json.loads(a.file.read_text()),'before')
    elif a.operation=='smoke': result=smoke(json.loads(a.file.read_text()))
    elif a.operation=='install':
        if not a.apply: p.error('install requires --apply; run verify first')
        result=install(a.root,a.candidate,json.loads(a.file.read_text()),a.backup_dir)
    elif a.operation=='restore-files':
        if not a.apply: p.error('restore-files requires --apply after canonical export')
        result=restore_files(a.root,a.backup_dir,json.loads(a.file.read_text()))
    else:
        import psycopg
        if a.operation=='restore-rehearsal': safety.validate_test_dsn(os.environ['KLEAL_PG_DSN'])
        with psycopg.connect(os.environ['KLEAL_PG_DSN']) as conn:
            if a.operation=='backup':
                require_stopped()
                conn.execute('set transaction isolation level repeatable read read only')
                value=backup(conn);save_private(a.file,value);result={'ok':True,'checksum':value['checksum']}
            elif a.operation=='restore-rehearsal': result=restore_rehearsal(conn,json.loads(a.file.read_text()))
            else:
                if not a.apply: p.error('activation/rollback require --apply and stopped writers')
                require_stopped()
                # The caller must provide the expected import provenance, preventing accidental DB targeting.
                evidence=json.loads(a.file.read_text())
                row=conn.execute("select value from monetization_meta where key='production_import'").fetchone()
                if not row or row[0]!=evidence['snapshotHash']: raise ValueError('wrong database/import provenance')
                result=production.activate(conn) if a.operation=='activate' else production.export_legacy(conn,True)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
