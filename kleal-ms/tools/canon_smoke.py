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
# словообразование больше не поглощается узким узлом
for w in ["market", "food", "coffee", "wine", "tea", "trading", "hike"]:
    check("не резолвится: %s" % w, C.resolve_node(w), None)
# уровни пар — ровно случаи со скриншотов админки
for a, b, lvl in [("market", "marketing", None),      # решает не канон, а буквальное сравнение
                  ("finance", "finanzas", 4),
                  ("senderismo", "hiking", 4),
                  ("mercado gastronómico", "food market", 4),
                  ("finance", "marketing", 3),        # одна семья бизнес-функций
                  ("поход", "hiking", 4)]:
    check("уровень: %s ~ %s" % (a, b), C.similarity_nodes(a, b), lvl)

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
for t, x, want in [("market", "go-to-market", 3), ("market", "stock market", 3),
                   ("craft beer", "craft beer", 4), ("рыбалка", "подлёдная рыбалка", 3)]:
    check("wshare: %s ~ %s" % (t, x), TX.similarity([t], [x])[0], want)

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
    check("фолбэк — темы интента плюс сама фраза", got1,
          {"stock", "market", "finance", "investing", "акции про рынок 2026"})
finally:
    urllib.request.urlopen = _orig

print()
if FAIL:
    print("СБОЕВ: %d" % len(FAIL))
    sys.exit(1)
print("канон и мост: всё зелёное")
