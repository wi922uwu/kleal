# -*- coding: utf-8 -*-
# Kleal HUB — a single entry point that puts BOTH prototype apps behind one URL:
#   /               -> a small landing with two buttons
#   /onboarding...  -> reverse-proxied to the onboarding server  (localhost:7072)
#   /profile...     -> reverse-proxied to the profile server     (localhost:7073)
#   /api/...        -> onboarding's API (the funnel chat lives here)
# The prefix is stripped before forwarding, so each backend still thinks it is served at "/".
# One cloudflared tunnel points at THIS server, so the whole demo is one link.
import os, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ONB = os.environ.get("HUB_ONB", "http://127.0.0.1:7072")
PROF = os.environ.get("HUB_PROF", "http://127.0.0.1:7073")
PORT = int(os.environ.get("HUB_PORT", "7080"))

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
    # the two-button menu is kept available at /menu (optional)
    if path == "/menu" or path.startswith("/menu?"):
        return ("LANDING", None)
    for pfx, base in (("/profile", PROF), ("/onboarding", ONB)):
        if path == pfx or path.startswith(pfx + "/") or path.startswith(pfx + "?"):
            rest = path[len(pfx):]
            if not rest.startswith("/"):
                rest = "/" + rest
            return (base, rest)
    # DEFAULT: "/", "/api/...", assets -> onboarding, so the site opens at the start of onboarding
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
            self._serve(("hub upstream error: " + str(e)).encode("utf-8"), 502, "text/plain; charset=utf-8")

    do_GET = _proxy
    do_POST = _proxy
    do_HEAD = _proxy

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Kleal HUB on http://127.0.0.1:%d  (onb=%s prof=%s)" % (PORT, ONB, PROF))
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
