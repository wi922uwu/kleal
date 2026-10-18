#!/usr/bin/env python3
"""Production migration protocol. Dry-run is read-only; import/export require an exact
snapshot digest and a durable DB fence. Never restores an old DB over current data.
Legacy services MUST be stopped by the release coordinator: old code can fall back
to JSON after a rejected DB write. The DB fence also rejects noncooperating writers.
"""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shared'))
import monetization_store as ms

OWNED=set('''_blocks _completion_confirms _evidence _exposure _gintents _ginvites
_gmsgs _gplans _gremovals _group_ledger _groups _gvotes _idem _identity _intents
_match_taken _matches _messages _mplans _names _outbox _outcome_seen _outcomes
_plan_store _premig_v2 _premig_v3 _proposal_by_id _proposal_store _proposals _reports
_requests _run_traces _thread_reads _trace _txn_seen _write_seen'''.split())
TERMINAL={'cancelled','done','expired','converted_1to1','closed_by_owner','locked','completed','closed'}
# Эти состояния встречи НЕ закрывают набор: gi_invite допускает приглашения
# во время planning/planned и below_quorum (пауза встречи, а не поиска).
# Новые участники проходят approval; только locked/terminal снимают search quota.
GROUP_STATES=TERMINAL|{'forming','searching','chat_open','ready_to_plan','ready','confirmed','proposed','active',
                       'below_quorum','planning','planned'}


def owned(key,users):
    return key in OWNED or key in users or key=='me' or key.startswith(('anon:','recovery:'))


def snapshot(conn,legacy_preview=None):
    # Caller chooses REPEATABLE READ or holds the fence/table locks.
    return {'users':[{'id':r[0],'row':r[1]} for r in conn.execute('select id,row from users order by id').fetchall()],
            'session':dict(conn.execute('select key,value from store_kv order by key').fetchall()),
            'legacy_preview':legacy_preview or {}}


def plan(data):
    users={r['id'] for r in data['users']}; doc=data['session']; issues=[]; resources={}; aliases={}; preserved={}
    if len(users)!=len(data['users']) or '' in users or any(x.startswith(('anon:','recovery:')) for x in users):
        issues.append('invalid users.id inventory')
    intent_rows={r.get('id'):r for r in doc.get('_intents',[])}
    live_groups={}
    def alias(kind,key,rid):
        a=kind+':'+key
        if a in aliases and aliases[a]!=rid: issues.append('ambiguous alias '+a)
        else: aliases[a]=rid
    for collection,field in (('_intents','owner_id'),('_gintents','owner'),('_groups','host')):
        ids=set()
        for row in doc.get(collection,[]):
            uid=row.get(field); ident=row.get('id')
            if not isinstance(ident,str) or not ident or ident in ids:
                issues.append('missing/duplicate id '+collection);continue
            ids.add(ident)
            state=row.get('state')
            if collection!='_intents' and state not in GROUP_STATES:
                issues.append('unknown lifecycle '+collection+':'+ident);continue
            active=bool(row.get('launched')) and row.get('status') not in TERMINAL|{'paused'} if collection=='_intents' else state not in TERMINAL
            if uid not in users:
                preserved.setdefault(collection,[]).append(ident)
                continue
            if collection=='_intents':
                rid='search_intent_'+ident
                resources[rid]={'owner':uid,'state':'active' if active else ('paused' if row.get('launched') else 'draft'),
                    'published':int(row.get('launched') or 0) or None,'payload':row}
                alias('intent',ident,rid);continue
            intent=row.get('intent') or {}
            refs={str(intent[k]) for k in ('_searchId','searchId','iid','id') if intent.get(k)}
            linked={aliases.get('intent:'+ref) for ref in refs}
            linked.discard(None)
            if refs and (len(linked)!=1 or any(ref not in intent_rows for ref in refs)):
                if active: issues.append('unresolved active search link '+collection+':'+ident)
                preserved.setdefault(collection,[]).append(ident);continue
            if linked:
                rid=next(iter(linked))
                if resources[rid]['owner']!=uid:
                    issues.append('foreign search link '+collection+':'+ident);continue
                # A historical group must not pause a current search with the same alias.
                if active and resources[rid]['state']!='active':
                    issues.append('active group/paused search '+collection+':'+ident)
            else:
                if active and any(r.get('owner_id')==uid and r.get('launched') and r.get('status') not in TERMINAL|{'paused'} for r in intent_rows.values()):
                    issues.append('active group/search requires explicit alias '+collection+':'+ident)
                rid='search_'+collection.strip('_')+'_'+ident
                resources[rid]={'owner':uid,'state':'active' if active else 'paused','published':int(row.get('created') or 0),'payload':row}
            alias('group',ident,rid)
            if active:
                if rid in live_groups: issues.append('multiple live groups for search '+rid)
                else: live_groups[rid]=(collection,ident)
            members=row.get('members',[])
            peers=[m.get('name') for m in members] if collection=='_gintents' else members+row.get('waitlist',[])
            if active and any(p not in users and not str(p).startswith('anon:') for p in peers):
                issues.append('unresolved active member '+collection+':'+ident)
    pairs={}
    for row in doc.get('_messages',[]):
        a,b=row.get('from'),row.get('to')
        if a not in users or b not in users or a==b: continue
        pair=ms.pair_key(a,b); entry=pairs.setdefault(pair,{'end':None,'human':None})
        syscode=row.get('sys');syscode=syscode.get('code') if isinstance(syscode,dict) else syscode
        if syscode=='chat_ended':
            entry['end']=max(entry['end'] or 0,float(row.get('ts') or row.get('t') or 0))
        elif not syscode and not row.get('admin'):
            entry['human']=max(entry['human'] or 0,float(row.get('ts') or row.get('t') or 0))
    sessions=[]
    for pair,entry in pairs.items():
        a,b=json.loads(pair)
        blocked=b in doc.get('_blocks',{}).get(a,[]) or a in doc.get('_blocks',{}).get(b,[])
        if entry['end'] is not None and entry['human']==entry['end']:
            issues.append('ambiguous chat lifecycle '+pair);continue
        closed=blocked or (entry['end'] is not None and (entry['human'] or 0)<entry['end'])
        sessions.append({'pair':pair,'state':'closed' if closed else 'active','closed':entry['end'] if closed else None})
    keys=sorted(k for k in doc if owned(k,users))
    pauses={}
    for uid in sorted(users):
        active=sorted((r for r in resources if resources[r]['owner']==uid and resources[r]['state']=='active'),
                      key=lambda r:(-(resources[r]['published'] or 0),r))
        if len(active)>1: pauses[uid]=active[1:]
    return {'ok':not issues,'issues':issues,'snapshotHash':ms.digest(data),'ownedKeys':keys,
            'externalKeys':sorted(set(doc)-set(keys)),'resources':resources,'aliases':aliases,
            'preserved':preserved,'sessions':sessions,'wouldPause':pauses}


FENCE_SQL="""
create or replace function monetization_legacy_fence() returns trigger language plpgsql as $$
declare state text; k text; old_key text;
begin
 select value #>> '{}' into state from monetization_meta where key='release_state';
 k := case when TG_OP='DELETE' then OLD.key else NEW.key end;
 old_key := case when TG_OP='UPDATE' then OLD.key else k end;
 if state in ('staged','enforce','rollback') and current_setting('kleal.release_writer',true) is distinct from 'on'
    and (k in (select key from monetization_owned_keys)
         or k in (select id from users) or k='me' or k like 'anon:%' or k like 'recovery:%'
         or old_key in (select key from monetization_owned_keys)
         or old_key in (select id from users) or old_key='me' or old_key like 'anon:%' or old_key like 'recovery:%') then
   raise exception 'monetization legacy writer fenced' using errcode='55000';
 end if;
 if TG_OP='DELETE' then return OLD; else return NEW; end if;
end $$;
drop trigger if exists monetization_legacy_fence on store_kv;
create trigger monetization_legacy_fence before insert or update or delete on store_kv
for each row execute function monetization_legacy_fence();
"""


def fence(conn):
    # Consistent order with canonical and manual writers; lock timeout is a hard stop.
    conn.execute("set local lock_timeout='10s'")
    ms.Transaction(conn).lock('monetization:projection')
    conn.execute('lock table users,store_kv,outbox in access exclusive mode')


def import_snapshot(conn,expected_hash,legacy_preview=None):
    fence(conn)
    data=snapshot(conn,legacy_preview); report=plan(data)
    if report['snapshotHash']!=expected_hash: raise ValueError('snapshot drift; no import')
    if not report['ok']: raise ValueError('; '.join(report['issues']))
    conn.execute(ms.SCHEMA)
    previous=conn.execute("select value from monetization_meta where key='production_import'").fetchone()
    if previous:
        if previous[0]!=expected_hash: raise ValueError('existing production import; never overwrite')
        return {'ok':True,'already':True,'snapshotHash':expected_hash}
    if conn.execute('select 1 from monetization_documents limit 1').fetchone() or conn.execute('select 1 from monetization_accounts limit 1').fetchone():
        raise ValueError('target is not empty')
    conn.execute('create table monetization_owned_keys(key text primary key)')
    for key in sorted(OWNED|set(report['ownedKeys'])):
        conn.execute('insert into monetization_owned_keys values(%s)',(key,))
    tx=ms.Transaction(conn)
    for person in data['users']:
        uid=person['id']; tx.account(uid)
        provenance={'migration':'production-v1','snapshotHash':expected_hash,'legacyStatusOnly':data['legacy_preview'].get(uid)}
        conn.execute('update monetization_accounts set eligibility_provenance=%s where owner_id=%s',(json.dumps(provenance),uid))
        tx.audit(uid,'preview_eligibility_migrated',provenance)
    for rid,r in report['resources'].items():
        conn.execute('insert into monetization_resources(id,owner_id,state,published,payload) values(%s,%s,%s,%s,%s)',
                     (rid,r['owner'],r['state'],r['published'],json.dumps(r['payload'])))
    for alias,rid in report['aliases'].items():
        kind,key=alias.split(':',1);tx.alias(kind,key,rid)
    for session in report['sessions']:
        conn.execute('insert into monetization_sessions(id,pair,state,opened,closed,protected,provenance) '
                     'values(%s,%s,%s,%s,%s,true,%s)',(ms.new_id('session_'),session['pair'],session['state'],tx.now,
                     session['closed'],json.dumps({'migration':'production-v1','initiator':'unknown'})))
    legacy_owned_hash=ms.digest({k:data['session'][k] for k in report['ownedKeys']})
    doc={k:data['session'][k] for k in report['ownedKeys']}
    for key,ids in report['preserved'].items():
        for row in doc.get(key,[]):
            if row.get('id') in ids: row['searchState']='paused'
    tx.save_documents(doc)
    for collection,kind in (('_requests','invite'),('_ginvites','group_invite')):
        for row in doc.get(collection,[]):
            if row.get('id'): tx.protect(kind,row['id'],'accept',{'migration':'production-v1','snapshotHash':expected_hash})
    for key,value in {'production_import':expected_hash,'release_state':'staged','ready':True,
                      'preserved':report['preserved'],'legacy_owned_hash':legacy_owned_hash}.items():
        conn.execute('insert into monetization_meta values(%s,%s)',(key,json.dumps(value)))
    conn.execute(FENCE_SQL)
    return {'ok':True,'snapshotHash':expected_hash,'state':'staged','wouldPause':report['wouldPause']}


def activate(conn):
    fence(conn)
    row=conn.execute("select value from monetization_meta where key='release_state'").fetchone()
    if not row or row[0]!='staged': raise ValueError('activation requires staged import')
    tx=ms.Transaction(conn)
    for (owner,) in conn.execute('select owner_id from monetization_accounts order by owner_id').fetchall(): tx.expire(owner)
    conn.execute("update monetization_meta set value='\"enforce\"' where key='release_state'")
    return {'ok':True,'state':'enforce'}


def export_legacy(conn,apply=False):
    """Export CURRENT canonical state only. Foreign keys and users never get overwritten."""
    fence(conn)
    state=conn.execute("select value from monetization_meta where key='release_state'").fetchone()
    if not state or state[0] not in ('enforce','staged'): raise ValueError('no active production import')
    tx=ms.Transaction(conn); doc=tx.documents()
    keys={r[0] for r in conn.execute('select key from monetization_owned_keys').fetchall()}
    users={r[0] for r in conn.execute('select id from users').fetchall()}
    if any(not (k in keys or owned(k,users)) for k in doc): raise ValueError('unowned canonical key')
    current=dict(conn.execute('select key,value from store_kv').fetchall())
    original={k:current[k] for k in current if k in keys}
    expected=conn.execute("select value from monetization_meta where key='legacy_owned_hash'").fetchone()[0]
    if ms.digest(original)!=expected: raise ValueError('legacy data changed while enforce; reconcile before rollback')
    if apply:
        for (owner,) in conn.execute('select owner_id from monetization_accounts where owner_id not in '
                                     '(select owner_id from monetization_deletions) order by owner_id').fetchall():
            tx.expire(owner)
    for key,kind in (('_intents','intent'),('_gintents','group'),('_groups','group')):
        for row in doc.get(key,[]):
            rid=tx.resolve(kind,row.get('id'))
            if not rid: continue
            r=tx.resource(rid);row.update(searchId=rid,searchState=r['state'])
            if key=='_intents': row['status']='active' if r['state']=='active' else 'paused'
    foreign={k:v for k,v in current.items() if k not in keys and not owned(k,users)}
    result={'ok':True,'dryRun':not apply,'projectionHash':ms.digest(doc),'foreignHash':ms.digest(foreign),'keys':sorted(doc)}
    if not apply: return result
    conn.execute("select set_config('kleal.release_writer','on',true)")
    for key in keys-set(doc): conn.execute('delete from store_kv where key=%s',(key,))
    for key,value in doc.items():
        conn.execute('insert into store_kv(key,value) values(%s,%s) on conflict(key) do update set value=excluded.value,updated=now()',
                     (key,json.dumps(value)))
    actual=dict(conn.execute('select key,value from store_kv').fetchall())
    if any(actual.get(k)!=v for k,v in doc.items()) or any(actual.get(k)!=v for k,v in foreign.items()):
        raise ValueError('rollback verification failed')
    conn.execute("update monetization_meta set value='\"legacy\"' where key='release_state'")
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',choices=('dry-run','import','export'))
    p.add_argument('--expected-hash');p.add_argument('--apply',action='store_true')
    p.add_argument('--legacy-preview',type=Path)
    a=p.parse_args();import psycopg
    legacy=json.loads(a.legacy_preview.read_text()) if a.legacy_preview else {}
    with psycopg.connect(os.environ['KLEAL_PG_DSN']) as conn:
        if a.operation=='dry-run' or (a.operation=='import' and not a.apply):
            conn.execute('set transaction isolation level repeatable read read only')
            report=plan(snapshot(conn,legacy));result={k:v for k,v in report.items() if k not in ('resources','sessions','aliases')}
        elif a.operation=='import':
            if not a.expected_hash: p.error('--expected-hash is required')
            sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
            from monetization_release import require_stopped
            require_stopped()
            result=import_snapshot(conn,a.expected_hash,legacy)
        else:
            if a.apply:
                sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
                from monetization_release import require_stopped
                require_stopped()
            result=export_legacy(conn,a.apply)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
