# -*- coding: utf-8 -*-
"""§6.1 / §9.1 — Feature Builder: 7 evidence groups × 4 состояния, без double-count.

Коррелированные представления объединяются в 7 групп; внутри — subfeatures с cap 1.0. Один source
statement влияет на несколько subfeatures только при явной независимости смысла (C#3: exact+alias+parent
+embedding НЕ дают 4 независимых бонуса — алиасы схлопнуты в один matched-набор). Состояния:
known_match / known_mismatch / unknown / not_applicable (§9.1). unknown ≠ match.
"""
import math
from geo import haversine as _haversine, latlon as _latlon   # см. shared/geo.py
from ..taxonomy import graph as TX

K_MATCH, K_MISM, UNKNOWN, NA = "known_match", "known_mismatch", "unknown", "not_applicable"

FEATURE_KEYS = ("semantic_activity", "time_feasibility", "location_feasibility", "mode_format",
                "directed_preferences", "social_context", "domain_constraints")

# §6 семантические расстояния (observed-value anchors, НЕ веса): exact/alias > sibling > parent > adjacent.
SEM_VALUE = {4: 1.0, 3: 0.65, 2: 0.45, 1: 0.25}
GEO_BANDS = ((1.5, 1.0), (3.5, 0.85), (7.0, 0.65), (15.0, 0.45))
VIBE_CLASH = {("chill", "party"), ("calm", "energetic"), ("introvert", "extrovert"),
              ("competitive", "chill"), ("calm", "competitive")}
ROLE_CONFLICT = {("play", "watch"), ("watch", "play"), ("practise", "watch")}






def _langs(seq):
    return {str(l)[:2].lower() for l in (seq or []) if str(l).strip()}


# ШИРИНА СОВПАДЕНИЯ ВНУТРИ УРОВНЯ. Уровень отвечает на «про то ли это» и определяет ярус; сам по
# себе он груб — значений всего четыре, поэтому у всех восьми человек в выдаче получался один и тот
# же балл, и порядок между ними был произвольным. Замерено на живых выдачах: 250 кандидатов по 32
# запросам дали ВСЕГО ПЯТЬ разных баллов, из них 71.3 — сто шестьдесят четыре раза.
#
# Внутри уровня различаем двумя признаками, оба уже посчитаны таксономией:
# различаем ПОКРЫТИЕМ: какую долю тем запроса человек закрыл. Закрывший три темы из четырёх сильнее
# закрывшего одну, хотя уровень у обоих четвёртый.
#
# ПРОБОВАЛИ И ОТКАТИЛИ: штрафовать совпадение, добытое машинной ручкой, а не собственным словом
# (`natural` в taxonomy/graph.py — признак остался, он честный, но балл на него не смотрит). На
# живых выдачах штраф бил ровно по тем, кого система должна беречь: преподавательница йоги, у
# которой своё «йогу преподавала» плюс дописанный `yoga`, вставала НИЖЕ человека с вином и одним
# тегом yoga; «продакт-менеджмент» кириллицей проигрывал playdate-профилю с английским тегом.
# Причина понятна задним числом: чем подробнее человек описал увлечение на своём языке, тем вернее
# его английская ручка окажется «производной» — то есть штраф начислялся за богатое описание.
#
# ПОЛОСЫ УРОВНЕЙ НЕ ПЕРЕСЕКАЮТСЯ, и это проверяемо: минимальный множитель 0.75, поэтому худшая
# четвёрка даёт 0.75 > 0.65 = потолок тройки. Ярус и балл не могут разойтись.
_BREADTH_FLOOR = 0.75          # доля балла, которую даёт сам уровень; остальное — покрытие тем


def _sem_value(best, info, n_topics):
    """Значение semantic_activity: уровень плюс ширина попадания, не покидая полосу уровня."""
    base = SEM_VALUE[best]
    per = (info or {}).get("per_topic") or {}
    if n_topics > 0 and per:
        cover = sum(SEM_VALUE.get(v, 0.0) for v in per.values()) / (float(n_topics) * SEM_VALUE[4])
    else:
        cover = 1.0
    return round(base * (_BREADTH_FLOOR + (1.0 - _BREADTH_FLOOR) * max(0.0, min(1.0, cover))), 4)


def build_features(intent, prof, cand, domain):
    """A->B evidence по 7 группам -> {group: (state, value, detail)}. Один matched-набор на semantic_activity
    (без double-count). online -> location not_applicable (исключается из знаменателя, C#2)."""
    F = {}
    topics = [str(t).lower() for t in (intent.get("topics") or [])]
    ints = [str(x).lower() for x in (cand.get("interests") or [])]

    # 1. semantic_activity — ОДНА агрегированная подфича через taxonomy.similarity (алиасы схлопнуты)
    if not topics or not ints:
        F["semantic_activity"] = (UNKNOWN, None, "")
    else:
        best, matched, info = TX.similarity_detail(topics, ints)
        if best >= 1:
            F["semantic_activity"] = (K_MATCH, _sem_value(best, info, len(topics)),
                                      ", ".join(sorted(matched)[:3]))
        else:
            F["semantic_activity"] = (K_MISM, 0.05, "")

    # 2. time_feasibility — единственный живой сигнал: open flag; иначе unknown (не тихий матч)
    tspec = str(intent.get("time") or "").strip().lower() if isinstance(intent.get("time"), str) else ""
    has_time = bool((intent.get("time") or {}).get("windows")) if isinstance(intent.get("time"), dict) else (tspec not in ("", "flexible"))
    if cand.get("open") is True:
        F["time_feasibility"] = (K_MATCH, 0.85 if has_time else 0.7, "open now")
    elif cand.get("open") is False and has_time:
        F["time_feasibility"] = (K_MISM, 0.25, "may be busy")
    else:
        F["time_feasibility"] = (UNKNOWN, None, "")

    # 3. location_feasibility — online -> not_applicable (не понижает coverage, C#2)
    mode = str(intent.get("mode") or "").lower()
    if mode == "online":
        F["location_feasibility"] = (NA, None, "")
    else:
        me, him = _latlon(prof), _latlon(cand)
        km = _haversine(me, him) if (me and him) else (float(cand["km"]) if isinstance(cand.get("km"), (int, float)) else None)
        if km is None:
            F["location_feasibility"] = (UNKNOWN, None, "")
        else:
            v = 0.15
            for lim, val in GEO_BANDS:
                if km <= lim:
                    v = val; break
            F["location_feasibility"] = ((K_MATCH if v >= 0.45 else K_MISM), v, "%.1f km" % km)

    # 4. mode_format — не заявлено -> unknown (не предполагаем совместимость)
    fmts = [str(x).lower() for x in (cand.get("formats") or [])]
    if not mode or not fmts:
        F["mode_format"] = (UNKNOWN, None, "")
    elif any(mode in f for f in fmts) or any(f in ("any", "both") for f in fmts):
        F["mode_format"] = (K_MATCH, 1.0, mode)
    else:
        F["mode_format"] = (K_MISM, 0.2, "")

    # 5. directed_preferences — только если intent реально таргетит роль (не meet)
    irole = str(intent.get("role") or "meet").lower()
    crole = str(cand.get("role") or "").lower()
    if irole in ("", "meet"):
        F["directed_preferences"] = (NA, None, "")
    elif not crole:
        F["directed_preferences"] = (UNKNOWN, None, "")
    elif irole == crole:                                # intent.role = ПРЯМОЕ требование; кандидат имеет её
        F["directed_preferences"] = (K_MATCH, 1.0, crole)
    elif (irole, crole) in ROLE_CONFLICT:
        F["directed_preferences"] = (K_MISM, 0.15, crole)
    else:
        F["directed_preferences"] = (K_MATCH, 0.55, crole)

    # 6. social_context — вайб; clash-матрица, иначе мягкий положительный
    mv, cv = str(prof.get("vibe") or "").lower(), str(cand.get("vibe") or "").lower()
    if not mv or not cv:
        F["social_context"] = (UNKNOWN, None, "")
    elif mv == cv:
        F["social_context"] = (K_MATCH, 1.0, cv)
    elif (mv, cv) in VIBE_CLASH or (cv, mv) in VIBE_CLASH:
        F["social_context"] = (K_MISM, 0.25, cv)
    else:
        F["social_context"] = (K_MATCH, 0.55, cv)

    # 7. domain_constraints — обязательные поля домена (языковая пара / required lang / entity)
    reql = _langs(intent.get("requiredLanguages"))
    clangs = _langs(cand.get("langs"))
    if domain == "language_exchange":
        F["domain_constraints"] = (K_MATCH, 1.0, "lang-pair") if (clangs & reql or clangs) else (UNKNOWN, None, "")
    elif reql:
        F["domain_constraints"] = (K_MATCH, 1.0, ",".join(sorted(reql)))   # hard-gate уже отсёк несовпадения
    elif domain in ("games", "sport_activity"):
        ents = " | ".join(str(e).lower() for e in (cand.get("entities") or []))
        F["domain_constraints"] = (K_MATCH, 0.8, "same community") if (ents and any(t in ents for t in topics)) else (UNKNOWN, None, "")
    else:
        F["domain_constraints"] = (NA, None, "")
    # §6: канонические complementary-рёбра (language_pair/role_complementarity/game_role/…) как domain-fit —
    # exchange value, где обычное similarity менее важно (§18.4). Не переопределяем известное значение.
    if F["domain_constraints"][0] == UNKNOWN and topics and ints:
        from ..taxonomy import canonical as CANON
        if any(CANON.is_complementary_nodes(t, x) for t in topics for x in ints):
            F["domain_constraints"] = (K_MATCH, 0.9, "complementary")
    return F
