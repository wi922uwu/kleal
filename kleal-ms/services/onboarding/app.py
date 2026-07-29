# -*- coding: utf-8 -*-
# Kleal onboarding-service — the profile-setup funnel (messenger UI + /api/onboarding/*).
# Carved from the pre-split monolith kleal_v2.py (onboarding half, lines 16-301 + the embedded HTML).
# Talks to llm-service over HTTP for every extract/reply/summary turn; holds NO model keys.
# Contract: ../../shared/contracts.md. Owner: Dev A.
import os, sys, json, re, threading, hashlib, hmac, time, base64
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "..", "..", "shared"), os.path.join(_HERE, "shared")):
    if os.path.isdir(_p) and _p not in sys.path: sys.path.insert(0, _p)
import kleal_lib as base                      # keyless shared helpers/prompts
import config                                  # the one topology table (ports/URLs/store paths)
from llm_client import llm_complete           # the ONLY model access (HTTP -> llm-service)
from http_util import send, send_json, read_json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = config.PORTS["onboarding"]
MODEL_ID = config.MODEL_ID


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

# Onboarding had no language rule at all — every prompt and the whole scripted greeting are English, so
# a user writing Russian got answered in English throughout setup, which is their first impression of
# the product.
_CYR_ONB = re.compile(r"[\u0430-\u044f\u0410-\u042f\u0451\u0401]")


def _onb_lang(hist, want=None):
    """The language the UI is in, when the client tells us; otherwise a guess from what was typed."""
    if want in ("ru", "en"):
        return want
    for m in reversed(hist or []):
        if m.get("role") == "user" and str(m.get("content", "")).strip():
            return "ru" if _CYR_ONB.search(str(m["content"])) else "en"
    return "ru"


_ONB_LANG_RULE = {
    "ru": (" [LANGUAGE: the user is writing in Russian, so write EVERY word of your message in Russian,"
           " including any [OPTIONS: ...] labels. Do not switch to English.]"),
    "en": "",
}

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
Style: react warmly to what they just said in ONE short line, then ask. EXACTLY ONE question per reply — one question mark, never two topics joined by "and". Asking "what, with whom and how long" in a single message is three questions and is forbidden; pick the single most useful one and keep the rest for later turns. The question is the LAST thing in the reply. Do not re-ask a question you already asked, even reworded, whether or not it was answered — if they sidestepped it, move on. English only. For closed choices end with [OPTIONS: a | b | c] (pipe-separated only, no letters/numbers). NEVER re-ask anything already known. No emoji, no markdown, no JSON, no <profile> tags.
A status line tells you exactly what to ask next - follow it strictly.'''

# finish / add-another intent detection at the confirm stage (order matters: FIN first - "no more" contains "more")
# The option buttons are localised (see _CONFIRM_OPTIONS), so these must match the Russian labels too —
# otherwise tapping «Это всё» would fall through and the step would never finish.
_FIN_RE = re.compile(r"that'?s all|that is all|\bfinish|\bdone\b|no more|nothing else|i'?m good|all set|\bnope\b|^\s*no[.! ]*$"
                     r"|это вс[её]|всё|все[.! ]*$|больше нет|хватит|готов|достаточно|^\s*нет[.! ]*$", re.I)
_ADD_RE = re.compile(r"\badd\b|another|one more|\bmore\b|\byes\b|yeah|sure|\balso\b|actually"
                     r"|добав|ещ[её]|да[.! ]*$|конечно|также|хочу", re.I)
_CONFIRM_OPTIONS = {"ru": "Добавить ещё интерес | Это всё", "en": "Add another interest | That's all"}

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
Given the profile JSON, write that summary in __LANGNAME__, second person, 4-8 sentences, warm but strictly factual. In Russian address the user as «ты».
Cover, when present in the JSON: who they are (name, age, gender), where and how far they go (area, radius), languages, EVERY interest with its role, how long they have been into it and key details (platform, rank, team, level, industry), how they like to connect, and their safety choices and permissions.
STRICT: only facts present in the JSON - NEVER invent or embellish. No lists, no markdown, no headings, no emoji, no JSON. Plain flowing text only.'''

def v2_summary(profile, lang="ru"):
    """One LLM call -> the running text summary we store for the user (profile.summary)."""
    cfg = MODEL_ID
    lang = "en" if str(lang).lower() == "en" else "ru"
    prof = {k: v for k, v in (profile or {}).items() if k not in ("photo", "summary")}
    sys_prompt = SUMMARY_PROMPT.replace("__LANGNAME__", "Russian" if lang == "ru" else "English")
    raw = llm_complete(cfg, [{"role": "system", "content": sys_prompt},
                              {"role": "user", "content": json.dumps(prof, ensure_ascii=False)}], 0.4)
    txt = base.parse_reply(raw)[0]
    txt = (txt or "").replace("—", "-").replace("–", "-").strip()
    return {"summary": txt}

def v2_chat(messages, prior, want_lang=None):
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
    # THIRD piece of the localisation coupling, and the one that bit: this sniffed the assistant's own
    # message for the literal English "another interest". Once the funnel started replying in Russian
    # the flag never went true, the _FIN_RE finish branch became unreachable, and the step looped
    # forever — the user answered «Это всё» three times and was asked again each time.

    sys = FUNNEL_PROMPT + _ONB_LANG_RULE[_onb_lang(hist, want_lang)]
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
    # NOT gated on confirm_asked any more. That flag was inferred from the assistant's own PROSE, which
    # only ever worked because the English prompt made it echo "another interest" verbatim; in Russian
    # it rephrases every time ("Похоже, мы уже обсудили все интересы") and no pattern catches it
    # reliably. This branch is already unreachable while `gaps` is non-empty, so "everything is
    # covered AND the user says they're done" is the honest condition — and it is language-free.
    elif _FIN_RE.search(lastu):
        complete = True
        sys += (" [The user confirmed they are done with interests. Reply ONE short, warm wrap-up sentence "
                "that ends in a period (NEVER a question mark) and tells them to tap Continue. No [OPTIONS].]")
    elif _ADD_RE.search(lastu):
        sys += " [The user wants to add another interest. Ask ONE short question: what else they are into. No [OPTIONS].]"
    else:
        # confirm-before-finish: never end the interests step without asking
        sys += (" [ALL PICKED INTERESTS ARE COVERED. Ask EXACTLY ONE closing question: would they like to add "
                "another interest, or is that everything for now. End with [OPTIONS: %s]. "
                "Nothing else.]" % _CONFIRM_OPTIONS[_onb_lang(hist, want_lang)])
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
.hback{flex:none;width:34px;height:34px;border-radius:50%;border:1px solid var(--line);background:#fff;
  color:var(--muted);font-size:15px;line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center}
.hback:active{transform:scale(.94)}

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
/* The input itself is 28px tall and transparent — that is the hit area. The 6px line the user sees
   is the TRACK pseudo-element. Before this the input was 6px tall and the thumb was painted outside
   its box, so dragging meant hitting a six-pixel band with a fingertip. */
input[type=range]{-webkit-appearance:none;appearance:none;width:100%;height:28px;background:transparent;
  outline:none;margin-top:2px;cursor:pointer;touch-action:none}
input[type=range]::-webkit-slider-runnable-track{height:6px;border-radius:4px;background:var(--track)}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;width:24px;height:24px;border-radius:50%;
  background:var(--accent);border:3px solid #fff;box-shadow:0 1px 5px #0004;cursor:pointer;margin-top:-9px}
input[type=range]::-moz-range-track{height:6px;border-radius:4px;background:var(--track)}
input[type=range]::-moz-range-thumb{width:24px;height:24px;border-radius:50%;background:var(--accent);
  border:3px solid #fff;box-shadow:0 1px 5px #0004;cursor:pointer}

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
  margin:auto 0 0;box-shadow:inset 0 2px 12px #0000000d;
  display:flex;align-items:center;justify-content:center}
.illus img{width:124px;height:124px;display:block;pointer-events:none;user-select:none;
  animation:illusIn .42s cubic-bezier(.2,.8,.25,1)}
@keyframes illusIn{from{opacity:0;transform:translateY(8px) scale(.94)}to{opacity:1;transform:none}}
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
.orow.flat{cursor:default}
.orow.flat:active{transform:none}
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

/* ============ Figma onboarding rework (2026-07-25) ============================================
   The mock is one chat surface all the way through: a left-aligned "Creating Profile" header with
   the percentage on the right and a hairline progress rule under it, full-width stacked action
   buttons, and a composer whose back control sits next to the field instead of up in the header. */
.head{padding:14px 18px 10px;gap:11px;position:relative}
.head::after{content:'';position:absolute;left:0;right:0;bottom:0;height:2px;background:var(--line)}
.head .ava{width:34px;height:34px;font-size:15px}
.htt{text-align:left;font-size:17px;font-weight:800;letter-spacing:-.02em}
.hpct{font-size:13px;color:var(--muted);font-weight:600;flex:none}
.hrule{position:absolute;left:0;bottom:0;height:2px;background:var(--accent);width:0;z-index:1;
  border-radius:2px;transition:width .5s cubic-bezier(.4,0,.2,1)}

/* stacked full-width actions */
.acts{display:flex;flex-direction:column;gap:10px;margin-top:12px}
.btn{width:100%;min-height:52px;border:0;border-radius:26px;font:700 16px inherit;cursor:pointer;
  display:flex;align-items:center;justify-content:center;gap:9px;transition:.12s;padding:0 18px}
.btn:active{transform:translateY(1px)}
.btn.pri{background:var(--accent);color:#fff}
.btn.pri:disabled{background:#F7B9C2;color:#fff;cursor:default}
.btn.dark{background:#15171C;color:#fff}
.btn.ghost{background:#ECEDF0;color:var(--ink)}
.btn svg{display:block}

/* age dial */
.dial{display:flex;flex-direction:column;align-items:center;margin-top:6px}
.dial svg{touch-action:none;display:block}
.dial .dnum{font-weight:800;font-size:34px;letter-spacing:-.03em}
.dialbox{margin-top:10px;min-width:74px;height:38px;border-radius:12px;background:var(--field);
  display:flex;align-items:center;justify-content:center;font-weight:700;font-size:15px}

/* labelled row with a value on the right (distance) */
.rowlbl{display:flex;align-items:baseline;justify-content:space-between;margin:16px 0 2px}
.rowlbl .k{font-size:13.5px;font-weight:600;color:var(--ink)}
.rowlbl .v{font-size:13.5px;font-weight:700;color:var(--accent)}

/* select-looking field */
.selwrap{position:relative;margin-top:4px}
.selwrap .cv{position:absolute;right:14px;top:50%;transform:translateY(-50%);color:var(--muted);
  pointer-events:none;display:flex}
.sel{width:100%;height:50px;border:1.5px solid var(--line);background:#fff;border-radius:14px;
  padding:0 40px 0 15px;font:15px inherit;color:var(--ink);outline:none;appearance:none;-webkit-appearance:none}
.sel:focus{border-color:var(--accent)}

/* camera sheet */
.cam-sheet{position:absolute;inset:0;background:#0E1013;z-index:40;display:flex;flex-direction:column;color:#fff}
.cam-top{flex:none;display:flex;align-items:center;justify-content:center;padding:16px 18px;position:relative}
.cam-top .ttl{font-weight:700;font-size:17px}
.cam-top .cancel{position:absolute;left:18px;top:50%;transform:translateY(-50%);background:none;border:0;
  color:#fff;font:600 15px inherit;cursor:pointer}
.cam-stage{flex:1;display:flex;align-items:center;justify-content:center;min-height:0;padding:8px 24px}
.cam-oval{width:min(78vw,300px);aspect-ratio:1/1.28;border-radius:50%;overflow:hidden;background:#22252B;
  border:3px solid rgba(255,255,255,.85);display:flex;align-items:center;justify-content:center}
.cam-oval video,.cam-oval img{width:100%;height:100%;object-fit:cover;display:block}
.cam-bar{flex:none;display:flex;align-items:center;justify-content:center;padding:14px 24px 30px;position:relative}
.cam-shot{width:74px;height:74px;border-radius:50%;background:#fff;border:5px solid rgba(255,255,255,.45);cursor:pointer}
.cam-shot:active{transform:scale(.95)}
.cam-thumb{position:absolute;left:24px;bottom:38px;width:46px;height:46px;border-radius:10px;object-fit:cover;
  background:#2A2E35}
.cam-note{color:#C9CDD4;font-size:13px;text-align:center;padding:0 28px 10px}

/* photo bubble + "photo set" confirmation */
.pbub{align-self:flex-end;width:150px;border-radius:18px;overflow:hidden;background:var(--field)}
.pbub img{width:100%;display:block}
.setcard{display:flex;align-items:center;gap:12px;background:#fff;border:1px solid var(--line);
  border-radius:16px;padding:12px 14px;margin-top:4px}
.setcard img{width:40px;height:40px;border-radius:50%;object-fit:cover;flex:none;background:var(--field)}
.setcard .st{flex:1;min-width:0}
.setcard .stn{font-weight:700;font-size:14.5px}
.setcard .sts{font-size:12.5px;color:var(--muted);margin-top:1px}
.setcard .ok{width:24px;height:24px;border-radius:50%;background:var(--ok);color:#fff;flex:none;
  display:flex;align-items:center;justify-content:center}

/* profile summary screen */
.sumhead{flex:none;padding:14px 18px 10px;display:flex;align-items:center;gap:11px;position:relative}
.sumhead::after{content:'';position:absolute;left:0;right:0;bottom:0;height:2px;background:var(--line)}
.sumwrap{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:14px}
.sumwrap::-webkit-scrollbar{width:0}
.idcard{display:flex;align-items:center;gap:13px;background:#fff;border:1px solid var(--line);
  border-radius:18px;padding:14px}
.idcard .av{width:46px;height:46px;border-radius:50%;background:var(--field);object-fit:cover;flex:none;
  display:flex;align-items:center;justify-content:center;color:var(--muted)}
.idcard .idt{flex:1;min-width:0}
.idcard .idn{font-weight:800;font-size:17px;display:flex;align-items:center;gap:6px}
.idcard .idn .vf{color:var(--accent);display:flex}
.conf{margin-top:7px}
.conf .cl{display:flex;align-items:center;justify-content:space-between;font-size:12px;color:var(--muted)}
.conf .cl b{color:var(--ink)}
.conf .cb{height:5px;border-radius:3px;background:var(--track);margin-top:5px;overflow:hidden}
.conf .cb>i{display:block;height:100%;background:var(--accent);border-radius:3px}
.sumbox{background:#fff;border:1px solid var(--line);border-radius:18px;padding:16px}
.sumbox .sh{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:8px}
.sumbox .sh b{font-size:16px;font-weight:800}
.sumbox .sh span{font-size:11.5px;color:var(--muted)}
.sumbox p{font-size:13.5px;line-height:1.5;color:#3A3F4A}
.infobox{display:flex;gap:11px;background:#EEF4FF;border-radius:16px;padding:14px}
.infobox .ii{color:#4B7BEC;flex:none;display:flex}
.infobox p{font-size:12.5px;line-height:1.45;color:#3C4A66}
.sumfoot{flex:none;padding:12px 16px calc(14px + env(safe-area-inset-bottom))}

/* success screen */
.done{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;
  padding:24px 28px;gap:22px}
.done .ph{width:170px;height:170px;border-radius:50%;background:var(--field);display:flex;
  align-items:center;justify-content:center;color:#B9BEC7}
.done h2{font-size:24px;font-weight:800;letter-spacing:-.02em;line-height:1.25}
.donefoot{flex:none;padding:0 16px 10px}

/* bottom nav (Figma Bottom Nav) */
.bnav{flex:none;display:flex;align-items:flex-end;justify-content:space-between;padding:8px 18px
  calc(10px + env(safe-area-inset-bottom));background:#fff;border-top:1px solid var(--line);position:relative}
.bnav .bi{flex:1;display:flex;flex-direction:column;align-items:center;gap:4px;color:var(--muted);
  font-size:10.5px;font-weight:600}
.bnav .bfab{width:56px;height:56px;border-radius:50%;background:var(--accent);color:#fff;flex:none;
  display:flex;align-items:center;justify-content:center;margin-top:-26px;
  box-shadow:0 8px 20px rgba(245,69,92,.42)}

/* composer back control */
.cback{width:40px;height:40px;border-radius:50%;background:#fff;border:1.5px solid var(--line);
  color:var(--ink);display:flex;align-items:center;justify-content:center;flex:none;cursor:pointer}
.cback:active{transform:scale(.94)}
</style></head><body>
<div class="phone">
  <div id="app"></div>
</div>
<input type="file" id="filein" accept="image/*" style="display:none">
<script>
const A=document.getElementById('app');
// ---- UI language. SAME key and SAME default as the profile app, because they share an origin and
// therefore share localStorage: whoever picks a language here picks it once for both. A browser hint
// (navigator.language) is deliberately NOT consulted — profile defaults to 'ru' unconditionally, and
// any other rule here lands a person in a different language than the one they were just shown.
let UILANG='ru'; try{ const _l=localStorage.getItem('kleal_uilang'); if(_l==='ru'||_l==='en') UILANG=_l; }catch(_e){}
function T(ru,en){ return UILANG==='en' ? en : ru; }
// Displayed label vs stored value. The chip text used to BE the stored value, so translating the
// labels alone would have written «Женщина» and «Готовка» into a store where every other row says
// "Female" and "cooking" — the person would then match nobody. Value first, label second, always.
const GENDERS=[['Male','Мужчина'],['Female','Женщина'],['Other','Другое']];
function genderLabel(v){ const g=GENDERS.find(x=>x[0]===v); return g?T(g[1],g[0]):String(v||''); }
const LANG_RU={English:'Английский',Spanish:'Испанский',German:'Немецкий',French:'Французский',
  Portuguese:'Португальский',Italian:'Итальянский',Russian:'Русский'};
function langLabel(v){ return LANG_RU[v]?T(LANG_RU[v],v):String(v||''); }
// Ten, and the ten the population actually has — the number beside each is how many people carry it.
// A longer menu is not more choice: whatever is missing goes into «Добавить своё», and free text is
// carried through matching as a literal word anyway, so nothing is lost by keeping this short.
const INTERESTS=()=>[
 ['coding',      'Код'],          // 568
 ['hiking',      'Походы'],       // 519
 ['gaming',      'Видеоигры'],    // 469
 ['yoga',        'Йога'],         // 445
 ['cooking',     'Готовка'],      // 433
 ['music',       'Музыка'],       // 376
 ['coffee',      'Кофе'],         // 326
 ['photography', 'Фото'],         // 305
 ['travel',      'Путешествия'],  // 303
 ['football',    'Футбол']];      // 257
function intLabel(v){
  const k=String(v||'').toLowerCase();
  const it=INTERESTS().find(x=>x[0]===k);
  return it?T(it[1],it[0]):String(v||'');   // a free-typed interest is shown exactly as written
}
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
  chevl:svg('<path d="M15 5l-7 7 7 7"/>'),
  chevd:svg('<path d="M6 9.5l6 6 6-6"/>'),
  upload:svg('<path d="M12 16V4M7.5 8.5L12 4l4.5 4.5"/><path d="M4 16v2.5A1.5 1.5 0 005.5 20h13a1.5 1.5 0 001.5-1.5V16"/>'),
  verified:'<svg viewBox="0 0 24 24" fill="currentColor" width="17" height="17"><path d="M12 2l2.4 1.8 3-.2.9 2.9 2.5 1.6-1.2 2.8 1.2 2.8-2.5 1.6-.9 2.9-3-.2L12 22l-2.4-1.8-3 .2-.9-2.9L3.2 15.9 4.4 13.1 3.2 10.3l2.5-1.6.9-2.9 3 .2z"/><path d="M8.4 12.4l2.5 2.5 4.7-4.9" stroke="#fff" stroke-width="1.9" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  usr:svg('<circle cx="12" cy="8.5" r="3.6"/><path d="M4.5 20a7.5 7.5 0 0115 0"/>'),
  list:svg('<path d="M4 7h16M4 12h16M4 17h10"/>'),
  search:svg('<circle cx="11" cy="11" r="6.6"/><path d="M16 16l4 4"/>'),
  msg:svg('<path d="M20 15a3 3 0 01-3 3H8l-4 3V6a3 3 0 013-3h10a3 3 0 013 3z"/>'),
  img:svg('<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="2"/><path d="M4 18l5.5-5 4 3.5L17 13l3 3"/>'),
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
// The photo is stripped from the CHATTY payloads on purpose — /state, the funnel and the summary
// run on almost every turn, and a 40 KB data URL on each of them is pure waste. It is sent exactly
// once, by profileForRegister() below, which is the call that actually persists the person.
function profileForServer(){ const c=Object.assign({},st.profile); delete c.photo; return c; }
// ...and this is where it must NOT be stripped. It used to be: every payload dropped the photo, so
// the store held none for anybody and every candidate card in the app showed the same stock face.
function profileForRegister(){ const c=Object.assign({},st.profile);
  if(!c.photo) delete c.photo; return c; }
async function refreshCrit(){
  try{ st.crit=await fetch('/api/onboarding/state',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({profile:profileForServer()})}).then(r=>r.json()); }catch(e){}
  updateHeader();
}
function updateHeader(){ const b=document.querySelector('.hrule')||document.querySelector('.pbar>i');
  const p=document.querySelector('.hpct')||document.querySelector('.pct');
  const pct=st.crit?st.crit.pct:0; if(b)b.style.width=pct+'%'; if(p)p.textContent=pct+'%'; }
function refreshSendState(){ const cin=document.getElementById('cin'),cs=document.getElementById('csend');
  if(cin&&cs) cs.disabled=!(cin.value.trim()&&st.compose)||st.busy; }

// ======================= SPLASH =======================
const SLIDES=[
 {t:"Tell Kleal what you<br>want to do", s:"Coffee, a match, a game, a walk, language practice, or just something spontaneous."},
 {t:"Find people for the plan,<br>not profiles to scroll", s:"Kleal looks for the right people, rooms, groups or events from your mood, time, place and interests.", m:"searching"},
 {t:"Less social admin.<br>More real plans", s:"Kleal finds who is interested, checks the fit, and brings you options. You confirm every step.", m:"match"},
];
function rSplash(){
  const sl=SLIDES[st.slide], last=st.slide===SLIDES.length-1;
  A.innerHTML=`<div class="splash fade">
    <button class="emu" id="emu">Emulate onboarding</button>
    <div class="illus"><img src="assets/${sl.m||'primary'}.svg" alt="" draggable="false"></div>
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
      <div class="auth-h">${T('Найди своих','Meet your people')}</div>
      <div class="auth-sub">${T('Войди или создай аккаунт, чтобы начать.','Sign in or create your account to get started.')}</div></div>
    <div class="authbtns">
      <button class="authbtn dark" data-auth="apple">${IC_APPLE}<span>${T('Продолжить с Apple','Continue with Apple')}</span></button>
      <button class="authbtn white" data-auth="google">${IC_GOOGLE}<span>${T('Продолжить с Google','Continue with Google')}</span></button>
      <button class="authbtn coral" data-auth="email">${IC_MAIL}<span>${T('Продолжить по почте','Continue with email')}</span></button>
      <button class="authbtn white" data-auth="pw"><span>${T('Логин и пароль','Login and password')}</span></button>
    </div>
    <div class="authterms">${AUTH_TERMS}</div>
  </div>`;
  A.querySelectorAll('[data-auth]').forEach(b=>b.onclick=()=>{ const m=b.dataset.auth;
    if(m==='email'){ rAuthEmail(); }
    else if(m==='pw'){ rAuthPw(); }
    else { st.profile.authMethod=m; rAuthDone(); } });
}
// ---- login + password ----------------------------------------------------------------------
// A shortcut so a profile survives between sessions instead of being rebuilt through onboarding every
// time. Deliberately small: no password reset, no rate limiting, no email verification. The password
// never lives here beyond the request — the server keeps a PBKDF2 hash and a per-account salt, in its
// own file, away from the matching store.
function rAuthPw(){ st.phase='auth';
  A.innerHTML=`<div class="authform fade">
    <button class="authback" id="ab">${IC_CHEV}</button>
    <div class="auth-h2">${T('Вход по логину','Sign in')}</div>
    <div class="auth-sub2">${T('Войди, чтобы вернуться в свой профиль, или создай новый логин.','Sign in to pick your profile back up, or create a new login.')}</div>
    <div class="fieldlbl">${T('Логин','Login')}</div>
    <input class="afield" id="alogin" autocapitalize="off" autocomplete="username" placeholder="${T('например, ivan','e.g. ivan')}">
    <div class="fieldlbl" style="margin-top:12px">${T('Пароль','Password')}</div>
    <input class="afield" id="apw" type="password" autocomplete="current-password" placeholder="${T('минимум 6 символов','at least 6 characters')}">
    <div class="cap" id="apwmsg" style="margin-top:10px;min-height:18px;color:#F5455C"></div>
    <div class="authspace"></div>
    <div class="authfoot">
      <button class="cta" id="asignin" disabled>${T('Войти','Sign in')}</button>
      <button class="cta" id="asignup" disabled style="margin-top:10px;background:#F1F2F5;color:#111">${T('Создать логин','Create a login')}</button>
      <div class="authterms center">${AUTH_TERMS}</div></div>
  </div>`;
  const lg=document.getElementById('alogin'), pw=document.getElementById('apw'),
        msg=document.getElementById('apwmsg'),
        bIn=document.getElementById('asignin'), bUp=document.getElementById('asignup');
  const val=()=>{ const ok=lg.value.trim().length>=3 && pw.value.length>=6;
    bIn.disabled=!ok; bUp.disabled=!ok; return ok; };
  lg.oninput=pw.oninput=()=>{ msg.style.color='#F5455C'; msg.textContent=''; val(); };
  val(); setTimeout(()=>lg.focus(),60);
  const post=(url,b)=>fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(b)}).then(r=>r.json());
  bIn.onclick=async()=>{ bIn.disabled=bUp.disabled=true; bIn.textContent=T('Секунду…','One moment…');
    let r=null; try{ r=await post('/api/onboarding/signin',{login:lg.value.trim(),password:pw.value}); }catch(e){}
    bIn.textContent=T('Войти','Sign in'); val();
    if(!r||!r.ok){ msg.textContent=T('Неверный логин или пароль','Wrong login or password'); return; }
    st.login=r.login;
    if(r.hasProfile&&r.profile){ st.profile=Object.assign({},r.profile); return openProfile(); }
    msg.style.color='#6B7180';
    msg.textContent=T('Логин есть, профиля ещё нет — соберём его сейчас.','Signed in; no profile yet, building it now.');
    setTimeout(rAuthDone,700); };
  bUp.onclick=async()=>{ bIn.disabled=bUp.disabled=true;
    let r=null; try{ r=await post('/api/onboarding/signup',{login:lg.value.trim(),password:pw.value}); }catch(e){}
    val();
    if(!r||!r.ok){ msg.textContent = (r&&r.error==='login taken')?T('Такой логин уже занят','That login is taken')
      : (r&&r.error==='password too short')?T('Пароль короче 6 символов','Password is shorter than 6 characters')
      : (r&&r.error==='login too short')?T('Логин короче 3 символов','Login is shorter than 3 characters')
      : T('Не получилось создать логин','Could not create the login'); return; }
    st.login=r.login; msg.style.color='#6B7180';
    msg.textContent=T('Логин создан. Теперь соберём профиль.','Login created. Now the profile.');
    setTimeout(rAuthDone,700); };
  document.getElementById('ab').onclick=()=>rAuth();
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
// The scripted funnel, in the order the Figma flow walks it. Copy is the mock's, one bubble per
// screen, and every step that collects something owns an inline widget.
const SCRIPT=[
  {id:'ready', bot:()=>[T('Расскажешь пару деталей о себе?','Would you be willing to fill in a few details about yourself?')],
    hint:()=>T('Выбери вариант или напиши своё','Pick some or write your own'), widget:'ready'},
  {id:'name', bot:()=>[T('Отлично! Как тебя зовут?','We\'re on! May I know your name?')], widget:'name'},
  {id:'basics', bot:()=>[T('Супер! Сначала немного о тебе.','Awesome! First, a little bit about you.')], widget:'basics'},
  {id:'location', bot:()=>[T('Класс! Где ты обычно бываешь?','Cool! Where do you usually hang out?')], widget:'location'},
  {id:'language', bot:()=>[T('Отлично. На каких языках тебе комфортно общаться?','Great. What languages are you comfortable communicating in?')],
    hint:()=>T('Выбери варианты или напиши свой','Pick some or write your own'), widget:'language'},
  {id:'interests', bot:()=>[T('Класс! Чем увлекаешься?','Cool! What are your hobbies?')],
    hint:()=>T('Выбери из готовых или напиши своё','Choose from the pre-written options or write your own'), widget:'interests'},
  {id:'photo', bot:()=>[T('Рад знакомству, '+(st.profile.name||'')+'!','Nice to meet you, '+(st.profile.name||'')+'!'),
    T('Давай добавим фото профиля, чтобы тебя узнавали на встречах.','Let\'s add a profile photo so people recognize you at meetups.')],
    hint:()=>T('Добавь фото','Add a photo'), widget:'photo'},
];
function startChat(){
  // The «Your safety matters» step is gone, but everything it applied when a person pressed Continue
  // without touching a toggle still has to exist: it was the ONLY writer of safety.publicPlacesOnly
  // and permissions.useProfileForMatching, and the progress criteria «Safety mode», «Consent» and
  // «Adjacent» read exactly those. Unset, the bar would have stopped short of 100% forever.
  set('safety.publicPlacesOnly', true);        // Kleal's own recommendation, applied by default
  set('safety.hideExactLocation', false);
  set('safety.verifiedOnly', false);
  set('permissions.useProfileForMatching', true);
  // Written explicitly as TRUE on purpose. Every consumer already reads it as `!== false`, i.e.
  // treats "unset" as on — while the toggle rendered `!!value`, i.e. showed it OFF. The switch was
  // telling the user the opposite of what the system did; with the switch gone, the value stops
  // disagreeing with the behaviour.
  set('permissions.allowAdjacentMatches', true);
  set('permissions.rememberPreferences', false);
  st.phase='chat'; st.thread=[]; st.step=-1; st.editing=false; renderChrome(); nextStep();
}
function renderChrome(){
  // Figma header: avatar, left-aligned title, percentage on the right, and the progress as a
  // hairline rule along the bottom edge of the header itself (not a pill under the title).
  A.innerHTML=`<div class="head"><div class="ava" id="ava">${MASCOT_SRC?'':'K'}</div>
    <div class="ht"><div class="htt">${st.editing?T('Редактирование','Editing'):T('Собираем профиль','Creating Profile')}</div></div>
    <div class="hpct">0%</div>
    <div class="hrule"></div>
    ${st.editing?`<button class="hback" id="hback" title="${T('Назад','Back')}" aria-label="${T('Назад','Back')}">&#10005;</button>`:''}</div>
    <div class="thread" id="thread"></div>
    <div class="composer">
      <button class="cback" id="cback" title="${T('Назад','Back')}" aria-label="${T('Назад','Back')}">${IC.chevl}</button>
      <div class="cwrap" id="cwrap"><input id="cin" placeholder="${T('Сообщение…','Message…')}"><span class="mic">${IC.mic}</span></div>
      <button class="csend" id="csend" disabled>${IC.send}</button></div>`;
  if(MASCOT_SRC){ document.getElementById('ava').style.backgroundImage=`url(${MASCOT_SRC})`; document.getElementById('ava').textContent=''; }
  // Leaves an edit WITHOUT changing anything. afterAnswer() also returns here, but only once you have
  // answered — which is not an exit, it is a toll.
  const hb=document.getElementById('hback');
  if(hb) hb.onclick=()=>{ st.editing=false; st.funnel=[]; st.fcEl=null; goSummary(); };
  updateHeader();
  const cin=document.getElementById('cin'), csend=document.getElementById('csend'), cwrap=document.getElementById('cwrap');
  cin.onfocus=()=>cwrap.classList.add('foc'); cin.onblur=()=>cwrap.classList.remove('foc');
  cin.oninput=refreshSendState;
  function sendC(){ if(st.busy||!st.compose)return; const v=cin.value.trim(); if(!v)return; const fn=st.compose; cin.value=''; refreshSendState(); fn(v); }
  csend.onclick=sendC; cin.onkeydown=e=>{ if(e.key==='Enter')sendC(); };
  // The mock puts back next to the composer, not in the header. It re-asks the previous step
  // rather than unwinding state: the answers are already stored, and re-answering overwrites them.
  const cb=document.getElementById('cback');
  if(cb) cb.onclick=()=>{ if(st.busy)return; stepBack(); };
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
  botSay((typeof s.bot==='function')?s.bot():s.bot, ()=>{
    if(s.hint) addHint((typeof s.hint==='function')?s.hint():s.hint);
    if(s.widget){ try{ WIDGETS[s.widget](widgetSlot()); }catch(e){ console.error(e); elBubble('bot',T('Что-то сломалось. Нажми «Начать заново», чтобы попробовать ещё раз.','Something glitched there. Tap Restart to try again.'),false); } }
    else { nextStep(); }   // pure-message step (greeting) -> roll on
  });
}
// Back re-opens the PREVIOUS step. The thread keeps its history — that is what a chat looks like —
// so this appends the question again instead of deleting bubbles; re-answering overwrites the stored
// value. Inside the free-chat interests funnel there is no scripted step to return to, so it is a
// no-op there rather than a jump out of the conversation.
function stepBack(){
  if(st.phase!=='chat' || st.busy) return;
  if(st.funnel && st.funnel.length) return;
  if(st.step<=0) return;
  st.step-=2; setCompose(null); nextStep();
}
function afterAnswer(){ refreshCrit().then(()=>{ if(st.editing){ st.editing=false; return goSummary(); } nextStep(); }).catch(()=>nextStep()); }

// once a step is answered the inline widget collapses away (the answer is now a bubble); this
// also prevents duplicate element ids from piling up in the persistent thread.
function lock(slot){ slot.remove(); }

// ======================= INLINE WIDGETS =======================
const WIDGETS={};

// consent-style gate before the basics form: nothing is asked until the user says they're ready
// Flags/emoji come straight from the mock — they are decoration on top of the same canonical values
// the rest of the funnel already stores, never a new vocabulary.
const LANG_FLAG={English:'🇬🇧',Spanish:'🇪🇸',German:'🇩🇪',French:'🇫🇷',Portuguese:'🇵🇹',Italian:'🇮🇹',Russian:'🇷🇺'};
const INT_EMOJI={coding:'💻',hiking:'🥾',gaming:'🎮',yoga:'🧘',cooking:'🍳',music:'🎵',coffee:'☕',
  photography:'📷',travel:'✈️',football:'⚽'};
const INT_EN={coding:'Coding',hiking:'Hiking',gaming:'Video games',yoga:'Yoga',cooking:'Cooking',
  music:'Music',coffee:'Coffee',photography:'Photography',travel:'Travel',football:'Football'};
function intChipLabel(k){ const en=INT_EN[k]||k; const it=INTERESTS().find(x=>x[0]===k);
  return (it?T(it[1],en):en)+(INT_EMOJI[k]?' '+INT_EMOJI[k]:''); }

// consent-style gate: nothing is asked until the person says go
WIDGETS.ready=function(slot){
  slot.innerHTML=`<div class="chips">
    <div class="chip" id="why">${T('Зачем это нужно?','Why do you need this?')}</div>
    <div class="chip on" id="rdy">${T('Поехали!',"Let's go!")}</div></div>`;
  slot.querySelector('#rdy').onclick=()=>{ if(st.busy)return; lock(slot); meSay(T('Поехали!',"Let's go!")); afterAnswer(); };
  slot.querySelector('#why').onclick=()=>{ if(st.busy)return; meSay(T('Зачем это нужно?','Why do you need this?'));
    botSay([T('Чтобы находить тебе людей и планы рядом, а не ленту незнакомцев. Всё можно изменить потом.',
              "So I can find you people and plans nearby instead of a feed of strangers. You can change any of it later.")]); };
};

// name — typed into the composer, exactly as the mock shows it
WIDGETS.name=function(slot){
  slot.remove();
  setCompose(function(v){
    const nm=String(v||'').trim().slice(0,40); if(!nm) return;
    meSay(nm); set('name',nm); setCompose(null); afterAnswer();
  }, T('Твоё имя','Your name'));
};

// ---- age dial -------------------------------------------------------------------------------
// A round scale, not a number field: the mock's control is the age. Pointer capture is explicit —
// without it a redraw during the drag steals the implicit touch capture and the dial stops after
// one step (the same trap the profile app's dials hit).
function ageDial(slot, value, onChange){
  const MIN=18, MAX=80, R=74, C=2*Math.PI*R;
  slot.innerHTML=`<div class="dial">
    <svg width="188" height="188" viewBox="0 0 188 188" id="agsvg">
      <circle cx="94" cy="94" r="${R}" fill="none" stroke="#EDEEF1" stroke-width="10"/>
      <circle cx="94" cy="94" r="${R}" fill="none" stroke="var(--accent)" stroke-width="10"
        stroke-linecap="round" id="agarc" transform="rotate(-90 94 94)"/>
      <circle id="aghand" r="9" fill="var(--accent)" stroke="#fff" stroke-width="3"/>
      <text x="94" y="94" text-anchor="middle" dominant-baseline="central" class="dnum"
        font-size="34" font-weight="800" fill="#181B22" id="agtxt"></text>
    </svg>
    <div class="dialbox" id="agbox"></div></div>`;
  const svg=slot.querySelector('#agsvg'), arc=slot.querySelector('#agarc'),
        hand=slot.querySelector('#aghand'), txt=slot.querySelector('#agtxt'), box=slot.querySelector('#agbox');
  let cur=Math.min(MAX,Math.max(MIN,value||28));
  function paint(){
    const f=(cur-MIN)/(MAX-MIN);
    arc.setAttribute('stroke-dasharray', C);
    arc.setAttribute('stroke-dashoffset', C*(1-f));
    const a=-Math.PI/2 + f*2*Math.PI;
    hand.setAttribute('cx', 94+R*Math.cos(a)); hand.setAttribute('cy', 94+R*Math.sin(a));
    txt.textContent=cur; box.textContent=cur;
  }
  function at(e){
    const b=svg.getBoundingClientRect();
    const x=e.clientX-(b.left+b.width/2), y=e.clientY-(b.top+b.height/2);
    let a=Math.atan2(y,x)+Math.PI/2; if(a<0)a+=2*Math.PI;
    return Math.round(MIN+(a/(2*Math.PI))*(MAX-MIN));
  }
  let drag=false;
  function apply(v){ v=Math.min(MAX,Math.max(MIN,v)); if(v===cur)return; cur=v; paint(); onChange(cur); }
  svg.addEventListener('pointerdown',e=>{ e.preventDefault(); drag=true;
    try{ svg.setPointerCapture(e.pointerId); }catch(_e){} apply(at(e)); });
  svg.addEventListener('pointermove',e=>{ if(drag){ e.preventDefault(); apply(at(e)); } });
  svg.addEventListener('pointerup',()=>{ drag=false; });
  svg.addEventListener('pointercancel',()=>{ drag=false; });
  paint(); onChange(cur);
  return ()=>cur;
}

WIDGETS.basics=function(slot){
  const p=st.profile;
  slot.innerHTML=`<div class="card">
      <div class="lbl" style="margin-top:0">${T('Твой возраст','Your age')}</div>
      <div id="agslot"></div>
      <div class="lbl">${T('Пол','Sex')}</div>
      <div class="grid3" id="f_sex">${GENDERS.map(g=>`<div class="chip ${p.gender===g[0]?'on':''}" data-g="${g[0]}">${esc(T(g[1],g[0]==='Other'?'Any is fine':g[0]))}</div>`).join('')}</div>
    </div>
    <div class="acts"><button class="btn pri" id="cont" disabled>${T('Продолжаем','Keep going')}</button></div>`;
  const cont=slot.querySelector('#cont');
  function val(){ cont.disabled=!(p.age>=18 && p.gender); }
  ageDial(slot.querySelector('#agslot'), p.age||28, v=>{ set('age',v); set('ageVerified18',true); val(); });
  slot.querySelectorAll('#f_sex .chip').forEach(c=>c.onclick=()=>{
    slot.querySelectorAll('#f_sex .chip').forEach(x=>x.classList.remove('on'));
    c.classList.add('on'); set('gender',c.dataset.g); val(); });
  val();
  cont.onclick=()=>{ lock(slot); meSay([p.age, genderLabel(p.gender)].filter(Boolean).join(', ')); afterAnswer(); };
};

// A raw phone photo is several MB as a dataURL — too big to keep in st.profile, to stash in
// localStorage (≈5MB quota), or to move around. Downscale to a 480px JPEG avatar first; that makes
// the upload reliable and small enough to hand to the profile app.
// One coral pin, inline so the step needs no image asset to show where the person is.
const LPIN_SVG='<svg viewBox="0 0 26 34" width="26" height="34" xmlns="http://www.w3.org/2000/svg">'
  +'<path d="M13 33C13 33 24 21.5 24 13A11 11 0 1 0 2 13c0 8.5 11 20 11 20Z" fill="#F5455C" stroke="#fff" stroke-width="2"/>'
  +'<circle cx="13" cy="13" r="4.2" fill="#fff"/></svg>';
function _downscalePhoto(dataURL, cb){
  const img=new Image();
  img.onload=function(){ const MAX=480; let w=img.width, h=img.height;
    if(w>=h && w>MAX){ h=Math.round(h*MAX/w); w=MAX; } else if(h>w && h>MAX){ w=Math.round(w*MAX/h); h=MAX; }
    try{ const c=document.createElement('canvas'); c.width=w; c.height=h;
      c.getContext('2d').drawImage(img,0,0,w,h); cb(c.toDataURL('image/jpeg',0.85)); }
    catch(_e){ cb(dataURL); } };
  img.onerror=function(){ cb(dataURL); };
  img.src=dataURL;
}
function pickPhoto(cb){ const fi=document.getElementById('filein'); fi.onchange=()=>{ const f=fi.files[0]; if(!f)return;
  const r=new FileReader();
  r.onload=()=>{ _downscalePhoto(r.result, function(small){
    st.profile.photo=small; set('photoStatus','uploaded');
    // onboarding and the profile app share one origin (via the gateway), so localStorage is the
    // delivery channel — the ?p= URL hand-off deliberately strips the heavy dataURL.
    try{ localStorage.setItem('kleal_photo', small); }catch(_e){}
    fi.value=''; cb(); }); };
  r.onerror=()=>{ fi.value=''; }; r.readAsDataURL(f); }; fi.click(); }

// The cities the population actually lives in, ordered by how many people are there — suggesting a
// place with nobody in it helps no one. Each carries its coordinates, so picking one needs no network
// at all: Nominatim is a geocoder, not an autocomplete, and on a prefix it answers «Белг» with
// Belgium and «Bel» with a mountain peak. It stays as the resolver for anything not on this list.
// The RU column is for typing only. The stored name is always the English one, because that is what
// every row in the store uses — type «Белград», store «Белград», and you match nobody.
const CITIES=[
 ["Copenhagen","Копенгаген",55.69,12.56],["Helsinki","Хельсинки",60.16,24.95],
 ["Stockholm","Стокгольм",59.33,18.07],["Sao Paulo","Сан-Паулу",-23.54,-46.64],
 ["London","Лондон",51.52,-0.14],["Oslo","Осло",59.91,10.76],["Yerevan","Ереван",40.17,44.5],
 ["New York","Нью-Йорк",40.72,-74.0],["Istanbul","Стамбул",41.0,28.99],
 ["Mexico City","Мехико",19.44,-99.12],["Cape Town","Кейптаун",-33.91,18.41],
 ["Bogota","Богота",4.72,-74.08],["Bucharest","Бухарест",44.43,26.09],["Dubai","Дубай",25.21,55.27],
 ["Budapest","Будапешт",47.51,19.03],["Tel Aviv","Тель-Авив",32.09,34.77],
 ["Toronto","Торонто",43.64,-79.38],["Lima","Лима",-12.05,-77.05],
 ["San Francisco","Сан-Франциско",37.78,-122.42],["Cairo","Каир",30.04,31.23],
 ["Chicago","Чикаго",41.89,-87.63],["Warsaw","Варшава",52.23,21.02],["Moscow","Москва",55.76,37.62],
 ["Kyiv","Киев",50.46,30.53],["Belgrade","Белград",44.79,20.46],["Lagos","Лагос",6.53,3.39],
 ["Tbilisi","Тбилиси",41.71,44.84],["Los Angeles","Лос-Анджелес",34.06,-118.24],
 ["Austin","Остин",30.27,-97.74],["Tokyo","Токио",35.67,139.69],
 ["Buenos Aires","Буэнос-Айрес",-34.59,-58.37],["Lisbon","Лиссабон",38.73,-9.14],
 ["Zurich","Цюрих",47.37,8.53],["Amsterdam","Амстердам",52.36,4.89],["Krakow","Краков",50.05,19.93],
 ["Nairobi","Найроби",-1.3,36.82],["Zagreb","Загреб",45.8,15.98],
 ["Saint Petersburg","Санкт-Петербург",59.92,30.36],["Milan","Милан",45.46,9.2],
 ["Prague","Прага",50.08,14.45],["Munich","Мюнхен",48.14,11.59],["Seoul","Сеул",37.57,126.98],
 ["Paris","Париж",48.85,2.35],["Athens","Афины",37.97,23.74],["Singapore","Сингапур",1.35,103.82],
 ["Manchester","Манчестер",53.47,-2.23],["Rome","Рим",41.91,12.5],["Mumbai","Мумбаи",19.09,72.88],
 ["Barcelona","Барселона",41.4,2.18],["Rotterdam","Роттердам",51.93,4.48],
 ["Sydney","Сидней",-33.86,151.2],["Lyon","Лион",45.77,4.85],["Valencia","Валенсия",39.47,-0.37],
 ["Delhi","Дели",28.61,77.21],["Madrid","Мадрид",40.42,-3.69],["Vienna","Вена",48.21,16.37],
 ["Melbourne","Мельбурн",-37.82,144.95],["Berlin","Берлин",52.51,13.41],
 ["Auckland","Окленд",-36.85,174.77],["Bangkok","Бангкок",13.77,100.49]];
function cityHit(q){
  q=String(q||'').trim().toLowerCase(); if(!q) return null;
  return CITIES.find(c=>c[0].toLowerCase()===q||c[1].toLowerCase()===q) || null;
}
WIDGETS.location=function(slot){
  const g=st.profile.geo||{}; const r=(g.maxDistanceKm!=null)?g.maxDistanceKm:10; set('geo.maxDistanceKm',r);
  const area=(g.comfortableAreas&&g.comfortableAreas[0])||st.profile.city||'';
  const hasL=(typeof L!=='undefined');
  const mapHtml = hasL ? '<div class="map" id="lmap"></div>'
      + '<div class="hint" style="margin-top:6px">'
      + T('Пин можно перетащить — район важнее города','Drag the pin — the district matters more than the city') + '</div>'
                       : '<div class="map"><div class="ring"></div><div class="pin">'+IC.pin+'</div></div>';
  // Figma order: the place field first, then the distance with its value on the right, then the
  // dark "detect" action, and the map underneath as confirmation of what was chosen. The field
  // stays a typeable input with a datalist (styled as the mock's select): the product needs a CITY
  // with coordinates, and a fixed dropdown cannot hold every city people actually live in.
  slot.innerHTML=`<div class="card">
    <div class="selwrap">
      <input class="sel" id="area" list="cityopts" autocomplete="off" placeholder="${T('Твой город','Your city')}" value="${esc(area)}">
      <span class="cv">${IC.chevd}</span>
    </div>
    <datalist id="cityopts"></datalist>
    <div class="rowlbl"><span class="k">${T('Далеко ли готов ехать?','How far are you happy to go?')}</span><span class="v"><b id="rkm">${r}</b> ${T('км','km')}</span></div>
    <input type="range" id="rad" min="1" max="50" value="${r}">
    <button class="btn dark" id="gloc" type="button" style="margin-top:14px">${IC.pin} ${T('Определить моё местоположение','Detect my location')}</button>
    <div style="margin-top:14px">${mapHtml}</div>
    <div class="cap" id="gstat" style="text-align:left;margin-top:8px"></div>
    </div>
    <div class="acts"><button class="btn pri" id="cont" ${area?'':'disabled'}>${T('Почти закончили','We\'re almost done')}</button></div>`;
  const rad=slot.querySelector('#rad'), area_in=slot.querySelector('#area'), cont=slot.querySelector('#cont');
  // ---- real map (Leaflet + Carto light tiles). A radius circle marks the AREA; no exact pin, no attribution bar. ----
  let lmap=null, circle=null, lpin=null;
  function fit(){ if(lmap&&circle) lmap.fitBounds(circle.getBounds(),{padding:[16,16]}); }
  function recenter(c){ if(!lmap||!circle)return; circle.setLatLng(c); if(lpin) lpin.setLatLng(c); fit(); }
  if(hasL){
    const center=(g.coarseLat&&g.coarseLon)?[g.coarseLat,g.coarseLon]:[41.3874,2.1686];
    lmap=L.map('lmap',{zoomControl:false,scrollWheelZoom:false,attributionControl:false});
    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',{maxZoom:19}).addTo(lmap);
    circle=L.circle(center,{radius:(r||10)*1000,color:'#F5455C',weight:2,fillColor:'#F5455C',fillOpacity:.12}).addTo(lmap);
    // The map only ever showed a circle around whatever city was typed or detected. A person lives in
    // a district, and these coordinates are what the distance gate ranks on — so there is a pin, and
    // it can be moved. Two decimals ≈ a kilometre: this is the COARSE location the step promises,
    // and a pin storing six decimals would turn "город" into a street address.
    lpin=L.marker(center,{draggable:true,autoPan:true,
      icon:L.divIcon({className:'',iconSize:[26,34],iconAnchor:[13,32],html:LPIN_SVG})}).addTo(lmap);
    lpin.on('drag',()=>{ const ll=lpin.getLatLng(); if(circle) circle.setLatLng(ll); });
    lpin.on('dragend',()=>{
      const ll=lpin.getLatLng();
      set('geo.coarseLat', +ll.lat.toFixed(2)); set('geo.coarseLon', +ll.lng.toFixed(2));
      set('geo.located', true);
      stat(T('Точка выбрана вручную','Spot picked by hand'));
      cont.disabled=false;
    });
    lmap.setView(center,12); fit();
    setTimeout(()=>{ if(lmap){ lmap.invalidateSize(); fit(); } }, 80);
  }
  rad.oninput=()=>{ const v=parseInt(rad.value,10); slot.querySelector('#rkm').textContent=v; set('geo.maxDistanceKm',v); if(circle){ circle.setRadius(v*1000); fit(); } };
  const stat=t=>{ const e=slot.querySelector('#gstat'); if(e) e.textContent=t; };
  function setCity(name){ if(!name)return; area_in.value=name; set('geo.comfortableAreas',[name]); set('city',name); cont.disabled=false; }
  // Suggestions, so nobody has to guess the exact spelling of their own city in a blank box.
  function suggest(q){
    q=String(q||'').trim().toLowerCase();
    const hits=(q.length<1?CITIES:CITIES.filter(c=>c[0].toLowerCase().startsWith(q)||c[1].toLowerCase().startsWith(q)))
      .slice(0,8);
    const dl=slot.querySelector('#cityopts');
    // The option VALUE is the canonical English name — that is what lands in the profile. The label
    // beside it is the local spelling, so a Russian speaker still recognises their own city.
    if(dl) dl.innerHTML=hits.map(c=>`<option value="${esc(c[0])}">${esc(c[1])}</option>`).join('');
  }
  // The coordinates are the whole point. geocode() used to only move the circle on the map, so a
  // person who TYPED their city shipped lat:null / lon:null to the store — and the distance gate
  // cannot place someone with no coordinates. Typing a city now locates it, exactly as the GPS path
  // does, and to the same two decimals (~1 km) so it stays an area and never an address.
  async function applyCity(name){
    name=String(name||'').trim(); if(!name) return false;
    const known=cityHit(name);
    // «Белград» and "Belgrade" are the same place; only one of them matches the rest of the store.
    if(known) name=known[0];
    setCity(name);
    let h=known?{lat:known[2],lon:known[3]}:null;
    if(!h){ try{ const j=await fetch('https://nominatim.openstreetmap.org/search?format=json&limit=1&q='
                                     +encodeURIComponent(name)).then(x=>x.json());
                 if(j&&j[0]) h={lat:+j[0].lat, lon:+j[0].lon}; }catch(e){} }
    if(h && isFinite(h.lat) && isFinite(h.lon)){
      set('geo.coarseLat', +h.lat.toFixed(2)); set('geo.coarseLon', +h.lon.toFixed(2));
      recenter([h.lat, h.lon]);
      stat(T('Kleal показывает только район города, никогда точное место.','Kleal shows your city area only, never your exact spot.'));
      return true;
    }
    stat(T('Не нашёл такое место. Проверишь написание?',"I couldn't find that place — check the spelling?"));
    return false;
  }
  const geocode=applyCity;
  async function reverseCity(la,lo){ try{ const j=await fetch('https://nominatim.openstreetmap.org/reverse?format=json&zoom=10&lat='+la+'&lon='+lo).then(x=>x.json());
    const a=(j&&j.address)||{}; return a.city||a.town||a.village||a.municipality||a.county||a.state||''; }catch(e){ return ''; } }
  area_in.oninput=()=>{ const v=area_in.value.trim(); if(v){set('geo.comfortableAreas',[v]);set('city',v);} cont.disabled=!v;
    suggest(v);                       // local list: no debounce needed, no request made
    // picking from the datalist fires `input`, not `change`, in several browsers
    if(cityHit(v)) applyCity(v); };
  area_in.onchange=()=>applyCity(area_in.value.trim());
  area_in.onfocus=()=>suggest(area_in.value.trim());
  suggest('');
  if(area) applyCity(area);
  // geolocation is requested AUTOMATICALLY when this step opens; the detected CITY name is used (never exact spot)
  function autoLocate(){
    if(!navigator.geolocation){ stat(T('Начни печатать город, я буду подсказывать.',"Start typing your city — I'll suggest as you go.")); return; }
    stat(T('Определяю твой город…','Finding your city…'));
    navigator.geolocation.getCurrentPosition(async pos=>{ const la=pos.coords.latitude.toFixed(2),lo=pos.coords.longitude.toFixed(2);
      set('geo.located',true); set('geo.coarseLat',Number(la)); set('geo.coarseLon',Number(lo)); recenter([Number(la),Number(lo)]);
      const city=await reverseCity(la,lo);
      if(city){ setCity(city); stat(T('Kleal показывает только район города, никогда точное место.','Kleal shows your city area only, never your exact spot.')); }
      else { stat(T('Не смог определить город. Начни печатать, я буду подсказывать.',"Couldn't name your city — start typing it, I'll suggest as you go.")); }
    }, err=>{ area_in.placeholder=T('Начни печатать, Kleal подскажет','Start typing — Kleal will suggest');
      stat(err && err.code===1
        ? T('Геолокация для сайта заблокирована. Начни печатать город, я буду подсказывать.',"Location is blocked for this site — start typing your city instead, I'll suggest as you go.")
        : T('Сейчас не получается определить. Начни печатать город, я буду подсказывать.',"Couldn't get a fix right now — start typing your city instead, I'll suggest as you go.")); },
      {enableHighAccuracy:false, timeout:10000, maximumAge:600000}); }
  // Reliable path: geolocation on a user click (browsers suppress the prompt for non-gesture calls).
  const glocBtn=slot.querySelector('#gloc'); if(glocBtn) glocBtn.onclick=autoLocate;
  if(!area) setTimeout(autoLocate, 300);   // best-effort auto-try (works on some browsers); button is the guaranteed prompt
  cont.onclick=async()=>{
    const g2=st.profile.geo||{};
    // last chance to locate: someone can type and hit Continue without ever blurring the field
    if(!(isFinite(g2.coarseLat)&&isFinite(g2.coarseLon))) await applyCity(area_in.value.trim());
    lock(slot); const km=(st.profile.geo&&st.profile.geo.maxDistanceKm)||rad.value;
    meSay((area_in.value.trim()||T('Мой город','My city'))+T(', в пределах ','; within ')+km+T(' км',' km')); afterAnswer(); };
};

const LANGS=['English','Spanish','German','French','Portuguese','Italian','Russian'];
WIDGETS.language=function(slot){
  const cur=(st.profile.languages&&st.profile.languages.comfortable)||[];
  slot.innerHTML=`<div class="chips" id="langs">
    ${LANGS.map(l=>`<div class="chip ${cur.includes(l)?'on':''}" data-l="${l}">${esc(langLabel(l))} ${LANG_FLAG[l]||''}</div>`).join('')}
    ${cur.filter(l=>!LANGS.includes(l)).map(l=>`<div class="chip on" data-l="${esc(l)}">${esc(l)}</div>`).join('')}</div>
    <div class="addrow" id="ar"><span class="ai">${IC.plus}</span><input id="lown" placeholder="${T('Свой вариант','Your option')}"><button class="go" id="ladd">${IC.send}</button></div>
    <div class="acts"><button class="btn pri" id="cont" disabled>${T('Далее','Next')}</button></div>`;
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

WIDGETS.interests=function(slot){
  const cur=((st.profile.interests&&st.profile.interests.explicit)||[]).map(x=>String(x).toLowerCase());
  const known=INTERESTS().map(i=>i[0]);
  const extra=((st.profile.interests&&st.profile.interests.explicit)||[]).filter(x=>known.indexOf(String(x).toLowerCase())<0);
  slot.innerHTML=`<div class="chips" id="ints">
    ${INTERESTS().map(i=>`<div class="chip ${cur.includes(i[0])?'on':''}" data-q="${esc(i[0])}">${esc(intChipLabel(i[0]))}</div>`).join('')}
    ${extra.map(x=>`<div class="chip on" data-q="${esc(x)}">${esc(x)}</div>`).join('')}</div>
    <div class="addrow" id="ar"><span class="ai">${IC.plus}</span><input id="iown" placeholder="${T('Добавить своё','Add your own')}"><button class="go" id="iadd">${IC.send}</button></div>
    <div class="acts"><button class="btn pri" id="cont" disabled>${T('Далее','Next')}</button></div>`;
  const cont=slot.querySelector('#cont');
  function picks(){ return [...slot.querySelectorAll('#ints .chip.on')].map(c=>c.dataset.q); }   // canonical tokens
  function sync(){ const on=picks(); set('interests.explicit',on); cont.disabled=!on.length; }
  slot.querySelectorAll('#ints .chip').forEach(c=>c.onclick=()=>{ c.classList.toggle('on'); sync(); });
  const own=slot.querySelector('#iown'), ar=slot.querySelector('#ar');
  own.onfocus=()=>ar.classList.add('foc'); own.onblur=()=>ar.classList.remove('foc');
  function add(){ const v=own.value.trim(); if(!v)return; const d=document.createElement('div'); d.className='chip on'; d.dataset.q=v; d.textContent=v; d.onclick=()=>{d.remove();sync();}; slot.querySelector('#ints').appendChild(d); own.value=''; sync(); }
  slot.querySelector('#iadd').onclick=add; own.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();add();}};
  sync();
  cont.onclick=()=>{ const on=picks(); if(!on.length)return; lock(slot); meSay(on.map(intLabel).join(', '));
    const funnelDone=st.crit&&st.crit.done&&st.crit.done.includes('Interests')
      &&!(st.crit.missing||[]).some(m=>/^(Role|Experience):/.test(m));
    if(st.editing&&funnelDone){ afterAnswer(); } else { startFunnel(on); } };
};

// ---- photo step: take / upload / skip, then the selfie sheet, then review, then confirmation ----
// Three screens in the mock, one widget here: they are the same decision seen at different stages.
WIDGETS.photo=function(slot){
  slot.innerHTML=`<div class="acts">
    <button class="btn pri" id="ptake">${IC.camera} ${T('Сделать фото','Take photo')}</button>
    <button class="btn dark" id="pup">${IC.upload} ${T('Загрузить фото','Upload photo')}</button>
    <button class="btn ghost" id="pskip">${T('Пропустить','Skip')}</button></div>`;
  slot.querySelector('#ptake').onclick=()=>{ if(st.busy)return; openCamera(dataURL=>reviewPhoto(slot,dataURL)); };
  slot.querySelector('#pup').onclick=()=>{ if(st.busy)return; pickPhoto(()=>reviewPhoto(slot, st.profile.photo)); };
  slot.querySelector('#pskip').onclick=()=>{ if(st.busy)return; lock(slot); meSay(T('Пропустить','Skip')); finishPhoto(); };
};

function photoBubble(src){
  const row=document.createElement('div'); row.className='row fade';
  const b=document.createElement('div'); b.className='pbub'; b.innerHTML=`<img src="${src}" alt="">`;
  row.appendChild(b);
  const tm=document.createElement('div'); tm.className='time me'; tm.textContent=clock(); row.appendChild(tm);
  thread().appendChild(row); scrollDown();
}

function reviewPhoto(slot, dataURL){
  if(!dataURL) return;
  lock(slot);
  photoBubble(dataURL);
  botSay([T('Отлично выглядишь! Идеальное фото профиля.',"Wow — you look great! That's a perfect profile photo.")], ()=>{
    addHint(T('Выбери вариант','Select an option by tap'));
    const w=widgetSlot();
    w.innerHTML=`<div class="chips">
      <div class="chip on" id="puse">${T('Оставить','Use it')}</div>
      <div class="chip" id="pre">${T('Переснять','Retake')}</div></div>`;
    w.querySelector('#puse').onclick=()=>{ if(st.busy)return; lock(w); usePhoto(dataURL); };
    w.querySelector('#pre').onclick=()=>{ if(st.busy)return; lock(w);
      openCamera(d=>reviewPhoto(widgetSlot(), d)); };
  });
}

function usePhoto(dataURL){
  _downscalePhoto(dataURL, function(small){
    st.profile.photo=small; set('photoStatus','uploaded');
    try{ localStorage.setItem('kleal_photo', small); }catch(_e){}
    botSay([T('Супер — теперь это твоё фото профиля.',"Love it — that's your profile photo now.")], ()=>{
      const w=widgetSlot();
      w.innerHTML=`<div class="setcard"><img src="${small}" alt="">
        <div class="st"><div class="stn">${T('Фото профиля установлено','Profile photo set')}</div>
          <div class="sts">${T('Выглядит отлично, ','Looking sharp, ')}${esc(st.profile.name||'')}</div></div>
        <div class="ok">${IC.check}</div></div>`;
      finishPhoto();
    });
  });
}

// Last scripted beat before the summary — the mock's "Now let's find your people."
function finishPhoto(){
  botSay([T('Теперь найдём твоих людей. Как будешь готов.',"Now let's find your people. Ready when you are.")], ()=>{
    const w=widgetSlot();
    w.innerHTML=`<div class="acts"><button class="btn pri" id="pgo">${T('Поехали',"Let's go")}</button></div>`;
    w.querySelector('#pgo').onclick=()=>{ if(st.busy)return; lock(w); afterAnswer(); };
  });
}

// ---- selfie sheet ----------------------------------------------------------------------------
// getUserMedia is not available everywhere (http origins, denied permission, desktop without a
// camera). Rather than show a dead shutter, the sheet says so and hands straight over to the file
// picker, which is the same outcome the user wanted.
function openCamera(cb){
  const host=document.querySelector('.phone')||document.body;
  const sheet=document.createElement('div'); sheet.className='cam-sheet fade';
  sheet.innerHTML=`<div class="cam-top"><button class="cancel" id="ccancel">${T('Отмена','Cancel')}</button>
      <div class="ttl">${T('Сделай селфи','Take a selfie')}</div></div>
    <div class="cam-stage"><div class="cam-oval" id="coval"><video id="cvid" autoplay playsinline muted></video></div></div>
    <div class="cam-note" id="cnote"></div>
    <div class="cam-bar"><button class="cam-shot" id="cshot" aria-label="${T('Снять','Shutter')}"></button></div>`;
  host.appendChild(sheet);
  const vid=sheet.querySelector('#cvid'), note=sheet.querySelector('#cnote');
  let stream=null;
  function close(){ try{ if(stream) stream.getTracks().forEach(t=>t.stop()); }catch(_e){} sheet.remove(); }
  sheet.querySelector('#ccancel').onclick=close;
  sheet.querySelector('#cshot').onclick=()=>{
    if(!stream){ close(); pickPhoto(()=>cb(st.profile.photo)); return; }
    try{
      const c=document.createElement('canvas');
      const w=vid.videoWidth||480, h=vid.videoHeight||640;
      c.width=w; c.height=h; c.getContext('2d').drawImage(vid,0,0,w,h);
      const d=c.toDataURL('image/jpeg',0.9); close(); cb(d);
    }catch(_e){ close(); pickPhoto(()=>cb(st.profile.photo)); }
  };
  if(navigator.mediaDevices&&navigator.mediaDevices.getUserMedia){
    navigator.mediaDevices.getUserMedia({video:{facingMode:'user'},audio:false})
      .then(s=>{ stream=s; vid.srcObject=s; })
      .catch(()=>{ note.textContent=T('Камера недоступна — выбери фото из галереи.','Camera unavailable — pick a photo instead.'); });
  } else {
    note.textContent=T('Камера недоступна — выбери фото из галереи.','Camera unavailable — pick a photo instead.');
  }
}

// interests free-chat funnel (Llama): draws out roles + domain detail, inline option chips
function startFunnel(picks){
  st.fcEl=null; st.funnelTurns=0;
  st.funnelCap=picks.length*2+4;  // 2 questions per interest + confirm/wiggle room (anti-stuck net)
  st.funnel=[{role:'assistant',content:"Nice picks."},{role:'user',content:"I'm into "+picks.join(', ')}];
  setCompose(funnelCompose, T('Расскажи Kleal больше…','Tell Kleal more…'));
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
  // A way to end the funnel is always available — it used to stop only when the model decided to stop
  // or a turn cap fired. But on the closing turn the model ALREADY offers «Это всё», and adding ours
  // beside it printed the same chip twice. Only add one when none of the offered options is already
  // a way out; the test is the same regex the server uses to recognise the answer.
  const FIN=/that'?s all|that'?s enough|that is all|\bfinish|\bdone\b|no more|nothing else|all set|это вс[её]|больше нет|хватит|достаточно/i;
  const hasOut=opts.some(o=>FIN.test(String(o||'').trim()));
  w.innerHTML='<div class="chips">'+opts.map(o=>`<div class="chip" data-o="${esc(o)}">${esc(o)}</div>`).join('')
    +(hasOut?'':`<div class="chip" id="fdone">${T('Это всё',"That's enough")}</div>`)+'</div>';
  w.querySelectorAll('.chip[data-o]').forEach(c=>c.onclick=()=>{ if(st.busy)return; const v=c.dataset.o; w.remove(); funnelTurn(v); });
  const fd=w.querySelector('#fdone'); if(fd) fd.onclick=()=>{ if(st.busy)return; w.remove(); advanceFunnel(); };
}
// always keep exactly ONE Continue button, re-appended at the bottom under the latest message
function funnelContinue(){ if(st.fcEl)st.fcEl.remove(); const w=widgetSlot(); st.fcEl=w;
  w.innerHTML=`<button class="cta" id="fc">${T('Продолжить','Continue')}</button>`;
  w.querySelector('#fc').onclick=()=>advanceFunnel(); }
async function funnelTurn(text, first){
  if(st.busy) return;
  if(text){ st.funnel.push({role:'user',content:text}); st.funnelTurns++; meSay(text); }
  st.busy=true; refreshSendState(); const t=thread();
  const typ=document.createElement('div'); typ.className='typing fade'; typ.innerHTML='<i></i><i></i><i></i>'; t.appendChild(typ); scrollDown();
  try{
    const r=await fetch('/api/onboarding/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({messages:st.funnel, profile:profileForServer(), lang:UILANG})}).then(x=>x.json());
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
  }catch(e){ typ.remove(); elBubble('bot',T('Связь на секунду пропала. Повторишь?','I lost the connection for a second. Say that again?'),true); }
  st.busy=false; refreshSendState();
}



// ======================= SUMMARY =======================
function finishChat(){ botSay([T('Это всё, что мне нужно. Вот что я о тебе знаю.',"That's everything I need. Here is what I have on you.")], ()=>setTimeout(goSummary,500)); }
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
  // The 4th element is the SCRIPT step this row opens, or '' when the row is only telling you
  // something. «Your personality» and «Safety & Privacy» have no step to open — personality is taken
  // in the profile, and the safety step was removed — so they are shown WITHOUT an edit affordance
  // instead of offering one that does nothing. «Goals» is gone entirely: that section no longer
  // exists in the profile either, so the row was pointing at a screen nobody can reach.
  R.push(['spark',T('Интересы','Interests'),(ints.map(intLabel).join(', ')||T('Не указано','Not set'))+(roleTxt?' ('+roleTxt+')':''),'interests']);
  R.push(['chat',T('Твоя личность','Your personality'),T('Пройди тест в профиле','Take the test in your profile'),'']);
  R.push(['lock',T('Безопасность и приватность','Safety & Privacy'),[sf.publicPlacesOnly!==false?T('публичные места','public places'):null,sf.hideExactLocation?T('примерное местоположение','approx location'):null,sf.verifiedOnly?T('сначала проверенные','verified first'):null,pm.allowAdjacentMatches?T('смежные интересы','adjacent'):null,pm.rememberPreferences?T('помнит предпочтения','remembers prefs'):null].filter(Boolean).join(', ')||T('публичные места','public places'),'']);
  return R;
}
function goSummary(){ st.phase='summary'; const rows=summaryRows();
  const p=st.profile, c=st.crit||{}; const done=(c.done||[]).length, miss=(c.missing||[]).length;
  const conf=Math.round(100*done/((done+miss)||1));
  const nm=p.name||T('Ты','You'), ini=nm.charAt(0).toUpperCase();
  // p.gender holds the stored English token; the ID card was reading «27 · Male · Белград».
  const sub=[p.age||null,p.gender?genderLabel(p.gender):null,p.city||null].filter(Boolean).join(' · ')||T('Новый профиль','New profile');
  // Figma "Profile Summary": identity card with a confidence bar, Kleal's own write-up, then the
  // detail rows behind a disclosure — the mock leads with the summary, not with a settings list.
  A.innerHTML=`<div class="sumhead"><div class="ava" id="ava2">${MASCOT_SRC?'':'K'}</div>
    <div class="ht"><div class="htt">${T('Что Kleal знает о тебе','What Kleal knows about you')}</div></div>
    <div class="hpct">${conf}%</div><div class="hrule" style="width:${conf}%"></div></div>
    <div class="sumwrap fade">
      <div class="idcard">
        ${p.photo?`<img class="av" src="${p.photo}" alt="">`:`<div class="av">${IC.usr}</div>`}
        <div class="idt"><div class="idn">${esc(nm)}<span class="vf">${IC.verified}</span></div>
          <div class="conf"><div class="cl"><span>${T('Готовность профиля','Profile confidence')}</span><b>${conf}%</b></div>
            <div class="cb"><i style="width:${conf}%"></i></div></div></div></div>
      <div class="sumbox"><div class="sh"><b>${T('Описание от Kleal',"Kleal's summary")}</b><span>${T('Обновлено сегодня','Updated today')}</span></div>
        <p class="sumtxt" id="sumtxt">${st.profile.summary?esc(st.profile.summary):`<span class="shim">${T('Kleal составляет описание…','Kleal is writing your summary…')}</span>`}</p>
        <div class="sumedit" id="sume" style="display:${st.profile.summary?'block':'none'}">Edit</div></div>
      <button class="btn pri" id="viewall">${T('Все настройки профиля','View all profile settings')}</button>
      <div class="infobox"><span class="ii">${IC.spark}</span>
        <p>${T('Чем больше Kleal о тебе знает, тем точнее он понимает твои намерения и находит нужных людей.','The more Kleal knows about you, the better it can understand your intentions and connect you with the right people.')}</p></div>
      <div class="orows" id="orows" style="display:none">${rows.map(r=>`<div class="orow${r[3]?'':' flat'}" data-step="${r[3]}"><div class="oic2">${IC[r[0]]}</div>
        <div class="ot2"><div class="otn2">${esc(r[1])}</div><div class="otv2">${esc(r[2])}</div></div>
        ${r[3]?`<div class="orowedit"><span class="rspark">${IC.spark}</span>${IC.edit}</div>`:''}</div>`).join('')}</div>
    </div>
    <div class="sumfoot"><button class="btn pri" id="done">${T('Готово','Done')}</button></div>`;
  if(MASCOT_SRC){ const a=document.getElementById('ava2'); a.style.backgroundImage=`url(${MASCOT_SRC})`; a.textContent=''; }
  A.querySelectorAll('.orow').forEach(e=>{ if(e.dataset.step) e.onclick=()=>editStep(e.dataset.step); });
  document.getElementById('done').onclick=()=>rDone();
  // The rows are the same editable list as before, just folded away behind the mock's button.
  const va=document.getElementById('viewall'), rowsEl=document.getElementById('orows');
  if(va&&rowsEl) va.onclick=()=>{ const open=rowsEl.style.display!=='none';
    rowsEl.style.display=open?'none':'block';
    va.textContent=open?T('Все настройки профиля','View all profile settings'):T('Свернуть настройки','Hide settings'); };
  wireSummaryEdit();
  if(!st.profile.summary) fetchSummary();
}
// the stored artifact: one continuous text describing the user (kept in profile.summary)
function fetchSummary(){
  fetch('/api/onboarding/summary',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({profile:profileForServer(), lang:UILANG})}).then(r=>r.json()).then(r=>{
      if(r.summary) st.profile.summary=r.summary;
      if(st.phase!=='summary')return;
      const el=document.getElementById('sumtxt'); if(el)el.textContent=r.summary||T('Сейчас не получилось составить описание.','Could not write the summary right now.');
      const e=document.getElementById('sume'); if(e&&r.summary)e.style.display='block';
    }).catch(()=>{ const el=document.getElementById('sumtxt'); if(el)el.textContent=T('Сейчас не получилось составить описание.','Could not write the summary right now.'); });
}
function wireSummaryEdit(){ const e=document.getElementById('sume'); if(!e)return;
  e.textContent=T('Изменить','Edit');
  e.onclick=()=>{ const box=document.getElementById('sumtxt');
    box.innerHTML=`<textarea id="sumta">${esc(st.profile.summary||'')}</textarea>`; e.textContent=T('Сохранить','Save');
    e.onclick=()=>{ const v=(document.getElementById('sumta').value||'').trim();
      st.profile.summary=v; st.sumEdited=true; box.textContent=v; wireSummaryEdit(); }; };
}
function editStep(id){ const i=SCRIPT.findIndex(s=>s.id===id); if(i<0)return goSummary();
  if(!st.sumEdited) st.profile.summary=null;  // regenerate after edits (unless hand-written)
  st.phase='chat'; st.editing=true; renderChrome(); st.step=i-1; nextStep(); }

// ======================= DONE =======================
function rDone(){ st.phase='done';
  // register the finished profile into the shared user store -> becomes matchable + shows in admin (fire-and-forget)
  try{ fetch('/api/onboarding/register',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({profile:profileForRegister()})}).catch(()=>{}); }catch(_e){}
  // and bind it to the login, so the next sign-in lands in the app instead of back here
  if(st.login){ const pf=Object.assign({},st.profile); delete pf.photo;
    try{ fetch('/api/onboarding/attach',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({login:st.login,name:st.profile.name||'',profile:pf})}).catch(()=>{}); }catch(_e){} }
  // Figma "Profile Success": the congratulation, then straight into creating the first intent —
  // with the app's own bottom nav already visible, so the person can see where they have landed.
  A.innerHTML=`<div class="done fade">
      <div class="ph">${svg('<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="2"/><path d="M4 18l5.5-5 4 3.5L17 13l3 3"/>','0 0 24 24').replace('width="22" height="22"','width="76" height="76"')}</div>
      <h2>${T('Поздравляем!<br>Ты в игре!',"Congratulation!<br>You are on the board!")}</h2>
    </div>
    <div class="donefoot"><button class="btn pri" id="ci">${T('Создать интент','Create Intent')}</button></div>
    <div class="bnav">
      <div class="bi">${IC.list}<span>${T('Интенты','My Intents')}</span></div>
      <div class="bi">${IC.search}<span>${T('Поиск','Search')}</span></div>
      <div class="bfab">${IC.spark}</div>
      <div class="bi">${IC.msg}<span>${T('Сообщения','Messages')}</span></div>
      <div class="bi">${IC.usr}<span>${T('Профиль','Profile')}</span></div>
    </div>`;
  document.getElementById('ci').onclick=()=>openProfile();   // -> the main screen (Agent Home)
}

// ======================= MENU (post-onboarding home) =======================
// hands the collected profile to the Kleal profile app (:7073) via ?p=<base64 utf8 json>
// PROFILE_URL is baked in server-side (env) for the pod, where the profile app lives behind its own
// tunnel host; empty locally -> fall back to the same-host :7073 dev port.
// Fallback is the SAME origin behind the gateway, not host:7073 — that port is internal (127.0.0.1)
// and never reachable from a browser, so whenever PROFILE_URL was not baked in, Continue navigated to
// a dead host and the button just hung. Going through /profile needs no env and works over the tunnel.
const PROFILE_ORIGIN = ("__PROFILE_URL__") || (location.origin + '/profile');
function openProfile(){
  const p=Object.assign({},st.profile); delete p.photo;   // strip the heavy dataURL
  let b64=''; try{ b64=btoa(unescape(encodeURIComponent(JSON.stringify(p)))); }catch(e){ b64=btoa(JSON.stringify(p)); }
  location.href = PROFILE_ORIGIN + '/?p=' + encodeURIComponent(b64);
}
rSplash();
</script></body></html>'''

# bake the profile app's public URL (pod: its own tunnel host) into the "My Profile" handoff; empty -> local :7073
HTML = HTML.replace("__PROFILE_URL__", os.environ.get("PROFILE_URL", "").rstrip("/"))

# ---------------------------------------------------------------- REGISTRATION: onboarding -> shared user store
# Everyone who finishes onboarding is written into the same store the matching agent reads and the admin
# panel shows, so they immediately become matchable and visible. Store format matches services/admin.
# The path is resolved ONCE, in shared/config.py, and every reader/writer imports it from there.
# It used to be recomputed here, in matching and in admin, and the copies disagreed — matching read
# <root>/users.json while this service wrote services/matching/users.json — so a single restart
# without KLEAL_USERS split the store in two and registrations landed in a file the matcher never read.
USERS_PATH = config.USERS
_REG_LOCK = threading.Lock()
FILTER_URL = config.FILTER_URL

# ---------------------------------------------------------------- profile photos
# The photo a person uploads during onboarding used to be thrown away: the client deleted it from
# every payload (profileForServer) and nothing here ever stored one, so all 602 rows in the store had
# no photo and every candidate card in the app fell back to the SAME stock face. People were looking
# at a stranger's stock portrait under someone else's name.
#
# Photos are files, not fields. A 480px JPEG data URL is ~40 KB; multiplied by the store that is tens
# of megabytes of base64 inside the one JSON file the matcher re-reads and holds in memory to rank
# with — it would make every search carry the photo album. So the bytes go to disk and the row keeps
# a short URL, which is all any client needs.
PHOTOS_DIR = os.path.join(os.path.dirname(os.path.abspath(USERS_PATH)), "photos")
PHOTO_MAX_BYTES = 600 * 1024          # a 480px JPEG is ~40 KB; this is a sanity ceiling, not a target
_DATA_URL = re.compile(r"^data:image/(jpeg|jpg|png|webp);base64,(.+)$", re.I | re.S)


def photo_url(uid):
    """The path a client fetches. Served by THIS service, and the gateway already forwards
    /api/onboarding/* here untouched — so no new route anywhere in the topology."""
    return "/api/onboarding/photo/%s.jpg" % uid


def save_photo(uid, data_url):
    """Persist a data-URL photo and return its URL, or None if there is nothing usable to save.

    Never raises: a photo that fails to store must not fail the registration that carried it — the
    person finished onboarding, and losing the whole profile over an avatar would be the worse bug."""
    m = _DATA_URL.match(str(data_url or "").strip())
    if not m:
        return None
    try:
        raw = base64.b64decode(re.sub(r"\s+", "", m.group(2)), validate=False)
    except Exception:
        return None
    if not raw or len(raw) > PHOTO_MAX_BYTES:
        return None
    try:
        os.makedirs(PHOTOS_DIR, exist_ok=True)
        dst = os.path.join(PHOTOS_DIR, "%s.jpg" % uid)
        tmp = dst + ".tmp"
        with open(tmp, "wb") as f:
            f.write(raw)
        os.replace(tmp, dst)                 # atomic: a half-written photo is never served
    except Exception:
        return None
    return photo_url(uid)


def read_photo(uid):
    """Bytes of a stored photo, or None. The id is used as a filename, so it is checked against the
    exact shape ids have — a path fragment must never reach the filesystem."""
    if not re.match(r"^[A-Za-z0-9_-]{1,64}$", str(uid or "")):
        return None
    try:
        with open(os.path.join(PHOTOS_DIR, "%s.jpg" % uid), "rb") as f:
            return f.read()
    except Exception:
        return None


def _canon_interests(words):
    """Give a free-typed interest an English handle the ranker can resolve.

    The search side already canonicalises — «senderismo» becomes hiking/trail before matching sees
    it — but the CANDIDATE side did not, so a person who typed «senderismo» or «настолки» stayed
    invisible to the very search looking for them. The chip interests are canonical already; this
    is for whatever someone typed into «Добавить своё».

    Their own wording stays FIRST (it is what the card shows, and the only handle a novel interest
    like "labubu" ever gets); filtration's canonical topics are appended. Best-effort by design: a
    slow or down filtration must never block a registration, it just means no extra handle.
    Same rule as tools/canonicalise_interests.py, which backfills people already in the store.
    """
    import urllib.request
    GENERIC = {"sport", "sports", "exercise", "activity", "activities", "hobby", "hobbies", "fun",
               "leisure", "beverage", "drink", "drinks", "food", "social", "socializing", "people",
               "meeting", "meetup", "friends", "community", "culture", "tradition", "lifestyle",
               "wellness", "entertainment", "game", "games", "play", "event", "events", "health", "art"}
    out = [str(w).strip() for w in (words or []) if str(w).strip()]
    have = {w.lower() for w in out}
    cands = []
    for w in out:
        try:
            req = urllib.request.Request(FILTER_URL + "/api/filter/categorize",
                                         data=json.dumps({"text": w}).encode(),
                                         headers={"Content-Type": "application/json"})
            topics = json.loads(urllib.request.urlopen(req, timeout=6).read().decode()).get("topics") or []
        except Exception:
            topics = []                    # filtration unavailable -> keep the raw word, lose nothing
        cands.append([str(t).strip().lower() for t in topics[:3]
                      if str(t).strip().lower() and str(t).strip().lower() not in GENERIC])
    # Round-robin, not first-come: filling from interest #1 until the cap left the LAST interest with
    # no English handle at all — exactly the person whose «настолки» then matched nobody.
    for depth in range(3):
        for lst in cands:
            if len(out) >= 8:
                return out[:8]
            if depth < len(lst) and lst[depth] not in have:
                have.add(lst[depth])
                out.append(lst[depth])
    return out[:8]

# ---------------------------------------------------------------- accounts (dev sign-in)
# A SEPARATE file from users.json on purpose. users.json is the matching store: it is read by the
# matcher, served to the admin screen and handed around as candidate data. Credentials must not ride
# along with something that is already being passed about, even hashed.
ACCOUNTS_PATH = config.ACCOUNTS
_ACC_LOCK = threading.Lock()
_PBKDF_ROUNDS = 200_000


def _read_accounts():
    try:
        with open(ACCOUNTS_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _write_accounts(d):
    tmp = ACCOUNTS_PATH + ".tmp"
    os.makedirs(os.path.dirname(os.path.abspath(ACCOUNTS_PATH)), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, ACCOUNTS_PATH)
    try:
        os.chmod(ACCOUNTS_PATH, 0o600)
    except Exception:
        pass


def _hash_pw(password, salt):
    return hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"),
                               bytes.fromhex(salt), _PBKDF_ROUNDS).hex()


def _acc_key(login):
    return str(login or "").strip().lower()


def signup(login, password, name=None):
    """Create an account. The profile itself is attached later, when onboarding finishes."""
    key = _acc_key(login)
    if len(key) < 3:
        return {"ok": False, "error": "login too short"}
    if len(str(password or "")) < 6:
        return {"ok": False, "error": "password too short"}
    with _ACC_LOCK:
        accs = _read_accounts()
        if key in accs:
            return {"ok": False, "error": "login taken"}
        salt = os.urandom(16).hex()
        accs[key] = {"login": str(login).strip(), "salt": salt,
                     "hash": _hash_pw(password, salt), "name": str(name or "").strip(),
                     "created": int(time.time())}
        _write_accounts(accs)
    return {"ok": True, "login": str(login).strip()}


def signin(login, password):
    """Verify, and hand back the stored profile so the app can skip onboarding entirely."""
    key = _acc_key(login)
    acc = _read_accounts().get(key)
    # Same answer whether the login is unknown or the password is wrong: a different message is a
    # free oracle for which logins exist.
    bad = {"ok": False, "error": "wrong login or password"}
    if not acc:
        return bad
    try:
        want = _hash_pw(password, acc.get("salt") or "")
    except Exception:
        return bad
    if not hmac.compare_digest(want, str(acc.get("hash") or "")):
        return bad
    # The ONBOARDING-shaped profile, not the user row. They are different shapes — the row is flat
    # (interests: [...]) and the client expects the nested form (interests.explicit) that the profile
    # app knows how to map. Handing back the row restored a profile with no interests at all.
    prof = acc.get("profile") if isinstance(acc.get("profile"), dict) else None
    return {"ok": True, "login": acc.get("login"), "name": acc.get("name") or "",
            "profile": prof, "hasProfile": bool(prof)}


def attach_profile(login, name, profile=None):
    """Bind the finished onboarding profile to the account, so the next sign-in restores it verbatim."""
    key = _acc_key(login)
    with _ACC_LOCK:
        accs = _read_accounts()
        if key not in accs:
            return {"ok": False, "error": "unknown login"}
        accs[key]["name"] = str(name or "").strip()
        if isinstance(profile, dict):
            # photo is a data URL and can be megabytes; it already travels through shared-origin
            # localStorage, so it has no business in the credential file.
            accs[key]["profile"] = {k: v for k, v in profile.items() if k != "photo"}
        _write_accounts(accs)
    return {"ok": True}
_R2M = {"watch": "watch", "play": "play", "discuss": "discuss", "practice": "practise",
        "practise": "practise", "attend": "attend", "meet": "meet"}


def _first(*vals):
    for v in vals:
        if v not in (None, "", [], {}):
            return v
    return None



# 'Spanish'[:2] is 'sp' and 'German'[:2] is 'ge' — neither is a language code, and matching's
# requiredLanguages gate compares codes, so a Spanish speaker written as 'sp' matched nobody.
_LANG_CODES = {"english": "en", "spanish": "es", "german": "de", "french": "fr", "portuguese": "pt",
               "italian": "it", "russian": "ru", "catalan": "ca", "ukrainian": "uk", "polish": "pl",
               "английский": "en", "испанский": "es", "немецкий": "de", "французский": "fr",
               "португальский": "pt", "итальянский": "it", "русский": "ru", "каталанский": "ca",
               "serbian": "sr", "сербский": "sr", "swedish": "sv", "шведский": "sv",
               "sp": "es"}   # legacy typo written by an older build; repair, do not drop


# Valid codes are ISO 639-1, NOT the keys of the name table above. Deriving them from that table
# was a bug caught only by counting the live store: 30 of the 31 codes in users.json are real
# (hi, ar, da, ko, zh, nl, ja, he, cs, el, th, vi, id ...) and simply have no English/Russian NAME
# entry, so the narrower check would have deleted a real language from anyone the admin touched —
# a worse bug than the one being fixed. The only genuinely broken code in the store is "sp", two
# rows, both real onboarding profiles; it is repaired by the alias table.
_LANG_VALID = set("""en es de fr pt it ru ca uk pl sr sv hi ar da ko zh fi nl tr no ja hu ro
he cs el th vi id bg hr sk sl et lv lt is ga cy sq mk bs be az ka hy fa ur bn ta te ml kn mr pa gu
si ne my km lo ms tl sw af zu am ku ps tg uz kk ky mn ta la eo""".split())


def _lang_code(x):
    """The comment above explains why `x[:2]` is wrong — and the fallback did it anyway for every
    word outside the table. Portuguese was in the table; Dutch, Greek, Turkish, Hebrew and anything
    typed freehand were not, and each became a two-letter string that is not a language code and
    therefore matches nobody. Unknown now returns "" and the caller drops it: no language is honest,
    a wrong language is not."""
    x = str(x or "").strip().lower()
    if not x:
        return "en"
    if x in _LANG_CODES:
        return _LANG_CODES[x]
    return x if (len(x) == 2 and x in _LANG_VALID) else ""


def _profile_to_user(p):
    """Map a Kleal onboarding profile -> a complete, matching-safe candidate record (like admin _norm_user)."""
    p = p or {}
    name = str(_first(p.get("name"), "New user")).strip() or "New user"
    ints = p.get("interests") or {}
    interests = [str(x).strip().lower() for x in (ints.get("explicit") if isinstance(ints, dict) else ints) or [] if str(x).strip()][:6]
    langs = (p.get("languages") or {})
    ll = langs.get("comfortable") or langs.get("fluent") or langs.get("native") or [] if isinstance(langs, dict) else []
    langs = [c for c in (_lang_code(x) for x in ll if str(x).strip()) if c][:4] or ["en"]
    vibe = ""
    vb = p.get("vibe")
    if isinstance(vb, dict) and vb.get("primary"):
        vibe = str(vb["primary"][0]).lower()
    elif isinstance(vb, str):
        vibe = vb.lower()
    geo = p.get("geo") or {}
    area = str(_first(p.get("city"), (geo.get("comfortableAreas") or [None])[0], "") or "").strip()
    # role from the first interest's role, normalised to matching's vocabulary
    role = "meet"
    roles = (ints.get("roles") if isinstance(ints, dict) else None) or {}
    if isinstance(roles, dict):
        for _k, rv in roles.items():
            r0 = (rv[0] if isinstance(rv, list) and rv else rv)
            if r0:
                role = _R2M.get(str(r0).lower(), "meet")
                break
    dating = bool((p.get("domains") or {}).get("dating", {}).get("enabled")) or \
        ("dating" in [str(x).lower() for x in (p.get("goals") or {}).get("primary") or []])
    try:
        age = int(_first(p.get("age"), (p.get("ageRange") or "28").split("-")[0], 28))
    except (TypeError, ValueError):
        age = 28
    # A stored per-person "km" is meaningless — distance depends on who is looking. It used to be
    # fabricated from a hash of the name; now it is honestly absent and distance comes from real
    # coarse coordinates when the person granted geolocation during onboarding.
    deals = [str(x).strip() for x in (p.get("dealBreakers") or []) if str(x).strip()][:6]
    lat = geo.get("coarseLat") if isinstance(geo.get("coarseLat"), (int, float)) else None
    lon = geo.get("coarseLon") if isinstance(geo.get("coarseLon"), (int, float)) else None
    try:
        radius = int(geo.get("maxDistanceKm")) if geo.get("maxDistanceKm") else None
    except (TypeError, ValueError):
        radius = None
    gender = str(p.get("gender") or "").strip() or None
    goals = [str(x).strip() for x in ((p.get("goals") or {}).get("primary") or []) if str(x).strip()][:4]
    sf = p.get("safety") or {}
    return {
        "id": "on" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:8],
        "name": name, "interests": interests or ["social"],
        # vibe/entities used to be invented ('chill', '<Interest> scene') — collected-or-absent now
        "vibe": vibe, "langs": langs, "area": area,
        "km": None, "lat": lat, "lon": lon, "radiusKm": radius, "open": True, "role": role,
        "gender": gender, "goals": goals, "summary": str(p.get("summary") or "")[:PROSE_MAX],
        # register_profile replaces the whole row, so the story must be carried here too or
        # re-running onboarding silently wipes what the person wrote.
        "story": str(p.get("story") or "")[:STORY_MAX],
        "personality": str(p.get("personality") or "")[:PROSE_MAX],
        "persona": (_clean_persona(p.get("persona")) if p.get("persona") else None),
        # meeting-format preference (Figma «Формат встреч»); matching's mode_format reads this. Empty
        # until the user picks in the profile sheet — an empty list is honestly "no preference stated".
        "formats": [str(x).strip().lower() for x in (p.get("formats") or []) if str(x).strip()][:8],
        "safety": {"publicPlacesOnly": bool(sf.get("publicPlacesOnly", True)),
                   "verifiedOnly": bool(sf.get("verifiedOnly")),
                   "hideExactLocation": bool(sf.get("hideExactLocation"))},
        "datingOk": dating, "age": age, "verified": bool(p.get("ageVerified18", True)),
        "paused": False, "pending": 0, "blocksMe": False, "lastActiveDays": 0, "declinedOwnerDaysAgo": None,
        "intents": [], "entities": [],
        "dealBreakers": deals, "source": "onboarding",
        # receiving policy (Matching Core spec §4.4): registering = explicit consent to be matched,
        # so a default ACTIVE policy is written here. Dating is opt-in only (spec §17). Matching's
        # readiness engine (core_v2.readiness_state) reads this to decide open_now/quiet-hours/busy.
        "receiving": _default_receiving(dating),
    }


def _default_receiving(dating_ok):
    doms = ["social_meet", "walk", "culture_event", "language_exchange", "coworking",
            "watch_together", "games", "sport_activity", "professional_networking"]
    if dating_ok:
        doms.append("dating")
    return {"status": "active", "allowed_domains": doms, "passive_outreach": True,
            "quiet_hours": {"start": "22:00", "end": "09:00", "tz_offset_min": 120},
            "paused_until": None}


def _valid_ts(s):
    """A paused_until string is valid only if it parses as epoch seconds or 'YYYY-MM-DDTHH:MM'."""
    s = str(s).strip()
    try:
        float(s)
        return True
    except ValueError:
        pass
    try:
        time.strptime(s[:16], "%Y-%m-%dT%H:%M")
        return True
    except (ValueError, TypeError):
        return False


_RECV_STATUSES = ("active", "busy", "paused")
_RECV_DOMAINS = {"social_meet", "walk", "games", "language_exchange", "sport_activity",
                 "culture_event", "professional_networking", "watch_together", "coworking", "dating"}

def update_receiving(name, patch):
    """The user's own availability settings — a WHITELISTED patch of their receiving policy
    (status / passive_outreach / allowed_domains / quiet_hours / paused_until), atomic on the
    shared store. Unknown fields are dropped, never written."""
    key = str(name or "").strip().lower()
    if not key:
        return {"ok": False, "error": "name required"}
    clean = {}
    st = str(patch.get("status") or "").lower()
    if st in _RECV_STATUSES:
        clean["status"] = st
    if isinstance(patch.get("passive_outreach"), bool):
        clean["passive_outreach"] = patch["passive_outreach"]
    doms = patch.get("allowed_domains")
    if isinstance(doms, list):
        keep = [d for d in (str(x).strip().lower() for x in doms) if d in _RECV_DOMAINS]
        if keep:
            clean["allowed_domains"] = keep
    q = patch.get("quiet_hours")
    if isinstance(q, dict):
        qh = {}
        for f in ("start", "end"):
            v = str(q.get(f) or "")
            # HH:MM with a REAL clock time (00:00-23:59); "99:99" must be rejected, not stored
            if (len(v) == 5 and v[2] == ":" and v[:2].isdigit() and v[3:].isdigit()
                    and 0 <= int(v[:2]) <= 23 and 0 <= int(v[3:]) <= 59):
                qh[f] = v
        if isinstance(q.get("tz_offset_min"), (int, float)) and -720 <= q["tz_offset_min"] <= 840:
            qh["tz_offset_min"] = int(q["tz_offset_min"])
        if qh:
            clean["quiet_hours"] = qh
    if "paused_until" in patch:
        pu = patch["paused_until"]
        if pu is None or isinstance(pu, (int, float)):
            clean["paused_until"] = pu
        elif isinstance(pu, str) and _valid_ts(pu):     # accept epoch or 'YYYY-MM-DDTHH:MM', drop junk
            clean["paused_until"] = pu
    with _REG_LOCK:
        try:
            with open(USERS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            users = data.get("users") if isinstance(data, dict) else data
            if not isinstance(users, list):
                users = []
        except Exception:
            users = []
        me = next((x for x in users if str(x.get("name", "")).strip().lower() == key), None)
        if me is None:
            return {"ok": False, "error": "user not found"}
        r = me.get("receiving")
        if not isinstance(r, dict):
            r = _default_receiving(bool(me.get("datingOk")))
        if not clean:                                   # empty patch = read the current policy
            return {"ok": True, "receiving": r}
        merged = dict(r)
        merged.update({k: v for k, v in clean.items()
                       if k != "quiet_hours"})
        if "quiet_hours" in clean:
            merged["quiet_hours"] = dict(r.get("quiet_hours") or {}, **clean["quiet_hours"])
        me["receiving"] = merged
        tmp = USERS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"users": users}, f, ensure_ascii=False)
        os.replace(tmp, USERS_PATH)
    return {"ok": True, "receiving": merged}




def _read_users():
    try:
        with open(USERS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        users = data.get("users") if isinstance(data, dict) else data
        return users if isinstance(users, list) else []
    except Exception:
        return []


def get_user(name):
    key = str(name or "").strip().lower()
    if not key:
        return None
    for x in _read_users():
        if str(x.get("name", "")).strip().lower() == key:
            return x
    return None


# The whole point of the whitelist: the profile client pushes edits here, and only fields a person
# actually owns may change — never source/verified/paused or other trust-bearing flags.
# Deliberately ABSENT and never to be added: verified, datingOk, paused, pending, blocksMe,
# declinedOwnerDaysAgo, source, role. Those are the hard gates in matching/app.py — a client patch
# that could set them could make a person invisible to everyone with no trace on screen.
_PATCH_FIELDS = {"age", "gender", "area", "radiusKm", "lat", "lon", "langs", "interests",
                 "goals", "formats", "summary", "story", "personality", "persona", "vibe", "safety"}
STORY_MAX = 4000        # a life story, not a novel — and update_user writes straight into the row
PROSE_MAX = 900         # what buddy actually returns for a summary / personality paragraph

# The personality test's own record: a closed vocabulary per axis. An unrecognised token is DROPPED,
# never defaulted — a default here would be the profile asserting something nobody answered.
_PERSONA_AXES = {
    "energy":    ("energised", "drained", "depends"),
    "group":     ("one", "small", "crowd"),
    "depth":     ("deep", "light", "practical"),
    "firstMeet": ("talk", "doing", "event"),
    "pace":      ("fast", "slow", "depends"),
    "planning":  ("advance", "spontaneous", "flexible"),
    "seek":      ("long", "interest", "wider"),
}


def _clean_persona(p):
    if not isinstance(p, dict):
        return None
    axes = p.get("axes") if isinstance(p.get("axes"), dict) else {}
    keep = {k: v for k, v in axes.items() if k in _PERSONA_AXES and v in _PERSONA_AXES[k]}
    out = {"v": 1, "axes": keep}
    if isinstance(p.get("takenAt"), (int, float)):
        out["takenAt"] = int(p["takenAt"])
    return out


def update_user(name, patch):
    key = str(name or "").strip().lower()
    if not key or not isinstance(patch, dict):
        return {"ok": False, "error": "name and patch required"}
    clean = {k: v for k, v in patch.items() if k in _PATCH_FIELDS}
    # update_user does a blind row.update(), so every free-text field a person can type without any
    # form validation gets its own guard: a string, capped, or not written at all.
    for _k, _cap in (("story", STORY_MAX), ("personality", PROSE_MAX), ("summary", PROSE_MAX)):
        if _k in clean:
            if isinstance(clean[_k], str):
                clean[_k] = clean[_k][:_cap]
            else:
                clean.pop(_k)
    if "persona" in clean:
        cp = _clean_persona(clean["persona"])
        if cp is None:
            clean.pop("persona")          # not a dict: leave whatever the row already holds
        else:
            clean["persona"] = cp
    if not clean:
        return {"ok": False, "error": "no editable fields in patch"}
    with _REG_LOCK:
        users = _read_users()
        row = next((x for x in users if str(x.get("name", "")).strip().lower() == key), None)
        if row is None:
            return {"ok": False, "error": "unknown user"}
        row.update(clean)
        tmp = USERS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"users": users}, f, ensure_ascii=False)
        os.replace(tmp, USERS_PATH)
    return {"ok": True, "user": row}

def register_profile(profile):
    """Append/replace this person in the shared store (de-dupe by name). Atomic write."""
    u = _profile_to_user(profile)
    u["interests"] = _canon_interests(u.get("interests")) or u.get("interests")
    # The photo arrives as a data URL and becomes a file. Re-onboarding replaces the whole row, so a
    # second pass that carries no photo must KEEP the one already on disk — same reason the story is
    # carried through _profile_to_user rather than left to be silently wiped.
    saved = save_photo(u["id"], (profile or {}).get("photo"))
    if saved:
        u["photo"] = saved
    elif read_photo(u["id"]):
        u["photo"] = photo_url(u["id"])
    with _REG_LOCK:
        try:
            with open(USERS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            users = data.get("users") if isinstance(data, dict) else data
            if not isinstance(users, list):
                users = []
        except Exception:
            users = []
        key = u["name"].strip().lower()
        users = [x for x in users if str(x.get("name", "")).strip().lower() != key]  # replace prior onboarding of same name
        users.append(u)
        tmp = USERS_PATH + ".tmp"
        os.makedirs(os.path.dirname(os.path.abspath(USERS_PATH)), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"users": users}, f, ensure_ascii=False)
        os.replace(tmp, USERS_PATH)
    return u


# ---------------------------------------------------------------- HTTP dispatcher (onboarding only)
# ---------------------------------------------------------------- mascot artwork (splash slides)
# The three poses the intro slides need, served from /assets/<name>.svg. They are duplicated from the
# profile service on purpose: every service here is a single self-contained file, and reaching across
# to :7073 would make the splash screen depend on another service being up just to draw itself.
ASSETS = {
    'match': '''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512" fill="none" role="img" aria-labelledby="matchTitle matchDesc"> <title id="matchTitle">Kleal mascot — match confirmed pose</title> <desc id="matchDesc">Kleal celebrates a mutual match with open arms and two connected route nodes.</desc> <defs> <linearGradient id="matchBody" x1="114" y1="66" x2="394" y2="447" gradientUnits="userSpaceOnUse"> <stop stop-color="#FF756A"/> <stop offset="0.55" stop-color="#FF5B55"/> <stop offset="1" stop-color="#E84242"/> </linearGradient> <radialGradient id="matchFace" cx="0" cy="0" r="1" gradientTransform="translate(224 153) rotate(54) scale(170 160)" gradientUnits="userSpaceOnUse"> <stop stop-color="#FFFDF5"/> <stop offset="1" stop-color="#F4E8D7"/> </radialGradient> <radialGradient id="matchGround"> <stop stop-color="#111217" stop-opacity="0.18"/> <stop offset="0.72" stop-color="#111217" stop-opacity="0.06"/> <stop offset="1" stop-color="#111217" stop-opacity="0"/> </radialGradient> </defs> <g id="kleal-match"> <ellipse cx="257" cy="451" rx="154" ry="24" fill="url(#matchGround)"/> <path d="M88 217c87-54 250-55 336 0" stroke="#FF5B55" stroke-width="6" stroke-linecap="round" stroke-dasharray="2 16"/> <path d="M257 35C161 35 91 105 91 195c0 56 24 95 61 121-23 44-15 94 23 126 30 25 70 18 87-21 20 39 64 44 95 15 31-29 41-70 24-108 49-11 78-46 75-85-3-43-36-70-78-69C374 91 323 35 257 35Z" fill="url(#matchBody)"/> <path d="M392 201c52-5 82 20 78 60-4 36-35 55-70 48-29-6-39-28-27-50 9-17 25-25 42-21 15 3 21 15 16 26-5 11-17 15-29 10" stroke="#E84242" stroke-width="25" stroke-linecap="round"/> <ellipse cx="255" cy="190" rx="118" ry="111" fill="url(#matchFace)"/> <path d="M200 191c9 11 20 11 29 0" stroke="#171920" stroke-width="8" stroke-linecap="round"/> <path d="M281 191c9 11 20 11 29 0" stroke="#171920" stroke-width="8" stroke-linecap="round"/> <path d="M230 227c17 21 36 21 53 0" stroke="#171920" stroke-width="8" stroke-linecap="round"/> <path d="M160 307c-41-8-75-36-83-70" stroke="url(#matchBody)" stroke-width="37" stroke-linecap="round"/> <path d="M352 307c41-8 75-36 83-70" stroke="url(#matchBody)" stroke-width="37" stroke-linecap="round"/> <circle cx="72" cy="222" r="16" fill="#FFF8EB" stroke="#FF5B55" stroke-width="8"/> <circle cx="440" cy="222" r="16" fill="#FFF8EB" stroke="#FF5B55" stroke-width="8"/> <path d="M209 414c-5 22-16 38-33 50" stroke="#E84242" stroke-width="34" stroke-linecap="round"/> <path d="M306 414c5 22 17 38 34 50" stroke="#E84242" stroke-width="34" stroke-linecap="round"/> <ellipse cx="166" cy="468" rx="31" ry="14" fill="#D9363C"/> <ellipse cx="350" cy="468" rx="31" ry="14" fill="#D9363C"/> <circle cx="114" cy="112" r="7" fill="#FF5B55"/> <path d="m398 105 7 12 13 2-10 9 3 13-13-6-12 6 2-13-9-9 13-2Z" fill="#FF5B55" opacity="0.72"/> </g> </svg>''',
    'primary': '''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512" fill="none" role="img" aria-labelledby="primaryTitle primaryDesc"> <title id="primaryTitle">Kleal mascot — primary welcome pose</title> <desc id="primaryDesc">Coral Kleal mascot facing forward and waving.</desc> <defs> <linearGradient id="primaryBody" x1="110" y1="62" x2="395" y2="448" gradientUnits="userSpaceOnUse"> <stop stop-color="#FF756A"/> <stop offset="0.55" stop-color="#FF5B55"/> <stop offset="1" stop-color="#E84242"/> </linearGradient> <radialGradient id="primaryFace" cx="0" cy="0" r="1" gradientTransform="translate(219 155) rotate(55) scale(175 166)" gradientUnits="userSpaceOnUse"> <stop stop-color="#FFFDF5"/> <stop offset="1" stop-color="#F4E8D7"/> </radialGradient> <linearGradient id="primaryHighlight" x1="150" y1="62" x2="210" y2="315" gradientUnits="userSpaceOnUse"> <stop stop-color="white" stop-opacity="0.34"/> <stop offset="1" stop-color="white" stop-opacity="0"/> </linearGradient> <radialGradient id="primaryGround"> <stop stop-color="#111217" stop-opacity="0.18"/> <stop offset="0.72" stop-color="#111217" stop-opacity="0.06"/> <stop offset="1" stop-color="#111217" stop-opacity="0"/> </radialGradient> </defs> <g id="kleal-primary"> <ellipse cx="256" cy="451" rx="159" ry="24" fill="url(#primaryGround)"/> <path d="M257 35C161 35 91 105 91 195c0 55 23 94 59 120-25 42-18 92 19 126 29 28 72 23 91-17 19 40 64 47 96 18 33-29 45-72 28-112 48-10 79-44 77-82-2-43-34-72-75-74C378 92 324 35 257 35Z" fill="url(#primaryBody)"/> <path d="M391 202c55-6 86 20 83 61-3 37-35 58-73 52-31-5-42-27-31-51 8-19 24-29 44-26 17 2 24 14 20 27-4 12-16 17-29 13" stroke="#E84242" stroke-width="26" stroke-linecap="round"/> <ellipse cx="255" cy="192" rx="118" ry="112" fill="url(#primaryFace)"/> <path d="M169 128c21-39 62-61 105-57" stroke="url(#primaryHighlight)" stroke-width="18" stroke-linecap="round" opacity="0.9"/> <ellipse cx="216" cy="191" rx="12" ry="18" fill="#171920"/> <ellipse cx="294" cy="191" rx="12" ry="18" fill="#171920"/> <path d="M237 229c12 13 26 13 38 0" stroke="#171920" stroke-width="8" stroke-linecap="round"/> <path d="M153 307c-38-10-66-39-64-72 1-24 18-43 39-42 17 1 29 13 28 29-1 15-12 24-24 31" stroke="url(#primaryBody)" stroke-width="36" stroke-linecap="round"/> <path d="M356 314c32-4 58-26 67-55" stroke="url(#primaryBody)" stroke-width="38" stroke-linecap="round"/> <path d="M412 249c6-12 16-20 30-25" stroke="#FF6C62" stroke-width="12" stroke-linecap="round"/> <circle cx="444" cy="223" r="8" fill="#FFF8EB"/> <path d="M205 410c-4 23-14 39-31 52" stroke="#E84242" stroke-width="34" stroke-linecap="round"/> <path d="M310 412c5 23 17 39 35 51" stroke="#E84242" stroke-width="34" stroke-linecap="round"/> <ellipse cx="166" cy="467" rx="32" ry="15" fill="#D9363C"/> <ellipse cx="355" cy="467" rx="32" ry="15" fill="#D9363C"/> <circle cx="378" cy="91" r="9" fill="#FFF8EB" opacity="0.55"/> </g> </svg>''',
    'searching': '''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512" fill="none" role="img" aria-labelledby="searchTitle searchDesc"> <title id="searchTitle">Kleal mascot — searching pose</title> <desc id="searchDesc">Kleal leans forward, looks to the right, and shades its eyes while searching for a good match.</desc> <defs> <linearGradient id="searchBody" x1="110" y1="70" x2="398" y2="445" gradientUnits="userSpaceOnUse"> <stop stop-color="#FF756A"/> <stop offset="0.56" stop-color="#FF5B55"/> <stop offset="1" stop-color="#E84242"/> </linearGradient> <radialGradient id="searchFace" cx="0" cy="0" r="1" gradientTransform="translate(247 157) rotate(57) scale(163 153)" gradientUnits="userSpaceOnUse"> <stop stop-color="#FFFDF5"/> <stop offset="1" stop-color="#F4E8D7"/> </radialGradient> <radialGradient id="searchGround"> <stop stop-color="#111217" stop-opacity="0.18"/> <stop offset="0.72" stop-color="#111217" stop-opacity="0.06"/> <stop offset="1" stop-color="#111217" stop-opacity="0"/> </radialGradient> </defs> <g id="kleal-searching" transform="rotate(-4 256 256)"> <ellipse cx="250" cy="451" rx="163" ry="24" fill="url(#searchGround)"/> <path d="M251 41C158 49 95 124 103 211c5 54 34 89 72 110-20 44-6 95 34 124 32 24 70 14 84-24 22 34 65 38 94 8 29-30 36-71 17-107 47-13 74-49 69-88-6-42-40-68-81-65-2-83-73-135-141-128Z" fill="url(#searchBody)"/> <path d="M403 198c51-8 82 15 81 54-1 36-30 57-66 53-29-3-41-25-31-48 8-17 23-27 40-25 16 2 23 13 20 25-3 11-14 17-27 14" stroke="#E84242" stroke-width="25" stroke-linecap="round"/> <ellipse cx="265" cy="193" rx="116" ry="109" transform="rotate(4 265 193)" fill="url(#searchFace)"/> <ellipse cx="237" cy="190" rx="12" ry="18" fill="#171920"/> <ellipse cx="312" cy="184" rx="12" ry="18" fill="#171920"/> <circle cx="241" cy="185" r="3.5" fill="white"/> <circle cx="316" cy="179" r="3.5" fill="white"/> <path d="M267 230c12 9 24 8 34-3" stroke="#171920" stroke-width="8" stroke-linecap="round"/> <path d="M337 147c29-31 59-36 84-17" stroke="url(#searchBody)" stroke-width="34" stroke-linecap="round"/> <path d="M396 126c22-8 43-3 57 13" stroke="#FF7166" stroke-width="17" stroke-linecap="round"/> <path d="M395 126c13 12 20 27 21 45" stroke="#E84242" stroke-width="13" stroke-linecap="round"/> <path d="M164 317c-38-7-65-31-65-61 0-22 15-39 35-39 17 0 29 11 29 27 0 14-10 24-22 29" stroke="url(#searchBody)" stroke-width="35" stroke-linecap="round"/> <path d="M218 416c-17 22-38 35-63 39" stroke="#E84242" stroke-width="34" stroke-linecap="round"/> <path d="M315 414c20 19 43 29 68 29" stroke="#E84242" stroke-width="34" stroke-linecap="round"/> <ellipse cx="143" cy="457" rx="33" ry="14" transform="rotate(-12 143 457)" fill="#D9363C"/> <ellipse cx="394" cy="444" rx="33" ry="14" transform="rotate(8 394 444)" fill="#D9363C"/> <circle cx="441" cy="92" r="8" fill="#FF5B55"/> <circle cx="470" cy="82" r="5" fill="#FF5B55" opacity="0.48"/> </g> </svg>''',
}


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            send(self, 200, HTML, "text/html")
        elif self.path.split("?")[0].startswith("/api/onboarding/photo/"):
            # Profile photos. Served from here because this service owns the user store and therefore
            # owns the write; the gateway already forwards /api/onboarding/* untouched, so a photo is
            # reachable from every screen in the app without a new route anywhere.
            uid = self.path.split("?")[0][len("/api/onboarding/photo/"):]
            raw = read_photo(uid[:-len(".jpg")] if uid.endswith(".jpg") else uid)
            if raw is None:
                return send_json(self, 404, {})
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(raw)))
            # A photo is immutable for as long as it is that person's photo, and re-uploading writes
            # the same path — so revalidate rather than cache hard, or a changed avatar would stick.
            self.send_header("Cache-Control", "public, max-age=300")
            self.end_headers()
            self.wfile.write(raw)
        elif self.path.startswith("/assets/") and self.path.endswith(".svg"):
            art = ASSETS.get(self.path[len("/assets/"):-len(".svg")])
            if not art:
                return send_json(self, 404, {})
            b = art.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers(); self.wfile.write(b)
        else:
            send_json(self, 404, {})

    def do_POST(self):
        body = read_json(self)
        # ONE canonical name per endpoint. Every route used to be spelled out twice — under
        # /api/onboarding/* and under the /api/v2/* alias left from the kleal_v2 era — and the
        # callers picked between them at random: this service's own UI called /api/v2/chat but
        # /api/onboarding/register, the profile UI called /api/v2/receiving but
        # /api/onboarding/profile. The result was ten endpoints that were served and never
        # called, and no way to tell which spelling was real. The alias is now rewritten once,
        # here, so old clients (a phone holding a cached bundle) keep working while the
        # dispatcher below knows exactly one name for each thing.
        p = self.path
        if p.startswith("/api/v2/"):
            p = "/api/onboarding/" + p[len("/api/v2/"):]
        if p == "/api/onboarding/state":
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            send_json(self, 200, critical_status_v2(prof))
        elif p == "/api/onboarding/chat":
            prior = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            msgs = body.get("messages") if isinstance(body.get("messages"), list) else []
            try:
                send_json(self, 200, v2_chat(msgs, prior, body.get("lang")))
            except Exception as e:
                send_json(self, 200, {"reply": "I lost the connection for a second. Say that again?",
                                      "options": [], "profile": prior, "crit": critical_status_v2(prior),
                                      "error": str(e)[:200]})
        elif p == "/api/onboarding/summary":
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            try:
                send_json(self, 200, v2_summary(prof, body.get("lang") or "ru"))
            except Exception as e:
                send_json(self, 200, {"summary": "", "error": str(e)[:200]})
        elif p == "/api/onboarding/signup":
            return send_json(self, 200, signup(body.get("login"), body.get("password"), body.get("name")))
        elif p == "/api/onboarding/signin":
            return send_json(self, 200, signin(body.get("login"), body.get("password")))
        elif p == "/api/onboarding/attach":
            return send_json(self, 200, attach_profile(body.get("login"), body.get("name"), body.get("profile")))
        elif p == "/api/onboarding/register":
            # everyone who finishes onboarding is written into the shared user store (matchable + in admin)
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            try:
                send_json(self, 200, {"ok": True, "user": register_profile(prof)})
            except Exception as e:
                send_json(self, 200, {"ok": False, "error": str(e)[:200]})
        elif p == "/api/onboarding/profile":
            send_json(self, 200, {"user": get_user(body.get("name"))})
        elif p == "/api/onboarding/profile-update":
            try:
                send_json(self, 200, update_user(body.get("name"),
                                                 body.get("patch") if isinstance(body.get("patch"), dict) else {}))
            except Exception as e:
                send_json(self, 200, {"ok": False, "error": str(e)[:200]})
        elif p == "/api/onboarding/receiving":
            # availability settings = the user's receiving policy (Matching Core spec §4.4).
            # {name} alone reads the current policy; whitelisted fields update it atomically.
            try:
                send_json(self, 200, update_receiving(body.get("name"),
                                                      body.get("receiving") if isinstance(body.get("receiving"), dict) else {}))
            except Exception as e:
                send_json(self, 200, {"ok": False, "error": str(e)[:200]})
        else:
            send_json(self, 404, {})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Kleal onboarding-service on http://127.0.0.1:%d  (LLM via llm-service)" % PORT)
    ThreadingHTTPServer((config.BIND_HOST, PORT), H).serve_forever()
