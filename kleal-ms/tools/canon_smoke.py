# -*- coding: utf-8 -*-
"""Смоук канона и моста тем: то, что сломалось в августе-2026, больше не собирается молча.

Три группы проверок, каждая — от настоящего инцидента:

1. РАЗРЕШЕНИЕ КАНОНА. `market` резолвился в узел `marketing` по префиксу, и similarity выдавала
   за это «точное совпадение»: поиск про акции приводил маркетологов и гастрономические рынки,
   все — первым тиром. Догадка обязана отличаться от попадания и не тянуться дальше двух
   символов хвоста.

2. ПОТОКО-ЛОКАЛЬНОСТЬ МОСТА. Мост был глобальной переменной: параллельный поиск переставлял
   решение под соседом, половина кандидатов оценивалась с чужим мостом.

3. ЧИСТОТА ПУТИ ПОИСКА. resolve_query_topics ходил в фильтрацию по сети и учился прямо внутри
   поиска: два одинаковых вызова подряд отвечали по-разному, 90/93 сценариев золотой батареи
   падали на «NON-DETERMINISTIC result». Путь поиска обязан только читать.

Запуск:  python3 tools/canon_smoke.py    (офлайн, без сервисов; выход 0 только при полном зелёном)
"""
import json
import os
import sys
import threading

# Мост тем приколачивается ПУСТЫМ до импорта движка: смоук проверяет правила, а не выученное.
# Без этого он зелёный на голой машине и красный на боксе, где мост знает полторы тысячи фраз, —
# ровно та зависимость от окружения, из-за которой проверкам перестают верить.
os.environ["KLEAL_PHRASE_TOPICS"] = os.devnull

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "shared"))
sys.path.insert(0, os.path.join(ROOT, "services", "matching"))

FAIL = []


def check(name, got, want):
    ok = got == want
    print("%s  %-52s %s (ждали %s)" % ("ok  " if ok else "СБОЙ", name, got, want))
    if not ok:
        FAIL.append(name)


# ---------------------------------------------------------------- 1. канон
from matching_core.taxonomy import canonical as C  # noqa: E402

check("канон загружен", C.AVAILABLE, True)
# точный алиас остаётся точным — в т.ч. переводы
for w, node in [("marketing", "I_marketing"), ("hiking", "I_hiking"), ("senderismo", "I_hiking"),
                ("finanzas", "I_finance"), ("food market", "I_food_market"), ("chess", "I_chess")]:
    nid, exact = C._resolve(w)
    check("точно: %s" % w, (nid, exact), (node, True))
# СВОЙСТВО, А НЕ СЛОВАРЬ. Раньше здесь перечислялись слова, которые «не должны резолвиться»
# (wine, tea, coffee). Стоило завести им честные алиасы — тест покраснел, хотя правило цело: он
# проверял содержимое словаря, а не поведение. Теперь берём длинные алиасы из самого канона,
# отрезаем три и более символа с конца и требуем, чтобы обрубок НЕ подхватывался — если только
# он сам не объявлен алиасом.
def _reachable_within_budget(stub):
    """Есть ли у обрубка ЗАКОННЫЙ путь: алиас в пределах порога словоизменения.

    Без этой проверки тест врал: `document` резолвится не через `documentary` (хвост три,
    отвергнут), а через испанское `documental` — разница два символа, законное словоизменение.
    Проверять надо «нет ли пути вообще», а не «не тот ли это узел»."""
    for a in C.ALIAS:
        if len(a) >= 5 and len(stub) >= 4 and abs(len(a) - len(stub)) <= C._MORPH_TAIL \
                and (a.startswith(stub) or stub.startswith(a)):
            return True
    return False


_bad = []
for alias, nid in list(C.ALIAS.items())[:4000]:
    if len(alias) < 9:
        continue
    stub = alias[:len(alias) - 3]              # хвост в 3 символа — уже словообразование
    if stub in C.ALIAS or _reachable_within_budget(stub):
        continue                               # объявлен явно или достижим законно
    if C.resolve_node(stub) is not None:
        _bad.append("%s (обрублен от %s)" % (stub, alias))
check("обрубок без законного пути не резолвится", _bad[:5], [])
check("порог словоизменения", C._MORPH_TAIL, 2)
# уровни пар — ровно случаи со скриншотов админки
for a, b, lvl in [("market", "marketing", None),      # решает не канон, а буквальное сравнение
                  ("finance", "finanzas", 4),
                  ("senderismo", "hiking", 4),
                  ("mercado gastronómico", "food market", 4),
                  ("finance", "marketing", 3),        # одна семья бизнес-функций
                  ("поход", "hiking", 4)]:
    check("уровень: %s ~ %s" % (a, b), C.similarity_nodes(a, b), lvl)

# ---------------------------------------------------------------- 1b. файл дополнений
# Дополнения приклеиваются ПОВЕРХ выгрузки и не имеют права её переопределять: иначе правка
# «на один случай» тихо переставила бы пары, посчитанные по базе.
_extra = os.path.join(ROOT, "matching_core", "taxonomy", "canonical_extra.json")
if os.path.exists(_extra):
    with open(_extra, encoding="utf-8") as _f:
        _ex = json.load(_f)
    base_ids = {n for n in C.NODES if n not in C.EXTRA_NODES}
    check("дополнение не переопределяет узлы базы",
          [n["id"] for n in _ex.get("nodes", []) if n["id"] in base_ids], [])
    check("у каждого узла дополнения есть родитель в каноне",
          [n["id"] for n in _ex.get("nodes", []) if n.get("parent") not in C.NODES], [])
    check("у каждого узла дополнения три перевода",
          [n["id"] for n in _ex.get("nodes", [])
           if not all(str(n.get(k) or "").strip() for k in ("ru", "en", "es"))], [])
    check("алиасы дополнения ведут в существующие узлы",
          [a["alias"] for a in _ex.get("aliases", []) if a.get("node") not in C.NODES], [])
    # Слово, попавшее в ALIAS из дополнения, обязано быть объявлено в дополнении — своим алиасом
    # или именем своего узла на одном из трёх языков. Сравнение через C._norm: он схлопывает
    # пробелы, и наивное сравнение по строке считало «подлёдная рыбалка» посторонним.
    declared = {C._norm(a["alias"]) for a in _ex.get("aliases", [])}
    declared |= {C._norm(n[k]) for n in _ex.get("nodes", []) for k in ("ru", "en", "es") if n.get(k)}
    check("дополнение заняло только объявленные имена",
          sorted(w for w in C.EXTRA_ALIASES if w not in declared), [])
    print("     (в дополнении: %d узлов, %d алиасов)" % (len(_ex.get("nodes", [])), len(_ex.get("aliases", []))))

# ---------------------------------------------------------------- 2. мост потоко-локален
from matching_core.taxonomy import graph as TX  # noqa: E402

TX.set_bridge(lambda x: True)
seen = {}


def _other():
    seen["other"] = TX._bridge_fn()
    TX.set_bridge(lambda x: False)          # чужой поток ставит свой мост...


t = threading.Thread(target=_other)
t.start()
t.join()
check("чужой поток моста не видит", seen["other"], None)
check("чужой мост сюда не протёк", TX._bridge_fn() is not None and TX._bridge_fn()("x"), True)
TX.set_bridge(None)
check("мост снят", TX._bridge_fn(), None)

# буквальное совпадение неканонного слова осталось точным (seed-путь)
best, matched = TX.similarity(["labubu"], ["labubu"])
check("labubu ~ labubu = 4 (seed)", best, 4)
best, matched = TX.similarity(["market"], ["marketing"])
check("market ~ marketing < 3 (движок)", best < 3, True)
# общий токен — родство, но не точное совпадение; точное — только сказанное целиком
# Слова НАРОЧНО вне таксономии: проверяем правило _wshare, а не содержимое канона. Раньше здесь
# стояла «рыбалка», и появление узла рыбалки честный тест сломало — уровень стал 4, потому что
# алиас на то и алиас. Тест обязан переживать пополнение словаря.
for t, x, want in [("labubu", "labubu коллекция", 3), ("labubu", "labubu", 4),
                   ("зюзюблик", "большой зюзюблик", 3), ("зюзюблик", "квамбаз", 0)]:
    check("wshare: %s ~ %s" % (t, x), TX.similarity([t], [x])[0], want)

# ---------------------------------------------------------------- 2b. ширина и своё слово
from matching_core.feature_builder.builder import _sem_value  # noqa: E402

FULL = {"per_topic": {"a": 4, "b": 4, "c": 4, "d": 4}, "natural": 4}
THIN = {"per_topic": {"a": 4, "b": 0, "c": 0, "d": 0}, "natural": 4}
HANDLE = {"per_topic": {"a": 4, "b": 0, "c": 0, "d": 0}, "natural": 0}
L3FULL = {"per_topic": {"a": 3, "b": 3, "c": 3, "d": 3}, "natural": 3}
check("покрытие различает", _sem_value(4, FULL, 4) > _sem_value(4, THIN, 4), True)
# Балл НЕ штрафует за ручку: штраф откатан, он бил по подробным описаниям на своём языке.
check("ручка балл не режет", _sem_value(4, THIN, 4), _sem_value(4, HANDLE, 4))
# ГЛАВНЫЙ ИНВАРИАНТ: полоса уровня 4 целиком выше полосы уровня 3, иначе ярус и балл разойдутся
check("полосы уровней не пересекаются", _sem_value(4, HANDLE, 4) > _sem_value(3, L3FULL, 4), True)

# Ручка опознаётся и НЕ лишается яруса (её откатывали — см. graph.py). Слова выдуманные: тест про
# ПРАВИЛО опознания производного слова, и он не должен падать от того, что канон выучил плавание.
# Фраза-источник НАРОЧНО не однокоренная ручке: иначе `_wshare` свяжет их морфологически, и
# natural окажется 2, а не 0. Тест про производность, а не про общий корень.
TX.set_topics_of(lambda x: {"ловлю мурлышек на закате": {"зюзюбинг", "закат"}}.get(
    str(x).lower(), {str(x).lower()}))
b, _, info = TX.similarity_detail(["зюзюбинг"], ["ловлю мурлышек на закате", "зюзюбинг"])
check("ручка держит ярус", b, 4)
check("ручка помечена как не своё", info["natural"], 0)
b, _, info = TX.similarity_detail(["квамбаз"], ["квамбаз"])
check("своё слово помечено своим", (b, info["natural"]), (4, 4))
TX.set_topics_of(None)

# ---------------------------------------------------------------- 3. путь поиска только читает
import urllib.request  # noqa: E402


def _no_net(*a, **k):
    raise AssertionError("путь поиска полез в сеть")


_orig = urllib.request.urlopen
urllib.request.urlopen = _no_net
try:
    import app as M  # noqa: E402
    got1 = M.resolve_query_topics(["stock", "market", "finance", "investing"], "Акции про рынок 2026")
    got2 = M.resolve_query_topics(["stock", "market", "finance", "investing"], "Акции про рынок 2026")
    check("без сети и детерминированно", got1 == got2 and isinstance(got1, set), True)
    # ВХОЖДЕНИЕ, А НЕ РАВЕНСТВО. Мост складывают несколько источников, и список законно растёт:
    # к темам интента добавляются стабильные метки концептов (concept:*, family:* из
    # taxonomy/concepts.py). Проверка на точное множество ломалась от каждого такого пополнения,
    # хотя правило — «темы интента и сама фраза обязаны быть в мосту» — целое.
    check("фолбэк — темы интента плюс сама фраза",
          {"stock", "market", "finance", "investing", "акции про рынок 2026"} - got1, set())
finally:
    urllib.request.urlopen = _orig

print()
if FAIL:
    print("СБОЕВ: %d" % len(FAIL))
    sys.exit(1)
print("канон и мост: всё зелёное")
