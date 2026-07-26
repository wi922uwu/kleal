# -*- coding: utf-8 -*-
"""Вердикт#5/#6 — разделение активной взаимности и пассивного профильного интереса.

Ревью: обратный score «по активному запросу ИЛИ интересам» смешивает две разные вещи.
  • active_reciprocity   — у кандидата есть ВСТРЕЧНЫЙ активный intent (настоящая взаимность);
  • passive_interest_fit — в профиле просто «люблю X» (лишь потенциальная релевантность);
  • receiving_eligibility — можно ли вообще предложить intent (policy);
  • readiness             — можно ли обращаться сейчас (см. readiness.py).
Разные сущности → разные формулы. Пассивная сторона низкая В ОСНОВНОМ из-за неизвестности, а не
несовместимости; поэтому для неё используем mean_b (а не lcb_b) — иначе неизвестность штрафуется дважды
(внутри R_lcb и ещё раз через min() взаимности).
"""


def classify_reciprocity(intent, cand):
    """Вердикт#5: какая это взаимность. Возвращает {kind, active_reciprocity, passive_interest_fit}.
    active — есть встречный активный intent с реальным topical-пересечением; passive — только профиль."""
    from ..retrieval.retriever import reciprocal as _has_active_counter_intent
    active = bool(_has_active_counter_intent(intent, cand))
    passive = bool(cand.get("interests") or cand.get("intents"))
    return {"kind": "active" if active else ("passive" if passive else "none"),
            "active_reciprocity": active,
            "passive_interest_fit": (passive and not active)}


def reciprocity_view(a, b, *, active_counter_intent):
    """Вердикт#5/#6: полное разложение взаимности без двойного штрафа неизвестности.
    a,b — directional-словари {mean, coverage, lcb} (A→B и B→A).

    active_counter_intent=True  → §9.4 как есть: 0.70·min(lcb) + 0.30·mean(lcb) (доверяем lcb — обе стороны
                                  реально заявлены, coverage высокая, штраф не двойной);
    active_counter_intent=False → passive_interest_fit: сторона B основана на статическом профиле, её lcb
                                  занижен неизвестностью → используем mean_b; неизвестность отражена ОТДЕЛЬНО
                                  полем uncertainty, а НЕ повторным штрафом.
    Возвращает directional relevance/coverage, uncertainty, active_reciprocity|passive_interest_fit и value."""
    out = {
        "directional_relevance": {"a_to_b": a.get("mean", a["lcb"]), "b_to_a": b.get("mean", b["lcb"])},
        "directional_coverage": {"a_to_b": a.get("coverage", 1.0), "b_to_a": b.get("coverage", 1.0)},
        "active_counter_intent": bool(active_counter_intent),
        # неизвестность хранится ОТДЕЛЬНО (Вердикт#6) — не «зашита» второй раз в число взаимности
        "uncertainty": round(1.0 - min(a.get("coverage", 1.0), b.get("coverage", 1.0)), 4),
    }
    if active_counter_intent:
        lo, hi = min(a["lcb"], b["lcb"]), max(a["lcb"], b["lcb"])
        val = round(0.70 * lo + 0.30 * (lo + hi) / 2.0, 4)
        out["active_reciprocity"] = val
        out["passive_interest_fit"] = None
    else:
        b_used = b.get("mean", b["lcb"])                       # mean_b, не lcb_b (штраф неизвестности — один раз)
        lo, hi = min(a["lcb"], b_used), max(a["lcb"], b_used)
        val = round(0.70 * lo + 0.30 * (lo + hi) / 2.0, 4)
        out["passive_interest_fit"] = val
        out["active_reciprocity"] = None
    out["value"] = val
    out["kind"] = "active" if active_counter_intent else "passive"
    return out
