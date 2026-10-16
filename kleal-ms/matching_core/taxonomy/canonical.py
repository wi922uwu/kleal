# -*- coding: utf-8 -*-
"""§6 Каноническая таксономия — загрузка Kleal_Global_Context_Profiles_Intent_Taxonomy_RU_v1
(405 нод · 1249 алиасов ru/en/es · 560 типизированных рёбер · 139 доменных слотов · 65 контекст-профилей).

Извлечено в `canonical_taxonomy.json` (stdlib json, БЕЗ openpyxl в рантайме — проект stdlib-only).
Даёт data-driven: negative-рёбра (`blocked_cross_purpose` → purpose isolation §8.1/§17.2), complementary
(`role_complementarity`/`language_pair`/`team_role`/… → C#16), adjacency (§6/§12), и доменные слоты с
hard/soft + unknown_behavior + compare_operator (§5/§8.1). Аддитивно к seed-графу (не заменяет similarity).
"""
import functools
import os
import json
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_JSON = os.path.join(_HERE, "canonical_taxonomy.json")

# ДОПОЛНЕНИЯ ЖИВУТ ОТДЕЛЬНЫМ ФАЙЛОМ, и это не вкусовщина. `canonical_taxonomy.json` — выгрузка из
# исходной таблицы (405 нод · 1249 алиасов); всё, что дописано в неё руками, исчезнет при следующей
# перегенерации, причём молча. Поэтому наши узлы и алиасы лежат в `canonical_extra.json` и
# приклеиваются поверх при загрузке: перегенерация базы их не трогает, а происхождение каждой
# строки видно по файлу, в котором она лежит.
#
# ПОВЕРХ, А НЕ ВМЕСТО: существующий алиас дополнение перебить не может (см. `_load_extra`) — иначе
# правка «на один случай» тихо переставила бы чужие пары.
_EXTRA = os.path.join(_HERE, "canonical_extra.json")
EXTRA_NODES = set()        # id узлов, пришедших из дополнения — для отчётов и проверок
EXTRA_ALIASES = set()

AVAILABLE = False
NODES = {}                 # node_id -> {parent,type,domain,ru,en,es,family,macro}
_TYPE = {}
_PARENT = {}
ALIAS = {}                 # нормализованный алиас -> node_id
ADJACENT = {}              # node_id -> set(соседей) из adjacent-рёбер
COMPLEMENTARY = set()      # {(node_a, node_b)} из role/pair-рёбер (симметрично)
BLOCKED_NODES = set()      # {(family_a, family_b)} из blocked_cross_purpose
SLOTS_BY_DOMAIN = {}       # domain -> [slot spec, ...]
FAMILY_PURPOSE = {}        # family_id -> purpose (из контекст-профилей)
PURPOSE_BLOCKS = set()     # {(purpose_a, purpose_b)} выведено из blocked_cross_purpose
_COMPLEMENT_RELS = {"role_complementarity", "language_pair", "team_role", "game_role",
                    "slot_complementarity", "project_role"}


def _norm(s):
    return str(s or "").strip().lower().replace(" ", "")


# Насколько длиннее слова может быть алиас, чтобы это всё ещё считалось словоизменением. См. `_resolve`.
_MORPH_TAIL = 2


def _load():
    global AVAILABLE
    try:
        data = json.load(open(_JSON, encoding="utf-8"))
    except Exception:
        AVAILABLE = False
        return
    for n in data.get("nodes", []):
        NODES[n["id"]] = n
        _TYPE[n["id"]] = n.get("type")
        if n.get("parent"):
            _PARENT[n["id"]] = n["parent"]
    # ancestors -> family/macro на каждой ноде
    for nid, n in NODES.items():
        n["family"] = _ancestor(nid, "family")
        n["macro"] = _ancestor(nid, "macro")
    for a in data.get("aliases", []):
        ALIAS[_norm(a["alias"])] = a["node"]
    _load_extra()                          # узлы дополнения — ДО раскладки алиасов из ru/en/es
    for nid, n in NODES.items():
        for key in ("en", "ru", "es"):
            if n.get(key):
                ALIAS.setdefault(_norm(n[key]), nid)
    _extra_aliases()                       # алиасы дополнения — ПОСЛЕ, и только на свободные места
    for e in data.get("edges", []):
        rel, s, d = e.get("rel"), e.get("src"), e.get("dst")
        if rel == "adjacent":
            ADJACENT.setdefault(s, set()).add(d)
            ADJACENT.setdefault(d, set()).add(s)
        elif rel == "blocked_cross_purpose":
            BLOCKED_NODES.add((s, d))
        elif rel in _COMPLEMENT_RELS:
            COMPLEMENTARY.add((s, d)); COMPLEMENTARY.add((d, s))
    for s in data.get("slots", []):
        SLOTS_BY_DOMAIN.setdefault(s.get("domain"), []).append(s)
    for p in data.get("profiles", []):
        if p.get("family") and p.get("purpose"):
            for fam in str(p["family"]).split("|"):
                FAMILY_PURPOSE.setdefault(_bare(fam.strip()), p["purpose"])
    # purpose-blocks из family-blocks (профили дают bare-family 'casual_social', ноды — 'F_casual_social')
    for (a, b) in BLOCKED_NODES:
        pa, pb = FAMILY_PURPOSE.get(_bare(_family_id(a))), FAMILY_PURPOSE.get(_bare(_family_id(b)))
        if pa and pb and pa != pb:
            PURPOSE_BLOCKS.add((pa, pb)); PURPOSE_BLOCKS.add((pb, pa))
    _resolve.cache_clear()          # таблица пересобрана — прежние ответы недействительны
    AVAILABLE = True


_EXTRA_DATA = {"nodes": [], "aliases": []}


def _load_extra():
    """Приклеить узлы дополнения. Узел с уже занятым id игнорируется, родитель обязан существовать."""
    global _EXTRA_DATA
    try:
        with open(_EXTRA, encoding="utf-8") as f:
            _EXTRA_DATA = json.load(f)
    except Exception:
        _EXTRA_DATA = {"nodes": [], "aliases": []}
        return
    for n in _EXTRA_DATA.get("nodes", []):
        nid = n.get("id")
        if not nid or nid in NODES:
            continue                       # база победила: дополнение НЕ переопределяет
        if n.get("parent") and n["parent"] not in NODES:
            continue                       # висячий родитель сломал бы _ancestor
        NODES[nid] = dict(n)
        _TYPE[nid] = n.get("type") or "activity"
        if n.get("parent"):
            _PARENT[nid] = n["parent"]
        NODES[nid]["family"] = _ancestor(nid, "family")
        NODES[nid]["macro"] = _ancestor(nid, "macro")
        EXTRA_NODES.add(nid)


def _extra_aliases():
    """Алиасы дополнения — только на СВОБОДНЫЕ имена. Занятое имя не перебиваем: чужая пара, уже
    посчитанная по базе, не должна поменяться из-за нашей правки."""
    for a in _EXTRA_DATA.get("aliases", []):
        w, nid = _norm(a.get("alias")), a.get("node")
        if not w or nid not in NODES or w in ALIAS:
            continue
        ALIAS[w] = nid
        EXTRA_ALIASES.add(w)


def _bare(x):
    return x[2:] if x and str(x).startswith("F_") else x


def _ancestor(nid, want_type):
    cur, seen = nid, set()
    while cur and cur not in seen:
        seen.add(cur)
        if _TYPE.get(cur) == want_type:
            return cur
        cur = _PARENT.get(cur)
    return None


def _family_id(nid):
    return _ancestor(nid, "family") or nid


# --------------------------------------------------------------- публичный API
# ПАМЯТЬ НА ОТВЕТЫ. Промах по алиасу стоит полного прохода по словарю (1749 записей, и на каждой
# по три len() и два startswith), а зовут эту функцию тысячи раз за один поиск: профиль живого
# запроса 15.09.2026 — 20 294 вызова, 10,4 с из 20, и 22 миллиона вызовов len() на всё про всё.
# Разных СЛОВ при этом десятки: интересы и темы повторяются у сотен людей.
#
# Кешировать безопасно: ALIAS собирается один раз при импорте (`_load`, единственный вызов внизу
# файла) и больше не меняется — governance правит СИНОНИМЫ движка, а не эту таблицу. На случай
# повторной сборки память сбрасывается там же, где таблица собирается.
@functools.lru_cache(maxsize=100000)
def _resolve(text):
    """node_id И КАК он получен: точным алиасом или догадкой по префиксу.

    Различать обязательно, потому что от этого зависит уровень. Раньше догадка была неотличима
    от попадания, и `similarity_nodes` выдавал за неё 4 — «точное совпадение». Так `market`
    становился узлом `marketing` (префикс), `food` — узлом `food market`, и поиск про акции
    приводил маркетологов и гастрономические рынки. Оттуда же жалоба «везде только первый тир»:
    разные слова склеивались в один узел и все получали высший балл.

    review#A уже подрезал это правило по минимальной длине ('remote'→rowing, 'surface'→surfing),
    но осталось главное: префикс — это не словоизменение. Хвост в три и больше символов почти
    всегда другое слово или вовсе второе слово составного имени узла, и именно так короткие
    обиходные интересы проваливались в узкие узлы:

        coffee (6) -> "coffee date"  (10)   человек про кофе, узел про свидание
        wine   (4) -> "wine tasting" (11)   человек про вино, узел про дегустацию
        food   (4) -> "food market"  (10)   человек про еду, узел про гастрорынок
        market (6) -> "marketing"    (9)    запрос про акции, узел про маркетинг

    Настоящее словоизменение короткое: hike/hiking, mercado/mercados, finanza/finanzas. Отсюда
    порог в два символа — он оставляет склонение и отрезает словообразование.
    """
    w = _norm(text)
    if not w:
        return None, False
    if w in ALIAS:
        return ALIAS[w], True                                 # точный алиас
    # Кандидат выбирается детерминированно — ближайший по длине, при равенстве по алфавиту.
    # Раньше побеждал первый в порядке словаря, то есть результат зависел от порядка загрузки
    # и мог меняться между процессами.
    best = None
    for alias, nid in ALIAS.items():
        if len(alias) < 5 or len(w) < 4 or abs(len(alias) - len(w)) > _MORPH_TAIL:
            continue
        if alias.startswith(w) or w.startswith(alias):
            d = abs(len(alias) - len(w))
            if best is None or (d, alias) < (best[0], best[1]):
                best = (d, alias, nid)
    return (best[2], False) if best else (None, False)


def resolve_node(text):
    """Строка интереса/темы -> node_id. Как резолвилось — см. `_resolve`."""
    return _resolve(text)[0]


# ---- КАРТА ДОГАДОК (canonical_guess.json) ----------------------------------------------------------
# Слово вне канона, поставленное к узлу моделью один раз, при появлении (tools/concept_guess.py, таймер
# kleal-guess.timer раз в минуту; файл вне дерева кода — его пишет машина, а не выкладка). Поиск
# только читает файл — в сеть не ходит; перечитывает не чаще раза в 30 с, если файл изменился. Догадка
# ставит слово только в СЕМЬЮ канона и даёт не больше 2: та же семья — 2, та же ветка — 1 (ярус тот же, что у
# 3, — второй; четвёрка остаётся за точным). Пары, которые канон решает сам,
# сюда не приходят (graph.similarity_detail), так что прежние уровни не меняются.
_GUESS = {"t": -1e9, "m": None, "words": {}, "memo": {}}
_GUESS_FILE = os.environ.get("KLEAL_GUESS_FILE") or "/var/lib/kleal/canonical_guess.json"   # данные, не код


def _guess_words():
    now = time.monotonic()
    if now - _GUESS["t"] >= 30:
        _GUESS["t"] = now
        try:
            m = os.path.getmtime(_GUESS_FILE)
            if m != _GUESS["m"]:
                with open(_GUESS_FILE, encoding="utf-8") as f:
                    d = json.load(f)
                _GUESS["words"] = {k: v.get("node") for k, v in (d.get("words") or {}).items()
                                   if isinstance(v, dict) and v.get("node") in NODES
                                   and NODES[v["node"]].get("macro") != "M_dating"}   # свидание — тип, не интерес
                _GUESS["memo"] = {}
                _GUESS["m"] = m
        except Exception:
            pass
    return _GUESS["words"]


def guess_node(text):
    """Узел по карте догадок или None. Зовут на каждой паре поиска — ответ на текст помнится до смены карты."""
    words = _guess_words()
    if not words:
        return None
    memo = _GUESS["memo"]
    if text not in memo:
        if len(memo) > 200000:
            memo.clear()
        memo[text] = words.get(_norm(text))
    return memo[text]


def similarity_guess(a_text, b_text):
    """Уровень пары, где хотя бы одна сторона известна канону только по догадке: 0, 1 или 2."""
    if not _guess_words():
        return 0
    ca, cb = _resolve(a_text)[0], _resolve(b_text)[0]
    if ca and cb:
        return 0                                  # обе в каноне — решает similarity_nodes
    na, nb = ca or guess_node(a_text), cb or guess_node(b_text)
    if not na or not nb:
        return 0
    fa = na if na.startswith("F_") else NODES[na].get("family")
    fb = nb if nb.startswith("F_") else NODES[nb].get("family")
    if fa and fa == fb:
        return 2
    ma, mb = NODES[na].get("macro"), NODES[nb].get("macro")
    if ma and ma == mb:
        return 1
    return 0


# ---- БЛИЗКИЕ ПО СМЫСЛУ (meaning_near.json, 02.10.2026) ------------------------------------------------
# Последняя ступень лестницы для слов, которых не знают ни канон, ни карта догадок: tools/meaning_near.py заранее
# сравнил слово по смыслу со всеми интересами людей (bge-m3) и дал модели выбрать из 25 ближайших тех, с кем правда
# стоит встретиться ("ok"). Поиск только читает файл, раз в 30 с по mtime, в сеть не ходит. Уровень — 1 (третий
# ярус, ниже семьи и раздела), ставит graph.similarity_detail и только там, где больше ничего не совпало.
# "near" (сырой порядок векторов) нужен последней ступени выдачи app._expand_fallback — «похожие люди».
_NEAR = {"t": -1e9, "m": None, "ok": {}, "near": {}}
_NEAR_FILE = os.environ.get("KLEAL_NEAR_FILE") or "/var/lib/kleal/meaning_near.json"   # данные, не код


def _near_data():
    now = time.monotonic()
    if now - _NEAR["t"] >= 30:
        _NEAR["t"] = now
        try:
            m = os.path.getmtime(_NEAR_FILE)
            if m != _NEAR["m"]:
                with open(_NEAR_FILE, encoding="utf-8") as f:
                    d = json.load(f)
                _NEAR["ok"] = {k: frozenset(v) for k, v in (d.get("ok") or {}).items() if v}
                _NEAR["near"] = {k: dict((x, s) for x, s in v) for k, v in (d.get("near") or {}).items()}
                _NEAR["m"] = m
        except Exception:
            pass
    return _NEAR


def meaning_near(a_text, b_text):
    """Интерес b близок по смыслу к незнакомому слову a (отобран моделью)."""
    ok = _near_data()["ok"]
    return bool(ok) and _norm(b_text) in ok.get(_norm(a_text), ())


def meaning_score(a_text, b_text):
    """Сходство векторов слова a и интереса b (0, если его нет среди 40 ближайших)."""
    return float(_near_data()["near"].get(_norm(a_text), {}).get(_norm(b_text), 0.0))


def similarity_nodes(a_text, b_text):
    """Уровень близости по КАНОНИЧЕСКОЙ иерархии: 4 exact, 3 sibling(family), 2 parent(macro), 1 adjacent, 0.

    ЧЕТВЁРКА ТОЛЬКО ЗА ТОЧНОЕ. Попадания в один узел мало: в узел приходят и по догадке, а
    `market` и `marketing` — разные слова. Выдавать за них «точное совпадение» значит ставить
    маркетолога вровень с финансистом по запросу про акции, что и происходило.

    Одинаковый текст сам по себе тоже не делает совпадение точным, если канон этого слова не
    знает. `market` он только угадывает как `marketing`; человеку это слово не принадлежит — оно
    дописано машиной в интересы («гастрономический рынок» → market) и машиной же добавлено в
    запрос («акции» → market). Две догадки, встретившиеся на общем слове, — не «оба назвали одно
    и то же», и первым тиром это быть не должно.

    Слово, которого в каноне нет ВОВСЕ, сюда не попадает: оно не резолвится, ответ None, и его
    судьбу решает буквальное сравнение в seed-графе, где одинаковый текст по-прежнему четвёрка.
    Так «labubu» с «labubu» остаётся точным совпадением, а «market» с «market» — нет.
    """
    na, ea = _resolve(a_text)
    nb, eb = _resolve(b_text)
    if not na or not nb:
        return None                      # не резолвится в каноне -> пусть решает seed-граф
    if na == nb:
        return 4 if (ea and eb) else 3
    if NODES[na].get("family") and NODES[na]["family"] == NODES[nb].get("family"):
        return 3
    if NODES[na].get("macro") and NODES[na]["macro"] == NODES[nb].get("macro"):
        return 2
    if nb in ADJACENT.get(na, set()) or na in ADJACENT.get(nb, set()):
        return 1
    return 0


def purpose_blocked(purpose_a, purpose_b):
    """§8.1/§17.2: разные purpose с blocked_cross_purpose ребром нельзя смешивать."""
    return (str(purpose_a), str(purpose_b)) in PURPOSE_BLOCKS


def is_complementary_nodes(a_text, b_text):
    """§6/C#16: complementary по каноническим ребрам (language_pair/role_complementarity/…)."""
    na, nb = resolve_node(a_text), resolve_node(b_text)
    return bool(na and nb and ((na, nb) in COMPLEMENTARY or (nb, na) in COMPLEMENTARY))


def slots_for_domain(domain):
    return SLOTS_BY_DOMAIN.get(domain, [])


def slot_spec(domain, slot_name):
    for s in SLOTS_BY_DOMAIN.get(domain, []):
        if s.get("slot") == slot_name:
            return s
    return None


def hard_slots(domain):
    return [s for s in SLOTS_BY_DOMAIN.get(domain, []) if s.get("imp") == "hard"]


_load()
