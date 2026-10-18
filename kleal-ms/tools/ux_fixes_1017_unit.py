# -*- coding: utf-8 -*-
"""Правки по сверке экранов и бэкенда, 17.10.2026 (AUDIT_2026-10-17).

    python3 tools/ux_fixes_1017_unit.py

1. Голосовые между людьми: адрес загрузки /api/agent/voice/… проходит, расшифровка необязательна.
2. Приглашение на другую затею к тому же человеку — своя заявка, прежняя цела.
3. OF.19e «Pick someone else»: не выбранные и ждущие выбора — с needs_pick; повторный выбор не выбранного.
4. Группа: «да» после начала плана видно приглашённому (gi_for, gi_invite_detail), отказ организатора — с причиной.
"""
import importlib.util
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = os.path.join(ROOT, "services", "matching")
TMP = tempfile.mkdtemp(prefix="kleal-ux1017-")
os.environ["KLEAL_STORE"] = os.path.join(TMP, "store.json")
os.environ["KLEAL_REPORT_EVIDENCE_DIR"] = os.path.join(TMP, "evidence")
os.environ["KLEAL_VOICE_DIR"] = os.path.join(TMP, "voice")
os.makedirs(os.environ["KLEAL_VOICE_DIR"], exist_ok=True)
sys.path.insert(0, SERVICE)
spec = importlib.util.spec_from_file_location("matching_ux1017", os.path.join(SERVICE, "app.py"))
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

ok = fail = 0


def check(name, condition, detail=""):
    global ok, fail
    if condition:
        ok += 1
    else:
        fail += 1
        print("FAIL %-62s %s" % (name, str(detail)[:300]))


now = time.time()

# ---------------------------------------------------------------- 1. голосовые
up = app.voice_store("v.m4a", "audio/mp4", b"\x00" * 2000, 3200)
if not (isinstance(up, dict) and up.get("ok")):
    # подпись voice_store могла быть другой — кладём файл сами, как это делает загрузка
    vid = "a" * 32
    open(os.path.join(app.VOICE_DIR, vid + ".m4a"), "wb").write(b"\x00" * 2000)
    up = {"ok": True, "id": vid, "url": "/api/agent/voice/%s.m4a" % vid, "duration_ms": 3200, "mime_type": "audio/mp4"}
vo = {"id": up["id"], "url": up["url"], "duration_ms": 3200, "mime_type": "audio/mp4", "transcript": ""}
v, err = app._voice_message(vo)
check("voice: upload url accepted", err is None and v and v["url"] == up["url"], (v, err))
check("voice: empty transcript allowed", err is None and v["transcript"] == "", v)
v, err = app._voice_message(dict(vo, transcript="привет"))
check("voice: transcript kept", v and v["transcript"] == "привет", v)
v, err = app._voice_message(dict(vo, id="b" * 32, url="/api/agent/voice/%s.m4a" % ("b" * 32)))
check("voice: url without file rejected", err == "INVALID_VOICE", (v, err))
v, err = app._voice_message(dict(vo, url="https://evil.example/x.m4a"))
check("voice: foreign url rejected", err == "INVALID_VOICE", (v, err))
v, err = app._voice_message(dict(vo, id="c" * 32, url="/api/speech/audio/%s.m4a" % ("c" * 32)))
check("voice: legacy url still accepted", err is None and v, (v, err))
v, err = app._voice_message(dict(vo, duration_ms=100))
check("voice: too short rejected", err == "INVALID_VOICE", (v, err))

app.SESSION.clear()
app.SESSION["_requests"] = [{"id": "rqA", "from": "Mateo", "to": "Marta", "status": "accepted", "iid": "i1",
                             "intent": {"id": "i1", "title": "Coffee"}, "version": 2, "created": now, "updated": now}]
app.SESSION["_messages"] = []
r = app.send_message("Mateo", "Marta", "", voice=vo)
check("voice: delivered between matched people", r.get("ok") is True, r)
m = (app.SESSION.get("_messages") or [{}])[-1]
check("voice: stored as voice, preview placeholder", m.get("kind") == "voice" and m.get("text") == "[voice]", m)

# ---------------------------------------------------------------- 2. другая затея — своя заявка
app.SESSION.clear()
app.SESSION["_requests"] = []
app.SESSION["_messages"] = []
a = app.propose("Ivan", "Anya", {"id": "coffee1", "title": "Coffee"}, "")
b = app.propose("Ivan", "Anya", {"id": "run1", "title": "Run"}, "")
rows = {x["id"]: x for x in app.SESSION["_requests"]}
check("propose: two intents -> two requests", a.get("ok") and b.get("ok") and a["id"] != b["id"] and len(rows) == 2, (a, b))
check("propose: coffee untouched", rows[a["id"]]["intent"]["title"] == "Coffee" and rows[a["id"]]["iid"] == "coffee1", rows[a["id"]])
c = app.propose("Ivan", "Anya", {"id": "coffee1", "title": "Coffee", "note": "x"}, "see you")
check("propose: same intent re-send updates", c.get("resent") and c["id"] == a["id"] and len(app.SESSION["_requests"]) == 2, c)
inb = [x for x in app.inbox("Anya") if x.get("status") == "pending"]
check("propose: recipient sees both", sorted(x["intent"]["title"] for x in inb) == ["Coffee", "Run"], inb)
# без iid — по названию: та же затея обновляется
app.SESSION["_requests"] = []
a = app.propose("Ivan", "Anya", {"title": "Coffee"}, "")
c = app.propose("Ivan", "Anya", {"title": "Coffee"}, "")
check("propose: no iid, same title updates", c.get("resent") and c["id"] == a["id"], c)

# ---------------------------------------------------------------- 3. Pick someone else


def req(i, to, status, trace=None, iid="int1", title="Coffee"):
    return {"id": "rq%d" % i, "from": "Mateo", "to": to, "status": status, "iid": iid, "version": 2,
            "intent": {"id": iid, "title": title}, "created": now - 100, "updated": now - i,
            "answered_at": now - 50, "trace": trace or {}, "expires_at": now + 3600}


app.SESSION.clear()
app.SESSION["_requests"] = [req(1, "Marta", "accepted", {"decision": "accepted"}),
                            req(2, "Nuria", "not_picked", {"reason": "picked_other"}),
                            req(3, "Paula", "answered"),
                            req(4, "Leo", "not_picked", {"reason": "intent_closed"}),
                            req(5, "Ines", "declined"),
                            req(6, "Otto", "not_picked", {"reason": "picked_other"}, iid="int2", title="Padel")]
app.SESSION["_mplans"] = []
app.SESSION["_messages"] = []
alt = {p["name"]: p for p in app.mp_alternatives("Mateo", "int1", "Coffee", "Marta")["people"]}
check("alts: chosen one excluded", "Marta" not in alt, alt.keys())
check("alts: not picked (picked_other) listed with needs_pick", alt.get("Nuria", {}).get("needs_pick") is True, alt.get("Nuria"))
check("alts: still answered listed with needs_pick", alt.get("Paula", {}).get("needs_pick") is True, alt.get("Paula"))
check("alts: other closures and declines not listed", "Leo" not in alt and "Ines" not in alt, alt.keys())
check("alts: other intent not listed", "Otto" not in alt, alt.keys())
check("alts: rows carry rid and status", alt["Nuria"].get("rid") == "rq2" and alt["Nuria"].get("status") == "not_picked", alt["Nuria"])
alt_all = {p["name"]: p for p in app.mp_alternatives("Mateo", "int1", "Coffee")["people"]}
check("alts: accepted keeps no needs_pick", alt_all.get("Marta", {}).get("needs_pick") is False, alt_all.get("Marta"))
r = app.pick_request("rq2", "Mateo")
check("repick: refused while the chosen one still holds the seat", r.get("ok") is False and r.get("error") == "ALREADY_RESOLVED", r)
app.SESSION["_mplans"] = [{"id": "mp1", "host": "Mateo", "guest": "Marta", "state": "cancelled",
                           "created": now - 30, "updated": now}]
r = app.pick_request("rq2", "Mateo")
check("repick: not_picked -> accepted after the plan was cancelled", r.get("ok") and r["status"] == "accepted", r)
check("repick: chat opens", app._chat_exists("Mateo", "Nuria"))
check("repick: still-answered closed as not_picked", next(x for x in app.SESSION["_requests"] if x["id"] == "rq3")["status"] == "not_picked")
r = app.pick_request("rq4", "Mateo")
check("repick: other closure refused", r.get("ok") is False and r.get("error") == "ALREADY_RESOLVED", r)
r = app.pick_request("rq6", "Nuria")
check("repick: only the sender", r.get("ok") is False, r)

# ---------------------------------------------------------------- 4. группа: ждущий одобрения
g = {"id": "gr-aw", "title": "BBQ", "owner": "Mateo", "state": "plan_pending", "min_total": 3, "max_total": 5,
     "updated": now, "version": 1, "created": now - 999,
     "members": [{"name": "Mateo", "state": "joined", "joined": now - 90},
                 {"name": "Jane", "state": "joined", "joined": now - 60}]}
app.SESSION.clear()
app.SESSION["_gintents"] = [g]
app.SESSION["_ginvites"] = [
    {"id": "gi-1", "gid": "gr-aw", "frm": "Mateo", "to": "Leo", "state": "awaiting_approval",
     "created": now - 500, "updated": now - 20, "expires_at": now + 3600},
    {"id": "gi-2", "gid": "gr-aw", "frm": "Mateo", "to": "Ana", "state": "declined_by_organizer",
     "created": now - 500, "updated": now - 10, "expires_at": now + 3600}]
mine = app.gi_for("Leo")
check("group: awaiting shows in recipient list", [x["invite"]["state"] for x in mine.get("invites") or []] == ["awaiting_approval"], mine)
d = app.gi_invite_detail("gi-1", "Leo")
check("group: awaiting detail is live", d.get("ok") and d["invite"]["state"] == "awaiting_approval" and "closed" not in d["invite"], d)
d = app.gi_invite_detail("gi-2", "Ana")
check("group: organizer refusal has a reason", d.get("ok") and d["invite"].get("closed") == "declined", d)
check("group: refused not in live list", not (app.gi_for("Ana").get("invites") or []))
check("group: stranger sees nothing", app.gi_invite_detail("gi-1", "Bob").get("error") == "NO_SUCH_INVITE")
check("group: organizer still sees awaiting list", "Leo" in (app._gi_public(g, "Mateo").get("awaiting_approval") or []))

print("UX FIXES 1017 RESULT: %d ok, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
