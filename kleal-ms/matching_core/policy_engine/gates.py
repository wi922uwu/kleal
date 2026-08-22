# -*- coding: utf-8 -*-
"""§8.1 Канонические gates — детерминированные exclusions ДО scoring.

Каждый gate возвращает (decision, reason), decision ∈ {ALLOW, BLOCK, REVIEW}. «Результат при
неизвестности» из таблицы §8.1 соблюдается (для большинства — BLOCK: unknown ≠ разрешение).
Safety/privacy НЕ дают «штраф совместимости» (§1) — они дают BLOCK/REVIEW.
"""

ALLOW, BLOCK, REVIEW = "ALLOW", "BLOCK", "REVIEW"

_ACCOUNT_BAD = frozenset({"suspended", "deactivated", "banned", "deleted"})
_SAFETY_HARD = frozenset({"banned", "csam_block", "legal_hold", "restricted"})
# режимы, которые нельзя смешивать (§8.1 intent mode isolation, §8.3): friendship/dating/professional/language...
_MODE_OF = {"dating": "dating", "social_meet": "friendship", "walk": "friendship",
           "culture_event": "friendship", "watch_together": "friendship", "coworking": "professional",
           "professional_networking": "professional", "language_exchange": "language",
           "games": "games", "sport_activity": "sport"}


def account_status(intent, c, ctx):
    st = str(c.get("accountStatus") or "active").lower()
    if st in _ACCOUNT_BAD or c.get("suspended") is True:
        return BLOCK, "account not active"
    # §8.1 таблица: unknown -> BLOCK. MVP по умолчанию permissive; strict-режим -> REVIEW (не молчаливый ALLOW).
    if (ctx or {}).get("strict_unknown") and c.get("accountStatus") is None and c.get("suspended") is None:
        return REVIEW, "account status unknown (strict)"
    return ALLOW, None


def mutual_block(intent, c, ctx):
    nm = str(c.get("name", "")).strip().lower()
    if nm in ctx.get("blocked", set()) or c.get("blocksMe"):
        return BLOCK, "mutual block"
    return ALLOW, None


def safety_restrictions(intent, c, ctx):
    flags = c.get("safetyFlags") or []
    if isinstance(flags, list) and any(f in _SAFETY_HARD for f in flags):
        return BLOCK, "safety restriction"
    if c.get("sensitivity") == "restricted" or "review" in flags:
        return REVIEW, "safety restriction: held for review"
    return ALLOW, None


def privacy_visibility(intent, c, ctx):
    # ОБЕ стороны должны разрешать использование данных для этого purpose (§8.1)
    vis = c.get("visibility") or (c.get("privacy") or {}).get("visibility")
    if vis == "private":
        return BLOCK, "private profile"
    if (ctx or {}).get("searcher_visibility") == "private":
        return BLOCK, "your profile is private for this purpose"     # сторона искателя
    # unknown -> BLOCK по таблице §8.1; MVP permissive, strict-режим -> REVIEW
    if (ctx or {}).get("strict_unknown") and vis is None:
        return REVIEW, "visibility unknown (strict)"
    return ALLOW, None


# Вердикт#24: 18+ — это ПРОДУКТОВАЯ политика (условия использования, onboarding, age verification, safety,
# родительские сценарии), а не скрытая техническая константа движка. Объявляем явно.
AGE_POLICY = {"kind": "adults_only_18plus", "declared_product_policy": True,
              "requires": ["terms_of_use", "onboarding_age_gate", "age_verification", "safety_flow"]}


def age_legal(intent, c, ctx):
    age = c.get("age")
    if age is not None and age < 18:
        return BLOCK, "under 18"
    if intent.get("type") == "dating" and age is None:
        return BLOCK, "age unknown for dating"      # unknown -> BLOCK для sensitive-сценария
    mn, mx = intent.get("minAge"), intent.get("maxAge")
    if mn or mx:
        if age is None:
            # §8.1: age unknown -> BLOCK, но при soft_eligibility -> REVIEW (held for answer)
            return (REVIEW, "age unknown") if intent.get("soft_eligibility") else (BLOCK, "age unknown")
        if mn and age < mn:
            return BLOCK, "below age range"
        if mx and age > mx:
            return BLOCK, "above age range"
    return ALLOW, None


_TYPE2PURPOSE = {"dating": "dating", "social_meet": "friendship", "walk": "friendship",
                 "culture_event": "friendship", "watch_together": "friendship", "games": "games",
                 "sport_activity": "sport", "professional_networking": "networking",
                 "coworking": "coworking", "language_exchange": "language"}


def intent_mode_isolation(intent, c, ctx):
    # §8.1/§8.3/§17.2: dating не смешивается с friendship/professional/language и т.д.
    want = _MODE_OF.get(intent.get("type") or "social_meet", "friendship")
    cand_modes = c.get("modes")
    if isinstance(cand_modes, list) and cand_modes and want not in cand_modes:
        return BLOCK, "intent mode isolation"
    if intent.get("type") == "dating" and not c.get("datingOk"):
        return BLOCK, "not open to dating"
    # data-driven purpose isolation из канонической таксономии (blocked_cross_purpose рёбра)
    from ..taxonomy import canonical as CANON
    ip = intent.get("purpose") or _TYPE2PURPOSE.get(intent.get("type"))
    cp = c.get("purpose")
    if ip and cp and CANON.purpose_blocked(ip, cp):
        return BLOCK, "purpose isolation (%s vs %s)" % (ip, cp)
    return ALLOW, None


_LANG_LEVELS = {"a1": 1, "a2": 2, "b1": 3, "b2": 4, "c1": 5, "c2": 6, "native": 6, "fluent": 5,
                "advanced": 5, "intermediate": 3, "basic": 1}


def _lvl(x):
    return _LANG_LEVELS.get(str(x).lower(), 0)


def language_feasibility(intent, c, ctx):
    reql = intent.get("requiredLanguages") or []
    if not reql:
        return ALLOW, None
    # required -> {code: min_level}; язык hard -> BLOCK при отсутствии кода ИЛИ недостаточном уровне (§8.1)
    req = {}
    for r in reql:
        if isinstance(r, dict):
            req[str(r.get("code"))[:2].lower()] = _lvl(r.get("level") or r.get("min_level"))
        else:
            req[str(r)[:2].lower()] = 0
    have = {}
    for l in (c.get("langs") or []):
        if isinstance(l, dict):
            have[str(l.get("code"))[:2].lower()] = _lvl(l.get("level"))
        else:
            have[str(l)[:2].lower()] = 6                  # строка без уровня -> достаточно (совместимость)
    for code, minlvl in req.items():
        if code not in have:
            return BLOCK, "missing a required language"
        if minlvl and have[code] < minlvl:
            return BLOCK, "language level below required (%s)" % code
    return ALLOW, None


def time_feasibility(intent, c, ctx):
    # §4.3/§8.4 interval algebra: окна пересекаются достаточной длительностью (UTC/tz)?
    t = intent.get("time") or {}
    iwin = t.get("windows")
    cav = c.get("availability") if isinstance(c.get("availability"), dict) else None
    cwin = (cav or {}).get("windows") if cav else c.get("time_windows")
    if iwin and cwin:
        from ..contracts.time_algebra import windows_overlap
        min_dur = int(t.get("duration") or intent.get("minDurationMin") or 0)
        feasible, _ = windows_overlap(iwin, cwin, min_duration_min=min_dur,
                                      a_tz=int(t.get("tz_offset_min") or 0),
                                      b_tz=int((cav or {}).get("tz_offset_min") or 0))
        if not feasible:
            return BLOCK, "no overlapping time slot"
        return ALLOW, None
    # fallback (демо-пул без окон): флаг open
    if bool(iwin) and c.get("open") is False:
        return BLOCK, "no overlapping time slot"
    return ALLOW, None


def location_policy(intent, c, ctx):
    # зона допустима без раскрытия точного адреса; вне радиуса -> REVIEW или расширение зоны (не hard BLOCK)
    if intent.get("mode") == "offline" and intent.get("radiusKm") and c.get("km") is not None:
        try:
            if float(c["km"]) > float(intent["radiusKm"]):
                return (REVIEW, "outside radius (zone expansion)") if intent.get("zoneOptIn") \
                    else (BLOCK, "outside the radius")
        except (TypeError, ValueError):
            pass
    return ALLOW, None


def capacity(intent, c, ctx):
    cap = c.get("capacity")
    if isinstance(cap, dict):
        if int(cap.get("current", 0)) >= int(cap.get("max", 10 ** 9)):
            return BLOCK, "capacity full"
    if (c.get("pending") or 0) >= 6:
        return BLOCK, "too many open invites"
    return ALLOW, None


def fatigue_readiness(intent, c, ctx):
    # BLOCK для outreach, НЕ обязательно для passive discovery (§8.1)
    nm = str(c.get("name", "")).strip().lower()
    received = (ctx.get("received24") or {}).get(nm, 0)
    budget = ((c.get("receiving") or {}).get("proposal_budget") or {}).get("per_24h", 4)
    if intent.get("_for_outreach") and received >= int(budget):
        return BLOCK, "receiver overloaded (fatigue)"
    return ALLOW, None


def disclosure_policy(intent, c, ctx):
    # предложение не должно раскрывать запрещённые поля; здесь — REVIEW при sensitivity restricted domain
    dom_cfg = ctx.get("domain_cfg") or {}
    if dom_cfg.get("release_gate") and not c.get("verified"):
        return REVIEW, "%s: separate safety/legal track (unverified)" % (intent.get("type") or "domain")
    return ALLOW, None


# Канонический ПОРЯДОК гейтов (§8: hard/safety раньше; scoring только после ALLOW).
CANONICAL_GATES = (
    account_status, mutual_block, safety_restrictions, privacy_visibility, age_legal,
    intent_mode_isolation, language_feasibility, time_feasibility, location_policy,
    capacity, fatigue_readiness, disclosure_policy,
)
