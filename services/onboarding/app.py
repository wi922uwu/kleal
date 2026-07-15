# -*- coding: utf-8 -*-
# Kleal onboarding-service — the profile-setup funnel (messenger UI + /api/onboarding/*).
# Carved from the pre-split monolith kleal_v2.py (onboarding half, lines 16-301 + the embedded HTML).
# Talks to llm-service over HTTP for every extract/reply/summary turn; holds NO model keys.
# Contract: ../../shared/contracts.md. Owner: Dev A.
import os, sys, json, re, threading
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "..", "..", "shared"), os.path.join(_HERE, "shared")):
    if os.path.isdir(_p) and _p not in sys.path: sys.path.insert(0, _p)
import kleal_lib as base                      # keyless shared helpers/prompts (was `import llm_demo_local as base`)
from llm_client import llm_complete           # the ONLY model access (HTTP -> llm-service)
from http_util import send, send_json, read_json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("ONBOARDING_PORT", "7072"))
MODEL_ID = os.environ.get("V2_MODEL", "llama_self")


# ---------------------------------------------------------------- restructured gate (V2)
_chas, _cset, _cpath = base._chas, base._cset, base._cpath

CRIT_V2 = [
    ("Name",        lambda p: _chas(p, "name")),
    ("Age 18+",     lambda p: _cset(p, "ageVerified18")),
    ("Gender",      lambda p: _chas(p, "gender")),
    ("Photo",       lambda p: _cpath(p, "photoStatus") == "uploaded"),
    ("Languages",   lambda p: _chas(p, "languages.comfortable")),
    ("Interests",   lambda p: _chas(p, "interests.explicit")),
    ("Area",        lambda p: _chas(p, "geo.comfortableAreas") or _chas(p, "city")),
    ("Radius",      lambda p: _cset(p, "geo.maxDistanceKm")),
    ("Safety mode", lambda p: any(_cset(p, k) for k in ("safety.verifiedOnly", "safety.publicPlacesOnly", "safety.noPrivateLocations", "geo.publicPlacesOnly"))),
    ("Consent",     lambda p: _cset(p, "permissions.useProfileForMatching")),
    ("Adjacent",    lambda p: _cset(p, "permissions.allowAdjacentMatches")),
]

# ---- per-interest funnel plan: max 2 questions per interest (role + experience, then ONE domain detail)
def _v2_ints(p):
    v = _cpath(p, "interests.explicit") or []
    if isinstance(v, str): v = [v]
    return [x for x in v if isinstance(x, str) and x.strip()]

def _v2_roles(p):
    """Flatten interests.roles into {interest_lower: role}; tolerates nested/list/str shapes."""
    r = _cpath(p, "interests.roles"); out = {}
    def eat(d):
        for k, v in d.items():
            if isinstance(v, dict) and str(k).lower() in ("interest", "interests", "roles"): eat(v)
            elif v: out[str(k).lower()] = v
    if isinstance(r, dict): eat(r)
    return out, r

def _v2_role_of(p, name):
    m, raw = _v2_roles(p); key = name.lower()
    for k, v in m.items():
        if key == k or key in k or k in key: return v
    if isinstance(raw, (str, list)) and raw and len(_v2_ints(p)) == 1: return raw
    return None

def _v2_exp_of(p, name):
    e = _cpath(p, "interests.experienceByInterest"); key = name.lower()
    if isinstance(e, dict):
        for k, v in e.items():
            kl = str(k).lower()
            if v and (key == kl or key in kl or kl in key): return v
    return None

def _v2_role_exp_spec(p):
    """Gate additions driving the progress %: per explicit interest, Role + Experience."""
    out = []
    for it in _v2_ints(p):
        out.append(("Role: " + it, lambda p, i=it: bool(_v2_role_of(p, i))))
        out.append(("Experience: " + it, lambda p, i=it: bool(_v2_exp_of(p, i))))
    return out

def critical_status_v2(p):
    p = p if isinstance(p, dict) else {}
    spec = CRIT_V2 + _v2_role_exp_spec(p)   # + role/experience per picked interest
    done, missing = [], []
    for label, chk in spec:
        try:
            ok = chk(p)
        except Exception:
            ok = False
        (done if ok else missing).append(label)
    total = len(spec)
    return {"done": done, "missing": missing, "total": total,
            "complete": len(missing) == 0, "pct": int(100 * len(done) / total) if total else 0}

# ---------------------------------------------------------------- interests-funnel chat prompt (interests step)
FUNNEL_PROMPT = '''You are Kleal, on the INTERESTS step of a short profile setup.
The user already gave their name, area and languages - do NOT ask about those.
Your job: understand each picked interest quickly. You get AT MOST TWO questions per interest, so make them count:
- First: HOW THEY ENGAGE with it (fit the interest - play vs watch for a game or sport; watch or discuss for shows; build / discuss / learn / attend events for a topic like AI or startups; practise + level for a language; the vibe for a social thing like coffee) AND how long they have been into it - both in one natural message. NEVER offer play/watch choices for something you cannot play or watch.
- Then, only where a domain applies, ONE most-useful detail: games -> platform + rank/level (one combined question); sport they play -> skill level; sport they watch -> favorite team; language -> current level; networking -> industry + goal.
Style: react warmly to what they just said in ONE short line, then ask. One question message per turn, the question is the LAST thing in the reply. English only. For closed choices end with [OPTIONS: a | b | c] (pipe-separated only, no letters/numbers). NEVER re-ask anything already known. No emoji, no markdown, no JSON, no <profile> tags.
A status line tells you exactly what to ask next - follow it strictly.'''

# finish / add-another intent detection at the confirm stage (order matters: FIN first - "no more" contains "more")
_FIN_RE = re.compile(r"that'?s all|that is all|\bfinish|\bdone\b|no more|nothing else|i'?m good|all set|\bnope\b|^\s*no[.! ]*$", re.I)
_ADD_RE = re.compile(r"\badd\b|another|one more|\bmore\b|\byes\b|yeah|sure|\balso\b|actually", re.I)

# gibberish / non-answer detection: catch keyboard-mash like "afcafcafc" / "ппфцпц" so the funnel
# re-asks instead of silently accepting junk and moving on.
_VOWELS = "aeiouyауоыиэяюёеAEIOUYАУОЫИЭЯЮЁЕ"
_KBD_MASH = {"asdf", "asdfg", "asdfgh", "asdfghjkl", "qwer", "qwert", "qwerty", "qwertyu",
             "zxcv", "zxcvb", "zxcvbn", "hjkl", "asd", "qwe", "zxc", "qaz", "wsx", "edc",
             "йцук", "йцуке", "йцукен", "фыва", "фывап", "ячсм", "ячсми", "ячсмит", "цук", "фыв"}
def _is_gibberish(text):
    """True when a message reads like random characters / a keyboard mash rather than a real answer.
    Conservative: only flags when EVERY 4+ letter token looks unpronounceable, so real short answers
    (PC, B1, 5y, Ancient, coffee...) always pass."""
    t = (text or "").strip().lower()
    letters = re.sub(r"[^a-zа-яё]", "", t)
    if len(letters) < 4:
        return False  # short answers are legitimate (PC, no, B1, 5y)
    words = [w for w in re.findall(r"[a-zа-яё]{2,}", t) if len(w) >= 4]
    if not words:
        return False
    vset = set(_VOWELS.lower())
    conrun = re.compile(r"[^" + _VOWELS.lower() + r"]{4,}")
    def periodic(w):                        # a short pattern tiled: "abcabc", "пвапвап", "аываыва"
        return any(all(w[i] == w[i % p] for i in range(len(w))) for p in range(1, len(w) // 2 + 1))
    def bad(w):
        if w in _KBD_MASH:
            return True
        vr = sum(1 for c in w if c in vset) / len(w)
        if vr < 0.2 or vr > 0.85:           # too few / too many vowels -> unpronounceable
            return True
        if conrun.search(w):                # long consonant run
            return True
        if len(set(w)) <= max(2, len(w) // 3):  # very repetitive (few unique letters)
            return True
        if len(w) >= 5 and periodic(w):     # a tiled n-gram pattern
            return True
        return False
    return all(bad(w) for w in words)

def _v2_listhas(p, path, name):
    v = _cpath(p, path) or []
    key = name.lower()
    return any(isinstance(x, str) and (key == x.lower() or key in x.lower() or x.lower() in key)
               for x in (v if isinstance(v, list) else [v]))

# classify an interest by NAME (before any domain is extracted) so the ROLE question fits it -
# "do you play or watch" makes sense for a game/sport, but is nonsense for AI or coffee.
def _v2_kind(it):
    n = (it or "").lower()
    if re.search(r"dota|valorant|league|\bcs\b|apex|fortnite|fifa|minecraft|\bgame|gaming|esport", n): return "game"
    if re.search(r"football|soccer|basket|tennis|\bgym\b|\brun|\bbox|climb|swim|cycl|\bhik|volleyball|skate|yoga|padel|surf|ski", n): return "sport"
    if re.search(r"movie|cinema|film|series|\bshow|anime|\btv\b|netflix|k-?drama", n): return "watch"
    if re.search(r"language|spanish|english|french|german|italian|portuguese|japanese|chinese|practice|duolingo", n): return "language"
    if re.search(r"\bai\b|\bml\b|startup|\btech|business|career|founder|network|invest|product|\bdesign|architect|coding|program|marketing|crypto", n): return "topic"
    return "social"

_ROLE_FRAME = {
    "game":     "whether they mainly play it or watch it",
    "sport":    "whether they play it or mostly watch it",
    "watch":    "how they like to enjoy it - on their own, watch-parties, or discussing it",
    "language": "how they practise it and roughly their level",
    "topic":    "how they engage with it - building, discussing, learning, or going to events",
    "social":   "what they enjoy most about it and who they usually do it with",
}
def _v2_frame(it): return _ROLE_FRAME.get(_v2_kind(it), "what they enjoy doing with it")

def _v2_detail_gap(p, it):
    """The ONE domain-detail question for this interest, or None (no domain / already known)."""
    role = json.dumps(_v2_role_of(p, it) or "").lower()
    if _v2_listhas(p, "domains.games.gamesList", it):
        if _chas(p, "domains.games.platformsByGame") or _chas(p, "domains.games.rankByGame"): return None
        return 'for "%s": which platform they play on and roughly their rank or level (one combined question)' % it
    if _v2_listhas(p, "domains.sport.sportsList", it):
        if "play" in role:
            if _chas(p, "domains.sport.skillLevelBySport"): return None
            return 'for "%s": their skill level (beginner / intermediate / advanced)' % it
        if _chas(p, "domains.sport.favoriteTeams"): return None
        return 'for "%s": whether they have a favorite team' % it
    low = it.lower()
    if any(w in low for w in ("language", "practice", "spanish", "english", "french", "german")):
        if _chas(p, "domains.language.targetLevel"): return None
        return 'for "%s": their current level (beginner / intermediate / fluent)' % it
    if any(w in low for w in ("network", "startup", "business", "career")):
        if _chas(p, "domains.networking.industry") or _chas(p, "domains.networking.goal"): return None
        return 'for "%s": their industry and what they want out of it' % it
    return None

def _v2_gaps(p, hist):
    """Ask-ordered funnel gaps honoring the max-2-questions-per-interest budget. Stateless: an
    interest's spent budget is estimated by how many agent turns already mentioned it by name."""
    gaps = []
    for it in _v2_ints(p):
        low = it.lower()
        asked = sum(1 for m in hist if m.get("role") == "assistant" and low in str(m.get("content", "")).lower())
        if asked >= 2: continue  # budget spent - move on even if something stayed unknown
        role, exp = _v2_role_of(p, it), _v2_exp_of(p, it)
        need = []
        if not role and not exp:
            need.append('for "%s": %s, AND how long they have been into it - both in ONE natural combined question that fits this interest (do NOT offer play/watch options for a non-game/sport interest)' % (it, _v2_frame(it)))
        elif not role:
            need.append('for "%s": %s (phrase it to fit this interest, not a generic play/watch list)' % (it, _v2_frame(it)))
        elif not exp:
            need.append('for "%s": how long they have been into it' % it)
        if role and exp:
            d = _v2_detail_gap(p, it)
            if d: need.append(d)
        gaps.extend(need[:max(0, 2 - asked)])
    return gaps

def _norm_options(options):
    """Models sometimes jam choices into one comma blob or prefix them (a) / 1.). Split + clean -> chips."""
    raw = list(options or [])
    if len(raw) == 1 and re.search(r"[;,|]|\b[b-d]\)", raw[0]):
        raw = re.split(r"\s*[;,|]\s*|\s+(?=[a-d]\))", raw[0])
    out = []
    for o in raw:
        o = re.sub(r"^\s*(?:[a-zA-Z]\)|\d+[.)]|[-•])\s*", "", str(o)).strip()
        if o and o.lower() not in (x.lower() for x in out):
            out.append(o)
    return out[:6]

# extractor with V2 extras: per-interest experience/tenure ("how long have you been into it")
EXTRACT_V2 = base.EXTRACT_PROMPT + '''
ALSO extract, under the same iron rules (ONLY if the user explicitly said it):
interests.experienceByInterest = {"<interest exactly as named in explicit>": "<how long they have been into it, short: '5 years', 'since school', 'just started'>"} - one entry per interest whose experience/tenure the user stated.'''

# the stored artifact: ONE continuous plain-text summary describing everything about the user
SUMMARY_PROMPT = '''You are Kleal, a personal social agent. You store your memory of a user as ONE continuous plain-text summary.
Given the profile JSON, write that summary: English, second person ("You're ..."), 4-8 sentences, warm but strictly factual.
Cover, when present in the JSON: who they are (name, age, gender), where and how far they go (area, radius), languages, EVERY interest with its role, how long they have been into it and key details (platform, rank, team, level, industry), how they like to connect, and their safety choices and permissions.
STRICT: only facts present in the JSON - NEVER invent or embellish. No lists, no markdown, no headings, no emoji, no JSON. Plain flowing text only.'''

def v2_summary(profile):
    """One LLM call -> the running text summary we store for the user (profile.summary)."""
    cfg = MODEL_ID
    prof = {k: v for k, v in (profile or {}).items() if k not in ("photo", "summary")}
    raw = llm_complete(cfg, [{"role": "system", "content": SUMMARY_PROMPT},
                              {"role": "user", "content": json.dumps(prof, ensure_ascii=False)}], 0.4)
    txt = base.parse_reply(raw)[0]
    txt = (txt or "").replace("—", "-").replace("–", "-").strip()
    return {"summary": txt}

def v2_chat(messages, prior):
    """Interests-step turn: extract first (sequential), then a focused funnel reply. Mirrors the
    base two-call pipeline but scoped to interests/roles/domain detail. Returns merged profile + crit."""
    cfg = MODEL_ID
    hist = [m for m in messages if m.get("role") in ("user", "assistant")]
    result = {"profile": None}
    def _job():
        try:
            lines = []
            for mm in hist:
                who = "User" if mm.get("role") == "user" else "Agent"
                lines.append(who + ": " + str(mm.get("content", "")))
            ext_raw = llm_complete(cfg, [{"role": "system", "content": EXTRACT_V2},
                                          {"role": "user", "content": "\n".join(lines)}], 0.1)
            prof = base._extract_json(ext_raw)
            if isinstance(prof, dict):
                prof = base._clean_profile(prof)
                prof = {k: v for k, v in prof.items() if k in base.KNOWN_TOP}
                result["profile"] = prof or None
        except Exception:
            result["profile"] = None
    if any(m.get("role") == "user" for m in hist):
        _t = threading.Thread(target=_job, daemon=True); _t.start(); _t.join(timeout=220)
    merged = base._deep_merge(dict(prior), result["profile"] or {})
    crit = critical_status_v2(merged)
    gaps = _v2_gaps(merged, hist)
    lastu = next((str(m.get("content", "")) for m in reversed(hist) if m.get("role") == "user"), "")
    confirm_asked = any(m.get("role") == "assistant" and "another interest" in str(m.get("content", "")).lower()
                        for m in hist)
    sys = FUNNEL_PROMPT
    complete = False
    if _is_gibberish(lastu):
        # user typed junk / random characters - do NOT advance or wrap up, gently re-ask.
        sys += (" [The user's last message does not look like a real answer - it reads like random "
                "characters or a keyboard mash. In ONE short, warm line say you did not quite catch that, "
                "then re-ask YOUR OWN PREVIOUS question in simpler words. Ask EXACTLY ONE question and keep "
                "the same [OPTIONS: ...] if your previous question had them. Do NOT move to a new topic and "
                "do NOT wrap up.]")
    elif gaps:
        sys += (" [NEXT GAP TO CLOSE: ask %s. Exactly ONE question message - warm reaction line first. "
                "If it is a closed choice end with [OPTIONS: a | b | c] (pipe-separated only). "
                "Never re-ask anything already known. Queued after this: %s]"
                % (gaps[0], "; ".join(gaps[1:3]) or "none"))
    elif confirm_asked and _FIN_RE.search(lastu):
        complete = True
        sys += (" [The user confirmed they are done with interests. Reply ONE short, warm wrap-up sentence "
                "that ends in a period (NEVER a question mark) and tells them to tap Continue. No [OPTIONS].]")
    elif confirm_asked and _ADD_RE.search(lastu):
        sys += " [The user wants to add another interest. Ask ONE short question: what else they are into. No [OPTIONS].]"
    else:
        # confirm-before-finish: never end the interests step without asking
        sys += (" [ALL PICKED INTERESTS ARE COVERED. Ask EXACTLY ONE closing question: would they like to add "
                "another interest, or is that everything for now. End with [OPTIONS: Add another interest | That's all]. "
                "Nothing else.]")
    raw = llm_complete(cfg, [{"role": "system", "content": sys}] + hist, 0.6)
    reply, _p, _i, _b, _s, options = base.parse_reply(raw)
    options = _norm_options(options)
    reply = base.dose_reply(base.sanitize_output(base.guard_reply(reply)))
    reply = reply.replace("—", "-").replace("–", "-")  # taste-skill: no em/en-dash in user-visible copy
    if not (reply or "").strip():
        reply = "Tell me a bit more. What do you like to do with it?"
    # funnelComplete = no gaps left AND the user explicitly confirmed they are done adding interests
    return {"reply": reply, "options": options, "profile": merged, "crit": crit,
            "funnelComplete": complete, "gibberish": bool(_is_gibberish(lastu))}

HTML = r'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,viewport-fit=cover">
<title>Kleal - Onboarding</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
:root{
  --accent:#F5455C; --accent-soft:#FDE7EB; --ink:#181B22; --bg:#F6F7F9; --card:#FFFFFF;
  --bot:#EEEFF2; --line:#E7E8EC; --muted:#6B7180; --field:#F1F2F5; --ok:#2BB673; --track:#E5E7EB;
}
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
html,body{height:100%}
body{background:#2b2d33;display:flex;align-items:center;justify-content:center;
  font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Inter,sans-serif;color:var(--ink)}
.phone{width:390px;height:844px;max-height:100vh;background:var(--bg);border-radius:44px;overflow:hidden;
  position:relative;display:flex;flex-direction:column;box-shadow:0 30px 90px #0008}
@media(max-width:430px){body{background:var(--bg)}.phone{width:100vw;height:100vh;border-radius:0}}
.statusbar{flex:none;height:46px;display:flex;align-items:center;justify-content:space-between;
  padding:0 22px 0 26px;font-weight:600;font-size:14px;color:var(--ink)}
.statusbar .notch{width:88px;height:26px;background:#000;border-radius:14px}
.statusbar .ic{display:flex;gap:6px;align-items:center}
.statusbar .ic svg{display:block}
#app{flex:1;display:flex;flex-direction:column;min-height:0}

/* header */
.head{flex:none;padding:18px 18px 12px;display:flex;align-items:center;gap:12px}
.ava{width:38px;height:38px;border-radius:50%;flex:none;background-size:cover;background-position:center;
  display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:17px;
  background:linear-gradient(135deg,#FF7A8A,#F5455C)}
.ht{flex:1;min-width:0}
.htt{font-weight:700;font-size:16px;letter-spacing:-.01em;text-align:center}
.hsub{font-size:12px;color:var(--muted);margin-top:1px}
.prow{display:flex;align-items:center;gap:9px;margin-top:7px}
.pbar{height:4px;border-radius:3px;background:var(--track);overflow:hidden;flex:1}
.pbar>i{display:block;height:100%;background:var(--accent);border-radius:3px;width:0;
  transition:width .5s cubic-bezier(.4,0,.2,1)}
.pct{font-size:12.5px;color:var(--muted);font-weight:600;flex:none}

/* thread */
.thread{flex:1;overflow-y:auto;padding:8px 16px 14px;display:flex;flex-direction:column;gap:7px}
.thread::-webkit-scrollbar{width:0}
.row{display:flex;flex-direction:column;max-width:100%}
.bub{max-width:80%;padding:11px 14px;border-radius:17px;font-size:14.5px;line-height:1.38;white-space:pre-wrap;word-wrap:break-word}
.bub.bot{align-self:flex-start;background:var(--bot);color:var(--ink)}
.bub.me{align-self:flex-end;background:var(--accent);color:#fff}
.time{font-size:11px;color:var(--muted);margin:1px 6px 3px}
.time.me{align-self:flex-end}
.hint{font-size:12px;color:var(--muted);margin:4px 2px 2px}
.typing{align-self:flex-start;background:var(--bot);border-radius:20px;border-bottom-left-radius:7px;
  padding:13px 15px;display:flex;gap:5px}
.typing i{width:7px;height:7px;border-radius:50%;background:#AEB3BC;animation:tp 1.1s infinite}
.typing i:nth-child(2){animation-delay:.16s}.typing i:nth-child(3){animation-delay:.32s}
@keyframes tp{0%,60%,100%{opacity:.35;transform:translateY(0)}30%{opacity:1;transform:translateY(-3px)}}

/* inline widgets live in the thread */
.w{align-self:stretch;margin:3px 0 2px}
.chips{display:flex;flex-wrap:wrap;gap:9px}
.chip{border:1.5px solid var(--line);background:#fff;border-radius:22px;padding:10px 16px;
  font:600 14px inherit;color:var(--ink);cursor:pointer;user-select:none;transition:.12s}
.chip:active{transform:scale(.97)}
.chip.on{background:var(--accent);border-color:var(--accent);color:#fff}
.addrow{display:flex;align-items:center;gap:10px;background:#fff;border:1.5px solid var(--line);
  border-radius:16px;padding:4px 6px 4px 14px;margin-top:10px}
.addrow .ai{color:var(--muted);display:flex}
.addrow input{flex:1;border:0;outline:none;font:14px inherit;background:none;padding:10px 0}
.addrow.foc{border-color:var(--accent)}
.addrow .go{width:36px;height:36px;border-radius:50%;border:0;background:var(--field);color:var(--ink);
  display:flex;align-items:center;justify-content:center;cursor:pointer}

/* form card (basics) */
.card{background:#fff;border:1px solid var(--line);border-radius:18px;padding:16px}
.photo{width:96px;height:96px;border-radius:50%;background:var(--field);margin:2px auto 0;position:relative;
  display:flex;align-items:center;justify-content:center;cursor:pointer;background-size:cover;background-position:center}
.photo .ph{color:#9AA0AB;display:flex}
.photo .cam{position:absolute;right:0;bottom:0;width:30px;height:30px;border-radius:50%;background:var(--accent);
  color:#fff;display:flex;align-items:center;justify-content:center;border:3px solid #fff}
.cap{text-align:center;font-size:12px;color:var(--muted);margin-top:8px}
.lbl{font-size:12.5px;color:var(--muted);margin:14px 0 6px;font-weight:600}
.inp{width:100%;height:48px;border:1.5px solid var(--line);background:#fff;border-radius:13px;padding:0 15px;
  font:15px inherit;color:var(--ink);outline:none}
.inp:focus{border-color:var(--accent)}
.inp::placeholder{color:#8A8F9A}
.cwrap input::placeholder,.addrow input::placeholder{color:#8A8F9A}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:9px}
.grid3 .chip{text-align:center;padding:12px 4px}
.warn{color:var(--accent);font-size:12px;margin-top:6px;display:none}

/* option cards (connect) */
.opts{display:flex;flex-direction:column;gap:9px}
.opt{display:flex;align-items:center;gap:13px;background:#fff;border:1.5px solid var(--line);border-radius:16px;
  padding:13px 14px;cursor:pointer;transition:.12s}
.opt:active{transform:scale(.99)}
.opt.on{border-color:var(--accent)}
.oic{width:38px;height:38px;border-radius:11px;background:var(--field);color:var(--ink);display:flex;
  align-items:center;justify-content:center;flex:none}
.opt.on .oic{background:var(--accent-soft);color:var(--accent)}
.ot{flex:1;min-width:0}.otn{font-weight:700;font-size:15px}.ots{font-size:12.5px;color:var(--muted);margin-top:1px}
.ock{width:24px;height:24px;flex:none;display:flex;align-items:center;justify-content:center;color:var(--accent)}
.ock svg{opacity:0}
.opt.on .ock svg{opacity:1}

/* toggles (safety) */
.feat{display:flex;align-items:center;gap:13px;background:#fff;border:1.5px solid var(--accent);border-radius:16px;
  padding:13px 14px;margin-bottom:4px}
.feat .oic{background:var(--accent-soft);color:var(--accent)}
.pillbadge{font-size:11px;font-weight:700;color:var(--accent);background:var(--accent-soft);
  padding:4px 9px;border-radius:20px}
.tog{display:flex;align-items:center;gap:13px;background:#fff;border:1.5px solid var(--line);border-radius:16px;
  padding:13px 14px;margin-top:9px;cursor:pointer}
.tog.feat{border-color:var(--accent);margin-top:0;margin-bottom:4px}
.tog.feat .oic{background:var(--accent-soft);color:var(--accent)}
.sw{width:46px;height:28px;border-radius:16px;background:#D7D9DF;flex:none;position:relative;transition:background .2s}
.sw>i{position:absolute;top:3px;left:3px;width:22px;height:22px;border-radius:50%;background:#fff;
  box-shadow:0 1px 3px #0003;transition:left .2s}
.tog.on .sw{background:var(--accent)}.tog.on .sw>i{left:21px}
/* Recommended card (Figma "Recommended Card v2") — nudge, not a toggle */
.reccard{display:flex;align-items:center;gap:12px;background:#fff;border:1px solid var(--line);border-radius:16px;
  padding:14px 16px;cursor:pointer;margin-bottom:14px}
.reccard .recchip{width:40px;height:40px;border-radius:12px;background:var(--accent-soft);color:var(--accent);
  display:flex;align-items:center;justify-content:center;flex:none}
.reccard .rectx{flex:1;min-width:0}
.reccard .reclbl{font-size:11px;font-weight:600;color:var(--muted);letter-spacing:.01em}
.reccard .rectitle{font-size:16px;font-weight:700;margin-top:3px;letter-spacing:-.01em}
.reccard .recnote{font-size:12.5px;color:var(--muted);margin-top:8px;line-height:1.4;display:none}
.reccard.open .recnote{display:block}
.reccard .recarw{color:var(--muted);flex:none;display:flex;transition:transform .2s}
.reccard.open .recarw{transform:rotate(90deg)}

/* geo */
.map{height:150px;border-radius:16px;position:relative;overflow:hidden;border:1px solid var(--line);background:
  radial-gradient(circle at 50% 52%, rgba(245,69,92,.18), rgba(245,69,92,0) 58%),
  linear-gradient(135deg,#EAEEF3,#DDE3EB)}
.map .ring{position:absolute;left:50%;top:52%;width:118px;height:118px;border-radius:50%;
  border:2px solid rgba(245,69,92,.5);background:rgba(245,69,92,.10);transform:translate(-50%,-50%)}
.map .pin{position:absolute;left:50%;top:52%;transform:translate(-50%,-100%);color:var(--accent)}
input[type=range]{-webkit-appearance:none;width:100%;height:6px;border-radius:4px;background:var(--track);outline:none;margin-top:6px}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:24px;height:24px;border-radius:50%;
  background:var(--accent);border:3px solid #fff;box-shadow:0 1px 5px #0004;cursor:pointer}

/* primary action button inside the thread + composer */
.cta{width:100%;height:52px;border:0;border-radius:26px;background:var(--accent);color:#fff;
  font:700 16px inherit;cursor:pointer;margin-top:12px;transition:.12s}
.cta:active{transform:translateY(1px)}
.cta:disabled{background:#E9EAEE;color:#9DA2AC;cursor:default}
.cta.ghost{background:var(--field);color:var(--ink)}
.composer{flex:none;display:flex;align-items:center;gap:9px;padding:8px 12px calc(10px + env(safe-area-inset-bottom));
  background:var(--bg);border-top:1px solid var(--line)}
.cadd{width:40px;height:40px;border-radius:50%;background:#fff;border:1.5px solid var(--line);color:var(--muted);
  display:flex;align-items:center;justify-content:center;flex:none;cursor:pointer}
.cwrap{flex:1;display:flex;align-items:center;gap:8px;background:#fff;border:1.5px solid var(--line);
  border-radius:22px;padding:0 12px 0 16px;height:44px}
.cwrap.foc{border-color:var(--accent)}
.cwrap input{flex:1;border:0;outline:none;background:none;font:14.5px inherit}
.cwrap .mic{color:var(--muted);display:flex}
.csend{width:44px;height:44px;border-radius:50%;background:var(--accent);color:#fff;border:1.5px solid var(--accent);flex:none;
  display:flex;align-items:center;justify-content:center;cursor:pointer;transition:.15s}
.csend:disabled{background:#fff;color:var(--accent);border-color:var(--line);opacity:.75;cursor:default}

/* splash */
.splash{flex:1;display:flex;flex-direction:column;align-items:center;text-align:center;padding:40px 28px 0;position:relative}
.emu{position:absolute;top:14px;right:14px;z-index:6;background:#fff;border:1px solid var(--line);
  border-radius:999px;padding:7px 13px;font:600 12px inherit;color:var(--muted);cursor:pointer;box-shadow:0 2px 8px #0001}
.emu:active{transform:scale(.97)}
.illus{width:180px;height:180px;border-radius:50%;background:radial-gradient(circle at 38% 34%,#fff,#E7EAEF);
  margin:auto 0 0;box-shadow:inset 0 2px 12px #0000000d}
.s-h{font-size:25px;font-weight:800;line-height:1.18;margin-top:34px;letter-spacing:-.02em}
.s-sub{color:var(--muted);font-size:14px;margin-top:10px;max-width:300px;line-height:1.5}
.dots{display:flex;gap:7px;margin:20px 0 auto}
.dots i{width:22px;height:5px;border-radius:3px;background:#D6D8DD}.dots i.on{background:var(--ink);width:28px}
.wave{position:relative;width:100%;height:160px;margin-top:auto;transform:translateY(44px)}
.wave svg{position:absolute;bottom:0;left:0;display:block;width:100%;height:160px}
.wave .btnwrap{position:absolute;left:0;right:0;bottom:54px;display:flex;justify-content:center}
.dark{height:48px;padding:0 28px;border:0;border-radius:0;background:transparent;
  color:#fff;font:700 18px inherit;cursor:pointer;letter-spacing:.01em}

/* summary + done */
.scroll{flex:1;overflow-y:auto;padding:4px 16px 14px}
.scroll::-webkit-scrollbar{width:0}
.srow{display:flex;align-items:center;gap:13px;padding:14px 2px;border-bottom:1px solid var(--line)}
.sic{width:38px;height:38px;border-radius:11px;background:var(--field);color:var(--ink);display:flex;
  align-items:center;justify-content:center;flex:none}
.sst{flex:1;min-width:0}.sstn{font-weight:700;font-size:14.5px}.sstv{font-size:12.5px;color:var(--muted);margin-top:1px}
.sedit{color:var(--accent);font-weight:600;font-size:13px;cursor:pointer;flex:none}
.sumc{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;margin:6px 0 12px;box-shadow:0 8px 24px #0000000a}
.sumlbl{color:#BC1F38;font-size:13px;font-weight:700;margin-bottom:7px}
.sumtxt{font-size:14px;line-height:1.55;white-space:pre-wrap}
.sumtxt textarea{width:100%;min-height:130px;border:1.5px solid var(--line);border-radius:10px;padding:10px;font:13.5px/1.5 inherit;color:var(--ink);outline:none;resize:vertical}
.sumtxt textarea:focus{border-color:var(--accent)}
.sumedit{color:var(--accent);font-weight:600;font-size:13px;cursor:pointer;margin-top:10px}
/* summary overview: identity + confidence + card rows (Figma "My Kleal Profile" style) */
.idcard{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;margin:6px 0 12px;box-shadow:0 8px 24px #0000000a}
.idrow{display:flex;align-items:center;gap:12px}
.idava{width:46px;height:46px;border-radius:50%;flex:none;display:flex;align-items:center;justify-content:center;
  background:linear-gradient(135deg,#FF7A8A,#F5455C);color:#fff;font-weight:800;font-size:18px}
.idt{flex:1;min-width:0}
.idn{font-weight:800;font-size:18px;letter-spacing:-.01em;display:flex;align-items:center;gap:8px}
.statusdot{width:9px;height:9px;border-radius:50%;background:var(--accent);display:inline-block;flex:none}
.idsub{font-size:12.5px;color:var(--muted);margin-top:2px;text-transform:capitalize}
.confrow{display:flex;justify-content:space-between;align-items:center;margin-top:15px;font-size:12.5px;color:var(--muted)}
.confrow .cp{font-weight:700;color:var(--ink)}
.ctrack{height:6px;border-radius:4px;background:var(--field);overflow:hidden;margin-top:7px}
.ctrack>i{display:block;height:100%;background:var(--accent);border-radius:4px;transition:width .4s}
.orows{display:flex;flex-direction:column;gap:10px;padding-bottom:6px}
.orow{display:flex;align-items:center;gap:12px;background:var(--card);border:1px solid var(--line);
  border-radius:16px;padding:13px 14px;cursor:pointer;transition:border-color .15s}
.orow:active{border-color:var(--accent)}
.orow .oic2{width:40px;height:40px;border-radius:999px;border:1px solid var(--line);color:var(--ink);
  display:flex;align-items:center;justify-content:center;flex:none}
.orow .ot2{flex:1;min-width:0}
.orow .otn2{font-weight:700;font-size:15px}
.orow .otv2{font-size:12.5px;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.orow .orowedit{display:flex;align-items:center;gap:14px;color:var(--accent);flex:none}
.orow .orowedit svg{width:20px;height:20px;display:block}
.orow .orowedit .rspark{color:var(--accent);display:flex}
.shim{color:var(--muted);animation:shm 1.1s ease-in-out infinite}
@keyframes shm{0%,100%{opacity:.45}50%{opacity:1}}
.menucard{display:flex;align-items:center;gap:14px;background:#fff;border:1px solid var(--line);border-radius:16px;
  padding:16px;margin-top:12px;cursor:pointer;box-shadow:0 8px 24px #0000000a}
.menucard.soon{opacity:.55;cursor:default;box-shadow:none}
.menucard .mic{width:44px;height:44px;border-radius:12px;background:var(--accent-soft);color:var(--accent);
  display:flex;align-items:center;justify-content:center;flex:none}
.menucard .mt{flex:1;min-width:0}.menucard .mtn{font-weight:700;font-size:16px}
.menucard .mts{font-size:12.5px;color:var(--muted);margin-top:2px}
.menucard .mchev{color:var(--muted);flex:none}
.done{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:28px}
.donedisc{width:160px;height:160px;border-radius:50%;background:var(--accent);color:#fff;display:flex;
  align-items:center;justify-content:center;margin-bottom:28px}
.d-h{font-size:26px;font-weight:800;line-height:1.2;letter-spacing:-.02em}
.d-sub{color:var(--muted);font-size:14px;margin-top:12px;max-width:280px;line-height:1.5}
.foot{flex:none;padding:14px 18px calc(16px + env(safe-area-inset-bottom))}
.link{background:none;border:0;color:var(--muted);font:inherit;font-size:13px;cursor:pointer;
  width:100%;text-align:center;padding:10px}
.fade{animation:fd .34s cubic-bezier(.16,1,.3,1)}
@keyframes fd{from{opacity:0;transform:translateY(7px)}to{opacity:1;transform:none}}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
/* ---- Auth (sign in / sign up) ---- */
.authwrap,.authform,.authdone{flex:1;display:flex;flex-direction:column;min-height:0;
  padding:24px 22px calc(20px + env(safe-area-inset-bottom))}
.authtop{margin-top:36px}
.authmark{font-size:30px;font-weight:800;color:var(--accent);letter-spacing:-.02em;margin-bottom:26px}
.auth-h{font-size:26px;font-weight:800;letter-spacing:-.02em}
.auth-sub{font-size:14.5px;color:var(--muted);margin-top:8px;line-height:1.5}
.authbtns{display:flex;flex-direction:column;gap:12px;margin-top:auto;margin-bottom:18px}
.authbtn{display:flex;align-items:center;justify-content:center;gap:10px;height:54px;border-radius:27px;
  font:inherit;font-size:15.5px;font-weight:700;cursor:pointer;border:1.5px solid transparent}
.authbtn.dark{background:#181B22;color:#fff}
.authbtn.white{background:#fff;color:var(--ink);border-color:var(--line)}
.authbtn.coral{background:var(--accent);color:#fff}
.authterms{font-size:11.5px;color:var(--muted);text-align:center;line-height:1.5}
.authterms b{color:var(--ink);font-weight:600}
.authterms.center{margin-top:12px}
.authback{width:40px;height:40px;border-radius:50%;border:1px solid var(--line);background:#fff;display:flex;
  align-items:center;justify-content:center;color:var(--ink);cursor:pointer;margin-bottom:22px}
.auth-h2{font-size:24px;font-weight:800;letter-spacing:-.02em}
.auth-sub2{font-size:14px;color:var(--muted);margin-top:8px;line-height:1.5}
.fieldlbl{font-size:13px;font-weight:600;color:var(--ink);margin:22px 0 8px}
.afield{width:100%;height:52px;border-radius:14px;border:1px solid var(--line);background:var(--field);
  padding:0 16px;font:inherit;font-size:15px;color:var(--ink);outline:0}
.afield:focus{border-color:var(--accent);background:#fff}
.authspace{flex:1}
.authfoot{flex:none}
.linkbtn{display:block;width:100%;text-align:center;background:none;border:0;font:inherit;font-size:14px;
  font-weight:700;color:var(--ink);cursor:pointer;padding:16px 0 4px}
.codebox{display:flex;gap:9px;margin-top:26px}
.cell{flex:1;height:56px;border-radius:14px;border:1.5px solid var(--line);background:var(--field);
  text-align:center;font-size:22px;font-weight:700;color:var(--ink);outline:0;min-width:0}
.cell:focus{border-color:var(--accent);background:#fff}
.resend{font-size:12.5px;color:var(--muted);text-align:center;margin-top:16px}
.resend.active{color:var(--accent);font-weight:600;cursor:pointer}
.authdone{align-items:center;text-align:center}
.doneicon{width:150px;height:150px;border-radius:50%;background:var(--field);display:flex;align-items:center;
  justify-content:center;margin-top:auto}
.authdone .auth-sub{margin-bottom:auto;max-width:290px}
.authdone .authfoot{width:100%}
</style></head><body>
<div class="phone">
  <div id="app"></div>
</div>
<input type="file" id="filein" accept="image/*" style="display:none">
<script>
const A=document.getElementById('app');
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const RM=matchMedia('(prefers-reduced-motion:reduce)').matches;  // honor reduced motion (skip typing delay)
const MASCOT_SRC=""; // drop in the real Kleal mascot image URL/dataURL here later

// ---- icon set (consistent stroke 1.75, currentColor; stands in for a real icon library) ----
function svg(inner,vb){return '<svg viewBox="'+(vb||'0 0 24 24')+'" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" width="22" height="22">'+inner+'</svg>';}
const IC={
  send:'<svg viewBox="0 0 24 24" fill="currentColor" width="20" height="20"><path d="M3.3 20.4l17.5-7.5a1 1 0 000-1.84L3.3 3.6a.5.5 0 00-.7.6L4.6 11 14 12 4.6 13 2.6 19.8a.5.5 0 00.7.6z"/></svg>',
  mic:svg('<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0014 0M12 18v3"/>'),
  plus:svg('<path d="M12 5v14M5 12h14"/>'),
  check:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" width="13" height="13"><path d="M5 12.5l4.5 4.5L19 7"/></svg>',
  camera:svg('<path d="M3 9a2 2 0 012-2h1.5L8 5h8l1.5 2H19a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"/><circle cx="12" cy="13" r="3.3"/>'),
  edit:svg('<path d="M4 20h4L18.5 9.5a2 2 0 00-2.83-2.83L5 17z"/><path d="M14 7l3 3"/>'),
  pin:svg('<path d="M12 21s7-6.2 7-11a7 7 0 10-14 0c0 4.8 7 11 7 11z"/><circle cx="12" cy="10" r="2.6"/>'),
  globe:svg('<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>'),
  spark:svg('<path d="M12 3l1.9 5.6L19.5 10l-5.6 1.9L12 17l-1.9-5.1L4.5 10l5.6-1.4L12 3z"/>'),
  cal:svg('<rect x="4" y="5" width="16" height="16" rx="2.5"/><path d="M4 9.5h16M8 3v4M16 3v4"/>'),
  info:svg('<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.6h.01"/>'),
  lock:svg('<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 018 0v3"/>'),
  star:svg('<path d="M12 4l2.4 4.9 5.4.8-3.9 3.8.9 5.4-4.8-2.5-4.8 2.5.9-5.4L4.2 9.7l5.4-.8L12 4z"/>'),
  user:svg('<circle cx="12" cy="8" r="3.5"/><path d="M5.5 20a6.5 6.5 0 0113 0"/>'),
  users:svg('<circle cx="9" cy="8.5" r="3"/><path d="M3.5 19a5.5 5.5 0 0111 0"/><path d="M16 6.2a3 3 0 010 5.6M20.5 19a5.5 5.5 0 00-3.5-5.1"/>'),
  monitor:svg('<rect x="3" y="4.5" width="18" height="12" rx="2"/><path d="M9 20h6M12 16.5V20"/>'),
  chat:svg('<path d="M4 6a2 2 0 012-2h12a2 2 0 012 2v8a2 2 0 01-2 2H9l-4 4v-4a2 2 0 01-1-1.7V6z"/>'),
  events:svg('<path d="M5 10l13-4M5 10l2.2 9.3 9.4-2.4M5 10l3 7.3"/><circle cx="18.2" cy="6" r="1.6"/>'),
  leaf:svg('<path d="M5 19c0-8 6-13 14-14C18.5 13.5 13 19 6 19H5z"/><path d="M5.5 18.5c3-4.5 6.5-7 10-8.5"/>'),
  columns:svg('<path d="M4 9l8-5 8 5M5 9.5V18M19 9.5V18M9.5 9.5V18M14.5 9.5V18M3.5 20.5h17"/>'),
  badge:svg('<path d="M12 3l2.3 1.7 2.8-.2.9 2.7 2.4 1.5-.7 2.8.7 2.8-2.4 1.5-.9 2.7-2.8-.2L12 21l-2.3-1.7-2.8.2-.9-2.7-2.4-1.5.7-2.8L3.6 9.4 6 7.9l.9-2.7 2.8.2L12 3z"/><path d="M9.2 12l2 2 3.6-3.8"/>'),
  search:svg('<circle cx="11" cy="11" r="6.5"/><path d="M20.5 20.5L16 16"/>'),
  link:svg('<path d="M10 13.5a3.5 3.5 0 005 0l2.5-2.5a3.5 3.5 0 00-5-5l-1 1"/><path d="M14 10.5a3.5 3.5 0 00-5 0L6.5 13a3.5 3.5 0 005 5l1-1"/>'),
  back:svg('<path d="M15 6l-6 6 6 6"/>'),
  sig:'<svg viewBox="0 0 20 14" fill="currentColor" width="18" height="13"><rect x="0" y="9" width="3" height="5" rx="1"/><rect x="5.3" y="6" width="3" height="8" rx="1"/><rect x="10.6" y="3" width="3" height="11" rx="1"/><rect x="15.9" y="0" width="3" height="14" rx="1"/></svg>',
  wifi:'<svg viewBox="0 0 20 15" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" width="18" height="14"><path d="M2 5.2a13 13 0 0116 0M5 8.6a8 8 0 0110 0M8 12a3 3 0 014 0"/></svg>',
  batt:'<svg viewBox="0 0 28 14" fill="none" width="25" height="13"><rect x="1" y="1.4" width="22" height="11.2" rx="3" stroke="currentColor" stroke-opacity=".5"/><rect x="2.8" y="3.1" width="16.5" height="7.8" rx="1.6" fill="currentColor"/><rect x="24.3" y="4.6" width="2.3" height="4.8" rx="1.1" fill="currentColor" fill-opacity=".5"/></svg>'
};

// ---- state ----
const st={ phase:'splash', slide:0, profile:{}, crit:null, thread:[], step:-1,
           busy:false, compose:null, funnel:[], fcEl:null, funnelTurns:0, funnelCap:0,
           editing:false, sumEdited:false };
function set(path,val){ const ks=path.split('.'); let o=st.profile; for(let i=0;i<ks.length-1;i++){o=o[ks[i]]=o[ks[i]]||{};} o[ks[ks.length-1]]=val; }
function clock(){ const d=new Date(); let h=d.getHours(); const m=d.getMinutes(); const ap=h>=12?'PM':'AM'; h=h%12||12; return h+':'+(m<10?'0':'')+m+' '+ap; }
function profileForServer(){ const c=Object.assign({},st.profile); delete c.photo; return c; }
async function refreshCrit(){
  try{ st.crit=await fetch('/api/v2/state',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({profile:profileForServer()})}).then(r=>r.json()); }catch(e){}
  updateHeader();
}
function updateHeader(){ const b=document.querySelector('.pbar>i'),p=document.querySelector('.pct');
  const pct=st.crit?st.crit.pct:0; if(b)b.style.width=pct+'%'; if(p)p.textContent=pct+'%'; }
function refreshSendState(){ const cin=document.getElementById('cin'),cs=document.getElementById('csend');
  if(cin&&cs) cs.disabled=!(cin.value.trim()&&st.compose)||st.busy; }

// ======================= SPLASH =======================
const SLIDES=[
 {t:"Tell Kleal what you<br>want to do", s:"Coffee, a match, a game, a walk, language practice, or just something spontaneous."},
 {t:"Find people for the plan,<br>not profiles to scroll", s:"Kleal looks for the right people, rooms, groups or events from your mood, time, place and interests."},
 {t:"Less social admin.<br>More real plans", s:"Kleal finds who is interested, checks the fit, and brings you options. You confirm every step."},
];
function rSplash(){
  const sl=SLIDES[st.slide], last=st.slide===SLIDES.length-1;
  A.innerHTML=`<div class="splash fade">
    <button class="emu" id="emu">Emulate onboarding</button>
    <div class="illus"></div>
    <div class="s-h">${sl.t}</div><div class="s-sub">${esc(sl.s)}</div>
    <div class="dots">${SLIDES.map((_,i)=>`<i class="${i===st.slide?'on':''}"></i>`).join('')}</div>
    <div class="wave" id="go" style="cursor:pointer"><svg viewBox="0 0 390 160" preserveAspectRatio="none" height="160">
      <path d="M0 132 C 78 132 120 20 195 20 C 270 20 312 132 390 132 L390 160 L0 160 Z" fill="#181B22"/></svg>
      <div class="btnwrap"><button class="dark" tabindex="-1">Let's Start</button></div></div>
  </div>`;
  document.getElementById('go').onclick=()=>{ if(!last){st.slide++;rSplash();} else startAuth(); };
  document.getElementById('emu').onclick=emulate;
}

// ======================= AUTH (sign in / sign up) =======================
const AUTH_TERMS='By continuing you agree to our <b>Terms</b> and <b>Privacy Policy</b>.';
const IC_GOOGLE='<svg width="19" height="19" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.6l6.8-6.8C35.6 2.4 30.1 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.9 6.1C12.4 13.2 17.7 9.5 24 9.5z"/><path fill="#4285F4" d="M46.1 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.4c-.5 2.9-2.1 5.3-4.6 7l7.1 5.5c4.1-3.8 6.5-9.4 6.5-16z"/><path fill="#FBBC05" d="M10.5 28.3c-.5-1.4-.8-2.9-.8-4.3s.3-3 .8-4.3l-7.9-6.1C.9 16.9 0 20.3 0 24s.9 7.1 2.6 10.4l7.9-6.1z"/><path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.1-5.5c-2 1.3-4.5 2.1-8.8 2.1-6.3 0-11.6-3.7-13.5-9.1l-7.9 6.1C6.5 42.6 14.6 48 24 48z"/></svg>';
const IC_APPLE='<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M16.4 1.5c.1.9-.3 1.9-.9 2.6-.7.8-1.8 1.4-2.8 1.3-.1-.9.4-1.9 1-2.6.7-.8 1.8-1.3 2.7-1.3zM19.2 17.3c-.5 1.1-.7 1.6-1.4 2.6-.9 1.4-2.2 3.1-3.8 3.1-1.4 0-1.8-.9-3.7-.9s-2.3.9-3.7.9c-1.6 0-2.8-1.5-3.7-2.9C-.1 16.4-.4 11.2 2.2 8.5c1-1.1 2.5-1.8 3.9-1.8 1.6 0 2.6.9 3.9.9 1.2 0 2-.9 3.9-.9 1.3 0 2.7.7 3.7 1.9-3.3 1.8-2.7 6.4.9 8z"/></svg>';
const IC_MAIL='<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2.5"/><path d="M4 7.5l8 5.5 8-5.5"/></svg>';
const IC_CHEV='<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 6l-6 6 6 6"/></svg>';

function startAuth(){ rAuth(); }
function rAuth(){ st.phase='auth';
  A.innerHTML=`<div class="authwrap fade">
    <div class="authtop"><div class="authmark">kleal</div>
      <div class="auth-h">Meet your people</div>
      <div class="auth-sub">Sign in or create your account to get started.</div></div>
    <div class="authbtns">
      <button class="authbtn dark" data-auth="apple">${IC_APPLE}<span>Continue with Apple</span></button>
      <button class="authbtn white" data-auth="google">${IC_GOOGLE}<span>Continue with Google</span></button>
      <button class="authbtn coral" data-auth="email">${IC_MAIL}<span>Continue with email</span></button>
    </div>
    <div class="authterms">${AUTH_TERMS}</div>
  </div>`;
  A.querySelectorAll('[data-auth]').forEach(b=>b.onclick=()=>{ const m=b.dataset.auth;
    if(m==='email'){ rAuthEmail(); } else { st.profile.authMethod=m; rAuthDone(); } });
}
function rAuthEmail(){ st.phase='auth';
  A.innerHTML=`<div class="authform fade">
    <button class="authback" id="ab">${IC_CHEV}</button>
    <div class="auth-h2">What's your email?</div>
    <div class="auth-sub2">We'll send you a code to sign in or create your account if you're new.</div>
    <div class="fieldlbl">Email</div>
    <input class="afield" id="aemail" type="email" inputmode="email" autocapitalize="off" autocomplete="email" placeholder="you@email.com" value="${esc(st.profile.email||'')}">
    <div class="authspace"></div>
    <div class="authfoot"><button class="cta" id="acont" disabled>Continue</button>
      <div class="authterms center">${AUTH_TERMS}</div></div>
  </div>`;
  const em=document.getElementById('aemail'), c=document.getElementById('acont');
  const ok=v=>/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v);
  const upd=()=>{ c.disabled=!ok(em.value.trim()); }; em.oninput=upd; upd(); setTimeout(()=>em.focus(),60);
  c.onclick=()=>{ st.profile.email=em.value.trim(); rAuthCode(); };
  document.getElementById('ab').onclick=()=>rAuth();
}
function rAuthCode(){ st.phase='auth';
  const email=st.profile.email||'you@email.com';
  A.innerHTML=`<div class="authform fade">
    <button class="authback" id="ab">${IC_CHEV}</button>
    <div class="auth-h2">Enter the code</div>
    <div class="auth-sub2">We sent a 6-digit code to ${esc(email)}. It expires in 10 minutes.</div>
    <div class="codebox">${[0,1,2,3,4,5].map(i=>`<input class="cell" maxlength="1" inputmode="numeric" data-i="${i}">`).join('')}</div>
    <div class="resend" id="resend">Resend code in 0:30</div>
    <div class="authspace"></div>
    <div class="authfoot"><button class="cta" id="averify" disabled>Verify</button>
      <button class="linkbtn" id="diff">Use a different email</button></div>
  </div>`;
  const cells=[...A.querySelectorAll('.cell')], v=document.getElementById('averify');
  const upd=()=>{ v.disabled=cells.some(x=>!x.value.trim()); };
  cells.forEach((c,i)=>{
    c.oninput=()=>{ c.value=c.value.replace(/\D/g,'').slice(0,1); if(c.value&&i<5)cells[i+1].focus(); upd(); };
    c.onkeydown=(e)=>{ if(e.key==='Backspace'&&!c.value&&i>0)cells[i-1].focus(); };
    c.onpaste=(e)=>{ const d=((e.clipboardData||window.clipboardData).getData('text')||'').replace(/\D/g,'').slice(0,6);
      if(d){ e.preventDefault(); d.split('').forEach((ch,j)=>{if(cells[j])cells[j].value=ch;}); cells[Math.min(d.length,6)-1].focus(); upd(); } };
  });
  setTimeout(()=>cells[0].focus(),60);
  let t=30, iv; const rl=document.getElementById('resend');
  const tick=()=>{ if(t<=0){ clearInterval(iv); rl.textContent='Resend code'; rl.classList.add('active');
      rl.onclick=()=>{ rl.classList.remove('active'); rl.onclick=null; t=30; loop(); }; return; }
    rl.textContent='Resend code in 0:'+(t<10?'0':'')+t; t--; };
  const loop=()=>{ clearInterval(iv); tick(); iv=setInterval(()=>{ if(st.phase!=='auth'||!document.getElementById('resend')){clearInterval(iv);return;} tick(); },1000); };
  loop();
  v.onclick=()=>{ clearInterval(iv); rAuthDone(); };
  document.getElementById('diff').onclick=()=>{ clearInterval(iv); rAuthEmail(); };
  document.getElementById('ab').onclick=()=>{ clearInterval(iv); rAuthEmail(); };
}
function rAuthDone(){ st.phase='auth';
  A.innerHTML=`<div class="authdone fade">
    <div class="doneicon"><svg width="38" height="38" viewBox="0 0 24 24" fill="none" stroke="#9aa0ac" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="2"/><path d="M3 16.5l5-4 4 3 3-2 6 5"/></svg></div>
    <div class="auth-h" style="margin-top:24px">You're in</div>
    <div class="auth-sub">Let's build your profile so Kleal can find your people and your plans.</div>
    <div class="authfoot"><button class="cta" id="setup">Set up profile</button></div>
  </div>`;
  document.getElementById('setup').onclick=()=>startChat();
}

// dev shortcut: fill a realistic finished profile and jump straight to the filled Kleal profile card
function emulate(){
  st.profile={
    name:"Ben", age:27, ageVerified18:true, gender:"Male",
    languages:{comfortable:["English","Spanish"]},
    city:"Barcelona", geo:{comfortableAreas:["Barcelona"], maxDistanceKm:15, located:true},
    interests:{ explicit:["AI","Dota 2","Coffee"],
      roles:{"AI":"practice","Dota 2":"play","Coffee":"discuss"},
      experienceByInterest:{"AI":"3 years","Dota 2":"5 years","Coffee":"a while"} },
    domains:{ games:{ gamesList:["Dota 2"], platformsByGame:{"Dota 2":"PC"}, rankByGame:{"Dota 2":"Ancient"},
      competitiveMode:"ranked", toxicityPreference:"low_toxicity" } },
    safety:{ publicPlacesOnly:true },
    permissions:{ useProfileForMatching:true, allowAdjacentMatches:true },
    // Social Style + Goals aren't collected by onboarding yet; the emulate shortcut fills them so the
    // whole profile card is inspectable in one click.
    vibe:{ primary:"calm" },
    social:{
      rows:[
        {icon:"spark", title:"Energy",             value:"Calm / medium"},
        {icon:"chat",  title:"Conversation depth", value:"Deep topics + casual warmth"},
        {icon:"coffee",title:"Best first format",  value:"Low-pressure coffee or walk"},
        {icon:"users", title:"Group comfort",      value:"1:1 or small group up to 4"},
        {icon:"pin",   title:"Places",             value:"Quiet cafes, walks, public spaces"},
        {icon:"ban",   title:"Avoid",              value:"Loud bars, big random groups"} ],
      vibe:[["calm",true],["friendly",true],["intellectual",true],["playful",false],["energetic",false],["cozy",true],["focused",false]],
      depth:[["light casual",false],["medium",true],["deep talk",true],["topic-based",true]] },
    goals:{ active:["Meet new people in Barcelona","Coffee / walks / dinners","Practice Spanish","Gaming teammates","AI / startup conversations"],
      optional:["Networking","Dating mode off","Regular groups"] },
    summary:"You're Ben, a 27-year-old in Barcelona, comfortable in English and Spanish and open to plans within 15 km of the city. You're into AI, which you've been practicing for about 3 years, and you play Dota 2 - 5 years in, on PC, at Ancient rank. You also like meeting over coffee. You prefer low-pressure meetups in public places, and you've allowed Kleal to use your profile for matching and adjacent suggestions."
  };
  openProfile();
}

// ======================= CHAT THREAD =======================
const SCRIPT=[
  {id:'greet', bot:["Hey! I'm Kleal, your personal agent for real-life plans 👋","Tell me a bit about yourself and I'll start finding the right people and plans around you: coffee, football, a game night, language practice. No feeds, no swiping.","It takes about two minutes. Let's get you set up!"]},
  {id:'ready', bot:["Ready to fill in a few details about yourself?"], widget:'ready'},
  {id:'basics', bot:["First, a few basics about you."], widget:'basics'},
  {id:'location', bot:["Where are you mostly based?"], widget:'location'},
  {id:'language', bot:["Great. What languages are you comfortable in?"], widget:'language'},
  {id:'interests', bot:["What are you into?"], hint:"Pick some or write your own", widget:'interests'},
  {id:'safety', bot:["Your safety matters. You're in control."], hint:"You can pick multiple", widget:'safety'},
];
function startChat(){ st.phase='chat'; st.thread=[]; st.step=-1; st.editing=false; renderChrome(); nextStep(); }
function renderChrome(){
  A.innerHTML=`<div class="head"><div class="ava" id="ava">${MASCOT_SRC?'':'K'}</div>
    <div class="ht"><div class="htt">Creating Profile</div>
      <div class="prow"><div class="pbar"><i></i></div><div class="pct">0%</div></div></div></div>
    <div class="thread" id="thread"></div>
    <div class="composer"><button class="cadd">${IC.plus}</button>
      <div class="cwrap" id="cwrap"><input id="cin" placeholder="Message..."><span class="mic">${IC.mic}</span></div>
      <button class="csend" id="csend" disabled>${IC.send}</button></div>`;
  if(MASCOT_SRC){ document.getElementById('ava').style.backgroundImage=`url(${MASCOT_SRC})`; document.getElementById('ava').textContent=''; }
  updateHeader();
  const cin=document.getElementById('cin'), csend=document.getElementById('csend'), cwrap=document.getElementById('cwrap');
  cin.onfocus=()=>cwrap.classList.add('foc'); cin.onblur=()=>cwrap.classList.remove('foc');
  cin.oninput=refreshSendState;
  function sendC(){ if(st.busy||!st.compose)return; const v=cin.value.trim(); if(!v)return; const fn=st.compose; cin.value=''; refreshSendState(); fn(v); }
  csend.onclick=sendC; cin.onkeydown=e=>{ if(e.key==='Enter')sendC(); };
}
function setCompose(fn,ph){ st.compose=fn; const cin=document.getElementById('cin'); if(cin){ cin.placeholder=ph||'Message...'; } refreshSendState(); }
function thread(){ return document.getElementById('thread'); }
function scrollDown(){ const t=thread(); if(t)requestAnimationFrame(()=>{ t.scrollTop=t.scrollHeight+600; }); }

function elBubble(kind,text,withTime){
  const row=document.createElement('div'); row.className='row fade';
  const b=document.createElement('div'); b.className='bub '+kind; b.textContent=text; row.appendChild(b);
  if(withTime){ const tm=document.createElement('div'); tm.className='time '+(kind==='me'?'me':''); tm.textContent=clock(); row.appendChild(tm); }
  thread().appendChild(row); scrollDown(); return row;
}
function botSay(lines,cb){
  st.busy=true; refreshSendState(); const t=thread();
  const typ=document.createElement('div'); typ.className='typing fade'; typ.innerHTML='<i></i><i></i><i></i>';
  t.appendChild(typ); scrollDown();
  setTimeout(()=>{ typ.remove(); lines.forEach((ln,i)=>elBubble('bot',ln, i===lines.length-1)); st.busy=false; refreshSendState();
    if(cb){ try{ cb(); }catch(e){ console.error(e); st.busy=false; refreshSendState(); } } }, RM?0:620);
}
function meSay(text){ elBubble('me',text,true); }
function addHint(text){ const h=document.createElement('div'); h.className='hint fade'; h.textContent=text; thread().appendChild(h); scrollDown(); }
function widgetSlot(){ const w=document.createElement('div'); w.className='w fade'; thread().appendChild(w); scrollDown(); return w; }

function nextStep(){
  st.step++;
  if(st.step>=SCRIPT.length){ return finishChat(); }
  const s=SCRIPT[st.step];
  setCompose(null);
  botSay(s.bot, ()=>{
    if(s.hint) addHint(s.hint);
    if(s.widget){ try{ WIDGETS[s.widget](widgetSlot()); }catch(e){ console.error(e); elBubble('bot',"Something glitched there. Tap Restart to try again.",false); } }
    else { nextStep(); }   // pure-message step (greeting) -> roll on
  });
}
function afterAnswer(){ refreshCrit().then(()=>{ if(st.editing){ st.editing=false; return goSummary(); } nextStep(); }).catch(()=>nextStep()); }

// once a step is answered the inline widget collapses away (the answer is now a bubble); this
// also prevents duplicate element ids from piling up in the persistent thread.
function lock(slot){ slot.remove(); }

// ======================= INLINE WIDGETS =======================
const WIDGETS={};

// consent-style gate before the basics form: nothing is asked until the user says they're ready
WIDGETS.ready=function(slot){
  slot.innerHTML=`<div class="chips"><div class="chip on" id="rdy">I'm ready</div><div class="chip" id="why">Why do you need this?</div></div>`;
  slot.querySelector('#rdy').onclick=()=>{ if(st.busy)return; lock(slot); meSay("I'm ready"); afterAnswer(); };
  slot.querySelector('#why').onclick=()=>{ if(st.busy)return; lock(slot); meSay("Why do you need this?");
    botSay(["Fair question. Your basics help me introduce you to the right people, and you stay in control: every detail can be edited, hidden from matching or removed later.","Ready when you are."],
      ()=>{ const w=widgetSlot(); w.innerHTML=`<div class="chips"><div class="chip on" id="rdy2">I'm ready</div></div>`;
            w.querySelector('#rdy2').onclick=()=>{ if(st.busy)return; lock(w); meSay("I'm ready"); afterAnswer(); }; });
  };
};

WIDGETS.basics=function(slot){
  const p=st.profile;
  slot.innerHTML=`<div class="card">
    <div class="photo" id="photo">${p.photo?'':'<span class="ph">'+IC.camera+'</span>'}<span class="cam">${IC.plus}</span></div>
    <div class="cap">Add a profile photo</div>
    <div class="lbl">How should I call you?</div>
    <input class="inp" id="f_name" placeholder="Your name" value="${esc(p.name||'')}">
    <div class="lbl">Your age</div>
    <input class="inp" id="f_age" type="number" inputmode="numeric" min="18" placeholder="18+" value="${p.age||''}">
    <div class="warn" id="agewarn">You need to be 18 or older.</div>
    <div class="lbl">Gender</div>
    <div class="grid3" id="f_gender">${['Male','Female','Other'].map(g=>`<div class="chip ${p.gender===g?'on':''}" data-g="${g}">${g}</div>`).join('')}</div>
    </div><button class="cta" id="cont" disabled>Continue</button>`;
  const photo=slot.querySelector('#photo'); if(p.photo)photo.style.backgroundImage=`url(${p.photo})`;
  photo.onclick=()=>pickPhoto(()=>WIDGETS.basics(slot));
  const name=slot.querySelector('#f_name'), age=slot.querySelector('#f_age'), cont=slot.querySelector('#cont');
  slot.querySelectorAll('#f_gender .chip').forEach(c=>c.onclick=()=>{ slot.querySelectorAll('#f_gender .chip').forEach(x=>x.classList.remove('on')); c.classList.add('on'); set('gender',c.dataset.g); val(); });
  function val(){ const a=parseInt(age.value,10); const okA=a>=18&&a<=120; slot.querySelector('#agewarn').style.display=(age.value&&!okA)?'block':'none'; cont.disabled=!(name.value.trim()&&okA&&p.gender); }
  name.oninput=()=>{ set('name',name.value.trim()); val(); };
  age.oninput=()=>{ const a=parseInt(age.value,10); if(a>=18){set('age',a);set('ageVerified18',true);} else{delete p.age;delete p.ageVerified18;} val(); };
  val();
  cont.onclick=()=>{ lock(slot); const bits=[p.name, p.age?p.age:null, p.gender].filter(Boolean).join(', '); meSay(bits+(p.photo?', photo added':'')); afterAnswer(); };
};
function pickPhoto(cb){ const fi=document.getElementById('filein'); fi.onchange=()=>{ const f=fi.files[0]; if(!f)return;
  const r=new FileReader(); r.onload=()=>{ st.profile.photo=r.result; set('photoStatus','uploaded'); fi.value=''; cb(); };
  r.onerror=()=>{ fi.value=''; }; r.readAsDataURL(f); }; fi.click(); }

WIDGETS.location=function(slot){
  const g=st.profile.geo||{}; const r=(g.maxDistanceKm!=null)?g.maxDistanceKm:10; set('geo.maxDistanceKm',r);
  const area=(g.comfortableAreas&&g.comfortableAreas[0])||st.profile.city||'';
  const hasL=(typeof L!=='undefined');
  const mapHtml = hasL ? '<div class="map" id="lmap"></div>'
                       : '<div class="map"><div class="ring"></div><div class="pin">'+IC.pin+'</div></div>';
  slot.innerHTML=`<div class="card">
    ${mapHtml}
    <div class="lbl" style="margin-top:14px">Your city</div>
    <input class="inp" id="area" placeholder="Detecting your city..." value="${esc(area)}">
    <div class="lbl" style="margin-top:16px">How far are you happy to go? <b id="rkm">${r}</b> km</div>
    <input type="range" id="rad" min="1" max="50" value="${r}">
    <div class="cap" id="gstat" style="text-align:left;margin-top:8px"></div>
    </div><button class="cta" id="cont" ${area?'':'disabled'}>Continue</button>`;
  const rad=slot.querySelector('#rad'), area_in=slot.querySelector('#area'), cont=slot.querySelector('#cont');
  // ---- real map (Leaflet + Carto light tiles). A radius circle marks the AREA; no exact pin, no attribution bar. ----
  let lmap=null, circle=null;
  function fit(){ if(lmap&&circle) lmap.fitBounds(circle.getBounds(),{padding:[16,16]}); }
  function recenter(c){ if(!lmap||!circle)return; circle.setLatLng(c); fit(); }
  if(hasL){
    const center=(g.coarseLat&&g.coarseLon)?[g.coarseLat,g.coarseLon]:[41.3874,2.1686];
    lmap=L.map('lmap',{zoomControl:false,scrollWheelZoom:false,attributionControl:false});
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',{maxZoom:19}).addTo(lmap);
    circle=L.circle(center,{radius:(r||10)*1000,color:'#F5455C',weight:2,fillColor:'#F5455C',fillOpacity:.12}).addTo(lmap);
    lmap.setView(center,12); fit();
    setTimeout(()=>{ if(lmap){ lmap.invalidateSize(); fit(); } }, 80);
  }
  rad.oninput=()=>{ const v=parseInt(rad.value,10); slot.querySelector('#rkm').textContent=v; set('geo.maxDistanceKm',v); if(circle){ circle.setRadius(v*1000); fit(); } };
  function setCity(name){ if(!name)return; area_in.value=name; set('geo.comfortableAreas',[name]); set('city',name); cont.disabled=false; }
  async function geocode(q){ if(!q)return; try{ const j=await fetch('https://nominatim.openstreetmap.org/search?format=json&limit=1&q='+encodeURIComponent(q)).then(x=>x.json()); if(j&&j[0]) recenter([+j[0].lat,+j[0].lon]); }catch(e){} }
  async function reverseCity(la,lo){ try{ const j=await fetch('https://nominatim.openstreetmap.org/reverse?format=json&zoom=10&lat='+la+'&lon='+lo).then(x=>x.json());
    const a=(j&&j.address)||{}; return a.city||a.town||a.village||a.municipality||a.county||a.state||''; }catch(e){ return ''; } }
  area_in.oninput=()=>{ const v=area_in.value.trim(); if(v){set('geo.comfortableAreas',[v]);set('city',v);} cont.disabled=!v; };
  area_in.onchange=()=>geocode(area_in.value.trim());
  if(area) geocode(area);
  // geolocation is requested AUTOMATICALLY when this step opens; the detected CITY name is used (never exact spot)
  function autoLocate(){ const stat=slot.querySelector('#gstat');
    if(!navigator.geolocation){ stat.textContent="Type your city above."; area_in.placeholder="Your city"; return; }
    stat.textContent="Finding your city...";
    navigator.geolocation.getCurrentPosition(async pos=>{ const la=pos.coords.latitude.toFixed(2),lo=pos.coords.longitude.toFixed(2);
      set('geo.located',true); set('geo.coarseLat',Number(la)); set('geo.coarseLon',Number(lo)); recenter([Number(la),Number(lo)]);
      const city=await reverseCity(la,lo);
      if(city){ setCity(city); stat.textContent="Kleal shows your city area only, never your exact spot."; }
      else { area_in.placeholder="Type your city"; stat.textContent="Couldn't name your city. Type it above."; }
    }, err=>{ area_in.placeholder="Your city"; stat.textContent="Location off. Type your city above."; },
      {enableHighAccuracy:false, timeout:10000, maximumAge:600000}); }
  if(!area) setTimeout(autoLocate, 120);
  cont.onclick=()=>{ lock(slot); const km=(st.profile.geo&&st.profile.geo.maxDistanceKm)||rad.value;
    meSay((area_in.value.trim()||'My city')+', within '+km+' km'); afterAnswer(); };
};

const LANGS=['English','Spanish','German','French','Portuguese','Italian','Russian'];
WIDGETS.language=function(slot){
  const cur=(st.profile.languages&&st.profile.languages.comfortable)||[];
  slot.innerHTML=`<div class="chips" id="langs">
    ${LANGS.map(l=>`<div class="chip ${cur.includes(l)?'on':''}" data-l="${l}">${l}</div>`).join('')}
    ${cur.filter(l=>!LANGS.includes(l)).map(l=>`<div class="chip on" data-l="${esc(l)}">${esc(l)}</div>`).join('')}</div>
    <div class="addrow" id="ar"><span class="ai">${IC.plus}</span><input id="lown" placeholder="Add your own"><button class="go" id="ladd">${IC.send}</button></div>
    <button class="cta" id="cont" disabled>Next</button>`;
  const cont=slot.querySelector('#cont');
  function sync(){ const on=[...slot.querySelectorAll('#langs .chip.on')].map(c=>c.dataset.l); set('languages.comfortable',on); cont.disabled=!on.length; }
  slot.querySelectorAll('#langs .chip').forEach(c=>c.onclick=()=>{ c.classList.toggle('on'); sync(); });
  const own=slot.querySelector('#lown'), ar=slot.querySelector('#ar');
  own.onfocus=()=>ar.classList.add('foc'); own.onblur=()=>ar.classList.remove('foc');
  function add(){ const v=own.value.trim(); if(!v)return; const d=document.createElement('div'); d.className='chip on'; d.dataset.l=v; d.textContent=v; d.onclick=()=>{d.remove();sync();}; slot.querySelector('#langs').appendChild(d); own.value=''; sync(); }
  slot.querySelector('#ladd').onclick=add; own.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();add();}};
  sync();
  cont.onclick=()=>{ const on=(st.profile.languages&&st.profile.languages.comfortable)||[]; lock(slot); meSay(on.join(', ')); afterAnswer(); };
};

const QUICK=['Coffee','Walks','Football','AI','Startups','Dota 2','Jazz','Design','Hiking'];
WIDGETS.interests=function(slot){
  const cur=(st.profile.interests&&st.profile.interests.explicit)||[];
  slot.innerHTML=`<div class="chips" id="ints">
    ${QUICK.map(q=>`<div class="chip ${cur.includes(q)?'on':''}" data-q="${esc(q)}">${esc(q)}</div>`).join('')}</div>
    <div class="addrow" id="ar"><span class="ai">${IC.plus}</span><input id="iown" placeholder="Add your own"><button class="go" id="iadd">${IC.send}</button></div>
    <button class="cta" id="cont" disabled>Next</button>`;
  const cont=slot.querySelector('#cont');
  function picks(){ return [...slot.querySelectorAll('#ints .chip.on')].map(c=>c.dataset.q); }
  function sync(){ const on=picks(); set('interests.explicit',on); cont.disabled=!on.length; }
  slot.querySelectorAll('#ints .chip').forEach(c=>c.onclick=()=>{ c.classList.toggle('on'); sync(); });
  const own=slot.querySelector('#iown'), ar=slot.querySelector('#ar');
  own.onfocus=()=>ar.classList.add('foc'); own.onblur=()=>ar.classList.remove('foc');
  function add(){ const v=own.value.trim(); if(!v)return; const d=document.createElement('div'); d.className='chip on'; d.dataset.q=v; d.textContent=v; d.onclick=()=>{d.remove();sync();}; slot.querySelector('#ints').appendChild(d); own.value=''; sync(); }
  slot.querySelector('#iadd').onclick=add; own.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();add();}};
  sync();
  cont.onclick=()=>{ const on=picks(); if(!on.length)return; lock(slot); meSay(on.join(', '));
    const funnelDone=st.crit&&st.crit.done&&st.crit.done.includes('Interests')
      &&!(st.crit.missing||[]).some(m=>/^(Role|Experience):/.test(m));
    if(st.editing&&funnelDone){ afterAnswer(); } else { startFunnel(on); } };
};

// interests free-chat funnel (Llama): draws out roles + domain detail, inline option chips
function startFunnel(picks){
  st.fcEl=null; st.funnelTurns=0;
  st.funnelCap=picks.length*2+4;  // 2 questions per interest + confirm/wiggle room (anti-stuck net)
  st.funnel=[{role:'assistant',content:"Nice picks."},{role:'user',content:"I'm into "+picks.join(', ')}];
  setCompose(funnelCompose, "Tell Kleal more...");
  funnelTurn(null,true);
}
function funnelCompose(t){
  const s=(t||'').trim();
  // if Continue is offered, plain affirmatives advance instead of asking the model again
  if(st.fcEl && /^(let'?s\s+)?(continue|next|done|proceed|go|ready|finish|that'?s it)\b/i.test(s)){ advanceFunnel(); return; }
  funnelTurn(s);
}
function advanceFunnel(){ if(st.busy)return; if(st.fcEl){ st.fcEl.remove(); st.fcEl=null; } setCompose(null); afterAnswer(); }
function funnelOpts(opts){
  if(!opts||!opts.length)return; const w=widgetSlot(); w.className='w fade';
  w.innerHTML='<div class="chips">'+opts.map(o=>`<div class="chip" data-o="${esc(o)}">${esc(o)}</div>`).join('')+'</div>';
  w.querySelectorAll('.chip').forEach(c=>c.onclick=()=>{ if(st.busy)return; const v=c.dataset.o; w.remove(); funnelTurn(v); });
}
// always keep exactly ONE Continue button, re-appended at the bottom under the latest message
function funnelContinue(){ if(st.fcEl)st.fcEl.remove(); const w=widgetSlot(); st.fcEl=w;
  w.innerHTML='<button class="cta" id="fc">Continue</button>';
  w.querySelector('#fc').onclick=()=>advanceFunnel(); }
async function funnelTurn(text, first){
  if(st.busy) return;
  if(text){ st.funnel.push({role:'user',content:text}); st.funnelTurns++; meSay(text); }
  st.busy=true; refreshSendState(); const t=thread();
  const typ=document.createElement('div'); typ.className='typing fade'; typ.innerHTML='<i></i><i></i><i></i>'; t.appendChild(typ); scrollDown();
  try{
    const r=await fetch('/api/v2/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({messages:st.funnel, profile:profileForServer()})}).then(x=>x.json());
    typ.remove();
    st.funnel.push({role:'assistant',content:r.reply});
    elBubble('bot',r.reply,true);
    if(r.profile&&typeof r.profile==='object'){ const ph=st.profile.photo; st.profile=r.profile; if(ph)st.profile.photo=ph; }
    if(r.crit) st.crit=r.crit; updateHeader();
    // a junk / gibberish answer must NOT count toward the anti-stuck net, else spamming nonsense
    // could unlock Continue. Undo this turn's increment so only real answers advance the net.
    if(r.gibberish) st.funnelTurns=Math.max(0, st.funnelTurns-1);
    // Continue ONLY once the agent stops asking: funnel has no gaps AND the bot's reply is a wrap-up (no "?"/options).
    // funnelTurns is an anti-stuck net so the user is never trapped if the model keeps probing.
    const replyAsks=((r.reply||'').indexOf('?')>=0)||(r.options&&r.options.length>0);
    const done=(!!r.funnelComplete && !replyAsks) || st.funnelTurns>=(st.funnelCap||10);
    if(done){ funnelContinue(); }
    else { if(st.fcEl){ st.fcEl.remove(); st.fcEl=null; } if(r.options&&r.options.length) funnelOpts(r.options); }
  }catch(e){ typ.remove(); elBubble('bot',"I lost the connection for a second. Say that again?",true); }
  st.busy=false; refreshSendState();
}

const CONNECT=[
 {k:'oneOnOne', ic:'user', t:'1:1', s:'One-on-one'},
 {k:'smallGroup', ic:'users', t:'Small group', s:'2-5 people'},
 {k:'online', ic:'monitor', t:'Online', s:'Video / voice'},
 {k:'inperson', ic:'pin', t:'Offline', s:'In person'},
 {k:'hybrid', ic:'chat', t:'Hybrid', s:'Both online & offline'},
 {k:'events', ic:'events', t:'Events', s:'Workshops, meetups'},
 {k:'lowpressure', ic:'leaf', t:'Low-pressure', s:'Chill & casual'},
];
function applyConnect(sel){ set('format.connect',sel);
  if(sel.includes('oneOnOne'))set('format.oneOnOne',true); if(sel.includes('smallGroup'))set('format.smallGroup',true);
  const on=sel.includes('online'),off=sel.includes('inperson'),hy=sel.includes('hybrid');
  if(hy||(on&&off))set('format.modePreference','hybrid'); else if(on)set('format.modePreference','online'); else if(off)set('format.modePreference','offline');
  if(sel.includes('lowpressure'))set('vibe.primary','low-pressure'); }
WIDGETS.connect=function(slot){
  const sel=(st.profile.format&&st.profile.format.connect)||[];
  slot.innerHTML=`<div class="opts" id="conn">${CONNECT.map(o=>`
    <div class="opt ${sel.includes(o.k)?'on':''}" data-k="${o.k}"><div class="oic">${IC[o.ic]}</div>
      <div class="ot"><div class="otn">${o.t}</div><div class="ots">${o.s}</div></div>
      <div class="ock">${IC.check}</div></div>`).join('')}</div>
    <button class="cta" id="cont">Next</button>`;
  slot.querySelectorAll('#conn .opt').forEach(o=>o.onclick=()=>{ o.classList.toggle('on');
    applyConnect([...slot.querySelectorAll('#conn .opt.on')].map(x=>x.dataset.k)); });
  slot.querySelector('#cont').onclick=()=>{ const sel=(st.profile.format&&st.profile.format.connect)||[]; lock(slot);
    meSay(sel.length?sel.map(k=>(CONNECT.find(c=>c.k===k)||{}).t||k).join(', '):'No preference'); afterAnswer(); };
};

function togRow(id,icon,t,s,on){ return `<div class="tog ${on?'on':''}" data-t="${id}"><div class="oic">${IC[icon]}</div>
  <div class="ot"><div class="otn">${t}</div><div class="ots">${s}</div></div><div class="sw"><i></i></div></div>`; }
// icon-less settings toggle row (Figma "Toggle Row": title + subtitle + trailing switch)
function togRow2(id,t,s,on){ return `<div class="tog ${on?'on':''}" data-t="${id}"><div class="ot"><div class="otn">${t}</div><div class="ots">${s}</div></div><div class="sw"><i></i></div></div>`; }
WIDGETS.safety=function(slot){
  const p=st.profile;
  // "Meet in public places" is the recommended default (applied); matching consent is implied by completing onboarding.
  if(!(p.safety&&p.safety.publicPlacesOnly!==undefined)) set('safety.publicPlacesOnly',true);
  if(!(p.permissions&&p.permissions.useProfileForMatching!==undefined)) set('permissions.useProfileForMatching',true);
  const sf=st.profile.safety||{}, pm=st.profile.permissions||{};
  slot.innerHTML=`
    <div class="reccard" id="recpub"><div class="recchip">${IC.star}</div>
      <div class="rectx"><div class="reclbl">Recommended by Kleal</div><div class="rectitle">Meet in public places</div>
        <div class="recnote">Kleal keeps first meetups in cafes, parks and other public spots.</div></div>
      <div class="recarw"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg></div></div>
    ${togRow2('safety.hideExactLocation','Hide exact location','Show approximate area only',!!sf.hideExactLocation)}
    ${togRow2('safety.verifiedOnly','Verified users first','Prefer verified profiles',!!sf.verifiedOnly)}
    ${togRow2('permissions.allowAdjacentMatches','Adjacent suggestions','Expand nearby options',!!pm.allowAdjacentMatches)}
    ${togRow2('permissions.rememberPreferences','Remember preferences','Apply to future plans',!!pm.rememberPreferences)}
    <button class="cta" id="cont" style="margin-top:16px">Continue</button>`;
  const rec=slot.querySelector('#recpub'); if(rec) rec.onclick=()=>rec.classList.toggle('open');
  slot.querySelectorAll('.tog').forEach(tg=>tg.onclick=()=>{ const path=tg.dataset.t, now=!tg.classList.contains('on');
    tg.classList.toggle('on'); set(path,now); });
  slot.querySelector('#cont').onclick=()=>{ lock(slot);
    const s2=st.profile.safety||{}, p2=st.profile.permissions||{};
    const on=['public places'];
    if(s2.hideExactLocation)on.push('approx area'); if(s2.verifiedOnly)on.push('verified first');
    if(p2.allowAdjacentMatches)on.push('adjacent'); if(p2.rememberPreferences)on.push('remember');
    meSay(on.join(', ')); afterAnswer(); };
};

// ======================= SUMMARY =======================
function finishChat(){ botSay(["That's everything I need. Here is what I have on you."], ()=>setTimeout(goSummary,500)); }
function summaryRows(){
  const p=st.profile, R=[];
  const langs=(p.languages&&p.languages.comfortable)||[];
  const ints=(p.interests&&p.interests.explicit)||[];
  const roles=p.interests&&p.interests.roles;
  const areas=(p.geo&&p.geo.comfortableAreas)||(p.city?[p.city]:[]);
  const km=p.geo&&p.geo.maxDistanceKm; const conn=(p.format&&p.format.connect)||[];
  const sf=p.safety||{}, pm=p.permissions||{};
  let roleTxt=''; if(roles){ roleTxt = Array.isArray(roles)?roles.join(', '):(typeof roles==='object'?Object.values(roles).map(v=>typeof v==='object'?Object.values(v).join('/'):v).join(', '):String(roles)); }
  // Figma summary sections: Interests · Your personality · Goals · Safety & Privacy
  R.push(['spark','Interests',(ints.join(', ')||'Not set')+(roleTxt?' ('+roleTxt+')':''),'interests']);
  R.push(['chat','Your personality','Take the test in your profile','personality']);
  R.push(['star','Goals','Add goals in your profile','goals']);
  R.push(['lock','Safety & Privacy',[sf.publicPlacesOnly!==false?'public places':null,sf.hideExactLocation?'approx location':null,sf.verifiedOnly?'verified first':null,pm.allowAdjacentMatches?'adjacent':null,pm.rememberPreferences?'remembers prefs':null].filter(Boolean).join(', ')||'public places','safety']);
  return R;
}
function goSummary(){ st.phase='summary'; const rows=summaryRows();
  const p=st.profile, c=st.crit||{}; const done=(c.done||[]).length, miss=(c.missing||[]).length;
  const conf=Math.round(100*done/((done+miss)||1));
  const nm=p.name||'You', ini=nm.charAt(0).toUpperCase();
  const sub=[p.age||null,p.gender||null,p.city||null].filter(Boolean).join(' · ')||'New profile';
  A.innerHTML=`<div class="head"><div class="ava" id="ava2">${MASCOT_SRC?'':'K'}</div>
    <div class="ht"><div class="htt">What Kleal knows about you</div><div class="hsub">Your agent's memory. Edit anything, anytime.</div></div></div>
    <div class="scroll fade">
      <div class="idcard">
        <div class="idrow"><div class="idava">${esc(ini)}</div>
          <div class="idt"><div class="idn">${esc(nm)}<span class="statusdot"></span></div><div class="idsub">${esc(sub)}</div></div></div>
        <div class="confrow"><span class="cl">Profile readiness</span><span class="cp">${conf}%</span></div>
        <div class="ctrack"><i style="width:${conf}%"></i></div></div>
      <div class="sumc"><div class="sumlbl">Kleal's summary</div>
        <div class="sumtxt" id="sumtxt">${st.profile.summary?esc(st.profile.summary):'<span class="shim">Kleal is writing your summary...</span>'}</div>
        <div class="sumedit" id="sume" style="display:${st.profile.summary?'block':'none'}">Edit</div></div>
      <div class="orows">${rows.map(r=>`<div class="orow" data-step="${r[3]}"><div class="oic2">${IC[r[0]]}</div>
        <div class="ot2"><div class="otn2">${esc(r[1])}</div><div class="otv2">${esc(r[2])}</div></div>
        <div class="orowedit"><span class="rspark">${IC.spark}</span>${IC.edit}</div></div>`).join('')}</div>
    </div>
    <div class="foot"><button class="cta" id="done">Done</button></div>`;
  if(MASCOT_SRC){ const a=document.getElementById('ava2'); a.style.backgroundImage=`url(${MASCOT_SRC})`; a.textContent=''; }
  A.querySelectorAll('.orow').forEach(e=>e.onclick=()=>editStep(e.dataset.step));
  document.getElementById('done').onclick=()=>rDone();
  wireSummaryEdit();
  if(!st.profile.summary) fetchSummary();
}
// the stored artifact: one continuous text describing the user (kept in profile.summary)
function fetchSummary(){
  fetch('/api/v2/summary',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({profile:profileForServer()})}).then(r=>r.json()).then(r=>{
      if(r.summary) st.profile.summary=r.summary;
      if(st.phase!=='summary')return;
      const el=document.getElementById('sumtxt'); if(el)el.textContent=r.summary||'Could not write the summary right now.';
      const e=document.getElementById('sume'); if(e&&r.summary)e.style.display='block';
    }).catch(()=>{ const el=document.getElementById('sumtxt'); if(el)el.textContent='Could not write the summary right now.'; });
}
function wireSummaryEdit(){ const e=document.getElementById('sume'); if(!e)return;
  e.textContent='Edit';
  e.onclick=()=>{ const box=document.getElementById('sumtxt');
    box.innerHTML=`<textarea id="sumta">${esc(st.profile.summary||'')}</textarea>`; e.textContent='Save';
    e.onclick=()=>{ const v=(document.getElementById('sumta').value||'').trim();
      st.profile.summary=v; st.sumEdited=true; box.textContent=v; wireSummaryEdit(); }; };
}
function editStep(id){ const i=SCRIPT.findIndex(s=>s.id===id); if(i<0)return goSummary();
  if(!st.sumEdited) st.profile.summary=null;  // regenerate after edits (unless hand-written)
  st.phase='chat'; st.editing=true; renderChrome(); st.step=i-1; nextStep(); }

// ======================= DONE =======================
function rDone(){ st.phase='done';
  A.innerHTML=`<div class="done fade"><div class="donedisc">${svg('<path d="M5 12.5l4.5 4.5L19 7"/>','0 0 24 24').replace('width="22" height="22"','width="72" height="72"')}</div>
    <div class="d-h">You're on the board!</div>
    <div class="d-sub">Your Kleal agent is ready. Tell it what you want to do and it starts finding people and plans.</div></div>
    <div class="foot"><button class="cta" id="ci">Continue</button></div>`;
  document.getElementById('ci').onclick=()=>openProfile();   // -> the main screen (Agent Home)
}

// ======================= MENU (post-onboarding home) =======================
// hands the collected profile to the Kleal profile app (:7073) via ?p=<base64 utf8 json>
// PROFILE_URL is baked in server-side (env) for the pod, where the profile app lives behind its own
// tunnel host; empty locally -> fall back to the same-host :7073 dev port.
const PROFILE_ORIGIN = ("__PROFILE_URL__") || (location.protocol+'//'+location.hostname+':7073');
function openProfile(){
  const p=Object.assign({},st.profile); delete p.photo;   // strip the heavy dataURL
  let b64=''; try{ b64=btoa(unescape(encodeURIComponent(JSON.stringify(p)))); }catch(e){ b64=btoa(JSON.stringify(p)); }
  location.href = PROFILE_ORIGIN + '/?p=' + encodeURIComponent(b64);
}
function rMenu(){ st.phase='menu';
  const nm = st.profile.name || 'there';
  A.innerHTML=`<div class="head"><div class="ava" id="avaM">${MASCOT_SRC?'':'K'}</div>
      <div class="ht"><div class="htt">Hi, ${esc(nm)}</div><div class="hsub">Your Kleal agent is ready.</div></div></div>
    <div class="scroll fade">
      <div class="menucard" id="mp"><div class="mic">${IC.user}</div>
        <div class="mt"><div class="mtn">My Profile</div><div class="mts">What Kleal knows about you</div></div>
        <div class="mchev">${svg('<path d="M9 6l6 6-6 6"/>','0 0 24 24')}</div></div>
      <div class="menucard soon"><div class="mic">${IC.spark}</div>
        <div class="mt"><div class="mtn">Create an intent</div><div class="mts">Coming soon</div></div></div>
    </div>
    <div class="foot"><button class="link" id="rs">Restart onboarding</button></div>`;
  if(MASCOT_SRC){ const a=document.getElementById('avaM'); a.style.backgroundImage=`url(${MASCOT_SRC})`; a.textContent=''; }
  document.getElementById('mp').onclick=openProfile;
  document.getElementById('rs').onclick=()=>{ Object.assign(st,{phase:'splash',slide:0,profile:{},crit:null,thread:[],step:-1,busy:false,compose:null,funnel:[],fcEl:null,funnelTurns:0,funnelCap:0,editing:false,sumEdited:false}); rSplash(); };
}

rSplash();
</script></body></html>'''

# bake the profile app's public URL (pod: its own tunnel host) into the "My Profile" handoff; empty -> local :7073
HTML = HTML.replace("__PROFILE_URL__", os.environ.get("PROFILE_URL", "").rstrip("/"))

# ---------------------------------------------------------------- HTTP dispatcher (onboarding only)
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            send(self, 200, HTML, "text/html")
        else:
            send_json(self, 404, {})

    def do_POST(self):
        body = read_json(self)
        p = self.path
        if p in ("/api/onboarding/state", "/api/v2/state"):
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            send_json(self, 200, critical_status_v2(prof))
        elif p in ("/api/onboarding/chat", "/api/v2/chat"):
            prior = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            msgs = body.get("messages") if isinstance(body.get("messages"), list) else []
            try:
                send_json(self, 200, v2_chat(msgs, prior))
            except Exception as e:
                send_json(self, 200, {"reply": "I lost the connection for a second. Say that again?",
                                      "options": [], "profile": prior, "crit": critical_status_v2(prior),
                                      "error": str(e)[:200]})
        elif p in ("/api/onboarding/summary", "/api/v2/summary"):
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            try:
                send_json(self, 200, v2_summary(prof))
            except Exception as e:
                send_json(self, 200, {"summary": "", "error": str(e)[:200]})
        else:
            send_json(self, 404, {})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Kleal onboarding-service on http://127.0.0.1:%d  (LLM via llm-service)" % PORT)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
