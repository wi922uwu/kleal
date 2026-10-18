#!/usr/bin/env python3
"""Private CLI; status is read-only, mutations preview unless --apply is explicit."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shared'))
import monetization_admin as admin


def utc(value):
    date=datetime.fromisoformat(value.replace('Z','+00:00'))
    if date.utcoffset() is None or date.utcoffset().total_seconds()!=0:
        raise argparse.ArgumentTypeError('explicit UTC expiry required, e.g. 2026-11-01T00:00:00Z')
    return int(date.timestamp())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('status','grant','revoke'))
    p.add_argument('--user-id');p.add_argument('--operator');p.add_argument('--reason');p.add_argument('--key')
    p.add_argument('--expires',type=utc);p.add_argument('--grant-id');p.add_argument('--apply',action='store_true')
    a=p.parse_args()
    import psycopg
    with psycopg.connect(os.environ['KLEAL_PG_DSN']) as conn:
        if a.action=='status':
            conn.execute('set transaction isolation level repeatable read read only')
            result=admin.status(conn,a.user_id)
        else:
            if not a.user_id: p.error('--user-id required')
            result=admin.command(conn,action=a.action,owner=a.user_id,operator=a.operator,reason=a.reason,key=a.key,
                                 expires=a.expires,grant_id=a.grant_id,apply=a.apply)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
