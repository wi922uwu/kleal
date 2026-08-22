# -*- coding: utf-8 -*-
"""Воркер очереди: делает фоновую работу, которая раньше терялась молча.

ЗАЧЕМ ОТДЕЛЬНЫЙ ПРОЦЕСС. Фоновая работа тяжёлая и медленная: разбор фразы фильтрацией — вызов
модели, секунда с лишним. Делать её в потоке внутри Бадди значит держать эту секунду внутри
запроса человека или бросать её «в никуда», как и было. Отдельный процесс переживает перезапуск
любого из сервисов и может тормозить, никого не задерживая.

ЧТО ДЕЛАЕТ СЕЙЧАС. Одну тему — `teach.phrases`: разбор интереса фильтрацией и обучение матчинга
темами (мост тем). Ровно та работа, которая неделями падала в несуществующий адрес.

ПОЧЕМУ ОБРАБОТЧИК ВОЗВРАЩАЕТ False, А НЕ БРОСАЕТ. Возврат False — это «не смог, попробуй позже»
и уводит сообщение в комнату ожидания. Исключение делает то же самое, но у него нет объяснения,
поэтому в мёртвой очереди потом лежит трассировка вместо причины. Обе дороги ведут в ретрай —
разница в том, что прочитает человек, разбирающий затор.
"""
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "shared"))

import config           # noqa: E402  единая таблица адресов
import mq               # noqa: E402
import db               # noqa: E402


def _post(base, path, body, timeout=30):
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode())


def teach_phrases(payload):
    """Разобрать фразы фильтрацией и научить матчинг. `payload = {"phrases": [...]}`.

    Пустой разбор — НЕ ошибка и повтора не заслуживает: фильтрация честно ответила «тем нет», и
    на седьмой попытке ответит так же. Ошибка — это когда сервис не ответил вовсе.
    """
    phrases = [str(p) for p in (payload or {}).get("phrases") or [] if str(p).strip()]
    if not phrases:
        return True
    items = []
    for ph in phrases[:50]:
        try:
            d = _post(config.FILTER_URL, "/api/filter/categorize", {"text": ph}, timeout=90)
        except Exception:
            return False                      # фильтрация недоступна — повторим позже
        ts = [str(t).lower().strip() for t in (d.get("topics") or []) if str(t).strip()]
        if ts:
            items.append({"phrase": ph, "topics": ts})
    if not items:
        return True
    try:
        r = _post(config.MATCH_URL, "/api/agent/learn-phrases", {"items": items}, timeout=60)
    except Exception:
        return False                          # матчинг недоступен — повторим позже
    return bool(r.get("ok"))


HANDLERS = {"teach.phrases": teach_phrases}


def main():
    topic = os.environ.get("KLEAL_WORKER_TOPIC", "teach.phrases")
    if topic not in HANDLERS:
        print("неизвестная тема: %s (знаю: %s)" % (topic, ", ".join(HANDLERS)))
        return 2
    if not mq.ENABLED:
        print("KLEAL_MQ=off — воркеру нечего слушать")
        return 2
    if db.ENABLED:
        db.ensure_schema()
    # Ретранслятор здесь же: если воркер поднят, а сервисы писали в outbox при лежащем брокере,
    # накопленное уедет само, без отдельного процесса.
    mq.start_relay()
    print("воркер слушает %s (брокер %s)" % (topic, mq.URL.split("@")[-1]))
    while True:
        try:
            mq.consume(topic, HANDLERS[topic])
        except KeyboardInterrupt:
            return 0
        except Exception as e:
            # Обрыв соединения с брокером — не повод умирать: сервис под systemd перезапустится,
            # но лишний перезапуск теряет prefetch-нутые сообщения. Ждём и переподключаемся сами.
            print("соединение с брокером потеряно (%s: %s), пробую через 5 с"
                  % (type(e).__name__, str(e)[:140]))
            time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
