#!/usr/bin/env python3
"""Вход через Google, своя часть протокола: python3 services/onboarding/test_google_auth.py

Без сети и без ключей: Google подменяется двумя функциями. Общее с Apple (белый список адресов
и одноразовые метки) проверяется отдельно — `test_oauth_common.py`.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import google_auth as G          # noqa: E402

_fails = []


def check(name, ok, got=""):
    print(("  ok  " if ok else "FAIL  ") + name + ("" if ok else "  -> %s" % (got,)))
    if not ok:
        _fails.append(name)


print("-- без ключей вход честно выключен")
os.environ.pop("KLEAL_GOOGLE_CLIENT_ID", None)
os.environ.pop("KLEAL_GOOGLE_CLIENT_SECRET", None)
check("не настроено -> configured() False", G.configured() is False)

os.environ["KLEAL_GOOGLE_CLIENT_ID"] = "test-client.apps.googleusercontent.com"
os.environ["KLEAL_GOOGLE_CLIENT_SECRET"] = "test-secret"
check("с ключами -> configured() True", G.configured() is True)

print("-- ссылка на Google собрана по правилам")
u = G.auth_url("СТЕЙТ")
for part in ("accounts.google.com", "client_id=test-client", "response_type=code",
             "scope=openid+email+profile", "state=%D0%A1", "prompt=select_account"):
    check("в ссылке есть %s" % part[:28], part in u, u[:120])
check("ключа в ссылке нет", "test-secret" not in u)

print("-- обмен кода: чужой токен и непроверенная почта не проходят")
def tok_ok(url, data, timeout=15):
    return {"id_token": "ЛЮБОЙ"}
def info(aud="test-client.apps.googleusercontent.com", email="me@gmail.com", verified="true"):
    def f(url, timeout=15):
        return {"aud": aud, "email": email, "email_verified": verified, "name": "Иван", "sub": "42"}
    return f

got = G.identity_from_code("код", fetch_token=tok_ok, fetch_info=info())
check("нормальный вход даёт почту", got["email"] == "me@gmail.com" and got["name"] == "Иван", got)

for why, f in (("токен выписан другому приложению", info(aud="другое-приложение")),
               ("почта не подтверждена", info(verified="false")),
               ("почты нет вовсе", info(email=""))):
    try:
        G.identity_from_code("код", fetch_token=tok_ok, fetch_info=f)
        check(why + " — отказ", False, "прошло, а не должно было")
    except ValueError as e:
        check(why + " — отказ (%s)" % e, True)

try:
    G.identity_from_code("код", fetch_token=lambda *a, **k: {"access_token": "x"}, fetch_info=info())
    check("ответ без id_token — отказ", False, "прошло")
except ValueError as e:
    check("ответ без id_token — отказ (%s)" % e, True)


print()
print("FAILED %d: %s" % (len(_fails), ", ".join(_fails)) if _fails else "ALL PASS")
sys.exit(1 if _fails else 0)
