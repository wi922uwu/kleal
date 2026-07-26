# -*- coding: utf-8 -*-
"""Вердикт#8 — три класса неизвестности (unknown ≠ просто штраф).

  1. neutral            — неважное поле → нейтрально, coverage не трогаем;
  2. coverage_reducing  — важное поле → снижает coverage (уже учтено в R_lcb);
  3. outreach_blocking  — операционно критичное поле → БЛОКИРУЕТ personal outreach до уточнения
                          (показываем «Нужно уточнение» / оставляем только в passive discovery).

Операционно критичные поля (когда домен/интент их реально требует): время, формат, платформа, уровень,
роль, языковая пара, готовность получать предложения. Их unknown нельзя молча «штрафовать» — надо спросить.
"""
from .builder import UNKNOWN

# группа фичи → критично ли её unknown, ЕСЛИ поле требуется интентом/доменом.
_CRITICAL_FEATURES = frozenset({"time_feasibility", "mode_format", "directed_preferences", "domain_constraints"})
# фичи, unknown которых важен для coverage, но не блокирует outreach.
_COVERAGE_FEATURES = frozenset({"semantic_activity", "location_feasibility"})


def _required(feature, intent, domain):
    """Операционно ли ТРЕБУЕТСЯ поле ИМЕННО этим интентом (тогда его unknown критичен → блок outreach).
    Критичность идёт от ЯВНОГО требования интента, а НЕ от того, что кандидат не заполнил опциональное
    поле: иначе сильный T0/T1-мэтч молча уходил бы в 'clarification' (formats/entities почти никогда не
    заявлены в профиле кандидата)."""
    if feature == "time_feasibility":
        t = intent.get("time")
        return bool((t or {}).get("windows")) if isinstance(t, dict) else bool(t and t != "flexible")
    if feature == "mode_format":
        # только при ЯВНОМ hard-требовании формата, не потому что у интента просто есть mode
        return bool(intent.get("format_required") or intent.get("format_hard"))
    if feature == "directed_preferences":
        return str(intent.get("role") or "meet").lower() not in ("", "meet")  # интент реально таргетит роль
    if feature == "domain_constraints":
        # только при ЯВНОМ hard-требовании (язык/платформа), не по факту домена games/language
        return bool(intent.get("requiredLanguages") or intent.get("platform_required"))
    return False


def classify_unknowns(features, intent, domain):
    """Вердикт#8: разнести unknown-фичи по трём классам. Возвращает
    {by_field: {feature: class}, critical: [...], blocks_outreach: bool}."""
    by_field, critical = {}, []
    for k, tup in (features or {}).items():
        if not tup or tup[0] != UNKNOWN:
            continue
        if k in _CRITICAL_FEATURES and _required(k, intent, domain):
            by_field[k] = "outreach_blocking"
            critical.append(k)
        elif k in _COVERAGE_FEATURES or k in _CRITICAL_FEATURES:
            by_field[k] = "coverage_reducing"
        else:
            by_field[k] = "neutral"
    return {"by_field": by_field, "critical": critical, "blocks_outreach": bool(critical)}


def high_impact_unknown(features, intent, domain):
    """Короткий предикат для decision_class(high_impact_unknown=…): есть ли критичный unknown."""
    return classify_unknowns(features, intent, domain)["blocks_outreach"]
