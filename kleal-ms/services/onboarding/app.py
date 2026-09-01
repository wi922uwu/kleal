# -*- coding: utf-8 -*-
# Kleal onboarding-service — the profile-setup funnel (messenger UI + /api/onboarding/*).
# Carved from the pre-split monolith kleal_v2.py (onboarding half, lines 16-301 + the embedded HTML).
# Talks to llm-service over HTTP for every extract/reply/summary turn; holds NO model keys.
# Contract: ../../shared/contracts.md. Owner: Dev A.
import os, sys, json, re, threading, hashlib, hmac, time, base64, secrets
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "..", "..", "shared"), os.path.join(_HERE, "shared")):
    if os.path.isdir(_p) and _p not in sys.path: sys.path.insert(0, _p)
import kleal_lib as base                      # keyless shared helpers/prompts
import config                                  # the one topology table (ports/URLs/store paths)
import db                                      # хранилище: postgres или файл — решает KLEAL_DB
from llm_client import llm_complete           # the ONLY model access (HTTP -> llm-service)
from http_util import send, send_json, read_json
import mailer                                  # письмо с кодом: провайдер выбирается окружением
import interest_normalization as interest_norm
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = config.PORTS["onboarding"]
MODEL_ID = config.MODEL_ID


# ---------------------------------------------------------------- restructured gate (V2)
_chas, _cset, _cpath = base._chas, base._cset, base._cpath

CRIT_V2 = [
    ("Name",        lambda p: _chas(p, "name")),
    ("Age 18+",     lambda p: _cset(p, "ageVerified18")),
    ("Gender",      lambda p: _chas(p, "gender")),
    ("Photo",       lambda p: _cpath(p, "photoStatus") == "uploaded"),
    ("Languages",   lambda p: _chas(p, "languages.comfortable")),
    ("Interests",   lambda p: _chas(p, "interests.explicit")),
    ("Area",        lambda p: _chas(p, "geo.comfortableAreas") or _chas(p, "city")),
    ("Radius",      lambda p: _cset(p, "geo.maxDistanceKm")),
    ("Safety mode", lambda p: any(_cset(p, k) for k in ("safety.verifiedOnly", "safety.publicPlacesOnly", "safety.noPrivateLocations", "geo.publicPlacesOnly"))),
    ("Consent",     lambda p: _cset(p, "permissions.useProfileForMatching")),
    ("Adjacent",    lambda p: _cset(p, "permissions.allowAdjacentMatches")),
]

# ---- per-interest funnel plan: max 2 questions per interest (role + experience, then ONE domain detail)
def _v2_ints(p):
    v = _cpath(p, "interests.explicit") or []
    if isinstance(v, str): v = [v]
    return [x for x in v if isinstance(x, str) and x.strip()]

def _v2_roles(p):
    """Flatten interests.roles into {interest_lower: role}; tolerates nested/list/str shapes."""
    r = _cpath(p, "interests.roles"); out = {}
    def eat(d):
        for k, v in d.items():
            if isinstance(v, dict) and str(k).lower() in ("interest", "interests", "roles"): eat(v)
            elif v: out[str(k).lower()] = v
    if isinstance(r, dict): eat(r)
    return out, r

def _v2_role_of(p, name):
    m, raw = _v2_roles(p); key = name.lower()
    for k, v in m.items():
        if key == k or key in k or k in key: return v
    if isinstance(raw, (str, list)) and raw and len(_v2_ints(p)) == 1: return raw
    return None

def _v2_exp_of(p, name):
    e = _cpath(p, "interests.experienceByInterest"); key = name.lower()
    if isinstance(e, dict):
        for k, v in e.items():
            kl = str(k).lower()
            if v and (key == kl or key in kl or kl in key): return v
    return None

def _v2_role_exp_spec(p):
    """Раньше здесь на КАЖДЫЙ интерес добавлялось по два гейта прогресса — Role и Experience.

    Оба стали недостижимы, и это видно на экране: стаж («сколько лет увлекаешься») воронка больше
    не спрашивает намеренно — он не меняет ни одного кандидата, — а роль извлекается далеко не из
    каждого ответа. Полоса застревала на 70% навсегда: человек отвечал на всё, что у него
    спрашивали, и всё равно не мог дойти до конца. Проценты должны мерить то, что реально
    спрашивается, иначе это просто неправда на экране.

    Интересы в списке гейтов представлены строкой «Interests» из CRIT_V2 — она и закрывается.
    """
    return []

# Onboarding had no language rule at all — every prompt and the whole scripted greeting are English, so
# a user writing Russian got answered in English throughout setup, which is their first impression of
# the product.
_CYR_ONB = re.compile(r"[\u0430-\u044f\u0410-\u042f\u0451\u0401]")


def _onb_lang(hist, want=None):
    """The language the UI is in, when the client tells us; otherwise a guess from what was typed."""
    if want in ("ru", "en", "es"):
        return want
    for m in reversed(hist or []):
        if m.get("role") == "user" and str(m.get("content", "")).strip():
            return "ru" if _CYR_ONB.search(str(m["content"])) else "en"
    return "ru"


# GRAMMAR is a separate demand from LANGUAGE, and it has to be: the model wrote Russian words in
# Russian order and still produced «Какую сторону кодирования ты больше интересуешься» and «Ты бы
# играл в игры с кем-то или смотреть матчи». Both are correct-language and broken-sentence, and a
# person reads a broken sentence as a broken product. The rule below names the two failures the
# model actually makes — case agreement in the question word, and a verb form that stops agreeing
# halfway through a choice — instead of asking politely for "good Russian".
_ONB_LANG_RULE = {
    "ru": (" [LANGUAGE: the user is writing in Russian, so write EVERY word of your message in Russian,"
           " including any [OPTIONS: ...] labels. Do not switch to English."
           " GRAMMAR, and this matters as much as the meaning: the question must be ONE complete,"
           " grammatical Russian sentence that ends with a single «?». The question word must agree"
           " in case with what it asks about («какая музыка тебе нравится», NOT «какую музыку тебе"
           " нравится»). When you offer a choice, both halves must be the same part of speech and the"
           " same form («играть или смотреть», NOT «играл или смотреть»). Re-read the sentence before"
           " you send it: if a native speaker would not say it out loud, rewrite it.]"),
    "en": (" [Write the question as one complete sentence ending in a single «?». Both halves of a"
           " choice take the same form (\"play or watch\", not \"played or watching\").]"),
    "es": (" [LANGUAGE: write EVERY word in Spanish (castellano), including any [OPTIONS: ...] labels."
           " Address the user as «tú». The question must be one complete, grammatical sentence with"
           " «¿» at the start and «?» at the end, and both halves of a choice take the same form.]"),
}

def critical_status_v2(p):
    p = p if isinstance(p, dict) else {}
    spec = CRIT_V2 + _v2_role_exp_spec(p)   # + role/experience per picked interest
    done, missing = [], []
    for label, chk in spec:
        try:
            ok = chk(p)
        except Exception:
            ok = False
        (done if ok else missing).append(label)
    total = len(spec)
    return {"done": done, "missing": missing, "total": total,
            "complete": len(missing) == 0, "pct": int(100 * len(done) / total) if total else 0}

# ---------------------------------------------------------------- interests-funnel chat prompt (interests step)
FUNNEL_PROMPT = '''You are Kleal, on the INTERESTS step of a short profile setup. The user already gave
their name, area and languages — never ask about those.

WHY YOU ARE ASKING AT ALL. Everything the user says here becomes the handle another human is found
by. «Music» matches a thousand people and therefore nobody; «инди и электроника, живьём в клубах»
matches the person they would actually enjoy an evening with. So every question must earn its place
by making the search sharper. Ask yourself before writing: would the answer change WHO we show them?
If not, do not ask it.

NEVER ASK — these were asked for a year and never once changed a single match:
- how long they have been into it («сколько лет увлекаешься», tenure, «since when»);
- their rank, level, skill tier, ELO or platform;
- anything that sounds like filling in a form rather than planning an evening.

DO ASK, one of these, whichever is missing and most useful for THIS interest:
- WHICH KIND exactly — the sub-flavour that separates people («какая музыка», «во что именно
  играешь», «какой спорт»);
- WHAT THEY WANT OUT OF IT with another person — play together, go and watch, talk about it, learn
  it, just company;
- WITH WHOM it usually happens — one-on-one, a small group, a crowd — but only if it is not obvious.

STYLE.

NEVER REPEAT BACK WHAT THEY JUST SAID. This is the failure that keeps happening, and it is what
makes the agent sound like a machine confirming input instead of a person listening:

    User: на концертах   ->  Agent: «Концерты. Ходишь на них с друзьями или один?»   WRONG
    User: климат         ->  Agent: «Климат. Что делает фотографию отличной?»        WRONG

A bare noun echoed back with a full stop adds nothing. If you have nothing to add, ADD NOTHING —
ask the question and stop. MOST OF YOUR MESSAGES SHOULD BE ONE QUESTION AND NOT A WORD MORE. A
lead-in is allowed only when it carries something NEW that follows from their answer, never a copy
of it.

DO NOT REUSE A SENTENCE PATTERN. «Что делает поездку идеальной для тебя?» followed by «Что делает
фотографию отличной для тебя?» is one template with the noun swapped — that is a questionnaire, not
a conversation. Ask about the thing itself: «Куда ездил в последний раз?», «Что снимаешь?»

NAMES IN LATIN SCRIPT STAY EXACTLY AS WRITTEN. Never decline them and never spell them in Cyrillic:
«Xbox», not «ксбоксом»; «во что играешь на Xbox?», not «занимаешься иксбоксом». The same holds for
game, brand, club and place names — Dota, PlayStation, Valorant, Netflix. Build the sentence around
the name instead of bending it («играешь на PlayStation с друзьями?»). A mangled Cyrillic spelling
of a Latin name reads as a broken translation, and it is the one thing people notice first.

Never compliment. No «это замечательно», «отличный выбор», «ты интересный человек», and never open
with «X — это отличный способ…».

Ask EXACTLY ONE question, and let it be the last thing in the message. It must be a complete
sentence and it must END WITH A QUESTION MARK — exactly one, and none anywhere else. Two topics
joined by «and» is two questions and is forbidden. Keep the whole message under 20 words.

Do not re-ask a question you already asked, even reworded — if they sidestepped it, move on. For
closed choices end with [OPTIONS: a | b | c] (pipe-separated only, no letters or numbers). No emoji,
no markdown, no JSON, no <profile> tags. A status line tells you exactly what to ask next — follow it.'''

# finish / add-another intent detection at the confirm stage (order matters: FIN first - "no more" contains "more")
# The option buttons are localised (see _CONFIRM_OPTIONS), so these must match the Russian labels too —
# otherwise tapping «Это всё» would fall through and the step would never finish.
_FIN_RE = re.compile(r"that'?s all|that is all|\bfinish|\bdone\b|no more|nothing else|i'?m good|all set|\bnope\b|^\s*no[.! ]*$"
                     r"|это вс[её]|всё|все[.! ]*$|больше нет|хватит|готов|достаточно|^\s*нет[.! ]*$"
                     # Испанский: без этих форм «Eso es todo» проваливалось мимо ветки финиша, и шаг
                     # зацикливался ровно так же, как когда-то зацикливался русский.
                     r"|eso es todo|ya est[áa]|nada m[áa]s|es todo|^\s*no[.! ]*$|listo|suficiente", re.I)
_ADD_RE = re.compile(r"\badd\b|another|one more|\bmore\b|\byes\b|yeah|sure|\balso\b|actually"
                     r"|добав|ещ[её]|да[.! ]*$|конечно|также|хочу"
                     r"|a[ñn]adir|otro inter[ée]s|uno m[áa]s|^\s*s[íi][.! ]*$|claro|tambi[ée]n", re.I)
_CONFIRM_OPTIONS = {"ru": "Добавить ещё интерес | Это всё", "en": "Add another interest | That's all",
                    "es": "Añadir otro interés | Eso es todo"}

# gibberish / non-answer detection: catch keyboard-mash like "afcafcafc" / "ппфцпц" so the funnel
# re-asks instead of silently accepting junk and moving on.
_VOWELS = "aeiouyауоыиэяюёеAEIOUYАУОЫИЭЯЮЁЕ"
_KBD_MASH = {"asdf", "asdfg", "asdfgh", "asdfghjkl", "qwer", "qwert", "qwerty", "qwertyu",
             "zxcv", "zxcvb", "zxcvbn", "hjkl", "asd", "qwe", "zxc", "qaz", "wsx", "edc",
             "йцук", "йцуке", "йцукен", "фыва", "фывап", "ячсм", "ячсми", "ячсмит", "цук", "фыв"}
def _is_gibberish(text):
    """True when a message reads like random characters / a keyboard mash rather than a real answer.
    Conservative: only flags when EVERY 4+ letter token looks unpronounceable, so real short answers
    (PC, B1, 5y, Ancient, coffee...) always pass."""
    t = (text or "").strip().lower()
    letters = re.sub(r"[^a-zа-яё]", "", t)
    if len(letters) < 4:
        return False  # short answers are legitimate (PC, no, B1, 5y)
    words = [w for w in re.findall(r"[a-zа-яё]{2,}", t) if len(w) >= 4]
    if not words:
        return False
    vset = set(_VOWELS.lower())
    conrun = re.compile(r"[^" + _VOWELS.lower() + r"]{4,}")
    def periodic(w):                        # a short pattern tiled: "abcabc", "пвапвап", "аываыва"
        return any(all(w[i] == w[i % p] for i in range(len(w))) for p in range(1, len(w) // 2 + 1))
    def bad(w):
        if w in _KBD_MASH:
            return True
        vr = sum(1 for c in w if c in vset) / len(w)
        if vr < 0.2 or vr > 0.85:           # too few / too many vowels -> unpronounceable
            return True
        if conrun.search(w):                # long consonant run
            return True
        if len(set(w)) <= max(2, len(w) // 3):  # very repetitive (few unique letters)
            return True
        if len(w) >= 5 and periodic(w):     # a tiled n-gram pattern
            return True
        return False
    return all(bad(w) for w in words)

def _v2_listhas(p, path, name):
    v = _cpath(p, path) or []
    key = name.lower()
    return any(isinstance(x, str) and (key == x.lower() or key in x.lower() or x.lower() in key)
               for x in (v if isinstance(v, list) else [v]))

# classify an interest by NAME (before any domain is extracted) so the ROLE question fits it -
# "do you play or watch" makes sense for a game/sport, but is nonsense for AI or coffee.
def _v2_kind(it):
    n = (it or "").lower()
    if re.search(r"dota|valorant|league|\bcs\b|apex|fortnite|fifa|minecraft|\bgame|gaming|esport|игр", n): return "game"
    if re.search(r"football|soccer|basket|tennis|\bgym\b|\brun|\bbox|climb|swim|cycl|\bhik|volleyball|skate|yoga|padel|surf|ski|футбол|бег|поход|спорт|йог", n): return "sport"
    if re.search(r"movie|cinema|film|series|\bshow|anime|\btv\b|netflix|k-?drama|кино|фильм|сериал", n): return "watch"
    if re.search(r"language|spanish|english|french|german|italian|portuguese|japanese|chinese|practice|duolingo|язык", n): return "language"
    if re.search(r"music|concert|gig|band|dj|vinyl|музык|концерт", n): return "music"
    if re.search(r"travel|trip|roadtrip|backpack|путешеств|поездк", n): return "travel"
    if re.search(r"coffee|food|cook|bar|wine|beer|restaurant|кофе|еда|готов|бар|вино", n): return "food"
    if re.search(r"photo|фото|снима|draw|paint|craft|рисов", n): return "photo"
    if re.search(r"\bai\b|\bml\b|startup|\btech|business|career|founder|network|invest|product|\bdesign|architect|coding|program|marketing|crypto|код|стартап|бизнес", n): return "topic"
    return "social"

# Что спросить про интерес. РОВНО ОДНО и всюду — КОНКРЕТИКА, потому что именно она становится
# ключом поиска: «музыка» не совпадает ни с кем, «инди и электроника» совпадает с живым человеком.
#
# Раньше каждая строка спрашивала ДВЕ вещи разом («во что именно играешь И играешь или смотришь»),
# и модель честно склеивала их в одно предложение, которое разваливалось: «Ты бы играл в игры с
# кем-то или смотреть матчи». Одна строка — один вопрос.
_ROLE_FRAME = {
    "game":     "which games exactly they play",
    "sport":    "whether they play it themselves or go and watch",
    "watch":    "what exactly they watch — which shows, films or sport",
    "language": "what they want the practice for — conversation, work or travel",
    "music":    "which music exactly — which artists or genres",
    "travel":   "where they went last, or where they are going next",
    "food":     "what kind of places they go to",
    "photo":    "what they shoot",
    "topic":    "which side of it interests them",
    # Общий случай — про КОНКРЕТНЫЙ последний раз, а не про идеал: «что делает X идеальным для
    # тебя» модель повторяла слово в слово от интереса к интересу, и это читалось анкетой.
    "social":   "the last time they did it — where it was or what it was",
}
def _v2_frame(it): return _ROLE_FRAME.get(_v2_kind(it), "what exactly they like about it")

def _v2_detail_gap(p, it):
    """Второй вопрос про интерес — или None, и None это норма.

    Здесь по очереди жили ранг в игре, платформа, спортивный уровень, уровень языка, стаж — ни одно
    из этого не участвует в подборе: ранжирование сравнивает ТЕМЫ. Последним стоял вопрос «один на
    один или в небольшой группе», и он оказался хуже всех: это свойство ЧЕЛОВЕКА, а не интереса, —
    воронка задавала его отдельно про игры, отдельно про футбол, отдельно про музыку, слово в слово.
    Три интереса превращались в три одинаковых вопроса подряд. Теперь он спрашивается один раз на
    весь шаг, в самом конце (см. _v2_gaps).

    Остаётся ровно один случай, где второй вопрос правда меняет выдачу: нетворкинг. «Кого ты
    хочешь встретить» — это и есть его тема, без неё интерес нечем сравнивать.
    """
    low = it.lower()
    if any(w in low for w in ("network", "startup", "business", "career")):
        if _chas(p, "domains.networking.industry") or _chas(p, "domains.networking.goal"): return None
        return 'for "%s": which field they are in and who they hope to meet through it' % it
    return None

def _v2_plan(hist, p):
    """План опроса — интересы, С КОТОРЫМИ ШАГ НАЧАЛСЯ, а не те, что сейчас в профиле.

    Берётся из первой реплики человека («I'm into xbox, foraging» — её кладёт колесо). Профиль для
    этого не годится: модель переписывает его целиком на каждом ходу, и интерес, который она не
    пронесла, исчезал из плана вместе с вопросом про него.

    Это же держит разговор конечным. Обогащение дописывает в профиль темы из ответов («экшн» после
    «во что играешь»), и пока план строился по профилю, три интереса превращались в шесть, шесть в
    десять, а шаг не кончался. Спрашиваем ровно про то, что человек выбрал сам.
    """
    first_user = next((str(m.get("content", "")) for m in hist if m.get("role") == "user"), "")
    body = re.sub(r"^\s*i'?m into\s+", "", first_user.strip(), flags=re.I)
    seed = [x.strip() for x in re.split(r"[,;]", body) if x.strip()]
    # Запасной путь для входов не из колеса (веб-прототип, «добавить интересы» из профиля).
    return seed[:8] if seed else _v2_ints(p)[:8]


def _v2_gaps(p, hist):
    """Что ещё стоит спросить, по порядку. Stateless: сколько бюджета потрачено на интерес,
    оценивается по тому, сколько раз агент уже называл его по имени.

    Бюджет — ОДИН вопрос на интерес. Было два, и второй уходил в никуда: спрашивать про один
    интерес дважды подряд человек читает как «меня не слышат», а выдачу это не меняло.

    И ПОТОЛОК НА ВЕСЬ ШАГ. Он появился вместе с обогащением: ответ «экшн» на «во что играешь»
    теперь сам ложится в интересы — и следующим ходом воронка честно видит новый интерес, про
    который ещё не спрашивала. Три интереса превращались в шесть, шесть в десять, и разговор не
    кончался никогда. Спрашиваем столько раз, сколько увлечений человек назвал САМ в начале, — то
    есть про то, что он выбрал, а не про то, что мы из него вытащили.
    """
    asked_total = sum(1 for m in hist if m.get("role") == "assistant" and "?" in str(m.get("content", "")))
    plan = _v2_plan(hist, p)
    # Закрытыми считаются ПЕРВЫЕ asked_total пунктов плана — по одному вопросу на интерес, в
    # порядке плана, потому что промпт и ведёт агента по gaps[0].
    #
    # Раньше «спрашивали ли уже про это» искалось подстрокой: ключ интереса внутри реплики агента.
    # Не находилось НИКОГДА. Агент пишет по-русски и склоняет латиницу — на «xbox» он отвечает
    # «Где ты обычно занимаешься ксбоксом?», и подстроки «xbox» там нет. План навсегда упирался в
    # первый пункт, агент второй раз спрашивал про него же, а шаг закрывал глобальный потолок по
    # ЧИСЛУ вопросов — то есть два интереса получали два вопроса, оба про первый.
    # Проверено вживую: «Игры → Консоли → Xbox» и «Природа → Сад и звёзды → Травы и грибы» —
    # про травы не спросили ни разу.
    remaining = plan[asked_total:]
    if not remaining:
        return []

    gaps = []
    for it in remaining:
        if _v2_role_of(p, it):
            d = _v2_detail_gap(p, it)    # только нетворкинг; всё остальное — None
            if d: gaps.append(d)
            continue
        gaps.append('for "%s": %s' % (it, _v2_frame(it)))
    # «Один на один или в небольшой группе» здесь НЕ спрашивается вовсе, и это осознанно.
    #
    # Сначала он задавался про каждый интерес отдельно — три интереса давали три одинаковых
    # вопроса подряд. Потом один раз на весь шаг, с проверкой «не спрашивал ли я это уже» по своим
    # прошлым репликам — и модель тут же переформулировала его словами, которых проверка не знала
    # («смотришь с друзьями или один?»), и спросила дважды. Ловить формулировку регуляркой значит
    # проигрывать ей каждый раз.
    #
    # А главное — этот ответ ничего не меняет в выдаче: размер компании человек выбирает заново
    # для КАЖДОГО интента (кадр O.06, «Сколько вас будет?»), и матчинг читает именно intent.format.
    # Вопрос в анкете спрашивал то, на что всё равно ответят потом.
    return gaps

def _v2_union_interests(prior, fresh, merged):
    """Список интересов ДОПОЛНЯЕТСЯ, а не заменяется.

    base._deep_merge для всего, что не словарь, делает `acc[k] = v` — то есть список интересов
    затирается тем, что извлеклось на ЭТОМ ходу. Извлекатель видит весь разговор и обычно
    перечисляет всё, но стоит ему один раз вернуть только последний ответ — и накопленное
    пропадает. Ровно из-за этого «экшн» мог не доехать до профиля: не потому, что его не извлекли,
    а потому что следующий ход его вытер.

    Порядок сохраняется, сравнение регистронезависимое, потолок на случай длинного разговора.
    """
    def lst(p):
        v = ((p or {}).get("interests") or {}).get("explicit")
        if isinstance(v, str):
            return [v]
        return [x for x in (v or []) if isinstance(x, str) and x.strip()]
    prior_items = lst(prior)
    prior_keys = {x.strip().lower() for x in prior_items}
    out, seen = [], set()
    for x in prior_items + lst(fresh) + lst(merged):
        k = x.strip().lower()
        # Extraction discovers text; it does not express consent. Only existing values and governed
        # taxonomy keys may survive this legacy merge path. Novel free text must cross the explicit
        # interest-normalize -> interest-confirm boundary first.
        if k not in prior_keys and not interest_norm.trusted_interest(k):
            continue
        if k and k not in seen:
            seen.add(k)
            out.append(x.strip())
    if out:
        merged.setdefault("interests", {})["explicit"] = out[:24]
    return merged


def _norm_options(options):
    """Models sometimes jam choices into one comma blob or prefix them (a) / 1.). Split + clean -> chips."""
    raw = list(options or [])
    if len(raw) == 1 and re.search(r"[;,|]|\b[b-d]\)", raw[0]):
        raw = re.split(r"\s*[;,|]\s*|\s+(?=[a-d]\))", raw[0])
    out = []
    for o in raw:
        o = re.sub(r"^\s*(?:[a-zA-Z]\)|\d+[.)]|[-•])\s*", "", str(o)).strip()
        if o and o.lower() not in (x.lower() for x in out):
            out.append(o)
    return out[:6]

# extractor with V2 extras: per-interest experience/tenure ("how long have you been into it")
EXTRACT_V2 = base.EXTRACT_PROMPT + '''
ALSO extract, under the same iron rules (ONLY if the user explicitly said it):
interests.experienceByInterest = {"<interest exactly as named in explicit>": "<how long they have been into it, short: '5 years', 'since school', 'just started'>"} - one entry per interest whose experience/tenure the user stated.

AND THIS IS THE POINT OF THE WHOLE STEP — THE ANSWER TO A "WHICH KIND" QUESTION IS ITSELF AN
INTEREST. When the Agent asked which kind / which genre / what exactly / what they play or watch,
and the User named it, that named thing goes into interests.explicit as ITS OWN ENTRY, in the
user's own words, alongside the broad one:

  Agent: Какой жанр игр тебе интересен?   User: экшн
  -> interests.explicit must contain BOTH the original interest and "экшн"

  Agent: Какую музыку любишь?             User: инди и электроника
  -> "инди", "электроника"

This is not decoration. Search compares these entries LITERALLY: a person who wrote «экшн» is
found by «экшн», and a detail that stays only in prose is a detail nobody can be found by.

Two limits, both hard. Only words the User actually typed — never a genre you inferred, never a
synonym you improved. And a message that names nothing («не знаю», «разное», «разную», «любую»,
«всякое», «мне нравится», «давно этим занимаюсь») adds NOTHING: it is a non-answer, not an interest.

Keep every interest already present — you are adding to the list, never replacing it.'''

# the stored artifact: ONE continuous plain-text summary describing everything about the user
SUMMARY_PROMPT = '''You are Kleal, a personal social agent. You store your memory of a user as ONE continuous plain-text summary.
Given the profile JSON, write that summary in __LANGNAME__, second person, warm but strictly factual, and AS SHORT AS THE FACTS ARE — two sentences when the profile holds two things, six at the very most. Never pad to reach a length: a sentence that adds no new fact («this is part of your life», «you spend time on it») must not be written at all. __LANGDIR__ In Russian address the user as «ты»; in Spanish use «tú».

WRITE ABOUT THE PERSON, NOT ABOUT THEIR SETTINGS. Cover, when present: who they are (name, age), what they are into — every interest with the detail that makes it theirs (how long, what level, with whom, what exactly they like about it) — the languages they are comfortable in, and the city or area they move around.

NEVER MENTION, even in passing: safety options, privacy or visibility choices, matching permissions, verification, radius in kilometres, coordinates, whether the profile may be used for matching, or any other switch from the app. These are settings, not the person; a summary that recites them reads like a form, and the user asked to be described, not configured. If the JSON has nothing but settings, write only what little is about the person and stop.

INTERESTS ARE STORED FOR A SEARCH ENGINE, NOT FOR READING. They arrive as a mixed bag: English keywords, the user's own words, sometimes another language entirely, sometimes near-duplicates of one another («gaming», «настольные игры», «board games»). Render them as the person would say them in __LANGNAME__, merge the duplicates into one mention, and NEVER quote the raw key, NEVER show a second language in brackets, NEVER remark on which language a key was written in. The storage format is not a fact about the human.

NO COMPLIMENTS AND NO CLOSING FLOURISH. Never tell the person they are interesting, unique, versatile or well-rounded, never sum them up with a verdict, never end on a flattering sentence. State what is there and stop — the last sentence should be as plain as the first. Gender is not a fact to announce either: it only shapes the grammar of the sentences.

DO NOT SPECULATE. No «probably», «likely», «you may also enjoy», no guessing at their free time, their character or their motives from an interest. If the JSON does not state it, it does not go in the summary — a person reading this must not find a single sentence they did not tell you.

STRICT: only facts present in the JSON - NEVER invent or embellish. No lists, no markdown, no headings, no emoji, no JSON. Plain flowing text only.'''

# Три языка, а не два: человек с испанской системой получал английский текст, потому что здесь
# была развилка «Russian или English». Названия и указания те же, что у buddy (_LANGNAME/_LANGDIR),
# чтобы агент и сводка не заговорили на разных языках об одном и том же человеке.
_SUM_LANGNAME = {"ru": "Russian", "en": "English", "es": "Spanish"}
_SUM_LANGDIR = {
    "ru": "Every word must be in Russian, in Cyrillic script.",
    "en": "Every word must be in English.",
    "es": "Every word must be in Spanish (castellano).",
}

def v2_summary(profile, lang="ru"):
    """One LLM call -> the running text summary we store for the user (profile.summary)."""
    cfg = MODEL_ID
    lang = str(lang or "ru").lower()
    if lang not in ("ru", "en", "es"):
        lang = "ru"
    # Настройки в модель просто НЕ отдаём: запрет в промпте — второй рубеж, а не единственный.
    # Пока они лежали во входе, модель исправно пересказывала их в сводке.
    DROP = ("photo", "summary", "safety", "permissions", "receiving", "verified", "paused",
            "radiusKm", "km", "lat", "lon", "geo", "datingOk", "blocksMe", "source", "id")
    prof = {k: v for k, v in (profile or {}).items() if k not in DROP}
    sys_prompt = (SUMMARY_PROMPT
                  .replace("__LANGNAME__", _SUM_LANGNAME.get(lang, "Russian"))
                  .replace("__LANGDIR__", _SUM_LANGDIR.get(lang, _SUM_LANGDIR["ru"])))
    raw = llm_complete(cfg, [{"role": "system", "content": sys_prompt},
                              {"role": "user", "content": json.dumps(prof, ensure_ascii=False)}], 0.4)
    txt = base.parse_reply(raw)[0]
    txt = (txt or "").replace("—", "-").replace("–", "-").strip()
    return {"summary": txt}

def v2_chat(messages, prior, want_lang=None):
    """Interests-step turn: extract first (sequential), then a focused funnel reply. Mirrors the
    base two-call pipeline but scoped to interests/roles/domain detail. Returns merged profile + crit."""
    cfg = MODEL_ID
    hist = [m for m in messages if m.get("role") in ("user", "assistant")]
    result = {"profile": None}
    def _job():
        try:
            lines = []
            for mm in hist:
                who = "User" if mm.get("role") == "user" else "Agent"
                lines.append(who + ": " + str(mm.get("content", "")))
            ext_raw = llm_complete(cfg, [{"role": "system", "content": EXTRACT_V2},
                                          {"role": "user", "content": "\n".join(lines)}], 0.1)
            prof = base._extract_json(ext_raw)
            if isinstance(prof, dict):
                prof = base._clean_profile(prof)
                prof = {k: v for k, v in prof.items() if k in base.KNOWN_TOP}
                result["profile"] = prof or None
        except Exception:
            result["profile"] = None
    if any(m.get("role") == "user" for m in hist):
        _t = threading.Thread(target=_job, daemon=True); _t.start(); _t.join(timeout=220)
    merged = base._deep_merge(dict(prior), result["profile"] or {})
    merged = _v2_union_interests(prior, result["profile"], merged)
    crit = critical_status_v2(merged)
    gaps = _v2_gaps(merged, hist)
    lastu = next((str(m.get("content", "")) for m in reversed(hist) if m.get("role") == "user"), "")
    # THIRD piece of the localisation coupling, and the one that bit: this sniffed the assistant's own
    # message for the literal English "another interest". Once the funnel started replying in Russian
    # the flag never went true, the _FIN_RE finish branch became unreachable, and the step looped
    # forever — the user answered «Это всё» three times and was asked again each time.

    sys = FUNNEL_PROMPT + _ONB_LANG_RULE[_onb_lang(hist, want_lang)]
    complete = False
    if _is_gibberish(lastu):
        # user typed junk / random characters - do NOT advance or wrap up, gently re-ask.
        sys += (" [The user's last message does not look like a real answer - it reads like random "
                "characters or a keyboard mash. In ONE short, warm line say you did not quite catch that, "
                "then re-ask YOUR OWN PREVIOUS question in simpler words. Ask EXACTLY ONE question and keep "
                "the same [OPTIONS: ...] if your previous question had them. Do NOT move to a new topic and "
                "do NOT wrap up.]")
    elif gaps:
        sys += (" [NEXT GAP TO CLOSE: ask %s. Exactly ONE question message - warm reaction line first. "
                "If it is a closed choice end with [OPTIONS: a | b | c] (pipe-separated only). "
                "Never re-ask anything already known. Queued after this: %s]"
                % (gaps[0], "; ".join(gaps[1:3]) or "none"))
    # NOT gated on confirm_asked any more. That flag was inferred from the assistant's own PROSE, which
    # only ever worked because the English prompt made it echo "another interest" verbatim; in Russian
    # it rephrases every time ("Похоже, мы уже обсудили все интересы") and no pattern catches it
    # reliably. This branch is already unreachable while `gaps` is non-empty, so "everything is
    # covered AND the user says they're done" is the honest condition — and it is language-free.
    elif _FIN_RE.search(lastu):
        complete = True
        sys += (" [The user confirmed they are done with interests. Reply ONE short, warm wrap-up sentence "
                "that ends in a period (NEVER a question mark) and tells them to tap Continue. No [OPTIONS].]")
    elif _ADD_RE.search(lastu):
        sys += " [The user wants to add another interest. Ask ONE short question: what else they are into. No [OPTIONS].]"
    else:
        # confirm-before-finish: never end the interests step without asking
        sys += (" [ALL PICKED INTERESTS ARE COVERED. Ask EXACTLY ONE closing question: would they like to add "
                "another interest, or is that everything for now. End with [OPTIONS: %s]. "
                "Nothing else.]" % _CONFIRM_OPTIONS[_onb_lang(hist, want_lang)])
    # 0.45, не 0.6. Здесь модель не сочиняет, а формулирует один вопрос на чужом для неё языке, и
    # каждая лишняя десятая температуры — это «Ты бы играл в игры с кем-то или смотреть матчи».
    # Разнообразие вопросов задаёт список пробелов выше, а не разброс сэмплинга.
    raw = llm_complete(cfg, [{"role": "system", "content": sys}] + hist, 0.45)
    reply, _p, _i, _b, _s, options = base.parse_reply(raw)
    options = _norm_options(options)
    reply = base.dose_reply(base.sanitize_output(base.guard_reply(reply)))
    reply = reply.replace("—", "-").replace("–", "-")  # taste-skill: no em/en-dash in user-visible copy
    # Вопрос без знака вопроса — самая частая осечка модели, и на экране он выглядит оборванным.
    # Ставим его сами ТОЛЬКО там, где реплика заведомо вопрос: есть варианты ответа, а завершающей
    # точки нет. Ветку финиша (она обязана кончаться точкой) это не трогает.
    if options and reply and not reply.rstrip().endswith(("?", ".", "!", "…")):
        reply = reply.rstrip() + "?"
    if not (reply or "").strip():
        reply = "Tell me a bit more. What do you like to do with it?"
    # funnelComplete = no gaps left AND the user explicitly confirmed they are done adding interests
    return {"reply": reply, "options": options, "profile": merged, "crit": crit,
            "funnelComplete": complete, "gibberish": bool(_is_gibberish(lastu))}

# ВЕБ-ВЕРСИИ ОНБОРДИНГА БОЛЬШЕ НЕТ.
#
# Здесь лежала страница на 1427 строк — второй, параллельный клиент того же шага: своя разметка,
# свои виджеты, свой разбор ответов. Продукт живёт в приложении, и держать две реализации одного
# и того же значило платить дважды за каждую правку и расходиться при каждой второй.
#
# Корень сайта отдаёт теперь рекламный лендинг (WAITLIST_HTML) — для приложения на телефоне это и
# есть правильная публичная страница, и она уже написана. Снимок удалённого лежит в
# /root/kleal-archive/onboarding_app_before_web_removal.py.

# bake the profile app's public URL (pod: its own tunnel host) into the "My Profile" handoff; empty -> local :7073

# ---------------------------------------------------------------- REGISTRATION: onboarding -> shared user store
# Everyone who finishes onboarding is written into the same store the matching agent reads and the admin
# panel shows, so they immediately become matchable and visible. Store format matches services/admin.
# The path is resolved ONCE, in shared/config.py, and every reader/writer imports it from there.
# It used to be recomputed here, in matching and in admin, and the copies disagreed — matching read
# <root>/users.json while this service wrote services/matching/users.json — so a single restart
# without KLEAL_USERS split the store in two and registrations landed in a file the matcher never read.
USERS_PATH = config.USERS
_REG_LOCK = threading.Lock()

# ---------------------------------------------------------------- profile photos
# The photo a person uploads during onboarding used to be thrown away: the client deleted it from
# every payload (profileForServer) and nothing here ever stored one, so all 602 rows in the store had
# no photo and every candidate card in the app fell back to the SAME stock face. People were looking
# at a stranger's stock portrait under someone else's name.
#
# Photos are files, not fields. A 480px JPEG data URL is ~40 KB; multiplied by the store that is tens
# of megabytes of base64 inside the one JSON file the matcher re-reads and holds in memory to rank
# with — it would make every search carry the photo album. So the bytes go to disk and the row keeps
# a short URL, which is all any client needs.
PHOTOS_DIR = os.path.join(os.path.dirname(os.path.abspath(USERS_PATH)), "photos")
PHOTO_MAX_BYTES = 600 * 1024          # a 480px JPEG is ~40 KB; this is a sanity ceiling, not a target
_DATA_URL = re.compile(r"^data:image/(jpeg|jpg|png|webp);base64,(.+)$", re.I | re.S)


def photo_url(uid):
    """The path a client fetches. Served by THIS service, and the gateway already forwards
    /api/onboarding/* here untouched — so no new route anywhere in the topology."""
    return "/api/onboarding/photo/%s.jpg" % uid


def save_photo(uid, data_url):
    """Persist a data-URL photo and return its URL, or None if there is nothing usable to save.

    Never raises: a photo that fails to store must not fail the registration that carried it — the
    person finished onboarding, and losing the whole profile over an avatar would be the worse bug."""
    m = _DATA_URL.match(str(data_url or "").strip())
    if not m:
        return None
    try:
        raw = base64.b64decode(re.sub(r"\s+", "", m.group(2)), validate=False)
    except Exception:
        return None
    if not raw or len(raw) > PHOTO_MAX_BYTES:
        return None
    try:
        os.makedirs(PHOTOS_DIR, exist_ok=True)
        dst = os.path.join(PHOTOS_DIR, "%s.jpg" % uid)
        tmp = dst + ".tmp"
        with open(tmp, "wb") as f:
            f.write(raw)
        os.replace(tmp, dst)                 # atomic: a half-written photo is never served
    except Exception:
        return None
    return photo_url(uid)


def read_photo(uid):
    """Bytes of a stored photo, or None. The id is used as a filename, so it is checked against the
    exact shape ids have — a path fragment must never reach the filesystem."""
    if not re.match(r"^[A-Za-z0-9_-]{1,64}$", str(uid or "")):
        return None
    try:
        with open(os.path.join(PHOTOS_DIR, "%s.jpg" % uid), "rb") as f:
            return f.read()
    except Exception:
        return None


def _translate_interests(batch):
    """Один вызов модели на всё непереводимое: список формулировок -> [{"en","ru","es"}].

    Модель, а не фильтрация: фильтрации задача «назови тему», и она отвечает темой ВСЕГДА, даже
    когда темы нет, — на этом уже горели (интересы «hello» и «leisure» у живых людей). Здесь
    задача другая: ПЕРЕВЕСТИ сказанное, сохранив специфичность. Текст промпта и разбор ответа —
    общие с миграцией (shared/interest_i18n.py), иначе два пути дали бы разные ключи одному слову.
    """
    import interest_i18n
    raw = llm_complete(MODEL_ID, [{"role": "system", "content": interest_i18n.TRANSLATE_PROMPT},
                                  {"role": "user", "content": "\n".join(batch)}], 0.2)
    return interest_i18n.parse_translation(raw, batch)


def _canon_interests(words):
    """Свести интересы к АНГЛИЙСКИМ КЛЮЧАМ. Подписи для показа живут в общем словаре
    (shared/interest_i18n.py), своё слово человека становится подписью его языка.

    РАНЬШЕ здесь ДОПИСЫВАЛИСЬ английские «ручки» от фильтрации — к «cata de café» добавлялось
    голое coffee, к «mercado gastronómico» голое market. Ручки-понятия трижды чистили миграциями
    (strip_generic_handles: market, design, exchange…), потому что они льстили любому запросу
    своей области и врали через границы областей. Теперь дописывать нечего: хранится сразу
    английская форма, и подбор сравнивает английское с английским.

    Best-effort остался прежним: модель молчит — слово хранится как есть, регистрация не ждёт
    и не падает. Такое слово переведётся позже (миграцией или при следующей правке профиля).

    Потолок здесь — ВТОРОЙ на том же пути: строку сначала собирает _profile_to_user, потом она
    проходит сюда. Пока тут стояло восемь, поднимать потолок там было бесполезно — обрезалось
    следом. Оба числа обязаны совпадать, иначе меньшее молча побеждает.
    """
    try:
        import interest_i18n
        return interest_i18n.to_en(words, translate=_translate_interests)[:INTERESTS_MAX]
    except Exception:
        out = [str(w).strip() for w in (words or []) if str(w).strip()]
        return out[:INTERESTS_MAX]

# ---------------------------------------------------------------- accounts (dev sign-in)
# A SEPARATE file from users.json on purpose. users.json is the matching store: it is read by the
# matcher, served to the admin screen and handed around as candidate data. Credentials must not ride
# along with something that is already being passed about, even hashed.
ACCOUNTS_PATH = config.ACCOUNTS
_ACC_LOCK = threading.Lock()
_PBKDF_ROUNDS = 200_000


def _read_accounts():
    try:
        with open(ACCOUNTS_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _write_accounts(d):
    tmp = ACCOUNTS_PATH + ".tmp"
    os.makedirs(os.path.dirname(os.path.abspath(ACCOUNTS_PATH)), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, ACCOUNTS_PATH)
    try:
        os.chmod(ACCOUNTS_PATH, 0o600)
    except Exception:
        pass


def _hash_pw(password, salt):
    return hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"),
                               bytes.fromhex(salt), _PBKDF_ROUNDS).hex()


def _acc_key(login):
    return str(login or "").strip().lower()


def signup(login, password, name=None):
    """Create an account. The profile itself is attached later, when onboarding finishes."""
    key = _acc_key(login)
    if len(key) < 3:
        return {"ok": False, "error": "login too short"}
    if len(str(password or "")) < 6:
        return {"ok": False, "error": "password too short"}
    with _ACC_LOCK:
        accs = _read_accounts()
        if key in accs:
            return {"ok": False, "error": "login taken"}
        salt = os.urandom(16).hex()
        accs[key] = {"login": str(login).strip(), "salt": salt,
                     "hash": _hash_pw(password, salt), "name": str(name or "").strip(),
                     "created": int(time.time())}
        _write_accounts(accs)
    return {"ok": True, "login": str(login).strip()}


def signin(login, password):
    """Verify, and hand back the stored profile so the app can skip onboarding entirely."""
    key = _acc_key(login)
    acc = _read_accounts().get(key)
    # Same answer whether the login is unknown or the password is wrong: a different message is a
    # free oracle for which logins exist.
    bad = {"ok": False, "error": "wrong login or password"}
    if not acc:
        return bad
    try:
        want = _hash_pw(password, acc.get("salt") or "")
    except Exception:
        return bad
    if not hmac.compare_digest(want, str(acc.get("hash") or "")):
        return bad
    # The ONBOARDING-shaped profile, not the user row. They are different shapes — the row is flat
    # (interests: [...]) and the client expects the nested form (interests.explicit) that the profile
    # app knows how to map. Handing back the row restored a profile with no interests at all.
    prof = acc.get("profile") if isinstance(acc.get("profile"), dict) else None
    return {"ok": True, "login": acc.get("login"), "name": acc.get("name") or "",
            "profile": prof, "hasProfile": bool(prof)}


# ИМЯ — ЭТО ПОДПИСЬ, КОТОРУЮ ЧИТАЮТ ДРУГИЕ. Оно стоит в шапке чужой переписки, в карточке
# кандидата и в приглашении, поэтому адрес почты в этом поле — не опечатка, а утечка: посторонний
# читает почту человека, который её не называл.
#
# До сих пор имя не проверял НИКТО — ни анкета, ни attach, ни register: оно проходило насквозь как
# подпись. На боевых данных это дало ровно одну строку, названную собственным адресом владельца, и
# она пережила переустановку, потому что привязка увезла её в аккаунт и вход возвращал обратно.
#
# Отсекаем то, чем имя не бывает: собаку и косые (адрес, ссылка), три цифры подряд (номер). И
# требуем хотя бы одну букву — «12345» именем тоже не является. Правило то же, что у клиента
# (kleal-app/src/onboarding.ts::isName): расходиться этим двум нельзя.
_NOT_A_NAME = re.compile(r"[@/\\]|https?:|\d{3,}")
_HAS_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)


def _clean_name(value):
    """Имя как подпись, не длиннее сорока. Пустая строка — имени нет."""
    name = " ".join(str(value or "").split())[:40]
    if not name or _NOT_A_NAME.search(name) or not _HAS_LETTER.search(name):
        return ""
    return name


def attach_profile(login, name, profile=None):
    """Bind the finished onboarding profile to the account, so the next sign-in restores it verbatim."""
    key = _acc_key(login)
    with _ACC_LOCK:
        accs = _read_accounts()
        if key not in accs:
            return {"ok": False, "error": "unknown login"}
        # Адрес сюда не кладём даже молча: отсюда он возвращается в профиль при каждом входе.
        accs[key]["name"] = _clean_name(name)
        if isinstance(profile, dict):
            # photo is a data URL and can be megabytes; it already travels through shared-origin
            # localStorage, so it has no business in the credential file.
            clean_profile = {k: v for k, v in profile.items() if k != "photo"}
            # Confirmation receipts are short-lived capabilities, not durable profile facts.
            if isinstance(clean_profile.get("interests"), dict):
                clean_profile["interests"] = dict(clean_profile["interests"])
                clean_profile["interests"].pop("confirmations", None)
            accs[key]["profile"] = clean_profile
        _write_accounts(accs)
    return {"ok": True}

# ============================================================================ вход по коду с почты
#
# Кадры A.03.1 … A.03.3. Одна и та же почта служит и входом, и регистрацией — отдельного «создать
# аккаунт» на борде нет, и это правило, а не упрощение: человек не должен помнить, заводил он тут
# аккаунт или нет.
#
# ЧТО ХРАНИТСЯ ГДЕ. Коды живут ТОЛЬКО в памяти: они действуют десять минут, и записывать секрет на
# диск ради переживания перезапуска — плохой размен. Сессии, наоборот, на диске рядом с аккаунтом:
# им жить месяцами, и потерять их при выкладке значит разлогинить всех.
#
# ЧЕГО НЕТ НАРУЖУ. Код не возвращается ни одной ручкой ни при каких настройках, а ответ на «пришли
# код» одинаков для существующего и несуществующего адреса — иначе это бесплатный способ узнать,
# кто зарегистрирован.
CODE_TTL = 600           # 10 минут — ровно как написано на кадре A.03.2
CODE_ATTEMPTS = 3        # кадр A.03.2b показывает «2 attempts left» после первой ошибки
RESEND_AFTER = 30        # «Resend code in 0:30»
SEND_PER_HOUR = 5        # на адрес
IP_PER_HOUR = 20         # на источник
SESSION_TTL = 90 * 24 * 3600

_CODES = {}              # email -> {"hash","exp","left","sent","last"}
_IP_HITS = {}            # ip -> [метки времени]
_CODE_LOCK = threading.Lock()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")


# КОД НА ЭКРАНЕ — ТОЛЬКО ПО ЯВНОМУ РУБИЛЬНИКУ, и по умолчанию он выключен.
#
# Пока почтовый домен не подтверждён, провайдер разрешает писать ровно на один адрес, и завести
# второй аккаунт для проверки нечем. Поэтому есть режим, в котором код возвращается ручкой и
# показывается рядом с полем ввода.
#
# Это ДЫРА, и она названа дырой намеренно: при включённом рубильнике любой, кто знает чужой адрес,
# запрашивает код и читает его в ответе — то есть входит в чужой аккаунт. Отсюда три решения:
# отдельная переменная (а не «включается, когда почта не настроена» — такое включилось бы само в
# первый же сбой провайдера), громкая строка в лог при старте, и заметная пометка на экране, чтобы
# никто не принял это за возможность продукта.
def show_code_enabled():
    return os.environ.get("KLEAL_SHOW_CODE", "").strip() in ("1", "true", "yes", "on")


if show_code_enabled():
    print("[auth] ВНИМАНИЕ: KLEAL_SHOW_CODE включён — код входа возвращается наружу и виден на "
          "экране. Это режим отладки, в проде он обязан быть выключен.", flush=True)


def _norm_email(e):
    return str(e or "").strip().lower()[:200]


def valid_email(e):
    return bool(_EMAIL_RE.match(_norm_email(e)))


def _sha(s):
    return hashlib.sha256(str(s).encode("utf-8")).hexdigest()


def _gen_code():
    """Шестизначный, с равномерным распределением. `secrets`, а не `random`: второй предсказуем по
    нескольким выданным значениям, и это ровно тот случай, где предсказуемость означает вход."""
    return "%06d" % secrets.randbelow(1000000)


def _prune(now):
    for k in [k for k, v in _CODES.items() if v.get("exp", 0) < now - 3600]:
        _CODES.pop(k, None)
    for k in list(_IP_HITS):
        _IP_HITS[k] = [t for t in _IP_HITS[k] if t > now - 3600]
        if not _IP_HITS[k]:
            _IP_HITS.pop(k, None)


def _acc_by_email(accs, email):
    """Аккаунт по почте. Ищем и по ключу, и по полю: аккаунты, заведённые логином с паролем, лежат
    под логином, а почта у них — обычное поле. Иначе один человек получил бы два аккаунта."""
    e = _norm_email(email)
    if e in accs:
        return e
    for k, v in accs.items():
        if _norm_email((v or {}).get("email")) == e:
            return k
    return None


def request_code(email, lang="en", ip=""):
    """Кадр A.03.1 → «Continue». Ответ ВСЕГДА одинаковый, кроме явно кривого адреса."""
    e = _norm_email(email)
    if not valid_email(e):
        return {"ok": False, "error": "bad email"}
    now = time.time()
    with _CODE_LOCK:
        _prune(now)
        hits = _IP_HITS.setdefault(str(ip or "?"), [])
        if len(hits) >= IP_PER_HOUR:
            return {"ok": False, "error": "too many", "retry_after": 3600}
        cur = _CODES.get(e)
        if cur and now - cur.get("last", 0) < RESEND_AFTER:
            # Не ошибка: человек нажал «отправить ещё раз» раньше времени. Экран покажет счётчик.
            return {"ok": True, "resend_in": int(RESEND_AFTER - (now - cur["last"])), "sent": False}
        if cur and cur.get("sent", 0) >= SEND_PER_HOUR and now - cur.get("first", now) < 3600:
            return {"ok": False, "error": "too many", "retry_after": 3600}
        code = _gen_code()
        _CODES[e] = {"hash": _sha(code), "exp": now + CODE_TTL, "left": CODE_ATTEMPTS,
                     "sent": (cur.get("sent", 0) + 1) if cur else 1,
                     "first": cur.get("first", now) if cur else now, "last": now}
        hits.append(now)
    ok, how, detail = mailer.send_code(e, code, lang=lang, minutes=CODE_TTL // 60)
    dev = {"dev_code": code} if show_code_enabled() else {}
    if not ok:
        # В режиме отладки код НЕ гасим даже при неудачной отправке: он и нужен ровно для тех
        # адресов, на которые провайдер писать отказывается. В обычном режиме — гасим, иначе
        # человек ждёт письма, которого не будет, а живой код висит десять минут.
        if not dev:
            with _CODE_LOCK:
                _CODES.pop(e, None)
            # «Не разрешён получатель» — отдельная новость: домен ещё не подтверждён у провайдера,
            # и повторять бессмысленно. Экран об этом скажет иначе, чем про временный сбой.
            if detail == "not allowed":
                return {"ok": False, "error": "not allowed"}
            return {"ok": False, "error": "send failed", "detail": detail}
        return dict({"ok": True, "resend_in": RESEND_AFTER, "sent": False, "via": "dev",
                     "mail_error": detail}, **dev)
    return dict({"ok": True, "resend_in": RESEND_AFTER, "sent": True, "via": how}, **dev)


def _new_session(accs, key):
    tok = secrets.token_urlsafe(32)
    acc = accs.setdefault(key, {})
    sess = acc.setdefault("sessions", {})
    now = int(time.time())
    # Держим не больше десяти живых сессий на аккаунт: у человека телефон и, может, планшет, а
    # неограниченный список — это склад ключей, который никто никогда не пересматривает.
    for h in [h for h, v in sess.items() if (v or {}).get("exp", 0) < now]:
        sess.pop(h, None)
    if len(sess) >= 10:
        for h in sorted(sess, key=lambda h: sess[h].get("created", 0))[:len(sess) - 9]:
            sess.pop(h, None)
    sess[_sha(tok)] = {"created": now, "exp": now + SESSION_TTL, "last": now}
    return tok


def verify_code(email, code, lang="en"):
    """Кадр A.03.2 → «Verify». Три исхода борда: верный, неверный (со счётчиком), истёкший."""
    e = _norm_email(email)
    now = time.time()
    with _CODE_LOCK:
        rec = _CODES.get(e)
        if not rec or rec.get("exp", 0) < now:
            _CODES.pop(e, None)
            return {"ok": False, "error": "expired"}
        if not hmac.compare_digest(_sha(str(code or "").strip()), rec.get("hash", "")):
            rec["left"] = int(rec.get("left", 1)) - 1
            if rec["left"] <= 0:
                _CODES.pop(e, None)
                return {"ok": False, "error": "expired"}   # попытки кончились — код мёртв
            return {"ok": False, "error": "wrong", "attempts_left": rec["left"]}
        _CODES.pop(e, None)                                 # одноразовый: гасим до выдачи сессии

    with _ACC_LOCK:
        accs = _read_accounts()
        key = _acc_by_email(accs, e)
        is_new = key is None
        if is_new:
            key = e
            accs[key] = {"login": e, "email": e, "created": int(now), "auth": "code"}
        else:
            accs[key].setdefault("email", e)
        tok = _new_session(accs, key)
        acc = accs[key]
        _write_accounts(accs)

    prof = acc.get("profile") if isinstance(acc.get("profile"), dict) else None
    # `isNew` — это про ПРОФИЛЬ, а не про запись в файле. Борд разводит два исхода: новому показать
    # A.03.3 и увести в анкету, вернувшемуся — сразу на главную. Человек, который завёл аккаунт и
    # бросил анкету на середине, по этому правилу пойдёт достраивать профиль, и это верно.
    return {"ok": True, "token": tok, "login": acc.get("login") or key, "email": e,
            "name": acc.get("name") or "", "profile": prof,
            "isNew": bool(is_new or not prof), "hasProfile": bool(prof)}


def session_owner(token):
    """Кому принадлежит сессия. Возвращает запись аккаунта или None. Заодно продлевает `last` —
    по нему потом можно будет чистить заброшенное."""
    if not token:
        return None
    h = _sha(token)
    now = int(time.time())
    with _ACC_LOCK:
        accs = _read_accounts()
        for key, acc in accs.items():
            sess = (acc or {}).get("sessions") or {}
            rec = sess.get(h)
            if not rec:
                continue
            if rec.get("exp", 0) < now:
                sess.pop(h, None)
                _write_accounts(accs)
                return None
            if now - rec.get("last", 0) > 3600:
                rec["last"] = now
                _write_accounts(accs)
            return dict(acc, _key=key)
    return None


def sign_out(token):
    """Выход с ЭТОГО устройства. Остальные сессии не трогаем: разлогинить человека везде — это
    отдельное осознанное действие, а не побочный эффект кнопки «выйти»."""
    if not token:
        return {"ok": True}
    h = _sha(token)
    with _ACC_LOCK:
        accs = _read_accounts()
        for acc in accs.values():
            if h in ((acc or {}).get("sessions") or {}):
                acc["sessions"].pop(h, None)
                _write_accounts(accs)
                break
    return {"ok": True}


def attach_profile_by_token(token, name, profile=None):
    """Привязать законченную анкету к аккаунту ПО СЕССИИ.

    Раньше привязка шла по `login`, а его выставлял единственный экран «Логин и пароль» — и всякий,
    кто входил иначе, доходил до конца анкеты с login = null. Профиль оставался только на телефоне:
    переустановил приложение и войти обратно некуда. Теперь личность берётся из сессии, и привязка
    происходит всегда.
    """
    acc = session_owner(token)
    if not acc:
        return {"ok": False, "error": "no session"}
    return attach_profile(acc.get("_key"), name, profile)

_R2M = {"watch": "watch", "play": "play", "discuss": "discuss", "practice": "practise",
        "practise": "practise", "attend": "attend", "meet": "meet"}


def _first(*vals):
    for v in vals:
        if v not in (None, "", [], {}):
            return v
    return None



# 'Spanish'[:2] is 'sp' and 'German'[:2] is 'ge' — neither is a language code, and matching's
# requiredLanguages gate compares codes, so a Spanish speaker written as 'sp' matched nobody.
_LANG_CODES = {"english": "en", "spanish": "es", "german": "de", "french": "fr", "portuguese": "pt",
               "italian": "it", "russian": "ru", "catalan": "ca", "ukrainian": "uk", "polish": "pl",
               "английский": "en", "испанский": "es", "немецкий": "de", "французский": "fr",
               "португальский": "pt", "итальянский": "it", "русский": "ru", "каталанский": "ca",
               "serbian": "sr", "сербский": "sr", "swedish": "sv", "шведский": "sv",
               "sp": "es"}   # legacy typo written by an older build; repair, do not drop


# Valid codes are ISO 639-1, NOT the keys of the name table above. Deriving them from that table
# was a bug caught only by counting the live store: 30 of the 31 codes in users.json are real
# (hi, ar, da, ko, zh, nl, ja, he, cs, el, th, vi, id ...) and simply have no English/Russian NAME
# entry, so the narrower check would have deleted a real language from anyone the admin touched —
# a worse bug than the one being fixed. The only genuinely broken code in the store is "sp", two
# rows, both real onboarding profiles; it is repaired by the alias table.
_LANG_VALID = set("""en es de fr pt it ru ca uk pl sr sv hi ar da ko zh fi nl tr no ja hu ro
he cs el th vi id bg hr sk sl et lv lt is ga cy sq mk bs be az ka hy fa ur bn ta te ml kn mr pa gu
si ne my km lo ms tl sw af zu am ku ps tg uz kk ky mn ta la eo""".split())


def _lang_code(x):
    """The comment above explains why `x[:2]` is wrong — and the fallback did it anyway for every
    word outside the table. Portuguese was in the table; Dutch, Greek, Turkish, Hebrew and anything
    typed freehand were not, and each became a two-letter string that is not a language code and
    therefore matches nobody. Unknown now returns "" and the caller drops it: no language is honest,
    a wrong language is not."""
    x = str(x or "").strip().lower()
    if not x:
        return "en"
    if x in _LANG_CODES:
        return _LANG_CODES[x]
    return x if (len(x) == 2 and x in _LANG_VALID) else ""


def _profile_to_user(p):
    """Map a Kleal onboarding profile -> a complete, matching-safe candidate record (like admin _norm_user)."""
    p = p or {}
    # «New user» остаётся последним рубежом для чужих вызовов; своя анкета до него не доходит —
    # register_profile отказывает раньше, чем человек получит чужую подпись вместо имени.
    name = _clean_name(_first(p.get("name"), "")) or "New user"
    ints = p.get("interests") or {}
    # ПОТОЛОК ОБЩИЙ С _canon_interests — см. INTERESTS_MAX.
    # ШЕСТЬ БЫЛО ПОТОЛКОМ АНКЕТЫ, А НЕ ЧЕЛОВЕКА. Когда интересы набирались чипами, шести хватало
    # с запасом. Колода карточек отдаёт двенадцать за один заход, разговор дописывает ещё — и всё,
    # что не влезло, ТИХО не доезжало до строки, по которой ищут: человек добавлял «Гарри Поттер»
    # в онбординге и не находил его в своей же карточке. Двадцать — это уже про человека: столько
    # можно назвать, не выдумывая.
    interests = [str(x).strip().lower() for x in (ints.get("explicit") if isinstance(ints, dict) else ints) or [] if str(x).strip()][:INTERESTS_MAX]
    langs = (p.get("languages") or {})
    ll = langs.get("comfortable") or langs.get("fluent") or langs.get("native") or [] if isinstance(langs, dict) else []
    langs = [c for c in (_lang_code(x) for x in ll if str(x).strip()) if c][:4] or ["en"]
    vibe = ""
    vb = p.get("vibe")
    if isinstance(vb, dict) and vb.get("primary"):
        vibe = str(vb["primary"][0]).lower()
    elif isinstance(vb, str):
        vibe = vb.lower()
    geo = p.get("geo") or {}
    area = str(_first(p.get("city"), (geo.get("comfortableAreas") or [None])[0], "") or "").strip()
    # Country is a distinct confirmed profile fact. Keeping it in the matching row lets online
    # discovery expose country-level placement without deriving or returning the person's point.
    country = str(p.get("country") or "").strip()[:80]
    # role from the first interest's role, normalised to matching's vocabulary
    role = "meet"
    roles = (ints.get("roles") if isinstance(ints, dict) else None) or {}
    if isinstance(roles, dict):
        for _k, rv in roles.items():
            r0 = (rv[0] if isinstance(rv, list) and rv else rv)
            if r0:
                role = _R2M.get(str(r0).lower(), "meet")
                break
    dating = bool((p.get("domains") or {}).get("dating", {}).get("enabled")) or \
        ("dating" in base.goals_list(p))
    try:
        age = int(_first(p.get("age"), (p.get("ageRange") or "28").split("-")[0], 28))
    except (TypeError, ValueError):
        age = 28
    # A stored per-person "km" is meaningless — distance depends on who is looking. It used to be
    # fabricated from a hash of the name; now it is honestly absent and distance comes from real
    # coarse coordinates when the person granted geolocation during onboarding.
    deals = [str(x).strip() for x in (p.get("dealBreakers") or []) if str(x).strip()][:6]
    lat = geo.get("coarseLat") if isinstance(geo.get("coarseLat"), (int, float)) else None
    lon = geo.get("coarseLon") if isinstance(geo.get("coarseLon"), (int, float)) else None
    try:
        radius = int(geo.get("maxDistanceKm")) if geo.get("maxDistanceKm") else None
    except (TypeError, ValueError):
        radius = None
    gender = str(p.get("gender") or "").strip() or None
    goals = base.goals_list(p)[:4]
    sf = p.get("safety") or {}
    return {
        "id": "on" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:8],
        "name": name, "interests": interests or ["social"],
        # vibe/entities used to be invented ('chill', '<Interest> scene') — collected-or-absent now
        "vibe": vibe, "langs": langs, "area": area, "country": country,
        "km": None, "lat": lat, "lon": lon, "radiusKm": radius, "open": True, "role": role,
        "gender": gender, "goals": goals, "summary": str(p.get("summary") or "")[:PROSE_MAX],
        # register_profile replaces the whole row, so the story must be carried here too or
        # re-running onboarding silently wipes what the person wrote.
        "story": str(p.get("story") or "")[:STORY_MAX],
        "personality": str(p.get("personality") or "")[:PROSE_MAX],
        # Часовой пояс ИМЕНЕМ зоны (Europe/Madrid), а не смещением: смещение меняется дважды в год,
        # зона — нет. Нужен, чтобы показать чужое местное время там, где оно расходится со своим.
        # Несётся здесь, а не только патчем, потому что register заменяет строку целиком — иначе
        # повторный онбординг молча стирал бы пояс, как когда-то стирал story.
        "tz": str(p.get("tz") or "")[:64],
        "persona": (_clean_persona(p.get("persona")) if p.get("persona") else None),
        # meeting-format preference (Figma «Формат встреч»); matching's mode_format reads this. Empty
        # until the user picks in the profile sheet — an empty list is honestly "no preference stated".
        "formats": [str(x).strip().lower() for x in (p.get("formats") or []) if str(x).strip()][:8],
        "safety": {"publicPlacesOnly": bool(sf.get("publicPlacesOnly", True)),
                   "verifiedOnly": bool(sf.get("verifiedOnly")),
                   "hideExactLocation": bool(sf.get("hideExactLocation"))},
        "datingOk": dating, "age": age, "verified": bool(p.get("ageVerified18", True)),
        "paused": False, "pending": 0, "blocksMe": False, "lastActiveDays": 0, "declinedOwnerDaysAgo": None,
        "intents": [], "entities": [],
        "dealBreakers": deals, "source": "onboarding",
        # receiving policy (Matching Core spec §4.4): registering = explicit consent to be matched,
        # so a default ACTIVE policy is written here. Dating is opt-in only (spec §17). Matching's
        # readiness engine (core_v2.readiness_state) reads this to decide open_now/quiet-hours/busy.
        "receiving": _default_receiving(dating, p.get("tz")),
    }


def _tz_offset_min(tz, when=None):
    """Смещение зоны в минутах на СЕЙЧАС. Неизвестная зона -> None, а не ноль и не Мадрид.

    Считается от имени зоны каждый раз, а не хранится: летом и зимой оно разное, и записанное
    однажды число к октябрю врёт на час.
    """
    tz = str(tz or "").strip()
    if not tz:
        return None
    try:
        import datetime
        from zoneinfo import ZoneInfo
        off = datetime.datetime.now(ZoneInfo(tz)).utcoffset()
        return int(off.total_seconds() // 60) if off is not None else None
    except Exception:
        return None


def _default_receiving(dating_ok, tz=""):
    doms = ["social_meet", "walk", "culture_event", "language_exchange", "coworking",
            "watch_together", "games", "sport_activity", "professional_networking"]
    if dating_ok:
        doms.append("dating")
    # Тихие часы «22:00–09:00» — местные, и без смещения их не во что перевести. Здесь стояло
    # жёсткое 120, то есть Мадрид: пока все были из Барселоны, это совпадало и потому не мешало.
    # Человеку в Токио оно давало тишину среди дня и звонки среди ночи — и никакой ошибки при
    # этом не возникало, движок готовности просто считал не тот интервал.
    off = _tz_offset_min(tz)
    return {"status": "active", "allowed_domains": doms, "passive_outreach": True,
            "quiet_hours": {"start": "22:00", "end": "09:00",
                            "tz_offset_min": 120 if off is None else off},
            "paused_until": None}


def _valid_ts(s):
    """A paused_until string is valid only if it parses as epoch seconds or 'YYYY-MM-DDTHH:MM'."""
    s = str(s).strip()
    try:
        float(s)
        return True
    except ValueError:
        pass
    try:
        time.strptime(s[:16], "%Y-%m-%dT%H:%M")
        return True
    except (ValueError, TypeError):
        return False


_RECV_STATUSES = ("active", "busy", "paused")
_RECV_DOMAINS = {"social_meet", "walk", "games", "language_exchange", "sport_activity",
                 "culture_event", "professional_networking", "watch_together", "coworking", "dating"}

def update_receiving(name, patch):
    """The user's own availability settings — a WHITELISTED patch of their receiving policy
    (status / passive_outreach / allowed_domains / quiet_hours / paused_until), atomic on the
    shared store. Unknown fields are dropped, never written."""
    key = str(name or "").strip().lower()
    if not key:
        return {"ok": False, "error": "name required"}
    clean = {}
    st = str(patch.get("status") or "").lower()
    if st in _RECV_STATUSES:
        clean["status"] = st
    if isinstance(patch.get("passive_outreach"), bool):
        clean["passive_outreach"] = patch["passive_outreach"]
    doms = patch.get("allowed_domains")
    if isinstance(doms, list):
        keep = [d for d in (str(x).strip().lower() for x in doms) if d in _RECV_DOMAINS]
        if keep:
            clean["allowed_domains"] = keep
    q = patch.get("quiet_hours")
    if isinstance(q, dict):
        qh = {}
        for f in ("start", "end"):
            v = str(q.get(f) or "")
            # HH:MM with a REAL clock time (00:00-23:59); "99:99" must be rejected, not stored
            if (len(v) == 5 and v[2] == ":" and v[:2].isdigit() and v[3:].isdigit()
                    and 0 <= int(v[:2]) <= 23 and 0 <= int(v[3:]) <= 59):
                qh[f] = v
        if isinstance(q.get("tz_offset_min"), (int, float)) and -720 <= q["tz_offset_min"] <= 840:
            qh["tz_offset_min"] = int(q["tz_offset_min"])
        if qh:
            clean["quiet_hours"] = qh
    if "paused_until" in patch:
        pu = patch["paused_until"]
        if pu is None or isinstance(pu, (int, float)):
            clean["paused_until"] = pu
        elif isinstance(pu, str) and _valid_ts(pu):     # accept epoch or 'YYYY-MM-DDTHH:MM', drop junk
            clean["paused_until"] = pu
    with _REG_LOCK:
        try:
            with open(USERS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            users = data.get("users") if isinstance(data, dict) else data
            if not isinstance(users, list):
                users = []
        except Exception:
            users = []
        me = next((x for x in users if str(x.get("name", "")).strip().lower() == key), None)
        if me is None:
            return {"ok": False, "error": "user not found"}
        r = me.get("receiving")
        if not isinstance(r, dict):
            r = _default_receiving(bool(me.get("datingOk")))
        if not clean:                                   # empty patch = read the current policy
            return {"ok": True, "receiving": r}
        merged = dict(r)
        merged.update({k: v for k, v in clean.items()
                       if k != "quiet_hours"})
        if "quiet_hours" in clean:
            merged["quiet_hours"] = dict(r.get("quiet_hours") or {}, **clean["quiet_hours"])
        me["receiving"] = merged
        _persist_users(users, touched=me)
    return {"ok": True, "receiving": merged}




def _read_users():
    """Все люди: из базы, если она ведущая, иначе из файла."""
    if db.ENABLED:
        try:
            rows = db.load_users()
            if rows:
                return rows
            # База пуста — перенос ещё не делали. Падаем на файл, а не отдаём пустую популяцию:
            # пустой ответ здесь выглядит как «все пользователи пропали».
        except Exception as e:
            print("[users] postgres недоступен, читаю файл: %s: %s" % (type(e).__name__, str(e)[:120]))
    try:
        with open(USERS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        users = data.get("users") if isinstance(data, dict) else data
        return users if isinstance(users, list) else []
    except Exception:
        return []


def _persist_users(users, touched=None):
    """Сохранить популяцию.

    ГЛАВНОЕ ЗДЕСЬ — `touched`. В базе пишется ОДНА строка того человека, которого правили, а не
    все семьсот: регистрация Sofia не имеет никакого отношения к строкам остальных, и переписывать
    их значило бы ровно ту стену, из-за которой всё и затевалось. Без `touched` (перенос, массовая
    правка) пишется пачка одной транзакцией.

    Файл остаётся зеркалом, пока KLEAL_DB=mirror, и единственным хранилищем при KLEAL_DB=json.
    """
    wrote = False
    if db.ENABLED:
        try:
            if touched is not None:
                db.save_user(touched)
            else:
                db.save_users(users)
            wrote = True
        except Exception as e:
            print("[users] запись в postgres не удалась, падаю на файл: %s: %s"
                  % (type(e).__name__, str(e)[:120]))
    if wrote and not db.MIRROR_JSON:
        return True
    tmp = USERS_PATH + ".tmp"
    os.makedirs(os.path.dirname(os.path.abspath(USERS_PATH)), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"users": users}, f, ensure_ascii=False)
    os.replace(tmp, USERS_PATH)
    return True


def get_user(name):
    key = str(name or "").strip().lower()
    if not key:
        return None
    for x in _read_users():
        if str(x.get("name", "")).strip().lower() == key:
            return x
    return None


# The whole point of the whitelist: the profile client pushes edits here, and only fields a person
# actually owns may change — never source/verified/paused or other trust-bearing flags.
# Deliberately ABSENT and never to be added: verified, datingOk, paused, pending, blocksMe,
# declinedOwnerDaysAgo, source, role. Those are the hard gates in matching/app.py — a client patch
# that could set them could make a person invisible to everyone with no trace on screen.
# `tz` — часовой пояс человека, именем зоны (Europe/Madrid). Спека: «Таймзона в UI — только при
# РАСХОЖДЕНИИ», а расхождение не с чем было считать: свой пояс устройство знает, чужой не хранился
# нигде, и кадры O.14/O.21 со строкой «20:00 Barcelona · 19:00 London» показать было физически
# нечем. Имя зоны, а не смещение: смещение меняется дважды в год, а зона — нет.
_PATCH_FIELDS = {"age", "gender", "area", "country", "radiusKm", "lat", "lon", "langs", "interests",
                 "goals", "formats", "summary", "story", "personality", "persona", "vibe", "safety",
                 "tz"}
INTERESTS_MAX = 20      # сколько интересов доезжает до строки, по которой ищут; см. _canon_interests
STORY_MAX = 4000        # a life story, not a novel — and update_user writes straight into the row
PROSE_MAX = 900         # what buddy actually returns for a summary / personality paragraph

# The personality test's own record: a closed vocabulary per axis. An unrecognised token is DROPPED,
# never defaulted — a default here would be the profile asserting something nobody answered.
# friction / lull / give were added when the test was rewritten from preference questions to
# behavioural ones: what someone DOES when a plan collapses, what they do with a silence, and what
# they bring rather than what they want. `pace` gained "mirror" (opens up in answer to the other
# person) and lost "depends" — the client no longer offers a non-answer on any axis, because a
# non-answer used to arrive as null and was never stored at all.
_PERSONA_AXES = {
    "energy":    ("energised", "drained", "depends"),
    "group":     ("one", "small", "crowd"),
    "depth":     ("deep", "light", "practical"),
    "firstMeet": ("talk", "doing", "event"),
    "pace":      ("fast", "slow", "mirror", "depends"),
    "planning":  ("advance", "spontaneous", "flexible"),
    "friction":  ("reschedule", "wait", "letgo"),
    "lull":      ("fill", "allow", "uneasy"),
    "give":      ("listen", "fun", "reliable", "instigate"),
    "seek":      ("long", "interest", "wider"),
}


def _clean_persona(p):
    """Accept BOTH shapes: the wrapped {"v":1,"axes":{...}} and a bare {axis: token} dict.

    The test screen sends the bare form, and this function only ever looked for `.axes` — so every
    axis a user answered was dropped on the way in and the row got {"v":1,"axes":{}}. It was
    invisible from the app (which keeps its own copy in device state) and visible only in the store,
    where exactly that empty record sits next to an older wrapped one that came through fine."""
    if not isinstance(p, dict):
        return None
    axes = p.get("axes") if isinstance(p.get("axes"), dict) else \
        {k: v for k, v in p.items() if k in _PERSONA_AXES}
    keep = {k: v for k, v in axes.items() if k in _PERSONA_AXES and v in _PERSONA_AXES[k]}
    out = {"v": 1, "axes": keep}
    if isinstance(p.get("takenAt"), (int, float)):
        out["takenAt"] = int(p["takenAt"])
    return out


def update_user(name, patch):
    key = str(name or "").strip().lower()
    if not key or not isinstance(patch, dict):
        return {"ok": False, "error": "name and patch required"}
    clean = {k: v for k, v in patch.items() if k in _PATCH_FIELDS}
    # update_user does a blind row.update(), so every free-text field a person can type without any
    # form validation gets its own guard: a string, capped, or not written at all.
    for _k, _cap in (("story", STORY_MAX), ("personality", PROSE_MAX), ("summary", PROSE_MAX)):
        if _k in clean:
            if isinstance(clean[_k], str):
                clean[_k] = clean[_k][:_cap]
            else:
                clean.pop(_k)
    if "country" in clean:
        if isinstance(clean["country"], str) and clean["country"].strip():
            clean["country"] = clean["country"].strip()[:80]
        else:
            clean.pop("country")
    if "persona" in clean:
        cp = _clean_persona(clean["persona"])
        if cp is None:
            clean.pop("persona")          # not a dict: leave whatever the row already holds
        else:
            clean["persona"] = cp
    if not clean:
        return {"ok": False, "error": "no editable fields in patch"}
    with _REG_LOCK:
        users = _read_users()
        row = next((x for x in users if str(x.get("name", "")).strip().lower() == key), None)
        if row is None:
            return {"ok": False, "error": "unknown user"}
        if isinstance(clean.get("interests"), list):
            requested = [str(x).strip().lower() for x in clean["interests"] if str(x).strip()]
            have = {str(x).strip().lower() for x in (row.get("interests") or []) if str(x).strip()}
            # A full-list profile sync may remove existing values or add governed catalogue keys.
            # Novel free text is accepted only after interest-confirm has already persisted the
            # canonical key in this row. A direct API request cannot bypass the confirmation UI.
            rejected = [x for x in requested if x not in have and not interest_norm.trusted_interest(x)]
            if rejected:
                return {"ok": False, "error": "unconfirmed interests", "interests": rejected[:6]}
            clean["interests"] = _canon_interests(requested) or requested
        row.update(clean)
        _persist_users(users, touched=row)
    return {"ok": True, "user": row}


def confirm_interest(name, token, owner_key=""):
    """Persist one schema-validated proposal after its owner explicitly confirms it."""
    rec = interest_norm.mark_confirmed(token, owner=owner_key)
    if not rec:
        return {"ok": False, "error": "interest proposal expired"}
    canonical = str(rec.get("canonical") or "").strip().lower()
    if not canonical:
        return {"ok": False, "error": "invalid interest proposal"}
    key = str(name or "").strip().lower()
    if not key:
        # During onboarding no user row exists yet. The receipt travels only in device state and is
        # validated again by register_profile before the first database write.
        return {"ok": True, "canonical": canonical, "label": rec.get("label"), "token": token,
                "persisted": False}
    with _REG_LOCK:
        users = _read_users()
        row = next((x for x in users if str(x.get("name", "")).strip().lower() == key), None)
        if row is None:
            return {"ok": True, "canonical": canonical, "label": rec.get("label"), "token": token,
                    "persisted": False}
        current = [str(x).strip().lower() for x in (row.get("interests") or []) if str(x).strip()]
        if canonical not in current:
            if len(current) >= INTERESTS_MAX:
                return {"ok": False, "error": "interest limit reached"}
            current.append(canonical)
        row["interests"] = _canon_interests(current) or current
        _persist_users(users, touched=row)
    return {"ok": True, "canonical": canonical, "label": rec.get("label"), "token": token,
            "persisted": True, "user": row}


def _owned_row(users, owner_key):
    """Строка, которая ПРИНАДЛЕЖИТ этому аккаунту. Ничья чужая сюда попасть не может.

    Два источника, и оба про владельца, а не про то, как человек назвался в запросе:

      1. `owner` в самой строке — его пишет эта же функция начиная с 28.08;
      2. `name` в записи аккаунта — его пишет `attach_profile`, и он существовал всегда. По нему
         находятся строки, заведённые ДО появления поля `owner`: аккаунт помнит, какую анкету к
         нему привязали, и подменить эту память из запроса нельзя.

    Порядок именно такой: собственная пометка надёжнее, привязка — совместимость со старым.
    """
    if not owner_key:
        return None
    mine = next((x for x in users if x.get("owner") == owner_key), None)
    if mine is not None:
        return mine
    try:
        with _ACC_LOCK:
            acc = _read_accounts().get(owner_key) or {}
    except Exception:
        acc = {}
    attached = str(acc.get("name") or "").strip().lower()
    if not attached:
        return None
    return next((x for x in users if str(x.get("name", "")).strip().lower() == attached), None)


def _fresh_uid(owner_key, users):
    """Идентификатор новой строки — от АККАУНТА, а не от имени.

    Пока он считался как sha1(имя), личностью человека было его имя: двое тёзок получали один и
    тот же id и одну строку на двоих, а посторонний перезаписывал чужой профиль, просто назвавшись
    так же. От аккаунта — устойчиво к переименованию и уникально по построению.

    Хвост удлиняется при столкновении: старые строки всё ещё носят id, посчитанные от имени, и
    совпадение с ними хоть и невероятно, но проверяется, а не предполагается.
    """
    taken = {str(x.get("id") or "") for x in users}
    base = hashlib.sha1(("acct:" + str(owner_key)).encode("utf-8")).hexdigest()
    for n in (8, 12, 16, 40):
        uid = "on" + base[:n]
        if uid not in taken:
            return uid
    return "on" + base


def my_profile_name(owner_key):
    """Имя строки, принадлежащей ЭТОМУ аккаунту, или пусто.

    ЗАЧЕМ ОНО ЕСТЬ. Ручки профиля принимали имя из ТЕЛА запроса и по нему находили строку — без
    единой проверки, чья она. Проверено живым запросом 28.08: посторонний без токена читал чужой
    профиль целиком (возраст, город, интересы) и переписывал его через `profile-update`. Знать надо
    было ровно одно — как человека зовут на экране.

    Сверять присланное имя с именем владельца было бы полумерой: тогда цель всё равно называет
    вызывающий, и любая будущая ручка снова забудет проверку. Здесь наоборот — цель определяет
    СЕССИЯ, а имя из тела не участвует вовсе. Подставить чужую строку физически нечем.

    Ищем через `_owned_row`: он знает и новые строки с полем `owner`, и старые — по имени,
    записанному в аккаунт при привязке.
    """
    if not str(owner_key or "").strip():
        return ""
    try:
        row = _owned_row(_read_users(), owner_key)
    except Exception:
        row = None
    return str((row or {}).get("name") or "")


def register_profile(profile, owner_key=""):
    """Записать анкету в общее хранилище. Строка одна на АККАУНТ. Атомарная запись.

    ЧТО ЗДЕСЬ БЫЛО СЛОМАНО (проверено живым запросом 28.08, две регистрации подряд):

      — личность строки считалась от ИМЕНИ (`sha1(name)`), поэтому двое тёзок делили один
        идентификатор и одну строку;
      — дедупликация шла по имени: приходящая анкета выбрасывала ВСЕ строки с таким именем;
      — сессия не требовалась вовсе: `owner_key` доезжал сюда, но использовался только для
        подтверждений интересов, а владение по нему не проверялось ни разу.

    Вместе это давало захват без пароля: зная одно лишь отображаемое имя, посторонний перезаписывал
    чужой профиль анонимным запросом — возраст, город, интересы, доступность. Хуже того, ветка
    `read_photo` ниже сохраняла уже лежащее фото, и подделанная строка наследовала настоящее лицо.

    Теперь: без сессии нельзя, своя строка ищется по владельцу, а имя остаётся просто подписью —
    тёзки живут рядом, каждый в своей строке.
    """
    # Сессия обязательна. Единственный экран, который её не ставил, — app/login.tsx, и он
    # недостижим: на маршрут '/login' в приложении не ведёт ни одна ссылка.
    if not str(owner_key or "").strip():
        raise ValueError("sign in required")
    # Имя проверяется ДО записи и по той же причине, что и подтверждения интересов: строка
    # уезжает в поиск, и починить её потом можно только через того же человека.
    if not _clean_name((profile or {}).get("name")):
        raise ValueError("invalid name")
    u = _profile_to_user(profile)
    ints = (profile or {}).get("interests") or {}
    confirmations = ints.get("confirmations") if isinstance(ints, dict) else {}
    confirmed_input = list(u.get("interests") or [])
    invalid = interest_norm.validate_confirmations(confirmed_input, confirmations, owner=owner_key)
    if invalid:
        raise ValueError("unconfirmed interests: " + ", ".join(invalid[:6]))
    u["interests"] = _canon_interests(u.get("interests")) or u.get("interests")
    with _REG_LOCK:
        try:
            with open(USERS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            users = data.get("users") if isinstance(data, dict) else data
            if not isinstance(users, list):
                users = []
        except Exception:
            users = []
        prior = _owned_row(users, owner_key)
        if prior is not None:
            # ИДЕНТИФИКАТОР СТАРОЙ СТРОКИ СОХРАНЯЕТСЯ, и это не косметика: по нему лежит файл
            # фотографии (photos/<id>.jpg) и на него ссылаются записи в хранилище матчинга.
            # Выдать существующему человеку новый id значило бы отвязать его от собственного лица.
            u["id"] = str(prior.get("id") or u["id"])
            users = [x for x in users if x is not prior]
        else:
            u["id"] = _fresh_uid(owner_key, users)
        u["owner"] = owner_key
        # Фотография обрабатывается ЗДЕСЬ, а не выше, потому что до этой строки идентификатор ещё
        # не известен: раньше он выводился из имени и был готов заранее. Повторный проход, пришедший
        # без фотографии, должен сохранить уже лежащую — иначе анкета молча стирает лицо.
        saved = save_photo(u["id"], (profile or {}).get("photo"))
        if saved:
            u["photo"] = saved
        elif read_photo(u["id"]):
            u["photo"] = photo_url(u["id"])
        users.append(u)
        _persist_users(users, touched=u)
    interest_norm.validate_confirmations(confirmed_input, confirmations, consume=True, owner=owner_key)
    return u


# ---------------------------------------------------------------- HTTP dispatcher (onboarding only)
# ---------------------------------------------------------------- mascot artwork (splash slides)
# The three poses the intro slides need, served from /assets/<name>.svg. They are duplicated from the
# profile service on purpose: every service here is a single self-contained file, and reaching across
# to :7073 would make the splash screen depend on another service being up just to draw itself.
ASSETS = {
    'match': '''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512" fill="none" role="img" aria-labelledby="matchTitle matchDesc"> <title id="matchTitle">Kleal mascot — match confirmed pose</title> <desc id="matchDesc">Kleal celebrates a mutual match with open arms and two connected route nodes.</desc> <defs> <linearGradient id="matchBody" x1="114" y1="66" x2="394" y2="447" gradientUnits="userSpaceOnUse"> <stop stop-color="#FF756A"/> <stop offset="0.55" stop-color="#FF5B55"/> <stop offset="1" stop-color="#E84242"/> </linearGradient> <radialGradient id="matchFace" cx="0" cy="0" r="1" gradientTransform="translate(224 153) rotate(54) scale(170 160)" gradientUnits="userSpaceOnUse"> <stop stop-color="#FFFDF5"/> <stop offset="1" stop-color="#F4E8D7"/> </radialGradient> <radialGradient id="matchGround"> <stop stop-color="#111217" stop-opacity="0.18"/> <stop offset="0.72" stop-color="#111217" stop-opacity="0.06"/> <stop offset="1" stop-color="#111217" stop-opacity="0"/> </radialGradient> </defs> <g id="kleal-match"> <ellipse cx="257" cy="451" rx="154" ry="24" fill="url(#matchGround)"/> <path d="M88 217c87-54 250-55 336 0" stroke="#FF5B55" stroke-width="6" stroke-linecap="round" stroke-dasharray="2 16"/> <path d="M257 35C161 35 91 105 91 195c0 56 24 95 61 121-23 44-15 94 23 126 30 25 70 18 87-21 20 39 64 44 95 15 31-29 41-70 24-108 49-11 78-46 75-85-3-43-36-70-78-69C374 91 323 35 257 35Z" fill="url(#matchBody)"/> <path d="M392 201c52-5 82 20 78 60-4 36-35 55-70 48-29-6-39-28-27-50 9-17 25-25 42-21 15 3 21 15 16 26-5 11-17 15-29 10" stroke="#E84242" stroke-width="25" stroke-linecap="round"/> <ellipse cx="255" cy="190" rx="118" ry="111" fill="url(#matchFace)"/> <path d="M200 191c9 11 20 11 29 0" stroke="#171920" stroke-width="8" stroke-linecap="round"/> <path d="M281 191c9 11 20 11 29 0" stroke="#171920" stroke-width="8" stroke-linecap="round"/> <path d="M230 227c17 21 36 21 53 0" stroke="#171920" stroke-width="8" stroke-linecap="round"/> <path d="M160 307c-41-8-75-36-83-70" stroke="url(#matchBody)" stroke-width="37" stroke-linecap="round"/> <path d="M352 307c41-8 75-36 83-70" stroke="url(#matchBody)" stroke-width="37" stroke-linecap="round"/> <circle cx="72" cy="222" r="16" fill="#FFF8EB" stroke="#FF5B55" stroke-width="8"/> <circle cx="440" cy="222" r="16" fill="#FFF8EB" stroke="#FF5B55" stroke-width="8"/> <path d="M209 414c-5 22-16 38-33 50" stroke="#E84242" stroke-width="34" stroke-linecap="round"/> <path d="M306 414c5 22 17 38 34 50" stroke="#E84242" stroke-width="34" stroke-linecap="round"/> <ellipse cx="166" cy="468" rx="31" ry="14" fill="#D9363C"/> <ellipse cx="350" cy="468" rx="31" ry="14" fill="#D9363C"/> <circle cx="114" cy="112" r="7" fill="#FF5B55"/> <path d="m398 105 7 12 13 2-10 9 3 13-13-6-12 6 2-13-9-9 13-2Z" fill="#FF5B55" opacity="0.72"/> </g> </svg>''',
    'primary': '''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512" fill="none" role="img" aria-labelledby="primaryTitle primaryDesc"> <title id="primaryTitle">Kleal mascot — primary welcome pose</title> <desc id="primaryDesc">Coral Kleal mascot facing forward and waving.</desc> <defs> <linearGradient id="primaryBody" x1="110" y1="62" x2="395" y2="448" gradientUnits="userSpaceOnUse"> <stop stop-color="#FF756A"/> <stop offset="0.55" stop-color="#FF5B55"/> <stop offset="1" stop-color="#E84242"/> </linearGradient> <radialGradient id="primaryFace" cx="0" cy="0" r="1" gradientTransform="translate(219 155) rotate(55) scale(175 166)" gradientUnits="userSpaceOnUse"> <stop stop-color="#FFFDF5"/> <stop offset="1" stop-color="#F4E8D7"/> </radialGradient> <linearGradient id="primaryHighlight" x1="150" y1="62" x2="210" y2="315" gradientUnits="userSpaceOnUse"> <stop stop-color="white" stop-opacity="0.34"/> <stop offset="1" stop-color="white" stop-opacity="0"/> </linearGradient> <radialGradient id="primaryGround"> <stop stop-color="#111217" stop-opacity="0.18"/> <stop offset="0.72" stop-color="#111217" stop-opacity="0.06"/> <stop offset="1" stop-color="#111217" stop-opacity="0"/> </radialGradient> </defs> <g id="kleal-primary"> <ellipse cx="256" cy="451" rx="159" ry="24" fill="url(#primaryGround)"/> <path d="M257 35C161 35 91 105 91 195c0 55 23 94 59 120-25 42-18 92 19 126 29 28 72 23 91-17 19 40 64 47 96 18 33-29 45-72 28-112 48-10 79-44 77-82-2-43-34-72-75-74C378 92 324 35 257 35Z" fill="url(#primaryBody)"/> <path d="M391 202c55-6 86 20 83 61-3 37-35 58-73 52-31-5-42-27-31-51 8-19 24-29 44-26 17 2 24 14 20 27-4 12-16 17-29 13" stroke="#E84242" stroke-width="26" stroke-linecap="round"/> <ellipse cx="255" cy="192" rx="118" ry="112" fill="url(#primaryFace)"/> <path d="M169 128c21-39 62-61 105-57" stroke="url(#primaryHighlight)" stroke-width="18" stroke-linecap="round" opacity="0.9"/> <ellipse cx="216" cy="191" rx="12" ry="18" fill="#171920"/> <ellipse cx="294" cy="191" rx="12" ry="18" fill="#171920"/> <path d="M237 229c12 13 26 13 38 0" stroke="#171920" stroke-width="8" stroke-linecap="round"/> <path d="M153 307c-38-10-66-39-64-72 1-24 18-43 39-42 17 1 29 13 28 29-1 15-12 24-24 31" stroke="url(#primaryBody)" stroke-width="36" stroke-linecap="round"/> <path d="M356 314c32-4 58-26 67-55" stroke="url(#primaryBody)" stroke-width="38" stroke-linecap="round"/> <path d="M412 249c6-12 16-20 30-25" stroke="#FF6C62" stroke-width="12" stroke-linecap="round"/> <circle cx="444" cy="223" r="8" fill="#FFF8EB"/> <path d="M205 410c-4 23-14 39-31 52" stroke="#E84242" stroke-width="34" stroke-linecap="round"/> <path d="M310 412c5 23 17 39 35 51" stroke="#E84242" stroke-width="34" stroke-linecap="round"/> <ellipse cx="166" cy="467" rx="32" ry="15" fill="#D9363C"/> <ellipse cx="355" cy="467" rx="32" ry="15" fill="#D9363C"/> <circle cx="378" cy="91" r="9" fill="#FFF8EB" opacity="0.55"/> </g> </svg>''',
    'searching': '''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512" fill="none" role="img" aria-labelledby="searchTitle searchDesc"> <title id="searchTitle">Kleal mascot — searching pose</title> <desc id="searchDesc">Kleal leans forward, looks to the right, and shades its eyes while searching for a good match.</desc> <defs> <linearGradient id="searchBody" x1="110" y1="70" x2="398" y2="445" gradientUnits="userSpaceOnUse"> <stop stop-color="#FF756A"/> <stop offset="0.56" stop-color="#FF5B55"/> <stop offset="1" stop-color="#E84242"/> </linearGradient> <radialGradient id="searchFace" cx="0" cy="0" r="1" gradientTransform="translate(247 157) rotate(57) scale(163 153)" gradientUnits="userSpaceOnUse"> <stop stop-color="#FFFDF5"/> <stop offset="1" stop-color="#F4E8D7"/> </radialGradient> <radialGradient id="searchGround"> <stop stop-color="#111217" stop-opacity="0.18"/> <stop offset="0.72" stop-color="#111217" stop-opacity="0.06"/> <stop offset="1" stop-color="#111217" stop-opacity="0"/> </radialGradient> </defs> <g id="kleal-searching" transform="rotate(-4 256 256)"> <ellipse cx="250" cy="451" rx="163" ry="24" fill="url(#searchGround)"/> <path d="M251 41C158 49 95 124 103 211c5 54 34 89 72 110-20 44-6 95 34 124 32 24 70 14 84-24 22 34 65 38 94 8 29-30 36-71 17-107 47-13 74-49 69-88-6-42-40-68-81-65-2-83-73-135-141-128Z" fill="url(#searchBody)"/> <path d="M403 198c51-8 82 15 81 54-1 36-30 57-66 53-29-3-41-25-31-48 8-17 23-27 40-25 16 2 23 13 20 25-3 11-14 17-27 14" stroke="#E84242" stroke-width="25" stroke-linecap="round"/> <ellipse cx="265" cy="193" rx="116" ry="109" transform="rotate(4 265 193)" fill="url(#searchFace)"/> <ellipse cx="237" cy="190" rx="12" ry="18" fill="#171920"/> <ellipse cx="312" cy="184" rx="12" ry="18" fill="#171920"/> <circle cx="241" cy="185" r="3.5" fill="white"/> <circle cx="316" cy="179" r="3.5" fill="white"/> <path d="M267 230c12 9 24 8 34-3" stroke="#171920" stroke-width="8" stroke-linecap="round"/> <path d="M337 147c29-31 59-36 84-17" stroke="url(#searchBody)" stroke-width="34" stroke-linecap="round"/> <path d="M396 126c22-8 43-3 57 13" stroke="#FF7166" stroke-width="17" stroke-linecap="round"/> <path d="M395 126c13 12 20 27 21 45" stroke="#E84242" stroke-width="13" stroke-linecap="round"/> <path d="M164 317c-38-7-65-31-65-61 0-22 15-39 35-39 17 0 29 11 29 27 0 14-10 24-22 29" stroke="url(#searchBody)" stroke-width="35" stroke-linecap="round"/> <path d="M218 416c-17 22-38 35-63 39" stroke="#E84242" stroke-width="34" stroke-linecap="round"/> <path d="M315 414c20 19 43 29 68 29" stroke="#E84242" stroke-width="34" stroke-linecap="round"/> <ellipse cx="143" cy="457" rx="33" ry="14" transform="rotate(-12 143 457)" fill="#D9363C"/> <ellipse cx="394" cy="444" rx="33" ry="14" transform="rotate(8 394 444)" fill="#D9363C"/> <circle cx="441" cy="92" r="8" fill="#FF5B55"/> <circle cx="470" cy="82" r="5" fill="#FF5B55" opacity="0.48"/> </g> </svg>''',
}


# ---------------------------------------------------------------- лист ожидания (лендинг kleal.app)
#
# Отдельный файл, а не таблица аккаунтов: это не пользователи, а адреса, которые попросили написать
# им один раз. Смешивать их с аккаунтами значило бы, что запись в лист похожа на регистрацию — а
# она ею не является ни на сервере, ни для человека.
WAITLIST_PATH = os.environ.get("KLEAL_WAITLIST",
                               os.path.join(os.path.dirname(ACCOUNTS_PATH), "waitlist.json"))
_WL_LOCK = threading.Lock()
_WL_IP = {}
_WL_IP_PER_HOUR = 30


def join_waitlist(email, source="", ip=""):
    """Записать адрес. Повтор — НЕ ошибка: человек нажал дважды или пришёл со второго устройства,
    и «ты уже здесь» для него такой же успех, как и первая запись."""
    e = _norm_email(email)
    if not valid_email(e):
        return {"ok": False, "error": "bad email"}
    now = time.time()
    with _WL_LOCK:
        hits = [t for t in _WL_IP.get(str(ip or "?"), []) if t > now - 3600]
        if len(hits) >= _WL_IP_PER_HOUR:
            return {"ok": False, "error": "too many"}
        hits.append(now)
        _WL_IP[str(ip or "?")] = hits
        try:
            with open(WAITLIST_PATH, "r", encoding="utf-8") as f:
                rows = json.load(f)
            rows = rows if isinstance(rows, list) else []
        except Exception:
            rows = []
        if any(_norm_email((r or {}).get("email")) == e for r in rows):
            return {"ok": True, "already": True}
        rows.append({"email": e, "source": str(source or "")[:40], "at": int(now)})
        try:
            tmp = WAITLIST_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False)
            os.replace(tmp, WAITLIST_PATH)
        except Exception as ex:
            return {"ok": False, "error": "save failed", "detail": str(ex)[:120]}
    return {"ok": True, "already": False, "count": len(rows)}


def waitlist_count():
    try:
        with open(WAITLIST_PATH, "r", encoding="utf-8") as f:
            rows = json.load(f)
        return len(rows) if isinstance(rows, list) else 0
    except Exception:
        return 0


# ------------------------------------------------- лендинг листа ожидания (kleal.app)
#
# Отдаётся отсюда по той же причине, что и фотографии профиля: этот сервис уже владеет
# записью адресов, а шлюз пробрасывает его пути без изменений. Отдельный сервис ради одной
# страницы был бы ещё одним процессом, который надо помнить перезапускать.
#
# Вид снят с кадров «IG · Feed» борда: чёрный фон, коралл #F13A59, Zalando Sans Expanded.
WAITLIST_HTML = '<title>Kleal Waitlist</title>\n<link rel="preconnect" href="https://fonts.googleapis.com">\n<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Zalando+Sans+Expanded:wght@400;500;700&display=swap">\n\n<style>\n  /*\n    Страница — это САМА КАМПАНИЯ, а не сайт про кампанию.\n    Значения не подобраны на глаз: чёрный фон, коралл #F13A59, заголовок 96/700, надзаголовок\n    34/700 с разрядкой 2 и подпись 44/400 сняты прямо с кадров «IG · Feed» борда Kleal.\n    Поэтому панели идут в пропорции поста 4:5 и собраны той же лесенкой — надзаголовок,\n    утверждение, подпись, кнопка, подпись автора.\n\n    Тема одна и намеренно: это рекламная поверхность, а не документ. Раз так — фон и каждый цвет\n    выставлены явно, чтобы страница не одолжила чужой фон, куда бы её ни вставили.\n  */\n  :root {\n    --ink:    #000000;   /* земля — как у постов */\n    --rise:   #140A0D;   /* приподнятая поверхность: почти чёрный со сдвигом в коралл */\n    --coral:  #F13A59;   /* единственный акцент, снят с кадра */\n    --paper:  #F7F8FA;   /* крупные утверждения */\n    --white:  #FFFFFF;   /* обычный текст */\n    --ash:    #9EA6AD;   /* служебное: подписи, сноски */\n    --hair:   rgba(255, 255, 255, 0.14);\n\n    --face: \'Zalando Sans Expanded\', \'Helvetica Neue\', Arial, sans-serif;\n\n    /* Кегли текучие: на кадре 1080 в ширину, здесь ширина любая. */\n    --statement: clamp(38px, 8.4vw, 96px);\n    --lead:      clamp(17px, 3.1vw, 34px);\n    --eyebrow:   clamp(12px, 1.5vw, 17px);\n    --handle:    clamp(13px, 1.6vw, 18px);\n  }\n\n  * { box-sizing: border-box; }\n\n  html { -webkit-text-size-adjust: 100%; }\n\n  body {\n    margin: 0;\n    background: var(--ink);\n    color: var(--white);\n    font-family: var(--face);\n    font-weight: 400;\n    line-height: 1.35;\n    -webkit-font-smoothing: antialiased;\n  }\n\n  /* ---- панель = один пост -------------------------------------------------------------- */\n  .feed {\n    display: flex;\n    flex-direction: column;\n    align-items: center;\n    gap: 0;\n  }\n\n  .post {\n    position: relative;\n    width: 100%;\n    max-width: 720px;\n    aspect-ratio: 4 / 5;\n    min-height: 560px;\n    display: flex;\n    flex-direction: column;\n    justify-content: flex-end;\n    gap: clamp(18px, 2.6vw, 34px);\n    padding: clamp(28px, 5vw, 64px);\n    overflow: hidden;\n    border-bottom: 1px solid var(--hair);\n    background: var(--ink);\n  }\n\n  /* Квадратный пост 1:1 — на борде это отдельный формат «statement». */\n  .post.square { aspect-ratio: 1 / 1; }\n\n  /*\n    Свечение вместо фотографии. На борде у постов лежит картинка; своей у страницы нет, а\n    заглушка-стоковое фото выглядела бы дешевле пустоты. Поэтому — мягкий коралловый источник\n    света: он держит ту же композицию и не притворяется съёмкой.\n  */\n  .post::before {\n    content: "";\n    position: absolute;\n    inset: 0;\n    background:\n      radial-gradient(120% 80% at 18% 8%, rgba(241, 58, 89, 0.30) 0%, rgba(241, 58, 89, 0) 58%),\n      radial-gradient(90% 70% at 92% 96%, rgba(241, 58, 89, 0.16) 0%, rgba(241, 58, 89, 0) 62%);\n    pointer-events: none;\n  }\n  .post > * { position: relative; z-index: 1; }\n\n  .eyebrow {\n    margin: 0;\n    font-size: var(--eyebrow);\n    font-weight: 700;\n    letter-spacing: 0.12em;\n    text-transform: uppercase;\n    color: var(--coral);\n  }\n\n  .statement {\n    margin: 0;\n    font-size: var(--statement);\n    font-weight: 700;\n    line-height: 1.04;\n    letter-spacing: -0.015em;\n    color: var(--paper);\n    text-wrap: balance;\n  }\n\n  .lead {\n    margin: 0;\n    max-width: 26ch;\n    font-size: var(--lead);\n    font-weight: 400;\n    line-height: 1.32;\n    color: var(--white);\n  }\n\n  .foot {\n    display: flex;\n    align-items: center;\n    justify-content: space-between;\n    gap: 16px;\n    margin-top: clamp(6px, 1.4vw, 16px);\n  }\n\n  .handle {\n    font-size: var(--handle);\n    font-weight: 400;\n    color: var(--white);\n    opacity: 0.82;\n  }\n\n  /*\n    Логотип — словом, а не картинкой: одна гарнитура на всю страницу, и грузить нечего.\n    Без цветной буквы внутри: коралловая «l» посреди белого слова читается как «kIeal», то есть\n    как сбой отрисовки, а не как знак. Проверено на живой странице.\n  */\n  .mark {\n    font-size: clamp(15px, 1.9vw, 22px);\n    font-weight: 700;\n    letter-spacing: -0.02em;\n    color: var(--white);\n  }\n\n  .cta {\n    display: inline-flex;\n    align-items: center;\n    justify-content: center;\n    align-self: flex-start;\n    padding: clamp(12px, 1.6vw, 20px) clamp(20px, 3vw, 38px);\n    border: 0;\n    border-radius: 999px;\n    background: var(--coral);\n    color: var(--white);\n    font-family: var(--face);\n    font-size: clamp(14px, 1.9vw, 22px);\n    font-weight: 700;\n    text-decoration: none;\n    cursor: pointer;\n    transition: transform 0.14s ease, filter 0.14s ease;\n  }\n  .cta:hover { filter: brightness(1.08); }\n  .cta:active { transform: translateY(1px); }\n  .cta:focus-visible { outline: 3px solid var(--white); outline-offset: 3px; }\n\n  /* ---- последняя панель: кнопка становится формой ------------------------------------- */\n  .join { background: var(--rise); }\n\n  .form {\n    display: flex;\n    flex-wrap: wrap;\n    gap: 10px;\n    width: 100%;\n    max-width: 560px;\n  }\n\n  .field {\n    flex: 1 1 240px;\n    min-width: 0;\n    padding: clamp(12px, 1.6vw, 20px) clamp(16px, 2vw, 24px);\n    border: 1px solid var(--hair);\n    border-radius: 999px;\n    background: rgba(255, 255, 255, 0.04);\n    color: var(--white);\n    font-family: var(--face);\n    font-size: clamp(14px, 1.8vw, 20px);\n    font-weight: 400;\n  }\n  .field::placeholder { color: var(--ash); }\n  .field:focus { outline: none; border-color: var(--coral); }\n  .field:focus-visible { outline: 2px solid var(--coral); outline-offset: 2px; }\n\n  .note {\n    margin: 0;\n    min-height: 1.4em;\n    font-size: var(--handle);\n    color: var(--ash);\n  }\n  .note.bad { color: var(--coral); }\n  .note.good { color: var(--paper); }\n\n  .fineprint {\n    margin: 0;\n    font-size: clamp(11px, 1.3vw, 14px);\n    color: var(--ash);\n    max-width: 44ch;\n  }\n\n  /*\n    ПЕРЕНОСЫ С БОРДА — ДЛЯ ШИРИНЫ БОРДА. На кадре пост 1080 в ширину, и разбивка строк там часть\n    композиции. На телефоне те же <br> рвут фразу не по смыслу: «Rooftop / tapas / in Gràcia — /\n    six spots». Поэтому ниже 560 они отключаются, и текст переносится сам. Проверено на 375.\n  */\n  @media (max-width: 560px) {\n    .statement br, .lead br { display: none; }\n    .statement { letter-spacing: -0.02em; }\n  }\n\n  @media (prefers-reduced-motion: reduce) {\n    .cta { transition: none; }\n  }\n</style>\n\n<main class="feed">\n\n  <!-- Пост 1 — type-led. Разбивка строк как на кадре: она часть композиции, а не перенос. -->\n  <section class="post">\n    <p class="eyebrow">Barcelona — Sat 19:30</p>\n    <h1 class="statement">Coffee<br>with 4 people<br>who love padel</h1>\n    <p class="lead">Your agent found the plan.<br>You just show up.</p>\n    <a class="cta" href="#join">Join the waitlist</a>\n    <div class="foot">\n      <span class="handle">@kleal / kleal.app</span>\n      <span class="mark">kleal</span>\n    </div>\n  </section>\n\n  <!-- Пост 2 — image-led: надзаголовок снизу, утверждение крупнее подписи. -->\n  <section class="post">\n    <p class="eyebrow">Thu 20:00 · Group of 6</p>\n    <h2 class="statement">Rooftop tapas<br>in Gràcia — six spots</h2>\n    <a class="cta" href="#join">Get a spot</a>\n    <div class="foot">\n      <span class="handle">@kleal / kleal.app</span>\n      <span class="mark">kleal</span>\n    </div>\n  </section>\n\n  <!-- Пост 3 — квадратный statement. -->\n  <section class="post square">\n    <p class="eyebrow">Kleal — your social agent in Barcelona</p>\n    <h2 class="statement">Less swiping.<br>More real plans.</h2>\n    <div class="foot">\n      <span class="handle">@kleal / kleal.app</span>\n      <span class="mark">kleal</span>\n    </div>\n  </section>\n\n  <!-- Пост 4 — тот же формат, но кнопка здесь работает. -->\n  <section class="post square join" id="join">\n    <p class="eyebrow">Opening in Barcelona</p>\n    <h2 class="statement">Get in before<br>the city fills up.</h2>\n    <p class="lead">Leave your email. We write once — when your part of the city opens.</p>\n\n    <form class="form" id="wl" novalidate>\n      <input class="field" id="email" type="email" name="email" inputmode="email"\n             autocomplete="email" autocapitalize="off" spellcheck="false"\n             placeholder="you@email.com" aria-label="Email">\n      <button class="cta" type="submit" id="go">Join the waitlist</button>\n    </form>\n    <p class="note" id="note" role="status" aria-live="polite"></p>\n    <p class="fineprint">One email about the launch. Nothing else, and nobody else gets the address.</p>\n\n    <div class="foot">\n      <span class="handle">@kleal / kleal.app</span>\n      <span class="mark">kleal</span>\n    </div>\n  </section>\n\n</main>\n\n<script>\n  /*\n    Форма отправляет адрес и говорит, что произошло. Три правила, каждое из-за реального провала\n    таких форм:\n      — адрес проверяется до отправки, иначе человек ждёт ответа на опечатку;\n      — кнопка блокируется на время запроса, иначе двойное нажатие шлёт два письма;\n      — отказ называется словами. «Что-то пошло не так» не даёт человеку ни одного действия.\n  */\n  (function () {\n    var form = document.getElementById(\'wl\');\n    var field = document.getElementById(\'email\');\n    var button = document.getElementById(\'go\');\n    var note = document.getElementById(\'note\');\n    var looksLikeEmail = function (v) { return /^[^@\\s]+@[^@\\s]+\\.[^@\\s]{2,}$/.test(String(v || \'\').trim()); };\n\n    var say = function (text, kind) {\n      note.textContent = text;\n      note.className = \'note\' + (kind ? \' \' + kind : \'\');\n    };\n\n    form.addEventListener(\'submit\', function (e) {\n      e.preventDefault();\n      var value = field.value.trim();\n      if (!looksLikeEmail(value)) {\n        say(\'That doesn’t look like an email. Check the address.\', \'bad\');\n        field.focus();\n        return;\n      }\n      button.disabled = true;\n      var was = button.textContent;\n      button.textContent = \'Sending…\';\n      say(\'\');\n\n      fetch(\'/api/waitlist\', {\n        method: \'POST\',\n        headers: { \'Content-Type\': \'application/json\' },\n        body: JSON.stringify({ email: value, source: \'landing\' })\n      })\n        .then(function (r) { return r.json().catch(function () { return {}; }); })\n        .then(function (d) {\n          if (d && d.ok) {\n            form.style.display = \'none\';\n            say(d.already\n              ? \'You’re already on the list. We’ll write when Barcelona opens.\'\n              : \'You’re on the list. We’ll write when Barcelona opens.\', \'good\');\n            return;\n          }\n          if (d && d.error === \'bad email\') say(\'That doesn’t look like an email. Check the address.\', \'bad\');\n          else if (d && d.error === \'too many\') say(\'Too many tries. Give it an hour.\', \'bad\');\n          else say(\'Couldn’t save that. Try again in a minute.\', \'bad\');\n        })\n        .catch(function () { say(\'No connection. Check your internet and try again.\', \'bad\'); })\n        .finally(function () { button.disabled = false; button.textContent = was; });\n    });\n  })();\n</script>\n'


def _bearer(handler):
    """Токен сессии из заголовка. Только из заголовка: в теле он попал бы в логи прокси и в
    историю запросов, а в строке запроса — ещё и в referer."""
    h = ""
    try:
        h = handler.headers.get("Authorization") or ""
    except Exception:
        return ""
    h = h.strip()
    return h[7:].strip() if h[:7].lower() == "bearer " else ""


def _client_ip(handler):
    """Источник запроса для счётчика частоты. За шлюзом видно только его адрес, поэтому сперва
    смотрим X-Forwarded-For — иначе весь мир считался бы одним отправителем."""
    try:
        fwd = (handler.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
        if fwd:
            return fwd[:64]
        return str(handler.client_address[0])[:64]
    except Exception:
        return "?"


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] == "/health":
            return send_json(self, 200, {"service": "onboarding", "ok": True,
                                         "storage": db.MODE})
        if self.path == "/":
            send(self, 200, WAITLIST_HTML, "text/html")
        elif self.path.split("?")[0] in ("/waitlist", "/join"):
            send(self, 200, WAITLIST_HTML, "text/html")
        elif self.path.split("?")[0].startswith("/api/onboarding/photo/"):
            # Profile photos. Served from here because this service owns the user store and therefore
            # owns the write; the gateway already forwards /api/onboarding/* untouched, so a photo is
            # reachable from every screen in the app without a new route anywhere.
            uid = self.path.split("?")[0][len("/api/onboarding/photo/"):]
            raw = read_photo(uid[:-len(".jpg")] if uid.endswith(".jpg") else uid)
            if raw is None:
                return send_json(self, 404, {})
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(raw)))
            # A photo is immutable for as long as it is that person's photo, and re-uploading writes
            # the same path — so revalidate rather than cache hard, or a changed avatar would stick.
            self.send_header("Cache-Control", "public, max-age=300")
            self.end_headers()
            self.wfile.write(raw)
        elif self.path.startswith("/assets/") and self.path.endswith(".svg"):
            art = ASSETS.get(self.path[len("/assets/"):-len(".svg")])
            if not art:
                return send_json(self, 404, {})
            b = art.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers(); self.wfile.write(b)
        else:
            send_json(self, 404, {})

    def do_POST(self):
        body = read_json(self)
        # ONE canonical name per endpoint. Every route used to be spelled out twice — under
        # /api/onboarding/* and under the /api/v2/* alias left from the kleal_v2 era — and the
        # callers picked between them at random: this service's own UI called /api/v2/chat but
        # /api/onboarding/register, the profile UI called /api/v2/receiving but
        # /api/onboarding/profile. The result was ten endpoints that were served and never
        # called, and no way to tell which spelling was real. The alias is now rewritten once,
        # here, so old clients (a phone holding a cached bundle) keep working while the
        # dispatcher below knows exactly one name for each thing.
        p = self.path
        if p.startswith("/api/v2/"):
            p = "/api/onboarding/" + p[len("/api/v2/"):]
        if p == "/api/onboarding/state":
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            send_json(self, 200, critical_status_v2(prof))
        elif p == "/api/onboarding/chat":
            prior = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            msgs = body.get("messages") if isinstance(body.get("messages"), list) else []
            try:
                send_json(self, 200, v2_chat(msgs, prior, body.get("lang")))
            except Exception as e:
                send_json(self, 200, {"reply": "I lost the connection for a second. Say that again?",
                                      "options": [], "profile": prior, "crit": critical_status_v2(prior),
                                      "error": str(e)[:200]})
        elif p == "/api/onboarding/summary":
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            try:
                send_json(self, 200, v2_summary(prof, body.get("lang") or "ru"))
            except Exception as e:
                send_json(self, 200, {"summary": "", "error": str(e)[:200]})
        elif p == "/api/onboarding/signup":
            return send_json(self, 200, signup(body.get("login"), body.get("password"), body.get("name")))
        elif p == "/api/onboarding/signin":
            return send_json(self, 200, signin(body.get("login"), body.get("password")))
        elif p == "/api/onboarding/attach":
            # Привязка по СЕССИИ, если она есть, и по логину иначе. Второй путь оставлен только для
            # старых сборок на телефонах: они про сессии не знают, а разлогинивать их выкладкой
            # нельзя. Новый клиент всегда шлёт токен.
            tok = _bearer(self)
            if tok:
                return send_json(self, 200, attach_profile_by_token(tok, body.get("name"),
                                                                    body.get("profile")))
            return send_json(self, 200, attach_profile(body.get("login"), body.get("name"), body.get("profile")))
        elif p == "/api/auth/code/request":
            return send_json(self, 200, request_code(body.get("email"), body.get("lang") or "en",
                                                     _client_ip(self)))
        elif p == "/api/auth/code/verify":
            return send_json(self, 200, verify_code(body.get("email"), body.get("code"),
                                                    body.get("lang") or "en"))
        elif p == "/api/auth/session":
            # «Кто я» по токену. Клиент зовёт на старте: сессия могла истечь или быть погашена.
            acc = session_owner(_bearer(self))
            if not acc:
                return send_json(self, 200, {"ok": False, "error": "no session"})
            prof = acc.get("profile") if isinstance(acc.get("profile"), dict) else None
            return send_json(self, 200, {"ok": True, "login": acc.get("login") or acc.get("_key"),
                                         "email": acc.get("email") or "", "name": acc.get("name") or "",
                                         "profile": prof, "hasProfile": bool(prof)})
        elif p == "/api/waitlist":
            return send_json(self, 200, join_waitlist(body.get("email"), body.get("source"),
                                                      _client_ip(self)))
        elif p == "/api/auth/signout":
            return send_json(self, 200, sign_out(_bearer(self)))
        elif p == "/api/onboarding/register":
            # everyone who finishes onboarding is written into the shared user store (matchable + in admin)
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            try:
                owner = session_owner(_bearer(self))
                send_json(self, 200, {"ok": True, "user": register_profile(
                    prof, (owner or {}).get("_key") or "")})
            except Exception as e:
                send_json(self, 200, {"ok": False, "error": str(e)[:200]})
        elif p == "/api/onboarding/profile":
            # Своя строка и только своя: цель берётся из сессии, `body["name"]` игнорируется.
            _owner = session_owner(_bearer(self))
            _mine = my_profile_name((_owner or {}).get("_key") or "")
            if not _mine:
                return send_json(self, 200, {"ok": False, "error": "sign in required"})
            _u = get_user(_mine)
            _resp = {"user": _u}
            # Подписи интересов на языке интерфейса. Ключи в строке английские; читатель
            # по-русски или по-испански получает словарь «ключ -> подпись» и рисует его.
            _lng = str(body.get("lang") or "").lower()
            if _u and _lng in ("ru", "es"):
                try:
                    import interest_i18n
                    _resp["interestLabels"] = interest_i18n.labels_for(_u.get("interests") or [], _lng)
                except Exception:
                    pass
            send_json(self, 200, _resp)
        elif p == "/api/onboarding/interest-normalize":
            owner = session_owner(_bearer(self))
            if not owner:
                return send_json(self, 200, {"ok": False, "status": "invalid", "error": "no session"})
            existing = body.get("existing") if isinstance(body.get("existing"), list) else []
            send_json(self, 200, interest_norm.normalize(
                body.get("text"), existing, body.get("lang") or "en", llm_complete, MODEL_ID,
                owner.get("_key") or ""))
        elif p == "/api/onboarding/interest-confirm":
            owner = session_owner(_bearer(self))
            if not owner:
                return send_json(self, 200, {"ok": False, "error": "no session"})
            requested_name = str(body.get("name") or "").strip()
            owned_name = str(owner.get("name") or "").strip()
            if requested_name and owned_name and requested_name.lower() != owned_name.lower():
                return send_json(self, 200, {"ok": False, "error": "profile does not belong to session"})
            send_json(self, 200, confirm_interest(
                requested_name, body.get("token"), owner.get("_key") or ""))
        elif p == "/api/onboarding/profile-update":
            try:
                owner = session_owner(_bearer(self))
                mine = my_profile_name((owner or {}).get("_key") or "")
                if not mine:
                    return send_json(self, 200, {"ok": False, "error": "sign in required"})
                send_json(self, 200, update_user(mine,
                                                 body.get("patch") if isinstance(body.get("patch"), dict) else {}))
            except Exception as e:
                send_json(self, 200, {"ok": False, "error": str(e)[:200]})
        elif p == "/api/onboarding/receiving":
            # availability settings = the user's receiving policy (Matching Core spec §4.4).
            # {name} alone reads the current policy; whitelisted fields update it atomically.
            try:
                owner = session_owner(_bearer(self))
                mine = my_profile_name((owner or {}).get("_key") or "")
                if not mine:
                    return send_json(self, 200, {"ok": False, "error": "sign in required"})
                send_json(self, 200, update_receiving(mine,
                                                      body.get("receiving") if isinstance(body.get("receiving"), dict) else {}))
            except Exception as e:
                send_json(self, 200, {"ok": False, "error": str(e)[:200]})
        else:
            send_json(self, 404, {})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Kleal onboarding-service on http://127.0.0.1:%d  (LLM via llm-service)" % PORT)
    ThreadingHTTPServer((config.BIND_HOST, PORT), H).serve_forever()
