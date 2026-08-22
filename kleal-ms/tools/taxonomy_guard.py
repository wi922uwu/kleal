# -*- coding: utf-8 -*-
"""Сторож дополнений таксономии: доказать, что правка сдвинула ТОЛЬКО то, ради чего затевалась.

ЗАЧЕМ. Добавить узел легко, а последствия неочевидны: узел даёт слову семью, а семья — соседство
СО ВСЕМИ её обитателями. Один неверный родитель тихо перетасовывает выдачи у сотен людей, и
заметить это по глазам невозможно. Governance в matching_core проверяет ровно шесть эталонных пар —
для правки на десятки узлов этого мало.

КАК. Берём реальные пары из живой популяции: (темы запроса × интересы человека). Считаем уровень
сходства ДО дополнения и ПОСЛЕ. Требование одно и оно жёсткое:

    уровень пары имеет право измениться ТОЛЬКО если в паре участвует слово, которое мы трогали.

Всё остальное обязано совпасть побайтно. Выросший уровень у пары, к дополнению не относящейся, —
это ошибка родителя или слишком широкий алиас, и запуск падает с перечислением таких пар.

    python3 tools/taxonomy_guard.py                     # на живой популяции (users.json)
    python3 tools/taxonomy_guard.py --pairs 40000       # больше пар — дольше и надёжнее
"""
import argparse
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)


def _norm(s):
    return " ".join(str(s or "").lower().split())


def _load_interests(path):
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    users = d.get("users") if isinstance(d, dict) else d
    out = []
    for u in (users or []):
        ints = [_norm(i) for i in (u.get("interests") or []) if _norm(i)]
        if ints:
            out.append(ints)
    return out


def _touches_extra(word):
    """Достаёт ли слово до правки — по УЗЛУ, а не по буквам.

    Первая версия сверяла слово со списком добавленных имён, и это было уже реальности: канон
    подхватывает и словоизменение, поэтому `mosaic` резолвился через новый испанский алиас
    `mosaico` (разница в один символ) и выглядел посторонним, хотя правку задевал напрямую.
    Путей до правки ДВА, и вторая версия сторожа знала только первый:
      1) слово приходит в НОВЫЙ узел;
      2) слово приходит куда угодно, но ЧЕРЕЗ новый алиас, — а таких большинство, потому что
         алиасы к существующим узлам и есть основная часть правки (372 из 425).
    Плюс словоизменение: `mosaic` достаёт до нового алиаса `mosaico` разницей в один символ.
    """
    from matching_core.taxonomy import canonical as C
    w = C._norm(word)
    if not w:
        return False
    nid = C.resolve_node(word)
    if nid and nid in C.EXTRA_NODES:
        return True                                        # путь 1
    if w in C.EXTRA_ALIASES:
        return True                                        # путь 2, дословно
    for a in C.EXTRA_ALIASES:                              # путь 2, через словоизменение
        if len(a) >= 5 and len(w) >= 4 and abs(len(a) - len(w)) <= C._MORPH_TAIL \
                and (a.startswith(w) or w.startswith(a)):
            return True
    return False


def _levels(pairs):
    """Уровни пар при ТЕКУЩЕМ состоянии модулей таксономии (перезагружаются вызывающим)."""
    from matching_core.taxonomy import graph as G
    return [G.similarity([t], [x])[0] for t, x in pairs]


def _reload(extra_on, extra_path, stash):
    """Перезагрузить таксономию с дополнением или без него."""
    if not extra_on:
        os.replace(extra_path, stash)
    elif os.path.exists(stash):
        os.replace(stash, extra_path)
    for m in [k for k in list(sys.modules) if k.startswith("matching_core.taxonomy")]:
        del sys.modules[m]
    from matching_core.taxonomy import canonical as C  # noqa: F401  перечитывает файлы при импорте


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", default=os.path.join(ROOT, "users.json"))
    ap.add_argument("--pairs", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    extra = os.path.join(ROOT, "matching_core", "taxonomy", "canonical_extra.json")
    stash = extra + ".off"

    rows = _load_interests(a.users)
    if not rows:
        print("популяция пуста — сверять нечего")
        return 2
    rnd = random.Random(a.seed)
    vocab = sorted({w for r in rows for w in r})
    pairs = [(rnd.choice(vocab), rnd.choice(rnd.choice(rows))) for _ in range(a.pairs)]
    print("пар для сверки: %d (словарь %d)" % (len(pairs), len(vocab)))

    try:
        _reload(False, extra, stash)          # без дополнения
        before = _levels(pairs)
        _reload(True, extra, stash)           # с дополнением
        after = _levels(pairs)
    finally:
        if os.path.exists(stash):             # что бы ни случилось — файл на месте
            os.replace(stash, extra)

    from matching_core.taxonomy import canonical as C
    print("узлов в дополнении: %d, алиасов: %d" % (len(C.EXTRA_NODES), len(C.EXTRA_ALIASES)))
    changed = [i for i in range(len(pairs)) if before[i] != after[i]]
    stray = [i for i in changed
             if not _touches_extra(pairs[i][0]) and not _touches_extra(pairs[i][1])]
    grew = sum(1 for i in changed if after[i] > before[i])
    print("\nизменилось пар: %d (из них выросло %d)" % (len(changed), grew))
    for i in changed[:12]:
        print("   %-28s ~ %-28s %s -> %s" % (pairs[i][0][:28], pairs[i][1][:28], before[i], after[i]))
    if stray:
        print("\nПОСТОРОННИЕ СДВИГИ: %d — правка задела пары, к которым не относится" % len(stray))
        for i in stray[:15]:
            print("   %-28s ~ %-28s %s -> %s" % (pairs[i][0][:28], pairs[i][1][:28], before[i], after[i]))
        return 1
    print("\nпосторонних сдвигов нет: изменились только пары со словами правки")
    return 0


if __name__ == "__main__":
    sys.exit(main())
