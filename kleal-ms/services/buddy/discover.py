# -*- coding: utf-8 -*-
"""Ветка «помоги разобраться»: короткий опросник сценами вместо вопросов о себе.

ЗАЧЕМ ОТДЕЛЬНЫЙ МОДУЛЬ. Человек нажал «Добавить интерес» и не смог назвать ни одного — значит
вопрос «чем любишь заниматься?» ему уже не помог. Спрашивать надо не про ярлыки («ты интроверт?»),
а про поступки: «пятница, восемь вечера, планов нет — что бы сделал?». На сцену отвечать легко, и
ответ честнее самоописания, потому что человек выбирает не кем себя считает, а что бы сделал.

ЗДЕСЬ НЕТ СЕТИ. Модуль строит промпт и разбирает ответ; вызов модели делает ручка. Так весь разбор
и все сторожа проверяются офлайн — стендом, без живого сервиса и без пяти секунд на ход.

ЧЕТЫРЕ СТОРОЖА, каждый от известной болезни модели:
  1. БАНАЛЬНОСТЬ. «Какие у тебя хобби?» — ровно тот вопрос, от которого человек сюда и ушёл.
  2. АБСТРАКЦИЯ В ВАРИАНТАХ. «Общение», «спорт», «отдых» — это ярлыки, а не продолжения сцены;
     тот же класс слов, что вычищали из интересов миграцией (market, design, language).
  3. ПОВТОР СЦЕНЫ. Модель охотно предлагает те же варианты другими словами, и опрос топчется.
  4. ВЫДУМАННОЕ ОБЪЯСНЕНИЕ. В подборке `why` обязана опираться на РЕАЛЬНЫЙ ответ человека —
     иначе это гороскоп. Проверяется пересечением слов с тем, что он выбирал.

Конечность: не больше MAX_SCENES сцен, дальше подборка выдаётся принудительно. Модель, которой
дали импровизировать, спрашивает бесконечно — это уже видели в построителе интентов.
"""
import json
import os
import random
import re
import time

MAX_SCENES = 4
POOL_SIZE = 40                 # сколько живых интересов показываем модели на выбор
POOL_TTL = 300.0               # секунд; популяция меняется медленнее, чем идёт разговор
WIDGETS = ("cards", "pair", "multi")
_SIZE = {"cards": (3, 3), "pair": (2, 2), "multi": (4, 6)}

# Зачины, ради ухода от которых ветка и существует.
_BANAL = re.compile(
    r"(?i)(как(ие|ое)\s+(у\s+теб[яя]\s+)?(хобби|увлечени)|чем\s+(ты\s+)?(любишь|нравится)\s+заниматься"
    r"|ты\s+(интроверт|экстраверт)|расскажи\s+о\s+себе|что\s+теб[яе]\s+интересует"
    r"|what.{0,12}(are your hobbies|do you like to do)|are you an introvert"
    r"|cu[áa]les son tus (aficiones|hobbies)|qu[ée] te gusta hacer)")

# СКУЧНОЕ. Человек, не сумевший назвать интерес, УЖЕ перебрал очевидное: про парки и музеи он
# знает, потому и пришёл. Модель по умолчанию выдаёт статистический центр — «пойти в парк»,
# «посмотреть фильм», «почитать книгу», — и опросник превращается в перечисление известного.
# Список найден на живом прогоне: ровно эти варианты выдавались сценам подряд.
_DULL = re.compile(
    r"(?i)^(пойти|сходить|посетить|погулять|почитать|посмотреть|поехать|заняться)?\s*"
    r"(в\s+)?(парк|музей|кино|театр|бар|кафе|ресторан|книг\w*|фильм\w*|сериал\w*|"
    r"спортзал|прогулк\w*|путешеств\w*)\s*$"
    r"|^(go|going)\s+(to\s+)?(the\s+)?(park|museum|cinema|movies|bar|cafe|gym|theatre|theater)\s*$"
    r"|^(read(ing)?\s+a?\s*book|watch(ing)?\s+a?\s*(movie|film|series)|take\s+a\s+walk)\s*$")

# Голые абстракции: вариант сцены обязан быть поступком, а не областью жизни.
_ABSTRACT = {
    "общение", "спорт", "отдых", "музыка", "искусство", "культура", "еда", "путешествия",
    "развитие", "саморазвитие", "хобби", "досуг", "движение", "творчество", "природа",
    "socializing", "sport", "sports", "rest", "music", "art", "culture", "food", "travel",
    "hobby", "leisure", "creativity", "nature", "self-development",
    "socializar", "deporte", "descanso", "música", "arte", "cultura", "comida", "viajes",
}


# Обороты, которыми модель читает характер вместо того, чтобы показать замеченное.
_HOROSCOPE = re.compile(
    r"(?i)(ты\s+человек\s|у\s+теб[яя]\s+интерес\s+к\s+активност|тебе\s+нравится\s+всё,"
    r"|похоже,?\s+ты\s+(из\s+тех|человек)|ты\s+(часто|всегда|обычно)\s+выбираешь"
    r"|чтобы\s+(расслабиться|выразить\s+себя|отдохнуть)$"
    r"|you\s+(are|tend\s+to\s+be)\s+(a\s+)?(creative|social|curious|thoughtful)"
    r"|you\s+(often|usually|always)\s+(choose|pick)|eres\s+una\s+persona)")

# Нейтральная подводка, когда закрывающую фразу пришлось снять: подборка ниже говорит сама.
_SUMMARY_LEAD = {"ru": "Вот что складывается из твоих ответов.",
                 "en": "Here is what your answers add up to.",
                 "es": "Esto es lo que sale de tus respuestas."}


# ---------------------------------------------------------------- живой пул интересов
_POOL = {"at": 0.0, "items": []}


def _pool_path():
    return os.environ.get("KLEAL_USERS",
                          os.path.join(os.path.dirname(os.path.dirname(
                              os.path.dirname(os.path.abspath(__file__)))), "users.json"))


def live_pool():
    """Интересы, которые у людей РЕАЛЬНО есть, — редкие вперёд.

    Подборку строим из них, а не из фантазии модели, по двум причинам сразу. Первая: живые
    формулировки конкретны там, где модель обобщает, — «organ concerts», «переплётное дело»,
    «варю пиво на кухне» против «музыка», «творчество», «готовка». Вторая важнее: интерес,
    которого нет НИ У КОГО, бесполезен — подбор по нему не найдёт никого, и предложение окажется
    обещанием, которое продукт не сдержит.

    Редкие вперёд намеренно: человек, не назвавший интерес, уже знает про кофе и прогулки. Смысл
    опросника — показать то, до чего он сам бы не додумался.
    """
    now = time.time()
    if _POOL["items"] and now - _POOL["at"] < POOL_TTL:
        return _POOL["items"]
    try:
        with open(_pool_path(), encoding="utf-8") as f:
            users = (json.load(f) or {}).get("users") or []
    except Exception:
        return _POOL["items"]
    freq = {}
    for u in users:
        for w in (u.get("interests") or []):
            w = _norm(w)
            if w:
                freq[w] = freq.get(w, 0) + 1
    known = _understood()
    items = []
    for w, n in freq.items():
        if len(w) < 4 or (" " not in w and w in _ABSTRACT):
            continue
        if _DULL.search(w) or _NOISE.search(w) or _NOT_INTEREST.search(w):
            continue
        # ПОНЯТОЕ, А НЕ ЛЮБОЕ. В строках людей полно обрывков прежних способов записи: «barrio»,
        # «black and white», «empiezo cursos y no los termino». Признак понятости уже посчитан —
        # слово либо переведено словарём подписей, либо резолвится в канон. Фильтр срезает
        # популяцию с 1360 до 610, и остаток предметен: vermut, typesetting, mosaic art.
        if w not in known:
            continue
        items.append((n, w))
    items.sort(key=lambda x: (x[0], x[1]))         # редкие вперёд, дальше по алфавиту — стабильно
    _POOL.update(at=now, items=[w for _, w in items])
    return _POOL["items"]


# Мусор, доставшийся от прежних способов записи: обрывки фраз и служебные слова.
_NOISE = re.compile(r"(?i)^(i\s|я\s|хочу|want\b|free\b|small\b|media$|home\s|six\b|more\b"
                    r"|closing\b|black and white$|homework$|venture$|topic chat$)")
# Телесная надобность — не увлечение. Тот же класс слов, что сторожит запись в interests_chat.
_NOT_INTEREST = re.compile(r"(?i)(drink|water|sleep|\beat\b|breath|\brest\b|пить|спать|дышать|кушать)")


def _understood():
    """Слова, которые система ПОНИМАЕТ: есть подпись в словаре или узел в каноне."""
    out = set()
    try:
        import interest_i18n as ii
        out |= {_norm(k) for k in (ii._load() or {})}
    except Exception:
        pass
    try:
        import sys as _s
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if root not in _s.path:
            _s.path.insert(0, root)
        from matching_core.taxonomy import canonical as C
        out |= {_norm(a) for a in C.ALIAS}
    except Exception:
        pass
    return out


def sample_pool(profile, seed, n=POOL_SIZE):
    """`n` живых интересов, которых у человека ещё нет. Порядок стабилен внутри разговора."""
    have = {_norm(x) for x in ((profile or {}).get("interests") or [])}
    items = [w for w in live_pool() if w not in have]
    if not items:
        return []
    rnd = random.Random(seed)
    head = items[:max(n * 6, 120)]                 # берём из редкого края, но не из одного хвоста
    rnd.shuffle(head)
    return head[:n]


# ДОГАДКА, ВЫДАННАЯ ЗА НАБЛЮДЕНИЕ. Цитата настоящая, а вывод придуман: «Позвал бы друзей на обед,
# ВОЗМОЖНО, с питомцами» — про питомцев человек не говорил ни разу. Проверить сам вывод машиной
# нельзя, но такие натяжки почти всегда прячутся за оговоркой; её и ловим.
_HEDGE = re.compile(r"(?i)(возможно|может быть|наверн\w+|похоже,|perhaps|maybe|probably|might\s+"
                    r"|quiz[áa]s|tal vez)")


def _family_of(word):
    """Семья канона для интереса — ей меряется разнообразие подборки."""
    try:
        import sys as _s
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if root not in _s.path:
            _s.path.insert(0, root)
        from matching_core.taxonomy import canonical as C
        nid = C.resolve_node(word)
        return (C.NODES.get(nid) or {}).get("family") if nid else None
    except Exception:
        return None


def _norm(s):
    return " ".join(str(s or "").strip().lower().split())


def _words(s):
    return {w for w in re.findall(r"[\wЀ-ӿ]+", str(s or "").lower()) if len(w) > 3}


def scenes_so_far(messages):
    """Сколько сцен уже показано. Считаем по репликам агента: ручка без состояния."""
    return sum(1 for m in (messages or []) if isinstance(m, dict) and m.get("role") == "assistant")


def answers_of(messages):
    """Что человек реально выбирал — тап по карточке приходит обычной репликой."""
    return [str(m.get("content", "")) for m in (messages or [])
            if isinstance(m, dict) and m.get("role") == "user" and str(m.get("content", "")).strip()]


def seen_options(messages):
    """Слова уже показанных вариантов — чтобы новая сцена не пересказывала прежнюю.

    Берём из реплик агента: в истории они лежат текстом сцены, а варианты человек выбирал
    своими репликами. Пересечение считаем по обоим.
    """
    out = set()
    for m in (messages or []):
        if isinstance(m, dict) and m.get("role") in ("assistant", "user"):
            out |= _words(m.get("content"))
    return out


PROMPT = """You run a SHORT discovery questionnaire for a social app. The person just tried to add
an interest and could not name one, so asking "what are your hobbies" is exactly what already failed.

Ask about SITUATIONS, not labels. A good turn sets a concrete scene and offers concrete things the
person might DO in it. Never ask what kind of person they are.

GOOD:  "Пятница, восемь вечера, планов нет." -> ["Ушёл бы гулять по городу", "Позвал бы двоих домой",
        "Остался бы один и не жалел"]
BAD:   "Какие у тебя увлечения?" / options like "Общение", "Спорт", "Отдых"

A scene needs ONE concrete detail that makes it real — a time, a weather, a thing on the table.
"Воскресенье утром" is a calendar entry; "Воскресенье, полдень, ты выспался впервые за неделю" is
a scene. Options are what the person WOULD DO, phrased the way they would say it to a friend —
"Позвал бы двоих домой", not "Организовать ужин".

Address the person informally — ты / tú / you, never вы or usted. Kleal talks like a friend.

Reply in __LANGNAME__. Answer with ONE JSON object, no other text.

While you still need signal (at most __MAX__ scenes):
  {"reply": "<the scene, one or two sentences, no question mark needed>",
   "scene": {"widget": "cards|pair|multi",
             "options": [{"label": "<a concrete thing they would DO, max 6 words>"}, ...]}}
  widget "cards" = exactly 3 options, "pair" = exactly 2, "multi" = 4 to 6 (they may pick several).
  Vary the widget between turns. Never repeat a scene or options you already used.

NEVER offer these as options — the person already knows they exist, that is why they could not
name an interest: going to a park, a museum, a cinema, a bar, a gym; reading a book; watching a
film or a series; taking a walk; travelling. If your option would fit ANY person in the city, it
is the wrong option. Say the small concrete thing instead: "Досмотрел бы сериал за ночь", not
"Посмотреть фильм".

When you can name real interests (or after __MAX__ scenes), STOP asking and answer instead:
  {"reply": "<one sentence naming the PATTERN you saw, pointing at their actual choices>",
   "suggest": [{"key": "<english interest key, max 4 words, specific>",
                "label": "<the same interest in __LANGNAME__>",
                "why": "<why THIS person — quote or paraphrase what they actually chose>"}, ...]}
  Give 3 or 4 suggestions. Every "why" must refer to an actual answer of theirs. Never invent a
  trait they did not show. If you catch yourself writing "maybe" or "possibly" in a `why`, the
  suggestion is a guess — drop it and pick one you can point at.
  CHOOSE ONLY FROM THE LIST under POOL below, copying the `key` exactly as written there. Those
  are interests real people in this city actually have — an interest nobody has finds nobody, and
  the whole point of the questionnaire is to name something they would not have thought of.
  Each suggestion must come from a DIFFERENT area of life. Four names for the same thing (photo
  editing, video, digital art, creative writing) is not a choice — keep one of those and spend
  the other slots on something else they showed.
  The closing line must NOT be a personality reading. "У тебя интерес к активностям, которые
  позволяют расслабиться" is a horoscope — it would fit anyone. "Ты трижды выбрал что-то делать
  руками, и ни разу — компанию побольше" points at what they did."""


def build_prompt(messages, profile, lang_name="Russian"):
    """(системный промпт, реплики для модели). Профиль даёт городу и языку контекст, не более."""
    sys_p = PROMPT.replace("__LANGNAME__", lang_name).replace("__MAX__", str(MAX_SCENES))
    n = scenes_so_far(messages)
    if n >= MAX_SCENES:
        sys_p += "\n\nYou have used all your scenes. Answer with `suggest` now — no more questions."
    # Пул отдаём с первой же сцены: он задаёт масштаб конкретики и модели, и подборке. Сид — по
    # длине истории, чтобы в пределах одного разговора список не прыгал от хода к ходу.
    pool = sample_pool(profile, seed=len(messages or []) and 1 or 0)
    if pool:
        sys_p += "\n\nPOOL (real interests of real people here — pick suggestions ONLY from this):\n" \
                 + "; ".join(pool)
    lines = []
    p = profile or {}
    city = str(p.get("area") or p.get("city") or "").strip()
    if city:
        lines.append("CITY: " + city)
    have = [str(x) for x in (p.get("interests") or []) if str(x).strip()][:8]
    if have:
        lines.append("ALREADY HAS (do not suggest these again): " + "; ".join(have))
    for m in (messages or [])[-12:]:
        if isinstance(m, dict) and str(m.get("content", "")).strip():
            lines.append(("User: " if m.get("role") == "user" else "Kleal: ") + str(m["content"]))
    return sys_p, "\n".join(lines)[-4000:]


def _clean_options(raw, widget, messages):
    """Варианты сцены: конкретные, не повторяющие прежние, в количестве по виджету."""
    lo, hi = _SIZE.get(widget, (3, 3))
    seen, out = seen_options(messages), []
    for it in (raw or [])[:hi]:
        label = it.get("label") if isinstance(it, dict) else it
        label = " ".join(str(label or "").split())[:48]
        if not label or _norm(label) in _ABSTRACT or _DULL.search(label):
            continue                       # абстракция или общеизвестное — не сцена, а перечисление
        w = _words(label)
        if w and len(w & seen) >= max(1, len(w)):
            continue                       # целиком из уже сказанного — пересказ прежней сцены
        if any(_norm(label) == _norm(o["label"]) for o in out):
            continue
        out.append({"id": "o%d" % (len(out) + 1), "label": label})
    return out if len(out) >= lo else []


def parse_turn(raw, messages, lang="ru", pool=None):
    """Ответ модели -> ход опросника. Сторожа применяются здесь, а не в ручке.

    Вернёт либо {"reply", "scene"}, либо {"reply", "suggest"}. Пустой словарь означает, что
    ход не годится и ручке следует ответить запасным текстом.
    """
    try:
        obj = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    except Exception:
        return {}
    if not isinstance(obj, dict):
        return {}
    reply = " ".join(str(obj.get("reply") or "").split())[:300]
    if not reply or _BANAL.search(reply):
        return {}

    sug = obj.get("suggest")
    if isinstance(sug, list) and sug:
        said = _words(" ".join(answers_of(messages)))
        fams = set()
        # Закрывающая фраза обязана указывать на сделанный выбор, а не читать характер. Гороскоп
        # («у тебя интерес к активностям, которые позволяют расслабиться») подошёл бы кому угодно
        # и обесценивает подборку, которая под ним. Замену берём из первого объяснения — оно по
        # построению опирается на реальный ответ.
        if _HOROSCOPE.search(reply):
            reply = ""
        out = []
        for it in sug[:4]:
            if not isinstance(it, dict):
                continue
            key = " ".join(str(it.get("key") or "").split()).lower()[:60]
            label = " ".join(str(it.get("label") or "").split())[:48] or key
            why = " ".join(str(it.get("why") or "").split())[:160]
            if not key or not why or _norm(key) in _ABSTRACT:
                continue
            if pool and key not in pool:
                continue                   # выдуманный интерес: подбор по нему никого не найдёт
            # Объяснение обязано опираться на сказанное человеком, иначе это гороскоп.
            if said and not (_words(why) & said):
                continue
            if _HEDGE.search(why):
                continue                   # оговорка выдаёт домысел, а не замеченное
            # РАЗНЫЕ ОБЛАСТИ, А НЕ ЧЕТЫРЕ ИМЕНИ ОДНОГО. На живом прогоне подборка вышла такой:
            # «редактирование фотографий», «создание видео», «цифровое искусство», «творческое
            # письмо» — выбирать тут не из чего, это одно и то же под разными именами. Семью
            # берём из канона: он ровно для этого и есть.
            fam = _family_of(key)
            if fam and fam in fams:
                continue
            if fam:
                fams.add(fam)
            out.append({"key": key, "label": label, "why": why})
        if len(out) < 2:
            return {}
        if not reply:
            reply = _SUMMARY_LEAD.get(lang, _SUMMARY_LEAD["en"])
        return {"reply": reply, "suggest": out}

    scene = obj.get("scene") if isinstance(obj.get("scene"), dict) else {}
    widget = str(scene.get("widget") or "cards").lower()
    if widget not in WIDGETS:
        widget = "cards"
    opts = _clean_options(scene.get("options"), widget, messages)
    if not opts:
        return {}
    return {"reply": reply, "scene": {"widget": widget, "options": opts}}
