# -*- coding: utf-8 -*-
"""Сгенерировать дерево интересов для приложения из общего реестра.

До этого дерево жило отдельным литералом на 390 строк и знало 320 ключей из 447: остальные 128 не
имели подписи и на карту не попадали. Теперь источник один, и добавить интерес — значит дописать
строку в shared/interests.json, а не в двух местах.

СИНОНИМЫ СХЛОПЫВАЮТСЯ. В таксономии football и soccer — два ключа про одно и то же, и оба на карте
дали бы два одинаковых пузыря. На экран идёт канонический; второй по-прежнему понимается поиском.
"""
import ast, io, json, re, sys, argparse

REG = "/opt/kleal/kleal-ms/shared/interests.json"
WHEEL = "/opt/kleal/kleal-app/src/interests-wheel.ts"
OUT = "/opt/kleal/kleal-app/src/interests-tree.generated.ts"

ap = argparse.ArgumentParser(); ap.add_argument("--apply", action="store_true"); a = ap.parse_args()

reg = json.load(io.open(REG, encoding="utf-8"))
tree, lab, syn = reg["tree"], reg["labels"], reg["synonyms"]

# РАСШИРЕННЫЙ СЛОВАРЬ (26.09.2026): по 150 занятий на тему — для карты приложения. В `tree` реестра
# его нет НАМЕРЕННО: `tree` читают ранжировщик и промпт Буди V2 (весь словарь в каждом ходе), и
# 1200 лишних слов удлинили бы каждый ответ. Сюда он вливается в дерево ПРИЛОЖЕНИЯ: подкатегория
# с тем же именем дополняется, новая — добавляется в конец темы.
tree = {b: {s: list(ws) for s, ws in g.items()} for b, g in tree.items()}
for b, g in (reg.get("extended") or {}).items():
    for s, ws in g.items():
        tgt = tree.setdefault(b, {}).setdefault(s, [])
        tgt.extend(w for w in ws if w not in tgt)

# ---- значки категорий берём из нынешнего дерева: в реестре их нет, а выдумывать нечего
#
# ИСКАТЬ ИХ НАДО ТАМ, ГДЕ ОНИ ЕСТЬ. Раньше здесь читался interests-wheel.ts — файл, где дерево жило
# до переезда. Вызовов TOP() в нём не осталось, и `icons` собирался ПУСТЫМ; на место значка вставал
# сам ключ категории, и держалось это лишь на том, что у всех восьми имя значка совпадает с ключом.
# Разойдись они — категория тихо осталась бы без иконки. Опора — прошлый результат генерации.
src = io.open(WHEEL, encoding="utf-8").read()
ICON = re.compile(
    r"\bTOP\(\s*(['\"])(.+?)\1\s*,\s*(['\"])(.+?)\3\s*,\s*(['\"])(.+?)\5\s*,\s*(['\"])(.+?)\7\s*,\s*(['\"])(.+?)\9")
try:
    icon_src = io.open(OUT, encoding="utf-8").read()
except Exception:
    icon_src = src
icons = {m.group(2): m.group(10) for m in ICON.finditer(icon_src)}
if not icons:
    icons = {m.group(2): m.group(8) for m in re.finditer(
        r"\bTOP\(\s*(['\"])(.+?)\1\s*,\s*(['\"])(.+?)\3\s*,\s*(['\"])(.+?)\5\s*,\s*(['\"])(.+?)\7", src)}

# ---- нынешние ключи и подписи, чтобы сравнить
NODE = re.compile(r"\b(?:N|TOP)\(\s*(['\"])(.+?)\1\s*,\s*(['\"])(.+?)\3\s*,\s*(['\"])(.+?)\5")
# СРАВНИВАЕМ С ПРЕДЫДУЩИМ СГЕНЕРИРОВАННЫМ, А НЕ С ИСХОДНЫМ ФАЙЛОМ.
#
# Пока дерево лежало литералом в interests-wheel.ts, сравнение шло с ним. После переезда там
# осталась одна строка реэкспорта, и проверка стала показывать «добавилось 441» на каждом запуске —
# то есть перестала ловить что бы то ни было. А именно она поймала, что при первой генерации
# пропадал coworking. Теперь опорой служит прошлый результат генерации, если он есть.
try:
    prev_src = io.open(OUT, encoding="utf-8").read()
except Exception:
    prev_src = src
now = {m.group(2).lower(): (m.group(4), m.group(6)) for m in NODE.finditer(prev_src)}

# ---- что схлопнуть: ключ, объявленный синонимом другого, который сам есть в дереве
allk = set(tree) | {s for g in tree.values() for s in g} | {w for g in tree.values() for ws in g.values() for w in ws}
drop = {k for k, canon in syn.items() if k in allk and canon in allk and k != canon}
if drop:
    print("схлопнуто как синонимы (%d): %s" % (len(drop), ", ".join(sorted(drop))))

def lit(s):
    return "'" + str(s).replace("\\", "\\\\").replace("'", "\\'") + "'"

def label(k):
    """Три подписи. Испанская может отсутствовать — тогда T() покажет английскую, как и раньше."""
    row = lab.get(k) or {}
    return row.get("ru") or k, row.get("en") or k, row.get("es") or row.get("en") or k

lines = []
for broad, groups in tree.items():
    ru, en, es = label(broad)
    ic = icons.get(broad, broad)
    lines.append("  TOP(%s, %s, %s, %s, %s, [" % (lit(broad), lit(ru), lit(en), lit(es), lit(ic)))
    for sub, words in groups.items():
        sru, sen, ses = label(sub)
        kids = [w for w in words if w not in drop and w != sub]
        lines.append("    N(%s, %s, %s, %s, [" % (lit(sub), lit(sru), lit(sen), lit(ses)))
        for w in kids:
            wru, wen, wes = label(w)
            lines.append("      N(%s, %s, %s, %s)," % (lit(w), lit(wru), lit(wen), lit(wes)))
        lines.append("    ]),")
    lines.append("  ]),")

body = "\n".join(lines)
ts = '''/**
 * СГЕНЕРИРОВАННЫЙ ФАЙЛ. Не править руками.
 *
 * Источник: kleal-ms/shared/interests.json
 * Обновить: python3 kleal-ms/tools/gen_interests_tree.py --apply
 *
 * Дерево интересов для карты. Раньше оно было отдельным литералом и знало 320 ключей из 447 —
 * остальные не имели подписи и на карту не попадали. Теперь источник общий с сервером: добавить
 * интерес значит дописать строку в реестр, а не в двух местах, которые потом расходятся.
 *
 * Синонимы на экран не идут: football и soccer — один пузырь, второй по-прежнему понимается поиском.
 */
export type TreeNode = { key: string; ru: string; en: string; es: string; icon?: string; kids?: TreeNode[] };

const N = (key: string, ru: string, en: string, es: string, kids?: TreeNode[]): TreeNode =>
  ({ key, ru, en, es, kids });
const TOP = (key: string, ru: string, en: string, es: string, icon: string, kids: TreeNode[]): TreeNode =>
  ({ key, ru, en, es, icon, kids });

export const TREE: TreeNode[] = [
%s
];
''' % body

# ---- сравнение
gen = set(re.findall(r"\b(?:N|TOP)\('([^']+)'", ts))
print("\nключей: было %d, стало %d" % (len(now), len(gen)))
lost = sorted(set(now) - gen)
add = sorted(gen - set(now))
print("ПРОПАЛО: %d %s" % (len(lost), lost[:12]))
print("добавилось: %d %s" % (len(add), add[:12]))
badlab = [k for k in (set(now) & gen) if (lab.get(k) or {}).get("ru") and (lab.get(k) or {}).get("ru") != now[k][0]]
# Испанскую подпись не сверяем: она добавлена позже русской и английской, и на первом же
# запуске разошлась бы у всех 449 ключей — то есть проверка перестала бы что-либо значить.
print("подпись изменилась у: %d %s" % (len(badlab), badlab[:8]))

if not a.apply:
    print("\nпоказ. С --apply — запишет файл.")
    sys.exit(0)
io.open(OUT, "w", encoding="utf-8").write(ts)
print("\nзаписано:", OUT, "(%d строк)" % len(ts.splitlines()))
