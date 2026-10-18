#!/usr/bin/env python3
"""Explicit synthetic-only Phase 2A migration. No service import calls this tool.

Default is a dry run. --apply requires the fixture's synthetic marker and an
explicit loopback database DSN with a database name starting kleal_monetization_test
and --schema selecting an already-created isolated test_* schema. Production
migration uses the separate monetization_production.py tool, never this CLI.
"""
import argparse
import json
import os
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'shared'))
import monetization_store as ms
import monetization_safety as safety


def validate_fixture(data):
    issues = []
    if data.get('synthetic') is not True:
        issues.append('synthetic marker required')
    owners = {str(x.get('id','')) for x in data.get('users', [])}
    if '' in owners or len(owners) != len(data.get('users', [])):
        issues.append('missing or duplicate users.id')
    session = data.get('session') or {}
    intents = {r.get('id'): r for r in session.get('_intents', [])}
    for key in ('_intents','_gintents','_groups','_requests','_ginvites','_mplans','_gplans'):
        rows=session.get(key,[])
        ids=[r.get('id') for r in rows]
        if any(not x for x in ids) or len(ids)!=len(set(ids)):
            issues.append('missing or duplicate resource id: '+key)
    for r in intents.values():
        if r.get('owner_id') not in owners:
            issues.append('unresolved intent owner: ' + str(r.get('id')))
    for key, field in (('_gintents','owner'),('_groups','host')):
        for r in session.get(key,[]):
            if r.get(field) not in owners:
                issues.append('unresolved group owner: ' + str(r.get('id')))
            ref = (r.get('intent') or {}).get('_searchId') or (r.get('intent') or {}).get('iid')
            if ref and (ref not in intents or intents[ref].get('owner_id') != r.get(field)):
                issues.append('unresolved search link: ' + str(r.get('id')))
            if not ref and any(i.get('owner_id') == r.get(field) for i in intents.values()):
                issues.append('group/search alias requires explicit review: ' + str(r.get('id')))
    for key, fields in (('_messages',('from','to')),('_requests',('from','to')),('_ginvites',('frm','to')),('_mplans',('host','guest'))):
        for r in session.get(key,[]):
            if any(r.get(f) not in owners for f in fields):
                issues.append('unresolved identity: ' + str(r.get('id')))
    for r in session.get('_gintents',[]):
        if any(m.get('name') not in owners for m in r.get('members',[])):
            issues.append('unresolved group member: '+str(r.get('id')))
    for r in session.get('_groups',[]):
        if any(m not in owners for m in (r.get('members',[])+r.get('waitlist',[]))):
            issues.append('unresolved legacy group member: '+str(r.get('id')))
    return issues


def migrate(conn, data):
    issues = validate_fixture(data)
    if issues:
        raise ValueError('; '.join(issues))
    safety.guard(conn)
    conn.execute(ms.SCHEMA)
    # Outbox belongs to shared/db; schema provisioning is an explicit operation here.
    conn.execute(ms.db.SCHEMA)
    tx = ms.Transaction(conn)
    tx.lock('monetization:projection')
    existed = conn.execute("select value from monetization_meta where key='fixture_hash'").fetchone()
    fingerprint = ms.digest(data)
    if existed:
        if existed[0] != fingerprint:
            raise ValueError('database already contains a different migration; never overwrite it')
        return {'ok':True,'already':True}
    session = data.get('session') or {}
    for person in data.get('users',[]):
        owner = person['id']
        tx.account(owner)
        legacy = (data.get('legacy_preview') or {}).get(owner)
        provenance = {'migration':'phase2a','legacyStatusOnly':legacy,'synthetic':True}
        conn.execute('update monetization_accounts set eligibility_provenance=%s where owner_id=%s',
                     (json.dumps(provenance),owner))
        tx.audit(owner,'preview_eligibility_migrated',provenance)
    for r in session.get('_intents',[]):
        rid = 'search_' + str(r['id'])
        conn.execute('insert into monetization_resources(id,owner_id,state,published,payload) values(%s,%s,%s,%s,%s)',
                     (rid,r['owner_id'],'active' if r.get('launched') else 'draft',
                      int(r.get('launched') or 0) or None,json.dumps(r)))
        tx.alias('intent',r['id'],rid)
    for key, field in (('_gintents','owner'),('_groups','host')):
        for r in session.get(key,[]):
            ref = (r.get('intent') or {}).get('_searchId') or (r.get('intent') or {}).get('iid')
            rid = tx.resolve('intent',ref) if ref else None
            if not rid:
                rid = 'search_' + str(r['id'])
                active = r.get('state') not in ('cancelled','done','expired','converted_1to1','closed_by_owner','locked')
                conn.execute('insert into monetization_resources(id,owner_id,state,published,payload) values(%s,%s,%s,%s,%s)',
                             (rid,r[field],'active' if active else 'paused',int(r.get('created') or 0),json.dumps(r)))
            tx.alias('group',r['id'],rid)
    for key, kind in (('_requests','invite'),('_ginvites','group_invite')):
        for r in session.get(key,[]):
            tx.protect(kind,r['id'],'accept',{'migration':'phase2a','state':r.get('status') or r.get('state')})
    # Truncated histories cannot establish an initiator. Preserve the pair explicitly.
    for r in session.get('_messages',[]):
        pair = ms.pair_key(r['from'],r['to'])
        if conn.execute("select 1 from monetization_sessions where pair=%s and state='active'",(pair,)).fetchone():
            continue
        conn.execute('insert into monetization_sessions(id,pair,state,opened,protected,provenance) '
                     "values(%s,%s,'active',%s,true,%s)",
                     (ms.new_id('session_'),pair,tx.now,json.dumps({'migration':'phase2a','initiator':'unknown'})))
    for p in session.get('_mplans',[]):
        # Closed historical plans cannot be assigned to a current conversation by
        # matching its pair: that could release an unrelated, later quota session.
        if p.get('state') not in ('cancelled','done','expired','closed_by_owner','converted_1to1'):
            tx.link_plan(p['id'],p['host'],p['guest'])
    tx.save_documents(session)
    conn.execute("insert into monetization_meta values('fixture_hash',%s)",(json.dumps(fingerprint),))
    conn.execute("insert into monetization_meta values('ready','true') on conflict(key) do update set value='true'")
    return {'ok':True,'accounts':len(data.get('users',[])),'documents':len(session)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixture',type=Path)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--schema',help='existing isolated test_* schema; required for --apply')
    args = parser.parse_args()
    if (args.apply or args.schema is not None) and not re.fullmatch(r'test_[a-z0-9_]+',args.schema or ''):
        parser.error('--apply requires an explicit existing test_* schema via --schema')
    data = json.loads(args.fixture.read_text())
    issues = validate_fixture(data)
    if not args.apply:
        print(json.dumps({'ok':not issues,'dryRun':True,'issues':issues},ensure_ascii=False))
        return 1 if issues else 0
    safety.validate_test_dsn(os.environ.get('KLEAL_PG_DSN',''))
    import psycopg
    with psycopg.connect(os.environ['KLEAL_PG_DSN'],options='-c search_path='+args.schema) as conn:
        result = migrate(conn,data)
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
