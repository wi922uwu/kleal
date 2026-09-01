# -*- coding: utf-8 -*-
"""Собрать shared/interests.json и ДОКАЗАТЬ, что он воспроизводит нынешние источники.

ФОРМА ВЫБРАНА ПОД ДАННЫЕ, А НЕ НАОБОРОТ. Первая попытка держала плоский список «ключ → родитель» и
потеряла 25 листьев: в таксономии головное слово группы перечислено среди её же членов
(social/coffee содержит лист coffee), а две категории — music и outdoors — перечислены внутри самих
себя. Плоскому списку такое не выразить, и он молча схлопывал пары в одну запись.

Поэтому структура хранится ДЕРЕВОМ, ровно как в оригинале, а подписи — отдельной таблицей по ключу.
Тогда обратная сборка тождественна по построению, и доказывать нечего — но проверка всё равно
стоит: она поймает следующую особенность, о которой мы ещё не знаем.
"""
import ast, io, json, re, sys

MATCHING = "/opt/kleal/kleal-ms/services/matching/app.py"
WHEEL = "/opt/kleal/kleal-app/src/interests-wheel.ts"
OUT = "/opt/kleal/kleal-ms/shared/interests.json"

vals = {}
for n in ast.parse(io.open(MATCHING, encoding="utf-8").read()).body:
    if isinstance(n, ast.Assign) and len(n.targets) == 1 and getattr(n.targets[0], "id", "") in ("TAXONOMY", "SYNONYMS"):
        vals[n.targets[0].id] = ast.literal_eval(n.value)
TAX, SYN = vals["TAXONOMY"], vals["SYNONYMS"]

low = lambda x: str(x).strip().lower()
tree = {low(b): {low(s): [low(w) for w in (ws or [])] for s, ws in (g or {}).items()}
        for b, g in TAX.items()}
syn = {low(a): low(c) for a, c in (SYN or {}).items()}

src = io.open(WHEEL, encoding="utf-8").read()
NODE = re.compile(r"\b(?:N|TOP)\(\s*(['\"])(.+?)\1\s*,\s*(['\"])(.+?)\3\s*,\s*(['\"])(.+?)\5")
labels = {}
for m in NODE.finditer(src):
    labels[low(m.group(2))] = {"ru": m.group(4), "en": m.group(6)}

allkeys = set(tree) | {s for g in tree.values() for s in g} | {w for g in tree.values() for ws in g.values() for w in ws}
labels = {k: v for k, v in labels.items() if k in allkeys}

reg = {
    "version": 1,
    "note": ("Единственный источник интересов. Ключ канонический английский. `tree` — структура, "
             "какой её понимает ранжировщик; `labels` — подписи для экрана; `synonyms` — прочие "
             "написания. Собирается tools/build_interests.py; менять руками можно, но потом "
             "обязательно прогнать сборку — она проверяет, что источники сходятся."),
    "tree": tree,
    "labels": labels,
    "synonyms": syn,
}

same_tax = tree == {low(b): {low(s): [low(w) for w in (ws or [])] for s, ws in (g or {}).items()} for b, g in TAX.items()}
same_syn = syn == {low(a): low(c) for a, c in (SYN or {}).items()}
subs = sum(len(g) for g in tree.values())
leaves = sum(len(ws) for g in tree.values() for ws in g.values())
print("категорий:    %d" % len(tree))
print("подкатегорий: %d" % subs)
print("листьев:      %d" % leaves)
print("ключей всего: %d (без повторов %d)" % (len(tree) + subs + leaves, len(allkeys)))
print("синонимов:    %d" % len(syn))
print("подписей ru/en: %d | БЕЗ подписи: %d" % (len(labels), len(allkeys) - len(labels)))
print()
print("структура воспроизводится: %s" % ("ДА" if same_tax else "НЕТ"))
print("синонимы воспроизводятся:  %s" % ("ДА" if same_syn else "НЕТ"))
if not (same_tax and same_syn):
    sys.exit("НЕ ЗАПИСЫВАЮ")
with io.open(OUT, "w", encoding="utf-8") as f:
    json.dump(reg, f, ensure_ascii=False, indent=1)
print("\nзаписано:", OUT)
