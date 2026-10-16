# -*- coding: utf-8 -*-
"""Показ прогона в реальном времени: python3 tools/battery_watch.py [--all]

Следит за СВЕЖИМ журналом батареи и печатает разговоры по мере того, как они идут. Когда прогон
кончается и служба начинает новый — смотритель сам переходит на новый журнал, ждать не надо.

По умолчанию показывает только суть: реплику человека, ответ Kleal, итоговую затею и беды.
`--all` добавляет служебные строки (темы, роль, режим, что записалось).
"""
import glob
import os
import re
import sys
import time

FULL = "--all" in sys.argv
DIR = "/root/kleal-archive/battery"
G, R, Y, B, D, Z = "\033[32m", "\033[31m", "\033[33m", "\033[36m", "\033[2m", "\033[0m"


def newest():
    files = sorted(glob.glob(os.path.join(DIR, "buddy-battery-*.log")), key=os.path.getmtime)
    return files[-1] if files else None


def paint(line):
    s = line.rstrip("\n")
    if s.startswith("=" * 20):
        return ""                                     # разделитель — своя рамка ниже не нужна
    if s.startswith("СЦЕНАРИЙ"):
        return "\n%s▶ %s%s" % (Y, s[9:], Z)
    if s.startswith("   человек:"):
        return "   %s→%s %s" % (B, Z, s[11:].strip())
    if s.startswith("   Kleal:"):
        return "   %s←%s %s" % (D, Z, s[9:].strip())
    if s.startswith("   ЗАТЕЯ:"):
        return "   %s✓ %s%s" % (G, s[9:].strip(), Z)
    if "!!" in s:
        return "   %s%s%s" % (R, s.strip(), Z)
    if s.startswith("БАТАРЕЯ БАДДИ"):
        return "%s%s%s" % (Y, s, Z)
    if FULL and s.strip().startswith(("ready=", "предмет=", "вопросов")):
        return "     %s%s%s" % (D, s.strip(), Z)
    return ""


def follow():
    path, fh = None, None
    while True:
        latest = newest()
        if latest != path:
            if fh:
                fh.close()
            path, fh = latest, None
            if path:
                fh = open(path, encoding="utf-8", errors="replace")
                print("%s── журнал: %s%s" % (Y, os.path.basename(path), Z), flush=True)
        if not fh:
            time.sleep(2)
            continue
        line = fh.readline()
        if not line:
            time.sleep(0.4)
            continue
        out = paint(line)
        if out:
            print(out, flush=True)


try:
    follow()
except KeyboardInterrupt:
    print()
