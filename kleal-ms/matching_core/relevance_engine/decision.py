# -*- coding: utf-8 -*-
"""§9.6 decision thresholds + §9.7 transparent results.

Пороги берутся из sha-pinned config (единый источник, §23.2 п.11) — НЕ хардкодятся. Пользователь видит
качественный band + 2–3 подтверждённые причины + один gap; «92% совместимости» ЗАПРЕЩЕНО без калибровки
(§9.7, §23.2 п.10). reason keys содержат только known-факты (C#23). UX-copy отделён от системного решения.
"""
from ..feature_builder.builder import FEATURE_KEYS, K_MATCH, K_MISM, UNKNOWN

# §9.7 качественные уровни (UX copy — RU/EN, отделено от decision).
BAND_LABELS = {
    "especially_close": ("Особенно близко к вашему запросу", "Especially close to your request"),
    "strong_option": ("Хороший вариант", "Strong option"),
    "broader_option": ("Более широкий вариант", "Broader option"),
    "needs_clarification": ("Нужно уточнение", "Needs clarification"),
}
BAND_RANK = {"especially_close": 0, "strong_option": 1, "broader_option": 2, "needs_clarification": 3}

# человекочитаемые причины по группам (§9.7); только для подтверждённых known_match.
_REASON = {
    "semantic_activity": lambda d: ("общее: %s" % d if d else "близкая тема", "shares %s" % d if d else "related topic"),
    "time_feasibility": lambda d: ("открыт(а) к встрече сейчас", "open to meet now"),
    "location_feasibility": lambda d: ("рядом (%s)" % d, "nearby (%s)" % d),
    "mode_format": lambda d: ("совпадает формат", "format fits"),
    "directed_preferences": lambda d: ("подходящая роль (%s)" % d, "matching role (%s)" % d),
    "social_context": lambda d: ("похожий вайб", "similar vibe"),
    "domain_constraints": lambda d: ("совпали условия (%s)" % d, "constraints fit (%s)" % d),
}
_GAP = {
    "semantic_activity": ("интересы не заполнены", "interests not filled in"),
    "time_feasibility": ("время не подтверждено", "time not confirmed"),
    "location_feasibility": ("район не указан", "area unknown"),
    "mode_format": ("формат не уточнён", "format not set"),
    "directed_preferences": ("роль не указана", "role unknown"),
    "social_context": ("вайб не указан", "vibe unknown"),
    "domain_constraints": ("детали домена не указаны", "domain details unknown"),
}


# Аудит #8: явная семантика policy для decision_class. personal outreach — только при ALLOW.
PERSONAL_CLASSES = ("strong_personal", "usable_personal")
POLICY_SEMANTICS = {"BLOCK": "never score/present/outreach",
                    "REVIEW": "never personal outreach; optional quarantined discovery / manual review",
                    "ALLOW": "normal pipeline"}


def is_personal(decision_class):
    """Аудит #8: является ли класс личным outreach (strong_personal / usable_personal)."""
    return decision_class in PERSONAL_CLASSES


def band(lcb, coverage, bands_cfg):
    """§9.7: качественный уровень из lcb + coverage (пороги из config user_facing_bands)."""
    for name in ("especially_close", "strong_option", "broader_option"):
        b = bands_cfg.get(name) or {}
        if lcb >= float(b.get("min_lcb", 1)) and coverage >= float(b.get("min_coverage", 1)):
            return name
    return "needs_clarification"


def decision_class(lcb, coverage, tier, dom_cfg, *, policy="ALLOW", broad_consent=False,
                   high_impact_unknown=False):
    """§9.6 пилотные пороги (из config domain thresholds). Возвращает одно из:
      strong_personal / usable_personal / discovery_only / clarification / no_outreach."""
    o_lcb, o_cov = float(dom_cfg["outreach_min_lcb"]), float(dom_cfg["outreach_min_coverage"])
    d_lcb, d_cov = float(dom_cfg["discovery_min_lcb"]), float(dom_cfg["discovery_min_coverage"])
    if policy != "ALLOW":
        return "no_outreach"
    if high_impact_unknown:
        return "clarification"
    outreach_tier = tier in ("T0", "T1") or (tier == "T2" and broad_consent)
    if outreach_tier and lcb >= o_lcb and coverage >= o_cov:
        return "strong_personal" if tier in ("T0", "T1") else "usable_personal"
    if outreach_tier and lcb >= d_lcb and coverage >= d_cov:
        return "usable_personal"
    if lcb >= d_lcb:
        return "discovery_only"                                  # tier T3-T4 или низкое coverage
    return "no_outreach"


def presentation(features, dom_cfg):
    """§9.7: 2–3 подтверждённые причины (ТОЛЬКО known_match, C#23 — никаких выдуманных фактов) + один
    существенный gap (top known_mismatch, иначе top unknown). Возвращает {reasons_ru/en, gap_ru/en}."""
    W = dom_cfg["weights"]
    known = sorted(
        [(float(W.get(k, 0)) * float(v), k, d) for k, (st, v, d) in features.items()
         if st == K_MATCH and float(W.get(k, 0)) > 0 and v is not None],
        key=lambda x: -x[0])
    rs_ru, rs_en = [], []
    for _wv, k, d in known[:3]:
        ru, en = _REASON[k](d)
        rs_ru.append(ru); rs_en.append(en)
    gaps = sorted([(float(W.get(k, 0)), k) for k, (st, v, d) in features.items()
                   if st == K_MISM and float(W.get(k, 0)) > 0], key=lambda x: -x[0])
    if not gaps:
        gaps = sorted([(float(W.get(k, 0)), k) for k, (st, v, d) in features.items()
                       if st == UNKNOWN and float(W.get(k, 0)) > 0], key=lambda x: -x[0])
    gap_ru = gap_en = None
    if gaps:
        gap_ru, gap_en = _GAP[gaps[0][1]]
    return {"reasons_ru": rs_ru, "reasons_en": rs_en, "gap_ru": gap_ru, "gap_en": gap_en}


def low_coverage(coverage, dom_cfg):
    """§9.7 отметка «часть данных ещё не подтверждена» — если coverage ниже discovery-порога."""
    return coverage < float(dom_cfg["discovery_min_coverage"])


# Вердикт#20: пороги band/coverage (0.78/0.66/0.52; 0.75/0.60/0.40) — ПРОВИЗОРНЫЕ экспертные константы,
# не доказанные реальными исходами. «Особенно близко» = высокий внутренний score, НЕ доказанный шанс успеха.
THRESHOLDS_PROVISIONAL = True


def threshold_provenance():
    """Вердикт#20: статус порогов — до калибровки это экспертные константы, не proven outcomes."""
    return {"status": "provisional_expert_constants", "proven": False,
            "calibrate_against": ["viewed", "interest_expressed", "mutual_interest", "confirmed_plan",
                                  "completed_meeting", "repeat_interaction", "block_or_report"]}
