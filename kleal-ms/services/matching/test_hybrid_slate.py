#!/usr/bin/env python3
"""Гибридная выдача: python3 services/matching/test_hybrid_slate.py

Функции берутся разбором исходника, а не импортом модуля: импорт поднимает сервис целиком.

Закрепляется одно свойство, ради которого всё и делалось: в гибридной выдаче ОБЯЗАН быть хотя бы
один человек, который придёт по ссылке. Пока его нет, гибрид — это офлайн под другим названием, и
именно так он и работал: замер на стенде вернул для гибрида ровно ту же восьмёрку, что и для
офлайна, потому что 'hybrid' не было в MODE_ALLOWLIST и режим переписывался в 'offline'.
"""
import ast
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
_ns = {}
with open(_SRC, encoding="utf-8") as f:
    _src = f.read()
for _node in ast.parse(_src).body:
    if isinstance(_node, ast.Assign) and getattr(_node.targets[0], "id", "") == "_HYBRID_CALL_SLOTS":
        exec(ast.get_source_segment(_src, _node), _ns)
    if isinstance(_node, ast.FunctionDef) and _node.name == "_hybrid_merge":
        exec(ast.get_source_segment(_src, _node), _ns)
merge = _ns["_hybrid_merge"]
SLOTS = _ns["_HYBRID_CALL_SLOTS"]

# И allowlist режимов: без 'hybrid' всё остальное в этом файле проверяет код, до которого запрос
# не доходит.
_INTENT_SRC = os.path.join(os.path.dirname(_SRC), "kleal_intent.py")
_ns2 = {}
with open(_INTENT_SRC, encoding="utf-8") as f:
    _isrc = f.read()
for _node in ast.parse(_isrc).body:
    if isinstance(_node, ast.Assign) and getattr(_node.targets[0], "id", "") == "MODE_ALLOWLIST":
        exec(ast.get_source_segment(_isrc, _node), _ns2)

_fails = []


def check(name, ok, got=""):
    print(("  ok  " if ok else "FAIL  ") + name + ("" if ok else "  -> %s" % got))
    if not ok:
        _fails.append(name)


def P(name):
    return {"name": name, "interests": ["football"]}


names = lambda s: [c["name"] for c in s]
joins = lambda s: [c.get("join") for c in s]

check("'hybrid' — законный режим, а не опечатка",
      "hybrid" in _ns2["MODE_ALLOWLIST"], _ns2["MODE_ALLOWLIST"])

# ---- 1. места для тех, кто подключится, зарезервированы ----
near = [P("n%d" % i) for i in range(8)]
far = [P("f%d" % i) for i in range(5)]
out = merge(near, far, 8)
check("в выдаче ровно восемь", len(out) == 8, len(out))
check("последние места отданы тем, кто по ссылке",
      joins(out) == ["in_person"] * (8 - SLOTS) + ["call"] * SLOTS, joins(out))
check("ближние идут первыми и в своём порядке",
      names(out)[:8 - SLOTS] == ["n%d" % i for i in range(8 - SLOTS)], names(out))

# ---- 2. один и тот же человек не попадает дважды ----
shared = P("both")
out = merge([shared] + [P("n1")], [shared, P("f1")], 8)
check("пересечение половин не двоится", names(out).count("both") == 1, names(out))
check("и остаётся тем, кто придёт живьём",
      [c for c in out if c["name"] == "both"][0]["join"] == "in_person")

# ---- 3. ближних мало — добираем дальними, а не отдаём пустые места ----
out = merge([P("n0")], [P("f%d" % i) for i in range(9)], 8)
check("места не пропадают, когда рядом почти никого", len(out) == 8, len(out))
check("первым всё равно ближний", out[0]["name"] == "n0", names(out))

# ---- 4. дальних нет вовсе — выдача просто офлайновая, без пустот и без пометки «call» ----
out = merge([P("n%d" % i) for i in range(8)], [], 8)
check("без дальних отдаём восемь ближних", len(out) == 8 and set(joins(out)) == {"in_person"}, joins(out))

# ---- 5. почему человек в списке — написано на карточке ----
out = merge([P("n0")], [P("f0")], 8)
call = [c for c in out if c.get("join") == "call"][0]
check("у подключающегося названа причина по-русски",
      any("по ссылке" in r for r in call.get("reasons_ru") or []), call.get("reasons_ru"))
check("и по-английски",
      any("join the call" in r for r in call.get("reasons_en") or []), call.get("reasons_en"))

# ---- 6. вырожденные входы ----
check("обе половины пусты — пустая выдача, без падения", merge([], [], 8) == [])

print()
if _fails:
    print("FAILED %d: %s" % (len(_fails), ", ".join(_fails)))
    sys.exit(1)
print("ALL PASS")
