# -*- coding: utf-8 -*-
"""Kleal — §22.2.0 / §23.4.1 contract registry + machine-checkable schema mirror (keyless, no FS/model).

Stage-0 of the implementation contract (§23.4) is «contracts + config validator authored BEFORE the engine».
This module makes that machine-checkable: a manifest listing every §4 entity builder + the versions in effect,
and a draft-07-ish schema mirror derived from the purpose-binding allow-lists in kleal_contracts, against which a
build_profile_view projection can be validated. Imports only the keyless shared modules."""
import kleal_contracts as kc
import kleal_states as ks

REGISTRY_VERSION = "registry-0.0.1"

# every §4 canonical entity -> its authoritative builder (the single source of the shape)
ENTITY_BUILDERS = {
    "evidence": "kc.build_evidence", "profile_view": "kc.build_profile_view",
    "receiving_policy": "kc.build_receiving_policy", "intent": "kc.compile_intent",
    "candidate_snapshot": "kc.build_candidate_snapshot", "proposal": "kc.build_proposal",
    "reservation": "kc.build_reservation", "match": "kc.build_match", "group": "kc.build_group",
    "plan": "kc.build_plan", "relationship_edge": "kc.build_relationship_edge",
}

def manifest(cfg=None):
    """The §22.2.0 stage-0 manifest: every entity builder + the config/contract/state versions in effect."""
    return {
        "registry_version": REGISTRY_VERSION,
        "contracts_version": kc.CONTRACTS_VERSION,
        "states_version": ks.STATES_VERSION,
        "config_version": (cfg or {}).get("config_version"),
        "config_sha": ((cfg or {}).get("_sha256") or "")[:12] or None,
        "entities": dict(ENTITY_BUILDERS),
        "state_machines": list(ks.STATE_MACHINES.keys()),
        "proposal_types": list(kc.PROPOSAL_TYPES),
        "contexts": list(kc.CONTEXTS),
    }

def contracts_schema():
    """§23.4.1 — a draft-07 schema mirror of the purpose-binding contracts, derived from the SAME allow-lists the
    engine uses (kc.PURPOSE_FIELDS / DISCLOSURE_STAGES / CONTEXTS). A ProfileView can be validated against it, so
    the contract is machine-checkable, not just prose."""
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "Kleal purpose-bound ProfileView",
        "type": "object",
        "required": ["view_id", "purpose", "context", "disclosure_stage", "fields"],
        "properties": {
            "view_id": {"type": "string"},
            "purpose": {"type": "string"},
            "context": {"type": "string", "enum": list(kc.CONTEXTS) + ["minimal"]},
            "disclosure_stage": {"type": "string", "enum": list(kc.DISCLOSURE_STAGES)},
            "fields": {"type": "object"},
        },
        "$defs": {
            "purpose_fields": {ctx: list(fields) for ctx, fields in kc.PURPOSE_FIELDS.items()},
        },
    }

def validate_profile_view(view):
    """Read-only check that a ProfileView conforms to contracts_schema() AND its projected fields are a subset of
    the context's allow-list (purpose binding). Returns a list of problems (empty == valid)."""
    problems = []
    sch = contracts_schema()
    if not isinstance(view, dict):
        return ["profile_view is not an object"]
    for req in sch["required"]:
        if req not in view:
            problems.append("missing required key %r" % req)
    ctx = view.get("context")
    allow = set(kc.PURPOSE_FIELDS.get(ctx) or ("name",))
    extra = set((view.get("fields") or {}).keys()) - allow
    if extra:
        problems.append("fields outside the %r allow-list: %s" % (ctx, sorted(extra)))
    if view.get("disclosure_stage") not in kc.DISCLOSURE_STAGES:
        problems.append("disclosure_stage not in the enum")
    return problems
