# -*- coding: utf-8 -*-
"""Run the query corpus through the REAL app path: text -> buddy -> intent -> slate.
Multi-turn, exactly like a person: if buddy asks a clarifying question, answer it once."""
import json, urllib.request, time

BUDDY = "http://127.0.0.1:7075/api/buddy/chat"
PROFILE = {"name": "Nadia", "interests": ["coffee", "startups", "hiking"], "area": "Belgrade",
           "age": 30, "langs": ["ru"]}

def chat(msgs, timeout=300):
    body = json.dumps({"messages": msgs, "profile": PROFILE}).encode("utf-8")
    r = urllib.request.Request(BUDDY, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))

def cards(res):
    c = res.get("matches") if isinstance(res.get("matches"), list) else []
    if not c:
        blk = res.get("match") if isinstance(res.get("match"), dict) else {}
        c = blk.get("candidates") if isinstance(blk.get("candidates"), list) else []
    return [str(x.get("name") or "") for x in c if isinstance(x, dict) and x.get("name")]

rows = []
corpus = json.load(open("/root/corpus.json"))
for n, (cat, q, expect) in enumerate(corpus, 1):
    msgs, res, turns, err = [{"role": "user", "content": q}], None, 0, None
    for t in range(2):
        try:
            res = chat(msgs)
        except Exception as e:
            err = "%s: %s" % (type(e).__name__, str(e)[:100]); break
        turns = t + 1
        if cards(res): break
        rep = str(res.get("reply") or "")
        if not rep: break
        msgs = msgs + [{"role": "assistant", "content": rep},
                       {"role": "user", "content": "не важно, на твой выбор — давай искать"}]
    intent = (res or {}).get("intent") or {}
    names = cards(res or {})
    rows.append({"n": n, "cat": cat, "q": q, "expect": expect, "err": err, "turns": turns,
                 "topics": intent.get("topics") or [], "rankable": intent.get("rankable"),
                 "n_found": len(names), "names": names[:4],
                 "reply": (str((res or {}).get("reply") or ""))[:220]})
    print("%2d/%d %-24s %-42s -> %s" % (n, len(corpus), cat, q[:42],
          ("ОШИБКА " + err) if err else ("%d чел, темы=%s" % (len(names), intent.get("topics") or []))), flush=True)

json.dump(rows, open("/root/corpus_results.json", "w"), ensure_ascii=False, indent=1)
print("\nГОТОВО:", len(rows), "-> /root/corpus_results.json")
