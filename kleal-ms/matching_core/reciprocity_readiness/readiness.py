# -*- coding: utf-8 -*-
"""§10 Reciprocity, readiness и вероятность результата.

Relevance («подходит ли задаче») и readiness («готов ли получать сейчас») — РАЗНЫЕ величины, НЕ
складываются (§10). Completion в MVP — прозрачные operational signals, НЕ «балл человека» (§10.2).
Hard gates/privacy/purpose/block/capacity/disclosure остаются deterministic policy (§10.3, §23.2 п.4/6).
"""
import time

# §10.1 состояния receiving readiness.
READINESS = ("open_now", "open_later", "passive_discovery", "busy", "paused", "unknown")
READINESS_RANK = {"open_now": 0, "open_later": 1, "unknown": 2, "passive_discovery": 3, "busy": 4, "paused": 5}
LABELS = {
    "open_now": ("открыт(а) сейчас", "open now"),
    "open_later": ("не сейчас — тихие часы", "later (quiet hours)"),
    "passive_discovery": ("только в подборке", "discovery only"),
    "busy": ("сейчас занят(а)", "busy right now"),
    "paused": ("на паузе", "paused"),
    "unknown": ("доступность не настроена", "availability not set"),
}


def _hhmm(s):
    try:
        h, m = str(s).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def _in_quiet(now_min, start, end):
    a, b = _hhmm(start), _hhmm(end)
    if a is None or b is None or now_min is None:
        return False
    return (a <= now_min < b) if a <= b else (now_min >= a or now_min < b)


def is_paused(cand, now_ts=None):
    if cand.get("paused"):
        return True
    r = cand.get("receiving")
    if isinstance(r, dict) and str(r.get("status") or "").lower() == "paused":
        pu = r.get("paused_until")
        return True if pu is None else (float(pu) > (now_ts or time.time()))
    return False


def readiness_state(cand, domain, now_ts, cfg, received_24h=0):
    """§10.1. Источники по приоритету: receiving policy (§4.4) -> демо-флаг open -> unknown.
    unknown ≠ открытость: без policy/probe personal outreach нет."""
    if is_paused(cand, now_ts):
        return "paused"
    r = cand.get("receiving")
    out_cfg = (cfg or {}).get("outreach") or {}
    if not isinstance(r, dict):
        if cand.get("open") is True:
            return "open_now"
        if cand.get("open") is False:
            return "busy"
        return "unknown"
    if str(r.get("status") or "").lower() == "busy":
        return "busy"
    cap = (r.get("proposal_budget") or {}).get("per_24h") or out_cfg.get("max_proposals_received_per_user_24h") or 4
    if received_24h >= int(cap):
        return "busy"                                          # proposal fatigue
    doms = r.get("allowed_domains")
    if isinstance(doms, list) and doms and domain not in doms:
        return "passive_discovery"
    q = r.get("quiet_hours") or {}
    defaults = out_cfg.get("quiet_hours_local") or ["22:00", "09:00"]
    if now_ts:
        local_min = int((now_ts // 60 + int(q.get("tz_offset_min", 120))) % 1440)
        if _in_quiet(local_min, q.get("start") or defaults[0], q.get("end") or defaults[-1]):
            return "open_later"
    if r.get("passive_outreach") is False:
        return "passive_discovery"
    return "open_now"


def completion_factors(cand, now_ts=None):
    """§10.2 прозрачные operational signals (НЕ непрозрачный социальный рейтинг). Возвращает dict факторов.
    Safety reports / sensitive inferences / единичные отзывы сюда НЕ входят."""
    return {
        "availability_fresh": bool(cand.get("open") is not None),
        "can_meet_min_duration": (cand.get("availableMinutes") is None) or bool(cand.get("availableMinutes", 0) >= (cand.get("minMeetMin") or 0)),
        "response_latency_band": cand.get("responseLatencyBand"),      # 'fast'/'medium'/'slow' или None
        "recent_no_show": bool(cand.get("recentNoShow")),              # контекстный reliability signal
        "active_plans": int(cand.get("activePlans") or 0),
        "tech_compatible": cand.get("techCompatible"),                # для online
        "has_host_venue": cand.get("hasHostOrVenue"),                 # для group/event
    }


# §10.3 ML-граница: что может стать ML-слоем, а что ОСТАЁТСЯ deterministic policy.
ML_LAYERS = ("intent_classification", "retrieval_recall", "p_response", "p_accept", "p_completion", "learning_to_rank")
DETERMINISTIC_FOREVER = ("hard_gates", "privacy", "purpose_binding", "block", "capacity", "disclosure")


def ml_boundary_manifest():
    """§10.3: декларативный манифест. P_* разрешены только после калибровки + версии модели."""
    return {"ml_addable_by_layer": list(ML_LAYERS), "stays_deterministic": list(DETERMINISTIC_FOREVER),
            "calibration_required_for": ["p_response", "p_accept", "p_completion"]}
