# -*- coding: utf-8 -*-
"""Пауза «вас двое» — договор борда «GR · Offline — new layout», кадры GR.40–GR.40f.

    python3 tools/gr_hold_unit.py

12 часов паузы, потом вопрос обоим («Twelve hours passed») до двух часов до встречи; оба за один
на один — переход; кто-то отпустил или срок вышел — план отменён, группа остаётся. Хранилище —
временное.
"""
import importlib.util
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = os.path.join(ROOT, "services", "matching")
TMP = tempfile.mkdtemp(prefix="kleal-hold-")
os.environ["KLEAL_STORE"] = os.path.join(TMP, "store.json")
os.environ["KLEAL_REPORT_EVIDENCE_DIR"] = os.path.join(TMP, "evidence")
sys.path.insert(0, SERVICE)
spec = importlib.util.spec_from_file_location("matching_hold", os.path.join(SERVICE, "app.py"))
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


def fresh(starts_in_h=40, gid="gr-hold"):
    """Тройка с подтверждённым планом; Marc выходит — план на паузе."""
    now = time.time()
    g = {"id": gid, "title": "BBQ by the beach", "owner": "Mateo", "state": "planning",
         "min_total": 3, "max_total": 3, "updated": now, "version": 1,
         "members": [{"name": "Mateo", "state": "joined", "joined": now - 90},
                     {"name": "Jane", "state": "joined", "joined": now - 60},
                     {"name": "Marc", "state": "joined", "joined": now - 30}]}
    p = {"id": "gp-" + gid, "gid": gid, "owner": "Mateo", "version": 1, "round": 1,
         "when": "Fri 24 July, 20:30", "place": "Barceloneta", "starts_at": now + starts_in_h * 3600,
         "state": "confirmed", "confirmed": ["Mateo", "Jane", "Marc"], "mode": "offline"}
    app.SESSION.clear()
    app.SESSION["_gintents"] = [g]
    app.SESSION["_gplans"] = [p]
    app.SESSION["_gmsgs"] = []
    app.SESSION["_gvotes"] = []
    r = app.gi_leave(gid, "Marc")
    assert r.get("ok"), r
    return g, p


def codes():
    return [(m.get("sys") or {}).get("code") for m in app.SESSION["_gmsgs"]]


def back(p, hours):
    """Сдвинуть часы паузы в прошлое, как будто прошло `hours` часов."""
    h = p["hold"]
    for f in ("since", "ask_at", "until"):
        if h.get(f):
            h[f] = float(h[f]) - hours * 3600
    if p.get("starts_at"):
        p["starts_at"] = float(p["starts_at"]) - hours * 3600


# 1. Вход в паузу.
g, p = fresh()
check("plan on hold", p["state"] == "below_quorum" and "hold" in p, p)
pub = app._gp_public(p, "Mateo")["hold"]
check("hold ends 12h after", abs(pub["ends_at"] - pub["since"] - 12 * 3600) < 1 and not pub["ask"], pub)
check("answer refused before ask", app.gp_hold_answer(p["id"], "Jane", "let_go").get("error") == "NOT_ASKING")

# 2. 12 часов прошли — вопрос обоим, срок до двух часов до встречи.
back(p, 12.1)
app._gp_hold_due()
pub = app._gp_public(p, "Jane")["hold"]
check("ask opens after 12h", pub["ask"] is True and pub["of"] == 2 and pub["answered"] == 0, pub)
check("reply by = 2h before start", abs(pub["until"] - (p["starts_at"] - 2 * 3600)) < 1, pub)
check("chat says hold_ask once", codes().count("hold_ask") == 1, codes())
app._gp_hold_due()
check("hold_ask not repeated", codes().count("hold_ask") == 1, codes())
check("left person cannot answer", app.gp_hold_answer(p["id"], "Marc", "one_on_one").get("error") == "NOT_A_MEMBER")
check("bad choice refused", app.gp_hold_answer(p["id"], "Jane", "maybe").get("error") == "INVALID_CHOICE")

# 3. Один за один на один — ждём второго.
r = app.gp_hold_answer(p["id"], "Jane", "one_on_one")
pub = app._gp_public(p, "Jane")["hold"]
check("first yes recorded", r.get("ok") and pub["answered"] == 1 and pub["my_answer"] == "one_on_one"
      and p["state"] == "below_quorum", pub)
check("one_on_one_by lists Jane", pub["one_on_one_by"] == ["Jane"], pub)

# 4. Второй тоже — группа становится один на один, план закрыт.
r = app.gp_hold_answer(p["id"], "Mateo", "one_on_one")
check("both yes converts", g["state"] == "converted_1to1" and p["state"] == "cancelled"
      and p.get("cancel_reason") == "converted_1to1", (g["state"], p["state"], p.get("cancel_reason")))
check("chat says converted", "converted" in codes(), codes())

# 5. Отпустил один — план отменён сразу, группа остаётся.
g, p = fresh()
back(p, 12.1)
app._gp_hold_due()
app.gp_hold_answer(p["id"], "Mateo", "let_go")
check("let go cancels", p["state"] == "cancelled" and p["hold"]["why"] == "let_go"
      and g["state"] == "chat_open", (p["state"], p.get("hold"), g["state"]))
check("chat says hold_let_go", "hold_let_go" in codes(), codes())

# 6. Никто не ответил до срока — отменено (GR.40b).
g, p = fresh()
back(p, 12.1)
app._gp_hold_due()
back(p, 30)                      # и срок ответа, и встреча уехали в прошлое
app._gp_hold_due()
check("deadline cancels", p["state"] == "cancelled" and p["hold"]["why"] == "expired", p.get("hold"))
check("chat says hold_expired", "hold_expired" in codes(), codes())
pub = app._gp_public(p, "Jane")["hold"]
check("public keeps the closed hold", pub["closed"] and pub["why"] == "expired", pub)
check("cancelled plan asks no feedback", app._gp_public(p, "Jane")["feedback_due"] is False)
gp = app._gi_public(g, "Jane")
check("group shows closed_plan, not plan", gp.get("plan") is None
      and (gp.get("closed_plan") or {}).get("state") == "cancelled", (gp.get("plan"), gp.get("closed_plan")))

# 7. Третий пришёл во время паузы — пауза снята.
g, p = fresh()
g["members"].append({"name": "Elly", "state": "joined", "joined": time.time()})
app._gp_recount(g["id"])
check("quorum back clears hold", p["state"] == "proposed" and "hold" not in p, p)

# 8. Встреча скоро: 12 часов не помещаются — вопрос сразу в срок, без лишнего ожидания.
g, p = fresh(starts_in_h=8)
pub = app._gp_public(p, "Mateo")["hold"]
check("short hold ends at the deadline", abs(pub["ends_at"] - (p["starts_at"] - 2 * 3600)) < 1, pub)

# 9. Пауза до появления счёта: часы идут с этой минуты, прошедшую встречу не трогаем.
g, p = fresh()
p.pop("hold")
app._gp_hold_due()
check("legacy hold starts now", "hold" in p and p["state"] == "below_quorum", p)
g, p = fresh()
p.pop("hold")
p["starts_at"] = time.time() - 3600
app._gp_hold_due()
check("past meeting untouched", "hold" not in p and p["state"] == "below_quorum", p)

print("HOLD RESULT: %d ok, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
