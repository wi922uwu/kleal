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
        # ОТКАЗ БЫВАЕТ ВРЕМЕННЫЙ И ПОСТОЯННЫЙ, и человеку это разные новости. Пока домен не
        # подтверждён, провайдер разрешает писать только на адрес владельца аккаунта и отвечает
        # 403 на всё остальное — сколько ни повторяй, письма не будет. Экран, говорящий «попробуй
        # через минуту», в этом случае гоняет человека по кругу. Отделяем это одно состояние.
        low = detail.lower()
        if e.code == 403 and ("verify a domain" in low or "your own email address" in low):
            return False, provider, "not allowed"
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

# ЦВЕТА ВЗЯТЫ ИЗ ТОКЕНОВ ПРИЛОЖЕНИЯ, а не подобраны на глаз. Здесь стояли похожие, но другие:
# #F2415A вместо фирменного #F13A59, серый #7A8091 вместо #5A616E, фон #F4F5F7 вместо кремового.
# Разница мелкая по числам и заметная в жизни: письмо открывают за минуту до того, как увидят
# экран, и два почти одинаковых красных читаются как подделка одного из них.
#
# Дублировать значения приходится: mailer живёт на сервере и до src/theme.ts не дотягивается.
# Если тронешь палитру там — поправь и здесь, других копий нет.
_PRIMARY = "#F13A59"        # color.primary
_MAGENTA = "#DD48FF"        # color.brandMagenta — второй конец фирменного градиента
_INK = "#181B22"            # color.fg
_MUTED = "#5A616E"          # color.muted
_BG = "#F5F1EC"             # color.ambientBase — кремовая земля, общая для всех экранов
_CARD = "#FFFFFF"           # color.card
_LINE = "#ECEEF2"           # color.line
_FIELD = "#F7F8FA"          # color.bg — подложка под кодом
_WASH  = "#FDF1F3"          # тёплая нота: фирменный, разбавленный до бумаги


def render_code_email(code, lang="en", minutes=10):
    """(тема, html, текст). Текстовая часть обязательна: без неё письмо теряет балл у спам-фильтров
    и не читается в клиентах, где html выключен."""
    t = _T.get(lang, _T["en"])
    code = str(code)
    spaced = " ".join(code)          # «4 2 0 6 1 9» — так его не прочитают как число и не потеряют ноль

    subject = t["subject"] % code
    text = "%s\n\n%s\n\n%s\n\n%s\n\n%s" % (t["hi"], t["lead"] % minutes, code,
                                           t["not_you"], t["foot"])

    # КОД РАЗЛОЖЕН ПО КЛЕТКАМ, ПО ОДНОЙ ЦИФРЕ. Одной строкой с разрядкой он не помещался на
    # телефоне и переносился посреди числа — сообщено с устройства. Клетки заданы долями (шесть по
    # 16.66%), поэтому сужаются вместе с письмом и не переносятся никогда. Заодно это привычный
    # вид поля для кода: ровно так он набирается в самом приложении.
    cells = "".join(
        '<td width="16.66%" align="center" style="padding:0 3px;">'
        '<div style="background:{field};border:1px solid {line};border-radius:14px;'
        'padding:14px 0;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;'
        'font-size:26px;line-height:30px;font-weight:700;color:{ink};">{d}</div></td>'.format(
            field=_FIELD, line=_LINE, ink=_INK, d=d)
        for d in code)

    # СВЕТЛЫЕ НОТЫ ВМЕСТО ЦВЕТНОЙ ПЛИТЫ. Раньше шапкой была насыщенная градиентная плашка во всю
    # ширину — рядом с приложением это чужое: там кремовая бумага и едва различимые пятна, а
    # фирменный цвет появляется точечно. Здесь то же: тёплая полоса поверх карточки и градиент
    # только на самом лице.
    html = """<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{subject}</title>
<style>
  @media only screen and (max-width:440px) {{
    .pad {{ padding-left:20px !important; padding-right:20px !important; }}
    .digit {{ font-size:21px !important; padding:11px 0 !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:{bg};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{pre}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:{bg};padding:44px 14px;">
  <tr><td align="center">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
           style="max-width:470px;background:{card};border-radius:24px;overflow:hidden;
                  box-shadow:0 6px 22px rgba(24,27,34,0.08);
                  font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">

      <!-- Тёплая нота: очень светлая полоса, а не заливка цветом. -->
      <tr><td style="background-color:{wash};
                     background-image:linear-gradient(180deg,{wash} 0%,{card} 100%);
                     padding:34px 32px 4px 32px;" class="pad" align="center">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
          <td align="center" valign="middle"
              style="width:56px;height:56px;border-radius:28px;
                     background-color:{primary};
                     background-image:linear-gradient(135deg,{primary} 0%,{magenta} 100%);">
            <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
              <td style="width:9px;height:9px;background:{ink};border-radius:5px;font-size:0;line-height:0;">&nbsp;</td>
              <td style="width:9px;font-size:0;line-height:0;">&nbsp;</td>
              <td style="width:9px;height:9px;background:{ink};border-radius:5px;font-size:0;line-height:0;">&nbsp;</td>
            </tr></table>
          </td>
        </tr></table>
      </td></tr>

      <tr><td style="padding:20px 32px 0 32px;" class="pad" align="center">
        <div style="font-size:23px;line-height:29px;font-weight:700;color:{ink};
                    letter-spacing:-0.3px;">{hi}</div>
        <div style="margin-top:8px;font-size:15px;line-height:22px;color:{muted};">{lead}</div>
      </td></tr>

      <tr><td style="padding:22px 29px 4px 29px;" class="pad">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>{cells}</tr>
        </table>
      </td></tr>

      <tr><td style="padding:16px 32px 26px 32px;" class="pad" align="center">
        <div style="font-size:13px;line-height:20px;color:{muted};">{not_you}</div>
      </td></tr>

      <tr><td style="padding:16px 32px 24px 32px;border-top:1px solid {line};" class="pad" align="center">
        <div style="font-size:12px;line-height:18px;color:{muted};">{foot}</div>
      </td></tr>
    </table>

    <div style="max-width:470px;margin:16px auto 0 auto;font-size:12px;line-height:18px;
                color:{muted};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,
                Helvetica,Arial,sans-serif;">Kleal</div>
  </td></tr>
</table>
</body></html>""".format(lang=lang, subject=subject, bg=_BG, primary=_PRIMARY, magenta=_MAGENTA,
                         card=_CARD, line=_LINE, field=_FIELD, ink=_INK, muted=_MUTED, wash=_WASH,
                         pre=t["pre"] % minutes, hi=t["hi"], lead=t["lead"] % minutes,
                         cells=cells, not_you=t["not_you"], foot=t["foot"])
    return subject, html, text
