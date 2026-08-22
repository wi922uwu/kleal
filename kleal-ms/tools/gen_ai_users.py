# -*- coding: utf-8 -*-
"""Generate a large, MAXIMALLY DIVERSE seed population with the self-hosted LLM.

Runs ON the pod (the model is local there). The LLM writes each person; this script only picks a
rotating focus per batch so diversity covers the whole space evenly, maps the model's output onto the
matching row schema, validates, de-dupes, and merges into users.json as source="seed" (a live,
matchable population — distinct from source="loadtest", which live matching excludes, and removable in
one line by its source tag).

Usage:  python3 tools/gen_ai_users.py --n 2000 --out /root/kleal-ms/users.json --workers 6
"""
import os, sys, json, re, time, random, argparse, hashlib, threading
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "shared"))
from llm_client import llm_complete   # POSTs llm-service -> self-hosted Llama-3.3-70B

MODEL = os.environ.get("SEED_MODEL", "llama_self")

# ---- the vocabulary the model must pick interests from (matching taxonomy + realistic life extras) --
TAXO = ("ai apex architecture art badminton ballet band bar basketball beer biking blockchain boardgames "
        "bookclub books bouldering boxing brunch business cafe camping cards career chess chill cinema "
        "climbing clubbing coding coffee concert cooking course crossfit crypto cs cycling data design "
        "dinner dj dnd dota drinks drums edm engineering entrepreneur festival fifa fishing fitness food "
        "football fortnite founder french gaming german gig guitar gym handball hiking investing italian "
        "jam jogging karaoke kayaking language league literature marathon mentorship ml mma mountains "
        "movies museum music nature networking nightlife opera outdoors overwatch padel painting party "
        "photography piano pilates pingpong poker portuguese product programming pub rave reading "
        "restaurant roadtrip running russian series sightseeing singing skiing snowboard soccer software "
        "spanish squash standup startups strength stretching surfing swimming tabletop tennis theatre "
        "travel trekking triathlon ui ux valorant vinyl volleyball walking wine workout yoga "
        "minecraft roblox rocketleague pubg warzone wow hearthstone "
        # realistic extras (literal-word matching still links them person-to-person)
        "pets dogs cats fashion baking wine_tasting sailing diving pottery knitting gardening "
        "volunteering meditation astrology chess_online kpop anime cosplay podcasting").split()

LANGS = ["en","es","ru","sr","de","fr","it","pt","ca","uk","pl","nl","tr","ar","he","zh","ja","ko",
         "hi","th","sv","da","no","fi","el","ro","hu","cs","id","vi"]

# city -> (lat, lon). Restricting the model to this set guarantees every person geocodes.
CITIES = {
 "Barcelona":(41.39,2.17),"Madrid":(40.42,-3.70),"Valencia":(39.47,-0.38),"Lisbon":(38.72,-9.14),
 "Berlin":(52.52,13.40),"Munich":(48.14,11.58),"London":(51.51,-0.13),"Manchester":(53.48,-2.24),
 "Paris":(48.86,2.35),"Lyon":(45.76,4.84),"Amsterdam":(52.37,4.90),"Rotterdam":(51.92,4.48),
 "Milan":(45.46,9.19),"Rome":(41.90,12.50),"Vienna":(48.21,16.37),"Zurich":(47.37,8.54),
 "Stockholm":(59.33,18.06),"Copenhagen":(55.68,12.57),"Oslo":(59.91,10.75),"Helsinki":(60.17,24.94),
 "Warsaw":(52.23,21.01),"Krakow":(50.06,19.94),"Prague":(50.08,14.44),"Budapest":(47.50,19.04),
 "Bucharest":(44.43,26.10),"Athens":(37.98,23.73),"Belgrade":(44.79,20.45),"Zagreb":(45.81,15.98),
 "Kyiv":(50.45,30.52),"Moscow":(55.76,37.62),"Saint Petersburg":(59.93,30.36),"Tbilisi":(41.72,44.83),
 "Yerevan":(40.18,44.51),"Istanbul":(41.01,28.98),"Dubai":(25.20,55.27),"Tel Aviv":(32.09,34.78),
 "Cairo":(30.04,31.24),"Nairobi":(-1.29,36.82),"Cape Town":(-33.92,18.42),"Lagos":(6.52,3.38),
 "New York":(40.71,-74.01),"San Francisco":(37.77,-122.42),"Los Angeles":(34.05,-118.24),
 "Chicago":(41.88,-87.63),"Austin":(30.27,-97.74),"Toronto":(43.65,-79.38),"Mexico City":(19.43,-99.13),
 "Bogota":(4.71,-74.07),"Buenos Aires":(-34.60,-58.38),"Sao Paulo":(-23.55,-46.63),"Lima":(-12.05,-77.04),
 "Bangkok":(13.76,100.50),"Singapore":(1.35,103.82),"Bali":(-8.34,115.09),"Tokyo":(35.68,139.69),
 "Seoul":(37.57,126.98),"Delhi":(28.61,77.21),"Mumbai":(19.08,72.88),"Sydney":(-33.87,151.21),
 "Melbourne":(-37.81,144.96),"Auckland":(-36.85,174.76),
}
CITY_LIST = list(CITIES.keys())

# rotating focus so the union of batches covers the whole space, not the model's favourite corner
REGIONS = [
 ("Iberia & Balkans", ["Barcelona","Madrid","Valencia","Lisbon","Belgrade","Zagreb","Athens","Bucharest"]),
 ("Central Europe", ["Berlin","Munich","Vienna","Zurich","Prague","Warsaw","Krakow","Budapest"]),
 ("West Europe", ["London","Manchester","Paris","Lyon","Amsterdam","Rotterdam","Milan","Rome"]),
 ("Nordics", ["Stockholm","Copenhagen","Oslo","Helsinki"]),
 ("East Europe & Caucasus", ["Kyiv","Moscow","Saint Petersburg","Tbilisi","Yerevan","Istanbul"]),
 ("MENA & Africa", ["Dubai","Tel Aviv","Cairo","Nairobi","Cape Town","Lagos"]),
 ("North America", ["New York","San Francisco","Los Angeles","Chicago","Austin","Toronto"]),
 ("Latin America", ["Mexico City","Bogota","Buenos Aires","Sao Paulo","Lima"]),
 ("Asia-Pacific", ["Bangkok","Singapore","Bali","Tokyo","Seoul","Delhi","Mumbai","Sydney","Melbourne","Auckland"]),
]
THEMES = [
 "team & racket sports (football, basketball, tennis, padel), plus gym and running",
 "nightlife and social (bars, drinks, wine, dinners, coffee, walks, dancing)",
 "online gaming and esports (dota, valorant, cs, minecraft, warzone, discord voice)",
 "tabletop and board games (chess, poker, boardgames, dnd) — in person",
 "tech, startups, founders, AI/ML, coding, product, investing, networking",
 "music: concerts, festivals, playing guitar/piano, DJing, electronic, karaoke, vinyl",
 "arts and culture: cinema, museums, theatre, photography, painting, books, bookclubs",
 "outdoors and travel: hiking, climbing, surfing, skiing, camping, roadtrips, sightseeing",
 "languages and learning: language exchange, courses, workshops, mentorship",
 "wellness and lifestyle: yoga, pilates, meditation, cooking, baking, gardening, pets",
]
AGE_BANDS = ["18-24 (students, early-career)", "25-32", "30-42", "40-55", "50-70 (older adults)"]
GENDERS = "roughly balanced across female, male, non-binary"

_TAXO_SET = set(TAXO)
_LANG_SET = set(LANGS)

def build_prompt(region_name, cities, theme, age_band, k):
    city_opts = ", ".join(cities)
    return [
        {"role": "system", "content":
         "You generate realistic, richly VARIED fictional people for a social-meetup app's test population. "
         "Output ONLY a JSON array, no prose. Every person must be distinct — vary names (match the city's "
         "culture and language, use many nationalities), ages, genders, interest mixes, personalities and "
         "meeting styles. Never repeat a name."},
        {"role": "user", "content":
         f"Generate {k} distinct people as a JSON array. For THIS batch:\n"
         f"- cities: pick each person's city ONLY from: {city_opts}\n"
         f"- lean the interests toward: {theme} (but still vary — mix in 1-2 unrelated interests per person)\n"
         f"- age skew: {age_band}; genders: {GENDERS}\n\n"
         "Each object MUST have exactly these fields:\n"
         '  "name": string (first + last, culturally fitting the city),\n'
         '  "age": integer 18-72,\n'
         '  "gender": "female" | "male" | "nonbinary",\n'
         '  "city": one of the cities above,\n'
         '  "langs": array of 1-3 ISO codes chosen from: ' + ",".join(LANGS) + ",\n"
         '  "interests": array of 3-6 lowercase words chosen ONLY from this list: ' + " ".join(TAXO) + ",\n"
         '  "vibe": one lowercase word (e.g. calm, playful, ambitious, cozy, adventurous, intellectual),\n'
         '  "formats": array from ["online","offline","hybrid","1:1","small","party","events"] '
         "(gamers/remote lean online or hybrid; in-person activities lean offline),\n"
         '  "dating": boolean (about 1 in 4 true),\n'
         '  "role": one of "meet","play","watch","discuss","practise","attend",\n'
         '  "bio": one short first-person sentence.\n\n'
         "Return ONLY the JSON array."}
    ]

def extract_json(txt):
    txt = txt.strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-zA-Z]*\n?", "", txt); txt = re.sub(r"\n?```$", "", txt)
    a, b = txt.find("["), txt.rfind("]")
    if a >= 0 and b > a:
        try:
            return json.loads(txt[a:b+1])
        except Exception:
            pass
    out = []                                     # salvage object-by-object
    for m in re.finditer(r"\{[^{}]*\}", txt):
        try: out.append(json.loads(m.group(0)))
        except Exception: pass
    return out

def to_row(p):
    name = str(p.get("name") or "").strip()
    if not name or len(name) < 2:
        return None
    city = str(p.get("city") or "").strip()
    coord = CITIES.get(city)
    langs = [str(x).lower()[:2] for x in (p.get("langs") or []) if str(x).lower()[:2] in _LANG_SET][:3] or ["en"]
    interests = [str(x).lower().strip() for x in (p.get("interests") or []) if str(x).strip()]
    interests = [w for w in interests if w in _TAXO_SET][:6] or ["social"]
    try:
        age = max(18, min(72, int(p.get("age"))))
    except Exception:
        age = random.randint(21, 45)
    gender = str(p.get("gender") or "").lower()
    gender = gender if gender in ("female", "male", "nonbinary", "other") else random.choice(["female","male","nonbinary"])
    fmts = [str(x).lower() for x in (p.get("formats") or []) if str(x).strip()]
    fmts = [f for f in fmts if f in ("online","offline","hybrid","1:1","small","party","events")][:4]
    role = str(p.get("role") or "meet").lower()
    role = role if role in ("meet","play","watch","discuss","practise","attend") else "meet"
    row = {
        "id": "sd" + hashlib.sha1((name + city + str(age)).encode("utf-8")).hexdigest()[:9],
        "name": name, "age": age, "gender": gender, "area": city,
        "interests": interests, "langs": langs, "vibe": str(p.get("vibe") or "").lower()[:20] or None,
        "formats": fmts, "role": role, "datingOk": bool(p.get("dating")),
        "summary": str(p.get("bio") or "")[:240],
        "verified": random.random() < 0.62, "km": None, "open": True,
        "paused": random.random() < 0.07, "pending": 0, "blocksMe": False,
        "lastActiveDays": random.randint(0, 6), "declinedOwnerDaysAgo": None,
        "intents": [], "entities": [], "dealBreakers": [],
        "source": "seed",
        "receiving": {"status": "active", "domains": ["social_meet","walk","culture_event",
                      "language_exchange","coworking","watch_together","games","sport_activity",
                      "professional_networking"] + (["dating"] if bool(p.get("dating")) else [])},
    }
    if coord:
        row["lat"] = round(coord[0] + (random.random()-0.5)*0.03, 5)
        row["lon"] = round(coord[1] + (random.random()-0.5)*0.03, 5)
        row["geo"] = {"coarseLat": row["lat"], "coarseLon": row["lon"]}
    return row

_lock = threading.Lock()

def run_batch(i, k):
    region_name, cities = REGIONS[i % len(REGIONS)]
    theme = THEMES[(i // 1) % len(THEMES)]
    age_band = AGE_BANDS[(i // 2) % len(AGE_BANDS)]
    msgs = build_prompt(region_name, cities, theme, age_band, k)
    for attempt in range(3):
        try:
            txt = llm_complete(MODEL, msgs, temperature=1.0)
            people = extract_json(txt)
            rows = [r for r in (to_row(p) for p in people) if r]
            if rows:
                return rows
        except Exception as e:
            time.sleep(1.5 * (attempt + 1))
    return []

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "users.json"))
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--progress", default="/root/seed_progress.txt")
    a = ap.parse_args()

    n_batches = (a.n + a.batch - 1) // a.batch
    def log(m):
        line = "[%s] %s" % (time.strftime("%H:%M:%S"), m)
        print(line, flush=True)
        try:
            with open(a.progress, "a") as f: f.write(line + "\n")
        except Exception: pass

    log("start: target=%d batches=%d workers=%d model=%s" % (a.n, n_batches, a.workers, MODEL))
    rows_by_name = {}
    done = 0
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(run_batch, i, a.batch): i for i in range(n_batches)}
        for fut in as_completed(futs):
            done += 1
            got = fut.result() or []
            with _lock:
                for r in got:
                    key = r["name"].strip().lower()
                    if key in rows_by_name:                     # keep names unique across the pool
                        key = key + "-" + r["id"][-4:]
                        r["name"] = r["name"] + " " + r["id"][-3:].upper()
                    rows_by_name[key] = r
            if done % 5 == 0 or done == n_batches:
                log("batches %d/%d  unique people so far: %d" % (done, n_batches, len(rows_by_name)))

    seed_rows = list(rows_by_name.values())[:a.n]
    log("generated %d seed people; merging into %s" % (len(seed_rows), a.out))

    try:
        with open(a.out, "r", encoding="utf-8") as f:
            data = json.load(f)
        existing = data.get("users") if isinstance(data, dict) else data
        if not isinstance(existing, list): existing = []
    except Exception:
        existing = []
    kept = [u for u in existing if u.get("source") != "seed"]     # replace any prior seed run
    allu = kept + seed_rows
    tmp = a.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"users": allu}, f, ensure_ascii=False)
    os.replace(tmp, a.out)

    # diversity report
    from collections import Counter
    cities = Counter(r["area"] for r in seed_rows)
    ints = Counter(w for r in seed_rows for w in r["interests"])
    langs = Counter(l for r in seed_rows for l in r["langs"])
    log("DONE. kept %d non-seed + %d seed = %d total" % (len(kept), len(seed_rows), len(allu)))
    log("distinct cities=%d interests=%d langs=%d" % (len(cities), len(ints), len(langs)))
    log("top cities: %s" % dict(cities.most_common(8)))
    log("top interests: %s" % dict(ints.most_common(12)))
    log("dating opt-in: %d  verified: %d  paused: %d" % (
        sum(1 for r in seed_rows if r["datingOk"]),
        sum(1 for r in seed_rows if r["verified"]),
        sum(1 for r in seed_rows if r["paused"])))

if __name__ == "__main__":
    main()
