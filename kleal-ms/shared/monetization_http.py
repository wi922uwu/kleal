"""Authenticated adapter on the existing onboarding prefix; no new gateway route."""
import json
import sqlite3
from urllib.parse import urlsplit
import kleal_auth
import monetization as billing

PREFIX = "/api/onboarding/monetization"


def respond(handler, status, data):
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Content-Length", str(len(raw)))
    handler.end_headers()
    handler.wfile.write(raw)


def handle(handler):
    path = urlsplit(handler.path).path
    if path != PREFIX and not path.startswith(PREFIX + "/"):
        return False
    # Failed auth/invalid bodies must not leave unread bytes on a reusable connection.
    handler.close_connection = True
    try:
        method = handler.command
        if (method, path) not in {
            ("GET", PREFIX + "/status"), ("POST", PREFIX + "/preview"),
            ("POST", PREFIX + "/purchase"), ("POST", PREFIX + "/restore"),
        }:
            raise billing.MonetizationError("not_found", 404)
        person = kleal_auth.caller_person(handler, strict_storage=True)
        person_id = str((person or {}).get("id") or "")
        if not person_id:
            raise billing.MonetizationError("sign_in_required", 401)
        if method == "POST":
            if handler.headers.get("Transfer-Encoding"):
                raise billing.MonetizationError("invalid_request")
            try:
                length = int(handler.headers.get("Content-Length", "0"))
            except ValueError:
                raise billing.MonetizationError("invalid_request") from None
            if not 0 < length <= 256:
                raise billing.MonetizationError("invalid_request")
            raw = handler.rfile.read(length)
            if len(raw) != length:
                raise billing.MonetizationError("invalid_request")
            body = json.loads(raw)
            if path.endswith("/preview"):
                # No client-supplied user, duration, status or price is accepted.
                if not isinstance(body, dict) or set(body) != {"consent"} or body["consent"] is not True:
                    raise billing.MonetizationError("invalid_request")
                result = billing.start_preview(person_id)
            else:
                if body != {}:
                    raise billing.MonetizationError("invalid_request")
                raise billing.MonetizationError("store_not_configured", 409)
        else:
            result = billing.status(person_id)
        respond(handler, 200, result)
    except billing.MonetizationError as error:
        respond(handler, error.status, {"ok": False, "error": error.code})
    except (ValueError, UnicodeError):
        respond(handler, 400, {"ok": False, "error": "invalid_request"})
    except (sqlite3.Error, OSError, kleal_auth.IdentityStorageUnavailable):
        respond(handler, 503, {"ok": False, "error": "monetization_unavailable"})
    return True
