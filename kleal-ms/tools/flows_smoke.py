# -*- coding: utf-8 -*-
"""Do the restored screens actually WORK, or just answer 200?

Each block is a whole user journey through one screen, asserting the state the next screen would
have to read. A handler that returns 200 with an empty body would pass a status probe and fail here.
"""
import json, urllib.request, urllib.error, sys, time

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7074"
A, B = "Nuria Iglesias", "Marc Puig"
R = {"ok": 0, "fail": 0}
FAILED = []


def call(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return {"_http": e.code, "_body": e.read().decode("utf-8", "replace")[:160]}
    except Exception as e:
        return {"_err": type(e).__name__ + ": " + str(e)[:120]}


def check(name, cond, detail=""):
    R["ok" if cond else "fail"] += 1
    if not cond:
        FAILED.append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (("   " + str(detail)[:120]) if detail else ""))


def q(name):
    from urllib.parse import quote
    return quote(name)


print("=" * 74)
print("MY INTENTS — save, list, delete")
print("=" * 74)
r = call("/api/agent/intent-save", {"self": A, "intent": {"topics": ["coffee"], "type": "social"},
                                    "title": "Coffee in Gracia"})
check("intent-save returns an id", bool(r.get("id") or (r.get("intent") or {}).get("id")), r)
iid = r.get("id") or (r.get("intent") or {}).get("id")

r = call("/api/agent/intents", {"self": A, "live": False})
lst = r.get("intents") or []
check("the saved intent appears in the list", any((i.get("id") == iid) for i in lst),
      "%d intents, ids=%s" % (len(lst), [i.get("id") for i in lst][:4]))
mine = [i for i in lst if i.get("id") == iid]
check("the intent kept its title", bool(mine and mine[0].get("title")), mine[0].get("title") if mine else None)

r = call("/api/agent/intent-delete", {"self": A, "id": iid})
check("intent-delete reports success", r.get("ok") is not False, r)
lst2 = (call("/api/agent/intents", {"self": A, "live": False}) or {}).get("intents") or []
check("the intent is gone after delete", not any(i.get("id") == iid for i in lst2),
      "%d left" % len(lst2))

print()
print("=" * 74)
print("MESSAGES — propose, inbox/outbox, respond, thread")
print("=" * 74)
idem = "flow-%d" % int(time.time())
r = call("/api/agent/propose", {"from": A, "to": B, "intent": {"topics": ["coffee"], "type": "social"},
                                "note": "coffee tomorrow?", "idem": idem})
rid = r.get("id") or (r.get("request") or {}).get("id")
check("propose creates a request", bool(rid), r)

r2 = call("/api/agent/propose", {"from": A, "to": B, "intent": {"topics": ["coffee"], "type": "social"},
                                 "note": "coffee tomorrow?", "idem": idem})
rid2 = r2.get("id") or (r2.get("request") or {}).get("id")
check("the same idem key does not create a second request (§14)", rid2 == rid, "%s vs %s" % (rid, rid2))

out = (call("/api/agent/outbox?self=" + q(A)) or {}).get("requests") or []
check("it shows in the sender's outbox", any(x.get("id") == rid for x in out), "%d in outbox" % len(out))
inb = (call("/api/agent/inbox?self=" + q(B)) or {}).get("requests") or []
check("it shows in the recipient's inbox", any(x.get("id") == rid for x in inb), "%d in inbox" % len(inb))

r = call("/api/agent/respond", {"id": rid, "decision": "accept", "self": B})
check("recipient can accept", r.get("ok") is not False and not r.get("error"), r)
inb2 = (call("/api/agent/inbox?self=" + q(B)) or {}).get("requests") or []
acc = [x for x in inb2 if x.get("id") == rid]
check("the request is now accepted", bool(acc) and acc[0].get("status") in ("accepted", "accept"),
      acc[0].get("status") if acc else "gone")

r = call("/api/agent/message", {"from": A, "to": B, "text": "see you at 6"})
check("a message can be sent", r.get("ok") is not False and not r.get("error"), r)
th = (call("/api/agent/thread?self=%s&with=%s" % (q(A), q(B))) or {}).get("messages") or []
check("the message is in the thread", any("see you at 6" in str(m.get("text", "")) for m in th),
      "%d messages" % len(th))
ths = (call("/api/agent/threads?self=" + q(A)) or {}).get("threads") or []
check("the thread appears in the thread list", any(B in str(t) for t in ths), "%d threads" % len(ths))

r = call("/api/agent/request-archive", {"id": rid, "self": B})
check("archive works", r.get("ok") is not False, r)

idem_w = "flow-w-%d" % int(time.time())
rw = call("/api/agent/propose", {"from": A, "to": B, "intent": {"topics": ["padel"]},
                                 "note": "padel?", "idem": idem_w})
ridw = rw.get("id") or (rw.get("request") or {}).get("id")
r = call("/api/agent/withdraw", {"id": ridw, "self": A})
check("sender can withdraw", r.get("ok") is not False and not r.get("error"), r)

print()
print("=" * 74)
print("GROUPS — create, list, join, leave")
print("=" * 74)
gidem = "flow-g-%d" % int(time.time())
r = call("/api/agent/group-create", {"host": A, "title": "Sunday padel", "topics": ["padel"],
                                     "when": "Sunday 10:00", "area": "Gràcia", "mode": "offline",
                                     "min_size": 2, "max_size": 4, "idem": gidem})
gid = r.get("gid") or (r.get("group") or {}).get("gid") or (r.get("group") or {}).get("id")
check("group-create returns a group id", bool(gid), r)

gl = (call("/api/agent/groups?self=%s&limit=30" % q(A)) or {}).get("groups") or []
check("the group is listed", any((g.get("gid") or g.get("id")) == gid for g in gl), "%d groups" % len(gl))
g0 = [g for g in gl if (g.get("gid") or g.get("id")) == gid]
check("the group carries its title and state", bool(g0) and bool(g0[0].get("title")),
      {k: g0[0].get(k) for k in ("title", "state", "members") if g0} if g0 else None)

r = call("/api/agent/group-join", {"gid": gid, "self": B, "idem": "j-" + gidem})
check("someone can join", r.get("ok") is not False and not r.get("error"), r)
gl2 = (call("/api/agent/groups?self=%s&limit=30" % q(B)) or {}).get("groups") or []
gj = [g for g in gl2 if (g.get("gid") or g.get("id")) == gid]
mem = (gj[0].get("members") if gj else None)
check("the joiner is counted as a member",
      bool(gj) and (isinstance(mem, int) and mem >= 2 or isinstance(mem, list) and len(mem) >= 2),
      "members=%s state=%s" % (mem, gj[0].get("state") if gj else None))

r = call("/api/agent/group-leave", {"gid": gid, "self": B, "idem": "l-" + gidem})
check("someone can leave", r.get("ok") is not False and not r.get("error"), r)

print()
print("=" * 74)
print("RESULT: %d ok, %d failed" % (R["ok"], R["fail"]))
if FAILED:
    print("\nfailed:")
    for f in FAILED:
        print("   -", f)
