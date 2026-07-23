# -*- coding: utf-8 -*-
"""§9.1–§9.4 — Математическая модель relevance (детерминированная, без ML в MVP).

Числовые слои НЕ смешиваются в один псевдопроцент (§9, §23.2 п.1/4). relevance — внутренняя эвристика
0..1, НЕ вероятность принятия и НЕ процент совместимости. unknown использует prior и снижает coverage;
not_applicable исключается из знаменателя (C#2). R_lcb — консервативная нижняя оценка для решений.
"""
from ..feature_builder.builder import FEATURE_KEYS, K_MATCH, K_MISM, UNKNOWN, NA


def _clamp01(x):
    return max(0.0, min(1.0, x))


def _adjusted(state, value, prior, confidence):
    """§9.2 нормализация наблюдения. known: conf·observed + (1−conf)·prior; unknown: prior."""
    if state == UNKNOWN:
        return float(prior)
    return _clamp01(float(confidence) * float(value) + (1.0 - float(confidence)) * float(prior))


def directional_score(features, dom_cfg, priors, confidences=None):
    """§9.3: R_mean, Coverage, R_lcb для направления A→B. Возвращает dict + список unknowns.
      R_mean = Σ(w·adjusted)/Σw ; Coverage = Σ(w·known)/Σw ; R_lcb = clamp(R_mean − λ·(1−Cov), 0, 1).
    NA исключается из знаменателя (вес 0) — C#2. Все observed/priors ∈ [0,1]."""
    W = dom_cfg["weights"]
    lam = float(dom_cfg["uncertainty_lambda"])
    confidences = confidences or {}
    tw = kw = acc = 0.0
    unknowns = []
    for k in FEATURE_KEYS:
        w = float(W.get(k, 0) or 0)
        if w <= 0:
            continue
        state, value, _detail = features.get(k, (UNKNOWN, None, ""))
        if state == NA:
            continue                                            # вне знаменателя (§9.1)
        tw += w
        conf = float(confidences.get(k, 1.0))
        acc += w * _adjusted(state, value, priors[k], conf)
        if state in (K_MATCH, K_MISM):
            kw += w
        else:
            unknowns.append(k)
    if tw <= 0:
        return {"mean": 0.0, "coverage": 0.0, "lcb": 0.0, "unknowns": unknowns}
    mean, cov = acc / tw, kw / tw
    lcb = _clamp01(mean - lam * (1.0 - cov))
    return {"mean": round(mean, 4), "coverage": round(cov, 4), "lcb": round(lcb, 4), "unknowns": unknowns}


def reciprocal(a, b):
    """§9.4: R_reciprocal = 0.70·min(lcb_a, lcb_b) + 0.30·mean(lcb_a, lcb_b). Штрафует односторонние пары,
    bounded в [0,1]. НЕ вероятность принятия."""
    lo, hi = min(a["lcb"], b["lcb"]), max(a["lcb"], b["lcb"])
    return round(0.70 * lo + 0.30 * (lo + hi) / 2.0, 4)


def priors_from_config(cfg):
    """unknown_prior по 7 группам из §9.5 config."""
    fg = cfg.get("feature_groups") or {}
    return {k: float((fg.get(k) or {}).get("unknown_prior", 0.5)) for k in FEATURE_KEYS}


# Вердикт#7: R_lcb — НЕ статистический lower confidence bound (нет модели дисперсии/распределения ошибки,
# λ не выведена из данных, coverage ≠ размер выборки). Честнее называть это coverage-adjusted эвристикой.
LCB_HONEST_NAMES = ("conservative_relevance", "coverage_adjusted_score", "uncertainty_penalized_score")


def conservative_relevance(directional):
    """Вердикт#7: честное имя для R_lcb — консервативная (coverage-adjusted) релевантность, НЕ statistical LCB."""
    return directional["lcb"]
