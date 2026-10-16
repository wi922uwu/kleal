# -*- coding: utf-8 -*-
"""Вход через Apple — своя часть протокола. Общее с Google (белый список, метки) — `oauth_common`.

Путь тот же, что у Google: браузер уходит к Apple, Apple возвращается на НАШ https-адрес, сервер
меняет код на почту и уводит браузер обратно в приложение с одноразовой меткой. Причина та же —
у Expo Go чужой идентификатор приложения, и нативная кнопка требует дев-сборки (AGENTS.md).

НО ЧЕТЫРЕ ВЕЩИ У APPLE УСТРОЕНЫ ИНАЧЕ, и каждая ломает вход, если сделать «как у Google»:

1. **Пароля у клиента нет.** Вместо `client_secret` Apple требует JWT, подписанный ES256 ключом
   `.p8` из кабинета разработчика. Его собираем сами и обновляем: Apple разрешает до полугода, мы
   берём час — короткий живёт меньше, чем успеет утечь.
2. **Ответ приходит POST-формой.** Как только просишь `scope=name email`, Apple отвечает не
   редиректом, а `response_mode=form_post` — POST-ом на наш адрес. Ручка обязана читать форму,
   а не JSON, иначе тело просто не разберётся.
3. **Имя даётся ОДИН РАЗ.** При первой авторизации в форме приходит поле `user` с именем; при всех
   следующих его не будет никогда. Не записал сразу — потерял навсегда.
4. **Почта может быть подставной** (`…@privaterelay.appleid.com`). Это нормальный рабочий адрес,
   письма через него доходят, и отвергать его нельзя.

И пятое, менее заметное: у Apple нет ручки вроде гугловой `tokeninfo`, поэтому подпись `id_token`
проверяем сами — по их же набору ключей (JWKS, RS256). `PyJWT` и `cryptography` на боксе есть.

Ключа в коде нет и быть не должно: путь к `.p8` и идентификаторы живут в окружении службы.
"""
import json
import os
import threading
import time
import urllib.parse
import urllib.request

import oauth_common as _c

# Общее — из одного места (см. oauth_common): белый список адресов возврата и одноразовые метки.
safe_redirect = _c.safe_redirect
new_state = _c.new_state
take_state = _c.take_state
new_ticket = _c.new_ticket
take_ticket = _c.take_ticket
back_to_app = _c.back_to_app

AUTH_URL = "https://appleid.apple.com/auth/authorize"
TOKEN_URL = "https://appleid.apple.com/auth/token"
KEYS_URL = "https://appleid.apple.com/auth/keys"
ISSUER = "https://appleid.apple.com"

SECRET_TTL = 3600          # час: Apple разрешает до полугода, но короткий JWT честнее
_SECRET = {}               # {"jwt": str, "exp": int} — собранный пароль клиента
_SECRET_LOCK = threading.Lock()


def client_id():
    """Services ID из кабинета Apple — НЕ идентификатор приложения (`com.kleal.app`), а отдельный,
    заведённый для входа через сайт, например `com.kleal.app.web`."""
    return str(os.environ.get("KLEAL_APPLE_CLIENT_ID") or "").strip()


def team_id():
    return str(os.environ.get("KLEAL_APPLE_TEAM_ID") or "").strip()


def key_id():
    return str(os.environ.get("KLEAL_APPLE_KEY_ID") or "").strip()


def key_file():
    return str(os.environ.get("KLEAL_APPLE_KEY_FILE") or "").strip()


def redirect_uri():
    return str(os.environ.get("KLEAL_APPLE_REDIRECT")
               or "https://aiopenware.com/api/auth/apple/callback").strip()


def configured():
    """Есть ли чем входить: четыре значения и читаемый файл ключа. Без этого ручка честно отвечает
    «не настроено», а кнопка на экране остаётся заглушкой."""
    f = key_file()
    return bool(client_id() and team_id() and key_id() and f and os.path.isfile(f))


def client_secret(now=None, key_text=None):
    """Пароль клиента — JWT, подписанный ключом `.p8`. Собирается сам и кешируется на час.

    `key_text` подменяется в проверках, чтобы не класть настоящий ключ в тест."""
    import jwt                                    # локально: модуль нужен только этой ветке
    now = int(now or time.time())
    with _SECRET_LOCK:
        if _SECRET.get("exp", 0) - 60 > now and not key_text:
            return _SECRET["jwt"]
        text = key_text if key_text is not None else open(key_file(), "r", encoding="utf-8").read()
        tok = jwt.encode({"iss": team_id(), "iat": now, "exp": now + SECRET_TTL,
                          "aud": ISSUER, "sub": client_id()},
                         text, algorithm="ES256", headers={"kid": key_id()})
        tok = tok.decode("utf-8") if isinstance(tok, bytes) else tok      # PyJWT 1.x отдавал байты
        if not key_text:
            _SECRET.update({"jwt": tok, "exp": now + SECRET_TTL})
        return tok


def auth_url(state):
    """Адрес Apple, на который уходит браузер.

    `response_mode=form_post` — не наша прихоть: с `scope=name email` Apple отвечает только так."""
    q = {"client_id": client_id(), "redirect_uri": redirect_uri(), "response_type": "code id_token",
         "scope": "name email", "response_mode": "form_post", "state": state}
    return AUTH_URL + "?" + urllib.parse.urlencode(q)


def _post_form(url, data, timeout=15):
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, body, {"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _get_json(url, timeout=15):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def verify_id_token(idt, fetch_keys=None):
    """Разобрать `id_token` Apple, проверив подпись их же ключом. Ошибка — исключение.

    Проверять обязательно: на наш адрес возврата POST-ом может прийти кто угодно, и без подписи
    «вход» свёлся бы к «пришли нам чужую почту в поле формы»."""
    import jwt
    from jwt.algorithms import RSAAlgorithm
    head = jwt.get_unverified_header(idt)
    keys = ((fetch_keys or _get_json)(KEYS_URL) or {}).get("keys") or []
    jwk = next((k for k in keys if k.get("kid") == head.get("kid")), None)
    if not jwk:
        raise ValueError("no matching key")
    return jwt.decode(idt, RSAAlgorithm.from_jwk(json.dumps(jwk)), algorithms=["RS256"],
                      audience=client_id(), issuer=ISSUER)


def identity_from_code(code, fetch_token=None, fetch_keys=None):
    """Код от Apple -> {"email","sub"}. Имени здесь нет: оно приходит формой, см. `name_from_form`."""
    tok = (fetch_token or _post_form)(TOKEN_URL, {
        "code": code, "client_id": client_id(), "client_secret": client_secret(),
        "redirect_uri": redirect_uri(), "grant_type": "authorization_code"})
    idt = (tok or {}).get("id_token")
    if not idt:
        raise ValueError("no id_token")
    claims = verify_id_token(idt, fetch_keys=fetch_keys)
    email = str(claims.get("email") or "").strip().lower()
    verified = str(claims.get("email_verified", "")).lower() in ("true", "1", "yes")
    if not email or not verified:
        raise ValueError("email not verified")
    return {"email": email, "sub": str(claims.get("sub") or "")}


def name_from_form(user_field):
    """Имя из поля `user` первой авторизации: {"name":{"firstName","lastName"},"email":…}.

    Второй раз Apple его не пришлёт, поэтому берём что дают и не капризничаем о форме."""
    raw = user_field
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except Exception:
            return ""
    nm = (raw or {}).get("name") if isinstance(raw, dict) else None
    if not isinstance(nm, dict):
        return ""
    parts = [str(nm.get("firstName") or "").strip(), str(nm.get("lastName") or "").strip()]
    return " ".join(p for p in parts if p)[:80]
