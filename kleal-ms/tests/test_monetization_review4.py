"""Четвёртый review: wire callers, canonical locks/aliases и точный backup."""
import concurrent.futures
import copy
import importlib.util
import json
import os
from pathlib import Path
from http.server import ThreadingHTTPServer
import threading
import time
import unittest
import uuid
from unittest.mock import patch

import test_monetization_phase2 as phase
import test_monetization_pg as pg
import test_monetization_review2 as review2
import test_monetization_production as production
from test_monetization_pg import DSN, ms


@unittest.skipUnless(DSN,'BLOCKED: isolated PostgreSQL DSN not configured')
class ReviewFour(unittest.TestCase):
    setUpClass=classmethod(pg.PostgreSQLCommands.setUpClass.__func__)
    setUp=phase.LegacyAdapters.setUp
    tearDown=phase.LegacyAdapters.tearDown
    tearDownDB=pg.PostgreSQLCommands.tearDown
    save=phase.LegacyAdapters.save
    free=pg.PostgreSQLCommands.free
    command=review2.ReviewTwo.command
    server=review2.ReviewTwo.server
    request=review2.ReviewTwo.request

    def test_ready_plan_replay_and_conflict_never_prepare_again(self):
        body={'query':'coffee','commandId':'plan-ready'}
        with self.server() as (server,_), patch.object(self.app,'parse_intent',return_value={'topics':['coffee']}):
            code,ready=self.request(server,'/api/agent/plan',body)
            self.assertEqual(code,200,ready);self.assertEqual(ready['launchState'],'ready')
            with patch.object(self.app,'prepare_search',side_effect=AssertionError('parser must not run')) as prepare, \
                 patch.object(self.app,'_prepare_map_intent',side_effect=AssertionError('geocoder must not run')) as geo:
                self.assertEqual(self.request(server,'/api/agent/plan',body),(code,ready))
                code,conflict=self.request(server,'/api/agent/plan',dict(body,query='different'))
                self.assertEqual((code,conflict['error']),(409,'idempotency_payload_conflict'))
                prepare.assert_not_called();geo.assert_not_called()
        with ms.transaction() as tx:self.assertEqual(tx.conn.execute('select count(*) from monetization_resources').fetchone()[0],1)

    def test_concurrent_first_preparation_remains_exactly_once(self):
        barrier=threading.Barrier(2)
        def prepare(*args):barrier.wait(timeout=3);return {'topics':['coffee']}
        with self.server() as (server,_),patch.object(self.app,'prepare_search',prepare),concurrent.futures.ThreadPoolExecutor(2) as workers:
            body={'commandId':'concurrent','intent':{'topics':['coffee']}}
            futures=[workers.submit(self.request,server,'/api/agent/search-command',body) for _ in range(2)]
            results=[future.result(timeout=5) for future in futures]
        self.assertEqual(results[0],results[1]);self.assertEqual(results[0][0],200)
        with ms.transaction() as tx:
            self.assertEqual(tx.conn.execute('select count(*) from monetization_resources').fetchone()[0],1)
            self.assertEqual(tx.conn.execute('select count(*) from monetization_commands').fetchone()[0],1)

    def test_malformed_containers_safe_400_before_preparation_in_every_mode(self):
        with self.server() as (server,_),patch.object(self.app,'prepare_search',side_effect=AssertionError('no preparation')) as prepare:
            for mode in ('off','shadow','enforce'):
                with patch.dict(os.environ,{'KLEAL_MONETIZATION_MODE':mode}):
                    for route in ('plan','match','search-command'):
                        for field in ('intent','ctx','override','profile'):
                            for value in ([],['private'],True,3,'private'):
                                body={'query':'coffee','intent':{'topics':['coffee']},field:value,'commandId':'malformed'}
                                code,result=self.request(server,'/api/agent/'+route,body)
                                self.assertEqual((code,result['error']),(400,'invalid_search_input'),(mode,route,field,value,result))
                                self.assertNotIn('private',json.dumps(result))
            prepare.assert_not_called()
        with ms.transaction() as tx:
            for table in ('monetization_resources','monetization_commands'):
                self.assertEqual(tx.conn.execute('select count(*) from '+table).fetchone()[0],0)
            self.assertFalse(tx.conn.execute('select 1 from monetization_accounts where preview_start is not null').fetchone())

    def test_off_shadow_pause_resume_are_not_publications(self):
        with self.server() as (server,_),patch.object(self.app,'prepare_search',side_effect=AssertionError('no preparation')) as prepare:
            for mode in ('off','shadow'):
                with patch.dict(os.environ,{'KLEAL_MONETIZATION_MODE':mode}):
                    before=copy.deepcopy(self.app.SESSION)
                    for operation in ('pause','resume'):
                        code,result=self.request(server,'/api/agent/search-command',{'operation':operation,'searchId':'old','commandId':mode+operation})
                        self.assertEqual((code,result['error']),(409,'phase2_not_enabled'))
                    self.assertEqual(dict(self.app.SESSION),before)
            prepare.assert_not_called()

    def test_one_live_group_per_search_free_plus_and_historical_alias(self):
        for owner in ('a','c'):
            if owner=='a':self.free(owner)
            saved=self.save(owner,key='intent-'+owner)
            intent={'id':saved['id'],'topics':['coffee']}
            first=self.app.gi_create(owner,intent,'First',idem='first-'+owner)
            self.assertTrue(first['ok'],first);gid=first['group']['gid']
            with ms.transaction() as tx:before=copy.deepcopy(tx.documents());rid=tx.resolve('group',gid);account=tx.account(owner)
            self.assertEqual(self.app.gi_create(owner,intent,'First',idem='first-'+owner),first)
            second=self.app.gi_create(owner,intent,'Second',idem='second-'+owner)
            self.assertEqual(second['error'],'search_group_conflict')
            with ms.transaction() as tx:
                self.assertEqual(tx.documents(),before);self.assertEqual(tx.account(owner),account)
                self.assertEqual(tx.conn.execute('select count(*) from monetization_resources where owner_id=%s',(owner,)).fetchone()[0],1)
            self.assertTrue(self.app.gi_close(gid,owner,idem='close-'+owner)['ok'])
            self.command(owner,operation='resume',searchId=rid,commandId='resume-'+owner)
            replacement=self.app.gi_create(owner,intent,'Replacement',idem='replacement-'+owner)
            self.assertTrue(replacement['ok'],replacement)
            new_gid=replacement['group']['gid']
            # A late historical lifecycle/owner update cannot pause or transfer the
            # resource now controlled by the replacement live group.
            with ms.transaction() as tx:
                before=tx.documents();after=copy.deepcopy(before)
                old=next(g for g in after['_gintents'] if g['id']==gid)
                old.update(state='expired',owner='b')
                self.app.monetization_commands._reconcile(tx,before,after,'gi_close',{})
                self.assertEqual(tx.resource(rid)['owner_id'],owner);self.assertEqual(tx.resource(rid)['state'],'active')
                self.assertEqual(tx.resolve('group',new_gid),rid)

    def test_legacy_live_alias_cannot_be_reused_or_paused_by_history(self):
        created=self.app.group_create('a','Legacy',['coffee'],idem='legacy');self.assertTrue(created['ok'])
        gid=created['group']['gid']
        with ms.transaction() as tx:
            rid=tx.resolve('group',gid)
        denied=self.app.gi_create('a',{'_searchId':rid,'topics':['coffee']},'Other model',idem='other')
        self.assertEqual(denied['error'],'search_group_conflict')
        with ms.transaction() as tx:
            before=tx.documents();after=copy.deepcopy(before)
            after['_groups'].append(dict(after['_groups'][0],id='legacy-second'))
            after['_groups'][-1]['intent']={'_searchId':rid}
            with self.assertRaises(ms.CommandError) as caught:
                self.app.monetization_commands._reconcile(tx,before,after,'group_create',{})
            self.assertEqual(caught.exception.code,'search_group_conflict')
        self.assertEqual(ms.status('a')['usage']['activeSearches'],1)

    def test_buddy_pending_uses_original_full_payload_after_profile_drift(self):
        root=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('review4_buddy',root/'services/buddy/app.py')
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
                body={'intent':{'topics':['coffee']},'signals':{'area':'Old city','languages':['en']},'override':{'radiusKm':20}}
                with patch.object(buddy,'_post',wire),patch.object(self.app,'render_search',side_effect=RuntimeError('pending')):
                    code,pending=self.request(server,'/api/buddy/launch',body)
                self.assertEqual((code,pending['error']),(503,'launch_pending'))
                self.assertEqual(len(buddy.SESSIONS),1);session=next(iter(buddy.SESSIONS.values()))
                stored=copy.deepcopy(session['launch_retry']);session['signals']={'area':'New city','languages':['es']}
                session['profile']={'city':'New city','languages':['es']}
                self.assertEqual(stored['payload']['profile']['city'],'Old city');self.assertEqual(stored['signals']['area'],'Old city')
                with patch.object(buddy,'_post',wire),patch.object(self.app,'render_search',side_effect=RuntimeError('still pending')):
                    code,repeated=self.request(server,'/api/buddy/launch',copy.deepcopy(body))
                    self.assertEqual((code,repeated['error']),(503,'launch_pending'))
                    self.assertEqual((repeated['commandId'],repeated['searchId']),(pending['commandId'],pending['searchId']))
                    self.assertEqual(sent[0],sent[1],'полный исходный body после drift должен повторить исходные bytes')
                with ms.transaction() as tx:self.assertEqual(tx.conn.execute('select count(*) from monetization_resources').fetchone()[0],1)
                with patch.object(buddy,'_post',wire),patch.object(self.app,'render_search',return_value={'candidates':[]}):
                    code,ready=self.request(server,'/api/buddy/launch',copy.deepcopy(body))
                    self.assertEqual(code,200,ready);self.assertEqual(ready['searchId'],pending['searchId'])
                    self.assertEqual(sent[0],sent[2],'exact matching wire payload must survive mutable profile/signals')
                    code,new=self.request(server,'/api/buddy/launch',body)
                    self.assertEqual(code,200,new);self.assertNotEqual(new['commandId'],ready['commandId'])
                    self.assertNotEqual(new['searchId'],ready['searchId'])
                    conflict_body={'intent':{'topics':['tennis']},'commandId':ready['commandId']}
                    code,conflict=self.request(server,'/api/buddy/launch',conflict_body)
                    self.assertEqual((code,conflict['error']),(409,'idempotency_payload_conflict'))
                with ms.transaction() as tx:self.assertEqual(tx.conn.execute('select count(*) from monetization_resources').fetchone()[0],2)
                # Незавершённый запуск не поглощает новый payload или новый явный key.
                with patch.object(buddy,'_post',wire),patch.object(self.app,'render_search',side_effect=RuntimeError('pending')):
                    code,pending_again=self.request(server,'/api/buddy/launch',body)
                    self.assertEqual(code,503,pending_again)
                    changed=copy.deepcopy(body);changed['override']['radiusKm']=30
                    code,changed_pending=self.request(server,'/api/buddy/launch',changed)
                    self.assertEqual(code,503,changed_pending)
                    self.assertNotEqual(changed_pending['commandId'],pending_again['commandId'])
                    self.assertNotEqual(changed_pending['searchId'],pending_again['searchId'])
                    code,explicit=self.request(server,'/api/buddy/launch',dict(changed,commandId='explicit-new'))
                    self.assertEqual(code,503,explicit);self.assertEqual(explicit['commandId'],'explicit-new')
                    self.assertNotEqual(explicit['searchId'],changed_pending['searchId'])
                with ms.transaction() as tx:self.assertEqual(tx.conn.execute('select count(*) from monetization_resources').fetchone()[0],5)
            finally:server.shutdown();server.server_close();thread.join(2)

    def test_projection_lock_deadline_rolls_back_releases_pool_and_same_key_retries(self):
        with self.psycopg.connect(DSN,options='-c search_path='+self.schema) as holder:
            holder.execute("select pg_advisory_xact_lock(hashtextextended('monetization:projection',0))")
            started=threading.Event()
            def run():
                started.set()
                try:return ms.execute('a','bounded','same',{},lambda tx:{'ok':True,'id':tx.publish('a',{'title':'bounded'})})
                except ms.CommandError as error:return error.response()
            with concurrent.futures.ThreadPoolExecutor(1) as worker:
                start=time.monotonic();future=worker.submit(run);self.assertTrue(started.wait(1))
                result=future.result(timeout=4)
                self.assertLess(time.monotonic()-start,4);self.assertEqual(result['httpStatus'],503);self.assertTrue(result['retryable'])
                self.assertEqual(result['error'],'monetization_unavailable')
            with ms.connection() as c:
                for table in ('monetization_resources','monetization_commands'):
                    self.assertEqual(c.execute('select count(*) from '+table).fetchone()[0],0)
                self.assertFalse(c.execute('select 1 from monetization_accounts where preview_start is not null').fetchone())
                self.assertEqual(c.execute('show lock_timeout').fetchone()[0],'0','SET LOCAL does not leak to pool defaults')
        result=run();self.assertTrue(result['ok']);self.assertEqual(run(),result)

    def test_statement_row_and_operator_deadlines_are_safe_and_recoverable(self):
        import monetization_admin as admin
        with ms.transaction() as tx:tx.account('a');tx.conn.execute("insert into users(id,name_key,name,row) values('a','a','A','{}')")
        with patch.object(ms,'LOCK_TIMEOUT_MS',150),patch.object(ms,'STATEMENT_TIMEOUT_MS',300):
            with self.assertRaises(ms.CommandError) as caught:
                with ms.transaction() as tx:
                    tx.conn.execute('select pg_sleep(1)')
            self.assertEqual(caught.exception.response()['error'],'monetization_unavailable')
            with self.psycopg.connect(DSN,options='-c search_path='+self.schema) as holder:
                holder.execute("select 1 from users where id='a' for update")
                with ms.connection() as c:
                    with self.assertRaises(ms.CommandError) as caught:
                        admin.command(c,action='grant',owner='a',operator='QA',reason='deadline',key='bounded-grant',expires=int(time.time())+3600,apply=True)
                    self.assertEqual(caught.exception.status,503)
                    self.assertEqual(c.execute('select count(*) from monetization_manual_grants').fetchone()[0],0)
            with ms.connection() as c:
                result=admin.command(c,action='grant',owner='a',operator='QA',reason='deadline',key='bounded-grant',expires=int(time.time())+3600,apply=True)
                self.assertTrue(result['ok'])

    def test_production_backup_exact_sequence_state_version_checksum_and_next_insert(self):
        release=production.release
        with ms.transaction() as tx:
            tx.audit('a','sample',{})
            tx.conn.execute("select setval(pg_get_serial_sequence('monetization_audit','id'),97,true)")
            tx.conn.execute("select setval(pg_get_serial_sequence('monetization_admin_audit','id'),43,false)")
            tx.conn.execute("select setval(pg_get_serial_sequence('outbox','id'),29,true)")
            snapshot=release.backup(tx.conn)
        self.assertEqual(snapshot['version'],2)
        self.assertEqual(snapshot['sequences'],{'monetization_audit':[97,True],'monetization_admin_audit':[43,False],'outbox':[29,True]})
        target='test_restore_'+uuid.uuid4().hex
        try:
            with self.psycopg.connect(DSN,autocommit=True) as c:c.execute('create schema '+target)
            for change in ('v1','tampered','shape'):
                bad=copy.deepcopy(snapshot)
                if change=='v1':bad['version']=1;bad['checksum']=ms.digest({k:v for k,v in bad.items() if k!='checksum'})
                elif change=='tampered':bad['sequences']['outbox'][0]+=1
                else:bad['sequences']['outbox']=[True,False];bad['checksum']=ms.digest({k:v for k,v in bad.items() if k!='checksum'})
                with self.psycopg.connect(DSN,options='-c search_path='+target) as c:
                    with self.assertRaises(ValueError):release.restore_rehearsal(c,bad)
                    self.assertFalse(c.execute('select 1 from information_schema.tables where table_schema=current_schema()').fetchone())
            with self.psycopg.connect(DSN,options='-c search_path='+target) as c:
                release.restore_rehearsal(c,snapshot);self.assertEqual(release.backup(c)['checksum'],snapshot['checksum'])
                for table,expected in (('monetization_audit',98),('monetization_admin_audit',43),('outbox',30)):
                    if table=='outbox':sql="insert into outbox(topic,payload) values('synthetic','{}') returning id"
                    else:sql="insert into "+table+"(owner_id,event,details,created) values('a','synthetic','{}',1) returning id"
                    self.assertEqual(c.execute(sql).fetchone()[0],expected)
        finally:
            with self.psycopg.connect(DSN,autocommit=True) as c:c.execute('drop schema '+target+' cascade')


if __name__=='__main__':unittest.main()
