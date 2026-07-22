# -*- coding: utf-8 -*-
# Kleal filtration-service — the CATEGORISATION agent. It takes a user's free-text request/intent and
# "magnetises" it to our existing categories, using world knowledge for novel items
# (e.g. "labubu" -> toys_collectibles, "matcha" -> food_drink, "wordle" -> games). It also extracts
# canonical topics and maps the category to a matching `type`, so the matching agent can score cleanly.
#
#   text  ->  filtration (:7076, LLM + taxonomy)  ->  {topics, category, type, role, ...}
#
# Holds NO model keys — reaches the LLM via shared/llm_client. Owner: Dev B (with matching).
import os
import sys
import re

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

# The existing category set the agent magnetises to (extensible).
CATEGORIES = ["sports", "gaming", "esports", "tabletop", "music", "dance", "film_tv", "anime", "comedy",
              "art_culture", "crafts", "writing", "books", "food_drink", "coffee", "nightlife",
              "outdoors", "travel", "gardening", "tech", "design", "startups", "career", "finance",
              "science", "languages", "wellness", "volunteering", "fashion", "toys_collectibles",
              "pets", "photography", "dating", "social", "other"]
# category -> the `type` the matching agent scores on
CAT_TO_TYPE = {"sports": "sport", "gaming": "gaming", "esports": "gaming", "tabletop": "gaming",
               "languages": "language", "tech": "networking", "startups": "networking", "career": "networking",
               "design": "networking", "finance": "networking", "science": "networking", "dating": "dating"}

FILTER_PROMPT = '''You are Kleal's "Filtration" agent. Turn a user's free-text request or interest into a structured, CATEGORISED intent by MAGNETISING it to ONE of our existing categories. Use world knowledge for novel items — e.g. "labubu" -> toys_collectibles, "matcha" -> food_drink, "wordle" -> games, "padel" -> sports, "vinted" -> fashion.

Categories (pick exactly ONE best fit): sports, gaming, esports, tabletop, music, dance, film_tv, anime, comedy, art_culture, crafts, writing, books, food_drink, coffee, nightlife, outdoors, travel, gardening, tech, design, startups, career, finance, science, languages, wellness, volunteering, fashion, toys_collectibles, pets, photography, dating, social, other.

Return ONLY compact JSON, no prose:
{"topics":[1-4 lowercase canonical keywords the user actually meant],
 "category":"<one category from the list>",
 "subcategory":"<short, optional>",
 "type":"sport|gaming|networking|language|dating|social|other",
 "role":"play|watch|discuss|practise|attend|meet",
 "isNew":<true only if nothing in the list really fits>,
 "note":"<=8 words, what this is"}
Map category->type: sports->sport; gaming/esports/tabletop->gaming; languages->language; tech/startups/career/design/finance/science->networking; dating->dating; everything else->social. Infer role from the verb (play/watch/discuss/practise/attend), default "meet". English only.'''

# ---- deterministic fallback (LLM down): small keyword magnet over the same categories ----
_KW = {
    "sports": ["football", "soccer", "basketball", "tennis", "padel", "run", "running", "gym", "boxing", "swim", "cycling", "climb", "rugby", "judo", "karate", "bjj", "kickboxing", "calisthenics", "pickleball", "volleyball", "hockey", "crossfit"],
    "gaming": ["dota", "valorant", "cs", "league", "chess", "boardgame", "poker", "gaming", "game", "wordle", "fortnite", "overwatch", "apex", "minecraft", "roblox", "playstation", "xbox", "nintendo", "catan", "warhammer", "dnd", "pubg"],
    "music": ["music", "guitar", "concert", "dj", "rave", "techno", "gig", "karaoke", "jazz", "rock", "hiphop", "classical", "indie", "piano", "bass", "festival", "vinyl", "band"],
    "dance": ["dance", "dancing", "salsa", "bachata", "tango", "ballroom", "zumba", "swing"],
    "film_tv": ["movie", "cinema", "film", "series", "netflix", "documentary", "sitcom"],
    "anime": ["anime", "manga", "cosplay", "kdrama", "kpop", "weeb"],
    "comedy": ["comedy", "standup", "improv"],
    "art_culture": ["art", "museum", "gallery", "theatre", "exhibition", "architecture", "urbanism", "sculpture", "opera", "ballet"],
    "crafts": ["pottery", "ceramics", "knitting", "crochet", "sewing", "woodworking", "diy", "calligraphy", "craft"],
    "writing": ["writing", "poetry", "journaling", "blogging", "blog"],
    "books": ["book", "books", "reading", "literature", "scifi", "fantasy"],
    "food_drink": ["dinner", "food", "restaurant", "cooking", "matcha", "brunch", "lunch", "baking", "bbq", "vegan", "sushi", "tapas", "pizza", "ramen", "foodie"],
    "coffee": ["coffee", "cafe", "tea", "espresso"],
    "nightlife": ["bar", "drinks", "pub", "party", "club", "cocktails", "beer", "wine"],
    "outdoors": ["hiking", "hike", "camping", "nature", "trek", "fishing", "surfing", "kayaking", "climbing", "paragliding", "birdwatching", "stargazing", "skiing", "snowboard", "paddleboard"],
    "travel": ["travel", "trip", "roadtrip", "vanlife", "backpacking", "hostels", "digitalnomad"],
    "gardening": ["gardening", "garden", "plants", "botany", "foraging"],
    "tech": ["ai", "ml", "coding", "programming", "crypto", "data", "web3", "devops", "cybersecurity", "python", "javascript", "cloud", "llm", "software"],
    "design": ["design", "ux", "ui", "figma", "branding", "typography"],
    "startups": ["startup", "startups", "founder", "product", "entrepreneur"],
    "career": ["networking", "career", "mentorship", "consulting", "freelance", "remote"],
    "finance": ["finance", "investing", "stocks", "trading", "vc", "investor"],
    "science": ["science", "psychology", "astronomy", "biology", "physics", "neuroscience", "economics"],
    "languages": ["spanish", "english", "french", "german", "language", "exchange", "japanese", "korean", "mandarin", "italian", "catalan", "arabic"],
    "wellness": ["yoga", "meditation", "pilates", "wellness", "spa", "sauna", "breathwork", "selfcare", "massage", "mindfulness"],
    "volunteering": ["volunteering", "volunteer", "charity", "community", "activism", "sustainability"],
    "fashion": ["fashion", "thrift", "vinted", "sneakers"],
    "toys_collectibles": ["labubu", "lego", "figures", "collectible", "funko", "toys"],
    "pets": ["dog", "cat", "pet", "puppy", "dogs", "cats"],
    "photography": ["photography", "photo", "camera", "street", "portrait"],
    "dating": ["date", "dating", "romance", "relationship"],
}


def _fallback(text):
    ql = (text or "").lower()
    words = [w for w in re.findall(r"[a-zA-Z]+", ql) if len(w) >= 3]
    cat = "other"
    topics = []
    for c, kws in _KW.items():
        for kw in kws:
            if re.search(r"\b" + re.escape(kw) + r"\b", ql):   # word boundary: 'art' must not match 'st-art-up'
                cat = c
                if kw not in topics:
                    topics.append(kw)
    if not topics:
        topics = words[:3] or ["social"]
    typ = CAT_TO_TYPE.get(cat, "dating" if cat == "dating" else "social")
    role = ("play" if any(w in ql for w in ("play", "match", "squad")) else
            "watch" if "watch" in ql else
            "practise" if any(w in ql for w in ("practise", "practice", "learn")) else
            "discuss" if any(w in ql for w in ("discuss", "talk", "chat")) else "meet")
    return {"topics": topics[:4], "category": cat, "subcategory": "", "type": typ, "role": role,
            "isNew": cat == "other", "note": "keyword fallback"}


def categorize(text):
    text = (text or "").strip()
    if not text:
        return _fallback("")
    try:
        raw = llm_complete(MODEL_ID, [{"role": "system", "content": FILTER_PROMPT},
                                      {"role": "user", "content": text}], 0.1)
        obj = base._extract_json(raw)
    except Exception:
        obj = None
    if isinstance(obj, dict) and obj.get("category"):
        cat = str(obj.get("category")).lower().strip()
        if cat not in CATEGORIES:
            cat = "other"
        topics = [str(t).lower() for t in (obj.get("topics") or []) if str(t).strip()][:4]
        typ = str(obj.get("type") or CAT_TO_TYPE.get(cat, "social")).lower()
        if typ not in ("sport", "gaming", "networking", "language", "dating", "social", "other"):
            typ = CAT_TO_TYPE.get(cat, "social")
        role = str(obj.get("role") or "meet").lower()
        return {"topics": topics or _fallback(text)["topics"], "category": cat,
                "subcategory": str(obj.get("subcategory") or "")[:40], "type": typ, "role": role,
                "isNew": bool(obj.get("isNew")), "note": str(obj.get("note") or "")[:60]}
    return _fallback(text)


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
        body = read_json(self)
        text = body.get("text") or body.get("query") or ""
        try:
            send_json(self, 200, categorize(text))
        except Exception as e:
            send_json(self, 200, dict(_fallback(text), error=str(e)[:200]))

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Kleal filtration-service on http://127.0.0.1:%d  (%d categories, LLM via llm-service)" % (PORT, len(CATEGORIES)))
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
