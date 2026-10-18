"""Release-seven boundaries: real files, loopback HTTP, CLI and disposable PG."""
import contextlib
import copy
from datetime import datetime, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import patch

import test_monetization_pg as pg
import test_monetization_phase2 as phase
import test_monetization_review2 as review2
import test_monetization_production as production
from test_monetization_pg import DSN, ms


@contextlib.contextmanager
def http_server(handler):
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown(); server.server_close(); thread.join(2)


@unittest.skipUnless(DSN, 'BLOCKED: isolated PostgreSQL DSN not configured')
class ReviewSeven(unittest.TestCase):
    setUpClass = classmethod(pg.PostgreSQLCommands.setUpClass.__func__)
    setUp = phase.LegacyAdapters.setUp
    tearDown = phase.LegacyAdapters.tearDown
    tearDownDB = pg.PostgreSQLCommands.tearDown
    command = review2.ReviewTwo.command
    server = review2.ReviewTwo.server
    request = review2.ReviewTwo.request

    def buddy(self):
        spec = importlib.util.spec_from_file_location('review7_buddy', pg.ROOT/'services/buddy/app.py')
        buddy = importlib.util.module_from_spec(spec); spec.loader.exec_module(buddy)
        buddy.STORE_PATH = str(Path(self.tmp.name)/'buddy.json')
        buddy.SESSIONS = buddy._load_store()
        self.assertFalse(buddy._STORE_UNAVAILABLE)
        return buddy

    def test_launch_real_writer_failures_never_dispatch_and_retry_survives_reload(self):
        buddy = self.buddy(); body = {'intent': {'topics': ['coffee']}, 'commandId': 'durable'}
        original_fdopen = buddy.os.fdopen
        class BrokenWrite:
            def __init__(self, *args, **kwargs): self.stream = original_fdopen(*args, **kwargs)
            def __enter__(self): return self
            def __exit__(self, *args): return self.stream.__exit__(*args)
            def write(self, data): raise OSError('sensitive local path must not escape')
        with self.server() as (matching, _), http_server(buddy.H) as server:
            buddy.MATCH_URL = 'http://127.0.0.1:'+str(matching.server_port)
            buddy._save_store(); original = Path(buddy.STORE_PATH).read_bytes()
            for owner, field, failing in ((buddy.os,'fdopen',BrokenWrite),
                    (buddy.os,'replace',OSError('sensitive replace')),
                    (buddy.os,'fsync',OSError('sensitive sync'))):
                with self.subTest(failure=field), patch.object(owner,field,side_effect=failing), patch.object(buddy,'_post') as dispatch:
                    code, result = self.request(server, '/api/buddy/launch', body)
                    self.assertEqual((code,result),(503,{'ok':False,'error':'buddy_store_unavailable','retryable':True}))
                    dispatch.assert_not_called()
                self.assertEqual(Path(buddy.STORE_PATH).read_bytes(), original)
                self.assertEqual(list(Path(self.tmp.name).glob('.buddy-*')), [])
            sent = []; original_post = buddy._post
            def wire(base, path, payload, **kwargs):
                if path.endswith('/match'): sent.append(copy.deepcopy(payload))
                return original_post(base, path, payload, **kwargs)
            with patch.object(buddy,'_post',wire), patch.object(self.app,'render_search',return_value={'candidates':[]}):
                code, first = self.request(server,'/api/buddy/launch',body)
                self.assertEqual(code,200,first)
                buddy.SESSIONS = buddy._load_store()
                session = next(iter(buddy.SESSIONS.values()))
                session['signals'] = {'area':'new city'}; session['profile'] = {'city':'changed'}
                code, again = self.request(server,'/api/buddy/launch',body)
                self.assertEqual(code,200,again); self.assertEqual(first['searchId'],again['searchId'])
                self.assertEqual(sent[0],sent[1])
                self.assertNotIn('Bearer',Path(buddy.STORE_PATH).read_text())
                self.assertIn('durable',session['launch_receipts'])
            with ms.transaction() as tx:
                self.assertEqual(tx.conn.execute('select count(*) from monetization_resources').fetchone()[0],1)

    def test_corrupt_existing_buddy_store_is_preserved_and_blocks_dispatch(self):
        buddy = self.buddy(); target = Path(buddy.STORE_PATH)
        with self.server(), http_server(buddy.H) as server:
            for corrupt in ('{"broken":', '[]', '{"a":{"launch_retries":[]}}',
                            '{"a":{"launch_retry":[]}}',
                            '{"a":{"launch_retries":{"key":{"commandId":"key","payload":{}}}}}'):
                target.write_text(corrupt); buddy.SESSIONS = buddy._load_store()
                with patch.object(buddy,'_post') as dispatch:
                    code,result = self.request(server,'/api/buddy/launch',{'intent':{'topics':['coffee']},'commandId':'same'})
                    self.assertEqual(code,503,result); self.assertTrue(result['retryable']); dispatch.assert_not_called()
                self.assertEqual(target.read_text(),corrupt)

    def test_buddy_concurrent_launch_store_serialized_but_matching_network_unlocked(self):
        buddy = self.buddy(); entered=threading.Event(); release=threading.Event(); saves=[]
        original_replace=buddy.os.replace
        def replace(source,target):
            saved=json.loads(Path(source).read_text()); saves.append(saved)
            return original_replace(source,target)
        def wire(base,path,payload,**kwargs):
            if payload['commandId']=='first':
                entered.set(); self.assertTrue(release.wait(3))
            return {'ok':True,'searchId':payload['commandId'],'launchState':'pending','retryable':True,'candidates':[]}
        result=[]
        with self.server(), http_server(buddy.H) as server, patch.object(buddy,'_post',wire), patch.object(buddy.os,'replace',replace):
            first=threading.Thread(target=lambda:result.append(self.request(server,'/api/buddy/launch',
                {'intent':{'topics':['coffee']},'commandId':'first'})))
            first.start(); self.assertTrue(entered.wait(2))
            try:
                # This request and its actual save must complete while first waits in network.
                code,second=self.request(server,'/api/buddy/launch',{'intent':{'topics':['tea']},'commandId':'second'})
                self.assertEqual(code,503,second)
                stored=json.loads(Path(buddy.STORE_PATH).read_text())
                self.assertEqual(set(next(iter(stored.values()))['launch_retries']),{'first','second'})
            finally: release.set();first.join(3)
            self.assertFalse(first.is_alive());self.assertEqual(result[0][0],503)
            self.assertTrue(saves);buddy.SESSIONS=buddy._load_store()
            self.assertEqual(set(next(iter(buddy.SESSIONS.values()))['launch_retries']),{'first','second'})

    def test_real_group_formation_receipt_pause_replay_has_no_roster(self):
        users=[dict(id=x,name=x,age=25,verified=True,interests=['coffee'],open=True,
                    langs=['en'],vibe='chill',formats=['online'],km=1) for x in ('a','b','c','d')]
        self.app.load_candidates=lambda:users;self.app._load_pool_rows=lambda:users
        self.app._people_index(force=True);self.app.match_candidates=self.real_match
        self.app._policy_ok_now=self.real_policy
        self.app.GROUPS_ENABLED=True;self.app.PILOT_DECISION_TYPES['group_formation']=True
        body={'commandId':'group-roster','intent':{'topics':['coffee'],'mode':'online','groupSize':3}}
        first=self.command(**body)
        self.assertEqual(first['launchState'],'ready');self.assertIn('group',first)
        self.assertTrue(first['group']['members'],first)
        self.command(operation='pause',searchId=first['searchId'],commandId='pause')
        replay=self.command(**body)
        self.assertEqual(replay['launchState'],'paused');self.assertEqual(replay['candidates'],[])
        self.assertNotIn('group',replay)

    def test_partner_closed_group_denial_commits_exact_invite_and_replays(self):
        for kind,peer in (('respond','b'),('approve','c')):
            gid=self.app.gi_create('a',{'topics':['coffee']},'Closed '+kind,idem='create-'+kind)['group']['gid']
            inv=self.app.gi_invite(gid,'a',peer,idem='invite-'+kind)['invite']['id']
            # Represents an imported closed group with an old open invitation.
            with ms.transaction() as tx:
                doc=tx.documents();next(g for g in doc['_gintents'] if g['id']==gid)['state']='closed_by_owner'
                if kind=='approve':next(i for i in doc['_ginvites'] if i['id']==inv)['state']='awaiting_approval'
                tx.save_documents(doc)
            self.app.monetization_commands.refresh()
            action=lambda:self.app.gi_respond(inv,peer,True,'closed-'+kind) if kind=='respond' else self.app.gi_approve(gid,'a',peer,True,'closed-'+kind)
            result=action();self.assertFalse(result['ok']);self.assertEqual(result['error'],'CLOSED')
            with ms.transaction() as tx:
                doc=tx.documents();self.assertEqual(next(i for i in doc['_ginvites'] if i['id']==inv)['state'],'group_closed')
                self.assertFalse(any(m.get('name')==peer for g in doc['_gintents'] if g['id']==gid for m in g.get('members',[])))
            self.assertEqual(action(),result)
            self.assertIsNone(ms.status(peer)['previewStartedAt'])

    def test_partner_message_delete_queues_media_only_on_committed_canonical_transition(self):
        folder=Path(self.tmp.name)/'videos';folder.mkdir();self.app.VIDEO_DIR=str(folder)
        filename='abcdef123456.mp4';media=folder/filename;media.write_bytes(b'synthetic video')
        url='/api/agent/video/'+filename;pair=self.app._pair_key('a','b')
        with ms.transaction() as tx:
            doc=tx.documents();doc['_messages']=[
                {'id':'video','from':'a','to':'b','pair':pair,'text':'private caption','video':{'url':url},'t':1},
                {'id':'quote','from':'b','to':'a','pair':pair,'text':'reply','rt':{'id':'video','text':'private caption'},'t':2}]
            tx.save_documents(doc)
        cmd=self.app.monetization_commands
        with patch.object(cmd,'_reconcile',side_effect=ms.CommandError('synthetic_rollback',503)):
            self.assertFalse(self.app.message_delete('a','video')['ok'])
        self.assertTrue(media.is_file())
        with ms.transaction() as tx:
            self.assertIn('video',tx.documents()['_messages'][0])
            self.assertEqual(tx.conn.execute("select count(*) from outbox where topic='monetization.media.cleanup'").fetchone()[0],0)
        self.assertTrue(self.app.message_delete('a','video')['ok']);self.assertTrue(media.is_file())
        with ms.transaction() as tx:
            rows=tx.documents()['_messages'];self.assertNotIn('video',rows[0]);self.assertTrue(rows[0]['deleted'])
            self.assertEqual(rows[1]['rt'],{'id':'video','text':'','deleted':True})
            self.assertEqual(tx.conn.execute("select payload from outbox where topic='monetization.media.cleanup'").fetchone()[0],
                             {'kind':'video','name':filename})
        self.assertEqual(cmd.drain_cleanup(),1);self.assertFalse(media.exists())

    def test_real_admin_subprocess_defaults_dry_run_and_applies_only_requested_grant(self):
        with ms.connection() as conn:
            conn.execute("insert into users(id,name_key,name,row) values('a','synthetic-a','Synthetic A','{}')")
        conninfo=self.psycopg.conninfo.make_conninfo(DSN,options='-c search_path='+self.schema)
        env={**os.environ,'KLEAL_PG_DSN':conninfo}
        common=['--user-id','a','--operator','synthetic-test','--reason','release seven regression']
        expires=datetime.fromtimestamp(time.time()+86400,timezone.utc).isoformat()
        def cli(args):
            result=subprocess.run([sys.executable,str(pg.ROOT/'tools/monetization_admin.py'),*args],env=env,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,0,result.stderr);return json.loads(result.stdout)
        def rows():
            with ms.connection() as conn:
                return {t:conn.execute('select to_jsonb(r) from '+t+' r order by to_jsonb(r)::text').fetchall()
                        for t in ('monetization_manual_grants','monetization_admin_audit','monetization_admin_commands')}
        before=rows();grant=['grant',*common,'--key','cli-grant','--expires',expires]
        self.assertTrue(cli(grant)['dryRun']);self.assertEqual(rows(),before)
        applied=cli(grant+['--apply']);self.assertFalse(applied['dryRun']);grant_id=applied['grantId']
        survivor=cli(['grant',*common,'--key','cli-survivor','--expires',expires,'--apply'])['grantId']
        revoke=['revoke',*common,'--key','cli-revoke','--grant-id',grant_id];before=rows()
        self.assertTrue(cli(revoke)['dryRun']);self.assertEqual(rows(),before)
        self.assertFalse(cli(revoke+['--apply'])['dryRun'])
        with ms.connection() as conn:
            grants=dict(conn.execute('select id,revoked from monetization_manual_grants').fetchall())
            self.assertIsNotNone(grants[grant_id]);self.assertIsNone(grants[survivor])
            self.assertEqual(conn.execute('select count(*) from monetization_admin_audit').fetchone()[0],3)
            self.assertEqual(conn.execute('select count(*) from monetization_admin_commands').fetchone()[0],3)

    def test_backup_cli_actual_writer_guard_precedes_snapshot_and_file(self):
        release=production.release;units={r:'synthetic-'+r+'.service' for r in release.WRITER_ROLES}
        conninfo=self.psycopg.conninfo.make_conninfo(DSN,options='-c search_path='+self.schema)
        target=Path(self.tmp.name)/'backup.json';state={'value':'active','load':'loaded'};calls=[]
        def systemctl(args,**kwargs):
            self.assertEqual(args[:2],['systemctl','show']);calls.append(args)
            return SimpleNamespace(returncode=0,stdout='LoadState='+state['load']+'\nActiveState='+state['value']+'\n')
        argv=['release','backup','--file',str(target)]
        with patch.dict(os.environ,{'KLEAL_PG_DSN':conninfo,'KLEAL_RELEASE_SERVICES':json.dumps(units)}), \
             patch.object(sys,'argv',argv),patch.object(release.subprocess,'run',systemctl):
            # A real read would see this unknown table and fail differently. The
            # writer guard must reject first; no snapshot/source primitive is mocked.
            with ms.connection() as conn:conn.execute('create table unexpected_for_backup(id int)')
            for value,load in (('active','loaded'),('activating','loaded'),('inactive','not-found')):
                state.update(value=value,load=load)
                with self.assertRaisesRegex(ValueError,'writers must|cannot establish'):release.main()
                self.assertFalse(target.exists())
            with ms.connection() as conn:conn.execute('drop table unexpected_for_backup')
            state.update(value='inactive',load='loaded')
            with contextlib.redirect_stdout(io.StringIO()):release.main()
            self.assertTrue(target.is_file());self.assertEqual(json.loads(target.read_text())['version'],2)
            self.assertGreaterEqual(len(calls),len(units))


class SmokeRedirects(unittest.TestCase):
    def test_redirects_never_forward_credentials_or_post_to_second_endpoint(self):
        seen=[];mode={'code':302,'location':''};secret='synthetic-only-secret'
        class Destination(BaseHTTPRequestHandler):
            def do_GET(self):seen.append((self.command,self.headers.get('Authorization')));self.send_response(200);self.end_headers()
            do_POST=do_GET
            def log_message(self,*args):pass
        class Origin(BaseHTTPRequestHandler):
            def do_GET(self):self.send_response(mode['code']);self.send_header('Location',mode['location']);self.end_headers()
            do_POST=do_GET
            def log_message(self,*args):pass
        with http_server(Destination) as destination,http_server(Origin) as origin,patch.dict(os.environ,{'SYNTHETIC_SMOKE_TOKEN':secret}):
            mode['location']='http://127.0.0.1:'+str(destination.server_port)+'/target?secret='+secret
            for code in (301,302,303,307,308):
                mode['code']=code
                for method in ('GET','POST'):
                    probe={'name':'redirect','url':'http://127.0.0.1:'+str(origin.server_port),
                           'method':method,'status':403,'headersEnv':{'Authorization':'SYNTHETIC_SMOKE_TOKEN'}}
                    if method=='POST':probe['body']={'operation':'synthetic_denial'}
                    with self.assertRaises(ValueError) as error:production.release.smoke([probe])
                    self.assertNotIn(secret,str(error.exception));self.assertEqual(seen,[])


if __name__=='__main__':unittest.main()
