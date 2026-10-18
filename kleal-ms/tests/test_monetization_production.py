import copy
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch
import test_monetization_pg as pg
from test_monetization_pg import ms,DSN
import monetization_production as prod
import monetization_admin as admin
import monetization_safety as safety
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ops'))
import monetization_release as release


class Plan(unittest.TestCase):
    def data(self):
        return {'users':[{'id':'a'},{'id':'b'}],'session':{
            '_intents':[{'id':'i','owner_id':'a','launched':100,'title':'one'},
                        {'id':'orphan','owner_id':'anon:old','launched':50}],
            '_messages':[{'id':'duplicate','from':'a','to':'b','t':1,'text':'hello'},
                         {'id':'duplicate','from':'a','to':'b','t':2,'sys':{'code':'chat_ended'}},
                         {'id':'historic','from':'anon:old','to':'b','t':3,'text':'history'}],
            '_settings':{'version':1},'_interest_proposals':{'pending':['x']},
            '_premig_v3':{'_exposure':{'Legacy name':[12]}}}}

    def test_anon_duplicates_and_ended_chat_preserved(self):
        data=self.data();before=copy.deepcopy(data);report=prod.plan(data)
        self.assertTrue(report['ok'],report['issues']);self.assertEqual(data,before)
        self.assertEqual(report['preserved'],{'_intents':['orphan']})
        self.assertEqual(len(report['resources']),1)
        self.assertEqual(report['sessions'][0]['state'],'closed')
        self.assertEqual(report['externalKeys'],['_interest_proposals','_settings'])

    def test_active_ambiguous_foreign_alias_unknown_lifecycle_block(self):
        for group in ({'id':'g','owner':'a','state':'searching'},
                      {'id':'g','owner':'b','state':'searching','intent':{'iid':'i'}},
                      {'id':'g','owner':'a','state':'mystery'}):
            data=self.data();data['session']['_gintents']=[group]
            self.assertFalse(prod.plan(data)['ok'])
        data=self.data();data['session']['_gintents']=[{'id':'g','owner':'a','state':'searching','intent':{'iid':'i'}}]
        report=prod.plan(data);self.assertTrue(report['ok'],report['issues'])
        self.assertEqual(len(report['resources']),1)

    def test_production_planning_lifecycles_registered_and_anonymous(self):
        for lifecycle in ('below_quorum','planning','planned'):
            for owner in ('a','anon:old'):
                with self.subTest(state=lifecycle,owner=owner):
                    data=self.data()
                    data['session']['_gintents']=[{'id':'g','owner':owner,'state':lifecycle,
                        'intent':{'iid':'i' if owner=='a' else 'orphan'},
                        'members':[{'name':owner,'state':'joined'},{'name':'b','state':'joined'}]}]
                    report=prod.plan(data)
                    self.assertTrue(report['ok'],report['issues'])
                    if owner=='a':
                        self.assertEqual(report['aliases']['group:g'],report['aliases']['intent:i'])
                        self.assertEqual(report['resources'][report['aliases']['group:g']]['state'],'active')
                    else:
                        self.assertEqual(report['preserved']['_gintents'],['g'])
                        self.assertNotIn('group:g',report['aliases'])
            data=self.data();data['session']['_gintents']=[{'id':'g','owner':'anon:old','state':'invented'}]
            self.assertFalse(prod.plan(data)['ok'])

    def test_manifest_exact_hashes_traversal_and_partial_install_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'live';root.mkdir();candidate=Path(temp)/'candidate';candidate.mkdir()
            (root/'a.py').write_text('old');(candidate/'a.py').write_text('new');(candidate/'b.py').write_text('added')
            manifest=release.make_manifest(root,candidate,['a.py','b.py'])
            release.verify_manifest(root,manifest,'before')
            with self.assertRaises(ValueError): release.target(root,'../escape')
            with patch.object(release,'require_stopped',return_value={}):
                release.install(root,candidate,manifest,Path(temp)/'backup')
                release.restore_files(root,Path(temp)/'backup',manifest)
            self.assertEqual((root/'a.py').read_text(),'old');self.assertFalse((root/'b.py').exists())
            (root/'a.py').write_text('peer edit')
            with self.assertRaisesRegex(ValueError,'drift'): release.verify_manifest(root,manifest,'before')

    def test_restore_checks_actual_peer_before_any_schema_write(self):
        queries=[]
        class Connection:
            info=SimpleNamespace(host='localhost',hostaddr='203.0.113.20')
            def execute(self,query,*args):
                queries.append(query)
                row=('kleal_monetization_test_fake','test_owned') if 'current_database()' in query else None
                return SimpleNamespace(fetchone=lambda:row,fetchall=lambda:[])
        snapshot={'version':1,'tables':{}};snapshot['checksum']=ms.digest(snapshot)
        with self.assertRaisesRegex(ValueError,'loopback'):
            release.restore_rehearsal(Connection(),snapshot)
        self.assertFalse(any('create table' in q for q in queries))

    def test_test_dsn_rejects_network_overrides_without_connecting(self):
        import monetization_safety as safety
        base='postgresql://test@localhost/kleal_monetization_test_only'
        for dsn in (base+'?hostaddr=203.0.113.20',base+'?service=remote',
                    'host=localhost,remote dbname=kleal_monetization_test_only',
                    'host=localhost hostaddr=127.0.0.1 dbname=kleal_monetization_test_only'):
            with self.subTest(dsn=dsn),self.assertRaises(ValueError): safety.validate_test_dsn(dsn)
        for variable in ('PGHOSTADDR','PGSERVICE','PGSERVICEFILE'):
            with patch.dict(os.environ,{variable:'override'}),self.assertRaises(ValueError):
                safety.validate_test_dsn(base)

    def test_release_preserves_original_metadata_and_refuses_drift_or_chown_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'live';root.mkdir();candidate=Path(temp)/'candidate';candidate.mkdir()
            old=root/'a.py';new=candidate/'a.py'
            old.write_text('old');old.chmod(0o640);new.write_text('new');new.chmod(0o755)
            manifest=release.make_manifest(root,candidate,['a.py'])
            meta=manifest['files'][0]['beforeMetadata']
            self.assertEqual(meta,{'mode':0o640,'uid':old.stat().st_uid,'gid':old.stat().st_gid})
            old.chmod(0o600)
            with self.assertRaisesRegex(ValueError,'drift'): release.verify_manifest(root,manifest,'before')
            old.chmod(0o640)
            with patch.object(release,'require_stopped',return_value={}):
                with patch.object(release.os,'chown',side_effect=PermissionError('cannot preserve owner')):
                    with self.assertRaises(PermissionError): release.install(root,candidate,manifest,Path(temp)/'failed')
                self.assertEqual(old.read_text(),'old');self.assertEqual(old.stat().st_mode & 0o777,0o640)
                prepare=release.prepare_file
                def drift_after_prepare(*args):
                    prepare(*args);old.chmod(0o600)
                with patch.object(release,'prepare_file',side_effect=drift_after_prepare):
                    with self.assertRaisesRegex(ValueError,'drift'):
                        release.install(root,candidate,manifest,Path(temp)/'metadata-drift')
                self.assertEqual(old.read_text(),'old');old.chmod(0o640)
                release.install(root,candidate,manifest,Path(temp)/'backup')
                self.assertEqual(release.metadata(old),meta)
                old.chmod(0o600)
                with self.assertRaisesRegex(ValueError,'drift'): release.restore_files(root,Path(temp)/'backup',manifest)
                old.chmod(0o640)
                release.restore_files(root,Path(temp)/'backup',manifest)
                self.assertEqual(old.read_text(),'old');self.assertEqual(release.metadata(old),meta)

    def test_interrupted_install_restores_only_manifest_bytes_and_original_metadata(self):
        for paths in (['a.py','new.py'],['new.py','a.py']):
            with self.subTest(order=paths),tempfile.TemporaryDirectory() as temp:
                root=Path(temp)/'live';root.mkdir();candidate=Path(temp)/'candidate';candidate.mkdir()
                old=root/'a.py';old.write_text('original');old.chmod(0o640)
                original=release.metadata(old)
                (candidate/'a.py').write_text('replacement');(candidate/'a.py').chmod(0o755)
                (candidate/'new.py').write_text('added');(candidate/'new.py').chmod(0o600)
                (root/'peer.txt').write_text('unrelated work')
                manifest=release.make_manifest(root,candidate,paths)
                replacements=[];replace=release.os.replace
                def interrupt_second(source,destination):
                    if replacements: raise OSError('synthetic interruption before second replacement')
                    replace(source,destination);replacements.append(str(destination))
                with patch.object(release,'require_stopped',return_value={}):
                    with patch.object(release.os,'replace',side_effect=interrupt_second):
                        with self.assertRaisesRegex(OSError,'interruption'):
                            release.install(root,candidate,manifest,Path(temp)/'backup')
                    self.assertEqual(len(replacements),1)
                    current=old.read_bytes();old.write_text('concurrent peer edit')
                    with self.assertRaisesRegex(ValueError,'drift'):
                        release.restore_files(root,Path(temp)/'backup',manifest)
                    self.assertEqual(old.read_text(),'concurrent peer edit')
                    self.assertEqual((root/'new.py').exists(),paths[0]=='new.py')
                    old.write_bytes(current)
                    release.restore_files(root,Path(temp)/'backup',manifest)
                self.assertEqual(old.read_text(),'original');self.assertEqual(release.metadata(old),original)
                self.assertFalse((root/'new.py').exists())
                self.assertEqual((root/'peer.txt').read_text(),'unrelated work')


@unittest.skipUnless(DSN,'BLOCKED: isolated PostgreSQL DSN not configured')
class Production(unittest.TestCase):
    setUpClass=classmethod(pg.PostgreSQLCommands.setUpClass.__func__)
    tearDown=pg.PostgreSQLCommands.tearDown

    def setUp(self):
        self.schema='test_'+uuid.uuid4().hex
        with self.psycopg.connect(DSN,autocommit=True) as c:
            safety.guard(c,require_schema=False)
            c.execute('create schema '+self.schema)
        self.prior=(ms.db.ENABLED,ms.db.MIRROR_JSON,ms.db._pool)
        ms.db.ENABLED,ms.db.MIRROR_JSON=True,False
        ms.db._pool=self.poolclass(DSN,kwargs={'options':'-c search_path='+self.schema},min_size=1,max_size=3)
        data=Plan().data()
        with ms.connection() as c:
            c.execute(ms.db.SCHEMA)
            for u in data['users']: c.execute('insert into users(id,name_key,name,row) values(%s,%s,%s,%s)',(u['id'],u['id'],'Same',json.dumps(u)))
            for k,v in data['session'].items(): c.execute('insert into store_kv(key,value) values(%s,%s)',(k,json.dumps(v)))

    def stage(self):
        with ms.connection() as c:
            data=prod.snapshot(c);report=prod.plan(data);self.assertTrue(report['ok'],report['issues'])
            return prod.import_snapshot(c,report['snapshotHash'])

    def test_synthetic_migration_cli_requires_existing_explicit_schema(self):
        with tempfile.TemporaryDirectory() as temp:
            fixture=Path(temp)/'fixture.json'
            fixture.write_text(json.dumps({'synthetic':True,'users':[{'id':'cli_owner'}],'session':{}}))
            command=[sys.executable,str(pg.ROOT/'tools'/'monetization_migrate.py'),str(fixture),'--apply']
            environment={**os.environ,'KLEAL_PG_DSN':DSN}
            for arguments in ([],['--schema','public'],['--schema','test_ok,public']):
                with self.subTest(arguments=arguments):
                    result=subprocess.run(command+arguments,env=environment,capture_output=True,text=True)
                    self.assertEqual(result.returncode,2,result.stderr)
                    self.assertIn('test_* schema',result.stderr)
            missing='test_missing_'+uuid.uuid4().hex
            result=subprocess.run(command+['--schema',missing],env=environment,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('test_* schema',result.stderr)
            with ms.connection() as c:
                self.assertIsNone(c.execute("select to_regclass('monetization_accounts')").fetchone()[0])
                self.assertFalse(c.execute('select 1 from pg_namespace where nspname=%s',(missing,)).fetchone())
            result=subprocess.run(command+['--schema',self.schema],env=environment,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(json.loads(result.stdout)['ok'])
            with ms.connection() as c:
                self.assertEqual(c.execute('select owner_id from monetization_accounts').fetchall(),[('cli_owner',)])

    def test_dry_run_drift_no_schema_mutation(self):
        with ms.connection() as c:
            c.execute('set transaction isolation level repeatable read read only')
            report=prod.plan(prod.snapshot(c));self.assertTrue(report['ok'])
            self.assertIsNone(c.execute("select to_regclass('monetization_meta')").fetchone()[0])
        with self.assertRaisesRegex(ValueError,'drift'):
            with ms.connection() as c: prod.import_snapshot(c,'wrong')
        with ms.connection() as c: self.assertIsNone(c.execute("select to_regclass('monetization_meta')").fetchone()[0])

    def test_import_fence_activation_new_writes_export_preserves_foreign(self):
        self.stage()
        with self.assertRaises(ms.CommandError): ms.status('a')
        def grant():
            with ms.connection() as c:
                return admin.command(c,action='grant',owner='a',expires=ms.Transaction(c).now+3600,
                                     operator='test',reason='fence',key='fenced-grant',apply=True)
        with self.assertRaises(ms.CommandError): grant()
        with self.assertRaises(self.psycopg.Error):
            with ms.connection() as c: c.execute("update store_kv set value='[]' where key='_messages'")
        with self.assertRaises(self.psycopg.Error):
            with ms.connection() as c: c.execute("update store_kv set key='renamed_external' where key='_messages'")
        with ms.connection() as c:
            c.execute("update store_kv set value='{\"version\":2}' where key='_settings'")
            prod.activate(c)
        with ms.transaction() as t:
            self.assertEqual(t.conn.execute('select count(*) from monetization_accounts').fetchone()[0],2)
            self.assertEqual(t.conn.execute('select state from monetization_sessions').fetchone()[0],'closed')
            self.assertEqual(t.documents()['_premig_v3'],{'_exposure':{'Legacy name':[12]}})
            doc=t.documents();doc['_messages'].append({'id':'new','from':'a','to':'b','text':'after activation'})
            t.publish('a',{'title':'new search'});t.save_documents(doc)
            t.conn.execute("update users set row=row || '{\"newProfileValue\":true}' where id='a'")
        with ms.connection() as c:
            result=prod.export_legacy(c,True);self.assertTrue(result['ok'])
            state=dict(c.execute('select key,value from store_kv').fetchall())
            self.assertEqual(state['_settings'],{'version':2})
            self.assertEqual(state['_interest_proposals'],{'pending':['x']})
            self.assertEqual(state['_premig_v3'],{'_exposure':{'Legacy name':[12]}})
            self.assertEqual(len(state['_messages']),4)
            self.assertTrue(c.execute("select row->'newProfileValue' from users where id='a'").fetchone()[0])
        with self.assertRaises(ms.CommandError): ms.status('a')
        with self.assertRaises(ms.CommandError): grant()

    def test_backup_restore_fresh_records_only_empty_isolated_schema(self):
        self.stage()
        with ms.connection() as c: saved=release.backup(c)
        target='test_restore_'+uuid.uuid4().hex
        try:
            with self.psycopg.connect(DSN) as c:
                c.execute('create schema '+target);c.execute('set search_path to '+target)
                release.restore_rehearsal(c,saved)
                self.assertEqual(release.backup(c)['checksum'],saved['checksum'])
                with self.assertRaisesRegex(ValueError,'empty'): release.restore_rehearsal(c,saved)
        finally:
            with self.psycopg.connect(DSN,autocommit=True) as c: c.execute('drop schema if exists '+target+' cascade')

    def test_planning_import_keeps_aliases_commitments_and_anonymous_history(self):
        groups=[];plans=[];intents=[]
        for n,state in enumerate(('below_quorum','planning','planned')):
            iid='i'+str(n);gid='g'+str(n)
            intents.append({'id':iid,'owner_id':'a','launched':100+n,'title':state})
            groups.append({'id':gid,'owner':'a','state':state,'intent':{'iid':iid},
                           'members':[{'name':'a','state':'joined'},{'name':'b','state':'joined'}]})
            plans.append({'id':'p'+str(n),'gid':gid,'owner':'a','state':
                          {'below_quorum':'below_quorum','planning':'proposed','planned':'confirmed'}[state],
                          'responses':{'b':{'state':'confirmed'}},'starts_at':2000000000})
        groups.append({'id':'anon-group','owner':'anon:old','state':'below_quorum',
                       'members':[{'name':'anon:old','state':'joined'},{'name':'b','state':'joined'}]})
        invites=[{'id':'old-invite','gid':'g2','frm':'a','to':'b','state':'pending_approval'}]
        with ms.connection() as c:
            for key,value in {'_intents':intents,'_gintents':groups,'_gplans':plans,'_ginvites':invites}.items():
                c.execute('insert into store_kv(key,value) values(%s,%s) on conflict(key) do update set value=excluded.value',
                          (key,json.dumps(value)))
        self.stage()
        with ms.connection() as c:
            tx=ms.Transaction(c)
            for n in range(3):
                rid=tx.resolve('group','g'+str(n))
                self.assertEqual(rid,tx.resolve('intent','i'+str(n)))
                self.assertEqual(tx.resource(rid)['state'],'active')
            prod.activate(c)
            self.assertEqual(tx.status('a')['usage']['activeSearches'],1)
            self.assertEqual(tx.documents()['_gplans'],plans)
            self.assertEqual([g['state'] for g in tx.documents()['_gintents']],
                             ['below_quorum','planning','planned','below_quorum'])
            self.assertTrue(c.execute("select 1 from monetization_protected where resource_id='old-invite'").fetchone())
            self.assertFalse(c.execute("select 1 from monetization_accounts where owner_id like 'anon:%'").fetchone())
            prod.export_legacy(c,True)
            self.assertEqual(c.execute("select value from store_kv where key='_gplans'").fetchone()[0],plans)


if __name__=='__main__': unittest.main()
