# -*- coding: utf-8 -*-
"""Операционный слой админки: что живо, что копится, что застряло.

ЗАЧЕМ ОТДЕЛЬНЫЙ ФАЙЛ. app.py админки — полторы тысячи строк, из них семьдесят процентов страница.
Дописывать в него ещё и работу с базой и брокером значило бы окончательно потерять его читаемость;
здесь только «спросить состояние», без единой строки разметки.

ЧТО ИМЕННО ПОКАЗЫВАЕТСЯ И ПОЧЕМУ ИМЕННО ЭТО. Панель до сих пор отвечала на вопросы про подбор —
кого нашли, почему не нашли, — и была полностью слепа к тому, на чём система стоит. Три числа,
из-за отсутствия которых поломки жили неделями:

    outbox.stuck   задания, которые не удаётся отправить (пять попыток и больше);
    dead           то, что обработчик не осилил за шесть повторов;
    queue.depth    длина очереди — растёт, если воркер лёг или не успевает.

Ровно эти три молчали, когда обучение таксономии падало в несуществующий адрес. Теперь они на
первом экране.

ОЧЕРЕДЬ ОПРАШИВАЕТСЯ ЧЕРЕЗ passive-declare, а не через плагин управления: он поднимает ещё один
HTTP-порт и ещё одного демона на боксе, где памяти и так впритык, а нужен нам ровно счётчик
сообщений, который отдаёт обычное объявление очереди.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if os.path.join(ROOT, "shared") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "shared"))

import config  # noqa: E402

try:
    import db  # noqa: E402
except Exception:                              # база выключена — панель обязана работать и так
    db = None
try:
    import mq  # noqa: E402
except Exception:
    mq = None

TOPICS = ("teach.phrases",)                    # темы, которые панель показывает поимённо


def _svc(name, timeout=1.5):
    """Жив ли сервис. 404 и 401 — это «отвечает», а не «лежит»: у части ручки нет, админка за
    паролем. Показывать их красным значит каждый раз ходить проверять руками здоровую систему."""
    url = ("http://127.0.0.1:%d" % config.PORTS["llm"]) if name == "llm" else config.url(name)
    t0 = time.time()
    try:
        with urllib.request.urlopen(url + "/health", timeout=timeout) as r:
            body = r.read(4000)
            try:
                extra = json.loads(body.decode())
            except Exception:
                extra = {}
            return {"ok": r.status == 200, "ms": int((time.time() - t0) * 1000), "info": extra}
    except urllib.error.HTTPError as e:
        note = "нет /health" if e.code == 404 else ("под паролем" if e.code in (401, 403) else None)
        return {"ok": bool(note), "code": e.code, "note": note,
                "ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        return {"ok": False, "error": type(e).__name__, "ms": int((time.time() - t0) * 1000)}


def services():
    return {n: _svc(n) for n in ("llm", "onboarding", "profile", "matching",
                                 "buddy", "filtration", "gateway")}


def storage():
    """Состояние хранилища. При KLEAL_DB=json честно говорит, что база не ведущая, — иначе
    пустые цифры читались бы как «база сломалась»."""
    if db is None or not db.ENABLED:
        return {"mode": (db.MODE if db else "json"), "enabled": False}
    out = {"mode": db.MODE, "enabled": True, "ok": db.healthy(), "stats": dict(db.STATS)}
    try:
        out["outbox"] = db.outbox_stats()
    except Exception as e:
        out["outbox_error"] = str(e)[:200]
    try:
        with db._connect().connection() as c, c.cursor() as cur:
            cur.execute("select pg_size_pretty(pg_database_size(current_database()))")
            out["size"] = cur.fetchone()[0]
            cur.execute("select relname, n_live_tup from pg_stat_user_tables order by n_live_tup desc")
            out["tables"] = [{"name": r[0], "rows": r[1]} for r in cur.fetchall()]
    except Exception as e:
        out["size_error"] = str(e)[:200]
    return out


def queue():
    """Длины очередей. Пустой ответ при KLEAL_MQ=off — не ошибка, а «очередь выключена»."""
    if mq is None or not mq.ENABLED:
        return {"mode": (mq.MODE if mq else "off"), "enabled": False}
    out = {"mode": mq.MODE, "enabled": True, "stats": dict(mq.STATS), "queues": []}
    try:
        ch = mq._channel()
        names = []
        for t in TOPICS:
            names += [t, t + ".wait"]
        names.append(mq.DEAD_QUEUE)
        for n in names:
            try:
                # passive: только спросить, не создавать. Если очереди ещё нет — так и скажем,
                # а не заведём пустую и не сделаем вид, что всё в порядке.
                r = ch.queue_declare(n, passive=True)
                out["queues"].append({"name": n, "messages": r.method.message_count,
                                      "consumers": r.method.consumer_count})
            except Exception:
                ch = mq._channel()          # неудачный passive закрывает канал — берём новый
                out["queues"].append({"name": n, "missing": True})
        out["ok"] = True
    except Exception as e:
        out["ok"] = False
        out["error"] = "%s: %s" % (type(e).__name__, str(e)[:160])
    return out


def dead_list(limit=25):
    """Заглянуть в мёртвую очередь, НЕ вынимая сообщений.

    Каждое прочитанное возвращается обратно (`nack` с requeue): просмотр не имеет права быть
    разрушительным. Порядок после возврата не гарантируется, но для разбора затора он и не нужен.
    """
    if mq is None or not mq.ENABLED:
        return {"enabled": False, "items": []}
    items, tags = [], []
    try:
        ch = mq._channel()
        for _ in range(int(limit)):
            method, props, body = ch.basic_get(mq.DEAD_QUEUE, auto_ack=False)
            if method is None:
                break
            tags.append(method.delivery_tag)
            h = (props.headers or {}) if props else {}
            try:
                payload = json.loads(body.decode())
            except Exception:
                payload = {"_raw": body[:200].decode("utf-8", "replace")}
            items.append({"topic": h.get("topic"), "attempt": h.get("attempt"),
                          "error": h.get("error"), "payload": payload})
        for t in tags:
            ch.basic_nack(t, requeue=True)
        return {"enabled": True, "items": items}
    except Exception as e:
        return {"enabled": True, "items": items, "error": "%s: %s" % (type(e).__name__, str(e)[:160])}


def dead_retry(limit=50):
    """Вернуть мёртвые сообщения в работу.

    Это единственное действие панели, которое что-то меняет в очереди, и оно намеренно
    НЕ разрушительное: сообщение публикуется заново с обнулённым счётчиком попыток, а из мёртвой
    снимается только после успешной публикации. Кнопки «очистить мёртвую очередь» здесь нет и не
    будет — молча выбросить работу это ровно то, от чего мы уходили.
    """
    if mq is None or not mq.ENABLED:
        return {"ok": False, "error": "очередь выключена"}
    moved, failed = 0, 0
    try:
        ch = mq._channel()
        for _ in range(int(limit)):
            method, props, body = ch.basic_get(mq.DEAD_QUEUE, auto_ack=False)
            if method is None:
                break
            h = (props.headers or {}) if props else {}
            topic = str(h.get("topic") or TOPICS[0])
            try:
                payload = json.loads(body.decode())
            except Exception:
                ch.basic_nack(method.delivery_tag, requeue=True)
                failed += 1
                continue
            if mq.publish_direct(topic, payload, attempt=0):
                ch.basic_ack(method.delivery_tag)
                moved += 1
            else:
                ch.basic_nack(method.delivery_tag, requeue=True)
                failed += 1
        return {"ok": True, "returned": moved, "failed": failed}
    except Exception as e:
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, str(e)[:160])}


# ---------------------------------------------------------------- мост тем
def _match_get(path, timeout=10):
    with urllib.request.urlopen(config.MATCH_URL + path, timeout=timeout) as r:
        return json.loads(r.read().decode())


def bridge(q="", limit=60):
    """Что матчинг знает про фразы. Читаем ФАЙЛ матчинга, а не спрашиваем сервис: отдельной
    ручки «покажи весь мост» нет, и заводить её ради панели значило бы открыть наружу то, что
    наружу не нужно."""
    path = os.environ.get("KLEAL_PHRASE_TOPICS",
                          os.path.join(ROOT, "services", "matching", "phrase_topics.json"))
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return {"total": 0, "items": [], "error": str(e)[:200]}
    q = " ".join(str(q or "").lower().split())
    items = []
    for phrase, topics in data.items():
        if q and q not in phrase and not any(q in str(t) for t in topics):
            continue
        items.append({"phrase": phrase, "topics": list(topics)})
    items.sort(key=lambda x: x["phrase"])
    return {"total": len(data), "matched": len(items), "items": items[:int(limit)]}


def bridge_teach(phrase):
    """Научить мост одной фразе — через очередь, а не напрямую.

    Панель не ходит в фильтрацию сама намеренно: разбор фразы это вызов модели, секунда с
    лишним, и делать его внутри запроса админки значит подвесить страницу. Плюс тот же путь, что
    у приложения, — если он сломан, сломан он и для панели, и это видно сразу, а не когда-нибудь.
    """
    ph = " ".join(str(phrase or "").split())
    if not ph:
        return {"ok": False, "error": "пустая фраза"}
    if mq is None or not mq.ENABLED:
        return {"ok": False, "error": "очередь выключена — задание некуда поставить"}
    ok = mq.send("teach.phrases", {"phrases": [ph]})
    return {"ok": bool(ok), "phrase": ph}


def overview():
    """Всё, что нужно первому экрану, одним ответом."""
    out = {"services": services(), "storage": storage(), "queue": queue(), "ts": time.time()}
    worst = []
    st, q = out["storage"], out["queue"]
    for name, v in out["services"].items():
        if not v.get("ok"):
            worst.append("сервис %s не отвечает" % name)
    if st.get("enabled") and st.get("ok") is False:
        worst.append("база не отвечает")
    if (st.get("outbox") or {}).get("stuck"):
        worst.append("в outbox застряло: %d" % st["outbox"]["stuck"])
    if q.get("enabled") and q.get("ok") is False:
        worst.append("брокер не отвечает")
    for qq in (q.get("queues") or []):
        if qq.get("name") == (mq.DEAD_QUEUE if mq else "kleal.dead") and qq.get("messages"):
            worst.append("мёртвых сообщений: %d" % qq["messages"])
    out["alarms"] = worst
    return out
