# -*- coding: utf-8 -*-
"""One adapter from a confirmed intent topic to a profile-compatible interest.

The parallel profile-interest work can replace the implementation behind
``normalize_confirmed_interest`` without changing the evidence tracker or API.  This module does
not invent a second taxonomy: it delegates to the canonical 405-node taxonomy first, then to the
existing conservative compound-concept layer, and finally to the seed graph.
"""
from dataclasses import dataclass

from matching_core.taxonomy import canonical, concepts, graph


@dataclass(frozen=True)
class NormalizedInterest:
    canonical_id: str
    profile_key: str
    labels: dict


_CONCEPT_PROFILE_KEYS = {
    "crypto_assets": "crypto",
    "bitcoin_ethereum": "bitcoin",
    "blockchain_web3": "web3",
    "market_trading": "trading",
    "forex_trading": "forex",
    "equity_markets": "stocks",
    "investing": "investing",
    "software_development": "programming",
    "artificial_intelligence": "ai",
    "running": "running",
    "cycling": "cycling",
    "tennis": "tennis",
    "padel": "padel",
    "badminton": "badminton",
    "table_tennis": "pingpong",
    "hiking": "hiking",
    "video_gaming": "gaming",
    "dota": "dota",
    "league_of_legends": "lol",
    "counter_strike": "cs2",
    "valorant": "valorant",
    "tabletop_games": "boardgames",
    "anime_manga": "anime",
    "photography": "photography",
    "language_exchange": "languageexchange",
    "spanish_language": "spanish",
    "english_language": "english",
}


def _labels(node, fallback):
    return {
        "ru": str((node or {}).get("ru") or fallback),
        "en": str((node or {}).get("en") or fallback),
        "es": str((node or {}).get("es") or (node or {}).get("en") or fallback),
    }


def normalize_confirmed_interest(value):
    """Return one stable semantic id and the key written by the confirmed profile flow.

    Unknown or broad-only prose returns ``None``.  Repetition is not enough to turn an
    ungoverned guess into a profile fact.
    """
    text = str(value or "").strip()
    if not text:
        return None

    node_id = canonical.resolve_node(text) if canonical.AVAILABLE else None
    if node_id:
        node = canonical.NODES.get(node_id) or {}
        if node.get("type") != "macro":
            # Prefer an existing seed/profile key when one is known.  For the larger canonical
            # taxonomy the English label remains a valid free-form profile interest.
            seed = graph.norm(text)
            profile_key = seed if graph.resolve(seed) != (None, None) else str(node.get("en") or text).lower()
            return NormalizedInterest("taxonomy:" + node_id, profile_key, _labels(node, profile_key))

    resolved = sorted(concepts.resolve_concepts(text))
    if resolved:
        concept = resolved[0]
        key = _CONCEPT_PROFILE_KEYS.get(concept, concept)
        return NormalizedInterest("concept:" + concept, key, {"ru": key, "en": key, "es": key})

    seed = graph.norm(text)
    broad, sub = graph.resolve(seed)
    if broad and sub:
        return NormalizedInterest("seed:" + seed, seed, {"ru": seed, "en": seed, "es": seed})
    return None
