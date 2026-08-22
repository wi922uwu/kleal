# -*- coding: utf-8 -*-
"""§19 Feedback, learning loop и память.

Primary positive outcome — НЕ клик и НЕ mutual like, а **Completed Positive Interaction** (§19.1).
Одно поведение не создаёт вечный вывод (§19.2). Timeout ≠ личное несовпадение; «не увидел» ≠ «отказал»
(§19.3). Dating feedback НЕ переносится в professional/social ranking (§19.2, C#13).
"""

# §19.1 outcome taxonomy — этапы и сигналы.
OUTCOME_STAGES = {
    "exposure": ("shown", "position", "source", "tier", "config_version", "propensity"),
    "consideration": ("open", "save", "ask_agent", "skip_reason"),
    "proposal": ("sent", "viewed", "response", "timeout", "decline_reason"),
    "coordination": ("counter", "conflict", "plan_created"),
    "completion": ("completed", "cancelled", "no_show", "technical_failure"),
    "quality": ("comfort", "usefulness", "would_repeat", "both_positive"),
    "safety": ("block", "report", "discomfort", "private_location_attempt"),
}


def record_outcome(store, pair_or_name, stage, signal, *, scope="default", value=None, ts=None):
    """Записать outcome-событие с scope (изоляция режимов, §17.2/§19.2). store — dict-подобный."""
    if stage not in OUTCOME_STAGES:
        raise ValueError("unknown outcome stage: %r" % stage)
    key = "%s::%s" % (str(pair_or_name).lower(), scope)
    store.setdefault(key, []).append({"stage": stage, "signal": signal, "value": value, "ts": ts})
    return store[key][-1]


def scoped_events(store, pair_or_name, scope="default"):
    return store.get("%s::%s" % (str(pair_or_name).lower(), scope), [])


def is_completed_positive(events):
    """§19.1: interaction состоялось И обе стороны НЕ дали safety-negative сигнала."""
    completed = any(e["stage"] == "completion" and e["signal"] == "completed" for e in events)
    safety_neg = any(e["stage"] == "safety" and e["signal"] in ("block", "report", "discomfort") for e in events)
    return completed and not safety_neg


def profile_update_rule(signal_kind, *, explicit=False, repeat_count=1, sensitive=False):
    """§19.2. explicit -> обновить stable; одно поведение -> нет вечного вывода; повторяющееся ->
    suggestion (sensitive требует подтверждения)."""
    if explicit:
        return "update_stable_preference"
    if repeat_count >= 3:
        return "suggestion_pending_confirmation" if sensitive else "create_suggestion"
    return "no_permanent_inference"                         # одно поведение не создаёт вечный вывод


def get_scoped_feedback(store, name, purpose):
    """§17.2/C#13: feedback читается ТОЛЬКО в своём scope. Dating-decline не виден friendship-ранкеру."""
    scope = "dating" if purpose == "dating" else "default"
    return scoped_events(store, name, scope)


# ---------------- §19.3 защита от feedback bias ----------------
def classify_nonresponse(event):
    """Отделить «не увидел» / «отказал» / «таймаут» (§19.3). timeout ≠ личное несовпадение."""
    sig = event.get("signal")
    if sig == "timeout":
        return "not_a_personal_mismatch"
    if sig in ("skip", "not_shown"):
        return "not_seen"
    if sig == "decline":
        return "declined"
    return "other"


def should_train_on(event):
    """§19.3: не обучаться на timeout как на отказе; exploration учитывается с propensity."""
    if event.get("stage") == "proposal" and event.get("signal") == "timeout":
        return False                                        # timeout не является negative label
    return True


def bias_guardrails():
    """§19.3 чек-лист (декларативно): safety/fairness проверяются ОТДЕЛЬНО от uplift conversion."""
    return {"account_exposure_position_bias": True, "not_only_responders": True,
            "separate_not_seen_from_declined": True, "timeout_not_mismatch": True,
            "exploration_with_propensity": True, "shadow_replay_before_launch": True,
            "safety_fairness_checked_separately": True}
