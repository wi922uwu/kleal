import copy
import concurrent.futures
import ast
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import hashlib
import http.client
import json
import shutil
import subprocess
import threading
import time
import unittest
from unittest.mock import patch

import test_monetization_pg as pg
from test_monetization_pg import DSN, ms
import monetization_migrate as migration
import test_monetization as foundation
import monetization_admin as admin

ROOT = Path(__file__).resolve().parents[1]


class MigrationValidation(unittest.TestCase):
    def test_ambiguous_legacy_links_are_blocked(self):
        data={'synthetic':True,'users':[{'id':'a'}],'session':{
            '_intents':[{'id':'i','owner_id':'a'}],
            '_gintents':[{'id':'g','owner':'a','intent':{}}]}}
        self.assertTrue(any('alias' in x for x in migration.validate_fixture(data)))

    def test_live_fixture_rejected(self):
        self.assertTrue(migration.validate_fixture({'users':[],'session':{}}))

    def test_flags_off_by_default_and_invalid_fail_closed(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(ms.mode(),'off')
        with patch.dict(os.environ,{'KLEAL_MONETIZATION_MODE':'oops'}):
            with self.assertRaises(ms.CommandError): ms.mode()


@unittest.skipUnless(DSN,'BLOCKED: isolated PostgreSQL DSN not configured')
class V2Wire(unittest.TestCase):
    setUpClass=classmethod(pg.PostgreSQLCommands.setUpClass.__func__)
    request=foundation.HttpTests.request
    stop_server=foundation.HttpTests.stop_server

    def setUp(self):
        pg.PostgreSQLCommands.setUp(self)
        foundation.HttpTests.setUp(self)
        env=patch.dict(os.environ,{'KLEAL_MONETIZATION_MODE':'enforce'})
        env.start();self.addCleanup(env.stop)

    def tearDown(self):
        self.doCleanups()
        pg.PostgreSQLCommands.tearDown(self)

    def test_status_notice_keeper_wire_identity_and_validation(self):
        self.assertEqual(self.request(path='/v2/status',token=None)[0],401)
        status,before,headers=self.request(path='/v2/status')
        self.assertEqual(status,200);self.assertEqual(before['version'],2)
        self.assertFalse(before['previewNotice']);self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(self.request('POST','/v2/notice',json.dumps({'commandId':'early'}))[0],409)
        with ms.transaction() as t:
            one=t.publish('id_alice',{'title':'one'});two=t.publish('id_alice',{'title':'two'})
            foreign=t.publish('id_bob',{'title':'private'})
        self.assertTrue(self.request(path='/v2/status')[1]['previewNotice'])
        self.assertEqual(self.request('POST','/v2/keep-search',json.dumps({'commandId':'foreign','searchId':foreign}))[0],403)
        self.assertEqual(self.request('POST','/v2/keep-search',json.dumps({'commandId':'spoof','searchId':one,'owner_id':'id_bob'}))[0],400)
        with ms.transaction() as t: t.pause('id_alice',two)
        self.assertEqual(self.request('POST','/v2/keep-search',json.dumps({'commandId':'paused','searchId':two}))[0],409)
        kept=self.request('POST','/v2/keep-search',json.dumps({'commandId':'keep','searchId':one}))
        self.assertEqual(kept[0],200);self.assertEqual(kept[1]['keepSearchId'],one)
        for _ in range(2):
            notice=self.request('POST','/v2/notice',json.dumps({'commandId':'notice'}))
            self.assertEqual(notice[0],200);self.assertFalse(notice[1]['previewNotice'])
        self.assertEqual(self.request('POST','/preview','{"consent":true}')[0],409)
        self.assertFalse(self.request(path='/status')[1]['enforcementEnabled'])

    def test_v2_unknown_is_retryable_and_recovery_preserves_exact_server_grant(self):
        with ms.transaction() as t: t.publish('id_alice',{'title':'Synthetic search'})
        before=self.request(path='/v2/status')[1]
        with patch.object(ms.db,'_connect',side_effect=OSError('synthetic database outage')):
            code,body,headers=self.request(path='/v2/status')
        self.assertEqual(code,503,body)
        self.assertTrue(body['retryable'],body)
        self.assertNotIn('plan',body)
        self.assertNotIn('state',body)
        self.assertEqual(headers['Cache-Control'],'no-store')
        after=self.request(path='/v2/status')[1]
        self.assertEqual(after['state'],'preview')
        self.assertEqual((after['previewStartedAt'],after['expiresAt']),(before['previewStartedAt'],before['expiresAt']))

    def test_server_clock_ignores_client_clock_timezone_and_duration(self):
        with ms.transaction() as t: t.publish('id_alice',{'title':'Synthetic search'})
        before=self.request(path='/v2/status')[1]
        for query in ('?serverTime=0&expiresAt=9999999999&tz=Pacific/Honolulu',
                      '?serverTime=9999999999&duration=1&tz=Europe/Moscow'):
            with self.subTest(query=query):
                code,body,_=self.request(path='/v2/status'+query)
                self.assertEqual(code,200)
                self.assertEqual((body['previewStartedAt'],body['expiresAt']),(before['previewStartedAt'],before['expiresAt']))
                self.assertEqual(body['expiresAt']-body['previewStartedAt'],1209600)
                self.assertGreaterEqual(body['serverTime'],before['serverTime'])

    def test_actual_http_free_preview_manual_expiry_accepted_by_production_mobile_validator(self):
        statuses=[self.request(path='/v2/status')[1]]
        with ms.transaction() as tx:tx.publish('id_alice',{'title':'Synthetic preview'})
        statuses.append(self.request(path='/v2/status')[1])
        with ms.transaction() as tx:
            tx.conn.execute('update monetization_accounts set preview_start=%s,preview_end=%s where owner_id=%s',
                            (tx.now-1209601,tx.now-1,'id_alice'))
            tx.conn.execute("insert into users(id,name_key,name,row) values('id_alice','synthetic','Synthetic','{}') on conflict do nothing")
            admin.command(tx.conn,action='grant',owner='id_alice',operator='synthetic-test',reason='wire contract',
                          key='wire-manual',expires=tx.now+3600,apply=True)
        statuses.append(self.request(path='/v2/status')[1])
        with ms.transaction() as tx:tx.conn.execute("update monetization_manual_grants set expires=%s,created=%s where owner_id='id_alice'",(tx.now-1,tx.now-3600))
        statuses.append(self.request(path='/v2/status')[1])
        self.assertEqual([value['plan'] for value in statuses],['free','plus','plus','free'])
        node=shutil.which('node') or '/Users/ivan/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
        self.assertTrue(Path(node).is_file(),'Node is required for the real mobile contract check; never silently skip')
        checker=ROOT.parent/'kleal-app/tools/membership_wire_check.js'
        result=subprocess.run([node,str(checker)],input=json.dumps(statuses),text=True,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        mutated=copy.deepcopy(statuses);mutated[0]['permissions'].pop('basicFilters')
        rejection=subprocess.run([node,str(checker)],input=json.dumps(mutated),text=True,capture_output=True,timeout=30)
        self.assertNotEqual(rejection.returncode,0,'mandatory basicFilters mutation must fail the production validator')


@unittest.skipUnless(DSN,'BLOCKED: isolated PostgreSQL DSN not configured')
class LegacyAdapters(unittest.TestCase):
    setUpClass = classmethod(pg.PostgreSQLCommands.setUpClass.__func__)
    tearDownDB = pg.PostgreSQLCommands.tearDown
    free = pg.PostgreSQLCommands.free

    def setUp(self):
        pg.PostgreSQLCommands.setUp(self)
        self.tmp = tempfile.TemporaryDirectory(prefix='kleal_monetization_fixture_')
        self.env = patch.dict(os.environ,{'KLEAL_DB':'json','KLEAL_STORE':self.tmp.name+'/store.json',
                                         'KLEAL_MONETIZATION_MODE':'off','KLEAL_GEOCODE_ENABLED':'0'})
        self.env.start()
        sys.path.insert(0,str(ROOT/'services'/'matching'))
        spec=importlib.util.spec_from_file_location('monetization_matching_fixture',ROOT/'services'/'matching'/'app.py')
        self.app=importlib.util.module_from_spec(spec); spec.loader.exec_module(self.app)
        self.app.VOICE_DIR=self.app.VIDEO_DIR=self.tmp.name
        # These existing quota fixtures now model uploaded local media, not dangling
        # URLs. Production reference writers verify existence under the cleanup lock.
        (Path(self.tmp.name)/('a'*32+'.m4a')).write_bytes(b'synthetic voice')
        (Path(self.tmp.name)/('b'*32+'.mp4')).write_bytes(b'synthetic video')
        self.real_candidates = self.app.load_candidates
        users=[{'id':x,'name':'Same name','age':25,'verified':True,'interests':['coffee'],'open':True} for x in ('a','b','c','d')]
        self.app.load_candidates=lambda:users
        self.app._load_pool_rows=lambda:users
        self.app._people_index(force=True)
        self.real_match = self.app.match_candidates
        self.real_policy = self.app._policy_ok_now
        self.app._prepare_map_intent=lambda owner,intent,owner_id='':copy.deepcopy(intent)
        self.app._policy_ok_now=lambda *a,**kw:(True,'')
        self.app.match_candidates=lambda *a,**kw:[]
        self.app.send_json=lambda handler,status,value: setattr(handler,'result',(status,value))
        os.environ['KLEAL_MONETIZATION_MODE']='enforce'

    def tearDown(self):
        self.env.stop(); self.tmp.cleanup(); self.tearDownDB()

    def save(self,owner='a',iid=None,launched=True,key='save'):
        return self.app.save_intent('Same name',{'topics':['coffee']},'Coffee',iid,launched,owner_id=owner,idem=key)

    def test_draft_does_not_start_preview_publish_does(self):
        r=self.save(launched=False)
        self.assertTrue(r['ok'],r)
        self.assertIsNone(ms.status('a')['previewStartedAt'])
        r=self.save(iid=r['id'],key='launch')
        self.assertTrue(r['ok'],r)
        self.assertEqual(ms.status('a')['state'],'preview')

    def test_nonmeaningful_reads_and_draft_leave_eligible_account_without_grant(self):
        self.assertTrue(self.save(launched=False)['ok'])
        self.app.monetization_commands.refresh()
        for view in ('offline','online'):
            self.assertEqual(self.app.map_feed_payload(view,self_id='a')['items'],[])
        self.assertEqual(self.app.explore_plans(self_id='a'),[])
        state=self.app.monetization_commands.chat_states('a',['b'])
        self.assertEqual(state['b']['state'],'new')
        status=ms.status('a')
        self.assertTrue(status['previewEligible'])
        self.assertIsNone(status['previewStartedAt'])
        self.assertEqual(status['usage'],{'activeSearches':0,'initiatedChats':0})
        with ms.transaction() as t:
            self.assertEqual(t.conn.execute("select count(*) from monetization_audit where event='preview_meaningful_use'").fetchone()[0],0)

    def test_registration_and_synthetic_kyc_observation_do_not_start_preview(self):
        import age_verification as age
        import kleal_auth
        onboarding=foundation.ONB
        accounts={'synthetic-registration':{'created':100}}
        # Исполняется register_profile; хранилища профиля/фото/account заменены,
        # чтобы не менять реальные данные и не обращаться к провайдеру KYC.
        with patch.object(onboarding,'_read_users',return_value=[]), \
             patch.object(onboarding,'_persist_users') as saved, \
             patch.object(onboarding,'_read_accounts',return_value=accounts), \
             patch.object(onboarding,'_write_accounts'), \
             patch.object(onboarding,'save_photo',return_value=None), \
             patch.object(onboarding,'read_photo',return_value=None):
            user=onboarding.register_profile({'name':'Synthetic User','age':25,'interests':{'leaves':['coffee']}},'synthetic-registration')
            saved.assert_called_once()
        owner=user['id']
        self.assertIsNone(ms.status(owner)['previewStartedAt'])
        with patch.dict(os.environ,{'KLEAL_AGE_GATE_ENABLED':'1','KLEAL_AGE_GATE_FROM':'1',
                                   'KLEAL_AGE_DB':self.tmp.name+'/registration-age.sqlite',
                                   'KLEAL_AGE_BINDING_SECRET':'synthetic-only-binding-secret-for-local-tests'}), \
             patch.object(kleal_auth,'_accounts',return_value=accounts):
            account=accounts['synthetic-registration']
            for status,admitted in [('pending',False),('declined',False),('approved',True)]:
                with self.subTest(kyc=status):
                    with age.database() as c:
                        c.execute('insert into verification(subject,status) values(?,?) on conflict(subject) do update set status=excluded.status',
                                  (age.subject('synthetic-registration',account),status))
                    # Только synthetic доказательство, не проверка live approval/provenance.
                    with patch.object(age.age_proof,'admitted',return_value=admitted), \
                         patch.object(age.age_proof,'local_policy',return_value={}):
                        self.assertEqual(age.state('synthetic-registration',account)['admitted'],admitted)
                    membership=ms.status(owner)
                    self.assertTrue(membership['previewEligible'])
                    self.assertIsNone(membership['previewStartedAt'])
                    self.assertEqual(membership['usage'],{'activeSearches':0,'initiatedChats':0})

    def test_one_to_one_acceptance_grants_once_but_decline_and_failed_accept_do_not(self):
        saved=self.save()
        sent=self.app.propose('a','b',{'topics':['coffee'],'id':saved['id']},'Synthetic invite','invite-b')
        self.assertTrue(sent['ok'],sent)
        self.assertIsNone(ms.status('b')['previewStartedAt'])
        self.assertFalse(self.app.respond(sent['id'],'accept','c','foreign')['ok'])
        self.assertIsNone(ms.status('c')['previewStartedAt'])
        accepted=self.app.respond(sent['id'],'accept','b','accepted')
        self.assertTrue(accepted['ok'],accepted)
        status=ms.status('b')
        self.assertEqual(status['state'],'preview')
        self.assertEqual(status['expiresAt']-status['previewStartedAt'],1209600)
        self.assertEqual(self.app.respond(sent['id'],'accept','b','accepted'),accepted)
        declined=self.app.propose('a','c',{'topics':['coffee'],'id':saved['id']},'Synthetic decline','invite-c')
        self.assertTrue(declined['ok'],declined)
        self.assertTrue(self.app.respond(declined['id'],'decline','c','decline')['ok'])
        self.assertIsNone(ms.status('c')['previewStartedAt'])
        with ms.transaction() as t:
            self.assertEqual(t.conn.execute("select count(*) from monetization_audit where owner_id='b' and event='preview_meaningful_use'").fetchone()[0],1)

    def test_group_chat_and_manual_coordination_do_not_take_initiative_slot(self):
        group=self.app.gi_create('a',{'topics':['coffee']},'Coffee',idem='group')
        gid=group['group']['gid']
        invitation=self.app.gi_invite(gid,'a','b',idem='invite')['invite']['id']
        self.assertTrue(self.app.gi_respond(invitation,'b',True,'join')['ok'])
        with ms.transaction() as t:
            t.conn.execute("update monetization_accounts set preview_start=%s,preview_end=%s where owner_id in ('a','b')",(t.now-1209601,t.now-1))
        for owner in ('a','b'):
            result=self.app.gi_post(gid,owner,'Synthetic logistics','group-post-'+owner)
            self.assertTrue(result['ok'],result)
            status=ms.status(owner)
            self.assertEqual(status['usage']['initiatedChats'],0)
            self.assertTrue(status['permissions']['manualCoordination'])
            self.assertTrue(status['permissions']['groupChat'])

    def test_group_and_search_share_alias_not_second_slot(self):
        self.free()
        r=self.save()
        self.assertTrue(r['ok'],r)
        g=self.app.gi_create('a',{'topics':['coffee'],'iid':r['id']},'Coffee',idem='group')
        self.assertTrue(g['ok'],g)
        self.assertEqual(ms.status('a')['usage']['activeSearches'],1)
        blocked=self.app.gi_create('a',{'topics':['padel']},'Padel',idem='another')
        self.assertEqual(blocked['error'],'search_quota')
        with ms.transaction() as t:
            self.assertEqual(len(t.documents()['_gintents']),1)

    def test_pending_approval_no_grant_actual_admission_grants(self):
        group=self.app.gi_create('a',{'topics':['coffee']},'Coffee',idem='g')
        self.assertTrue(group['ok'],group)
        gid=group['group']['gid']
        invite=self.app.gi_invite(gid,'a','b',idem='invite')
        self.assertTrue(invite['ok'],invite)
        with ms.transaction(projection=True) as t:
            doc=t.documents(); doc['_gintents'][0]['state']='planning'; t.save_documents(doc)
        accepted=self.app.gi_respond(invite['invite']['id'],'b',True,'accept')
        self.assertTrue(accepted.get('awaiting_approval'),accepted)
        self.assertIsNone(ms.status('b')['previewStartedAt'])
        approved=self.app.gi_approve(gid,'a','b',True,'approve')
        self.assertTrue(approved['ok'],approved)
        self.assertEqual(ms.status('b')['state'],'preview')
        self.assertEqual(ms.status('b')['usage']['activeSearches'],0,'участие в чужой группе не занимает собственный слот')

    def test_planning_states_recruit_with_approval_and_keep_own_search_quota(self):
        for lifecycle,peer in zip(('below_quorum','planning','planned'),('b','c','d')):
            with self.subTest(state=lifecycle):
                group=self.app.gi_create('a',{'topics':['coffee']},lifecycle,idem='group-'+peer)
                self.assertTrue(group['ok'],group);gid=group['group']['gid']
                with ms.transaction() as t:
                    doc=t.documents();next(g for g in doc['_gintents'] if g['id']==gid)['state']=lifecycle
                    t.save_documents(doc)
                    self.assertEqual(t.resource(t.resolve('group',gid))['state'],'active')
                invited=self.app.gi_invite(gid,'a',peer,idem='invite-'+peer)
                self.assertTrue(invited['ok'],invited)
                accepted=self.app.gi_respond(invited['invite']['id'],peer,True,'accept-'+peer)
                self.assertTrue(accepted.get('awaiting_approval'),accepted)
                self.assertIsNone(ms.status(peer)['previewStartedAt'])
                self.assertTrue(self.app.gi_approve(gid,'a',peer,True,'approve-'+peer)['ok'])
                self.assertEqual(ms.status(peer)['usage']['activeSearches'],0)
        self.assertEqual(ms.status('a')['usage']['activeSearches'],3)

    def test_old_pending_accepts_after_pause_but_new_invites_denied(self):
        group=self.app.gi_create('a',{'topics':['coffee']},'Coffee',idem='g')
        gid=group['group']['gid']
        invite=self.app.gi_invite(gid,'a','b',idem='invite')
        with ms.transaction(projection=True) as t:
            t.pause('a',t.resolve('group',gid))
        accepted=self.app.gi_respond(invite['invite']['id'],'b',True,'accept')
        self.assertTrue(accepted['ok'],accepted)
        denied=self.app.gi_invite(gid,'a','c',idem='new')
        self.assertEqual(denied['error'],'search_paused')

    def test_message_allows_response_and_explicit_end_releases_slot_once(self):
        self.free()
        with ms.transaction(projection=True) as t:
            t.save_documents({'_requests':[{'id':'r1','from':'a','to':'b','status':'accepted'},
                                            {'id':'r2','from':'a','to':'c','status':'accepted'}]})
        self.assertTrue(self.app.send_message('a','b','first',client_id='message-1')['ok'])
        self.assertTrue(self.app.send_message('b','a','reply',client_id='reply-1')['ok'])
        denied=self.app.send_message('a','c','second',client_id='message-2')
        self.assertEqual(denied['error'],'chat_quota')
        self.assertTrue(self.app.end_thread('a','b','end')['ok'])
        self.assertTrue(self.app.send_message('a','c','second',client_id='message-2')['ok'])
        self.assertEqual(self.app.send_message('a','b','new initiative',client_id='new-ab')['error'],'chat_quota')
        self.assertTrue(self.app.end_thread('a','c','end-c')['ok'])
        self.assertTrue(self.app.send_message('a','b','new initiative',client_id='new-ab')['ok'])
        self.assertTrue(self.app.end_thread('a','b','end')['ok'])
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],1)
        with ms.transaction() as t:
            human=[m['text'] for m in t.documents()['_messages'] if not m.get('sys')]
            self.assertEqual(human,['first','reply','second','new initiative'])

    def test_search_command_caller_and_retry(self):
        self.free()
        class Handler: _pid='a'
        h=Handler()
        body={'intent':{'topics':['coffee']},'owner_id':'b','commandId':'publish','profile':{}}
        self.app.monetization_commands.handle(h,'/api/agent/search-command',body)
        self.assertEqual(h.result[0],200)
        result=h.result[1]
        self.app.monetization_commands.handle(h,'/api/agent/search-command',body)
        # The HTTP response and persisted replay both cross JSON; tuples from ranking
        # become arrays on the wire. Compare that full contract, not Python container types.
        self.assertEqual(json.loads(json.dumps(result,default=str)),h.result[1])
        self.assertEqual(ms.status('a')['usage']['activeSearches'],1)
        self.assertEqual(ms.status('b')['usage']['activeSearches'],0)

    def test_empty_search_without_title_finishes_and_replays_fallback(self):
        class Handler: _pid='a'
        for suffix, title in (('missing', {}), ('null', {'title': None})):
            with self.subTest(title=suffix):
                h=Handler()
                body={'intent':{'topics':['coffee'],'mode':'hybrid',**title},
                      'commandId':'fallback-'+suffix}
                self.app.monetization_commands.handle(h,'/api/agent/search-command',body)
                self.assertEqual(h.result[0],200)
                result=copy.deepcopy(h.result[1])
                self.assertEqual(result['launchState'],'ready')
                self.assertEqual(result['candidates'],[])
                self.assertEqual(result['fallback']['room']['title'],'Live room: meet')
                self.assertFalse(result['fallback']['room']['approved'])
                self.app.monetization_commands.handle(h,'/api/agent/search-command',body)
                self.assertEqual(h.result[1],json.loads(json.dumps(result,default=str)))

    def test_terminal_history_never_binds_to_new_session(self):
        self.free()
        with ms.transaction(projection=True) as t:
            t.save_documents({'_requests':[{'id':'r','from':'a','to':'b','status':'accepted'}],
                              '_mplans':[{'id':'old_done_no_chat','host':'a','guest':'b','state':'done'}]})
        self.assertTrue(self.app.send_message('a','b','new',client_id='new')['ok'])
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],1)
        with ms.transaction() as t:
            self.assertIsNone(t.conn.execute('select 1 from monetization_plan_sessions where plan_id=%s',
                                            ('old_done_no_chat',)).fetchone())

    def test_resume_restores_canonical_payload_and_quota_swap_is_atomic(self):
        self.free()
        class Handler: _pid='a'
        h=Handler()
        intent={'topics':['coffee'],'title':'Original title','mode':'hybrid','radiusKm':7,'minAge':23,'maxAge':49,
                'requiredLanguages':['en'],'dateKey':'2030-10-09','time':'18:00','address':'Synthetic venue'}
        self.app.monetization_commands.handle(h,'/api/agent/search-command',{'intent':intent,'title':'Original title','commandId':'original'})
        rid=h.result[1]['searchId']
        with ms.transaction() as t:
            t.pause('a',rid)
        other=self.save(key='other')
        with ms.transaction() as t:
            blocker=t.resolve('intent',other['id'])
            saved=copy.deepcopy(t.resource(rid)['payload'])
        body={'operation':'resume','searchId':rid,'commandId':'resume'}
        with self.assertRaises(ms.CommandError) as denied:
            self.app.monetization_commands.handle(h,'/api/agent/search-command',body)
        self.assertEqual(denied.exception.code,'search_quota')
        with ms.transaction() as t:
            self.assertEqual(t.resource(rid)['state'],'paused')
            self.assertEqual(t.resource(rid)['payload'],saved)
            self.assertEqual(t.resource(blocker)['state'],'active')
        swapped=dict(body,swapSearchId=blocker)
        self.app.monetization_commands.handle(h,'/api/agent/search-command',swapped)
        result=copy.deepcopy(h.result[1]);self.assertEqual(result['launchState'],'ready')
        self.app.monetization_commands.handle(h,'/api/agent/search-command',swapped)
        self.assertEqual(h.result[1],json.loads(json.dumps(result,default=str)))
        with ms.transaction() as t:
            self.assertEqual(t.resource(rid)['payload'],saved)
            self.assertEqual(t.resource(blocker)['state'],'paused')
            row=next(r for r in t.documents()['_intents'] if r['searchId']==rid)
            self.assertEqual(row['title'],'Original title')
            for key,value in intent.items(): self.assertEqual(row['intent'][key],value,key)
        with self.assertRaises(ms.CommandError) as conflict:
            self.app.monetization_commands.handle(h,'/api/agent/search-command',dict(swapped,title='different payload'))
        self.assertEqual(conflict.exception.code,'idempotency_payload_conflict')
        h._pid='b'
        with self.assertRaises(ms.CommandError) as foreign:
            self.app.monetization_commands.handle(h,'/api/agent/search-command',dict(body,commandId='foreign'))
        self.assertEqual(foreign.exception.code,'not_your_search')
        h._pid='a'
        for bad in ({'operation':'resume'},dict(body,searchId=['wrong']),dict(body,commandId=17)):
            with self.assertRaises(ms.CommandError) as invalid:
                self.app.monetization_commands.handle(h,'/api/agent/search-command',bad)
            self.assertEqual(invalid.exception.status,400)

    def test_ready_replay_cannot_bypass_pause_or_expiry(self):
        class Handler: _pid='a'
        h=Handler()
        self.app.match_candidates=lambda *a,**kw:[{'id':'b'}]
        body={'intent':{'topics':['coffee']},'commandId':'ready-replay'}
        self.app.monetization_commands.handle(h,'/api/agent/search-command',body)
        self.assertEqual(h.result[1]['candidates'],[{'id':'b'}])
        rid=h.result[1]['searchId']
        with ms.transaction() as t: t.pause('a',rid)
        self.app.monetization_commands.handle(h,'/api/agent/search-command',body)
        self.assertEqual(h.result[1]['launchState'],'paused')
        self.assertEqual(h.result[1]['candidates'],[])
        with ms.transaction() as t:
            self.assertEqual(t.resource(rid)['state'],'paused')
            t.publish('a',{'title':'explicit resume'},rid)
            keeper=t.publish('a',{'title':'keep other search'})
            t.conn.execute('update monetization_accounts set keep_search=%s,preview_start=%s,preview_end=%s where owner_id=%s',
                           (keeper,t.now-1209601,t.now-1,'a'))
        self.app.monetization_commands.handle(h,'/api/agent/search-command',body)
        self.assertEqual(h.result[1]['launchState'],'paused')
        self.assertEqual(h.result[1]['candidates'],[])

    def test_real_ranking_contract_and_safety_are_tier_independent(self):
        self.app.match_candidates=self.real_match
        self.app._policy_ok_now=self.real_policy
        users=[dict(id=x,name=x,age=25,verified=True,interests=['coffee'],open=True,
                    langs=['en'],vibe='chill',formats=['online'],km=1) for x in ('a','b','c','d')]
        users += [dict(users[1],id='minor',name='minor',age=16),
                  dict(users[1],id='unverified',name='unverified',verified=False),
                  dict(users[1],id='paused',name='paused',paused=True)]
        self.app.load_candidates=lambda:users
        self.app._load_pool_rows=lambda:users
        self.app._people_index(force=True)
        class Handler: _pid='a'
        h=Handler()
        body={'intent':{'topics':['coffee'],'mode':'online','verifiedOnly':True},
              'commandId':'real-ranking','lang':'es','limit':1,'ctx':{'now':time.time()},'profile':{}}
        answers=[]
        for mode,tier in [('off','free'),('shadow','free'),('enforce','free'),('enforce','preview')]:
            os.environ['KLEAL_MONETIZATION_MODE']=mode
            if mode=='enforce':
                with ms.transaction() as t:
                    t.conn.execute('update monetization_accounts set eligible=%s,preview_start=null,preview_end=null where owner_id=%s',(tier=='preview','a'))
            data=dict(body,commandId=mode+tier)
            if answers and mode=='enforce' and tier=='preview':
                data['searchId']=answers[-1]['searchId']
            self.app.monetization_commands.handle(h,'/api/agent/search-command',data)
            result=h.result[1]
            self.assertTrue(result['candidates'],result)
            self.assertTrue(result['has_more'],result)
            self.assertEqual(result['shown'],1)
            self.assertIn('interestLabels',result)
            self.assertIn('retrieval',result)
            self.assertIn('expansion',result)
            self.assertNotIn(result['candidates'][0]['name'],('minor','unverified','paused'))
            answers.append(copy.deepcopy(result))
        for r in answers[1:]:
            self.assertEqual(r['candidates'],answers[0]['candidates'])
            self.assertEqual(r['retrieval'],answers[0]['retrieval'])
        self.assertFalse(self.real_policy('a','minor')[0])
        self.assertFalse(self.real_policy('a','paused')[0])
        # Pilot-disabled decisions retain the existing people fallback, including
        # its explicit metadata, with exactly the same real ranker.
        body=dict(body,intent=dict(body['intent'],decisionType='intent_to_event'),commandId='pilot',searchId=answers[-1]['searchId'])
        self.app.monetization_commands.handle(h,'/api/agent/search-command',body)
        self.assertFalse(h.result[1]['pilot']['enabled'])
        self.assertTrue(h.result[1]['candidates'])

    def test_buddy_delegates_to_canonical_matching_with_real_ranker(self):
        self.app.match_candidates=self.real_match
        users=[dict(id=x,name=x,age=25,verified=True,interests=['coffee'],open=True,
                    langs=['en'],vibe='chill',formats=['online'],km=1) for x in ('a','b','c')]
        self.app.load_candidates=lambda:users
        self.app._load_pool_rows=lambda:users
        self.app._people_index(force=True)
        spec=importlib.util.spec_from_file_location('phase2_buddy',ROOT/'services'/'buddy'/'app.py')
        buddy=importlib.util.module_from_spec(spec);spec.loader.exec_module(buddy)
        def post(url,path,body,**kw):
            self.assertEqual(kw['auth'],'synthetic-bearer')
            class Handler: _pid='a'
            h=Handler();self.app.monetization_commands.handle(h,path,body)
            return h.result[1]
        with patch.object(buddy,'_post',side_effect=post):
            result,cards=buddy.run_match({'topics':['coffee'],'mode':'online'},{},'a','en',owner='a',auth='synthetic-bearer')
        self.assertTrue(result['candidates'],result)
        self.assertTrue(cards)
        self.assertIn('_searchId',result['intent'])
        self.assertEqual(ms.status('a')['usage']['activeSearches'],1)
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],0)

    def test_real_search_route_contracts_match_off_free_and_preview(self):
        self.app.match_candidates=self.real_match
        self.app._policy_ok_now=self.real_policy
        users=[dict(id=x,name=x,age=25,verified=True,interests=['coffee'],open=True,
                    langs=['en'],vibe='chill',formats=['online'],km=1) for x in ('a','b','c','d')]
        self.app.load_candidates=lambda:users;self.app._load_pool_rows=lambda:users
        self.app._people_index(force=True)
        self.app.GROUPS_ENABLED=True;self.app.PILOT_DECISION_TYPES['group_formation']=True
        class Handler: _pid='a'
        h=Handler();now=time.time();rid=None
        for route,extra,required in (
            ('confirm',{'constraints':[],'confirmed_ids':[]},('confirmed','expansion')),
            ('expand',{'axis':'radius'},('axis','changed_keys','ladder_step','explanation')),
            ('plan',{'query':'Synthetic coffee','override':{'mode':'online'}},('retrieval','expansion')),
            ('match',{'intent':{'topics':['coffee'],'mode':'online','groupSize':3}},('group','retrieval','expansion')),
        ):
            with self.subTest(route=route):
                path='/api/agent/'+route
                body=dict({'intent':{'topics':['coffee'],'mode':'online','radiusKm':10},
                           'ctx':{'now':now},'profile':{}},**extra)
                # Only the external language parser is replaced. The compiler,
                # confirmation/expansion, ranker, policy and group builder are real.
                with patch.object(self.app,'parse_intent',return_value={'topics':['coffee'],'mode':'online'}):
                    os.environ['KLEAL_MONETIZATION_MODE']='off'
                    ctx=dict(body['ctx'],self_id='a',self='a')
                    prepared=self.app.prepare_search(path,body,ctx)
                    legacy=self.app.render_search(path,body,prepared,ctx)
                    self.assertTrue(legacy['candidates'],legacy)
                    for tier in ('free','preview'):
                        os.environ['KLEAL_MONETIZATION_MODE']='enforce'
                        with ms.transaction() as t:
                            t.conn.execute('update monetization_accounts set eligible=%s,preview_start=null,preview_end=null where owner_id=%s',(tier=='preview','a'))
                        data=dict(body,commandId=route+tier)
                        if rid: data['searchId']=rid
                        self.app.monetization_commands.handle(h,path,data)
                        actual=h.result[1];rid=actual['searchId']
                        self.assertEqual(actual['launchState'],'ready',actual)
                        self.assertEqual(actual['candidates'],legacy['candidates'])
                        for field in required: self.assertEqual(actual[field],legacy[field],field)
                        if route=='expand':
                            self.assertEqual(actual['intent']['radiusKm'],20)
                            self.assertEqual(actual['changed_keys'],['radiusKm'])

    def test_pause_keeps_payload_and_durable_launch_recovers(self):
        class Handler: _pid='a'
        h=Handler()
        body={'intent':{'topics':['coffee'],'title':'Coffee'},'commandId':'pending','profile':{}}
        with patch.object(self.app,'match_candidates',side_effect=RuntimeError('ranking unavailable')):
            self.app.monetization_commands.handle(h,'/api/agent/search-command',body)
        self.assertEqual(h.result[1]['launchState'],'pending')
        rid=h.result[1]['searchId']
        self.assertEqual(self.app.monetization_commands.drain_launches(),1)
        self.app.monetization_commands.handle(h,'/api/agent/search-command',body)
        self.assertEqual(h.result[1]['launchState'],'ready')
        intent=h.result[1]['intent']
        self.app.monetization_commands.handle(h,'/api/agent/search-command',{
            'intent':{'_searchId':rid},'searchId':rid,'operation':'pause','commandId':'pause'})
        self.assertEqual(h.result[1]['intent'],intent)
        with ms.transaction() as t:
            self.assertEqual(t.documents()['_intents'][0]['title'],'Coffee')
            self.assertEqual(t.conn.execute('select count(*) from outbox where sent_at is null').fetchone()[0],0)

    def test_shadow_keeps_legacy_write_without_grant_and_audits(self):
        os.environ['KLEAL_MONETIZATION_MODE']='shadow'
        result=self.save()
        self.assertTrue(result['ok'],result)
        self.assertEqual(len(self.app.SESSION['_intents']),1)
        with ms.transaction() as t:
            self.assertEqual(t.conn.execute('select count(*) from monetization_resources').fetchone()[0],0)
            self.assertEqual(t.conn.execute("select count(*) from monetization_audit where event='shadow_decision'").fetchone()[0],1)
        self.assertIsNone(ms.status('a')['previewStartedAt'])

    def test_database_failure_returns_retryable_error_without_json_fallback(self):
        before=copy.deepcopy(self.app.SESSION)
        with patch.object(ms.db,'_connect',side_effect=OSError('synthetic database outage')):
            result=self.save()
        self.assertEqual(result['httpStatus'],503,result)
        self.assertTrue(result['retryable'])
        self.assertEqual(self.app.SESSION,before)
        self.assertIsNone(ms.status('a')['previewStartedAt'])
        retried=self.save()
        self.assertTrue(retried['ok'],retried)
        self.assertEqual(self.save(),retried)
        with ms.transaction() as t:
            self.assertEqual(t.conn.execute("select count(*) from monetization_resources where owner_id='a'").fetchone()[0],1)
            self.assertEqual(t.conn.execute("select count(*) from monetization_audit where owner_id='a' and event='preview_meaningful_use'").fetchone()[0],1)

    def test_role_recipient_quota_rolls_back_owner_and_roster(self):
        group=self.app.gi_create('a',{'topics':['coffee']},'Coffee',idem='g')
        gid=group['group']['gid']
        invite=self.app.gi_invite(gid,'a','b',idem='invite')
        self.assertTrue(self.app.gi_respond(invite['invite']['id'],'b',True,'join')['ok'])
        self.free('b')
        with ms.transaction() as t:
            t.conn.execute("update monetization_accounts set preview_start=null,preview_end=null where owner_id='b'")
        other=self.save(owner='b',key='other')
        self.assertTrue(other['ok'],other)
        self.assertTrue(self.app.gi_role_offer(gid,'a','b','offer')['ok'])
        denied=self.app.gi_role_respond(gid,'b',True,'accept-role')
        self.assertEqual(denied['error'],'organizer_search_quota',denied)
        self.assertNotIn('blockerIds',denied)
        with ms.transaction() as t:
            row=t.documents()['_gintents'][0]
            self.assertEqual(row['owner'],'a')
            self.assertEqual(len(row['members']),2)
            t.pause('b',t.resolve('intent',other['id']))
        result=self.app.gi_role_respond(gid,'b',True,'accept-role')
        self.assertTrue(result['ok'],result)
        with ms.transaction() as t:
            self.assertEqual(t.documents()['_gintents'][0]['owner'],'b')

    def test_role_quota_decline_returns_choice_to_owner_without_slot_writes(self):
        group=self.app.gi_create('a',{'topics':['coffee']},'Coffee',idem='g')
        gid=group['group']['gid']
        for member in ('b','c'):
            invite=self.app.gi_invite(gid,'a',member,idem='invite-'+member)
            self.assertTrue(self.app.gi_respond(invite['invite']['id'],member,True,'join-'+member)['ok'])
        with ms.transaction() as t:
            t.conn.execute("update monetization_accounts set eligible=false,preview_start=null,preview_end=null where owner_id='b'")
        own=self.save(owner='b',key='own-search')
        self.assertTrue(self.app.gi_role_offer(gid,'a','b','offer')['ok'])
        denied=self.app.gi_role_respond(gid,'b',True,'take-role')
        self.assertEqual(denied['error'],'organizer_search_quota')
        self.assertNotIn('blockerIds',denied)
        # A quota refusal does not grant the recipient the owner's power to choose.
        self.assertEqual(self.app.gi_role_offer(gid,'b','c','illegal-offer')['error'],'NOT_ORGANIZER')
        self.assertEqual(self.app.gi_takeover_back(gid,'b',False,'illegal-back')['error'],'NOT_ORGANIZER')
        with ms.transaction() as t:
            resources=t.conn.execute('select id,owner_id,state from monetization_resources order by id').fetchall()
            before=t.documents()['_gintents'][0]
            self.assertEqual(before['owner'],'a')
            self.assertEqual(before['role_offer']['state'],'open')
        declined=self.app.gi_role_respond(gid,'b',False,'decline-role')
        self.assertTrue(declined['ok'],declined)
        public=self.app._humanize(declined)['group']
        self.assertEqual(public['owner_id'],'a')
        self.assertEqual(public['role_offer']['to_id'],'b')
        self.assertEqual(public['role_offer']['declined_ids'],['b'])
        self.assertFalse(public['i_am_owner'])
        self.assertFalse(public['can_hand_over'])
        with ms.transaction() as t:
            after=t.documents()['_gintents'][0]
            self.assertEqual(after['owner'],'a')
            self.assertEqual(after['members'],before['members'])
            self.assertEqual(after['state'],before['state'])
            self.assertEqual(resources,t.conn.execute('select id,owner_id,state from monetization_resources order by id').fetchall())
            self.assertEqual(t.resource(t.resolve('intent',own['id']))['state'],'active')
        # Same display names are harmless: the original owner selects a different ID.
        offered=self.app.gi_role_offer(gid,'a','c','offer-other')
        self.assertTrue(offered['ok'],offered)
        self.assertEqual(self.app._humanize(offered)['group']['role_offer']['to_id'],'c')
        accepted=self.app.gi_role_respond(gid,'c',True,'other-takes')
        self.assertTrue(accepted['ok'],accepted)
        with ms.transaction() as t:
            final=t.documents()['_gintents'][0]
            self.assertEqual(final['owner'],'c')
            self.assertEqual(final['members'],before['members'])
            self.assertEqual(t.resource(t.resolve('intent',own['id']))['state'],'active')

    def test_auto_vote_and_safety_exit_never_assign_over_quota_owner(self):
        group=self.app.gi_create('a',{'topics':['coffee']},'Coffee',idem='g')
        gid=group['group']['gid']
        invite=self.app.gi_invite(gid,'a','b',idem='invite')
        self.app.gi_respond(invite['invite']['id'],'b',True,'join')
        with ms.transaction() as t:
            t.conn.execute("update monetization_accounts set eligible=false,preview_start=null,preview_end=null where owner_id='b'")
        self.save(owner='b',key='b-search')
        with ms.transaction() as t:
            doc=t.documents();g=doc['_gintents'][0]
            g['takeover']={'state':'open','by':'b','closes':t.now-1,'votes':{'c':True}}
            t.save_documents(doc)
        self.app._gi_roles_due()
        with ms.transaction() as t:
            g=t.documents()['_gintents'][0]
            self.assertEqual(g['owner'],'a')
            self.assertEqual(g['takeover']['why'],'organizer_search_quota')
        # The complaint and safety exit remain available even though the automatic
        # successor cannot currently take over recruiting.
        result=self.app.gi_report(gid,'a','rule_violation',text='Synthetic QA report',idem='report')
        self.assertTrue(result['ok'],result)
        with ms.transaction() as t:
            doc=t.documents();g=doc['_gintents'][0]
            self.assertEqual(g['owner'],'')
            self.assertTrue(g['role_recovery'])
            self.assertEqual(t.resource(t.resolve('group',gid))['state'],'paused')
            self.assertTrue(doc['_reports'])
            self.assertEqual(next(m for m in g['members'] if m['name']=='a')['state'],'left')
        recovered=self.app.gi_takeover(gid,'b','recovery')
        self.assertTrue(recovered['ok'],recovered)
        with ms.transaction() as t:
            self.assertEqual(t.documents()['_gintents'][0]['owner'],'b')
            self.assertEqual(t.resource(t.resolve('group',gid))['state'],'paused')
        self.assertEqual(ms.status('b')['usage']['activeSearches'],1)

    def test_exit_selects_next_eligible_not_overquota_oldest(self):
        group=self.app.gi_create('a',{'topics':['coffee']},'Coffee',idem='g')
        gid=group['group']['gid']
        for who in ('b','c'):
            invite=self.app.gi_invite(gid,'a',who,idem='invite-'+who)
            self.app.gi_respond(invite['invite']['id'],who,True,'join-'+who)
        with ms.transaction() as t:
            t.conn.execute("update monetization_accounts set eligible=false,preview_start=null,preview_end=null where owner_id='b'")
        self.save(owner='b',key='b-search')
        left=self.app.gi_leave(gid,'a','leave')
        self.assertTrue(left['ok'],left)
        with ms.transaction() as t: self.assertEqual(t.documents()['_gintents'][0]['owner'],'c')

    def test_account_purge_exact_projection_and_durable_postcommit_files(self):
        self.free()
        self.save()
        voice=Path(self.tmp.name)/'abcdef123456.m4a'
        evidence=Path(self.tmp.name)/'abcdef123457.png'
        voice.write_bytes(b'synthetic voice');evidence.write_bytes(b'synthetic evidence')
        self.app.VOICE_DIR=self.tmp.name;self.app.EVIDENCE_DIR=self.tmp.name;self.app.VIDEO_DIR=self.tmp.name
        with ms.transaction(projection=True) as t:
            t.message('b','a')
            doc=t.documents();doc.update(a={'feedback':{'private':True}},_messages=[{
                'id':'m','from':'b','to':'a','voice':{'url':'/api/speech/voice/'+voice.name}}],
                _evidence={'e':{'by':'a','file':evidence.name}})
            t.save_documents(doc)
        # Real onboarding order: durable barrier commits BEFORE matching purge.
        with ms.connection() as c: admin.begin_delete(c,'a')
        with patch.object(ms.Transaction,'save_documents',side_effect=RuntimeError('rollback deletion')):
            failed=self.app.purge_person('a')
        self.assertFalse(failed['ok']);self.assertTrue(voice.exists());self.assertTrue(evidence.exists())
        with ms.transaction() as t:
            self.assertIn('a',t.documents())
            self.assertEqual(t.conn.execute("select count(*) from outbox where topic='monetization.media.cleanup'").fetchone()[0],0)
        result=self.app.purge_person('a')
        self.assertTrue(result['ok'],result)
        self.assertTrue(voice.exists()) # No filesystem deletion before canonical commit.
        with ms.transaction() as t:
            self.assertNotIn('a',t.documents())
            for table in ('monetization_accounts','monetization_commands','monetization_resources','monetization_audit'):
                self.assertEqual(t.conn.execute('select count(*) from '+table+' where owner_id=%s',('a',)).fetchone()[0],0)
            self.assertEqual(t.conn.execute('select count(*) from monetization_sessions').fetchone()[0],0)
        self.assertEqual(ms.status('b')['usage']['initiatedChats'],0)
        with patch.object(self.app.monetization_commands.os,'remove',side_effect=OSError('synthetic retry')):
            self.assertEqual(self.app.monetization_commands.drain_cleanup(),0)
        self.assertTrue(voice.exists());self.assertTrue(evidence.exists())
        with ms.transaction() as t:
            self.assertEqual(t.conn.execute("select count(*) from outbox where topic='monetization.media.cleanup' and attempts=1 and sent_at is null").fetchone()[0],2)
            t.conn.execute("update outbox set next_try=now() where topic='monetization.media.cleanup'")
        self.assertEqual(self.app.monetization_commands.drain_cleanup(),2)
        self.assertFalse(voice.exists());self.assertFalse(evidence.exists())
        self.assertTrue(self.app.purge_person('a')['ok'])
        self.assertEqual(self.app.monetization_commands.drain_cleanup(),0)

    def test_deleted_identity_does_not_poison_other_canonical_writers(self):
        group=self.app.gi_create('a',{'topics':['coffee']},'Coffee',idem='g')
        gid=group['group']['gid']
        invite=self.app.gi_invite(gid,'a','b',idem='invite')
        self.app.gi_respond(invite['invite']['id'],'b',True,'join')
        with ms.transaction() as t:
            doc=t.documents();doc['_reports']=[{'id':'foreign','by':'c','about':'a'}]
            doc['a']={'private':'deleted'};t.save_documents(doc)
        self.assertTrue(self.app.purge_person('a')['ok'])
        users=[u for u in self.app.load_candidates() if u['id']!='a']
        self.app.load_candidates=lambda:users;self.app._load_pool_rows=lambda:users;self.app._people_index(force=True)
        self.assertTrue(self.save(owner='c',key='other-publish')['ok'])
        self.assertTrue(self.app.gi_post(gid,'b','hello after deletion')['ok'])
        with ms.transaction() as t:
            doc=t.documents();doc['_requests']=[{'id':'bc','from':'b','to':'c','status':'accepted'}];t.save_documents(doc)
        self.assertTrue(self.app.send_message('b','c','surviving chat',client_id='bc-msg')['ok'])
        with ms.transaction() as t:
            self.assertNotIn('a',t.documents());self.assertEqual(t.documents()['_reports'][0]['by'],'c')

    def test_onboarding_barrier_purge_transfers_shared_resource_and_recovers_full_successor(self):
        saved=self.save()
        linked=self.app.gi_create('a',{'topics':['coffee'],'iid':saved['id']},'Shared',idem='shared')['group']['gid']
        recovery=self.app.gi_create('a',{'topics':['coffee']},'Recovery',idem='recovery')['group']['gid']
        for gid,peer in ((linked,'b'),(recovery,'c')):
            sent=self.app.gi_invite(gid,'a',peer,idem='invite-'+peer)
            self.assertTrue(self.app.gi_respond(sent['invite']['id'],peer,True,'join-'+peer)['ok'])
        legacy=self.app.group_create('a','Legacy',['coffee'],idem='legacy')['group']['gid']
        self.assertTrue(self.app.group_join(legacy,'d','join-d')['ok'])
        with ms.transaction() as t:
            t.conn.execute("update monetization_accounts set eligible=false,preview_start=null,preview_end=null where owner_id='c'")
        self.assertTrue(self.save(owner='c',key='occupied-c')['ok'])
        with ms.transaction() as t:
            linked_id=t.resolve('group',linked)
            self.assertEqual(linked_id,t.resolve('intent',saved['id']))
        with ms.connection() as c: admin.begin_delete(c,'a')
        result=self.app.purge_person('a');self.assertTrue(result['ok'],result)
        with ms.transaction() as t:
            self.assertEqual((t.resource(linked_id)['owner_id'],t.resource(linked_id)['state']),('b','active'))
            self.assertIsNone(t.resolve('intent',saved['id']))
            self.assertEqual(t.resource(linked_id)['payload']['owner'],'b')
            recovered=t.resource(t.resolve('group',recovery))
            self.assertEqual((recovered['owner_id'],recovered['state']),('recovery:'+recovery,'paused'))
            old=t.resource(t.resolve('group',legacy))
            self.assertEqual((old['owner_id'],old['state']),('d','active'))
            self.assertEqual(t.conn.execute("select count(*) from monetization_accounts where owner_id='a'").fetchone()[0],0)
        users=[u for u in self.app.load_candidates() if u['id']!='a']
        self.app.load_candidates=lambda:users;self.app._load_pool_rows=lambda:users;self.app._people_index(force=True)
        self.assertTrue(self.app.purge_person('a')['ok'])
        self.assertTrue(self.save(owner='b',key='unrelated-write')['ok'])
        self.assertTrue(self.app.gi_takeover(recovery,'c','recover')['ok'])
        self.assertTrue(self.app.gi_post(linked,'b','survives after deletion')['ok'])
        self.assertEqual(self.save(owner='a',key='forbidden-after-delete')['error'],'account_deleting')

    def test_onboarding_barrier_erases_only_subject_operator_data_and_denies_concurrent_grant(self):
        with ms.connection() as c:
            for uid in ('a','b'):
                c.execute('insert into users(id,name_key,name,row) values(%s,%s,%s,%s)',
                          (uid,uid,'Same name',json.dumps({'id':uid})))
                admin.command(c,action='grant',owner=uid,expires=ms.Transaction(c).now+3600,
                              operator='private operator',reason='private reason',key='manual-'+uid,apply=True)
            foreign={table:c.execute('select to_jsonb(t) from '+table+' t order by to_jsonb(t)::text').fetchall()
                     for table in ('monetization_manual_grants','monetization_admin_audit','monetization_admin_commands')}
            foreign={table:[row for row in rows if (row[0].get('owner_id') or row[0].get('result',{}).get('status',{}).get('ownerId'))=='b']
                     for table,rows in foreign.items()}
        started=threading.Event()
        def late_grant():
            started.set()
            try:
                with ms.connection() as c:
                    admin.command(c,action='grant',owner='a',expires=ms.Transaction(c).now+3600,
                                  operator='op',reason='late',key='late-a',apply=True)
            except ms.CommandError as e: return e.code
            return 'unexpected success'
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            with ms.connection() as c:
                admin.begin_delete(c,'a')
                pending=pool.submit(late_grant);self.assertTrue(started.wait(2))
                self.assertFalse(pending.done())
            self.assertEqual(pending.result(timeout=5),'account_deleting')
        self.assertTrue(self.app.purge_person('a')['ok'])
        self.assertTrue(self.app.purge_person('a')['ok'])
        with ms.connection() as c:
            for table in foreign:
                self.assertEqual(c.execute('select to_jsonb(t) from '+table+' t order by to_jsonb(t)::text').fetchall(),foreign[table])
            self.assertEqual(c.execute('select owner_id from monetization_deletions').fetchall(),[('a',)])

    def test_delete_owner_never_assigns_an_also_deleting_successor(self):
        gid=self.app.gi_create('a',{'topics':['coffee']},'Group',idem='group')['group']['gid']
        for peer in ('b','c'):
            invite=self.app.gi_invite(gid,'a',peer,idem='invite-'+peer)
            self.assertTrue(self.app.gi_respond(invite['invite']['id'],peer,True,'join-'+peer)['ok'])
        with ms.connection() as c:
            admin.begin_delete(c,'b');admin.begin_delete(c,'a')
        result=self.app.purge_person('a');self.assertTrue(result['ok'],result)
        with ms.transaction() as t:
            self.assertEqual(t.documents()['_gintents'][0]['owner'],'c')
            self.assertEqual(t.resource(t.resolve('group',gid))['owner_id'],'c')
        self.assertTrue(self.app.purge_person('b')['ok'])

    def test_map_hybrid_single_resource_and_paused_on_both_surfaces(self):
        self.free()
        intent={'topics':['coffee'],'mode':'hybrid','lat':40.41,'lng':-3.70,'address':'Synthetic venue',
                'title':'Hybrid future','starts_at':time.time()+7*86400}
        saved=self.app.save_intent('Same name',intent,'Hybrid future',launched=True,owner_id='a',idem='hybrid')
        group=self.app.gi_create('a',dict(intent,iid=saved['id']),'Hybrid future',idem='hybrid-group')
        self.assertTrue(group['ok'],group)
        self.app.monetization_commands.refresh()
        for view in ('offline','online'):
            feed=self.app.map_feed_payload(view,self_id='b')
            self.assertEqual(len(feed['items']),1,feed)
            self.assertEqual(feed['items'][0]['searchId'],ms.status('a')['searches'][0]['id'])
        self.assertEqual(ms.status('a')['usage']['activeSearches'],1)
        with ms.transaction() as t: t.pause('a',t.resolve('intent',saved['id']))
        self.app.monetization_commands.refresh()
        for view in ('offline','online'):
            self.assertEqual(self.app.map_feed_payload(view,self_id='b')['items'],[])
        self.assertEqual(self.app.explore_plans(self_id='b'),[])

    def test_malicious_protected_references_cannot_create_new_obligations(self):
        saved=self.save()
        with ms.transaction() as t:
            rid=t.resolve('intent',saved['id']);t.pause('a',rid)
            t.protect('invite','existing','accept',{'migration':'synthetic'})
            doc=t.documents();doc['_requests']=[{'id':'existing','from':'a','to':'b','status':'pending','updated':t.now,'created':t.now}];t.save_documents(doc)
        self.assertFalse(self.app.respond('existing','accept','c','stolen')['ok'])
        self.assertEqual(self.app.gi_create('c',{'topics':['coffee'],'_searchId':rid},'Stolen','malicious')['error'],'not_your_search')
        self.assertEqual(self.app.gi_create('a',{'topics':['coffee'],'_searchId':rid},'Paused','paused-new')['error'],'search_paused')
        before=ms.status('c')
        self.assertIsNone(before['previewStartedAt']);self.assertEqual(before['usage']['activeSearches'],0)

    def test_plan_terminal_writers_preserve_chat_and_quota_after_replay(self):
        self.free()
        for callback in ('cancel','decline','leave','timeout','feedback_no','feedback_both','admin_ban'):
            with self.subTest(callback=callback):
                with ms.transaction(projection=True) as t:
                    t.conn.execute('delete from monetization_plan_sessions');t.conn.execute('delete from monetization_sessions')
                    t.conn.execute('delete from monetization_commands')
                    t.save_documents({'_requests':[{'id':'ab','from':'a','to':'b','status':'accepted'},
                                                   {'id':'ac','from':'a','to':'c','status':'accepted'}]})
                first=self.app.send_message('a','b','before plan',client_id='first')
                self.assertTrue(first['ok'],first)
                original=ms.status('a')['blockerIds']['chats'][0]
                with ms.transaction(projection=True) as t:
                    plan={'id':'p','host':'a','guest':'b','pair':self.app._pair_key('a','b'),'state':'proposed',
                          'starts_at':t.now+86400,'version':1,'responses':{'a':{'state':'confirmed','version':1}}}
                    if callback.startswith('feedback'): plan['state']='confirmed'
                    if callback=='leave': plan.update(round=3,final_by_host={'round':3,'by':'a','at':t.now})
                    if callback=='timeout': plan['round_ends_at']=t.now-1
                    doc=t.documents();doc['_mplans']=[plan];t.save_documents(doc)
                    t.link_plan('p','a','b')
                def terminal():
                    if callback=='cancel': return self.app.mp_cancel('p','a',idem='cancel')
                    if callback in ('decline','leave'): return self.app.mp_respond('p','b',callback,idem=callback)
                    if callback=='timeout': return self.app._mp_sweep()
                    if callback=='feedback_no': return self.app.mp_feedback('p','a',False,idem='fb')
                    if callback=='feedback_both':
                        self.app.mp_feedback('p','a',True,idem='fba')
                        return self.app.mp_feedback('p','b',True,idem='fbb')
                    if callback=='admin_ban': return self.app.admin_ban_sweep('a')
                result=terminal()
                if isinstance(result,dict): self.assertTrue(result.get('ok'),result)
                self.assertEqual(ms.status('a')['blockerIds']['chats'],[original])
                self.assertTrue(self.app.send_message('a','b','same conversation',client_id='continuation')['ok'])
                self.assertTrue(self.app.send_message('b','a','reply after plan',client_id='reply')['ok'])
                self.assertEqual(self.app.send_message('a','c','new initiative',client_id='blocked')['error'],'chat_quota')
                with ms.transaction() as t:
                    self.assertEqual(t.conn.execute('select initiator,state,closed,protected from monetization_sessions where id=%s',
                                                    (original,)).fetchone(),('a','active',None,False))
                    doc=t.documents()
                    self.assertIn(doc['_mplans'][0]['state'],('cancelled','done'))
                    self.assertEqual([m['text'] for m in doc['_messages'] if not m.get('sys')],
                                     ['before plan','same conversation','reply after plan'])
                terminal()
                self.assertEqual(ms.status('a')['blockerIds']['chats'],[original])
                self.assertTrue(self.app.end_thread('a','b','explicit-end')['ok'])
                self.assertEqual(ms.status('a')['usage']['initiatedChats'],0)
                self.assertTrue(self.app.send_message('a','b','new session',client_id='new-session')['ok'])
                reopened=ms.status('a')['blockerIds']['chats'][0]
                self.assertNotEqual(original,reopened)
                terminal()
                # Повторный sweep выполняет reconciliation без cached command result.
                self.app._mp_sweep()
                if callback.startswith('feedback'):
                    late=self.app.mp_feedback('p','a',True,rating=5,idem='late-feedback')
                    self.assertTrue(late['ok'],late)
                self.assertEqual(ms.status('a')['blockerIds']['chats'],[reopened])
                with ms.transaction() as t:
                    self.assertEqual(t.conn.execute('select session_id from monetization_plan_sessions where plan_id=%s',
                                                    ('p',)).fetchone()[0],original)
                    self.assertEqual(len([m for m in t.documents()['_messages'] if not m.get('sys')]),4)

    def test_elapsed_meeting_and_postplan_feedback_preserve_initiator(self):
        self.free()
        with ms.transaction() as t:
            t.save_documents({'_requests':[{'id':'ab','from':'a','to':'b','status':'accepted'},
                                           {'id':'ac','from':'a','to':'c','status':'accepted'}]})
        self.assertTrue(self.app.send_message('a','b','first',client_id='first')['ok'])
        original=ms.status('a')['blockerIds']['chats'][0]
        with ms.transaction() as t:
            doc=t.documents();doc['_mplans']=[{'id':'past','host':'a','guest':'b','pair':self.app._pair_key('a','b'),
                'state':'confirmed','starts_at':t.now-self.app.MP_KEEP_AFTER-1,'version':1}]
            t.save_documents(doc);t.link_plan('past','a','b')
        self.app.monetization_commands.refresh()
        self.app._mp_sweep()
        self.assertIsNone(self.app._mp_of('a','b'))
        self.assertEqual(ms.status('a')['blockerIds']['chats'],[original])
        self.assertTrue(self.app.mp_feedback('past','a',True,rating=5,idem='postplan')['ok'])
        self.assertTrue(self.app.send_message('a','b','after the meeting',client_id='continue')['ok'])
        self.assertEqual(ms.status('a')['blockerIds']['chats'],[original])
        self.assertEqual(self.app.send_message('a','c','new initiative',client_id='blocked')['error'],'chat_quota')
        self.assertTrue(self.app.end_thread('a','b','end')['ok'])
        self.assertTrue(self.app.send_message('a','c','new initiative',client_id='blocked')['ok'])
        # Прошедший план не освобождает чат, но и не даёт исключение новой сессии после end.
        self.assertEqual(self.app.send_message('a','b','reopen old meeting',client_id='reopen')['error'],'chat_quota')
        self.assertTrue(self.app.end_thread('a','c','end-c')['ok'])
        self.assertTrue(self.app.send_message('a','b','reopen old meeting',client_id='reopen')['ok'])
        reopened=ms.status('a')['blockerIds']['chats']
        self.assertEqual(len(reopened),1)
        self.assertNotEqual(reopened,[original])
        self.assertTrue(self.app.mp_feedback('past','a',True,rating=4,idem='late-postplan')['ok'])
        self.assertEqual(ms.status('a')['blockerIds']['chats'],reopened)

    def test_chat_read_reports_canonical_resume_end_block_and_failed_quota(self):
        self.free()
        with ms.transaction() as t:
            t.save_documents({'_requests':[{'id':'ab','from':'a','to':'b','status':'accepted'},
                                           {'id':'ac','from':'a','to':'c','status':'accepted'}]})
        def read(peer='b'):
            self.app.monetization_commands.refresh()
            class Handler:
                _pid='a'
                path='/api/agent/thread?self=spoofed&with_id='+peer
            h=Handler()
            self.assertTrue(self.app.H._restored_get(h))
            return h.result[1]
        before=read()['chat']
        self.assertEqual(before['peerId'],'b')
        self.assertEqual(before['state'],'new')
        self.assertIsNone(before['sessionId'])
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],0)
        self.assertTrue(self.app.send_message('a','b','first',client_id='first')['ok'])
        original=read()['chat']
        self.assertEqual(original['state'],'active')
        self.assertTrue(self.app.end_thread('a','b','end')['ok'])
        closed=read()
        self.assertEqual(closed['chat']['state'],'closed')
        self.assertIsNone(closed['chat']['sessionId'])
        self.assertTrue(any(m.get('text')=='first' for m in closed['messages']))
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],0)
        # A receipt for an earlier delivered message is not a resumed session.
        self.assertTrue(self.app.send_message('a','b','first',client_id='first')['ok'])
        self.assertEqual(read()['chat']['state'],'closed')
        self.assertTrue(self.app.send_message('a','c','occupy',client_id='occupy')['ok'])
        denied=self.app.send_message('a','b','resume denied',client_id='denied')
        self.assertEqual(denied['error'],'chat_quota')
        self.assertEqual(read()['chat']['state'],'closed')
        self.assertFalse(any(m.get('text')=='resume denied' for m in read()['messages']))
        self.assertTrue(self.app.end_thread('a','c','end-c')['ok'])
        self.assertTrue(self.app.send_message('a','b','resumed',client_id='resume')['ok'])
        resumed=read()['chat']
        self.assertEqual(resumed['state'],'active')
        self.assertNotEqual(resumed['sessionId'],original['sessionId'])
        self.assertGreater(resumed['serverTime'],closed['chat']['serverTime'])
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],1)
        self.assertTrue(self.app.end_thread('a','b','end')['ok'])
        self.assertEqual(read()['chat']['sessionId'],resumed['sessionId'])
        self.assertEqual(read()['chat']['state'],'active')
        # The peer's block must be visible too, without exposing anyone else's IDs.
        self.assertTrue(self.app.block_user('b','a',idem='peer-block')['ok'])
        blocked=read()['chat']
        self.assertTrue(blocked['blocked'])
        self.assertEqual(blocked['state'],'closed')
        self.assertEqual(set(blocked),{'peerId','state','sessionId','blocked','serverTime'})
        self.assertEqual(self.app.send_message('a','b','blocked',client_id='blocked')['error'],'BLOCKED')
        self.assertTrue(self.app.block_user('b','a',False,'unblock')['ok'])
        self.assertFalse(read()['chat']['blocked'])
        listed={r['who']:r['chat'] for r in self.app.threads_for('a')}
        self.assertEqual(listed['b']['state'],'closed')
        self.assertIsNone(listed['b']['sessionId'])
        self.assertEqual(listed['c']['state'],'closed')
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],0)
        with patch.dict(os.environ,{'KLEAL_MONETIZATION_MODE':'off'}):
            self.assertEqual(read()['chat']['state'],'legacy')

    def test_end_preserves_active_plan_communication_and_block_replay_is_safe(self):
        self.free()
        with ms.transaction() as t:
            t.save_documents({'_requests':[{'id':'ab','from':'a','to':'b','status':'accepted'},
                                           {'id':'ac','from':'a','to':'c','status':'accepted'}]})
        self.assertTrue(self.app.send_message('a','b','first',client_id='first')['ok'])
        with ms.transaction() as t:
            doc=t.documents();doc['_mplans']=[{'id':'live','host':'a','guest':'b','pair':self.app._pair_key('a','b'),
                'state':'confirmed','starts_at':t.now+86400,'version':1}]
            t.save_documents(doc);t.link_plan('live','a','b')
        self.assertTrue(self.app.end_thread('a','b','end')['ok'])
        self.assertTrue(self.app.send_message('a','c','new initiative',client_id='new-ac')['ok'])
        self.assertTrue(self.app.send_message('a','b','needed plan details',client_id='plan-details')['ok'])
        with ms.transaction() as t:
            self.assertEqual(t.conn.execute("select protected from monetization_sessions where pair=%s and state='active'",
                                            (ms.pair_key('a','b'),)).fetchone()[0],True)
        blocked=self.app.block_user('a','c',idem='block')
        self.assertTrue(blocked['ok'],blocked)
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],0)
        self.assertTrue(self.app.block_user('a','c',False,'unblock')['ok'])
        self.assertTrue(self.app.send_message('a','c','after unblock',client_id='reopened')['ok'])
        reopened=ms.status('a')['blockerIds']['chats']
        self.assertEqual(self.app.block_user('a','c',idem='block'),blocked)
        self.assertEqual(ms.status('a')['blockerIds']['chats'],reopened)
        self.assertTrue(self.app.end_thread('a','c','end-c')['ok'])
        plan_block=self.app.block_user('a','b',idem='block-live-plan')
        self.assertTrue(plan_block['ok'],plan_block)
        with ms.transaction() as t:
            self.assertEqual(t.documents()['_mplans'][0]['state'],'cancelled')
            self.assertIsNone(t.conn.execute("select 1 from monetization_sessions where pair=%s and state='active'",
                                             (ms.pair_key('a','b'),)).fetchone())
        self.assertTrue(self.app.block_user('a','b',False,'unblock-plan')['ok'])
        self.assertTrue(self.app.send_message('a','b','after plan block',client_id='reopen-plan')['ok'])
        reopened=ms.status('a')['blockerIds']['chats']
        self.assertEqual(len(reopened),1)
        self.assertEqual(self.app.block_user('a','b',idem='block-live-plan'),plan_block)
        self.assertEqual(ms.status('a')['blockerIds']['chats'],reopened)

    def test_writer_inventory_no_unclassified_save_store_paths(self):
        tree=ast.parse((ROOT/'services'/'matching'/'app.py').read_text())
        writers={node.name for node in tree.body if isinstance(node,ast.FunctionDef) and any(
            isinstance(call,ast.Call) and isinstance(call.func,ast.Name) and call.func.id=='_save_store' for call in ast.walk(node))}
        adapter=self.app.monetization_commands
        classified=set(adapter.WRITERS+adapter.UNADAPTED+adapter.TRANSACTION_ONLY+adapter.READ_PROJECTIONS)
        self.assertEqual(writers-classified,set())
        for name in adapter.WRITERS:
            self.assertTrue(hasattr(getattr(self.app,name),'__wrapped__'),name)
        before=copy.deepcopy(self.app.SESSION)
        with self.assertRaises(ms.CommandError): self.app.agent_transition({'object':{},'to':'sent'})
        self.assertEqual(self.app.SESSION,before)

    def test_picked_answer_preserves_sender_choice_and_grants_only_selected_recipient(self):
        with ms.transaction() as t:
            doc=t.documents();doc['_requests']=[
                {'id':'pick-b','from':'a','to':'b','status':'answered','iid':'same','intent':{'title':'same'},'updated':1},
                {'id':'pick-c','from':'a','to':'c','status':'answered','iid':'same','intent':{'title':'same'},'updated':1}]
            t.save_documents(doc)
        denied=self.app.pick_request('pick-b','b','denied-pick')
        self.assertFalse(denied['ok'])
        self.assertEqual(ms.status('b')['state'],'free')
        result=self.app.pick_request('pick-b','a','sender-pick')
        self.assertTrue(result['ok'],result)
        self.assertEqual(result,self.app.pick_request('pick-b','a','sender-pick'))
        self.assertEqual(ms.status('b')['state'],'preview')
        self.assertEqual(ms.status('c')['state'],'free')
        with ms.transaction() as t:
            self.assertEqual({r['id']:r['status'] for r in t.documents()['_requests']},
                             {'pick-b':'accepted','pick-c':'not_picked'})

    def test_support_system_and_media_share_correct_quota_semantics(self):
        self.free()
        self.assertTrue(self.app.admin_notify('a','Synthetic safety notification',idem='support')['ok'])
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],0)
        with ms.transaction() as t:
            doc=t.documents();doc['_requests']=[{'id':'ab','from':'a','to':'b','status':'accepted'},{'id':'ac','from':'a','to':'c','status':'accepted'}];t.save_documents(doc)
        voice={'id':'a'*32,'url':'/api/speech/audio/'+('a'*32)+'.m4a','duration_ms':1000,'mime_type':'audio/mp4','transcript':'Synthetic voice'}
        video={'id':'b'*32,'url':'/api/agent/video/'+('b'*32)+'.mp4','duration_ms':1000,'mime_type':'video/mp4'}
        one=self.app.send_message('a','b','',voice=voice,client_id='voice')
        self.assertTrue(one['ok'],one)
        self.assertEqual(self.app.send_message('a','b','',voice=voice,client_id='voice'),one)
        self.assertEqual(self.app.send_message('a','c','',video=video,client_id='video')['error'],'chat_quota')
        self.assertTrue(self.app.send_message('b','a','',video=video,client_id='reply-video')['ok'])
        self.assertTrue(self.app.message_delete('a',one['id'])['ok'])
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],1)

    def test_uploaded_voice_without_transcription_can_send_and_purge(self):
        self.free();self.app.VOICE_DIR=self.tmp.name
        with ms.transaction() as t:
            t.save_documents({'_requests':[{'id':'r','from':'a','to':'b','status':'accepted'}]})
        uploaded=self.app.voice_store('synthetic.m4a','audio/mp4',b'synthetic fixture not real audio',1000)
        result=self.app.send_message('a','b','',voice=uploaded,client_id='uploaded-voice')
        self.assertTrue(result['ok'],result)
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],1)
        path=Path(self.tmp.name)/uploaded['url'].rsplit('/',1)[-1]
        self.assertTrue(path.exists())
        self.assertTrue(self.app.purge_person('a')['ok'])
        self.assertTrue(path.exists())
        self.assertEqual(self.app.monetization_commands.drain_cleanup(),1)
        self.assertFalse(path.exists())

    def test_preview_media_initiatives_preserve_safety_and_free_limit_after_expiry(self):
        self.assertTrue(self.save()['ok'])
        with ms.transaction() as t:
            doc=t.documents();doc['_requests']=[{'id':'a'+peer,'from':'a','to':peer,'status':'accepted'} for peer in ('b','c','d')];t.save_documents(doc)
        voice={'id':'a'*32,'url':'/api/speech/audio/'+('a'*32)+'.m4a','duration_ms':1000,'mime_type':'audio/mp4','transcript':'Synthetic voice'}
        video={'id':'b'*32,'url':'/api/agent/video/'+('b'*32)+'.mp4','duration_ms':1000,'mime_type':'video/mp4'}
        for peer,kwargs in [('b',{'text':'text'}),('c',{'text':'','voice':voice}),('d',{'text':'','video':video})]:
            with self.subTest(peer=peer):
                result=self.app.send_message('a',peer,client_id='first-'+peer,**kwargs)
                self.assertTrue(result['ok'],result)
                self.assertEqual(self.app.send_message('a',peer,client_id='first-'+peer,**kwargs),result)
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],3)
        with ms.transaction() as t:
            t.conn.execute("update monetization_accounts set preview_start=%s,preview_end=%s where owner_id='a'",(t.now-1209601,t.now-1))
        self.assertTrue(self.app.send_message('a','c','continued after expiry',client_id='continued')['ok'])
        self.assertTrue(self.app.end_thread('a','b','end-b')['ok'])
        self.assertEqual(self.app.send_message('a','b','new session',client_id='new-b')['error'],'chat_quota')
        self.assertTrue(self.app.block_user('a','d',idem='block')['ok'])
        self.assertFalse(self.app.send_message('a','d','',video=video,client_id='blocked')['ok'])
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],1)

    def test_pending_invite_survives_actual_expiry_without_reopening_recruitment(self):
        group=self.app.gi_create('a',{'topics':['coffee']},'Coffee',idem='group')
        gid=group['group']['gid']
        invite=self.app.gi_invite(gid,'a','b',idem='invite')['invite']['id']
        kept=self.save(key='keep')
        with ms.transaction() as t:
            keep=t.resolve('intent',kept['id'])
            t.conn.execute("update monetization_accounts set keep_search=%s,preview_start=%s,preview_end=%s where owner_id='a'",(keep,t.now-1209601,t.now-1))
        accepted=self.app.gi_respond(invite,'b',True,'accept')
        self.assertTrue(accepted['ok'],accepted)
        self.assertEqual(ms.status('b')['state'],'preview')
        self.assertEqual(ms.status('a')['blockerIds']['searches'],[keep])
        self.assertEqual(self.app.gi_invite(gid,'a','c',idem='new')['error'],'search_paused')
        self.assertEqual(self.app.gi_respond(invite,'b',True,'accept'),accepted)
        with ms.transaction() as t:
            self.assertEqual(t.resource(t.resolve('group',gid))['state'],'paused')
            self.assertEqual(t.conn.execute("select count(*) from monetization_audit where owner_id='b' and event='preview_meaningful_use'").fetchone()[0],1)

    def test_nested_report_block_releases_chat_without_plan_and_replay_is_safe(self):
        self.free()
        with ms.transaction() as t:
            t.save_documents({'_requests':[{'id':'r','from':'a','to':'b','status':'accepted'}]})
        self.assertTrue(self.app.send_message('a','b','before report',client_id='before')['ok'])
        report=self.app.report_user('a','b','harassment','Synthetic report','report')
        self.assertTrue(report['ok'],report)
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],0)
        self.app.block_user('a','b',False,'unblock')
        self.assertTrue(self.app.send_message('a','b','new session',client_id='new')['ok'])
        self.assertEqual(self.app.report_user('a','b','harassment','Synthetic report','report'),report)
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],1)

    def test_nested_group_report_block_releases_chat_and_replay_is_safe(self):
        self.free()
        group=self.app.gi_create('a',{'topics':['coffee']},'Synthetic group',idem='group')
        gid=group['group']['gid']
        invitation=self.app.gi_invite(gid,'a','b',idem='invite')
        self.assertTrue(self.app.gi_respond(invitation['invite']['id'],'b',True,'join')['ok'])
        with ms.transaction() as t:
            doc=t.documents();doc['_requests']=[{'id':'r','from':'a','to':'b','status':'accepted'}];t.save_documents(doc)
        self.assertTrue(self.app.send_message('a','b','before group report',client_id='before')['ok'])
        report=self.app.gi_report(gid,'a','rule_violation',text='Synthetic group report',idem='report',about='b')
        self.assertTrue(report['ok'],report)
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],0)
        self.assertTrue(self.app.block_user('a','b',False,'unblock')['ok'])
        self.assertTrue(self.app.send_message('a','b','new session',client_id='new')['ok'])
        self.assertEqual(self.app.gi_report(gid,'a','rule_violation',text='Synthetic group report',idem='report',about='b'),report)
        self.assertEqual(ms.status('a')['usage']['initiatedChats'],1)

    def test_legacy_paused_group_new_join_blocked_existing_waitlist_promoted(self):
        r=self.app.group_create('a','Coffee',['coffee'],min_size=2,max_size=2,idem='legacy')
        self.assertTrue(r['ok'],r)
        gid=r['group']['gid']
        self.assertTrue(self.app.group_join(gid,'b','b')['ok'])
        pending=self.app.group_join(gid,'c','c')
        self.assertTrue(pending['waitlisted'],pending)
        self.assertIsNone(ms.status('c')['previewStartedAt'])
        with ms.transaction() as t:
            t.pause('a',t.resolve('group',gid))
        self.assertEqual(self.app.group_join(gid,'d','d')['error'],'search_paused')
        self.assertTrue(self.app.group_leave(gid,'b','leave')['ok'])
        self.assertEqual(ms.status('c')['state'],'preview')

    def test_real_http_map_reply_uses_authors_search_without_publishing_responders_search(self):
        self.free()
        own=self.save()
        original={'title':'Native hybrid','topics':['coffee'],'mode':'hybrid','address':'Synthetic Madrid venue',
                  'lat':40.4,'lng':-3.7,'starts_at':time.time()+7*86400,'link':'private-link','text':'private Buddy text'}
        target=self.app.save_intent('Same name',original,'Native hybrid',launched=True,owner_id='d',idem='target')
        self.app.monetization_commands.refresh()
        feeds=[self.app.map_feed_payload(view,self_id='a')['items'] for view in ('offline','online')]
        cards=[next(r for r in rows if r['id']==target['id']) for rows in feeds]
        self.assertEqual(cards[0]['searchId'],cards[1]['searchId'])
        rid=cards[0]['searchId']
        before=ms.status('a')
        prior=self.app.propose('a','d',{'id':own['id']},'',idem='own-pending')
        self.assertTrue(prior['ok'],prior)
        import kleal_auth
        from http.server import ThreadingHTTPServer
        accounts={x:{'person_id':x,'sessions':{hashlib.sha256(x.encode()).hexdigest():{'exp':time.time()+3600}}} for x in ('a','b','c','d')}
        users=[{'id':x,'owner':x,'name':'Same name'} for x in accounts]
        server=ThreadingHTTPServer(('127.0.0.1',0),self.app.H)
        self.app.send_json=lambda h,status,obj:self.app._send_json_raw(h,obj.get('httpStatus',status) if isinstance(obj,dict) else status,obj)
        def call(body,token='a',path='/api/agent/propose'):
            conn=http.client.HTTPConnection(*server.server_address,timeout=3)
            conn.request('POST',path,json.dumps(body),{'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            r=conn.getresponse(); result=(r.status,json.loads(r.read())); conn.close(); return result
        body={'from':'d','to':'Same name','to_id':'d','idem':'map-reply',
              'intent':{'targetSearchId':rid,'targetIntentId':target['id'],'topics':['tampered'],'link':'injected'}}
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        with patch.object(kleal_auth,'_accounts',return_value=accounts),patch.object(kleal_auth,'_population',return_value=users):
            thread.start()
            try:
                code,response=call(body)
                self.assertEqual(code,200,response)
                self.assertTrue(response['ok'],response)
                self.assertNotEqual(response['id'],prior['id'],'partner contract: another intent keeps its own pending proposal')
                preserved=next(r for r in self.app.outbox('a') if r['id']==prior['id'])
                self.assertEqual(preserved['status'],'pending')
                self.assertNotEqual(preserved.get('iid'),target['id'])
                self.assertEqual(call(body)[1],response,'same reply command has one durable result')
                after=ms.status('a')
                self.assertIsInstance(after['serverTime'],int)
                self.assertGreaterEqual(after['serverTime'],before['serverTime'])
                with ms.transaction() as t:
                    self.assertLessEqual(after['serverTime'],t.now,'status time must not be ahead of the database clock')
                # The invitation must change no entitlement, usage or resource field;
                # only the observation timestamp may advance across a second boundary.
                self.assertEqual({k:v for k,v in after.items() if k!='serverTime'},
                                 {k:v for k,v in before.items() if k!='serverTime'})
                stored=next(r for r in self.app.outbox('a') if r['id']==response['id'])
                self.assertEqual((stored['from'],stored['to']),('a','d'),'bearer and stable recipient ID win over names')
                self.assertEqual(stored['intent']['targetSearchId'],rid)
                self.assertEqual(stored['intent']['targetIntentId'],target['id'])
                self.assertEqual(stored['intent']['topics'],['coffee'])
                self.assertEqual(stored['intent']['title'],'Native hybrid')
                self.assertNotIn('link',stored['intent']);self.assertNotIn('text',stored['intent'])
                self.assertNotIn('_searchId',stored['intent']);self.assertNotIn('id',stored['intent'])
                self.assertEqual(stored['iid'],'','reply must not retain the replaced own-intent association')
                with ms.transaction() as t:
                    self.assertEqual(t.conn.execute('select count(*) from monetization_resources').fetchone()[0],2)
                    self.assertTrue(t.protected('invite',response['id'],'accept'))
                    provenance=t.conn.execute("select provenance from monetization_protected where kind='invite' and resource_id=%s",(response['id'],)).fetchone()[0]
                    self.assertEqual(provenance['searchId'],rid)
                    self.assertEqual(provenance['searchOwnerId'],'d')
                for intent,to,expected in [
                    ({'topics':['coffee']},'d','search_reference_required'),
                    ({'targetSearchId':'search_missing'},'d','search_not_found'),
                    ({'targetIntentId':'missing'},'d','search_reference_required'),
                    ({'targetSearchId':rid},'c','not_your_search'),
                    ({'targetSearchId':rid,'targetIntentId':own['id']},'d','search_reference_mismatch'),
                    ({'_searchId':rid},'d','not_your_search'),
                    ({'targetSearchId':{'invalid':True}},'d','invalid_search_reference'),
                ]:
                    code,error=call({'to_id':to,'intent':intent})
                    self.assertGreaterEqual(code,400,error);self.assertEqual(error['error'],expected)
                # Legacy detail entrypoint carries only targetIntentId; it is still a reply,
                # not a new publication or a meaningful-use grant to the eligible responder.
                code,eligible=call({'to_id':'d','intent':{'targetIntentId':target['id']}},token='b')
                self.assertEqual(code,200,eligible)
                self.assertIsNone(ms.status('b')['previewStartedAt'])
                self.assertEqual(ms.status('b')['usage'],{'activeSearches':0,'initiatedChats':0})
                self.assertTrue(self.app.block_user('d','c')['ok'])
                code,error=call({'to_id':'d','intent':{'targetSearchId':rid}},token='c')
                self.assertEqual(error['error'],'BLOCKED')
                with ms.transaction() as t: t.pause('d',rid)
                code,error=call({**body,'idem':'new-after-pause'})
                self.assertEqual((code,error['error']),(409,'search_paused'))
                code,accepted=call({'id':response['id'],'decision':'accept','idem':'old-obligation'},token='d',path='/api/agent/respond')
                self.assertEqual(code,200,accepted);self.assertTrue(accepted['ok'],accepted)
                self.assertEqual(ms.status('a')['usage'],{'activeSearches':1,'initiatedChats':0})
                print('MAP_REPLY_HTTP_PASS searchId=%s invitationId=%s sender=a author=d usage=1/0' % (rid,response['id']),flush=True)
            finally:
                server.shutdown();server.server_close();thread.join(2)

    def test_map_group_reply_is_application_not_membership_or_own_search(self):
        self.free()
        self.assertTrue(self.save()['ok'])
        group=self.app.gi_create('d',{'topics':['coffee'],'mode':'hybrid'},'Group',2,4,idem='group')['group']
        result=self.app.propose('a','d',{'targetIntentId':group['gid']},'',idem='group-reply')
        self.assertTrue(result['ok'],result)
        self.assertEqual(ms.status('a')['usage'],{'activeSearches':1,'initiatedChats':0})
        self.assertNotIn('a',[m['name'] for m in self.app.SESSION['_gintents'][0]['members']])
        self.assertEqual(len(self.app.SESSION['_gintents']),1)
        self.assertEqual(self.app.propose('b','c',{'targetIntentId':group['gid']},'')['error'],'not_your_search')
        with ms.transaction() as t: t.pause('d',t.resolve('group',group['gid']))
        self.assertEqual(self.app.propose('b','d',{'targetIntentId':group['gid']},'')['error'],'search_paused')

    def test_map_reply_checks_actual_expiry_but_keeps_existing_reply(self):
        target=self.save(owner='d',key='target')
        intent={'targetIntentId':target['id']}
        pending=self.app.propose('a','d',intent,'',idem='before-expiry')
        self.assertTrue(pending['ok'],pending)
        kept=self.app.save_intent('Same name',{'topics':['padel']},'Keep',launched=True,owner_id='d',idem='keep')
        with ms.transaction() as t:
            keep=t.resolve('intent',kept['id'])
            t.conn.execute("update monetization_accounts set keep_search=%s,preview_start=%s,preview_end=%s where owner_id='d'",(keep,t.now-1209601,t.now-1))
        denied=self.app.propose('b','d',intent,'',idem='new-after-expiry')
        self.assertEqual(denied['error'],'search_paused')
        accepted=self.app.respond(pending['id'],'accept','d',idem='accept-old')
        self.assertTrue(accepted['ok'],accepted)
        self.assertEqual(ms.status('a')['usage'],{'activeSearches':0,'initiatedChats':0})
        self.assertIsNone(ms.status('a')['previewStartedAt'])

    def test_map_reply_public_snapshot_off_and_shadow_remains_legacy_without_grant(self):
        public={'targetIntentId':'legacy-intent-d','targetSearchId':'search_legacy_d',
                'title':'Native hybrid','topics':['coffee'],'mode':'hybrid','when':'Saturday',
                'dateKey':'2026-11-01','minutes':600,'address':'Synthetic Madrid venue'}
        for mode in ('off','shadow'):
            with patch.dict(os.environ,{'KLEAL_MONETIZATION_MODE':mode}):
                result=self.app.propose('a','d',copy.deepcopy(public),'',idem='reply-'+mode)
                self.assertTrue(result['ok'],result)
                stored=next(r for r in self.app.outbox('a') if r['id']==result['id'])
                self.assertEqual(stored['intent'],public)
                for private in ('link','phrase','text','summary','exact_point','id','iid','_searchId','searchId'):
                    self.assertNotIn(private,stored['intent'])
        with ms.transaction() as t:
            self.assertEqual(t.conn.execute('select count(*) from monetization_resources').fetchone()[0],0)
            self.assertEqual(t.conn.execute("select count(*) from monetization_audit where event='preview_meaningful_use'").fetchone()[0],0)
        self.assertIsNone(ms.status('a')['previewStartedAt'])

    def test_real_http_authentication_and_legacy_route_cannot_bypass_quota(self):
        self.free()
        import kleal_auth
        from http.server import ThreadingHTTPServer
        accounts={x:{'person_id':x,'sessions':{hashlib.sha256(x.encode()).hexdigest():{'exp':time.time()+3600}}} for x in ('a','b')}
        users=[{'id':x,'owner':x,'name':'Same name'} for x in ('a','b')]
        server=ThreadingHTTPServer(('127.0.0.1',0),self.app.H)
        # Restore real wire serialization; direct adapter assertions above capture results.
        self.app.send_json=lambda h,status,obj:self.app._send_json_raw(h,obj.get('httpStatus',status) if isinstance(obj,dict) else status,obj)
        def call(path,body,token='a'):
            conn=http.client.HTTPConnection(*server.server_address,timeout=3)
            headers={'Content-Type':'application/json'}
            if token: headers['Authorization']='Bearer '+token
            conn.request('POST',path,json.dumps(body),headers)
            r=conn.getresponse(); result=(r.status,json.loads(r.read())); conn.close(); return result
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        with patch.object(kleal_auth,'_accounts',return_value=accounts),patch.object(kleal_auth,'_population',return_value=users):
            thread.start()
            try:
                body={'intent':{'topics':['coffee']},'commandId':'http-one','self':'b'}
                self.assertEqual(call('/api/agent/search-command',body,token='')[0],401)
                code,res=call('/api/agent/search-command',body)
                self.assertEqual(code,200,res)
                self.assertEqual(ms.status('b')['usage']['activeSearches'],0)
                code,res=call('/api/agent/gintent-create',{'intent':{'topics':['padel']},'idem':'other'})
                self.assertEqual((code,res['error']),(409,'search_quota'))
                code,res=call('/api/agent/match',{'intent':{'topics':['run']},'idem':'old-client'})
                self.assertEqual((code,res['error']),(409,'search_quota'))
            finally:
                server.shutdown();server.server_close();thread.join(2)

    def test_real_serving_kyc_denied_is_identical_for_free_and_preview(self):
        import kleal_auth
        import age_verification as age
        from serving import KlealServer
        accounts={'a':{'person_id':'a','created':100,'sessions':{hashlib.sha256(b'a').hexdigest():{'exp':time.time()+3600}}}}
        users=[{'id':'a','owner':'a','name':'Same name'}]
        self.app.send_json=lambda h,status,obj:self.app._send_json_raw(h,status,obj)
        server=KlealServer(('127.0.0.1',0),self.app.H)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        with patch.dict(os.environ,{'KLEAL_AGE_GATE_ENABLED':'1','KLEAL_AGE_COHORT_KEYS':'["a"]',
                                   'KLEAL_AGE_GATE_FROM':'1','KLEAL_AGE_DB':self.tmp.name+'/age.sqlite',
                                   'KLEAL_AGE_BINDING_SECRET':'synthetic-only-binding-secret-for-local-tests'}), \
             patch.object(kleal_auth,'_accounts',return_value=accounts),patch.object(kleal_auth,'_population',return_value=users):
            with age.database() as c:
                c.execute("insert into verification(subject,status) values(?,'declined')",(age.subject('a',accounts['a']),))
            thread.start()
            try:
                for tier in ('free','preview'):
                    if tier=='preview':
                        with ms.transaction() as t: t.grant('a',{'synthetic':'preexisting grant'})
                    self.assertFalse(age.state('a',accounts['a'])['admitted'])
                    for path in ('/api/agent/search-command','/api/agent/message','/api/agent/match'):
                        conn=http.client.HTTPConnection(*server.server_address,timeout=3)
                        conn.request('POST',path,json.dumps({'intent':{'topics':['coffee']},'commandId':tier}),
                                     {'Authorization':'Bearer a','Content-Type':'application/json'})
                        response=conn.getresponse();body=json.loads(response.read());conn.close()
                        self.assertEqual((response.status,body['error']),(403,'age_verification_required'))
                with ms.transaction() as t:
                    self.assertEqual(t.conn.execute('select count(*) from monetization_commands').fetchone()[0],0)
                    self.assertEqual(t.conn.execute('select count(*) from monetization_resources').fetchone()[0],0)
            finally:
                server.shutdown();server.server_close();thread.join(2)


if __name__=='__main__': unittest.main()
