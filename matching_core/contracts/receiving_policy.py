# -*- coding: utf-8 -*-
"""§4.4 Receiving policy — когда и для каких предложений агент может рассматривать пользователя.

Это НЕ общий интерес в профиле (§2). Управляет passive outreach, доменами, тихими часами, бюджетом
предложений, географией и стадией disclosure.
"""

DEFAULT_QUIET = {"start": "22:00", "end": "09:00", "timezone": "Europe/Madrid"}


def build_receiving_policy(user_id, *, status="active", allowed_domains=None, passive_outreach=True,
                           quiet_hours=None, proposal_budget=None, location_scope=None,
                           allowed_proposal_types=None, disclosure_stage="limited_profile",
                           paused_until=None):
    return {
        "user_id": user_id, "status": status,
        "allowed_domains": list(allowed_domains or []),
        "passive_outreach": bool(passive_outreach),
        "quiet_hours": quiet_hours or dict(DEFAULT_QUIET),
        "proposal_budget": proposal_budget or {"per_24h": 2, "per_7d": 5},
        "location_scope": list(location_scope or []),
        "allowed_proposal_types": list(allowed_proposal_types or ["person", "small_group"]),
        "disclosure_stage": disclosure_stage, "paused_until": paused_until,
    }


def is_paused(policy, now):
    if str(policy.get("status") or "").lower() == "paused":
        pu = policy.get("paused_until")
        return True if pu is None else (float(pu) > float(now))
    pu = policy.get("paused_until")
    return bool(pu is not None and float(pu) > float(now))


def allows_domain(policy, domain):
    doms = policy.get("allowed_domains")
    return (not doms) or (domain in doms)


def _hhmm(s):
    try:
        h, m = str(s).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return None


def in_quiet_hours(policy, now_local_min):
    q = policy.get("quiet_hours") or DEFAULT_QUIET
    a, b = _hhmm(q.get("start")), _hhmm(q.get("end"))
    if a is None or b is None or now_local_min is None:
        return False
    return (a <= now_local_min < b) if a <= b else (now_local_min >= a or now_local_min < b)


def budget_ok(policy, received_24h=0, received_7d=0):
    b = policy.get("proposal_budget") or {}
    return (received_24h < int(b.get("per_24h", 99))) and (received_7d < int(b.get("per_7d", 999)))


# ---------------- Вердикт#12: purpose-bound receiving policy (per-purpose / per-channel / per-platform) ----------------
# «Открыт сейчас» слишком глобален: человек открыт к шахматам, но не к кофе; к онлайн-играм, но не к
# офлайн; к групповым событиям, но не к личным сообщениям; к дружбе, но не к networking; вечером, но не сейчас.
CHANNELS = ("direct_invites", "group_invites")


def build_purpose_policy(per_purpose=None):
    """Вердикт#12: структура receiving_policy по purpose. Пример:
      {'friendship': {'direct_invites': True, 'group_invites': True},
       'networking': {'direct_invites': False},
       'games': {'direct_invites': True, 'platforms': ['PC']}}."""
    return {"per_purpose": dict(per_purpose or {})}


def receiving_decision(policy, purpose, *, channel="direct_invites", platform=None):
    """Вердикт#12: можно ли обратиться к пользователю по данному purpose/каналу/платформе.
    Возвращает (ok, reason). Отсутствие записи для purpose -> запрет direct (unknown ≠ разрешение),
    но group_invites через discovery допустим (менее интрузивно)."""
    pp = (policy or {}).get("per_purpose") or {}
    rule = pp.get(purpose)
    if rule is None:
        # purpose не сконфигурирован: direct запрещён (не докучаем), group -> passive discovery
        return (False, "purpose not opted in for direct outreach") if channel == "direct_invites" \
            else (True, "group/discovery allowed by default")
    if channel not in rule:
        return (False, "%s channel not enabled for %s" % (channel, purpose))
    if not rule.get(channel):
        return (False, "%s disabled for %s" % (channel, purpose))
    plats = rule.get("platforms")
    if platform is not None and isinstance(plats, list) and plats and platform not in plats:
        return (False, "platform %s not allowed for %s" % (platform, purpose))
    return (True, None)
