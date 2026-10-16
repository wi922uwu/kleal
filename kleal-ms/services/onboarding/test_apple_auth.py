#!/usr/bin/env python3
"""Вход через Apple, своя часть протокола: python3 services/onboarding/test_apple_auth.py

Без сети и без настоящих ключей: ключи делаются прямо здесь (`cryptography`), Apple подменяется
двумя функциями. Проверяется то, на чём такой вход и течёт: подпись `id_token` (на наш адрес
возврата POST-ом может прийти кто угодно), чужой `aud`, чужой издатель, просроченный токен и имя,
которое Apple даёт ровно один раз.

Общее с Google — белый список адресов и одноразовые метки — проверяется в `test_oauth_common.py`.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apple_auth as A            # noqa: E402

_fails = []


def check(name, ok, got=""):
    print(("  ok  " if ok else "FAIL  ") + name + ("" if ok else "  -> %s" % (got,)))
    if not ok:
        _fails.append(name)


try:
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec, rsa
except Exception as e:                                    # pragma: no cover
    print("нет криптографии (%s) — этот тест гоняется на боксе, где она стоит" % e)
    raise SystemExit(0)

CLIENT = "com.kleal.app.web"

print("-- без настроек вход честно выключен")
for k in ("KLEAL_APPLE_CLIENT_ID", "KLEAL_APPLE_TEAM_ID", "KLEAL_APPLE_KEY_ID", "KLEAL_APPLE_KEY_FILE"):
    os.environ.pop(k, None)
check("не настроено -> configured() False", A.configured() is False)

# ── ключ подписи (.p8 у Apple — это EC P-256) ────────────────────────────────────────────────
ec_key = ec.generate_private_key(ec.SECP256R1())
p8 = ec_key.private_bytes(serialization.Encoding.PEM,
                          serialization.PrivateFormat.PKCS8,
                          serialization.NoEncryption()).decode()
key_path = "/tmp/kleal_test_apple_key.p8"
open(key_path, "w").write(p8)
os.environ.update({"KLEAL_APPLE_CLIENT_ID": CLIENT, "KLEAL_APPLE_TEAM_ID": "TEAM123456",
                   "KLEAL_APPLE_KEY_ID": "KEY7654321", "KLEAL_APPLE_KEY_FILE": key_path})
check("с настройками -> configured() True", A.configured() is True)
os.environ["KLEAL_APPLE_KEY_FILE"] = "/tmp/нет-такого-файла.p8"
check("ключа на диске нет -> configured() False", A.configured() is False)
os.environ["KLEAL_APPLE_KEY_FILE"] = key_path

print("-- пароль клиента: Apple не принимает обычный пароль, только подписанный JWT")
sec = A.client_secret(now=1700000000, key_text=p8)
head = jwt.get_unverified_header(sec)
body = jwt.decode(sec, options={"verify_signature": False}, audience=A.ISSUER)
check("подписан ES256", head.get("alg") == "ES256", head)
check("несёт номер ключа", head.get("kid") == "KEY7654321", head)
check("издатель — команда", body.get("iss") == "TEAM123456", body)
check("для Apple", body.get("aud") == A.ISSUER, body)
check("про наш Services ID", body.get("sub") == CLIENT, body)
check("живёт час, а не полгода", body.get("exp") - body.get("iat") == 3600, body)

print("-- ссылка на Apple: форма-ответ обязательна, иначе имени не будет")
u = A.auth_url("СТЕЙТ")
for part in ("appleid.apple.com/auth/authorize", "client_id=com.kleal.app.web",
             "response_type=code+id_token", "scope=name+email", "response_mode=form_post",
             "state=%D0%A1"):
    check("в ссылке есть %s" % part[:30], part in u, u[:130])

# ── поддельный Apple: свой ключ RSA и свой набор JWKS ────────────────────────────────────────
rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
pem = rsa_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
pub_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(rsa_key.public_key()))
pub_jwk.update({"kid": "AAAA1111", "alg": "RS256", "use": "sig"})
KEYS = {"keys": [pub_jwk]}


def token(aud=CLIENT, iss=A.ISSUER, email="me@privaterelay.appleid.com", verified="true",
          exp_in=600, kid="AAAA1111"):
    now = int(time.time())
    claims = {"iss": iss, "aud": aud, "sub": "000123.abc", "iat": now, "exp": now + exp_in,
              "email": email, "email_verified": verified}
    return jwt.encode(claims, pem, algorithm="RS256", headers={"kid": kid})


def fetch_token_with(idt):
    def f(url, data, timeout=15):
        return {"id_token": idt}
    return f


def fetch_keys(url, timeout=15):
    return KEYS


print("-- обычный вход: подставная почта Apple — нормальная почта")
got = A.identity_from_code("код", fetch_token=fetch_token_with(token()), fetch_keys=fetch_keys)
check("почта доехала", got["email"] == "me@privaterelay.appleid.com", got)
check("и постоянный номер человека", got["sub"] == "000123.abc", got)

print("-- подделки не проходят")
bad = [
    ("токен выписан другому приложению", token(aud="com.someone.else")),
    ("издатель не Apple", token(iss="https://evil.example")),
    ("почта не подтверждена", token(verified="false")),
    ("почты нет", token(email="")),
    ("токен просрочен", token(exp_in=-60)),
    ("ключ не из набора Apple", token(kid="ЧУЖОЙ")),
]
for why, idt in bad:
    try:
        A.identity_from_code("код", fetch_token=fetch_token_with(idt), fetch_keys=fetch_keys)
        check(why + " — отказ", False, "прошло, а не должно было")
    except Exception as e:
        check(why + " — отказ (%s)" % type(e).__name__, True)

# подпись СВОИМ ключом, а kid — настоящий: самая честная попытка подделки
other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
other_pem = other.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
now = int(time.time())
forged = jwt.encode({"iss": A.ISSUER, "aud": CLIENT, "sub": "x", "iat": now, "exp": now + 600,
                     "email": "victim@gmail.com", "email_verified": "true"},
                    other_pem, algorithm="RS256", headers={"kid": "AAAA1111"})
try:
    A.identity_from_code("код", fetch_token=fetch_token_with(forged), fetch_keys=fetch_keys)
    check("токен, подписанный чужим ключом — отказ", False, "ПРОШЛО — это дыра")
except Exception as e:
    check("токен, подписанный чужим ключом — отказ (%s)" % type(e).__name__, True)

try:
    A.identity_from_code("код", fetch_token=lambda *a, **k: {"access_token": "x"}, fetch_keys=fetch_keys)
    check("ответ без id_token — отказ", False, "прошло")
except ValueError as e:
    check("ответ без id_token — отказ (%s)" % e, True)

print("-- имя, которое Apple даёт ровно один раз")
check("имя из формы", A.name_from_form('{"name":{"firstName":"Иван","lastName":"Копылов"}}') == "Иван Копылов")
check("словарём тоже", A.name_from_form({"name": {"firstName": "Ann", "lastName": ""}}) == "Ann")
check("второй вход без имени — пусто", A.name_from_form("") == "")
check("мусор — пусто", A.name_from_form("не json") == "")
check("без имени внутри — пусто", A.name_from_form('{"email":"a@b.c"}') == "")

os.remove(key_path)
print()
print("FAILED %d: %s" % (len(_fails), ", ".join(_fails)) if _fails else "ALL PASS")
sys.exit(1 if _fails else 0)
