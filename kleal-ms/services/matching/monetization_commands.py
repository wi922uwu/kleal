"""Canonical transaction adapter for the existing matching state machines.

The legacy code still enforces consent, identity, safety and capacity. Its SESSION
is a projection loaded under one database lock, never a second durable writer.
Ranking runs after publication commits, so an external call holds no quota lock.
"""
import copy
import contextlib
from collections.abc import MutableMapping
import functools
import hashlib
import inspect
import json
import os
import re
import threading
import time
import uuid

import monetization_store as ms
import monetization_admin

_local = threading.local()
_app = None

# Explicit supported writers; unadapted scaffold paths fail closed below.
WRITERS = '''save_intent delete_intent propose respond pick_request withdraw_request archive_request
send_message end_thread message_react message_delete thread_mark_read block_user report_user
gi_create gi_invite gi_invite_many gi_respond gi_invite_cancel gi_close gi_report gi_approve gi_remove
gi_takeover gi_takeover_vote gi_takeover_withdraw gi_takeover_back gi_role_offer gi_role_respond gi_role_withdraw
gi_convert_ask gi_convert_respond gi_leave gi_post gmsg_react gmsg_delete
gp_hold_answer gp_begin gp_respond gp_cancel gp_fix gp_vote_open gp_vote gp_update gp_link gp_details
gp_mode gp_side gp_vote_decide gp_vote_close gp_status gp_feedback mp_side mp_propose mp_respond
mp_address mp_ask mp_cancel mp_move_to_call mp_status mp_feedback group_create group_join group_leave group_recover
_gp_sweep _mp_sweep _gi_roles_due _gi_expire _expire_due inbox outbox
_gp_postcall_due report_evidence_store admin_notify admin_ban_sweep reset_fatigue purge_person _migrate_engine_ids_v3'''.split()
UNADAPTED = '''proposal_create proposal_respond plan_resource plan_transition form_group_from_slate
group_reserve group_accept group_release agent_transition confirm_completion _append_run_trace
_save_search _delete_saved_search _migrate_identity_v2'''.split()
TRANSACTION_ONLY = '_log_proposal _log_exposure _idempotent record_feedback _record_outcome'.split()
READ_PROJECTIONS = '_check_saved_searches _ensure_intent_owner_ids'.split()
TERMINAL = {'done','cancelled','expired','closed_by_owner','converted_1to1'}
PASSIVE = set('inbox outbox _gp_sweep _mp_sweep _gi_roles_due _gi_expire _expire_due _gp_postcall_due _migrate_engine_ids_v3'.split())


class SessionProjection(MutableMapping):
    """Legacy helpers see the calling thread's document, never another transaction's edits."""
    def __init__(self, committed): self.committed = committed
    def current(self): return getattr(_local, 'document', None) if getattr(_local, 'document', None) is not None else self.committed
    def __getitem__(self, key): return self.current()[key]
    def __setitem__(self, key, value): self.current()[key] = value
    def __delitem__(self, key): del self.current()[key]
    def __iter__(self): return iter(self.current())
    def __len__(self): return len(self.current())
    def __deepcopy__(self, memo): return copy.deepcopy(self.current(), memo)


@contextlib.contextmanager
def projection(doc):
    previous = getattr(_local, 'document', None)
    _local.document = doc
    try: yield doc
    finally: _local.document = previous


def ranking_pool():
    return getattr(_local,'ranking_pool',None)


@contextlib.contextmanager
def pool_projection(pool):
    previous=ranking_pool()
    _local.ranking_pool=pool
    try: yield
    finally: _local.ranking_pool=previous


def read_snapshot():
    try:
        return _read_snapshot()
    except ms.CommandError:
        raise
    except Exception as error:
        raise ms.CommandError('monetization_unavailable',503) from error


def _read_snapshot():
    """One committed MVCC snapshot; no writer/advisory lock while reading or ranking.

    Effective expiry is projected without persisting it. The next canonical writer
    performs the same reconciliation atomically before any gated mutation.
    """
    with ms.connection() as conn, conn.transaction():
        conn.execute('set transaction isolation level repeatable read read only')
        ms.bounded_transaction(conn)
        ready = conn.execute("select value from monetization_meta where key='ready'").fetchone()
        release = conn.execute("select value from monetization_meta where key='release_state'").fetchone()
        if not ready or ready[0] is not True: raise ms.CommandError('monetization_migration_required',503)
        if release and release[0]!='enforce': raise ms.CommandError('monetization_release_fenced',503)
        tx = ms.Transaction(conn)
        doc = tx.documents()
        resources = ms.projection_resources(tx)
        aliases = {(kind,alias):rid for kind,alias,rid in conn.execute('select kind,alias,resource_id from monetization_aliases').fetchall()}
        for key,kind in (('_intents','intent'),('_groups','group'),('_gintents','group')):
            for row in doc.get(key,[]):
                rid = aliases.get((kind,str(row.get('id'))))
                if rid not in resources: continue
                row.update(searchId=rid,searchState=resources[rid]['state'])
                if key=='_intents': row['status']=resources[rid]['state']
                if isinstance(row.get('intent'),dict): row['intent']['_searchId']=rid
        return doc


def publish_projection(doc):
    # Caller holds the short in-process adapter lock; only committed snapshots get here.
    _app['SESSION'].committed = copy.deepcopy(doc)
    if getattr(_local, 'request', False): _local.document = copy.deepcopy(doc)


def active_tx():
    return getattr(_local,'tx',None)


def role_available(group,new_owner):
    """Automatic role checks must not turn a read or a safety exit into a paywall."""
    tx=active_tx()
    if not tx or ms.mode()!='enforce': return True
    if tx.conn.execute('select 1 from monetization_deletions where owner_id=%s',(new_owner,)).fetchone():
        return False
    rid=tx.resolve('group',group.get('id'))
    if not rid or tx.resource(rid)['state']!='active': return True
    try:
        tx.check_search(new_owner,rid)
        return True
    except ms.CommandError as e:
        if e.code!='search_quota': raise
        return False


def _rows(doc,key):
    return {str(r['id']):r for r in doc.get(key,[]) if isinstance(r,dict) and r.get('id')}


def _owner(row, field):
    owner = str(row.get(field) or '')
    if owner.startswith('recovery:') and row.get('role_recovery'):
        return owner
    # Identity storage, not display names, defines the subject of every entitlement.
    if not owner or not _app['_people_index']()['by_id'].get(owner):
        raise ms.CommandError('unresolved_identity',503)
    return owner


def _resource_ref(tx,intent,owner):
    raw = intent.get('_searchId') or intent.get('searchId') or intent.get('iid') or intent.get('id')
    if not raw:
        return None
    rid = tx.resolve('intent',raw)
    if not rid and str(raw).startswith('search_'):
        rid = raw
    if rid:
        tx.resource(rid,owner)
    return rid


def _require_active(tx,rid,owner):
    tx.expire(owner)
    if not rid:
        raise ms.CommandError('search_reference_required',409)
    if tx.resource(rid,owner)['state'] != 'active':
        raise ms.CommandError('search_paused',409,resourceId=rid)


def _reply_intent(tx,intent,recipient):
    """A map response applies to the recipient's publication; it never publishes for the sender."""
    if not isinstance(intent,dict) or not (intent.get('targetSearchId') or intent.get('targetIntentId')):
        return intent
    for key in ('targetSearchId','targetIntentId'):
        if key in intent and (not isinstance(intent[key],str) or not intent[key] or len(intent[key])>160):
            raise ms.CommandError('invalid_search_reference',400)
    alias=intent.get('targetIntentId')
    linked=(tx.resolve('intent',alias) or tx.resolve('group',alias)) if alias else None
    rid=intent.get('targetSearchId') or linked
    if alias and rid and linked!=rid:
        raise ms.CommandError('search_reference_mismatch',409)
    _require_active(tx,rid,recipient)
    resource=tx.resource(rid,recipient)
    source=resource['payload']
    # Copy only the public projection, never the client's title/topics or the author's
    # private Buddy text/link. Search IDs are deliberately not copied into own-search fields.
    public=_app['imf'].public_intent(source.get('intent') or {},record=source)
    public['title']=str(source.get('title') or public.get('title') or '')[:160]
    public['targetSearchId']=rid
    if alias: public['targetIntentId']=alias
    return public


def proposal_intent(tx,intent,owner,recipient):
    if intent.get('targetSearchId') or intent.get('targetIntentId'):
        return _reply_intent(tx,intent,recipient)
    rid=_resource_ref(tx,intent,owner)
    _require_active(tx,rid,owner)
    source=tx.resource(rid,owner)['payload']
    canonical=source.get('intent')
    if not isinstance(canonical,dict): raise ms.CommandError('search_payload_unavailable',409)
    # IDs identify the resource; they do not authorize replacing its content at
    # invitation time. Compare provided fields, then use only canonical content.
    transport={'id','iid','_searchId','searchId'}
    for field,value in intent.items():
        if field not in transport and canonical.get(field)!=value:
            raise ms.CommandError('search_content_conflict',409)
    result=copy.deepcopy(canonical)
    result.update({k:v for k,v in intent.items() if k in transport})
    result['_searchId']=rid
    return result


def _project(tx,doc):
    resources=ms.projection_resources(tx,persist=True)
    aliases={(kind,alias):rid for kind,alias,rid in tx.conn.execute('select kind,alias,resource_id from monetization_aliases')}
    for key,kind in (('_intents','intent'),('_gintents','group'),('_groups','group')):
        for row in doc.get(key,[]):
            rid = aliases.get((kind,str(row.get('id'))))
            if rid in resources:
                r = resources[rid]
                row['searchId'],row['searchState'] = rid,r['state']
                if isinstance(row.get('intent'),dict):
                    row['intent']['_searchId'] = rid
                # Do not overwrite the group state machine or the historical launch time.
                if key == '_intents':
                    row['status'] = r['state']
    return doc


def _reconcile(tx,before,after,action,args,*,deleting_owner=None):
    # Both writers and cleanup hold the projection lock at this boundary.
    for kind,name in media_references(after)-media_references(before):
        folder={'voice':_app['VOICE_DIR'],'video':_app['VIDEO_DIR'],'evidence':_app['EVIDENCE_DIR']}[kind]
        if not os.path.isfile(os.path.join(folder,name)):
            raise ms.CommandError('media_not_found',409)
    historical=tx.conn.execute("select value from monetization_meta where key='preserved'").fetchone()
    preserved=historical[0] if historical else {}
    group_aliases = dict(tx.conn.execute("select alias,resource_id from monetization_aliases where kind='group'").fetchall())
    def other_live_groups(rid,gid):
        return [g for box in ('_groups','_gintents') for g in after.get(box,[])
                if g.get('id') != gid and group_aliases.get(g.get('id')) == rid and g.get('state') not in TERMINAL]
    prior_intents=_rows(before,'_intents')
    for r in after.get('_intents',[]):
        old = prior_intents.get(r.get('id'))
        if old==r: continue
        if r.get('id') in preserved.get('_intents',[]): continue
        owner = _owner(r,'owner_id')
        rid = tx.resolve('intent',r['id'])
        if rid and tx.resource(rid)['state']=='deleted': raise ms.CommandError('search_deleted',410)
        if not rid:
            if r.get('launched'):
                rid = tx.publish(owner,r)
            else:
                rid = ms.new_id('search_')
                tx.conn.execute("insert into monetization_resources(id,owner_id,state,payload) values(%s,%s,'draft',%s)",
                                (rid,owner,json.dumps(r)))
            tx.alias('intent',r['id'],rid)
        elif r.get('launched') and (not old or r.get('launched') != old.get('launched')):
            tx.publish(owner,r,rid)
        else:
            source = tx.resource(rid)['payload']
            # A synthesized intent is a projection of a group-owned resource.
            # Its next sweep must not erase the original group/capacity metadata.
            if not (source.get('id') and tx.resolve('group',source['id'])==rid):
                tx.conn.execute('update monetization_resources set payload=%s where id=%s',(json.dumps(r),rid))
    deleted = set(_rows(before,'_intents'))-set(_rows(after,'_intents'))
    for iid in deleted:
        rid = tx.resolve('intent',iid)
        if rid:
            owner=_rows(before,'_intents')[iid]['owner_id']
            # В deletion path ресурс может ещё принадлежать живой группе.
            # Не вызываем обычный entitlement API для tombstoned владельца и
            # не ставим ресурс на паузу до quota-aware передачи организатора.
            if owner!=deleting_owner:
                aliases={r[0] for r in tx.conn.execute("select alias from monetization_aliases where kind='group' and resource_id=%s",(rid,))}
                live_group=any(g.get('id') in aliases and g.get('state') not in TERMINAL
                               for box in ('_groups','_gintents') for g in after.get(box,[]))
                if not live_group: tx.delete_search(owner,rid)
    for key,owner_field in (('_gintents','owner'),('_groups','host')):
        old_rows = _rows(before,key)
        for r in after.get(key,[]):
            old = old_rows.get(r.get('id')) or {}
            if old==r: continue
            if r.get('id') in preserved.get(key,[]): continue
            rid = tx.resolve('group',r['id'])
            if r.get('role_recovery') and not r.get(owner_field) and rid:
                if other_live_groups(rid,r['id']):
                    if r.get('state') not in TERMINAL: raise ms.CommandError('search_group_conflict',409)
                    continue
                owner='recovery:'+r['id']
                if key=='_groups' and not old.get('role_recovery'):
                    r['recovery_search_active']=tx.resource(rid)['state']=='active'
                tx.conn.execute("update monetization_resources set state='paused',owner_id=%s where id=%s",(owner,rid))
                if deleting_owner and old.get(owner_field)==deleting_owner:
                    tx.conn.execute('update monetization_resources set payload=%s where id=%s',(json.dumps(r),rid))
                for saved in after.get('_intents',[]):
                    if tx.resolve('intent',saved.get('id'))==rid:
                        saved.update(owner_id=owner,owner='',role_recovery=True)
                continue
            owner = _owner(r,owner_field)
            if not rid:
                rid = _resource_ref(tx,r.get('intent') or {},owner)
                if rid:
                    _require_active(tx,rid,owner)
                    if other_live_groups(rid,r['id']): raise ms.CommandError('search_group_conflict',409)
                else:
                    rid = tx.publish(owner,r)
                tx.alias('group',r['id'],rid)
                group_aliases[r['id']] = rid
            # A terminal historical alias may remain for old plans/history, but
            # only the one live group controls this search's pause and ownership.
            others = other_live_groups(rid,r['id'])
            if others:
                if r.get('state') not in TERMINAL: raise ms.CommandError('search_group_conflict',409)
                continue
            if key=='_groups' and action=='group_join':
                # Existing waitlist admission is protected; a new join/request is recruitment.
                person=args.get('who')
                if person not in (old.get('members') or []) and person not in (old.get('waitlist') or []):
                    _require_active(tx,rid,owner)
            if old and old.get(owner_field) != owner:
                if key=='_groups' and old.get('role_recovery') and old.get('recovery_search_active',old.get('role_transfer_blocked')=='organizer_search_quota'):
                    # Explicit recovery restores the same recruitment only after
                    # the recipient passes quota; rollback preserves the vacancy.
                    tx.check_search(owner,rid)
                    tx.conn.execute("update monetization_resources set state='active' where id=%s",(rid,))
                r.pop('recovery_search_active',None)
                tx.transfer(rid,tx.resource(rid)['owner_id'],owner)
                if deleting_owner and old.get(owner_field)==deleting_owner:
                    tx.conn.execute('update monetization_resources set payload=%s where id=%s',(json.dumps(r),rid))
                for saved in after.get('_intents',[]):
                    if tx.resolve('intent',saved.get('id'))==rid:
                        saved.update(owner_id=owner,owner=_app['_display'](owner,owner))
                        saved.pop('role_recovery',None)
            if (r.get('state') in TERMINAL or r.get('state') == 'locked') and r.get('state') != old.get('state'):
                tx.pause(owner,rid)
            if tx.resource(rid)['payload'].get('id') == r['id']:
                tx.conn.execute('update monetization_resources set payload=%s where id=%s',(json.dumps(r),rid))
            # Membership deltas, including legacy waitlist promotion, are real admission.
            def members(row):
                if key=='_groups':
                    return set(row.get('members') or [])
                return {m.get('name') for m in row.get('members',[]) if m.get('state') in ('joined','active')}
            for person in members(r)-members(old):
                if person and person != owner:
                    tx.grant(_owner({'id':person},'id'),{'action':'joined','groupId':r['id']})
    for key,kind,owner_field in (('_requests','invite','from'),('_ginvites','group_invite','frm')):
        old_rows = _rows(before,key)
        for r in after.get(key,[]):
            old = old_rows.get(r['id'])
            if old==r: continue
            state = r.get('status') or r.get('state')
            if not old or (state in ('pending','sent') and r.get('updated') != old.get('updated')):
                intent=r.get('intent') or {}
                reply=key=='_requests' and bool(intent.get('targetSearchId'))
                owner = _owner(r,'to' if reply else owner_field)
                rid = (intent['targetSearchId'] if reply else tx.resolve('group',r.get('gid'))
                       if key=='_ginvites' else _resource_ref(tx,intent,owner))
                # Group -> 1:1 conversion is an existing obligation, scoped to that created request.
                conversion = action in ('gi_convert_respond','gp_hold_answer') and state=='accepted'
                if not conversion:
                    _require_active(tx,rid,owner)
                provenance={'action':action,'searchId':rid,'conversion':conversion,
                            'reply':reply,'searchOwnerId':owner}
                if old and key=='_requests':
                    # A re-sent pending pair can change its intent/direction. Protect the
                    # newly validated target, not the obsolete own-search provenance.
                    tx.conn.execute("update monetization_protected set provenance=%s where kind=%s and resource_id=%s and action='accept'",
                                    (json.dumps(provenance),kind,r['id']))
                tx.protect(kind,r['id'],'accept',provenance)
            if state=='accepted' and (not old or (old.get('status') or old.get('state'))!='accepted'):
                tx.grant(_owner(r,'to'),{'action':'accepted','inviteId':r['id']})
    old_messages = _rows(before,'_messages')
    for m in after.get('_messages',[]):
        if m.get('id') in old_messages or m.get('sys') or m.get('admin'):
            continue
        owner,peer = _owner(m,'from'),_owner(m,'to')
        # Исключение новой сессии — общение по ещё действующему плану. Исторический
        # confirmed после MP_KEEP_AFTER не даёт вечного обхода после явного end.
        current_plan = _app['_mp_of'](owner,peer)
        plans = [current_plan] if current_plan else []
        tx.message(owner,peer,protected=bool(plans),provenance={'planIds':[p['id'] for p in plans]})
        for p in plans:
            tx.link_plan(p['id'],owner,peer)
    if action=='end_thread':
        tx.end_pair(args['who'],args['other'],'end_chat')
    # Reports can call block_user inside the outer canonical transaction. Observe
    # actual newly blocked pairs, not the name of the outer endpoint. Unblock and
    # unchanged/replayed blocks are not new lifecycle events.
    for owner,peers in (after.get('_blocks') or {}).items():
        for peer in set(peers or [])-set((before.get('_blocks') or {}).get(owner) or []):
            tx.end_pair(owner,peer,'block')
    previous_plans=_rows(before,'_mplans')
    for p in after.get('_mplans',[]):
        # Отмена, окончание, timeout и feedback плана сохраняют сессию и её квоту.
        # Старый план также не привязываем к позднее открытой сессии по одной паре.
        if previous_plans.get(p.get('id'))!=p and p.get('state') not in TERMINAL and _app['_mp_of'](p['host'],p['guest']) is p:
            tx.link_plan(p['id'],p['host'],p['guest'])
    _project(tx,after)


def queue_cleanup(kind,name):
    if kind not in ('voice','video','evidence') or not re.fullmatch(r'[0-9a-f]{8,64}\.[a-z0-9]{2,5}',name):
        return
    ms.db.outbox_put('monetization.media.cleanup',{'kind':kind,'name':name},conn=active_tx().conn)


def media_references(value):
    refs=set()
    def visit(item):
        if isinstance(item,dict):
            for key,child in item.items():
                if key=='file' and isinstance(child,str) and re.fullmatch(r'[0-9a-f]{8,64}\.[a-z0-9]{2,5}',child):
                    refs.add(('evidence',child))
                visit(child)
        elif isinstance(item,list):
            for child in item: visit(child)
        elif isinstance(item,str):
            match=re.fullmatch(r'/api/(speech/audio|agent/voice|agent/video)/([0-9a-f]{8,64}\.[a-z0-9]{2,5})',item)
            if match: refs.add(('video' if match[1]=='agent/video' else 'voice',match[2]))
    visit(value)
    return refs


def purge_canonical(tx,before,after,owner):
    """Exact account cleanup; other people's reports remain their own records."""
    for key,kind in (('_requests','invite'),('_ginvites','group_invite')):
        ids=list(set(_rows(before,key))-set(_rows(after,key)))
        tx.conn.execute('delete from monetization_protected where kind=%s and resource_id=any(%s)',(kind,ids))
    tx.conn.execute('delete from monetization_plan_sessions where session_id in '
                    ' (select id from monetization_sessions where pair::jsonb ? %s)',(owner,))
    tx.conn.execute('delete from monetization_sessions where pair::jsonb ? %s',(owner,))
    removed_intents=[iid for iid,row in _rows(before,'_intents').items()
                     if row.get('owner_id')==owner and iid not in _rows(after,'_intents')]
    tx.conn.execute("delete from monetization_aliases where kind='intent' and alias=any(%s)",(removed_intents,))
    tx.conn.execute('delete from monetization_aliases where resource_id in '
                    '(select id from monetization_resources where owner_id=%s)',(owner,))
    tx.conn.execute('delete from monetization_resources where owner_id=%s',(owner,))
    tx.conn.execute('delete from monetization_commands where owner_id=%s',(owner,))
    # Keep the payload hash/key fence, but discard personal snapshots in somebody
    # else's cached response. These are server-defined identity fields, not a text
    # substring search (reports and unrelated commands must survive).
    identity_fields = {'owner','owner_id','ownerId','host','host_id','guest','guest_id','frm','frm_id',
                       'from','from_id','to','to_id','who','who_id','peerId','person_id','user_id','initiator'}
    person_lists = {'members','departed','participants','candidates','awaiting_approval','waitlist'}
    def refers(value, context=''):
        if isinstance(value,dict):
            return any((k in identity_fields or (context in person_lists
                        and (k=='id' or k=='name' and context!='candidates')
                        and value.get('kind') not in ('group','event','room','online_room','alternative_solution_type'))) and v==owner
                       or refers(v,k if k in person_lists else '') for k,v in value.items())
        if isinstance(value,list):
            return any((context in person_lists and v==owner) or refers(v,context) for v in value)
        return False
    # GIN jsonb_ops supports recursive jsonpath equality. Select only receipts
    # containing this exact scalar ID, including pre-index/imported receipts;
    # the structural check below rejects unrelated free text with the same value.
    subject_path='$.** ? (@ == '+json.dumps(owner)+')'
    for subject,action,key,result in tx.conn.execute('select owner_id,action,command_key,result from monetization_commands '
                                                   'where result @? %s::jsonpath',(subject_path,)):
        if refers(result):
            tx.conn.execute('update monetization_commands set result=%s where owner_id=%s and action=%s and command_key=%s',
                            (json.dumps({'ok':True,'redacted':True,'reason':'account_deleted'}),subject,action,key))
    tx.conn.execute('delete from monetization_audit where owner_id=%s',(owner,))
    tx.conn.execute('delete from monetization_accounts where owner_id=%s',(owner,))
    tx.conn.execute("delete from outbox where topic='monetization.search.launch' and payload->>'ownerId'=%s",(owner,))


def terminal_denial(before,after,name,args,result):
    """Commit only the exact safe terminal transition behind a known denial.

    Legacy functions also run sweeps. A denial must never bless their unrelated
    partial mutations or issue a Preview; copy just the addressed receipt state.
    """
    if name in ('gi_respond','gi_approve'):
        box,field='_ginvites','state'
        states={'NOT_ELIGIBLE':('policy_revoked',),'GROUP_FULL':('group_full',),'CLOSED':('withdrawn','group_closed')}
        rows=_rows(before,box)
        row=rows.get(str(args.get('inv_id'))) if name=='gi_respond' else next((r for r in rows.values()
            if r.get('gid')==args.get('gid') and r.get('to')==args.get('who') and r.get('state')=='awaiting_approval'),None)
        allowed=('sent','viewed') if name=='gi_respond' else ('awaiting_approval',)
        fields=('state','updated')
    elif name in ('respond','pick_request'):
        box,field='_requests','status'
        states={'POLICY_CHANGED':('policy_revoked',)}
        row=_rows(before,box).get(str(args.get('rid')))
        allowed=('pending',) if name=='respond' else ('answered',)
        if name=='pick_request' and row and (row.get('trace') or {}).get('reason')=='picked_other':
            allowed+=('not_picked',)  # The actual handler also checks that the prior seat is free.
        fields=('status','updated','version','trace')
    else: return None
    target=states.get(result.get('error'))
    new=_rows(after,box).get(str(row.get('id'))) if row else None
    if not target or not row or row.get(field) not in allowed or not new or new.get(field) not in target: return None
    safe=copy.deepcopy(before)
    saved=next(r for r in safe[box] if r.get('id')==row['id'])
    for key in fields:
        if key in new: saved[key]=copy.deepcopy(new[key])
    return safe


def canonical_pair_state(owner,peer):
    tx=active_tx()
    if not tx or ms.mode()!='enforce': return None
    row=tx.conn.execute("select state from monetization_sessions where pair=%s order by (state='active') desc limit 1",
                        (ms.pair_key(owner,peer),)).fetchone()
    return row[0] if row else None


def _invoke(name,fn,args,kwargs):
    mode=ms.mode()
    if mode=='shadow' and not getattr(_local,'shadow',False):
        # Observe the same decision without persisting quotas, grants or shadow results
        # over the existing product data. The legacy result remains authoritative.
        with _app['_STORE_LOCK']:
            before=copy.deepcopy(_app['SESSION'])
            _local.shadow=True
            try:
                result=fn(*args,**kwargs)
            finally:
                _local.shadow=False
            payload=inspect.signature(fn).bind(*args,**kwargs)
            payload.apply_defaults()
            decision='allowed'
            class ProbeRollback(Exception): pass
            try:
                with ms.transaction(projection=True) as tx:
                    _reconcile(tx,before,copy.deepcopy(_app['SESSION']),name,dict(payload.arguments))
                    raise ProbeRollback()
            except ms.CommandError as e:
                decision='allowed' if isinstance(e.__cause__,ProbeRollback) else e.code
            try:
                with ms.transaction() as tx:
                    tx.audit(None,'shadow_decision',{'action':name,'decision':decision})
            except ms.CommandError:
                pass  # Shadow observability cannot change a legacy product result.
            return result
    if mode != 'enforce' or active_tx():
        return fn(*args,**kwargs)
    bound = inspect.signature(fn).bind(*args,**kwargs)
    bound.apply_defaults()
    payload = dict(bound.arguments)
    for field in ('idem','client_id'):
        if payload.get(field) is not None: ms.command_key(payload[field])
    # Evidence files stay in the existing media store; the command fingerprints bytes,
    # never embeds private binary attachments in the command/audit ledger.
    payload = {k:({'sha256':hashlib.sha256(v).hexdigest(),'bytes':len(v)} if isinstance(v,bytes) else v)
               for k,v in payload.items()}
    owner = next((str(payload.get(k)) for k in ('owner_id','frm','owner','host','self_name','who') if payload.get(k)),'system:sweep')
    if name=='purge_person': owner=str(payload['name'])
    key = payload.get('idem') or payload.get('client_id') or ms.new_id('legacy_')
    prepared = None
    if name in ('save_intent','gi_create') and owner!='system:sweep' and isinstance(payload.get('intent'),dict):
        # Address/geocoder work precedes the canonical transaction. The legacy
        # helper consumes this prepared value under the lock without network I/O.
        prepared = _app['_prepare_map_intent'](_app['_display'](owner,owner),payload['intent'],owner)
    with _app['_STORE_LOCK']:
        committed = None
        def run(tx):
            nonlocal committed
            doc = _project(tx,tx.documents())
            before = copy.deepcopy(doc)
            _local.tx = tx
            _local.prepared_map = prepared
            try:
                with projection(doc):
                    if name=='propose':
                        proposal=dict(bound.arguments)
                        proposal['intent']=proposal_intent(tx,proposal['intent'],proposal['frm'],proposal['to'])
                        result=fn(**proposal)
                    else:
                        result = fn(*args,**kwargs)
                    if isinstance(result,dict) and result.get('ok') is False:
                        safe=terminal_denial(before,doc,name,payload,result)
                        if safe is None:
                            raise ms.CommandError(result.get('error','command_failed'),result.get('httpStatus',409),legacy=result)
                        doc.clear();doc.update(safe)
                        result=ms.CommittedDenial(result,httpStatus=result.get('httpStatus',409))
                    _reconcile(tx,before,doc,name,payload,deleting_owner=owner if name=='purge_person' else None)
                    if name=='purge_person': purge_canonical(tx,before,doc,owner)
                    tx.save_documents(doc)
                    committed = doc
                    return result
            finally:
                _local.tx = None
                _local.prepared_map = None
        try:
            if name=='purge_person':
                # Deletion is idempotent without retaining a ledger for the deleted subject.
                with ms.transaction(projection=True) as tx:
                    # Onboarding normally committed this first. Direct/retry admin
                    # purge must establish the same barrier, never reopen rights.
                    monetization_admin.begin_delete(tx.conn,owner)
                    result = run(tx)
            elif name in PASSIVE and not payload.get('idem') and not payload.get('client_id'):
                # Reconcile every poll atomically, without an unbounded full receipt log.
                with ms.transaction(projection=True) as tx:
                    result = run(tx)
            else:
                result = ms.execute(owner,name,key,payload,run,projection=True)
            if committed is not None: publish_projection(committed)
            return result
        except ms.CommandError as e:
            if name.startswith('_'):
                raise
            return dict(e.details.get('legacy') or {}, **e.response())


def refresh():
    if ms.mode() != 'enforce' or active_tx():
        return
    with _app['_STORE_LOCK']:
        with ms.transaction(projection=True) as tx:
            doc = _project(tx,tx.documents())
            tx.save_documents(doc)
        publish_projection(doc)


def chat_states(owner, peers):
    """Read lifecycle from the canonical pair, never from truncated message history.

    This is deliberately a read: opening a screen must not reserve a chat slot.
    No initiator or third-party blocker IDs are exposed to the other participant.
    """
    def read(tx=None):
        result = {}
        observed = float(tx.conn.execute('select extract(epoch from clock_timestamp())').fetchone()[0]) if tx else time.time()
        stored_blocks = tx.conn.execute("select value from monetization_documents where key='_blocks'").fetchone() if tx else None
        blocks = (stored_blocks[0] if stored_blocks else {}) or {}
        for peer in peers:
            row = tx.conn.execute(
                "select id,state from monetization_sessions where pair=%s "
                "order by (state='active') desc limit 1",
                (ms.pair_key(owner,peer),)).fetchone() if tx else None
            result[peer] = dict(peerId=peer, state=row[1] if row else ('new' if tx else 'legacy'),
                                # Only an active session is current. Old closed rows
                                # can share second-resolution timestamps; do not guess
                                # their order and present a historical ID as current.
                                sessionId=row[0] if row and row[1]=='active' else None,
                                blocked=(peer in (blocks.get(owner) or []) or owner in (blocks.get(peer) or []))
                                    if tx else bool(_app['_blocked_pair'](owner,peer)),
                                serverTime=observed)
        return result
    if ms.mode() != 'enforce':
        return read()
    if active_tx():
        return read(active_tx())
    with ms.transaction(projection=True) as tx:
        return read(tx)


def search_inactive(intent,owner):
    if ms.mode() != 'enforce':
        return False
    with ms.transaction(projection=True) as tx:
        rid = _resource_ref(tx,intent,owner)
        tx.expire(owner)
        return not rid or tx.resource(rid,owner)['state'] != 'active'


def handle(handler,path,body):
    """Called only after existing authentication resolves handler._pid."""
    search_paths = ('/api/agent/search-command','/api/agent/match','/api/agent/confirm','/api/agent/expand','/api/agent/plan')
    if path in search_paths + ('/api/agent/intent-save','/api/agent/gintent-create','/api/agent/group-create'):
        if not isinstance(body,dict): raise ms.CommandError('invalid_search_input',400)
        for field in ('intent','ctx','override','profile'):
            if field in body and body[field] is not None and not isinstance(body[field],dict):
                raise ms.CommandError('invalid_search_input',400)
        validate_search_input(path,body)
        # Present-but-invalid is not an old client. Validate both aliases before
        # parsing/ranking/network, even when the other alias happens to be valid.
        for field in ('commandId','idem'):
            if field in body: ms.command_key(body[field])
        key = body.get('commandId',body.get('idem'))
        if key is None: key = 'legacy:' + ms.digest({'path':path,'body':body})
        # Restored legacy routes consume idem, so forward the validated identity.
        body['idem']=key
    if ms.mode() != 'enforce':
        if path != '/api/agent/search-command':
            return False
        if not handler._pid:
            raise ms.CommandError('sign_in_required',401)
        if body.get('operation','publish') not in ('publish','rank_group'):
            raise ms.CommandError('phase2_not_enabled',409)
        ctx = dict(body.get('ctx') or {},self_id=handler._pid,self=_app['_display'](handler._pid,handler._pid))
        if body.get('operation')=='rank_group':
            group,canonical=group_search(_app['SESSION'],handler._pid,body.get('groupId'))
            result=_app['render_search'](path,body,canonical,ctx)
            _app['send_json'](handler,200,dict(result,ok=True,intent=canonical,groupId=group['id'],launchState='ready'))
            return True
        intent = _app['prepare_search'](path,body,ctx)
        saved = _app['save_intent'](handler._pid,intent,body.get('title') or intent.get('title',''),
                                    intent.get('id'),True,owner_id=handler._pid)
        if not saved.get('ok'):
            _app['send_json'](handler,409,saved)
            return True
        intent = dict(intent,id=saved['id'])
        result = _app['render_search'](path,body,intent,ctx)
        _app['send_json'](handler,200,dict(result,ok=True,id=saved['id']))
        return True
    owner = handler._pid
    if path in ('/api/agent/feedback','/api/agent/outcome'):
        if not owner: raise ms.CommandError('sign_in_required',401)
        key=body.get('commandId') or body.get('idempotency_key') or ms.new_id('legacy_')
        def side_command(owner_id,idem,data):
            peer=_app['_ckey'](data)
            if path.endswith('/feedback'):
                ok=_app['record_feedback'](peer,data.get('decision'),owner_id,purpose=data.get('purpose'))
                return {'ok':bool(ok),'feedback':_app['_session'](owner_id).get('feedback')}
            ok=_app['_record_outcome'](peer,data.get('stage'),owner_id)
            return {'ok':bool(ok),'stages':list(_app['_OUTCOME_STAGES']),
                    'metrics':_app['_success_metrics'](),'match_capsules':_app['_match_capsules']()}
        result=_invoke(path,side_command,(owner,key,body),{})
        _app['send_json'](handler,result.get('httpStatus',200),result)
        return True
    # Historical scaffolds have no real admission adapter; explicit error prevents bypass.
    if path in ('/api/agent/group/reserve','/api/agent/group/accept','/api/agent/group/release',
                '/api/agent/proposal','/api/agent/proposal/respond','/api/agent/plan_resource',
                '/api/agent/plan-resource','/api/agent/negotiate','/api/agent/transition',
                '/api/agent/save','/api/agent/save_search','/api/agent/save_search/delete') or (
                path=='/api/agent/group' and body.get('reserve')):
        raise ms.CommandError('legacy_command_not_supported',409)
    if path not in ('/api/agent/search-command','/api/agent/match','/api/agent/confirm','/api/agent/expand','/api/agent/plan'):
        return False
    if not owner:
        raise ms.CommandError('sign_in_required',401)
    intent = body.get('intent') or {}
    operation = body.get('operation','publish')
    if operation not in ('publish','resume','pause','rank_group'):
        raise ms.CommandError('invalid_search_operation',400)
    if operation=='rank_group' and (not isinstance(body.get('groupId'),str) or not body['groupId'] or len(body['groupId'])>160):
        raise ms.CommandError('search_reference_required',400)
    if operation=='resume' and (not isinstance(body.get('searchId'),str) or not body['searchId']
                               or len(body['searchId'])>160 or not isinstance(intent,dict)):
        raise ms.CommandError('search_reference_required',400)
    if operation=='publish' and path != '/api/agent/plan' and (not isinstance(intent,dict) or not intent):
        raise ms.CommandError('intent_required',400)
    cached = ms.receipt(owner,'search_command',key,body)
    if cached is not None:
        return respond_launch(handler,owner,key,body,cached,path,operation)
    if operation=='publish':
        original_id = intent.get('_searchId') or intent.get('id') or intent.get('iid')
        ctx = dict(body.get('ctx') or {},self_id=owner,self=_app['_display'](owner,owner))
        intent=_app['prepare_search'](path,body,ctx)
        if original_id:
            intent['_searchId']=original_id
        intent = _app['_prepare_map_intent'](_app['_display'](owner,owner),intent,owner)
    committed=None
    def run(tx):
        nonlocal committed
        if operation=='rank_group':
            rid=tx.resolve('group',body['groupId'])
            _require_active(tx,rid,owner)
            group,canonical=group_search(tx.documents(),owner,body['groupId'])
            canonical['_searchId']=rid
            generation=ms.new_id('publication_')
            tx.conn.execute("update monetization_resources set generation=%s,launch_state='pending' where id=%s",(generation,rid))
            ms.db.outbox_put('monetization.search.launch',{'resourceId':rid,'generation':generation,'ownerId':owner,'commandKey':key,'body':body,'route':path},conn=tx.conn)
            return {'ok':True,'id':canonical.get('id'),'searchId':rid,'intent':canonical,'launchState':'pending','_generation':generation}
        rid = body.get('searchId') or _resource_ref(tx,intent,owner)
        command_intent = intent
        publish_payload = {'intent':intent,'title':body.get('title') or intent.get('title') or ''}
        if rid:
            resource=tx.resource(rid,owner)
            if resource['state']=='deleted': raise ms.CommandError('search_deleted',410)
        if operation=='resume':
            if not rid: raise ms.CommandError('search_reference_required',400)
            # A status card intentionally carries no editable intent. Restore the
            # canonical payload under the same lock as owner/quota/swap checks;
            # caller-supplied placeholders or edits never replace it on resume.
            publish_payload=copy.deepcopy(resource['payload'])
            source_id=publish_payload.get('id')
            if source_id and tx.resolve('group',source_id)==rid:
                docs=tx.documents()
                source=next((g for box in ('_groups','_gintents') for g in docs.get(box,[])
                             if g.get('id')==source_id),None)
                if source: publish_payload=copy.deepcopy(source)
            command_intent=publish_payload.get('intent')
            if not command_intent:
                # Legacy group_create stores public search fields directly. Resolve
                # the current group by its canonical alias, retaining owner/capacity.
                aliases = {r[0] for r in tx.conn.execute("select alias from monetization_aliases where kind='group' and resource_id=%s",(rid,))}
                groups = tx.documents().get('_groups',[])
                group = next((g for g in groups if g.get('id') in aliases and g.get('host')==owner),None)
                if group:
                    publish_payload = copy.deepcopy(group)
                    command_intent = {k:copy.deepcopy(group[k]) for k in ('title','topics','mode','area','lat','lon') if k in group}
                    command_intent.update(time=group.get('when',''),place=group.get('area',''),
                                          group=True,groupSize=group.get('max_size'),minSize=group.get('min_size'))
            if not isinstance(command_intent,dict) or not command_intent:
                raise ms.CommandError('resume_payload_unavailable',409)
        if operation=='pause':
            if not rid:
                raise ms.CommandError('search_reference_required')
            tx.pause(owner,rid)
        else:
            rid = tx.publish(owner,publish_payload,
                             rid,body.get('swapSearchId'),launch={'commandKey':key,'body':body,'route':path})
        iid = tx.conn.execute("select alias from monetization_aliases where kind='intent' and resource_id=%s order by alias limit 1",
                              (rid,)).fetchone()
        iid = iid[0] if iid else ms.new_id('in_')
        tx.alias('intent',iid,rid)
        doc = tx.documents()
        rows = doc.setdefault('_intents',[])
        row = next((r for r in rows if r.get('id')==iid),None)
        if row is None:
            row = {'id':iid,'owner_id':owner,'owner':_app['_display'](owner,owner),'created':tx.now}
            rows.append(row)
        if operation!='pause':
            row.update(intent=dict(command_intent,id=iid,_searchId=rid),title=publish_payload.get('title') or command_intent.get('title') or '',
                       launched=tx.now)
        row.update(updated=tx.now,searchId=rid)
        committed=_project(tx,doc)
        tx.save_documents(committed)
        return {'ok':True,'id':iid,'searchId':rid,'intent':row.get('intent',{}),'launchState':'pending' if operation!='pause' else 'paused',
                '_generation':tx.resource(rid,owner)['generation']}
    with _app['_STORE_LOCK']:
        result = ms.execute(owner,'search_command',key,body,run,projection=True)
        if committed is not None: publish_projection(committed)
    return respond_launch(handler,owner,key,body,result,path,operation)


def validate_search_input(path,body):
    def invalid(): raise ms.CommandError('invalid_search_input',400)
    if not isinstance(body,dict): invalid()
    for field in ('intent','ctx','override','profile'):
        if body.get(field) is not None and not isinstance(body[field],dict): invalid()
    for obj in (body,body.get('intent') or {},body.get('override') or {}):
        if not isinstance(obj,dict): invalid()
        if obj.get('title') is not None and not isinstance(obj['title'],str): invalid()
        for field in ('id','iid','_searchId','searchId','swapSearchId','groupId','targetSearchId','targetIntentId'):
            if field in obj and obj[field] is not None:
                if not isinstance(obj[field],str) or not obj[field].strip() or len(obj[field])>160: invalid()
    confirmed=body.get('confirmed_ids')
    if confirmed is not None and (not isinstance(confirmed,list) or any(not isinstance(x,str) or not x or len(x)>160 for x in confirmed)): invalid()
    constraints=body.get('constraints')
    if constraints is not None:
        if path.endswith('/confirm'):
            if not isinstance(constraints,list): invalid()
            for item in constraints:
                if not isinstance(item,dict): invalid()
                for field in ('id','kind','field','phrase'):
                    if field in item and not isinstance(item[field],str): invalid()
                if not isinstance(item.get('id'),str) or not item['id']: invalid()
                if item.get('target_prefs') is not None and not isinstance(item['target_prefs'],dict): invalid()
                if item.get('field')=='requiredLanguages' and item.get('proposed_value') is not None:
                    values=item['proposed_value']
                    if not isinstance(values,list) or any(not isinstance(x,str) for x in values): invalid()
        elif not isinstance(constraints,dict): invalid()


def respond_launch(handler,owner,key,body,result,path,operation):
    result = current_launch(owner,result,body)
    if operation != 'pause' and result.get('launchState') == 'pending':
        # No DB lock during ranking. Failure leaves a durable, retryable pending launch.
        try:
            result = complete_launch(owner,key,body,result,path)
        except Exception:
            result = dict(result,candidates=[],launchState='pending',retryable=True)
    # Snapshot identity bindings are private receipt metadata, never a wire field.
    _app['send_json'](handler,200,{k:v for k,v in result.items() if k not in ('_candidate_refs','_generation')})
    return True


def group_search(doc,owner,gid):
    if not isinstance(gid,str) or not gid or len(gid)>160: raise ms.CommandError('search_reference_required',400)
    group=next((g for g in doc.get('_gintents',[]) if g.get('id')==gid),None)
    if not group or group.get('owner')!=owner: raise ms.CommandError('not_your_search',403)
    if group.get('state') in TERMINAL or group.get('state')=='locked': raise ms.CommandError('group_not_recruiting',409)
    canonical=copy.deepcopy(group.get('intent') or {})
    canonical.update(format='group',groupSize=group.get('max_total'),minSize=group.get('min_total'),
                     title=group.get('title') or canonical.get('title',''))
    return group,canonical


def current_launch(owner,result,body=None):
    """Idempotency preserves a command, not permission to reveal stale recruitment."""
    if result.get('redacted'): return result
    with ms.transaction() as tx:
        tx.expire(owner)
        resource=tx.resource(result['searchId'])
        if resource['owner_id']!=owner: return retired_launch(result)
        if resource['state']=='deleted': raise ms.CommandError('search_deleted',410)
        if resource['state']!='active':
            return {k:v for k,v in dict(result,candidates=[],launchState='paused',has_more=False,shown=0).items() if k!='group'}
        if result.get('_generation','')!=resource['generation']:
            return retired_launch(result)
        if result.get('launchState')=='ready':
            return safe_receipt(tx,owner,result,result.get('intent') or {},body)
    return result


def retired_launch(result):
    return {k:v for k,v in dict(result,candidates=[],launchState='superseded',has_more=False,shown=0).items() if k!='group'}


def public_snapshot_hash(row):
    value=copy.deepcopy(row)
    # Safety and temporary pause are rechecked independently on every read. They
    # can tighten outreach and later recover without changing public profile data.
    value.pop('safetyFlags',None)
    receiving=value.get('receiving')
    if isinstance(receiving,dict):
        receiving.pop('status',None);receiving.pop('paused_until',None)
        if not receiving: value.pop('receiving',None)
    return ms.digest(value)


def candidate_refs(result,pool,intent):
    """Bind legacy name-only cards to the ranking snapshot, never to a later namesake."""
    ids={str(r['id']):r for r in pool if r.get('id')}
    names={}
    for row in pool:
        if row.get('id'): names.setdefault(str(row.get('name') or '').strip().lower(),set()).add(str(row['id']))
    refs=[]
    for card in result.get('candidates') or []:
        if card==_app['_online_fallback'](intent)['room']:
            refs.append({'alternative':True}); continue
        explicit=str(card.get('id') or card.get('person_id') or '')
        profile=str((card.get('profile_view') or {}).get('user_id') or '')
        matches=names.get(str(card.get('name') or '').strip().lower(),set())
        peer=explicit or (profile if profile in ids else next(iter(matches)) if len(matches)==1 else '')
        refs.append({'person_id':peer,'public_hash':public_snapshot_hash(ids[peer])} if peer in ids else {})
    return refs


def safe_receipt(tx,owner,result,intent,body=None):
    """Recheck current local safety inputs without invoking the external ranker."""
    doc = tx.documents()
    deleted = {r[0] for r in tx.conn.execute('select owner_id from monetization_deletions').fetchall()}
    candidates = result.get('candidates') or []
    with projection(doc):
        request_ctx=dict((body or {}).get('ctx') or {},self_id=owner,self=_app['_display'](owner,owner))
        prof=(body or {}).get('profile') or {}
        ctx,self_name = _app['_gate_ctx_and_self'](request_ctx,prof)
        prof=_app['_prof_with_own_row'](prof,self_name,owner)
        raw_pool=_app['load_candidates']()
        public_hashes={str(r['id']):public_snapshot_hash(r) for r in raw_pool if r.get('id')}
        pool=_app['_with_km'](raw_pool,prof,request_ctx)
        people={str(r.get('id')):r for r in pool if r.get('id')}
        intent=_app['ki'].normalize_for_scoring(intent)
        kept=[]; kept_refs=[]; changed=False
        refs=result.get('_candidate_refs')
        for index,candidate in enumerate(candidates):
            ref=refs[index] if refs is not None and index<len(refs) else {}
            # A generated room suggestion is not a person and has no peer ID.
            # Keep only the known public alternative shape; it contains no roster.
            if candidate == _app['_online_fallback'](intent)['room']:
                kept.append(candidate); kept_refs.append(ref); continue
            peer=str(ref.get('person_id') or candidate.get('id') or candidate.get('person_id') or (candidate.get('profile_view') or {}).get('user_id') or '')
            current=people.get(peer)
            if not current or peer in deleted or _app['_blocked_pair'](owner,peer): continue
            # The full source snapshot includes receiving/disclosure consent. If
            # it changed, removing the stale card is safer than copying its old
            # nested photo/bio/profile fields or rerunning an external ranker.
            if ref.get('public_hash')!=public_hashes.get(peer): continue
            if _app['_core'].is_paused(current,tx.now): continue
            decision,_ = _app['_policy_decision'](intent,current,ctx)
            if decision=='BLOCK': continue
            if decision=='REVIEW' and (candidate.get('policy')!='REVIEW' or candidate.get('can_outreach')):
                candidate=copy.deepcopy(candidate)
                _app['_apply_policy']([candidate],{_app['_ckey'](candidate):'REVIEW'})
                changed=True
            kept.append(candidate); kept_refs.append(ref)
        if len(kept)==len(candidates) and not changed: return result
        result=dict(result,candidates=kept)
        if refs is not None: result['_candidate_refs']=kept_refs
        if len(kept)!=len(candidates): result.update(shown=len(kept),has_more=False)
        result.pop('group',None)  # A precomputed group can contain the removed people.
        return result


def complete_launch(owner,key,body,result,path='/api/agent/match',lease=None):
    """Ranking is lock-free; first committed result wins even with concurrent retries."""
    with ms.transaction() as tx:
        if lease: require_launch_lease(tx,*lease)
        terminal=unavailable_launch(tx,owner,result)
        if terminal is not None: return finish_retired_launch(tx,owner,key,terminal)
        tx.expire(owner)
        resource=tx.resource(result['searchId'],owner)
    if resource['state']!='active':
        ranked=dict(result,candidates=[],launchState='paused')
    else:
        snapshot=read_snapshot()
        with projection(snapshot):
            ctx=dict(body.get('ctx') or {},self_id=owner,self=_app['_display'](owner,owner))
            pool=copy.deepcopy(_app['load_candidates']())
            with pool_projection(pool):
                ranked=dict(result,**_app['render_search'](path,body,result['intent'],ctx),launchState='ready')
            ranked['_candidate_refs']=candidate_refs(ranked,pool,result['intent'])
    with ms.transaction() as tx:
        if lease: require_launch_lease(tx,*lease)
        terminal=unavailable_launch(tx,owner,result)
        if terminal is not None: return finish_retired_launch(tx,owner,key,terminal)
        tx.account(owner)
        current=tx.conn.execute('select result from monetization_commands where owner_id=%s and action=%s and command_key=%s for update',
                                (owner,'search_command',key)).fetchone()[0]
        # Expiry or explicit pause during ranking cannot republish or expose results.
        tx.expire(owner)
        resource=tx.resource(result['searchId'],owner)
        state=resource['state']
        if result.get('_generation','')!=resource['generation']:
            ranked=retired_launch(result)
            tx.conn.execute('update monetization_commands set result=%s where owner_id=%s and action=%s and command_key=%s',
                            (json.dumps(ranked),owner,'search_command',key))
            tx.conn.execute("update outbox set sent_at=now() where topic='monetization.search.launch' and payload->>'ownerId'=%s and payload->>'commandKey'=%s",(owner,key))
            return ranked
        if state=='deleted':
            ranked={'ok':True,'searchId':result['searchId'],'candidates':[],'launchState':'deleted'}
        elif state!='active':
            ranked=dict(result,candidates=[],launchState='paused',has_more=False,shown=0)
        elif current.get('launchState')!='pending':
            return current if current.get('redacted') else safe_receipt(tx,owner,current,result['intent'],body)
        else:
            ranked=safe_receipt(tx,owner,ranked,result['intent'],body)
        tx.conn.execute('update monetization_commands set result=%s where owner_id=%s and action=%s and command_key=%s',
                        (json.dumps(ranked,ensure_ascii=False,default=str),owner,'search_command',key))
        tx.conn.execute('update monetization_resources set launch_state=%s where id=%s',(ranked['launchState'],result['searchId']))
        tx.conn.execute("update outbox set sent_at=now() where topic='monetization.search.launch' and payload->>'ownerId'=%s and payload->>'commandKey'=%s",
                        (owner,key))
    return ranked


def unavailable_launch(tx,owner,result):
    """Permanent loss of this publication is a terminal receipt, not a retry."""
    if tx.conn.execute('select 1 from monetization_deletions where owner_id=%s',(owner,)).fetchone():
        return {'ok':True,'searchId':result['searchId'],'candidates':[],'launchState':'deleted'}
    try: resource=tx.resource(result['searchId'])
    except ms.CommandError as error:
        if error.code!='search_not_found': raise
        return {'ok':True,'searchId':result['searchId'],'candidates':[],'launchState':'deleted'}
    if resource['owner_id']!=owner or result.get('_generation','')!=resource['generation']:
        return retired_launch(result)
    if resource['state']=='deleted':
        return {'ok':True,'searchId':result['searchId'],'candidates':[],'launchState':'deleted'}
    if resource['state']!='active':
        return {k:v for k,v in dict(result,candidates=[],launchState='paused',has_more=False,shown=0).items() if k!='group'}
    return None


def finish_retired_launch(tx,owner,key,result):
    # Preserve the key/hash fence. Never mutate the resource now owned by another
    # user or publication, and never requeue an obsolete owner-bound command.
    current=tx.conn.execute('select result from monetization_commands where owner_id=%s and action=%s and command_key=%s for update',
                            (owner,'search_command',key)).fetchone()
    if current and current[0].get('redacted'): result=current[0]
    tx.conn.execute('update monetization_commands set result=%s where owner_id=%s and action=%s and command_key=%s',
                    (json.dumps(result),owner,'search_command',key))
    tx.conn.execute("update outbox set sent_at=now(),last_error=null where topic='monetization.search.launch' "
                    "and payload->>'ownerId'=%s and payload->>'commandKey'=%s",(owner,key))
    return result


def require_launch_lease(tx,jid,token):
    row=tx.conn.execute("select 1 from outbox where id=%s and payload->>'_leaseToken'=%s and next_try>clock_timestamp() and sent_at is null for update",
                        (jid,token)).fetchone()
    if not row: raise ms.CommandError('launch_lease_lost',503)


@contextlib.contextmanager
def launch_lease(jid,token):
    stopped=threading.Event()
    deadline=time.monotonic()+600
    def renew():
        while not stopped.wait(30):
            try:
                if not renew_launch_lease(jid,token,deadline): break
            except Exception: break
    thread=threading.Thread(target=renew,daemon=True,name='monetization-lease');thread.start()
    try: yield
    finally: stopped.set();thread.join(timeout=ms.STATEMENT_TIMEOUT_MS/1000+1)


def renew_launch_lease(jid,token,deadline):
    remaining=deadline-time.monotonic()
    if remaining<=0:return False
    with ms.transaction() as tx:
        require_launch_lease(tx,jid,token)
        remaining=deadline-time.monotonic()
        if remaining<=0:return False
        tx.conn.execute("update outbox set next_try=clock_timestamp()+make_interval(secs=>%s) where id=%s",
                        (min(120,remaining),jid))
    return True


def drain_launches(limit=10):
    """Lease local outbox jobs, then recover launches after a process/reply failure."""
    if ms.mode()!='enforce': return 0
    completed=0
    for _ in range(limit):
        # Claim only the next job we are about to execute. An unstarted job must
        # never spend its lease waiting behind a slow external ranking request.
        token=uuid.uuid4().hex
        with ms.transaction() as tx:
            row=tx.conn.execute("select id,payload from outbox where topic='monetization.search.launch' and sent_at is null "
                                "and next_try<=clock_timestamp() order by id limit 1 for update skip locked").fetchone()
            if not row: break
            jid,job=row
            tx.conn.execute("update outbox set next_try=clock_timestamp()+interval '120 seconds',payload=jsonb_set(payload,'{_leaseToken}',%s) where id=%s",
                            (json.dumps(token),jid))
        try:
            key=job.get('commandKey')
            if key:
                with ms.transaction() as tx:
                    row=tx.conn.execute('select result from monetization_commands where owner_id=%s and action=%s and command_key=%s',
                                        (job['ownerId'],'search_command',key)).fetchone()
                if not row: raise RuntimeError('launch command missing')
                if row[0].get('launchState')=='pending':
                    with launch_lease(jid,token):
                        complete_launch(job['ownerId'],key,job['body'],row[0],job.get('route','/api/agent/match'),lease=(jid,token))
            # Legacy publication is discoverable from its canonical projection. It does
            # not request ranked results; only search commands carry a ranking payload.
            with ms.transaction() as tx:
                tx.conn.execute("update outbox set sent_at=now(),last_error=null where id=%s and payload->>'_leaseToken'=%s",(jid,token))
            completed+=1
        except Exception:
            with ms.transaction() as tx:
                tx.conn.execute("update outbox set attempts=attempts+1,next_try=now()+interval '30 seconds',last_error='launch_retry_required' where id=%s and payload->>'_leaseToken'=%s and sent_at is null",(jid,token))
    return completed


def drain_cleanup(limit=10):
    if ms.mode()!='enforce': return 0
    with ms.transaction() as tx:
        jobs=tx.conn.execute("select id,payload from outbox where topic='monetization.media.cleanup' and sent_at is null "
                            "and next_try<=now() order by id limit %s for update skip locked",(limit,)).fetchall()
        for jid,_ in jobs: tx.conn.execute("update outbox set next_try=now()+interval '120 seconds' where id=%s",(jid,))
    completed=0
    for jid,job in jobs:
        try:
            folder={'voice':_app['VOICE_DIR'],'video':_app['VIDEO_DIR'],'evidence':_app['EVIDENCE_DIR']}.get(job.get('kind'))
            if not folder or not re.fullmatch(r'[0-9a-f]{8,64}\.[a-z0-9]{2,5}',job.get('name','')): raise ValueError('invalid_cleanup')
            with ms.transaction(projection=True) as tx:
                # Check and unlink share the same lock as all reference writers.
                referenced=any(name==job['name'] for _,name in media_references(tx.documents()))
                if not referenced:
                    try: os.remove(os.path.join(folder,job['name']))
                    except FileNotFoundError: pass
                tx.conn.execute('update outbox set sent_at=now(),last_error=null where id=%s',(jid,))
            completed+=1
        except Exception:
            with ms.transaction() as tx:
                tx.conn.execute("update outbox set attempts=attempts+1,next_try=now()+interval '30 seconds',last_error='cleanup_retry_required' where id=%s",(jid,))
    return completed


def start_launch_worker():
    def work():
        while True:
            try:
                drain_launches()
                drain_cleanup()
            except ms.CommandError: pass  # No fallback; durable jobs remain pending.
            time.sleep(5)
    threading.Thread(target=work,name='monetization-launch',daemon=True).start()


def install(namespace):
    global _app
    _app = namespace
    namespace['SESSION'] = SessionProjection(namespace['SESSION'])
    prepare_map=namespace['_prepare_map_intent']
    def prepared_map(owner,intent,owner_id=''):
        if active_tx():
            value=getattr(_local,'prepared_map',None)
            if value is None: raise ms.CommandError('canonical_prepare_required',503)
            return copy.deepcopy(value)
        return prepare_map(owner,intent,owner_id)
    namespace['_prepare_map_intent']=prepared_map
    for name in WRITERS:
        fn = namespace.get(name)
        if not fn:
            continue
        def make(n,f):
            @functools.wraps(f)
            def wrapped(*a,**kw):
                return _invoke(n,f,a,kw)
            return wrapped
        namespace[name] = make(name,fn)
    for name in UNADAPTED:
        fn = namespace.get(name)
        if not fn:
            continue
        def block(f):
            @functools.wraps(f)
            def wrapped(*a,**kw):
                if ms.mode()=='enforce':
                    if f.__name__=='form_group_from_slate' and not inspect.signature(f).bind(*a,**kw).arguments.get('reserve',False):
                        return f(*a,**kw)  # Read-only formation is part of the existing ranking contract.
                    raise ms.CommandError('legacy_command_not_supported',409)
                return f(*a,**kw)
            return wrapped
        namespace[name] = block(fn)
    for name in TRANSACTION_ONLY:
        fn=namespace[name]
        def require_transaction(f):
            @functools.wraps(f)
            def wrapped(*a,**kw):
                if ms.mode()=='enforce' and not active_tx():
                    raise ms.CommandError('canonical_writer_required',503)
                return f(*a,**kw)
            return wrapped
        namespace[name]=require_transaction(fn)
    legacy_ensure=namespace['_ensure_intent_owner_ids']
    namespace['_ensure_intent_owner_ids']=lambda: 0 if ms.mode()=='enforce' else legacy_ensure()
    legacy_save = namespace['_save_store']
    def save():
        if active_tx():
            return  # The command commits the projection, quotas and outbox together.
        if ms.mode()=='enforce':
            raise ms.CommandError('canonical_writer_required',503)
        return legacy_save()
    namespace['_save_store'] = save
    get,put = namespace['_idem_get'],namespace['_idem_put']
    namespace['_idem_get'] = lambda key: None if active_tx() else get(key)
    namespace['_idem_put'] = lambda key,value: value if active_tx() else put(key,value)
    legacy_check = namespace['_check_saved_searches']
    def check_saved(prof=None,uid='me'):
        if ms.mode()!='enforce':
            return legacy_check(prof,uid)
        results = []
        with projection(read_snapshot()), pool_projection(copy.deepcopy(namespace['load_candidates']())):
            for item in namespace['_session'](uid).get('saved_searches',[]):
                if search_inactive(item.get('intent') or {},uid):
                    results.append({'id':item['id'],'status':'paused','matches':0})
                else:
                    candidates = namespace['match_candidates'](item['intent'],prof or {},{'self_id':uid})
                    results.append({'id':item['id'],'status':'ready' if candidates else 'watching','matches':len(candidates)})
        return results
    namespace['_check_saved_searches'] = check_saved
    for method in ('do_GET','do_POST'):
        original = getattr(namespace['H'],method)
        def guard(fn):
            @functools.wraps(fn)
            def wrapped(self):
                try:
                    if ms.mode()!='enforce': return fn(self)
                    # No request-wide lock: body/auth/HTTP I/O and ranking run on a
                    # private committed snapshot. Writer adapters own their transactions.
                    previous=getattr(_local,'request',False)
                    _local.request=True
                    try:
                        with projection(read_snapshot()): return fn(self)
                    finally: _local.request=previous
                except ms.CommandError as e:
                    namespace['send_json'](self,e.status,e.response())
            return wrapped
        setattr(namespace['H'],method,guard(original))
