# -*- coding: utf-8 -*-
"""Вход по коду с почты — кадры A.03.1 … A.03.3.

    python3 tools/auth_smoke.py                 # прямо по функциям, без сети
    python3 tools/auth_smoke.py https://...     # против живого шлюза

БЕЗ СЕТИ — режим по умолчанию, и он важнее. Код нигде не возвращается наружу (это правило, а не
недосмотр), поэтому по HTTP проверяемы только отказы: истёкший, неверный, лимиты. Полный путь
«запросил → ввёл верный → получил сессию» проверяется вызовом функций напрямую, где код видно
изнутри. Ровно поэтому смоук умеет оба режима.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "shared"))
sys.path.insert(0, os.path.join(ROOT, "services", "onboarding"))

ok = bad = 0


def check(name, cond, extra=""):
    global ok, bad
    if cond:
        ok += 1
        print("  ok   %s   %s" % (name, str(extra)[:80]))
    else:
        bad += 1
        print("  FAIL %s   %s" % (name, str(extra)[:200]))


def local():
    # Свой файл аккаунтов и свой outbox: смоук не имеет права трогать боевые.
    tmp = os.path.join(HERE, "_auth_smoke_tmp")
    os.makedirs(tmp, exist_ok=True)
    os.environ["KLEAL_ACCOUNTS"] = os.path.join(tmp, "accounts.json")
    os.environ["KLEAL_MAIL_OUTBOX"] = os.path.join(tmp, "outbox")
    os.environ.pop("KLEAL_MAIL_PROVIDER", None)
    for f in (os.environ["KLEAL_ACCOUNTS"],):
        if os.path.exists(f):
            os.remove(f)
    import app

    S = int(time.time()) % 1000000
    mail = "probe%d@example.com" % S

    print("\n-- адрес --")
    check("кривой адрес отклонён", app.request_code("не-почта").get("error") == "bad email")
    check("проверка адреса не пускает alex@@mail", not app.valid_email("alex@@mail"))
    check("нормальный адрес проходит", app.valid_email("alex@mail.com"))

    print("\n-- запрос кода --")
    r = app.request_code(mail, "ru")
    check("код запрошен", r.get("ok") is True and r.get("sent") is True, r)
    check("наружу код НЕ уходит", "code" not in str(r).lower() or "code" not in r, list(r))
    check("сказано, когда можно повторить", r.get("resend_in") == app.RESEND_AFTER, r.get("resend_in"))
    code = app._CODES[mail]["hash"]
    check("на сервере лежит ХЕШ, а не сам код", len(code) == 64, code[:12])

    print("\n-- повтор раньше времени --")
    r2 = app.request_code(mail, "ru")
    check("повтор не шлёт второе письмо", r2.get("sent") is False, r2)
    check("и не ошибка, а счётчик", r2.get("ok") is True and r2.get("resend_in", 0) > 0, r2)

    print("\n-- неверный код --")
    r3 = app.verify_code(mail, "000000")
    check("отказ", r3.get("error") == "wrong", r3)
    check("счётчик попыток виден", r3.get("attempts_left") == app.CODE_ATTEMPTS - 1, r3)
    r4 = app.verify_code(mail, "111111")
    check("вторая ошибка уменьшает счётчик", r4.get("attempts_left") == app.CODE_ATTEMPTS - 2, r4)
    r5 = app.verify_code(mail, "222222")
    check("после последней попытки код мёртв", r5.get("error") == "expired", r5)
    check("и из памяти удалён", mail not in app._CODES)

    print("\n-- верный код, новый аккаунт --")
    mail2 = "probe%db@example.com" % S
    app.request_code(mail2, "ru")
    real = _peek(app, mail2)
    v = app.verify_code(mail2, real)
    check("вход выполнен", v.get("ok") is True, v.get("error"))
    check("выдана сессия", isinstance(v.get("token"), str) and len(v["token"]) > 30)
    check("это новый — по борду ведём в анкету", v.get("isNew") is True, v)
    check("профиля ещё нет", v.get("profile") is None)
    check("код одноразовый", app.verify_code(mail2, real).get("error") == "expired")

    print("\n-- сессия --")
    who = app.session_owner(v["token"])
    check("сессия узнаёт хозяина", (who or {}).get("email") == mail2, (who or {}).get("email"))
    check("чужой токен не проходит", app.session_owner("нет-такого") is None)
    accs = app._read_accounts()
    key = app._acc_by_email(accs, mail2)
    stored = list((accs[key].get("sessions") or {}).keys())
    check("на диске лежит хеш сессии, не сам токен",
          stored and v["token"] not in stored and len(stored[0]) == 64, stored[:1])

    print("\n-- анкета привязывается ПО СЕССИИ --")
    a = app.attach_profile_by_token(v["token"], "Probe", {"name": "Probe", "city": "Barcelona"})
    check("привязка прошла", a.get("ok") is True, a)
    check("без сессии не привязывается",
          app.attach_profile_by_token("мусор", "X", {}).get("error") == "no session")

    print("\n-- возврат того же человека --")
    app.request_code(mail2, "ru")
    v2 = app.verify_code(mail2, _peek(app, mail2))
    check("вошёл", v2.get("ok") is True)
    check("это НЕ новый — по борду сразу на главную", v2.get("isNew") is False, v2.get("isNew"))
    check("профиль вернулся", (v2.get("profile") or {}).get("city") == "Barcelona", v2.get("profile"))
    # Аккаунт заводится ТОЛЬКО после успешного кода: первый адрес израсходовал попытки и записи
    # не оставил — это верно, а не упущение. Проверяем то, что важно: повторный вход по той же
    # почте не плодит второй аккаунт.
    accs_now = app._read_accounts()
    check("повторный вход не завёл второй аккаунт", len(accs_now) == 1, list(accs_now))
    check("и он именно этой почты", app._acc_by_email(accs_now, mail2) is not None)
    check("а неудачная попытка аккаунта не создала", app._acc_by_email(accs_now, mail) is None)

    print("\n-- выход --")
    app.sign_out(v2["token"])
    check("эта сессия погашена", app.session_owner(v2["token"]) is None)
    check("а прежняя жива — выходим только с этого устройства",
          (app.session_owner(v["token"]) or {}).get("email") == mail2)

    print("\n-- частота --")
    mail3 = "probe%dc@example.com" % S
    for i in range(app.SEND_PER_HOUR + 1):
        app._CODES.pop(mail3, None) if False else None
        rr = app.request_code(mail3, "ru")
        if rr.get("sent"):
            app._CODES[mail3]["last"] = 0          # обходим окно в 30 с, лимит на час проверяем отдельно
    last = app.request_code(mail3, "ru")
    check("больше пяти писем в час не уходит", last.get("error") == "too many", last)

    print("\n-- истечение --")
    mail4 = "probe%dd@example.com" % S
    app.request_code(mail4, "ru")
    app._CODES[mail4]["exp"] = time.time() - 1
    check("просроченный код отклонён", app.verify_code(mail4, "123456").get("error") == "expired")

    print("\n-- письмо --")
    import mailer
    subj, html, text = mailer.render_code_email("420619", lang="ru")
    check("код есть в теме", "420619" in subj, subj)
    check("код есть в тексте письма", "420619" in text)
    check("в письме нет внешних ссылок", "http://" not in html and "https://" not in html)
    check("есть текстовая часть", len(text) > 50)
    box = os.environ["KLEAL_MAIL_OUTBOX"]
    check("без ключа письмо ложится в outbox", os.path.isdir(box) and len(os.listdir(box)) > 0,
          len(os.listdir(box)) if os.path.isdir(box) else 0)


def _peek(app, mail):
    """Подсмотреть код изнутри — перебором по хешу. Так смоук не требует «отдай мне код» наружу и
    заодно доказывает, что на сервере лежит именно хеш."""
    want = app._CODES[mail]["hash"]
    for n in range(1000000):
        c = "%06d" % n
        if app._sha(c) == want:
            return c
    raise AssertionError("код не подобран")


def remote(base):
    import json
    import urllib.request
    def post(p, b, tok=""):
        h = {"Content-Type": "application/json"}
        if tok:
            h["Authorization"] = "Bearer " + tok
        r = urllib.request.Request(base.rstrip("/") + p, data=json.dumps(b).encode(), headers=h)
        return json.loads(urllib.request.urlopen(r, timeout=60).read().decode())

    S = int(time.time()) % 1000000
    mail = "probe%d@example.com" % S
    print("\n-- живой шлюз --")
    check("кривой адрес отклонён", post("/api/auth/code/request", {"email": "нет"}).get("error") == "bad email")
    r = post("/api/auth/code/request", {"email": mail, "lang": "ru"})
    check("код запрошен", r.get("ok") is True, r)
    check("КОДА В ОТВЕТЕ НЕТ", "code" not in json.dumps(r), r)
    check("неизвестный адрес отвечает так же", post("/api/auth/code/request",
          {"email": "nobody%d@example.com" % S}).get("ok") is True)
    check("неверный код отклонён", post("/api/auth/code/verify",
          {"email": mail, "code": "000000"}).get("error") == "wrong")
    check("счётчик попыток приходит", isinstance(post("/api/auth/code/verify",
          {"email": mail, "code": "000001"}).get("attempts_left"), int))
    check("чужая сессия не проходит", post("/api/auth/session", {}, "мусор").get("ok") is False)


if __name__ == "__main__":
    print("=" * 74)
    print("ВХОД ПО КОДУ")
    print("=" * 74)
    if len(sys.argv) > 1:
        remote(sys.argv[1])
    else:
        local()
    print("\n%s\nРЕЗУЛЬТАТ: %d ok, %d проблем\n%s" % ("=" * 74, ok, bad, "=" * 74))
    sys.exit(1 if bad else 0)
