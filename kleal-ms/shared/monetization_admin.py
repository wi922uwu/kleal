"""Private operator API. Never registered as an HTTP handler."""
import json
import monetization_store as ms


def _person(conn,owner):
    if not isinstance(owner,str) or not owner.strip() or owner.startswith(('anon:','recovery:','system:')):
        raise ms.CommandError('exact_user_id_required',400)
    row=conn.execute('select row from users where id=%s for update',(owner,)).fetchone()
    if not row: raise ms.CommandError('user_not_found',404)
    if row[0].get('deleting') or row[0].get('deleted') or conn.execute(
        'select 1 from monetization_deletions where owner_id=%s',(owner,)).fetchone():
        raise ms.CommandError('account_deleting',409)


@ms.bounded_operation
def status(conn,owner=None):
    """Reads every users.id, including accounts with no entitlement row; no locks/writes."""
    now=int(conn.execute('select extract(epoch from clock_timestamp())::bigint').fetchone()[0])
    rows=conn.execute('select u.id,a.eligible,a.preview_start,a.preview_end,a.plus_until,a.keep_search,'
                      "(d.owner_id is not null or coalesce(u.row->'deleting'='true'::jsonb,false) "
                      "or coalesce(u.row->'deleted'='true'::jsonb,false)) "
                      'from users u left join monetization_accounts a on a.owner_id=u.id '
                      'left join monetization_deletions d on d.owner_id=u.id '
                      'where (%s::text is null or u.id=%s) order by u.id',(owner,owner)).fetchall()
    if owner is not None and not rows: raise ms.CommandError('user_not_found',404)
    result=[]
    for uid,eligible,start,end,paid,keep,deleting in rows:
        rights=ms.entitlements(conn,uid,{'end':end,'plus':paid},now)
        active=[r[0] for r in conn.execute("select id from monetization_resources where owner_id=%s "
                "and state='active' order by published desc nulls last,id",(uid,)).fetchall()]
        chosen=keep if keep in active else next(iter(active),None)
        grants=[dict(zip(('id','expiresAt','revokedAt','operator','reason'),r)) for r in conn.execute(
            'select id,expires,revoked,operator,reason from monetization_manual_grants where owner_id=%s order by created,id',(uid,)).fetchall()]
        result.append({'ownerId':uid,'serverTime':now,'deleting':bool(deleting),'plan':'plus' if rights['sources'] and not deleting else 'free',
            'plusExpiresAt':rights['expiresAt'] if not deleting else None,'entitlementSources':rights['sources'] if not deleting else [],
            'previewStartedAt':start,'previewExpiresAt':end,'previewEligible':eligible if eligible is not None else True,
            'activeSearchIds':active,'wouldPause':[] if rights['sources'] else [x for x in active if x!=chosen],
            'grants':grants})
    return result[0] if owner is not None else result


@ms.bounded_operation
def command(conn,*,action,owner,operator,reason,key,expires=None,grant_id=None,apply=False):
    for value in (operator,reason,key):
        if not isinstance(value,str) or not value.strip() or len(value)>500:
            raise ms.CommandError('operator_reason_and_key_required',400)
    if action not in ('grant','revoke'): raise ms.CommandError('invalid_admin_action',400)
    if not isinstance(owner,str) or not owner.strip(): raise ms.CommandError('exact_user_id_required',400)
    payload={'action':action,'owner':owner,'operator':operator,'reason':reason,'expires':expires,'grantId':grant_id}
    tx=ms.Transaction(conn)
    # Same order as canonical writers/deletion. One operator key serializes cross-owner replays.
    tx.lock('monetization:projection')
    release=conn.execute("select value from monetization_meta where key='release_state'").fetchone()
    if release and release[0]!='enforce': raise ms.CommandError('monetization_release_fenced',503)
    tx.lock('monetization:admin:'+key)
    tx.lock('monetization:owner:'+owner)
    cached=conn.execute('select payload_hash,result from monetization_admin_commands where command_key=%s',(key,)).fetchone()
    if cached:
        if cached[0]!=ms.digest(payload): raise ms.CommandError('idempotency_payload_conflict')
        return cached[1]
    _person(conn,owner)
    tx.refresh_clock()  # The users row can also have queued behind deletion.
    if action=='grant':
        if isinstance(expires,bool) or not isinstance(expires,int) or expires<=tx.now:
            raise ms.CommandError('future_utc_expiry_required',400)
    elif not grant_id or not conn.execute('select 1 from monetization_manual_grants where id=%s and owner_id=%s',
                                          (grant_id,owner)).fetchone():
        raise ms.CommandError('grant_not_found',404)
    before=status(conn,owner)
    if not apply:
        return {'ok':True,'dryRun':True,'change':payload,'before':before}
    if action=='grant':
        grant_id=ms.new_id('manual_')
        conn.execute('insert into monetization_manual_grants(id,owner_id,expires,created,operator,reason) values(%s,%s,%s,%s,%s,%s)',
                     (grant_id,owner,expires,tx.now,operator,reason))
    else:
        conn.execute('update monetization_manual_grants set revoked=%s,revoked_by=%s,revoke_reason=%s '
                     'where id=%s and owner_id=%s and revoked is null',(tx.now,operator,reason,grant_id,owner))
        tx.expire(owner)
    result={'ok':True,'dryRun':False,'action':action,'grantId':grant_id,'status':status(conn,owner)}
    conn.execute('insert into monetization_admin_audit(owner_id,event,details,created) values(%s,%s,%s,%s)',
                 (owner,action,json.dumps({**payload,'grantId':grant_id}),tx.now))
    conn.execute('insert into monetization_admin_commands values(%s,%s,%s)',(key,ms.digest(payload),json.dumps(result)))
    return result


@ms.bounded_operation
def begin_delete(conn,owner):
    """Independent of billing flags; persists before slow matching/KYC cleanup."""
    if not conn.execute("select to_regclass('monetization_deletions')").fetchone()[0]: return
    tx=ms.Transaction(conn);tx.lock('monetization:projection');tx.lock('monetization:owner:'+owner)
    conn.execute('insert into monetization_deletions values(%s,%s) on conflict do nothing',(owner,tx.now))
    # Удаление учётки не является отзывом оператором: приватные reason/operator,
    # grant history и cached status больше не нужны. Оставляем только точный
    # owner_id + started в tombstone, чтобы late/replayed grant не воскресил права.
    # status.ownerId записан сервером, это exact ownership, не поиск строки/имени.
    conn.execute("delete from monetization_admin_commands where result #>> '{status,ownerId}'=%s",(owner,))
    conn.execute('delete from monetization_admin_audit where owner_id=%s',(owner,))
    conn.execute('delete from monetization_manual_grants where owner_id=%s',(owner,))
