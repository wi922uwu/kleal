# -*- coding: utf-8 -*-
"""«Заполнить через ChatGPT» — черновик анкеты от ИИ человека (18.10.2026).

Два пути к одному и тому же черновику:
  1. MCP-коннектор. Человек получает в приложении ЛИЧНУЮ ссылку и добавляет её в ChatGPT как свой
     коннектор (режим разработчика, «без авторизации»). ChatGPT вызывает наш инструмент и кладёт
     то, что знает о человеке. Авторизация — сам ключ в ссылке: он живёт сутки, умеет только одно —
     положить черновик ЭТОМУ человеку, и гасится новой ссылкой. Читать через него нельзя ничего.
  2. Вставка. Человек спросил свой ИИ сам и вставил ответ — разбираем тем же извлечением, что и
     разговор онбординга (EXTRACT_V2).

ЧЕРНОВИК — НЕ АНКЕТА. В профиль не пишется ничего: приложение показывает черновик, человек правит и
подтверждает, и только тогда данные идут прежним путём онбординга (интересы — со своим правилом
подтверждения). Имени, возраста, пола, свиданий, безопасности и разрешений в черновике не бывает
никогда: возраст держит рубеж 18+, и брать его со слов чужой модели нельзя.

Модуль без сети и без хранилища: хранение (файл аккаунтов) и ответы HTTP — в app.py. Здесь —
протокол MCP (Streamable HTTP, ответ JSON), схема инструмента и чистка присланного.
"""
import base64
import hashlib
import json
import re
import secrets
import time

LINK_TTL = 24 * 3600            # ссылка коннектора: сутки — хватит, чтобы дойти до компьютера
LINK_MAX_USES = 10              # сколько раз ChatGPT может положить черновик по одной ссылке
DRAFT_TTL = 7 * 24 * 3600       # черновик, который человек так и не открыл, не висит вечно
PASTE_MAX = 6000
PASTE_PER_HOUR = 10

PROTOCOLS = ("2025-06-18", "2025-03-26", "2024-11-05")
TOOL_NAME = "save_kleal_profile_draft"
LINK_TOOL = "prepare_kleal_profile_link"

GOALS = ("friends", "games", "language", "networking", "watch", "sport", "city_explore")
VIBES = ("calm", "energetic", "social", "intellectual", "chill", "curious", "competitive")
MODES = ("offline_first", "online_first", "hybrid")

PROMPT = {
    "ru": "Заполни мой профиль в Kleal по тому, что знаешь обо мне.",
    "en": "Fill in my Kleal profile from what you know about me.",
    "es": "Rellena mi perfil de Kleal con lo que sabes de mí.",
}

# Что попросить у ИИ, если человек идёт запасным путём (копирует ответ сам).
PASTE_PROMPT = {
    "ru": ("Расскажи обо мне для профиля в Kleal — приложении, где находят людей для совместных занятий. "
           "Только то, что знаешь точно: город и страна, на каких языках общаюсь, мои интересы и увлечения, "
           "что ищу (друзья, спорт, игры, языковой обмен, нетворкинг), какой я в компании, коротко о себе. "
           "Без возраста, здоровья и личных данных."),
    "en": ("Describe me for my Kleal profile — an app for finding people to do things with. Only what you know "
           "for sure: city and country, languages I speak, my interests and hobbies, what I'm looking for "
           "(friends, sport, games, language exchange, networking), what I'm like in company, a short bio. "
           "No age, health or personal identifiers."),
    "es": ("Descríbeme para mi perfil de Kleal, una app para encontrar gente con quien hacer cosas. Solo lo que "
           "sepas con seguridad: ciudad y país, idiomas que hablo, mis intereses y aficiones, qué busco (amigos, "
           "deporte, juegos, intercambio de idiomas, networking), cómo soy en grupo, una breve bio. "
           "Sin edad, salud ni datos personales."),
}

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?:\+?\d[\s\-().]?){9,}")
_URL = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
_HANDLE = re.compile(r"(?<!\w)@[A-Za-z0-9_.]{2,}")


# ---------------------------------------------------------------- ключи ссылок

def new_token():
    return secrets.token_urlsafe(24)


def token_hash(token):
    return hashlib.sha256(("kleal-mcp:" + str(token or "")).encode("utf-8")).hexdigest()


def issue_link(acc, now=None):
    """Новая ссылка для аккаунта: прежние гаснут. Возвращает ключ (в аккаунте — только его хэш)."""
    now = float(now or time.time())
    tok = new_token()
    acc["mcp_links"] = [{"h": token_hash(tok), "exp": now + LINK_TTL, "uses": 0, "at": now}]
    return tok, now + LINK_TTL


def find_link(accounts, token):
    """(ключ аккаунта, запись ссылки) по ключу из адреса, или (None, None). Сравнение — по хэшу."""
    h = token_hash(token)
    if not token or len(str(token)) < 20:
        return None, None
    for key, acc in (accounts or {}).items():
        if not isinstance(acc, dict) or acc.get("deleting"):
            continue
        for link in acc.get("mcp_links") or []:
            if isinstance(link, dict) and secrets.compare_digest(str(link.get("h") or ""), h):
                return key, link
    return None, None


def link_usable(link, now=None):
    now = float(now or time.time())
    if not link:
        return False, "unknown"
    if now > float(link.get("exp") or 0):
        return False, "expired"
    if int(link.get("uses") or 0) >= LINK_MAX_USES:
        return False, "used_up"
    return True, ""


# ---------------------------------------------------------------- чистка присланного

def _text(v, cap):
    s = " ".join(str(v or "").split())
    s = _URL.sub("", s)
    s = _EMAIL.sub("", s)
    s = _PHONE.sub("", s)
    s = _HANDLE.sub("", s)
    s = " ".join(s.split()).strip(" ,;-")
    return s[:cap]


def _list(v, cap_items, cap_len):
    if isinstance(v, str):
        v = [x for x in re.split(r"[,;\n]", v)]
    out, seen = [], set()
    for x in v if isinstance(v, (list, tuple)) else []:
        s = _text(x, cap_len)
        k = s.lower()
        if s and k not in seen:
            seen.add(k)
            out.append(s)
        if len(out) >= cap_items:
            break
    return out


def _enum(v, allowed):
    vals = v if isinstance(v, (list, tuple)) else [v]
    out = []
    for x in vals:
        s = str(x or "").strip().lower().replace(" ", "_")
        if s in allowed and s not in out:
            out.append(s)
    return out


def draft_profile(args):
    """Аргументы инструмента (или разобранный текст) -> анкета в форме онбординга.

    Берём только разрешённое; всё остальное — имя, возраст, пол, свидания, безопасность, контакты —
    выбрасывается молча, даже если прислано."""
    a = args if isinstance(args, dict) else {}
    prof = {}
    city = _text(a.get("city"), 80)
    if city:
        prof["city"] = city
    country = _text(a.get("country"), 80)
    if country:
        prof["country"] = country
    about = _text(a.get("about_me") or a.get("aboutMe"), 600)
    if about:
        prof["aboutMe"] = about
    langs = _list(a.get("languages"), 6, 30)
    if langs:
        prof["languages"] = {"comfortable": langs}
    ints = _list(a.get("interests"), 15, 40)
    if ints:
        prof["interests"] = {"explicit": ints}
    goals = _enum(a.get("goals"), GOALS)
    if goals:
        prof["goals"] = {"primary": goals}
    vibe = _enum(a.get("vibe"), VIBES)
    if vibe:
        prof["vibe"] = {"primary": vibe}
    mode = _enum(a.get("meet_format") or a.get("modePreference"), MODES)
    if mode:
        prof["format"] = {"modePreference": mode[0]}
    return prof


def from_extracted(prof):
    """Разобранное извлечением онбординга (EXTRACT_V2) -> те же разрешённые поля."""
    p = prof if isinstance(prof, dict) else {}
    langs = p.get("languages") if isinstance(p.get("languages"), dict) else {}
    lang_list = []
    for k in ("comfortable", "native", "fluent"):
        lang_list += [x for x in (langs.get(k) or []) if isinstance(x, str)]
    ints = p.get("interests") if isinstance(p.get("interests"), dict) else {}
    return draft_profile({
        "city": p.get("city"), "country": p.get("country"),
        "about_me": p.get("aboutMe"),
        "languages": lang_list,
        "interests": ints.get("explicit") or [],
        "goals": (p.get("goals") or {}).get("primary") if isinstance(p.get("goals"), dict) else None,
        "vibe": (p.get("vibe") or {}).get("primary") if isinstance(p.get("vibe"), dict) else None,
        "meet_format": (p.get("format") or {}).get("modePreference") if isinstance(p.get("format"), dict) else None,
    })


def draft_public(draft, now=None):
    """Черновик для приложения или None (нет / протух)."""
    now = float(now or time.time())
    if not isinstance(draft, dict) or not isinstance(draft.get("profile"), dict):
        return None
    if now - float(draft.get("at") or 0) > DRAFT_TTL:
        return None
    # review — интересы, которые не свелись к ключу реестра сами: каждый с готовыми вариантами и
    # квитанцией (token) для /api/onboarding/interest-confirm — тем же путём, что в анкете.
    return {"source": draft.get("source") or "chatgpt", "at": draft.get("at"), "profile": draft["profile"],
            "review": [r for r in (draft.get("review") or []) if isinstance(r, dict)]}


# ---------------------------------------------------------------- протокол MCP

TOOL = {
    "name": TOOL_NAME,
    "title": "Save Kleal profile draft",
    "description": (
        "Save a DRAFT of the user's Kleal profile. Kleal is an app for finding people to do things with "
        "(sport, games, coffee, language exchange, walks…). Fill it from what you already know about the "
        "user from memory and past conversations; ask them only if you know almost nothing. Include ONLY "
        "facts you are confident about — the user reviews and confirms everything in the Kleal app before "
        "anything is saved. Write interests as short concrete activities in the user's language "
        "(\"padel\", \"board games\", \"jazz concerts\"). Never include age, birth date, health, sexuality, "
        "relationship status, religion, politics, exact address, phone, email or social handles. "
        "After saving, tell the user to open Kleal to review the draft. If this tool is not available "
        "in this chat, use prepare_kleal_profile_link instead."),
    "inputSchema": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "City the user lives in, in English (e.g. Barcelona)."},
            "country": {"type": "string", "description": "Country, in English."},
            "languages": {"type": "array", "items": {"type": "string"}, "maxItems": 6,
                          "description": "Languages the user can comfortably talk in (e.g. Russian, English)."},
            "interests": {"type": "array", "items": {"type": "string"}, "maxItems": 15,
                          "description": "Concrete hobbies and activities the user enjoys, most important first."},
            "goals": {"type": "array", "items": {"type": "string", "enum": list(GOALS)},
                      "description": "What the user looks for on Kleal."},
            "vibe": {"type": "array", "items": {"type": "string", "enum": list(VIBES)}, "maxItems": 2,
                     "description": "What the user is like in company."},
            "meet_format": {"type": "string", "enum": list(MODES),
                            "description": "Prefers meeting in person, online, or both."},
            "about_me": {"type": "string", "maxLength": 600,
                         "description": "Two or three friendly sentences about the user, in their language."},
        },
        "additionalProperties": False,
    },
    "annotations": {"title": "Save Kleal profile draft", "readOnlyHint": False, "destructiveHint": False,
                    "idempotentHint": True, "openWorldHint": False},
}

# ИНСТРУМЕНТ ТОЛЬКО ДЛЯ ЧТЕНИЯ (18.10.2026). Живая проверка Ивана: при обращении «@kleal» вне режима
# разработчика ChatGPT отдаёт модели лишь инструменты с readOnlyHint=true — запись была скрыта, и ChatGPT
# ответил «действия с профилем недоступны» (tools/call не пришёл ни разу). Помечать запись как чтение —
# обман, поэтому второй инструмент ДЕЙСТВИТЕЛЬНО ничего не пишет: он лишь собирает ссылку на нашу страницу,
# где человек сам видит присланное и сам нажимает «Сохранить». Анкета лежит во фрагменте ссылки (#…):
# фрагмент браузер на сервер не отправляет, в журналы nginx он не попадает.
LINK_TOOL_DEF = {
    "name": LINK_TOOL,
    "title": "Prepare Kleal profile link",
    "description": (
        "Prepare a link the user opens to review and save a draft of their Kleal profile. Kleal is an app for "
        "finding people to do things with. Fill the fields from what you already know about the user from "
        "memory and past conversations; include ONLY facts you are confident about. This tool does not save "
        "anything by itself — it returns a link; show it to the user and ask them to open it and tap Save. "
        "Never include age, birth date, health, sexuality, relationship status, religion, politics, exact "
        "address, phone, email or social handles."),
    "inputSchema": TOOL["inputSchema"],
    "annotations": {"title": "Prepare Kleal profile link", "readOnlyHint": True, "destructiveHint": False,
                    "idempotentHint": True, "openWorldHint": False},
}

INSTRUCTIONS = ("Kleal helps people find others to do things with. To fill the user's Kleal profile from what you "
                "know about them, call save_kleal_profile_draft; if it is not available in this chat, call "
                "prepare_kleal_profile_link and give the user the link. The user confirms everything in Kleal.")


def encode_fragment(prof):
    raw = json.dumps(prof, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_fragment(frag):
    s = str(frag or "").strip()
    try:
        data = json.loads(base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode("utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}

_REASON_TEXT = {
    "expired": "This Kleal link has expired. Open Kleal and get a new link, then update the connector URL.",
    "used_up": "This Kleal link has been used too many times. Open Kleal and get a new link.",
    "unknown": "This Kleal link is not valid. Open Kleal and get a new link.",
}


def _ok(rid, result):
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _err(rid, code, msg):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": msg}}


def handle_rpc(msg, link_state, save, make_link=None):
    """Одно сообщение JSON-RPC -> ответ или None (уведомление).

    `link_state` — (годна ли ссылка, причина); `save(args) -> (ok, profile|reason)` кладёт черновик."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        return _err(msg.get("id") if isinstance(msg, dict) else None, -32600, "Invalid Request")
    rid, method = msg.get("id"), msg["method"]
    params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
    if "id" not in msg:                       # уведомление (notifications/initialized и т. п.)
        return None
    if method == "initialize":
        want = str(params.get("protocolVersion") or "")
        return _ok(rid, {"protocolVersion": want if want in PROTOCOLS else PROTOCOLS[0],
                         "capabilities": {"tools": {"listChanged": False}},
                         "serverInfo": {"name": "kleal", "title": "Kleal", "version": "1.0.0"},
                         "instructions": INSTRUCTIONS})
    if method == "ping":
        return _ok(rid, {})
    if method == "tools/list":
        return _ok(rid, {"tools": [TOOL, LINK_TOOL_DEF] if make_link else [TOOL]})
    if method == "tools/call" and params.get("name") == LINK_TOOL and make_link:
        usable, why = link_state
        if not usable:
            return _ok(rid, {"content": [{"type": "text", "text": _REASON_TEXT.get(why, _REASON_TEXT["unknown"])}],
                             "isError": True})
        prof = draft_profile(params.get("arguments") if isinstance(params.get("arguments"), dict) else {})
        if not prof:
            return _ok(rid, {"content": [{"type": "text", "text": "Nothing to include: no usable facts. "
                                                                   "Include at least city, languages or interests."}],
                             "isError": True})
        url = make_link(prof)
        return _ok(rid, {"content": [{"type": "text", "text": (
                             "Here is the link. Show it to the user and ask them to open it, check the draft and tap "
                             "Save — then it appears in the Kleal app: %s" % url)}],
                         "structuredContent": {"url": url, "fields": sorted(prof.keys())},
                         "isError": False})
    if method == "tools/call":
        if params.get("name") != TOOL_NAME:
            return _err(rid, -32602, "Unknown tool")
        usable, why = link_state
        if not usable:
            return _ok(rid, {"content": [{"type": "text", "text": _REASON_TEXT.get(why, _REASON_TEXT["unknown"])}],
                             "isError": True})
        args = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        ok, got = save(args)
        if not ok:
            return _ok(rid, {"content": [{"type": "text", "text": "Nothing to save: no usable facts. %s" % (got or "")}],
                             "isError": True})
        fields = sorted(got.keys())
        return _ok(rid, {"content": [{"type": "text", "text": (
                             "Saved a draft of the Kleal profile (%s). Tell the user to open the Kleal app: "
                             "they will see the draft there and confirm or edit it." % ", ".join(fields))}],
                         "structuredContent": {"saved": True, "fields": fields},
                         "isError": False})
    return _err(rid, -32601, "Method not found")


def handle_body(raw, link_state, save, make_link=None):
    """Тело POST -> (HTTP-код, тело ответа или None). Пакет сообщений — список ответов."""
    try:
        data = json.loads(raw or "")
    except Exception:
        return 400, _err(None, -32700, "Parse error")
    if isinstance(data, list):
        out = [r for r in (handle_rpc(m, link_state, save, make_link) for m in data) if r is not None]
        return (200, out) if out else (202, None)
    r = handle_rpc(data, link_state, save, make_link)
    return (200, r) if r is not None else (202, None)
