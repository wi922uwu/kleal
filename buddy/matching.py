"""Intent normalization (inline filtration) + candidate scoring.

A thin v1 of the Excel "Карта интента" sheet-03 model: enough to rank people for an
intent. Full hard-gates + Tier 0-5 expansion replace `find_candidates` later behind the
same interface.
"""

CATEGORIES = [
    "social_meet", "watch_together", "games", "language_practice",
    "interest_conversation", "sport_activity", "networking", "culture_event", "dating",
]

# keyword -> category (RU+EN), ported/extended from llm_demo_local.categorize_intent
CATEGORY_KEYWORDS = {
    "games": ["dota", "cs2", "cs:go", "csgo", "valorant", "league of legends", " lol", "игр", "гейм",
              "teammate", "тиммейт", "lobby", "лобби", "ranked", "катк", "board game", "настолк"],
    "watch_together": ["watch", "смотреть", "матч", "match", "трансляц", "stream", "esports",
                       "киберспорт", "финал", "watch party"],
    "sport_activity": ["football", "футбол", "padel", "падел", "running", "бег", "tennis", "теннис",
                       "basketball", "баскет", "gym", "качал", "yoga", "йога", "play ", "поиграть в футбол"],
    "language_practice": ["spanish", "испанск", "english", "английск", "german", "немецк", "french",
                          "французск", "language", "язык", "practice", "практик", "exchange", "обмен"],
    "social_meet": ["coffee", "кофе", "walk", "прогул", "dinner", "ужин", "drinks", " бар", "hang",
                    "встрет", "погулять", "lunch", "обед", "brunch", "выйти"],
    "interest_conversation": ["talk about", "поговорить", "conversation", "обсуд", "architecture",
                              "архитектур", "cinema", "кино", "book", "книг", "topic", "философ"],
    "networking": ["founder", "стартап", "startup", "networking", "нетворк", "business", "бизнес",
                   "investor", "инвест", "professional", "коллег"],
    "culture_event": ["exhibition", "выставк", "museum", "музей", "concert", "концерт", "lecture",
                      "лекц", "theatre", "театр", "gallery", "opera", "опер"],
}


_LANG_ALIASES = {
    "русский": "ru", "russian": "ru", "ru": "ru", "рус": "ru",
    "английский": "en", "english": "en", "en": "en", "англ": "en",
    "испанский": "es", "spanish": "es", "es": "es", "español": "es", "espanol": "es",
    "немецкий": "de", "german": "de", "de": "de",
    "французский": "fr", "french": "fr", "fr": "fr",
    "каталанский": "ca", "catalan": "ca", "ca": "ca",
    "итальянский": "it", "italian": "it", "it": "it",
    "португальский": "pt", "portuguese": "pt", "pt": "pt",
}


def _norm_langs(langs):
    """Normalize language names/codes to ISO-ish codes so 'русский' == 'ru'."""
    out = set()
    for l in langs or []:
        k = str(l).strip().lower()
        out.add(_LANG_ALIASES.get(k, k))
    return out


def _text(intent):
    parts = [str(intent.get("activity", "")),
             " ".join(str(t) for t in (intent.get("tags") or [])),
             str(intent.get("notes", ""))]
    return " ".join(parts).lower()


def categorize(intent):
    """Inline filtration: keep a valid category, else infer from tags/activity."""
    cat = intent.get("category")
    if cat in CATEGORIES:
        return cat
    text = _text(intent)
    counts = {}
    for c, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw in text:
                counts[c] = counts.get(c, 0) + 1
    return max(counts, key=counts.get) if counts else "social_meet"


def normalize_intent(intent):
    intent = dict(intent or {})
    tags = intent.get("tags")
    if isinstance(tags, str):
        tags = [tags]
    intent["tags"] = [str(t) for t in (tags or [])]
    langs = intent.get("languages")
    if isinstance(langs, str):
        langs = [langs]
    intent["languages"] = [str(x) for x in (langs or [])]
    intent["category"] = categorize(intent)
    return intent


def _profile_categories(profile):
    text = " ".join(str(i) for i in profile.get("interests", [])).lower()
    cats = set()
    for c, kws in CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in kws):
            cats.add(c)
    return cats


def score_candidate(intent, profile, user_profile=None):
    """Return (score, human reason). Thin, deterministic."""
    user_profile = user_profile or {}
    score = 0.0
    reasons = []

    # category / activity
    if intent["category"] in _profile_categories(profile):
        score += 25
        reasons.append("тема: " + intent["category"])

    # tag / entity overlap (exact + substring, e.g. "dota 2" ~ "dota")
    itags = set(t.lower() for t in intent.get("tags", []) if t)
    interests = set(i.lower() for i in profile.get("interests", []) if i)
    overlap = set(itags & interests)
    for t in itags:
        for i in interests:
            if t and (t in i or i in t):
                overlap.add(t)
    if overlap:
        score += 12 * len(overlap)
        reasons.append("совпадает: " + ", ".join(sorted(overlap)))

    # location (only for offline/hybrid/unspecified)
    mode = (intent.get("mode") or "").lower()
    if mode in ("", "offline", "hybrid"):
        ucity = (user_profile.get("city") or intent.get("city") or "").lower()
        pcity = (profile.get("city") or "").lower()
        if ucity and pcity and ucity == pcity:
            score += 15
            reasons.append("тот же город: " + (profile.get("city") or ""))

    # language (soft boost, only when the intent explicitly names a language — the model
    # emits one when it matters; names/codes normalized so 'русский' == 'ru')
    ilangs = _norm_langs(intent.get("languages") or [])
    plangs = _norm_langs(profile.get("languages", []))
    common_l = ilangs & plangs
    if common_l:
        score += 10
        reasons.append("общий язык: " + ", ".join(sorted(common_l)))

    # format
    ifmt = (intent.get("format") or "").lower()
    pfmts = set(f.lower() for f in profile.get("formats", []))
    if ifmt and ifmt in pfmts:
        score += 8
        reasons.append("формат: " + ifmt)

    return round(score, 1), ("; ".join(reasons) if reasons else "общий социальный контекст")


# Minimum relevance to surface as a match. Drops lone-format / lone-language "adjacent"
# hits (sheet-03 Tier 3) so a Dota request doesn't return a yoga profile just for
# sharing a group-format preference. Requires a real topic/tag/city contribution.
MIN_SCORE = 12.0


def find_candidates(intent, user_id, store, limit=4):
    intent = normalize_intent(intent)
    user_profile = store.get_profile(user_id) or {}
    my_blocked = set(user_profile.get("blocked", []))

    out = []
    for p in store.list_profiles(exclude=user_id):
        pid = p["user_id"]
        # hard gates (v1): block-list + dating opt-in.
        # NOTE: language is a SOFT boost in v1, not a gate — the model tends to emit the
        # user's own spoken language, which is not a match *requirement*. A real
        # `required_languages` hard-gate arrives with the full sheet-03 scorer.
        if pid in my_blocked or user_id in set(p.get("blocked", [])):
            continue
        if intent["category"] == "dating" and not p.get("dating_enabled"):
            continue
        score, reason = score_candidate(intent, p, user_profile)
        if score >= MIN_SCORE:
            out.append({"user_id": pid, "name": p.get("name") or pid, "score": score, "reason": reason})

    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:limit]
