"""Review-two contract regressions on isolated PostgreSQL and real HTTP/adapters."""
import contextlib
import copy
import hashlib
import http.client
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import unittest
import uuid
from unittest.mock import patch

import test_monetization_phase2 as phase
import test_monetization_pg as pg
import test_monetization_production as production
from test_monetization_pg import DSN, ms, rehearsal


@unittest.skipUnless(DSN,'BLOCKED: isolated PostgreSQL DSN not configured')
class ReviewTwo(unittest.TestCase):
    setUpClass=classmethod(pg.PostgreSQLCommands.setUpClass.__func__)
    setUp=phase.LegacyAdapters.setUp
    tearDown=phase.LegacyAdapters.tearDown
    tearDownDB=pg.PostgreSQLCommands.tearDown
    save=phase.LegacyAdapters.save
    free=pg.PostgreSQLCommands.free

    def command(self,owner='a',**body):
        class Handler: pass
        h=Handler();h._pid=owner
        self.app.monetization_commands.handle(h,'/api/agent/search-command',body)
        return h.result[1]

    @contextlib.contextmanager
    def server(self,serving=False):
        import kleal_auth
        from serving import KlealServer
        accounts={x:{'person_id':x,'created':100,'sessions':{hashlib.sha256(x.encode()).hexdigest():{'exp':time.time()+3600}}} for x in ('a','b','c','d')}
        users=[{'id':x,'owner':x,'name':'Same name'} for x in accounts]
        server=(KlealServer if serving else ThreadingHTTPServer)(('127.0.0.1',0),self.app.H)
        original=self.app.send_json
        self.app.send_json=lambda h,status,obj:self.app._send_json_raw(h,obj.get('httpStatus',status) if isinstance(obj,dict) else status,obj)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        with patch.object(kleal_auth,'_accounts',return_value=accounts),patch.object(kleal_auth,'_population',return_value=users):
            thread.start()
            try: yield server,accounts
            finally:
                server.shutdown();server.server_close();thread.join(2);self.app.send_json=original

    def request(self,server,path,body=None,owner='a'):
        conn=http.client.HTTPConnection(*server.server_address,timeout=5)
        conn.request('POST' if body is not None else 'GET',path,json.dumps(body) if body is not None else None,
                     {'Authorization':'Bearer '+owner,'Content-Type':'application/json'})
        response=conn.getresponse();value=response.status,json.loads(response.read());conn.close();return value

    def test_group_rerank_real_handler_keeps_single_resource_and_same_invite_group(self):
        self.app.load_candidates=self.real_candidates
        self.app._load_pool_rows=lambda:[dict(id=x,name='Display '+x,age=25,verified=True,interests=['coffee'],open=True,
                    langs=['en'],vibe='chill',formats=['online'],km=1) for x in ('a','b','c','d')]
        self.app._people_index(force=True);self.app.match_candidates=self.real_match;self.app._policy_ok_now=self.real_policy
        for tier,owner,peer in [('free','a','b'),('plus','c','d')]:
            if tier=='free': self.free(owner)
            saved=self.save(owner,key='save-'+owner)
            group=self.app.gi_create(owner,{'id':saved['id'],'topics':['coffee']},'Canonical',idem='group-'+owner)['group']
            gid=group['gid']
            with ms.transaction() as tx:
                rid=tx.resolve('group',gid);before=copy.deepcopy(tx.resource(rid))
            with self.server() as (server,_):
                code,result=self.request(server,'/api/agent/search-command',{'operation':'rank_group','groupId':gid,
                    'commandId':'rank-'+owner,'intent':{'title':'tampered'}},owner)
            self.assertEqual(code,200,result);self.assertEqual(result['launchState'],'ready')
            self.assertEqual(result['searchId'],rid);self.assertEqual(result['intent']['topics'],['coffee'])
            self.assertEqual(result['intent']['format'],'group')
            with ms.transaction() as tx:
                stored=next(g for g in tx.documents()['_gintents'] if g['id']==gid)
                self.assertEqual(result['intent']['groupSize'],stored['max_total'])
            invite=self.app.gi_invite(gid,owner,peer,idem='invite-'+owner)
            self.assertTrue(invite['ok'],invite)
            with ms.transaction() as tx:
                self.assertEqual(next(i for i in tx.documents()['_ginvites'] if i['id']==invite['invite']['id'])['gid'],gid)
                self.assertEqual(tx.conn.execute('select count(*) from monetization_resources where owner_id=%s',(owner,)).fetchone()[0],1)
                self.assertEqual(tx.resource(rid)['published'],before['published'])
                self.assertEqual(tx.resource(rid)['payload'],before['payload'])
            with self.assertRaises(ms.CommandError): self.command(owner=peer,operation='rank_group',groupId=gid,commandId='foreign-'+peer)

    def test_deleted_standalone_cannot_resume_or_replay_but_group_alias_survives(self):
        original={'commandId':'original','intent':{'topics':['coffee']}}
        launched=self.command(**original);rid=launched['searchId']
        self.assertTrue(self.app.delete_intent('Same name',launched['id'],owner_id='a')['ok'])
        self.assertEqual(ms.status('a')['searches'],[])
        for body in (original,{'operation':'resume','searchId':rid,'commandId':'new'},
                     {'intent':{'_searchId':rid,'topics':['coffee']},'commandId':'recreate'}):
            with self.assertRaises(ms.CommandError) as error:self.command(**body)
            self.assertEqual(error.exception.code,'search_deleted')
        with ms.transaction() as tx:
            self.assertEqual(tx.documents()['_intents'],[])
            self.assertEqual(tx.resource(rid)['payload'],{})
            self.assertTrue(tx.conn.execute("select 1 from monetization_commands where command_key='original'").fetchone())
        saved=self.save(key='group-save')
        gid=self.app.gi_create('a',{'id':saved['id'],'topics':['coffee']},'Group',idem='g')['group']['gid']
        self.assertTrue(self.app.delete_intent('Same name',saved['id'],owner_id='a')['ok'])
        with ms.transaction() as tx:
            self.assertEqual(tx.resource(tx.resolve('group',gid))['state'],'active')
            self.assertEqual(len(tx.documents()['_gintents']),1)
        self.assertTrue(self.app.gi_invite(gid,'a','b',idem='keep-obligation')['ok'])

    def test_read_snapshot_connection_schema_and_fence_errors_are_json_503(self):
        with self.server() as (server,_):
            with patch.object(ms.db,'_connect',side_effect=RuntimeError('PRIVATE connection secret')):
                code,body=self.request(server,'/health')
            self.assertEqual((code,body['error']),(503,'monetization_unavailable'))
            self.assertNotIn('PRIVATE',json.dumps(body));self.assertTrue(body['retryable'])
            with ms.connection() as c:c.execute('alter table monetization_accounts rename to unavailable_accounts')
            code,body=self.request(server,'/health');self.assertEqual((code,body['error']),(503,'monetization_unavailable'))
            with ms.connection() as c:c.execute('alter table unavailable_accounts rename to monetization_accounts')
            for key,value,error in [('ready',False,'monetization_migration_required'),('release_state','fenced','monetization_release_fenced')]:
                with ms.connection() as c:c.execute('insert into monetization_meta values(%s,%s) on conflict(key) do update set value=excluded.value',(key,json.dumps(value)))
                code,body=self.request(server,'/health');self.assertEqual((code,body['error']),(503,error))
                with ms.connection() as c:c.execute('insert into monetization_meta values(%s,%s) on conflict(key) do update set value=excluded.value',(key,json.dumps(True if key=='ready' else 'enforce')))

    def test_legacy_recovery_is_visible_member_scoped_and_quota_aware(self):
        gid=self.app.group_create('a','Legacy',['coffee'],idem='g')['group']['gid']
        self.assertTrue(self.app.group_join(gid,'b','join')['ok'])
        self.save('b',key='busy')
        with ms.transaction() as tx:tx.conn.execute("update monetization_accounts set eligible=false,preview_start=null,preview_end=null where owner_id='b'")
        self.assertTrue(self.app.group_leave(gid,'a','leave')['ok'])
        public=self.app.group_list('b')[0]
        self.assertTrue(public['role_recovery']);self.assertFalse(public['host'])
        self.assertEqual(ms.status('b')['recoverableGroups'],[{'gid':gid,'title':'Legacy','model':'legacy'}])
        self.assertEqual(ms.status('c')['recoverableGroups'],[])
        self.assertFalse(self.app.group_recover(gid,'c','foreign')['ok'])
        self.assertEqual(self.app.group_recover(gid,'b','busy')['error'],'search_quota')
        with ms.transaction() as tx:
            own=tx.conn.execute("select id from monetization_resources where owner_id='b' and state='active'").fetchone()[0]
            tx.pause('b',own)
        with self.server() as (server,_):code,result=self.request(server,'/api/agent/group-recover',{'gid':gid,'idem':'retry'},'b')
        self.assertEqual(code,200,result);self.assertEqual(result['group']['host'],'b')
        self.assertFalse(result['group']['role_recovery']);self.assertEqual(ms.status('b')['usage']['activeSearches'],1)
        modern=self.app.gi_create('c',{'topics':['coffee']},'Modern',idem='modern')['group']['gid']
        self.assertFalse(self.app.group_recover(modern,'c','wrong-model')['ok'])

    def test_blocker_destination_does_not_depend_on_message_history(self):
        with ms.transaction() as tx:
            sid=tx.message('a','b');tx.message('c','d')
            tx.save_documents({'_messages':[],'_requests':[]})
        status=ms.status('a')
        self.assertEqual(status['chatBlockers'],[{'sessionId':sid,'peerId':'b','peerName':'b'}])
        self.assertEqual([b['peerId'] for b in status['chatBlockers']],['b'])
        self.assertEqual(self.app.threads_for('a'),[])
        with ms.transaction() as tx:tx.end_pair('a','b','end_chat')
        self.assertEqual(ms.status('a')['chatBlockers'],[])

    def test_projection_queries_are_bounded_for_4_100_890_owners(self):
        import psycopg
        original=psycopg.Connection.execute
        metrics=[]
        for count in (4,100,890):
            with ms.connection() as c:
                c.execute('insert into monetization_accounts(owner_id,eligible) select \'scale_\'||i,false from generate_series(1,%s) i on conflict do nothing',(count,))
                c.execute("insert into monetization_resources select 'scale_search_'||i,'scale_'||i,'active',1,'{}','ready' from generate_series(1,%s) i on conflict do nothing",(count,))
                doc={'_intents':[{'id':'scale_intent_'+str(i),'owner_id':'scale_'+str(i)} for i in range(1,count+1)]}
                doc.update({'scale_'+str(i):{'synthetic':'owner document'} for i in range(1,count+1)})
                c.execute("insert into monetization_aliases select 'intent','scale_intent_'||i,'scale_search_'||i from generate_series(1,%s) i on conflict do nothing",(count,))
                ms.Transaction(c).save_documents(doc)
            queries=[]
            def measured(conn,query,*args,**kwargs):queries.append(str(query));return original(conn,query,*args,**kwargs)
            start=time.perf_counter()
            with patch.object(psycopg.Connection,'execute',measured):snapshot=self.app.monetization_commands.read_snapshot()
            read_count=len(queries);elapsed=(time.perf_counter()-start)*1000;queries.clear()
            with patch.object(psycopg.Connection,'execute',measured):
                self.assertTrue(self.app.thread_mark_read('a','b')['ok'])
            metrics.append((count,read_count,len(queries),round(elapsed,2)))
            self.assertEqual(len(snapshot['_intents']),count)
        self.assertLessEqual(max(m[1] for m in metrics)-min(m[1] for m in metrics),1,metrics)
        self.assertLessEqual(max(m[2] for m in metrics)-min(m[2] for m in metrics),1,metrics)
        self.assertLessEqual(max(m[1] for m in metrics),10,metrics)
        print('PROJECTION_SCALE owners/readSQL/writerSQL/readMs',metrics)

    def test_synthetic_snapshot_preserves_nonempty_operator_state_and_sequences(self):
        import monetization_admin as admin
        with ms.connection() as c:
            for owner in ('a','b'):
                c.execute('insert into users(id,name_key,name,row) values(%s,%s,%s,%s)',(owner,owner,owner,json.dumps({'id':owner})))
            now=ms.Transaction(c).now
            payload=dict(action='grant',owner='a',operator='synthetic operator',reason='round trip',key='grant-key',expires=now+3600,apply=True)
            grant=admin.command(c,**payload)
            admin.begin_delete(c,'b')
            c.execute("select nextval(pg_get_serial_sequence('monetization_admin_audit','id'))")
            snapshot=rehearsal.backup(c)
        schema='test_restore_'+uuid.uuid4().hex
        with self.psycopg.connect(DSN,autocommit=True) as c:c.execute('create schema '+schema)
        try:
            with self.psycopg.connect(DSN,options='-c search_path='+schema) as c:
                rehearsal.restore(c,snapshot)
                self.assertEqual(rehearsal.backup(c)['checksum'],snapshot['checksum'])
                self.assertEqual(admin.command(c,**payload),grant)
                new=admin.command(c,**dict(payload,key='next-key'))
                self.assertNotEqual(new['grantId'],grant['grantId'])
                self.assertEqual(c.execute('select max(id) from monetization_admin_audit').fetchone()[0],3)
                with self.assertRaises(ms.CommandError):admin.command(c,**dict(payload,owner='b',key='deleted'))
            old=dict(snapshot,version=1);old['checksum']=ms.digest({k:v for k,v in old.items() if k!='checksum'})
            with self.psycopg.connect(DSN,options='-c search_path='+schema) as c:
                with self.assertRaises(ValueError):rehearsal.restore(c,old)
        finally:
            with self.psycopg.connect(DSN,autocommit=True) as c:c.execute('drop schema '+schema+' cascade')

    def test_post_smoke_executes_real_kyc_and_quota_denials_without_mutation(self):
        import age_verification as age
        self.free();self.save()
        before=ms.status('a')['searches']
        with self.server(serving=True) as (server,accounts),patch.dict(os.environ,{'SYNTHETIC_SMOKE_AUTH':'Bearer a'}):
            check={'name':'quota','url':'http://127.0.0.1:%s/api/agent/search-command'%server.server_port,
                   'method':'POST','body':{'commandId':'denial','intent':{'topics':['new']}},'status':409,
                   'headersEnv':{'Authorization':'SYNTHETIC_SMOKE_AUTH'},'json':{'error':'search_quota'}}
            self.assertEqual(production.release.smoke([check]),[{'name':'quota','ok':True}])
            with patch.dict(os.environ,{'KLEAL_AGE_GATE_ENABLED':'1','KLEAL_AGE_COHORT_KEYS':'["a"]','KLEAL_AGE_GATE_FROM':'1',
                        'KLEAL_AGE_DB':self.tmp.name+'/age.sqlite','KLEAL_AGE_BINDING_SECRET':'synthetic-only-binding-secret-for-local-tests'}):
                with age.database() as c:c.execute("insert into verification(subject,status) values(?,'declined')",(age.subject('a',accounts['a']),))
                self.assertEqual(production.release.smoke([dict(check,name='kyc',status=403,json={'error':'age_verification_required'})]),[{'name':'kyc','ok':True}])
            for invalid in (dict(check,status=None),dict(check,status=200),dict(check,body={'token':'do not log'})):
                with self.assertRaises(ValueError):production.release.smoke([invalid])
        self.assertEqual(ms.status('a')['searches'],before)
        with ms.connection() as c:self.assertFalse(c.execute("select 1 from monetization_commands where command_key='denial'").fetchone())

    def test_bounded_load_cli_runs_and_cleans_up(self):
        result=subprocess.run([os.sys.executable,str(Path(__file__).resolve().parents[1]/'tools/monetization_load.py'),
                               '--workers','2','--owners','2','--attempts','2'],text=True,capture_output=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        report=json.loads(result.stdout)
        self.assertTrue(report['cleanupConfirmed']);self.assertEqual(report['unexpectedErrors'],0)
        self.assertEqual(report['afterDrain']['outboxPending'],0)


if __name__=='__main__':unittest.main()
