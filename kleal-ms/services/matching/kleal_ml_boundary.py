# -*- coding: utf-8 -*-
"""Kleal — §10.3 ML migration boundary (declarative manifest; NO ML runs in the pilot).

The spec adds learnable models in layers, but hard gates, privacy, purpose binding, block, capacity and
disclosure STAY deterministic policy and are never given to a model. This manifest declares the roadmap,
states that the calibrated acceptance probabilities are absent BY DESIGN (never fabricated), and pins the
no-model-in-gates invariant. Keyless, no model access.
"""
ML_BOUNDARY = {
    # §10.3 the six ML layers — declared, not implemented. Calibrated probabilities need data + a model version.
    "roadmap": [
        {"layer": 1, "name": "intent_classification_and_slot_extraction", "status": "future"},
        {"layer": 2, "name": "candidate_retrieval_recall",                "status": "future"},
        {"layer": 3, "name": "calibrated_P_response",                     "status": "blocked_calibration"},
        {"layer": 4, "name": "calibrated_P_accept_by_direction_and_domain","status": "blocked_calibration"},
        {"layer": 5, "name": "calibrated_P_completion",                   "status": "blocked_calibration"},
        {"layer": 6, "name": "learning_to_rank_with_off_policy_eval",     "status": "blocked_calibration"},
    ],
    # NEVER stubbed to a placeholder probability (e.g. 0.5) — absent by design until calibrated.
    "probabilities": {"P_response": "absent_by_design", "P_accept": "absent_by_design", "P_completion": "absent_by_design"},
    "probabilities_note": "a calibrated probability requires sufficient data + a stated model version (§9.4/§10.3); "
                          "the rule-based MVP never fabricates one",
    # §10.3: these stay deterministic policy and are NOT given to any model.
    "deterministic_policy": [
        {"policy": "hard_gates",      "where": "app._hard_gates / _policy_decision",                          "model_driven": False},
        {"policy": "privacy",         "where": "app._hard_gates (visibility) / kc.build_profile_view",         "model_driven": False},
        {"policy": "purpose_binding", "where": "kc.DOMAIN_TO_CONTEXT / PURPOSE_FIELDS / app._cross_purpose_blocked", "model_driven": False},
        {"policy": "block",           "where": "app._hard_gates (blocked / blocksMe)",                         "model_driven": False},
        {"policy": "capacity",        "where": "app._hard_gates (pending) / core_v2.readiness_state (budget)",  "model_driven": False},
        {"policy": "disclosure",      "where": "kc.build_proposal clamp / app._revalidate_disclosure",         "model_driven": False},
    ],
    "invariant": "no_model_in_gates: hard gates, privacy, purpose binding, block, capacity and disclosure stay "
                 "deterministic policy and are never given to a model (§10.3)",
}

def assert_no_model_in_gates():
    """Return the names of any deterministic-policy entries erroneously flagged model_driven (empty = invariant holds)."""
    return [p["policy"] for p in ML_BOUNDARY["deterministic_policy"] if p.get("model_driven")]

# §23.4.7 — the ML interfaces are declared UP FRONT as typed stubs that return the absent-by-design sentinel and
# NEVER a fabricated probability/vector (no random floats standing in for a calibrated model). Keyless, no model.
_ABSENT = "absent_by_design"

def feature_vector(*args, **kwargs):
    """§10.3 feature interface stub — returns the absent sentinel, never a fabricated vector."""
    return {"status": _ABSENT, "vector": None}

def predict_response(*args, **kwargs):
    return {"status": _ABSENT, "probability": None, "model_version": _ABSENT}

def predict_acceptance(*args, **kwargs):
    return {"status": _ABSENT, "probability": None, "model_version": _ABSENT}

def predict_completion(*args, **kwargs):
    return {"status": _ABSENT, "probability": None, "model_version": _ABSENT}

def model_version():
    """The active decision model: rule-based deterministic; the calibrated ML models are absent by design."""
    return {"scoring": "rule_based_deterministic", "ml": _ABSENT}
