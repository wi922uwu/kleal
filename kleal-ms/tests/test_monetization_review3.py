"""Третий review: реальные HTTP/PG границы и subprocess startup."""
import copy
import json
import importlib.util
from http.server import ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import threading
import time
import unittest
from unittest.mock import patch

import test_monetization_phase2 as phase
import test_monetization_pg as pg
from test_monetization_pg import DSN, ms
import test_monetization_review2 as review2


@unittest.skipUnless(DSN,'BLOCKED: isolated PostgreSQL DSN not configured')
class ReviewThree(unittest.TestCase):
    setUpClass=classmethod(pg.PostgreSQLCommands.setUpClass.__func__)
    setUp=phase.LegacyAdapters.setUp
    tearDown=phase.LegacyAdapters.tearDown
    tearDownDB=pg.PostgreSQLCommands.tearDown
    save=phase.LegacyAdapters.save
    free=pg.PostgreSQLCommands.free
    command=review2.ReviewTwo.command
    server=review2.ReviewTwo.server
    request=review2.ReviewTwo.request

    def test_group_rank_modes_use_existing_group_without_publication(self):
        for mode in ('off','shadow','enforce'):
            with patch.dict(os.environ,{'KLEAL_MONETIZATION_MODE':mode}):
                group=self.app.gi_create('a',{'topics':['coffee']},'Original',idem='g-'+mode)['group']
                gid=group['gid']
                before=copy.deepcopy(self.app.SESSION)
                seen=[]
                def ranking(path,body,intent,ctx):
                    seen.append(copy.deepcopy(intent));return {'candidates':[]}
                with patch.object(self.app,'render_search',ranking),self.server() as (server,_):
                    code,result=self.request(server,'/api/agent/search-command',{'operation':'rank_group','groupId':gid,'commandId':'rank-'+mode})
                    self.assertEqual(code,200,result);self.assertEqual(result['launchState'],'ready')
                    denied,body=self.request(server,'/api/agent/search-command',{'operation':'rank_group','groupId':gid,'commandId':'foreign'},'b')
                    self.assertIn(denied,(403,404));self.assertFalse(body['ok'])
                self.assertEqual(seen[0]['topics'],['coffee']);self.assertEqual(seen[0]['format'],'group')
                self.assertEqual(len(self.app.SESSION.get('_gintents',[])),len(before.get('_gintents',[])))
                self.assertEqual(len(self.app.SESSION.get('_intents',[])),len(before.get('_intents',[])))
                self.assertTrue(self.app.gi_invite(gid,'a','b',idem='invite-'+mode)['ok'])

    def test_swap_rejects_deleted_paused_foreign_self_for_free_and_plus(self):
        for plus in (False,True):
            with ms.transaction() as tx:
                tx.account('a');tx.account('b')
                tx.conn.execute("delete from monetization_resources")
                tx.conn.execute("update monetization_accounts set eligible=%s,preview_start=null,preview_end=null,plus_until=%s",(plus,tx.now+3600 if plus else None))
                for rid,owner,state in [('deleted','a','deleted'),('paused','a','paused'),('foreign','b','active'),('self','a','active')]:
                    tx.conn.execute('insert into monetization_resources values(%s,%s,%s,1,\'{}\',\'ready\')',(rid,owner,state))
            for swap in ('deleted','paused','foreign','self'):
                with self.assertRaises(ms.CommandError):
                    ms.execute('a','swap',str(plus)+swap,{},lambda tx:tx.publish('a',{'title':'new'},rid='self' if swap=='self' else None,swap=swap))
                with ms.transaction() as tx:
                    self.assertIsNone(tx.account('a')['start'])
                    self.assertEqual(tx.resource('deleted')['state'],'deleted')
                    self.assertEqual(tx.conn.execute('select count(*) from monetization_resources').fetchone()[0],4)
            with ms.transaction() as tx:
                rid=tx.publish('a',{'title':'valid'},swap='self');self.assertEqual(tx.resource('self')['state'],'paused')
                self.assertEqual(tx.resource(rid)['state'],'active')

    def test_cached_receipt_respects_receiving_pause_and_recovers_original_ranking(self):
        rows=[dict(id=x,name=x,age=25,verified=True,open=True,interests=['coffee']) for x in ('a','b')]
        self.app.load_candidates=lambda:rows
        original={'ok':True,'candidates':[{'id':'b','name':'b'}],'group':{'members':['b']},'shown':1}
        original['_candidate_refs']=self.app.monetization_commands.candidate_refs(original,rows,{'topics':['coffee']})
        for receiving in ({'status':'paused'},{'status':'paused','paused_until':time.time()+3600}):
            rows[1]['receiving']=receiving
            with ms.transaction() as tx:
                result=self.app.monetization_commands.safe_receipt(tx,'a',copy.deepcopy(original),{'topics':['coffee']})
            self.assertEqual(result['candidates'],[]);self.assertNotIn('group',result)
        rows[1]['receiving']={'status':'paused','paused_until':time.time()-1}
        with ms.transaction() as tx:result=self.app.monetization_commands.safe_receipt(tx,'a',copy.deepcopy(original),{'topics':['coffee']})
        self.assertEqual(result,original)
        with patch.object(self.app,'render_search',return_value={'candidates':original['candidates'],'group':original['group']}):
            body={'commandId':'cached','intent':{'topics':['coffee']}}
            ready=self.command(**body);self.assertEqual(len(ready['candidates']),1)
            rows[1]['receiving']={'status':'paused'}
            replay=self.command(**body);self.assertEqual(replay['candidates'],[]);self.assertNotIn('group',replay)
            rows[1]['receiving']={'status':'active'}
            self.assertEqual(self.command(**body)['candidates'],ready['candidates'])

    def test_buddy_actual_http_error_pending_and_client_contract(self):
        root=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('review3_buddy',root/'services/buddy/app.py')
        buddy=importlib.util.module_from_spec(spec);spec.loader.exec_module(buddy)
        buddy._save_store=lambda:None;buddy.SESSIONS={}
        with self.server() as (matching,_):
            buddy.MATCH_URL='http://127.0.0.1:'+str(matching.server_port)
            server=ThreadingHTTPServer(('127.0.0.1',0),buddy.H)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                body={'intent':{'topics':['coffee']},'commandId':'buddy-wire'}
                with patch.object(self.app,'render_search',side_effect=RuntimeError('PRIVATE token exception')):
                    code,pending=self.request(server,'/api/buddy/launch',body)
                self.assertEqual((code,pending['error']),(503,'launch_pending'))
                self.assertEqual(pending['launchState'],'pending');self.assertTrue(pending['retryable'])
                rid=pending['searchId'];self.assertEqual(pending['intent']['_searchId'],rid)
                with patch.object(self.app,'render_search',return_value={'candidates':[]}):
                    code,ready=self.request(server,'/api/buddy/launch',{})
                self.assertEqual(code,200,ready);self.assertEqual(ready['searchId'],rid)
                self.assertEqual(ready['commandId'],'buddy-wire');self.assertEqual(ready['launchState'],'ready')
                with ms.transaction() as tx:
                    self.assertEqual(tx.conn.execute('select count(*) from monetization_resources').fetchone()[0],1)
                    tx.conn.execute("update monetization_accounts set eligible=false,preview_start=null,preview_end=null where owner_id='a'")
                code,quota=self.request(server,'/api/buddy/launch',dict(body,commandId='buddy-second'))
                self.assertEqual((code,quota['error']),(409,'search_quota'));self.assertEqual(quota['blockerIds'],[rid])
                with patch.object(self.app.monetization_commands,'read_snapshot',side_effect=ms.CommandError('monetization_unavailable',503)):
                    code,unavailable=self.request(server,'/api/buddy/launch',dict(body,commandId='buddy-unavailable'))
                self.assertEqual((code,unavailable['error']),(503,'monetization_unavailable'));self.assertTrue(unavailable['retryable'])
                self.assertNotIn('PRIVATE',json.dumps([pending,quota,unavailable]))
            finally:server.shutdown();server.server_close();thread.join(2)

    def test_terminal_invitation_denial_commits_only_safe_transition_and_replays(self):
        gid=self.app.gi_create('a',{'topics':['coffee']},'Group',idem='g')['group']['gid']
        invite=self.app.gi_invite(gid,'a','b',idem='invite')['invite']['id']
        with patch.object(self.app,'_policy_ok_now',return_value=(False,'policy changed')),self.server() as (server,_):
            code,result=self.request(server,'/api/agent/ginvite-respond',{'id':invite,'accept':True,'idem':'denial'},'b')
            self.assertEqual((code,result['error']),(409,'NOT_ELIGIBLE'))
            self.assertEqual(self.request(server,'/api/agent/ginvite-respond',{'id':invite,'accept':True,'idem':'denial'},'b'),(code,result))
        with ms.transaction() as tx:
            doc=tx.documents();self.assertEqual(doc['_ginvites'][0]['state'],'policy_revoked')
            self.assertIsNone(tx.account('b')['start'])
        self.assertTrue(self.app.gi_invite(gid,'a','b',idem='reinvite')['ok'])
        def broken(who,idem=None):
            self.app.SESSION['unsafe']={'partial':True};return {'ok':False,'error':'NOT_ELIGIBLE'}
        self.assertFalse(self.app.monetization_commands._invoke('broken',broken,('a','partial'),{})['ok'])
        with ms.transaction() as tx:self.assertNotIn('unsafe',tx.documents())

    def test_archive_and_missing_request_do_not_trap_active_canonical_pair(self):
        saved=self.save();intent={'id':saved['id'],'topics':['coffee']}
        request=self.app.propose('a','b',intent,'',idem='proposal')['id']
        self.assertTrue(self.app.respond(request,'accept','b',idem='accept')['ok'])
        self.assertTrue(self.app.send_message('a','b','hello',client_id='message')['ok'])
        self.assertTrue(self.app.archive_request(request,'a')['ok'])
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],1)
        with ms.transaction() as tx:
            doc=tx.documents();doc['_requests']=[];tx.save_documents(doc)
        with self.server() as (server,_):
            code,result=self.request(server,'/api/agent/thread-end',{'with_id':'b','idem':'end'})
            self.assertEqual(code,200,result);self.assertTrue(result['ok'])
            self.assertEqual(self.request(server,'/api/agent/thread-end',{'with_id':'b','idem':'end'}),(code,result))
            code,result=self.request(server,'/api/agent/thread-end',{'with_id':'c','idem':'foreign'})
            self.assertFalse(result['ok'])
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],0)
        with ms.transaction() as tx:
            messages=tx.documents()['_messages'];self.assertTrue(any(m.get('text')=='hello' for m in messages))
            self.assertEqual(sum((m.get('sys') or {}).get('code')=='chat_ended' for m in messages),1)

    def test_terminal_group_capacity_and_closed_denials_commit_without_grant(self):
        for case in ('full','closed','approve-full'):
            gid=self.app.gi_create('a',{'topics':['coffee']},case,idem='g-'+case)['group']['gid']
            iid=self.app.gi_invite(gid,'a','b',idem='invite-'+case)['invite']['id']
            with ms.transaction() as tx:
                doc=tx.documents();group=next(g for g in doc['_gintents'] if g['id']==gid)
                if case=='closed':group['state']='cancelled'
                else:group['max_total']=len(self.app._gi_active(group))
                if case=='approve-full':next(i for i in doc['_ginvites'] if i['id']==iid)['state']='awaiting_approval'
                tx.save_documents(doc)
            path='/api/agent/gintent-approve' if case=='approve-full' else '/api/agent/ginvite-respond'
            body={'gid':gid,'who_id':'b','accept':True,'idem':'denial-'+case} if case=='approve-full' else {'id':iid,'accept':True,'idem':'denial-'+case}
            owner='a' if case=='approve-full' else 'b'
            with self.server() as (server,_):
                code,result=self.request(server,path,body,owner)
                self.assertEqual((code,result['error']),(409,'CLOSED' if case=='closed' else 'GROUP_FULL'))
                self.assertEqual(self.request(server,path,body,owner),(code,result))
            with ms.transaction() as tx:
                doc=tx.documents();invite=next(i for i in doc['_ginvites'] if i['id']==iid)
                self.assertEqual(invite['state'],'withdrawn' if case=='closed' else 'group_full')
                self.assertFalse(any(i['gid']==gid and i['state'] in ('sent','viewed','awaiting_approval') for i in doc['_ginvites']))
                self.assertIsNone(tx.account('b')['start'])

    def test_terminal_request_policy_denials_commit_and_replay_without_pair(self):
        saved=self.save();intent={'id':saved['id'],'topics':['coffee']}
        for method in ('respond','pick'):
            rid=self.app.propose('a','b',intent,'',idem='proposal-'+method)['id']
            if method=='pick':
                # Partner contract: a sole positive reply is accepted immediately;
                # the organizer picker exists only when the same intent has rivals.
                self.app.propose('a','c',intent,'',idem='pick-rival')
                answered=self.app.respond(rid,'accept','b',idem='answer',flow='pick')
                self.assertTrue(answered['ok']);self.assertEqual(answered['status'],'answered')
            path='/api/agent/respond' if method=='respond' else '/api/agent/request-pick'
            body={'id':rid,'decision':'accept','idem':'policy-'+method}
            with patch.object(self.app,'_policy_ok_now',return_value=(False,'synthetic policy change')),self.server() as (server,_):
                code,result=self.request(server,path,body,'b' if method=='respond' else 'a')
                self.assertEqual((code,result['error']),(409,'POLICY_CHANGED'))
                self.assertEqual(self.request(server,path,body,'b' if method=='respond' else 'a'),(code,result))
            with ms.transaction() as tx:
                request=next(r for r in tx.documents()['_requests'] if r['id']==rid)
                self.assertEqual(request['status'],'policy_revoked');self.assertGreater(request['version'],1)
                self.assertIsNone(tx.account('b')['start'])
                self.assertEqual(tx.conn.execute('select count(*) from monetization_sessions').fetchone()[0],0)

    def test_legacy_publication_http_command_aliases_replay_without_duplicates(self):
        with self.server() as (server,_):
            for route in ('intent-save','group-create','gintent-create'):
                for alias in ('commandId','idem',None):
                    body={'title':route+str(alias),'intent':{'topics':['coffee']},'topics':['coffee'],'launched':True}
                    if alias:body[alias]=route+alias
                    first=self.request(server,'/api/agent/'+route,body)
                    self.assertEqual(first[0],200,first);self.assertTrue(first[1]['ok'],first)
                    self.assertEqual(self.request(server,'/api/agent/'+route,body),first)
                    if alias:
                        code,value=self.request(server,'/api/agent/'+route,dict(body,title='conflicting'))
                        self.assertEqual((code,value['error']),(409,'idempotency_payload_conflict'))

    def test_actual_startup_completes_pending_launch_and_media_cleanup(self):
        from psycopg.conninfo import make_conninfo
        with patch.object(self.app,'render_search',side_effect=RuntimeError('synthetic pending')):
            result=self.command(commandId='startup',intent={'topics':['coffee']})
        self.assertEqual(result['launchState'],'pending')
        media=Path(self.tmp.name)/'aabbccdd.webm';media.write_bytes(b'synthetic media')
        keep=Path(self.tmp.name)/'deadbeef.webm';keep.write_bytes(b'synthetic referenced media')
        with ms.transaction() as tx:
            doc=tx.documents();doc['_synthetic_reference']={'file':keep.name};tx.save_documents(doc)
            for file in (media,keep):ms.db.outbox_put('monetization.media.cleanup',{'kind':'voice','name':file.name},conn=tx.conn)
        root=Path(__file__).resolve().parents[1]
        env=dict(os.environ,KLEAL_DB='postgres',KLEAL_PG_DSN=make_conninfo(DSN,options='-c search_path='+self.schema),
                 PGOPTIONS='-c search_path='+self.schema,KLEAL_MONETIZATION_MODE='enforce',MATCHING_PORT='0',
                 SYNTHETIC_STARTUP_MEDIA=self.tmp.name,PYTHONPATH=os.pathsep.join(map(str,(root/'tests',root/'shared',root/'tools',root/'services/matching'))))
        proc=subprocess.Popen([os.sys.executable,'-c',"import monetization_startup_adapter as adapter;adapter.entrypoint("+repr(str(root/'services/matching/app.py'))+")"],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                with ms.connection() as c:
                    receipt=c.execute("select result from monetization_commands where command_key='startup'").fetchone()[0]
                    pending=c.execute("select count(*) from outbox where sent_at is null").fetchone()[0]
                if receipt.get('launchState')=='ready' and not media.exists() and pending==0:break
                if proc.poll() is not None:break
                time.sleep(.1)
            self.assertEqual(receipt.get('launchState'),'ready');self.assertFalse(media.exists())
            self.assertTrue(keep.exists());self.assertEqual(pending,0)
        finally:
            proc.terminate()
            out,err=proc.communicate(timeout=5)
            if err:print('STARTUP_DIAGNOSTICS',err)
            if proc.returncode not in (0,-15):self.fail(out+err)


if __name__=='__main__':unittest.main()
