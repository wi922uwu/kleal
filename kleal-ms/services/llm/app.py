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
            _send(self, 200, "Kleal llm-service. POST /llm/complete {model,messages,temperature}; GET /llm/models", "text/plain")
        else:
            _send(self, 404, {})

    def do_POST(self):
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

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Kleal llm-service on http://127.0.0.1:%d  (%d models, keys %s)" % (
        PORT, len(MODELS), "set" if AITUNNEL_KEY or SELF_KEY != "x" else "from env"))
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
