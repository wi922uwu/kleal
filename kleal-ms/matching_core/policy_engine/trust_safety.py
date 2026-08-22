# -*- coding: utf-8 -*-
"""Вердикт#25 — trust & safety модель (block list — лишь минимальный слой).

При большом объёме нужны: report history, suspicious-account signals, spam/mass-invite detection,
harassment limits, identity duplication, invitation velocity, repeated rejection patterns, no-show history,
venue safety, moderation holds. КЛЮЧЕВОЕ: trust НЕ смешивается с relevance score — он работает как
gate / ограничение outreach / снижение видимости / ручная проверка / отдельный safety workflow.
"""

ALLOW, LIMIT, REDUCE_VISIBILITY, REVIEW, BLOCK = "ALLOW", "LIMIT_OUTREACH", "REDUCE_VISIBILITY", "REVIEW", "BLOCK"

# пороги (провизорные, вынести в config при калибровке — см. Вердикт#20).
_TH = {
    "reports_24h_review": 2, "reports_total_block": 5,
    "invite_velocity_1h": 10,            # массовая рассылка
    "distinct_recipients_1h": 8,         # spam/mass-invite
    "rejection_rate_review": 0.8,        # повторные отказы (repeated rejection)
    "no_shows_review": 2,
}


def trust_signals(account):
    """Собрать trust-сигналы аккаунта в один снимок (без влияния на relevance)."""
    return {
        "reports_24h": int(account.get("reports_24h") or 0),
        "reports_total": int(account.get("reports_total") or 0),
        "invites_last_1h": int(account.get("invites_last_1h") or 0),
        "distinct_recipients_1h": int(account.get("distinct_recipients_1h") or 0),
        "rejection_rate": float(account.get("rejection_rate") or 0.0),
        "no_shows": int(account.get("no_shows") or 0),
        "identity_duplicate": bool(account.get("identity_duplicate")),
        "moderation_hold": bool(account.get("moderation_hold")),
        "suspicious_new_account": bool(account.get("suspicious_new_account")),
    }


def evaluate_trust(account):
    """Вердикт#25: итог trust как ОТДЕЛЬНОЕ решение (не relevance). Возвращает {action, reasons[]}.
    Порядок серьёзности: BLOCK > REVIEW > REDUCE_VISIBILITY > LIMIT_OUTREACH > ALLOW."""
    s = trust_signals(account)
    reasons = []
    action = ALLOW

    def esc(to, why):
        nonlocal action
        order = {ALLOW: 0, LIMIT: 1, REDUCE_VISIBILITY: 2, REVIEW: 3, BLOCK: 4}
        if order[to] > order[action]:
            action = to
        reasons.append(why)

    if s["moderation_hold"]:
        esc(BLOCK, "moderation hold")
    if s["reports_total"] >= _TH["reports_total_block"]:
        esc(BLOCK, "report history exceeds block threshold")
    if s["identity_duplicate"]:
        esc(REVIEW, "identity duplication")
    if s["reports_24h"] >= _TH["reports_24h_review"]:
        esc(REVIEW, "recent reports")
    if s["no_shows"] >= _TH["no_shows_review"]:
        esc(REVIEW, "repeated no-shows")
    if s["invites_last_1h"] >= _TH["invite_velocity_1h"] or s["distinct_recipients_1h"] >= _TH["distinct_recipients_1h"]:
        esc(LIMIT, "mass-invite / velocity")
    if s["rejection_rate"] >= _TH["rejection_rate_review"]:
        esc(REDUCE_VISIBILITY, "repeated rejection pattern")
    if s["suspicious_new_account"]:
        esc(LIMIT, "suspicious new account")
    return {"action": action, "reasons": reasons, "signals": s}


def outreach_cap(account, base_cap):
    """Вердикт#25: velocity guard снижает лимит исходящих, не трогая relevance. Срабатывает, КОГДА пробит
    velocity-сигнал (mass-invite/suspicious), даже если итоговый collapsed action — иной (напр.
    REDUCE_VISIBILITY по repeated-rejection), иначе один сигнал маскировал бы другой."""
    ev = evaluate_trust(account)
    if ev["action"] in (BLOCK, REVIEW):
        return 0
    s = ev["signals"]
    velocity = (s["invites_last_1h"] >= _TH["invite_velocity_1h"]
                or s["distinct_recipients_1h"] >= _TH["distinct_recipients_1h"]
                or s["suspicious_new_account"])
    if ev["action"] == LIMIT or velocity:
        return max(1, int(base_cap) // 3)
    return int(base_cap)


def assert_trust_not_relevance(feature_keys):
    """Guard (§11.3-подобно, Вердикт#25): trust-сигналы НЕ должны попадать в relevance feature set."""
    banned = {"reports_24h", "reports_total", "rejection_rate", "no_shows", "trust_score", "suspicious_new_account"}
    leaked = banned & set(feature_keys or [])
    if leaked:
        raise ValueError("trust signal used as relevance feature: %s" % ", ".join(sorted(leaked)))
    return True
