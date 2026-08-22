# -*- coding: utf-8 -*-
"""Deterministic load-test user generator for the Kleal matching pilot.

Builds ~1000 diverse synthetic people spanning every Matching Core spec domain (§18), plus the
edge cases the gates/readiness engine must handle (minors, paused, busy, no-policy, overloaded,
sparse profiles, off-taxonomy and Russian-language interests, cross-city geo, own active intents
for T0 reciprocity). Every user carries:
  - source: "loadtest"  -> visible in the admin panel, NEVER on the Explore map (that filter is
    source=="onboarding"), and removable in one line;
  - tags: [recipe tag]  -> the evaluation harness (eval_matching.py) asserts expectations by tag.

Usage:
  python3 tools/gen_test_users.py --n 1000 --seed 42 --out /tmp/pool.json --index /tmp/index.json
  python3 tools/gen_test_users.py --merge users.json ...   # keep existing non-loadtest users

Deterministic: same seed + n -> byte-identical pool. Stdlib only.
"""
import argparse, hashlib, json, os, random, sys

# ---------------------------------------------------------------- name material (unique, human)
FIRST = ("Marc Ana Dima Sofia Leo Nina Tom Yuki Pablo Lena Marta Sam Elena Hugo Kira Noah Vera Max "
         "Lucia Oleg Sara Ben Mira Jon Alba Rus Cleo Ravi Tanya Nico Iris Omar Zoe Karl Maya Erik "
         "Nadia Luca Petra Adam Rosa Timur Gaia Feliks Anya Diego Sana Bruno Yara Igor Olia Pau "
         "Nuria Jordi Aina Sergi Laia Pol Carla Andrei Dasha Kolya Sveta Artem Lera Vlad Alina "
         "Mateo Emma Luis Carmen Aleks Dana Boris Rita Ivo Mila Stas Vika Denis Katya").split()
LAST = ("Garcia Petrov Smirnov Lopez Ivanov Marti Costa Volkov Serra Novak Ortiz Sokolov Vidal "
        "Fedorov Roca Kuznetsov Ferrer Popov Bosch Morozov Pujol Vlasov Camps Egorov Sala Belov "
        "Font Orlov Riera Titov Soler Zaitsev Mas Drozdov Valls Gusev Rius Komarov Pons Frolov").split()

# ---------------------------------------------------------------- geo (Barcelona districts + far)
GEO = {
    "eixample":      (41.391, 2.164), "gracia":   (41.402, 2.156), "poblenou": (41.397, 2.197),
    "born":          (41.385, 2.183), "sants":    (41.375, 2.135), "raval":    (41.379, 2.168),
    "sarria":        (41.399, 2.121), "badalona": (41.450, 2.247), "castelldefels": (41.280, 1.976),
    "madrid":        (40.416, -3.703), "none": None,
}
BCN = [k for k in GEO if k not in ("madrid", "none")]

VIBES = ["calm", "energetic", "intellectual", "creative", "competitive", "chill", "social",
         "introvert", "extrovert", None]
ALL_DOMAINS = ["social_meet", "walk", "culture_event", "language_exchange", "coworking",
               "watch_together", "games", "sport_activity", "professional_networking"]

# receiving-policy modes the generator can stamp (spec §4.4 / §10.1)
def _recv(mode, domains=None):
    base = {"status": "active", "allowed_domains": domains or list(ALL_DOMAINS),
            "passive_outreach": True,
            "quiet_hours": {"start": "00:00", "end": "00:00", "tz_offset_min": 120},  # never quiet
            "paused_until": None}
    if mode == "always_open":  return base
    if mode == "night_quiet":  base["quiet_hours"] = {"start": "22:00", "end": "09:00", "tz_offset_min": 120}; return base
    if mode == "busy":         base["status"] = "busy"; return base
    if mode == "paused":       base["status"] = "paused"; return base
    if mode == "no_passive":   base["passive_outreach"] = False; return base
    if mode == "none":         return None
    return base

# ---------------------------------------------------------------- recipes
# (tag, count@n=1000, dict of fields). interests may mix EN taxonomy words, RU words, off-taxonomy.
# own_intent: probability of carrying an ACTIVE intent (topics drawn from own interests) -> T0 tests.
R = []
def recipe(tag, count, interests, langs=("en",), vibes=None, geo="bcn", age=(20, 44),
           recv="always_open", recv_domains=None, own_intent=0.0, own_type="social",
           dating=False, entities=None, deals=None, open_flag=None, extras=None, role=None):
    R.append(dict(tag=tag, count=count, interests=interests, langs=langs, vibes=vibes, geo=geo,
                  age=age, recv=recv, recv_domains=recv_domains, own_intent=own_intent,
                  own_type=own_type, dating=dating, entities=entities, deals=deals,
                  open_flag=open_flag, extras=extras or {}, role=role))

# tag -> declared role (spec §6 "negative edge": ranked-competitive vs casual, player vs watcher)
_ROLE = {"dota_active": "play", "dota_interest": "play", "lol_only": "play", "valorant_cs": "play",
         "fifa_console": "play", "padel": "play", "tennis": "play", "football_play": "play",
         "running": "play", "climbing": "play", "barca_fans": "watch", "f1_fans": "watch",
         "series_watch": "watch", "spanish_native": "practise", "spanish_learner": "practise",
         "english_club": "practise", "french_german": "practise", "russian_exch": "practise",
         "yoga": "practise", "books": "discuss", "founder_ai": "discuss", "product_ux": "discuss",
         "investor": "discuss", "dev_it": "discuss", "crypto": "discuss",
         "art_museum": "attend", "theatre": "attend"}

# --- games (spec §18.2) ---
recipe("dota_active",   28, [["dota 2", "гейминг"], ["dota", "ranked"], ["дота", "dota 2"]],
       langs=("ru", "en"), own_intent=0.9, own_type="gaming", entities=["Dota 2 ladder"])
recipe("dota_interest", 26, [["dota 2"], ["дота 2", "киберспорт"]], langs=("ru", "en"))
recipe("lol_only",      20, [["league of legends"], ["лол", "league"]], langs=("en", "ru"))
recipe("valorant_cs",   26, [["valorant"], ["cs", "counter strike"], ["валорант"]], langs=("en", "ru"))
recipe("chess_board",   22, [["chess", "boardgames"], ["шахматы"], ["настолки", "настольные игры"]],
       langs=("ru", "en"), own_intent=0.3, own_type="gaming")
recipe("fifa_console",  14, [["fifa", "playstation"], ["фифа", "приставка"]], langs=("ru", "en"))
# --- sport (§18.6 падель) ---
recipe("padel",         24, [["padel"], ["падель"], ["padel", "tennis"]], own_intent=0.4,
       own_type="sport", geo="bcn")
recipe("tennis",        18, [["tennis"], ["теннис"]], own_intent=0.3, own_type="sport")
recipe("football_play", 26, [["football"], ["футбол"], ["футбол", "мини-футбол"]],
       langs=("ru", "es", "en"), own_intent=0.4, own_type="sport")
recipe("gym_cross",     20, [["gym", "crossfit"], ["зал", "кроссфит"], ["fitness"]], langs=("ru", "en"))
recipe("yoga",          14, [["yoga"], ["йога", "растяжка"]], vibes=["calm", "chill"])
recipe("running",       18, [["running"], ["бег"], ["running", "marathon"]], own_intent=0.3, own_type="sport")
recipe("climbing",      14, [["climbing", "bouldering"], ["скалолазание"]])
# --- social (§18.3 прогулка, §18.6 кофе/пиво) ---
recipe("coffee_en",     26, [["coffee"], ["coffee", "brunch"], ["specialty coffee"]], own_intent=0.3)
recipe("coffee_ru",     26, [["кофе"], ["кофе", "спешелти"], ["кофейни"]], langs=("ru",), own_intent=0.3)
recipe("walk_eixample", 26, [["walking", "strolls"], ["прогулки"], ["гулять", "город"]],
       langs=("ru", "es", "en"), geo="eixample", own_intent=0.4, own_type="social")
recipe("walk_far",      12, [["прогулки"], ["walking"]], geo="madrid")
recipe("beer_pub",      18, [["beer", "pubs"], ["пиво"], ["пиво", "крафт"]], langs=("ru", "en"))
recipe("dinner_food",   20, [["dinner", "food"], ["ужины", "рестораны"], ["cooking"]])
recipe("brunch",        12, [["brunch", "cafe"], ["бранч"]])
# --- culture (§18.6 MACBA, книги) ---
recipe("art_museum",    22, [["art", "museum"], ["искусство", "музеи"], ["exhibitions", "macba"]],
       own_intent=0.3, own_type="social")
recipe("cinema",        22, [["cinema"], ["кино"], ["кино", "сериалы"]], langs=("ru", "en"))
recipe("books",         22, [["books", "reading"], ["книги"], ["книжный клуб"]], langs=("ru", "en"),
       vibes=["intellectual", "calm", "chill"])
recipe("theatre",       10, [["theatre"], ["театр"]])
recipe("photography",   12, [["photography"], ["фотография", "стрит-фото"]])
# --- language exchange (§18.4) ---
recipe("spanish_native",22, [["language exchange", "spanish"], ["языковой обмен", "испанский"]],
       langs=("es", "en"), own_intent=0.4, own_type="language")
recipe("spanish_learner",20, [["spanish", "language exchange"], ["испанский", "практика языка"]],
       langs=("ru", "en"), own_intent=0.3, own_type="language")
recipe("english_club",  18, [["english", "speaking club"], ["английский", "разговорный клуб"]],
       langs=("ru",))
recipe("french_german", 16, [["french"], ["german"], ["французский"], ["немецкий"]],
       langs=("fr", "de", "en"))
recipe("russian_exch",  12, [["russian", "language exchange"], ["русский язык"]], langs=("ru", "es"))
# --- professional networking (§18.5) ---
recipe("founder_ai",    22, [["startups", "ai"], ["стартапы", "нейросети"], ["founder", "ml"]],
       vibes=["intellectual", "energetic", "social"], own_intent=0.4, own_type="networking",
       entities=["Startup Grind BCN"])
recipe("product_ux",    18, [["product", "design"], ["продакт", "ux"]], langs=("ru", "en"))
recipe("investor",      10, [["investing", "venture"], ["инвестиции"]])
recipe("dev_it",        20, [["programming", "backend"], ["программирование"], ["coding", "python"]],
       langs=("ru", "en"))
recipe("crypto",        10, [["crypto", "web3"], ["крипта"]])
# --- watch together (§18.6 Барса) ---
recipe("barca_fans",    20, [["watch football", "barca"], ["смотреть футбол", "барса"],
                             ["футбол по тв", "бар"]], langs=("ru", "es", "en"), own_intent=0.4,
       own_type="social", entities=["Camp Nou crowd"])
recipe("f1_fans",        8, [["formula 1"], ["формула 1"]])
recipe("series_watch",  12, [["series", "watch together"], ["сериалы", "совместный просмотр"]])
# --- outdoors ---
recipe("hiking",        22, [["hiking", "mountains"], ["хайкинг", "горы"], ["походы"]],
       own_intent=0.3, own_type="sport")
recipe("fishing",       16, [["fishing"], ["рыбалка"], ["рыбачить", "спиннинг"]], langs=("ru",))
recipe("travel",        12, [["travel", "roadtrips"], ["путешествия"]])
# --- coworking (§18.6) ---
recipe("cowork_poblenou", 20, [["coworking"], ["коворкинг", "поработать вместе"]], geo="poblenou",
       own_intent=0.3, own_type="social")
recipe("digital_nomad", 12, [["coworking", "remote work"], ["удалёнка", "кафе с ноутом"]])
# --- dating contour (§17: isolated) ---
recipe("dating_open",   26, [["coffee", "walks"], ["кино", "прогулки"], ["wine", "art"]],
       dating=True, recv_domains=ALL_DOMAINS + ["dating"], own_intent=0.2, own_type="dating")
recipe("dating_closed", 14, [["coffee"], ["прогулки"], ["cinema"]], dating=False)
# --- off-taxonomy interests (must match via word-overlap, never via false category) ---
recipe("apple_tech",    14, [["технику apple"], ["apple", "гаджеты"], ["macbook", "apple"]],
       langs=("ru", "en"))
recipe("labubu",         8, [["labubu"], ["лабубу", "коллекционные игрушки"]])
recipe("mate_tea",       8, [["мате"], ["mate tea"]])
recipe("disc_golf",      8, [["disc golf"], ["диск-гольф"]])
# --- gates / readiness edge cases ---
recipe("minor_16",      10, [["football"], ["gaming"], ["кофе"]], age=(16, 17))
recipe("paused_user",   12, [["coffee"], ["футбол"], ["dota 2"]], recv="paused")
recipe("busy_user",     12, [["coffee"], ["падель"], ["books"]], recv="busy")
recipe("night_quiet",   14, [["coffee"], ["прогулки"], ["cinema"]], recv="night_quiet")
recipe("no_policy",     14, [["coffee"], ["футбол"], ["hiking"]], recv="none", open_flag=None)
recipe("games_only_recv",10, [["dota 2", "coffee"]], recv_domains=["games"])
recipe("overloaded",     6, [["coffee"], ["tennis"]], extras={"pending": 7})
recipe("blocker",        4, [["coffee"]], extras={"blocksMe": True})
recipe("declined_cd",    4, [["coffee"]], extras={"declinedOwnerDaysAgo": 2})
recipe("no_langs",       6, [["chess"], ["yoga"]], langs=())
# --- sparse profiles (§9: must not outrank full ones silently) ---
recipe("sparse_one",    24, [["coffee"], ["футбол"], ["dota 2"], ["books"], ["падель"]],
       vibes=[None], geo="none", recv="none", age=(0, 0), open_flag=None)

LANG_SETS = {"en": ["en"], "ru": ["ru"], "es": ["es"], "ru,en": ["ru", "en"], "es,en": ["es", "en"],
             "ru,es,en": ["ru", "es", "en"]}

def _next_name(counter, used):
    """Deterministic unique human-looking name; numeric suffix only after all 3200 combos."""
    while True:
        n = counter[0]
        counter[0] += 1
        base = FIRST[n % len(FIRST)] + " " + LAST[(n // len(FIRST)) % len(LAST)]
        k = n // (len(FIRST) * len(LAST))
        nm = base if k == 0 else "%s %d" % (base, k + 1)
        if nm not in used:
            used.add(nm)
            return nm

def build(n_target, seed):
    rnd = random.Random(seed)
    scale = float(n_target) / sum(r["count"] for r in R)
    users, index, used = [], {}, set()
    counter = [0]
    for r in R:
        cnt = max(1, round(r["count"] * scale))
        names = []
        for i in range(cnt):
            nm = _next_name(counter, used)
            ints = list(rnd.choice(r["interests"]))
            langs = list(r["langs"]) if r["langs"] else []
            if langs and rnd.random() < 0.3:
                extra = rnd.choice(["en", "es", "ru", "ca", "fr"])
                if extra not in langs:
                    langs.append(extra)
            vibe = rnd.choice(r["vibes"] or VIBES)
            gkey = r["geo"]
            if gkey == "bcn":
                gkey = rnd.choice(BCN)
            geo = GEO.get(gkey)
            age = rnd.randint(*r["age"]) if r["age"] != (0, 0) else None
            u = {
                "id": "lt" + hashlib.sha1(nm.encode()).hexdigest()[:8],
                "name": nm, "interests": ints, "vibe": vibe, "langs": langs,
                "role": r["role"] or _ROLE.get(r["tag"]),
                "source": "loadtest", "tags": [r["tag"]],
                "verified": rnd.random() < 0.75, "datingOk": bool(r["dating"]),
                "pending": 0, "blocksMe": False, "paused": False,
                "lastActiveDays": rnd.randint(0, 5), "declinedOwnerDaysAgo": None,
                "intents": [], "entities": list(r["entities"] or []),
                "dealBreakers": list(r["deals"] or []),
            }
            if age is not None:
                u["age"] = age
            if geo:
                jlat = (rnd.random() - 0.5) * 0.012          # ~±0.7 km jitter
                jlon = (rnd.random() - 0.5) * 0.016
                u["geo"] = {"coarseLat": round(geo[0] + jlat, 5), "coarseLon": round(geo[1] + jlon, 5)}
            rec = _recv(r["recv"], r["recv_domains"])
            if rec is not None:
                u["receiving"] = rec
            if r["open_flag"] is not None:
                u["open"] = r["open_flag"]
            elif r["recv"] not in ("none",):
                u["open"] = rnd.random() < 0.8
            if rnd.random() < r["own_intent"]:
                u["intents"] = [{"type": r["own_type"], "topics": ints[:2],
                                 "role": rnd.choice(["meet", "play", "discuss", "practise"]),
                                 "time": rnd.choice(["Today evening", "tonight", "Tomorrow",
                                                     "This weekend", "Flexible"])}]
            u.update(r["extras"])
            users.append(u)
            names.append(nm)
        index[r["tag"]] = names
    return users, index

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", required=True)
    ap.add_argument("--index", default=None)
    ap.add_argument("--merge", default=None,
                    help="existing users.json whose NON-loadtest users are preserved")
    a = ap.parse_args()
    users, index = build(a.n, a.seed)
    keep = []
    if a.merge and os.path.exists(a.merge):
        with open(a.merge, encoding="utf-8") as f:
            data = json.load(f)
        old = data.get("users") if isinstance(data, dict) else data
        keep = [u for u in (old or []) if u.get("source") != "loadtest"]
    synth_names = {u["name"] for u in users}
    keep = [u for u in keep if u.get("name") not in synth_names]
    allu = keep + users
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"users": allu}, f, ensure_ascii=False)
    if a.index:
        with open(a.index, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=0)
    print("wrote %d users (%d kept + %d loadtest, %d recipes) -> %s" %
          (len(allu), len(keep), len(users), len(R), a.out))

if __name__ == "__main__":
    main()
