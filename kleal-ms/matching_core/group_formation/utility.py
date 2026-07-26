# -*- coding: utf-8 -*-
"""§15.2 Group utility — группа оценивается как МНОЖЕСТВО, НЕ как среднее парных совпадений (§23.2 п.8).

GroupUtility(G) = 0.35·least_misery + 0.25·mean_pair_fit + 0.20·role_coverage + 0.10·time_overlap
                 + 0.10·diversity_value.
least_misery — минимальная направленная удовлетворённость (защита от «среднее высокое, но один участник
явно неподходящий»). Если нарушен ЛЮБОЙ hard set constraint — группа недопустима (utility = None).
Веса из sha-pinned config group_formation.utility_weights (§9.5, единый источник).
"""
from . import constraints as C

DEFAULT_WEIGHTS = {"least_misery": 0.35, "mean_member_relevance": 0.25, "role_coverage": 0.20,
                   "time_overlap": 0.10, "diversity_budget": 0.10}


def load_weights(cfg):
    return (cfg or {}).get("group_formation", {}).get("utility_weights") or DEFAULT_WEIGHTS


def _directed_pairs(members, pair_rel):
    ids = [str(m.get("id") or m.get("name", "")) for m in members]
    pairs = []
    for i, a in enumerate(members):
        for j, b in enumerate(members):
            if i != j:
                pairs.append((ids[i], ids[j], float(pair_rel(a, b))))
    return pairs


def least_misery(members, pair_rel):
    """min по участникам от (min его направленной удовлетворённости остальными)."""
    if len(members) < 2:
        return 0.0
    worst = 1.0
    for i, a in enumerate(members):
        sats = [float(pair_rel(a, b)) for j, b in enumerate(members) if i != j]
        if sats:
            worst = min(worst, min(sats))
    return worst


def group_utility(members, pair_rel, constraints, weights=None, group_constraints=None):
    """Возвращает utility 0..1 для ДОПУСТИМОГО множества, иначе None (§15.2)."""
    gc = group_constraints or constraints
    feasible, _viol = C.check_set_constraints(members, gc)
    if not feasible:
        return None
    w = weights or DEFAULT_WEIGHTS
    lm = least_misery(members, pair_rel)
    pairs = _directed_pairs(members, pair_rel)
    mean_pair = sum(p[2] for p in pairs) / len(pairs) if pairs else 0.0
    # role coverage
    req = gc.get("required_roles") or gc.get("role_distribution") or {}
    if req:
        covered = set()
        for m in members:
            covered |= {str(r).lower() for r in (m.get("roles") or ([m.get("side")] if m.get("side") else []))}
        role_cov = sum(1 for r in req if str(r).lower() in covered) / len(req)
    else:
        role_cov = 1.0
    # time overlap normalized
    want = int(gc.get("min_common_window_min", 60)) or 60
    time_ov = min(1.0, C.common_window_min(members) / want) if want else 1.0
    # diversity: доля уникальных бакетов
    buckets = [m.get("bucket") for m in members if m.get("bucket") is not None]
    diversity = (len(set(buckets)) / len(members)) if members and buckets else 0.5
    u = (w["least_misery"] * lm + w["mean_member_relevance"] * mean_pair +
         w["role_coverage"] * role_cov + w["time_overlap"] * time_ov +
         w["diversity_budget"] * diversity)
    return round(u, 4)
