import concurrent.futures
import json
import unittest
import test_monetization_pg as pg
from test_monetization_pg import ms,DSN
import monetization_admin as admin


@unittest.skipUnless(DSN,'BLOCKED: isolated PostgreSQL DSN not configured')
class Admin(unittest.TestCase):
    setUpClass=classmethod(pg.PostgreSQLCommands.setUpClass.__func__)
    tearDown=pg.PostgreSQLCommands.tearDown

    def setUp(self):
        pg.PostgreSQLCommands.setUp(self)
        with ms.connection() as c:
            for owner in ('a','b','c','d','new-user'):
                c.execute('insert into users(id,name_key,name,row) values(%s,%s,%s,%s)',
                          (owner,owner,'Same name',json.dumps({'id':owner})))
            self.now=ms.Transaction(c).now

    def grant(self,key='manual',owner='a',expires=None,apply=True):
        with ms.connection() as c:
            return admin.command(c,action='grant',owner=owner,expires=expires or self.now+3600,
                                 operator='operator-id',reason='synthetic test',key=key,apply=apply)

    def revoke(self,grant,key='revoke',owner='a'):
        with ms.connection() as c:
            return admin.command(c,action='revoke',owner=owner,grant_id=grant,operator='operator-id',
                                 reason='synthetic revoke',key=key,apply=True)

    def test_read_only_all_users_and_preview_no_writes(self):
        with ms.connection() as c:
            c.execute('set transaction read only')
            states=admin.status(c)
            self.assertEqual(len(states),5)
            self.assertFalse(c.execute("select 1 from monetization_accounts where owner_id='new-user'").fetchone())
        self.assertTrue(self.grant(apply=False)['dryRun'])
        with ms.connection() as c:
            self.assertEqual(c.execute('select count(*) from monetization_manual_grants').fetchone()[0],0)
            self.assertEqual(c.execute('select count(*) from monetization_admin_commands').fetchone()[0],0)

    def test_exact_id_expiry_required_and_deletion_barrier(self):
        for owner in ('missing','Same name','anon:old'):
            with self.assertRaises(ms.CommandError): self.grant(owner=owner)
        for expiry in (self.now-1,True,1.1):
            with self.assertRaises(ms.CommandError): self.grant(expires=expiry)
        self.grant()
        with ms.connection() as c: admin.begin_delete(c,'a')
        with self.assertRaises(ms.CommandError): self.grant('new')
        with self.assertRaises(ms.CommandError): ms.status('a')
        with ms.connection() as c:
            self.assertEqual(admin.status(c,'a')['plan'],'free')
            self.assertEqual(c.execute('select count(*) from monetization_manual_grants').fetchone()[0],0)
            self.assertEqual(c.execute('select count(*) from monetization_admin_commands').fetchone()[0],0)
            self.assertEqual(c.execute('select count(*) from monetization_admin_audit').fetchone()[0],0)

    def test_idempotency_conflict_concurrent_and_atomic_audit(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            one,two=list(pool.map(lambda _:self.grant(),range(2)))
        self.assertEqual(one,two)
        with self.assertRaises(ms.CommandError): self.grant(owner='b')
        with ms.connection() as c:
            self.assertEqual(c.execute('select count(*) from monetization_manual_grants').fetchone()[0],1)
            self.assertEqual(c.execute('select count(*) from monetization_admin_audit').fetchone()[0],1)
        try:
            with ms.connection() as c:
                admin.command(c,action='grant',owner='b',expires=self.now+3600,operator='op',reason='rollback',key='rollback',apply=True)
                raise ValueError('transaction failure')
        except ValueError: pass
        with ms.connection() as c: self.assertEqual(admin.status(c,'b')['grants'],[])

    def test_mixed_sources_revoke_specific_and_no_preview_reset(self):
        with ms.transaction() as t:
            t.grant('a',{'test':True})
            t.conn.execute('update monetization_accounts set plus_until=%s where owner_id=%s',(self.now+7200,'a'))
        one=self.grant()['grantId'];two=self.grant('two',expires=self.now+1800)['grantId']
        status=ms.status('a')
        self.assertEqual({x['source'] for x in status['entitlementSources']},{'preview','manual','paid'})
        preview=status['expiresAt']
        self.revoke(one)
        status=ms.status('a');self.assertEqual(status['expiresAt'],preview)
        self.assertEqual(next(s['expiresAt'] for s in status['entitlementSources'] if s['source']=='manual'),self.now+1800)
        with self.assertRaises(ms.CommandError): self.revoke(two,'foreign','b')
        self.revoke(two,'two-revoke')
        self.assertEqual({x['source'] for x in ms.status('a')['entitlementSources']},{'preview','paid'})

    def test_last_expiry_downgrades_without_automatic_resume(self):
        with ms.transaction() as t: t.conn.execute("update monetization_accounts set eligible=false where owner_id='a'")
        grant=self.grant()['grantId']
        with ms.transaction() as t:
            one=t.publish('a',{'title':'one'},rid=None);two=t.publish('a',{'title':'two'})
            t.conn.execute("update monetization_accounts set keep_search=%s where owner_id='a'",(one,))
        self.revoke(grant)
        self.assertEqual(ms.status('a')['blockerIds']['searches'],[one])
        self.grant('again')
        self.assertEqual(ms.status('a')['blockerIds']['searches'],[one])
        with ms.connection() as c:
            c.execute('update monetization_manual_grants set created=%s,expires=%s where revoked is null',(self.now-10,self.now-1))
        self.assertEqual(ms.status('a')['plan'],'free')


if __name__=='__main__': unittest.main()
