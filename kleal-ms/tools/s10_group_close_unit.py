# -*- coding: utf-8 -*-
"""Focused S10 / GR.53-GR.55 contract test. Uses an isolated store."""
import importlib.util
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = os.path.join(ROOT, "services", "matching")
os.environ["KLEAL_STORE"] = os.path.join(tempfile.mkdtemp(prefix="kleal-s10-"), "store.json")
sys.path.insert(0, SERVICE)
spec = importlib.util.spec_from_file_location("matching_s10", os.path.join(SERVICE, "app.py"))
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

ok = fail = 0


def check(name, condition, detail=""):
    global ok, fail
    if condition:
        ok += 1
    else:
        fail += 1
        print("FAIL %-52s %s" % (name, str(detail)[:240]))


now = time.time() - 60
g = {
    "id": "s10-main", "title": "Language meetup", "topics": ["languages"],
    "owner": "Anna", "state": "chat_open", "min_total": 3, "max_total": 5,
    "members": [
        {"name": "Anna", "state": "joined", "joined": now},
        {"name": "Marc", "state": "joined", "joined": now + 1},
        {"name": "Jane", "state": "joined", "joined": now + 2},
    ],
    "updated": now, "version": 1,
}
app.SESSION.clear()
app.SESSION["_gintents"] = [g]
app.SESSION["_gplans"] = []
app.SESSION["_gmsgs"] = [
    {"id": "before", "gid": g["id"], "frm": "Marc", "text": "hello",
     "t": now + 10, "u": now + 10, "kind": "msg"},
]
app.SESSION["_ginvites"] = [
    {"id": "open", "gid": g["id"], "frm": "Anna", "to": "Sofia", "state": "sent",
     "created": now, "updated": now, "expires_at": now + 86400},
]

check("owner sees end affordance before plan", app._gi_public(g, "Anna").get("can_end") is True)
check("member cannot close", app.gi_close(g["id"], "Marc").get("error") == "NOT_ORGANIZER")
closed = app.gi_close(g["id"], "Anna", "s10-once")
check("owner closes group", closed.get("ok") is True and g.get("state") == "closed_by_owner", closed)
check("idempotent retry", app.gi_close(g["id"], "Anna", "s10-once") == closed)
check("open invite is closed neutrally", app.SESSION["_ginvites"][0].get("state") == "group_closed"
      and "Nothing you did" in app.SESSION["_ginvites"][0].get("note_out", ""), app.SESSION["_ginvites"])
check("invitee receives agent event", any((m.get("sys") or {}).get("code") == "group_closed_invite"
      and m.get("to") == "Sofia" for m in app.SESSION.get("_messages") or []), app.SESSION.get("_messages"))

member = app.gi_thread(g["id"], "Marc")
check("member keeps read-only archive", member.get("ok") is True
      and member.get("group", {}).get("read_only_reason") == "group_closed", member)
check("archive contains close event", any((m.get("sys") or {}).get("code") == "group_closed"
      for m in member.get("messages") or []), member.get("messages"))
check("closed group rejects posts", app.gi_post(g["id"], "Marc", "after").get("error") == "CLOSED")
check("closed group rejects reactions", app.gmsg_react(g["id"], "Marc", "before", "👍").get("error") == "CLOSED")
check("closed group rejects deletes", app.gmsg_delete(g["id"], "Marc", "before").get("error") == "CLOSED")
check("closed invite leaves inbox", not app.home_invites("Sofia").get("invites"))
check("closed group cannot start plan", app.gp_begin(g["id"], "Anna", "tomorrow").get("error") == "CLOSED")

g2 = dict(g, id="s10-plan", state="chat_open", members=[dict(m) for m in g["members"]])
app.SESSION["_gintents"].append(g2)
app.SESSION["_gplans"].append({"id": "plan", "gid": g2["id"], "state": "proposed"})
check("plan hides end affordance", app._gi_public(g2, "Anna").get("can_end") is False)
check("server blocks close after plan", app.gi_close(g2["id"], "Anna").get("error") == "PLAN_EXISTS")

print("S10 RESULT: %d ok, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
