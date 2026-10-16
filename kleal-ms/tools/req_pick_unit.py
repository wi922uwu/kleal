# -*- coding: utf-8 -*-
"""Приглашения 1:1: организатор выбирает из ответивших — борд «1:1 · Offline — new layout», раздел A
(OF.12d–16, C1a, N1, N2), решение владельца 11.10.2026.

    python3 tools/req_pick_unit.py

«Да» с признаком flow=pick → `answered` (чат не открыт, соседи целы); `pick_request` → выбранный
`accepted`, остальные по той же затее `not_picked`; до выбора оба могут передумать; организатор
молчит до `pick_by` → `expired` с причиной host_silent. Без признака — прежнее «первое да».
"""
import importlib.util
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = os.path.join(ROOT, "services", "matching")
TMP = tempfile.mkdtemp(prefix="kleal-reqpick-")
os.environ["KLEAL_STORE"] = os.path.join(TMP, "store.json")
os.environ["KLEAL_REPORT_EVIDENCE_DIR"] = os.path.join(TMP, "evidence")
sys.path.insert(0, SERVICE)
spec = importlib.util.spec_from_file_location("matching_reqpick", os.path.join(SERVICE, "app.py"))
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


def row(i, to, iid="int1", title="Coffee", frm="Mateo", status="pending"):
    return {"id": "rq%d" % i, "from": frm, "to": to, "status": status, "iid": iid, "version": 1,
            "intent": {"id": iid, "title": title} if iid else {"title": title},
            "created": now, "updated": now, "expires_at": now + 6 * 3600}


def fresh():
    app.SESSION.clear()
    app.SESSION["_requests"] = [row(1, "Marta"), row(2, "Nuria"), row(3, "Paula"),
                                row(4, "Leo", iid="int2", title="Padel"),
                                row(5, "Marta", frm="Otto", iid="int9", title="Coffee")]
    app.SESSION["_mplans"] = []
    app.SESSION["_messages"] = []


def st(i):
    return next(r for r in app.SESSION["_requests"] if r["id"] == "rq%d" % i)["status"]


fresh()
r = app.respond("rq1", "accept", "Marta", flow="pick")
check("yes with flow=pick -> answered", r.get("ok") and r["status"] == "answered" and r.get("pick_by"), r)
check("neighbours untouched by a yes", (st(2), st(3), st(4)) == ("pending", "pending", "pending"))
check("answered opens no chat and no plan right", not app._chat_exists("Mateo", "Marta")
      and not app._mp_matched("Mateo", "Marta"))
check("plan to an answered person refused",
      app.mp_propose("Mateo", "Marta", "Coffee", "offline", now + 48 * 3600).get("error") == "NOT_MATCHED")
check("second yes is the same answer", app.respond("rq1", "accept", "Marta", flow="pick").get("status") == "answered")
check("recipient sees answered in inbox", any(x["id"] == "rq1" and x["status"] == "answered" for x in app.inbox("Marta")))
check("sender sees answered in outbox", any(x["id"] == "rq1" and x["status"] == "answered" and x.get("pick_by")
                                             for x in app.outbox("Mateo")))
app.respond("rq2", "accept", "Nuria", flow="pick")
check("pick is sender-only", "only the sender" in str(app.pick_request("rq1", "Marta").get("error")))
check("cannot pick someone who has not answered", app.pick_request("rq3", "Mateo").get("error") == "NOT_ANSWERED")
r = app.pick_request("rq2", "Mateo")
check("pick -> accepted", r.get("ok") and r["status"] == "accepted" and st(2) == "accepted", r)
check("others on the same intent -> not_picked (answered and silent)",
      (st(1), st(3)) == ("not_picked", "not_picked") and sorted(r["closed"]) == ["rq1", "rq3"], r)
check("other intent and other sender untouched", (st(4), st(5)) == ("pending", "pending"))
tr = next(x for x in app.SESSION["_requests"] if x["id"] == "rq1")["trace"]
check("reason is picked_other, not seat_taken", tr.get("reason") == "picked_other", tr)
check("not_picked is visible to the recipient", any(x["id"] == "rq1" and x["status"] == "not_picked" for x in app.inbox("Marta")))
check("picked pair now has chat and plan right", app._chat_exists("Mateo", "Nuria") and app._mp_matched("Mateo", "Nuria"))
check("second pick refused", app.pick_request("rq1", "Mateo").get("error") == "ALREADY_RESOLVED")

# передумать до выбора — обе стороны
fresh()
app.respond("rq1", "accept", "Marta", flow="pick")
r = app.respond("rq1", "decline", "Marta")
check("answered guest can change mind", r.get("ok") and st(1) == "declined", r)
check("pick after change of mind refused", app.pick_request("rq1", "Mateo").get("error") == "ALREADY_RESOLVED")
app.respond("rq2", "accept", "Nuria", flow="pick")
r = app.withdraw_request("rq2", "Mateo")
check("sender can withdraw an answered invite", r.get("ok") and st(2) == "withdrawn", r)

# организатор молчит
fresh()
app.respond("rq1", "accept", "Marta", flow="pick")
next(x for x in app.SESSION["_requests"] if x["id"] == "rq1")["pick_by"] = time.time() - 1
app._expire_due()
x = next(x for x in app.SESSION["_requests"] if x["id"] == "rq1")
check("host silent past pick_by -> expired/host_silent", x["status"] == "expired"
      and x["trace"].get("reason") == "host_silent", x.get("trace"))
check("silent-guest expiry is still plain expired", (lambda y: (y.update(expires_at=time.time() - 1), app._expire_due(),
      y["status"] == "expired" and (y.get("trace") or {}).get("reason") != "host_silent")[-1])(
      next(x for x in app.SESSION["_requests"] if x["id"] == "rq3")))

# без iid — по названию; другой заголовок не трогаем
fresh()
for x in app.SESSION["_requests"][:3]:
    x["iid"] = ""; x["intent"] = {"title": "Coffee"}
app.SESSION["_requests"].append(dict(row(6, "Zoe", iid="", title="Walk")))
app.respond("rq1", "accept", "Marta", flow="pick")
app.pick_request("rq1", "Mateo")
check("no iid: same title closes siblings, other title stays",
      (st(2), st(3), st(6)) == ("not_picked", "not_picked", "pending"))

# старый клиент без признака — прежнее «первое да»
fresh()
r = app.respond("rq1", "accept", "Marta")
check("legacy yes -> accepted at once", r.get("ok") and r["status"] == "accepted" and st(1) == "accepted", r)
check("legacy: same-intent neighbours withdrawn (seat_taken)", (st(2), st(3), st(4)) == ("withdrawn", "withdrawn", "pending"))
fresh()
app.respond("rq2", "accept", "Nuria", flow="pick")
app.respond("rq1", "accept", "Marta")
check("legacy yes also closes an answered neighbour", st(2) == "withdrawn", st(2))

# блокировка закрывает и ответившего
fresh()
app.respond("rq1", "accept", "Marta", flow="pick")
app.block_user("Mateo", "Marta", True)
check("block closes an answered invite", st(1) == "withdrawn", st(1))

# повторная отправка ответившему ничего не сбрасывает
fresh()
app.respond("rq1", "accept", "Marta", flow="pick")
r = app.propose("Mateo", "Marta", {"id": "int1", "title": "Coffee"}, "")
check("re-propose to an answered person keeps the answer", r.get("status") == "answered" and r.get("id") == "rq1"
      and st(1) == "answered", r)

# главная: answered и свежий not_picked — только по признаку нового клиента
fresh()
app.respond("rq1", "accept", "Marta", flow="pick")
old = app.home_invites("Marta")["invites"]
new = app.home_invites("Marta", True)["invites"]
check("home without flag: answered is not shown as a new invite", [x["id"] for x in old] == ["rq5"], old)
check("home rows carry status", all(x.get("status") == "pending" for x in old), old)
row1 = next((x for x in new if x["id"] == "rq1"), {})
check("home with flag: answered row with pick_by", row1.get("status") == "answered" and row1.get("pick_by")
      and row1.get("answered_at"), row1)
app.respond("rq2", "accept", "Nuria", flow="pick")
app.pick_request("rq2", "Mateo")
row1 = next((x for x in app.home_invites("Marta", True)["invites"] if x["id"] == "rq1"), {})
check("home with flag: fresh not_picked with reason", row1.get("status") == "not_picked"
      and row1.get("reason") == "picked_other" and row1.get("closed_at"), row1)
next(x for x in app.SESSION["_requests"] if x["id"] == "rq1")["updated"] = time.time() - 25 * 3600
check("not_picked leaves home after a day", not any(x["id"] == "rq1" for x in app.home_invites("Marta", True)["invites"]))
check("accepted/declined never return to home", not any(x["id"] == "rq2" for x in app.home_invites("Nuria", True)["invites"]))

# пояс собеседника до плана: заявки, главная, выдача
fresh()
app._person = (lambda orig: (lambda x: {"id": "u_mateo", "name": "Mateo", "tz": "Europe/Madrid", "age": 34}
                             if str(x).lower() in ("mateo", "u_mateo") else orig(x)))(app._person)
check("inbox row carries sender tz", next(x for x in app.inbox("Marta") if x["id"] == "rq1").get("tz") == "Europe/Madrid")
check("home invite card carries tz", next(x for x in app.home_invites("Marta")["invites"] if x["id"] == "rq1")["from"].get("tz") == "Europe/Madrid")
cards = app._stamp_photo([{"id": "u_mateo", "name": "Mateo"}, {"name": "Demo"}])
check("search card carries tz, card without id untouched", cards[0].get("tz") == "Europe/Madrid" and "tz" not in cards[1], cards)

print("REQ PICK RESULT: %d ok, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
