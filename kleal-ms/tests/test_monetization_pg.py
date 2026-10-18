"""Real isolated PostgreSQL tests; absence is explicitly SKIP/BLOCKED, never PASS.

KLEAL_MONETIZATION_TEST_DSN must reference a loopback kleal_monetization_test DB.
Each test uses a new PostgreSQL schema, with synthetic account IDs only.
"""
import concurrent.futures
import multiprocessing
import os
from pathlib import Path
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'shared'),str(ROOT/'tools')]
import monetization_store as ms
import monetization_migrate as migration
import monetization_rehearse as rehearsal
import monetization_safety as safety

DSN = os.environ.get('KLEAL_MONETIZATION_TEST_DSN','')


def worker(dsn,schema,key,kind='publish',peer='b'):
    import psycopg_pool
    ms.db.ENABLED = True
    ms.db.MIRROR_JSON = False
    ms.db._pool = psycopg_pool.ConnectionPool(dsn,kwargs={'options':'-c search_path='+schema},min_size=1,max_size=2)
    try:
        owner='b' if kind=='reply' else 'a'
        fn = (lambda t: {'ok':True,'id':t.publish(owner,{'title':key})}) if kind=='publish' else (
             lambda t: {'ok':True,'id':t.message(owner,peer)})
        return ms.execute(owner,kind,key,{'title':key},fn)
    except ms.CommandError as e:
        return e.response()
    finally:
        ms.db._pool.close()


def crash_worker(dsn,schema):
    import psycopg_pool
    ms.db.ENABLED=True; ms.db.MIRROR_JSON=False
    ms.db._pool=psycopg_pool.ConnectionPool(dsn,kwargs={'options':'-c search_path='+schema},min_size=1,max_size=1)
    with ms.transaction() as t:
        t.publish('a',{'title':'never committed'})
        os._exit(7)


@unittest.skipUnless(DSN,'BLOCKED: isolated PostgreSQL DSN not configured')
class PostgreSQLCommands(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        safety.validate_test_dsn(DSN)
        import psycopg
        import psycopg_pool
        cls.psycopg,cls.poolclass = psycopg,psycopg_pool.ConnectionPool

    def setUp(self):
        self.schema = 'test_' + uuid.uuid4().hex
        with self.psycopg.connect(DSN,autocommit=True) as c:
            safety.guard(c,require_schema=False)
            c.execute('create schema '+self.schema)
        self.prior = (ms.db.ENABLED,ms.db.MIRROR_JSON,ms.db._pool)
        ms.db.ENABLED,ms.db.MIRROR_JSON = True,False
        ms.db._pool = self.poolclass(DSN,kwargs={'options':'-c search_path='+self.schema},min_size=1,max_size=6)
        with ms.connection() as c:
            migration.migrate(c,{'synthetic':True,'users':[{'id':x} for x in ('a','b','c','d')],'session':{}})

    def tearDown(self):
        ms.db._pool.close()
        ms.db.ENABLED,ms.db.MIRROR_JSON,ms.db._pool = self.prior
        # Drop only the exact UUID-named schema created by this test.
        with self.psycopg.connect(DSN,autocommit=True) as c:
            c.execute('drop schema '+self.schema+' cascade')

    def free(self,owner='a'):
        with ms.transaction() as t:
            t.account(owner)
            t.conn.execute('update monetization_accounts set eligible=false where owner_id=%s',(owner,))

    def publish(self,key='one',owner='a',**kwargs):
        return ms.execute(owner,'publish',key,{'key':key,**kwargs},
                          lambda t:{'ok':True,'id':t.publish(owner,{'title':key},**kwargs)})

    def test_grant_atomic_exact_duration_and_retry(self):
        r = self.publish()
        self.assertEqual(r,self.publish())
        s = ms.status('a')
        self.assertEqual(s['expiresAt']-s['previewStartedAt'],1209600)
        self.assertEqual(s['usage']['activeSearches'],1)
        self.assertEqual(s['state'],'preview')

    def test_synthetic_backup_restore_and_exact_legacy_rollback(self):
        self.publish()
        with ms.transaction() as t:
            t.save_documents({'_intents':[{'id':'i','owner_id':'a','title':'current'}],'survivor':{'new':True}})
            t.alias('intent','i',t.conn.execute('select id from monetization_resources').fetchone()[0])
            t.conn.execute("insert into store_kv(key,value) values('deleted','{}'),('survivor','{\"stale\":true}')")
            snapshot=rehearsal.backup(t.conn)
        target='test_restore_'+uuid.uuid4().hex
        try:
            with self.psycopg.connect(DSN) as c:
                c.execute('create schema '+target);c.execute('set search_path to '+target)
                rehearsal.restore(c,snapshot)
                self.assertEqual(rehearsal.backup(c),snapshot)
                result=rehearsal.canonical_to_legacy(c)
                self.assertFalse(result['activationChanged'])
                self.assertEqual(dict(c.execute('select key,value from store_kv').fetchall()),ms.Transaction(c).documents())
                self.assertFalse(c.execute("select 1 from store_kv where key='deleted'").fetchone())
                self.assertEqual(c.execute("select value->>'new' from store_kv where key='survivor'").fetchone()[0],'true')
                self.assertEqual(c.execute('select count(*) from monetization_commands').fetchone()[0],1)
                self.assertEqual(c.execute('select count(*) from outbox').fetchone()[0],1)
                self.assertTrue(c.execute("select value from monetization_meta where key='ready'").fetchone()[0])
                with self.assertRaisesRegex(ValueError,'empty schema'): rehearsal.restore(c,snapshot)
        finally:
            with self.psycopg.connect(DSN,autocommit=True) as c: c.execute('drop schema if exists '+target+' cascade')

    def test_equal_expiry_timestamps_use_stable_resource_id(self):
        with ms.transaction() as t:
            for rid in ('search_z','search_a','search_m'):
                t.conn.execute("insert into monetization_resources(id,owner_id,state,published,payload) values(%s,'a','active',42,'{}')",(rid,))
            t.conn.execute("update monetization_accounts set eligible=false,preview_start=%s,preview_end=%s where owner_id='a'",(t.now-1209600,t.now))
        status=ms.status('a')
        self.assertEqual(status['blockerIds']['searches'],['search_a'])
        with ms.transaction() as t:
            t.pause('a','search_a')
        self.assertEqual(ms.status('a')['usage']['activeSearches'],0)

    def test_migration_closed_plan_does_not_guess_current_session(self):
        schema='test_'+uuid.uuid4().hex
        try:
            with self.psycopg.connect(DSN) as c:
                c.execute('create schema '+schema);c.execute('set search_path to '+schema)
                migration.migrate(c,{'synthetic':True,'users':[{'id':'a'},{'id':'b'}],'session':{
                    '_messages':[{'id':'current','from':'a','to':'b'}],
                    '_mplans':[{'id':'historical','host':'a','guest':'b','state':'done'}]}})
                self.assertEqual(c.execute("select state from monetization_sessions").fetchone()[0],'active')
                self.assertEqual(c.execute('select count(*) from monetization_plan_sessions').fetchone()[0],0)
        finally:
            with self.psycopg.connect(DSN,autocommit=True) as c: c.execute('drop schema if exists '+schema+' cascade')

    def test_expiry_without_choice_keeps_last_published_search(self):
        with ms.transaction() as t:
            for rid,published in [('search_a',t.now-30),('search_z',t.now-10),('search_m',t.now-20)]:
                t.conn.execute("insert into monetization_resources(id,owner_id,state,published,payload) values(%s,'a','active',%s,'{}')",(rid,published))
            t.conn.execute("update monetization_accounts set eligible=false,preview_start=%s,preview_end=%s where owner_id='a'",(t.now-1209600,t.now))
        status=ms.status('a')
        self.assertEqual(status['blockerIds']['searches'],['search_z'])
        self.assertEqual({s['id']:s['state'] for s in status['searches']},
                         {'search_a':'paused','search_m':'paused','search_z':'active'})

    def test_legacy_status_preview_is_audited_once_without_consuming_eligibility(self):
        schema='test_'+uuid.uuid4().hex
        data={'synthetic':True,'users':[{'id':'legacy'}],'session':{},
              'legacy_preview':{'legacy':{'started':1,'expires':1209601}}}
        try:
            with self.psycopg.connect(DSN) as c:
                c.execute('create schema '+schema);c.execute('set search_path to '+schema)
                migration.migrate(c,data)
                self.assertTrue(migration.migrate(c,data)['already'])
                eligible,start,provenance=c.execute('select eligible,preview_start,eligibility_provenance from monetization_accounts').fetchone()
                self.assertTrue(eligible);self.assertIsNone(start)
                self.assertEqual(provenance['legacyStatusOnly'],data['legacy_preview']['legacy'])
                self.assertEqual(c.execute("select count(*) from monetization_audit where event='preview_eligibility_migrated'").fetchone()[0],1)
        finally:
            with self.psycopg.connect(DSN,autocommit=True) as c:
                c.execute('drop schema if exists '+schema+' cascade')

    def test_conflicting_payload_and_scoped_owners(self):
        self.publish()
        with self.assertRaises(ms.CommandError) as e:
            ms.execute('a','publish','one',{'different':True},lambda t:{'ok':True})
        self.assertEqual(e.exception.code,'idempotency_payload_conflict')
        self.publish(owner='b')
        self.assertEqual(ms.status('b')['usage']['activeSearches'],1)

    def test_rollback_no_phantom_grant_resource_or_outbox(self):
        def fail(t):
            t.publish('a',{})
            raise RuntimeError('crash before commit')
        with self.assertRaises(ms.CommandError):
            ms.execute('a','publish','crash',{},fail)
        self.assertIsNone(ms.status('a')['previewStartedAt'])
        with ms.connection() as c:
            self.assertEqual(c.execute('select count(*) from outbox').fetchone()[0],0)
            self.assertEqual(c.execute('select count(*) from monetization_resources').fetchone()[0],0)

    def test_two_process_publication_and_restart_retry(self):
        self.free()
        ctx = multiprocessing.get_context('spawn')
        with concurrent.futures.ProcessPoolExecutor(2,mp_context=ctx) as pool:
            results = list(pool.map(worker,[DSN]*2,[self.schema]*2,['one','two']))
        self.assertEqual(sum(r.get('ok') is True for r in results),1)
        self.assertEqual(sum(r.get('error')=='search_quota' for r in results),1)
        self.assertEqual(ms.status('a')['usage']['activeSearches'],1)
        key = 'one' if results[0].get('ok') else 'two'
        with concurrent.futures.ProcessPoolExecutor(1,mp_context=ctx) as pool:
            retried = pool.submit(worker,DSN,self.schema,key).result()
        self.assertEqual(retried, next(r for r in results if r.get('ok')))

    def test_process_death_rolls_back_database(self):
        child=multiprocessing.get_context('spawn').Process(target=crash_worker,args=(DSN,self.schema))
        child.start(); child.join(10)
        self.assertEqual(child.exitcode,7)
        self.assertIsNone(ms.status('a')['previewStartedAt'])
        self.assertEqual(ms.status('a')['usage']['activeSearches'],0)
        self.assertTrue(self.publish()['ok'])

    def test_two_process_meaningful_events_create_one_immutable_grant(self):
        with concurrent.futures.ProcessPoolExecutor(2,mp_context=multiprocessing.get_context('spawn')) as pool:
            results=list(pool.map(worker,[DSN]*2,[self.schema]*2,['first','second']))
        self.assertTrue(all(r.get('ok') for r in results),results)
        before=ms.status('a')
        self.assertEqual(before['expiresAt']-before['previewStartedAt'],1209600)
        self.assertEqual(before['usage']['activeSearches'],2)
        with ms.transaction() as t:
            self.assertEqual(t.conn.execute("select count(*) from monetization_audit where owner_id='a' and event='preview_meaningful_use'").fetchone()[0],1)
        with concurrent.futures.ProcessPoolExecutor(1,mp_context=multiprocessing.get_context('spawn')) as pool:
            replay=pool.submit(worker,DSN,self.schema,'first').result()
        self.assertEqual(replay,results[0])
        after=ms.status('a')
        self.assertEqual((after['previewStartedAt'],after['expiresAt']),(before['previewStartedAt'],before['expiresAt']))

    def test_opposite_first_messages_choose_one_initiator(self):
        self.free('a');self.free('b')
        with concurrent.futures.ProcessPoolExecutor(2,mp_context=multiprocessing.get_context('spawn')) as pool:
            first=pool.submit(worker,DSN,self.schema,'first','message','b')
            second=pool.submit(worker,DSN,self.schema,'reply','reply','a')
            a,b=first.result(),second.result()
        self.assertEqual(a['id'],b['id'])
        self.assertEqual(ms.status('a')['usage']['initiatedChats']+ms.status('b')['usage']['initiatedChats'],1)

    def test_swap_is_atomic_and_owner_checked(self):
        self.free()
        one = self.publish()['id']
        with self.assertRaises(ms.CommandError):
            self.publish('two')
        two = self.publish('two',swap=one)['id']
        self.assertEqual(ms.status('a')['blockerIds']['searches'],[two])
        with self.assertRaises(ms.CommandError):
            self.publish('attack',owner='b',rid=two)

    def test_expiry_selected_and_no_automatic_restart(self):
        one,two = self.publish()['id'],self.publish('two')['id']
        with ms.transaction() as t:
            t.conn.execute('update monetization_accounts set keep_search=%s,preview_start=%s,preview_end=%s where owner_id=%s',
                           (one,t.now-1209601,t.now-1,'a'))
        s = ms.status('a')
        self.assertEqual(s['blockerIds']['searches'],[one])
        with ms.transaction() as t:
            t.conn.execute('update monetization_accounts set plus_until=%s where owner_id=%s',(t.now+1000,'a'))
        self.assertEqual(ms.status('a')['blockerIds']['searches'],[one])

    def test_first_message_response_and_end(self):
        self.free()
        with ms.transaction() as t:
            sid = t.message('a','b')
            self.assertEqual(sid,t.message('b','a'))
            with self.assertRaises(ms.CommandError):
                t.message('a','c')
            t.end_pair('a','b','end_chat')
            self.assertNotEqual(sid,t.message('a','c'))
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],1)

    def test_plan_lifecycle_cannot_be_used_to_close_chat(self):
        self.free()
        with ms.transaction() as t:
            current = t.message('a','b')
            t.link_plan('plan_old','a','b')
            for reason in ('plan_terminal','done','cancelled','expired','feedback','admin_ban'):
                with self.subTest(reason=reason):
                    with self.assertRaises(ms.CommandError) as denied:
                        t.end_pair('a','b',reason)
                    self.assertEqual(denied.exception.code,'invalid_session_close_reason')
            self.assertEqual(t.message('a','b'),current)
            self.assertEqual(t.conn.execute('select session_id from monetization_plan_sessions').fetchone()[0],current)
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],1)

    def test_plan_continuation_does_not_take_new_slot(self):
        self.free()
        with ms.transaction() as t:
            t.message('a','b')
            t.message('a','c',protected=True,provenance={'planId':'plan_c'})
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],1)

    def test_transfer_blocker_ids_private_and_role_unchanged(self):
        self.free('a'); self.free('b')
        one,two = self.publish()['id'],self.publish(owner='b')['id']
        with self.assertRaises(ms.CommandError) as e:
            ms.execute('a','transfer','role',{},lambda t:t.transfer(one,'a','b'),projection=True)
        self.assertEqual(e.exception.code,'organizer_search_quota')
        self.assertNotIn('blockerIds',e.exception.details)
        with ms.transaction() as t:
            self.assertEqual(t.resource(one)['owner_id'],'a')
            t.pause('b',two)
            t.transfer(one,'a','b')
        self.assertEqual(ms.status('b')['usage']['activeSearches'],1)

    def test_paused_group_transfer_does_not_consume_slot(self):
        self.free('a'); self.free('b')
        one = self.publish()['id']; self.publish(owner='b')
        with ms.transaction() as t:
            t.pause('a',one); t.transfer(one,'a','b')
        self.assertEqual(ms.status('b')['usage']['activeSearches'],1)

    def test_protected_provenance_exact_resource_action(self):
        with ms.transaction() as t:
            t.protect('invite','old','accept',{'source':'migration'})
            self.assertTrue(t.protected('invite','old','accept'))
            self.assertFalse(t.protected('invite','new','accept'))
            self.assertFalse(t.protected('invite','old','send'))


if __name__=='__main__':
    unittest.main()
