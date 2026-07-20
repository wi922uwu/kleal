# -*- coding: utf-8 -*-
# Kleal shared LLM client — the ONLY way onboarding-service and matching-service reach a model.
# It talks HTTP to llm-service (which alone holds the API keys + model base URLs). No secrets here.
#
# Drop-in for the old `base.call_llm(cfg, messages, temperature)` — except the first arg is now a
# model *id* (a MODELS key like "llama_self"), not a resolved cfg dict. On a transport failure to
# llm-service it RAISES (exactly like the old urllib call), so the callers' existing try/except
# fallbacks fire unchanged. See contracts.md.
import os
import json
import urllib.request

LLM_URL = os.environ.get("LLM_URL", "http://127.0.0.1:7071").rstrip("/")


def llm_complete(model, messages, temperature=0.7):
    """POST /llm/complete -> assistant text ('' if the model returned nothing). Raises on transport error."""
    body = json.dumps({"model": model, "messages": messages, "temperature": temperature}).encode("utf-8")
    req = urllib.request.Request(LLM_URL + "/llm/complete", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=195) as r:
        return json.loads(r.read().decode("utf-8")).get("content", "")


def llm_models():
    """GET /llm/models -> [{id,label,info}] (best-effort; [] on failure)."""
    try:
        with urllib.request.urlopen(LLM_URL + "/llm/models", timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return []


def llm_stream(model, messages, temperature, field, on_text):
    """POST /llm/stream -> consumes SSE, calls on_text(str) per new piece of `field`.
    Returns the FULL raw model output so the caller still parses the complete JSON envelope.
    Raises on transport error, exactly like llm_complete, so existing fallbacks fire."""
    body = json.dumps({"model": model, "messages": messages, "temperature": temperature,
                       "field": field}).encode("utf-8")
    req = urllib.request.Request(LLM_URL + "/llm/stream", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    raw, ev = "", None
    with urllib.request.urlopen(req, timeout=195) as r:
        for line in r:
            line = line.decode("utf-8", "replace").rstrip("\n")
            if line.startswith("event: "):
                ev = line[7:]
            elif line.startswith("data: "):
                try:
                    d = json.loads(line[6:])
                except Exception:
                    continue
                if ev == "delta" and d.get("t"):
                    on_text(d["t"])
                elif ev == "done":
                    raw = d.get("content") or ""
                elif ev == "error":
                    raise RuntimeError(d.get("error") or "llm stream error")
    return raw
