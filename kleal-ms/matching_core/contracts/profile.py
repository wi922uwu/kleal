# -*- coding: utf-8 -*-
"""§4 UserProfile + ProfileView; §8.3 + Приложение D — purpose binding.

Matching Core работает не с «большим профилем», а с purpose-bound минимальными представлениями.
Поле, разрешённое для одного режима, НЕ становится доступным в другом (§23.2 п.9, C#12). Точная live
location НИКОГДА не попадает в view (§8.4, C#14) — только coarse.
"""

PURPOSES = ("friendship", "dating", "networking", "language", "games", "sport")

# Приложение D — что делать с полем в каждом режиме. Трансформы:
#   drop   — поле НЕ входит в view для этого purpose
#   full   — как есть (по disclosure)
#   band   — возраст → диапазон
#   age_by_consent — точный возраст только при consent_exact_age, иначе band
#   coarse — только грубая зона (никогда точная координата)
#   confirmed_dating — только подтверждённые dating-relevant интересы
_MATRIX = {
    "name":        {"friendship": "full", "dating": "staged", "networking": "full", "language": "full", "games": "full", "sport": "full"},
    "avatar":      {"friendship": "full", "dating": "staged", "networking": "full", "language": "full", "games": "full", "sport": "full"},
    "age":         {"friendship": "band", "dating": "age_by_consent", "networking": "drop", "language": "drop", "games": "band", "sport": "band"},
    "gender":      {"friendship": "drop", "dating": "full", "networking": "drop", "language": "drop", "games": "drop", "sport": "drop"},
    "orientation": {"friendship": "drop", "dating": "full", "networking": "drop", "language": "drop", "games": "drop", "sport": "drop"},
    "profession":  {"friendship": "full", "dating": "drop", "networking": "full", "language": "full", "games": "drop", "sport": "drop"},
    "languages":   {"friendship": "full", "dating": "full", "networking": "full", "language": "full", "games": "full", "sport": "full"},
    "interests":   {"friendship": "full", "dating": "confirmed_dating", "networking": "full", "language": "full", "games": "full", "sport": "full"},
    "availability": {"friendship": "full", "dating": "full", "networking": "full", "language": "full", "games": "full", "sport": "full"},
    "location":    {"friendship": "coarse", "dating": "coarse", "networking": "coarse", "language": "coarse", "games": "coarse", "sport": "coarse"},
    "behavioral_reliability": {"friendship": "full", "dating": "full", "networking": "full", "language": "full", "games": "full", "sport": "full"},
    "inferred_memory": {"friendship": "full", "dating": "drop", "networking": "full", "language": "full", "games": "full", "sport": "full"},
    "dating_preferences": {"friendship": "drop", "dating": "full", "networking": "drop", "language": "drop", "games": "drop", "sport": "drop"},
}

_AGE_BANDS = ((18, 24), (25, 34), (35, 44), (45, 54), (55, 64), (65, 200))


def age_band(age):
    try:
        a = int(age)
    except (TypeError, ValueError):
        return None
    for lo, hi in _AGE_BANDS:
        if lo <= a <= hi:
            return "%d-%d" % (lo, hi) if hi < 200 else "%d+" % lo
    return None


def build_user_profile(user_id, **fields):
    """Базовые явные факты (§4). Хранит и точную геолокацию, и coarse — но точную НИКОГДА не отдаёт наружу."""
    p = {"user_id": user_id, "profile_version": int(fields.get("profile_version", 1))}
    for k in ("name", "avatar", "age", "gender", "orientation", "profession", "languages", "interests",
              "availability", "behavioral_reliability", "inferred_memory", "dating_preferences",
              "verified", "city", "dating_optin", "target_preferences_confirmed"):
        if k in fields:
            p[k] = fields[k]
    # геолокация: exact_lat/exact_lon (внутренние, наружу нельзя) + coarse_area/coarse_lat/coarse_lon
    p["geo"] = fields.get("geo") or {}
    return p


def _coarse_location(user):
    """§8.4 / C#14: ТОЛЬКО грубая зона. Точные exact_lat/exact_lon исключаются из view физически."""
    g = user.get("geo") or {}
    out = {}
    for k in ("coarse_area", "coarse_lat", "coarse_lon", "h3_cell", "city"):
        if g.get(k) is not None:
            out[k] = g[k]
    if not out and user.get("city"):
        out["city"] = user["city"]
    return out or None


def build_profile_view(user, purpose, disclosure_stage="limited_profile", now=None, consents=None):
    """§4/§8.3 purpose-bound view. Возвращает ТОЛЬКО поля, разрешённые матрицей Приложения D, с
    коарсенингом. Гарантии: exact location отсутствует (C#14); dating-поля отсутствуют вне dating (C#12)."""
    if purpose not in PURPOSES:
        raise ValueError("unknown purpose: %r" % purpose)
    consents = consents or {}
    fields, dropped = {}, []
    for field, rule_by_purpose in _MATRIX.items():
        rule = rule_by_purpose.get(purpose, "drop")
        val = user.get(field)
        if rule == "drop" or val is None and field not in ("location", "age"):
            if rule == "drop":
                dropped.append(field)
            continue
        if field == "location":
            loc = _coarse_location(user)
            if loc:
                fields["location"] = loc
            continue
        if rule == "band":
            b = age_band(user.get("age"))
            if b:
                fields["age_band"] = b
        elif rule == "age_by_consent":
            if consents.get("consent_exact_age") and user.get("age") is not None:
                fields["age"] = user.get("age")
            else:
                b = age_band(user.get("age"))
                if b:
                    fields["age_band"] = b
        elif rule == "confirmed_dating":
            di = [i for i in (val or []) if isinstance(i, dict) and i.get("dating_relevant")] \
                 or (val if consents.get("consent_share_interests") else [])
            if di:
                fields["interests"] = di
        elif rule == "staged":
            # staged disclosure: показываем на поздней стадии
            if disclosure_stage in ("full_profile", "match"):
                fields[field] = val
            else:
                dropped.append(field)
        else:  # full / coarse handled above
            if val is not None:
                fields[field] = val
    return {
        "purpose": purpose, "purpose_id": None, "disclosure_stage": disclosure_stage,
        "fields": fields, "_dropped": sorted(set(dropped)),
        "profile_version": user.get("profile_version"),
        "_no_exact_location": True,  # инвариант C#14
    }
