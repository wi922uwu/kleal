# -*- coding: utf-8 -*-
"""БУДИ V2 — ОДИН ВЫЗОВ МОДЕЛИ НА ХОД.

ЗАЧЕМ. Карта V1 (23.09.2026) показала, почему агент «везде тупит»:
  * вся переписка уходила модели ОДНИМ сообщением с подписями «User:»/«Buddy:», а саму модель
    называли «Kleal» — она не видела, какие реплики её, и путала себя с человеком;
  * профиль подставлялся кодами \\u0418\\u0432\\u0430\\u043d вместо «Иван»;
  * ответ писала одна модель, а карточку — фильтрация, карточная модель и около сорока правил;
    между ними шёл только английский пересказ, поэтому в чате «овцы», а в карточке их нет;
  * до девяти вызовов модели на одно сообщение.

КАК УСТРОЕНО. Один вызов: модель видит переписку как есть (свои реплики — assistant, человека —
user), профиль нормальным текстом и словарь интересов, и возвращает сразу ответ И карточку (или
«карточки нет»). Ответ и карточку пишет одна голова — противоречить им негде.

ЧТО ДЕЛАЕТ КОД. Только то, чего модели доверять нельзя, и только функциями V1, а не своими копиями:
возраст и безопасность, язык ответа, «встреча назначена», сито чипов (опора на слова человека,
никаких чипов из профиля), контракт телефона. Любая беда V2 до записи ответа — возврат False,
и ход обрабатывает прежний буди.

ЧЕГО ЗДЕСЬ НАРОЧНО НЕТ: падежей, таблиц глаголов, разбора разворотов. Если тянет добавить сюда
регулярку про язык — правь промпт (он же лежит в админке под ключом buddy.v2).

КОНТРАКТ ТЕЛЕФОНА (проверено по app/buddy.tsx и src/buddy.ts на боевой копии 24.09.2026):
  * чипы карточки телефон рисует из intent.topics, поле tags он не показывает;
  * окно затеи не выезжает, если ответ кончается вопросом — поэтому хвостовой вопрос при затее снимаем;
  * в потоке шлём только событие done: delta и done одной пачкой заставляют экран напечатать ответ дважды.
"""
import ast
import io
import json
import os
import re
import time
import unicodedata
import hashlib
import threading
import urllib.error
import urllib.request

_ROOT = os.environ.get("KLEAL_ROOT") or "/opt/kleal/kleal-ms"
_КЭШ = {}
_МАРКЕР = re.compile(r"(?im)^[\s`*_>#]*#{2,}\s*card\b[\s:*_`]*$")
_РОЛИ = ("play", "watch", "discuss", "practise", "attend", "meet")
_ОКНО = 12            # столько реплик видит модель; сторож безопасности смотрит столько же


def enabled(body):
    """Выключатель KLEAL_V2: off (по умолчанию) — V2 нет; request — только для запроса с "v2": "1"
    в теле (так V2 сравнивается с V1 на боевой службе, приложение этот флаг не шлёт); all — всем."""
    режим = (os.environ.get("KLEAL_V2") or "off").strip().lower()
    if режим == "all":
        # "v2": "0" в теле — чёрный ход к V1: так V1 и V2 сравниваются и после включения V2 всем.
        return str((body or {}).get("v2") or "") != "0"
    if режим == "request":
        return str((body or {}).get("v2") or "") == "1"
    return False


# ---------------------------------------------------------------- словарь и справочники

def _словарь(B):
    """Ключи реестра для промпта — без общих корзин (gaming, sports…): их модель брала вместо
    конкретного, а код потом всё равно выбрасывал."""
    if "ключи" not in _КЭШ:
        рег = json.load(io.open(os.path.join(_ROOT, "shared", "interests.json"), encoding="utf-8"))
        дер = рег.get("tree", рег)
        ключи = set()

        def обойти(у):
            if isinstance(у, dict):
                for k, v in у.items():
                    ключи.add(k)
                    обойти(v)
            elif isinstance(у, list):
                for v in у:
                    if isinstance(v, str):
                        ключи.add(v)
                    else:
                        обойти(v)
        обойти(дер)
        общие = getattr(B, "_GENERIC_TOPIC", set()) or set()
        _КЭШ["ключи"] = sorted(k for k in ключи if isinstance(k, str) and len(k) > 1 and k not in общие)
    return _КЭШ["ключи"]


def _подписи(ключ):
    """Подписи ключа на всех языках (реестр: labels / labels_auto)."""
    if "подписи" not in _КЭШ:
        рег = json.load(io.open(os.path.join(_ROOT, "shared", "interests.json"), encoding="utf-8"))
        карта = {}
        for имя in ("labels", "labels_auto"):
            ист = рег.get(имя)
            if isinstance(ист, dict):
                for k, v in ист.items():
                    карта.setdefault(k, []).extend(str(x) for x in (v.values() if isinstance(v, dict) else [v]) if x)
            elif isinstance(ист, list):
                for э in ист:
                    if isinstance(э, dict) and (э.get("key") or э.get("k")):
                        k = э.get("key") or э.get("k")
                        карта.setdefault(k, []).extend(str(x) for kk, x in э.items() if kk not in ("key", "k", "id") and isinstance(x, str))
        _КЭШ["подписи"] = карта
    return _КЭШ["подписи"].get(ключ, [])


def _категории():
    """Категории и справочники тип/домен — из самой фильтрации. Кешируется только целиком:
    полусчитанный справочник молча превращал бы всё в social."""
    if "кат" in _КЭШ:
        return _КЭШ["кат"]
    кат, тип, дом = None, None, None
    src = io.open(os.path.join(_ROOT, "services", "filtration", "app.py"), encoding="utf-8").read()
    for n in ast.parse(src).body:
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name):
            имя = n.targets[0].id
            if имя in ("CATEGORIES", "CAT_TO_TYPE", "CAT_TO_DOMAIN"):
                знач = ast.literal_eval(n.value)
                if имя == "CATEGORIES":
                    кат = list(знач)
                elif имя == "CAT_TO_TYPE":
                    тип = dict(знач)
                else:
                    дом = dict(знач)
    if not (кат and тип and дом):
        raise RuntimeError("справочник категорий фильтрации не прочитан")
    _КЭШ["кат"] = (кат, тип, дом)
    return _КЭШ["кат"]


# ---------------------------------------------------------------- промпт

_ЯЗЫК = {"ru": "Russian", "en": "English", "es": "Spanish",
         "de": "German", "fr": "French", "it": "Italian", "pt": "Portuguese (European)"}
_ОБРАЩЕНИЕ = {"ru": "«ты»", "en": "«you»", "es": "«tú»", "de": "«du»", "fr": "«tu»", "it": "«tu»", "pt": "«tu»"}
# Телефон знает только эти три: поле lang в ответе остаётся в них, новый язык — только в тексте ответа.
_ЯЗЫК_КЛИЕНТА = ("ru", "en", "es")


def _язык_клиенту(lang, просили):
    if lang in _ЯЗЫК_КЛИЕНТА:
        return lang
    просили = str(просили or "").strip().lower()
    return просили if просили in _ЯЗЫК_КЛИЕНТА else "en"

# ПРИМЕРЫ РЕПЛИК ЧЕЛОВЕКА НЕ ДОЛЖНЫ СОВПАДАТЬ СО СТЕНДОМ: «в падел кто тут играет», «постух», «овцы/мороженое»
# стояли и здесь, и в стенде — стенд мерил, как модель помнит примеры (каталог шага 4, 24.09.2026). Запрещённые
# обороты описаны словами, без цитат: перечисление плохих фраз модель тоже копирует.
# В ПРОМПТЕ НЕТ ГОТОВЫХ ФРАЗ ДЛЯ ОТВЕТА. Пример «Фрисби в парке — отличная идея!» модель начала
# копировать: на стенде 24.09.2026 31–41 ответ из ~440 начинались на «Ф» («Фантаично!», «Фигурное катание
# на велотреке», дословное «Фрисби в парке…»), до примера — ни одного. Образцы реплик человека (что
# считать просьбой) остаются: их модель узнаёт, а не повторяет.
ПРОМПТ = """You are Kleal, a warm and smart assistant inside a social app that helps people find others to do things with, in real life or online. You talk WITH the user. Messages with role "user" are the user's; messages with role "assistant" are yours. Never speak as the user and never describe yourself as them.

THE USER (use naturally, never recite it back): __PROFILE__

HOW TO TALK. Reply in __LANGNAME__, like a friend: 1-3 short sentences, address the user as __YOU__, at most ONE question per reply. If the user asks a question, answer it first, plainly. This is a text chat typed on a phone: typos are normal — take the closest real word that fits («постух» -> «пастух») and never say you did not hear. «я …» + a description is the user talking about themselves; «ищу / хочу найти / хочу познакомиться с …» describes the person they want to meet. Time, place, format and group size are set in the app later — never ask about them. You go nowhere yourself, so never invite the user to go somewhere with you. In Russian speak about yourself in the masculine form («рад», «понял»). You have no memory of earlier conversations — never say you have seen the user before.

MOST MESSAGES ARE JUST TALK. Answer what the user said and stay on their topic, like a friend. When they talk about you (who you are, your life, what you can do), share their feelings, say something warm or romantic to you, or ask you to chat, imagine, explain, advise or teach — do it yourself, kindly and honestly: you are an AI in this app, not a person and not a partner; you may mention once in the whole conversation that the app can help them meet real people. If they ask you to just talk, talk: share a thought, a fun fact or a short story, not only questions. If they ask what you can do, say that you help find people to do things with, in real life or online. If they ask what you know about them, say you see their profile (name, age, city) and this chat. Suggest finding company only when the user is looking for something to do (they are bored or free, or named an activity they would like to do), and at most once: after you suggested it, wait for their answer and do not suggest it again unless they name a new activity. Suggest it as a short question in your own words, naming their activity.

YOUR REPLY AND YOUR CARD AGREE. The app shows the search window only when you send a card; after that the user fills in the next screens by hand, and only then does the search start. With a card, your reply is one short plain sentence in your own words that names their activity as they said it, different from your earlier replies. It does not praise or judge the plan (no «отлично», «уютно», «романтично», «всегда приятно», «great», «lovely») and says nothing about time, place or next steps. Without a card, nothing is happening yet: your reply does not say that you are looking for, finding, inviting or creating anything. A meeting is never already arranged.

WHEN TO MAKE A CARD. A card is a plan to do something together with other people. Make one as soon as the user's LAST message shows they want to do something with others — do NOT ask them to confirm first. For example: «в падел кто тут играет», «кто со мной на скалодром», «ищу компанию в кино», «хочу найти, с кем выпить кофе», «хочу на свидание», or a yes («да», «давай», «ну да, давай», «хочу») to your offer to find someone. Wanting company counts even without «ищу» or «найти», when there is an activity: «было бы с кем — пошёл бы на каток», «одной на концерт идти не хочется», «кто бы сходил со мной на квест». Chatting, questions, feelings, stories about themselves, talk about you, romance toward you — NO card. If the user only told you about an interest, you may ask whether to find someone, but make no card until they want it. When you make a card, do not end your reply with a question.

THE CARD.
- title: in __LANGNAME__, a VERB + OBJECT naming what they will do: «Выпить кофе», «Поиграть в падел», «Сходить за грибами», «Сходить на свидание». Do not write «Поговорить о X» when X is something people do. The object is never a verb and never a random word taken from the message. Name the specific activity, never generic words («интересы», «что-нибудь», «встретиться»). If the user wants a date or a romantic partner, the title is «Сходить на свидание» and the category is dating. If they named several things, name the main one or two: «Поговорить про крипту и CS».
- subject: the object alone, a noun in its dictionary form, in __LANGNAME__: «кофе», «падел», «грибы».
- role: one of play, watch, discuss, practise, attend, meet.
- chips: 1-4 interests the user named IN THIS CONVERSATION — never from the profile. Use VOCABULARY keys exactly as written. If the user named something that is not in the vocabulary («овцы», «мороженое»), use the user's own word in its dictionary form. Never moods, time, place, company or filler words.
- If the user changed their mind, the card is about the LAST choice; anything cancelled or refused never appears in the title or chips. When the user ADDS something, keep the title and add chips.
- category: exactly one of: __CATS__
- request: true
__CURRENT__
VOCABULARY: __VOCAB__

OUTPUT — exactly this shape and nothing else. First your reply to the user, then a line with ###CARD, then one JSON object:
<your reply>
###CARD
{"card": null}
or, when there is a card:
<your reply>
###CARD
{"card": {"title": "...", "subject": "...", "role": "...", "chips": ["..."], "category": "...", "request": true}}"""

СБОРЩИК = """

THE USER IS IN THE CARD BUILDER: they came here to make a card, so the rule «questions or stories — no card» does not apply here. The card on their screen changes ONLY when you send a card. If this is their first message here, send the full card. Whenever their last message names the activity or changes the plan — another activity, something added or dropped — send the full card for the plan as it is NOW: their last choice wins, and everything they did not change stays as it was. When their last message does not change the plan — a question, a time, a place, a level, gear — return {"card": null}, and the card on screen stays. If no activity has been named at all, ask ONE short question about what they want to do, and return no card. If they cancel the whole plan and name nothing instead, return {"card": null, "cancel": true}. Your reply answers what they just said; when the plan changed, say in a few words what it is now. The user picks time, place and the rest by hand on the next screens: never mention them and never tell the user what to do next."""


def _профиль_текстом(profile):
    """Профиль словами и кириллицей, а не json.dumps с кодами \\uXXXX. Интересы профиля модели не
    показываем вовсе: они подменяли сказанное в этом разговоре."""
    p = dict(profile or {})
    части = []
    for ключ, подпись in (("name", "name"), ("age", "age"), ("area", "city"), ("city", "city")):
        if p.get(ключ) not in (None, "", []):
            части.append("%s: %s" % (подпись, p[ключ]))
    языки = p.get("langs") or p.get("languages")
    if языки:
        части.append("languages: %s" % ", ".join(str(x) for x in (языки if isinstance(языки, list) else [языки])))
    return "; ".join(части) or "unknown"


# ---------------------------------------------------------------- переписка

def нормализовать(messages):
    """Один список для сторожей, модели и сита: только user/assistant со строкой. Чужие роли
    (system от клиента, пустые) выбрасываются — иначе сторож и модель видели разные переписки."""
    из = []
    for m in (messages or []):
        if not isinstance(m, dict):
            continue
        роль = str(m.get("role") or "").strip().lower()
        текст = m.get("content")
        if роль not in ("user", "assistant") or not isinstance(текст, str) or not текст.strip():
            continue
        из.append({"role": роль, "content": текст.strip()[:1200]})
    return из


def разобрать(сырое):
    """Ответ модели -> (текст, карточка или None, чисто ли). Маркер ищется терпимо: модели пишут
    «### CARD», «**###CARD**», прячут JSON в ```; без маркера хвостовой {"card"…} тоже срезается."""
    s = str(сырое or "").strip()
    части = _МАРКЕР.split(s, maxsplit=1)
    if len(части) == 2:
        ответ, хвост = части
    else:
        i = s.find('{"card"')
        ответ, хвост = (s[:i], s[i:]) if i >= 0 else (s, "")
    ответ = re.sub(r"[\s`*#_]+$", "", ответ).strip()
    карточка = None
    м = re.search(r"\{.*\}", хвост, re.S)
    if м:
        for кусок in (м.group(0), re.sub(r",\s*([}\]])", r"\1", м.group(0))):
            try:
                карточка = (json.loads(кусок) or {}).get("card")
                break
            except Exception:
                continue
    чисто = bool(ответ) and '{"' not in ответ and "###" not in ответ
    return ответ, (карточка if isinstance(карточка, dict) else None), чисто


# ---------------------------------------------------------------- сито чипов

def _плоско(s):
    """ё→е, без ударений, нижний регистр — чтобы «ещё/еще», «café/cafe» сравнивались как одно.

    «й» — отдельная буква, а не «и» с ударением: NFKD раскладывал её, и «бассейн» становился
    «бассеин», которого реестр не знает, — чип swimming считался несказанным (проверка шага 2,
    24.09.2026). Поэтому «й» прячется от разложения и возвращается."""
    s = unicodedata.normalize("NFKD", str(s or "").lower().replace("ё", "е").replace("й", "\x01"))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).replace("\x01", "й")
    # «БУКВА & БУКВА» — ОДНО СЛОВО. «хочу поиграть в d&d» распадалось на две буквы «d», короче любого слова:
    # ни чип модели «D&D», ни ключ dnd не считались сказанными — «нет чипов» трижды, окна нет, Буди
    # переспрашивал «Поиграем в D&D?» на каждое «да» (снимок владельца 06.10.2026). Склеиваем так же, как
    # пишет реестр: d&d -> dnd, R&B -> rnb (ключ rnb, подпись «R&B»).
    return re.sub(r"\b([a-z])\s*&\s*([a-z])\b", r"\1n\2", s)


def _формы(w, B):
    """Слово и его словарные формы: «овец» и «овцы» оба дают «овца»."""
    w = _плоско(w)
    из = {w}
    разбор = getattr(B, "_морф_разбор", None)
    if разбор is not None and re.search(r"[а-я]", w):
        try:
            for р in разбор.parse(w)[:2]:
                из.add(_плоско(р.normal_form))
        except Exception:
            pass
    return из


# ТРАНСЛИТ. «hochu s kem nibud vypit kofe», «kto nibud hodit na skalodrom» — человек пишет по-русски
# латиницей, модель верно ставит чип «кофе» / «скалодром», а сито не находило этих слов в сказанном и
# выбрасывало карточку целиком (noise-01, noise-10 на стенде 24.09.2026). Латинское слово получает ещё
# и кириллическую форму — только для проверки «сказано ли», в чип она не попадает.
_ЛАТ = [("shch", "щ"), ("sch", "щ"), ("zh", "ж"), ("kh", "х"), ("ch", "ч"), ("sh", "ш"), ("ts", "ц"),
        ("ya", "я"), ("ja", "я"), ("yu", "ю"), ("ju", "ю"), ("yo", "ё"), ("jo", "ё"), ("a", "а"), ("b", "б"),
        ("v", "в"), ("w", "в"), ("g", "г"), ("d", "д"), ("e", "е"), ("z", "з"), ("i", "и"), ("j", "й"), ("k", "к"),
        ("l", "л"), ("m", "м"), ("n", "н"), ("o", "о"), ("p", "п"), ("r", "р"), ("s", "с"), ("t", "т"), ("u", "у"),
        ("f", "ф"), ("h", "х"), ("c", "к"), ("y", "ы"), ("x", "кс"), ("q", "к")]


def _транслит(w):
    w = str(w or "").lower()
    if not re.fullmatch(r"[a-z]+", w):
        return ""
    out, i = [], 0
    while i < len(w):
        for лат, кир in _ЛАТ:
            if w.startswith(лат, i):
                out.append(кир)
                i += len(лат)
                break
        else:
            i += 1
    return "".join(out).replace("ё", "е")


def _транслит_текст(t):
    """Реплика латиницей по-русски -> кириллицей, по словам; знаки на месте. Нужна отрицанию и
    развороту: «hotya net, luchshe v bar» иначе не отменяло kino (проверка шага 3)."""
    return re.sub(r"[A-Za-z]+", lambda m: _транслит(m.group(0)) or m.group(0), str(t or ""))


def _латиницей(t):
    буквы = re.findall(r"[^\W\d_]", str(t or ""), re.UNICODE)
    return bool(буквы) and sum(1 for ч in буквы if "a" <= ч.lower() <= "z") >= 0.8 * len(буквы)


def _описка_ли(w, B):
    """Слово похоже на описку, только если оно русское и морфология его НЕ знает: «сушы» — да;
    «пару», «билет», «видно» — настоящие слова, и засчитывать их за «парк», «балет», «вино» нельзя
    (проверка шага 3 поймала именно это). Для латиницы проверки «настоящее ли слово» нет — не берём."""
    if not re.fullmatch(r"[а-я]{4,}", w or ""):
        return False
    разбор = getattr(B, "_морф_разбор", None)
    if разбор is None:
        return False
    try:
        return not разбор.word_is_known(w)
    except Exception:
        return False


def _похоже(а, б, B):
    """Одна описка: «сушы» — это «суши». Только от четырёх букв, с той же первой буквой и почти той
    же длиной — иначе «бар» совпал бы с чем угодно. Не same_word V1: у того «начало совпало» тоже
    считается одним словом, и «бар» стал бы «барахолкой»."""
    if len(а) < 4 or len(б) < 4 or а[0] != б[0] or abs(len(а) - len(б)) > 1:
        return False
    try:
        return B._edit_distance(а, б, 2) <= 1
    except Exception:
        return False



def _звук(w):
    """Слово «на слух» — как его пишут с ошибкой. Русское: й→и, э→е, о→а, без ъ/ь; латиница (es/en): c перед
    e/i→s, z→s, qu→k, c→k, v→b, без h; двойные буквы — одна. «кофэ»=«кофе», «басеин»=«бассейн»,
    «пагулять»=«погулять», «sine»=«cine», «tenis»=«tennis»."""
    w = _плоско(w)
    if re.search(r"[а-я]", w):
        w = w.replace("й", "и").replace("э", "е").replace("о", "а").replace("ъ", "").replace("ь", "")
    else:
        w = w.replace("ph", "f").replace("qu", "k").replace("ck", "k").replace("ll", "y")
        w = re.sub(r"c(?=[eiy])", "s", w).replace("c", "k").replace("z", "s").replace("v", "b").replace("h", "").replace("y", "i")
    return re.sub(r"(.)\1+", r"\1", w)


def _имена_ключа(ключ, B):
    """Все слова, которыми таблицы Буди и реестр называют ключ: алиасы ru/en/es, синонимы реестра, подписи."""
    if "имена_ключа" not in _КЭШ:
        карта = {}

        def доб(слово, к):
            try:
                кк = B.norm_topic(_плоско(к)) or к
            except Exception:
                кк = к
            t = _плоско(слово).strip()
            if re.fullmatch(r"[^\W\d_]{3,}", t, re.UNICODE):   # одно слово целиком
                карта.setdefault(кк, set()).add(t)
        for имя in ("TOPIC_ALIASES", "_EN_SYN", "_ES_SYN", "_CAPTION_ALIAS"):
            for слово, к in list((getattr(B, имя, {}) or {}).items()):
                доб(слово, к)
        try:
            for слово, к in list((B.taxonomy.synonyms() or {}).items()):
                доб(слово, к)
        except Exception:
            pass
        _КЭШ["имена_ключа"] = карта
    return (_КЭШ["имена_ключа"].get(ключ, set())
            | {_плоско(п).strip() for п in _подписи(ключ) if re.fullmatch(r"[^\W\d_]{3,}", _плоско(п).strip(), re.UNICODE)}
            | ({_плоско(ключ)} if re.fullmatch(r"[^\W\d_]{3,}", _плоско(ключ), re.UNICODE) else set()))


def _на_слух(ключ, формы, B):
    """Ключ сказан словом с опиской: «го в басеин» — swimming, «kiero ir al sine» — cinema, «пагулять» — walk.
    Ночная проверка 27.09.2026: модель такие карточки давала, сито не находило сказанного слова — «нет
    чипов» дважды и окна нет (6 случаев из 11 с опечатками и эмодзи). Совпадение звука — любое слово от
    4 букв; одна буква разницы — только для русских слов, которых нет в словаре («видно» — не «вино»). В
    латинице словаря нет: «tengo»≈«tango», «poder»≈«poker» — поэтому там только точный звук (sine=cine).
    Подписи и синонимы из нескольких слов не сверяются: «Table tennis» подтверждал pingpong по «tennis»."""
    звуки = {}
    for п in _имена_ключа(ключ, B):
        if len(п) >= 4:
            звуки[_звук(п)] = п
    if not звуки:
        return False
    for f in формы:
        if len(f) < 4:
            continue
        зф = _звук(f)
        if зф in звуки:
            return True
        if not _описка_ли(f, B) or len(зф) < 5:   # одна буква — только русская описка; латиница — только точный звук
            continue
        for зс in звуки:
            if зс[:1] == зф[:1] and abs(len(зс) - len(зф)) <= 1:
                try:
                    if B._edit_distance(зф, зс, 2) <= 1:
                        return True
                except Exception:
                    pass
    return False


# ЭМОДЗИ — ТОЖЕ СЛОВО. «☕️ кто со мной? 🙏», «🎾 кто завтра?», «🏀 pickup game anyone?» — модель понимала и давала
# карточку, а сито не видело сказанного: «нет чипов» дважды, окна нет (ночная проверка 27.09.2026, 0 из 5).
_ЭМОДЗИ = {"☕": "coffee", "🍵": "tea", "🍺": "beer", "🍻": "beer", "🍷": "wine", "🍸": "cocktails", "🍹": "cocktails",
          "🏀": "basketball", "⚽": "football", "🎾": "tennis", "🏐": "volleyball", "🏓": "pingpong", "🎳": "bowling",
          "🧗": "climbing", "🏃": "running", "🚴": "cycling", "🚲": "cycling", "🏊": "swimming", "🏄": "surfing",
          "⛷": "skiing", "🏂": "snowboarding", "⛸": "skating", "🎬": "cinema", "🍿": "cinema", "🎭": "theatre",
          "🎤": "karaoke", "🎸": "guitar", "🎨": "art", "📷": "photography", "📸": "photography", "🎲": "boardgames",
          "♟": "chess", "🎮": "gaming", "🧘": "yoga", "🎣": "fishing", "🍕": "pizza", "🍣": "sushi", "🍔": "burger",
          "🥾": "hiking", "⛺": "camping", "🐕": "dog", "🐶": "dog", "📚": "books", "💃": "dancing", "🕺": "dancing",
          "🏋": "gym", "🥊": "boxing", "🛹": "skateboarding", "⛳": "golf", "🎯": "darts", "🃏": "poker"}


def _эмодзи_слова(текст, B):
    """Ключи занятий по эмодзи в тексте — только те, что знает реестр."""
    out, т = set(), str(текст or "")
    for э, к in _ЭМОДЗИ.items():
        if э in т:
            try:
                кк = B.norm_topic(к) or ""
            except Exception:
                кк = ""
            if кк:
                out.add(кк)
    return out


def _эхо(ответ, said):
    """Ответ дословно повторяет человека: «Quiero tener una cita con una chica.» на «quiero tener una cita con una
    chica», «Если бы кто-то позвал меня на сплав, я бы пошёл» (ночная проверка 27.09.2026). Это брак, не ответ."""
    а = re.sub(r"[^\w ]+", "", _плоско(ответ)).strip()
    return len(а) >= 12 and any(а == re.sub(r"[^\w ]+", "", _плоско(x)).strip() for x in (said or [])[-2:])


# ОТКАЗ ПОСЛЕ СЛОВА. Отрицание V1 действует только вперёд («не хочу бегать»), а люди чаще говорят
# наоборот: «футбол смотреть не зови», «бегать я точно не буду», «в зал не пойду». На стенде шага 3
# (24.09.2026) по таким фразам открывались окна про футбол и пробежки. Здесь — назад, в пределах
# одной части фразы (до запятой, «а», «но»). «не откажусь», «не против», «не прочь» — согласие, их тут нет.
_НЕТ_НАЗАД = re.compile(
    r"(?iu)\b(?:не|ни\s+за\s+что\s+не)\s+(?:хочу|хотелось\s+бы|буду|зови|пойду|пойдём|пойдем|надо|люблю|"
    r"интересно|интересует|моё|мое|вариант|тянет|катит)\b|\bни\s+за\s+что\b|\bне\s+для\s+меня\b|"
    r"\bnot\s+(?:into|interested|for\s+me)\b|\bno\s+thanks\b|\bno\s+(?:quiero|me\s+(?:apetece|interesa|gusta))\b|"
    r"\bni\s+de\s+broma\b")
_ЧАСТИ = re.compile(r"(?iu)[,;.!?…]|\s(?:а|но|зато|but|pero)\s")
# ОТМЕНА В ТОЙ ЖЕ РЕПЛИКЕ: «хотел спросить про поход в горы... а, забей» — всё названное до «забей»
# отменено (noise-11), если после него не названо новое занятие.
_ЗАБЕЙ = re.compile(r"(?iu)\b(?:забей|проехали|отбой|неважно|не\s+важно|forget\s+it|never\s+mind|olv[ií]dalo|da\s+igual)\b")


def _отказ_назад(x):
    """Слова, отвергнутые ПОСЛЕ себя в той же части фразы, и всё названное до «забей»."""
    out = set()
    for часть in _ЧАСТИ.split(str(x or "")):
        m = _НЕТ_НАЗАД.search(часть)
        if m:
            out |= {w.lower() for w in re.findall(r"[^\W\d_]{3,}", часть[:m.start()], re.UNICODE)}
    м = _ЗАБЕЙ.search(str(x or ""))
    if м:
        до, после = str(x)[:м.start()], str(x)[м.end():]
        if not re.search(r"(?iu)\b(?:лучше|давай|хочу|instead|mejor)\b", после):
            out |= {w.lower() for w in re.findall(r"[^\W\d_]{3,}", до, re.UNICODE)}
    return out


# РАЗВОРОТ «НЕТ, ХОЧУ Y». «вообще нет, хочу посидеть на мосту и покурить сигары» — в _REVERSAL V1 такого
# нет, и крипта из прошлых реплик оставалась в карточке (снимок владельца 24.09.2026, 17:23). Реплика,
# которая НАЧИНАЕТСЯ с «нет / не то / вообще нет» и называет новый выбор («хочу», «лучше», «давай»),
# отменяет всё, что названо раньше и не повторено. «нет, хочу ещё и овец» — добавка, не отмена;
# «нет, в воскресенье» — не выбор, не отмена.
_НЕТ_В_НАЧАЛЕ = re.compile(r"(?iu)^\s*(?:(?:вообще|совсем|точно)\s+)?(?:нет|неа)\b(?!\s*,?\s*но\b)(?=\s*[,.!—–-]|\s+(?:хочу|лучше|давай))"
                           r"|^\s*не\s+(?:то|это)\s*[,.!—–-](?!\s*слово)|\bвместо\s+этого\b")
_НОВЫЙ_ВЫБОР = re.compile(r"(?iu)\b(?:хочу|хочется|лучше|давай|давайте|хотелось\s+бы)\b")
# «нет, хочу именно на комедию» (при кино) — уточнение того же занятия, не разворот.
_УТОЧНЕНИЕ = re.compile(r"(?iu)\b(?:именно|конкретно|а\s+именно|точнее)\b")
# Не новый выбор: компания, время, место свидания — «нет, хочу найти партнёра», «нет, давай в пятницу».
_НЕ_ЗАНЯТИЕ = {"партнер", "напарник", "компания", "друг", "подруга", "люди", "человек", "девушка", "парень", "собеседник",
               "команда", "раз", "время", "день", "вечер", "утро", "ночь", "неделя", "выходные", "пятница", "суббота",
               "воскресенье", "понедельник", "вторник", "среда", "четверг", "час", "минута", "сегодня", "завтра"}


def _новые_предметы(x, раньше, B):
    """Существительные реплики, которых не было раньше и которые не про компанию и время."""
    разбор = getattr(B, "_морф_разбор", None)
    if разбор is None:
        return set()
    out = set()
    for w in re.findall(r"[а-яё]{3,}", str(x or "").lower()):
        try:
            п = разбор.parse(w)[0]
        except Exception:
            continue
        н = _плоско(п.normal_form)
        if "NOUN" in п.tag and н not in _НЕ_ЗАНЯТИЕ and н not in раньше:
            out.add(н)
    return out


def _отменено_разворотом(said, B):
    """Ключи и предметы, отменённые репликой «нет, хочу Y» — только если Y действительно НОВЫЙ выбор:
    новый ключ реестра или новое существительное (не компания и не время). «нет» в ответ на вопрос
    агента, «нет, давай в пятницу», «нет, хочу именно на комедию», «нет, но…» — не разворот
    (проверка шага 3g: первая версия отменяла теннис на «нет, хочу найти партнёра»). Глаголы
    («поиграть», «поговорить») не отменяются никогда: реестр сводит их в общие ключи."""
    out = set()
    for i, x in enumerate(said):
        if i == 0 or not _НЕТ_В_НАЧАЛЕ.search(x) or not _НОВЫЙ_ВЫБОР.search(x) or _УТОЧНЕНИЕ.search(x):
            continue
        рег = getattr(B, "_ДОБАВЛЕНИЕ", None)
        if рег is not None and рег.search(x):
            continue
        ключи_было = _ключи_занятий(said[:i], B)
        ключи_стало = _ключи_занятий(said[i:], B)
        раньше = set()
        for y in said[:i]:
            for w in re.findall(r"[^\W\d_]{3,}", _плоско(y), re.UNICODE):
                раньше |= _формы(w, B)
        if not ((_ключи_занятий([x], B) - ключи_было) or _новые_предметы(x, раньше, B)):
            continue
        out |= ключи_было - ключи_стало
        стало = set()
        for y in said[i:]:
            for w in re.findall(r"[^\W\d_]{3,}", _плоско(y), re.UNICODE):
                стало |= _формы(w, B)
        # отменённые предметы прошлых реплик (существительные), не повторённые после разворота
        разбор = getattr(B, "_морф_разбор", None)
        for y in said[:i]:
            for w in re.findall(r"[а-яё]{3,}", str(y).lower()):
                try:
                    п = разбор.parse(w)[0] if разбор is not None else None
                except Exception:
                    п = None
                if п is not None and "NOUN" in п.tag and not (_формы(_плоско(w), B) & стало):
                    out |= _формы(_плоско(w), B)
    return out


_НЕТ_ПЕРЕД_ВЫБОРОМ = re.compile(r"(?iu)^\s*(?:(?:вообще|совсем|точно)\s+)?(?:нет|неа)\s*[,.!—–-]?\s*(?=(?:хочу|лучше|давай)\b)")


def _без_нет_впереди(x):
    """«вообще нет хочу покурить сигары»: начальное «нет» — отказ от прошлого, а не отрицание хвоста;
    иначе negated_terms V1 вычёркивал сами сигары (проверка шага 3g)."""
    return _НЕТ_ПЕРЕД_ВЫБОРОМ.sub("", str(x or ""))


def _явный_отказ(said, B):
    """Только ЯВНО отвергнутое: «не хочу X», «X не зови», «нет, хочу Y». Без широкого cancelled_before V1 —
    по нему проверка заголовка давала ложные отказы (проверка шага 2)."""
    out = set()
    for x in said:
        try:
            for w in B.negated_terms(_без_нет_впереди(x)):
                out.add(_плоско(w))
        except Exception:
            pass
        for w in _отказ_назад(x):
            out |= _формы(_плоско(w), B)
    out |= _отменено_разворотом(said, B)
    # Только КЛЮЧИ занятий, без общих корзин: «поиграть» -> gaming, «поговорить» -> talk не отказ.
    нельзя = set(getattr(B, "_GENERIC_TOPIC", set()) or set()) | set(getattr(B, "_NO_ACTIVITY", set()) or set())
    ключи = set()
    for w in out:
        try:
            к = B.norm_topic(w)
        except Exception:
            к = ""
        if к and к not in нельзя:
            ключи.add(к)
    return ключи


def _сказанное(said, B, lang="ru"):
    """Формы всех слов человека, кроме отменённого и отвергнутого им самим."""
    # Транслит — только в русском разговоре: в английском «tennis» -> «теннис» совпадал с русской
    # подписью «Настольный теннис», «club» -> «клуб» с clubbing (проверка шага 3).
    русский = (lang or "ru") == "ru"
    if русский:
        said = [(_транслит_текст(x) + " " + x) if _латиницей(x) else x for x in said]
    текст = " ".join(said)
    вычесть = set()
    try:
        # Отрицание — по КАЖДОЙ реплике: на склейке «не с кем играть» + «хочу в падел» оно
        # перетекало через границу реплик и вычёркивало падел (проверка шага 2, 24.09.2026).
        отказ = set()
        for x in said:
            отказ |= B.negated_terms(_без_нет_впереди(x))
            for w in _отказ_назад(x):
                отказ.add(w)
                отказ |= _формы(_плоско(w), B)
                try:
                    к = B.norm_topic(_плоско(w))
                    if к:
                        отказ.add(к)
                except Exception:
                    pass
        вычесть = {_плоско(x) for x in (отказ | B.cancelled_before(said))} | _отменено_разворотом(said, B)
    except Exception:
        pass
    формы = set()
    for w in re.findall(r"[^\W\d_]{2,}", _плоско(текст), re.UNICODE):
        if w in вычесть:
            continue
        формы |= _формы(w, B)
    формы |= _эмодзи_слова(" ".join(str(x) for x in said), B)
    return формы, вычесть


def _общее_начало(а, б):
    н = 0
    for x, y in zip(а, б):
        if x != y:
            break
        н += 1
    return н


def _ключ_из_слов(ключ, формы, B):
    """Сводится ли какое-то сказанное слово в этот ключ реестра."""
    for f in формы:
        try:
            if B.norm_topic(f) == ключ:
                return True
        except Exception:
            continue
    return False


# ---------------------------------------------------------------- смысл (bge-m3 на поде)

# ВЕКТОРЫ СМЫСЛА. Словарь не угонится за людьми («мармеладки», «сарай»), готовые списки дали 0.4–2.6%
# (22-23.09.2026). bge-m3 на поде (туннель 17078) ставит слово человека к ключу реестра по смыслу.
# Замер 24.09.2026 на 65 живых словах: верный ключ в первой десятке у 85%, но первым — у 60%, а у слов
# без ключа сходство доходит до 0.78 («овцы» -> dogs). Поэтому ключ берётся ТОЛЬКО от 0.85 — там в
# замере ошибок не было; ниже слово остаётся словом человека и пишется в журнал «[v2-слово]» —
# список «что люди говорят, а у нас нет» для решения владельца (tools/unknown_words.py).
_СМЫСЛ_ЗАМОК = {"до": 0.0}
_СМЫСЛ_ПАМЯТЬ = {}


def _смысл_вкл():
    return (os.environ.get("KLEAL_MEANING") or "0").strip() == "1"


def _поверхности(B):
    """(формы, ключи): ключи реестра, их подписи и синонимы — всё, что поиск понимает как ключ.
    Общие корзины и «не занятия» не входят: к ним прилипало бы всё подряд."""
    if "поверх" not in _КЭШ:
        рег = json.load(io.open(os.path.join(_ROOT, "shared", "interests.json"), encoding="utf-8"))
        нельзя = set(getattr(B, "_GENERIC_TOPIC", set()) or set()) | set(getattr(B, "_NO_ACTIVITY", set()) or set())
        пары = []
        for b, subs in (рег.get("tree") or {}).items():
            for s_, ws in (subs or {}).items():
                for k in ws or []:
                    if k in нельзя:
                        continue
                    пары.append((k, k))
                    for v in ((рег.get("labels") or {}).get(k) or {}).values():
                        if isinstance(v, str) and v.strip():
                            пары.append((v.strip(), k))
        for w, k in (рег.get("synonyms") or {}).items():
            if k not in нельзя:
                пары.append((w, k))
        виден, формы, ключи = set(), [], []
        for f, k in пары:
            if (f, k) not in виден:
                виден.add((f, k)); формы.append(f); ключи.append(k)
        _КЭШ["поверх"] = (формы, ключи)
    return _КЭШ["поверх"]


def _смысл_пачка(слова, B):
    """Все свои слова карточки — одним запросом: дорога до пода через туннель ~0.25-0.35 с (замер
    24.09.2026, сам расчёт на поде ~0 мс), и платить её за каждое слово отдельно незачем. Итог каждого
    слова — в памяти процесса. Сбой пода не ломает ход: минуту не спрашиваем."""
    нужны = []
    for w in слова:
        w = str(w or "").strip().lower()
        if w and w not in _СМЫСЛ_ПАМЯТЬ and w not in нужны:
            нужны.append(w)
    if not нужны or not _смысл_вкл() or time.time() < _СМЫСЛ_ЗАМОК["до"]:
        return
    формы, ключи = _поверхности(B)
    база = os.environ.get("KLEAL_MEANING_URL") or "http://127.0.0.1:17078"
    # Список форм ключей под запоминает один раз (индекс по md5), а не получает с каждым словом.
    имя = "reg-" + hashlib.md5("\n".join(формы).encode("utf-8")).hexdigest()[:16]

    def позвать(путь, тело, ждать=1.5):
        req = urllib.request.Request(база + путь, data=json.dumps(тело).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=ждать))

    def зарегистрировать():
        try:
            позвать("/index", {"name": имя, "candidates": формы}, ждать=60)
        except Exception as e:
            print("[v2] индекс смысла не зарегистрирован: %s" % str(e)[:100], flush=True)
        finally:
            _СМЫСЛ_ЗАМОК["индекс"] = False
    try:
        все = позвать("/nearest", {"index": имя, "queries": нужны, "k": 12})["hits"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Индекса нет (первый запрос или под перезапустился). Регистрация — разовый расчёт ~1600
            # векторов, 1-2 с: в фоне, а этот ход обходится без подсказки.
            if not _СМЫСЛ_ЗАМОК.get("индекс"):
                _СМЫСЛ_ЗАМОК["индекс"] = True
                threading.Thread(target=зарегистрировать, daemon=True).start()
            return
        _СМЫСЛ_ЗАМОК["до"] = time.time() + 60
        print("[v2] смысл недоступен, минуту без него: %s" % str(e)[:100], flush=True)
        return
    except Exception as e:
        _СМЫСЛ_ЗАМОК["до"] = time.time() + 60
        print("[v2] смысл недоступен, минуту без него: %s" % str(e)[:100], flush=True)
        return
    порог = float(os.environ.get("KLEAL_MEANING_MIN") or 0.85)
    if len(_СМЫСЛ_ПАМЯТЬ) > 20000:
        _СМЫСЛ_ПАМЯТЬ.clear()
    for w, hits in zip(нужны, все):
        три, виден = [], set()
        for i, sc in hits:
            к = ключи[int(i)]
            if к not in виден:
                виден.add(к); три.append((к, float(sc)))
        _СМЫСЛ_ПАМЯТЬ[w] = ((три[0][0], три[0][1]) if три and три[0][1] >= порог
                            else ("", три[0][1] if три else 0.0)) + (три[:3],)


def _смысл(слово, B):
    """-> (ключ или "", сходство, три подсказки)."""
    слово = str(слово or "").strip().lower()
    if not слово or not _смысл_вкл():
        return "", 0.0, []
    _смысл_пачка([слово], B)
    return _СМЫСЛ_ПАМЯТЬ.get(слово, ("", 0.0, []))


# МЕСТО — только если это точно место: слово из короткого списка, имя собственное с заглавной в речи
# или сырое слово сразу после «в/на» (прежнее правило). «в мафию», «на роликах», «латиноамериканские
# танцы» — занятия, и выбрасывать их нельзя (проверка шага 3 поймала обратное).
_МЕСТА = {"река", "озеро", "море", "пруд", "набережная", "парк", "сквер", "лес", "берег", "дом", "улица",
          "площадь", "центр", "район", "двор", "город", "квартира", "офис", "рассвет", "закат", "вечер", "утро"}


# Родовые слова занятия: без предмета они ничего не называют, и в составном чипе их можно опустить.
_РОДОВЫЕ_ЗАНЯТИЯ = {"сбор", "поход", "катание", "игра", "прогулка", "занятие", "поездка", "встреча", "посиделки",
                    "курс", "урок", "тренировка", "партия", "вылазка", "выезд", "сходка", "мастер-класс", "просмотр",
                    "обсуждение", "разговор", "изучение", "практика"}
# Предлоги места для своего сита: V1 place_words брал и второе слово после предлога («на даче ягоды» ->
# «ягоды» тоже место), и ягоды выпадали, стоило модели добавить второй чип (снимок владельца 25.09, 03:03).
_ПРЕДЛОГ_МЕСТА_RU = {"в", "во", "на", "у", "около", "возле", "под", "по"}
# Уровень и опыт — не занятие: «средний уровень», «новичок» становились чипами (стенд 4d).
_НЕ_ЧИП = {"уровень", "новичок", "начинающий", "опыт", "профи", "профессионал", "любитель",
          # Ночная проверка 27.09.2026: «ранг голд» -> чип «голд»/gold, «я лидер» (бачата), «soy support» (LoL),
          # «с ночёвкой» -> «ночёвка», «на одну ночь», «на крыше» -> «крыша», «busco equipo» -> «equipo».
          "голд", "gold", "плат", "plat", "platinum", "платина", "diamond", "даймонд", "silver", "bronze", "бронза",
          "ранг", "rank", "ranked", "рейтинг", "support", "саппорт", "лидер", "leader", "follower", "advanced",
          "intermediate", "beginner", "ночевка", "ночёвка", "overnight", "ночь", "крыша", "roof", "rooftop",
          "equipo", "team", "команда",
          "principiante", "principiantes", "novato", "novata", "intermedio", "avanzado", "nivel", "level",
          "evening", "evenings", "morning", "mornings", "weekend", "weekends", "tonight", "afternoon",
          "tarde", "noche", "вечер", "утро", "выходные"}
# ЛЮДИ И СВИДАНИЕ — НЕ ЧИП. «хочу пойти на свидание с девушкой» давало чип «девушка»: слово человека
# проходило сито как своё, поиск искал буквально «девушку» и не находил никого (ручной прогон
# 26.09.2026, мерка /root/nn/merka). Свидание в поиске — ТИП затеи (type=dating), а не интерес; чип у
# свидания — само занятие (прогулка, кофе, кино). Нет занятия — нет чипа, и сборщик спрашивает, как
# провести встречу. Словарные формы: ru через морфологию, en/es — как написано (плюс мн. число).
_НЕ_ЧИП_ЛЮДИ = {
    "девушка", "парень", "мужчина", "женщина", "девочка", "мальчик", "подруга", "друг", "жена", "муж",
    "невеста", "жених", "любовь", "свидание", "половинка", "знакомство", "отношение", "романтика",
    "партнер", "партнёр", "собеседник", "человек", "люди",
    "girl", "girls", "boy", "boys", "guy", "guys", "girlfriend", "boyfriend", "woman", "women", "man", "men",
    "lady", "ladies", "date", "dates", "dating", "romance", "love", "partner", "partners", "relationship",
    "wife", "husband", "someone", "people",
    "мама", "папа", "тиммейт", "teammate", "teammates", "mum", "mums", "mom", "moms", "dad", "dads", "owner", "owners", "владелец",
    "chica", "chicas", "chico", "chicos", "novia", "novias", "novio", "novios", "mujer", "mujeres",
    "hombre", "hombres", "cita", "citas", "pareja", "parejas", "amor", "alguien", "gente", "persona", "personas"}


def _места_речи(said, B):
    """Слова-места из речи человека: слово сразу после предлога места; второе — только если первое
    прилагательное («на Красной площади»). Слово, которое человек говорил и НЕ после предлога («собрать
    ягоды»), местом не считается. Латиница — как у V1 (place_words), там морфологии нет."""
    места, вне = set(), set()
    разбор = getattr(B, "_морф_разбор", None)
    for x in said or []:
        т = [m.group(0) for m in re.finditer(r"[^\W\d_]{2,}", str(x or ""), re.UNICODE)]
        for i, w in enumerate(т):
            п = _плоско(w)
            if not re.search(r"[а-я]", п) or len(п) < 3:
                continue
            пред = _плоско(т[i - 1]) if i > 0 else ""
            пред2 = _плоско(т[i - 2]) if i > 1 else ""
            if пред in _ПРЕДЛОГ_МЕСТА_RU:
                места.add(п)
                continue
            if пред2 in _ПРЕДЛОГ_МЕСТА_RU and разбор is not None:
                try:
                    if разбор.parse(пред)[0].tag.POS in ("ADJF", "ADJS", "PRTF"):
                        места.add(п)
                        continue
                except Exception:
                    pass
            вне |= _формы(п, B)
    try:
        места |= {_плоско(w) for w in B.place_words(said) if not re.search(r"[а-я]", _плоско(w))}
    except Exception:
        pass
    return {м for м in места if not (_формы(м, B) & вне)}


def _слово_человека(w, said, B):
    """Слово так, как его написал человек («ягод» -> «ягоды»), иначе как есть."""
    ф = _формы(w, B)
    for x in said or []:
        for m in re.finditer(r"[^\W\d_]{3,}", str(x or ""), re.UNICODE):
            if _формы(_плоско(m.group(0)), B) & ф:
                return _плоско(m.group(0))
    return w


def чипы(сырые, said, B, профиль=None, lang="ru", запас=None):
    """(ключи, показ, опора): чип остаётся, если это ключ словаря или слово самого человека.

    Опора — сколько чипов держится на сказанных словах; без неё карточки нет вовсе. Несказанный
    ключ выбрасывается всегда — будь он дописан моделью «по смыслу» или взят из профиля.
    """
    формы, вычесть = _сказанное(said, B, lang)
    общие = getattr(B, "_GENERIC_TOPIC", set()) or set()
    места = _места_речи(said, B)
    # Имена собственные: слово с заглавной НЕ в начале реплики («на Покровке», «в Доме музыки»).
    собств = set()
    for x in said:
        for m in re.finditer(r"(?<![.!?]\s)(?<!^)\b([А-ЯЁA-Z][а-яёa-z]{2,})", str(x)):
            собств |= _формы(_плоско(m.group(1)), B)
    длинные = [s for s in формы if _описка_ли(s, B)]

    def близко(w, лат=False):
        """Сказано ли слово — по словарной форме или с одной опиской («сушы» → «суши»). С лат=True
        латинское слово модели сверяется и в кириллице: человек писал «марио карт», модель — «Mario Kart»
        (ho-edge-07). Только для СВОИХ слов: имя ключа в транслите давало омонимы — mandarin ← «мандарины»,
        band ← «банда» (ревью 4d, третий круг)."""
        if bool(_формы(w, B) & формы) or any(_похоже(w, s, B) for s in длинные):
            return True
        if not лат or not re.fullmatch(r"[a-z]{4,}", w):
            return False                              # «net» -> «нет», «pro» -> «про» (ревью 4d)
        тр = _транслит(w)
        разбор = getattr(B, "_морф_разбор", None)
        try:
            if разбор is not None and разбор.parse(тр)[0].tag.POS in ("PREP", "CONJ", "PRCL", "INTJ", "NPRO"):
                return False
        except Exception:
            pass
        return bool(_формы(тр, B) & формы)
    стоп = set(getattr(B, "_RAW_STOP", set()) or set()) | set(getattr(B, "_NO_ACTIVITY", set()) or set())
    ключи, показ, опора, общие_взяты, места_чипы = [], [], 0, [], []
    if _смысл_вкл():
        свои = []
        for c in (сырые or [])[:6]:
            н = _плоско(str(c or "").strip())
            try:
                if н and not B.norm_topic(н):
                    свои.append(н)
            except Exception:
                pass
        _смысл_пачка(свои, B)
    for c in (сырые or [])[:6]:
        c = str(c or "").strip()
        if not c:
            continue
        низ = _плоско(c)
        к = ""
        try:
            к = B.norm_topic(низ) or ""
        except Exception:
            к = ""
        if not к:
            # СЛОВО МОДЕЛИ В ДРУГОЙ ФОРМЕ. «плаванье» при сказанном «поплавать»: реестр знает «плавание»,
            # а не «плаванье», чип уходил в «свои слова», которых в разговоре не было, — «нет чипов»
            # дважды и пустой сборщик (живая проверка 24.09.2026). Словарные формы сводятся в ключ;
            # сказан ли ключ, проверяется ниже как обычно.
            for f in sorted(_формы(низ, B)):
                try:
                    к = B.norm_topic(f) or ""
                except Exception:
                    к = ""
                if к:
                    break
        if к:
            if к in ключи or к in вычесть:
                continue
            # КЛЮЧ ТОЛЬКО СКАЗАННЫЙ. Модель дописывает «похожее» — к CS Minecraft, к играм шахматы
            # (снимки владельца 23.09.2026). Ключ остаётся, если человек его сказал: словом, которое
            # реестр сводит в этот ключ, самим ключом или его подписью на своём языке.
            слова_ключа = re.findall(r"[^\W\d_]{3,}", " ".join([_плоско(к)] + [_плоско(p) for p in _подписи(к)]), re.UNICODE)
            сказан = (_ключ_из_слов(к, формы, B) or bool(_формы(низ, B) & формы)
                      or any(_формы(w, B) & формы for w in слова_ключа)
                      or any(близко(w) for w in re.findall(r"[^\W\d_]{4,}", низ, re.UNICODE))
                      # общее начало от 5 букв: «криптоман» держит crypto через «Криптовалюты»
                      or any(_общее_начало(w, s) >= 5 for w in слова_ключа for s in формы if len(w) >= 5 and len(s) >= 5)
                      or _на_слух(к, формы, B))
            if not сказан:
                continue
            if к in общие:
                общие_взяты.append((к, сказан))
                continue
            # КЛЮЧ-МЕСТО. park и city — ключи реестра, и правило «место — не интерес» ниже их не видело:
            # «Покататься на велосипеде» [cycling, park], «Jugar a la pelota» [park, pingpong] — по 3 карточки
            # на прогон стенда 4c1 (у 4a 0–1). Такой ключ — в запас мест: чипом он станет, только если
            # другого занятия нет («погулять в парке» -> park остаётся).
            if к in _ключи_мест(B):
                if к not in места_чипы:
                    места_чипы.append(к)
                continue
            ключи.append(к)
            показ.append(к)
            опора += 1 if сказан else 0
            continue
        # Своё слово человека: каждое его слово обязано прозвучать в разговоре (по словарной форме).
        if re.search(r"\d", низ):
            continue                              # «5000 деталей», «5 на 5» — число, не интерес
        слова = [w for w in re.findall(r"[^\W\d_]{3,}", низ, re.UNICODE)]
        if not слова:
            continue
        if not all(близко(w, лат=True) for w in слова):
            # СОСТАВНОЙ ЧИП С РОДОВЫМ СЛОВОМ: «сбор ягод» при сказанном «собрать ягоды» (снимок владельца
            # 25.09.2026, 03:03 — сборщик трижды «нет чипов»). Несказанная часть — только родовое слово
            # занятия (сбор, поход, катание…), сказанная остаётся словом самого человека: «ягоды». Если
            # несказанное — само занятие («ремонт квартиры» при «квартиры»), чип не проходит, как раньше.
            свои_сл = [w for w in слова if близко(w, лат=True)]
            чужие = [w for w in слова if not близко(w, лат=True)]
            if not свои_сл or not all(_формы(w, B) & _РОДОВЫЕ_ЗАНЯТИЯ for w in чужие):
                continue
            c = " ".join(_слово_человека(w, said, B) for w in свои_сл)
            низ, слова = _плоско(c), свои_сл
        if низ in общие or низ in стоп or c in показ or any(_формы(w, B) & _НЕ_ЧИП for w in слова):
            continue
        if any(_формы(w, B) & _НЕ_ЧИП_ЛЮДИ for w in слова):
            print("[v2-люди] %s — не чип" % низ, flush=True)
            continue
        try:
            if B._is_verbish(низ) or not B.subject_shaped(низ):
                continue
        except Exception:
            pass
        # МЕСТО — НЕ ИНТЕРЕС. «на реке», «в доме музыки», «на покровке» — модель ставила «река», «дом
        # музыки», «Покровка» чипом (стенд 24.09.2026). Прежняя проверка сравнивала сырое слово
        # («реке») со словарной формой чипа («река») и не срабатывала. Теперь по формам, но место
        # выбрасывается, только если рядом есть настоящий чип: одно-единственное слово после «в/на»
        # бывает и самим занятием («хочу на бурбулямбу»).
        первое = _формы(слова[0], B)
        if низ in места or (первое & _МЕСТА) or (первое & собств):
            места_чипы.append(c)
            continue
        # Своё слово без ключа — к ключу по смыслу, только уверенно (от 0.85, см. _смысл). Ниже — слово
        # человека остаётся как есть и уходит в журнал непонятого.
        к_смысл, сх, три = _смысл(низ, B)
        if к_смысл and к_смысл not in ключи and к_смысл not in вычесть and к_смысл not in общие:
            print("[v2-смысл] %s -> %s %.2f" % (низ, к_смысл, сх), flush=True)
            ключи.append(к_смысл)
            показ.append(к_смысл)
            опора += 1
            continue
        if три:
            print("[v2-слово] %s" % json.dumps({"w": низ, "lang": lang, "top": [[к, round(v, 3)] for к, v in три]},
                                               ensure_ascii=False), flush=True)
        # Слово модели оставляем как есть: ей велено давать словарную форму, а повторная правка
        # морфологией ломает двусмысленные слова — «овцы» превращалось в «овца».
        показ.append(c)
        опора += 1
    if запас is not None:
        # Запасные пути решает вызывающий: сперва предмет карточки, потом место, потом корзина.
        запас["места"] = места_чипы[:4]
        запас["общие"] = [к for к, _ in общие_взяты[:1]]
        return ключи[:4], показ[:4], опора
    if not показ:
        for c in места_чипы[:4]:
            показ.append(c)
            опора += 1
    # Общая корзина остаётся, только если ничего конкретнее нет (правило V1).
    if not показ:
        for к, сказан in общие_взяты[:1]:
            ключи.append(к)
            показ.append(к)
            опора += 1 if сказан else 0
    return ключи[:4], показ[:4], опора


# ---------------------------------------------------------------- карточка -> затея

def _описание(title, lang):
    t = str(title or "").strip()
    if not t:
        return ""
    низ = t[:1].lower() + t[1:]
    return {"ru": "Найти, с кем %s." % низ, "en": "Find someone to %s." % низ,
            "es": "Encontrar con quién %s." % низ}.get(lang, "Find someone to %s." % низ)


def _к_агенту(said, B):
    """Личное и романтическое к самому агенту — в двух последних репликах человека. Берётся только
    личная часть сторожа V1: общий _ABOUT_BUDDY ложно срабатывал на «ты мне найди кого-нибудь»."""
    шаблон = getattr(B, "_К_АГЕНТУ", "")
    if not шаблон:
        return False
    # «ТЫ МНЕ» — НЕ ПРИЗНАНИЕ. В _К_АГЕНТУ V1 оно стоит в общем виде, и «ты мне найди кого-нибудь
    # на теннис» (в том числе репликой раньше: «ты мне найди кого-нибудь» / «на теннис») браковало
    # карточку как роман с агентом. Для V2 оно заменено на явное «ты мне нравишься / дорог».
    # Исключать реплику «по наличию занятия» нельзя: «люблю тебя, пошли в кино» — это признание
    # (проверка шага 2, 24.09.2026).
    шаблон = шаблон.rstrip("|").replace("|мне)", ")") + r"|\bты\s+мне\s+(?:нравишься|дорог\w*|симпатичн\w*)\b"
    try:
        рег = re.compile(шаблон, re.I | re.U)
    except Exception:
        return False
    return any(рег.search(x) for x in said[-2:])


def _ключи_мест(B):
    """Ключи реестра, в которые сводятся слова-места (парк, река…): местом чип не делаем."""
    if "места_к" not in _КЭШ:
        из = set()
        for m in _МЕСТА:
            try:
                к = B.norm_topic(m) or ""
            except Exception:
                к = ""
            if к:
                из.add(к)
        _КЭШ["места_к"] = из
    return _КЭШ["места_к"]


def _глагол_тег(w, B):
    """Русское слово — глагол или инфинитив по морфологии (для латиницы — нет)."""
    разбор = getattr(B, "_морф_разбор", None)
    if разбор is None or not re.search(r"[а-я]", w):
        return False
    try:
        return bool({"INFN", "VERB"} & set(str(разбор.parse(w)[0].tag).replace(" ", ",").split(",")))
    except Exception:
        return False


def _глагол_ли(слово, lang, B):
    """Заголовок из одного слова — глагол? ru — морфология (инфинитив); es — окончание -ar/-er/-ir;
    en — не существительное из реестра (Run, Swim, Dance)."""
    w = str(слово or "").strip().lower()
    if not w:
        return False
    if lang == "es":
        return bool(re.fullmatch(r"[a-záéíóúñ]+(?:ar|er|ir)(?:se)?", w))
    if lang in ("de", "fr", "it", "pt"):               # инфинитив по окончанию, как у испанского
        return bool(re.fullmatch({"de": r"[a-zäöüß]+(?:en|ern|eln)", "fr": r"[a-zàâçéèêëîïôûùü]+(?:er|ir|re)",
                                  "it": r"[a-zàèéìòù]+(?:are|ere|ire)(?:si)?",
                                  "pt": r"[a-záâãàçéêíóôõú]+(?:ar|er|ir)(?:-se)?"}[lang], w))
    if lang == "en":
        try:
            return not B.norm_topic(w) and w.isalpha()
        except Exception:
            return False
    разбор = getattr(B, "_морф_разбор", None)
    if разбор is None:
        return w.endswith(("ть", "ться", "ти"))
    try:
        return "INFN" in str(разбор.parse(w)[0].tag)
    except Exception:
        return False


# ---------------------------------------------------------------- заголовок: канон занятия

# КРИВЫЕ ГЛАГОЛЫ. Разметка 523 заголовков стенда двумя судьями (24.09.2026): плохой каждый пятый показ
# русского заголовка — «Поплыть на байдарках», «Выпить кальян», «Покататься на скалодроме», «Посмотреть
# квиз», «Сходить на кино», «Поплавать утрам», «Поскаладь», «Сплав на байдарках». Модель называет занятие
# глаголом, который существует, но к предмету не подходит, — морфологией это не поймать. Держит таблица
# shared/activity_titles.json: на каждый ключ реестра канон «глагол + предмет» и допустимые глаголы на
# трёх языках (собрана и перепроверена агентами-носителями). Нет файла — правка ничего не делает.
def _таблица_занятий():
    if "занятия" not in _КЭШ:
        try:
            рег = json.load(io.open(os.path.join(_ROOT, "shared", "activity_titles.json"), encoding="utf-8"))
            _КЭШ["занятия"] = рег.get("keys", рег) if isinstance(рег, dict) else {}
        except Exception:
            _КЭШ["занятия"] = {}
    return _КЭШ["занятия"]


def _канон(ключ, lang):
    строка = (_таблица_занятий().get(ключ) or {}).get(lang) or {}
    return str(строка.get("title") or "").strip()


# ВРЕМЯ В ЗАГОЛОВКЕ уходит в поле времени: «Поплавать утрам», «Зарубиться вечерами» (60 показов на
# разметке). Срезается только ХВОСТ, целиком («ранним утром», «tomorrow morning», «en la tarde»), и только
# если остаток не кончается служебным словом: обрубки «Побегать ранним», «Watch Edge of» хуже исходника
# (ревью 4d). Английский и испанский — только строчные слова: «Edge of Tomorrow» — название. Место-имя
# («по Красной площади», «по Гарри Поттеру») не трогаем: падеж ломался, а тема терялась.
_ВРЕМЯ_ХВОСТ = {
    "ru": re.compile(r"(?iu)\s+(?:(?:(?:ранн|поздн|летн|зимн|осенн|весенн|субботн|воскресн|пятничн|тёпл|тепл|"
                     r"холодн|свободн|следующ|будн)\w*\s+|(?:этим|этой|тем|той|одним|одной|каждым|каждой)\s+)?"
                     r"(?:утром|вечером|вечерком|днём|днем|ночью)|по\s+(?:утрам|вечерам|выходным|будням|субботам|"
                     r"воскресеньям|пятницам)|утрам|вечерам|вечерами|завтра|сегодня|послезавтра|"
                     r"на\s+(?:выходных|выхах|рассвете|закате|(?:этой\s+)?неделе)|"
                     r"в\s+(?:понедельник|вторник|среду|четверг|пятницу|субботу|воскресенье|выходные)|где-нибудь|где-то)$"),
    "en": re.compile(r"\s+(?:tonight|today|(?:the\s+day\s+after\s+)?tomorrow(?:\s+(?:morning|evening|night|afternoon))?|"
                     r"this\s+(?:weekend|week|evening|morning|afternoon)|(?:on|at)\s+the\s+weekend|"
                     r"in\s+the\s+(?:mornings?|evenings?|afternoons?)|at\s+(?:sunrise|sunset|night)|"
                     r"on\s+(?i:(?:mon|tues|wednes|thurs|fri|satur|sun)days?)(?:\s+(?:mornings?|evenings?|nights?|afternoons?))?|"
                     r"every\s+(?:morning|evening|day|week|weekend)|somewhere)$"),
    "es": re.compile(r"\s+(?:esta\s+(?:noche|tarde|semana)|hoy|este\s+fin\s+de\s+semana|el\s+fin\s+de\s+semana|"
                     r"por\s+la\s+(?:mañana|tarde|noche)|al\s+(?:amanecer|atardecer)|"
                     r"(?:pasado\s+)?mañana(?:\s+por\s+la\s+(?:mañana|tarde|noche))?|"
                     r"(?:el|los)\s+(?:lunes|martes|miércoles|jueves|viernes|sábados?|domingos?)(?:\s+por\s+la\s+(?:mañana|tarde|noche))?|"
                     r"en\s+algún\s+sitio)$"),
}
_СЛУЖЕБНЫЕ = {
    "ru": {"в", "во", "на", "по", "за", "под", "с", "со", "у", "к", "ко", "и", "или", "из", "от", "до", "для", "про", "о", "об",
           "перед", "над", "вдоль", "после", "между", "через", "около", "возле", "без", "вместе"},
    "en": {"a", "an", "the", "to", "in", "on", "at", "for", "with", "of", "and", "or", "some", "together"},
    "es": {"a", "al", "el", "la", "los", "las", "un", "una", "de", "del", "en", "con", "por", "para", "y", "o", "juntos", "juntas"},
}


def _без_времени(title, lang):
    t = str(title or "").strip()
    рег = _ВРЕМЯ_ХВОСТ.get(lang)
    if not рег:
        return t
    new = t
    for _ in range(3):
        m = рег.search(new)
        if not m:
            break
        остаток = new[:m.start()].strip()
        хвост = _плоско(остаток.split()[-1]) if остаток.split() else ""
        if not остаток or хвост in _СЛУЖЕБНЫЕ.get(lang, set()):
            break
        new = остаток
    return new


_ПРЕДЛОГИ_RU = ("в", "во", "на", "за", "по")
# Глаголы, которые подходят к любому занятию: разговор и учёба («Поговорить про йогу», «Научиться готовить
# пасту»), движение («Поехать в поход на Алтай»), своё дело («Приготовить суши дома», «Выступить на
# концерте», «Поболеть за Зенит»), еда при месте («Поужинать в кафе»). Их замена каноном меняла смысл
# (разметка и ревью 4d).
_ВСЕГДА_МОЖНО = {
    "ru": {"поговорить", "обсудить", "пообщаться", "поболтать", "посетить", "научиться", "учиться", "поучиться",
           "попробовать", "потренироваться", "позаниматься", "заниматься", "помочь", "поучаствовать", "подготовиться",
           "сходить", "пойти", "поехать", "съездить", "выбраться", "сгонять", "заглянуть", "зайти", "отправиться",
           "приготовить", "сварить", "испечь", "написать", "устроить", "организовать", "провести", "сыграть",
           "выступить", "поболеть", "послушать", "поужинать", "пообедать", "позавтракать", "перекусить", "станцевать",
           "посидеть", "прогуляться", "поработать"},
    "en": {"talk", "discuss", "chat", "learn", "try", "visit", "attend", "practice", "practise", "join", "help", "train",
           "listen", "watch", "go", "cook", "make", "host", "organise", "organize", "play", "perform"},
    "es": {"hablar", "charlar", "conversar", "aprender", "probar", "visitar", "asistir", "practicar", "ayudar",
           "participar", "entrenar", "escuchar", "ir", "cocinar", "preparar", "organizar", "tocar", "jugar"},
}
_НЕ_ПРЕДМЕТ_POS = {"ADJF", "ADJS", "PRTF", "PRTS", "NUMR", "ADVB", "PRCL", "CONJ", "PREP", "NPRO", "INTJ"}


def _ключ_слова(w, B):
    """Ключ реестра для слова: само слово или его словарные формы."""
    for f in [w] + sorted(_формы(w, B) - {w}):
        try:
            к = B.norm_topic(f) or ""
        except Exception:
            к = ""
        if к:
            return к
    return ""


def _ключ_пары(a, b, B):
    """Ключ пары слов — только настоящей: norm_topic сравнивает по НАЧАЛУ строки, и «концерт в», «бассейн
    сауну» сводились в ключ первого слова, глотая соседнее (ревью 4d). Пара — ключ, только если она даёт
    ДРУГОЙ ключ, чем первое слово само по себе: «настольный теннис» — pingpong, а «настольный» — нет."""
    try:
        к = B.norm_topic(a + " " + b) or ""
    except Exception:
        к = ""
    return к if к and к != _ключ_слова(a, B) else ""


def _предмет_заголовка(t, lang, B):
    """(ключ, слово, индекс последнего слова предмета) — ПРЕДМЕТ ГЛАГОЛА: первое содержательное слово
    после глагола, мимо предлогов, артиклей и прилагательных; настоящая пара слов — раньше одного.
    Ключ — по предмету, а не по первому слову с ключом: «Посмотреть матч в баре» — про матч (ревью 4d)."""
    слова = [re.sub(r"[^\w-]", "", _плоско(x)) for x in str(t or "").split()]
    разбор = getattr(B, "_морф_разбор", None)
    for i in range(1, len(слова)):
        w = слова[i]
        if not w or w in _СЛУЖЕБНЫЕ.get(lang, set()):
            continue
        if i + 1 < len(слова) and слова[i + 1] and слова[i + 1] not in _СЛУЖЕБНЫЕ.get(lang, set()):
            к2 = _ключ_пары(w, слова[i + 1], B)
            if к2:
                return к2, w + " " + слова[i + 1], i + 1
        if lang == "ru" and разбор is not None and re.search(r"[а-я]", w):
            try:
                pos = разбор.parse(w)[0].tag.POS
            except Exception:
                pos = None
            if pos in _НЕ_ПРЕДМЕТ_POS or pos == "INFN":
                continue
        return _ключ_слова(w, B), w, i
    return "", "", -1


# ПРЕДЛОГ ПРИ ГЛАГОЛЕ ДВИЖЕНИЯ — явный короткий список, а не таблица: по таблице «Сходить на пинг-понг»
# становилось «в пинг-понг», «на пляжный волейбол» — «в пляжный» (ревью 4d). Здесь только заведения, куда
# ходят «в», и события, куда ходят «на».
_ПРЕДЛОГ_ВЕРНЫЙ = {"кино": "в", "кинотеатр": "в", "боулинг": "в", "театр": "в", "музей": "в",
                   "клуб": "в", "бар": "в", "кафе": "в", "ресторан": "в", "бассейн": "в", "зоопарк": "в", "цирк": "в",
                   "баню": "в", "сауну": "в", "кальянную": "в", "антикафе": "в",
                   "концерт": "на", "выставку": "на", "квиз": "на", "йогу": "на", "рыбалку": "на", "каток": "на",
                   "скалодром": "на", "экскурсию": "на", "фестиваль": "на", "лекцию": "на", "стендап": "на",
                   "спектакль": "на", "мастер-класс": "на", "пробежку": "на", "тренировку": "на", "матч": "на"}
_ДВИЖЕНИЕ_RU = {"сходить", "пойти", "съездить", "поехать", "выбраться", "сгонять", "заглянуть", "зайти", "отправиться"}
_ЗАВЕДЕНИЯ = {"cafe", "coffee", "bar", "pub", "restaurant", "club", "park", "city", "beach"}


def _хвост_без_повтора(хвост, канон, lang, B):
    """Хвост после предмета без слов, которые повторяют ПРЕДМЕТ канона: «на байдарках по Вуоксе» при
    каноне «Сплавиться на байдарках» -> «по Вуоксе»; «по реке на байдарках» -> «по реке». Служебные слова
    перед первым своим словом сохраняются все («en la playa», «и в бар»), глагол повтором не считается
    («и сходить в бар» остаётся) — ревью 4d, третий круг."""
    формы = set().union(*[_формы(_плоско(w), B) for w in канон.split()[1:]]) if канон else set()
    сл = хвост.split()
    служ = _СЛУЖЕБНЫЕ.get(lang, set())

    def повтор(w):
        п = _плоско(w)
        return п not in служ and not _глагол_тег(п, B) and bool(_формы(п, B) & формы)
    i = 0
    while i < len(сл) and (_плоско(сл[i]) in служ or повтор(сл[i])):
        if повтор(сл[i]):
            i += 1
            while i < len(сл) and повтор(сл[i]):
                i += 1
            continue
        k = i
        while k < len(сл) and _плоско(сл[k]) in служ:
            k += 1
        if k < len(сл) and not повтор(сл[k]):
            break
        i = k
    сл = сл[i:]
    # повтор предмета в конце: «… по реке на байдарках»
    while сл and повтор(сл[-1]):
        сл.pop()
        while сл and _плоско(сл[-1]) in служ:
            сл.pop()
    return " ".join(сл)


def _поправь_заголовок(title, ключи, lang, B):
    """(заголовок, причина правки или ""). Ключ — предмет глагола (или само первое слово, если это
    существительное-занятие); он обязан быть ключом карточки, иначе заголовок про другое и не трогается.
    ru: сломанный глагол или глагол не из допустимых для ключа -> канон + свой хвост; не тот предлог после
    глагола движения -> только предлог. es: первое слово не глагол -> канон. en: без правки."""
    таб = _таблица_занятий()
    t = str(title or "").strip()
    if not t or not таб or not ключи:
        return t, ""
    общие = set(getattr(B, "_GENERIC_TOPIC", set()) or set())
    слова = t.split()
    первое = _плоско(слова[0])
    разбор = getattr(B, "_морф_разбор", None)

    def годный(к):
        return bool(к) and к in ключи and к in таб and к not in общие

    def строка_для(к):
        return (таб.get(к) or {}).get(lang) or {}

    # ЗАНЯТИЕ ПЕРВЫМ СЛОВОМ: «Сапсерфинг по реке», «Сплав на байдарках», «Fútbol en la playa». Только
    # существительное: прилагательное «Велосипедная прогулка» ключ давало, а заголовок ломался (ревью 4d).
    первое_сущ = False
    if lang == "ru" and первое not in _ВСЕГДА_МОЖНО["ru"] and разбор is not None:
        try:
            первое_сущ = разбор.parse(первое)[0].tag.POS == "NOUN"
        except Exception:
            первое_сущ = False
    elif lang == "es" and not re.fullmatch(r"[a-záéíóúñ]*(?:ar|er|ir)(?:se|nos|la|lo)?", первое):
        первое_сущ = True
    if первое_сущ:
        к1 = _ключ_пары(первое, _плоско(слова[1]), B) if len(слова) > 1 else ""
        idx1 = 1 if к1 else 0
        к1 = к1 or _ключ_слова(первое, B)
        if not годный(к1):
            return t, ""
        канон = str(строка_для(к1).get("title") or "").strip()
        if not канон:
            return t, ""
        остаток = слова[idx1 + 1:]
        if остаток and _плоско(остаток[0]) in ("и", "или", "y", "o", "and", "or", "e"):
            return t, ""                      # «Кофе и прогулка»: два занятия — не наш случай
        if остаток and _плоско(остаток[0]) not in _СЛУЖЕБНЫЕ.get(lang, set()):
            остаток = []                      # «Cena italiana»: остаток именной группы к глаголу не клеится
        хвост = _хвост_без_повтора(" ".join(остаток), канон, lang, B)
        return (канон + " " + хвост).strip(), "не глагол «%s»" % первое
    if lang != "ru":
        # en/es: по разметке сверка со списком глаголов портила больше хороших заголовков, чем чинила
        # плохих (en 19 против 27, es 13 против 28) — там её нет.
        return t, ""
    кз, _, idx = _предмет_заголовка(t, lang, B)
    if кз and not годный(кз):
        return t, ""
    строка = строка_для(кз) if кз else {}
    глаголы = {_плоско(v) for v in (строка.get("verbs") or []) if str(v).strip()}
    свои = глаголы | _ВСЕГДА_МОЖНО["ru"]
    сломан = False
    if первое not in свои and разбор is not None:
        try:
            р0 = разбор.parse(первое)[0]
            # Сломан — только незнакомое слово или знакомое не-слово-действие; «Совместно лепить из глины»
            # (наречие + инфинитив) — не сломан, и канон тут не нужен (ревью 4d, третий круг).
            сломан = not разбор.word_is_known(первое) or р0.tag.POS not in ("INFN", "VERB", "ADVB", "PRCL", "CONJ", "ADJF", "ADJS")
            if р0.tag.POS in ("ADVB", "PRCL", "CONJ", "ADJF", "ADJS", "VERB"):
                return t, ""
        except Exception:
            сломан = False
    if not кз:
        остаток = [w for w in слова[1:] if _плоско(w) not in _СЛУЖЕБНЫЕ["ru"]]
        if сломан and not остаток:
            # «Поскалиться вместе»: заголовок — одно сломанное слово; ключ из него же, а нет — первый чип.
            к = _ключ_слова(первое, B)
            к = к if годный(к) else next((x for x in ключи if годный(x)), "")
            канон = str(строка_для(к).get("title") or "").strip() if к else ""
            if канон:
                return канон, "не глагол «%s»" % первое
        return t, ""
    канон = str(строка.get("title") or "").strip()
    if not канон or not глаголы:
        return t, ""
    # Корзина («food»: «Сходить поесть») стирает названное блюдо: «Выпить шашлык» -> «Сходить поесть».
    if re.search(r"(?iu)корзин|общ(?:ая|ий|ее)\s", str((таб.get(кз) or {}).get("note") or "")):
        return t, ""
    # Заведение после предлога при непереходном глаголе: «Почитать в кафе», «Потанцевать в баре» — место,
    # а не предмет; канон заведения («Выпить кофе», «Сходить в бар») тут меняет занятие.
    if кз in _ЗАВЕДЕНИЯ and idx >= 2 and _плоско(слова[idx - 1]) in ("в", "во", "на") and первое not in свои:
        return t, ""
    хвост = _хвост_без_повтора(" ".join(слова[idx + 1:]), канон, lang, B) if idx >= 0 else ""
    с_хвостом = (канон + " " + хвост).strip()
    if сломан:
        return с_хвостом, "не глагол «%s»" % первое
    if первое not in свои:
        return с_хвостом, "глагол «%s» не к %s" % (первое, кз)
    # «во» только прямо перед ПРЕДМЕТОМ глагола: «Поиграть во футбол» -> «в футбол»; «во дворе» — не предмет.
    if idx >= 2 and _плоско(слова[idx - 1]) == "во" and not re.match(r"[вф][^аеёиоуыэюя]", _плоско(слова[idx])):
        слова[idx - 1] = "в"
        return " ".join(слова), "предлог «в»"
    if первое in _ДВИЖЕНИЕ_RU:
        for i in range(1, len(слова) - 1):
            п, f = _плоско(слова[i]), _плоско(слова[i + 1])
            верный = _ПРЕДЛОГ_ВЕРНЫЙ.get(f)
            if п in ("в", "во", "на") and верный and п != верный and not (п == "во" and верный == "в"):
                слова[i] = верный
                return " ".join(слова), "предлог «%s»" % верный
    return t, ""


# Предложение агента найти компанию: «Хочешь найти, с кем поговорить про крипту?». Старый _OFFERED_MEET ждёт
# «с кем-то / с кем-нибудь» и такую фразу V2 не узнавал.
_НАЙТИ_С_КЕМ = re.compile(r"(?iu)\b(?:найти|найду|поискать|поищу|подобрать|подберу|find|look\s+for|buscar|busco|encontrar|"
                         r"finden?|suchen?|trouver?|chercher?|trovare|trovi|cercare|cerchi|encontre|procurar|achar)\b"
                         r"[^.!?\n]{0,40}?\b(?:с\s+кем|кого|someone|somebody|people|alguien|con\s+qui[eé]n|gente|"
                         r"jemand\w*|leute|quelqu['’]un|des\s+gens|qualcuno|persone|algu[eé]m|pessoas)\b"
                         # немецкий порядок слов: «Soll ich jemanden finden, mit dem…»
                         r"|\bjemand\w*\s+(?:\w+\s+){0,3}?(?:finden|suchen)\b")


def _принятое_предложение(msgs, B):
    """Реплики агента, на которые человек сейчас соглашается, если среди них есть предложение найти компанию.

    Идём назад от последнего «да»: реплики агента берём, прежние «да» человека пропускаем, на первой его
    содержательной реплике останавливаемся. Так «да» на «Круто, что тебе нравятся макбуки и Xbox!» всё ещё
    отвечает предложению двумя репликами выше («…хочешь найти кого-то, с кем поиграть или поговорить про
    технику?» — «ну наверное да»): раньше смотрели только последнюю реплику агента, предложение терялось, и
    на второе «да» Буди спрашивал «Чем хочется заняться?» (снимок владельца 11.10.2026, 13:34). -> [тексты]"""
    try:
        if not msgs or msgs[-1]["role"] != "user" or not B._is_affirmation(msgs[-1]["content"]):
            return []
        тексты, звал = [], False
        for m in reversed(msgs[:-1]):
            т = str(m.get("content") or "")
            if m["role"] == "user":
                if B._is_affirmation(т):
                    continue
                break
            тексты.append(т)
            if B._OFFERED_MEET.search(т) or _НАЙТИ_С_КЕМ.search(т):
                звал = True
            if len(тексты) >= 4:
                break
        return list(reversed(тексты)) if звал else []
    except Exception:
        return []


def _затея(карточка, msgs, profile, signals, lang, B):
    """Проверка карточки модели и сборка затеи в том же виде, что у V1, для телефона и поиска."""
    if not isinstance(карточка, dict) or карточка.get("request") is not True:
        return None, "нет заявки"
    said = [m["content"] for m in msgs if m["role"] == "user"]
    if _к_агенту(said, B):
        return None, "обращение к агенту"
    # СОГЛАСИЕ НА ПРЕДЛОЖЕНИЕ БУДИ. «да хочу» на «Хочешь найти, с кем поговорить про крипту?» — занятие назвал
    # агент, человек согласился. Сито засчитывало только слова человека и выкидывало crypto: сборщик — «нет
    # чипов» дважды, потом карточка с одним словом «торговля» (снимок владельца 30.09.2026, 19:50; приложение
    # к тому же отдаёт сборщику лишь хвост разговора). Слова принятого предложения — тоже сказанное.
    # С 11.10.2026 — вся реплика с предложением и реплики агента между повторными «да»: в них агент называет
    # занятие правильно («макбуки и Xbox» при «мак буки и xboz» у человека), человек с этим согласился.
    принято = _принятое_предложение(msgs, B)
    сито = (said[:-1] + принято + said[-1:]) if (said and принято) else said
    title = _без_времени(str(карточка.get("title") or "").strip(), lang)
    # ОДНО СЛОВО В ЗАГОЛОВКЕ. Глагол («Побегать», «Поплавать») — законная затея: к нему «вместе»
    # (снимок владельца 24.09.2026, 18:55: «Хочу побегать» — карточку «Побегать» отбраковывало дважды,
    # и сборщик оставался пустым). Существительное («Скалодром») — имя собирает V1 (build_intent).
    if len(title.split()) == 1 and _глагол_ли(title, lang, B):
        title = title + {"ru": " вместе", "en": " together", "es": " juntos"}.get(lang, " вместе")
    имя_v1 = len(title.split()) < 2
    запас = {}
    # ЗАГОЛОВОК ПРО ЯВНО ОТВЕРГНУТОЕ. «Обсудить крипту» после «вообще нет, хочу покурить сигары» и
    # «не хочу крипту» (снимок владельца 24.09.2026, 17:23). Сверяются предмет и слова заголовка по
    # КЛЮЧУ реестра и только с явными отказами — не с широким cancelled_before (ложные срабатывания).
    отказ = _явный_отказ(said, B)
    разбор = getattr(B, "_морф_разбор", None)
    for w in re.findall(r"[^\W\d_]{3,}", _плоско(str(карточка.get("subject") or "") + " " + title), re.UNICODE):
        # Глагол заголовка не сверяем: «Поиграть в теннис» после «нет, лучше в теннис» законна.
        try:
            if разбор is not None and re.search(r"[а-я]", w) and ({"INFN", "VERB"} & set(str(разбор.parse(w)[0].tag).replace(" ", ",").split(","))):
                continue
        except Exception:
            pass
        try:
            к = B.norm_topic(w) or ""
        except Exception:
            к = ""
        if к and к in отказ:
            return None, "заголовок про отменённое: «%s»" % w
    ключи, показ, опора = чипы(карточка.get("chips"), сито, B, profile, lang=lang, запас=запас)
    if not показ and str(карточка.get("subject") or "").strip():
        # ЧИПОВ НЕТ — ПРЕДМЕТ ЕСТЬ. На «бегать не хочу, а вот на кофе с радостью» модель дважды слала
        # «Выпить кофе» с пустыми чипами (own-08, стенд 24.09.2026), и сборщик оставался пустым.
        # Предмет её же карточки проходит то же сито: несказанное не пройдёт и так. Предмет идёт
        # РАНЬШЕ места: «дом музыки» не должен побеждать «джаз».
        ключи, показ, опора = чипы([карточка.get("subject")], сито, B, profile, lang=lang, запас={})
    if not показ and title:
        # ЗАГОЛОВОК — СЛОВА ЧЕЛОВЕКА, ЧИПЫ — НЕТ. «хочу погулять» -> «Погулять» с чипом «гулянка»: чип
        # модели не сказан, а само занятие человек назвал (живая проверка 24.09.2026, 5 из 5 без карточки).
        # Ключи — из его же реплики и без отвергнутого, и только если ВЕСЬ заголовок — его слова: при
        # «выпить чаю» заголовок модели «Выпить кофе» не должен получить чип «чай».
        текст = _формы_текста(_реплика_занятия(said, B), B)
        слова = [w for w in re.findall(r"[^\W\d_]{3,}", _плоско(title), re.UNICODE) if w not in ("вместе", "together", "juntos")]
        if слова and all(_формы(w, B) & текст for w in слова):
            свои = _ключи_человека(said, B)
            if свои:
                ключи, показ, опора = чипы(sorted(свои), сито, B, profile, lang=lang, запас={})
    if not показ and запас.get("места"):
        показ, опора = list(запас["места"]), len(запас["места"])
    if not показ and запас.get("общие"):
        ключи, показ, опора = list(запас["общие"]), list(запас["общие"]), 1
    # СВИДАНИЕ БЕЗ ЗАНЯТИЯ. Человек (девушка, парень) — не чип (_НЕ_ЧИП_ЛЮДИ), свидание в поиске — тип
    # затеи, а не интерес. Если занятие встречи не названо, чипов нет, но просьба есть: в чате окно
    # выезжает с одним заголовком, а сборщик такую карточку готовой не считает и спрашивает, как
    # провести встречу (ход(), «свидание без занятия»). Поиску нужен чип-занятие: без него он не
    # находит никого даже в режиме свиданий (проба 26.09.2026).
    свидание_без_занятия = (not показ and str(карточка.get("category") or "").strip().lower() == "dating")
    if not показ and not свидание_без_занятия:
        return None, "нет чипов"
    # НЕПОНЯТНОЕ СЛОВО. «заркибола» — модель собрала «Поиграть в заркибола» и открыла поиск (noise-02,
    # стенд шага 3). Если ключей нет, а каждое своё слово — русское и морфология его не знает, это не
    # занятие, а загадка: карточки нет, переспрос просит спросить человека, что это.
    # Только если вся последняя реплика — это слово: «посидеть со мной с макбуком» — не загадка, а
    # бренд, которого не знает морфология (снимок владельца 24.09.2026, 16:47: сторож срабатывал
    # дважды, и карточки не было вовсе).
    реплика = [w for w in re.findall(r"[а-я]{3,}", _плоско(said[-1] if said else ""))]
    if (показ and not ключи and len(реплика) <= 2 and all(re.fullmatch(r"[а-яё\s-]+", _плоско(c))
            and all(_описка_ли(w, B) for w in re.findall(r"[а-я]{4,}", _плоско(c)))
            and re.findall(r"[а-я]{4,}", _плоско(c)) for c in показ)):
        return None, "непонятное слово: «%s»" % показ[0]
    if not опора and not свидание_без_занятия:
        return None, "ни один чип не сказан человеком"
    # КЛЮЧ ЗАГОЛОВКА. «Съесть рамен» с чипом food, «Поесть суши» с food, «Покататься на велосипеде по
    # паркам» с park (стенд 4b, судьи 24.09.2026): занятие из заголовка в чипы не попадало, и поиск шёл
    # по общему. Существительное заголовка или предмета, сведённое в ключ, встаёт первым, если оно
    # проходит то же сито «сказано ли» (там и «рамена» -> рамен по общему началу). Глаголы («поесть» ->
    # food) и места — нет; место сверяется по КЛЮЧУ: «парке» морфология разбирает как «парка».
    общие_к = set(getattr(B, "_GENERIC_TOPIC", set()) or set()) | set(getattr(B, "_NO_ACTIVITY", set()) or set())
    # Пара слов проверяется раньше одного: «настольный теннис» — pingpong, а поодиночке «теннис» давал
    # tennis, и карточка про пинг-понг получала большой теннис первым (ревью 4d).
    кандидаты = []
    формы_сказ = _сказанное(said, B, lang)[0]
    for часть in (str(карточка.get("subject") or ""), title):
        сл = re.findall(r"[^\W\d_]{3,}", _плоско(часть), re.UNICODE)
        i = 0
        while i < len(сл):
            к = ""
            if _глагол_тег(сл[i], B):
                i += 1                                # «выпить кофе» целиком — drinks, «поесть суши» — food
                continue
            if i + 1 < len(сл):
                к = _ключ_пары(сл[i], сл[i + 1], B)
                # Пара — сказанной, только если сказаны ОБА слова: иначе «теннис» держал pingpong через
                # подпись «Настольный теннис», и несказанный «настольный» ставил пинг-понг первым.
                if к and not all(_формы(x, B) & формы_сказ for x in (сл[i], сл[i + 1])):
                    к = ""
                    i += 2
                    continue
            if к:
                кандидаты.append(к)
                i += 2
                continue
            кандидаты.append(_ключ_слова(сл[i], B))
            i += 1
    for к in кандидаты:
        if not к or к in ключи or к in общие_к or к in отказ or к in _ключи_мест(B):
            continue
        try:
            сказан = к in чипы([к], said, B, profile, lang=lang, запас={})[0]
        except Exception:
            сказан = False
        if сказан:
            ключи.insert(0, к)
            показ.insert(0, к)
    ключи, показ = ключи[:4], показ[:4]
    кат, тип, дом = _категории()
    категория = str(карточка.get("category") or "").strip().lower()
    if категория not in кат:
        категория = "other" if "other" in кат else кат[-1]
    роль = str(карточка.get("role") or "").strip().lower()
    роль = роль if роль in _РОЛИ else ""
    темы = ключи + [x for x in показ if x not in ключи]
    cat = {"topics": темы, "category": категория, "subcategory": "",
           "type": "dating" if категория == "dating" else тип.get(категория, "social"),
           "domain": дом.get(категория, "social_meet"), "role": роль, "isNew": not ключи, "note": title}
    sig = dict(profile or {})
    sig.update(signals or {})
    затея = dict(B.build_intent(sig, cat, said[-1] if said else "", lang, said=said) or {})
    if имя_v1:
        title = str(затея.get("title") or "").strip()
        if len(title.split()) < 2:
            return None, "заголовок без глагола и предмета"
    нов, правка = _поправь_заголовок(title, ключи, lang, B)
    if правка and нов != title:
        print("[v2-заголовок] %s -> %s (%s)" % (title, нов, правка), flush=True)
        title = нов
        if len(title.split()) == 1 and _глагол_ли(title, lang, B):
            title = title + {"ru": " вместе", "en": " together", "es": " juntos"}.get(lang, " вместе")
    предмет = str(карточка.get("subject") or "").strip() or (показ[0] if показ else "")
    # Что видит человек и что главное для поиска — от V2. Чипы телефон рисует из topics.
    затея.update({"title": title, "activity": title, "subject": предмет, "topics": темы, "tags": темы,
                  "category": категория, "type": cat["type"], "rankable": True,
                  "desc": _описание(title, lang), "lang": lang})
    if свидание_без_занятия:
        затея["needs_activity"] = True
    if роль:
        затея["role"] = роль
    return затея, ""


# ---------------------------------------------------------------- ответ против карточки

# ЗАЯВЛЕНИЕ О ПОИСКЕ. Промпт это запрещает, но модель нарушает стабильно: на стенде 24.09.2026 39
# ответов чата без карточки и 43 хода сборщика говорили «ищу / создаю карточку / давай найдём»,
# а окна не было — человек ждал поиска, которого нет. Держит код. Ловим только ПЕРВОЕ лицо агента
# и только утверждение: вопрос «Хочешь, поищу?» — это предложение, а не ложь, он остаётся.
# «Ты ищешь», «могу подобрать» и «помогаю находить» не ловятся нарочно: это рассказ о себе.
# Известное ложное срабатывание — «Ну давай, найдём, чем заняться!»: цена ему один лишний переспрос.
_АП = "['\u2019]?"
_ЗАЯВКА = re.compile(
    r"(?iu)(?<![\w-])(?:ищу|ищем|поищу|поищем|найду|найд[её]м|подберу|подбер[её]м|позову|позов[её]м|"
    r"буд(?:у|ем)\s+искать|созда[юм]|созда[её]м|создадим|"
    # «создал» — только про карточку/объявление: «меня создала команда Kleal» — не заявление.
    r"создал[а]?\s+(?:тебе\s+|для\s+тебя\s+)?(?:карточк\w*|объявлени\w*|затею|интент\w*)|"
    r"помогу\s+(?:тебе\s+)?(?:найти|подобрать)|"
    # «Дай мне немного подобрать» — снимок владельца 24.09.2026, 16:47: обещание без карточки.
    r"да(?:й|йте)\s+мне\s+(?:немного\s+|чуть\s+|минутку\s+)?(?:подобрать|поискать|найти)|"
    r"i" + _АП + r"m\s+(?:already\s+)?(?:looking|searching)(?!\s+forward)|we" + _АП + r"re\s+(?:looking|searching)(?!\s+forward)|"
    r"i" + _АП + r"ll\s+(?:find|look|search|connect)(?!\s+out)|let" + _АП + r"s\s+(?:find|connect\s+you)(?!\s+out)|"
    r"i" + _АП + r"ll\s+help\s+you\s+find|"
    r"busco|buscamos|buscar[eé]|buscaremos|vamos\s+a\s+(?:buscar|encontrar)|voy\s+a\s+buscar|"
    r"encontrar[eé]|encontraremos|encontremos|te\s+ayudo\s+a\s+(?:buscar|encontrar)|"
    # Шаг 4 (каталог голоса, 24.09.2026): английские и испанские обещания, которые проходили мимо —
    # 30 ответов на двух прогонах; и гарантии: «обязательно найдётся», «держу в курсе».
    r"let" + _АП + r"s\s+(?:get\s+you\s+connected|see\s+who)|let\s+me\s+(?:help\s+you\s+)?(?:find|connect|look)|"
    r"i\s+can\s+help\s+you\s+find|i" + _АП + r"d\s+(?:love|be\s+happy)\s+to\s+help\s+you\s+find|i" + _АП + r"ll\s+help\s+you\s+connect|"
    r"i" + _АП + r"ll\s+keep\s+you\s+posted|hope\s+you\s+find|someone\s+will\s+(?:definitely|surely)|"
    r"vamos\s+a\s+ver\s+(?:si|qui[eé]n)|voy\s+a\s+ver\s+si|ojal[aá]\s+encuentres|"
    r"(?:обязательно|точно|наверняка)\s+(?:кто-?(?:то|нибудь)\s+)?(?:найд[её]тся|присоедин\w*|захочет|откликн\w*)|"
    r"держу\s+в\s+курсе|напишу\s+тебе|надеюсь,?\s+ты\s+найд[её]шь|у\s+меня\s+(?:уже\s+)?есть\s+(?:пара\s+)?вариант\w*|"
    # Шаг 4c (судьи 24.09.2026, 11 отметок «ложное обещание» против 2): после вырезания похвалы на виду
    # остались обещания людей — «кто-то точно тоже рад присоединиться», «ты обязательно найдёшь того,
    # кто тебе по душе», «рад, что нашёл(а) единомышленников», «удачной встречи!» до всякого поиска.
    r"(?<!если\s)(?<!чтобы\s)кто-?(?:то|нибудь)\s+(?:[\w-]+\s+){0,3}?(?:присоедин\w*|найд[её]тся|откликн\w*|составит)|"
    r"(?:обязательно|точно|наверняка)\s+найд[её]шь|рад[аы]?,?\s+что\s+(?:ты\s+)?наш[её]л\w*(?:\(а\))?\s+(?:единомышленник\w*|компани\w*|друз\w*|люд\w*|кого|партн[её]р\w*)|(?:удачной|приятной)\s+встречи|"
    r"you" + _АП + r"ll\s+(?:definitely\s+|surely\s+)?find|someone\s+will\s+(?:join|love|be\s+happy)|"
    r"alguien\s+(?:se\s+)?(?:unir[aá]|apuntar[aá])|seguro\s+que\s+(?:alguien|encuentras))(?![\w-])")
# «не ищу», «пока не создаю», «I won't look» — это не заявление.
_НЕ_ПЕРЕД = re.compile(r"(?iu)(?:\bне|\bnot|n" + _АП + r"t|\bno)\s+(?:\w+\s+)?$")
_ПРЕДЛ = re.compile(r"[^.!?…\n]+[.!?…]*[»\"'\u2019)\]]*\s*")
_ХВОСТ = re.compile("[\\s»\"'\u2019)\\]\u2600-\u27BF\U0001F300-\U0001FAFF]+$")


def _заявка_в(предложение):
    s = предложение.strip()
    if not s or _ХВОСТ.sub("", s).endswith(("?", "？")):
        return False                      # вопрос — это предложение, а не заявление («…на каток?)»)
    return any(not _НЕ_ПЕРЕД.search(s[:m.start()]) for m in _ЗАЯВКА.finditer(s))


def заявляет_поиск(ответ):
    """Есть ли в ответе утверждение «ищу / создаю / найдём» (не вопрос)."""
    return any(_заявка_в(s) for s in _ПРЕДЛ.findall(str(ответ or "")))


def без_заявок(ответ):
    """Ответ без предложений-заявлений о поиске; вопросы и остальное — как были."""
    return "".join(s for s in _ПРЕДЛ.findall(str(ответ or "")) if not _заявка_в(s)).strip()


def _ключи_занятий(тексты, B):
    """Ключи реестра, которые называют эти реплики: слова, их словарные формы и пары соседних
    слов («пинг понг», «live music»). Общие корзины и «не занятия» не считаются."""
    нельзя = set(getattr(B, "_GENERIC_TOPIC", set()) or set()) | set(getattr(B, "_NO_ACTIVITY", set()) or set())
    из = set()
    for т in тексты:
        слова = re.findall(r"[^\W\d_]{2,}", _плоско(т), re.UNICODE)
        кандидаты = set()
        for w in слова:
            кандидаты |= _формы(w, B)
        кандидаты |= {a + " " + b for a, b in zip(слова, слова[1:])}
        for w in кандидаты:
            # «go» — глагол почти любой английской просьбы («go on a date», «let's go running»), а
            # реестр сводит его в golang: язык программирования вставал чипом свидания (мерка 26.09.2026).
            if w in _НЕ_КЛЮЧ_ИЗ_РЕЧИ:
                continue
            try:
                к = B.norm_topic(w) or ""
            except Exception:
                к = ""
            if к and к not in нельзя:
                из.add(к)
        из |= {к for к in _эмодзи_слова(т, B) if к not in нельзя}
    return из


_НЕ_КЛЮЧ_ИЗ_РЕЧИ = {"go"}


def _без_отказа(ключи, текст, B):
    """Ключи без отвергнутого в этой же реплике. Места (B.place_words) не вычитаются нарочно:
    это слова после «в/на», и «лучше в бассейн» потеряло бы само занятие."""
    try:
        отказ = {_плоско(x) for x in B.negated_terms(текст)}
    except Exception:
        отказ = set()
    return {к for к in ключи if к not in отказ}


def _формы_текста(текст, B):
    """Словарные формы всех слов реплики."""
    из = set()
    for w in re.findall(r"[^\W\d_]{3,}", _плоско(текст), re.UNICODE):
        из |= _формы(w, B)
    return из


def _реплика_занятия(said, B):
    """Реплика, где человек назвал занятие: последняя, а на «да / да хочу» без занятия — предыдущая."""
    if not said:
        return ""
    try:
        да = B._is_affirmation(said[-1])
    except Exception:
        да = False
    if да and len(said) > 1 and not _ключи_занятий(said[-1:], B):
        return said[-2]
    return said[-1]


def _ключи_человека(said, B):
    """Ключи занятий из реплики человека — без отвергнутого в ней и во всём разговоре."""
    текст = _реплика_занятия(said, B)
    if not текст:
        return set()
    return _без_отказа(_ключи_занятий([текст], B), текст, B) - _явный_отказ(said, B)


# Глаголы, которые сами занятия не называют: «поиграть» без «во что» — не заголовок.
_ОБЩИЕ_ГЛАГОЛЫ = {"поиграть", "сыграть", "играть", "сходить", "пойти", "идти", "заняться", "пообщаться",
                  "встретиться", "поехать", "съездить", "сделать", "найти", "посмотреть", "смотреть", "хотеть",
                  "мочь", "попробовать", "начать", "потусить", "провести", "погнать", "поговорить", "поесть"}
# Ветка реестра -> категория фильтрации (для карточки из слов человека: модели там нет).
_ВЕТКА_КАТ = {("sports", "mindbody"): "wellness", ("social", "coffee"): "coffee", ("social", "dining"): "food_drink",
              ("social", "foodie"): "food_drink", ("social", "nightlife"): "nightlife", ("social", "wellness"): "wellness",
              ("social", "pets"): "pets", ("games", "esports"): "esports", ("games", "tabletop"): "tabletop",
              ("culture", "screen"): "film_tv", ("culture", "reading"): "books", ("culture", "writing"): "books",
              ("tech", "startups"): "startups", ("tech", "career"): "career", ("outdoors", "travel"): "travel",
              ("learning", "language"): "languages", ("learning", "langs2"): "languages"}
_КОРЕНЬ_КАТ = {"sports": "sports", "social": "social", "games": "gaming", "culture": "art_culture", "tech": "tech",
               "music": "music", "outdoors": "outdoors", "learning": "other"}


def _категория_ключа(ключ):
    """Категория фильтрации по месту ключа в дереве реестра."""
    if "ветки" not in _КЭШ:
        рег = json.load(io.open(os.path.join(_ROOT, "shared", "interests.json"), encoding="utf-8"))
        карта = {}

        def обойти(у, путь):
            if isinstance(у, dict):
                for k, v in у.items():
                    карта.setdefault(k, (путь + (k,))[:2])
                    обойти(v, путь + (k,))
            elif isinstance(у, list):
                for v in у:
                    if isinstance(v, str):
                        карта.setdefault(v, путь[:2])
                    else:
                        обойти(v, путь)
        обойти(рег.get("tree", {}), ())
        _КЭШ["ветки"] = карта
    путь = tuple(_КЭШ["ветки"].get(ключ) or ())
    return _ВЕТКА_КАТ.get(путь[:2]) or _КОРЕНЬ_КАТ.get(путь[:1] and путь[0] or "", "other")


def _заголовок_из_слов(текст, ключи, B):
    """Глагол человека с его предметом: «выпить кофе», «сходить в кино». Один глагол — только если он
    сам называет занятие («погулять»): голое «выпить» из «выпить кофе» стало «Выпить вместе»."""
    слова = re.findall(r"[а-яё]+", _плоско(текст))
    for i, w in enumerate(слова):
        if len(w) < 4 or not _глагол_ли(w, "ru", B):
            continue
        j, предлог, хвост = i + 1, [], []
        if j < len(слова) and слова[j] in ("в", "во", "на"):
            предлог, j = [слова[j]], j + 1
        while j < len(слова) and len(хвост) < 3 and (_ключи_занятий([слова[j]], B) & ключи):
            хвост.append(слова[j])
            j += 1
        if хвост:
            фраза = " ".join([w] + предлог + хвост)
            return фраза[:1].upper() + фраза[1:]
        if w not in _ОБЩИЕ_ГЛАГОЛЫ and (_ключи_занятий([w], B) & ключи):
            return w[:1].upper() + w[1:]
    return ""


# Канон первого хода не берётся: смотреть, а не играть («на футбольный матч» -> канон «Поиграть в футбол»),
# и отказ словами, которых не знает отрицание («надоело кино», «устал от бега») — ревью 4d, третий круг.
_НЕ_КАНОН = re.compile(r"(?iu)\b(?:матч\w*|болеть|поболеть|трансляци\w*|посмотреть|смотреть|надоел\w*|наскучил\w*|"
                       r"достал\w*|устал\w*|хватит|не\s+предлагай|не\s+надо|не\s+хочу)\b")


def _карточка_из_слов(said, B, lang, затравка=False):
    """Карточка из слов человека — только занятие, которое он сам назвал; вопрос не в счёт.
    Заголовок — его глагол, если глагол сам называет занятие («погулять», «поплавать»); иначе имя
    собирает V1 (build_intent), как для однословного заголовка модели."""
    if not said or re.search(r"[?？¿]\s*$", str(said[-1] or "")):
        return None
    # ТОЛЬКО РУССКИЙ И ТОЛЬКО С ГЛАГОЛОМ ЧЕЛОВЕКА. На стенде шага 4b: «lets go taste some» -> чип golang
    # («go» у реестра — язык), «signed up for a pottery course and bailed» (рассказ) -> карточка «Meet
    # someone». Без заголовка из слов человека и в рассказе о прошлом карточку из слов не строим.
    if рассказ_о_прошлом(said[-1], B):
        return None
    if lang != "ru":
        return _карточка_канона(said, B, lang, затравка)
    ключи = _ключи_человека(said, B)
    текст = _реплика_занятия(said, B)
    if not ключи:
        return None
    title = _заголовок_из_слов(текст, ключи, B)
    if not title and затравка and not _НЕ_КАНОН.search(текст):
        # Первый ход без глагола человека («на каток бы», «кофе»): канон занятия — только если оно в
        # реплике ОДНО и не место. К прошлым репликам не возвращаемся: откат давал карточки из рассказов,
        # вопросов и заведений (ревью 4d, два круга), а переспрос первого хода после «Понял — …» снова есть.
        активные = sorted(к for к in ключи if к not in _ключи_мест(B))
        if len(активные) == 1:
            title = _канон(активные[0], lang)
    if not title and any(_СВИДАНИЕ.search(str(x or "")) for x in said):
        # СВИДАНИЕ: ответ на вопрос «как провести свидание?» — «давай прогуляемся по набережной». Из формы
        # «прогуляемся» заголовок не собрать, а у свидания он один. Чип — занятие из последней реплики
        # (мерка 26.09.2026, свидание-1: модель дала «без карточки», экран остался пустым).
        занятия = sorted(к for к in _без_отказа(_ключи_занятий(said[-1:], B), said[-1], B) if к not in _ключи_мест(B))
        if занятия:
            return {"request": True, "title": "Сходить на свидание", "subject": "", "chips": занятия[:4],
                    "category": "dating", "role": ""}
    if not title:
        return None
    первый = sorted(ключи)[0]
    return {"request": True, "title": title, "subject": "", "chips": sorted(ключи)[:4],
            "category": _категория_ключа(первый), "role": ""}


_СВИДАНИЕ_КАНОН = {"en": "Go on a date", "es": "Tener una cita"}


def _карточка_канона(said, B, lang, затравка=False):
    """Английский и испанский: морфологии нет, глагол человека в заголовок не взять — берём канон ОДНОГО
    занятия. Ночная проверка 27.09.2026: «yeah sure, find me someone to shoot with» — сборщик без карточки
    3 раза из 3; «no, mejor al teatro» — ответ «ir al teatro», а на экране остался музей. Занятие — из
    последней реплики; на первом ходу (согласие «yeah sure…») — из двух последних."""
    места = _ключи_мест(B)
    активные = sorted(к for к in _без_отказа(_ключи_занятий(said[-1:], B), said[-1], B) if к not in места)
    if not активные and затравка and len(said) > 1:
        активные = sorted(к for к in _ключи_человека(said[-2:], B) if к not in места)
    if len(активные) != 1:
        return None
    к = активные[0]
    if any(_СВИДАНИЕ.search(str(x or "")) for x in said):
        return {"request": True, "title": _СВИДАНИЕ_КАНОН.get(lang, "Go on a date"), "subject": "", "chips": [к],
                "category": "dating", "role": ""}
    title = _канон(к, lang)
    if not title:
        return None
    return {"request": True, "title": title, "subject": "", "chips": [к], "category": _категория_ключа(к), "role": ""}


def занятие_в_последней(said, B):
    """Последняя реплика называет занятие (не отвергнутое). Для переспроса сборщика «новое» не
    годится: если чат ответил на затравку пустой строкой, первый ход сборщика не отличить от
    обычного, а занятие в нём названо (проверка шага 2, 24.09.2026)."""
    if not said:
        return False
    return bool(_без_отказа(_ключи_занятий(said[-1:], B), said[-1], B))


def новое_занятие(said, B):
    """Последняя реплика называет занятие, которого раньше в разговоре не было."""
    if not said:
        return False
    return bool(_без_отказа(_ключи_занятий(said[-1:], B) - _ключи_занятий(said[:-1], B), said[-1], B))


# Записки для ОДНОГО переспроса — по-английски и по причине: общая русская пометка «нет чипов»
# не говорила модели, что исправлять, и вторая попытка повторяла ту же карточку (family-09, own-01).
_ПОЧЕМУ = {
    "нет чипов": "none of its chips is something the user said",
    "ни один чип не сказан человеком": "none of its chips is something the user said",
    "заголовок без глагола и предмета": "the title must be a verb plus an object, like «Поиграть в сквош»",
    "обращение к агенту": "the user is talking to you, not asking to meet other people",
}
_ЗАПИСКА_БРАК = ("Your card was not used: %s.%s Chips are VOCABULARY keys for things the user named, or the "
                 "user's own word as they wrote it, in dictionary form and in their language. Send your reply "
                 "and the corrected card again. If the user did not ask to do something with other people, "
                 "return {\"card\": null} and do not say you are looking for anyone.")
_ЗАПИСКА_АГЕНТ = ("The user is talking to you, not asking to meet other people. Reply to them yourself, kindly "
                  "and honestly, and return {\"card\": null}.")
_ЗАПИСКА_ОБЕЩАНИЕ = ("Your reply says you are looking for or finding people, but you sent no card, so nothing "
                     "will happen in the app. If the user's own words ask to do a specific activity with other "
                     "people, send your reply and the card. If not, rewrite the reply so it does not say you are "
                     "looking for anyone, and return {\"card\": null}.")
_ЗАПИСКА_ПРОСЬБА = ("The user's last message already asks for company for an activity they named (or agrees to your "
                    "offer). Send the card now, in this reply, and do not ask them to confirm. If they are talking "
                    "about you or refused, return {\"card\": null}.")
_ЗАПИСКА_СБОРЩИК = ("The user is in the card builder, and the card on their screen changes only when you send one. "
                    "If their last message names the activity or changes the plan, or it is their first message "
                    "here, send your reply and the full card for the plan as it is now, keeping everything they "
                    "did not change. If it does not change the plan, return {\"card\": null}.")


_ЗАПИСКА_ПОНЯЛ = ("Your reply «Понял — …» sounds like a plan was made, but there is no plan and the user did not ask "
                  "for one. Reply to what they actually said, in your own words, like a friend, and return {\"card\": null}.")
# Наша заготовка окна («Понял — сходить в кино.»), которую модель повторяет из истории без карточки.
_ПОНЯЛ_ЗАТЕЯ = re.compile(r"(?iu)^(?:понял|got it|entendido)\s+[—–-]\s+[^.!?…\n]{2,60}[.!…]\s*")


# Явная сексуальная просьба. «На одну ночь», hookup, fwb сюда НЕ входят — это решение владельца (27.09.2026).
_ИНТИМ = re.compile(r"(?iu)\b(?:sext(?!et|ant)\w*|секст\w*|nudes?|nude\s+pics?|dick\s*pics?|нюдс\w*|нюдес\w*|"
                    r"интим\w*|секс(?!\s*пистолс)\w*|sex(?!\s+(?:pistols|and\s+the\s+city|education|ed\b))|sexual\w*|"
                    r"sexo|porn\w*|порн\w*|onlyfans|трах\w*|ебат\w*|ебать\w*|follar|coger\s+con|"
                    # de / fr / it / pt (13.10.2026)
                    r"ficken|bumsen|nacktbilder|nacktfotos|sexuell\w*|"
                    r"sexe|sexuel\w*|plan\s+cul|coucher\s+avec|baiser\s+avec|"
                    r"sesso|sessual\w*|scopare\s+con|scopata|foto\s+nude|"
                    r"foder|transar|putaria)\b")
_ИНТИМ_ОТВЕТ = {
    "ru": "С секстингом и интимом не помогу — Kleal для живых встреч и общения. Если хочешь познакомиться с кем-то "
          "для свидания, скажи — соберу свидание: кофе, прогулка или ужин.",
    "en": "I can't help with sexting or anything sexual — Kleal is for meeting people and doing things together. If you'd "
          "like to meet someone for a date, just say so and I'll set it up: coffee, a walk or dinner.",
    "es": "Con sexting o temas sexuales no puedo ayudarte: Kleal es para conocer gente y hacer planes. Si quieres conocer a "
          "alguien para una cita, dímelo y la preparo: un café, un paseo o una cena.",
    "de": "Bei Sexting oder Sexuellem kann ich nicht helfen — Kleal ist für echte Treffen und gemeinsame Aktivitäten. Wenn du "
          "jemanden für ein Date kennenlernen möchtest, sag es mir, dann plane ich es: Kaffee, Spaziergang oder Abendessen.",
    "fr": "Pour le sexting ou le sexuel, je ne peux pas aider — Kleal sert à rencontrer des gens et à faire des choses ensemble. "
          "Si tu veux rencontrer quelqu’un pour un rendez-vous, dis-le-moi et je l’organise : un café, une balade ou un dîner.",
    "it": "Con il sexting o temi sessuali non posso aiutarti: Kleal serve per incontrare persone e fare cose insieme. Se vuoi "
          "conoscere qualcuno per un appuntamento, dimmelo e lo organizzo: un caffè, una passeggiata o una cena.",
    "pt": "Com sexting ou temas sexuais não posso ajudar — o Kleal é para conhecer pessoas e fazer coisas em conjunto. Se queres "
          "conhecer alguém para um encontro, diz-me e eu organizo: um café, um passeio ou um jantar."}
_ИНТИМ_ЕЩЁ = {
    "ru": "Понимаю, но с этим — нет. Свидание, кофе или компания на что-то — пожалуйста.",
    "en": "I get it, but that's not something I do. A date, coffee or company for something — happy to help.",
    "es": "Lo entiendo, pero con eso no. Una cita, un café o compañía para algo: encantado.",
    "de": "Verstehe, aber dabei nicht. Ein Date, ein Kaffee oder Gesellschaft für etwas — gern.",
    "fr": "Je comprends, mais ça, non. Un rendez-vous, un café ou de la compagnie pour quelque chose : avec plaisir.",
    "it": "Capisco, ma con questo no. Un appuntamento, un caffè o compagnia per qualcosa: volentieri.",
    "pt": "Percebo, mas com isso não. Um encontro, um café ou companhia para algo: com gosto."}
_ЗАПИСКА_ИНТИМ = ("The user keeps asking for sexting or sexual content. You already told them you cannot help with that. "
                  "Reply in ONE short sentence, in your own words and differently from all your previous replies: stay "
                  "calm and kind, never argue with insults or repeat them, and offer a date or company for an activity "
                  "instead. Never offer to help with anything sexual. Return {\"card\": null}.")
# Ответ модели упоминает интим, но без отказа («помогу найти кого-то для секстинга») — заменяется заготовкой.
_ОТКАЗ_В_ОТВЕТЕ = re.compile(r"(?iu)can'?t|cannot|won'?t|not\s+something|не\s+(?:могу|помогу|буду)|с\s+этим\s+(?:—\s*)?нет|"
                            r"no\s+puedo|no\s+voy|con\s+eso\s+no")
_ЗАПИСКА_ПОВТОР = ("Your reply repeats what you already told the user almost word for word. Answer what they said just "
                   "now, in different words. If they keep asking for something you cannot help with, say so plainly in "
                   "one short sentence and offer what you can do instead — do not repeat your earlier explanation.")


def _повтор_ответа(ответ, msgs):
    """Ответ почти слово в слово повторяет прежний ответ агента: от 8 слов и не меньше 80% общих."""
    а = set(re.findall(r"[^\W\d_]+", _плоско(ответ), re.UNICODE))
    if len(а) < 8:
        return False
    for m in (msgs or [])[:-1]:
        if m.get("role") != "assistant":
            continue
        б = set(re.findall(r"[^\W\d_]+", _плоско(m.get("content")), re.UNICODE))
        if б and len(а & б) / float(len(а | б)) >= 0.8:
            return True
    return False


def _записка_брака(пометка, карточка, показ):
    if пометка == "обращение к агенту":
        return _ЗАПИСКА_АГЕНТ
    if пометка == "сейчас делает":
        return ("The user only said where they are or what they are doing right now; they did not ask for company. "
                "That is not a plan: reply to it as a friend in one or two short sentences and return {\"card\": null}.")
    if пометка == "свидание без занятия":
        return ("The user wants a date. A person (a girl, a guy) and the word date itself are never chips: the "
                "chip is WHAT they will do on the date. If the user already said it in any words (a walk, "
                "coffee, dinner, cinema, «прогуляемся», «un café»…), send your reply and the card again with that "
                "activity as the chip (walk, coffee, dinner, cinema…), category dating. If they have not said it, "
                "ask one short, warm question in their language — coffee, a walk, dinner or something else? — "
                "and return {\"card\": null}.")
    if пометка.startswith("заголовок про отменённое"):
        return ("Your card was not used: its title or subject is about «%s», which the user refused or replaced. "
                "Make the card about what they want now, without it." % пометка.split("«", 1)[-1].rstrip("»"))
    if пометка.startswith("непонятное слово"):
        return ("The user wrote %s, which is not a word you know for sure. Do not guess what it is and do not "
                "make a card: ask them in one short question what it is, and return {\"card\": null}."
                % пометка.split(": ", 1)[-1])
    выброшено = [str(c) for c in ((карточка or {}).get("chips") or []) if str(c) not in (показ or [])]
    хвост = (" Dropped chips: %s." % ", ".join(выброшено[:6])) if выброшено else ""
    return _ЗАПИСКА_БРАК % (_ПОЧЕМУ.get(пометка, пометка), хвост)


_ОТМЕНА = re.compile(r'"cancel"\s*:\s*true', re.I)
# ОТМЕНА ВСЕЙ ЗАТЕИ СЛОВАМИ ЧЕЛОВЕКА. Флаг cancel модель не поставила ни разу за 946 ходов стенда
# (каталог шага 4): «забей» — и карточка оставалась на экране и уходила в поиск. «неважно», «не важно»,
# «da igual» — не отмена (own-01: «Не важно» — про детали).
_ОТМЕНИТЬ_ВСЁ = re.compile(
    r"(?iu)\b(?:забей|проехали|отбой|отмени\w*|отменяй|ничего\s+не\s+надо|никого\s+не\s+(?:ищи|надо)|не\s+надо\s+никого|"
    r"forget\s+it|never\s*mind|cancel\s+(?:it|that|this)|olv[ií]dalo|d[ée]jalo|es\s+cosa\s+m[ií]a|"
    r"cancel(?:a|ar|o)?|an[uú]la(?:r|lo)?|ya\s+no\s+quiero(?:\s+nada)?)\b")


# ЗОВ ИСКАТЬ: «хочешь, найду…?», «могу помочь найти…», «Want to find someone…?», «¿Quieres que busque…?»
_ЗОВ = re.compile(r"(?iu)(?:хочешь|хотел\w*\s+бы|могу|можем|давай|найти\s+тебе|поищу|найду|подобрать)[^.!?…\n]{0,80}"
                  r"(?:с\s+кем|кого-?(?:то|нибудь)|компани\w*|партн[её]р\w*|собеседник\w*|людей|единомышленник\w*)|"
                  r"(?:want|would\s+you\s+like|shall\s+i|i\s+can)[^.!?\n]{0,60}(?:find|look\s+for|connect)[^.!?\n]{0,40}"
                  r"(?:someone|somebody|people|others|a\s+partner|company)|"
                  r"(?:quieres|te\s+gustar[ií]a|puedo)[^.!?\n]{0,60}(?:bus(?:c|qu)|encontr)[^.!?\n]{0,40}(?:alguien|gente|compa[ñn][ií]a|personas)")


_ОТСЫЛКА = re.compile(r"(?iu)\b(?:это|этом|этим|всё\s+это|все\s+это|об\s+этом|про\s+это|всё\s+разом|все\s+разом|"
                      r"this|that|all\s+of\s+it|esto|eso|todo\s+eso)\b")


def просит_компанию(msgs, said, B):
    """Человек уже попросил компанию для НАЗВАННОГО занятия или согласился на предложение агента.
    Триггер V1 (wants_people без фильтрации) плюс ключ реестра в той же реплике: запасной ярус V1
    «похоже на предмет» здесь слишком широк. Модель в таких ходах переспрашивала «Найти тебе
    компанию?» вместо карточки — 25 из 50 проигрышей V1 на стенде 24.09.2026 («в бассейн бы
    ходила, одной скучно», «ищу компанию в кино»)."""
    if not said or _к_агенту(said, B):
        return False
    try:
        if B._agreed_to_offer(msgs) or _принятое_предложение(msgs, B):
            return True
        # СВИДАНИЕ — ТОЖЕ ПРОСЬБА. «Да, хочу на свидание», «хочу найти себе девушку» (own-01, разговор
        # владельца): модель во всех версиях отвечала «звучит романтично» без карточки, а wants_people
        # этих слов не знает. Нужно желание и не вопрос: «как одеться на свидание?» — не просьба.
        if _СВИДАНИЕ.search(said[-1]) and _ЖЕЛАНИЕ.search(said[-1]) and not re.search(r"[?？]\s*$", said[-1].strip()):
            return True
        if not B.wants_people(said[-1], False):
            return False
        if занятие_в_последней(said, B):
            return True
        # СВОЁ ЗАНЯТИЕ ГЛАГОЛОМ: «хочу с кем-нибудь собрать ягоды и повесить шторы» — ключей реестра нет, но
        # просьба ясная: «с кем-нибудь» + действие инфинитивом. Модель отвечала «Хочешь, я помогу найти…?», и
        # окно выезжало лишь на следующем «да» (снимок владельца 25.09.2026, 03:02; живая проверка 4d — 1 из 2).
        if _действие_человека(said[-1], B):
            return True
        # ОТСЫЛКА НАЗАД: «хочу встретиться и обсудить это всё разом с кем-то» — занятия в реплике нет, но
        # оно названо раньше (own-03: крипта, CS, дота). Это тоже просьба.
        return bool(_ОТСЫЛКА.search(said[-1]) and _ключи_занятий(said[:-1], B))
    except Exception:
        return False


# Инфинитивы, которые сами занятия не называют: «хочу с кем-нибудь поговорить / познакомиться / провести время».
_НЕ_ДЕЙСТВИЕ = {"найти", "искать", "поискать", "познакомиться", "знакомиться", "встретиться", "встречаться", "пообщаться",
                "общаться", "поговорить", "поболтать", "провести", "проводить", "сделать", "делать", "заняться",
                "заниматься", "хотеть", "мочь", "быть", "стать", "начать", "попробовать", "помочь", "позвать", "собраться",
                "увидеться", "повидаться", "отдохнуть", "развеяться", "расслабиться", "тусить", "потусить"}


def _действие_человека(текст, B):
    """Назвал ли человек занятие СВОИМ глаголом-действием (инфинитив, не «найти/поговорить/провести»)."""
    разбор = getattr(B, "_морф_разбор", None)
    if разбор is None or re.search(r"[?？]\s*$", str(текст or "").strip()):
        return False
    for w in re.findall(r"[а-яё]{4,}", _плоско(текст)):
        if w in _НЕ_ДЕЙСТВИЕ:
            continue
        try:
            р = разбор.parse(w)[0]
            if "INFN" in str(р.tag) and разбор.word_is_known(w) and р.normal_form not in _НЕ_ДЕЙСТВИЕ:
                return True
        except Exception:
            continue
    return False


_СВИДАНИЕ = re.compile(
    r"(?iu)\b(?:на\s+свидани\w*|найти\s+(?:себе\s+)?(?:девушк\w*|парн\w*|пару|вторую\s+половин\w*)|"
    r"познакомиться\s+с\s+(?:девушк|парн)\w*|go\s+on\s+a\s+date|find\s+(?:me\s+)?a\s+(?:girlfriend|boyfriend|date)|"
    r"una\s+cita|buscar\s+(?:una\s+)?(?:novia|novio|pareja))")
_ЖЕЛАНИЕ = re.compile(
    r"(?iu)\b(?:хочу|хочется|хотел[аи]?\s+бы|хотелось\s+бы|давай|давайте|пошли|пойд[её]м|го|кто\s+(?:со\s+мной|хочет|пойд)|"
    r"с\s+кем|компани\w*|ищу|найти|найди|поищи|бы|может|завтра|в\s+выходные|would\s+like|want|let'?s|anyone|"
    r"quiero|vamos|me\s+apetece)\b")


# НАМЕРЕНИЕ В ПРОШЕДШЕМ ВРЕМЕНИ — НЕ РАССКАЗ. «думал сегодня в кино сходить», «хотел сходить глянуть»,
# «собирался в поход на выходных», «нет, передумал, лучше в бассейн», «кто ходил на байдарках?» — первая
# версия сторожа резала их все (стенд 3e, 24.09.2026: 17 срабатываний, из них ~12 на намерения и вопросы).
_НАМЕРЕНИЕ = re.compile(r"(?iu)\b(?:думал\w*|хотел\w*|собирал\w*|планировал\w*|мечтал\w*|решил\w*|передумал\w*|"
                        r"лучше|кто|где|когда|есть\s+кто)\b|\?")


# ГДЕ ЧЕЛОВЕК И ЧТО ДЕЛАЕТ СЕЙЧАС — рассказ, а не затея. Снимок владельца 26.09.2026, 18:29: на вопрос Буди,
# чем занимается, «в кофейне сижу» -> окно «Сходить в кофейню». Проба на бою: «я в кофейне, кофе пью» —
# окно 2 раза из 4, «сижу в баре с друзьями» — 1 из 4. Только глаголы состояния в настоящем времени от
# первого лица («сижу», «пью», «гуляю») или «я в/на …» без глагола; любое другое действие, инфинитив,
# желание, вопрос или зов компании — решает модель.
_СОСТОЯНИЕ = frozenset(("сидеть", "пить", "кушать", "гулять", "работать", "отдыхать", "смотреть", "читать",
                        "писать", "лежать", "стоять", "ждать", "учиться", "готовить", "валяться", "находиться",
                        "торчать", "кайфовать", "чилить", "чиллить", "завтракать", "обедать", "ужинать",
                        "заниматься", "тусить", "тусоваться", "зависать", "бухать", "есть"))
_ЗОВ_КОМПАНИИ = re.compile(r"(?iu)\b(?:кто|с\s+кем|компани\w*|присоедин\w*|составит\w*|одному|одной|вместе|"
                           r"со\s+мной)\b")
_Я_ГДЕ = re.compile(r"(?iu)^\s*(?:я\s+(?:сейчас\s+|щас\s+|пока\s+)?|сейчас\s+(?:я\s+)?|щас\s+(?:я\s+)?)(?:в|во|на)\s+[а-яё]")


def сейчас_делает(текст, B):
    """«в кофейне сижу», «я на работе», «пью кофе в кофейне» — человек говорит, где он и что делает, а не
    зовёт. False, если есть желание, намерение, вопрос, зов компании, инфинитив или другой глагол."""
    t = str(текст or "").strip()
    if not t or _ЖЕЛАНИЕ.search(t) or _НАМЕРЕНИЕ.search(t) or _ЗОВ_КОМПАНИИ.search(t):
        return False
    разбор = getattr(B, "_морф_разбор", None)
    if разбор is None:
        return False
    состояние = 0
    for w in re.findall(r"[а-яё]{2,}", t.lower()):
        try:
            вар = разбор.parse(w)[0]
        except Exception:
            continue
        тег = вар.tag
        if "INFN" in тег:
            return False
        if "VERB" in тег:
            if "pres" in тег and "3per" not in тег and вар.normal_form in _СОСТОЯНИЕ:
                состояние += 1
            else:
                return False
    return состояние > 0 or bool(_Я_ГДЕ.search(t))


def рассказ_о_прошлом(текст, B):
    """«сегодня пил кофе и рыбачил», «вчера сорвались в баню всем отделом» — рассказ, а не просьба
    (снимок владельца 24.09.2026, 16:44: окно выехало на рассказ, карточку дал переспрос). Рассказ —
    это прошедшее время БЕЗ инфинитива («сходить»), без глаголов намерения («думал», «хотел»,
    «собирался»), без «лучше», без вопроса и без признаков желания. Английский и испанский — только
    по маркерам V1 (вчера/на прошлой неделе)."""
    t = str(текст or "")
    if _ЖЕЛАНИЕ.search(t) or _НАМЕРЕНИЕ.search(t):
        return False
    разбор = getattr(B, "_морф_разбор", None)
    глаголы = прошлые = инфинитивы = 0
    if разбор is not None:
        for w in re.findall(r"[а-яё]{2,}", t.lower()):
            try:
                тег = разбор.parse(w)[0].tag
            except Exception:
                continue
            if "INFN" in тег:
                инфинитивы += 1
            elif "VERB" in тег:
                глаголы += 1
                прошлые += 1 if "past" in тег else 0
    if инфинитивы:
        return False
    try:
        if B._PAST.search(t):
            return True
    except Exception:
        pass
    return глаголы > 0 and прошлые == глаголы


def _без_затравки(msgs, B=None):
    """ПЕРВЫЙ ХОД СБОРЩИКА. Телефон (app/buddy.tsx toCreate) вырезает из истории фразу, на которой
    выехало окно, но оставляет ответ агента на неё, а саму фразу шлёт следом первым ходом. Модель
    видела «свой» ответ, а за ним ту же фразу ещё раз, считала дело сделанным и писала «Создаю
    карточку» без карточки. Без этой реплики модель видит ровно тот ход, на котором в чате собрала
    карточку окна, и собирает её снова. Две реплики агента подряд перед последней репликой человека
    в сборщике бывают только здесь (и после «Продолжим общаться» -> «Создать», где уходит заготовка
    sheetKept — это безвредно). -> (переписка, была ли затравка)."""
    if len(msgs) >= 2 and msgs[-1]["role"] == "user" and msgs[-2]["role"] == "assistant" and (
            len(msgs) == 2 or msgs[-3]["role"] == "assistant"):
        return msgs[:-2] + msgs[-1:], True
    # ОДНА РЕПЛИКА — ТОЖЕ ПЕРВЫЙ ХОД: окно выехало на самой первой фразе с пустым ответом, или человек
    # открыл сборщик сам. Вырезать нечего, но переспрос первого хода нужен.
    if len(msgs) == 1 and msgs[0]["role"] == "user":
        т = str(msgs[0].get("content") or "")
        # «привет» или «предложи что-нибудь» — не затравка: переспрос с «пришли полную карточку» давал
        # лишний вызов и выдуманную карточку. А голое «кофе» или «падел» — затравка: экран сборщика сам
        # подсказывает такие слова (ревью 4d, два круга).
        if (_ЖЕЛАНИЕ.search(т) or (B is not None and _ключи_занятий([т], B))) and not re.search(r"[?？¿]\s*$", т.strip()):
            return msgs, True
    return msgs, False


# ---------------------------------------------------------------- один ход

def _промпт(B, lang, сборщик, profile, signals):
    кат, _, _ = _категории()
    текущая = (signals or {}).get("v2_card")
    строка = ""
    if isinstance(текущая, dict) and текущая.get("title"):
        строка = ("CURRENT CARD (already shown to the user; change only what they changed): %s\n"
                  % json.dumps({"title": текущая.get("title"), "chips": текущая.get("chips") or []}, ensure_ascii=False))
    основа = B.settings.prompt("buddy.v2", ПРОМПТ) if hasattr(B, "settings") else ПРОМПТ
    текст = (основа.replace("__PROFILE__", _профиль_текстом(profile))
             .replace("__LANGNAME__", _ЯЗЫК[lang]).replace("__YOU__", _ОБРАЩЕНИЕ[lang])
             .replace("__CATS__", ", ".join(кат)).replace("__VOCAB__", ", ".join(_словарь(B)))
             .replace("__CURRENT__", строка))
    if сборщик:
        текст += B.settings.prompt("buddy.v2_builder", СБОРЩИК) if hasattr(B, "settings") else СБОРЩИК
    return текст


def ход(messages, profile, signals, lang, B, сборщик=False):
    """Один ход V2 -> (ответ, затея или None, язык, пометка, вызовов модели). Исключение — отдать ход V1."""
    msgs = нормализовать(messages)
    if not msgs or msgs[-1]["role"] != "user":
        raise RuntimeError("последней нет реплики человека")
    затравка = False
    if сборщик:
        msgs, затравка = _без_затравки(msgs, B)
    said = [m["content"] for m in msgs if m["role"] == "user"]
    lang = (lang or "").strip().lower()
    if lang not in _ЯЗЫК:
        try:
            lang = B.thread_lang(msgs, said[-1])
        except Exception:
            lang = "ru"
        lang = lang if lang in _ЯЗЫК else "ru"
    # Человек пишет по-немецки, по-французски, по-итальянски или по-португальски — отвечаем на его языке, каким бы ни
    # был язык интерфейса (телефон шлёт только ru/en/es). Только при уверенном распознавании, см. detect_lang_eu.
    try:
        _eu = B.detect_lang_eu(said)
    except Exception:
        _eu = None
    if _eu in _ЯЗЫК:
        lang = _eu

    # СТОРОЖА V1 на том же нормализованном списке, что увидит модель. Их заготовки дальше не чистятся:
    # в HARM_REPLY есть «не буду искать», и сито заявлений его бы съело.
    if B.stated_minor(msgs) is not None:
        return B.minor_reply(msgs, lang), None, lang, "возраст", 0
    вердикт, домен = B.safety.check_conversation(msgs, look_back=_ОКНО)
    if вердикт == "block":
        return B.REFUSE_REPLY.get(lang, B.REFUSE_REPLY["en"]), None, lang, "отказ", 0
    if вердикт == "selfharm":
        return B.SELFHARM_REPLY.get(lang, B.SELFHARM_REPLY["en"]), None, lang, "selfharm", 0
    if B.harmful_use_of_a_person(msgs):
        return B.HARM_REPLY.get(lang, B.HARM_REPLY["en"]), None, lang, "вред", 0
    интим_настаивает = False
    if _ИНТИМ.search(str(said[-1] or "")):
        # ИНТИМНАЯ ПЕРЕПИСКА — НЕ ЗАТЕЯ. Снимок тестировщика 27.09.2026: «Sexting», «find me some one to sexting
        # with» — модель пять раз подряд отвечала одной фразой «I'm here to help you find people to do things
        # with…», а первым ответом обещала «помочь обсудить секстинг». Kleal — не площадка для интима: первый раз
        # говорим это заготовкой прямо и предлагаем, что можем (свидание вживую). Дальше отвечает модель с
        # запиской — коротко и каждый раз иначе: одна заготовка на повтор звучала автоответчиком (4 раза подряд).
        первый = _ИНТИМ_ОТВЕТ.get(lang, _ИНТИМ_ОТВЕТ["en"])
        if not _было_у_агента(первый, msgs):
            return первый, None, lang, "интим", 0
        интим_настаивает = True

    сообщения = [{"role": "system", "content": _промпт(B, lang, сборщик, profile, signals)}] + msgs[-_ОКНО:]
    if интим_настаивает:
        сообщения.append({"role": "system", "content": _ЗАПИСКА_ИНТИМ})
    # ОТВЕТ ИЗ ТОЙ ЖЕ ПОПЫТКИ, ЧТО И КАРТОЧКА. Раньше человеку уходил текст ПЕРВОЙ попытки и после
    # отбраковки её карточки: «Помогу найти партнёра по сквошу!» при пустом экране, а на развороте
    # «в бассейн — отлично!» при карточке про скалодром (13 из 39 обещаний без окна на стенде
    # 24.09.2026 шли с переспросом). Теперь итог — последняя годная попытка целиком; текст первой
    # берётся, только если вторая прислала одну карточку без текста.
    итог, пометки, вызовов, отмена = None, [], 0, False
    for попытка in range(2):
        вызовов += 1
        сырое = B.llm_complete(B.MODEL_ID, сообщения, temperature=0.4 if попытка == 0 else 0.2, tag="v2") or ""
        ответ, карточка, чисто = разобрать(сырое)
        if not ответ and карточка and итог:
            ответ, чисто = итог[0], True          # вторая дала только карточку — текст из первой
        if not чисто or not B._lang_ok(ответ, lang) or (_эхо(ответ, said) and not карточка):
            пометки.append("брак ответа")
            if попытка == 0:
                continue
            break
        затея, пометка = _затея(карточка, msgs, profile, signals, lang, B) if карточка else (None, "без карточки")
        if сборщик and затея and затея.get("needs_activity"):
            затея, пометка = None, "свидание без занятия"
        if not сборщик and затея and сейчас_делает(said[-1], B):
            затея, пометка = None, "сейчас делает"
        пометки.append(пометка or "карточка")
        итог = (ответ, затея, карточка, пометка)
        if попытка == 1 or затея:
            break
        # ОДИН ПЕРЕСПРОС НА ХОД, по первой сработавшей причине.
        записка = ""
        if карточка and not затея and пометка != "нет заявки":
            показ = []
            if "чип" in пометка:
                try:
                    _, показ, _ = чипы(карточка.get("chips"), said, B, profile, lang=lang)
                except Exception:
                    показ = []
            записка = _записка_брака(пометка, карточка, показ)
        elif сборщик and not затея and (_ОТМЕНА.search(сырое) or _ОТМЕНИТЬ_ВСЁ.search(said[-1])) \
                and not занятие_в_последней(said, B):
            отмена = True
            break
        elif сборщик and not затея and (затравка or занятие_в_последней(said, B) or _явный_отказ(said[-1:], B)
                                         or B._is_affirmation(said[-1])):
            записка = _ЗАПИСКА_СБОРЩИК
        elif not затея and not карточка and _повтор_ответа(ответ, msgs):
            # ПОВТОР СВОЕЙ ЖЕ РЕПЛИКИ БЕЗ КАРТОЧКИ: человек настаивает, а модель слово в слово повторяет прошлый
            # ответ (снимок тестировщика 27.09.2026 — пять одинаковых ответов). При карточке это уже ловит
            # _было_у_агента; без карточки сторожа не было.
            записка = _ЗАПИСКА_ПОВТОР
        elif not сборщик and not затея and заявляет_поиск(ответ) and not рассказ_о_прошлом(said[-1], B):
            записка = _ЗАПИСКА_ОБЕЩАНИЕ
        elif not сборщик and not затея and not карточка and not рассказ_о_прошлом(said[-1], B) \
                and not сейчас_делает(said[-1], B) and просит_компанию(msgs, said, B):
            записка = _ЗАПИСКА_ПРОСЬБА
        elif not сборщик and not затея and not карточка and _ПОНЯЛ_ЗАТЕЯ.match(str(ответ or "").strip()):
            # Не просьба и не обещание — значит, «Понял — X.» списан из истории. Карточку НЕ просим: на
            # «нет» после закрытого окна записка без запрета давала окно «Выпить кофе» (теневая проба 26.09).
            записка = _ЗАПИСКА_ПОНЯЛ
        if not записка:
            break
        # Человек прошлой попытки НЕ видел. Без этой строки модель извинялась за неё: «Извини, я немного
        # запутался», «Вот исправленная карточка:» — 5–11 таких ответов на прогон (стенд шага 3, 24.09.2026).
        записка += (" The user never saw your previous attempt: reply to their message as if for the first time — "
                    "do not apologize, do not mention any correction, card or mistake.")
        сообщения = сообщения + [{"role": "assistant", "content": str(сырое)[:1500]},
                                 {"role": "system", "content": записка}]
    if not итог:
        raise RuntimeError("модель не дала годного ответа: %s" % ",".join(пометки))
    ответ, затея, _, пометка = итог
    if интим_настаивает:
        затея = None
        if (not str(ответ or "").strip() or _повтор_ответа(ответ, msgs) or _было_у_агента(ответ, msgs)
                or (_ИНТИМ.search(str(ответ)) and not _ОТКАЗ_В_ОТВЕТЕ.search(str(ответ)))):
            ответ = _ИНТИМ_ЕЩЁ.get(lang, _ИНТИМ_ЕЩЁ["en"])
        пометка = "интим:" + (пометка or "")
    if сборщик and затея and затея.get("type") != "dating" and any(_СВИДАНИЕ.search(str(x or "")) for x in said) \
            and not _ОТМЕНИТЬ_ВСЁ.search(said[-1]):
        затея = dict(затея, type="dating", category="dating",
                     title={"ru": "Сходить на свидание", "en": "Go on a date", "es": "Tener una cita"}.get(lang, затея.get("title")))
        затея["activity"] = затея["title"]
        пометка += ":свидание"
    if _эхо(ответ, said):
        # Эхо при годной карточке: попытку не бракуем (окно верное), пустой ответ ниже станет «Понял — X.».
        ответ = "" if затея else _ЧЕМ_ЗАНЯТЬСЯ.get(lang, _ЧЕМ_ЗАНЯТЬСЯ["ru"])
    пометка = "→".join(пометки) if len(пометки) > 1 else (пометка or "")
    if затравка:
        пометка = "seed:" + пометка
    if not сборщик and затея and рассказ_о_прошлом(said[-1], B):
        затея, пометка = None, пометка + ":рассказ"
    if not сборщик and not затея and _ПОНЯЛ_ЗАТЕЯ.match(str(ответ or "").strip()):
        # «Понял — сходить на латте.» без окна (снимок владельца 26.09.2026, 18:30): модель списала форму нашей
        # заготовки из истории. Затеи нет — объявлять её нельзя; остаток ответа, если он есть.
        ответ = _ПОНЯЛ_ЗАТЕЯ.sub("", str(ответ).strip(), count=1).strip() or _ПОНЯЛ[lang]
        пометка += ":заготовка без окна"
    if сборщик and not затея and not отмена:
        # КАРТОЧКА ИЗ СЛОВ ЧЕЛОВЕКА. В сборщике человек уже нажал «Создать интент», а модель на «хочу
        # погулять» дважды спрашивала «с кем?» без карточки — экран оставался пустым (живая проверка
        # 24.09.2026). Последний рубеж: занятие, названное им самим, проходит тот же _затея, что и
        # карточка модели (отказы, обращение к агенту, сито чипов).
        своя = _карточка_из_слов(said, B, lang, затравка=затравка)
        if своя:
            з2, п2 = _затея(своя, msgs, profile, signals, lang, B)
            if з2 and not з2.get("needs_activity"):
                затея, ответ = з2, _готово(з2, msgs, lang)
                пометка += ":из слов"
    if отмена and not затея:
        # ОТМЕНА В СБОРЩИКЕ. Ход без карточки оставляет прежнюю на экране, и после «забей / ничего не
        # надо» она уходила в поиск (ru-cases-11, ru-mixed-yes-no-12 на стенде 24.09.2026). Модель
        # ставит "cancel": true, а код верит ей, только если в реплике нет нового занятия.
        пометка += ":отмена"

    # СЛУЖЕБНЫЙ МУСОР ПОСЛЕ ПЕРЕСПРОСА: «Вот исправленный вариант:», «Here is the corrected card» — модель
    # отвечает записке, а не человеку (ru-phrases-03 на стенде шага 3). Такие фразы вырезаются.
    ответ = _МЕТА.sub("", ответ).strip()
    if _ПОХВАЛА.search(ответ):
        без_похвалы = _ПОХВАЛА.sub("", ответ).strip()
        if len(без_похвалы) >= 15:
            ответ = без_похвалы
    if len(_ОЦЕНКА.findall(ответ)) >= 2 and _ВОСКЛИЦАНИЕ.search(ответ):
        остаток = _ВОСКЛИЦАНИЕ.sub("", ответ).strip()
        if len(остаток) >= 10:
            ответ = остаток[:1].upper() + остаток[1:]
    if _САМ_ЗОВЁТ.search(ответ):
        ответ = _САМ_ЗОВЁТ.sub("", ответ).strip() or (
            _готово(затея, msgs, lang) if (затея and сборщик) else ("" if затея else _ПОНЯЛ[lang]))
    if вызовов > 1:
        ответ = _ИЗВИНЕНИЕ.sub("", ответ).strip() or ответ
        # «Давай исправлюсь — …», «here's the corrected one» — тоже ответ записке, а не человеку.
        ответ = "".join(x for x in _ПРЕДЛ.findall(ответ)
                        if not re.search(r"(?iu)исправ\w*|correct\w*|correg\w*", x)).strip() or ответ
    if затея and ответ:
        # ОЦЕНКА ПРИ КАРТОЧКЕ. После 4b похвала осталась в 37% ответов, и почти вся — там, где карточка
        # уже есть (стенд 4b: 270 из 331): «Хорошая идея — кофе всегда поднимает настроение», «звучит как
        # отличный повод для общения». Карточка и есть ответ: оценочное предложение вырезается целиком,
        # вопрос остаётся. Ничего не осталось — в чате пустой ответ (окно сразу), в сборщике своя фраза.
        # Стоит ПОСЛЕ вырезания извинений: иначе от «Извини, я запутался. Скалодром — это здорово!»
        # оставалось одно извинение.
        остаток = "".join(x for x in _ПРЕДЛ.findall(ответ)
                          if re.search(r"[?？]\s*$", x.strip()) or not _ОЦЕНКА_ПРЕДЛ.search(x)).strip()
        if остаток != ответ.strip():
            ответ = остаток if len(остаток) >= 10 else (_готово(затея, msgs, lang) if сборщик else "")
    # ЧИСТКА ЗАЯВЛЕНИЙ «ищу / создаю» — на ответе модели, после выбора итога.
    if заявляет_поиск(ответ):
        чисто = без_заявок(ответ)
        if len(чисто) >= 20:
            ответ = чисто
        elif сборщик and затея:
            # Пустым ответ сборщика не бывает: запасной путь телефона считает его обрывом связи.
            ответ = _готово(затея, msgs, lang)
        elif сборщик:
            # Карточки нет и после переспроса. Заготовка neutral_ready тут врёт («выбери время и место,
            # и я поищу») — кнопки дальше на экране нет. Остаток без заявлений, если он есть; иначе
            # коротко и без обещаний (проверка шага 2, 24.09.2026). Голое «Понял.» — только если нечего
            # сказать по делу: карточка на экране остаётся, дальше время и место.
            ответ = чисто or (_ЧТО_ЗАПИСАТЬ[lang] if затравка else _КАК_ЕСТЬ[lang])
        elif затея:
            ответ = ""                            # окно и есть ответ — контракт V1 и телефона
        else:
            # Без карточки и без окна «ищу» — ложь. Раньше ход отдавался V1, но и у него на этом месте
            # «С радостью найду — а чем хочешь заняться?» и «Тогда ищи, с кем провести время» (снимки
            # владельца 24.09.2026, 16:46). Честный ответ — спросить, чем заняться.
            ответ = _ЧЕМ_ЗАНЯТЬСЯ[lang]
    # В СБОРЩИКЕ НЕ ЗОВУТ ИСКАТЬ И НЕ СПРАШИВАЮТ ПРИ КАРТОЧКЕ. Человек уже создаёт затею: «А хочешь найти
    # кого-то…?» (снимок владельца 24.09.2026, 16:45) и вопросы под готовой карточкой (52 на двух
    # прогонах, каталог шага 4) — лишнее. Вопрос остаётся, когда карточки нет или слово непонятно.
    if сборщик and ответ:
        предл = _ПРЕДЛ.findall(ответ)
        без_зова = "".join(x for x in предл if not _ЗОВ.search(x)).strip()
        if len(без_зова) >= 10:
            ответ = без_зова
        if затея:
            try:
                ответ = B.strip_trailing_question(ответ) or ответ
            except Exception:
                pass
            if re.search(r"[?？]\s*$", ответ):
                ответ = _готово(затея, msgs, lang)
    # ПОВТОРНЫЙ ЗОВ. Агент уже предлагал найти компанию, человек не согласился и нового занятия не
    # назвал — хвостовое предложение срезается (функции V1). «С кем бы ты хотел…?» без глагола поиска
    # сюда не попадает — это держит промпт.
    if not сборщик and not затея and ответ:
        last = said[-1]
        try:
            # Зов искать — один на разговор, пока человек не назвал новое занятие: смотрим ВСЕ прежние
            # реплики агента, а не одну (каталог шага 4: 8–10 разговоров с двумя и более зовами).
            звал = any(_ЗОВ.search(str(m.get("content") or "")) for m in msgs[:-1] if m.get("role") == "assistant")
            if звал and not B._is_affirmation(last) and not новое_занятие(said, B):
                без_зова = "".join(x for x in _ПРЕДЛ.findall(ответ) if not _ЗОВ.search(x)).strip()
                ответ = без_зова if len(без_зова) >= 10 else (B.strip_trailing_offer(ответ) or ответ)
        except Exception:
            pass
    # Третий рубеж V1: тема опасная, но спрашивали не способ — проверяем готовый текст.
    if вердикт == "care" and B.safety.looks_operational(ответ, домен):
        return B.REFUSE_REPLY.get(lang, B.REFUSE_REPLY["en"]), None, lang, "отказ по тексту", вызовов
    if затея and B.promises_a_meeting(ответ):
        ответ = _готово(затея, msgs, lang) if сборщик else ""
    if not сборщик and затея and not str(ответ or "").strip():
        # ПУСТОЙ ОТВЕТ ПРИ ОКНЕ ТЕРЯЛ ЗАТРАВКУ. Телефон кладёт в историю только непустой ответ, а сборщик
        # узнаёт первый ход по двум репликам агента подряд. С 4c (оценка при карточке вырезается) окно с
        # пустым ответом выезжало в 66–72 случаях из ~108 на прогон стенда (у 4a — 13), затравка не
        # узнавалась в ~60, переспроса на первом ходу не было — 8 из 13 пустых сборщиков. Короткое «Понял
        # — сходить в кино.» и есть ответ: окно выезжает под ним так же (вопроса в нём нет).
        ответ = _ответ_окна(затея, msgs, lang)
    if затея and _было_у_агента(ответ, msgs):
        # ПОВТОР СВОЕЙ РЕПЛИКИ. Два окна подряд с тем же заголовком давали одно и то же «Понял — X.», а
        # модель копировала его из истории (повторов на стенде 4d 9 и 13 против 7 и 7 у 4c2). При карточке
        # берётся следующий вариант — «Хорошо.», «Понял.».
        ответ = _готово(затея, msgs, lang) if сборщик else _ответ_окна(затея, msgs, lang)
    if сборщик and not затея and "свидание без занятия" in (пометка or "") and "?" not in str(ответ or ""):
        # СВИДАНИЕ БЕЗ ЗАНЯТИЯ, А ВОПРОСА НЕТ. Модель после переспроса иногда отвечала похвалой («Perfecto,
        # suena como una idea maravillosa.») — человек видел пустой сборщик и не знал, что сказать дальше.
        # Поиску нужно занятие встречи, поэтому вопрос о нём обязателен (мерка 26.09.2026).
        ответ = (str(ответ or "").strip() + " " + _ВОПРОС_СВИДАНИЯ.get(lang, _ВОПРОС_СВИДАНИЯ["ru"])).strip()
    return ответ, затея, lang, пометка, вызовов


_ВОПРОС_СВИДАНИЯ = {"ru": "Как хочешь провести свидание — кофе, прогулка, ужин или что-то другое?",
                    "en": "How would you like to spend the date — coffee, a walk, dinner or something else?",
                    "es": "¿Cómo te gustaría pasar la cita: un café, un paseo, una cena u otra cosa?"}


_ПОНЯЛ = {"ru": "Понял.", "en": "Got it.", "es": "Entendido.",
          "de": "Verstanden.", "fr": "Compris.", "it": "Capito.", "pt": "Percebido."}
_ХОРОШО = {"ru": "Хорошо.", "en": "Okay.", "es": "Vale.", "de": "Okay.", "fr": "D’accord.", "it": "Va bene.", "pt": "Está bem."}
# Ответ чата при окне, когда от ответа модели ничего не осталось (см. «ПУСТОЙ ОТВЕТ ПРИ ОКНЕ»).
_ОКНО_ОТВЕТ = {"ru": "Понял — %s.", "en": "Got it — %s.", "es": "Entendido — %s.",
               "de": "Verstanden — %s.", "fr": "Compris — %s.", "it": "Capito — %s.", "pt": "Percebido — %s."}
# Первый ход сборщика без карточки: на экране НИЧЕГО нет, «оставим как есть» тут ложь.
_ЧТО_ЗАПИСАТЬ = {"ru": "Чем хочется заняться? Назови занятие — и соберу затею.",
                 "en": "What would you like to do? Name the activity and I'll put the plan together.",
                 "es": "¿Qué te apetece hacer? Dime la actividad y preparo el plan.",
                 "de": "Worauf hast du Lust? Nenn mir die Aktivität, dann stelle ich den Plan zusammen.",
                 "fr": "Qu’est-ce que tu as envie de faire ? Dis-moi l’activité et je prépare le plan.",
                 "it": "Cosa ti va di fare? Dimmi l’attività e preparo il piano.",
                 "pt": "O que te apetece fazer? Diz-me a atividade e eu preparo o plano."}
# Готово: без «я поищу» и без «дальше выбери время и место» — время и место человек ставит руками на
# следующих экранах, говорить о них Буди незачем (владелец 26.09.2026). «Записал», а не «Понял»: в чате
# над окном уже стояло «Понял — X.», и сборщик повторял его слово в слово.
_ГОТОВО = {"ru": "Записал — %s.", "en": "Noted — %s.", "es": "Apuntado — %s.",
           "de": "Notiert — %s.", "fr": "C’est noté — %s.", "it": "Annotato — %s.", "pt": "Anotado — %s."}
_КАК_ЕСТЬ = {"ru": "Хорошо, оставим как есть.", "en": "Okay, let's keep it as it is.", "es": "Vale, lo dejamos así.",
             "de": "Okay, wir lassen es so.", "fr": "D’accord, on laisse comme ça.", "it": "Va bene, lasciamo così.",
             "pt": "Está bem, deixamos assim."}


def _было_у_агента(текст, msgs):
    т = str(текст or "").strip()
    return bool(т) and any(str(m.get("content") or "").strip() == т for m in (msgs or []) if m.get("role") == "assistant")


def _первый_новый(варианты, msgs):
    """Первый вариант, которого агент в разговоре ещё не говорил; если сказаны все — последний."""
    for v in варианты:
        if v and not _было_у_агента(v, msgs):
            return v
    return варианты[-1]


def _готово(затея, msgs, lang):
    """Запасная реплика сборщика при карточке, без повторов за разговор: «Записал — X.», потом «Понял.»,
    потом «Хорошо.»."""
    t = _с_маленькой((затея or {}).get("title"))
    полная = (_ГОТОВО[lang] % t) if t else ""
    return _первый_новый([полная, _ПОНЯЛ[lang], _ХОРОШО[lang]], msgs)


def _ответ_окна(затея, msgs, lang):
    """Ответ чата при окне, когда от ответа модели ничего не осталось: «Понял — X.», потом «Хорошо.», «Понял.»."""
    lang = lang if lang in _ОКНО_ОТВЕТ else "ru"
    t = _с_маленькой((затея or {}).get("title"))
    return _первый_новый([(_ОКНО_ОТВЕТ[lang] % t) if t else "", _ХОРОШО[lang], _ПОНЯЛ[lang]], msgs)
# АГЕНТ ЗОВЁТ С СОБОЙ: «давай просто посидим на мосту и покурим сигары» (снимок владельца 24.09.2026,
# 17:23) — агент никуда не ходит. Промпт это запрещает; держит код.
_САМ_ЗОВЁТ = re.compile(
    r"(?iu)(?:^|(?<=[.!?…]\s))[^.!?…\n]*\bдавай(?:те)?\s+(?:просто\s+|тогда\s+|лучше\s+|вместе\s+)?"
    r"(?:посидим|сходим|пойд[её]м|поиграем|сыграем|выпьем|покурим|погуляем|прогуляемся|потанцуем|"
    r"съездим|поедем|встретимся|покатаемся|поплаваем|побегаем|поедим)\b(?!\s+в\s+(?:слова|города|ассоциаци|угадайк))"
    r"[^.!?…\n]*[.!?…]*\s*")
_ЧЕМ_ЗАНЯТЬСЯ = {"ru": "Чем хочется заняться — есть что-то на примете?", "en": "What would you like to do — anything in mind?",
                 "es": "¿Qué te apetece hacer? ¿Tienes algo en mente?",
                 "de": "Worauf hast du Lust — hast du schon etwas im Kopf?",
                 "fr": "Qu’est-ce que tu as envie de faire — tu as une idée en tête ?",
                 "it": "Cosa ti va di fare — hai già qualcosa in mente?",
                 "pt": "O que te apetece fazer — tens alguma coisa em mente?"}
# Извинение за невидимую человеку попытку — вырезается на ходах с переспросом.
_ИЗВИНЕНИЕ = re.compile(r"(?iu)(?:^|(?<=[.!?…]\s))(?:ой,?\s+)?(?:извини(?:те)?|прости(?:те)?|sorry|perd[oó]n)[^.!?…\n]{0,60}?"
                        r"(?:запутал\w*|ошиб\w*|упростил\w*|исправ\w*|сбил\w*|confus\w*|mistake|correct\w*|equivoqu\w*)[^.!?…\n]*[.!?…]*\s*")
# ПОХВАЛА ЧЕЛОВЕКУ: «Хорошо, что ты хочешь бегать по утрам!» сразу после «бег меня подбешивает» — 13%
# ответов на стенде 3f (каталог шага 4). Промпт это запрещает; страховка — вырезать предложение.
_ПОХВАЛА = re.compile(r"(?iu)(?:^|(?<=[.!?…]\s))(?:хорошо|здорово|отлично|круто|классно|замечательно|рад[а]?|приятно|"
                      r"it'?s\s+(?:great|good|nice)|qu[eé]\s+bien)\s*,?\s+(?:что|that)\s+(?:ты|у\s+тебя|you)\b[^.!?…\n]*[.!?…]*\s*")
# Одно оценочное слово дважды: «Отлично, кофе — это всегда отличная идея!» (27 ответов на стенде 3f).
_ВОСКЛИЦАНИЕ = re.compile(r"(?iu)^(?:отлично|здорово|классно|круто|супер|great|awesome|genial|perfecto)\s*[,!.—–-]+\s*")
_ОЦЕНКА = re.compile(r"(?iu)отличн|здоров|классн|крут|великолепн|great|awesome|genial|perfect")
# Оценочное предложение — для вырезания при карточке (см. «ОЦЕНКА ПРИ КАРТОЧКЕ» в ход).
_ОЦЕНКА_ПРЕДЛ = re.compile(r"(?iu)\b(?:отличн\w*|здорово|классн\w*|прекрасн\w*|замечательн\w*|потрясающ\w*|круто|чудесн\w*|"
                          r"великолепн\w*|хорош(?:ая|ий|ее|ую)\s+(?:идея|выбор|план|мысль|повод|способ)|звучит|"
                          r"great|awesome|amazing|lovely|sounds|nice|genial|estupend\w*|fant[aá]stic\w*|suena|"
                          r"buena\s+(?:idea|opci[oó]n)|qu[eé]\s+bien)")


_МЕТА = re.compile(r"(?imu)^[ \t]*(?:вот|here(?:'s|\s+is)|aqu[ií]\s+(?:est[aá]|tienes))\s+(?:исправленн\w*|обновл[её]нн\w*|"
                   r"corrected|updated|fixed|la\s+versi[oó]n\s+corregida)\b[^\n.!?]*[:.!]?[ \t]*$\n?")
_СТОРОЖА = ("возраст", "отказ", "selfharm", "вред", "отказ по тексту")


def _с_маленькой(t):
    t = str(t or "").strip()
    return t[:1].lower() + t[1:] if t else ""


def serve(handler, route, body, B):
    """Ответить на /chat или /intent-build. True — ответ ушёл; False — пусть отвечает V1."""
    t0 = time.time()
    profile = body.get("profile") if isinstance(body.get("profile"), dict) else {}
    signals = body.get("signals") if isinstance(body.get("signals"), dict) else {}
    сборщик = route == "/intent-build"
    try:
        ответ, затея, lang, пометка, вызовов = ход(body.get("messages"), profile, signals, body.get("lang"), B, сборщик=сборщик)
    except Exception as e:
        print("[v2] %s брак, отвечает V1: %s" % (route, str(e)[:160]), flush=True)
        return False
    if сборщик:
        out = {"reply": ответ, "valid": True, "ready": bool(затея), "intent": затея, "lang": _язык_клиенту(lang, body.get("lang")),
               "hints": [], "v2": True}
        # Пустой ответ сборщика телефон на запасном пути читает как обрыв связи — не отдаём его.
        if not ответ:
            out["reply"] = B.neutral_ready(_с_маленькой((затея or {}).get("title")), lang)
    else:
        if затея:
            # Окно затеи телефон не выдвигает под вопросом — снимаем хвостовой вопрос, как V1.
            ответ = B.strip_trailing_question(B.strip_trailing_offer(ответ)) or ответ
            if re.search(r"[?？]\s*$", ответ):
                ответ = ""
            if not str(ответ or "").strip():
                # Тот же «Понял — …», что и в ход(): от ответа после вырезания оценки часто остаётся один
                # вопрос («Хочешь, найду компанию?»), и он обнулялся уже здесь (ревью 4d).
                ответ = _ответ_окна(затея, нормализовать(body.get("messages")), lang)
        sig = dict(signals)
        if затея:
            ключи = [t for t in (затея.get("topics") or []) if re.match(r"^[a-z0-9 &'-]+$", str(t))]
            if ключи:
                sig["interest"] = ключи[0]
            sig["v2_card"] = {"title": затея.get("title"), "chips": затея.get("topics") or []}
        out = {"reply": ответ, "signals": sig, "lang": _язык_клиенту(lang, body.get("lang")), "match": bool(затея), "intent": затея,
               "matches": [], "tool_call": None, "category": (затея or {}).get("category"), "v2": True}
    # ОТВЕТ СТОРОЖА СНИМАЕТ КАРТОЧКУ. В сборщике ход без карточки оставляет на экране прежнюю вместе
    # с кнопкой «дальше»: после «мне 15» или отказа по безопасности она уходила бы в поиск. Телефон
    # снимает её только по refused/valid:false (create.tsx settle, buddy.tsx finish) — как у V1.
    if сборщик and str(пометка).endswith(":отмена"):
        out["valid"] = False
    if пометка in _СТОРОЖА:
        out["refused"] = пометка
        if сборщик:
            out["valid"] = False
    # Причина и число вызовов — в ответ и в журнал: без них «модель не написала карточку» и «код её
    # отбраковал» приходилось угадывать по секундам хода. Телефон лишних полей не читает.
    out["v2_note"], out["v2_calls"] = пометка, вызовов
    print("[v2] %s %.1fс заголовок=%r чипы=%s пометка=%s вызовов=%d" % (
        route, time.time() - t0, (затея or {}).get("title"), (затея or {}).get("topics"), пометка, вызовов), flush=True)
    if not body.get("stream"):
        try:
            B.send_json(handler, 200, out)
        except Exception as e:
            print("[v2] клиент ушёл: %s" % str(e)[:100], flush=True)
        return True
    # ПОТОК: только done. delta и done одной пачкой заставляли экран печатать ответ дважды;
    # путь «ответ без delta» телефон уже знает по ранней просьбе V1 и печатает ответ один раз.
    try:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("X-Accel-Buffering", "no")
        handler.send_header("Connection", "close")
        handler.end_headers()
        out["replaced"] = False
        handler.wfile.write(("event: done\ndata: %s\n\n" % json.dumps(out, ensure_ascii=False)).encode("utf-8"))
        handler.wfile.flush()
    except Exception as e:
        print("[v2] клиент ушёл посреди ответа: %s" % str(e)[:100], flush=True)
    return True
