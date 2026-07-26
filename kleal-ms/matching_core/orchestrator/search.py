# -*- coding: utf-8 -*-
"""Приложение B.1 — публичная точка входа поиска.

Аудит P0#1: реальная реализация вынесена в authoritative-оркестратор `pipeline.run_search`. Этот модуль
оставлен как ТОНКИЙ делегат ради обратной совместимости (сигнатура `search()` и хелперы `domain_of`/
`_reverse_features`, которые импортируют другие модули и под-адаптер). Всё скоринг-поведение живёт в
оркестраторе — обойти защитные/продуктовые стадии в обход `run_search` нельзя.
"""
from . import pipeline as _P
from .pipeline import domain_of, _reverse_features  # re-export (обратная совместимость)

# исторические ре-экспорты статусов policy (некоторые тесты импортируют их отсюда)
from ..policy_engine.engine import ALLOW, BLOCK, REVIEW  # noqa: F401


def search(intent, prof, pool, cfg, *, now, search_id, purpose=None, gate_ctx=None,
           broad_consent=None, budget=80, trace_log=None, mode="production"):
    """Делегирует в `pipeline.run_search` и возвращает transparent slate (список). Аудит #2: `now` и
    `search_id` обязательны; purpose/broad_consent выводятся из intent snapshot. Аудит #16: в production
    decision trace создаётся автоматически (отключаемо только mode='benchmark'/'test')."""
    return _P.run_search(intent, prof, pool, cfg, purpose=purpose, now=now, gate_ctx=gate_ctx,
                         broad_consent=broad_consent, budget=budget, trace_log=trace_log,
                         search_id=search_id, mode=mode)["slate"]
