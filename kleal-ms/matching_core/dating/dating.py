# -*- coding: utf-8 -*-
"""§17 Dating — отдельный режим продукта (НЕ ещё один набор весов поверх friendship).

Отдельная dating capsule (purpose-bound), строгие age gates, sensitive-контур с минимизацией, staged
disclosure, no auto-accept, изоляция от других режимов (§17.2), pilot gate (§17.3), explanation без
чувствительных причин и псевдопсихологического score (§17.1).
"""
from ..contracts import profile as PR

# §17.1: поля, которые НЕ попадают в explanation (sensitive / pseudo-psych).
_SENSITIVE_REASON_KEYS = frozenset({"gender", "orientation", "compatibility_score", "personality", "attractiveness"})

# §17.3 pilot gate: обязательные review-флаги перед запуском dating.
PILOT_REQUIRED = ("ux_ready", "safety_ready", "moderation_ready", "dpia_legal_ready",
                  "incident_ops_ready", "abuse_scenarios_tested")


def consent_gate(user, intent):
    """§17.1 consent: dating требует явного включения режима + подтверждения target preferences.
    Возвращает (ok, reason)."""
    if intent.get("type") != "dating":
        return False, "not a dating intent"
    if not user.get("dating_optin"):
        return False, "dating mode not opted in"
    if not user.get("target_preferences_confirmed"):
        return False, "target preferences not confirmed"
    age = user.get("age")
    if age is None or int(age) < 18:
        return False, "age gate (18+) not satisfied"          # §17.1 несовершеннолетние исключены
    return True, None


def build_dating_capsule(user, *, disclosure_stage="limited_profile", consents=None, now=None):
    """§17.1 dating capsule: purpose-bound view с минимизацией. Age→band без consent_exact_age; interests —
    только подтверждённые dating-relevant; gender/orientation — sensitive-контур (только при явном consent)."""
    consents = consents or {}
    view = PR.build_profile_view(user, "dating", disclosure_stage=disclosure_stage, consents=consents)
    f = view["fields"]
    # sensitive-контур: gender/orientation по умолчанию НЕ отдаём даже в dating без явного согласия
    if not consents.get("consent_share_sensitive"):
        for k in ("gender", "orientation"):
            f.pop(k, None)
    view["sensitive_minimized"] = True
    view["auto_accept"] = False                                # §17.1 no auto-accept
    return view


def dating_explanation(reason_keys):
    """§17.1: убрать чувствительные причины и псевдопсихологический score из объяснения."""
    return [r for r in (reason_keys or [])
            if not any(s in str(r).lower() for s in _SENSITIVE_REASON_KEYS)]


def feedback_scope():
    """§17.2 изоляция: dating feedback имеет ОТДЕЛЬНЫЙ scope и не переносится в friendship/professional."""
    return "dating"


def crosses_into(other_mode):
    """§17.2: dating goal НЕ используется для предложения коллег/языковых партнёров/спортивных групп.
    Переход friendship→dating требует нового взаимного consent."""
    return False if other_mode == "dating" else True    # True == пересечение запрещено (isolation active)


def pilot_gate(review_flags):
    """§17.3: dating нельзя включать только потому, что ranking работает. Требует всех review-флагов.
    Возвращает (enabled, missing[])."""
    rf = review_flags or {}
    missing = [k for k in PILOT_REQUIRED if not rf.get(k)]
    return (len(missing) == 0, missing)


# ---------------- Вердикт#13: доработки dating-контура до прод-готовности ----------------
# Отдельные rate limits (dating строже friendship), взаимная проверка предпочтений, запрет
# использовать friendship-поведение как dating-сигнал и авто-расширение friendship→dating.
DATING_RATE_LIMITS = {"proposals_per_24h": 2, "proposals_per_7d": 6, "new_conversations_per_24h": 3}

# поведенческие сигналы из friendship/других режимов, которые НЕЛЬЗЯ трактовать как dating-интерес.
_FRIENDSHIP_SIGNALS = frozenset({"friendship_message", "group_join", "coworking_reply", "game_invite",
                                 "walk_accept", "language_practice"})


def dating_rate_limits():
    """Вердикт#13: dating имеет ОТДЕЛЬНЫЕ (более строгие) лимиты, не общие с friendship."""
    return dict(DATING_RATE_LIMITS)


def _prefs_match(prefs, profile):
    """Простая взаимная проверка target preferences против профиля: gender/age-band/langs (если заявлены)."""
    if not prefs:
        return True
    g = prefs.get("gender")
    if g and profile.get("gender") and g != "any" and profile.get("gender") not in (g if isinstance(g, (list, tuple, set)) else [g]):
        return False
    amin, amax = prefs.get("min_age"), prefs.get("max_age")
    age = profile.get("age")
    if age is not None and ((amin and age < amin) or (amax and age > amax)):
        return False
    want_langs = set(prefs.get("languages") or [])
    if want_langs and not (want_langs & set(profile.get("langs") or [])):
        return False
    return True


def mutual_preference_ok(a_prefs, a_profile, b_prefs, b_profile):
    """Вердикт#13: dating требует ВЗАИМНОЙ проверки предпочтений — подходит A→B И B→A. Возвращает
    (ok, reason). Односторонний интерес не создаёт dating-предложения."""
    if not _prefs_match(a_prefs, b_profile):
        return False, "searcher preferences not met by candidate"
    if not _prefs_match(b_prefs, a_profile):
        return False, "candidate preferences not met by searcher"
    return True, None


def is_dating_signal(signal_kind):
    """Вердикт#13: friendship-поведение НЕ является dating-сигналом. Только явные dating-действия считаются."""
    return str(signal_kind).lower() not in _FRIENDSHIP_SIGNALS and str(signal_kind).lower().startswith("dating_")


def assert_no_friendship_to_dating_autoexpand(from_mode, to_mode):
    """Вердикт#13/§17.2: авто-расширение friendship→dating запрещено (нужен новый взаимный consent)."""
    if str(from_mode).lower() != "dating" and str(to_mode).lower() == "dating":
        raise ValueError("auto-expansion into dating is forbidden without new mutual consent")
    return True
