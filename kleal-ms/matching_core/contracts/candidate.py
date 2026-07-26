# -*- coding: utf-8 -*-
"""§4 CandidateSnapshot — результат feature building для КОНКРЕТНОЙ версии intent.

Immutable snapshot: source, semantic_tier, feature groups, unknowns, версии данных/policy/config.
Заполняется Feature Builder (§6.1/§9.1); здесь — контракт + версионное клеймо.
"""

TIERS = ("T0", "T1", "T2", "T3", "T4", "T5")


def build_candidate_snapshot(candidate_id, *, source, tier, feature_groups=None, unknowns=None,
                             intent_version=None, profile_versions=None, config_version=None,
                             policy_version=None):
    if tier not in TIERS:
        raise ValueError("bad semantic_tier: %r" % tier)
    return {
        "candidate_id": candidate_id, "source": source, "semantic_tier": tier,
        "feature_groups": feature_groups or {}, "unknowns": list(unknowns or []),
        "versions": {"intent": intent_version, "profiles": profile_versions or {},
                     "config": config_version, "policy": policy_version},
    }
