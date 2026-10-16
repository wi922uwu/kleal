# -*- coding: utf-8 -*-
"""После групповой встречи: отзыв и история. Отдельный хранилищем тест, без сети.

    python3 tools/gplan_feedback_unit.py

ЗАЧЕМ ОТДЕЛЬНО. Этот раздел жил в gplans_smoke и падал там шестью строками с тех пор, как сервер
начал принимать отзыв только ПОСЛЕ встречи (NOT_YET до `starts_at + GP_FEEDBACK_DELAY`): через HTTP
план в прошлом не завести — сервер честно отказывает IN_THE_PAST. Смоук теперь проверяет отказ до
встречи, а сама обратная связь проверяется здесь, на плане, чьё время уже прошло (аудит 27.09.2026).
"""
import importlib.util
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = os.path.join(ROOT, "services", "matching")
os.environ["KLEAL_STORE"] = os.path.join(tempfile.mkdtemp(prefix="kleal-gpfb-"), "store.json")
os.environ.setdefault("KLEAL_DB", "json")
sys.path.insert(0, SERVICE)
spec = importlib.util.spec_from_file_location("matching_gpfb", os.path.join(SERVICE, "app.py"))
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print("  ok   " + name)
    else:
        fail += 1
        print("  FAIL %s   %s" % (name, str(detail)[:240]))


now = time.time()
starts = now - app.GP_FEEDBACK_DELAY - 600          # встреча прошла, окно отзыва открыто
people = ["Anna", "Marc", "Jane", "Luis"]
g = {"id": "gpfb", "title": "Кофе", "topics": ["coffee"], "owner": "Anna", "state": "locked",
     "min_total": 3, "max_total": 6, "updated": now, "version": 1,
     "members": [{"name": n, "state": "joined", "joined": now - 86400 + i} for i, n in enumerate(people)]}
p = {"id": "gpfb-plan", "gid": "gpfb", "state": "locked", "when": "сб 19:00", "starts_at": starts,
     "version": 1, "responses": {n: {"state": "confirmed", "version": 1} for n in people},
     "feedback": {}, "created": starts - 86400, "updated": starts - 86400}
app.SESSION.clear()
app.SESSION["_gintents"] = [g]
app.SESSION["_gplans"] = [p]

f1 = app.gp_feedback("gpfb-plan", "Anna", happened=True, text="хорошо посидели", idem="f1")
check("первый ответил", f1.get("ok") is True, f1)
check("план ещё не в истории", (f1.get("answered"), f1.get("of")) == (1, 4), [f1.get("answered"), f1.get("of")])
check("повтор с тем же ключом — тот же ответ", app.gp_feedback("gpfb-plan", "Anna", happened=True, idem="f1") == f1)
nope = app.gp_feedback("gpfb-plan", "Sofia", happened=True)
check("не участник отзыв не оставляет", nope.get("error") == "NOT_A_PARTICIPANT", nope)
last = None
for n in people[1:]:
    last = app.gp_feedback("gpfb-plan", n, happened=False, reason="дождь")
check("когда ответили все — план закрыт", ((last or {}).get("plan") or {}).get("state") == "done", last)
hist = app.gp_for("Anna")
check("и уехал в историю", any(x.get("id") == "gpfb-plan" for x in hist.get("history") or []),
      [x.get("id") for x in hist.get("history") or []])
check("из активных пропал", not any(x.get("id") == "gpfb-plan" for x in hist.get("plans") or []))

p2 = dict(p, id="gpfb-future", starts_at=now + 86400, state="locked", feedback={})
app.SESSION["_gplans"].append(p2)
early = app.gp_feedback("gpfb-future", "Anna", happened=True)
check("до встречи отзыв не принимается", early.get("error") == "NOT_YET", early)

print("\nитог: %d ok, %d FAIL" % (ok, fail))
sys.exit(1 if fail else 0)
