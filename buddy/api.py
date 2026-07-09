"""Buddy HTTP API (stdlib http.server).

Serves the Kleal app interface (buddy/web) plus the JSON API. Onboarding lives in
kleal_v2; this app opens after it, receiving the profile via ?p= (see web/state.js).

  GET  /                      -> web/index.html  (tab-bar app interface)
  GET  /<asset>               -> static file from buddy/web (css/js), typed
  GET  /buddy/health
  POST /buddy/onboard  {user_id, profile}  -> persist profile + return LLM summary
  POST /buddy/chat     {user_id, message}  -> {reply, intent, matches, tool_call}
Auth: optional Bearer BUDDY_API_KEY (checked only when the env var is set).
"""
import os
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import agent
from . import llm
from . import prompts
from .store import Store

PORT = int(os.environ.get("BUDDY_PORT", "8090"))
API_KEY = os.environ.get("BUDDY_API_KEY", "")
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

# module-level so a launcher can seed it before serve()
store = Store()

_CT = {".html": "text/html", ".css": "text/css", ".js": "application/javascript",
       ".svg": "image/svg+xml", ".json": "application/json", ".ico": "image/x-icon",
       ".png": "image/png", ".webmanifest": "application/manifest+json"}
_TEXTY = {".html", ".css", ".js", ".svg", ".json", ".webmanifest"}


def _authed(handler):
    if not API_KEY:
        return True
    return handler.headers.get("Authorization", "") == "Bearer " + API_KEY


def _onboard(user_id, profile):
    """Persist the onboarding profile to the matching store and return an LLM summary.

    Client fields are flattened into the store schema so Buddy can score real users
    against each other; the full client object is kept in signals.onboarding."""
    interests = [it.get("name") for it in (profile.get("interests") or []) if isinstance(it, dict) and it.get("name")]
    store.upsert_profile(
        user_id,
        name=(profile.get("name") or "").strip(),
        city=(profile.get("city") or "").strip(),
        languages=profile.get("languages") or [],
        interests=interests,
        dating_enabled=0,
        signals={"onboarding": profile},
    )
    try:
        msg = llm.chat(prompts.summary_messages(profile), temperature=0.4, max_tokens=220)
        return (msg.get("content") or "").strip()
    except Exception:
        return ""  # client falls back to its own summary line


class Handler(BaseHTTPRequestHandler):
    # ---- helpers ---------------------------------------------------------
    def _json(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _static(self, name):
        name = os.path.basename(name) or "index.html"  # basename blocks path traversal
        path = os.path.join(WEB_DIR, name)
        if not os.path.isfile(path):
            self._json(404, {"error": "not found"})
            return
        ext = os.path.splitext(name)[1].lower()
        ct = _CT.get(ext, "application/octet-stream")
        if ext in _TEXTY:
            ct += "; charset=utf-8"
        with open(path, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        ln = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(ln).decode("utf-8") or "{}")

    # ---- routes ----------------------------------------------------------
    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/buddy/health":
            self._json(200, {"status": "ok", "model": llm.LLM_MODEL, "tool_mode": llm.TOOL_MODE})
        elif p == "/":
            self._static("index.html")
        elif p.startswith("/buddy"):
            self._json(404, {"error": "not found"})
        else:
            self._static(p.lstrip("/"))

    def do_POST(self):
        if self.path not in ("/buddy/chat", "/buddy/onboard"):
            self._json(404, {"error": "not found"})
            return
        if not _authed(self):
            self._json(401, {"error": "unauthorized"})
            return
        try:
            body = self._body()
        except Exception:
            self._json(400, {"error": "bad json"})
            return
        user_id = (body.get("user_id") or "").strip()
        if not user_id:
            self._json(400, {"error": "user_id is required"})
            return
        try:
            if self.path == "/buddy/onboard":
                self._json(200, {"summary": _onboard(user_id, body.get("profile") or {})})
            else:  # /buddy/chat
                message = (body.get("message") or "").strip()
                if not message:
                    self._json(400, {"error": "message is required"})
                    return
                self._json(200, agent.handle_message(user_id, message, store))
        except Exception as e:
            self._json(502, {"error": str(e)})

    def log_message(self, *a):
        pass


def serve():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("Buddy API on :%d · model=%s · tool_mode=%s · db=%s · web=%s"
          % (PORT, llm.LLM_MODEL, llm.TOOL_MODE, store.db_path, WEB_DIR))
    srv.serve_forever()


if __name__ == "__main__":
    serve()
