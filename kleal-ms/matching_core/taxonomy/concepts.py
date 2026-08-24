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
    "tabletop_games": ("tabletop_games", (
        "board games", "tabletop games", "chess", "catan", "настольные игры", "настолки", "шахматы",
        "juegos de mesa", "ajedrez",
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
    "english_language": ("language_learning", (
        "english", "learn english", "practice english", "английский", "учить английский",
        "практиковать английский", "ingles", "aprender ingles", "practicar ingles",
    )),
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
    found = set()
    for concept, (_family, aliases) in _NORMALIZED.items():
        if any(_contains_alias(tokens, alias) for alias in aliases):
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
