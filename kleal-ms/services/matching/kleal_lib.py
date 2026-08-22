# -*- coding: utf-8 -*-
# Kleal shared helper library — the KEYLESS, deterministic utilities carved out of the old
# `llm_demo_local` module. Onboarding-service imports this as `base` (so `base.parse_reply`,
# `base._extract_json`, ... keep working); matching-service imports `base._extract_json`.
#
# There are NO secrets, NO model config, and NO network here — the only place that talks to a
# model is llm-service (reached via shared/llm_client.py). Keep this file small and STABLE:
# it is a frozen contract shared by two services (see contracts.md). Editing it is a cross-team event.
import re
import json

# -------- extractor prompt (fact extraction for the profile card) --------
EXTRACT_PROMPT = '''You are a precise extractor of facts about the user for the Kleal card. Read the conversation (lines "User" and "Agent") and output, as ONE valid JSON object, ONLY what the user said EXPLICITLY and literally about THEMSELF. Output ONLY JSON, with no text before or after.
IRON RULE: if nothing was said about a field — do NOT include it (no nulls, no empty arrays/objects). If the user said almost nothing — return {} or only name. NEVER invent interests, formats, ratings, cities, teams, or languages that were NOT in the user's words. Do not take values from this instruction — it only describes the fields.
Do NOT translate the person's name — write it as the user wrote it. Normalize the obvious to Latin/English: cities (Москва->Moscow, Питер->Saint Petersburg), teams (ЦСКА->CSKA, Зенит->Zenit, Спартак->Spartak), languages (русский/Russian->ru, английский/English->en, испанский/Spanish->es). Keep names of interests, sports and games exactly as the user wrote them, in their language, and write them identically across all fields.
Roles: watch=watch, play=play, discuss=discuss, practice/learn=practice, attend/visit=attend; "I support X" -> domains.sport.favoriteTeams:[X] and roleBySport <sport>:[watch].

Schema (camelCase; output ONLY known fields):
name; city; country; language(ru/en);
geo{comfortableAreas[], maxDistanceKm};
languages{native[], fluent[], comfortable[], learning[]};
availability{days[](weekday/weekend/mon..sun), timeWindows[]("evening"/"19:00-22:00"/"weekend"), spontaneousMode(off/soft/on)};
goals{primary[]}(friends/games/language/networking/watch/sport/dating/city_explore);
interests{explicit[], categories[](sport/games/culture/tech/social/music/outdoor/language), roles{interest:[watch|play|discuss|practice|attend]}};
format{oneOnOne, smallGroup, largeGroup (integers 0-5), modePreference(offline_first/online_first/hybrid), preferredGroupSize};
domains{sport{sportsList[], favoriteTeams[], roleBySport{sport:[watch|play]}, skillLevelBySport{sport:beginner|amateur|intermediate|advanced}, competitiveness(casual/balanced/competitive)}, watch{contentTypes[](sports/movies/series/esports), favoriteTeamsOrSports[]}, games{gamesList[], platformsByGame{game:PC|PS|Xbox|Switch|mobile}, rankByGame{}, competitiveMode(casual/ranked/tryhard), voiceRequired(required/ok/no_voice), toxicityPreference(no_toxicity/banter_ok/competitive_talk_ok), teamPreference(one_time/regular_team)}, language{targetLanguage, targetLevel(A1..C2), partnerType(native/peer/exchange)}, networking{industry[], role, goal[]}, dating{enabled(bool), goal, boundaries[]}};
vibe{primary[]}(calm/energetic/social/intellectual/chill/curious/competitive);
ageVerified18(bool);
safety{publicPlacesOnly(bool), verifiedOnly(bool), noPrivateLocations(bool)};
permissions{useProfileForMatching(bool), allowAdjacentMatches(bool), allowBroadSuggestions(off/in_app_only/push_allowed)}
STRICT about these fields (common mistakes): fill permissions.*, safety.*, format.*, availability.* and vibe ONLY when the user EXPLICITLY answered a DIRECT question about it — NOT from indirect cues and NOT in advance. When in doubt — do NOT include the field.
- ageVerified18:true — only if the user confirmed 18+ or gave an age >=18.
- Do NOT infer language from the language the message is written in; set languages only if the user explicitly named a language they communicate in.
- permissions.useProfileForMatching:true — only on an explicit "yes/ok" to the offer to build a profile / find people.
- permissions.allowAdjacentMatches — only on an explicit answer about near/adjacent ("adjacent ok" -> true, "exact only" -> false).
- safety.* — only on an explicit answer about a cautious mode / public places.
- format.*/availability.*/vibe — only if the user explicitly said about format, time/days/spontaneity, vibe.'''

# -------- output guards (PII strip / prompt-leak guard / one-question dosing) --------
_URL = re.compile(r"\b(?:https?://|www\.)\S+", re.I)
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?:\+?\d[\s\-().]?){10,}")
_EMOJI = re.compile("[🀀-🫿☀-➿🇦-🇿⬀-⯿⌀-⏿️‍]+")
_LEAK = ["VOICE & TONE", "SIGNATURE LANGUAGE", "HOW YOU TALK", "DRAW THE PERSON OUT",
         "WHAT TO COLLECT", "DOMAIN DETAILS", "SAFETY & PRIVACY", "HARD RULES",
         "<profile>", "system prompt", "matching algorithm"]


def sanitize_output(text):
    text = _URL.sub("[link hidden]", text)
    text = _EMAIL.sub("[contact hidden]", text)
    text = _PHONE.sub("[number hidden]", text)
    text = _EMOJI.sub("", text)
    return text


def guard_reply(text):
    if sum(1 for m in _LEAK if m in text) >= 2:
        return "I don't share my internal instructions. Let's get back to it — who or what are you looking for?"
    return text


# Dosing: exactly ONE question per turn, no service narration / markdown. Weak models dump
# "profile updated / next question / choose an option" plus a second question in one turn — cut server-side.
_META_PAT = re.compile("(?im)^.*(профиль обновл|следующий вопрос|выбери один вариант|нажми.{0,14}друг|profile updated|next question|choose (?:one|an) option|tap .{0,14}(?:button|option)).*$")


def dose_reply(text):
    text = re.sub(r"[*`]+", "", text or "")        # drop markdown emphasis (demo renders plain text)
    text = _META_PAT.sub("", text)                  # drop service lines
    q = text.find("?")
    if q != -1:
        text = text[:q + 1]                         # keep only the first question
    text = re.sub(r" {2,}", " ", text)
    return re.sub(r"\n{2,}", "\n", text).strip()


KNOWN_TOP = {"name", "ageVerified18", "ageRange", "city", "country", "timezone", "photoStatus",
             "verificationStatus", "trustStatus", "intents", "aboutMe", "summary", "confidence",
             "inferred", "language", "geo", "languages", "availability", "goals", "format",
             "interests", "vibe", "sessionState", "domains", "safety", "permissions", "dealBreakers"}


# -------- JSON / profile helpers --------
def _loads_lenient(js):
    """Best-effort recovery of a truncated/edge <profile> JSON: balance brackets/braces."""
    if not js:
        return None
    for cut in (len(js), js.rfind("}") + 1, js.rfind("]") + 1):
        if cut <= 0:
            continue
        s = js[:cut]
        ob = s.count("{") - s.count("}")
        oa = s.count("[") - s.count("]")
        cand = s + ("]" * oa if oa > 0 else "") + ("}" * ob if ob > 0 else "")
        try:
            return json.loads(cand)
        except Exception:
            continue
    return None


def _clean_profile(p):
    """Recursively drop null/empty values from the extractor profile."""
    if isinstance(p, dict):
        out = {}
        for k, v in p.items():
            v = _clean_profile(v)
            if v not in (None, "", [], {}):
                out[k] = v
        return out
    if isinstance(p, list):
        return [x for x in (_clean_profile(i) for i in p) if x not in (None, "", [], {})]
    return p


def _cpath(p, path):
    cur = p
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return None
        cur = cur[k]
    return cur


def _chas(p, path):
    return _cpath(p, path) not in (None, "", [], {})


def _cset(p, path):
    return _cpath(p, path) is not None


def _deep_merge(acc, delta):
    if not isinstance(delta, dict):
        return acc
    for k, v in delta.items():
        if v in (None, "", [], {}):
            continue
        if isinstance(v, dict):
            if not isinstance(acc.get(k), dict):
                acc[k] = {}
            _deep_merge(acc[k], v)
        else:
            acc[k] = v
    return acc


def _extract_json(text):
    """Pull the first balanced JSON object out of an extractor reply."""
    text = (text or "").replace("```json", "").replace("```", "")
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return None
    js = m.group(0)
    try:
        return json.loads(js)
    except Exception:
        return _loads_lenient(js)


def parse_reply(text):
    """Replicates onboarding.service.ts: extract <profile>, [INTENT], [BANNER], strip tags."""
    text = text or ""
    banner = None
    m = re.search(r"\[BANNER:\s*([\s\S]*?)\]", text, re.I)
    if m:
        banner = m.group(1).strip()[:80] or None
        text = text.replace(m.group(0), "")
    search = None
    m = re.search(r"\[SEARCH:\s*(\d+)\]", text, re.I)
    if m:
        search = int(m.group(1))
        text = re.sub(r"\[SEARCH:\s*\d+\]", "", text, flags=re.I)
    options = []
    m = re.search(r"\[OPTIONS:\s*([^\]]*)\]", text, re.I)
    if m:
        options = [o.strip() for o in m.group(1).split("|") if o.strip()][:8]
        text = text.replace(m.group(0), "")
    intent = None
    m = re.search(r"\[INTENT:\s*(\{[\s\S]*?\})\s*\]", text, re.I)
    if m:
        try:
            intent = json.loads(m.group(1))
        except Exception:
            intent = None
        text = text.replace(m.group(0), "")
    text = re.sub(r"\[EVENT(?:_UPDATE)?:\s*\{[\s\S]*?\}\s*\]", "", text, flags=re.I)
    profile = None
    m = re.search(r"<profile>([\s\S]*?)(?:</profile>|$)", text, re.I)
    if m:
        js = m.group(1).strip().replace("```json", "").replace("```", "").strip()
        try:
            profile = json.loads(js)
        except Exception:
            profile = _loads_lenient(js)
        # Remove the profile block; if it's closed, preserve any text AFTER it.
        if re.search(r"</profile>", text, re.I):
            text = re.sub(r"<profile>[\s\S]*?</profile>", "", text, flags=re.I)
        else:
            text = re.sub(r"<profile>[\s\S]*", "", text, flags=re.I)
    text = re.sub(r"<think>[\s\S]*?(?:</think>|$)", "", text, flags=re.I)
    text = re.sub(r"</?profile\s*>", "", text, flags=re.I)  # strip stray profile tags
    text = text.replace("```json", "").replace("```", "")
    text = re.sub(r"\[(?:INTENT|EVENT|EVENT_UPDATE|SEARCH|BANNER|OPTIONS):[\s\S]*$", "", text, flags=re.I)
    return text.strip(), profile, intent, banner, search, options
