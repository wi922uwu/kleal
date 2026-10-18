"""Phase 2A durable commands. Import never creates or migrates a schema.

Legacy matching functions run against a transaction-local document projection. The
global projection lock deliberately serializes those adapters until their documents
are split; owner/pair locks also cover the normalized resource and session writers.
No JSON fallback is permitted here. All times come from PostgreSQL.
"""
import contextlib
import functools
import hashlib
import json
import os
import uuid

import db

PREVIEW_SECONDS = 1209600
LOCK_TIMEOUT_MS = 3000
STATEMENT_TIMEOUT_MS = 10000
SCHEMA = """
create table if not exists monetization_meta (key text primary key, value jsonb not null);
create table if not exists monetization_accounts (
 owner_id text primary key, eligible boolean not null default true,
 preview_start bigint, preview_end bigint, plus_until bigint,
 keep_search text, notice_seen boolean not null default false,
 eligibility_provenance jsonb not null default '{}'::jsonb,
 check (preview_end is null or preview_end = preview_start + 1209600)
);
create table if not exists monetization_commands (
 owner_id text not null, action text not null, command_key text not null,
 payload_hash text not null, result jsonb not null, created bigint not null,
 primary key(owner_id, action, command_key)
);
create index if not exists monetization_command_result_values on monetization_commands using gin (result);
create table if not exists monetization_resources (
 id text primary key, owner_id text not null, state text not null,
 published bigint, payload jsonb not null, launch_state text not null default 'idle', generation text not null default ''
);
alter table monetization_resources add column if not exists generation text not null default '';
create index if not exists monetization_resource_owner on monetization_resources(owner_id, state);
create table if not exists monetization_aliases (
 kind text not null, alias text not null, resource_id text not null references monetization_resources(id),
 primary key(kind, alias)
);
create table if not exists monetization_sessions (
 id text primary key, pair text not null, initiator text,
 state text not null, opened bigint not null, closed bigint,
 protected boolean not null default false, provenance jsonb not null default '{}'::jsonb
);
create unique index if not exists monetization_session_active_pair
 on monetization_sessions(pair) where state = 'active';
create index if not exists monetization_session_owner on monetization_sessions(initiator, state);
create table if not exists monetization_plan_sessions (
 plan_id text primary key, session_id text not null references monetization_sessions(id),
 terminal_applied boolean not null default false
);
create table if not exists monetization_protected (
 kind text not null, resource_id text not null, action text not null,
 provenance jsonb not null, primary key(kind,resource_id,action)
);
create table if not exists monetization_documents (key text primary key, value jsonb not null);
create table if not exists monetization_audit (
 id bigserial primary key, owner_id text, event text not null,
 details jsonb not null, created bigint not null
);
create table if not exists monetization_deletions (
 owner_id text primary key, started bigint not null
);
create table if not exists monetization_manual_grants (
 id text primary key, owner_id text not null, expires bigint not null,
 created bigint not null, operator text not null, reason text not null,
 revoked bigint, revoked_by text, revoke_reason text,
 check (expires > created)
);
create index if not exists monetization_manual_owner on monetization_manual_grants(owner_id);
create table if not exists monetization_admin_commands (
 command_key text primary key, payload_hash text not null, result jsonb not null
);
create table if not exists monetization_admin_audit (
 id bigserial primary key, owner_id text not null, event text not null,
 details jsonb not null, created bigint not null
);
"""


class CommandError(Exception):
    def __init__(self, code, status=409, **details):
        super().__init__(code)
        self.code, self.status, self.details = code, status, details

    def response(self):
        return dict(ok=False, error=self.code, reason=self.code, httpStatus=self.status,
                    retryable=self.status == 503, **self.details)


def mode():
    value = os.environ.get('KLEAL_MONETIZATION_MODE', 'off').lower()
    if value not in ('off', 'shadow', 'enforce'):
        raise CommandError('monetization_configuration_invalid', 503)
    return value


def digest(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def pair_key(a, b):
    return json.dumps(sorted((str(a), str(b))), separators=(',', ':'))


def new_id(prefix):
    return prefix + uuid.uuid4().hex


def connection():
    if not db.ENABLED or db.MIRROR_JSON:
        raise CommandError('monetization_postgres_required', 503)
    return db._connect().connection(timeout=5)


def bounded_transaction(conn):
    # SET LOCAL never changes pool/session defaults or the user's database config.
    conn.execute("select set_config('lock_timeout',%s,true),set_config('statement_timeout',%s,true)",
                 (str(LOCK_TIMEOUT_MS),str(STATEMENT_TIMEOUT_MS)))


def bounded_operation(fn):
    """Operator entrypoints get the same local deadlines and atomic error boundary."""
    @functools.wraps(fn)
    def wrapped(conn,*args,**kwargs):
        import psycopg
        try:
            # Start the caller-owned transaction before the savepoint. Entering
            # conn.transaction() on an idle connection would COMMIT this command
            # prematurely, defeating the caller's later rollback.
            bounded_transaction(conn)
            with conn.transaction():
                return fn(conn,*args,**kwargs)
        except CommandError:
            raise
        except psycopg.Error as error:
            raise CommandError('monetization_unavailable',503) from error
    return wrapped


class Transaction:
    def __init__(self, conn):
        self.conn = conn
        bounded_transaction(conn)
        self.refresh_clock()

    def refresh_clock(self):
        self.now = int(self.conn.execute('select extract(epoch from clock_timestamp())::bigint').fetchone()[0])

    def lock(self, *keys):
        for key in sorted(set(keys)):
            self.conn.execute('select pg_advisory_xact_lock(hashtextextended(%s,0))', (key,))
        # Decisions use the server clock AFTER queueing for the required locks.
        self.refresh_clock()

    def account(self, owner):
        if not isinstance(owner, str) or not owner:
            raise CommandError('sign_in_required', 401)
        self.lock('monetization:owner:' + owner)
        if self.conn.execute('select 1 from monetization_deletions where owner_id=%s',(owner,)).fetchone():
            raise CommandError('account_deleting',409)
        if self.conn.execute("select 1 from monetization_meta where key='production_import'").fetchone():
            if not self.conn.execute('select 1 from users where id=%s',(owner,)).fetchone():
                raise CommandError('user_not_found',404)
        self.conn.execute('insert into monetization_accounts(owner_id) values (%s) on conflict do nothing', (owner,))
        r = self.conn.execute('select eligible,preview_start,preview_end,plus_until,keep_search,notice_seen '
                              'from monetization_accounts where owner_id=%s for update', (owner,)).fetchone()
        return dict(zip(('eligible','start','end','plus','keep','seen'), r))

    def audit(self, owner, event, details):
        self.conn.execute('insert into monetization_audit(owner_id,event,details,created) values (%s,%s,%s,%s)',
                          (owner, event, json.dumps(details), self.now))

    def grant(self, owner, evidence):
        a = self.account(owner)
        if a['eligible'] and a['start'] is None:
            self.conn.execute('update monetization_accounts set eligible=false,preview_start=%s,preview_end=%s '
                              'where owner_id=%s', (self.now, self.now + PREVIEW_SECONDS, owner))
            self.audit(owner, 'preview_meaningful_use', evidence)
            return True
        return False

    def plus(self, owner):
        a = self.account(owner)
        return bool(entitlements(self.conn,owner,a,self.now)['sources'])

    def expire(self, owner):
        a = self.account(owner)
        if self.plus(owner):
            return
        rows = self.conn.execute("select id from monetization_resources where owner_id=%s and state='active' "
                                 'order by published desc nulls last,id asc', (owner,)).fetchall()
        ids = [r[0] for r in rows]
        keep = a['keep'] if a['keep'] in ids else (ids[0] if ids else None)
        if len(ids) > 1:
            self.conn.execute("update monetization_resources set state='paused' where owner_id=%s "
                              "and state='active' and id<>%s", (owner, keep))
            self.audit(owner, 'expiry_paused', {'keep': keep, 'paused': [i for i in ids if i != keep]})

    def resource(self, rid, owner=None):
        row = self.conn.execute('select id,owner_id,state,published,payload,launch_state,generation '
                                'from monetization_resources where id=%s', (rid,)).fetchone()
        if not row:
            raise CommandError('search_not_found', 404)
        r = dict(zip(('id','owner_id','state','published','payload','launchState','generation'), row))
        if owner is not None and r['owner_id'] != owner:
            raise CommandError('not_your_search', 403)
        return r

    def resolve(self, kind, alias):
        r = self.conn.execute('select resource_id from monetization_aliases where kind=%s and alias=%s',
                              (kind, str(alias))).fetchone()
        return r[0] if r else None

    def alias(self, kind, alias, rid):
        existing = self.resolve(kind, alias)
        if existing and existing != rid:
            raise CommandError('ambiguous_resource_link', 409)
        self.conn.execute('insert into monetization_aliases values (%s,%s,%s) on conflict do nothing',
                          (kind, str(alias), rid))

    def check_search(self, owner, rid=None, swap=None):
        self.expire(owner)
        if self.plus(owner):
            return
        blockers = [r[0] for r in self.conn.execute("select id from monetization_resources "
                    "where owner_id=%s and state='active' and id<>%s order by id", (owner, rid or '')).fetchall()]
        if blockers and not (len(blockers) == 1 and swap == blockers[0]):
            raise CommandError('search_quota', blockerIds=blockers)

    def publish(self, owner, payload, rid=None, swap=None, meaningful=True, launch=None):
        self.account(owner)
        if rid:
            if self.resource(rid, owner)['state']=='deleted':
                raise CommandError('search_deleted',410)
        if swap:
            blocker = self.resource(swap, owner)
            if swap == rid or blocker['state'] != 'active':
                raise CommandError('invalid_search_swap',409)
        if meaningful:
            self.grant(owner, {'action':'publish','resourceId':rid})
        self.check_search(owner, rid, swap)
        if swap:
            self.resource(swap, owner)
            self.conn.execute("update monetization_resources set state='paused' where id=%s", (swap,))
        rid = rid or new_id('search_')
        generation=new_id('publication_')
        self.conn.execute("insert into monetization_resources(id,owner_id,state,published,payload,launch_state,generation) "
                          "values (%s,%s,'active',%s,%s,'pending',%s) on conflict(id) do update set "
                          "state='active',published=excluded.published,payload=excluded.payload,launch_state='pending',generation=excluded.generation",
                          (rid,owner,self.now,json.dumps(payload),generation))
        db.outbox_put('monetization.search.launch', dict(resourceId=rid,ownerId=owner,generation=generation,**(launch or {})), conn=self.conn)
        return rid

    def pause(self, owner, rid):
        self.account(owner)
        if self.resource(rid, owner)['state']=='deleted':
            raise CommandError('search_deleted',410)
        self.conn.execute("update monetization_resources set state='paused' where id=%s", (rid,))

    def delete_search(self, owner, rid):
        self.account(owner)
        self.resource(rid,owner)
        # Keep aliases and command hashes as permanent replay fences. No payload
        # or queued launch may resurrect an explicitly deleted standalone search.
        self.conn.execute("update monetization_resources set state='deleted',payload='{}',launch_state='deleted' where id=%s",(rid,))
        self.conn.execute("update monetization_commands set result=%s where action='search_command' and result->>'searchId'=%s",
                          (json.dumps({'ok':True,'searchId':rid,'launchState':'deleted','candidates':[]}),rid))
        self.conn.execute("update outbox set sent_at=now() where topic='monetization.search.launch' and payload->>'resourceId'=%s",(rid,))

    def transfer(self, rid, old_owner, new_owner):
        self.lock(*('monetization:owner:' + x for x in (old_owner,new_owner)))
        r = self.resource(rid, old_owner)
        self.account(new_owner)
        if r['state'] == 'active':
            try:
                self.check_search(new_owner, rid)
            except CommandError as e:
                # The old owner must never learn IDs of the recipient's private searches.
                if e.code == 'search_quota':
                    raise CommandError('organizer_search_quota', choices=['free_slot','choose_other']) from None
                raise
        self.conn.execute('update monetization_resources set owner_id=%s where id=%s', (new_owner,rid))

    def message(self, owner, peer, *, protected=False, provenance=None):
        self.account(owner)
        pair = pair_key(owner,peer)
        self.lock('monetization:pair:' + pair)
        row = self.conn.execute("select id from monetization_sessions where pair=%s and state='active'", (pair,)).fetchone()
        if row:
            return row[0]
        if not protected and not self.plus(owner):
            ids = [r[0] for r in self.conn.execute("select id from monetization_sessions where initiator=%s "
                    "and state='active' and not protected order by id", (owner,)).fetchall()]
            if ids:
                raise CommandError('chat_quota', blockerIds=ids)
        sid = new_id('session_')
        self.conn.execute('insert into monetization_sessions(id,pair,initiator,state,opened,protected,provenance) '
                          "values (%s,%s,%s,'active',%s,%s,%s)",
                          (sid,pair,owner,self.now,protected,json.dumps(provenance or {})))
        return sid

    def end_pair(self, a, b, reason):
        # Только явное завершение или новая блокировка закрывают чатовую сессию.
        if reason not in ('end_chat', 'block'):
            raise CommandError('invalid_session_close_reason', 400)
        pair = pair_key(a,b)
        self.lock('monetization:pair:' + pair)
        self.conn.execute("update monetization_sessions set state='closed',closed=%s where pair=%s and state='active'",
                          (self.now,pair))
        self.audit(a, 'session_closed', {'pair':pair,'reason':reason})

    def link_plan(self, plan_id, a, b):
        # Историческая связь служит provenance; состояние плана не закрывает чат.
        row = self.conn.execute("select id from monetization_sessions where pair=%s and state='active'",
                                (pair_key(a,b),)).fetchone()
        if row:
            self.conn.execute('insert into monetization_plan_sessions(plan_id,session_id) values(%s,%s) '
                              'on conflict do nothing', (plan_id,row[0]))

    def protect(self, kind, rid, action, provenance):
        self.conn.execute('insert into monetization_protected values(%s,%s,%s,%s) on conflict do nothing',
                          (kind,rid,action,json.dumps(provenance)))

    def protected(self, kind, rid, action):
        return bool(self.conn.execute('select 1 from monetization_protected where kind=%s and resource_id=%s and action=%s',
                                     (kind,rid,action)).fetchone())

    def documents(self):
        return dict(self.conn.execute('select key,value from monetization_documents').fetchall())

    def save_documents(self, value):
        # This is an exact projection, not a merge: deleted account session keys
        # must not reappear on the next canonical refresh.
        self.conn.execute('delete from monetization_documents where not (key=any(%s))',(list(value),))
        self.conn.execute('''insert into monetization_documents select key,value from jsonb_each(%s::jsonb)
            on conflict(key) do update set value=excluded.value
            where monetization_documents.value is distinct from excluded.value''',
                          (json.dumps(value,ensure_ascii=False,default=str),))

    def status(self, owner):
        self.expire(owner)
        a = self.account(owner)
        plus = self.plus(owner)
        rights = entitlements(self.conn,owner,a,self.now)
        preview = (a['end'] or 0) > self.now
        searches = [dict(id=r[0],state=r[1],title=r[2].get('title',''),publishedAt=r[3]) for r in
                    self.conn.execute("select id,state,payload,published from monetization_resources where owner_id=%s and state<>'deleted' "
                                      'order by published desc nulls last,id', (owner,)).fetchall()]
        chat_rows = self.conn.execute("select id,pair from monetization_sessions where initiator=%s "
                 "and state='active' and not protected", (owner,)).fetchall()
        chats = [r[0] for r in chat_rows]
        chat_blockers = []
        for sid,pair in chat_rows:
            people=json.loads(pair)
            if len(people)==2 and owner in people:
                chat_blockers.append({'sessionId':sid,'peerId':next(p for p in people if p!=owner)})
        names=dict(self.conn.execute('select id,name from users where id=any(%s)',([b['peerId'] for b in chat_blockers],)).fetchall())
        for blocker in chat_blockers: blocker['peerName']=names.get(blocker['peerId'],blocker['peerId'])
        recoverable=[{'gid':g['id'],'title':str(g.get('title') or ''),'model':'legacy'}
                     for g in self.documents().get('_groups',[]) if g.get('role_recovery') and not g.get('host')
                     and owner in (g.get('members') or []) and g.get('state')!='cancelled']
        active = [r['id'] for r in searches if r['state']=='active']
        can_search, can_chat = plus or not active, plus or not chats
        return dict(ok=True,version=2,phase='phase2a',state='preview' if preview else ('plus' if plus else 'free'),
                    plan='plus' if plus else 'free',serverTime=self.now,previewStartedAt=a['start'],expiresAt=a['end'],
                    plusExpiresAt=rights['expiresAt'],entitlementSources=rights['sources'],
                    previewEligible=a['eligible'],previewNotice=bool(a['start'] and not a['seen']),
                    enforcementEnabled=True,purchaseAvailable=False,restoreAvailable=False,
                    permissions={'publishSearch':can_search,'initiateChat':can_chat,'reply':True,'groupChat':True,
                                 'manualCoordination':True,'basicFilters':True},
                    usage={'activeSearches':len(active),'initiatedChats':len(chats)},
                    limits={'activeSearches':None if plus else 1,'initiatedChats':None if plus else 1},
                    reasons={'publishSearch':None if can_search else 'search_quota',
                             'initiateChat':None if can_chat else 'chat_quota'},
                    blockerIds={'searches':active,'chats':chats},chatBlockers=chat_blockers,
                    searches=searches,keepSearchId=a['keep'],recoverableGroups=recoverable)


@contextlib.contextmanager
def transaction(*, projection=False):
    try:
        with connection() as conn:
            with conn.transaction():
                tx = Transaction(conn)
                ready = conn.execute("select value from monetization_meta where key='ready'").fetchone()
                if not ready or ready[0] is not True:
                    raise CommandError('monetization_migration_required',503)
                tx.lock('monetization:projection')
                release = conn.execute("select value from monetization_meta where key='release_state'").fetchone()
                if release and release[0] != 'enforce':
                    raise CommandError('monetization_release_fenced',503)
                yield tx
    except CommandError:
        raise
    except Exception as e:
        raise CommandError('monetization_unavailable',503) from e


def command_key(key):
    if not isinstance(key,str) or not key.strip() or len(key)>160:
        raise CommandError('idempotency_key_required',400)
    return key


class CommittedDenial(dict):
    """Only a validated terminal transition from the canonical adapter may use this."""


def receipt(owner, action, key, payload):
    """Short committed lookup before external preparation; execute rechecks on commit."""
    command_key(key)
    fingerprint = digest(payload)
    with transaction() as tx:
        if tx.conn.execute('select 1 from monetization_deletions where owner_id=%s',(owner,)).fetchone():
            raise CommandError('account_deleting',409)
        cached = tx.conn.execute('select payload_hash,result from monetization_commands '
                                 'where owner_id=%s and action=%s and command_key=%s',(owner,action,key)).fetchone()
        if not cached: return None
        if cached[0] != fingerprint: raise CommandError('idempotency_payload_conflict')
        return cached[1]


def execute(owner, action, key, payload, run, *, projection=False):
    command_key(key)
    fingerprint = digest(payload)
    with transaction(projection=projection) as tx:
        if owner=='system:sweep': tx.lock('monetization:owner:'+owner)
        else: tx.account(owner)
        cached = tx.conn.execute('select payload_hash,result from monetization_commands '
                                 'where owner_id=%s and action=%s and command_key=%s', (owner,action,str(key))).fetchone()
        if cached:
            if cached[0] != fingerprint:
                raise CommandError('idempotency_payload_conflict')
            return cached[1]
        result = run(tx)
        if isinstance(result,dict) and result.get('ok') is False and not isinstance(result,CommittedDenial):
            raise CommandError(result.get('error','command_failed'), result.get('httpStatus',409))
        tx.conn.execute('insert into monetization_commands values(%s,%s,%s,%s,%s,%s)',
                        (owner,action,str(key),fingerprint,json.dumps(result,ensure_ascii=False,default=str),tx.now))
        return result


def status(owner):
    with transaction(projection=True) as tx:
        return tx.status(owner)


def entitlements(conn,owner,account,now):
    """Pure resolution: independent sources; no account creation or expiry writes."""
    sources=[]
    for source,until in (('preview',account.get('end')),('paid',account.get('plus'))):
        if (until or 0)>now: sources.append({'source':source,'expiresAt':until})
    manual=conn.execute('select max(expires) from monetization_manual_grants '
                        'where owner_id=%s and revoked is null and expires>%s',(owner,now)).fetchone()[0]
    if manual: sources.append({'source':'manual','expiresAt':manual})
    return {'sources':sources,'expiresAt':max((s['expiresAt'] for s in sources),default=None)}


def projection_resources(tx, *, persist=False):
    """Batch effective expiry; O(1) SQL statements, one pass through owner buckets.

    Writers call this under the global canonical lock. Readers call it in their
    committed repeatable-read snapshot; neither path creates accounts per row.
    """
    rows=tx.conn.execute('''select r.id,r.owner_id,r.state,r.published,a.keep_search,
        greatest(coalesce(a.preview_end,0),coalesce(a.plus_until,0),coalesce(m.expires,0))>%s,
        d.owner_id is not null
        from monetization_resources r left join monetization_accounts a on a.owner_id=r.owner_id
        left join (select owner_id,max(expires) expires from monetization_manual_grants
                   where revoked is null group by owner_id) m on m.owner_id=r.owner_id
        left join monetization_deletions d on d.owner_id=r.owner_id''',(tx.now,)).fetchall()
    resources={}; buckets={}
    for rid,owner,state,published,keep,plus,deleting in rows:
        resources[rid]={'owner':owner,'state':'deleting' if deleting else state,'published':published}
        if state=='active' and not plus and not deleting and not owner.startswith('recovery:'):
            bucket=buckets.setdefault(owner,{'keep':keep,'ids':[]})
            bucket['ids'].append(rid)
    audits=[]; paused=[]
    for owner,bucket in buckets.items():
        ids=sorted(bucket['ids'],key=lambda rid:(-(resources[rid]['published'] or 0),rid))
        keep=bucket['keep'] if bucket['keep'] in ids else ids[0]
        changed=[rid for rid in ids if rid!=keep]
        if not changed: continue
        for rid in changed: resources[rid]['state']='paused'
        paused.extend(changed)
        audits.append({'owner':owner,'details':{'keep':keep,'paused':changed}})
    if persist and paused:
        tx.conn.execute("update monetization_resources set state='paused' where id=any(%s)",(paused,))
        tx.conn.execute('''insert into monetization_audit(owner_id,event,details,created)
            select x.owner,'expiry_paused',x.details,%s
            from jsonb_to_recordset(%s::jsonb) as x(owner text,details jsonb)''',(tx.now,json.dumps(audits)))
    return resources
