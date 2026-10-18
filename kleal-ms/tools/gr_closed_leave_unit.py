# -*- coding: utf-8 -*-
"""Закрытая группа не зовёт и не принимает; уход организатора гасит предложение роли и перехват.

    python3 tools/gr_closed_leave_unit.py

17.10.2026. Два серверных бага групп:
  1. gi_invite / gi_respond отсекали cancelled/expired/converted_1to1, а closed_by_owner (S10)
     пропускали: организатор закрыл группу, позвал ещё человека, тот сказал «да» и через
     awaiting_approval → gi_approve попадал в комнату только для чтения.
  2. gi_leave отдавал роль старейшему, но не закрывал role_offer и takeover: у наследника
     оставались чужие кнопки, а адресат предложения мог забрать роль у наследника.
Хранилище — временное.
"""
import importlib.util
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = os.path.join(ROOT, "services", "matching")
TMP = tempfile.mkdtemp(prefix="kleal-closed-leave-")
os.environ["KLEAL_STORE"] = os.path.join(TMP, "store.json")
os.environ["KLEAL_REPORT_EVIDENCE_DIR"] = os.path.join(TMP, "evidence")
sys.path.insert(0, SERVICE)
spec = importlib.util.spec_from_file_location("matching_closed_leave", os.path.join(SERVICE, "app.py"))
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


def reset(*groups):
    app.SESSION.clear()
    app.SESSION["_gintents"] = list(groups)
    app.SESSION["_gplans"] = []
    app.SESSION["_gmsgs"] = []
    app.SESSION["_ginvites"] = []


def pair(state="chat_open", gid="gr-cl"):
    """Организатор и один участник — места есть, плана нет."""
    t = time.time() - 60
    return {"id": gid, "title": "Language meetup", "owner": "Anna", "state": state,
            "min_total": 3, "max_total": 5, "updated": t, "version": 1,
            "members": [{"name": "Anna", "state": "joined", "joined": t},
                        {"name": "Marc", "state": "joined", "joined": t + 1}]}


def four(hours_ago=13, gid="gr-lv"):
    """Собранная четвёрка без плана; организатор Mateo молчит `hours_ago` часов. Старейший после
    него — Jane, она и наследница."""
    t0 = time.time() - hours_ago * 3600
    return {"id": gid, "title": "BBQ by the beach", "owner": "Mateo", "state": "ready_to_plan",
            "min_total": 3, "max_total": 5, "updated": t0, "version": 1,
            "members": [{"name": "Mateo", "state": "joined", "joined": t0 - 60},
                        {"name": "Jane", "state": "joined", "joined": t0 - 30},
                        {"name": "Marc", "state": "joined", "joined": t0},
                        {"name": "Leo", "state": "joined", "joined": t0 + 1}]}


def legacy_invite(g, to, state="sent"):
    """Приглашение, которое прежний код успел отправить уже ПОСЛЕ закрытия группы."""
    now = time.time()
    row = {"id": "gv-%s" % to, "gid": g["id"], "frm": g["owner"], "to": to, "state": state,
           "created": now - 30, "updated": now - 30, "expires_at": now + 3600, "intent_version": 1}
    app.SESSION["_ginvites"].append(row)
    return row


def names(g):
    return [m["name"] for m in app._gi_active(g)]


def codes(gid=None):
    return [(m.get("sys") or {}).get("code") for m in app.SESSION["_gmsgs"]
            if gid is None or m.get("gid") == gid]


def ago(g, key, hours):
    x = g.get(key)
    for f in ("at", "closes", "expires"):
        if x and f in x:
            x[f] = float(x[f]) - hours * 3600


# ── 1. Закрытая организатором группа ─────────────────────────────────────────────────────────────
g = pair()
reset(g)
r = app.gi_invite(g["id"], "Anna", "Sofia")
check("open group: invite before close goes out", r.get("ok") is True, r)
before = app.SESSION["_ginvites"][0]
check("close ok", app.gi_close(g["id"], "Anna").get("ok") is True and g["state"] == "closed_by_owner")
check("close: open invite -> group_closed", before["state"] == "group_closed", before)

# 1a. Звать в закрытую группу нельзя.
n_inv = len(app.SESSION["_ginvites"])
r = app.gi_invite(g["id"], "Anna", "Leo", idem="cl-inv")
check("closed: invite refused CLOSED", r.get("ok") is False and r.get("error") == "CLOSED", r)
check("closed: no invite row created", len(app.SESSION["_ginvites"]) == n_inv, app.SESSION["_ginvites"])
check("closed: idempotent refusal", app.gi_invite(g["id"], "Anna", "Leo", idem="cl-inv") == r)
r = app.gi_invite_many(g["id"], "Anna", ["Leo", "Kim"])
check("closed: batch refused for everyone", r.get("ok") is False and not r.get("sent")
      and all(x.get("error") == "CLOSED" for x in r.get("refused") or []), r)

# 1b. «Да» на приглашение, отправленное после закрытия прежним кодом, — отказ и group_closed.
late = legacy_invite(g, "Sofia")
r = app.gi_respond(late["id"], "Sofia", True, idem="cl-yes")
check("closed: accept refused CLOSED", r.get("ok") is False and r.get("error") == "CLOSED", r)
check("closed: invite -> group_closed (not awaiting_approval)", late["state"] == "group_closed", late)
check("closed: Sofia is not a member", "Sofia" not in names(g), names(g))
check("closed: retry with same idem is the same answer", app.gi_respond(late["id"], "Sofia", True, idem="cl-yes") == r)
r = app.gi_respond(late["id"], "Sofia", True)
check("closed: second accept names the state", r.get("error") == "GROUP_CLOSED", r)
det = app.gi_invite_detail(late["id"], "Sofia")
check("invitee sees the invite closed: closed", (det.get("invite") or {}).get("closed") == "closed", det)
own = {i["id"]: i for i in app._gi_full(g, "Anna").get("invites_closed") or []}
check("organiser sees it as closed (group_closed)", own.get(late["id"], {}).get("state") == "closed"
      and own[late["id"]].get("reason") == "group_closed", own)
check("closed: nothing new in the read-only chat", codes(g["id"]).count("joined") == 0, codes(g["id"]))

# 1c. Ждущего одобрения в закрытой группе не одобряют.
wait = legacy_invite(g, "Kim", state="awaiting_approval")
r = app.gi_approve(g["id"], "Anna", "Kim", True)
check("closed: approve refused CLOSED", r.get("ok") is False and r.get("error") == "CLOSED", r)
check("closed: awaiting -> group_closed", wait["state"] == "group_closed", wait)
check("closed: Kim is not a member", "Kim" not in names(g), names(g))

# 1d. Закрытие гасит и ждущих одобрения (так было и до правки — договор S10).
g = pair(state="planning", gid="gr-cl2")
reset(g)
w = legacy_invite(g, "Nia", state="awaiting_approval")
app.gi_close(g["id"], "Anna")
check("close: awaiting_approval -> group_closed", w["state"] == "group_closed", w)

# ── 2. Открытая группа — как раньше ──────────────────────────────────────────────────────────────
g = pair()
reset(g)
r = app.gi_invite(g["id"], "Anna", "Sofia")
check("open: invite ok", r.get("ok") is True, r)
r = app.gi_respond(r["invite"]["id"], "Sofia", True)
check("open: accept drops straight into the room", r.get("ok") is True and "Sofia" in names(g)
      and g["state"] == "ready_to_plan", (r, g["state"]))
check("open: chat says joined", "joined" in codes(g["id"]), codes(g["id"]))
r = app.gi_invite(g["id"], "Anna", "Leo")
app.gi_respond(r["invite"]["id"], "Leo", False)
check("open: decline still recorded", app.SESSION["_ginvites"][-1]["state"] == "declined")
g = pair(state="planning", gid="gr-op2")
reset(g)
r = app.gi_invite(g["id"], "Anna", "Sofia")
r = app.gi_respond(r["invite"]["id"], "Sofia", True)
check("planning: accept waits for approval", r.get("awaiting_approval") is True, r)
r = app.gi_approve(g["id"], "Anna", "Sofia", True)
check("planning: approve makes a member", r.get("ok") is True and "Sofia" in names(g), r)
g = pair(state="cancelled", gid="gr-op3")
reset(g)
check("cancelled group still CLOSED", app.gi_invite(g["id"], "Anna", "Sofia").get("error") == "CLOSED")
late = legacy_invite(g, "Sofia")
app.gi_respond(late["id"], "Sofia", True)
check("cancelled group: accept still -> withdrawn", late["state"] == "withdrawn", late)

# ── 3. Организатор ушёл при открытом предложении роли ───────────────────────────────────────────
g = four(hours_ago=1)
reset(g)
check("offer to Marc", app.gi_role_offer(g["id"], "Mateo", "Marc").get("ok") is True)
r = app.gi_leave(g["id"], "Mateo")
check("leave ok, heir is the eldest (Jane)", r.get("ok") is True and g["owner"] == "Jane", g["owner"])
o = g["role_offer"]
check("offer closed as on any role change", o["state"] == "closed" and o.get("why") == "role_changed"
      and o.get("closed"), o)
check("role_from says Mateo left", (g.get("role_from") or {}).get("who") == "Mateo"
      and g["role_from"].get("how") == "left", g.get("role_from"))
pub = app._gi_role_public(g, "Jane")
check("heir: no open offer on screen", pub["role_offer"]["state"] == "closed", pub["role_offer"])
check("heir can hand over herself now", pub["can_hand_over"] is True, pub)
r = app.gi_role_respond(g["id"], "Marc", True)
check("addressee cannot take the role from the heir", r.get("error") == "NO_OPEN_OFFER"
      and g["owner"] == "Jane", (r.get("error"), g["owner"]))
check("heir can make her own offer", app.gi_role_offer(g["id"], "Jane", "Marc").get("ok") is True
      and g["role_offer"]["by"] == "Jane", g.get("role_offer"))
check("chat: left_heir once, nothing about the offer", codes(g["id"]).count("left_heir") == 1
      and "role_taken" not in codes(g["id"]), codes(g["id"]))
ago(g, "role_offer", 25)
app._gi_roles_due()
check("the heir's own offer still expires normally", g["role_offer"]["state"] == "expired", g["role_offer"])

# ── 4. Организатор ушёл посреди голосования за перехват ─────────────────────────────────────────
g = four(hours_ago=13)
reset(g)
check("Marc puts himself forward", app.gi_takeover(g["id"], "Marc").get("ok") is True)
app.gi_takeover_vote(g["id"], "Leo", True)
sil0 = codes(g["id"]).count("organiser_silent")
r = app.gi_leave(g["id"], "Mateo")
t = g["takeover"]
check("leave: heir Jane", r.get("ok") is True and g["owner"] == "Jane", g["owner"])
check("takeover closed as on any role change", t["state"] == "closed" and t.get("why") == "role_changed"
      and t.get("resolved"), t)
pub = app._gi_role_public(g, "Jane")
check("heir is not 'silent 12h' for Mateo's silence", pub["organiser_silent_h"] == 0, pub)
check("heir sees no open vote", pub["takeover"]["state"] == "closed", pub["takeover"])
check("vote after leave refused", app.gi_takeover_vote(g["id"], "Leo", True).get("error") == "NO_OPEN_VOTE")
check("candidate withdraw after leave refused",
      app.gi_takeover_withdraw(g["id"], "Marc").get("error") == "NO_OPEN_OFFER")
check("nobody can take over the fresh heir", not app._gi_role_public(g, "Leo")["can_take_over"])
ago(g, "takeover", 7)
app._gi_roles_due()
check("window end changes nothing: Jane stays", g["owner"] == "Jane" and g["takeover"]["state"] == "closed", g)
check("chat: no takeover_passed / takeover_failed", not ({"takeover_passed", "takeover_failed"}
                                                         & set(codes(g["id"]))), codes(g["id"]))
check("chat: no new 'organiser_silent' for the heir", codes(g["id"]).count("organiser_silent") == sil0,
      codes(g["id"]))

# Наследник — сам кандидат: голосование тоже гаснет, роль у него.
g = four(hours_ago=13, gid="gr-lv2")
reset(g)
app.gi_takeover(g["id"], "Jane")
app.gi_leave(g["id"], "Mateo")
check("heir is the candidate: vote closed, Jane organiser",
      g["owner"] == "Jane" and g["takeover"]["state"] == "closed", g.get("takeover"))

# ── 5. Обычный выход участника ничего этого не трогает ─────────────────────────────────────────
g = four(hours_ago=1, gid="gr-lv3")
reset(g)
app.gi_role_offer(g["id"], "Mateo", "Marc")
v0 = g.get("role_from")
r = app.gi_leave(g["id"], "Leo")
check("member leaves: ok, owner unchanged", r.get("ok") is True and g["owner"] == "Mateo", g["owner"])
check("member leaves: offer stays open", g["role_offer"]["state"] == "open", g["role_offer"])
check("member leaves: no role_from", g.get("role_from") == v0, g.get("role_from"))
check("member leaves: chat says left", "left" in codes(g["id"]) and "left_heir" not in codes(g["id"]), codes(g["id"]))
r = app.gi_role_respond(g["id"], "Marc", True)
check("offer still works after a member left", r.get("ok") is True and g["owner"] == "Marc", r)

g = four(hours_ago=13, gid="gr-lv4")
reset(g)
app.gi_takeover(g["id"], "Marc")
app.gi_leave(g["id"], "Leo")
check("voter leaves: vote stays open", g["takeover"]["state"] == "open" and g["owner"] == "Mateo", g["takeover"])

print("CLOSED LEAVE RESULT: %d ok, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
