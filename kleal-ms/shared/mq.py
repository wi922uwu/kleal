# -*- coding: utf-8 -*-
"""RabbitMQ: очередь заданий с ретраями, которая не может потерять работу молча.

ЗАЧЕМ. Межсервисные вызовы были синхронным HTTP без единого повтора, а обучение таксономии —
«выстрелил и забыл»: поток бросал POST матчингу и уходил, не дожидаясь ответа. После
переписывания матчинга адрес перестал существовать, и открытки НЕДЕЛЯМИ падали в несуществующий
ящик. Ни ошибки на экране, ни алерта — единственным следом был лог, который никто не читает.
Счётчик TEACH_STATS в buddy — шрам от этого случая.

ТРИ ПРАВИЛА, ИЗ КОТОРЫХ ВСЁ СЛЕДУЕТ.

1. ЗАПРОС ЧЕЛОВЕКА НЕ ЖДЁТ ОЧЕРЕДЬ. Публикация идёт в `outbox` — таблицу в той же базе, что и
   сами данные, ТОЙ ЖЕ транзакцией. Дальше отдельный ретранслятор переносит задания в Rabbit.
   Поэтому «данные записались, а задание потерялось» невозможно по построению: либо обе записи,
   либо ни одной. И Rabbit может лежать сколько угодно — человек этого не заметит.

2. НЕУДАЧА НЕ ТЕРЯЕТСЯ, А ОТКЛАДЫВАЕТСЯ. Обработчик сказал «не смог» — сообщение уезжает в
   очередь ожидания с TTL и возвращается обратно через 5 секунд, потом 30, потом 5 минут
   (шесть попыток, дальше — мёртвая очередь). Задержка растёт намеренно: если сервис лежит,
   долбить его раз в секунду значит мешать ему подняться.

3. МЁРТВОЕ ВИДНО. То, что не удалось за шесть попыток, лежит в `kleal.dead` и считается в
   /health. Тихая потеря — то, из-за чего всё и случилось; шумная чинится в день появления.

ОТКАТ В ОДНУ ПЕРЕМЕННУЮ. `KLEAL_MQ=off` (по умолчанию) — pika не импортируется, публикация
возвращает False, вызывающий работает как раньше. `KLEAL_MQ=on` — очередь ведущая.
"""
import json
import os
import threading
import time

MODE = os.environ.get("KLEAL_MQ", "off").strip().lower()        # off | on
URL = os.environ.get("KLEAL_MQ_URL", "amqp://kleal:kleal@127.0.0.1:5672/%2F")
ENABLED = MODE == "on"

EXCHANGE = "kleal"                 # основной обмен, direct по topic
RETRY_EXCHANGE = "kleal.retry"     # сюда уезжает неудача; TTL возвращает её в основной
DEAD_QUEUE = "kleal.dead"

# Задержки повторов. Шесть попыток: секунды, полминуты, пять минут — этого хватает пережить и
# перезапуск сервиса, и получасовую недоступность модели.
BACKOFF_MS = [5_000, 30_000, 120_000, 300_000, 900_000, 1_800_000]
MAX_ATTEMPTS = len(BACKOFF_MS)

STATS = {"published": 0, "publish_failed": 0, "consumed": 0, "retried": 0,
         "dead": 0, "last_error": None}

# СОЕДИНЕНИЕ ЛОКАЛЬНО ДЛЯ ПОТОКА, И ЭТО НЕ ПЕДАНТИЗМ.
#
# `BlockingConnection` в pika потокобезопасным не является: он ведёт свой ввод-вывод сам и
# ожидает, что его дёргает один поток. Общее соединение у воркера (который блокируется на
# `start_consuming`) и у ретранслятора (который публикует раз в две секунды из другого потока)
# ломается сразу — в логе это `AssertionError: _AsyncTransportBase._initate_abort() expected
# _STATE_ABORTED_BY_USER`, и выглядит как «брокер отвалился», хотя брокер ни при чём.
# Поймано на первой же проверке живучести очереди.
_state = threading.local()


def _pika():
    import pika
    return pika


def _channel():
    """Соединение ЭТОГО потока и объявленная топология. Пересоздаётся при обрыве — Rabbit роняет
    idle-каналы, и держаться за мёртвый значит терять первую же публикацию после паузы."""
    pika = _pika()
    conn = getattr(_state, "conn", None)
    if conn is not None and conn.is_open:
        try:
            return conn.channel()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
    params = pika.URLParameters(URL)
    params.heartbeat = 30
    params.blocked_connection_timeout = 15
    conn = pika.BlockingConnection(params)
    _state.conn = conn
    ch = conn.channel()
    _declare(ch)
    return ch


def _declare(ch):
    """Топология. Объявляется обеими сторонами и идемпотентна: кто первым поднялся, тот и создал."""
    ch.exchange_declare(EXCHANGE, exchange_type="direct", durable=True)
    ch.exchange_declare(RETRY_EXCHANGE, exchange_type="direct", durable=True)
    ch.queue_declare(DEAD_QUEUE, durable=True)


def declare_topic(ch, topic):
    """Пара очередей на тему: рабочая и её комната ожидания.

    Ожидание — обычная очередь БЕЗ потребителя: сообщение лежит в ней, пока не истечёт TTL, и
    dead-letter возвращает его в рабочую. Так задержка получается без единого спящего потока.
    """
    ch.queue_declare(topic, durable=True, arguments={
        "x-dead-letter-exchange": RETRY_EXCHANGE,
        "x-dead-letter-routing-key": topic,
    })
    ch.queue_bind(topic, EXCHANGE, routing_key=topic)
    wait = topic + ".wait"
    ch.queue_declare(wait, durable=True, arguments={
        "x-dead-letter-exchange": EXCHANGE,
        "x-dead-letter-routing-key": topic,
    })
    ch.queue_bind(wait, RETRY_EXCHANGE, routing_key=topic)
    return wait


def publish_direct(topic, payload, attempt=0):
    """Отправить в Rabbit СЕЙЧАС. Ретранслятор зовёт это; прикладной код — нет, он пишет в outbox.

    `delivery_mode=2` и подтверждения издателя: без них Rabbit отвечает «принял» до записи на
    диск, и перезапуск брокера съедает всё, что было в полёте.
    """
    if not ENABLED:
        return False
    pika = _pika()
    ch = _channel()
    declare_topic(ch, topic)
    ch.confirm_delivery()
    body = json.dumps(payload, ensure_ascii=False, default=str).encode()
    props = pika.BasicProperties(delivery_mode=2, content_type="application/json",
                                 headers={"attempt": int(attempt)})
    try:
        ch.basic_publish(EXCHANGE, topic, body, properties=props, mandatory=True)
        STATS["published"] += 1
        return True
    except Exception as e:
        STATS["publish_failed"] += 1
        STATS["last_error"] = "%s: %s" % (type(e).__name__, str(e)[:160])
        return False


def send(topic, payload):
    """ПРИКЛАДНАЯ точка входа. Кладёт задание в outbox и немедленно возвращается.

    Не публикует напрямую намеренно: сеть до брокера — это ожидание в запросе человека, а
    потеря при обрыве — ровно та тихая потеря, ради которой всё затевалось.
    """
    try:
        import db
        if db.ENABLED:
            db.outbox_put(topic, payload)
            return True
    except Exception as e:
        STATS["last_error"] = "outbox: %s" % str(e)[:160]
    # База выключена — публикуем напрямую, чтобы очередь была полезна и без неё.
    return publish_direct(topic, payload)


def relay_once(limit=50):
    """Перенести готовые задания из outbox в Rabbit. Одна итерация ретранслятора.

    Неудача не удаляет задание: `outbox_failed` откладывает повтор с той же нарастающей
    задержкой, что и у обработчика.
    """
    import db
    if not (db.ENABLED and ENABLED):
        return 0
    moved = 0
    for job in db.outbox_take(limit):
        ok = False
        try:
            ok = publish_direct(job["topic"], job["payload"], attempt=0)
        except Exception as e:
            STATS["last_error"] = "relay: %s" % str(e)[:160]
        if ok:
            db.outbox_done(job["id"])
            moved += 1
        else:
            i = min(job["attempts"], len(BACKOFF_MS) - 1)
            db.outbox_failed(job["id"], STATS.get("last_error") or "publish failed",
                             BACKOFF_MS[i] / 1000.0)
    return moved


def start_relay(period_s=2.0):
    """Ретранслятор фоном. Один на процесс; `skip locked` в outbox_take делает безопасным
    и несколько сразу."""
    if not ENABLED:
        return None

    def _loop():
        while True:
            try:
                relay_once()
            except Exception as e:
                STATS["last_error"] = "relay loop: %s" % str(e)[:160]
            time.sleep(period_s)

    t = threading.Thread(target=_loop, daemon=True, name="mq-relay")
    t.start()
    return t


def retry_or_dead(ch, topic, body, headers, err):
    """Обработчик не смог: отложить повтор или признать мёртвым.

    Считаем попытки в заголовке сообщения, а не в брокере: так число попыток переживает
    перезапуск и видно глазами в мёртвой очереди.
    """
    pika = _pika()
    attempt = int((headers or {}).get("attempt") or 0) + 1
    if attempt > MAX_ATTEMPTS:
        ch.basic_publish("", DEAD_QUEUE, body, properties=pika.BasicProperties(
            delivery_mode=2, headers={"attempt": attempt, "error": str(err)[:300], "topic": topic}))
        STATS["dead"] += 1
        return "dead"
    wait = declare_topic(ch, topic)
    ttl = BACKOFF_MS[min(attempt - 1, len(BACKOFF_MS) - 1)]
    ch.basic_publish(RETRY_EXCHANGE, topic, body, properties=pika.BasicProperties(
        delivery_mode=2, expiration=str(ttl),
        headers={"attempt": attempt, "error": str(err)[:300]}))
    STATS["retried"] += 1
    return "retry:%dms" % ttl


def consume(topic, handler, prefetch=8):
    """Слушать тему. `handler(payload) -> bool`; False или исключение = повтор.

    prefetch намеренно небольшой: обработчики ходят к модели, и набирать сотню сообщений в
    один процесс с двумя ядрами значит только удлинять очередь ожидания внутри себя.
    """
    if not ENABLED:
        raise RuntimeError("KLEAL_MQ=off")
    ch = _channel()
    declare_topic(ch, topic)
    ch.basic_qos(prefetch_count=prefetch)

    def _on(chan, method, props, body):
        try:
            payload = json.loads(body.decode())
        except Exception:
            # Нечитаемое сообщение повторять бессмысленно — оно и на седьмой раз не разберётся.
            chan.basic_ack(method.delivery_tag)
            STATS["dead"] += 1
            return
        try:
            ok = handler(payload)
        except Exception as e:
            ok, err = False, e
        else:
            err = "handler returned False"
        if ok:
            STATS["consumed"] += 1
            chan.basic_ack(method.delivery_tag)
            return
        retry_or_dead(chan, topic, body, (props.headers or {}), err)
        chan.basic_ack(method.delivery_tag)      # исходное снято, копия уже в ожидании

    ch.basic_consume(topic, _on)
    ch.start_consuming()


def healthy():
    if not ENABLED:
        return None
    try:
        _channel()
        return True
    except Exception as e:
        STATS["last_error"] = "%s: %s" % (type(e).__name__, str(e)[:160])
        return False
