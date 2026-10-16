# -*- coding: utf-8 -*-
"""Раунды плана 1:1 — борд «1:1 · Offline — new layout», разделы B/C (OF.20–20c, OF.21a–c, C3–C5, OF.19e).

    python3 tools/mplan_rounds_unit.py

Раунд 1 — план хозяина; каждое встречное до подтверждения — новый раунд, не больше трёх; на ответ
6 ч, просроченное снимается само при чтении. После третьего хозяин фиксирует версию (`fix`), гость
остаётся (`stay`) или выходит без последствий (`leave`). После подтверждения встречное — перенос
с тем же сроком. «Pick someone else» — кто уже принял приглашение на эту затею.
"""
import importlib.util
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = os.path.join(ROOT, "services", "matching")
TMP = tempfile.mkdtemp(prefix="kleal-mprounds-")
os.environ["KLEAL_STORE"] = os.path.join(TMP, "store.json")
os.environ["KLEAL_REPORT_EVIDENCE_DIR"] = os.path.join(TMP, "evidence")
sys.path.insert(0, SERVICE)
spec = importlib.util.spec_from_file_location("matching_mprounds", os.path.join(SERVICE, "app.py"))
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


H, G = 3600.0, None
now = time.time()


def fresh():
    app.SESSION.clear()
    app.SESSION["_requests"] = [
        {"id": "rq1", "from": "Mateo", "to": "Marta", "status": "accepted", "iid": "int1",
         "intent": {"id": "int1", "title": "Coffee"}, "updated": now - 50},
        {"id": "rq2", "from": "Mateo", "to": "Nuria", "status": "accepted", "iid": "",
         "intent": {"title": "Coffee"}, "updated": now - 40},
        {"id": "rq3", "from": "Mateo", "to": "Paula", "status": "pending", "iid": "int1",
         "intent": {"id": "int1", "title": "Coffee"}, "updated": now - 30},
        {"id": "rq4", "from": "Mateo", "to": "Leo", "status": "accepted", "iid": "int2",
         "intent": {"id": "int2", "title": "Padel"}, "updated": now - 20}]
    app.SESSION["_mplans"] = []
    app.SESSION["_messages"] = []


def codes(who, peer):
    return [m.get("code") or (m.get("sys") or {}).get("code") for m in app.thread(who, peer)]


fresh()
r = app.mp_propose("Mateo", "Marta", "Coffee", "offline", now + 48 * H, "Thu 19:30", "Gracia")
pid = r["plan"]["id"]
pl = r["plan"]
check("propose: round 1 of 3", pl["round"] == 1 and pl["max_rounds"] == 3, pl.get("round"))
check("propose: rounds_log has round 1 by host", [e["round"] for e in pl["rounds_log"]] == [1], pl["rounds_log"])
check("propose: guest has 6h to answer", abs((pl["round_ends_at"] or 0) - (time.time() + 6 * H)) < 5, pl["round_ends_at"])

r = app.mp_respond(pid, "Marta", "counter", now + 49 * H, "Thu 20:30")
pl = r["plan"]
check("guest counter = round 2", r.get("ok") and pl["round"] == 2, r)
check("counter has 6h deadline", abs((pl["round_ends_at"] or 0) - (time.time() + 6 * H)) < 5, pl["round_ends_at"])
check("pending carries round and expires_at", pl["pending"]["round"] == 2 and pl["pending"]["expires_at"])
r = app.mp_respond(pid, "Mateo", "counter", now + 50 * H, "Thu 21:00")
check("host counter = round 3", r["plan"]["round"] == 3, r)
check("round 3: host can fix", r["plan"]["can_fix"] is True)
check("round 3: guest cannot fix", app._mp_public(app._mp_find(pid), "Marta")["can_fix"] is False)
r = app.mp_respond(pid, "Marta", "counter", now + 51 * H, "Thu 22:00")
check("no 4th round", r.get("error") == "NO_ROUNDS_LEFT", r)
check("guest is not offered counter after round 3",
      "counter" not in app._mp_public(app._mp_find(pid), "Marta")["actions"])
check("host is offered fix", "fix" in app._mp_public(app._mp_find(pid), "Mateo")["actions"])
r = app.mp_respond(pid, "Marta", "fix", round_no=1)
check("guest fix refused", r.get("error") == "HOST_ONLY", r)
r = app.mp_respond(pid, "Mateo", "fix", round_no=9)
check("fix of unknown round refused", r.get("error") == "NO_SUCH_ROUND", r)
r = app.mp_respond(pid, "Mateo", "fix", round_no=2)
pl = r["plan"]
check("fix applies round 2 time", r.get("ok") and pl["starts_at"] == now + 49 * H and pl["when"] == "Thu 20:30", r)
check("fix clears pending, stays proposed", pl["pending"] is None and pl["state"] == "proposed")
gv = app._mp_public(app._mp_find(pid), "Marta")
check("guest sees final_by_host", gv["final_by_host"] is True and gv["fixed"]["round"] == 2, gv.get("fixed"))
hv = app._mp_public(app._mp_find(pid), "Mateo")
check("after fix host cannot re-fix", hv["can_fix"] is False and "fix" not in hv["actions"], hv["actions"])
check("re-fix refused", app.mp_respond(pid, "Mateo", "fix", round_no=1).get("error") == "ALREADY_FIXED")
check("guest has 6h for stay/leave", abs((gv["round_ends_at"] or 0) - (time.time() + 6 * H)) < 5, gv["round_ends_at"])
check("guest offered stay/leave, not confirm/decline",
      "stay" in gv["actions"] and "leave" in gv["actions"]
      and "confirm" not in gv["actions"] and "decline" not in gv["actions"], gv["actions"])
check("plan_fixed line reached guest", "plan_fixed" in codes("Marta", "Mateo"), codes("Marta", "Mateo"))
r = app.mp_respond(pid, "Marta", "stay")
check("stay -> confirmed", r.get("ok") and r["plan"]["state"] == "confirmed", r)
check("confirmed plan has no silence deadline", app._mp_find(pid).get("round_ends_at") is None)
check("after stay final_by_host is off, fixed kept",
      r["plan"]["final_by_host"] is False and r["plan"]["fixed"]["answer"] == "stay", r["plan"].get("fixed"))

# leave на втором плане
fresh()
pid = app.mp_propose("Mateo", "Marta", "Coffee", "offline", now + 48 * H, "Thu 19:30")["plan"]["id"]
app.mp_respond(pid, "Marta", "counter", now + 49 * H)
app.mp_respond(pid, "Mateo", "counter", now + 50 * H)
app.mp_respond(pid, "Mateo", "fix", round_no=3)
r = app.mp_respond(pid, "Mateo", "leave")
check("host cannot leave", r.get("error") == "GUEST_ONLY", r)
r = app.mp_respond(pid, "Marta", "leave")
check("leave -> cancelled, left_final", r.get("ok") and r["plan"]["state"] == "cancelled"
      and r["plan"]["cancel_kind"] == "left_final", r)
check("plan_left line reached host", "plan_left" in codes("Mateo", "Marta"), codes("Mateo", "Marta"))
r = app.mp_respond(pid, "Marta", "stay")
check("stay after leave refused", r.get("error") == "NOT_OPEN", r)

# accept_change в раунде 2 = confirmed
fresh()
pid = app.mp_propose("Mateo", "Marta", "Coffee", "offline", now + 48 * H)["plan"]["id"]
app.mp_respond(pid, "Marta", "counter", now + 49 * H)
r = app.mp_respond(pid, "Mateo", "accept_change")
check("accepting round 2 confirms on its time", r["plan"]["state"] == "confirmed" and r["plan"]["starts_at"] == now + 49 * H, r)

# перенос после подтверждения: срок 6 ч, без раундов, снимается сам
r = app.mp_respond(pid, "Mateo", "counter", now + 52 * H)
pend = r["plan"]["pending"]
check("reschedule after confirm: no round, 6h deadline", pend.get("round") is None and pend.get("expires_at"), pend)
check("reschedule does not change round", r["plan"]["round"] == 2, r["plan"]["round"])
p = app._mp_find(pid)
p["pending"]["expires_at"] = time.time() - 1
app._mp_sweep()
p = app._mp_find(pid)
check("expired reschedule dropped, plan intact", p["pending"] is None and p["state"] == "confirmed"
      and p["starts_at"] == now + 49 * H, p.get("pending"))
check("last_change = expired", (p.get("last_change") or {}).get("state") == "expired")
check("plan_change_expired line written", "plan_change_expired" in codes("Marta", "Mateo"), codes("Marta", "Mateo"))
check("old pending without expires_at is not swept",
      (lambda q: (q.update(pending={"by": "Mateo", "starts_at": now + 60 * H, "at": now}), app._mp_sweep(),
                  q["pending"] is not None)[-1])(app._mp_find(pid)))

# МОЛЧАНИЕ ДО ПОДТВЕРЖДЕНИЯ закрывает план без последствий
def expire(pid):
    app._mp_find(pid)["round_ends_at"] = time.time() - 1
    app._mp_sweep()
    return app._mp_find(pid)

fresh()
pid = app.mp_propose("Mateo", "Marta", "Coffee", "offline", now + 48 * H)["plan"]["id"]
p = expire(pid)
check("guest silent on round 1 -> plan closed", p["state"] == "cancelled" and p["cancel_kind"] == "expired_no_answer"
      and p["expired_silent"] == "Marta" and not p.get("cancelled_by"), p)
pv = app._mp_public(p, "Mateo")
check("projection gives silent name + id", pv["expired_silent"] and "expired_silent_id" in pv, pv.get("expired_silent"))
check("plan_expired line in the pair chat", "plan_expired" in codes("Mateo", "Marta"), codes("Mateo", "Mateo"))
check("pair is free for a new plan", app._mp_of("Mateo", "Marta") is None)
fresh()
pid = app.mp_propose("Mateo", "Marta", "Coffee", "offline", now + 48 * H)["plan"]["id"]
app.mp_respond(pid, "Marta", "counter", now + 49 * H)
p = expire(pid)
check("host silent on guest counter -> closed, host is the silent one",
      p["state"] == "cancelled" and p["expired_silent"] == "Mateo", p.get("expired_silent"))
fresh()
pid = app.mp_propose("Mateo", "Marta", "Coffee", "offline", now + 48 * H)["plan"]["id"]
app.mp_respond(pid, "Marta", "counter", now + 49 * H)
app.mp_respond(pid, "Mateo", "counter", now + 50 * H)
app.mp_respond(pid, "Mateo", "fix", round_no=1)
p = expire(pid)
check("guest silent after fix = left, no consequences", p["state"] == "cancelled"
      and p["cancel_kind"] == "expired_no_answer" and p["final_by_host"]["answer"] == "timeout", p.get("final_by_host"))
fresh()
pid = app.mp_propose("Mateo", "Marta", "Coffee", "offline", now + 48 * H)["plan"]["id"]
app.mp_respond(pid, "Marta", "confirm")
p = app._mp_find(pid); p["round_ends_at"] = time.time() - 1; app._mp_sweep()
check("confirmed plan never closed by silence", app._mp_find(pid)["state"] == "confirmed")
fresh()
pid = app.mp_propose("Mateo", "Marta", "Coffee", "offline", now + 48 * H)["plan"]["id"]
app._mp_find(pid).pop("round_ends_at"); app._mp_sweep()
check("plan from before the rule has no deadline and stays", app._mp_find(pid)["state"] == "proposed")
check("expiry visible via GET path too",
      (lambda q: (q.update(round_ends_at=time.time() - 1), app._mp_sweep(), q["state"])[-1])(app._mp_find(pid)) == "cancelled")

# старый план без журнала раундов: первый встречный достраивает раунд 1
fresh()
pid = app.mp_propose("Mateo", "Marta", "Coffee", "offline", now + 48 * H)["plan"]["id"]
p = app._mp_find(pid)
p.pop("rounds_log"); p.pop("round")
r = app.mp_respond(pid, "Marta", "counter", now + 49 * H)
check("legacy plan: log rebuilt with round 1", [e["round"] for e in r["plan"]["rounds_log"]] == [1, 2], r["plan"]["rounds_log"])

# OF.19e: кто уже принял по этой затее
fresh()
a = app.mp_alternatives("Mateo", "int1", "Coffee", "Marta")
names = [x["name"] for x in a["people"]]
check("alternatives: Nuria (by title, no iid), not Marta/Paula/Leo", names == ["Nuria"], a)
check("alternatives: Nuria is free", a["people"][0]["free"] is True)
app.mp_propose("Mateo", "Nuria", "Coffee", "offline", now + 48 * H)
check("alternatives: busy when a live plan exists", app.mp_alternatives("Mateo", "int1", "Coffee", "Marta")["people"][0]["free"] is False)
check("alternatives: other intent -> Leo only", [x["name"] for x in app.mp_alternatives("Mateo", "int2", "Padel")["people"]] == ["Leo"])
check("alternatives: not someone else's invites", app.mp_alternatives("Marta", "int1", "Coffee")["people"] == [])

# возраст в участниках и карточка альтернативы — из строки человека
fresh()
app._person = (lambda orig: (lambda x: {"age": 29, "area": "Gràcia", "interests": ["coffee", "books"],
                                         "summary": "Likes slow mornings", "verified": True}
                             if str(x).lower() in ("marta", "nuria") else orig(x)))(app._person)
pv = app.mp_propose("Mateo", "Marta", "Coffee", "offline", now + 48 * H)["plan"]
check("participants carry age", any(x.get("age") == 29 for x in pv["participants"]), pv["participants"])
check("participants carry gender key", all("gender" in x for x in pv["participants"]), pv["participants"])
alt = app.mp_alternatives("Mateo", "int1", "Coffee", "Marta")["people"][0]
app._person = (lambda orig: (lambda x: {"age": 31, "city": "Barcelona",
                                         "interests": {"explicit": ["padel", "wine"], "categories": ["sport"]}}
                             if str(x).lower() == "nuria" else orig(x)))(app._person)
alt2 = app.mp_alternatives("Mateo", "int1", "Coffee", "Marta")["people"][0]
check("dict-form interests -> explicit list, city fallback", alt2["interests"] == ["padel", "wine"]
      and alt2["area"] == "Barcelona", alt2)
check("alternative card: area/interests/summary", alt["area"] == "Gràcia" and alt["interests"] == ["coffee", "books"]
      and alt["summary"] and alt["verified"] is True, alt)

# адрес после отмены: кому был открыт — тому и остаётся; кто не подтверждал — не получает
fresh()
pid = app.mp_propose("Mateo", "Marta", "Coffee", "offline", now + 48 * H, address="Carrer de Verdi 12")["plan"]["id"]
app.mp_respond(pid, "Marta", "confirm")
app.mp_cancel(pid, "Mateo")
pm, pg = app._mp_public(app._mp_find(pid), "Mateo"), app._mp_public(app._mp_find(pid), "Marta")
check("after cancel of a confirmed plan both keep the address", pm["address"] and pg["address"], (pm["address"], pg["address"]))
fresh()
pid = app.mp_propose("Mateo", "Marta", "Coffee", "offline", now + 48 * H, address="Carrer de Verdi 12")["plan"]["id"]
app.mp_respond(pid, "Marta", "decline")
pm, pg = app._mp_public(app._mp_find(pid), "Mateo"), app._mp_public(app._mp_find(pid), "Marta")
check("guest who never confirmed never gets the address", pm["address"] and pg["address"] == "", (pm["address"], pg["address"]))

# борд «1:1 · Online»: чья ссылка, отзыв просьбы, «никто не вошёл», срок ответа об исходе
fresh()
pid = app.mp_propose("Mateo", "Marta", "Call", "online", now + 48 * H)["plan"]["id"]
app.mp_respond(pid, "Marta", "confirm")
r = app.mp_ask(pid, "Mateo", "link")
check("ask link recorded", r.get("ok") and app._mp_find(pid)["asks"]["link"]["by"] == "Mateo", r)
r = app.mp_ask(pid, "Marta", "link", cancel=True)
check("asked person can decline the ask", r.get("ok") and not app._mp_find(pid)["asks"].get("link"), r)
check("plan_ask_declined line", "plan_ask_declined" in codes("Mateo", "Marta"), codes("Mateo", "Marta"))
check("plan untouched by a declined ask", app._mp_find(pid)["state"] == "confirmed")
app.mp_ask(pid, "Mateo", "link")
r = app.mp_ask(pid, "Mateo", "link", cancel=True)
check("asker can take the ask back", r.get("ok") and "plan_ask_pulled" in codes("Marta", "Mateo"), r)
check("nothing to cancel -> NO_ASK", app.mp_ask(pid, "Mateo", "link", cancel=True).get("error") == "NO_ASK")
app.mp_address(pid, "Marta", link="https://meet.example/abc")
pv = app._mp_public(app._mp_find(pid), "Mateo")
check("link_by names who gave the link", pv["link_by"] == "Marta" and pv["link_set"], pv.get("link_by"))
check("feedback_expires_at = start + 24h", pv["feedback_expires_at"] == now + 48 * H + 24 * H, pv["feedback_expires_at"])
check("join window is 15 min, not yet nobody_joined", pv["join_closes_at"] == now + 48 * H + 900 and pv["nobody_joined"] is False)
p = app._mp_find(pid); p["starts_at"] = time.time() - 16 * 60
check("16 min in, nobody here -> nobody_joined", app._mp_public(p, "Mateo")["nobody_joined"] is True)
p.setdefault("live", {})["marta"] = {"status": "here", "t": time.time()}
pv = app._mp_public(p, "Mateo")
check("one joined -> not nobody_joined, joined flag on participant", pv["nobody_joined"] is False
      and [x["joined"] for x in pv["participants"]] == [False, True], pv["participants"])
fresh()
pid = app.mp_propose("Mateo", "Marta", "Coffee", "offline", now + 48 * H)["plan"]["id"]
app.mp_respond(pid, "Marta", "confirm")
p = app._mp_find(pid); p["starts_at"] = time.time() - 16 * 60
pv = app._mp_public(p, "Mateo")
check("in-person meeting never says nobody_joined", pv["nobody_joined"] is False and pv["join_closes_at"] is None)

print("MPLAN ROUNDS RESULT: %d ok, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
