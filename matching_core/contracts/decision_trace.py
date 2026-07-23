# -*- coding: utf-8 -*-
"""§21.3 Decision trace — аудируемый след одного (search, candidate) для replay.

Содержит ВСЕ версии (intent/profiles/policy/config/model) и промежуточные величины раздельно
(policy, semantic_tier, evidence, directional a→b/b→a, reciprocal, readiness, allocation, reason_keys).
Replay по этому следу обязан воспроизвести результат той же версии конфигурации (C#24, §23.4.8).
"""


def build_decision_trace(search_id, candidate_id, *, intent_version, profile_versions=None,
                         purpose_id=None, policy=None, semantic_tier=None, evidence=None,
                         directional=None, reciprocal_relevance=None, readiness=None,
                         allocation=None, reason_keys=None, config_version=None, model_versions=None):
    return {
        "search_id": search_id, "candidate_id": candidate_id, "intent_version": intent_version,
        "profile_versions": profile_versions or {}, "purpose_id": purpose_id,
        "policy": policy or {"decision": None, "version": None},
        "semantic_tier": semantic_tier,
        "evidence": evidence or [],
        "directional": directional or {"a_to_b": None, "b_to_a": None},
        "reciprocal_relevance": reciprocal_relevance, "readiness": readiness,
        "allocation": allocation or {"position": None, "exploration": False},
        "reason_keys": list(reason_keys or []),
        "config_version": config_version, "model_versions": model_versions or {},
    }
