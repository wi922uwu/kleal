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
private outbox/mail-<random>.html с правами0600. Код, адрес и тело не пишутся в лог.
Каталог0700 не должен публиковаться через HTTP; письмо доступно только оператору.
Наружу код при этом НЕ уходит ни при каких настройках: в ответе ручки его нет никогда.
"""
import base64
import json
import os
import re
import time
import tempfile
import urllib.error
import urllib.request

OUTBOX = os.environ.get("KLEAL_MAIL_OUTBOX",
                        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                     "outbox"))

# Как сложить запрос к каждому провайдеру: (url, заголовки(ключ), тело(from,to,subject,html,text,
# картинки)). Картинки — список (cid, имя файла, base64) для вложений «внутрь письма»: внешних
# ссылок в письме нет (см. ниже), поэтому маскот едет вложением и вызывается как cid:имя.
_PROVIDERS = {
    "resend": (
        "https://api.resend.com/emails",
        lambda k: {"Authorization": "Bearer %s" % k, "Content-Type": "application/json"},
        lambda f, t, s, h, x, a: dict({"from": f, "to": [t], "subject": s, "html": h, "text": x},
                                      **({"attachments": [{"filename": n, "content": b, "content_id": c,
                                                           "content_type": "image/png"} for c, n, b in a]} if a else {})),
    ),
    "postmark": (
        "https://api.postmarkapp.com/email",
        lambda k: {"X-Postmark-Server-Token": k, "Content-Type": "application/json",
                   "Accept": "application/json"},
        lambda f, t, s, h, x, a: dict({"From": f, "To": t, "Subject": s, "HtmlBody": h, "TextBody": x,
                                       "MessageStream": "outbound"},
                                      **({"Attachments": [{"Name": n, "Content": b, "ContentType": "image/png",
                                                           "ContentID": "cid:" + c} for c, n, b in a]} if a else {})),
    ),
    "brevo": (
        "https://api.brevo.com/v3/smtp/email",
        lambda k: {"api-key": k, "Content-Type": "application/json", "accept": "application/json"},
        lambda f, t, s, h, x, a: {"sender": _split_from(f), "to": [{"email": t}],
                                  "subject": s, "htmlContent": h, "textContent": x},
    ),
}
# Кто умеет картинки-вложения с cid. Brevo через этот вызов — нет: ему письмо уходит без картинок.
_CID_OK = ("resend", "postmark")


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
        os.makedirs(OUTBOX, mode=0o700, exist_ok=True)
        os.chmod(OUTBOX, 0o700)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=OUTBOX,
                                         prefix="mail-", suffix=".html", delete=False) as f:
            path = f.name
            f.write(html)
        print("[mail] private outbox message saved", flush=True)
        return path
    except Exception as e:
        print("[mail] outbox failed: %s" % type(e).__name__, flush=True)
        return ""


def send_code(to, code, lang="en", minutes=10):
    """Отправить письмо с кодом. Возвращает (ok, как_доставлено, подробность).

    Исключений не бросает: отказ почты не должен ронять ручку входа — человеку в этом случае
    честно говорят «не смогли отправить», а не показывают экран ввода кода, которого нет.
    """
    provider = os.environ.get("KLEAL_MAIL_PROVIDER", "none").strip().lower()
    key = os.environ.get("KLEAL_MAIL_KEY", "").strip()
    live = provider in _PROVIDERS and bool(key)
    mode = ("cid" if provider in _CID_OK else "none") if live else "data"
    subject, html, text = render_code_email(code, lang=lang, minutes=minutes, to=to, images=mode)
    atts = _inline_images() if mode == "cid" else []
    # Домен — в punycode. Провайдеры принимают только ASCII, а «почта.рф» — законный домен: без
    # этой строки письмо на него получало 422 и никуда не уходило. Имя ящика не трогаем: его
    # кодировать нечем, и его уже отбил request_code.
    try:
        _local, _dom = str(to).rsplit("@", 1)
        to = _local + "@" + _dom.encode("idna").decode("ascii")
    except (ValueError, UnicodeError):
        pass
    sender = os.environ.get("KLEAL_MAIL_FROM", "Kleal <hello@aiopenware.com>").strip()

    if not live:
        path = _to_outbox(to, subject, html, code)
        return bool(path), "outbox", path if path else "outbox unavailable"

    url, headers, body = _PROVIDERS[provider]
    try:
        h = dict(headers(key))
        # СВОЙ User-Agent ОБЯЗАТЕЛЕН. Ручки провайдеров стоят за Cloudflare, и он режет запрос по
        # подписи клиента: urllib представляется «Python-urllib/3.x» и получает 403 с «error code:
        # 1010» — это отказ Cloudflare, а НЕ провайдера, и по тексту он на отказ в ключе похож.
        # Поймано на первой же настоящей отправке.
        h.setdefault("User-Agent", "Kleal/1.0 (+https://aiopenware.com)")
        h.setdefault("Accept", h.get("Accept", "application/json"))
        req = urllib.request.Request(url, data=json.dumps(body(sender, to, subject, html, text, atts)).encode("utf-8"),
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
        print("[mail] %s HTTP %s" % (provider, e.code), flush=True)
        # ОТКАЗ БЫВАЕТ ВРЕМЕННЫЙ И ПОСТОЯННЫЙ, и человеку это разные новости. Пока домен не
        # подтверждён, провайдер разрешает писать только на адрес владельца аккаунта и отвечает
        # 403 на всё остальное — сколько ни повторяй, письма не будет. Экран, говорящий «попробуй
        # через минуту», в этом случае гоняет человека по кругу. Отделяем это одно состояние.
        low = detail.lower()
        if e.code == 403 and ("verify a domain" in low or "your own email address" in low):
            return False, provider, "not allowed"
        return False, provider, "http %s" % e.code
    except Exception as e:
        print("[mail] %s failed: %s" % (provider, type(e).__name__), flush=True)
        return False, provider, type(e).__name__


# ------------------------------------------------------------------ само письмо
#
# ВЁРСТКА ПИСЬМА — НЕ ВЁРСТКА СТРАНИЦЫ. Gmail, Outlook и Mail.app режут часть CSS, не знают flex и
# grid. Поэтому: таблицы, стили в атрибутах, ни одной внешней ссылки или картинки (это проверяет
# tools/auth_smoke.py — письмо с кодом не зовёт «нажми сюда» и не тянет пиксели с чужих адресов).
#
# Стиль — ЛЕНДИНГА (aiopenware.com, 18.10.2026), а не нейтральной карточки:
#   • всё письмо на горячем градиенте маскота; где градиента нет (Outlook), остаётся сплошной
#     фирменный цвет из bgcolor — письмо всё равно узнаётся;
#   • огромный белый заголовок с плотной разрядкой и настоящий 3D-маскот рядом — как первый экран;
#   • код — в стеклянном чипе, как слово-чип на лендинге; одной строкой и без переносов, поэтому
#     выделяется и копируется целиком;
#   • низ — одна строка «не ты? проигнорируй» и подпись, без отдельных карточек: письмо с кодом
#     должно читаться за секунду и помещаться в экран телефона целиком (Иван: «слишком длинное»).
# Картинки (маскот, диско-шар, кроссовок) лежат рядом в mail-assets/ и едут вложениями с cid.
# Нет файла или провайдер не умеет cid — письмо собирается без картинок, вёрстка не рассыпается.
import html as _html

_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mail-assets")
_IMAGES = (("kleal-mascot", "kleal-mascot.png"), ("kleal-disco", "disco.png"), ("kleal-sneaker", "sneaker.png"))


def _inline_images():
    """[(cid, имя файла, base64)] — только те картинки, что реально лежат в mail-assets/."""
    out = []
    for cid, name in _IMAGES:
        try:
            with open(os.path.join(_ASSETS, name), "rb") as f:
                out.append((cid, name, base64.b64encode(f.read()).decode("ascii")))
        except OSError:
            pass
    return out


_T = {
    "ru": {
        "subject": "%s — код для входа в Kleal",
        "pre": "Твой код: %s. Действует %s.",
        "tag": "Код для входа",
        "hi": "Вот твой код.",
        "lead": "Введи его в Kleal, чтобы войти.",
        "valid": "Действует %s",
        "to": "Запрошен для %s",
        "safe_t": "Не запрашивал код?",
        "safe": "Просто проигнорируй письмо. Без кода в твой аккаунт никто не войдёт.",
        "foot": "Письмо отправлено автоматически, отвечать на него не нужно.",
    },
    "en": {
        "subject": "%s is your Kleal code",
        "pre": "Your code is %s. It works for %s.",
        "tag": "Sign-in code",
        "hi": "Here's your code.",
        "lead": "Enter it in Kleal to sign in.",
        "valid": "Works for %s",
        "to": "Requested for %s",
        "safe_t": "Didn't ask for this?",
        "safe": "Just ignore this email. Without the code, nobody can get into your account.",
        "foot": "This email was sent automatically. No need to reply.",
    },
    "es": {
        "subject": "%s es tu código de Kleal",
        "pre": "Tu código es %s. Vale durante %s.",
        "tag": "Código de acceso",
        "hi": "Aquí tienes tu código.",
        "lead": "Introdúcelo en Kleal para entrar.",
        "valid": "Vale durante %s",
        "to": "Solicitado para %s",
        "safe_t": "¿No lo has pedido tú?",
        "safe": "Ignora este correo. Sin el código nadie puede entrar en tu cuenta.",
        "foot": "Mensaje automático, no hace falta responder.",
    },
}


def _minutes(n, lang):
    """«10 минут», «1 минуту», «3 минуты» — в винительном, как после «действует»."""
    n = int(n)
    if lang == "ru":
        if n % 10 == 1 and n % 100 != 11:
            w = "минуту"
        elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            w = "минуты"
        else:
            w = "минут"
        return "%d %s" % (n, w)
    if lang == "es":
        return "%d minuto%s" % (n, "" if n == 1 else "s")
    return "%d minute%s" % (n, "" if n == 1 else "s")


# ЦВЕТА — с лендинга (landing/index.html): горячий градиент первого экрана, бумага, слива подвала.
_HOT = "#E5306A"            # основа градиента; она же сплошная заливка там, где градиента нет
_HOT_PINK = "#FF6FA8"
_HOT_VIOLET = "#B13CFF"
_GLASS_FALLBACK = "#EE5A86" # «стекло» чипа для клиентов без rgba
_INK = "#1A1024"
_MUTED = "#6B6377"
_PAPER = "#FFF8FB"
_LILAC = "#F3EDFF"
_PLUM = "#2A0E3A"
_WORD = "#FF5A8A"           # гигантское «kleal» в подвале
_OK = "#7CFFB2"             # зелёная точка «действует», как «Private beta in Barcelona»

_FONT = "-apple-system,BlinkMacSystemFont,'SF Pro Display','Helvetica Neue','Segoe UI',Roboto,Arial,sans-serif"


def render_code_email(code, lang="en", minutes=10, to=None, images="cid"):
    """(тема, html, текст). images: "cid" — картинки вложениями, "data" — встроены в файл (outbox и
    превью), "none" — без картинок. Текстовая часть обязательна: без неё письмо теряет балл у
    спам-фильтров и не читается в клиентах, где html выключен."""
    t = _T.get(lang, _T["en"])
    code = str(code)
    mins = _minutes(minutes, lang)
    esc = _html.escape

    subject = t["subject"] % code
    lines = [t["hi"], "", code, "", t["lead"], t["valid"] % mins]
    if to:
        lines.append(t["to"] % to)
    lines += ["", t["safe_t"], t["safe"], "", "Kleal", t["foot"]]
    text = "\n".join(lines)

    have = {c for c, _n, _b in _inline_images()} if images != "none" else set()
    data = {c: b for c, _n, b in _inline_images()} if images == "data" else {}

    def img(cid, w, alt="", style=""):
        if cid not in have:
            return ""
        src = ("data:image/png;base64," + data[cid]) if images == "data" else ("cid:" + cid)
        return ('<img src="%s" width="%d" alt="%s" style="display:block;width:%dpx;max-width:100%%;height:auto;'
                'border:0;outline:none;text-decoration:none;%s">' % (src, w, esc(alt), w, style))

    pre = esc(t["pre"] % (code, mins)) + ("&#847;&zwnj;&nbsp;" * 60)
    mascot = img("kleal-mascot", 150, "Kleal")
    mascot_col = ('<td width="150" valign="bottom" align="right" class="mcol" style="width:150px;padding-left:8px;">%s</td>'
                  % mascot) if mascot else ""
    objs = img("kleal-disco", 58) and ('<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="right"><tr>'
                                        '<td valign="top" style="padding-right:6px;">%s</td><td valign="bottom" style="padding-top:18px;">%s</td>'
                                        '</tr></table>' % (img("kleal-disco", 58), img("kleal-sneaker", 70)))
    to_block = ""
    if to:
        to_block = ('<div style="margin-top:4px;font-family:{f};font-size:14px;line-height:21px;color:#FFFFFF;color:rgba(255,255,255,0.8);">{lab}</div>'
                    .format(f=_FONT,
                            lab=esc(t["to"] % "\u0000").replace(
                                "\u0000", '<b style="color:#FFFFFF;font-weight:700;">%s</b>' % esc(str(to)))))

    html = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="x-apple-disable-message-reformatting">
<meta name="format-detection" content="telephone=no, date=no, address=no, email=no">
<meta name="color-scheme" content="light only">
<meta name="supported-color-schemes" content="light only">
<title>{subject}</title>
<style>
  :root {{ color-scheme: light only; }}
  body {{ margin:0 !important; padding:0 !important; }}
  .code {{ font-variant-numeric: tabular-nums; }}
  @media only screen and (max-width:480px) {{
    .outer {{ padding:12px 8px 28px 8px !important; }}
    .pad {{ padding-left:22px !important; padding-right:22px !important; }}
    .h1 {{ font-size:40px !important; line-height:38px !important; letter-spacing:-1.8px !important; }}
    .mcol {{ width:112px !important; }}
    .mcol img {{ width:112px !important; }}
    .code {{ font-size:36px !important; letter-spacing:8px !important; padding:18px 4px 18px 12px !important; }}
  }}
</style>
</head>
<body style="margin:0;padding:0;background:#D93A8E;-webkit-text-size-adjust:100%;">
<div style="display:none;max-height:0;max-width:0;overflow:hidden;opacity:0;mso-hide:all;">{pre}</div>

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{hot}"
       style="background-color:{hot};
              background-image:radial-gradient(70% 40% at 0% 0%,{pink} 0%,rgba(255,111,168,0) 100%),
                               radial-gradient(80% 45% at 100% 38%,{violet} 0%,rgba(177,60,255,0) 100%),
                               linear-gradient(180deg,{hot} 0%,#D93A8E 100%);">
<tr><td align="center" class="outer" style="padding:20px 14px 30px 14px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:520px;">

  <!-- ===== первый экран: марка, заголовок, маскот ===== -->
  <tr><td class="pad" style="padding:18px 26px 0 26px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
      <td align="left" style="font-family:{font};font-size:26px;line-height:30px;font-weight:800;letter-spacing:-1.3px;color:#FFFFFF;">kleal</td>
      <td align="right">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" align="right"><tr>
          <td bgcolor="#FFFFFF" style="padding:9px 16px;border-radius:999px;background:#FFFFFF;
                     font-family:{font};font-size:13px;line-height:16px;font-weight:700;color:{ink};">{tag}</td>
        </tr></table>
      </td>
    </tr></table>
  </td></tr>

  <tr><td class="pad" style="padding:18px 26px 0 26px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
      <td valign="bottom" align="left" class="h1"
          style="font-family:{font};font-size:54px;line-height:50px;font-weight:800;letter-spacing:-2.6px;color:#FFFFFF;padding-bottom:6px;">{hi}</td>
      {mascot_col}
    </tr></table>
  </td></tr>

  <!-- ===== код: стеклянный чип, как слово на первом экране ===== -->
  <tr><td class="pad" style="padding:24px 26px 0 26px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr><td align="center" bgcolor="{glass}"
              style="background-color:{glass};background-color:rgba(255,255,255,0.20);border:2px solid #F7A9C2;border:2px solid rgba(255,255,255,0.62);
                     border-radius:30px;box-shadow:inset 0 2px 0 rgba(255,255,255,0.45);">
        <div class="code" style="padding:22px 4px 22px 16px;font-family:{font};font-size:48px;line-height:52px;font-weight:800;
                                 letter-spacing:13px;white-space:nowrap;color:#FFFFFF;">{code}</div>
      </td></tr>
    </table>
  </td></tr>

  <tr><td class="pad" style="padding:18px 26px 0 26px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
      <td valign="top" align="left" style="font-family:{font};">
        <div style="font-size:17px;line-height:25px;color:#FFFFFF;">{lead}</div>
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-top:12px;"><tr>
          <td valign="middle" style="padding-right:9px;">
            <div style="width:9px;height:9px;border-radius:5px;background:{ok};box-shadow:0 0 0 4px rgba(124,255,178,0.28);font-size:0;line-height:0;">&nbsp;</div>
          </td>
          <td valign="middle" style="font-family:{font};font-size:15px;line-height:20px;font-weight:600;color:#FFFFFF;">{valid}</td>
        </tr></table>
      </td>
      <td valign="top" align="right" width="140" style="width:140px;">{objs}</td>
    </tr></table>
  </td></tr>

  <!-- ===== низ: одной строкой, без отдельных карточек — письмо должно помещаться в экран ===== -->
  <tr><td class="pad" style="padding:26px 26px 0 26px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
      <tr><td style="border-top:1px solid #F59BBE;border-top:1px solid rgba(255,255,255,0.35);padding-top:18px;font-family:{font};">
        <div style="font-size:14px;line-height:21px;color:#FFFFFF;"><b style="font-weight:700;">{safe_t}</b> {safe}</div>
        {to_block}
        <div style="margin-top:14px;font-size:12px;line-height:18px;color:#FFFFFF;color:rgba(255,255,255,0.72);"><b style="font-weight:800;letter-spacing:-0.4px;color:#FFFFFF;">kleal</b>&nbsp;&nbsp;{foot}</div>
      </td></tr>
    </table>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>""".format(
        lang=esc(lang), subject=esc(subject), pre=pre, font=_FONT,
        hot=_HOT, pink=_HOT_PINK, violet=_HOT_VIOLET, glass=_GLASS_FALLBACK, ink=_INK, muted=_MUTED,
        paper=_PAPER, lilac=_LILAC, plum=_PLUM, word=_WORD, ok=_OK,
        tag=esc(t["tag"]), hi=esc(t["hi"]), mascot_col=mascot_col, code=esc(code), lead=esc(t["lead"]),
        valid=esc(t["valid"] % mins), objs=objs, to_block=to_block, safe_t=esc(t["safe_t"]), safe=esc(t["safe"]),
        foot=esc(t["foot"]))
    return subject, html, text
