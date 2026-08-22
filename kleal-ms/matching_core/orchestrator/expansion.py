# -*- coding: utf-8 -*-
"""§12 Controlled expansion и гарантия полезного ответа.

Цель fallback — не выдать случайного человека любой ценой, а обеспечить полезный следующий шаг. За один
шаг ослабляется ТОЛЬКО одна ось (§12.1), сначала дешёвый soft; safety/age/consent/block/critical language/
purpose isolation НИКОГДА не ослабляются; provenance tier сохраняется; компромисс объясняется.
"""
import copy

# ОСИ, которые НИКОГДА не ослабляются (§12.1, §23.2 п.4/9).
FORBIDDEN_AXES = frozenset({"safety", "age", "mutual_consent", "block", "critical_language", "purpose_isolation"})

# Вердикт#9: expansion_policy на самом intent — что вообще допустимо расширять. Порядок = возрастание свободы.
EXPANSION_POLICIES = ("exact_only", "allow_family", "allow_adjacent_after_confirmation", "event_fallback_allowed")
# какие оси лестницы разрешает каждая политика (event/saved_search — безопасный хвост, всегда допустимы).
_POLICY_AXES = {
    "exact_only":                        {"exact"},
    "allow_family":                      {"exact", "sibling", "parent"},
    "allow_adjacent_after_confirmation": {"exact", "sibling", "parent", "time_distance", "format"},
    "event_fallback_allowed":            {"exact", "sibling", "parent", "time_distance", "format", "alternative_type"},
}


def expansion_policy(intent):
    """Вердикт#9: политика расширения интента. Явно заданная — honor'ится строго. Если не задана —
    ВЫВОДИТСЯ из уже данного согласия: явные fallback-оси (time/distance/format) = согласие на adjacent;
    иначе консервативный allow_family (без молчаливого adjacent-расширения)."""
    p = (intent.get("expansion_policy") or (intent.get("fallback") or {}).get("expansion_policy"))
    if p in EXPANSION_POLICIES:
        return p
    fb = intent.get("fallback") or {}
    dims = set(fb.get("allowed_dimensions") or [])
    if dims & {"time", "distance", "format"}:
        return "allow_adjacent_after_confirmation"    # пользователь явно разрешил оси fallback
    return "allow_family"                             # консервативный дефолт (silent adjacent запрещён)


def policy_allows_axis(intent, axis):
    """Вердикт#9: ось разрешена самой политикой интента (до вопроса consent). saved_search разрешён всегда."""
    if axis == "saved_search":
        return True
    return axis in _POLICY_AXES.get(expansion_policy(intent), set())

# §12.2 типовой порядок расширения: (axis, требует ли consent, объяснение).
EXPANSION_LADDER = [
    ("exact",           False, "точное совпадение сущности/роли, то же время и зона"),
    ("sibling",         False, "близкая родственная сущность"),
    ("parent",          "broad_consent", "родительская категория активности"),
    ("time_distance",   "fallback_consent", "чуть шире по времени или расстоянию (в пределах согласия)"),
    ("format",          "fallback_consent", "другой формат: 1:1 → small group или offline → online"),
    ("alternative_type", False, "событие/комната/группа как альтернативный способ закрыть запрос"),
    ("saved_search",    False, "сохранить поиск и уведомить позже"),
]


def _consent_ok(intent, requirement):
    if requirement is False:
        return True
    consents = (intent.get("fallback") or {}).get("consent") or {}
    dims = (intent.get("fallback") or {}).get("allowed_dimensions") or []
    if requirement == "broad_consent":
        return bool(consents.get("broad_matching"))
    if requirement == "fallback_consent":
        return bool(dims)                          # пользователь разрешил какие-то оси fallback
    return False


def allowed(intent, axis):
    """§12.1 + Вердикт#9: ось разрешена, если не forbidden И политика интента её допускает И
    (не требует consent, либо consent есть)."""
    if axis in FORBIDDEN_AXES:
        return False
    if not policy_allows_axis(intent, axis):
        return False                               # expansion_policy интента не разрешает эту ось
    for a, req, _ in EXPANSION_LADDER:
        if a == axis:
            return _consent_ok(intent, req)
    return False


def _relax(intent, axis):
    """Применить ослабление одной оси. Возвращает новый intent (provenance tier сохраняется вызывающим)."""
    it = copy.deepcopy(intent)
    if axis == "sibling":
        it["adjacentAllowed"] = True
    elif axis == "parent":
        it["broadAllowed"] = True
    elif axis == "time_distance":
        if it.get("radiusKm"):
            it["radiusKm"] = float(it["radiusKm"]) * 1.5
        it["_time_relaxed"] = True
    elif axis == "format":
        if it.get("mode") == "offline":
            it["mode"] = "online"
        it["format"] = "small_group"
    elif axis == "alternative_type":
        it["_allow_alt_types"] = True             # event/room/group (T4)
    elif axis == "saved_search":
        it["_saved_search"] = True
    return it


def expand_step(intent, step_index):
    """Один шаг лестницы (§12.2). Возвращает {axis, intent, explanation, tier_note, discovery_only} или
    None (лестница исчерпана / ось запрещена без consent)."""
    if step_index >= len(EXPANSION_LADDER):
        return None
    axis, req, expl = EXPANSION_LADDER[step_index]
    if not policy_allows_axis(intent, axis):
        return None                               # Вердикт#9: expansion_policy интента запрещает эту ось
    if not allowed(intent, axis) and axis not in ("exact", "sibling", "saved_search", "alternative_type"):
        return None                               # нет согласия на consent-gated ось
    relaxed = _relax(intent, axis)
    # §12.1: personal outreach в parent tier требует broad consent; adjacent -> discovery, не в inbox
    discovery_only = axis in ("parent", "alternative_type") and not _consent_ok(intent, "broad_consent")
    return {"axis": axis, "intent": relaxed, "explanation": expl,
            "tier_note": "provenance tier сохранён", "discovery_only": discovery_only}


def expand_until_useful(intent, has_results_fn, max_steps=None):
    """§12: расширять по одной оси, пока не появится полезный результат или лестница не исчерпана.
    has_results_fn(relaxed_intent) -> bool. Возвращает (relaxed_intent, trail[])."""
    trail = []
    cur = intent
    steps = len(EXPANSION_LADDER) if max_steps is None else min(max_steps, len(EXPANSION_LADDER))
    for i in range(steps):
        step = expand_step(cur, i)
        if step is None:
            continue
        trail.append({"axis": step["axis"], "explanation": step["explanation"], "discovery_only": step["discovery_only"]})
        cur = step["intent"]
        if has_results_fn(cur):
            break
    return cur, trail


# ---------------- Вердикт#1: тематического пересечения нет -> НЕ персональная выдача T5 ----------------
# Последовательность безопасных шагов вместо «подсунуть ближайшего человека» (fallback T5 запрещён).
NO_MATCH_LADDER = ("offer_expansion_consent", "relevant_event_group_room", "background_search",
                   "offer_create_open_intent", "honest_no_result")


def nearby_open_block(nearby_people):
    """Вердикт#1: допустим ОТДЕЛЬНЫЙ блок «люди поблизости, открытые к другим планам», но он явно отделён
    от результатов по intent, и личное приглашение из него ЗАПРЕЩЕНО без нового подтверждения пользователя."""
    names = [str(p.get("name") if isinstance(p, dict) else p) for p in (nearby_people or [])]
    if not names:
        return None
    return {"title_ru": "Люди поблизости, открытые к другим планам",
            "title_en": "People nearby, open to other plans",
            "members": names,
            "separated_from_intent_results": True,   # НЕ в основном слейте по текущему intent
            "personal_invite_allowed": False,        # из этого блока нельзя слать личное приглашение…
            "requires_new_confirmation": True}       # …без нового явного подтверждения пользователя


def no_topical_overlap_response(intent, *, has_alt_types=False, nearby_open=None):
    """Вердикт#1: если тематического основания нет — вернуть последовательность полезных шагов, а НЕ
    случайного ближайшего человека как персональную рекомендацию. personal_outreach жёстко False."""
    steps = []
    # 1. предложить расширение (не молча) — только если политика интента это вообще допускает
    if expansion_policy(intent) != "exact_only":
        steps.append("offer_expansion_consent")
    # 2. релевантное событие/группа/комната (T4) — если доступны и политика разрешает event_fallback
    if has_alt_types and policy_allows_axis(intent, "alternative_type"):
        steps.append("relevant_event_group_room")
    # 3-5. фоновый поиск -> открытый intent -> честный no-result
    steps += ["background_search", "offer_create_open_intent", "honest_no_result"]
    return {"personal_outreach": False, "steps": steps,
            "nearby_open_block": nearby_open_block(nearby_open)}
