# -*- coding: utf-8 -*-
"""Исход приглашения в группу организатор видит с сервера — борд «0 · Create the intent», GR.14d/14e/17.

    python3 tools/gr_invites_closed_unit.py

До 03.10.2026 `gintent` отдавал организатору только открытые приглашения, и «Can't make it» /
«Invite closed» клиент угадывал по пропаже строки. Теперь закрытые идут полем `invites_closed`
в словаре клиента (src/ginvites.ts CLOSED_STATES); `invites` по-прежнему только открытые.
"""
import importlib.util
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = os.path.join(ROOT, "services", "matching")
TMP = tempfile.mkdtemp(prefix="kleal-invclosed-")
os.environ["KLEAL_STORE"] = os.path.join(TMP, "store.json")
os.environ["KLEAL_REPORT_EVIDENCE_DIR"] = os.path.join(TMP, "evidence")
sys.path.insert(0, SERVICE)
spec = importlib.util.spec_from_file_location("matching_invclosed", os.path.join(SERVICE, "app.py"))
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

ok = fail = 0


def check(name, condition, detail=""):
    global ok, fail
    if condition:
        ok += 1
    else:
        fail += 1
        print("FAIL %-60s %s" % (name, str(detail)[:300]))


now = time.time()
g = {"id": "gr-ic", "title": "BBQ by the beach", "owner": "Mateo", "state": "chat_open",
     "min_total": 3, "max_total": 5, "updated": now, "version": 1,
     "members": [{"name": "Mateo", "state": "joined", "joined": now - 90},
                 {"name": "Jane", "state": "joined", "joined": now - 60}]}


def inv(i, to, state, upd):
    return {"id": "gi-%d" % i, "gid": g["id"], "frm": "Mateo", "to": to, "state": state,
            "created": now - 500, "updated": now - upd, "expires_at": now + 3600}


app.SESSION.clear()
app.SESSION["_gintents"] = [g]
app.SESSION["_ginvites"] = [
    inv(1, "Jane", "accepted", 60), inv(2, "Marc", "declined", 50), inv(3, "Elly", "group_full", 40),
    inv(4, "Leo", "expired", 30), inv(5, "Ana", "sent", 20), inv(6, "Bob", "withdrawn", 25),
    inv(7, "Bob", "sent", 10), inv(8, "Kim", "policy_revoked", 5)]

own = app._gi_full(g, "Mateo")
opn = own.get("invites") or []
cls = own.get("invites_closed") or []
check("open list is open only", sorted(i["to"] for i in opn) == ["Ana", "Bob"], opn)
check("open rows carry at/expires_at", all(i.get("at") and i.get("expires_at") for i in opn), opn)
by = {(i["to"], i["reason"]): i for i in cls}
check("declined stays declined", by.get(("Marc", "declined"), {}).get("state") == "declined", cls)
check("group_full -> closed", by.get(("Elly", "group_full"), {}).get("state") == "closed", cls)
check("policy_revoked -> closed", by.get(("Kim", "policy_revoked"), {}).get("state") == "closed", cls)
check("expired/withdrawn keep names", by.get(("Leo", "expired"), {}).get("state") == "expired"
      and by.get(("Bob", "withdrawn"), {}).get("state") == "withdrawn", cls)
check("accepted is not a closed row", not any(i["to"] == "Jane" for i in cls), cls)
check("closed rows carry closed_at", all(i.get("closed_at") for i in cls), cls)
check("closed rows oldest first", [i["closed_at"] for i in cls] == sorted(i["closed_at"] for i in cls), cls)
client = {"declined", "rejected", "expired", "withdrawn", "closed", "cancelled", "superseded"}
check("every closed state is in client vocabulary", all(i["state"] in client for i in cls), cls)
check("members carry joined_at", all(m.get("joined_at") for m in own.get("members") or []), own.get("members"))

# withdrawn = «организатор отменил» только в живой группе; закрытие группы и 1:1 — это closed.
conv = dict(inv(9, "Zoe", "withdrawn", 3), note_out="Mateo turned it into a one-on-one")
app.SESSION["_ginvites"].append(conv)
cls2 = {i["id"]: i for i in app._gi_full(g, "Mateo").get("invites_closed") or []}
check("owner cancel stays withdrawn", cls2.get("gi-6", {}).get("state") == "withdrawn", cls2.get("gi-6"))
check("1:1 conversion withdrawn -> closed", cls2.get("gi-9", {}).get("state") == "closed", cls2.get("gi-9"))
ended = dict(g, state="cancelled")
cls3 = {i["id"]: i for i in app._gi_full(ended, "Mateo").get("invites_closed") or []}
check("ended group withdrawn -> closed", cls3.get("gi-6", {}).get("state") == "closed", cls3.get("gi-6"))
check("raw kept in reason", cls3.get("gi-6", {}).get("reason") == "withdrawn", cls3.get("gi-6"))
app.SESSION["_ginvites"].remove(conv)

check("group invite lives 12h (board, owner 04.10)", app.GI_INVITE_TTL == 12 * 3600, app.GI_INVITE_TTL)

g["intent"] = {"title": "BBQ by the beach", "address": "Pg. Marítim de la Barceloneta, 4"}
check("owner sees exact address", app._gi_full(g, "Mateo").get("address") == "Pg. Marítim de la Barceloneta, 4")
check("member gets no address", "address" not in app._gi_full(g, "Jane"))
check("member public view has no address", "address" not in app._gi_public(g, "Jane"))
check("stranger teaser has no address", "address" not in app._gi_public(g, "Zed"))
# Бывший организатор (передал роль Jane) видит адрес, пока в комнате; новый — тоже; третий — нет.
g2 = dict(g, owner="Jane", role_from={"who": "Mateo", "how": "handed", "at": now},
          members=g["members"] + [{"name": "Marc", "state": "joined", "joined": now - 10}])
check("former owner in room sees address", app._gi_full(g2, "Mateo").get("address") == "Pg. Marítim de la Barceloneta, 4")
check("new owner sees address", app._gi_full(g2, "Jane").get("address") == "Pg. Marítim de la Barceloneta, 4")
check("other member still no address", "address" not in app._gi_full(g2, "Marc"))
g3 = dict(g2, members=[{"name": "Jane", "state": "joined", "joined": now - 60},
                       {"name": "Mateo", "state": "left", "joined": now - 90, "left": now - 5}])
check("former owner who left loses address", "address" not in app._gi_full(g3, "Mateo"))

app.SESSION["_ginvites"].append(inv(10, "Nia", "sent", 1))
check("invitee view has no address", "address" not in app._gi_public(g, "Nia"))
app.SESSION["_ginvites"].pop()

mem = app._gi_full(g, "Jane")
check("member sees no invites", "invites" not in mem and "invites_closed" not in mem, list(mem))
check("stranger teaser has no invites", "invites_closed" not in app._gi_public(g, "Zed"))

print("INVITES CLOSED RESULT: %d ok, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
