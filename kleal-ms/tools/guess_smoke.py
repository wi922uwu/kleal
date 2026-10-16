# -*- coding: utf-8 -*-
"""Сторож карты догадок: пустая карта ничего не меняет; догадка не даёт 4; одинаковый текст — 4; сеть не трогается.
    python3 tools/guess_smoke.py [--root=...]"""
import io, json, os, sys, tempfile
ROOT = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--root=")), os.environ.get("KLEAL_ROOT") or "/opt/kleal/kleal-ms")
sys.path.insert(0, ROOT)
import socket
_real = socket.socket
class _NoNet(_real):
    def connect(self, *a, **k):
        raise RuntimeError("поиск пошёл в сеть")
socket.socket = _NoNet
from matching_core.taxonomy import canonical as C, graph as G
fails = []
def check(name, ok, extra=""):
    print(("  ok  " if ok else "FAIL  ") + name + ("" if ok else "  -> " + str(extra)))
    if not ok: fails.append(name)
pairs = [(["coffee"], ["coffee and conversation", "dinner"]), (["padel"], ["padel", "tennis"]), (["labubu"], ["labubu"]),
         (["мороженое"], ["pizza", "street food"]), (["zzkx"], ["qqwy"]), (["walking"], ["park walk", "dog-friendly walk"])]
C._GUESS.update({"t": 1e18, "words": {}, "memo": {}})          # пустая карта, без перечитывания
base = [G.similarity_detail(t, x)[0] for t, x in pairs]
check("одинаковый незнакомый текст — 4", base[2] == 4, base[2])
C._GUESS["memo"] = {}
C._GUESS["words"] = {C._norm("мороженое"): "F_food_out", C._norm("labubu"): "F_tabletop"}
after = [G.similarity_detail(t, x)[0] for t, x in pairs]
for (t, x), b, a in zip(pairs, base, after):
    check("не ниже прежнего: %s ~ %s (%s -> %s)" % (t, x, b, a), a >= b, (b, a))
check("догадка даёт 2 за семью (мороженое ~ pizza)", after[3] == 2, after[3])
check("одинаковый текст остаётся 4 и с картой (labubu)", after[2] == 4, after[2])
check("незнакомое без карты — 0", after[4] == 0, after[4])
check("канон решает сам: coffee не изменился", after[0] == base[0], (base[0], after[0]))
print("\nСБОЕВ: %d" % len(fails)); sys.exit(1 if fails else 0)
