# -*- coding: utf-8 -*-
"""Отправка письма с кодом входа.

ПОЧЕМУ НЕ SMTP. Проверено на боевом боксе: исходящие 25, 587 и 465 закрыты — DigitalOcean
режет SMTP по умолчанию. Значит остаётся HTTP-ручка провайдера через 443, и это к лучшему:
никаких долгоживущих соединений внутри ThreadingHTTPServer и понятный отказ вместо таймаута.

ПРОВАЙДЕР ВЫБИРАЕТСЯ ОКРУЖЕНИЕМ, а не кодом:

    KLEAL_MAIL_PROVIDER = resend | postmark | brevo | none   (по умолчанию none)
    KLEAL_MAIL_KEY      = ключ провайдера
    KLEAL_MAIL_FROM     = "Kleal <hello@aiopenware.com>"

Все три ручки принимают JSON и отвечают JSON — различий ровно столько, сколько описано в
_PROVIDERS. Добавить четвёртого значит дописать туда строчку, а не трогать вызывающий код.

`none` — это НЕ заглушка «ничего не делаем». Письмо собирается целиком и кладётся в
outbox/<время>-<адрес>.html, а код пишется в лог. Так весь путь — запрос, письмо, ввод кода,
сессия — проверяется до того, как у проекта появится ключ, и письмо можно открыть глазами.
Наружу код при этом НЕ уходит ни при каких настройках: в ответе ручки его нет никогда.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

OUTBOX = os.environ.get("KLEAL_MAIL_OUTBOX",
                        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                     "outbox"))

# Как сложить запрос к каждому провайдеру: (url, заголовки(ключ), тело(from,to,subject,html,text)).
_PROVIDERS = {
    "resend": (
        "https://api.resend.com/emails",
        lambda k: {"Authorization": "Bearer %s" % k, "Content-Type": "application/json"},
        lambda f, t, s, h, x: {"from": f, "to": [t], "subject": s, "html": h, "text": x},
    ),
    "postmark": (
        "https://api.postmarkapp.com/email",
        lambda k: {"X-Postmark-Server-Token": k, "Content-Type": "application/json",
                   "Accept": "application/json"},
        lambda f, t, s, h, x: {"From": f, "To": t, "Subject": s, "HtmlBody": h, "TextBody": x,
                               "MessageStream": "outbound"},
    ),
    "brevo": (
        "https://api.brevo.com/v3/smtp/email",
        lambda k: {"api-key": k, "Content-Type": "application/json", "accept": "application/json"},
        lambda f, t, s, h, x: {"sender": _split_from(f), "to": [{"email": t}],
                               "subject": s, "htmlContent": h, "textContent": x},
    ),
}


def _split_from(f):
    """«Kleal <hello@a.com>» -> {"name": "Kleal", "email": "hello@a.com"} — этого просит Brevo."""
    m = re.match(r"\s*(.*?)\s*<([^>]+)>\s*$", str(f or ""))
    if m:
        return {"name": m.group(1) or "Kleal", "email": m.group(2)}
    return {"name": "Kleal", "email": str(f or "").strip()}


def configured():
    """Настроен ли настоящий провайдер. Нужно /health и админке, чтобы «письма не приходят»
    не выяснялось от пользователя."""
    p = os.environ.get("KLEAL_MAIL_PROVIDER", "none").strip().lower()
    return p in _PROVIDERS and bool(os.environ.get("KLEAL_MAIL_KEY", "").strip())


def _to_outbox(to, subject, html, code):
    try:
        os.makedirs(OUTBOX, exist_ok=True)
        safe = re.sub(r"[^a-z0-9._@-]", "_", str(to).lower())[:60]
        path = os.path.join(OUTBOX, "%d-%s.html" % (int(time.time()), safe))
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        # Код — в лог сервиса, а не в ответ ручки. Иначе «проверить без ключа» превратилось бы в
        # «любой может получить чужой код по HTTP».
        print("[mail] outbox %s | to=%s | subject=%s | code=%s" % (path, to, subject, code),
              flush=True)
        return path
    except Exception as e:
        print("[mail] outbox failed: %s" % e, flush=True)
        return ""


def send_code(to, code, lang="en", minutes=10):
    """Отправить письмо с кодом. Возвращает (ok, как_доставлено, подробность).

    Исключений не бросает: отказ почты не должен ронять ручку входа — человеку в этом случае
    честно говорят «не смогли отправить», а не показывают экран ввода кода, которого нет.
    """
    subject, html, text = render_code_email(code, lang=lang, minutes=minutes)
    provider = os.environ.get("KLEAL_MAIL_PROVIDER", "none").strip().lower()
    key = os.environ.get("KLEAL_MAIL_KEY", "").strip()
    sender = os.environ.get("KLEAL_MAIL_FROM", "Kleal <hello@aiopenware.com>").strip()

    if provider not in _PROVIDERS or not key:
        path = _to_outbox(to, subject, html, code)
        return True, "outbox", path

    url, headers, body = _PROVIDERS[provider]
    try:
        h = dict(headers(key))
        # СВОЙ User-Agent ОБЯЗАТЕЛЕН. Ручки провайдеров стоят за Cloudflare, и он режет запрос по
        # подписи клиента: urllib представляется «Python-urllib/3.x» и получает 403 с «error code:
        # 1010» — это отказ Cloudflare, а НЕ провайдера, и по тексту он на отказ в ключе похож.
        # Поймано на первой же настоящей отправке.
        h.setdefault("User-Agent", "Kleal/1.0 (+https://aiopenware.com)")
        h.setdefault("Accept", h.get("Accept", "application/json"))
        req = urllib.request.Request(url, data=json.dumps(body(sender, to, subject, html, text)).encode("utf-8"),
                                     headers=h)
        with urllib.request.urlopen(req, timeout=15) as r:
            r.read()
        return True, provider, ""
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        print("[mail] %s HTTP %s: %s" % (provider, e.code, detail), flush=True)
        return False, provider, "http %s" % e.code
    except Exception as e:
        print("[mail] %s failed: %s" % (provider, e), flush=True)
        return False, provider, type(e).__name__


# ------------------------------------------------------------------ само письмо
#
# ВЁРСТКА ПИСЬМА — НЕ ВЁРСТКА СТРАНИЦЫ. Почтовые клиенты (Gmail, Outlook, Mail.app) режут <style>,
# не знают flex и grid, теряют внешние картинки. Поэтому: таблицы, стили внутри атрибутов, ни
# одного внешнего файла. Логотип — текстом, а «картинка» нарисована фоном и кругом, потому что
# вложенная картинка у половины получателей не покажется, а у второй половины утяжелит письмо.
_T = {
    "ru": {
        "subject": "%s — код для входа в Kleal",
        "pre": "Код действует %d минут.",
        "hi": "Вход в Kleal",
        "lead": "Введи этот код в приложении — он действует %d минут.",
        "not_you": "Если это был не ты, просто не вводи код: без него ничего не произойдёт.",
        "foot": "Письмо отправлено автоматически, отвечать на него не нужно.",
    },
    "en": {
        "subject": "%s is your Kleal code",
        "pre": "This code is valid for %d minutes.",
        "hi": "Sign in to Kleal",
        "lead": "Enter this code in the app — it is valid for %d minutes.",
        "not_you": "If this wasn't you, just ignore it: nothing happens without the code.",
        "foot": "This message was sent automatically, no need to reply.",
    },
    "es": {
        "subject": "%s es tu código de Kleal",
        "pre": "El código es válido durante %d minutos.",
        "hi": "Entrar en Kleal",
        "lead": "Introduce este código en la app — es válido durante %d minutos.",
        "not_you": "Si no has sido tú, ignóralo: sin el código no ocurre nada.",
        "foot": "Mensaje automático, no hace falta responder.",
    },
}

_CORAL = "#F2415A"
_INK = "#12141A"
_MUTED = "#7A8091"
_BG = "#F4F5F7"


def render_code_email(code, lang="en", minutes=10):
    """(тема, html, текст). Текстовая часть обязательна: без неё письмо теряет балл у спам-фильтров
    и не читается в клиентах, где html выключен."""
    t = _T.get(lang, _T["en"])
    code = str(code)
    spaced = " ".join(code)          # «4 2 0 6 1 9» — так его не прочитают как число и не потеряют ноль

    subject = t["subject"] % code
    text = "%s\n\n%s\n\n%s\n\n%s\n\n%s" % (t["hi"], t["lead"] % minutes, code,
                                           t["not_you"], t["foot"])

    html = """<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{subject}</title></head>
<body style="margin:0;padding:0;background:{bg};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{pre}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:{bg};padding:32px 16px;">
  <tr><td align="center">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
           style="max-width:480px;background:#FFFFFF;border-radius:20px;overflow:hidden;
                  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">

      <!-- шапка: «картинка» без картинки — плашка цвета марки с кругом и знаком -->
      <tr><td style="background:{coral};padding:36px 32px 32px 32px;" align="center">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
          <td align="center" style="width:72px;height:72px;background:#FFFFFF;border-radius:36px;
                                    font-size:30px;line-height:72px;color:{coral};font-weight:700;">&#10022;</td>
        </tr></table>
        <div style="margin-top:18px;color:#FFFFFF;font-size:22px;font-weight:700;
                    letter-spacing:-0.3px;">kleal</div>
      </td></tr>

      <tr><td style="padding:32px 32px 8px 32px;">
        <div style="font-size:22px;line-height:28px;font-weight:700;color:{ink};">{hi}</div>
        <div style="margin-top:10px;font-size:15px;line-height:22px;color:{muted};">{lead}</div>
      </td></tr>

      <!-- сам код: крупно, моноширинно, с разрядкой -->
      <tr><td style="padding:24px 32px 8px 32px;" align="center">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"><tr>
          <td align="center" style="background:{bg};border-radius:14px;padding:22px 12px;">
            <span style="font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
                         font-size:34px;line-height:38px;font-weight:700;color:{ink};
                         letter-spacing:6px;">{spaced}</span>
          </td>
        </tr></table>
      </td></tr>

      <tr><td style="padding:16px 32px 28px 32px;">
        <div style="font-size:13px;line-height:20px;color:{muted};">{not_you}</div>
      </td></tr>

      <tr><td style="padding:18px 32px 26px 32px;border-top:1px solid #ECEEF2;">
        <div style="font-size:12px;line-height:18px;color:{muted};">{foot}</div>
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>""".format(lang=lang, subject=subject, bg=_BG, coral=_CORAL, ink=_INK, muted=_MUTED,
                         pre=t["pre"] % minutes, hi=t["hi"], lead=t["lead"] % minutes,
                         spaced=spaced, not_you=t["not_you"], foot=t["foot"])
    return subject, html, text
