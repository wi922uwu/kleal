# -*- coding: utf-8 -*-
"""Лента приглашений главного экрана: /api/agent/home-invites.

    python3 tools/home_invites_smoke.py [http://127.0.0.1:7074]

Ручка склеивает два источника — заявки 1:1 и групповые приглашения — в один список, из которого
главная строит стопку (борд GR.01 «Invite Stack»). Проверяется ровно то, на чём такая склейка
ломается: форма строки, отбор по состоянию и порядок.

Форма важнее остального. Клиент (`homeInvites` в kleal-app/src/home.ts) молча ОТБРАСЫВАЕТ строки
без `id` или с незнакомым `type`, поэтому ошибка в имени поля выглядит не как ошибка, а как
«приглашений нет» — и искать её будут на экране, а не здесь.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7074").rstrip("/")
R = {"ok": 0, "fail": 0}
FAILED = []
S = int(time.time() * 1000) % 100000000 + os.getpid()
ME = "HiMe%d" % S
A = "HiFrom%d" % S
B = "HiOwner%d" % S
C = "HiCo%d" % S


def call(path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + urllib.parse.quote(path, safe="/?&=%"), data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return {"_http": e.code, "_body": e.read().decode("utf-8", "replace")[:200]}
    except Exception as e:
        return {"_err": "%s: %s" % (type(e).__name__, str(e)[:140])}


def check(name, cond, detail=""):
    R["ok" if cond else "fail"] += 1
    if not cond:
        FAILED.append(name)
    print(("  ok   " if cond else "  FAIL ") + name + (("   " + str(detail)[:130]) if detail else ""))


def feed(who=ME):
    return call("/api/agent/home-invites?self=%s" % who).get("invites")


def keep(row):
    """ПОРТ клиентского фильтра из kleal-app/src/home.ts — что он вообще покажет."""
    return bool(row) and bool(row.get("id")) and row.get("type") in ("one_to_one", "group")


print("=" * 76)
print("1. ПУСТО — ЭТО ПУСТОЙ СПИСОК, А НЕ ОШИБКА")
print("=" * 76)
r = call("/api/agent/home-invites?self=%s" % ME)
check("ручка отвечает", r.get("ok") is True, r)
check("и отдаёт список", isinstance(r.get("invites"), list), r)
check("пока пустой", r.get("invites") == [], r.get("invites"))

print()
print("=" * 76)
print("2. ЗАЯВКА 1:1 ПОПАДАЕТ В ЛЕНТУ")
print("=" * 76)
p = call("/api/agent/propose", {"from": A, "to": ME, "note": "сходим за кофе?",
                                "intent": {"title": "Кофе в Грасии", "time": "чт 19:00",
                                           "mode": "offline", "area": "Gràcia",
                                           "address": "Carrer Verdi 12"},
                                "idem": "hp%d" % S})
check("заявка создана", bool(p.get("id")), p)
rows = feed()
check("в ленте одна строка", len(rows or []) == 1, rows)
row = (rows or [{}])[0]
check("тип назван так, как ждёт клиент", row.get("type") == "one_to_one", row.get("type"))
check("клиент такую строку не выбросит", keep(row), row)
check("отправитель — объектом с именем", (row.get("from") or {}).get("name") == A, row.get("from"))
check("интент разложен по полям карточки",
      (row.get("intent") or {}).get("title") == "Кофе в Грасии"
      and (row.get("intent") or {}).get("when") == "чт 19:00"
      and (row.get("intent") or {}).get("area") == "Gràcia", row.get("intent"))
check("записка донесена", row.get("note") == "сходим за кофе?", row.get("note"))
check("время строкой, а не числом", isinstance(row.get("created_at"), str) and row["created_at"],
      row.get("created_at"))
# OF.09: точный адрес в приглашение не отдаётся — так же, как в inbox.
check("точного адреса в ленте НЕТ", "Carrer Verdi" not in json.dumps(row, ensure_ascii=False), row)
check("чужую заявку не видно", feed(C) == [], feed(C))

print()
print("=" * 76)
print("3. ГРУППОВОЕ ПРИГЛАШЕНИЕ — В ТОЙ ЖЕ ЛЕНТЕ")
print("=" * 76)
g = call("/api/agent/gintent-create", {"self": B, "title": "Падел",
                                       "intent": {"topics": ["padel"], "mode": "offline",
                                                  "place": "Gràcia", "time": "сб 10:00"},
                                       "idem": "hg%d" % S})
GID = ((g or {}).get("group") or {}).get("gid")
def invite_id(resp):
    """Одиночное приглашение сервер отдаёт в `invite`, батч — списком `sent`. Обе формы законные,
    и брать надо ту, что пришла: раньше здесь читалась только вторая, C в группу не входил, и
    проверка «видно, кто уже внутри» проходила на одном организаторе — то есть ни на чём."""
    return ((resp or {}).get("invite") or {}).get("id") or \
        (((resp or {}).get("sent") or [{}])[0] or {}).get("id")


c_inv = invite_id(call("/api/agent/gintent-invite", {"gid": GID, "self": B, "to": C,
                                                     "idem": "hgc%d" % S}))
check("второго позвали", bool(c_inv), c_inv)
joined = call("/api/agent/ginvite-respond", {"id": c_inv, "self": C, "accept": True,
                                             "idem": "hgca%d" % S})
check("и он вошёл — в группе теперь двое",
      ((joined.get("group") or {}).get("joined_count")) == 2, joined.get("group"))
IID = invite_id(call("/api/agent/gintent-invite", {"gid": GID, "self": B, "to": ME,
                                                   "idem": "hgm%d" % S}))
check("приглашение мне ушло", bool(IID), IID)
rows = feed()
grp = next((x for x in (rows or []) if x.get("type") == "group"), None)
check("групповая строка в ленте есть", bool(grp), rows)
check("и клиент её не выбросит", keep(grp or {}), grp)
check("зовущий назван", (grp.get("from") or {}).get("name") == B, grp.get("from"))
check("блок группы на месте", bool(grp.get("group")), grp.get("group"))
check("gid отдан — по нему открывается комната",
      (grp.get("group") or {}).get("gid") == GID, (grp.get("group") or {}).get("gid"))
parts = ((grp.get("group") or {}).get("participants")) or []
check("видно ОБОИХ, кто уже внутри", len(parts) == 2, parts)
check("и это организатор со вторым, а не приглашённый я",
      {p.get("name") for p in parts} == {B, C}, parts)
check("счётчик совпадает со списком",
      (grp.get("group") or {}).get("participant_count") == len(parts), grp.get("group"))
check("потолок отдан", (grp.get("group") or {}).get("max_size"), grp.get("group"))
check("условия встречи взяты у ИНТЕНТА группы, а не выдуманы",
      (grp.get("intent") or {}).get("title") == "Падел"
      and (grp.get("intent") or {}).get("area") == "Gràcia", grp.get("intent"))
# GR.16 обещает приглашённому «кто уже внутри», а не «кого ещё позвали».
check("список приглашённых наружу не идёт",
      "invites" not in json.dumps(grp.get("group"), ensure_ascii=False), grp.get("group"))

print()
print("=" * 76)
print("4. В ЛЕНТЕ ТОЛЬКО ТО, НА ЧТО ЕЩЁ МОЖНО ОТВЕТИТЬ")
print("=" * 76)
check("сейчас в ленте двое", len(feed() or []) == 2, feed())
check("новее — сверху", (feed() or [{}])[0].get("type") == "group", [x.get("type") for x in feed()])
call("/api/agent/respond", {"id": p.get("id"), "self": ME, "decision": "decline"})
rows = feed()
check("отклонённая заявка из ленты ушла",
      not any(x.get("id") == p.get("id") for x in (rows or [])), rows)
check("групповое осталось", len(rows or []) == 1, rows)
call("/api/agent/ginvite-respond", {"id": IID, "self": ME, "accept": False, "idem": "hd%d" % S})
check("отвеченное групповое тоже ушло", feed() == [], feed())

print()
print("=" * 76)
print("РЕЗУЛЬТАТ: %d ok, %d проблем" % (R["ok"], R["fail"]))
for f in FAILED:
    print("   -", f)
sys.exit(1 if R["fail"] else 0)
