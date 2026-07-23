# -*- coding: utf-8 -*-
"""§7 Candidate retrieval и semantic tiers.

Semantic tier — IMMUTABLE provenance кандидата в конкретном search run (§7.1). Сильная логистика НЕ
переводит parent candidate в direct tier (C#4). Tier назначается из ПРОИСХОЖДЕНИЯ (совпадение
темы/взаимность/тип кандидата), НЕ из score (§23.2 п.2).
"""
from ..taxonomy import graph as TX

# §7.1 пять источников (порядок = приоритет).
SOURCES = {
    1: "active_intent_match",
    2: "active_receiving_direct_interest",
    3: "groups_with_capacity",
    4: "events_and_rooms",
    5: "parent_adjacent_expansion",
}

# §7.2 retrieval budgets (этапы; ANN — infra, помечено отдельно).
BUDGET_STAGES = {
    "hard_prefilter": 250, "structured_retrieval": 80, "ann_recall": 50,
    "feature_build": 30, "ranking_slate": 8,
}

# UX + personal_outreach по tier (§7.1 таблица).
TIER_UX = {
    "T0": ("exact active intent", True),
    "T1": ("direct interest", True),
    "T2": ("parent category", "broad_consent"),
    "T3": ("adjacent context", False),
    "T4": ("alternative solution", False),
    "T5": ("no overlap", False),
}


def reciprocal(intent, cand):
    """Собственный активный intent кандидата делит реальный topical-интерес (sub/exact, best>=3)."""
    itop = [str(t).lower() for t in (intent.get("topics") or [])]
    for oi in (cand.get("intents") or []):
        if TX.similarity(itop, [str(t).lower() for t in (oi.get("topics") or [])])[0] >= 3:
            return True
    return False


def assign_tier(intent, cand):
    """Immutable provenance-tier (§7.1). НЕ зависит от score/времени/логистики (C#4)."""
    kind = str(cand.get("kind") or "person").lower()
    if kind in ("event", "room", "venue", "group"):
        return "T4"                                       # альтернативный тип решения
    topics = [str(t).lower() for t in (intent.get("topics") or [])]
    best = TX.similarity(topics, [str(x).lower() for x in (cand.get("interests") or [])])[0]
    if reciprocal(intent, cand) and best >= 4:
        return "T0"                                       # почти такой же активный запрос
    if best >= 4:
        return "T1"                                       # прямой интерес
    if best in (2, 3):
        return "T2"                                       # родительская категория
    if best == 1:
        return "T3"                                       # смежный контекст
    return "T5"                                           # нет overlap


def source_of(intent, cand, tier):
    if tier == "T4":
        return 4
    if tier == "T0":
        return 1
    if tier == "T1":
        return 2 if (cand.get("receiving") or cand.get("open")) else 1
    return 5                                              # parent/adjacent expansion


_SOURCE_RANK = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4}


def retrieve(intent, pool, *, budget=80, allowed_tiers=("T0", "T1", "T2", "T3", "T4")):
    """Помечает кандидатов source + IMMUTABLE tier, фильтрует по allowed_tiers, сортирует по приоритету
    источника, режет бюджетом. Возвращает список dict-обёрток {cand, tier, source, best}.
    Обрезка режет только no-overlap хвост (T5 не входит в allowed_tiers), поэтому slate стабилен."""
    labeled = []
    for c in pool:
        tier = assign_tier(intent, c)
        if tier not in allowed_tiers:
            continue                                      # T5 (или запрещённый tier) не показывается
        src = source_of(intent, c, tier)
        best = TX.similarity([str(t).lower() for t in (intent.get("topics") or [])],
                             [str(x).lower() for x in (c.get("interests") or [])])[0]
        labeled.append({"cand": c, "tier": tier, "source": src, "best": best})
    labeled.sort(key=lambda r: (_SOURCE_RANK.get(r["source"], 9), -r["best"],
                                str(r["cand"].get("name", ""))))
    return labeled[:max(0, int(budget))]


def retrieve_staged(intent, pool, *, budget=80, allowed_tiers=("T0", "T1", "T2", "T3", "T4"), prefilter=None):
    """§7.2 явный 5-стадийный funnel с counts на каждом этапе. ann_recall — DECLARED no-op в stdlib-
    прототипе (pgvector/embeddings = infra, отсутствуют). Возвращает (labeled, stage_stats)."""
    n0 = len(pool)
    pre = [c for c in pool if (prefilter is None or prefilter(c))]        # 1. hard_prefilter
    labeled = retrieve(intent, pre, budget=budget, allowed_tiers=allowed_tiers)   # 2. structured_retrieval
    stats = {"input": n0, "hard_prefilter": len(pre), "structured_retrieval": len(labeled),
             "ann_recall": {"added": 0, "status": "no_op_stdlib"},          # 3. ANN — no-op
             "feature_build": "downstream", "ranking_slate": "downstream"}  # 4-5. вниз по пайплайну
    return labeled, stats


def tier_analytics(items, *, tier_key="tier", lcb_key="lcb", cov_key="coverage"):
    """§7.1: распределение relevance ОТДЕЛЬНО внутри каждого semantic tier (tier immutable; аналитика НЕ
    промоутит tier). items — scored-элементы. Возвращает {tier: {count, mean_lcb, mean_coverage}}."""
    by = {}
    for it in items:
        t = it.get(tier_key)
        b = by.setdefault(t, {"count": 0, "lcb": 0.0, "cov": 0.0})
        b["count"] += 1
        b["lcb"] += float(it.get(lcb_key) or 0)
        b["cov"] += float(it.get(cov_key) or 0)
    return {t: {"count": v["count"], "mean_lcb": round(v["lcb"] / v["count"], 4),
                "mean_coverage": round(v["cov"] / v["count"], 4)} for t, v in by.items() if v["count"]}
