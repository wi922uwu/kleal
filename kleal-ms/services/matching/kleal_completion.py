# -*- coding: utf-8 -*-
"""Kleal — §10.2 completion factors (transparent operational signals; NEVER an opaque social rating).

In the MVP, completion is NOT turned into a separate "person score". This module surfaces a small set of
INDEPENDENT, named operational signals — each transparent, none combined into an aggregate. Safety reports,
sensitive inferences and single negative reviews are excluded BY CONSTRUCTION: the helper only ever reads
availability / capacity / technical-compat fields. Read-only, keyless; never feeds scoring.
"""
MAX_PENDING = 6   # mirrors app.MAX_PENDING (capacity-headroom denominator; not re-deciding capacity here)

# §10.2 hard invariant — these are NEVER read into a completion factor (no opaque social rating). The lists
# name REAL candidate fields so the guarantee is verifiable (see the C10 test that asserts none appear).
EXCLUDES = {
    "safety_reports": ["safetyFlags", "sensitivity", "accountStatus", "suspended"],
    "single_negative_reviews": ["blocksMe", "declinedOwnerDaysAgo"],   # a decline cooldown is a GATE, not a rating
    "sensitive_inferences": ["slots", "visibility"],
}

def _sig(key, ru, en, state, value=None):
    return {"key": key, "label_ru": ru, "label_en": en, "state": state, "value": value, "transparent": True}

def completion_factors(candidate, intent, now_ts=None, received_24h=0):
    """§10.2: a read-only dict of TRANSPARENT, independently-named operational signals — NEVER summed into a
    score, NEVER a person rating. Reads ONLY lastActiveDays / pending / receiving.proposal_budget / formats
    and the intent's mode; safety / sensitive / single-review fields are excluded by construction."""
    c = candidate or {}
    intent = intent or {}
    signals = []

    # availability freshness — read-only mirror of the existing lastActiveDays<=3 "recently active" signal
    lad = c.get("lastActiveDays")
    fresh = "fresh" if (isinstance(lad, (int, float)) and lad <= 3) else ("stale" if isinstance(lad, (int, float)) else "unknown")
    signals.append(_sig("availability_fresh", "Активность за 3 дня", "Active in the last 3 days", fresh, lad))

    # capacity headroom + active plans — the SAME pending count the deterministic capacity gate uses
    pending = c.get("pending")
    if isinstance(pending, (int, float)):
        p = int(pending)
        cap = "at_capacity" if p >= MAX_PENDING else ("near_capacity" if p >= MAX_PENDING - 1 else "has_headroom")
        signals.append(_sig("capacity_headroom", "Свободные слоты", "Capacity headroom", cap, "%d/%d" % (p, MAX_PENDING)))
        signals.append(_sig("active_plans", "Активные планы", "Active plans (proxy)", "counted", p))
    else:
        signals.append(_sig("capacity_headroom", "Свободные слоты", "Capacity headroom", "unknown", None))
    budget = (c.get("receiving") or {}).get("proposal_budget")
    if isinstance(budget, dict) and budget:
        signals.append(_sig("proposal_budget", "Бюджет предложений", "Proposal budget", "declared", dict(budget)))

    # technical compatibility for online activity — only meaningful for online intents; never assumed
    mode = str(intent.get("mode") or "").lower()
    if mode == "online" or intent.get("allowOnlineFallback"):
        fmts = [str(f).lower() for f in (c.get("formats") or [])]
        tc = ("unknown" if not fmts else
              ("compatible" if any(m in f for f in fmts for m in ("online", "any", "both")) else "incompatible"))
    else:
        tc = "not_applicable"
    signals.append(_sig("technical_compat", "Тех. совместимость (онлайн)", "Technical compatibility (online)", tc))

    return {
        "signals": signals,
        "not_collected": {
            "response_latency": "not_collected — no per-candidate latency; silence/expired_no_response stays NEUTRAL, never read as latency",
            "recent_no_show": "not_collected — no no-show history; a decline cooldown is a gate, not a reliability rating",
            "min_duration_capability": "intent_side_only — only the searcher's window carries min_duration",
            "host_venue_room": "post_pilot — group/event flows disabled",
        },
        "excludes": EXCLUDES,
        "aggregate_score": None,          # §10.2: there is NO combined completion / person score — by design
        "note": "transparent per-signal operational readiness; never an opaque social rating (§10.2)",
    }

# §10.1 the six receiving-readiness states — surfaced (core_v2.readiness_state emits them; this only EXPLAINS,
# it never recomputes readiness). Readiness is domain-dependent (open to language practice, closed to dating).
READINESS_EXPLAIN = {
    "open_now":          {"meaning_en": "proposals of this type allowed in the current window", "outreach_allowed": True,  "domain_dependent": True},
    "open_later":        {"meaning_en": "may save, do not send until the window opens",           "outreach_allowed": False, "domain_dependent": False},
    "passive_discovery": {"meaning_en": "may show in list/map; personal proposal forbidden",       "outreach_allowed": False, "domain_dependent": True},
    "busy":              {"meaning_en": "temporarily do not send",                                 "outreach_allowed": False, "domain_dependent": False},
    "paused":            {"meaning_en": "excluded from retrieval for that purpose",                "outreach_allowed": False, "domain_dependent": False},
    "unknown":           {"meaning_en": "no personal outreach without explicit setting or a probe", "outreach_allowed": False, "domain_dependent": False},
}
