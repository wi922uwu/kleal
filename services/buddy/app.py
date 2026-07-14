# -*- coding: utf-8 -*-
# Kleal buddy-service — the CONVERSATIONAL agent the user just chats with. It talks naturally, quietly
# accumulates the user's SIGNALS (topics/role/type/vibe/languages/time/area/datingOk/dealBreakers),
# and when the user clearly wants to meet someone it calls the MATCHING agent (agent-to-agent, over
# HTTP) with the assembled signals and surfaces the best match in the chat.
#
#   user  <->  buddy-service (:7075, conversation, LLM)  --HTTP-->  matching-service (:7074, ranking)
#
# Holds NO model keys — reaches the LLM via shared/llm_client. Owner: shared (Dev A conversation, Dev B match).
import os
import sys
import json
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "..", "..", "shared"), os.path.join(_HERE, "shared")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
import kleal_lib as base                      # base._extract_json (keyless)
from llm_client import llm_complete
from http_util import send_json, read_json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("BUDDY_PORT", "7075"))
MODEL_ID = os.environ.get("V2_MODEL", "llama_self")
MATCH_URL = os.environ.get("MATCH_URL", "http://127.0.0.1:7074").rstrip("/")

SIGNAL_KEYS = ("topics", "role", "type", "vibe", "languages", "time", "area", "datingOk", "dealBreakers")
LIST_KEYS = ("topics", "languages", "dealBreakers")
MEET_WORDS = ("meet", "find", "someone", "people", "partner", "buddy", "teammate", "match", "date",
              "play with", "together", "join", "hang out", "who else")

BUDDY_PROMPT = '''You are "Kleal", the user's personal buddy — a warm, genuinely curious friend they chat with. Talk naturally and briefly (1-3 sentences), never like a form or a survey. React to what they said, bring a little energy, and ask at most ONE light question when it flows.

Quietly, as you chat, learn the user's SIGNALS (ONLY what they actually reveal — never invent):
- topics: interests/activities, lowercase (e.g. ["chess","coffee","football"])
- role: what they want to DO with someone — one of play, watch, discuss, practise, attend, meet
- type: sport, gaming, networking, dating, language, social
- vibe: chill, energetic, competitive, intellectual, creative, social, calm
- languages: 2-letter codes (e.g. ["en","es"])
- time: when they are free (e.g. "today evening", "weekend")
- area: their neighbourhood / city if mentioned
- datingOk: true ONLY if they clearly want dating / romance
- dealBreakers: anything they say they want to avoid

Known so far (baseline from their profile): __SIG__

Set "match": true ONLY when the user clearly wants to meet a person or do an activity WITH someone (or asks you to find people). Otherwise keep chatting (match:false).

Reply as ONE JSON object only, nothing outside it:
{"reply":"<your natural message>","signals":{<only the fields you newly learned THIS turn>},"match":true|false}
English only.'''


def _as_list(v):
    if isinstance(v, list):
        return [str(x).strip().lower() for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [v.strip().lower()]
    return []


def _merge_signals(base_sig, delta):
    out = {k: v for k, v in (base_sig or {}).items()}
    for k, v in (delta or {}).items():
        if k not in SIGNAL_KEYS or v in (None, "", [], {}):
            continue
        if k in LIST_KEYS:
            cur = list(out.get(k) or [])
            for x in _as_list(v):
                if x not in cur:
                    cur.append(x)
            out[k] = cur[:8]
        else:
            out[k] = v
    return out


def _baseline_signals(profile):
    """Seed signals from what the buddy already KNOWS about the user (their profile / agent memory)."""
    p = profile or {}
    sig = {}
    ints = p.get("interests")
    topics = []
    if isinstance(ints, dict):
        topics = _as_list(ints.get("explicit"))
    elif isinstance(ints, list):
        for it in ints:
            if isinstance(it, dict) and it.get("name"):
                topics.append(str(it["name"]).lower())
            elif isinstance(it, str):
                topics.append(it.lower())
    if topics:
        sig["topics"] = topics[:8]
    langs = p.get("languages")
    ll = []
    if isinstance(langs, dict):
        ll = _as_list(langs.get("comfortable")) or _as_list(langs.get("fluent"))
    elif isinstance(langs, list):
        ll = _as_list(langs)
    ll = [x[:2] for x in ll]
    if ll:
        sig["languages"] = ll
    vibe = p.get("vibe")
    if isinstance(vibe, dict):
        pv = _as_list(vibe.get("primary"))
        if pv:
            sig["vibe"] = pv[0]
    elif isinstance(vibe, str) and vibe.strip():
        sig["vibe"] = vibe.strip().lower()
    city = p.get("city") or ((p.get("geo") or {}).get("comfortableAreas") or [None])[0]
    if city:
        sig["area"] = str(city)
    dom = (p.get("domains") or {}).get("dating") or {}
    if dom.get("enabled") is True or "dating" in _as_list((p.get("goals") or {}).get("primary")):
        sig["datingOk"] = True
    return sig


def _signals_to_intent(sig):
    topics = sig.get("topics") or []
    typ = (sig.get("type") or "").lower()
    if not typ:
        typ = "dating" if sig.get("datingOk") else "social"
    title = "Date" if typ == "dating" else ((topics[0].capitalize() + " meetup") if topics else "Meet someone")
    return {"title": title, "type": typ, "topics": topics or (["dating"] if typ == "dating" else ["social"]),
            "role": sig.get("role") or "meet", "mode": "offline",
            "time": sig.get("time") or "Flexible", "place": "Public places nearby",
            "radiusKm": 15, "adjacentAllowed": True, "broadAllowed": True,
            "verifiedOnly": bool(typ == "dating"), "minAge": (18 if typ == "dating" else None)}


def _post(path, payload, timeout=30):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(MATCH_URL + path, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _do_match(sig, profile):
    """Agent-to-agent: hand the assembled signals to the matching agent, get the best match back."""
    intent = _signals_to_intent(sig)
    prof = {"languages": {"comfortable": sig.get("languages") or []}, "vibe": sig.get("vibe")}
    try:
        res = _post("/api/agent/match", {"intent": intent, "profile": prof})
    except Exception:
        res = {"candidates": []}
    cands = res.get("candidates") or []
    if not cands:
        return {"intent": intent, "top": None, "candidates": [], "fallback": res.get("fallback")}
    return {"intent": intent, "top": cands[0], "candidates": cands[:3]}


def buddy_chat(messages, profile, signals):
    sig = _merge_signals(_baseline_signals(profile), signals)
    convo = "\n".join((("User: " + str(m.get("content", ""))) if m.get("role") == "user"
                       else ("Buddy: " + str(m.get("content", "")))) for m in (messages or [])[-12:])
    last_user = next((str(m.get("content", "")) for m in reversed(messages or []) if m.get("role") == "user"), "")
    obj = None
    try:
        raw = llm_complete(MODEL_ID, [{"role": "system", "content": BUDDY_PROMPT.replace("__SIG__", json.dumps(sig))},
                                      {"role": "user", "content": convo}], 0.6)
        obj = base._extract_json(raw)
    except Exception:
        obj = None

    if isinstance(obj, dict) and obj.get("reply"):
        reply = str(obj.get("reply"))[:600]
        sig = _merge_signals(sig, obj.get("signals") or {})
        want_match = bool(obj.get("match"))
    else:
        # deterministic fallback (LLM down): keep it light + detect a meet-intent by keywords
        want_match = any(w in last_user.lower() for w in MEET_WORDS)
        reply = ("Let me find someone for you." if want_match
                 else "Nice — tell me a bit more about what you're into and who you'd like to meet.")

    match = None
    if want_match:
        match = _do_match(sig, profile)
        if match.get("top"):
            t = match["top"]
            why = (t.get("reasons") or ["a great fit"])[0]
            reply = (reply + "\n\nI think you'd click with %s — %s." % (t.get("name"), why)).strip()
        else:
            reply = (reply + "\n\nNo one perfect right now — want to go broader or try online?").strip()
    return {"reply": reply, "signals": sig, "match": match}


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            send_json(self, 200, {"service": "buddy", "ok": True})
        else:
            send_json(self, 404, {})

    def do_POST(self):
        if self.path != "/api/buddy/chat":
            return send_json(self, 404, {})
        body = read_json(self)
        messages = body.get("messages") if isinstance(body.get("messages"), list) else []
        profile = body.get("profile") if isinstance(body.get("profile"), dict) else {}
        signals = body.get("signals") if isinstance(body.get("signals"), dict) else {}
        try:
            send_json(self, 200, buddy_chat(messages, profile, signals))
        except Exception as e:
            send_json(self, 200, {"reply": "I glitched for a second — say that again?",
                                  "signals": signals, "match": None, "error": str(e)[:200]})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Kleal buddy-service on http://127.0.0.1:%d  (LLM via llm-service, matching at %s)" % (PORT, MATCH_URL))
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
