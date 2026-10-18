"""Review 5: actual HTTP/PG, writer barriers and host-local durability only."""
import concurrent.futures
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

import test_monetization_phase2 as phase
import test_monetization_pg as pg
import test_monetization_review2 as review2
import test_monetization_production as production
from test_monetization_pg import DSN, ms


@unittest.skipUnless(DSN,'BLOCKED: isolated PostgreSQL DSN not configured')
class ReviewFive(unittest.TestCase):
    setUpClass=classmethod(pg.PostgreSQLCommands.setUpClass.__func__)
    setUp=phase.LegacyAdapters.setUp
    tearDown=phase.LegacyAdapters.tearDown
    tearDownDB=pg.PostgreSQLCommands.tearDown
    save=phase.LegacyAdapters.save
    free=pg.PostgreSQLCommands.free
    command=review2.ReviewTwo.command
    server=review2.ReviewTwo.server
    request=review2.ReviewTwo.request

    def test_proposal_content_bound_to_current_resource_and_old_agreement_preserved(self):
        saved=self.save()
        with ms.transaction() as tx:
            rid=tx.resolve('intent',saved['id']);before=copy.deepcopy(tx.documents())
        forged={'id':saved['id'],'_searchId':rid,'topics':['tennis'],'title':'Tennis','time':'tomorrow','place':'Other place'}
        denied=self.app.propose('a','b',forged,'note','forged')
        self.assertEqual(denied['error'],'search_content_conflict')
        with ms.transaction() as tx:self.assertEqual(tx.documents(),before)
        valid={'id':saved['id'],'_searchId':rid,'topics':['coffee']}
        result=self.app.propose('a','b',valid,'kept note','current')
        self.assertTrue(result['ok'],result)
        with ms.transaction() as tx:
            request=tx.documents()['_requests'][0]
            self.assertEqual(request['intent']['topics'],['coffee']);self.assertEqual(request['note'],'kept note')
        self.assertTrue(self.app.save_intent('Same name',{'topics':['tea']},'Tea',saved['id'],True,owner_id='a',idem='edited')['ok'])
        self.assertEqual(self.app.propose('a','c',valid,'stale','stale')['error'],'search_content_conflict')
        self.assertEqual(self.app.propose('a','b',valid,'kept note','current'),result)
        current=dict(valid,topics=['tea'])
        self.assertTrue(self.app.propose('a','c',current,'current tea','tea')['ok'])

    def test_publication_generation_fences_slow_completions_in_both_orders(self):
        for order in ('old-first','new-first'):
            with self.subTest(order=order):
                entered=threading.Event();release_a=threading.Event();release_b=threading.Event();entered_b=threading.Event()
                def rank(path,body,intent,ctx):
                    if body['commandId'].endswith('-a'): entered.set();self.assertTrue(release_a.wait(5))
                    else: entered_b.set();self.assertTrue(release_b.wait(5))
                    return {'candidates':[{'id':'b','score':1 if body['commandId'].endswith('-a') else 2}]}
                saved=self.save(key=order)
                with ms.transaction() as tx:rid=tx.resolve('intent',saved['id'])
                with patch.object(self.app,'render_search',rank),concurrent.futures.ThreadPoolExecutor(2) as workers:
                    a=workers.submit(self.command,intent={'topics':['coffee']},searchId=rid,commandId=order+'-a')
                    self.assertTrue(entered.wait(3))
                    b=workers.submit(self.command,intent={'topics':['tea']},searchId=rid,commandId=order+'-b')
                    self.assertTrue(entered_b.wait(3))
                    with ms.transaction() as tx:
                        generation=tx.resource(rid)['generation'];self.assertEqual(tx.resource(rid)['payload']['intent']['topics'],['tea'])
                    if order=='old-first':release_a.set();old=a.result(3);release_b.set();new=b.result(3)
                    else:release_b.set();new=b.result(3);release_a.set();old=a.result(3)
                self.assertEqual(old['launchState'],'superseded');self.assertEqual(old['candidates'],[])
                self.assertEqual(new['launchState'],'ready');self.assertEqual(new['candidates'][0]['score'],2)
                with ms.transaction() as tx:
                    row=tx.resource(rid);self.assertEqual((row['generation'],row['launchState']),(generation,'ready'))
                    self.assertEqual(row['payload']['intent']['topics'],['tea'])
                with patch.object(self.app,'render_search',side_effect=AssertionError('no rerank')):
                    old=self.command(intent={'topics':['coffee']},searchId=rid,commandId=order+'-a')
                self.assertEqual(old['candidates'],[])
                with ms.transaction() as tx:tx.pause('a',rid)
                self.assertEqual(self.command(intent={'topics':['coffee']},searchId=rid,commandId=order+'-a')['launchState'],'paused')

    def test_rank_group_resume_and_deleted_fence_prior_generation(self):
        saved=self.save()
        group=self.app.gi_create('a',{'id':saved['id'],'topics':['coffee']},'Coffee',idem='group')['group']['gid']
        first=self.command(operation='rank_group',groupId=group,commandId='rank-one')
        second=self.command(operation='rank_group',groupId=group,commandId='rank-two')
        self.assertEqual(first['searchId'],second['searchId'])
        self.assertEqual(self.command(operation='rank_group',groupId=group,commandId='rank-one')['launchState'],'superseded')
        with ms.transaction() as tx:tx.pause('a',first['searchId'])
        self.command(operation='resume',searchId=first['searchId'],commandId='resume')
        self.assertEqual(self.command(operation='rank_group',groupId=group,commandId='rank-two')['launchState'],'superseded')
        with ms.transaction() as tx:tx.conn.execute("update monetization_resources set state='deleted' where id=%s",(first['searchId'],))
        with self.assertRaises(ms.CommandError) as error:self.command(operation='rank_group',groupId=group,commandId='rank-two')
        self.assertEqual(error.exception.code,'search_deleted')

    def test_startup_worker_skips_superseded_pending_generation_without_ranking(self):
        cmd=self.app.monetization_commands;saved=self.save()
        with ms.transaction() as tx:rid=tx.resolve('intent',saved['id'])
        with patch.object(self.app,'render_search',side_effect=RuntimeError('interrupted')):
            old=self.command(intent={'topics':['coffee']},searchId=rid,commandId='startup-old')
            new=self.command(intent={'topics':['tea']},searchId=rid,commandId='startup-new')
        with ms.transaction() as tx:generation=tx.resource(rid)['generation']
        calls=[]
        def rank(path,body,*args):calls.append(body['commandId']);return {'candidates':[]}
        with patch.object(self.app,'render_search',rank):self.assertEqual(cmd.drain_launches(10),3)
        self.assertEqual(calls,['startup-new'])
        with ms.transaction() as tx:
            resource=tx.resource(rid)
            self.assertEqual((resource['generation'],resource['launchState']),(generation,'ready'))
            self.assertEqual(resource['payload']['intent']['topics'],['tea'])
        with patch.object(self.app,'render_search',side_effect=AssertionError('no rerank')):
            old=self.command(intent={'topics':['coffee']},searchId=rid,commandId='startup-old')
        self.assertEqual((old['launchState'],old['candidates']),('superseded',[]))

    def test_cached_profile_changes_remove_all_old_nested_disclosure_without_rerank(self):
        users=self.app.load_candidates();users[1].update(photo='/old-photo',bio='Old secret bio',receiving={'disclosure_stage':'full'})
        card={'id':'b','name':'Same name','score':.9,'photo':'/old-photo','bio':'Old secret bio','profile_view':{'user_id':'b','bio':'Old secret bio'}}
        body={'intent':{'topics':['coffee']},'commandId':'profile'}
        with patch.object(self.app,'render_search',return_value={'candidates':[card,{'id':'c','score':.8}],
                                                               'group':{'members':[card]}}):
            original=self.command(**body)
        self.assertEqual(len(original['candidates']),2)
        users[1].pop('photo');users[1].pop('bio');users[1]['receiving']['disclosure_stage']='match_only'
        with patch.object(self.app,'render_search',side_effect=AssertionError('must not rerank')):
            replay=self.command(**body)
        self.assertEqual(replay['candidates'],[{'id':'c','score':.8}]);self.assertNotIn('group',replay)
        self.assertNotIn('Old secret',json.dumps(replay));self.assertNotIn('/old-photo',json.dumps(replay))
        # Changes during ranking are checked at the same commit boundary.
        def rank(*args):users[2]['bio']='changed while ranking';return {'candidates':[{'id':'c','bio':'stale'}]}
        with patch.object(self.app,'render_search',rank):latest=self.command(intent={'topics':['tea']},commandId='commit-profile')
        self.assertEqual(latest['candidates'],[])

    def accepted_pair(self):
        with ms.transaction() as tx:
            doc=tx.documents();doc['_requests']=[{'id':'ab','from':'a','to':'b','status':'accepted'}];tx.save_documents(doc)

    def test_real_http_end_reopen_end_and_stale_session_denial(self):
        self.accepted_pair()
        self.assertTrue(self.app.send_message('a','b','first',client_id='first')['ok'])
        first_session=self.app.monetization_commands.chat_states('a',['b'])['b']['sessionId']
        body={'with_id':'b','sessionId':first_session,'idem':'first-end'}
        with self.server() as (server,_):
            code,ended=self.request(server,'/api/agent/thread-end',body)
            self.assertEqual(code,200,ended);self.assertTrue(ended['ok'])
            self.assertEqual(ms.status('a')['usage']['initiatedChats'],0)
            self.assertTrue(self.app.send_message('a','b','reopened',client_id='reopen')['ok'])
            second_session=self.app.monetization_commands.chat_states('a',['b'])['b']['sessionId']
            self.assertNotEqual(first_session,second_session)
            self.assertEqual(self.request(server,'/api/agent/thread-end',body),(code,ended))
            self.assertEqual(ms.status('a')['usage']['initiatedChats'],1,'cached old end must not close new session')
            _,denied=self.request(server,'/api/agent/thread-end',dict(body,idem='stale-new-key'))
            self.assertEqual(denied['error'],'chat_session_changed')
            self.assertEqual(ms.status('a')['usage']['initiatedChats'],1)
            _,new=self.request(server,'/api/agent/thread-end',dict(body,idem='second-end',sessionId=second_session))
            self.assertTrue(new['ok'],new);self.assertEqual(ms.status('a')['usage']['initiatedChats'],0)
        with ms.transaction() as tx:
            messages=tx.documents()['_messages'];self.assertEqual(sum(bool(m.get('sys')) for m in messages),2)
            self.assertEqual([m['text'] for m in messages if not m.get('sys')],['first','reopened'])

    def test_cleanup_writer_order_and_missing_file_retry_are_atomic(self):
        self.accepted_pair();cmd=self.app.monetization_commands
        voice=self.app.voice_store('test.m4a','audio/mp4',b'synthetic audio',1000)
        filename=voice['url'].rsplit('/',1)[-1];file=Path(self.app.VOICE_DIR)/filename
        def queue():
            with ms.transaction() as tx:ms.db.outbox_put('monetization.media.cleanup',{'kind':'voice','name':filename},conn=tx.conn)
        queue()
        self.assertTrue(self.app.send_message('a','b','',voice=voice,client_id='writer-first')['ok'])
        self.assertEqual(cmd.drain_cleanup(),1);self.assertTrue(file.exists())
        with ms.transaction() as tx:
            doc=tx.documents();doc['_messages']=[];doc['_idem']={};tx.save_documents(doc)
        queue();at_unlink=threading.Event();release=threading.Event();at_lock=threading.Event();original_remove=os.remove;original_lock=ms.Transaction.lock
        def remove(path):at_unlink.set();self.assertTrue(release.wait(3));return original_remove(path)
        def lock(tx,*keys):
            if 'monetization:projection' in keys and at_unlink.is_set():at_lock.set()
            return original_lock(tx,*keys)
        with patch.object(cmd.os,'remove',remove),patch.object(ms.Transaction,'lock',lock),concurrent.futures.ThreadPoolExecutor(2) as workers:
            cleanup=workers.submit(cmd.drain_cleanup);self.assertTrue(at_unlink.wait(3))
            writer=workers.submit(self.app.send_message,'a','b','',voice=voice,client_id='writer-after')
            self.assertTrue(at_lock.wait(3));self.assertFalse(writer.done());release.set()
            self.assertEqual(cleanup.result(3),1);self.assertEqual(writer.result(3)['error'],'media_not_found')
        self.assertFalse(file.exists())
        queue();self.assertEqual(cmd.drain_cleanup(),1,'FileNotFound is completed idempotently')
        with ms.transaction() as tx:self.assertFalse(tx.documents().get('_messages'))
        queue()
        with patch.object(cmd.os,'remove',side_effect=OSError('temporary filesystem error')):
            self.assertEqual(cmd.drain_cleanup(),0)
        with ms.transaction() as tx:
            job=tx.conn.execute("select id,attempts,last_error,sent_at from outbox where topic='monetization.media.cleanup' order by id desc limit 1").fetchone()
            self.assertEqual(job[1:],(1,'cleanup_retry_required',None))
            tx.conn.execute('update outbox set next_try=now() where id=%s',(job[0],))
        self.assertEqual(cmd.drain_cleanup(),1,'retry recovers after filesystem error')

    def test_worker_claims_only_job_about_to_execute_and_fences_abandoned_token(self):
        cmd=self.app.monetization_commands
        with patch.object(self.app,'render_search',side_effect=RuntimeError('pending')):
            self.command(intent={'topics':['coffee']},commandId='job-a')
            self.command(intent={'topics':['tea']},commandId='job-b')
        entered=threading.Event();release=threading.Event();calls=[]
        def rank(path,body,*args):
            calls.append(body['commandId'])
            if body['commandId']=='job-a':entered.set();self.assertTrue(release.wait(5))
            return {'candidates':[]}
        with patch.object(self.app,'render_search',rank),concurrent.futures.ThreadPoolExecutor(2) as workers:
            first=workers.submit(cmd.drain_launches,2);self.assertTrue(entered.wait(3))
            with ms.transaction() as tx:
                next_job=tx.conn.execute("select payload,next_try<=clock_timestamp() from outbox where payload->>'commandKey'='job-b'").fetchone()
                self.assertTrue(next_job[1]);self.assertNotIn('_leaseToken',next_job[0])
            second=workers.submit(cmd.drain_launches,2);self.assertEqual(second.result(3),1)
            release.set();self.assertEqual(first.result(3),1)
        self.assertCountEqual(calls,['job-a','job-b'])
        with ms.transaction() as tx:
            row=tx.conn.execute("select id,payload->>'_leaseToken' from outbox where payload->>'commandKey'='job-a'").fetchone()
            tx.conn.execute("update outbox set sent_at=null,next_try=clock_timestamp()-interval '1 second' where id=%s",(row[0],))
            with self.assertRaises(ms.CommandError):cmd.require_launch_lease(tx,*row)
        self.assertEqual(cmd.drain_launches(1),1,'abandoned lease recovers already committed receipt')

    def test_lease_renewal_checks_owner_and_never_extends_past_bounded_deadline(self):
        cmd=self.app.monetization_commands
        with ms.transaction() as tx:
            ms.db.outbox_put('monetization.search.launch',{'ownerId':'a','_leaseToken':'owner-token'},conn=tx.conn)
            jid=tx.conn.execute("select max(id) from outbox").fetchone()[0]
            tx.conn.execute("update outbox set next_try=clock_timestamp()+interval '5 seconds' where id=%s",(jid,))
        with patch.object(cmd.time,'monotonic',return_value=100):
            self.assertTrue(cmd.renew_launch_lease(jid,'owner-token',700))
        with ms.transaction() as tx:
            seconds=tx.conn.execute('select extract(epoch from next_try-clock_timestamp()) from outbox where id=%s',(jid,)).fetchone()[0]
            self.assertGreater(seconds,110);self.assertLessEqual(seconds,120)
        with patch.object(cmd.time,'monotonic',return_value=699):
            self.assertTrue(cmd.renew_launch_lease(jid,'owner-token',700))
        with ms.transaction() as tx:
            before=tx.conn.execute('select next_try,extract(epoch from next_try-clock_timestamp()) from outbox where id=%s',(jid,)).fetchone()
            self.assertLessEqual(before[1],1)
        with patch.object(cmd.time,'monotonic',return_value=700):
            self.assertFalse(cmd.renew_launch_lease(jid,'owner-token',700))
        with ms.transaction() as tx:
            self.assertEqual(tx.conn.execute('select next_try from outbox where id=%s',(jid,)).fetchone()[0],before[0])
            tx.conn.execute("update outbox set payload=jsonb_set(payload,'{_leaseToken}','\"new-owner\"'),next_try=clock_timestamp()+interval '120 seconds' where id=%s",(jid,))
        with patch.object(cmd.time,'monotonic',return_value=101),self.assertRaises(ms.CommandError) as lost:
            cmd.renew_launch_lease(jid,'owner-token',700)
        self.assertEqual(lost.exception.code,'launch_lease_lost')

    def test_scalar_and_confirmation_validation_keeps_wire_status_valid(self):
        statuses=[]
        invalid=[{'title':{}},{'searchId':12},{'searchId':[]},{'swapSearchId':True},{'intent':{'id':4}},
                 {'intent':{'topics':['coffee'],'title':{}}},{'confirmed_ids':True},{'confirmed_ids':'one'},
                 {'confirmed_ids':[{}]},{'constraints':True},{'constraints':[True]},
                 {'constraints':[{'id':[]}]} ,{'constraints':[{'id':'x','field':'requiredLanguages','proposed_value':True}]},
                 {'constraints':[{'id':'x','kind':'dating_evergreen','target_prefs':[]}]}]
        with self.server() as (server,_),patch.object(self.app,'prepare_search',side_effect=AssertionError('prepare forbidden')) as prepare:
            for mode in ('off','shadow','enforce'):
                with patch.dict(os.environ,{'KLEAL_MONETIZATION_MODE':mode}):
                    for delta in invalid:
                        body={'intent':{'topics':['coffee']},'commandId':'invalid',**delta}
                        code,result=self.request(server,'/api/agent/confirm',body)
                        self.assertEqual((code,result.get('error')),(400,'invalid_search_input'),(mode,delta,result))
                        with patch.dict(os.environ,{'KLEAL_MONETIZATION_MODE':'enforce'}):
                            status=ms.status('a');self.assertIsInstance(status['searches'],list)
                            self.assertEqual(status['usage']['activeSearches'],0)
                            statuses.append(status)
            prepare.assert_not_called()
        node=shutil.which('node') or '/Users/ivan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
        checker=Path(__file__).resolve().parents[2]/'kleal-app/tools/membership_wire_check.js'
        checked=subprocess.run([node,str(checker)],input=json.dumps(statuses),text=True,capture_output=True,timeout=30)
        self.assertEqual(checked.returncode,0,checked.stderr)
        with ms.transaction() as tx:
            self.assertEqual(tx.conn.execute('select count(*) from monetization_commands').fetchone()[0],0)
            self.assertIsNone(tx.account('a')['start'])
        with self.server() as (server,_):
            code,result=self.request(server,'/api/agent/confirm',{'intent':{'topics':['coffee']},'title':None,
                'confirmed_ids':[],'constraints':[],'commandId':'valid-null'})
            self.assertEqual(code,200,result)

    def test_buddy_multiple_pending_payloads_survive_reload_and_independent_completion(self):
        root=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('review5_buddy',root/'services/buddy/app.py')
        buddy=importlib.util.module_from_spec(spec);spec.loader.exec_module(buddy)
        buddy.SESSIONS={};buddy._save_store=lambda:None
        with self.server() as (matching,_):
            buddy.MATCH_URL='http://127.0.0.1:'+str(matching.server_port)
            server=ThreadingHTTPServer(('127.0.0.1',0),buddy.H);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            sent=[];original=buddy._post
            def wire(base,path,payload,**kwargs):
                if path.endswith('/match'):sent.append(json.dumps(payload).encode())
                return original(base,path,payload,**kwargs)
            try:
                bodies=[{'intent':{'topics':[topic]},'signals':{'area':'Old'},'commandId':key} for topic,key in [('coffee','pending-a'),('tea','pending-b')]]
                with patch.object(buddy,'_post',wire),patch.object(self.app,'render_search',side_effect=RuntimeError('pending')):
                    results=[self.request(server,'/api/buddy/launch',bodies[0])]
                    # A pre-upgrade store has only the single pending record.
                    next(iter(buddy.SESSIONS.values())).pop('launch_retries')
                    results.append(self.request(server,'/api/buddy/launch',bodies[1]))
                self.assertEqual([code for code,_ in results],[503,503]);original_bytes=sent[:]
                buddy.SESSIONS=json.loads(json.dumps(buddy.SESSIONS))
                session=next(iter(buddy.SESSIONS.values()));session['signals']={'area':'New'};session['profile']={'city':'New'}
                self.assertEqual(set(session['launch_retries']),{'pending-a','pending-b'})
                self.assertNotIn('Bearer',json.dumps(session['launch_retries']))
                with patch.object(buddy,'_post',wire),patch.object(self.app,'render_search',return_value={'candidates':[]}):
                    before=copy.deepcopy(session['launch_retries']);count=len(sent)
                    code,result=self.request(server,'/api/buddy/launch',dict(bodies[0],intent={'topics':['tennis']}))
                    self.assertEqual((code,result.get('error')),(409,'idempotency_payload_conflict'))
                    self.assertEqual(len(sent),count);self.assertEqual(session['launch_retries'],before)
                    for index,body in enumerate(bodies):
                        code,result=self.request(server,'/api/buddy/launch',{'commandId':body['commandId']})
                        self.assertEqual(code,200,result);self.assertEqual(result['searchId'],results[index][1]['searchId'])
                        self.assertEqual(sent[-1],original_bytes[index])
                        if index==0:self.assertIn('pending-b',session['launch_retries'])
                self.assertEqual(session['launch_retries'],{})
                with ms.transaction() as tx:self.assertEqual(tx.conn.execute('select count(*) from monetization_resources').fetchone()[0],2)
            finally:server.shutdown();server.server_close();thread.join(2)


@unittest.skipUnless(DSN,'BLOCKED: isolated PostgreSQL DSN not configured')
class ImportBeforeMutation(unittest.TestCase):
    setUpClass=classmethod(pg.PostgreSQLCommands.setUpClass.__func__)
    setUp=production.Production.setUp
    tearDown=production.Production.tearDown

    def test_duplicate_live_alias_import_rejects_before_schema_or_data_mutation(self):
        with ms.connection() as conn:
            for box,owner,gid in (('_groups','host','first'),('_gintents','owner','second')):
                members=['a','b'] if box=='_groups' else [{'name':'a','state':'joined'},{'name':'b','state':'joined'}]
                conn.execute('insert into store_kv(key,value) values(%s,%s)',(box,json.dumps([
                    {'id':gid,owner:'a','state':'searching','intent':{'id':'i'},'members':members}])) )
            before=production.prod.snapshot(conn);report=production.prod.plan(before)
            self.assertFalse(report['ok'])
            with self.assertRaisesRegex(ValueError,'multiple live groups'):
                production.prod.import_snapshot(conn,report['snapshotHash'])
            self.assertIsNone(conn.execute("select to_regclass('monetization_meta')").fetchone()[0])
            self.assertEqual(production.prod.snapshot(conn),before)


class ReleaseAndImport(unittest.TestCase):
    def test_import_rejects_multiple_live_aliases_and_preserves_terminal_history(self):
        for boxes in (('_gintents','_gintents'),('_groups','_gintents')):
            data=production.Plan().data()
            for index,box in enumerate(boxes):
                row={'id':'g'+str(index),'state':'searching','intent':{'id':'i'},'members':[]}
                row['host' if box=='_groups' else 'owner']='a'
                data['session'].setdefault(box,[]).append(row)
            self.assertFalse(production.prod.plan(data)['ok'])
            data['session'][boxes[-1]][-1]['state']='done'
            report=production.prod.plan(data);self.assertTrue(report['ok'],report['issues'])
            self.assertEqual(report['aliases']['group:g0'],report['aliases']['group:g1'])

    def test_backup_fsync_precedes_first_replace_and_failure_leaves_source_unchanged(self):
        release=production.release
        for fail in (False,True):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp).resolve()/'live';root.mkdir();candidate=Path(temp).resolve()/'candidate';candidate.mkdir()
                (root/'a.py').write_text('old');(candidate/'a.py').write_text('new')
                manifest=release.make_manifest(root,candidate,['a.py']);backup=Path(temp).resolve()/'backup';events=[]
                original_sync=release.sync_directory;original_replace=release.os.replace;original_fsync=release.os.fsync
                def fsync(fd):events.append(('fsync',os.fstat(fd).st_ino));return original_fsync(fd)
                def sync(path):
                    events.append(('dir',Path(path)))
                    if fail and Path(path)==backup:raise OSError('synthetic sync failure')
                    return original_sync(path)
                def replace(src,dst):
                    self.assertIn(('fsync',(backup/'a.py').stat().st_ino),events)
                    self.assertIn(('fsync',(backup/'release-manifest.json').stat().st_ino),events)
                    self.assertIn(('dir',backup),events);self.assertIn(('dir',backup.parent),events)
                    events.append(('replace',Path(dst)));return original_replace(src,dst)
                with patch.object(release,'require_stopped',return_value={}),patch.object(release,'sync_directory',sync), \
                     patch.object(release.os,'fsync',fsync),patch.object(release.os,'replace',replace):
                    if fail:
                        with self.assertRaises(OSError):release.install(root,candidate,manifest,backup)
                        self.assertEqual((root/'a.py').read_text(),'old');self.assertFalse(any(e[0]=='replace' for e in events))
                    else:
                        release.install(root,candidate,manifest,backup)
                        index=events.index(('replace',root/'a.py'));self.assertIn(('dir',root),events[index+1:])
                        release.restore_files(root,backup,manifest);self.assertEqual((root/'a.py').read_text(),'old')
                        self.assertEqual(events[-2][0],'dir')


if __name__=='__main__':unittest.main()
