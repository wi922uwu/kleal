# -*- coding: utf-8 -*-
"""§6 Таксономия — смысловые отношения (не заменяет policy и domain fields).

Типы связей (§6): alias (одна сущность, тот же evidence_id) · exact (1.0) · direct sibling (0.55–0.75) ·
parent (tier T2) · adjacent purpose (T3) · negative edge (penalty/constraint) · complementary role (matrix,
не similarity). Embeddings — только recall, не финальное решение. Уровни similarity: 4 exact/alias,
3 sibling(sub), 2 parent(broad), 1 adjacent, 0 none.
"""
import re

# broad -> {sub -> [канонические слова]}
TAXONOMY = {
    "games": {
        "moba": ["dota2", "dota", "lol", "leagueoflegends", "hon", "smite"],
        "fps": ["cs2", "csgo", "valorant", "overwatch", "apex"],
        "board": ["chess", "boardgames", "catan", "poker"],
    },
    "social": {
        "coffee": ["coffee", "tea", "brunch", "cafe", "matcha"],
        "walk": ["walk", "stroll", "hike"],
        "nightlife": ["bar", "drinks", "wine", "party"],
    },
    "sport": {
        "racket": ["tennis", "padel", "badminton", "squash"],
        "endurance": ["running", "cycling", "swimming"],
        "team": ["football", "basketball", "volleyball"],
    },
    "learning": {
        "language": ["spanish", "english", "french", "catalan", "german"],
    },
    "professional": {
        "startups": ["startups", "founders", "vc", "web3"],
    },
    "culture": {
        "arts": ["art", "cinema", "music", "photography"],
    },
}

# alias (§6): вариант -> каноническое слово. Тот же evidence_id (дедуп в feature builder).
SYNONYMS = {
    "dota": "dota2", "dota 2": "dota2", "league": "lol", "league of legends": "lol",
    "counterstrike": "cs2", "counter-strike": "cs2", "españita": "spanish", "espanol": "spanish",
}

# adjacent purpose (§6): соседние broad-категории (T3). Пример: кофе ↔ прогулка как спокойный social plan.
ADJACENCY = {
    "social": ["culture", "sport"],
    "culture": ["social"],
    "sport": ["social"],
    "games": ["social"],
    "professional": ["social"],
    "learning": ["social"],
}

# negative edge (§6): не считать общую категорию достаточной. (ranked competitive ↔ casual no-pressure)
NEGATIVE_EDGES = {("ranked", "casual"), ("competitive", "chill")}

# complementary role (§6): matrix, НЕ similarity. support↔carry; learner↔native.
COMPLEMENTARY_ROLES = {("support", "carry"), ("carry", "support"),
                       ("learner", "native"), ("native", "learner"),
                       ("host", "guest")}

_IDX = {}
for _b, _subs in TAXONOMY.items():
    for _s, _ws in _subs.items():
        for _w in _ws:
            _IDX[_w] = (_b, _s)


def norm(w):
    w = str(w).strip().lower()
    w2 = w.replace(" ", "")
    return SYNONYMS.get(w, SYNONYMS.get(w2, w2))


def resolve(word):
    """(broad, sub) по известному словарю: точное совпадение или префикс >=5 (не сырая подстрока)."""
    w = norm(word)
    if w in _IDX:
        return _IDX[w]
    for k, bs in _IDX.items():
        if len(w) >= 5 and (k.startswith(w) or w.startswith(k)):
            return bs
    return (None, None)


def _wtok(s):
    return [w for w in re.findall(r"[a-zа-яё0-9]+", str(s).lower()) if len(w) >= 3]


def _wshare(a, b):
    """Уровень общего слова между OFF-taxonomy строками (labubu/рыбалка и т.п.):
      4 — литеральное совпадение (labubu==labubu) — exact/alias;
      2 — префиксная морфо-близость (painting~paintball: родственно, НО не точное) — parent-уровень;
      0 — нет. Раньше префикс-5 тоже давал 4 и склеивал НЕсвязанные слова в фальшивый T1."""
    A, B = _wtok(a), _wtok(b)
    lvl = 0
    for x in A:
        for y in B:
            if x == y:
                return 4                                    # точное литеральное совпадение
            if len(x) >= 5 and len(y) >= 5 and abs(len(x) - len(y)) <= 2 and x[:5] == y[:5]:
                lvl = max(lvl, 2)                            # лишь морфо-близость -> parent, не exact
    return lvl


# ---------------------------------------------------------------- мост тем фильтрации (внешний)
#
# Канон знает 405 узлов, но не знает ни «опционы», ни «finanzas», ни «economía». Между двумя
# неизвестными ему словами остаётся лишь `_wshare` — буквально общий токен, — а у «опционы» и
# «finanzas» общих токенов нет. Отсюда T5 «нет overlap» и запрос, находящий одного человека из 714.
#
# Знание о том, что эти слова про одно и то же, есть у фильтрации, но она живёт в другом сервисе,
# и таксономия не имеет права ходить по сети: она обязана быть чистой и быстрой. Поэтому хозяин
# процесса (services/matching/app.py) ВПРЫСКИВАЕТ готовое знание на время запроса, а здесь только
# точка подключения. Ничего не впрыснули — движок работает ровно как раньше.
_BRIDGE = None          # (темы_запроса:set, темы_интереса: callable(str)->set)


def set_bridge(query_topics=None, topics_of=None):
    """Впрыснуть знание на текущий поиск. Вызывается владельцем процесса, не самим движком."""
    global _BRIDGE
    _BRIDGE = (set(query_topics or ()), topics_of) if (query_topics and topics_of) else None


def _bridged(x):
    """Сошёлся ли интерес `x` с запросом по темам фильтрации."""
    if not _BRIDGE:
        return False
    qt, fn = _BRIDGE
    try:
        return bool(qt & set(fn(x) or ()))
    except Exception:
        return False


def similarity(topics, interests):
    """§6 + Аудит #4 — ЕДИНЫЙ semantic resolver. Canonical taxonomy (405 nodes) — авторитетный источник:
    если ОБЕ стороны пары резолвятся в каноне, уровень берётся из `canonical.similarity_nodes`. Seed-граф
    ниже — только bootstrap/fallback для концептов, которых в каноне нет. Уровни: 4 exact/alias >
    3 sibling > 2 parent > 1 adjacent > 0. Complementary roles и negative edges — отдельные матрицы."""
    from . import canonical as C
    canon = C.AVAILABLE
    matched, best = set(), 0
    xb = [(x, resolve(x)) for x in interests]
    for t in topics:
        bt, st = resolve(t)
        nt = norm(t)
        t_in_canon = C.resolve_node(t) if canon else None
        for x, (bx, sx) in xb:
            # --- Аудит #4: canonical АВТОРИТЕТНО решает пару, если резолвит обе стороны ---
            if t_in_canon and C.resolve_node(x):
                lvl = C.similarity_nodes(t, x)
                if lvl >= 4:
                    matched.add(norm(x)); best = max(best, 4)
                elif lvl:
                    best = max(best, lvl)
                continue
            # --- seed fallback: концепт вне канона (bootstrap для unknown) ---
            if norm(x) == nt:
                matched.add(norm(x)); best = max(best, 4)          # exact/alias
            elif st and st == sx:
                best = max(best, 3)                                 # sibling (та же sub)
            elif bt and bt == bx:
                best = max(best, 2)                                 # parent (тот же broad)
            elif bt and bx and bx in ADJACENCY.get(bt, []):
                best = max(best, 1)                                 # adjacent purpose
            elif not bt and not bx:
                lvl = _wshare(t, x)                                 # off-taxonomy: 4 литерал / 2 морфо
                if lvl >= 4:
                    matched.add(norm(x)); best = max(best, 4)
                elif lvl:
                    best = max(best, lvl)
    # Мост проверяется ПОСЛЕДНИМ и не спорит с каноном: он поднимает только тех, кого канон и
    # `_wshare` не связали вовсе. Уровень 3 (sibling) — «про то же самое, но названо иначе»;
    # выше нельзя, точное совпадение должно оставаться точным.
    if best < 3 and _BRIDGE:
        for x in interests:
            if _bridged(x):
                matched.add(norm(x)); best = max(best, 3)
    return best, matched


def is_negative(a, b):
    a, b = str(a).lower(), str(b).lower()
    return (a, b) in NEGATIVE_EDGES or (b, a) in NEGATIVE_EDGES


def is_complementary(role_a, role_b):
    return (str(role_a).lower(), str(role_b).lower()) in COMPLEMENTARY_ROLES
