# -*- coding: utf-8 -*-
"""Смоук таблицы понятий (matching_core/taxonomy/concepts.py).

ЗАЧЕМ. Модуль закрывает то, чего нет в каноне: составные и многоязычные формулировки. У него
нетривиальная морфология с русскими окончаниями и таблица на сотни алиасов — и ни одной проверки,
пока это писалось. Правило «короткое слово должно быть НАЧАЛОМ длинного, разница не больше
четырёх» держится на одной строке; следующий, кто её тронет, должен узнать о поломке здесь, а не
от человека, которому поиск про криптографию принёс криптовалютчиков.

ПРОВЕРЯЮТСЯ ГРАНИЦЫ, А НЕ СЛОВАРЬ. Тесты на «такое-то слово есть в таблице» ломались бы от каждого
честного пополнения — за два дня это случилось четырежды. Здесь проверяются ПРАВИЛА: где
морфология обязана сработать, где обязана промолчать, и что алиас ловится только на границе слова.

    python3 tools/concepts_smoke.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from matching_core.taxonomy import concepts as X  # noqa: E402

FAIL = []


def check(name, got, want):
    ok = got == want
    print("%s  %-56s %s (ждали %s)" % ("ok  " if ok else "СБОЙ", name, got, want))
    if not ok:
        FAIL.append(name)


# ---------------------------------------------------------------- морфология: где ДА
for a, b in (("apple", "apples"), ("поход", "походы"), ("теннис", "теннисом")):
    check("родственно: %s ~ %s" % (a, b), X.token_equivalent(a, b), True)

# ---------------------------------------------------------------- морфология: где НЕТ
# Каждая пара — отдельный класс ошибки, а не просто «непохожие слова».
for a, b, why in (
    ("cryptography", "cryptocurrency", "общее начало ещё не родство"),
    ("crypt", "cryptocurrency", "хвост длиннее четырёх символов"),
    ("padel", "paddle", "разные слова с общими буквами"),
    ("cycling", "cyclist", "разные слова одного корня — не взаимозаменяемы"),
    ("run", "running", "короче пяти символов морфология не трогает"),
):
    check("НЕ родственно (%s): %s ~ %s" % (why, a, b), X.token_equivalent(a, b), False)

# ---------------------------------------------------------------- алиас ловится на границе слова
check("«крипта» — это крипта", "crypto_assets" in X.resolve_concepts("крипта"), True)
check("«microcrypto» — не крипта", X.resolve_concepts("microcrypto"), set())
check("«dotarium» — не дота", X.resolve_concepts("dotarium"), set())
check("«обмен книгами» — не языковой обмен", X.resolve_concepts("обмен книгами"), set())
check("составной алиас в фразе", "dota" in X.resolve_concepts("играю в дота 2"), True)

# ---------------------------------------------------------------- уровни
check("одно понятие -> 4", X.similarity("крипта", "cryptocurrency"), 4)
check("одна семья -> 3", X.similarity("tennis", "padel"), 3)
check("разные семьи -> 0", X.similarity("tennis", "bitcoin"), 0)
check("неизвестное молчит, а не гадает", X.similarity("labubu", "зюзюблик"), 0)

# ---------------------------------------------------------------- зонтики НЕ алиасы
# Слова-понятия льстят любому запросу своей области и врут через границу областей. Их вычищали
# из профилей тремя миграциями; в таблице понятий им тоже не место.
UMBRELLA = ("market", "tech", "project", "exchange", "business", "product", "language",
            "sport", "game", "music", "art", "food", "design", "рынок", "обмен", "проект")
leaked = sorted(w for w in UMBRELLA if X.resolve_concepts(w))
check("зонтики не резолвятся сами по себе", leaked, [])

# ---------------------------------------------------------------- области не протекают друг в друга
# Односложный алиас находится внутри любой фразы с этим словом. Для «кофе» это значило, что
# «кофе-свидание» становилось ТОЧНЫМ совпадением любителю кофе — а свидания область отдельная,
# со своим согласием и своим гейтом. Гасится списком _BLOCKED_WHEN.
for a, b in (("coffee", "кофе-свидание"), ("coffee", "cita de café"), ("coffee", "coffee date"),
             ("walking", "walking date")):
    check("свидание не бытовое: %s ~ %s" % (a, b), X.similarity(a, b), 0)

# ...но само понятие должно связывать свои формы на трёх языках
for a, b in (("coffee", "cata de café"), ("coffee", "кофе"), ("coffee", "café para charlar"),
             ("paseo", "прогулка"), ("reading", "книги"), ("movie", "кино")):
    check("связывает свои формы: %s ~ %s" % (a, b), X.similarity(a, b), 4)

# ---------------------------------------------------------------- ролевые игры
# Слово «rpg» не резолвилось нигде, хотя сами игры в каноне есть: запрос «поиграть в rpg» выдавал
# подлёдную рыбалку и counter-strike, обоих «Мэтчем». Семья общая для настольных и компьютерных
# ролевых, но внутри — разные понятия: настольная кампания и одиночная игра не одно и то же.
for a, b in (("rpg", "ролевые игры"), ("рпг", "rpg"), ("dungeons & dragons", "днд"),
             ("ведьмак", "the witcher")):
    check("ролевые, одно понятие: %s ~ %s" % (a, b), X.similarity(a, b), 4)
for a, b in (("rpg", "dungeons & dragons"), ("rpg", "baldur's gate 3"), ("rpg", "genshin impact")):
    check("ролевые, одна семья: %s ~ %s" % (a, b), X.similarity(a, b), 3)
for b in ("counter-strike 2", "dota 2", "board games", "подлёдная рыбалка", "натуральное вино"):
    check("rpg НЕ связан с %s" % b, X.similarity("rpg", b), 0)

# ---------------------------------------------------------------- зонтичные токены
# Общий токен-зонтик — не признак родства. Найдено живой жалобой: «поиграть в rpg» приводило
# человека с ИИ, теннисом и мясом на решётке — цеплял общий `games` из «strategy board games».
# Проверяется через движок, а не через таблицу: правило живёт в _wshare (taxonomy/graph.py).
from matching_core.taxonomy import graph as _G  # noqa: E402

_G.set_bridge(None)
_G.set_topics_of(None)
for a, b in (("games", "strategy board games"), ("game", "tennis"),
             ("role", "role playing games"), ("playing", "board games"),
             ("market", "stock market"), ("exchange", "language exchange")):
    check("зонтик не роднит: %s ~ %s" % (a, b), _G.similarity([a], [b])[0], 0)
# ...но конкретика рядом с зонтиком работает как прежде
for a, b, want in (("board games", "настольные игры", 4), ("board games", "board games", 4),
                   ("board games", "strategy board games", 4), ("rpg", "dungeons & dragons", 3)):
    check("конкретика цела: %s ~ %s" % (a, b), _G.similarity([a], [b])[0], want)

# ---------------------------------------------------------------- семья не смешивает области
check("финансы и игры не пересекаются", X.similarity("nasdaq", "valorant"), 0)
check("разработка — не финансы", X.similarity("programming", "trading"), 0)
check("игры — не разработка", X.similarity("dota 2", "software development"), 0)

print()
if FAIL:
    print("СБОЕВ: %d" % len(FAIL))
    sys.exit(1)
print("таблица понятий: всё зелёное")
