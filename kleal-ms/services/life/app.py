# -*- coding: utf-8 -*-
"""Эмуляция жизни: сиды сами отвечают на приглашения, переписываются и договариваются о встрече.

ЗАЧЕМ. Проверить сквозной поток вдвоём — пригласил, ответили, списались, назначили время — до сих
пор можно было только вдвоём с человеком. Один тестировщик упирался в первый же шаг: приглашение
уходило, и на той стороне никого не было. Здесь та сторона есть.

ВЫКЛЮЧАЕТСЯ ЩЕЛЧКОМ, И ЭТО ГЛАВНОЕ СВОЙСТВО:

    systemctl stop kleal-life          # остановить
    systemctl disable kleal-life       # и не поднимать при перезагрузке

Плюс предохранитель в самой службе: без `KLEAL_LIFE=on` она отказывается работать и выходит. То
есть случайно запущенная — не делает ничего. Выключенная не оставляет после себя ни таймера, ни
очереди, ни отложенных заданий: весь эффект живёт только внутри тика.

ЧЕРЕЗ НАСТОЯЩИЙ API, А НЕ В ОБХОД. Бот ходит теми же ручками, что и приложение. Писать прямо в
хранилище было бы проще и бессмысленно: тогда проверяется хранилище, а не продукт. Все правила
матчинга — гейты, версии, идемпотентность, состояния плана — работают ровно так же, как для
человека, и если поток сломан, бот споткнётся там же, где споткнулся бы живой.

ПО ПЕТЛЕ, А НЕ ЧЕРЕЗ ШЛЮЗ. Служба обращается к матчингу на 127.0.0.1:7074 — так же, как админка.
Снаружи этот порт не виден, поэтому никакого внутреннего заголовка-пропуска заводить не нужно: то,
чего нет, невозможно подделать.

БОТ НИКОГДА НЕ ДЕЙСТВУЕТ ЗА ЖИВОГО. Действующими лицами становятся только строки с `source`,
отличным от `onboarding`, — сиды и нагрузочные. Проверка стоит в одном месте (`_actors`), и любой
живой профиль отсеивается до того, как о нём зайдёт речь. Отвечать живому бот при этом может и
должен: в этом вся польза.

СЛЕД ВИДЕН И СНИМАЕТСЯ. Каждое сообщение уходит с `client_id`, начинающимся на `life-`, поэтому
всё наигранное находится одной выборкой и удаляется, не задевая настоящего.
"""
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "shared"))

import config  # noqa: E402

MATCH = os.environ.get("MATCH_URL", "http://127.0.0.1:7074")

# Сколько ждать между тиками и сколько действий делать за тик. Мало намеренно: цель — оживить
# стенд, а не нагрузить его. Двадцать пять секунд читаются как «человек отвлёкся», а не как бот.
TICK = int(os.environ.get("KLEAL_LIFE_TICK", "25"))
ACTS = int(os.environ.get("KLEAL_LIFE_ACTS", "3"))

# Реплики нарочно короткие и бессодержательные: бот изображает присутствие, а не собеседника.
# Осмысленный разговор — работа модели, и звать её в цикле проверки значит тратить её впустую.
LINES = [
    "Привет! Давай.", "Ага, я за", "Звучит хорошо", "Удобно, да",
    "Ок, договорились", "Можно и так", "Я свободен вечером", "Идёт",
]


def _get(path):
    try:
        with urllib.request.urlopen(MATCH + path, timeout=10) as r:
            return json.loads(r.read().decode())
    except Exception:
        return {}


def _post(path, body):
    try:
        req = urllib.request.Request(MATCH + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, str(e)[:80])}


def _actors():
    """Кто имеет право действовать. ТОЛЬКО не-живые строки — разбор в шапке."""
    try:
        with open(config.USERS, "r", encoding="utf-8") as f:
            raw = json.load(f)
        rows = raw.get("users") if isinstance(raw, dict) else raw
    except Exception:
        return []
    out = []
    for u in rows or []:
        if not isinstance(u, dict):
            continue
        if (u.get("source") or "") == "onboarding":
            continue                       # живой человек — не марионетка
        nm = str(u.get("name") or "").strip()
        if nm:
            out.append(nm)
    return out


def _idem(kind, who, ident):
    """Ключ идемпотентности. Один и тот же ответ на одно и то же событие не должен раздваиваться,
    если тик перекрылся с предыдущим или служба перезапустилась посреди действия."""
    return "life-%s-%s-%s" % (kind, abs(hash(who)) % 10 ** 6, str(ident)[:24])


def pending_requests(bots):
    """Неотвеченные приглашения, адресованные ботам, — ОДНИМ запросом.

    ПОЧЕМУ НЕ ОПРОСОМ ВСЕХ ПОДРЯД. Первая версия перебирала действующих лиц и спрашивала у каждого
    его входящие: шестьсот сидов по три запроса — тысяча восемьсот обращений на тик. Тик не
    успевал дойти до нужного бота за отведённые секунды, и приглашение висело неотвеченным,
    хотя служба работала. Поймано на живой проверке: пригласил бота, подождал два тика — тишина.

    Реестр заявок отдаёт всё сразу, и работа находится за один запрос вместо тысячи.
    """
    reg = _get("/api/agent/admin/proposals")
    out = []
    known = {b.strip().lower() for b in bots}
    for r in (reg.get("requests") or []):
        if str(r.get("status") or "").lower() not in ("", "pending", "proposed", "new"):
            continue
        to = str(r.get("to") or "").strip()
        if to.lower() in known and r.get("id"):
            # ОТ ЖИВОГО ЧЕЛОВЕКА ПРИГЛАШЕНИЕ ПРИНИМАЕТСЯ ВСЕГДА, отказ разыгрывается только между
            # ботами. Причина найдена на живом телефоне и она серьёзнее, чем кажется: бот отклонил
            # приглашение проверяющего, а `send_message` без принятой заявки сообщений не
            # пропускает — человек остался в переписке, из которой нельзя написать. Стенд, который
            # случайным образом закрывает проверяющему дорогу, бесполезен: смысл эмуляции в том,
            # чтобы поток ПРОХОДИЛСЯ.
            out.append((to, r["id"], str(r.get("from") or "").strip().lower() in known))
    return out


def act_requests(who, rid, rng, from_bot=False):
    """Ответить на входящее приглашение.

    Отказ разыгрывается ТОЛЬКО между ботами (`from_bot`): ветку отказа проверять надо, но не на
    том, кто пришёл проверять продукт. Приглашение от живого принимается всегда.
    """
    decision = "accept" if (not from_bot or rng.random() < 0.75) else "decline"
    res = _post("/api/agent/respond", {"id": rid, "decision": decision, "self": who,
                                       "idem": _idem("resp", who, rid)})
    return "заявка %s -> %s (%s)" % (str(rid)[:8], decision, "ок" if res.get("ok") else res.get("error"))


def act_threads(who, rng):
    """Ответить в переписке, где последнее слово не за нами. Одна реплика за тик: бот, пишущий
    подряд, читается ботом мгновенно."""
    th = _get("/api/agent/threads?self=" + urllib.parse.quote(who))
    for t in (th.get("threads") or [])[:3]:
        # ФОРМА ВЕТКИ ПРОВЕРЕНА ЖИВЫМ ЗАПРОСОМ, а не угадана: собеседник лежит в `who`, а `last` —
        # это СТРОКА с текстом, не объект с автором. Первая версия искала `with`/`other` и читала
        # `last.get("from")`; собеседник выходил пустым, и бот молчал, хотя служба работала.
        # Кто написал последним, говорит `mine`.
        other = str(t.get("who") or "").strip()
        if not other or t.get("mine"):
            continue                       # последнее слово за нами — отвечать нечего
        if not str(t.get("last") or "").strip():
            continue
        text = LINES[rng.randrange(len(LINES))]
        res = _post("/api/agent/message", {"from": who, "to": other, "text": text,
                                           "client_id": _idem("msg", who, other + str(t.get("t") or ""))})
        return "письмо -> %s (%s)" % (other[:16], "ок" if res.get("ok") else res.get("error"))
    return None


def act_plans(who, rng):
    """Ответить на предложенное время встречи."""
    pl = _get("/api/agent/mplans?self=" + urllib.parse.quote(who))
    for p in (pl.get("plans") or [])[:2]:
        pid = p.get("id")
        st = str(p.get("status") or "")
        if not pid or st not in ("proposed", "pending", "changed"):
            continue
        action = "accept" if rng.random() < 0.8 else "decline"
        res = _post("/api/agent/mplan-respond", {"id": pid, "self": who, "action": action,
                                                 "version": p.get("version"),
                                                 "idem": _idem("plan", who, pid)})
        return "план %s -> %s (%s)" % (str(pid)[:8], action, "ок" if res.get("ok") else res.get("error"))
    return None


def tick(rng):
    """Один тик: сперва ищем работу, потом делаем.

    Порядок именно такой и он важен. Ответ на приглашение — первый шаг любого сквозного потока, и
    пока он не сделан, ни переписки, ни плана не появится. Поэтому неотвеченные заявки разбираются
    в начале, целиком и без жребия; переписка и планы идут потом, по остатку разрешённых действий,
    и только у тех, кто в разговоре уже участвует.
    """
    bots = _actors()
    if not bots:
        return 0
    done = 0

    for who, rid, from_bot in pending_requests(bots)[:ACTS]:
        try:
            said = act_requests(who, rid, rng, from_bot)
        except Exception as e:
            said = "сбой ответа: %s" % str(e)[:60]
        print("[life] %s: %s" % (who[:18], said), flush=True)
        done += 1

    if done >= ACTS:
        return done

    # Переписка и планы — только у тех, кто уже в разговоре. Кого проверять, узнаём из того же
    # реестра: приглашение принято, значит между этими двумя есть о чём говорить.
    reg = _get("/api/agent/admin/proposals")
    known = {b.strip().lower() for b in bots}
    talking = []
    for r in (reg.get("requests") or []):
        if str(r.get("status") or "").lower() != "accepted":
            continue
        for side in (r.get("to"), r.get("from")):
            nm = str(side or "").strip()
            if nm and nm.lower() in known and nm not in talking:
                talking.append(nm)
    rng.shuffle(talking)
    for who in talking:
        if done >= ACTS:
            break
        for fn in (act_threads, act_plans):
            try:
                said = fn(who, rng)
            except Exception as e:
                said = "сбой %s: %s" % (fn.__name__, str(e)[:60])
            if said:
                print("[life] %s: %s" % (who[:18], said), flush=True)
                done += 1
                break
    return done


def main():
    if os.environ.get("KLEAL_LIFE", "").strip().lower() not in ("1", "on", "true", "yes"):
        print("[life] KLEAL_LIFE не включён — выхожу, ничего не делаю", flush=True)
        return 0
    rng = random.Random()
    print("[life] включена. тик %d с, до %d действий за тик, действующих лиц %d"
          % (TICK, ACTS, len(_actors())), flush=True)
    while True:
        try:
            tick(rng)
        except KeyboardInterrupt:
            return 0
        except Exception as e:
            print("[life] тик упал (%s: %s)" % (type(e).__name__, str(e)[:100]), flush=True)
        time.sleep(TICK)


if __name__ == "__main__":
    sys.exit(main())
