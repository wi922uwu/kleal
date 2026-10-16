# -*- coding: utf-8 -*-
"""Вход через Google — протокольная часть: ссылки, одноразовые метки, обмен кода на почту.

ПОЧЕМУ ЧЕРЕЗ БРАУЗЕР И СВОЙ СЕРВЕР, А НЕ «нативной кнопкой». Приложение живёт в Expo Go, а Google
принимает в качестве адреса возврата только https или схему, зарегистрированную на СВОЙ
идентификатор приложения. У Expo Go идентификатор чужой (`host.exp.Exponent`), а адрес возврата
выглядит как `exp://…` — Google такой не примет. Поэтому: телефон открывает системный браузер на
НАШЕМ `/api/auth/google/start`, Google возвращается на НАШ https-адрес, сервер меняет код на почту
и уводит браузер обратно в приложение по его собственной ссылке — с одноразовой меткой вместо
токена. Этот путь работает и в Expo Go, и в будущей дев-сборке; нативную кнопку можно добавить
поверх, ничего здесь не меняя.

ЧЕГО ЗДЕСЬ НЕТ И БЫТЬ НЕ ДОЛЖНО: ключа в коде. `client_secret` живёт только в окружении службы
(`/etc/kleal-infra.env`), и в журнал не попадает ни он, ни токен сессии, ни сам код от Google.

Модуль ЧИСТЫЙ в той части, где это возможно: аккаунтов и сессий он не знает — их заводит вызывающий
(`services/onboarding/app.py`), ровно тем же кодом, что и вход по почте. Здесь только протокол,
и поэтому его можно проверить без сети (`test_google_auth.py`); общее с Apple — в `oauth_common.py`.
"""
import json
import os
import urllib.parse
import urllib.request

import oauth_common as _c
# Общее — из одного места: белый список адресов возврата и одноразовые метки (oauth_common).
# Имена ре-экспортированы, чтобы вызывающий код и проверки не знали, где именно они лежат.
safe_redirect = _c.safe_redirect
new_state = _c.new_state
take_state = _c.take_state
new_ticket = _c.new_ticket
take_ticket = _c.take_ticket
back_to_app = _c.back_to_app
STATE_TTL = _c.STATE_TTL
TICKET_TTL = _c.TICKET_TTL

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"



def client_id():
    return str(os.environ.get("KLEAL_GOOGLE_CLIENT_ID") or "").strip()


def _client_secret():
    return str(os.environ.get("KLEAL_GOOGLE_CLIENT_SECRET") or "").strip()


def redirect_uri():
    return str(os.environ.get("KLEAL_GOOGLE_REDIRECT")
               or "https://aiopenware.com/api/auth/google/callback").strip()


def configured():
    """Есть ли чем входить. Без ключей ручка честно отвечает «не настроено», а не молча падает."""
    return bool(client_id() and _client_secret())


def auth_url(state):
    """Адрес Google, на который уходит браузер. `select_account` — чтобы человек с двумя почтами
    мог выбрать, а не входил молча тем, чем вошёл в браузере в прошлый раз."""
    q = {"client_id": client_id(), "redirect_uri": redirect_uri(), "response_type": "code",
         "scope": "openid email profile", "state": state,
         "access_type": "online", "prompt": "select_account", "include_granted_scopes": "true"}
    return AUTH_URL + "?" + urllib.parse.urlencode(q)


def _post_form(url, data, timeout=15):
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, body, {"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_json(url, timeout=15):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def identity_from_code(code, fetch_token=None, fetch_info=None):
    """Код от Google -> {"email","name","sub"}. Ошибка — исключение с коротким текстом.

    Подпись id_token проверяем не сами: спрашиваем `tokeninfo` у самого Google. Своя проверка
    подписи означала бы тянуть криптографию и следить за ротацией ключей — ради одного входа это
    лишний риск, а ответ `tokeninfo` приходит уже проверенным на стороне, которая эти ключи и
    выпускает. Обязательно сверяем `aud` со своим идентификатором: без этой сверки подошёл бы
    токен, выписанный ДРУГОМУ приложению.

    `fetch_token`/`fetch_info` подменяются в тестах — сеть в проверках не нужна."""
    tok = (fetch_token or _post_form)(TOKEN_URL, {
        "code": code, "client_id": client_id(), "client_secret": _client_secret(),
        "redirect_uri": redirect_uri(), "grant_type": "authorization_code"})
    idt = (tok or {}).get("id_token")
    if not idt:
        raise ValueError("no id_token")
    info = (fetch_info or _get_json)(TOKENINFO_URL + "?" + urllib.parse.urlencode({"id_token": idt}))
    if str((info or {}).get("aud") or "") != client_id():
        raise ValueError("wrong audience")          # токен выписан не нам
    email = str((info or {}).get("email") or "").strip().lower()
    verified = str((info or {}).get("email_verified", "")).lower() in ("true", "1", "yes")
    if not email or not verified:
        raise ValueError("email not verified")      # непроверенная почта — не личность
    return {"email": email, "name": str((info or {}).get("name") or "").strip(),
            "sub": str((info or {}).get("sub") or "")}


