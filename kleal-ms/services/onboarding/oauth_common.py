# -*- coding: utf-8 -*-
"""Общее для всех входов через чужой сервис: куда можно вернуть браузер и одноразовые метки.

Одно место на Google и Apple намеренно. Здесь лежит белый список адресов возврата — самая опасная
строчка во всей этой затее: без него ручка `start` становится открытым перенаправителем, то есть
ссылкой, которая выглядит как наша, а уводит куда угодно. Две копии такого списка однажды разойдутся,
и разойдётся именно та, про которую забыли ([[живой движок — это пакет]] — там копии признаков уже
разъезжались полгода).

Метки тоже общие: и у Google, и у Apple один и тот же порядок — метка запроса связывает возврат с
адресом приложения, метка выдачи меняется на сессию. Обе одноразовые и обе живут минуты.
"""
import secrets
import threading
import time
import urllib.parse

STATE_TTL = 600        # 10 минут на то, чтобы человек выбрал аккаунт в браузере
TICKET_TTL = 120       # 2 минуты от возврата в приложение до обмена метки на сессию
MAX_PENDING = 500      # верхняя граница памяти: дальше самые старые вытесняются

# Куда МОЖНО вернуть браузер. Без этого списка ручка становится открытым перенаправителем: любой
# адрес в `?redirect=` — и наша ссылка уводит人 куда угодно, выглядя при этом как ссылка Kleal.
# `exp://` и `exps://` — это Expo Go (там же живёт туннель aiopenware.com), `kleal://` — своя схема
# приложения из app.json, https — только наш домен.
ALLOWED_SCHEMES = ("exp://", "exps://", "kleal://")
ALLOWED_HTTPS_HOSTS = ("aiopenware.com", "www.aiopenware.com", "localhost", "127.0.0.1")

_LOCK = threading.Lock()
_STATES = {}           # state -> {"redirect": str, "exp": float}
_TICKETS = {}          # ticket -> {"payload": dict, "exp": float}


def safe_redirect(uri):
    """Можно ли вернуть браузер по этому адресу. Пусто/чужое — нельзя."""
    u = str(uri or "").strip()
    if not u or len(u) > 400 or "\n" in u or "\r" in u:
        return False
    low = u.lower()
    if low.startswith(ALLOWED_SCHEMES):
        return True
    if low.startswith("https://"):
        host = urllib.parse.urlsplit(u).hostname or ""
        return host.lower() in ALLOWED_HTTPS_HOSTS
    return False


def _prune(store, now):
    for k in [k for k, v in store.items() if (v or {}).get("exp", 0) < now]:
        store.pop(k, None)
    if len(store) > MAX_PENDING:
        for k in sorted(store, key=lambda k: store[k].get("exp", 0))[:len(store) - MAX_PENDING]:
            store.pop(k, None)


def new_state(redirect):
    """Метка запроса: связывает возврат от Google с адресом приложения. Одноразовая."""
    now = time.time()
    s = secrets.token_urlsafe(24)
    with _LOCK:
        _prune(_STATES, now)
        _STATES[s] = {"redirect": redirect, "exp": now + STATE_TTL}
    return s


def take_state(s):
    """Забрать адрес возврата по метке и ПОГАСИТЬ её. None — метки нет или протухла."""
    now = time.time()
    with _LOCK:
        _prune(_STATES, now)
        rec = _STATES.pop(str(s or ""), None)
    return (rec or {}).get("redirect") if rec else None


def new_ticket(payload):
    """Одноразовая метка вместо сессии в адресной строке: адрес попадает в историю браузера и в
    журналы, а токен на 90 дней там оказаться не должен. Метка живёт две минуты и гаснет при обмене."""
    now = time.time()
    t = secrets.token_urlsafe(24)
    with _LOCK:
        _prune(_TICKETS, now)
        _TICKETS[t] = {"payload": payload, "exp": now + TICKET_TTL}
    return t


def take_ticket(t):
    """Обменять метку на то, что за ней лежит. None — нет, протухла или уже использована."""
    now = time.time()
    with _LOCK:
        _prune(_TICKETS, now)
        rec = _TICKETS.pop(str(t or ""), None)
    return (rec or {}).get("payload") if rec else None


def back_to_app(redirect, **params):
    """Адрес возврата в приложение с добавленными полями. Разделитель выбирается по адресу:
    у `exp://…/--/auth` вопроса ещё нет, а у туннельного `exps://…?x=1` уже может быть."""
    u = str(redirect or "")
    sep = "&" if "?" in u else "?"
    return u + sep + urllib.parse.urlencode({k: v for k, v in params.items() if v})
