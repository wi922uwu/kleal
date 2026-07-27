# -*- coding: utf-8 -*-
"""Kleal — §15 Group Formation Core (keyless, LLM-free, deterministic, PILOT-DISABLED scaffolding).

A group is scored as a SET, not as an average of pair matches (§15). This module implements §15.1 set-level
hard constraints, the §15.2 GroupUtility (weights read from the sha-pinned config — never hardcoded), and the
§15.3 MVP formation algorithm (seed → feasible pools → greedy marginal gain → local repair → reserve). It is
CONFORMANCE SCAFFOLDING: group_formation is OFF in the pilot (§1.2/§15), so nothing here is wired into the live
buddy→filtration→matching person-to-person flow. The algorithm runs ONLY under an explicit test-only override
(`{'enable_group_formation': True}`); every returned payload still carries `enabled:False`.

Discipline (mirrors kleal_states / kleal_contracts):
  - imports ONLY stdlib `hashlib` + `kleal_contracts` (kc) + `kleal_states` (ks); NEVER core_v2 / llm_client.
  - no FS, no clock, no randomness at import OR at runtime — `now_ts` is injected by the caller (incl. into
    `kc.build_reservation`, which otherwise defaults to `time.time()`).
  - deterministic: stable sha1 `_id_hash` tiebreaks (never salted `hash()`), sorted iteration, 6dp rounding.
  - pair relevance is strictly an INPUT (§15.2). The module NEVER computes R_{i→j}; the wiring layer (task #37)
    builds the symmetric n×n candidate↔candidate matrix from core_v2 and passes it as `pair_rel`.

Honest scope: capacity/reservation is SINGLE-PROCESS (reuses the §14 `ks.claim_slot`; cross-process/multi-pod
atomicity needs the DB/queue the pilot does not run — blocked_infra). Structured invitations are constructed but
NOT sent (no messaging in the pilot). Concrete §15.4 domain packs are deferred to the §37 wiring.
"""
import hashlib
import kleal_contracts as kc
import kleal_states as ks

GROUPS_VERSION = "groups-15.0.0"
_EPS = 1e-9
_MAX_MVP_SIZE = 8          # §15 config supported_size_max_mvp ceiling; a per-intent size may only tighten this
_RES_TTL = 3600            # reservation hold seconds (seat hold); TTL semantics live in kc.build_reservation

# EXACT config keys are the source of truth. The §15.2 PROSE uses different names for two of them — SPEC_ALIAS
# documents the map so a weight is never looked up by the wrong (spec) name and silently zeroed.
WEIGHT_KEYS = ("least_misery", "mean_member_relevance", "role_coverage", "time_overlap", "diversity_budget")
SPEC_ALIAS = {"mean_member_relevance": "mean_pair_fit", "diversity_budget": "diversity_value"}
# config size/quorum keys → internal names (the yaml uses supported_size_*/min_quorum_*; do NOT read internal names off the yaml)
_SIZE_KEY_MAP = {"supported_size_min": "size_min", "supported_size_max_mvp": "size_max", "min_quorum_default": "quorum_default"}
# spec-default params — used ONLY when a caller runs the pure functions without a config in hand (tests/introspection).
# The live/override path always reads the sha-pinned config via load_group_params; these mirror yaml:221-229.
_SPEC_DEFAULT_PARAMS = {"size_min": 3, "size_max": 8, "quorum_default": 3,
                        "weights": {"least_misery": 0.35, "mean_member_relevance": 0.25,
                                    "role_coverage": 0.20, "time_overlap": 0.10, "diversity_budget": 0.10}}


class GroupConfigError(ValueError):
    """Raised by load_group_params on group_formation-block drift. Never swallowed silently — the endpoint
    catches it and stays enabled:False (a bad config must not activate group formation)."""


# ----------------------------------------------------------------------------- config (config-derived weights)
def _check_block(block):
    """Return a SORTED list of problems with a group_formation config block (empty == valid). Closes the
    utility_weights sum-to-1.0 gate that core_v2.load_config skips — WITHOUT editing the sha-pinned yaml."""
    probs = []
    if not isinstance(block, dict):
        return ["group_formation block missing or not a mapping"]
    uw = block.get("utility_weights")
    if not isinstance(uw, dict):
        probs.append("utility_weights missing")
    else:
        missing = [k for k in WEIGHT_KEYS if k not in uw]
        if missing:
            probs.append("utility_weights missing keys: %s" % sorted(missing))
        unknown = [k for k in uw if k not in WEIGHT_KEYS]
        if unknown:
            probs.append("utility_weights unknown keys: %s" % sorted(unknown))
        for k in WEIGHT_KEYS:
            v = uw.get(k)
            if not isinstance(v, (int, float)) or isinstance(v, bool) or not (0.0 <= float(v) <= 1.0):
                probs.append("utility_weight %r not a float in [0,1]" % k)
        if not missing and all(isinstance(uw.get(k), (int, float)) and not isinstance(uw.get(k), bool) for k in WEIGHT_KEYS):
            s = sum(float(uw[k]) for k in WEIGHT_KEYS)
            if abs(s - 1.0) > 1e-6:
                probs.append("utility_weights sum to %.4f, must be 1.0" % s)
    smin, smax, quorum = block.get("supported_size_min"), block.get("supported_size_max_mvp"), block.get("min_quorum_default")
    for name, v in (("supported_size_min", smin), ("supported_size_max_mvp", smax), ("min_quorum_default", quorum)):
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            probs.append("%s must be a positive int" % name)
    if isinstance(smin, int) and isinstance(smax, int) and not (1 <= smin <= smax <= _MAX_MVP_SIZE):
        probs.append("require 1 <= supported_size_min(%s) <= supported_size_max_mvp(%s) <= %d" % (smin, smax, _MAX_MVP_SIZE))
    if isinstance(quorum, int) and isinstance(smin, int) and isinstance(smax, int) and not (smin <= quorum <= smax):
        probs.append("min_quorum_default(%s) must be within [supported_size_min, supported_size_max_mvp]" % quorum)
    return sorted(probs)

def validate_group_config_block(cfg):
    """Read-only sibling of load_group_params: returns a list of problem strings (never raises). Meant to run
    at the CALLER (app.py load-time / CI) so a config drift is reported without crashing the live service."""
    return _check_block(((cfg or {}) or {}).get("group_formation"))

def load_group_params(cfg):
    """Read cfg['group_formation'] (already parsed by core_v2.load_config — NO FS here) into validated params
    {size_min, size_max, quorum_default, weights{5 config keys→float}}. Raises GroupConfigError on ANY problem.
    NEVER hardcodes 0.35/0.25/…; the weights come only from the config block."""
    block = (cfg or {}).get("group_formation")
    probs = _check_block(block)
    if probs:
        raise GroupConfigError("; ".join(probs))
    out = {_SIZE_KEY_MAP[k]: int(block[k]) for k in _SIZE_KEY_MAP}
    out["weights"] = {k: float(block["utility_weights"][k]) for k in WEIGHT_KEYS}
    return out


# ----------------------------------------------------------------------------- deterministic identity helpers
def _id_hash(*parts):
    """Cross-process-stable sha1 hex of the parts — the tiebreak key. NEVER Python hash() (per-process salted)."""
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()

def _member_id(m):
    m = m or {}
    return str(m.get("id") or m.get("name") or "")

def _sort_key(m):
    """Stable order: strongest directed relevance first, then sha1 id-hash, then id (total order, permutation-proof)."""
    return (-float((m or {}).get("relevance") or 0.0), _id_hash(_member_id(m)), _member_id(m))

def group_signature(members):
    """Byte-stable identity of a member SET (order-independent) — the exact-tie winner + kc.build_group id source."""
    return hashlib.sha1("|".join(sorted(_member_id(m) for m in (members or []))).encode("utf-8")).hexdigest()

def member_from_card(card, member_id=None):
    """ADAPTER (wiring layer only, task #37): a core_v2 slate card → a group member. relevance = card['lcb']
    (the DIRECTED conservative satisfaction estimate — the INPUT, NOT reciprocal_score, NOT recomputed here)."""
    card = card or {}
    return {
        "id": member_id or card.get("id") or card.get("name"),
        "name": card.get("name"),
        "relevance": float(card.get("lcb") if card.get("lcb") is not None else (card.get("relevance") or 0.0)),
        "role": card.get("role"), "roles": list(card.get("roles") or ([] if card.get("role") is None else [card.get("role")])),
        "level": card.get("level"), "langs": list(card.get("langs") or card.get("languages") or []),
        "time_windows": list(card.get("time_windows") or card.get("availability") or []),
        "equipment": list(card.get("equipment") or []), "platforms": list(card.get("platforms") or []),
        "is_moderator": bool(card.get("is_moderator")),
    }

def directed_relevance(pair_rel, a_id, b_id):
    """INPUT accessor for R_{a→b} in [0,1]. pair_rel may be dict{(a,b):R} | dict-of-dicts | callable(a,b)->R |
    None. Missing edge -> 0.0 (deny-safe: unknown != openness). The module NEVER computes R."""
    if pair_rel is None:
        return 0.0
    v = None
    try:
        if callable(pair_rel):
            v = pair_rel(a_id, b_id)
        elif isinstance(pair_rel, dict):
            if (a_id, b_id) in pair_rel:
                v = pair_rel[(a_id, b_id)]
            else:
                inner = pair_rel.get(a_id)
                v = inner.get(b_id) if isinstance(inner, dict) else None
    except Exception:
        v = None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0.0
    if v != v:                        # NaN -> deny-safe 0.0 (unknown != openness)
        return 0.0
    return 0.0 if v < 0 else (1.0 if v > 1 else v)


# ----------------------------------------------------------------------------- §15.2 utility components (each in [0,1])
def _directed_pairs(members):
    ids = [_member_id(m) for m in members]
    return [(ids[i], ids[j]) for i in range(len(ids)) for j in range(len(ids)) if i != j]

def least_misery(members, pair_rel=None):
    """§15.2 — the MINIMUM directed satisfaction within the group (protects against a high mean hiding one
    clearly-unsuitable member). With a pair matrix: min over all ordered edges. Star fallback (pair_rel None):
    min over members of member['relevance'] (the initiator's directed lcb — see docstring note on the fallback)."""
    if len(members or []) < 2:
        return 0.0
    if pair_rel is None:
        return max(0.0, min(float((m or {}).get("relevance") or 0.0) for m in members))
    return min(directed_relevance(pair_rel, a, b) for a, b in _directed_pairs(members))

def mean_pair_fit(members, pair_rel=None):
    """§15.2 (config key 'mean_member_relevance') — mean over all ordered directed edges; star fallback = mean
    of member['relevance']. Shares its population with least_misery (mean vs min of the SAME edges)."""
    ms = members or []
    if len(ms) < 2:
        return 0.0
    if pair_rel is None:
        return sum(float((m or {}).get("relevance") or 0.0) for m in ms) / len(ms)
    edges = _directed_pairs(ms)
    return sum(directed_relevance(pair_rel, a, b) for a, b in edges) / len(edges)

def _member_roles(m):
    m = m or {}
    rs = set(str(r) for r in (m.get("roles") or []) if r)
    if m.get("role"):
        rs.add(str(m.get("role")))
    return rs

def role_coverage(members, required_roles):
    """§15.2 SOFT term over the FULL role wishlist: |covered required roles| / |required|. Empty wishlist -> 1.0
    (vacuous). The MANDATORY subset is ALSO a hard gate in check_set_constraints — this only shapes utility."""
    req = [str(r) for r in (required_roles or []) if r]
    if not req:
        return 1.0
    covered = set()
    for m in members or []:
        covered |= _member_roles(m)
    return len([r for r in req if r in covered]) / float(len(req))

def _intervals(m):
    """A member's availability as a list of [start,end] numeric intervals (minutes/epoch — caller-consistent)."""
    out = []
    for w in (m or {}).get("time_windows") or []:
        try:
            s, e = float(w[0]), float(w[1])
            if e > s:
                out.append((s, e))
        except (TypeError, ValueError, IndexError):
            continue
    return out

def _intersect(a, b):
    """Intersection of two interval SETS (lists of (s,e)) -> the sub-intervals covered by BOTH."""
    out = []
    for s1, e1 in a:
        for s2, e2 in b:
            s, e = max(s1, s2), min(e1, e2)
            if e > s:
                out.append((s, e))
    return out

def _total_length(intervals):
    """Total measure of a (possibly overlapping) interval set — merge overlaps, then sum lengths."""
    if not intervals:
        return 0.0
    xs = sorted(intervals)
    total, cs, ce = 0.0, xs[0][0], xs[0][1]
    for s, e in xs[1:]:
        if s > ce:
            total += ce - cs
            cs, ce = s, e
        else:
            ce = max(ce, e)
    return total + (ce - cs)

def _common_window(members):
    """TRUE length of the intersection of ALL members' availability SETS (not a bounding span — a member with
    two disjoint windows [[0,10],[100,110]] must NOT read as available across the gap). A member with no
    declared window is treated as always-available (deny-safe: the HARD gate handles 'insufficient'); if NO
    member declares any window at all -> None (time unconstrained)."""
    present = [_intervals(m) for m in members or []]
    present = [p for p in present if p]
    if not present:
        return None
    acc = present[0]
    for p in present[1:]:
        acc = _intersect(acc, p)
        if not acc:
            return 0.0
    return _total_length(acc)

def time_overlap(members, constraints):
    """§15.2 SOFT term: clamp(common_window / target, 0, 1), target = ideal_duration_min or min_duration_min.
    No time constrained at all -> 1.0; windows present but disjoint -> 0.0."""
    c = constraints or {}
    target = c.get("ideal_duration_min") or c.get("min_duration_min")
    cw = _common_window(members)
    if cw is None or not target:
        return 1.0
    target = float(target)
    if target <= 0:
        return 1.0
    return max(0.0, min(1.0, cw / target))

def diversity_value(members, constraints):
    """§15.2 (config key 'diversity_budget') — normalized Gini-Simpson over constraints['diversity_axis']:
    (1 - Σ p_v²)/(1 - 1/N) for N>=2 else 0.0. 50/50 -> 1.0, homogeneous -> 0.0. MISSING axis -> 0.0
    (conservative: no free utility on an unexpressed dimension; a 0.10 soft term, never a source of infeasibility)."""
    c = constraints or {}
    axis = c.get("diversity_axis")
    ms = members or []
    n = len(ms)
    if not axis or n < 2:
        return 0.0
    counts = {}
    for m in ms:
        v = (m or {}).get(axis)
        counts[v] = counts.get(v, 0) + 1
    simpson = 1.0 - sum((cnt / float(n)) ** 2 for cnt in counts.values())
    denom = 1.0 - 1.0 / n
    return max(0.0, min(1.0, simpson / denom)) if denom > 0 else 0.0

def group_utility_components(members, constraints, params, pair_rel=None):
    """The 5 raw §15.2 components (each in [0,1]) + their weighted parts + total. Reported even for an infeasible
    group (transparency); the feasibility gate lives in group_utility, not here."""
    w = (params or _SPEC_DEFAULT_PARAMS)["weights"]
    req_roles = (constraints or {}).get("required_roles") or (constraints or {}).get("mandatory_roles") or []
    comp = {
        "least_misery": least_misery(members, pair_rel),
        "mean_pair_fit": mean_pair_fit(members, pair_rel),
        "role_coverage": role_coverage(members, req_roles),
        "time_overlap": time_overlap(members, constraints),
        "diversity_value": diversity_value(members, constraints),
    }
    # map each spec-named component onto its CONFIG weight key (source of truth)
    weighted = {
        "least_misery": w["least_misery"] * comp["least_misery"],
        "mean_member_relevance": w["mean_member_relevance"] * comp["mean_pair_fit"],
        "role_coverage": w["role_coverage"] * comp["role_coverage"],
        "time_overlap": w["time_overlap"] * comp["time_overlap"],
        "diversity_budget": w["diversity_budget"] * comp["diversity_value"],
    }
    return {"components": comp, "weighted": weighted, "total": sum(weighted.values())}


# ----------------------------------------------------------------------------- §15.1 set-level hard constraints
def _all_langs(members):
    out = set()
    for m in members or []:
        out |= set(str(l) for l in ((m or {}).get("langs") or []) if l)
    return out

def _levels(members):
    out = []
    for m in members or []:
        lv = (m or {}).get("level")
        if isinstance(lv, (int, float)) and not isinstance(lv, bool):
            out.append(float(lv))
    return out

def check_set_constraints(group, constraints, params, now_ts=None):
    """Return SORTED §15.1 violation codes for a candidate group (empty == feasible). Deny-safe: an unknown /
    unspecified constraint is a no-op, NEVER a false-pass on a block/safety exclusion. now_ts is accepted for
    a clock-free signature symmetry (time gates use member windows, not the wall clock)."""
    c = constraints or {}
    p = params or _SPEC_DEFAULT_PARAMS
    members = list(group or [])
    ids = [_member_id(m) for m in members]
    v = []
    n = len(members)
    size_min = int(c.get("size_min", p.get("size_min", 3)))
    size_max = int(c.get("size_max", p.get("size_max", _MAX_MVP_SIZE)))
    quorum = int(c.get("quorum", p.get("quorum_default", size_min)))
    if n < size_min:
        v.append("SIZE_MIN")
    if n > size_max:
        v.append("SIZE_MAX")
    if n < quorum:
        v.append("QUORUM")
    cap = c.get("capacity")
    if isinstance(cap, int) and n > cap:
        v.append("CAPACITY_EXCEEDED")
    # mandatory roles — hard gate (the soft role_coverage term measures the FULL wishlist separately)
    mand = [str(r) for r in (c.get("mandatory_roles") or []) if r]
    if mand:
        covered = set()
        for m in members:
            covered |= _member_roles(m)
        if any(r not in covered for r in mand):
            v.append("MANDATORY_ROLE_UNMET")
    # pairwise blocks
    for pb in c.get("pair_blocks") or []:
        try:
            a, b = str(pb[0]), str(pb[1])
        except (TypeError, IndexError):
            continue
        if a in ids and b in ids:
            v.append("PAIR_BLOCKED")
            break
    # safety exclusions
    excl = set(str(x) for x in (c.get("safety_excluded") or []))
    if excl & set(ids):
        v.append("SAFETY_EXCLUDED")
    # host / moderator
    if c.get("require_moderator") and not any((m or {}).get("is_moderator") for m in members):
        v.append("HOST_MISSING")
    # skill spread
    msp = c.get("max_skill_spread")
    if isinstance(msp, (int, float)) and not isinstance(msp, bool):
        lv = _levels(members)
        if lv and (max(lv) - min(lv)) > float(msp):
            v.append("SKILL_SPREAD")
    # language coverage — every required language covered by the UNION of members' languages
    req_langs = [str(l) for l in (c.get("required_languages") or []) if l]
    if req_langs:
        have = _all_langs(members)
        if any(l not in have for l in req_langs):
            v.append("LANGUAGE_UNCOVERED")
    # equipment / platform / venue — every required item present in the union of members' equipment/platforms
    req_eq = [str(e) for e in (c.get("required_equipment") or []) if e]
    if req_eq:
        have_eq = set()
        for m in members:
            have_eq |= set(str(e) for e in ((m or {}).get("equipment") or []))
        if any(e not in have_eq for e in req_eq):
            v.append("EQUIPMENT_MISSING")
    req_plat = c.get("required_platform")
    if req_plat and not all(str(req_plat) in set(str(x) for x in ((m or {}).get("platforms") or [])) for m in members):
        v.append("PLATFORM_UNSUPPORTED")
    # time overlap of sufficient duration — HARD gate at min_duration_min
    min_dur = c.get("min_duration_min")
    if min_dur:
        cw = _common_window(members)
        if cw is not None and cw < float(min_dur):
            v.append("TIME_OVERLAP_INSUFFICIENT")
    return sorted(set(v))

def set_feasible(group, constraints, params, now_ts=None):
    return not check_set_constraints(group, constraints, params, now_ts=now_ts)

def group_utility(group, constraints, params, pair_rel=None, now_ts=None):
    """§15.2 — FEASIBILITY DOMINATES. If any hard set constraint is violated, utility is None (undefined, never
    a number) so an infeasible group can never be compared or selected regardless of its component values."""
    members = list(group or [])
    violations = check_set_constraints(members, constraints, params, now_ts=now_ts)
    parts = group_utility_components(members, constraints, params, pair_rel=pair_rel)
    if violations:
        return {"utility": None, "components": parts["components"], "weighted": parts["weighted"],
                "feasible": False, "violations": violations}
    return {"utility": round(parts["total"], 6), "components": parts["components"], "weighted": parts["weighted"],
            "feasible": True, "violations": []}


# ----------------------------------------------------------------------------- §15.3 MVP formation algorithm
def filter_hard_set_constraints(candidates, constraints, now_ts=None):
    """Per-member prefilter: drop anyone who can NEVER sit in a feasible group (safety-excluded, missing a
    required-language they'd have to solely provide is NOT droppable — that's a set property; here we only drop
    universally-infeasible members: safety exclusion, wrong required_platform, missing all required_equipment,
    level outside an explicit band). Returns SORTED by (-relevance, id_hash, id) for order-stable seeding."""
    c = constraints or {}
    excl = set(str(x) for x in (c.get("safety_excluded") or []))
    band = c.get("level_band")             # optional [lo, hi]
    req_plat = c.get("required_platform")
    out = []
    for m in candidates or []:
        mid = _member_id(m)
        if mid in excl:
            continue
        if req_plat and str(req_plat) not in set(str(x) for x in ((m or {}).get("platforms") or [])):
            continue
        if isinstance(band, (list, tuple)) and len(band) == 2:
            lv = (m or {}).get("level")
            if isinstance(lv, (int, float)) and not isinstance(lv, bool) and not (float(band[0]) <= float(lv) <= float(band[1])):
                continue
        out.append(m)
    return sorted(out, key=_sort_key)

def _best_for_role(pool, role, chosen_ids, pair_rel=None):
    """The feasible member covering `role`, not already chosen, with the best relevance; ties by (id_hash,id)."""
    cands = [m for m in pool if role in _member_roles(m) and _member_id(m) not in chosen_ids]
    if not cands:
        return None
    return sorted(cands, key=_sort_key)[0]

def generate_role_complete_seeds(feasible, constraints, params, pair_rel=None, max_seeds=16):
    """§15.3.1/3 — deterministic minimal seed sets covering ALL mandatory roles. No mandatory roles -> top-K
    feasible singletons (by id_hash). Seeds are deduped by signature and capped for a bounded work budget."""
    c = constraints or {}
    mand = [str(r) for r in (c.get("mandatory_roles") or []) if r]
    pool = list(feasible or [])
    if not mand:
        return [[m] for m in sorted(pool, key=lambda m: (_id_hash(_member_id(m)), _member_id(m)))[:max_seeds]]
    seeds, seen = [], set()
    anchors = sorted(pool, key=lambda m: (_id_hash(_member_id(m)), _member_id(m)))
    for anchor in anchors:
        if len(seeds) >= max_seeds:
            break
        chosen, chosen_ids = [anchor], {_member_id(anchor)}
        # cover each mandatory role (sorted) starting from the anchor's own roles
        ok = True
        for role in sorted(mand):
            if role in _member_roles(anchor) or any(role in _member_roles(x) for x in chosen):
                continue
            pick = _best_for_role(pool, role, chosen_ids, pair_rel)
            if pick is None:
                ok = False
                break
            chosen.append(pick)
            chosen_ids.add(_member_id(pick))
        if not ok:
            continue
        sig = group_signature(chosen)
        if sig not in seen and not check_set_constraints_role_only(chosen, mand):
            seen.add(sig)
            seeds.append(chosen)
    return seeds

def check_set_constraints_role_only(members, mandatory):
    """Lightweight: are all mandatory roles covered? (used during seeding, before full feasibility)."""
    covered = set()
    for m in members or []:
        covered |= _member_roles(m)
    return [r for r in (mandatory or []) if r not in covered]

_SHORTFALL = ("SIZE_MIN", "QUORUM", "MANDATORY_ROLE_UNMET")   # violations an ADD can resolve

def greedy_marginal_add(seed, feasible, constraints, params, pair_rel=None, now_ts=None):
    """§15.3.3 — grow the seed. While the group is infeasible ONLY via a size/quorum/mandatory-role SHORTFALL,
    add the member that best PROGRESSES feasibility (fewest remaining violations; ties by higher utility then
    id-hash) EVEN at neutral/negative marginal utility — otherwise a group that needs a low-value filler to
    reach size_min would be wrongly dropped as NO_FEASIBLE_GROUP. Once feasible, switch to positive-marginal-
    gain-only optimisation (least_misery is non-monotone, so gain is on TOTAL utility). Deterministic tiebreaks;
    each pass adds exactly one member or halts -> terminates within size_max steps."""
    p = params or _SPEC_DEFAULT_PARAMS
    size_max = int((constraints or {}).get("size_max", p.get("size_max", _MAX_MVP_SIZE)))

    def total(members):
        return round(group_utility_components(members, constraints, params, pair_rel=pair_rel)["total"], 6)

    g = list(seed or [])
    g_ids = {_member_id(m) for m in g}
    while len(g) < size_max:
        cur_v = check_set_constraints(g, constraints, params, now_ts=now_ts)
        addable = [c for c in (feasible or []) if _member_id(c) not in g_ids]
        if not addable:
            break
        if any(code in _SHORTFALL for code in cur_v):
            # FEASIBILITY mode: only members introducing NO non-shortfall violation (no new hard block / SIZE_MAX)
            # and not worsening the violation set; pick fewest remaining violations, then highest utility, then id.
            scored = []
            for c in addable:
                v2 = check_set_constraints(g + [c], constraints, params, now_ts=now_ts)
                if any(code not in _SHORTFALL for code in v2) or len(v2) > len(cur_v):
                    continue
                scored.append((len(v2), -total(g + [c]), _id_hash(_member_id(c)), _member_id(c), c))
            if not scored:
                break
            pick = min(scored)[4]
            g.append(pick); g_ids.add(_member_id(pick))
            continue
        # OPTIMISE mode: positive marginal gain only (feasibility-preserving)
        base = total(g)
        best = None
        for c in addable:
            trial = g + [c]
            if check_set_constraints(trial, constraints, params, now_ts=now_ts):
                continue
            gain = round(total(trial) - base, 6)
            if gain > _EPS:
                key = (-gain, _id_hash(_member_id(c)), _member_id(c))
                if best is None or key < best[0]:
                    best = (key, c)
        if best is None:
            break
        g.append(best[1]); g_ids.add(_member_id(best[1]))
    return g

def local_repair(group, feasible, constraints, params, pair_rel=None, now_ts=None):
    """§15.3.4 — bounded, STRICTLY-improving passes: ADD to fill an unmet role, SWAP the member on the worst
    directed edge for a feasible alternative, REMOVE if size stays >= quorum and utility rises. Accept only a
    move with delta > EPS (6dp). Hard cap MAX_REPAIR_ITERS = 2*size_max*(|feasible|+1) => provable termination."""
    p = params or _SPEC_DEFAULT_PARAMS
    size_max = int((constraints or {}).get("size_max", p.get("size_max", _MAX_MVP_SIZE)))
    quorum = int((constraints or {}).get("quorum", p.get("quorum_default", 3)))
    g = list(group or [])
    cap = 2 * size_max * (len(feasible or []) + 1)
    iters = 0

    def total(members):
        return round(group_utility_components(members, constraints, params, pair_rel=pair_rel)["total"], 6)

    def feasible_ok(members):
        return not check_set_constraints(members, constraints, params, now_ts=now_ts)

    while iters < cap:
        iters += 1
        cur = total(g)
        cur_ids = {_member_id(m) for m in g}
        best_move, best_total = None, cur
        # (a) ADD
        if len(g) < size_max:
            for c in sorted((x for x in (feasible or []) if _member_id(x) not in cur_ids), key=_sort_key):
                trial = g + [c]
                if feasible_ok(trial):
                    t = total(trial)
                    if t > best_total + _EPS:
                        best_move, best_total = ("add", trial), t
        # (b) SWAP each member for a feasible alternative
        for i in range(len(g)):
            for c in sorted((x for x in (feasible or []) if _member_id(x) not in cur_ids), key=_sort_key):
                trial = [c if k == i else m for k, m in enumerate(g)]
                if feasible_ok(trial):
                    t = total(trial)
                    if t > best_total + _EPS:
                        best_move, best_total = ("swap", trial), t
        # (c) REMOVE if still >= quorum
        if len(g) - 1 >= quorum:
            for i in range(len(g)):
                trial = [m for k, m in enumerate(g) if k != i]
                if feasible_ok(trial):
                    t = total(trial)
                    if t > best_total + _EPS:
                        best_move, best_total = ("remove", trial), t
        if best_move is None:
            break
        g = best_move[1]
    return g

def max_by_utility(best, group, constraints, params, pair_rel=None):
    """Return the higher-utility FEASIBLE (members, utility). An infeasible group (utility None) can never win.
    EXACT-utility tie -> smaller group_signature (byte-deterministic across seed order and input permutation)."""
    gu = group_utility(group, constraints, params, pair_rel=pair_rel)
    if gu["utility"] is None:
        return best
    cand = (list(group), gu["utility"])
    if best is None:
        return cand
    if cand[1] > best[1] + _EPS:
        return cand
    if abs(cand[1] - best[1]) <= _EPS and group_signature(cand[0]) < group_signature(best[0]):
        return cand
    return best


# ----------------------------------------------------------------------------- §15.3.5 reservations + App C #8 race
def claim_group_seat(ledger, group_id, seat_ordinal, capacity, claimant):
    """App C #8 primitive — REUSES §14 `ks.claim_slot`, NO bespoke lock. Rejects seat_ordinal >= capacity
    BEFORE claiming (a claim past the last seat can never happen), then a first-claim-wins atomic insert on the
    composite key 'group_id#seatN'. SINGLE-PROCESS only (cross-process capacity needs the DB/queue — blocked_infra)."""
    if seat_ordinal >= int(capacity):
        return {"won": False, "error_code": "CAPACITY_EXCEEDED", "seat": None, "winner": None}
    key = "%s#seat%d" % (group_id, seat_ordinal)
    slot = ks.claim_slot(ledger if isinstance(ledger, dict) else {}, key, claimant)
    if slot.get("won"):
        return {"won": True, "error_code": "OK", "seat": key, "winner": claimant}
    return {"won": False, "error_code": "SLOT_TAKEN", "seat": key, "winner": slot.get("winner")}

def reserve_members(group, ledger, constraints, now_ts, capacity=None):
    """§15.3.5 — assign seats in a single DETERMINISTIC sorted pass; each accepting member claims the next seat
    via claim_group_seat, then kc.build_reservation(now=now_ts) [now_ts MANDATORY — build_reservation defaults to
    time.time()]. A last-seat loser routes through ks.resolve_race('slot_taken') (WITHDRAWN / coarse public
    reason / leak:False) + waitlist. `filled` can never exceed capacity by construction."""
    members = sorted(list(group or []), key=_sort_key)
    gid = group_signature(members)
    cap = int(capacity if capacity is not None else (constraints or {}).get("capacity") or len(members))
    led = ledger if isinstance(ledger, dict) else {}
    reservations, confirmed, rejected, filled = [], [], [], 0
    for m in members:
        res = claim_group_seat(led, gid, filled, cap, _member_id(m))
        if res["won"]:
            reservations.append(kc.build_reservation(res["seat"], _member_id(m), ttl_s=_RES_TTL, now=now_ts))
            confirmed.append(_member_id(m))
            filled += 1
        else:
            race = ks.resolve_race("slot_taken")
            rejected.append({"member": _member_id(m), "error_code": res["error_code"],
                             "public_reason": race["public_reason"], "state": race["to"], "leak": False})
    return {"group_id": gid, "reservations": reservations, "confirmed": confirmed, "rejected": rejected,
            "filled": filled, "capacity": cap, "capacity_ok": filled <= cap}


# ----------------------------------------------------------------------------- §15.3.6/7 invitations + replacement
def build_group_invitations(members, intent):
    """§15.3.6 — purpose-bound structured invites (kc.build_profile_view, clock-safe). CONSTRUCTED, not sent
    (the pilot has no messaging). Purpose = the intent's domain/goal."""
    intent = intent or {}
    purpose = (intent.get("goal") or {}).get("purpose") or intent.get("type") or intent.get("domain") or "social"
    return [kc.build_profile_view(m, purpose) for m in members or []]

def replacement_policy(group, constraints, remainder=None):
    """§15.3.7 — DATA-ONLY policy (no execution): waitlist on refusal, cancel-or-reform on quorum loss."""
    p = constraints or {}
    quorum = int(p.get("quorum") or p.get("quorum_default") or 3)
    waitlist = [_member_id(m) for m in sorted(list(remainder or []), key=_sort_key)]
    return {"on_refusal": "waitlist", "on_quorum_loss": "cancel_or_reform", "quorum": quorum, "waitlist": waitlist}


# ----------------------------------------------------------------------------- top-level gate + endpoint body
def dormant_response(intent, constraints=None, note=None):
    """The pilot-off response: group_formation is not enabled. Byte-identical-in-intent to the app.py honest-
    empty /api/agent/match branch. No algorithm runs to produce this."""
    return {"decision_type": "group_formation", "enabled": False, "override": False, "group": None,
            "members": [], "feasible": False,
            "pilot": {"enabled": False, "note": note or "group_formation is not enabled in this pilot (§15)"}}

def is_override_enabled(override):
    """The ONLY switch that runs the algorithm: True IFF override is a dict whose EXACT key
    'enable_group_formation' is boolean True. None / {} / wrong key / truthy string -> False (stays dormant)."""
    return isinstance(override, dict) and override.get("enable_group_formation") is True

def form_group(intent, candidates, constraints, params, pair_rel=None, now_ts=None, enabled_override=False):
    """§15.3 / App B.3 MVP. FIRST statement short-circuits to dormant unless enabled_override — the algorithm body
    is UNREACHABLE in the pilot. Pure (computes a reservation PLAN but performs no I/O). Result ALWAYS carries
    enabled:False (conformance scaffolding, never live)."""
    if not enabled_override:
        return dormant_response(intent, constraints)
    feasible = filter_hard_set_constraints(candidates, constraints, now_ts=now_ts)
    seeds = generate_role_complete_seeds(feasible, constraints, params, pair_rel=pair_rel)
    best = None
    for seed in seeds:
        g = greedy_marginal_add(seed, feasible, constraints, params, pair_rel=pair_rel, now_ts=now_ts)
        g = local_repair(g, feasible, constraints, params, pair_rel=pair_rel, now_ts=now_ts)
        if set_feasible(g, constraints, params, now_ts=now_ts):
            best = max_by_utility(best, g, constraints, params, pair_rel=pair_rel)
    if best is None:
        return {"decision_type": "group_formation", "enabled": False, "override": True, "group": None,
                "members": [], "utility": None, "feasible": False, "violations": ["NO_FEASIBLE_GROUP"]}
    members, utility = best
    gu = group_utility(members, constraints, params, pair_rel=pair_rel)
    roles = sorted({r for m in members for r in _member_roles(m)})
    # The quorum this group actually ran under — check_set_constraints reads constraints["quorum"]
    # first everywhere else, so reporting the config default here described a 4-seat padel court as
    # needing 3 and made the returned group disagree with the rule it was built to.
    _q = (constraints or {}).get("quorum")
    grp = kc.build_group(int(_q if _q else (params or _SPEC_DEFAULT_PARAMS)["quorum_default"]),
                         roles, (constraints or {}).get("pair_blocks"))
    return {"decision_type": "group_formation", "enabled": False, "override": True, "group": grp,
            "members": [_member_id(m) for m in members], "utility": utility,
            "components": gu["components"], "weighted": gu["weighted"], "feasible": True, "violations": []}

def run_group_formation(intent, candidates, constraints, cfg, override=None, now_ts=None, ledger=None, pair_rel=None):
    """The gated ENDPOINT body (wired at task #37 as POST /api/agent/group). Returns dormant_response UNLESS the
    EXACT test-only override is present. Never mutates PILOT_DECISION_TYPES; the result is always enabled:False."""
    if not is_override_enabled(override):
        return dormant_response(intent, constraints)
    try:
        params = load_group_params(cfg)
    except GroupConfigError as e:
        return dict(dormant_response(intent, constraints, note="group config invalid: %s" % e), error=str(e))
    fg = form_group(intent, candidates, constraints, params, pair_rel=pair_rel, now_ts=now_ts, enabled_override=True)
    if fg.get("members"):
        member_objs = [c for c in (candidates or []) if _member_id(c) in set(fg["members"])]
        if ledger is not None:
            fg["reservations"] = reserve_members(member_objs, ledger, constraints, now_ts=now_ts,
                                                  capacity=(constraints or {}).get("capacity"))
        fg["invitations"] = build_group_invitations(member_objs, intent)
        remainder = [c for c in (candidates or []) if _member_id(c) not in set(fg["members"])]
        fg["replacement"] = replacement_policy(fg["members"], dict(constraints or {}, quorum_default=params["quorum_default"]), remainder)
    return fg


# ----------------------------------------------------------------------------- introspection (tests/docs)
# §15.4 — concrete per-domain constraint presets (plain declarative dicts consumed by form_group via the same
# enabled_override path; group_formation stays pilot-off). Padel = a fixed 4-seat court; conversation = a
# native/learner balance with a language floor + moderator; walk = a small paced group; dota = role-complete stack.
DOMAIN_PACKS = {
    "dota":         {"mandatory_roles": ["carry", "support", "mid", "offlane"], "size_min": 5, "size_max": 5, "quorum": 5, "max_skill_spread": 2},
    "padel":        {"size_min": 4, "size_max": 4, "quorum": 4, "capacity": 4, "max_skill_spread": 2, "required_equipment": ["racket"]},
    "conversation": {"size_min": 3, "size_max": 6, "quorum": 3, "require_moderator": True, "diversity_axis": "lang_role"},
    "walk":         {"size_min": 2, "size_max": 8, "quorum": 2, "min_duration_min": 30},
}

def pack_for(domain):
    """Return a copy of the §15.4 constraint preset for a domain (empty dict for an unknown domain)."""
    return dict(DOMAIN_PACKS.get(str(domain or "").lower()) or {})


def summary():
    return {"groups_version": GROUPS_VERSION, "weight_keys": list(WEIGHT_KEYS), "spec_alias": dict(SPEC_ALIAS),
            "weight_source": "config", "max_mvp_size": _MAX_MVP_SIZE,
            "reuses": ["kleal_contracts", "kleal_states"], "enabled": False}
