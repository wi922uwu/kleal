# -*- coding: utf-8 -*-
"""§4 RelationshipEdge — история пары (advisory metadata, НЕ authoritative gate).

new/contact/friend/repeat/avoid/block, scope, cooldown. Реальный block/cooldown остаётся hard gate
policy-engine (§8.1); это ребро — контекст для relationship continuation (§1.1) и allocation cooldown.
Scope важен для purpose isolation (§8.3): dating decline не переносится на friendship edge.
"""

EDGE_TYPES = ("new", "contact", "friend", "repeat", "avoid", "block")


def build_relationship_edge(pair, edge_type="new", *, scope=None, cooldown_days=7, last_ts=None,
                            accepted=0, completed=0):
    if edge_type not in EDGE_TYPES:
        raise ValueError("bad edge type: %r" % edge_type)
    return {"pair": tuple(sorted(str(p).lower() for p in pair)), "type": edge_type, "scope": scope,
            "cooldown_days": int(cooldown_days), "last_ts": last_ts,
            "accepted": int(accepted), "completed": int(completed)}


def in_cooldown(edge, now, day_sec=86400.0):
    lt = edge.get("last_ts")
    if lt is None:
        return False
    return (float(now) - float(lt)) < edge.get("cooldown_days", 7) * day_sec
