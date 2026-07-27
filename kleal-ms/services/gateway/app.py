# -*- coding: utf-8 -*-
# Kleal gateway — the single public entry point (evolved from the old kleal_hub.py). It is the ONLY
# process bound to a public interface (0.0.0.0); every other service binds 127.0.0.1. One cloudflared
# tunnel points here, so the whole product is one URL. Holds NO business logic, NO keys, NO state.
#
# Routing table (ORDER MATTERS — specific API prefixes are tested before the generic "/" fallback):
#   /menu                       -> local landing (two-button page)
#   /api/buddy/*                -> buddy-service    (path unchanged)   [the conversational agent]
#   /api/filter/*               -> filtration-service (path unchanged) [the categorisation agent]
#   /api/agent/*                -> matching-service  (path unchanged)   [profile JS hard-codes these]
#   /api/onboarding/* /api/v2/* -> onboarding-service (path unchanged)  [/api/v2/* = legacy alias]
#   /profile /profile/*         -> profile-service    (strip /profile)
#   /onboarding /onboarding/*   -> onboarding-service (strip /onboarding)
#   / and everything else       -> onboarding-service (path unchanged)  [site opens at onboarding]
import os
import sys
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "..", "..", "shared"), os.path.join(_HERE, "shared")):
    if os.path.isdir(_p) and _p not in sys.path: sys.path.insert(0, _p)
import config                                  # the one topology table (ports/URLs); keyless

# Upstreams come from shared/config.py, so the gateway no longer carries its own copy of the port
# map. The old HUB_* variables still work — config.py reads them as aliases.
ONB = config.ONBOARDING_URL
PROF = config.PROFILE_URL
MATCH = config.MATCH_URL
BUDDY = config.BUDDY_URL
FILTER = config.FILTER_URL
PORT = config.PORTS["gateway"]

LANDING = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kleal</title><style>
*{box-sizing:border-box;margin:0;padding:0}
body{min-height:100vh;display:flex;align-items:center;justify-content:center;background:#F7F8FA;
 font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Inter,sans-serif;color:#181B22;padding:24px}
.wrap{width:100%;max-width:420px;text-align:center}
.logo{font-size:34px;font-weight:800;letter-spacing:-.02em;color:#F5455C;margin-bottom:6px}
.sub{color:#5A616E;margin-bottom:28px}
a.card{display:block;text-decoration:none;color:inherit;background:#fff;border:1px solid #E2E5EC;border-radius:18px;
 padding:20px 22px;margin-bottom:14px;text-align:left;transition:.15s;box-shadow:0 1px 2px rgba(20,20,40,.04)}
a.card:hover{border-color:#FECDD4;box-shadow:0 8px 24px rgba(245,69,92,.10);transform:translateY(-1px)}
.t{font-size:18px;font-weight:700;display:flex;align-items:center;justify-content:space-between}
.d{color:#5A616E;font-size:14px;margin-top:4px}
.arw{color:#F5455C;font-size:22px}
.note{color:#8A909C;font-size:12.5px;margin-top:18px}
</style></head><body><div class="wrap">
<div class="logo">kleal</div>
<div class="sub">Один вход — весь прототип</div>
<a class="card" href="/onboarding"><div class="t">Онбординг <span class="arw">→</span></div>
  <div class="d">Знакомство с агентом: чат, интересы, локация, безопасность.</div></a>
<a class="card" href="/profile"><div class="t">Мой профиль <span class="arw">→</span></div>
  <div class="d">Память агента: интересы, личность, цели, интенты, Safety & Privacy.</div></a>
<div class="note">Агент («бадди») — это чат внутри онбординга и экрана интента в профиле.</div>
</div></body></html>"""

_HOP = {"host", "content-length", "connection", "keep-alive", "transfer-encoding",
        "te", "trailer", "upgrade", "accept-encoding", "content-encoding"}


def route(path):
    """Resolve (upstream_base, forwarded_path). Order is load-bearing: API prefixes before the '/' default."""
    if path == "/menu" or path.startswith("/menu?"):
        return ("LANDING", None)
    # API prefixes — forwarded UNCHANGED so the backends keep their own paths.
    if path.startswith("/api/buddy/"):
        return (BUDDY, path)
    if path.startswith("/api/filter/"):
        return (FILTER, path)
    if path.startswith("/api/agent/"):
        return (MATCH, path)
    if path.startswith("/api/onboarding/") or path.startswith("/api/v2/"):   # /api/v2/* = legacy alias
        return (ONB, path)
    # UI apps — prefix STRIPPED so each backend still believes it is served at "/".
    for pfx, base in (("/profile", PROF), ("/onboarding", ONB)):
        if path == pfx or path.startswith(pfx + "/") or path.startswith(pfx + "?"):
            rest = path[len(pfx):]
            if not rest.startswith("/"):
                rest = "/" + rest
            return (base, rest)
    # DEFAULT: "/", assets, unknown -> onboarding, so the site opens at the start of onboarding.
    return (ONB, path)


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _serve(self, body, status=200, ctype="text/html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _proxy(self):
        base, fwd = route(self.path)
        if base == "LANDING":
            return self._serve(LANDING.encode("utf-8"))
        length = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(length) if length else None
        req = urllib.request.Request(base + fwd, data=data, method=self.command)
        for k, v in self.headers.items():
            if k.lower() not in _HOP:
                req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                # Server-sent events must be relayed as they arrive. r.read() blocks until the upstream
                # closes, which would buffer the whole generation and defeat streaming entirely — the
                # user would wait the full time and then see the text appear at once.
                if "text/event-stream" in (r.headers.get("Content-Type") or "").lower():
                    self.send_response(r.status)
                    for k, v in r.headers.items():
                        if k.lower() not in _HOP and k.lower() != "content-length":
                            self.send_header(k, v)
                    self.send_header("X-Accel-Buffering", "no")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    if self.command == "HEAD":
                        return
                    try:
                        while True:
                            chunk = r.read1(512) if hasattr(r, "read1") else r.read(512)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        pass                     # client navigated away mid-stream
                    return
                body = r.read()
                self.send_response(r.status)
                for k, v in r.headers.items():
                    if k.lower() not in _HOP:
                        self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)
        except urllib.error.HTTPError as e:
            body = e.read() or b""
            self.send_response(e.code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            self._serve(("gateway upstream error: " + str(e)).encode("utf-8"), 502, "text/plain; charset=utf-8")

    do_GET = _proxy
    do_POST = _proxy
    do_HEAD = _proxy

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Kleal gateway on http://%s:%d  (onb=%s prof=%s match=%s buddy=%s filter=%s)"
          % (config.GATEWAY_BIND_HOST, PORT, ONB, PROF, MATCH, BUDDY, FILTER))
    ThreadingHTTPServer((config.GATEWAY_BIND_HOST, PORT), H).serve_forever()
