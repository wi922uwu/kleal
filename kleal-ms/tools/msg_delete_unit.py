# -*- coding: utf-8 -*-
"""Удаление реплики в переписке 1:1 и список «Сообщений» — правки 17.10.2026.

    python3 tools/msg_delete_unit.py

Удалённый кружок не отдаёт собеседнику адрес и уходит с диска (если на файл не ссылается другая
реплика); цитаты удалённого в ответах становятся «удалено»; непрочитанное не считает удалённые,
а превью удалённой — как в ленте; пары с блокировкой в любую сторону в списке не показываются,
история /thread при этом открывается. Плюс «ничего не сломалось»: обычное удаление текста, чужое
и системное не удаляются, цитата неудалённого не меняется.
"""
import importlib.util
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = os.path.join(ROOT, "services", "matching")
TMP = tempfile.mkdtemp(prefix="kleal-msgdel-")
os.environ["KLEAL_STORE"] = os.path.join(TMP, "store.json")
os.environ["KLEAL_REPORT_EVIDENCE_DIR"] = os.path.join(TMP, "evidence")
os.environ["KLEAL_VIDEO_DIR"] = os.path.join(TMP, "video")
os.environ["KLEAL_VOICE_DIR"] = os.path.join(TMP, "voice")
sys.path.insert(0, SERVICE)
spec = importlib.util.spec_from_file_location("matching_msgdel", os.path.join(SERVICE, "app.py"))
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


def accepted(i, frm, to):
    return {"id": "rq%d" % i, "from": frm, "to": to, "status": "accepted", "iid": "int%d" % i,
            "version": 1, "intent": {"id": "int%d" % i, "title": "Coffee"},
            "created": now, "updated": now, "expires_at": now + 6 * 3600}


def fresh():
    app.SESSION.clear()
    app.SESSION["_requests"] = [accepted(1, "Mateo", "Marta"), accepted(2, "Mateo", "Nuria")]
    app.SESSION["_mplans"] = []
    app.SESSION["_messages"] = []
    app.SESSION["_gmsgs"] = []


def say(frm, to, text="", **kw):
    r = app.send_message(frm, to, text, **kw)
    assert r.get("ok"), r
    return r["id"]


def row_of(me, other, mid):
    return next((x for x in app.thread(me, other) if x.get("id") == mid), None)


def thr(me, who):
    return next((x for x in app.threads_for(me) if app._norm_name(x.get("who")) == app._norm_name(who)), None)


def new_video():
    v = app.video_store("c.mp4", "video/mp4", b"\x00" * 256, 3000)
    assert v.get("ok"), v
    return {k: v[k] for k in ("id", "url", "duration_ms", "mime_type")}


def vpath(v):
    return os.path.join(app.VIDEO_DIR, v["url"].rsplit("/", 1)[-1])


# 1. кружок: адрес не уезжает собеседнику, файл уходит с диска
fresh()
v = new_video()
mid = say("Mateo", "Marta", video=v)
check("video sent, file on disk, peer sees url", os.path.exists(vpath(v))
      and (row_of("Marta", "Mateo", mid) or {}).get("video", {}).get("url") == v["url"])
r = app.message_delete("Mateo", mid)
check("video delete ok", r.get("ok"), r)
x = row_of("Marta", "Mateo", mid) or {}
check("peer row: no video, deleted, empty text", "video" not in x and x.get("deleted") is True
      and x.get("text") == "", x)
check("video url gone from the whole peer thread", v["url"] not in json.dumps(app.thread("Marta", "Mateo")))
check("video file removed from disk", not os.path.exists(vpath(v)))
check("video url gone from threads list", v["url"] not in json.dumps(app.threads_for("Marta")))

# тот же адрес в другой ленте — файл живёт, пока на него ссылается кто-то ещё
fresh()
v = new_video()
m1 = say("Mateo", "Marta", video=v)
m2 = say("Mateo", "Nuria", video=v)
app.message_delete("Mateo", m1)
check("shared video: file kept while another row uses it", os.path.exists(vpath(v)))
check("shared video: other row still has it", (row_of("Nuria", "Mateo", m2) or {}).get("video", {}).get("url") == v["url"])
app.message_delete("Mateo", m2)
check("shared video: file removed with the last row", not os.path.exists(vpath(v)))
# ссылка из групповой ленты тоже держит файл
fresh()
v = new_video()
m1 = say("Mateo", "Marta", video=v)
app.SESSION["_gmsgs"].append({"id": "g1", "gid": "gr1", "frm": "Mateo", "text": "[video]", "kind": "video",
                              "video": dict(v), "t": now})
app.message_delete("Mateo", m1)
check("video used in a group: file kept", os.path.exists(vpath(v)))
# файла на диске уже нет — удаление всё равно проходит
fresh()
v = new_video()
m1 = say("Mateo", "Marta", video=v)
os.remove(vpath(v))
r = app.message_delete("Mateo", m1)
check("missing video file: delete still ok", r.get("ok") and "video" not in (row_of("Marta", "Mateo", m1) or {}), r)

# 2. цитаты удалённого в ответах
fresh()
src = say("Marta", "Mateo", "secret plan")
keep = say("Marta", "Mateo", "hello")
rep = say("Mateo", "Marta", "ok!", reply_to=src)
rep2 = say("Mateo", "Marta", "hi", reply_to=keep)
check("reply carries quote text", (row_of("Mateo", "Marta", rep) or {}).get("rt", {}).get("text") == "secret plan")
# строка из ДРУГОЙ пары с тем же id в цитате (подделка) — не наша, не трогаем
app.SESSION["_messages"].append({"id": "m_x", "pair": app._pair_key("Mateo", "Nuria"), "from": "Nuria",
                                 "to": "Mateo", "text": "x", "t": now, "u": now,
                                 "rt": {"id": src, "from": "Marta", "text": "secret plan"}})
time.sleep(0.01)
before = time.time()
time.sleep(0.01)
app.message_delete("Marta", src)
q = (row_of("Marta", "Mateo", rep) or {}).get("rt") or {}
check("quote of deleted: text wiped, deleted flag", q.get("text") == "" and q.get("deleted") is True, q)
check("quote of deleted: id and author kept", q.get("id") == src and q.get("from") == "Marta", q)
check("quote of deleted: not in the thread anywhere", "secret plan" not in json.dumps(app.thread("Mateo", "Marta")))
check("reply text itself untouched", (row_of("Marta", "Mateo", rep) or {}).get("text") == "ok!")
polled = [x.get("id") for x in app.thread("Mateo", "Marta", since=before)]
check("poll brings the changed reply to the peer", rep in polled and src in polled, polled)
q2 = (row_of("Marta", "Mateo", rep2) or {}).get("rt") or {}
check("quote of a kept message unchanged", q2.get("text") == "hello" and "deleted" not in q2, q2)
check("kept-quote reply not touched by the poll", rep2 not in polled, polled)
fake = next(x for x in app.SESSION["_messages"] if x["id"] == "m_x")
check("other pair's quote not touched", fake["rt"].get("text") == "secret plan" and "deleted" not in fake["rt"], fake)

# 3. непрочитанное и превью
fresh()
a = say("Marta", "Mateo", "one")
b = say("Marta", "Mateo", "two")
c = say("Marta", "Mateo", "three")
check("unread before delete = 3", (thr("Mateo", "Marta") or {}).get("unread") == 3, thr("Mateo", "Marta"))
app.message_delete("Marta", b)
check("unread skips deleted = 2", (thr("Mateo", "Marta") or {}).get("unread") == 2, thr("Mateo", "Marta"))
check("live last line preview unchanged", (thr("Mateo", "Marta") or {}).get("last") == "three"
      and "deleted" not in thr("Mateo", "Marta"), thr("Mateo", "Marta"))
app.message_delete("Marta", c)
t = thr("Mateo", "Marta") or {}
feed = row_of("Mateo", "Marta", c) or {}
check("deleted last line: preview like the feed", t.get("last") == feed.get("text") == ""
      and t.get("deleted") is True and feed.get("deleted") is True, (t, feed))
check("unread = 1 after second delete", t.get("unread") == 1, t)
check("sender's own preview also deleted", (thr("Marta", "Mateo") or {}).get("deleted") is True)
# голосовое: превью не должно говорить «голосовое», когда в ленте «удалено»
vid = "ab" * 16
voice = {"id": vid, "url": "/api/speech/audio/%s.m4a" % vid, "duration_ms": 2000,
         "transcript": "voice words", "mime_type": "audio/mp4"}
vm = say("Marta", "Mateo", voice=voice)
check("voice preview before delete", (thr("Mateo", "Marta") or {}).get("kind") == "voice")
app.message_delete("Marta", vm)
t = thr("Mateo", "Marta") or {}
check("deleted voice: no kind/voice/text in preview", t.get("kind") is None and not t.get("voice")
      and t.get("last") == "" and t.get("deleted") is True, t)
check("deleted voice: transcript gone from list", "voice words" not in json.dumps(app.threads_for("Mateo")))
app.thread_mark_read("Mateo", "Marta")
check("read clears unread", (thr("Mateo", "Marta") or {}).get("unread") == 0)

# 4. блокировка: из списка — да, история — нет
fresh()
say("Marta", "Mateo", "hola")
say("Nuria", "Mateo", "hey")
check("both threads listed before block", thr("Mateo", "Marta") and thr("Mateo", "Nuria"))
app.block_user("Marta", "Mateo", True)                    # блокирует собеседник
check("blocked by peer: pair gone from my list", thr("Mateo", "Marta") is None and thr("Mateo", "Nuria"))
check("blocker's list: pair gone too", thr("Marta", "Mateo") is None)
check("history still opens", [x.get("text") for x in app.thread("Mateo", "Marta")] == ["hola"])
check("sending still refused with BLOCKED", app.send_message("Mateo", "Marta", "?").get("error") == "BLOCKED")
app.block_user("Marta", "Mateo", False)
check("unblock: pair back in the list", thr("Mateo", "Marta") is not None)
app.block_user("Mateo", "Nuria", True)                    # блокирую я
check("blocked by me: pair gone, other stays", thr("Mateo", "Nuria") is None and thr("Mateo", "Marta"))
check("blocked by me: case-insensitive", thr("mateo", "NURIA") is None)

# 5. ничего не сломалось
fresh()
a = say("Mateo", "Marta", "first")
b = say("Mateo", "Marta", "second")
app.message_react("Marta", b, app.REACTIONS[0])
r = app.message_delete("Mateo", b)
x = row_of("Marta", "Mateo", b) or {}
check("plain delete: ok, text wiped, deleted, reactions dropped", r.get("ok") and x.get("text") == ""
      and x.get("deleted") is True and "r" not in x, x)
check("plain delete: neighbour untouched", (row_of("Marta", "Mateo", a) or {}).get("text") == "first"
      and not (row_of("Marta", "Mateo", a) or {}).get("deleted"))
check("not yours refused", app.message_delete("Marta", a).get("error") == "NOT_YOURS")
check("unknown id refused", app.message_delete("Mateo", "m_nope").get("error") == "NO_SUCH_MESSAGE")
with app._STORE_LOCK:
    app._sys_msg("Mateo", "Marta", "chat_ended")
sid = next(x["id"] for x in app.SESSION["_messages"] if x.get("sys"))
check("system row refused", app.message_delete("Mateo", sid).get("error") == "NOT_A_MESSAGE")
check("second delete is harmless", app.message_delete("Mateo", b).get("ok"))
check("sys row still the preview, not counted as unread", (thr("Marta", "Mateo") or {}).get("sys", {}).get("code") == "chat_ended"
      and (thr("Marta", "Mateo") or {}).get("unread") == 1, thr("Marta", "Mateo"))
rp = say("Marta", "Mateo", "re", reply_to=a)
check("reply to a live message still quotes it", (row_of("Mateo", "Marta", rp) or {}).get("rt", {}).get("text") == "first")
check("reply to another pair's message still refused",
      app.send_message("Mateo", "Nuria", "x", reply_to=a).get("error") == "NO_SUCH_MESSAGE")

print("MSG DELETE RESULT: %d ok, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
