"""Wire-only native fixture regression; no simulator or production auth claim."""
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest

import test_monetization_pg as pg


@unittest.skipUnless(pg.DSN,'BLOCKED: isolated PostgreSQL DSN not configured')
class NativeFixtureWire(unittest.TestCase):
    def test_smoke_keeps_bearer_identity_and_drops_only_its_schema(self):
        pg.safety.validate_test_dsn(pg.DSN)
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run([sys.executable,str(root/'tools/monetization_native_fixture.py'),'--smoke','--port','0'],
                              env=os.environ.copy(),capture_output=True,text=True,timeout=45)
        output=result.stdout+result.stderr
        created=re.findall(r'schema=(test_[0-9a-f]{32})',output)
        self.assertEqual(len(created),1,output)
        self.assertIn('Dropped disposable schema '+created[0],output)
        import psycopg
        with psycopg.connect(pg.DSN) as conn:
            pg.safety.guard(conn,require_schema=False)
            self.assertIsNone(conn.execute('select 1 from pg_namespace where nspname=%s',(created[0],)).fetchone())
        self.assertEqual(result.returncode,0,output)
        self.assertIn('PASS: synthetic profile/session bearer identity, explicit OTP login, missing/unknown/expired bearer denied',output)
        self.assertIn('PASS: loopback wire fixture only; native UI NOT tested',output)


if __name__=='__main__': unittest.main()
