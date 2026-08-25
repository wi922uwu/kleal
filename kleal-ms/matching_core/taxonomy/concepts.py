# -*- coding: utf-8 -*-
"""Conservative concept canonicalization for free-form interests.

The canonical taxonomy is authoritative for curated activities. This module fills a narrower gap:
compound profile interests and common multilingual aliases that do not have a canonical node yet.
It deliberately exposes only exact concepts and direct families; broad labels such as ``tech``,
``market`` and ``project`` are not aliases because they create unsafe cross-domain matches.
"""
import re
import unicodedata
from functools import lru_cache


_CONCEPTS = {
    # Finance: digital assets and market activity are related, but neither is generic "tech".
    "crypto_assets": ("financial_markets", (
        "crypto", "cryptocurrency", "cryptocurrencies", "крипта", "криптовалюта", "криптовалюты",
        "cripto", "criptomoneda", "criptomonedas",
    )),
    "bitcoin_ethereum": ("financial_markets", (
        "bitcoin", "btc", "ethereum", "биткоин",
    )),
    "blockchain_web3": ("financial_markets", (
        "blockchain", "web3", "defi", "smart contract", "smart contracts",
        "decentralized application", "decentralized applications", "dapp", "dapps",
        "блокчейн", "веб3",
        "смарт контракт", "смарт контракты", "децентрализованные приложения",
        "cadena de bloques", "contrato inteligente",
    )),
    "market_trading": ("financial_markets", (
        "trading", "trader", "трейдинг", "трейдер",
    )),
    "forex_trading": ("financial_markets", (
        "forex", "fx trading", "currency trading", "форекс", "валютный рынок", "comercio de divisas",
    )),
    "equity_markets": ("financial_markets", (
        "nasdaq", "stock trading", "stock market", "stocks", "equities", "financial markets",
        "capital markets", "фондовый рынок", "биржа", "акции", "mercado de valores", "bolsa",
        "acciones", "mercados financieros",
    )),
    "investing": ("financial_markets", (
        "investing", "investment", "finance", "инвестиции", "инвестирование", "финансы",
        "inversion", "inversiones", "finanzas",
    )),

    # Technology concepts stay separate from finance and from games.
    "software_development": ("software_engineering", (
        "software development", "web development", "mobile development", "programming", "coding",
        "backend development", "frontend development", "full stack", "software engineering",
        "разработка программного обеспечения", "веб разработка", "программирование", "разработка по",
        "desarrollo de software", "desarrollo web", "programacion", "ingenieria de software",
    )),
    "artificial_intelligence": ("ai_data", (
        "artificial intelligence", "machine learning", "deep learning", "data science",
        "искусственный интеллект", "машинное обучение", "нейросети",
        "inteligencia artificial", "aprendizaje automatico", "ciencia de datos",
    )),

    # Sport compounds and translations. Families are intentionally narrow.
    "running": ("endurance_sport", (
        "running", "jogging", "trail running", "road running", "бег", "пробежка",
        "бег по пересеченной местности", "correr", "running de trail", "carrera a pie",
    )),
    "cycling": ("endurance_sport", (
        "cycling", "road cycling", "mountain biking", "bike riding", "велоспорт", "велосипед",
        "езда на велосипеде", "ciclismo", "ciclismo de carretera", "bicicleta",
    )),
    "tennis": ("racket_sport", ("tennis", "теннис", "tenis")),
    "padel": ("racket_sport", ("padel", "paddle tennis", "падел")),
    "badminton": ("racket_sport", ("badminton", "бадминтон")),
    "table_tennis": ("racket_sport", (
        "table tennis", "ping pong", "настольный теннис", "tenis de mesa",
    )),
    "hiking": ("outdoor_hiking", (
        "hiking", "trail hiking", "trekking", "mountain hiking", "поход", "походы", "хайкинг",
        "senderismo", "excursion de montana",
    )),

    # Games are not software development. Titles remain within a games-only family.
    "video_gaming": ("video_games", (
        "video games", "video gaming", "gaming", "esports", "competitive gaming", "видеоигры",
        "гейминг", "киберспорт", "videojuegos", "deportes electronicos",
    )),
    "dota": ("video_games", ("dota 2", "dota2", "дота 2")),
    "league_of_legends": ("video_games", ("league of legends",)),
    "counter_strike": ("video_games", ("counter strike", "counter strike 2", "cs2")),
    "valorant": ("video_games", ("valorant", "валорант")),
    # Шахматы — ОТДЕЛЬНОЕ понятие в той же семье, а не синоним настолок. Замер калибровочной
    # батареей: запрос «шахматы» приводил игроков в «Катан» первым ярусом, потому что одно
    # понятие накрывало и то и другое. В каноне I_chess — самостоятельный узел, то есть таблица
    # была ГРУБЕЕ канона и, проверяясь раньше него, стирала различие. Теперь шахматы сходятся с
    # шахматами на 4, с настолками — на 3 по семье.
    "chess": ("tabletop_games", (
        "chess", "шахматы", "ajedrez", "chess club", "шахматный клуб",
    )),
    "tabletop_games": ("tabletop_games", (
        "board games", "tabletop games", "catan", "настольные игры", "настолки",
        "juegos de mesa", "strategy board games", "стратегические настольные игры",
    )),

    # Culture and learning compounds that are common in profiles.
    "anime_manga": ("japanese_screen_culture", (
        "anime", "manga", "japanese animation", "anime discussion", "аниме", "анимешник",
        "анимешники", "манга",
        "японская анимация", "animacion japonesa",
    )),
    "photography": ("visual_media", (
        "photography", "street photography", "portrait photography", "photo walk", "фотография",
        "стрит фотография", "фотопрогулка", "fotografia", "fotografia callejera",
    )),
    "language_exchange": ("language_learning", (
        "language exchange", "conversation exchange", "speaking practice", "language practice",
        "языковой обмен", "разговорная практика", "практика языка",
        "intercambio de idiomas", "intercambio linguistico", "practica de idiomas",
    )),
    "spanish_language": ("language_learning", (
        "spanish", "learn spanish", "practice spanish", "испанский", "учить испанский",
        "практиковать испанский", "espanol", "aprender espanol", "practicar espanol",
    )),
    # Everyday life. The table grew out of finance and crypto complaints and barely covered what the
    # cohort actually writes: `coffee` alone is 90 people, `paseo` 29, and neither resolved anywhere,
    # so they matched only by literal string equality. Families stay narrow on purpose — a broad
    # "drinks" or "outdoors" family would flatter every food or nature query in the domain.
    #
    # DATING FORMS ARE DELIBERATELY ABSENT from coffee: "кофе-свидание" / "cita de café" live in the
    # dating domain and have their own canonical node. Folding them in here would make a person who
    # likes coffee tasting an exact match for someone looking for a date.
    "coffee": ("coffee_culture", (
        "coffee", "кофе", "cafe", "café", "кофейня", "кофейни", "cafeteria",
        "coffee tasting", "specialty coffee", "third wave coffee", "coffee roasting", "home roast",
        "cata de café", "cata de cafe", "дегустация кофе", "спешелти", "обжарка кофе",
        "coffee and conversation", "coffee catch-up", "кофе и разговор", "кофе поболтать",
        "café para charlar", "café y conversación", "coffee talk",
    )),
    "tea": ("tea_culture", (
        "tea", "чай", "té", "te", "tea tasting", "чайная церемония", "дегустация чая",
        "cata de té", "cata de te", "чаепитие",
    )),
    "walking": ("walking_strolling", (
        "walking", "go walking", "walk", "paseo", "paseos", "прогулка", "прогулки", "гулять",
        "погулять", "caminar", "caminata", "dar un paseo", "neighborhood walk",
        "прогулка по району", "paseo por el barrio", "long walk", "долгая прогулка",
    )),
    "reading": ("books_reading", (
        "reading", "books", "book", "чтение", "книги", "читать", "lectura", "libros", "leer",
        "silent reading", "тихое чтение", "reading and research", "book club", "книжный клуб",
        "club de lectura", "fiction", "non-fiction", "novels", "художественная литература",
    )),
    "cinema": ("screen_watching", (
        "cinema", "movie", "movies", "film", "films", "кино", "фильмы", "фильм",
        "cine", "pelicula", "película", "peliculas", "películas",
        "watching movies", "movie night", "киновечер", "noche de cine", "documentary",
        "документалки", "documental",
    )),
    "stand_up_comedy": ("live_comedy", (
        "stand up", "stand-up", "standup", "stand up comedy", "стендап", "стенд-ап",
        "comedy", "комедия", "comedia", "open mic", "открытый микрофон", "micro abierto",
    )),
    "fishing": ("outdoor_fishing", (
        "fishing", "рыбалка", "рыбачить", "pesca", "pescar",
        "sea fishing", "морская рыбалка", "pesca en el mar",
        "ice fishing", "подлёдная рыбалка", "подледная рыбалка",
    )),
    "english_language": ("language_learning", (
        "english", "learn english", "practice english", "английский", "учить английский",
        "практиковать английский", "ingles", "aprender ingles", "practicar ingles",
    )),
}


# ПОНЯТИЕ НЕ ПРИМЕНЯЕТСЯ, если во фразе есть слово из этого списка.
#
# Сопоставление идёт по границам ТОКЕНОВ, а не по фразе целиком: односложный алиас находится
# внутри любого словосочетания, где это слово встречается. Для «bitcoin» или «nasdaq» это
# безобидно, для «кофе» — нет: «кофе-свидание» и «cita de café» содержат его буквально, и
# любитель кофе становился ТОЧНЫМ совпадением для человека, ищущего свидание. Свидания — отдельная
# область со своим согласием и своим гейтом; смешивать её с бытовой не имеет права ни одна таблица.
#
# Список намеренно узкий: он гасит понятие, а не подменяет его другим, и трогает только те слова,
# у которых доказана двойная жизнь.
_BLOCKED_WHEN = {
    "coffee": ("свидание", "свидания", "date", "cita", "dating", "citas"),
    "walking": ("свидание", "свидания", "date", "cita", "dating", "citas"),
}


def normalize_text(value):
    text = unicodedata.normalize("NFKD", str(value or "").strip().lower().replace("ё", "е"))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-zа-я0-9]+", text))


def token_equivalent(actual, expected):
    if actual == expected:
        return True
    # Controlled suffix tolerance, never an arbitrary shared prefix. The old first-five rule made
    # cryptography look like cryptocurrency because both begin with "crypt".
    shorter, longer = sorted((actual, expected), key=len)
    if len(shorter) >= 5 and longer.startswith(shorter) and len(longer) - len(shorter) <= 4:
        return True
    if re.search(r"[а-я]", actual + expected):
        endings = ("ами", "ями", "ого", "ему", "ому", "ыми", "ими", "ах", "ях", "ом", "ем",
                   "ов", "ев", "ы", "и", "а", "я", "у", "ю", "е")
        def stem(token):
            return next((token[:-len(end)] for end in endings
                         if token.endswith(end) and len(token) - len(end) >= 5), token)
        return stem(actual) == stem(expected)
    return False


def _contains_alias(tokens, alias):
    wanted = alias.split()
    if not wanted or len(wanted) > len(tokens):
        return False
    for start in range(len(tokens) - len(wanted) + 1):
        if all(token_equivalent(tokens[start + i], token) for i, token in enumerate(wanted)):
            return True
    return False


_NORMALIZED = {
    concept: (family, tuple(sorted((normalize_text(alias) for alias in aliases), key=len, reverse=True)))
    for concept, (family, aliases) in _CONCEPTS.items()
}


@lru_cache(maxsize=20000)
def _resolve_normalized(text):
    if not text:
        return frozenset()
    tokens = text.split()
    seen = set(tokens)
    found = set()
    for concept, (_family, aliases) in _NORMALIZED.items():
        if not any(_contains_alias(tokens, alias) for alias in aliases):
            continue
        if any(w in seen for w in _BLOCKED_WHEN.get(concept, ())):
            continue                      # слово есть, но фраза не про это — см. _BLOCKED_WHEN
        found.add(concept)
    return frozenset(found)


def resolve_concepts(value):
    """Return deterministic concept ids found on token boundaries, longest aliases first."""
    return set(_resolve_normalized(normalize_text(value)))


def family_of(concept):
    item = _NORMALIZED.get(concept)
    return item[0] if item else None


def similarity(a, b):
    """4 for one concept, 3 for a direct family, otherwise 0."""
    ca, cb = resolve_concepts(a), resolve_concepts(b)
    if not ca or not cb:
        return 0
    if ca & cb:
        return 4
    fa = {family_of(x) for x in ca}
    fb = {family_of(x) for x in cb}
    return 3 if (fa & fb) else 0


def topic_tags(value):
    """Stable tags usable by the learned phrase bridge without exposing generic words."""
    concepts = resolve_concepts(value)
    return {"concept:" + c for c in concepts} | {
        "family:" + family_of(c) for c in concepts if family_of(c)
    }
