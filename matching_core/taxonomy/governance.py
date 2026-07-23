# -*- coding: utf-8 -*-
"""§6 Governance — каждая taxonomy edge имеет owner, version, review state, evidence, rollback.

Изменение графа проходит **shadow replay**: добавление alias НЕ должно повышать similarity существующей
пары (иначе редактор графа мог бы «подкрутить» результаты). Транзакционно: при нарушении инварианта —
откат, edge отклоняется.
"""
import threading
from . import graph as G

_LOCK = threading.Lock()

# Реестр метаданных рёбер (§6 governance): edge -> {owner, version, review_state, kind}.
EDGE_META = {}

# Референсные пары (existing scored pairs) для shadow-replay инварианта.
REFERENCE_PAIRS = [
    (["dota2"], ["dota"]),        # alias-пара
    (["dota2"], ["lol"]),         # sibling (sub=moba)
    (["dota2"], ["chess"]),       # parent (broad=games)
    (["coffee"], ["tea"]),        # sibling (sub=coffee)
    (["coffee"], ["dota2"]),      # no overlap
    (["tennis"], ["padel"]),      # sibling (racket)
]


def _snapshot_levels():
    return {i: G.similarity(t, x)[0] for i, (t, x) in enumerate(REFERENCE_PAIRS)}


def shadow_replay(mutation):
    """Применяет mutation() (изменяет граф), сравнивает similarity REFERENCE_PAIRS до/после.
    Возвращает (ok, raised) — raised = список индексов пар, чей уровень ВЫРОС (нарушение §6)."""
    before = _snapshot_levels()
    undo = mutation()
    try:
        after = _snapshot_levels()
        raised = [i for i in before if after[i] > before[i]]
        return (len(raised) == 0), raised
    finally:
        if undo:
            undo()  # shadow: всегда откатываем сам replay; фактический commit — отдельно


def add_alias(variant, canonical, owner, *, review_state="approved"):
    """Транзакционно добавить alias variant->canonical. Отклоняет, если shadow-replay показывает рост
    similarity любой референсной пары (§6). Возвращает {ok, reason, edge}."""
    with _LOCK:
        v = str(variant).strip().lower()
        c = str(canonical).strip().lower()
        if v in G.SYNONYMS and G.SYNONYMS[v] != c:
            return {"ok": False, "reason": "alias already maps elsewhere", "edge": None}
        if G.resolve(c) == (None, None) and G.norm(c) not in G._IDX:
            return {"ok": False, "reason": "canonical not in taxonomy", "edge": None}

        def mutate():
            prev = G.SYNONYMS.get(v, None)
            G.SYNONYMS[v] = c
            def undo():
                if prev is None:
                    G.SYNONYMS.pop(v, None)
                else:
                    G.SYNONYMS[v] = prev
            return undo

        ok, raised = shadow_replay(mutate)
        if not ok:
            return {"ok": False, "reason": "shadow replay: raised existing pairs %s" % raised, "edge": None}
        # инвариант соблюдён -> коммитим по-настоящему
        G.SYNONYMS[v] = c
        meta = {"kind": "alias", "variant": v, "canonical": c, "owner": owner,
                "review_state": review_state, "version": EDGE_META.get(("alias", v), {}).get("version", 0) + 1}
        EDGE_META[("alias", v)] = meta
        return {"ok": True, "reason": None, "edge": meta}


def validate_governance():
    """Каждое зарегистрированное ребро имеет owner + review_state (§6)."""
    problems = []
    for key, meta in EDGE_META.items():
        if not meta.get("owner"):
            problems.append("%s: missing owner" % (key,))
        if meta.get("review_state") not in ("approved", "shadow", "pending"):
            problems.append("%s: bad review_state" % (key,))
    return problems
