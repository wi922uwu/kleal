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
from llm_client import llm_complete
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


def wants_people(text, model_flagged):
    """Deterministic search trigger. STRONG ask always; COMPANION cue only with the model's agreement."""
    t = str(text or "")
    if _STRONG_ASK.search(t):
        return True
    return bool(model_flagged and _COMPANION.search(t))

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

Reply as ONE JSON object only, nothing outside it:
{"reply":"<your natural, helpful message>","signals":{<only fields you newly learned THIS turn; may include "interest">},"match":true|false}

LANGUAGE: write "reply" in the SAME language the user writes in (they write Russian -> you answer in Russian). Every other value — signals, interest, topics, time, area — stays in ENGLISH, because the filtration and matching agents only understand English.'''


# ======================= CANONICALISATION (make the intent rankable) =======================
# RU (and loose EN) surface forms -> the exact words matching's TAXONOMY understands.
TOPIC_ALIASES = {
    # sports
    "футбол": "football", "соккер": "football", "матч": "football", "баскетбол": "basketball",
    "баскет": "basketball", "волейбол": "volleyball", "теннис": "tennis", "падел": "padel",
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
    "инвестиции": "investing", "инвестор": "investor", "карьера": "career", "дизайн": "design",
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
           "boardgame": "boardgames", "videogames": "gaming"}
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
    for k in _ALIAS_KEYS:
        if len(k) >= 5 and k in w:
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
             "that", "this", "тему", "темы", "человек", "человека", "который", "которые"}


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


def _title_for(topics, typ, lang):
    if typ == "dating":
        return "Свидание" if lang == "ru" else "Date"
    if topics:
        return topics[0].capitalize() + (" — встреча" if lang == "ru" else " meetup")
    return "Встреча" if lang == "ru" else "Meet someone"


def build_intent(sig, cat, last_user, lang):
    """Filtration result + signals -> the intent matching ranks on.
    Machine fields are canonical English; the card fields follow the user's language."""
    cat = cat or {}
    # engine topics: prefer words the ranker resolves (RU -> EN, taxonomy-validated).
    topics = (norm_topics(cat.get("topics")) or norm_topics(sig.get("interest"))
              or norm_topics(sig.get("topics")) or norm_topics(re.findall(r"[\w']+", str(last_user).lower())))
    # Interests the taxonomy doesn't cover ("apple", "рыбалка", "labubu") canonicalise to nothing. Keep the
    # raw significant words — matching's _wshare does literal-word overlap, so two people who both listed
    # "apple" still match. This runs BEFORE the category bridge so a specific interest isn't replaced by a
    # generic taxonomy word (apple -> ai). filtration's topics are already cleaned; else use the raw text.
    if not topics:
        topics = [str(t).lower()[:24] for t in (cat.get("topics") or []) if str(t).strip()][:4]
    if not topics:
        topics = [w[:24] for w in re.findall(r"[a-zа-яё0-9]{4,}", str(sig.get("interest") or last_user).lower())
                  if w not in _RAW_STOP][:3]
    if not topics:                                    # last resort: nearest taxonomy word for the category
        topics = CATEGORY_BRIDGE.get(str(cat.get("category") or ""), [])
    # card tags: what the user actually asked for (may be outside the taxonomy — "labubu" stays "labubu")
    tags = [str(t).lower()[:24] for t in (cat.get("topics") or []) if str(t).strip()][:4] or topics
    typ = str(cat.get("type") or sig.get("type") or "").lower()
    if typ not in ("dinner", "sport", "gaming", "networking", "dating", "language", "social", "other"):
        typ = "dating" if sig.get("datingOk") and any(
            w in str(last_user).lower() for w in ("dating", "date", "свидан", "знаком")) else infer_type(topics)
    role = ROLE_WORDS.get(str(cat.get("role") or "").lower()) or \
        ROLE_WORDS.get(str(sig.get("role") or "").lower()) or infer_role(sig.get("interest") or last_user)
    dating = typ == "dating"
    demand = str(sig.get("interest") or "") + " " + str(last_user or "")
    req_langs = norm_langs(sig.get("languages")) if any(w in demand.lower() for w in LANG_DEMAND) else []
    place = str(sig.get("area") or ("Публичные места рядом" if lang == "ru" else "Public places nearby"))[:60]
    title = _title_for(tags or topics, typ, lang)
    return {
        # ---- machine-facing: matching-service reads exactly these ----
        "title": title, "type": typ, "topics": topics or ["social"], "role": role, "mode": "offline",
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
        "rankable": bool(topics),          # False -> the ranker has no word for this yet; be honest, don't fake
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
    """One matching candidate -> the card the UI draws. `reasons` stays verbatim for the legacy UI."""
    return {"user_id": c.get("name"), "name": c.get("name"), "score": c.get("score"), "km": c.get("km"),
            "tier": c.get("tier"), "kind": c.get("kind"), "vibe": c.get("vibe"), "open": c.get("open"),
            "verified": c.get("verified"), "interests": c.get("interests") or [], "role": c.get("role"),
            "reasons": c.get("reasons") or [], "reason": humanize(c.get("reasons"), lang),
            "agree": c.get("agree"), "note": c.get("note"), "reply": c.get("reply")}


def run_match(intent, sig, uid, lang, negotiate=False):
    """Hand the intent to the matching agent; optionally let each candidate's agent negotiate.
    Returns (legacy_match_block, cards). Never fabricates people."""
    prof = {"languages": {"comfortable": norm_langs(sig.get("languages"))}, "vibe": sig.get("vibe"),
            "city": sig.get("area")}
    try:
        res = _post(MATCH_URL, "/api/agent/match",
                    {"intent": intent, "profile": prof, "ctx": {"uid": uid or "me"}}, timeout=45)
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
_CLICK = {"ru": "Думаю, вы сойдётесь с %s — %s.", "en": "I think you'd click with %s — %s."}
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
        want_match = bool(_STRONG_ASK.search(last_user))
        reply = _FALLBACK_REPLY[lang][0 if want_match else 1]

    out = {"reply": reply, "signals": sig, "lang": lang, "match": None,
           "intent": None, "matches": [], "tool_call": None, "category": None}
    if not want_match:
        return out

    # 1) filtration categorises what they want; 2) buddy makes it rankable; 3) matching scores it.
    req_text = sig.get("interest") or last_user or " ".join(sig.get("topics") or [])
    cat = _categorize(req_text)
    intent = build_intent(sig, cat, last_user, lang)
    out["tool_call"] = "find_people"
    out["intent"] = intent
    out["category"] = cat

    if not intent.get("rankable"):
        # Categorised fine, but the ranker has no vocabulary for it yet (e.g. "labubu"). Say so — do not
        # silently return an empty list, and do not match the wrong people just to show a card.
        out["match"] = {"intent": intent, "top": None, "candidates": [], "fallback": None}
        out["reply"] = (reply + "\n\n" + _NEW[lang] % (intent.get("category") or "?")).strip()
        return out

    block, cards = run_match(intent, sig, uid, lang)
    out["match"] = block
    out["matches"] = cards
    if block.get("top"):
        t = block["top"]
        why = humanize(t.get("reasons"), lang) or ("хороший фит" if lang == "ru" else "a great fit")
        out["reply"] = (reply + "\n\n" + _CLICK[lang] % (t.get("name"), why)).strip()
    else:
        catn = intent.get("category")
        out["reply"] = (reply + "\n\n" + (_FILED[lang] % catn if catn else _NO_ONE[lang])).strip()
    return out


ONBOARD_PROMPT = ('You are Kleal. In 2 short sentences, warmly summarise what you now know about this person '
                  '(interests, city, languages, how they like to meet). Speak TO them ("You…"). No lists, no JSON.')


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
RESUMMARY_PROMPT = '''You are Kleal. Below is a user's current profile summary and their up-to-date profile data. Rewrite the SUMMARY as ONE warm, natural, flowing paragraph that reflects the CURRENT data. Integrate every change smoothly into the prose — NEVER just append or list words. Keep the SAME language as the existing summary (if it is in English, stay English; if Russian, stay Russian). Speak TO the user ("You…" / "Ты…"). 2-4 sentences, concrete, no bullet points, output ONLY the paragraph.'''


def resummary(profile, current):
    """Rewrite the profile summary to integrate the latest changes (adapt, don't append)."""
    payload = ("CURRENT SUMMARY:\n" + str(current or "(none yet)") +
               "\n\nUP-TO-DATE PROFILE DATA:\n" + json.dumps(profile or {}, ensure_ascii=False)[:2200])
    try:
        s = llm_complete(MODEL_ID, [{"role": "system", "content": RESUMMARY_PROMPT},
                                    {"role": "user", "content": payload}], 0.5)
        return {"summary": str(s or "").strip()[:900]}
    except Exception:
        return {"summary": ""}


# ======================= INTENT BUILDER (conversational "Create intent") =======================
# The "Create intent" flow used to POST straight to matching's parser, which turned ANY text — even random
# letters — into an intent card, with no validation and no follow-up. This builder instead runs a SHORT
# dialogue: it validates (gibberish -> ask again, never build), asks for the missing essentials (activity,
# when, format) one at a time, and only when it has the gist returns ready:true with a CANONICAL intent
# (same filtration + build_intent as /chat, so matching can rank it). The card is shown for confirmation;
# the frontend launches the search separately.
INTENT_BUILD_PROMPT = '''You help the user create an "intent" — a plan to meet people or do an activity with someone. Keep it SHORT: you only need two things — the ACTIVITY and roughly WHEN. Ask at most ONE brief question, and only if one of those is missing.

Conversation so far is given. Return ONE JSON object, nothing else:
{"reply":"<your message — a single question, or a short confirmation once you have the gist>",
 "valid":true|false, "ready":true|false,
 "activity":"<short activity phrase, once known>", "time":"<when, once known>", "format":"<1:1|small group|group, if the user mentioned it>"}

Rules:
- valid:false ONLY when the latest message is gibberish / not about doing something with people (e.g. random letters "asdfgh"). Then reply asks them to describe what they'd like to do, and ready MUST be false. Never build an intent from nonsense.
- ready:true as soon as you know the ACTIVITY and any sense of WHEN (a day, "today", "this weekend", or "whenever"). Do NOT keep asking — format, group size, exact place, number of people are OPTIONAL and default sensibly. If the user already gave activity + time in one message, set ready:true right away with a one-line confirmation.
- Only when the activity is clear but timing is totally absent, ask the single question "when?". Never ask more than that.
- Keep reply short (1-2 sentences), in the user's language. activity/time/format values in English.'''


def intent_build(messages, profile):
    last_user = next((str(m.get("content", "")) for m in reversed(messages or []) if m.get("role") == "user"), "")
    lang = detect_lang(last_user)
    convo = "\n".join((("User: " + str(m.get("content", ""))) if m.get("role") == "user"
                       else ("Kleal: " + str(m.get("content", "")))) for m in (messages or [])[-12:])
    obj = None
    try:
        raw = llm_complete(MODEL_ID, [{"role": "system", "content": INTENT_BUILD_PROMPT},
                                      {"role": "user", "content": convo}], 0.5)
        obj = _lenient_json(raw)
    except Exception:
        obj = None
    if not isinstance(obj, dict) or not obj.get("reply"):
        return {"reply": ("Что хочешь устроить? Опиши, чем заняться и с кем." if lang == "ru"
                          else "What would you like to set up? Tell me what and with whom."),
                "valid": False, "ready": False, "intent": None, "lang": lang}
    reply = str(obj.get("reply"))[:400]
    valid = bool(obj.get("valid", True))
    ready = bool(obj.get("ready")) and valid
    activity = str(obj.get("activity") or last_user)
    user_turns = sum(1 for m in (messages or []) if m.get("role") == "user")
    # Backstop against over-asking: the 70B tends to keep interrogating (group size, exact place...). Once the
    # user has already answered at least one follow-up AND we can recognise a real activity, build the card
    # instead of asking further — sensible defaults cover the rest.
    if valid and not ready and user_turns >= 2 and _categorize(activity).get("topics"):
        if build_intent(_baseline_signals(profile), _categorize(activity), activity, lang).get("rankable"):
            ready = True
    if not ready:
        return {"reply": reply, "valid": valid, "ready": False, "intent": None, "lang": lang}

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
                "valid": True, "ready": False, "intent": None, "lang": lang}
    return {"reply": reply, "valid": True, "ready": True, "intent": intent, "lang": lang}


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
                block, cards = run_match(intent, sig, uid, lang, negotiate=True)
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
                return send_json(self, 200, intent_build(msgs, prof))

            if r == "/resummary":                    # after a profile edit: rewrite the summary to fit (adapt, not append)
                prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
                return send_json(self, 200, resummary(prof, body.get("current") or ""))

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
