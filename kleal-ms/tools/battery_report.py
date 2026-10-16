# -*- coding: utf-8 -*-
"""Что показала батарея за последние прогоны: python3 tools/battery_report.py [сколько]"""
import sys
HIST = "/root/kleal-archive/battery-history.tsv"
n = int(sys.argv[1]) if len(sys.argv) > 1 else 15
try:
    rows = [l.rstrip("\n").split("\t") for l in open(HIST, encoding="utf-8")]
except FileNotFoundError:
    print("прогонов ещё не было"); raise SystemExit(0)
head, data = rows[0], rows[1:]
print("%-17s %-6s %-6s %-5s %-7s %-7s %-6s %s" % ("время", "сцен", "собр", "бед", "медиана", "p95", "сбоев", "виды"))
for r in data[-n:]:
    if len(r) < 11:
        continue
    print("%-17s %-6s %-6s %-5s %-7s %-7s %-6s %s" % (r[0], r[1], r[2], r[3], r[6] + "с", r[7] + "с", r[8], r[4]))
if len(data) >= 2:
    beds = [int(r[3]) for r in data if len(r) > 3 and r[3].isdigit()]
    print()
    print("прогонов: %d | бед: сейчас %d, в среднем %.1f, лучший %d, худший %d"
          % (len(beds), beds[-1], sum(beds) / len(beds), min(beds), max(beds)))
