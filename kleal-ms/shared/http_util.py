# -*- coding: utf-8 -*-
# Kleal shared HTTP helpers (stdlib only) — the tiny JSON read/write boilerplate every service
# used to duplicate. No routing, no business logic. Handlers stay plain http.server subclasses.
import json


def read_json(handler):
    """Read + parse a JSON request body; returns {} on empty/invalid."""
    try:
        ln = int(handler.headers.get("Content-Length", "0") or 0)
    except (TypeError, ValueError):
        ln = 0
    raw = handler.rfile.read(ln).decode("utf-8") if ln else ""
    try:
        return json.loads(raw or "{}")
    except Exception:
        return {}


def send(handler, code, body, ctype="application/json"):
    """Write a response with the right Content-Length. `body` may be str or bytes."""
    b = body.encode("utf-8") if isinstance(body, str) else body
    handler.send_response(code)
    handler.send_header("Content-Type", ctype + "; charset=utf-8")
    handler.send_header("Content-Length", str(len(b)))
    handler.end_headers()
    handler.wfile.write(b)


def send_json(handler, code, obj):
    """Serialize `obj` to JSON and send it."""
    send(handler, code, json.dumps(obj), "application/json")
