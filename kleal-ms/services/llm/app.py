# -*- coding: utf-8 -*-
# Kleal llm-service — the SINGLE service that holds model base-URLs + API keys. It exposes a tiny,
# keyless HTTP completion API so onboarding-service and matching-service never see secrets:
#     POST /llm/complete  {model, messages, temperature}  -> {content}
#     GET  /llm/models    -> [{id, label, info}]
# Config comes from env only (AITUNNEL_KEY / AITUNNEL_BASE / SELF_BASE / SELF_KEY). See .env.example.
# Owner: Dev A. This is the ONLY place `Authorization: Bearer <key>` is ever set.
import os
import json
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("LLM_PORT", "7071"))

AITUNNEL_KEY = os.environ.get("AITUNNEL_KEY", "")   # set your own key in the env / .env
AITUNNEL_BASE = os.environ.get("AITUNNEL_BASE", "https://api.aitunnel.ru/v1")
SELF_BASE = os.environ.get("SELF_BASE", os.environ.get("ALIA_BASE", "http://localhost:8002/v1"))
SELF_KEY = os.environ.get("SELF_KEY", "x")


def _a(label, model, info):
    return {"label": label, "base": AITUNNEL_BASE, "key": AITUNNEL_KEY, "model": model, "info": info}


def _self(label, model, info):
    return {"label": label, "base": SELF_BASE, "key": SELF_KEY, "model": model, "info": info}


# Model registry. `llama_self` is the self-hosted vLLM on our pod (:8002) — the default prod path.
MODELS = {
    "qwen3_30b":  _a("Qwen3-30B-A3B", "qwen3-30b-a3b",
                     "Qwen3 30B MoE (3B active) · Apache 2.0 · fast (~5s), excellent multilingual."),
    "mistral32":  _a("Mistral-Small-3.2-24B", "mistral-small-3.2-24b-instruct",
                     "Mistral Small 3.2 24B · Apache 2.0 · domain-tuned, fast (~2s)."),
    "gptoss120":  _a("GPT-OSS-120B", "gpt-oss-120b",
                     "OpenAI GPT-OSS 120B · Apache 2.0 · powerful and open (~7s)."),
    "qwen35_35b": _a("Qwen3.5-35B-A3B", "qwen3.5-35b-a3b",
                     "Qwen3.5 35B MoE · Apache 2.0 · strong multilingual. Slower (~20s)."),
    "llama70":    _a("Llama-3.3-70B", "llama-3.3-70b-instruct",
                     "Llama 3.3 70B · Llama Community license · top quality (~3s)."),
    "glm46":      _a("GLM-4.6", "glm-4.6",
                     "Zhipu GLM-4.6 · MIT license · large MoE, very competitive. Slow (~35s)."),
    "llama_self": _self("Llama-3.3-70B (self-hosted)", "llama-3.3-70b",
                     "Llama 3.3 70B Instruct, AWQ int4 · SELF-HOSTED on our A100-80GB via vLLM — the prod path (~3-6s)."),
}


def call_llm(cfg, messages, temperature=0.7):
    payload = {"model": cfg["model"], "messages": messages, "max_tokens": 2500, "temperature": temperature}
    headers = {"Content-Type": "application/json"}
    if cfg.get("key"):
        headers["Authorization"] = "Bearer " + cfg["key"]
    req = urllib.request.Request(cfg["base"] + "/chat/completions",
                                 data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        data = json.loads(r.read().decode("utf-8"))
    msg = data["choices"][0]["message"]
    # reasoning models (qwen3.5/gpt-oss/glm) sometimes send content=null with text in reasoning_content
    return msg.get("content") or msg.get("reasoning_content") or ""


# ------------------------------------------------------------------ streaming
# Kleal's prompts return a JSON object ({"reply": "...", "signals": {...}, ...}), so a raw token
# stream would show the user `{"reply":"Прив`. This extractor walks the stream character by
# character and emits ONLY the decoded contents of one string field, so the caller receives plain
# text as it is generated and never sees the envelope. When no field is requested it passes the
# tokens through unchanged (plain-text prompts).
class FieldStreamer:
    """Incrementally pull one top-level string field out of a JSON object as it streams."""

    def __init__(self, field, gate=None):
        self.key = '"%s"' % field if field else None
        # gate = (key, expected) — hold the field back until another key in the SAME object is seen
        # with the expected value. The caller puts that key BEFORE the field in the prompt, so the
        # verdict arrives before the text does and text that would be thrown away is never shown.
        self.gate = gate
        self.blocked = False
        self.buf = ""          # raw text seen so far (also the full body for the final parse)
        self.started = False   # we are inside the value
        self.done = False      # the value's closing quote was seen
        self._esc = False      # previous char was a backslash
        self._scan = 0         # how much of buf we have already emitted from

    _ESCAPES = {'n': '\n', 't': '\t', 'r': '\r', '"': '"', '\\': '\\', '/': '/', 'b': '', 'f': ''}

    def feed(self, chunk):
        """Return the newly available plain text for this chunk ('' if none yet)."""
        self.buf += chunk
        if not self.key:
            out = self.buf[self._scan:]
            self._scan = len(self.buf)
            return out
        if self.done or self.blocked:
            return ""
        if self.gate and not self.started:
            gk, gv = self.gate
            i = self.buf.find('"%s"' % gk)
            if i < 0:
                return ""                       # verdict not in yet — emit nothing
            seg = self.buf[i + len(gk) + 2: i + len(gk) + 24].lstrip(": \t")
            if seg.startswith(("true", "false", '"')):
                got = seg.split(",")[0].split("}")[0].strip().strip('"')
                if got != str(gv).lower():
                    self.blocked = True         # this reply is destined to be discarded
                    return ""
                self.gate = None                # verdict matches — stream from here on
            else:
                return ""                       # value not complete yet
        if not self.started:
            i = self.buf.find(self.key)
            if i < 0:
                return ""
            j = self.buf.find('"', i + len(self.key))     # opening quote of the VALUE
            if j < 0:
                return ""
            self.started = True
            self._scan = j + 1
        out = []
        i = self._scan
        while i < len(self.buf):
            c = self.buf[i]
            if self._esc:
                if c == 'u' and i + 4 < len(self.buf):     # \uXXXX
                    try:
                        out.append(chr(int(self.buf[i + 1:i + 5], 16)))
                    except ValueError:
                        pass
                    i += 5
                else:
                    out.append(self._ESCAPES.get(c, c))
                    i += 1
                self._esc = False
                continue
            if c == '\\':
                # a trailing backslash may be the first half of an escape split across chunks
                if i == len(self.buf) - 1:
                    break
                self._esc = True
                i += 1
                continue
            if c == '"':                                   # unescaped quote ends the value
                self.done = True
                i += 1
                break
            out.append(c)
            i += 1
        self._scan = i
        return "".join(out)


def stream_llm(cfg, messages, temperature, field, on_text, gate=None):
    """Stream from the OpenAI-compatible endpoint. Calls on_text(str) per new piece of the field.
    Returns the FULL raw model output so the caller can still parse the complete JSON."""
    payload = {"model": cfg["model"], "messages": messages, "max_tokens": 2500,
               "temperature": temperature, "stream": True}
    headers = {"Content-Type": "application/json"}
    if cfg.get("key"):
        headers["Authorization"] = "Bearer " + cfg["key"]
    req = urllib.request.Request(cfg["base"] + "/chat/completions",
                                 data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    fs = FieldStreamer(field, gate)
    raw = []
    with urllib.request.urlopen(req, timeout=180) as r:
        for line in r:
            line = line.decode("utf-8", "replace").strip()
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0].get("delta") or {}
            except Exception:
                continue
            piece = delta.get("content") or delta.get("reasoning_content") or ""
            if not piece:
                continue
            raw.append(piece)
            text = fs.feed(piece)
            if text:
                on_text(text)
    return "".join(raw)


def _send(h, code, obj, ctype="application/json"):
    b = obj.encode("utf-8") if isinstance(obj, str) else json.dumps(obj).encode("utf-8")
    h.send_response(code)
    h.send_header("Content-Type", ctype + "; charset=utf-8")
    h.send_header("Content-Length", str(len(b)))
    h.end_headers()
    h.wfile.write(b)


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/llm/models":
            _send(self, 200, [{"id": k, "label": v["label"], "info": v["info"]} for k, v in MODELS.items()])
        elif self.path == "/":
            _send(self, 200, "Kleal llm-service. POST /llm/complete {model,messages,temperature}; POST /llm/stream (SSE); GET /llm/models", "text/plain")
        else:
            _send(self, 404, {})

    def _sse_open(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")     # tell any proxy in front not to buffer
        self.send_header("Connection", "close")
        self.end_headers()

    def _sse(self, event, obj):
        try:
            self.wfile.write(("event: %s\ndata: %s\n\n" % (
                event, json.dumps(obj, ensure_ascii=False))).encode("utf-8"))
            self.wfile.flush()                          # without this nothing leaves until the end
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False                                # client navigated away mid-stream

    def do_POST(self):
        if self.path == "/llm/stream":
            return self._stream()
        if self.path != "/llm/complete":
            return _send(self, 404, {})
        ln = int(self.headers.get("Content-Length", "0") or 0)
        try:
            body = json.loads(self.rfile.read(ln).decode("utf-8") or "{}")
        except Exception:
            body = {}
        model = body.get("model") or "llama_self"
        cfg = MODELS.get(model) or MODELS["llama_self"]
        messages = body.get("messages") or []
        temperature = body.get("temperature", 0.7)
        try:
            content = call_llm(cfg, messages, temperature)
            _send(self, 200, {"content": content})
        except Exception as e:
            # 502 so shared/llm_client.llm_complete raises and the callers' own fallbacks fire (as before)
            _send(self, 502, {"content": "", "error": str(e)[:200]})


    def _stream(self):
        """POST /llm/stream {model, messages, temperature, field} -> SSE.
        Events: `delta` {t} per new piece of text, then `done` {content} with the FULL raw output so
        the caller can still parse the complete JSON envelope, or `error` {error}."""
        ln = int(self.headers.get("Content-Length", "0") or 0)
        try:
            body = json.loads(self.rfile.read(ln).decode("utf-8") or "{}")
        except Exception:
            body = {}
        cfg = MODELS.get(body.get("model") or "llama_self") or MODELS["llama_self"]
        self._sse_open()
        alive = [True]

        def on_text(t):
            if alive[0] and not self._sse("delta", {"t": t}):
                alive[0] = False

        try:
            g = body.get("gate")
            raw = stream_llm(cfg, body.get("messages") or [], body.get("temperature", 0.7),
                             body.get("field") or None, on_text,
                             (g[0], g[1]) if isinstance(g, list) and len(g) == 2 else None)
            if alive[0]:
                self._sse("done", {"content": raw})
        except Exception as e:
            if alive[0]:
                self._sse("error", {"error": str(e)[:200]})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Kleal llm-service on http://127.0.0.1:%d  (%d models, keys %s)" % (
        PORT, len(MODELS), "set" if AITUNNEL_KEY or SELF_KEY != "x" else "from env"))
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
