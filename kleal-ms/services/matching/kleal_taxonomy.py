# -*- coding: utf-8 -*-
"""Kleal — governed taxonomy / evidence / semantic-expansion layer (spec §6).

A strictly READ-ONLY narrator + governor over the sealed scoring path. It NEVER recomputes a tier or a
score — the sha-pinned engine (core_v2.assign_tier / SEM_VALUE / directional_score, and app.topical) stays
the single source of truth. Everything here is additive metadata: a typed taxonomy edge, an expansion-chain
EXPLANATION (§6 «обязательно объяснить расширение»), a complementary-role matrix, per-edge governance
(owner/version/language_aliases/review_state/evidence/rollback), and the falsifiable governance PROOFS
(alias-does-not-raise-score invariant, shadow replay). All C/R/RCV/NEG/C4/C5 tests and the explain-vs-search
PARITY guard stay green because no output ever touches band/tier/lcb/can_outreach/reciprocal/readiness/trace.

Design invariants (do NOT break):
  * No `import app` (avoids a cycle). app injects the engine via bind_engine(); if it wasn't called, every
    public function no-ops (returns None / empty).
  * No filesystem access at import. The ontology (data/taxonomy/*.json) loads lazily on first use, is
    process-global mtime-cached, and every read is guarded — on ANY failure the ontology is empty and the
    layer degrades to pure in-code narration off the injected engine functions.
  * Every public function is catch-all: it returns None/empty, never raises into a scoring or explain path.
  * The governance proofs mutate the LIVE taxonomy globals via the injected graph_txn — TEST-ONLY / offline.
"""
import os, time
try:
    import kleal_contracts as kc
except Exception:                                    # pragma: no cover — kc is always present in-repo
    kc = None

# ------------------------------------------------------------------ injected engine (bind_engine)
_ENGINE = {}          # topical / norm / cat_of / same_topic / TAXONOMY / SYNONYMS / ADJACENCY / graph_txn

def bind_engine(**fns):
    """app injects its OWN scoring-taxonomy functions + globals so kt narrates the same decision the engine
    makes, and gets the single sanctioned edit channel (graph_txn) for its proofs. Read-only refs; no setters."""
    _ENGINE.update(fns)

def _bound():
    return bool(_ENGINE.get("topical") and _ENGINE.get("cat_of") and _ENGINE.get("norm"))

# ------------------------------------------------------------------ advisory mirrors (NEVER authoritative)
# Read-only echoes of sealed core_v2 constants — surfaced so a card can SHOW the engine's decision, never to
# recompute it. If core_v2 ever changes, these are advisory and reconciled against the injected engine.
_SEM_VALUE_MIRROR = {4: 1.0, 3: 0.65, 2: 0.45, 1: 0.25, 0: 0.05}
_BEST_TO_TYPE = {4: "exact_entity", 3: "direct_sibling", 2: "parent", 1: "adjacent_purpose", 0: "none"}
_BEST_TO_TIER = {4: "T1", 3: "T2", 2: "T2", 1: "T3", 0: "T5"}   # T2 folds sibling(3)+parent(2); T4 never emitted
_EDGE_NOTE = {
    "alias": "same entity, different surface form — collapses to one evidence_id, not a separate bonus",
    "exact_entity": "exact entity match (1.0 inside the semantic subfeature; not summed with alias)",
    "direct_sibling": "same sub-category (sibling) — related, discovery only",
    "parent": "same broad category (parent) — a broader match; expansion is explained",
    "adjacent_purpose": "adjacent purpose — no personal outreach without consent",
    "literal_token_share": "off-taxonomy literal shared word (not a curated ontology edge)",
    "none": "no meaningful topical overlap",
}
CONTRACTS_VERSION = "taxonomy-6.0.0"
ENGINE_VERSION = "matching-core-2.0.0"
ENGINE_SHA = "21505ccb"

# ------------------------------------------------------------------ lazy, guarded ontology load
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "taxonomy")
_ONTO = {"mtime": None, "edges": [], "aliases_by_norm": {}, "aliases_by_node": {}, "nodes": {}, "loaded": False}

def _load_ontology():
    """Read data/taxonomy/*.json ONCE (mtime-cached), fully guarded. On any failure -> empty ontology and the
    layer runs on in-code narration only (the honest pod default — the ~1.2MB ontology is not shipped)."""
    try:
        edges_path = os.path.join(_DATA_DIR, "edges.json")
        m = os.path.getmtime(edges_path)
    except Exception:
        _ONTO["loaded"] = True
        return _ONTO
    if _ONTO["loaded"] and _ONTO["mtime"] == m:
        return _ONTO
    import json
    def _read(name):
        try:
            with open(os.path.join(_DATA_DIR, name), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    try:
        edges = _read("edges.json")
        aliases = _read("aliases.json")
        nodes = {n.get("node_id"): n for n in _read("interests.json") if isinstance(n, dict) and n.get("node_id")}
        by_norm, by_node = {}, {}
        for a in aliases:
            if not isinstance(a, dict):
                continue
            surf = str(a.get("alias") or "").strip().lower()
            if surf:
                by_norm.setdefault(surf, a.get("node_id"))
            by_node.setdefault(a.get("node_id"), []).append(
                {"lang": a.get("language"), "alias": a.get("alias"), "type": a.get("alias_type"),
                 "canonical": a.get("normalized_label")})
        _ONTO.update({"mtime": m, "edges": edges, "aliases_by_norm": by_norm,
                      "aliases_by_node": by_node, "nodes": nodes, "loaded": True})
    except Exception:
        _ONTO.update({"mtime": m, "edges": [], "aliases_by_norm": {}, "aliases_by_node": {},
                      "nodes": {}, "loaded": True})
    return _ONTO

def _ontology_node_for(topic):
    """Best-effort map a topic surface form to a canonical ontology node_id (alias match, then EN/RU name
    substring). Enrichment only — returns None when the ontology is absent or nothing matches."""
    o = _load_ontology()
    t = str(topic or "").strip().lower()
    if not t:
        return None
    nid = o["aliases_by_norm"].get(t)
    if nid:
        return nid
    for node_id, n in o["nodes"].items():
        for key in ("Название EN", "Название RU", "Название ES"):
            if t and t in str(n.get(key) or "").strip().lower():
                return node_id
    return None

# ------------------------------------------------------------------ §6 typed edges
def edge_type(a, b):
    """Classify the (topic a, candidate-interest b) relationship via the SAME engine reducer (injected
    topical -> best), then label it. alias vs exact is decided by whether _norm rewrote the surface form;
    an off-taxonomy best=4 is literal_token_share, never a fabricated exact_entity edge. Advisory mirror of
    the engine's tier/value — never authoritative. Returns an Edge dict or None."""
    if not _bound():
        return None
    try:
        topical, norm, cat_of, same = (_ENGINE["topical"], _ENGINE["norm"],
                                       _ENGINE["cat_of"], _ENGINE["same_topic"])
        best, _matched = topical([a], [b])
        na, nb = norm(a), norm(b)                        # canonical (post-SYNONYM) forms
        ra = str(a).strip().lower().replace(" ", "")     # raw surface forms (pre-SYNONYM)
        rb = str(b).strip().lower().replace(" ", "")
        in_tax = cat_of(a)[0] is not None and cat_of(b)[0] is not None
        if best >= 4:
            if not in_tax:
                etype = "literal_token_share"            # off-taxonomy shared word — not a curated edge
            elif ra == rb:
                etype = "exact_entity"                   # identical surface form
            elif na == nb:
                etype = "alias"                          # different surface, same canonical (SYNONYM collapse)
            else:
                etype = "exact_entity"                   # same_topic via inflection/prefix — a fuzzy exact
        else:
            etype = _BEST_TO_TYPE.get(best, "none")
        node_id = _ontology_node_for(a) or _ontology_node_for(b)
        edge = {"type": etype, "a": a, "b": b, "best": best,
                "semantic_tier": _BEST_TO_TIER.get(best, "T5"),      # advisory mirror of assign_tier
                "sem_value_echo": _SEM_VALUE_MIRROR.get(best), "advisory": True,
                "note": _EDGE_NOTE.get(etype, ""),
                "source": "both" if node_id else "in_code",
                "canonical_node": node_id}
        _enrich_edge_from_ontology(edge, na, nb, node_id)
        edge["governance"] = governance_of(edge)
        return edge
    except Exception:
        return None

def _enrich_edge_from_ontology(edge, na, nb, node_id):
    try:
        o = _load_ontology()
        if not o["edges"] or not node_id:
            return
        for e in o["edges"]:
            src, tgt = e.get("source_node"), e.get("target_node")
            if node_id in (src, tgt) and e.get("relation"):
                edge.setdefault("ontology_relation", e.get("relation"))
                edge.setdefault("ontology_tier", e.get("tier"))
                edge.setdefault("outreach_allowed", e.get("outreach_allowed"))
                edge.setdefault("ontology_explanation", e.get("explanation"))
                # governance drift: ontology tier disagrees with the engine's advisory tier
                if e.get("tier") and e.get("tier") != edge["semantic_tier"]:
                    edge.setdefault("governance_finding",
                                    "ontology tier %s != engine tier %s (engine preferred)"
                                    % (e.get("tier"), edge["semantic_tier"]))
                break
    except Exception:
        return

def edge_for(topics, interests):
    """The single best typed edge for an intent's topics against a candidate's interests — mirrors the
    engine's single-best-tier reducer, so the card explains exactly the pair the engine scored."""
    if not _bound():
        return None
    try:
        topical, norm = _ENGINE["topical"], _ENGINE["norm"]
        best, matched = topical(list(topics or []), list(interests or []))
        m = sorted(matched)[0] if matched else None
        # pick the topic that yields `best` against the matched (or first) interest
        target = m or (list(interests or []) or [None])[0]
        chosen_topic, chosen_best = None, -1
        for t in (topics or []):
            e = edge_type(t, target) if target else None
            if e and e["best"] > chosen_best:
                chosen_best, chosen_topic = e["best"], t
        if chosen_topic is None:
            return None
        edge = edge_type(chosen_topic, target)
        if edge:
            edge["matched_topic"] = chosen_topic
            edge["matched_interest"] = target
        return edge
    except Exception:
        return None

# ------------------------------------------------------------------ §6 expansion chain (explain expansion)
def expand(topic):
    """The human-readable expansion chain for a topic (interest -> sub-category -> broad-category), the
    §6-mandated explanation for parent/sibling matches. In-code narration is authoritative; the ontology
    parent chain (interests.json parent_id + edges.json explanation) enriches it, and on any drift the
    ENGINE bucket is preferred with a governance_finding."""
    if not _bound():
        return None
    try:
        cat_of, norm = _ENGINE["cat_of"], _ENGINE["norm"]
        b, s = cat_of(topic)
        chain = [{"node": norm(topic), "level": "interest"}]
        if s:
            chain.append({"node": s, "level": "sub_category"})
        if b:
            chain.append({"node": b, "level": "broad_category"})
        parts = [c["node"] for c in chain]
        out = {"topic": topic, "in_code_bucket": {"broad": b, "sub": s}, "chain": chain,
               "explanation": " → ".join(parts) if len(parts) > 1 else "%s (no broader taxonomy chain)" % parts[0],
               "source": "in_code", "advisory": True}
        _enrich_expand_from_ontology(out, topic, b)
        return out
    except Exception:
        return None

def _enrich_expand_from_ontology(out, topic, in_code_broad):
    try:
        o = _load_ontology()
        node_id = _ontology_node_for(topic)
        if not node_id or not o["nodes"]:
            return
        onto_chain, guard, seen = [], 0, set()
        cur = node_id
        while cur and cur in o["nodes"] and guard < 8 and cur not in seen:
            seen.add(cur); guard += 1
            n = o["nodes"][cur]
            onto_chain.append({"node_id": cur, "name_en": n.get("Название EN"),
                               "domain": n.get("domain"), "level": n.get("node_type")})
            cur = n.get("parent_id")
        if onto_chain:
            out["ontology_chain"] = onto_chain
            leaf = o["nodes"].get(node_id) or {}
            onto_domain = leaf.get("domain")
            # drift: the ontology's domain family vs the in-code broad bucket the engine actually used
            if onto_domain and in_code_broad and onto_domain not in (in_code_broad,) and out.get("in_code_bucket", {}).get("broad"):
                out["governance_finding"] = ("ontology domain %r vs in-code broad %r — engine bucket preferred"
                                             % (onto_domain, in_code_broad))
    except Exception:
        return

# ------------------------------------------------------------------ §6 complementary-role matrix (NOT similarity)
# A typed ROLE MATRIX — complementary roles fit together (support+carry), they are NOT "similar". Distinct
# from ROLE_CONFLICT (opposing) and from vibe similarity. Surfaced as metadata; never fed into scoring.
_COMPLEMENT = {
    frozenset(("support", "carry")): "role_complementarity",
    frozenset(("tank", "healer")): "team_role",
    frozenset(("tank", "dps")): "team_role",
    frozenset(("healer", "dps")): "team_role",
    frozenset(("learner", "native")): "language_pair",
    frozenset(("beginner", "native")): "language_pair",
    frozenset(("cofounder", "engineer")): "project_role",
    frozenset(("mentor", "mentee")): "role_complementarity",
    frozenset(("teacher", "student")): "role_complementarity",
}

def complementary(role_a, role_b):
    """Typed complementary-role relation (support↔carry, learner↔native, …) or None. A MATRIX, not a
    similarity score — complementary roles are different-and-fitting, never the same role."""
    try:
        ra, rb = str(role_a or "").strip().lower(), str(role_b or "").strip().lower()
        if not ra or not rb or ra == rb:
            return None
        rel = _COMPLEMENT.get(frozenset((ra, rb)))
        if not rel:
            rel = _complement_from_ontology(ra, rb)
        if not rel:
            return None
        return {"type": "complementary_role", "relation": rel, "a": ra, "b": rb,
                "similarity": False, "note": "complementary roles fit together — not a similarity match",
                "governance": {"owner": "matching-engine@app.py", "version": ENGINE_VERSION,
                               "review_state": "in_code", "rollback": "sha-pinned:%s — Dev-B version bump" % ENGINE_SHA}}
    except Exception:
        return None

def _complement_from_ontology(ra, rb):
    try:
        o = _load_ontology()
        rolelike = {"role_complementarity", "team_role", "game_role", "project_role",
                    "slot_complementarity", "language_pair"}
        for e in o["edges"]:
            if e.get("relation") in rolelike:
                src = str(e.get("source_node") or "").lower()
                tgt = str(e.get("target_node") or "").lower()
                if (ra in src and rb in tgt) or (ra in tgt and rb in src):
                    return e.get("relation")
        return None
    except Exception:
        return None

# ------------------------------------------------------------------ §6 governance
def governance_of(edge):
    """Attach the six §6 governance fields to an edge. In-code-derived edges are owned by the engine and roll
    back only via a Dev-B core_v2 version bump; ontology-enriched edges cite the MANIFEST + edge row."""
    edge = edge or {}
    onto = edge.get("source") in ("ontology", "both")
    node_id = edge.get("canonical_node")
    lang_aliases = []
    try:
        if node_id:
            lang_aliases = [{"lang": a["lang"], "alias": a["alias"]}
                            for a in _load_ontology()["aliases_by_node"].get(node_id, [])][:6]
    except Exception:
        lang_aliases = []
    ev = None
    try:
        if kc is not None and edge.get("a") is not None:
            # Evidence is about the NODE/ENTITY, keyed on its CANONICAL form (ontology node_id or the norm),
            # under a fixed field — so an alias and its canonical collapse to ONE evidence_id (§4.1 dedup):
            # taxonomy.node / "football" is identical whether reached via "soccer" (alias) or "football" (exact).
            canon = node_id or _ENGINE.get("norm", lambda x: x)(edge.get("b") or edge.get("a"))
            ev = kc.build_evidence("taxonomy.node", canon, "explicit_stable_profile", scope="taxonomy_edge")
    except Exception:
        ev = None
    return {
        "owner": "ontology@data/taxonomy" if onto else "matching-engine@app.py",
        "version": ENGINE_VERSION,
        "language_aliases": lang_aliases,
        "review_state": "active" if onto else "in_code",
        "evidence": ev,
        "rollback": ("ontology: drop the edge row + revert to prior MANIFEST version" if onto
                     else "sha-pinned:%s — change requires a Dev-B core_v2 version bump" % ENGINE_SHA),
    }

def validate(edge):
    """Read-only governance validator — every edge MUST carry all six governance fields + a legal
    review_state. Returns a list of findings (empty = ok); never mutates."""
    g = (edge or {}).get("governance") or {}
    findings = []
    for f in ("owner", "version", "language_aliases", "review_state", "evidence", "rollback"):
        if f not in g:
            findings.append("missing governance field: %s" % f)
    if g.get("review_state") not in ("active", "in_code", "deprecated"):
        findings.append("illegal review_state: %r" % g.get("review_state"))
    return findings

# ------------------------------------------------------------------ §6 falsifiable governance proofs (TEST-ONLY)
def alias_invariant(fixture_pairs, alias_to_add):
    """§6 Governance: «adding an alias must NOT raise the score of an existing pair.» Records best_before for
    every fixture pair via the injected topical, then transactionally adds the alias to the LIVE graph via
    graph_txn (so the injected topical genuinely resolves it), records best_after, and asserts
    best_after <= best_before for ALL pairs. Restores in finally (graph_txn guarantees it). TEST-ONLY —
    never call inside a live request. Returns {ok, violations, checked}."""
    if not _bound() or not _ENGINE.get("graph_txn"):
        return {"ok": None, "violations": [], "checked": 0, "note": "engine/graph_txn not bound"}
    try:
        topical, graph_txn = _ENGINE["topical"], _ENGINE["graph_txn"]
        before = {}
        for (a, b) in fixture_pairs:
            before[(a, b)] = topical([a], [b])[0]
        variant, canon = alias_to_add
        violations = []
        with graph_txn({"synonyms": {variant: canon}}):
            for (a, b) in fixture_pairs:
                after = topical([a], [b])[0]
                if after > before[(a, b)]:
                    violations.append({"pair": [a, b], "before": before[(a, b)], "after": after})
        return {"ok": not violations, "violations": violations, "checked": len(fixture_pairs)}
    except Exception as e:
        return {"ok": None, "violations": [], "checked": 0, "error": str(e)[:120]}

def shadow_replay(mode, edits, replay_fn, fields=("band", "tier", "lcb", "can_outreach")):
    """§6 Governance: «a graph change goes through shadow replay.» Two honest, negative-controlled modes:
      MODE A ('ontology'): the edit is to reference data the scoring path never reads -> replay MUST be
        byte-identical on the PARITY fields (proves the ontology surface is additive-only / invisible).
      MODE B ('graph'):    the edit is applied to the LIVE in-code SYNONYMS/TAXONOMY/ADJACENCY via graph_txn
        -> replay the fixture before + after and DIFF the fields; this is the real §6 gate over the graph
        the engine actually scores. Restores in finally.
    replay_fn() must return a comparable snapshot (list of per-card dicts). Returns {mode, changed, diff}."""
    if not _bound() or not callable(replay_fn):
        return {"mode": mode, "changed": None, "diff": [], "note": "not bound"}
    def _snap():
        try:
            return [tuple(round(c[f], 4) if isinstance(c.get(f), float) else c.get(f) for f in fields)
                    for c in (replay_fn() or [])]
        except Exception:
            return []
    try:
        before = _snap()
        if mode == "ontology":
            after = _snap()                                  # no live-graph edit — must be identical
        else:
            graph_txn = _ENGINE.get("graph_txn")
            if not graph_txn:
                return {"mode": mode, "changed": None, "diff": [], "note": "graph_txn not bound"}
            with graph_txn(edits or {}):
                after = _snap()
        diff = [{"i": i, "before": before[i], "after": after[i]}
                for i in range(min(len(before), len(after))) if before[i] != after[i]]
        return {"mode": mode, "changed": bool(diff), "diff": diff,
                "n": min(len(before), len(after))}
    except Exception as e:
        return {"mode": mode, "changed": None, "diff": [], "error": str(e)[:120]}

# ------------------------------------------------------------------ enrichment surface (additive card keys)
def enrich_card(topics, cand_interests, role_a=None, role_b=None):
    """Build the additive §6 card keys for one candidate. Returns a dict with any of taxonomy_edge /
    expansion_chain / complementary — the caller setdefaults them onto the card. Fully guarded: returns {}
    on any problem, so it can NEVER empty a slate or change a score."""
    out = {}
    try:
        edge = edge_for(topics, cand_interests)
        if edge:
            out["taxonomy_edge"] = edge
            if edge.get("matched_topic") and edge.get("best", 0) in (2, 3):   # explain broadened (parent/sibling)
                ex = expand(edge["matched_topic"])
                if ex:
                    out["expansion_chain"] = ex
        comp = complementary(role_a, role_b)
        if comp:
            out["complementary"] = comp
    except Exception:
        return {}
    return out
