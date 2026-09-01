# -*- coding: utf-8 -*-
"""Общий словарь тем: одно слово — одна широкая категория.

ЗАЧЕМ ЭТОТ ФАЙЛ ВООБЩЕ ПОЯВИЛСЯ. Таксономия объявлена в services/matching/app.py::TAXONOMY, и по ней
ранжировщик сравнивает интересы буквально. Всем остальным она тоже нужна — но импортировать сервис
ради константы нельзя, поэтому buddy держал СВОЙ список слов, переписанный руками. Над ним стояло
«KEEP IN SYNC with services/matching/app.py::TAXONOMY (a shared/taxonomy.py would be better)», и это
не сработало: на 1 сентября 2026 в оригинале 441 слово, а в зеркале 158. Двести восемьдесят три
слова — anime, baking, baseball, bachata, backend и так далее — buddy отбрасывал как «ранжировщик
их не поймёт», хотя тот понимает их все. Ничего лишнего зеркало при этом не выдумало и категории не
перепутало: оно просто отстало и тихо резало воронку.

Здесь тот же приём, которым уже пользуется services/onboarding/interest_normalization.py: литералы
читаются из исходника разбором ast, без импорта и без запуска чужого сервиса. Копии больше нет —
есть один источник и одно чтение, поэтому разойтись нечему.

Когда таксономия наконец переедет сюда целиком, поменяется только тело `_source()`; всё, что зовёт
`broad_of()` и `words()`, останется прежним.
"""
import ast
import os

_MATCHING = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "services", "matching", "app.py"))

_CACHE = {}


def _literal_assignments(path, wanted):
    """Прочитать литеральные константы из чужого модуля, не импортируя его."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=path)
        out = {}
        for node in tree.body:
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in wanted:
                out[target.id] = ast.literal_eval(node.value)
        return out
    except Exception:
        return {}


def _source():
    if "tax" not in _CACHE:
        vals = _literal_assignments(_MATCHING, {"TAXONOMY", "SYNONYMS"})
        tax = vals.get("TAXONOMY")
        syn = vals.get("SYNONYMS")
        _CACHE["tax"] = tax if isinstance(tax, dict) else {}
        _CACHE["syn"] = syn if isinstance(syn, dict) else {}
    return _CACHE["tax"], _CACHE["syn"]


def broad_of():
    """{слово: широкая категория}. Подгруппы тоже слова: по ним ранжировщик ищет наравне с листьями."""
    if "broad" not in _CACHE:
        tax, _syn = _source()
        out = {}
        for broad, groups in (tax or {}).items():
            b = str(broad).strip().lower()
            if not b:
                continue
            out.setdefault(b, b)
            if not isinstance(groups, dict):
                continue
            for sub, words in groups.items():
                s = str(sub).strip().lower()
                if s:
                    out.setdefault(s, b)
                for w in (words or []):
                    w = str(w).strip().lower()
                    if w:
                        out.setdefault(w, b)
        _CACHE["broad"] = out
    return _CACHE["broad"]


def words_of(broad):
    """Все слова одной широкой категории — включая имена её подгрупп."""
    b = str(broad or "").strip().lower()
    return {w for w, v in broad_of().items() if v == b and w != b}


def synonyms():
    """{чужое написание: каноническое слово} — тот же источник, что и у таксономии."""
    _tax, syn = _source()
    return {str(k).strip().lower(): str(v).strip().lower() for k, v in (syn or {}).items() if k and v}
