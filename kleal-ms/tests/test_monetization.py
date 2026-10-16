"""Offline billing-foundation checks. All state is temporary; no provider calls."""
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "shared"))
import monetization as M
import monetization_http as H
import kleal_auth
from serving import KlealServer

sys.path.insert(0, str(ROOT / "services" / "onboarding"))
spec = importlib.util.spec_from_file_location("monetization_onboarding_under_test", ROOT / "services" / "onboarding" / "app.py")
ONB = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ONB)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / "preview.sqlite3")
        self.now = 1000
        self.store = M.PreviewStore(self.path, lambda: self.now)

    def test_exact_expiry_and_no_restart(self):
        first = self.store.start("one")
        self.assertEqual(first, {"started_at": 1000, "expires_at": 1000 + 14 * 86400})
        self.now = first["expires_at"]
        self.assertEqual(M.describe(first, enabled=True, now=self.now - 1)["state"], "preview")
        expired = M.describe(first, enabled=True, now=self.now)
        self.assertEqual((expired["state"], expired["plan"], expired["canStartPreview"]), ("expired", "free", False))
        self.assertEqual(self.store.start("one"), first)
        self.assertEqual(M.PreviewStore(self.path).read("one"), first)

    def test_simultaneous_devices_create_one_period(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(lambda n: M.PreviewStore(self.path, lambda: 1000 + n).start("one"), range(16)))
        self.assertTrue(all(row == rows[0] for row in rows))
        self.assertEqual(self.store.read("one"), rows[0])

    def test_users_are_isolated_and_sql_is_parameterized(self):
        self.store.start("one")
        self.now += 60
        two = self.store.start("two' OR 1=1;--")
        self.assertEqual(two["started_at"], 1060)
        self.assertEqual(self.store.read("one")["started_at"], 1000)
        self.assertIsNone(self.store.read("missing"))

    def test_flag_off_does_not_touch_storage(self):
        with patch.dict(os.environ, {"KLEAL_MONETIZATION_PREVIEW_ENABLED": "0", "KLEAL_MONETIZATION_DB": self.path}):
            result = M.status("one")
            self.assertEqual((result["state"], result["canStartPreview"]), ("free", False))
            with self.assertRaisesRegex(M.MonetizationError, "preview_unavailable"):
                M.start_preview("one")
        self.assertFalse(Path(self.path).exists())

    def test_configuration_must_be_explicit_and_absolute(self):
        for value in ("", "relative.sqlite3"):
            with patch.dict(os.environ, {"KLEAL_MONETIZATION_DB": value}):
                with self.assertRaisesRegex(M.MonetizationError, "monetization_not_configured"):
                    M.database_path()

    def test_no_paid_access_or_enforcement(self):
        for row in (None, self.store.start("one")):
            result = M.describe(row, enabled=True, now=1001)
            for key in ("purchaseAvailable", "restoreAvailable", "enforcementEnabled"):
                self.assertIs(result[key], False)
            self.assertEqual([p["referencePriceCents"] for p in result["products"]], [1199, 8999])
            result["products"][0]["referencePriceCents"] = 1
            self.assertEqual(M.PRODUCTS[0]["referencePriceCents"], 1199)

    def test_owner_required(self):
        for person in (None, "", " ", 123):
            with self.assertRaises(M.MonetizationError):
                self.store.start(person)


class Handler(ONB.H):
    # Real onboarding GET/POST dispatch and the production server wrapper, quiet local logs.
    def log_message(self, *_args):
        pass


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / "preview.sqlite3")
        env = patch.dict(os.environ, {"KLEAL_MONETIZATION_DB": self.path, "KLEAL_MONETIZATION_PREVIEW_ENABLED": "1"})
        env.start()
        self.addCleanup(env.stop)
        accounts = {}
        for token, expiry in (("alice", time.time() + 3600), ("bob", time.time() + 3600), ("expired", 1)):
            accounts[token] = {"person_id": "id_" + token, "sessions": {hashlib.sha256(token.encode()).hexdigest(): {"exp": expiry}}}
        # The real bearer -> hashed session -> stable user resolver runs against synthetic stores.
        for mock in (patch.object(kleal_auth, "_accounts", return_value=accounts),
                     patch.object(kleal_auth, "_population", return_value=[
                         {"id": "id_" + token, "owner": token, "name": "Same name"} for token in accounts])):
            mock.start()
            self.addCleanup(mock.stop)
        self.server = KlealServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method="GET", path="/status", body=None, token="alice", headers=None):
        hdr = {"Content-Type": "application/json"}
        if token:
            hdr["Authorization"] = "Bearer " + token
        hdr.update(headers or {})
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        try:
            conn.request(method, H.PREFIX + path, body, hdr)
            reply = conn.getresponse()
            return reply.status, json.loads(reply.read()), dict(reply.getheaders())
        finally:
            conn.close()

    def test_complete_lifecycle_without_payments(self):
        status, data, headers = self.request()
        self.assertEqual(status, 200)
        self.assertEqual((data["state"], data["canStartPreview"]), ("free", True))
        self.assertEqual(headers["Cache-Control"], "no-store")
        status, first, _ = self.request("POST", "/preview", '{"consent":true}')
        self.assertEqual((status, first["state"]), (200, "preview"))
        _, again, _ = self.request("POST", "/preview", '{"consent":true}')
        self.assertEqual(first["expiresAt"], again["expiresAt"])
        self.assertEqual(self.request()[1]["state"], "preview")
        self.assertEqual(self.request(token="bob")[1]["state"], "free")

    def test_missing_bad_and_expired_auth(self):
        for token in (None, "unknown", "expired"):
            for method, path, body in (("GET", "/status", None), ("POST", "/preview", '{"consent":true}')):
                with self.subTest(token=token, method=method):
                    self.assertEqual(self.request(method, path, body, token)[0], 401)
        self.assertFalse(Path(self.path).exists())

    def test_cannot_forge_identity_or_duration(self):
        for body in ('{"consent":true,"person_id":"id_bob"}', '{"consent":true,"days":999}',
                     '{"consent":true,"plan":"plus"}', '{"consent":false}', '{"consent":1}',
                     '{}', '[]', 'null', 'not json', '', '{"consent":"true"}', 'x' * 257):
            with self.subTest(body=body):
                self.assertEqual(self.request("POST", "/preview", body)[0], 400)
        self.assertFalse(Path(self.path).exists())

    def test_fake_receipts_cannot_grant_paid_access(self):
        for path in ("/purchase", "/restore"):
            self.assertEqual(self.request("POST", path, '{}')[:2], (409, {"ok": False, "error": "store_not_configured"}))
            self.assertEqual(self.request("POST", path, '{"receipt":"fake"}')[0], 400)
        self.assertFalse(Path(self.path).exists())

    def test_query_cannot_change_owner(self):
        self.request("POST", "/preview?person_id=id_bob", '{"consent":true}')
        self.assertEqual(self.request(token="alice")[1]["state"], "preview")
        self.assertEqual(self.request(token="bob")[1]["state"], "free")

    def test_unknown_paths_and_methods(self):
        self.assertEqual(self.request("GET", "/preview")[0], 404)
        self.assertEqual(self.request("POST", "/status", '{}')[0], 404)
        self.assertEqual(self.request("GET", "/fake")[0], 404)

    def test_storage_failure_is_sanitized(self):
        with patch.object(M, "database_path", return_value="/nonexistent-mon-test/preview.sqlite3"):
            self.assertEqual(self.request()[:2], (503, {"ok": False, "error": "monetization_unavailable"}))
        with patch.object(kleal_auth, "_population", side_effect=kleal_auth.IdentityStorageUnavailable()):
            self.assertEqual(self.request()[0], 503)

    def test_flag_off_status_available_but_start_disabled(self):
        with patch.dict(os.environ, {"KLEAL_MONETIZATION_PREVIEW_ENABLED": "0"}):
            self.assertEqual(self.request()[1]["canStartPreview"], False)
            self.assertEqual(self.request("POST", "/preview", '{"consent":true}')[0], 409)
        self.assertFalse(Path(self.path).exists())


if __name__ == "__main__":
    unittest.main()
