"""Phase 1: server-owned, opt-in Preview. No payment processing or product gates.

Never infer paid access from a client field, a redirect, or an unverified receipt.
Store billing and product quota enforcement will be added after product approval.
"""
import os
import sqlite3
import time
from pathlib import Path

PREVIEW_SECONDS = 14 * 24 * 60 * 60
PRODUCTS = (
    {"id": "plus_monthly", "period": "month", "referencePriceCents": 1199, "currency": "EUR"},
    {"id": "plus_annual", "period": "year", "referencePriceCents": 8999, "currency": "EUR"},
)


class MonetizationError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code, self.status = code, status


def preview_enabled():
    return os.environ.get("KLEAL_MONETIZATION_PREVIEW_ENABLED") == "1"


def database_path():
    value = os.environ.get("KLEAL_MONETIZATION_DB", "")
    if not value or not Path(value).is_absolute():
        raise MonetizationError("monetization_not_configured", 503)
    return value


class PreviewStore:
    def __init__(self, path, clock=time.time):
        self.path, self.clock = str(path), clock

    def connect(self):
        # Parent directory is provisioned explicitly; never create a shared directory silently.
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE IF NOT EXISTS monetization_preview ("
                     "person_id TEXT PRIMARY KEY, started_at INTEGER NOT NULL, "
                     "expires_at INTEGER NOT NULL)")
        return conn

    def read(self, person_id):
        conn = self.connect()
        try:
            row = conn.execute("SELECT started_at, expires_at FROM monetization_preview "
                               "WHERE person_id = ?", (person_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def start(self, person_id):
        if not isinstance(person_id, str) or not person_id.strip():
            raise MonetizationError("sign_in_required", 401)
        now = int(self.clock())
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            # Unique owner + transaction: retries, reinstalls and simultaneous devices never extend it.
            conn.execute("INSERT OR IGNORE INTO monetization_preview VALUES (?, ?, ?)",
                         (person_id, now, now + PREVIEW_SECONDS))
            row = conn.execute("SELECT started_at, expires_at FROM monetization_preview "
                               "WHERE person_id = ?", (person_id,)).fetchone()
            conn.commit()
            return dict(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def describe(row=None, *, enabled=False, now=None):
    now = int(time.time() if now is None else now)
    active = bool(enabled and row and row["expires_at"] > now)
    state = "preview" if active else ("expired" if row else "free")
    return {
        "ok": True, "state": state, "plan": "plus" if active else "free",
        "source": "preview" if row else "none", "serverTime": now,
        "previewStartedAt": row["started_at"] if row else None,
        "expiresAt": row["expires_at"] if row else None,
        "canStartPreview": bool(enabled and not row), "previewEnabled": enabled,
        "previewDays": 14, "purchaseAvailable": False, "restoreAvailable": False,
        "enforcementEnabled": False, "phase": "foundation",
        # Reference prices are NOT live store prices or an offer to charge the customer.
        "products": [dict(p) for p in PRODUCTS],
    }


def status(person_id):
    if not preview_enabled():
        return describe()
    store = PreviewStore(database_path())
    return describe(store.read(person_id), enabled=True)


def start_preview(person_id):
    import monetization_store as phase2
    if phase2.mode() == 'enforce':
        raise MonetizationError('preview_starts_on_meaningful_use', 409)
    if not preview_enabled():
        raise MonetizationError("preview_unavailable", 409)
    store = PreviewStore(database_path())
    return describe(store.start(person_id), enabled=True)


def status_v2(person_id):
    import monetization_store as phase2
    if phase2.mode() == 'enforce':
        return phase2.status(person_id)
    # Off/shadow does not claim working entitlement enforcement.
    result = status(person_id)
    result['mode'] = phase2.mode()
    return result
