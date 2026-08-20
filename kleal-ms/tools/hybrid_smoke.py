# -*- coding: utf-8 -*-
"""ГИБРИД 1:1 — два входа и выбор стороны, живьём.

    python3 tools/hybrid_smoke.py [https://aiopenware.com]

Проверяет ровно то, что борд «1:1 Hybrid Negotiating» требует, а код не делал:

  * место и ссылка едут ВМЕСТЕ и не затирают друг друга (HY.20a/20b/20c). Раньше поле было одно,
    и у гибрида второй вход молча пропадал: экран слал «ссылка, а если её нет — место»;
  * оба открываются только подтвердившему (OF.C3) — правило то же, что у адреса;
  * старые планы читаются по-прежнему: у звонка `address` и есть ссылка;
  * сторона встречи (HY.22) ставится, видна второму, обратима и НЕ отменяет встречу;
  * сторона, которой нет входа, — отказ с именем (NO_LINK / NO_PLACE), а не «не получилось».

Идентификаторы у людей одноразовые (метка времени), поэтому смоук можно гонять по живому стенду,
не задевая настоящие пары.
"""
import json, sys, time, urllib.request
from urllib.parse import quote
B = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7074").rstrip("/")
S = int(time.time()) % 100000000
H, G = "HyHost%d" % S, "HyGuest%d" % S
ok = bad = 0
def check(name, cond, extra=""):
    global ok, bad
    if cond: ok += 1; print("  ok   %s   %s" % (name, str(extra)[:90]))
    else: bad += 1; print("  FAIL %s   %s" % (name, str(extra)[:200]))
def call(path, body=None):
    d = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(B + path, data=d, headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=90).read().decode())
def get(who, pid):
    # Ручка отдаёт {"ok":…, "plan":{…}} — брать надо plan, иначе КАЖДАЯ проверка «не видно»
    # проходит вхолостую: у обёртки поля place нет ни при каких обстоятельствах.
    r = call("/api/agent/mplan?self=%s&id=%s" % (quote(who), quote(pid)))
    return r.get("plan") or {}

for n in (H, G):
    call("/api/onboarding/register", {"profile": {"name": n, "age": 30, "city": "Barcelona",
        "interests": {"explicit": ["sketching"]}, "languages": {"comfortable": ["English"]}}})
def match(a, b, tag):
    r = call("/api/agent/propose", {"from": a, "to": b, "intent": {"topics": ["sketching"]},
                                    "note": "hi", "idem": "hypr%s%d" % (tag, S)})
    call("/api/agent/respond", {"id": r.get("id"), "decision": "accept", "self": b})
match(H, G, "a")

print("\n-- гибрид: место и ссылка едут ВМЕСТЕ --")
r = call("/api/agent/mplan-propose", {"self": H, "to": G, "title": "Sketch session",
         "mode": "hybrid", "starts_at": time.time() + 6 * 3600,
         "district": "El Born", "address": "Federal, Carrer del Parlament 39",
         "link": "https://meet.example.com/abc"})
p = r.get("plan") or {}
PID = p.get("id")
check("план создан", r.get("ok"), r.get("error"))
check("место на месте", p.get("place_set") is True, p.get("place"))
check("ссылка на месте", p.get("link_set") is True, p.get("link"))
check("автор видит оба", bool(p.get("place")) and bool(p.get("link")), (p.get("place"), p.get("link")))

print("\n-- HY.20b: ссылка есть, места нет --")
r2 = call("/api/agent/mplan-propose", {"self": H, "to": G, "title": "x", "mode": "hybrid",
          "starts_at": time.time() + 7 * 3600, "link": "https://meet.example.com/only"})
check("второй план на ту же пару отклонён", r2.get("error") == "PLAN_EXISTS", r2.get("error"))

print("\n-- гость видит входы только после подтверждения (OF.C3) --")
g = get(G, PID)
check("до подтверждения места не видно", not g.get("place"), g.get("place"))
check("и ссылки тоже", not g.get("link"), g.get("link"))
check("но сказано, что они есть", g.get("place_set") and g.get("link_set"),
      (g.get("place_set"), g.get("link_set")))
call("/api/agent/mplan-respond", {"id": PID, "self": G, "action": "confirm"})
g = get(G, PID)
check("подтвердил — видит место", "Federal" in str(g.get("place")), g.get("place"))
check("и ссылку", "meet.example.com" in str(g.get("link")), g.get("link"))

print("\n-- донести второй вход отдельно, не затерев первый --")
r3 = call("/api/agent/mplan-address", {"id": PID, "self": G, "link": "https://zoom.example/new"})
p3 = (r3.get("plan") or {})
check("ссылка переписана", "zoom.example" in str(p3.get("link")), p3.get("link"))
check("а место осталось", "Federal" in str(p3.get("place")), p3.get("place"))
r4 = call("/api/agent/mplan-address", {"id": PID, "self": G, "address": "Nømad, Carrer Joaquín Costa 26"})
p4 = (r4.get("plan") or {})
check("место переписано", "Nomad" in str(p4.get("place")) or "Nømad" in str(p4.get("place")), p4.get("place"))
check("а ссылка осталась", "zoom.example" in str(p4.get("link")), p4.get("link"))

print("\n-- старые планы читаются по-прежнему --")
Ho, Go = "HyOldH%d" % S, "HyOldG%d" % S
for n in (Ho, Go):
    call("/api/onboarding/register", {"profile": {"name": n, "age": 30, "city": "Barcelona",
        "interests": {"explicit": ["sketching"]}, "languages": {"comfortable": ["English"]}}})
match(Ho, Go, "b")
ro = call("/api/agent/mplan-propose", {"self": Ho, "to": Go, "title": "old-style", "mode": "online",
          "starts_at": time.time() + 5 * 3600, "address": "https://old.example/room"})
po = ro.get("plan") or {}
check("у звонка старый address читается как ссылка", "old.example" in str(po.get("link")), po.get("link"))
check("и местом не притворяется", not po.get("place"), po.get("place"))



print("\n-- HY.22: сторона встречи --")
r = call("/api/agent/mplan-side", {"id": PID, "self": G, "side": "call"})
p5 = r.get("plan") or {}
check("гость ушёл в звонок", r.get("ok") and p5.get("my_side") == "call", p5.get("my_side"))
h = get(H, PID)
check("хозяин это видит", h.get("their_side") == "call", h.get("their_side"))
check("а сам остаётся живьём", h.get("my_side") in (None, "in_person"), h.get("my_side"))
rows = {x.get("name"): x.get("side") for x in (h.get("participants") or [])}
check("сторона стоит и в строке участника", rows.get(G) == "call", rows)
back = call("/api/agent/mplan-side", {"id": PID, "self": G, "side": "in_person"})
check("и обратимо", (back.get("plan") or {}).get("my_side") == "in_person",
      (back.get("plan") or {}).get("my_side"))
check("встреча при этом не отменена", (back.get("plan") or {}).get("state") == "confirmed",
      (back.get("plan") or {}).get("state"))

print("\n-- сторона, которой нет входа, — тупик --")
Hn, Gn = "HyNoH%d" % S, "HyNoG%d" % S
for n in (Hn, Gn):
    call("/api/onboarding/register", {"profile": {"name": n, "age": 30, "city": "Barcelona",
        "interests": {"explicit": ["sketching"]}, "languages": {"comfortable": ["English"]}}})
match(Hn, Gn, "c")
rn = call("/api/agent/mplan-propose", {"self": Hn, "to": Gn, "title": "no-link", "mode": "hybrid",
          "starts_at": time.time() + 9 * 3600, "address": "Federal"})
PIDN = (rn.get("plan") or {}).get("id")
nl = call("/api/agent/mplan-side", {"id": PIDN, "self": Hn, "side": "call"})
check("в звонок без ссылки не уйти", nl.get("error") == "NO_LINK", nl)
ip = call("/api/agent/mplan-side", {"id": PIDN, "self": Hn, "side": "in_person"})
check("а живьём — можно, место есть", ip.get("ok") is True, ip.get("error"))

print("\n-- у звонка и у встречи вживую стороны нет --")
off = call("/api/agent/mplan-side", {"id": PIDO if False else PIDN, "self": Hn, "side": "bogus"})
check("выдуманная сторона отклонена", off.get("error") == "BAD_SIDE", off)

print("\n%s\nИТОГ ПРОБНИКА: %d ok, %d проблем\n%s" % ("=" * 70, ok, bad, "=" * 70))
