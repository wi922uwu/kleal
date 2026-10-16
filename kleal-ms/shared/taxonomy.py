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
import io
import json
import os

_REGISTRY = os.path.join(os.path.dirname(__file__), "interests.json")

_CACHE = {}


def _source():
    """Дерево и синонимы из общего реестра.

    Раньше литералы вычитывались разбором ast прямо из services/matching/app.py — приём рабочий,
    но он оставлял источником файл на восемь тысяч строк, куда таксономия попала исторически.
    Теперь источник — shared/interests.json, собранный tools/build_interests.py и доказавший, что
    воспроизводит прежние литералы до последнего ключа. Ранжировщик перейдёт на него следующим
    шагом; пока он читает свой литерал, а сборка следит, чтобы они не разошлись.
    """
    # ПУСТОЕ ДЕРЕВО НЕ КЕШИРУЕМ. Раньше при любой осечке чтения сюда клалось `{}` — и оставалось
    # навсегда, потому что сторож смотрит «нет ли ключа», а ключ уже записан. Одна заминка с файлом
    # при старте означала, что сервис ВЕСЬ СВОЙ ВЕК работает с нулевой таксономией: ни одна тема не
    # сводится, поиск отдаёт ноль по любому запросу, и снаружи это неотличимо от «никто не подошёл».
    # Найдено разбором 18.09.2026, когда этот файл стал единственным источником для обоих сервисов.
    if not _CACHE.get("tax"):
        try:
            with io.open(_REGISTRY, encoding="utf-8") as f:
                reg = json.load(f)
        except Exception as e:
            # Не кешируем и не молчим: следующий вызов попробует снова, а в журнале видно причину.
            try:
                import sys as _sys
                _sys.stderr.write("taxonomy: реестр %s не прочитан (%s) — работаем без него\n"
                                 % (_REGISTRY, str(e)[:120]))
            except Exception:
                pass
            return {}, {}
        tree = reg.get("tree") or {}
        if not tree:
            try:
                import sys as _sys
                _sys.stderr.write("taxonomy: в реестре %s пустое дерево — НЕ кеширую\n" % _REGISTRY)
            except Exception:
                pass
            return {}, {}
        _CACHE["tax"] = tree
        _CACHE["syn"] = reg.get("synonyms") or {}
        _CACHE["lab"] = reg.get("labels") or {}
    return _CACHE["tax"], _CACHE["syn"]


def label(key, lang="ru"):
    """Подпись ключа на языке экрана. Пусто — подписи нет, и выдумывать её здесь нечем."""
    _source()
    row = _CACHE["lab"].get(str(key or "").strip().lower()) or {}
    tag = str(lang or "").lower()
    if tag.startswith("ru"):
        return row.get("ru", "")
    # Испанская подпись есть не у всякого ключа: нет — остаётся английская, а не пустота.
    if tag.startswith("es"):
        return row.get("es") or row.get("en", "")
    return row.get("en", "")


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


def sub_of():
    """{слово: подгруппа} — на уровень точнее, чем `broad_of`.

    Восьми широких категорий мало, когда по теме надо выбрать ГЛАГОЛ. «sports» накрывает и падел,
    и бег, и йогу, а говорят про них по-разному: в падел играют, бегают бегом, йогой занимаются.
    Подгрупп пятьдесят одна, и каждая — это уже один вид действия.

    Возвращаются полные имена вида «sports/racket»: подгруппы в разных корнях могут называться
    одинаково, и короткое имя их бы склеило.
    """
    if "sub" not in _CACHE:
        tax, _syn = _source()
        out = {}
        for broad, groups in (tax or {}).items():
            b = str(broad).strip().lower()
            if not b or not isinstance(groups, dict):
                continue
            for sub, words in groups.items():
                s = str(sub).strip().lower()
                if not s:
                    continue
                full = b + "/" + s
                out.setdefault(s, full)
                for w in (words or []):
                    w = str(w).strip().lower()
                    if w:
                        out.setdefault(w, full)
        _CACHE["sub"] = out
    return _CACHE["sub"]


def words_of(broad):
    """Все слова одной широкой категории — включая имена её подгрупп."""
    b = str(broad or "").strip().lower()
    return {w for w, v in broad_of().items() if v == b and w != b}


def synonyms():
    """{чужое написание: каноническое слово} — тот же источник, что и у таксономии."""
    _tax, syn = _source()
    return {str(k).strip().lower(): str(v).strip().lower() for k, v in (syn or {}).items() if k and v}
