# -*- coding: utf-8 -*-
"""Переписка: адресуемость сообщения и непрочитанное.

    python3 tools/messages_smoke.py [http://127.0.0.1:7080]

Проверяет ровно то, на чём держатся реакции, цитата, правка и удаление, — и то, что до сих пор
ломалось молча, без падений и без единой красной строки на экране:

  1. У СООБЩЕНИЯ УНИКАЛЬНЫЙ id. Был просто миллисекундой, и две реплики одной миллисекунды
     получали один id. Клиент склеивает ленту по id — одна строка затирала другую.

  2. КЛЮЧ ОТПРАВИТЕЛЯ (`client_id`) ВОЗВРАЩАЕТСЯ и делает отправку идемпотентной. Без него
     «отправить ещё раз» после неясного сбоя удваивает реплику у собеседника, а голосовое
     двоится всегда: сервер кладёт в текст расшифровку, а локальный пузырь пустой, и склеить
     их по тексту нечем.

  3. ОПРОС ВИДИТ ИЗМЕНЁННОЕ, а не только новое. `t` задаёт порядок в ленте и меняться не может,
     поэтому правка отмечается отдельным `u`, а опрос смотрит на больший из двух. Без этого
     реакцию и правку увидел бы только тот, кто их сделал.

  4. НЕПРОЧИТАННОЕ СЧИТАЕТ СЕРВЕР. Клиент считал его сам, отдельным запросом на каждую
     переписку — до десяти штук каждые пятнадцать секунд — и всё равно врал: у одиннадцатой
     переписки числа не бывало никогда.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7080").rstrip("/")
R = {"ok": 0, "fail": 0}
FAILED = []
S = int(time.time() * 1000) % 100000000 + os.getpid()
A = "MsgA%d" % S
B = "MsgB%d" % S


def call(path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return {"_http": e.code, "_body": e.read().decode("utf-8", "replace")[:200]}
    except Exception as e:
        return {"_err": "%s: %s" % (type(e).__name__, str(e)[:140])}


def check(name, cond, detail=""):
    R["ok" if cond else "fail"] += 1
    if not cond:
        FAILED.append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (("   " + str(detail)[:140]) if detail else ""))


def send(frm, to, text, client_id=None):
    body = {"from": frm, "to": to, "text": text}
    if client_id:
        body["client_id"] = client_id
    return call("/api/agent/message", body)


def thread(me, other, since=0):
    return call("/api/agent/thread?self=%s&with=%s&since=%s" % (me, other, since))


def threads(me):
    return (call("/api/agent/threads?self=%s" % me) or {}).get("threads") or []


print("=" * 76)
print("1. У КАЖДОГО СООБЩЕНИЯ СВОЙ id")
print("=" * 76)
# Подряд, без пауз: именно так две реплики попадают в одну миллисекунду.
ids = [send(A, B, "залп %d" % i).get("id") for i in range(12)]
check("все отправились", all(ids), ids)
check("ни один id не повторился", len(set(ids)) == len(ids),
      "повторов: %d" % (len(ids) - len(set(ids))))

print()
print("=" * 76)
print("2. КЛЮЧ ОТПРАВИТЕЛЯ И ПОВТОР ОТПРАВКИ")
print("=" * 76)
cid = "c-%d" % S
first = send(A, B, "одно и то же", cid)
again = send(A, B, "одно и то же", cid)
check("ключ возвращается обратно", first.get("cid") == cid, first)
check("повтор с тем же ключом не создаёт вторую реплику",
      first.get("id") == again.get("id"), (first.get("id"), again.get("id")))
body = thread(B, A).get("messages") or []
same = [m for m in body if m.get("cid") == cid]
check("в ленте собеседника она ровно одна", len(same) == 1, len(same))
check("клиенту есть по чему узнать свой пузырь", same and same[0].get("cid") == cid)

print()
print("=" * 76)
print("3. ОПРОС ВИДИТ И ИЗМЕНЁННОЕ")
print("=" * 76)
msgs = thread(A, B).get("messages") or []
check("у сообщений есть отметка изменения", all("u" in m for m in msgs[-3:]),
      [sorted(m.keys()) for m in msgs[-1:]])
check("пока ничего не меняли, она равна времени отправки",
      all(abs((m.get("u") or 0) - (m.get("t") or 0)) < 0.001 for m in msgs[-3:]))
newest = max((m.get("t") or 0) for m in msgs)
check("опрос с последнего момента приносит пусто",
      len((thread(A, B, newest).get("messages") or [])) == 0)
send(A, B, "после отсечки")
check("а новую реплику приносит",
      len((thread(A, B, newest).get("messages") or [])) == 1)

print()
print("=" * 76)
print("4. НЕПРОЧИТАННОЕ СЧИТАЕТ СЕРВЕР")
print("=" * 76)
row = [t for t in threads(B) if str(t.get("who") or "").lower() == A.lower()]
check("переписка видна в списке", len(row) == 1, threads(B))
if row:
    check("непрочитанные посчитаны и это не ноль", (row[0].get("unread") or 0) > 0, row[0])
    n_before = row[0]["unread"]
    call("/api/agent/thread-read", {"self": B, "with": A})
    row2 = [t for t in threads(B) if str(t.get("who") or "").lower() == A.lower()]
    check("после открытия переписки счётчик обнулился",
          row2 and (row2[0].get("unread") or 0) == 0, row2)
    # Своё сообщение себе же непрочитанным не считается — иначе бейдж горел бы на собственных
    # репликах, и человек ходил бы «читать» то, что сам только что написал.
    send(B, A, "мой ответ")
    row3 = [t for t in threads(B) if str(t.get("who") or "").lower() == A.lower()]
    check("своя реплика непрочитанной не считается",
          row3 and (row3[0].get("unread") or 0) == 0, row3)
    send(A, B, "и ещё одно")
    row4 = [t for t in threads(B) if str(t.get("who") or "").lower() == A.lower()]
    check("чужая — считается", row4 and (row4[0].get("unread") or 0) == 1, row4)
    check("счётчик не подменил собой ничего из прежнего",
          row4 and row4[0].get("who") and row4[0].get("t") and "last" in row4[0], row4)

print()
print("=" * 76)
print("итог: %d ok, %d fail" % (R["ok"], R["fail"]))
for f in FAILED:
    print("   не прошло: " + f)
sys.exit(1 if R["fail"] else 0)
