#!/usr/bin/env python3
"""Два движка обязаны отвечать одинаково: python3 services/matching/test_engine_twins.py

Признаки кандидата считает ПАКЕТ (`matching_core/feature_builder/builder.py`) — его и подключает
`services/matching/app.py`, если пакет на месте; `services/matching/core_v2.py` остаётся запасным
на случай, когда пакета нет или он сломан. Две копии одной логики живут рядом, и они УЖЕ
расходились молча:

  * языковая пара (15.09.2026): у запасного движка признак смотрел, какой ИМЕННО язык назван,
    у живого стояло «есть хоть один язык — полный балл». Носитель испанского и тот, кто испанский
    учит, получали одинаковую оценку; четыре сценария батареи держались на одной этой строке;
  * `TIER_KIND`: у запасного четыре уровня, у живого пять.

Тест сравнивает не текст файлов (они законно разные), а ОТВЕТЫ на одних и тех же входных данных.
Падение здесь значит: правку внесли в одну копию и забыли про вторую.
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))      # HERE = services/matching -> корень kleal-ms

_fails = []


def check(name, ok, got=""):
    print(("  ok  " if ok else "FAIL  ") + name + ("" if ok else "  -> %s" % (got,)))
    if not ok:
        _fails.append(name)


def pick(path, names):
    """Достать константы и функции из файла БЕЗ импорта модуля: у обоих движков на импорте висят
    конфиг, таксономия и стор, а проверять надо чистую арифметику."""
    src = open(path, encoding="utf-8").read()
    ns = {}
    for node in ast.parse(src).body:
        nm = getattr(node, "name", None) or (getattr(node.targets[0], "id", None)
                                             if isinstance(node, ast.Assign) else None)
        if nm in names:
            exec(compile(ast.Module([node], []), path, "exec"), ns)
    missing = [n for n in names if n not in ns]
    if missing:
        raise SystemExit("в %s не нашлось: %s" % (os.path.basename(path), ", ".join(missing)))
    return ns


LIVE = os.path.join(ROOT, "matching_core", "feature_builder", "builder.py")
SPARE = os.path.join(HERE, "core_v2.py")

NAMES = ("GEO_BANDS", "geo_value", "SEM_VALUE", "VIBE_CLASH", "LANG_WORDS")
live = pick(LIVE, NAMES)
spare = pick(SPARE, NAMES)

print("-- таблицы-якоря совпадают")
for n in ("GEO_BANDS", "SEM_VALUE", "VIBE_CLASH", "LANG_WORDS"):
    check("%s одинаков в обоих движках" % n, live[n] == spare[n],
          "живой %r != запасной %r" % (live[n], spare[n]))

print("-- близость: одинаковое число на одинаковом расстоянии")
KM = (0.0, 0.1, 1.0, 1.5, 1.6, 2.5, 3.4, 3.5, 3.6, 5.0, 6.9, 7.0, 7.1, 10.0, 14.9, 15.0, 15.1, 40.0)
for km in KM:
    a, b = live["geo_value"](km), spare["geo_value"](km)
    check("%.1f км: %s" % (km, a), a == b, "живой %s != запасной %s" % (a, b))

print("-- якоря спеки целы (ступеньки убрали, значения на границах не двигали)")
for km, want in ((1.5, 1.0), (3.5, 0.85), (7.0, 0.65), (15.0, 0.45), (15.1, 0.15), (40.0, 0.15)):
    check("%.1f км -> %s" % (km, want), live["geo_value"](km) == want, live["geo_value"](km))

print("-- между якорями значение падает, а не стоит ступенькой")
vals = [live["geo_value"](k) for k in KM]
check("не растёт с расстоянием", all(a >= b for a, b in zip(vals, vals[1:])), vals)
mid = [live["geo_value"](k) for k in (1.6, 2.5, 3.4)]
check("внутри одной прежней ступени значения разные", len(set(mid)) == 3, mid)
near = [live["geo_value"](k) for k in (0.1, 1.0, 1.4)]
check("ближе 1,5 км все равны — «в шаговой доступности» не делится", len(set(near)) == 1, near)

print()
print("FAILED %d: %s" % (len(_fails), ", ".join(_fails)) if _fails else "ALL PASS")
sys.exit(1 if _fails else 0)
