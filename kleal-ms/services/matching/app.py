# -*- coding: utf-8 -*-
# Kleal matching-service — the buddy agent (intent parse -> ranked candidates -> agent negotiation).
# Carved from the pre-split monolith kleal_v2.py (matching half, lines 304-831). Serves /api/agent/*.
# Talks to llm-service over HTTP for parse/intro/negotiate; holds NO model keys. Owner: Dev B.
# Endpoint names are FROZEN — the profile-service frontend hard-codes them (see ../../shared/contracts.md).
import os, sys, json, re, threading, concurrent.futures, math, hashlib, time, copy, contextlib, traceback, secrets
import urllib.request                        # мост тем: один вопрос фильтрации на НОВОЕ слово запроса
_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "..", "..", "shared"), os.path.join(_HERE, "shared")):
    if os.path.isdir(_p) and _p not in sys.path: sys.path.insert(0, _p)
# ...and THIS directory ahead of shared/, always. The kleal_* engine modules below live here; only
# kleal_lib is genuinely shared. An older layout kept all of them in shared/, and a deploy that
# restored that layout left stale copies behind — which, with shared/ first on the path, SHADOWED
# every module in this directory. The service then ran a mix of new dispatcher and old engine:
# matching answered with a group ceiling of 8 that no file in this folder still contained, and the
# config-pin check failed against a config it was never meant to read. A local module must win.
sys.path.insert(0, _HERE)
import kleal_lib as base                      # keyless shared helpers (uses base._extract_json)
import settings                            # живые настройки: промпты и температура из панели
import kleal_contracts as kc                  # §4 canonical data contracts (builders/validators; keyless)
import kleal_intent as ki                     # §5 intent compiler + clarification policy (keyless, LLM-free)
import kleal_taxonomy as kt                   # §6 governed taxonomy layer (read-only narrator; keyless, no FS at import)
import kleal_completion as kcf                # §10.2 completion factors (transparent operational signals; keyless)
import kleal_ml_boundary as kmlb              # §10.3 ML-migration boundary manifest (declarative; keyless)
import kleal_protocol as kp                   # §13 typed agent protocol (actions/envelope/waves/guards; LLM-free)
import kleal_states as ks                      # §14 transaction state machines + race protection (keyless, LLM-free)
import mplan_rules as mpr                      # правила сделки 1:1: одна таблица на все ручки mp_*
import kleal_groups as kg                       # §15 group formation core (PILOT-DISABLED scaffolding; keyless, LLM-free)
import kleal_candidates as kct                  # §16 events/rooms/venues candidate types (PILOT-DISABLED; keyless, LLM-free)
import intent_map_feed as imf                   # privacy-safe offline/online intent map read models
from llm_client import llm_complete           # the ONLY model access (HTTP -> llm-service)
from http_util import send_json as _send_json_raw, read_json
from geo import haversine as _haversine   # одна формула на дерево, см. shared/geo.py
import vibe as kvibe                      # настрой из теста характера: одно правило на все службы
import db                            # хранилище: postgres или файл — решает KLEAL_DB
import kleal_auth                     # кто прислал запрос; пока ТОЛЬКО наблюдение, см. _watch_owner
import mq                            # очередь заданий: rabbit или ничего — решает KLEAL_MQ
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("MATCHING_PORT", "7074"))
MODEL_ID = os.environ.get("V2_MODEL", "llama_self")


# ======================= BUDDY AGENT (intent parsing + matching) =======================
# The core loop from the TZ: free-text query -> structured intent -> ranked candidates ->
# agent-to-agent negotiation -> curated result. Uses the LLM to parse, deterministic scoring to rank.
# Hierarchical interest taxonomy: BROAD category -> SUB-category -> interest words.
import io
import json
# ТАКСОНОМИЯ ЧИТАЕТСЯ ИЗ ОБЩЕГО РЕЕСТРА, А НЕ ЛЕЖИТ ЗДЕСЬ ВТОРОЙ КОПИЕЙ.
#
# Копий было две: Бади читал `shared/interests.json`, ранжировщик держал свой литерал на 139 строк.
# Сверка 18.09.2026 показала, что они совпадают ТОЧНО (8 широких, 415 слов, 86 синонимов, ноль
# расхождений) — вторая копия не давала ничего, кроме обязанности не разойтись. А цена расхождения
# молчалива и высока: тема, известная Бади и неизвестная ранжировщику, не просто не находит пары —
# она обнуляет выдачу целиком, потому что `_base_tier` вернёт none по ВСЕМ кандидатам.
#
# Теперь источник один, и новый ключ дописывается в одном месте.
#
# ПАДАЕМ ГРОМКО. Урезанная таксономия страшнее отсутствующей: сервис поднимется и будет молча
# отдавать ноль кандидатов на любой запрос, а снаружи это неотличимо от «никто не подошёл».
# Поэтому при недочитанном реестре — исключение при импорте.
def _load_taxonomy():
    _path = os.path.join(_HERE, "..", "..", "shared", "interests.json")
    with io.open(_path, encoding="utf-8") as _f:
        _reg = json.load(_f)
    _tree = _reg.get("tree") or {}
    _syn = _reg.get("synonyms") or {}
    _words = sum(len(_ws or []) for _subs in _tree.values() for _ws in (_subs or {}).values())
    if len(_tree) < 5 or _words < 300 or len(_syn) < 40:
        raise RuntimeError(
            "shared/interests.json недочитан: %d широких, %d слов, %d синонимов. "
            "С такой таксономией ранжировщик молча вернёт ноль по любому запросу." % (
                len(_tree), _words, len(_syn)))
    return _tree, _syn


TAXONOMY, SYNONYMS = _load_taxonomy()
# curated adjacency between BROAD categories (a mild "related" bonus)
# Adjacency is deliberately conservative — over-broad links made a coffee search surface a Dota player
# ("social" ~ "games"). Keep only genuinely related neighbours.
ADJACENCY = {'sports':['outdoors'], 'social':['culture','music','learning'],
             'games':['tech'], 'culture':['learning','music'],
             'tech':['games','learning'], 'music':['culture'],
             'outdoors':['sports'], 'learning':['culture','tech']}
_IDX = {}
for _b, _subs in TAXONOMY.items():
    for _s, _ws in _subs.items():
        for _w in _ws: _IDX[_w] = (_b, _s)

def _norm(w):
    w = str(w).strip().lower().replace(' ', '')
    return SYNONYMS.get(w, w)

# ПАМЯТЬ НА ОТВЕТЫ. Слово, которого нет в словаре точным попаданием, стоит полного прохода по
# `_IDX` — а зовут `cat_of` тысячи раз за один поиск: профиль живого запроса 15.09.2026 дал
# 16 577 вызовов и 5,7 с из 20. Разных слов при этом десятки: интересы повторяются у сотен людей.
#
# Отпечаток словарей в ключе, а не просто слово: `_IDX` и `SYNONYMS` (через `_norm`) правит
# `graph_txn` — тестовый канал правок графа. Сменился размер — память сбрасывается; сам `graph_txn`
# вдобавок чистит её явно, потому что правка может заменить значение, не меняя размера.
_CAT_CACHE = {}
_CAT_SIG = None


def cat_of(word):
    """(broad, sub) for an interest/topic, matched against the KNOWN vocabulary (exact, then prefix>=5).
    Never a raw substring — so no 'art' in 'party', and >=5 stops short words like 'over'->overwatch, 'star'->startups.
    Short real forms (hike, swim, climb...) are handled by SYNONYMS, not by the prefix rule."""
    global _CAT_SIG
    sig = (len(_IDX), len(SYNONYMS))
    if sig != _CAT_SIG:
        _CAT_CACHE.clear()
        _CAT_SIG = sig
    w = _norm(word)
    got = _CAT_CACHE.get(w)
    if got is not None:
        return got
    res = _IDX.get(w)
    if res is None:
        res = (None, None)
        if len(w) >= 5:
            for k, bs in _IDX.items():
                if k.startswith(w) or w.startswith(k):
                    res = bs
                    break
    _CAT_CACHE[w] = res
    return res

def same_topic(t, x):
    t, x = _norm(t), _norm(x)
    if t == x: return True
    ct, cx = cat_of(t), cat_of(x)
    return len(t) >= 4 and len(x) >= 4 and (t.startswith(x) or x.startswith(t)) and ct[1] and ct[1] == cx[1]

def _wtok(s):
    return [w for w in re.findall(r"[a-zа-яё0-9]+", str(s).lower()) if len(w) >= 3]

def _wshare(a, b):
    """Literal or safely inflected shared word between two OFF-TAXONOMY strings.

    Generic polysemes need resolved context, and arbitrary common prefixes are insufficient:
    stock market != food market and cryptography != cryptocurrency.
    """
    try:
        from matching_core.taxonomy import concepts as _concepts
    except Exception:
        _concepts = None
    ambiguous = {"market", "mercado", "рынок", "project", "проект",
                 "exchange", "intercambio", "обмен"}
    A = [w for w in _wtok(a) if w not in ambiguous]
    B = [w for w in _wtok(b) if w not in ambiguous]
    for x in A:
        for y in B:
            if x == y: return True
            if _concepts is not None and _concepts.token_equivalent(x, y): return True
    return False

# ============================================================ мост через темы фильтрации (фразами)
#
# ЗАЧЕМ. Рукописная таксономия знает «finance», но не знает «опционы», «finanzas», «economía».
# Между незнакомыми словами остаётся лишь запасной путь «общее слово буквально», а у «опционы» и
# «finanzas» общих слов нет. Поэтому запрос «поговорить про опционы» находил ровно одного человека
# из 714 — того, у кого в профиле стоит само слово `finance`. Снято с телефона 21 августа.
#
# ПОЧЕМУ ФРАЗАМИ, А НЕ СЛОВАМИ. Ровно так уже пробовали, и это дало мусор. `_teach` в Бадди берёт
# у фильтрации список тем ФРАЗЫ и учит каждое слово из него ОДНОЙ категорией фразы. Для «падел в
# Грасии на выходных» темы — [padel, gracia, weekend], и в карту уходит «gracia → спорт/падел» и
# «weekend → спорт/ракетки». Проверено на боксе: из 136 выученных слов такие — заметная часть.
# Включи это в поиск, и все барселонцы совпадут по падлу.
#
# Здесь хранится другое: ФРАЗА -> её темы. Мы никогда не утверждаем, что «gracia» — это падел; мы
# помним, что у фразы «падел в грасии на выходных» темы {padel, gracia, weekend}. Совпадение — это
# пересечение наборов, и общие слова из него выброшены. Тогда «падел» и та фраза сходятся по
# `padel`, а «поход на выходных» с ней — ни по чему.
_PHRASES_PATH = os.environ.get(
    "KLEAL_PHRASE_TOPICS",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "phrase_topics.json"))

# Темы, по которым совпадать нельзя: они есть почти у всего и связали бы всех со всеми. Это НЕ
# стоп-список интересов — «finance» интересом быть может, а вот темой для сближения «weekend» нет.
_TOPIC_STOP = {
    "weekend", "weekends", "weekday", "morning", "evening", "afternoon", "night", "today",
    "tomorrow", "hour", "week", "month", "year", "time", "day", "days",
    "people", "person", "friend", "friends", "partner", "someone", "somebody", "group", "company",
    "meeting", "meet", "meetup", "hangout", "socializing", "friendship", "hello", "greeting",
    "activity", "activities", "hobby", "hobbies", "fun", "new", "local", "city", "place", "places",
    "work", "play", "playing", "watching", "doing", "making", "care", "match", "fire", "thing",
    "things", "stuff", "interest", "interests", "conversation", "chat", "talk", "discussion",
}

_PHRASES_LOCK = threading.Lock()
_PHRASES_CAP = 20000


def _norm_phrase(s):
    return " ".join(str(s or "").lower().split())[:120]


def _load_phrases():
    try:
        with open(_PHRASES_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        out = {}
        for k, v in d.items():
            ts = {str(t).lower().strip() for t in (v or []) if str(t).strip()}
            ts = {t for t in ts if t not in _TOPIC_STOP and len(t) >= 3}
            if ts:
                out[_norm_phrase(k)] = ts
        return out
    except Exception:
        return {}


PHRASE_TOPICS = _load_phrases()


def learn_phrases(items):
    """items: [{"phrase": "...", "topics": [...]}]. Возвращает, сколько фраз стало известно.

    Пустой набор тем НЕ запоминается: «ничего не понял» и «понял, что тем нет» на поиске ведут
    себя одинаково, а вот перезаписать этим уже известную фразу — значит её потерять.
    """
    added = 0
    with _PHRASES_LOCK:
        for it in items or []:
            if not isinstance(it, dict):
                continue
            ph = _norm_phrase(it.get("phrase"))
            ts = {str(t).lower().strip() for t in (it.get("topics") or []) if str(t).strip()}
            ts = {t for t in ts if t not in _TOPIC_STOP and 3 <= len(t) <= 40}
            if not ph or not ts or len(PHRASE_TOPICS) >= _PHRASES_CAP:
                continue
            if PHRASE_TOPICS.get(ph) == ts:
                continue
            PHRASE_TOPICS[ph] = ts
            added += 1
        if added:
            try:
                tmp = _PHRASES_PATH + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({k: sorted(v) for k, v in PHRASE_TOPICS.items()}, f, ensure_ascii=False)
                os.replace(tmp, _PHRASES_PATH)   # атомарно: файл читается на каждом поиске
            except Exception:
                pass
    return added


def topics_of(s):
    """Темы фразы. Сама фраза тоже считается темой — иначе два человека с одинаковым интересом,
    которого фильтрация не видела, перестали бы сходиться через этот мост."""
    ph = _norm_phrase(s)
    if not ph:
        return set()
    # Deterministic concept tags complement the learned phrase map. They make compound interests
    # ("trading forex", "street photography") useful on their first request without writing to the
    # production phrase store, while broad ambiguous words intentionally receive no tags.
    try:
        from matching_core.taxonomy import concepts as _concepts
        stable = _concepts.topic_tags(ph)
    except Exception:
        stable = set()
    got = PHRASE_TOPICS.get(ph)
    if got:
        return set(got) | stable | ({ph} if ph not in _TOPIC_STOP else set())
    return stable | ({ph} if ph not in _TOPIC_STOP else set())


_TEACH_SENT = set()          # фразы, уже отправленные в очередь этим процессом — не слать дубли


def resolve_query_topics(topics, phrase=""):
    """Темы ЗАПРОСА для моста — только из уже выученного, без единого сетевого вызова.

    Раньше незнакомая фраза разбиралась фильтрацией прямо здесь, внутри поиска, и тут же
    запоминалась. Это дало мост первому же запросу, но ценой, которую показала батарея: поиск
    ждал модель (секунды на сценарий), а два одинаковых вызова подряд отвечали по-разному,
    потому что первый УЧИЛСЯ между ними. Девяносто сценариев золотой батареи из девяноста трёх
    упали ровно на «NON-DETERMINISTIC result» — и это не придирка теста: тот же поиск, повторённый
    человеком, находил других людей.

    Теперь путь поиска только читает. Незнакомое уходит заданием в `teach.phrases` — воркер
    спросит фильтрацию и научит живой матчинг через /api/agent/learn-phrases, обычно за секунды.
    А ТЕКУЩИЙ поиск строит мост из тем интента: вызывающий уже прогнал текст запроса через
    фильтрацию, когда собирал интент, — это ответ той же модели, полученный до входа сюда.
    Выученная фраза точнее тем, что несёт контекст («поговорить про опционы» -> финансы, голое
    «options» -> варианты выбора), поэтому когда она есть — она в приоритете.
    """
    ph = _norm_phrase(phrase) if phrase else ""
    # «Выучено» проверяется по PHRASE_TOPICS напрямую: topics_of для этого не годится — она по
    # замыслу считает темой САМУ фразу (сторона кандидатов на этом сходится), то есть непустой
    # ответ у неё есть всегда, и фолбэк на темы интента никогда бы не сработал.
    learned = bool(ph and PHRASE_TOPICS.get(ph))
    # Чему научиться на будущее: сама фраза и до трёх слов запроса, которых нет ни в выученном,
    # ни в таксономии. Дедупликация в памяти процесса: очередь и так переживёт дубль, но слать
    # одно и то же на каждый повтор поиска — шум в outbox и в панели.
    ask = []
    if phrase and not learned and ph not in _TEACH_SENT:
        ask.append(str(phrase))
    ask += [str(t) for t in (topics or [])
            if t and _norm_phrase(t) not in PHRASE_TOPICS and not cat_of(t)[0]
            and _norm_phrase(t) not in _TEACH_SENT][:3]
    if ask:
        for a in ask:
            _TEACH_SENT.add(_norm_phrase(a))
        try:
            mq.send("teach.phrases", {"phrases": ask})
        except Exception:
            pass                          # очередь лежит — выучим в другой раз; поиск не ждёт
    out = topics_of(phrase) if learned else set()
    if not learned and ph and ph not in _TOPIC_STOP:
        out.add(ph)                       # буквальное совпадение запроса с интересом — тоже мост
    # Слова интента разворачиваются через topics_of, а не кладутся как есть: выученное слово несёт
    # свои темы («кофе» -> coffee — иначе русский запрос никогда не сойдётся с английским
    # интересом), невыученное остаётся самим собой. Порог в topics_join держит разросшийся набор:
    # одного общего слова, как и раньше, мало.
    for t in (topics or ()):
        out |= topics_of(t)
    return out

def topics_join(ta, tb):
    """Достаточно ли двум наборам тем ОБЩЕГО, чтобы считать фразы про одно и то же.

    ОДНОГО СОВПАВШЕГО СЛОВА МАЛО, и это стоило ложных находок. Запрос «Акции» разбирается в
    {finance, investing, market, stock}, а «mercado gastronómico» — в {cuisine, food, gastronomy,
    market}. Пересечение есть — ровно `market`, — и мост радостно сводил биржу с продуктовым
    рынком. Снято с панели 21 августа: в выдаче по «Акции» стояли рыбный рынок и уличная еда.

    Частотой это не лечится: `market` встречается всего в одиннадцати фразах из 1683 (0,65%), то
    есть по редкости он неотличим от честного `fishing`. Дело не в редкости, а в многозначности.

    Поэтому мерим ДОЛЮ, а не факт: связываем, если общих тем хотя бы две, либо если общее
    покрывает половину меньшего набора. Тогда:

        «Акции» ~ «food market»   1 из 4 = 0.25   -> не связываем
        «Акции» ~ «trading»       3 из 4 = 0.75   -> связываем
        «Акции» ~ «finanzas»      2 общих         -> связываем
        «Рыбалка» ~ «подлёдная рыбалка»  1 из 1   -> связываем

    Последняя строка и есть причина, почему нельзя просто потребовать двух совпадений: у короткого
    запроса тема одна, и одна же — всё, что у него есть.
    """
    if not ta or not tb:
        return False
    common = ta & tb
    if not common:
        return False
    if len(common) >= 2:
        return True
    return len(common) / float(min(len(ta), len(tb))) >= 0.5


def topic_bridge(a, b):
    """Сошлись ли две фразы по темам фильтрации. Хотя бы одна из них должна быть РАЗОБРАНА —
    иначе это просто сравнение двух строк, которое и так делает `_wshare`, и мост тут ни при чём."""
    pa, pb = _norm_phrase(a), _norm_phrase(b)
    if pa not in PHRASE_TOPICS and pb not in PHRASE_TOPICS:
        return False
    return topics_join(topics_of(a), topics_of(b))


# Темы ФРАЗЫ запроса на время одного поиска.
#
# Параметром их не передать: ранжирует не `_retrieve`, а движок (matching_core / core_v2), и он
# зовёт впрыснутый `topical` РОВНО ДВУМЯ аргументами. Добавленный третий до него не доходил, и
# мост молчал ровно там, где решается выдача, — проверено живьём: запрос уходил в «широкие
# предложения», как будто моста нет.
#
# Локально для потока, а не глобально: сервис многопоточный, и общая переменная подмешивала бы
# темы одного человека в поиск другого.
_QCTX = threading.local()


def _set_query_bridge(topics):
    _QCTX.bridge = set(topics or ())


def _query_bridge():
    return getattr(_QCTX, "bridge", None) or ()


def topical(topics, interests, bridge=()):
    """Best topical tier (4 exact > 3 sub-cat / мост тем > 2 broad-cat > 1 adjacent > 0 none) + matched.

    МОСТ ЧЕРЕЗ ТЕМЫ ФИЛЬТРАЦИИ стоит ярусом 3 — ниже точного совпадения, выше общей ветки. Он
    закрывает ровно ту дыру, из-за которой «поговорить про опционы» находило одного человека из
    714: рукописная таксономия знает `finance`, но не знает ни «опционы», ни «finanzas», ни
    «economía», а между двумя незнакомыми словами оставался лишь буквально общий токен.

    Проверяется ПОСЛЕ ярусов таксономии и до запасного пути по словам: там, где таксономия знает
    оба слова, ей и верить — она рукописная и точнее. Мост нужен там, где она молчит.
    """
    matched = set(); best = 0
    bridge = set(bridge) or set(_query_bridge())
    xb = [(x, cat_of(x)) for x in interests]
    for t in topics:
        bt, st = cat_of(t)
        for x, (bx, sx) in xb:
            if same_topic(t, x): matched.add(_norm(x)); best = max(best, 4)
            elif st and st == sx: best = max(best, 3)
            elif bt and bt == bx: best = max(best, 2)
            elif bt and bx and bx in ADJACENCY.get(bt, []): best = max(best, 1)
            # Мост: наборы тем пересеклись по неслужебной теме. `bridge` — темы ФРАЗЫ запроса,
            # они точнее скомпилированных слов (см. resolve_query_topics).
            elif topic_bridge(t, x) or (bridge and topics_join(set(bridge), topics_of(x))):
                matched.add(_norm(x)); best = max(best, 3)
            # neither side is in the taxonomy -> fall back to a literal shared interest word, so real
            # interests the vocabulary doesn't cover ("apple", "рыбалка", "labubu") still match each other.
            elif not bt and not bx and _wshare(t, x): matched.add(_norm(x)); best = max(best, 4)
    return best, matched

def _cat_of(tok):   # back-compat: broad category only
    return cat_of(tok)[0]

# ---- §6 governed taxonomy layer: bind the REAL scoring taxonomy into the read-only narrator (kt) ----
# kt never imports app (avoids a cycle) and never scores — app injects its own functions so kt narrates the
# SAME decision the engine makes. graph_txn is the ONLY sanctioned edit channel for kt's governance PROOFS
# (alias_invariant / shadow_replay Mode B): it transactionally mutates THIS module's own taxonomy globals
# under a lock and guarantees restore in finally. It transiently changes real scoring, so it is TEST-ONLY /
# offline — never call it from inside a live request handler.
_GRAPH_LOCK = threading.Lock()

@contextlib.contextmanager
def graph_txn(edits):
    """Apply taxonomy-graph edits to the live globals so the injected topical() actually resolves them, then
    restore. edits = {'synonyms': {variant: canonical}, 'adjacency': {broad: [neighbours]},
    'taxonomy': {(broad, sub): [words]}}. TEST-ONLY — see the note above."""
    edits = edits or {}
    with _GRAPH_LOCK:
        saved_syn, saved_adj = dict(SYNONYMS), copy.deepcopy(ADJACENCY)
        saved_tax, saved_idx = copy.deepcopy(TAXONOMY), dict(_IDX)
        try:
            for v, canon in (edits.get("synonyms") or {}).items():
                SYNONYMS[str(v).strip().lower().replace(" ", "")] = str(canon).strip().lower().replace(" ", "")
            for (b, s), words in (edits.get("taxonomy") or {}).items():
                TAXONOMY.setdefault(b, {}).setdefault(s, [])
                for w in words:
                    wn = str(w).strip().lower().replace(" ", "")
                    if wn not in TAXONOMY[b][s]:
                        TAXONOMY[b][s].append(wn)
                    _IDX[wn] = (b, s)
            for b, neigh in (edits.get("adjacency") or {}).items():
                ADJACENCY[b] = list(neigh)
            _CAT_CACHE.clear()            # словарь под правкой — прежние ответы недействительны
            yield
        finally:
            SYNONYMS.clear(); SYNONYMS.update(saved_syn)
            ADJACENCY.clear(); ADJACENCY.update(saved_adj)
            TAXONOMY.clear(); TAXONOMY.update(saved_tax)
            _IDX.clear(); _IDX.update(saved_idx)
            _CAT_CACHE.clear()            # и после отката тоже

kt.bind_engine(topical=topical, norm=_norm, cat_of=cat_of, same_topic=same_topic,
               TAXONOMY=TAXONOMY, SYNONYMS=SYNONYMS, ADJACENCY=ADJACENCY, graph_txn=graph_txn)

# ============================ MATCHING ENGINE (production-parity demo) ============================
# Mirrors dating/apps/api scoring: hard gates -> base tier (reciprocal/exact/adjacent/related/broad)
# -> capped modifiers -> deterministic tiebreak -> diversify. 100% deterministic; no LLM, no randomness.

ME_LATLON = (41.3874, 2.1686)          # owner location (Barcelona centre) — same as the client map
COOLDOWN_DAYS = 7                      # a candidate who declined the owner is muted this long
MAX_PENDING   = 6                      # a candidate with >= this many open proposals is "overloaded"
MIN_AGE       = 18                     # hard 18+ floor
GEO_NEAR, GEO_MID, GEO_FAR = 1.5, 3.5, 7.0   # km bands for the proximity bonus

# All weights are tunable at runtime via GET/POST /api/agent/weights (mirrors the prod admin panel).
WEIGHTS = {
    # base tiers (dominant signal)
    'tier_reciprocal': 85, 'tier_exact': 70, 'tier_exact_step': 4,
    'tier_adjacent': 55, 'tier_related': 40, 'tier_broad': 30,
    # capped modifiers
    'lang': 6, 'vibe': 5, 'mood_open': 3, 'fresh': 2,
    'geo_near': 8, 'geo_mid': 5, 'geo_far': 2,
    'fb_accept': 8, 'fb_reject': -20, 'entity': 10,
    'time_fit': 8, 'time_conflict': -6, 'role_same': 5, 'role_diff': -8,
    # tier thresholds (for the human-readable tier label) + output shaping
    'thr_t0': 85, 'thr_t1': 70, 'thr_t2': 55, 'thr_t3': 40, 'thr_t4': 30,
    'diversity_max': 3, 'top_n': 10,
}
def get_weights(): return dict(WEIGHTS)
def set_weights(patch):
    """§23.2.11 single source of truth — the sha-pinned config is authoritative for all weights/thresholds. This
    legacy runtime tuner is FROZEN: it no longer mutates WEIGHTS (a request body can never create a second weight
    source), it just echoes the current values read-only."""
    return dict(WEIGHTS)

# ---- server-side session store (file-backed) — mirrors the client's localStorage + holds the feedback loop ----
STORE_PATH = os.environ.get("KLEAL_STORE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "kleal_store.json"))
# Geocoding is a best-effort enrichment, never a persistence prerequisite. Successful lookups are
# cached beside the store (or at KLEAL_GEOCODE_CACHE) and failures are bounded by timeout/retry.
_MAP_GEOCODER = imf.SafeGeocoder(
    cache_path=os.environ.get("KLEAL_GEOCODE_CACHE", STORE_PATH + ".geocode-cache.json"),
    timeout=float(os.environ.get("KLEAL_GEOCODE_TIMEOUT", "1.25")),
    attempts=int(os.environ.get("KLEAL_GEOCODE_ATTEMPTS", "2")),
)
# §14: a REENTRANT lock so the accept transaction can hold ONE lock across revalidate + slot-claim +
# _record_outcome (which re-acquires it) without deadlocking — closes the read-then-write gap at the send boundary.
_STORE_LOCK = threading.RLock()
def _load_store():
    """Состояние: из базы, если она ведущая, иначе из файла — как было всегда.

    База не обязана быть: при KLEAL_DB=json (по умолчанию) сюда даже не заглядываем, и сервис
    поднимается на машине, где postgres не установлен."""
    if db.ENABLED:
        try:
            db.ensure_schema()
            got = db.load_store()
            if got:
                return got
            # База пуста, а файл есть — первый запуск после переноса ещё не случился. Читаем файл
            # и НЕ падаем: пустое состояние выглядит как «все планы исчезли».
        except Exception as e:
            print("[store] postgres недоступен, читаю файл: %s: %s" % (type(e).__name__, str(e)[:120]))
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as f: return json.load(f)
    except Exception:
        return {}
SESSION = _load_store()
def _save_store():
    """Записать состояние.

    В базе уезжают ТОЛЬКО изменившиеся ключи верхнего уровня (см. shared/db.py) — вместо
    переписывания всего файла на каждое нажатие. Зеркало в файл остаётся, пока KLEAL_DB=mirror:
    на время перехода JSON — бесплатная резервная копия, и откат ничего не стоит.

    Ошибка базы НЕ роняет запрос: человек уже сделал действие, и падение на записи он прочитает
    как «не сработало», хотя в памяти всё применилось. Пишем в файл и живём дальше.
    """
    if db.ENABLED:
        try:
            # ПОД ТЕМ ЖЕ ЗАМКОМ, под которым состояние меняют. Без него сериализация шла, пока
            # соседний запрос добавлял ключ, — «dictionary changed size during iteration», и запись
            # молча уходила в файл, которого при базе никто не читает (26.09.2026: так потерялась
            # привязка 126 интентов к id). Замок — RLock: вызов изнутри `with _STORE_LOCK` безопасен.
            with _STORE_LOCK:
                db.save_store(SESSION)
            if not db.MIRROR_JSON:
                return
        except Exception as e:
            print("[store] запись в postgres не удалась, падаю на файл: %s: %s"
                  % (type(e).__name__, str(e)[:120]))
    try:
        with open(STORE_PATH, "w", encoding="utf-8") as f: json.dump(SESSION, f)
    except Exception:
        pass
def _me_or_claimed(handler, claimed):
    """УСТАРЕЛО с 26.09.2026: личность запроса — `handler._pid` (см. H._whoami). Оставлено для
    совместимости вызовов: возвращает id по сессии, а без неё — пусто, имя из тела не принимается."""
    return getattr(handler, "_pid", "") or ""


def _me_or_claimed_legacy(handler, claimed):
    """Имя своей строки, если сессия его называет; иначе — заявленное в запросе.

    ЗАПРЕТА ЗДЕСЬ НЕТ, И ЭТО НАМЕРЕННО. Опросные ручки (планы, переписки, входящие) принимают за
    неделю 22788 запросов без токена — это бот-эмулятор `kleal-life` на петле, у которого аккаунта
    нет и быть не может. Отказ выкинул бы его целиком, а вместе с ним и всю проверку сценариев.

    Но ПОДМЕНА закрыта: вошедший человек получает СВОИ планы и переписку, что бы он ни написал в
    `self`. Сессия сильнее запроса. Осталось ровно одно окно — запрос совсем без токена; закрыть
    его можно будет, когда у эмулятора появится собственный внутренний ключ, а у шести аккаунтов,
    чей профиль не доехал до users.json, — строка, по которой их узнаёт `caller_name`.
    """
    mine = kleal_auth.caller_name(handler)
    return mine or claimed


def _own_uid(handler):
    """ЧЬИ ЭТО ЗАПИСИ — решает сессия, а не тело запроса. Пусто, если назвать себя нечем.

    Личные записи этого сервиса — оценки кандидатов, чёрный список и сохранённые поиски — лежат
    в SESSION под ключом `uid`, и до сих пор этот ключ приходил ИЗ ЗАПРОСА: `body.get("uid", "me")`.
    Знать надо было ровно одно — как человека зовут на экране, — и посторонний читал его чёрный
    список, дописывал за него оценки и удалял сохранённые поиски. Проверки не было никакой.

    ПОЧЕМУ ЗДЕСЬ МОЖНО ЗАПРЕЩАТЬ, А НА СОСЕДНИХ РУЧКАХ ЕЩЁ НЕТ. Наблюдение (`_watch_owner`) за
    неделю дало цифры: 2593 запроса с сессией и совпавшим именем, 22788 — с именем и БЕЗ сессии,
    одно расхождение. Запрет вслепую выкинул бы девять из десяти. Но у этих четырёх ручек за ту же
    неделю НОЛЬ обращений — ни одного, ни с токеном, ни без, — поэтому их можно закрыть сегодня и
    ничего не сломать. Опросные ручки (mplans, threads, inbox) закрываются отдельно и после того,
    как станет ясно, чей это трафик без токена: у приложения токен есть всегда, когда человек вошёл
    (kleal-app/src/api.ts).
    """
    # Ключ личных записей — id человека (сессия), а не подпись: у тёзок разные чёрные списки.
    return getattr(handler, "_pid", "") or ""


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# ЛИЧНОСТЬ — ЭТО ID ЧЕЛОВЕКА, А НЕ ИМЯ (docs/IDENTITY.md, 26.09.2026)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Человек = строка популяции с постоянным `id`. Имя — подпись: у двух людей она совпадает, и это
# нормально. Всё, что принадлежит человеку (интенты, заявки, переписка, планы, группы), хранит его
# id рядом с подписью — `owner_id`, `from_id`, `to_id`… — и «чьё это» решается ТОЛЬКО по id.
#
# КАК УЗНАТЬ, КТО ПРИСЛАЛ ЗАПРОС: сессия (Bearer → аккаунт → его строка → id). Имя из тела
# запроса личностью не является никогда. Единственное исключение — запрос БЕЗ сессии (бот-эмулятор
# `kleal-life`, смоук-тесты): ему разрешено назваться только тем, кто не принадлежит ни одному
# аккаунту, а если под этим именем нет ни одной строки — он получает временную личность
# `anon:<имя>`, которая с настоящим человеком не склеится никогда.
#
# Почему так, а не «имя уникально»: анкета хранит одно имя без фамилии, и совпадения — норма
# («Иван», «Анна»). 26.09.2026 четыре аккаунта «Иван» видели интенты друг друга, а регистрация
# каждого нового затирала анкету прежнего.
ANON = "anon:"
# НЕ `_IDX`: это имя занято словарём категорий интересов наверху файла (его читают `cat_of` и
# `cat_of_fixed`). 26.09.2026 индекс людей назывался так же, при импорте затёр словарь, и подбор
# несколько часов не узнавал ни одного интереса — (None, None) на любое слово.
_PEOPLE = {"src": None, "built": False, "checked": 0.0, "forced": 0.0, "by_id": {}, "by_name": {}}
_PEOPLE_TTL = 1.0


def _people_index(force=False):
    """{id: строка} и {имя: [строки]} по текущему пулу. Пересчитывается, только когда пул сменился.

    Строится по СЫРОМУ пулу (`_load_pool_rows`), а не по `load_candidates()`: та на каждый вызов отдаёт
    НОВЫЙ список с дописанными полями, сравнение «тот же ли объект» не срабатывало никогда, и индекс
    пересобирался на каждый `_person` — десятки раз за запрос, с записью в журнал каждый раз.
    Версию пула спрашиваем у базы не чаще раза в `_PEOPLE_TTL`: ответ на один запрос зовёт `_person`
    на каждое поле с человеком. Свежую регистрацию `_person` добирает принудительной проверкой."""
    now = time.time()
    if _PEOPLE["built"] and not force and now - _PEOPLE["checked"] < _PEOPLE_TTL:
        return _PEOPLE
    store = _load_pool_rows()
    _PEOPLE["checked"] = now
    if not _PEOPLE["built"] or _PEOPLE["src"] is not store:
        rows = [r for r in (store or []) if isinstance(r, dict)]
        if MERGE_DEMO or (not rows and DEMO_FALLBACK):
            seen = {str(u.get("name", "")).strip().lower() for u in rows}
            rows += [c for c in CANDIDATES if str(c.get("name", "")).strip().lower() not in seen]
        by_id, by_name = {}, {}
        for r in rows:
            if not isinstance(r, dict):
                continue
            rid = str(r.get("id") or "").strip()
            if rid:
                by_id[rid] = r
                by_id.setdefault(rid.lower(), r)
            nm = _norm_name(r.get("name"))
            if nm:
                by_name.setdefault(nm, []).append(r)
        _PEOPLE.update(src=store, built=True, by_id=by_id, by_name=by_name)
    return _PEOPLE


def _person(pid):
    """Строка человека по id или None. Регистр не важен: словари хранилища держат ключи
    нормализованными (`_norm_name`), и id оттуда приходит в нижнем регистре."""
    s = str(pid or "").strip()
    if not s:
        return None
    idx = _people_index()["by_id"]
    got = idx.get(s) or idx.get(s.lower())
    if got is None and not s.lower().startswith(ANON) and time.time() - _PEOPLE["forced"] > 0.5:
        _PEOPLE["forced"] = time.time()
        idx = _people_index(force=True)["by_id"]
        got = idx.get(s) or idx.get(s.lower())
    return got


def _names():
    """Подписи тех, кого нет в пуле: временные личности `anon:` и удалённые люди. Запоминаются,
    когда личность впервые появляется, чтобы при выдаче было что показать вместо id."""
    return SESSION.setdefault("_names", {})


def _remember(pid, display):
    if pid and display:
        k = _norm_name(pid)
        if _names().get(k) != display:
            _names()[k] = str(display)[:80]


def _display(pid, fallback=""):
    """Подпись человека для показа: из его строки, иначе из реестра подписей, иначе запасная."""
    p = _person(pid)
    if p and p.get("name"):
        return str(p.get("name"))
    s = str(pid or "")
    known = _names().get(_norm_name(s))
    if known:
        return known
    return fallback or (s[len(ANON):] if s.lower().startswith(ANON) else "")


def _is_pid(s):
    """Это id человека (из пула или временный `anon:`)? Имена с id не совпадают — проверено на
    живом пуле 26.09: 871 id, все в нижнем регистре, без пробелов, ни один не равен чьему-то имени."""
    if not isinstance(s, str) or not s:
        return False
    if s.lower().startswith(ANON):
        return True
    return _person(s) is not None


def _canon_pid(s):
    """Канонический id: у человека из пула — ровно как в его строке, у временной личности — `anon:`."""
    s = str(s or "").strip()
    if not s:
        return ""
    if s.lower().startswith(ANON):
        return ANON + _norm_name(s[len(ANON):])        # временная личность — всегда в нижнем регистре
    p = _person(s)
    return str(p.get("id")) if p else ""


def _photo_of(pid):
    """Фото человека по id — не по имени: у тёзок разные лица."""
    return (_person(pid) or {}).get("photo") or None


def _tz_of(pid):
    """Часовой пояс человека по id."""
    return str((_person(pid) or {}).get("tz") or "")


def _counterparts(me, gid=""):
    """С кем у `me` уже есть связь. Нужна ТОЛЬКО чтобы развести тёзок, когда клиент прислал подпись
    без id: из двух «Иванов» берётся тот, с кем человек уже имеет дело, — если такой ровно один.
    В группе (`gid`) круг — её организатор, участники и приглашённые; иначе — заявки, переписка и
    планы 1:1. Это не угадывание: среди СВОИХ собеседников имя однозначно."""
    me = str(me or "").strip().lower()
    out = set()
    if not me:
        return out
    if gid:
        g = _gi_find(gid) or {}
        out.add(str(g.get("owner") or "").lower())
        out.update(str(m.get("name") or "").lower() for m in g.get("members") or [] if isinstance(m, dict))
        for i in _ginvites():
            if isinstance(i, dict) and i.get("gid") == gid:
                out.update((str(i.get("to") or "").lower(), str(i.get("frm") or "").lower()))
    else:
        for box, a, b in (("_requests", "from", "to"), ("_messages", "from", "to"),
                          ("_mplans", "host", "guest")):
            for r in SESSION.get(box) or []:
                if isinstance(r, dict):
                    x, y = str(r.get(a) or "").lower(), str(r.get(b) or "").lower()
                    if x == me:
                        out.add(y)
                    elif y == me:
                        out.add(x)
    out.discard(me)
    out.discard("")
    return out


def _peer(pid_hint="", name="", me="", gid=""):
    """id СОБЕСЕДНИКА из запроса. Приложение присылает id (`to_id`, `with_id`…); подпись принимается,
    только если по ней однозначно находится один человек — во всём пуле или среди тех, с кем `me`
    уже связан (`_counterparts`). Иначе тёзки без id — пусто: угадывать, кому из двух «Иванов» ушло
    сообщение, нельзя. Подпись без строки в пуле — временная личность `anon:` (тесты, эмулятор),
    с настоящим человеком она не совпадёт никогда."""
    c = _canon_pid(pid_hint)
    if c:
        return c
    nm = str(name or "").strip()
    if not nm:
        return ""
    # Kleal — не человек из пула, а отправитель ответов модерации и уведомлений (admin_notify,
    # GR.52). Его реплики лежат под именем «Kleal»; временная личность `anon:kleal` уводила
    # переписку в пустую пару — в «Сообщениях» строка была, а открытый тред показывал «пусто».
    if _norm_name(nm) == _norm_name(SAFETY_SENDER):
        return SAFETY_SENDER
    c = _canon_pid(nm)                    # в поле подписи уже пришёл id — принимаем
    if c:
        return c
    rows = _people_index()["by_name"].get(_norm_name(nm)) or []
    if len(rows) == 1:
        return str(rows[0].get("id") or "")
    if not rows:
        pid = ANON + _norm_name(nm)
        _remember(pid, nm)
        return pid
    if me:
        mine = _counterparts(me, gid)
        hit = [r for r in rows if str(r.get("id") or "").lower() in mine]
        if len(hit) == 1:
            return str(hit[0].get("id") or "")
    return ""


def _unowned_pid(name):
    """Личность для запроса БЕЗ сессии, названного `name`.

    Строка без владельца (бот, посев), и ровно одна → её id. Ни одной строки → `anon:<имя>`.
    Имя принадлежит аккаунту или неоднозначно → пусто: назваться чужим человеком без сессии нельзя.
    """
    nm = _norm_name(name)
    if not nm:
        return ""
    rows = _people_index()["by_name"].get(nm) or []
    if not rows:
        pid = ANON + nm
        _remember(pid, str(name).strip())
        return pid
    free = [r for r in rows if not r.get("owner")]
    if len(free) == 1 and len(rows) == 1:
        return str(free[0].get("id") or "")
    return ""


def _identify(handler, claimed=""):
    """(id, подпись) того, кто прислал запрос. Сессия сильнее всего, что написано в теле."""
    try:
        p = kleal_auth.caller_person(handler, users=load_candidates())
    except Exception:
        p = None
    if p and p.get("id"):
        return str(p.get("id")), str(p.get("name") or "")
    try:
        if kleal_auth.bearer(handler):
            # Токен есть, а строки у аккаунта нет (анкета не пройдена). Это не аноним — это
            # человек без личности; за чужое имя из тела он спрятаться не может.
            return "", ""
    except Exception:
        pass
    pid = _unowned_pid(claimed)
    return pid, (_display(pid, str(claimed or "").strip()) if pid else "")


# ---- выдача: id человека → подпись (и id рядом) -------------------------------------------------
# В хранилище все ссылки на людей — id (`from`, `to`, `owner`, `host`, `members[].name`, ключи
# `responses/live/sides/feedback/votes`…). Приложению нужны подписи. Переводчик стоит на КАЖДОМ
# ответе сервиса (send_json ниже), поэтому ни одна выдача не может «забыть» перевести, а новые
# поля с людьми достаточно добавить в _PERSON_KEYS. Рядом с подписью уезжает id (`from_id`, …):
# приложение сравнивает людей по нему, а подпись только рисует. id и подписи не пересекаются
# (см. _is_pid), так что перевод однозначен.
_PERSON_KEYS = frozenset((
    "from", "to", "frm", "who", "by", "owner", "host", "guest", "other", "heir", "with",
    "address_by", "link_by", "cancelled_by", "fixed_by", "proposed_by", "taken_by", "about",
    "name", "to_user", "place_asked_by", "link_asked_by", "organiser", "asked", "removed_by",
    "candidate", "former"))


_NORMALIZED_LISTS = frozenset(("blocked",))


def _humanize(v, _d=0):
    if _d > 40:
        return v
    if isinstance(v, dict):
        keys = list(v.keys())
        pid_keys = bool(keys) and all(isinstance(k, str) and _is_pid(k) for k in keys)
        out = {}
        for k, x in v.items():
            if pid_keys:
                # Словарь «человек → что-то» (live, sides, votes…): ключ — подпись в том же виде,
                # в каком приложение его ищет (нормализованная), а при совпадении подписей тёзок —
                # id, чтобы один не затёр другого.
                nk = _norm_name(_display(k)) or k
                out[k if nk in out else nk] = _humanize(x, _d + 1)
                continue
            if k == "r" and isinstance(x, dict):
                # Реакции: {эмодзи: [кто]} — приложение сверяет с нормализованной подписью.
                out[k] = {e: [_norm_name(_display(n)) if _is_pid(n) else n for n in (lst or [])]
                          for e, lst in x.items()}
                out["r_ids"] = {e: list(lst or []) for e, lst in x.items()}
                continue
            if isinstance(x, str) and k in _PERSON_KEYS and _is_pid(x):
                out[k] = _display(x)
                idk = "id" if (k == "name" and "id" not in v) else k + "_id"
                if idk not in v:
                    out[idk] = _canon_pid(x) or x
                continue
            if (isinstance(x, list) and x and all(isinstance(e, str) for e in x)
                    and all(_is_pid(e) for e in x)):
                # Чёрный список приложение всегда получало нормализованным — так и оставляем.
                out[k] = ([_norm_name(_display(e)) for e in x] if k in _NORMALIZED_LISTS
                          else [_display(e) for e in x])
                if k + "_ids" not in v:
                    out[k + "_ids"] = [_canon_pid(e) or e for e in x]
                continue
            out[k] = _humanize(x, _d + 1)
        return out
    if isinstance(v, list):
        return [_humanize(x, _d + 1) for x in v]
    return v


def send_json(handler, status, obj):
    """Отправка ответа сервиса — всегда через перевод id → подпись (см. _humanize)."""
    try:
        obj = _humanize(obj)
    except Exception as e:                  # перевод не имеет права ронять ответ
        print("[identity] перевод ответа не удался: %s" % str(e)[:120], flush=True)
    return _send_json_raw(handler, status, obj)


# ---- разовый перевод хранилища с имён на id (identity v2) ------------------------------------
# До 26.09.2026 все ссылки на людей в хранилище матчинга были ИМЕНАМИ. Перевод идёт один раз при
# старте службы (до приёма запросов), под замком, с копией каждого хранилища в `_premig_v2` — откат
# это восстановление копии и прежний код (tools/identity_repair.py rollback-v2). Правило для каждой
# старой ссылки — `_legacy_pid`; если тёзок несколько и все могли сделать запись — берётся тот, чья
# сессия началась ближе всего ДО записи (кто в тот момент был в приложении). Каждое такое решение и
# каждая неразрешённая ссылка — в журнал и в отчёт `_identity.report`.
IDENTITY_V = 2


def _session_near(owner_key, at):
    """Момент последнего входа аккаунта не позже `at` (или 0)."""
    try:
        ss = (((kleal_auth._accounts() or {}).get(owner_key) or {}).get("sessions") or {}).values()
        starts = [float(s.get("created") or 0) for s in ss if float(s.get("created") or 0) <= float(at) + 60]
        return max(starts) if starts else 0.0
    except Exception:
        return 0.0


def _migrate_identity_v2(apply=True):
    import collections as _co
    state = SESSION.get("_identity") or {}
    if int(state.get("v") or 0) >= IDENTITY_V:
        return {"skipped": True, "v": state.get("v")}
    rep = _co.Counter()
    unresolved = _co.Counter()
    guessed = []

    def pid_of(name, at=None):
        s = str(name or "").strip()
        if not s:
            return s
        if _is_pid(s):
            return _canon_pid(s)
        pid = _legacy_pid(s, at)
        if pid:
            rep["resolved"] += 1
            return pid
        rows = _people_index()["by_name"].get(_norm_name(s)) or []
        alive = [r for r in rows if not r.get("owner") or not at
                 or not _account_created(r.get("owner")) or float(at) + 60 >= _account_created(r.get("owner"))]
        if len(alive) > 1 and at:
            scored = sorted(((_session_near(r.get("owner"), at), r) for r in alive if r.get("owner")),
                            key=lambda x: -x[0])
            if scored and scored[0][0] > 0 and (len(scored) == 1 or scored[0][0] != scored[1][0]):
                pick = str(scored[0][1].get("id"))
                guessed.append({"name": s, "at": at, "pid": pick})
                rep["guessed"] += 1
                return pick
        unresolved[_norm_name(s)] += 1
        return s                              # остаётся именем: запись не увидит никто, но и не чужой

    def conv_list(lst, at):
        return [pid_of(x, at) for x in (lst or [])]

    def conv_keys(d, at):
        out = {}
        for k, v in (d or {}).items():
            nk = _norm_name(pid_of(k, at))
            if nk in out and isinstance(out[nk], dict) and isinstance(v, dict):
                continue                      # два тёзки в одном плане слились в одного — первый остаётся
            out[nk] = v
        return out

    def pair_of(a, b):
        return _pair_key(a, b) if a and b else ""

    with _STORE_LOCK:
        keys = ("_requests", "_messages", "_thread_reads", "_mplans", "_blocks", "_reports",
                "_gintents", "_ginvites", "_gmsgs", "_gplans", "_gvotes", "_gremovals", "_groups")
        backup = {k: copy.deepcopy(SESSION.get(k)) for k in keys if SESSION.get(k) is not None}
        for r in SESSION.get("_requests") or []:
            at = r.get("created")
            r["from"], r["to"] = pid_of(r.get("from"), at), pid_of(r.get("to"), at)
            tr = r.get("trace") or {}
            for f in ("by", "taken_by"):
                if tr.get(f):
                    tr[f] = pid_of(tr[f], at)
        for m in SESSION.get("_messages") or []:
            at = m.get("t")
            m["from"], m["to"] = pid_of(m.get("from"), at), pid_of(m.get("to"), at)
            if m.get("from") and m.get("to"):
                m["pair"] = pair_of(m["from"], m["to"])
            if isinstance(m.get("r"), dict):
                m["r"] = {e: [_norm_name(pid_of(n, at)) for n in (lst or [])] for e, lst in m["r"].items()}
            sy = m.get("sys") if isinstance(m.get("sys"), dict) else None
            for f in ("by", "who", "taken_by"):
                if sy and isinstance(sy.get(f), str) and sy.get(f):
                    sy[f] = pid_of(sy[f], at)
            if isinstance(m.get("rt"), dict) and m["rt"].get("from"):
                m["rt"]["from"] = pid_of(m["rt"]["from"], at)
        reads = SESSION.get("_thread_reads") or {}
        new_reads = {}
        for pk, who in reads.items():
            parts = [pid_of(x) for x in str(pk).split("|")]
            nk = pair_of(*parts) if len(parts) == 2 else pk
            dst = new_reads.setdefault(nk, {})
            for w, ts in (who or {}).items():
                dst[_norm_name(pid_of(w))] = max(float(ts or 0), float(dst.get(_norm_name(pid_of(w))) or 0))
        if reads:
            SESSION["_thread_reads"] = new_reads
        for pl in SESSION.get("_mplans") or []:
            at = pl.get("created")
            pl["host"], pl["guest"] = pid_of(pl.get("host"), at), pid_of(pl.get("guest"), at)
            if pl.get("host") and pl.get("guest"):
                pl["pair"] = pair_of(pl["host"], pl["guest"])
            for f in ("responses", "sides", "live", "feedback"):
                if isinstance(pl.get(f), dict):
                    pl[f] = conv_keys(pl[f], at)
            for sd in (pl.get("sides") or {}).values():
                if isinstance(sd, dict) and sd.get("by"):
                    sd["by"] = pid_of(sd["by"], at)
            for f in ("address_by", "link_by", "cancelled_by"):
                if pl.get(f):
                    pl[f] = pid_of(pl[f], at)
            for f in ("pending", "last_change", "moved_to_call"):
                if isinstance(pl.get(f), dict) and pl[f].get("by"):
                    pl[f]["by"] = pid_of(pl[f]["by"], at)
            for ask in (pl.get("asks") or {}).values():
                if isinstance(ask, dict) and ask.get("by"):
                    ask["by"] = pid_of(ask["by"], at)
        bl = SESSION.get("_blocks") or {}
        if bl:
            nb = {}
            for k, lst in bl.items():
                dst = nb.setdefault(_norm_name(pid_of(k)), [])
                for x in lst or []:
                    v = _norm_name(pid_of(x))
                    if v not in dst:
                        dst.append(v)
            SESSION["_blocks"] = nb
        for r in SESSION.get("_reports") or []:
            r["by"], r["about"] = pid_of(r.get("by"), r.get("at")), pid_of(r.get("about"), r.get("at"))
        for g in SESSION.get("_gintents") or []:
            at = g.get("created")
            g["owner"] = pid_of(g.get("owner"), at)
            for mb in g.get("members") or []:
                mb["name"] = pid_of(mb.get("name"), at)
                if mb.get("removed_by"):
                    mb["removed_by"] = pid_of(mb["removed_by"], at)
            if isinstance(g.get("pending_1to1"), dict):
                for f in ("by", "to"):
                    if g["pending_1to1"].get(f):
                        g["pending_1to1"][f] = pid_of(g["pending_1to1"][f], at)
        for i in SESSION.get("_ginvites") or []:
            at = i.get("created")
            i["frm"], i["to"] = pid_of(i.get("frm"), at), pid_of(i.get("to"), at)
        for m in SESSION.get("_gmsgs") or []:
            at = m.get("t")
            if m.get("frm"):
                m["frm"] = pid_of(m["frm"], at)
            if isinstance(m.get("r"), dict):
                m["r"] = {e: [_norm_name(pid_of(n, at)) for n in (lst or [])] for e, lst in m["r"].items()}
            sy = m.get("sys") if isinstance(m.get("sys"), dict) else None
            for f in ("who", "owner", "by", "heir"):
                if sy and isinstance(sy.get(f), str) and sy.get(f):
                    sy[f] = pid_of(sy[f], at)
            if isinstance(m.get("rt"), dict) and m["rt"].get("from"):
                m["rt"]["from"] = pid_of(m["rt"]["from"], at)
        for gp in SESSION.get("_gplans") or []:
            at = gp.get("created")
            for f in ("owner", "proposed_by", "cancelled_by", "fixed_by"):
                if gp.get(f):
                    gp[f] = pid_of(gp[f], at)
            if gp.get("feedback_members"):
                gp["feedback_members"] = conv_list(gp["feedback_members"], at)
            for f in ("responses", "live", "sides", "feedback"):
                if isinstance(gp.get(f), dict):
                    gp[f] = conv_keys(gp[f], at)
            if isinstance(gp.get("update"), dict) and gp["update"].get("by"):
                gp["update"]["by"] = pid_of(gp["update"]["by"], at)
        for v in SESSION.get("_gvotes") or []:
            at = v.get("opened") or v.get("created")
            if v.get("by"):
                v["by"] = pid_of(v["by"], at)
            if isinstance(v.get("votes"), dict):
                v["votes"] = {pid_of(k, at): x for k, x in v["votes"].items()}
        for r in SESSION.get("_gremovals") or []:
            r["who"], r["by"] = pid_of(r.get("who"), r.get("t")), pid_of(r.get("by"), r.get("t"))
        for g in SESSION.get("_groups") or []:
            at = g.get("created")
            if g.get("host"):
                g["host"] = pid_of(g["host"], at)
            if isinstance(g.get("members"), list):
                g["members"] = conv_list(g["members"], at)
        # Личные сессии (оценки, чёрные списки, сохранённые поиски) — ключ верхнего уровня был именем.
        for k in [k for k in list(SESSION.keys()) if not str(k).startswith("_") and k != "me"]:
            if _is_pid(k):
                continue
            pid = pid_of(k)
            if not _is_pid(pid):
                continue
            src = SESSION.pop(k)
            dst = SESSION.setdefault(pid, {})
            for f, v in (src or {}).items():
                if f == "blocked":
                    dst.setdefault("blocked", [])
                    for x in v or []:
                        x2 = pid_of(x)
                        if x2 not in dst["blocked"]:
                            dst["blocked"].append(x2)
                elif f not in dst:
                    dst[f] = v
            backup.setdefault("_sessions", {})[k] = src
        report = {"resolved": rep["resolved"], "guessed": rep["guessed"],
                  "unresolved": dict(unresolved.most_common(50)), "guesses": guessed[:200]}
        if not apply:
            for k, v in backup.items():
                if k == "_sessions":
                    for sk, sv in v.items():
                        SESSION[sk] = sv
                else:
                    SESSION[k] = v
            return dict(report, applied=False)
        SESSION["_premig_v2"] = backup
        SESSION["_identity"] = {"v": IDENTITY_V, "at": time.time(), "report": report}
    _save_store()
    print("[identity] хранилище переведено на id: %s" % json.dumps(
        {k: report[k] for k in ("resolved", "guessed")}, ensure_ascii=False), flush=True)
    if report["unresolved"]:
        print("[identity] не разрешено (остались именами): %s"
              % json.dumps(report["unresolved"], ensure_ascii=False)[:600], flush=True)
    for gsz in guessed[:50]:
        print("[identity] тёзки, выбран по ближайшему входу: %s" % json.dumps(gsz, ensure_ascii=False),
              flush=True)
    return dict(report, applied=True)


def _account_created(owner_key):
    try:
        return float(((kleal_auth._accounts() or {}).get(owner_key) or {}).get("created") or 0)
    except Exception:
        return 0.0


def _legacy_pid(name, at=None):
    """Чей это СТАРЫЙ ключ-имя — для разовой привязки записей, сделанных до id.

    Правило одно на все хранилища: среди строк с этим именем берём тех, кто мог сделать запись, —
    строки без владельца (боты) и аккаунты, существовавшие к моменту записи (аккаунт не может
    владеть тем, что сделано до его рождения — ровно так новый «Иван» получил интенты прежних).
    Ровно один такой — запись его. Иначе — пусто:
    запись остаётся без хозяина (её не видит никто), а не уходит не тому. Такие случаи разбирает
    tools/identity_repair.py.
    """
    nm = _norm_name(name)
    if not nm:
        return ""
    if nm.startswith(ANON):
        return nm
    rows = _people_index()["by_name"].get(nm) or []
    if not rows:
        _remember(ANON + nm, str(name).strip())
        return ANON + nm            # человека нет в пуле: тест или удалённый — запись не чья-то чужая

    def existed(r):
        key = str(r.get("owner") or "")
        if not key or not at:
            return True
        born = _account_created(key)
        return not (born and float(at) + 60 < born)

    alive = [r for r in rows if existed(r)]
    return str(alive[0].get("id") or "") if len(alive) == 1 else ""


def _session(uid="me"):
    with _STORE_LOCK:
        u = SESSION.setdefault(str(uid or "me"), {})
        u.setdefault("feedback", {})   # {candidateName: 'accepted' | 'rejected'} — owner's past decisions
        u.setdefault("blocked", [])    # names the owner blocked
        u.setdefault("state", None)    # mirrored client UI state (server persistence)
        u.setdefault("saved_searches", [])   # §12.2 step 7: [{id, intent, created_at, status}]
        return u

# ---- §12.2 step 7: saved search + notify-later. Lives in SESSION / kleal_store.json (gitignored) — NEVER a
# users.json writer. 'Notify later' is a persist + on-demand /check pull-hook (real async push is separate infra).
def _save_search(intent, uid="me"):
    u = _session(uid)
    sid = "ss_" + hashlib.sha1(("%s|%s" % (uid, json.dumps(intent, sort_keys=True, default=str))).encode("utf-8")).hexdigest()[:12]
    if not any(s.get("id") == sid for s in u["saved_searches"]):
        u["saved_searches"].append({"id": sid, "intent": intent, "created_at": kc._iso(time.time()), "status": "watching"})
        _save_store()
    return sid

def _list_saved_searches(uid="me"):
    return list(_session(uid).get("saved_searches") or [])

def _delete_saved_search(sid, uid="me"):
    u = _session(uid)
    n = len(u["saved_searches"])
    u["saved_searches"] = [s for s in u["saved_searches"] if s.get("id") != sid]
    if len(u["saved_searches"]) != n:
        _save_store()
    return n != len(u["saved_searches"])

def _check_saved_searches(prof=None, uid="me"):
    """Re-run each saved search READ-ONLY over the CURRENT hard-gate pool (block/pause/age/consent since save
    are honored, never relaxed); mark 'ready' only when a REAL (non-fallback) direct match now exists."""
    u = _session(uid)
    out = []
    for s in u.get("saved_searches") or []:
        try:
            cands = match_candidates(dict(s.get("intent") or {}), prof or {}, {"uid": uid})
            real = [c for c in cands if not c.get("fallback")]
            s["status"] = "ready" if real else "watching"
            out.append({"id": s["id"], "status": s["status"], "matches": len(real), "created_at": s.get("created_at")})
        except Exception as e:
            out.append({"id": s.get("id"), "status": "error", "error": str(e)[:120]})
    _save_store()
    return out
# ---- proposal fatigue log (receiving policy budgets, spec §4.4/§10.1) ----
# Counts proposals RECEIVED per person; lives in matching's own kleal_store.json (no new writer
# on users.json). Feeds readiness ('busy' when over max_proposals_received_per_user_24h).
def _log_proposal(name):
    key = str(name or "").strip().lower()
    if not key:
        return
    now = time.time()
    with _STORE_LOCK:
        log = SESSION.setdefault("_proposals", {})
        log[key] = [t for t in (log.get(key) or []) if now - t < 7 * 86400] + [now]
    _save_store()

def _proposals_received_24h():
    now = time.time()
    log = SESSION.get("_proposals") or {}
    return {k: sum(1 for t in (v or []) if now - t < 86400) for k, v in log.items()}

# ---- §11 allocation: per-name IMPRESSION log (like _proposals; gitignored kleal_store.json, no users.json writer)
def _log_exposure(name):
    key = str(name or "").strip().lower()
    if not key:
        return
    now = time.time()
    with _STORE_LOCK:
        log = SESSION.setdefault("_exposure", {})
        log[key] = [t for t in (log.get(key) or []) if now - t < 7 * 86400] + [now]
    _save_store()

def _exposures_in_window(window_s):
    now = time.time()
    log = SESSION.get("_exposure") or {}
    return {k: sum(1 for t in (v or []) if now - t < window_s) for k, v in log.items()}

def _responsive_counts():
    """§11.1 'most-responsive' signal = accepted+completed outcomes per name. Used DEMOTE-ONLY (never a
    ranking boost — a boost would be the reputation-score-fed-to-ranking §11 forbids)."""
    r = {}
    for e in (SESSION.get("_outcomes") or []):
        if e.get("stage") in ("accepted", "completed"):
            r[e.get("name")] = r.get(e.get("name"), 0) + 1
    return r

def _idempotent(idem_key, entity, ent_id, action, producer):
    """§23.2.13 — memoize a write's response by an idempotency key so a replay returns the prior result
    (error_code DUPLICATE) WITHOUT re-applying its side effects. A falsy key runs the producer unchanged."""
    if not idem_key:
        return producer()
    key = ks.dedup_key(entity, ent_id, action, extra=idem_key)
    with _STORE_LOCK:
        prior = (SESSION.get("_write_seen") or {}).get(key)
    if prior is not None:
        return dict(prior, duplicate=True, error_code="DUPLICATE")
    res = producer()
    with _STORE_LOCK:
        SESSION.setdefault("_write_seen", {})[key] = res
        _save_store()
    return res

def record_feedback(name, decision, uid="me", purpose=None):
    """§17.2 isolation: an optional `purpose` scopes the feedback key to a mode (e.g. 'dating') so a decline in
    one mode never bleeds into another's ranking/edge. purpose=None keeps the bare-name key (byte-identical to
    the legacy domain-agnostic behavior)."""
    d = str(decision or "").lower()
    if not d.startswith(("accept", "reject")): return False
    u = _session(uid)
    key = "%s::%s" % (name, purpose) if purpose else str(name)
    u["feedback"][key] = "accepted" if d.startswith("accept") else "rejected"
    _save_store(); return True

# ---- success invariant (spec §1 / §2 terms) -------------------------------------------------------
# Success = a COMPLETED interaction with two-sided confirmation — NOT a click or an impression, and NOT
# a single probability. Silence is neutral, never negative: 'expired_no_response' is its own stage and is
# never fed to the ranking-lowering feedback loop. A 'match' exists only after a mutual accept that passed
# the send-boundary revalidation (§8.2). Lives in matching's own kleal_store.json (no new users.json writer).
_OUTCOME_STAGES = ("proposed", "accepted", "declined", "completed", "expired_no_response")
def _record_outcome(name, stage, uid="me"):
    st = str(stage or "").strip().lower()
    key = str(name or "").strip().lower()
    if st not in _OUTCOME_STAGES or not key:
        return False
    now = time.time()
    with _STORE_LOCK:
        SESSION.setdefault("_outcomes", []).append({"name": key, "stage": st, "ts": now, "uid": str(uid or "me")})
        if st in ("accepted", "completed"):                 # mutual accept forms a match; complete = success
            m = SESSION.setdefault("_matches", {}).setdefault(key, {"name": key, "matched_ts": None, "completed_ts": None})
            if st == "accepted" and not m["matched_ts"]:  m["matched_ts"] = now
            if st == "completed":                          m["completed_ts"] = now
    _save_store()
    return True

_MATCH_STATUS_STATE = {"completed": "COMPLETED", "active": "MUTUAL", "expired": "CANCELLED"}
def _match_capsules(uid="me"):
    """§4.9 Match Capsules materialised from SESSION['_matches'] (mutual accept after revalidation). An
    ADDITIVE list on the outcome routes — the int `matches` metric below is left untouched (COMPAT-1)."""
    out = []
    for key, rec in (SESSION.get("_matches") or {}).items():
        cap = kc.build_match(rec, [uid, key], "pilot")
        cap["state"] = _MATCH_STATUS_STATE.get(cap.get("status"), ks.initial_state("match"))  # §14.1 lifecycle state
        out.append(cap)
    return out

def _success_metrics():
    """§1 success model, computed over the outcome log. 'silence_is_negative' is False by construction:
    expired_no_response is counted but never treated as a rejection."""
    log = SESSION.get("_outcomes") or []
    stages = {s: 0 for s in _OUTCOME_STAGES}
    for e in log:
        stages[e.get("stage")] = stages.get(e.get("stage"), 0) + 1
    matches = SESSION.get("_matches") or {}
    return {"stages": stages, "matches": len(matches),
            "completed_interactions": sum(1 for m in matches.values() if m.get("completed_ts")),
            "silence_is_negative": False,
            "note": "success = completed interaction + two-sided accept; expired_no_response is neutral, "
                    "only explicit 'declined' is negative"}

def _offset(latlon, km, bearing_deg):
    br = math.radians(bearing_deg)
    dlat = (km * math.cos(br)) / 110.574
    dlon = (km * math.sin(br)) / (111.320 * math.cos(math.radians(latlon[0])))
    return (round(latlon[0] + dlat, 5), round(latlon[1] + dlon, 5))
def _tiebreak(name):    # deterministic 0.0..0.9 nudge from the id hash (NOT randomness) — stable ordering
    return (int(hashlib.sha1(str(name).encode("utf-8")).hexdigest()[:6], 16) % 10) / 10.0

# named communities/venues per interest -> drives "entity affinity" (shared club/game/scene)
ENTITY_MAP = {'dota':'Dota 2 ladder','valorant':'Valorant scrims','cs':'CS ranked queue','chess':'Casa del Chess club',
    'football':'Sunday football league','basketball':'Poblenou basketball run','tennis':'Padel & tennis club',
    'coffee':'Third-wave coffee crowd','startups':'Startup Grind BCN','startup':'Startup Grind BCN',
    'running':'Morning running crew','cinema':'Arthouse film club','books':'Gràcia book club',
    'music':'Live gigs scene','rave':'Warehouse techno crew','hiking':'Weekend hiking group','art':'MACBA art walks',
    'photography':'Street photo collective','climbing':'Boulder gym crew','ai':'ML paper reading group'}

# Demo pool of 50 users (stands in for the real user DB). Deterministic -> reproducible matching + tests.
def _gen_pool():
    NAMES = ("Marc Ana Dima Sofia Leo Nina Tom Yuki Pablo Lena Ivan Marta Sam Elena Hugo Kira Noah Vera Max Lucia "
             "Oleg Sara Ben Mira Jon Alba Rus Cleo Ravi Tanya Nico Iris Omar Zoe Karl Maya Erik Nadia Luca Petra "
             "Adam Rosa Timur Gaia Feliks Anya Diego Sana Bruno Yara").split()
    SETS = [
        ["coffee","ai","startups"], ["spanish","coffee","language"], ["dota","valorant","gaming"],
        ["football","running","gym"], ["architecture","urbanism","cinema"], ["startups","networking","ai"],
        ["hiking","outdoor","travel"], ["cinema","art","music"], ["boxing","gym","running"],
        ["tennis","coffee","walk"], ["chess","board","coffee"], ["guitar","music","concert"],
        ["french","language","coffee"], ["cs","valorant","gaming"], ["museum","art","books"],
        ["yoga","walk","coffee"], ["cycling","outdoor","running"], ["poker","games","drinks"],
        ["product","design","startups"], ["dinner","drinks","talk"], ["basketball","gym","running"],
        ["photography","art","walk"], ["climbing","outdoor","hiking"], ["ml","ai","networking"],
        ["swimming","running","gym"], ["theatre","cinema","art"], ["german","language","books"],
        ["dj","music","rave"], ["startup","product","coffee"], ["urbanism","architecture","walk"],
        ["dota","gaming","chess"], ["coffee","books","cinema"], ["running","cycling","outdoor"],
    ]
    VIBES = ["calm","energetic","intellectual","creative","competitive","chill","social","introvert","extrovert"]
    LANGS = [["en"],["en","es"],["en","ru"],["es","en"],["ru","en"],["en","fr"],["es"],["en","de"],["fr","en"]]
    ROLES = ["play","watch","discuss","practise","attend"]
    DEALS = [[], ["no smokers"], ["no late nights"], [], ["no bars"], []]
    typ_of = {'sports':'sport','games':'gaming','tech':'networking','learning':'language',
              'music':'social','culture':'social','social':'social','outdoors':'sport'}
    pool = []
    for i, nm in enumerate(NAMES):
        interests = SETS[i % len(SETS)]
        km = round(0.4 + (i * 0.53) % 7.6, 1)
        lat, lon = _offset(ME_LATLON, km, (i * 137.5) % 360)     # spread on a golden-angle spiral
        km = _haversine(ME_LATLON, (lat, lon))                   # true great-circle distance
        # ~1/3 of people carry their OWN active intent -> enables reciprocal (T0) matching
        own = None
        if i % 3 == 1:
            broad = cat_of(interests[0])[0]
            own = {"type": typ_of.get(broad, 'social'), "topics": interests[:2], "role": ROLES[i % len(ROLES)]}
        ents = [ENTITY_MAP[w] for w in interests if w in ENTITY_MAP] or [interests[0].capitalize() + " scene"]
        pool.append({
            "name": nm, "interests": interests, "vibe": VIBES[i % len(VIBES)],
            "langs": LANGS[i % len(LANGS)], "lat": lat, "lon": lon, "km": km,
            "open": (i % 5 != 4), "role": ROLES[i % len(ROLES)], "datingOk": (i % 3 == 0),
            "age": (17 if i % 13 == 0 else 24 + (i * 7) % 22),   # a few minors to exercise the 18+ gate
            "verified": (i % 4 != 0),                            # ~75% verified
            "paused": (i % 11 == 0),                             # on a break -> hard-gated out
            "pending": (i * 3) % 9,                              # open proposals -> overload gate at >=6
            "blocksMe": (i % 17 == 0),                           # two-sided block-list
            "lastActiveDays": i % 6, "declinedOwnerDaysAgo": (2 if i % 23 == 0 else None),
            "intents": ([own] if own else []), "entities": ents, "dealBreakers": DEALS[i % len(DEALS)],
        })
    return pool
CANDIDATES = _gen_pool()

# The candidate pool = real users registered by onboarding, MERGED with the built-in demo pool for depth.
# IMPORTANT (was a silent, total break): onboarding writes the shared store at the repo-root users.json
# (KLEAL_USERS=/root/kleal-ms/users.json), but this file previously defaulted to services/matching/users.json
# — a different file onboarding never touched — so every registered person was invisible to the matcher and
# search ran on the 50 demo fakes only. Default now points at the SAME repo-root users.json onboarding uses.
USERS_PATH = os.environ.get(
    "KLEAL_USERS",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "users.json"))
# Match ONLY real registered users by default — surfacing demo-pool fakes (Ana/Nico/Iris...) in results
# reads as "mock users". The demo pool is still the fallback when the store is missing/empty, so a fresh
# system isn't dead. Set KLEAL_MERGE_DEMO=1 to blend the demo pool in (for a populated demo).
MERGE_DEMO = os.environ.get("KLEAL_MERGE_DEMO", "0") != "0"
# Off by default: no fabricated people, ever, unless a demo explicitly asks for them.
DEMO_FALLBACK = os.environ.get("KLEAL_DEMO_FALLBACK", "0") != "0"
_users_cache = {"mtime": None, "list": None}
def _langs_of(prof):
    """Языки человека — из ЛЮБОЙ из двух форм, которыми их присылают.

    Профиль хранит `languages` объектом: {"comfortable": [...], "native": ...}. Часть экранов
    приложения, собирая профиль под поиск, отдаёт сразу список — и на этом ранжирование падало
    с «'list' object has no attribute 'get'», а человек читал ответ как «никого не нашлось».
    Экраны поправлены, но терпимость остаётся здесь: цена ошибки в форме одного поля не должна
    быть «поиск не работает вообще», а следующий, кто соберёт профиль иначе, узнает об этом
    не от пользователя.

    Пустая строка и None отбрасываются: пустой язык — это не язык, а дырка в анкете."""
    langs = (prof or {}).get('languages')
    if isinstance(langs, dict):
        langs = langs.get('comfortable') or langs.get('speaks') or []
    if isinstance(langs, str):
        langs = [langs]
    if not isinstance(langs, (list, tuple, set)):
        return []
    return [l for l in langs if l]


# Тест характера -> настрой, которым оперирует ранжировщик. ПРАВИЛО ЖИВЁТ В shared/vibe.py:
# его читает и онбординг, чтобы экран «Твоя личность» показывал человеку тот же настрой, каким
# его видит подбор, и чтобы правку можно было принять обратно. Здесь остаётся только дописывание.
def _fill_vibe(rows):
    """Дописать `vibe` тем, у кого его нет, из пройденного теста. Строки копируются: пул кэшируется
    и делится между запросами."""
    out, filled = [], 0
    for r in rows:
        if isinstance(r, dict) and not str(r.get("vibe") or "").strip():
            v = kvibe.from_persona(r)
            if v:
                out.append(dict(r, vibe=v))
                filled += 1
                continue
        out.append(r)
    if filled:
        print("[pool] настрой выведен из теста характера: %d строк" % filled, flush=True)
    return out


def _modes_asked():
    """Кто какие форматы встречи уже выбирал — по его собственным интентам и заявкам.

    ЗАЧЕМ. Признак mode_format сверяет запрошенный режим с полем `formats` кандидата, и пустое поле
    даёт «неизвестно». А «неизвестно» здесь не воздержание: оценка считается как среднее минус
    штраф за непокрытие, поэтому каждый незаполненный признак ТЯНЕТ БАЛЛ ВНИЗ. На боевых данных
    `formats` заполнен у двух живых людей из двадцати одного и у шестисот синтетических из шестисот
    — то есть живые систематически проигрывали тестовым строкам по полю, которого у них нет.

    Спрашивать заново нечего: формат человек выбирает руками на шаге после создания интента, и этот
    выбор уже лежит в хранилище. Четырнадцать живых людей из двадцати одного успели его сделать —
    кто-то семь раз офлайн, кто-то в основном онлайн. Берём то, что он делал, а не то, что о себе
    заявил бы в анкете.
    """
    out = {}
    for box in ("_intents", "_requests"):
        for r in (SESSION.get(box) or []):
            if not isinstance(r, dict):
                continue
            it = r.get("intent") if isinstance(r.get("intent"), dict) else r
            m = str(it.get("mode") or "").strip().lower()
            # Кто выбирал — по ID (docs/IDENTITY.md): у интента это `owner_id`, у заявки `from`
            # (после перевода 26.09 там id). По имени тёзки делили бы выбор друг друга.
            who = str((r.get("owner_id") if box == "_intents" else r.get("from")) or "").strip().lower()
            if who and m in ("offline", "online", "hybrid"):
                out.setdefault(who, set()).add(m)
    return out


_FMT_SAID = {"n": None}


def _fill_formats(rows):
    """Дописать `formats` тем, у кого его нет, из уже сделанного выбора. Строки КОПИРУЮТСЯ:
    пул кэшируется и делится между запросами, а править общий список — значит отдать свою правку
    следующему."""
    seen = _modes_asked()
    if not seen:
        return rows
    out, filled = [], 0
    for r in rows:
        if isinstance(r, dict) and not (r.get("formats") or []):
            m = seen.get(str(r.get("id") or "").strip().lower())
            if m:
                out.append(dict(r, formats=sorted(m)))
                filled += 1
                continue
        out.append(r)
    if filled and filled != _FMT_SAID.get("n"):
        print("[pool] формат выведен из выбранного: %d строк" % filled, flush=True)
    _FMT_SAID["n"] = filled
    return out


def _load_pool_rows():
    """Сырой пул из базы (или файла): ОДИН и тот же список, пока пул не сменился; None, если пусто."""
    store = None
    if db.ENABLED:
        # Из базы. Отпечаток вместо mtime файла: перечитываем пул, только если кто-то
        # зарегистрировался или поправил профиль, — на каждый поиск ходить за 714 строками незачем.
        try:
            v = db.users_version()
            if _users_cache.get("ver") != v:
                rows = db.load_users()
                if rows:
                    _users_cache["ver"] = v
                    _users_cache["list"] = rows
            if _users_cache.get("list"):
                store = _users_cache["list"]
        except Exception as e:
            print("[pool] postgres недоступен, читаю файл: %s: %s" % (type(e).__name__, str(e)[:120]))
    if store is None:
        try:
            m = os.path.getmtime(USERS_PATH)
            if _users_cache["mtime"] != m:
                with open(USERS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                lst = data.get("users") if isinstance(data, dict) else data
                _users_cache["mtime"] = m
                _users_cache["list"] = lst if isinstance(lst, list) else None
            store = _users_cache["list"]
        except Exception:
            store = None
    return store or None


_VIBE_MEMO = {"src": None, "out": None}


def load_candidates():
    store = _load_pool_rows()
    if not store:
        # No real people in the store. The demo pool used to stand in here so a fresh system would
        # not look dead — but the stand-ins ARE what a user reads as "mock users", and after the
        # store was emptied the app still answered every search with Ana/Nico/Iris. Product call:
        # an empty pool must return an empty pool, and buddy already has an honest "nobody yet"
        # reply for exactly that. The fallback is kept one env var away for demos and for the
        # matching owner's own testing: KLEAL_DEMO_FALLBACK=1 restores the old behaviour.
        return CANDIDATES if DEMO_FALLBACK else []
    # Настрой зависит только от строк — выводим его раз на версию пула, а не на каждый вызов
    # (было: 600 строк заново и строка в журнал на каждый поиск). Формат зависит от свежих
    # интентов и заявок — его по-прежнему дописываем каждый раз.
    if _VIBE_MEMO["src"] is not store:
        _VIBE_MEMO.update(src=store, out=_fill_vibe(store))
    store = _fill_formats(_VIBE_MEMO["out"])
    # Only the explicitly enrolled KYC canary is filtered; preserve other rows.
    import age_rollout
    store = age_rollout.filter_candidates(store)
    if not MERGE_DEMO:
        return store                               # opt-out: store authoritative (original behaviour)
    seen = {str(u.get("name", "")).strip().lower() for u in store}
    return list(store) + [c for c in CANDIDATES if str(c.get("name", "")).strip().lower() not in seen]

# ---------------- Matching Core v2 (spec-faithful engine; core_v2.py + ../../config/*.yaml) ----------------
# Scoring per "Kleal_Matching_Core_Final_Spec_RU_v2": feature groups with unknown/coverage, R_lcb,
# tier-as-provenance, user-facing bands. Weights/thresholds live ONLY in the sha-pinned YAML.
# Engine select (full replacement path): KLEAL_ENGINE=matching_core (default) loads the clean-rebuild
# package `matching_core/` via the drop-in adapter; KLEAL_ENGINE=core_v2 restores Dev B's engine instantly.
# Rollback for Dev A/B: KLEAL_CORE_V2=0 -> the legacy scorer below runs unchanged. A missing or
# tampered config also falls back automatically (fail-safe, spec §21.4) — see /api/agent/weights.
_ENGINE = os.environ.get("KLEAL_ENGINE", "matching_core").strip().lower()
if _ENGINE == "core_v2":
    import core_v2 as _core
else:
    try:
        import matching_core_engine as _core          # full replacement: matching_core is the engine
    except Exception as _ee:
        import core_v2 as _core                        # safety net if the package is missing/broken
        _ENGINE = "core_v2(fallback:%s)" % type(_ee).__name__
_CORE_CFG, _CORE_ERR = None, None
try:
    _CORE_CFG = _core.load_config(os.environ.get(
        "KLEAL_CORE_CONFIG",
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                     "config", "Kleal_Matching_Core_Config_v2.yaml")))
except Exception as _e:
    _CORE_ERR = str(_e)
CORE_V2 = os.environ.get("KLEAL_CORE_V2", "1") != "0" and _CORE_CFG is not None
# §15: report (NON-raising) any group_formation config-block drift at load time. We deliberately do NOT call the
# raising kg.load_group_params here — a bad group block must never crash live matching (it would perturb the
# person-to-person slate). The gated /api/agent/group endpoint calls load_group_params in a try/except -> dormant.
_GROUP_CFG_PROBLEMS = kg.validate_group_config_block(_CORE_CFG) if _CORE_CFG else ["core config not loaded"]

def _relaxed_cfg():
    """A clone of the canonical config with every domain's DISCOVERY floor dropped to 0 — used only by
    the never-dead-end fallback pass (§12). Weights / λ / OUTREACH floors are untouched, so scoring and
    the outreach/consent gates are identical; only the 'show it in discovery' threshold is relaxed, so
    adjacent/broader-but-eligible people can surface instead of an empty result."""
    if _CORE_CFG is None:
        return None
    c = copy.deepcopy(_CORE_CFG)
    for dc in c.get("domains", {}).values():
        dc["discovery_min_lcb"] = 0.0
        dc["discovery_min_coverage"] = 0.0
    return c
_RELAXED_CFG = _relaxed_cfg()

# ---- §0 decision 10 / §11.3: payment MUST NOT touch relevance, eligibility, safety, or order ----------
# Structurally the engine feeds ZERO payment signal into scoring. This reads the config's stated invariant
# and makes it an ENFORCED, visible guarantee: if a future config ever flipped a payment boost on, matching
# surfaces ok=False (the caller/health can refuse) instead of silently honouring it. Reads the already-pinned
# `currency_or_paid_priority` key — no config edit, no sha change.
def _payment_invariant(cfg=None):
    flags = ((cfg or _CORE_CFG) or {}).get("currency_or_paid_priority") or {}
    boost = bool(flags.get("ranking_boost_allowed", False))
    safety = bool(flags.get("safety_priority_affected_by_payment", False))
    return {"ranking_boost_allowed": boost, "safety_priority_affected_by_payment": safety,
            "enforced": True, "ok": (not boost) and (not safety),
            "note": "subscription may change limits/tools, never relevance/eligibility/safety/order"}
PAYMENT_INVARIANT = _payment_invariant()

# ---- §1.2 pilot: only a subset of §1.1 decision types ships now; the rest are DECLARED but disabled ----
# (i.e. out-of-scope by design, not merely unbuilt). release_status comes from the pinned config; the
# decision-type surface is explicit so a caller asking for a non-pilot type gets a clear "not in this pilot"
# instead of a silent empty result. Group/event/room/continuation are the post-pilot layers (§14–§16).
RELEASE_STATUS = str((_CORE_CFG or {}).get("release_status") or "pilot_candidate")
PILOT_DECISION_TYPES = {
    "person_to_person": True,           # §1.1 — the live matching path
    "intent_to_intent": True,           # §1.1 — reciprocity join (live; full condition-merge is partial)
    "group_formation": False,           # §1.1 — post-pilot (§15)
    "intent_to_event": False,           # §1.1 — post-pilot (§16)
    "intent_to_room": False,            # §1.1 — post-pilot (§16)
    "intent_to_venue": False,           # §1.1 — post-pilot (§16); additive, declared-but-disabled (never flipped True)
    "relationship_continuation": False, # §1.1 — post-pilot (§14)
}
# ---- §15 group formation: the PRODUCT switch -----------------------------------------------------
# kleal_groups.py is deliberate conformance scaffolding: its payloads hard-code enabled:False and the
# algorithm only runs behind an exact, test-only override. That design stays — it is what keeps a
# post-pilot layer from activating itself. What was missing is a switch ABOVE it, so the feature can
# be turned on as a product without editing §15's semantics, and turned off again with one variable.
#
# Off, asking for a group was a silent zero: `groupSize` routes the intent to group_formation, the
# pilot gate rejected it, and /api/agent/match returned ZERO PEOPLE. The same query without that one
# field returned eight. Whatever the switch says, a group request must never cost you the people.
GROUPS_ENABLED = os.environ.get("KLEAL_GROUPS", "0") != "0"
_GROUP_OVERRIDE = {"enable_group_formation": True}   # the exact shape kg.is_override_enabled demands


# Spec §1 — the product's group floor, in TOTAL people including whoever is asking.
GROUP_MIN_TOTAL = 3


def _decision_type(intent):
    """Which §1.1 decision type an intent asks for. Explicit `decisionType` wins; otherwise inferred from
    group/event/room signals, defaulting to person_to_person (the pilot path)."""
    intent = intent or {}
    dt = str(intent.get("decisionType") or "").strip()
    if dt in PILOT_DECISION_TYPES:
        return dt
    # The floor is applied HERE because this is where the routing decision is made. The structured
    # /match entry never passes through ki.validate_and_normalize before this point — that runs later,
    # inside ranking — so a caller asking for a "group of 2" was routed to §15 and got a pair dressed
    # as a group, which is exactly the hidden-1:1 shape spec §1 forbids.
    try:
        _gs = int(intent.get("groupSize") or 0)
    except (TypeError, ValueError):
        _gs = 0
    if _gs >= GROUP_MIN_TOTAL or intent.get("group"): return "group_formation"
    if intent.get("eventId") or str(intent.get("type") or "") == "event": return "intent_to_event"
    if intent.get("roomId"):                                  return "intent_to_room"
    if intent.get("venueId") or str(intent.get("type") or "") == "venue": return "intent_to_venue"   # §16 (pilot-off)
    return "person_to_person"
if GROUPS_ENABLED:
    PILOT_DECISION_TYPES["group_formation"] = True    # §15 live: set at import, never per-request


def _pilot_enabled(intent):
    return bool(PILOT_DECISION_TYPES.get(_decision_type(intent), False))

def _data_version():
    """Fingerprint of the candidate store in effect (source + mtime + count). Part of the request snapshot
    so a result is interpretable against exactly the data that produced it (§4 immutable snapshot)."""
    lst = _users_cache.get("list")
    src, mt = ("store", _users_cache.get("mtime")) if isinstance(lst, list) else ("demo", None)
    n = len(lst) if isinstance(lst, list) else len(CANDIDATES)
    tag = "%s:%s:%d" % (src, ("%.0f" % mt) if mt else "0", n)
    return "data_" + hashlib.sha1(tag.encode("utf-8")).hexdigest()[:10]

def _intent_identity(intent):
    """§3 step1 / §4.3: a stable intent_id + version from the NORMALISED intent (deterministic, no clock),
    plus its domain, decision type and status — the identity block the spec attaches to a compiled intent."""
    intent = intent or {}
    core = {k: intent.get(k) for k in ("type", "topics", "mode", "format", "role", "radiusKm",
                                       "requiredLanguages", "minAge", "maxAge", "verifiedOnly")}
    h = hashlib.sha1(json.dumps(core, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()
    return {"intent_id": "int_" + h[:12], "version": h[:8], "status": "active",
            "domain": (_core.infer_domain(intent, cat_of) if CORE_V2 else None),
            "decision_type": _decision_type(intent)}

def _request_snapshot(intent):
    """§4 intro: an immutable per-request snapshot of every version in effect (intent/config/policy/data)
    plus the enforced payment invariant, so a result stays interpretable against its exact inputs."""
    ident = _intent_identity(intent)
    return {"intent_id": ident["intent_id"], "intent_version": ident["version"],
            "decision_type": ident["decision_type"], "pilot_enabled": _pilot_enabled(intent),
            "config_version": (_CORE_CFG or {}).get("config_version"),
            "config_sha": ((_CORE_CFG or {}).get("_sha256") or "")[:12],
            "release_status": RELEASE_STATUS, "policy_version": "policy-2.0.0",
            "data_version": _data_version(), "payment_invariant": PAYMENT_INVARIANT,
            "config_health": {"core_v2": CORE_V2, "error": _CORE_ERR,          # §21.4 SLA: config/taxonomy health
                              "group_drift": list(_GROUP_CFG_PROBLEMS or []), "degraded": bool(_CORE_ERR)}}

PARSE_PROMPT = '''You convert a user's free-text social request into a structured intent.
Return ONLY compact JSON (no prose, no markdown), keys:
 title  (3-5 word human label, e.g. "Coffee & urbanism chat"),
 type   (one of: dinner, sport, gaming, networking, dating, language, social, other),
 topics (array of 1-4 lowercase keywords, e.g. ["coffee","urbanism"]),
 role   (one of: play, watch, discuss, practise, attend, meet — infer from the verb; default "meet"),
 mode   (offline | online),
 format (short, e.g. "1:1 or small group"),
 time   (short, infer from text, default "Flexible"),
 place  (short, infer, default "Public places nearby"),
 groupSize (integer 2-8 = how many people in TOTAL should be at the meetup, the asker INCLUDED;
            null unless the user asks for a group/team/company or names a headcount),
 group  (true if they want several people rather than one, but gave no number; else null).
English only.'''

# Group headcount, read from the words people actually use. Until this existed, `groupSize` had no
# producer anywhere in the product: the screen that asks «Один на один / Малая группа / Компания»
# dropped the answer, and the parser had no such key, so §15 group formation was unreachable and
# every group request was silently served as one-person-at-a-time matching.
_GROUP_WORDS = ('групп', 'компани', 'команд', 'вместе', 'втро', 'вчетвер', 'впятер', 'вшестер',
                'group', 'team', 'crew', 'squad', 'together', 'grupo', 'equipo', 'juntos')
# «вдвоём» is deliberately absent: two people are a 1:1, not a small group.
_GROUP_NUM_WORDS = {'втроем': 3, 'втроём': 3, 'троем': 3, 'троём': 3,
                    'вчетвером': 4, 'впятером': 5, 'вшестером': 6}
# A headcount sits next to a people-word, in either order — Russian puts it on both sides
# («4 человека», «человека 4») and so does Spanish («4 personas», «somos 4»).
_PEOPLE_NUM = re.compile(
    r"(\d{1,2})\s*(?:чел\w*|людей|человек\w*|игрок\w*|people|persons?|players?|personas?|jugadores)"
    r"|(?:чел\w*|людей|человек\w*|people|persons?|personas?|somos|нас)\s*(\d{1,2})", re.U)
# A bare number is a headcount only in a sentence that already said "group" — and never when it is
# really a clock ("в 18:00", "at 7pm"), a distance or a price.
_BARE_NUM = re.compile(r"(?<![:\d.,])(\d{1,2})(?![:\d])"
                       r"(?!\s*(?:час|утра|вечера|дня|ночи|:|h\b|am\b|pm\b|мин|min|км|km|€|\$|%))", re.U)


def _parse_group_size(ql):
    """(groupSize, wants_a_group) from free text. The number is the TOTAL at the meetup, asker included."""
    wants = any(w in ql for w in _GROUP_WORDS)
    for w, n in _GROUP_NUM_WORDS.items():
        if w in ql:
            return n, True
    m = _PEOPLE_NUM.search(ql) or (_BARE_NUM.search(ql) if wants else None)
    if m:
        n = int(next(g for g in m.groups() if g))
        # Spec §1: a group is three people minimum, the asker included. «вдвоём» and «нас двое» are
        # one-on-one, so they must not route to group formation at all — a pair dressed as a group
        # is exactly the hidden-1:1 shape the spec forbids.
        if n == 2:
            return None, False
        if GROUP_MIN_TOTAL <= n <= 12:
            return n, True
    return None, wants

def _fallback_parse(q):
    ql = (q or '').lower()
    toks = [w for w in re.findall(r"[a-zA-Z]+", ql) if len(w) >= 3]
    resolved = []                                     # only taxonomy-recognised words survive
    for t in toks:
        if cat_of(t)[0] and _norm(t) not in resolved: resolved.append(_norm(t))
    resolved = resolved[:4]
    dating = any(w in ql for w in ('date','dating','romantic','relationship','single','flirt','love'))
    topics = resolved or (['dating'] if dating else (toks[:4] or ['social']))
    tm = 'Today evening' if ('today' in ql or 'evening' in ql or 'tonight' in ql) else \
         ('Tomorrow' if 'tomorrow' in ql else ('This weekend' if 'weekend' in ql else 'Flexible'))
    role = ('play' if any(w in ql for w in ('play','teammate','squad','sparring','match')) else
            'watch' if 'watch' in ql else
            'practise' if any(w in ql for w in ('practise','practice','learn','exchange')) else
            'discuss' if any(w in ql for w in ('discuss','talk','chat','conversation','about')) else
            'attend' if any(w in ql for w in ('event','attend','concert','festival')) else 'meet')
    broad = (cat_of(resolved[0])[0] if resolved else None)
    typ = 'dating' if dating else \
          {'sports':'sport','games':'gaming','tech':'networking','learning':'language'}.get(broad, 'social')
    title = ('Date' if dating else (topics[0].capitalize() + ' meetup')) if (dating or topics) else 'New plan'
    online = any(w in ql for w in ('online','remote','voice','video','call','stream'))
    gsize, gwant = _parse_group_size(ql)
    return {"title": title, "type": typ, "topics": topics or (['dating'] if dating else ['social']),
            "role": role, "mode": ('online' if online else 'offline'),
            "format": "1:1 or small group", "time": tm, "place": "Public places nearby",
            # §15 routing: a size, or — when they asked for company without naming a number — the bare
            # flag, which lets the domain pack / config decide how many seats a padel court has.
            "groupSize": gsize, "group": (True if (gwant and not gsize) else None),
            # gate parameters (owner's search scope) — sensible defaults; dating tightens age/verification
            "radiusKm": 15, "verifiedOnly": bool(dating), "minAge": (18 if dating else None), "maxAge": None,
            "requiredLanguages": [], "exactMatchRequired": False, "adjacentAllowed": True, "broadAllowed": True}

def parse_intent(q):
    """§5: the LLM is an untrusted PARSER. Both the LLM branch and the fallback pass through
    ki.validate_and_normalize (schema-complete the 16 keys, allowlist type/role/mode, clamp numerics,
    truncate language codes) before returning — so no un-validated LLM output ever drives matching."""
    q = (q or '').strip()
    if not q: return ki.validate_and_normalize(_fallback_parse(''))[0]
    try:
        cfg = MODEL_ID
        raw = llm_complete(cfg, [{"role": "system", "content": settings.prompt("matching.parse_intent", PARSE_PROMPT)},
                                  {"role": "user", "content": q}], 0.2)
        obj = base._extract_json(raw)
        if isinstance(obj, dict) and obj.get('topics'):
            fb = _fallback_parse(q)
            for k, v in fb.items(): obj.setdefault(k, v)
            if not isinstance(obj.get('topics'), list) or not obj['topics']: obj['topics'] = fb['topics']
            # setdefault cannot help when the model EMITS the key as null, which it does for
            # groupSize far more often than it reads «человека 4» correctly. A regex that found a
            # headcount beats a model that returned nothing; a model that found one still wins.
            for k in ('groupSize', 'group'):
                if not obj.get(k) and fb.get(k): obj[k] = fb[k]
            return ki.validate_and_normalize(obj, source='llm')[0]
    except Exception:
        pass
    return ki.validate_and_normalize(_fallback_parse(q))[0]

ROLE_CONFLICT = {('play', 'watch'), ('watch', 'play'), ('practise', 'watch')}
SOON_WORDS = ('today', 'tonight', 'evening', 'tomorrow')

# ---- §8 eligibility / safety / purpose-binding constants (all ADDITIVE; gates fire only on a PRESENT,
# restrictive value and default-ALLOW on absence, so field-less fixtures + the demo pool stay byte-identical).
_ACCOUNT_BLOCK = frozenset({'suspended', 'deactivated', 'banned', 'deleted'})   # §8.1 account_status (known-bad only)
_SAFETY_BLOCK = frozenset({'banned', 'csam_block', 'legal_hold', 'restricted'})  # §8.1 safety restrictions (closed set)
# §8.1 intent-mode isolation: purpose pairs that MUST NOT auto-cross (§8.3 dating is a separate contour).
# Deterministic purpose matrix (informed by the ontology's blocked_cross_purpose edges) — a candidate's
# purpose is read ONLY from its OWN active intents, never from datingOk/receiving/interests.
_TYPE_PURPOSE = {'dating': 'dating', 'networking': 'networking', 'language': 'language_exchange',
                 'gaming': 'games', 'sport': 'sport', 'social': 'friendship', 'dinner': 'friendship',
                 'event': 'friendship', 'other': 'friendship'}
_XPURPOSE_BLOCK = frozenset({frozenset(('dating', p)) for p in
                             ('friendship', 'networking', 'language_exchange', 'games', 'sport')})
_DEC_RANK = {'ALLOW': 0, 'REVIEW': 1, 'BLOCK': 2}
_REVAL_CHECKPOINTS = ('slate', 'send', 'profile_open', 'accept', 'shared_chat',
                      'reveal_place', 'reveal_contact', 'state_change')          # §8.2 #1..#7
_REVEAL_STAGE = {'reveal_place': 'full', 'reveal_contact': 'full', 'shared_chat': 'match_only'}
# §8.4: exact/home/work location must never be in the candidate payload — scrubbed from every returned card.
_PRECISE_LOCATION_KEYS = ('home', 'work', 'address', 'homeLat', 'homeLon', 'workLat', 'workLon',
                          'exact_lat', 'exact_lon', 'preciseLat', 'preciseLon', 'live_location')

def _cross_purpose_blocked(intent, c):
    """§8.1 intent-mode isolation, SHARED by retrieval (_policy_decision) and the send boundary
    (_negotiate_precheck) so a cross-purpose pair can't slip through /api/agent/negotiate. Resolves the
    candidate's purpose ONLY from its own active intents (c['intents']); returns False (ALLOW) when the
    candidate has no own-intent purpose — the common case — so the demo pool + fixtures stay byte-identical."""
    ip = _TYPE_PURPOSE.get(str((intent or {}).get('type') or '').lower())
    if not ip:
        return False
    for oi in (c.get('intents') or []):
        cp = _TYPE_PURPOSE.get(str((oi or {}).get('type') or '').lower())
        if cp and frozenset((ip, cp)) in _XPURPOSE_BLOCK:
            return True
    return False

# §18 per-domain hard slots — a critical value that, when BOTH sides declare it and they differ, is a hard
# exclusion (games server/platform, event ticket, networking industry). Absent-permissive by construction.
_DOMAIN_CRITICAL_SLOTS = ("server", "platform", "ticket", "industry")

def _latlon(d):
    try:
        la, lo = float((d or {}).get("lat")), float((d or {}).get("lon"))
    except (TypeError, ValueError, AttributeError):
        return None
    return None if (la == 0 and lo == 0) else (la, lo)


def _with_km(pool, prof, ctx=None):
    """Distance from the SEARCHER to each candidate, stamped BEFORE the gates run.

    The radius gate in _hard_gates reads c['km'], and for everyone in the real store that key simply
    did not exist: `km` is precomputed only on the synthetic demo pool (against a fixed city-centre
    constant), while for registered people distance is derived much later, inside the scorer, as a
    soft feature. So `intent.radiusKm` — a HARD gate on paper — never once fired for a real user.
    Asking for 3 km and asking for 40 returned the same eight people.

    Rows are copied, never mutated: load_candidates() hands back a cached list shared across requests,
    and stamping one searcher's distances onto it would hand them to the next.
    """
    me = _latlon(prof) or _latlon(ctx)
    if not me:
        return pool                                  # no coordinates for the searcher -> no distance
    out = []
    for c in pool:
        there = _latlon(c)
        # У КАНДИДАТА НЕТ КООРДИНАТ, А У ИЩУЩЕГО ЕСТЬ — ЭТО НЕ «РАССТОЯНИЕ НЕИЗВЕСТНО», А «МИМО».
        # Раньше такая строка уезжала дальше без отметки km, и гейт радиуса её пропускал: он
        # судит только тех, у кого расстояние посчитано. На боевых данных так проходили 203
        # машинные фикстуры, и человек, просивший три километра, получал их в выдаче. У всех
        # двадцати одного живого человека координаты есть, поэтому запрет никого из них не задел.
        out.append(dict(c, km=round(_haversine(me, there), 1)) if there else dict(c, km_unknown=True))
    return out


# Поля, которые движок читает у ИЩУЩЕГО — прямой ход (`build_features`) и обратный
# (`matching_core/orchestrator/pipeline.py:_reverse_features`, где профиль подставляется вместо
# карточки). Приложение шлёт в поиск только семь: имя, возраст, пол, город, широту, долготу, языки.
_PROF_OWN_FIELDS = ("vibe", "interests", "langs", "formats", "age", "role", "summary")


def _is_self(c, self_id="", self_name=""):
    """Эта карточка — сам ищущий? По id, если он известен (docs/IDENTITY.md); по подписи — только
    для старого пути без личности. По подписи тёзки исключали друг друга из выдачи навсегда."""
    if self_id:
        return str((c or {}).get("id") or "") == str(self_id)
    return bool(self_name) and str((c or {}).get("name", "")).strip().lower() == self_name


def _prof_with_own_row(prof, self_name, self_id=""):
    """Дополнить профиль ищущего его СОБСТВЕННОЙ карточкой из стора — только пустые поля.

    НАСТРОЯ В ЗАПРОСЕ НЕТ НИКОГДА. `vibe` у человека не хранится вовсе: сервер выводит его из
    теста характера, когда собирает карточки (`[pool] настрой выведен из теста характера`), и
    приложению взять его неоткуда. А признак «социальный контекст» (вес 0.15, самый различающий
    по замеру `tools/weights_probe.py`) сравнивает настрой ищущего с настроем кандидата — и без
    первого всегда отвечает unknown. Замер 15.09.2026 на боевом сторе, запрос «кофе»: без настроя
    восемь карточек с ОДНИМ баллом 84.3 на всех; с настроем — 97.4, 97.4, 97.1, 95.4, 83.5. То же
    с интересами: обратный ход подставляет профиль вместо карточки и видел пустого человека.

    Присланное клиентом ВСЕГДА сильнее: человек мог сменить район, язык или настрой прямо в
    мастере, и его слово важнее записи в базе. Поэтому заполняем только пустое."""
    if self_id:
        row = _person(self_id)             # своя карточка — по id; по имени нашёлся бы тёзка
    elif not self_name:
        return prof
    else:
        key = _norm_name(self_name)
        row = next((u for u in load_candidates() if _norm_name(u.get("name")) == key), None)
    if not row:
        return prof                      # ищущего нет в сторе (тестовый профиль, гость) — не выдумываем
    out = dict(prof or {})
    for k in _PROF_OWN_FIELDS:
        if not out.get(k) and row.get(k):
            out[k] = row[k]
    if not out.get("langs"):             # обратный ход читает `langs`, приложение шлёт `languages.comfortable`
        comf = (out.get("languages") or {}).get("comfortable") if isinstance(out.get("languages"), dict) else None
        if comf:
            out["langs"] = list(comf)
    return out


def _hard_gates(intent, c, gate_ctx):
    """Cheap, deterministic exclusions applied BEFORE scoring. Returns (ok, reason_if_blocked)."""
    if c.get('paused'):                                            return False, 'on a break'
    # `blocked_norm` holds BOTH directions and is case-insensitive: the exact-string check alone
    # missed «marta» vs «Marta», and the one-way check let the blocked person keep seeing you.
    _bn = gate_ctx.get('blocked_norm') or ()
    if (c['name'] in gate_ctx['blocked'] or c.get('blocksMe')
            or str(c.get('name', '')).strip().lower() in _bn
            or str(c.get('id', '')).strip().lower() in _bn):     # блокировки хранятся по id
        return False, 'blocked'
    d = c.get('declinedOwnerDaysAgo')
    if d is not None and d < COOLDOWN_DAYS:                        return False, 'recently declined (cooldown)'
    if (c.get('pending') or 0) >= MAX_PENDING:                     return False, 'too many open invites'
    # ЧИСЛО, А НЕ ТО, ЧТО ЛЕЖИТ В СТРОКЕ. Анкета принимает `age` любого вида, и одной строки «30»
    # хватало, чтобы сравнение ниже бросило TypeError внутри ворот. Ошибку ловил общий except
    # обработчика и отвечал `200 {candidates: []}` — то есть ОДНА кривая строка превращала поиск в
    # «никого не нашли» для ВСЕХ пользователей разом. `_num` для этого и написан (см. его строку
    # документации), просто здесь его забыли. Границы диапазона приходят прямо из тела запроса и
    # падали на том же месте — поэтому приводятся тоже.
    age = _num(c.get('age'))
    if age is not None and age < MIN_AGE:                          return False, 'under 18'
    if intent.get('type') == 'dating' and not c.get('datingOk'):  return False, 'not open to dating'
    if intent.get('verifiedOnly') and not c.get('verified'):      return False, 'not verified'
    mn, mx = _num(intent.get('minAge')), _num(intent.get('maxAge'))
    if mn or mx:
        if age is None:                                           return False, 'age unknown'
        if mn and age < mn:                                       return False, 'below age range'
        if mx and age > mx:                                       return False, 'above age range'
    # Gender. Onboarding has always collected it and tools/ has always written it, but NOTHING in
    # matching ever read the field — so the "Кто / Sex" selector was a control that changed nothing.
    # Gated exactly like age: absent from the intent means no filter at all, and `any` is an explicit
    # "do not filter" rather than a value to match against.
    want_g = str(intent.get('gender') or intent.get('sex') or '').strip().lower()
    if want_g and want_g not in ('any', 'any is fine', 'не важно', 'любой', 'all'):
        cand_g = str(c.get('gender') or '').strip().lower()
        if not cand_g:                                            return False, 'gender unknown'
        if cand_g != want_g:                                      return False, 'different gender'
    reql = {str(l)[:2].lower() for l in (intent.get('requiredLanguages') or [])}
    if reql and not reql.issubset({str(l)[:2].lower() for l in (c.get('langs') or [])}):
        return False, 'missing a required language'
    if intent.get('mode') == 'offline' and intent.get('radiusKm'):
        if c.get('km_unknown'):                                  return False, 'distance unknown'
    if intent.get('mode') == 'offline' and intent.get('radiusKm') and c.get('km') is not None:
        try:
            if float(c['km']) > float(intent['radiusKm']):       return False, 'outside the radius'
        except (TypeError, ValueError):
            pass
    # ---- §8.1 additional canonical gates (appended LAST so existing reason tuples are unchanged; each
    # fires ONLY on a present restrictive value, so absent-field fixtures stay byte-identical) ----
    st = str(c.get('accountStatus') or '').strip().lower()
    if st in _ACCOUNT_BLOCK or c.get('suspended') is True:        return False, 'account not active'   # §8.1 account_status
    vis = c.get('visibility') or (c.get('privacy') or {}).get('visibility')
    if vis == 'private':                                          return False, 'private profile'      # §8.1 privacy visibility
    sf = c.get('safetyFlags') or []
    if isinstance(sf, list) and any(f in _SAFETY_BLOCK for f in sf): return False, 'safety restriction' # §8.1 safety (hard)
    # ---- §18 per-domain critical slots (absent-permissive: fires ONLY when BOTH intent and candidate declare
    # the slot AND they differ, so no current person fixture is touched — byte-identical) ----
    for _slot in _DOMAIN_CRITICAL_SLOTS:
        iv, cv = intent.get(_slot), c.get(_slot)
        if iv and cv and str(iv).strip().lower() != str(cv).strip().lower():
            return False, 'domain slot mismatch: %s' % _slot
    mind = intent.get('minDurationMin')                            # §18.3 minimum meet duration
    cav = c.get('availableMinutes')
    if mind and isinstance(cav, (int, float)) and not isinstance(cav, bool) and cav < float(mind):
        return False, 'window shorter than requested duration'
    return True, None

def _policy_decision(intent, c, gate_ctx, cfg=None):
    """§0 output table / §3 step2: policy_decision is a TRI-state, not a boolean.
      BLOCK  — a hard eligibility/safety exclusion (never scored, never shown).
      REVIEW — discoverable, but NOT auto-proposable: it must clear a separate safety/legal track first.
               A dating domain whose config sets release_gate=separate_safety_legal_track and whose
               candidate is unverified lands here instead of a silent ALLOW (§0 dec.8 / §1.2 dating gate).
      ALLOW  — clear for scoring + personal outreach.
    Returns (decision, reason)."""
    ok, why = _hard_gates(intent, c, gate_ctx)
    if not ok:
        # §8.1: age⇒"BLOCK or REVIEW", location⇒"REVIEW or zone expansion". Opt-in ONLY (default absent ⇒
        # unchanged BLOCK, so the existing slate/counts are byte-identical); when the intent asks for softer
        # semantics these two become REVIEW (discoverable, non-proposable, held for a user answer / expansion).
        if (intent.get("soft_eligibility") or c.get("zoneOptIn")) and why in ("age unknown", "outside the radius"):
            return "REVIEW", why                                # §8.1 zone-expansion: a zone opt-in outside the radius is held for expansion, not hard-blocked
        return "BLOCK", why
    if _cross_purpose_blocked(intent, c):                       # §8.1 intent-mode isolation (shared with send)
        return "BLOCK", "cross-purpose isolation"
    if c.get("sensitivity") == "restricted" or "review" in (c.get("safetyFlags") or []):   # §8.1 safety (soft)
        return "REVIEW", "safety restriction: held for safety review"
    if CORE_V2:
        domain = _core.infer_domain(intent, cat_of)
        dom_cfg = ((cfg or _CORE_CFG) or {}).get("domains", {}).get(domain) or {}
        if dom_cfg.get("release_gate") and not c.get("verified"):
            return "REVIEW", "%s: separate safety/legal track required (unverified)" % domain
    return "ALLOW", None

def evaluate_policy(intent, c, gate_ctx=None):
    """§23.4.2 — a single typed policy-verdict facade that runs the existing gate stack IN ORDER (_hard_gates ->
    cross-purpose isolation -> _policy_decision -> disclosure clamp) and returns one object. It reproduces the
    per-gate ALLOW/BLOCK/REVIEW outcome byte-for-byte — it adds NO new behavior, only a unified surface."""
    gate_ctx = gate_ctx if gate_ctx is not None else _gate_ctx_and_self({})[0]
    ok, why = _hard_gates(intent, c, gate_ctx)
    decision, reason = _policy_decision(intent, c, gate_ctx)
    disc = _revalidate_disclosure(intent, c, "profile_open") if decision != "BLOCK" else None
    return {"decision": decision, "reason": reason, "eligible": ok, "gate_reason": why,
            "cross_purpose_blocked": _cross_purpose_blocked(intent, c),
            "disclosure": disc, "policy_version": "policy-2.0.0"}

def _allocation_action(card):
    """§0 output table: an explicit typed allocation_action per candidate, DERIVED from decisions already
    made (policy / readiness / tier / fallback) — never a new score. One of:
      review_required · propose · discovery_expanded · discovery_only."""
    if card.get("policy") == "REVIEW":     return "review_required"
    if card.get("can_outreach"):           return "propose"
    if card.get("fallback"):               return "discovery_expanded"
    return "discovery_only"

def _decision_class(card):
    """§9.6 read-only 5-way decision label, a strict sibling of _allocation_action. Derived ONLY from the
    engine's OWN already-stamped decisions {policy, tier, band, can_outreach, why_no_outreach} — it
    re-thresholds NOTHING (the spec's flat 0.72/0.58/0.45 are illustrative; the REAL per-domain floors live
    in the sha-pinned config and are already folded into can_outreach/band). Total function; every read via
    .get() default so a sparse slate card (no why_no_outreach) safely falls through. Never touches scoring."""
    policy = str(card.get("policy") or "ALLOW")
    tier = str(card.get("tier") or "")
    band = str(card.get("band") or "")
    can = bool(card.get("can_outreach"))
    why = str(card.get("why_no_outreach") or "")
    if policy == "REVIEW":                                 # held for the safety/legal track — never a probe
        return "no_personal_outreach"                      # §9.6 row 5 (before clarification — must-fix)
    if can:
        if tier in ("T0", "T1") and band == "especially_close":
            return "strong_personal_candidate"             # §9.6 row 1 (ALLOW & high lcb/cov & T0-T1)
        return "usable_personal_candidate"                 # §9.6 row 2 (ALLOW & proposable, incl. T2+consent)
    if "broad consent" in why:                             # T2-without-consent is NOT discovery (must-fix)
        return "no_personal_outreach"                      # §9.6 row 5 (no expansion consent)
    if tier in ("T3", "T4") or "discovery only" in why or "below outreach floor" in why:
        return "discovery_only"                            # §9.6 row 3 (T3-T4 / below outreach floor)
    if band == "needs_clarification":
        return "clarification"                             # §9.6 row 4 (a high-impact unknown could flip it)
    return "no_personal_outreach"                          # §9.6 row 5 (below thresholds / receiving disallows)

def _validate_math_config(cfg, feature_keys, policy_version="policy-2.0.0", engine_version=None, schema_allowlist=("1.0",)):
    """§9.5 config CI checks, READ-ONLY (never mutates cfg / never re-writes _sha256 — the sha pin holds).
    Adds the checks core_v2.load_config does NOT do at runtime — evidence_id uniqueness within feature groups,
    config↔model↔policy MAJOR-version compatibility, and user_facing_bands cut ranges — plus non-mutating
    echoes of load_config's weights-sum(1e-6)/feature-key/prior-range checks. Returns a health dict; never raises."""
    cfg = cfg or {}
    checks, errors = [], []
    def add(cid, ok, detail):
        checks.append({"id": cid, "ok": bool(ok), "detail": detail})
        if not ok:
            errors.append("%s: %s" % (cid, detail))
    import re as _re
    _major = lambda v: (lambda m: int(m.group(1)) if m else None)(_re.search(r"(\d+)\.(\d+)\.(\d+)", str(v or "")))
    ev_ids = [e.get("evidence_id") for g in (cfg.get("feature_groups") or {}).values()
              for e in ((g or {}).get("evidences") or []) if isinstance(e, dict) and e.get("evidence_id")]
    add("evidence_id_unique", len(ev_ids) == len(set(ev_ids)),
        ("%d ids, %d unique" % (len(ev_ids), len(set(ev_ids)))) if ev_ids else "0 evidence ids in registry (guard active)")
    cvM, pvM = _major(cfg.get("config_version")), _major(policy_version)
    evM = _major(engine_version) if engine_version else cvM
    add("version_compat", cvM is not None and cvM == pvM and cvM == evM,
        "config=%s policy=%s engine=%s (majors %s/%s/%s)" % (cfg.get("config_version"), policy_version, engine_version, cvM, pvM, evM))
    add("schema_version_allowed", str(cfg.get("schema_version") or "") in schema_allowlist,
        "schema_version=%r allow=%s" % (cfg.get("schema_version"), list(schema_allowlist)))
    bad_band = [("%s.%s=%r" % (n, k, (b or {}).get(k))) for n, b in (cfg.get("user_facing_bands") or {}).items()
                for k in ("min_lcb", "min_coverage", "max_coverage")
                if k in (b or {}) and not (isinstance(b[k], (int, float)) and 0.0 <= b[k] <= 1.0)]
    add("band_cut_ranges", not bad_band, "all in [0,1]" if not bad_band else "out of range: %s" % bad_band)
    bad_w = []
    for d, dc in (cfg.get("domains") or {}).items():
        w = (dc or {}).get("weights") or {}
        if set(w) - set(feature_keys):
            bad_w.append("%s unknown keys %s" % (d, sorted(set(w) - set(feature_keys))))
        if abs(sum(float(w.get(k, 0) or 0) for k in feature_keys) - 1.0) > 1e-6:
            bad_w.append("%s weights sum != 1.0" % d)
    add("weights_sum_and_keys", not bad_w, "all domains sum to 1.0, no unknown keys" if not bad_w else "; ".join(bad_w))
    add("prior_ranges", all(isinstance((g or {}).get("unknown_prior"), (int, float)) and 0.0 <= (g or {}).get("unknown_prior", -1) <= 1.0
                            for g in (cfg.get("feature_groups") or {}).values()), "all unknown_prior in [0,1]")
    return {"ok": not errors, "config_version": cfg.get("config_version"), "schema_version": cfg.get("schema_version"),
            "config_sha": (cfg.get("_sha256") or "")[:12], "policy_version": policy_version,
            "checks": checks, "errors": errors}

GENERIC_TYPES = {'social', 'other', ''}   # too broad to count as a mutual-intent match on their own

def _reciprocal(intent, c):
    """True only if the candidate's OWN active intent shares a real topical interest (sub-category or exact).
    A bare TYPE match (both 'sport', both 'gaming'…) is NOT enough — 'sport/football' must not read as a
    mutual match for a 'sport/tennis' search, which used to hand football players the top T0 slot."""
    itop = [str(t).lower() for t in (intent.get('topics') or [])]
    for oi in (c.get('intents') or []):
        b, _ = topical(itop, [str(t).lower() for t in (oi.get('topics') or [])])
        if b >= 3:                                 # same sub-category or exact -> genuine mutual interest
            return True
    return False

def _base_tier(intent, c, topics, dating):
    """Strongest topical/intent signal -> (kind, base_score, matched_interests, reason)."""
    if _reciprocal(intent, c):
        return 'reciprocal', WEIGHTS['tier_reciprocal'], set(), 'you both want the same thing'
    best, matched = topical(topics, [str(x).lower() for x in c['interests']])
    if best == 4:
        return 'exact', WEIGHTS['tier_exact'] + WEIGHTS['tier_exact_step'] * min(max(len(matched)-1, 0), 3), \
               matched, 'shares ' + ', '.join(sorted(matched)[:2])
    if best == 3:
        return 'adjacent', WEIGHTS['tier_adjacent'], matched, 'same kind of activity'
    if best == 2:
        return 'related', WEIGHTS['tier_related'], matched, 'related interest'
    if best == 1:
        return 'broad', WEIGHTS['tier_broad'], matched, 'adjacent interest'
    if dating:                                                     # dating: opt-in gated, ranked by fit below
        return 'broad', WEIGHTS['tier_broad'], set(), 'open to dating nearby'
    return 'none', 0, set(), ''

def _tier_label(score):
    W = WEIGHTS
    return ('T0' if score >= W['thr_t0'] else 'T1' if score >= W['thr_t1'] else 'T2' if score >= W['thr_t2']
            else 'T3' if score >= W['thr_t3'] else 'T4' if score >= W['thr_t4'] else 'T5')

def _diversify(items):
    """Keep at most WEIGHTS['diversity_max'] per dominant-interest bucket; cap at top_n. Items pre-sorted desc."""
    # Focused search (1-2 buckets): DON'T cap — a "tennis" search must return all the tennis players, not 3
    # of them padded with unrelated people. Only diversify when the results genuinely span many categories.
    buckets = {it.get('bucket') or 'other' for it in items}
    cap = WEIGHTS['diversity_max'] if len(buckets) > 2 else WEIGHTS['top_n']
    seen, out = {}, []
    for it in items:
        b = it.get('bucket') or 'other'
        if seen.get(b, 0) >= cap:
            continue
        seen[b] = seen.get(b, 0) + 1
        out.append(it)
        if len(out) >= WEIGHTS['top_n']:
            break
    return out

def match_candidates_legacy(intent, prof, ctx=None):
    W = WEIGHTS
    ctx = ctx or {}
    sess = _session(ctx.get('uid', 'me'))
    feedback = dict(sess.get('feedback') or {}); feedback.update(ctx.get('feedback') or {})
    gate_ctx = {'feedback': feedback,
                'blocked': set(sess.get('blocked') or []) | set(ctx.get('blocked') or [])}
    topics   = [str(t).lower() for t in (intent.get('topics') or [])]
    irole    = (intent.get('role') or 'meet').lower()
    my_langs = {str(l)[:2].lower() for l in _langs_of(prof)}
    my_vibe  = str(prof.get('vibe') or '').lower()
    dating   = (intent.get('type') or '').lower() == 'dating'
    soon     = any(w in str(intent.get('time', '')).lower() for w in SOON_WORDS)
    exactReq = bool(intent.get('exactMatchRequired'))
    adjOk    = intent.get('adjacentAllowed', True)
    broadOk  = intent.get('broadAllowed', True)
    # the searcher must never match themselves — identify them by name (or uid) and skip that candidate
    self_name = str(ctx.get('self') or prof.get('name') or ctx.get('uid') or '').strip().lower()
    self_id = str(ctx.get('self_id') or '')
    out = []
    for c in _with_km(load_candidates(), prof, ctx):        # same radius fix as the Core v2 path
        if _is_self(c, self_id, self_name):
            continue
        # ── 1. HARD GATES ──
        ok, _why = _hard_gates(intent, c, gate_ctx)
        if not ok:
            continue
        # ── 2. BASE TIER (reciprocal / exact / adjacent / related / broad) + search-breadth gates ──
        kind, score, matched, tier_reason = _base_tier(intent, c, topics, dating)
        if kind == 'none':
            continue                                              # never propose unrelated people
        if exactReq and kind not in ('reciprocal', 'exact'):
            continue
        if kind == 'adjacent' and not adjOk:
            continue
        if kind in ('related', 'broad') and not broadOk:
            continue
        reasons = [tier_reason]
        # ── 3. CAPPED MODIFIERS (base dominates; each just nudges) ──
        crole = (c.get('role') or '').lower()
        if irole != 'meet' and crole:
            if irole == crole:
                score += W['role_same']; reasons.append('same role (%s)' % irole)
            elif (irole, crole) in ROLE_CONFLICT:
                score += W['role_diff']; reasons.append('different role (%s)' % crole)
        if my_vibe and my_vibe == (c.get('vibe') or '').lower():
            score += W['vibe']; reasons.append('similar vibe')
        if my_langs and (my_langs & {str(l)[:2].lower() for l in c['langs']}):
            score += W['lang']; reasons.append('common language')
        if c.get('open'):
            score += W['mood_open']; reasons.append('open to meet')
        if soon:
            score += (W['time_fit'] if c.get('open') else W['time_conflict'])
            reasons.append('suits your time' if c.get('open') else 'may not be free then')
        if (c.get('lastActiveDays') or 0) <= 3:
            score += W['fresh']; reasons.append('recently active')
        # entity affinity — shared named club/game/scene
        ents = ' | '.join(str(e).lower() for e in (c.get('entities') or []))
        if ents and any(t in ents for t in topics):
            score += W['entity']; reasons.append('shares a community')
        # geo
        # Distance is OPTIONAL. `km` is computed only inside _gen_pool(), i.e. only for the demo
        # fakes; a real registered person carries km=None on purpose (onboarding's own comment: a
        # stored per-person distance is meaningless, it depends on who is looking). Comparing that
        # None to a float raised TypeError and the whole ranking returned zero candidates — which,
        # once the demo fallback was switched off, made every search look empty for a real user.
        # Unknown distance now scores as what it is: no proximity signal, no bonus, no penalty.
        km = c.get('km')
        if isinstance(km, (int, float)):
            if km <= GEO_NEAR:
                score += W['geo_near']; reasons.append('very close (%.1f km)' % km)
            elif km <= GEO_MID:
                score += W['geo_mid']; reasons.append('%.1f km away' % km)
            elif km <= GEO_FAR:
                score += W['geo_far']
        # feedback loop — learn from the owner's past decisions
        fb = feedback.get(c['name'])
        if fb == 'accepted':
            score += W['fb_accept']; reasons.append('you accepted them before')
        elif fb == 'rejected':
            score += W['fb_reject']; reasons.append('you passed on them before')
        # ── 4. DETERMINISTIC TIEBREAK + CLAMP ──
        score = round(max(0.0, min(100.0, score + _tiebreak(c['name']))), 1)
        # dominant-interest bucket (for diversify)
        bcat = (cat_of(sorted(matched)[0])[0] if matched else None) or cat_of((c['interests'] or ['x'])[0])[0] or 'other'
        tier = _tier_label(score)
        agree = bool(c.get('open') and score >= W['thr_t2'])
        note = ('Agent agreed — ' + reasons[0]) if agree else \
               ('Agent: not free today' if not c.get('open') else 'Agent: fit too weak')
        out.append({"name": c['name'], "score": score, "tier": tier, "kind": kind, "km": km,
                    "vibe": c['vibe'], "open": c['open'], "verified": c.get('verified'), "age": c.get('age'),
                    # Языки нужны карточке (O.13): без них человек решает, писать ли незнакомому,
                    # не зная, поймут ли его вообще. Внутри они у кандидата были всегда — просто
                    # никогда не выезжали наружу. `_langs_of` берёт обе формы хранения.
                    "interests": c['interests'], "role": c.get('role'), "dealBreakers": c.get('dealBreakers'),
                    "langs": _langs_of(c) or c.get('langs') or [],
                    # Сводка о человеке — на карточку вместо разбора совпадения: «общее: coffee,
                    # совпадает формат» человек и так видит по чипам, а хочет прочитать, кто перед ним.
                    "summary": str(c.get('summary') or '')[:600],
                    "reasons": reasons, "agree": agree, "note": note, "bucket": bcat})
    out.sort(key=lambda x: (-x['score'], x['name']))
    return _diversify(out)

# taxonomy helpers injected into core_v2 — module-level (all four are immutable), so every scorer reuses
# one dict instead of rebuilding it per request.
_H = {'topical': topical, 'cat_of': cat_of, 'reciprocal': _reciprocal, 'role_conflict': ROLE_CONFLICT}


def _blocks():
    """who (normalised) -> the set of names they have blocked, as a list. Stored per NAME, like
    requests and messages, because SESSION['me'] is a single shared session and a block list living
    there would be one global block list for the whole product."""
    return SESSION.setdefault("_blocks", {})


def _blocked_by(who):
    return set(_blocks().get(_norm_name(who)) or [])


def _gate_ctx_and_self(ctx, prof=None):
    """Owner session -> (hard-gate context, self-name), shared by match_candidates / _negotiate_precheck /
    explain_match so the eligibility inputs never drift between the real slate and the diagnostic."""
    ctx = ctx or {}
    self_id = str(ctx.get('self_id') or '')
    # Личные записи ищущего (оценки, чёрный список) — по его id, если он известен.
    sess = _session(self_id or ctx.get('uid', 'me'))
    self_name = str(ctx.get('self') or (prof or {}).get('name') or ctx.get('uid') or '').strip().lower()
    # _hard_gates compares c['name'] against this set, so it has to hold names as WRITTEN, not
    # normalised — and the reverse direction is stamped onto the candidates as `blocksMe`.
    blocked = (set(sess.get('blocked') or []) | set(ctx.get('blocked') or [])
               | _blocked_by(self_id or self_name))
    # The other direction, resolved ONCE per search rather than per candidate: everyone who has
    # blocked me. Without it the gate depends on a `blocksMe` flag that only the demo pool carries.
    _me_key = _norm_name(self_id) if self_id else self_name
    blocked_me = {k for k, v in _blocks().items() if _me_key and _me_key in set(v or [])} \
        if _me_key else set()
    gate_ctx = {'feedback': dict(sess.get('feedback') or {}), 'blocked': blocked,
                'blocked_norm': {_norm_name(b) for b in blocked} | blocked_me, 'self': self_name,
                'self_id': str(ctx.get('self_id') or '')}
    return gate_ctx, self_name


# ---- §11 allocation & fairness (post-relevance, post-policy). Allocation decides who/how many get shown —
# it NEVER changes a pair's relevance (§11 intro) and NEVER reads payment_status (§11.3). Every mechanism is
# a NO-OP at the pilot defaults below (cap huge / quota 0 / guard off), so the surfaced slate is byte-identical
# to core_v2's; a mechanism bites ONLY under an explicit ctx['allocation'] override (falsifiably testable,
# like the §7 retrieval budget). Overridden via ctx only — NEVER the sha-pinned config, so its sha is unchanged.
ALLOCATION_CONFIG = {
    "exposure_cap_per_window": 10 ** 9,   # §11.1 per-user impression cap -> remove over-exposed tail; huge = off
    "exposure_window_s":       7 * 86400,
    "exploration_quota":       0,         # §11.2 step5 ADD count for new users; 0 -> adds nobody
    "exploration_min_coverage": 0.6,
    "popularity_max_slate_share": 1.0,    # §11.1 popularity-concentration guard; 1.0 = off
    "popularity_min_exposure": 10 ** 9,
    "supply_max_per_area":     10 ** 9,   # §11.1 city/area supply balancing; huge = off
    "responsive_max_exposure": 10 ** 9,   # §11.1 protect the most-responsive (demote-only); huge = off
    "pair_cooldown_days":      0,         # §11.1 general same-pair repeat-proposal cooldown at send; 0 = off
}

def _alloc_cfg(ctx):
    cfg = dict(ALLOCATION_CONFIG)
    ov = (ctx or {}).get("allocation")
    if isinstance(ov, dict):
        cfg.update({k: v for k, v in ov.items() if k in ALLOCATION_CONFIG})
    return cfg

def _alloc_is_default(cfg):
    return cfg == ALLOCATION_CONFIG       # exact pilot default -> _allocate early-returns the SAME list object

def _within_band_demote(slate, cfg, exp):
    """§11.1 popularity-concentration guard + most-responsive protection — DEMOTE-ONLY, WITHIN each band, and
    re-applying the FROZEN sort key so open_now/reciprocal/lcb precedence (RCV9/§11.2-2) can never be violated.
    Dormant unless the thresholds are lowered; never a ranking boost, never a scoring write-back."""
    pmin, rmax = cfg["popularity_min_exposure"], cfg["responsive_max_exposure"]
    if pmin >= 10 ** 9 and rmax >= 10 ** 9:
        return slate
    resp = _responsive_counts()
    def _demote(c):
        e = exp.get(str(c.get("name", "")).strip().lower(), 0)
        return (e > pmin) or (e > rmax and resp.get(c.get("name"), 0) > 0)
    key = lambda c: (_core.READINESS_RANK.get(c.get("readiness"), 9), -(c.get("reciprocal") or 0),
                     -(c.get("lcb") or 0), -(c.get("coverage") or 0), str(c.get("name")))
    from collections import OrderedDict
    bands, out = OrderedDict(), []
    for c in slate:
        bands.setdefault(c.get("band"), []).append(c)
    for _b, cards in bands.items():
        keep = sorted([c for c in cards if not _demote(c)], key=key)
        dem = sorted([c for c in cards if _demote(c)], key=key)
        out.extend(keep + dem)
    return out

def _allocate(slate, ctx, pool=None):
    """§11 allocation pass. DORMANT at pilot defaults (returns the SAME list object, byte-identical). Reads
    exposure / outcomes / area into LOCAL decision logic ONLY — never writes back into lcb/reciprocal/mean/
    coverage/score (no feedback into relevance, §11 intro); never reads payment_status (§11.3)."""
    cfg = _alloc_cfg(ctx)
    if _alloc_is_default(cfg):
        return slate
    win = int(cfg["exposure_window_s"])
    exp = _exposures_in_window(win)
    out = list(slate)
    cap = cfg["exposure_cap_per_window"]              # per-user exposure cap -> remove over-exposed (tail, order kept)
    if cap < 10 ** 9:
        out = [c for c in out if exp.get(str(c.get("name", "")).strip().lower(), 0) < cap]
    smax = cfg["supply_max_per_area"]                 # city/area supply balancing (drop lowest-ranked surplus)
    if smax < 10 ** 9:
        seen, keep = {}, []
        for c in out:
            a = str(c.get("area") or "").strip().lower() or "_"
            if seen.get(a, 0) < smax:
                seen[a] = seen.get(a, 0) + 1
                keep.append(c)
        out = keep
    out = _within_band_demote(out, cfg, exp)          # popularity + responsive protection (demote-only, in-band)
    q = int(cfg["exploration_quota"])                 # §11.2 step5 exploration append (0 -> nobody; never fabricates)
    if q > 0 and pool:
        have = {str(c.get("name", "")).strip().lower() for c in out}
        picks = sorted((c for c in pool if str(c.get("name", "")).strip().lower() not in have),
                       key=lambda c: exp.get(str(c.get("name", "")).strip().lower(), 0))
        for c in picks[:q]:
            out.append(dict(c, exploration=True, allocation_action="exploration"))
    return out

def _stamp_allocation_trace(slate, ctx, cfg):
    """§11.2 step 6: additive read-only per-card allocation trace. Reorders/drops/adds NOTHING. Contains ZERO
    payment keys and ZERO acceptance-probability proxy — propensity stays null / absent_by_design (§9/§10).
    NOTE: exposure_count/fatigue_state legitimately VARY across two identical match_candidates calls as the
    logs accumulate — any full-card / replay diff MUST exclude 'allocation_trace'."""
    win = int(cfg["exposure_window_s"])
    exp = _exposures_in_window(win)
    received24 = (ctx or {}).get("received24") or {}
    fatigue_cap = int(((_CORE_CFG or {}).get("outreach") or {}).get("max_proposals_received_per_user_24h") or 4)
    for idx, c in enumerate(slate):
        nm = str(c.get("name", "")).strip().lower()
        reasons = []
        if c.get("policy") == "REVIEW":     reasons.append("held: safety/legal review")
        if not c.get("can_outreach"):       reasons.append("discovery only (no personal outreach)")
        if c.get("fallback"):               reasons.append("expansion: %s" % c.get("fallback"))
        if c.get("exploration"):            reasons.append("exploration slot")
        c["allocation_trace"] = {
            "position": idx, "bucket": c.get("bucket"), "tier": c.get("tier"),
            "readiness_class": c.get("readiness"), "exposure_count": exp.get(nm, 0),
            "fatigue_state": "fatigued" if received24.get(nm, 0) >= fatigue_cap else "ok",
            "diversity_bucket": c.get("bucket"), "exploration": bool(c.get("exploration")),
            "propensity": None, "propensity_status": "absent_by_design",   # no acceptance probability (§9.4/§10.3)
            "allocation_reasons": reasons,
        }
    return slate


# ---- §7 candidate retrieval: staged budgets + source order (read-only over the sealed scorer) ------------
# ОТСЕЧКА ДО СКОРИНГА ОБЯЗАНА БЫТЬ ВЫШЕ ПУЛА. Порядок отбора считает `topical()` по реестру интересов
# (shared/interests.json), а ярус человеку ставит движок по СВОЕМУ канону (matching_core/taxonomy).
# Словари разные: кого реестр ставит в хвост, того канон может считать T1–T3. При бюджете 500 из ~880
# допущенных срезалось ДО скоринга: кофе — 1 T1 + 40 T2 + 6 T3, падел — 23 T2 + 8 T3, прогулка —
# 2 T1 + 98 T3 (замер 30.09.2026), а пополнение канона теряло бы 43–47% новых совпадений. Прежний
# комментарий обещал, что срез «никогда не кусает» и режет лишь T5: пул перерос бюджет, и обещание
# стало неправдой. Пока отбор не ранжирует тем же каноном, что и движок, бюджет держится ВЫШЕ
# допущенного пула (1000 при ~880); вырастет пул — поднять и перемерить задержку.
RETRIEVAL_BUDGET = {"prefilter": 500, "structured": 1000}
# §7.2 the seven-stage retrieval pipeline (documented; the deterministic in-memory prefilter is the stdlib
# stand-in for SQL/PostGIS/H3, and ANN/pgvector recall is infra out of scope — both marked accordingly).
RETRIEVAL_STAGES = [
    {"stage": "hard_prefilter",     "mechanism": "in-memory policy gates + geo radius (SQL/PostGIS/H3 = infra, deferred)", "pilot": "1000->100-250", "llm": False},
    {"stage": "structured_retrieval", "mechanism": "taxonomy overlap + active intents, ordered by source, capped by budget", "pilot": "100-250->30-80", "llm": False},
    {"stage": "ann_recall",         "mechanism": "pgvector embeddings — INFRA, not in the stdlib prototype", "pilot": "+top 50", "llm": False, "status": "blocked_infra"},
    {"stage": "feature_build",      "mechanism": "core_v2.build_features (7 canonical evidence groups)", "pilot": "30-80->10-30", "llm": False},
    {"stage": "ranking_slate",      "mechanism": "core_v2 directional/reciprocal + _slate diversify TOP_N=8", "pilot": "10-30->3-8", "llm": False},
    {"stage": "explanation",        "mechanism": "reason keys -> NL (_presentation), final slate only", "pilot": "final slate", "llm": "optional"},
    {"stage": "agent_probe",        "mechanism": "negotiate top candidates (allowlisted)", "pilot": "top 1-3", "llm": "small"},
]
# §7.1 the five retrieval sources. 1/2/5 are live person sources; 3/4 are DECLARED but pilot-disabled
# (groups/events/rooms are non-pilot decision types — kleal_intent.PILOT_DECISION_TYPES), so they retrieve
# zero candidates rather than being faked.
RETRIEVAL_SOURCES = {
    1: {"name": "active_intent_match", "enabled": True},
    2: {"name": "active_receiving_direct_interest", "enabled": True},
    3: {"name": "groups_with_capacity", "enabled": False, "note": "pilot-disabled (§15 group formation)"},
    4: {"name": "events_and_rooms", "enabled": False, "note": "pilot-disabled (§16); the online-room fallback is the T4 alternative"},
    5: {"name": "parent_adjacent_expansion", "enabled": True},
}

def _retrieval_source(intent, c, best=None):
    """§7.1 retrieval-source provenance for one candidate: 1 = its own active intent reciprocally matches;
    2 = a direct confirmed interest (best>=4); 5 = parent/sibling/adjacent only (best 1-3); 0 = no overlap
    (the tail, retrieved last / only to feed controlled expansion)."""
    try:
        if best is None:
            best = topical([str(t).lower() for t in (intent.get("topics") or [])],
                           [str(x).lower() for x in (c.get("interests") or [])])[0]
        if _reciprocal(intent, c):
            return 1
        if best >= 4:
            return 2
        if best >= 1:
            return 5
        return 0
    except Exception:
        return 0

_SOURCE_RANK = {1: 0, 2: 1, 5: 2, 0: 3}   # retrieval priority: reciprocal -> direct -> adjacent -> no-overlap tail

def _retrieve(intent, eligible, budget):
    """§7.2 structured-retrieval stage. Labels each eligible candidate with its §7.1 source, orders by
    retrieval priority (reciprocal -> direct interest -> parent/adjacent -> no-overlap tail), and caps at the
    budget. The ORDER is invisible to the surfaced slate (the engine re-sorts totally). The CAP is NOT
    tier-safe: the order comes from the registry-based `topical()`, while the engine assigns tiers from its
    own canon, so a cut below the eligible pool can drop people the engine would score T1-T3 (measured
    30.09.2026, see RETRIEVAL_BUDGET). The slate is byte-identical only while the eligible pool <= budget.
    Returns (retrieved_pool, source_by_name, stats)."""
    topics = [str(t).lower() for t in (intent.get("topics") or [])]
    # МОСТ ТЕМ: сторона запроса разбирается ЗДЕСЬ, на входе в отбор, и только для новых слов.
    # Интересы популяции разобраны заранее, а слово запроса может быть таким, какого нет ни у кого
    # («опционы»), — тогда мост без этого вызова молчит, и запрос снова находит одного. Один
    # вопрос фильтрации на слово за всю его жизнь, дальше из памяти.
    qbridge = resolve_query_topics(topics, str(intent.get("_query") or ""))
    scored, source_by = [], {}
    for c in eligible:
        nm = str(c.get("name", "")).strip().lower()
        best = topical(topics, [str(x).lower() for x in (c.get("interests") or [])], qbridge)[0]
        src = _retrieval_source(intent, c, best)
        source_by[nm] = src
        scored.append((_SOURCE_RANK.get(src, 3), -best, nm, c))
    scored.sort(key=lambda t: (t[0], t[1], t[2]))
    retrieved = [t[3] for t in scored[:max(0, int(budget))]]
    stats = {"eligible": len(eligible), "retrieved": len(retrieved), "budget": int(budget),
             "dropped_tail": len(eligible) - len(retrieved),
             "by_source": {s: sum(1 for v in source_by.values() if v == s) for s in (1, 2, 5, 0)}}
    return retrieved, source_by, stats

def _tier_analytics(rows):
    """§7.1: relevance distribution measured SEPARATELY WITHIN each semantic tier (tier is immutable
    provenance; analytics never promotes a tier). Over explain rows carrying a_to_b.lcb/coverage."""
    by = {}
    for m in (rows or []):
        t = m.get("tier")
        ab = m.get("a_to_b") or {}
        d = by.setdefault(t, {"lcbs": [], "covs": []})
        if isinstance(ab.get("lcb"), (int, float)):      d["lcbs"].append(ab["lcb"])
        if isinstance(ab.get("coverage"), (int, float)): d["covs"].append(ab["coverage"])
        d["count"] = d.get("count", 0) + 1
    out = []
    for t in sorted(by, key=lambda x: str(x)):
        d = by[t]; ls, cs = d["lcbs"], d["covs"]
        out.append({"tier": t, "count": d.get("count", 0),
                    "lcb_mean": round(sum(ls) / len(ls), 4) if ls else None,
                    "lcb_min": round(min(ls), 4) if ls else None,
                    "lcb_max": round(max(ls), 4) if ls else None,
                    "coverage_mean": round(sum(cs) / len(cs), 4) if cs else None})
    return out

def _retrieval_report(slate):
    """§7.2 pipeline + §7.1 source provenance summary for a response (additive, read-only)."""
    src_counts = {}
    for c in (slate or []):
        s = c.get("retrieval_source")
        src_counts[str(s)] = src_counts.get(str(s), 0) + 1
    return {"stages": RETRIEVAL_STAGES, "sources": RETRIEVAL_SOURCES, "budget": RETRIEVAL_BUDGET,
            "slate_size": len(slate or []), "slate_by_source": src_counts,
            "top_n": (_core.TOP_N if CORE_V2 else None)}


def _photo_by_name():
    """name (normalised) -> photo URL, for everything that shows a person by name."""
    out = {}
    for u in load_candidates():
        ph = u.get("photo")
        if ph:
            out[str(u.get("name", "")).strip().lower()] = ph
    return out


def _tz_by_name():
    """имя (нормализованное) -> часовой пояс человека.

    Нужен ровно для одного правила спеки: «Таймзона в UI — только при РАСХОЖДЕНИИ». Пока чужого
    пояса не было нигде, расхождение не с чем было считать, и строку «20:00 Barcelona · 19:00
    London» с кадров O.14/O.21/O.C3 показать было нечем.
    """
    out = {}
    for u in load_candidates():
        tz = str(u.get("tz") or "").strip()
        if tz:
            out[str(u.get("name", "")).strip().lower()] = tz
    return out


def _stamp_matched_first(cards, topics):
    """Поставить СОВПАВШИЕ интересы в начало списка на карточке.

    Карточка показывает три первых интереса, а список приходил в том порядке, в каком человек
    его завёл. Получалось так: сводка пишет «Общее: dota2», а чипы показывают подлёдную рыбалку,
    поиск работы и силовую тренировку — того единственного, из-за чего человек вообще попал в
    выдачу, на карточке НЕТ. Проверено на трёх подряд: apex legends, minecraft, dota2 — ни один
    не был виден.

    Порядок внутри группы сохраняется (устойчивая сортировка): совпавшие идут в своём исходном
    порядке, за ними всё остальное в своём. Ни один интерес не выбрасывается — меняется только
    очередь, потому что решает её не человек, а ширина экрана.

    Ставится ЗДЕСЬ, рядом с фотографией, по той же причине: карточки собираются в четырёх местах,
    и это единственная точка, где слейт уже окончателен.
    """
    ts = [str(t).lower() for t in (topics or []) if str(t).strip()]
    if not ts:
        return cards
    for c in (cards or []):
        if not isinstance(c, dict):
            continue
        ints = c.get("interests") or []
        if len(ints) < 2:
            continue
        try:
            from matching_core.taxonomy import graph as _G
            lvl = {}
            for x in ints:
                lvl[id(x)] = _G.similarity(ts, [str(x).lower()])[0]
            if not any(lvl.values()):
                continue                       # ничего не совпало — переставлять нечего
            c["interests"] = sorted(ints, key=lambda x: -lvl.get(id(x), 0))
        except Exception:
            pass                               # порядок чипов не повод ронять выдачу
    return cards


def _stamp_photo(cards):
    """Put each person's real photo onto their card, in ONE place.

    Cards are assembled in four different code paths (core_v2, the matching_core adapter, the legacy
    scorer and the §12 expansion fallback), and none of them carried a photo — so every candidate
    screen in the app fell back to the same stock portrait, shown under whatever name was ranked.
    Stamping here, after the slate is final, covers all four and cannot drift apart from them.

    The value is a short URL, never image bytes: users.json is re-read and held in memory to rank
    with, and a slate carrying base64 avatars would put the photo album on every search response."""
    by_name = None
    for c in cards or []:
        if isinstance(c, dict) and not c.get("photo"):
            # По id карточки: у тёзок разные лица. По подписи — только карточка без id (демо).
            ph = _photo_of(c.get("id")) if c.get("id") else None
            if not ph and not c.get("id"):
                by_name = by_name if by_name is not None else _photo_by_name()
                ph = by_name.get(str(c.get("name", "")).strip().lower())
            if ph:
                c["photo"] = ph
        # Пояс — рядом с лицом и по той же причине «в одном месте» (борд 1:1 · Online, 11.10.2026):
        # «19:30 Barcelona · 18:30 London» нужно ДО плана, в выдаче. Нового не раскрывает: город
        # человека в карточке уже есть.
        if isinstance(c, dict) and c.get("id") and not c.get("tz"):
            tz = _tz_of(c.get("id"))
            if tz:
                c["tz"] = tz
    return cards


def _slate_budget(intent):
    """How many people the slate may hold for THIS request.

    Person-to-person keeps the eight it has always returned — that is the answer to «найди мне
    человека», and a group request is no reason to make that list longer. §15, though, forms a group
    out of the slate it is handed and never retrieves for itself, so a company of twelve cannot be
    assembled from eight candidates: the group ceiling has to be matched by the slate feeding it.
    A little headroom above the seats keeps the choice a choice rather than "everyone we found"."""
    if _decision_type(intent) != "group_formation":
        return None                                        # None -> the engine's own TOP_N
    try:
        total = int((intent or {}).get("groupSize") or 0)
    except (TypeError, ValueError):
        total = 0
    seats = max(0, total - 1) or kg._MAX_MVP_SIZE
    return max(_core.TOP_N, min(2 * kg._MAX_MVP_SIZE, seats + 4))


@contextlib.contextmanager
def _matching_topic_context(intent):
    """Install one request's phrase/canonicalization context and restore the prior one."""
    intent = intent or {}
    prev_q = getattr(_QCTX, "bridge", None)
    try:
        from matching_core.taxonomy import graph as _TX
        prev_fn, prev_tof = _TX._bridge_fn(), _TX._topics_of_fn()
    except Exception:
        _TX, prev_fn, prev_tof = None, None, None
    effective = intent
    try:
        _phr = str(intent.get("_query") or intent.get("phrase") or "")
        _qb = resolve_query_topics(
            [str(t).lower() for t in (intent.get("topics") or [])], _phr)
        _set_query_bridge(_qb)
        _pn = _norm_phrase(_phr)
        # Profiles store canonical interest keys. Prefer that key when the query phrase has one,
        # so a translated label still compares literally with the stored interest.
        try:
            import interest_i18n as _ii
            _pk = _ii.key_of(_phr)
            if _pk:
                _pn = _pk
        except Exception:
            pass
        if _pn and len(_pn.split()) <= 3:
            _tl = [str(t).lower() for t in (intent.get("topics") or [])]
            if _pn not in _tl:
                effective = dict(intent, topics=[_pn] + _tl)
        if _TX is not None:
            _qbs = set(_qb or ())
            _TX.set_bridge(lambda x: topics_join(_qbs, topics_of(x)) if _qbs else False)
            _TX.set_topics_of(topics_of)
    except Exception:
        _set_query_bridge(())
    try:
        yield effective
    finally:
        _QCTX.bridge = prev_q
        if _TX is not None:
            _TX.set_bridge(prev_fn)
            _TX.set_topics_of(prev_tof)


def match_candidates(intent, prof, ctx=None, diag=None, want=None):
    """Вход подбора: ставит мост тем НА ВРЕМЯ поиска и гарантированно снимает его после.

    Мост — знание фильтрации о фразе запроса, впрыснутое в таксономию на один поиск (см.
    resolve_query_topics и graph.set_bridge). Снятие в finally обязательно: слот потоко-локальный,
    но поток живёт дольше запроса, и вызов, который моста не ставил — групповой подбор, батарея,
    диагностика, — не должен наследовать решение прошлого поиска. Восстанавливается ПРЕЖНЕЕ
    значение, а не пустота: если подбор однажды позовёт подбор, внутренний не снимет мост под
    внешним.
    """
    with _matching_topic_context(intent) as effective:
        return _match_candidates_engine(effective, prof, ctx, diag, want)


def _match_candidates_engine(intent, prof, ctx=None, diag=None, want=None):
    """Entry point. Policy hard gates run HERE (scoring only after ALLOW — spec §8), then §7 staged
    retrieval assembles the pool, then Core v2 scores it. KLEAL_CORE_V2=0 or an invalid config -> legacy
    scorer above, unchanged. The response is a superset of the legacy card contract.

    `diag`, when a dict is passed, is filled with the per-stage counts behind «почему никого нет».
    The rewrite dropped this parameter, which broke the admin funnel outright (TypeError: 4 args).
    It is restored with one stage the old funnel did not have and could not have shown: §7.2
    retrieval now caps the eligible pool at a budget BEFORE scoring, so `eligible` and `scored._in`
    legitimately differ and people can be lost between the gates and the ranker. A funnel that
    hides its narrowest stage is decoration."""
    if not CORE_V2:
        return _persona_order(match_candidates_legacy(intent, prof, ctx), intent)
    ctx = ctx or {}
    intent = ki.normalize_for_scoring(intent)              # §5: untrusted-output hardening (idempotent; PARITY)
    now = ctx.get('now') or time.time()
    if kc.is_expired(intent, now):                         # §4.3 Lifecycle: an expired intent never ranks
        return []
    intent = kc.compile_intent(intent, _intent_identity(intent), ctx, now)  # §4.3 canonical blocks + TTL
    gate_ctx, self_name = _gate_ctx_and_self(ctx, prof)
    self_id = gate_ctx.get('self_id') or ''
    prof = _prof_with_own_row(prof, self_name, self_id)     # настрой и интересы — из карточки ищущего
    eligible, policy_by = [], {}                            # ALLOW + REVIEW are both discoverable (§8/§0)
    _pool = _with_km(load_candidates(), prof, ctx)          # distance must exist before the radius gate
    if diag is not None:
        diag['pool'] = len(_pool)
        diag['gates'] = {}
        diag['self'] = 0
        diag['review'] = 0
    for c in _pool:
        if _is_self(c, self_id, self_name):
            if diag is not None:
                diag['self'] += 1
            continue                                       # the searcher never matches themselves
        decision, _why = _policy_decision(intent, c, gate_ctx)
        if decision == "BLOCK":
            if diag is not None:
                # _hard_gates has always returned the exact reason; both call sites threw it away.
                # It is the whole answer to «почему никого нет», and it costs a dict.
                k = str(_why or 'gate')
                diag['gates'][k] = diag['gates'].get(k, 0) + 1
            continue
        if decision == "REVIEW" and diag is not None:
            diag['review'] += 1
        policy_by[str(c.get('name', '')).strip().lower()] = decision
        eligible.append(c)
    if diag is not None:
        diag['eligible'] = len(eligible)
    ctx = dict(ctx)
    ctx.setdefault('now', now)                              # pinnable for deterministic replay
    ctx.setdefault('received24', _proposals_received_24h())  # proposal-fatigue counts -> readiness
    budget = int(ctx.get('retrieval_budget') or RETRIEVAL_BUDGET['structured'])   # §7.2 (test-overridable)
    retrieved, source_by, _rstats = _retrieve(intent, eligible, budget)           # §7.1 source order + §7.2 budget
    if diag is not None:
        diag['retrieved'] = len(retrieved)
        diag['retrieval_budget'] = budget
        # What the ranker was actually handed. The old funnel asserted scored._in == eligible; that
        # identity only held before staged retrieval existed.
        diag['scored'] = {'_in': len(retrieved), 'budget_dropped': max(0, len(eligible) - len(retrieved))}
    # Порядок по характеру должен применяться ДО отсечки, иначе он не значит ничего: восьмёрку
    # движок уже отобрал, а человек, прошедший тест, может стоять девятым — переставлять внутри
    # выдачи, в которую он не попал, бессмысленно. Поэтому у движка просим втрое больше карточек и
    # режем до восьми уже ПОСЛЕ переупорядочивания. Ранжирование при этом остаётся его: полосы
    # (band) сохраняются, меняется только порядок внутри полосы.
    n_final = _slate_budget(intent)
    # СКОЛЬКО ПОКАЗАТЬ. Восемь — это ПЕРВАЯ страница, а не весь ответ.
    #
    # Раньше срез стоял намертво: `slate[:TOP_N]`. Из-за этого «Расширить поиск» не мог показать
    # никого нового — ослабление условий лишь впускает больше людей в отбор, а вперёд всё равно
    # выходят те же лучшие восемь. Измерено на живом сервере: все четыре оси расширения вернули
    # ТУ ЖЕ восьмёрку, ноль новых имён. Со стороны это «нажимаю — ничего не происходит».
    #
    # `want` просит продолжение того же ранжирования: девятый идёт после восьмого, а не вместо.
    want_n = None
    if n_final is None and want:
        try:
            want_n = max(_core.TOP_N, min(48, int(want)))
        except (TypeError, ValueError):
            want_n = None
    over = None if n_final is not None else max(_PERSONA_OVERFETCH, (want_n or 0) + 8)
    hybrid = str(intent.get('mode') or '') == 'hybrid' and over is not None
    if hybrid:
        near, far, _meta = _hybrid_pair(intent, prof, ctx, eligible, budget, over)
        if not near and not far and eligible:
            near = _expand_fallback(intent, prof or {}, ctx, eligible)
        # Порядок по характеру считаем в КАЖДОЙ половине отдельно: иначе полосы двух выдач
        # перемешались бы, и «сначала ближние» перестало бы соблюдаться.
        slate = _hybrid_merge(_persona_order(near, intent), _persona_order(far, intent),
                              want_n or _core.TOP_N)
    else:
        slate, _meta = _core.search(intent, prof or {}, ctx, retrieved, _H, _CORE_CFG,
                                    top_n=(over if over is not None else n_final))
        if len(slate) < _MIN_FOUND and eligible:          # never dead-end while anyone is eligible (§12) —
            # Не только пусто: меньше трёх человек — тоже тупик для того, кто пришёл найти людей (02.10.2026).
            # Найденные остаются первыми, запасные ступени дописываются после них.
            have = {_card_key(c) for c in slate}
            slate = slate + [c for c in _expand_fallback(intent, prof or {}, ctx, eligible)  # FULL pool
                             if _card_key(c) not in have]
        slate = _persona_order(slate, intent)
        if over is not None:
            slate = slate[:(want_n or _core.TOP_N)]        # без `want` — ровно та же восьмёрка
    slate = _apply_policy(slate, policy_by)
    slate = _allocate(slate, ctx, retrieved)              # §11 allocation (DORMANT at pilot defaults; before contracts)
    slate = _stamp_contracts(slate, intent, ctx)          # §4.6/§8.3/§4.12 additive contract overlays
    for c in slate:                                        # §7.1 retrieval-source provenance (additive)
        c.setdefault("retrieval_source", source_by.get(str(c.get("name", "")).strip().lower(), 0))
    _stamp_photo(slate)                                    # the person's real face, from the store row
    _stamp_matched_first(slate, intent.get("topics"))     # чипы начинаются с того, из-за чего нашли
    _stamp_allocation_trace(slate, ctx, _alloc_cfg(ctx))  # §11.2 step 6 allocation reasons (additive, read-only)
    if diag is not None:
        diag['slate'] = len(slate)
        diag['meta'] = dict(_meta or {})                   # engine, config_version, domain, config_sha
    return slate

# ---------------- гибрид: две половины встречи, обе настоящие ----------------
# Кадр HY.09 даёт гибриду И место, И ссылку, а HY.21/HY.22 объясняют зачем: «both ways open» —
# один идёт в кафе, второй подключается по видео, и переключиться можно до последнего.
#
# Из этого следует то, чего поиск не делал: далёкий человек для гибрида — НОРМАЛЬНЫЙ кандидат.
# Жёсткого гейта радиуса у гибрида и не было (он включён только для mode == 'offline'), но замер на
# стенде показал, что этого мало: гибрид с радиусом 3 км вернул РОВНО ту же восьмёрку, что и
# офлайн, — расстояние доминирует в ранжировании, и «онлайн-половина» встречи не была
# представлена ни одним человеком. Гибрид на выходе не отличался от офлайна ничем.
#
# Поэтому два прохода одним и тем же движком: обычный (с радиусом) и «как онлайн» (без радиуса).
# Скоринг не трогаем — меняется только то, ЧТО у движка спрашивают. Ближние идут первыми, но
# несколько мест в выдаче зарезервированы за теми, кто придёт по ссылке.
_HYBRID_CALL_SLOTS = 2


def _hybrid_pair(intent, prof, ctx, eligible, budget, top_n):
    """(ближние, дальние, meta) — две выдачи одного движка по одному пулу."""
    far_i = dict(intent)
    far_i.pop("radiusKm", None)
    far_i["mode"] = "online"                     # «как если бы встречались только по ссылке»
    r_near, _src, _st = _retrieve(intent, eligible, budget)
    near, meta = _core.search(intent, prof or {}, ctx, r_near, _H, _CORE_CFG, top_n=top_n)
    r_far, _src2, _st2 = _retrieve(far_i, eligible, budget)
    far, _m2 = _core.search(far_i, prof or {}, ctx, r_far, _H, _CORE_CFG, top_n=top_n)
    return near, far, meta


def _hybrid_merge(near, far, n_final, lang_note=True):
    """Ближние вперёд, но не все места им: иначе гибрид — это офлайн под другим названием.

    Каждая карточка помечена тем, КАК этот человек попадёт на встречу, и это написано словами:
    место в списке, которое человек не может себе объяснить, он объяснит себе неверно."""
    key = lambda c: str((c or {}).get("name", "")).strip().lower()
    seen = {key(c) for c in near}
    extra = [c for c in far if key(c) not in seen]
    for c in near:
        c["join"] = "in_person"
    for c in extra:
        c["join"] = "call"
        c.setdefault("reasons_ru", []).append("далеко для встречи — подключится по ссылке")
        c.setdefault("reasons_en", []).append("too far to meet in person — can join the call")
    if not extra:
        return near[:n_final]
    slots = min(_HYBRID_CALL_SLOTS, len(extra), n_final)
    out = near[:max(0, n_final - slots)] + extra[:slots]
    if len(out) < n_final:                       # ближних не хватило — добираем дальними
        out += [c for c in extra[slots:] if key(c) not in {key(x) for x in out}][:n_final - len(out)]
    return out[:n_final]


# ---------------- personality: what the Kleal test collected, used where it can be used ----------------
# The test writes a closed set of axis tokens onto the person's row (onboarding _PERSONA_AXES). Nothing
# read them. This orders the slate by them — and ONLY orders it: character never gates anybody out.
# It cannot: the test is new, almost nobody has taken it, and a gate would answer most searches with an
# empty screen. A wish that quietly empties the results is worse than no wish at all.
#
# The engine's own relevance ordering is preserved exactly. Cards are regrouped only INSIDE the band the
# engine already put them in, so a weak match can never climb over a strong one because it filled in
# more of its profile.
# Сколько карточек просить у движка сверх восьми, чтобы переупорядочивание вообще имело материал.
# Втрое: дальше третьей страницы результата уже другая полоса релевантности, и поднимать оттуда
# человека за то, что он прошёл тест, — обман про совпадение.
_PERSONA_OVERFETCH = 24

_NATURE_SAY = {
    ("energy", "energised"):   ("заводной", "high-energy", "con energía"),
    ("energy", "drained"):     ("спокойный", "low-key", "tranquilo"),
    ("depth", "deep"):         ("говорит по душам", "goes deep", "habla a fondo"),
    ("depth", "light"):        ("лёгкий, с юмором", "light and funny", "ligero, con humor"),
    ("pace", "fast"):          ("открывается сразу", "opens up fast", "se abre enseguida"),
    ("pace", "slow"):          ("сначала присматривается", "takes their time", "se lo toma con calma"),
    ("planning", "advance"):   ("договаривается заранее", "plans ahead", "queda con antelación"),
    ("planning", "spontaneous"): ("спонтанный", "spontaneous", "espontáneo"),
    ("give", "listen"):        ("умеет слушать", "a good listener", "sabe escuchar"),
    ("give", "instigate"):     ("вытащит из дома", "gets you out", "te saca de casa"),
}


def _axes_of(p):
    """Axes out of whatever shape the store holds: bare {axis: token} or {"v":1,"axes":{…}}."""
    if not isinstance(p, dict):
        return {}
    a = p.get("axes") if isinstance(p.get("axes"), dict) else p
    return {str(k): str(v) for k, v in a.items() if isinstance(v, str)} if isinstance(a, dict) else {}


def _persona_by_name():
    """name (normalised) -> test axes. Same reason _photo_by_name exists: the four card-assembly
    paths do not carry the field, and the card came back with persona=null even for people whose
    row has it. Read at the end from the store, like the photo."""
    out = {}
    for u in load_candidates():
        ax = _axes_of(u.get("persona"))
        if ax:
            out[str(u.get("name", "")).strip().lower()] = ax
    return out


# Порядок ярусов (§7.1): T0 взаимный запрос, T1 прямой интерес, T2 родственная категория,
# T3 смежный контекст, T4 другой тип решения, T5 без пересечения.
_TIER_ORDER = {"T0": 0, "T1": 1, "T2": 2, "T3": 3, "T4": 4, "T5": 5}


def _persona_order(slate, intent):
    """§ product: «сначала те, кто подходят и заполнили интерес и характер».

    Ключи по порядку:
      1. ЯРУС — про то ли это вообще;
      2. полоса, которую дал движок, — насколько уверенно;
      3. сколько запрошенных черт характера у человека есть;
      4. читается ли профиль вообще — есть и интересы, и пройденный тест.
    При равенстве — позиция от движка, чтобы сортировка была устойчивой от начала до конца.

    ЯРУС СТАЛ ПЕРВЫМ КЛЮЧОМ. Раньше первой была полоса, а она выводится из уверенности
    (lcb/coverage), не из яруса, — и ярусы в выдаче перемешивались: человек спрашивал про
    велоспорт и получал бегуна (T2) ВЫШЕ велосипедиста (T1), потому что у бегуна профиль был
    полнее. Замерено калибровочной батареей: 7% выдач с перестановкой, 108 перевёрнутых пар;
    шесть из десяти оставшихся содержательных сбоев ЗОЛОТОЙ батареи — та же перестановка
    (spanish_native ниже spanish_learner, gym_cross ниже yoga, dinner_food ниже brunch).

    Почему ярус важнее уверенности: карточка показывает ИНТЕРЕСЫ, и несовпадение по ним человек
    видит глазами. Уверенность ему не показана ничем, поэтому объяснить ею порядок невозможно —
    выдача просто выглядит перепутанной.
    """
    slate = list(slate or [])
    want = {str(k): str(v) for k, v in ((intent or {}).get("wantPersona") or {}).items()
            if isinstance(v, str) and v}
    by_name = _persona_by_name()
    bands, keyed = {}, []
    for i, c in enumerate(slate):
        band = str(c.get("band") or c.get("tier") or "")
        if band not in bands:
            bands[band] = len(bands)          # порядок появления = порядок движка, не наш алфавит
        axes = _axes_of(c.get("persona")) or by_name.get(str(c.get("name", "")).strip().lower(), {})
        if axes and not c.get("persona"):
            c["persona"] = {"v": 1, "axes": axes}      # карточка теперь знает то, что знает строка
        hits = [k for k, v in want.items() if axes.get(k) == v]
        filled = bool(axes) and bool(c.get("interests"))
        c["persona_hits"] = len(hits)
        c["persona_filled"] = filled
        # Названо вслух на карточке: «спокойный — как ты просил». Совпадение, о котором человек не
        # прочитал, для него не существует, а место в списке он объяснит себе как угодно.
        for k in hits:
            say = _NATURE_SAY.get((k, want[k]))
            if not say:
                continue
            c.setdefault("reasons_ru", []).append("%s — как ты и хочешь" % say[0])
            c.setdefault("reasons_en", []).append("%s — as you asked" % say[1])
            c.setdefault("reasons_es", []).append("%s — como pediste" % say[2])
        tier = _TIER_ORDER.get(str(c.get("tier") or ""), 9)
        keyed.append((tier, bands[band], -len(hits), 0 if filled else 1, i, c))
    keyed.sort(key=lambda t: t[:5])
    return [t[5] for t in keyed]


def _apply_policy(slate, policy_by):
    """Stamp each card with its policy_decision + a typed allocation_action (§0 output table). A REVIEW
    candidate stays in discovery but is forced non-proposable — outreach only after the separate track."""
    for c in slate:
        decision = policy_by.get(str(c.get("name", "")).strip().lower(), c.get("policy") or "ALLOW")
        c["policy"] = decision
        if decision == "REVIEW":
            c["can_outreach"] = False
            if not c.get("note"):
                c["note"] = "Needs a safety/legal review before outreach"
            c.setdefault("trace", {})["policy"] = "REVIEW"
        else:
            c.setdefault("trace", {}).setdefault("policy", decision)
        c["allocation_action"] = _allocation_action(c)
        c["decision_class"] = _decision_class(c)          # §9.6 read-only 5-way label (additive)
    return slate

def _relationship_edge(name, uid="me", scope=None):
    """Advisory §4.12 pair edge from the session outcome store (new/contact/friend/repeat/avoid/block).
    NEVER authoritative — the real cooldown/block stays the matching hard gate; this is metadata only."""
    key = str(name or "").strip().lower()
    sess = _session(uid)
    outs = [e for e in (SESSION.get("_outcomes") or []) if e.get("name") == key]
    # §17.2 mode isolation: prefer a purpose-scoped feedback key (e.g. name::dating) so a dating decline never
    # flips a friendship edge; fall back to the bare name (legacy/domain-agnostic feedback stays byte-identical).
    fbmap = sess.get("feedback") or {}
    fb = None
    if scope:
        fb = fbmap.get("%s::%s" % (name, scope)) or fbmap.get("%s::%s" % (key, scope))
    fb = fb or fbmap.get(name) or fbmap.get(key)
    acc = sum(1 for e in outs if e.get("stage") == "accepted") or (1 if fb == "accepted" else 0)
    comp = sum(1 for e in outs if e.get("stage") == "completed")
    ov = {"blocked": key in {str(b).lower() for b in (sess.get("blocked") or [])},
          "rejected": fb == "rejected", "accepted": acc, "completed": comp,
          "cooldown_days": COOLDOWN_DAYS,
          "last_ts": (outs[-1]["ts"] if outs else None)}
    return kc.build_relationship_edge([uid, key], ov, scope=scope)

def _stamp_contracts(slate, intent, ctx):
    """§4 additive overlays on each returned card: a purpose-bound ProfileView (§8.3), a versioned
    CandidateSnapshot (§4.6) and the pair RelationshipEdge (§4.12). Wrapped PER CARD so a projection/
    snapshot error degrades to a missing sub-key — never a bubbled exception that empties the slate."""
    domain = (intent.get("identity") or {}).get("domain") or _core.infer_domain(intent, cat_of)
    uid = (ctx or {}).get("uid", "me")
    now_ts = (ctx or {}).get("now") or time.time()
    received24 = (ctx or {}).get("received24") or {}
    cfg_meta = {"config_version": (_CORE_CFG or {}).get("config_version"),
                "config_sha": ((_CORE_CFG or {}).get("_sha256") or "")[:12]}
    topics = intent.get("topics") or []
    live_by = {str(u.get("name", "")).strip().lower(): u for u in load_candidates()}   # full fields for §10 factors
    for c in slate:
        try:
            nm_key = str(c.get("name", "")).strip().lower()
            c["snapshot"] = kc.build_candidate_snapshot(c, intent, cfg_meta)
            c["profile_view"] = kc.build_profile_view(c, domain)
            c["relationship"] = _relationship_edge(c.get("name"), uid, scope=domain)
            for k, v in kt.enrich_card(topics, c.get("interests") or [],       # §6 typed edge + expansion + complementary
                                       role_a=intent.get("role"), role_b=c.get("role")).items():
                c.setdefault(k, v)                        # additive only — never touches band/tier/lcb/can_outreach
            c.setdefault("completion_factors", kcf.completion_factors(   # §10.2 transparent operational signals (no rating)
                live_by.get(nm_key, c), intent, now_ts, received24.get(nm_key, 0)))
            c.setdefault("readiness_explain", kcf.READINESS_EXPLAIN.get(c.get("readiness")))  # §10.1
            for _k in _PRECISE_LOCATION_KEYS:             # §8.4: home/work/exact location never in the payload
                c.pop(_k, None)                           # no-op today (no fixture carries these) — hard barrier later
        except Exception:
            pass                                          # degrade gracefully; the card stays valid
    return slate

# ---- §12 controlled expansion: the ordered ladder as a PLAN + step tagging (additive; the executed
# _expand_fallback below is unchanged and NEVER a dead-end). The PLAN is one-axis-per-step / cheapest-first;
# the EXECUTED fallback still relaxes two axes at once (adjacentAllowed + exactMatchRequired) and is tagged
# after the fact. provenance tier is KEPT (never re-tiered — sha-pinned); parent outreach needs broad consent;
# adjacent -> discovery, not an inbox; safety/age/consent/block/language/purpose are NEVER relaxed.
_LADDER = [
    {"step": 1, "axis": "exact_entity_role_same_time_zone", "relaxes": "none", "provenance_tier": "T0/T1",
     "outreach": {"mode": "personal", "broad_consent_required": False},
     "explanation_ru": "Точное совпадение сущности/роли, то же время и зона.",
     "explanation_en": "Exact entity/role at the same time and zone."},
    {"step": 2, "axis": "adjacent_sibling_entity", "relaxes": "entity_exactness", "provenance_tier": "T2/T3",
     "outreach": {"mode": "discovery", "broad_consent_required": True},
     "explanation_ru": "Смежная/родственная сущность — только discovery; personal лишь при broad consent.",
     "explanation_en": "Adjacent/sibling entity — discovery only; personal outreach needs broad consent."},
    {"step": 3, "axis": "parent_activity_category", "relaxes": "category_breadth", "provenance_tier": "T2",
     "outreach": {"mode": "discovery", "broad_consent_required": True},
     "explanation_ru": "Родительская категория — более широкий вариант; outreach только при broad consent.",
     "explanation_en": "Parent activity/category — a broader option; outreach needs broad consent."},
    {"step": 4, "axis": "widen_time_or_distance", "relaxes": "time_or_radius", "provenance_tier": "none",
     "outreach": {"mode": "discovery", "broad_consent_required": False},
     "explanation_ru": "Увеличить время или радиус в пределах согласия.",
     "explanation_en": "Increase time or distance within consent."},
    {"step": 5, "axis": "change_format", "relaxes": "format", "provenance_tier": "none",
     "outreach": {"mode": "discovery", "broad_consent_required": False},
     "explanation_ru": "Сменить формат: 1:1→малая группа или offline→online, если разрешено.",
     "explanation_en": "Change format: 1:1->small group or offline->online, if allowed."},
    {"step": 6, "axis": "event_room_group_alternative", "relaxes": "solution_type", "provenance_tier": "T4",
     "outreach": {"mode": "none", "broad_consent_required": False},
     "explanation_ru": "Событие/комната/группа как альтернативный способ закрыть запрос.",
     "explanation_en": "Event/room/group as an alternative solution type."},
    {"step": 7, "axis": "saved_search_notify", "relaxes": "immediacy", "provenance_tier": "none",
     "outreach": {"mode": "none", "broad_consent_required": False},
     "explanation_ru": "Сохранить поиск и уведомить позже.",
     "explanation_en": "Save the search and notify later."},
]
_LADDER_BY_STEP = {s["step"]: s for s in _LADDER}
_DOTA_EXAMPLE = [   # §12.3 — a LoL player never gets a personal proposal disguised as a close Dota match
    {"tier": "T0", "row": "active Dota 2 intent, role support, same server/time"},
    {"tier": "T1", "row": "confirmed Dota 2 interest + games receiving policy"},
    {"tier": "T2", "row": "other MOBA players — only as a broader option, never 'almost Dota'"},
    {"tier": "T4", "row": "active Dota room / watch party / group queue (alternative solution type)"},
    {"tier": "No supply", "row": "clarify: unranked ok? another evening? save the search?"},
]

def expansion_ladder(intent, ctx=None):
    """§12.2 the ORDERED expansion ladder as a read-only PLAN (never re-scores / re-tiers / mutates). Each
    step relaxes ONE soft axis, cheapest-first; safety/age/consent/block/language/purpose are never relaxed."""
    intent = intent or {}
    fb = intent.get("fallback") if isinstance(intent.get("fallback"), dict) else {}
    dims = [str(d).lower() for d in (fb.get("allowed_dimensions") or [])]
    consent = bool(fb.get("consent") or intent.get("broadConsent"))
    exact = bool(intent.get("exactMatchRequired"))
    out = []
    for s in _LADDER:
        st = dict(s, outreach=dict(s["outreach"]), cost_rank=s["step"])
        step = s["step"]
        if step == 1:
            app = True
        elif step == 2:
            app = (not exact) and ("adjacent" in dims or "related" in dims or intent.get("adjacentAllowed", True))
        elif step == 3:
            app = (not exact) and ("broader" in dims or intent.get("broadAllowed", True))
        elif step == 4:
            app = bool(intent.get("radiusKm")) or str(intent.get("mode")) == "offline"
        elif step == 5:
            app = bool(intent.get("allowOnlineFallback")) or str(intent.get("mode")) == "offline"
        else:
            app = True
        st["applicable"] = bool(app)
        if st["outreach"].get("broad_consent_required") and not consent:
            st["outreach"]["note"] = "broad consent not given — discovery only (no inbox)"
        out.append(st)
    return {"ladder": out, "dota_example": _DOTA_EXAMPLE,
            "principles": {"one_axis_per_step_in_plan": True, "cheapest_first": True,
                           "executed_fallback": "multi-axis (adjacentAllowed+exactMatchRequired), tagged after the fact",
                           "never_relaxes": ["safety", "age", "mutual_consent", "block", "critical_language", "purpose_isolation"]}}

def _ladder_step_for_card(card):
    """Map an executed fallback / online-room card to its §12.2 ladder step. PURE + exception-safe (only
    c.get() reads) so a tagging error can never regress the never-dead-end fallback into an empty slate."""
    c = card if isinstance(card, dict) else {}
    fb = str(c.get("fallback") or "")
    tier = str(c.get("tier") or "")
    if fb == "broader":
        return 2 if tier == "T3" else 3        # T3 adjacent -> step 2; T2 sibling/parent -> step 3
    if fb == "alternative":
        return 3
    if c.get("kind") == "alternative_solution_type":
        return 6
    return None

def _tag_ladder(cards):
    """Stamp ladder_step/axis/relaxes on executed fallback cards, additively, without reordering/dropping."""
    for c in (cards or []):
        if not isinstance(c, dict):
            continue
        step = _ladder_step_for_card(c)
        if step is not None:
            row = _LADDER_BY_STEP.get(step) or {}
            c.setdefault("ladder_step", step)
            c.setdefault("ladder_axis", row.get("axis"))
            c.setdefault("ladder_relaxes", row.get("relaxes"))
    return cards

_MIN_FOUND = 3          # меньше — запасные ступени лестницы (§12): шире, близкие по смыслу, похожие люди
# Темы, по которым «похожих людей» не подставляем никогда: выдача пустая честно (свидания идут своим типом).
_NO_SUBSTITUTE = re.compile(r"наркот|травк|марихуан|кокаин|закладк|\bdrugs?\b|\bweed\b|cannabis|cocaine|"
                            r"\bdrogas?\b|\bporros?\b|секс|интим|\bsex\b|nudes|porn", re.I)


def _card_key(c):
    return str(c.get("name") or c.get("id") or "").strip().lower()


def _meaning_of(topics, c):
    """(сходство, интерес) — ближайший по смыслу интерес человека к словам запроса (файл meaning_near)."""
    from matching_core.taxonomy import canonical as _canon
    best = (0.0, "")
    for t in topics or []:
        for x in c.get("interests") or []:
            try:
                s = _canon.meaning_score(t, x)
            except Exception:
                s = 0.0
            if s > best[0]:
                best = (s, str(x))
    return best


def _expand_fallback(intent, prof, ctx, eligible):
    """§12 controlled expansion — a search must never dead-end. Over the SAME hard-gate-eligible pool
    (eligibility/safety gates are NEVER relaxed): (1) re-score with adjacent tiers allowed and the
    discovery floor dropped, surfacing wider/adjacent people; (2) if there is no topical overlap at all,
    offer the nearest available people as an explicit 'different category' suggestion. Every card is
    tagged `fallback` (+ a note) so the UI can say the search was broadened — never a silent random pick."""
    if not eligible or not CORE_V2:
        return []
    relaxed = dict(intent, adjacentAllowed=True, exactMatchRequired=False)
    slate, _m = _core.search(relaxed, prof, ctx, eligible, _H, _RELAXED_CFG or _CORE_CFG)
    if slate:                                              # (1) broader / adjacent, below the normal floor
        for c in slate:
            c["fallback"] = "broader"
            c["note"] = "Broader match — a wider or adjacent category"
        return _tag_ladder(slate)                          # §12.2 tag with the ladder step (2 adjacent / 3 parent)
    # (2) no topical overlap anywhere -> nearest available eligible people, marked as a different category
    topics = [str(t) for t in (intent.get("topics") or [])]
    if any(_NO_SUBSTITUTE.search(t) for t in topics + [str(intent.get("title") or "")]):
        return []                                          # запрещённая тема: людей «вместо» не подставляем
    now_ts = (ctx or {}).get("now") or time.time()
    # Сначала — у кого интересы ближе к запросу по смыслу (сходство ≥0.55, ступенями по 0.05), потом открытые и
    # ближние. Раньше первым был ближайший: анкеты с координатами «центр города» стояли в 0 км от любого ищущего
    # и выходили первыми на любой запрос (02.10.2026).
    sem = {id(c): _meaning_of(topics, c) for c in eligible}
    avail = sorted((c for c in eligible if not _core.is_paused(c, now_ts)),
                   key=lambda c: (-(int(sem[id(c)][0] * 20) if sem[id(c)][0] >= 0.55 else 0),
                                  0 if c.get("open") else 1,
                                  float(c["km"]) if isinstance(c.get("km"), (int, float)) else 99.0,
                                  str(c.get("name") or "")))
    domain = _core.infer_domain(intent, cat_of)
    out = []
    for c in avail[:_core.TOP_N]:
        ints = c.get("interests") or []
        out.append({
            "name": c.get("name"), "score": 0, "tier": "T4", "kind": "alternative",
            "km": c.get("km"), "vibe": c.get("vibe"), "open": c.get("open"),
            "verified": c.get("verified"), "age": c.get("age"), "interests": ints,
            "langs": _langs_of(c) or c.get("langs") or [],
            "summary": str(c.get("summary") or "")[:600],
            "role": c.get("role"), "dealBreakers": c.get("dealBreakers"),
            "reasons": ["different interests — a broader suggestion"], "agree": False,
            "note": "Broader suggestion — a different category (no direct match right now)",
            "bucket": (cat_of(ints[0])[0] if ints else "other"),
            "band": "needs_clarification", "band_ru": "Нужно уточнение", "band_en": "Needs clarification",
            "band_es": "Necesita aclaración",
            "reasons_ru": ["другие интересы — более широкий вариант"],
            "reasons_en": ["different interests — a broader suggestion"], "gap_ru": None, "gap_en": None,
            "reasons_es": ["otros intereses — una opción más amplia"], "gap_es": None,
            "coverage": 0.0, "lcb": 0.0, "reciprocal": 0.0, "unknowns": [], "can_outreach": False,
            "readiness": "unknown", "readiness_ru": "доступность не настроена",
            "readiness_en": "availability not set", "readiness_es": "disponibilidad sin configurar",
            "fallback": "alternative",
            "trace": {"tier": "T4", "policy": "ALLOW", "domain": domain, "fallback": "alternative"},
        })
    # Честная подпись: у кого есть интерес, близкий по смыслу, — какой именно; у остальных «другие интересы».
    by = {str(c.get("name")): sem[id(c)] for c in avail[:_core.TOP_N]}
    for o in out:
        sc, x = by.get(str(o.get("name")), (0.0, ""))
        if sc >= 0.55 and x:
            o["reasons_ru"] = ["ближе всего к запросу: %s" % x]
            o["reasons_en"] = o["reasons"] = ["closest to your request: %s" % x]
            o["reasons_es"] = ["lo más cercano a tu búsqueda: %s" % x]
            o["fallback"] = "similar"
            o["note"] = "Similar interests — nobody named this exact activity yet"
    return _tag_ladder(out)                                 # §12.2 tag the alternative cards with the ladder step

def _expand_stepwise(intent, prof, ctx, eligible, min_cards=1):
    """§12.1 one-axis-per-step, cheapest-first: relax EXACTLY ONE axis per step over the SAME hard-gate-eligible
    pool (safety/age/consent/block/language/purpose NEVER relaxed), stopping at the first step yielding >=
    min_cards. Unlike _expand_fallback (which drops adjacent+exactness together), step 2 relaxes ONLY adjacency.
    Returns (cards, step). Additive — the pool is byte-identical; only discovery breadth widens."""
    if not eligible or not CORE_V2:
        return [], None
    for step, relaxed in ((2, dict(intent, adjacentAllowed=True)),
                          (3, dict(intent, adjacentAllowed=True, broadAllowed=True)),
                          (4, dict(intent, adjacentAllowed=True, broadAllowed=True, exactMatchRequired=False))):
        slate, _m = _core.search(relaxed, prof, ctx, eligible, _H, _RELAXED_CFG or _CORE_CFG)
        if len(slate) >= min_cards:
            for c in slate:
                c["fallback"] = "broader"; c["ladder_step"] = step
            return _tag_ladder(slate), step
    return [], None

def _online_fallback(intent):
    """When 0 offline candidates: offer to go live + ways to broaden — so the user never hits a dead end.
    §5.1 row4: the offline intent is NEVER silently swapped to online — going live is pre-approved only
    when the user explicitly said online is ok (allowOnlineFallback); otherwise it's an explained offer."""
    topics = ', '.join(intent.get('topics') or []) or 'this'
    approved = bool((intent or {}).get('allowOnlineFallback'))
    return {
        # §7.1 tier table: an online room is the T4 "alternative solution type" (another way to close the
        # intent, not a person) — no personal outreach; source 4 (events/rooms) surfaced as this alternative.
        "room": {"title": "Live room: " + intent.get('title', 'meet'), "approved": approved,
                 "tier": "T4", "kind": "alternative_solution_type", "retrieval_source": 4, "ladder_step": 6,
                 "options": [{"id": "voice", "label": "Start a voice room"},
                             {"id": "watch", "label": "Watch together online"}]},
        "suggestions": [   # §12.2: each broaden option tagged with its ladder step
            {"id": "inexact",  "label": "Allow less-exact matches", "ladder_step": 2},
            {"id": "adjacent", "label": "Include adjacent topics", "ladder_step": 2},
            {"id": "radius",   "label": "Widen the distance", "ladder_step": 4},
            {"id": "wait",     "label": "Save this search & notify me", "action": "save_search", "ladder_step": 7},
        ],
        "note": (("Online is pre-approved for this search — " if approved else "")
                 + "No offline matches for %s right now — go live, or broaden the search." % topics),
    }

def _section5_addendum(intent, text, cands):
    """§5.1/§5.2 additive response keys: the confirmation summary + the single rule-based clarification
    question for the compiled intent. Never mutates the intent or the slate."""
    _o, cons = ki.extract_constraints(text or "", intent)
    return {"intent_summary": ki.intent_summary(intent, cons),
            "clarification": ki.clarification_policy(intent, cons, has_results=bool(cands)),
            "minimally_sufficient": ki.minimally_sufficient(intent)}

def agent_plan(query, prof, ctx=None, override=None):
    intent = parse_intent(query)
    if isinstance(override, dict):                 # broaden the search scope (radius / inexact / adjacent)
        for k, v in override.items():
            if k in ('radiusKm', 'verifiedOnly', 'minAge', 'maxAge', 'requiredLanguages', 'mode',
                     'exactMatchRequired', 'adjacentAllowed', 'broadAllowed'):
                intent[k] = v
    ctx = ctx or {}
    intent, _cons = ki.extract_constraints(query, intent)   # §5.1: merge additive soft/proposed/fallback keys
    intent = kc.compile_intent(intent, _intent_identity(intent), ctx, ctx.get('now') or time.time())  # §4.3 blocks echoed
    cands = match_candidates(intent, prof or {}, ctx)
    res = {"intent": intent, "candidates": cands, "snapshot": _request_snapshot(intent)}
    res.update(_section5_addendum(intent, query, cands))
    res["retrieval"] = _retrieval_report(cands)           # §7 staged pipeline + source provenance
    res["expansion"] = expansion_ladder(intent, ctx)      # §12 controlled-expansion ladder (plan)
    if not cands:
        res["fallback"] = _online_fallback(intent)
    return res

# ---- Agent-to-agent intro (Phase 2): the candidate's agent confirms + an icebreaker opener ----
INTRO_PROMPT = '''You are the AI agent of user B. User A wants to meet for the activity below, and B's agent has agreed.
Write (a) as B's agent, a warm one-sentence confirmation to A's agent, and (b) a friendly one-sentence icebreaker
opener B could send A. Return ONLY JSON: {"reply":"...","opener":"..."}. English, lively, no markdown.'''
def agent_intro(intent, cand):
    topics = ', '.join(intent.get('topics') or intent.get('tags') or []) or 'this'
    ctx = 'Activity: %s (%s). Person B interests: %s. Vibe: %s.' % (
        intent.get('title', 'a meetup'), topics, ', '.join(cand.get('interests') or []), cand.get('vibe', ''))
    try:
        cfg = MODEL_ID
        raw = llm_complete(cfg, [{"role": "system", "content": settings.prompt("matching.intro", INTRO_PROMPT)}, {"role": "user", "content": ctx}], 0.6)
        obj = base._extract_json(raw)
        if isinstance(obj, dict) and obj.get('opener'):
            return {"reply": str(obj.get('reply', ''))[:200], "opener": str(obj.get('opener', ''))[:200]}
    except Exception:
        pass
    return {"reply": "My user is up for it — it works on their side.",
            "opener": "Hey! Looks like we both like " + topics + " — want to make a plan?"}

# ---- Agent-to-agent NEGOTIATION (LLM): the candidate's agent decides accept/reject, with a reason ----
NEGOTIATE_PROMPT = '''You are the AI agent of user B. User A sends an intent (a plan/activity) and wants to meet.
Decide, on B's behalf, whether B accepts. Consider: does the activity fit B's interests? do time and place work?
is B open/available right now? would it break any of B's deal-breakers (if so -> reject)?
Return ONLY JSON (no prose): {"decision":"accept"|"reject","reason":"one short sentence why","reply":"one lively sentence from B's agent to A's agent, or null if reject"}.'''

def negotiate_one(intent, cand):
    # §23.2.7 — the accept/reject VERDICT is a DETERMINISTIC protocol decision (availability from the readiness
    # engine + a score threshold), never delegated to the LLM. The LLM is used ONLY to phrase the opener reply.
    # So the agent-to-agent decision is replay-stable and testable; free-text is confined to `reply`.
    avail = (cand.get('readiness') == 'open_now') or bool(cand.get('open'))
    agree = bool(avail and cand.get('score', 0) >= 45)
    reason = 'good fit and free today' if agree else ('not free today' if not avail else 'fit is a bit weak')
    reply = None
    if agree:
        topics = ', '.join(intent.get('topics') or intent.get('tags') or []) or 'this'
        a = 'INTENT FROM A: %s. Topics: %s. Time: %s. Place: %s. Format: %s.' % (
            intent.get('title', ''), topics, intent.get('time', ''), intent.get('place', ''), intent.get('format', ''))
        b = 'USER B: interests %s; vibe %s; open to meet today: yes; deal-breakers: %s.' % (
            ', '.join(cand.get('interests') or []) or 'unknown', cand.get('vibe', ''),
            ', '.join(cand.get('dealBreakers') or []) or 'none')
        try:
            o = base._extract_json(llm_complete(MODEL_ID, [{"role": "system", "content": settings.prompt("matching.negotiate", NEGOTIATE_PROMPT)},
                                                            {"role": "user", "content": a + "\n" + b}], 0.4))
            if isinstance(o, dict) and o.get('reply'):
                reply = str(o.get('reply'))[:200]   # phrasing ONLY — never flips the deterministic verdict
        except Exception:
            pass
    return {"agree": agree, "reason": reason, "reply": reply, "decided": True}

def _outreach_ok(intent, c):
    """Tier/consent gate for PERSONAL outreach (spec §7 tier table + §12): T0/T1 always, T2 only
    with broad consent, T3+/T5 never. Mirrors core_v2.search's outreach_tier_ok so the send path
    enforces the same consent rule the slate does."""
    if not CORE_V2:
        return True
    topics = [str(t).lower() for t in (intent.get('topics') or [])]
    tier = _core.assign_tier(intent, c, topics, _H)
    return tier in ('T0', 'T1') or (tier == 'T2' and bool(intent.get('broadConsent')))

_PTYPE_OF_DECISION = {"person_to_person": "person", "intent_to_intent": "person",
                      "group_formation": "group", "intent_to_event": "event", "intent_to_room": "room",
                      "intent_to_venue": "venue"}   # §16 additive (pilot-off); venue in kc.PROPOSAL_TYPES

def _receiving_send_gate(intent, live, now_ts):
    """§4.4 send-boundary enforcement of the EXTENDED ReceivingPolicy fields (beyond the base readiness
    that core_v2 already applies). ABSENT-FIELD-PERMISSIVE: a field only gates when the user actually set
    it. (block/avoid/cooldown stay the authoritative hard gate; not re-checked here.) Returns (ok, reason)."""
    r = live.get("receiving") if isinstance(live.get("receiving"), dict) else {}
    if not r:
        return True, None
    ptypes = r.get("allowed_proposal_types")
    if isinstance(ptypes, list) and ptypes:                    # (a) allowed_proposal_types
        want = _PTYPE_OF_DECISION.get(_decision_type(intent), "person")
        if want not in ptypes and not (want == "person" and "small_group" in ptypes):
            return False, "receiving policy: %r proposals not accepted" % want
    scope = r.get("location_scope")
    city = (intent.get("location_block") or {}).get("city")    # (b) location_scope — only when a real city is known
    if isinstance(scope, list) and scope and city:
        if not any(str(s).lower() in str(city).lower() or str(city).lower() in str(s).lower() for s in scope):
            return False, "receiving policy: outside allowed location scope"
    per7d = (r.get("proposal_budget") or {}).get("per_7d")     # (c) per_7d budget via the 7-day proposal log
    if per7d is not None:
        key = str(live.get("name", "")).strip().lower()
        log = SESSION.get("_proposals") or {}
        if sum(1 for t in (log.get(key) or []) if now_ts - t < 7 * 86400) >= int(per7d):
            return False, "receiving policy: 7-day proposal budget reached"
    return True, None

def _negotiate_precheck(intent, cands, now_ts=None):
    """Receiving-policy AND eligibility enforcement BEFORE any proposal goes out (spec §8.2: policy
    revalidation immediately before sending; §23.2 #12: no proposal without a receiving-policy check).
    /api/agent/negotiate accepts client-supplied candidates verbatim, so each is re-resolved against
    the LIVE store, re-run through the eligibility hard gates + the tier/consent outreach gate, then
    readiness is computed and the parallel wave capped from config (default 2, urgent 3).
    Returns (to_send, decided_without_sending)."""
    now_ts = now_ts or time.time()
    store = {str(u.get('name', '')).strip().lower(): u for u in load_candidates()}
    received = _proposals_received_24h()
    gate_ctx, _ = _gate_ctx_and_self({})
    out_cfg = ((_CORE_CFG or {}).get('outreach') or {})
    soon = any(w in str(intent.get('time', '')).lower() for w in SOON_WORDS)
    cap = int(out_cfg.get('urgent_same_day_parallel_proposals' if soon else
                          'default_parallel_proposals') or (3 if soon else 2))
    if not soon and intent.get('broadConsent'):            # §13.2 Wave 3: user-allowed expansion raises the cap
        cap = max(cap, 3)                                  # keeps the config-derived base; never a hardcoded 2/3
    wctx = {"urgent": soon, "expansion": bool(intent.get('broadConsent'))}
    to_send, decided, sent = [], [], 0
    for c in cands:
        nm = str(c.get('name', '')).strip().lower()
        live = store.get(nm, c)
        # §8.2 revalidation at the SEND boundary — never trust the caller's candidate list.
        if not (nm or c.get('name')):
            decided.append(dict(c, agree=False, decided=True, readiness="blocked",
                                reason="not eligible: no candidate id", reply=None)); continue
        live = dict(live); live['name'] = live.get('name') or c.get('name') or ''
        ok, why = _hard_gates(intent, live, gate_ctx)          # block / age / dating / language / radius…
        if not ok:
            # §8.2 POLICY_CHANGED: the caller handed us a proposable candidate that the LIVE store now blocks
            decided.append(dict(c, agree=False, decided=True, readiness="blocked",
                                code="POLICY_CHANGED", reason="not eligible: %s" % why, reply=None)); continue
        if _cross_purpose_blocked(intent, live):               # §8.1 mode isolation — parity with retrieval BLOCK
            decided.append(dict(c, agree=False, decided=True, readiness="blocked",
                                code="POLICY_CHANGED", reason="not eligible: cross-purpose isolation", reply=None)); continue
        pcd = int(ALLOCATION_CONFIG.get("pair_cooldown_days") or 0)   # §11.1 general same-pair repeat cooldown (0 = off)
        if pcd > 0 and any(now_ts - t < pcd * 86400 for t in ((SESSION.get("_proposals") or {}).get(nm) or [])):
            decided.append(dict(c, agree=False, decided=True, readiness="pair_cooldown",
                                reason="same-pair cooldown (proposed within %d days)" % pcd, reply=None)); continue
        if not _outreach_ok(intent, live):                     # tier/consent: no personal proposal at T2-no-consent / T3+
            decided.append(dict(c, agree=False, decided=True, readiness="discovery_only",
                                reason="discovery only — needs broad consent for this match", reply=None)); continue
        if CORE_V2:
            domain = _core.infer_domain(intent, cat_of)
            rdy = _core.readiness_state(live, domain, now_ts, _CORE_CFG, received.get(nm, 0))
        else:
            rdy = 'open_now' if live.get('open') else ('paused' if live.get('paused') else 'busy')
        if rdy != 'open_now':
            label = _core.READINESS_LABELS.get(rdy, (rdy, rdy)) if CORE_V2 else (rdy, rdy)
            d = dict(c); d.update({"agree": False, "decided": True, "readiness": rdy,
                                   "reason": label[1], "reply": None})
            decided.append(d)
            continue
        pol_ok, pol_why = _receiving_send_gate(intent, live, now_ts)    # §4.4 extended receiving fields
        if not pol_ok:
            decided.append(dict(c, agree=False, decided=True, readiness="policy_capped",
                                reason=pol_why, reply=None)); continue
        tf_ok, tf_why = _time_feasible(intent, live, now_ts)   # §8.4 slot feasibility (absent-permissive)
        if not tf_ok:
            decided.append(dict(c, agree=False, decided=True, readiness="time_infeasible",
                                reason=tf_why, reply=None)); continue
        if sent >= cap:
            d = dict(c); d.update({"agree": False, "decided": True, "readiness": rdy,
                                   "reason": "queued for the next wave (parallel-proposal cap)",
                                   "reply": None})
            decided.append(d)
            continue
        sent += 1
        # the negotiating agent must reason over the LIVE profile, not the client's stale copy —
        # fill interests/vibe/open/dealBreakers from the store when the client didn't send them
        merged = dict(c, readiness=rdy)
        for k in ("interests", "vibe", "open", "dealBreakers"):
            if merged.get(k) is None and live.get(k) is not None:
                merged[k] = live[k]
        to_send.append(merged)
    # §13.1/§13.2: stamp the typed action (string) + detail + wave ADDITIVELY (new keys only — never touches
    # name/agree/reason/readiness/reply, membership or order, so NEG1-4 / C4-SEND1 stay byte-identical).
    for _c, _ints in ((to_send, True), (decided, False)):
        for c in _c:
            ta = kp.type_action(c, _ints)
            c["action"], c["action_detail"], c["wave"] = ta["action"], ta, kp.assign_wave(c, wctx)
    return to_send, decided

# ---- §8.2 revalidation checkpoints + §8.4 time / reveal-ladder (read-only; reuse the same gate stack) ----
def _to_utc_min(win, key):
    """Minutes-since-midnight in UTC for a 'HH:MM' + tz_offset_min window field. None if unreadable."""
    try:
        hh, mm = str(win.get(key)).split(":")[:2]
        return (int(hh) * 60 + int(mm) - int(win.get("tz_offset_min", 0))) % 1440
    except Exception:
        return None

def _time_feasible(intent, live, now_ts):
    """§8.4 slot feasibility with a travel buffer. ABSENT-PERMISSIVE: only gates when BOTH sides carry a
    window (no fixture does -> no-op -> byte-safe). UTC-normalized by each side's tz_offset_min. PARTIAL:
    no DST table / travel-mode routing (infra)."""
    iw = intent.get("window") or {}
    cw = live.get("availability") or {}
    if not (iw.get("from") and cw.get("from")):
        return True, None
    a0, a1, b0, b1 = _to_utc_min(iw, "from"), _to_utc_min(iw, "until"), _to_utc_min(cw, "from"), _to_utc_min(cw, "until")
    if None in (a0, a1, b0, b1):
        return True, None
    overlap = min(a1, b1) - max(a0, b0)
    need = int(iw.get("min_duration_min") or 0) + int(intent.get("travel_buffer_min") or 0)
    if overlap < max(need, 1):
        return False, "no feasible time slot"
    return True, None

def _revalidate_disclosure(intent, live, checkpoint):
    """§8.2 #6 / §8.4 disclosure ladder: exact place/contact revealed ONLY at 'full' stage AND after a
    mutual-accept Match Capsule exists (mutual consent). Clamped by the candidate's receiving.disclosure_stage."""
    req = _REVEAL_STAGE.get(checkpoint, "limited_profile")
    cand_stage = (live.get("receiving") or {}).get("disclosure_stage")
    allowed = kc._min_disclosure(req, cand_stage) if cand_stage else req
    nm = str(live.get("name", "")).strip().lower()
    mutual = any(nm in {str(p).strip().lower() for p in (m.get("participants") or [])} for m in _match_capsules())
    reveal_ok = (allowed == "full") and mutual
    return {"requested": req, "allowed": allowed, "exact_place_ok": bool(reveal_ok),
            "reason": None if reveal_ok else "exact place/contact requires mutual accept (Match Capsule) + full disclosure"}

def revalidate(intent, candidate, checkpoint="profile_open", now_ts=None):
    """§8.2 #3-#7: re-decide ONE (intent, candidate) pair against the LIVE store at a checkpoint, reusing the
    exact retrieval/send gate stack. Read-only. code == 'POLICY_CHANGED' iff the live re-decision is STRICTER
    than the caller's last-seen baseline — so a caller never silently continues an old transaction (§8.2)."""
    now_ts = now_ts or time.time()
    checkpoint = checkpoint if checkpoint in _REVAL_CHECKPOINTS else "profile_open"
    cand = candidate or {}
    nm = str(cand.get("name", "")).strip().lower()
    store = {str(u.get("name", "")).strip().lower(): u for u in load_candidates()}
    live = dict(store.get(nm, cand)); live["name"] = live.get("name") or cand.get("name") or ""
    gate_ctx, _ = _gate_ctx_and_self({})
    decision, why = _policy_decision(intent, live, gate_ctx)
    domain = _core.infer_domain(intent, cat_of) if CORE_V2 else None
    rdy = (_core.readiness_state(live, domain, now_ts, _CORE_CFG, _proposals_received_24h().get(nm, 0))
           if CORE_V2 else ("open_now" if live.get("open") else "busy"))
    base_dec, base_rdy = str(cand.get("policy") or "ALLOW").upper(), str(cand.get("readiness") or "open_now")
    changed = (_DEC_RANK.get(decision, 0) > _DEC_RANK.get(base_dec, 0)
               or (base_rdy == "open_now" and rdy != "open_now"))
    disclosure = _revalidate_disclosure(intent, live, checkpoint)
    out = {"checkpoint": checkpoint, "name": live["name"], "decision": decision, "readiness": rdy,
           "disclosure": disclosure,
           "allocation_action": _allocation_action({"policy": decision,
                                                     "can_outreach": (decision == "ALLOW" and rdy == "open_now")})}
    out["code"], out["reason"] = ("POLICY_CHANGED", (why or "no longer open (%s)" % rdy)) if changed else ("OK", why)
    return out

# ---- §14 additive transaction stamps on a negotiation card (never touch agree/reason/readiness/name) ----
def _stamp_txn(card, race_case):
    """§14.4: attach the coarse race outcome to a card and move its proposal state. PUBLIC-SAFE — only the
    opaque public_reason is carried (no granular gate reason leaks into a cross-agent surface)."""
    p = card.get('proposal') or {}
    r = ks.resolve_race(race_case, p.get('state'))
    card['txn'] = {"error_code": r["error_code"], "public_reason": r["public_reason"],
                   "state": r["to"], "leak": r["leak"]}
    if card.get('proposal') and r.get('applied'):
        card['proposal']['state'] = r['to']
        card['proposal']['version'] = int(card['proposal'].get('version', 1)) + 1
    return card

def _stamp_accept(card):
    """§14.1: a winning accept moves the proposal SENT->ACCEPTED (+version) and records a MUTUAL match state.
    Pure metadata for the transaction view; leaves agree/reason/readiness/name untouched."""
    p = card.get('proposal')
    if p is not None:
        ks.apply_transition(p, 'proposal', 'ACCEPTED')     # SENT->ACCEPTED (+version bump); no-op if not SENT
    card['match_state'] = 'MUTUAL' if ks.can_transition('match', 'PENDING_DISCLOSURE', 'MUTUAL') else 'PENDING_DISCLOSURE'
    card['txn'] = {"error_code": "OK", "public_reason": None, "state": (card.get('proposal') or {}).get('state'),
                   "leak": False}
    return card

def negotiate_candidates(intent, cands):
    top = cands[:5]
    to_send, decided = _negotiate_precheck(intent, top)
    snap = _request_snapshot(intent)
    for c in to_send:
        _log_proposal(c.get('name'))                   # a real proposal reaches this person's agent
        _log_exposure(c.get('name'))                   # §11.1 impression log (send boundary; not in match_candidates)
        _record_outcome(c.get('name'), 'proposed')     # §1 outcome lifecycle: a proposal went out
        c['proposal'] = kc.build_proposal(intent, c)   # §4.7 structured proposal (idempotency + disclosure clamp)
        c['proposal']['state'] = ks.next_state('proposal', 'CREATED', 'PROPOSE_CONNECTION') or 'SENT'  # §14.1 CREATED->SENT
        c['envelope'] = kp.build_envelope(c['proposal'], snap, purpose=(intent.get('goal') or {}).get('purpose'),
                                          disclosure=c['proposal'].get('allowed_disclosure'),
                                          action="PROPOSE_CONNECTION", structured_fields=c['proposal'].get('payload'),
                                          rendering_key="proposal.propose_connection")   # §13.1 typed message envelope
    def work(c):
        v = negotiate_one(intent, c); c = dict(c); c.update(v); return c
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            done = list(ex.map(work, to_send))
    except Exception:
        done = [dict(c, **negotiate_one(intent, c)) for c in to_send]
    active_plans = [{"window": m.get("plan_window")} for m in _match_capsules()]   # §13.3 conflicting-plan guard input
    accept_policy = ks.concurrent_accept_policy(intent)   # §14.3 how simultaneous accepts resolve (default: multiple)
    for c in done:                                     # B's agent accepted -> §8.2 #4 re-gate at accept, then match
        c['action'] = kp.map_decision_to_action(c)     # §13.1 LLM decision -> typed ACCEPT/DECLINE/COUNTER_*
        if c.get('agree'):
            with _STORE_LOCK:                          # §14: revalidate + slot-claim + record under ONE reentrant lock
                rv = revalidate(intent, c, "accept")
                if rv.get("code") == "POLICY_CHANGED": # policy flipped between propose and accept -> don't match
                    c['agree'] = False; c['decided'] = True; c['code'] = "POLICY_CHANGED"; c['action'] = "DECLINE"
                    c['readiness'] = rv.get("readiness")
                    c['reason'] = "policy changed before accept: %s" % (rv.get("reason") or "")
                    _stamp_txn(c, "policy_revoked_before_accept")   # §14.4 proposal -> POLICY_REVOKED (coarse public reason)
                    continue
                # §13.3 autonomy boundaries — the agent may NOT auto-confirm payment/booking/venue or a conflicting plan
                g1_ok, g1 = kp.guard_no_payment_booking_venue_confirm(c.get('envelope'))
                g2_ok, g2 = kp.guard_no_conflicting_plans(c.get('name'), active_plans, intent.get('window'))
                if not (g1_ok and g2_ok):
                    c['agree'] = False; c['decided'] = True; c['code'] = "NEEDS_CONSENT"
                    c['action'] = "DECLINE"; c['reason'] = g1 or g2
                    continue
                # §14.3 exclusivity: a 1:1 fixed-time intent has ONE slot — the first accept wins, a later
                # concurrent accept is WITHDRAWN (SLOT_TAKEN) and is NOT recorded as accepted (no coexisting match).
                if accept_policy.get("exclusive") and accept_policy.get("policy") == "one_to_one_fixed_time":
                    iid = (c.get('proposal') or {}).get('intent_id')
                    slot = ks.claim_slot(SESSION.setdefault('_match_taken', {}), iid, str(c.get('name') or '').lower())
                    if not slot.get("won"):
                        c['agree'] = False; c['decided'] = True; c['code'] = "SLOT_TAKEN"; c['action'] = "WITHDRAW"
                        c['reason'] = "slot unavailable"
                        _stamp_txn(c, "slot_taken")     # proposal -> WITHDRAWN; loser skipped below (must-fix 4)
                        continue
                # §14.3 dating: manual confirmation required — the agent may NOT auto-commit a match on B's accept;
                # it is HELD pending an explicit user confirm (no _record_outcome / no _stamp_accept, agree preserved).
                if accept_policy.get("auto_commit") is False and accept_policy.get("policy") == "dating_manual_confirm":
                    c['decided'] = True; c['code'] = "NEEDS_MANUAL_CONFIRM"
                    c['manual_confirm_required'] = True
                    continue
                _record_outcome(c.get('name'), 'accepted')   # winner keeps the UNCHANGED accepted path (byte-identical)
                _stamp_accept(c)                        # §14.1 proposal SENT->ACCEPTED, match state MUTUAL (additive)
    by = {str(x.get('name', '')).strip().lower(): x for x in done + decided}
    return [by.get(str(c.get('name', '')).strip().lower(), c) for c in top]

def agent_transition(body):
    """§14 single VALIDATED transition surface for WITHDRAW/EXPIRE/COUNTER/etc. Stateless over the object the
    caller passes (the pilot has no cross-request proposal store — that is blocked_infra; here the caller round-
    trips the object). Deny-safe: an illegal edge -> ILLEGAL_TRANSITION (object untouched); a stale
    expected_version -> VERSION_CONFLICT; a replayed idempotency_key -> the stored prior result (DUPLICATE, no
    re-apply). On success appends an immutable audit trace + outbox row. Clock-free -> fully replay-deterministic."""
    body = body or {}
    entity = str(body.get("entity") or "proposal").lower()
    obj = dict(body.get("object") or {})
    if body.get("state") is not None and obj.get("state") is None:
        obj["state"] = body.get("state")
    action = body.get("action")
    cur = obj.get("state") or ks.initial_state(entity)
    to = body.get("to") or (ks.next_state(entity, cur, action) if action else None)
    expected = body.get("expected_version")
    idem = body.get("idempotency_key")
    eid = obj.get("proposal_id") or obj.get("match_id") or obj.get("intent_id") or obj.get("reservation_id") or ""
    with _STORE_LOCK:
        seen = SESSION.setdefault("_txn_seen", {})
        key = ks.dedup_key(entity, eid, action or to or "", extra=idem)
        if key in seen:                               # replayed notification -> prior result, no re-apply
            return dict(seen.get(key) or {}, duplicate=True, error_code="DUPLICATE")
        if to is None:
            res = {"ok": False, "error_code": "ILLEGAL_TRANSITION", "state": cur,
                   "reason": "no legal target for action %r from %r" % (action, cur)}
        elif expected is not None:
            res = ks.compare_and_swap(obj, entity, to, expected)
        else:
            res = ks.apply_transition(obj, entity, to)
        res = dict(res); res.setdefault("state", obj.get("state", cur)); res["entity"] = entity; res["object"] = obj
        if res.get("ok"):
            SESSION.setdefault("_trace", []).append({"entity": entity, "from": cur, "to": res.get("state"),
                                                     "version": res.get("version"), "action": action, "id": eid})
            SESSION.setdefault("_outbox", []).append({"entity": entity, "state": res.get("state"), "id": eid})
            seen[key] = res                           # memoize ONLY an applied transition; a replay returns it verbatim.
            _save_store()                             # a failed edge/CAS has no side effect -> not memoized, so a
        return res                                    # corrected retry (new expected_version) is never wedged as DUPLICATE.

# ---------------------------------------------------------------- §21.2 proposal / plan resource endpoints
def proposal_create(body):
    """§21.2 POST /proposals — build + STORE a proposal (file-backed SESSION['_proposal_store'], keyed by the
    §4.7 idempotency_key). A repeat with the same (intent, candidate) returns the SAME proposal_id (no dup row)."""
    intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
    cand = body.get("candidate") if isinstance(body.get("candidate"), dict) else {}
    prop = kc.build_proposal(intent, cand)
    with _STORE_LOCK:
        store = SESSION.setdefault("_proposal_store", {})
        idem = prop.get("idempotency_key")
        if idem in store:
            return {"proposal_id": store[idem]["proposal_id"], "proposal": store[idem], "duplicate": True}
        prop["state"] = ks.next_state("proposal", "CREATED", "PROPOSE_CONNECTION") or "SENT"
        store[idem] = prop
        SESSION.setdefault("_proposal_by_id", {})[prop["proposal_id"]] = idem
        _save_store()
    return {"proposal_id": prop["proposal_id"], "proposal": prop}

def proposal_respond(body):
    """§21.2 POST /proposals/{id}/respond — load the stored proposal by id and drive a validated §14 transition
    (VERSION_CONFLICT on a stale expected_version, DUPLICATE on a replayed idempotency_key). Persists the result."""
    pid = body.get("proposal_id")
    with _STORE_LOCK:
        idem = (SESSION.get("_proposal_by_id") or {}).get(pid)
        obj = (SESSION.get("_proposal_store") or {}).get(idem)
    if obj is None:
        return {"ok": False, "error_code": "NOT_FOUND"}
    res = agent_transition({"entity": "proposal", "object": dict(obj), "action": body.get("action"),
                            "expected_version": body.get("expected_version"), "idempotency_key": body.get("idempotency_key")})
    if res.get("ok") and isinstance(res.get("object"), dict):
        with _STORE_LOCK:
            (SESSION.get("_proposal_store") or {})[idem] = res["object"]; _save_store()
    return res

def plan_resource(body):
    """§21.2 POST /plans — create/update a plan resource with the version-checked §14 transition path. The Plan
    state machine stays pilot-off (kc.build_plan enabled:False); this is the additive resource wiring only."""
    pid = body.get("plan_id")
    with _STORE_LOCK:
        store = SESSION.setdefault("_plan_store", {})
        if not pid or pid not in store:                       # create
            plan = kc.build_plan(body.get("time_block"), body.get("place") or body.get("place_or_room"),
                                 body.get("participants") or [])
            plan["state"] = ks.initial_state("plan"); plan["version"] = 1
            store[plan["plan_id"]] = plan; _save_store()
            return {"plan_id": plan["plan_id"], "plan": plan, "created": True}
        obj = store[pid]
    res = agent_transition({"entity": "plan", "object": dict(obj), "to": body.get("to"),
                            "action": body.get("action"), "expected_version": body.get("expected_version")})
    if res.get("ok") and isinstance(res.get("object"), dict):
        with _STORE_LOCK:
            SESSION.setdefault("_plan_store", {})[pid] = res["object"]; _save_store()
    return res

# ---------------------------------------------------------------- §1/§17/§18/§21/§23 additive orchestration helpers
_DATING_REDACT = {"not open to dating": "no longer available", "private profile": "no longer available",
                  "not verified": "no longer available"}
def _redact_dating_reason(reason, domain=None):
    """§17.1 explanation — a sensitive dating reason is NEVER surfaced to a non-owner; it is mapped to a coarse
    public reason. Outside the dating domain the reason is unchanged (owner-only surfaces keep the detail)."""
    return _DATING_REDACT.get(str(reason or ""), reason) if str(domain or "") == "dating" else reason

def merge_conditions(intent_a, intent_b):
    """§1.1 intent_to_intent — merge two overlapping intents: topics ∩, shared time, role pair. feasible iff a
    shared topic exists. Additive, deterministic; the reciprocity join uses this to form a mutual condition."""
    a, b = intent_a or {}, intent_b or {}
    ta = set(str(t).lower() for t in a.get("topics") or [])
    tb = set(str(t).lower() for t in b.get("topics") or [])
    topics = sorted(ta & tb)
    return {"topics": topics, "feasible": bool(topics), "roles": [a.get("role"), b.get("role")],
            "time": a.get("time") if a.get("time") == b.get("time") else None}

def coordinate_plan(intent_a, intent_b):
    """§21.1 Plan Coordinator — from two overlapping intents pick a concrete time_block + public place and return
    a kc.build_plan object (pilot-off, enabled:False). Compute only; persistence is infra."""
    m = merge_conditions(intent_a, intent_b)
    if not m["feasible"]:
        return {"plan": None, "feasible": False, "reason": "no shared topic"}
    tb = m.get("time") or (intent_a or {}).get("time") or "Flexible"
    place = (intent_a or {}).get("place") or "Public place nearby"
    parts = [((intent_a or {}).get("identity") or {}).get("user_id") or "a",
             ((intent_b or {}).get("identity") or {}).get("user_id") or "b"]
    return {"plan": kc.build_plan(tb, place, parts), "feasible": True, "shared_topics": m["topics"]}

def confirm_completion(name, uid="me", party="a", now=None):
    """§1.0b — a COMPLETED interaction needs TWO-SIDED confirmation. Records each party's confirm; completed_ts is
    set ONLY when BOTH sides confirm. Silence by one side never marks completion (never a negative)."""
    key = str(name or "").strip().lower()
    with _STORE_LOCK:
        cc = SESSION.setdefault("_completion_confirms", {}).setdefault(key, {})
        cc[str(party)] = True
        both = bool(cc.get("a") and cc.get("b"))
        if both:
            m = SESSION.setdefault("_matches", {}).setdefault(key, {"name": key, "matched_ts": None, "completed_ts": None})
            if not m.get("completed_ts"):
                m["completed_ts"] = float(now if now is not None else time.time())
        _save_store()
    return {"name": key, "confirms": dict(cc), "completed": both}

def match_capsule_disclosed(participant_users, purpose, disclosure_stage="match_only"):
    """§21.1 Match Capsule Builder — a per-participant purpose-bound disclosed ProfileView (a dating capsule omits
    'entities'; a friendship capsule omits 'datingOk'), respecting the disclosure stage."""
    return [kc.build_profile_view(u, purpose, disclosure_stage) for u in participant_users or []]

def _decision_trace(card, intent, snapshot):
    """§21.3 — a unified auditable decision trace per card (search/candidate/purpose ids + policy & model versions;
    scoring is rule-based deterministic, the LLM is parse-only). Deterministic."""
    snap = snapshot or {}
    return {"search_id": kc._det_id("srch", snap.get("intent_id"), snap.get("data_version")),
            "candidate_id": kc._det_id("cand", str((card or {}).get("name") or "").lower()),
            "purpose_id": ((intent or {}).get("goal") or {}).get("purpose") or snap.get("decision_type"),
            "policy": {"version": snap.get("policy_version")},
            "model_versions": {"scoring": "rule_based_deterministic", "llm": "parse_only"},
            "config_version": snap.get("config_version")}

def _append_run_trace(snapshot):
    """§23.4.8 — append each run's snapshot trace to a bounded SESSION['_run_traces'] (file-backed), so a fixture
    run leaves a retrievable decision trace. Bounded to the last 200."""
    with _STORE_LOCK:
        rt = SESSION.setdefault("_run_traces", [])
        rt.append({"intent_id": (snapshot or {}).get("intent_id"),
                   "intent_version": (snapshot or {}).get("intent_version"),
                   "config_version": (snapshot or {}).get("config_version")})
        del rt[:-200]
        _save_store()
    return len(SESSION.get("_run_traces") or [])

def _search_pipeline(intent, cards):
    """§B.1 — a read-only provenance-tier walk over the already-labelled slate (accumulate under the high retrieval
    budget so nothing is cut). Returns the SAME cards (byte-identical) + a trace; never re-scores or drops anyone."""
    by_tier = {}
    for c in cards or []:
        by_tier[str(c.get("tier") or "T?")] = by_tier.get(str(c.get("tier") or "T?"), 0) + 1
    strong = sum(v for k, v in by_tier.items() if k in ("T0", "T1"))
    return {"cards": list(cards or []), "trace": {"tiers": by_tier, "strong_count": strong,
            "enough_strong": strong >= 1, "budget": RETRIEVAL_BUDGET.get("structured", 500),
            "used": len(cards or []), "broke_early": len(cards or []) < RETRIEVAL_BUDGET.get("structured", 500)}}

_DOMAIN_LADDER = {
    "games": ["exact game/role", "parent genre", "room with consent"],
    "walk": ["same area/time", "another zone/time", "small group"],
    "language_exchange": ["exact pair/role", "group practice", "event"],
    "professional_networking": ["exact role/industry", "adjacent role", "curated group/event"],
}
def domain_ladder(intent):
    """§18.1 — the per-domain typical fallback ordering (read-only plan; the generic ladder still executes)."""
    return list(_DOMAIN_LADDER.get(_core.infer_domain(intent, cat_of),
                                   ["broaden topic", "widen zone/time", "alternative"]))

def compile_endpoint(body):
    """§21.2 POST /intents/compile — ONE object folding parse + compile + clarification + snapshot so a caller
    gets {intent, draft, slots, clarification, minimally_sufficient, snapshot} in a single round-trip."""
    q = body.get("query") or ""
    intent = parse_intent(q) if q else (body.get("intent") if isinstance(body.get("intent"), dict) else {})
    ctx = body.get("ctx") if isinstance(body.get("ctx"), dict) else {}
    intent = kc.compile_intent(intent, _intent_identity(intent), ctx, ctx.get("now") or time.time())
    add = _section5_addendum(intent, q, [])
    return {"intent": intent, "draft": intent, "slots": intent.get("topics"),
            "intent_summary": add.get("intent_summary"), "clarification": add.get("clarification"),
            "minimally_sufficient": add.get("minimally_sufficient"), "snapshot": _request_snapshot(intent)}

def expand_one_axis(body):
    """§21.2 POST /searches/{id}/expand — apply EXACTLY ONE declared expansion axis (never the two _expand_fallback
    relaxes together); safety/age/consent stay fixed. Returns {axis, candidates, ladder_step, explanation}."""
    intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
    prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
    ctx = body.get("ctx") if isinstance(body.get("ctx"), dict) else {}
    axis = str(body.get("axis") or "adjacent")
    _AXIS = {"adjacent": {"adjacentAllowed": True}, "parent": {"broadAllowed": True},
             "exactness": {"exactMatchRequired": False},
             "radius": {"radiusKm": (intent.get("radiusKm") or 15) * 2}}
    relaxed = dict(intent, **_AXIS.get(axis, {}))
    return {"axis": axis, "changed_keys": list(_AXIS.get(axis, {}).keys()),
            "candidates": match_candidates(relaxed, prof, ctx),
            "ladder_step": {"adjacent": 2, "parent": 3, "exactness": 2, "radius": 4}.get(axis),
            "explanation": "Expanded by a single axis: %s (safety/age/consent unchanged)" % axis}

# ---------------------------------------------------------------- Explore: public plans near the owner
# The client's Explore map used to hard-code 5 fake plans. Serve real ones instead: every candidate who
# carries an OPEN own-intent becomes a public plan (title from ENTITY_MAP, distance from their geo). Draws
# from load_candidates() so it honours the store, and returns [] when nobody is posting — the client then
# shows an empty state instead of invented pins.
_INACTIVE_INTENT_STATUSES = frozenset({
    "archived", "cancelled", "canceled", "completed", "declined", "draft",
    "expired", "failed", "paused", "withdrawn",
})


def _public_intents(candidate):
    """Yield only actual active intents. Interests alone are not public plans."""
    for intent in candidate.get("intents") or []:
        if not isinstance(intent, dict) or intent.get("open") is False:
            continue
        status = str(intent.get("status") or "active").strip().lower()
        if status in _INACTIVE_INTENT_STATUSES:
            continue
        topics = [
            str(topic).strip().lower()
            for topic in (intent.get("topics") or intent.get("tags") or [])
            if str(topic).strip()
        ]
        if topics:
            yield intent, topics[:3]



def _saved_public_intents():
    """Yield persisted intents with their owner (подпись, id), preserving only stored facts."""
    for row in list(SESSION.get("_intents") or []):
        if not isinstance(row, dict):
            continue
        owner = str(row.get("owner") or "").strip()
        raw = row.get("intent")
        if not owner or not isinstance(raw, dict):
            continue
        intent = dict(raw)
        if row.get("id") is not None:
            intent.setdefault("id", row.get("id"))
        if row.get("title"):
            intent.setdefault("title", row.get("title"))
        if row.get("status"):
            intent.setdefault("status", row.get("status"))
        for public_intent, topics in _public_intents({"intents": [intent]}):
            yield owner, str(row.get("owner_id") or ""), public_intent, topics


def _viewer_candidate(profile):
    """Convert a client profile to the candidate shape expected by policy gates."""
    profile = profile if isinstance(profile, dict) else {}
    raw_interests = profile.get("interests") or []
    interests = [
        str(item.get("name") if isinstance(item, dict) else item).strip().lower()
        for item in raw_interests
        if str(item.get("name") if isinstance(item, dict) else item).strip()
    ]
    languages = profile.get("languages") if isinstance(profile.get("languages"), dict) else {}
    return {
        "name": str(profile.get("name") or "viewer"),
        "age": profile.get("age"),
        "gender": profile.get("gender"),
        "interests": interests,
        "langs": profile.get("langs") or languages.get("comfortable") or [],
        "verified": bool(profile.get("verified") or profile.get("ageVerified18")),
        "pending": 0,
        "intents": profile.get("intents") or [],
    }


def _potential_fit(intent, topics, viewer):
    """Require topical relevance and permission from the plan owner's hard gates."""
    if not viewer or not viewer.get("interests"):
        return False
    decision, _ = _policy_decision(intent, viewer, {"blocked": set(), "feedback": {}}, _CORE_CFG)
    if decision != "ALLOW":
        return False
    best, _ = topical(topics, viewer["interests"])
    if best <= 0:
        return False
    if best == 1 and intent.get("adjacentAllowed") is False:
        return False
    if best < 4 and intent.get("exactMatchRequired"):
        return False
    return True


def explore_plans(limit=12, self_name="", viewer_profile=None, self_id=""):
    sn = str(self_name or "").strip().lower()
    users = [c for c in load_candidates() if not _is_self(c, self_id, sn)]
    # Seed users exist only to keep matching non-empty. They are never public content.
    ordered = [c for c in users if c.get("source") == "onboarding"]
    owners = {
        str(c.get("name") or "").strip().lower(): c
        for c in ordered
        if str(c.get("name") or "").strip()
    }
    viewer = _viewer_candidate(viewer_profile) if viewer_profile is not None else None
    out = []
    seen = set()
    # A plan card shows a PERSON, so it carries their face. Resolved by name as well as off the row:
    # a saved intent builds a synthetic candidate ({name, source, open}) that has no photo on it,
    # and that owner is a real person with a real photo.
    photos = _photo_by_name()

    def append_plan(c, intent, topics):
        intent_id = intent.get("id") or intent.get("intent_id")
        if intent_id and intent_id in seen:
            return
        # Свидание в открытую витрину не попадает — то же правило, что у ленты карты (imf.is_dating).
        if imf.is_dating(intent):
            return
        if _core.is_paused(c) or c.get("open") is False:
            return
        if viewer is not None and not _potential_fit(intent, topics, viewer):
            return
        km = c.get("km")
        plan = {
            "intentId": intent_id,
            "title": intent.get("title") or ENTITY_MAP.get(topics[0]) or (topics[0].capitalize() + " meetup"),
            "who": c.get("name") or "Someone",
            # id автора: отклик на затею зовёт его по id — у тёзок подписи равны (docs/IDENTITY.md)
            "who_id": str(c.get("id") or ""),
            "age": c.get("age"),
            "topics": topics,
            "role": intent.get("role") or "meet",
            "when": intent.get("when") or intent.get("time") or "",
            "area": intent.get("area") or intent.get("place") or c.get("city") or "",
            "verified": bool(c.get("verified")),
        }
        photo = c.get("photo") or (_photo_of(c.get("id")) if c.get("id") else
                                   photos.get(str(c.get("name") or "").strip().lower()))
        if photo:
            plan["photo"] = photo
        if km is not None:
            try:
                plan["dist"] = round(float(km), 1)
            except (TypeError, ValueError):
                pass
        # Координата ВСТРЕЧИ важнее координаты автора. Место человек назвал сам, когда заводил
        # интент; точка автора — это его район из профиля, одна на все его интенты. Пока брали
        # только её, карта поиска сводила все встречи города в одну булавку: замерено на живой
        # выдаче — двенадцать интентов на три точки, девять из них в запасном центре.
        # КООРДИНАТА ЗАТЕИ, А НЕ АВТОРА, И ТОЧНАЯ.
        #
        # Разница между двумя видами точки, и она принципиальна. Домашняя точка человека и метка,
        # которую он ставит в профиле, огрублены и такими остаются: geo_privacy держит их закрытыми,
        # и правильно. Адрес встречи — другое: человек называет его САМ и именно для того, чтобы
        # туда пришли. Прятать площадку значит сделать карту бесполезной — по зоне в полкилометра
        # на встречу не придёшь.
        #
        # Сюда попадает только адрес: клиент кладёт lat/lon в затею лишь когда их дал выбранный
        # адрес (`venue`), а булавка карты радиуса — «ищи вокруг вон той точки» — уезжает в профиль
        # поиска и на карту не идёт. Запасной вариант ниже — координаты автора из его строки, они
        # уже огрублены онбордингом.
        p_lat = intent.get("lat") if intent.get("lat") is not None else c.get("lat")
        p_lon = intent.get("lon") if intent.get("lon") is not None else c.get("lon")
        if p_lat is not None and p_lon is not None:
            plan["lat"], plan["lon"] = p_lat, p_lon
        out.append(plan)
        if intent_id:
            seen.add(intent_id)

    for c in ordered:
        for intent, topics in _public_intents(c):
            append_plan(c, intent, topics)

    by_id = {str(c.get("id")): c for c in ordered if c.get("id")}
    for owner, owner_id, intent, topics in _saved_public_intents():
        owner_key = owner.lower()
        if self_id and owner_id:
            if owner_id == self_id:
                continue
        elif sn and owner_key == sn:
            continue
        candidate = (by_id.get(owner_id) if owner_id else owners.get(owner_key)) or {
            "name": owner,
            "source": "saved_intent",
            "open": True,
        }
        append_plan(candidate, intent, topics)

    out.sort(key=lambda p: (
        p.get("dist") is None,
        p.get("dist", 0),
        str(p.get("title") or "").lower(),
    ))
    return out[:limit]


# ---------------------------------------------------------------- Map feed: two privacy-distinct intent projections
def map_feed_payload(view="offline", self_name="", limit=60, self_id=""):
    users = load_candidates()
    _ensure_intent_owner_ids()
    # У группы `owner` — id организатора; ленте нужна подпись и id отдельно.
    gis = [dict(g, owner=_display(g.get("owner"), str(g.get("owner") or "")),
                owner_id=_canon_pid(g.get("owner")))
           for g in (SESSION.get("_gintents") or []) if isinstance(g, dict)]
    return imf.build_feed(
        imf.collect_sources(users, SESSION.get("_intents") or [], gis,
                            self_name=self_name, self_id=self_id),
        view=view,
        limit=limit,
        geocoder=_MAP_GEOCODER,
        geocode_budget=int(os.environ.get("KLEAL_MAP_GEOCODE_BUDGET", "4")),
    )


def _prepare_map_intent(owner, intent, owner_id=""):
    profile = imf.owner_profile_for(load_candidates(), owner, owner_id)
    return imf.prepare_persisted_intent(intent, profile, _MAP_GEOCODER)


# ---------------------------------------------------------------- explain: full diagnostic of one search
# Mirrors core_v2.search() decision-for-decision, but CLASSIFIES every pool candidate instead of silently
# dropping it — so a matching test panel can show who matched and why, who was gated out (and the gate),
# and who was considered-but-filtered — plus the per-feature-group breakdown behind each score.
def _explain_match_engine(intent, prof, ctx=None):
    if not CORE_V2:
        return {"error": "Core v2 disabled (KLEAL_CORE_V2=0) — nothing to explain", "matched": [], "excluded": [], "considered": []}
    ctx = ctx or {}
    intent, prof = intent or {}, prof or {}
    intent = ki.normalize_for_scoring(intent)              # §5: same normalization as match_candidates (PARITY)
    cfg = _CORE_CFG
    domain = _core.infer_domain(intent, cat_of)
    dom_cfg = cfg["domains"].get(domain) or cfg["domains"]["social_meet"]
    W = dom_cfg["weights"]
    lam = float(dom_cfg["uncertainty_lambda"])
    disc_lcb, disc_cov = float(dom_cfg["discovery_min_lcb"]), float(dom_cfg["discovery_min_coverage"])
    out_lcb, out_cov = float(dom_cfg["outreach_min_lcb"]), float(dom_cfg["outreach_min_coverage"])
    priors = {k: (cfg["feature_groups"][k] or {}).get("unknown_prior", 0.5) for k in _core.FEATURE_KEYS}
    bands = cfg["user_facing_bands"]
    topics = [str(t).lower() for t in (intent.get("topics") or [])]
    now_ts = ctx.get("now") or time.time()
    snap_id = _intent_identity(intent)["intent_id"]      # scope for per-feature Evidence (§4.1)
    received24 = ctx.get("received24") or _proposals_received_24h()
    gate_ctx, self_name = _gate_ctx_and_self(ctx, prof)
    prof = _prof_with_own_row(prof, self_name, gate_ctx.get('self_id') or '')  # разбор = выдача

    def _feats(F):
        tw = sum(float(W.get(k, 0) or 0) for k in _core.FEATURE_KEYS if F.get(k, (None,))[0] != _core.NA)
        rows = []
        for k in _core.FEATURE_KEYS:
            st, v, det = F.get(k, (_core.UNKNOWN, None, ""))
            w = float(W.get(k, 0) or 0)
            adj = None if st == _core.NA else (priors[k] if st == _core.UNKNOWN else v)
            contrib = round(w * adj / tw, 4) if (st != _core.NA and tw > 0 and adj is not None) else 0.0
            rows.append({"group": k, "state": st, "value": adj, "weight": round(w, 3),
                         "contribution": contrib, "detail": det})
        return rows

    matched, considered, excluded = [], [], []
    pool = load_candidates()
    for c in pool:
        nm = c.get("name")
        # Ключ счётчика приглашений за сутки — тот же, что у боевого подбора (`received24` строится
        # по нормализованной подписи). Без этой строки разбор выдачи падал NameError на первом же
        # кандидате, прошедшем фильтры (аудит 27.09.2026).
        nm_key = str(nm or "").strip().lower()
        if _is_self(c, gate_ctx.get("self_id") or "", self_name):
            excluded.append({"name": nm, "gate": "self", "reason": "the searcher (you)"}); continue
        decision, why = _policy_decision(intent, c, gate_ctx)     # BLOCK / REVIEW / ALLOW (§0 output table)
        if decision == "BLOCK":
            excluded.append({"name": nm, "gate": "hard", "reason": why}); continue
        if _core.is_paused(c, now_ts):
            excluded.append({"name": nm, "gate": "paused", "reason": "paused / left retrieval"}); continue
        tier = _core.assign_tier(intent, c, topics, _H)
        if tier == "T5":
            considered.append({"name": nm, "tier": "T5", "reason": "no meaningful topical overlap"}); continue
        if tier == "T3" and not intent.get("adjacentAllowed", True):
            considered.append({"name": nm, "tier": tier, "reason": "adjacent excluded (adjacentAllowed off)"}); continue
        if tier == "T2" and intent.get("exactMatchRequired"):
            considered.append({"name": nm, "tier": tier, "reason": "related excluded (exactMatchRequired on)"}); continue
        F = _core.build_features(intent, prof, c, domain, _H, ROLE_CONFLICT)
        d_ab = _core.directional_score(F, dom_cfg, priors)
        d_ba = _core.directional_score(_core.reverse_features(intent, prof, c, domain, _H, ROLE_CONFLICT), dom_cfg, priors)
        rec = _core.reciprocal_score(d_ab, d_ba)
        readiness = _core.readiness_state(c, domain, now_ts, cfg, received24.get(nm_key, 0))
        disc_ok = d_ab["lcb"] >= disc_lcb and d_ab["coverage"] >= disc_cov
        if not disc_ok and tier not in ("T0", "T1"):
            considered.append({"name": nm, "tier": tier,
                               "reason": "below discovery floor (lcb %.2f<%.2f or cov %.2f<%.2f)"
                               % (d_ab["lcb"], disc_lcb, d_ab["coverage"], disc_cov),
                               "lcb": d_ab["lcb"], "coverage": d_ab["coverage"], "reciprocal": rec, "readiness": readiness}); continue
        band = _core.assign_band(d_ab["lcb"], d_ab["coverage"], bands) if disc_ok else "needs_clarification"
        outreach_tier_ok = tier in ("T0", "T1") or (tier == "T2" and bool(intent.get("broadConsent")))
        can_outreach = (outreach_tier_ok and readiness == "open_now" and
                        d_ab["lcb"] >= out_lcb and d_ab["coverage"] >= out_cov)
        if decision == "REVIEW":                                 # discoverable, but the safety/legal track gates outreach
            can_outreach = False
        rs_ru, rs_en, _legacy, gap_ru, gap_en = _core._presentation(F, d_ab, dom_cfg)
        band_lbl = _core.BAND_LABELS.get(band, (band, band))
        rdy_lbl = _core.READINESS_LABELS.get(readiness, (readiness, readiness))
        if can_outreach:
            why_no = None
        elif decision == "REVIEW":
            why_no = why
        elif not outreach_tier_ok:
            why_no = "tier T2 needs broad consent" if tier == "T2" else "tier %s: discovery only (no personal outreach)" % tier
        elif readiness != "open_now":
            why_no = "not open now (%s)" % rdy_lbl[1]
        else:
            why_no = "below outreach floor (lcb %.2f / cov %.2f)" % (d_ab["lcb"], d_ab["coverage"])
        alloc = ("review_required" if decision == "REVIEW" else "propose" if can_outreach else "discovery_only")
        feat_rows = _feats(F)
        # §4.1/§4.2: one Evidence object per KNOWN feature group, provenance from FEATURE_GROUP_SOURCE
        # (not a hardcoded L1); scope-bound to this intent so aliases from one phrase share an evidence_id.
        evidence = [kc.build_evidence(r["group"], r["detail"],
                                      kc.FEATURE_GROUP_SOURCE.get(r["group"], "agent_inference"),
                                      scope="intent:" + snap_id, confidence=r["value"], now=now_ts)
                    for r in feat_rows if r["state"] == "known_match" and r.get("detail")]
        matched.append({
            "name": nm, "tier": tier, "kind": _core.TIER_KIND.get(tier, "related"),
            "policy": decision, "allocation_action": alloc,
            "decision_class": _decision_class({"policy": decision, "tier": tier, "band": band,
                                               "can_outreach": can_outreach, "why_no_outreach": why_no}),  # §9.6
            "probe_unknowns": [u for u, _w in sorted(((u, W.get(u, 0)) for u in d_ab.get("unknowns", [])),
                                                     key=lambda x: -x[1])[:3]],   # §9.6 clarification: top-1-3 unknowns
            "band": band, "band_en": band_lbl[1], "readiness": readiness, "readiness_en": rdy_lbl[1],
            "can_outreach": can_outreach, "reciprocal": rec, "disc_ok": disc_ok,
            "a_to_b": {"mean": d_ab["mean"], "coverage": d_ab["coverage"], "lcb": d_ab["lcb"],
                       "lam": lam, "features": feat_rows},
            "b_to_a": {"mean": d_ba["mean"], "coverage": d_ba["coverage"], "lcb": d_ba["lcb"]},
            "reasons": rs_en, "gap": gap_en, "why_no_outreach": why_no,
            "evidence": evidence, "relationship": _relationship_edge(nm, ctx.get("uid", "me"), scope=domain),
        })
        try:                                              # §6: additive typed-edge + expansion + complementary
            for k, v in kt.enrich_card(topics, c.get("interests") or [],
                                       role_a=intent.get("role"), role_b=c.get("role")).items():
                matched[-1].setdefault(k, v)              # never touches band/tier/lcb/can_outreach/sort keys
            matched[-1].setdefault("retrieval_source", _retrieval_source(intent, c))   # §7.1 source provenance
            matched[-1].setdefault("completion_factors", kcf.completion_factors(c, intent, now_ts, received24.get(nm_key, 0)))  # §10.2
            matched[-1].setdefault("readiness_explain", kcf.READINESS_EXPLAIN.get(readiness))  # §10.1
        except Exception:
            pass
    matched.sort(key=lambda x: (_core.BAND_RANK[x["band"]], _core.READINESS_RANK[x["readiness"]],
                                -x["reciprocal"], -x["a_to_b"]["lcb"], -x["a_to_b"]["coverage"], str(x["name"])))
    slate_cut = _core.TOP_N
    return {
        "domain": domain,
        "domain_config": {"weights": W, "uncertainty_lambda": lam,
                          "outreach_min_lcb": float(dom_cfg["outreach_min_lcb"]),
                          "discovery_min_lcb": float(dom_cfg["discovery_min_lcb"]),
                          "outreach_min_coverage": float(dom_cfg["outreach_min_coverage"]),
                          "discovery_min_coverage": float(dom_cfg["discovery_min_coverage"])},
        "bands": bands, "priors": priors, "slate_cut": slate_cut,
        "matched": matched, "considered": considered, "excluded": excluded,
        "counts": {"pool": len(pool), "matched": len(matched),
                   "considered": len(considered), "excluded": len(excluded),
                   "review": sum(1 for m in matched if m.get("policy") == "REVIEW")},
        "tier_analytics": _tier_analytics(matched),    # §7.1 relevance distribution within each tier
        "retrieval": _retrieval_report(matched),       # §7.2 staged pipeline + §7.1 source provenance
        "snapshot": _request_snapshot(intent),      # §4 immutable per-request version snapshot
        "payment_invariant": PAYMENT_INVARIANT,     # §0 dec.10 / §11.3
    }


def explain_match(intent, prof, ctx=None):
    """Slate diagnostic with the exact same phrase/canonicalization context as real matching."""
    with _matching_topic_context(intent) as effective:
        return _explain_match_engine(effective, prof, ctx)


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# RESTORED: intents, messages/proposals and groups.
#
# The rewrite of this service RENAMED its API surface — propose→proposal, respond→proposal/respond,
# intents/intent-save/intent-delete→saved_searches/save_search/save_search/delete, group-*→group —
# but the profile frontend was never updated, so it kept calling the old names and got 404. Three
# whole screens (My Intents, Messages, Groups) were dead in the shipped build, and the admin panel
# lost 25 of its 87 checks with them.
#
# These handlers are restored verbatim from the pre-rewrite service rather than the frontend being
# repointed at the new names: the payload shapes differ, so aliasing old names onto the new
# handlers would answer 200 with a body the UI cannot read — worse than an honest 404.
#
# This is state-machine and store code (SESSION / kleal_store.json, §14 transactional guarantees
# with idempotency keys and optimistic versions). It does NOT touch the ranking engine, so nothing
# here can change who matches whom.
# ═══════════════════════════════════════════════════════════════════════════════════════════════

# transplanted symbols in dependency order (35):
#   PROPOSAL_TTL_S, _requests, _expire_due, _idem, _idem_get, _idem_put, _norm_name, propose, inbox, outbox, archive_request, _num, _policy_ok_now, respond, withdraw_request, _messages, _pair_key, send_message, thread, threads_for, _intents, save_intent, delete_intent, _normalize_intent, list_intents, _gnorm, _group_state, _group_public, _groups, group_create, group_join, group_leave, _pair_fit, group_utility, group_list

# ---- §14 transactional guarantees ------------------------------------------------------------------
# A proposal used to be a row with a status string: no version, no expiry, no idempotency, and policy
# was checked only when SENDING. So a retry created a duplicate, a three-week-old request was still
# acceptable, and — the real defect — if the recipient paused or blocked the sender between SENT and
# ACCEPT, the accept still went through. §14.2 requires the policy re-check to happen INSIDE the same
# transaction as the acceptance.
PROPOSAL_TTL_S = int(os.environ.get("KLEAL_PROPOSAL_TTL_S", 72 * 3600))   # spec §14.2 reservation TTL
# Спека «01 · Сроки и пороги» → «Срок жизни инвайта»: min(6 ч, 50 % до встречи), но не меньше
# 30 минут. Чип Decided.
#
# Здесь стояли плоские 72 часа, и они не смотрели на время встречи вовсе: приглашение на сегодняшний
# вечер держало место трое суток — то есть ещё двое суток ПОСЛЕ того, как встреча прошла. Половина
# оставшегося времени — честный размен, и спека объясняет почему: получателю хватает на решение, а
# отправителю остаётся столько же на второй заход.
INVITE_TTL_MAX_S = 6 * 3600
INVITE_TTL_MIN_S = 30 * 60


def _invite_ttl(intent, now=None):
    """Сколько живёт приглашение по этому интенту."""
    now = now or time.time()
    starts = None
    if isinstance(intent, dict):
        try:
            starts = float(intent.get("starts_at") or 0) or None
        except (TypeError, ValueError):
            starts = None
    ttl = INVITE_TTL_MAX_S
    if starts and starts > now:
        ttl = min(ttl, (starts - now) / 2.0)
    return max(INVITE_TTL_MIN_S, ttl)

def _requests():
    return SESSION.setdefault("_requests", [])


# ВЫБОР ИЗ ОТВЕТИВШИХ — борд «1:1 · Offline — new layout», раздел A (OF.12d–16, C1a, N1, N2),
# решение владельца 11.10.2026. «Да» приглашённого больше не открывает чат и не гасит соседей:
# заявка становится `answered` («ответил, ждёт выбора»), организатор выбирает одного
# (`pick_request`), тот получает обычное `accepted`, остальным по этой затее — `not_picked`
# («не в этот раз»). Открытая заявка — та, по которой ещё может что-то произойти.
REQ_OPEN = ("pending", "answered")


def _req_same_intent(a, b):
    """Две заявки одного отправителя — про одну затею? По `iid`, а где его нет хотя бы у одной —
    по названию (так же сверяет клиент, src/invites.ts sameIntent, и mp_alternatives)."""
    ia, ib = str(a.get("iid") or "").strip(), str(b.get("iid") or "").strip()
    if ia and ib:
        return ia == ib
    ta = _norm_name((a.get("intent") or {}).get("title"))
    return bool(ta) and ta == _norm_name((b.get("intent") or {}).get("title"))

def _expire_due(now=None):
    """Mark overdue proposals EXPIRED. Called on every read and before every write, so an expired
    proposal can never be accepted (acceptance test #9)."""
    now = now or time.time()
    changed = False
    for r in _requests():
        if r.get("status") == "pending" and (r.get("expires_at") or 0) and now > r["expires_at"]:
            r["status"] = "expired"
            r["updated"] = now
            r["version"] = int(r.get("version") or 1) + 1
            changed = True
        # Организатор не выбрал до срока (`pick_by`): заявка ответившего закрывается БЕЗ последствий
        # для обоих — то же правило молчания, что у плана (06.10.2026). Причина отличима от «не
        # ответил приглашённый»: trace.reason = host_silent.
        elif r.get("status") == "answered" and (r.get("pick_by") or 0) and now > r["pick_by"]:
            r["status"] = "expired"
            r["updated"] = now
            r["version"] = int(r.get("version") or 1) + 1
            r["trace"] = {"decision": "expired", "at": now, "reason": "host_silent"}
            changed = True
    return changed

def _idem():
    return SESSION.setdefault("_idem", {})

def _idem_get(key):
    row = _idem().get(str(key)) if key else None
    return row.get("result") if row else None

def _idem_put(key, result):
    """Same idempotency key -> same answer (spec §14.2, acceptance test #7)."""
    if not key:
        return result
    d = _idem()
    d[str(key)] = {"result": result, "at": time.time()}
    if len(d) > 2000:                                   # bounded; oldest keys fall off
        for k in sorted(d, key=lambda k: d[k].get("at") or 0)[:600]:
            d.pop(k, None)
    return result

# ---- real proposal delivery (was missing entirely) -------------------------------------------------
# Sending a request used to be local: the client posted feedback, asked an LLM to ROLE-PLAY the
# recipient's agent, and showed "мы отправили твой запрос <name>" plus a mutual match based on that
# simulation. Nothing ever reached the other account — logging in as the recipient showed no request.
# These endpoints are the actual delivery: a proposal is stored, the recipient reads and answers it,
# and the sender sees the real answer instead of a generated one.
def _norm_name(n):
    return str(n or "").strip().lower()


def _blocked_pair(a, b):
    """True if either has blocked the other. Checked at every point where one person can reach the
    other — search, invitation, message, plan — because a block that only filters search results
    still leaves every direct route open."""
    na, nb = _norm_name(a), _norm_name(b)
    bl = SESSION.get("_blocks") or {}
    return nb in set(bl.get(na) or []) or na in set(bl.get(nb) or [])

def _chat_exists(a, b):
    """Есть ли у этих двоих переписка: принятая заявка или хоть одна реплика в их ленте.

    Нужно, чтобы отличить ПЕРВОЕ приглашение от второго. У первого вся переписка и есть затея —
    событие о ней было бы пересказом самой ленты, в которой пока ничего нет. У второго иначе: чат
    уже живёт своей жизнью, и новая затея, не оставив следа, исчезает бесследно.
    """
    na, nb = _norm_name(a), _norm_name(b)
    for r in _requests():
        if (r.get("status") == "accepted"
                and {_norm_name(r.get("from")), _norm_name(r.get("to"))} == {na, nb}):
            return True
    key = _pair_key(a, b)
    return any(m.get("pair") == key for m in _messages())


def propose(frm, to, intent, note, idem=None):
    frm, to = str(frm or "").strip(), str(to or "").strip()
    if not frm or not to or _norm_name(frm) == _norm_name(to):
        return {"ok": False, "error": "sender and recipient required and must differ"}
    if _blocked_pair(frm, to):
        return {"ok": False, "error": "BLOCKED"}
    cached = _idem_get(idem)
    if cached is not None:
        return cached                                    # retry-safe: same key, same answer
    now = time.time()
    with _STORE_LOCK:
        _expire_due(now)
        rs = _requests()
        # Человек уже сказал «да» на эту затею и ждёт выбора — повторная отправка ничего не меняет:
        # сбросить его ответ молча было бы хуже, чем честно вернуть то, что есть.
        probe = {"iid": str((intent or {}).get("id") or "")[:64], "intent": intent or {}}
        for r in rs:
            if (r.get("status") == "answered" and _norm_name(r.get("from")) == _norm_name(frm)
                    and _norm_name(r.get("to")) == _norm_name(to) and _req_same_intent(r, probe)):
                return _idem_put(idem, {"ok": True, "id": r["id"], "status": "answered",
                                        "version": r.get("version"), "pick_by": r.get("pick_by")})
        # one open proposal per pair per direction — re-sending updates it rather than stacking
        for r in rs:
            if (_norm_name(r.get("from")) == _norm_name(frm) and _norm_name(r.get("to")) == _norm_name(to)
                    and r.get("status") == "pending"):
                r.update({"intent": intent or {}, "note": str(note or "")[:400], "updated": now,
                          "expires_at": now + _invite_ttl(intent, now),
                          "version": int(r.get("version") or 1) + 1})
                _save_store()
                return _idem_put(idem, {"ok": True, "id": r["id"], "status": "pending",
                                        "version": r["version"], "expires_at": r["expires_at"], "resent": True})
        # The id was time-in-ms + hash(pair), so two proposals for the SAME pair inside one
        # millisecond collided — and every later lookup by id hit whichever row came first.
        base = "rq_%d_%s" % (int(now * 1000), hashlib.sha1((frm + to).encode("utf-8")).hexdigest()[:6])
        taken = {r.get("id") for r in rs}
        rid, n = base, 1
        while rid in taken:
            rid, n = "%s_%d" % (base, n), n + 1
        # `iid` — по какой затее это приглашение. Спека: «Открытых инвайтов НА ИНТЕНТ — 3 · Plus 5»,
        # а считалось по всем затеям человека сразу: просто потому, что заявка не знала, откуда она.
        # Проверено по живому хранилищу — из 32 заявок с затеей id не было ни у одной.
        rs.append({"id": rid, "from": frm, "to": to, "intent": intent or {},
                   "iid": str((intent or {}).get("id") or "")[:64],
                   "note": str(note or "")[:400], "status": "pending", "created": now, "updated": now,
                   "version": 1, "expires_at": now + _invite_ttl(intent, now),
                   "config_version": (_CORE_CFG or {}).get("config_version")})   # immutable trace stamp
        # НОВАЯ ЗАТЕЯ К ТОМУ, С КЕМ УЖЕ ГОВОРИМ, ОБЯЗАНА ОСТАВИТЬ СЛЕД В ЛЕНТЕ.
        #
        # Снято живым опытом на этом же сервере: у пары встреча по первой затее, приходит вторая —
        # и в переписке не меняется НИЧЕГО. Закреплённая полоса сверху занята планом (так и надо:
        # встреча важнее), а другого входа в карточку затеи с этого экрана нет вовсе — полоса либо
        # план, либо затея, третьего не бывает. Человек ищет новую затею и не находит её нигде.
        #
        # Событие несёт КОД и заголовок, а не готовую фразу: двое могут читать приложение на разных
        # языках, и русская строка, собранная здесь, приедет на английский экран (см. _sys_msg).
        if _chat_exists(frm, to):
            _sys_msg(frm, to, "intent_new",
                     title=str((intent or {}).get("title") or "")[:80], rid=rid)
    _save_store()
    _log_proposal(to)                       # feeds the receiving-policy budget, spec 4.4
    # Срок берём ИЗ ЗАПИСИ, а не считаем второй раз. Здесь стоял свой литерал `now +
    # PROPOSAL_TTL_S`, и когда правило срока поменялось, запись с ответом разошлись: приглашение
    # жило по спеке, а отправителю сообщалось прежнее число. Разошедшиеся копии одного значения —
    # это тот самый класс поломок, который в этом проекте виден только на живом сервере.
    return _idem_put(idem, {"ok": True, "id": rid, "status": "pending", "version": 1,
                            "expires_at": rs[-1]["expires_at"]})

def _with_photos(rows, name_key):
    """Attach the photo of the person named under `name_key` — an invitation and a message thread are
    both a PERSON, and a row that knows only their name renders a blank circle beside it."""
    for r in rows or []:
        if isinstance(r, dict) and not r.get("photo"):
            ph = _photo_of(r.get(name_key))          # в поле лежит id человека — фото по нему
            if ph:
                r["photo"] = ph
        if isinstance(r, dict) and not r.get("tz"):
            tz = _tz_of(r.get(name_key))             # пояс того же человека — для времени на приглашении
            if tz:
                r["tz"] = tz
    return rows


def inbox(self_name):
    me = _norm_name(self_name)
    if not me:
        return []
    if _expire_due():
        _save_store()
    # A WITHDRAWN invitation is one the sender pulled back — the recipient was never meant to act on
    # it, so it has no business in their inbox at all. Until now only the client's «status===pending»
    # filter kept it off the screen, which means the invitation was still being delivered and merely
    # not drawn. Declined and expired ones stay: those are the recipient's own history.
    out = [dict(r) for r in _requests()
           if _norm_name(r.get("to")) == me and r.get("status") != "withdrawn"]
    # OF.09: точное место в приглашение НЕ отдаётся. Раньше это делал клиент — вырезал `address`
    # ПЕРЕД отправкой, — и вместе с приватностью терялась вещь, которую обещали не спрашивать
    # дважды: автор интента, дойдя до формы плана, не находил собственного адреса и вводил его
    # заново. Место остаётся в заявке (её видит только отправитель, через outbox) и вырезается
    # здесь, на выходе получателю. Это же и надёжнее: правило живёт на сервере, а не в клиенте.
    for r in out:
        it = r.get("intent")
        # Адрес и ССЫЛКА — одного рода: и то и другое открывается только после согласия.
        #
        # Спека «Онлайн и гибрид → Ссылка генерируется при PlanState = Confirmed. До подтверждения
        # ссылки физически не существует — правило безопасности, а не UI». Адрес вырезали, а link
        # рядом забыли: он уезжал получателю целиком ещё до всякого ответа. Экран при этом честно
        # рисовал «Видеозвонок · ссылка у X» — то есть правило соблюдалось на вид, но не в данных.
        if isinstance(it, dict) and (it.get("address") or it.get("link")):
            r["intent"] = {k: v for k, v in it.items() if k not in ("address", "link")}
            r["intent"]["link_pending"] = bool(it.get("link"))
    out.sort(key=lambda r: -(r.get("updated") or 0))
    return _with_photos(out[:50], "from")

def outbox(self_name):
    me = _norm_name(self_name)
    if not me:
        return []
    if _expire_due():
        _save_store()
    out = [dict(r) for r in _requests() if _norm_name(r.get("from")) == me]
    out.sort(key=lambda r: -(r.get("updated") or 0))
    return _with_photos(out[:50], "to")

# A meetup leaves the active list only when someone says so. Deriving "past" from a timestamp would
# be a guess: the request carries the intent's loose time ("tomorrow evening"), never a real date.
def archive_request(rid, who):
    me = _norm_name(who)
    with _STORE_LOCK:
        for r in _requests():
            if r.get("id") == rid:
                if me and me not in (_norm_name(r.get("to")), _norm_name(r.get("from"))):
                    return {"ok": False, "error": "not your request"}
                if r.get("status") != "accepted":
                    return {"ok": False, "error": "only an accepted meetup can be archived"}
                r["status"] = "archived"
                r["updated"] = time.time()
                _save_store()
                return {"ok": True, "id": rid, "status": "archived"}
    return {"ok": False, "error": "not found"}

def _num(v):
    """Numeric coercion that tolerates strings ('28') and refuses junk — a single profile with a
    string-typed age/km used to raise inside a gate and kill the search for EVERY user."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def _policy_ok_now(frm, to, blocked=None):
    """Re-resolve BOTH sides against the live store and re-run the hard gates. Returns (ok, reason).
    Safe to call while _STORE_LOCK is held: load_candidates() and plain SESSION reads never take it
    (_session() does — calling that here would deadlock on the non-reentrant lock)."""
    # Обе стороны — по id: по имени нашёлся бы тёзка, и проверка допуска считалась бы не для того.
    a, b = _person(frm), _person(to)
    if not a or not b:
        return True, ""                                  # unknown to the store: nothing to revoke on
    if b.get("open") is False or b.get("paused"):
        return False, "recipient is not accepting requests"
    if a.get("paused"):
        return False, "sender is paused"
    # Only CONSENT and SAFETY gates are re-checked here. Outreach budgets (fatigue, cooldown,
    # "too many open invites") governed whether the proposal could be SENT; re-applying them now
    # would revoke perfectly consensual acceptances just because the sender got popular meanwhile.
    bl = {str(x).strip().lower() for x in (blocked or ())}
    if _norm_name(frm) in bl or a.get("blocksMe") or b.get("blocksMe"):
        return False, "blocked"
    for side, tag in ((a, "sender"), (b, "recipient")):
        age = _num(side.get("age"))
        if age is not None and age < MIN_AGE:
            return False, "%s under %d" % (tag, MIN_AGE)
    return True, ""

def respond(rid, decision, who, idem=None, version=None, flow=None):
    """Accept/decline INSIDE one transaction that re-checks expiry, version and LIVE policy (§14.2).
    Before this, policy was validated only when SENDING: if the recipient paused, blocked the sender
    or closed the domain between SENT and ACCEPT, the accept still went through."""
    dec = "accepted" if str(decision).lower() in ("accept", "accepted", "yes") else "declined"
    cached = _idem_get(idem)
    if cached is not None:
        return cached                                    # same key -> same answer (acceptance test #7)
    with _STORE_LOCK:
        now = time.time()
        _expire_due(now)
        for r in _requests():
            if r.get("id") != rid:
                continue
            # Без имени — отказ. Раньше отсутствие имени означало «проверять нечего».
            if not who or _norm_name(who) != _norm_name(r.get("to")):
                return {"ok": False, "error": "only the recipient can answer this request"}
            st = r.get("status")
            if st == "expired":
                _save_store()
                return _idem_put(idem, {"ok": False, "error": "EXPIRED", "id": rid, "status": "expired"})
            if st == "answered":
                # C1a: ответивший «да» ждёт выбора и до выбора может передумать. Повторное «да» —
                # тот же ответ, а не ошибка.
                if dec == "accepted":
                    return _idem_put(idem, {"ok": True, "id": rid, "status": "answered",
                                            "version": r.get("version"), "pick_by": r.get("pick_by")})
                r["status"] = "declined"
                r["updated"] = now
                r["version"] = int(r.get("version") or 1) + 1
                r["trace"] = {"decision": "declined", "at": now, "by": who, "reason": "changed_mind"}
                _save_store()
                return _idem_put(idem, {"ok": True, "id": rid, "status": "declined",
                                        "version": r["version"], "withdrawn": []})
            if st != "pending":
                # already settled: report the settled state, never flip it (concurrent-accept, §14.3)
                return _idem_put(idem, {"ok": False, "error": "ALREADY_RESOLVED", "id": rid,
                                        "status": st, "version": r.get("version")})
            # optimistic concurrency: a stale version means someone else moved this row first
            if version is not None and str(version) != str(r.get("version") or 1):
                return {"ok": False, "error": "VERSION_CONFLICT", "id": rid,
                        "status": st, "version": r.get("version")}
            if dec == "accepted":
                # the responder IS the local user, so their block list is session "me"
                mine = (SESSION.get("me") or {}).get("blocked") or []
                ok, why = _policy_ok_now(r.get("from"), r.get("to"), mine)
                if not ok:
                    r["status"] = "policy_revoked"
                    r["updated"] = now
                    r["version"] = int(r.get("version") or 1) + 1
                    r["trace"] = {"decision": "policy_revoked", "at": now, "reason": why}
                    _save_store()
                    return _idem_put(idem, {"ok": False, "error": "POLICY_CHANGED", "id": rid,
                                            "status": "policy_revoked", "reason": why})
            if dec == "accepted" and str(flow or "").strip().lower() == "pick":
                # «ДА» = «ОТВЕТИЛ, ЖДЁТ ВЫБОРА». Чат не открывается (он держится на `accepted`),
                # соседи не гасятся — выбирает организатор. Включается признаком `flow: "pick"` от
                # нового клиента: старый клиент без признака идёт прежним путём «первое да», иначе
                # между выкладками сервера и приложения согласие вело бы в никуда.
                r["status"] = "answered"
                r["updated"] = now
                r["answered_at"] = now
                r["pick_by"] = now + _invite_ttl(r.get("intent"), now)
                r["version"] = int(r.get("version") or 1) + 1
                r["trace"] = {"decision": "answered", "at": now, "by": who,
                              "config_version": r.get("config_version")}
                _save_store()
                return _idem_put(idem, {"ok": True, "id": rid, "status": "answered",
                                        "version": r["version"], "pick_by": r["pick_by"],
                                        "withdrawn": []})
            r["status"] = dec
            r["updated"] = now
            r["version"] = int(r.get("version") or 1) + 1
            r["trace"] = {"decision": dec, "at": now, "by": who or r.get("to"),
                          "config_version": r.get("config_version")}   # immutable decision trace
            # ПЕРВОЕ «ДА» ЗАКРЫВАЕТ ОСТАЛЬНЫЕ.
            #
            # Спека «01 · Сроки и пороги» → «Первый accept на 1:1 → остальные withdrawn.
            # Автоматически, с уведомлением. Закрывает гонку „двое приняли последнее место“».
            #
            # Этого не было вовсе: статус менялся ровно у своей строки. Пригласивший троих получал
            # три согласия на один вечер, а второй и третий узнавали об этом уже в чате — если
            # вообще узнавали. Гасим соседей ТОГО ЖЕ отправителя, и только по 1:1: у группы места
            # считаются иначе, там несколько «да» — норма.
            withdrawn = []
            if dec == "accepted":
                # ...НО ТОЛЬКО ПО ТОЙ ЖЕ ЗАТЕЕ. «Место занято» имеет смысл лишь для одного и того
                # же вечера. Цикл сравнивал одного отправителя — и всё: Иван зовёт Аню на кофе во
                # вторник и Борю на пробежку в субботу, Аня говорит «да» — и приглашение Бори
                # исчезает с пометкой «место занято», хотя это другая затея и другой день. Никто
                # из троих об этом не узнаёт: у Бори строка пропадает из ленты, у Ивана — из его
                # интентов. Воспроизведено в памяти 7 сентября 2026 (/tmp/test_withdraw.py).
                #
                # `iid` пишется в заявку ровно для этого (см. propose). У старых заявок его нет —
                # их НЕ гасим: не доказано, что это то же место, а отнять приглашение молча хуже,
                # чем оставить гонку двух «да», которую видно хотя бы в чате.
                mine = str(r.get("iid") or "")
                for other in _requests():
                    if other is r or other.get("status") not in REQ_OPEN:
                        continue
                    if _norm_name(other.get("from")) != _norm_name(r.get("from")):
                        continue
                    if not mine or str(other.get("iid") or "") != mine:
                        continue
                    other["status"] = "withdrawn"
                    other["updated"] = now
                    other["version"] = int(other.get("version") or 1) + 1
                    # Причина видна получателю: «место занято», а не «отправитель передумал».
                    other["trace"] = {"decision": "withdrawn", "at": now, "reason": "seat_taken",
                                      "taken_by": r.get("to")}
                    withdrawn.append(other.get("id"))
            _save_store()
            return _idem_put(idem, {"ok": True, "id": rid, "status": dec, "version": r["version"],
                                    "withdrawn": withdrawn})
    return {"ok": False, "error": "not found"}

def pick_request(rid, who, idem=None):
    """Организатор выбирает ОДНОГО из ответивших «да» (OF.14a–16). Только отправитель заявки.

    Выбранный получает обычное `accepted` — дальше всё как после согласия: чат, план. Остальные
    открытые заявки этого отправителя по ТОЙ ЖЕ затее (и ответившие, и ещё молчащие) закрываются
    как `not_picked` с причиной `picked_other` — «не в этот раз» (N2). Это не `withdrawn`:
    отозванное приглашение получателю не показывается вовсе, а здесь он обязан увидеть исход."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    with _STORE_LOCK:
        now = time.time()
        _expire_due(now)
        for r in _requests():
            if r.get("id") != rid:
                continue
            if not who or _norm_name(who) != _norm_name(r.get("from")):
                return {"ok": False, "error": "only the sender can pick"}
            st = r.get("status")
            if st == "pending":
                return _idem_put(idem, {"ok": False, "error": "NOT_ANSWERED", "id": rid, "status": st})
            if st != "answered":
                if st == "expired":
                    _save_store()
                return _idem_put(idem, {"ok": False, "error": "ALREADY_RESOLVED", "id": rid,
                                        "status": st, "version": r.get("version")})
            # Согласие дано раньше — допуск перепроверяем сейчас, как при обычном accept (§14.2).
            ok, why = _policy_ok_now(r.get("from"), r.get("to"), ())
            if not ok or _blocked_pair(r.get("from"), r.get("to")):
                r["status"] = "policy_revoked"
                r["updated"] = now
                r["version"] = int(r.get("version") or 1) + 1
                r["trace"] = {"decision": "policy_revoked", "at": now, "reason": why or "blocked"}
                _save_store()
                return _idem_put(idem, {"ok": False, "error": "POLICY_CHANGED", "id": rid,
                                        "status": "policy_revoked", "reason": why or "blocked"})
            r["status"] = "accepted"
            r["updated"] = now
            r["picked_at"] = now
            r["version"] = int(r.get("version") or 1) + 1
            r["trace"] = {"decision": "accepted", "at": now, "by": r.get("to"), "picked_by": who,
                          "config_version": r.get("config_version")}
            closed = []
            for other in _requests():
                if other is r or other.get("status") not in REQ_OPEN:
                    continue
                if _norm_name(other.get("from")) != _norm_name(r.get("from")):
                    continue
                if not _req_same_intent(other, r):
                    continue
                other["status"] = "not_picked"
                other["updated"] = now
                other["version"] = int(other.get("version") or 1) + 1
                other["trace"] = {"decision": "not_picked", "at": now, "reason": "picked_other"}
                closed.append(other.get("id"))
            _save_store()
            return _idem_put(idem, {"ok": True, "id": rid, "status": "accepted",
                                    "version": r["version"], "closed": closed})
    return {"ok": False, "error": "not found"}


def withdraw_request(rid, who, idem=None):
    """The SENDER pulls a proposal back before it is answered (§14.1 WITHDRAWN)."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    with _STORE_LOCK:
        _expire_due()
        for r in _requests():
            if r.get("id") != rid:
                continue
            if not who or _norm_name(who) != _norm_name(r.get("from")):
                return {"ok": False, "error": "only the sender can withdraw"}
            # Отозвать можно и у ответившего «да», пока его не выбрали: организатор передумал звать.
            if r.get("status") not in REQ_OPEN:
                return _idem_put(idem, {"ok": False, "error": "ALREADY_RESOLVED",
                                        "id": rid, "status": r.get("status")})
            r["status"] = "withdrawn"
            r["updated"] = time.time()
            r["version"] = int(r.get("version") or 1) + 1
            _save_store()
            return _idem_put(idem, {"ok": True, "id": rid, "status": "withdrawn", "version": r["version"]})
    return {"ok": False, "error": "not found"}

# ---- real message delivery ------------------------------------------------------------------------
# Same gap as proposals had: the chat pushed the typed text into local state only, so the recipient's
# account never received it. Messages are stored per pair and read back by either side.
def _messages():
    return SESSION.setdefault("_messages", [])

def _pair_key(a, b):
    return "|".join(sorted([_norm_name(a), _norm_name(b)]))

def _sys_msg(frm, to, code, **fields):
    """A PLAN EVENT written into the pair's thread. Call only with _STORE_LOCK already held.

    Why the thread and not just the plan screen. The plan lives on its own screen, and everything
    that happened to it used to live there too: the other side got a pinned card that silently
    changed under them — no line saying the plan was sent, none saying it was confirmed, none when
    the place or the call link was finally named. Two people agreeing to meet were reading two
    different states of the same evening and had to ask each other «ну что, договорились?».

    The row carries a CODE and its facts, never a rendered sentence: the two sides can be reading
    the app in different languages, and a Russian line baked here would arrive at an English screen.
    `text` is a plain fallback for anything that shows a raw last-message preview.
    """
    frm, to = str(frm or "").strip(), str(to or "").strip()
    if not frm or not to:
        return
    _now = time.time()
    m = {"id": "s_%d_%s" % (int(_now * 1000), code), "pair": _pair_key(frm, to),
         "from": frm, "to": to, "text": "", "t": _now, "u": _now,
         "sys": dict({"code": code, "by": frm}, **{k: v for k, v in fields.items() if v not in (None, "")})}
    ms = _messages()
    ms.append(m)
    del ms[:-4000]


_VOICE_URL_RE = re.compile(r"^/api/speech/audio/([0-9a-f]{32})\.(m4a|mp4|webm|wav|mp3|ogg)$")


def _voice_message(voice):
    """Normalize voice metadata produced by llm-service and reject arbitrary media URLs."""
    if voice is None:
        return None, None
    if not isinstance(voice, dict):
        return None, "INVALID_VOICE"
    voice_id = str(voice.get("id") or "").strip().lower()
    url = str(voice.get("url") or "").strip()
    transcript = str(voice.get("transcript") or voice.get("text") or "").strip()[:2001]
    mime_type = str(voice.get("mime_type") or "").strip().lower()
    try:
        duration_ms = int(voice.get("duration_ms") or 0)
    except (TypeError, ValueError):
        return None, "INVALID_VOICE"
    match = _VOICE_URL_RE.fullmatch(url)
    if (not re.fullmatch(r"[0-9a-f]{32}", voice_id) or not match
            or match.group(1) != voice_id or not transcript or len(transcript) > 2000
            or duration_ms < 250 or duration_ms > 60000
            or not (mime_type.startswith("audio/") or mime_type.startswith("video/"))):
        return None, "INVALID_VOICE"
    return {
        "id": voice_id, "url": url, "duration_ms": duration_ms,
        "transcript": transcript, "mime_type": mime_type,
    }, None


_MID_SEQ = [0]


def _mid(prefix):
    """Уникальный id сообщения.

    Был просто миллисекундой (`m_%d`), и две реплики, отправленные в одну и ту же миллисекунду,
    получали ОДИН id. Клиент склеивает ленту по id — одна строка молча затирала другую. Пока по
    id никто не адресовался, это была редкая невидимая потеря; с реакциями, цитатой и удалением
    цена промаха другая: действие уедет не в то сообщение.

    Счётчик, а не случайные символы: внутри процесса он даёт гарантию, а не вероятность, и
    сохраняет порядок отправки для двух реплик одной миллисекунды.
    """
    _MID_SEQ[0] = (_MID_SEQ[0] + 1) % 4096
    return "%s%d_%03x" % (prefix, int(time.time() * 1000), _MID_SEQ[0])


# ---- КРУЖКИ: приём, хранение и раздача КУСКАМИ ---------------------------------------------------
#
# Раздача по кускам здесь не украшение, а условие работы. Проигрыватель на iOS тянет удалённое
# видео частями и требует от сервера поддержки `Range`; сервер, который её не умеет, для него
# просто непригоден — файл не открывается вовсе. Ровно на это уже наступили с голосовыми: там
# пришлось скачивать файл целиком перед проигрыванием. У видео такой обход неприемлем — минута
# кружка это мегабайты, и ждать их до первого кадра никто не станет.
VIDEO_DIR = os.environ.get(
    "KLEAL_VIDEO_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "video"))
MAX_VIDEO_BYTES = 12 * 1024 * 1024
MAX_VIDEO_MS = 60_000
MIN_VIDEO_MS = 700
VIDEO_NAME_RE = re.compile(r"^[0-9a-f]{32}\.(mp4|mov|m4v)$")
_VIDEO_URL_RE = re.compile(r"^/api/agent/video/[0-9a-f]{32}\.(mp4|mov|m4v)$")


def _one_file(content_type, body):
    """Достать единственный файл из multipart/form-data.

    Полноценный разбор здесь не нужен и был бы лишним: клиент шлёт ровно одно поле с файлом.
    Берём первую часть, у которой есть `filename`, — всё остальное в этом запросе не наше дело.
    """
    m = re.search(r'boundary="?([^";]+)"?', content_type or "", re.I)
    if not m:
        return None, None, None
    sep = ("--" + m.group(1)).encode()
    for part in body.split(sep):
        head, _, data = part.partition(b"\r\n\r\n")
        if b"filename=" not in head.lower():
            continue
        h = head.decode("utf-8", "replace")
        name = (re.search(r'filename="([^"]*)"', h) or [None, ""])[1]
        ctype = (re.search(r"Content-Type:\s*([^\r\n;]+)", h, re.I) or [None, ""])[1].strip().lower()
        if data.endswith(b"\r\n"):
            data = data[:-2]
        return name, ctype, data
    return None, None, None


def video_store(filename, media_type, blob, duration_ms):
    if not blob:
        return {"ok": False, "error": "VIDEO_REQUIRED"}
    if len(blob) > MAX_VIDEO_BYTES:
        return {"ok": False, "error": "VIDEO_TOO_LARGE"}
    if not (MIN_VIDEO_MS <= int(duration_ms or 0) <= MAX_VIDEO_MS):
        return {"ok": False, "error": "INVALID_VIDEO_DURATION"}
    ext = "mp4"
    low = "%s %s" % (str(filename or "").lower(), str(media_type or "").lower())
    if "quicktime" in low or low.endswith(".mov") or ".mov" in low:
        ext = "mov"
    os.makedirs(VIDEO_DIR, exist_ok=True)
    vid = secrets.token_hex(16)            # случайное имя: см. голосовые ниже
    name = "%s.%s" % (vid, ext)
    with open(os.path.join(VIDEO_DIR, name), "wb") as f:
        f.write(blob)
    return {"ok": True, "id": vid, "url": "/api/agent/video/%s" % name,
            "duration_ms": int(duration_ms), "mime_type": "video/%s" % ("quicktime" if ext == "mov" else "mp4")}


def _video_message(video):
    """Проверить метаданные кружка и НЕ пустить произвольный адрес.

    Та же защита, что у голосовых: без неё через переписку можно заставить чужое приложение
    сходить куда угодно — достаточно прислать сообщение со ссылкой в поле `video`.
    """
    if video is None:
        return None, None
    if not isinstance(video, dict):
        return None, "INVALID_VIDEO"
    url = str(video.get("url") or "").strip()
    vid = str(video.get("id") or "").strip().lower()
    try:
        ms = int(video.get("duration_ms") or 0)
    except (TypeError, ValueError):
        return None, "INVALID_VIDEO"
    if not _VIDEO_URL_RE.match(url) or not re.fullmatch(r"[0-9a-f]{32}", vid):
        return None, "INVALID_VIDEO"
    if not (MIN_VIDEO_MS <= ms <= MAX_VIDEO_MS):
        return None, "INVALID_VIDEO"
    return {"id": vid, "url": url, "duration_ms": ms,
            "mime_type": str(video.get("mime_type") or "video/mp4")[:40]}, None


# Набор реакций закрытый и маленький. Открытый вернул бы в переписку произвольную картинку от
# постороннего — это уже не реакция, а сообщение в обход всех проверок. Шесть штук покрывают то,
# ради чего реакция и нужна: согласиться, обрадоваться, удивиться, посочувствовать.
REACTIONS = ("❤️", "👍", "😂", "🔥", "😮", "😢")


# ---- ГОЛОСОВЫЕ: приём, хранение, раздача кусками, расшифровка -----------------------------------
#
# Повторяет кружки один в один (см. блок выше) и добавляет расшифровку через под. Отдельный
# каталог и отдельный предел: минута речи в m4a — сотни килобайт, не мегабайты, и 4 МБ хватает
# с запасом на любой кодек телефона (Android отдаёт m4a/3gp, iOS — m4a, браузер — webm).
VOICE_DIR = os.environ.get(
    "KLEAL_VOICE_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "voice"))
MAX_VOICE_BYTES = 4 * 1024 * 1024
MAX_VOICE_MS = 60_000
MIN_VOICE_MS = 500
VOICE_NAME_RE = re.compile(r"^[0-9a-f]{32}\.(m4a|mp4|aac|3gp|webm|ogg|wav|caf)$")
VOICE_MIME = {"m4a": "audio/mp4", "mp4": "audio/mp4", "aac": "audio/aac", "3gp": "audio/3gpp",
              "webm": "audio/webm", "ogg": "audio/ogg", "wav": "audio/wav", "caf": "audio/x-caf"}
# Столько ждём расшифровку. Дольше — голосовое уходит без текста, а не висит у человека на экране.
TRANSCRIBE_TIMEOUT_S = 25


def _voice_ext(filename, media_type):
    low = "%s %s" % (str(filename or "").lower(), str(media_type or "").lower())
    for ext in ("webm", "ogg", "wav", "caf", "3gp", "aac"):
        if low.endswith("." + ext) or ("." + ext + " ") in low or ("/" + ext) in low:
            return ext
    if "3gpp" in low:
        return "3gp"
    return "m4a"


def voice_store(filename, media_type, blob, duration_ms):
    if not blob:
        return {"ok": False, "error": "VOICE_REQUIRED"}
    if len(blob) > MAX_VOICE_BYTES:
        return {"ok": False, "error": "VOICE_TOO_LARGE"}
    if not (MIN_VOICE_MS <= int(duration_ms or 0) <= MAX_VOICE_MS):
        return {"ok": False, "error": "INVALID_VOICE_DURATION"}
    ext = _voice_ext(filename, media_type)
    os.makedirs(VOICE_DIR, exist_ok=True)
    # Имя файла — случайное (аудит 27.09.2026): хэш от времени, длины и имени угадывается
    # перебором вокруг момента отправки, а ссылка на файл и есть доступ к нему.
    vid = secrets.token_hex(16)
    name = "%s.%s" % (vid, ext)
    with open(os.path.join(VOICE_DIR, name), "wb") as f:
        f.write(blob)
    return {"ok": True, "id": vid, "url": "/api/agent/voice/%s" % name,
            "duration_ms": int(duration_ms), "mime_type": VOICE_MIME.get(ext, "audio/mp4")}


def transcribe_remote(blob, filename, media_type):
    """Речь -> текст через под (/llm/transcribe). Любая беда -> ("", "") и голосовое уходит без текста."""
    boundary = "kleal%s" % hashlib.md5(str(time.time()).encode()).hexdigest()[:16]
    head = ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\n"
            "Content-Type: %s\r\n\r\n" % (boundary, (filename or "voice.m4a").replace('"', ""),
                                          media_type or "audio/mp4")).encode("utf-8")
    body = head + blob + ("\r\n--%s--\r\n" % boundary).encode("utf-8")
    # Адрес пода — из окружения службы (LLM_URL в unit), как у всех, кто ходит к модели.
    llm_url = os.environ.get("LLM_URL") or "http://127.0.0.1:17071"
    req = urllib.request.Request(llm_url.rstrip("/") + "/llm/transcribe", data=body, headers={
        "Content-Type": "multipart/form-data; boundary=%s" % boundary,
        "Content-Length": str(len(body))})
    try:
        with urllib.request.urlopen(req, timeout=TRANSCRIBE_TIMEOUT_S) as r:
            out = json.loads(r.read().decode("utf-8") or "{}")
        return str(out.get("text") or "").strip(), str(out.get("language") or "")
    except Exception as e:
        print("[voice] расшифровка не удалась: %s" % str(e)[:120])
        return "", ""



def _quote_of(m):
    """Что показать в цитате: кто сказал и первые слова.

    Хранится РЯДОМ с ответом, а не берётся по ссылке при чтении. Лента отдаёт последние двести
    строк, и цитируемое запросто окажется за этим краем — тогда ответ остался бы без того, на что
    отвечает. Двести знаков хватает: цитата в пузыре и так обрезается.
    """
    return {"id": m.get("id"), "from": m.get("from") or m.get("frm"),
            "text": str(m.get("text") or "")[:200], "kind": m.get("kind")}


def _touch(m):
    """Отметить строку изменённой — по этому полю опрос и приносит её второму участнику."""
    m["u"] = time.time()


def end_thread(who, other, idem=None):
    """Закрыть переписку — так, чтобы об этом узнал ВТОРОЙ.

    Кадр O.19c «Jane ended the chat. You can pick again» существует, а показать его было нечем:
    «Завершить чат» клало имя в локальный список на телефоне закрывшего, и на сервер не уходило
    ничего. Второй человек оставался ждать ответа в открытой переписке — и ждал бы вечно.

    Что делаем: пишем в ленту пары системную строку с кодом. Она приходит обоим по обычному пути
    чтения, ей не нужен ни отдельный опрос, ни уведомление, и она остаётся в истории — «почему
    этот разговор кончился» видно и через неделю.

    Заявку при этом НЕ трогаем: закрыть разговор и отозвать согласие — разные вещи, и второй
    может завести новый план с тем же человеком, если оба захотят.
    """
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    who, other = str(who or "").strip(), str(other or "").strip()
    if not who or not other or _norm_name(who) == _norm_name(other):
        return {"ok": False, "error": "TWO_PEOPLE_REQUIRED"}
    if not _mp_matched(who, other):
        return {"ok": False, "error": "NOT_MATCHED"}
    with _STORE_LOCK:
        _sys_msg(who, other, "chat_ended")
        _save_store()
    return _idem_put(idem, {"ok": True})


def send_message(frm, to, text, voice=None, client_id=None, reply_to=None, video=None):
    frm, to, text = str(frm or "").strip(), str(to or "").strip(), str(text or "").strip()[:2000]
    voice, voice_error = _voice_message(voice)
    if voice_error:
        return {"ok": False, "error": voice_error}
    video, video_error = _video_message(video)
    if video_error:
        return {"ok": False, "error": video_error}
    if voice:
        text = voice["transcript"]
    if video and not text:
        # У кружка расшифровки нет, а пустой текст `send_message` не пускает — и правильно
        # делает. Подпись даёт списку «Сообщений» что показать вместо пустоты под именем.
        text = "[video]"
    if not frm or not to or not text or _norm_name(frm) == _norm_name(to):
        return {"ok": False, "error": "from, to and text are required and the two must differ"}
    if _blocked_pair(frm, to):
        return {"ok": False, "error": "BLOCKED"}
    # КАНАЛ ОТКРЫВАЕТ СОГЛАСИЕ, А НЕ ЗНАНИЕ ИМЕНИ.
    #
    # Этой проверки здесь не было, и продукт держался на том, какие кнопки нарисованы. А имена
    # видны в поиске: зная имя, можно было написать кому угодно одним запросом, минуя весь путь
    # «заявка → согласие → переписка». Проверено на живом сервере 14 августа: два человека, между
    # которыми никогда ничего не было, — сообщение доставлено с ok: true.
    #
    # Правило то же, что у плана (_mp_matched ниже по файлу): «может уйти только тому, кто
    # согласился». Одна функция на оба случая — чтобы правило не разошлось само с собой.
    if not _mp_matched(frm, to):
        return {"ok": False, "error": "NOT_MATCHED",
                "note": "a message can only go to someone who accepted an invitation"}
    # Повтор с тем же ключом отправителя — тот же ответ, а не вторая реплика. Без этого «отправить
    # ещё раз» после неясного сбоя (сообщение записалось, а ответ не доехал) удваивает реплику у
    # собеседника, и отправитель об этом не узнает.
    cached = _idem_get(client_id)
    if cached is not None:
        return cached
    now = time.time()
    m = {"id": _mid("m_"), "pair": _pair_key(frm, to),
         "from": frm, "to": to, "text": text, "t": now, "u": now}
    if client_id:
        m["cid"] = str(client_id)[:64]
    if reply_to:
        # Цитируемое обязано быть ИЗ ЭТОЙ ЖЕ переписки: иначе ответом можно вытащить на экран
        # строку из чужого разговора — id угадывать не нужно, они последовательны.
        src = next((x for x in _messages()
                    if x.get("id") == str(reply_to) and x.get("pair") == m["pair"]), None)
        if not src:
            return {"ok": False, "error": "NO_SUCH_MESSAGE"}
        m["rt"] = _quote_of(src)
    if voice:
        m.update({"kind": "voice", "voice": voice})
    if video:
        m.update({"kind": "video", "video": video})
    with _STORE_LOCK:
        ms = _messages()
        ms.append(m)
        del ms[:-4000]                       # keep the store bounded
    _save_store()
    return _idem_put(client_id, {"ok": True, "id": m["id"], "t": m["t"], "cid": m.get("cid")})

def _touched(m):
    """Когда строку последний раз трогали: создали или изменили. По ней и идёт опрос.

    `t` — момент отправки, и он задаёт ПОРЯДОК в ленте; менять его при правке нельзя, иначе
    исправленная реплика прыгнет в конец разговора. Поэтому изменения отмечаются отдельным `u`, а
    опрос смотрит на больший из двух. Пока ничего не меняется, `u == t` и поведение прежнее.

    Без этого поля реакция, правка и удаление были бы видны ТОЛЬКО тому, кто их сделал: опрос
    тянет строго новее `since`, а тронутая строка старше — второй участник не узнал бы о ней.
    """
    return max(m.get("t") or 0, m.get("u") or 0)


def _react(m, who, emoji):
    """Поставить или снять реакцию. Повторное нажатие снимает — другого способа передумать нет."""
    who = _norm_name(who)
    rs = m.setdefault("r", {})
    names = [n for n in (rs.get(emoji) or []) if n]
    if who in names:
        names.remove(who)
    else:
        names.append(who)
    if names:
        rs[emoji] = names
    else:
        rs.pop(emoji, None)
    if not rs:
        m.pop("r", None)
    _touch(m)


def message_react(self_name, mid, emoji):
    me = _norm_name(self_name)
    emoji = str(emoji or "")
    if not me or not mid:
        return {"ok": False, "error": "self and id are required"}
    if emoji not in REACTIONS:
        return {"ok": False, "error": "UNKNOWN_REACTION"}
    with _STORE_LOCK:
        m = next((x for x in _messages() if x.get("id") == str(mid)), None)
        if not m:
            return {"ok": False, "error": "NO_SUCH_MESSAGE"}
        # Реагировать может только участник этой пары — членство и есть право доступа.
        if me not in (_norm_name(m.get("from")), _norm_name(m.get("to"))):
            return {"ok": False, "error": "NOT_YOURS"}
        _react(m, me, emoji)
        _save_store()
    return {"ok": True, "id": m["id"], "r": m.get("r") or {}}


def message_delete(self_name, mid):
    """Удаление МЯГКОЕ: строка остаётся, текст стирается.

    Жёсткое вырезание строки из стора второму участнику не доедет никогда: опрос переносит
    изменения, а не пропажи — сообщение так и висело бы у него на экране. Поэтому строка живёт
    дальше и говорит о себе «удалено»."""
    me = _norm_name(self_name)
    if not me or not mid:
        return {"ok": False, "error": "self and id are required"}
    with _STORE_LOCK:
        m = next((x for x in _messages() if x.get("id") == str(mid)), None)
        if not m:
            return {"ok": False, "error": "NO_SUCH_MESSAGE"}
        if _norm_name(m.get("from")) != me:
            return {"ok": False, "error": "NOT_YOURS"}
        if m.get("sys"):
            return {"ok": False, "error": "NOT_A_MESSAGE"}
        m["text"] = ""
        m["deleted"] = True
        m.pop("voice", None)
        m.pop("r", None)
        _touch(m)
        _save_store()
    return {"ok": True, "id": m["id"]}


def thread(self_name, other, since=0.0):
    """Every message between the two, oldest first. `since` lets a client poll for new ones only."""
    if not str(self_name or "").strip() or not str(other or "").strip():
        return []
    key = _pair_key(self_name, other)
    try:
        since = float(since or 0)
    except (TypeError, ValueError):
        since = 0.0
    out = [dict(m) for m in _messages() if m.get("pair") == key and _touched(m) > since]
    out.sort(key=lambda m: m.get("t") or 0)
    return out[-200:]

def threads_for(self_name):
    """Latest message per conversation, so the Messages tab reflects what actually exists."""
    me = _norm_name(self_name)
    if not me:
        return []
    reads = _thread_reads()
    last, unread = {}, {}
    for m in _messages():
        if me not in (_norm_name(m.get("from")), _norm_name(m.get("to"))):
            continue
        other = m.get("to") if _norm_name(m.get("from")) == me else m.get("from")
        okey = _norm_name(other)
        cur = last.get(okey)
        if not cur or (m.get("t") or 0) > (cur.get("t") or 0):
            # `sys` едет наружу: в списке «Сообщений» последней строкой вполне может быть событие
            # плана, и рисовать под именем пустоту вместо «План подтверждён» нельзя.
            last[okey] = {"who": other, "last": m.get("text"), "t": m.get("t"),
                          "kind": m.get("kind"), "voice": m.get("voice"),
                          "sys": m.get("sys"),
                          # Строка Kleal с кодом (GR.52 «removed you from…») — чтобы превью в
                          # «Сообщениях» было на языке приложения, а не английским текстом сервера.
                          **({"code": m.get("code"), "by": m.get("by"), "title": m.get("title")}
                             if m.get("admin") and m.get("code") else {}),
                          "mine": _norm_name(m.get("from")) == me}
        # Непрочитанное считается ЗДЕСЬ, потому что этот проход по сообщениям всё равно делается.
        # Клиент ради того же числа слал отдельный запрос на каждую переписку — до десяти штук
        # каждые пятнадцать секунд — и всё равно врал: у одиннадцатой переписки числа не бывало
        # никогда, а у групп не бывает и сейчас. Системные строки не считаем: событие плана —
        # не реплика, и жирная единица из-за него читается как «тебе написали».
        if _norm_name(m.get("from")) != me and not m.get("sys"):
            seen = (reads.get(_pair_key(self_name, other)) or {}).get(me) or 0
            if (m.get("t") or 0) > seen:
                unread[okey] = unread.get(okey, 0) + 1
    for k, row in last.items():
        row["unread"] = unread.get(k, 0)
    return _with_photos(sorted(last.values(), key=lambda x: -(x.get("t") or 0))[:50], "who")

def _thread_reads():
    return SESSION.setdefault("_thread_reads", {})


def thread_mark_read(self_name, other):
    """MSG.11: «прочитано» — отметка ЧИТАТЕЛЯ, а не свойство сообщения. Храним момент, когда человек
    в последний раз открывал пару; второй стороне отдаётся ТОЛЬКО этот момент (peer_read_at в
    /api/agent/thread) — по нему клиент сам решает, на каких его пузырях рисовать двойную галочку.
    Никакого по-сообщенного статуса нет намеренно: его пришлось бы писать в каждую строку стора."""
    me = _norm_name(self_name)
    if not me or not str(other or "").strip():
        return {"ok": False, "error": "self and with are required"}
    with _STORE_LOCK:
        _thread_reads().setdefault(_pair_key(self_name, other), {})[me] = time.time()
        _save_store()
    return {"ok": True}


# ---- intents as LIVE server-side standing searches ------------------------------------------------
# Intents used to live only in the sender's localStorage, holding a FROZEN copy of the candidates from
# the moment they were created — so a saved intent was a private note that never re-searched, while the
# requests and messages it supposedly drove were already shared server state. Stored here instead, and
# re-ranked on read so opening one shows who fits NOW, not who fitted then.
def _intents():
    return SESSION.setdefault("_intents", [])


def _ensure_intent_owner_ids():
    """Разовая привязка интентов, сделанных до id (`owner` = имя, `owner_id` нет).

    Идёт по правилу `_legacy_pid`: однозначное имя и аккаунт, существовавший к моменту записи.
    Неоднозначные остаются без хозяина — их не видит никто, пока их не разберёт
    tools/identity_repair.py. Это лучше, чем отдать чужому: ровно так и случилась беда 26.09.
    Дёшево: после первого прохода новых строк без id не бывает.
    """
    changed = 0
    with _STORE_LOCK:
        for r in _intents():
            if isinstance(r, dict) and "owner_id" not in r and r.get("owner"):
                pid = _legacy_pid(r.get("owner"), r.get("created"))
                if pid:
                    r["owner_id"] = pid
                    changed += 1
    if changed:
        print("[identity] интентов привязано к id: %d" % changed, flush=True)
        _save_store()
    return changed


def save_intent(owner, intent, title, iid=None, launched=None, owner_id=""):
    owner_id = str(owner_id or "").strip()
    if not owner_id or not isinstance(intent, dict):
        # Без личности интент не сохраняется: хозяина у него определить нечем, а по имени — нельзя.
        return {"ok": False, "error": "sign in required" if not owner_id else "intent required"}
    owner = _display(owner_id, str(owner or "").strip())
    _ensure_intent_owner_ids()
    intent = _prepare_map_intent(owner, intent, owner_id)
    # Snapshot confirmed country and resolve an explicitly supplied meeting address when possible.
    # Failure is intentionally non-fatal: the intent is still saved and map-feed reports partial data.
    # (Подготовка — выше, сразу после определения личности: страна берётся из СВОЕЙ строки по id.)
    now = time.time()
    key = imf.persistence_key(intent)
    with _STORE_LOCK:
        rows = _intents()
        if iid:
            for r in rows:
                if r.get("id") == iid and r.get("owner_id") == owner_id:
                    r.update({"intent": intent, "title": title or r.get("title"), "updated": now,
                              "key": key, "owner": owner})
                    # once a search has actually run this never flips back to "not started"
                    if launched:
                        r["launched"] = now
                    _save_store()
                    return {"ok": True, "id": iid}
        # The same request twice updates one row, but a different mode/date/address is a different
        # intent even when topics and role match. The previous topics|role key collapsed those plans.
        for r in rows:
            same_owner = r.get("owner_id") == owner_id
            same_intent = r.get("key") == key or imf.persistence_key(r.get("intent") or {}) == key
            if same_owner and same_intent:
                r.update({"intent": intent, "title": title or r.get("title"), "updated": now,
                          "key": key})
                if launched:
                    r["launched"] = now
                _save_store()
                return {"ok": True, "id": r["id"], "merged": True}
        base_id = "in_%d" % int(now * 1000)
        taken = {str(r.get("id") or "") for r in rows}
        nid, suffix = base_id, 1
        while nid in taken:
            nid, suffix = "%s_%d" % (base_id, suffix), suffix + 1
        rows.append({"id": nid, "owner": owner, "owner_id": owner_id, "title": title or "", "intent": intent,
                     "key": key, "created": now, "updated": now,
                     "launched": now if launched else None})
    _save_store()
    return {"ok": True, "id": nid}

def delete_intent(owner, iid, owner_id=""):
    owner_id = str(owner_id or "").strip()
    if not owner_id:
        return {"ok": False, "error": "sign in required"}
    with _STORE_LOCK:
        rows = _intents()
        keep = [r for r in rows
                if not (r.get("id") == iid and r.get("owner_id") == owner_id)]
        removed = len(rows) - len(keep)
        rows[:] = keep
    _save_store()
    return {"ok": removed > 0}

def _normalize_intent(raw):
    """Accept the shapes clients actually send. The profile UI posts its CARD object, where the
    topics live in `tags` and the real intent is nested under `intent` — so the engine saw an
    intent with NO topics, tiered everyone as T5 ("no meaningful topical overlap") and declined
    the whole slate. Be liberal here: a missing topic list is never a legitimate search."""
    if not isinstance(raw, dict):
        return {}
    it = dict(raw)
    inner = raw.get("intent")
    if isinstance(inner, dict):                       # card wrapper -> use the real intent
        merged = dict(inner)
        for k, v in it.items():
            if k != "intent" and k not in merged:
                merged[k] = v
        it = merged
    if not it.get("topics"):
        for alt in ("tags", "keywords"):
            v = it.get(alt)
            if isinstance(v, list) and v:
                it["topics"] = [str(x) for x in v]
                break
    return it

# ПАМЯТЬ ПЕРЕСЧЁТА ВКЛАДКИ «МОЯ АКТИВНОСТЬ».
#
# `list_intents(live=True)` ранжирует КАЖДЫЙ интент человека заново — около двух секунд на штуку
# по пулу в восемьсот строк. У человека с пятью затеями вкладка открывалась 10,3 секунды, и так
# при каждом заходе (замерено 11 сентября 2026: 10,31 с против 0,00 с без пересчёта). Пул при
# этом меняется редко, а вкладку открывают часто — то есть считалось одно и то же.
#
# Здесь пересчёт помнится пять минут по ключу «интент + его updated + профиль искателя»: правка
# интента ключ сбивает, и пересчёт идёт сразу. Второй заход в вкладку — мгновенный.
# Быстрый проход (live=False) отдаёт ПОСЛЕДНИЙ известный снимок с пометкой stale, а не пустоту:
# экран рисует лица и счётчик сразу, а свежий пересчёт догоняет вторым запросом.
_RANK_MEMO = {}                 # intent id -> (ключ, момент, кандидаты)
RANK_MEMO_TTL = 300


def list_intents(owner, profile=None, live=True, owner_id=""):
    """Every intent this user owns. With live=True each one is re-ranked now (memoised for five
    minutes, see _RANK_MEMO), so the count and the top band reflect the current pool rather than a
    snapshot taken when the card was made. live=False returns the last known snapshot instantly."""
    # ТОЛЬКО ПО ID. По имени здесь отдавались интенты всех тёзок сразу: 26.09.2026 новый аккаунт
    # «Иван» увидел в «Моей активности» интенты трёх других «Иванов».
    owner_id = str(owner_id or "").strip()
    if not owner_id:
        return []
    _ensure_intent_owner_ids()
    sig = json.dumps(profile or {}, sort_keys=True, ensure_ascii=False, default=str)[:2000]
    now = time.time()
    out = []
    for r in [x for x in _intents() if x.get("owner_id") == owner_id]:
        row = {"id": r["id"], "title": r.get("title"), "intent": r.get("intent") or {},
               "created": r.get("created"), "updated": r.get("updated"),
               "launched": r.get("launched"), "candidates": []}
        memo = _RANK_MEMO.get(r["id"])
        key = (r.get("updated"), sig)
        if live:
            if memo and memo[0] == key and now - memo[1] < RANK_MEMO_TTL:
                row["candidates"] = memo[2]
            else:
                try:
                    row["candidates"] = match_candidates(_normalize_intent(r.get("intent") or {}),
                                                         profile or {},
                                                         {"self": _display(owner_id, owner),
                                                          "self_id": owner_id}) or []
                    _RANK_MEMO[r["id"]] = (key, now, row["candidates"])
                except Exception as e:
                    row["error"] = str(e)[:120]        # a failed re-rank must not hide the intent
        elif memo:
            row["candidates"] = memo[2]
            row["stale"] = True                        # снимок: свежий пересчёт придёт вторым проходом
        out.append(row)
    out.sort(key=lambda x: -(x.get("updated") or 0))
    return out

# Group size bounds (§15). Restored with the group handlers: this was a tuple assignment in the
# pre-rewrite file, which the transplant's dependency scan did not follow.
# -*- coding: utf-8 -*-
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# GROUP INTENTS — individual invites and ONE shared chat   (Group Chats & Group Plans spec, §1–§6.7)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# The UX invariant this whole block exists to hold: there is no lobby, no waiting room and no private
# chat between the organiser and a member. A group intent has exactly ONE thread. The first person to
# accept opens it; everyone who accepts after that is added to the same one automatically.
#
# Every check below (capacity, open-invite cap, policy) is per-candidate and re-run at ACCEPT as
# well as at SEND, because the group can fill up in between.
GI_MIN_TOTAL = 3          # three people INCLUDING the organiser; two is not a group result
# Free ceiling is FIVE — board GR.08: «Free groups go up to 5 people. Plus raises the ceiling
# to 20». The Plus tier does not exist in the backend yet, so 5 is the ceiling, full stop; when
# the Plus layer lands, this becomes per-owner. (Was 6 — a written-spec-era default that matched
# neither the board nor the app copy «3–5 человек».)
GI_MAX_TOTAL = 5
# Который документ здесь главный — уже менялось ДВАЖДЫ, поэтому история выписана явно:
#   written spec  : приглашения строго по одному, батч запрещён;
#   daily (июль)  : батч разрешён («отправить 10 инвайтов»), кап — только предохранитель (20);
#   БОРД (август) : снова по одному, с шитом подтверждения на каждого (GR.16), и открытых
#                   приглашений У ОДНОЙ ГРУППЫ не больше ТРЁХ на Free — GR.14/GR.15: «3 open
#                   invites at a time on Free · first 5 who accept are in», «Kleal holds them at
#                   three so nobody gets a fan-out of requests. Cancel one, or wait — Plus raises
#                   it». Борд новее, борд и действует.
# API по-прежнему принимает список (gi_invite_many) — но кап в 3 открытых делает «казтинг-колл»
# невозможным независимо от формы вызова. Отменить открытое приглашение можно (gi_invite_cancel):
# GR.17 даёт Cancel на каждой строке, и GR.15 прямо предлагает «Cancel one» как выход из капа.
GI_OPEN_INVITE_CAP = 3
# 12 часов — борд «0 · Create the intent» («Ends in 12h»), решение владельца 04.10.2026 (было 72 ч).
# Уже отправленные приглашения держат свой прежний expires_at: срок пишется в строку при отправке.
GI_INVITE_TTL = 12 * 3600  # an invite nobody answers stops being a held seat
# Исход закрытого приглашения в словаре клиента: «declined» → «Can't make it», прочее → «Invite closed».
_GI_INVITE_OUTCOME = {"declined": "declined", "expired": "expired", "withdrawn": "withdrawn",
                      "group_full": "closed", "group_closed": "closed", "policy_revoked": "closed",
                      "declined_by_organizer": "closed"}
# The phases where an accepted invite still drops straight into the chat. After that the roster is
# what a plan is being confirmed against, so a newcomer is approved by the organiser, not admitted
# automatically — «он уже не автоматически попадает в чат, а создатель должен сделать аппрув».
GI_OPEN_PHASES = ("searching", "chat_open", "ready_to_plan")
# Переход в один на один возможен и из ПАУЗЫ. Когда план падает ниже кворума, туда же уходит и
# состояние самой группы — а она при этом жива: люди на месте, разговор на месте, стоит только
# встреча. Кадр GR.40 предлагает оттуда три выхода, и средний («перейти в один на один») упирался
# сразу в две проверки: «есть ли план» и «открыта ли группа». Обе отвечали «нельзя».
GI_CONVERTIBLE_PHASES = GI_OPEN_PHASES + ("below_quorum",)


def _gintents():
    return SESSION.setdefault("_gintents", [])


def _ginvites():
    return SESSION.setdefault("_ginvites", [])


def _gmsgs():
    return SESSION.setdefault("_gmsgs", [])


def _gi_find(gid):
    for g in _gintents():
        if g.get("id") == gid:
            return g
    return None


def _gi_active(g):
    """Members who are actually in the room right now. LEFT and SAFETY_REMOVED stay on the record —
    a roster that forgets people cannot explain why the count changed."""
    return [m for m in (g.get("members") or []) if m.get("state") in ("joined", "active")]


def _gi_pending(gid):
    return [i for i in _ginvites() if i.get("gid") == gid and i.get("state") in ("sent", "viewed")]


def _gi_expire(now=None):
    """Invites go stale. Run before every read and every write, so a seat can never be held by an
    invitation nobody ever answered."""
    now = now or time.time()
    changed = False
    for i in _ginvites():
        if i.get("state") in ("sent", "viewed") and (i.get("expires_at") or 0) and now > i["expires_at"]:
            i["state"] = "expired"
            i["updated"] = now
            changed = True
    return changed


# Что видит приглашённый из плана: когда, в каком виде, сколько согласились. Место, ссылка на
# звонок, заметка и живые статусы участников — только тем, кто внутри (как адрес в 1:1 открывает
# лишь взаимное «да»).
_GP_INVITEE_KEYS = ("id", "gid", "version", "when", "starts_at", "state", "mode",
                    "confirmed_count", "needs", "round", "max_rounds")
# Витрина для постороннего: сама затея и места, без людей и без плана.
_GI_TEASER_KEYS = ("gid", "title", "topics", "when", "area", "mode", "state", "min_total",
                   "max_total", "joined_count", "seats_left", "full", "need_more", "planning_allowed")


# Группа, где уже ничего не происходит: закрыта организатором, распущена, истекла, стала 1:1.
_GI_ENDED = ("closed_by_owner", "cancelled", "expired", "converted_1to1", "done")


def _gi_role(g, me):
    """Кем смотрящий приходится группе: owner | member | invitee | stranger. По id (docs/IDENTITY.md)."""
    mine = _norm_name(me)
    if not mine or not g:
        return "stranger"
    if mine == _norm_name(g.get("owner")):
        return "owner"
    if any(_norm_name(m.get("name")) == mine for m in _gi_active(g)):
        return "member"
    if any(i.get("gid") == g.get("id") and _norm_name(i.get("to")) == mine
           and i.get("state") in ("sent", "viewed", "awaiting_approval") for i in _ginvites()):
        return "invitee"
    if any(_norm_name(m.get("name")) == mine and m.get("safety_exit") for m in g.get("members") or []):
        return "former"                    # ушёл по жалобе (S11): своя история только для чтения
    return "stranger"


def _gi_public(g, me=""):
    """Группа глазами того, кто спрашивает, — по его месту в ней.

    Организатор и участники получают всё. Приглашённый — состав и места (экран приглашения обещает
    показать «кто уже внутри»), а из плана только время и вид встречи. Все остальные — витрину.

    ЗАЧЕМ. До 27.09.2026 группа уходила целиком любому: `/api/agent/gintent?gid=` не спрашивал даже
    входа, а id групп лежат в открытой ленте карты. Посторонний видел, кто, когда и ГДЕ
    встречается, и ссылку на звонок."""
    role = _gi_role(g, me)
    full = _gi_full(g, me)
    if role in ("owner", "member"):
        return full
    if role == "former":
        return dict({k: full.get(k) for k in _GI_TEASER_KEYS}, i_am_owner=False, i_am_member=False,
                    read_only=True, read_only_reason="left",
                    removal_notice={"title": g.get("title") or ""})
    if role == "invitee":
        plan = full.get("plan")
        if isinstance(plan, dict):
            full["plan"] = {k: plan.get(k) for k in _GP_INVITEE_KEYS if k in plan}
        # Внутренние дела группы (кто молчит, кто за кого голосует) приглашённому не показываем.
        for k in ("takeover", "role_offer", "role_from", "organiser_silent_h", "can_take_over", "can_hand_over"):
            full.pop(k, None)
        return full
    return dict({k: full.get(k) for k in _GI_TEASER_KEYS}, i_am_owner=False, i_am_member=False)


def _gi_full(g, me=""):
    """What a client may see. The roster is names and states — never contact details, and never a
    per-member action, because there is no per-member action to offer."""
    act = _gi_active(g)
    n = len(act)
    mine = _norm_name(me)
    is_owner = bool(mine) and mine == _norm_name(g.get("owner"))
    # Открытые приглашения — ТОЛЬКО организатору: это его экран «Invites sent» (GR.17), со
    # строкой и Cancel на каждого. Участникам список не показывается — GR.16 обещает приглашённому
    # «who is already in», а не «кого ещё позвали».
    # Время отправки и срок едут вместе со строкой: полоса «Ends in …» и «Invite sent ⏱» (GR.14–17).
    invites = [{"id": i.get("id"), "to": i.get("to"), "state": i.get("state"),
                "at": i.get("created"), "expires_at": i.get("expires_at")}
               for i in _ginvites()
               if i.get("gid") == g.get("id") and i.get("state") in ("sent", "viewed",
                                                                     "awaiting_approval")] \
        if is_owner else None
    # ЗАКРЫТЫЕ ПРИГЛАШЕНИЯ — ОТДЕЛЬНЫМ ПОЛЕМ, и тоже только организатору (03.10.2026, борд GR.14d/14e):
    # карточка «Can't make it» / «Invite closed» раньше угадывалась клиентом по пропаже строки и
    # жила до перезапуска. В `invites` их класть нельзя: его длину читают как «открытых» (gmembers,
    # group, смоуки). Состояние переведено в словарь клиента (src/ginvites.ts CLOSED_STATES), сырое —
    # в `reason`. Принятые не отдаются: человек в `members`.
    closed = None
    if is_owner:
        rows = sorted((i for i in _ginvites() if i.get("gid") == g.get("id")
                       and i.get("state") in _GI_INVITE_OUTCOME), key=lambda i: i.get("updated") or 0)
        # «withdrawn» ставят ТРИ пути: отмена организатором (gi_invite_cancel), ответ в уже
        # закончившуюся группу (gi_respond) и переход в 1:1 (там же note_out). Клиент читает
        # withdrawn как «организатор отменил, место свободно» (GR.14b) — значит, отдаём его только
        # пока группа жива и без note_out; иначе это закрытие.
        ended = g.get("state") in _GI_ENDED

        def outcome(i):
            st = i.get("state")
            if st == "withdrawn" and (ended or i.get("note_out")):
                return "closed"
            return _GI_INVITE_OUTCOME[st]

        closed = [{"id": i.get("id"), "to": i.get("to"), "state": outcome(i),
                   "reason": i.get("state"), "at": i.get("created"), "expires_at": i.get("expires_at"),
                   "closed_at": i.get("updated")} for i in rows[-50:]]
    return {
        "gid": g.get("id"), "title": g.get("title"), "topics": g.get("topics") or [],
        "when": g.get("when") or "", "area": g.get("area") or "", "mode": g.get("mode") or "offline",
        "owner": g.get("owner"), "state": g.get("state"),
        "min_total": g.get("min_total"), "max_total": g.get("max_total"),
        # Время входа и возраст — строка участника на борде «GR · Offline — new layout»: «Jane, 28»
        # и «In the group since ⏱ 14:28» (GR.24, GR.24a). Время создания — первая строка ленты
        # «You created BBQ by the beach meetup ⏱ 14:24» (GR.18) и «Created the group» у организатора.
        "members": [{"name": m.get("name"), "state": m.get("state"),
                     "photo": _photo_of(m.get("name")), "joined": m.get("joined"),
                     "joined_at": m.get("joined"),                  # имя, которое читает src/ginvites.ts
                     "age": (_person(m.get("name")) or {}).get("age")} for m in act],
        "created": g.get("created"),
        # Дата и время затеи как их выбрали в мастере: лист «Send the plan?» (GR.25) предлагает
        # план ровно на них одним нажатием, без повторного выбора.
        "date_key": (g.get("intent") or {}).get("dateKey") or "",
        "minutes": (g.get("intent") or {}).get("minutes"),
        # ВЫБЫВШИЕ отдаются отдельно и со временем ухода. Кадр GR.39 — «Jane left the plan» —
        # построить без этого нечем: состав наружу шёл только активный, вышедший исчезал бесследно,
        # и объяснить, почему людей стало меньше, экрану было нечем. В самой строке участника
        # время ухода лежало всё это время (`left`), просто наружу не выходило.
        "departed": [{"name": m.get("name"), "state": m.get("state"), "left": m.get("left"),
                      "joined": m.get("joined"), "photo": _photo_of(m.get("name")),
                      "age": (_person(m.get("name")) or {}).get("age")}
                     for m in (g.get("members") or [])
                     if m.get("state") in ("left", "removed", "safety_removed") and m.get("left")],
        "joined_count": n,
        "pending_count": len(_gi_pending(g.get("id"))),
        # People who accepted after planning started and are waiting on the organiser. Surfaced on
        # the group object because there is no other screen where the organiser would find them.
        "awaiting_approval": [i.get("to") for i in _ginvites()
                              if i.get("gid") == g.get("id") and i.get("state") == "awaiting_approval"],
        "seats_left": max(0, int(g.get("max_total") or GI_MAX_TOTAL) - n),
        "invite_cap": GI_OPEN_INVITE_CAP,
        **({"invites": invites} if invites is not None else {}),
        **({"invites_closed": closed} if closed is not None else {}),
        # ТОЧНЫЙ АДРЕС ВСТРЕЧИ — ТОЛЬКО ОРГАНИЗАТОРУ (борд «GR · Offline — new layout», GR.44/44h, 04.10.2026):
        # он сам его назвал в мастере (intent.address). Остальные до общего согласия видят район —
        # «Exact spot after everyone confirms»; адрес им открывает план после подтверждения.
        # …и БЫВШЕМУ организатору, пока он в комнате (GR.44f/44l, 06.10.2026): он назвал это место сам,
        # роль передал — адрес не забыл. Ушёл из группы — адреса больше нет.
        **({"address": str((g.get("intent") or {}).get("address") or "")[:200]}
           if (is_owner or (bool(mine) and mine == _norm_name((g.get("role_from") or {}).get("who"))
                            and any(_norm_name(m.get("name")) == mine for m in act))) else {}),
        "i_am_owner": is_owner,
        "i_am_member": any(_norm_name(m.get("name")) == mine for m in act),
        # §6.6/§6.7: the ONE thing the screen keys off. Below the floor the chat is a coordination
        # room and nothing more; the plan CTA is disabled with a reason, never hidden.
        # ПЕРЕХОД В ОДИН НА ОДИН (GR.19/GR.20). Оба поля нужны на РАЗНЫХ сторонах: организатору —
        # можно ли предложить, второму — что предложение уже пришло и ждёт ответа. Без второго
        # экран приглашённого не знал бы о просьбе вовсе.
        "can_convert": is_owner and n == 2
                       and g.get("state") in GI_CONVERTIBLE_PHASES
                       and not _gp_blocks_convert(g.get("id"))
                       and not g.get("pending_1to1"),
        "pending_1to1": g.get("pending_1to1"),
        # S10: «Завершить группу» — организатору и только пока плана нет совсем.
        "can_end": is_owner and not _gp_of(g.get("id")) and g.get("state") not in _GI_ENDED,
        **({"read_only": True, "read_only_reason": "group_closed",
            "closure_notice": {"owner": g.get("closed_by") or g.get("owner"), "title": g.get("title") or ""}}
           if g.get("state") == "closed_by_owner" else {}),
        "planning_allowed": n >= int(g.get("min_total") or GI_MIN_TOTAL)
                            and g.get("state") not in _GI_ENDED,
        "need_more": max(0, int(g.get("min_total") or GI_MIN_TOTAL) - n),
        "full": n >= int(g.get("max_total") or GI_MAX_TOTAL),
        "plan": _gp_public(_gp_of(g.get("id")), me),
        # GR.40b / 40e: план, закрытый с паузы, ещё сутки виден на своей странице — отдельным полем,
        # чтобы чат и карточка затеи не приняли отменённое за живой план.
        "closed_plan": (None if _gp_of(g.get("id")) else _gp_public(_gp_hold_closed_recent(g.get("id")), me)),
        # GR.42–44: молчание организатора, голосование за перехват, предложение роли.
        **_gi_role_public(g, me),
    }


def _gi_say(g, text, kind="system", code=None, **fields):
    """System messages ARE the group's history — «X joined», «time changed» — so they live in the
    same thread as everything else rather than in a side channel the next joiner cannot see.

    THE ROW CARRIES A CODE AND ITS FACTS, not only a rendered sentence. The English text stays as
    the fallback (previews, older clients, anything that just prints the last line), but the screen
    should read `sys`: a group is one history for everyone, and the interface language is personal.

    Why this was added. The client used to recognise these lines by REGEX over English text
    (`groupSysLine` in src/groups.ts). It covered five phrases out of twenty-seven, and one of the
    misses is the one that matters most: «X left. Y is now the organiser» does not match
    `^(.+?) left the group$`, so a Russian screen printed it in English. Worse, the failure is
    silent — reword a sentence here and the client stops recognising it without a single error.

    `text` stays the first positional argument on purpose: every existing call keeps working
    untouched, and a call without a code degrades to exactly the old behaviour.
    """
    # В строке и в полях участники — id (docs/IDENTITY.md). Текст — для людей, поэтому id в нём
    # заменяются подписями СЕЙЧАС (строка — снимок момента); поля остаются id и переводятся при выдаче.
    cands = {str(m.get("name") or "") for m in (g.get("members") or [])} | {str(g.get("owner") or "")}
    for v in fields.values():
        if isinstance(v, str):
            cands.update(x.strip() for x in v.split(","))
    for pid in sorted((x for x in cands if x and _is_pid(x)), key=len, reverse=True):
        text = text.replace(pid, _display(pid))
    if isinstance(fields.get("names"), str):
        fields = dict(fields, names=", ".join(_display(x.strip(), x.strip())
                                              for x in fields["names"].split(",") if x.strip()))
    row = {"id": "gm_%d_%s" % (int(time.time() * 1000), hashlib.sha1(text.encode("utf-8")).hexdigest()[:4]),
           "gid": g.get("id"), "frm": "", "text": text, "t": time.time(), "kind": kind}
    if code:
        row["sys"] = dict({"code": str(code)}, **{k: v for k, v in fields.items() if v is not None})
    _gmsgs().append(row)


def gi_create(owner, intent, title="", min_total=None, max_total=None, idem=None):
    """Open a group intent. The organiser is member number one from the very first moment — §1 counts
    them in the minimum, so a roster that started empty would make «3 total» mean four people."""
    owner = str(owner or "").strip()
    if not owner:
        return {"ok": False, "error": "owner required"}
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    intent = _prepare_map_intent(_display(owner, owner), intent if isinstance(intent, dict) else {},
                                 owner_id=_canon_pid(owner))
    try:
        mn = int(min_total or GI_MIN_TOTAL)
    except (TypeError, ValueError):
        mn = GI_MIN_TOTAL
    try:
        mx = int(max_total or GI_MAX_TOTAL)
    except (TypeError, ValueError):
        mx = GI_MAX_TOTAL
    mn = max(GI_MIN_TOTAL, mn)
    mx = max(mn, min(GI_MAX_TOTAL, mx))
    now = time.time()
    with _STORE_LOCK:
        gid = "gi_%d_%s" % (int(now * 1000), hashlib.sha1(owner.encode("utf-8")).hexdigest()[:6])
        g = {"id": gid, "owner": owner, "intent": intent,
             "title": str(title or intent.get("title") or "").strip()[:120] or "Meetup",
             "topics": [str(t).lower() for t in (intent.get("topics") or [])][:6],
             "when": str(intent.get("time") or "")[:80],
             "area": str(intent.get("place") or intent.get("area") or "")[:80],
             "mode": str(intent.get("mode") or "offline"),
             "min_total": mn, "max_total": mx,
             "state": "searching",           # §7: SEARCHING -> CHAT_OPEN -> READY_TO_PLAN -> ...
             "members": [{"name": owner, "state": "joined", "joined": now}],
             "created": now, "updated": now, "version": 1}
        _gintents().append(g)
        _save_store()
        return _idem_put(idem, {"ok": True, "group": _gi_public(g, owner)})


def gi_invite_many(gid, frm, names, note="", idem=None):
    """Invite the slate. The organiser sends to everyone matching showed them — «отправить 10
    инвайтов» — so the CALL takes a list, while every check stays per candidate: one person being
    blocked, already invited or already in must not cost the other nine their invitation.

    The answer is per candidate too. A batch that silently half-failed would leave the organiser
    thinking ten people were asked when three were."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    names = [n for n in (names or []) if str(n or "").strip()]
    if not names:
        return {"ok": False, "error": "no candidates"}
    sent, refused = [], []
    for n in names:
        if str(n).startswith("?"):
            # Не опознан: такого нет или это тёзки без id — звать наугад нельзя.
            refused.append({"to": str(n)[1:], "error": "UNKNOWN_OR_AMBIGUOUS_PERSON"})
            continue
        r = gi_invite(gid, frm, n, note, None)
        if r.get("ok"):
            sent.append({"to": n, "id": (r.get("invite") or {}).get("id")})
        else:
            refused.append({"to": n, "error": r.get("error"), "reason": r.get("reason")})
    g = _gi_find(gid)
    out = {"ok": bool(sent), "sent": sent, "refused": refused,
           "group": _gi_public(g, frm) if g else None}
    return _idem_put(idem, out)


def gi_invite(gid, frm, to, note="", idem=None):
    """Invite ONE candidate — the unit every check works on. Everything that could have changed since
    the slate was drawn is checked here, and checked again at accept, because the group can fill in
    between."""
    frm, to = str(frm or "").strip(), str(to or "").strip()
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    if not frm or not to or _norm_name(frm) == _norm_name(to):
        return {"ok": False, "error": "sender and recipient required and must differ"}
    now = time.time()
    with _STORE_LOCK:
        _gi_expire(now)
        g = _gi_find(gid)
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if _norm_name(frm) != _norm_name(g.get("owner")):
            return {"ok": False, "error": "NOT_ORGANIZER"}
        if g.get("state") in ("cancelled", "expired", "converted_1to1"):
            return _idem_put(idem, {"ok": False, "error": "CLOSED", "gid": gid})
        # Recruitment is NOT locked during planning. The daily keeps inviting open and moves the
        # gate to acceptance instead: a person who accepts once a plan is being confirmed waits for
        # the organiser's approval rather than walking into the roster mid-confirmation. Two hours
        # before the meeting everything stops — that is the only hard freeze.
        if g.get("state") in ("locked", "done"):
            return _idem_put(idem, {"ok": False, "error": "LOCKED", "gid": gid})
        act = _gi_active(g)
        if any(_norm_name(m.get("name")) == _norm_name(to) for m in act):
            return _idem_put(idem, {"ok": False, "error": "ALREADY_MEMBER", "gid": gid})
        if len(act) >= int(g.get("max_total") or GI_MAX_TOTAL):
            return _idem_put(idem, {"ok": False, "error": "GROUP_FULL", "gid": gid})
        pend = _gi_pending(gid)
        if any(_norm_name(i.get("to")) == _norm_name(to) for i in pend):
            return _idem_put(idem, {"ok": False, "error": "ALREADY_INVITED", "gid": gid})
        # Продуктовый кап борда, не предохранитель: больше трёх ждущих ответа приглашений у группы
        # не бывает (GR.15). Выход из капа — отменить одно (gi_invite_cancel) или дождаться ответа.
        if len(pend) >= GI_OPEN_INVITE_CAP:
            return _idem_put(idem, {"ok": False, "error": "INVITE_CAP", "gid": gid,
                                    "cap": GI_OPEN_INVITE_CAP})
        # Deliberately NO "forecast" check here — outstanding invites do NOT reserve seats. Blocking
        # an invite because everyone MIGHT say yes sounds prudent and is wrong: §20 requires the case
        # where two candidates accept the last seat at the same moment to be handled, and a forecast
        # makes that case unreachable, so the atomic claim below would never be exercised in real
        # use. Over-inviting is bounded by the pending cap above; who actually gets in is decided by
        # the claim at accept, which is the only count that can be authoritative.
        # pairwise safety, against every person already in the room — not only the organiser
        mine = (SESSION.get("me") or {}).get("blocked") or []
        for m in act:
            ok, why = _policy_ok_now(to, m.get("name"), mine)
            if not ok:
                return _idem_put(idem, {"ok": False, "error": "NOT_ELIGIBLE", "reason": why})
        inv = {"id": "gv_%d_%s" % (int(now * 1000), hashlib.sha1((gid + to).encode("utf-8")).hexdigest()[:6]),
               "gid": gid, "frm": frm, "to": to, "note": str(note or "")[:400],
               "state": "sent", "created": now, "updated": now,
               "expires_at": now + GI_INVITE_TTL,
               "intent_version": int(g.get("version") or 1)}
        _ginvites().append(inv)
        g["updated"] = now
        _save_store()
        return _idem_put(idem, {"ok": True, "invite": {"id": inv["id"], "to": to, "state": "sent"},
                                "group": _gi_public(g, frm)})


def gi_respond(inv_id, who, accept, idem=None):
    """Accept or decline. Accepting is one transaction: revalidate, claim a seat, become a member and
    get chat access — all under the lock, so two people racing for the last seat cannot both win and
    nobody ever sees the thread without holding a place in it."""
    who = str(who or "").strip()
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    now = time.time()
    with _STORE_LOCK:
        _gi_expire(now)
        inv = next((i for i in _ginvites() if i.get("id") == inv_id), None)
        if not inv:
            return {"ok": False, "error": "NO_SUCH_INVITE"}
        if _norm_name(inv.get("to")) != _norm_name(who):
            return {"ok": False, "error": "NOT_YOURS"}
        if inv.get("state") not in ("sent", "viewed"):
            return _idem_put(idem, {"ok": False, "error": inv.get("state", "").upper() or "CLOSED",
                                    "invite": {"id": inv_id, "state": inv.get("state")}})
        g = _gi_find(inv.get("gid"))
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if not accept:
            inv["state"] = "declined"; inv["updated"] = now
            # ОТКАЗ ГОВОРИТСЯ ВСЛУХ. Он проходил молча: строка отказавшегося пропадала из
            # _gi_public (наружу идут только sent|viewed|awaiting_approval), версия группы не
            # росла, и экран организатора даже не перерисовывался. Человек видел «2 из 3» и не
            # понимал, ждать ему или звать другого — а третий уже ответил «нет».
            _gi_say(g, "%s can\'t make it." % inv.get("to"), code="cant_make_it", who=inv.get("to"))
            g["version"] = int(g.get("version") or 1) + 1
            g["updated"] = now
            _save_store()
            return _idem_put(idem, {"ok": True, "invite": {"id": inv_id, "state": "declined"}})
        if g.get("state") in ("cancelled", "expired", "converted_1to1"):
            inv["state"] = "withdrawn"; inv["updated"] = now
            _save_store()
            return _idem_put(idem, {"ok": False, "error": "CLOSED", "gid": g.get("id")})
        act = _gi_active(g)
        if any(_norm_name(m.get("name")) == _norm_name(who) for m in act):
            return _idem_put(idem, {"ok": True, "already": True, "group": _gi_public(g, who)})
        # THE atomic claim. Capacity is re-read here rather than trusted from send time.
        if len(act) >= int(g.get("max_total") or GI_MAX_TOTAL):
            inv["state"] = "group_full"; inv["updated"] = now
            _save_store()
            return _idem_put(idem, {"ok": False, "error": "GROUP_FULL", "gid": g.get("id")})
        mine = (SESSION.get("me") or {}).get("blocked") or []
        for m in act:
            ok, why = _policy_ok_now(who, m.get("name"), mine)
            if not ok:
                inv["state"] = "policy_revoked"; inv["updated"] = now
                _save_store()
                return _idem_put(idem, {"ok": False, "error": "NOT_ELIGIBLE", "reason": why})
        # «Все остальные люди также без ограничений сразу проваливаются в группу, но только в тот
        # момент, когда у нас статус нашей встречи именно "инвайт".» Once a plan is being confirmed
        # the roster is what people are confirming AGAINST, so a late acceptance waits for approval.
        if g.get("state") not in GI_OPEN_PHASES:
            inv["state"] = "awaiting_approval"; inv["updated"] = now
            _save_store()
            return _idem_put(idem, {"ok": True, "awaiting_approval": True, "gid": g.get("id"),
                                    "note": "the organiser approves joiners once planning has started"})
        inv["state"] = "accepted"; inv["updated"] = now
        g.setdefault("members", []).append({"name": who, "state": "joined", "joined": now})
        _gp_recount(g.get("gid"), now)     # тот же пересчёт, что и при одобрении организатором
        n = len(_gi_active(g))
        # §7 state: the thread opens on the FIRST acceptance and is the same thread from then on.
        if g.get("state") == "searching":
            g["state"] = "chat_open"
        if n >= int(g.get("min_total") or GI_MIN_TOTAL) and g.get("state") == "chat_open":
            g["state"] = "ready_to_plan"
        g["updated"] = now
        g["version"] = int(g.get("version") or 1) + 1
        _gi_say(g, "%s joined the group." % who, code="joined", who=who)
        if n == int(g.get("min_total") or GI_MIN_TOTAL):
            _gi_say(g, "You have enough people to make a plan.", code="quorum_reached")
        # Every remaining invite is re-checked against the new capacity: once the room is full the
        # people still holding an invitation are told so, instead of finding out by tapping Join.
        if n >= int(g.get("max_total") or GI_MAX_TOTAL):
            for i in _gi_pending(g.get("id")):
                i["state"] = "group_full"; i["updated"] = now
            _gi_say(g, "This group is full. Pending invites are no longer available.", code="group_full")
        _save_store()
        return _idem_put(idem, {"ok": True, "gid": g.get("id"), "group": _gi_public(g, who)})


def gi_invite_cancel(inv_id, frm, idem=None):
    """Withdraw an OPEN invite — the Cancel on every GR.17 row, and the way out of the three-open
    cap that GR.15 offers by name («Cancel one»). Only the organiser, and only while the invite is
    still unanswered: a person who already accepted is a member (leaving is theirs to do), and one
    who is awaiting approval is decided by gi_approve(accept=False), not by yanking the invite."""
    frm = str(frm or "").strip()
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    now = time.time()
    with _STORE_LOCK:
        _gi_expire(now)
        inv = next((i for i in _ginvites() if i.get("id") == inv_id), None)
        if not inv:
            return {"ok": False, "error": "NO_SUCH_INVITE"}
        g = _gi_find(inv.get("gid"))
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if _norm_name(frm) != _norm_name(g.get("owner")):
            return {"ok": False, "error": "NOT_ORGANIZER"}
        if inv.get("state") not in ("sent", "viewed"):
            # Уже отвечено/сгорело — состояние называется по имени, как в gi_respond: ошибка
            # «ACCEPTED» говорит организатору правду, а не абстрактное «нельзя».
            return _idem_put(idem, {"ok": False, "error": inv.get("state", "").upper() or "CLOSED",
                                    "invite": {"id": inv_id, "state": inv.get("state")}})
        inv["state"] = "withdrawn"
        inv["updated"] = now
        # Приглашённому — тишина, а не сообщение в чат: он в комнате не был, писать ему некуда.
        # Его сторона просто перестаёт видеть приглашение (gi_for отдаёт только живые), а попытка
        # принять по старой ссылке честно ответит WITHDRAWN — это уже умеет gi_respond.
        _save_store()
        return _idem_put(idem, {"ok": True, "invite": {"id": inv_id, "state": "withdrawn"},
                                "group": _gi_public(g, frm)})


def gi_close(gid, who, idem=None):
    """S10 / GR.53-55: организатор закрывает группу, ПОКА ПЛАНА НЕТ.

    Договор — tools/s10_group_close_unit.py (с 18.08.2026). Серверной половины не было вовсе
    (аудит 27.09.2026): «Завершить группу» в приложении всегда отвечала ошибкой.

    Любой план — даже только предложенный — это уже общее дело, и закрыть группу поверх него
    нельзя: PLAN_EXISTS (кнопку экран прячет по `can_end`). Группа становится `closed_by_owner`:
    участники сохраняют историю только для чтения, а писать, реагировать, удалять и начинать план
    больше нельзя (CLOSED). Открытые приглашения гаснут нейтрально — `group_closed` с запиской
    «Nothing you did», и приглашённому в переписку с организатором уходит событие
    `group_closed_invite`: иначе он принял бы приглашение в группу, которой уже нет."""
    who = str(who or "").strip()
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    now = time.time()
    with _STORE_LOCK:
        g = _gi_find(gid)
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if _norm_name(who) != _norm_name(g.get("owner")):
            return {"ok": False, "error": "NOT_ORGANIZER"}
        if g.get("state") in _GI_ENDED:
            return _idem_put(idem, {"ok": False, "error": "ALREADY_CLOSED", "group": _gi_public(g, who)})
        if _gp_of(gid):
            return _idem_put(idem, {"ok": False, "error": "PLAN_EXISTS",
                                    "note": "a plan exists — it is changed or cancelled by a vote"})
        title = g.get("title") or ""
        for inv in _ginvites():
            if inv.get("gid") == gid and inv.get("state") in ("sent", "viewed", "awaiting_approval"):
                inv["state"] = "group_closed"
                inv["updated"] = now
                inv["note_out"] = ("The organiser closed %s before a plan was set, so this invite is "
                                   "gone. Nothing you did." % (title or "the group"))
                if inv.get("to"):
                    _sys_msg(who, inv.get("to"), "group_closed_invite", by=who, title=title)
        g["state"] = "closed_by_owner"
        g["closed"] = now
        g["closed_by"] = who
        g["updated"] = now
        g["version"] = int(g.get("version") or 1) + 1
        _gi_say(g, "%s closed the group." % who, code="group_closed", who=who, title=title)
        _save_store()
        return _idem_put(idem, {"ok": True, "gid": gid, "group": _gi_public(g, who)})


# Причины жалобы на группу — ровно те, что предлагает экран (app/group-report.tsx).
# Плюс две причины борда «GR · Offline — new layout» (GR.55): «Unsafe behaviour at the meetup» и
# «Something else». Старые коды остаются: их шлют прежние сборки.
GROUP_REPORT_REASONS = ("inappropriate_behaviour", "insults_or_humiliation", "harassment_or_threats",
                        "fake_profile", "rule_violation", "unsafe_behaviour", "something_else")
# Файлы к жалобам. Папка НЕ раздаётся наружу: читает её только админ-ручка, а её шлюз снаружи
# закрывает. Имя файла — случайное (secrets), не от содержимого и не от времени.
EVIDENCE_DIR = (os.environ.get("KLEAL_REPORT_EVIDENCE_DIR") or os.environ.get("KLEAL_EVIDENCE_DIR")
                or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "evidence"))
MAX_EVIDENCE_BYTES = 12 * 1024 * 1024            # столько обещает экран: «меньше 12 МБ»
EVIDENCE_PER_HOUR = 10
_EVIDENCE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/heic": "heic",
                   "image/gif": "gif", "video/mp4": "mp4", "video/quicktime": "mov",
                   "application/pdf": "pdf", "text/plain": "txt", "application/msword": "doc",
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx"}
_EVIDENCE_URL = re.compile(r"^/api/agent/report-evidence/([0-9a-f]{32})\.([a-z0-9]{2,5})$")


def _evidence():
    return SESSION.setdefault("_evidence", {})


def report_evidence_store(filename, media_type, blob, who=""):
    """Принять файл к будущей жалобе (S11). Договор — tools/s11_group_report_unit.py.

    Кто загрузил — запоминается: чужой файл к своей жалобе не приложить, а стирание учётки уносит
    и эти файлы. URL — только опознаватель: по нему файл наружу НЕ отдаётся (см. админ-ручку)."""
    if not blob:
        return {"ok": False, "error": "EVIDENCE_REQUIRED"}
    if len(blob) > MAX_EVIDENCE_BYTES:
        return {"ok": False, "error": "EVIDENCE_TOO_LARGE"}
    mt = str(media_type or "").split(";")[0].strip().lower()
    ext = _EVIDENCE_TYPES.get(mt)
    if not ext:
        return {"ok": False, "error": "UNSUPPORTED_EVIDENCE_TYPE"}
    now = time.time()
    with _STORE_LOCK:
        if who:
            mine = [e for e in _evidence().values() if e.get("by") == who and now - (e.get("at") or 0) < 3600]
            if len(mine) >= EVIDENCE_PER_HOUR:
                return {"ok": False, "error": "TOO_MANY"}
        eid = secrets.token_hex(16)
        fname = "%s.%s" % (eid, ext)
        os.makedirs(EVIDENCE_DIR, exist_ok=True)
        with open(os.path.join(EVIDENCE_DIR, fname), "wb") as f:
            f.write(blob)
        rec = {"id": eid, "by": who, "name": str(filename or "file")[:120], "mime_type": mt,
               "size": len(blob), "file": fname, "at": now}
        _evidence()[eid] = rec
        _save_store()
    return {"ok": True, "id": eid, "url": "/api/agent/report-evidence/%s" % fname,
            "name": rec["name"], "mime_type": mt, "size": rec["size"]}


def _gi_safety_exit(g, who, now):
    """Выход по жалобе (S11): для комнаты — обычное нейтральное «вышел», без слова о жалобе.
    Роль организатора переходит к первому из оставшихся, кворум пересчитывается. Сам ушедший
    сохраняет историю только для чтения — замороженную на моменте выхода (`gi_thread`)."""
    m = next((x for x in (g.get("members") or [])
              if _norm_name(x.get("name")) == _norm_name(who) and x.get("state") in ("joined", "active")), None)
    if not m:
        return False
    m["state"] = "left"
    m["left"] = now
    m["safety_exit"] = True
    rest = _gi_active(g)
    if _norm_name(who) == _norm_name(g.get("owner")) and rest:
        g["owner"] = sorted(rest, key=lambda x: x.get("joined") or 0)[0].get("name")
    _gi_say(g, "%s left the group." % who, code="left", who=who)
    if len(rest) < int(g.get("min_total") or GI_MIN_TOTAL) and g.get("state") in ("ready_to_plan", "planning"):
        g["state"] = "below_quorum"
    g["updated"] = now
    g["version"] = int(g.get("version") or 1) + 1
    _gp_recount(g.get("id"), now)
    return True


def gi_report(gid, who, reason, text="", evidence=None, idem=None, about=""):
    """S11: жалоба на группу и безопасный выход из неё. Договор — tools/s11_group_report_unit.py.

    Серверной половины не было (аудит 27.09.2026): экран жалобы всегда отвечал «не удалось
    отправить». Жалоба ложится в общую очередь модератора (`_reports`, `source: group_s11`);
    подробности в комнату не попадают. Жалующийся тут же выходит из группы (`_gi_safety_exit`).
    Приложить можно только файлы, загруженные к нам (`/api/agent/report-evidence/…`), и не чужие."""
    who = str(who or "").strip()
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    rs = str(reason or "").strip().lower()
    if rs not in GROUP_REPORT_REASONS:
        return {"ok": False, "error": "INVALID_REASON", "reasons": list(GROUP_REPORT_REASONS)}
    now = time.time()
    with _STORE_LOCK:
        g = _gi_find(gid)
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        me = _norm_name(who)
        in_room = any(_norm_name(m.get("name")) == me for m in _gi_active(g))
        was_in = in_room or any(_norm_name(m.get("name")) == me for m in g.get("members") or [])
        if not me or not was_in:
            return {"ok": False, "error": "NOT_A_MEMBER"}
        ev = []
        for x in evidence or []:
            if not isinstance(x, dict):
                continue
            mt = _EVIDENCE_URL.match(str(x.get("url") or ""))
            if not mt:
                continue                           # чужой адрес — не наш файл, отбрасываем
            rec = _evidence().get(mt.group(1))
            if rec and rec.get("by") and _norm_name(rec.get("by")) != me:
                continue                           # чужой загруженный файл к своей жалобе не приложить
            ev.append({"id": mt.group(1), "url": str(x.get("url")),
                       "name": str((rec or {}).get("name") or x.get("name") or "file")[:120],
                       "mime_type": str((rec or {}).get("mime_type") or x.get("mime_type") or ""),
                       "size": int((rec or {}).get("size") or _num(x.get("size")) or 0)})
        rid = "rg_%d_%s" % (int(now * 1000), secrets.token_hex(3))
        case_no = "KLEAL-%s" % rid[-6:].upper()
        rows = _reports()
        # ЖАЛОБА НА ЧЕЛОВЕКА (GR.55 «Who is this about?»). Он должен быть или быть в этой группе:
        # жаловаться через группу на постороннего нельзя. Защита тогда — не выход жалующегося из
        # группы, а стена между двумя (GR.55a «Marc can't message you · can't see your profile ·
        # won't be matched again»): это блокировка, и включается она сразу, до решения модерации.
        about = str(about or "").strip()
        if about:
            known = {_norm_name(m.get("name")) for m in g.get("members") or []}
            if _norm_name(about) not in known or _norm_name(about) == me:
                return {"ok": False, "error": "NOT_IN_GROUP"}
        rows.append({"id": rid, "kind": "group", "source": "group_s11", "gid": gid,
                     "group_title": g.get("title") or "", "by": who, "about": about, "reason": rs,
                     "text": str(text or "")[:2000], "evidence": ev, "case_no": case_no,
                     "at": now, "state": "received"})
        del rows[:-2000]
        exited = _gi_safety_exit(g, who, now) if in_room and not about else False
        _save_store()
    measures = ["left_group"] if exited else []
    if about:
        # Вне замка хранилища: block_user берёт его сам, а замок не повторный.
        block_user(who, about, True)
        measures = ["no_messages", "profile_hidden", "no_match"]
    return _idem_put(idem, {"ok": True, "id": rid, "case_no": case_no, "status": "received", "at": now,
                            "protective_measures": measures, "about": about,
                            "group": _gi_public(g, who)})


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# СМЕНА ОРГАНИЗАТОРА — борд «GR · Offline — new layout», кадры GR.42–GR.44 (29.09.2026)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Два пути, и оба — ДО плана: организатор делает план, и пока плана нет, группа может остаться
# без того, кто его сделает.
#
#  1) ПЕРЕХВАТ ПО ГОЛОСОВАНИЮ (GR.42–43). Группа собрана, плана нет, организатор молчит 12 часов
#     («Silent for 12h»). Любой участник может предложить себя. Голосуют остальные, кроме
#     организатора и самого кандидата; окно — 6 часов; решают ОТВЕТИВШИЕ (молчание не «за» и не
#     «против»), ничья и «никто не ответил» — не прошло. В отличие от голосования по плану, это
#     решает само: совещаться не с кем, организатор молчит. Организатор может вернуться до конца —
#     оставить роль (голосование остановлено) или сразу отдать её кандидату. Одно предложение за раз.
#  2) ПЕРЕДАЧА РОЛИ (GR.44). Организатор сам предлагает роль одному участнику; тот берёт или
#     отказывается; 24 часа без ответа — роль остаётся. Пока не взяли, ничего не меняется.
#
# Бывший организатор остаётся в группе (и может выйти сам). Роль переходит полем `owner`: все
# права экрана и сервера уже читаются из него, второго признака «кто главный» не заводим.
GI_SILENT_AFTER = 12 * 3600
GI_TAKEOVER_WINDOW = 6 * 3600
GI_ROLE_OFFER_WINDOW = 24 * 3600


def _gi_ready_at(g):
    """Когда группа собралась (минимум людей) — от этого момента считается молчание организатора."""
    act = sorted(float(m.get("joined") or 0) for m in _gi_active(g))
    mn = int(g.get("min_total") or GI_MIN_TOTAL)
    return act[mn - 1] if len(act) >= mn else 0.0


def _gi_owner_active_at(g):
    """Последнее действие организатора в группе: реплика в чате или любая его ручка группы."""
    owner = _norm_name(g.get("owner"))
    t = max(float(g.get("owner_active") or 0), float(g.get("owner_since") or 0))
    for m in reversed(_gmsgs()):
        if m.get("gid") == g.get("id") and _norm_name(m.get("frm")) == owner:
            t = max(t, float(m.get("t") or 0))
            break
    return t


def _gi_silent_for(g, now=None):
    """Сколько секунд организатор молчит в собранной группе без плана; 0 — не тот случай."""
    now = now or time.time()
    if not g or g.get("state") in _GI_ENDED or _gp_of(g.get("id")):
        return 0.0
    ready = _gi_ready_at(g)
    if not ready:
        return 0.0
    return max(0.0, now - max(ready, _gi_owner_active_at(g)))


def _gi_touch_owner(g, who, now=None):
    """Организатор что-то сделал в группе — он не молчит."""
    if g and _norm_name(who) == _norm_name(g.get("owner")):
        g["owner_active"] = now or time.time()


def _gi_takeover_voters(g, t):
    # Организатор — тот, кого переизбирали (t["owner"]), а не нынешний: после перехвата роль уже у
    # кандидата, и счёт «1 из 1» не должен превращаться в «1 из 2» с бывшим организатором в ждущих.
    owner, cand = _norm_name(t.get("owner") or g.get("owner")), _norm_name(t.get("by"))
    return [m.get("name") for m in _gi_active(g) if _norm_name(m.get("name")) not in (owner, cand)]


def _gi_transfer(g, new_owner, now, how):
    prev = g.get("owner")
    g["owner"] = new_owner
    g["role_from"] = {"who": prev, "how": how, "at": now}
    g["owner_since"] = now
    g["owner_active"] = now
    g["updated"] = now
    g["version"] = int(g.get("version") or 1) + 1
    offer = g.get("role_offer")
    if offer and offer.get("state") == "open":
        offer.update(state="closed", closed=now, why="role_changed")


def _gi_roles_due(now=None):
    """Провести то, что наступает само: конец голосования за перехват, истёкшее предложение роли и
    строку «X hasn't made the plan for 12h» в чате. Зовётся на КАЖДОМ чтении групп (_gp_sweep)."""
    now = now or time.time()
    changed = False
    for g in _gintents():
        if g.get("state") in _GI_ENDED:
            continue
        t = g.get("takeover")
        if t and t.get("state") == "open":
            votes = t.get("votes") or {}
            voters = _gi_takeover_voters(g, t)
            # Закрывается ТОЛЬКО по сроку, даже если все уже ответили (борд GR.43k: «счётчик 1/1,
            # таймер идёт»): все шесть часов у организатора есть право вернуться. Исключение —
            # голосовать некому: тогда ждать нечего.
            if now >= float(t.get("closes") or 0) or not voters:
                yes = sum(1 for v in votes.values() if v)
                no = len(votes) - yes
                t["result"] = {"yes": yes, "no": no, "silent": max(0, len(voters) - len(votes))}
                t["resolved"] = now
                prev = g.get("owner")
                if yes > no and any(_norm_name(m.get("name")) == _norm_name(t.get("by")) for m in _gi_active(g)):
                    t["state"] = "passed"
                    _gi_transfer(g, t.get("by"), now, "vote")
                    _gi_say(g, "%s is the organiser now." % t.get("by"), code="takeover_passed",
                            who=t.get("by"), former=prev, yes=yes, no=no)
                else:
                    t["state"] = "failed"
                    _gi_say(g, "%s stays the organiser." % prev, code="takeover_failed",
                            who=t.get("by"), owner=prev, yes=yes, no=no)
                changed = True
        o = g.get("role_offer")
        if o and o.get("state") == "open" and now >= float(o.get("expires") or 0):
            o.update(state="expired", closed=now)
            changed = True
        silent = _gi_silent_for(g, now)
        mark = round(max(_gi_ready_at(g), _gi_owner_active_at(g)), 3)
        if silent >= GI_SILENT_AFTER and g.get("silent_said") != mark and not (t and t.get("state") == "open"):
            g["silent_said"] = mark
            _gi_say(g, "%s hasn't made the plan for 12h." % g.get("owner"), code="organiser_silent",
                    who=g.get("owner"), hours=int(silent // 3600))
            changed = True
    return changed


def _gi_role_public(g, me, now=None):
    """Смена организатора глазами смотрящего: что сейчас идёт и что ему можно сделать."""
    now = now or time.time()
    mine = _norm_name(me)
    owner = _norm_name(g.get("owner"))
    active = [m.get("name") for m in _gi_active(g)]
    in_room = any(_norm_name(n) == mine for n in active)
    silent = _gi_silent_for(g, now)
    out = {"organiser_silent_h": int(silent // 3600) if silent >= GI_SILENT_AFTER else 0}
    t = g.get("takeover")
    if t:
        votes = t.get("votes") or {}
        voters = _gi_takeover_voters(g, t)
        out["takeover"] = {
            "id": t.get("id"), "by": t.get("by"), "state": t.get("state"),
            "started": t.get("at"), "closes_at": t.get("closes"), "resolved": t.get("resolved"),
            "voters": len(voters), "voted": len([v for v in voters if v in votes]),
            "waiting": [v for v in voters if v not in votes],
            "my_vote": votes.get(next((v for v in votes if _norm_name(v) == mine), ""), None),
            "i_vote": any(_norm_name(v) == mine for v in voters),
            "result": t.get("result"), "why": t.get("why"),
            "silent_h": int(max(0.0, now - float(t.get("silent_since") or now)) // 3600),
        }
    o = g.get("role_offer")
    if o:
        out["role_offer"] = {"to": o.get("to"), "by": o.get("by"), "state": o.get("state"),
                             "at": o.get("at"), "expires_at": o.get("expires"), "why": o.get("why"),
                             # Когда закрылось — итог («Nobody took the role») показывается сутки от
                             # закрытия, а не от предложения: истёкшее старше суток с самого начала.
                             "closed_at": o.get("closed"),
                             "declined": o.get("declined") or []}
    if g.get("role_from"):
        out["role_from"] = dict(g["role_from"])
    open_t = bool(t and t.get("state") == "open")
    open_o = bool(o and o.get("state") == "open")
    no_plan = not _gp_of(g.get("id")) and g.get("state") not in _GI_ENDED
    out["can_take_over"] = (no_plan and in_room and mine != owner and not open_t and not open_o
                            and silent >= GI_SILENT_AFTER)
    out["can_hand_over"] = no_plan and mine == owner and not open_t and not open_o and len(active) >= 2
    return out


def _gi_role_guard(g, who):
    if not g:
        return {"ok": False, "error": "NO_SUCH_GROUP"}
    if g.get("state") in _GI_ENDED:
        return {"ok": False, "error": "GROUP_ENDED"}
    if _gp_of(g.get("id")):
        return {"ok": False, "error": "PLAN_EXISTS"}
    if not any(_norm_name(m.get("name")) == _norm_name(who) for m in _gi_active(g)):
        return {"ok": False, "error": "NOT_A_MEMBER"}
    return None


def gi_takeover(gid, who, idem=None):
    """GR.42b «Put me forward»: участник предлагает себя вместо молчащего организатора."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    now = time.time()
    with _STORE_LOCK:
        _gi_roles_due(now)
        g = _gi_find(gid)
        bad = _gi_role_guard(g, who)
        if bad:
            return bad
        if _norm_name(who) == _norm_name(g.get("owner")):
            return {"ok": False, "error": "ALREADY_ORGANISER"}
        t = g.get("takeover")
        if t and t.get("state") == "open":
            # GR.44a: одно предложение за раз — кто-то успел раньше.
            return _idem_put(idem, {"ok": False, "error": "OFFER_EXISTS", "by": t.get("by"),
                                    "group": _gi_public(g, who)})
        o = g.get("role_offer")
        if o and o.get("state") == "open":
            return _idem_put(idem, {"ok": False, "error": "ROLE_OFFER_OPEN", "group": _gi_public(g, who)})
        silent = _gi_silent_for(g, now)
        if silent < GI_SILENT_AFTER:
            return _idem_put(idem, {"ok": False, "error": "NOT_SILENT", "silent_h": int(silent // 3600)})
        g["takeover"] = {"id": "gt_%d_%s" % (int(now * 1000), secrets.token_hex(3)), "by": who, "at": now,
                         "closes": now + GI_TAKEOVER_WINDOW, "votes": {}, "state": "open",
                         "silent_since": now - silent, "owner": g.get("owner")}
        _gi_say(g, "%s offered to take over as organiser." % who, code="takeover_offered", who=who,
                owner=g.get("owner"))
        # Голосовать некому (в группе только кандидат и организатор) — решается сразу правилом «никто
        # не ответил»: роль не переходит. Отдельного кадра нет; строка в чате скажет, что вышло.
        _gi_roles_due(now)
        _save_store()
        return _idem_put(idem, {"ok": True, "group": _gi_public(g, who)})


def gi_takeover_vote(gid, who, yes, idem=None):
    """GR.43e: голос за кандидата. Решают ответившие; итог наступает, когда ответили все или вышло время."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    now = time.time()
    with _STORE_LOCK:
        _gi_roles_due(now)
        g = _gi_find(gid)
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        t = g.get("takeover")
        if not t or t.get("state") != "open":
            return _idem_put(idem, {"ok": False, "error": "NO_OPEN_VOTE", "group": _gi_public(g, who)})
        voter = next((v for v in _gi_takeover_voters(g, t) if _norm_name(v) == _norm_name(who)), None)
        if not voter:
            return {"ok": False, "error": "NOT_A_VOTER"}
        t.setdefault("votes", {})[voter] = bool(yes)
        _gi_roles_due(now)
        _save_store()
        return _idem_put(idem, {"ok": True, "group": _gi_public(g, who)})


def gi_takeover_withdraw(gid, who, idem=None):
    """GR.43a «Withdraw»: кандидат снимает предложение — голосование закрывается сразу."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    now = time.time()
    with _STORE_LOCK:
        g = _gi_find(gid)
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        t = g.get("takeover")
        if not t or t.get("state") != "open" or _norm_name(t.get("by")) != _norm_name(who):
            return _idem_put(idem, {"ok": False, "error": "NO_OPEN_OFFER"})
        t.update(state="withdrawn", resolved=now, why="withdrawn")
        _gi_say(g, "%s withdrew the offer to take over." % who, code="takeover_withdrawn", who=who)
        _save_store()
        return _idem_put(idem, {"ok": True, "group": _gi_public(g, who)})


def gi_takeover_back(gid, who, hand=False, idem=None):
    """GR.42a: организатор вернулся посреди голосования — оставить роль или отдать кандидату сразу."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    now = time.time()
    with _STORE_LOCK:
        g = _gi_find(gid)
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if _norm_name(who) != _norm_name(g.get("owner")):
            return {"ok": False, "error": "NOT_ORGANIZER"}
        t = g.get("takeover")
        if not t or t.get("state") != "open":
            return _idem_put(idem, {"ok": False, "error": "NO_OPEN_VOTE", "group": _gi_public(g, who)})
        _gi_touch_owner(g, who, now)
        if hand:
            t.update(state="handed", resolved=now, why="owner_handed")
            _gi_transfer(g, t.get("by"), now, "handed")
            _gi_say(g, "%s handed the organiser role to %s." % (who, t.get("by")), code="role_taken",
                    who=t.get("by"), former=who)
        else:
            t.update(state="stopped", resolved=now, why="owner_back")
            _gi_say(g, "%s is back and kept the role." % who, code="takeover_stopped", who=who,
                    candidate=t.get("by"))
        _save_store()
        return _idem_put(idem, {"ok": True, "group": _gi_public(g, who)})


def gi_role_offer(gid, who, to, idem=None):
    """GR.44b «Offer it to Jane»: организатор предлагает роль одному участнику. 24 часа на ответ."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    now = time.time()
    with _STORE_LOCK:
        _gi_roles_due(now)
        g = _gi_find(gid)
        bad = _gi_role_guard(g, who)
        if bad:
            return bad
        if _norm_name(who) != _norm_name(g.get("owner")):
            return {"ok": False, "error": "NOT_ORGANIZER"}
        if not any(_norm_name(m.get("name")) == _norm_name(to) for m in _gi_active(g)) \
                or _norm_name(to) == _norm_name(who):
            return {"ok": False, "error": "NOT_A_MEMBER"}
        if (g.get("takeover") or {}).get("state") == "open":
            return _idem_put(idem, {"ok": False, "error": "VOTE_IN_PROGRESS"})
        o = g.get("role_offer")
        if o and o.get("state") == "open":
            return _idem_put(idem, {"ok": False, "error": "OFFER_EXISTS", "group": _gi_public(g, who)})
        declined = list((o or {}).get("declined") or []) if o and o.get("state") in ("declined", "expired", "withdrawn") else []
        g["role_offer"] = {"to": to, "by": who, "at": now, "expires": now + GI_ROLE_OFFER_WINDOW,
                           "state": "open", "declined": declined}
        _gi_touch_owner(g, who, now)
        _gi_say(g, "%s offered %s the organiser role." % (who, to), code="role_offered", who=who, to=to)
        _save_store()
        return _idem_put(idem, {"ok": True, "group": _gi_public(g, who)})


def gi_role_respond(gid, who, accept, idem=None):
    """GR.44c «Take the role» / GR.44i «Keep it with Mateo»."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    now = time.time()
    with _STORE_LOCK:
        _gi_roles_due(now)
        g = _gi_find(gid)
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        o = g.get("role_offer")
        if not o or o.get("state") != "open" or _norm_name(o.get("to")) != _norm_name(who):
            return _idem_put(idem, {"ok": False, "error": "NO_OPEN_OFFER", "group": _gi_public(g, who)})
        if accept:
            if _gp_of(g.get("id")):
                return {"ok": False, "error": "PLAN_EXISTS"}
            o.update(state="accepted", closed=now)
            prev = g.get("owner")
            _gi_transfer(g, who, now, "offer")
            _gi_say(g, "%s is the organiser now." % who, code="role_taken", who=who, former=prev)
        else:
            o.update(state="declined", closed=now)
            o.setdefault("declined", []).append(who)
            _gi_say(g, "%s kept the organiser role with %s." % (who, o.get("by")), code="role_declined",
                    who=who, owner=o.get("by"))
        _save_store()
        return _idem_put(idem, {"ok": True, "group": _gi_public(g, who)})


def gi_role_withdraw(gid, who, idem=None):
    """GR.44d «Withdraw the offer»: организатор передумал — роль остаётся, предложение закрыто."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    now = time.time()
    with _STORE_LOCK:
        g = _gi_find(gid)
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        o = g.get("role_offer")
        if not o or o.get("state") != "open" or _norm_name(o.get("by")) != _norm_name(who):
            return _idem_put(idem, {"ok": False, "error": "NO_OPEN_OFFER"})
        o.update(state="withdrawn", closed=now)
        _gi_touch_owner(g, who, now)
        _save_store()
        return _idem_put(idem, {"ok": True, "group": _gi_public(g, who)})


def gi_approve(gid, frm, who, accept=True, idem=None):
    """Approve (or refuse) somebody who accepted after planning began.

    «Тот человек, которого мы пригласили ранее в intent, присоединяется на этапе плана — его нужно
    заапрувить.» The seat is claimed HERE, not when they tapped accept, so the same atomic capacity
    rule applies and an approval cannot overfill a room that filled while it was pending."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    now = time.time()
    with _STORE_LOCK:
        g = _gi_find(gid)
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if _norm_name(frm) != _norm_name(g.get("owner")):
            return {"ok": False, "error": "NOT_ORGANIZER"}
        inv = next((i for i in _ginvites()
                    if i.get("gid") == gid and _norm_name(i.get("to")) == _norm_name(who)
                    and i.get("state") == "awaiting_approval"), None)
        if not inv:
            return _idem_put(idem, {"ok": False, "error": "NOTHING_TO_APPROVE"})
        if not accept:
            inv["state"] = "declined_by_organizer"; inv["updated"] = now
            _save_store()
            return _idem_put(idem, {"ok": True, "approved": False, "who": who})
        if len(_gi_active(g)) >= int(g.get("max_total") or GI_MAX_TOTAL):
            inv["state"] = "group_full"; inv["updated"] = now
            _save_store()
            return _idem_put(idem, {"ok": False, "error": "GROUP_FULL"})
        inv["state"] = "accepted"; inv["updated"] = now
        g.setdefault("members", []).append({"name": inv.get("to"), "state": "joined", "joined": now})
        g["updated"] = now
        g["version"] = int(g.get("version") or 1) + 1
        _gi_say(g, "%s joined the group." % inv.get("to"), code="joined", who=inv.get("to"))
        # Состав вырос — пересчитать план. Без этого «позвать ещё людей» с кадра GR.40 выглядело
        # рабочим и не работало: человек приходил в группу, а план оставался на паузе навсегда.
        _gp_recount(gid, now)
        _save_store()
        return _idem_put(idem, {"ok": True, "approved": True, "who": inv.get("to"),
                                "group": _gi_public(g, frm)})


def gi_remove(gid, frm, who, reason="", idem=None):
    """The organiser removes a participant, WITH a reason.

    «Если мы удаляем человека из интента, у нас открывается окошко со сбором обратной связи. Почему
    мы этого человека удалили. Это поможет нам в будущем правильно принимать решения — если человек
    10 раз удалили из-за того, что он отправлял дикпики.» So the reason is not a courtesy field: it
    is the signal, and a removal without one is refused rather than recorded as an anonymous ejection.

    Only before a plan is approved. «После того, как у нас апрувнутый план приходит в действие, у нас
    блокируется кнопка удаления участников плана из общего чата.»"""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    reason = str(reason or "").strip()
    now = time.time()
    with _STORE_LOCK:
        g = _gi_find(gid)
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if _norm_name(frm) != _norm_name(g.get("owner")):
            return {"ok": False, "error": "NOT_ORGANIZER"}
        if _norm_name(who) == _norm_name(g.get("owner")):
            return {"ok": False, "error": "CANNOT_REMOVE_ORGANIZER"}
        if g.get("state") in ("planned", "locked", "done"):
            return _idem_put(idem, {"ok": False, "error": "PLAN_APPROVED",
                                    "note": "removal is blocked once a plan is in force"})
        if not reason:
            return {"ok": False, "error": "REASON_REQUIRED"}
        m = next((x for x in (g.get("members") or [])
                  if _norm_name(x.get("name")) == _norm_name(who)
                  and x.get("state") in ("joined", "active")), None)
        if not m:
            return _idem_put(idem, {"ok": False, "error": "NOT_A_MEMBER"})
        m["state"] = "removed"; m["left"] = now
        m["removed_by"] = g.get("owner"); m["reason"] = reason[:400]
        # The reason is kept as a record about the PERSON, not only inside this one group, because
        # that is the whole point of collecting it — a pattern is only visible across groups.
        SESSION.setdefault("_gremovals", []).append(
            {"gid": gid, "who": who, "by": g.get("owner"), "reason": reason[:400], "t": now})
        if len(_gi_active(g)) < int(g.get("min_total") or GI_MIN_TOTAL) and g.get("state") == "ready_to_plan":
            g["state"] = "chat_open"
        g["updated"] = now
        g["version"] = int(g.get("version") or 1) + 1
        # Neutral in the room: the group is told somebody left, never why or by whom.
        _gi_say(g, "%s is no longer in the group." % who, code="removed", who=who)
        # GR.52: а самому удалённому говорит Kleal — кто удалил и что причину не назовёт. Раньше
        # человек узнавал об этом только по исчезнувшей группе. Та же переписка с Kleal, что у
        # ответов модерации (admin_notify); `code` — чтобы приложение сказало это на своём языке.
        _messages().append({
            "id": _mid("a_"), "pair": _pair_key(SAFETY_SENDER, who),
            "from": SAFETY_SENDER, "to": who, "t": now, "u": now, "admin": True,
            "code": "group_removed", "by": g.get("owner"), "title": str(g.get("title") or "")[:200],
            "text": ("%s removed you from %s. I can’t share the reason. Your other intents aren’t "
                     "affected — I’m still looking for something close."
                     % (_display(g.get("owner"), str(g.get("owner") or "")), g.get("title") or "the group")),
            "ref": gid})
        _gp_recount(gid, now)
        _save_store()
        return _idem_put(idem, {"ok": True, "gid": gid, "group": _gi_public(g, frm)})


def _gp_blocks_convert(gid):
    """Мешает ли план перейти в один на один.

    Живая встреча мешает: переводить нечего, есть договорённость, и увести из неё вдвоём значит
    отменить её молча. А вот план НА ПАУЗЕ (below_quorum, GR.40) не мешает — он и стоит потому,
    что третьего нет. Ровно там кадр и предлагает три выхода: позвать ещё, перейти в один на один,
    отменить. Средний не работал: проверка стояла на «есть ли план вообще», а на паузе он есть.
    """
    p = _gp_of(gid)
    return bool(p) and p.get("state") not in ("below_quorum", "cancelled", "done")


def gi_convert_ask(gid, frm, idem=None):
    """GR.19 «Switch to one-on-one» — организатор просит второго перевести группу в один на один.

    Почему это ПРОСЬБА, а не действие: группа принадлежит обоим. Организатор, закрывающий её
    единолично, отнимает у второго то, на что тот согласился, — поэтому здесь только запрос, а
    решает GR.20 (`gi_convert_respond`).

    Условия ровно те, при которых предложение осмысленно: их двое (третий не пришёл или отказался),
    план ещё не назначен, группа жива. При назначенном плане переводить нечего — есть встреча.
    """
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    frm = str(frm or "").strip()
    now = time.time()
    with _STORE_LOCK:
        g = _gi_find(gid)
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if _norm_name(frm) != _norm_name(g.get("owner")):
            return _idem_put(idem, {"ok": False, "error": "NOT_ORGANIZER"})
        if g.get("state") not in GI_CONVERTIBLE_PHASES:
            return _idem_put(idem, {"ok": False, "error": "NOT_OPEN", "state": g.get("state")})
        act = _gi_active(g)
        if len(act) != 2:
            return _idem_put(idem, {"ok": False, "error": "NEED_TWO", "joined": len(act)})
        if _gp_blocks_convert(gid):
            return _idem_put(idem, {"ok": False, "error": "PLAN_EXISTS"})
        other = next((m.get("name") for m in act if _norm_name(m.get("name")) != _norm_name(frm)), None)
        if not other:
            return _idem_put(idem, {"ok": False, "error": "NEED_TWO"})
        g["pending_1to1"] = {"by": frm, "to": other, "at": now}
        g["version"] = int(g.get("version") or 1) + 1
        g["updated"] = now
        _gi_say(g, "%s asked to switch to one-on-one." % frm, code="convert_asked", who=frm)
        _save_store()
    return _idem_put(idem, {"ok": True, "asked": other, "group": _gi_public(g, frm)})


def gi_convert_respond(gid, who, agree, idem=None):
    """GR.20 — сторона, которую спросили, отвечает.

    Согласие закрывает группу и гасит её открытые приглашения: приглашённым уходит текст GR.23
    («…so the group invite is closed. Nothing you did») — это важно сказать вслух, иначе человек
    решит, что его отвергли лично.

    Отказ просто снимает просьбу: группа продолжает жить, и повторно спросить можно.
    """
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    who = str(who or "").strip()
    now = time.time()
    with _STORE_LOCK:
        g = _gi_find(gid)
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        req = g.get("pending_1to1") or {}
        if not req:
            return _idem_put(idem, {"ok": False, "error": "NOTHING_TO_ANSWER"})
        if _norm_name(req.get("to")) != _norm_name(who):
            return _idem_put(idem, {"ok": False, "error": "NOT_ASKED"})
        if not agree:
            g["pending_1to1"] = None
            g["version"] = int(g.get("version") or 1) + 1
            g["updated"] = now
            _gi_say(g, "%s wants to keep the group." % who, code="convert_declined", who=who)
            _save_store()
            return _idem_put(idem, {"ok": True, "agreed": False, "group": _gi_public(g, who)})

        g["pending_1to1"] = None
        g["state"] = "converted_1to1"
        g["version"] = int(g.get("version") or 1) + 1
        g["updated"] = now
        # План, стоявший на паузе, закрывается ВМЕСТЕ с группой. Оставить его — значит оставить
        # встречу, к которой больше некому прийти: группы уже нет, а план ссылается на неё и
        # продолжает висеть в списке живых. Молчаливый мусор, который потом никто не свяжет с
        # этим переходом.
        held = _gp_of(gid)
        if held and held.get("state") == "below_quorum":
            held["state"] = "cancelled"
            held["updated"] = now
            held["version"] = int(held.get("version") or 1) + 1
            held["cancelled_by"] = str(req.get("by") or "")
            held["cancel_reason"] = "converted_1to1"
        # Открытые приглашения гасятся ЗДЕСЬ, а не оставляются висеть: место, на которое звали,
        # больше не существует. Текст с борда GR.23 — про то, что человек ни при чём.
        title = str(g.get("title") or "the group")
        for inv in _gi_pending(gid):
            inv["state"] = "withdrawn"
            inv["updated"] = now
            inv["note_out"] = ("%s turned %s into a one-on-one, so the group invite is closed. "
                               "Nothing you did." % (req.get("by"), title))
        # А ВОТ И САМ ОДИН-НА-ОДИН. Без этой записи «перешли в один на один» было ярлыком без
        # вещи: состояние группы менялось, строка в чат уходила, а никакого один-на-один не
        # возникало. Двое оставались в комнате мёртвой группы и не могли ни написать друг другу
        # (переписка 1:1 требует принятого приглашения — _mp_matched), ни назначить встречу.
        # Отказа при этом не было: экран просто оставался прежним.
        #
        # Согласие уже дано — обоими, вслух, прямо здесь: один спросил, второй ответил «да».
        # Поэтому заявка создаётся СРАЗУ принятой, а не «отправленной»: спрашивать второй раз то,
        # на что человек только что согласился, значит не понимать собственный вопрос.
        by, to_ = str(req.get("by") or ""), str(req.get("to") or "")
        if by and to_ and not _mp_matched(by, to_):
            rs = _requests()
            rid = "rq_%d_%s" % (int(now * 1000),
                                hashlib.sha1((by + to_ + "cv").encode("utf-8")).hexdigest()[:6])
            rs.append({"id": rid, "from": by, "to": to_,
                       "intent": {"topics": list(g.get("topics") or []),
                                  "title": str(g.get("title") or "")[:200]},
                       "iid": str(g.get("gid") or "")[:64],
                       "note": "", "status": "accepted", "created": now, "updated": now,
                       "version": 1, "expires_at": now,
                       # След происхождения: эта пара пришла НЕ из поиска, а из распавшейся группы.
                       # Без него потом не отличить её от обычного знакомства.
                       "source": "group_convert",
                       "config_version": (_CORE_CFG or {}).get("config_version")})
            # Разговор не начинается с пустого экрана: люди уже общались, и первое, что они
            # увидят в переписке, — почему она вдруг стала личной.
            _sys_msg(by, to_, "converted_from_group")
        _gi_say(g, "The group is now a one-on-one.", code="converted")
        _save_store()
    return _idem_put(idem, {"ok": True, "agreed": True, "with": str(req.get("by") or ""),
                            "group": _gi_public(g, who)})


def gi_leave(gid, who, idem=None):
    """Voluntary exit — the only way out that is not a safety action (§16). The record keeps the
    person with state LEFT so the count can be explained; the roster no longer contains them."""
    who = str(who or "").strip()
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    now = time.time()
    with _STORE_LOCK:
        g = _gi_find(gid)
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        m = next((x for x in (g.get("members") or [])
                  if _norm_name(x.get("name")) == _norm_name(who) and x.get("state") in ("joined", "active")), None)
        if not m:
            return _idem_put(idem, {"ok": False, "error": "NOT_A_MEMBER", "gid": gid})
        m["state"] = "left"; m["left"] = now
        rest = _gi_active(g)
        # The organiser may leave — but the group must not be left with nobody who can invite, plan
        # or close it. Every organiser-only action checks one name, so an orphaned group is simply
        # frozen: three people in a room where no button works. Hand it to whoever has been there
        # longest instead; forbidding the exit would trap the organiser in a group they want out of,
        # and closing the group would destroy a plan the others may already have confirmed.
        if _norm_name(who) == _norm_name(g.get("owner")) and rest:
            heir = sorted(rest, key=lambda x: x.get("joined") or 0)[0]
            g["owner"] = heir.get("name")
            _gi_say(g, "%s left. %s is now the organiser." % (who, heir.get("name")), code="left_heir", who=who, heir=heir.get("name"))
        else:
            _gi_say(g, "%s left the group." % who, code="left", who=who)
        n = len(rest)
        if n < int(g.get("min_total") or GI_MIN_TOTAL) and g.get("state") in ("ready_to_plan", "planning"):
            g["state"] = "below_quorum"
        g["updated"] = now
        g["version"] = int(g.get("version") or 1) + 1
        _gp_recount(gid, now)
        _save_store()
        return _idem_put(idem, {"ok": True, "gid": gid, "group": _gi_public(g, who)})


def gmsg_react(gid, who, mid, emoji):
    """Реакция в комнате. Право — членство: кто в группе, тот и реагирует."""
    emoji = str(emoji or "")
    if emoji not in REACTIONS:
        return {"ok": False, "error": "UNKNOWN_REACTION"}
    with _STORE_LOCK:
        g = _gi_find(gid)
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if g.get("state") == "closed_by_owner":
            return {"ok": False, "error": "CLOSED"}    # S10: закрытая комната — только для чтения
        if not any(_norm_name(m.get("name")) == _norm_name(who) for m in _gi_active(g)):
            return {"ok": False, "error": "NOT_A_MEMBER"}
        m = next((x for x in _gmsgs() if x.get("id") == str(mid) and x.get("gid") == gid), None)
        if not m:
            return {"ok": False, "error": "NO_SUCH_MESSAGE"}
        _react(m, who, emoji)
        _save_store()
    return {"ok": True, "id": m["id"], "r": m.get("r") or {}}


def gmsg_delete(gid, who, mid):
    with _STORE_LOCK:
        g = _gi_find(gid)
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if g.get("state") == "closed_by_owner":
            return {"ok": False, "error": "CLOSED"}    # S10: закрытая комната — только для чтения
        m = next((x for x in _gmsgs() if x.get("id") == str(mid) and x.get("gid") == gid), None)
        if not m:
            return {"ok": False, "error": "NO_SUCH_MESSAGE"}
        if _norm_name(m.get("frm")) != _norm_name(who):
            return {"ok": False, "error": "NOT_YOURS"}
        if m.get("kind") == "system":
            return {"ok": False, "error": "NOT_A_MESSAGE"}
        m["text"] = ""
        m["deleted"] = True
        m.pop("voice", None)
        m.pop("r", None)
        _touch(m)
        _save_store()
    return {"ok": True, "id": m["id"]}


def gi_thread(gid, who, since=0.0):
    """The shared chat. Membership IS the ACL: a person who is not in the room does not get the
    history, and there is no other thread to be in."""
    g = _gi_find(gid)
    if not g:
        return {"ok": False, "error": "NO_SUCH_GROUP"}
    if not any(_norm_name(m.get("name")) == _norm_name(who) for m in _gi_active(g)):
        # S11: ушедший по жалобе сохраняет историю только для чтения — замороженную на выходе.
        gone = next((m for m in g.get("members") or []
                     if _norm_name(m.get("name")) == _norm_name(who) and m.get("safety_exit")), None)
        if not gone:
            return {"ok": False, "error": "NOT_A_MEMBER"}
        upto = float(gone.get("left") or 0)
        msgs = [m for m in _gmsgs() if m.get("gid") == gid and (m.get("t") or 0) < upto]
        msgs.sort(key=lambda m: m.get("t") or 0)
        return {"ok": True, "group": _gi_public(g, who), "messages": msgs[-200:]}
    try:
        since = float(since or 0)
    except (TypeError, ValueError):
        since = 0.0
    msgs = [m for m in _gmsgs() if m.get("gid") == gid and _touched(m) > since]
    msgs.sort(key=lambda m: m.get("t") or 0)
    return {"ok": True, "group": _gi_public(g, who), "messages": msgs[-200:]}


def gi_post(gid, who, text, idem=None, voice=None, client_id=None, reply_to=None, video=None):
    who, text = str(who or "").strip(), str(text or "").strip()
    voice, voice_error = _voice_message(voice)
    if voice_error:
        return {"ok": False, "error": voice_error}
    video, video_error = _video_message(video)
    if video_error:
        return {"ok": False, "error": video_error}
    if voice:
        text = voice["transcript"]
    if video and not text:
        text = "[video]"
    if not text:
        return {"ok": False, "error": "empty message"}
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    with _STORE_LOCK:
        g = _gi_find(gid)
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if g.get("state") == "closed_by_owner":
            return {"ok": False, "error": "CLOSED"}    # S10: закрытая комната — только для чтения
        if not any(_norm_name(m.get("name")) == _norm_name(who) for m in _gi_active(g)):
            return {"ok": False, "error": "NOT_A_MEMBER"}
        if g.get("state") in ("cancelled", "expired"):
            return {"ok": False, "error": "CLOSED"}
        now = time.time()
        msg = {"id": _mid("gm_"), "gid": gid, "frm": who,
               "text": text[:2000], "t": now, "u": now, "kind": "msg"}
        if client_id:
            msg["cid"] = str(client_id)[:64]
        if reply_to:
            # Цитируемое — из ЭТОЙ комнаты: иначе ответом можно вытащить строку из чужой.
            src = next((x for x in _gmsgs()
                        if x.get("id") == str(reply_to) and x.get("gid") == gid), None)
            if not src:
                return {"ok": False, "error": "NO_SUCH_MESSAGE"}
            msg["rt"] = _quote_of(src)
        if voice:
            msg.update({"kind": "voice", "voice": voice})
        if video:
            msg.update({"kind": "video", "video": video})
        _gmsgs().append(msg)
        g["updated"] = now
        _save_store()
        return _idem_put(idem, {"ok": True, "message": msg})


def _blew_up(where, e):
    """Записать в лог ТРАССИРОВКУ упавшего запроса, а не только текст исключения.

    Поиск людей падал с «'list' object has no attribute 'get'» и отдавал клиенту пустую выдачу.
    Экран показывал «никого не нашлось» — то есть обычный, ожидаемый исход, — а в логе не было
    ни строки: обработчик клал str(e) в ответ и на этом успокаивался. Найти такое можно только
    случайно, и именно так его и нашли, через несколько дней.

    Строка исключения без трассировки бесполезна вдвойне: она называет ТИП ошибки, но не место,
    а «где-то список вместо словаря» в файле на шесть тысяч строк — это не подсказка."""
    sys.stderr.write("[matching] %s FAILED: %s\n%s\n" % (where, e, traceback.format_exc()))
    sys.stderr.flush()


def _iso(ts):
    """unix-секунды → ISO-8601 в UTC. Клиенту время приглашения нужно строкой, а не числом:
    число он всё равно форматирует сам, и два разных формата разъезжаются первыми."""
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(ts)))
    except (TypeError, ValueError):
        return ""


def _person_card(name):
    """Имя → как этого человека рисуют в чужом списке: фото и возраст, и ничего сверх того.

    Отдельно от `_photo_by_name`, потому что приглашение подписывается «Марк, 31»: без возраста
    строка обрывается на имени, а лезть за ним в общий профиль ради одной цифры — лишний повод
    вынести наружу то, чего в приглашении быть не должно."""
    u = _person(name)                        # `name` — id человека (docs/IDENTITY.md)
    if u is not None:
        if True:
            age = u.get("age")
            try:
                age = int(age) if age is not None else None
            except (TypeError, ValueError):
                age = None
            return {"name": str(u.get("name") or _display(name)), "id": str(u.get("id") or ""),
                    "age": age, "photo": u.get("photo") or "", "tz": str(u.get("tz") or "")}
    return {"name": _display(name, str(name or "")), "id": _canon_pid(name), "age": None, "photo": ""}


HOME_NOT_PICKED_KEEP = 24 * 3600        # исход «не в этот раз» стоит на главной сутки, потом — история


def home_invites(who, with_answered=False):
    """Единая лента входящих приглашений для главной — 1:1 и групповые в ОДНОМ списке.

    Почему отдельная ручка, а не два запроса и склейка на клиенте: на борде (GR.01, «Invite Stack»)
    это одна стопка, и порядок в ней общий. Считать «что новее» на клиенте значило бы держать это
    правило там же, где вид, и повторять его в каждом месте, где стопка понадобится снова.

    В ленту попадает ТОЛЬКО то, на что человек ещё может ответить: `pending` у заявок 1:1 и
    `sent`/`viewed` у групповых. Отклонённое и просроченное — история; экрану, который спрашивает
    «идёшь?», ей отвечать нечем, а показанная там она читается как новое приглашение.

    Форма строки списана с клиента (`homeInvites` в kleal-app/src/home.ts), а не придумана:
    он отбрасывает всё, у чего нет `id` и знакомого `type`, так что расхождение здесь означает
    не ошибку на экране, а пустую ленту без единого слова о причине.

    ВЫБОР ИЗ ОТВЕТИВШИХ (11.10.2026). С `with_answered` (запрос `?pick=1`, новый клиент) в ленту
    идут ещё заявки 1:1, где человек сказал «да» и ждёт выбора (`status: answered` — вернуться к
    «You said yes / Take back my yes», C1a), и свежий исход «не в этот раз» (`not_picked`, сутки).
    Только по признаку: клиент без него рисует любую строку как новое приглашение — ровно то, от
    чего предостерегает абзац выше. У каждой строки теперь есть `status`."""
    _expire_due()
    _gi_expire()
    me = _norm_name(who)
    if not me:
        return {"ok": True, "invites": []}
    rows = []
    now = time.time()

    for r in _requests():
        if _norm_name(r.get("to")) != me:
            continue
        st = r.get("status")
        if st != "pending":
            if not with_answered:
                continue
            if st == "not_picked":
                if now - float(r.get("updated") or 0) > HOME_NOT_PICKED_KEEP:
                    continue
            elif st != "answered":
                continue
        it = r.get("intent") if isinstance(r.get("intent"), dict) else {}
        rows.append({
            "id": r.get("id"), "type": "one_to_one", "status": st,
            # Срок ответа («Reply by») у pending; срок выбора организатором у answered.
            "expires_at": r.get("expires_at"), "answered_at": r.get("answered_at"),
            "pick_by": r.get("pick_by") if st == "answered" else None,
            "closed_at": r.get("updated") if st == "not_picked" else None,
            "reason": (r.get("trace") or {}).get("reason") if st == "not_picked" else "",
            "created_at": _iso(r.get("created") or r.get("updated")),
            "_t": float(r.get("created") or r.get("updated") or 0),
            "from": _person_card(r.get("from")),
            "note": str(r.get("note") or "")[:400],
            "intent": {
                "id": str(it.get("id") or ""),
                "title": str(it.get("title") or ""),
                "when": str(it.get("time") or it.get("when") or ""),
                "mode": str(it.get("mode") or ""),
                # Точный адрес наружу не идёт — тот же запрет, что в `inbox` (OF.09): в списке
                # приглашений человек видит район, а куда именно идти — уже после согласия.
                "area": str(it.get("area") or it.get("district") or it.get("place") or ""),
            },
        })

    for i in _ginvites():
        if _norm_name(i.get("to")) != me or i.get("state") not in ("sent", "viewed"):
            continue
        g = _gi_find(i.get("gid"))
        if not g:
            continue
        pub = _gi_public(g, who)
        rows.append({
            "id": i.get("id"), "type": "group",
            "created_at": _iso(i.get("created")),
            "_t": float(i.get("created") or 0),
            "from": _person_card(i.get("frm")),
            "note": str(i.get("note") or "")[:400],
            "intent": {
                "id": str(g.get("id") or ""),
                "title": str(g.get("title") or ""),
                "when": str(g.get("when") or ""),
                "mode": str(g.get("mode") or "offline"),
                "area": str(g.get("area") or ""),
            },
            "group": {
                "gid": g.get("id"),
                "cover": "",
                # Кто уже внутри — ровно то, что GR.16 обещает приглашённому. Приглашённых
                # (кого ещё позвали) здесь нет и быть не должно: это видит только организатор.
                "participants": [{"name": m.get("name"), "photo": m.get("photo") or ""}
                                 for m in (pub.get("members") or [])],
                "participant_count": pub.get("joined_count"),
                "max_size": pub.get("max_total"),
            },
        })

    rows.sort(key=lambda r: -r["_t"])
    for r in rows:
        r.pop("_t", None)
    return {"ok": True, "invites": rows[:50]}


def gi_for(who):
    """Every group intent this person is in or has been invited to — the Intents tab reads this."""
    _gi_expire()
    me = _norm_name(who)
    mine, invited = [], []
    for g in _gintents():
        if any(_norm_name(m.get("name")) == me for m in _gi_active(g)):
            mine.append(_gi_public(g, who))
    for i in _ginvites():
        if _norm_name(i.get("to")) == me and i.get("state") in ("sent", "viewed"):
            g = _gi_find(i.get("gid"))
            if g:
                invited.append({"invite": {"id": i.get("id"), "from": i.get("frm"),
                                           "note": i.get("note"), "state": i.get("state"),
                                           "expires_at": i.get("expires_at")},
                                "group": _gi_public(g, who)})
    mine.sort(key=lambda x: -(x.get("joined_count") or 0))
    return {"ok": True, "groups": mine, "invites": invited}


# Почему приглашение закрылось — экран GR.56a называет причину: «turned into a one-on-one»,
# «filled up before you answered», «closed it before a plan was set». Отказ и принятие сюда не
# входят: их человек сделал сам и видит итог сразу.
_GI_INVITE_CLOSED = {"group_full": "full", "withdrawn": "withdrawn", "group_closed": "closed",
                     "expired": "expired", "policy_revoked": "withdrawn"}


def gi_invite_detail(inv_id, who):
    """Return one group invitation only to its recipient — live, or closed with the reason (GR.56a)."""
    _gi_expire()
    me = _norm_name(who)
    inv = next((i for i in _ginvites()
                if i.get("id") == inv_id and _norm_name(i.get("to")) == me
                and (i.get("state") in ("sent", "viewed") or i.get("state") in _GI_INVITE_CLOSED)), None)
    if not inv:
        return {"ok": False, "error": "NO_SUCH_INVITE"}
    g = _gi_find(inv.get("gid"))
    if not g:
        return {"ok": False, "error": "NO_SUCH_GROUP"}
    closed = _GI_INVITE_CLOSED.get(inv.get("state"))
    if closed == "withdrawn" and g.get("state") == "converted_1to1":
        closed = "converted"
    return {
        "ok": True,
        "invite": {
            "id": inv.get("id"), "gid": inv.get("gid"), "from": inv.get("frm"),
            "note": inv.get("note"), "state": inv.get("state"),
            "expires_at": inv.get("expires_at"),
            **({"closed": closed} if closed else {}),
            # Кто позвал — лицо и возраст для строки «Mateo, 34 · Invited you» (GR.56/56a). Состав
            # закрытой группы постороннему не отдаётся, а пригласивший ему и так известен.
            "from_photo": _photo_of(inv.get("frm")),
            "from_age": (_person(inv.get("frm")) or {}).get("age"),
        },
        "group": _gi_public(g, who),
    }


# -*- coding: utf-8 -*-
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# GROUP PLANS — confirmation, counter-proposals, votes, the two-hour lock, feedback
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Per the daily. The shape of the thing:
#
#   3+ in the chat -> organiser presses «Создать план» -> a draft of time and place goes to everyone
#   -> each person confirms, or makes a COUNTER-PROPOSAL, which puts it back to the room and restarts
#   approval from scratch -> once three have confirmed the CURRENT version, the plan exists.
#
# Three is the whole rule, not a fallback: «в тот момент, когда все участники встречи, а минимум
# трое, договорились... у нас создаётся план». Waiting for silent members would let one person who
# stopped reading hold four others hostage.
#
# After the plan exists nobody can be removed, and changing or cancelling it is not the organiser's
# call any more — it goes to a VOTE, decided by a majority OF THOSE WHO VOTED. A tie fails: a plan
# people already agreed to does not fall apart because the room split evenly.
#
# Two hours before it starts everything freezes. «Убираются все кнопки, и этот план считается, что
# он точно состоялся» — no edits, no cancels, no new people.
GP_LOCK_BEFORE = 2 * 3600      # the freeze window, in seconds before the meeting starts
# Три — это ПОЛ, а не достаточность. План утверждается, когда подтвердили ВСЕ (борд GR.26
# «Waiting for everyone»); эта константа осталась нижней границей СОСТАВА: план, в котором меньше
# трёх человек, группой быть перестал (§1) — это проверяет `_gp_recount`.
GP_MIN_CONFIRMS = GI_MIN_TOTAL
# А вот сколько нужно СОГЛАСИЙ, чтобы организатор мог закрепить план (GR.30) — другое число, и
# путать их дорого. Борд показывает кадр закрепления при двух согласных из трёх: «Two confirmed,
# one didn’t… You can fix Thursday 20:30 as the plan». Требование трёх согласий делало бы кнопку
# недостижимой в группе ровно из трёх человек — то есть в самой частой, — и молчащий получал бы
# право вечного вето, ради устранения которого раунды и придумывались.
#
# Почему не единица: закрепление с одним согласием — это указ организатора, а не план группы. Два
# означает «решаю не я один», и §1 при этом не нарушается: не подтвердившего НИКТО не выбрасывает,
# он остаётся в составе и решает сам (GR.31), так что людей в плане по-прежнему трое.
GP_FIX_MIN_CONFIRMS = 2
# Сколько встречных предложений допускается, считая исходное. Борд: «Round 1 of 3» → «Round 2 of
# 3» → «Last round · after this the organiser fixes the plan». Дальше — gp_fix.
GP_MAX_ROUNDS = 3
# Голосование живёт шесть часов. Борд GR.35: «Everyone gets 6 hours to answer». Окно нужно именно
# потому, что голосование СОВЕЩАТЕЛЬНОЕ: без срока молчащий держал бы его вечно, а организатору
# нечего было бы решать. Истёк срок — считаем по тем, кто ответил.
GP_VOTE_WINDOW = 6 * 3600
# GRO.47-50. The call is considered over an hour after its start. Everybody gets three days to
# answer; after two days the agent leaves one reminder in the group chat, then closes the prompt.
GP_FEEDBACK_DELAY = 3600
GP_FEEDBACK_REMINDER = 2 * 24 * 3600
GP_FEEDBACK_WINDOW = 3 * 24 * 3600


def _gplans():
    return SESSION.setdefault("_gplans", [])


def _gvotes():
    return SESSION.setdefault("_gvotes", [])


def _gp_find(pid):
    for p in _gplans():
        if p.get("id") == pid:
            return p
    return None


def _gp_of(gid):
    """The plan currently in force for a group intent, if any. One at a time, by construction."""
    for p in _gplans():
        if p.get("gid") == gid and p.get("state") in ("proposed", "confirmed", "locked", "below_quorum"):
            return p
    return None


def _gp_confirms(p):
    """Who has confirmed THIS version AND is still in the group.

    Both halves matter. The version half: a counter-proposal bumps it precisely so older
    confirmations stop counting — people agreed to a different evening. The membership half: a
    confirmation is not a signature that outlives leaving. Without it a plan kept listing someone
    who had walked out, stayed at three when it was really two, and never noticed it had fallen
    below quorum."""
    v = int(p.get("version") or 1)
    said_yes = [n for n, r in (p.get("responses") or {}).items()
                if r.get("state") == "confirmed" and int(r.get("version") or 0) == v]
    g = _gi_find(p.get("gid"))
    if not g:
        return said_yes
    live = {_norm_name(m.get("name")) for m in _gi_active(g)}
    return [n for n in said_yes if _norm_name(n) in live]


def _gp_round(p):
    """Каким по счёту раундом согласования идёт план. Отдельно от версии — см. `_gp_public`.
    Планы, заведённые до появления поля, читаются по версии: у них другого числа и не было."""
    return int(p.get("round") or p.get("version") or 1)


def _gp_recount(gid, now=None):
    """Re-derive a plan's standing after the roster changed. Called from every exit path, because
    losing a confirmed participant is exactly when a plan stops being a group plan."""
    now = now or time.time()
    p = _gp_of(gid)
    if not p or p.get("state") not in ("proposed", "confirmed", "below_quorum"):
        return
    g = _gi_find(gid)
    roster = len(_gi_active(g)) if g else 0

    # ПАУЗА СНИМАЕТСЯ. Раньше below_quorum было состоянием без выхода: сюда попадали и здесь
    # оставались навсегда — ни одна ветка кода его не снимала, и позвать людей заново было
    # бессмысленно. Меряем СОСТАВОМ, а не подтверждениями: только что принятый участник ничего
    # подтвердить ещё не успел. Возвращаемся в «предложено», а не в «согласовано»: состав другой,
    # и согласие каждого надо получить заново.
    if p.get("state") == "below_quorum":
        if roster >= GP_MIN_CONFIRMS:
            p["state"] = "proposed"
            p["updated"] = now
            p.pop("hold", None)          # пауза кончилась: третий пришёл (GR.40f)
            if g:
                g["state"] = "planning"
                _gi_say(g, "Three again — the plan is back on. Everyone confirms once more.", code="quorum_back")
        return

    # Пока идёт «принять или выйти» (GR.33), считать по подтверждениям нельзя: их по построению
    # одно — организатора. Меряем составом, который и есть встреча: «the group carries on either
    # way». Иначе первый же вышедший обрушивал план в below_quorum со строкой «Only 1 confirmed
    # remain» — при пятерых, которые никуда не делись.
    n = len(_gi_active(g)) if (g and p.get("update")) else len(_gp_confirms(p))
    # Согласование тоже роняется — по составу. Пока проверялось только «согласовано», выход
    # участника посреди раундов не ронял ничего: экран «вас осталось двое» не наступал, а двое
    # продолжали согласовывать групповой план, которого уже не могло быть.
    below = (p.get("state") == "confirmed" and n < GP_MIN_CONFIRMS) or \
            (p.get("state") == "proposed" and roster < GP_MIN_CONFIRMS)
    if below:
        p["state"] = "below_quorum"
        p["updated"] = now
        p["hold"] = {"since": now}       # отсюда считаются 12 часов паузы (GR.40)
        if g:
            g["state"] = "below_quorum"
            # Борд GR.40: план НА ПАУЗЕ, а не отменён, и решение за организатором. Прежняя строка
            # («This is no longer a group plan») закрывала вопрос, который борд как раз открывает.
            _gi_say(g, "A group plan needs three. Nothing happens until you choose.", code="below_quorum")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# ПАУЗА «ВАС ДВОЕ» — борд «GR · Offline — new layout», кадры GR.40–GR.40f (29.09.2026)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# План встал на паузу (below_quorum): группе нужно трое. Раньше пауза не кончалась никогда — план
# висел до и после встречи. По борду:
#   — 12 часов паузы («On hold 2 of 3 · Ends in 11h 40m»): организатор зовёт третьего, переводит
#     в один на один или отменяет; пришёл третий — пауза снята (_gp_recount).
#   — 12 часов прошли без решения — Kleal спрашивает ОБОИХ («Twelve hours passed»): Switch to
#     one-on-one / Let the plan go. Ответ — до двух часов до встречи («Reply by 18:30»).
#     Оба за один на один — группа переходит в него (gi_convert_respond); кто-то отпустил план
#     или срок вышел — план отменён, группа остаётся и снова ищет людей (GR.40b / GR.40e).
GP_HOLD_WINDOW = 12 * 3600
GP_HOLD_CHOICES = ("one_on_one", "let_go")


def _gp_hold_deadline(p, since):
    """До когда можно ответить: за два часа до встречи; без времени встречи — ещё 12 часов."""
    sa = float(p.get("starts_at") or 0)
    return sa - GP_LOCK_BEFORE if sa else since + 2 * GP_HOLD_WINDOW


def _gp_hold_close(p, g, now, why, who=""):
    """Отменить план с паузы: группа остаётся, место снова ищется (борд: «Your intent goes back
    to searching»)."""
    h = p.setdefault("hold", {"since": now})
    h.update(closed=now, why=why)
    p["state"] = "cancelled"
    p["updated"] = now
    p["version"] = int(p.get("version") or 1) + 1
    p["cancel_reason"] = "hold_" + why
    if g:
        g["state"] = "chat_open"
        g["updated"] = now
        g["version"] = int(g.get("version") or 1) + 1
        if why == "let_go":
            _gi_say(g, "%s let the plan go. The group is still here." % who, code="hold_let_go", who=who)
        else:
            _gi_say(g, "The plan is cancelled — nobody agreed to a one-on-one. The group is still here.",
                    code="hold_expired")


def _gp_hold_due(now=None):
    """Провести то, что наступает само: конец 12 часов паузы (вопрос обоим) и конец срока ответа
    (отмена). Зовётся на каждом чтении (_gp_sweep)."""
    now = now or time.time()
    changed = False
    for p in _gplans():
        if p.get("state") != "below_quorum":
            continue
        g = _gi_find(p.get("gid"))
        h = p.get("hold")
        if not h:
            # План встал на паузу до того, как пауза стала считаться: часы идут с этой минуты.
            # Встреча, время которой уже прошло, — не наша забота: не трогаем.
            sa = float(p.get("starts_at") or 0)
            if sa and sa <= now:
                continue
            p["hold"] = h = {"since": now}
            changed = True
        since = float(h.get("since") or now)
        deadline = _gp_hold_deadline(p, since)
        if not h.get("ask_at") and now >= min(since + GP_HOLD_WINDOW, deadline):
            h["ask_at"] = now
            h["until"] = deadline
            h.setdefault("answers", {})
            changed = True
            if now < deadline and g:
                _gi_say(g, "Twelve hours passed. Switch to one-on-one if you both agree, or let the plan go.",
                        code="hold_ask")
        if h.get("ask_at") and now >= float(h.get("until") or 0):
            _gp_hold_close(p, g, now, "expired")
            changed = True
    return changed


def _gp_hold_closed_recent(gid, now=None):
    """Последний план группы, закрытый с паузы за сутки, — для кадра «The plan is cancelled»."""
    now = now or time.time()
    best = None
    for p in _gplans():
        h = p.get("hold") or {}
        if p.get("gid") == gid and p.get("state") == "cancelled" and h.get("closed") \
                and now - float(h["closed"]) < 24 * 3600:
            if not best or float(h["closed"]) > float(best["hold"]["closed"]):
                best = p
    return best


def _gp_hold_public(p, me, act):
    h = p.get("hold")
    if not h:
        return None
    since = float(h.get("since") or 0)
    answers = h.get("answers") or {}
    mine = next((v for k, v in answers.items() if _norm_name(k) == _norm_name(me)), None)
    return {"since": since,
            "ends_at": min(since + GP_HOLD_WINDOW, _gp_hold_deadline(p, since)),
            "ask": bool(h.get("ask_at")), "ask_at": h.get("ask_at"), "until": h.get("until"),
            "answered": len([n for n in act if any(_norm_name(k) == _norm_name(n) for k in answers)]),
            "of": len(act), "my_answer": mine,
            # Кто ответил и кто за один на один — списками людей: ключи словаря ответов на боевом —
            # id строк, и в подписи их переводит только _humanize, который ходит по спискам.
            "answered_by": [k for k in answers],
            "one_on_one_by": [k for k, v in answers.items() if v == "one_on_one"],
            "let_go_by": [k for k, v in answers.items() if v == "let_go"],
            "closed": h.get("closed"), "why": h.get("why")}


def gp_hold_answer(pid, who, choice, idem=None):
    """GR.40a / GR.40d: ответ на «Twelve hours passed» — one_on_one или let_go."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    who = str(who or "").strip()
    choice = str(choice or "").strip()
    if choice not in GP_HOLD_CHOICES:
        return {"ok": False, "error": "INVALID_CHOICE"}
    now = time.time()
    convert_to = ""
    with _STORE_LOCK:
        _gp_hold_due(now)
        p = _gp_find(pid)
        if not p:
            return {"ok": False, "error": "NO_SUCH_PLAN"}
        g = _gi_find(p.get("gid"))
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        act = [m.get("name") for m in _gi_active(g)]
        if not any(_norm_name(n) == _norm_name(who) for n in act):
            return _idem_put(idem, {"ok": False, "error": "NOT_A_MEMBER"})
        h = p.get("hold") or {}
        if p.get("state") != "below_quorum" or not h.get("ask_at"):
            return _idem_put(idem, {"ok": False, "error": "NOT_ASKING", "plan": _gp_public(p, who)})
        h.setdefault("answers", {})[who] = choice
        p["updated"] = now
        p["version"] = int(p.get("version") or 1) + 1
        if choice == "let_go":
            # Один на один нужен обоим — отпустил один, ждать второго незачем.
            _gp_hold_close(p, g, now, "let_go", who)
        else:
            both = len(act) == 2 and all(
                any(_norm_name(k) == _norm_name(n) and v == "one_on_one" for k, v in h["answers"].items())
                for n in act)
            if both:
                owner = g.get("owner")
                other = next((n for n in act if _norm_name(n) != _norm_name(owner)), "")
                if other:
                    g["pending_1to1"] = {"by": owner, "to": other, "at": now}
                    convert_to = other
            else:
                _gi_say(g, "%s wants to switch to one-on-one." % who, code="hold_one_on_one", who=who)
        _save_store()
    if convert_to:
        # Оба сказали «да» — тот же переход, что GR.19 → GR.19b: план с паузы закрывается вместе
        # с группой, заявка один на один создаётся сразу принятой.
        gi_convert_respond(p.get("gid"), convert_to, True)
    with _STORE_LOCK:
        return _idem_put(idem, {"ok": True, "plan": _gp_public(_gp_find(pid), who)})


def _gp_lock_due(now=None):
    """Freeze anything inside the two-hour window, and close whatever was still being voted on —
    an open vote at that point can no longer change a meeting people are already travelling to."""
    now = now or time.time()
    changed = False
    for p in _gplans():
        if p.get("state") in ("confirmed", "proposed") and p.get("starts_at"):
            if now >= float(p["starts_at"]) - GP_LOCK_BEFORE:
                p["state"] = "locked"
                p["updated"] = now
                g = _gi_find(p.get("gid"))
                if g and not p.get("feedback_members"):
                    p["feedback_members"] = [m.get("name") for m in _gi_active(g) if m.get("name")]
                changed = True
                for v in _gvotes():
                    if v.get("plan_id") == p.get("id") and v.get("state") == "open":
                        # Голосование о встрече, до которой меньше двух часов, решать уже нечего:
                        # закрываем и сразу помечаем решённым, иначе организатору навсегда
                        # останется висеть кнопка «It’s your call» по плану, который не меняется.
                        v["state"] = "closed"
                        v["closed"] = now
                        v["decided"] = "kept"
                        v["why"] = "locked"
                if g:
                    g["state"] = "locked"
                    _gi_say(g, "The plan is locked — it starts in less than two hours.", code="plan_locked")
    return changed


def _gp_feedback_members(p):
    """People entitled to the private post-call question.

    The roster is frozen when the plan locks so a later leave cannot erase somebody's answer or
    change a 2-of-3 outcome into 2-of-2. Older plans get the same snapshot lazily.
    """
    saved = [str(n).strip() for n in (p.get("feedback_members") or []) if str(n).strip()]
    if saved:
        return saved
    g = _gi_find(p.get("gid"))
    active = [m.get("name") for m in _gi_active(g) if m.get("name")] if g else []
    return active or _gp_confirms(p)


def _gp_feedback_times(p):
    try:
        starts = float(p.get("starts_at") or 0)
    except (TypeError, ValueError):
        starts = 0
    return {
        "due": starts + GP_FEEDBACK_DELAY if starts else 0,
        "reminder": starts + GP_FEEDBACK_REMINDER if starts else 0,
        "expires": starts + GP_FEEDBACK_WINDOW if starts else 0,
    }


def _gp_feedback_record(p, who):
    me = _norm_name(who)
    for name, value in (p.get("feedback") or {}).items():
        if _norm_name(name) == me:
            return value
    return None


def _gp_feedback_outcome(p):
    members = _gp_feedback_members(p)
    answers = [(_gp_feedback_record(p, n) or {}) for n in members]
    answers = [v for v in answers if v.get("happened") is not None]
    yes = sum(1 for v in answers if v.get("happened") is True)
    no = sum(1 for v in answers if v.get("happened") is False)
    needed = len(members) // 2 + 1
    outcome = "held" if yes >= needed else "not_held" if no >= needed else "pending"
    return {"state": outcome, "yes": yes, "no": no,
            "answered": len(answers), "of": len(members)}


def _gp_postcall_due(now=None):
    """Emit the single GRO.50 reminder and close unanswered prompts after day three."""
    now = now or time.time()
    changed = False
    for p in _gplans():
        if p.get("state") not in ("confirmed", "locked", "done"):
            continue
        times = _gp_feedback_times(p)
        if not times["due"] or now < times["due"]:
            continue
        if not p.get("feedback_members"):
            p["feedback_members"] = _gp_feedback_members(p)
            changed = True
        outcome = _gp_feedback_outcome(p)
        g = _gi_find(p.get("gid"))
        if (now >= times["reminder"] and now < times["expires"]
                and outcome["answered"] < outcome["of"] and not p.get("feedback_reminded")):
            p["feedback_reminded"] = now
            if g:
                _gi_say(g, "Two days since %s — did it happen? One tap, and I’ll stop asking. "
                         "It closes on its own tomorrow either way." % (g.get("title") or "the call"),
                        code="feedback_reminder", title=g.get("title") or "")
            changed = True
        if now >= times["expires"] and p.get("state") != "done":
            p["state"] = "done"
            p["feedback_closed"] = now
            p["updated"] = now
            changed = True
    if changed:
        _save_store()
    return changed


def _gp_public(p, me=""):
    if not p:
        return None
    conf = _gp_confirms(p)
    g = _gi_find(p.get("gid"))
    act = [m.get("name") for m in _gi_active(g)] if g else []
    now = time.time()
    feedback_times = _gp_feedback_times(p)
    feedback_outcome = _gp_feedback_outcome(p)
    my_feedback = _gp_feedback_record(p, me)
    mode = p.get("mode") or (g.get("mode") if g else "offline") or "offline"
    place = str(p.get("place") or "").strip()
    link = str(p.get("link") or "").strip()
    sides = dict(p.get("sides") or {})
    live = dict(p.get("live") or {})
    side_counts = {"in_person": 0, "call": 0, "undecided": 0}
    for name in act:
        key = _norm_name(name)
        # «Не смогу прийти» сохраняет участника в группе, но не обещает группе его присутствие.
        if (live.get(key) or {}).get("status") == "cant_make_it":
            continue
        side = (sides.get(key) or {}).get("side")
        if side in ("in_person", "call"):
            side_counts[side] += 1
        else:
            side_counts["undecided"] += 1
    return {
        "id": p.get("id"), "gid": p.get("gid"), "version": p.get("version"),
        "when": p.get("when"), "place": place, "note": p.get("note"),
        "starts_at": p.get("starts_at"), "state": p.get("state"),
        # Строка места — единственное, чем офлайн-борд отличается от онлайн-борда (GR.25 «Gràcia ·
        # Nømad» против GRO.25 «Video call · link saved»). Поэтому её различие живёт ЗДЕСЬ, в
        # данных, а не в двух экранах: два экрана разошлись бы на первой правке.
        "mode": mode,
        "link": link,
        # GRO.25a: интент завели без ссылки — план согласован, а подключиться некуда. Группе про
        # это говорят прямо, организатору дают вставить ссылку.
        "needs_link": mode in ("online", "hybrid") and not link,
        "needs_place": mode == "hybrid" and not place,
        "details_ready": mode != "hybrid" or bool(place and link),
        "sides": sides if mode == "hybrid" else {},
        "my_side": (sides.get(_norm_name(me)) or {}).get("side") if mode == "hybrid" else None,
        "side_counts": side_counts if mode == "hybrid" else None,
        "confirmed": conf, "confirmed_count": len(conf),
        # Who has not answered THIS version — the counter is meaningless without it.
        "waiting": [n for n in act if n not in conf
                    and (p.get("responses") or {}).get(n, {}).get("version") != p.get("version")],
        "declined": [n for n, r in (p.get("responses") or {}).items() if r.get("state") == "declined"],
        "my_response": (p.get("responses") or {}).get(str(me or ""), {}).get("state"),
        # Сколько ещё «да» нужно, чтобы план встал сам. Считается от ВСЕГО состава (борд GR.26
        # «Waiting for everyone»), а не от тройки: тройка — это пол для фиксации организатором.
        "needs": max(0, len(act) - len(conf)),
        # Раунд и потолок — на экране это «Round 2 of 3» и «Last round» (GR.28/29). Числа отдаёт
        # сервер, чтобы подпись не разошлась с тем, что он на самом деле разрешает.
        #
        # Раунд НЕ равен версии, хотя их легко перепутать. Версия растёт от любой смены условий —
        # включая перенос по итогам голосования и правку организатора; раунд считает только
        # встречные предложения (GR.27→28→29). Пока это было одно число, перенос утверждённого
        # плана поднимал «раунд» до третьего, и следующее согласование начиналось сразу
        # исчерпанным: «Last round» на первом же экране.
        # GR.45a: кто уже в пути, кто опаздывает, кто на месте. Отдаётся ВСЕЙ группе, в отличие
        # от один-на-один, где это личное: здесь «опаздываю» адресовано всем сразу, и знать об
        # этом должен каждый, а не только тот, кто откроет чат.
        "live": live,
        "my_live": live.get(_norm_name(me)),
        # Встреча уже идёт — кадр меняется с «заперто, через два часа» на «происходит сейчас».
        "started": bool(p.get("starts_at")) and time.time() >= float(p.get("starts_at") or 0)
                   and p.get("state") in ("confirmed", "locked"),
        "round": _gp_round(p),
        # Автор последнего предложения — фактом, а не догадкой экрана.
        "proposed_by": p.get("proposed_by"),
        "max_rounds": GP_MAX_ROUNDS,
        "rounds_used_up": _gp_round(p) >= GP_MAX_ROUNDS,
        # Организатор может закрепить план (GR.30), когда раунды кончились и согласных хотя бы трое.
        "can_fix": bool(g) and _norm_name(me) == _norm_name(g.get("owner"))
                   and p.get("state") == "proposed"
                   and _gp_round(p) >= GP_MAX_ROUNDS
                   # Закрепляющий организатор согласен с тем, что закрепляет (gp_fix) — его голос
                   # считается, даже если отдельного «Confirm» он не нажимал (кадр GR.29).
                   and len({_norm_name(n) for n in conf} | {_norm_name(g.get("owner"))}) >= GP_FIX_MIN_CONFIRMS,
        "fixed_by": p.get("fixed_by"),
        # Начало окна «Staying» — полоса GR.30/31 показывает прошедшее время до замка.
        "fixed_at": p.get("fixed_at"),
        # Версии по раундам — лист «Pick the final version» (GR.29a).
        "rounds_log": [{"round": r.get("round"), "by": r.get("by"), "when": r.get("when"),
                        "place": r.get("place"), "starts_at": r.get("starts_at")}
                       for r in (p.get("rounds_log") or [])],
        # Пауза «вас двое» (GR.40–40f): срок паузы, вопрос обоим и ответы.
        "hold": _gp_hold_public(p, me, act),
        # «Ты не подтверждал этот план, но прийти можешь» — экран GR.31 у тех, кого зафиксировали
        # молчащими. Флаг личный: остальным этого выбора не показывают.
        "stay_or_leave": bool(p.get("fixed_by")) and str(me or "") in act and str(me or "") not in conf,
        # Правка сверху (GR/GRO.32→33): что изменилось, кто изменил и чей сейчас ход. `was` даёт
        # строку «21:00 · was 19:00» — без прежнего значения человек не поймёт, что именно поменяли.
        "update": ({"by": (p.get("update") or {}).get("by"),
                    "at": (p.get("update") or {}).get("at"),
                    "was": (p.get("update") or {}).get("from")} if p.get("update") else None),
        "accept_or_leave": bool(p.get("update")) and str(me or "") in act and str(me or "") not in conf,
        "editable": p.get("state") in ("proposed", "confirmed"),
        "locked": p.get("state") == "locked",
        # GRO.47-50: only the viewer's answer is returned. The aggregate contains counts, never
        # names or somebody else's private reason/rating.
        "my_feedback": dict(my_feedback) if my_feedback else None,
        # Отменённый план встречей не был — «Did you meet?» по нему не спрашиваем (закрытая пауза
        # GR.40b висит на странице сутки, и через час после несостоявшегося начала спросила бы).
        "feedback_due": bool(feedback_times["due"] and now >= feedback_times["due"]
                             and now < feedback_times["expires"] and p.get("state") != "cancelled"),
        "feedback_expires_at": feedback_times["expires"] or None,
        "feedback_reminder": bool(p.get("feedback_reminded")),
        "feedback_outcome": feedback_outcome,
        # Кто уже ответил на «Did you meet?» — только ФАКТ ответа, без ответа и причины: борд
        # GR.47/GR.50 показывает у каждого «Answered» / «Hasn't answered», и больше ничего.
        "feedback_answered": [n for n in _gp_feedback_members(p)
                              if (_gp_feedback_record(p, n) or {}).get("happened") is not None]
                             if feedback_times["due"] else [],
    }


def _gp_log_round(p, by, now):
    """Записать версию плана этого раунда — из них организатор выбирает финальную (борд GR.29a
    «Pick the final version»: «Marc’s suggestion · round 3», «Jane’s suggestion · round 2»,
    «Your plan · round 1»). Кто подтвердил версию, пока она была текущей, — там же."""
    log = p.setdefault("rounds_log", [])
    log.append({"round": _gp_round(p), "by": by, "at": now,
                "when": p.get("when"), "place": p.get("place"), "link": p.get("link"),
                "starts_at": p.get("starts_at"),
                "confirmed": [n for n, r in (p.get("responses") or {}).items()
                              if (r or {}).get("state") == "confirmed"]})


def _gp_log_confirm(p, who):
    log = p.get("rounds_log") or []
    if log and log[-1].get("round") == _gp_round(p) and who not in log[-1].setdefault("confirmed", []):
        log[-1]["confirmed"].append(who)


def gp_begin(gid, who, when="", place="", note="", starts_at=None, idem=None, link=""):
    """«Создать план» — available only at three. Sends ONE draft to the whole current roster; the
    organiser does not choose who it goes to, because choosing would make this a casting call."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    now = time.time()
    with _STORE_LOCK:
        g = _gi_find(gid)
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if g.get("state") == "closed_by_owner":
            return {"ok": False, "error": "CLOSED"}    # S10: закрытая комната — только для чтения
        if _norm_name(who) != _norm_name(g.get("owner")):
            return {"ok": False, "error": "NOT_ORGANIZER"}
        if len(_gi_active(g)) < GP_MIN_CONFIRMS:
            return _idem_put(idem, {"ok": False, "error": "NEED_THREE",
                                    "need": GP_MIN_CONFIRMS - len(_gi_active(g))})
        if _gp_of(gid):
            return _idem_put(idem, {"ok": False, "error": "PLAN_EXISTS"})
        try:
            sa = float(starts_at) if starts_at else None
        except (TypeError, ValueError):
            sa = None
        # A plan starting inside the freeze window cannot be confirmed by anybody: the two-hour lock
        # would close it on the very next request, leaving a "plan" that only its author agreed to
        # and that the system nonetheless treats as definitely happening. Refuse it instead.
        if sa is not None and sa - GP_LOCK_BEFORE <= now:
            return _idem_put(idem, {"ok": False, "error": "TOO_LATE",
                                    "note": "a plan must start more than two hours from now, "
                                            "or nobody can confirm it"})
        mode = str(g.get("mode") or "offline")
        initial_link = str(link or (g.get("intent") or {}).get("link") or g.get("link") or "")[:400]
        # OF.09: автор уже указал точное место в мастере. Оно хранится внутри группового интента
        # и не выдаётся приглашённым до согласия; когда группа дошла до плана, не просим его снова.
        initial_place = str(place or (g.get("intent") or {}).get("address") or "")[:160]
        p = {"id": "gp_%d_%s" % (int(now * 1000), hashlib.sha1(gid.encode("utf-8")).hexdigest()[:6]),
             "gid": gid, "owner": g.get("owner"), "version": 1, "round": 1,
             "when": str(when or "")[:120], "place": initial_place,
             "note": str(note or "")[:400], "starts_at": sa,
             # Онлайн или офлайн решает ИНТЕНТ, а не автор плана: группа собиралась под звонок или
             # под место, и подменять это на шаге плана значило бы позвать людей на одно, а свести
             # на другое. Ссылка приезжает оттуда же, если она была; если нет — GRO.25a.
             "mode": mode,
             "link": initial_link,
             "state": "proposed", "responses": {}, "created": now, "updated": now}
        if mode == "hybrid":
            p["sides"] = {
                _norm_name(m.get("name")): {
                    "side": m.get("join") if m.get("join") in ("in_person", "call") else "in_person",
                    "t": now,
                }
                for m in _gi_active(g)
            }
        # The organiser proposing it IS their confirmation — asking them to agree with themselves
        # would be theatre, and it would make three people impossible with a group of exactly three.
        if mode != "hybrid" or (str(p.get("place") or "").strip() and initial_link.strip()):
            p["responses"][g.get("owner")] = {"state": "confirmed", "t": now, "version": 1}
        _gp_log_round(p, g.get("owner"), now)
        _gplans().append(p)
        g["state"] = "planning"
        g["updated"] = now
        _gi_say(g, "A group plan is ready. Confirm to join it.", code="plan_ready")
        _save_store()
        return _idem_put(idem, {"ok": True, "plan": _gp_public(p, who)})


def gp_respond(pid, who, action, when="", place="", note="", starts_at=None, idem=None, link=""):
    """confirm | decline | counter.

    A COUNTER is not a vote against the plan — it is «внести своё предложение»: it replaces the
    terms, bumps the version and sends everyone back to confirming, exactly as the daily describes
    («это выносится на общее обсуждение, и процесс утверждения плана запускается по новой»)."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    who = str(who or "").strip()
    action = str(action or "").strip().lower()
    now = time.time()
    with _STORE_LOCK:
        _gp_lock_due(now)
        p = _gp_find(pid)
        if not p:
            return {"ok": False, "error": "NO_SUCH_PLAN"}
        g = _gi_find(p.get("gid"))
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if not any(_norm_name(m.get("name")) == _norm_name(who) for m in _gi_active(g)):
            return {"ok": False, "error": "NOT_A_MEMBER"}
        if p.get("state") == "locked":
            return _idem_put(idem, {"ok": False, "error": "LOCKED"})
        if p.get("state") in ("cancelled", "done"):
            return _idem_put(idem, {"ok": False, "error": "CLOSED"})
        # План на паузе не принимает ни подтверждений, ни встречных предложений: состава для
        # групповой встречи нет. Раньше сервер отвечал «ok» и не менял ничего — человек жал
        # «Подтвердить», получал успех и не понимал, почему на экране всё по-прежнему.
        if p.get("state") == "below_quorum":
            return _idem_put(idem, {"ok": False, "error": "BELOW_QUORUM"})
        v = int(p.get("version") or 1)
        rnd = _gp_round(p)
        if action == "counter" and p.get("state") != "proposed":
            # Once the plan is agreed, changing it is not one person's move any more — it goes to a
            # vote. Without this guard a single «внести своё предложение» tore up a confirmed plan
            # and sent three people back to square one on their own.
            return _idem_put(idem, {"ok": False, "error": "ALREADY_CONFIRMED",
                                    "note": "open a vote to change an agreed plan"})
        if action == "counter":
            # РАУНДЫ. Борд GR.28/GR.29: «Round 2 of 3», «This is the last round. After it Marc
            # fixes the plan and it stops changing». Бесконечные встречные предложения — это не
            # согласование, а способ никогда не договориться; трое могут гонять время по кругу
            # сутками, и план так и не наступит. После третьего раунда слово за организатором
            # (gp_fix), а не за следующим предложившим.
            if rnd >= GP_MAX_ROUNDS:
                return _idem_put(idem, {"ok": False, "error": "ROUNDS_USED_UP",
                                        "rounds": rnd, "max_rounds": GP_MAX_ROUNDS,
                                        "note": "the organiser fixes the plan now",
                                        "plan": _gp_public(p, who)})
            p["version"] = v + 1
            p["round"] = rnd + 1
            # Кто предложил. Экран выводил это эвристикой «единственный подтвердивший» — она
            # рассыпалась ровно там, где кадр GR.29 и нарисован: после второго подтверждения
            # подтвердивших двое, и заголовок срывался в «ждём всех», хотя пояснение рядом
            # продолжало называть имя.
            p["proposed_by"] = who
            if when:
                p["when"] = str(when)[:120]
            if place:
                p["place"] = str(place)[:160]
            if link:
                p["link"] = str(link)[:400]
            if note:
                p["note"] = str(note)[:400]
            if starts_at:
                try:
                    p["starts_at"] = float(starts_at)
                except (TypeError, ValueError):
                    pass
            # Everything confirmed against the old terms is void — including the organiser's own.
            complete = p.get("mode") != "hybrid" or bool(str(p.get("place") or "").strip()
                                                           and str(p.get("link") or "").strip())
            p["responses"] = ({who: {"state": "confirmed", "t": now, "version": p["version"]}}
                              if complete else {})
            p["state"] = "proposed"
            p["updated"] = now
            _gp_log_round(p, who, now)
            _gi_say(g, "%s suggested a change: %s%s. Everyone confirms again."
                    % (who, p.get("when") or "", (", " + p.get("place")) if p.get("place") else ""),
                               code="plan_countered", who=who, when=p.get("when"), place=p.get("place"))
            _save_store()
            return _idem_put(idem, {"ok": True, "countered": True, "plan": _gp_public(p, who)})
        if action == "decline":
            p["responses"][who] = {"state": "declined", "t": now, "version": v}
            p["updated"] = now
            _gi_say(g, "%s will not join this plan." % who, code="plan_declined", who=who)
            _save_store()
            return _idem_put(idem, {"ok": True, "plan": _gp_public(p, who)})
        if action != "confirm":
            return {"ok": False, "error": "BAD_ACTION"}
        if p.get("mode") == "hybrid" and not (str(p.get("place") or "").strip()
                                                and str(p.get("link") or "").strip()):
            return _idem_put(idem, {"ok": False, "error": "PLAN_INCOMPLETE",
                                    "needs_place": not bool(str(p.get("place") or "").strip()),
                                    "needs_link": not bool(str(p.get("link") or "").strip()),
                                    "plan": _gp_public(p, who)})
        p["responses"][who] = {"state": "confirmed", "t": now, "version": v}
        p["updated"] = now
        _gp_log_confirm(p, who)
        conf = _gp_confirms(p)
        # ПОДТВЕРЖДАЮТ ВСЕ. Борд GR.26 говорит это заголовком — «Waiting for everyone» — и текстом:
        # «The plan starts when all three confirm». Раньше здесь хватало трёх, и четвёртый человек
        # узнавал, что план без него, из ленты: он ещё думал, а состав уже закрыли. Молчащего
        # теперь не выбрасывают — его ждут, а когда ждать больше нельзя (раунды кончились),
        # организатор фиксирует план явно, и молчавшему предлагают остаться или выйти (GR.30/31).
        need = [m.get("name") for m in _gi_active(g)]
        if p.get("state") == "proposed" and len(conf) >= len(need):
            p["state"] = "confirmed"
            g["state"] = "planned"
            _gi_say(g, "Everyone confirmed. The plan is set: %s." % ", ".join(conf), code="plan_confirmed", names=", ".join(conf))
        elif p.get("update") and len(conf) >= len(need):
            # Правку приняли все — «принять или выйти» закончилось, и план снова просто план.
            # Пока метка висит, экран показывал бы «Marc changed the time» людям, которые уже
            # ответили, и считал бы состав по-другому (см. `_gp_recount`).
            p.pop("update", None)
            _gi_say(g, "Everyone accepted the change.", code="change_accepted")
        _save_store()
        return _idem_put(idem, {"ok": True, "plan": _gp_public(p, who)})


def gp_cancel(pid, who, idem=None):
    """GR.40 «Cancel the plan» — организатор закрывает план, который встал на паузу.

    Появилось потому, что выхода из below_quorum не было ВООБЩЕ. Единственным способом закрыть
    план оставалось голосование, а оно требует состояния confirmed (gp_vote_open) — то есть
    именно из того состояния, куда план упал, закрыть его было нечем. План висел вечно.

    Отменяет только организатор и только то, что ещё живо. Группа при этом НЕ распускается: люди
    остались, разговор остался, и завести новый план они могут — поэтому она возвращается в
    «можно планировать», а не куда-нибудь в отмену."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    who = str(who or "").strip()
    now = time.time()
    with _STORE_LOCK:
        _gp_lock_due(now)
        p = _gp_find(pid)
        if not p:
            return {"ok": False, "error": "NO_SUCH_PLAN"}
        g = _gi_find(p.get("gid"))
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if _norm_name(who) != _norm_name(g.get("owner")):
            return {"ok": False, "error": "NOT_ORGANIZER"}
        if p.get("state") == "locked":
            return _idem_put(idem, {"ok": False, "error": "LOCKED"})
        if p.get("state") in ("cancelled", "done"):
            return _idem_put(idem, {"ok": False, "error": "CLOSED"})
        p["state"] = "cancelled"
        p["updated"] = now
        p["version"] = int(p.get("version") or 1) + 1
        g["state"] = "ready_to_plan"
        g["updated"] = now
        _gi_say(g, "%s cancelled the plan. The group is still here." % who, code="plan_cancelled_group_stays", who=who)
        _save_store()
    return _idem_put(idem, {"ok": True, "plan": _gp_public(p, who)})


def gp_fix(pid, who, idem=None, round_no=None):
    """GR.30 «Fix the plan» — организатор закрывает согласование, когда раунды кончились.

    Зачем отдельное действие, а не автоматика по счётчику раундов: борд даёт организатору ВЫБОР —
    «Fix the plan» или «Give it more time». Автоматическая фиксация отняла бы у него второй
    вариант, а он осмысленный: человек может знать, что молчащий просто спит.

    Не подтвердившие НЕ выбрасываются. Борд GR.31 показывает им экран «Stay or leave»: план
    состоялся без их «да», но прийти они всё ещё могут. Поэтому состав плана здесь не режется —
    режет его только собственный уход (gp_leave) или отказ."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    who = str(who or "").strip()
    now = time.time()
    with _STORE_LOCK:
        _gp_lock_due(now)
        p = _gp_find(pid)
        if not p:
            return {"ok": False, "error": "NO_SUCH_PLAN"}
        g = _gi_find(p.get("gid"))
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if _norm_name(who) != _norm_name(g.get("owner")):
            return {"ok": False, "error": "NOT_ORGANIZER"}
        if p.get("state") == "locked":
            return _idem_put(idem, {"ok": False, "error": "LOCKED"})
        if p.get("state") != "proposed":
            return _idem_put(idem, {"ok": False, "error": "NOT_PROPOSED", "plan": _gp_public(p, who)})
        # Фиксировать можно только когда раунды исчерпаны: иначе это способ обойти согласование —
        # предложил и тут же закрепил, не дав никому ответить.
        if int(p.get("version") or 1) < GP_MAX_ROUNDS:
            return _idem_put(idem, {"ok": False, "error": "ROUNDS_LEFT",
                                    "rounds": int(p.get("version") or 1),
                                    "max_rounds": GP_MAX_ROUNDS})
        # GR.29a «Pick the final version»: организатор может закрепить не последнюю версию, а одну
        # из прежних. Согласие тогда считается по ЭТОЙ версии — кто подтверждал её, пока она была
        # текущей (плюс сам организатор, раз он её выбирает). Правило «один организатор — это указ»
        # действует и здесь: своя версия, которую никто не подтверждал, не закрепляется.
        pick = None
        try:
            rn = int(round_no) if round_no not in (None, "") else None
        except (TypeError, ValueError):
            rn = None
        if rn is not None and rn != _gp_round(p):
            pick = next((r for r in (p.get("rounds_log") or []) if int(r.get("round") or 0) == rn), None)
            if not pick:
                return _idem_put(idem, {"ok": False, "error": "NO_SUCH_ROUND", "plan": _gp_public(p, who)})
        if pick:
            act_n = {_norm_name(m.get("name")) for m in _gi_active(g)}
            conf = [n for n in (pick.get("confirmed") or []) if _norm_name(n) in act_n]
            if not any(_norm_name(n) == _norm_name(who) for n in conf):
                conf.append(who)
        else:
            # Закрепить — и есть согласиться: организатор, нажавший «Fix this plan» на версии
            # Marc (GR.29a), с ней согласен. Раньше требовалось ещё отдельное «Confirm», и без него
            # фиксация отвечала ALONE при согласном Marc — кнопка на кадре GR.29 не работала.
            conf = list(_gp_confirms(p))
            if not any(_norm_name(n) == _norm_name(who) for n in conf):
                conf.append(who)
        if len(conf) < GP_FIX_MIN_CONFIRMS:
            # Согласен только сам организатор — это указ, а не план (см. GP_FIX_MIN_CONFIRMS).
            return _idem_put(idem, {"ok": False, "error": "ALONE",
                                    "need": GP_FIX_MIN_CONFIRMS,
                                    "confirmed": conf, "plan": _gp_public(p, who)})
        if len(_gi_active(g)) < GP_MIN_CONFIRMS:
            # А вот людей в плане должно остаться трое — это §1, и оно про состав, не про согласия.
            return _idem_put(idem, {"ok": False, "error": "NEED_THREE",
                                    "confirmed": conf, "plan": _gp_public(p, who)})
        if pick:
            for k in ("when", "place", "link", "starts_at"):
                if pick.get(k) not in (None, ""):
                    p[k] = pick[k]
            p["version"] = int(p.get("version") or 1) + 1
            p["responses"] = {n: {"state": "confirmed", "t": now, "version": p["version"]} for n in conf}
            p["fixed_round"] = rn
        else:
            p.setdefault("responses", {}).setdefault(
                who, {"state": "confirmed", "t": now, "version": int(p.get("version") or 1)})
        p["state"] = "confirmed"
        p["fixed_by"] = who
        p["fixed_at"] = now
        p["updated"] = now
        g["state"] = "planned"
        silent = [m.get("name") for m in _gi_active(g)
                  if _norm_name(m.get("name")) not in {_norm_name(c) for c in conf}]
        _gi_say(g, "%s fixed the plan: %s%s." % (who, p.get("when") or "",
                                                 (", " + p.get("place")) if p.get("place") else ""),
                                                            code="plan_fixed", who=who, when=p.get("when"), place=p.get("place"))
        if silent:
            # Названы поимённо и нейтрально: им предстоит решить, идут они или выходят (GR.31),
            # и группа должна понимать, почему у этих людей в составе стоит вопрос.
            _gi_say(g, "%s did not confirm this time and can stay or leave."
                    % ", ".join(str(s) for s in silent),
                               code="silent_stay_or_leave", names=", ".join(str(s) for s in silent))
        _save_store()
        return _idem_put(idem, {"ok": True, "fixed": True, "unconfirmed": silent,
                                "plan": _gp_public(p, who)})


def gp_vote_open(pid, who, kind, when="", place="", note="", starts_at=None, idem=None, link=""):
    """Once a plan is in force the organiser cannot simply change or drop it — «при нажатии на эту
    кнопку у нас выносится голосование». kind is 'edit' or 'cancel'."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    kind = str(kind or "").strip().lower()
    if kind not in ("edit", "cancel"):
        return {"ok": False, "error": "BAD_KIND"}
    now = time.time()
    with _STORE_LOCK:
        _gp_lock_due(now)
        p = _gp_find(pid)
        if not p:
            return {"ok": False, "error": "NO_SUCH_PLAN"}
        if p.get("state") != "confirmed":
            return _idem_put(idem, {"ok": False,
                                    "error": "LOCKED" if p.get("state") == "locked" else "NOT_CONFIRMED"})
        g = _gi_find(p.get("gid"))
        if not any(_norm_name(m.get("name")) == _norm_name(who) for m in _gi_active(g or {})):
            return {"ok": False, "error": "NOT_A_MEMBER"}
        if any(v.get("plan_id") == pid and v.get("state") == "open" for v in _gvotes()):
            return _idem_put(idem, {"ok": False, "error": "VOTE_IN_PROGRESS"})
        vote = {"id": "gvo_%d" % int(now * 1000), "gid": p.get("gid"), "plan_id": pid,
                "kind": kind, "by": who, "state": "open", "created": now,
                "proposal": {"when": str(when or "")[:120], "place": str(place or "")[:160],
                             "link": str(link or "")[:400], "note": str(note or "")[:400],
                             "starts_at": starts_at},
                # Whoever calls the vote has cast the first one, by calling it.
                "votes": {who: True}}
        _gvotes().append(vote)
        _gi_say(g, "%s asked the group to %s the plan. Please vote."
                % (who, "change" if kind == "edit" else "cancel"),
                           code="vote_opened", who=who, kind=kind)
        _save_store()
        return _idem_put(idem, _gp_vote_view(vote, who))


def _gp_vote_view(v, me=""):
    g = _gi_find(v.get("gid"))
    act = [m.get("name") for m in _gi_active(g)] if g else []
    votes = v.get("votes") or {}
    yes = [n for n, b in votes.items() if b]
    no = [n for n, b in votes.items() if not b]
    owner = g.get("owner") if g else ""
    closes = float(v.get("created") or 0) + GP_VOTE_WINDOW
    return {"ok": True, "vote": {"id": v.get("id"), "plan_id": v.get("plan_id"),
                                 "kind": v.get("kind"), "state": v.get("state"),
                                 "by": v.get("by"), "organiser": owner,
                                 "yes": len(yes), "no": len(no),
                                 # Ждём только участников: организатор не голосует, он решает.
                                 "waiting": [n for n in act if n not in votes
                                             and _norm_name(n) != _norm_name(owner)],
                                 "my_vote": votes.get(str(me or "")),
                                 # Срок — на экране это «closes in 4h» (GR.36). Отдаём момент, а
                                 # не «осталось столько-то»: клиент считает сам и не врёт, пока
                                 # экран открыт.
                                 "closes_at": closes,
                                 # Совет и решение — разные вещи, и на борде они разными словами
                                 # (GR.37 «the group asked, you decide»). Клиенту нужны обе.
                                 "advice": v.get("advice"), "decided": v.get("decided"),
                                 # Ждём ли решения организатора — то, чем GR.37 отличается от GR.38.
                                 "awaiting_decision": v.get("state") == "closed" and not v.get("decided"),
                                 "i_decide": bool(owner) and _norm_name(me) == _norm_name(owner),
                                 "why": v.get("why"), "proposal": v.get("proposal")}}


def gp_vote(vote_id, who, yes, idem=None):
    """One vote each. The result is a majority OF THOSE WHO VOTED — a tie is not a majority, so the
    plan stands. Resolved once everyone has answered; the two-hour lock closes it either way."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    now = time.time()
    with _STORE_LOCK:
        _gp_lock_due(now)
        _gp_votes_due(now)
        v = next((x for x in _gvotes() if x.get("id") == vote_id), None)
        if not v:
            return {"ok": False, "error": "NO_SUCH_VOTE"}
        if v.get("state") != "open":
            return _idem_put(idem, _gp_vote_view(v, who))
        g = _gi_find(v.get("gid"))
        act = [m.get("name") for m in _gi_active(g)] if g else []
        if not any(_norm_name(n) == _norm_name(who) for n in act):
            return {"ok": False, "error": "NOT_A_MEMBER"}
        v.setdefault("votes", {})[who] = bool(yes)
        # Голосуют УЧАСТНИКИ, организатор — решает (борд GR.36 «Vote 1 of 2», GR.37 «Jane Voted,
        # Marc Voted, You Confirmed»). Ждать его голоса значило держать голосование открытым все
        # шесть часов: кнопки «проголосовать» у организатора нет — у него «See the numbers and decide».
        owner = _norm_name(g.get("owner")) if g else ""
        voters = [n for n in act if _norm_name(n) != owner] or act
        if all(n in v["votes"] for n in voters):
            _gp_close_vote(v, now)
        _save_store()
        return _idem_put(idem, _gp_vote_view(v, who))


def _gp_close_vote(v, now=None):
    """COUNT the vote. Deliberately does not act on it.

    Борд GR.35 говорит это открытым текстом ещё до первого голоса: «The result is advice — Marc
    makes the final call», и повторяет голосующему (GR.36 «Your answer is advice»), и объявляет
    итог (GR.38 «3 of 5 voted to change it. On Kleal the vote is advice — the organiser decides»).
    Раньше здесь большинство само переносило и само отменяло встречу; человека, который её собрал,
    об этом просто ставили в известность. Теперь голосование даёт ЧИСЛА, а решение — отдельным
    действием организатора (`gp_vote_decide`).

    Что «большинство» значит для совета: большинство ОТ ОТВЕТИВШИХ, ничья — не большинство. Это та
    же арифметика, что была, но теперь она называет исход советом, а не приговором."""
    now = now or time.time()
    votes = v.get("votes") or {}
    yes = sum(1 for b in votes.values() if b)
    no = len(votes) - yes
    g = _gi_find(v.get("gid"))
    act = [m.get("name") for m in _gi_active(g)] if g else []
    # Молчавшие — среди голосующих, то есть без организатора: он не голосует, а решает.
    owner = _norm_name(g.get("owner")) if g else ""
    voters = [n for n in act if _norm_name(n) != owner] or act
    silent = max(0, len([n for n in voters if n not in votes]))
    v["state"] = "closed"
    v["closed"] = now
    v["tally"] = {"yes": yes, "no": no, "silent": silent}
    v["advice"] = "change" if yes > no else "keep"
    if g:
        what = "change" if v.get("kind") == "edit" else "cancel"
        _gi_say(g, "The vote is closed: %d for, %d against, %d didn’t answer. "
                   "It’s %s’s call whether to %s the plan."
                % (yes, no, silent, g.get("owner"), what),
                           code="vote_closed", yes=yes, no=no, silent=silent, owner=g.get("owner"), what=what)
    return v


def _gp_votes_due(now=None):
    """Шесть часов вышли — считаем по тем, кто ответил (GR.35 «Everyone gets 6 hours to answer»).

    Без срока совещательное голосование зависало бы навсегда: один молчащий — и организатору
    нечего решать, потому что «голоса ещё идут»."""
    now = now or time.time()
    changed = False
    for v in _gvotes():
        if v.get("state") == "open" and now - float(v.get("created") or now) >= GP_VOTE_WINDOW:
            _gp_close_vote(v, now)
            changed = True
    return changed


def _gp_sweep():
    """Провести всё, что наступает САМО: двухчасовой замок и истёкший срок голосования.

    Оба события — про время, а не про чьё-то нажатие, поэтому их обязан проводить и тот, кто
    просто пришёл ЧИТАТЬ. Пока это делали только пишущие ручки, группа, открытая на чтение,
    показывала живой план с кнопкой «Подтвердить» — а сервер на неё отвечал LOCKED: экран узнавал
    правду только после того, как соврал человеку."""
    with _STORE_LOCK:
        # Плюс смена организатора: конец голосования за перехват и истёкшее предложение роли
        # наступают сами (GR.43/44) — их тоже проводит тот, кто пришёл читать.
        if _gp_lock_due() | _gp_votes_due() | _gi_roles_due() | _gp_hold_due():
            _save_store()


def _gp_apply_change(p, g, pr, by, now):
    """Изменить условия УТВЕРЖДЁННОГО плана — и заново спросить каждого.

    Один код на два входа: организатор правит сам (GR.32) или применяет совет голосования
    (GR.37 «Change the plan»). Итог по борду одинаковый: «Everyone who already joined has to accept
    or leave, and the open invite is updated to the new time» — то есть подтверждения обнуляются,
    но состав НЕ режется и встреча не отменяется: «the group carries on either way» (GR.33).

    Раунд не трогаем: это не встречное предложение, а правка сверху (см. `_gp_public`)."""
    p["prev"] = {"when": p.get("when"), "place": p.get("place"), "link": p.get("link"),
                 "starts_at": p.get("starts_at")}
    if pr.get("when"):
        p["when"] = str(pr["when"])[:120]
    if pr.get("place"):
        p["place"] = str(pr["place"])[:160]
    if pr.get("link"):
        p["link"] = str(pr["link"])[:400]
    if pr.get("note"):
        p["note"] = str(pr["note"])[:400]
    if pr.get("starts_at"):
        try:
            p["starts_at"] = float(pr["starts_at"])
        except (TypeError, ValueError):
            pass
    p["version"] = int(p.get("version") or 1) + 1
    p["update"] = {"by": by, "at": now, "from": p["prev"]}
    p["responses"] = {by: {"state": "confirmed", "t": now, "version": p["version"]}}
    p["updated"] = now
    if g:
        # Открытое приглашение показывает новое время само: карточка группы читает план, а не
        # свою копию условий, — поэтому «the open invite is updated» ничего дополнительно не требует.
        g["updated"] = now
        _gi_say(g, "%s changed the plan: %s%s. Accept to stay in the group, or leave."
                % (by, p.get("when") or "", (", " + p.get("place")) if p.get("place") else ""),
                           code="plan_updated", who=by, when=p.get("when"), place=p.get("place"))
    return p


def gp_update(pid, who, when="", place="", note="", starts_at=None, idem=None, link=""):
    """GR/GRO.32 «Change the time or place» — организатор правит утверждённый план напрямую.

    Почему не через голосование: голосование — инструмент УЧАСТНИКА, который хочет попросить
    (GR.35 «Ask the group to change this plan?»). У организатора власть менять есть по роли, и
    борд даёт ему прямую кнопку; цена — каждый участник заново говорит «принимаю» или уходит."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    who = str(who or "").strip()
    now = time.time()
    with _STORE_LOCK:
        _gp_lock_due(now)
        p = _gp_find(pid)
        if not p:
            return {"ok": False, "error": "NO_SUCH_PLAN"}
        g = _gi_find(p.get("gid"))
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if _norm_name(who) != _norm_name(g.get("owner")):
            return {"ok": False, "error": "NOT_ORGANIZER"}
        if p.get("state") == "locked":
            return _idem_put(idem, {"ok": False, "error": "LOCKED"})
        if p.get("state") != "confirmed":
            # До утверждения менять условия нечего: там для этого есть встречное предложение,
            # и оно считается раундом.
            return _idem_put(idem, {"ok": False, "error": "NOT_CONFIRMED",
                                    "note": "counter-propose while the plan is still being agreed",
                                    "plan": _gp_public(p, who)})
        if any(v.get("plan_id") == pid and v.get("state") == "open" for v in _gvotes()):
            # Иначе группа отвечает на вопрос про время, которого уже нет.
            return _idem_put(idem, {"ok": False, "error": "VOTE_IN_PROGRESS"})
        if not (when or place or link or starts_at):
            return _idem_put(idem, {"ok": False, "error": "NOTHING_TO_CHANGE"})
        try:
            sa = float(starts_at) if starts_at else None
        except (TypeError, ValueError):
            sa = None
        if sa is not None and sa - GP_LOCK_BEFORE <= now:
            return _idem_put(idem, {"ok": False, "error": "TOO_LATE",
                                    "note": "the new time must start more than two hours from now"})
        _gp_apply_change(p, g, {"when": when, "place": place, "link": link,
                                "note": note, "starts_at": sa},
                         who, now)
        _save_store()
        return _idem_put(idem, {"ok": True, "updated": True, "plan": _gp_public(p, who)})


def gp_link(pid, who, link="", idem=None):
    """GRO.25a «Add the call link» — онлайн-план без ссылки: подключиться некуда.

    Ссылку ставит организатор. Второй кнопкой борд предлагает «Ask the group to host instead» —
    это просто сообщение в общий чат, а не отдельная сущность: хост меняется тем, что ссылку
    пришлёт кто-то другой, и тогда её сохранит организатор."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    who = str(who or "").strip()
    link = str(link or "").strip()[:400]
    now = time.time()
    with _STORE_LOCK:
        p = _gp_find(pid)
        if not p:
            return {"ok": False, "error": "NO_SUCH_PLAN"}
        g = _gi_find(p.get("gid"))
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if _norm_name(who) != _norm_name(g.get("owner")):
            return {"ok": False, "error": "NOT_ORGANIZER"}
        if (p.get("mode") or g.get("mode")) not in ("online", "hybrid"):
            return _idem_put(idem, {"ok": False, "error": "NOT_ONLINE"})
        if not link:
            return _idem_put(idem, {"ok": False, "error": "LINK_REQUIRED"})
        if not re.match(r"^(https?://|[a-z0-9.-]+\.[a-z]{2,})", link, re.I):
            # Не валидатор ссылок, а защита от пустого текста в поле: человек, который придёт по
            # такой «ссылке», не попадёт никуда, а узнает об этом за минуту до звонка.
            return _idem_put(idem, {"ok": False, "error": "BAD_LINK"})
        p["link"] = link
        if p.get("mode") == "hybrid" and str(p.get("place") or "").strip():
            p.setdefault("responses", {}).setdefault(
                g.get("owner"), {"state": "confirmed", "t": now, "version": p.get("version")})
        p["updated"] = now
        g["link"] = link
        _gi_say(g, "The call link is saved.", code="link_saved")
        _save_store()
        return _idem_put(idem, {"ok": True, "plan": _gp_public(p, who)})


def gp_details(pid, who, place=None, link=None, idem=None):
    """GRH.25a/25b: complete one missing entrance of a hybrid group plan.

    Place and call link are independent resources. Saving one must never overwrite the other, and
    nobody may confirm until both exist. Only the organiser edits these shared meeting details.
    """
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    who = str(who or "").strip()
    now = time.time()
    with _STORE_LOCK:
        p = _gp_find(pid)
        if not p:
            return {"ok": False, "error": "NO_SUCH_PLAN"}
        g = _gi_find(p.get("gid"))
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if _norm_name(who) != _norm_name(g.get("owner")):
            return _idem_put(idem, {"ok": False, "error": "NOT_ORGANIZER"})
        if (p.get("mode") or g.get("mode")) != "hybrid":
            return _idem_put(idem, {"ok": False, "error": "NOT_HYBRID"})
        if p.get("state") in ("locked", "cancelled", "done"):
            return _idem_put(idem, {"ok": False, "error": "LOCKED"})
        if place is None and link is None:
            return _idem_put(idem, {"ok": False, "error": "NOTHING_TO_CHANGE"})
        if place is not None:
            value = str(place or "").strip()[:160]
            if not value:
                return _idem_put(idem, {"ok": False, "error": "PLACE_REQUIRED"})
            p["place"] = value
            _gi_say(g, "The meeting place is saved.", code="place_saved")
        if link is not None:
            value = str(link or "").strip()[:400]
            if not value:
                return _idem_put(idem, {"ok": False, "error": "LINK_REQUIRED"})
            if not re.match(r"^(https?://|[a-z0-9.-]+\.[a-z]{2,})", value, re.I):
                return _idem_put(idem, {"ok": False, "error": "BAD_LINK"})
            p["link"] = value
            g["link"] = value
            _gi_say(g, "The call link is saved.", code="link_saved")
        p["updated"] = now
        if str(p.get("place") or "").strip() and str(p.get("link") or "").strip():
            p.setdefault("responses", {}).setdefault(
                g.get("owner"), {"state": "confirmed", "t": now, "version": p.get("version")})
        _save_store()
        return _idem_put(idem, {"ok": True, "plan": _gp_public(p, who)})


GP_MODES = ("offline", "online")


def gp_mode(pid, who, mode, idem=None):
    """GRH.25a/25b: finish an incomplete hybrid plan using its available entrance only.

    The board offers this as an explicit fallback beside the missing field: a saved place can
    become an offline plan, and a saved call link can become an online plan. It changes this
    meeting only; the group intent stays hybrid for future plans.
    """
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    who = str(who or "").strip()
    target = str(mode or "").strip().lower()
    if target not in GP_MODES:
        return {"ok": False, "error": "BAD_MODE", "allowed": list(GP_MODES)}
    now = time.time()
    with _STORE_LOCK:
        p = _gp_find(pid)
        if not p:
            return {"ok": False, "error": "NO_SUCH_PLAN"}
        g = _gi_find(p.get("gid"))
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if _norm_name(who) != _norm_name(g.get("owner")):
            return _idem_put(idem, {"ok": False, "error": "NOT_ORGANIZER"})
        if p.get("mode") != "hybrid":
            return _idem_put(idem, {"ok": False, "error": "NOT_HYBRID"})
        if p.get("state") in ("locked", "cancelled", "done"):
            return _idem_put(idem, {"ok": False, "error": "LOCKED"})
        if target == "offline" and not str(p.get("place") or "").strip():
            return _idem_put(idem, {"ok": False, "error": "NO_PLACE"})
        if target == "online" and not str(p.get("link") or "").strip():
            return _idem_put(idem, {"ok": False, "error": "NO_LINK"})

        p["mode"] = target
        p["sides"] = {}
        p["updated"] = now
        p.setdefault("responses", {}).setdefault(
            g.get("owner"), {"state": "confirmed", "t": now, "version": p.get("version")})
        _gi_say(g, "%s made this plan %s only." % (who, target),
                code="plan_mode_changed", who=who, mode=target)
        _save_store()
        return _idem_put(idem, {"ok": True, "plan": _gp_public(p, who)})


GP_SIDES = ("in_person", "call")


def gp_side(pid, who, side, idem=None):
    """GRH attendance switch. A member can move between the table and the call without cancelling."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    who = str(who or "").strip()
    side = str(side or "").strip().lower()
    if side not in GP_SIDES:
        return {"ok": False, "error": "BAD_SIDE", "allowed": list(GP_SIDES)}
    now = time.time()
    with _STORE_LOCK:
        p = _gp_find(pid)
        if not p:
            return {"ok": False, "error": "NO_SUCH_PLAN"}
        g = _gi_find(p.get("gid"))
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if p.get("mode") != "hybrid":
            return _idem_put(idem, {"ok": False, "error": "NOT_HYBRID"})
        if not any(_norm_name(m.get("name")) == _norm_name(who) for m in _gi_active(g)):
            return _idem_put(idem, {"ok": False, "error": "NOT_A_PARTICIPANT"})
        if p.get("state") not in ("proposed", "confirmed", "locked"):
            return _idem_put(idem, {"ok": False, "error": "NOT_OPEN", "state": p.get("state")})
        if side == "call" and not str(p.get("link") or "").strip():
            return _idem_put(idem, {"ok": False, "error": "NO_LINK"})
        if side == "in_person" and not str(p.get("place") or "").strip():
            return _idem_put(idem, {"ok": False, "error": "NO_PLACE"})
        previous = (p.get("sides") or {}).get(_norm_name(who), {}).get("side")
        p.setdefault("sides", {})[_norm_name(who)] = {"side": side, "t": now}
        p["updated"] = now
        if previous != side:
            _gi_say(g, "%s will join %s." % (who, "the call" if side == "call" else "in person"),
                    code="attendance_side", who=who, side=side)
        _save_store()
        return _idem_put(idem, {"ok": True, "plan": _gp_public(p, who)})


def gp_vote_decide(vote_id, who, apply=True, idem=None):
    """GR.37 «It’s your call» — организатор решает, что делать с советом группы.

    Только после закрытия голосования: решать, пока считают, значит не считать вовсе."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    who = str(who or "").strip()
    now = time.time()
    with _STORE_LOCK:
        _gp_lock_due(now)
        _gp_votes_due(now)
        v = next((x for x in _gvotes() if x.get("id") == vote_id), None)
        if not v:
            return {"ok": False, "error": "NO_SUCH_VOTE"}
        g = _gi_find(v.get("gid"))
        if not g or _norm_name(who) != _norm_name(g.get("owner")):
            return {"ok": False, "error": "NOT_ORGANIZER"}
        if v.get("state") == "open":
            return _idem_put(idem, {"ok": False, "error": "VOTE_OPEN",
                                    "note": "close the vote first, or wait for the six hours"})
        if v.get("decided"):
            return _idem_put(idem, _gp_vote_view(v, who))
        p = _gp_find(v.get("plan_id"))
        v["decided"] = "applied" if apply else "kept"
        v["decided_at"] = now
        if not apply or not p:
            _gi_say(g, "%s kept the plan as it is." % who, code="vote_kept", who=who)
            _save_store()
            return _idem_put(idem, _gp_vote_view(v, who))
        if p.get("state") == "locked":
            return _idem_put(idem, {"ok": False, "error": "LOCKED"})
        if v.get("kind") == "cancel":
            p["state"] = "cancelled"
            p["updated"] = now
            g["state"] = "chat_open"
            _gi_say(g, "%s cancelled the plan." % who, code="plan_cancelled", who=who)
        else:
            _gp_apply_change(p, g, v.get("proposal") or {}, who, now)
        _save_store()
        return _idem_put(idem, _gp_vote_view(v, who))


def gp_vote_close(vote_id, who, idem=None):
    """Закрыть голосование, не дожидаясь шести часов. Только организатор; счёт — по ответившим."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    with _STORE_LOCK:
        v = next((x for x in _gvotes() if x.get("id") == vote_id), None)
        if not v:
            return {"ok": False, "error": "NO_SUCH_VOTE"}
        g = _gi_find(v.get("gid"))
        if not g or _norm_name(who) != _norm_name(g.get("owner")):
            return {"ok": False, "error": "NOT_ORGANIZER"}
        if v.get("state") == "open":
            _gp_close_vote(v)
        _save_store()
        return _idem_put(idem, _gp_vote_view(v, who))


GP_LIVE = ("otw", "late", "here", "cant_make_it")


def gp_status(pid, who, status, eta_min=None, idem=None):
    """GR.45a/GR.45b — «я опаздываю» и что об этом узнаёт группа.

    Отличие от один-на-один принципиальное и потому не сведено к общей функции: там статус —
    ЛИЧНОЕ сообщение одному человеку, здесь его должны увидеть все, и увидеть СРАЗУ. Поэтому
    строка уходит в чат группы кодом (`running_late`), а не только полем в плане: человек,
    который смотрит в переписку, а не в план, иначе не узнал бы ничего.

    Ставится только на живой встрече — подтверждённой или уже запертой. Сказать «опаздываю» на
    план, который ещё согласовывают, значит заявить о договорённости, которой нет.
    """
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    st = str(status or "").strip().lower()
    if st not in GP_LIVE:
        return {"ok": False, "error": "BAD_STATUS", "allowed": list(GP_LIVE)}
    try:
        eta = int(eta_min) if eta_min not in (None, "") else None
    except (TypeError, ValueError):
        eta = None
    if eta is not None:
        eta = max(0, min(180, eta))
    now = time.time()
    with _STORE_LOCK:
        _gp_lock_due(now)
        p = _gp_find(pid)
        if not p:
            return {"ok": False, "error": "NO_SUCH_PLAN"}
        g = _gi_find(p.get("gid"))
        if not g:
            return {"ok": False, "error": "NO_SUCH_GROUP"}
        if _norm_name(who) not in {_norm_name(m.get("name")) for m in _gi_active(g)}:
            return _idem_put(idem, {"ok": False, "error": "NOT_A_PARTICIPANT"})
        if p.get("state") not in ("confirmed", "locked"):
            return _idem_put(idem, {"ok": False, "error": "NOT_CONFIRMED", "state": p.get("state")})
        p.setdefault("live", {})[_norm_name(who)] = {"status": st, "eta_min": eta, "t": now}
        p["updated"] = now
        if st == "late":
            _gi_say(g, "%s is running late." % who, code="running_late", who=who, eta=eta)
        elif st == "here":
            _gi_say(g, "%s is there." % who, code="arrived", who=who)
        elif st == "cant_make_it":
            _gi_say(g, "%s can\'t make it. The meetup stays on for everyone else.",
                    code="cant_make_it", who=who)
        _save_store()
        return _idem_put(idem, {"ok": True, "plan": _gp_public(p, who)})


def gp_feedback(pid, who, happened=None, reason="", text="", rating=None, idem=None):
    """After the meeting: did it happen, and how was it. «Когда человек отправляет, этот план у нас
    переносится в историю планов.» The plan moves to history for THAT person as soon as they answer;
    it is marked done for everyone once every confirmed participant has."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    now = time.time()
    with _STORE_LOCK:
        p = _gp_find(pid)
        if not p:
            return {"ok": False, "error": "NO_SUCH_PLAN"}
        if p.get("state") not in ("locked", "confirmed", "done"):
            return _idem_put(idem, {"ok": False, "error": "NOT_YET"})
        times = _gp_feedback_times(p)
        if not times["due"] or now < times["due"]:
            return _idem_put(idem, {"ok": False, "error": "NOT_YET"})
        if now >= times["expires"]:
            return _idem_put(idem, {"ok": False, "error": "EXPIRED"})
        members = _gp_feedback_members(p)
        canonical = next((n for n in members if _norm_name(n) == _norm_name(who)), None)
        if not canonical:
            return {"ok": False, "error": "NOT_A_PARTICIPANT"}
        p.setdefault("feedback_members", list(members))
        fb = p.setdefault("feedback", {})
        current = dict(fb.get(canonical) or {})
        if happened is not None:
            current["happened"] = bool(happened)
        if reason:
            current["reason"] = str(reason)[:400]
        if text:
            current["text"] = str(text)[:1000]
        if rating not in (None, ""):
            try:
                current["rating"] = max(1, min(5, int(rating)))
            except (TypeError, ValueError):
                return _idem_put(idem, {"ok": False, "error": "BAD_RATING"})
        if current.get("happened") is None:
            return _idem_put(idem, {"ok": False, "error": "ANSWER_REQUIRED"})
        current["t"] = now
        fb[canonical] = current
        answered = sum(1 for n in members if (_gp_feedback_record(p, n) or {}).get("happened") is not None)
        if answered >= len(members):
            p["state"] = "done"
        p["updated"] = now
        _save_store()
        return _idem_put(idem, {"ok": True, "plan": _gp_public(p, who),
                                "answered": answered, "of": len(members)})


def gp_for(who):
    """This person's plans — active and history — plus any vote waiting on them."""
    _gp_lock_due()
    _gp_postcall_due()
    me = _norm_name(who)
    active, history, votes = [], [], []
    for p in _gplans():
        g = _gi_find(p.get("gid"))
        if not g:
            continue
        inside = any(_norm_name(m.get("name")) == me for m in _gi_active(g)) or \
            any(_norm_name(n) == me for n in _gp_confirms(p))
        if not inside:
            continue
        view = _gp_public(p, who)
        view["title"] = g.get("title")
        mine = _gp_feedback_record(p, who)
        personal_done = bool(mine and mine.get("happened") is not None)
        (history if p.get("state") in ("done", "cancelled") or personal_done else active).append(view)
    _gp_votes_due()
    for v in _gvotes():
        # Закрытое, но НЕ решённое голосование — это и есть экран GR.37/38: организатору «It’s your
        # call», остальным «жду решения». Пока сюда попадали только открытые, обе стороны узнавали
        # исход ниоткуда: голосование просто исчезало.
        # Решённое — ещё сутки: участник должен увидеть исход (GR.38 «Mateo kept the plan as it
        # is» и лист GR.38a), а не заметить, что голосование молча пропало.
        if v.get("state") not in ("open", "closed"):
            continue
        if v.get("decided") and time.time() - float(v.get("decided_at") or 0) > 24 * 3600:
            continue
        g = _gi_find(v.get("gid"))
        if g and any(_norm_name(m.get("name")) == me for m in _gi_active(g)):
            votes.append(_gp_vote_view(v, who)["vote"])
    return {"ok": True, "plans": active, "history": history, "votes": votes}


# ============================================================================ 1:1 meeting plans (борд «1:1 Offline»)
# The group side has had a real plan object for a while — propose, confirm, counter, lock, feedback.
# The 1:1 side had NOTHING. The whole meeting lived in a client-side `PLAN` variable, which is why the
# app could say «Марта получит уведомление» and «статус видит только твой собеседник» while nothing at
# all left the device: the other account had no plan, no time, no address and no idea anyone was late.
#
# The board sets the rules. From OF.C3, verbatim: «Confirm and the exact address opens for you. Until
# then you only see the district — that works both ways.» So the address is a per-VIEWER field released
# by that viewer's own confirmation — not by the plan's overall state, and not by being the host.
# OF.22 иду / OF.22a опаздываю / OF.23 я на месте / «не смогу» внутри заморозки — тоже живой
# статус, а не отмена: встреча остаётся, второй просто знает, что его не ждут (см. mp_respond).
MP_LIVE = ("otw", "late", "here", "cant_make_it")

# ВЫБОР СТОРОНЫ У ГИБРИДА (HY.22 / HY.22a / HY.22b / HY.C4).
#
# У гибрида два входа, и каждый идёт своим: один за столик, другой в звонок. Это НЕ отмена
# (HY.23b говорит это прямым текстом: «this is not switching sides — it ends the meetup») и не
# статус «опаздываю»: встреча продолжается, человек просто на другой её стороне.
#
# Почему отдельное поле, а не значение в `live`. `live` — про путь к ОДНОЙ точке: «иду»,
# «опаздываю», «на месте». Сторона живёт дольше и значит другое: её выбирают заранее, её видит
# второй, и она переключается туда и обратно сколько угодно. Смешать их значило бы, что «я на
# месте» стирает выбор стороны, а «ухожу в звонок» стирает «опаздываю на 10 минут».
MP_SIDES = ("in_person", "call")
# HY.25. «И так и так» — не отговорка: у гибрида это обычный исход, когда один пришёл, второй
# подключился, а потом поменялись местами.
MP_HOW = ("in_person", "call", "both")


def mp_side(pid, who, side, idem=None):
    """HY.22: сказать, с какой стороны придёшь. Обратимо — «Go in person after all» на кадре 22a."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    st = str(side or "").strip().lower()
    if st not in MP_SIDES:
        return {"ok": False, "error": "BAD_SIDE", "allowed": list(MP_SIDES)}
    with _STORE_LOCK:
        p = _mp_find(pid)
        if not p:
            return {"ok": False, "error": "NO_SUCH_PLAN"}
        if not _mp_is_in(p, who):
            return {"ok": False, "error": "NOT_A_PARTICIPANT"}
        # Только у гибрида и только на сторону, у которой есть вход (ссылка или место) — mplan_rules.
        no = _mp_refusal(p, who, "side_" + st)
        if no:
            return _idem_put(idem, no)
        was = (p.get("sides") or {}).get(_norm_name(who))
        p.setdefault("sides", {})[_norm_name(who)] = {"side": st, "t": time.time()}
        p["updated"] = time.time()
        # Второму говорят СРАЗУ и в ленту, а не только полем в плане: смысл кадра HY.22b целиком
        # в том, что «она сказала заранее, и ты не сидишь за столиком один».
        if was is None or was.get("side") != st:
            _sys_msg(who, _mp_other(p, who), "plan_side", side=st)
        _save_store()
        return _idem_put(idem, {"ok": True, "plan": _mp_public(p, who)})


def _looks_like_url(s):
    s = str(s or "").strip().lower()
    return s.startswith(("http://", "https://")) or "://" in s or s.startswith("www.")


def _mp_link(p):
    """Ссылка встречи — отдельно от места.

    Раньше и то и другое лежало в ОДНОМ поле `address`: у звонка там была ссылка, у встречи вживую —
    адрес, а у ГИБРИДА — что положили первым, то есть второе терялось молча. Борд «1:1 Hybrid» на
    кадрах HY.20a/20b/20c требует обратного: у гибрида два входа, и каждый заполняется сам по себе,
    потому что без ссылки не войдёт половина, а без места второй половине некуда идти.

    Старые планы не переписываются, а ЧИТАЮТСЯ: у звонка `address` и есть ссылка; у гибрида,
    созданного до этой правки, там лежит ссылка, если она похожа на ссылку, и место иначе — другого
    признака в тех записях просто нет.
    """
    if p.get("link"):
        return p["link"]
    mode, addr = p.get("mode"), p.get("address") or ""
    if mode == "online":
        return addr
    if mode == "hybrid" and _looks_like_url(addr):
        return addr
    return ""


def _mp_place(p):
    """Место встречи — та же развязка с другой стороны."""
    if p.get("place"):
        return p["place"]
    mode, addr = p.get("mode"), p.get("address") or ""
    if mode == "online":
        return ""
    if mode == "hybrid" and _looks_like_url(addr):
        return ""
    return addr

MP_MODES = ("offline", "online", "hybrid")
MP_MAX_AHEAD = 365 * 24 * 3600           # a first coffee is not scheduled for the year 31 billion
MP_KEEP_AFTER = 24 * 3600                # a plan stays "active" for a day past its start, then history
# РАУНДЫ И СРОК ОТВЕТА — борд «1:1 · Offline — new layout», разделы B/C (OF.20–20c, OF.21a–c, C3–C5),
# 06.10.2026. До подтверждения каждое встречное время — раунд, их не больше трёх; на ответ — 6 ч и
# до, и после подтверждения («Round 1 / 3 · Ends in 6h», «Accepted 0 of 1 · Ends in 6h»).
MP_MAX_ROUNDS = 3
MP_ROUND_TTL = 6 * 3600
# O.23c «Nobody joined the call»: ссылка открыта 15 минут от начала. Это ПОМЕТКА для экрана, а не
# исход: состоялась ли встреча, по-прежнему решают ответы двоих (решение владельца 11.10.2026).
MP_JOIN_WINDOW = 15 * 60


def _mplans():
    return SESSION.setdefault("_mplans", [])


def _mp_find(pid):
    for p in _mplans():
        if p.get("id") == pid:
            return p
    return None


def _mp_of(a, b):
    """The plan in force between two people — one at a time, like the single open proposal per pair.

    ДЕЙСТВУЮЩИЙ — ЗНАЧИТ ЕЩЁ НЕ ПРОШЕДШИЙ. Состояния было мало: `done` ставится только когда об
    исходе ответили ОБЕ стороны, и пара, где второй просто не открыл приложение, оставалась
    запертой навсегда — новый план не создать, потому что «уже есть действующий». Встреча
    состоялась неделю назад, а `confirmed` держит пару мёртвой хваткой.

    Горизонт — MP_KEEP_AFTER, тот же, по которому `mp_for` разделяет живое и историю. За ним план
    перестаёт быть действующим, даже если об исходе не сказал никто: спрашивать об исходе можно и
    дальше (`mp_feedback` принимает и `done`), а вот запрещать людям встречаться — уже нет.
    """
    key, now = _pair_key(a, b), time.time()
    for p in _mplans():
        if p.get("pair") != key or p.get("state") not in ("proposed", "confirmed"):
            continue
        try:
            starts = float(p.get("starts_at") or 0)
        except (TypeError, ValueError):
            starts = 0
        if starts and now >= starts + MP_KEEP_AFTER:
            continue                       # встреча давно прошла — держать пару больше не за что
        return p
    return None


def person_card(me, other):
    """Карточка человека для того, с кем он УЖЕ согласился встретиться.

    ЗАМОК ТОТ ЖЕ, ЧТО У СООБЩЕНИЙ И ПЛАНОВ — `_mp_matched`. Одна функция на все три двери, чтобы
    правило не разошлось само с собой: имя человека видно в выдаче, и ручка без проверки отдавала
    бы профиль кого угодно по одному запросу.

    НИЧЕГО НОВОГО НЕ РАСКРЫВАЕМ. Отдаём ровно те поля, которые собеседник уже видел карточкой в
    выдаче, когда решал, звать или нет: имя, фото, возраст, район, интересы, языки, настрой,
    подтверждённость. Точных координат здесь нет и быть не может — их нет и в выдаче.

    Отдельно про `km`: он НЕ отдаётся. Расстояние в выдаче считается от того, кто искал, и здесь
    было бы числом из чужой системы координат — либо враньём, либо утечкой точности.
    """
    me, other = str(me or "").strip(), str(other or "").strip()
    if not me or not other:
        return {"ok": False, "error": "TWO_PEOPLE_REQUIRED"}
    if _blocked_pair(me, other):
        return {"ok": False, "error": "BLOCKED"}
    if not _mp_matched(me, other):
        return {"ok": False, "error": "NOT_MATCHED"}
    row = _person(other)                     # по id: карточка тёзки — это другой человек
    if row is None:
        return {"ok": False, "error": "not found"}
    card = {k: row.get(k) for k in ("id", "name", "photo", "age", "area", "interests", "langs",
                                    "vibe", "verified", "formats", "role", "open", "summary")
            if row.get(k) is not None}
    return {"ok": True, "person": card}


def _mp_matched(a, b):
    """A plan may only go to someone who ACCEPTED an invitation. Without this gate the exact address of
    a first date is one POST away from any name in the pool."""
    pair = {_norm_name(a), _norm_name(b)}
    for r in _requests():
        if r.get("status") == "accepted" and {_norm_name(r.get("from")), _norm_name(r.get("to"))} == pair:
            return True
    return False


def _mp_is_in(p, who):
    return _norm_name(who) in (_norm_name(p.get("host")), _norm_name(p.get("guest")))


def _mp_answer(p, who):
    """This person's answer to the CURRENT version. An answer to an older version is not an answer:
    a counter-proposal bumps the version precisely so an old yes stops counting — they agreed to a
    different evening."""
    r = (p.get("responses") or {}).get(_norm_name(who)) or {}
    return r.get("state") if int(r.get("version") or 0) == int(p.get("version") or 1) else None


def _mp_confirmed(p):
    """Normalised names of everyone who has confirmed this version."""
    return [n for n in ((p.get("responses") or {}).keys())
            if _mp_answer(p, n) == "confirmed"]


def _mp_other(p, who):
    return p.get("guest") if _norm_name(who) == _norm_name(p.get("host")) else p.get("host")


def _mp_facts(p, who, now=None):
    """Факты о плане для правил (`mplan_rules`) — одна сборка, чтобы ручки и проекция читали одно и то же."""
    pend = p.get("pending") or {}
    return {"state": p.get("state"), "frozen": _mp_frozen(p, now),
            "pending": bool(pend),
            "pending_mine": bool(pend) and _norm_name(pend.get("by")) == _norm_name(who),
            "mode": p.get("mode"), "link": bool(_mp_link(p)), "place": bool(_mp_place(p)),
            "my_answer": _mp_answer(p, who),
            "is_host": _norm_name(who) == _norm_name(p.get("host")),
            "round": int(p.get("round") or 1), "max_rounds": MP_MAX_ROUNDS,
            "final": _mp_final_open(p)}


def _mp_final_open(p):
    """Хозяин зафиксировал финальную версию (OF.20c), гость ещё не ответил «остаюсь / выхожу»."""
    f = p.get("final_by_host") or None
    return bool(f) and not f.get("answer") and p.get("state") == "proposed"


def _mp_round_entry(p, rnd, by, starts_at, when, district, now):
    return {"round": int(rnd), "by": by, "starts_at": starts_at, "when": str(when or "")[:120],
            "district": str(district or "")[:120], "at": now}


def _mp_sweep(now=None):
    """Время наступает на чтении: просроченное встречное время снимается само (OF.21c, C5a).

    «Marta не ответила за 6 ч — остаётся 20:00»: висящее предложение уходит, план остаётся ровно
    каким был, в переписке пары — строка об этом. Зовётся из каждой ручки, отдающей или меняющей
    план (как _gp_sweep у группы), иначе экран показал бы перенос, на который уже нельзя ответить.
    Предложения без срока (до 06.10.2026) не трогаем — им срок никто не обещал."""
    now = now or time.time()
    changed = False
    for p in _mplans():
        # МОЛЧАНИЕ ДО ПОДТВЕРЖДЕНИЯ (решение владельца 06.10.2026): на каждый ход 6 ч; кто молчит —
        # план закрывается «не ответил(а)» БЕЗ последствий. Из молчания нельзя получить встречу, на
        # которую второй ни разу не сказал «да». Срок ставят propose/counter/fix; у планов до
        # 06.10.2026 его нет — их время не закрывает.
        try:
            due = float(p.get("round_ends_at") or 0)
        except (TypeError, ValueError):
            due = 0
        if p.get("state") == "proposed" and due and now >= due:
            pend = p.get("pending") or {}
            # Чей был ход: висит встречное — отвечает не его автор; нет — гость (хозяин уже «за»).
            silent = (_mp_other(p, pend.get("by")) if pend.get("by") else p.get("guest"))
            was_final = _mp_final_open(p)           # считать ДО смены состояния: проверка смотрит на proposed
            p["state"] = "cancelled"
            p["cancelled_by"] = ""
            p["cancel_kind"] = "expired_no_answer"
            p["expired_silent"] = silent
            p["pending"] = None
            p["round_ends_at"] = None
            if was_final:
                p["final_by_host"] = dict(p["final_by_host"], answer="timeout", answered_at=now)
            p["updated"] = now
            _sys_msg(silent, _mp_other(p, silent), "plan_expired", at=p.get("starts_at"), by=silent)
            changed = True
            continue
        pend = p.get("pending") or None
        if not pend or p.get("state") not in ("proposed", "confirmed"):
            continue
        try:
            exp = float(pend.get("expires_at") or 0)
        except (TypeError, ValueError):
            exp = 0
        if not exp or now < exp:
            continue
        p["pending"] = None
        p["last_change"] = {"state": "expired", "by": pend.get("by"), "at": now}
        p["updated"] = now
        _sys_msg(pend.get("by"), _mp_other(p, pend.get("by")), "plan_change_expired",
                 at=p.get("starts_at"), was=pend.get("starts_at"))
        changed = True
    if changed:
        _save_store()
    return changed


def _mp_refusal(p, who, action, now=None):
    """Готовый отказ ручки по таблице правил, или None — действие возможно."""
    return mpr.refusal(action, _mp_facts(p, who, now))


def _mp_public(p, me=""):
    if not p:
        return None
    who = _norm_name(me)
    conf = set(_mp_confirmed(p))
    people = []
    for nm, role in ((p.get("host"), "host"), (p.get("guest"), "guest")):
        k = _norm_name(nm)
        people.append({"name": nm, "role": role, "is_me": k == who, "photo": _photo_of(k),
                       # «Marta, 29» на кадрах B/C. Возраст пара и так видит в карточке человека
                       # (person_card — тот же замок «приглашение принято»), план без него не открыть.
                       "age": (_person(nm) or {}).get("age"),
                       # Пол — только двоим участникам плана, чтобы тексты писали «он/она», а не «they»
                       # (решение владельца 11.10.2026). В выдаче и карточке человека его по-прежнему нет.
                       "gender": (_person(nm) or {}).get("gender") or "",
                       "status": _mp_answer(p, nm) or "pending", "confirmed": k in conf,
                       # Пояс участника — чтобы экран мог показать чужое местное время, и только
                       # когда оно отличается от своего.
                       "tz": _tz_of(k),
                       # HY.22a/22b: с какой стороны человек придёт. Второму это видно — в том и
                       # смысл: «она сказала заранее, и ты не сидишь за столиком один».
                       "side": ((p.get("sides") or {}).get(k) or {}).get("side"),
                       "live": (p.get("live") or {}).get(k),
                       # Вошёл в звонок / пришёл: клиент шлёт статус `here` по «Open link» (O.23).
                       "joined": ((p.get("live") or {}).get(k) or {}).get("status") == "here"})
    # OF.C3: released by the viewer's OWN confirmation — plus, always, to whoever typed it. Without
    # that second half a counter-proposal (which resets every confirmation) would hide the address
    # from the very person who wrote it, which is not privacy, just a broken screen.
    opened = who in conf or who == _norm_name(p.get("address_by"))
    return {
        "id": p.get("id"), "version": p.get("version"), "state": p.get("state"),
        "title": p.get("title"), "mode": p.get("mode"),
        "starts_at": p.get("starts_at"), "when": p.get("when"),
        "district": p.get("district"), "venue": p.get("venue"),
        # OF.21b: a proposed change sits BESIDE the plan, it does not replace it. Both sides need to
        # see the old hour and the suggested one at once, or «nothing is cancelled» is a lie.
        "pending": (dict(p["pending"], mine=(_norm_name(p["pending"].get("by")) == who))
                    if p.get("pending") else None),
        "address": (p.get("address") or "") if opened else "",
        "address_set": bool(p.get("address")),
        "address_visible_to_me": bool(opened and p.get("address")),
        # ДВА ВХОДА ОТДЕЛЬНЫМИ ПОЛЯМИ. Экран гибрида не мог показать ни места, ни ссылки: строка
        # места стояла на «режим == offline», строка ссылки — на «режим == online», а гибрид не
        # тот и не другой. Теперь наружу идут оба, и каждый со своим признаком «задан ли» —
        # на этом различии держатся кадры HY.20a («место есть, ссылки нет»), HY.20b (наоборот)
        # и HY.20c (нет ни того, ни другого).
        #
        # Правило открытия у обоих одно и то же (OF.C3): их видит подтвердивший и тот, кто их
        # написал. Ссылка не безобиднее адреса — по ней входят в разговор.
        "place": (_mp_place(p) if opened else ""),
        "place_set": bool(_mp_place(p)),
        # ПЕРЕДАЧА ВЫБОРА — ФАКТ ПЛАНА, А НЕ ПАМЯТЬ ЭКРАНА. «Пусть выберет он(а)» жило локальным
        # флагом в приложении: сбрасывалось при повторном открытии, второму не показывалось вовсе,
        # и оба могли просить друг друга по кругу. Теперь просьба лежит в плане, оба её видят, и
        # она снимается сама, когда просимое названо (см. mp_address).
        "place_asked_by": ((p.get("asks") or {}).get("place") or {}).get("by") or "",
        "link_asked_by": ((p.get("asks") or {}).get("link") or {}).get("by") or "",
        "link": (_mp_link(p) if opened else ""),
        "link_set": bool(_mp_link(p)),
        # Чья ссылка и чьё место: после «Host the call myself» экран подписывал ссылку организатору
        # («Mateo's link»), хотя её дал гость. Сам вход по-прежнему открыт только подтвердившим.
        "link_by": p.get("link_by") or "", "address_by": p.get("address_by") or "",
        "note": p.get("note"), "cover": p.get("cover"),
        "host": p.get("host"), "guest": p.get("guest"), "other": _mp_other(p, me),
        "participants": people,
        "confirmed_count": len(conf), "both_confirmed": len(conf) >= 2,
        "my_response": _mp_answer(p, me),
        "waiting_on": [x["name"] for x in people if not x["confirmed"]],
        # ЗАМОК ВИДЕН ЭКРАНУ. За два часа до начала сервер перестаёт принимать встречное время,
        # ответ на него и правку ссылки — а экран продолжал рисовать все эти кнопки и получал на
        # нажатие безымянную ошибку. Ровно в тот момент, когда для человека важнее всего понять,
        # что происходит. Признак отдаём фактом, чтобы экран не считал время сам и не разошёлся
        # с сервером на минуту.
        "locked": _mp_frozen(p),
        # Что этому участнику можно предложить прямо сейчас — по той же таблице, по которой ручки
        # отказывают. Экран рисует кнопки по этому списку, а не выводит правила заново.
        "actions": mpr.offered(_mp_facts(p, me)),
        "locks_at": (float(p["starts_at"]) - MP_LOCK_BEFORE) if p.get("starts_at") else None,
        # Сторона парой my/their — как live и tz: экрану нужен один ключ, а не перебор участников.
        "my_side": ((p.get("sides") or {}).get(who) or {}).get("side"),
        "their_side": ((p.get("sides") or {}).get(_norm_name(_mp_other(p, me))) or {}).get("side"),
        "my_live": (p.get("live") or {}).get(who),
        "their_live": (p.get("live") or {}).get(_norm_name(_mp_other(p, me))),
        # Пояс собеседника рядом с their_live по той же причине: экрану нужен ОДИН ключ, а не
        # перебор participants ради поля, которое смотрят в каждой строке времени.
        "their_tz": _tz_of(_mp_other(p, me)),
        # OF.23a разводит «You told X you can't make it» и «X can't make it» — без имени отменившего
        # экран не знает, какую из двух правд показывать.
        "cancelled_by": p.get("cancelled_by"),
        # ИСХОД БЕЗ ЧУЖОЙ ПРИЧИНЫ. В самом плане `outcome.reason` — это причина ТОГО, кто ответил
        # «не состоялась»: «Иван не пришёл», «не смог(ла) я». Экран обещает прямым текстом
        # «Твой ответ другим не показывается», а наружу эта строка уезжала обоим. Наружу идёт
        # только сам факт; причину видит тот, кто её написал, — в своём `my_feedback`.
        "outcome": ({k: v for k, v in (p.get("outcome") or {}).items() if k != "reason"}
                    if p.get("outcome") else None),
        "my_feedback": (p.get("feedback") or {}).get(who),
        # HY.23c: экран должен отличать «оба ушли в звонок, потому что место закрыто» от обычной
        # смены стороны — иначе кнопка «уходим в звонок» так и стоит после того, как ушли.
        "moved_to_call": bool(p.get("moved_to_call")),
        # OF.24 говорит «пока не ответите оба, никому ничего не засчитывается» — значит экрану нужно
        # знать сам ФАКТ ответа второго, но не его содержание. Пара their_*/my_* здесь та же, что у
        # live: наружу уходит булево, чужая оценка и причина остаются внутри.
        "their_feedback": bool((p.get("feedback") or {}).get(_norm_name(_mp_other(p, me)))),
        "due": bool(p.get("starts_at") and time.time() >= float(p["starts_at"])),
        # «Reply by Sun 20:00» (O.24 / O.C10 / OF.24): до какого момента план спрашивает об исходе —
        # сутки от начала, тот же горизонт, за которым он уходит в историю. Срок только показывается:
        # по его истечении ничего не засчитывается само.
        "feedback_expires_at": (float(p["starts_at"]) + MP_KEEP_AFTER) if p.get("starts_at") else None,
        # O.23c: звонок, в который за 15 минут не вошёл никто. Только у встречи-звонка и только
        # у подтверждённой; пометка, а не состояние.
        "join_closes_at": ((float(p["starts_at"]) + MP_JOIN_WINDOW)
                           if p.get("starts_at") and (p.get("mode") == "online" or p.get("moved_to_call")) else None),
        "nobody_joined": bool(p.get("state") == "confirmed" and p.get("starts_at")
                              and (p.get("mode") == "online" or p.get("moved_to_call"))
                              and time.time() >= float(p["starts_at"]) + MP_JOIN_WINDOW
                              and not any(x.get("joined") for x in people)),
        # РАУНДЫ (OF.20–20c, C3–C3d). round — номер текущей версии до подтверждения (1 — исходный
        # план), round_ends_at — срок ответа на висящее встречное время. Журнал раундов — для листа
        # «Fix the plan»: хозяин выбирает финальную версию из всех.
        "round": int(p.get("round") or 1), "max_rounds": MP_MAX_ROUNDS,
        # До подтверждения — срок текущего хода (молчание закрывает план); после — срок переноса.
        "round_ends_at": (p.get("round_ends_at") if p.get("state") == "proposed"
                          else ((p.get("pending") or {}).get("expires_at") if p.get("pending") else None)),
        "rounds_log": list(p.get("rounds_log") or []),
        "can_fix": (p.get("state") == "proposed" and who == _norm_name(p.get("host"))
                    and int(p.get("round") or 1) >= MP_MAX_ROUNDS and not _mp_frozen(p)
                    and not _mp_final_open(p)),
        # Кто промолчал, если план закрыло время (cancel_kind = expired_no_answer).
        # Ключа нет в _PERSON_KEYS, поэтому подпись и id — явно: иначе экран получил бы голый id.
        "expired_silent": (_display(p["expired_silent"], str(p["expired_silent"]))
                           if p.get("expired_silent") else ""),
        "expired_silent_id": _canon_pid(p.get("expired_silent")) if p.get("expired_silent") else "",
        # Гость должен решить «остаться / выйти» по зафиксированному плану; сам факт фиксации —
        # в fixed (раунд и время), он остаётся и после ответа.
        "final_by_host": _mp_final_open(p),
        "fixed": p.get("final_by_host") or None,
        # «Вышел из зафиксированного плана» — без последствий (OF.C3d), отличать от отмены.
        "cancel_kind": p.get("cancel_kind") or "",
        "created": p.get("created"), "updated": p.get("updated"),
    }


def mp_propose(frm, to, title="", mode="offline", starts_at=None, when="", district="",
               address="", note="", cover="", venue="", idem=None, link=""):
    """OF.20 — one side sends the meeting: when, which district, and (optionally) the exact address."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    frm, to = str(frm or "").strip(), str(to or "").strip()
    if not frm or not to or _norm_name(frm) == _norm_name(to):
        return {"ok": False, "error": "TWO_PEOPLE_REQUIRED"}
    if _blocked_pair(frm, to):
        return {"ok": False, "error": "BLOCKED"}
    if not _mp_matched(frm, to):
        return {"ok": False, "error": "NOT_MATCHED",
                "note": "a plan can only go to someone who accepted an invitation"}
    now = time.time()
    try:
        sa = float(starts_at) if starts_at else None
    except (TypeError, ValueError):
        sa = None
    if sa is not None and sa <= now:
        return _idem_put(idem, {"ok": False, "error": "IN_THE_PAST"})
    if sa is not None and sa > now + MP_MAX_AHEAD:
        return _idem_put(idem, {"ok": False, "error": "TOO_FAR_AHEAD"})
    md = str(mode or "offline").strip().lower()
    with _STORE_LOCK:
        if _mp_of(frm, to):
            return _idem_put(idem, {"ok": False, "error": "PLAN_EXISTS"})
        base = "mp_%d_%s" % (int(now * 1000),
                             hashlib.sha1(_pair_key(frm, to).encode("utf-8")).hexdigest()[:6])
        taken = {x.get("id") for x in _mplans()}
        pid, n = base, 1
        while pid in taken:
            pid, n = "%s_%d" % (base, n), n + 1
        p = {"id": pid, "pair": _pair_key(frm, to), "host": frm, "guest": to,
             "title": str(title or "")[:120], "mode": md if md in MP_MODES else "offline",
             "starts_at": sa, "when": str(when or "")[:120],
             "district": str(district or "")[:120], "address": str(address or "")[:200],
             "venue": str(venue or "")[:120], "address_by": frm if address else "",
             # ДВА ВХОДА У ГИБРИДА. Раньше место и ссылка делили одно поле, и у гибрида второе
             # молча пропадало: экран отправлял `address = link or place`. Теперь ссылка своя.
             # У звонка и встречи вживую ничего не меняется — там как был один вход, так и есть.
             "link": str(link or "")[:400], "link_by": frm if link else "",
             "pending": None,
             "note": str(note or "")[:400], "cover": str(cover or "")[:400],
             "state": "proposed", "version": 1,
             "round": 1, "rounds_log": [_mp_round_entry(None, 1, frm, sa, when, district, now)],
             "round_ends_at": now + MP_ROUND_TTL,
             # Proposing IS confirming. Asking the sender to agree with themselves would be theatre.
             "responses": {_norm_name(frm): {"state": "confirmed", "t": now, "version": 1}},
             "live": {}, "feedback": {}, "created": now, "updated": now}
        _mplans().append(p)
        _sys_msg(frm, to, "plan_proposed", at=sa, mode=p["mode"], district=p["district"])
        # МЕСТО, ВПИСАННОЕ ПРЯМО В ФОРМУ, ТОЖЕ СОБЫТИЕ. Названное минутой позже через mp_address
        # оно даёт `plan_place` и доходит до переписки, а названное сразу — не давало ничего:
        # второй читал «план предложен» и не знал, что адрес уже есть. Владелец назвал это среди
        # пропавших: «указываю новое время, дату, место».
        if p["link"]:
            _sys_msg(frm, to, "plan_place", kind="link")
        if p["address"] or p["venue"]:
            _sys_msg(frm, to, "plan_place", kind="place", district=p["district"])
        _save_store()
        return _idem_put(idem, {"ok": True, "plan": _mp_public(p, frm)})


# ЗАМОРОЗКА ЗА ДВА ЧАСА — та же, что у группы, и по той же спеке.
#
# «Заморозка перед встречей · T − 2 h. Отключены правки, отмена, голосования и приглашения.
# Остаётся только „I can't make it" — оно встречу не отменяет. Заморозка сильнее любого другого
# таймера» (board_spec_sroki.txt, чип Decided).
#
# У группы это жило с самого начала (GP_LOCK_BEFORE), у пары — не жило вовсе: перенести, отменить
# и переписать место можно было за пять минут до встречи и даже ПОСЛЕ её начала. Второй человек
# при этом уже вышел из дома.
MP_LOCK_BEFORE = GP_LOCK_BEFORE


def _mp_frozen(p, now=None):
    """Заморозка правок — ОКНО вокруг встречи, а не полупрямая от T−2ч в бесконечность.

    Верхней границы не было, и план месячной давности считался замороженным навсегда. Из-за этого
    `mp_cancel` у любого прошедшего плана отвечал LOCKED — единственная ручка со словом «отменить»
    не работала вообще. Заморозка защищает человека, который уже вышел из дома; через сутки после
    начала защищать нечего, а запертая запись мешает паре жить дальше.

    Верх — MP_KEEP_AFTER, тот же горизонт, по которому `mp_for` разделяет живое и историю: за
    границей окна план для всех уже история, и правила живого плана к нему не применяются.
    """
    try:
        starts = float(p.get("starts_at") or 0)
    except (TypeError, ValueError):
        return False
    if not starts:
        return False
    t = now or time.time()
    return starts - MP_LOCK_BEFORE <= t < starts + MP_KEEP_AFTER


def mp_respond(pid, who, action, starts_at=None, when="", district="",
               title="", note="", version=None, idem=None, round_no=None):
    """confirm | decline | counter | accept_change | reject_change.

    A COUNTER here is NOT what a counter is on the group side. The group rule tears the plan up and
    restarts confirmation; the 1:1 board says the opposite, three times over:

      OF.21a  «Marta confirms again after this. The current time stays until she does — nothing is cancelled.»
      OF.21b  «Until then the old time still stands — nothing is cancelled and nobody has to do anything.»
      OF.C5   «The old time holds until you answer, so there is no rush and nothing is lost if you say no.»

    So a counter parks a PENDING CHANGE beside a plan that keeps running. Accepting it applies it;
    rejecting it drops the change and leaves the meeting exactly as it was. Nobody is ever left with a
    cancelled evening because the other person floated a different hour."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    act = str(action or "").strip().lower()
    if act not in ("confirm", "decline", "counter", "accept_change", "reject_change",
                   "fix", "stay", "leave"):
        return {"ok": False, "error": "BAD_ACTION"}
    now = time.time()
    with _STORE_LOCK:
        _mp_sweep(now)
        p = _mp_find(pid)
        if not p:
            return {"ok": False, "error": "NO_SUCH_PLAN"}
        if not _mp_is_in(p, who):
            return {"ok": False, "error": "NOT_A_PARTICIPANT"}
        # Открыт ли план, не заморозка ли, не висит ли встречное время — всё по одной таблице
        # (mplan_rules). Отказ уносит с собой проекцию: телефон опрашивает сервер раз в 15 секунд
        # и о чужом переносе внутри этого окна иначе не узнал бы.
        #
        # ПОРЯДОК ТОТ ЖЕ, ЧТО БЫЛ: закрытый план → устаревшая версия → заморозка и условия.
        # Версия обязана опережать LOCKED и PENDING_CHANGE: только на VERSION_CONFLICT экран
        # перечитывает план и говорит «за это время всё изменилось» (plan.tsx), а на прочие коды
        # показывает общее «не удалось». Ответ на позавчерашнюю версию — это именно «перечитай».
        no = _mp_refusal(p, who, act, now)
        if no and no.get("error") == "NOT_OPEN":
            return _idem_put(idem, dict(no, plan=_mp_public(p, who)))
        if version is not None and str(version) != str(p.get("version") or 1):
            return {"ok": False, "error": "VERSION_CONFLICT", "version": p.get("version")}
        if no:
            # YOUR_OWN_CHANGE и раньше НЕ клался в кэш идемпотентности: это отказ «не тому
            # человеку», а не результат действия, и повтор с тем же ключом должен считаться заново.
            if no.get("error") == "YOUR_OWN_CHANGE":
                return dict(no, plan=_mp_public(p, who))
            return _idem_put(idem, dict(no, plan=_mp_public(p, who)))
        k = _norm_name(who)
        v = int(p.get("version") or 1)
        pend = p.get("pending") or None
        peer = _mp_other(p, who)
        # В заморозке живут только ответы, а не правки: подтвердить можно, «не смогу» — можно,
        # переносить время и принимать чужой перенос — нельзя. Спека: «Отключены правки, отмена,
        # голосования и приглашения. Остаётся только „I can't make it" — оно встречу не отменяет».
        if act in ("confirm", "stay") and _mp_final_open(p):
            p["final_by_host"] = dict(p["final_by_host"], answer="stay", answered_at=now)
            act = "confirm"
        if act == "leave":
            # OF.C3d «Leave the plan»: выход из зафиксированного хозяином плана — без последствий.
            # Это не отмена встречи кем-то из двоих, а честный выход после трёх несошедшихся раундов.
            p["final_by_host"] = dict(p["final_by_host"], answer="leave", answered_at=now)
            p["state"] = "cancelled"
            p["cancelled_by"] = who
            p["cancel_kind"] = "left_final"
            p.setdefault("responses", {})[k] = {"state": "declined", "t": now, "version": v}
            _sys_msg(who, peer, "plan_left", at=p.get("starts_at"))
            p["updated"] = now
            _save_store()
            return _idem_put(idem, {"ok": True, "plan": _mp_public(p, who)})
        if act == "fix":
            try:
                rn = int(round_no)
            except (TypeError, ValueError):
                return _idem_put(idem, {"ok": False, "error": "NO_ROUND"})
            entry = next((e for e in (p.get("rounds_log") or []) if int(e.get("round") or 0) == rn), None)
            if not entry:
                return _idem_put(idem, {"ok": False, "error": "NO_SUCH_ROUND"})
            try:
                sa = float(entry.get("starts_at")) if entry.get("starts_at") else None
            except (TypeError, ValueError):
                sa = None
            if sa is not None and sa <= now:
                return _idem_put(idem, {"ok": False, "error": "IN_THE_PAST"})
            p["starts_at"] = sa
            for f in ("when", "district"):
                if entry.get(f):
                    p[f] = entry[f]
            p["pending"] = None
            p["version"] = v + 1
            # Хозяин выбрал — значит, он согласен; гость отвечает «остаюсь / выхожу» (OF.C3d).
            p["responses"] = {k: {"state": "confirmed", "t": now, "version": p["version"]}}
            p["final_by_host"] = {"round": rn, "by": who, "starts_at": sa, "at": now}
            p["round_ends_at"] = now + MP_ROUND_TTL           # молчание гостя = вышел, без последствий
            p["live"] = {}
            _sys_msg(who, peer, "plan_fixed", at=sa, round=rn, mode=p.get("mode"))
            p["updated"] = now
            _save_store()
            return _idem_put(idem, {"ok": True, "plan": _mp_public(p, who)})
        if act == "decline" and _mp_frozen(p, now):
            # СПЕКА, СЛОВО В СЛОВО: «Остаётся только „I can't make it" — оно встречу не отменяет».
            # Комментарий выше это правило называл, а код строкой ниже ставил `cancelled` — то
            # есть за двадцать минут до встречи кнопка «Не смогу» необратимо рвала план, и второй,
            # уже вышедший из дома, узнавал об отмене вместо «задерживаюсь».
            #
            # Внутри заморозки это ЖИВОЙ СТАТУС рядом с живым планом, как «опаздываю» и «я на
            # месте»: встреча остаётся, второй видит честное «не придёт» и решает сам.
            p.setdefault("live", {})[k] = {"status": "cant_make_it", "eta_min": None, "t": now,
                                           "note": str(note or "")[:200]}
            p["updated"] = now
            _sys_msg(who, peer, "plan_cant_make_it", at=p.get("starts_at"))
            _save_store()
            return _idem_put(idem, {"ok": True, "plan": _mp_public(p, who), "cancelled": False})
        if act == "decline":
            p["state"] = "cancelled"
            p["cancelled_by"] = who
            p["cancel_reason"] = str(note or "")[:400]
            p.setdefault("responses", {})[k] = {"state": "declined", "t": now, "version": v}
            _sys_msg(who, peer, "plan_cancelled", at=p.get("starts_at"))
        elif act == "confirm":
            # Условие смотрит на ПЕРЕХОД, а не на итог. «Согласились оба» остаётся истиной и после
            # того, как согласились, — поэтому каждое следующее нажатие «Подтвердить» писало в
            # ленту ещё одну строку «План подтверждён». Комментарий ниже обещал «пишется один раз»
            # ещё до того, как это стало правдой; прогон 14.09.2026 дал три одинаковых строки на
            # три нажатия. С кнопкой прямо в ленте промахнуться пальцем стало только легче.
            _was_confirmed = p.get("state") == "confirmed"
            p.setdefault("responses", {})[k] = {"state": "confirmed", "t": now, "version": v}
            if len(_mp_confirmed(p)) >= 2:
                p["state"] = "confirmed"
                p["round_ends_at"] = None
                # ЭТА строка и есть «финальное сообщение, что план подтверждён». Пишется один раз,
                # в момент, когда согласились оба, — не на каждое нажатие «Подтвердить».
                if not _was_confirmed:
                    _sys_msg(who, peer, "plan_confirmed", at=p.get("starts_at"), mode=p.get("mode"))
        elif act == "counter":
            try:
                sa = float(starts_at) if starts_at else None
            except (TypeError, ValueError):
                sa = None
            if sa is None:
                return _idem_put(idem, {"ok": False, "error": "NO_NEW_TIME"})
            if sa <= now:
                return _idem_put(idem, {"ok": False, "error": "IN_THE_PAST"})
            if sa > now + MP_MAX_AHEAD:
                return _idem_put(idem, {"ok": False, "error": "TOO_FAR_AHEAD"})
            # The plan itself is untouched: same state, same starts_at, same confirmations.
            # Срок ответа — 6 ч (OF.21c, C3); по истечении предложение снимает _mp_sweep.
            p["pending"] = {"by": who, "starts_at": sa, "when": str(when or "")[:120],
                            "district": str(district or "")[:120], "title": str(title or "")[:120],
                            "note": str(note or "")[:400], "at": now,
                            "expires_at": now + MP_ROUND_TTL}
            rnd = None
            if p.get("state") == "proposed":
                # До подтверждения встречное — новый раунд (OF.20b). Журнал нужен листу «Fix the
                # plan»: у планов, созданных до раундов, первый раунд — нынешние условия хозяина.
                log = p.setdefault("rounds_log", [])
                if not log:
                    log.append(_mp_round_entry(p, 1, p.get("host"), p.get("starts_at"), p.get("when"),
                                               p.get("district"), p.get("created") or now))
                rnd = int(p.get("round") or 1) + 1
                p["round"] = rnd
                log.append(_mp_round_entry(p, rnd, who, sa, when or p.get("when"),
                                           district or p.get("district"), now))
                p["pending"]["round"] = rnd
                p["round_ends_at"] = p["pending"]["expires_at"]
            _sys_msg(who, peer, "plan_counter", at=sa, was=p.get("starts_at"), round=rnd)
        elif act in ("accept_change", "reject_change"):
            # Своё предложение принять нельзя (mplan_rules), а забрать — можно и нужно: иначе оно
            # висит у второго на экране, пока он не ответит на то, чего автор уже не имеет в виду.
            if act == "reject_change":
                p["pending"] = None
                p["last_change"] = {"state": "rejected", "by": who, "at": now}
                # Забрать своё предложение и отказать чужому — разные новости, и в ленте они разные:
                # иначе автор переноса читал бы, что ему отказали, отказав самому себе.
                _sys_msg(who, peer,
                         "plan_change_pulled" if _norm_name(pend.get("by")) == k else "plan_change_no",
                         at=p.get("starts_at"))
            else:
                p["starts_at"] = pend.get("starts_at")
                for f in ("when", "district", "title", "note"):
                    if pend.get(f):
                        p[f] = pend[f]
                p["pending"] = None
                p["version"] = v + 1
                # Both have now agreed to this hour: the proposer by proposing, this side by accepting.
                p["responses"] = {_norm_name(pend.get("by")): {"state": "confirmed", "t": pend.get("at"),
                                                              "version": p["version"]},
                                  k: {"state": "confirmed", "t": now, "version": p["version"]}}
                p["state"] = "confirmed"
                p["round_ends_at"] = None
                p["live"] = {}                    # nobody is on their way to the old hour any more
                p["last_change"] = {"state": "accepted", "by": who, "at": now}
                _sys_msg(who, peer, "plan_change_ok", at=p.get("starts_at"), mode=p.get("mode"))
        p["updated"] = now
        _save_store()
        return _idem_put(idem, {"ok": True, "plan": _mp_public(p, who)})


def mp_address(pid, who, address="", venue="", idem=None, link=""):
    """OF.20a «Pick the exact place» — naming the venue for a time both sides already agreed to.

    This deliberately does NOT go through counter. «Thursday 19:00 in Gràcia is agreed» — filling in
    where exactly must not un-agree when. It bumps nothing and resets nobody; the address simply
    becomes visible to whoever has already confirmed, which is what OF.21 then reports."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    with _STORE_LOCK:
        p = _mp_find(pid)
        if not p:
            return {"ok": False, "error": "NO_SUCH_PLAN"}
        if not _mp_is_in(p, who):
            return {"ok": False, "error": "NOT_A_PARTICIPANT"}
        no = _mp_refusal(p, who, "address")
        if no:
            return _idem_put(idem, no)
        if address:
            p["address"] = str(address)[:200]
            p["address_by"] = who
            (p.get("asks") or {}).pop("place", None)      # место названо — просьба выбрать снята
        if venue:
            p["venue"] = str(venue)[:120]
        # HY.20a/HY.20b: у гибрида второй вход доносят ОТДЕЛЬНО и в любом порядке — «место есть,
        # ссылки нет» и «ссылка есть, места нет» это два разных кадра, а не одно поле по очереди.
        if link:
            p["link"] = str(link)[:400]
            p["link_by"] = who
            (p.get("asks") or {}).pop("link", None)       # ссылка есть — просьба хостить снята
        p["updated"] = time.time()
        if address or venue or link:
            # Само место в ленту НЕ уходит: адрес открывается только подтвердившим (OF.C3), а лента
            # общая. В строке — сам факт, что место наконец названо; кто подтвердил, увидит его в плане.
            _sys_msg(who, _mp_other(p, who), "plan_place",
                     kind="link" if (link or p.get("mode") == "online") else "place")
        _save_store()
        return _idem_put(idem, {"ok": True, "plan": _mp_public(p, who)})


MP_ASKS = ("place", "link")


def mp_ask(pid, who, what, idem=None, cancel=False):
    """OF.20a / O.20a «Пусть выберет он(а)» / «Пусть хостит он(а)» — передать второму выбор места
    или создание ссылки.

    Раньше это была только реплика в чат, а флаг «уже попросил» жил в памяти экрана. Теперь просьба
    записана в план: второй видит на своём экране «X просит тебя выбрать место», а не общее поле с
    двумя кнопками, автор — «попросил(а), ждём», и так до тех пор, пока просимое не названо. Повтор
    той же просьбы — идемпотентен: перезаписывает время, не плодит строк в ленте."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    what = str(what or "").strip().lower()
    if what not in MP_ASKS:
        return {"ok": False, "error": "BAD_ASK", "allowed": list(MP_ASKS)}
    with _STORE_LOCK:
        p = _mp_find(pid)
        if not p:
            return {"ok": False, "error": "NO_SUCH_PLAN"}
        if not _mp_is_in(p, who):
            return {"ok": False, "error": "NOT_A_PARTICIPANT"}
        if cancel:
            # O.C3e «I can't host» / «Take it back»: просьбу можно было только исполнить. Теперь её
            # снимает любая из двух сторон — попросивший забирает, попрошенный отказывается; в ленте
            # это разные строки. План при этом не трогается: поле снова общее.
            if p.get("state") not in ("proposed", "confirmed"):
                return _idem_put(idem, {"ok": False, "error": "NOT_OPEN", "state": p.get("state")})
            ask = (p.get("asks") or {}).get(what) or None
            if not ask:
                return _idem_put(idem, {"ok": False, "error": "NO_ASK"})
            mine = _norm_name(ask.get("by")) == _norm_name(who)
            p["asks"].pop(what, None)
            p["updated"] = time.time()
            _sys_msg(who, _mp_other(p, who), "plan_ask_pulled" if mine else "plan_ask_declined", kind=what)
            _save_store()
            return _idem_put(idem, {"ok": True, "plan": _mp_public(p, who)})
        no = _mp_refusal(p, who, "ask_" + what)
        if no:
            return _idem_put(idem, no)
        was = ((p.get("asks") or {}).get(what) or {}).get("by")
        p.setdefault("asks", {})[what] = {"by": who, "t": time.time()}
        p["updated"] = time.time()
        if _norm_name(was) != _norm_name(who):
            _sys_msg(who, _mp_other(p, who), "plan_ask", kind=what)
        _save_store()
        return _idem_put(idem, {"ok": True, "plan": _mp_public(p, who)})


def mp_cancel(pid, who, reason="", idem=None):
    """Either side calls it off. A cancelled plan is terminal — the pair make a new one if they want."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    with _STORE_LOCK:
        p = _mp_find(pid)
        if not p:
            return {"ok": False, "error": "NO_SUCH_PLAN"}
        if not _mp_is_in(p, who):
            return {"ok": False, "error": "NOT_A_PARTICIPANT"}
        no = _mp_refusal(p, who, "cancel")
        if no:
            return _idem_put(idem, no)
        p["state"] = "cancelled"
        p["cancelled_by"] = who
        p["cancel_reason"] = str(reason or "")[:400]
        p["updated"] = time.time()
        _sys_msg(who, _mp_other(p, who), "plan_cancelled", at=p.get("starts_at"))
        _save_store()
        return _idem_put(idem, {"ok": True, "plan": _mp_public(p, who)})


def mp_move_to_call(pid, who, idem=None):
    """HY.23c — «место закрыто, уходим в звонок»: перевести ОБОИХ на другую сторону.

    Это не то же, что сменить свою сторону. Кадр описывает ровно тот случай, когда оба уже стоят у
    закрытой двери: менять сторону по одному значило бы, что каждый сам догадается сделать то же
    самое, а пока он не догадался — второй сидит в звонке один. Поэтому одно действие переводит
    двоих и говорит об этом в ленту.

    И это НЕ отмена: у гибрида есть выход, которого нет у встречи вживую, — ссылка уже открыта.
    Ровно это и написано на кадре.
    """
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    with _STORE_LOCK:
        p = _mp_find(pid)
        if not p:
            return {"ok": False, "error": "NO_SUCH_PLAN"}
        if not _mp_is_in(p, who):
            return {"ok": False, "error": "NOT_A_PARTICIPANT"}
        no = _mp_refusal(p, who, "move_to_call")
        if no:
            return _idem_put(idem, no)
        now = time.time()
        for nm in (p.get("host"), p.get("guest")):
            p.setdefault("sides", {})[_norm_name(nm)] = {"side": "call", "t": now, "by": who}
        p["moved_to_call"] = {"by": who, "t": now}
        p["updated"] = now
        _sys_msg(who, _mp_other(p, who), "moved_to_call")
        _save_store()
        return _idem_put(idem, {"ok": True, "plan": _mp_public(p, who)})


def mp_status(pid, who, status, eta_min=None, idem=None):
    """OF.22 / OF.22a / OF.23 — «уже иду», «опаздываю», «я на месте».

    This is the endpoint the copy «статус видит только твой собеседник» was always promising. It only
    means anything once both sides are coming: broadcasting «I'm on my way» to a meeting the other
    person has not agreed to is a claim about a plan that does not exist yet."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    st = str(status or "").strip().lower()
    if st not in MP_LIVE:
        return {"ok": False, "error": "BAD_STATUS", "allowed": list(MP_LIVE)}
    try:
        eta = int(eta_min) if eta_min not in (None, "") else None
    except (TypeError, ValueError):
        eta = None
    if eta is not None:
        eta = max(0, min(180, eta))
    with _STORE_LOCK:
        p = _mp_find(pid)
        if not p:
            return {"ok": False, "error": "NO_SUCH_PLAN"}
        if not _mp_is_in(p, who):
            return {"ok": False, "error": "NOT_A_PARTICIPANT"}
        no = _mp_refusal(p, who, "status")
        if no:
            return _idem_put(idem, no)
        # СТАТУС ДОЛЖЕН ДОХОДИТЬ ДО ПЕРЕПИСКИ, А НЕ ТОЛЬКО ДО ЭКРАНА ПЛАНА.
        #
        # Здесь статус только клался в план, и второй видел его, лишь если сам открывал экран
        # плана и смотрел на карточку. В переписку не приходило НИЧЕГО. Сообщено владельцем с
        # телефона: «говорю, что я на месте… часть сообщений не приходит вообще». Прогон 14.09.2026
        # подтвердил: из девяти действий плана восемь пишут строку в ленту, а все четыре статуса —
        # «выхожу», «опаздываю», «я на месте» и «не смогу» — не пишут ни одной.
        #
        # «Не смогу» тут особенно дорого: человек предупреждает, что не придёт, и предупреждение
        # уходит в пустоту.
        _key = _norm_name(who)
        _prev = (p.get("live") or {}).get(_key) or {}
        p.setdefault("live", {})[_key] = {"status": st, "eta_min": eta, "t": time.time()}
        p["updated"] = time.time()
        # Повтор того же статуса в ленту не пишем: человек жмёт «я на месте» дважды, а лента не
        # должна повторять за ним. Изменилось время опоздания — это новость, её пишем.
        if _prev.get("status") != st or (st in ("late", "otw") and _prev.get("eta_min") != eta):
            _sys_msg(who, _mp_other(p, who), "plan_status", status=st, eta=eta,
                     at=p.get("starts_at"))
        _save_store()
        return _idem_put(idem, {"ok": True, "plan": _mp_public(p, who)})


def mp_feedback(pid, who, happened=None, reason="", rating=None, text="", idem=None, how=""):
    """OF.24 «Did it happen» → OF.24a reason, or OF.25 feedback. Two screens, one record: the second
    call MERGES into the first instead of replacing it, or rating a meetup would erase the answer to
    whether it took place at all."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    now = time.time()
    with _STORE_LOCK:
        p = _mp_find(pid)
        if not p:
            return {"ok": False, "error": "NO_SUCH_PLAN"}
        if not _mp_is_in(p, who):
            return {"ok": False, "error": "NOT_A_PARTICIPANT"}
        no = _mp_refusal(p, who, "feedback")
        if no:
            return _idem_put(idem, no)
        k = _norm_name(who)
        row = dict((p.setdefault("feedback", {})).get(k) or {})
        if happened is not None:
            row["happened"] = bool(happened)
        if reason:
            row["reason"] = str(reason)[:400]
        if rating not in (None, ""):
            try:
                row["rating"] = max(1, min(5, int(rating)))
            except (TypeError, ValueError):
                pass
        if text:
            row["text"] = str(text)[:1000]
        # HY.25 — КАК встретились: за столиком, на звонке или и так и так. Вопрос только у гибрида
        # и только к тому, кто сказал «состоялась»: у него два входа, и какой сработал — это не
        # оценка встречи, а подсказка агенту, какой формат предлагать в следующий раз.
        if str(how or "").strip().lower() in MP_HOW:
            row["how"] = str(how).strip().lower()
        row["t"] = now
        p["feedback"][k] = row
        # It took place if either side says so; it did not only when someone says it did not and
        # nobody contradicts them. One person's silence is not evidence of anything.
        said = [r.get("happened") for r in p["feedback"].values() if r.get("happened") is not None]
        if said:
            p["outcome"] = {"happened": any(said), "at": now,
                            "reason": next((r.get("reason") for r in p["feedback"].values()
                                            if r.get("happened") is False and r.get("reason")), "")}
        if len(p["feedback"]) >= 2 or (said and not any(said)):
            p["state"] = "done"
        p["updated"] = now
        _save_store()
        return _idem_put(idem, {"ok": True, "plan": _mp_public(p, who),
                                "answered": len(p["feedback"])})


# ============================================================================ safety (OF.13b)
# «Заблокировать» and «Пожаловаться» were toasts. Block dropped the person from the local candidate
# array and said «Заблокировано»; report said «Спасибо. Центр безопасности посмотрит.» Neither sent
# anything anywhere. The blocked person kept seeing the profile, kept being able to invite, and came
# back in the next search — the list was local and the next /match rebuilt it from the server.
REPORT_REASONS = ("fake", "harassment", "spam", "unsafe", "underage", "other")


def _reports():
    return SESSION.setdefault("_reports", [])


def block_user(who, name, on=True, idem=None):
    """Blocking is not hiding. It closes everything open between the two: a pending invitation is
    withdrawn, a live plan is cancelled. Leaving those standing would mean a blocked person still had
    a meeting in their calendar with someone who wanted nothing more to do with them."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    me, them = _norm_name(who), str(name or "").strip()
    if not me or not them or me == _norm_name(them):
        return {"ok": False, "error": "TWO_PEOPLE_REQUIRED"}
    now = time.time()
    with _STORE_LOCK:
        lst = _blocks().setdefault(me, [])
        tn = _norm_name(them)
        if on and tn not in lst:
            lst.append(tn)
        elif not on and tn in lst:
            lst.remove(tn)
        closed = {"requests": 0, "plans": 0}
        if on:
            for r in _requests():
                if r.get("status") in REQ_OPEN and \
                        {_norm_name(r.get("from")), _norm_name(r.get("to"))} == {me, tn}:
                    r["status"] = "withdrawn" if _norm_name(r.get("from")) == me else "declined"
                    r["updated"] = now
                    r["version"] = int(r.get("version") or 1) + 1
                    closed["requests"] += 1
            for p in _mplans():
                if p.get("pair") == _pair_key(me, tn) and p.get("state") in ("proposed", "confirmed"):
                    p["state"] = "cancelled"
                    p["cancelled_by"] = who
                    p["cancel_reason"] = "blocked"
                    p["updated"] = now
                    closed["plans"] += 1
                    # ВТОРОМУ ГОВОРЯТ. Отмена шла молча: подтверждённая встреча исчезала у
                    # человека без единого слова, а экран тут же предлагал создать новую — то
                    # есть он приходил в назначенное место, не зная, что встречи нет. Причину
                    # блокировки не называем и назвать не можем: она принадлежит тому, кто
                    # заблокировал. Но факт отмены — принадлежит обоим.
                    _sys_msg(who, _mp_other(p, who), "plan_cancelled", at=p.get("starts_at"))
        _save_store()
        return _idem_put(idem, {"ok": True, "blocked": list(lst), "closed": closed})


def report_user(who, name, reason="", text="", idem=None):
    """A report is stored and queued for review. «Спасибо, посмотрим» has to correspond to a row that
    somebody can actually open, or it is a sentence that calms the person and protects nobody."""
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    me, them = str(who or "").strip(), str(name or "").strip()
    if not me or not them or _norm_name(me) == _norm_name(them):
        return {"ok": False, "error": "TWO_PEOPLE_REQUIRED"}
    rs = str(reason or "other").strip().lower()
    now = time.time()
    with _STORE_LOCK:
        rows = _reports()
        rid = "rp_%d_%s" % (int(now * 1000),
                            hashlib.sha1((me + them).encode("utf-8")).hexdigest()[:6])
        rows.append({"id": rid, "by": me, "about": them,
                     "reason": rs if rs in REPORT_REASONS else "other",
                     "text": str(text or "")[:1000], "at": now, "state": "open"})
        del rows[:-2000]
        _save_store()
    # Reporting someone you must keep meeting is not a safety feature. The block is part of the act.
    block_user(me, them, True)
    return _idem_put(idem, {"ok": True, "id": rid, "reasons": list(REPORT_REASONS)})


# ──────────────────────────────────────────────────────────────────────────────────── модерация
# Жалобы писались и не читались никем: строки копились в `_reports`, а экрана не было ни одного.
# «Спасибо, посмотрим» было фразой без адресата. Здесь появляется то, что делает её правдой:
# очередь для модератора, ответ, доходящий до человека, и зачистка данных при удалении учётки.
#
# ГЛАВНОЕ ПРАВИЛО ЭТОГО БЛОКА. Хранилище матчинга живёт В ПАМЯТИ этого процесса: оно читается
# один раз на старте и пишется по «грязным» ключам. Поэтому НИКТО СНАРУЖИ не имеет права писать
# в те же ключи напрямую в базу — при следующей записи матчинг перетрёт чужую правку своей
# копией из памяти, молча. Отсюда и эти ручки: панель просит, а делает всё сам матчинг.

def reports_queue(limit=200, reason="", name=""):
    """Очередь жалоб для модератора. Только чтение.

    К каждой строке добавляется то, ради чего очередь и открывают: сколько ВСЕГО жалоб на этого
    человека. Одна жалоба — это чей-то плохой вечер, пятая на того же — это уже видно без слов.
    """
    rows = list(_reports())
    rs, nm = str(reason or "").strip().lower(), _norm_name(name)
    about_counts = {}

    def _about_key(r):
        # Жалобы на группу считаются по группе, а не в общую кучу с пустым «на кого».
        return ("group:" + str(r.get("gid") or "")) if r.get("kind") == "group" else _norm_name(r.get("about"))

    for r in rows:
        k = _about_key(r)
        about_counts[k] = about_counts.get(k, 0) + 1
    out = []
    for r in reversed(rows):                       # свежие сверху: модератор смотрит с конца
        if rs and str(r.get("reason") or "") != rs:
            continue
        if nm and nm not in (_norm_name(r.get("about")), _norm_name(r.get("by"))):
            continue
        out.append(dict(r,
                        by_key=_norm_name(r.get("by")),
                        about_key=_about_key(r),
                        about_count=about_counts.get(_about_key(r), 1)))
        if len(out) >= max(1, min(500, int(limit or 200))):
            break
    # Потолок виден намеренно: `report_user` режет список до 2000 строк, и необработанная жалоба
    # может исчезнуть раньше, чем её откроют. Молчать об этом нельзя.
    return {"ok": True, "total": len(rows), "cap": 2000, "near_cap": len(rows) > 1800,
            "reasons": list(REPORT_REASONS) + list(GROUP_REPORT_REASONS), "reports": out}


# Имя, от которого приходят ответы модерации. Человеку важно видеть, что это продукт, а не
# случайный собеседник, поэтому отправитель назван и одинаков всегда.
SAFETY_SENDER = "Kleal"


def admin_notify(to, text, ref="", idem=None):
    """Написать человеку от имени продукта — так, чтобы он это УВИДЕЛ.

    Почему обычная реплика, а не системная строка. Системные строки (`_sys_msg`) клиент рисует по
    известному ему коду, а неизвестный код не рисует вовсе — при этом текст такой строки всё равно
    попал бы в список переписок предпросмотром. Вышло бы худшее: жирная непрочитанная строка,
    открываешь — пусто. Обычная реплика рисуется любым клиентом, включая уже установленные.

    Переписки может не быть вовсе — и это нормально: список тредов собирается из самих сообщений,
    поэтому строка сама создаёт разговор с Kleal.
    """
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    who = str(to or "").strip()
    body = str(text or "").strip()
    if not who or len(body) < 2:
        return {"ok": False, "error": "NAME_AND_TEXT_REQUIRED"}
    now = time.time()
    with _STORE_LOCK:
        m = {"id": _mid("a_"), "pair": _pair_key(SAFETY_SENDER, who),
             "from": SAFETY_SENDER, "to": who, "text": body[:2000], "t": now, "u": now,
             # Признак происхождения. Клиент по нему рисует реплику как системную, а не как
             # сообщение незнакомца; старый клиент лишнего ключа не заметит и покажет обычной.
             "admin": True}
        if ref:
            m["ref"] = str(ref)[:64]
        _messages().append(m)
        _save_store()
    return _idem_put(idem, {"ok": True, "id": m["id"], "to": who})


def admin_ban_sweep(name, reason="banned"):
    """Закрыть всё открытое у заблокированного: приглашения снять, встречи отменить.

    Сам запрет («не показывать, не пускать в группы») живёт полями строки человека и пишется
    панелью. Здесь — только то, что нельзя сделать снаружи: состояние в памяти этого процесса.
    Второй стороне про отмену говорят: подтверждённая встреча, исчезнувшая молча, — это человек,
    пришедший в назначенное место зря.
    """
    me = _norm_name(name)
    if not me:
        return {"ok": False, "error": "NAME_REQUIRED"}
    now = time.time()
    closed = {"requests": 0, "plans": 0}
    with _STORE_LOCK:
        for r in _requests():
            if r.get("status") not in REQ_OPEN:
                continue
            if me not in (_norm_name(r.get("from")), _norm_name(r.get("to"))):
                continue
            r["status"] = "withdrawn" if _norm_name(r.get("from")) == me else "declined"
            r["updated"] = now
            r["version"] = int(r.get("version") or 1) + 1
            closed["requests"] += 1
        for p in _mplans():
            if p.get("state") not in ("proposed", "confirmed"):
                continue
            if me not in (_norm_name(p.get("host")), _norm_name(p.get("guest"))):
                continue
            p["state"] = "cancelled"
            p["cancel_reason"] = reason
            p["updated"] = now
            closed["plans"] += 1
            other = _mp_other(p, name)
            if other:
                _sys_msg(name, other, "plan_cancelled", at=p.get("starts_at"))
        _save_store()
    return {"ok": True, "closed": closed}


def purge_person(name):
    """Стереть следы человека из хранилища матчинга — при удалении учётки.

    Почему это ДОЛЖНО делаться здесь. Хранилище матчинга — это словарь в памяти процесса; удаление
    строк прямо в базе снаружи не удалит ничего: при первой же записи матчинг вернёт их обратно
    из своей копии. Единственное честное удаление — то, что происходит в этом процессе.

    Что остаётся намеренно: строки жалоб, поданных НА этого человека, — они принадлежат тем, кто
    пожаловался, и нужны, если он вернётся под другим именем. Его собственные жалобы уходят. Так же
    остаются записи модерации групп (`_gremovals`).

    ГРУППЫ И ФАЙЛЫ (аудит 27.09.2026). Раньше стирание их не касалось вовсе, а удаление учётки из
    приложения не звало его совсем: у удалившегося оставались интенты на карте, переписка, планы,
    места в группах, голосовые и кружки на диске. Теперь человек выходит из каждой группы тем же
    путём, что и сам (`gi_leave`: наследник организатора, пересчёт кворума), после чего из групп
    уходят его след в составе, приглашения, реплики, ответы по планам и голоса. Файлы голосовых и
    кружков удалённых реплик стираются с диска.
    """
    me = _norm_name(name)
    if not me:
        return {"ok": False, "error": "NAME_REQUIRED"}
    gone = {}
    media = []

    def _media_of(m):
        for k in ("voice", "video"):
            v = m.get(k) if isinstance(m, dict) else None
            if isinstance(v, dict) and v.get("url"):
                media.append(str(v["url"]))

    with _STORE_LOCK:
        msgs = _messages()
        keep = [m for m in msgs if me not in (_norm_name(m.get("from")), _norm_name(m.get("to")))]
        for m in msgs:
            if me in (_norm_name(m.get("from")), _norm_name(m.get("to"))):
                _media_of(m)
        gone["messages"] = len(msgs) - len(keep)
        msgs[:] = keep

        reqs = _requests()
        keep = [r for r in reqs if me not in (_norm_name(r.get("from")), _norm_name(r.get("to")))]
        gone["requests"] = len(reqs) - len(keep)
        reqs[:] = keep

        plans = _mplans()
        keep = [p for p in plans if me not in (_norm_name(p.get("host")), _norm_name(p.get("guest")))]
        gone["plans"] = len(plans) - len(keep)
        plans[:] = keep

        ints = _intents()
        keep = [i for i in ints if _norm_name(i.get("owner_id") or i.get("owner") or i.get("self")) != me]
        gone["intents"] = len(ints) - len(keep)
        ints[:] = keep

        bl = _blocks()
        gone["blocks"] = 1 if bl.pop(me, None) is not None else 0
        for k, lst in list(bl.items()):
            if me in (lst or []):
                lst.remove(me)
                gone["blocks"] += 1

        rows = _reports()
        keep = [r for r in rows if _norm_name(r.get("by")) != me]
        gone["own_reports"] = len(rows) - len(keep)
        rows[:] = keep

        # Личная сессия человека лежит отдельным ключом верхнего уровня — по имени.
        for k in list(SESSION.keys()):
            if _norm_name(k) == me:
                SESSION.pop(k, None)
                gone["session_key"] = 1

        # ---- группы
        left = 0
        for g in list(_gintents()):
            if any(_norm_name(m.get("name")) == me for m in _gi_active(g)):
                if (gi_leave(g.get("id"), me) or {}).get("ok"):
                    left += 1
        gone["groups_left"] = left
        n = 0
        for g in _gintents():
            mem = g.get("members") or []
            kept = [m for m in mem if _norm_name(m.get("name")) != me]
            n += len(mem) - len(kept)
            g["members"] = kept
        gone["group_member_rows"] = n
        inv = _ginvites()
        keep = [i for i in inv if me not in (_norm_name(i.get("to")), _norm_name(i.get("frm")))]
        gone["group_invites"] = len(inv) - len(keep)
        inv[:] = keep
        gm = _gmsgs()
        keep = []
        for m in gm:
            # Автор реплики в группе — поле `frm` (у 1:1 — `from`); смотрим оба.
            if me in (_norm_name(m.get("frm")), _norm_name(m.get("from"))):
                _media_of(m)
            else:
                keep.append(m)
        gone["group_messages"] = len(gm) - len(keep)
        gm[:] = keep
        n = 0
        for pl in _gplans():
            for fld in ("responses", "sides", "live", "feedback"):
                d = pl.get(fld)
                if isinstance(d, dict):
                    for k in [k for k in d if _norm_name(k) == me]:
                        d.pop(k, None)
                        n += 1
        for v in _gvotes():
            d = v.get("votes")
            if isinstance(d, dict):
                for k in [k for k in d if _norm_name(k) == me]:
                    d.pop(k, None)
                    n += 1
        gone["group_plan_marks"] = n
        tr = _thread_reads()
        drop = [k for k in tr if me in str(k).split("|")]
        for k in drop:
            tr.pop(k, None)
        gone["thread_reads"] = len(drop)
        _names().pop(me, None)
        ev = _evidence()
        mine = [k for k, e in ev.items() if _norm_name(e.get("by")) == me]
        for k in mine:
            try:
                os.remove(os.path.join(EVIDENCE_DIR, str(ev[k].get("file") or "")))
            except Exception:
                pass
            ev.pop(k, None)
        gone["evidence"] = len(mine)
        _save_store()
    gone["files"] = _drop_media(media)
    return {"ok": True, "purged": gone}


def _drop_media(urls):
    """Удалить с диска файлы голосовых и кружков по их адресам. Только имя файла — путь к нему
    строит сервер, и имя проверяется по форме, которую выдаёт сам сервер при записи."""
    n = 0
    for u in urls or []:
        u = str(u or "")
        name = u.rsplit("/", 1)[-1]
        if not re.match(r"^[0-9a-f]{8,64}\.[a-z0-9]{2,5}$", name):
            continue
        folder = VOICE_DIR if "/voice/" in u else VIDEO_DIR if "/video/" in u else None
        if not folder:
            continue
        try:
            os.remove(os.path.join(folder, name))
            n += 1
        except FileNotFoundError:
            pass
        except Exception as e:
            print("[purge] файл не удалён: %s: %s" % (name, str(e)[:80]), flush=True)
    return n


def safety_for(who):
    me = _norm_name(who)
    return {"ok": True, "blocked": list(_blocks().get(me) or []),
            "reports": [dict(r) for r in _reports() if _norm_name(r.get("by")) == me][-50:],
            "reasons": list(REPORT_REASONS)}


def mp_alternatives(me, iid="", title="", except_pid=""):
    """OF.19e «Pick someone else»: кто раньше принял МОЁ приглашение по этой затее.

    Затея узнаётся по `iid` заявки (или метке затеи внутри неё), а если опознавателя нет хотя бы с
    одной стороны — по названию: у большинства живых заявок `iid` пуст (так же сверяет клиент,
    src/invites.ts sameIntent). Принявший уже открыл переписку — «Pick» значит сразу в чат, новое
    приглашение не нужно. `free` — с ним нет живого плана (у пары он один, PLAN_EXISTS)."""
    mk = _norm_name(me)
    iid = str(iid or "").strip()
    tk = _norm_name(title)
    ex = _norm_name(except_pid)
    out, seen = [], set()
    for r in sorted(_requests(), key=lambda x: -(x.get("updated") or 0)):
        if r.get("status") != "accepted" or _norm_name(r.get("from")) != mk:
            continue
        it = r.get("intent") or {}
        rid = str(r.get("iid") or it.get("kleal_intent_id") or it.get("id") or "").strip()
        same = (rid == iid) if (rid and iid) else bool(tk) and _norm_name(it.get("title")) == tk
        other = r.get("to")
        ok_ = _norm_name(other)
        if not same or not ok_ or ok_ in seen or ok_ == ex or _blocked_pair(me, other):
            continue
        seen.add(ok_)
        # Карточка OF.19e — только поля person_card: этот человек уже принял моё приглашение, и
        # ровно это я о нём видел в выдаче. Профессии в анкете нет — её не выдумываем.
        row = _person(other) or {}
        # Интересы бывают плоским списком (боевые анкеты) и словарём старой формы
        # {explicit, categories, roles} (shared/kleal_lib.py): из словаря — только explicit, иначе
        # наружу уезжали его ключи («explicit»). Район пуст — город, как на борде («Barcelona»).
        ints = row.get("interests") or []
        if isinstance(ints, dict):
            ints = ints.get("explicit") or []
        ints = [str(x) for x in (ints if isinstance(ints, (list, tuple)) else []) if isinstance(x, str) and x.strip()]
        out.append({"name": other, "photo": _photo_of(other), "age": row.get("age"),
                    "area": row.get("area") or row.get("city") or "", "interests": ints[:6],
                    "summary": row.get("summary") or "", "verified": bool(row.get("verified")),
                    "free": _mp_of(me, other) is None, "rid": r.get("id"), "at": r.get("updated")})
    return {"ok": True, "people": out}


def mp_for(who, peer=""):
    """Every 1:1 plan this person is part of — live ones first, then history.

    `peer` is the person the screen is looking at. Its only job is `peer_tz`: on the plan FORM there
    is no plan yet, so `their_tz` has nowhere to come from — and the form is exactly where the hour
    is being chosen and «20:00 for you is 02:00 for them» matters most.
    """
    me = _norm_name(who)
    now = time.time()
    active, history = [], []
    for p in _mplans():
        if not _mp_is_in(p, me):
            continue
        view = _mp_public(p, who)
        stale = p.get("starts_at") and now > float(p["starts_at"]) + MP_KEEP_AFTER
        (history if p.get("state") in ("done", "cancelled") or stale else active).append(view)
    active.sort(key=lambda x: x.get("starts_at") or x.get("updated") or 0)
    history.sort(key=lambda x: -(x.get("updated") or 0))
    out = {"ok": True, "plans": active, "history": history}
    if peer:
        out["peer_tz"] = _tz_of(peer)
    return out


GROUP_MIN, GROUP_MAX = 2, 8


def _gnorm(seq):
    return [_norm_name(x) for x in (seq or [])]

def _group_state(g):
    """Derived, never stored twice: forming -> confirmed at quorum, full at capacity."""
    if g.get("state") == "cancelled":
        return "cancelled"
    n = len(g.get("members") or [])
    if n >= int(g.get("max_size") or GROUP_MAX):
        return "full"
    return "confirmed" if n >= int(g.get("min_size") or GROUP_MIN) else "forming"

def _group_public(g, me=""):
    mem = list(g.get("members") or [])
    return {"gid": g.get("id"), "title": g.get("title"), "host": g.get("host"),
            "topics": list(g.get("topics") or []), "when": g.get("when") or "",
            "area": g.get("area") or "", "lat": g.get("lat"), "lon": g.get("lon"),
            "mode": g.get("mode") or "offline",
            "min_size": int(g.get("min_size") or GROUP_MIN), "max_size": int(g.get("max_size") or GROUP_MAX),
            "members": mem, "size": len(mem), "waitlist": list(g.get("waitlist") or []),
            "state": _group_state(g), "version": int(g.get("version") or 1),
            "mine": bool(me) and _norm_name(me) in _gnorm(mem),
            "hosting": bool(me) and _norm_name(me) == _norm_name(g.get("host")),
            "waiting": bool(me) and _norm_name(me) in _gnorm(g.get("waitlist"))}

def _groups():
    return SESSION.setdefault("_groups", [])

def group_create(host, title, topics, when="", area="", mode="offline",
                 min_size=GROUP_MIN, max_size=GROUP_MAX, lat=None, lon=None, idem=None):
    host = str(host or "").strip()
    if not host:
        return {"ok": False, "error": "host required"}
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    try:
        mn, mx = int(min_size or GROUP_MIN), int(max_size or GROUP_MAX)
    except Exception:
        mn, mx = GROUP_MIN, GROUP_MAX
    mn = max(2, min(mn, GROUP_MAX))
    mx = max(mn, min(mx, GROUP_MAX))
    now = time.time()
    with _STORE_LOCK:
        gs = _groups()
        gid = "gr_%d_%s" % (int(now * 1000), hashlib.sha1(host.encode("utf-8")).hexdigest()[:6])
        taken = {g.get("id") for g in gs}
        base, n = gid, 1
        while gid in taken:
            gid, n = "%s_%d" % (base, n), n + 1
        g = {"id": gid, "host": host, "title": str(title or "").strip()[:120] or "Meetup",
             "topics": [str(t).lower() for t in (topics or [])][:6], "when": str(when or "")[:80],
             "area": str(area or "")[:80], "mode": str(mode or "offline"), "lat": lat, "lon": lon,
             "min_size": mn, "max_size": mx, "members": [host], "waitlist": [], "state": "forming",
             "created": now, "updated": now, "version": 1,
             "config_version": (_CORE_CFG or {}).get("config_version")}
        gs.append(g)
        _save_store()
        return _idem_put(idem, {"ok": True, "group": _group_public(g, host)})

def group_join(gid, who, idem=None, version=None):
    """Joining is a transaction, exactly like accepting a proposal: capacity, state and pairwise
    safety are re-checked under the lock, so two people racing for the last seat cannot both win."""
    who = str(who or "").strip()
    if not who:
        return {"ok": False, "error": "name required"}
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    with _STORE_LOCK:
        for g in _groups():
            if g.get("id") != gid:
                continue
            if g.get("state") == "cancelled":
                return _idem_put(idem, {"ok": False, "error": "CANCELLED", "gid": gid})
            if version is not None and str(version) != str(g.get("version") or 1):
                return {"ok": False, "error": "VERSION_CONFLICT", "gid": gid,
                        "version": g.get("version"), "group": _group_public(g, who)}
            if _norm_name(who) in _gnorm(g.get("members")):
                return _idem_put(idem, {"ok": True, "gid": gid, "already": True,
                                        "group": _group_public(g, who)})
            # §15.1 safety exclusions are PAIRWISE: the joiner must be acceptable to every member
            # already in, and every member to them. Checking only the host would let a blocked
            # person walk in through someone else's group.
            mine = (SESSION.get("me") or {}).get("blocked") or []
            for m in (g.get("members") or []):
                ok, why = _policy_ok_now(who, m, mine)
                if not ok:
                    return _idem_put(idem, {"ok": False, "error": "NOT_ELIGIBLE", "gid": gid,
                                            "reason": why})
            if len(g.get("members") or []) >= int(g.get("max_size") or GROUP_MAX):
                wl = g.setdefault("waitlist", [])
                if _norm_name(who) not in _gnorm(wl):
                    wl.append(who)
                g["updated"] = time.time()
                g["version"] = int(g.get("version") or 1) + 1
                _save_store()
                return _idem_put(idem, {"ok": True, "gid": gid, "waitlisted": True,
                                        "group": _group_public(g, who)})
            g.setdefault("members", []).append(who)
            g["waitlist"] = [w for w in (g.get("waitlist") or []) if _norm_name(w) != _norm_name(who)]
            g["updated"] = time.time()
            g["version"] = int(g.get("version") or 1) + 1
            _save_store()
            return _idem_put(idem, {"ok": True, "gid": gid, "group": _group_public(g, who)})
    return {"ok": False, "error": "not found"}

def group_leave(gid, who, idem=None):
    """§15.3 step 7: on a drop, promote from the waitlist; losing quorum re-forms the group rather
    than cancelling it. The host leaving hands the group to the next member — an empty group ends."""
    who = str(who or "").strip()
    cached = _idem_get(idem)
    if cached is not None:
        return cached
    with _STORE_LOCK:
        for g in _groups():
            if g.get("id") != gid:
                continue
            mem = [m for m in (g.get("members") or []) if _norm_name(m) != _norm_name(who)]
            wl = [w for w in (g.get("waitlist") or []) if _norm_name(w) != _norm_name(who)]
            if len(mem) == len(g.get("members") or []) and len(wl) == len(g.get("waitlist") or []):
                return _idem_put(idem, {"ok": False, "error": "NOT_A_MEMBER", "gid": gid})
            promoted = None
            if len(mem) < int(g.get("max_size") or GROUP_MAX) and wl and len(mem) < len(g.get("members") or []):
                promoted = wl.pop(0)
                mem.append(promoted)
            g["members"], g["waitlist"] = mem, wl
            if not mem:
                g["state"] = "cancelled"
            elif _norm_name(g.get("host")) == _norm_name(who):
                g["host"] = mem[0]                       # the group survives its host leaving
            g["updated"] = time.time()
            g["version"] = int(g.get("version") or 1) + 1
            _save_store()
            return _idem_put(idem, {"ok": True, "gid": gid, "promoted": promoted,
                                    "group": _group_public(g, who)})
    return {"ok": False, "error": "not found"}

def _pair_fit(intent, a, b):
    """Directed relevance a->b combined reciprocally, on the SAME engine the slate uses. Returns
    0..1, or None when the engine is off — callers must treat None as 'unknown', never as 0."""
    if not (CORE_V2 and _CORE_CFG):
        return None
    try:
        # A stored user row and a searcher PROFILE are not the same shape (languages is a list on one
        # and {comfortable:[...]} on the other). Feeding a row in as a profile made reverse_features
        # throw, and _pair_fit swallowed it as "unknown" — every group utility came back null.
        a = dict(a or {})
        if isinstance(a.get("languages"), list):
            a["languages"] = {"comfortable": list(a["languages"])}
        H = {'topical': topical, 'cat_of': cat_of, 'reciprocal': _reciprocal, 'role_conflict': ROLE_CONFLICT}
        domain = _core.infer_domain(intent, cat_of)
        dom_cfg = _CORE_CFG["domains"].get(domain) or _CORE_CFG["domains"]["social_meet"]
        priors = {k: (_CORE_CFG["feature_groups"][k] or {}).get("unknown_prior", 0.5)
                  for k in _core.FEATURE_KEYS}
        f_ab = _core.build_features(intent, a, b, domain, H, ROLE_CONFLICT)
        d_ab = _core.directional_score(f_ab, dom_cfg, priors)
        f_ba = _core.reverse_features(intent, a, b, domain, H, ROLE_CONFLICT)
        d_ba = _core.directional_score(f_ba, dom_cfg, priors)
        return float(_core.reciprocal_score(d_ab, d_ba))
    except Exception:
        return None

def group_utility(g, rows=None):
    """Spec §15.2: 0.35*least_misery + 0.25*mean_pair_fit + 0.20*role_coverage + 0.10*time_overlap
    + 0.10*diversity_value. Only the terms we can actually evidence are scored; the rest stay out of
    the denominator instead of being invented (same unknown discipline as the pair engine)."""
    by = {}
    for c in (rows if rows is not None else load_candidates()):
        by[_norm_name(c.get("name"))] = c
    mem = [by.get(n) for n in _gnorm(g.get("members"))]
    mem = [m for m in mem if m]
    if len(mem) < 2:
        return {"utility": None, "least_misery": None, "mean_pair_fit": None, "pairs": 0}
    intent = {"topics": list(g.get("topics") or []), "type": g.get("type") or "social",
              "role": "meet", "mode": g.get("mode") or "offline", "time": g.get("when") or ""}
    fits = []
    for i in range(len(mem)):
        for j in range(len(mem)):
            if i == j:
                continue
            f = _pair_fit(intent, mem[i], mem[j])
            if f is not None:
                fits.append(f)
    if not fits:
        return {"utility": None, "least_misery": None, "mean_pair_fit": None, "pairs": 0}
    least, mean = min(fits), sum(fits) / len(fits)
    langs = set()
    for m in mem:
        langs |= {str(x).lower() for x in (m.get("languages") or [])}
    diversity = min(1.0, len(langs) / 3.0) if langs else None
    parts, weights = [(least, 0.35), (mean, 0.25)], []
    if diversity is not None:
        parts.append((diversity, 0.10))
    tot = sum(w for _v, w in parts)
    util = sum(v * w for v, w in parts) / tot if tot else None
    return {"utility": round(util, 4) if util is not None else None,
            "least_misery": round(least, 4), "mean_pair_fit": round(mean, 4), "pairs": len(fits)}

def group_list(self_name="", limit=30, open_only=False):
    me = str(self_name or "").strip()
    out = []
    rows = load_candidates()
    for g in _groups():
        if g.get("state") == "cancelled":
            continue
        pub = _group_public(g, me)
        if open_only and (pub["mine"] or pub["state"] == "full"):
            continue
        pub["fit"] = group_utility(g, rows)
        out.append(pub)
    # mine first, then the ones closest to happening, then group utility — never a raw percentage
    out.sort(key=lambda p: (not p["mine"], -(p["size"] or 0), -((p["fit"] or {}).get("utility") or 0)))
    return out[:max(1, int(limit or 30))]


# ---- helpers for the restored admin/diagnostic routes (verbatim from the pre-rewrite service)
# ── Learned categories ────────────────────────────────────────────────────────────────────────────
# The hand-written taxonomy is 165 words; interests are not a closed set. Filtration already decides
# a (category, subcategory) for text nobody has seen before — «лабубу» -> toys_collectibles, «улитки»
# -> pets/breeding — and that answer used to be computed, put on the intent and then ignored, because
# nothing on the CANDIDATE side had a category to compare against.
#
# This is that missing half: one shared word -> (broad, sub) map that both sides resolve through.
# Because it is consulted from cat_of(), the existing level logic (4 exact / 3 sub / 2 broad /
# 1 adjacent) applies to new interests unchanged — no new scoring path, no new weights.
#
# Only filtration writes here, and only its own vocabulary is accepted, so a malformed answer cannot
# invent a category. Entries are per-word and bounded; the file is small and human-readable on
# purpose, because a wrong category here is invisible in a slate and obvious in a list.
LEARNED_PATH = os.environ.get("KLEAL_LEARNED",
                              os.path.join(os.path.dirname(os.path.abspath(__file__)), "learned_topics.json"))


_FILTRATION_CATS = {"sports", "gaming", "esports", "tabletop", "music", "film_tv", "art_culture",
                    "books", "food_drink", "coffee", "nightlife", "outdoors", "travel", "tech",
                    "startups", "career", "languages", "wellness", "fashion", "toys_collectibles",
                    "pets", "photography", "dating", "social"}


def _load_learned():
    try:
        with open(LEARNED_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        return {str(k).lower(): (str(v[0]), str(v[1])) for k, v in d.items()
                if isinstance(v, (list, tuple)) and len(v) == 2 and str(v[0]) in _FILTRATION_CATS}
    except Exception:
        return {}


LEARNED = _load_learned()


# ---------------------------------------------------------------- one person, every reason (admin)
def _raw_store_rows():
    """The store as written, WITHOUT the loadtest filter — the admin has to be able to look at a
    row precisely because it was excluded from the pool."""
    try:
        with open(USERS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        lst = data.get("users") if isinstance(data, dict) else data
        return lst if isinstance(lst, list) else []
    except Exception:
        return []


def cohorts():
    """The saved queries that a 3000-row table cannot answer. Counts + names, computed over the raw
    store so a cohort can be ABOUT the rows retrieval drops."""
    rows = _raw_store_rows()
    now_ts = time.time()
    defs = [
        ("no_interests", "Без интересов — навсегда T5", lambda u: not [x for x in (u.get("interests") or []) if str(x).strip()]),
        ("no_intents", "Без своих интентов — никогда не T0", lambda u: not (u.get("intents") or [])),
        ("no_age", "Без возраста — нет dating и возрастных запросов", lambda u: _num(u.get("age")) is None),
        ("no_coords", "Без координат — нет поиска по радиусу", lambda u: _num(u.get("lat")) is None or _num(u.get("lon")) is None),
        ("paused", "На паузе — вне выдачи", lambda u: _core.is_paused(u, now_ts)),
        ("no_domains", "allowed_domains пуст — ни одного предложения", lambda u: isinstance(((u.get("receiving") or {}) if isinstance(u.get("receiving"), dict) else {}).get("allowed_domains"), list) and not ((u.get("receiving") or {}).get("allowed_domains"))),
        ("budget_zero", "Нулевой бюджет предложений", lambda u: (((u.get("receiving") or {}) if isinstance(u.get("receiving"), dict) else {}).get("proposal_budget") or {}).get("per_24h") == 0),
        ("unverified", "Не верифицированы", lambda u: not u.get("verified")),
        ("loadtest", "source=loadtest — вне поиска", lambda u: u.get("source") == "loadtest"),
    ]
    out = []
    for key, label, fn in defs:
        names = []
        n = 0
        for u in rows:
            try:
                if fn(u):
                    n += 1
                    if len(names) < 40:
                        names.append(u.get("name") or "?")
            except Exception:
                pass
        out.append({"key": key, "label": label, "count": n, "total": len(rows), "sample": names})
    return {"ok": True, "total": len(rows), "cohorts": out}


def compare_scorers(intent, prof, ctx=None):
    """Same query, both scorers, side by side — the shipped Core v2 and the legacy scorer that
    KLEAL_CORE_V2=0 falls back to.

    This exists because the fallback is silent. A config whose sha does not match drops the whole
    system onto the legacy scorer without an error anywhere, and the only visible symptom is that
    different people start appearing. Before this you could not answer «насколько вообще разные
    эти два движка» without editing an env var on a live box.
    """
    ctx = dict(ctx or {})
    try:
        new = match_candidates(intent, prof, ctx) if CORE_V2 else []
    except Exception as e:
        new = []
        ctx["_new_error"] = str(e)[:160]
    try:
        old = match_candidates_legacy(intent, prof, ctx)
    except Exception as e:
        old = []
        ctx["_old_error"] = str(e)[:160]
    nn = [str(c.get("name") or "") for c in new]
    on = [str(c.get("name") or "") for c in old]
    sn, so = set(nn), set(on)
    both = sn & so
    denom = float(len(sn | so)) or 1.0
    # Rank movement for the people BOTH scorers show — a slate can have identical membership and
    # still be a different product if the order is inverted.
    moved = []
    for name in both:
        a, b = nn.index(name), on.index(name)
        if a != b:
            moved.append({"name": name, "new": a + 1, "old": b + 1, "delta": b - a})
    moved.sort(key=lambda m: -abs(m["delta"]))
    return {"ok": True,
            "core": {"enabled": CORE_V2, "config_version": (_CORE_CFG or {}).get("config_version"),
                     "config_sha": ((_CORE_CFG or {}).get("_sha256") or "")[:12], "error": _CORE_ERR},
            "new": {"n": len(nn), "names": nn}, "old": {"n": len(on), "names": on},
            "shared": sorted(both), "onlyNew": [n for n in nn if n not in so],
            "onlyOld": [n for n in on if n not in sn],
            "jaccard": round(len(both) / denom, 3),
            "topChanged": bool(nn[:1] != on[:1]),
            "moved": moved[:8],
            "errors": {k: v for k, v in ctx.items() if k.startswith("_") and k.endswith("error")}}


_LEARNED_CAPS = 4000


_LEARNED_LOCK = threading.Lock()


# Generic descriptor words filtration emits alongside the real interest. Stored as categories they
# match everyone: «money» -> startups/investing would pair every uncategorised person who typed
# money, «find»/«search» are worse. A learned entry is permanent and invisible in a slate, so the
# writer — this service — is where the guard belongs, whatever the source.
_LEARN_STOP = {
    "hobby", "hobbies", "fun", "day", "days", "time", "people", "person", "friend", "friends",
    "company", "someone", "somebody", "group", "meet", "meetup", "socialize", "social", "find",
    "search", "looking", "want", "wanna", "activity", "activities", "thing", "things", "stuff",
    "money", "cash", "finance", "discussion", "chat", "talk", "collect", "collecting", "watching",
    "throwing", "playing", "doing", "making", "sport", "sports", "game", "games", "gaming",
    "interest", "interests", "new", "cool", "nice", "good", "best", "любой", "разное", "хобби",
    "деньги", "компания", "человек", "люди", "друзья", "встреча", "общение", "интерес",
}


def cat_of_fixed(word):
    """Taxonomy only, no learned entries — used to decide whether a word still needs teaching."""
    w = _norm(word)
    return _IDX.get(w, (None, None))


def learn_topics(pairs):
    """pairs: [(word, category, subcategory)]. Returns how many are new. `other` is filtration's
    honest "nothing here" and is never stored — an unknown word must stay unknown, not become a
    category that matches everyone else who is also uncategorised."""
    added = 0
    with _LEARNED_LOCK:
        for w, c, sub in pairs or []:
            w = str(w or "").strip().lower()[:40]
            c = str(c or "").strip().lower()
            sub = str(sub or "").strip().lower()[:40]
            if not w or c not in _FILTRATION_CATS or w in LEARNED or len(LEARNED) >= _LEARNED_CAPS:
                continue
            if w in _LEARN_STOP or len(w) < 3:
                continue                       # a generic descriptor, not an interest
            if cat_of_fixed(w)[0]:
                continue                       # the hand-written taxonomy already owns this word
            LEARNED[w] = (c, sub)
            added += 1
        if added:
            try:
                tmp = LEARNED_PATH + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({k: list(v) for k, v in LEARNED.items()}, f, ensure_ascii=False)
                os.replace(tmp, LEARNED_PATH)   # atomic: this file is read on every search
            except Exception:
                pass
    if added:
        # Invalidate the topic-similarity memo, because it reads the category map we just changed.
        # Conditional on purpose: `same_topic` carried @lru_cache before the matching rewrite and
        # does not now, so this line raised AttributeError on every learn that stored a word —
        # i.e. the whole learning path 500'd — after learn_topics was restored alongside it.
        # Nothing to invalidate when nothing is cached, and the guard picks the cache back up
        # automatically if the decorator returns.
        if hasattr(same_topic, "cache_clear"):
            same_topic.cache_clear()
    return added


# tools/gen_test_users.py stamps source="loadtest" on its 1000-person load pool. Only the Explore map
# ever filtered them out, so a real user's SEARCH was ranked against ~982 synthetic people (every
# result surnamed Volkov/Petrov/Garcia). They are fixtures, not people, and must not be proposed to
# anyone. The eval and fuzz harnesses run ON that pool, so they flip this back on.
INCLUDE_LOADTEST = os.environ.get("KLEAL_INCLUDE_LOADTEST", "0") != "0"


def person_report(name, now_ts=None):
    """Why is this person invisible, and why do they see nobody? Two different questions with two
    different answers, and until this endpoint existed both looked like "the ranker is bad".

    Every field is reported as the store actually holds it. A missing value is reported as None
    (the panel renders «не собрано») and NEVER as a default — a fabricated `age: 30` here would
    hide the exact gate that is dropping the person.
    """
    now_ts = now_ts or time.time()
    # `name` — id человека (панель шлёт id; подпись разрешается однозначно в _admin_target).
    _pid = _canon_pid(name)
    row = None
    if _pid:
        row = next((u for u in _raw_store_rows() if str(u.get("id") or "") == _pid), None)
        if row is not None:
            name = row.get("name") or name
    want = _norm_name(name)
    if row is None:
        for u in _raw_store_rows():
            if _norm_name(u.get("name")) == want:
                row = u
                break
    if row is None:
        for u in CANDIDATES:                      # demo pool, only reachable with KLEAL_MERGE_DEMO
            if _norm_name(u.get("name")) == want:
                row = dict(u, source="demo")
                break
    if row is None:
        return {"ok": False, "error": "no such person", "name": name}

    in_pool = any((str(c.get("id") or "") == str(row.get("id") or "")) if row.get("id")
                  else _norm_name(c.get("name")) == want for c in load_candidates())
    ints = [str(x).lower() for x in (row.get("interests") or []) if str(x).strip()]
    lat, lon = _num(row.get("lat")), _num(row.get("lon"))
    age = _num(row.get("age"))
    langs = [str(l)[:2].lower() for l in (row.get("langs") or []) if str(l).strip()]
    r = row.get("receiving") if isinstance(row.get("receiving"), dict) else None
    received = (_proposals_received_24h() or {}).get(want, 0)

    # ---- inbound: can anyone find them at all
    blocks = []                                    # hard, absolute — no search reaches them
    warns = []                                     # narrows them to a subset of searches
    if row.get("source") == "loadtest" and not INCLUDE_LOADTEST:
        blocks.append({"key": "loadtest", "ru": "строка помечена source=loadtest — исключена из поиска",
                       "en": "row is source=loadtest — excluded from retrieval"})
    if _core.is_paused(row, now_ts):
        why = ("флаг paused" if row.get("paused") else
               ("receiving.status=paused" if str((r or {}).get("status") or "").lower() == "paused"
                else "receiving.paused_until в будущем"))
        blocks.append({"key": "paused", "ru": "на паузе (%s)" % why, "en": "paused (%s)" % why})
    if not ints:
        blocks.append({"key": "no_interests",
                       "ru": "нет интересов — тир T5 при ЛЮБОМ запросе, никогда не показывается",
                       "en": "no interests — tier T5 for every query, never shown"})
    if row.get("open") is False and not r:
        warns.append({"key": "open_false", "ru": "open=false — готовность «занят(а)»",
                      "en": "open=false — readiness 'busy'"})
    if age is None:
        warns.append({"key": "no_age",
                      "ru": "возраст не собран — выпадает из dating и из любого запроса с возрастным диапазоном",
                      "en": "age unknown — dropped from dating and any age-range query"})
    elif age < MIN_AGE:
        blocks.append({"key": "under_age", "ru": "младше 18 — жёсткий отказ", "en": "under 18 — hard gate"})
    if lat is None or lon is None:
        warns.append({"key": "no_coords",
                      "ru": "нет координат — выпадает из любого запроса с радиусом",
                      "en": "no coordinates — dropped from any query with a radius"})
    if not langs:
        warns.append({"key": "no_langs", "ru": "языки не собраны — выпадает при requiredLanguages",
                      "en": "no languages — dropped when a language is required"})
    if not row.get("verified"):
        warns.append({"key": "unverified", "ru": "не верифицирован — выпадает при «только проверенные»",
                      "en": "unverified — dropped when the search asks for verified only"})
    if not row.get("datingOk"):
        warns.append({"key": "no_dating", "ru": "нет согласия на dating — выпадает из dating-запросов",
                      "en": "no dating opt-in — dropped from dating queries"})
    if (_num(row.get("pending")) or 0) >= MAX_PENDING:
        blocks.append({"key": "pending", "ru": "слишком много открытых приглашений (%s)" % row.get("pending"),
                       "en": "too many open invites (%s)" % row.get("pending")})

    # ---- receiving policy, read the same way readiness_state reads it (opt-outs fail closed)
    out_cfg = (_CORE_CFG or {}).get("outreach") or {}
    pb = ((r or {}).get("proposal_budget") or {}).get("per_24h")
    cap = pb if isinstance(pb, (int, float)) and not isinstance(pb, bool) else \
        (out_cfg.get("max_proposals_received_per_user_24h") or 4)
    q = (r or {}).get("quiet_hours") or {}
    tzoff = int(q.get("tz_offset_min", 120))
    local_min = int((now_ts // 60 + tzoff) % 1440)
    defaults = out_cfg.get("quiet_hours_local") or ["22:00", "09:00"]
    quiet_now = _core._in_quiet_hours(local_min, q.get("start") or defaults[0], q.get("end") or defaults[-1])
    policy = {
        "hasPolicy": r is not None,
        "status": (r or {}).get("status"),
        "allowedDomains": (r or {}).get("allowed_domains"),
        "passiveOutreach": (r or {}).get("passive_outreach"),
        "budgetPer24h": cap, "budgetExplicit": pb is not None,
        "received24h": received,
        "budgetSpent": received >= int(cap),
        "quietHours": {"start": q.get("start") or defaults[0], "end": q.get("end") or defaults[-1],
                       "tzOffsetMin": tzoff,
                       "localTime": "%02d:%02d" % (local_min // 60, local_min % 60),
                       "inQuietNow": bool(quiet_now)},
    }
    if isinstance(policy["allowedDomains"], list) and not policy["allowedDomains"]:
        blocks.append({"key": "no_domains", "ru": "allowed_domains пуст — ни одного личного предложения",
                       "en": "allowed_domains is empty — no personal proposal in any domain"})
    if policy["budgetSpent"]:
        warns.append({"key": "budget", "ru": "лимит предложений на сутки исчерпан (%s из %s)" % (received, cap),
                      "en": "24h proposal budget spent (%s of %s)" % (received, cap)})

    readiness = {}
    for d in _core.ALL_DOMAINS:
        readiness[d] = _core.readiness_state(row, d, now_ts, _CORE_CFG, received)

    # ---- outbound: what THIS person's own requests can reach
    own_intents = row.get("intents") if isinstance(row.get("intents"), list) else []
    outbound = []
    if not own_intents:
        outbound.append({"key": "no_intents",
                         "ru": "нет собственных интентов — этот человек никогда не станет T0 "
                               "(взаимным совпадением) ни для кого",
                         "en": "no own intents — this person can never be a T0 reciprocal match for anybody"})
    if not ints:
        outbound.append({"key": "no_interests_out",
                         "ru": "нет интересов — его собственный поиск не на чем строить",
                         "en": "no interests — nothing to build their own search on"})
    if lat is None or lon is None:
        outbound.append({"key": "no_coords_out",
                         "ru": "нет координат — его поиск не может отфильтровать по расстоянию",
                         "en": "no coordinates — their own search cannot filter by distance"})

    return {"ok": True, "name": row.get("name"), "inPool": in_pool,
            "verdict": ("невидим" if blocks else ("виден" if in_pool else "не в пуле")),
            "identity": {"source": row.get("source"), "area": row.get("area") or None,
                         "age": age, "verified": bool(row.get("verified")),
                         "datingOk": bool(row.get("datingOk")),
                         "lat": lat, "lon": lon, "radiusKm": _num(row.get("radiusKm")),
                         "langs": langs or None, "interests": ints or None,
                         "ownIntents": len(own_intents), "entities": len(row.get("entities") or [])},
            "blocks": blocks, "warnings": warns, "outbound": outbound,
            "policy": policy, "readiness": readiness}


def proposals_registry(limit=300):
    """Stage 3: the proposal ledger. Four failures look identical from outside — declined, expired
    unanswered, revoked by policy at accept time, and never created at all — and only the trace
    separates them. Read-only: _save_store() writes this file without tmp+replace, so a reader that
    ever wrote could truncate a request mid-flight."""
    now = time.time()
    rows = []
    for r in (SESSION.get("_requests") or []):
        if not isinstance(r, dict):
            continue
        trace = r.get("trace") if isinstance(r.get("trace"), list) else []
        exp = r.get("expires_at")
        try:
            exp_f = float(exp) if exp is not None else None
        except (TypeError, ValueError):
            exp_f = None
        st = str(r.get("status") or "").lower()
        rows.append({
            "id": r.get("id"), "from": r.get("from"), "to": r.get("to"),
            "note": (str(r.get("note") or "")[:160] or None),
            "status": st or "unknown",
            "domain": r.get("domain") or (r.get("intent") or {}).get("type"),
            "createdAt": r.get("created_at") or r.get("ts"),
            "ageHours": (round((now - float(r.get("created_at") or r.get("ts") or now)) / 3600.0, 1)
                         if (r.get("created_at") or r.get("ts")) else None),
            "expiresAt": exp_f,
            "expiresInHours": (round((exp_f - now) / 3600.0, 1) if exp_f else None),
            "expired": bool(exp_f and exp_f <= now and st in ("pending", "sent", "")),
            "configVersion": r.get("config_version"),
            "trace": [str(t) for t in trace][-8:],
            "policyRevoked": st == "policy_revoked" or any("policy_revoked" in str(t) for t in trace),
        })
    rows.sort(key=lambda x: (x["createdAt"] or 0), reverse=True)
    by_status = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    return {"ok": True, "total": len(rows), "byStatus": by_status,
            "expiringSoon": sum(1 for r in rows
                                if r["expiresInHours"] is not None and 0 < r["expiresInHours"] < 12
                                and r["status"] in ("pending", "sent")),
            "expiredUnanswered": sum(1 for r in rows if r["expired"]),
            "policyRevoked": sum(1 for r in rows if r["policyRevoked"]),
            "requests": rows[:limit]}


def reset_fatigue(name):
    """Clear one person's received-proposal log. The ONLY write this admin surface makes, and it
    touches matching's own kleal_store.json — never users.json."""
    key = _norm_name(name)
    with _STORE_LOCK:
        log = SESSION.setdefault("_proposals", {})
        had = len(log.get(key) or [])
        log[key] = []
    _save_store()
    return {"ok": True, "name": name, "cleared": had}


def _group_slate(cands):
    """§15 reads each candidate's directed fit from `relevance`; a core_v2 slate card carries it as
    `lcb`. Map it losslessly (every other field, including any diversity axis, is preserved).

    This lived in /api/agent/group and nowhere else, so the SAME slate produced a sensible group
    through that door and a hash-ordered one through /api/agent/match — with relevance missing, every
    utility component that depends on it is 0 and selection falls back to the id-hash tiebreak. On
    prod that put a 0.665 candidate in the group and left the 0.883 one out. One helper, both doors."""
    return [dict(c, relevance=(c.get("relevance") if c.get("relevance") is not None else c.get("lcb", 0)))
            for c in (cands or []) if isinstance(c, dict)]


# §15.4 domain packs, restricted to the keys the DATA can satisfy. The packs also carry
# required_equipment, max_skill_spread and mandatory_roles; users.json has no equipment, level or
# per-person role field, so applying those verbatim makes every candidate violate a hard gate and
# "padel for four" answers NO_FEASIBLE_GROUP. Seat counts are wired now; the rest waits for profiles
# that actually carry equipment and skill.
_PACK_SIZE_KEYS = ("size_min", "size_max", "quorum", "capacity")


def _group_constraints(intent, caller=None):
    """An intent's §15 set-constraints.

    `groupSize` is the TOTAL headcount asked for, THE ASKER INCLUDED — they are never in their own
    candidate slate, so the group being assembled is one seat smaller than the number they said.

    Precedence: explicit caller constraints > the stated size > the domain pack > config defaults.
    The floor matters more than the ceiling: §15 grows a seed only while a size/quorum SHORTFALL is
    outstanding and then stops (adding a weaker member always lowers least_misery, so nothing is ever
    added for utility alone). Group size is therefore decided by size_min, which is why leaving it at
    the config default returned exactly three people whatever was asked for."""
    intent = intent or {}
    pack = {}
    for name in list(intent.get("topics") or []) + [intent.get("type"), intent.get("activity")]:
        p = kg.pack_for(name)
        if p:
            # Pack numbers are TOTAL headcount — a padel court holds four PLAYERS. §15 counts the
            # seats it is filling, and the asker is never in their own candidate slate, so each of
            # those numbers is one smaller here. Copying them across units capped a padel group at
            # four strangers PLUS you — five on a four-seat court — and made a request for six
            # collide with the pack's capacity and fall all the way back to three.
            pack = {k: max(1, int(v) - 1) for k, v in p.items() if k in _PACK_SIZE_KEYS}
            break
    out = dict(pack)
    try:
        total = int(intent.get("groupSize")) if intent.get("groupSize") is not None else None
    except (TypeError, ValueError):
        total = None
    if total:
        # seats = people to find; the asker holds one of the places. §1's floor of three total is
        # therefore two seats, and nothing may ask this layer for a smaller "group".
        seats = max(GROUP_MIN_TOTAL - 1, min(kg._MAX_MVP_SIZE, total - 1))
        ceiling = pack.get("size_max") or pack.get("capacity")
        if ceiling:
            seats = min(seats, int(ceiling))   # a padel court does not grow because you asked it to
        out["size_min"] = out["quorum"] = out["size_max"] = seats
    out.update({k: v for k, v in (caller or {}).items() if v is not None})
    return out


def form_group_from_slate(intent, cands, constraints=None, now_ts=None, pair_rel=None, reserve=False):
    """Assemble a group out of an already-ranked slate (§15.3).

    The §15 core takes candidates as an ARGUMENT — it never retrieves. That is why calling
    /api/agent/group without a slate answered NO_FEASIBLE_GROUP: there was nothing to form a group
    from, which looked like the algorithm failing and was really an empty input.

    Runs only when GROUPS_ENABLED. The override is supplied here, by the service, rather than by the
    caller: kg's switch stays the exact test-only key it was written as, and whether the product
    offers groups is decided in one place instead of by whoever crafts the request body.

    `reserve` defaults to FALSE and that is the important part. §15.3.5 reserve_members CLAIMS SEATS
    in a persisted ledger, so forming a group with a ledger attached is a write. Wiring that into
    the search path made every search silently hold seats for people who had agreed to nothing —
    visible immediately as a second identical request returning a different company, because the
    first one had already taken the first three. A search is a read. Seats are claimed only when a
    caller explicitly asks to commit."""
    if not GROUPS_ENABLED:
        return kg.dormant_response(intent, constraints or {})
    if not cands:
        return dict(kg.dormant_response(intent, constraints or {}, note="no candidates to form a group from"),
                    feasible=False)
    slate = _group_slate(cands)
    cons = _group_constraints(intent, constraints)
    now_ts = now_ts or time.time()

    def _run(c, ledger=None):
        return kg.run_group_formation(intent, slate, c, _CORE_CFG, override=_GROUP_OVERRIDE,
                                      now_ts=now_ts, ledger=ledger, pair_rel=pair_rel)

    def _finish(res, c):
        """Say what was asked for, what the rules allowed, and what was filled — all as TOTAL
        headcount, the asker included, because that is the number they typed.

        `asked` is their own number, not the clamped one: a request for eight padel players is
        answered with four, and the UI can only explain that ("a court seats four") if it can still
        see that eight was asked. `allowed` is the ceiling after the §15.4 pack, `formed` the result."""
        allowed = cons.get("size_min")
        res["seats"] = {"asked": intent.get("groupSize"),
                        "allowed": (allowed + 1) if allowed else None,
                        "formed": (len(res.get("members") or []) + 1) if res.get("members") else 0,
                        "relaxed": c is not cons}
        res["group_formation_live"] = True
        return res

    if not reserve:
        res = _run(cons)
        # A thin pool must degrade to a smaller REAL group, never to nothing: §15 treats size_min as
        # hard, so a request for six in a city with four padel players answered NO_FEASIBLE_GROUP —
        # which reads as "groups are broken" and is really "we could only find four". Relax the floor
        # ONCE, to the config default, and label the result.
        if not res.get("members") and (cons.get("size_min") or 0) > 2:
            relaxed = dict(cons)
            relaxed.pop("size_min", None); relaxed.pop("quorum", None)
            alt = _run(relaxed)
            if alt.get("members"):
                res = _finish(alt, relaxed)
                return dict(res, reserved=False)
        return dict(_finish(res, cons), reserved=False)
    with _STORE_LOCK:
        led = SESSION.setdefault("_group_ledger", {})
        res = _finish(_run(cons, ledger=led), cons)
        _save_store()
    res["reserved"] = True
    # kg always reports enabled:False (it is scaffolding and says so). The PRODUCT-level answer is
    # this switch, so state it plainly next to kg's own field rather than rewriting kg's contract.
    res["group_formation_live"] = True
    return res


# ---------------------------------------------------------------- HTTP dispatcher (matching only)
class H(BaseHTTPRequestHandler):
    _pid = ""          # личность запроса — id человека (см. _whoami); пусто, пока не определена
    _pname = ""
    # ---- restored routes: the names the profile frontend actually calls (see the block above) ----
    # ---- ЛИЧНОСТЬ В РУЧКАХ (docs/IDENTITY.md) ---------------------------------------------------
    # Действующее лицо — ВСЕГДА self._pid (сессия; без сессии — только бот без владельца или
    # временная личность теста). То, что написано в `self`/`from`/`who` тела, личностью не является:
    # 26.09.2026 по одному имени можно было читать чужую переписку и писать от чужого лица.
    # Собеседник — по `<поле>_id`; подпись принимается, только если однозначна (_peer).
    def _peer_of(self, src, *fields, related=False):
        """(id собеседника, ответ-отказ или None). `src` — тело запроса или разобранная строка.

        `related=True` — только для действий, возможных ЛИШЬ внутри уже существующей связи
        (сообщение, прочтение, план, карточка собеседника, решение по участнику группы): там тёзку
        без id разводит круг своих собеседников. Первый контакт (приглашение, зов в группу, блок и
        жалоба из выдачи) — никогда: человек нажал на НОВОГО «Ивана», а связь есть со старым, и
        приглашение ушло бы не тому. Это поймал tools/identity_http_test.py."""
        if not any(str(src.get(f) or "").strip() or str(src.get(f + "_id") or "").strip()
                   for f in fields):
            return "", {"ok": False, "error": "TWO_PEOPLE_REQUIRED"}   # код отказа — прежний
        for f in fields:
            pid = _peer(src.get(f + "_id"), src.get(f), self._pid if related else "",
                        src.get("gid") or "")
            if pid:
                return pid, None
        for f in fields:
            v = src.get(f)
            if isinstance(v, str) and v.strip() and not src.get(f + "_id") \
                    and len(_people_index()["by_name"].get(_norm_name(v)) or []) > 1:
                return "", {"ok": False, "error": "AMBIGUOUS_PERSON",
                            "note": "several people share this name — send %s_id" % f}
        return "", {"ok": False, "error": "UNKNOWN_PERSON"}

    def _no_actor(self):
        return {"ok": False, "error": "sign in required"}

    def _restored_get(self):
        """The GET half of the restored screens. Returns True when it handled the request."""
        from urllib.parse import unquote
        base = self.path.split("?")[0]
        q = dict(kv.split("=", 1) for kv in self.path.split("?", 1)[-1].split("&") if "=" in kv) \
            if "?" in self.path else {}
        q = {k: unquote(str(v).replace("+", " ")) for k, v in q.items()}
        me = self._pid                       # кто читает — решает сессия, а не `self` в строке запроса
        # 1:1 meeting plans. Read-your-own-only: the view is built FOR the caller, because the exact
        # address is released per viewer (OF.C3) — handing back an unfiltered row would leak it.
        if base == "/api/agent/mplan-alternatives":
            # OF.19e «Pick someone else»: кто уже сказал «да» на ЭТУ затею — только свои заявки.
            if not me:
                send_json(self, 200, {"ok": True, "people": []})
            else:
                ex = (_peer(q.get("except_id"), q.get("except"), me)
                      if (q.get("except") or q.get("except_id")) else "")
                send_json(self, 200, mp_alternatives(me, q.get("iid", ""), q.get("title", ""), ex))
            return True
        if base in ("/api/agent/mplans", "/api/agent/mplan", "/api/agent/safety"):
            if base != "/api/agent/safety":
                with _STORE_LOCK:
                    _mp_sweep()
            if base == "/api/agent/safety":
                send_json(self, 200, safety_for(me) if me else
                          {"ok": True, "blocked": [], "reports": [], "reasons": list(REPORT_REASONS)})
            elif base == "/api/agent/mplans":
                peer = _peer(q.get("with_id"), q.get("with"), me) if (q.get("with") or q.get("with_id")) else ""
                send_json(self, 200, mp_for(me, peer) if me else {"ok": True, "plans": [], "history": []})
            else:
                pl = _mp_find(q.get("id", ""))
                if pl and (not me or not _mp_is_in(pl, me)):
                    send_json(self, 200, {"ok": False, "error": "NOT_A_PARTICIPANT"})
                else:
                    send_json(self, 200, {"ok": bool(pl), "plan": _mp_public(pl, me) if pl else None})
            return True
        # Group intents (spec: individual invites, one shared chat). Handled first so their own
        # membership ACL applies rather than the 1:1 thread rules below.
        if base in ("/api/agent/gintent", "/api/agent/gintent-thread", "/api/agent/gintents",
                    "/api/agent/gplans", "/api/agent/home-invites", "/api/agent/ginvite"):
            gid = q.get("gid", "")
            # Все четыре ручки отдают план — значит все четыре обязаны сперва провести время.
            _gp_sweep()
            if base == "/api/agent/home-invites":
                send_json(self, 200, home_invites(me, q.get("pick") in ("1", "true")))
            elif base == "/api/agent/ginvite":
                send_json(self, 200, gi_invite_detail(q.get("id", ""), me))
            elif base == "/api/agent/gplans":
                send_json(self, 200, gp_for(me))
            elif base == "/api/agent/gintents":
                send_json(self, 200, gi_for(me))
            elif base == "/api/agent/gintent-thread":
                try:
                    since = float(q.get("since", 0) or 0)
                except (TypeError, ValueError):
                    since = 0.0
                send_json(self, 200, gi_thread(gid, me, since))
            else:
                g = _gi_find(gid)
                send_json(self, 200, {"ok": bool(g), "group": _gi_public(g, me) if g else None})
            return True
        if base not in ("/api/agent/thread", "/api/agent/threads",
                        "/api/agent/inbox", "/api/agent/outbox", "/api/agent/groups"):
            return False
        if base == "/api/agent/threads":
            send_json(self, 200, {"threads": threads_for(me) if me else []})
        elif base == "/api/agent/thread":
            try:
                since = float(q.get("since", 0) or 0)
            except (TypeError, ValueError):
                since = 0.0
            other = _peer(q.get("with_id"), q.get("with"), me)
            if not me or not other:
                send_json(self, 200, {"messages": [], "peer_read_at": 0})
                return True
            send_json(self, 200, {
                "messages": thread(me, other, since),
                # MSG.11: когда ВТОРАЯ сторона в последний раз открывала эту пару. Моих отметок тут
                # нет — свою прочитанность человеку показывать незачем.
                "peer_read_at": (_thread_reads().get(_pair_key(me, other)) or {}).get(_norm_name(other), 0),
            })
        elif base in ("/api/agent/inbox", "/api/agent/outbox"):
            fn = inbox if base.endswith("inbox") else outbox
            send_json(self, 200, {"requests": fn(me) if me else []})
        else:
            try:
                lim = max(1, min(100, int(q.get("limit", 30))))
            except (TypeError, ValueError):
                lim = 30
            send_json(self, 200, {"groups": group_list(me, lim, q.get("open") in ("1", "true"))})
        return True

    # Ручки, где действующее лицо обязательно. Ответ без личности — «войди», а не молчаливое «ок».
    _ACTOR_POST = frozenset((
        "/api/agent/intent-save", "/api/agent/intent-delete", "/api/agent/message",
        "/api/agent/thread-end", "/api/agent/message-react", "/api/agent/message-delete",
        "/api/agent/thread-read", "/api/agent/propose", "/api/agent/respond", "/api/agent/withdraw",
        "/api/agent/request-pick",
        "/api/agent/request-archive", "/api/agent/gintent-create", "/api/agent/gintent-invite",
        "/api/agent/gintent-invite-cancel", "/api/agent/gintent-approve", "/api/agent/gintent-remove",
        "/api/agent/ginvite-respond", "/api/agent/gintent-post", "/api/agent/gmsg-react",
        "/api/agent/gmsg-delete", "/api/agent/gplan-begin", "/api/agent/gplan-cancel",
        "/api/agent/gplan-fix", "/api/agent/gplan-update", "/api/agent/gplan-link",
        "/api/agent/gplan-details", "/api/agent/gplan-mode", "/api/agent/gplan-side",
        "/api/agent/gplan-respond", "/api/agent/gplan-vote-open", "/api/agent/gplan-vote",
        "/api/agent/gplan-vote-close", "/api/agent/gplan-vote-decide", "/api/agent/gplan-status",
        "/api/agent/gplan-feedback", "/api/agent/mplan-propose", "/api/agent/mplan-respond",
        "/api/agent/person", "/api/agent/block", "/api/agent/report", "/api/agent/mplan-ask",
        "/api/agent/mplan-address", "/api/agent/mplan-cancel", "/api/agent/mplan-move-to-call",
        "/api/agent/mplan-side", "/api/agent/mplan-status", "/api/agent/mplan-feedback",
        "/api/agent/gintent-leave", "/api/agent/gintent-convert", "/api/agent/gintent-convert-respond",
        "/api/agent/gintent-close", "/api/agent/gintent-report",
        "/api/agent/gintent-takeover", "/api/agent/gintent-takeover-vote", "/api/agent/gintent-takeover-withdraw",
        "/api/agent/gintent-takeover-back", "/api/agent/gintent-role-offer", "/api/agent/gintent-role-respond",
        "/api/agent/gintent-role-withdraw", "/api/agent/gplan-hold-answer",
        "/api/agent/group-create", "/api/agent/group-join", "/api/agent/group-leave"))

    def _restored_post(self, p, body):
        """The POST half of the restored screens. Returns True when it handled the request."""
        if p in self._ACTOR_POST and not self._pid:
            send_json(self, 200, self._no_actor())
            return True
        me = self._pid
        # Интенты — только свои: «свои» решает личность запроса, а не присланное `self`.
        if p == "/api/agent/intent-save":
            send_json(self, 200, save_intent(body.get("self"), body.get("intent") or {},
                                             body.get("title"), body.get("id"),
                                             bool(body.get("launched")), owner_id=me))
        elif p == "/api/agent/intent-delete":
            send_json(self, 200, delete_intent(body.get("self"), body.get("id"), owner_id=me))
        elif p == "/api/agent/intents":
            send_json(self, 200, {"intents": list_intents(body.get("self"), body.get("profile") or {},
                                                          body.get("live") is not False,
                                                          owner_id=me)})
        elif p == "/api/agent/message":
            to, no = self._peer_of(body, "to", related=True)
            send_json(self, 200, no or send_message(me, to, body.get("text"),
                                                    body.get("voice"), body.get("client_id"),
                                                    body.get("reply_to"), body.get("video")))
        elif p == "/api/agent/thread-end":
            other, no = self._peer_of(body, "with", "other", related=True)
            send_json(self, 200, no or end_thread(me, other, body.get("idem")))
        elif p == "/api/agent/message-react":
            send_json(self, 200, message_react(me, body.get("id"), body.get("emoji")))
        elif p == "/api/agent/message-delete":
            send_json(self, 200, message_delete(me, body.get("id")))
        elif p == "/api/agent/thread-read":
            other, no = self._peer_of(body, "with", related=True)
            send_json(self, 200, no or thread_mark_read(me, other))
        elif p == "/api/agent/propose":
            to, no = self._peer_of(body, "to")
            send_json(self, 200, no or propose(me, to, body.get("intent") or {},
                                               body.get("note"), body.get("idem")))
        elif p == "/api/agent/respond":
            send_json(self, 200, respond(body.get("id"), body.get("decision"), me,
                                         body.get("idem"), body.get("version"), body.get("flow")))
        elif p == "/api/agent/request-pick":
            send_json(self, 200, pick_request(body.get("id"), me, body.get("idem")))
        elif p == "/api/agent/withdraw":
            send_json(self, 200, withdraw_request(body.get("id"), me, body.get("idem")))
        elif p == "/api/agent/request-archive":
            send_json(self, 200, archive_request(body.get("id"), me))
        elif p == "/api/agent/gintent-create":
            send_json(self, 200, gi_create(me, body.get("intent"), body.get("title"),
                                           body.get("min_total"), body.get("max_total"),
                                           body.get("idem")))
        elif p == "/api/agent/gintent-invite":
            # `to` — один человек или список: организатор зовёт всю выдачу разом и получает ответ по
            # каждому. Люди — по id (`to_id` / `to_ids`), подпись — только однозначная.
            _to, _ids = body.get("to"), body.get("to_ids")
            if isinstance(_to, list) or isinstance(_ids, list):
                names = list(_to or []) if isinstance(_to, list) else []
                ids = list(_ids or []) if isinstance(_ids, list) else []
                peers = []
                for i in range(max(len(names), len(ids))):
                    pid = _peer(ids[i] if i < len(ids) else "", names[i] if i < len(names) else "")
                    peers.append(pid or ("?" + str(names[i] if i < len(names) else "")))
                send_json(self, 200, gi_invite_many(body.get("gid"), me, peers,
                                                    body.get("note"), body.get("idem")))
            else:
                to, no = self._peer_of(body, "to")
                send_json(self, 200, no or gi_invite(body.get("gid"), me, to,
                                                     body.get("note"), body.get("idem")))
        elif p == "/api/agent/gintent-invite-cancel":
            send_json(self, 200, gi_invite_cancel(body.get("id"), me, body.get("idem")))
        elif p == "/api/agent/gintent-close":
            send_json(self, 200, gi_close(body.get("gid"), me, body.get("idem")))
        elif p == "/api/agent/gintent-report":
            ev = body.get("evidence") if isinstance(body.get("evidence"), list) else []
            about, no = ("", None)
            if str(body.get("about") or "").strip() or str(body.get("about_id") or "").strip():
                about, no = self._peer_of(body, "about", related=True)
            send_json(self, 200, no or gi_report(body.get("gid"), me, body.get("reason"), body.get("text"),
                                                 ev, body.get("idem"), about=about))
        elif p == "/api/agent/gintent-approve":
            who, no = self._peer_of(body, "who", related=True)
            send_json(self, 200, no or gi_approve(body.get("gid"), me, who,
                                                  body.get("accept", True), body.get("idem")))
        elif p == "/api/agent/gintent-remove":
            who, no = self._peer_of(body, "who", related=True)
            send_json(self, 200, no or gi_remove(body.get("gid"), me, who,
                                                 body.get("reason"), body.get("idem")))
        elif p == "/api/agent/ginvite-respond":
            send_json(self, 200, gi_respond(body.get("id"), me, bool(body.get("accept")), body.get("idem")))
        elif p == "/api/agent/gintent-post":
            send_json(self, 200, gi_post(body.get("gid"), me, body.get("text"), body.get("idem"),
                                         body.get("voice"), body.get("client_id"),
                                         body.get("reply_to"), body.get("video")))
        elif p == "/api/agent/gmsg-react":
            send_json(self, 200, gmsg_react(body.get("gid"), me, body.get("id"), body.get("emoji")))
        elif p == "/api/agent/gmsg-delete":
            send_json(self, 200, gmsg_delete(body.get("gid"), me, body.get("id")))
        elif p == "/api/agent/gplan-begin":
            send_json(self, 200, gp_begin(body.get("gid"), me, body.get("when"),
                                          body.get("place"), body.get("note"),
                                          body.get("starts_at"), body.get("idem"), body.get("link")))
        elif p == "/api/agent/gplan-cancel":
            send_json(self, 200, gp_cancel(body.get("id"), me, body.get("idem")))
        elif p == "/api/agent/gplan-hold-answer":
            send_json(self, 200, gp_hold_answer(body.get("id"), me, body.get("choice"), body.get("idem")))
        elif p == "/api/agent/gplan-fix":
            send_json(self, 200, gp_fix(body.get("id"), me, body.get("idem"), body.get("round")))
        elif p == "/api/agent/gplan-update":
            send_json(self, 200, gp_update(body.get("id"), me, body.get("when"),
                                           body.get("place"), body.get("note"),
                                           body.get("starts_at"), body.get("idem"), body.get("link")))
        elif p == "/api/agent/gplan-link":
            send_json(self, 200, gp_link(body.get("id"), me, body.get("link"), body.get("idem")))
        elif p == "/api/agent/gplan-details":
            send_json(self, 200, gp_details(body.get("id"), me, body.get("place"), body.get("link"),
                                            body.get("idem")))
        elif p == "/api/agent/gplan-mode":
            send_json(self, 200, gp_mode(body.get("id"), me, body.get("mode"), body.get("idem")))
        elif p == "/api/agent/gplan-side":
            send_json(self, 200, gp_side(body.get("id"), me, body.get("side"), body.get("idem")))
        elif p == "/api/agent/gplan-respond":
            send_json(self, 200, gp_respond(body.get("id"), me, body.get("action"),
                                            body.get("when"), body.get("place"), body.get("note"),
                                            body.get("starts_at"), body.get("idem"), body.get("link")))
        elif p == "/api/agent/gplan-vote-open":
            send_json(self, 200, gp_vote_open(body.get("id"), me, body.get("kind"),
                                              body.get("when"), body.get("place"), body.get("note"),
                                              body.get("starts_at"), body.get("idem"), body.get("link")))
        elif p == "/api/agent/gplan-vote":
            send_json(self, 200, gp_vote(body.get("id"), me, bool(body.get("yes")), body.get("idem")))
        elif p == "/api/agent/gplan-vote-close":
            send_json(self, 200, gp_vote_close(body.get("id"), me, body.get("idem")))
        elif p == "/api/agent/gplan-vote-decide":
            # `apply` по умолчанию НЕ True: решение «менять план» слишком тяжёлое, чтобы приезжать
            # из пропущенного поля. Не сказали — значит оставили как есть.
            send_json(self, 200, gp_vote_decide(body.get("id"), me, bool(body.get("apply")),
                                                body.get("idem")))
        elif p == "/api/agent/gplan-status":
            send_json(self, 200, gp_status(body.get("id"), me, body.get("status"),
                                           body.get("eta_min"), body.get("idem")))
        elif p == "/api/agent/gplan-feedback":
            send_json(self, 200, gp_feedback(body.get("id"), me, body.get("happened"),
                                             body.get("reason"), body.get("text"), body.get("rating"),
                                             body.get("idem")))
        elif p == "/api/agent/mplan-propose":
            # ОТКАЗ ОБЯЗАН БЫТЬ ВИДЕН В ЖУРНАЛЕ. Пишем КОД отказа и выбранное время, без имён и без
            # содержимого: причина нужна, переписка в журнале — нет.
            to, no = self._peer_of(body, "to", related=True)
            _mp = no or mp_propose(me, to, body.get("title"), body.get("mode") or "offline",
                                   body.get("starts_at"), body.get("when"),
                                   body.get("district"), body.get("address"),
                                   body.get("note"), body.get("cover"),
                                   body.get("venue"), body.get("idem"), body.get("link"))
            if not (_mp or {}).get("ok"):
                print("[mplan] отказ=%s starts_at=%s mode=%s"
                      % (str((_mp or {}).get("error") or "?")[:32],
                         body.get("starts_at"), body.get("mode")), flush=True)
            send_json(self, 200, _mp)
        elif p == "/api/agent/mplan-respond":
            send_json(self, 200, mp_respond(body.get("id"), me, body.get("action"),
                                            body.get("starts_at"), body.get("when"),
                                            body.get("district"), body.get("title"),
                                            body.get("note"), body.get("version"), body.get("idem"),
                                            body.get("round")))
        elif p == "/api/agent/person":
            other, no = self._peer_of(body, "name", related=True)
            send_json(self, 200, no or person_card(me, other))
        elif p == "/api/agent/block":
            other, no = self._peer_of(body, "name")
            send_json(self, 200, no or block_user(me, other, body.get("on", True), body.get("idem")))
        elif p == "/api/agent/report":
            other, no = self._peer_of(body, "name")
            send_json(self, 200, no or report_user(me, other, body.get("reason"), body.get("text"),
                                                   body.get("idem")))
        elif p == "/api/agent/mplan-ask":
            send_json(self, 200, mp_ask(body.get("id"), me, body.get("what"), body.get("idem"),
                                        bool(body.get("cancel"))))
        elif p == "/api/agent/mplan-address":
            send_json(self, 200, mp_address(body.get("id"), me, body.get("address"),
                                            body.get("venue"), body.get("idem"), body.get("link")))
        elif p == "/api/agent/mplan-cancel":
            send_json(self, 200, mp_cancel(body.get("id"), me, body.get("reason"), body.get("idem")))
        elif p == "/api/agent/mplan-move-to-call":
            send_json(self, 200, mp_move_to_call(body.get("id"), me, body.get("idem")))
        elif p == "/api/agent/mplan-side":
            send_json(self, 200, mp_side(body.get("id"), me, body.get("side"), body.get("idem")))
        elif p == "/api/agent/mplan-status":
            send_json(self, 200, mp_status(body.get("id"), me, body.get("status"),
                                           body.get("eta_min"), body.get("idem")))
        elif p == "/api/agent/mplan-feedback":
            send_json(self, 200, mp_feedback(body.get("id"), me, body.get("happened"),
                                             body.get("reason"), body.get("rating"),
                                             body.get("text"), body.get("idem"), body.get("how")))
        elif p == "/api/agent/gintent-leave":
            send_json(self, 200, gi_leave(body.get("gid"), me, body.get("idem")))
        # Смена организатора (GR.42–44).
        elif p == "/api/agent/gintent-takeover":
            send_json(self, 200, gi_takeover(body.get("gid"), me, body.get("idem")))
        elif p == "/api/agent/gintent-takeover-vote":
            send_json(self, 200, gi_takeover_vote(body.get("gid"), me, bool(body.get("yes")), body.get("idem")))
        elif p == "/api/agent/gintent-takeover-withdraw":
            send_json(self, 200, gi_takeover_withdraw(body.get("gid"), me, body.get("idem")))
        elif p == "/api/agent/gintent-takeover-back":
            send_json(self, 200, gi_takeover_back(body.get("gid"), me, bool(body.get("hand")), body.get("idem")))
        elif p == "/api/agent/gintent-role-offer":
            to, no = self._peer_of(body, "to", related=True)
            send_json(self, 200, no or gi_role_offer(body.get("gid"), me, to, body.get("idem")))
        elif p == "/api/agent/gintent-role-respond":
            send_json(self, 200, gi_role_respond(body.get("gid"), me, bool(body.get("accept")), body.get("idem")))
        elif p == "/api/agent/gintent-role-withdraw":
            send_json(self, 200, gi_role_withdraw(body.get("gid"), me, body.get("idem")))
        elif p == "/api/agent/gintent-convert":
            send_json(self, 200, gi_convert_ask(body.get("gid"), me, body.get("idem")))
        elif p == "/api/agent/gintent-convert-respond":
            send_json(self, 200, gi_convert_respond(body.get("gid"), me, bool(body.get("agree")),
                                                    body.get("idem")))
        elif p == "/api/agent/group-create":
            send_json(self, 200, group_create(me, body.get("title"), body.get("topics"),
                                              body.get("when"), body.get("area"), body.get("mode"),
                                              body.get("min_size"), body.get("max_size"),
                                              body.get("lat"), body.get("lon"), body.get("idem")))
        elif p == "/api/agent/group-join":
            send_json(self, 200, group_join(body.get("gid"), me, body.get("idem"), body.get("version")))
        elif p == "/api/agent/group-leave":
            send_json(self, 200, group_leave(body.get("gid"), me, body.get("idem")))
        else:
            return False
        return True


    # ---- restored diagnostics: what the admin panel proxies to (person card, cohorts, proposal
    # registry, scorer compare, fatigue reset, stability/diversity probes, the funnel). The rewrite
    # dropped these with the rest; without them 23 of the panel's 87 checks fail and its Cohorts,
    # Person, Compare, Funnel and Stability views are blank. Bodies are verbatim from the
    # pre-rewrite service — read-only diagnostics, they never write to the store or send anything.
    def _admin_target(self, src, id_field="id", name_field="name"):
        """Кого касается действие модератора: id — и только однозначно. По подписи тёзок панель
        могла забанить или стереть не того из двух «Иванов»; теперь для тёзок — отказ со списком."""
        pid = _peer(src.get(id_field) or src.get(name_field + "_id"), "")
        if pid:
            return pid, None
        nm = str(src.get(name_field) or "").strip()
        rows = _people_index()["by_name"].get(_norm_name(nm)) or []
        if len(rows) > 1:
            return "", {"ok": False, "error": "AMBIGUOUS_PERSON",
                        "candidates": [{"id": r.get("id"), "name": r.get("name"), "age": r.get("age"),
                                        "area": r.get("area") or r.get("city"),
                                        "owned": bool(r.get("owner"))} for r in rows[:10]]}
        pid = _peer("", nm)
        return (pid, None) if pid else ("", {"ok": False, "error": "UNKNOWN_PERSON"})

    def _restored_admin_get(self):
        """Returns True when it handled the request."""
        if self.path.split("?")[0] == "/api/agent/admin/person":
            q = dict(kv.split("=", 1) for kv in self.path.split("?", 1)[-1].split("&") if "=" in kv) if "?" in self.path else {}
            from urllib.parse import unquote
            q = {k: unquote(str(v).replace("+", " ")) for k, v in q.items()}
            pid, no = self._admin_target(q)
            send_json(self, 200, no or person_report(pid))
        elif self.path.split("?")[0] == "/api/agent/admin/cohorts":
            send_json(self, 200, cohorts())
        elif self.path.split("?")[0] == "/api/agent/admin/proposals":
            send_json(self, 200, proposals_registry())
        elif self.path.split("?")[0] == "/api/agent/admin/reports":
            from urllib.parse import unquote
            q = dict(kv.split("=", 1) for kv in self.path.split("?", 1)[-1].split("&") if "=" in kv) \
                if "?" in self.path else {}
            _nm = unquote(q.get("name", "").replace("+", " "))
            _pid = _peer(q.get("id"), _nm) if (_nm or q.get("id")) else ""
            send_json(self, 200, reports_queue(limit=int(q.get("limit") or 200),
                                               reason=unquote(q.get("reason", "")),
                                               name=_pid or _nm))
        else:
            return False
        return True

    def _restored_admin_post(self, p, body):
        """Returns True when it handled the request."""
        if p == "/api/agent/admin/compare":
            send_json(self, 200, compare_scorers(_normalize_intent(body.get("intent")),
                                                 body.get("profile") if isinstance(body.get("profile"), dict) else {},
                                                 body.get("ctx") if isinstance(body.get("ctx"), dict) else {}))
        elif p == "/api/agent/learn-phrases":
            # Фраза целиком и её темы, как их увидела фильтрация. Отдельно от пословного
            # /api/agent/learn: тот учит СЛОВО категорией фразы, и именно так в карту попали
            # «gracia -> спорт/падел» и «weekend -> спорт/ракетки».
            send_json(self, 200, {"ok": True,
                                  "added": learn_phrases(body.get("items") or []),
                                  "known": len(PHRASE_TOPICS)})
        elif p == "/api/agent/learn":
            # Teach the shared word -> (category, subcategory) map. Buddy calls this with what
            # filtration already worked out, so no extra model call is spent here.
            pairs = [(x.get("word"), x.get("category"), x.get("subcategory"))
                     for x in (body.get("items") or []) if isinstance(x, dict)]
            send_json(self, 200, {"ok": True, "added": learn_topics(pairs), "known": len(LEARNED)})
        elif p == "/api/agent/admin/fatigue-reset":
            send_json(self, 200, reset_fatigue(body.get("name")))     # журнал движка — пока по подписи
        elif p == "/api/agent/admin/notify":
            pid, no = self._admin_target(body, "to_id", "to")
            send_json(self, 200, no or admin_notify(pid, body.get("text"),
                                                    body.get("ref") or "", body.get("idem")))
        elif p == "/api/agent/admin/ban-sweep":
            pid, no = self._admin_target(body)
            send_json(self, 200, no or admin_ban_sweep(pid, body.get("reason") or "banned"))
        elif p == "/api/agent/admin/purge":
            pid, no = self._admin_target(body)
            # Строки человека может уже не быть (учётку удалили раньше, стирание повторяют): тогда
            # по сырому id — ручка внутренняя, снаружи её закрывает шлюз.
            if no and str(body.get("id") or "").strip():
                pid, no = str(body.get("id")).strip().lower(), None
            send_json(self, 200, no or purge_person(pid))
        elif p == "/api/agent/stability":
            # Ported capability (not code) from the PROD|OLD|NEW bench: run the SAME search N times
            # and check the slate does not move. Our tie-break is a name hash, so drift can only come
            # from something time-dependent — readiness, quiet hours, proposal fatigue — and drift is
            # indistinguishable, from the outside, from "random people".
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            intent = _normalize_intent(body.get("intent"))
            runs = max(2, min(8, int(body.get("runs") or 4)))
            pin = body.get("now")
            outs = []
            for _i in range(runs):
                # `seen` pinned empty ON PURPOSE. Paging is a deterministic function of the seen-set,
                # so this probe answers the question it was written to answer — can the RANKER drift
                # on its own — rather than accidentally measuring rotation.
                ctx = {"self": (prof.get("name") or ""), "uid": "admin-stab", "seen": []}
                if pin:
                    ctx["now"] = float(pin)
                try:
                    outs.append([c.get("name") for c in match_candidates(intent, prof, ctx)])
                except Exception as e:
                    outs.append(["__error__: " + str(e)[:80]])
            first = outs[0]
            same_order = all(o == first for o in outs)
            same_set = all(set(o) == set(first) for o in outs)
            drift = sorted(set().union(*[set(o) for o in outs]) - set(first)) if not same_set else []
            send_json(self, 200, {"ok": True, "runs": runs, "n": len(first),
                                  "stableOrder": same_order, "stableSet": same_set,
                                  "pinnedNow": bool(pin), "drift": drift[:10],
                                  "slates": [o[:8] for o in outs]})
        elif p == "/api/agent/diversity":
            # «Мне попадаются одни и те же люди, какой бы запрос я ни написал.» That is a claim about
            # a SET of searches, so no single search can confirm or refute it. Run N topics as one
            # person and report how many distinct people came back and who keeps reappearing.
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            topics = [str(t).strip() for t in (body.get("topics") or []) if str(t).strip()][:24]
            base = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            ctx = {"self": (prof.get("name") or ""), "uid": "admin-div"}
            seen, per, empty = {}, [], []
            for t in topics:
                it = _normalize_intent(dict(base, topics=[t]))
                try:
                    cands = match_candidates(it, prof, dict(ctx))
                except Exception:
                    cands = []
                names = [c.get("name") for c in cands]
                per.append({"topic": t, "n": len(names), "names": names[:8]})
                if not names:
                    empty.append(t)
                for n in names:
                    seen[n] = seen.get(n, 0) + 1
            runs = max(1, len([p for p in per if p["n"]]))
            repeats = sorted(((v, k) for k, v in seen.items() if v > 1), reverse=True)[:10]
            send_json(self, 200, {"ok": True, "queries": len(topics), "withResults": runs,
                                  "distinctPeople": len(seen),
                                  "shownMoreThanOnce": sum(1 for v in seen.values() if v > 1),
                                  "topRepeats": [{"name": k, "times": v} for v, k in repeats],
                                  "emptyTopics": empty, "per": per})
        elif p == "/api/agent/funnel":
            # «Почему никого нет», as a shape rather than a slate: how the pool collapses, stage by
            # stage, with the exact gate string for each drop. Read-only, writes nothing, sends nothing.
            intent = _normalize_intent(body.get("intent"))
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            ctx = body.get("ctx") if isinstance(body.get("ctx"), dict) else {}
            if body.get("now"):
                ctx["now"] = float(body["now"])
            diag = {}
            try:
                cands = match_candidates(intent, prof, ctx, diag)
                send_json(self, 200, {"ok": True, "intent": intent, "funnel": diag,
                                      "names": [c.get("name") for c in cands]})
            except Exception as e:
                send_json(self, 200, {"ok": False, "error": str(e)[:200], "funnel": diag})
        else:
            return False
        return True

    def _whoami(self, body=None):
        """Определить личность запроса ОДИН раз и положить её туда, где её ждут.

        `self._pid` / `self._pname` — id и подпись по сессии (или, без сессии, по правилам
        `_unowned_pid`). В `ctx` поиска кладётся `self_id`, а при живой сессии и `self` — подпись
        из сессии поверх присланной: движок исключает «себя», подтягивает свою анкету и сверяет
        блокировки по id, а не по тому, как человек назвался в запросе. См. docs/IDENTITY.md.
        """
        claimed = ""
        src = body if isinstance(body, dict) else {}
        for k in ("self", "from", "who", "me", "uid", "owner", "host"):
            v = src.get(k)
            if isinstance(v, str) and v.strip():
                claimed = v.strip()
                break
        if not claimed and isinstance(src.get("ctx"), dict):
            # Поиск присылает «кто ищет» только внутри ctx — без этого запрос без сессии оставался
            # без личности, и блокировки (они по id) в выдаче не применялись.
            v = src["ctx"].get("self")
            if isinstance(v, str) and v.strip():
                claimed = v.strip()
        if not claimed and "?" in self.path:
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            for k in ("self", "who", "me", "from"):
                if q.get(k) and str(q[k][0]).strip():
                    claimed = str(q[k][0]).strip()
                    break
        try:
            self._pid, self._pname = _identify(self, claimed)
        except Exception as e:
            print("[identity] не определилась: %s" % str(e)[:120], flush=True)
            self._pid, self._pname = "", ""
        ctx = src.get("ctx") if isinstance(src.get("ctx"), dict) else None
        if ctx is not None:
            if self._pid:
                ctx["self_id"] = self._pid
                if self._pname and not self._pid.startswith(ANON):
                    ctx["self"] = self._pname
            else:
                ctx.pop("self_id", None)
        return self._pid

    def _watch_owner(self, body=None):
        """НАБЛЮДЕНИЕ, А НЕ ЗАПРЕТ. Ничего не блокирует и ничего не меняет в ответе.

        ЗАЧЕМ. В этом сервисе человек до сих пор определяется ИМЕНЕМ, которое сам же и прислал:
        шестьдесят с лишним ручек принимают `self`/`name`/`from` из запроса и по нему достают
        чужие заявки, переписку и планы. Заголовок `Authorization` при этом уже доезжает — шлюз
        его пробрасывает, — но никто его не читает.

        Включать запрет вслепую нельзя: связка «аккаунт → строка» проставлена у шестнадцати строк
        из восьмисот двадцати восьми, и отказ по несовпадению выкинул бы из поиска тех, кто вошёл
        раньше. Сначала надо узнать ЦИФРУ: сколько живого трафика вообще приходит с токеном и как
        часто заявленное имя расходится с именем из сессии. Её сейчас не существует.

        В ЖУРНАЛ НЕ ПОПАДАЮТ НИ ИМЕНА, НИ АДРЕСА — только признаки. Журнал читают в отладке, и
        превращать его во вторую копию персональных данных нельзя.
        """
        try:
            claimed = ""
            if isinstance(body, dict):
                for k in ("self", "name", "from", "me", "uid"):
                    v = body.get(k)
                    if isinstance(v, str) and v.strip():
                        claimed = v.strip()
                        break
            if not claimed and "?" in self.path:
                from urllib.parse import parse_qs, urlparse
                q = parse_qs(urlparse(self.path).query)
                for k in ("self", "name", "from", "me", "uid"):
                    if q.get(k) and str(q[k][0]).strip():
                        claimed = str(q[k][0]).strip()
                        break
            mine = kleal_auth.caller_name(self)
            has_tok = bool(kleal_auth.bearer(self))
            if not claimed and not has_tok:
                return                       # ручка не про личность — молчим
            if claimed and mine and claimed.strip().lower() == mine.strip().lower():
                verdict = "совпало"
            elif claimed and mine:
                verdict = "РАСХОЖДЕНИЕ"
            elif claimed and not mine:
                verdict = "имя без сессии"
            else:
                verdict = "сессия без имени"
            print("[owner] %s | токен=%s | путь=%s"
                  % (verdict, "да" if has_tok else "нет", self.path.split("?", 1)[0]), flush=True)
        except Exception:
            pass                             # наблюдение не имеет права мешать работе

    def do_GET(self):
        self._watch_owner()
        self._whoami()
        _p = self.path.split("?", 1)[0]
        if _p == "/health":
            # Ровно один вопрос: процесс жив и отвечает. Состояние базы и очереди собирает
            # /status на шлюзе — учить каждый сервис одному и тому же значит заводить копии,
            # которые расходятся молча.
            return send_json(self, 200, {"service": "matching", "ok": True,
                                         "pool": len(load_candidates() or []),
                                         "storage": db.MODE, "queue": mq.MODE})
        if _p.startswith("/api/agent/video/"):
            return self._video_serve(_p.rsplit("/", 1)[-1])
        if _p.startswith("/api/agent/voice/"):
            return self._voice_serve(_p.rsplit("/", 1)[-1])
        if _p.startswith("/api/agent/admin/evidence/"):
            # Файл к жалобе — только модератору: ручка внутренняя (шлюз закрывает /api/agent/admin/*),
            # панель ходит сюда напрямую и отдаёт файл по своему токену.
            eid = _p.rsplit("/", 1)[-1]
            rec = _evidence().get(eid)
            if not rec and re.match(r"^[0-9a-f]{32}$", eid):
                # приложен по адресу, записи о загрузке нет — ищем файл по опознавателю
                hit = [f for f in (os.listdir(EVIDENCE_DIR) if os.path.isdir(EVIDENCE_DIR) else [])
                       if f.startswith(eid + ".")]
                rec = {"file": hit[0], "mime_type": "application/octet-stream"} if hit else None
            path = os.path.join(EVIDENCE_DIR, str((rec or {}).get("file") or "")) if rec else ""
            if not rec or not os.path.isfile(path):
                return send_json(self, 404, {"ok": False, "error": "NO_SUCH_FILE"})
            data = open(path, "rb").read()
            self.send_response(200)
            self.send_header("Content-Type", rec.get("mime_type") or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % rec.get("file"))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)
            return
        if self._restored_get() or self._restored_admin_get():
            return
        if self.path == "/api/agent/weights":
            send_json(self, 200, {"weights": get_weights(),
                                  "core": {"enabled": CORE_V2,
                                           "config_version": (_CORE_CFG or {}).get("config_version"),
                                           "config_sha": ((_CORE_CFG or {}).get("_sha256") or "")[:12],
                                           "error": _CORE_ERR},
                                  "payment_invariant": PAYMENT_INVARIANT,      # §0 dec.10 / §11.3
                                  "release_status": RELEASE_STATUS,            # §1.2 pilot
                                  "pilot_decision_types": PILOT_DECISION_TYPES,
                                  "policy_decisions": ["ALLOW", "REVIEW", "BLOCK"],  # §0 output table
                                  "revalidation_checkpoints": list(_REVAL_CHECKPOINTS),  # §8.2
                                  "reason_codes": ["OK", "POLICY_CHANGED"],    # §8.2
                                  "decision_classes": ["strong_personal_candidate", "usable_personal_candidate",
                                                       "discovery_only", "clarification", "no_personal_outreach"],  # §9.6
                                  "config_ci": (_validate_math_config(_CORE_CFG, _core.FEATURE_KEYS,   # §9.5
                                                                      engine_version=(_CORE_CFG or {}).get("config_version"))
                                                if _CORE_CFG else {"ok": False, "error": _CORE_ERR}),
                                  "readiness_states": list(kcf.READINESS_EXPLAIN.keys()),  # §10.1
                                  "ml_boundary": kmlb.ML_BOUNDARY,             # §10.3
                                  "agent_protocol": {"actions": list(kp.ACTIONS),  # §13.1/§13.2/§13.3
                                                     "protocol_version": kp.PROTOCOL_VERSION,
                                                     "autonomy_boundaries": kp.AUTONOMY_BOUNDARIES}})
        elif self.path == "/api/agent/outcomes":
            send_json(self, 200, dict(_success_metrics(), match_capsules=_match_capsules()))  # §1 + §4.9
        elif self.path.split("?")[0] == "/api/agent/saved_searches":       # §12.2 step 7
            _uid = _own_uid(self)
            if not _uid:
                return send_json(self, 200, {"saved_searches": [], "error": "sign in required"})
            send_json(self, 200, {"saved_searches": _list_saved_searches(_uid)})
        elif self.path == "/api/agent/load":
            send_json(self, 200, {"state": _session("me").get("state")})
        elif self.path == "/api/agent/pool":
            # `bySource` and `store` are not decoration: the admin health bar compares the path the
            # ENGINE reports here against the path the PANEL uses, and that comparison is the only
            # automatic detector of the split-store failure (two services resolving users.json
            # differently, registrations landing in a file the matcher never reads). The rewrite
            # dropped both fields, so the detector had been silently reporting engine=None.
            c = load_candidates()
            src = {}
            for u in c:
                k = str(u.get("source") or "unknown")
                src[k] = src.get(k, 0) + 1
            try:
                st = os.stat(USERS_PATH)
                store = {"path": os.path.abspath(USERS_PATH), "mtime": int(st.st_mtime), "bytes": st.st_size}
            except Exception as e:
                store = {"path": os.path.abspath(USERS_PATH), "error": str(e)[:120]}
            # СПИСОК ОСТАЁТСЯ, ТОЧКА НА КАРТЕ — НЕТ.
            #
            # Здесь отдавалась вся популяция целиком, с точными широтой и долготой каждого
            # человека. Снаружи путь закрыт на nginx, но дверь сервиса не должна держаться на одной
            # строке чужого конфига: запрос, пришедший через шлюз, приходит сюда с того же
            # 127.0.0.1, что и внутренние.
            #
            # Убрать `users` целиком нельзя — его читает первичное наполнение панели
            # администратора и смоук, и оба ходят без токена. Поэтому режется не список, а самое
            # чувствительное в нём: координаты и адрес. Кому положено видеть точку — тот приходит
            # с токеном.
            if kleal_auth.admin_ok(self):
                pool_rows = c
            else:
                _HIDE = ("lat", "lon", "latitude", "longitude", "address", "coords", "geo")
                pool_rows = [{k: v for k, v in (u or {}).items() if k not in _HIDE} for u in c]
            send_json(self, 200, {"count": len(c), "fromStore": _users_cache["list"] is not None,
                                  "bySource": src, "store": store, "users": pool_rows})
        elif self.path.split("?")[0] == "/api/agent/map-feed":
            from urllib.parse import parse_qs, urlsplit
            q = parse_qs(urlsplit(self.path).query)
            view = str((q.get("view") or ["offline"])[0]).strip().lower()
            claimed = str((q.get("self") or [""])[0]).strip()
            # Prefer authenticated identity when available; the query name is compatibility for the
            # current Expo bundle and must never influence location fields.
            me = self._pname or claimed
            try:
                lim = int((q.get("limit") or [60])[0])
            except (TypeError, ValueError):
                lim = 60
            try:
                send_json(self, 200, map_feed_payload(view=view, self_name=me, limit=lim,
                                                      self_id=self._pid))
            except ValueError as e:
                send_json(self, 400, {"error": str(e), "items": [],
                                      "partial": False, "unavailableCount": 0})
        elif self.path.split("?")[0] == "/api/agent/explore":
            q = dict(kv.split("=", 1) for kv in self.path.split("?", 1)[-1].split("&") if "=" in kv) if "?" in self.path else {}
            from urllib.parse import unquote
            send_json(self, 200, {"plans": explore_plans(self_name=unquote(q.get("self", "")),
                                                         self_id=self._pid)})
        elif self.path == "/":
            send_json(self, 200, {"service": "matching", "ok": True})
        else:
            send_json(self, 404, {})

    def _read_one_file(self, max_bytes, err):
        """Общий приём одного файла multipart: тело целиком, потом разбор. None — уже ответили."""
        try:
            ln = int(self.headers.get("Content-Length", "0") or 0)
        except (TypeError, ValueError):
            ln = 0
        if ln <= 0 or ln > max_bytes + 64 * 1024:
            send_json(self, 413, {"ok": False, "error": err + "_TOO_LARGE"})
            return None
        raw = self.rfile.read(ln)
        name, ctype, blob = _one_file(self.headers.get("Content-Type", ""), raw)
        if blob is None:
            send_json(self, 400, {"ok": False, "error": err + "_REQUIRED"})
            return None
        return name, ctype, blob

    def _evidence_upload(self):
        """POST /api/agent/report-evidence — файл к жалобе на группу (multipart, одно поле)."""
        self._whoami({})                       # кто загружает — только по сессии
        if not self._pid:
            return send_json(self, 200, {"ok": False, "error": "sign in required"})
        got = self._read_one_file(MAX_EVIDENCE_BYTES, "EVIDENCE")
        if got is None:
            return
        name, ctype, blob = got
        send_json(self, 200, report_evidence_store(name, ctype, blob, self._pid))

    def _voice_upload(self):
        """POST /api/speech/voice — голосовое файлом; в ответ id, url, длительность, тип и текст."""
        got = self._read_one_file(MAX_VOICE_BYTES, "VOICE")
        if got is None:
            return
        name, ctype, blob = got
        try:
            ms = int(self.headers.get("X-Voice-Duration-Ms", "0") or 0)
        except (TypeError, ValueError):
            ms = 0
        stored = voice_store(name, ctype, blob, ms)
        if not stored.get("ok"):
            return send_json(self, 400, stored)
        text, lang = transcribe_remote(blob, name, ctype)
        stored["transcript"] = text
        stored["language"] = lang
        return send_json(self, 200, stored)

    def _voice_transcribe(self):
        """POST /api/speech/transcribe — надиктовка в поле: только текст, файл не хранится."""
        got = self._read_one_file(MAX_VOICE_BYTES, "VOICE")
        if got is None:
            return
        name, ctype, blob = got
        text, lang = transcribe_remote(blob, name, ctype)
        if not text:
            return send_json(self, 200, {"ok": False, "error": "NO_SPEECH", "text": ""})
        return send_json(self, 200, {"ok": True, "text": text, "language": lang})

    def _voice_serve(self, name):
        """GET /api/agent/voice/<id>.m4a — как кружок: с частичными запросами, иначе iOS не играет."""
        if not VOICE_NAME_RE.match(name):
            return send_json(self, 404, {})
        path = os.path.join(VOICE_DIR, name)
        try:
            size = os.path.getsize(path)
        except OSError:
            return send_json(self, 404, {})
        start, end, partial = 0, size - 1, False
        rm = re.match(r"bytes=(\d*)-(\d*)\s*$", str(self.headers.get("Range") or "").strip())
        if rm:
            a, b = rm.group(1), rm.group(2)
            if a:
                start = min(int(a), size - 1)
                end = min(int(b), size - 1) if b else size - 1
            elif b:
                start = max(0, size - int(b))
            partial = True
        with open(path, "rb") as f:
            f.seek(start)
            chunk = f.read(end - start + 1)
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", VOICE_MIME.get(name.rsplit(".", 1)[-1], "audio/mp4"))
        self.send_header("Content-Length", str(len(chunk)))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Access-Control-Allow-Origin", "*")
        if partial:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(chunk)

    def _video_upload(self):
        """POST /api/agent/video — кружок приезжает файлом, а не в JSON."""
        try:
            ln = int(self.headers.get("Content-Length", "0") or 0)
        except (TypeError, ValueError):
            ln = 0
        if ln <= 0 or ln > MAX_VIDEO_BYTES + 64 * 1024:
            return send_json(self, 413, {"ok": False, "error": "VIDEO_TOO_LARGE"})
        raw = self.rfile.read(ln)
        try:
            ms = int(self.headers.get("X-Video-Duration-Ms", "0") or 0)
        except (TypeError, ValueError):
            ms = 0
        name, ctype, blob = _one_file(self.headers.get("Content-Type", ""), raw)
        if blob is None:
            return send_json(self, 400, {"ok": False, "error": "VIDEO_REQUIRED"})
        return send_json(self, 200, video_store(name, ctype, blob, ms))

    def _video_serve(self, name):
        """GET /api/agent/video/<id>.mp4 — с поддержкой ЧАСТИЧНЫХ запросов.

        Проигрыватель просит файл кусками и без 206 не откроет его вовсе. Полный ответ тоже
        остаётся: без заголовка `Range` отдаём файл целиком, как обычно."""
        if not VIDEO_NAME_RE.match(name):
            return send_json(self, 404, {})
        path = os.path.join(VIDEO_DIR, name)
        try:
            size = os.path.getsize(path)
        except OSError:
            return send_json(self, 404, {})
        start, end, partial = 0, size - 1, False
        rm = re.match(r"bytes=(\d*)-(\d*)\s*$", str(self.headers.get("Range") or "").strip())
        if rm:
            a, b = rm.group(1), rm.group(2)
            if a:
                start = min(int(a), size - 1)
                end = min(int(b), size - 1) if b else size - 1
            elif b:                                   # bytes=-500 — последние 500 байт
                start = max(0, size - int(b))
            partial = True
        if start > end:
            return send_json(self, 416, {"ok": False, "error": "BAD_RANGE"})
        with open(path, "rb") as f:
            f.seek(start)
            chunk = f.read(end - start + 1)
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", "video/quicktime" if name.endswith(".mov") else "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(chunk)))
        if partial:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        # Файл неизменен по своему имени: имя — это его хеш, и второй раз он не понадобится.
        self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(chunk)

    def do_POST(self):
        # Кружок приезжает multipart'ом, и разбирать его как JSON нельзя: read_json прочитает
        # тело до конца, и до файла дело уже не дойдёт.
        if self.path.split("?", 1)[0] == "/api/agent/video":
            return self._video_upload()
        # Голосовое — тоже multipart, и тоже до read_json: см. объяснение выше.
        if self.path.split("?", 1)[0] == "/api/speech/voice":
            return self._voice_upload()
        if self.path.split("?", 1)[0] == "/api/speech/transcribe":
            return self._voice_transcribe()
        if self.path.split("?", 1)[0] == "/api/agent/report-evidence":
            return self._evidence_upload()
        body = read_json(self)
        self._watch_owner(body)
        self._whoami(body)
        p = self.path
        if self._restored_post(p, body) or self._restored_admin_post(p, body):
            return
        if p == "/api/agent/plan":
            q = str(body.get("query") or "")
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            ctx = body.get("ctx") if isinstance(body.get("ctx"), dict) else {}
            override = body.get("override") if isinstance(body.get("override"), dict) else None
            try:
                send_json(self, 200, agent_plan(q, prof, ctx, override))
            except Exception as e:
                send_json(self, 200, {"intent": _fallback_parse(q), "candidates": [], "error": str(e)[:200]})
        elif p == "/api/agent/explore":
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            send_json(self, 200, {"plans": explore_plans(
                limit=int(body.get("limit") or 12),
                self_name=body.get("self") or prof.get("name") or "",
                viewer_profile=prof,
                self_id=self._pid,
            )})
        elif p == "/api/agent/match":
            # structured entry: caller (e.g. the buddy agent) already assembled the intent/signals -> skip LLM parse
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            ctx = body.get("ctx") if isinstance(body.get("ctx"), dict) else {}
            # ЧЕЛОВЕЧЕСКАЯ ФРАЗА ради моста тем. Приложение шлёт её отдельным полем `phrase`:
            # в `topics` ей нельзя (русская строка буквально не совпадает ни с кем), а без неё
            # фильтрация разбирает голое «options» как «варианты выбора», а не как опционы.
            # Ставится ПОСЛЕ compile_intent — тот собирает свою структуру и чужих ключей не носит.
            _phrase = str(intent.get("phrase") or body.get("query") or "")
            try:
                intent = kc.compile_intent(intent, _intent_identity(intent), ctx, ctx.get('now') or time.time())  # §4.3 blocks
                if _phrase:
                    intent["_query"] = _phrase
                snap = _request_snapshot(intent)
                if not _pilot_enabled(intent):             # §1.2: a non-pilot decision type
                    # ...but STILL rank the people. Returning an empty slate here meant that adding
                    # `groupSize` to a request that found eight people found nobody, with the reason
                    # buried in a `pilot` field the UI never showed. The layer being off is a reason
                    # not to ASSEMBLE a group — never a reason to hide the people who fit.
                    ppl = match_candidates(dict(intent, groupSize=None, group=None,
                                                decisionType="person_to_person"), prof, ctx)
                    send_json(self, 200, {"intent": intent, "candidates": ppl, "snapshot": snap,
                                          "pilot": {"enabled": False, "decision_type": snap["decision_type"],
                                                    "note": "%s is not enabled in this pilot (%s)"
                                                            % (snap["decision_type"], RELEASE_STATUS),
                                                    "people_shown_anyway": len(ppl)}}); return
                # `limit` — сколько человек показать. Просим на одного БОЛЬШЕ и по нему же решаем,
                # есть ли продолжение: иначе кнопка «показать ещё» осталась бы вечной, и человек
                # снова жал бы её впустую — ровно та поломка, из-за которой всё это и правится.
                _lim = 0
                try:
                    _lim = int(body.get("limit") or 0)
                except (TypeError, ValueError):
                    _lim = 0
                _lim = max(0, min(48, _lim))
                cands = match_candidates(intent, prof, ctx, want=(_lim + 1) if _lim else None)
                res = {"intent": intent, "candidates": cands, "snapshot": snap}
                if _lim:
                    res["has_more"] = len(cands) > _lim
                    res["candidates"] = cands = cands[:_lim]
                    res["shown"] = len(cands)
                _lng = str(body.get("lang") or "").lower()
                if _lng in ("ru", "es") and cands:
                    try:
                        import interest_i18n as _ii
                        _iw = sorted({str(w) for c in cands for w in (c.get("interests") or [])})
                        res["interestLabels"] = _ii.labels_for(_iw, _lng)
                    except Exception:
                        pass
                res.update(_section5_addendum(intent, str(body.get("query") or ""), cands))  # §5.1/§5.2
                res["retrieval"] = _retrieval_report(cands)                                    # §7
                res["expansion"] = expansion_ladder(intent, ctx)                               # §12
                if snap["decision_type"] == "group_formation":     # §15: the slate becomes a group
                    res["group"] = form_group_from_slate(intent, cands,
                                                         body.get("constraints") if isinstance(body.get("constraints"), dict) else None,
                                                         now_ts=ctx.get("now"))
                if not cands:
                    res["fallback"] = _online_fallback(intent)
                    if kc.is_expired(intent, ctx.get('now')):     # §4.3 Lifecycle: distinguish expired from no-match
                        res["expired"] = True
                send_json(self, 200, res)
            except Exception as e:
                _blew_up("/api/agent/match", e)
                send_json(self, 200, {"intent": intent, "candidates": [], "error": str(e)[:200]})
        elif p == "/api/agent/confirm":
            # §5.1 confirmation flow: promote ONLY the confirmed sensitive constraints (required language,
            # dating mode) into active gates, then re-match. Unconfirmed constraints stay soft/absent.
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            ctx = body.get("ctx") if isinstance(body.get("ctx"), dict) else {}
            confirmed_ids = body.get("confirmed_ids") if isinstance(body.get("confirmed_ids"), list) else []
            query = str(body.get("query") or "")
            try:
                cons = body.get("constraints") if isinstance(body.get("constraints"), list) \
                    else ki.extract_constraints(query, intent)[1]
                conf = ki.apply_confirmation(intent, confirmed_ids, cons, now=ctx.get("now"))
                conf = kc.compile_intent(conf, _intent_identity(conf), ctx, ctx.get("now") or time.time())
                # Исходная фраза едет с интентом ради моста тем: по ней фильтрация отличает
                # «опционы» от «вариантов», а по скомпилированному слову — уже нет. Приложение
                # шлёт её отдельным полем `phrase`, а не в `query`: `query` идёт ещё и в разбор
                # ограничений, и человеческая подпись добавила бы туда условий, которых человек
                # не ставил.
                _ph = str((body.get("intent") or {}).get("phrase") or query or "")
                if _ph:
                    conf["_query"] = _ph
                cands = match_candidates(conf, prof, ctx)
                res = {"intent": conf, "candidates": cands, "snapshot": _request_snapshot(conf),
                       "confirmed": conf.get("_confirmed")}
                res.update(_section5_addendum(conf, query, cands))
                res["expansion"] = expansion_ladder(conf, ctx)   # §12 controlled-expansion ladder (plan)
                if not cands:
                    res["fallback"] = _online_fallback(conf)      # §12 never dead-end even after a narrowing confirm
                send_json(self, 200, res)
            except Exception as e:
                _blew_up("/api/agent/confirm", e)
                send_json(self, 200, {"intent": intent, "candidates": [], "error": str(e)[:200]})
        elif p == "/api/agent/explain":
            # TWO tools under one name, chosen by whether a `candidate` is named:
            #   with candidate -> the per-pair decision trace (§21.3), «почему мне не попадается X»;
            #   without        -> the slate-wide diagnostic (matched + gated-out + per-feature).
            # The rewrite kept only the second, so the admin pair view silently got a slate dump and
            # found no trace in it. Both are real tools; neither is a rename of the other.
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            ctx = body.get("ctx") if isinstance(body.get("ctx"), dict) else {}
            who = str(body.get("candidate") or "").strip().lower()
            if not who:
                try:
                    send_json(self, 200, explain_match(intent, prof, ctx))
                except Exception as e:
                    send_json(self, 200, {"error": str(e)[:200], "matched": [], "excluded": [], "considered": []})
                return
            try:
                # Кандидат — по id, если панель его прислала; по подписи — только если она однозначна.
                _cid = str(body.get("candidate_id") or "").strip()
                if _cid:
                    cand = _person(_cid)
                else:
                    _same = [c for c in load_candidates() if str(c.get("name", "")).strip().lower() == who]
                    cand = _same[0] if len(_same) == 1 else None
                if cand is None:
                    send_json(self, 200, {"ok": False, "error": "candidate not found in store"})
                elif not CORE_V2:
                    send_json(self, 200, {"ok": False, "error": "core v2 disabled (KLEAL_CORE_V2=0)"})
                else:
                    gate_ctx, self_name = _gate_ctx_and_self(ctx, prof)
                    ctx2 = dict(ctx)
                    ctx2.setdefault("now", time.time())
                    ctx2.setdefault("received24", _proposals_received_24h())
                    if _is_self(cand, gate_ctx.get("self_id") or "", self_name):
                        send_json(self, 200, {"ok": True, "trace": {
                            "name": cand.get("name"), "shown": False, "steps": [
                                {"step": "self-match guard", "ok": False,
                                 "detail": "the searcher is never matched to themselves"}],
                            "drop_reason": "self-match: searcher == candidate"}})
                    else:
                        decision, why = _policy_decision(intent, cand, gate_ctx)
                        if decision == "BLOCK":
                            send_json(self, 200, {"ok": True, "trace": {
                                "name": cand.get("name"), "shown": False, "steps": [
                                    {"step": "eligibility hard gates", "ok": False, "detail": why}],
                                "drop_reason": "blocked by policy: %s" % why}})
                        else:
                            with _matching_topic_context(intent) as effective:
                                tr = _core.explain(effective, prof, ctx2, cand, _H, _CORE_CFG)
                            tr["steps"].insert(0, {"step": "eligibility hard gates", "ok": True,
                                                   "detail": decision})
                            send_json(self, 200, {"ok": True, "trace": tr})
            except Exception as e:
                send_json(self, 200, {"ok": False, "error": str(e)[:200]})
        elif p == "/api/agent/feedback":
            _uid = _own_uid(self)
            if not _uid:
                return send_json(self, 200, {"ok": False, "error": "sign in required"})

            def _do_feedback():                                # §23.2.13 idempotent write (opt-in idempotency_key)
                ok = record_feedback(body.get("name"), body.get("decision"), _uid,
                                     purpose=body.get("purpose"))   # §17.2 optional mode-scoped feedback (dating isolation)
                # Читаем ОТТУДА ЖЕ, куда писали. Раньше запись шла в `uid`, а ответ отдавал общую
                # корзину "me": человек ставил оценку и получал обратно чужие.
                return {"ok": bool(ok), "feedback": _session(_uid).get("feedback")}
            send_json(self, 200, _idempotent(body.get("idempotency_key"), "feedback",
                                             body.get("name"), body.get("decision"), _do_feedback))
        elif p == "/api/agent/outcome":
            # §1 success lifecycle: record proposed/accepted/declined/completed/expired_no_response.
            # §14 idempotency: if the caller passes an idempotency_key, a REPLAY of the same key returns the
            # prior metrics (error_code DUPLICATE) instead of double-appending. Without a key -> unchanged append.
            idem = body.get("idempotency_key")
            key = ks.dedup_key("outcome", body.get("name"), body.get("stage"), extra=idem) if idem else None
            with _STORE_LOCK:                          # §14: check + record + memoize ATOMICALLY (RLock -> _record_outcome
                prior = (SESSION.get("_outcome_seen") or {}).get(key) if key else None   # re-enters safely). One lock closes
                if prior is not None:                  # the read-then-write gap so a concurrent replay can't double-append.
                    payload = dict(prior, duplicate=True, error_code="DUPLICATE")
                else:
                    ok = _record_outcome(body.get("name"), body.get("stage"), _own_uid(self) or "me")
                    payload = {"ok": bool(ok), "stages": list(_OUTCOME_STAGES),
                               "metrics": _success_metrics(), "match_capsules": _match_capsules()}
                    if key and ok:                     # memoize only a real applied outcome (a failed record can retry)
                        SESSION.setdefault("_outcome_seen", {})[key] = payload; _save_store()
            send_json(self, 200, payload)              # network I/O outside the lock
        elif p == "/api/agent/transition":
            # §14 validated state transition (WITHDRAW/EXPIRE/COUNTER/...): edge check + optimistic CAS +
            # idempotent replay. Under the reentrant store lock; appends an immutable audit trace on success.
            try:
                send_json(self, 200, agent_transition(body if isinstance(body, dict) else {}))
            except Exception as e:
                send_json(self, 200, {"ok": False, "error_code": "ILLEGAL_TRANSITION", "error": str(e)[:200]})
        elif p == "/api/agent/group":
            # §15 group formation — PILOT-DISABLED scaffolding. Returns enabled:False unless the EXACT test-only
            # override {'enable_group_formation': True} is present. NEVER flips PILOT_DECISION_TYPES and NEVER
            # touches the person-to-person slate (kg is a separate keyless module). Config-derived weights;
            # the last-seat capacity race reuses §14 (ks.claim_slot) via a SESSION-backed seat ledger.
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            cands = body.get("candidates") if isinstance(body.get("candidates"), list) else []
            constraints = body.get("constraints") if isinstance(body.get("constraints"), dict) else {}
            override = body.get("override")
            if GROUPS_ENABLED and not kg.is_override_enabled(override):
                override = _GROUP_OVERRIDE      # the product switch decides, not the request body
            if not cands:
                # §15 forms a group out of a slate it is GIVEN; it never retrieves. An empty body
                # therefore answered NO_FEASIBLE_GROUP, which reads as the algorithm rejecting the
                # request when it had simply been handed nobody. Rank first, then form.
                prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
                ctx = body.get("ctx") if isinstance(body.get("ctx"), dict) else {}
                try:
                    cands = match_candidates(intent, prof, ctx)
                except Exception:
                    cands = []
            cands = _group_slate(cands)               # lcb -> relevance, the §15 star-fallback input
            constraints = _group_constraints(intent, constraints)   # groupSize + §15.4 pack -> seat counts
            reserve = bool(body.get("reserve"))       # claiming seats is a commit, never a preview
            try:
                if kg.is_override_enabled(override) and reserve:   # real seat ledger + reservations
                    with _STORE_LOCK:
                        led = SESSION.setdefault("_group_ledger", {})
                        res = dict(kg.run_group_formation(intent, cands, constraints, _CORE_CFG, override=override,
                                                          now_ts=body.get("now") or time.time(), ledger=led,
                                                          pair_rel=body.get("pair_rel")),
                                   group_formation_live=GROUPS_ENABLED, reserved=True)
                        _save_store()
                elif kg.is_override_enabled(override):
                    res = dict(kg.run_group_formation(intent, cands, constraints, _CORE_CFG,
                                                      override=override, now_ts=body.get("now") or time.time(),
                                                      ledger=None, pair_rel=body.get("pair_rel")),
                               group_formation_live=GROUPS_ENABLED, reserved=False)
                else:
                    res = kg.run_group_formation(intent, cands, constraints, _CORE_CFG, override=override)
                send_json(self, 200, res)
            except Exception as e:
                send_json(self, 200, dict(kg.dormant_response(intent, constraints), error=str(e)[:200]))
        elif p in ("/api/agent/event", "/api/agent/room", "/api/agent/venue"):
            # §16 events/rooms/venues — PILOT-DISABLED scaffolding, DISTINCT per-kind path (event != user-with-
            # capacity). Returns enabled:False unless the EXACT override {'enable_intent_to_<kind>': True}. NEVER
            # flips PILOT_DECISION_TYPES; NEVER touches the person slate. Read-only ranking (no reservation side-
            # effect); cfg is accepted but never influences a score (§16 ranking is module-local, not config-derived).
            kind = p.rsplit("/", 1)[-1]
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            objects = (body.get("objects") if isinstance(body.get("objects"), list)
                       else body.get("candidates") if isinstance(body.get("candidates"), list) else [])
            user = (body.get("user") if isinstance(body.get("user"), dict)
                    else body.get("profile") if isinstance(body.get("profile"), dict) else {})
            try:
                send_json(self, 200, kct.run_candidates(kind, intent, objects, user, cfg=_CORE_CFG,
                                                        override=body.get("override"),
                                                        now_ts=body.get("now") or time.time()))
            except Exception as e:
                send_json(self, 200, dict(kct.dormant_response(kind, intent), error=str(e)[:200]))
        elif p == "/api/agent/save_search":
            # §12.2 step 7: persist a search to notify later (SESSION only; no users.json writer).
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            _uid = _own_uid(self)
            if not _uid:
                return send_json(self, 200, {"ok": False, "error": "sign in required"})
            send_json(self, 200, {"id": _save_search(intent, _uid),
                                  "saved_searches": _list_saved_searches(_uid)})
        elif p == "/api/agent/save_search/check":
            prof = body.get("profile") if isinstance(body.get("profile"), dict) else {}
            _uid = _own_uid(self)
            if not _uid:
                return send_json(self, 200, {"checked": [], "error": "sign in required"})
            send_json(self, 200, {"checked": _check_saved_searches(prof, _uid)})
        elif p == "/api/agent/save_search/delete":
            _uid = _own_uid(self)
            if not _uid:
                return send_json(self, 200, {"ok": False, "error": "sign in required"})
            send_json(self, 200, {"deleted": _delete_saved_search(body.get("id"), _uid),
                                  "saved_searches": _list_saved_searches(_uid)})
        elif p == "/api/agent/revalidate":
            # §8.2 #3-#7: re-decide a pair against the live store at a checkpoint; POLICY_CHANGED if stricter.
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            cand = body.get("candidate") if isinstance(body.get("candidate"), dict) else {}
            checkpoint = str(body.get("checkpoint") or "profile_open")
            try:
                send_json(self, 200, revalidate(intent, cand, checkpoint, body.get("now")))
            except Exception as e:
                send_json(self, 200, {"decision": "ALLOW", "code": "OK", "error": str(e)[:200]})
        elif p == "/api/agent/weights":
            send_json(self, 200, {"weights": set_weights(body.get("weights") if isinstance(body.get("weights"), dict) else body)})
        elif p == "/api/agent/save":
            u = _session("me"); u["state"] = body.get("state"); _save_store()
            send_json(self, 200, {"ok": True})
        elif p == "/api/agent/intro":
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            cand = body.get("candidate") if isinstance(body.get("candidate"), dict) else {}
            try:
                send_json(self, 200, agent_intro(intent, cand))
            except Exception as e:
                send_json(self, 200, {"reply": "", "opener": "Hey! Want to make a plan?", "error": str(e)[:200]})
        elif p == "/api/agent/negotiate":
            intent = body.get("intent") if isinstance(body.get("intent"), dict) else {}
            cands = body.get("candidates") if isinstance(body.get("candidates"), list) else []
            # §22.2.3/§23.2.13 controlled proposals: a re-send of the SAME (intent, candidate set) is idempotent —
            # memoized so it never double-emits proposals. Content-keyed (intent id + sorted names).
            _iid = (intent.get("identity") or {}).get("intent_id") or intent.get("title") or ",".join(intent.get("topics") or [])
            _names = ",".join(sorted(str(c.get("name")) for c in cands if isinstance(c, dict)))
            def _do_negotiate():
                try:
                    return {"candidates": negotiate_candidates(intent, cands)}
                except Exception as e:
                    return {"candidates": cands, "error": str(e)[:200]}
            send_json(self, 200, _idempotent(body.get("idempotency_key") or ("auto:%s" % _iid),
                                             "negotiate", _names, "send", _do_negotiate))
        elif p == "/api/agent/proposal":
            try: send_json(self, 200, proposal_create(body if isinstance(body, dict) else {}))
            except Exception as e: send_json(self, 200, {"error": str(e)[:200]})
        elif p == "/api/agent/proposal/respond":
            try: send_json(self, 200, proposal_respond(body if isinstance(body, dict) else {}))
            except Exception as e: send_json(self, 200, {"ok": False, "error": str(e)[:200]})
        elif p == "/api/agent/plan_resource":
            try: send_json(self, 200, plan_resource(body if isinstance(body, dict) else {}))
            except Exception as e: send_json(self, 200, {"ok": False, "error": str(e)[:200]})
        elif p == "/api/agent/intents/compile":
            try: send_json(self, 200, compile_endpoint(body if isinstance(body, dict) else {}))
            except Exception as e: send_json(self, 200, {"intent": {}, "error": str(e)[:200]})
        elif p == "/api/agent/expand":
            try: send_json(self, 200, expand_one_axis(body if isinstance(body, dict) else {}))
            except Exception as e: send_json(self, 200, {"candidates": [], "error": str(e)[:200]})
        else:
            send_json(self, 404, {})

    def log_message(self, *a):
        pass


# Панели нужен список ВСЕХ инструкций сервиса, а не только тех, что успели
# прочитаться. Объявляем их при старте: ни одного обращения к модели это не стоит,
# зато промпт виден в панели сразу после перезапуска, а не после первого разговора.
try:
    settings.announce([
        ("matching.parse_intent", PARSE_PROMPT),
        ("matching.intro", INTRO_PROMPT),
        ("matching.negotiate", NEGOTIATE_PROMPT),
    ])
except Exception:
    pass


def _warm_up():
    """Один холостой поиск при старте — чтобы первым его ждала служба, а не человек.

    Память на ответы (`cat_of`, `canonical._resolve`) наполняется словами СТОРА, и наполняет её
    первый же настоящий поиск: он и платит за всех. Замер 15.09.2026 на боевой службе: первый
    запрос после перезапуска — 17,5 с, следующий — 1,5 с. Человеку, зашедшему сразу после
    выкладки, доставалась ровно та секунда, за которую он решает, работает приложение или нет.

    Идёт в отдельном потоке и молча: ошибка прогрева не должна мешать службе подняться. Ничего
    не пишет — поиск состояние не трогает (журнал показов ведётся при отправке, а не при выдаче)."""
    try:
        t0 = time.time()
        pool = load_candidates()
        me = next((u for u in pool if u.get("lat") and u.get("interests")), None) or {}
        prof = {"name": "", "lat": me.get("lat"), "lon": me.get("lon"),
                "languages": {"comfortable": me.get("langs") or []}}
        match_candidates({"topics": ["кофе"], "type": "social", "role": "meet",
                          "mode": "offline", "time": "Today evening"}, prof, {"self": ""})
        print("[warm] словарь прогрет за %.1f с, карточек %d" % (time.time() - t0, len(pool)), flush=True)
    except Exception as e:
        print("[warm] прогрев не удался: %s" % str(e)[:120], flush=True)


if __name__ == "__main__":
    print("Kleal matching-service on http://127.0.0.1:%d  (LLM via llm-service)" % PORT)
    # Перевод хранилища на id — ДО приёма запросов: иначе первые ответы шли бы по старым именам.
    try:
        _migrate_identity_v2(apply=True)
    except Exception as _e:
        print("[identity] перевод на id не выполнен: %s" % str(_e)[:200], flush=True)
        traceback.print_exc()
    threading.Thread(target=_warm_up, daemon=True).start()
    import serving  # очередь подключений на 128, а не на 5 — см. shared/serving.py
    serving.KlealServer(("127.0.0.1", PORT), H).serve_forever()
