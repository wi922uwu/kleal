"""Fresh partner identity migration stays inside the real canonical writer."""
import copy
import unittest
from unittest.mock import patch

import test_monetization_phase2 as phase
import test_monetization_pg as pg
import test_monetization_review2 as review2
from test_monetization_pg import DSN, ms


@unittest.skipUnless(DSN, 'BLOCKED: isolated PostgreSQL DSN not configured')
class PartnerCurrent(unittest.TestCase):
    setUpClass = classmethod(pg.PostgreSQLCommands.setUpClass.__func__)
    setUp = phase.LegacyAdapters.setUp
    tearDown = phase.LegacyAdapters.tearDown
    tearDownDB = pg.PostgreSQLCommands.tearDown
    server = review2.ReviewTwo.server
    request = review2.ReviewTwo.request

    def test_feedback_and_outcomes_keep_equal_display_names_separate_by_id(self):
        with self.server() as (server, _):
            for peer, decision, stage in [('b', 'reject', 'accepted'), ('c', 'accept', 'completed')]:
                for route, fields in [('feedback', {'decision': decision}), ('outcome', {'stage': stage})]:
                    body = dict(id=peer, name='Same name', commandId=route+peer, **fields)
                    first = self.request(server, '/api/agent/'+route, body)
                    self.assertEqual(first[0], 200, first)
                    self.assertTrue(first[1]['ok'], first)
                    self.assertEqual(self.request(server, '/api/agent/'+route, body), first)
        with ms.transaction() as tx:
            doc = tx.documents()
            self.assertEqual(doc['a']['feedback'], {'b': 'rejected', 'c': 'accepted'})
            self.assertEqual([(r['name'], r['stage']) for r in doc['_outcomes']],
                             [('b', 'accepted'), ('c', 'completed')])
            self.assertEqual(set(doc['_matches']), {'b', 'c'})

    def test_keyless_decisions_are_new_commands_but_explicit_retries_do_not_reapply(self):
        with self.server() as (server, _):
            for decision in ('reject', 'accept', 'reject'):
                result = self.request(server, '/api/agent/feedback',
                                      {'id': 'b', 'name': 'Same name', 'decision': decision})
                self.assertEqual(result[0], 200, result)
            with ms.transaction() as tx:
                self.assertEqual(tx.documents()['a']['feedback'], {'b': 'rejected'})
                self.assertEqual(tx.conn.execute('select count(*) from monetization_commands').fetchone()[0], 3)
            for alias in ('commandId', 'idempotency_key'):
                reject = {'id': 'b', 'name': 'Same name', 'decision': 'reject', alias: alias+'reject'}
                accepted = dict(reject, decision='accept', **{alias: alias+'accept'})
                first = self.request(server, '/api/agent/feedback', reject)
                self.assertEqual(self.request(server, '/api/agent/feedback', accepted)[0], 200)
                self.assertEqual(self.request(server, '/api/agent/feedback', reject), first)
                body = {'id': 'b', 'name': 'Same name', 'stage': 'accepted', alias: alias+'outcome'}
                outcome = self.request(server, '/api/agent/outcome', body)
                self.assertEqual(self.request(server, '/api/agent/outcome', body), outcome)
                with ms.transaction() as tx:
                    self.assertEqual(tx.documents()['a']['feedback'], {'b': 'accepted'})
            with ms.transaction() as tx:
                self.assertEqual(len(tx.documents()['_outcomes']), 2)

    def test_repick_policy_denial_commits_only_safe_fields_and_replays(self):
        with ms.transaction() as tx:
            doc = tx.documents()
            doc['_requests'] = [dict(id='pick-'+peer, **{'from': 'a', 'to': peer}, status='answered',
                                    iid='same', intent={'title': 'same'}, updated=1, version=1)
                                for peer in ('b', 'c')]
            doc['_reports'] = []
            tx.save_documents(doc)
        self.assertTrue(self.app.pick_request('pick-b', 'a', 'first-pick')['ok'])
        with ms.transaction() as tx:
            doc = tx.documents()
            doc['_mplans'] = [{'id': 'cancelled', 'host': 'a', 'guest': 'b',
                              'state': 'cancelled', 'updated': tx.now+1}]
            tx.save_documents(doc)
            before = copy.deepcopy(doc)
            self.assertEqual(doc['_requests'][1]['status'], 'not_picked')
            self.assertEqual(doc['_requests'][1]['trace']['reason'], 'picked_other')
            sessions = tx.conn.execute('select count(*) from monetization_sessions').fetchone()[0]
        def deny(*args):
            # A known denial must not authorize unrelated legacy partial mutations.
            self.app.SESSION['_reports'].append({'text': 'must roll back'})
            self.app.SESSION['_requests'][1]['intent']['title'] = 'must roll back'
            return False, 'synthetic changed policy'
        with patch.object(self.app, '_policy_ok_now', side_effect=deny), self.server() as (server, _):
            body = {'id': 'pick-c', 'idem': 'repick-denial'}
            first = self.request(server, '/api/agent/request-pick', body)
            self.assertEqual((first[0], first[1]['error']), (409, 'POLICY_CHANGED'))
            self.assertEqual(self.request(server, '/api/agent/request-pick', body), first)
        with ms.transaction() as tx:
            doc = tx.documents()
            request = doc['_requests'][1]
            self.assertEqual(request['status'], 'policy_revoked')
            self.assertGreater(request['version'], before['_requests'][1]['version'])
            self.assertEqual(request['intent'], before['_requests'][1]['intent'])
            self.assertEqual(doc['_requests'][0], before['_requests'][0])
            self.assertEqual(doc['_reports'], before['_reports'])
            self.assertEqual(doc['_mplans'], before['_mplans'])
            self.assertIsNone(tx.account('c')['start'])
            self.assertEqual(tx.conn.execute('select count(*) from monetization_sessions').fetchone()[0], sessions)
        # Not every not_picked row is a supported repick: only picked_other is.
        adapter = self.app.monetization_commands
        invalid = copy.deepcopy(before)
        invalid['_requests'][1]['trace']['reason'] = 'unrelated_terminal'
        after = copy.deepcopy(invalid);after['_requests'][1]['status'] = 'policy_revoked'
        self.assertIsNone(adapter.terminal_denial(invalid, after, 'pick_request', {'rid': 'pick-c'},
                                               {'error': 'POLICY_CHANGED'}))

    def test_engine_identity_migration_is_atomic_and_survives_projection_refresh(self):
        users = copy.deepcopy(self.app.load_candidates())
        users[1]['name'] = 'Unique B'
        self.app.load_candidates = lambda: users
        self.app._load_pool_rows = lambda: users
        self.app._people_index(force=True)
        with ms.transaction() as tx:
            doc = tx.documents()
            doc.update(_identity={'v': 2}, _exposure={'Unique B': [12], 'Same name': [13]},
                       _messages=[{'id': 'history', 'from': 'a', 'to': 'b', 'text': 'keep'}])
            tx.save_documents(doc)
            before = copy.deepcopy(doc)
        with patch.object(ms.Transaction, 'save_documents', side_effect=RuntimeError('synthetic write failure')):
            with self.assertRaises(ms.CommandError):
                self.app._migrate_engine_ids_v3(apply=True)
        with ms.transaction() as tx:
            self.assertEqual(tx.documents(), before)
        result = self.app._migrate_engine_ids_v3(apply=True)
        self.assertTrue(result['applied'])
        with ms.transaction() as tx:
            migrated = tx.documents()
            self.assertEqual(migrated['_exposure'], {'b': [12]})
            self.assertEqual(migrated['_messages'], before['_messages'])
            self.assertEqual(migrated['_premig_v3']['_exposure'], before['_exposure'])
            self.assertEqual(migrated['_identity']['engine_v'], 3)
            self.assertEqual(tx.conn.execute('select count(*) from monetization_commands').fetchone()[0], 0)
        self.app.monetization_commands.refresh()
        self.assertEqual(self.app.SESSION['_exposure'], {'b': [12]})
        self.assertTrue(self.app._migrate_engine_ids_v3(apply=True)['skipped'])
        with ms.transaction() as tx:
            self.assertEqual(tx.documents(), migrated)


if __name__ == '__main__':
    unittest.main()
