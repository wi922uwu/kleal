# -*- coding: utf-8 -*-
# Kleal buddy-service — the CONVERSATIONAL agent the user chats with. It is their day-to-day AI on Kleal:
# it answers, riffs, recommends — and quietly accumulates their SIGNALS. When they clearly want to meet
# someone, it hands the request to the FILTRATION agent (categorisation) and then to the MATCHING agent
# (ranking), agent-to-agent over HTTP, and surfaces the ranked people back in the chat.
#
#   user <-> buddy (:7075) --HTTP--> filtration (:7076, categorise) --HTTP--> matching (:7074, rank)
#
# Holds NO model keys — reaches the LLM via shared/llm_client. Owner: shared (Dev A conversation, Dev B match).
#
# ── Division of labour ───────────────────────────────────────────────────────────────────────────
# buddy      : conversation, signals, session memory, the intent card the UI renders, humanised reasons,
#              and CANONICALISATION — making sure the intent it sends is one the ranker can actually score.
# filtration : magnetises free text to a category (incl. novel things: "labubu" -> toys_collectibles).
# matching   : ranking only (hard gates, tiers, weights, geo, feedback, negotiation).
# We never re-rank here and never invent people: if matching returns nobody, we say so and offer to widen.
#
# ── Why buddy canonicalises topics (this was a silent zero-match bug) ────────────────────────────
# matching resolves `topics` against ITS OWN English TAXONOMY (football/dota/coffee...). Two things reach
# it that it cannot resolve, and an unresolvable topic makes `_base_tier` return 'none' for EVERY candidate
# — i.e. zero matches, with no error anywhere:
#   1. Russian words. filtration's LLM usually translates, but its deterministic fallback scans
#      `[a-zA-Z]+` only, so on Cyrillic it yields nothing and the whole chain silently returns 0 people.
#   2. Novel items filtration is proud of ("labubu"): a great category, but a word the ranker never heard.
# So before calling matching we map topics onto the ranker's vocabulary (TOPIC_ALIASES + BROAD_OF), fall
# back to a category bridge, and if there is still nothing rankable we say so honestly instead of pretending.
# The user's own words are kept for the card (`tags`), and the reply is written in the user's language.
#
# ── Contract (a SUPERSET — the existing profile-service UI keeps working unchanged) ──────────────
# POST /api/buddy/chat
#   stateless (profile UI) : {messages:[{role,content}], profile:{}, signals:{}}
#   stateful  (thin client): {user_id, message, profile?}     <- buddy keeps the thread + signals itself
#   -> {reply, signals, lang,
#       match:{intent, top, candidates, fallback} | null,      # legacy shape the profile UI renders
#       intent, matches, tool_call, category}                  # + intent card, ranked list, filtration result
# POST /api/buddy/launch  {user_id|intent, override?}  -> "Launch search": match + the candidates' agents
#                                                          negotiate -> verdicts (accept/decline + opener)
# POST /api/buddy/intro    {intent, candidate}         -> icebreaker (delegated to matching)
# POST /api/buddy/feedback {name, decision}            -> teach the ranker (delegated to matching)
# POST /api/buddy/onboard  {user_id, profile}          -> {summary, signals}: seed buddy from onboarding
# GET  /api/buddy/health | /api/buddy/state?user_id=   -> ops
# Every route is also served bare (/buddy/*) and CORS is open, so a cross-origin frontend can call it
# directly, not only through the gateway.
import os
import re
import sys
import json
import threading
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "..", "..", "shared"), os.path.join(_HERE, "shared")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
import kleal_lib as base                      # base._extract_json (keyless)
from llm_client import llm_complete, llm_stream
from http_util import send_json, read_json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("BUDDY_PORT", "7075"))
MODEL_ID = os.environ.get("V2_MODEL", "llama_self")
MATCH_URL = os.environ.get("MATCH_URL", "http://127.0.0.1:7074").rstrip("/")
FILTER_URL = os.environ.get("FILTER_URL", "http://127.0.0.1:7076").rstrip("/")
STORE_PATH = os.environ.get("BUDDY_STORE", os.path.join(_HERE, "buddy_store.json"))

SIGNAL_KEYS = ("topics", "role", "type", "vibe", "languages", "time", "area", "datingOk", "dealBreakers", "interest")
LIST_KEYS = ("topics", "languages", "dealBreakers")

# ── When buddy SEARCHES vs just chats ──────────────────────────────────────────────────────────────
# Buddy is a general assistant FIRST; it should create an intent + look for people only on an EXPLICIT ask,
# never just because an activity was mentioned. The 70B's own "match" flag is unreliable in both directions
# (misses real asks; fires on plain chat), so the trigger is deterministic and two-tiered:
#   STRONG  — an unmistakable ask to find/meet people (найди, ищу с кем, find me, who wants, teammate…)
#             -> always search.
#   COMPANION — a softer "with someone" cue (с кем, кто-нибудь, someone to…)
#             -> search only if the model ALSO flagged match, so a stray cue in chat doesn't fire.
# Bare activity words ("поиграть", "футбол", "together", "play") never trigger on their own — that was the
# bug: "мы вчера поиграли в футбол вместе" and "давай сыграем в шахматы" (with Buddy!) both created intents.
_STRONG_ASK = re.compile(
    r"найд[иёе]|найти\b|подбер[иёе]|свед[иё]|познаком|"
    r"ищу\s+(кого|с\s+кем|людей|компан|напарник|партн[её]р|тиммейт|игрок)|"
    r"кто\s+хочет|кто-нибудь\s+хочет|кто\s+со\s+мной|есть\s+кто|нужен\s+напарник|напарник|тиммейт|"
    r"find\s+(me\b|someone|people|players?|a\s+(teammate|partner|buddy|group))|"
    r"looking\s+for\s+(someone|people|players?|a\s+(teammate|partner|buddy|group))|"
    r"who\s+wants|who'?s\s+(up\s+for|down\s+for)|anyone\s+(want|up\s+for|keen|down)|"
    r"match\s+me|connect\s+me|introduce\s+me|hook\s+me\s+up|teammate", re.I)
_COMPANION = re.compile(
    r"с\s+кем|кого-нибудь|кто-нибудь|компани[юе]|"
    r"someone\s+to\b|somebody\s+to\b|people\s+to\b|with\s+(someone|somebody|people)", re.I)
# language-exchange asks read as "I want a person to practise with" even without a STRONG verb —
# "практиковать испанский с носителем" / "language partner" should search, not just chat.
_STRONG_ASK_EXTRA = re.compile(
    r"с\s+носител|носител[ья]\s+язык|языков\w*\s+обмен|language\s+(partner|exchange)|"
    r"practi[cs]e\s+\w+\s+with|language\s+buddy", re.I)


# DESIRE — first-person, forward-looking wish to DO something ("хочу выпить кофе", "I want to play
# padel"). Tier-2 like COMPANION: it fires only with the model's agreement, because the wording alone
# is ambiguous. Without this tier the most natural way to ask — the way the product is demoed — was
# answered with small talk forever: an end-to-end probe of six ordinary phrases produced ONE search
# in six, and three turns of "не важно, давай искать" never got there either.
# Deliberately excluded: past tense ("мы вчера поиграли"), and "давай …" imperatives, which address
# Buddy itself rather than describe a wish — both used to create intents and were fixed once already.
_DESIRE = re.compile(
    r"(^|[\s,.:;!?—-])(хочу|хочется|хотел[аи]?\s+бы|мечтаю|планиру[юе]|собира[юе]сь|"
    r"не\s+прочь|было\s+бы\s+круто|"
    r"i\s+want\s+to|i'?d\s+like\s+to|i\s+wanna|want\s+to\s+go|planning\s+to|thinking\s+of)\b", re.I)
_PAST = re.compile(r"вчера|позавчера|на\s+прошлой\s+неделе|yesterday|last\s+(week|night|time)", re.I)


def _names_an_activity(text):
    """Does the user's own text contain a word the ranker can actually resolve?

    Deliberately NOT the model's extraction. Gating the desire tier on `signals.interest` made the
    product a coin flip: at temperature 0.6 the same «хочу выпить кофе» searched on one turn and
    made small talk on the next, which from outside is indistinguishable from a broken matcher.
    The user's words are the same every time, so the trigger reads those.
    """
    for piece in re.split(r"[^\w'-]+", str(text or "").lower()):
        if piece and norm_topic(piece):
            return True
    return False


def wants_people(text, model_flagged):
    """Deterministic search trigger. STRONG ask always; COMPANION needs the model's agreement;
    DESIRE needs a resolvable activity in the user's own words."""
    t = str(text or "")
    if _STRONG_ASK_EXTRA.search(t):
        return True
    if _STRONG_ASK.search(t):
        return True
    if model_flagged and _COMPANION.search(t):
        return True
    return bool(_DESIRE.search(t) and not _PAST.search(t) and _names_an_activity(t))

BUDDY_PROMPT = '''You are "Kleal" — the user's buddy: a warm, smart, genuinely helpful companion they can chat with like they would with ChatGPT. Talk naturally (1-4 sentences). Be actually useful: answer questions, riff on ideas, recommend things, help them think — about anything, not only meeting people. You are their day-to-day AI on the Kleal platform. (Deeper tools like web research come later.)

Kleal's superpower is connecting people. So while you chat, quietly notice the user's SIGNALS when they naturally come up (ONLY what they actually reveal — never invent):
- vibe: chill, energetic, competitive, intellectual, creative, social, calm
- languages: 2-letter codes (e.g. ["en","es"])
- time: when they are free (e.g. "today evening", "weekend")
- area: their neighbourhood / city if mentioned
- datingOk: true ONLY if they clearly want dating / romance
- dealBreakers: anything they say they want to avoid
- interest: a short phrase for the thing they're talking about wanting to do with someone (e.g. "play chess", "labubu collectors", "practise spanish")

Set "match": true ONLY when the user clearly wants to MEET a person / find people / do an activity WITH someone. For normal conversation keep it false and just be a great chatbot. When match is true, put a short natural-language description of what they want into "interest" (another agent will categorise it).

Known so far (baseline from their profile): __SIG__
You ALREADY KNOW this person — that block is their profile. Never ask for anything already in it: not
their name, not their city, not their languages. If "name" is there, address them by it naturally
instead of asking who they are.

Reply as ONE JSON object only, nothing outside it:
{"reply":"<your natural, helpful message>","signals":{<only fields you newly learned THIS turn; may include "interest">},"match":true|false}

LANGUAGE: write "reply" in the SAME language the user writes in (they write Russian -> you answer in Russian). Every other value — signals, interest, topics, time, area — stays in ENGLISH, because the filtration and matching agents only understand English.

MEMORY: the conversation you are given is the WHOLE history — there is nothing before it. Never refer to things "we already talked about", never say "as I said" or "снова"/"again", and never claim to remember a person or a topic that is not in the text above. If the history starts with [FIRST MESSAGE], this person is talking to you for the very first time: greet them as a new acquaintance.'''


# ======================= CANONICALISATION (make the intent rankable) =======================
# RU (and loose EN) surface forms -> the exact words matching's TAXONOMY understands.
TOPIC_ALIASES = {
    # sports
    "футбол": "football", "соккер": "football", "матч": "football", "баскетбол": "basketball",
    "баскет": "basketball", "волейбол": "volleyball", "теннис": "tennis", "падел": "padel",
    # «падл» is how people actually type it, and the filtration LLM answers with "paddle" — a
    # different sport entirely (an oar, not a racquet). Unresolved, the ask reached the ranker as a
    # word nobody has, and generic neighbours ("sport", "game") decided the slate instead.
    "падл": "padel", "паддл": "padel", "paddle": "padel", "padle": "padel", "падел-теннис": "padel",
    # compounds ending in -спорт, listed explicitly now that the prefix rule no longer guesses them
    "киберспорт": "gaming", "велоспорт": "cycling", "автоспорт": "cycling", "мотоспорт": "cycling",
    "пинг-понг": "pingpong", "пингпонг": "pingpong", "настольный теннис": "pingpong",
    "гандбол": "handball", "кроссфит": "crossfit", "футзал": "football", "мини-футбол": "football",
    "бадминтон": "badminton", "сквош": "squash", "бег": "running", "пробежка": "running",
    "побегать": "running", "велосипед": "cycling", "велик": "cycling", "вело": "cycling",
    "плавание": "swimming", "бассейн": "swimming", "поплавать": "swimming", "зал": "gym",
    "качалка": "gym", "спортзал": "gym", "фитнес": "gym", "тренировка": "gym", "спорт": "gym",
    "бокс": "boxing", "мма": "mma", "скалолазание": "climbing", "скалодром": "climbing",
    "йога": "yoga", "пилатес": "pilates", "марафон": "marathon", "триатлон": "triathlon",
    # games
    "дота": "dota", "валорант": "valorant", "контра": "cs", "кс": "cs", "лол": "league",
    "шахматы": "chess", "покер": "poker", "настолки": "boardgames", "настолка": "boardgames",
    "игры": "gaming", "поиграть": "gaming", "гейминг": "gaming", "катка": "gaming", "фифа": "fifa",
    "тиммейт": "gaming", "напарник": "gaming",
    "майнкрафт": "minecraft", "майн": "minecraft", "роблокс": "roblox", "пубг": "pubg",
    "варзон": "warzone", "вов": "wow", "кс2": "cs", "калда": "cod", "гта": "gta",
    # social
    "кофе": "coffee", "кофейня": "coffee", "чай": "tea", "бранч": "brunch", "ужин": "dinner",
    "обед": "lunch", "поесть": "food", "ресторан": "restaurant", "готовка": "cooking",
    "готовить": "cooking", "бар": "bar", "выпить": "drinks", "пиво": "beer", "вино": "wine",
    "вечеринка": "party", "туса": "party", "тусить": "hangout", "клуб": "club",
    "прогулка": "walk", "погулять": "walk", "гулять": "walk", "поболтать": "talk",
    "поговорить": "talk", "болтать": "talk", "чилл": "chill",
    # culture
    "кино": "cinema", "фильм": "cinema", "фильмы": "cinema", "сериал": "series", "сериалы": "series",
    "искусство": "art", "музей": "museum", "галерея": "gallery", "фотография": "photography",
    "фото": "photography", "выставка": "exhibition", "театр": "theatre", "опера": "opera",
    "балет": "ballet", "стендап": "standup", "книги": "books", "книга": "books", "чтение": "reading",
    "литература": "literature", "архитектура": "architecture", "урбанистика": "urbanism", "город": "city",
    # tech
    "стартап": "startup", "стартапы": "startups", "продукт": "product", "фаундер": "founder",
    "основатель": "founder", "бизнес": "business", "ии": "ai", "нейронки": "ai", "нейросети": "ai",
    "мл": "ai", "программирование": "coding", "кодинг": "coding", "разработка": "software",
    "данные": "data", "крипта": "crypto", "блокчейн": "blockchain", "нетворкинг": "networking",
    "инвестиции": "investing", "инвестирование": "investing", "инвестировать": "investing",
    "облигации": "investing", "облигация": "investing", "акции": "investing", "акция": "investing",
    "биржа": "investing", "бирже": "investing", "фондовый": "investing", "трейдинг": "investing",
    "финансы": "investing", "финансах": "investing", "портфель": "investing", "дивиденды": "investing",
    "bonds": "investing", "bond": "investing", "stocks": "investing", "equities": "investing",
    "finance": "investing", "trading": "investing", "portfolio": "investing",
    "инвестор": "investor", "карьера": "career", "дизайн": "design",
    # music
    "концерт": "concert", "фестиваль": "festival", "музыка": "music", "винил": "vinyl",
    "гитара": "guitar", "пианино": "piano", "барабаны": "drums", "диджей": "dj", "джем": "jam",
    "караоке": "karaoke", "группа": "band", "рейв": "rave", "техно": "techno",
    # outdoors
    "поход": "hiking", "походы": "hiking", "хайкинг": "hiking", "треккинг": "trekking",
    "природа": "nature", "кемпинг": "camping", "горы": "mountains", "серфинг": "surfing",
    "каякинг": "kayaking", "лыжи": "skiing", "сноуборд": "snowboard", "путешествия": "travel",
    "путешествие": "travel", "рыбалка": "fishing",
    # learning
    "испанский": "spanish", "английский": "english", "французский": "french", "немецкий": "german",
    "итальянский": "italian", "португальский": "portuguese", "русский": "russian",
    "язык": "language", "языки": "languages", "обмен": "exchange", "практика": "practice",
    "курс": "course", "воркшоп": "workshop", "учеба": "study",
}
_ALIAS_KEYS = sorted(TOPIC_ALIASES, key=len, reverse=True)

# MIRRORS matching-service's TAXONOMY (word -> broad category). Buddy needs it to keep only words the ranker
# can resolve. KEEP IN SYNC with services/matching/app.py::TAXONOMY (a shared/taxonomy.py would be better —
# see the note in the deploy summary).
_TAX = {
    "sports": "football soccer basketball volleyball handball tennis padel badminton squash pingpong running "
              "jogging cycling biking swimming triathlon marathon gym fitness workout crossfit boxing mma "
              "climbing bouldering yoga pilates stretching",
    "social": "coffee tea brunch cafe dinner lunch food restaurant cooking bar drinks pub beer wine party club "
              "clubbing walk walking stroll hang hangout chill talk chat",
    "games": "dota valorant cs league apex fortnite fifa overwatch gaming chess boardgames poker cards dnd tabletop",
    "culture": "cinema movies film series art museum gallery photography exhibition painting theatre opera ballet "
               "standup books reading literature bookclub architecture urbanism city",
    "tech": "startup startups product founder entrepreneur business ai ml programming coding software data crypto "
            "blockchain networking investing investor career mentorship design ux ui",
    "music": "concert gig festival music vinyl guitar piano drums dj jam producing singing karaoke band rave techno edm",
    "outdoors": "hiking trekking nature camping mountains trail outdoor outdoors surfing kayaking skiing snowboard "
                "travel roadtrip sightseeing fishing",
    "learning": "spanish english french german italian portuguese russian language languages exchange practice "
                "course workshop study",
}
BROAD_OF = {w: broad for broad, words in _TAX.items() for w in words.split()}
TYPE_OF_BROAD = {"sports": "sport", "games": "gaming", "tech": "networking", "learning": "language",
                 "music": "social", "culture": "social", "social": "social", "outdoors": "sport"}

# filtration's category -> the nearest word the ranker knows. Used ONLY when nothing else resolved, so a
# categorised request still reaches candidates. Categories with no taxonomy home (pets, fashion,
# toys_collectibles) map to nothing ON PURPOSE — we would rather say "nobody yet" than match the wrong people.
CATEGORY_BRIDGE = {
    "sports": ["gym"], "gaming": ["gaming"], "esports": ["gaming"], "tabletop": ["boardgames"],
    "music": ["music"], "film_tv": ["cinema"], "art_culture": ["art"], "books": ["books"],
    "food_drink": ["dinner"], "coffee": ["coffee"], "nightlife": ["bar"], "outdoors": ["hiking"],
    "travel": ["travel"], "tech": ["ai"], "startups": ["startups"], "career": ["networking"],
    "languages": ["language"], "wellness": ["yoga"], "photography": ["photography"],
    "social": ["talk"], "dating": [],
}
# NB: "game"/"games"/"teammate" deliberately do NOT map to `gaming` — filtration often returns them alongside
# a real topic ("football", "soccer", "sport", "game"), and mapping them would bolt a gaming topic onto a
# football request and surface gamers for it. A bare "games" request still lands via CATEGORY_BRIDGE.
_EN_SYN = {"soccer": "football", "movies": "cinema", "movie": "cinema", "film": "cinema", "ml": "ai",
           "boardgame": "boardgames", "videogames": "gaming",
           # the filtration LLM answers «падл» with "paddle" — an oar, not a racquet. Unresolved it
           # dropped the whole ask into the raw-passthrough branch below.
           "paddle": "padel", "padle": "padel", "padeltennis": "padel",
           "ping-pong": "pingpong", "table tennis": "pingpong", "futbol": "football"}

# Words that name a BUCKET, not an ask. They only ever reach `topics` through the raw-passthrough
# branch (nothing resolved), and there they are actively harmful: measured on «игры в падл», the
# generic "game" pulled a gamer with no padel to the top of the slate and made every card lead with
# «gaming» instead of «padel». Dropping them can empty `topics`, which is the honest outcome — the
# category bridge then labels the request instead of a word nobody meant.
_GENERIC_TOPIC = {"sport", "sports", "game", "games", "gaming", "activity", "activities", "hobby",
                  "hobbies", "racquet", "racket", "meetup", "meetups", "event", "events", "fun",
                  "outdoor", "outdoors", "indoor", "team", "exercise", "training",
                  "people", "meeting", "social", "friends", "company", "спорт", "игры", "игра",
                  "хобби", "встреча", "встречи", "люди", "компания", "развлечения",
                  # verbs describing HOW, not WHAT — filtration emits them alongside the real topic
                  "play", "playing", "talk", "talking", "discussing", "drinking", "eating",
                  "watching", "hanging", "hang", "hangout", "chill", "joining", "learning",
                  "practising", "practicing",
                  # answers to «вдвоём или компанией?» belong in `format`, not in what we search on —
                  # they leaked into topics as soon as the agent started asking about format
                  "small", "group", "groups", "big", "large", "duo", "pair", "solo", "alone",
                  "together", "вдвоём", "вдвоем", "компанией", "группой"}
_RU_END = ("ами", "ями", "ах", "ях", "ов", "ев", "ом", "ем", "ой", "ей", "ую", "ые", "ый", "ая", "ое",
           "у", "а", "я", "и", "ы", "е", "ю", "ь", "й", "о")
_CYR = re.compile(r"[а-яё]", re.I)


def detect_lang(text):
    """Which language we REPLY in. Machine-facing fields stay English regardless."""
    return "ru" if _CYR.search(str(text or "")) else "en"


def _stem(w):
    """RU inflection: 'доту' -> 'дот', 'футболом' -> 'футбол'."""
    for end in _RU_END:
        if w.endswith(end) and len(w) - len(end) >= 3:
            return w[: -len(end)]
    return w


_ALIAS_STEMS = {}
for _k, _v in TOPIC_ALIASES.items():
    _ALIAS_STEMS.setdefault(_stem(_k), _v)


def norm_topic(word):
    """One surface form -> one canonical word the ranker resolves ('' if it could not resolve it anyway)."""
    w = str(word or "").strip().lower()
    if not w:
        return ""
    if not _CYR.search(w):
        w = _EN_SYN.get(w, w)
        return w if w in BROAD_OF else ""
    if w in TOPIC_ALIASES:
        return TOPIC_ALIASES[w]
    s = _stem(w)
    if s in _ALIAS_STEMS:
        return _ALIAS_STEMS[s]
    # PREFIX, not "contained anywhere". Russian compounds put the modifier first, so an infix rule
    # made «спорт» swallow киберспорт / велоспорт / автоспорт / мотоспорт — every one of them
    # resolved to `gym`, and someone asking about esports was shown people who lift weights.
    for k in _ALIAS_KEYS:
        if len(k) >= 5 and w.startswith(k):
            return TOPIC_ALIASES[k]
    return ""


def norm_topics(topics):
    out = []
    for t in topics or []:
        for piece in re.split(r"[\s,/]+", str(t).lower()):
            n = norm_topic(piece)
            if n and n not in out:
                out.append(n)
    return out[:4]


LANG_ALIASES = {"русский": "ru", "russian": "ru", "английский": "en", "english": "en", "испанский": "es",
                "spanish": "es", "немецкий": "de", "german": "de", "французский": "fr", "french": "fr",
                "итальянский": "it", "italian": "it", "португальский": "pt", "portuguese": "pt"}


def norm_langs(langs):
    out = []
    for l in langs or []:
        k = str(l).strip().lower()
        k = LANG_ALIASES.get(k, k)[:2]
        if k and k not in out:
            out.append(k)
    return out


ROLE_HINTS = (   # matching scores role_same and penalises ROLE_CONFLICT (play vs watch) — worth getting right
    ("play",     ("play", "teammate", "squad", "sparring", "поиграть", "играть", "сыграть", "катк", "тиммейт")),
    ("watch",    ("watch", "посмотреть", "смотреть", "трансляц", "матч")),
    ("practise", ("practise", "practice", "learn", "exchange", "практик", "потренир", "выучить", "обмен")),
    ("discuss",  ("discuss", "talk", "chat", "conversation", "поговорить", "обсудить", "поболтать")),
    ("attend",   ("attend", "event", "concert", "festival", "сходить", "концерт", "фестивал", "выставк")),
)
ROLE_WORDS = {"play": "play", "watch": "watch", "discuss": "discuss", "practise": "practise",
              "practice": "practise", "attend": "attend", "meet": "meet"}
# A language becomes a HARD gate only if the user explicitly demands it. Merely speaking one must never gate
# the search — that bug once filtered out every valid candidate.
LANG_DEMAND = ("speaks", "speaking", "in english", "in spanish", "in russian", "говорящ", "по-русски",
               "по-английски", "по-испански", "кто говорит")


def infer_role(text):
    t = str(text or "").lower()
    for role, words in ROLE_HINTS:
        if any(w in t for w in words):
            return role
    return "meet"


def infer_type(topics):
    for t in topics or []:
        broad = BROAD_OF.get(t)
        if broad:
            return TYPE_OF_BROAD.get(broad, "social")
    return "social"


# Stop-words for the raw-topic fallback (when an interest is outside the taxonomy): drop verbs / fillers so
# "хочу обсудить apple" -> ["apple"], not ["хочу","обсудить","apple"].
_RAW_STOP = {"хочу", "хотел", "найти", "найди", "найдите", "поговорить", "обсудить", "обсуждать", "встретить",
             "познакомиться", "люблю", "нравится", "заниматься", "занимаюсь", "интересует", "someone", "people",
             "with", "about", "want", "like", "find", "meet", "discuss", "talk", "into", "some", "have", "who",
             "that", "this", "тему", "темы", "человек", "человека", "который", "которые",
             # filtration writes its `interest` as an English gerund phrase ("discussing bonds while
             # swimming"), so the verb forms leak in as topics unless they are stopped here too.
             "discussing", "talking", "chatting", "meeting", "finding", "looking", "sharing", "wanting",
             "play", "playing", "game", "games", "talk", "hang", "hangout", "join", "joining",
             "while", "together", "someone", "somebody", "tomorrow", "tonight", "today", "evening",
             "завтра", "сегодня", "вечером", "утром", "вместе", "бокалом",
             "утро", "вечер", "ночью", "днём", "днем", "выходные", "выходных", "неделе"}


def _is_verbish(w):
    """A Russian infinitive, by ending. The raw-word union exists to carry unresolvable SUBJECTS
    («облигации», «labubu») — a verb is never the subject, and hand-listing them lost: «выпить»
    rode into the topics of a coffee search and was shown to the user as a tag. Feminine nouns in
    -сть/-знь/-щь (новость, жизнь, помощь) are kept, which is what those endings are for."""
    return (w.endswith("ться") or w.endswith("чься") or
            (w.endswith("ть") and not w.endswith(("сть", "знь", "щь"))))


# ======================= SIGNALS =======================
def _as_list(v):
    if isinstance(v, list):
        return [str(x).strip().lower() for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [v.strip().lower()]
    return []


def _merge_signals(base_sig, delta):
    out = {k: v for k, v in (base_sig or {}).items()}
    for k, v in (delta or {}).items():
        if k not in SIGNAL_KEYS or v in (None, "", [], {}):
            continue
        if k in LIST_KEYS:
            cur = list(out.get(k) or [])
            for x in _as_list(v):
                if x not in cur:
                    cur.append(x)
            out[k] = cur[:8]
        else:
            out[k] = v
    if out.get("languages"):
        out["languages"] = norm_langs(out["languages"])
    return out


def _baseline_signals(profile):
    """Seed signals from what the buddy already KNOWS about the user (their profile / agent memory)."""
    p = profile or {}
    sig = {}
    # The client sends the user's name but it was never copied into the signals, so BUDDY_PROMPT's
    # "Known so far" block reached the model without it and Kleal politely asked «как вас зовут?» —
    # of someone whose profile it is holding.
    nm = str(p.get("name") or "").strip()
    if nm:
        sig["name"] = nm
    ints = p.get("interests")
    topics = []
    if isinstance(ints, dict):
        topics = _as_list(ints.get("explicit"))
    elif isinstance(ints, list):
        for it in ints:
            if isinstance(it, dict) and it.get("name"):
                topics.append(str(it["name"]).lower())
            elif isinstance(it, str):
                topics.append(it.lower())
    if topics:
        sig["topics"] = topics[:8]
    langs = p.get("languages")
    ll = []
    if isinstance(langs, dict):
        ll = _as_list(langs.get("comfortable")) or _as_list(langs.get("fluent"))
    elif isinstance(langs, list):
        ll = _as_list(langs)
    ll = norm_langs(ll)
    if ll:
        sig["languages"] = ll
    vibe = p.get("vibe")
    if isinstance(vibe, dict):
        pv = _as_list(vibe.get("primary"))
        if pv:
            sig["vibe"] = pv[0]
    elif isinstance(vibe, str) and vibe.strip():
        sig["vibe"] = vibe.strip().lower()
    city = p.get("city") or ((p.get("geo") or {}).get("comfortableAreas") or [None])[0]
    if city:
        sig["area"] = str(city)
    dom = (p.get("domains") or {}).get("dating") or {}
    if dom.get("enabled") is True or "dating" in _as_list((p.get("goals") or {}).get("primary")):
        sig["datingOk"] = True
    return sig


# ======================= SESSIONS (only for the {user_id, message} mode) =======================
# The profile UI keeps the thread client-side and posts it back each turn (stateless). Thin clients post just
# {user_id, message}; for those buddy keeps the thread + signals here, so it actually remembers the person.
_LOCK = threading.Lock()


def _load_store():
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


SESSIONS = _load_store()


def _save_store():
    try:
        with open(STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(SESSIONS, f, ensure_ascii=False)
    except Exception:
        pass


def _session(uid):
    with _LOCK:
        return SESSIONS.setdefault(str(uid), {"thread": [], "signals": {}, "profile": {}, "intent": None})


# ======================= AGENT-TO-AGENT CLIENTS =======================
def _post(base_url, path, payload, timeout=30):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(base_url + path, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _categorize(text):
    """Filtration agent: magnetise the request to an existing category + canonical topics.
    Timeout is generous on purpose: it runs its own 70B call, and under load 45s was not enough — the call
    failed, the category came back empty and the search silently found nobody. On failure we return None and
    canonicalise from the raw text instead, so a slow filtration degrades the card, never the match."""
    try:
        return _post(FILTER_URL, "/api/filter/categorize", {"text": text}, timeout=90)
    except Exception:
        return None


# Topics are canonicalised to English for the ranker, so a Russian user's intent came back titled
# "Coffee — встреча". Titles are user-facing: put the topic back into their language.
_TOPIC_RU = {
    'coffee':'Кофе','tea':'Чай','brunch':'Бранч','dinner':'Ужин','food':'Еда','restaurant':'Ресторан',
    'cooking':'Готовка','beer':'Пиво','bar':'Бар','wine':'Вино','party':'Вечеринка','club':'Клуб',
    'walk':'Прогулка','football':'Футбол','basketball':'Баскетбол','volleyball':'Волейбол',
    'tennis':'Теннис','padel':'Падель','running':'Бег','cycling':'Велосипед','swimming':'Плавание',
    'gym':'Зал','fitness':'Фитнес','crossfit':'Кроссфит','boxing':'Бокс','climbing':'Скалолазание',
    'yoga':'Йога','pilates':'Пилатес','dota':'Дота','league':'Лига','valorant':'Валорант','cs':'CS',
    'fifa':'ФИФА','gaming':'Гейминг','chess':'Шахматы','boardgames':'Настолки','poker':'Покер',
    'cinema':'Кино','series':'Сериалы','art':'Искусство','museum':'Музей','gallery':'Галерея',
    'exhibition':'Выставка','photography':'Фотография','theatre':'Театр','opera':'Опера',
    'books':'Книги','reading':'Чтение','literature':'Литература','bookclub':'Книжный клуб',
    'architecture':'Архитектура','urbanism':'Урбанистика','startup':'Стартап','startups':'Стартапы',
    'product':'Продакт','founder':'Фаундер','business':'Бизнес','ai':'ИИ','ml':'ML','coding':'Кодинг',
    'software':'Разработка','crypto':'Крипта','networking':'Нетворкинг','investing':'Инвестиции',
    'career':'Карьера','design':'Дизайн','concert':'Концерт','festival':'Фестиваль','music':'Музыка',
    'guitar':'Гитара','piano':'Пианино','dj':'Диджеинг','singing':'Вокал','karaoke':'Караоке',
    'rave':'Рейв','techno':'Техно','hiking':'Хайкинг','mountains':'Горы','nature':'Природа',
    'camping':'Кемпинг','surfing':'Сёрфинг','kayaking':'Каякинг','skiing':'Лыжи','snowboard':'Сноуборд',
    'travel':'Путешествия','fishing':'Рыбалка','spanish':'Испанский','english':'Английский',
    'french':'Французский','german':'Немецкий','italian':'Итальянский','russian':'Русский',
    'languages':'Языки','exchange':'Языковой обмен','practice':'Практика языка','course':'Курс',
    'workshop':'Воркшоп','study':'Учёба','coworking':'Коворкинг','remotework':'Удалёнка',
    'formula1':'Формула 1','barca':'Барса','motorsport':'Автоспорт',
}

def _title_for(topics, tags, typ, lang):
    """Card title. Prefers whichever word we can actually SAY in the user's language.

    It used to title off `tags or topics`, and filtration's tags are synonym bags in arbitrary order —
    'хочу поиграть в футбол' came back tagged ['soccer','football',...], so the Russian card read
    "Soccer — встреча". _TOPIC_RU knows 'football' but not 'soccer'. Scan every candidate for one that
    translates before falling back, so an untranslated synonym can never win over a translatable topic.
    """
    if typ == "dating":
        return "Свидание" if lang == "ru" else "Date"
    cands = [str(t) for t in list(topics or []) + list(tags or []) if str(t).strip()]
    if not cands:
        return "Встреча" if lang == "ru" else "Meet someone"
    if lang == "ru":
        for c in cands:
            word = _TOPIC_RU.get(c.strip().lower())
            if word:
                return word + " — встреча"
        for c in cands:                        # off-taxonomy but the user's own Russian word -> keep it
            if any('а' <= ch <= 'я' for ch in c.lower()):
                return c + " — встреча"
        return cands[0].capitalize() + " — встреча"
    return cands[0].capitalize() + " meetup"


# Online-native activities and explicit "let's do it online" cues. Hard-coding mode="offline" sent
# ranked Dota to "public places nearby" and made the ranker demand geo feasibility for a game that
# is played over the internet (spec §18.2: games are an online domain, location weight 0).
# Online-by-nature = the taxonomy's ESPORTS branch (real-time internet games), kept in sync with
# matching/app.py TAXONOMY['games']['esports'], PLUS crypto. This is the whole branch, not an
# arbitrary short list — add a game to the esports vocabulary and it becomes online automatically,
# so "minecraft" no longer silently defaults to a coffee-shop meetup. Tabletop games (chess, poker,
# boardgames) are deliberately NOT here: you play those across a table, in person.
_ESPORTS = {"dota", "valorant", "cs", "league", "apex", "fortnite", "fifa", "overwatch", "gaming",
            "minecraft", "roblox", "rocketleague", "pubg", "warzone", "wow", "hearthstone", "tft",
            "rainbow6", "callofduty", "cod", "gta", "starcraft", "hots", "pubgm"}
_ONLINE_TOPICS = _ESPORTS | {"crypto"}
_ONLINE_WORDS = ("online", "онлайн", "по сети", "удалённо", "удаленно", "remote", "voice", "video",
                 "call", "созвон", "стрим", "stream", "discord", "дискорд", "zoom", "зум", "ranked",
                 "ранкед", "каток", "катку", "катки")
_OFFLINE_WORDS = ("offline", "офлайн", "оффлайн", "вживую", "встретиться", "meet up", "in person",
                  "за столом", "в баре", "в кафе")

def _infer_mode(topics, sig, last_user, category="", subcategory=""):
    blob = (str(sig.get("interest") or "") + " " + str(last_user or "")).lower()
    if any(w in blob for w in _OFFLINE_WORDS):          # the user said "вживую"/"в кафе" — offline wins
        return "offline"
    if any(w in blob for w in _ONLINE_WORDS):           # the user said "онлайн"/"discord"/"каток"
        return "online"
    if str(category).lower() == "esports" or str(subcategory).lower() == "esports":
        return "online"                                 # taxonomy says this is an internet game
    if any(str(t).lower() in _ONLINE_TOPICS for t in (topics or [])):
        return "online"
    return "offline"                                    # everything else meets in person

def build_intent(sig, cat, last_user, lang):
    """Filtration result + signals -> the intent matching ranks on.
    Machine fields are canonical English; the card fields follow the user's language."""
    cat = cat or {}
    # engine topics: prefer words the ranker resolves (RU -> EN, taxonomy-validated).
    # `sig["topics"]` is the searcher's OWN standing profile interests. It used to sit in this chain,
    # so a request the taxonomy has no word for silently became "find people who share my interests":
    # «хочу обсудить собачников» resolved to nothing, fell through to the profile, and searched
    # startups/ai — returning four confident cards about a query the user never made. Standing
    # interests are context, never the ask. Only the REQUEST may set the topics.
    topics = (norm_topics(cat.get("topics")) or norm_topics(sig.get("interest"))
              or norm_topics(re.findall(r"[\w']+", str(last_user).lower())))
    # Weak/strong, not a blanket drop. A bucket word that CANONICALISED (so it is a real taxonomy
    # entry: «спорт» -> gym, «поиграть» -> gaming) is a legitimate whole ask when it is all the
    # person gave — dropping it outright returns nothing. It only loses when something specific
    # exists beside it, which is the «прогулка + outdoors» case.
    _strong = [t for t in topics if t not in _GENERIC_TOPIC]
    topics = _strong or topics
    from_request = bool(topics)
    # An `or` chain used to end here, and that is how the SUBJECT of a request got thrown away: the
    # moment the taxonomy resolved a single word, every other word of the request was discarded.
    # «Обсудить облигации, плавая в бассейне» resolved "плавание" -> ["swimming"] and searched for
    # swimmers, while "облигации" survived only as a display tag. Matching does literal-word overlap
    # too (_wshare), so an unresolvable word is still worth carrying — union, not fallback.
    if topics:
        raw = [w[:24] for w in re.findall(r"[a-zа-яё0-9]{4,}",
                                          str(sig.get("interest") or last_user or "").lower())
               # both lists, or the third path leaks what the other two now stop: «один или с
               # компанией?» put "company" into the topics of a cinema search.
               if w not in _RAW_STOP and w not in _GENERIC_TOPIC and not _is_verbish(w)
               and norm_topic(w) not in topics]
        # A "discuss" request is ABOUT something; the activity is the setting. Put the subject first
        # so the ranker weighs what the person actually wants to talk about.
        wants_talk = any(w in str(last_user or "").lower()
                         for w in ("обсуд", "поговор", "разговор", "потрещ", "discuss", "talk about", "chat about"))
        extra = [w for w in raw if w not in topics][:2]
        topics = (extra + topics) if (wants_talk and extra) else (topics + extra)
        topics = topics[:4]
    # Interests the taxonomy doesn't cover ("apple", "рыбалка", "labubu") canonicalise to nothing. Keep the
    # raw significant words — matching's _wshare does literal-word overlap, so two people who both listed
    # "apple" still match. This runs BEFORE the category bridge so a specific interest isn't replaced by a
    # generic taxonomy word (apple -> ai). filtration's topics are already cleaned; else use the raw text.
    if not topics:
        topics = [str(t).lower()[:24] for t in (cat.get("topics") or [])
                  if str(t).strip() and str(t).strip().lower() not in _GENERIC_TOPIC][:4]
        from_request = from_request or bool(topics)      # filtration read the request — still the ask
    if not topics:
        topics = [w[:24] for w in re.findall(r"[a-zа-яё0-9]{4,}", str(sig.get("interest") or last_user).lower())
                  if w not in _RAW_STOP][:3]
        from_request = from_request or bool(topics)      # raw words of the request itself
    if not topics:                                    # last resort: nearest taxonomy word for the category
        topics = CATEGORY_BRIDGE.get(str(cat.get("category") or ""), [])
    # card tags: what the user actually asked for (may be outside the taxonomy — "labubu" stays "labubu")
    tags = [str(t).lower()[:24] for t in (cat.get("topics") or [])
            if str(t).strip() and str(t).strip().lower() not in _GENERIC_TOPIC][:4] or topics
    # Show the word the search actually ran on. Filtration's surface form can be a near-miss
    # ("paddle" for padel), and a card that names a different sport than the one being searched is
    # worse than a card that repeats the canonical word.
    for _canon in topics:
        if _canon and _canon not in tags:
            tags = [_canon] + [t for t in tags if norm_topic(t) != _canon][:3]
            break
    typ = str(cat.get("type") or sig.get("type") or "").lower()
    if typ not in ("dinner", "sport", "gaming", "networking", "dating", "language", "social", "other"):
        typ = "dating" if sig.get("datingOk") and any(
            w in str(last_user).lower() for w in ("dating", "date", "свидан", "знаком")) else infer_type(topics)
    role = ROLE_WORDS.get(str(cat.get("role") or "").lower()) or \
        ROLE_WORDS.get(str(sig.get("role") or "").lower()) or infer_role(sig.get("interest") or last_user)
    dating = typ == "dating"
    demand = str(sig.get("interest") or "") + " " + str(last_user or "")
    req_langs = norm_langs(sig.get("languages")) if any(w in demand.lower() for w in LANG_DEMAND) else []
    mode = _infer_mode(topics, sig, last_user, cat.get("category"), cat.get("subcategory"))
    place = str(sig.get("area") or (("Онлайн" if lang == "ru" else "Online") if mode == "online" else
                                    ("Публичные места рядом" if lang == "ru" else "Public places nearby")))[:60]
    title = _title_for(topics, tags, typ, lang)
    return {
        # ---- machine-facing: matching-service reads exactly these ----
        "title": title, "type": typ, "topics": topics or ["social"], "role": role, "mode": mode,
        "category": cat.get("category"), "subcategory": cat.get("subcategory") or "",
        "time": sig.get("time") or ("Гибко" if lang == "ru" else "Flexible"),
        "place": place, "format": ("1:1 или небольшая группа" if lang == "ru" else "1:1 or small group"),
        "radiusKm": 15, "verifiedOnly": bool(dating), "minAge": (18 if dating else None), "maxAge": None,
        "requiredLanguages": req_langs, "exactMatchRequired": False,
        "adjacentAllowed": True, "broadAllowed": True,
        # ---- card-facing: what the intent card in the UI shows ----
        "activity": title, "tags": tags or ["social"], "area": place,
        "safety": ("Только публичные места" if lang == "ru" else "Public places only"),
        "visibility": ("Только через Kleal" if lang == "ru" else "Via Kleal only"),
        "fallback": ("Онлайн, если не сложится" if lang == "ru" else "Online if it falls through"),
        # Only topics that came from the REQUEST make an intent rankable. A category-bridge guess is a
        # last-resort label, not evidence that anyone matching it wants THIS.
        # Deliberately NOT "must contain a non-bucket word". That rule contradicted the weak/strong
        # one above — which keeps a bucket word precisely when it is all the person gave — and it
        # killed «хочу заняться спортом», a real request. The first-turn-ready problem it was meant
        # to solve is handled where it belongs: the agent now asks what the person actually wants
        # before deciding anything is ready.
        "rankable": bool(topics) and from_request,
        "isNew": bool(cat.get("isNew")),
        "lang": lang,
    }


OVERRIDES = {                                   # the ids matching offers in its `fallback` block
    "inexact":  {"exactMatchRequired": False, "broadAllowed": True},
    "adjacent": {"adjacentAllowed": True, "broadAllowed": True},
    "radius":   {"radiusKm": 45},
    "online":   {"mode": "online"},
}


def apply_override(intent, override):
    """Broaden the search: accepts a dict of intent fields and/or a list of suggestion ids."""
    it = dict(intent or {})
    if isinstance(override, list):
        for oid in override:
            it.update(OVERRIDES.get(str(oid), {}))
    elif isinstance(override, dict):
        for k, v in override.items():
            if k in OVERRIDES:
                if v:
                    it.update(OVERRIDES[k])
            elif k in ("radiusKm", "verifiedOnly", "minAge", "maxAge", "requiredLanguages", "mode",
                       "exactMatchRequired", "adjacentAllowed", "broadAllowed"):
                it[k] = v
    return it


# matching's reasons are engine-speak ("same role (play)", "very close (0.4 km)"). The card shows a person,
# not a scorecard — so translate the useful ones, drop the negatives.
_REASON_RU = [("you both want the same thing", "хочет того же"), ("same kind of activity", "похожее занятие"),
              ("related interest", "близкие интересы"), ("adjacent interest", "близкие интересы"),
              ("open to meet", "открыт к встрече"), ("recently active", "недавно заходил"),
              ("shares a community", "общая тусовка"), ("suits your time", "свободен в это время"),
              ("common language", "общий язык"), ("similar vibe", "похожий вайб"),
              ("open to dating nearby", "открыт к знакомству")]
_ROLE_RU = {"play": "тоже хочет играть", "watch": "тоже хочет посмотреть", "discuss": "тоже хочет обсудить",
            "practise": "тоже хочет практиковать", "attend": "тоже хочет сходить"}
_DROP = ("different role", "may not be free then", "passed on them before", "fit is a bit weak")


def humanize(reasons, lang):
    """-> a short '·'-joined why-this-person line (max 2 fragments)."""
    out = []
    for r in reasons or []:
        rl = str(r).lower()
        if any(d in rl for d in _DROP):
            continue
        if lang != "ru":
            out.append(str(r))
            continue
        m = re.match(r"shares (.+)", rl)
        if m:
            out.append("тоже: " + m.group(1))
            continue
        m = re.match(r"same role \((\w+)\)", rl)
        if m:
            out.append(_ROLE_RU.get(m.group(1), "хочет того же"))
            continue
        m = re.match(r"very close \(([\d.]+) km\)", rl)
        if m:
            out.append("рядом · %s км" % m.group(1))
            continue
        m = re.match(r"([\d.]+) km away", rl)
        if m:
            out.append("%s км от тебя" % m.group(1))
            continue
        out.append(next((ru for en, ru in _REASON_RU if en in rl), str(r)))
    seen, uniq = set(), []
    for x in out:
        if x.lower() not in seen:
            seen.add(x.lower())
            uniq.append(x)
    return " · ".join(uniq[:2])


def _shape(c, lang):
    """One matching candidate -> the card the UI draws. `reasons` stays verbatim for the legacy UI.
    Matching Core v2 fields (band/gap/localised reasons) pass through so the UI can show qualitative
    bands instead of raw percentages (spec §9.7)."""
    core_rs = c.get("reasons_ru") if lang == "ru" else c.get("reasons_en")
    return {"user_id": c.get("name"), "name": c.get("name"), "score": c.get("score"), "km": c.get("km"),
            "tier": c.get("tier"), "kind": c.get("kind"), "vibe": c.get("vibe"), "open": c.get("open"),
            "verified": c.get("verified"), "interests": c.get("interests") or [], "role": c.get("role"),
            "reasons": c.get("reasons") or [],
            "reason": (", ".join(core_rs[:2]) if core_rs else humanize(c.get("reasons"), lang)),
            "band": c.get("band"), "band_ru": c.get("band_ru"), "band_en": c.get("band_en"),
            "gap_ru": c.get("gap_ru"), "gap_en": c.get("gap_en"),
            "reasons_ru": c.get("reasons_ru"), "reasons_en": c.get("reasons_en"),
            "coverage": c.get("coverage"), "can_outreach": c.get("can_outreach"),
            "readiness": c.get("readiness"), "readiness_ru": c.get("readiness_ru"),
            "readiness_en": c.get("readiness_en"),
            "agree": c.get("agree"), "note": c.get("note"), "reply": c.get("reply")}


def run_match(intent, sig, uid, lang, negotiate=False, owner=None):
    """Hand the intent to the matching agent; optionally let each candidate's agent negotiate.
    Returns (legacy_match_block, cards). Never fabricates people."""
    prof = {"languages": {"comfortable": norm_langs(sig.get("languages"))}, "vibe": sig.get("vibe"),
            "city": sig.get("area"), "name": owner or ""}
    try:
        res = _post(MATCH_URL, "/api/agent/match",
                    {"intent": intent, "profile": prof, "ctx": {"uid": uid or "me", "self": owner or ""}},
                    timeout=45)
    except Exception as e:
        return {"intent": intent, "top": None, "candidates": [], "error": str(e)[:160]}, []
    cands = res.get("candidates") or []
    if cands and negotiate:
        try:                                     # each candidate's agent accepts/declines + writes an opener
            cands = (_post(MATCH_URL, "/api/agent/negotiate", {"intent": intent, "candidates": cands[:5]},
                           timeout=150).get("candidates") or cands)
            for c in cands:
                # matching computes `note` at scoring time and negotiation only overwrites `agree`, so a
                # declined candidate can come back still saying "Agent agreed". Restate it from the verdict.
                if "agree" in c and c.get("reason"):
                    c["note"] = ("Agent agreed — " if c.get("agree") else "Agent passed — ") + str(c["reason"])
        except Exception:
            pass
    block = {"intent": intent, "top": (cands[0] if cands else None), "candidates": cands[:3]}
    if not cands:
        block["fallback"] = res.get("fallback")
    return block, [_shape(c, lang) for c in cands[:4]]


# ======================= CONVERSATION =======================
_FALLBACK_REPLY = {
    "ru": ("Сейчас поищу кого-нибудь.", "Расскажи чуть больше — чем занимаешься и с кем хотел бы встретиться?"),
    "en": ("Let me find someone for you.", "Tell me a bit more about what you're into and who you'd like to meet."),
}
# Reply framing MUST match the match strength (spec §9.7: show the honest qualitative level, never
# oversell). Only an especially_close/strong_option candidate is pitched as a confident match; a
# broader/needs-clarification result is offered as exactly that, so buddy never claims "you'll click
# with X" about someone the ranker flagged as weak or not-yet-reachable.
_CLICK = {"ru": "Думаю, вы сойдётесь с %s — %s.", "en": "I think you'd click with %s — %s."}
_BROADER = {"ru": "Идеального совпадения нет, но есть вариант пошире — %s (%s). Посмотришь?",
            "en": "No perfect match, but here's a broader option — %s (%s). Want a look?"}
_NEEDCLAR = {"ru": "Кое-кто есть, например %s, но по деталям стоит уточнить — расскажешь чуть больше (время, район)?",
             "en": "There are a few, like %s, but the details need firming up — tell me a bit more (time, area)?"}
# search asked for, but no concrete activity given ("найди мне кого-нибудь") -> ask, don't dump people
_ASK_ACTIVITY = {"ru": "С радостью найду — а чем хочешь заняться? Кофе, спорт, игра, прогулка?",
                 "en": "Happy to find someone — what would you like to do? Coffee, sport, a game, a walk?"}
_NO_ONE = {"ru": "Пока никто не подходит — расширим поиск или попробуем онлайн?",
           "en": "No one perfect right now — want to go broader or try online?"}
_FILED = {"ru": "Отнёс это к «%s», но пока никого нет — расширим поиск или попробуем онлайн?",
          "en": "I filed that under “%s” but found no one perfect right now — go broader or try online?"}
_NEW = {"ru": "Отнёс это к «%s» — для Kleal это новая тема, вокруг неё пока никого. Поискать что-то смежное?",
        "en": "I filed that under “%s” — it's new for Kleal and nobody is around it yet. Try something adjacent?"}
_GLITCH = {"ru": "Что-то я подвис — повтори, пожалуйста?", "en": "I glitched for a second — say that again?"}


def _lenient_json(raw):
    """The 70B sometimes truncates the closing braces. Try the shared extractor, then repair."""
    obj = base._extract_json(raw)
    if isinstance(obj, dict):
        return obj
    s = str(raw or "")
    i = s.find("{")
    if i < 0:
        return None
    for extra in ("", "}", "}}", "\"}}", "\"}"):
        try:
            o = json.loads(s[i:] + extra)
            if isinstance(o, dict):
                return o
        except Exception:
            continue
    return None


def buddy_chat(messages, profile, signals, uid=None):
    sig = _merge_signals(_baseline_signals(profile), signals)
    convo = "\n".join((("User: " + str(m.get("content", ""))) if m.get("role") == "user"
                       else ("Buddy: " + str(m.get("content", "")))) for m in (messages or [])[-12:])
    # Without this marker the 70B invents a shared past on turn one ("Привет снова! Я уже отвечал…",
    # "I've already told you…") — it reads a bare one-line history as the tail of a longer chat.
    if sum(1 for m in (messages or []) if m.get("role") == "user") <= 1:
        convo = "[FIRST MESSAGE — you have never spoken with this person before]\n" + convo
    last_user = next((str(m.get("content", "")) for m in reversed(messages or []) if m.get("role") == "user"), "")
    lang = detect_lang(last_user)
    obj = None
    try:
        raw = llm_complete(MODEL_ID, [{"role": "system", "content": BUDDY_PROMPT.replace("__SIG__", json.dumps(sig))},
                                      {"role": "user", "content": convo}], 0.6)
        obj = _lenient_json(raw)
    except Exception:
        obj = None

    if isinstance(obj, dict) and obj.get("reply"):
        reply = str(obj.get("reply"))[:600]
        sig = _merge_signals(sig, obj.get("signals") or {})
        # The model's flag alone is not enough (it fires on plain chat and misses real asks). Require an
        # explicit ask in the user's words; the flag only tips a soft "with someone" cue over the line.
        want_match = wants_people(last_user, bool(obj.get("match")))
    else:
        # LLM down: only the strong, explicit ask triggers a search — never a bare activity mention.
        want_match = wants_people(last_user, False)
        reply = _FALLBACK_REPLY[lang][0 if want_match else 1]

    out = {"reply": reply, "signals": sig, "lang": lang, "match": None,
           "intent": None, "matches": [], "tool_call": None, "category": None}
    if not want_match:
        return out

    # 1) filtration categorises what they want; 2) buddy makes it rankable; 3) matching scores it.
    req_text = sig.get("interest") or last_user or " ".join(sig.get("topics") or [])
    cat = _categorize(req_text)
    intent = build_intent(sig, cat, last_user, lang)
    # "find me someone" with NO concrete activity -> ask, don't dump a generic social slate (spec §5:
    # a missing high-value slot is a clarification, not a silent default). Bare-social = the only topic
    # is the "social" placeholder AND the user named no recognizable activity word.
    # bare-social = the intent carries only the "social"/"other" placeholder, i.e. the user asked to
    # meet people but named no concrete activity. Ask what they want to do instead of ranking the
    # whole pool on a generic intent and name-dropping a weak "match" (spec §5 clarification).
    topics = [str(t).lower() for t in (intent.get("topics") or [])]
    bare_social = (not topics) or all(t in ("social", "other") for t in topics)
    if bare_social:
        out["reply"] = _ASK_ACTIVITY[lang]
        out["tool_call"] = "ask_activity"
        return out
    out["tool_call"] = "find_people"
    out["intent"] = intent
    out["category"] = cat

    if not intent.get("rankable"):
        # Categorised fine, but the ranker has no vocabulary for it yet (e.g. "labubu"). Say so — do not
        # silently return an empty list, and do not match the wrong people just to show a card.
        out["match"] = {"intent": intent, "top": None, "candidates": [], "fallback": None}
        out["reply"] = (reply + "\n\n" + _NEW[lang] % (intent.get("category") or "?")).strip()
        return out

    block, cards = run_match(intent, sig, uid, lang, owner=(profile or {}).get("name"))
    out["match"] = block
    out["matches"] = cards
    if block.get("top"):
        t = block["top"]
        # prefer the localized reason the matcher already produced (reasons_ru/en); humanize is the
        # legacy fallback and can leak untranslated interest words into an English reply
        why = (t.get("reason") or humanize(t.get("reasons"), lang)
               or ("хороший фит" if lang == "ru" else "a great fit"))
        band = t.get("band")
        if band in ("especially_close", "strong_option"):
            line = _CLICK[lang] % (t.get("name"), why)          # confident: real fit + reachable
        elif band == "broader_option":
            line = _BROADER[lang] % (t.get("name"), why)        # honest: broader, not perfect
        else:                                                   # needs_clarification / unknown
            line = _NEEDCLAR[lang] % t.get("name")              # honest: exists, but firm up details
        out["reply"] = (reply + "\n\n" + line).strip()
    else:
        catn = intent.get("category")
        out["reply"] = (reply + "\n\n" + (_FILED[lang] % catn if catn else _NO_ONE[lang])).strip()
    return out


ONBOARD_PROMPT = ('You are Kleal. In 2 short sentences, warmly summarise what you now know about this person '
                  '(interests, city, languages, how they like to meet). Speak TO them. Write in the SAME '
                  'language as their data — Russian if their interests/area are in Russian, else English. No lists, no JSON.')


def onboard(uid, profile):
    """Seed the buddy from the onboarding funnel: baseline signals + a summary the UI can show."""
    sig = _baseline_signals(profile)
    try:
        summary = str(llm_complete(MODEL_ID, [{"role": "system", "content": ONBOARD_PROMPT},
                                              {"role": "user",
                                               "content": json.dumps(profile or {}, ensure_ascii=False)[:2500]}],
                                   0.5) or "")[:400]
    except Exception:
        summary = ""
    if uid:
        s = _session(uid)
        s["profile"] = profile or {}
        s["signals"] = _merge_signals(s.get("signals") or {}, sig)
        s["summary"] = summary
        _save_store()
    return {"summary": summary, "signals": sig}


# ======================= PROFILE EDITOR ("Edit with Kleal") =======================
# The user opens a dedicated editor (the profile-service "Profile" button) and changes THEIR OWN profile
# in natural language ("добавь теннис", "город Мадрид", "убери футбол"). We return a structured PATCH; the
# frontend shows a confirmation and, on approval, applies it to its own DATA (the frontend owns the profile).
# We never mutate anything here — buddy has no copy of the card's DATA shape. Keep this endpoint separate
# from /chat so the editor prompt/behaviour can't leak into the conversational agent.
#
# Fields (must match the frontend's applyProfilePatch mapping):
#   set-fields  (op "set",   value = the FULL new human string): name, location, languages, formats,
#                availability, safety, vibe, summary
#   list-fields (op add/remove, value = ONE item):               interests, goals
EDIT_SET_FIELDS = ("name", "location", "languages", "formats", "availability", "safety", "vibe", "summary")
EDIT_LIST_FIELDS = ("interests", "goals")
EDIT_FIELDS = EDIT_SET_FIELDS + EDIT_LIST_FIELDS

PROFILE_EDIT_PROMPT = '''You are Kleal's profile editor. The user is changing THEIR OWN profile by talking to you. Read their message and the current profile, and return the change(s) as a PATCH.

Current profile (JSON): __PROFILE__

Fields you may change:
- name, location, languages, formats, availability, safety, vibe, summary  -> op "set", value = the COMPLETE new value as a short human string. For languages/formats/availability produce the full updated value (merge with what's already there — do NOT drop existing items unless the user asked to remove them).
- interests, goals  -> op "add" or "remove", value = the SINGLE item (one interest / one goal). Emit one patch entry per item.

Return ONE JSON object, nothing else:
{"reply":"<a short confirmation QUESTION in the user's language, e.g. 'Добавить теннис в интересы?'>",
 "patch":[{"op":"set|add|remove","field":"<one field above>","value":"<value>","label":"<short human description of THIS change, user's language>"}]}

Rules:
- If the user is NOT changing the profile (a question, chit-chat, unclear) -> "patch":[] and just reply naturally. Never invent a change.
- Multiple changes in one message -> multiple patch entries.
- reply and label follow the user's language; field names stay English; value for set-fields may be in the user's language (it is shown as-is on the card).'''


def _validate_patch(patch):
    out = []
    for p in patch or []:
        if not isinstance(p, dict):
            continue
        field = str(p.get("field") or "").strip().lower()
        op = str(p.get("op") or "").strip().lower()
        value = p.get("value")
        if field not in EDIT_FIELDS:
            continue
        if field in EDIT_LIST_FIELDS:
            op = "remove" if op in ("remove", "delete", "rm", "del", "drop") else "add"
        else:
            op = "set"
        if value in (None, "", [], {}):
            continue
        out.append({"op": op, "field": field, "value": str(value)[:200],
                    "label": str(p.get("label") or "").strip()[:120]})
    return out[:8]


def profile_edit(message, profile, lang):
    """Free-text profile change -> {reply, patch}. Applying is the frontend's job (it owns DATA)."""
    prof = json.dumps(profile or {}, ensure_ascii=False)[:2500]
    obj = None
    try:
        raw = llm_complete(MODEL_ID, [{"role": "system", "content": PROFILE_EDIT_PROMPT.replace("__PROFILE__", prof)},
                                      {"role": "user", "content": str(message or "")}], 0.2)
        obj = _lenient_json(raw)
    except Exception:
        obj = None
    if not isinstance(obj, dict):
        return {"reply": ("Не совсем понял — что поменять в профиле?" if lang == "ru"
                          else "I didn't catch that — what should I change?"), "patch": [], "lang": lang}
    patch = _validate_patch(obj.get("patch"))
    reply = str(obj.get("reply") or "").strip()[:400] or (
        ("Готово?" if lang == "ru" else "Want me to apply that?") if patch
        else ("Что поменять в профиле?" if lang == "ru" else "What should I change?"))
    return {"reply": reply, "patch": patch, "lang": lang}


# After a profile change is applied, the "Kleal's summary" paragraph must ADAPT — reflect the new profile in
# flowing prose — not get a word tacked on the end (the bug: changing personality appended "Интроверт" to the
# summary). We rewrite the whole paragraph from the current summary + up-to-date profile, keeping its language.
# Language follows the UI, NOT the profile data. Topics are canonicalised to English for matching
# ("coffee", "football"), so the old "match the language of the profile data" rule handed a Russian
# user an English paragraph about themselves on their own profile screen.
RESUMMARY_PROMPT = '''You are Kleal. Below is a user's current profile summary and their up-to-date profile data. Rewrite the SUMMARY as ONE warm, natural, flowing paragraph that reflects the CURRENT data. Integrate every change smoothly into the prose — NEVER just append or list words. Address the user directly. 2-4 sentences, concrete, no bullet points, output ONLY the paragraph.

If a PERSONALITY section is present, it is a separate text the user owns and keeps: do NOT copy its sentences and do NOT replace the summary with it. Carry its substance — how they come across and who they are easy with — into the paragraph, while keeping everything the CURRENT SUMMARY already states about their life, interests and plans. The result must read as ONE paragraph about the whole person.

LANGUAGE: write the paragraph in __LANGNAME__. This is not optional: __LANGDIR__ The interests may be stored as English keywords for the matching engine — translate them naturally, do not switch language because of them.'''


def resummary(profile, current, lang="ru", personality=""):
    """Rewrite the profile summary to integrate the latest changes (adapt, don't append).

    `personality` is the SEPARATE text the Kleal test owns. It is carried in as substance to weave,
    never as sentences to copy: the two texts have two owners and must not collapse into one."""
    lang = "en" if str(lang).lower() == "en" else "ru"
    pers = str(personality or "").strip()[:900]
    payload = ("CURRENT SUMMARY:\n" + str(current or "(none yet)") +
               (("\n\nPERSONALITY (the user's own separate text, from the Kleal test — weave, do not copy):\n"
                 + pers) if pers else "") +
               "\n\nUP-TO-DATE PROFILE DATA:\n" + json.dumps(profile or {}, ensure_ascii=False)[:2200])
    sys_prompt = (RESUMMARY_PROMPT
                  .replace("__LANGNAME__", _LANGNAME.get(lang, "Russian"))
                  .replace("__LANGDIR__", _LANGDIR.get(lang, _LANGDIR["ru"])))
    best = ""
    for attempt in range(2):
        try:
            s = str(llm_complete(MODEL_ID, [{"role": "system", "content": sys_prompt},
                                            {"role": "user", "content": payload}],
                                 0.5 if attempt == 0 else 0.2) or "").strip()[:900]
        except Exception:
            s = ""
        if not s:
            continue
        best = best or s
        if _lang_ok(s, lang):          # same guard the intent builder uses
            return {"summary": s}
    # Both attempts came back in the wrong language: an empty summary keeps the honest placeholder,
    # which beats showing the user an English paragraph about themselves.
    return {"summary": best if _lang_ok(best, lang) else ""}


# ======================= THE KLEAL PERSONALITY TEST (/persona) =======================
# Eight fixed questions on the client, then exactly ONE call here. The alternative — an LLM turn per
# question — gives eight chances to hang on a chain that allows ~195s, for questions that are fixed by
# design anyway. The paragraph is the PERSONALITY text and has its own owner: «Сводка Kleal» keeps its
# own field and afterwards re-weaves to carry this strand, rather than being replaced by it.
PERSONA_PROMPT = """You are Kleal. Below is a user's profile data, the life story they wrote in their own
words, and their answers to a short personality test. Write ONE warm, natural, flowing paragraph
describing how this person comes across and who they are easy with. Address the user directly ("you").
3-5 sentences. Be concrete and grounded ONLY in what is given — never invent facts, never flatter.
No bullet points, no headings, no preamble: output ONLY the paragraph.

LANGUAGE: write the paragraph in __LANGNAME__. This is not optional: __LANGDIR__ Interests may be
stored as English keywords for the matching engine — translate them naturally, and do not switch
language because of them."""


def persona(profile, story, answers, current, lang="ru"):
    """The personality test -> one paragraph, in the user's language, or "" if the model won't comply."""
    lang = "en" if str(lang).lower() == "en" else "ru"
    qa = "\n".join("Q: %s\nA: %s" % (str(a.get("q", ""))[:200], str(a.get("a", ""))[:400])
                    for a in (answers or []) if isinstance(a, dict) and str(a.get("a", "")).strip())
    payload = ("PROFILE DATA:\n" + json.dumps(profile or {}, ensure_ascii=False)[:1800] +
               "\n\nTHEIR LIFE STORY, IN THEIR OWN WORDS:\n" + (str(story or "").strip()[:2500] or "(not written)") +
               "\n\nPERSONALITY TEST ANSWERS:\n" + (qa or "(not taken)") +
               "\n\nCURRENT SUMMARY:\n" + (str(current or "").strip()[:900] or "(none yet)"))
    sys_prompt = (PERSONA_PROMPT
                  .replace("__LANGNAME__", _LANGNAME.get(lang, "Russian"))
                  .replace("__LANGDIR__", _LANGDIR.get(lang, _LANGDIR["ru"])))
    best = ""
    for attempt in range(2):
        try:
            out = str(llm_complete(MODEL_ID, [{"role": "system", "content": sys_prompt},
                                              {"role": "user", "content": payload}],
                                   0.5 if attempt == 0 else 0.2) or "").strip()[:900]
        except Exception:
            out = ""
        if not out:
            continue
        best = best or out
        if _lang_ok(out, lang):
            return {"personality": out, "summary": out}
    # Same honesty rule as resummary: an empty result keeps the old text on screen and lets the client
    # offer a retry, which beats handing the user an English paragraph about themselves.
    _b = best if _lang_ok(best, lang) else ""
    return {"personality": _b, "summary": _b}


# ======================= GHOSTWRITER (Kleal helps in a chat with a real person) =======================
# Kleal drafts the user's OWN next message to a match, in their voice, from their profile and the
# thread so far. It never sends: the product's promise on screen is "я пишу только после твоего
# одобрения", and the recipient is a real person. The draft lands in the composer for the user to edit
# or send. The other side's words are given as context and are never invented — only what they
# actually wrote is passed in.
GHOSTWRITE_PROMPT = '''You are writing AS the user (the account owner), not as their assistant, and not as
the other person. Produce the user's next message in a chat with someone they have just matched with.

Rules:
- FIRST PERSON, the user's voice. Never write "as your agent" or refer to Kleal.
- Ground it in the user's own profile (interests, languages, area) and in what the other person
  ACTUALLY wrote. Never invent facts about either side — no claimed plans, no places, no times that
  are not in the conversation.
- If the thread is empty, write a natural opener that gives the other person something easy to answer.
- If they asked something, answer it and ask one thing back.
- Short: 1-2 sentences. Warm, specific, not salesy. No emoji spam, no markdown.

Return ONE JSON object, nothing else: {"draft":"<the message>"}
The KEY is the literal ASCII word draft. Do NOT translate the key — only its value is translated.

LANGUAGE: write the VALUE of "draft" in __LANGNAME__. This is not optional: __LANGDIR__'''


def ghostwrite(profile, candidate, messages, lang="ru"):
    lang = "en" if str(lang).lower() == "en" else "ru"
    me = _baseline_signals(profile or {})
    them = {k: v for k, v in (candidate or {}).items()
            if k in ("name", "interests", "vibe", "langs", "area", "age")}
    thread = "\n".join(
        (("Me: " if m.get("who") == "me" else "Them: ") + str(m.get("text", "")))
        for m in (messages or [])[-12:] if str(m.get("text", "")).strip())
    ctx = ("MY PROFILE: %s\nTHE OTHER PERSON: %s\nCONVERSATION SO FAR:\n%s"
           % (json.dumps(me, ensure_ascii=False), json.dumps(them, ensure_ascii=False),
              thread or "(nothing yet — this is the first message)"))
    sys_prompt = (GHOSTWRITE_PROMPT
                  .replace("__LANGNAME__", _LANGNAME.get(lang, "Russian"))
                  .replace("__LANGDIR__", _LANGDIR.get(lang, _LANGDIR["ru"])))
    best = ""
    for attempt in range(2):
        try:
            raw = llm_complete(MODEL_ID, [{"role": "system", "content": sys_prompt},
                                          {"role": "user", "content": ctx}],
                               0.7 if attempt == 0 else 0.4)
            obj = _lenient_json(raw)
        except Exception:
            obj = None
        # The 70B translated the KEY itself ({"черновик": …}) when told to answer in Russian, so accept
        # the localised key too — a prompt rule alone is not a guarantee.
        o = obj or {}
        d = str(o.get("draft") or o.get("черновик") or o.get("сообщение") or
                (next(iter(o.values())) if len(o) == 1 else "") or "").strip()[:400]
        if not d:
            continue
        best = best or d
        if _lang_ok(d, lang):
            return {"draft": d, "lang": lang}
    # Wrong language twice: return nothing rather than put English words in a Russian user's mouth.
    return {"draft": best if _lang_ok(best, lang) else "", "lang": lang}


# ======================= INTENT BUILDER (conversational "Create intent") =======================
# The "Create intent" flow used to POST straight to matching's parser, which turned ANY text — even random
# letters — into an intent card, with no validation and no follow-up. This builder instead runs a SHORT
# dialogue: it validates (gibberish -> ask again, never build), asks for the missing essentials (activity,
# when, format) one at a time, and only when it has the gist returns ready:true with a CANONICAL intent
# (same filtration + build_intent as /chat, so matching can rank it). The card is shown for confirmation;
# the frontend launches the search separately.
INTENT_BUILD_PROMPT = '''You help the user create an "intent" — a plan to meet people or do an activity with someone. What matters is that the ACTIVITY is specific enough to search on. Timing and place are NOT your job: the app asks for the day, the time of day and the district on the very next screen.

Conversation so far is given. Return ONE JSON object, nothing else, WITH THE KEYS IN EXACTLY THIS ORDER:
{"valid":true|false, "ready":true|false,
 "reply":"<your message — a single question, or a short confirmation once you have the gist>",
 "activity":"<short activity phrase, once known>", "time":"<when, once known>", "format":"<1:1|small group|group, if the user mentioned it>",
 "hints":["<3 short things THE USER could say next>"]}
The order matters: "valid" must come before "reply".

Rules:
- valid:false when the latest message is NOT a plan to do something with people. That includes gibberish ("asdfgh"), greetings and small talk ("привет", "как дела", "спасибо"), and general questions ("что такое дивиденды", "какая погода") — anything a person could ask a chatbot rather than ask of a meetup. ready MUST then be false. Never build an intent from those.
- valid:true ONLY when the message really is about doing something with another person, even if the details are still missing ("хочу кофе" is valid, "привет" is not).
- NEVER ask about logistics: not when, not what day, not what time, not where, not which district or city, not how far. The next screen asks all of that with taps, so asking here makes the person answer the same thing twice. If they volunteer a time anyway, record it in "time" and move on without acknowledging it as a question.
- Ask at most TWO short questions, one per turn, and ONLY to make the request specific enough that a stranger could tell whether it is for them. Useful directions, pick what actually fits:
  * what they want out of it — «хочу выпить кофе» → «о чём хочется поговорить за кофе — про работу, про город, или просто познакомиться?»
  * which side of a broad interest — «футбол» → «поиграть или посмотреть матч?»
  * what kind of company — «вдвоём или небольшой компанией?»
  * the mood — «спокойно посидеть или куда-то выбраться?»
- Ask ONE thing at a time. Never stack two questions into one sentence.
- Never ask something the conversation already answered, and never ask a question whose answer would not change who you look for.
- ready:true as soon as the activity is specific enough to describe to a stranger in one line. If the first message was ALREADY specific («хочу поиграть в падл», «хочу обсудить стартапы за ужином»), confirm it in one line and set ready:true immediately — asking anything then is noise.
- Fold the answers into "activity" as one phrase: «coffee and startup talk», not just «coffee». That phrase is what the search runs on, so it is the whole point of asking.
- Keep reply short (1-2 sentences).
- "hints": exactly 3, each at most 6 words, written as the USER's own words in __LANGNAME__, never
  questions back at them and never repeats of each other. If your "reply" asked a question, the hints
  are plausible ANSWERS to it ("про работу", "лучше один на один"). Otherwise they are
  concrete next things this person could ask for. Use the PROFILE line at the top of the conversation
  to make them specific ("Найти компанию на утренний бег в Белграде", not "Заняться спортом").
  "hints" is the ONLY key you may omit; never omit or reorder the others.

LANGUAGE: write "reply" in __LANGNAME__ — the language this user writes in. This is not optional: __LANGDIR__ Every other value — activity, time, format — stays in ENGLISH, because the filtration and matching agents only understand English. (The transcript below is labelled "User:"/"Kleal:" in English for machine reasons; that says nothing about the reply language.)'''

_LANGNAME = {"ru": "Russian", "en": "English"}
_LANGDIR = {"ru": "every word of \"reply\" must be in Russian, in Cyrillic script.",
            "en": "every word of \"reply\" must be in English."}


_LAT_GLUE = re.compile(r"[а-яА-ЯёЁ][A-Za-z]|[A-Za-z][а-яА-ЯёЁ]")
_LAT_RUN = re.compile(r"[A-Za-z]")


def _lang_ok(reply, lang):
    """Did the model actually answer in the language the user wrote in?

    Only Russian is checkable cheaply and only Russian is the failure mode we see: the 70B slips into
    English on the FIRST intent-build turn, and because that turn then sits in the history, the rest of
    the conversation locks into English too. Three ways it goes wrong, all caught here:
      1. no Cyrillic at all      -> "Sounds good! When would you like to grab coffee?"
      2. Latin glued to Cyrillic -> "Завтраsounds как отличный план!" (always a generation artifact)
      3. mostly Latin            -> a sentence with one Russian word bolted on
    Latin words that stand on their own are LEFT ALONE — "поиграть в Dota", "Формула 1", venue and game
    names are normal Russian chat, so the ratio has to be well past half before we call it English.
    """
    if lang != "ru":
        return True
    s = str(reply or "")
    if not _CYR.search(s):
        return False
    if _LAT_GLUE.search(s):
        return False
    lat = len(_LAT_RUN.findall(s))
    cyr = len(_CYR.findall(s))
    return lat <= cyr


# Filtration answers a bare greeting with topics: "привет" -> ['hello','greeting'],
# "как дела" -> ['hello','greeting','how','are']. Those are conversational filler, not activities —
# treating them as topics kept greetings inside the intent builder and, worse, would let a greeting
# become a searchable intent whose "topics" are hello/greeting.
_FILLER_TOPICS = {"hello", "hi", "greeting", "greetings", "how", "are", "you", "thanks", "thank",
                  "bye", "goodbye", "ok", "okay", "yes", "no", "smalltalk", "small", "talk", "chat"}


def _real_topics(cat):
    """Topics from filtration with conversational filler removed."""
    ts = [str(t).strip().lower() for t in ((cat or {}).get("topics") or []) if str(t).strip()]
    return [t for t in ts if t not in _FILLER_TOPICS]


def _chat_reply(messages, profile, lang, on_text=None):
    """A conversational reply and NOTHING ELSE.

    Deliberately not buddy_chat(): that function is side-effecting — when wants_people() fires it runs
    the whole pipeline (filtration HTTP, then a real ranking POST to the matching service with a 45s
    timeout). Chaining it here would let an ordinary chat turn silently execute a search. Worse, the
    two triggers disagree by construction: _STRONG_ASK matches the bare stem "найд[иёе]", so
    "найди мне книгу по дивидендам" is valid:false to the intent builder AND True to wants_people —
    exactly the case that would fire a people-search nobody asked for. So this mirrors only the LLM
    call and drops the entire tail.
    """
    sig = _baseline_signals(profile)
    convo = "\n".join((("User: " + str(m.get("content", ""))) if m.get("role") == "user"
                       else ("Buddy: " + str(m.get("content", "")))) for m in (messages or [])[-12:])
    if sum(1 for m in (messages or []) if m.get("role") == "user") <= 1:
        convo = "[FIRST MESSAGE — you have never spoken with this person before]\n" + convo
    for attempt in range(2):
        try:
            msgs = [{"role": "system", "content": BUDDY_PROMPT.replace("__SIG__", json.dumps(sig))},
                    {"role": "user", "content": convo}]
            temp = 0.6 if attempt == 0 else 0.3
            if on_text is not None and attempt == 0:      # only the first try streams — see intent_build
                raw = llm_stream(MODEL_ID, msgs, temp, "reply", on_text)
            else:
                raw = llm_complete(MODEL_ID, msgs, temp)
            obj = _lenient_json(raw)
        except Exception:
            obj = None
        if isinstance(obj, dict) and obj.get("reply"):
            reply = str(obj["reply"])[:600]
            if _lang_ok(reply, lang):
                return reply
    return ""


# Not "мне 15 минут идти" / "мне 15 лет назад" — a bare number followed by one of these is not an age.
_AGE_NOT_YEARS = re.compile(r"^\s*(мин|час|км|кг|мет|руб|дол|евр|тыс|проц|град|сек|дн|нед|мес|назад)", re.I)
_AGE_RU = re.compile(r"(?:мне|я)\s+(?:только\s+|всего\s+|уже\s+)?(\d{1,2})\s*(лет|год|года|годика|годиков)?\b")
_AGE_EN = [re.compile(r"\b(?:i'?m|i am)\s+(\d{1,2})\b"),
           re.compile(r"\b(\d{1,2})\s*(?:years?\s*old|y\.?o\.?)\b")]


def stated_minor(messages):
    """Did the person say, in their own words, that they are under 18?

    Deterministic and BEFORE the model, so it cannot be talked around: a matching service that pairs
    a self-declared 15-year-old with adults is not a bug to soften, and an LLM asked to judge this
    would negotiate. Conservative about what counts as an age («мне 15 минут идти» is not one) and
    decisive once it does. Scans the whole transcript, so the statement keeps holding on later turns.
    """
    for m in (messages or []):
        if m.get("role") != "user":
            continue
        t = str(m.get("content") or "").lower()
        for mt in _AGE_RU.finditer(t):
            if mt.group(2) is None and _AGE_NOT_YEARS.match(t[mt.end():]):
                continue
            if t[mt.end():].strip().startswith("назад"):
                continue
            n = int(mt.group(1))
            if 1 <= n < 18:
                return n
        for rx in _AGE_EN:
            for mt in rx.finditer(t):
                n = int(mt.group(1))
                if 1 <= n < 18:
                    return n
    return None


MINOR_REPLY = {
    "ru": "Kleal работает с 18 лет, так что подбирать встречи я тут не смогу. "
          "Если тебе уже есть 18 — поправь возраст в профиле, и вернёмся к этому.",
    "en": "Kleal is for 18 and over, so I can't set up meetups here. "
          "If you are 18 or older, correct your age in your profile and we'll pick this up again.",
}


def _profile_line(p):
    """One compact line at the top of the transcript so the hints can name this person's own city and
    interests instead of offering everyone the same three openers. Interests the user switched off in
    the client are already filtered there; this only formats what arrives."""
    p = p or {}
    ints = [str(i) for i in (p.get("interests") or []) if str(i).strip()][:6]
    bits = [str(p.get("city") or p.get("area") or "").strip(), ", ".join(ints)]
    line = " | ".join(b for b in bits if b)
    return ("PROFILE: " + line + "\n") if line else ""


def _hints(obj, lang):
    """Three or none. A row of one usable chip reads as a bug, and the client has deterministic
    layers that are strictly better than a partial list."""
    out = []
    for h in ((obj or {}).get("hints") or [])[:6]:
        t = re.sub(r"\s+", " ", str(h or "")).strip().strip('"\u00ab\u00bb\u2013-\u2022 ').rstrip(".!?")
        if not t or len(t) > 48 or not _lang_ok(t, lang):
            continue
        if t.lower() in [x.lower() for x in out]:
            continue
        out.append(t)
    return out[:3] if len(out) >= 3 else []


def intent_build(messages, profile, on_text=None):
    last_user = next((str(m.get("content", "")) for m in reversed(messages or []) if m.get("role") == "user"), "")
    lang = detect_lang(last_user)
    # Before anything else, and before the model: a person who has said they are under 18 gets no
    # intent built, on this turn or any later one. The reply is fixed text, not a generation, so
    # there is nothing to argue with and no way for a later turn to talk it back open.
    if stated_minor(messages) is not None:
        return {"reply": MINOR_REPLY.get(lang, MINOR_REPLY["en"]), "valid": False, "ready": False,
                "intent": None, "lang": lang, "conversational": True, "hints": []}
    convo = "\n".join((("User: " + str(m.get("content", ""))) if m.get("role") == "user"
                       else ("Kleal: " + str(m.get("content", "")))) for m in (messages or [])[-12:])
    convo = _profile_line(profile) + convo
    sys_prompt = (INTENT_BUILD_PROMPT
                  .replace("__LANGNAME__", _LANGNAME.get(lang, "English"))
                  .replace("__LANGDIR__", _LANGDIR.get(lang, _LANGDIR["en"])))
    # Two attempts: the language directive alone still slips occasionally, and one English turn drags the
    # whole conversation into English because it goes into the history. Cheaper to re-roll than to strand
    # a Russian first-run user in an English dialogue.
    obj = None
    for attempt in range(2):
        try:
            msgs = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": convo}]
            temp = 0.5 if attempt == 0 else 0.2
            # Only the FIRST attempt streams. A re-roll happens because the first answer was rejected
            # (wrong language / unparseable), and the user has already watched that text appear —
            # streaming the replacement on top would make the bubble rewrite itself mid-read.
            if on_text is not None and attempt == 0:
                # Gate on the builder's OWN verdict, which the prompt now emits BEFORE the text: when
                # valid is false this reply is about to be thrown away for a conversational answer, so
                # not one character of it reaches the screen. Without this the user watched the refusal
                # type out and then turn into a different answer — indistinguishable from the model
                # hallucinating and correcting itself, which is exactly how it was reported.
                raw = llm_stream(MODEL_ID, msgs, temp, "reply", on_text, gate=("valid", True))
            else:
                raw = llm_complete(MODEL_ID, msgs, temp)
            cand = _lenient_json(raw)
        except Exception:
            cand = None
        if not isinstance(cand, dict) or not cand.get("reply"):
            continue
        if obj is None:
            obj = cand          # keep the first structurally valid answer even if its language is wrong
        if _lang_ok(cand.get("reply"), lang):
            obj = cand
            break
    # Both attempts slipped: keep the extracted activity/time/ready (they are English by design and still
    # correct) but do not show the user an English sentence — swap in the neutral prompt in their language.
    if isinstance(obj, dict) and obj.get("reply") and not _lang_ok(obj.get("reply"), lang):
        obj = dict(obj, reply=("Понял. Когда тебе удобно?" if obj.get("ready") is not True
                               else "Понял, записал."))
    if not isinstance(obj, dict) or not obj.get("reply"):
        chat = _chat_reply(messages, profile, lang)     # the builder failed; still answer the person
        return {"reply": chat or ("Что хочешь устроить? Опиши, чем заняться и с кем." if lang == "ru"
                                  else "What would you like to set up? Tell me what and with whom."),
                "valid": False, "ready": False, "intent": None, "lang": lang,
                "conversational": bool(chat), "hints": []}
    reply = str(obj.get("reply"))[:400]
    valid = bool(obj.get("valid", True))
    ready = bool(obj.get("ready")) and valid
    activity = str(obj.get("activity") or last_user)
    user_turns = sum(1 for m in (messages or []) if m.get("role") == "user")
    # Backstop against over-asking: the 70B tends to keep interrogating (group size, exact place...). Once the
    # user has already answered at least one follow-up AND we can recognise a real activity, build the card
    # instead of asking further — sensible defaults cover the rest.
    # Was >= 2, which forced ready right after the first answer. Two clarifying questions are the
    # point now, so the backstop moves out by one — it still exists, because the 70B will happily
    # interrogate forever.
    if valid and not ready and user_turns >= 3 and _categorize(activity).get("topics"):
        if build_intent(_baseline_signals(profile), _categorize(activity), activity, lang).get("rankable"):
            ready = True
    # Hand the turn to the conversational agent when there is no plan to build. Two signals, because
    # one is not enough: the model marks obvious non-asks valid:false, but it called the typo greeting
    # "привкет" VALID and still answered it with a refusal ("Опишите, что вы хотели бы сделать с
    # кем-то"). So also catch: nothing ready, no activity extracted, and the raw text categorises to
    # no topic at all — i.e. there is genuinely nothing to build on. A real but incomplete ask
    # ("хочу кофе", no time) still has an activity AND a topic, so it stays in the builder.
    # Deliberately NOT keyed on obj["activity"] — the model fills that field unreliably (it echoed the
    # raw text for one typo'd greeting and left it empty for the next identical case), which made the
    # branch flap between runs. Filtration is the stable signal. `cat is not None` matters: filtration
    # returns None when it times out, and without that guard a slow filtration would push a REAL ask
    # into small talk instead of building it.
    # Classify AFTER the model, not before. Pre-classifying let chit-chat skip a wasted builder call,
    # but filtration is itself an LLM call — measured, it pushed the first streamed token from 0.16s to
    # 1.86s on EVERY request, including real ones. Streaming exists to make the common path feel
    # instant, so the common path wins; the rare chit-chat swap is handled by the explicit reset event.
    _cat = _categorize(last_user)
    nothing_to_build = (not ready and _cat is not None and not _real_topics(_cat))
    if not valid or nothing_to_build:
        # If _chat_reply comes back empty (bad JSON, or the language guard rejected both attempts) we
        # must NOT fall through to the builder — that is what produced "Опишите, что вы хотели бы
        # сделать с кем-то" in response to a greeting. Measured: the fall-through made the typo
        # "привкет" a coin flip, 4 of 8 runs. A plain acknowledgement is always the better answer.
        # This reply is the first and only text that reaches the screen (the gate suppressed the
        # builder's discarded draft), so stream it — it is also the long one worth streaming.
        chat = _chat_reply(messages, profile, lang, on_text=on_text) or (
            "Привет! Чем могу помочь?" if lang == "ru" else "Hey! How can I help?")
        return {"reply": chat, "valid": valid, "ready": False, "intent": None, "lang": lang,
                "conversational": True, "hints": _hints(obj, lang)}
    if not ready:
        return {"reply": reply, "valid": valid, "ready": False, "intent": None, "lang": lang,
                "hints": _hints(obj, lang)}

    # ready -> assemble a canonical, rankable intent (filtration + the same builder /chat uses)
    cat = _categorize(activity)
    sig = _baseline_signals(profile)
    if obj.get("time"):
        sig["time"] = str(obj.get("time"))
    intent = build_intent(sig, cat, activity, lang)
    if obj.get("format"):
        intent["format"] = str(obj.get("format"))[:40]
    # guard: if nothing rankable survived canonicalisation, don't pretend it's ready
    if not intent.get("rankable"):
        return {"reply": (("Понял тему, но пока не за что зацепиться для поиска — уточни, чем именно заняться?")
                          if lang == "ru" else
                          "I got the gist, but there's nothing concrete to search on yet — what exactly do you want to do?"),
                "valid": True, "ready": False, "intent": None, "lang": lang, "hints": []}
    return {"reply": reply, "valid": True, "ready": True, "intent": intent, "lang": lang,
            "hints": _hints(obj, lang)}


# ======================= HTTP =======================
class H(BaseHTTPRequestHandler):
    def _route(self):
        """Serve every endpoint both behind the gateway (/api/buddy/*) and bare (/buddy/*)."""
        p = (self.path or "/").split("?")[0]
        for pfx in ("/api/buddy", "/buddy"):
            if p.startswith(pfx):
                return p[len(pfx):] or "/"
        return p

    def do_OPTIONS(self):
        self.send_response(204)                      # CORS headers come from end_headers() below
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        r = self._route()
        if r in ("/", "/health"):
            return send_json(self, 200, {"service": "buddy", "ok": True, "model": MODEL_ID,
                                         "filter_url": FILTER_URL, "match_url": MATCH_URL,
                                         "sessions": len(SESSIONS)})
        if r == "/state":
            q = (self.path.split("?", 1) + [""])[1]
            uid = dict(kv.split("=", 1) for kv in q.split("&") if "=" in kv).get("user_id", "")
            s = SESSIONS.get(uid) or {}
            return send_json(self, 200, {"user_id": uid, "signals": s.get("signals") or {},
                                         "turns": len(s.get("thread") or []), "summary": s.get("summary")})
        send_json(self, 404, {})

    def do_POST(self):
        r = self._route()
        body = read_json(self)
        uid = str(body.get("user_id") or "").strip() or None
        try:
            if r == "/chat":
                profile = body.get("profile") if isinstance(body.get("profile"), dict) else {}
                if isinstance(body.get("messages"), list) and body["messages"]:
                    res = buddy_chat(body["messages"], profile, body.get("signals") or {}, uid)   # stateless
                elif uid and body.get("message"):
                    s = _session(uid)                                                             # stateful
                    if profile:
                        s["profile"] = profile
                    s["thread"] = (s.get("thread") or [])[-22:] + [{"role": "user", "content": str(body["message"])}]
                    res = buddy_chat(s["thread"], s.get("profile") or {}, s.get("signals") or {}, uid)
                    s["thread"].append({"role": "assistant", "content": res.get("reply", "")})
                    s["signals"] = res.get("signals") or {}
                    if res.get("intent"):
                        s["intent"] = res["intent"]
                    _save_store()
                else:
                    return send_json(self, 400, {"error": "need {messages} or {user_id, message}"})
                return send_json(self, 200, res)

            if r == "/launch":
                # The "Launch search" button: re-run matching on the confirmed intent and let each
                # candidate's agent negotiate, so the result carries real accept/decline verdicts.
                s = _session(uid) if uid else {}
                intent = body.get("intent") if isinstance(body.get("intent"), dict) else (s.get("intent") or {})
                if not intent:
                    return send_json(self, 400, {"error": "no intent to launch"})
                intent = apply_override(intent, body.get("override"))
                lang = intent.get("lang") or "en"
                sig = s.get("signals") or (body.get("signals") if isinstance(body.get("signals"), dict) else {})
                owner = (s.get("profile") or {}).get("name") or (body.get("profile") or {}).get("name")
                block, cards = run_match(intent, sig, uid, lang, negotiate=True, owner=owner)
                if uid:
                    s["intent"] = intent
                    _save_store()
                return send_json(self, 200, {"intent": intent, "match": block, "matches": cards,
                                             "fallback": block.get("fallback"), "lang": lang})

            if r == "/profile-edit":                 # "Edit with Kleal": free text -> profile patch (frontend applies)
                msg = body.get("message") or ""
                prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
                return send_json(self, 200, profile_edit(msg, prof, detect_lang(msg)))

            if r == "/intent-build":                 # conversational "Create intent": validate + ask + build
                msgs = body.get("messages") if isinstance(body.get("messages"), list) else []
                prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
                if not body.get("stream"):
                    return send_json(self, 200, intent_build(msgs, prof))
                # Streamed variant. Deltas start flowing before we know whether this turn is small talk
                # or a real intent — that verdict only exists once the whole JSON envelope has parsed,
                # so it rides in `done` and the client applies its usual branching there.
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("X-Accel-Buffering", "no")
                self.send_header("Connection", "close")
                self.end_headers()
                alive = [True]
                shown = []                  # exactly what the user has watched appear, for the check below

                def emit(event, obj):
                    if not alive[0]:
                        return
                    try:
                        self.wfile.write(("event: %s\ndata: %s\n\n" % (
                            event, json.dumps(obj, ensure_ascii=False))).encode("utf-8"))
                        self.wfile.flush()
                    except (BrokenPipeError, ConnectionResetError):
                        alive[0] = False        # user left mid-stream; finish the work, stop writing

                def sink(t):
                    shown.append(t)
                    emit("delta", {"t": t})

                try:
                    out = intent_build(msgs, prof, on_text=sink)
                    # A re-roll, or the hand-off to the conversational agent, produces a DIFFERENT reply
                    # from the one the user just watched appear. Tell the client so it can replace the
                    # bubble instead of leaving a stale half-sentence stranded above the real answer.
                    emit("done", dict(out, replaced=("".join(shown) != (out.get("reply") or ""))))
                except Exception as e:
                    emit("error", {"error": str(e)[:200]})
                return

            if r == "/ghostwrite":                   # Kleal drafts the user's OWN next message
                return send_json(self, 200, ghostwrite(
                    body.get("profile") or {}, body.get("candidate") or {},
                    body.get("messages") or [], body.get("lang") or "ru"))

            if r == "/persona":                      # the Kleal personality test -> one prose summary
                prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
                ans = body.get("answers") if isinstance(body.get("answers"), list) else []
                return send_json(self, 200, persona(prof, body.get("story") or "", ans,
                                                    body.get("current") or "", body.get("lang") or "ru"))

            if r == "/resummary":                    # after a profile edit: rewrite the summary to fit (adapt, not append)
                prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
                return send_json(self, 200, resummary(prof, body.get("current") or "",
                                                      body.get("lang") or "ru",
                                                      body.get("personality") or ""))

            if r == "/intro":                        # the candidate's agent writes the icebreaker
                return send_json(self, 200, _post(MATCH_URL, "/api/agent/intro",
                                                  {"intent": body.get("intent") or {},
                                                   "candidate": body.get("candidate") or {}}, timeout=60))

            if r == "/feedback":                     # teach the ranker from the user's accept/pass
                return send_json(self, 200, _post(MATCH_URL, "/api/agent/feedback",
                                                  {"name": body.get("name"), "decision": body.get("decision"),
                                                   "uid": uid or "me"}))

            if r == "/onboard":
                return send_json(self, 200, onboard(uid, body.get("profile") or {}))

            send_json(self, 404, {})
        except Exception as e:
            lang = detect_lang(body.get("message") or "")
            send_json(self, 200, {"reply": _GLITCH[lang], "signals": body.get("signals") or {},
                                  "match": None, "matches": [], "intent": None, "error": str(e)[:200]})

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        BaseHTTPRequestHandler.end_headers(self)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Kleal buddy-service on http://127.0.0.1:%d  (LLM llm-service, filter %s, match %s)"
          % (PORT, FILTER_URL, MATCH_URL))
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
