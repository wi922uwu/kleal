# -*- coding: utf-8 -*-
# Tests for the filtration agent — pure classification/contract logic (no live LLM).
# Run: python3 test_filtration.py
import os
import sys
import importlib.util

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "..", "..", "shared"), os.path.join(_HERE, "shared")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)
_spec = importlib.util.spec_from_file_location("filt", os.path.join(_HERE, "app.py"))
F = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(F)

_fails = []


def check(name, cond, extra=""):
    print(("  ok  " if cond else "FAIL  ") + name + (("  -> " + extra) if (extra and not cond) else ""))
    if not cond:
        _fails.append(name)


def C(text):
    return F._classify_fallback(text)

# ---- 1. every category maps to a valid type and a domain (contract completeness) ----
for cat in F.CATEGORIES:
    check("type map: %s" % cat, F.CAT_TO_TYPE.get(cat) in F.VALID_TYPES, repr(F.CAT_TO_TYPE.get(cat)))
check("every category has a type", all(c in F.CAT_TO_TYPE for c in F.CATEGORIES))
check("domains are engine-valid", set(F.CAT_TO_DOMAIN.values()) <= {
    "social_meet", "walk", "watch_together", "culture_event", "toys_collectibles", "coworking",
    "professional_networking", "sport_activity", "games", "language_exchange", "dating"})

# ---- 2. card shape + deterministic type/domain ----
card = F._card("gaming", ["dota"], "play", "n")
check("card type from category", card["type"] == "gaming")
check("card domain from category", card["domain"] == "games")
check("card has all keys", set(card) == {"topics", "category", "subcategory", "type", "domain", "role", "isNew", "note"})

# ---- 3. English fallback ----
r = C("i want to play padel")
check("english padel -> sports", r["category"] == "sports", r["category"])
check("english padel -> type sport", r["type"] == "sport")
check("english padel -> domain sport_activity", r["domain"] == "sport_activity")
check("english padel -> role play", r["role"] == "play", r["role"])
check("english padel topic", "padel" in r["topics"], str(r["topics"]))

# ---- 4. CYRILLIC fallback (the whole point of the refactor) ----
r = C("хочу поиграть в футбол")
check("ru football -> sports", r["category"] == "sports", r["category"])
check("ru football -> role play", r["role"] == "play", r["role"])
check("ru football topic cyrillic", "футбол" in r["topics"], str(r["topics"]))

r = C("собираю лабубу")
check("ru labubu -> toys_collectibles", r["category"] == "toys_collectibles", r["category"])
check("ru labubu -> domain", r["domain"] == "toys_collectibles")

r = C("давай учить испанский")
check("ru spanish -> languages", r["category"] == "languages", r["category"])
check("ru spanish -> type language", r["type"] == "language")
check("ru spanish -> role practise", r["role"] == "practise", r["role"])

r = C("хочу выпить кофе и поговорить")
check("ru coffee -> coffee", r["category"] == "coffee", r["category"])
check("ru coffee -> type social", r["type"] == "social")
check("ru coffee -> role discuss", r["role"] == "discuss", r["role"])

# ---- 4b. SPANISH fallback (EN/ES audience) + accented tokeniser ----
check("tokeniser keeps accented word whole", "fútbol" in F._tokens("quiero jugar al fútbol"),
      str(F._tokens("quiero jugar al fútbol")))
r = C("quiero jugar al fútbol")
check("es futbol -> sports", r["category"] == "sports", r["category"])
check("es futbol -> role play (jugar)", r["role"] == "play", r["role"])
check("es futbol topic accented", "fútbol" in r["topics"], str(r["topics"]))

r = C("quedar para un café")
check("es cafe -> coffee", r["category"] == "coffee", r["category"])

r = C("me gusta el senderismo")
check("es senderismo -> outdoors", r["category"] == "outdoors", r["category"])
check("es senderismo -> domain sport_activity", r["domain"] == "sport_activity")

r = C("intercambio de idiomas en español")
check("es idiomas -> languages", r["category"] == "languages", r["category"])
check("es idiomas -> type language", r["type"] == "language")

r = C("busco una cita")
check("es cita -> dating", r["category"] == "dating", r["category"])

r = C("quiero ver una película")
check("es pelicula -> film_tv", r["category"] == "film_tv", r["category"])
check("es pelicula -> role watch (ver)", r["role"] == "watch", r["role"])

r = C("clase de fotografía con cámara")
check("es camara accented -> photography", r["category"] == "photography", r["category"])

# ---- 5. best-match (most hits) beats last-iterated ----
r = C("футбол футбол футбол и немного кофе")
check("best-match picks the dominant category", r["category"] == "sports", r["category"])

# ---- 6. dating wins ties (safety-relevant) ----
r = C("свидание")
check("ru dating -> dating", r["category"] == "dating", r["category"])
check("dating -> type dating", r["type"] == "dating")

# ---- 7. unknown -> other/social_meet, isNew ----
r = C("qwzx zzz")
check("gibberish -> other", r["category"] == "other", r["category"])
check("other -> domain social_meet", r["domain"] == "social_meet")
check("other -> isNew", r["isNew"] is True)

# ---- 8. empty text -> fallback, never crashes ----
r = F.categorize("")
check("empty text -> a valid card", r["category"] in F.CATEGORIES and r["type"] in F.VALID_TYPES)

# ---- 9. _normalize derives type from category, IGNORING a bad LLM type field ----
obj = {"category": "languages", "type": "other", "topics": ["spanish"], "role": "practise"}
n = F._normalize(obj, "learn spanish")
check("normalize forces type from category (ignores llm type:other)", n["type"] == "language", n["type"])
check("normalize sets domain from category", n["domain"] == "language_exchange")

obj = {"category": "definitely_not_a_category", "topics": ["x"]}
n = F._normalize(obj, "x")
check("normalize clamps unknown category -> other", n["category"] == "other")

obj = {"category": "gaming", "topics": [], "role": "zzz"}
n = F._normalize(obj, "хочу поиграть в доту")
check("normalize backfills empty topics from fallback", len(n["topics"]) >= 1, str(n["topics"]))
check("normalize clamps bad role -> meet", n["role"] == "meet")

print()
if _fails:
    print("FAILED %d:" % len(_fails), ", ".join(_fails))
    sys.exit(1)
print("ALL PASS")
