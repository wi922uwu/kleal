# -*- coding: utf-8 -*-
"""§15.1 Set-level constraints — группа проверяется как МНОЖЕСТВО.

Любое нарушение hard set constraint делает группу недопустимой независимо от pair scores (§15.2,
C#18: 4 одинаковых role/side отклоняются даже при высоких pair scores; C#19: pairwise block отклоняет).
"""


# §15 supported_size_max_mvp, in seats. Kept in step with services/matching/kleal_groups.py
# and the sha-pinned config; an 8 here silently capped every larger company.
MAX_MVP_SIZE = 12

def _intersect_windows(members):
    """Общее временное окно (минуты) как пересечение окон всех участников. 0 — если пересечения нет."""
    per_member = []
    for m in members:
        wins = m.get("time_windows") or []
        ints = [(_min(w[0]), _min(w[1])) for w in wins if len(w) == 2]
        per_member.append([iv for iv in ints if iv[0] is not None and iv[1] is not None and iv[1] > iv[0]])
    if not per_member or any(not p for p in per_member):
        return 0
    # пересечение: начинаем с окон первого, последовательно пересекаем
    cur = per_member[0]
    for nxt in per_member[1:]:
        new = []
        for a in cur:
            for b in nxt:
                lo, hi = max(a[0], b[0]), min(a[1], b[1])
                if hi > lo:
                    new.append((lo, hi))
        cur = new
        if not cur:
            return 0
    return max((hi - lo) for lo, hi in cur)


def _min(hhmm):
    try:
        h, m = str(hhmm).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def check_set_constraints(members, constraints, pair_blocks=None):
    """Возвращает (feasible, violations[]). Коды нарушений типизированы."""
    v = []
    n = len(members)
    smin, smax = int(constraints.get("size_min", 3)), int(constraints.get("size_max", MAX_MVP_SIZE))
    if n < smin:
        v.append("below_size_min")
    if n > smax:
        v.append("above_size_max")
    if n < int(constraints.get("min_quorum", smin)):
        v.append("below_quorum")

    # pairwise blocks / safety exclusions (C#19)
    blocks = {tuple(sorted((str(a).lower(), str(b).lower()))) for a, b in (pair_blocks or constraints.get("pair_blocks") or [])}
    ids = [str(m.get("id") or m.get("name", "")).lower() for m in members]
    for i in range(n):
        for j in range(i + 1, n):
            if tuple(sorted((ids[i], ids[j]))) in blocks:
                v.append("pairwise_block")
                break

    # role/side distribution (C#18): точные требуемые count по ролям/сторонам
    dist = constraints.get("role_distribution")
    if dist:
        have = {}
        for m in members:
            for r in (m.get("roles") or ([m.get("side")] if m.get("side") else [])):
                have[str(r).lower()] = have.get(str(r).lower(), 0) + 1
        for role, need in dist.items():
            if have.get(str(role).lower(), 0) != int(need):
                v.append("role_distribution:%s" % role)

    # required roles (покрытие)
    req = constraints.get("required_roles")
    if req:
        covered = set()
        for m in members:
            covered |= {str(r).lower() for r in (m.get("roles") or [])}
        for r in req:
            if str(r).lower() not in covered:
                v.append("missing_role:%s" % r)

    # time overlap достаточной длительности
    min_win = int(constraints.get("min_common_window_min", 0))
    if min_win and _intersect_windows(members) < min_win:
        v.append("insufficient_time_overlap")

    # language coverage
    lang_req = constraints.get("languages_required")
    if lang_req:
        for lg in lang_req:
            if not any(lg in (m.get("langs") or []) for m in members):
                v.append("missing_language:%s" % lg)

    # skill spread
    spread_max = constraints.get("skill_spread_max")
    if spread_max is not None:
        skills = [m.get("skill") for m in members if isinstance(m.get("skill"), (int, float))]
        if skills and (max(skills) - min(skills)) > spread_max:
            v.append("skill_spread_exceeded")

    return (len(v) == 0, v)


def common_window_min(members):
    return _intersect_windows(members)
