"""Review-one regressions: real adapters and isolated PostgreSQL, no live data."""
import concurrent.futures
import copy
import json
import os
import threading
import http.client
from http.server import ThreadingHTTPServer
import unittest
from unittest.mock import patch

import test_monetization_phase2 as phase
import test_monetization_pg as pg
from test_monetization_pg import DSN, ms


@unittest.skipUnless(DSN, 'BLOCKED: isolated PostgreSQL DSN not configured')
class ReviewOne(unittest.TestCase):
    setUpClass = classmethod(pg.PostgreSQLCommands.setUpClass.__func__)
    setUp = phase.LegacyAdapters.setUp
    tearDown = phase.LegacyAdapters.tearDown
    tearDownDB = pg.PostgreSQLCommands.tearDown
    save = phase.LegacyAdapters.save
    free = pg.PostgreSQLCommands.free

    def command(self, **body):
        class Handler: _pid = 'a'
        h = Handler()
        self.app.monetization_commands.handle(h, '/api/agent/search-command', body)
        return h.result[1]

    def test_search_keys_validated_before_preparation(self):
        class Handler: _pid='a'
        for path in ('match','plan','confirm','expand','intent-save','gintent-create','group-create'):
            with self.subTest(path=path), patch.object(self.app,'prepare_search') as prepare, patch.object(self.app,'_prepare_map_intent') as map_prepare:
                with self.assertRaises(ms.CommandError) as error:
                    self.app.monetization_commands.handle(Handler(),'/api/agent/'+path,{'commandId':{},'idem':'otherwise-valid','intent':{'topics':['coffee']}})
                self.assertEqual(error.exception.status,400);prepare.assert_not_called();map_prepare.assert_not_called()
        for operation in ('publish', 'resume', 'pause'):
            for field in ('commandId', 'idem'):
                for key in (17, {}, [], True, '', ' ', None, 'x' * 161):
                    with self.subTest(operation=operation, field=field, key=key), \
                         patch.object(self.app, 'prepare_search') as prepare:
                        with self.assertRaises(ms.CommandError) as error:
                            self.command(operation=operation, searchId='search_missing', intent={'topics':['coffee']}, **{field:key})
                        self.assertEqual(error.exception.status, 400)
                        prepare.assert_not_called()
        with ms.connection() as c:
            self.assertEqual(c.execute('select count(*) from monetization_commands').fetchone()[0], 0)
            self.assertEqual(c.execute('select count(*) from monetization_resources').fetchone()[0], 0)
            self.assertEqual(c.execute('select count(*) from outbox').fetchone()[0], 0)
        one = self.command(intent={'topics':['coffee']})
        self.assertEqual(json.loads(json.dumps(one)), self.command(intent={'topics':['coffee']}))

    def test_legacy_group_resume_uses_canonical_group_fields(self):
        result = self.app.group_create('a', 'Canonical', ['coffee'], when='18:00', area='Place',
                                       mode='hybrid', min_size=3, max_size=7, idem='legacy')
        self.assertTrue(result['ok'], result)
        with ms.transaction() as t:
            group = copy.deepcopy(t.documents()['_groups'][0])
            rid = t.resolve('group', group['id'])
            t.pause('a', rid)
        resumed = self.command(operation='resume', searchId=rid, commandId='resume-group',
                               intent={'title':'tampered', 'topics':['tampered'], 'groupSize':99})
        self.assertEqual(resumed['launchState'], 'ready')
        self.assertEqual(resumed['intent']['topics'], ['coffee'])
        with ms.transaction() as t:
            self.assertEqual(t.resolve('group', group['id']), rid)
            resource = t.resource(rid)
            self.assertEqual(resource['owner_id'], 'a')
            self.assertEqual(resource['payload']['max_size'], 7)
            self.assertEqual(t.documents()['_groups'][0]['max_size'], 7)

    def test_old_terminal_group_does_not_pause_explicit_resume(self):
        saved = self.save()
        group = self.app.gi_create('a', {'id':saved['id'], 'topics':['coffee']}, 'Coffee', idem='group')
        self.assertTrue(group['ok'], group)
        self.assertTrue(self.app.gi_close(group['group']['gid'], 'a', 'close')['ok'])
        with ms.transaction() as t: rid = t.resolve('intent', saved['id'])
        self.command(operation='resume', searchId=rid, commandId='resume')
        self.assertEqual(ms.status('a')['usage']['activeSearches'], 1)
        self.app.thread_mark_read('a', 'b')
        self.assertEqual(ms.status('a')['usage']['activeSearches'], 1)

    def test_real_ranker_group_resume_and_display_names_preserve_cards(self):
        users=[dict(id=x,name='Display '+x,age=25,verified=True,interests=['coffee'],open=True,
                    langs=['en'],vibe='chill',formats=['online'],km=1) for x in ('a','b','c','d')]
        self.app.load_candidates=self.real_candidates
        self.app._load_pool_rows=lambda:users
        self.app._people_index(force=True)
        self.app.match_candidates=self.real_match
        self.app._policy_ok_now=self.real_policy
        result=self.app.group_create('a','Canonical',['coffee'],when='18:00',area='Place',mode='online',min_size=3,max_size=7,idem='legacy')
        self.assertTrue(result['ok'],result)
        with ms.transaction() as tx:
            group=tx.documents()['_groups'][0];rid=tx.resolve('group',group['id']);tx.pause('a',rid)
        body=dict(operation='resume',searchId=rid,commandId='group-real')
        resumed=self.command(**body)
        self.assertEqual(resumed['launchState'],'ready',resumed)
        self.assertTrue(resumed['candidates'],resumed)
        self.assertNotIn('_candidate_refs',resumed)
        self.assertEqual(resumed['intent']['time'],'18:00')
        self.assertEqual(resumed['intent']['groupSize'],7)
        self.assertEqual(resumed['intent']['minSize'],3)
        ctx={'self_id':'a','self':'Display a'}
        compiled=self.app.prepare_search('/api/agent/search-command',{'intent':resumed['intent']},ctx)
        expected=self.app.render_search('/api/agent/search-command',body,compiled,ctx)
        self.assertEqual([c['name'] for c in resumed['candidates']],[c['name'] for c in expected['candidates']])
        self.assertEqual(self.command(**body)['candidates'],resumed['candidates'])
        with ms.transaction() as tx:
            refs=tx.conn.execute("select result->'_candidate_refs' from monetization_commands where command_key='group-real'").fetchone()[0]
            self.assertTrue(refs);self.assertTrue(all(r['person_id'] in ('b','c','d') for r in refs))

    def test_latest_policy_review_uses_existing_outreach_semantics(self):
        users=self.app.load_candidates()
        card={'id':'b','name':'Same name','policy':'ALLOW','can_outreach':True,'tier':'T1'}
        with patch.object(self.app,'render_search',return_value={'candidates':[card]}):
            before=self.command(intent={'topics':['coffee']},commandId='review')
        self.assertTrue(before['candidates'][0]['can_outreach'])
        users[1]['safetyFlags']=['review']
        after=self.command(intent={'topics':['coffee']},commandId='review')
        self.assertEqual(after['candidates'][0]['policy'],'REVIEW')
        self.assertFalse(after['candidates'][0]['can_outreach'])
        self.assertEqual(after['candidates'][0]['allocation_action'],'review_required')
        users[1]['safetyFlags']=['blocked']
        # A hard current gate is independent of the cached ALLOW score.
        users[1]['age']=16
        self.assertEqual(self.command(intent={'topics':['coffee']},commandId='review')['candidates'],[])

    def test_purge_redacts_foreign_ranked_receipts_structural_ids(self):
        for key,card in [('profile',{'name':'Display','profile_view':{'user_id':'b','fields':{'photo':'private'}}}),
                         ('direct',{'id':'b','name':'Display','photo':'private'})]:
            ms.execute('a','cached',key,{},lambda t,c=card:{'ok':True,'candidates':[c]})
        ms.execute('c','cached','unrelated',{},lambda t:{'ok':True,'candidates':[{'id':'db','name':'b','media':{'id':'b'}}],'text':'b'})
        self.app.purge_person('b')
        for key in ('profile','direct'):
            def forbidden(tx): self.fail('purge must retain replay fence')
            result=ms.execute('a','cached',key,{},forbidden)
            self.assertEqual(result,{'ok':True,'redacted':True,'reason':'account_deleted'})
        with ms.connection() as c:
            unrelated=c.execute("select result from monetization_commands where command_key='unrelated'").fetchone()[0]
            self.assertEqual(unrelated['candidates'][0]['id'],'db')

    def test_projection_mapping_copy_save_and_off_shadow_compatibility(self):
        for mode in ('off','shadow','enforce'):
            with patch.dict(os.environ,{'KLEAL_MONETIZATION_MODE':mode}):
                self.app.SESSION['compat']={'nested':[mode]}
                copied=copy.deepcopy(self.app.SESSION)
                self.assertEqual(json.loads(json.dumps(dict(self.app.SESSION)))['compat'],copied['compat'])
                copied['compat']['nested'].append('private')
                self.assertEqual(self.app.SESSION['compat']['nested'],[mode])
                if mode!='enforce':
                    with patch.object(self.app.db,'ENABLED',False): self.app._save_store()
                    with open(self.tmp.name+'/store.json') as f: self.assertEqual(json.load(f)['compat'],{'nested':[mode]})
                    with patch.object(self.app.db,'ENABLED',True), patch.object(self.app.db,'MIRROR_JSON',False), patch.object(self.app.db,'save_store') as save:
                        self.app._save_store();self.assertIsInstance(save.call_args.args[0],dict)
        with ms.transaction() as tx:
            doc=tx.documents();doc['committed-reader']={'value':1};tx.save_documents(doc)
        self.app.monetization_commands.refresh()
        self.assertEqual(self.app.SESSION.get('committed-reader'),{'value':1})

    def test_polls_do_not_append_receipts_explicit_commands_still_replay(self):
        first = self.save()
        with ms.connection() as c: before = c.execute('select count(*) from monetization_commands').fetchone()[0]
        for _ in range(8):
            self.app.inbox('a'); self.app.outbox('a'); self.app._gp_sweep(); self.app._mp_sweep()
        with ms.connection() as c: after = c.execute('select count(*) from monetization_commands').fetchone()[0]
        self.assertEqual(after, before)
        self.assertEqual(self.save(), first)
        self.assertEqual(ms.status('a')['usage']['activeSearches'], 1)

    def test_purge_redacts_foreign_receipt_without_repeating_approval(self):
        gid = self.app.gi_create('a', {'topics':['coffee']}, 'Coffee', idem='group')['group']['gid']
        invite = self.app.gi_invite(gid, 'a', 'b', idem='invite')['invite']['id']
        with ms.transaction() as t:
            doc = t.documents(); doc['_gintents'][0]['state'] = 'planning'; t.save_documents(doc)
        self.app.gi_respond(invite, 'b', True, 'accept')
        approved = self.app.gi_approve(gid, 'a', 'b', True, 'approve')
        self.assertTrue(approved['ok'], approved)
        ms.execute('c', 'unrelated', 'keep', {}, lambda t: {'ok':True, 'text':'b is an arbitrary substring', 'person_id':'db'})
        self.assertTrue(self.app.purge_person('b')['ok'])
        with ms.transaction() as t:
            before = t.documents()
            count = t.conn.execute('select count(*) from monetization_commands').fetchone()[0]
        replay = self.app.gi_approve(gid, 'a', 'b', True, 'approve')
        self.assertTrue(replay['ok'], replay)
        self.assertNotIn('group', replay)
        self.assertNotIn('who', replay)
        self.assertTrue(replay.get('redacted'))
        with ms.transaction() as t:
            self.assertEqual(t.documents(), before)
            self.assertEqual(t.conn.execute('select count(*) from monetization_commands').fetchone()[0], count)
            self.assertEqual(t.conn.execute("select result->>'text' from monetization_commands where owner_id='c'").fetchone()[0], 'b is an arbitrary substring')

    def test_ranking_committed_snapshot_and_latest_block_before_receipt(self):
        entered, release = threading.Event(), threading.Event()
        observed = []
        def rank(*args):
            observed.append(self.app._blocked_pair('a','b'))
            entered.set()
            if not release.wait(5): raise AssertionError('ranking barrier not released')
            observed.append(self.app._blocked_pair('a','b'))
            return {'candidates':[{'id':'b'}]}
        with patch.object(self.app, 'render_search', side_effect=rank), concurrent.futures.ThreadPoolExecutor(2) as pool:
            pending = pool.submit(self.command, intent={'topics':['coffee']}, commandId='rank')
            try:
                self.assertTrue(entered.wait(3))
                blocked = pool.submit(self.app.block_user, 'a', 'b', True, 'block').result(timeout=3)
                self.assertTrue(blocked['ok'], blocked)
            finally: release.set()
            result = pending.result(timeout=5)
        self.assertEqual(observed, [False, False], 'one consistent committed snapshot during ranking')
        self.assertEqual(result['candidates'], [])
        self.assertEqual(self.command(intent={'topics':['coffee']}, commandId='rank')['candidates'], [])

    def test_dirty_projection_is_invisible_even_during_rollback(self):
        entered, release = threading.Event(), threading.Event()
        def fail(who, idem):
            self.app.SESSION.setdefault('_blocks', {})['a'] = ['b']
            entered.set()
            if not release.wait(5): raise AssertionError('writer barrier not released')
            raise ms.CommandError('synthetic_failure', 409)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            pending = pool.submit(self.app.monetization_commands._invoke, 'fail', fail, ('a', 'rollback'), {})
            try:
                self.assertTrue(entered.wait(3))
                self.assertFalse(pool.submit(self.app._blocked_pair, 'a', 'b').result(timeout=2))
            finally: release.set()
            self.assertEqual(pending.result(timeout=5)['error'], 'synthetic_failure')
        self.assertFalse(self.app._blocked_pair('a','b'))

    def test_http_body_wait_does_not_lock_health_or_writer_in_off_and_enforce(self):
        original_read=self.app.read_json
        for mode in ('off','enforce'):
            with self.subTest(mode=mode), patch.dict(os.environ,{'KLEAL_MONETIZATION_MODE':mode}):
                entered,release=threading.Event(),threading.Event()
                def read(handler):
                    entered.set()
                    if not release.wait(5): raise AssertionError('body barrier not released')
                    return original_read(handler)
                self.app.send_json=lambda h,status,obj:self.app._send_json_raw(h,status,obj)
                server=ThreadingHTTPServer(('127.0.0.1',0),self.app.H)
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                def request(method,path):
                    conn=http.client.HTTPConnection(*server.server_address,timeout=3)
                    conn.request(method,path,'{}' if method=='POST' else None)
                    r=conn.getresponse(); value=(r.status,r.read());conn.close();return value
                try:
                    with patch.object(self.app,'read_json',side_effect=read), concurrent.futures.ThreadPoolExecutor(3) as pool:
                        slow=pool.submit(request,'POST','/api/agent/search-command')
                        try:
                            self.assertTrue(entered.wait(3))
                            self.assertEqual(pool.submit(request,'GET','/health').result(timeout=2)[0],200)
                            self.assertTrue(pool.submit(self.save,key='body-'+mode).result(timeout=2)['ok'])
                        finally: release.set()
                        slow.result(timeout=3)
                finally: server.shutdown();server.server_close();thread.join(2)

    def test_clock_after_lock_queue_controls_expiry_and_preview_start(self):
        queued=threading.Event()
        original=ms.Transaction.lock
        waiting_thread=[None]
        def lock(tx,*keys):
            if threading.get_ident()==waiting_thread[0] and 'monetization:projection' in keys: queued.set()
            return original(tx,*keys)
        with ms.transaction() as t:
            t.publish('a',{'title':'existing'})
            t.conn.execute('update monetization_accounts set preview_start=%s,preview_end=%s where owner_id=%s',
                           (t.now-1209600+1,t.now+1,'a'))
        def wait_publish(owner):
            waiting_thread[0]=threading.get_ident()
            return ms.execute(owner,'publish','wait-'+owner,{},lambda t:{'ok':True,'id':t.publish(owner,{})})
        with patch.object(ms.Transaction,'lock',lock), concurrent.futures.ThreadPoolExecutor(1) as pool:
            for owner in ('a','b'):
                queued.clear()
                with ms.connection() as c, c.transaction():
                    c.execute("select pg_advisory_xact_lock(hashtextextended('monetization:projection',0))")
                    future=pool.submit(wait_publish,owner)
                    self.assertTrue(queued.wait(3))
                    # Real server-clock advancement AFTER the waiter reached the barrier.
                    c.execute('select pg_sleep(2)')
                    release_time=int(c.execute('select extract(epoch from clock_timestamp())::bigint').fetchone()[0])
                if owner=='a':
                    with self.assertRaises(ms.CommandError) as error: future.result(timeout=3)
                    self.assertEqual(error.exception.code,'search_quota')
                else:
                    self.assertTrue(future.result(timeout=3)['ok'])
                    self.assertGreaterEqual(ms.status('b')['previewStartedAt'],release_time)

    def test_room_alternative_and_fallback_wire_are_retained(self):
        intent={'title':'Coffee','topics':['coffee'],'mode':'offline','allowOnlineFallback':True}
        room=self.app._online_fallback(intent)['room']
        with patch.object(self.app,'render_search',return_value={'candidates':[room], 'fallback':self.app._online_fallback(intent)}):
            result=self.command(intent=intent,commandId='room')
        self.assertEqual(result['candidates'],[room])
        self.assertEqual(result['fallback'],self.app._online_fallback(intent))


if __name__ == '__main__': unittest.main()
