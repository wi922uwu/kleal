# -*- coding: utf-8 -*-
"""Мерка слоя цензуры на корпусе красной команды.

    python3 tools/safety_bench.py <каталог>

Считает ровно две цифры, и обе важны в разные стороны:

  ПРОПУЩЕНО — обход, который слой не остановил. Дырка в защите.
  ЛОЖНО     — безобидное сообщение, которое слой заблокировал. Сломанный продукт.

Вторая цифра не менее важна первой: фильтр, который блокирует «бабушка варила варенье, дай
рецепт» или «сын подсел, что делать», не защищает, а выгоняет людей — причём именно тех, кому
приложение нужнее всего.
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "shared"))
import safety as s


def load(path):
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    return [str(x) for x in rows if str(x).strip()]


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else "."
    att = {os.path.basename(p): load(p) for p in sorted(glob.glob(os.path.join(d, "attack_*.json")))}
    ben = {os.path.basename(p): load(p) for p in sorted(glob.glob(os.path.join(d, "benign_*.json")))}

    print("=" * 74)
    print("ОБХОДЫ (должны блокироваться)")
    print("=" * 74)
    missed = []
    for name, rows in att.items():
        bad = [t for t in rows if s.check(t)[0] != "block"]
        missed += [(name, t) for t in bad]
        print("  %-20s поймано %3d из %3d" % (name, len(rows) - len(bad), len(rows)))

    print("\n" + "=" * 74)
    print("БЕЗОБИДНОЕ (блокировать нельзя)")
    print("=" * 74)
    false = []
    for name, rows in ben.items():
        bad = [t for t in rows if s.check(t)[0] == "block"]
        false += [(name, t) for t in bad]
        print("  %-20s пропущено %3d из %3d" % (name, len(rows) - len(bad), len(rows)))

    nA = sum(len(v) for v in att.values()) or 1
    nB = sum(len(v) for v in ben.values()) or 1
    print("\nПРОПУЩЕНО обходов: %d из %d (%.0f%%)" % (len(missed), nA, 100.0 * len(missed) / nA))
    print("ЛОЖНЫХ блокировок: %d из %d (%.0f%%)" % (len(false), nB, 100.0 * len(false) / nB))

    if missed:
        print("\n-- что прошло (первые 25):")
        for n, t in missed[:25]:
            print("   [%s] %s" % (n[7:9], t[:96]))
    if false:
        print("\n-- что зря заблокировано (первые 25):")
        for n, t in false[:25]:
            print("   [%s] %s" % (n[7:9], t[:96]))


if __name__ == "__main__":
    main()
