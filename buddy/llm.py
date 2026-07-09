"""OpenAI-compatible LLM client. Model/endpoint entirely env-driven.

LLM_BASE / LLM_KEY / LLM_MODEL point at any OpenAI-compatible endpoint (the pod gateway
:3000 or vLLM :8002). BUDDY_TOOL_MODE = 'prompt' (default, works on the current vLLM) or
'native' (requires vLLM launched with --enable-auto-tool-choice --tool-call-parser).
"""
import os
import json
import urllib.request
import urllib.error

LLM_BASE = os.environ.get("LLM_BASE", os.environ.get("SELF_BASE", "http://localhost:8002/v1")).rstrip("/")
LLM_KEY = os.environ.get("LLM_KEY", os.environ.get("SELF_KEY", "x"))
LLM_MODEL = os.environ.get("LLM_MODEL", "llama-3.3-70b")
TOOL_MODE = os.environ.get("BUDDY_TOOL_MODE", "prompt")  # 'prompt' | 'native'


class LLMError(Exception):
    pass


def chat(messages, tools=None, tool_choice="auto", temperature=0.6, max_tokens=1200, timeout=180):
    """Return the assistant message dict (choices[0].message); may carry tool_calls."""
    payload = {"model": LLM_MODEL, "messages": messages,
               "temperature": temperature, "max_tokens": max_tokens}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice
    headers = {"Content-Type": "application/json"}
    if LLM_KEY:
        headers["Authorization"] = "Bearer " + LLM_KEY
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    last = None
    for _ in range(2):  # retry once on transient/5xx
        try:
            req = urllib.request.Request(LLM_BASE + "/chat/completions",
                                         data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                resp = json.loads(r.read().decode("utf-8"))
            msg = resp["choices"][0]["message"]
            # reasoning models sometimes put text in reasoning_content
            if not msg.get("content") and msg.get("reasoning_content"):
                msg["content"] = msg["reasoning_content"]
            return msg
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:200]
            last = LLMError("upstream %d: %s" % (e.code, body))
            if e.code < 500:
                break
        except Exception as e:  # timeout / connection
            last = LLMError(str(e))
    raise last or LLMError("unknown LLM error")
