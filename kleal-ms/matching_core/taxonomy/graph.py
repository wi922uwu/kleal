# -*- coding: utf-8 -*-
"""§6 Таксономия — смысловые отношения (не заменяет policy и domain fields).

Типы связей (§6): alias (одна сущность, тот же evidence_id) · exact (1.0) · direct sibling (0.55–0.75) ·
parent (tier T2) · adjacent purpose (T3) · negative edge (penalty/constraint) · complementary role (matrix,
не similarity). Embeddings — только recall, не финальное решение. Уровни similarity: 4 exact/alias,
3 sibling(sub), 2 parent(broad), 1 adjacent, 0 none.
"""
import re
import threading

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
      2 — безопасная суффиксная морфо-близость (apple~apples) — parent-уровень;
      0 — нет. Общий префикс сам по себе недостаточен: cryptography != cryptocurrency."""
    from . import concepts as X
    # Generic polysemes may support a match only with context resolved elsewhere. Alone they caused
    # stock market == food market and any "project" == any other project.
    # ЗОНТИЧНЫЕ ТОКЕНЫ: сами по себе не признак родства, только вместе с конкретикой.
    #
    # Вторая волна найдена по живой жалобе: запрос «поиграть в rpg» приводил человека с ИИ,
    # теннисом и мясом на решётке — его цеплял общий токен `games` из «strategy board games».
    # Понятия тут ни при чём (rpg и настолки в разных семьях), и мост его честно отвергал:
    # тащил именно этот путь. `role`/`playing` — оттуда же, фильтрация отдаёт их темами для
    # «поиграть в rpg», и оба ничего не значат в одиночку.
    #
    # Настоящие совпадения от этого не страдают: «board games» ~ «настольные игры» решает
    # таблица понятий, а «board games» ~ «board games» — сравнение строки целиком, и оба пути
    # идут мимо токенов.
    ambiguous = {"market", "mercado", "рынок", "project", "проект",
                 "exchange", "intercambio", "обмен",
                 "game", "games", "игра", "игры", "juego", "juegos",
                 "role", "playing", "роль",
                 # «стартапы» -> тема `business` -> цепляло «business language», то есть интерес
                 # к ЯЗЫКУ, а не к делу. Тот же зонтик, что market.
                 "business", "бизнес", "negocio"}
    A = [w for w in _wtok(a) if w not in ambiguous]
    B = [w for w in _wtok(b) if w not in ambiguous]
    if norm(a) and norm(a) == norm(b):
        return 4
    lvl = 0
    for x in A:
        for y in B:
            if x == y:
                lvl = max(lvl, 3)                            # общий токен в разных фразах
            if X.token_equivalent(x, y):
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
_CTX = threading.local()


def set_bridge(is_related=None):
    """Впрыснуть ГОТОВОЕ РЕШЕНИЕ на текущий поиск: «похож этот интерес на запрос или нет».

    Раньше сюда передавали два набора тем, и правило «сколько общего достаточно» жило здесь —
    то есть во второй копии. Копии таких правил расходятся молча: одна сторона считает биржу и
    продуктовый рынок похожими, другая нет, и понять, кто прав, можно только чтением обеих.
    Решение принимает владелец процесса, здесь только точка подключения.
    """
    _CTX.bridge = is_related if callable(is_related) else None


def _bridge_fn():
    return getattr(_CTX, "bridge", None)


def set_topics_of(resolver=None):
    """Install the phrase resolver for this request (kept for bridge provenance/parity)."""
    _CTX.topics_of = resolver if callable(resolver) else None


def _topics_of_fn():
    return getattr(_CTX, "topics_of", None)


def _derived_set(interests):
    """Нормированные интересы, выводимые из другого интереса того же человека."""
    fn = _topics_of_fn()
    if not fn or len(interests) < 2:
        return frozenset()
    norms = [norm(x) for x in interests]
    try:
        topics = [set(fn(x) or ()) for x in interests]
    except Exception:
        return frozenset()
    out = set()
    for i, word in enumerate(norms):
        if not word or " " in word:
            continue
        for j, resolved in enumerate(topics):
            if j != i and word in resolved:
                out.add(word)
                break
    return frozenset(out)


def _bridged(x):
    """Сошёлся ли интерес `x` с запросом."""
    bridge = _bridge_fn()
    if not bridge:
        return False
    try:
        return bool(bridge(x))
    except Exception:
        return False


def similarity(topics, interests):
    """Уровень и совпавшие интересы. Полная картина — `similarity_detail`."""
    best, matched, _ = similarity_detail(topics, interests)
    return best, matched


def similarity_detail(topics, interests):
    """§6 + Аудит #4 — ЕДИНЫЙ semantic resolver. Canonical taxonomy (405 nodes) — авторитетный источник:
    если ОБЕ стороны пары резолвятся в каноне, уровень берётся из `canonical.similarity_nodes`. Seed-граф
    ниже — только bootstrap/fallback для концептов, которых в каноне нет. Уровни: 4 exact/alias >
    3 sibling > 2 parent > 1 adjacent > 0. Complementary roles и negative edges — отдельные матрицы."""
    from . import canonical as C, concepts as X
    canon = C.AVAILABLE
    matched, best, natural = set(), 0, 0
    per_topic = {}
    derived = _derived_set(interests)
    xb = [(x, resolve(x)) for x in interests]
    for t in topics:
        bt, st = resolve(t)
        nt = norm(t)
        t_in_canon = C.resolve_node(t) if canon else None
        lvl_t = 0
        for x, (bx, sx) in xb:
            # Free-form compound/multilingual concepts are evaluated before the curated graph. They
            # return only exact or direct-family levels and never broad category adjacency.
            concept_lvl = X.similarity(t, x)
            if concept_lvl:
                if concept_lvl >= 4:
                    matched.add(norm(x))
                lvl_t = max(lvl_t, concept_lvl)
                if norm(x) not in derived:
                    natural = max(natural, concept_lvl)
                continue
            # --- Аудит #4: canonical АВТОРИТЕТНО решает пару, если резолвит обе стороны ---
            if t_in_canon and C.resolve_node(x):
                lvl = C.similarity_nodes(t, x)
                if lvl >= 4:
                    matched.add(norm(x)); lvl_t = max(lvl_t, 4)
                    if norm(x) not in derived:
                        natural = max(natural, 4)
                elif lvl:
                    lvl_t = max(lvl_t, lvl)
                    if norm(x) not in derived:
                        natural = max(natural, lvl)
                continue
            # --- seed fallback: концепт вне канона (bootstrap для unknown) ---
            if norm(x) == nt:
                matched.add(norm(x)); lvl_t = max(lvl_t, 4)        # exact/alias
                if norm(x) not in derived:
                    natural = max(natural, 4)
            elif st and st == sx:
                lvl_t = max(lvl_t, 3)                               # sibling (та же sub)
            elif bt and bt == bx:
                lvl_t = max(lvl_t, 2)                               # parent (тот же broad)
            elif bt and bx and bx in ADJACENCY.get(bt, []):
                lvl_t = max(lvl_t, 1)                               # adjacent purpose
            elif not bt and not bx:
                lvl = _wshare(t, x)                                 # off-taxonomy: 4 literal / 3 token / 2 morphology
                if lvl >= 4:
                    matched.add(norm(x))
                if lvl:
                    lvl_t = max(lvl_t, lvl)
                    if norm(x) not in derived:
                        natural = max(natural, lvl)
        per_topic[norm(t)] = lvl_t
        best = max(best, lvl_t)
    # Мост проверяется ПОСЛЕДНИМ и не спорит с каноном: он поднимает только тех, кого канон и
    # `_wshare` не связали вовсе. Уровень 3 (sibling) — «про то же самое, но названо иначе»;
    # выше нельзя, точное совпадение должно оставаться точным.
    if best < 3 and _bridge_fn():
        for x in interests:
            if _bridged(x):
                matched.add(norm(x)); best = max(best, 3)
                break
    return best, matched, {"per_topic": per_topic, "natural": natural}


def is_negative(a, b):
    a, b = str(a).lower(), str(b).lower()
    return (a, b) in NEGATIVE_EDGES or (b, a) in NEGATIVE_EDGES


def is_complementary(role_a, role_b):
    return (str(role_a).lower(), str(role_b).lower()) in COMPLEMENTARY_ROLES
