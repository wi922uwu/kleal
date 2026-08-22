# -*- coding: utf-8 -*-
"""Экран группового плана: тот ли кадр борда покажется в каждом состоянии.

    python3 tools/gplan_screen_smoke.py [http://127.0.0.1:7074]

gplans_smoke.py проверяет ПРАВИЛА сервера. Здесь проверяется то, чего он не видит: что по ответу
сервера экран `kleal-app/app/gplan.tsx` выберет кадр борда, а не соседний. Логика выбора там одна
функция (`frameOf`) и живёт на флагах, которые сервер отдаёт, — значит её можно прогнать здесь и
поймать расхождение до симулятора, а не после.

Порядок веток повторяет `frameOf` дословно. Если он там поменяется, а здесь нет — тест соврёт;
поэтому ветки перечислены в том же порядке и с теми же именами.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7074").rstrip("/")
R = {"ok": 0, "fail": 0}
FAILED = []
S = int(time.time() * 1000) % 100000000 + os.getpid()
OWN = "ScrOwner%d" % S
M = ["ScrM%d_%d" % (S, i) for i in range(4)]


def call(path, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data,
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


def frame_of(plan, vote, is_owner):
    """ПОРТ `frameOf` из app/gplan.tsx. Один в один, включая порядок веток."""
    if not plan:
        return "none"
    st = plan.get("state")
    if st in ("cancelled", "done"):
        return "closed"
    if plan.get("started"):
        return "now"
    if st == "locked":
        return "locked"
    if st == "below_quorum":
        return "below"
    if plan.get("stay_or_leave"):
        return "stayOrLeave"
    if plan.get("accept_or_leave"):
        return "acceptOrLeave"
    if vote and vote.get("state") == "open":
        return "voteOpen"
    if vote and vote.get("state") == "closed" and not vote.get("decided"):
        return "voteDecide" if is_owner else "voteWait"
    if st == "proposed":
        return "fix" if plan.get("can_fix") else "proposed"
    return "confirmed"


def screen(who, gid):
    """Что экран увидит глазами `who`: группа, её план и голосование по нему."""
    g = (call("/api/agent/gintent?gid=%s&self=%s" % (gid, who)).get("group") or {})
    plan = g.get("plan")
    vote = None
    if plan:
        vs = call("/api/agent/gplans?self=%s" % who).get("votes") or []
        vote = next((v for v in vs if v.get("plan_id") == plan.get("id")), None)
    return frame_of(plan, vote, bool(g.get("i_am_owner"))), plan or {}, vote or {}, g


def make(tag, mode="offline", n=3):
    c = call("/api/agent/gintent-create", {"self": OWN, "title": "Экран " + tag,
                                           "intent": {"topics": ["coffee"], "mode": mode},
                                           "idem": "sc%s%d" % (tag, S)})
    gid = ((c or {}).get("group") or {}).get("gid")
    b = call("/api/agent/gintent-invite", {"gid": gid, "self": OWN, "to": M[:n],
                                           "idem": "si%s%d" % (tag, S)})
    for x in (b.get("sent") or []):
        call("/api/agent/ginvite-respond", {"id": x["id"], "self": x["to"], "accept": True})
    return gid


print("=" * 76)
print("A. ПУСТО → СОГЛАСОВАНИЕ → УТВЕРЖДЕНО (GR.25 → GR.26 → GR.34)")
print("=" * 76)
gid = make("a", n=2)                                   # организатор + двое = трое
f, p, v, g = screen(OWN, gid)
check("плана нет — кадр создания", f == "none", f)
check("и создавать его предложено организатору", g.get("i_am_owner") is True)
f2, _, _, _ = screen(M[0], gid)
check("участнику — тот же кадр, но без кнопки создания", f2 == "none", f2)

pb = call("/api/agent/gplan-begin", {"gid": gid, "self": OWN, "when": "чт 20:30",
                                     "place": "Gràcia · Nømad",
                                     "starts_at": time.time() + 40 * 3600, "idem": "sb%d" % S})
PID = ((pb or {}).get("plan") or {}).get("id")
f, p, v, _ = screen(M[0], gid)
check("план предложен — кадр согласования", f == "proposed", f)
check("раунд первый из трёх", (p.get("round"), p.get("max_rounds")) == (1, 3),
      [p.get("round"), p.get("max_rounds")])
check("строка места офлайновая", p.get("mode") == "offline" and p.get("place") == "Gràcia · Nømad",
      [p.get("mode"), p.get("place")])
check("ждём двоих", p.get("needs") == 2, p.get("needs"))
check("мой ответ ещё не дан", not p.get("my_response"), p.get("my_response"))

call("/api/agent/gplan-respond", {"id": PID, "self": M[0], "action": "confirm"})
f, p, _, _ = screen(M[0], gid)
check("подтвердил — кадр тот же, но кнопки «Подтвердить» уже нет",
      f == "proposed" and p.get("my_response") == "confirmed", [f, p.get("my_response")])
call("/api/agent/gplan-respond", {"id": PID, "self": M[1], "action": "confirm"})
f, p, _, _ = screen(M[0], gid)
check("подтвердили все — кадр утверждённого плана", f == "confirmed", f)
check("и раундов на нём больше не рисуем", p.get("state") == "confirmed", p.get("state"))

print()
print("=" * 76)
print("B. РАУНДЫ И ЗАКРЕПЛЕНИЕ (GR.27 → GR.29 → GR.30 → GR.31)")
print("=" * 76)
gidB = make("b", n=3)                                  # четверо
pb = call("/api/agent/gplan-begin", {"gid": gidB, "self": OWN, "when": "чт 19:00",
                                     "starts_at": time.time() + 40 * 3600, "idem": "sbb%d" % S})
PB = ((pb or {}).get("plan") or {}).get("id")
call("/api/agent/gplan-respond", {"id": PB, "self": M[0], "action": "counter", "when": "чт 20:00"})
f, p, _, _ = screen(M[1], gidB)
check("после встречного — второй раунд", p.get("round") == 2, p.get("round"))
check("закреплять ещё рано", f == "proposed" and not p.get("can_fix"), [f, p.get("can_fix")])
call("/api/agent/gplan-respond", {"id": PB, "self": M[1], "action": "counter", "when": "чт 20:30"})
f, p, _, _ = screen(M[1], gidB)
check("третий раунд — последний", p.get("round") == 3 and p.get("rounds_used_up") is True,
      [p.get("round"), p.get("rounds_used_up")])
fown, pown, _, _ = screen(OWN, gidB)
check("но пока согласных мало — кнопки «Закрепить» у организатора нет",
      fown == "proposed" and not pown.get("can_fix"), [fown, pown.get("can_fix")])
call("/api/agent/gplan-respond", {"id": PB, "self": OWN, "action": "confirm"})
call("/api/agent/gplan-respond", {"id": PB, "self": M[0], "action": "confirm"})
fown, pown, _, _ = screen(OWN, gidB)
check("трое согласны, раунды кончились — кадр закрепления", fown == "fix", fown)
check("и названы те, кого спросят «остаться или выйти»", M[2] in (pown.get("waiting") or []),
      pown.get("waiting"))
fm, _, _, _ = screen(M[2], gidB)
check("молчащему кадра закрепления НЕ показывают", fm == "proposed", fm)

call("/api/agent/gplan-fix", {"id": PB, "self": OWN, "idem": "sfx%d" % S})
fm, pm, _, _ = screen(M[2], gidB)
check("закрепили — молчавшему кадр «остаться или выйти»", fm == "stayOrLeave", fm)
fo, _, _, _ = screen(M[0], gidB)
check("подтвердившему — обычный утверждённый план", fo == "confirmed", fo)
call("/api/agent/gplan-respond", {"id": PB, "self": M[2], "action": "confirm"})
fm, _, _, _ = screen(M[2], gidB)
check("остался — и кадр стал общим", fm == "confirmed", fm)

print()
print("=" * 76)
print("C. ГОЛОСОВАНИЕ: ИДЁТ → ЗАКРЫТО → РЕШЕНО (GR.36 → GR.37/38)")
print("=" * 76)
vo = call("/api/agent/gplan-vote-open", {"id": PID, "self": M[0], "kind": "edit",
                                         "when": "пт 20:00", "idem": "svo%d" % S})
VID = ((vo or {}).get("vote") or {}).get("id")
f, _, v, _ = screen(M[1], gid)
check("голосование идёт — кадр голосования", f == "voteOpen", f)
check("срок виден", bool(v.get("closes_at")), v.get("closes_at"))
check("мой голос ещё не подан", v.get("my_vote") is None, v.get("my_vote"))
check("названо, кто попросил", v.get("by") == M[0], v.get("by"))
fo, _, vo2, _ = screen(OWN, gid)
check("организатору на этом шаге — тот же кадр, решать ещё нечего", fo == "voteOpen", fo)

call("/api/agent/gplan-vote", {"id": VID, "self": OWN, "yes": False})
call("/api/agent/gplan-vote", {"id": VID, "self": M[1], "yes": True})
fo, _, v, _ = screen(OWN, gid)
check("высказались все — организатору кадр решения", fo == "voteDecide", fo)
check("числа для строки «3 за · 1 против»", (v.get("yes"), v.get("no")) == (2, 1),
      [v.get("yes"), v.get("no")])
check("совет группы посчитан", v.get("advice") == "change", v.get("advice"))
fm, _, vm, _ = screen(M[1], gid)
check("участнику — кадр ожидания решения", fm == "voteWait", fm)
check("и он знает, что решает не он", vm.get("i_decide") is False, vm.get("i_decide"))

call("/api/agent/gplan-vote-decide", {"id": VID, "self": OWN, "apply": False, "idem": "svd%d" % S})
fo, po, vo3, _ = screen(OWN, gid)
check("решил оставить — вернулись к утверждённому плану", fo == "confirmed", fo)
check("время не изменилось", po.get("when") == "чт 20:30", po.get("when"))
check("голосование с экрана ушло", not vo3, vo3)

print()
print("=" * 76)
print("D. ПРАВКА ОРГАНИЗАТОРОМ (GR.32 → GR.33)")
print("=" * 76)
call("/api/agent/gplan-update", {"id": PID, "self": OWN, "when": "чт 21:00", "idem": "sup%d" % S})
fm, pm, _, _ = screen(M[0], gid)
check("участнику — кадр «принять или выйти»", fm == "acceptOrLeave", fm)
check("видно, что было", (pm.get("update") or {}).get("was", {}).get("when") == "чт 20:30",
      pm.get("update"))
check("и что стало", pm.get("when") == "чт 21:00", pm.get("when"))
fo, _, _, _ = screen(OWN, gid)
check("автору правки этого выбора не показывают", fo == "confirmed", fo)
call("/api/agent/gplan-respond", {"id": PID, "self": M[0], "action": "confirm"})
call("/api/agent/gplan-respond", {"id": PID, "self": M[1], "action": "confirm"})
fm, pm, _, _ = screen(M[0], gid)
check("приняли все — кадр снова обычный", fm == "confirmed" and not pm.get("update"),
      [fm, pm.get("update")])

print()
print("=" * 76)
print("E. ОНЛАЙН БЕЗ ССЫЛКИ (GRO.25 → GRO.25a)")
print("=" * 76)
gidO = make("o", mode="online", n=2)
po = call("/api/agent/gplan-begin", {"gid": gidO, "self": OWN, "when": "чт 20:30 Барселона",
                                     "starts_at": time.time() + 40 * 3600, "idem": "sbo%d" % S})
PO = ((po or {}).get("plan") or {}).get("id")
for n in M[:2]:
    call("/api/agent/gplan-respond", {"id": PO, "self": n, "action": "confirm"})
f, p, _, _ = screen(OWN, gidO)
check("онлайновый план утверждён", f == "confirmed", f)
check("экран знает, что он онлайновый", p.get("mode") == "online", p.get("mode"))
check("и что ссылки нет — главной кнопкой станет «Сохранить ссылку»",
      p.get("needs_link") is True, p.get("needs_link"))
check("места у онлайна нет — строка соберётся из режима", not p.get("place"), p.get("place"))
fm, pm, _, _ = screen(M[0], gidO)
check("участник тоже видит, что ссылки ещё нет", pm.get("needs_link") is True, pm.get("needs_link"))
call("/api/agent/gplan-link", {"id": PO, "self": OWN, "link": "https://meet.example/kleal",
                               "idem": "slk%d" % S})
f, p, _, _ = screen(M[0], gidO)
check("ссылка появилась — строка станет «ссылка сохранена»",
      p.get("needs_link") is False and p.get("link") == "https://meet.example/kleal",
      [p.get("needs_link"), p.get("link")])

print()
print("=" * 76)
print("F. КОНЕЦ ЖИЗНИ: ЗАМОК И ОТМЕНА")
print("=" * 76)
gidL = make("l", n=2)
pl = call("/api/agent/gplan-begin", {"gid": gidL, "self": OWN, "when": "скоро",
                                     "starts_at": time.time() + 2 * 3600 + 300, "idem": "sbl%d" % S})
PL = ((pl or {}).get("plan") or {}).get("id")
for n in M[:2]:
    call("/api/agent/gplan-respond", {"id": PL, "self": n, "action": "confirm"})
vl = call("/api/agent/gplan-vote-open", {"id": PL, "self": OWN, "kind": "edit", "when": "через час",
                                         "starts_at": time.time() + 3600})
VL = ((vl or {}).get("vote") or {}).get("id")
for n in M[:2]:
    call("/api/agent/gplan-vote", {"id": VL, "self": n, "yes": True})
call("/api/agent/gplan-vote-decide", {"id": VL, "self": OWN, "apply": True})
f, p, v, _ = screen(M[0], gidL)
check("встреча вошла в двухчасовое окно — кадр замка", f == "locked", f)
check("и голосований на нём не висит", not v, v)

vc = call("/api/agent/gplan-vote-open", {"id": PID, "self": OWN, "kind": "cancel", "idem": "svc%d" % S})
VC = ((vc or {}).get("vote") or {}).get("id")
for n in M[:2]:
    call("/api/agent/gplan-vote", {"id": VC, "self": n, "yes": True})
call("/api/agent/gplan-vote-decide", {"id": VC, "self": OWN, "apply": True, "idem": "svdc%d" % S})
# Отменённый план группа НЕ показывает: `_gp_of` его больше не отдаёт, а сама группа возвращается
# в chat_open. Это и есть нужное поведение — «отменили» не значит «группа кончилась»: те же люди
# остаются в чате и могут договориться заново. Экран поэтому снова предлагает завести план, а о
# самой отмене группе сказано строкой в ленте.
f, p, _, gg = screen(M[0], gid)
check("отменили — план с экрана ушёл, а группа осталась", f == "none" and not p, [f, p])
check("и группа вернулась в чат", gg.get("state") == "chat_open", gg.get("state"))
hist = call("/api/agent/gplans?self=%s" % OWN).get("history") or []
check("а сам план уехал в историю отменённым",
      any(x.get("id") == PID and x.get("state") == "cancelled" for x in hist),
      [(x.get("id"), x.get("state")) for x in hist])
again = call("/api/agent/gplan-begin", {"gid": gid, "self": OWN, "when": "сб 18:00",
                                        "starts_at": time.time() + 60 * 3600, "idem": "sag%d" % S})
check("и новый план завести можно", again.get("ok") is True, again)

print()
print("=" * 76)
print("G. GROUP HYBRID: НЕДОСТАЮЩИЙ ВХОД, СТОРОНЫ И LIVE-СТАТУСЫ")
print("=" * 76)
check("started имеет приоритет над locked и показывает активную встречу",
      frame_of({"state": "locked", "started": True}, None, False) == "now")

gidH1 = make("h1", mode="hybrid", n=2)
h1 = call("/api/agent/gplan-begin", {"gid": gidH1, "self": OWN, "when": "сб 18:00",
                                      "place": "Nømad", "starts_at": time.time() + 40 * 3600,
                                      "idem": "sh1%d" % S})
PH1 = ((h1 or {}).get("plan") or {}).get("id")
p = (screen(OWN, gidH1)[1])
check("место есть, ссылка отсутствует", p.get("needs_link") is True and not p.get("needs_place"), p)
bad = call("/api/agent/gplan-mode", {"id": PH1, "self": M[0], "mode": "offline"})
check("режим меняет только организатор", bad.get("error") == "NOT_ORGANIZER", bad)
off = call("/api/agent/gplan-mode", {"id": PH1, "self": OWN, "mode": "offline",
                                     "idem": "sh1m%d" % S})
check("без ссылки можно оставить план офлайновым",
      off.get("ok") is True and (off.get("plan") or {}).get("mode") == "offline", off)

gidH2 = make("h2", mode="hybrid", n=2)
h2 = call("/api/agent/gplan-begin", {"gid": gidH2, "self": OWN, "when": "сб 19:00",
                                      "link": "https://meet.example/hybrid",
                                      "starts_at": time.time() + 40 * 3600, "idem": "sh2%d" % S})
PH2 = ((h2 or {}).get("plan") or {}).get("id")
on = call("/api/agent/gplan-mode", {"id": PH2, "self": OWN, "mode": "online",
                                    "idem": "sh2m%d" % S})
check("без места можно оставить план онлайновым",
      on.get("ok") is True and (on.get("plan") or {}).get("mode") == "online", on)

gidH3 = make("h3", mode="hybrid", n=2)
h3 = call("/api/agent/gplan-begin", {"gid": gidH3, "self": OWN, "when": "сб 20:00",
                                      "place": "Nømad", "link": "https://meet.example/live",
                                      "starts_at": time.time() + 40 * 3600, "idem": "sh3%d" % S})
PH3 = ((h3 or {}).get("plan") or {}).get("id")
for n in M[:2]:
    call("/api/agent/gplan-respond", {"id": PH3, "self": n, "action": "confirm"})
side = call("/api/agent/gplan-side", {"id": PH3, "self": M[0], "side": "call",
                                      "idem": "sh3s%d" % S})
check("участник выбирает звонок, и счётчик обновляется",
      (side.get("plan") or {}).get("my_side") == "call"
      and ((side.get("plan") or {}).get("side_counts") or {}).get("call") == 1, side)
cant = call("/api/agent/gplan-status", {"id": PH3, "self": M[1], "status": "cant_make_it",
                                        "idem": "sh3c%d" % S})
check("«не смогу» сохраняется как live-статус",
      (((cant.get("plan") or {}).get("my_live") or {}).get("status")) == "cant_make_it", cant)
g3 = screen(OWN, gidH3)[3]
check("live-статус не удаляет человека из группы", len(g3.get("members") or []) == 3,
      [m.get("name") for m in (g3.get("members") or [])])

print()
print("=" * 76)
print("РЕЗУЛЬТАТ: %d ok, %d проблем" % (R["ok"], R["fail"]))
for f in FAILED:
    print("   -", f)
sys.exit(1 if R["fail"] else 0)
