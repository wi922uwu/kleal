# -*- coding: utf-8 -*-
"""§5.2 Операционализированная clarification policy.

Класс вопроса: P0 mandatory (без ответа нельзя безопасно/корректно определить eligibility) · P1 high
value (>30% pool / новый tier / предотвращает провал) · P2 ranking only · P3 cosmetic. В MVP вопрос
выбирается RULE-BASED (не формулой EVI) из 4 ordinal факторов (safety, pool-split, supply-unlock,
user-control) минус friction. Не более ОДНОГО вопроса до первых результатов, кроме mandatory safety.
"""

# действие при отказе пользователя ответить (§5.2).
CLASS_ACTION = {
    "P0": "block_sensitive_flow_offer_safe_alternative",
    "P1": "search_with_unknown_lower_confidence",
    "P2": "dont_ask_before_results",
    "P3": "dont_ask",
}

# Каталог известных вопросов: класс + ordinal факторы (0..3) + friction (0..3).
QUESTION_CATALOG = {
    "dating_optin":       {"klass": "P0", "safety": 3, "pool": 2, "supply": 0, "control": 3, "friction": 1},
    "platform_crossplay": {"klass": "P0", "safety": 1, "pool": 3, "supply": 1, "control": 2, "friction": 1},
    "required_language":  {"klass": "P0", "safety": 1, "pool": 3, "supply": 1, "control": 3, "friction": 1},
    "time_window":        {"klass": "P1", "safety": 0, "pool": 3, "supply": 2, "control": 2, "friction": 1},
    "area":               {"klass": "P1", "safety": 1, "pool": 3, "supply": 2, "control": 2, "friction": 1},
    "format_1to1_group":  {"klass": "P1", "safety": 0, "pool": 2, "supply": 1, "control": 3, "friction": 1},
    "native_vs_samelevel": {"klass": "P1", "safety": 0, "pool": 2, "supply": 1, "control": 2, "friction": 1},
    "exact_topic":        {"klass": "P2", "safety": 0, "pool": 1, "supply": 0, "control": 1, "friction": 1},
    "card_name":          {"klass": "P3", "safety": 0, "pool": 0, "supply": 0, "control": 0, "friction": 2},
}


def priority(q):
    """Rule-based приоритет из ordinal факторов; safety весит сильнее (§5.2)."""
    return 2 * q["safety"] + q["pool"] + q["supply"] + q["control"] - q["friction"]


def classify(question_key):
    q = QUESTION_CATALOG.get(question_key)
    if not q:
        return None
    return {"key": question_key, "klass": q["klass"], "priority": priority(q),
            "action_on_refusal": CLASS_ACTION[q["klass"]]}


# ---------------- §5.2 из КАНОНИЧЕСКИХ слотов (Kleal_Global_Context_Profiles_Intent_Taxonomy) ----------------
def slots_catalog(domain):
    """Каталог уточнений из канонических доменных слотов: importance(hard/soft/policy) +
    unknown_behavior -> класс P0/P1/P2 + реальный вопрос RU. Возвращает [{slot,klass,unknown,op,question}]."""
    from ..taxonomy import canonical as CANON
    out = []
    for s in CANON.slots_for_domain(domain):
        imp, unk = s.get("imp"), s.get("unknown")
        if imp == "policy":
            klass = "P0"
        elif imp == "hard":
            klass = "P0" if unk in ("ask", "reject_if_false", "ask_if_required") else "P1"
        else:
            klass = "P2"
        out.append({"slot": s.get("slot"), "klass": klass, "importance": imp,
                    "unknown_behavior": unk, "compare_operator": s.get("op"), "question": s.get("q")})
    return out


def select_slot_question(domain, missing_slot_names, *, before_results=True):
    """§5.2 rule-based выбор ≤1 вопроса из канонических слотов домена (P0 mandatory поверх P1;
    P2/P3 не до результатов). Возвращает spec слота или None."""
    cat = {c["slot"]: c for c in slots_catalog(domain)}
    specs = [cat[s] for s in missing_slot_names if s in cat]
    p0 = [s for s in specs if s["klass"] == "P0"]
    if p0:
        return p0[0]
    if before_results:
        p1 = [s for s in specs if s["klass"] == "P1"]
        return p1[0] if p1 else None
    p12 = [s for s in specs if s["klass"] in ("P1", "P2")]
    return p12[0] if p12 else None


def select_question(missing_keys, *, before_results=True):
    """Выбрать ≤1 вопрос. Если есть mandatory P0 — задаём его (safety не подчиняется лимиту одного вопроса).
    Иначе лучший P1. До результатов P2/P3 не спрашиваем (§5.2). Возвращает spec или None."""
    specs = [classify(k) for k in missing_keys]
    specs = [s for s in specs if s]
    p0 = [s for s in specs if s["klass"] == "P0"]
    if p0:
        return max(p0, key=lambda s: s["priority"])
    if before_results:
        p1 = [s for s in specs if s["klass"] == "P1"]
        return max(p1, key=lambda s: s["priority"]) if p1 else None
    p12 = [s for s in specs if s["klass"] in ("P1", "P2")]
    return max(p12, key=lambda s: s["priority"]) if p12 else None
