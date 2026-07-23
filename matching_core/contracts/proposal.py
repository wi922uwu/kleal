# -*- coding: utf-8 -*-
"""§4 Proposal — структурированное предложение.

Каждый write имеет idempotency key и version (§23.2 п.13). TTL обязателен; истёкший proposal нельзя
принять (C#9). disclosure ограничивает payload (§8.1 disclosure policy).
"""

STATUS = ("draft", "sent", "accepted", "declined", "countered", "withdrawn", "expired")


def build_proposal(proposal_id, frm, to, intent_id, *, payload=None, allowed_disclosure=None,
                   ttl_sec=720 * 60, created_at=None, idempotency_key=None, status="draft",
                   intent_version=None, policy_version=None, config_version=None, version=1):
    if status not in STATUS:
        raise ValueError("bad proposal status: %r" % status)
    expires_at = (float(created_at) + ttl_sec) if created_at is not None else None
    return {
        "proposal_id": proposal_id, "from": frm, "to": to, "intent_id": intent_id,
        "payload": payload or {}, "allowed_disclosure": list(allowed_disclosure or []),
        "status": status, "created_at": created_at, "expires_at": expires_at,
        "idempotency_key": idempotency_key or ("prop:%s:%s:%s" % (frm, to, intent_id)),
        "versions": {"intent": intent_version, "policy": policy_version, "config": config_version},
        "version": int(version),
    }


def is_expired(proposal, now):
    exp = proposal.get("expires_at")
    return bool(exp is not None and float(now) >= float(exp))
