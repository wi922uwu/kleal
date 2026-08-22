# -*- coding: utf-8 -*-
"""Seed 600 people in Barcelona — deliberately MESSY, the way real registrations look.

Interests are NOT pre-canonicalised into the ranker's 158-word taxonomy. They are drawn from a wide
pool that mixes clean English tokens, Spanish/Catalan/Russian phrasing, multi-word terms and niche
hobbies nobody has a taxonomy entry for. That is the point: a pool of already-canonical tokens tests
nothing, while this exercises filtration, buddy's canonicalisation and matching's literal-overlap
path together — and shows honestly where each of them still drops something.

Written straight into the shared store in the exact shape onboarding's _profile_to_user produces,
so every consumer (matching, admin, profile) reads them as ordinary registrations.
Marked source="seed" so they can be removed again without touching real sign-ups.
"""
import hashlib, json, os, random, sys

random.seed(20260726)

# Same default the matching service and onboarding resolve to (repo-root users.json).
OUT = os.environ.get("KLEAL_USERS",
                     os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "users.json"))
N = int(os.environ.get("SEED_N", "600"))

# ---- Barcelona, by district, with real coarse coordinates -------------------------------------
DISTRICTS = [
    ("Gràcia", 41.4045, 2.1527), ("Eixample", 41.3915, 2.1630), ("El Born", 41.3840, 2.1810),
    ("Barceloneta", 41.3797, 2.1896), ("El Raval", 41.3795, 2.1686), ("Gòtic", 41.3830, 2.1770),
    ("Sants", 41.3750, 2.1350), ("Poblenou", 41.3990, 2.2030), ("Sarrià", 41.3990, 2.1220),
    ("Les Corts", 41.3860, 2.1300), ("Horta", 41.4250, 2.1600), ("Sant Andreu", 41.4350, 2.1900),
    ("Nou Barris", 41.4420, 2.1770), ("Guinardó", 41.4160, 2.1720), ("Poble-sec", 41.3730, 2.1580),
    ("Vila Olímpica", 41.3890, 2.1970), ("Sant Gervasi", 41.4010, 2.1400), ("Clot", 41.4110, 2.1880),
    ("Sagrada Família", 41.4036, 2.1744), ("Badalona", 41.4500, 2.2470), ("L'Hospitalet", 41.3590, 2.1000),
]

FIRST = ("Marc Laia Pau Nuria Jordi Anna Oriol Carla Pol Marta Arnau Julia Guillem Aina Roger Clara "
         "Sergi Emma Bruno Sofia Diego Lucia Javier Elena Pablo Rosa Alvaro Irene Hugo Alba "
         "Matteo Giulia Luca Chiara Marco Elisa Andrea Sara Nico Valentina "
         "Thomas Louise Julien Camille Antoine Manon Pierre Chloe Lucas Ines "
         "Jonas Lena Felix Mia Erik Nadia Lars Petra Kai Vera "
         "Ivan Olga Dmitry Anya Sergey Katya Pavel Masha Artem Sonya "
         "Youssef Amina Omar Layla Karim Nour Rami Dalia "
         "Kenji Yuki Hiro Sakura Wei Mei Jin Ling "
         "Adam Zoe Noah Iris Leo Maya Sam Nina Ben Cleo Ravi Tanya Gabriel Paula").split()
LAST = ("Puig Ferrer Serra Vidal Roca Bosch Camps Mas Soler Riera Costa Pons Vila Font Marti "
        "Garcia Lopez Martinez Sanchez Romero Navarro Ortega Molina Iglesias Castro "
        "Rossi Ferrari Conti Greco Moretti Ricci "
        "Dubois Moreau Laurent Girard Petit Renard "
        "Schmidt Weber Fischer Becker Hoffmann Klein "
        "Ivanov Petrov Volkov Sokolov Novak Horvat Kovalenko Melnyk "
        "Ali Hassan Farah Nasser Tanaka Sato Chen Wang Kim Park "
        "Silva Costa Pereira Almeida Nilsson Berg Larsen Jensen").split()

# ---- interests: messy on purpose --------------------------------------------------------------
# Clean taxonomy tokens, so part of the pool resolves cleanly and the rest has to be worked for.
CLEAN = ("coffee football padel tennis chess boardgames gaming dota running cycling climbing yoga "
         "pilates gym swimming hiking camping fishing surfing skiing photography cinema museum "
         "theatre books reading music guitar piano concert techno karaoke cooking brunch wine beer "
         "bar party travel languages spanish english french german italian coding ai startups "
         "design networking investing dnd poker cards pingpong basketball volleyball boxing").split()

# Spanish / Catalan, as a Barcelona resident would actually type it.
ES_CA = ["pádel", "senderismo", "escalada", "natación", "ciclismo", "fútbol sala", "baloncesto",
         "cerveza artesanal", "vermut", "tapas", "paella", "cafè amb llet", "café de especialidad",
         "castellers", "sardanes", "rumba catalana", "flamenco", "sevillanas",
         "cine español", "teatro independiente", "museos", "arquitectura modernista",
         "intercambio de idiomas", "catalán", "castellano", "clases de salsa", "bachata",
         "petanca", "calçotada", "excursiones por Montserrat", "playa y voley", "kayak en la Costa Brava",
         "mercadillos vintage", "fotografía analógica", "cerámica", "huerto urbano"]

# Russian, kept because a chunk of the real sign-ups arrive in it.
RU = ["настолки", "шахматы", "походы в горы", "бег по утрам", "велопрогулки", "скалолазание",
      "йога", "плавание", "сноуборд", "рыбалка", "фотография", "кино", "театр", "музеи",
      "книжный клуб", "гитара", "электронная музыка", "караоке", "готовка", "вино", "крафтовое пиво",
      "путешествия", "испанский язык", "программирование", "стартапы", "инвестиции", "преферанс",
      "бачата", "лабубу", "спидкубинг", "кинцуги", "страйкбол", "петанк", "фридайвинг"]

# Niche and brand-new: nothing in any taxonomy knows these.
NICHE = ["labubu", "kintsugi", "speedcubing", "bachata", "kizomba", "petanque", "airsoft",
         "freediving", "bouldering", "parkour", "urban sketching", "bookcrossing", "geocaching",
         "fpv drones", "3d printing", "mechanical keyboards", "vinyl digging", "improv theatre",
         "board game cafes", "escape rooms", "birdwatching", "foraging", "home brewing",
         "roller derby", "capoeira", "aerial silks", "ultimate frisbee", "spikeball", "padel tennis",
         "sourdough baking", "specialty coffee", "natural wine", "chess boxing", "swing dancing",
         "tango argentino", "muay thai", "calisthenics", "trail running", "open water swimming",
         "sailing", "windsurf", "skate", "longboard", "watercolour", "linocut", "film photography",
         "street art tours", "vermouth crawls", "language cafes", "startup meetups", "AI safety",
         "indie hacking", "climate tech", "board sports", "night photography", "astrophotography"]

POOL = [(w, "clean") for w in CLEAN] + [(w, "es") for w in ES_CA] + \
       [(w, "ru") for w in RU] + [(w, "niche") for w in NICHE]

LANGS = ["es", "ca", "en", "it", "fr", "de", "ru", "pt", "ar", "zh", "uk", "nl"]
ROLES = ["meet", "play", "watch", "discuss", "practise", "attend"]
VIBES = ["", "chill", "social", "active", "curious", "creative", "focused"]
FORMATS = ["offline", "online", "1:1", "small_group", "group"]
GOALS = ["friends", "activity_partner", "language", "networking", "community"]


def receiving(dating):
    doms = ["social_meet", "walk", "games", "language_exchange", "sport_activity",
            "culture_event", "professional_networking", "watch_together", "coworking"]
    if dating:
        doms.append("dating")
    return {"status": "active", "allowed_domains": doms, "passive_outreach": True,
            "quiet_hours": {"start": "22:00", "end": "09:00", "tz_offset_min": 120},
            "paused_until": None}


def age_pick():
    """Skewed the way a city app's population actually is, but the tails are real people too."""
    r = random.random()
    if r < 0.10:  return random.randint(18, 22)
    if r < 0.45:  return random.randint(23, 30)
    if r < 0.75:  return random.randint(31, 40)
    if r < 0.90:  return random.randint(41, 52)
    if r < 0.97:  return random.randint(53, 64)
    return random.randint(65, 75)


used = set()
people = []
for i in range(N):
    for _ in range(60):
        name = "%s %s" % (random.choice(FIRST), random.choice(LAST))
        if name.lower() not in used:
            break
    else:
        name = "%s %s %d" % (random.choice(FIRST), random.choice(LAST), i)
    used.add(name.lower())

    area, lat, lon = random.choice(DISTRICTS)
    lat += random.uniform(-0.012, 0.012)
    lon += random.uniform(-0.012, 0.012)

    # 2-5 interests, mixed across the buckets so no single flavour dominates the pool
    k = random.choice([2, 3, 3, 4, 4, 5])
    picked, seen_w = [], set()
    while len(picked) < k:
        w, _bucket = random.choice(POOL)
        if w.lower() not in seen_w:
            seen_w.add(w.lower())
            picked.append(w)

    langs = ["es"] if random.random() < .55 else []
    if random.random() < .30 and "ca" not in langs: langs.append("ca")
    if random.random() < .70 and "en" not in langs: langs.append("en")
    for extra in random.sample(LANGS, random.randint(0, 2)):
        if extra not in langs: langs.append(extra)
    langs = (langs or ["en"])[:4]

    gender = random.choices(["Male", "Female", "Other"], weights=[46, 46, 8])[0]
    dating = random.random() < .18
    age = age_pick()

    people.append({
        "id": "sd" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:8],
        "name": name,
        "interests": picked,
        "vibe": random.choice(VIBES),
        "langs": langs,
        "area": area + ", Barcelona",
        "km": None, "lat": round(lat, 5), "lon": round(lon, 5),
        "radiusKm": random.choice([5, 8, 10, 12, 15, 20, 25, 30]),
        "open": random.random() < .88,
        "role": random.choice(ROLES),
        "gender": gender,
        "goals": random.sample(GOALS, random.randint(0, 2)),
        "summary": "", "story": "", "personality": "", "persona": None,
        "formats": random.sample(FORMATS, random.randint(0, 2)),
        "safety": {"publicPlacesOnly": random.random() < .8, "verifiedOnly": random.random() < .15,
                   "hideExactLocation": random.random() < .2},
        "datingOk": dating,
        "age": age,
        "verified": random.random() < .7,
        "paused": False, "pending": random.choice([0, 0, 0, 1, 2]), "blocksMe": False,
        "lastActiveDays": random.choice([0, 0, 0, 1, 1, 2, 3, 5, 8, 14]),
        "declinedOwnerDaysAgo": None,
        "intents": [], "entities": [],
        "dealBreakers": [], "source": "seed",
        "receiving": receiving(dating),
    })

# keep whatever real registrations are already there; only replace previous seeds
try:
    cur = json.load(open(OUT, encoding="utf-8"))
    keep = [u for u in (cur.get("users") if isinstance(cur, dict) else cur) or []
            if u.get("source") != "seed"]
except Exception:
    keep = []

tmp = OUT + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump({"users": keep + people}, f, ensure_ascii=False)
os.replace(tmp, OUT)

import collections
print("записано: %d (сохранено реальных: %d)" % (len(people), len(keep)))
print("возраст:", min(p["age"] for p in people), "-", max(p["age"] for p in people),
      "| медиана", sorted(p["age"] for p in people)[len(people)//2])
print("пол:", dict(collections.Counter(p["gender"] for p in people)))
print("районов:", len({p["area"] for p in people}), "| уникальных интересов:",
      len({w.lower() for p in people for w in p["interests"]}))
print("dating-ok:", sum(1 for p in people if p["datingOk"]), "| verified:", sum(1 for p in people if p["verified"]))
