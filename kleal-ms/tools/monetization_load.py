#!/usr/bin/env python3
"""Reproducible synthetic canonical-writer load; never connects to a live database.

Real adapter, projection, PostgreSQL transactions, quota, idempotency and outbox.
Authentication/identity/intent preparation/ranking are synthetic; this is NOT an
HTTP, model/provider or production-capacity benchmark. Each run owns a new schema.
"""
import argparse
import concurrent.futures
import copy
import json
import math
import multiprocessing
import os
from pathlib import Path
import platform
import random
import sys
import threading
import time
from types import SimpleNamespace
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'shared'), str(ROOT / 'services' / 'matching')]
import monetization_store as ms
import monetization_commands as commands
import monetization_migrate as migration
import monetization_safety as safety

LOCK_SAMPLES = []
FAIL_RENDER = False


def initialize(dsn, schema):
    import psycopg_pool
    safety.validate_test_dsn(dsn)
    os.environ['KLEAL_MONETIZATION_MODE'] = 'enforce'
    ms.db.ENABLED, ms.db.MIRROR_JSON = True, False
    ms.db._pool = psycopg_pool.ConnectionPool(
        dsn, kwargs={'options': '-c search_path=' + schema}, min_size=1, max_size=2)
    with ms.db._pool.connection() as conn: safety.guard(conn)
    def render(*_):
        if FAIL_RENDER:
            raise RuntimeError('synthetic ranking outage')
        return {'candidates': [], 'shown': 0, 'has_more': False}
    commands._app = {
        '_STORE_LOCK': threading.RLock(), 'SESSION': commands.SessionProjection({}),
        '_display': lambda owner, fallback: 'Synthetic ' + owner,
        'prepare_search': lambda path, body, ctx: copy.deepcopy(body['intent']),
        '_prepare_map_intent': lambda owner, intent, owner_id: intent,
        'render_search': render,
        'load_candidates': lambda: [],
        '_online_fallback': lambda intent: {'room':{'kind':'online_room'}},
        '_gate_ctx_and_self': lambda ctx,prof: (ctx,ctx['self']),
        '_prof_with_own_row': lambda prof,name,owner: prof,
        '_with_km': lambda pool,prof,ctx: pool,
        'ki': SimpleNamespace(normalize_for_scoring=lambda intent:intent),
        '_blocked_pair': lambda owner,peer: False,
        '_policy_decision': lambda intent,person,ctx: ('ALLOW',None),
        '_apply_policy': lambda cards,decisions: cards,
        'send_json': lambda handler, status, value: setattr(handler, 'result', (status, value)),
    }
    real_lock = ms.Transaction.lock
    def measured_lock(tx, *keys):
        start = time.perf_counter()
        try:
            return real_lock(tx, *keys)
        finally:
            if 'monetization:projection' in keys:
                LOCK_SAMPLES.append((time.perf_counter() - start) * 1000)
    ms.Transaction.lock = measured_lock


def execute(task):
    global FAIL_RENDER
    LOCK_SAMPLES.clear()
    start = time.perf_counter()
    FAIL_RENDER = task.get('pending', False)
    try:
        if task['kind'] == 'drain':
            value = {'ok': True, 'drained': commands.drain_launches(task['limit'])}
        else:
            handler = SimpleNamespace(_pid=task['owner'])
            commands.handle(handler, '/api/agent/search-command', task['body'])
            status, value = handler.result
            if status != 200:
                value = dict(value, httpStatus=status)
    except ms.CommandError as error:
        value = error.response()
    except Exception as error:
        value = {'ok': False, 'error': type(error).__name__ + ': ' + str(error)}
    return dict(task=task, result=value, pid=os.getpid(),
                ms=(time.perf_counter() - start) * 1000,
                projectionLockMs=list(LOCK_SAMPLES))


def distribution(samples):
    values = sorted(samples)
    if not values:
        return {'count': 0}
    at = lambda p: round(values[max(0, math.ceil(p * len(values)) - 1)], 3)
    return {'count': len(values), 'p50': at(.50), 'p95': at(.95), 'max': at(1)}


def batch(pool, tasks):
    start = time.perf_counter()
    rows = list(pool.map(execute, tasks, chunksize=1))
    elapsed = time.perf_counter() - start
    errors = {}
    for row in rows:
        if not row['result'].get('ok'):
            code = row['result'].get('error', 'unknown')
            errors[code] = errors.get(code, 0) + 1
    return rows, {'commands': len(rows), 'elapsedSeconds': round(elapsed, 3),
                  'commandsPerSecond': round(len(rows) / elapsed, 3),
                  'latencyMs': distribution([r['ms'] for r in rows]),
                  'projectionLockAcquisitionMs': distribution([v for r in rows for v in r['projectionLockMs']]),
                  'errors': errors, 'pids': sorted({r['pid'] for r in rows})}


def snapshot(conn):
    return {
        'activePerOwner': dict(conn.execute("select owner_id,count(*) from monetization_resources where state='active' group by owner_id").fetchall()),
        'resources': conn.execute('select count(*) from monetization_resources').fetchone()[0],
        'commands': conn.execute('select count(*) from monetization_commands').fetchone()[0],
        'previewGrants': conn.execute("select count(*) from monetization_audit where event='preview_meaningful_use'").fetchone()[0],
        'previewDurations': [r[0] for r in conn.execute('select distinct preview_end-preview_start from monetization_accounts where preview_start is not null').fetchall()],
        'outboxTotal': conn.execute('select count(*) from outbox').fetchone()[0],
        'outboxPending': conn.execute('select count(*) from outbox where sent_at is null').fetchone()[0],
        'outboxAttempts': conn.execute('select coalesce(sum(attempts),0) from outbox').fetchone()[0],
        'launchStates': dict(conn.execute('select launch_state,count(*) from monetization_resources group by launch_state').fetchall()),
    }


def run(args):
    import psycopg
    from psycopg import sql
    dsn = os.environ.get('KLEAL_MONETIZATION_TEST_DSN', '')
    parameters=safety.validate_test_dsn(dsn)
    schema = 'test_load_' + uuid.uuid4().hex
    free = ['free_' + str(i) for i in range(args.owners)]
    preview = ['preview_' + str(i) for i in range(args.owners)]
    with psycopg.connect(dsn, autocommit=True) as admin:
        safety.guard(admin,require_schema=False)
        admin.execute(sql.SQL('create schema {}').format(sql.Identifier(schema)))
        report = {'schema': schema, 'profile': vars(args), 'environment': {
            'platform': platform.platform(), 'python': platform.python_version(),
            'cpuCount': os.cpu_count(), 'postgres': admin.execute('select version()').fetchone()[0],
            'database': parameters['dbname'], 'host': parameters['host'], 'port': parameters.get('port'),
            'poolConnectionsPerProcess': 'min=1 max=2', 'transport': 'in-process canonical handle, no HTTP',
            'synthetic': 'identity, intent preparation, empty ranking; real PostgreSQL and canonical adapter'},
            'phases': {}}
        try:
            with psycopg.connect(dsn, options='-c search_path=' + schema) as conn:
                migration.migrate(conn, {'synthetic': True, 'users': [{'id': x} for x in free + preview], 'session': {}})
                conn.execute('update monetization_accounts set eligible=false where owner_id=any(%s)', (free,))
            task = lambda owner, key, **extra: dict(kind='search', owner=owner, body={
                'commandId': key, 'intent': {'title': key, 'mode': 'hybrid', 'topics': ['coffee']}}, **extra)
            tasks = [task(owner, owner + '-' + str(i)) for owner in free + preview for i in range(args.attempts)]
            random.Random(args.seed).shuffle(tasks)
            with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers,
                    mp_context=multiprocessing.get_context('spawn'), initializer=initialize,
                    initargs=(dsn, schema)) as pool:
                # Initialize processes before measuring workload latency/throughput.
                list(pool.map(execute, [{'kind': 'drain', 'limit': 1}] * args.workers))
                rows, report['phases']['contendedPublish'] = batch(pool, tasks)
                assert report['phases']['contendedPublish']['errors'] == {'search_quota': args.owners * (args.attempts - 1)}
                winners = {}
                for row in rows:
                    if row['result'].get('ok'):
                        assert row['result']['launchState'] == 'ready', row
                        winners.setdefault(row['task']['owner'], row)
                assert len(winners) == len(free + preview)
                replay_tasks = [winners[owner]['task'] for owner in free + preview]
                replay, report['phases']['replay'] = batch(pool, replay_tasks)
                for row in replay:
                    assert row['result'] == winners[row['task']['owner']]['result'], row
                pending, report['phases']['rankingOutage'] = batch(pool, [task(owner, owner + '-outage', pending=True) for owner in preview])
                assert all(r['result'].get('ok') and r['result']['launchState'] == 'pending' for r in pending)
                with psycopg.connect(dsn, options='-c search_path=' + schema) as conn:
                    report['beforeDrain'] = snapshot(conn)
                assert report['beforeDrain']['outboxPending'] == args.owners
                recovered, report['phases']['recovery'] = batch(pool, [{'kind': 'drain', 'limit': args.owners * 2}])
                assert recovered[0]['result']['drained'] == args.owners
            with psycopg.connect(dsn, options='-c search_path=' + schema) as conn:
                final = report['afterDrain'] = snapshot(conn)
            expected = args.owners * (args.attempts + 2)
            assert final['activePerOwner'] == {**{o: 1 for o in free}, **{o: args.attempts + 1 for o in preview}}
            assert final['resources'] == final['commands'] == final['outboxTotal'] == expected
            assert final['previewGrants'] == args.owners and final['previewDurations'] == [1209600]
            assert final['outboxPending'] == final['outboxAttempts'] == 0
            assert final['launchStates'] == {'ready': expected}
            report['invariants'] = 'PASS: free <=1, exact preview duration/grant, replay equality/no duplicate resources, pending durable/recovered, queue empty'
            report['unexpectedErrors'] = 0
        finally:
            # Only the exact schema created above; existing test/native data is untouched.
            admin.execute(sql.SQL('drop schema {} cascade').format(sql.Identifier(schema)))
            report['cleanupConfirmed'] = admin.execute('select count(*) from information_schema.schemata where schema_name=%s', (schema,)).fetchone()[0] == 0
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--owners', type=int, default=8, help='owners per cohort (free and preview)')
    parser.add_argument('--attempts', type=int, default=4, help='independent publications per owner')
    parser.add_argument('--seed', type=int, default=20261012)
    args = parser.parse_args()
    if not (1 <= args.workers <= 32 and 1 <= args.owners <= 100 and 2 <= args.attempts <= 20):
        parser.error('bounded synthetic profile required: workers 1..32, owners 1..100, attempts 2..20')
    run(args)
