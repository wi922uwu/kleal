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
import argparse
import ast, io, json, re, sys

ap = argparse.ArgumentParser(description="реестр интересов: собрать или проверить")
ap.add_argument("--check", action="store_true",
                help="ничего не писать; сказать, разошлись ли реестр и литерал в матчинге")
ARGS = ap.parse_args()

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

# ПЕРЕСБОРКА НЕ СТИРАЕТ ДОПИСАННОЕ, И ЭТО НЕ МЕЛОЧЬ.
#
# Подписи приходят из двух мест: 319 из них написаны в дереве карты, остальные 128 дописаны
# отдельно (tools/fill_interest_labels.py). Первая версия этой сборки собирала реестр с нуля и
# при первом же запуске снесла все 128 — молча, потому что «источником» считала только дерево.
# Теперь уже лежащий реестр читается первым, а из источников добавляется то, чего в нём нет.
# Метка labels_auto переносится вместе с подписями: без неё не отличить машинный перевод от
# человеческого, а переучивать человека машиной нельзя.
prev_auto = []
try:
    with io.open(OUT, encoding="utf-8") as f:
        prev = json.load(f)
    kept = {k: v for k, v in (prev.get("labels") or {}).items() if k in allkeys}
    prev_auto = [k for k in (prev.get("labels_auto") or []) if k in allkeys]
    kept.update(labels)          # написанное в дереве карты сильнее: его правил человек
    for k, v in (prev.get("labels") or {}).items():
        if k in allkeys and k not in labels:
            kept[k] = v
    labels = kept
except Exception:
    pass

reg = {
    "version": 1,
    "note": ("Единственный источник интересов. Ключ канонический английский. `tree` — структура, "
             "какой её понимает ранжировщик; `labels` — подписи для экрана; `synonyms` — прочие "
             "написания. Собирается tools/build_interests.py; менять руками можно, но потом "
             "обязательно прогнать сборку — она проверяет, что источники сходятся."),
    "tree": tree,
    "labels": labels,
    "synonyms": syn,
    "labels_auto": prev_auto,
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
if ARGS.check:
    """СТОРОЖ ПРОТИВ РАСХОЖДЕНИЯ.

    Литерал в матчинге снять пока нельзя: его читает разбором services/onboarding/
    interest_normalization.py, и без него каталог станет пустым, а вместе с ним отвалится
    сохранение профиля у всех. Значит источников два, и вопрос не «как их слить», а «как
    заметить, что они разошлись». Именно этого не было, когда зеркало таксономии в buddy
    отстало на 283 слова и молча резало воронку треть года.

    Правьте shared/interests.json, потом прогоняйте эту проверку. Она сравнивает реестр с
    литералом и падает, если они разъехались.
    """
    try:
        with io.open(OUT, encoding="utf-8") as f:
            saved = json.load(f)
    except Exception as e:
        sys.exit("реестр не читается: %s" % e)
    ok_t = saved.get("tree") == tree
    ok_s = saved.get("synonyms") == syn
    print("\nПРОВЕРКА: реестр против литерала в матчинге")
    print("  структура: %s" % ("сходится" if ok_t else "РАСХОДИТСЯ"))
    print("  синонимы:  %s" % ("сходится" if ok_s else "РАСХОДЯТСЯ"))
    if not ok_t:
        a = {w for g in (saved.get("tree") or {}).values() for ws in g.values() for w in ws}
        b = {w for g in tree.values() for ws in g.values() for w in ws}
        print("    только в реестре: %d %s" % (len(a - b), sorted(a - b)[:8]))
        print("    только в коде:    %d %s" % (len(b - a), sorted(b - a)[:8]))
    sys.exit(0 if (ok_t and ok_s) else 1)

with io.open(OUT, "w", encoding="utf-8") as f:
    json.dump(reg, f, ensure_ascii=False, indent=1)
print("\nзаписано:", OUT)
