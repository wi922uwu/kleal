# -*- coding: utf-8 -*-
"""§4 Match — взаимное согласие ПОСЛЕ revalidation (§8.2), не показ рекомендации (§2).

Привязан к purpose_id (§8.3): materialized Match Capsule для конкретного purpose, с версией и TTL.
Disclosure state растёт стадиями; точное место/контакты раскрываются только после нужного уровня согласия.
"""


def build_match(match_id, participants, purpose_id, *, disclosure_state="limited", links=None,
                created_at=None, intent_versions=None, policy_version=None, config_version=None):
    return {
        "match_id": match_id, "participants": list(participants), "purpose_id": purpose_id,
        "disclosure_state": disclosure_state, "links": links or {},
        "created_at": created_at, "status": "active",
        "versions": {"intents": intent_versions or {}, "policy": policy_version, "config": config_version},
    }
