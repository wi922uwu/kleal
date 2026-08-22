# -*- coding: utf-8 -*-
"""§15.3 MVP algorithm + Приложение B.3 — формирование допустимой группы.

seed candidates -> feasible pools по hard constraints -> greedy marginal add -> local repair -> reserve.
Группа оценивается как множество (utility, §15.2), НЕ средним пар. Возвращает лучшую ДОПУСТИМУЮ группу
(с reservations) или None (пул не даёт допустимого множества — C#18/#19).
"""
from . import constraints as C
from . import utility as U
from ..contracts import reservation as RSV


def _mid(m):
    return str(m.get("id") or m.get("name", ""))


def _build_score(members, pair_rel, gc, weights):
    """Скор для построения: utility, если множество допустимо; иначе partial-эвристика (ведёт к feasibility)."""
    feasible, viol = C.check_set_constraints(members, gc)
    if feasible:
        return U.group_utility(members, pair_rel, gc, weights) or 0.0
    if len(members) < 2:
        return 0.0
    pairs = U._directed_pairs(members, pair_rel)
    mean_pair = sum(p[2] for p in pairs) / len(pairs) if pairs else 0.0
    return mean_pair - 0.25 * len(viol)                 # штраф за нарушения


def greedy_marginal_add(seed, feasible, pair_rel, gc, weights):
    """Жадно добавлять кандидата с макс. marginal gain, пока не size_max / нет улучшения при feasible."""
    group = list(seed)
    used = {_mid(m) for m in group}
    smax = int(gc.get("size_max", C.MAX_MVP_SIZE))
    while len(group) < smax:
        best, best_gain = None, 1e-9
        base = _build_score(group, pair_rel, gc, weights)
        for c in feasible:
            if _mid(c) in used:
                continue
            gain = _build_score(group + [c], pair_rel, gc, weights) - base
            # ниже size_min принимаем даже небольшой прогресс к feasibility
            if gain > best_gain or (len(group) < int(gc.get("size_min", 3)) and gain >= best_gain):
                best, best_gain = c, gain
        if best is None:
            break
        group.append(best)
        used.add(_mid(best))
        # остановиться, если уже feasible и добавление больше не улучшает
        if len(group) >= int(gc.get("size_min", 3)) and C.check_set_constraints(group, gc)[0] and best_gain <= 0:
            group.pop()
            break
    return group


def local_repair(group, feasible, pair_rel, gc, weights):
    """swap/remove/add для ролей и least-misery. Пытается заменить худшего (по least-misery) участника."""
    feasible_ok, _ = C.check_set_constraints(group, gc)
    if feasible_ok:
        return group
    used = {_mid(m) for m in group}
    best = group
    best_score = _build_score(group, pair_rel, gc, weights)
    for i in range(len(group)):
        for c in feasible:
            if _mid(c) in used:
                continue
            cand = group[:i] + [c] + group[i + 1:]
            sc = _build_score(cand, pair_rel, gc, weights)
            if sc > best_score:
                best, best_score = cand, sc
    return best


def _seeds(feasible, gc):
    """Role-complete seeds: если задан role_distribution — по одному кандидату на каждую роль/сторону.
    Иначе — синглтоны (детерминированно по id)."""
    feasible = sorted(feasible, key=_mid)
    dist = gc.get("role_distribution") or gc.get("required_roles")
    if not dist:
        return [[m] for m in feasible[:8]]
    seeds, roles = [], list(dist.keys() if isinstance(dist, dict) else dist)
    by_role = {}
    for m in feasible:
        for r in (m.get("roles") or ([m.get("side")] if m.get("side") else [])):
            by_role.setdefault(str(r).lower(), []).append(m)
    # один seed: первый доступный кандидат каждой требуемой роли
    seed = []
    for r in roles:
        cands = by_role.get(str(r).lower(), [])
        if cands:
            seed.append(cands[0])
    if seed:
        seeds.append(seed)
    seeds.extend([[m] for m in feasible[:4]])
    return seeds


def form_group(intent, candidates, group_constraints, pair_rel, cfg=None, now=0.0):
    """B.3. Возвращает {group, utility, members, reservations} для лучшей допустимой группы, иначе None."""
    weights = U.load_weights(cfg)
    gc = group_constraints
    # feasible pool: кандидаты без индивидуальных safety/eligibility блоков (передаются pre-gated)
    feasible = [c for c in candidates if not c.get("blocked")]
    best_group, best_util = None, -1.0
    for seed in _seeds(feasible, gc):
        g = greedy_marginal_add(seed, feasible, pair_rel, gc, weights)
        g = local_repair(g, feasible, pair_rel, gc, weights)
        if C.check_set_constraints(g, gc)[0]:
            u = U.group_utility(g, pair_rel, gc, weights)
            if u is not None and u > best_util:
                best_group, best_util = g, u
    if best_group is None:
        return None
    reservations = [RSV.build_reservation("resv:%s" % _mid(m), "group_slot", _mid(m), created_at=now)
                    for m in best_group]
    return {"group": best_group, "utility": best_util,
            "members": [_mid(m) for m in best_group], "reservations": reservations}
