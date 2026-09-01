# -*- coding: utf-8 -*-
"""Дописать русские подписи ключам, у которых их нет.

ПОЧЕМУ ЭТО НУЖНО. 128 ключей из 447 не имеют подписи, и ровно поэтому их нельзя выбрать на карте:
дерево в приложении собрано из подписанных. Треть словаря достижима только разговором.

ПОЧЕМУ АВТОМАТИЧЕСКИ, НО С ПОМЕТКОЙ. Подпись видит человек на экране, и машинный перевод там —
риск. Поэтому каждая такая подпись помечается `auto`, и рядом печатается список на вычитку: видно,
что проверять, и поправить можно в одном файле, не трогая код.

Контекст обязателен: без него `console` в разделе игр переводится как «утешение», а `strength` в
разделе спорта — как «прочность».
"""
import sys, io, json, argparse
sys.path.insert(0, "/opt/kleal/kleal-ms/shared")
from llm_client import llm_complete

REG = "/opt/kleal/kleal-ms/shared/interests.json"
MODEL = "llama_self"
BATCH = 24

ap = argparse.ArgumentParser()
ap.add_argument("--apply", action="store_true")
ap.add_argument("--from-file", default="", help="взять подписи из файла, не спрашивая модель")
a = ap.parse_args()

reg = json.load(io.open(REG, encoding="utf-8"))
tree, labels = reg["tree"], reg["labels"]

# у кого нет подписи, и в каком разделе он лежит
need = []
for broad, groups in tree.items():
    for sub, words in groups.items():
        for k in [broad, sub] + list(words):
            if k not in labels and not any(k == x[0] for x in need):
                need.append((k, broad, sub))
print("без подписи:", len(need))

PROMPT = ("Ты переводишь названия увлечений на русский для интерфейса приложения знакомств.\n"
          "Дают английский ключ и раздел, в котором он лежит. Верни JSON: {\"ключ\": \"подпись\"}.\n"
          "Правила: подпись — короткое существительное или именная группа, 1-3 слова, с большой "
          "буквы, без пояснений и скобок. Раздел задаёт смысл: console в играх — это приставки, а "
          "не утешение. Общепринятые заимствования оставляй как есть: DJ, техно, MMA. Только JSON.")

PROPOSAL = "/tmp/labels_proposal.json"
out = {}
if a.from_file:
    out = json.load(io.open(a.from_file, encoding="utf-8"))
    print("подписи взяты из файла:", len(out))
for i in ([] if a.from_file else range(0, len(need), BATCH)):
    chunk = need[i:i + BATCH]
    body = "\n".join("%s (раздел: %s / %s)" % (k, b, s) for k, b, s in chunk)
    try:
        raw = llm_complete(MODEL, [{"role": "system", "content": PROMPT},
                                   {"role": "user", "content": body}], 0.0)
        txt = str(raw or "")
        j = txt[txt.index("{"):txt.rindex("}") + 1]
        got = json.loads(j)
    except Exception as e:
        print("  партия %d: сбой (%s)" % (i // BATCH + 1, str(e)[:50]))
        continue
    for k, _b, _s in chunk:
        v = str(got.get(k) or "").strip()
        if v and len(v) <= 26:
            out[k] = v
    print("  партия %d: %d из %d" % (i // BATCH + 1, sum(1 for k, _, _ in chunk if k in out), len(chunk)))

if not a.from_file:
    json.dump(out, io.open(PROPOSAL, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\nпредложение сохранено:", PROPOSAL)

# СТОРОЖА КАЧЕСТВА. Машинный перевод виден людям, поэтому подозрительное называем поимённо.
import collections
back = collections.defaultdict(list)
for k, v in out.items():
    back[v.strip().lower()].append(k)
dups = {v: ks for v, ks in back.items() if len(ks) > 1}
latin = [k for k, v in out.items() if all(ord(c) < 128 for c in v)]
miss = [k for k, _b, _s in need if k not in out]
same = [k for k in out if out[k].strip().lower() == k.lower()]
print("\nполучено подписей: %d | не переведено: %d | осталось латиницей: %d" % (len(out), len(miss), len(same)))
if dups:
    print("\nОДНА ПОДПИСЬ НА РАЗНЫЕ КЛЮЧИ (на экране неразличимы):")
    for v, ks in sorted(dups.items()):
        print("   %-22s <- %s" % (v, ", ".join(ks)))
if latin:
    print("\nОСТАЛОСЬ ЛАТИНИЦЕЙ: %s" % ", ".join(sorted(latin)))
print("\nна вычитку (первые 40):")
for k, b, s in need[:40]:
    print("   %-22s %-22s %s" % (k, out.get(k, "— НЕТ —"), "(%s/%s)" % (b, s)))
if miss:
    print("\nБЕЗ ПЕРЕВОДА:", miss[:20])

if not a.apply:
    print("\nпоказ. С --apply — запишет в реестр с пометкой auto.")
    sys.exit(0)

reg.setdefault("labels_auto", [])
for k, v in out.items():
    labels[k] = {"ru": v, "en": k}
    if k not in reg["labels_auto"]:
        reg["labels_auto"].append(k)
json.dump(reg, io.open(REG, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("\nзаписано подписей: %d, помечено auto: %d" % (len(out), len(reg["labels_auto"])))
