#!/usr/bin/env python3
"""Synthetic-only snapshot/restore and canonical-to-legacy rollback rehearsal.

No activation flags, service restarts, live database or JSON fallback options.
The connection must be loopback, kleal_monetization_test*, schema test_*.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shared'))
import monetization_store as ms
import monetization_safety as safety

TABLES=('users','monetization_meta','monetization_accounts','monetization_commands',
        'monetization_resources','monetization_aliases','monetization_sessions',
        'monetization_plan_sessions','monetization_protected','monetization_documents',
        'monetization_audit','monetization_deletions','monetization_manual_grants',
        'monetization_admin_commands','monetization_admin_audit','outbox','store_kv')
SEQUENCES=('monetization_audit','monetization_admin_audit','outbox')


def guard(conn):
    safety.guard(conn)


def backup(conn):
    guard(conn)
    tx=ms.Transaction(conn);tx.lock('monetization:projection')
    if not conn.execute("select 1 from monetization_meta where key='fixture_hash'").fetchone():
        raise ValueError('synthetic migration provenance required')
    # One SQL statement means one MVCC snapshot, even while lock-free outbox
    # completion updates its ledger. A series of READ COMMITTED selects does not.
    parts=["'%s',coalesce((select jsonb_agg(to_jsonb(r) order by to_jsonb(r)::text) from %s r),'[]'::jsonb)" % (table,table)
           for table in TABLES]
    tables=conn.execute('select jsonb_build_object('+','.join(parts)+')').fetchone()[0]
    sequences={}
    for table in SEQUENCES:
        sequence=conn.execute("select pg_get_serial_sequence(%s,'id')",(table,)).fetchone()[0]
        # Sequence names originate in pg_catalog, never the snapshot or CLI.
        from psycopg import sql
        sequences[table]=list(conn.execute(sql.SQL('select last_value,is_called from {}').format(sql.Identifier(*sequence.split('.')))).fetchone())
    result={'synthetic':True,'version':2,'tables':tables,'sequences':sequences}
    result['checksum']=ms.digest(result)
    return result


def restore(conn,snapshot):
    guard(conn)
    payload={k:v for k,v in snapshot.items() if k!='checksum'}
    if payload.get('synthetic') is not True or payload.get('version')!=2 or set(payload.get('tables',{}))!=set(TABLES) or set(payload.get('sequences',{}))!=set(SEQUENCES) or ms.digest(payload)!=snapshot.get('checksum'):
        raise ValueError('invalid synthetic snapshot/checksum')
    if conn.execute("select 1 from information_schema.tables where table_schema=current_schema() limit 1").fetchone():
        raise ValueError('restore requires an empty schema; existing state is never overwritten')
    conn.execute(ms.SCHEMA);conn.execute(ms.db.SCHEMA)
    for table in TABLES:
        for row in payload['tables'][table]:
            conn.execute('insert into '+table+' select * from json_populate_record(null::'+table+',%s)',(json.dumps(row),))
    for table in SEQUENCES:
        last,called=payload['sequences'][table]
        if not isinstance(last,int) or last<1 or not isinstance(called,bool): raise ValueError('invalid sequence state')
        conn.execute("select setval(pg_get_serial_sequence(%s,'id'),%s,%s)",(table,last,called))
    return {'ok':True,'restoredChecksum':snapshot['checksum']}


def canonical_to_legacy(conn):
    """Freeze projection, refresh expiry and replace—not merge—the synthetic legacy store."""
    guard(conn)
    tx=ms.Transaction(conn);tx.lock('monetization:projection')
    for (owner,) in conn.execute("select owner_id from monetization_accounts where owner_id not like 'recovery:%%'").fetchall():
        tx.expire(owner)
    doc=tx.documents()
    for key,kind in (('_intents','intent'),('_gintents','group'),('_groups','group')):
        for row in doc.get(key,[]):
            rid=tx.resolve(kind,row.get('id'))
            if not rid: continue
            resource=tx.resource(rid)
            row.update(searchId=rid,searchState=resource['state'])
            if key=='_intents': row['status']='active' if resource['state']=='active' else 'paused'
    tx.save_documents(doc)
    conn.execute('delete from store_kv where not (key=any(%s))',(list(doc),))
    for key,value in doc.items():
        conn.execute('insert into store_kv(key,value) values(%s,%s) on conflict(key) do update set value=excluded.value,updated=now()',
                     (key,json.dumps(value)))
    legacy=dict(conn.execute('select key,value from store_kv').fetchall())
    if legacy!=doc: raise ValueError('legacy rollback projection mismatch')
    return {'ok':True,'documents':len(doc),'projectionChecksum':ms.digest(doc),'activationChanged':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('backup','restore','rollback-rehearsal'))
    parser.add_argument('--schema',required=True)
    parser.add_argument('--file',type=Path)
    args=parser.parse_args()
    if not re.fullmatch(r'test_[a-z0-9_]+',args.schema): parser.error('exact test_* schema required')
    import psycopg
    safety.validate_test_dsn(os.environ['KLEAL_MONETIZATION_TEST_DSN'])
    with psycopg.connect(os.environ['KLEAL_MONETIZATION_TEST_DSN'],options='-c search_path='+args.schema) as conn:
        guard(conn)
        if args.operation=='backup':
            if not args.file: parser.error('--file required')
            # Refuse replacing an existing backup.
            with args.file.open('x') as stream: json.dump(backup(conn),stream,ensure_ascii=False,indent=2)
            result={'ok':True,'backup':str(args.file)}
        elif args.operation=='restore':
            if not args.file: parser.error('--file required')
            result=restore(conn,json.loads(args.file.read_text()))
        else: result=canonical_to_legacy(conn)
    print(json.dumps(result))


if __name__=='__main__': main()
