# -*- coding: utf-8 -*-
"""Склад ветвей: складка кольца, дедупликация, ротация. Запуск: python3 test_battery_tree.py [кольцо]."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import battery_tree as BT  # noqa: E402

_fails = []


def check(name, ok, detail=""):
    print(("  ok  " if ok else "  FAIL") + " " + name + ("" if ok else "   " + str(detail)[:160]))
    if not ok:
        _fails.append(name)


ring = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "fixture", "ring.jsonl")
events = [json.loads(l) for l in open(ring, encoding="utf-8") if l.strip()]
now = max(float(e.get("t") or 0) for e in events) + 60

branches = BT.fold(events, now=now)
check("ветви сложились", 250 < len(branches) < 400, len(branches))
_empty = [b for b in branches if not b["turns"]]
check("ветви без ходов — редкость (обрыв кольца, сеть)", len(_empty) < len(branches) * 0.12, len(_empty))
withp = [b for b in branches if b["problems"]]
check("беды разобраны по видам", withp and all(p["kind"] for b in withp for p in b["problems"]))
check("bad не ниже числа бед", all(b["bad"] >= len(b["problems"]) for b in branches))
popup_silent = [b for b in branches if any(p["kind"] == "ПОПАП НЕ СРАБОТАЛ" for p in b["problems"])]
check("молчащий попап: fired=0 и popup=None", popup_silent and all(b["fired"] == 0 and b["popup"] is None for b in popup_silent), len(popup_silent))
fired = [b for b in branches if b["fired"]]
check("сработавший попап: лист попапа есть", fired and all(b["popup"] for b in fired))
ready = [b for b in branches if any(t["ready"] for t in b["turns"])]
check("ready стоит на ответе Kleal", all(all(t["k"] == "k" for t in b["turns"] if t["ready"]) for b in ready))
rounds = sorted(set(b["r"] for b in branches))
check("круг помечен отметкой run_start", len(rounds) >= 1 and rounds[-1] > 0, rounds)
at = [p["at"] for b in branches for p in b["problems"] if p["at"]]
check("«на ходу N» вытаскивается в at", bool(at), at[:5])

# незаконченное не складывается
open_only = [e for e in events if e.get("kind") != "scen_done"]
check("без scen_done ветвей нет", BT.fold(open_only, now=now) == [])
# ОТМЕТКА ПРОГОНА НЕ ТЕРЯЕТСЯ. Хвост кольца держит примерно один прогон, и сценарии, начавшиеся
# раньше его `run_start`, сваливались в мешок r=0 — одна жирная дуга поверх настоящих.
_no_start = [e for e in events if e.get("kind") != "run_start"]
_sirot = [b for b in BT.fold(_no_start, now=now) if not b["r"]]
check("без run_start ветви осиротели", len(_sirot) > 100, len(_sirot))
# Отметка должна быть НЕ ПОЗЖЕ начала сценария, а начало у части из них раньше самого
# хвоста кольца: `t0` берётся из `scen_done`, а не из первого события в хвосте.
_t_run = min(b["t0"] for b in branches) - 5
_spas = [b for b in BT.fold(_no_start, now=now, known=[_t_run]) if not b["r"]]
check("с известной отметкой — не осиротели", len(_spas) == 0, len(_spas))
check("и отметка взята именно та", all(b["r"] == _t_run for b in BT.fold(_no_start, now=now, known=[_t_run])))
check("чужая (более поздняя) отметка не липнет",
      all(not b["r"] for b in BT.fold(_no_start, now=now, known=[now + 1000])))
# тишина ещё не наступила
check("сразу после конца не складываем", BT.fold(events, now=max(float(e["t"]) for e in events) + 1) == [] or
      len(BT.fold(events, now=max(float(e["t"]) for e in events) + 1)) < len(branches))

# склад: дедупликация и хвост
d = tempfile.mkdtemp()
path = os.path.join(d, "tree.jsonl")
st = BT.Store(path=path, live=ring)
n1 = st.append(branches)
n2 = st.append(branches)
check("первая складка дописала всё", n1 == len(branches), n1)
check("повторная — ничего", n2 == 0, n2)
st2 = BT.Store(path=path, live=ring)
check("после перезапуска ключи помнятся", st2.append(branches) == 0)
tail = st2.tail(since=0, limit=10)
check("хвост отдаёт последние", len(tail) == 10 and tail[-1]["scen"] == branches[-1]["scen"])
# СЛОВА ХРАНЯТСЯ, НО В КОЛЬЦА НЕ ЕДУТ. Со скриншота владельца: у ветки из прошлого круга в панели
# оставалась одна строка вместо разговора — кольцо событий коротко, журналы перемешаны.
_wt = [b for b in branches if b["turns"]]
check("реплики легли в склад", _wt and all(any(t.get("txt") for t in b["turns"]) for b in _wt))
check("хвост для колец идёт без реплик", all(all("txt" not in t for t in b["turns"]) for b in tail))
check("а с thin=False — с репликами", any(any(t.get("txt") for t in b["turns"]) for b in st2.tail(0, 10, thin=False)))
_one = st2.find(_wt[-1]["scen"], _wt[-1]["t0"])
check("ветвь по метке находится целиком", _one and any(t.get("txt") for t in _one["turns"]), (_one or {}).get("scen"))
check("чужой метки нет", st2.find("нет-такого-сценария") is None)
# ХОЛОДНЫЙ СТАРТ: просим прогонами, а не строками — иначе после обновления страницы часть дуг
# не приезжает и картинка выглядит сброшенной.
_rt = st2.rounds_tail(1)
check("rounds_tail(1) — ровно один прогон", len(set(round(b["r"], 3) for b in _rt)) == 1, len(_rt))
check("rounds_tail(9) берёт все, что есть", len(st2.rounds_tail(9)) == len(branches), len(st2.rounds_tail(9)))
check("и он тоже без реплик", all(all("txt" not in t for t in b["turns"]) for b in _rt))
_t = st2.tail(0, 5)[0]
check("тонкая ветвь несёт только нужное кольцам",
      set(_t) == {"scen","t0","t1","r","lang","hard","src","done","bad","fired","turns","problems","master","intent"},
      sorted(_t))
check("в тонкой ветви не больше одного вида беды", all(len(b["problems"]) <= 1 for b in st2.tail(0, 50)))
import json as _j
_sz = sum(len(_j.dumps(b, ensure_ascii=False)) for b in st2.tail(0, 200)) / max(len(st2.tail(0, 200)), 1)
check("тонкая ветвь весит меньше 420 байт", _sz < 420, round(_sz))
check("реплика обрезана по TEXT_MAX", all(len(t.get("txt") or "") <= BT.TEXT_MAX for b in _wt for t in b["turns"]))
check("since режет по t1", len(st2.tail(since=now + 1)) == 0)
# ротация
BT.ROTATE_BYTES = 10
st3 = BT.Store(path=path, live=ring)
st3.seen = set()
st3.append(branches[:3])
check("ротация переименовала в .1", os.path.exists(path + ".1") and os.path.getsize(path) < 5000)
check("и хвост читает оба файла", len(st3.tail(since=0, limit=100000)) >= len(branches))

print()
if _fails:
    print("FAILED %d: %s" % (len(_fails), ", ".join(_fails)))
    sys.exit(1)
print("ALL PASS")
