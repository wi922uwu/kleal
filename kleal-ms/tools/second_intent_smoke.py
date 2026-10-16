# -*- coding: utf-8 -*-
"""Вторая затея к тому, с кем уже говорим: python3 tools/second_intent_smoke.py [адрес]

Сценарий с телефона владельца: он уже переписывался с человеком и нашёл его снова — под ДРУГУЮ
затею. До правки в переписке не менялось ничего: закреплённая полоса сверху занята живым планом по
прежней затее, а другого входа в карточку затеи с этого экрана нет. Здесь это проверяется живьём,
на настоящих ручках, а не рассуждением.
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7080").rstrip("/")
FAIL = []


def post(path, body):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return {"HTTP": e.code, "body": e.read().decode()[:200]}


def get(path, **q):
    try:
        with urllib.request.urlopen(BASE + path + "?" + urllib.parse.urlencode(q), timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return {"HTTP": e.code, "body": e.read().decode()[:200]}


def check(name, got, want):
    ok = got == want
    print("%s  %-54s %s (ждали %s)" % ("ok  " if ok else "СБОЙ", name, got, want))
    if not ok:
        FAIL.append(name)


def events(a, b, code):
    ms = (get("/api/agent/thread", self=a, **{"with": b}) or {}).get("messages") or []
    return [m for m in ms if ((m.get("sys") or {}).get("code")) == code]


# Имена свои на каждый прогон: хранилище живое, и вчерашняя пара исказила бы счёт.
_ST = str(int(time.time()))[-6:]
A, C = "Смоук" + _ST + "А", "Смоук" + _ST + "Б"
I1 = {"id": "sm_padel_" + _ST, "title": "Поиграть в падель", "topics": ["padel"],
      "type": "sport", "mode": "offline"}
I2 = {"id": "sm_kino_" + _ST, "title": "Сходить в кино", "topics": ["cinema"],
      "type": "culture", "mode": "offline"}

print("1. Первое приглашение — вся переписка и есть затея, событию там неоткуда взяться.")
r1 = post("/api/agent/propose", {"from": A, "to": C, "intent": I1})
check("первая заявка создана", bool(r1.get("id")), True)
check("на первом приглашении события НЕТ", len(events(A, C, "intent_new")), 0)

print()
print("2. Согласие и пара реплик — переписка живёт.")
post("/api/agent/respond", {"id": r1.get("id"), "self": C, "decision": "accept"})
post("/api/agent/message", {"from": A, "to": C, "text": "привет, давай сыграем"})
post("/api/agent/message", {"from": C, "to": A, "text": "давай"})
talk = [m for m in ((get("/api/agent/thread", self=A, **{"with": C}) or {}).get("messages") or [])
        if not m.get("sys")]
check("реплики на месте", len(talk), 2)

print()
print("3. Тот же человек найден под ВТОРУЮ затею.")
r2 = post("/api/agent/propose", {"from": A, "to": C, "intent": I2})
check("вторая заявка — отдельная запись", r2.get("id") != r1.get("id"), True)
rows = [r for r in ((get("/api/agent/outbox", self=A) or {}).get("requests") or []) if r.get("to") == C]
check("обе заявки живы", len(rows), 2)

ev = events(A, C, "intent_new")
check("в ленте появилось событие о новой затее", len(ev), 1)
if ev:
    sysd = ev[0].get("sys") or {}
    check("событие несёт заголовок НОВОЙ затеи", sysd.get("title"), "Сходить в кино")
    check("событие знает, чьё оно", sysd.get("by"), A)
    check("событие ссылается на новую заявку", sysd.get("rid"), r2.get("id"))
    # Строку рисует клиент по коду: русская фраза, собранная на сервере, приехала бы на
    # английский экран (см. _sys_msg).
    check("готовой фразы в событии нет", str(ev[0].get("text") or ""), "")

print()
print("4. Событие видит и второй — лента у пары одна.")
check("у второго то же событие", len(events(C, A, "intent_new")), 1)

print()
print("5. Повтор той же затеи не плодит событий: заявка «пересылается», а не создаётся заново.")
post("/api/agent/propose", {"from": A, "to": C, "intent": I2})
check("событие по-прежнему одно", len(events(A, C, "intent_new")), 1)

print()
if FAIL:
    print("СБОЕВ: %d — %s" % (len(FAIL), ", ".join(FAIL)))
    sys.exit(1)
print("вторая затея в существующей переписке: всё зелёное")
