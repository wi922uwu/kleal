# -*- coding: utf-8 -*-
"""Одно глобальное имя — одно определение. Сторож класса ошибок, который уже стоил часов.

    python3 tools/dup_names_check.py        # код 1, если нашлось

26.09.2026 индекс людей в matching/app.py назвали `_IDX` — тем же именем, что у словаря категорий
выше по файлу, — и при импорте он его затёр: подбор несколько часов не узнавал ни одного интереса,
а все смоуки были зелёными. Там же функцию пула назвали `_load_store`, как загрузку хранилища.
В файлах по десять тысяч строк второе определение не видно глазами; здесь оно видно всегда.

Смотрит только верхний уровень модулей служб и shared/ (не тесты, не tools/). Повтор допустим,
если он нарочный, — тогда имя вносится в ALLOWED с объяснением.
"""
import ast
import collections
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ALLOWED = set()


def scan(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    seen = collections.defaultdict(list)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            seen[node.name].append(node.lineno)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    seen[t.id].append(node.lineno)
    return {n: ls for n, ls in seen.items() if len(ls) > 1 and not n.startswith("__")
            and (os.path.relpath(path, ROOT), n) not in ALLOWED}


def main():
    bad = 0
    for sub in ("services", "shared"):
        for dp, dn, fn in os.walk(os.path.join(ROOT, sub)):
            if "__pycache__" in dp:
                continue
            for f in sorted(fn):
                # «._имя.py» — спутники macOS из tar, не код (и не UTF-8).
                if f.endswith(".py") and not f.startswith(("test_", "._")):
                    for name, lines in scan(os.path.join(dp, f)).items():
                        bad += 1
                        print("  ДВАЖДЫ %s: %s — строки %s" % (os.path.relpath(os.path.join(dp, f), ROOT),
                                                             name, lines))
    print("итог: %s" % ("чисто" if not bad else "%d повторов" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
