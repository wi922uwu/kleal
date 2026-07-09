"""Buddy tool-dispatch loop: chat, and on a social intent call find_people, then compose.

One turn = up to two LLM calls (decide -> [tool] -> compose). Works in 'prompt' or
'native' tool transport. The LLM client is injectable (`llm_chat`) for tests.
"""
import re
import json

from . import llm as _llm
from . import prompts
from .tools import FIND_PEOPLE_TOOL, run_find_people

_TOOL_LINE = re.compile(r"TOOL_CALL\s+find_people\s*(\{.*)", re.S)
_LEAK_LINE = re.compile(r"^\s*TOOL_CALL\b.*$", re.M)

FALLBACK = "Расскажи чуть больше — чего хочется: с кем, что поделать, онлайн или вживую?"


def _lenient_json(s):
    """Parse a JSON object, tolerating a missing closing brace / trailing text."""
    if not s:
        return None
    i = s.find("{")
    if i < 0:
        return None
    s = s[i:]
    for cut in (len(s), s.rfind("}") + 1):
        if cut <= 0:
            continue
        cand = s[:cut]
        ob = cand.count("{") - cand.count("}")
        cand2 = cand + ("}" * ob if ob > 0 else "")
        try:
            return json.loads(cand2)
        except Exception:
            continue
    return None


def _parse_prompt_tool_call(content):
    m = _TOOL_LINE.search(content or "")
    return _lenient_json(m.group(1)) if m else None


def _sanitize(text):
    return _LEAK_LINE.sub("", text or "").strip()


def handle_message(user_id, message, store, llm_chat=None, tool_mode=None):
    llm_chat = llm_chat or _llm.chat
    tool_mode = tool_mode or _llm.TOOL_MODE

    history = store.get_history(user_id, limit=12)
    msgs = ([{"role": "system", "content": prompts.system_prompt(tool_mode)}]
            + history + [{"role": "user", "content": message}])

    intent = matches = tool_used = None

    if tool_mode == "native":
        m = llm_chat(msgs, tools=[FIND_PEOPLE_TOOL], tool_choice="auto")
        call, tc_id = None, "call_0"
        for tc in (m.get("tool_calls") or []):
            fn = tc.get("function") or {}
            if fn.get("name") == "find_people":
                call = _lenient_json(fn.get("arguments") or "") or {}
                tc_id = tc.get("id") or tc_id
                break
        if call is not None:
            res = run_find_people(user_id, call, store)
            intent, matches, tool_used = res["intent"], res["matches"], "find_people"
            msgs2 = msgs + [m,
                            {"role": "tool", "tool_call_id": tc_id,
                             "content": json.dumps(res, ensure_ascii=False)},
                            {"role": "user", "content": prompts.tool_result_note(res)}]
            reply = llm_chat(msgs2).get("content") or ""
        else:
            reply = m.get("content") or ""
    else:  # prompt transport
        content = (llm_chat(msgs).get("content") or "").strip()
        call = _parse_prompt_tool_call(content)
        if call is not None:
            res = run_find_people(user_id, call, store)
            intent, matches, tool_used = res["intent"], res["matches"], "find_people"
            msgs2 = msgs + [{"role": "assistant", "content": content},
                            {"role": "user", "content": prompts.tool_result_note(res)}]
            reply = llm_chat(msgs2).get("content") or ""
        else:
            reply = content

    reply = _sanitize(reply) or FALLBACK
    store.add_message(user_id, "user", message)
    store.add_message(user_id, "assistant", reply)
    return {"reply": reply, "intent": intent, "matches": matches, "tool_call": tool_used}
