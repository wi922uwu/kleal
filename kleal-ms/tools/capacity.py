#!/usr/bin/env python3
"""Сколько живых людей выдержит модель: задержка против числа одновременных запросов."""
import json, statistics, subprocess, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

URL = "http://127.0.0.1:7080/api/buddy/chat"
PROF = {"name": "Иван", "age": 30, "area": "Barcelona", "langs": ["ru"]}
SAYS = ["хочу поиграть в настолки в субботу", "давай вечером", "можно и кофе выпить"]


def one(i):
    t0 = time.time()
    try:
        body = {"messages": [{"role": "user", "content": SAYS[i % len(SAYS)]}],
                "lang": "ru", "profile": PROF}
        req = urllib.request.Request(URL, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=180).read()
        return time.time() - t0
    except Exception:
        return -1.0


def sweep(n, total=None):
    total = total or max(n * 3, 12)
    with ThreadPoolExecutor(max_workers=n) as p:
        ts = list(p.map(one, range(total)))
    ok = [t for t in ts if t > 0]
    bad = len(ts) - len(ok)
    if not ok:
        return (n, 0, 0, bad, 0)
    ok.sort()
    med = statistics.median(ok)
    p95 = ok[min(len(ok) - 1, int(0.95 * (len(ok) - 1)))]
    thr = len(ok) / (sum(ok) / max(n, 1))
    return (n, med, p95, bad, thr)


print("останавливаю батарею, даю дотечь…", flush=True)
subprocess.run(["systemctl", "stop", "kleal-battery"], check=False)
time.sleep(40)
try:
    print("%-6s %-9s %-9s %-7s %s" % ("в полёте", "медиана", "p95", "сбоев", "запросов/с"), flush=True)
    for n in (1, 4, 8, 16, 32, 64):
        n_, med, p95, bad, thr = sweep(n)
        print("%-9d %-9.1f %-9.1f %-7d %.2f" % (n_, med, p95, bad, thr), flush=True)
finally:
    subprocess.run(["systemctl", "start", "kleal-battery"], check=False)
    print("батарея поднята", flush=True)
