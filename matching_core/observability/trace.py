# -*- coding: utf-8 -*-
"""§21.3 Observability — immutable decision trace log + replay.

Каждый (search, candidate) логируется с ВСЕМИ версиями (§21.3). Replay по трейсу воспроизводит результат
ТОЙ ЖЕ версии конфигурации (C#24, §23.4.8). Trace immutable; замена версии конфига требует нового trace.
"""
import copy
from ..relevance_engine import decision as DE


class TraceLog:
    """Хранилище immutable decision traces + exposure log (§21.3, §19.1 exposure signals)."""
    def __init__(self):
        self._traces = []

    def log(self, trace):
        self._traces.append(copy.deepcopy(trace))            # immutable snapshot
        return self._traces[-1]

    def find(self, search_id, candidate_id):
        for t in self._traces:
            if t.get("search_id") == search_id and t.get("candidate_id") == candidate_id:
                return copy.deepcopy(t)
        return None

    def all(self):
        return list(self._traces)


def replay(trace, cfg):
    """C#24: воспроизвести band из сохранённого directional по ТОЙ ЖЕ версии конфига. Возвращает
    {band, config_version, version_match}. Детерминированно: те же входы + тот же конфиг = тот же результат."""
    d = (trace.get("directional") or {}).get("a_to_b") or {}
    lcb, cov = float(d.get("lcb", 0)), float(d.get("coverage", 0))
    band = DE.band(lcb, cov, cfg.get("user_facing_bands") or {})
    return {"band": band, "config_version": trace.get("config_version"),
            "version_match": trace.get("config_version") == cfg.get("config_version")}
