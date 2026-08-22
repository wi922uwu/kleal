# -*- coding: utf-8 -*-
"""Drop-in engine adapter: exposes the `core_v2` interface (`_core.*`) that services/matching/app.py
depends on, but routes all scoring through the clean-rebuild package `matching_core/`.

Full replacement of core_v2: app.py imports THIS as `_core` when KLEAL_ENGINE=matching_core (default).
The 22 interface points app.py uses (search + infer_domain/assign_tier/readiness_state/is_paused/
build_features/directional_score/reverse_features/reciprocal_score/assign_band/_presentation/load_config +
constants FEATURE_KEYS/TOP_N/NA/UNKNOWN/READINESS_RANK/READINESS_LABELS/TIER_KIND/BAND_RANK/BAND_LABELS) are
reproduced here with core_v2-identical signatures and card shape, so the frozen /api/agent/* contract and
the profile frontend keep working unchanged. Behaviour = matching_core (spec-faithful + Вердикт fixes,
notably critical-unknown blocking outreach).
"""
import os
import sys
import time

# matching_core lives at repo root (/root/kleal-ms/matching_core on pod). app.py's script dir is
# services/matching, so add repo root (two levels up) to import the package.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from matching_core.config import validator as _V
from matching_core.feature_builder import builder as _FB
from matching_core.feature_builder import unknowns as _UNK
from matching_core.relevance_engine import relevance as _RL
from matching_core.relevance_engine import decision as _DE
from matching_core.reciprocity_readiness import readiness as _RD
from matching_core.retrieval import retriever as _RET
from matching_core.orchestrator import search as _SEARCH   # for _reverse_features

# ------------------------------------------------------------------ constants (core_v2-compatible)
FEATURE_KEYS = _FB.FEATURE_KEYS
NA, UNKNOWN = _FB.NA, _FB.UNKNOWN
TOP_N = 8
PER_BUCKET = 3
READINESS_RANK = _RD.READINESS_RANK
READINESS_LABELS = _RD.LABELS
BAND_RANK = _DE.BAND_RANK
BAND_LABELS = _DE.BAND_LABELS
TIER_KIND = {"T0": "reciprocal", "T1": "exact", "T2": "related", "T3": "adjacent", "T4": "alternative"}
ENGINE_NAME = "matching_core"

_TYPE2DOMAIN = {"social": "social_meet", "social_meet": "social_meet", "walk": "walk", "games": "games",
                "gaming": "games", "sport": "sport_activity", "sport_activity": "sport_activity",
                "networking": "professional_networking", "professional_networking": "professional_networking",
                "language": "language_exchange", "language_exchange": "language_exchange", "dating": "dating",
                "culture": "culture_event", "culture_event": "culture_event", "watch": "watch_together",
                "watch_together": "watch_together", "coworking": "coworking"}


# ------------------------------------------------------------------ config
def load_config(path=None, expect_sha=None):
    """Same sha-pinned YAML as core_v2 (config_version matching-core-2.0.0, PINNED_SHA 2b7c24eb…)."""
    if expect_sha:
        return _V.load_config(path, expect_sha=expect_sha)
    return _V.load_config(path)


# ------------------------------------------------------------------ helpers (core_v2 signatures)
def infer_domain(intent, cat_of=None):
    intent = intent or {}
    t = str(intent.get("type") or "").lower()
    if t == "dating":
        return "dating"
    topics = [str(x).lower() for x in (intent.get("topics") or [])]
    blob = " ".join(topics + [str(intent.get("title") or "")]).lower()
    if any(w in blob for w in ("walk", "stroll", "прогул", "гуля")):
        return "walk"
    if any(w in blob for w in ("cowork", "поработ")):
        return "coworking"
    if "watch" in blob or "смотреть" in blob:
        return "watch_together"
    if t in _TYPE2DOMAIN:
        return _TYPE2DOMAIN[t]
    if callable(cat_of):
        for x in topics:
            try:
                b = cat_of(x)[0]
            except Exception:
                b = None
            if b in _TYPE2DOMAIN:
                return _TYPE2DOMAIN[b]
    return "social_meet"


def assign_tier(intent, cand, topics=None, H=None):
    """matching_core provenance tier (T0 reciprocal / T1 exact / T2 parent / T3 adjacent / T4 non-person /
    T5 none). topics/H accepted for signature-compat; matching_core uses its own taxonomy."""
    return _RET.assign_tier(intent or {}, cand or {})


def is_paused(cand, now_ts=None):
    return _RD.is_paused(cand or {}, now_ts)


def readiness_state(cand, domain, now_ts, cfg, received_24h=0):
    return _RD.readiness_state(cand or {}, domain, now_ts, cfg, received_24h)


def build_features(intent, prof, cand, domain, H=None, role_conflict=None):
    return _FB.build_features(intent or {}, prof or {}, cand or {}, domain)


def reverse_features(intent, prof, cand, domain, H=None, role_conflict=None):
    return _SEARCH._reverse_features(intent or {}, prof or {}, cand or {}, domain)


def directional_score(F, dom_cfg, priors):
    return _RL.directional_score(F, dom_cfg, priors)


def reciprocal_score(a, b):
    return _RL.reciprocal(a, b)


def assign_band(lcb, cov, bands):
    return _DE.band(lcb, cov, bands)


def _presentation(F, d_ab, dom_cfg):
    """Return (reasons_ru, reasons_en, legacy_reasons, gap_ru, gap_en) — the tuple core_v2 emits."""
    p = _DE.presentation(F, dom_cfg)
    rs_ru, rs_en = p.get("reasons_ru") or [], p.get("reasons_en") or []
    return rs_ru, rs_en, (rs_en or rs_ru), p.get("gap_ru"), p.get("gap_en")


def _slate(items, top_n=None):
    """Diversify by bucket + cap TOP_N (identical to core_v2._slate, including the `top_n` widening
    that lets §15 assemble a group larger than the eight-person 1:1 slate)."""
    n = int(top_n or TOP_N)
    per = PER_BUCKET if n <= TOP_N else max(PER_BUCKET, -(-n // 2))
    buckets = {it.get("bucket") or "other" for it in items}
    cap = per if len(buckets) > 2 else n
    seen, out = {}, []
    for it in items:
        b = it.get("bucket") or "other"
        if seen.get(b, 0) >= cap:
            continue
        seen[b] = seen.get(b, 0) + 1
        out.append(it)
        if len(out) >= n:
            break
    return out


# ------------------------------------------------------------------ main entry: search()
def search(intent, prof, ctx, candidates, H, cfg, top_n=None):
    """Score policy-ALLOWED candidates via matching_core, emit the core_v2 card shape + (slate, meta).
    `candidates` are already hard-gated by app.py; H injects app.py taxonomy (used only for the bucket
    label). matching_core does the relevance/reciprocity/readiness/band math (+ critical-unknown gate)."""
    intent, prof, ctx = intent or {}, prof or {}, ctx or {}
    cat_of = (H or {}).get("cat_of")
    domain = infer_domain(intent, cat_of)
    dom_cfg = cfg["domains"].get(domain) or cfg["domains"]["social_meet"]
    priors = _RL.priors_from_config(cfg)
    bands = cfg["user_facing_bands"]
    topics = [str(t).lower() for t in (intent.get("topics") or [])]
    now_ts = ctx.get("now") or time.time()
    received24 = ctx.get("received24") or {}
    out = []
    for c in candidates:
        if is_paused(c, now_ts):
            continue
        tier = assign_tier(intent, c)
        if tier == "T5":
            continue
        if tier == "T3" and not intent.get("adjacentAllowed", True):
            continue
        if tier == "T2" and intent.get("exactMatchRequired"):
            continue
        F = build_features(intent, prof, c, domain)
        d_ab = directional_score(F, dom_cfg, priors)
        d_ba = directional_score(reverse_features(intent, prof, c, domain), dom_cfg, priors)
        rec = reciprocal_score(d_ab, d_ba)
        disc_ok = (d_ab["lcb"] >= float(dom_cfg["discovery_min_lcb"]) and
                   d_ab["coverage"] >= float(dom_cfg["discovery_min_coverage"]))
        if not disc_ok and tier not in ("T0", "T1"):
            continue
        band = assign_band(d_ab["lcb"], d_ab["coverage"], bands) if disc_ok else "needs_clarification"
        readiness = readiness_state(c, domain, now_ts, cfg,
                                    received24.get(str(c.get("name", "")).strip().lower(), 0))
        crit_unknown = _UNK.high_impact_unknown(F, intent, domain)   # Вердикт#8: критичный unknown -> нет outreach
        outreach_tier_ok = tier in ("T0", "T1") or (tier == "T2" and bool(intent.get("broadConsent")))
        can_outreach = (outreach_tier_ok and readiness == "open_now" and not crit_unknown and
                        d_ab["lcb"] >= float(dom_cfg["outreach_min_lcb"]) and
                        d_ab["coverage"] >= float(dom_cfg["outreach_min_coverage"]))
        rs_ru, rs_en, legacy_reasons, gap_ru, gap_en = _presentation(F, d_ab, dom_cfg)
        matched = F["semantic_activity"][2] or ""
        if callable(cat_of):
            try:
                bucket = (cat_of(matched.split(", ")[0])[0] if matched else
                          cat_of((c.get("interests") or ["x"])[0])[0]) or "other"
            except Exception:
                bucket = matched.split(", ")[0] if matched else "other"
        else:
            bucket = (matched.split(", ")[0] if matched else (c.get("interests") or ["other"])[0])
        km_txt = F["location_feasibility"][2] if F["location_feasibility"][0] in (_FB.K_MATCH, _FB.K_MISM) else ""
        km = float(km_txt.split(" ")[0]) if km_txt else c.get("km")
        agree = bool(can_outreach)
        note = ("Agent agreed — " + (legacy_reasons[0] if legacy_reasons else "good fit")) if agree else \
               ("Agent: not reachable now (%s)" % READINESS_LABELS[readiness][1]
                if readiness != "open_now" else
                ("Agent: needs clarification" if (band == "needs_clarification" or crit_unknown)
                 else "Agent: fit too weak"))
        band_ru, band_en = BAND_LABELS[band]
        rdy_ru, rdy_en = READINESS_LABELS[readiness]
        out.append({
            # ---- legacy card contract (buddy/_card + profile UI keep rendering) ----
            "name": c.get("name"), "score": round(d_ab["lcb"] * 100, 1), "tier": tier,
            "kind": TIER_KIND.get(tier, "related"), "km": km, "vibe": c.get("vibe"),
            "open": c.get("open"), "verified": c.get("verified"), "age": c.get("age"),
            "interests": c.get("interests") or [], "role": c.get("role"),
            "dealBreakers": c.get("dealBreakers"), "reasons": legacy_reasons or rs_en,
            "agree": agree, "note": note, "bucket": bucket,
            # ---- Matching Core (spec) ----
            "band": band, "band_ru": band_ru, "band_en": band_en,
            "reasons_ru": rs_ru, "reasons_en": rs_en, "gap_ru": gap_ru, "gap_en": gap_en,
            "coverage": d_ab["coverage"], "lcb": d_ab["lcb"], "reciprocal": rec,
            "unknowns": d_ab["unknowns"], "can_outreach": can_outreach,
            "readiness": readiness, "readiness_ru": rdy_ru, "readiness_en": rdy_en,
            "trace": {"tier": tier, "policy": "ALLOW", "domain": domain,
                      "a_to_b": d_ab, "b_to_a": d_ba, "reciprocal": rec, "band": band,
                      "readiness": readiness, "critical_unknown": crit_unknown,
                      "config_version": cfg.get("config_version"), "engine": ENGINE_NAME},
        })
    out.sort(key=lambda x: (BAND_RANK[x["band"]], READINESS_RANK[x["readiness"]], -x["reciprocal"],
                            -x["lcb"], -x["coverage"], str(x["name"])))
    meta = {"core": ENGINE_NAME, "config_version": cfg.get("config_version"), "domain": domain,
            "config_sha": (cfg.get("_sha256") or "")[:12]}
    return _slate(out, top_n), meta


# ---------------------------------------------------------------- adapter completeness
# This module is a DROP-IN for core_v2: app.py reaches the engine only through `_core.*`, so any
# name core_v2 exports and this one does not is a crash waiting for the code path that uses it.
# Two were missing and only surfaced when the admin person-card route was restored:
# `_in_quiet_hours` (crashed with AttributeError) and `ALL_DOMAINS` (used by the same report, one
# line further down, so it would have crashed on the next request anyway).
#
# Both are engine-independent: a domain list from the spec, and plain wall-clock arithmetic. They
# are implemented here rather than imported from core_v2 on purpose — the whole point of the
# KLEAL_ENGINE switch is that the two engines do not depend on each other.

# §18.1 domain table. Kept identical to core_v2.ALL_DOMAINS; the config's `domains` section is the
# runtime source, this tuple is the enumeration order the reports iterate in.
ALL_DOMAINS = ("social_meet", "walk", "games", "language_exchange", "sport_activity",
               "culture_event", "professional_networking", "watch_together", "coworking", "dating")


def _hhmm_to_min(s):
    """'22:00' -> 1320. None when unparseable, so a malformed policy disables the check rather
    than raising inside a ranking request."""
    try:
        h, m = str(s).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def _in_quiet_hours(now_min, start, end):
    """Is `now_min` (minutes since local midnight) inside the [start, end) quiet window?
    The window may wrap midnight — 22:00→09:00 is the default receiving policy — so the wrapped
    case is tested as two half-open ranges, not as a single comparison."""
    a, b = _hhmm_to_min(start), _hhmm_to_min(end)
    if a is None or b is None or now_min is None:
        return False
    if a <= b:
        return a <= now_min < b
    return now_min >= a or now_min < b


def explain(intent, prof, ctx, cand, H, cfg):
    """Per-pair decision trace (§21.3) — the admin lab's answer to «почему мне не попадается X».

    Neither this adapter nor the trimmed core_v2 on the pod had it, so the panel's pair view had
    been returning the slate-wide diagnostic and failing to find a trace in it. It re-runs the SAME
    calculation `search()` does for one candidate and records each gate as it is applied, so the
    steps cannot drift from the ranking: every early `continue` in search() has a step here.

    Returns {"name", "shown", "steps": [{"step", "ok", "detail"}], "drop_reason"}.
    """
    intent, prof, ctx = intent or {}, prof or {}, ctx or {}
    cat_of = (H or {}).get("cat_of")
    domain = infer_domain(intent, cat_of)
    dom_cfg = cfg["domains"].get(domain) or cfg["domains"]["social_meet"]
    priors = _RL.priors_from_config(cfg)
    bands = cfg["user_facing_bands"]
    now_ts = ctx.get("now") or time.time()
    received24 = ctx.get("received24") or {}
    steps = []

    def step(name, ok, detail):
        steps.append({"step": name, "ok": bool(ok), "detail": str(detail)})

    def done(reason):
        return {"name": cand.get("name"), "shown": False, "steps": steps, "drop_reason": reason}

    step("domain", True, "%s (weights from %s)" % (domain, cfg.get("config_version")))

    if is_paused(cand, now_ts):
        step("availability", False, "opted out of retrieval (paused / receiving.status)")
        return done("paused: not in the searchable pool")
    step("availability", True, "active")

    tier = assign_tier(intent, cand)
    if tier == "T5":
        step("semantic tier", False, "T5 — no topical overlap with the request")
        return done("no meaningful overlap with the requested topic")
    if tier == "T3" and not intent.get("adjacentAllowed", True):
        step("semantic tier", False, "T3 (adjacent) but the request disallows adjacent matches")
        return done("adjacent match, and the request asked for exact only")
    if tier == "T2" and intent.get("exactMatchRequired"):
        step("semantic tier", False, "T2 (related) but exactMatchRequired is set")
        return done("related match, and the request asked for exact only")
    step("semantic tier", True, "%s — %s" % (tier, TIER_KIND.get(tier, tier)))

    F = build_features(intent, prof, cand, domain)
    d_ab = directional_score(F, dom_cfg, priors)
    d_ba = directional_score(reverse_features(intent, prof, cand, domain), dom_cfg, priors)
    rec = reciprocal_score(d_ab, d_ba)
    step("relevance a->b", True, "lcb=%.3f coverage=%.3f mean=%.3f"
         % (d_ab["lcb"], d_ab["coverage"], d_ab.get("mean", 0.0)))
    step("relevance b->a", True, "lcb=%.3f coverage=%.3f" % (d_ba["lcb"], d_ba["coverage"]))
    step("reciprocal", True, "%.3f = 0.70*min(lcb) + 0.30*mean(lcb)" % rec)

    disc_ok = (d_ab["lcb"] >= float(dom_cfg["discovery_min_lcb"]) and
               d_ab["coverage"] >= float(dom_cfg["discovery_min_coverage"]))
    if not disc_ok and tier not in ("T0", "T1"):
        step("discovery threshold", False,
             "lcb %.3f < %.3f or coverage %.3f < %.3f, and the tier is not exact"
             % (d_ab["lcb"], float(dom_cfg["discovery_min_lcb"]),
                d_ab["coverage"], float(dom_cfg["discovery_min_coverage"])))
        return done("below the discovery floor for this domain")
    step("discovery threshold", True,
         "passed" if disc_ok else "below the floor, kept because the tier is %s (exact)" % tier)

    band = assign_band(d_ab["lcb"], d_ab["coverage"], bands) if disc_ok else "needs_clarification"
    readiness = readiness_state(cand, domain, now_ts, cfg,
                               received24.get(str(cand.get("name", "")).strip().lower(), 0))
    step("band", True, "%s" % band)
    step("readiness", readiness == "open_now", "%s" % readiness)

    crit = _UNK.high_impact_unknown(F, intent, domain)
    step("critical unknowns", not crit, "none" if not crit else str(crit))
    outreach_tier_ok = tier in ("T0", "T1") or (tier == "T2" and bool(intent.get("broadConsent")))
    can_outreach = (outreach_tier_ok and readiness == "open_now" and not crit and
                    d_ab["lcb"] >= float(dom_cfg["outreach_min_lcb"]) and
                    d_ab["coverage"] >= float(dom_cfg["outreach_min_coverage"]))
    step("outreach permission", can_outreach,
         "may be proposed to" if can_outreach else "discoverable, but not auto-proposable")
    return {"name": cand.get("name"), "shown": True, "steps": steps, "drop_reason": None,
            "band": band, "readiness": readiness, "tier": tier, "reciprocal": rec,
            "lcb": d_ab["lcb"], "coverage": d_ab["coverage"], "can_outreach": can_outreach}
