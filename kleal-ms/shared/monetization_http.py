"""Authenticated adapter on the existing onboarding prefix; no new gateway route."""
import json
import sqlite3
from urllib.parse import urlsplit
import kleal_auth
import monetization as billing
import monetization_store as phase2

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
            ("GET", PREFIX + "/v2/status"), ("POST", PREFIX + "/v2/notice"),
            ("POST", PREFIX + "/v2/keep-search"),
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
            if not 0 < length <= 1024:
                raise billing.MonetizationError("invalid_request")
            raw = handler.rfile.read(length)
            if len(raw) != length:
                raise billing.MonetizationError("invalid_request")
            body = json.loads(raw)
            if path.endswith('/v2/notice') or path.endswith('/v2/keep-search'):
                if phase2.mode() != 'enforce':
                    raise billing.MonetizationError('phase2_not_enabled',409)
                allowed={'commandId'} if path.endswith('/notice') else {'commandId','searchId'}
                if not isinstance(body,dict) or set(body)!=allowed or not isinstance(body.get('commandId'),str) or not 0<len(body['commandId'])<=160:
                    raise billing.MonetizationError('invalid_request')
                def command(tx):
                    tx.expire(person_id)
                    account=tx.account(person_id)
                    if path.endswith('/notice'):
                        if account['start'] is None:
                            raise phase2.CommandError('preview_notice_not_available',409)
                        tx.conn.execute('update monetization_accounts set notice_seen=true where owner_id=%s',(person_id,))
                    else:
                        if not isinstance(body.get('searchId'),str) or not body['searchId']:
                            raise phase2.CommandError('invalid_request',400)
                        resource=tx.resource(body['searchId'],person_id)
                        if resource['state']!='active':
                            raise phase2.CommandError('keeper_search_not_active',409)
                        if not tx.plus(person_id):
                            raise phase2.CommandError('plus_not_active',409)
                        tx.conn.execute('update monetization_accounts set keep_search=%s where owner_id=%s',
                                        (body['searchId'],person_id))
                    return tx.status(person_id)
                result = phase2.execute(person_id,path,body['commandId'],body,command,projection=True)
            elif path.endswith("/preview"):
                # No client-supplied user, duration, status or price is accepted.
                if not isinstance(body, dict) or set(body) != {"consent"} or body["consent"] is not True:
                    raise billing.MonetizationError("invalid_request")
                result = billing.start_preview(person_id)
            else:
                if body != {}:
                    raise billing.MonetizationError("invalid_request")
                raise billing.MonetizationError("store_not_configured", 409)
        else:
            result = billing.status_v2(person_id) if path.endswith('/v2/status') else billing.status(person_id)
        respond(handler, 200, result)
    except billing.MonetizationError as error:
        respond(handler, error.status, {"ok": False, "error": error.code})
    except phase2.CommandError as error:
        respond(handler,error.status,error.response())
    except (ValueError, UnicodeError):
        respond(handler, 400, {"ok": False, "error": "invalid_request"})
    except (sqlite3.Error, OSError, kleal_auth.IdentityStorageUnavailable):
        respond(handler, 503, {"ok": False, "error": "monetization_unavailable"})
    return True
