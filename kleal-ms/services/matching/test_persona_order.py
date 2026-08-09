#!/usr/bin/env python3
"""Порядок выдачи по характеру: python3 services/matching/test_persona_order.py

Функции берутся из app.py разбором исходника, а не импортом модуля: импорт поднимает сервис
целиком, читает конфиг и просится в сеть, а проверять надо чистую сортировку.

Главное, что здесь закреплено, — то, что легче всего сломать позже: характер переставляет людей
ТОЛЬКО внутри полосы, которую выдал движок. Кандидат с двумя совпадениями по характеру, но из
полосы «broader», обязан остаться ниже любого «strong». Иначе «сначала подходящие» превращается в
«сначала заполнившие анкету», а это разные вещи.
"""
import ast
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
_ns = {"load_candidates": lambda: []}          # стор здесь не нужен: оси кладём прямо в карточку
with open(_SRC, encoding="utf-8") as f:
    _src = f.read()
for _node in ast.parse(_src).body:
    if isinstance(_node, ast.Assign) and getattr(_node.targets[0], "id", "") in (
            "_NATURE_SAY", "_PERSONA_OVERFETCH"):
        exec(ast.get_source_segment(_src, _node), _ns)
    if isinstance(_node, ast.FunctionDef) and _node.name in (
            "_axes_of", "_persona_by_name", "_persona_order"):
        exec(ast.get_source_segment(_src, _node), _ns)
persona_order = _ns["_persona_order"]

_fails = []


def check(name, ok, got=""):
    print(("  ok  " if ok else "FAIL  ") + name + ("" if ok else "  -> %s" % got))
    if not ok:
        _fails.append(name)


def C(name, band, axes=None, interests=("boardgames",)):
    c = {"name": name, "band": band, "interests": list(interests)}
    if axes:
        c["persona"] = {"v": 1, "axes": axes}
    return c


names = lambda slate: [c["name"] for c in slate]

# ---- 1. полоса движка сильнее характера ----
slate = [C("A", "strong"),
         C("B", "strong", {"energy": "drained"}),
         C("C", "strong", {"energy": "energised", "depth": "deep"}),
         C("D", "broader", {"energy": "drained", "depth": "deep"}),   # два совпадения, но полоса ниже
         C("E", "broader")]
out = persona_order(slate, {"wantPersona": {"energy": "drained", "depth": "deep"}})
check("совпавший по характеру поднимается внутри своей полосы", names(out)[:3] == ["B", "C", "A"], names(out))
check("но не перепрыгивает полосу — D с двумя совпадениями остаётся ниже A",
      names(out) == ["B", "C", "A", "D", "E"], names(out))

# ---- 2. без пожелания работает вторая половина правила: «заполнили интерес и характер» ----
out = persona_order([C("A", "strong"), C("B", "strong", {"energy": "drained"}),
                     C("X", "strong", None, interests=())], {})
check("без пожелания вперёд идёт заполненный профиль", names(out) == ["B", "A", "X"], names(out))

# ---- 3. «заполнен» — это ОБА: и тест, и интересы ----
out = persona_order([C("P", "strong", {"energy": "drained"}, interests=()),
                     C("Q", "strong", {"energy": "drained"})], {})
check("тест без интересов не считается заполненным профилем", names(out) == ["Q", "P"], names(out))

# ---- 4. обе формы записи осей в сторе ----
flat = [{"name": "F", "band": "strong", "interests": ["x"], "persona": {"energy": "drained"}}]
check("плоская {axis: token} читается как оси",
      persona_order(flat, {"wantPersona": {"energy": "drained"}})[0]["persona_hits"] == 1)
wrapped = [{"name": "G", "band": "strong", "interests": ["x"],
            "persona": {"v": 1, "axes": {"energy": "drained"}}}]
check("обёрнутая {v,axes} читается как оси",
      persona_order(wrapped, {"wantPersona": {"energy": "drained"}})[0]["persona_hits"] == 1)

# ---- 5. совпадение названо на карточке: молчаливая перестановка человеку ничего не объясняет ----
out = persona_order([C("B", "strong", {"energy": "drained"})], {"wantPersona": {"energy": "drained"}})
check("причина дописана по-русски",
      any("как ты просил" in r for r in out[0].get("reasons_ru") or []), out[0].get("reasons_ru"))
check("и по-английски",
      any("as you asked" in r for r in out[0].get("reasons_en") or []), out[0].get("reasons_en"))

# ---- 6. характер НИКОГО не отсекает: пожелание, а не гейт ----
out = persona_order([C("A", "strong"), C("B", "strong")], {"wantPersona": {"energy": "drained"}})
check("никто не выпал из выдачи из-за характера", len(out) == 2, len(out))

# ---- 7. мусор в пожелании не роняет сортировку ----
out = persona_order([C("A", "strong", {"energy": "drained"})],
                    {"wantPersona": {"energy": None, "нет-такой-оси": "drained"}})
check("нестроковые и неизвестные оси игнорируются", out[0]["persona_hits"] == 0, out[0]["persona_hits"])
check("пустая выдача не падает", persona_order([], {"wantPersona": {"energy": "drained"}}) == [])

print()
if _fails:
    print("FAILED %d: %s" % (len(_fails), ", ".join(_fails)))
    sys.exit(1)
print("ALL PASS")
