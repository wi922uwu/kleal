# -*- coding: utf-8 -*-
"""Смена организатора группы — договор борда «GR · Offline — new layout», кадры GR.42–GR.44.

    python3 tools/gr_roles_unit.py

Перехват по голосованию (организатор молчит 12 ч, решают ответившие, 6 ч окно, организатор может
вернуться) и передача роли (одному участнику, 24 ч на ответ). Хранилище — временное.
"""
import importlib.util
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = os.path.join(ROOT, "services", "matching")
TMP = tempfile.mkdtemp(prefix="kleal-roles-")
os.environ["KLEAL_STORE"] = os.path.join(TMP, "store.json")
os.environ["KLEAL_REPORT_EVIDENCE_DIR"] = os.path.join(TMP, "evidence")
sys.path.insert(0, SERVICE)
spec = importlib.util.spec_from_file_location("matching_roles", os.path.join(SERVICE, "app.py"))
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


def fresh(hours_ago=13, gid="gr-roles"):
    """Собранная тройка без плана; все пришли `hours_ago` часов назад и с тех пор организатор молчит."""
    t0 = time.time() - hours_ago * 3600
    g = {"id": gid, "title": "BBQ by the beach", "owner": "Mateo", "state": "ready_to_plan",
         "min_total": 3, "max_total": 3, "updated": t0, "version": 1,
         "members": [{"name": "Mateo", "state": "joined", "joined": t0 - 60},
                     {"name": "Jane", "state": "joined", "joined": t0 - 30},
                     {"name": "Marc", "state": "joined", "joined": t0}]}
    app.SESSION.clear()
    app.SESSION["_gintents"] = [g]
    app.SESSION["_gplans"] = []
    app.SESSION["_gmsgs"] = []
    return g


def codes():
    return [(m.get("sys") or {}).get("code") for m in app.SESSION["_gmsgs"]]


def ago(g, key, hours):
    """Сдвинуть срок в прошлое, как будто прошло `hours` часов."""
    for k in ("takeover", "role_offer"):
        x = g.get(k)
        if x and key == k:
            for f in ("at", "closes", "expires"):
                if f in x:
                    x[f] = float(x[f]) - hours * 3600


# 1. Молчание и право предложить себя.
g = fresh(hours_ago=6)
check("6h: nobody can take over yet", not app._gi_role_public(g, "Jane")["can_take_over"])
check("6h: takeover refused NOT_SILENT", app.gi_takeover(g["id"], "Jane").get("error") == "NOT_SILENT")
g = fresh(hours_ago=13)
pub = app._gi_role_public(g, "Jane")
check("13h: Jane can take over", pub["can_take_over"] and pub["organiser_silent_h"] >= 12, pub)
check("organiser cannot take over himself", app.gi_takeover(g["id"], "Mateo").get("error") == "ALREADY_ORGANISER")
app._gi_roles_due()
check("silence line said once in chat", codes().count("organiser_silent") == 1, codes())
app._gi_roles_due()
check("silence line not repeated", codes().count("organiser_silent") == 1, codes())

# 2. Предложение и одно предложение за раз.
r = app.gi_takeover(g["id"], "Jane", idem="t1")
check("Jane puts herself forward", r.get("ok") is True and g["takeover"]["state"] == "open", r)
check("second offer refused OFFER_EXISTS", app.gi_takeover(g["id"], "Marc").get("error") == "OFFER_EXISTS")
tv = app._gi_role_public(g, "Marc")["takeover"]
check("only Marc votes (not Jane, not Mateo)", tv["voters"] == 1 and tv["i_vote"] is True, tv)
check("candidate does not vote", app.gi_takeover_vote(g["id"], "Jane", True).get("error") == "NOT_A_VOTER")
check("organiser does not vote", app.gi_takeover_vote(g["id"], "Mateo", False).get("error") == "NOT_A_VOTER")

# 3. Прошло — роль у Jane, Mateo остаётся в группе. Все ответили, но закрывается только по сроку.
r = app.gi_takeover_vote(g["id"], "Marc", True)
check("all voted: still open until the window ends", g["takeover"]["state"] == "open" and g["owner"] == "Mateo", g.get("takeover"))
check("second vote from the same voter is an update", app.gi_takeover_vote(g["id"], "Marc", True).get("ok"))
ago(g, "takeover", 7)
app._gi_roles_due()
check("vote passes at the end of the window", g["takeover"]["state"] == "passed" and g["owner"] == "Jane", g.get("takeover"))
check("role_from says vote from Mateo", (g.get("role_from") or {}).get("how") == "vote"
      and g["role_from"]["who"] == "Mateo", g.get("role_from"))
check("Mateo stays in the group", any(m["name"] == "Mateo" and m["state"] == "joined" for m in g["members"]))
check("chat says takeover_passed", "takeover_passed" in codes(), codes())
tv = app._gi_role_public(g, "Jane")["takeover"]
check("tally frozen after pass: 1 of 1, nobody waiting", tv["voters"] == 1 and tv["voted"] == 1
      and tv["waiting"] == [], tv)

# 4. Не прошло: против.
g = fresh()
app.gi_takeover(g["id"], "Jane")
app.gi_takeover_vote(g["id"], "Marc", False)
ago(g, "takeover", 7)
app._gi_roles_due()
check("no vote: failed, Mateo stays", g["takeover"]["state"] == "failed" and g["owner"] == "Mateo", g["takeover"])
check("result counts only", g["takeover"]["result"] == {"yes": 0, "no": 1, "silent": 0}, g["takeover"])

# 5. Время вышло — никто не ответил: не прошло.
g = fresh()
app.gi_takeover(g["id"], "Jane")
ago(g, "takeover", 7)
app._gi_roles_due()
check("timeout with no answers fails", g["takeover"]["state"] == "failed"
      and g["takeover"]["result"]["silent"] == 1 and g["owner"] == "Mateo", g["takeover"])

# 6. Организатор вернулся: оставить роль / отдать кандидату.
g = fresh()
app.gi_takeover(g["id"], "Jane")
check("only organiser can come back", app.gi_takeover_back(g["id"], "Marc").get("error") == "NOT_ORGANIZER")
app.gi_takeover_back(g["id"], "Mateo", hand=False)
check("keep the role stops the vote", g["takeover"]["state"] == "stopped" and g["owner"] == "Mateo", g["takeover"])
check("organiser is no longer silent", app._gi_role_public(g, "Jane")["organiser_silent_h"] == 0)
g = fresh()
app.gi_takeover(g["id"], "Jane")
app.gi_takeover_back(g["id"], "Mateo", hand=True)
check("hand it over makes Jane organiser at once", g["owner"] == "Jane" and g["role_from"]["how"] == "handed", g)

# 7. Кандидат снимает предложение.
g = fresh()
app.gi_takeover(g["id"], "Jane")
check("only candidate withdraws", app.gi_takeover_withdraw(g["id"], "Marc").get("error") == "NO_OPEN_OFFER")
app.gi_takeover_withdraw(g["id"], "Jane")
check("withdraw closes the vote", g["takeover"]["state"] == "withdrawn" and g["owner"] == "Mateo", g["takeover"])

# 8. Передача роли.
g = fresh(hours_ago=1)
pub = app._gi_role_public(g, "Mateo")
check("organiser can hand over", pub["can_hand_over"] is True, pub)
check("member cannot offer the role", app.gi_role_offer(g["id"], "Jane", "Marc").get("error") == "NOT_ORGANIZER")
r = app.gi_role_offer(g["id"], "Mateo", "Jane")
check("offer is open for 24h", r.get("ok") and g["role_offer"]["state"] == "open"
      and abs(g["role_offer"]["expires"] - g["role_offer"]["at"] - 24 * 3600) < 1, g.get("role_offer"))
check("second offer refused", app.gi_role_offer(g["id"], "Mateo", "Marc").get("error") == "OFFER_EXISTS")
check("someone else cannot answer", app.gi_role_respond(g["id"], "Marc", True).get("error") == "NO_OPEN_OFFER")
app.gi_role_respond(g["id"], "Jane", False)
check("decline keeps the role", g["owner"] == "Mateo" and g["role_offer"]["state"] == "declined"
      and g["role_offer"]["declined"] == ["Jane"], g["role_offer"])
app.gi_role_offer(g["id"], "Mateo", "Marc")
check("declined list carries over to next offer", g["role_offer"]["declined"] == ["Jane"], g["role_offer"])
app.gi_role_respond(g["id"], "Marc", True)
check("accept makes Marc organiser", g["owner"] == "Marc" and g["role_from"]["how"] == "offer", g)
g = fresh(hours_ago=1)
app.gi_role_offer(g["id"], "Mateo", "Jane")
ago(g, "role_offer", 25)
app._gi_roles_due()
check("offer expires after 24h", g["role_offer"]["state"] == "expired" and g["owner"] == "Mateo", g["role_offer"])
g = fresh(hours_ago=1)
app.gi_role_offer(g["id"], "Mateo", "Jane")
app.gi_role_withdraw(g["id"], "Mateo")
check("organiser withdraws the offer", g["role_offer"]["state"] == "withdrawn", g["role_offer"])

# 9. С планом — ни перехвата, ни передачи.
g = fresh()
app.SESSION["_gplans"] = [{"id": "p1", "gid": g["id"], "state": "proposed", "confirmed": ["Mateo"]}]
check("plan exists: takeover refused", app.gi_takeover(g["id"], "Jane").get("error") == "PLAN_EXISTS")
check("plan exists: no hand-over", app.gi_role_offer(g["id"], "Mateo", "Jane").get("error") == "PLAN_EXISTS")
check("plan exists: not silent", app._gi_role_public(g, "Jane")["organiser_silent_h"] == 0)

print("ROLES RESULT: %d ok, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
