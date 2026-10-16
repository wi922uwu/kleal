# -*- coding: utf-8 -*-
"""Батарея Бадди: имена, затеи, записанное и момент создания — на трёх языках.

    python3 tools/buddy_battery.py [адрес] [файл-журнала]

ЧТО ЭТО. Живые сценарии через настоящие ручки — мастер затеи (`/api/buddy/intent-build`) и разговор
(`/api/buddy/chat`). Полный ход каждого разговора пишется в журнал, в вывод идут только таблица и
найденные беды.

ДВА ПРАВИЛА ИЗМЕРИТЕЛЯ, оба оплачены ошибками:
  1. Проверять ПРЕДМЕТ, а не строку целиком. Первая батарея метила «Talk about smart contracts» как
     мусор — из-за слова «talk», которое здесь НАШ глагол, а не предмет человека.
  2. Не заимствовать правила у измеряемого. Признак намерения здесь свой: измеритель, взявший
     правила из кода сборщика, согласится с ним по построению и не найдёт ничего.
"""
import json
import os
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7080").rstrip("/")
LOG = sys.argv[2] if len(sys.argv) > 2 else "/root/kleal-archive/buddy-battery-%s.log" % time.strftime("%Y%m%d_%H%M%S")
_log = open(LOG, "w", encoding="utf-8")
_LOCK = threading.Lock()

# ПАРАЛЛЕЛЬНО, А НЕ ПО ОЧЕРЕДИ. Разговоры между собой не связаны, и гонять их по одному значит
# мерить не продукт, а собственное терпение: круг из тридцати сценариев шёл две минуты, из тысячи
# шёл бы час. Потоки заодно дают то, ради чего всё и затевалось — настоящую нагрузку на модель:
# восемь одновременных разговоров это восемь живых людей в приложении.
WORKERS = int(os.environ.get("KLEAL_BATTERY_WORKERS", "8"))
# Сколько сценариев в круге. Пул большой, гонять его целиком каждый раз незачем — берём выборку,
# и за несколько кругов проходит весь.
BATCH = int(os.environ.get("KLEAL_BATTERY_BATCH", "60"))
POOL_FILE = "/root/kleal-archive/scenarios.jsonl"
# Живой поток событий для админки: кольцо на последние N записей, каждая — одна строка JSON.
LIVE = "/root/kleal-archive/battery-live.jsonl"
LIVE_KEEP = 7000


def w(line=""):
    with _LOCK:
        _log.write(line + "\n")
        _log.flush()


# НОМЕР ПОТОКА. Панель раскладывает прогон по дорожкам — одна дорожка на поток, — и без номера
# это невозможно: имя системного потока («ThreadPoolExecutor-0_7») меняется от запуска к запуску и
# ничего не говорит глазу. Заводим свою нумерацию по первому появлению.
_THREADS, _THREAD_LOCK = {}, threading.Lock()


def thread_no():
    tid = threading.current_thread().ident
    with _THREAD_LOCK:
        if tid not in _THREADS:
            _THREADS[tid] = len(_THREADS) + 1
        return _THREADS[tid]


def live(kind, scen="", lang="", text="", extra=None):
    """Событие в живой поток: его читает админка и показывает как есть, без задержки."""
    row = {"t": time.time(), "kind": kind, "scen": scen, "lang": lang, "text": str(text)[:400],
           "w": thread_no()}
    if extra:
        row.update(extra)
    try:
        with _LOCK:
            with open(LIVE, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


# Время каждого вызова и сбои — это и есть «как модель держит нагрузку». Считаем их здесь, в одном
# месте, а не в сценариях: любой вызов, откуда бы он ни шёл, попадает в общий счёт.
TIMES, ERRORS = [], []


def post(path, body, timeout=240):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            out = json.loads(r.read().decode() or "{}")
        with _LOCK:
            TIMES.append(time.time() - t0)
        return out
    except Exception as e:
        with _LOCK:
            TIMES.append(time.time() - t0)
            ERRORS.append(str(e)[:80])
        return {"__error": str(e)[:120]}


def quantile(xs, q):
    if not xs:
        return 0.0
    ys = sorted(xs)
    return ys[min(len(ys) - 1, int(round(q * (len(ys) - 1))))]


CYR = re.compile(r"[а-яёА-ЯЁ]")
LAT = re.compile(r"[a-zA-Z]")
WORD = re.compile(r"[^\W\d_]{3,}", re.U)

# Затея без предмета: глагол есть, а чего именно — нет.
BARE = {"ru": {"поговорить", "встретиться", "пообщаться", "погулять вместе", "поиграть вместе", "сходить куда-нибудь"},
        "en": {"have a chat", "a chat", "meet up", "hang out", "play together", "go somewhere"},
        "es": {"charlar", "charla", "quedar", "vernos", "jugar juntos", "salir"}}
# Слова, которые не называют занятие. Проверяются ТОЛЬКО на предмете, не на глаголе.
JUNK = {"talk", "chat", "conversation", "year", "girl", "boy", "need", "over", "smart", "work",
        "listen", "moms", "kids", "people", "company", "socializing", "thing", "things", "stuff",
        "разговор", "общение", "встреча", "компании", "компания", "год", "человек", "люди", "штука"}
# Имена собственные — латиница в русской фразе для них законна.
PROPER = re.compile(r"(?:^|\s)(?:[A-Z][a-z]+|[A-Z]{2,}|\w*[a-z]\w*[A-Z]\w*)")

_WISH = re.compile(
    r"(?iu)(?:^|[\s,])(?:хочу|хочется|хотел|давай|пойдём|пошли|ищу|люблю|обожаю|мечтаю|собираюсь|"
    r"i\s+want|i\s+wanna|i'?d\s+like|i\s+love|let'?s|looking\s+for|i\s+need|"
    r"quiero|quisiera|busco|me\s+encanta|me\s+gustar|necesito)(?:\s|$)"
    # «про кино», «about crypto», «sobre música» — предмет назван прямо, и это просьба, а не ответ
    # на наш вопрос. Без этого батарея метила верные имена: человек путано рассказывал, потом
    # сказал «про кино» — и «Поговорить про кино» попадало в беды.
    r"|(?:^|[\s,])(?:про|обо|об|about|sobre)\s+\S")

PROF = {"ru": {"name": "Иван", "age": 30, "area": "Barcelona", "langs": ["ru"]},
        "en": {"name": "John", "age": 30, "area": "Barcelona", "langs": ["en"]},
        "es": {"name": "Juan", "age": 30, "area": "Barcelona", "langs": ["es"]}}

# СЦЕНАРИИ. Прежние были учебные — «хочу поиграть в падель в субботу», — и на них всё сходилось
# просто потому, что человек назвал занятие первым же словом. Живые разговоры так не идут: человек
# начинает с настроения, передумывает на середине, ставит условие после согласия, спрашивает
# вопросом вместо просьбы. Поэтому каждый сценарий — несколько ходов, а проверяется ТО, ЧЕМ
# РАЗГОВОР КОНЧИЛСЯ, а не то, что в нём мелькало.
#
#   says   — реплики человека по порядку;
#   expect — про что должна быть затея в итоге (хватает одного совпадения);
#   never  — чего в ней быть не должно: отвергнутое, промежуточное, чужое.
SCEN = [
    # ── КОНТРОЛЬНАЯ ГРУППА: простые просьбы. Нужны, чтобы отличить «стало хуже вообще» от
    #    «не вывозит сложное»: если ломается здесь, дело не в трудности сценария.
    {"label": "контроль-точная", "lang": "ru", "says": ["хочу поиграть в падель в субботу", "я новичок"],
     "expect": ["падел"], "never": ["новичок", "суббот"]},
    {"label": "контроль-описка", "lang": "ru", "says": ["хочу поиграть в тенис", "по вечерам"],
     "expect": ["теннис"], "never": ["вечер"]},
    {"label": "control-exact", "lang": "en", "says": ["i want to play padel on saturday", "i'm a beginner"],
     "expect": ["padel"], "never": ["beginner", "saturday"]},
    {"label": "control-exacta", "lang": "es", "says": ["quiero jugar al pádel el sábado", "soy principiante"],
     "expect": ["padel", "pádel"], "never": ["principiante", "sábado"]},

    # ── НАСТРОЕНИЕ ВМЕСТО ПРОСЬБЫ: человек называет состояние, занятие появляется к третьему ходу.
    {"label": "скука-к-делу", "lang": "ru",
     "says": ["скучно", "не знаю, что-нибудь на воздухе", "только не бегать", "давай тогда на велике"],
     "expect": ["велик", "велосипед", "cycl"], "never": ["бег", "бегать"]},
    {"label": "намёк", "lang": "ru",
     "says": ["надоело сидеть дома", "да, выбраться куда-нибудь", "можно на выставку"],
     "expect": ["выставк", "exhibit"], "never": ["дом"]},
    {"label": "эмоция", "lang": "ru",
     "says": ["хреново после расставания", "хочу отвлечься", "может сходить на концерт"],
     "expect": ["концерт"], "never": ["расстава"]},
    {"label": "bored-to-plan", "lang": "en",
     "says": ["i'm bored", "something outdoors maybe", "not running though", "cycling then"],
     "expect": ["cycl", "bike"], "never": ["running", "bored"]},
    {"label": "emotional", "lang": "en",
     "says": ["feeling rough after a breakup", "want a distraction", "maybe a concert"],
     "expect": ["concert"], "never": ["breakup"]},
    {"label": "aburrido", "lang": "es",
     "says": ["estoy aburrido", "algo al aire libre", "correr no", "entonces en bici"],
     "expect": ["bici", "ciclis"], "never": ["correr", "aburrid"]},

    # ── ПЕРЕДУМАЛ ПОСРЕДИ РАЗГОВОРА: первое занятие названо прямо и потом отменено.
    {"label": "передумал-дважды", "lang": "ru",
     "says": ["хочу в кино", "хотя нет, лучше просто поговорить", "про архитектуру", "да, давай"],
     "expect": ["архитект"], "never": ["кино"]},
    {"label": "два-варианта", "lang": "ru",
     "says": ["или бег, или кофе, не решил", "давай кофе", "утром"],
     "expect": ["кофе"], "never": ["бег"]},
    {"label": "twice-changed", "lang": "en",
     "says": ["let's watch a movie", "actually no, let's just talk", "about architecture", "yes"],
     "expect": ["architect"], "never": ["movie", "film"]},
    {"label": "cambio-doble", "lang": "es",
     "says": ["vamos al cine", "no, mejor hablamos", "de arquitectura", "sí"],
     "expect": ["arquitect"], "never": ["cine"]},

    # ── УСЛОВИЕ ПОСЛЕ СОГЛАСИЯ: занятие названо, потом ограничение, и оно меняет занятие.
    {"label": "условие-потом", "lang": "ru",
     "says": ["хочу в бар", "только без алкоголя", "тогда в кафе"],
     "expect": ["кафе", "cafe"], "never": ["алкогол"]},
    {"label": "constraint-later", "lang": "en",
     "says": ["i want to go to a bar", "no alcohol though", "a cafe works"],
     "expect": ["cafe", "coffee"], "never": ["alcohol"]},
    {"label": "condicion", "lang": "es",
     "says": ["quiero ir a un bar", "pero sin alcohol", "un café vale"],
     "expect": ["café", "cafe"], "never": ["alcohol"]},

    # ── ВОПРОСОМ ВМЕСТО ПРОСЬБЫ: человек спрашивает, есть ли такие люди.
    {"label": "вопросом", "lang": "ru",
     "says": ["а есть тут кто в шахматы играет?", "да, хочу партию", "онлайн"],
     "expect": ["шахмат"], "never": []},
    {"label": "question-first", "lang": "en",
     "says": ["anyone here into chess?", "yeah i want a game", "online"],
     "expect": ["chess"], "never": []},
    {"label": "pregunta", "lang": "es",
     "says": ["¿alguien juega al ajedrez?", "sí, quiero una partida", "en línea"],
     "expect": ["ajedrez"], "never": []},

    # ── СЛИШКОМ МНОГО СРАЗУ: четыре занятия в одной реплике, выбор — во второй.
    {"label": "слишком-много", "lang": "ru",
     "says": ["люблю бег, кофе, настолки и ещё языки учу", "давай про настолки", "в компании"],
     "expect": ["настолк", "board"], "never": ["язык", "бег"]},
    {"label": "too-much", "lang": "en",
     "says": ["i run, drink coffee, play board games and learn languages", "board games please", "in a group"],
     "expect": ["board", "game"], "never": ["language", "running"]},
    {"label": "demasiado", "lang": "es",
     "says": ["corro, tomo café, juego a juegos de mesa y aprendo idiomas", "juegos de mesa", "en grupo"],
     "expect": ["mesa", "board"], "never": ["idioma", "correr"]},

    # ── СЛЕНГ И ОПИСКИ: так пишут в жизни.
    {"label": "сленг", "lang": "ru",
     "says": ["го покекать в доту", "вечером", "рейтинг не важен"],
     "expect": ["дот", "dota"], "never": ["покек", "рейтинг"]},
    {"label": "slang-typo", "lang": "en",
     "says": ["wanna play dota lol", "in the evening", "rank doesn't matter"],
     "expect": ["dota"], "never": ["rank", "lol"]},
    {"label": "сленг-2", "lang": "ru",
     "says": ["кто в падик на кальян", "вечером", "можно и дома"],
     "expect": ["кальян", "shisha"], "never": ["падик"]},

    # ── ОТСЫЛКА НАЗАД И НЕЯВНОЕ: предмет называется только в конце.
    {"label": "отсылка", "lang": "ru",
     "says": ["хочу как в прошлый раз", "ну поиграть во что-нибудь", "в приставку"],
     "expect": ["приставк", "консол"], "never": ["прошлый"]},
    {"label": "indirecto", "lang": "es",
     "says": ["estoy harto de estar en casa", "salir a algún sitio", "una exposición"],
     "expect": ["exposici"], "never": ["casa"]},
    {"label": "не-занятие", "lang": "ru",
     "says": ["хочу выучить испанский", "с носителем поговорить", "по вечерам"],
     "expect": ["испан", "spanish", "язык"], "never": ["вечер"]},

    # ── ГРАНИЦЫ: просьбы, на которые продукт обязан отвечать иначе.
    {"label": "алкоголь", "lang": "ru",
     "says": ["хочу нажраться", "ну или просто посидеть с кем-то", "в баре"],
     "expect": ["бар", "bar"], "never": ["нажрат"]},
    {"label": "грубость", "lang": "ru",
     "says": ["найди мне кого-нибудь нормального блин", "поговорить про музыку", "рок"],
     "expect": ["музык", "рок"], "never": ["блин", "нормальн"]},
]

def load_pool():
    """Сценарии, написанные нейронкой. Свои (ядро) остаются всегда — они стерегут основы."""
    out = []
    try:
        for line in open(POOL_FILE, encoding="utf-8"):
            try:
                sc = json.loads(line)
            except Exception:
                continue
            if sc.get("says") and sc.get("expect") and sc.get("lang"):
                out.append(sc)
    except FileNotFoundError:
        pass
    return out


# ЭТАЛОННЫЙ ПРОГОН: ТОТ ЖЕ НАБОР ДО И ПОСЛЕ ПРАВКИ.
#
# ЗАЧЕМ. Круг берёт случайную выборку из растущего пула, поэтому два круга подряд отличаются на
# 0,05 доли бед просто от смены сценариев: 17.09.2026 чистые круги дали «затея не про то» 0,404 /
# 0,351 / 0,400 — и середина выглядела победой правки, которой не было. Отличить правку от шума на
# случайной выборке нельзя. С `KLEAL_BATTERY_FIXED=<файл>` набор берётся целиком и в том же
# порядке, ядро не подмешивается, а история кругов и таблица НЕ пишутся: эталон не должен
# притворяться боевым кругом.
FIXED = os.environ.get("KLEAL_BATTERY_FIXED", "").strip()

# СВЕРКА «ПРО ТО ЛИ ЗАТЕЯ» — ПО СМЫСЛУ, А НЕ ПО БУКВАМ.
#
# Генератор пишет `expect` обрезанным корнем и на языке разговора: «вело», «кин», «чит», «idioma».
# Сверка была голой подстрокой по названию, предмету и темам, а темы приходят КАНОНИЧЕСКИМ
# английским ключом. Отсюда ложные беды: «Покататься на велике» против «вело» (человек написал
# слэнгом), «Посмотреть фильмы» против «кино» (синонимы), «Practicar lenguas» против «idioma»
# (перевод). Разбор 16 свежих бед 17.09.2026: минимум половина — верные имена.
#
# Поэтому вторая попытка: обе стороны приводятся к ключу таксономии. Берём ПОЛНОЕ слово из реплик
# человека, в котором сидит корень («велике» по «вело»), — корень сам по себе к ключу не сводится.
# Это словарь форм, а не правило продукта: он только переводит слова в один язык, решение «то же
# это занятие или нет» остаётся за сравнением ключей. Если таксономия слова не знает (испанские
# глаголы «jugar», «leer» — 39% случаев), работает прежняя проверка по подстроке, то есть хуже
# точно не станет.
try:
    import importlib.util as _ilu
    _vs = _ilu.spec_from_file_location("_kleal_vocab", "/opt/kleal/kleal-ms/services/buddy/app.py")
    _voc = _ilu.module_from_spec(_vs); _vs.loader.exec_module(_voc)
    _canon = _voc.norm_topic
    _STOPWORDS_VOC = set(getattr(_voc, "_RAW_STOP", ()) or ())
except Exception as _ve:
    print("словарь форм не поднялся (%s) — сверка останется по буквам" % str(_ve)[:60])
    _canon = lambda _w: ""
    _STOPWORDS_VOC = set()


_NEG_TOKEN = re.compile(r"(?iu)(?:^|[\s,.;:!?¿¡-])(?:не|нет|ни|без|not|no|don'?t|dont|never|sin|tampoco)(?:[\s,.;:!?-]|$)")


def _subject_from_refusal(subj, answers):
    """Предмет взят из куска, который человек ОТВЕРГ, — вот это настоящая беда.

    ЗАЧЕМ. Проверка «предмет из ответа» задумывалась против случая «человек просил одно, а затея
    про слово из ответа на наше уточнение». С 17.09.2026 батарея судит по ПОСЛЕДНЕЙ затее, и
    условие «предмет нашёлся только в поздней реплике» стало описывать НОРМУ: человек начинает с
    настроения и называет занятие третьим ходом — затея обязана быть про это. Разбор 12 свежих
    случаев: верных имён одиннадцать («мне грустно» → «наверное, кино посмотрим?» → «Посмотреть
    кино»), беда одна.

    Что осталось настоящей бедой: предмет вытащен из клочка, где человек как раз ОТКАЗЫВАЛСЯ —
    «correr no», «not running though», «no me apetece cocinar». Ищем отрицание в том же куске
    фразы (между запятыми), где стоит сам предмет: «no, mejor veamos una película» — это поправка,
    а не отказ от кино, и она в счёт не идёт.
    """
    ss = stems(subj)
    for a in answers:
        for piece in re.split(r"[,.;!?\u2026]+", str(a or "")):
            if piece.strip() and share(ss, stems(piece)) and _NEG_TOKEN.search(" " + piece + " "):
                return piece.strip()
    return ""


def _same_thing(expect, said, title, subj, topics):
    """Совпадает ли затея с тем, чем разговор кончился, — с точностью до языка и формы слова."""
    want, got = set(), set()
    _said = " ".join(str(x) for x in (said or [])).lower()
    for e in expect:
        e = str(e).lower()
        for w in re.findall(r"[\w-]+", _said):
            if e in w:
                k = _canon(w)
                if k:
                    want.add(k)
        k = _canon(e)
        if k:
            want.add(k)
    for t in list(topics or []) + [subj, title]:
        for w in re.findall(r"[\w-]+", str(t or "").lower()):
            k = _canon(w)
            if k:
                got.add(k)
    return bool(want & got)


CORE = list(SCEN)
_pool = load_pool()
# ЯДРО ЦЕЛИКОМ, ПУЛ — ВЫБОРКОЙ. Ядро написано руками и стережёт основы: если сломается там, дело
# не в трудности сценария. Пул большой и растёт, за несколько кругов проходит весь.
if FIXED:
    SCEN = [json.loads(_l) for _l in open(FIXED, encoding="utf-8") if _l.strip()]
else:
    random.shuffle(_pool)
    SCEN = CORE + _pool[:max(0, BATCH - len(CORE))]

problems, rows = [], []

# ЖИВОЙ ПОКАЗ. Функция названа `emit`, а не `say`: внутри `run()` переменная цикла тоже `say`
# (реплика человека), и она перекрывала функцию — прогон падал с «'str' object is not callable»
# на первом же сценарии. Имя переменной здесь важнее: она читается в теле сценария постоянно. Раньше вывод был только в конце — сорок минут в тишине, и непонятно, идёт прогон
# или встал. Теперь строка печатается сразу, как сценарий закончился, и служба кладёт её в журнал:
# `journalctl -fu kleal-battery -o cat` показывает прогон в реальном времени.
G, R, Y, D, Z = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
_started = time.time()


def emit(line=""):
    with _LOCK:
        print(line, flush=True)


def flag(kind, scen, detail):
    with _LOCK:
        problems.append((kind, scen, detail))
    # МЕТКА СЦЕНАРИЯ ОБЯЗАНА СТОЯТЬ В САМОЙ СТРОКЕ БЕДЫ.
    #
    # Её тут не было, и привязать беду к разговору по журналу было НЕЛЬЗЯ: 64 работника пишут в
    # один файл вперемешку, поэтому ближайшая сверху строка «СЦЕНАРИЙ X» — чужая. Разбор 17.09.2026
    # по такому журналу дал 23 «имени из ниоткуда» из 28 и вывод «попап — это монетка, ни один
    # разговор не сломан». Оба неверны: по `battery-live.jsonl`, где метка есть, на 57 общих
    # сценариях соседних кругов «попап не сработал» совпал 8 из 8 при ожидании 1,1 — то есть беда
    # УСТОЙЧИВА и воспроизводится. Час работы ушёл на то, чего не было в одной строке формата.
    w("      !! %-20s [%s] %s" % (kind, scen, detail))
    emit("      %s!! %-18s%s %s" % (R, kind, Z, detail[:96]))
    live("problem", scen, "", "%s: %s" % (kind, detail))


def stems(text):
    return {x.lower() for x in WORD.findall(str(text))}


def _dist(a, b, cap=2):
    """Расстояние правок с ранним выходом — нам важно только «то же слово или нет»."""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def share(a, b):
    """Есть ли у двух наборов общее слово с точностью до формы и описки.

    Ни срез в N букв, ни общее начало не годятся: «вино» и «вина» расходятся на четвёртой букве,
    «тенис» и «теннис» — на четвёртой же. Обе пары — одно слово, и мерка, которая считает их
    разными, ругается на ВЕРНЫЕ имена. Расстояние правок до двух ловит и падеж, и описку, а «дом» с
    «доской» не путает.
    """
    for x in a:
        for y in b:
            if len(x) >= 4 and len(y) >= 4 and _dist(x, y) <= 2:
                return True
            # Приставка и суффикс — то же слово: «бег» и «побегать», «кино» и «кинотеатр».
            # Расстояние правок их не сводит, а вхождение корня — сводит.
            if len(x) >= 3 and len(y) >= 3 and (x[:4] in y or y[:4] in x):
                return True
            if x == y:
                return True
    return False


# КАК ЗАТЕЮ НАЗЫВАЮТ РАЗНЫЕ ОКНА.
#
# Одна и та же затея показывается человеку минимум в трёх местах, и каждое берёт название
# по-своему: мастер затеи — из ответа сборщика; попап «С чего начнём?» в разговоре с Бадди — из
# ответа /chat, через свои запасные правила; карточка — третьим способом. Разойтись они могут
# запросто, и человек увидит два разных имени одной затеи.
#
# Правила ЗДЕСЬ — НАМЕРЕННАЯ КОПИЯ клиентских (kleal-app/src/buddy.ts: intentTitle, intentDesc,
# intentLabel). Импортировать оттуда нечего — это TypeScript в приложении, — а главное, измеритель
# и не должен брать правила у измеряемого: свою копию видно, и когда клиент поменяется, копия
# разойдётся заметно, а не молча.
_BARE_TITLE = {"ru": {"discuss": "Разговор", "_": "Встреча"},
               "en": {"discuss": "A chat", "_": "Meet someone"},
               "es": {"discuss": "Charla", "_": "Quedada"}}


def surfaces(res, lang):
    """Имя затеи так, как его увидят в окнах приложения."""
    it = (res or {}).get("intent") or {}
    raw = str(it.get("title") or it.get("activity") or "").strip()
    subj = str(it.get("subject") or "").strip()
    role = str(it.get("role") or "").strip()
    title = raw or (subj[:1].upper() + subj[1:] if subj
                    else _BARE_TITLE.get(lang, _BARE_TITLE["en"]).get(role, _BARE_TITLE.get(lang, _BARE_TITLE["en"])["_"]))
    label = raw or ", ".join(str(t) for t in (it.get("topics") or [])) or title
    return {"title": title, "desc": str(it.get("desc") or "").strip(), "label": label,
            "subject": subj, "role": role, "topics": [str(t) for t in (it.get("topics") or [])],
            "mode": str(it.get("mode") or ""), "format": str(it.get("format") or "")}


def run(sc):
    label, lang, says = sc["label"], sc["lang"], sc["says"]
    _t0 = time.time()
    live("scen_start", label, lang, says[0][:80], {"hard": sc.get("hard", 0), "src": sc.get("src", "core")})
    w("=" * 100)
    w("СЦЕНАРИЙ %s [%s]" % (label, lang))
    msgs, turns, intent, ready_at, questions, added = [], 0, None, None, [], []
    questions_before_ready = []
    ready_reply = ""
    # РАЗГОВОР ДОСМАТРИВАЕМ ДО КОНЦА, А СУДИМ ПО ПОСЛЕДНЕЙ ЗАТЕЕ.
    #
    # Раньше проход обрывался на первом `ready`, и батарея мерила ПЕРВУЮ карточку. Продукт же с
    # этого места разговор продолжает: человек говорит «нет, лучше настолки», и карточка
    # пересобирается. Из-за обрыва не было видно ни этой пересборки, ни цены ранней сборки:
    # 17.09.2026 сборщик научился собирать с первого хода, и в замере это выглядело ухудшением
    # («взял отвергнутое» ползло вверх), хотя человек в живом разговоре поправку вносил и получал
    # верную затею. Меряем то, с чем человек остаётся в конце.
    for i in range(len(says) + 2):
        if intent and i >= len(says):
            break                      # реплики человека кончились, а затея есть — добирать нечего
        say = says[i] if i < len(says) else {"ru": "давай", "en": "sure", "es": "vale"}[lang]
        msgs.append({"role": "user", "content": say})
        turns += 1
        d = post("/api/buddy/intent-build", {"messages": msgs, "profile": PROF[lang], "lang": lang})
        if d.get("__error"):
            flag("СЕТЬ", label, d["__error"]); return
        reply = str(d.get("reply") or "")
        added += (d.get("added") or [])
        w("   человек: %s" % say)
        w("   Kleal:   %s" % (reply or "(пусто)"))
        live("human", label, lang, say)
        live("kleal", label, lang, reply or "(пусто)", {"ready": bool(d.get("ready"))})
        w("   ready=%s added=%s" % (d.get("ready"), json.dumps(d.get("added") or [], ensure_ascii=False)[:160]))
        if reply.rstrip().endswith(("?", "？")):
            # ВОПРОСЫ СЧИТАЕМ ДО СБОРКИ. Бюджет в два вопроса — про то, что сборщик не должен
            # допрашивать, ПОКА собирает план. После готовой карточки разговор живёт дальше:
            # человек передумывает, называет новое, и уточняющий вопрос там законен. Разбор 849
            # вопросов агента 17.09.2026: про запретные поля (сколько людей, когда, где) — три
            # штуки, 0,4%; остальное обычные уточнения, и в длинном разговоре их закономерно
            # больше двух. Считать их бедой значит ругаться на разговор, а не на допрос.
            if intent is None:
                questions_before_ready.append(reply)
            if any(stems(reply) == stems(q) for q in questions):
                flag("ПОВТОР ВОПРОСА", label, reply[:70])
            questions.append(reply)
        if re.search(r"(\S)\1{5,}", reply):
            flag("СРЫВ В ПОВТОР", label, reply[:60])
        if reply:
            if lang == "ru" and not CYR.search(reply):
                flag("ЧУЖОЙ ЯЗЫК", label, "без кириллицы: " + reply[:50])
            if lang in ("en", "es") and CYR.search(reply):
                flag("ЧУЖОЙ ЯЗЫК", label, "кириллица в %s: %s" % (lang, reply[:50]))
        if d.get("ready") and (d.get("intent") or {}).get("title"):
            # Затея есть — но разговор не окончен: следующая реплика может её поправить, и
            # побеждает ПОСЛЕДНЯЯ. `ready_at` остаётся временем ПЕРВОЙ сборки: это про то, скоро
            # ли человек увидел карточку, а не про то, какой она вышла.
            intent = d["intent"]
            ready_reply = reply
            if ready_at is None:
                ready_at = turns
        msgs.append({"role": "assistant", "content": reply})

    if not intent:
        w("   ИТОГ: затея НЕ СОБРАЛАСЬ за %d ходов" % turns)
        flag("НЕ СОБРАЛАСЬ", label, "%d ходов, вопросов %d" % (turns, len(questions)))
        emit("%s│%s %s— не собралась —%s (%d ходов)" % (D, Z, R, Z, turns))
        live("scen_done", label, lang, "— не собралась —",
             {"t0": _t0, "bad": 1, "turns": turns, "hard": sc.get("hard", 0), "src": sc.get("src", "core")})
        rows.append((label, lang, None, None, turns, len(questions), added)); return

    title = str(intent.get("title") or "")
    subj = str(intent.get("subject") or "").strip()
    topics = [str(t).lower() for t in (intent.get("topics") or [])]
    w("   ЗАТЕЯ: «%s»" % title)
    w("      предмет=%r роль=%s режим=%s формат=%s темы=%s"
      % (subj, intent.get("role"), intent.get("mode"), intent.get("format"), topics))
    w("      вопросов %d, собралась на ходу %d, записано %s"
      % (len(questions), ready_at, json.dumps(added, ensure_ascii=False)[:160]))

    # 1. Затея без предмета.
    if title.strip().lower().rstrip(".!") in BARE[lang]:
        flag("БЕЗ ПРЕДМЕТА", label, "«%s»" % title)
    # 2. Предмет — из ответа на наш вопрос, а не из просьбы.
    wish = [s for i, s in enumerate(says) if i == 0 or _WISH.search(s)]
    answers = [s for s in says if s not in wish]
    if subj:
        ss = stems(subj)
        # ПЕЧАТАТЬ НАДО ТУ САМУЮ РЕПЛИКУ, А НЕ ПЕРВУЮ ПОПАВШУЮСЯ. Раньше в беду писались
        # `answers[0]` и `says[0]` — куски, к совпадению отношения не имеющие. Дозор дважды читал
        # это как «человек назвал занятие позже» и чинил не то место: мерка врала не числом, а
        # объяснением. Теперь в строке стоит реплика, где предмет ДЕЙСТВИТЕЛЬНО нашёлся, и все
        # реплики-просьбы, в которых его не было.
        _hit = _subject_from_refusal(subj, answers)
        if _hit and not any(share(ss, stems(x)) for x in wish):
            flag("ПРЕДМЕТ ИЗ ОТКАЗА", label, "«%s»: %r из отвергнутого «%s», а просили «%s»"
                 % (title, subj, _hit[:40], " / ".join(wish)[:60]))
    # 2б. РАСПИСКА ОБЯЗАНА НАЗЫВАТЬ ТО ЖЕ, ЧТО КАРТОЧКА.
    #
    # Снято с телефона владельца 17.09.2026: карточка «Посмотреть кино», а под ней «Понял — мне
    # грустно. Дальше выбери время и место». Батарея этого не видела вовсе — она смотрела заголовок
    # и темы, а текст ответа не читала. Расписка узнаётся по нашему же шаблону: «Понял — X.»,
    # «Got it — X.», «Entendido — X.».
    _rm = re.search(r"(?:Понял|Got it|Entendido)\s+[—-]\s+([^.!?]+)", str(ready_reply or ""))
    if _rm and subj:
        _said_in_receipt = _rm.group(1).strip()
        # Дословное совпадение считаем совпадением без разбора: у «80-х» нет корней, и `share`
        # честно отвечал «не то» на два одинаковых слова.
        _same_text = _said_in_receipt.strip().lower() == str(subj).strip().lower()
        if not _same_text and not share(stems(_said_in_receipt), stems(subj)) and not _same_thing(
                [_said_in_receipt], [subj], title, subj, topics):
            flag("РАСПИСКА НЕ ПРО ТО", label,
                 "карточка «%s» (предмет %r), а в ответе «%s»" % (title, subj, _said_in_receipt[:40]))

    # 2в. ЧИПЫ КАРТОЧКИ — ЭТО ТО, ЧТО ЧЕЛОВЕК ВИДИТ. С того же телефона: под заголовком стояли
    # «CS», «расскажи», «про». Служебное слово в чипе — беда не хуже мусорной темы.
    _tags = [str(t).strip().lower() for t in (intent.get("tags") or []) if str(t).strip()]
    # Стоп-список сам по себе тут не мерка: в нём лежат «games», «jugar», «cs» — для разбора
    # предмета это служебные слова, а на карточке «Игры» и «КС» совершенно законные чипы. Поэтому
    # мусор — это то, что И в стоп-списке, И не сводится к занятию: «расскажи», «про», «buen».
    _junk_tags = [t for t in _tags
                  if (len(t) < 3 and not _canon(t)) or (t in _STOPWORDS_VOC and not _canon(t))]
    if _junk_tags:
        flag("МУСОР В ЧИПАХ", label, "«%s»: %s" % (title, _junk_tags))

    # 3. Предмет — мусорное слово.
    if subj and subj.strip().lower() in JUNK:
        flag("ПРЕДМЕТ-МУСОР", label, "«%s» <- %r" % (title, subj))
    # 4. Предмет ниоткуда: его нет ни в одной реплике человека (описку реестра это не задевает —
    #    у неё общий корень со сказанным).
    # СРАВНИВАЕМ ПО СМЫСЛУ, А НЕ ПО БУКВАМ — как и «про то ли затея».
    #
    # Подпись реестра нарочно не повторяет слово человека: он сказал «movie», «бассейн», «peli», а
    # в карточке стоит «Films», «Плавание», «Películas». Буквенная сверка звала это «предметом
    # ниоткуда». Разбор 93 бед 17.09.2026: сорок процентов снимаются одним приведением к ключу
    # таксономии, и это при том, что в самой строке беды текст человека обрезан — внутри проверки
    # он целый, значит снимется больше.
    #
    # Настоящей бедой остаётся предмет, которого в разговоре нет НИ В КАКОМ виде: «Чтение» после
    # разговора про велосипеды.
    if subj:
        _sk = _canon(str(subj).strip().lower())
        _grounded = any(share(stems(subj), stems(s)) for s in says)
        if not _grounded and _sk:
            for _s in says:
                for _w in re.findall(r"[\w-]+", str(_s).lower()):
                    if _canon(_w) == _sk:
                        _grounded = True
                        break
                if _grounded:
                    break
        if not _grounded:
            flag("ПРЕДМЕТ НИОТКУДА", label,
                 "«%s»: %r, а человек говорил «%s»" % (title, subj, " | ".join(says)[:60]))
    # 5. Английское слово в русской фразе — кроме имён собственных.
    if lang == "ru" and subj and LAT.search(subj) and not PROPER.search(subj):
        flag("АНГЛ В РУССКОМ", label, "«%s» <- %r" % (title, subj))
    # 0. ЧЕМ КОНЧИЛСЯ РАЗГОВОР — главная проверка сложных сценариев. Человек передумал, поставил
    #    условие или назвал предмет только на третьем ходу: затея обязана быть про КОНЕЦ разговора.
    _hay = (title + " " + subj + " " + " ".join(topics)).lower()
    _exp = [e for e in (sc.get("expect") or []) if e]
    if (_exp and not any(e.lower() in _hay for e in _exp)
            and not _same_thing(_exp, says, title, subj, topics)):
        flag("ЗАТЕЯ НЕ ПРО ТО", label, "«%s» (темы %s), а разговор кончился на %s"
             % (title, topics, "/".join(_exp)))
    # ЗАПРЕТ, ОЗНАЧАЮЩИЙ ТО ЖЕ, ЧТО ОЖИДАНИЕ, — ОШИБКА СЦЕНАРИЯ, А НЕ БЕДА ПРОДУКТА.
    #
    # Генератор пишет сценарии нашей же моделью и иногда называет одно занятие двумя словами:
    # «ждём película, запрещаем cine», «ждём фильм, запрещаем кино», «ждём movie, запрещаем
    # cinema». Любая ВЕРНАЯ карточка ловит такой запрет и получает «взял отвергнутое» — то есть
    # мерка штрафует за правильный ответ. Разбор 434 бед по складу 17.09.2026: таких 11 (2,5%),
    # в пуле 9 сценариев из 3199. Сверяем ключом таксономии — тем же, чем сверяется всё остальное.
    _exp_keys = {(_canon(e.lower()) or e.lower()) for e in _exp}
    _bad_end = [n for n in (sc.get("never") or [])
                if n.lower() in _hay and (_canon(n.lower()) or n.lower()) not in _exp_keys]
    if _bad_end:
        flag("ВЗЯЛ ОТВЕРГНУТОЕ", label, "«%s» несёт %s" % (title, _bad_end))

    # 6a. Падежная форма в темах. Темы — ключи поиска; «котами» не совпадёт ни с `cats`, ни с
    #     «кот», а на экране стоит чипом. Своя регулярка, не из кода сборщика: мерка не должна
    #     соглашаться с измеряемым по построению.
    _OBL = re.compile(r"(?iu)(ами|ями|ах|ях|ыми|ими)$")
    _obl = [t for t in topics if len(t) >= 5 and CYR.search(t) and _OBL.search(t)]
    if _obl:
        flag("ПАДЕЖ В ТЕМАХ", label, "%s <- %s" % (topics, _obl))
    # 6. Мусор в темах — он идёт в поиск.
    jt = [t for t in topics if t in JUNK]
    if jt:
        flag("МУСОР В ТЕМАХ", label, "%s <- %s" % (topics, jt))
    # 7. Записанное в интересы — тоже не мусор.
    aj = [a.get("key") for a in added if isinstance(a, dict) and str(a.get("key", "")).lower() in JUNK]
    if aj:
        flag("ЗАПИСАЛ МУСОР", label, str(aj))
    # 8. Бюджет вопросов — два.
    if len(questions_before_ready) > 2:
        flag("ЛИШНИЕ ВОПРОСЫ", label, "%d до сборки (всего %d)"
             % (len(questions_before_ready), len(questions)))
    # 9. Режим и место должны сходиться.
    _place = str(intent.get("place") or intent.get("district") or "").strip()
    # «Онлайн» в поле места — это не место, а подпись того же режима: ругаться на неё незачем.
    if str(intent.get("mode")) == "online" and _place and _place.lower() not in (
            "онлайн", "online", "en línea", "en linea", "по видео", "видео", "zoom"):
        flag("РЕЖИМ НЕ СХОДИТСЯ", label, "онлайн, но место %r" % _place)
    rows.append((label, lang, title, topics, ready_at, len(questions), added))
    # СКЛАД ДЛЯ ДООБУЧЕНИЯ. Батарея каждый круг производит именно то, чего не хватает для обучения
    # модели: разговор, собранную по нему затею и МЕХАНИЧЕСКИЙ вердикт. Раньше всё это оседало в
    # журнале и терялось. Теперь каждый сценарий ложится строкой: `good` — ни одной беды (годится
    # в примеры), иначе список видов беды (годится в отрицательные пары и в разбор). Эталонные
    # прогоны сюда НЕ пишутся: там один и тот же набор по кругу, он перекосил бы выборку.
    if not FIXED:
        try:
            _ds = "/root/kleal-archive/dataset.jsonl"
            _kinds_here = sorted({_k for _k, _sc, _d in problems if _sc == label})
            with open(_ds, "a", encoding="utf-8") as _df:
                _df.write(json.dumps({
                    "t": round(time.time()), "label": label, "lang": lang,
                    "hard": sc.get("hard", 0), "src": sc.get("src", "core"),
                    "shape": sc.get("shape", "plain"), "says": says,
                    "expect": sc.get("expect") or [], "never": sc.get("never") or [],
                    "intent": {"title": title, "subject": subj, "topics": topics,
                               "role": intent.get("role"), "mode": intent.get("mode"),
                               "type": intent.get("type"), "format": intent.get("format")},
                    "turns": ready_at, "questions": len(questions),
                    "good": not _kinds_here, "bad": _kinds_here,
                }, ensure_ascii=False) + "\n")
            # Держим последние 50 тысяч строк: это примерно сутки кругов, а файл остаётся мелким.
            _all = open(_ds, encoding="utf-8").readlines()
            if len(_all) > 50000:
                open(_ds, "w", encoding="utf-8").writelines(_all[-50000:])
        except Exception as _dse:
            print("склад дообучения не пишется: %s" % str(_dse)[:80], flush=True)
    # Строка итога — сразу после сценария, а не в конце прогона: ради неё живой показ и делался.
    _bad = sum(1 for _k, _sc, _d in problems if _sc == label)
    emit("%s│%s %s «%s» %s(ход %d, вопросов %d)%s"
        % (D, Z, (R + "✗" + Z) if _bad else (G + "✓" + Z), title, D, ready_at, len(questions), Z))
    # ТОТ ЖЕ РАЗГОВОР — ЧЕРЕЗ РАЗГОВОРНУЮ РУЧКУ, ХОД ЗА ХОДОМ.
    #
    # В приложении попап «С чего начнём?» выскакивает САМ, посреди разговора, как только сервер
    # распознал затею. Признак у клиента один — поле `intent` в ответе /chat (см. looksLikeIntent).
    # Поэтому мало спросить итог: важно, СРАБОТАЛ ли попап и на каком ходу. Разговор проходим
    # заново, добавляя по реплике, и останавливаемся на первом срабатывании.
    _pmsgs, _fired_at, _chat, _perr, _plast = [], 0, {}, "", ""
    for _i, _say in enumerate(says, 1):
        _pmsgs.append({"role": "user", "content": _say})
        _r = post("/api/buddy/chat", {"messages": _pmsgs, "profile": PROF[lang], "lang": lang})
        if _r.get("__error"):
            # ОБРЫВ ПОВТОРА — ЭТО СБОЙ СЕТИ, А НЕ МОЛЧАЩИЙ ПОПАП. Ниже стоял голый `break`, и
            # прогон, не доехавший до ответа, попадал в «ПОПАП НЕ СРАБОТАЛ» как беда продукта.
            # Запоминаем причину и отчитываемся честно.
            _perr = str(_r.get("__error"))[:60]
            break
        if (_r.get("intent") or {}).get("title") or (_r.get("intent") or {}).get("activity"):
            _chat, _fired_at = _r, _i
            break
        # ПОСЛЕДНИЙ ОТВЕТ ЗАПОМИНАЕМ. Без него «попап не сработал» — это приговор без улики:
        # снаружи, при 48 потоках поверх круга, молчание воспроизводится в 2% случаев, а круг
        # пишет 11%, и по строке беды нельзя отличить три разных исхода — сторож «человек ничего
        # не назвал» переспрашивает, ворота `rankable` честно говорят «не за что зацепиться», или
        # модель просто заболталась и карточку не собрала.
        _plast = str(_r.get("reply") or "")
        _pmsgs.append({"role": "assistant", "content": _plast})

    _master = surfaces({"intent": intent}, lang)
    _popup = surfaces(_chat, lang) if _fired_at else None
    live("result", label, lang, title,
         {"master": _master, "popup": _popup, "fired": _fired_at, "turns_said": len(says)})

    # ПОПАП ОБЯЗАН СРАБОТАТЬ ТАМ, ГДЕ МАСТЕР СОБРАЛ ЗАТЕЮ. Иначе человек в разговоре с Бадди
    # рассказывает то же самое и не получает ничего: предложения создать затею просто не будет.
    if not _fired_at and _perr:
        # ПОВТОР УДВАИВАЕТ РАБОТУ МОДЕЛИ: тот же разговор проходится второй раз, ход за ходом, и
        # именно на нём нагрузка максимальна. Разбор 17.09.2026: из 117 помеченных «попап не
        # сработал» у 107 сухой триггер срабатывает САМ, а живой повтор на четырёх потоках дал
        # 24 из 24 — то есть беда не воспроизводится и держалась на оборванных запросах.
        flag("СЕТЬ", label, "повтор для попапа оборвался: %s" % _perr)
    elif not _fired_at:
        flag("ПОПАП НЕ СРАБОТАЛ", label,
             "мастер собрал «%s», а в разговоре затея не распозналась; ответ: %s"
             % (title, (_plast[:90].replace("\n", " ") or "—")))
    else:
        # СРАВНИВАТЬ НАДО НА ОДНОМ И ТОМ ЖЕ РАЗГОВОРЕ.
        #
        # Попап выскакивает на ходу N и видит только N реплик, а мастер собирал затею по ВСЕМ.
        # Сверка «мастер ↔ попап» ругалась на разницу, которой обязана быть: «Go hiking» против
        # «Shoot photos together (ход 1)» — это не расхождение путей, это разные входы. Замер
        # 17.09.2026: 0,257 на собранную затею, и почти все примеры такого вида.
        #
        # Поэтому мастера переспрашиваем на ТОМ ЖЕ куске разговора, на котором сработал попап.
        # Лишний вызов делается только там, где попап сработал, и только ради честности сверки.
        _cut = post("/api/buddy/intent-build",
                    {"messages": [{"role": "user", "content": _s} for _s in says[:_fired_at]],
                     "profile": PROF[lang], "lang": lang})
        _cut_i = (_cut or {}).get("intent") or {}
        _cut_name = surfaces({"intent": _cut_i}, lang) if _cut_i else None
        if _cut_name and _cut_name["title"].strip().lower() != _popup["title"].strip().lower():
            flag("ИМЕНА РАСХОДЯТСЯ", label,
                 "на ходу %d мастер «%s» ↔ попап «%s» (по всему разговору «%s»)"
                 % (_fired_at, _cut_name["title"], _popup["title"], _master["title"]))

    live("scen_done", label, lang, title,
         {"t0": _t0, "bad": _bad, "turns": ready_at, "hard": sc.get("hard", 0), "src": sc.get("src", "core")})
    live("intent", label, lang, title, {"topics": topics, "subject": subj, "turns": ready_at,
                                        "questions": len(questions), "bad": _bad,
                                        "hard": sc.get("hard", 0), "src": sc.get("src", "core")})


# Третьим доводом — список меток через запятую: прогнать часть, когда проверяешь саму батарею.
_only = [x.strip() for x in (sys.argv[3] if len(sys.argv) > 3 else "").split(",") if x.strip()]
if _only:
    SCEN = [x for x in SCEN if x["label"] in _only]

w("БАТАРЕЯ БАДДИ — %s, адрес %s" % (time.strftime("%Y-%m-%d %H:%M"), BASE))
emit("%s┌ БАТАРЕЯ БАДДИ · %d сценариев · %s · журнал %s%s"
    % (Y, len(SCEN), time.strftime("%H:%M"), LOG, Z))
# Кольцо живого потока подрезаем в начале круга: админка читает хвост, а файл не должен расти вечно.
try:
    if os.path.exists(LIVE):
        _tail = open(LIVE, encoding="utf-8").readlines()[-LIVE_KEEP:]
        open(LIVE, "w", encoding="utf-8").writelines(_tail)
except Exception:
    pass
live("run_start", "", "", "круг начат", {"scen": len(SCEN), "workers": WORKERS,
                                          "core": len(CORE), "pool": len(_pool)})

_done = [0]


def _one(sc):
    with _LOCK:
        _done[0] += 1
        _n = _done[0]
    emit("%s│ %2d/%d %-18s [%s] %s…%s"
         % (D, _n, len(SCEN), sc["label"], sc["lang"], sc["says"][0][:38], Z))
    try:
        run(sc)
    except Exception as e:                      # один сценарий не должен ронять круг
        flag("СЦЕНАРИЙ УПАЛ", sc.get("label", "?"), str(e)[:90])


with ThreadPoolExecutor(max_workers=WORKERS) as _ex:
    list(_ex.map(_one, SCEN))

print("ПОЛНЫЙ ЖУРНАЛ: %s" % LOG)
print()
print("%-18s %-3s %-38s %-4s %-4s %s" % ("сценарий", "яз", "затея", "ход", "воп", "записано"))
for label, lang, title, topics, at, qs, added in rows:
    names = ",".join(str(a.get("key")) for a in added if isinstance(a, dict))[:26]
    print("%-18s %-3s %-38s %-4s %-4s %s" % (label, lang, (title or "— не собралась —")[:38], at or "-", qs, names))
print()
by = {}
for kind, scen, detail in problems:
    by.setdefault(kind, []).append((scen, detail))
print("НАЙДЕНО БЕД: %d в %d видах (сценариев %d)" % (len(problems), len(by), len(SCEN)))
for kind, items in sorted(by.items(), key=lambda x: -len(x[1])):
    print("  %-18s %d:" % (kind, len(items)))
    for scen, detail in items[:8]:
        print("      %-18s %s" % (scen, detail[:96]))
emit("%s└ прогон окончен: %d сценариев, бед %d, %.0f мин%s"
    % (Y, len(SCEN), len(problems), (time.time() - _started) / 60, Z))
live("run_done", "", "", "круг окончен", {"scen": len(SCEN), "bad": len(problems),
                                           "min": round((time.time() - _started) / 60, 1),
                                           "calls": len(TIMES), "errors": len(ERRORS)})
print()
_dur = sum(TIMES)
print("НАГРУЗКА: вызовов %d, медиана %.1f с, p95 %.1f с, максимум %.1f с, сбоев %d, всего %.0f мин"
      % (len(TIMES), quantile(TIMES, .5), quantile(TIMES, .95), max(TIMES or [0]), len(ERRORS), _dur / 60))
if ERRORS:
    print("   сбои:", "; ".join(sorted(set(ERRORS))[:3]))

# ПОДРОБНОСТИ КРУГА — ОТДЕЛЬНОЙ ЗАПИСЬЮ. Строка истории отвечает на «сколько бед», но не на
# «каких, на каком языке и на какой сложности». Без этого аналитика в панели строится из воздуха:
# график «бед по кругам» нарисовать можно, а понять, что именно испортилось, — нельзя.
ROUNDS = "/root/kleal-archive/battery-rounds.jsonl"
try:
    _kinds, _langs, _hards, _by_src = {}, {}, {}, {}
    for _k, _sc, _d in problems:
        _kinds[_k] = _kinds.get(_k, 0) + 1
    _bad_scen = {sc for _k, sc, _d in problems}
    for _r in rows:
        _lg = _r[1]
        _langs.setdefault(_lg, {"всего": 0, "бед": 0})
        _langs[_lg]["всего"] += 1
        if _r[0] in _bad_scen:
            _langs[_lg]["бед"] += 1
    for _sc in SCEN:
        _h = str(_sc.get("hard", 0))
        _hards.setdefault(_h, {"всего": 0, "бед": 0})
        _hards[_h]["всего"] += 1
        if _sc["label"] in _bad_scen:
            _hards[_h]["бед"] += 1
        _s = _sc.get("src", "core")
        _by_src.setdefault(_s, {"всего": 0, "бед": 0})
        _by_src[_s]["всего"] += 1
        if _sc["label"] in _bad_scen:
            _by_src[_s]["бед"] += 1
    if FIXED:
        print("ЭТАЛОН: %d сценариев, собралось %d, бед %d" % (len(SCEN), sum(1 for r in rows if r[2]), len(problems)))
        for _k in sorted(_kinds, key=lambda x: -_kinds[x]):
            print("   %-22s %4d  (%.3f на собранную)" % (_k, _kinds[_k], _kinds[_k] / max(sum(1 for r in rows if r[2]), 1)))
        raise SystemExit(0)
    with open(ROUNDS, "a", encoding="utf-8") as _rf:
        _rf.write(json.dumps({
            "t": time.time(), "time": time.strftime("%H:%M"),
            "scen": len(SCEN), "built": sum(1 for r in rows if r[2]), "bad": len(problems),
            "kinds": _kinds, "langs": _langs, "hards": _hards, "src": _by_src,
            "median": round(quantile(TIMES, .5), 2), "p95": round(quantile(TIMES, .95), 2),
            "calls": len(TIMES), "errors": len(ERRORS), "workers": WORKERS,
            "pool": len(_pool), "min": round((time.time() - _started) / 60, 1),
        }, ensure_ascii=False) + "\n")
    # Держим последние 500 кругов: этого хватает на сутки с лишним, а файл остаётся мелким.
    _all = open(ROUNDS, encoding="utf-8").readlines()
    if len(_all) > 500:
        open(ROUNDS, "w", encoding="utf-8").writelines(_all[-500:])
except Exception as _e:
    print("подробности круга записать не вышло: %s" % _e)

# ИСТОРИЯ ОДНОЙ СТРОКОЙ. Ради неё всё и затевалось: разговор перестаёт быть «опять тупое название»
# и становится «вчера было 1, сегодня 4 — что сломалось». Таблица дописывается, не переписывается.
HIST = "/root/kleal-archive/battery-history.tsv"
try:
    _new = not __import__("os").path.exists(HIST)
    with open(HIST, "a", encoding="utf-8") as h:
        if _new:
            h.write("время\tсценариев\tсобралось\tбед\tвиды\tвызовов\tмедиана_с\tp95_с\tсбоев\tминут\tжурнал\n")
        h.write("%s\t%d\t%d\t%d\t%s\t%d\t%.1f\t%.1f\t%d\t%.0f\t%s\n"
                % (time.strftime("%Y-%m-%d %H:%M"), len(SCEN), sum(1 for r in rows if r[2]),
                   len(problems), ";".join(sorted(by)) or "-", len(TIMES),
                   quantile(TIMES, .5), quantile(TIMES, .95), len(ERRORS), _dur / 60, LOG))
except Exception as e:
    print("историю записать не вышло: %s" % e)

w(); w("ИТОГО бед: %d" % len(problems))
w("НАГРУЗКА: вызовов %d, медиана %.1f с, p95 %.1f с, сбоев %d" % (len(TIMES), quantile(TIMES, .5), quantile(TIMES, .95), len(ERRORS)))
_log.close()
