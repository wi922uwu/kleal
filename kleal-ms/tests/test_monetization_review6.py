"""Review six: real isolated PG/HTTP and local release guard boundaries."""
import copy
import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch

import test_monetization_pg as pg
import test_monetization_phase2 as phase
import test_monetization_review2 as review2
import test_monetization_production as production
from test_monetization_pg import DSN, ms


@unittest.skipUnless(DSN,'BLOCKED: isolated PostgreSQL DSN not configured')
class ReviewSix(unittest.TestCase):
    setUpClass=classmethod(pg.PostgreSQLCommands.setUpClass.__func__)
    setUp=phase.LegacyAdapters.setUp
    tearDown=phase.LegacyAdapters.tearDown
    tearDownDB=pg.PostgreSQLCommands.tearDown
    save=phase.LegacyAdapters.save
    command=review2.ReviewTwo.command
    server=review2.ReviewTwo.server
    request=review2.ReviewTwo.request

    def test_successful_buddy_receipt_replays_original_payload_after_reload(self):
        root=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('review6_buddy',root/'services/buddy/app.py')
        buddy=importlib.util.module_from_spec(spec);spec.loader.exec_module(buddy)
        buddy.SESSIONS={};saved=[];buddy._save_store=lambda:saved.append(json.dumps(buddy.SESSIONS))
        with self.server() as (matching,_):
            buddy.MATCH_URL='http://127.0.0.1:'+str(matching.server_port)
            server=ThreadingHTTPServer(('127.0.0.1',0),buddy.H)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            sent=[];original=buddy._post
            def wire(base,path,payload,**kwargs):
                if path.endswith('/match'):sent.append(json.dumps(payload).encode())
                return original(base,path,payload,**kwargs)
            body={'intent':{'topics':['coffee']},'signals':{'area':'Old'},'commandId':'success-a'}
            try:
                with patch.object(buddy,'_post',wire),patch.object(self.app,'render_search',return_value={'candidates':[]}):
                    code,first=self.request(server,'/api/buddy/launch',body)
                    self.assertEqual(code,200,first)
                    # This response can be lost downstream; no client ack exists.
                    original_bytes=sent[-1]
                    buddy.SESSIONS=json.loads(saved[-1])
                    session=next(iter(buddy.SESSIONS.values()));session['signals']={'area':'Changed'}
                    session['profile']={'city':'Changed'}
                    self.assertFalse(session['launch_retries'])
                    self.assertNotIn('Bearer',json.dumps(session))
                    with patch.object(self.app,'prepare_search',side_effect=AssertionError('no prepare on replay')):
                        code,replay=self.request(server,'/api/buddy/launch',body)
                    self.assertEqual(code,200,replay);self.assertEqual(replay['searchId'],first['searchId'])
                    self.assertEqual(sent[-1],original_bytes)
                    count=len(sent)
                    code,conflict=self.request(server,'/api/buddy/launch',dict(body,intent={'topics':['tea']}))
                    self.assertEqual((code,conflict['error']),(409,'idempotency_payload_conflict'))
                    self.assertEqual(len(sent),count)
                    code,new=self.request(server,'/api/buddy/launch',dict(body,commandId='success-b'))
                    self.assertEqual(code,200,new);self.assertNotEqual(new['searchId'],first['searchId'])
                    # Old clients without keys intentionally start again after ready.
                    _,legacy1=self.request(server,'/api/buddy/launch',{'intent':{'topics':['coffee']}})
                    _,legacy2=self.request(server,'/api/buddy/launch',{'intent':{'topics':['coffee']}})
                    self.assertNotEqual(legacy1['searchId'],legacy2['searchId'])
                with ms.transaction() as tx:self.assertEqual(tx.conn.execute('select count(*) from monetization_resources').fetchone()[0],4)
            finally:server.shutdown();server.server_close();thread.join(2)

    def test_begin_delete_hides_actual_offline_online_projection_before_cleanup(self):
        cmd=self.app.monetization_commands
        intent={'topics':['coffee'],'mode':'hybrid','lat':40.41,'lng':-3.70,'address':'Synthetic venue',
                'title':'Hybrid future','starts_at':time.time()+7*86400}
        saved=self.app.save_intent('Same name',intent,'Hybrid future',launched=True,owner_id='a',idem='hybrid')
        with ms.transaction() as tx:
            rid=tx.resolve('intent',saved['id']);doc=tx.documents()
            doc['_messages']=[{'id':'history','from':'a','to':'b','text':'keep history'}];tx.save_documents(doc)
        cmd.refresh()
        for view in ('offline','online'):self.assertEqual(len(self.app.map_feed_payload(view,self_id='b')['items']),1)
        with ms.connection() as conn:production.admin.begin_delete(conn,'a')
        snapshot=cmd.read_snapshot()
        self.assertEqual(snapshot['_intents'][0]['searchState'],'deleting')
        with cmd.projection(snapshot):
            for view in ('offline','online'):self.assertEqual(self.app.map_feed_payload(view,self_id='b')['items'],[])
            self.assertEqual(self.app.explore_plans(self_id='b'),[])
        cmd.refresh()
        for view in ('offline','online'):self.assertEqual(self.app.map_feed_payload(view,self_id='b')['items'],[])
        with self.assertRaises(ms.CommandError) as error:self.command(operation='resume',searchId=rid,commandId='cannot-resume')
        self.assertEqual(error.exception.code,'account_deleting')
        with ms.transaction() as tx:
            projected=cmd._project(tx,tx.documents())
            self.assertEqual(projected['_intents'][0]['searchState'],'deleting')
            self.assertEqual(projected['_messages'][0]['text'],'keep history')
            self.assertEqual(tx.resource(rid)['state'],'active','barrier hides without destroying history')

    def test_map_proposal_wire_replay_keeps_version_ttl_after_acceptance(self):
        saved=self.save()
        body={'to_id':'a','intent':{'targetIntentId':saved['id']},'idem':'reply-original'}
        with self.server() as (server,_):
            code,first=self.request(server,'/api/agent/propose',body,'b')
            self.assertEqual(code,200,first);self.assertTrue(first['ok'])
            with ms.transaction() as tx:before=copy.deepcopy(tx.documents()['_requests'])
            self.assertEqual(self.request(server,'/api/agent/propose',body,'b'),(code,first))
            with ms.transaction() as tx:self.assertEqual(tx.documents()['_requests'],before)
            accepted=self.app.respond(first['id'],'accept','a','accept-reply')
            self.assertTrue(accepted['ok'],accepted)
            with ms.transaction() as tx:after=copy.deepcopy(tx.documents()['_requests'])
            self.assertEqual(self.request(server,'/api/agent/propose',body,'b'),(code,first))
            with ms.transaction() as tx:self.assertEqual(tx.documents()['_requests'],after)

    def test_deleting_candidate_is_hidden_from_receipt_before_cleanup(self):
        body={'intent':{'topics':['coffee']},'commandId':'viewer-receipt'}
        with patch.object(self.app,'render_search',return_value={'candidates':[{'id':'a'},{'id':'c'}],
                                                               'group':{'members':[{'id':'a'}]}}):
            first=self.command(owner='b',**body)
        self.assertEqual([row['id'] for row in first['candidates']],['a','c'])
        with ms.connection() as conn:production.admin.begin_delete(conn,'a')
        with patch.object(self.app,'render_search',side_effect=AssertionError('no new ranking on replay')):
            replay=self.command(owner='b',**body)
        self.assertEqual(replay['candidates'],[{'id':'c'}]);self.assertNotIn('group',replay)

    def test_obsolete_owner_launch_finishes_receipt_and_real_drain(self):
        cmd=self.app.monetization_commands
        group=self.app.gi_create('a',{'topics':['coffee']},'Coffee',idem='group')['group']['gid']
        invite=self.app.gi_invite(group,'a','b',idem='invite')
        self.assertTrue(self.app.gi_respond(invite['invite']['id'],'b',True,'join')['ok'])
        with patch.object(self.app,'render_search',side_effect=RuntimeError('interrupted')):
            pending=self.command(operation='rank_group',groupId=group,commandId='old-owner')
        self.assertEqual(pending['launchState'],'pending')
        self.assertTrue(self.app.gi_role_offer(group,'a','b','offer')['ok'])
        self.assertTrue(self.app.gi_role_respond(group,'b',True,'take-role')['ok'])
        with ms.transaction() as tx:resource=copy.deepcopy(tx.resource(pending['searchId']))
        with patch.object(self.app,'render_search',side_effect=AssertionError('obsolete must not rank')):cmd.drain_launches(10)
        with ms.transaction() as tx:
            self.assertEqual(tx.resource(pending['searchId']),resource)
            result=tx.conn.execute("select result from monetization_commands where command_key='old-owner'").fetchone()[0]
            self.assertEqual((result['launchState'],result['candidates']),('superseded',[]))
            jobs=tx.conn.execute("select sent_at,last_error from outbox where payload->>'commandKey'='old-owner'").fetchall()
            self.assertTrue(jobs);self.assertTrue(all(sent and not error for sent,error in jobs))
        with patch.object(self.app,'render_search',side_effect=AssertionError('replay must not rank')):
            self.assertEqual(self.command(operation='rank_group',groupId=group,commandId='old-owner')['launchState'],'superseded')

    def test_terminal_pending_jobs_and_retryable_failure_are_distinct(self):
        cmd=self.app.monetization_commands
        for key,state in [('paused','paused'),('deleted','deleted'),('superseded','superseded'),('deleting','deleting')]:
            with self.subTest(state=state):
                owner='b' if state=='deleting' else 'a'
                with patch.object(self.app,'render_search',side_effect=RuntimeError('retryable')):
                    pending=self.command(owner=owner,intent={'topics':['coffee']},commandId=key)
                with ms.transaction() as tx:
                    if state=='deleting':tx.conn.execute('insert into monetization_deletions values(%s,%s)',(owner,tx.now))
                    elif state=='superseded':tx.conn.execute("update monetization_resources set generation='replacement' where id=%s",(pending['searchId'],))
                    else:tx.conn.execute('update monetization_resources set state=%s where id=%s',(state,pending['searchId']))
                with patch.object(self.app,'render_search',side_effect=AssertionError('terminal must not rank')):cmd.drain_launches(10)
                with ms.transaction() as tx:
                    result=tx.conn.execute('select result from monetization_commands where command_key=%s',(key,)).fetchone()[0]
                    self.assertEqual(result['launchState'],'deleted' if state=='deleting' else state)
                    self.assertEqual(result['candidates'],[])
        with patch.object(self.app,'render_search',side_effect=RuntimeError('temporary')):
            self.command(intent={'topics':['tea']},commandId='retryable');cmd.drain_launches(10)
        with ms.transaction() as tx:
            job=tx.conn.execute("select sent_at,last_error from outbox where payload->>'commandKey'='retryable'").fetchone()
            self.assertEqual(job,(None,'launch_retry_required'))
            tx.conn.execute("update outbox set next_try=now() where payload->>'commandKey'='retryable'")
        with patch.object(self.app,'render_search',return_value={'candidates':[]}):self.assertEqual(cmd.drain_launches(10),1)

    def test_transfer_during_ranking_retires_old_receipt_without_touching_new_owner(self):
        group=self.app.gi_create('a',{'topics':['coffee']},'Coffee',idem='group')['group']['gid']
        invite=self.app.gi_invite(group,'a','b',idem='invite')
        self.assertTrue(self.app.gi_respond(invite['invite']['id'],'b',True,'join')['ok'])
        entered=threading.Event();release=threading.Event()
        def ranking(*args):
            entered.set();self.assertTrue(release.wait(5));return {'candidates':[{'id':'c'}]}
        with patch.object(self.app,'render_search',ranking),concurrent.futures.ThreadPoolExecutor(1) as workers:
            future=workers.submit(self.command,operation='rank_group',groupId=group,commandId='in-flight')
            self.assertTrue(entered.wait(3))
            try:
                self.assertTrue(self.app.gi_role_offer(group,'a','b','offer')['ok'])
                self.assertTrue(self.app.gi_role_respond(group,'b',True,'take-role')['ok'])
                with ms.transaction() as tx:
                    rid=tx.resolve('group',group);resource=copy.deepcopy(tx.resource(rid))
            finally:release.set()
            result=future.result(5)
        self.assertEqual((result['launchState'],result['candidates']),('superseded',[]))
        with ms.transaction() as tx:
            self.assertEqual(tx.resource(rid),resource)
            receipt=tx.conn.execute("select result from monetization_commands where command_key='in-flight'").fetchone()[0]
            self.assertEqual(receipt['launchState'],'superseded')
            self.assertIsNotNone(tx.conn.execute("select sent_at from outbox where payload->>'commandKey'='in-flight'").fetchone()[0])

    def test_purge_selects_only_exact_id_receipts_from_large_existing_ledger(self):
        import psycopg
        for key,result in [('person',{'candidates':[{'id':'b','photo':'private'}]}),
                           ('nested',{'group':{'members':[{'name':'b','photo':'private'}]}}),
                           ('text',{'text':'b','candidates':[{'id':'db','name':'b'}]})]:
            ms.execute('a','cached',key,{},lambda tx,r=result:dict(ok=True,**r))
        with ms.connection() as conn:
            conn.execute("insert into monetization_commands select 'd','cached','unrelated-'||i,'hash','{\"ok\":true,\"to_id\":\"other\"}'::jsonb,1 from generate_series(1,20000) i")
            conn.execute('analyze monetization_commands')
            conn.execute('set local enable_seqscan=off')
            explain=conn.execute("explain select result from monetization_commands where result @? %s::jsonpath",('$.** ? (@ == "b")',)).fetchall()
            self.assertIn('monetization_command_result_values',' '.join(row[0] for row in explain))
        original=psycopg.Connection.execute;selected=[]
        def measured(conn,query,*args,**kwargs):
            cursor=original(conn,query,*args,**kwargs)
            if str(query).startswith('select owner_id,action,command_key,result from monetization_commands'):
                rows=cursor.fetchall();selected.append(len(rows));return iter(rows)
            return cursor
        with patch.object(psycopg.Connection,'execute',measured):
            self.assertTrue(self.app.purge_person('b')['ok'])
            self.assertTrue(self.app.purge_person('b')['ok'])
        self.assertLessEqual(max(selected),3,selected)
        for key in ('person','nested'):
            replay=ms.execute('a','cached',key,{},lambda tx:self.fail('idempotency fence removed'))
            self.assertTrue(replay['redacted']);self.assertNotIn('private',json.dumps(replay))
        with ms.connection() as conn:
            self.assertEqual(conn.execute("select count(*) from monetization_commands where owner_id='d'").fetchone()[0],20000)
            self.assertEqual(conn.execute("select result->>'text' from monetization_commands where command_key='text'").fetchone()[0],'b')

    def test_nullable_and_absent_titles_pass_production_mobile_wire_validator(self):
        statuses=[]
        with self.server() as (server,_):
            for index,intent in enumerate(({'topics':['coffee'],'title':None},{'topics':['tea']})):
                code,result=self.request(server,'/api/agent/search-command',{'intent':intent,'commandId':'title-'+str(index)})
                self.assertEqual(code,200,result)
                status=ms.status('a');self.assertTrue(all(isinstance(row['title'],str) for row in status['searches']))
                statuses.append(status)
        node=shutil.which('node') or '/Users/ivan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
        self.assertTrue(Path(node).is_file(),'Node is required for the real mobile contract check; never silently skip')
        checker=Path(__file__).resolve().parents[2]/'kleal-app/tools/membership_wire_check.js'
        checked=subprocess.run([node,str(checker)],input=json.dumps(statuses),text=True,capture_output=True,timeout=30)
        self.assertEqual(checked.returncode,0,checked.stderr)


class ReleaseWriterGuards(unittest.TestCase):
    def test_actual_install_restore_guards_stop_before_source_writes(self):
        release=production.release
        units={role:'synthetic-'+role+'.service' for role in release.WRITER_ROLES}
        state={'active':'inactive','load':'loaded','code':0};calls=[]
        def systemctl(args,**kwargs):
            calls.append(args)
            self.assertEqual(args[0:2],['systemctl','show'])
            self.assertIn(args[2],units.values())
            return SimpleNamespace(returncode=state['code'],stdout='LoadState='+state['load']+'\nActiveState='+state['active']+'\n')
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'KLEAL_RELEASE_SERVICES':json.dumps(units)}),patch.object(release.subprocess,'run',systemctl):
            root=Path(temp).resolve()/'live';root.mkdir();candidate=Path(temp).resolve()/'candidate';candidate.mkdir()
            (root/'one.py').write_text('old');(candidate/'one.py').write_text('new')
            manifest=release.make_manifest(root,candidate,['one.py']);backup=Path(temp).resolve()/'backup'
            denied=[('active','loaded',0),('activating','loaded',0),('unknown','not-found',0),('inactive','loaded',1)]
            for active,load,code in denied:
                state.update(active=active,load=load,code=code)
                with self.assertRaises(ValueError):release.install(root,candidate,manifest,backup)
                self.assertEqual((root/'one.py').read_text(),'old');self.assertFalse(backup.exists())
                self.assertEqual(list(root.iterdir()),[root/'one.py'])
            state.update(active='inactive',load='loaded',code=0)
            self.assertTrue(release.install(root,candidate,manifest,backup)['ok'])
            self.assertEqual((root/'one.py').read_text(),'new')
            for active,load,code in denied:
                state.update(active=active,load=load,code=code)
                with self.assertRaises(ValueError):release.restore_files(root,backup,manifest)
                self.assertEqual((root/'one.py').read_text(),'new');self.assertEqual(list(root.iterdir()),[root/'one.py'])
            state.update(active='inactive',load='loaded',code=0)
            self.assertTrue(release.restore_files(root,backup,manifest)['ok'])
            self.assertEqual((root/'one.py').read_text(),'old');self.assertTrue(calls)


if __name__=='__main__':unittest.main()
