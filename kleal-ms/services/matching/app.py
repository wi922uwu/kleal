# -*- coding: utf-8 -*-
# Kleal matching-service — the buddy agent (intent parse -> ranked candidates -> agent negotiation).
# Carved from the pre-split monolith kleal_v2.py (matching half, lines 304-831). Serves /api/agent/*.
# Talks to llm-service over HTTP for parse/intro/negotiate; holds NO model keys. Owner: Dev B.
# Endpoint names are FROZEN — the profile-service frontend hard-codes them (see ../../shared/contracts.md).
import os, sys, json, re, threading, concurrent.futures, math, hashlib, time, copy, contextlib
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "..", "..", "shared"), os.path.join(_HERE, "shared")):
    if os.path.isdir(_p) and _p not in sys.path: sys.path.insert(0, _p)
# ...and THIS directory ahead of shared/, always. The kleal_* engine modules below live here; only
# kleal_lib is genuinely shared. An older layout kept all of them in shared/, and a deploy that
# restored that layout left stale copies behind — which, with shared/ first on the path, SHADOWED
# every module in this directory. The service then ran a mix of new dispatcher and old engine:
# matching answered with a group ceiling of 8 that no file in this folder still contained, and the
# config-pin check failed against a config it was never meant to read. A local module must win.
sys.path.insert(0, _HERE)
import kleal_lib as base                      # keyless shared helpers (uses base._extract_json)
import kleal_contracts as kc                  # §4 canonical data contracts (builders/validators; keyless)
import kleal_intent as ki                     # §5 intent compiler + clarification policy (keyless, LLM-free)
import kleal_taxonomy as kt                   # §6 governed taxonomy layer (read-only narrator; keyless, no FS at import)
import kleal_completion as kcf                # §10.2 completion factors (transparent operational signals; keyless)
import kleal_ml_boundary as kmlb              # §10.3 ML-migration boundary manifest (declarative; keyless)
import kleal_protocol as kp                   # §13 typed agent protocol (actions/envelope/waves/guards; LLM-free)
import kleal_states as ks                      # §14 transaction state machines + race protection (keyless, LLM-free)
import kleal_groups as kg                       # §15 group formation core (PILOT-DISABLED scaffolding; keyless, LLM-free)
import kleal_candidates as kct                  # §16 events/rooms/venues candidate types (PILOT-DISABLED; keyless, LLM-free)
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
  'sports':  {'team':['football','soccer','basketball','volleyball','handball','rugby','cricket','hockey','baseball','futsal','ultimate','waterpolo'],
              'racket':['tennis','padel','badminton','squash','pingpong','tabletennis','pickleball','racquetball'],
              'endurance':['running','jogging','cycling','biking','swimming','triathlon','marathon','rowing','spinning','hyrox','duathlon'],
              'strength':['gym','fitness','workout','crossfit','boxing','mma','climbing','bouldering','calisthenics','powerlifting','weightlifting','kettlebell','kickboxing','judo','karate','bjj','wrestling','muaythai','fencing'],
              'mindbody':['yoga','pilates','stretching','meditation','breathwork','taichi','qigong']},
  'social':  {'coffee':['coffee','tea','brunch','cafe','matcha','espresso'],
              'dining':['dinner','lunch','food','restaurant','cooking'],
              'nightlife':['bar','drinks','pub','beer','wine','party','club','clubbing','cocktails','mezcal','sake'],
              'casual':['walk','walking','stroll','hang','hangout','chill','talk','chat','park','terrace'],
              'foodie':['baking','bbq','streetfood','vegan','vegetarian','tapas','sushi','foodie','picnic','ramen','pizza','pasta'],
              'wellness':['spa','sauna','wellness','selfcare','massage'],
              'community':['volunteering','charity','meetup','community','activism','sustainability'],
              'pets':['dogs','dog','cats','pets','dogwalk'],
              'family':['parenting','kids','playdate','family','mums']},
  'games':   {'esports':['dota','valorant','cs','league','apex','fortnite','fifa','overwatch','gaming','rocketleague','r6','rainbow6','starcraft','hearthstone','tekken','smash','cod','warzone'],
              'tabletop':['chess','boardgames','poker','cards','dnd','tabletop','catan','monopoly','risk','magic','mtg','warhammer','ttrpg','trivia','quiz','mahjong','backgammon','escaperoom'],
              'console':['playstation','xbox','nintendo','switch','console','ps5'],
              'pc':['minecraft','roblox','valheim','terraria','stardew'],
              'mobile':['mobile','clashroyale','pubg','genshin','mobilegaming']},
  'culture': {'screen':['cinema','movies','film','series','documentary','netflix','marvel','sitcom'],
              'visual':['art','museum','gallery','photography','exhibition','painting','sketching','illustration','streetart','graffiti','sculpture'],
              'stage':['theatre','opera','ballet','standup','comedy','improv','musical','circus'],
              'reading':['books','reading','literature','bookclub','scifi','fantasy','nonfiction'],
              'urbanism':['architecture','urbanism','city'],
              'anime':['anime','manga','kdrama','cosplay','kpop'],
              'craft':['pottery','ceramics','knitting','crochet','sewing','woodworking','calligraphy','diy'],
              'writing':['writing','poetry','journaling','blogging'],
              'history':['history','heritage','archaeology']},
  'tech':    {'startups':['startup','startups','product','founder','entrepreneur','business'],
              'engineering':['ai','ml','programming','coding','software','data','crypto','blockchain','devops','cloud','cybersecurity','security','python','javascript','rust','golang','opensource','frontend','backend'],
              'career':['networking','investing','investor','career','mentorship','consulting','finance','vc','freelance','remote'],
              'design':['design','ux','ui','figma','branding','typography','motion'],
              'dataai':['datascience','analytics','statistics','bigdata'],
              'web3':['web3','defi','nft','dao','ethereum','bitcoin','solidity','degen'],
              'growth':['marketing','sales','saas','growth','b2b','pm']},
  'music':   {'listening':['concert','gig','festival','music','vinyl','livemusic','playlist'],
              'making':['guitar','piano','drums','dj','jam','producing','singing','karaoke','band','bass','synth','ableton','songwriting','choir'],
              'electronic':['rave','techno','edm'],
              'genres':['jazz','rock','hiphop','rap','classical','indie','pop','metal','punk','reggae','funk','soul','house','disco'],
              'dance':['salsa','bachata','tango','swing','ballroom','zumba']},
  'outdoors':{'hiking':['hiking','trekking','nature','camping','mountains','trail','outdoor','outdoors','backpacking','trailrunning','mountaineering'],
              'watersnow':['surfing','kayaking','skiing','snowboard','paddleboard','sup','windsurf','kitesurf','wakeboard','snorkeling','freediving','scuba'],
              'travel':['travel','roadtrip','sightseeing','vanlife','digitalnomad','hostels','cityhop'],
              'fishing':['fishing'],
              'naturelife':['birdwatching','foraging','gardening','plants','stargazing','botany'],
              'adventure':['paragliding','skydiving','caving','canyoning']},
  'learning':{'language':['spanish','english','french','german','italian','portuguese','russian','language','languages','exchange','practice'],
              'skills':['course','workshop','study','bootcamp','certification','tutoring','studygroup'],
              'langs2':['japanese','korean','mandarin','chinese','arabic','catalan','dutch','swedish','hindi','polish','turkish','greek'],
              'academic':['psychology','economics','science','neuroscience'],
              'personal':['publicspeaking','debate','productivity']},
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
            'drink':'drinks','party':'party','gym':'gym','codes':'coding','code':'coding','programme':'coding',
            # expanded vocabulary — variants / short forms of the new topics
            'ps5':'playstation','ps4':'playstation','weeb':'anime','btc':'bitcoin','eth':'ethereum',
            'js':'javascript','infosec':'cybersecurity','garden':'gardening','gardens':'gardening',
            'birding':'birdwatching','birdwatch':'birdwatching','kayak':'kayaking','meditate':'meditation',
            'mindfulness':'meditation','dancing':'salsa','jiujitsu':'bjj','muay':'muaythai','bake':'baking',
            'volunteer':'volunteering','llm':'ai','genai':'ai','machinelearning':'ai','productmanager':'pm'}
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

def _norm(w):
    w = str(w).strip().lower().replace(' ', '')
    return SYNONYMS.get(w, w)

def cat_of(word):
    """(broad, sub) for an interest/topic, matched against the KNOWN vocabulary (exact, then prefix>=5).
    Never a raw substring — so no 'art' in 'party', and >=5 stops short words like 'over'->overwatch, 'star'->startups.
    Short real forms (hike, swim, climb...) are handled by SYNONYMS, not by the prefix rule."""
    w = _norm(word)
    if w in _IDX: return _IDX[w]
    for k, bs in _IDX.items():
        if len(w) >= 5 and (k.startswith(w) or w.startswith(k)): return bs
    return (None, None)

def same_topic(t, x):
    t, x = _norm(t), _norm(x)
    if t == x: return True
    ct, cx = cat_of(t), cat_of(x)
    return len(t) >= 4 and len(x) >= 4 and (t.startswith(x) or x.startswith(t)) and ct[1] and ct[1] == cx[1]

def _wtok(s):
    return [w for w in re.findall(r"[a-zа-яё0-9]+", str(s).lower()) if len(w) >= 3]

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
    """Best topical tier (4 exact > 3 sub-cat > 2 broad-cat > 1 adjacent > 0 none) + matched interests."""
    matched = set(); best = 0
    xb = [(x, cat_of(x)) for x in interests]
    for t in topics:
        bt, st = cat_of(t)
        for x, (bx, sx) in xb:
            if same_topic(t, x): matched.add(_norm(x)); best = max(best, 4)
            elif st and st == sx: best = max(best, 3)
            elif bt and bt == bx: best = max(best, 2)
            elif bt and bx and bx in ADJACENCY.get(bt, []): best = max(best, 1)
            # neither side is in the taxonomy -> fall back to a literal shared interest word, so real
            # interests the vocabulary doesn't cover ("apple", "рыбалка", "labubu") still match each other.
            elif not bt and not bx and _wshare(t, x): matched.add(_norm(x)); best = max(best, 4)
    return best, matched

def _cat_of(tok):   # back-compat: broad category only
    return cat_of(tok)[0]

# ---- §6 governed taxonomy layer: bind the REAL scoring taxonomy into the read-only narrator (kt) ----
# kt never imports app (avoids a cycle) and never scores — app injects its own functions so kt narrates the
# SAME decision the engine makes. graph_txn is the ONLY sanctioned edit channel for kt's governance PROOFS
# (alias_invariant / shadow_replay Mode B): it transactionally mutates THIS module's own taxonomy globals
# under a lock and guarantees restore in finally. It transiently changes real scoring, so it is TEST-ONLY /
# offline — never call it from inside a live request handler.
_GRAPH_LOCK = threading.Lock()

@contextlib.contextmanager
def graph_txn(edits):
    """Apply taxonomy-graph edits to the live globals so the injected topical() actually resolves them, then
    restore. edits = {'synonyms': {variant: canonical}, 'adjacency': {broad: [neighbours]},
    'taxonomy': {(broad, sub): [words]}}. TEST-ONLY — see the note above."""
    edits = edits or {}
    with _GRAPH_LOCK:
        saved_syn, saved_adj = dict(SYNONYMS), copy.deepcopy(ADJACENCY)
        saved_tax, saved_idx = copy.deepcopy(TAXONOMY), dict(_IDX)
        try:
            for v, canon in (edits.get("synonyms") or {}).items():
                SYNONYMS[str(v).strip().lower().replace(" ", "")] = str(canon).strip().lower().replace(" ", "")
            for (b, s), words in (edits.get("taxonomy") or {}).items():
                TAXONOMY.setdefault(b, {}).setdefault(s, [])
                for w in words:
                    wn = str(w).strip().lower().replace(" ", "")
                    if wn not in TAXONOMY[b][s]:
                        TAXONOMY[b][s].append(wn)
                    _IDX[wn] = (b, s)
            for b, neigh in (edits.get("adjacency") or {}).items():
                ADJACENCY[b] = list(neigh)
            yield
        finally:
            SYNONYMS.clear(); SYNONYMS.update(saved_syn)
            ADJACENCY.clear(); ADJACENCY.update(saved_adj)
            TAXONOMY.clear(); TAXONOMY.update(saved_tax)
            _IDX.clear(); _IDX.update(saved_idx)

kt.bind_engine(topical=topical, norm=_norm, cat_of=cat_of, same_topic=same_topic,
               TAXONOMY=TAXONOMY, SYNONYMS=SYNONYMS, ADJACENCY=ADJACENCY, graph_txn=graph_txn)

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
    """§23.2.11 single source of truth — the sha-pinned config is authoritative for all weights/thresholds. This
    legacy runtime tuner is FROZEN: it no longer mutates WEIGHTS (a request body can never create a second weight
    source), it just echoes the current values read-only."""
    return dict(WEIGHTS)

# ---- server-side session store (file-backed) — mirrors the client's localStorage + holds the feedback loop ----
STORE_PATH = os.environ.get("KLEAL_STORE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "kleal_store.json"))
# §14: a REENTRANT lock so the accept transaction can hold ONE lock across revalidate + slot-claim +
# _record_outcome (which re-acquires it) without deadlocking — closes the read-then-write gap at the send boundary.
_STORE_LOCK = threading.RLock()
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
        u.setdefault("saved_searches", [])   # §12.2 step 7: [{id, intent, created_at, status}]
        return u

# ---- §12.2 step 7: saved search + notify-later. Lives in SESSION / kleal_store.json (gitignored) — NEVER a
# users.json writer. 'Notify later' is a persist + on-demand /check pull-hook (real async push is separate infra).
def _save_search(intent, uid="me"):
    u = _session(uid)
    sid = "ss_" + hashlib.sha1(("%s|%s" % (uid, json.dumps(intent, sort_keys=True, default=str))).encode("utf-8")).hexdigest()[:12]
    if not any(s.get("id") == sid for s in u["saved_searches"]):
        u["saved_searches"].append({"id": sid, "intent": intent, "created_at": kc._iso(time.time()), "status": "watching"})
        _save_store()
    return sid

def _list_saved_searches(uid="me"):
    return list(_session(uid).get("saved_searches") or [])

def _delete_saved_search(sid, uid="me"):
    u = _session(uid)
    n = len(u["saved_searches"])
    u["saved_searches"] = [s for s in u["saved_searches"] if s.get("id") != sid]
    if len(u["saved_searches"]) != n:
        _save_store()
    return n != len(u["saved_searches"])

def _check_saved_searches(prof=None, uid="me"):
    """Re-run each saved search READ-ONLY over the CURRENT hard-gate pool (block/pause/age/consent since save
    are honored, never relaxed); mark 'ready' only when a REAL (non-fallback) direct match now exists."""
    u = _session(uid)
    out = []
    for s in u.get("saved_searches") or []:
        try:
            cands = match_candidates(dict(s.get("intent") or {}), prof or {}, {"uid": uid})
            real = [c for c in cands if not c.get("fallback")]
            s["status"] = "ready" if real else "watching"
            out.append({"id": s["id"], "status": s["status"], "matches": len(real), "created_at": s.get("created_at")})
        except Exception as e:
            out.append({"id": s.get("id"), "status": "error", "error": str(e)[:120]})
    _save_store()
    return out
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

# ---- §11 allocation: per-name IMPRESSION log (like _proposals; gitignored kleal_store.json, no users.json writer)
def _log_exposure(name):
    key = str(name or "").strip().lower()
    if not key:
        return
    now = time.time()
    with _STORE_LOCK:
        log = SESSION.setdefault("_exposure", {})
        log[key] = [t for t in (log.get(key) or []) if now - t < 7 * 86400] + [now]
    _save_store()

def _exposures_in_window(window_s):
    now = time.time()
    log = SESSION.get("_exposure") or {}
    return {k: sum(1 for t in (v or []) if now - t < window_s) for k, v in log.items()}

def _responsive_counts():
    """§11.1 'most-responsive' signal = accepted+completed outcomes per name. Used DEMOTE-ONLY (never a
    ranking boost — a boost would be the reputation-score-fed-to-ranking §11 forbids)."""
    r = {}
    for e in (SESSION.get("_outcomes") or []):
        if e.get("stage") in ("accepted", "completed"):
            r[e.get("name")] = r.get(e.get("name"), 0) + 1
    return r

def _idempotent(idem_key, entity, ent_id, action, producer):
    """§23.2.13 — memoize a write's response by an idempotency key so a replay returns the prior result
    (error_code DUPLICATE) WITHOUT re-applying its side effects. A falsy key runs the producer unchanged."""
    if not idem_key:
        return producer()
    key = ks.dedup_key(entity, ent_id, action, extra=idem_key)
    with _STORE_LOCK:
        prior = (SESSION.get("_write_seen") or {}).get(key)
    if prior is not None:
        return dict(prior, duplicate=True, error_code="DUPLICATE")
    res = producer()
    with _STORE_LOCK:
        SESSION.setdefault("_write_seen", {})[key] = res
        _save_store()
    return res

def record_feedback(name, decision, uid="me", purpose=None):
    """§17.2 isolation: an optional `purpose` scopes the feedback key to a mode (e.g. 'dating') so a decline in
    one mode never bleeds into another's ranking/edge. purpose=None keeps the bare-name key (byte-identical to
    the legacy domain-agnostic behavior)."""
    d = str(decision or "").lower()
    if not d.startswith(("accept", "reject")): return False
    u = _session(uid)
    key = "%s::%s" % (name, purpose) if purpose else str(name)
    u["feedback"][key] = "accepted" if d.startswith("accept") else "rejected"
    _save_store(); return True

# ---- success invariant (spec §1 / §2 terms) -------------------------------------------------------
# Success = a COMPLETED interaction with two-sided confirmation — NOT a click or an impression, and NOT
# a single probability. Silence is neutral, never negative: 'expired_no_response' is its own stage and is
# never fed to the ranking-lowering feedback loop. A 'match' exists only after a mutual accept that passed
# the send-boundary revalidation (§8.2). Lives in matching's own kleal_store.json (no new users.json writer).
_OUTCOME_STAGES = ("proposed", "accepted", "declined", "completed", "expired_no_response")
def _record_outcome(name, stage, uid="me"):
    st = str(stage or "").strip().lower()
    key = str(name or "").strip().lower()
    if st not in _OUTCOME_STAGES or not key:
        return False
    now = time.time()
    with _STORE_LOCK:
        SESSION.setdefault("_outcomes", []).append({"name": key, "stage": st, "ts": now, "uid": str(uid or "me")})
        if st in ("accepted", "completed"):                 # mutual accept forms a match; complete = success
            m = SESSION.setdefault("_matches", {}).setdefault(key, {"name": key, "matched_ts": None, "completed_ts": None})
            if st == "accepted" and not m["matched_ts"]:  m["matched_ts"] = now
            if st == "completed":                          m["completed_ts"] = now
    _save_store()
    return True

_MATCH_STATUS_STATE = {"completed": "COMPLETED", "active": "MUTUAL", "expired": "CANCELLED"}
def _match_capsules(uid="me"):
    """§4.9 Match Capsules materialised from SESSION['_matches'] (mutual accept after revalidation). An
    ADDITIVE list on the outcome routes — the int `matches` metric below is left untouched (COMPAT-1)."""
    out = []
    for key, rec in (SESSION.get("_matches") or {}).items():
        cap = kc.build_match(rec, [uid, key], "pilot")
        cap["state"] = _MATCH_STATUS_STATE.get(cap.get("status"), ks.initial_state("match"))  # §14.1 lifecycle state
        out.append(cap)
    return out

def _success_metrics():
    """§1 success model, computed over the outcome log. 'silence_is_negative' is False by construction:
    expired_no_response is counted but never treated as a rejection."""
    log = SESSION.get("_outcomes") or []
    stages = {s: 0 for s in _OUTCOME_STAGES}
    for e in log:
        stages[e.get("stage")] = stages.get(e.get("stage"), 0) + 1
    matches = SESSION.get("_matches") or {}
    return {"stages": stages, "matches": len(matches),
            "completed_interactions": sum(1 for m in matches.values() if m.get("completed_ts")),
            "silence_is_negative": False,
            "note": "success = completed interaction + two-sided accept; expired_no_response is neutral, "
                    "only explicit 'declined' is negative"}

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
# Off by default: no fabricated people, ever, unless a demo explicitly asks for them.
DEMO_FALLBACK = os.environ.get("KLEAL_DEMO_FALLBACK", "0") != "0"
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
    if not store:
        # No real people in the store. The demo pool used to stand in here so a fresh system would
        # not look dead — but the stand-ins ARE what a user reads as "mock users", and after the
        # store was emptied the app still answered every search with Ana/Nico/Iris. Product call:
        # an empty pool must return an empty pool, and buddy already has an honest "nobody yet"
        # reply for exactly that. The fallback is kept one env var away for demos and for the
        # matching owner's own testing: KLEAL_DEMO_FALLBACK=1 restores the old behaviour.
        return CANDIDATES if DEMO_FALLBACK else []
    if not MERGE_DEMO:
        return store                               # opt-out: store authoritative (original behaviour)
    seen = {str(u.get("name", "")).strip().lower() for u in store}
    return list(store) + [c for c in CANDIDATES if str(c.get("name", "")).strip().lower() not in seen]

# ---------------- Matching Core v2 (spec-faithful engine; core_v2.py + ../../config/*.yaml) ----------------
# Scoring per "Kleal_Matching_Core_Final_Spec_RU_v2": feature groups with unknown/coverage, R_lcb,
# tier-as-provenance, user-facing bands. Weights/thresholds live ONLY in the sha-pinned YAML.
# Engine select (full replacement path): KLEAL_ENGINE=matching_core (default) loads the clean-rebuild
# package `matching_core/` via the drop-in adapter; KLEAL_ENGINE=core_v2 restores Dev B's engine instantly.
# Rollback for Dev A/B: KLEAL_CORE_V2=0 -> the legacy scorer below runs unchanged. A missing or
# tampered config also falls back automatically (fail-safe, spec §21.4) — see /api/agent/weights.
_ENGINE = os.environ.get("KLEAL_ENGINE", "matching_core").strip().lower()
if _ENGINE == "core_v2":
    import core_v2 as _core
else:
    try:
        import matching_core_engine as _core          # full replacement: matching_core is the engine
    except Exception as _ee:
        import core_v2 as _core                        # safety net if the package is missing/broken
        _ENGINE = "core_v2(fallback:%s)" % type(_ee).__name__
_CORE_CFG, _CORE_ERR = None, None
try:
    _CORE_CFG = _core.load_config(os.environ.get(
        "KLEAL_CORE_CONFIG",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                     "config", "Kleal_Matching_Core_Config_v2.yaml")))
except Exception as _e:
    _CORE_ERR = str(_e)
CORE_V2 = os.environ.get("KLEAL_CORE_V2", "1") != "0" and _CORE_CFG is not None
# §15: report (NON-raising) any group_formation config-block drift at load time. We deliberately do NOT call the
# raising kg.load_group_params here — a bad group block must never crash live matching (it would perturb the
# person-to-person slate). The gated /api/agent/group endpoint calls load_group_params in a try/except -> dormant.
_GROUP_CFG_PROBLEMS = kg.validate_group_config_block(_CORE_CFG) if _CORE_CFG else ["core config not loaded"]

def _relaxed_cfg():
    """A clone of the canonical config with every domain's DISCOVERY floor dropped to 0 — used only by
    the never-dead-end fallback pass (§12). Weights / λ / OUTREACH floors are untouched, so scoring and
    the outreach/consent gates are identical; only the 'show it in discovery' threshold is relaxed, so
    adjacent/broader-but-eligible people can surface instead of an empty result."""
    if _CORE_CFG is None:
        return None
    c = copy.deepcopy(_CORE_CFG)
    for dc in c.get("domains", {}).values():
        dc["discovery_min_lcb"] = 0.0
        dc["discovery_min_coverage"] = 0.0
    return c
_RELAXED_CFG = _relaxed_cfg()

# ---- §0 decision 10 / §11.3: payment MUST NOT touch relevance, eligibility, safety, or order ----------
# Structurally the engine feeds ZERO payment signal into scoring. This reads the config's stated invariant
# and makes it an ENFORCED, visible guarantee: if a future config ever flipped a payment boost on, matching
# surfaces ok=False (the caller/health can refuse) instead of silently honouring it. Reads the already-pinned
# `currency_or_paid_priority` key — no config edit, no sha change.
def _payment_invariant(cfg=None):
    flags = ((cfg or _CORE_CFG) or {}).get("currency_or_paid_priority") or {}
    boost = bool(flags.get("ranking_boost_allowed", False))
    safety = bool(flags.get("safety_priority_affected_by_payment", False))
    return {"ranking_boost_allowed": boost, "safety_priority_affected_by_payment": safety,
            "enforced": True, "ok": (not boost) and (not safety),
            "note": "subscription may change limits/tools, never relevance/eligibility/safety/order"}
PAYMENT_INVARIANT = _payment_invariant()

# ---- §1.2 pilot: only a subset of §1.1 decision types ships now; the rest are DECLARED but disabled ----
# (i.e. out-of-scope by design, not merely unbuilt). release_status comes from the pinned config; the
# decision-type surface is explicit so a caller asking for a non-pilot type gets a clear "not in this pilot"
# instead of a silent empty result. Group/event/room/continuation are the post-pilot layers (§14–§16).
RELEASE_STATUS = str((_CORE_CFG or {}).get("release_status") or "pilot_candidate")
PILOT_DECISION_TYPES = {
    "person_to_person": True,           # §1.1 — the live matching path
    "intent_to_intent": True,           # §1.1 — reciprocity join (live; full condition-merge is partial)
    "group_formation": False,           # §1.1 — post-pilot (§15)
    "intent_to_event": False,           # §1.1 — post-pilot (§16)
    "intent_to_room": False,            # §1.1 — post-pilot (§16)
    "intent_to_venue": False,           # §1.1 — post-pilot (§16); additive, declared-but-disabled (never flipped True)
    "relationship_continuation": False, # §1.1 — post-pilot (§14)
}
# ---- §15 group formation: the PRODUCT switch -----------------------------------------------------
# kleal_groups.py is deliberate conformance scaffolding: its payloads hard-code enabled:False and the
# algorithm only runs behind an exact, test-only override. That design stays — it is what keeps a
# post-pilot layer from activating itself. What was missing is a switch ABOVE it, so the feature can
# be turned on as a product without editing §15's semantics, and turned off again with one variable.
#
# Off, asking for a group was a silent zero: `groupSize` routes the intent to group_formation, the
# pilot gate rejected it, and /api/agent/match returned ZERO PEOPLE. The same query without that one
# field returned eight. Whatever the switch says, a group request must never cost you the people.
GROUPS_ENABLED = os.environ.get("KLEAL_GROUPS", "0") != "0"
_GROUP_OVERRIDE = {"enable_group_formation": True}   # the exact shape kg.is_override_enabled demands


def _decision_type(intent):
    """Which §1.1 decision type an intent asks for. Explicit `decisionType` wins; otherwise inferred from
    group/event/room signals, defaulting to person_to_person (the pilot path)."""
    intent = intent or {}
    dt = str(intent.get("decisionType") or "").strip()
    if dt in PILOT_DECISION_TYPES:
        return dt
    if intent.get("groupSize") or intent.get("group"):        return "group_formation"
    if intent.get("eventId") or str(intent.get("type") or "") == "event": return "intent_to_event"
    if intent.get("roomId"):                                  return "intent_to_room"
    if intent.get("venueId") or str(intent.get("type") or "") == "venue": return "intent_to_venue"   # §16 (pilot-off)
    return "person_to_person"
if GROUPS_ENABLED:
    PILOT_DECISION_TYPES["group_formation"] = True    # §15 live: set at import, never per-request


def _pilot_enabled(intent):
    return bool(PILOT_DECISION_TYPES.get(_decision_type(intent), False))

def _data_version():
    """Fingerprint of the candidate store in effect (source + mtime + count). Part of the request snapshot
    so a result is interpretable against exactly the data that produced it (§4 immutable snapshot)."""
    lst = _users_cache.get("list")
    src, mt = ("store", _users_cache.get("mtime")) if isinstance(lst, list) else ("demo", None)
    n = len(lst) if isinstance(lst, list) else len(CANDIDATES)
    tag = "%s:%s:%d" % (src, ("%.0f" % mt) if mt else "0", n)
    return "data_" + hashlib.sha1(tag.encode("utf-8")).hexdigest()[:10]

def _intent_identity(intent):
    """§3 step1 / §4.3: a stable intent_id + version from the NORMALISED intent (deterministic, no clock),
    plus its domain, decision type and status — the identity block the spec attaches to a compiled intent."""
    intent = intent or {}
    core = {k: intent.get(k) for k in ("type", "topics", "mode", "format", "role", "radiusKm",
                                       "requiredLanguages", "minAge", "maxAge", "verifiedOnly")}
    h = hashlib.sha1(json.dumps(core, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
    return {"intent_id": "int_" + h[:12], "version": h[:8], "status": "active",
            "domain": (_core.infer_domain(intent, cat_of) if CORE_V2 else None),
            "decision_type": _decision_type(intent)}

def _request_snapshot(intent):
    """§4 intro: an immutable per-request snapshot of every version in effect (intent/config/policy/data)
    plus the enforced payment invariant, so a result stays interpretable against its exact inputs."""
    ident = _intent_identity(intent)
    return {"intent_id": ident["intent_id"], "intent_version": ident["version"],
            "decision_type": ident["decision_type"], "pilot_enabled": _pilot_enabled(intent),
            "config_version": (_CORE_CFG or {}).get("config_version"),
            "config_sha": ((_CORE_CFG or {}).get("_sha256") or "")[:12],
            "release_status": RELEASE_STATUS, "policy_version": "policy-2.0.0",
            "data_version": _data_version(), "payment_invariant": PAYMENT_INVARIANT,
            "config_health": {"core_v2": CORE_V2, "error": _CORE_ERR,          # §21.4 SLA: config/taxonomy health
                              "group_drift": list(_GROUP_CFG_PROBLEMS or []), "degraded": bool(_CORE_ERR)}}

PARSE_PROMPT = '''You convert a user's free-text social request into a structured intent.
Return ONLY compact JSON (no prose, no markdown), keys:
 title  (3-5 word human label, e.g. "Coffee & urbanism chat"),
 type   (one of: dinner, sport, gaming, networking, dating, language, social, other),
 topics (array of 1-4 lowercase keywords, e.g. ["coffee","urbanism"]),
 role   (one of: play, watch, discuss, practise, attend, meet — infer from the verb; default "meet"),
 mode   (offline | online),
 format (short, e.g. "1:1 or small group"),
 time   (short, infer from text, default "Flexible"),
 place  (short, infer, default "Public places nearby"),
 groupSize (integer 2-8 = how many people in TOTAL should be at the meetup, the asker INCLUDED;
            null unless the user asks for a group/team/company or names a headcount),
 group  (true if they want several people rather than one, but gave no number; else null).
English only.'''

# Group headcount, read from the words people actually use. Until this existed, `groupSize` had no
# producer anywhere in the product: the screen that asks «Один на один / Малая группа / Компания»
# dropped the answer, and the parser had no such key, so §15 group formation was unreachable and
# every group request was silently served as one-person-at-a-time matching.
_GROUP_WORDS = ('групп', 'компани', 'команд', 'вместе', 'втро', 'вчетвер', 'впятер', 'вшестер',
                'group', 'team', 'crew', 'squad', 'together', 'grupo', 'equipo', 'juntos')
_GROUP_NUM_WORDS = {'вдвоем': 2, 'вдвоём': 2, 'двоем': 2, 'двоём': 2, 'втроем': 3, 'втроём': 3,
                    'троем': 3, 'троём': 3, 'вчетвером': 4, 'впятером': 5, 'вшестером': 6}
# A headcount sits next to a people-word, in either order — Russian puts it on both sides
# («4 человека», «человека 4») and so does Spanish («4 personas», «somos 4»).
_PEOPLE_NUM = re.compile(
    r"(\d{1,2})\s*(?:чел\w*|людей|человек\w*|игрок\w*|people|persons?|players?|personas?|jugadores)"
    r"|(?:чел\w*|людей|человек\w*|people|persons?|personas?|somos|нас)\s*(\d{1,2})", re.U)
# A bare number is a headcount only in a sentence that already said "group" — and never when it is
# really a clock ("в 18:00", "at 7pm"), a distance or a price.
_BARE_NUM = re.compile(r"(?<![:\d.,])(\d{1,2})(?![:\d])"
                       r"(?!\s*(?:час|утра|вечера|дня|ночи|:|h\b|am\b|pm\b|мин|min|км|km|€|\$|%))", re.U)


def _parse_group_size(ql):
    """(groupSize, wants_a_group) from free text. The number is the TOTAL at the meetup, asker included."""
    wants = any(w in ql for w in _GROUP_WORDS)
    for w, n in _GROUP_NUM_WORDS.items():
        if w in ql:
            return n, True
    m = _PEOPLE_NUM.search(ql) or (_BARE_NUM.search(ql) if wants else None)
    if m:
        n = int(next(g for g in m.groups() if g))
        if 2 <= n <= 12:
            return n, True
    return None, wants

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
    gsize, gwant = _parse_group_size(ql)
    return {"title": title, "type": typ, "topics": topics or (['dating'] if dating else ['social']),
            "role": role, "mode": ('online' if online else 'offline'),
            "format": "1:1 or small group", "time": tm, "place": "Public places nearby",
            # §15 routing: a size, or — when they asked for company without naming a number — the bare
            # flag, which lets the domain pack / config decide how many seats a padel court has.
            "groupSize": gsize, "group": (True if (gwant and not gsize) else None),
            # gate parameters (owner's search scope) — sensible defaults; dating tightens age/verification
            "radiusKm": 15, "verifiedOnly": bool(dating), "minAge": (18 if dating else None), "maxAge": None,
            "requiredLanguages": [], "exactMatchRequired": False, "adjacentAllowed": True, "broadAllowed": True}

def parse_intent(q):
    """§5: the LLM is an untrusted PARSER. Both the LLM branch and the fallback pass through
    ki.validate_and_normalize (schema-complete the 16 keys, allowlist type/role/mode, clamp numerics,
    truncate language codes) before returning — so no un-validated LLM output ever drives matching."""
    q = (q or '').strip()
    if not q: return ki.validate_and_normalize(_fallback_parse(''))[0]
    try:
        cfg = MODEL_ID
        raw = llm_complete(cfg, [{"role": "system", "content": PARSE_PROMPT},
                                  {"role": "user", "content": q}], 0.2)
        obj = base._extract_json(raw)
        if isinstance(obj, dict) and obj.get('topics'):
            fb = _fallback_parse(q)
            for k, v in fb.items(): obj.setdefault(k, v)
            if not isinstance(obj.get('topics'), list) or not obj['topics']: obj['topics'] = fb['topics']
            # setdefault cannot help when the model EMITS the key as null, which it does for
            # groupSize far more often than it reads «человека 4» correctly. A regex that found a
            # headcount beats a model that returned nothing; a model that found one still wins.
            for k in ('groupSize', 'group'):
                if not obj.get(k) and fb.get(k): obj[k] = fb[k]
            return ki.validate_and_normalize(obj, source='llm')[0]
    except Exception:
        pass
    return ki.validate_and_normalize(_fallback_parse(q))[0]

ROLE_CONFLICT = {('play', 'watch'), ('watch', 'play'), ('practise', 'watch')}
SOON_WORDS = ('today', 'tonight', 'evening', 'tomorrow')

# ---- §8 eligibility / safety / purpose-binding constants (all ADDITIVE; gates fire only on a PRESENT,
# restrictive value and default-ALLOW on absence, so field-less fixtures + the demo pool stay byte-identical).
_ACCOUNT_BLOCK = frozenset({'suspended', 'deactivated', 'banned', 'deleted'})   # §8.1 account_status (known-bad only)
_SAFETY_BLOCK = frozenset({'banned', 'csam_block', 'legal_hold', 'restricted'})  # §8.1 safety restrictions (closed set)
# §8.1 intent-mode isolation: purpose pairs that MUST NOT auto-cross (§8.3 dating is a separate contour).
# Deterministic purpose matrix (informed by the ontology's blocked_cross_purpose edges) — a candidate's
# purpose is read ONLY from its OWN active intents, never from datingOk/receiving/interests.
_TYPE_PURPOSE = {'dating': 'dating', 'networking': 'networking', 'language': 'language_exchange',
                 'gaming': 'games', 'sport': 'sport', 'social': 'friendship', 'dinner': 'friendship',
                 'event': 'friendship', 'other': 'friendship'}
_XPURPOSE_BLOCK = frozenset({frozenset(('dating', p)) for p in
                             ('friendship', 'networking', 'language_exchange', 'games', 'sport')})
_DEC_RANK = {'ALLOW': 0, 'REVIEW': 1, 'BLOCK': 2}
_REVAL_CHECKPOINTS = ('slate', 'send', 'profile_open', 'accept', 'shared_chat',
                      'reveal_place', 'reveal_contact', 'state_change')          # §8.2 #1..#7
_REVEAL_STAGE = {'reveal_place': 'full', 'reveal_contact': 'full', 'shared_chat': 'match_only'}
# §8.4: exact/home/work location must never be in the candidate payload — scrubbed from every returned card.
_PRECISE_LOCATION_KEYS = ('home', 'work', 'address', 'homeLat', 'homeLon', 'workLat', 'workLon',
                          'exact_lat', 'exact_lon', 'preciseLat', 'preciseLon', 'live_location')

def _cross_purpose_blocked(intent, c):
    """§8.1 intent-mode isolation, SHARED by retrieval (_policy_decision) and the send boundary
    (_negotiate_precheck) so a cross-purpose pair can't slip through /api/agent/negotiate. Resolves the
    candidate's purpose ONLY from its own active intents (c['intents']); returns False (ALLOW) when the
    candidate has no own-intent purpose — the common case — so the demo pool + fixtures stay byte-identical."""
    ip = _TYPE_PURPOSE.get(str((intent or {}).get('type') or '').lower())
    if not ip:
        return False
    for oi in (c.get('intents') or []):
        cp = _TYPE_PURPOSE.get(str((oi or {}).get('type') or '').lower())
        if cp and frozenset((ip, cp)) in _XPURPOSE_BLOCK:
            return True
    return False

# §18 per-domain hard slots — a critical value that, when BOTH sides declare it and they differ, is a hard
# exclusion (games server/platform, event ticket, networking industry). Absent-permissive by construction.
_DOMAIN_CRITICAL_SLOTS = ("server", "platform", "ticket", "industry")

def _hard_gates(intent, c, gate_ctx):
    """Cheap, deterministic exclusions applied BEFORE scoring. Returns (ok, reason_if_blocked)."""
    if c.get('paused'):                                            return False, 'on a break'
    if c['name'] in gate_ctx['blocked'] or c.get('blocksMe'):     return False, 'blocked'
    d = c.get('declinedOwnerDaysAgo')
    if d is not None and d < COOLDOWN_DAYS:                        return False, 'recently declined (cooldown)'
    if (c.get('pending') or 0) >= MAX_PENDING:                     return False, 'too many open invites'
    age = c.get('age')
    if age is not None and age < MIN_AGE:                          return False, 'under 18'
    if intent.get('type') == 'dating' and not c.get('datingOk'):  return False, 'not open to dating'
    if intent.get('verifiedOnly') and not c.get('verified'):      return False, 'not verified'
    mn, mx = intent.get('minAge'), intent.get('maxAge')
    if mn or mx:
        if age is None:                                           return False, 'age unknown'
        if mn and age < mn:                                       return False, 'below age range'
        if mx and age > mx:                                       return False, 'above age range'
    # Gender. Onboarding has always collected it and tools/ has always written it, but NOTHING in
    # matching ever read the field — so the "Кто / Sex" selector was a control that changed nothing.
    # Gated exactly like age: absent from the intent means no filter at all, and `any` is an explicit
    # "do not filter" rather than a value to match against.
    want_g = str(intent.get('gender') or intent.get('sex') or '').strip().lower()
    if want_g and want_g not in ('any', 'any is fine', 'не важно', 'любой', 'all'):
        cand_g = str(c.get('gender') or '').strip().lower()
        if not cand_g:                                            return False, 'gender unknown'
        if cand_g != want_g:                                      return False, 'different gender'
    reql = {str(l)[:2].lower() for l in (intent.get('requiredLanguages') or [])}
    if reql and not reql.issubset({str(l)[:2].lower() for l in (c.get('langs') or [])}):
        return False, 'missing a required language'
    if intent.get('mode') == 'offline' and intent.get('radiusKm') and c.get('km') is not None:
        try:
            if float(c['km']) > float(intent['radiusKm']):       return False, 'outside the radius'
        except (TypeError, ValueError):
            pass
    # ---- §8.1 additional canonical gates (appended LAST so existing reason tuples are unchanged; each
    # fires ONLY on a present restrictive value, so absent-field fixtures stay byte-identical) ----
    st = str(c.get('accountStatus') or '').strip().lower()
    if st in _ACCOUNT_BLOCK or c.get('suspended') is True:        return False, 'account not active'   # §8.1 account_status
    vis = c.get('visibility') or (c.get('privacy') or {}).get('visibility')
    if vis == 'private':                                          return False, 'private profile'      # §8.1 privacy visibility
    sf = c.get('safetyFlags') or []
    if isinstance(sf, list) and any(f in _SAFETY_BLOCK for f in sf): return False, 'safety restriction' # §8.1 safety (hard)
    # ---- §18 per-domain critical slots (absent-permissive: fires ONLY when BOTH intent and candidate declare
    # the slot AND they differ, so no current person fixture is touched — byte-identical) ----
    for _slot in _DOMAIN_CRITICAL_SLOTS:
        iv, cv = intent.get(_slot), c.get(_slot)
        if iv and cv and str(iv).strip().lower() != str(cv).strip().lower():
            return False, 'domain slot mismatch: %s' % _slot
    mind = intent.get('minDurationMin')                            # §18.3 minimum meet duration
    cav = c.get('availableMinutes')
    if mind and isinstance(cav, (int, float)) and not isinstance(cav, bool) and cav < float(mind):
        return False, 'window shorter than requested duration'
    return True, None

def _policy_decision(intent, c, gate_ctx, cfg=None):
    """§0 output table / §3 step2: policy_decision is a TRI-state, not a boolean.
      BLOCK  — a hard eligibility/safety exclusion (never scored, never shown).
      REVIEW — discoverable, but NOT auto-proposable: it must clear a separate safety/legal track first.
               A dating domain whose config sets release_gate=separate_safety_legal_track and whose
               candidate is unverified lands here instead of a silent ALLOW (§0 dec.8 / §1.2 dating gate).
      ALLOW  — clear for scoring + personal outreach.
    Returns (decision, reason)."""
    ok, why = _hard_gates(intent, c, gate_ctx)
    if not ok:
        # §8.1: age⇒"BLOCK or REVIEW", location⇒"REVIEW or zone expansion". Opt-in ONLY (default absent ⇒
        # unchanged BLOCK, so the existing slate/counts are byte-identical); when the intent asks for softer
        # semantics these two become REVIEW (discoverable, non-proposable, held for a user answer / expansion).
        if (intent.get("soft_eligibility") or c.get("zoneOptIn")) and why in ("age unknown", "outside the radius"):
            return "REVIEW", why                                # §8.1 zone-expansion: a zone opt-in outside the radius is held for expansion, not hard-blocked
        return "BLOCK", why
    if _cross_purpose_blocked(intent, c):                       # §8.1 intent-mode isolation (shared with send)
        return "BLOCK", "cross-purpose isolation"
    if c.get("sensitivity") == "restricted" or "review" in (c.get("safetyFlags") or []):   # §8.1 safety (soft)
        return "REVIEW", "safety restriction: held for safety review"
    if CORE_V2:
        domain = _core.infer_domain(intent, cat_of)
        dom_cfg = ((cfg or _CORE_CFG) or {}).get("domains", {}).get(domain) or {}
        if dom_cfg.get("release_gate") and not c.get("verified"):
            return "REVIEW", "%s: separate safety/legal track required (unverified)" % domain
    return "ALLOW", None

def evaluate_policy(intent, c, gate_ctx=None):
    """§23.4.2 — a single typed policy-verdict facade that runs the existing gate stack IN ORDER (_hard_gates ->
    cross-purpose isolation -> _policy_decision -> disclosure clamp) and returns one object. It reproduces the
    per-gate ALLOW/BLOCK/REVIEW outcome byte-for-byte — it adds NO new behavior, only a unified surface."""
    gate_ctx = gate_ctx if gate_ctx is not None else _gate_ctx_and_self({})[0]
    ok, why = _hard_gates(intent, c, gate_ctx)
    decision, reason = _policy_decision(intent, c, gate_ctx)
    disc = _revalidate_disclosure(intent, c, "profile_open") if decision != "BLOCK" else None
    return {"decision": decision, "reason": reason, "eligible": ok, "gate_reason": why,
            "cross_purpose_blocked": _cross_purpose_blocked(intent, c),
            "disclosure": disc, "policy_version": "policy-2.0.0"}

def _allocation_action(card):
    """§0 output table: an explicit typed allocation_action per candidate, DERIVED from decisions already
    made (policy / readiness / tier / fallback) — never a new score. One of:
      review_required · propose · discovery_expanded · discovery_only."""
    if card.get("policy") == "REVIEW":     return "review_required"
    if card.get("can_outreach"):           return "propose"
    if card.get("fallback"):               return "discovery_expanded"
    return "discovery_only"

def _decision_class(card):
    """§9.6 read-only 5-way decision label, a strict sibling of _allocation_action. Derived ONLY from the
    engine's OWN already-stamped decisions {policy, tier, band, can_outreach, why_no_outreach} — it
    re-thresholds NOTHING (the spec's flat 0.72/0.58/0.45 are illustrative; the REAL per-domain floors live
    in the sha-pinned config and are already folded into can_outreach/band). Total function; every read via
    .get() default so a sparse slate card (no why_no_outreach) safely falls through. Never touches scoring."""
    policy = str(card.get("policy") or "ALLOW")
    tier = str(card.get("tier") or "")
    band = str(card.get("band") or "")
    can = bool(card.get("can_outreach"))
    why = str(card.get("why_no_outreach") or "")
    if policy == "REVIEW":                                 # held for the safety/legal track — never a probe
        return "no_personal_outreach"                      # §9.6 row 5 (before clarification — must-fix)
    if can:
        if tier in ("T0", "T1") and band == "especially_close":
            return "strong_personal_candidate"             # §9.6 row 1 (ALLOW & high lcb/cov & T0-T1)
        return "usable_personal_candidate"                 # §9.6 row 2 (ALLOW & proposable, incl. T2+consent)
    if "broad consent" in why:                             # T2-without-consent is NOT discovery (must-fix)
        return "no_personal_outreach"                      # §9.6 row 5 (no expansion consent)
    if tier in ("T3", "T4") or "discovery only" in why or "below outreach floor" in why:
        return "discovery_only"                            # §9.6 row 3 (T3-T4 / below outreach floor)
    if band == "needs_clarification":
        return "clarification"                             # §9.6 row 4 (a high-impact unknown could flip it)
    return "no_personal_outreach"                          # §9.6 row 5 (below thresholds / receiving disallows)

def _validate_math_config(cfg, feature_keys, policy_version="policy-2.0.0", engine_version=None, schema_allowlist=("1.0",)):
    """§9.5 config CI checks, READ-ONLY (never mutates cfg / never re-writes _sha256 — the sha pin holds).
    Adds the checks core_v2.load_config does NOT do at runtime — evidence_id uniqueness within feature groups,
    config↔model↔policy MAJOR-version compatibility, and user_facing_bands cut ranges — plus non-mutating
    echoes of load_config's weights-sum(1e-6)/feature-key/prior-range checks. Returns a health dict; never raises."""
    cfg = cfg or {}
    checks, errors = [], []
    def add(cid, ok, detail):
        checks.append({"id": cid, "ok": bool(ok), "detail": detail})
        if not ok:
            errors.append("%s: %s" % (cid, detail))
    import re as _re
    _major = lambda v: (lambda m: int(m.group(1)) if m else None)(_re.search(r"(\d+)\.(\d+)\.(\d+)", str(v or "")))
    ev_ids = [e.get("evidence_id") for g in (cfg.get("feature_groups") or {}).values()
              for e in ((g or {}).get("evidences") or []) if isinstance(e, dict) and e.get("evidence_id")]
    add("evidence_id_unique", len(ev_ids) == len(set(ev_ids)),
        ("%d ids, %d unique" % (len(ev_ids), len(set(ev_ids)))) if ev_ids else "0 evidence ids in registry (guard active)")
    cvM, pvM = _major(cfg.get("config_version")), _major(policy_version)
    evM = _major(engine_version) if engine_version else cvM
    add("version_compat", cvM is not None and cvM == pvM and cvM == evM,
        "config=%s policy=%s engine=%s (majors %s/%s/%s)" % (cfg.get("config_version"), policy_version, engine_version, cvM, pvM, evM))
    add("schema_version_allowed", str(cfg.get("schema_version") or "") in schema_allowlist,
        "schema_version=%r allow=%s" % (cfg.get("schema_version"), list(schema_allowlist)))
    bad_band = [("%s.%s=%r" % (n, k, (b or {}).get(k))) for n, b in (cfg.get("user_facing_bands") or {}).items()
                for k in ("min_lcb", "min_coverage", "max_coverage")
                if k in (b or {}) and not (isinstance(b[k], (int, float)) and 0.0 <= b[k] <= 1.0)]
    add("band_cut_ranges", not bad_band, "all in [0,1]" if not bad_band else "out of range: %s" % bad_band)
    bad_w = []
    for d, dc in (cfg.get("domains") or {}).items():
        w = (dc or {}).get("weights") or {}
        if set(w) - set(feature_keys):
            bad_w.append("%s unknown keys %s" % (d, sorted(set(w) - set(feature_keys))))
        if abs(sum(float(w.get(k, 0) or 0) for k in feature_keys) - 1.0) > 1e-6:
            bad_w.append("%s weights sum != 1.0" % d)
    add("weights_sum_and_keys", not bad_w, "all domains sum to 1.0, no unknown keys" if not bad_w else "; ".join(bad_w))
    add("prior_ranges", all(isinstance((g or {}).get("unknown_prior"), (int, float)) and 0.0 <= (g or {}).get("unknown_prior", -1) <= 1.0
                            for g in (cfg.get("feature_groups") or {}).values()), "all unknown_prior in [0,1]")
    return {"ok": not errors, "config_version": cfg.get("config_version"), "schema_version": cfg.get("schema_version"),
            "config_sha": (cfg.get("_sha256") or "")[:12], "policy_version": policy_version,
            "checks": checks, "errors": errors}

GENERIC_TYPES = {'social', 'other', ''}   # too broad to count as a mutual-intent match on their own

def _reciprocal(intent, c):
    """True only if the candidate's OWN active intent shares a real topical interest (sub-category or exact).
    A bare TYPE match (both 'sport', both 'gaming'…) is NOT enough — 'sport/football' must not read as a
    mutual match for a 'sport/tennis' search, which used to hand football players the top T0 slot."""
    itop = [str(t).lower() for t in (intent.get('topics') or [])]
    for oi in (c.get('intents') or []):
        b, _ = topical(itop, [str(t).lower() for t in (oi.get('topics') or [])])
        if b >= 3:                                 # same sub-category or exact -> genuine mutual interest
            return True
    return False

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
        ok, _why = _hard_gates(intent, c, gate_ctx)
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
        # Distance is OPTIONAL. `km` is computed only inside _gen_pool(), i.e. only for the demo
        # fakes; a real registered person carries km=None on purpose (onboarding's own comment: a
        # stored per-person distance is meaningless, it depends on who is looking). Comparing that
        # None to a float raised TypeError and the whole ranking returned zero candidates — which,
        # once the demo fallback was switched off, made every search look empty for a real user.
        # Unknown distance now scores as what it is: no proximity signal, no bonus, no penalty.
        km = c.get('km')
        if isinstance(km, (int, float)):
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

# taxonomy helpers injected into core_v2 — module-level (all four are immutable), so every scorer reuses
# one dict instead of rebuilding it per request.
_H = {'topical': topical, 'cat_of': cat_of, 'reciprocal': _reciprocal, 'role_conflict': ROLE_CONFLICT}


def _gate_ctx_and_self(ctx, prof=None):
    """Owner session -> (hard-gate context, self-name), shared by match_candidates / _negotiate_precheck /
    explain_match so the eligibility inputs never drift between the real slate and the diagnostic."""
    ctx = ctx or {}
    sess = _session(ctx.get('uid', 'me'))
    gate_ctx = {'feedback': dict(sess.get('feedback') or {}),
                'blocked': set(sess.get('blocked') or []) | set(ctx.get('blocked') or [])}
    self_name = str(ctx.get('self') or (prof or {}).get('name') or ctx.get('uid') or '').strip().lower()
    return gate_ctx, self_name


# ---- §11 allocation & fairness (post-relevance, post-policy). Allocation decides who/how many get shown —
# it NEVER changes a pair's relevance (§11 intro) and NEVER reads payment_status (§11.3). Every mechanism is
# a NO-OP at the pilot defaults below (cap huge / quota 0 / guard off), so the surfaced slate is byte-identical
# to core_v2's; a mechanism bites ONLY under an explicit ctx['allocation'] override (falsifiably testable,
# like the §7 retrieval budget). Overridden via ctx only — NEVER the sha-pinned config, so its sha is unchanged.
ALLOCATION_CONFIG = {
    "exposure_cap_per_window": 10 ** 9,   # §11.1 per-user impression cap -> remove over-exposed tail; huge = off
    "exposure_window_s":       7 * 86400,
    "exploration_quota":       0,         # §11.2 step5 ADD count for new users; 0 -> adds nobody
    "exploration_min_coverage": 0.6,
    "popularity_max_slate_share": 1.0,    # §11.1 popularity-concentration guard; 1.0 = off
    "popularity_min_exposure": 10 ** 9,
    "supply_max_per_area":     10 ** 9,   # §11.1 city/area supply balancing; huge = off
    "responsive_max_exposure": 10 ** 9,   # §11.1 protect the most-responsive (demote-only); huge = off
    "pair_cooldown_days":      0,         # §11.1 general same-pair repeat-proposal cooldown at send; 0 = off
}

def _alloc_cfg(ctx):
    cfg = dict(ALLOCATION_CONFIG)
    ov = (ctx or {}).get("allocation")
    if isinstance(ov, dict):
        cfg.update({k: v for k, v in ov.items() if k in ALLOCATION_CONFIG})
    return cfg

def _alloc_is_default(cfg):
    return cfg == ALLOCATION_CONFIG       # exact pilot default -> _allocate early-returns the SAME list object

def _within_band_demote(slate, cfg, exp):
    """§11.1 popularity-concentration guard + most-responsive protection — DEMOTE-ONLY, WITHIN each band, and
    re-applying the FROZEN sort key so open_now/reciprocal/lcb precedence (RCV9/§11.2-2) can never be violated.
    Dormant unless the thresholds are lowered; never a ranking boost, never a scoring write-back."""
    pmin, rmax = cfg["popularity_min_exposure"], cfg["responsive_max_exposure"]
    if pmin >= 10 ** 9 and rmax >= 10 ** 9:
        return slate
    resp = _responsive_counts()
    def _demote(c):
        e = exp.get(str(c.get("name", "")).strip().lower(), 0)
        return (e > pmin) or (e > rmax and resp.get(c.get("name"), 0) > 0)
    key = lambda c: (_core.READINESS_RANK.get(c.get("readiness"), 9), -(c.get("reciprocal") or 0),
                     -(c.get("lcb") or 0), -(c.get("coverage") or 0), str(c.get("name")))
    from collections import OrderedDict
    bands, out = OrderedDict(), []
    for c in slate:
        bands.setdefault(c.get("band"), []).append(c)
    for _b, cards in bands.items():
        keep = sorted([c for c in cards if not _demote(c)], key=key)
        dem = sorted([c for c in cards if _demote(c)], key=key)
        out.extend(keep + dem)
    return out

def _allocate(slate, ctx, pool=None):
    """§11 allocation pass. DORMANT at pilot defaults (returns the SAME list object, byte-identical). Reads
    exposure / outcomes / area into LOCAL decision logic ONLY — never writes back into lcb/reciprocal/mean/
    coverage/score (no feedback into relevance, §11 intro); never reads payment_status (§11.3)."""
    cfg = _alloc_cfg(ctx)
    if _alloc_is_default(cfg):
        return slate
    win = int(cfg["exposure_window_s"])
    exp = _exposures_in_window(win)
    out = list(slate)
    cap = cfg["exposure_cap_per_window"]              # per-user exposure cap -> remove over-exposed (tail, order kept)
    if cap < 10 ** 9:
        out = [c for c in out if exp.get(str(c.get("name", "")).strip().lower(), 0) < cap]
    smax = cfg["supply_max_per_area"]                 # city/area supply balancing (drop lowest-ranked surplus)
    if smax < 10 ** 9:
        seen, keep = {}, []
        for c in out:
            a = str(c.get("area") or "").strip().lower() or "_"
            if seen.get(a, 0) < smax:
                seen[a] = seen.get(a, 0) + 1
                keep.append(c)
        out = keep
    out = _within_band_demote(out, cfg, exp)          # popularity + responsive protection (demote-only, in-band)
    q = int(cfg["exploration_quota"])                 # §11.2 step5 exploration append (0 -> nobody; never fabricates)
    if q > 0 and pool:
        have = {str(c.get("name", "")).strip().lower() for c in out}
        picks = sorted((c for c in pool if str(c.get("name", "")).strip().lower() not in have),
                       key=lambda c: exp.get(str(c.get("name", "")).strip().lower(), 0))
        for c in picks[:q]:
            out.append(dict(c, exploration=True, allocation_action="exploration"))
    return out

def _stamp_allocation_trace(slate, ctx, cfg):
    """§11.2 step 6: additive read-only per-card allocation trace. Reorders/drops/adds NOTHING. Contains ZERO
    payment keys and ZERO acceptance-probability proxy — propensity stays null / absent_by_design (§9/§10).
    NOTE: exposure_count/fatigue_state legitimately VARY across two identical match_candidates calls as the
    logs accumulate — any full-card / replay diff MUST exclude 'allocation_trace'."""
    win = int(cfg["exposure_window_s"])
    exp = _exposures_in_window(win)
    received24 = (ctx or {}).get("received24") or {}
    fatigue_cap = int(((_CORE_CFG or {}).get("outreach") or {}).get("max_proposals_received_per_user_24h") or 4)
    for idx, c in enumerate(slate):
        nm = str(c.get("name", "")).strip().lower()
        reasons = []
        if c.get("policy") == "REVIEW":     reasons.append("held: safety/legal review")
        if not c.get("can_outreach"):       reasons.append("discovery only (no personal outreach)")
        if c.get("fallback"):               reasons.append("expansion: %s" % c.get("fallback"))
        if c.get("exploration"):            reasons.append("exploration slot")
        c["allocation_trace"] = {
            "position": idx, "bucket": c.get("bucket"), "tier": c.get("tier"),
            "readiness_class": c.get("readiness"), "exposure_count": exp.get(nm, 0),
            "fatigue_state": "fatigued" if received24.get(nm, 0) >= fatigue_cap else "ok",
            "diversity_bucket": c.get("bucket"), "exploration": bool(c.get("exploration")),
            "propensity": None, "propensity_status": "absent_by_design",   # no acceptance probability (§9.4/§10.3)
            "allocation_reasons": reasons,
        }
    return slate


# ---- §7 candidate retrieval: staged budgets + source order (read-only over the sealed scorer) ------------
# Pilot budgets. Defaults are >> the ~100-user store, so the structured-retrieval cut NEVER bites at pilot
# scale — the mechanism is present (and would trim a huge pool) but is a no-op today. When it DOES bite it
# only drops the no-overlap (T5) tail the engine already discards, so the surfaced slate stays byte-identical.
RETRIEVAL_BUDGET = {"prefilter": 500, "structured": 500}
# §7.2 the seven-stage retrieval pipeline (documented; the deterministic in-memory prefilter is the stdlib
# stand-in for SQL/PostGIS/H3, and ANN/pgvector recall is infra out of scope — both marked accordingly).
RETRIEVAL_STAGES = [
    {"stage": "hard_prefilter",     "mechanism": "in-memory policy gates + geo radius (SQL/PostGIS/H3 = infra, deferred)", "pilot": "1000->100-250", "llm": False},
    {"stage": "structured_retrieval", "mechanism": "taxonomy overlap + active intents, ordered by source, capped by budget", "pilot": "100-250->30-80", "llm": False},
    {"stage": "ann_recall",         "mechanism": "pgvector embeddings — INFRA, not in the stdlib prototype", "pilot": "+top 50", "llm": False, "status": "blocked_infra"},
    {"stage": "feature_build",      "mechanism": "core_v2.build_features (7 canonical evidence groups)", "pilot": "30-80->10-30", "llm": False},
    {"stage": "ranking_slate",      "mechanism": "core_v2 directional/reciprocal + _slate diversify TOP_N=8", "pilot": "10-30->3-8", "llm": False},
    {"stage": "explanation",        "mechanism": "reason keys -> NL (_presentation), final slate only", "pilot": "final slate", "llm": "optional"},
    {"stage": "agent_probe",        "mechanism": "negotiate top candidates (allowlisted)", "pilot": "top 1-3", "llm": "small"},
]
# §7.1 the five retrieval sources. 1/2/5 are live person sources; 3/4 are DECLARED but pilot-disabled
# (groups/events/rooms are non-pilot decision types — kleal_intent.PILOT_DECISION_TYPES), so they retrieve
# zero candidates rather than being faked.
RETRIEVAL_SOURCES = {
    1: {"name": "active_intent_match", "enabled": True},
    2: {"name": "active_receiving_direct_interest", "enabled": True},
    3: {"name": "groups_with_capacity", "enabled": False, "note": "pilot-disabled (§15 group formation)"},
    4: {"name": "events_and_rooms", "enabled": False, "note": "pilot-disabled (§16); the online-room fallback is the T4 alternative"},
    5: {"name": "parent_adjacent_expansion", "enabled": True},
}

def _retrieval_source(intent, c, best=None):
    """§7.1 retrieval-source provenance for one candidate: 1 = its own active intent reciprocally matches;
    2 = a direct confirmed interest (best>=4); 5 = parent/sibling/adjacent only (best 1-3); 0 = no overlap
    (the tail, retrieved last / only to feed controlled expansion)."""
    try:
        if best is None:
            best = topical([str(t).lower() for t in (intent.get("topics") or [])],
                           [str(x).lower() for x in (c.get("interests") or [])])[0]
        if _reciprocal(intent, c):
            return 1
        if best >= 4:
            return 2
        if best >= 1:
            return 5
        return 0
    except Exception:
        return 0

_SOURCE_RANK = {1: 0, 2: 1, 5: 2, 0: 3}   # retrieval priority: reciprocal -> direct -> adjacent -> no-overlap tail

def _retrieve(intent, eligible, budget):
    """§7.2 structured-retrieval stage. Labels each eligible candidate with its §7.1 source, orders by
    retrieval priority (reciprocal -> direct interest -> parent/adjacent -> no-overlap tail), and caps at the
    budget. The ORDER is invisible to the surfaced slate (core_v2.search re-sorts totally); the CAP only ever
    drops the no-overlap tail that the engine already discards (T5), so the slate is byte-identical for any
    eligible pool <= budget. Returns (retrieved_pool, source_by_name, stats)."""
    topics = [str(t).lower() for t in (intent.get("topics") or [])]
    scored, source_by = [], {}
    for c in eligible:
        nm = str(c.get("name", "")).strip().lower()
        best = topical(topics, [str(x).lower() for x in (c.get("interests") or [])])[0]
        src = _retrieval_source(intent, c, best)
        source_by[nm] = src
        scored.append((_SOURCE_RANK.get(src, 3), -best, nm, c))
    scored.sort(key=lambda t: (t[0], t[1], t[2]))
    retrieved = [t[3] for t in scored[:max(0, int(budget))]]
    stats = {"eligible": len(eligible), "retrieved": len(retrieved), "budget": int(budget),
             "dropped_tail": len(eligible) - len(retrieved),
             "by_source": {s: sum(1 for v in source_by.values() if v == s) for s in (1, 2, 5, 0)}}
    return retrieved, source_by, stats

def _tier_analytics(rows):
    """§7.1: relevance distribution measured SEPARATELY WITHIN each semantic tier (tier is immutable
    provenance; analytics never promotes a tier). Over explain rows carrying a_to_b.lcb/coverage."""
    by = {}
    for m in (rows or []):
        t = m.get("tier")
        ab = m.get("a_to_b") or {}
        d = by.setdefault(t, {"lcbs": [], "covs": []})
        if isinstance(ab.get("lcb"), (int, float)):      d["lcbs"].append(ab["lcb"])
        if isinstance(ab.get("coverage"), (int, float)): d["covs"].append(ab["coverage"])
        d["count"] = d.get("count", 0) + 1
    out = []
    for t in sorted(by, key=lambda x: str(x)):
        d = by[t]; ls, cs = d["lcbs"], d["covs"]
        out.append({"tier": t, "count": d.get("count", 0),
                    "lcb_mean": round(sum(ls) / len(ls), 4) if ls else None,
                    "lcb_min": round(min(ls), 4) if ls else None,
                    "lcb_max": round(max(ls), 4) if ls else None,
                    "coverage_mean": round(sum(cs) / len(cs), 4) if cs else None})
    return out

def _retrieval_report(slate):
    """§7.2 pipeline + §7.1 source provenance summary for a response (additive, read-only)."""
    src_counts = {}
    for c in (slate or []):
        s = c.get("retrieval_source")
        src_counts[str(s)] = src_counts.get(str(s), 0) + 1
    return {"stages": RETRIEVAL_STAGES, "sources": RETRIEVAL_SOURCES, "budget": RETRIEVAL_BUDGET,
            "slate_size": len(slate or []), "slate_by_source": src_counts,
            "top_n": (_core.TOP_N if CORE_V2 else None)}


def _photo_by_name():
    """name (normalised) -> photo URL, for everything that shows a person by name."""
    out = {}
    for u in load_candidates():
        ph = u.get("photo")
        if ph:
            out[str(u.get("name", "")).strip().lower()] = ph
    return out


def _stamp_photo(cards):
    """Put each person's real photo onto their card, in ONE place.

    Cards are assembled in four different code paths (core_v2, the matching_core adapter, the legacy
    scorer and the §12 expansion fallback), and none of them carried a photo — so every candidate
    screen in the app fell back to the same stock portrait, shown under whatever name was ranked.
    Stamping here, after the slate is final, covers all four and cannot drift apart from them.

    The value is a short URL, never image bytes: users.json is re-read and held in memory to rank
    with, and a slate carrying base64 avatars would put the photo album on every search response."""
    by_name = _photo_by_name()
    if not by_name:
        return cards
    for c in cards or []:
        if isinstance(c, dict) and not c.get("photo"):
            ph = by_name.get(str(c.get("name", "")).strip().lower())
            if ph:
                c["photo"] = ph
    return cards


def _slate_budget(intent):
    """How many people the slate may hold for THIS request.

    Person-to-person keeps the eight it has always returned — that is the answer to «найди мне
    человека», and a group request is no reason to make that list longer. §15, though, forms a group
    out of the slate it is handed and never retrieves for itself, so a company of twelve cannot be
    assembled from eight candidates: the group ceiling has to be matched by the slate feeding it.
    A little headroom above the seats keeps the choice a choice rather than "everyone we found"."""
    if _decision_type(intent) != "group_formation":
        return None                                        # None -> the engine's own TOP_N
    try:
        total = int((intent or {}).get("groupSize") or 0)
    except (TypeError, ValueError):
        total = 0
    seats = max(0, total - 1) or kg._MAX_MVP_SIZE
    return max(_core.TOP_N, min(2 * kg._MAX_MVP_SIZE, seats + 4))


def match_candidates(intent, prof, ctx=None, diag=None):
    """Entry point. Policy hard gates run HERE (scoring only after ALLOW — spec §8), then §7 staged
    retrieval assembles the pool, then Core v2 scores it. KLEAL_CORE_V2=0 or an invalid config -> legacy
    scorer above, unchanged. The response is a superset of the legacy card contract.

    `diag`, when a dict is passed, is filled with the per-stage counts behind «почему никого нет».
    The rewrite dropped this parameter, which broke the admin funnel outright (TypeError: 4 args).
    It is restored with one stage the old funnel did not have and could not have shown: §7.2
    retrieval now caps the eligible pool at a budget BEFORE scoring, so `eligible` and `scored._in`
    legitimately differ and people can be lost between the gates and the ranker. A funnel that
    hides its narrowest stage is decoration."""
    if not CORE_V2:
        return match_candidates_legacy(intent, prof, ctx)
    ctx = ctx or {}
    intent = ki.normalize_for_scoring(intent)              # §5: untrusted-output hardening (idempotent; PARITY)
    now = ctx.get('now') or time.time()
    if kc.is_expired(intent, now):                         # §4.3 Lifecycle: an expired intent never ranks
        return []
    intent = kc.compile_intent(intent, _intent_identity(intent), ctx, now)  # §4.3 canonical blocks + TTL
    gate_ctx, self_name = _gate_ctx_and_self(ctx, prof)
    eligible, policy_by = [], {}                            # ALLOW + REVIEW are both discoverable (§8/§0)
    _pool = load_candidates()
    if diag is not None:
        diag['pool'] = len(_pool)
        diag['gates'] = {}
        diag['self'] = 0
        diag['review'] = 0
    for c in _pool:
        if self_name and str(c.get('name', '')).strip().lower() == self_name:
            if diag is not None:
                diag['self'] += 1
            continue                                       # the searcher never matches themselves
        decision, _why = _policy_decision(intent, c, gate_ctx)
        if decision == "BLOCK":
            if diag is not None:
                # _hard_gates has always returned the exact reason; both call sites threw it away.
                # It is the whole answer to «почему никого нет», and it costs a dict.
                k = str(_why or 'gate')
                diag['gates'][k] = diag['gates'].get(k, 0) + 1
            continue
        if decision == "REVIEW" and diag is not None:
            diag['review'] += 1
        policy_by[str(c.get('name', '')).strip().lower()] = decision
        eligible.append(c)
    if diag is not None:
        diag['eligible'] = len(eligible)
    ctx = dict(ctx)
    ctx.setdefault('now', now)                              # pinnable for deterministic replay
    ctx.setdefault('received24', _proposals_received_24h())  # proposal-fatigue counts -> readiness
    budget = int(ctx.get('retrieval_budget') or RETRIEVAL_BUDGET['structured'])   # §7.2 (test-overridable)
    retrieved, source_by, _rstats = _retrieve(intent, eligible, budget)           # §7.1 source order + §7.2 budget
    if diag is not None:
        diag['retrieved'] = len(retrieved)
        diag['retrieval_budget'] = budget
        # What the ranker was actually handed. The old funnel asserted scored._in == eligible; that
        # identity only held before staged retrieval existed.
        diag['scored'] = {'_in': len(retrieved), 'budget_dropped': max(0, len(eligible) - len(retrieved))}
    slate, _meta = _core.search(intent, prof or {}, ctx, retrieved, _H, _CORE_CFG,
                                top_n=_slate_budget(intent))
    if not slate and eligible:                             # never dead-end while anyone is eligible (§12) —
        slate = _expand_fallback(intent, prof or {}, ctx, eligible)   # over the FULL pool, never budget-starved
    slate = _apply_policy(slate, policy_by)
    slate = _allocate(slate, ctx, retrieved)              # §11 allocation (DORMANT at pilot defaults; before contracts)
    slate = _stamp_contracts(slate, intent, ctx)          # §4.6/§8.3/§4.12 additive contract overlays
    for c in slate:                                        # §7.1 retrieval-source provenance (additive)
        c.setdefault("retrieval_source", source_by.get(str(c.get("name", "")).strip().lower(), 0))
    _stamp_photo(slate)                                    # the person's real face, from the store row
    _stamp_allocation_trace(slate, ctx, _alloc_cfg(ctx))  # §11.2 step 6 allocation reasons (additive, read-only)
    if diag is not None:
        diag['slate'] = len(slate)
        diag['meta'] = dict(_meta or {})                   # engine, config_version, domain, config_sha
    return slate

def _apply_policy(slate, policy_by):
    """Stamp each card with its policy_decision + a typed allocation_action (§0 output table). A REVIEW
    candidate stays in discovery but is forced non-proposable — outreach only after the separate track."""
    for c in slate:
        decision = policy_by.get(str(c.get("name", "")).strip().lower(), c.get("policy") or "ALLOW")
        c["policy"] = decision
        if decision == "REVIEW":
            c["can_outreach"] = False
            if not c.get("note"):
                c["note"] = "Needs a safety/legal review before outreach"
            c.setdefault("trace", {})["policy"] = "REVIEW"
        else:
            c.setdefault("trace", {}).setdefault("policy", decision)
        c["allocation_action"] = _allocation_action(c)
        c["decision_class"] = _decision_class(c)          # §9.6 read-only 5-way label (additive)
    return slate

def _relationship_edge(name, uid="me", scope=None):
    """Advisory §4.12 pair edge from the session outcome store (new/contact/friend/repeat/avoid/block).
    NEVER authoritative — the real cooldown/block stays the matching hard gate; this is metadata only."""
    key = str(name or "").strip().lower()
    sess = _session(uid)
    outs = [e for e in (SESSION.get("_outcomes") or []) if e.get("name") == key]
    # §17.2 mode isolation: prefer a purpose-scoped feedback key (e.g. name::dating) so a dating decline never
    # flips a friendship edge; fall back to the bare name (legacy/domain-agnostic feedback stays byte-identical).
    fbmap = sess.get("feedback") or {}
    fb = None
    if scope:
        fb = fbmap.get("%s::%s" % (name, scope)) or fbmap.get("%s::%s" % (key, scope))
    fb = fb or fbmap.get(name) or fbmap.get(key)
    acc = sum(1 for e in outs if e.get("stage") == "accepted") or (1 if fb == "accepted" else 0)
    comp = sum(1 for e in outs if e.get("stage") == "completed")
    ov = {"blocked": key in {str(b).lower() for b in (sess.get("blocked") or [])},
          "rejected": fb == "rejected", "accepted": acc, "completed": comp,
          "cooldown_days": COOLDOWN_DAYS,
          "last_ts": (outs[-1]["ts"] if outs else None)}
    return kc.build_relationship_edge([uid, key], ov, scope=scope)

def _stamp_contracts(slate, intent, ctx):
    """§4 additive overlays on each returned card: a purpose-bound ProfileView (§8.3), a versioned
    CandidateSnapshot (§4.6) and the pair RelationshipEdge (§4.12). Wrapped PER CARD so a projection/
    snapshot error degrades to a missing sub-key — never a bubbled exception that empties the slate."""
    domain = (intent.get("identity") or {}).get("domain") or _core.infer_domain(intent, cat_of)
    uid = (ctx or {}).get("uid", "me")
    now_ts = (ctx or {}).get("now") or time.time()
    received24 = (ctx or {}).get("received24") or {}
    cfg_meta = {"config_version": (_CORE_CFG or {}).get("config_version"),
                "config_sha": ((_CORE_CFG or {}).get("_sha256") or "")[:12]}
    topics = intent.get("topics") or []
    live_by = {str(u.get("name", "")).strip().lower(): u for u in load_candidates()}   # full fields for §10 factors
    for c in slate:
        try:
            nm_key = str(c.get("name", "")).strip().lower()
            c["snapshot"] = kc.build_candidate_snapshot(c, intent, cfg_meta)
            c["profile_view"] = kc.build_profile_view(c, domain)
            c["relationship"] = _relationship_edge(c.get("name"), uid, scope=domain)
            for k, v in kt.enrich_card(topics, c.get("interests") or [],       # §6 typed edge + expansion + complementary
                                       role_a=intent.get("role"), role_b=c.get("role")).items():
                c.setdefault(k, v)                        # additive only — never touches band/tier/lcb/can_outreach
            c.setdefault("completion_factors", kcf.completion_factors(   # §10.2 transparent operational signals (no rating)
                live_by.get(nm_key, c), intent, now_ts, received24.get(nm_key, 0)))
            c.setdefault("readiness_explain", kcf.READINESS_EXPLAIN.get(c.get("readiness")))  # §10.1
            for _k in _PRECISE_LOCATION_KEYS:             # §8.4: home/work/exact location never in the payload
                c.pop(_k, None)                           # no-op today (no fixture carries these) — hard barrier later
        except Exception:
            pass                                          # degrade gracefully; the card stays valid
    return slate

# ---- §12 controlled expansion: the ordered ladder as a PLAN + step tagging (additive; the executed
# _expand_fallback below is unchanged and NEVER a dead-end). The PLAN is one-axis-per-step / cheapest-first;
# the EXECUTED fallback still relaxes two axes at once (adjacentAllowed + exactMatchRequired) and is tagged
# after the fact. provenance tier is KEPT (never re-tiered — sha-pinned); parent outreach needs broad consent;
# adjacent -> discovery, not an inbox; safety/age/consent/block/language/purpose are NEVER relaxed.
_LADDER = [
    {"step": 1, "axis": "exact_entity_role_same_time_zone", "relaxes": "none", "provenance_tier": "T0/T1",
     "outreach": {"mode": "personal", "broad_consent_required": False},
     "explanation_ru": "Точное совпадение сущности/роли, то же время и зона.",
     "explanation_en": "Exact entity/role at the same time and zone."},
    {"step": 2, "axis": "adjacent_sibling_entity", "relaxes": "entity_exactness", "provenance_tier": "T2/T3",
     "outreach": {"mode": "discovery", "broad_consent_required": True},
     "explanation_ru": "Смежная/родственная сущность — только discovery; personal лишь при broad consent.",
     "explanation_en": "Adjacent/sibling entity — discovery only; personal outreach needs broad consent."},
    {"step": 3, "axis": "parent_activity_category", "relaxes": "category_breadth", "provenance_tier": "T2",
     "outreach": {"mode": "discovery", "broad_consent_required": True},
     "explanation_ru": "Родительская категория — более широкий вариант; outreach только при broad consent.",
     "explanation_en": "Parent activity/category — a broader option; outreach needs broad consent."},
    {"step": 4, "axis": "widen_time_or_distance", "relaxes": "time_or_radius", "provenance_tier": "none",
     "outreach": {"mode": "discovery", "broad_consent_required": False},
     "explanation_ru": "Увеличить время или радиус в пределах согласия.",
     "explanation_en": "Increase time or distance within consent."},
    {"step": 5, "axis": "change_format", "relaxes": "format", "provenance_tier": "none",
     "outreach": {"mode": "discovery", "broad_consent_required": False},
     "explanation_ru": "Сменить формат: 1:1→малая группа или offline→online, если разрешено.",
     "explanation_en": "Change format: 1:1->small group or offline->online, if allowed."},
    {"step": 6, "axis": "event_room_group_alternative", "relaxes": "solution_type", "provenance_tier": "T4",
     "outreach": {"mode": "none", "broad_consent_required": False},
     "explanation_ru": "Событие/комната/группа как альтернативный способ закрыть запрос.",
     "explanation_en": "Event/room/group as an alternative solution type."},
    {"step": 7, "axis": "saved_search_notify", "relaxes": "immediacy", "provenance_tier": "none",
     "outreach": {"mode": "none", "broad_consent_required": False},
     "explanation_ru": "Сохранить поиск и уведомить позже.",
     "explanation_en": "Save the search and notify later."},
]
_LADDER_BY_STEP = {s["step"]: s for s in _LADDER}
_DOTA_EXAMPLE = [   # §12.3 — a LoL player never gets a personal proposal disguised as a close Dota match
    {"tier": "T0", "row": "active Dota 2 intent, role support, same server/time"},
    {"tier": "T1", "row": "confirmed Dota 2 interest + games receiving policy"},
    {"tier": "T2", "row": "other MOBA players — only as a broader option, never 'almost Dota'"},
    {"tier": "T4", "row": "active Dota room / watch party / group queue (alternative solution type)"},
    {"tier": "No supply", "row": "clarify: unranked ok? another evening? save the search?"},
]

def expansion_ladder(intent, ctx=None):
    """§12.2 the ORDERED expansion ladder as a read-only PLAN (never re-scores / re-tiers / mutates). Each
    step relaxes ONE soft axis, cheapest-first; safety/age/consent/block/language/purpose are never relaxed."""
    intent = intent or {}
    fb = intent.get("fallback") if isinstance(intent.get("fallback"), dict) else {}
    dims = [str(d).lower() for d in (fb.get("allowed_dimensions") or [])]
    consent = bool(fb.get("consent") or intent.get("broadConsent"))
    exact = bool(intent.get("exactMatchRequired"))
    out = []
    for s in _LADDER:
        st = dict(s, outreach=dict(s["outreach"]), cost_rank=s["step"])
        step = s["step"]
        if step == 1:
            app = True
        elif step == 2:
            app = (not exact) and ("adjacent" in dims or "related" in dims or intent.get("adjacentAllowed", True))
        elif step == 3:
            app = (not exact) and ("broader" in dims or intent.get("broadAllowed", True))
        elif step == 4:
            app = bool(intent.get("radiusKm")) or str(intent.get("mode")) == "offline"
        elif step == 5:
            app = bool(intent.get("allowOnlineFallback")) or str(intent.get("mode")) == "offline"
        else:
            app = True
        st["applicable"] = bool(app)
        if st["outreach"].get("broad_consent_required") and not consent:
            st["outreach"]["note"] = "broad consent not given — discovery only (no inbox)"
        out.append(st)
    return {"ladder": out, "dota_example": _DOTA_EXAMPLE,
            "principles": {"one_axis_per_step_in_plan": True, "cheapest_first": True,
                           "executed_fallback": "multi-axis (adjacentAllowed+exactMatchRequired), tagged after the fact",
                           "never_relaxes": ["safety", "age", "mutual_consent", "block", "critical_language", "purpose_isolation"]}}

def _ladder_step_for_card(card):
    """Map an executed fallback / online-room card to its §12.2 ladder step. PURE + exception-safe (only
    c.get() reads) so a tagging error can never regress the never-dead-end fallback into an empty slate."""
    c = card if isinstance(card, dict) else {}
    fb = str(c.get("fallback") or "")
    tier = str(c.get("tier") or "")
    if fb == "broader":
        return 2 if tier == "T3" else 3        # T3 adjacent -> step 2; T2 sibling/parent -> step 3
    if fb == "alternative":
        return 3
    if c.get("kind") == "alternative_solution_type":
        return 6
    return None

def _tag_ladder(cards):
    """Stamp ladder_step/axis/relaxes on executed fallback cards, additively, without reordering/dropping."""
    for c in (cards or []):
        if not isinstance(c, dict):
            continue
        step = _ladder_step_for_card(c)
        if step is not None:
            row = _LADDER_BY_STEP.get(step) or {}
            c.setdefault("ladder_step", step)
            c.setdefault("ladder_axis", row.get("axis"))
            c.setdefault("ladder_relaxes", row.get("relaxes"))
    return cards

def _expand_fallback(intent, prof, ctx, eligible):
    """§12 controlled expansion — a search must never dead-end. Over the SAME hard-gate-eligible pool
    (eligibility/safety gates are NEVER relaxed): (1) re-score with adjacent tiers allowed and the
    discovery floor dropped, surfacing wider/adjacent people; (2) if there is no topical overlap at all,
    offer the nearest available people as an explicit 'different category' suggestion. Every card is
    tagged `fallback` (+ a note) so the UI can say the search was broadened — never a silent random pick."""
    if not eligible or not CORE_V2:
        return []
    relaxed = dict(intent, adjacentAllowed=True, exactMatchRequired=False)
    slate, _m = _core.search(relaxed, prof, ctx, eligible, _H, _RELAXED_CFG or _CORE_CFG)
    if slate:                                              # (1) broader / adjacent, below the normal floor
        for c in slate:
            c["fallback"] = "broader"
            c["note"] = "Broader match — a wider or adjacent category"
        return _tag_ladder(slate)                          # §12.2 tag with the ladder step (2 adjacent / 3 parent)
    # (2) no topical overlap anywhere -> nearest available eligible people, marked as a different category
    now_ts = (ctx or {}).get("now") or time.time()
    avail = sorted((c for c in eligible if not _core.is_paused(c, now_ts)),
                   key=lambda c: (0 if c.get("open") else 1,
                                  float(c["km"]) if isinstance(c.get("km"), (int, float)) else 99.0,
                                  str(c.get("name") or "")))
    domain = _core.infer_domain(intent, cat_of)
    out = []
    for c in avail[:_core.TOP_N]:
        ints = c.get("interests") or []
        out.append({
            "name": c.get("name"), "score": 0, "tier": "T4", "kind": "alternative",
            "km": c.get("km"), "vibe": c.get("vibe"), "open": c.get("open"),
            "verified": c.get("verified"), "age": c.get("age"), "interests": ints,
            "role": c.get("role"), "dealBreakers": c.get("dealBreakers"),
            "reasons": ["different interests — a broader suggestion"], "agree": False,
            "note": "Broader suggestion — a different category (no direct match right now)",
            "bucket": (cat_of(ints[0])[0] if ints else "other"),
            "band": "needs_clarification", "band_ru": "Нужно уточнение", "band_en": "Needs clarification",
            "reasons_ru": ["другие интересы — более широкий вариант"],
            "reasons_en": ["different interests — a broader suggestion"], "gap_ru": None, "gap_en": None,
            "coverage": 0.0, "lcb": 0.0, "reciprocal": 0.0, "unknowns": [], "can_outreach": False,
            "readiness": "unknown", "readiness_ru": "доступность не настроена",
            "readiness_en": "availability not set", "fallback": "alternative",
            "trace": {"tier": "T4", "policy": "ALLOW", "domain": domain, "fallback": "alternative"},
        })
    return _tag_ladder(out)                                 # §12.2 tag the alternative cards with the ladder step

def _expand_stepwise(intent, prof, ctx, eligible, min_cards=1):
    """§12.1 one-axis-per-step, cheapest-first: relax EXACTLY ONE axis per step over the SAME hard-gate-eligible
    pool (safety/age/consent/block/language/purpose NEVER relaxed), stopping at the first step yielding >=
    min_cards. Unlike _expand_fallback (which drops adjacent+exactness together), step 2 relaxes ONLY adjacency.
    Returns (cards, step). Additive — the pool is byte-identical; only discovery breadth widens."""
    if not eligible or not CORE_V2:
        return [], None
    for step, relaxed in ((2, dict(intent, adjacentAllowed=True)),
                          (3, dict(intent, adjacentAllowed=True, broadAllowed=True)),
                          (4, dict(intent, adjacentAllowed=True, broadAllowed=True, exactMatchRequired=False))):
        slate, _m = _core.search(relaxed, prof, ctx, eligible, _H, _RELAXED_CFG or _CORE_CFG)
        if len(slate) >= min_cards:
            for c in slate:
                c["fallback"] = "broader"; c["ladder_step"] = step
            return _tag_ladder(slate), step
    return [], None

def _online_fallback(intent):
    """When 0 offline candidates: offer to go live + ways to broaden — so the user never hits a dead end.
    §5.1 row4: the offline intent is NEVER silently swapped to online — going live is pre-approved only
    when the user explicitly said online is ok (allowOnlineFallback); otherwise it's an explained offer."""
    topics = ', '.join(intent.get('topics') or []) or 'this'
    approved = bool((intent or {}).get('allowOnlineFallback'))
    return {
        # §7.1 tier table: an online room is the T4 "alternative solution type" (another way to close the
        # intent, not a person) — no personal outreach; source 4 (events/rooms) surfaced as this alternative.
        "room": {"title": "Live room: " + intent.get('title', 'meet'), "approved": approved,
                 "tier": "T4", "kind": "alternative_solution_type", "retrieval_source": 4, "ladder_step": 6,
                 "options": [{"id": "voice", "label": "Start a voice room"},
                             {"id": "watch", "label": "Watch together online"}]},
        "suggestions": [   # §12.2: each broaden option tagged with its ladder step
            {"id": "inexact",  "label": "Allow less-exact matches", "ladder_step": 2},
            {"id": "adjacent", "label": "Include adjacent topics", "ladder_step": 2},
            {"id": "radius",   "label": "Widen the distance", "ladder_step": 4},
            {"id": "wait",     "label": "Save this search & notify me", "action": "save_search", "ladder_step": 7},
        ],
        "note": (("Online is pre-approved for this search — " if approved else "")
                 + "No offline matches for %s right now — go live, or broaden the search." % topics),
    }

def _section5_addendum(intent, text, cands):
    """§5.1/§5.2 additive response keys: the confirmation summary + the single rule-based clarification
    question for the compiled intent. Never mutates the intent or the slate."""
    _o, cons = ki.extract_constraints(text or "", intent)
    return {"intent_summary": ki.intent_summary(intent, cons),
            "clarification": ki.clarification_policy(intent, cons, has_results=bool(cands)),
            "minimally_sufficient": ki.minimally_sufficient(intent)}

def agent_plan(query, prof, ctx=None, override=None):
    intent = parse_intent(query)
    if isinstance(override, dict):                 # broaden the search scope (radius / inexact / adjacent)
        for k, v in override.items():
            if k in ('radiusKm', 'verifiedOnly', 'minAge', 'maxAge', 'requiredLanguages', 'mode',
                     'exactMatchRequired', 'adjacentAllowed', 'broadAllowed'):
                intent[k] = v
    ctx = ctx or {}
    intent, _cons = ki.extract_constraints(query, intent)   # §5.1: merge additive soft/proposed/fallback keys
    intent = kc.compile_intent(intent, _intent_identity(intent), ctx, ctx.get('now') or time.time())  # §4.3 blocks echoed
    cands = match_candidates(intent, prof or {}, ctx)
    res = {"intent": intent, "candidates": cands, "snapshot": _request_snapshot(intent)}
    res.update(_section5_addendum(intent, query, cands))
    res["retrieval"] = _retrieval_report(cands)           # §7 staged pipeline + source provenance
    res["expansion"] = expansion_ladder(intent, ctx)      # §12 controlled-expansion ladder (plan)
    if not cands:
        res["fallback"] = _online_fallback(intent)
    return res

# ---- Agent-to-agent intro (Phase 2): the candidate's agent confirms + an icebreaker opener ----
INTRO_PROMPT = '''You are the AI agent of user B. User A wants to meet for the activity below, and B's agent has agreed.
Write (a) as B's agent, a warm one-sentence confirmation to A's agent, and (b) a friendly one-sentence icebreaker
opener B could send A. Return ONLY JSON: {"reply":"...","opener":"..."}. English, lively, no markdown.'''
def agent_intro(intent, cand):
    topics = ', '.join(intent.get('topics') or intent.get('tags') or []) or 'this'
    ctx = 'Activity: %s (%s). Person B interests: %s. Vibe: %s.' % (
        intent.get('title', 'a meetup'), topics, ', '.join(cand.get('interests') or []), cand.get('vibe', ''))
    try:
        cfg = MODEL_ID
        raw = llm_complete(cfg, [{"role": "system", "content": INTRO_PROMPT}, {"role": "user", "content": ctx}], 0.6)
        obj = base._extract_json(raw)
        if isinstance(obj, dict) and obj.get('opener'):
            return {"reply": str(obj.get('reply', ''))[:200], "opener": str(obj.get('opener', ''))[:200]}
    except Exception:
        pass
    return {"reply": "My user is up for it — it works on their side.",
            "opener": "Hey! Looks like we both like " + topics + " — want to make a plan?"}

# ---- Agent-to-agent NEGOTIATION (LLM): the candidate's agent decides accept/reject, with a reason ----
NEGOTIATE_PROMPT = '''You are the AI agent of user B. User A sends an intent (a plan/activity) and wants to meet.
Decide, on B's behalf, whether B accepts. Consider: does the activity fit B's interests? do time and place work?
is B open/available right now? would it break any of B's deal-breakers (if so -> reject)?
Return ONLY JSON (no prose): {"decision":"accept"|"reject","reason":"one short sentence why","reply":"one lively sentence from B's agent to A's agent, or null if reject"}.'''

def negotiate_one(intent, cand):
    # §23.2.7 — the accept/reject VERDICT is a DETERMINISTIC protocol decision (availability from the readiness
    # engine + a score threshold), never delegated to the LLM. The LLM is used ONLY to phrase the opener reply.
    # So the agent-to-agent decision is replay-stable and testable; free-text is confined to `reply`.
    avail = (cand.get('readiness') == 'open_now') or bool(cand.get('open'))
    agree = bool(avail and cand.get('score', 0) >= 45)
    reason = 'good fit and free today' if agree else ('not free today' if not avail else 'fit is a bit weak')
    reply = None
    if agree:
        topics = ', '.join(intent.get('topics') or intent.get('tags') or []) or 'this'
        a = 'INTENT FROM A: %s. Topics: %s. Time: %s. Place: %s. Format: %s.' % (
            intent.get('title', ''), topics, intent.get('time', ''), intent.get('place', ''), intent.get('format', ''))
        b = 'USER B: interests %s; vibe %s; open to meet today: yes; deal-breakers: %s.' % (
            ', '.join(cand.get('interests') or []) or 'unknown', cand.get('vibe', ''),
            ', '.join(cand.get('dealBreakers') or []) or 'none')
        try:
            o = base._extract_json(llm_complete(MODEL_ID, [{"role": "system", "content": NEGOTIATE_PROMPT},
                                                            {"role": "user", "content": a + "\n" + b}], 0.4))
            if isinstance(o, dict) and o.get('reply'):
                reply = str(o.get('reply'))[:200]   # phrasing ONLY — never flips the deterministic verdict
        except Exception:
            pass
    return {"agree": agree, "reason": reason, "reply": reply, "decided": True}

def _outreach_ok(intent, c):
    """Tier/consent gate for PERSONAL outreach (spec §7 tier table + §12): T0/T1 always, T2 only
    with broad consent, T3+/T5 never. Mirrors core_v2.search's outreach_tier_ok so the send path
    enforces the same consent rule the slate does."""
    if not CORE_V2:
        return True
    topics = [str(t).lower() for t in (intent.get('topics') or [])]
    tier = _core.assign_tier(intent, c, topics, _H)
    return tier in ('T0', 'T1') or (tier == 'T2' and bool(intent.get('broadConsent')))

_PTYPE_OF_DECISION = {"person_to_person": "person", "intent_to_intent": "person",
                      "group_formation": "group", "intent_to_event": "event", "intent_to_room": "room",
                      "intent_to_venue": "venue"}   # §16 additive (pilot-off); venue in kc.PROPOSAL_TYPES

def _receiving_send_gate(intent, live, now_ts):
    """§4.4 send-boundary enforcement of the EXTENDED ReceivingPolicy fields (beyond the base readiness
    that core_v2 already applies). ABSENT-FIELD-PERMISSIVE: a field only gates when the user actually set
    it. (block/avoid/cooldown stay the authoritative hard gate; not re-checked here.) Returns (ok, reason)."""
    r = live.get("receiving") if isinstance(live.get("receiving"), dict) else {}
    if not r:
        return True, None
    ptypes = r.get("allowed_proposal_types")
    if isinstance(ptypes, list) and ptypes:                    # (a) allowed_proposal_types
        want = _PTYPE_OF_DECISION.get(_decision_type(intent), "person")
        if want not in ptypes and not (want == "person" and "small_group" in ptypes):
            return False, "receiving policy: %r proposals not accepted" % want
    scope = r.get("location_scope")
    city = (intent.get("location_block") or {}).get("city")    # (b) location_scope — only when a real city is known
    if isinstance(scope, list) and scope and city:
        if not any(str(s).lower() in str(city).lower() or str(city).lower() in str(s).lower() for s in scope):
            return False, "receiving policy: outside allowed location scope"
    per7d = (r.get("proposal_budget") or {}).get("per_7d")     # (c) per_7d budget via the 7-day proposal log
    if per7d is not None:
        key = str(live.get("name", "")).strip().lower()
        log = SESSION.get("_proposals") or {}
        if sum(1 for t in (log.get(key) or []) if now_ts - t < 7 * 86400) >= int(per7d):
            return False, "receiving policy: 7-day proposal budget reached"
    return True, None

def _negotiate_precheck(intent, cands, now_ts=None):
    """Receiving-policy AND eligibility enforcement BEFORE any proposal goes out (spec §8.2: policy
    revalidation immediately before sending; §23.2 #12: no proposal without a receiving-policy check).
    /api/agent/negotiate accepts client-supplied candidates verbatim, so each is re-resolved against
    the LIVE store, re-run through the eligibility hard gates + the tier/consent outreach gate, then
    readiness is computed and the parallel wave capped from config (default 2, urgent 3).
    Returns (to_send, decided_without_sending)."""
    now_ts = now_ts or time.time()
    store = {str(u.get('name', '')).strip().lower(): u for u in load_candidates()}
    received = _proposals_received_24h()
    gate_ctx, _ = _gate_ctx_and_self({})
    out_cfg = ((_CORE_CFG or {}).get('outreach') or {})
    soon = any(w in str(intent.get('time', '')).lower() for w in SOON_WORDS)
    cap = int(out_cfg.get('urgent_same_day_parallel_proposals' if soon else
                          'default_parallel_proposals') or (3 if soon else 2))
    if not soon and intent.get('broadConsent'):            # §13.2 Wave 3: user-allowed expansion raises the cap
        cap = max(cap, 3)                                  # keeps the config-derived base; never a hardcoded 2/3
    wctx = {"urgent": soon, "expansion": bool(intent.get('broadConsent'))}
    to_send, decided, sent = [], [], 0
    for c in cands:
        nm = str(c.get('name', '')).strip().lower()
        live = store.get(nm, c)
        # §8.2 revalidation at the SEND boundary — never trust the caller's candidate list.
        if not (nm or c.get('name')):
            decided.append(dict(c, agree=False, decided=True, readiness="blocked",
                                reason="not eligible: no candidate id", reply=None)); continue
        live = dict(live); live['name'] = live.get('name') or c.get('name') or ''
        ok, why = _hard_gates(intent, live, gate_ctx)          # block / age / dating / language / radius…
        if not ok:
            # §8.2 POLICY_CHANGED: the caller handed us a proposable candidate that the LIVE store now blocks
            decided.append(dict(c, agree=False, decided=True, readiness="blocked",
                                code="POLICY_CHANGED", reason="not eligible: %s" % why, reply=None)); continue
        if _cross_purpose_blocked(intent, live):               # §8.1 mode isolation — parity with retrieval BLOCK
            decided.append(dict(c, agree=False, decided=True, readiness="blocked",
                                code="POLICY_CHANGED", reason="not eligible: cross-purpose isolation", reply=None)); continue
        pcd = int(ALLOCATION_CONFIG.get("pair_cooldown_days") or 0)   # §11.1 general same-pair repeat cooldown (0 = off)
        if pcd > 0 and any(now_ts - t < pcd * 86400 for t in ((SESSION.get("_proposals") or {}).get(nm) or [])):
            decided.append(dict(c, agree=False, decided=True, readiness="pair_cooldown",
                                reason="same-pair cooldown (proposed within %d days)" % pcd, reply=None)); continue
        if not _outreach_ok(intent, live):                     # tier/consent: no personal proposal at T2-no-consent / T3+
            decided.append(dict(c, agree=False, decided=True, readiness="discovery_only",
                                reason="discovery only — needs broad consent for this match", reply=None)); continue
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
        pol_ok, pol_why = _receiving_send_gate(intent, live, now_ts)    # §4.4 extended receiving fields
        if not pol_ok:
            decided.append(dict(c, agree=False, decided=True, readiness="policy_capped",
                                reason=pol_why, reply=None)); continue
        tf_ok, tf_why = _time_feasible(intent, live, now_ts)   # §8.4 slot feasibility (absent-permissive)
        if not tf_ok:
            decided.append(dict(c, agree=False, decided=True, readiness="time_infeasible",
                                reason=tf_why, reply=None)); continue
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
    # §13.1/§13.2: stamp the typed action (string) + detail + wave ADDITIVELY (new keys only — never touches
    # name/agree/reason/readiness/reply, membership or order, so NEG1-4 / C4-SEND1 stay byte-identical).
    for _c, _ints in ((to_send, True), (decided, False)):
        for c in _c:
            ta = kp.type_action(c, _ints)
            c["action"], c["action_detail"], c["wave"] = ta["action"], ta, kp.assign_wave(c, wctx)
    return to_send, decided

# ---- §8.2 revalidation checkpoints + §8.4 time / reveal-ladder (read-only; reuse the same gate stack) ----
def _to_utc_min(win, key):
    """Minutes-since-midnight in UTC for a 'HH:MM' + tz_offset_min window field. None if unreadable."""
    try:
        hh, mm = str(win.get(key)).split(":")[:2]
        return (int(hh) * 60 + int(mm) - int(win.get("tz_offset_min", 0))) % 1440
    except Exception:
        return None

def _time_feasible(intent, live, now_ts):
    """§8.4 slot feasibility with a travel buffer. ABSENT-PERMISSIVE: only gates when BOTH sides carry a
    window (no fixture does -> no-op -> byte-safe). UTC-normalized by each side's tz_offset_min. PARTIAL:
    no DST table / travel-mode routing (infra)."""
    iw = intent.get("window") or {}
    cw = live.get("availability") or {}
    if not (iw.get("from") and cw.get("from")):
        return True, None
    a0, a1, b0, b1 = _to_utc_min(iw, "from"), _to_utc_min(iw, "until"), _to_utc_min(cw, "from"), _to_utc_min(cw, "until")
    if None in (a0, a1, b0, b1):
        return True, None
    overlap = min(a1, b1) - max(a0, b0)
    need = int(iw.get("min_duration_min") or 0) + int(intent.get("travel_buffer_min") or 0)
    if overlap < max(need, 1):
        return False, "no feasible time slot"
    return True, None

def _revalidate_disclosure(intent, live, checkpoint):
    """§8.2 #6 / §8.4 disclosure ladder: exact place/contact revealed ONLY at 'full' stage AND after a
    mutual-accept Match Capsule exists (mutual consent). Clamped by the candidate's receiving.disclosure_stage."""
    req = _REVEAL_STAGE.get(checkpoint, "limited_profile")
    cand_stage = (live.get("receiving") or {}).get("disclosure_stage")
    allowed = kc._min_disclosure(req, cand_stage) if cand_stage else req
    nm = str(live.get("name", "")).strip().lower()
    mutual = any(nm in {str(p).strip().lower() for p in (m.get("participants") or [])} for m in _match_capsules())
    reveal_ok = (allowed == "full") and mutual
    return {"requested": req, "allowed": allowed, "exact_place_ok": bool(reveal_ok),
            "reason": None if reveal_ok else "exact place/contact requires mutual accept (Match Capsule) + full disclosure"}

def revalidate(intent, candidate, checkpoint="profile_open", now_ts=None):
    """§8.2 #3-#7: re-decide ONE (intent, candidate) pair against the LIVE store at a checkpoint, reusing the
    exact retrieval/send gate stack. Read-only. code == 'POLICY_CHANGED' iff the live re-decision is STRICTER
    than the caller's last-seen baseline — so a caller never silently continues an old transaction (§8.2)."""
    now_ts = now_ts or time.time()
    checkpoint = checkpoint if checkpoint in _REVAL_CHECKPOINTS else "profile_open"
    cand = candidate or {}
    nm = str(cand.get("name", "")).strip().lower()
    store = {str(u.get("name", "")).strip().lower(): u for u in load_candidates()}
    live = dict(store.get(nm, cand)); live["name"] = live.get("name") or cand.get("name") or ""
    gate_ctx, _ = _gate_ctx_and_self({})
    decision, why = _policy_decision(intent, live, gate_ctx)
    domain = _core.infer_domain(intent, cat_of) if CORE_V2 else None
    rdy = (_core.readiness_state(live, domain, now_ts, _CORE_CFG, _proposals_received_24h().get(nm, 0))
           if CORE_V2 else ("open_now" if live.get("open") else "busy"))
    base_dec, base_rdy = str(cand.get("policy") or "ALLOW").upper(), str(cand.get("readiness") or "open_now")
    changed = (_DEC_RANK.get(decision, 0) > _DEC_RANK.get(base_dec, 0)
               or (base_rdy == "open_now" and rdy != "open_now"))
    disclosure = _revalidate_disclosure(intent, live, checkpoint)
    out = {"checkpoint": checkpoint, "name": live["name"], "decision": decision, "readiness": rdy,
           "disclosure": disclosure,
           "allocation_action": _allocation_action({"policy": decision,
                                                     "can_outreach": (decision == "ALLOW" and rdy == "open_now")})}
    out["code"], out["reason"] = ("POLICY_CHANGED", (why or "no longer open (%s)" % rdy)) if changed else ("OK", why)
    return out

# ---- §14 additive transaction stamps on a negotiation card (never touch agree/reason/readiness/name) ----
def _stamp_txn(card, race_case):
    """§14.4: attach the coarse race outcome to a card and move its proposal state. PUBLIC-SAFE — only the
    opaque public_reason is carried (no granular gate reason leaks into a cross-agent surface)."""
    p = card.get('proposal') or {}
    r = ks.resolve_race(race_case, p.get('state'))
    card['txn'] = {"error_code": r["error_code"], "public_reason": r["public_reason"],
                   "state": r["to"], "leak": r["leak"]}
    if card.get('proposal') and r.get('applied'):
        card['proposal']['state'] = r['to']
        card['proposal']['version'] = int(card['proposal'].get('version', 1)) + 1
    return card

def _stamp_accept(card):
    """§14.1: a winning accept moves the proposal SENT->ACCEPTED (+version) and records a MUTUAL match state.
    Pure metadata for the transaction view; leaves agree/reason/readiness/name untouched."""
    p = card.get('proposal')
    if p is not None:
        ks.apply_transition(p, 'proposal', 'ACCEPTED')     # SENT->ACCEPTED (+version bump); no-op if not SENT
    card['match_state'] = 'MUTUAL' if ks.can_transition('match', 'PENDING_DISCLOSURE', 'MUTUAL') else 'PENDING_DISCLOSURE'
    card['txn'] = {"error_code": "OK", "public_reason": None, "state": (card.get('proposal') or {}).get('state'),
                   "leak": False}
    return card

def negotiate_candidates(intent, cands):
    top = cands[:5]
    to_send, decided = _negotiate_precheck(intent, top)
    snap = _request_snapshot(intent)
    for c in to_send:
        _log_proposal(c.get('name'))                   # a real proposal reaches this person's agent
        _log_exposure(c.get('name'))                   # §11.1 impression log (send boundary; not in match_candidates)
        _record_outcome(c.get('name'), 'proposed')     # §1 outcome lifecycle: a proposal went out
        c['proposal'] = kc.build_proposal(intent, c)   # §4.7 structured proposal (idempotency + disclosure clamp)
        c['proposal']['state'] = ks.next_state('proposal', 'CREATED', 'PROPOSE_CONNECTION') or 'SENT'  # §14.1 CREATED->SENT
        c['envelope'] = kp.build_envelope(c['proposal'], snap, purpose=(intent.get('goal') or {}).get('purpose'),
                                          disclosure=c['proposal'].get('allowed_disclosure'),
                                          action="PROPOSE_CONNECTION", structured_fields=c['proposal'].get('payload'),
                                          rendering_key="proposal.propose_connection")   # §13.1 typed message envelope
    def work(c):
        v = negotiate_one(intent, c); c = dict(c); c.update(v); return c
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            done = list(ex.map(work, to_send))
    except Exception:
        done = [dict(c, **negotiate_one(intent, c)) for c in to_send]
    active_plans = [{"window": m.get("plan_window")} for m in _match_capsules()]   # §13.3 conflicting-plan guard input
    accept_policy = ks.concurrent_accept_policy(intent)   # §14.3 how simultaneous accepts resolve (default: multiple)
    for c in done:                                     # B's agent accepted -> §8.2 #4 re-gate at accept, then match
        c['action'] = kp.map_decision_to_action(c)     # §13.1 LLM decision -> typed ACCEPT/DECLINE/COUNTER_*
        if c.get('agree'):
            with _STORE_LOCK:                          # §14: revalidate + slot-claim + record under ONE reentrant lock
                rv = revalidate(intent, c, "accept")
                if rv.get("code") == "POLICY_CHANGED": # policy flipped between propose and accept -> don't match
                    c['agree'] = False; c['decided'] = True; c['code'] = "POLICY_CHANGED"; c['action'] = "DECLINE"
                    c['readiness'] = rv.get("readiness")
                    c['reason'] = "policy changed before accept: %s" % (rv.get("reason") or "")
                    _stamp_txn(c, "policy_revoked_before_accept")   # §14.4 proposal -> POLICY_REVOKED (coarse public reason)
                    continue
                # §13.3 autonomy boundaries — the agent may NOT auto-confirm payment/booking/venue or a conflicting plan
                g1_ok, g1 = kp.guard_no_payment_booking_venue_confirm(c.get('envelope'))
                g2_ok, g2 = kp.guard_no_conflicting_plans(c.get('name'), active_plans, intent.get('window'))
                if not (g1_ok and g2_ok):
                    c['agree'] = False; c['decided'] = True; c['code'] = "NEEDS_CONSENT"
                    c['action'] = "DECLINE"; c['reason'] = g1 or g2
                    continue
                # §14.3 exclusivity: a 1:1 fixed-time intent has ONE slot — the first accept wins, a later
                # concurrent accept is WITHDRAWN (SLOT_TAKEN) and is NOT recorded as accepted (no coexisting match).
                if accept_policy.get("exclusive") and accept_policy.get("policy") == "one_to_one_fixed_time":
                    iid = (c.get('proposal') or {}).get('intent_id')
                    slot = ks.claim_slot(SESSION.setdefault('_match_taken', {}), iid, str(c.get('name') or '').lower())
                    if not slot.get("won"):
                        c['agree'] = False; c['decided'] = True; c['code'] = "SLOT_TAKEN"; c['action'] = "WITHDRAW"
                        c['reason'] = "slot unavailable"
                        _stamp_txn(c, "slot_taken")     # proposal -> WITHDRAWN; loser skipped below (must-fix 4)
                        continue
                # §14.3 dating: manual confirmation required — the agent may NOT auto-commit a match on B's accept;
                # it is HELD pending an explicit user confirm (no _record_outcome / no _stamp_accept, agree preserved).
                if accept_policy.get("auto_commit") is False and accept_policy.get("policy") == "dating_manual_confirm":
                    c['decided'] = True; c['code'] = "NEEDS_MANUAL_CONFIRM"
                    c['manual_confirm_required'] = True
                    continue
                _record_outcome(c.get('name'), 'accepted')   # winner keeps the UNCHANGED accepted path (byte-identical)
                _stamp_accept(c)                        # §14.1 proposal SENT->ACCEPTED, match state MUTUAL (additive)
    by = {str(x.get('name', '')).strip().lower(): x for x in done + decided}
    return [by.get(str(c.get('name', '')).strip().lower(), c) for c in top]

def agent_transition(body):
    """§14 single VALIDATED transition surface for WITHDRAW/EXPIRE/COUNTER/etc. Stateless over the object the
    caller passes (the pilot has no cross-request proposal store — that is blocked_infra; here the caller round-
    trips the object). Deny-safe: an illegal edge -> ILLEGAL_TRANSITION (object untouched); a stale
    expected_version -> VERSION_CONFLICT; a replayed idempotency_key -> the stored prior result (DUPLICATE, no
    re-apply). On success appends an immutable audit trace + outbox row. Clock-free -> fully replay-deterministic."""
    body = body or {}
    entity = str(body.get("entity") or "proposal").lower()
    obj = dict(body.get("object") or {})
    if body.get("state") is not None and obj.get("state") is None:
        obj["state"] = body.get("state")
    action = body.get("action")
    cur = obj.get("state") or ks.initial_state(entity)
    to = body.get("to") or (ks.next_state(entity, cur, action) if action else None)
    expected = body.get("expected_version")
    idem = body.get("idempotency_key")
    eid = obj.get("proposal_id") or obj.get("match_id") or obj.get("intent_id") or obj.get("reservation_id") or ""
    with _STORE_LOCK:
        seen = SESSION.setdefault("_txn_seen", {})
        key = ks.dedup_key(entity, eid, action or to or "", extra=idem)
        if key in seen:                               # replayed notification -> prior result, no re-apply
            return dict(seen.get(key) or {}, duplicate=True, error_code="DUPLICATE")
        if to is None:
            res = {"ok": False, "error_code": "ILLEGAL_TRANSITION", "state": cur,
                   "reason": "no legal target for action %r from %r" % (action, cur)}
        elif expected is not None:
            res = ks.compare_and_swap(obj, entity, to, expected)
        else:
            res = ks.apply_transition(obj, entity, to)
        res = dict(res); res.setdefault("state", obj.get("state", cur)); res["entity"] = entity; res["object"] = obj
        if res.get("ok"):
            SESSION.setdefault("_trace", []).append({"entity": entity, "from": cur, "to": res.get("state"),
                                                     "version": res.get("version"), "action": action, "id": eid})
            SESSION.setdefault("_outbox", []).append({"entity": entity, "state": res.get("state"), "id": eid})
            seen[key] = res                           # memoize ONLY an applied transition; a replay returns it verbatim.
            _save_store()                             # a failed edge/CAS has no side effect -> not memoized, so a
        return res                                    # corrected retry (new expected_version) is never wedged as DUPLICATE.

# ---------------------------------------------------------------- §21.2 proposal / plan resource endpoints
def proposal_create(body):
    """§21.2 POST /proposals — build + STORE a proposal (file-backed SESSION['_proposal_store'], keyed by the
    §4.7 idempotency_key). A repeat with the same (intent, candidate) returns the SAME proposal_id (no dup row)."""
    intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
    cand = body.get("candidate") if isinstance(body.get("candidate"), dict) else {}
    prop = kc.build_proposal(intent, cand)
    with _STORE_LOCK:
        store = SESSION.setdefault("_proposal_store", {})
        idem = prop.get("idempotency_key")
        if idem in store:
            return {"proposal_id": store[idem]["proposal_id"], "proposal": store[idem], "duplicate": True}
        prop["state"] = ks.next_state("proposal", "CREATED", "PROPOSE_CONNECTION") or "SENT"
        store[idem] = prop
        SESSION.setdefault("_proposal_by_id", {})[prop["proposal_id"]] = idem
        _save_store()
    return {"proposal_id": prop["proposal_id"], "proposal": prop}

def proposal_respond(body):
    """§21.2 POST /proposals/{id}/respond — load the stored proposal by id and drive a validated §14 transition
    (VERSION_CONFLICT on a stale expected_version, DUPLICATE on a replayed idempotency_key). Persists the result."""
    pid = body.get("proposal_id")
    with _STORE_LOCK:
        idem = (SESSION.get("_proposal_by_id") or {}).get(pid)
        obj = (SESSION.get("_proposal_store") or {}).get(idem)
    if obj is None:
        return {"ok": False, "error_code": "NOT_FOUND"}
    res = agent_transition({"entity": "proposal", "object": dict(obj), "action": body.get("action"),
                            "expected_version": body.get("expected_version"), "idempotency_key": body.get("idempotency_key")})
    if res.get("ok") and isinstance(res.get("object"), dict):
        with _STORE_LOCK:
            (SESSION.get("_proposal_store") or {})[idem] = res["object"]; _save_store()
    return res

def plan_resource(body):
    """§21.2 POST /plans — create/update a plan resource with the version-checked §14 transition path. The Plan
    state machine stays pilot-off (kc.build_plan enabled:False); this is the additive resource wiring only."""
    pid = body.get("plan_id")
    with _STORE_LOCK:
        store = SESSION.setdefault("_plan_store", {})
        if not pid or pid not in store:                       # create
            plan = kc.build_plan(body.get("time_block"), body.get("place") or body.get("place_or_room"),
                                 body.get("participants") or [])
            plan["state"] = ks.initial_state("plan"); plan["version"] = 1
            store[plan["plan_id"]] = plan; _save_store()
            return {"plan_id": plan["plan_id"], "plan": plan, "created": True}
        obj = store[pid]
    res = agent_transition({"entity": "plan", "object": dict(obj), "to": body.get("to"),
                            "action": body.get("action"), "expected_version": body.get("expected_version")})
    if res.get("ok") and isinstance(res.get("object"), dict):
        with _STORE_LOCK:
            SESSION.setdefault("_plan_store", {})[pid] = res["object"]; _save_store()
    return res

# ---------------------------------------------------------------- §1/§17/§18/§21/§23 additive orchestration helpers
_DATING_REDACT = {"not open to dating": "no longer available", "private profile": "no longer available",
                  "not verified": "no longer available"}
def _redact_dating_reason(reason, domain=None):
    """§17.1 explanation — a sensitive dating reason is NEVER surfaced to a non-owner; it is mapped to a coarse
    public reason. Outside the dating domain the reason is unchanged (owner-only surfaces keep the detail)."""
    return _DATING_REDACT.get(str(reason or ""), reason) if str(domain or "") == "dating" else reason

def merge_conditions(intent_a, intent_b):
    """§1.1 intent_to_intent — merge two overlapping intents: topics ∩, shared time, role pair. feasible iff a
    shared topic exists. Additive, deterministic; the reciprocity join uses this to form a mutual condition."""
    a, b = intent_a or {}, intent_b or {}
    ta = set(str(t).lower() for t in a.get("topics") or [])
    tb = set(str(t).lower() for t in b.get("topics") or [])
    topics = sorted(ta & tb)
    return {"topics": topics, "feasible": bool(topics), "roles": [a.get("role"), b.get("role")],
            "time": a.get("time") if a.get("time") == b.get("time") else None}

def coordinate_plan(intent_a, intent_b):
    """§21.1 Plan Coordinator — from two overlapping intents pick a concrete time_block + public place and return
    a kc.build_plan object (pilot-off, enabled:False). Compute only; persistence is infra."""
    m = merge_conditions(intent_a, intent_b)
    if not m["feasible"]:
        return {"plan": None, "feasible": False, "reason": "no shared topic"}
    tb = m.get("time") or (intent_a or {}).get("time") or "Flexible"
    place = (intent_a or {}).get("place") or "Public place nearby"
    parts = [((intent_a or {}).get("identity") or {}).get("user_id") or "a",
             ((intent_b or {}).get("identity") or {}).get("user_id") or "b"]
    return {"plan": kc.build_plan(tb, place, parts), "feasible": True, "shared_topics": m["topics"]}

def confirm_completion(name, uid="me", party="a", now=None):
    """§1.0b — a COMPLETED interaction needs TWO-SIDED confirmation. Records each party's confirm; completed_ts is
    set ONLY when BOTH sides confirm. Silence by one side never marks completion (never a negative)."""
    key = str(name or "").strip().lower()
    with _STORE_LOCK:
        cc = SESSION.setdefault("_completion_confirms", {}).setdefault(key, {})
        cc[str(party)] = True
        both = bool(cc.get("a") and cc.get("b"))
        if both:
            m = SESSION.setdefault("_matches", {}).setdefault(key, {"name": key, "matched_ts": None, "completed_ts": None})
            if not m.get("completed_ts"):
                m["completed_ts"] = float(now if now is not None else time.time())
        _save_store()
    return {"name": key, "confirms": dict(cc), "completed": both}

def match_capsule_disclosed(participant_users, purpose, disclosure_stage="match_only"):
    """§21.1 Match Capsule Builder — a per-participant purpose-bound disclosed ProfileView (a dating capsule omits
    'entities'; a friendship capsule omits 'datingOk'), respecting the disclosure stage."""
    return [kc.build_profile_view(u, purpose, disclosure_stage) for u in participant_users or []]

def _decision_trace(card, intent, snapshot):
    """§21.3 — a unified auditable decision trace per card (search/candidate/purpose ids + policy & model versions;
    scoring is rule-based deterministic, the LLM is parse-only). Deterministic."""
    snap = snapshot or {}
    return {"search_id": kc._det_id("srch", snap.get("intent_id"), snap.get("data_version")),
            "candidate_id": kc._det_id("cand", str((card or {}).get("name") or "").lower()),
            "purpose_id": ((intent or {}).get("goal") or {}).get("purpose") or snap.get("decision_type"),
            "policy": {"version": snap.get("policy_version")},
            "model_versions": {"scoring": "rule_based_deterministic", "llm": "parse_only"},
            "config_version": snap.get("config_version")}

def _append_run_trace(snapshot):
    """§23.4.8 — append each run's snapshot trace to a bounded SESSION['_run_traces'] (file-backed), so a fixture
    run leaves a retrievable decision trace. Bounded to the last 200."""
    with _STORE_LOCK:
        rt = SESSION.setdefault("_run_traces", [])
        rt.append({"intent_id": (snapshot or {}).get("intent_id"),
                   "intent_version": (snapshot or {}).get("intent_version"),
                   "config_version": (snapshot or {}).get("config_version")})
        del rt[:-200]
        _save_store()
    return len(SESSION.get("_run_traces") or [])

def _search_pipeline(intent, cards):
    """§B.1 — a read-only provenance-tier walk over the already-labelled slate (accumulate under the high retrieval
    budget so nothing is cut). Returns the SAME cards (byte-identical) + a trace; never re-scores or drops anyone."""
    by_tier = {}
    for c in cards or []:
        by_tier[str(c.get("tier") or "T?")] = by_tier.get(str(c.get("tier") or "T?"), 0) + 1
    strong = sum(v for k, v in by_tier.items() if k in ("T0", "T1"))
    return {"cards": list(cards or []), "trace": {"tiers": by_tier, "strong_count": strong,
            "enough_strong": strong >= 1, "budget": RETRIEVAL_BUDGET.get("structured", 500),
            "used": len(cards or []), "broke_early": len(cards or []) < RETRIEVAL_BUDGET.get("structured", 500)}}

_DOMAIN_LADDER = {
    "games": ["exact game/role", "parent genre", "room with consent"],
    "walk": ["same area/time", "another zone/time", "small group"],
    "language_exchange": ["exact pair/role", "group practice", "event"],
    "professional_networking": ["exact role/industry", "adjacent role", "curated group/event"],
}
def domain_ladder(intent):
    """§18.1 — the per-domain typical fallback ordering (read-only plan; the generic ladder still executes)."""
    return list(_DOMAIN_LADDER.get(_core.infer_domain(intent, cat_of),
                                   ["broaden topic", "widen zone/time", "alternative"]))

def compile_endpoint(body):
    """§21.2 POST /intents/compile — ONE object folding parse + compile + clarification + snapshot so a caller
    gets {intent, draft, slots, clarification, minimally_sufficient, snapshot} in a single round-trip."""
    q = body.get("query") or ""
    intent = parse_intent(q) if q else (body.get("intent") if isinstance(body.get("intent"), dict) else {})
    ctx = body.get("ctx") if isinstance(body.get("ctx"), dict) else {}
    intent = kc.compile_intent(intent, _intent_identity(intent), ctx, ctx.get("now") or time.time())
    add = _section5_addendum(intent, q, [])
    return {"intent": intent, "draft": intent, "slots": intent.get("topics"),
            "intent_summary": add.get("intent_summary"), "clarification": add.get("clarification"),
            "minimally_sufficient": add.get("minimally_sufficient"), "snapshot": _request_snapshot(intent)}

def expand_one_axis(body):
    """§21.2 POST /searches/{id}/expand — apply EXACTLY ONE declared expansion axis (never the two _expand_fallback
    relaxes together); safety/age/consent stay fixed. Returns {axis, candidates, ladder_step, explanation}."""
    intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
    prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
    ctx = body.get("ctx") if isinstance(body.get("ctx"), dict) else {}
    axis = str(body.get("axis") or "adjacent")
    _AXIS = {"adjacent": {"adjacentAllowed": True}, "parent": {"broadAllowed": True},
             "exactness": {"exactMatchRequired": False},
             "radius": {"radiusKm": (intent.get("radiusKm") or 15) * 2}}
    relaxed = dict(intent, **_AXIS.get(axis, {}))
    return {"axis": axis, "changed_keys": list(_AXIS.get(axis, {}).keys()),
            "candidates": match_candidates(relaxed, prof, ctx),
            "ladder_step": {"adjacent": 2, "parent": 3, "exactness": 2, "radius": 4}.get(axis),
            "explanation": "Expanded by a single axis: %s (safety/age/consent unchanged)" % axis}

# ---------------------------------------------------------------- Explore: public plans near the owner
# The client's Explore map used to hard-code 5 fake plans. Serve real ones instead: every candidate who
# carries an OPEN own-intent becomes a public plan (title from ENTITY_MAP, distance from their geo). Draws
# from load_candidates() so it honours the store, and returns [] when nobody is posting — the client then
# shows an empty state instead of invented pins.
_INACTIVE_INTENT_STATUSES = frozenset({
    "archived", "cancelled", "canceled", "completed", "declined", "draft",
    "expired", "failed", "paused", "withdrawn",
})


def _public_intents(candidate):
    """Yield only actual active intents. Interests alone are not public plans."""
    for intent in candidate.get("intents") or []:
        if not isinstance(intent, dict) or intent.get("open") is False:
            continue
        status = str(intent.get("status") or "active").strip().lower()
        if status in _INACTIVE_INTENT_STATUSES:
            continue
        topics = [
            str(topic).strip().lower()
            for topic in (intent.get("topics") or intent.get("tags") or [])
            if str(topic).strip()
        ]
        if topics:
            yield intent, topics[:3]



def _saved_public_intents():
    """Yield persisted intents with their owner, preserving only stored facts."""
    for row in list(SESSION.get("_intents") or []):
        if not isinstance(row, dict):
            continue
        owner = str(row.get("owner") or "").strip()
        raw = row.get("intent")
        if not owner or not isinstance(raw, dict):
            continue
        intent = dict(raw)
        if row.get("id") is not None:
            intent.setdefault("id", row.get("id"))
        if row.get("title"):
            intent.setdefault("title", row.get("title"))
        if row.get("status"):
            intent.setdefault("status", row.get("status"))
        for public_intent, topics in _public_intents({"intents": [intent]}):
            yield owner, public_intent, topics


def _viewer_candidate(profile):
    """Convert a client profile to the candidate shape expected by policy gates."""
    profile = profile if isinstance(profile, dict) else {}
    raw_interests = profile.get("interests") or []
    interests = [
        str(item.get("name") if isinstance(item, dict) else item).strip().lower()
        for item in raw_interests
        if str(item.get("name") if isinstance(item, dict) else item).strip()
    ]
    languages = profile.get("languages") if isinstance(profile.get("languages"), dict) else {}
    return {
        "name": str(profile.get("name") or "viewer"),
        "age": profile.get("age"),
        "gender": profile.get("gender"),
        "interests": interests,
        "langs": profile.get("langs") or languages.get("comfortable") or [],
        "verified": bool(profile.get("verified") or profile.get("ageVerified18")),
        "pending": 0,
        "intents": profile.get("intents") or [],
    }


def _potential_fit(intent, topics, viewer):
    """Require topical relevance and permission from the plan owner's hard gates."""
    if not viewer or not viewer.get("interests"):
        return False
    decision, _ = _policy_decision(intent, viewer, {"blocked": set(), "feedback": {}}, _CORE_CFG)
    if decision != "ALLOW":
        return False
    best, _ = topical(topics, viewer["interests"])
    if best <= 0:
        return False
    if best == 1 and intent.get("adjacentAllowed") is False:
        return False
    if best < 4 and intent.get("exactMatchRequired"):
        return False
    return True


def explore_plans(limit=12, self_name="", viewer_profile=None):
    sn = str(self_name or "").strip().lower()
    users = [c for c in load_candidates() if not (sn and str(c.get("name", "")).strip().lower() == sn)]
    # Seed users exist only to keep matching non-empty. They are never public content.
    ordered = [c for c in users if c.get("source") == "onboarding"]
    owners = {
        str(c.get("name") or "").strip().lower(): c
        for c in ordered
        if str(c.get("name") or "").strip()
    }
    viewer = _viewer_candidate(viewer_profile) if viewer_profile is not None else None
    out = []
    seen = set()
    # A plan card shows a PERSON, so it carries their face. Resolved by name as well as off the row:
    # a saved intent builds a synthetic candidate ({name, source, open}) that has no photo on it,
    # and that owner is a real person with a real photo.
    photos = _photo_by_name()

    def append_plan(c, intent, topics):
        intent_id = intent.get("id") or intent.get("intent_id")
        if intent_id and intent_id in seen:
            return
        if _core.is_paused(c) or c.get("open") is False:
            return
        if viewer is not None and not _potential_fit(intent, topics, viewer):
            return
        km = c.get("km")
        plan = {
            "intentId": intent_id,
            "title": intent.get("title") or ENTITY_MAP.get(topics[0]) or (topics[0].capitalize() + " meetup"),
            "who": c.get("name") or "Someone",
            "age": c.get("age"),
            "topics": topics,
            "role": intent.get("role") or "meet",
            "when": intent.get("when") or intent.get("time") or "",
            "area": intent.get("area") or intent.get("place") or c.get("city") or "",
            "verified": bool(c.get("verified")),
        }
        photo = c.get("photo") or photos.get(str(c.get("name") or "").strip().lower())
        if photo:
            plan["photo"] = photo
        if km is not None:
            try:
                plan["dist"] = round(float(km), 1)
            except (TypeError, ValueError):
                pass
        if c.get("lat") is not None and c.get("lon") is not None:
            plan["lat"], plan["lon"] = c["lat"], c["lon"]
        out.append(plan)
        if intent_id:
            seen.add(intent_id)

    for c in ordered:
        for intent, topics in _public_intents(c):
            append_plan(c, intent, topics)

    for owner, intent, topics in _saved_public_intents():
        owner_key = owner.lower()
        if sn and owner_key == sn:
            continue
        candidate = owners.get(owner_key) or {
            "name": owner,
            "source": "saved_intent",
            "open": True,
        }
        append_plan(candidate, intent, topics)

    out.sort(key=lambda p: (
        p.get("dist") is None,
        p.get("dist", 0),
        str(p.get("title") or "").lower(),
    ))
    return out[:limit]


# ---------------------------------------------------------------- explain: full diagnostic of one search
# Mirrors core_v2.search() decision-for-decision, but CLASSIFIES every pool candidate instead of silently
# dropping it — so a matching test panel can show who matched and why, who was gated out (and the gate),
# and who was considered-but-filtered — plus the per-feature-group breakdown behind each score.
def explain_match(intent, prof, ctx=None):
    if not CORE_V2:
        return {"error": "Core v2 disabled (KLEAL_CORE_V2=0) — nothing to explain", "matched": [], "excluded": [], "considered": []}
    ctx = ctx or {}
    intent, prof = intent or {}, prof or {}
    intent = ki.normalize_for_scoring(intent)              # §5: same normalization as match_candidates (PARITY)
    cfg = _CORE_CFG
    domain = _core.infer_domain(intent, cat_of)
    dom_cfg = cfg["domains"].get(domain) or cfg["domains"]["social_meet"]
    W = dom_cfg["weights"]
    lam = float(dom_cfg["uncertainty_lambda"])
    disc_lcb, disc_cov = float(dom_cfg["discovery_min_lcb"]), float(dom_cfg["discovery_min_coverage"])
    out_lcb, out_cov = float(dom_cfg["outreach_min_lcb"]), float(dom_cfg["outreach_min_coverage"])
    priors = {k: (cfg["feature_groups"][k] or {}).get("unknown_prior", 0.5) for k in _core.FEATURE_KEYS}
    bands = cfg["user_facing_bands"]
    topics = [str(t).lower() for t in (intent.get("topics") or [])]
    now_ts = ctx.get("now") or time.time()
    snap_id = _intent_identity(intent)["intent_id"]      # scope for per-feature Evidence (§4.1)
    received24 = ctx.get("received24") or _proposals_received_24h()
    gate_ctx, self_name = _gate_ctx_and_self(ctx, prof)

    def _feats(F):
        tw = sum(float(W.get(k, 0) or 0) for k in _core.FEATURE_KEYS if F.get(k, (None,))[0] != _core.NA)
        rows = []
        for k in _core.FEATURE_KEYS:
            st, v, det = F.get(k, (_core.UNKNOWN, None, ""))
            w = float(W.get(k, 0) or 0)
            adj = None if st == _core.NA else (priors[k] if st == _core.UNKNOWN else v)
            contrib = round(w * adj / tw, 4) if (st != _core.NA and tw > 0 and adj is not None) else 0.0
            rows.append({"group": k, "state": st, "value": adj, "weight": round(w, 3),
                         "contribution": contrib, "detail": det})
        return rows

    matched, considered, excluded = [], [], []
    pool = load_candidates()
    for c in pool:
        nm = c.get("name")
        nm_key = str(nm or "").strip().lower()
        if self_name and nm_key == self_name:
            excluded.append({"name": nm, "gate": "self", "reason": "the searcher (you)"}); continue
        decision, why = _policy_decision(intent, c, gate_ctx)     # BLOCK / REVIEW / ALLOW (§0 output table)
        if decision == "BLOCK":
            excluded.append({"name": nm, "gate": "hard", "reason": why}); continue
        if _core.is_paused(c, now_ts):
            excluded.append({"name": nm, "gate": "paused", "reason": "paused / left retrieval"}); continue
        tier = _core.assign_tier(intent, c, topics, _H)
        if tier == "T5":
            considered.append({"name": nm, "tier": "T5", "reason": "no meaningful topical overlap"}); continue
        if tier == "T3" and not intent.get("adjacentAllowed", True):
            considered.append({"name": nm, "tier": tier, "reason": "adjacent excluded (adjacentAllowed off)"}); continue
        if tier == "T2" and intent.get("exactMatchRequired"):
            considered.append({"name": nm, "tier": tier, "reason": "related excluded (exactMatchRequired on)"}); continue
        F = _core.build_features(intent, prof, c, domain, _H, ROLE_CONFLICT)
        d_ab = _core.directional_score(F, dom_cfg, priors)
        d_ba = _core.directional_score(_core.reverse_features(intent, prof, c, domain, _H, ROLE_CONFLICT), dom_cfg, priors)
        rec = _core.reciprocal_score(d_ab, d_ba)
        readiness = _core.readiness_state(c, domain, now_ts, cfg, received24.get(nm_key, 0))
        disc_ok = d_ab["lcb"] >= disc_lcb and d_ab["coverage"] >= disc_cov
        if not disc_ok and tier not in ("T0", "T1"):
            considered.append({"name": nm, "tier": tier,
                               "reason": "below discovery floor (lcb %.2f<%.2f or cov %.2f<%.2f)"
                               % (d_ab["lcb"], disc_lcb, d_ab["coverage"], disc_cov),
                               "lcb": d_ab["lcb"], "coverage": d_ab["coverage"], "reciprocal": rec, "readiness": readiness}); continue
        band = _core.assign_band(d_ab["lcb"], d_ab["coverage"], bands) if disc_ok else "needs_clarification"
        outreach_tier_ok = tier in ("T0", "T1") or (tier == "T2" and bool(intent.get("broadConsent")))
        can_outreach = (outreach_tier_ok and readiness == "open_now" and
                        d_ab["lcb"] >= out_lcb and d_ab["coverage"] >= out_cov)
        if decision == "REVIEW":                                 # discoverable, but the safety/legal track gates outreach
            can_outreach = False
        rs_ru, rs_en, _legacy, gap_ru, gap_en = _core._presentation(F, d_ab, dom_cfg)
        band_lbl = _core.BAND_LABELS.get(band, (band, band))
        rdy_lbl = _core.READINESS_LABELS.get(readiness, (readiness, readiness))
        if can_outreach:
            why_no = None
        elif decision == "REVIEW":
            why_no = why
        elif not outreach_tier_ok:
            why_no = "tier T2 needs broad consent" if tier == "T2" else "tier %s: discovery only (no personal outreach)" % tier
        elif readiness != "open_now":
            why_no = "not open now (%s)" % rdy_lbl[1]
        else:
            why_no = "below outreach floor (lcb %.2f / cov %.2f)" % (d_ab["lcb"], d_ab["coverage"])
        alloc = ("review_required" if decision == "REVIEW" else "propose" if can_outreach else "discovery_only")
        feat_rows = _feats(F)
        # §4.1/§4.2: one Evidence object per KNOWN feature group, provenance from FEATURE_GROUP_SOURCE
        # (not a hardcoded L1); scope-bound to this intent so aliases from one phrase share an evidence_id.
        evidence = [kc.build_evidence(r["group"], r["detail"],
                                      kc.FEATURE_GROUP_SOURCE.get(r["group"], "agent_inference"),
                                      scope="intent:" + snap_id, confidence=r["value"], now=now_ts)
                    for r in feat_rows if r["state"] == "known_match" and r.get("detail")]
        matched.append({
            "name": nm, "tier": tier, "kind": _core.TIER_KIND.get(tier, "related"),
            "policy": decision, "allocation_action": alloc,
            "decision_class": _decision_class({"policy": decision, "tier": tier, "band": band,
                                               "can_outreach": can_outreach, "why_no_outreach": why_no}),  # §9.6
            "probe_unknowns": [u for u, _w in sorted(((u, W.get(u, 0)) for u in d_ab.get("unknowns", [])),
                                                     key=lambda x: -x[1])[:3]],   # §9.6 clarification: top-1-3 unknowns
            "band": band, "band_en": band_lbl[1], "readiness": readiness, "readiness_en": rdy_lbl[1],
            "can_outreach": can_outreach, "reciprocal": rec, "disc_ok": disc_ok,
            "a_to_b": {"mean": d_ab["mean"], "coverage": d_ab["coverage"], "lcb": d_ab["lcb"],
                       "lam": lam, "features": feat_rows},
            "b_to_a": {"mean": d_ba["mean"], "coverage": d_ba["coverage"], "lcb": d_ba["lcb"]},
            "reasons": rs_en, "gap": gap_en, "why_no_outreach": why_no,
            "evidence": evidence, "relationship": _relationship_edge(nm, ctx.get("uid", "me"), scope=domain),
        })
        try:                                              # §6: additive typed-edge + expansion + complementary
            for k, v in kt.enrich_card(topics, c.get("interests") or [],
                                       role_a=intent.get("role"), role_b=c.get("role")).items():
                matched[-1].setdefault(k, v)              # never touches band/tier/lcb/can_outreach/sort keys
            matched[-1].setdefault("retrieval_source", _retrieval_source(intent, c))   # §7.1 source provenance
            matched[-1].setdefault("completion_factors", kcf.completion_factors(c, intent, now_ts, received24.get(nm_key, 0)))  # §10.2
            matched[-1].setdefault("readiness_explain", kcf.READINESS_EXPLAIN.get(readiness))  # §10.1
        except Exception:
            pass
    matched.sort(key=lambda x: (_core.BAND_RANK[x["band"]], _core.READINESS_RANK[x["readiness"]],
                                -x["reciprocal"], -x["a_to_b"]["lcb"], -x["a_to_b"]["coverage"], str(x["name"])))
    slate_cut = _core.TOP_N
    return {
        "domain": domain,
        "domain_config": {"weights": W, "uncertainty_lambda": lam,
                          "outreach_min_lcb": float(dom_cfg["outreach_min_lcb"]),
                          "discovery_min_lcb": float(dom_cfg["discovery_min_lcb"]),
                          "outreach_min_coverage": float(dom_cfg["outreach_min_coverage"]),
                          "discovery_min_coverage": float(dom_cfg["discovery_min_coverage"])},
        "bands": bands, "priors": priors, "slate_cut": slate_cut,
        "matched": matched, "considered": considered, "excluded": excluded,
        "counts": {"pool": len(pool), "matched": len(matched),
                   "considered": len(considered), "excluded": len(excluded),
                   "review": sum(1 for m in matched if m.get("policy") == "REVIEW")},
        "tier_analytics": _tier_analytics(matched),    # §7.1 relevance distribution within each tier
        "retrieval": _retrieval_report(matched),       # §7.2 staged pipeline + §7.1 source provenance
        "snapshot": _request_snapshot(intent),      # §4 immutable per-request version snapshot
        "payment_invariant": PAYMENT_INVARIANT,     # §0 dec.10 / §11.3
    }


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# RESTORED: intents, messages/proposals and groups.
#
# The rewrite of this service RENAMED its API surface — propose→proposal, respond→proposal/respond,
# intents/intent-save/intent-delete→saved_searches/save_search/save_search/delete, group-*→group —
# but the profile frontend was never updated, so it kept calling the old names and got 404. Three
# whole screens (My Intents, Messages, Groups) were dead in the shipped build, and the admin panel
# lost 25 of its 87 checks with them.
#
# These handlers are restored verbatim from the pre-rewrite service rather than the frontend being
# repointed at the new names: the payload shapes differ, so aliasing old names onto the new
# handlers would answer 200 with a body the UI cannot read — worse than an honest 404.
#
# This is state-machine and store code (SESSION / kleal_store.json, §14 transactional guarantees
# with idempotency keys and optimistic versions). It does NOT touch the ranking engine, so nothing
# here can change who matches whom.
# ═══════════════════════════════════════════════════════════════════════════════════════════════

# transplanted symbols in dependency order (35):
#   PROPOSAL_TTL_S, _requests, _expire_due, _idem, _idem_get, _idem_put, _norm_name, propose, inbox, outbox, archive_request, _num, _policy_ok_now, respond, withdraw_request, _messages, _pair_key, send_message, thread, threads_for, _intents, save_intent, delete_intent, _normalize_intent, list_intents, _gnorm, _group_state, _group_public, _groups, group_create, group_join, group_leave, _pair_fit, group_utility, group_list

# ---- §14 transactional guarantees ------------------------------------------------------------------
# A proposal used to be a row with a status string: no version, no expiry, no idempotency, and policy
# was checked only when SENDING. So a retry created a duplicate, a three-week-old request was still
# acceptable, and — the real defect — if the recipient paused or blocked the sender between SENT and
# ACCEPT, the accept still went through. §14.2 requires the policy re-check to happen INSIDE the same
# transaction as the acceptance.
PROPOSAL_TTL_S = int(os.environ.get("KLEAL_PROPOSAL_TTL_S", 72 * 3600))   # spec §14.2 reservation TTL

def _requests():
    return SESSION.setdefault("_requests", [])

def _expire_due(now=None):
    """Mark overdue proposals EXPIRED. Called on every read and before every write, so an expired
    proposal can never be accepted (acceptance test #9)."""
    now = now or time.time()
    changed = False
    for r in _requests():
        if r.get("status") == "pending" and (r.get("expires_at") or 0) and now > r["expires_at"]:
            r["status"] = "expired"
            r["updated"] = now
            r["version"] = int(r.get("version") or 1) + 1
            changed = True
    return changed

def _idem():
    return SESSION.setdefault("_idem", {})

def _idem_get(key):
    row = _idem().get(str(key)) if key else None
    return row.get("result") if row else None

def _idem_put(key, result):
    """Same idempotency key -> same answer (spec §14.2, acceptance test #7)."""
    if not key:
        return result
    d = _idem()
    d[str(key)] = {"result": result, "at": time.time()}
    if len(d) > 2000:                                   # bounded; oldest keys fall off
        for k in sorted(d, key=lambda k: d[k].get("at") or 0)[:600]:
            d.pop(k, None)
    return result

# ---- real proposal delivery (was missing entirely) -------------------------------------------------
# Sending a request used to be local: the client posted feedback, asked an LLM to ROLE-PLAY the
# recipient's agent, and showed "мы отправили твой запрос <name>" plus a mutual match based on that
# simulation. Nothing ever reached the other account — logging in as the recipient showed no request.
# These endpoints are the actual delivery: a proposal is stored, the recipient reads and answers it,
# and the sender sees the real answer instead of a generated one.
def _norm_name(n):
    return str(n or "").strip().lower()

def propose(frm, to, intent, note, idem=None):
    frm, to = str(frm or "").strip(), str(to or "").strip()
    if not frm or not to or _norm_name(frm) == _norm_name(to):
        return {"ok": False, "error": "sender and recipient required and must differ"}
    cached = _idem_get(idem)
    if cached is not None:
        return cached                                    # retry-safe: same key, same answer
    now = time.time()
    with _STORE_LOCK:
        _expire_due(now)
        rs = _requests()
        # one open proposal per pair per direction — re-sending updates it rather than stacking
        for r in rs:
            if (_norm_name(r.get("from")) == _norm_name(frm) and _norm_name(r.get("to")) == _norm_name(to)
                    and r.get("status") == "pending"):
                r.update({"intent": intent or {}, "note": str(note or "")[:400], "updated": now,
                          "expires_at": now + PROPOSAL_TTL_S,
                          "version": int(r.get("version") or 1) + 1})
                _save_store()
                return _idem_put(idem, {"ok": True, "id": r["id"], "status": "pending",
                                        "version": r["version"], "expires_at": r["expires_at"], "resent": True})
        # The id was time-in-ms + hash(pair), so two proposals for the SAME pair inside one
        # millisecond collided — and every later lookup by id hit whichever row came first.
        base = "rq_%d_%s" % (int(now * 1000), hashlib.sha1((frm + to).encode("utf-8")).hexdigest()[:6])
        taken = {r.get("id") for r in rs}
        rid, n = base, 1
        while rid in taken:
            rid, n = "%s_%d" % (base, n), n + 1
        rs.append({"id": rid, "from": frm, "to": to, "intent": intent or {},
                   "note": str(note or "")[:400], "status": "pending", "created": now, "updated": now,
                   "version": 1, "expires_at": now + PROPOSAL_TTL_S,
                   "config_version": (_CORE_CFG or {}).get("config_version")})   # immutable trace stamp
    _save_store()
    _log_proposal(to)                       # feeds the receiving-policy budget, spec 4.4
    return _idem_put(idem, {"ok": True, "id": rid, "status": "pending", "version": 1,
                            "expires_at": now + PROPOSAL_TTL_S})

def _with_photos(rows, name_key):
    """Attach the photo of the person named under `name_key` — an invitation and a message thread are
    both a PERSON, and a row that knows only their name renders a blank circle beside it."""
    by = _photo_by_name()
    if by:
        for r in rows or []:
            if isinstance(r, dict) and not r.get("photo"):
                ph = by.get(str(r.get(name_key) or "").strip().lower())
                if ph:
                    r["photo"] = ph
    return rows


def inbox(self_name):
    me = _norm_name(self_name)
    if not me:
        return []
    if _expire_due():
        _save_store()
    out = [dict(r) for r in _requests() if _norm_name(r.get("to")) == me]
    out.sort(key=lambda r: -(r.get("updated") or 0))
    return _with_photos(out[:50], "from")

def outbox(self_name):
    me = _norm_name(self_name)
    if not me:
        return []
    if _expire_due():
        _save_store()
    out = [dict(r) for r in _requests() if _norm_name(r.get("from")) == me]
    out.sort(key=lambda r: -(r.get("updated") or 0))
    return _with_photos(out[:50], "to")

# A meetup leaves the active list only when someone says so. Deriving "past" from a timestamp would
# be a guess: the request carries the intent's loose time ("tomorrow evening"), never a real date.
def archive_request(rid, who):
    me = _norm_name(who)
    with _STORE_LOCK:
        for r in _requests():
            if r.get("id") == rid:
                if me and me not in (_norm_name(r.get("to")), _norm_name(r.get("from"))):
                    return {"ok": False, "error": "not your request"}
                if r.get("status") != "accepted":
                    return {"ok": False, "error": "only an accepted meetup can be archived"}
                r["status"] = "archived"
                r["updated"] = time.time()
                _save_store()
                return {"ok": True, "id": rid, "status": "archived"}
    return {"ok": False, "error": "not found"}

def _num(v):
    """Numeric coercion that tolerates strings ('28') and refuses junk — a single profile with a
    string-typed age/km used to raise inside a gate and kill the search for EVERY user."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def _policy_ok_now(frm, to, blocked=None):
    """Re-resolve BOTH sides against the live store and re-run the hard gates. Returns (ok, reason).
    Safe to call while _STORE_LOCK is held: load_candidates() and plain SESSION reads never take it
    (_session() does — calling that here would deadlock on the non-reentrant lock)."""
    by = {}
    for c in load_candidates():
        by[_norm_name(c.get("name"))] = c
    a, b = by.get(_norm_name(frm)), by.get(_norm_name(to))
    if not a or not b:
        return True, ""                                  # unknown to the store: nothing to revoke on
    if b.get("open") is False or b.get("paused"):
        return False, "recipient is not accepting requests"
    if a.get("paused"):
        return False, "sender is paused"
    # Only CONSENT and SAFETY gates are re-checked here. Outreach budgets (fatigue, cooldown,
    # "too many open invites") governed whether the proposal could be SENT; re-applying them now
    # would revoke perfectly consensual acceptances just because the sender got popular meanwhile.
    bl = {str(x).strip().lower() for x in (blocked or ())}
    if _norm_name(frm) in bl or a.get("blocksMe") or b.get("blocksMe"):
        return False, "blocked"
    for side, tag in ((a, "sender"), (b, "recipient")):
        age = _num(side.get("age"))
        if age is not None and age < MIN_AGE:
            return False, "%s under %d" % (tag, MIN_AGE)
    return True, ""

def respond(rid, decision, who, idem=None, version=None):
    """Accept/decline INSIDE one transaction that re-checks expiry, version and LIVE policy (§14.2).
    Before this, policy was validated only when SENDING: if the recipient paused, blocked the sender
    or closed the domain between SENT and ACCEPT, the accept still went through."""
    dec = "accepted" if str(decision).lower() in ("accept", "accepted", "yes") else "declined"
    cached = _idem_get(idem)
    if cached is not None:
        return cached                                    # same key -> same answer (acceptance test #7)
    with _STORE_LOCK:
        now = time.time()
        _expire_due(now)
        for r in _requests():
            if r.get("id") != rid:
                continue
            if who and _norm_name(who) != _norm_name(r.get("to")):
                return {"ok": False, "error": "only the recipient can answer this request"}
            st = r.get("status")
            if st == "expired":
                _save_store()
                return _idem_put(idem, {"ok": False, "error": "EXPIRED", "id": rid, "status": "expired"})
            if st != "pending":
                # already settled: report the settled state, never flip it (concurrent-accept, §14.3)
                return _idem_put(idem, {"ok": False, "error": "ALREADY_RESOLVED", "id": rid,
                                        "status": st, "version": r.get("version")})
            # optimistic concurrency: a stale version means someone else moved this row first
            if version is not None and str(version) != str(r.get("version") or 1):
                return {"ok": False, "error": "VERSION_CONFLICT", "id": rid,
                        "status": st, "version": r.get("version")}
            if dec == "accepted":
                # the responder IS the local user, so their block list is session "me"
                mine = (SESSION.get("me") or {}).get("blocked") or []
                ok, why = _policy_ok_now(r.get("from"), r.get("to"), mine)
                if not ok:
                    r["status"] = "policy_revoked"
                    r["updated"] = now
                    r["version"] = int(r.get("version") or 1) + 1
                    r["trace"] = {"decision": "policy_revoked", "at": now, "reason": why}
                    _save_store()
                    return _idem_put(idem, {"ok": False, "error": "POLICY_CHANGED", "id": rid,
                                            "status": "policy_revoked", "reason": why})
            r["status"] = dec
            r["updated"] = now
            r["version"] = int(r.get("version") or 1) + 1
            r["trace"] = {"decision": dec, "at": now, "by": who or r.get("to"),
                          "config_version": r.get("config_version")}   # immutable decision trace
            _save_store()
            return _idem_put(idem, {"ok": True, "id": rid, "status": dec, "version": r["version"]})
    return {"ok": False, "error": "not found"}

def withdraw_request(rid, who, idem=None):
    """The SENDER pulls a proposal back before it is answered (§14.1 WITHDRAWN)."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    with _STORE_LOCK:
        _expire_due()
        for r in _requests():
            if r.get("id") != rid:
                continue
            if who and _norm_name(who) != _norm_name(r.get("from")):
                return {"ok": False, "error": "only the sender can withdraw"}
            if r.get("status") != "pending":
                return _idem_put(idem, {"ok": False, "error": "ALREADY_RESOLVED",
                                        "id": rid, "status": r.get("status")})
            r["status"] = "withdrawn"
            r["updated"] = time.time()
            r["version"] = int(r.get("version") or 1) + 1
            _save_store()
            return _idem_put(idem, {"ok": True, "id": rid, "status": "withdrawn", "version": r["version"]})
    return {"ok": False, "error": "not found"}

# ---- real message delivery ------------------------------------------------------------------------
# Same gap as proposals had: the chat pushed the typed text into local state only, so the recipient's
# account never received it. Messages are stored per pair and read back by either side.
def _messages():
    return SESSION.setdefault("_messages", [])

def _pair_key(a, b):
    return "|".join(sorted([_norm_name(a), _norm_name(b)]))

def send_message(frm, to, text):
    frm, to, text = str(frm or "").strip(), str(to or "").strip(), str(text or "").strip()[:2000]
    if not frm or not to or not text or _norm_name(frm) == _norm_name(to):
        return {"ok": False, "error": "from, to and text are required and the two must differ"}
    m = {"id": "m_%d" % int(time.time() * 1000), "pair": _pair_key(frm, to),
         "from": frm, "to": to, "text": text, "t": time.time()}
    with _STORE_LOCK:
        ms = _messages()
        ms.append(m)
        del ms[:-4000]                       # keep the store bounded
    _save_store()
    return {"ok": True, "id": m["id"], "t": m["t"]}

def thread(self_name, other, since=0.0):
    """Every message between the two, oldest first. `since` lets a client poll for new ones only."""
    if not str(self_name or "").strip() or not str(other or "").strip():
        return []
    key = _pair_key(self_name, other)
    try:
        since = float(since or 0)
    except (TypeError, ValueError):
        since = 0.0
    out = [dict(m) for m in _messages() if m.get("pair") == key and (m.get("t") or 0) > since]
    out.sort(key=lambda m: m.get("t") or 0)
    return out[-200:]

def threads_for(self_name):
    """Latest message per conversation, so the Messages tab reflects what actually exists."""
    me = _norm_name(self_name)
    if not me:
        return []
    last = {}
    for m in _messages():
        if me not in (_norm_name(m.get("from")), _norm_name(m.get("to"))):
            continue
        other = m.get("to") if _norm_name(m.get("from")) == me else m.get("from")
        cur = last.get(_norm_name(other))
        if not cur or (m.get("t") or 0) > (cur.get("t") or 0):
            last[_norm_name(other)] = {"who": other, "last": m.get("text"), "t": m.get("t"),
                                       "mine": _norm_name(m.get("from")) == me}
    return _with_photos(sorted(last.values(), key=lambda x: -(x.get("t") or 0))[:50], "who")

# ---- intents as LIVE server-side standing searches ------------------------------------------------
# Intents used to live only in the sender's localStorage, holding a FROZEN copy of the candidates from
# the moment they were created — so a saved intent was a private note that never re-searched, while the
# requests and messages it supposedly drove were already shared server state. Stored here instead, and
# re-ranked on read so opening one shows who fits NOW, not who fitted then.
def _intents():
    return SESSION.setdefault("_intents", [])

def save_intent(owner, intent, title, iid=None, launched=None):
    owner = str(owner or "").strip()
    if not owner or not isinstance(intent, dict):
        return {"ok": False, "error": "owner and intent required"}
    now = time.time()
    with _STORE_LOCK:
        rows = _intents()
        if iid:
            for r in rows:
                if r.get("id") == iid and _norm_name(r.get("owner")) == _norm_name(owner):
                    r.update({"intent": intent, "title": title or r.get("title"), "updated": now})
                    # once a search has actually run this never flips back to "not started"
                    if launched:
                        r["launched"] = now
                    _save_store()
                    return {"ok": True, "id": iid}
        # the same request twice should update, not pile up a second identical card
        key = json.dumps(intent.get("topics") or [], sort_keys=True) + "|" + str(intent.get("role") or "")
        for r in rows:
            if _norm_name(r.get("owner")) == _norm_name(owner) and r.get("key") == key:
                r.update({"intent": intent, "title": title or r.get("title"), "updated": now})
                if launched:
                    r["launched"] = now
                _save_store()
                return {"ok": True, "id": r["id"], "merged": True}
        nid = "in_%d" % int(now * 1000)
        rows.append({"id": nid, "owner": owner, "title": title or "", "intent": intent,
                     "key": key, "created": now, "updated": now,
                     "launched": now if launched else None})
    _save_store()
    return {"ok": True, "id": nid}

def delete_intent(owner, iid):
    with _STORE_LOCK:
        rows = _intents()
        keep = [r for r in rows
                if not (r.get("id") == iid and _norm_name(r.get("owner")) == _norm_name(owner))]
        removed = len(rows) - len(keep)
        rows[:] = keep
    _save_store()
    return {"ok": removed > 0}

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

def list_intents(owner, profile=None, live=True):
    """Every intent this user owns. With live=True each one is re-ranked now, so the count and the
    top band reflect the current pool rather than a snapshot taken when the card was made."""
    me = _norm_name(owner)
    if not me:
        return []
    out = []
    for r in [x for x in _intents() if _norm_name(x.get("owner")) == me]:
        row = {"id": r["id"], "title": r.get("title"), "intent": r.get("intent") or {},
               "created": r.get("created"), "updated": r.get("updated"),
               "launched": r.get("launched"), "candidates": []}
        if live:
            try:
                row["candidates"] = match_candidates(_normalize_intent(r.get("intent") or {}),
                                                     profile or {}, {"self": owner}) or []
            except Exception as e:
                row["error"] = str(e)[:120]        # a failed re-rank must not hide the intent
        out.append(row)
    out.sort(key=lambda x: -(x.get("updated") or 0))
    return out

# Group size bounds (§15). Restored with the group handlers: this was a tuple assignment in the
# pre-rewrite file, which the transplant's dependency scan did not follow.
GROUP_MIN, GROUP_MAX = 2, 8


def _gnorm(seq):
    return [_norm_name(x) for x in (seq or [])]

def _group_state(g):
    """Derived, never stored twice: forming -> confirmed at quorum, full at capacity."""
    if g.get("state") == "cancelled":
        return "cancelled"
    n = len(g.get("members") or [])
    if n >= int(g.get("max_size") or GROUP_MAX):
        return "full"
    return "confirmed" if n >= int(g.get("min_size") or GROUP_MIN) else "forming"

def _group_public(g, me=""):
    mem = list(g.get("members") or [])
    return {"gid": g.get("id"), "title": g.get("title"), "host": g.get("host"),
            "topics": list(g.get("topics") or []), "when": g.get("when") or "",
            "area": g.get("area") or "", "lat": g.get("lat"), "lon": g.get("lon"),
            "mode": g.get("mode") or "offline",
            "min_size": int(g.get("min_size") or GROUP_MIN), "max_size": int(g.get("max_size") or GROUP_MAX),
            "members": mem, "size": len(mem), "waitlist": list(g.get("waitlist") or []),
            "state": _group_state(g), "version": int(g.get("version") or 1),
            "mine": bool(me) and _norm_name(me) in _gnorm(mem),
            "hosting": bool(me) and _norm_name(me) == _norm_name(g.get("host")),
            "waiting": bool(me) and _norm_name(me) in _gnorm(g.get("waitlist"))}

def _groups():
    return SESSION.setdefault("_groups", [])

def group_create(host, title, topics, when="", area="", mode="offline",
                 min_size=GROUP_MIN, max_size=GROUP_MAX, lat=None, lon=None, idem=None):
    host = str(host or "").strip()
    if not host:
        return {"ok": False, "error": "host required"}
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    try:
        mn, mx = int(min_size or GROUP_MIN), int(max_size or GROUP_MAX)
    except Exception:
        mn, mx = GROUP_MIN, GROUP_MAX
    mn = max(2, min(mn, GROUP_MAX))
    mx = max(mn, min(mx, GROUP_MAX))
    now = time.time()
    with _STORE_LOCK:
        gs = _groups()
        gid = "gr_%d_%s" % (int(now * 1000), hashlib.sha1(host.encode("utf-8")).hexdigest()[:6])
        taken = {g.get("id") for g in gs}
        base, n = gid, 1
        while gid in taken:
            gid, n = "%s_%d" % (base, n), n + 1
        g = {"id": gid, "host": host, "title": str(title or "").strip()[:120] or "Meetup",
             "topics": [str(t).lower() for t in (topics or [])][:6], "when": str(when or "")[:80],
             "area": str(area or "")[:80], "mode": str(mode or "offline"), "lat": lat, "lon": lon,
             "min_size": mn, "max_size": mx, "members": [host], "waitlist": [], "state": "forming",
             "created": now, "updated": now, "version": 1,
             "config_version": (_CORE_CFG or {}).get("config_version")}
        gs.append(g)
        _save_store()
        return _idem_put(idem, {"ok": True, "group": _group_public(g, host)})

def group_join(gid, who, idem=None, version=None):
    """Joining is a transaction, exactly like accepting a proposal: capacity, state and pairwise
    safety are re-checked under the lock, so two people racing for the last seat cannot both win."""
    who = str(who or "").strip()
    if not who:
        return {"ok": False, "error": "name required"}
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    with _STORE_LOCK:
        for g in _groups():
            if g.get("id") != gid:
                continue
            if g.get("state") == "cancelled":
                return _idem_put(idem, {"ok": False, "error": "CANCELLED", "gid": gid})
            if version is not None and str(version) != str(g.get("version") or 1):
                return {"ok": False, "error": "VERSION_CONFLICT", "gid": gid,
                        "version": g.get("version"), "group": _group_public(g, who)}
            if _norm_name(who) in _gnorm(g.get("members")):
                return _idem_put(idem, {"ok": True, "gid": gid, "already": True,
                                        "group": _group_public(g, who)})
            # §15.1 safety exclusions are PAIRWISE: the joiner must be acceptable to every member
            # already in, and every member to them. Checking only the host would let a blocked
            # person walk in through someone else's group.
            mine = (SESSION.get("me") or {}).get("blocked") or []
            for m in (g.get("members") or []):
                ok, why = _policy_ok_now(who, m, mine)
                if not ok:
                    return _idem_put(idem, {"ok": False, "error": "NOT_ELIGIBLE", "gid": gid,
                                            "reason": why})
            if len(g.get("members") or []) >= int(g.get("max_size") or GROUP_MAX):
                wl = g.setdefault("waitlist", [])
                if _norm_name(who) not in _gnorm(wl):
                    wl.append(who)
                g["updated"] = time.time()
                g["version"] = int(g.get("version") or 1) + 1
                _save_store()
                return _idem_put(idem, {"ok": True, "gid": gid, "waitlisted": True,
                                        "group": _group_public(g, who)})
            g.setdefault("members", []).append(who)
            g["waitlist"] = [w for w in (g.get("waitlist") or []) if _norm_name(w) != _norm_name(who)]
            g["updated"] = time.time()
            g["version"] = int(g.get("version") or 1) + 1
            _save_store()
            return _idem_put(idem, {"ok": True, "gid": gid, "group": _group_public(g, who)})
    return {"ok": False, "error": "not found"}

def group_leave(gid, who, idem=None):
    """§15.3 step 7: on a drop, promote from the waitlist; losing quorum re-forms the group rather
    than cancelling it. The host leaving hands the group to the next member — an empty group ends."""
    who = str(who or "").strip()
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    with _STORE_LOCK:
        for g in _groups():
            if g.get("id") != gid:
                continue
            mem = [m for m in (g.get("members") or []) if _norm_name(m) != _norm_name(who)]
            wl = [w for w in (g.get("waitlist") or []) if _norm_name(w) != _norm_name(who)]
            if len(mem) == len(g.get("members") or []) and len(wl) == len(g.get("waitlist") or []):
                return _idem_put(idem, {"ok": False, "error": "NOT_A_MEMBER", "gid": gid})
            promoted = None
            if len(mem) < int(g.get("max_size") or GROUP_MAX) and wl and len(mem) < len(g.get("members") or []):
                promoted = wl.pop(0)
                mem.append(promoted)
            g["members"], g["waitlist"] = mem, wl
            if not mem:
                g["state"] = "cancelled"
            elif _norm_name(g.get("host")) == _norm_name(who):
                g["host"] = mem[0]                       # the group survives its host leaving
            g["updated"] = time.time()
            g["version"] = int(g.get("version") or 1) + 1
            _save_store()
            return _idem_put(idem, {"ok": True, "gid": gid, "promoted": promoted,
                                    "group": _group_public(g, who)})
    return {"ok": False, "error": "not found"}

def _pair_fit(intent, a, b):
    """Directed relevance a->b combined reciprocally, on the SAME engine the slate uses. Returns
    0..1, or None when the engine is off — callers must treat None as 'unknown', never as 0."""
    if not (CORE_V2 and _CORE_CFG):
        return None
    try:
        # A stored user row and a searcher PROFILE are not the same shape (languages is a list on one
        # and {comfortable:[...]} on the other). Feeding a row in as a profile made reverse_features
        # throw, and _pair_fit swallowed it as "unknown" — every group utility came back null.
        a = dict(a or {})
        if isinstance(a.get("languages"), list):
            a["languages"] = {"comfortable": list(a["languages"])}
        H = {'topical': topical, 'cat_of': cat_of, 'reciprocal': _reciprocal, 'role_conflict': ROLE_CONFLICT}
        domain = _core.infer_domain(intent, cat_of)
        dom_cfg = _CORE_CFG["domains"].get(domain) or _CORE_CFG["domains"]["social_meet"]
        priors = {k: (_CORE_CFG["feature_groups"][k] or {}).get("unknown_prior", 0.5)
                  for k in _core.FEATURE_KEYS}
        f_ab = _core.build_features(intent, a, b, domain, H, ROLE_CONFLICT)
        d_ab = _core.directional_score(f_ab, dom_cfg, priors)
        f_ba = _core.reverse_features(intent, a, b, domain, H, ROLE_CONFLICT)
        d_ba = _core.directional_score(f_ba, dom_cfg, priors)
        return float(_core.reciprocal_score(d_ab, d_ba))
    except Exception:
        return None

def group_utility(g, rows=None):
    """Spec §15.2: 0.35*least_misery + 0.25*mean_pair_fit + 0.20*role_coverage + 0.10*time_overlap
    + 0.10*diversity_value. Only the terms we can actually evidence are scored; the rest stay out of
    the denominator instead of being invented (same unknown discipline as the pair engine)."""
    by = {}
    for c in (rows if rows is not None else load_candidates()):
        by[_norm_name(c.get("name"))] = c
    mem = [by.get(n) for n in _gnorm(g.get("members"))]
    mem = [m for m in mem if m]
    if len(mem) < 2:
        return {"utility": None, "least_misery": None, "mean_pair_fit": None, "pairs": 0}
    intent = {"topics": list(g.get("topics") or []), "type": g.get("type") or "social",
              "role": "meet", "mode": g.get("mode") or "offline", "time": g.get("when") or ""}
    fits = []
    for i in range(len(mem)):
        for j in range(len(mem)):
            if i == j:
                continue
            f = _pair_fit(intent, mem[i], mem[j])
            if f is not None:
                fits.append(f)
    if not fits:
        return {"utility": None, "least_misery": None, "mean_pair_fit": None, "pairs": 0}
    least, mean = min(fits), sum(fits) / len(fits)
    langs = set()
    for m in mem:
        langs |= {str(x).lower() for x in (m.get("languages") or [])}
    diversity = min(1.0, len(langs) / 3.0) if langs else None
    parts, weights = [(least, 0.35), (mean, 0.25)], []
    if diversity is not None:
        parts.append((diversity, 0.10))
    tot = sum(w for _v, w in parts)
    util = sum(v * w for v, w in parts) / tot if tot else None
    return {"utility": round(util, 4) if util is not None else None,
            "least_misery": round(least, 4), "mean_pair_fit": round(mean, 4), "pairs": len(fits)}

def group_list(self_name="", limit=30, open_only=False):
    me = str(self_name or "").strip()
    out = []
    rows = load_candidates()
    for g in _groups():
        if g.get("state") == "cancelled":
            continue
        pub = _group_public(g, me)
        if open_only and (pub["mine"] or pub["state"] == "full"):
            continue
        pub["fit"] = group_utility(g, rows)
        out.append(pub)
    # mine first, then the ones closest to happening, then group utility — never a raw percentage
    out.sort(key=lambda p: (not p["mine"], -(p["size"] or 0), -((p["fit"] or {}).get("utility") or 0)))
    return out[:max(1, int(limit or 30))]


# ---- helpers for the restored admin/diagnostic routes (verbatim from the pre-rewrite service)
# ── Learned categories ────────────────────────────────────────────────────────────────────────────
# The hand-written taxonomy is 165 words; interests are not a closed set. Filtration already decides
# a (category, subcategory) for text nobody has seen before — «лабубу» -> toys_collectibles, «улитки»
# -> pets/breeding — and that answer used to be computed, put on the intent and then ignored, because
# nothing on the CANDIDATE side had a category to compare against.
#
# This is that missing half: one shared word -> (broad, sub) map that both sides resolve through.
# Because it is consulted from cat_of(), the existing level logic (4 exact / 3 sub / 2 broad /
# 1 adjacent) applies to new interests unchanged — no new scoring path, no new weights.
#
# Only filtration writes here, and only its own vocabulary is accepted, so a malformed answer cannot
# invent a category. Entries are per-word and bounded; the file is small and human-readable on
# purpose, because a wrong category here is invisible in a slate and obvious in a list.
LEARNED_PATH = os.environ.get("KLEAL_LEARNED",
                              os.path.join(os.path.dirname(os.path.abspath(__file__)), "learned_topics.json"))


_FILTRATION_CATS = {"sports", "gaming", "esports", "tabletop", "music", "film_tv", "art_culture",
                    "books", "food_drink", "coffee", "nightlife", "outdoors", "travel", "tech",
                    "startups", "career", "languages", "wellness", "fashion", "toys_collectibles",
                    "pets", "photography", "dating", "social"}


def _load_learned():
    try:
        with open(LEARNED_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        return {str(k).lower(): (str(v[0]), str(v[1])) for k, v in d.items()
                if isinstance(v, (list, tuple)) and len(v) == 2 and str(v[0]) in _FILTRATION_CATS}
    except Exception:
        return {}


LEARNED = _load_learned()


# ---------------------------------------------------------------- one person, every reason (admin)
def _raw_store_rows():
    """The store as written, WITHOUT the loadtest filter — the admin has to be able to look at a
    row precisely because it was excluded from the pool."""
    try:
        with open(USERS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        lst = data.get("users") if isinstance(data, dict) else data
        return lst if isinstance(lst, list) else []
    except Exception:
        return []


def cohorts():
    """The saved queries that a 3000-row table cannot answer. Counts + names, computed over the raw
    store so a cohort can be ABOUT the rows retrieval drops."""
    rows = _raw_store_rows()
    now_ts = time.time()
    defs = [
        ("no_interests", "Без интересов — навсегда T5", lambda u: not [x for x in (u.get("interests") or []) if str(x).strip()]),
        ("no_intents", "Без своих интентов — никогда не T0", lambda u: not (u.get("intents") or [])),
        ("no_age", "Без возраста — нет dating и возрастных запросов", lambda u: _num(u.get("age")) is None),
        ("no_coords", "Без координат — нет поиска по радиусу", lambda u: _num(u.get("lat")) is None or _num(u.get("lon")) is None),
        ("paused", "На паузе — вне выдачи", lambda u: _core.is_paused(u, now_ts)),
        ("no_domains", "allowed_domains пуст — ни одного предложения", lambda u: isinstance(((u.get("receiving") or {}) if isinstance(u.get("receiving"), dict) else {}).get("allowed_domains"), list) and not ((u.get("receiving") or {}).get("allowed_domains"))),
        ("budget_zero", "Нулевой бюджет предложений", lambda u: (((u.get("receiving") or {}) if isinstance(u.get("receiving"), dict) else {}).get("proposal_budget") or {}).get("per_24h") == 0),
        ("unverified", "Не верифицированы", lambda u: not u.get("verified")),
        ("loadtest", "source=loadtest — вне поиска", lambda u: u.get("source") == "loadtest"),
    ]
    out = []
    for key, label, fn in defs:
        names = []
        n = 0
        for u in rows:
            try:
                if fn(u):
                    n += 1
                    if len(names) < 40:
                        names.append(u.get("name") or "?")
            except Exception:
                pass
        out.append({"key": key, "label": label, "count": n, "total": len(rows), "sample": names})
    return {"ok": True, "total": len(rows), "cohorts": out}


def compare_scorers(intent, prof, ctx=None):
    """Same query, both scorers, side by side — the shipped Core v2 and the legacy scorer that
    KLEAL_CORE_V2=0 falls back to.

    This exists because the fallback is silent. A config whose sha does not match drops the whole
    system onto the legacy scorer without an error anywhere, and the only visible symptom is that
    different people start appearing. Before this you could not answer «насколько вообще разные
    эти два движка» without editing an env var on a live box.
    """
    ctx = dict(ctx or {})
    try:
        new = match_candidates(intent, prof, ctx) if CORE_V2 else []
    except Exception as e:
        new = []
        ctx["_new_error"] = str(e)[:160]
    try:
        old = match_candidates_legacy(intent, prof, ctx)
    except Exception as e:
        old = []
        ctx["_old_error"] = str(e)[:160]
    nn = [str(c.get("name") or "") for c in new]
    on = [str(c.get("name") or "") for c in old]
    sn, so = set(nn), set(on)
    both = sn & so
    denom = float(len(sn | so)) or 1.0
    # Rank movement for the people BOTH scorers show — a slate can have identical membership and
    # still be a different product if the order is inverted.
    moved = []
    for name in both:
        a, b = nn.index(name), on.index(name)
        if a != b:
            moved.append({"name": name, "new": a + 1, "old": b + 1, "delta": b - a})
    moved.sort(key=lambda m: -abs(m["delta"]))
    return {"ok": True,
            "core": {"enabled": CORE_V2, "config_version": (_CORE_CFG or {}).get("config_version"),
                     "config_sha": ((_CORE_CFG or {}).get("_sha256") or "")[:12], "error": _CORE_ERR},
            "new": {"n": len(nn), "names": nn}, "old": {"n": len(on), "names": on},
            "shared": sorted(both), "onlyNew": [n for n in nn if n not in so],
            "onlyOld": [n for n in on if n not in sn],
            "jaccard": round(len(both) / denom, 3),
            "topChanged": bool(nn[:1] != on[:1]),
            "moved": moved[:8],
            "errors": {k: v for k, v in ctx.items() if k.startswith("_") and k.endswith("error")}}


_LEARNED_CAPS = 4000


_LEARNED_LOCK = threading.Lock()


# Generic descriptor words filtration emits alongside the real interest. Stored as categories they
# match everyone: «money» -> startups/investing would pair every uncategorised person who typed
# money, «find»/«search» are worse. A learned entry is permanent and invisible in a slate, so the
# writer — this service — is where the guard belongs, whatever the source.
_LEARN_STOP = {
    "hobby", "hobbies", "fun", "day", "days", "time", "people", "person", "friend", "friends",
    "company", "someone", "somebody", "group", "meet", "meetup", "socialize", "social", "find",
    "search", "looking", "want", "wanna", "activity", "activities", "thing", "things", "stuff",
    "money", "cash", "finance", "discussion", "chat", "talk", "collect", "collecting", "watching",
    "throwing", "playing", "doing", "making", "sport", "sports", "game", "games", "gaming",
    "interest", "interests", "new", "cool", "nice", "good", "best", "любой", "разное", "хобби",
    "деньги", "компания", "человек", "люди", "друзья", "встреча", "общение", "интерес",
}


def cat_of_fixed(word):
    """Taxonomy only, no learned entries — used to decide whether a word still needs teaching."""
    w = _norm(word)
    return _IDX.get(w, (None, None))


def learn_topics(pairs):
    """pairs: [(word, category, subcategory)]. Returns how many are new. `other` is filtration's
    honest "nothing here" and is never stored — an unknown word must stay unknown, not become a
    category that matches everyone else who is also uncategorised."""
    added = 0
    with _LEARNED_LOCK:
        for w, c, sub in pairs or []:
            w = str(w or "").strip().lower()[:40]
            c = str(c or "").strip().lower()
            sub = str(sub or "").strip().lower()[:40]
            if not w or c not in _FILTRATION_CATS or w in LEARNED or len(LEARNED) >= _LEARNED_CAPS:
                continue
            if w in _LEARN_STOP or len(w) < 3:
                continue                       # a generic descriptor, not an interest
            if cat_of_fixed(w)[0]:
                continue                       # the hand-written taxonomy already owns this word
            LEARNED[w] = (c, sub)
            added += 1
        if added:
            try:
                tmp = LEARNED_PATH + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({k: list(v) for k, v in LEARNED.items()}, f, ensure_ascii=False)
                os.replace(tmp, LEARNED_PATH)   # atomic: this file is read on every search
            except Exception:
                pass
    if added:
        # Invalidate the topic-similarity memo, because it reads the category map we just changed.
        # Conditional on purpose: `same_topic` carried @lru_cache before the matching rewrite and
        # does not now, so this line raised AttributeError on every learn that stored a word —
        # i.e. the whole learning path 500'd — after learn_topics was restored alongside it.
        # Nothing to invalidate when nothing is cached, and the guard picks the cache back up
        # automatically if the decorator returns.
        if hasattr(same_topic, "cache_clear"):
            same_topic.cache_clear()
    return added


# tools/gen_test_users.py stamps source="loadtest" on its 1000-person load pool. Only the Explore map
# ever filtered them out, so a real user's SEARCH was ranked against ~982 synthetic people (every
# result surnamed Volkov/Petrov/Garcia). They are fixtures, not people, and must not be proposed to
# anyone. The eval and fuzz harnesses run ON that pool, so they flip this back on.
INCLUDE_LOADTEST = os.environ.get("KLEAL_INCLUDE_LOADTEST", "0") != "0"


def person_report(name, now_ts=None):
    """Why is this person invisible, and why do they see nobody? Two different questions with two
    different answers, and until this endpoint existed both looked like "the ranker is bad".

    Every field is reported as the store actually holds it. A missing value is reported as None
    (the panel renders «не собрано») and NEVER as a default — a fabricated `age: 30` here would
    hide the exact gate that is dropping the person.
    """
    now_ts = now_ts or time.time()
    want = _norm_name(name)
    row = None
    for u in _raw_store_rows():
        if _norm_name(u.get("name")) == want:
            row = u
            break
    if row is None:
        for u in CANDIDATES:                      # demo pool, only reachable with KLEAL_MERGE_DEMO
            if _norm_name(u.get("name")) == want:
                row = dict(u, source="demo")
                break
    if row is None:
        return {"ok": False, "error": "no such person", "name": name}

    in_pool = any(_norm_name(c.get("name")) == want for c in load_candidates())
    ints = [str(x).lower() for x in (row.get("interests") or []) if str(x).strip()]
    lat, lon = _num(row.get("lat")), _num(row.get("lon"))
    age = _num(row.get("age"))
    langs = [str(l)[:2].lower() for l in (row.get("langs") or []) if str(l).strip()]
    r = row.get("receiving") if isinstance(row.get("receiving"), dict) else None
    received = (_proposals_received_24h() or {}).get(want, 0)

    # ---- inbound: can anyone find them at all
    blocks = []                                    # hard, absolute — no search reaches them
    warns = []                                     # narrows them to a subset of searches
    if row.get("source") == "loadtest" and not INCLUDE_LOADTEST:
        blocks.append({"key": "loadtest", "ru": "строка помечена source=loadtest — исключена из поиска",
                       "en": "row is source=loadtest — excluded from retrieval"})
    if _core.is_paused(row, now_ts):
        why = ("флаг paused" if row.get("paused") else
               ("receiving.status=paused" if str((r or {}).get("status") or "").lower() == "paused"
                else "receiving.paused_until в будущем"))
        blocks.append({"key": "paused", "ru": "на паузе (%s)" % why, "en": "paused (%s)" % why})
    if not ints:
        blocks.append({"key": "no_interests",
                       "ru": "нет интересов — тир T5 при ЛЮБОМ запросе, никогда не показывается",
                       "en": "no interests — tier T5 for every query, never shown"})
    if row.get("open") is False and not r:
        warns.append({"key": "open_false", "ru": "open=false — готовность «занят(а)»",
                      "en": "open=false — readiness 'busy'"})
    if age is None:
        warns.append({"key": "no_age",
                      "ru": "возраст не собран — выпадает из dating и из любого запроса с возрастным диапазоном",
                      "en": "age unknown — dropped from dating and any age-range query"})
    elif age < MIN_AGE:
        blocks.append({"key": "under_age", "ru": "младше 18 — жёсткий отказ", "en": "under 18 — hard gate"})
    if lat is None or lon is None:
        warns.append({"key": "no_coords",
                      "ru": "нет координат — выпадает из любого запроса с радиусом",
                      "en": "no coordinates — dropped from any query with a radius"})
    if not langs:
        warns.append({"key": "no_langs", "ru": "языки не собраны — выпадает при requiredLanguages",
                      "en": "no languages — dropped when a language is required"})
    if not row.get("verified"):
        warns.append({"key": "unverified", "ru": "не верифицирован — выпадает при «только проверенные»",
                      "en": "unverified — dropped when the search asks for verified only"})
    if not row.get("datingOk"):
        warns.append({"key": "no_dating", "ru": "нет согласия на dating — выпадает из dating-запросов",
                      "en": "no dating opt-in — dropped from dating queries"})
    if (_num(row.get("pending")) or 0) >= MAX_PENDING:
        blocks.append({"key": "pending", "ru": "слишком много открытых приглашений (%s)" % row.get("pending"),
                       "en": "too many open invites (%s)" % row.get("pending")})

    # ---- receiving policy, read the same way readiness_state reads it (opt-outs fail closed)
    out_cfg = (_CORE_CFG or {}).get("outreach") or {}
    pb = ((r or {}).get("proposal_budget") or {}).get("per_24h")
    cap = pb if isinstance(pb, (int, float)) and not isinstance(pb, bool) else \
        (out_cfg.get("max_proposals_received_per_user_24h") or 4)
    q = (r or {}).get("quiet_hours") or {}
    tzoff = int(q.get("tz_offset_min", 120))
    local_min = int((now_ts // 60 + tzoff) % 1440)
    defaults = out_cfg.get("quiet_hours_local") or ["22:00", "09:00"]
    quiet_now = _core._in_quiet_hours(local_min, q.get("start") or defaults[0], q.get("end") or defaults[-1])
    policy = {
        "hasPolicy": r is not None,
        "status": (r or {}).get("status"),
        "allowedDomains": (r or {}).get("allowed_domains"),
        "passiveOutreach": (r or {}).get("passive_outreach"),
        "budgetPer24h": cap, "budgetExplicit": pb is not None,
        "received24h": received,
        "budgetSpent": received >= int(cap),
        "quietHours": {"start": q.get("start") or defaults[0], "end": q.get("end") or defaults[-1],
                       "tzOffsetMin": tzoff,
                       "localTime": "%02d:%02d" % (local_min // 60, local_min % 60),
                       "inQuietNow": bool(quiet_now)},
    }
    if isinstance(policy["allowedDomains"], list) and not policy["allowedDomains"]:
        blocks.append({"key": "no_domains", "ru": "allowed_domains пуст — ни одного личного предложения",
                       "en": "allowed_domains is empty — no personal proposal in any domain"})
    if policy["budgetSpent"]:
        warns.append({"key": "budget", "ru": "лимит предложений на сутки исчерпан (%s из %s)" % (received, cap),
                      "en": "24h proposal budget spent (%s of %s)" % (received, cap)})

    readiness = {}
    for d in _core.ALL_DOMAINS:
        readiness[d] = _core.readiness_state(row, d, now_ts, _CORE_CFG, received)

    # ---- outbound: what THIS person's own requests can reach
    own_intents = row.get("intents") if isinstance(row.get("intents"), list) else []
    outbound = []
    if not own_intents:
        outbound.append({"key": "no_intents",
                         "ru": "нет собственных интентов — этот человек никогда не станет T0 "
                               "(взаимным совпадением) ни для кого",
                         "en": "no own intents — this person can never be a T0 reciprocal match for anybody"})
    if not ints:
        outbound.append({"key": "no_interests_out",
                         "ru": "нет интересов — его собственный поиск не на чем строить",
                         "en": "no interests — nothing to build their own search on"})
    if lat is None or lon is None:
        outbound.append({"key": "no_coords_out",
                         "ru": "нет координат — его поиск не может отфильтровать по расстоянию",
                         "en": "no coordinates — their own search cannot filter by distance"})

    return {"ok": True, "name": row.get("name"), "inPool": in_pool,
            "verdict": ("невидим" if blocks else ("виден" if in_pool else "не в пуле")),
            "identity": {"source": row.get("source"), "area": row.get("area") or None,
                         "age": age, "verified": bool(row.get("verified")),
                         "datingOk": bool(row.get("datingOk")),
                         "lat": lat, "lon": lon, "radiusKm": _num(row.get("radiusKm")),
                         "langs": langs or None, "interests": ints or None,
                         "ownIntents": len(own_intents), "entities": len(row.get("entities") or [])},
            "blocks": blocks, "warnings": warns, "outbound": outbound,
            "policy": policy, "readiness": readiness}


def proposals_registry(limit=300):
    """Stage 3: the proposal ledger. Four failures look identical from outside — declined, expired
    unanswered, revoked by policy at accept time, and never created at all — and only the trace
    separates them. Read-only: _save_store() writes this file without tmp+replace, so a reader that
    ever wrote could truncate a request mid-flight."""
    now = time.time()
    rows = []
    for r in (SESSION.get("_requests") or []):
        if not isinstance(r, dict):
            continue
        trace = r.get("trace") if isinstance(r.get("trace"), list) else []
        exp = r.get("expires_at")
        try:
            exp_f = float(exp) if exp is not None else None
        except (TypeError, ValueError):
            exp_f = None
        st = str(r.get("status") or "").lower()
        rows.append({
            "id": r.get("id"), "from": r.get("from"), "to": r.get("to"),
            "note": (str(r.get("note") or "")[:160] or None),
            "status": st or "unknown",
            "domain": r.get("domain") or (r.get("intent") or {}).get("type"),
            "createdAt": r.get("created_at") or r.get("ts"),
            "ageHours": (round((now - float(r.get("created_at") or r.get("ts") or now)) / 3600.0, 1)
                         if (r.get("created_at") or r.get("ts")) else None),
            "expiresAt": exp_f,
            "expiresInHours": (round((exp_f - now) / 3600.0, 1) if exp_f else None),
            "expired": bool(exp_f and exp_f <= now and st in ("pending", "sent", "")),
            "configVersion": r.get("config_version"),
            "trace": [str(t) for t in trace][-8:],
            "policyRevoked": st == "policy_revoked" or any("policy_revoked" in str(t) for t in trace),
        })
    rows.sort(key=lambda x: (x["createdAt"] or 0), reverse=True)
    by_status = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    return {"ok": True, "total": len(rows), "byStatus": by_status,
            "expiringSoon": sum(1 for r in rows
                                if r["expiresInHours"] is not None and 0 < r["expiresInHours"] < 12
                                and r["status"] in ("pending", "sent")),
            "expiredUnanswered": sum(1 for r in rows if r["expired"]),
            "policyRevoked": sum(1 for r in rows if r["policyRevoked"]),
            "requests": rows[:limit]}


def reset_fatigue(name):
    """Clear one person's received-proposal log. The ONLY write this admin surface makes, and it
    touches matching's own kleal_store.json — never users.json."""
    key = _norm_name(name)
    with _STORE_LOCK:
        log = SESSION.setdefault("_proposals", {})
        had = len(log.get(key) or [])
        log[key] = []
    _save_store()
    return {"ok": True, "name": name, "cleared": had}


def _group_slate(cands):
    """§15 reads each candidate's directed fit from `relevance`; a core_v2 slate card carries it as
    `lcb`. Map it losslessly (every other field, including any diversity axis, is preserved).

    This lived in /api/agent/group and nowhere else, so the SAME slate produced a sensible group
    through that door and a hash-ordered one through /api/agent/match — with relevance missing, every
    utility component that depends on it is 0 and selection falls back to the id-hash tiebreak. On
    prod that put a 0.665 candidate in the group and left the 0.883 one out. One helper, both doors."""
    return [dict(c, relevance=(c.get("relevance") if c.get("relevance") is not None else c.get("lcb", 0)))
            for c in (cands or []) if isinstance(c, dict)]


# §15.4 domain packs, restricted to the keys the DATA can satisfy. The packs also carry
# required_equipment, max_skill_spread and mandatory_roles; users.json has no equipment, level or
# per-person role field, so applying those verbatim makes every candidate violate a hard gate and
# "padel for four" answers NO_FEASIBLE_GROUP. Seat counts are wired now; the rest waits for profiles
# that actually carry equipment and skill.
_PACK_SIZE_KEYS = ("size_min", "size_max", "quorum", "capacity")


def _group_constraints(intent, caller=None):
    """An intent's §15 set-constraints.

    `groupSize` is the TOTAL headcount asked for, THE ASKER INCLUDED — they are never in their own
    candidate slate, so the group being assembled is one seat smaller than the number they said.

    Precedence: explicit caller constraints > the stated size > the domain pack > config defaults.
    The floor matters more than the ceiling: §15 grows a seed only while a size/quorum SHORTFALL is
    outstanding and then stops (adding a weaker member always lowers least_misery, so nothing is ever
    added for utility alone). Group size is therefore decided by size_min, which is why leaving it at
    the config default returned exactly three people whatever was asked for."""
    intent = intent or {}
    pack = {}
    for name in list(intent.get("topics") or []) + [intent.get("type"), intent.get("activity")]:
        p = kg.pack_for(name)
        if p:
            # Pack numbers are TOTAL headcount — a padel court holds four PLAYERS. §15 counts the
            # seats it is filling, and the asker is never in their own candidate slate, so each of
            # those numbers is one smaller here. Copying them across units capped a padel group at
            # four strangers PLUS you — five on a four-seat court — and made a request for six
            # collide with the pack's capacity and fall all the way back to three.
            pack = {k: max(1, int(v) - 1) for k, v in p.items() if k in _PACK_SIZE_KEYS}
            break
    out = dict(pack)
    try:
        total = int(intent.get("groupSize")) if intent.get("groupSize") is not None else None
    except (TypeError, ValueError):
        total = None
    if total:
        seats = max(1, min(kg._MAX_MVP_SIZE, total - 1))
        ceiling = pack.get("size_max") or pack.get("capacity")
        if ceiling:
            seats = min(seats, int(ceiling))   # a padel court does not grow because you asked it to
        out["size_min"] = out["quorum"] = out["size_max"] = seats
    out.update({k: v for k, v in (caller or {}).items() if v is not None})
    return out


def form_group_from_slate(intent, cands, constraints=None, now_ts=None, pair_rel=None, reserve=False):
    """Assemble a group out of an already-ranked slate (§15.3).

    The §15 core takes candidates as an ARGUMENT — it never retrieves. That is why calling
    /api/agent/group without a slate answered NO_FEASIBLE_GROUP: there was nothing to form a group
    from, which looked like the algorithm failing and was really an empty input.

    Runs only when GROUPS_ENABLED. The override is supplied here, by the service, rather than by the
    caller: kg's switch stays the exact test-only key it was written as, and whether the product
    offers groups is decided in one place instead of by whoever crafts the request body.

    `reserve` defaults to FALSE and that is the important part. §15.3.5 reserve_members CLAIMS SEATS
    in a persisted ledger, so forming a group with a ledger attached is a write. Wiring that into
    the search path made every search silently hold seats for people who had agreed to nothing —
    visible immediately as a second identical request returning a different company, because the
    first one had already taken the first three. A search is a read. Seats are claimed only when a
    caller explicitly asks to commit."""
    if not GROUPS_ENABLED:
        return kg.dormant_response(intent, constraints or {})
    if not cands:
        return dict(kg.dormant_response(intent, constraints or {}, note="no candidates to form a group from"),
                    feasible=False)
    slate = _group_slate(cands)
    cons = _group_constraints(intent, constraints)
    now_ts = now_ts or time.time()

    def _run(c, ledger=None):
        return kg.run_group_formation(intent, slate, c, _CORE_CFG, override=_GROUP_OVERRIDE,
                                      now_ts=now_ts, ledger=ledger, pair_rel=pair_rel)

    def _finish(res, c):
        """Say what was asked for, what the rules allowed, and what was filled — all as TOTAL
        headcount, the asker included, because that is the number they typed.

        `asked` is their own number, not the clamped one: a request for eight padel players is
        answered with four, and the UI can only explain that ("a court seats four") if it can still
        see that eight was asked. `allowed` is the ceiling after the §15.4 pack, `formed` the result."""
        allowed = cons.get("size_min")
        res["seats"] = {"asked": intent.get("groupSize"),
                        "allowed": (allowed + 1) if allowed else None,
                        "formed": (len(res.get("members") or []) + 1) if res.get("members") else 0,
                        "relaxed": c is not cons}
        res["group_formation_live"] = True
        return res

    if not reserve:
        res = _run(cons)
        # A thin pool must degrade to a smaller REAL group, never to nothing: §15 treats size_min as
        # hard, so a request for six in a city with four padel players answered NO_FEASIBLE_GROUP —
        # which reads as "groups are broken" and is really "we could only find four". Relax the floor
        # ONCE, to the config default, and label the result.
        if not res.get("members") and (cons.get("size_min") or 0) > 2:
            relaxed = dict(cons)
            relaxed.pop("size_min", None); relaxed.pop("quorum", None)
            alt = _run(relaxed)
            if alt.get("members"):
                res = _finish(alt, relaxed)
                return dict(res, reserved=False)
        return dict(_finish(res, cons), reserved=False)
    with _STORE_LOCK:
        led = SESSION.setdefault("_group_ledger", {})
        res = _finish(_run(cons, ledger=led), cons)
        _save_store()
    res["reserved"] = True
    # kg always reports enabled:False (it is scaffolding and says so). The PRODUCT-level answer is
    # this switch, so state it plainly next to kg's own field rather than rewriting kg's contract.
    res["group_formation_live"] = True
    return res


# ---------------------------------------------------------------- HTTP dispatcher (matching only)
class H(BaseHTTPRequestHandler):
    # ---- restored routes: the names the profile frontend actually calls (see the block above) ----
    def _restored_get(self):
        """The GET half of the restored screens. Returns True when it handled the request."""
        from urllib.parse import unquote
        base = self.path.split("?")[0]
        if base not in ("/api/agent/thread", "/api/agent/threads",
                        "/api/agent/inbox", "/api/agent/outbox", "/api/agent/groups"):
            return False
        q = dict(kv.split("=", 1) for kv in self.path.split("?", 1)[-1].split("&") if "=" in kv) \
            if "?" in self.path else {}
        me = unquote(q.get("self", "").replace("+", " "))
        if base == "/api/agent/threads":
            send_json(self, 200, {"threads": threads_for(me)})
        elif base == "/api/agent/thread":
            try:
                since = float(q.get("since", 0) or 0)
            except (TypeError, ValueError):
                since = 0.0
            send_json(self, 200, {"messages": thread(me, unquote(q.get("with", "").replace("+", " ")), since)})
        elif base in ("/api/agent/inbox", "/api/agent/outbox"):
            fn = inbox if base.endswith("inbox") else outbox
            send_json(self, 200, {"requests": fn(me)})
        else:
            try:
                lim = max(1, min(100, int(q.get("limit", 30))))
            except (TypeError, ValueError):
                lim = 30
            send_json(self, 200, {"groups": group_list(me, lim, q.get("open") in ("1", "true"))})
        return True

    def _restored_post(self, p, body):
        """The POST half of the restored screens. Returns True when it handled the request."""
        if p == "/api/agent/intent-save":
            send_json(self, 200, save_intent(body.get("self"), body.get("intent") or {},
                                             body.get("title"), body.get("id"),
                                             bool(body.get("launched"))))
        elif p == "/api/agent/intent-delete":
            send_json(self, 200, delete_intent(body.get("self"), body.get("id")))
        elif p == "/api/agent/intents":
            send_json(self, 200, {"intents": list_intents(body.get("self"), body.get("profile") or {},
                                                          body.get("live") is not False)})
        elif p == "/api/agent/message":
            send_json(self, 200, send_message(body.get("from"), body.get("to"), body.get("text")))
        elif p == "/api/agent/propose":
            send_json(self, 200, propose(body.get("from"), body.get("to"), body.get("intent") or {},
                                         body.get("note"), body.get("idem")))
        elif p == "/api/agent/respond":
            send_json(self, 200, respond(body.get("id"), body.get("decision"), body.get("self"),
                                         body.get("idem"), body.get("version")))
        elif p == "/api/agent/withdraw":
            send_json(self, 200, withdraw_request(body.get("id"), body.get("self"), body.get("idem")))
        elif p == "/api/agent/request-archive":
            send_json(self, 200, archive_request(body.get("id"), body.get("self")))
        elif p == "/api/agent/group-create":
            send_json(self, 200, group_create(body.get("host"), body.get("title"), body.get("topics"),
                                              body.get("when"), body.get("area"), body.get("mode"),
                                              body.get("min_size"), body.get("max_size"),
                                              body.get("lat"), body.get("lon"), body.get("idem")))
        elif p == "/api/agent/group-join":
            send_json(self, 200, group_join(body.get("gid"), body.get("self"),
                                            body.get("idem"), body.get("version")))
        elif p == "/api/agent/group-leave":
            send_json(self, 200, group_leave(body.get("gid"), body.get("self"), body.get("idem")))
        else:
            return False
        return True


    # ---- restored diagnostics: what the admin panel proxies to (person card, cohorts, proposal
    # registry, scorer compare, fatigue reset, stability/diversity probes, the funnel). The rewrite
    # dropped these with the rest; without them 23 of the panel's 87 checks fail and its Cohorts,
    # Person, Compare, Funnel and Stability views are blank. Bodies are verbatim from the
    # pre-rewrite service — read-only diagnostics, they never write to the store or send anything.
    def _restored_admin_get(self):
        """Returns True when it handled the request."""
        if self.path.split("?")[0] == "/api/agent/admin/person":
            q = dict(kv.split("=", 1) for kv in self.path.split("?", 1)[-1].split("&") if "=" in kv) if "?" in self.path else {}
            from urllib.parse import unquote
            send_json(self, 200, person_report(unquote(q.get("name", "").replace("+", " "))))
        elif self.path.split("?")[0] == "/api/agent/admin/cohorts":
            send_json(self, 200, cohorts())
        elif self.path.split("?")[0] == "/api/agent/admin/proposals":
            send_json(self, 200, proposals_registry())
        else:
            return False
        return True

    def _restored_admin_post(self, p, body):
        """Returns True when it handled the request."""
        if p == "/api/agent/admin/compare":
            send_json(self, 200, compare_scorers(_normalize_intent(body.get("intent")),
                                                 body.get("profile") if isinstance(body.get("profile"), dict) else {},
                                                 body.get("ctx") if isinstance(body.get("ctx"), dict) else {}))
        elif p == "/api/agent/learn":
            # Teach the shared word -> (category, subcategory) map. Buddy calls this with what
            # filtration already worked out, so no extra model call is spent here.
            pairs = [(x.get("word"), x.get("category"), x.get("subcategory"))
                     for x in (body.get("items") or []) if isinstance(x, dict)]
            send_json(self, 200, {"ok": True, "added": learn_topics(pairs), "known": len(LEARNED)})
        elif p == "/api/agent/admin/fatigue-reset":
            send_json(self, 200, reset_fatigue(body.get("name")))
        elif p == "/api/agent/stability":
            # Ported capability (not code) from the PROD|OLD|NEW bench: run the SAME search N times
            # and check the slate does not move. Our tie-break is a name hash, so drift can only come
            # from something time-dependent — readiness, quiet hours, proposal fatigue — and drift is
            # indistinguishable, from the outside, from "random people".
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            intent = _normalize_intent(body.get("intent"))
            runs = max(2, min(8, int(body.get("runs") or 4)))
            pin = body.get("now")
            outs = []
            for _i in range(runs):
                # `seen` pinned empty ON PURPOSE. Paging is a deterministic function of the seen-set,
                # so this probe answers the question it was written to answer — can the RANKER drift
                # on its own — rather than accidentally measuring rotation.
                ctx = {"self": (prof.get("name") or ""), "uid": "admin-stab", "seen": []}
                if pin:
                    ctx["now"] = float(pin)
                try:
                    outs.append([c.get("name") for c in match_candidates(intent, prof, ctx)])
                except Exception as e:
                    outs.append(["__error__: " + str(e)[:80]])
            first = outs[0]
            same_order = all(o == first for o in outs)
            same_set = all(set(o) == set(first) for o in outs)
            drift = sorted(set().union(*[set(o) for o in outs]) - set(first)) if not same_set else []
            send_json(self, 200, {"ok": True, "runs": runs, "n": len(first),
                                  "stableOrder": same_order, "stableSet": same_set,
                                  "pinnedNow": bool(pin), "drift": drift[:10],
                                  "slates": [o[:8] for o in outs]})
        elif p == "/api/agent/diversity":
            # «Мне попадаются одни и те же люди, какой бы запрос я ни написал.» That is a claim about
            # a SET of searches, so no single search can confirm or refute it. Run N topics as one
            # person and report how many distinct people came back and who keeps reappearing.
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            topics = [str(t).strip() for t in (body.get("topics") or []) if str(t).strip()][:24]
            base = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            ctx = {"self": (prof.get("name") or ""), "uid": "admin-div"}
            seen, per, empty = {}, [], []
            for t in topics:
                it = _normalize_intent(dict(base, topics=[t]))
                try:
                    cands = match_candidates(it, prof, dict(ctx))
                except Exception:
                    cands = []
                names = [c.get("name") for c in cands]
                per.append({"topic": t, "n": len(names), "names": names[:8]})
                if not names:
                    empty.append(t)
                for n in names:
                    seen[n] = seen.get(n, 0) + 1
            runs = max(1, len([p for p in per if p["n"]]))
            repeats = sorted(((v, k) for k, v in seen.items() if v > 1), reverse=True)[:10]
            send_json(self, 200, {"ok": True, "queries": len(topics), "withResults": runs,
                                  "distinctPeople": len(seen),
                                  "shownMoreThanOnce": sum(1 for v in seen.values() if v > 1),
                                  "topRepeats": [{"name": k, "times": v} for v, k in repeats],
                                  "emptyTopics": empty, "per": per})
        elif p == "/api/agent/funnel":
            # «Почему никого нет», as a shape rather than a slate: how the pool collapses, stage by
            # stage, with the exact gate string for each drop. Read-only, writes nothing, sends nothing.
            intent = _normalize_intent(body.get("intent"))
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            ctx = body.get("ctx") if isinstance(body.get("ctx"), dict) else {}
            if body.get("now"):
                ctx["now"] = float(body["now"])
            diag = {}
            try:
                cands = match_candidates(intent, prof, ctx, diag)
                send_json(self, 200, {"ok": True, "intent": intent, "funnel": diag,
                                      "names": [c.get("name") for c in cands]})
            except Exception as e:
                send_json(self, 200, {"ok": False, "error": str(e)[:200], "funnel": diag})
        else:
            return False
        return True

    def do_GET(self):
        if self._restored_get() or self._restored_admin_get():
            return
        if self.path == "/api/agent/weights":
            send_json(self, 200, {"weights": get_weights(),
                                  "core": {"enabled": CORE_V2,
                                           "config_version": (_CORE_CFG or {}).get("config_version"),
                                           "config_sha": ((_CORE_CFG or {}).get("_sha256") or "")[:12],
                                           "error": _CORE_ERR},
                                  "payment_invariant": PAYMENT_INVARIANT,      # §0 dec.10 / §11.3
                                  "release_status": RELEASE_STATUS,            # §1.2 pilot
                                  "pilot_decision_types": PILOT_DECISION_TYPES,
                                  "policy_decisions": ["ALLOW", "REVIEW", "BLOCK"],  # §0 output table
                                  "revalidation_checkpoints": list(_REVAL_CHECKPOINTS),  # §8.2
                                  "reason_codes": ["OK", "POLICY_CHANGED"],    # §8.2
                                  "decision_classes": ["strong_personal_candidate", "usable_personal_candidate",
                                                       "discovery_only", "clarification", "no_personal_outreach"],  # §9.6
                                  "config_ci": (_validate_math_config(_CORE_CFG, _core.FEATURE_KEYS,   # §9.5
                                                                      engine_version=(_CORE_CFG or {}).get("config_version"))
                                                if _CORE_CFG else {"ok": False, "error": _CORE_ERR}),
                                  "readiness_states": list(kcf.READINESS_EXPLAIN.keys()),  # §10.1
                                  "ml_boundary": kmlb.ML_BOUNDARY,             # §10.3
                                  "agent_protocol": {"actions": list(kp.ACTIONS),  # §13.1/§13.2/§13.3
                                                     "protocol_version": kp.PROTOCOL_VERSION,
                                                     "autonomy_boundaries": kp.AUTONOMY_BOUNDARIES}})
        elif self.path == "/api/agent/outcomes":
            send_json(self, 200, dict(_success_metrics(), match_capsules=_match_capsules()))  # §1 + §4.9
        elif self.path.split("?")[0] == "/api/agent/saved_searches":       # §12.2 step 7
            q = dict(kv.split("=", 1) for kv in self.path.split("?", 1)[-1].split("&") if "=" in kv) if "?" in self.path else {}
            send_json(self, 200, {"saved_searches": _list_saved_searches(q.get("uid", "me"))})
        elif self.path == "/api/agent/load":
            send_json(self, 200, {"state": _session("me").get("state")})
        elif self.path == "/api/agent/pool":
            # `bySource` and `store` are not decoration: the admin health bar compares the path the
            # ENGINE reports here against the path the PANEL uses, and that comparison is the only
            # automatic detector of the split-store failure (two services resolving users.json
            # differently, registrations landing in a file the matcher never reads). The rewrite
            # dropped both fields, so the detector had been silently reporting engine=None.
            c = load_candidates()
            src = {}
            for u in c:
                k = str(u.get("source") or "unknown")
                src[k] = src.get(k, 0) + 1
            try:
                st = os.stat(USERS_PATH)
                store = {"path": os.path.abspath(USERS_PATH), "mtime": int(st.st_mtime), "bytes": st.st_size}
            except Exception as e:
                store = {"path": os.path.abspath(USERS_PATH), "error": str(e)[:120]}
            send_json(self, 200, {"count": len(c), "fromStore": _users_cache["list"] is not None,
                                  "bySource": src, "store": store, "users": c})
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
        if self._restored_post(p, body) or self._restored_admin_post(p, body):
            return
        if p == "/api/agent/plan":
            q = str(body.get("query") or "")
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            ctx = body.get("ctx") if isinstance(body.get("ctx"), dict) else {}
            override = body.get("override") if isinstance(body.get("override"), dict) else None
            try:
                send_json(self, 200, agent_plan(q, prof, ctx, override))
            except Exception as e:
                send_json(self, 200, {"intent": _fallback_parse(q), "candidates": [], "error": str(e)[:200]})
        elif p == "/api/agent/explore":
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            send_json(self, 200, {"plans": explore_plans(
                limit=int(body.get("limit") or 12),
                self_name=body.get("self") or prof.get("name") or "",
                viewer_profile=prof,
            )})
        elif p == "/api/agent/match":
            # structured entry: caller (e.g. the buddy agent) already assembled the intent/signals -> skip LLM parse
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            ctx = body.get("ctx") if isinstance(body.get("ctx"), dict) else {}
            try:
                intent = kc.compile_intent(intent, _intent_identity(intent), ctx, ctx.get('now') or time.time())  # §4.3 blocks
                snap = _request_snapshot(intent)
                if not _pilot_enabled(intent):             # §1.2: a non-pilot decision type
                    # ...but STILL rank the people. Returning an empty slate here meant that adding
                    # `groupSize` to a request that found eight people found nobody, with the reason
                    # buried in a `pilot` field the UI never showed. The layer being off is a reason
                    # not to ASSEMBLE a group — never a reason to hide the people who fit.
                    ppl = match_candidates(dict(intent, groupSize=None, group=None,
                                                decisionType="person_to_person"), prof, ctx)
                    send_json(self, 200, {"intent": intent, "candidates": ppl, "snapshot": snap,
                                          "pilot": {"enabled": False, "decision_type": snap["decision_type"],
                                                    "note": "%s is not enabled in this pilot (%s)"
                                                            % (snap["decision_type"], RELEASE_STATUS),
                                                    "people_shown_anyway": len(ppl)}}); return
                cands = match_candidates(intent, prof, ctx)
                res = {"intent": intent, "candidates": cands, "snapshot": snap}
                res.update(_section5_addendum(intent, str(body.get("query") or ""), cands))  # §5.1/§5.2
                res["retrieval"] = _retrieval_report(cands)                                    # §7
                res["expansion"] = expansion_ladder(intent, ctx)                               # §12
                if snap["decision_type"] == "group_formation":     # §15: the slate becomes a group
                    res["group"] = form_group_from_slate(intent, cands,
                                                         body.get("constraints") if isinstance(body.get("constraints"), dict) else None,
                                                         now_ts=ctx.get("now"))
                if not cands:
                    res["fallback"] = _online_fallback(intent)
                    if kc.is_expired(intent, ctx.get('now')):     # §4.3 Lifecycle: distinguish expired from no-match
                        res["expired"] = True
                send_json(self, 200, res)
            except Exception as e:
                send_json(self, 200, {"intent": intent, "candidates": [], "error": str(e)[:200]})
        elif p == "/api/agent/confirm":
            # §5.1 confirmation flow: promote ONLY the confirmed sensitive constraints (required language,
            # dating mode) into active gates, then re-match. Unconfirmed constraints stay soft/absent.
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            ctx = body.get("ctx") if isinstance(body.get("ctx"), dict) else {}
            confirmed_ids = body.get("confirmed_ids") if isinstance(body.get("confirmed_ids"), list) else []
            query = str(body.get("query") or "")
            try:
                cons = body.get("constraints") if isinstance(body.get("constraints"), list) \
                    else ki.extract_constraints(query, intent)[1]
                conf = ki.apply_confirmation(intent, confirmed_ids, cons, now=ctx.get("now"))
                conf = kc.compile_intent(conf, _intent_identity(conf), ctx, ctx.get("now") or time.time())
                cands = match_candidates(conf, prof, ctx)
                res = {"intent": conf, "candidates": cands, "snapshot": _request_snapshot(conf),
                       "confirmed": conf.get("_confirmed")}
                res.update(_section5_addendum(conf, query, cands))
                res["expansion"] = expansion_ladder(conf, ctx)   # §12 controlled-expansion ladder (plan)
                if not cands:
                    res["fallback"] = _online_fallback(conf)      # §12 never dead-end even after a narrowing confirm
                send_json(self, 200, res)
            except Exception as e:
                send_json(self, 200, {"intent": intent, "candidates": [], "error": str(e)[:200]})
        elif p == "/api/agent/explain":
            # TWO tools under one name, chosen by whether a `candidate` is named:
            #   with candidate -> the per-pair decision trace (§21.3), «почему мне не попадается X»;
            #   without        -> the slate-wide diagnostic (matched + gated-out + per-feature).
            # The rewrite kept only the second, so the admin pair view silently got a slate dump and
            # found no trace in it. Both are real tools; neither is a rename of the other.
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            ctx = body.get("ctx") if isinstance(body.get("ctx"), dict) else {}
            who = str(body.get("candidate") or "").strip().lower()
            if not who:
                try:
                    send_json(self, 200, explain_match(intent, prof, ctx))
                except Exception as e:
                    send_json(self, 200, {"error": str(e)[:200], "matched": [], "excluded": [], "considered": []})
                return
            try:
                cand = next((c for c in load_candidates()
                             if str(c.get("name", "")).strip().lower() == who), None)
                if cand is None:
                    send_json(self, 200, {"ok": False, "error": "candidate not found in store"})
                elif not CORE_V2:
                    send_json(self, 200, {"ok": False, "error": "core v2 disabled (KLEAL_CORE_V2=0)"})
                else:
                    gate_ctx, self_name = _gate_ctx_and_self(ctx, prof)
                    ctx2 = dict(ctx)
                    ctx2.setdefault("now", time.time())
                    ctx2.setdefault("received24", _proposals_received_24h())
                    if self_name and str(cand.get("name", "")).strip().lower() == self_name:
                        send_json(self, 200, {"ok": True, "trace": {
                            "name": cand.get("name"), "shown": False, "steps": [
                                {"step": "self-match guard", "ok": False,
                                 "detail": "the searcher is never matched to themselves"}],
                            "drop_reason": "self-match: searcher == candidate"}})
                    else:
                        decision, why = _policy_decision(intent, cand, gate_ctx)
                        if decision == "BLOCK":
                            send_json(self, 200, {"ok": True, "trace": {
                                "name": cand.get("name"), "shown": False, "steps": [
                                    {"step": "eligibility hard gates", "ok": False, "detail": why}],
                                "drop_reason": "blocked by policy: %s" % why}})
                        else:
                            tr = _core.explain(intent, prof, ctx2, cand, _H, _CORE_CFG)
                            tr["steps"].insert(0, {"step": "eligibility hard gates", "ok": True,
                                                   "detail": decision})
                            send_json(self, 200, {"ok": True, "trace": tr})
            except Exception as e:
                send_json(self, 200, {"ok": False, "error": str(e)[:200]})
        elif p == "/api/agent/feedback":
            def _do_feedback():                                # §23.2.13 idempotent write (opt-in idempotency_key)
                ok = record_feedback(body.get("name"), body.get("decision"), body.get("uid", "me"),
                                     purpose=body.get("purpose"))   # §17.2 optional mode-scoped feedback (dating isolation)
                return {"ok": bool(ok), "feedback": _session("me").get("feedback")}
            send_json(self, 200, _idempotent(body.get("idempotency_key"), "feedback",
                                             body.get("name"), body.get("decision"), _do_feedback))
        elif p == "/api/agent/outcome":
            # §1 success lifecycle: record proposed/accepted/declined/completed/expired_no_response.
            # §14 idempotency: if the caller passes an idempotency_key, a REPLAY of the same key returns the
            # prior metrics (error_code DUPLICATE) instead of double-appending. Without a key -> unchanged append.
            idem = body.get("idempotency_key")
            key = ks.dedup_key("outcome", body.get("name"), body.get("stage"), extra=idem) if idem else None
            with _STORE_LOCK:                          # §14: check + record + memoize ATOMICALLY (RLock -> _record_outcome
                prior = (SESSION.get("_outcome_seen") or {}).get(key) if key else None   # re-enters safely). One lock closes
                if prior is not None:                  # the read-then-write gap so a concurrent replay can't double-append.
                    payload = dict(prior, duplicate=True, error_code="DUPLICATE")
                else:
                    ok = _record_outcome(body.get("name"), body.get("stage"), body.get("uid", "me"))
                    payload = {"ok": bool(ok), "stages": list(_OUTCOME_STAGES),
                               "metrics": _success_metrics(), "match_capsules": _match_capsules()}
                    if key and ok:                     # memoize only a real applied outcome (a failed record can retry)
                        SESSION.setdefault("_outcome_seen", {})[key] = payload; _save_store()
            send_json(self, 200, payload)              # network I/O outside the lock
        elif p == "/api/agent/transition":
            # §14 validated state transition (WITHDRAW/EXPIRE/COUNTER/...): edge check + optimistic CAS +
            # idempotent replay. Under the reentrant store lock; appends an immutable audit trace on success.
            try:
                send_json(self, 200, agent_transition(body if isinstance(body, dict) else {}))
            except Exception as e:
                send_json(self, 200, {"ok": False, "error_code": "ILLEGAL_TRANSITION", "error": str(e)[:200]})
        elif p == "/api/agent/group":
            # §15 group formation — PILOT-DISABLED scaffolding. Returns enabled:False unless the EXACT test-only
            # override {'enable_group_formation': True} is present. NEVER flips PILOT_DECISION_TYPES and NEVER
            # touches the person-to-person slate (kg is a separate keyless module). Config-derived weights;
            # the last-seat capacity race reuses §14 (ks.claim_slot) via a SESSION-backed seat ledger.
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            cands = body.get("candidates") if isinstance(body.get("candidates"), list) else []
            constraints = body.get("constraints") if isinstance(body.get("constraints"), dict) else {}
            override = body.get("override")
            if GROUPS_ENABLED and not kg.is_override_enabled(override):
                override = _GROUP_OVERRIDE      # the product switch decides, not the request body
            if not cands:
                # §15 forms a group out of a slate it is GIVEN; it never retrieves. An empty body
                # therefore answered NO_FEASIBLE_GROUP, which reads as the algorithm rejecting the
                # request when it had simply been handed nobody. Rank first, then form.
                prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
                ctx = body.get("ctx") if isinstance(body.get("ctx"), dict) else {}
                try:
                    cands = match_candidates(intent, prof, ctx)
                except Exception:
                    cands = []
            cands = _group_slate(cands)               # lcb -> relevance, the §15 star-fallback input
            constraints = _group_constraints(intent, constraints)   # groupSize + §15.4 pack -> seat counts
            reserve = bool(body.get("reserve"))       # claiming seats is a commit, never a preview
            try:
                if kg.is_override_enabled(override) and reserve:   # real seat ledger + reservations
                    with _STORE_LOCK:
                        led = SESSION.setdefault("_group_ledger", {})
                        res = dict(kg.run_group_formation(intent, cands, constraints, _CORE_CFG, override=override,
                                                          now_ts=body.get("now") or time.time(), ledger=led,
                                                          pair_rel=body.get("pair_rel")),
                                   group_formation_live=GROUPS_ENABLED, reserved=True)
                        _save_store()
                elif kg.is_override_enabled(override):
                    res = dict(kg.run_group_formation(intent, cands, constraints, _CORE_CFG,
                                                      override=override, now_ts=body.get("now") or time.time(),
                                                      ledger=None, pair_rel=body.get("pair_rel")),
                               group_formation_live=GROUPS_ENABLED, reserved=False)
                else:
                    res = kg.run_group_formation(intent, cands, constraints, _CORE_CFG, override=override)
                send_json(self, 200, res)
            except Exception as e:
                send_json(self, 200, dict(kg.dormant_response(intent, constraints), error=str(e)[:200]))
        elif p in ("/api/agent/event", "/api/agent/room", "/api/agent/venue"):
            # §16 events/rooms/venues — PILOT-DISABLED scaffolding, DISTINCT per-kind path (event != user-with-
            # capacity). Returns enabled:False unless the EXACT override {'enable_intent_to_<kind>': True}. NEVER
            # flips PILOT_DECISION_TYPES; NEVER touches the person slate. Read-only ranking (no reservation side-
            # effect); cfg is accepted but never influences a score (§16 ranking is module-local, not config-derived).
            kind = p.rsplit("/", 1)[-1]
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            objects = (body.get("objects") if isinstance(body.get("objects"), list)
                       else body.get("candidates") if isinstance(body.get("candidates"), list) else [])
            user = (body.get("user") if isinstance(body.get("user"), dict)
                    else body.get("profile") if isinstance(body.get("profile"), dict) else {})
            try:
                send_json(self, 200, kct.run_candidates(kind, intent, objects, user, cfg=_CORE_CFG,
                                                        override=body.get("override"),
                                                        now_ts=body.get("now") or time.time()))
            except Exception as e:
                send_json(self, 200, dict(kct.dormant_response(kind, intent), error=str(e)[:200]))
        elif p == "/api/agent/save_search":
            # §12.2 step 7: persist a search to notify later (SESSION only; no users.json writer).
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            send_json(self, 200, {"id": _save_search(intent, body.get("uid", "me")),
                                  "saved_searches": _list_saved_searches(body.get("uid", "me"))})
        elif p == "/api/agent/save_search/check":
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            send_json(self, 200, {"checked": _check_saved_searches(prof, body.get("uid", "me"))})
        elif p == "/api/agent/save_search/delete":
            send_json(self, 200, {"deleted": _delete_saved_search(body.get("id"), body.get("uid", "me")),
                                  "saved_searches": _list_saved_searches(body.get("uid", "me"))})
        elif p == "/api/agent/revalidate":
            # §8.2 #3-#7: re-decide a pair against the live store at a checkpoint; POLICY_CHANGED if stricter.
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            cand = body.get("candidate") if isinstance(body.get("candidate"), dict) else {}
            checkpoint = str(body.get("checkpoint") or "profile_open")
            try:
                send_json(self, 200, revalidate(intent, cand, checkpoint, body.get("now")))
            except Exception as e:
                send_json(self, 200, {"decision": "ALLOW", "code": "OK", "error": str(e)[:200]})
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
        elif p == "/api/agent/negotiate":
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            cands = body.get("candidates") if isinstance(body.get("candidates"), list) else []
            # §22.2.3/§23.2.13 controlled proposals: a re-send of the SAME (intent, candidate set) is idempotent —
            # memoized so it never double-emits proposals. Content-keyed (intent id + sorted names).
            _iid = (intent.get("identity") or {}).get("intent_id") or intent.get("title") or ",".join(intent.get("topics") or [])
            _names = ",".join(sorted(str(c.get("name")) for c in cands if isinstance(c, dict)))
            def _do_negotiate():
                try:
                    return {"candidates": negotiate_candidates(intent, cands)}
                except Exception as e:
                    return {"candidates": cands, "error": str(e)[:200]}
            send_json(self, 200, _idempotent(body.get("idempotency_key") or ("auto:%s" % _iid),
                                             "negotiate", _names, "send", _do_negotiate))
        elif p == "/api/agent/proposal":
            try: send_json(self, 200, proposal_create(body if isinstance(body, dict) else {}))
            except Exception as e: send_json(self, 200, {"error": str(e)[:200]})
        elif p == "/api/agent/proposal/respond":
            try: send_json(self, 200, proposal_respond(body if isinstance(body, dict) else {}))
            except Exception as e: send_json(self, 200, {"ok": False, "error": str(e)[:200]})
        elif p == "/api/agent/plan_resource":
            try: send_json(self, 200, plan_resource(body if isinstance(body, dict) else {}))
            except Exception as e: send_json(self, 200, {"ok": False, "error": str(e)[:200]})
        elif p == "/api/agent/intents/compile":
            try: send_json(self, 200, compile_endpoint(body if isinstance(body, dict) else {}))
            except Exception as e: send_json(self, 200, {"intent": {}, "error": str(e)[:200]})
        elif p == "/api/agent/expand":
            try: send_json(self, 200, expand_one_axis(body if isinstance(body, dict) else {}))
            except Exception as e: send_json(self, 200, {"candidates": [], "error": str(e)[:200]})
        else:
            send_json(self, 404, {})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Kleal matching-service on http://127.0.0.1:%d  (LLM via llm-service)" % PORT)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
