# -*- coding: utf-8 -*-
# Kleal filtration-service — the CATEGORISATION agent. It takes a user's free-text request/intent and
# "magnetises" it to our existing categories, using world knowledge for novel items
# (e.g. "labubu" -> toys_collectibles, "matcha" -> food_drink, "wordle" -> games). It also extracts
# canonical topics and maps the category to a matching `type` (+ advisory `domain`), so the matching
# agent can score cleanly.
#
#   text  ->  filtration (:7076, LLM + keyword magnet)  ->  {topics, category, subcategory, type, domain, role, isNew, note}
#
# Holds NO model keys — reaches the LLM via shared/llm_client. Owner: Dev B (with matching).
#
# Refactor (2026-07-23) — self-contained, matching-service untouched:
#   * LLM call is time-boxed (FILTER_LLM_TIMEOUT) so a slow/hung model degrades to the keyword magnet
#     instead of blocking the request thread.
#   * `type` is derived DETERMINISTICALLY from `category` (CAT_TO_TYPE) — the LLM's own `type` field is
#     no longer trusted, which killed the "LLM returned type:other and overrode the category" drift and
#     guarantees a value the matching engine's _TYPE2DOMAIN can route.
#   * Fallback keyword magnet is now Cyrillic-aware (tokeniser + RU synonyms) so a downed LLM does not
#     silently dump every Russian request into `other`; it also picks the BEST category (most hits),
#     not the last one iterated.
#   * `domain` (advisory) mirrors the matching engine's domain vocabulary so the buddy/adapter can pass
#     it through as identity.domain; matching ignores unknown fields, so emitting it is safe.
#   * Confident LLM results are cached (bounded) — cuts repeat 70B calls and stops the same request
#     flapping between categories across runs. Fallback results are never cached.
import os
import sys
import re
import concurrent.futures

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "..", "..", "shared"), os.path.join(_HERE, "shared")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
import kleal_lib as base                      # base._extract_json (keyless)
from llm_client import llm_complete
from http_util import send_json, read_json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("FILTER_PORT", "7076"))
MODEL_ID = os.environ.get("V2_MODEL", "llama_self")
LLM_TIMEOUT_S = float(os.environ.get("FILTER_LLM_TIMEOUT", "5"))   # hard cap on the model call
CACHE_MAX = int(os.environ.get("FILTER_CACHE_MAX", "512"))

# ------------------------------------------------------------------ vocabulary / contract
# The existing category set the agent magnetises to (extensible).
CATEGORIES = ["sports", "gaming", "esports", "tabletop", "music", "film_tv", "art_culture", "books",
              "food_drink", "coffee", "nightlife", "outdoors", "travel", "tech", "startups", "career",
              "languages", "wellness", "fashion", "toys_collectibles", "pets", "photography",
              "dating", "social", "other"]

# The matching engine's 7 scoring `type`s (kleal_intent.TYPE_ALLOWLIST is a superset that also allows
# dinner/event; those are the matching service's own, not ours to emit).
VALID_TYPES = ("sport", "gaming", "networking", "language", "dating", "social", "other")
VALID_ROLES = ("play", "watch", "discuss", "practise", "attend", "meet")

# category -> the `type` the matching agent scores on. EVERY category maps (default social), so `type`
# is always deterministic and never inherits a stray value from the model.
CAT_TO_TYPE = {
    "sports": "sport", "outdoors": "sport",
    "gaming": "gaming", "esports": "gaming", "tabletop": "gaming",
    "tech": "networking", "startups": "networking", "career": "networking",
    "languages": "language",
    "dating": "dating",
    "other": "other",
    # everything else -> social
    "music": "social", "film_tv": "social", "art_culture": "social", "books": "social",
    "food_drink": "social", "coffee": "social", "nightlife": "social", "travel": "social",
    "wellness": "social", "fashion": "social", "toys_collectibles": "social", "pets": "social",
    "photography": "social", "social": "social",
}

# category -> the matching engine's DOMAIN vocabulary (advisory; mirrors what matching's infer_domain
# would land on, so a buddy/adapter can forward it as identity.domain). Engine domains:
#   social_meet, walk, watch_together, culture_event, toys_collectibles, coworking,
#   professional_networking, sport_activity, games, language_exchange, dating
CAT_TO_DOMAIN = {
    "sports": "sport_activity", "outdoors": "sport_activity",
    "gaming": "games", "esports": "games", "tabletop": "games",
    "tech": "professional_networking", "startups": "professional_networking", "career": "professional_networking",
    "languages": "language_exchange",
    "dating": "dating",
    "toys_collectibles": "toys_collectibles",
    "art_culture": "culture_event", "film_tv": "culture_event", "books": "culture_event",
    "photography": "culture_event", "music": "culture_event",
    # coffee / food_drink / nightlife / wellness / fashion / pets / travel / social / other
}

FILTER_PROMPT = '''You are Kleal's "Filtration" agent. Turn a user's free-text request or interest into a structured, CATEGORISED intent by MAGNETISING it to ONE of our existing categories. Use world knowledge for novel items — e.g. "labubu" -> toys_collectibles, "matcha" -> food_drink, "wordle" -> games, "padel" -> sports, "vinted" -> fashion.

Categories (pick exactly ONE best fit): sports, gaming, esports, tabletop, music, film_tv, art_culture, books, food_drink, coffee, nightlife, outdoors, travel, tech, startups, career, languages, wellness, fashion, toys_collectibles, pets, photography, dating, social, other.

Return ONLY compact JSON, no prose:
{"topics":[1-4 lowercase canonical keywords the user actually meant],
 "category":"<one category from the list>",
 "subcategory":"<short, optional>",
 "role":"play|watch|discuss|practise|attend|meet",
 "isNew":<true only if nothing in the list really fits>,
 "note":"<=8 words, what this is"}
Infer role from the verb (play/watch/discuss/practise/attend), default "meet". Topics in English, lowercase.'''

# ------------------------------------------------------------------ keyword fallback (LLM down)
# Bilingual keyword magnet over the same categories — used when the model is unreachable or times out.
# Cyrillic keys matter: the model prompt asks for English topics, but a DOWN model must still resolve a
# Russian request instead of dumping it into `other`.
_KW = {
    "sports": ["football", "soccer", "basketball", "tennis", "padel", "run", "running", "gym", "boxing",
               "swim", "cycling", "climb",
               "футбол", "баскетбол", "теннис", "падел", "бег", "пробежка", "зал", "бокс", "плавание", "велосипед", "борьба"],
    "gaming": ["dota", "valorant", "cs", "league", "chess", "boardgame", "poker", "gaming", "game", "wordle",
               "дота", "шахматы", "настолки", "покер", "игра", "игры"],
    "music": ["music", "guitar", "concert", "dj", "rave", "techno", "gig", "karaoke",
              "музыка", "гитара", "концерт", "караоке"],
    "film_tv": ["movie", "cinema", "film", "series", "anime",
                "кино", "фильм", "сериал", "аниме"],
    "art_culture": ["art", "museum", "gallery", "theatre", "exhibition", "architecture", "urbanism",
                    "искусство", "музей", "галерея", "театр", "выставка", "архитектура"],
    "books": ["book", "books", "reading", "книги", "книга", "чтение"],
    "food_drink": ["dinner", "food", "restaurant", "cooking", "matcha", "brunch", "lunch",
                   "ужин", "еда", "ресторан", "готовка", "бранч", "обед"],
    "coffee": ["coffee", "cafe", "tea", "кофе", "кафе", "чай"],
    "nightlife": ["bar", "drinks", "pub", "party", "club",
                  "бар", "напитки", "вечеринка", "клуб", "тусовка"],
    "outdoors": ["hiking", "hike", "camping", "nature", "trek", "fishing",
                 "поход", "походы", "природа", "рыбалка", "кемпинг"],
    "travel": ["travel", "trip", "roadtrip", "путешествия", "поездка"],
    "tech": ["ai", "ml", "coding", "programming", "crypto", "data",
             "код", "программирование", "крипта", "данные", "разработка"],
    "startups": ["startup", "startups", "founder", "product", "стартап", "стартапы", "основатель"],
    "career": ["networking", "career", "mentorship", "investing", "нетворкинг", "карьера", "инвестиции"],
    "languages": ["spanish", "english", "french", "german", "language", "exchange",
                  "испанский", "английский", "французский", "немецкий", "язык", "практика"],
    "wellness": ["yoga", "meditation", "pilates", "wellness", "йога", "медитация", "пилатес"],
    "fashion": ["fashion", "thrift", "vinted", "sneakers", "мода", "винтаж", "кроссовки"],
    "toys_collectibles": ["labubu", "lego", "figures", "collectible", "funko", "toys",
                          "лабубу", "лего", "фигурки", "коллекция"],
    "pets": ["dog", "cat", "pet", "puppy", "собака", "кот", "питомец", "щенок"],
    "photography": ["photography", "photo", "camera", "фото", "съёмка", "камера"],
    "dating": ["date", "dating", "romance", "relationship", "свидание", "знакомства", "отношения"],
}

_ROLE_HINTS = (
    ("play", ("play", "match", "squad", "играть", "поиграть", "сыграть")),
    ("watch", ("watch", "смотреть", "посмотреть")),
    ("practise", ("practise", "practice", "learn", "учить", "практика", "практиковать")),
    ("discuss", ("discuss", "talk", "chat", "обсудить", "поговорить", "обсуждать")),
)


def _tokens(ql):
    return [w for w in re.findall(r"[a-zа-яё0-9]+", ql) if len(w) >= 3]


def _role_of(ql):
    for role, hints in _ROLE_HINTS:
        if any(re.search(r"\b" + re.escape(h) + r"\b", ql) for h in hints):
            return role
    return "meet"


def _card(cat, topics, role, note):
    """Assemble a response card with type/domain derived deterministically from the category."""
    return {"topics": topics[:4],
            "category": cat,
            "subcategory": "",
            "type": CAT_TO_TYPE.get(cat, "social"),
            "domain": CAT_TO_DOMAIN.get(cat, "social_meet"),
            "role": role,
            "isNew": cat == "other",
            "note": note}


def _classify_fallback(text):
    ql = (text or "").lower()
    # score categories by how many of their keywords appear; the winner is the most-hit category, and
    # the winner's own hits become the topics (not a blend across every category that grazed a word).
    scores, hits_by_cat = {}, {}
    for c, kws in _KW.items():
        hits = [kw for kw in kws if re.search(r"\b" + re.escape(kw) + r"\b", ql)]
        if hits:
            scores[c] = len(hits)
            hits_by_cat[c] = hits
    if scores:
        cat = max(scores, key=lambda c: (scores[c], c == "dating"))   # dating wins ties (safety-relevant)
        topics = hits_by_cat[cat][:4]
    else:
        cat = "other"
        topics = _tokens(ql)[:3] or ["social"]
    return dict(_card(cat, topics, _role_of(ql), "keyword fallback"))


# ------------------------------------------------------------------ LLM path (time-boxed)
_EXEC = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="filt-llm")


def _classify_llm(text):
    """Call the model with a hard timeout. Returns the parsed dict, or None on timeout/error/garbage."""
    fut = _EXEC.submit(llm_complete, MODEL_ID,
                       [{"role": "system", "content": FILTER_PROMPT},
                        {"role": "user", "content": text}], 0.1)
    try:
        raw = fut.result(timeout=LLM_TIMEOUT_S)
    except Exception:
        return None                       # timeout / model error -> caller falls back
    try:
        obj = base._extract_json(raw)
    except Exception:
        obj = None
    return obj if isinstance(obj, dict) and obj.get("category") else None


def _normalize(obj, text):
    cat = str(obj.get("category") or "").lower().strip()
    if cat not in CATEGORIES:
        cat = "other"
    topics = [str(t).lower().strip() for t in (obj.get("topics") or []) if str(t).strip()][:4]
    if not topics:
        topics = _classify_fallback(text)["topics"]
    role = str(obj.get("role") or "meet").lower()
    if role not in VALID_ROLES:
        role = "meet"
    card = _card(cat, topics, role, str(obj.get("note") or "")[:60])
    card["subcategory"] = str(obj.get("subcategory") or "")[:40]
    card["isNew"] = bool(obj.get("isNew")) or cat == "other"
    return card


# bounded cache of CONFIDENT (LLM-sourced) results only — never caches a degraded fallback.
_CACHE = {}


def categorize(text):
    text = (text or "").strip()
    if not text:
        return _classify_fallback("")
    key = " ".join(text.lower().split())
    cached = _CACHE.get(key)
    if cached is not None:
        return dict(cached)
    obj = _classify_llm(text)
    if obj is None:
        return _classify_fallback(text)   # not cached: degraded result must not stick
    card = _normalize(obj, text)
    _CACHE[key] = card
    if len(_CACHE) > CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    return dict(card)


# ------------------------------------------------------------------ HTTP
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/filter/categories":
            send_json(self, 200, {"categories": CATEGORIES})
        elif self.path == "/":
            send_json(self, 200, {"service": "filtration", "ok": True})
        else:
            send_json(self, 404, {})

    def do_POST(self):
        if self.path != "/api/filter/categorize":
            return send_json(self, 404, {})
        try:
            body = read_json(self) or {}
            text = body.get("text") or body.get("query") or ""
        except Exception:
            text = ""                      # malformed body -> empty text -> deterministic fallback
        try:
            send_json(self, 200, categorize(text))
        except Exception as e:
            send_json(self, 200, dict(_classify_fallback(text), error=str(e)[:200]))

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Kleal filtration-service on http://127.0.0.1:%d  (%d categories, LLM<=%.1fs via llm-service)"
          % (PORT, len(CATEGORIES), LLM_TIMEOUT_S))
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
