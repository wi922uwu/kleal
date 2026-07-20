# -*- coding: utf-8 -*-
# Kleal matching-service — the buddy agent (intent parse -> ranked candidates -> agent negotiation).
# Carved from the pre-split monolith kleal_v2.py (matching half, lines 304-831). Serves /api/agent/*.
# Talks to llm-service over HTTP for parse/intro/negotiate; holds NO model keys. Owner: Dev B.
# Endpoint names are FROZEN — the profile-service frontend hard-codes them (see ../../shared/contracts.md).
import os, sys, json, re, threading, concurrent.futures, math, hashlib, time, functools
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "..", "..", "shared"), os.path.join(_HERE, "shared")):
    if os.path.isdir(_p) and _p not in sys.path: sys.path.insert(0, _p)
import kleal_lib as base                      # keyless shared helpers (uses base._extract_json)
from llm_client import llm_complete           # the ONLY model access (HTTP -> llm-service)
from http_util import send_json, read_json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("MATCHING_PORT", "7074"))
MODEL_ID = os.environ.get("V2_MODEL", "llama_self")


# ======================= BUDDY AGENT (intent parsing + matching) =======================
# The core loop from the TZ: free-text query -> structured intent -> ranked candidates ->
# agent-to-agent negotiation -> curated result. Uses the LLM to parse, deterministic scoring to rank.
# Hierarchical interest taxonomy: BROAD category -> SUB-category -> interest words.
TAXONOMY = {
  'sports':  {'team':['football','soccer','basketball','volleyball','handball'],
              'racket':['tennis','padel','badminton','squash','pingpong'],
              'endurance':['running','jogging','cycling','biking','swimming','triathlon','marathon'],
              'strength':['gym','fitness','workout','crossfit','boxing','mma','climbing','bouldering'],
              'mindbody':['yoga','pilates','stretching']},
  'social':  {'coffee':['coffee','tea','brunch','cafe'],
              'dining':['dinner','lunch','food','restaurant','cooking'],
              'nightlife':['bar','drinks','pub','beer','wine','party','club','clubbing'],
              'casual':['walk','walking','stroll','hang','hangout','chill','talk','chat'],
              'cowork':['coworking','cowork','remotework']},
  'games':   {'esports':['dota','valorant','cs','league','apex','fortnite','fifa','overwatch','gaming'],
              'tabletop':['chess','boardgames','poker','cards','dnd','tabletop']},
  'culture': {'screen':['cinema','movies','film','series'],
              'visual':['art','museum','gallery','photography','exhibition','painting'],
              'stage':['theatre','opera','ballet','standup'],
              'reading':['books','reading','literature','bookclub'],
              'urbanism':['architecture','urbanism','city']},
  'tech':    {'startups':['startup','startups','product','founder','entrepreneur','business'],
              'engineering':['ai','ml','programming','coding','software','data','crypto','blockchain'],
              'career':['networking','investing','investor','career','mentorship'],
              'design':['design','ux','ui']},
  'music':   {'listening':['concert','gig','festival','music','vinyl'],
              'making':['guitar','piano','drums','dj','jam','producing','singing','karaoke','band'],
              'electronic':['rave','techno','edm']},
  'outdoors':{'hiking':['hiking','trekking','nature','camping','mountains','trail','outdoor','outdoors'],
              'watersnow':['surfing','kayaking','skiing','snowboard'],
              'travel':['travel','roadtrip','sightseeing'],
              'fishing':['fishing']},
  'learning':{'language':['spanish','english','french','german','italian','portuguese','russian','language','languages','exchange','practice'],
              'skills':['course','workshop','study']},
}
SYNONYMS = {'soccer':'football','movies':'cinema','movie':'cinema','film':'cinema','ml':'ai',
            'biking':'cycling','jogging':'running','theater':'theatre','board':'boardgames',
            'boardgames':'boardgames','lol':'league','csgo':'cs','cs2':'cs','game':'gaming','games':'gaming',
            # short forms / morphology (users type verbs, taxonomy stores nouns)
            'hike':'hiking','hikes':'hiking','trek':'trekking','camp':'camping','run':'running',
            'jog':'running','bike':'cycling','swim':'swimming','climb':'climbing','box':'boxing',
            'lift':'gym','workout':'gym','paint':'painting','draw':'painting','sing':'singing',
            'cook':'cooking','read':'reading','dance':'jam','ski':'skiing','surf':'surfing',
            'travelling':'travel','traveling':'travel','trip':'travel','coffees':'coffee',
            'drink':'drinks','party':'party','gym':'gym','codes':'coding','code':'coding','programme':'coding'}
# ---- RU -> EN taxonomy bridge ----
# Half the real profiles arrive in Russian while the taxonomy is English; without this bridge
# "кофе" and "coffee" can never meet (the word-overlap fallback needs BOTH sides off-taxonomy).
# Keys are _norm()-shaped (lowercase, spaces stripped), values are taxonomy words.
SYNONYMS.update({
    'кофе':'coffee','кофейни':'coffee','кофейня':'coffee','чай':'tea','бранч':'brunch',
    'ужин':'dinner','ужины':'dinner','ресторан':'restaurant','рестораны':'restaurant','еда':'food',
    'готовка':'cooking','пиво':'beer','бар':'bar','бары':'bar','вино':'wine',
    'вечеринка':'party','вечеринки':'party','клубы':'club',
    'прогулка':'walk','прогулки':'walk','гулять':'walk','погулять':'walk','прогуляться':'walk',
    'футбол':'football','баскетбол':'basketball','волейбол':'volleyball','теннис':'tennis',
    'падель':'padel','бадминтон':'badminton','бег':'running','пробежка':'running','пробежки':'running',
    'велосипед':'cycling','вело':'cycling','плавание':'swimming','зал':'gym','качалка':'gym',
    'фитнес':'fitness','кроссфит':'crossfit','бокс':'boxing','скалолазание':'climbing',
    'йога':'yoga','пилатес':'pilates','растяжка':'stretching',
    'дота':'dota','дота2':'dota','доту':'dota','доте':'dota','дотку':'dota','дотан':'dota',
    'катка':'gaming','катки':'gaming','каточки':'gaming','каточку':'gaming',
    'лол':'league','валорант':'valorant','контра':'cs','кс':'cs',
    'фифа':'fifa','гейминг':'gaming','киберспорт':'gaming','шахматы':'chess',
    'настолки':'boardgames','настольныеигры':'boardgames','покер':'poker',
    'кино':'cinema','фильм':'cinema','фильмы':'cinema','сериал':'series','сериалы':'series',
    'искусство':'art','музей':'museum','музеи':'museum','галерея':'gallery',
    'выставка':'exhibition','выставки':'exhibition','фотография':'photography','театр':'theatre',
    'опера':'opera','балет':'ballet','стендап':'standup','книги':'books','книга':'books',
    'чтение':'reading','литература':'literature','книжныйклуб':'bookclub',
    'архитектура':'architecture','урбанистика':'urbanism',
    'стартап':'startup','стартапы':'startups','продакт':'product','фаундер':'founder',
    'бизнес':'business','ии':'ai','нейросети':'ai','нейросеть':'ai','машинноеобучение':'ml',
    'программирование':'coding','кодинг':'coding','разработка':'software','крипта':'crypto',
    'криптовалюты':'crypto','нетворкинг':'networking','инвестиции':'investing','инвестор':'investing',
    'карьера':'career','менторство':'mentorship','дизайн':'design',
    'концерт':'concert','концерты':'concert','фестиваль':'festival','музыка':'music',
    'гитара':'guitar','пианино':'piano','диджей':'dj','вокал':'singing','караоке':'karaoke',
    'рейв':'rave','техно':'techno',
    'хайкинг':'hiking','поход':'hiking','походы':'hiking','горы':'mountains','природа':'nature',
    'кемпинг':'camping','сёрфинг':'surfing','серфинг':'surfing','каяк':'kayaking','лыжи':'skiing',
    'сноуборд':'snowboard','путешествия':'travel','путешествие':'travel',
    'рыбалка':'fishing','рыбачить':'fishing',
    'испанский':'spanish','английский':'english','французский':'french','немецкий':'german',
    'итальянский':'italian','португальский':'portuguese','русский':'russian','языки':'languages',
    'языковойобмен':'exchange','обменязыками':'exchange','практикаязыка':'practice',
    'языковой':'language','обмен':'exchange','практика':'practice','паб':'pub','пабы':'pub',
    'курс':'course','курсы':'course','воркшоп':'workshop','учёба':'study','учеба':'study',
    'коворкинг':'coworking','поработатьвместе':'coworking','удалёнка':'remotework','удаленка':'remotework',
    # transliterations and stems the pool actually contains — without these whole cohorts were
    # unreachable from one of the two languages ('крипто' -> 0 results while 'крипта' -> 8)
    'крипто':'crypto','крипта':'crypto','криптовалюта':'crypto','биткоин':'crypto','биткойн':'crypto',
    'bitcoin':'crypto','блокчейн':'crypto','blockchain':'crypto','web3':'crypto','вэб3':'crypto',
    'формула1':'formula1','формула':'formula1','f1':'formula1','автоспорт':'formula1',
    'барса':'barca','барселона':'barca','barcelona':'barca',
    'нейросетей':'ai','ml':'ai','ии':'ai',
})
# vocabulary the pool actually uses but the taxonomy lacked: motorsport as its own sub-category,
# and the club name people write instead of "football"
TAXONOMY['sports']['motorsport'] = ['formula1', 'motorsport', 'karting']
TAXONOMY['sports']['team'].append('barca')
# curated adjacency between BROAD categories (a mild "related" bonus)
# Adjacency is deliberately conservative — over-broad links made a coffee search surface a Dota player
# ("social" ~ "games"). Keep only genuinely related neighbours.
ADJACENCY = {'sports':['outdoors'], 'social':['culture','music','learning'],
             'games':['tech'], 'culture':['learning','music'],
             'tech':['games','learning'], 'music':['culture'],
             'outdoors':['sports'], 'learning':['culture','tech']}
_IDX = {}
for _b, _subs in TAXONOMY.items():
    for _s, _ws in _subs.items():
        for _w in _ws: _IDX[_w] = (_b, _s)

# _norm/cat_of/same_topic are PURE over the static SYNONYMS+TAXONOMY (never mutated at runtime),
# so their results are memoized. This is the hottest path by far: without the cache, cat_of ran a
# linear prefix scan over the whole taxonomy for every off-taxonomy word on every candidate
# (~9.7M calls / 567M str.startswith at 5000 users). One search sees only a few thousand distinct
# words, so the cache turns the scan into a dict hit and makes p95 scale flat.
@functools.lru_cache(maxsize=65536)
def _norm(w):
    w = str(w).strip().lower().replace(' ', '')
    return SYNONYMS.get(w, w)

_SHORT_OK = {'f1', 'ux', 'ui', 'ai', 'cs', 'dj', 'ml', 'pr', 'бг'}

@functools.lru_cache(maxsize=65536)
def cat_of(word):
    """(broad, sub) for an interest/topic, matched against the KNOWN vocabulary (exact, then prefix>=5).
    Never a raw substring — so no 'art' in 'party', and >=5 stops short words like 'over'->overwatch, 'star'->startups.
    Short real forms (hike, swim, climb...) are handled by SYNONYMS, not by the prefix rule.
    Multi-word phrases resolve by their strongest token ("пить пиво" -> beer, "смотреть футбол" ->
    football) so verb+noun interests still land in the right category."""
    w = _norm(word)
    if w in _IDX: return _IDX[w]
    # plural of a SHORT vocabulary word ("pubs" -> "pub", "бары" -> "бар"): the length-gated
    # prefix rule below needs >=5 chars, so short interests fell out of the taxonomy entirely
    # and their holders became invisible to the very query that names them.
    for suf in ("s", "es", "ы", "и", "а"):
        if len(w) > len(suf) + 1 and w.endswith(suf):
            stem = _norm(w[:-len(suf)])
            if stem in _IDX: return _IDX[stem]
    for k, bs in _IDX.items():
        if len(w) >= 5 and (k.startswith(w) or w.startswith(k)): return bs
    toks = re.findall(r"[a-zа-яё0-9]+", str(word).lower())
    if len(toks) > 1:
        for t in toks:
            # generic filler must not decide the category: "speaking CLUB" resolved via 'club'
            # to social/nightlife and then read as the same sub-category as a beer search,
            # seeding every social query with the same strangers
            if t in _STOPTOK:
                continue
            tn = _norm(t)
            if tn in _IDX: return _IDX[tn]
    return (None, None)

@functools.lru_cache(maxsize=65536)
def same_topic(t, x):
    tn, xn = _norm(t), _norm(x)
    if tn == xn: return True
    ct, cx = cat_of(tn), cat_of(xn)
    if len(tn) >= 4 and len(xn) >= 4 and (tn.startswith(xn) or xn.startswith(tn)) and ct[1] and ct[1] == cx[1]:
        return True
    # phrase vs word: sharing a MEANINGFUL word (exact token or its inflected stem, via _wshare)
    # is the same entity: "пить пиво" ~ "пиво", "смотреть барсу" ~ "барса". _wtok drops generic
    # filler (клуб/вечер/games...), so "разговорный клуб" never equals "книжный клуб" this way.
    if not _wshare(t, x):
        return False
    # spec §6 negative edge: WATCHING an activity is not DOING it — "смотреть футбол"/"футбол по
    # тв" is exact against another watcher, but only category-related to "футбол" players.
    # It applies ONLY where doing and watching are different activities (sport, games): for
    # culture/screen watching IS the activity, so "посмотреть кино" must stay exact against
    # "кино" — it used to drop such candidates a whole tier and revoke outreach permission.
    broad = (ct[0] or cx[0])
    if broad not in ('sports', 'games'):
        return True
    return _watch_marks(t) == _watch_marks(x)

# generic filler words that two unrelated interests can share ("разговорный КЛУБ" vs "книжный КЛУБ");
# a match on ONLY such a token is not a shared interest, so they never reach _wshare comparison
_STOPTOK = {'клуб','клуба','клубы','вечер','вечером','встреча','встречи','люди','человек','вместе',
            'время','город','район','районе','новые','новых','люблю','нравится','хочу',
            'игры','игра','the','and','for','with','club','together','meet','meetup','new','fan',
            'fans','games','game','play'}

_WATCH_MARK = {'смотреть', 'посмотреть', 'просмотр', 'смотрим', 'глянуть', 'поглядеть',
               'watch', 'watching', 'watched', 'viewing', 'тв', 'tv', 'телек', 'трансляция'}

def _watch_marks(s):
    # A single BOOLEAN, not the token set: comparing raw tokens made the same interest written in
    # two languages ("watch football" vs "смотреть футбол") count as different activities, so a
    # 20-person fan cohort split into mutually invisible language islands.
    toks = set(re.findall(r"[a-zа-яё0-9]+", str(s).lower()))
    return bool(toks & _WATCH_MARK)

def _wtok(s):
    # tokens are normalised through SYNONYMS so the RU->EN bridge works word-by-word inside
    # phrases too: "выпить кофе" tokenises to {"coffee"} and meets "coffee" exactly.
    # Short tokens are dropped as noise EXCEPT real short interests — "f1", "ux", "ai", "cs"
    # are entire hobbies, and filtering purely on length made them match nobody.
    return [_norm(w) for w in re.findall(r"[a-zа-яё0-9]+", str(s).lower())
            if (len(w) >= 3 or any(ch.isdigit() for ch in w) or w in _SHORT_OK)
            and w not in _STOPTOK]

def _wshare(a, b):
    """A literal shared interest word between two OFF-TAXONOMY strings. Exact token, or a long common stem
    (>=5-char shared prefix AND near-equal length) to catch RU inflection ('технику'~'техника',
    'apple'~'apples') WITHOUT false matches like 'apple'~'application' or 'anime'~'animals'."""
    A, B = _wtok(a), _wtok(b)
    for x in A:
        for y in B:
            if x == y: return True
            if len(x) >= 5 and len(y) >= 5 and abs(len(x) - len(y)) <= 2 and x[:5] == y[:5]: return True
    return False

def topical(topics, interests):
    """Best topical tier (4 exact > 3 sub-cat > 2 broad-cat > 1 adjacent > 0 none) + matched interests.
    `matched` holds the candidate's ORIGINAL strings, not the canonical tokens: the card must say
    what the person actually wrote ("кофе", "лабубу"), not the engine's internal English form —
    reasons like "общее: coffee" for someone whose profile says "кофе" read as a different person."""
    matched = set(); best = 0
    xb = [(x, cat_of(x)) for x in interests]
    for t in topics:
        bt, st = cat_of(t)
        for x, (bx, sx) in xb:
            if same_topic(t, x): matched.add(str(x)); best = max(best, 4)
            elif st and st == sx: best = max(best, 3)
            elif bt and bt == bx: best = max(best, 2)
            elif bt and bx and bx in ADJACENCY.get(bt, []): best = max(best, 1)
            # neither side is in the taxonomy -> fall back to a literal shared interest word, so real
            # interests the vocabulary doesn't cover ("apple", "рыбалка", "labubu") still match each
            # other; the watcher/doer distinction applies here too.
            elif not bt and not bx and _wshare(t, x) and _watch_marks(t) == _watch_marks(x):
                matched.add(str(x)); best = max(best, 4)
    return best, matched

def _cat_of(tok):   # back-compat: broad category only
    return cat_of(tok)[0]

# ============================ MATCHING ENGINE (production-parity demo) ============================
# Mirrors dating/apps/api scoring: hard gates -> base tier (reciprocal/exact/adjacent/related/broad)
# -> capped modifiers -> deterministic tiebreak -> diversify. 100% deterministic; no LLM, no randomness.

ME_LATLON = (41.3874, 2.1686)          # owner location (Barcelona centre) — same as the client map
COOLDOWN_DAYS = 7                      # a candidate who declined the owner is muted this long
MAX_PENDING   = 6                      # a candidate with >= this many open proposals is "overloaded"
MIN_AGE       = 18                     # hard 18+ floor
GEO_NEAR, GEO_MID, GEO_FAR = 1.5, 3.5, 7.0   # km bands for the proximity bonus

# All weights are tunable at runtime via GET/POST /api/agent/weights (mirrors the prod admin panel).
WEIGHTS = {
    # base tiers (dominant signal)
    'tier_reciprocal': 85, 'tier_exact': 70, 'tier_exact_step': 4,
    'tier_adjacent': 55, 'tier_related': 40, 'tier_broad': 30,
    # capped modifiers
    'lang': 6, 'vibe': 5, 'mood_open': 3, 'fresh': 2,
    'geo_near': 8, 'geo_mid': 5, 'geo_far': 2,
    'fb_accept': 8, 'fb_reject': -20, 'entity': 10,
    'time_fit': 8, 'time_conflict': -6, 'role_same': 5, 'role_diff': -8,
    # tier thresholds (for the human-readable tier label) + output shaping
    'thr_t0': 85, 'thr_t1': 70, 'thr_t2': 55, 'thr_t3': 40, 'thr_t4': 30,
    'diversity_max': 3, 'top_n': 10,
}
def get_weights(): return dict(WEIGHTS)
def set_weights(patch):
    for k, v in (patch or {}).items():
        if k in WEIGHTS and isinstance(v, (int, float)) and not isinstance(v, bool): WEIGHTS[k] = v
    return dict(WEIGHTS)

# ---- server-side session store (file-backed) — mirrors the client's localStorage + holds the feedback loop ----
STORE_PATH = os.environ.get("KLEAL_STORE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "kleal_store.json"))
_STORE_LOCK = threading.Lock()
def _load_store():
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as f: return json.load(f)
    except Exception:
        return {}
SESSION = _load_store()
def _save_store():
    try:
        with open(STORE_PATH, "w", encoding="utf-8") as f: json.dump(SESSION, f)
    except Exception:
        pass
def _session(uid="me"):
    with _STORE_LOCK:
        u = SESSION.setdefault(str(uid or "me"), {})
        u.setdefault("feedback", {})   # {candidateName: 'accepted' | 'rejected'} — owner's past decisions
        u.setdefault("blocked", [])    # names the owner blocked
        u.setdefault("state", None)    # mirrored client UI state (server persistence)
        return u
# ---- proposal fatigue log (receiving policy budgets, spec §4.4/§10.1) ----
# Counts proposals RECEIVED per person; lives in matching's own kleal_store.json (no new writer
# on users.json). Feeds readiness ('busy' when over max_proposals_received_per_user_24h).
def _log_proposal(name):
    key = str(name or "").strip().lower()
    if not key:
        return
    now = time.time()
    with _STORE_LOCK:
        log = SESSION.setdefault("_proposals", {})
        log[key] = [t for t in (log.get(key) or []) if now - t < 7 * 86400] + [now]
    _save_store()

def _proposals_received_24h():
    now = time.time()
    log = SESSION.get("_proposals") or {}
    return {k: sum(1 for t in (v or []) if now - t < 86400) for k, v in log.items()}

def record_feedback(name, decision, uid="me"):
    d = str(decision or "").lower()
    if not d.startswith(("accept", "reject")): return False
    u = _session(uid); u["feedback"][str(name)] = "accepted" if d.startswith("accept") else "rejected"
    _save_store(); return True

def _haversine(a, b):
    R = 6371.0088
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2-la1)/2)**2 + math.cos(la1)*math.cos(la2)*math.sin((lo2-lo1)/2)**2
    return round(2 * R * math.asin(min(1.0, math.sqrt(h))), 2)
def _offset(latlon, km, bearing_deg):
    br = math.radians(bearing_deg)
    dlat = (km * math.cos(br)) / 110.574
    dlon = (km * math.sin(br)) / (111.320 * math.cos(math.radians(latlon[0])))
    return (round(latlon[0] + dlat, 5), round(latlon[1] + dlon, 5))
def _tiebreak(name):    # deterministic 0.0..0.9 nudge from the id hash (NOT randomness) — stable ordering
    return (int(hashlib.sha1(str(name).encode("utf-8")).hexdigest()[:6], 16) % 10) / 10.0

# named communities/venues per interest -> drives "entity affinity" (shared club/game/scene)
ENTITY_MAP = {'dota':'Dota 2 ladder','valorant':'Valorant scrims','cs':'CS ranked queue','chess':'Casa del Chess club',
    'football':'Sunday football league','basketball':'Poblenou basketball run','tennis':'Padel & tennis club',
    'coffee':'Third-wave coffee crowd','startups':'Startup Grind BCN','startup':'Startup Grind BCN',
    'running':'Morning running crew','cinema':'Arthouse film club','books':'Gràcia book club',
    'music':'Live gigs scene','rave':'Warehouse techno crew','hiking':'Weekend hiking group','art':'MACBA art walks',
    'photography':'Street photo collective','climbing':'Boulder gym crew','ai':'ML paper reading group'}

# Demo pool of 50 users (stands in for the real user DB). Deterministic -> reproducible matching + tests.
def _gen_pool():
    NAMES = ("Marc Ana Dima Sofia Leo Nina Tom Yuki Pablo Lena Ivan Marta Sam Elena Hugo Kira Noah Vera Max Lucia "
             "Oleg Sara Ben Mira Jon Alba Rus Cleo Ravi Tanya Nico Iris Omar Zoe Karl Maya Erik Nadia Luca Petra "
             "Adam Rosa Timur Gaia Feliks Anya Diego Sana Bruno Yara").split()
    SETS = [
        ["coffee","ai","startups"], ["spanish","coffee","language"], ["dota","valorant","gaming"],
        ["football","running","gym"], ["architecture","urbanism","cinema"], ["startups","networking","ai"],
        ["hiking","outdoor","travel"], ["cinema","art","music"], ["boxing","gym","running"],
        ["tennis","coffee","walk"], ["chess","board","coffee"], ["guitar","music","concert"],
        ["french","language","coffee"], ["cs","valorant","gaming"], ["museum","art","books"],
        ["yoga","walk","coffee"], ["cycling","outdoor","running"], ["poker","games","drinks"],
        ["product","design","startups"], ["dinner","drinks","talk"], ["basketball","gym","running"],
        ["photography","art","walk"], ["climbing","outdoor","hiking"], ["ml","ai","networking"],
        ["swimming","running","gym"], ["theatre","cinema","art"], ["german","language","books"],
        ["dj","music","rave"], ["startup","product","coffee"], ["urbanism","architecture","walk"],
        ["dota","gaming","chess"], ["coffee","books","cinema"], ["running","cycling","outdoor"],
    ]
    VIBES = ["calm","energetic","intellectual","creative","competitive","chill","social","introvert","extrovert"]
    LANGS = [["en"],["en","es"],["en","ru"],["es","en"],["ru","en"],["en","fr"],["es"],["en","de"],["fr","en"]]
    ROLES = ["play","watch","discuss","practise","attend"]
    DEALS = [[], ["no smokers"], ["no late nights"], [], ["no bars"], []]
    typ_of = {'sports':'sport','games':'gaming','tech':'networking','learning':'language',
              'music':'social','culture':'social','social':'social','outdoors':'sport'}
    pool = []
    for i, nm in enumerate(NAMES):
        interests = SETS[i % len(SETS)]
        km = round(0.4 + (i * 0.53) % 7.6, 1)
        lat, lon = _offset(ME_LATLON, km, (i * 137.5) % 360)     # spread on a golden-angle spiral
        km = _haversine(ME_LATLON, (lat, lon))                   # true great-circle distance
        # ~1/3 of people carry their OWN active intent -> enables reciprocal (T0) matching
        own = None
        if i % 3 == 1:
            broad = cat_of(interests[0])[0]
            own = {"type": typ_of.get(broad, 'social'), "topics": interests[:2], "role": ROLES[i % len(ROLES)]}
        ents = [ENTITY_MAP[w] for w in interests if w in ENTITY_MAP] or [interests[0].capitalize() + " scene"]
        pool.append({
            "name": nm, "interests": interests, "vibe": VIBES[i % len(VIBES)],
            "langs": LANGS[i % len(LANGS)], "lat": lat, "lon": lon, "km": km,
            "open": (i % 5 != 4), "role": ROLES[i % len(ROLES)], "datingOk": (i % 3 == 0),
            "age": (17 if i % 13 == 0 else 24 + (i * 7) % 22),   # a few minors to exercise the 18+ gate
            "verified": (i % 4 != 0),                            # ~75% verified
            "paused": (i % 11 == 0),                             # on a break -> hard-gated out
            "pending": (i * 3) % 9,                              # open proposals -> overload gate at >=6
            "blocksMe": (i % 17 == 0),                           # two-sided block-list
            "lastActiveDays": i % 6, "declinedOwnerDaysAgo": (2 if i % 23 == 0 else None),
            "intents": ([own] if own else []), "entities": ents, "dealBreakers": DEALS[i % len(DEALS)],
        })
    return pool
CANDIDATES = _gen_pool()

# The candidate pool = real users registered by onboarding, MERGED with the built-in demo pool for depth.
# IMPORTANT (was a silent, total break): onboarding writes the shared store at the repo-root users.json
# (KLEAL_USERS=/root/kleal-ms/users.json), but this file previously defaulted to services/matching/users.json
# — a different file onboarding never touched — so every registered person was invisible to the matcher and
# search ran on the 50 demo fakes only. Default now points at the SAME repo-root users.json onboarding uses.
USERS_PATH = os.environ.get(
    "KLEAL_USERS",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "users.json"))
# Match ONLY real registered users by default — surfacing demo-pool fakes (Ana/Nico/Iris...) in results
# reads as "mock users". The demo pool is still the fallback when the store is missing/empty, so a fresh
# system isn't dead. Set KLEAL_MERGE_DEMO=1 to blend the demo pool in (for a populated demo).
MERGE_DEMO = os.environ.get("KLEAL_MERGE_DEMO", "0") != "0"
_users_cache = {"mtime": None, "list": None}
def load_candidates():
    store = None
    try:
        m = os.path.getmtime(USERS_PATH)
        if _users_cache["mtime"] != m:
            with open(USERS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            lst = data.get("users") if isinstance(data, dict) else data
            _users_cache["mtime"] = m
            _users_cache["list"] = lst if isinstance(lst, list) else None
        store = _users_cache["list"]
    except Exception:
        store = None
    if not store:                                  # missing/broken/empty store -> demo pool keeps matching alive
        return CANDIDATES
    if not MERGE_DEMO:
        return store                               # opt-out: store authoritative (original behaviour)
    seen = {str(u.get("name", "")).strip().lower() for u in store}
    return list(store) + [c for c in CANDIDATES if str(c.get("name", "")).strip().lower() not in seen]

# ---------------- Matching Core v2 (spec-faithful engine; core_v2.py + ../../config/*.yaml) ----------------
# Scoring per "Kleal_Matching_Core_Final_Spec_RU_v2": feature groups with unknown/coverage, R_lcb,
# tier-as-provenance, user-facing bands. Weights/thresholds live ONLY in the sha-pinned YAML.
# Rollback for Dev A/B: KLEAL_CORE_V2=0 -> the legacy scorer below runs unchanged. A missing or
# tampered config also falls back automatically (fail-safe, spec §21.4) — see /api/agent/weights.
import core_v2 as _core
_CORE_CFG, _CORE_ERR = None, None
try:
    _CORE_CFG = _core.load_config(os.environ.get(
        "KLEAL_CORE_CONFIG",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                     "config", "Kleal_Matching_Core_Config_v2.yaml")))
except Exception as _e:
    _CORE_ERR = str(_e)
CORE_V2 = os.environ.get("KLEAL_CORE_V2", "1") != "0" and _CORE_CFG is not None

PARSE_PROMPT = '''You convert a user's free-text social request into a structured intent.
Return ONLY compact JSON (no prose, no markdown), keys:
 title  (3-5 word human label, e.g. "Coffee & urbanism chat"),
 type   (one of: dinner, sport, gaming, networking, dating, language, social, other),
 topics (array of 1-4 lowercase keywords, e.g. ["coffee","urbanism"]),
 role   (one of: play, watch, discuss, practise, attend, meet — infer from the verb; default "meet"),
 mode   (offline | online),
 format (short, e.g. "1:1 or small group"),
 time   (short, infer from text, default "Flexible"),
 place  (short, infer, default "Public places nearby").
English only.'''

def _fallback_parse(q):
    ql = (q or '').lower()
    toks = [w for w in re.findall(r"[a-zA-Z]+", ql) if len(w) >= 3]
    resolved = []                                     # only taxonomy-recognised words survive
    for t in toks:
        if cat_of(t)[0] and _norm(t) not in resolved: resolved.append(_norm(t))
    resolved = resolved[:4]
    dating = any(w in ql for w in ('date','dating','romantic','relationship','single','flirt','love'))
    topics = resolved or (['dating'] if dating else (toks[:4] or ['social']))
    tm = 'Today evening' if ('today' in ql or 'evening' in ql or 'tonight' in ql) else \
         ('Tomorrow' if 'tomorrow' in ql else ('This weekend' if 'weekend' in ql else 'Flexible'))
    role = ('play' if any(w in ql for w in ('play','teammate','squad','sparring','match')) else
            'watch' if 'watch' in ql else
            'practise' if any(w in ql for w in ('practise','practice','learn','exchange')) else
            'discuss' if any(w in ql for w in ('discuss','talk','chat','conversation','about')) else
            'attend' if any(w in ql for w in ('event','attend','concert','festival')) else 'meet')
    broad = (cat_of(resolved[0])[0] if resolved else None)
    typ = 'dating' if dating else \
          {'sports':'sport','games':'gaming','tech':'networking','learning':'language'}.get(broad, 'social')
    title = ('Date' if dating else (topics[0].capitalize() + ' meetup')) if (dating or topics) else 'New plan'
    online = any(w in ql for w in ('online','remote','voice','video','call','stream'))
    return {"title": title, "type": typ, "topics": topics or (['dating'] if dating else ['social']),
            "role": role, "mode": ('online' if online else 'offline'),
            "format": "1:1 or small group", "time": tm, "place": "Public places nearby",
            # gate parameters (owner's search scope) — sensible defaults; dating tightens age/verification
            "radiusKm": 15, "verifiedOnly": bool(dating), "minAge": (18 if dating else None), "maxAge": None,
            "requiredLanguages": [], "exactMatchRequired": False, "adjacentAllowed": True, "broadAllowed": True}

def parse_intent(q):
    q = (q or '').strip()
    if not q: return _fallback_parse('')
    try:
        cfg = MODEL_ID
        raw = llm_complete(cfg, [{"role": "system", "content": PARSE_PROMPT},
                                  {"role": "user", "content": q}], 0.2)
        obj = base._extract_json(raw)
        if isinstance(obj, dict) and obj.get('topics'):
            fb = _fallback_parse(q)
            for k, v in fb.items(): obj.setdefault(k, v)
            if not isinstance(obj.get('topics'), list) or not obj['topics']: obj['topics'] = fb['topics']
            obj['topics'] = [str(t).lower() for t in obj['topics']][:4]
            return obj
    except Exception:
        pass
    return _fallback_parse(q)

ROLE_CONFLICT = {('play', 'watch'), ('watch', 'play'), ('practise', 'watch')}
SOON_WORDS = ('today', 'tonight', 'evening', 'tomorrow')

def _num(v):
    """Numeric coercion that tolerates strings ('28') and refuses junk — a single profile with a
    string-typed age/km used to raise inside a gate and kill the search for EVERY user."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def _dist_km(intent, prof, c):
    """Searcher-relative distance. c['km'] is a pre-baked distance to a FIXED origin, so it can't
    answer 'within N km of me' — with real coordinates on both sides we measure properly, and only
    fall back to the stored figure when geo is missing."""
    a, b = _core._latlon(prof or {}), _core._latlon(c)
    if a and b:
        return _core._haversine(a, b)
    return _num(c.get('km'))

def _hard_gates(intent, c, gate_ctx, prof=None):
    """Cheap, deterministic exclusions applied BEFORE scoring. Returns (ok, reason_if_blocked).
    Gates fail CLOSED: when a value needed for a safety decision is unknown, the candidate is
    excluded rather than let through (spec §8.1)."""
    if c.get('paused'):                                            return False, 'on a break'
    # names are compared case/whitespace-insensitively everywhere else; a block list that isn't
    # would silently stop blocking after any casing difference. A record with no name at all used
    # to raise KeyError here, aborting retrieval for EVERY user with an unexplained empty slate.
    nm = str(c.get('name') or '').strip().lower()
    if not nm:                                                     return False, 'no candidate id'
    blocked = {str(b).strip().lower() for b in (gate_ctx.get('blocked') or set())}
    if nm in blocked or c.get('blocksMe'):                         return False, 'blocked'
    d = _num(c.get('declinedOwnerDaysAgo'))
    if d is not None and d < COOLDOWN_DAYS:                        return False, 'recently declined (cooldown)'
    if (_num(c.get('pending')) or 0) >= MAX_PENDING:               return False, 'too many open invites'
    age = _num(c.get('age'))
    if age is not None and age < MIN_AGE:                          return False, 'under 18'
    itype = str(intent.get('type') or '').strip().lower()          # 'Dating' must gate like 'dating'
    if itype == 'dating':
        # both sides must be adults with a known age and an explicit opt-in (spec §17)
        if not c.get('datingOk'):                                  return False, 'not open to dating'
        if age is None:                                            return False, 'age unknown (dating)'
        s_age = _num((prof or {}).get('age'))
        if s_age is None:                                          return False, 'searcher age unknown (dating)'
        if s_age < MIN_AGE:                                        return False, 'searcher under 18 (dating)'
    if intent.get('verifiedOnly') and not c.get('verified'):      return False, 'not verified'
    mn, mx = _num(intent.get('minAge')), _num(intent.get('maxAge'))
    if mn or mx:
        if age is None:                                           return False, 'age unknown'
        if mn and age < mn:                                       return False, 'below age range'
        if mx and age > mx:                                       return False, 'above age range'
    reql = {str(l)[:2].lower() for l in (intent.get('requiredLanguages') or [])}
    if reql and not reql.issubset({str(l)[:2].lower() for l in (c.get('langs') or [])}):
        return False, 'missing a required language'
    radius = _num(intent.get('radiusKm'))
    if intent.get('mode') != 'online' and radius and radius > 0:
        km = _dist_km(intent, prof, c)
        if km is not None and km > radius:                        return False, 'outside the radius'
    return True, None

GENERIC_TYPES = {'social', 'other', ''}   # too broad to count as a mutual-intent match on their own

def _reciprocal(intent, c):
    """True only if the candidate's OWN active intent shares a real topical interest (sub-category or exact).
    A bare TYPE match (both 'sport', both 'gaming'…) is NOT enough — 'sport/football' must not read as a
    mutual match for a 'sport/tennis' search, which used to hand football players the top T0 slot."""
    itop = [str(t).lower() for t in (intent.get('topics') or [])]
    for oi in (c.get('intents') or []):
        b, _ = topical(itop, [str(t).lower() for t in (oi.get('topics') or [])])
        if b >= 4:                                 # EXACT entity only: T0 means "almost the same
            return True                            # active request" — a wine intent is not a craft-
    return False                                   # beer request, испанский is not французский

def _base_tier(intent, c, topics, dating):
    """Strongest topical/intent signal -> (kind, base_score, matched_interests, reason)."""
    if _reciprocal(intent, c):
        return 'reciprocal', WEIGHTS['tier_reciprocal'], set(), 'you both want the same thing'
    best, matched = topical(topics, [str(x).lower() for x in c['interests']])
    if best == 4:
        return 'exact', WEIGHTS['tier_exact'] + WEIGHTS['tier_exact_step'] * min(max(len(matched)-1, 0), 3), \
               matched, 'shares ' + ', '.join(sorted(matched)[:2])
    if best == 3:
        return 'adjacent', WEIGHTS['tier_adjacent'], matched, 'same kind of activity'
    if best == 2:
        return 'related', WEIGHTS['tier_related'], matched, 'related interest'
    if best == 1:
        return 'broad', WEIGHTS['tier_broad'], matched, 'adjacent interest'
    if dating:                                                     # dating: opt-in gated, ranked by fit below
        return 'broad', WEIGHTS['tier_broad'], set(), 'open to dating nearby'
    return 'none', 0, set(), ''

def _tier_label(score):
    W = WEIGHTS
    return ('T0' if score >= W['thr_t0'] else 'T1' if score >= W['thr_t1'] else 'T2' if score >= W['thr_t2']
            else 'T3' if score >= W['thr_t3'] else 'T4' if score >= W['thr_t4'] else 'T5')

def _diversify(items):
    """Keep at most WEIGHTS['diversity_max'] per dominant-interest bucket; cap at top_n. Items pre-sorted desc."""
    # Focused search (1-2 buckets): DON'T cap — a "tennis" search must return all the tennis players, not 3
    # of them padded with unrelated people. Only diversify when the results genuinely span many categories.
    buckets = {it.get('bucket') or 'other' for it in items}
    cap = WEIGHTS['diversity_max'] if len(buckets) > 2 else WEIGHTS['top_n']
    seen, out = {}, []
    for it in items:
        b = it.get('bucket') or 'other'
        if seen.get(b, 0) >= cap:
            continue
        seen[b] = seen.get(b, 0) + 1
        out.append(it)
        if len(out) >= WEIGHTS['top_n']:
            break
    return out

def match_candidates_legacy(intent, prof, ctx=None):
    W = WEIGHTS
    ctx = ctx or {}
    sess = _session(ctx.get('uid', 'me'))
    feedback = dict(sess.get('feedback') or {}); feedback.update(ctx.get('feedback') or {})
    gate_ctx = {'feedback': feedback,
                'blocked': set(sess.get('blocked') or []) | set(ctx.get('blocked') or [])}
    topics   = [str(t).lower() for t in (intent.get('topics') or [])]
    irole    = (intent.get('role') or 'meet').lower()
    my_langs = {str(l)[:2].lower() for l in ((prof.get('languages') or {}).get('comfortable') or [])}
    my_vibe  = str(prof.get('vibe') or '').lower()
    dating   = (intent.get('type') or '').lower() == 'dating'
    soon     = any(w in str(intent.get('time', '')).lower() for w in SOON_WORDS)
    exactReq = bool(intent.get('exactMatchRequired'))
    adjOk    = intent.get('adjacentAllowed', True)
    broadOk  = intent.get('broadAllowed', True)
    # the searcher must never match themselves — identify them by name (or uid) and skip that candidate
    self_name = str(ctx.get('self') or prof.get('name') or ctx.get('uid') or '').strip().lower()
    out = []
    for c in load_candidates():
        if self_name and str(c.get('name', '')).strip().lower() == self_name:
            continue
        # ── 1. HARD GATES ──
        ok, _why = _hard_gates(intent, c, gate_ctx, prof)
        if not ok:
            continue
        # ── 2. BASE TIER (reciprocal / exact / adjacent / related / broad) + search-breadth gates ──
        kind, score, matched, tier_reason = _base_tier(intent, c, topics, dating)
        if kind == 'none':
            continue                                              # never propose unrelated people
        if exactReq and kind not in ('reciprocal', 'exact'):
            continue
        if kind == 'adjacent' and not adjOk:
            continue
        if kind in ('related', 'broad') and not broadOk:
            continue
        reasons = [tier_reason]
        # ── 3. CAPPED MODIFIERS (base dominates; each just nudges) ──
        crole = (c.get('role') or '').lower()
        if irole != 'meet' and crole:
            if irole == crole:
                score += W['role_same']; reasons.append('same role (%s)' % irole)
            elif (irole, crole) in ROLE_CONFLICT:
                score += W['role_diff']; reasons.append('different role (%s)' % crole)
        if my_vibe and my_vibe == (c.get('vibe') or '').lower():
            score += W['vibe']; reasons.append('similar vibe')
        if my_langs and (my_langs & {str(l)[:2].lower() for l in c['langs']}):
            score += W['lang']; reasons.append('common language')
        if c.get('open'):
            score += W['mood_open']; reasons.append('open to meet')
        if soon:
            score += (W['time_fit'] if c.get('open') else W['time_conflict'])
            reasons.append('suits your time' if c.get('open') else 'may not be free then')
        if (c.get('lastActiveDays') or 0) <= 3:
            score += W['fresh']; reasons.append('recently active')
        # entity affinity — shared named club/game/scene
        ents = ' | '.join(str(e).lower() for e in (c.get('entities') or []))
        if ents and any(t in ents for t in topics):
            score += W['entity']; reasons.append('shares a community')
        # geo
        km = c['km']
        if km <= GEO_NEAR:
            score += W['geo_near']; reasons.append('very close (%.1f km)' % km)
        elif km <= GEO_MID:
            score += W['geo_mid']; reasons.append('%.1f km away' % km)
        elif km <= GEO_FAR:
            score += W['geo_far']
        # feedback loop — learn from the owner's past decisions
        fb = feedback.get(c['name'])
        if fb == 'accepted':
            score += W['fb_accept']; reasons.append('you accepted them before')
        elif fb == 'rejected':
            score += W['fb_reject']; reasons.append('you passed on them before')
        # ── 4. DETERMINISTIC TIEBREAK + CLAMP ──
        score = round(max(0.0, min(100.0, score + _tiebreak(c['name']))), 1)
        # dominant-interest bucket (for diversify)
        bcat = (cat_of(sorted(matched)[0])[0] if matched else None) or cat_of((c['interests'] or ['x'])[0])[0] or 'other'
        tier = _tier_label(score)
        agree = bool(c.get('open') and score >= W['thr_t2'])
        note = ('Agent agreed — ' + reasons[0]) if agree else \
               ('Agent: not free today' if not c.get('open') else 'Agent: fit too weak')
        out.append({"name": c['name'], "score": score, "tier": tier, "kind": kind, "km": km,
                    "vibe": c['vibe'], "open": c['open'], "verified": c.get('verified'), "age": c.get('age'),
                    "interests": c['interests'], "role": c.get('role'), "dealBreakers": c.get('dealBreakers'),
                    "reasons": reasons, "agree": agree, "note": note, "bucket": bcat})
    out.sort(key=lambda x: (-x['score'], x['name']))
    return _diversify(out)

def match_candidates(intent, prof, ctx=None):
    """Entry point. Policy hard gates run HERE (scoring only after ALLOW — spec §8), then Core v2
    scores the eligible pool. KLEAL_CORE_V2=0 or an invalid config -> legacy scorer above, unchanged.
    The response is a superset of the legacy card contract (name/score/tier/reasons/agree/note/...)."""
    if not CORE_V2:
        return match_candidates_legacy(intent, prof, ctx)
    ctx = ctx or {}
    sess = _session(ctx.get('uid', 'me'))
    gate_ctx = {'feedback': dict(sess.get('feedback') or {}),
                'blocked': set(sess.get('blocked') or []) | set(ctx.get('blocked') or [])}
    self_name = str(ctx.get('self') or (prof or {}).get('name') or ctx.get('uid') or '').strip().lower()
    eligible = []
    for c in load_candidates():
        if self_name and str(c.get('name', '')).strip().lower() == self_name:
            continue                                       # the searcher never matches themselves
        ok, _why = _hard_gates(intent, c, gate_ctx, prof)
        if ok:
            eligible.append(c)
    H = {'topical': topical, 'cat_of': cat_of, 'reciprocal': _reciprocal, 'role_conflict': ROLE_CONFLICT}
    ctx = dict(ctx)
    ctx.setdefault('now', time.time())                     # pinnable for deterministic replay
    ctx.setdefault('received24', _proposals_received_24h())  # proposal-fatigue counts -> readiness
    slate, _meta = _core.search(intent, prof or {}, ctx, eligible, H, _CORE_CFG)
    return slate

def _online_fallback(intent):
    """When 0 offline candidates: offer to go live + ways to broaden — so the user never hits a dead end."""
    topics = ', '.join(intent.get('topics') or []) or 'this'
    return {
        "room": {"title": "Live room: " + intent.get('title', 'meet'),
                 "options": [{"id": "voice", "label": "Start a voice room"},
                             {"id": "watch", "label": "Watch together online"}]},
        "suggestions": [
            {"id": "inexact",  "label": "Allow less-exact matches"},
            {"id": "adjacent", "label": "Include adjacent topics"},
            {"id": "radius",   "label": "Widen the distance"},
            {"id": "wait",     "label": "Keep searching in the background"},
        ],
        "note": "No offline matches for %s right now — go live, or broaden the search." % topics,
    }

def agent_plan(query, prof, ctx=None, override=None):
    intent = parse_intent(query)
    if isinstance(override, dict):                 # broaden the search scope (radius / inexact / adjacent)
        for k, v in override.items():
            if k in ('radiusKm', 'verifiedOnly', 'minAge', 'maxAge', 'requiredLanguages', 'mode',
                     'exactMatchRequired', 'adjacentAllowed', 'broadAllowed'):
                intent[k] = v
    cands = match_candidates(intent, prof or {}, ctx or {})
    res = {"intent": intent, "candidates": cands}
    if not cands:
        res["fallback"] = _online_fallback(intent)
    return res

_CYR_RE = re.compile(r"[\u0430-\u044f\u0410-\u042f\u0451\u0401]")

# ---- real proposal delivery (was missing entirely) -------------------------------------------------
# Sending a request used to be local: the client posted feedback, asked an LLM to ROLE-PLAY the
# recipient's agent, and showed "мы отправили твой запрос <name>" plus a mutual match based on that
# simulation. Nothing ever reached the other account — logging in as the recipient showed no request.
# These endpoints are the actual delivery: a proposal is stored, the recipient reads and answers it,
# and the sender sees the real answer instead of a generated one.
def _norm_name(n):
    return str(n or "").strip().lower()

def _requests():
    return SESSION.setdefault("_requests", [])

def propose(frm, to, intent, note):
    frm, to = str(frm or "").strip(), str(to or "").strip()
    if not frm or not to or _norm_name(frm) == _norm_name(to):
        return {"ok": False, "error": "sender and recipient required and must differ"}
    now = time.time()
    with _STORE_LOCK:
        rs = _requests()
        # one open proposal per pair per direction — re-sending updates it rather than stacking
        for r in rs:
            if (_norm_name(r.get("from")) == _norm_name(frm) and _norm_name(r.get("to")) == _norm_name(to)
                    and r.get("status") == "pending"):
                r.update({"intent": intent or {}, "note": str(note or "")[:400], "updated": now})
                _save_store()
                return {"ok": True, "id": r["id"], "status": "pending", "resent": True}
        rid = "rq_%d_%s" % (int(now * 1000), hashlib.sha1((frm + to).encode("utf-8")).hexdigest()[:6])
        rs.append({"id": rid, "from": frm, "to": to, "intent": intent or {},
                   "note": str(note or "")[:400], "status": "pending", "created": now, "updated": now})
    _save_store()
    _log_proposal(to)                       # feeds the receiving-policy budget, spec 4.4
    return {"ok": True, "id": rid, "status": "pending"}

def inbox(self_name):
    me = _norm_name(self_name)
    if not me:
        return []
    out = [dict(r) for r in _requests() if _norm_name(r.get("to")) == me]
    out.sort(key=lambda r: -(r.get("updated") or 0))
    return out[:50]

def outbox(self_name):
    me = _norm_name(self_name)
    if not me:
        return []
    out = [dict(r) for r in _requests() if _norm_name(r.get("from")) == me]
    out.sort(key=lambda r: -(r.get("updated") or 0))
    return out[:50]

def respond(rid, decision, who):
    dec = "accepted" if str(decision).lower() in ("accept", "accepted", "yes") else "declined"
    with _STORE_LOCK:
        for r in _requests():
            if r.get("id") == rid:
                # only the recipient may answer — a sender must not accept on the other person's behalf
                if who and _norm_name(who) != _norm_name(r.get("to")):
                    return {"ok": False, "error": "only the recipient can answer this request"}
                r["status"] = dec
                r["updated"] = time.time()
                _save_store()
                return {"ok": True, "id": rid, "status": dec}
    return {"ok": False, "error": "not found"}

# ---- Agent-to-agent intro (Phase 2): the candidate's agent confirms + an icebreaker opener ----
INTRO_PROMPT = '''You are the AI agent of user B. User A wants to meet for the activity below, and B's agent has agreed.
Write (a) as B's agent, a warm one-sentence confirmation to A's agent, and (b) a friendly one-sentence icebreaker
opener B could send A. Return ONLY JSON: {"reply":"...","opener":"..."}. Lively, no markdown.
LANGUAGE: write BOTH "reply" and "opener" in __LANG__. The opener is shown to a user in that language,
so an English line inside a Russian interface reads as someone else's words.'''
def agent_intro(intent, cand):
    topics = ', '.join(intent.get('topics') or intent.get('tags') or []) or 'this'
    ctx = 'Activity: %s (%s). Person B interests: %s. Vibe: %s.' % (
        intent.get('title', 'a meetup'), topics, ', '.join(cand.get('interests') or []), cand.get('vibe', ''))
    lang = "ru" if _CYR_RE.search("%s %s" % (intent.get("title", ""), " ".join(intent.get("topics") or []))) \
        or str(intent.get("lang", "")).lower() == "ru" else "en"
    prompt = INTRO_PROMPT.replace("__LANG__", "Russian" if lang == "ru" else "English")
    try:
        cfg = MODEL_ID
        raw = llm_complete(cfg, [{"role": "system", "content": prompt}, {"role": "user", "content": ctx}], 0.6)
        obj = base._extract_json(raw)
        if isinstance(obj, dict) and obj.get('opener'):
            return {"reply": str(obj.get('reply', ''))[:200], "opener": str(obj.get('opener', ''))[:200]}
    except Exception:
        pass
    if lang == "ru":
        return {"reply": "Мой пользователь не против — со стороны расписания всё сходится.",
                "opener": "Привет! Похоже, нам обоим интересно: " + topics + ". Давай что-нибудь придумаем?"}
    return {"reply": "My user is up for it — it works on their side.",
            "opener": "Hey! Looks like we both like " + topics + " — want to make a plan?"}

# ---- Agent-to-agent NEGOTIATION (LLM): the candidate's agent decides accept/reject, with a reason ----
# B's AVAILABILITY is already settled by the readiness engine before this call — only reachable
# people get here. Asking the model about it made it reject on "the meeting is not today" for a
# perfectly ordinary "tomorrow at 21" plan, which is how half the declines were being produced.
NEGOTIATE_PROMPT = '''You are the AI agent of user B. User A proposes a plan and wants to meet.
Decide, on B's behalf, whether B accepts.

B's availability has ALREADY been verified by the system — B is reachable and the proposed time is
within B's window. NEVER reject because of timing, dates, "not today", or scheduling: that is not
your call. A future date (tomorrow, this weekend) is perfectly normal.

Judge ONLY:
- does the activity genuinely fit B's interests?
- would it break one of B's stated deal-breakers (if so -> reject)?
Accept when the activity is a reasonable fit. Reject only for a real mismatch of interest or a
deal-breaker, and say which one.

Return ONLY JSON (no prose): {"decision":"accept"|"reject","reason":"one short sentence why","reply":"one lively sentence from B's agent to A's agent, or null if reject"}.'''

def negotiate_one(intent, cand):
    topics = ', '.join(intent.get('topics') or intent.get('tags') or []) or 'this'
    a = 'INTENT FROM A: %s. Topics: %s. Time: %s. Place: %s. Format: %s.' % (
        intent.get('title', ''), topics, intent.get('time', ''), intent.get('place', ''), intent.get('format', ''))
    # No availability field at all: the readiness engine already cleared it, and mentioning "today"
    # invited the model to decline anything scheduled for another day.
    b = 'USER B: interests %s; vibe %s; deal-breakers: %s.' % (
        ', '.join(cand.get('interests') or []) or 'unknown', cand.get('vibe', ''),
        ', '.join(cand.get('dealBreakers') or []) or 'none')
    try:
        cfg = MODEL_ID
        raw = llm_complete(cfg, [{"role": "system", "content": NEGOTIATE_PROMPT},
                                  {"role": "user", "content": a + "\n" + b}], 0.4)
        o = base._extract_json(raw)
        if isinstance(o, dict) and o.get('decision') in ('accept', 'reject'):
            acc = o['decision'] == 'accept'
            return {"agree": acc, "reason": str(o.get('reason', ''))[:160],
                    "reply": (str(o.get('reply', ''))[:200] if acc and o.get('reply') else None), "decided": True}
    except Exception:
        pass
    # graceful fallback when the model is unavailable: availability was already settled upstream,
    # so the only question left is whether the fit is strong enough
    acc = cand.get('score', 0) >= 45
    return {"agree": acc, "reason": ('good fit for this plan' if acc else 'fit is a bit weak'),
            "reply": None, "decided": False}

def _normalize_intent(raw):
    """Accept the shapes clients actually send. The profile UI posts its CARD object, where the
    topics live in `tags` and the real intent is nested under `intent` — so the engine saw an
    intent with NO topics, tiered everyone as T5 ("no meaningful topical overlap") and declined
    the whole slate. Be liberal here: a missing topic list is never a legitimate search."""
    if not isinstance(raw, dict):
        return {}
    it = dict(raw)
    inner = raw.get("intent")
    if isinstance(inner, dict):                       # card wrapper -> use the real intent
        merged = dict(inner)
        for k, v in it.items():
            if k != "intent" and k not in merged:
                merged[k] = v
        it = merged
    if not it.get("topics"):
        for alt in ("tags", "keywords"):
            v = it.get(alt)
            if isinstance(v, list) and v:
                it["topics"] = [str(x) for x in v]
                break
    return it

def _outreach_ok(intent, c, prof=None, ctx=None):
    """Full PERSONAL-outreach permission for the send path — the same verdict the slate computes,
    not a subset of it. It used to check only tier/consent, so a candidate the slate had marked
    can_outreach=False (fit below the domain's outreach_min_lcb / coverage, or not open_now) still
    received a proposal. Now the whole decision is delegated to the engine (spec §9.6 + §10.1)."""
    if not CORE_V2:
        return True, ""
    Hh = {'topical': topical, 'cat_of': cat_of, 'reciprocal': _reciprocal, 'role_conflict': ROLE_CONFLICT}
    tr = _core.explain(intent, prof or {}, ctx or {}, c, Hh, _CORE_CFG)
    if tr.get("can_outreach"):
        return True, ""
    if not tr.get("shown"):
        # user-facing copy: the trace's drop_reason is engine-speak ("no meaningful topical
        # overlap (T5) — never proposed") and used to be printed verbatim on the card
        return False, ("no shared interest with this request" if tr.get("tier") == "T5"
                       else "not a match for this request")
    tier = tr.get("tier")
    if tier not in ("T0", "T1") and not (tier == "T2" and intent.get("broadConsent")):
        return False, "discovery only — needs broad consent for this match"
    if tr.get("readiness") != "open_now":
        return False, _core.READINESS_LABELS.get(tr.get("readiness"), ("", "not reachable"))[1]
    return False, "fit below the outreach threshold for this domain"

def _negotiate_precheck(intent, cands, now_ts=None, prof=None):
    """Receiving-policy AND eligibility enforcement BEFORE any proposal goes out (spec §8.2: policy
    revalidation immediately before sending; §23.2 #12: no proposal without a receiving-policy check).
    /api/agent/negotiate accepts client-supplied candidates verbatim, so each is re-resolved against
    the LIVE store, re-run through the eligibility hard gates + the tier/consent outreach gate, then
    readiness is computed and the parallel wave capped from config (default 2, urgent 3).
    Returns (to_send, decided_without_sending)."""
    now_ts = now_ts or time.time()
    store = {str(u.get('name', '')).strip().lower(): u for u in load_candidates()}
    received = _proposals_received_24h()
    _sess = _session("me")
    gate_ctx = {'feedback': dict(_sess.get('feedback') or {}), 'blocked': set(_sess.get('blocked') or [])}
    out_cfg = ((_CORE_CFG or {}).get('outreach') or {})
    soon = any(w in str(intent.get('time', '')).lower() for w in SOON_WORDS)
    cap = int(out_cfg.get('urgent_same_day_parallel_proposals' if soon else
                          'default_parallel_proposals') or (3 if soon else 2))
    to_send, decided, sent = [], [], 0
    for c in cands:
        nm = str(c.get('name', '')).strip().lower()
        live = store.get(nm, c)
        # §8.2 revalidation at the SEND boundary — never trust the caller's candidate list.
        if not (nm or c.get('name')):
            decided.append(dict(c, agree=False, decided=True, readiness="blocked",
                                reason="not eligible: no candidate id", reply=None)); continue
        live = dict(live); live['name'] = live.get('name') or c.get('name') or ''
        ok, why = _hard_gates(intent, live, gate_ctx, prof)    # block / age / dating / language / radius…
        if not ok:
            decided.append(dict(c, agree=False, decided=True, readiness="blocked",
                                reason="not eligible: %s" % why, reply=None)); continue
        # full outreach permission (tier/consent AND readiness AND the domain's lcb/coverage
        # thresholds) — identical to what the slate showed, so the send path can't be more generous
        allowed, deny_why = _outreach_ok(intent, live, prof, {"now": now_ts, "received24": received})
        if not allowed:
            decided.append(dict(c, agree=False, decided=True, readiness="discovery_only",
                                reason=deny_why, reply=None)); continue
        if CORE_V2:
            domain = _core.infer_domain(intent, cat_of)
            rdy = _core.readiness_state(live, domain, now_ts, _CORE_CFG, received.get(nm, 0))
        else:
            rdy = 'open_now' if live.get('open') else ('paused' if live.get('paused') else 'busy')
        if rdy != 'open_now':
            label = _core.READINESS_LABELS.get(rdy, (rdy, rdy)) if CORE_V2 else (rdy, rdy)
            d = dict(c); d.update({"agree": False, "decided": True, "readiness": rdy,
                                   "reason": label[1], "reply": None})
            decided.append(d)
            continue
        if sent >= cap:
            d = dict(c); d.update({"agree": False, "decided": True, "readiness": rdy,
                                   "reason": "queued for the next wave (parallel-proposal cap)",
                                   "reply": None})
            decided.append(d)
            continue
        sent += 1
        # the negotiating agent must reason over the LIVE profile, not the client's stale copy —
        # fill interests/vibe/open/dealBreakers from the store when the client didn't send them
        merged = dict(c, readiness=rdy)
        for k in ("interests", "vibe", "open", "dealBreakers"):
            if merged.get(k) is None and live.get(k) is not None:
                merged[k] = live[k]
        to_send.append(merged)
    return to_send, decided

def negotiate_candidates(intent, cands, prof=None):
    top = cands[:5]
    to_send, decided = _negotiate_precheck(intent, top, prof=prof)
    for c in to_send:
        _log_proposal(c.get('name'))                   # a real proposal reaches this person's agent
    def work(c):
        v = negotiate_one(intent, c); c = dict(c); c.update(v); return c
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            done = list(ex.map(work, to_send))
    except Exception:
        done = [dict(c, **negotiate_one(intent, c)) for c in to_send]
    by = {str(x.get('name', '')).strip().lower(): x for x in done + decided}
    return [by.get(str(c.get('name', '')).strip().lower(), c) for c in top]

# ---------------------------------------------------------------- Explore: public plans near the owner
# The client's Explore map used to hard-code 5 fake plans. Serve real ones instead: every candidate who
# carries an OPEN own-intent becomes a public plan (title from ENTITY_MAP, distance from their geo). Draws
# from load_candidates() so it honours the store, and returns [] when nobody is posting — the client then
# shows an empty state instead of invented pins.
_EXPLORE_WHEN = ("Today 18:00", "Tonight 21:00", "Tomorrow 08:00", "Tomorrow 19:00", "Sat 11:00",
                 "Sun 10:00", "Wed 17:00", "Fri 20:00", "Thu 20:00", "Sat 17:00")


def explore_plans(limit=12, self_name=""):
    sn = str(self_name or "").strip().lower()
    users = [c for c in load_candidates() if not (sn and str(c.get("name", "")).strip().lower() == sn)]
    # Explore shows ONLY real registered users (source == "onboarding") — a plan from their own-intent, or,
    # if none, their top interest. Demo pool users are NEVER surfaced here (they exist only so matching has a
    # non-empty pool to rank against); when there are no real users, the client shows an empty state.
    ordered = [c for c in users if c.get("source") == "onboarding"]
    out = []
    for i, c in enumerate(ordered):
        # paused (incl. receiving.status/paused_until) leaves retrieval entirely (spec §10.1);
        # busy/quiet-hours people STAY discoverable — receiving policy blocks proposals, not visibility
        if _core.is_paused(c) or c.get("open") is False:
            continue
        oi = (c.get("intents") or [None])[0]
        topics = [str(t).lower() for t in ((oi.get("topics") if oi else None) or c.get("interests") or []) if t][:3]
        if not topics:
            continue
        lat, lon, km = c.get("lat"), c.get("lon"), c.get("km")
        # Do NOT invent a position. This used to spiral users without coordinates around the map centre
        # at (i * 137.5)°, which put pins in the Mediterranean and — worse — drew people whose area says
        # "Москва" as a pin 2.6 km from Barcelona. A pin asserts "this person is here"; we only know a
        # distance to some origin, not a direction. lat/lon stay null and the client omits the pin while
        # still listing the plan, with `area` shown so the user can see where they actually are.
        if lat is None or lon is None:
            lat = lon = None
        out.append({"title": ENTITY_MAP.get(topics[0]) or (topics[0].capitalize() + " meetup"),
                    "who": c.get("name") or "Someone", "topics": topics, "role": (oi or {}).get("role") or "meet",
                    "when": _EXPLORE_WHEN[i % len(_EXPLORE_WHEN)],
                    "dist": (round(float(km), 1) if km is not None else None),
                    "area": c.get("area") or "",
                    "lat": lat, "lon": lon, "verified": bool(c.get("verified"))})
    out.sort(key=lambda p: (p["dist"] is None, p["dist"] or 0))
    return out[:limit]

# ---------------------------------------------------------------- HTTP dispatcher (matching only)
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/agent/weights":
            send_json(self, 200, {"weights": get_weights(),
                                  "core": {"enabled": CORE_V2,
                                           "config_version": (_CORE_CFG or {}).get("config_version"),
                                           "config_sha": ((_CORE_CFG or {}).get("_sha256") or "")[:12],
                                           "error": _CORE_ERR}})
        elif self.path == "/api/agent/load":
            send_json(self, 200, {"state": _session("me").get("state")})
        elif self.path == "/api/agent/pool":
            c = load_candidates()
            send_json(self, 200, {"count": len(c), "fromStore": _users_cache["list"] is not None, "users": c})
        elif self.path.split("?")[0] in ("/api/agent/inbox", "/api/agent/outbox"):
            q = dict(kv.split("=", 1) for kv in self.path.split("?", 1)[-1].split("&") if "=" in kv) if "?" in self.path else {}
            from urllib.parse import unquote
            who = unquote(q.get("self", ""))
            fn = inbox if self.path.split("?")[0].endswith("inbox") else outbox
            send_json(self, 200, {"requests": fn(who)})
        elif self.path.split("?")[0] == "/api/agent/explore":
            q = dict(kv.split("=", 1) for kv in self.path.split("?", 1)[-1].split("&") if "=" in kv) if "?" in self.path else {}
            from urllib.parse import unquote
            send_json(self, 200, {"plans": explore_plans(self_name=unquote(q.get("self", "")))})
        elif self.path == "/":
            send_json(self, 200, {"service": "matching", "ok": True})
        else:
            send_json(self, 404, {})

    def do_POST(self):
        body = read_json(self)
        p = self.path
        if p == "/api/agent/plan":
            q = str(body.get("query") or "")
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            ctx = body.get("ctx") if isinstance(body.get("ctx"), dict) else {}
            override = body.get("override") if isinstance(body.get("override"), dict) else None
            try:
                send_json(self, 200, agent_plan(q, prof, ctx, override))
            except Exception as e:
                send_json(self, 200, {"intent": _fallback_parse(q), "candidates": [], "error": str(e)[:200]})
        elif p == "/api/agent/match":
            # structured entry: caller (e.g. the buddy agent) already assembled the intent/signals -> skip LLM parse
            intent = _normalize_intent(body.get("intent"))
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            ctx = body.get("ctx") if isinstance(body.get("ctx"), dict) else {}
            try:
                cands = match_candidates(intent, prof, ctx)
                res = {"intent": intent, "candidates": cands}
                if not cands:
                    res["fallback"] = _online_fallback(intent)
                send_json(self, 200, res)
            except Exception as e:
                send_json(self, 200, {"intent": intent, "candidates": [], "error": str(e)[:200]})
        elif p == "/api/agent/explain":
            # Decision trace for ONE pair (spec §21.3) — powers the admin Matching lab. Read-only:
            # runs the same gates + scoring as /match but reports WHY a candidate was dropped.
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            ctx = body.get("ctx") if isinstance(body.get("ctx"), dict) else {}
            who = str(body.get("candidate") or "").strip().lower()
            try:
                cand = next((c for c in load_candidates()
                             if str(c.get("name", "")).strip().lower() == who), None)
                if cand is None:
                    send_json(self, 200, {"ok": False, "error": "candidate not found in store"})
                elif not CORE_V2:
                    send_json(self, 200, {"ok": False, "error": "core v2 disabled (KLEAL_CORE_V2=0)"})
                else:
                    sess = _session(ctx.get("uid", "me"))
                    gate_ctx = {"feedback": dict(sess.get("feedback") or {}),
                                "blocked": set(sess.get("blocked") or []) | set(ctx.get("blocked") or [])}
                    self_name = str(ctx.get("self") or prof.get("name") or "").strip().lower()
                    ctx2 = dict(ctx)
                    ctx2.setdefault("received24", _proposals_received_24h())
                    Hh = {"topical": topical, "cat_of": cat_of, "reciprocal": _reciprocal,
                          "role_conflict": ROLE_CONFLICT}
                    if self_name and str(cand.get("name", "")).strip().lower() == self_name:
                        send_json(self, 200, {"ok": True, "trace": {
                            "name": cand.get("name"), "shown": False, "steps": [
                                {"step": "self-match guard", "ok": False,
                                 "detail": "the searcher is never matched to themselves"}],
                            "drop_reason": "self-match: searcher == candidate"}})
                    else:
                        ok, why = _hard_gates(intent, cand, gate_ctx, prof)
                        if not ok:
                            send_json(self, 200, {"ok": True, "trace": {
                                "name": cand.get("name"), "shown": False, "steps": [
                                    {"step": "eligibility hard gates", "ok": False, "detail": why}],
                                "drop_reason": "blocked by policy: %s" % why}})
                        else:
                            tr = _core.explain(intent, prof, ctx2, cand, Hh, _CORE_CFG)
                            tr["steps"].insert(0, {"step": "eligibility hard gates", "ok": True,
                                                   "detail": "ALLOW"})
                            send_json(self, 200, {"ok": True, "trace": tr})
            except Exception as e:
                send_json(self, 200, {"ok": False, "error": str(e)[:200]})
        elif p == "/api/agent/feedback":
            ok = record_feedback(body.get("name"), body.get("decision"), body.get("uid", "me"))
            send_json(self, 200, {"ok": bool(ok), "feedback": _session("me").get("feedback")})
        elif p == "/api/agent/weights":
            send_json(self, 200, {"weights": set_weights(body.get("weights") if isinstance(body.get("weights"), dict) else body)})
        elif p == "/api/agent/save":
            u = _session("me"); u["state"] = body.get("state"); _save_store()
            send_json(self, 200, {"ok": True})
        elif p == "/api/agent/intro":
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            cand = body.get("candidate") if isinstance(body.get("candidate"), dict) else {}
            try:
                send_json(self, 200, agent_intro(intent, cand))
            except Exception as e:
                send_json(self, 200, {"reply": "", "opener": "Hey! Want to make a plan?", "error": str(e)[:200]})
        elif p == "/api/agent/propose":
            send_json(self, 200, propose(body.get("from"), body.get("to"),
                                         body.get("intent") or {}, body.get("note")))
        elif p == "/api/agent/respond":
            send_json(self, 200, respond(body.get("id"), body.get("decision"), body.get("self")))
        elif p == "/api/agent/negotiate":
            intent = _normalize_intent(body.get("intent"))
            cands = body.get("candidates") if isinstance(body.get("candidates"), list) else []
            try:
                prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
                send_json(self, 200, {"candidates": negotiate_candidates(intent, cands, prof)})
            except Exception as e:
                send_json(self, 200, {"candidates": cands, "error": str(e)[:200]})
        else:
            send_json(self, 404, {})

    def log_message(self, *a):
        pass


class _Server(ThreadingHTTPServer):
    daemon_threads = True          # don't block shutdown on in-flight requests
    request_queue_size = 128       # deeper listen backlog — a burst of concurrent clients no longer
    allow_reuse_address = True     # gets connection-reset (fuzz saw 12/90 resets at queue_size=5)

if __name__ == "__main__":
    print("Kleal matching-service on http://127.0.0.1:%d  (LLM via llm-service)" % PORT)
    _Server(("127.0.0.1", PORT), H).serve_forever()
