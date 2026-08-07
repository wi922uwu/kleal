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
import config                                  # the one topology table (ports/URLs/store paths)
from llm_client import llm_complete, llm_stream
from http_util import send_json, read_json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = config.PORTS["buddy"]
MODEL_ID = config.MODEL_ID
MATCH_URL = config.MATCH_URL
FILTER_URL = config.FILTER_URL
STORE_PATH = config.BUDDY_STORE

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
    r"match\s+me|connect\s+me|introduce\s+me|hook\s+me\s+up|teammate|"
    # SPANISH. Missing entirely until now, so «quiero encontrar a alguien para jugar al pádel» —
    # about as explicit as an ask gets — never started a search: buddy asked a follow-up question
    # instead, and the ES half of the audience could not reach matching at all. Mirrors the Russian
    # «ищу …» shape: the verb alone is not enough (\"busco un libro\" is not an ask for people).
    r"busc\w*\s+(a\s+)?(alguien|gente|personas?|compañer|companer|pareja|jugador|equipo|grupo|amigos?)|"
    r"encontrar\s+(a\s+)?(alguien|gente|personas?|compañer|companer|jugador)|"
    r"encu[eé]ntrame|preséntame|presentame|conocer\s+(gente|personas)|"
    r"alguien\s+(quiere|que\s+quiera|se\s+apunta)|qui[eé]n\s+se\s+apunta|"
    r"compañer[oa]\s+de|companer[oa]\s+de|pareja\s+de\s+juego", re.I)
_COMPANION = re.compile(
    r"с\s+кем|кого-нибудь|кто-нибудь|компани[юе]|"
    r"someone\s+to\b|somebody\s+to\b|people\s+to\b|with\s+(someone|somebody|people)|"
    r"con\s+alguien|alguien\s+para|gente\s+para|con\s+qui[eé]n|acompañante", re.I)
# language-exchange asks read as "I want a person to practise with" even without a STRONG verb —
# "практиковать испанский с носителем" / "language partner" should search, not just chat.
_STRONG_ASK_EXTRA = re.compile(
    r"с\s+носител|носител[ья]\s+язык|языков\w*\s+обмен|language\s+(partner|exchange)|"
    r"practi[cs]e\s+\w+\s+with|language\s+buddy|"
    r"intercambio\s+(de\s+)?(idiomas?|ling)|practicar\s+\w+\s+con|hablante\s+nativo|con\s+un\s+nativo", re.I)


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
    r"i\s+want\s+to|i'?d\s+like\s+to|i\s+wanna|want\s+to\s+go|planning\s+to|thinking\s+of|"
    r"quiero|quisiera|me\s+gustar[ií]a|tengo\s+ganas\s+de|me\s+apetece|planeo|pienso\s+ir)\b", re.I)
_PAST = re.compile(r"вчера|позавчера|на\s+прошлой\s+неделе|yesterday|last\s+(week|night|time)|"
                   r"\bayer\b|anteayer|anoche|la\s+semana\s+pasada", re.I)


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


# ── Negation ──────────────────────────────────────────────────────────────────────────────────────
# «Не хочу в бар, хочу что-то тихое» used to search for BAR — the one thing the person ruled out.
# Nothing anywhere in the pipeline read «не»: the model happily reports the mentioned entity as the
# interest, and both the alias table and the raw-word union then carry it through as a topic.
# Negation scopes over its CLAUSE, which is why this splits on commas and on «но»/«а» first — in
# «хочу гулять, но только не спорт» the negation must reach спорт and must not reach гулять.
_NEG_TRIGGER = re.compile(r"(?:^|[\s,;—-])(?:не|нет|кроме|без|никаких|ничего|"
                          r"don'?t|do\s+not|not|except|without|no)(?:\s|$)", re.I)
_CLAUSE_SPLIT = re.compile(r"[,;.!?]|\bно\b|\bа\b|\bbut\b", re.I)
# Words that are never the thing being ruled out — they are the ruling-out itself, or filler.
_NEG_NOISE = {"не", "нет", "только", "кроме", "без", "никаких", "ничего", "хочу", "хочется",
              "что", "чего", "угодно", "это", "нибудь", "какой", "какая", "какое", "тоже",
              "not", "no", "dont", "don", "any", "anything", "want", "just", "only", "except",
              "without", "something", "the", "and"}


def negated_terms(text):
    """Everything the user explicitly ruled out, as canonical topics AND raw words.

    Two scoping rules, both learned from getting them wrong:
    - negation reaches FORWARD from its trigger, not over the whole sentence. «хочу футбол без
      алкоголя» rules out alcohol, not football, and football sits before the trigger.
    - it does not cross a clause boundary, so «хочу гулять, но только не спорт» leaves гулять alone.
    Bucket words are deliberately NOT skipped here: «не спорт» is precisely a negated bucket, and
    filtering it as noise is what made the first version miss it.

    Raw words are kept alongside canonical ones because the union path carries unresolvable words
    verbatim — dropping only the canonical form would still let «бар» through as a literal tag."""
    out = set()
    for clause in _CLAUSE_SPLIT.split(str(text or "").lower()):
        m = _NEG_TRIGGER.search(" " + clause)
        if not m:
            continue
        tail = (" " + clause)[m.end():]
        for w in re.findall(r"[a-zа-яёáéíóúüñç0-9-]{3,}", tail):
            if w in _NEG_NOISE:
                continue
            n = norm_topic(w)
            if n:
                out.add(n)
            out.add(w)
    return out


# A word the taxonomy cannot resolve is not the same as no interest. These are the shapes a NEW
# interest arrives in — a proper noun, a brand, a hobby nobody has listed yet — and they must not be
# mistaken for the empty-handed «хочу спать».
_NOT_A_SUBJECT = re.compile(r"^(спать|есть|пить|жить|домой|туда|сюда|обратно|назад|уже|ещё|еще|"
                            r"сам|сама|сами|так|тут|там|очень|просто|home|sleep|out)$", re.I)


def _has_novel_subject(text):
    """Is there a content word that could BE the interest, even though the taxonomy has never heard
    of it? Deliberately shallow — it only decides whether the question is worth asking; filtration
    makes the actual call."""
    for w in re.split(r"[^\w'-]+", str(text or "").lower()):
        if len(w) < 4 or w in _RAW_STOP or w in _GENERIC_TOPIC or w in _NEG_NOISE:
            continue
        if _is_verbish(w) or _NOT_A_SUBJECT.match(w):
            continue
        if norm_topic(w):
            continue                       # known word — the fast path already handled it
        return True
    return False


def wants_people(text, model_flagged, ask_filtration=None):
    """Deterministic search trigger.

    STRONG ask always; COMPANION needs the model's agreement; DESIRE needs a subject.

    The subject test has two tiers because the taxonomy is 165 words and interests are not. The fast
    tier is a taxonomy hit. When that misses but the sentence still names something — «хочу собирать
    лабубу», «хочу шить на машинке» — the word is handed to filtration, which exists precisely to
    magnetise unseen text onto a category and answers `other` when there is nothing there. Without
    this second tier every interest outside the 165 words was silently unsearchable: the trigger I
    wrote to stop buddy chatting instead of searching had made novel interests invisible.
    """
    t = str(text or "")
    if _STRONG_ASK_EXTRA.search(t):
        return True
    if _STRONG_ASK.search(t):
        return True
    if model_flagged and _COMPANION.search(t):
        return True
    if not (_DESIRE.search(t) and not _PAST.search(t)):
        return False
    if _names_an_activity(t):
        return True
    if not _has_novel_subject(t):
        return False
    return bool(ask_filtration and ask_filtration(t))


def _filtration_says_activity(text):
    """One filtration call, used only when the cheap checks were inconclusive. `other` is its honest
    'nothing here', so it is the one answer that does NOT start a search."""
    cat = _categorize(text) or {}
    name = str(cat.get("category") or "").lower().strip()
    return bool(name) and name != "other"

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

The "interest" and any clarifying question MUST come from what THIS conversation is actually about — the topic the user just raised, in their own words. NEVER substitute their profile interests: if you were discussing clouds and they ask to talk to someone about it, the interest is "discuss clouds / weather", NOT their profile's coding or games. Do not offer profile interests as the options in a clarifying question when the conversation is about something else.

If the user clearly wants to talk to or meet SOMEONE about a topic — even a niche knowledge topic (clouds, philosophy, a specific book) that isn't an obvious meetup activity — set "match": true and put "discuss <that exact topic>" into "interest". Don't keep chatting or ask the same thing again. It is perfectly fine if such a niche interest turns out to have few or no matches — that is the honest outcome, and the next agents will handle it.

Known so far (baseline from their profile): __SIG__
You ALREADY KNOW this person — that block is their profile. Never ask for anything already in it: not
their name, not their city, not their languages. If "name" is there, address them by it naturally
instead of asking who they are.

Reply as ONE JSON object only, nothing outside it:
{"reply":"<your natural, helpful message>","signals":{<only fields you newly learned THIS turn; may include "interest">},"match":true|false}

LANGUAGE: write "reply" in the SAME language the user writes in (Russian -> answer in Russian; Spanish -> answer in Spanish; English -> answer in English). Write EVERY word of "reply" in that language's own script — translate or transliterate technical terms, species/type names and examples (in Russian say «кучевые», «слоистые», «перистые облака», never "cumulus"/"stratus" or any Chinese/Japanese characters). Never leave a foreign-script or stray Latin word inside a Russian or Spanish sentence. Every OTHER value — signals, interest, topics, time, area — stays in ENGLISH, because the filtration and matching agents only understand English.

MEMORY: the conversation you are given is the WHOLE history — there is nothing before it. Never refer to things "we already talked about", never say "as I said" or "снова"/"again", and never claim to remember a person or a topic that is not in the text above. If the history starts with [FIRST MESSAGE], this person is talking to you for the very first time: greet them as a new acquaintance. Otherwise you are MID-conversation: do NOT greet again (no "Привет"/"Здравствуйте"), and when the user sends a short follow-up like "подробнее"/"примеры"/"ещё"/"а как", it refers to the CURRENT topic — continue and expand it, never ask what they mean or reset to small talk.'''


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
           "ping-pong": "pingpong", "table tennis": "pingpong", "futbol": "football",
           # SPANISH -> the ranker's English vocabulary. Filtration usually translates first, but a
           # word the user typed themselves reaches norm_topic() raw, and until now every Spanish
           # one resolved to nothing — the ES half of the target audience searched on fragments.
           "fútbol": "football", "pádel": "padel", "tenis": "tennis", "baloncesto": "basketball",
           "básquet": "basketball", "basquet": "basketball", "voleibol": "volleyball",
           "vóley": "volleyball", "balonmano": "handball", "bádminton": "badminton",
           "natación": "swimming", "natacion": "swimming", "ciclismo": "cycling",
           "senderismo": "hiking", "escalada": "climbing", "boxeo": "boxing", "ajedrez": "chess",
           "gimnasio": "gym", "esquí": "skiing", "esqui": "skiing", "pesca": "fishing",
           "café": "coffee", "cerveza": "beer", "vino": "wine", "cocina": "cooking",
           "cena": "dinner", "almuerzo": "lunch", "restaurante": "restaurant",
           "cine": "cinema", "película": "cinema", "pelicula": "cinema", "música": "music",
           "musica": "music", "concierto": "concert", "conciertos": "concert", "fiesta": "party",
           "libros": "books", "lectura": "reading", "fotografía": "photography",
           "fotografia": "photography", "museo": "museum", "teatro": "theatre", "arte": "art",
           "viajes": "travel", "montaña": "mountains", "montana": "mountains",
           "videojuegos": "gaming", "cartas": "cards", "póker": "poker",
           "idiomas": "languages", "español": "spanish", "espanol": "spanish", "inglés": "english",
           "ingles": "english", "negocios": "business", "emprendedor": "entrepreneur",
           "programación": "programming", "programacion": "programming", "diseño": "design",
           "caminar": "walking", "paseo": "stroll", "camping": "camping", "surf": "surfing"}

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
                  "разговор", "разговоры", "беседа", "общение", "conversation", "conversations",
                  "discussion", "conversación", "conversacion", "charla", "tertulia",
                  # verbs describing HOW, not WHAT — filtration emits them alongside the real topic
                  "play", "playing", "talk", "talking", "discussing", "drinking", "eating",
                  "watching", "hanging", "hang", "hangout", "chill", "joining", "learning",
                  "practising", "practicing", "practice", "practise",
                  # English filler verbs, the counterpart of _is_verbish for Russian: filtration
                  # answers "grab a beer" with a `grab` topic, which the ranker then tries to match
                  # people on.
                  "grab", "grabbing", "get", "getting", "take", "taking", "catch", "catching",
                  "do", "doing", "make", "making", "go", "going", "visit", "visiting",
                  # answers to «вдвоём или компанией?» belong in `format`, not in what we search on —
                  # they leaked into topics as soon as the agent started asking about format
                  "small", "group", "groups", "big", "large", "duo", "pair", "solo", "alone",
                  "together", "вдвоём", "вдвоем", "компанией", "группой",
                  # WHEN, not WHAT. Filtration answers «в субботу» with a "saturday" topic, and it
                  # rode into the search and onto the card as if the person's interest were Saturday.
                  # The day belongs in `time`, which build_intent fills separately.
                  "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
                  "weekend", "weekday", "morning", "afternoon", "evening", "night", "today",
                  "tomorrow", "tonight",
                  "lunes", "martes", "miércoles", "miercoles", "jueves", "viernes", "sábado",
                  "sabado", "domingo", "mañana", "manana", "tarde", "noche",
                  "понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"}
_RU_END = ("ами", "ями", "ах", "ях", "ов", "ев", "ом", "ем", "ой", "ей", "ую", "ые", "ый", "ая", "ое",
           "у", "а", "я", "и", "ы", "е", "ю", "ь", "й", "о")
_CYR = re.compile(r"[а-яё]", re.I)
# Non-target scripts never belong in a RU/EN/ES reply — the 70B leaks them for technical terms
# ("积云" for cumulus, "биζнес" with a Greek zeta). Any CJK/Hangul/Greek glyph is an artifact, so
# _lang_ok rejects it (triggers a re-roll).
_FOREIGN = re.compile(r"[぀-ヿ㐀-鿿가-힯Ͱ-Ͽἀ-῿]")


# Spanish shares the Latin alphabet with English, so a Cyrillic-vs-not test read every Spanish request
# as English (the P0 bug: an ES/EN audience got English replies to Spanish). Detect Spanish by its
# distinctive glyphs (ñ ¿ ¡ accents) or a common Spanish function/verb word; only then fall to English.
_ES_CHARS = re.compile(r"[ñ¿¡áéíóúü]", re.I)
_ES_WORDS = re.compile(
    r"\b(?:que|con|para|por|una|quiero|quieres|busco|buscas|hola|gente|alguien|alguno|alguna|"
    r"quedar|salir|español|espanol|mañana|manana|fútbol|futbol|café|cafe|práctica|practica|practicar|"
    r"cita|pareja|noche|fiesta|película|pelicula|idiomas|idioma|nativo|nativa|tranquilo|tranquila|"
    r"vamos|hacer|tengo|estoy|está|estás|también|tambien|gustaría|gustaria|jugar|contigo|conmigo)\b",
    re.I)


def detect_lang(text):
    """Which language we REPLY in. Machine-facing fields stay English regardless."""
    t = str(text or "")
    if _CYR.search(t):
        return "ru"
    if _ES_CHARS.search(t) or _ES_WORDS.search(t):
        return "es"
    return "en"


def thread_lang(messages, last_user=None):
    """Which language to reply in, decided over the thread instead of the last word alone.

    A follow-up is usually one ambiguous token — «ejemplos», "more", «ещё». detect_lang() reads
    "ejemplos" as English (Latin script, not in the Spanish word list), so a Spanish conversation
    answered its own follow-up in English. Cyrillic and the Spanish markers are decisive on their
    own; a short Latin-only turn is not, and inherits the language of the last decisive user turn.
    """
    t = str(last_user if last_user is not None else "")
    if not t:
        t = next((str(m.get("content", "")) for m in reversed(messages or [])
                  if m.get("role") == "user"), "")
    lang = detect_lang(t)
    if lang != "en" or len(re.findall(r"[^\W\d_]+", t, re.UNICODE)) >= 4:
        return lang                      # decisive: ru/es markers, or long enough to trust as English
    for m in reversed(messages or []):
        if m.get("role") != "user":
            continue
        prev = detect_lang(str(m.get("content", "")))
        if prev != "en":
            return prev
    return "en"


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
    """Filtration's topics -> the ranker's vocabulary. Multi-word topics are tried WHOLE first.

    Splitting first made every multi-word alias dead code and, worse, turned a phrase into a
    different concept: filtration reads «настольный теннис» correctly as "table tennis", the split
    threw away "table", and the search ran on `tennis` — a different sport, and one _EN_SYN already
    had the right answer for ("table tennis" -> pingpong).
    """
    out = []
    for t in topics or []:
        whole = norm_topic(str(t).lower().strip())
        if whole:
            if whole not in out:
                out.append(whole)
            continue
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
             "утро", "вечер", "ночью", "днём", "днем", "выходные", "выходных", "неделе",
             # Russian pronouns that survive as 4+ letter fragments: «кого-то» tokenises to "кого",
             # which then rode into the topics of a Go search as if it were the subject.
             "кого", "кому", "кем-то", "чего", "чем-то", "чтобы", "нибудь", "какой", "какие", "кто-то",
             # SPANISH — the audience this product is aimed at, and entirely unstopped until now:
             # «quiero quedar para un café» searched on ["coffee", "quiero", "quedar"] and showed
             # the user a card tagged «quiero».
             "quiero", "queria", "quería", "quedar", "quedamos", "busco", "buscar", "buscando",
             "alguien", "alguno", "alguna", "gente", "personas", "persona", "conocer", "hablar",
             "charlar", "tomar", "hacer", "salir", "para", "con", "una", "unos", "unas", "algo",
             "sobre", "tengo", "ganas", "quisiera", "podemos", "puedo", "estoy", "estar", "encontrar",
             "mañana", "manana", "hoy", "noche", "tarde", "fin", "semana", "finde",
             # Spanish infinitives are listed, not detected by ending: -ar/-er/-ir would also swallow
             # «billar», "poker", "beer" and "theater", which are exactly the subjects we carry.
             "jugar", "comer", "beber", "correr", "bailar", "cantar", "aprender", "practicar",
             "entrenar", "pasear", "cocinar", "viajar", "escuchar", "compartir", "disfrutar",
             "conversar", "quedarme", "apetece", "gustaria", "gustaría",
             # Russian fillers that are neither verb nor subject — «лучше» rode into a basketball
             # search as a topic.
             "лучше", "больше", "меньше", "очень", "просто", "немного", "может", "можно",
             "давай", "давайте", "нужно", "надо", "чуть", "если", "либо"}


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


# Fire-and-forget teaching either works or it does not, and for weeks it did not: /api/agent/learn
# was 404 after the matching rewrite and the only evidence was a traceback in this service's log,
# which nobody reads. Count the outcomes so /health can say it out loud.
TEACH_STATS = {"sent": 0, "failed": 0, "last_error": None}


def _teach(cat):
    """Hand filtration's verdict to matching so BOTH sides of a future search can resolve the word.
    Fire-and-forget on purpose: teaching is an optimisation, and a slow or dead matcher must never
    delay the answer the user is waiting for.

    The guard has to be INSIDE the thread. It used to wrap only the .start() call, so a failing
    POST raised on the new thread — outside the try — and printed a full traceback per turn while
    the request itself looked fine. Silent-but-counted beats loud-and-ignored."""
    try:
        cname = str((cat or {}).get("category") or "").lower().strip()
        if not cname or cname == "other":
            return
        sub = str((cat or {}).get("subcategory") or "").lower().strip()
        items = [{"word": str(t).lower(), "category": cname, "subcategory": sub}
                 for t in ((cat or {}).get("topics") or []) if str(t).strip()][:4]
        if not items:
            return

        def _send():
            try:
                _post(MATCH_URL, "/api/agent/learn", {"items": items}, timeout=10)
                TEACH_STATS["sent"] += 1
            except Exception as e:
                TEACH_STATS["failed"] += 1
                TEACH_STATS["last_error"] = "%s: %s" % (type(e).__name__, str(e)[:120])

        threading.Thread(target=_send, daemon=True).start()
    except Exception:
        pass


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

# «хочу поиграть в падел завтра в 19:00» came back with "19:00" as a TOPIC, so the ranker went
# looking for people whose interest is a clock reading. WHEN belongs in `time`, filled separately.
_TIMEISH = re.compile(r"^\s*\d{1,2}\s*[:.\-]?\s*\d{0,2}\s*(ч|h|am|pm)?\s*$", re.I)


def _title_for(topics, tags, typ, lang, role="meet"):
    """Card title. Prefers whichever word we can actually SAY in the user's language.

    It used to title off `tags or topics`, and filtration's tags are synonym bags in arbitrary order —
    'хочу поиграть в футбол' came back tagged ['soccer','football',...], so the Russian card read
    "Soccer — встреча". _TOPIC_RU knows 'football' but not 'soccer'. Scan every candidate for one that
    translates before falling back, so an untranslated synonym can never win over a translatable topic.
    """
    if typ == "dating":
        return _L(lang, "Свидание", "Date", "Cita")
    cands = [str(t) for t in list(topics or []) + list(tags or []) if str(t).strip()]
    # A generic word must never win the title. Tags carried «разговоры» alongside `hertz`, and the
    # Russian-preference scan below happily picked it: "разговоры — разговор".
    named = [c for c in cands if c.strip().lower() not in _GENERIC_TOPIC
             and c.strip().lower() not in _NO_ACTIVITY and not _TIMEISH.match(c)]
    if cands and not named:
        # Nothing but generic words — «разговоры» and nothing else. Naming it twice
        # ("разговоры — разговор") is worse than naming it once.
        return {"discuss": _L(lang, "Разговор", "A chat", "Charla")}.get(
            str(role or "").lower(), _L(lang, "Встреча", "Meet someone", "Quedada"))
    cands = named
    if not cands:
        return _L(lang, "Встреча", "Meet someone", "Quedada")
    # The suffix should name what will actually happen. Someone who asked to TALK about hertz was
    # given "Hertz — встреча"; "встреча" is right for padel, wrong for a conversation.
    suffix = {"discuss": _L(lang, " — разговор", " chat", " — charla"),
              "watch": _L(lang, " — просмотр", " watch", " — sesión"),
              "practise": _L(lang, " — практика", " practice", " — práctica")}.get(
        str(role or "").lower(), _L(lang, " — встреча", " meetup", " — quedada"))
    if lang == "ru":
        # `topics` is ordered and canonical, so position 0 IS the subject — translate it, or show it
        # as it is. Scanning past it for a word that merely happens to be translatable turned
        # ['hertz','frequency','music'] into «Музыка — разговор», which is not what was discussed.
        prim = [str(t) for t in (topics or []) if str(t).strip()
                and str(t).strip().lower() not in _GENERIC_TOPIC
                and str(t).strip().lower() not in _NO_ACTIVITY]
        if prim:
            first = prim[0]
            word = _TOPIC_RU.get(first.strip().lower())
            if word:
                return word + suffix
            if any('а' <= ch <= 'я' for ch in first.lower()):
                return first[:1].upper() + first[1:] + suffix
            # Untranslatable and Latin — but filtration usually also returned the person's OWN word
            # among the tags («chlamydia» next to «хламидиоз»). Show them their word, not ours.
            for c in cands:
                if any('а' <= ch <= 'я' for ch in c.lower()):
                    return c[:1].upper() + c[1:] + suffix
            return first.capitalize() + suffix
        # No engine topics — we are in the tag bag, whose order IS arbitrary («хочу поиграть в
        # футбол» came back tagged ['soccer','football',...]), so there a scan is the right move.
        for c in cands:
            word = _TOPIC_RU.get(c.strip().lower())
            if word:
                return word + suffix
        for c in cands:
            if any('а' <= ch <= 'я' for ch in c.lower()):
                return c[:1].upper() + c[1:] + suffix
    return cands[0].capitalize() + suffix


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
    # _NO_ACTIVITY joins the filter here: «ищу напарника в зал» produced [gym, workout, fitness,
    # partner], and `partner` names WHO you want, not what you would do — the ranker can only match
    # noise on it. Still weak-not-blanket: if such a word is ALL the person gave, it survives below.
    _strong = [t for t in topics if t not in _GENERIC_TOPIC and t not in _NO_ACTIVITY
               and not _TIMEISH.match(str(t))]
    topics = _strong or topics
    from_request = bool(topics)
    # An `or` chain used to end here, and that is how the SUBJECT of a request got thrown away: the
    # moment the taxonomy resolved a single word, every other word of the request was discarded.
    # «Обсудить облигации, плавая в бассейне» resolved "плавание" -> ["swimming"] and searched for
    # swimmers, while "облигации" survived only as a display tag. Matching does literal-word overlap
    # too (_wshare), so an unresolvable word is still worth carrying — union, not fallback.
    if topics:
        # Accented letters are LETTERS, not separators. Without them «sábado» tokenised to "bado"
        # and «fútbol» to "tbol" — fragments that match no candidate and reach the card as tags.
        raw = [w[:24] for w in re.findall(r"[a-zа-яёáéíóúüñç0-9]{4,}",
                                          str(sig.get("interest") or last_user or "").lower())
               # both lists, or the third path leaks what the other two now stop: «один или с
               # компанией?» put "company" into the topics of a cinema search.
               if w not in _RAW_STOP and w not in _GENERIC_TOPIC and not _is_verbish(w)
               and norm_topic(w) not in topics]
        # A "discuss" request is ABOUT something; the activity is the setting. Put the subject first
        # so the ranker weighs what the person actually wants to talk about.
        wants_talk = any(w in str(last_user or "").lower()
                         for w in ("обсуд", "поговор", "разговор", "потрещ", "discuss", "talk about", "chat about"))
        # Filtration's own leftovers come FIRST, because they are already English — the only thing
        # the ranker's taxonomy and the candidate pool speak. The raw surface words below exist to
        # carry a subject the taxonomy has no word for ("labubu"), and that job does not require
        # Russian or Spanish grammar: «настольный», «искусственный» and "quiero" all reached the
        # engine — and the user's card tags — through this branch, where they can never match
        # anything. So a non-Latin word is used only if nothing English survived at all.
        # Same filter as _strong above, or the word comes straight back in through the side door:
        # `partner` was dropped from the primary topics and re-admitted here, so «ищу напарника в
        # зал» ranked on it anyway — and the result flapped between 0 and 4 people run to run.
        spare = [str(t).lower()[:24] for t in (cat.get("topics") or [])
                 if str(t).strip() and str(t).strip().lower() not in _GENERIC_TOPIC
                 and str(t).strip().lower() not in _NO_ACTIVITY
                 and not _TIMEISH.match(str(t))]
        _pool, _seen = [], set(topics)
        for w in spare + raw:
            if w and w not in _seen:
                _seen.add(w)
                _pool.append(w)
        _eng = [w for w in _pool if not _CYR.search(w)]
        extra = (_eng or _pool)[:2]
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
        topics = [w[:24] for w in re.findall(r"[a-zа-яёáéíóúüñç0-9]{4,}", str(sig.get("interest") or last_user).lower())
                  if w not in _RAW_STOP][:3]
        from_request = from_request or bool(topics)      # raw words of the request itself
    if not topics:                                    # last resort: nearest taxonomy word for the category
        topics = CATEGORY_BRIDGE.get(str(cat.get("category") or ""), [])
    # Drop whatever the person ruled out, and remember it as a deal-breaker rather than losing it.
    _neg = negated_terms(last_user)
    if _neg:
        topics = [t for t in topics if str(t).lower() not in _neg]
        _db = [d for d in (sig.get("dealBreakers") or []) if d]
        for w in sorted(_neg):
            if w not in _db:
                _db.append(w)
        sig["dealBreakers"] = _db[:8]
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
    place = str(sig.get("area") or (_L(lang, "Онлайн", "Online", "En línea") if mode == "online" else
                                    _L(lang, "Публичные места рядом", "Public places nearby", "Lugares públicos cercanos")))[:60]
    title = _title_for(topics, tags, typ, lang, role)
    return {
        # ---- machine-facing: matching-service reads exactly these ----
        "title": title, "type": typ, "topics": topics or ["social"], "role": role, "mode": mode,
        "category": cat.get("category"), "subcategory": cat.get("subcategory") or "",
        "time": sig.get("time") or _L(lang, "Гибко", "Flexible", "Flexible"),
        "place": place, "format": _L(lang, "1:1 или небольшая группа", "1:1 or small group", "1:1 o grupo pequeño"),
        "radiusKm": 15, "verifiedOnly": bool(dating), "minAge": (18 if dating else None), "maxAge": None,
        "requiredLanguages": req_langs, "exactMatchRequired": False,
        "adjacentAllowed": True, "broadAllowed": True,
        # ---- card-facing: what the intent card in the UI shows ----
        "activity": title, "tags": tags or ["social"], "area": place,
        "safety": _L(lang, "Только публичные места", "Public places only", "Solo lugares públicos"),
        "visibility": _L(lang, "Только через Kleal", "Via Kleal only", "Solo a través de Kleal"),
        "fallback": _L(lang, "Онлайн, если не сложится", "Online if it falls through", "En línea si no cuaja"),
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
    # A score of 0 is not a weak match, it is no evidence at all. When the pool has nobody for the
    # ask, matching still returns filler at score 0 and the cards presented them as real people —
    # measured on "find someone into speedcubing": four scored-0 strangers, shown without a hint
    # that nothing was found. Dropping them here empties `top` too, so the honest "nobody yet"
    # reply downstream takes over. A missing score is left alone; only an explicit <=0 is filler.
    cands = [c for c in cands if not (isinstance(c.get("score"), (int, float)) and c["score"] <= 0)]
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
    if res.get("broadened"):
        block["broadened"] = True
    if res.get("fallback"):
        block["fallback"] = res.get("fallback")   # honest note is attached whenever the exact search was empty
    return block, [_shape(c, lang) for c in cands[:4]]


# ======================= CONVERSATION =======================
# Every one of these is indexed as dict[lang], and lang can be "es" since detect_lang() learned
# Spanish. Without the "es" rows a Spanish search raised KeyError('es') INSIDE the result-rendering
# path — the request reached matching, found people, and then died on the way to the screen, so the
# user got "I glitched for a second". Measured: the whole search path was unreachable in Spanish.
_FALLBACK_REPLY = {
    "ru": ("Сейчас поищу кого-нибудь.", "Расскажи чуть больше — чем занимаешься и с кем хотел бы встретиться?"),
    "en": ("Let me find someone for you.", "Tell me a bit more about what you're into and who you'd like to meet."),
    "es": ("Voy a buscar a alguien para ti.", "Cuéntame un poco más — qué te gusta hacer y con quién te gustaría quedar."),
}
# Reply framing MUST match the match strength (spec §9.7: show the honest qualitative level, never
# oversell). Only an especially_close/strong_option candidate is pitched as a confident match; a
# broader/needs-clarification result is offered as exactly that, so buddy never claims "you'll click
# with X" about someone the ranker flagged as weak or not-yet-reachable.
_CLICK = {"ru": "Думаю, вы сойдётесь с %s — %s.", "en": "I think you'd click with %s — %s.",
          "es": "Creo que conectarías con %s — %s."}
_BROADER = {"ru": "Идеального совпадения нет, но есть вариант пошире — %s (%s). Посмотришь?",
            "en": "No perfect match, but here's a broader option — %s (%s). Want a look?",
            "es": "No hay una coincidencia perfecta, pero sí una opción más amplia — %s (%s). ¿Le echas un vistazo?"}
_BROADENED = {"ru": "Точного совпадения по этому рядом нет — но вот кто занимается близкими активностями: %s. Посмотришь?",
              "en": "No exact match for this nearby — but here are people doing related activities: %s. Want a look?",
              "es": "No hay coincidencia exacta cerca — pero aquí tienes gente con actividades parecidas: %s. ¿Le echas un vistazo?"}
_NEEDCLAR = {"ru": "Кое-кто есть, например %s, но по деталям стоит уточнить — расскажешь чуть больше (время, район)?",
             "en": "There are a few, like %s, but the details need firming up — tell me a bit more (time, area)?",
             "es": "Hay algunas personas, como %s, pero faltan detalles — ¿me cuentas un poco más (hora, zona)?"}
# search asked for, but no concrete activity given ("найди мне кого-нибудь") -> ask, don't dump people
_ASK_ACTIVITY = {"ru": "С радостью найду — а чем хочешь заняться? Кофе, спорт, игра, прогулка?",
                 "en": "Happy to find someone — what would you like to do? Coffee, sport, a game, a walk?",
                 "es": "Encantado de buscar — ¿qué te apetece hacer? ¿Un café, deporte, una partida, un paseo?"}
_NO_ONE = {"ru": "Пока никто не подходит — расширим поиск или попробуем онлайн?",
           "en": "No one perfect right now — want to go broader or try online?",
           "es": "Ahora mismo no encaja nadie — ¿ampliamos la búsqueda o probamos en línea?"}
_FILED = {"ru": "Отнёс это к «%s», но пока никого нет — расширим поиск или попробуем онлайн?",
          "en": "I filed that under “%s” but found no one perfect right now — go broader or try online?",
          "es": "Lo he clasificado como «%s», pero ahora mismo no hay nadie — ¿ampliamos la búsqueda o probamos en línea?"}
_NEW = {"ru": "Отнёс это к «%s» — для Kleal это новая тема, вокруг неё пока никого. Поискать что-то смежное?",
        "en": "I filed that under “%s” — it's new for Kleal and nobody is around it yet. Try something adjacent?",
        "es": "Lo he clasificado como «%s» — es un tema nuevo para Kleal y aún no hay nadie alrededor. ¿Probamos algo parecido?"}
_GLITCH = {"ru": "Что-то я подвис — повтори, пожалуйста?", "en": "I glitched for a second — say that again?",
           "es": "Me he colgado un momento — ¿me lo repites?"}


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
    lang = thread_lang(messages, last_user)
    # The age gate lived ONLY in intent_build(), i.e. on the composer path — /chat, which is the
    # path the app's buddy actually uses, had none. A sweep of «мне 15 лет, хочу найти друзей»
    # got "Хорошо, давай начнём поиск" back. The model is never asked; this is deterministic and
    # scans the whole transcript, so it cannot be talked around in a later turn.
    if stated_minor(messages) is not None:
        return {"reply": MINOR_REPLY.get(lang, MINOR_REPLY["en"]), "signals": sig, "lang": lang,
                "match": None, "intent": None, "matches": [], "tool_call": None, "category": None}
    if harmful_use_of_a_person(messages):
        return {"reply": HARM_REPLY.get(lang, HARM_REPLY["en"]), "signals": sig, "lang": lang,
                "match": None, "intent": None, "matches": [], "tool_call": None, "category": None}
    # Two attempts: the language directive still slips occasionally (a stray foreign glyph in a technical
    # word — "积云"/"биζнес"). Re-roll once, colder, and prefer the language-clean answer; keep the first
    # usable one as a fallback so a fussy guard never leaves the user with no reply.
    _cmsgs = [{"role": "system", "content": _buddy_sys(sig, lang)},
              {"role": "user", "content": convo}]
    obj = None
    for _attempt in range(2):
        try:
            raw = llm_complete(MODEL_ID, _cmsgs, 0.35 if _attempt == 0 else 0.2)
            cand = _lenient_json(raw)
        except Exception:
            cand = None
        if not isinstance(cand, dict) or not cand.get("reply"):
            continue
        if obj is None:
            obj = cand
        _sal = _salvage(cand.get("reply"), lang)
        if _sal:
            obj = dict(cand, reply=_sal)
            break

    if isinstance(obj, dict) and obj.get("reply"):
        reply = str(obj.get("reply"))[:600]
        sig = _merge_signals(sig, obj.get("signals") or {})
        # The model's flag alone is not enough (it fires on plain chat and misses real asks). Require an
        # explicit ask in the user's words; the flag only tips a soft "with someone" cue over the line.
        want_match = wants_people(last_user, bool(obj.get("match")), _filtration_says_activity)
    else:
        # LLM down: only the strong, explicit ask triggers a search — never a bare activity mention.
        want_match = wants_people(last_user, False)
        reply = _FALLBACK_REPLY.get(lang, _FALLBACK_REPLY["en"])[0 if want_match else 1]

    out = {"reply": reply, "signals": sig, "lang": lang, "match": None,
           "intent": None, "matches": [], "tool_call": None, "category": None}
    if not want_match:
        return out

    # 1) filtration categorises what they want; 2) buddy makes it rankable; 3) matching scores it.
    # Feed filtration the user's OWN words (this turn) ALONGSIDE the model's interest paraphrase, not the
    # paraphrase alone — the paraphrase is where place/game names got mangled ("нью йорке" -> "york",
    # "преферанс" -> "preference", "over the board" -> "over"). Raw first so the real words win when
    # filtration canonicalises; the paraphrase still carries multi-turn context.
    # Same back-reference rule as intent_build: «поговорить об этом» names no subject, the turn it
    # points at does. Without it /chat searched on ["conversation","discussion","talk"].
    _subj = _subject_from_history(messages) if _ANAPHORA.search(str(last_user or "")) else ""
    req_text = " ".join(x for x in (_subj, str(last_user or ""), str(sig.get("interest") or "")) if x).strip() \
        or " ".join(sig.get("topics") or [])
    cat = _categorize(req_text)
    _teach(cat)
    intent = build_intent(sig, cat, last_user, lang)
    # "find me someone" with NO concrete activity -> ask, don't dump a generic social slate (spec §5:
    # a missing high-value slot is a clarification, not a silent default). Bare-social = the only topic
    # is the "social" placeholder AND the user named no recognizable activity word.
    # bare-social = the intent carries only the "social"/"other" placeholder, i.e. the user asked to
    # meet people but named no concrete activity. Ask what they want to do instead of ranking the
    # whole pool on a generic intent and name-dropping a weak "match" (spec §5 clarification).
    topics = [str(t).lower() for t in (intent.get("topics") or [])]
    # The test used to be `all topics are literally "social"/"other"`. Filtration answers «найди мне
    # кого-нибудь» with something richer and perfectly reasonable — [person, find, someone] — so the
    # guard stopped firing and a request that named nothing ranked the whole pool: four strangers
    # presented as matches for nothing in particular, in all three languages. Ask instead whether any
    # topic names a THING TO DO, which is what the guard always meant.
    bare_social = not [t for t in topics
                       if t not in _NO_ACTIVITY and t not in _GENERIC_TOPIC and t not in _FILLER_TOPICS]
    if bare_social:
        out["reply"] = _ASK_ACTIVITY.get(lang, _ASK_ACTIVITY["en"])
        out["tool_call"] = "ask_activity"
        return out
    out["tool_call"] = "find_people"
    out["intent"] = intent
    out["category"] = cat

    if not intent.get("rankable"):
        # Categorised fine, but the ranker has no vocabulary for it yet (e.g. "labubu"). Say so — do not
        # silently return an empty list, and do not match the wrong people just to show a card.
        out["match"] = {"intent": intent, "top": None, "candidates": [], "fallback": None}
        out["reply"] = (reply + "\n\n" + _NEW.get(lang, _NEW["en"]) % (intent.get("category") or "?")).strip()
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
        if block.get("broadened"):
            # Exact search found nobody; these are related-activity people. Say so — never present
            # a broadened result as if it were a match for what was asked.
            names = ", ".join(str(c.get("name")) for c in (block.get("candidates") or [])[:3]) or t.get("name")
            line = _BROADENED.get(lang, _BROADENED["en"]) % names
        elif band in ("especially_close", "strong_option"):
            line = _CLICK.get(lang, _CLICK["en"]) % (t.get("name"), why)          # confident: real fit + reachable
        elif band == "broader_option":
            line = _BROADER.get(lang, _BROADER["en"]) % (t.get("name"), why)        # honest: broader, not perfect
        else:                                                   # needs_clarification / unknown
            line = _NEEDCLAR.get(lang, _NEEDCLAR["en"]) % t.get("name")              # honest: exists, but firm up details
        out["reply"] = (reply + "\n\n" + line).strip()
    else:
        catn = intent.get("category")
        out["reply"] = (reply + "\n\n" + (_FILED.get(lang, _FILED["en"]) % catn if catn else _NO_ONE.get(lang, _NO_ONE["en"]))).strip()
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

WRITE ABOUT THE PERSON, NOT ABOUT THEIR SETTINGS. Never mention safety options, privacy or visibility choices, matching permissions, verification, radius in kilometres or coordinates — they are switches in an app, not traits of a human being, and a paragraph that recites them reads like a form.

LANGUAGE: write the paragraph in __LANGNAME__. This is not optional: __LANGDIR__ The interests may be stored as English keywords for the matching engine — translate them naturally, do not switch language because of them.'''


def resummary(profile, current, lang="ru", personality=""):
    """Rewrite the profile summary to integrate the latest changes (adapt, don't append).

    `personality` is the SEPARATE text the Kleal test owns. It is carried in as substance to weave,
    never as sentences to copy: the two texts have two owners and must not collapse into one."""
    lang = str(lang or "ru").lower()
    if lang not in ("ru", "en", "es"):
        lang = "ru"
    pers = str(personality or "").strip()[:900]
    # Настройки в модель не отдаём вовсе: запрет словами — второй рубеж, а не единственный.
    DROP = ("photo", "summary", "safety", "permissions", "receiving", "verified", "paused",
            "radiusKm", "km", "lat", "lon", "geo", "datingOk", "blocksMe", "source", "id")
    clean = {k: v for k, v in (profile or {}).items() if k not in DROP}
    payload = ("CURRENT SUMMARY:\n" + str(current or "(none yet)") +
               (("\n\nPERSONALITY (the user's own separate text, from the Kleal test — weave, do not copy):\n"
                 + pers) if pers else "") +
               "\n\nUP-TO-DATE PROFILE DATA:\n" + json.dumps(clean, ensure_ascii=False)[:2200])
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
INTENT_BUILD_PROMPT = '''You help the user create an "intent" — a plan to meet people or do an activity with someone. What matters is that the ACTIVITY is specific enough to search on. Timing, place and group size are NOT your job: the app asks for the day, the time of day, the district, the format and how many people on the very next screens.

Conversation so far is given. Return ONE JSON object, nothing else, WITH THE KEYS IN EXACTLY THIS ORDER:
{"valid":true|false, "ready":true|false,
 "reply":"<your message — a single question, or a short confirmation once you have the gist>",
 "activity":"<short activity phrase, once known>", "time":"<when, once known>", "format":"<1:1|small group|group, if the user mentioned it>",
 "hints":["<3 short things THE USER could say next>"]}
The order matters: "valid" must come before "reply".

Rules:
- valid:false when the latest message is NOT a plan to do something with people. That includes gibberish ("asdfgh"), greetings and small talk ("привет", "как дела", "спасибо"), and general questions ("что такое дивиденды", "какая погода") — anything a person could ask a chatbot rather than ask of a meetup. ready MUST then be false. Never build an intent from those.
- valid:true ONLY when the message really is about doing something with another person, even if the details are still missing ("хочу кофе" is valid, "привет" is not).
- NEVER ask about logistics: not when, not what day, not what time, not where, not which district or city, not how far, and NOT how many people (not «вдвоём или компанией», not one-on-one vs group, not the group size). The next screen asks all of that with taps — including the format and the group size — so asking here makes the person answer the same thing twice. If they volunteer a time or a format anyway, record it in "time" / "format" and move on without acknowledging it as a question.
- Ask at most TWO short questions, one per turn, and ONLY to make the request specific enough that a stranger could tell whether it is for them. Useful directions, pick what actually fits:
  * what they want out of it — «хочу выпить кофе» → «о чём хочется поговорить за кофе — про работу, про город, или просто познакомиться?»
  * which side of a broad interest — «футбол» → «поиграть или посмотреть матч?»
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

_LANGNAME = {"ru": "Russian", "en": "English", "es": "Spanish"}
_LANGDIR = {"ru": "every word must be in Russian, in Cyrillic script — translate/transliterate technical "
                  "terms and names («кучевые облака», not \"cumulus\"), and use NO Latin or Chinese/Japanese words.",
            "en": "every word must be in English.",
            "es": "every word must be in Spanish (castellano) — translate technical terms and names, no Russian or CJK words."}


def _L(lang, ru, en, es=None):
    """Pick a user-facing string by reply language; Spanish falls back to English if not given."""
    if lang == "ru":
        return ru
    if lang == "es":
        return es if es is not None else en
    return en


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
    s = str(reply or "")
    if _FOREIGN.search(s):
        return False                          # CJK/Hangul/Greek in any reply is an artifact ("积云", "биζнес")
    if lang != "ru":
        # The MIRROR failure, and the one that matters for an EN/ES audience: the user writes English
        # and the 70B answers in Russian because the profile and the rest of the app around it are
        # Russian ("what is padel" -> "Привет, Иван! Падель - это..."). Unchecked until now, because
        # this branch returned True for everything that was not Russian. A Russian proper noun inside
        # an English sentence is fine; a Russian sentence is not, so compare the two scripts.
        cyr = len(_CYR.findall(s))
        return cyr == 0 or cyr <= len(_LAT_RUN.findall(s))
    if not _CYR.search(s):
        return False
    if _LAT_GLUE.search(s):
        return False
    lat = len(_LAT_RUN.findall(s))
    cyr = len(_CYR.findall(s))
    # Was lat <= cyr, which a genuinely Russian answer could fail just by naming places: a list of
    # Barcelona cafés («Cafè Granja Viader», «Skye Coffee») is half Latin by character count, and
    # rejecting it twice left the user with a canned line instead of the answer. A fully English
    # reply is already caught above (no Cyrillic at all), so this only has to catch the mixed case.
    return lat <= 2 * cyr


def _buddy_sys(sig, lang):
    """BUDDY_PROMPT with the reply language named outright, the way the intent builder already does.

    The prompt's generic "answer in the same language the user writes in" loses to the surrounding
    context: the profile, the app and most of the history are Russian, so an English "what is padel"
    came back as «Привет, Иван! Падель - это...». Rejecting that in _lang_ok only bought a re-roll
    that failed the same way and left the user with a canned line; naming the language fixes the
    cause instead of catching the symptom.
    """
    return (BUDDY_PROMPT.replace("__SIG__", json.dumps(sig))
            + "\n\nTHIS TURN: write \"reply\" in %s — %s Answer in that language whatever language "
              "the profile or the earlier turns happen to be in." % (_LANGNAME.get(lang, "English"),
                                                                     _LANGDIR.get(lang, _LANGDIR["en"])))


_FOREIGN_RUN = re.compile(r"[぀-ヿ㐀-鿿가-힯Ͱ-Ͽἀ-῿]+")
_EMPTY_BRACKETS = re.compile(r"[（(\[]\s*[)）\]]")


def _strip_foreign(reply):
    """Delete the stray non-target-script glyphs instead of throwing the whole answer away.

    The 70B writes perfect Russian and then glosses one technical term in Chinese —
    «кучевые облака (积云)». _lang_ok rejected the reply for those two characters, both attempts
    lost the same way, and the caller fell through to a canned greeting: that is how «а какие
    бывают» in the middle of a conversation about clouds came back as "Привет! Чем могу помочь?".
    The sentence around the gloss is fine, so drop the glyphs and the bracket they sat in.
    """
    s = _FOREIGN_RUN.sub("", str(reply or ""))
    s = _EMPTY_BRACKETS.sub("", s)
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()


def _salvage(reply, lang):
    """The reply if it is usable in `lang` — cleaned of stray glyphs if that is all that was wrong.

    Returns "" only when the answer is genuinely in the wrong language, which is unfixable here and
    still worth a re-roll. Losing a good answer to a two-character artifact is not.
    """
    s = str(reply or "")
    if _lang_ok(s, lang):
        return s
    s2 = _strip_foreign(s)
    return s2 if (s2 and _lang_ok(s2, lang)) else ""


# Filtration answers a bare greeting with topics: "привет" -> ['hello','greeting'],
# "как дела" -> ['hello','greeting','how','are']. Those are conversational filler, not activities —
# treating them as topics kept greetings inside the intent builder and, worse, would let a greeting
# become a searchable intent whose "topics" are hello/greeting.
_FILLER_TOPICS = {"hello", "hi", "greeting", "greetings", "how", "are", "you", "thanks", "thank",
                  "bye", "goodbye", "ok", "okay", "yes", "no", "smalltalk", "small", "talk", "chat"}


# Words that name the PERSON you want, never the thing you want to do. They are legitimate output
# from filtration for a request that named no activity — and completely useless to rank on.
_NO_ACTIVITY = {"person", "people", "someone", "somebody", "anyone", "friend", "friends",
                "new friends", "meet people", "meeting people", "making friends", "new people",
                "find", "finding", "search", "searching", "looking", "company", "companion",
                "buddy", "mate", "partner", "partners", "teammate", "team mate",
                "connection", "connections", "acquaintance",
                "socializing", "socialising", "socialize", "socialise", "social", "other",
                "meet", "meets", "mingle", "hang out", "hangout", "get together",
                # bare "network" arrives from «познакомиться»; the ACTIVITY word is "networking",
                # which the ranker's taxonomy actually resolves — bare "network" it does not, so it
                # could only ever add literal noise.
                "network",
                "gente", "persona", "personas", "alguien", "amigos", "amigo", "conocer",
                "pareja", "compañero", "compañera", "companero", "напарник", "партнёр", "партнер",
                "человек", "люди", "друзья", "знакомство", "компания"}


# A bare request to elaborate points BACK at the previous turn — it can never be an intent of its
# own. Reported twice from the app: «что такое герцы» answered well, then «а подробнее» came back as
# "О чём хочется поговорить за кофе — про кодинг, игры или просто познакомиться?" — the builder
# answering a question nobody asked it. The only thing standing between that and the user was the
# model's own `valid` flag, which is a coin flip on an input this short.
_FOLLOWUP = re.compile(
    r"^\W*(а|и|ну|ok|окей)?\s*(подробн\w*|поподробнее|детальн\w*|ещё|еще|дальше|продолжай|"
    r"примеры|пример|а\s+как|а\s+почему|почему|как\s+так|и\s+что|"
    r"more|tell\s+me\s+more|go\s+on|continue|examples?|why|how\s+so|"
    r"m[aá]s|m[aá]s\s+detalles|detalles|ejemplos?|sigue|contin[uú]a|por\s+qu[eé])\W*$", re.I)


# «поговорить об этом», "talk about this", «sobre esto» — the ask points BACK at the conversation,
# which means the conversation IS the subject. The builder is deliberately blind to small talk, so
# without this it saw only "я хочу с кем-то поговорить об этом" and asked «О чём именно хочется
# поговорить?» — to which the honest answer was «я выше писал».
_ANAPHORA = re.compile(
    r"об\s+этом|про\s+это|на\s+эту\s+тему|об\s+этой\s+теме|"
    # word order is free in Russian: «это обсудить», «обсудить это», «поговорить об этом»
    r"(?:обсуд|поговор|потрещ|пообща|расскаж)\w*\s+(?:об\s+|про\s+|на\s+)?эт\w+|"
    r"\bэт(?:о|ом|у|ой)\s+(?:же\s+)?(?:обсуд|поговор|потрещ|пообща)\w*|"
    r"выше\s+(писал|говорил|сказал)|как\s+я\s+(писал|сказал|говорил)|то\s+же\s+самое|"
    r"about\s+(this|that|it)\b|on\s+this\s+topic|as\s+i\s+(said|wrote)|the\s+same\s+thing|"
    r"(?:discuss|talk|chat|speak)\s+(?:about\s+)?(?:it|this|that)\b|"
    r"(?:hablar|discutir|charlar)\s+(?:de\s+|sobre\s+)?(?:esto|eso)\b|"
    r"sobre\s+(esto|eso|este\s+tema)|de\s+esto|como\s+(dije|he\s+dicho)|lo\s+mismo", re.I)


def _subject_from_history(messages):
    """The last thing the person actually asked ABOUT — the referent of «об этом».

    Walks their OWN turns backwards and skips the ones that carry no subject either: another
    back-reference, or a bare follow-up like «а подробнее». Assistant turns are not used — the
    answer paraphrases, the question names.
    """
    for m in reversed(messages or []):
        if m.get("role") != "user":
            continue
        t = str(m.get("content") or "").strip()
        if not t or _ANAPHORA.search(t) or _FOLLOWUP.match(t):
            continue
        return t[:200]
    return ""


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
            msgs = [{"role": "system", "content": _buddy_sys(sig, lang)},
                    {"role": "user", "content": convo}]
            temp = 0.35 if attempt == 0 else 0.2   # lower: the streamed attempt-0 is what the user sees
            if on_text is not None and attempt == 0:      # only the first try streams — see intent_build
                raw = llm_stream(MODEL_ID, msgs, temp, "reply", on_text)
            else:
                raw = llm_complete(MODEL_ID, msgs, temp)
            obj = _lenient_json(raw)
        except Exception:
            obj = None
        if isinstance(obj, dict) and obj.get("reply"):
            reply = _salvage(str(obj["reply"])[:600], lang)
            if reply:
                return reply
    return ""


# Not "мне 15 минут идти" / "мне 15 лет назад" — a bare number followed by one of these is not an age.
# A unit right after the number means it was never an age: «мне 15 минут идти», «жду 15 сек».
_AGE_NOT_YEARS = re.compile(r"^\s*(мин|час|км|кг|мет|руб|дол|евр|тыс|проц|град|сек|дн|нед|мес|"
                            r"минут|минуты|min|hour|метр|шаг|остан|назад)", re.I)
# «мне» / «я» / «мне уже» — but NOT a word ending in -я (Настя, Катя), which used to make «Настя 16»
# read as a self-declared 16-year-old. Any number of small filler words may sit between the pronoun
# and the number: the old three-word whitelist let «мне щас 15» and «мне вообще-то 15» straight past.
_AGE_RU = re.compile(r"(?:^|[^а-яё])(?:мне|я)\s+(?:[\w-]+[\s,]+){0,3}?(\d{1,2})\s*"
                     r"(лет|год|года|годика|годиков)?\b", re.I)
# Numbers as words, 1..17 — «мне пятнадцать», «мне шестнадцать».
_AGE_WORDS = {"один":1,"одна":1,"два":2,"две":2,"три":3,"четыре":4,"пять":5,"шесть":6,"семь":7,
              "восемь":8,"девять":9,"десять":10,"одиннадцать":11,"двенадцать":12,"тринадцать":13,
              "четырнадцать":14,"пятнадцать":15,"шестнадцать":16,"семнадцать":17}
_AGE_RU_WORDS = re.compile(r"(?:^|[^а-яё])(?:мне|я)\s+(?:[\w-]+[\s,]+){0,3}?(" +
                           "|".join(_AGE_WORDS) + r")\b", re.I)
# English: "i'm 15" is subject-bound; the bare "N years old" needs the unit and a NOT-a-relative
# guard, so «my daughter is 15 years old» and «15 minutes away» stop false-firing.
_AGE_EN = [re.compile(r"\b(?:i'?m|i am|im)\s+(\d{1,2})\b"),
           re.compile(r"\bi(?:'?m| am)?\s+(\d{1,2})\s*(?:years?\s*old|y\.?o\.?)\b")]
_AGE_EN_REL = re.compile(r"\b(daughter|son|kid|child|niece|nephew|brother|sister|friend|cousin)\b", re.I)


# ── Using another person as the means ─────────────────────────────────────────────────────────────
# «Хочу найти кого-то, чтобы обмануть на деньги» came back as a friendly offer to look in financial
# communities. The model reads it as an interest in finance, because that is what the words are
# about; nothing was asking what the OTHER person in the sentence is for.
#
# That is the line this checks, and it is the only one: not a topic list, and not a morality filter.
# Drugs, sex, drinking, gambling and money are all legitimate things to want company for — every one
# of them stays allowed. What is refused is a request whose stated purpose is to defraud, coerce,
# stalk, blackmail or hurt the person being matched. Kleal introduces real people to each other; the
# harm here would be delivered BY the product, to a user, which is why this runs before the model
# and cannot be negotiated in a later turn.
# «развести/развод на деньги» is fraud, but bare «развед/развест» also prefix-matches «разведать»,
# «развести костёр», «развести цветы». So money-fraud must carry its object, and the loose stems go.
_HARM_INTENT = re.compile(
    r"(обман\w*|кинуть\s+на\s+деньг|развест\w*\s+на\s+деньг|развод\w*\s+на\s+деньг|"
    r"выманит\w*|вымогат\w*|шантаж\w*|запугат\w*|угрожат\w*|"
    r"убить|убью|убива\w*|зареза\w*|задуши\w*|застрел\w*|прикончит\w*|"
    r"избит\w*|побит\w*|отпиздит\w*|изнасил\w*|похитит\w*|"
    r"следит\w+\s+за|выследит\w*|преследоват\w*|"
    r"scam|defraud|rip\s+off|con\s+(?:someone|somebody|people)|blackmail|extort|kidnap|"
    r"stalk|harass|beat\s+up|jump\s+(?:someone|somebody)|kill|murder|rape|threaten)", re.I)
# Negation flips it: «не хочу никого обманывать» is a disclaimer, not a plan. Reuse the negation
# machinery so the two features agree on what «не …» means.
# The victim has to be a PERSON, not a game or a system — «обмануть систему», «обыграть бота»,
# «развести костёр» are not this, and «обманул ожидания» is about nobody.
_HARM_TARGET = re.compile(
    r"(кого-то|кого-нибудь|кого\b|人|человек\w*|люд\w+|парн\w+|девуш\w+|мужик\w+|"
    r"жертв\w*|лох\w*|someone|somebody|people|a\s+guy|a\s+girl|victim|him|her|them)", re.I)
_HARM_NOT = re.compile(r"(систем\w*|бота|игр\w+|казино|костёр|костер|ожидани\w*|"
                       r"system|the\s+game|bot|expectations)", re.I)


def _harm_in_text(t):
    t = str(t or "").lower()
    if not _HARM_INTENT.search(t):
        return False
    # The harm verb sits inside a negated clause -> a disclaimer, not a plan. «не хочу никого
    # обманывать», «не буду никого обманывать».
    # The harm verb sits inside a negated clause -> a disclaimer, not a plan. negated_terms() carries
    # the same forward-scoping and clause boundaries the negation feature uses, so «не хочу никого
    # обманывать» and «I don't want to scam anyone» both read as ruling the verb out.
    if any(_HARM_INTENT.search(w) for w in negated_terms(t)):
        return False
    # The user is the VICTIM, not the perpetrator: «меня обманули мошенники», «нас развели»,
    # «scammed me». Past-tense/passive harm with a first-person object is someone seeking support,
    # and refusing them is the cruellest false positive this gate can produce.
    if re.search(r"(меня|мен[яе]|нас)\s+(обману\w+|кину\w+|разве\w+|обокрали|ограбили|избили|"
                 r"шантажир\w*|развод\w+)|(scammed|defrauded|conned|robbed|cheated)\s+(me|us)|"
                 r"(я|мы)\s+жертв\w*|был\w*\s+жертв\w*", t):
        return False
    if _HARM_NOT.search(t) and not _HARM_TARGET.search(t):
        return False                                  # target is a system/game, not a person
    return bool(_HARM_TARGET.search(t) or
                re.search(r"(найти|найд|ищу|подбер|познаком|find|looking\s+for)", t))


def harmful_use_of_a_person(messages):
    """Is the person being searched for the TARGET of harm? Deterministic and before the model.

    Reads the LATEST user message, not the whole transcript. Harm is an INTENT, and a person can
    genuinely drop it — «хочу обмануть» then «ладно, просто хочу кофе» must be answered, not refused
    forever. (Age is different: it is an immutable fact about the person, so that gate still scans
    everything.) The tradeoff — a bad actor could split the plan across turns — is worth taking:
    a determined one can say it all in one message anyway, while the poison version was refusing
    real users for the rest of their conversation.
    """
    last = ""
    for m in (messages or []):
        if m.get("role") == "user":
            last = m.get("content") or ""
    return _harm_in_text(last)


HARM_REPLY = {
    "ru": "Этого я не сделаю. Kleal знакомит людей друг с другом, и я не буду искать человека, "
          "которому по твоим же словам собираются навредить. Если хочешь найти компанию для "
          "чего-то другого — скажи, и поищем.",
    "en": "I won't do that. Kleal introduces real people to each other, and I'm not going to look "
          "for someone you've just described as the target. If you want company for something "
          "else, tell me and we'll look.",
    "es": "Eso no lo voy a hacer. Kleal conecta a personas reales entre sí, y no voy a buscar a "
          "alguien que, según tus propias palabras, sería el objetivo. Si quieres compañía para "
          "otra cosa, dímelo y la buscamos.",
}


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
                continue                              # a unit follows -> not an age
            if t[mt.end():].strip().startswith("назад"):
                continue                              # «15 лет назад»
            n = int(mt.group(1))
            if 1 <= n < 18:
                return n
        for mt in _AGE_RU_WORDS.finditer(t):
            n = _AGE_WORDS.get(mt.group(1).lower())
            if n and 1 <= n < 18:
                return n
        if not _AGE_EN_REL.search(t):                 # «my daughter is 15» is about someone else
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
    "es": "Kleal es para mayores de 18 años, así que no puedo organizar quedadas aquí. "
          "Si ya tienes 18, corrige tu edad en el perfil y lo retomamos.",
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


def _builder_msgs(messages, keep_chat=False):
    """The turns the intent BUILDER may reason about — not the ones the conversation remembers.

    A turn already answered conversationally is context for the chat, not material for a plan:
    greeting Kleal and then asking what dividends are must not compile into an intent about bonds.
    The client marks those turns `chat`. They used to be dropped from the request entirely, which
    is what produced the reported reset — ask a question, then "расскажи детальнее", and the
    follow-up arrived alone, so the buddy greeted the person again and asked what they meant
    (reproduced 4/4). Now they are SENT and stay in the conversation, and only the builder is
    blind to them. The newest user turn is never hidden: it is the one being judged right now.
    """
    msgs = list(messages or [])
    if keep_chat:
        return msgs          # the ask refers back to the conversation, so the conversation is context
    keep = [m for m in msgs if not m.get("chat")]
    if msgs and not keep:
        last_user = next((m for m in reversed(msgs) if m.get("role") == "user"), None)
        keep = [last_user] if last_user is not None else []
    return keep


INTENT_SUGGEST_PROMPT = """You suggest what a person could set up with other people, based on their profile.

Return ONE JSON object and nothing else: {"suggestions":["...","...","..."]}

Rules:
- EXACTLY 3 suggestions, each at most 8 words, written in __LANGNAME__.
- Each is a THING TO DO WITH PEOPLE, phrased as the user's own wish: «Найти компанию на утренний кофе», not «Кофе» and not a question back at them.
- Ground them in the PROFILE line: name their city, their interests, their languages. Three generic openers everyone could get are worthless — that is the whole reason this exists.
- Never mention a day, a time, a district or a distance. The app asks all of that later with taps.
- The three must be genuinely different from each other: not three ways to say «попить кофе»."""


def intent_suggest(profile, lang="en", seed=""):
    """Three things THIS person could propose, from their profile alone.

    Feeds the «Suggestions» / «Regenerate» row on the intent-creation screen, which is shown BEFORE
    the user has said anything — so intent_build cannot serve it: that one needs a message to react
    to. `seed` only varies the sampling so «Regenerate» gives a different three rather than the same
    list again.
    """
    sys_prompt = INTENT_SUGGEST_PROMPT.replace("__LANGNAME__", _LANGNAME.get(lang, "English"))
    line = _profile_line(profile) or "PROFILE: (empty)\n"
    for attempt in range(2):
        try:
            raw = llm_complete(MODEL_ID, [{"role": "system", "content": sys_prompt},
                                          {"role": "user", "content": line + (seed or "")}],
                               0.9 if attempt == 0 else 0.6)
            obj = _lenient_json(raw)
            out = [str(s).strip() for s in (obj or {}).get("suggestions") or [] if str(s).strip()]
            if len(out) >= 3:
                return {"suggestions": out[:3], "lang": lang}
        except Exception:
            pass
    # Молчание лучше выдумки: клиент покажет пустой ряд и оставит человеку поле ввода.
    return {"suggestions": [], "lang": lang}


def intent_build(messages, profile, on_text=None):
    last_user = next((str(m.get("content", "")) for m in reversed(messages or []) if m.get("role") == "user"), "")
    # The whole thread is the conversation's memory; the builder normally sees only the plan-relevant
    # part — unless the ask points back at the chat, in which case the chat is what it is about.
    _refers_back = bool(_ANAPHORA.search(last_user))
    _subject = _subject_from_history(messages) if _refers_back else ""
    bmsgs = _builder_msgs(messages, keep_chat=_refers_back)
    lang = thread_lang(messages, last_user)
    # Before anything else, and before the model: a person who has said they are under 18 gets no
    # intent built, on this turn or any later one. The reply is fixed text, not a generation, so
    # there is nothing to argue with and no way for a later turn to talk it back open.
    if stated_minor(messages) is not None:
        return {"reply": MINOR_REPLY.get(lang, MINOR_REPLY["en"]), "valid": False, "ready": False,
                "intent": None, "lang": lang, "conversational": True, "hints": []}
    if harmful_use_of_a_person(messages):
        return {"reply": HARM_REPLY.get(lang, HARM_REPLY["en"]), "valid": False, "ready": False,
                "rankable": False, "intent": None, "hints": []}
    convo = "\n".join((("User: " + str(m.get("content", ""))) if m.get("role") == "user"
                       else ("Kleal: " + str(m.get("content", "")))) for m in bmsgs[-12:])
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
            temp = 0.35 if attempt == 0 else 0.2
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
        _sal = _salvage(cand.get("reply"), lang)
        if _sal:
            obj = dict(cand, reply=_sal)
            break
    # Both attempts slipped: keep the extracted activity/time/ready (they are English by design and still
    # correct) but do not show the user an English sentence — swap in the neutral prompt in their language.
    if isinstance(obj, dict) and obj.get("reply") and not _lang_ok(obj.get("reply"), lang):
        _sal = _salvage(obj.get("reply"), lang)
        obj = dict(obj, reply=_sal) if _sal else dict(obj, reply=(
            "Понял. Когда тебе удобно?" if obj.get("ready") is not True else "Понял, записал."))
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
    # Counts the turns that were actually building this plan. Chit-chat must not inflate it, or a
    # long conversation would trip the over-asking backstop below and force `ready` on turn one.
    user_turns = sum(1 for m in bmsgs if m.get("role") == "user")
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
    # «поговорить об этом» has no subject of its own; the referent does. Feed both.
    _cat = _categorize((_subject + " " + last_user).strip() if _subject else last_user)
    _teach(_cat)
    _followup = bool(_FOLLOWUP.match(str(last_user or "").strip()))
    nothing_to_build = not ready and (_followup or (_cat is not None and not _real_topics(_cat)))
    if not valid or nothing_to_build:
        # If _chat_reply comes back empty (bad JSON, or the language guard rejected both attempts) we
        # must NOT fall through to the builder — that is what produced "Опишите, что вы хотели бы
        # сделать с кем-то" in response to a greeting. Measured: the fall-through made the typo
        # "привкет" a coin flip, 4 of 8 runs. A plain acknowledgement is always the better answer.
        # This reply is the first and only text that reaches the screen (the gate suppressed the
        # builder's discarded draft), so stream it — it is also the long one worth streaming.
        # This canned line greeted unconditionally, so whenever _chat_reply came back empty it reset a
        # conversation that was already running — «а какие бывают» about clouds answered with
        # "Привет! Чем могу помочь?". Greet only when this genuinely is the first turn.
        _first_turn = sum(1 for m in (messages or []) if m.get("role") == "user") <= 1
        chat = _chat_reply(messages, profile, lang, on_text=on_text) or (
            _L(lang, "Привет! Чем могу помочь?", "Hey! How can I help?",
               "¡Hola! ¿En qué puedo ayudarte?") if _first_turn else
            _L(lang, "Секунду — переспроси, пожалуйста, другими словами.",
               "One sec — could you put that another way?",
               "Un segundo — ¿puedes decirlo de otra forma?"))
        return {"reply": chat, "valid": valid, "ready": False, "intent": None, "lang": lang,
                "conversational": True, "hints": _hints(obj, lang)}
    if not ready:
        return {"reply": reply, "valid": valid, "ready": False, "intent": None, "lang": lang,
                "hints": _hints(obj, lang)}

    # ready -> assemble a canonical, rankable intent (filtration + the same builder /chat uses).
    # Feed filtration the raw last user turn ALONGSIDE the model's `activity` paraphrase, so place/game
    # names survive canonicalisation (нью йорке -> new york, преферанс -> card games) instead of being
    # mangled by the paraphrase — the same fix as /chat's req_text.
    # The person's OWN words go first, the model's paraphrase last. The comment above has claimed
    # this since the «нью йорке -> york» fix, but the code passed the paraphrase first — and that is
    # decisive, not cosmetic: the builder wrote `activity` as "talk about Herz" (German spelling of
    # hertz), and paraphrase-first made filtration read the whole thing as LEARNING GERMAN, so a
    # chat about frequency compiled into «Немецкий — встреча». Raw-first on the same input gives
    # tech/physics. Measured both ways.
    # ВСЕ реплики этого разговора, а не только последняя. Уточняющий вопрос забирал у поиска
    # предмет просьбы: «хочу пойти в бар» → «просто выпить и пообщаться» категоризировалось в
    # [drinks, socializing], и слово «бар» пропадало — человек с интересом «bar» получал T2
    # «близкая тема» вместо точного совпадения. Проверено на стенде: по «drinks» точных нет ни
    # одного, по «bar» их трое. Реплики берём из bmsgs — там уже отобрано то, что относится к
    # плану, так что болтовня сюда не попадает.
    _asked = " ".join(str(m.get("content", "")) for m in bmsgs if m.get("role") == "user")[-600:]
    cat = _categorize(" ".join(x for x in (_subject, _asked, str(activity or "")) if x).strip()
                      or activity)
    _teach(cat)
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
                                         "sessions": len(SESSIONS),
                                         "teach": dict(TEACH_STATS)})
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

            if r == "/intent-suggest":               # три варианта из профиля для экрана создания интента
                return send_json(self, 200, intent_suggest(
                    body.get("profile") if isinstance(body.get("profile"), dict) else {},
                    str(body.get("lang") or "en"),
                    str(body.get("seed") or "")))

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
            send_json(self, 200, {"reply": _GLITCH.get(lang, _GLITCH["en"]), "signals": body.get("signals") or {},
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
    ThreadingHTTPServer((config.BIND_HOST, PORT), H).serve_forever()
