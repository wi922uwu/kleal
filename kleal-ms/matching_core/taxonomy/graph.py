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
    """Уровень близости OFF-taxonomy строк (labubu/рыбалка и т.п.):
      4 — совпадение ЦЕЛИКОМ (labubu==labubu) — exact/alias;
      3 — общий токен при более длинной стороне (market ~ go-to-market: то же поле, не то же самое);
      2 — префиксная морфо-близость (painting~paintball) — parent-уровень;
      0 — нет.

    Раньше ЛЮБОЙ общий токен давал 4: «go-to-market» и «stock market» были «точным совпадением»
    запроса `market`, и человек про вывод продукта вставал первым тиром в поиск про акции.
    Точное — это когда сказано ТО ЖЕ САМОЕ, а не когда в сказанном есть то же слово."""
    A, B = _wtok(a), _wtok(b)
    # Целиком — это нормированные СТРОКИ, не множества токенов: токенизатор выбрасывает короткие
    # слова, и «go-to-market» превращается в {market} — множества совпали бы у разных фраз.
    if norm(a) and norm(a) == norm(b):
        return 4                                            # сказано одно и то же
    lvl = 0
    for x in A:
        for y in B:
            if x == y:
                lvl = max(lvl, 3)                            # общее слово в разных фразах
            elif len(x) >= 5 and len(y) >= 5 and abs(len(x) - len(y)) <= 2 and x[:5] == y[:5]:
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
_BRIDGE_TL = None       # потоко-локальный слот; создаётся лениво, см. set_bridge


def set_bridge(is_related=None):
    """Впрыснуть ГОТОВОЕ РЕШЕНИЕ на текущий поиск: «похож этот интерес на запрос или нет».

    Раньше сюда передавали два набора тем, и правило «сколько общего достаточно» жило здесь —
    то есть во второй копии. Копии таких правил расходятся молча: одна сторона считает биржу и
    продуктовый рынок похожими, другая нет, и понять, кто прав, можно только чтением обеих.
    Решение принимает владелец процесса, здесь только точка подключения.

    Слот ПОТОКО-ЛОКАЛЬНЫЙ, и это не перестраховка: матчинг обслуживает запросы параллельными
    потоками, и глобальный мост означал, что чужой поиск переставляет решение ПОД ТВОИМ —
    половина кандидатов оценена с одним мостом, половина с другим, и никакой лог этого не
    покажет. Хозяин обязан снять мост после поиска (set_bridge() без аргумента): поток, который
    моста не ставил — групповой подбор, батарея, — не должен наследовать чужой.
    """
    global _BRIDGE_TL
    if _BRIDGE_TL is None:
        import threading
        _BRIDGE_TL = threading.local()
    _BRIDGE_TL.fn = is_related if callable(is_related) else None


def _bridge_fn():
    return getattr(_BRIDGE_TL, "fn", None) if _BRIDGE_TL is not None else None


# ПРОИЗВОДНЫЕ РУЧКИ. Фильтрация дописывает человеку английские ручки к его собственным словам:
# «natación en aguas abiertas» -> swimming, «cata de café» -> coffee, «intercambio sobre cuidado de
# mascotas» -> exchange. Ручка — не слово человека, а догадка машины о том, что он имел в виду, и
# иногда догадка мимо: запрос «языковой обмен» приводил человека про уход за котами (общая ручка
# `exchange`), «пробежка по утрам» — рабочую фокус-сессию (`morning`).
#
# ПРОБОВАЛИ И ОТКАТИЛИ: запрещать ручке быть точным совпадением. Замерено на тридцати двух живых
# запросах — стало хуже, чем было. «Плавание», «аниме», «испанский язык» ушли из первого яруса
# целиком: для них ручка ЕДИНСТВЕННЫЙ мост между языками, потому что испанской фразы канон не
# знает, а общих слов у «natación en aguas abiertas» и «плавание» нет. Ручка чинит ровно то, ради
# чего заведена, и отнимать у неё ярус нельзя.
#
# Поэтому различение перенесено в БАЛЛ: `natural` — лучший уровень, добытый СОБСТВЕННЫМ словом
# человека. Совпал только по ручке — ярус тот же, балл ниже, и в выдаче он стоит под теми, кто
# сказал это сам. Ярус отвечает на «про то ли это», балл — «насколько уверенно».
#
# Опознаётся ручка тем же мостом: слово ВЫВОДИМО из другой фразы того же человека. Своё слово из
# соседнего не выводится, поэтому «senderismo» остаётся собственным, а приписанное к нему
# «hiking» — производным.
_TOPICS_OF_TL = None


def set_topics_of(fn=None):
    """Впрыснуть разбор фразы на темы (тот же, что у моста) — им опознаются производные ручки."""
    global _TOPICS_OF_TL
    if _TOPICS_OF_TL is None:
        import threading
        _TOPICS_OF_TL = threading.local()
    _TOPICS_OF_TL.fn = fn if callable(fn) else None


def _topics_of_fn():
    return getattr(_TOPICS_OF_TL, "fn", None) if _TOPICS_OF_TL is not None else None


def _derived_set(interests):
    """Нормированные интересы, выводимые из ДРУГОГО интереса того же человека."""
    fn = _topics_of_fn()
    if not fn or len(interests) < 2:
        return frozenset()
    norms = [norm(x) for x in interests]
    try:
        topics = [set(fn(x) or ()) for x in interests]
    except Exception:
        return frozenset()
    out = set()
    for i, w in enumerate(norms):
        if not w or " " in w:
            continue                    # ручка всегда одно слово; фразы человек пишет сам
        for j, ts in enumerate(topics):
            if j != i and w in ts:
                out.add(w)
                break
    return frozenset(out)


def _bridged(x):
    """Сошёлся ли интерес `x` с запросом."""
    fn = _bridge_fn()
    if not fn:
        return False
    try:
        return bool(fn(x))
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
    3 sibling > 2 parent > 1 adjacent > 0. Complementary roles и negative edges — отдельные матрицы.

    Третьим значением — уровень ПО КАЖДОЙ теме запроса. Без него наружу уходил только максимум, и
    человек, закрывший одну тему из четырёх, был неотличим от закрывшего все четыре: у восьми
    кандидатов в выдаче получался один и тот же балл, а порядок между ними — произвольный.
    """
    from . import canonical as C
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
                matched.add(norm(x)); lvl_t = max(lvl_t, 4)         # exact/alias
                if norm(x) not in derived:
                    natural = max(natural, 4)
            elif st and st == sx:
                lvl_t = max(lvl_t, 3)                               # sibling (та же sub)
            elif bt and bt == bx:
                lvl_t = max(lvl_t, 2)                               # parent (тот же broad)
            elif bt and bx and bx in ADJACENCY.get(bt, []):
                lvl_t = max(lvl_t, 1)                               # adjacent purpose
            elif not bt and not bx:
                lvl = _wshare(t, x)                                 # off-taxonomy: 4 литерал / 3 токен / 2 морфо
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
                # Мост — решение про ЗАПРОС ЦЕЛИКОМ, а не про отдельную тему, поэтому потемно он
                # ничего не поднимает. Так связанный только мостом кандидат честно оказывается у
                # нижнего края своего уровня: связь есть, но какую именно тему он закрыл — неизвестно.
                break
    return best, matched, {"per_topic": per_topic, "natural": natural}


def is_negative(a, b):
    a, b = str(a).lower(), str(b).lower()
    return (a, b) in NEGATIVE_EDGES or (b, a) in NEGATIVE_EDGES


def is_complementary(role_a, role_b):
    return (str(role_a).lower(), str(role_b).lower()) in COMPLEMENTARY_ROLES
