# -*- coding: utf-8 -*-
"""§4 Group — набор участников и set-level ограничения (полная логика формирования — §15).

Здесь контракт: quorum, roles, pairwise blocks, reservations, состояние. Ранжирование группы НЕ
средним pair score (§23.2 п.8) — это в group_formation (§15.2 group utility).
"""

GROUP_STATE = ("forming", "quorum_met", "confirmed", "cancelled")


def build_group(group_id, host, *, title="", topics=None, size_min=3, size_max=8, min_quorum=3,
                roles=None, pair_blocks=None, members=None, reservations=None, state="forming"):
    if state not in GROUP_STATE:
        raise ValueError("bad group state: %r" % state)
    return {
        "group_id": group_id, "host": host, "title": title, "topics": list(topics or []),
        "size_min": int(size_min), "size_max": int(size_max), "min_quorum": int(min_quorum),
        "roles": roles or {}, "pair_blocks": [tuple(sorted(p)) for p in (pair_blocks or [])],
        "members": list(members or []), "reservations": list(reservations or []), "state": state,
    }
