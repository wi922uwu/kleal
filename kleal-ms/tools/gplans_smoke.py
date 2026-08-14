# -*- coding: utf-8 -*-
"""Group plans, layer 2: confirmation, counter-proposals, votes, the two-hour lock, feedback.

    python3 tools/gplans_smoke.py [http://127.0.0.1:7074]

Написан по БОРДУ (секции 2247:44703 офлайн и 2328:66035 онлайн), который в фазе плана отменяет
два прежних правила дейлика. Разбор расхождений — docs/GROUP_PLAN_BOARD_VS_BACKEND.md.

  1. ПОДТВЕРЖДАЮТ ВСЕ, а не трое: GR.26 «Waiting for everyone… The plan starts when all three
     confirm». Молчащего ждут, из состава не выбрасывают.
  2. РАУНДОВ ТРИ: GR.28/29 «Round 2 of 3», «Last round · after this the organiser fixes the plan».
     Четвёртое встречное предложение отклоняется (ROUNDS_USED_UP), дальше gp_fix.

  3. ГОЛОСОВАНИЕ СОВЕЩАТЕЛЬНОЕ: GR.35 «The result is advice — Marc makes the final call», GR.38
     «On Kleal the vote is advice — the organiser decides». Голоса СЧИТАЮТСЯ, план не трогают;
     решает организатор отдельным действием, и он вправе не послушать большинство.
  4. ПРАВКА СВЕРХУ: GR/GRO.32 — организатор меняет утверждённый план сам, а каждый участник
     заново «принимает или выходит» (GR.33). Раундом это не считается.
  5. ОНЛАЙН БЕЗ ССЫЛКИ: GRO.25a — план согласован, подключиться некуда; ссылку ставит организатор.
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
OWN = "GpOwner%d" % S
M = ["GpM%d_%d" % (S, i) for i in range(5)]


def call(path, body=None, timeout=120):
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
    print(("  ok   " if cond else "  FAIL ") + name + (("   " + str(detail)[:120]) if detail else ""))


def group(n_members, max_total=6, tag=""):
    """A group intent with n_members people in the chat besides the organiser."""
    c = call("/api/agent/gintent-create", {"self": OWN, "title": "План " + tag,
                                           "intent": {"topics": ["coffee"]},
                                           "max_total": max_total, "idem": "c%s%d" % (tag, S)})
    gid = ((c or {}).get("group") or {}).get("gid")
    who = M[:n_members]
    b = call("/api/agent/gintent-invite", {"gid": gid, "self": OWN, "to": who,
                                           "idem": "i%s%d" % (tag, S)})
    for x in (b.get("sent") or []):
        call("/api/agent/ginvite-respond", {"id": x["id"], "self": x["to"], "accept": True})
    return gid, who


print("=" * 76)
print("1. «СОЗДАТЬ ПЛАН» ДОСТУПЕН ТОЛЬКО ПРИ ТРЁХ")
print("=" * 76)
g2, w2 = group(1, tag="a")                       # организатор + один = двое
early = call("/api/agent/gplan-begin", {"gid": g2, "self": OWN, "when": "сб 19:00"})
check("при двоих план создать нельзя", early.get("error") == "NEED_THREE", early)

gid, who = group(3, tag="b")                     # организатор + трое = четверо
st = call("/api/agent/gintent?gid=%s&self=%s" % (gid, OWN))
check("в чате четверо", ((st.get("group") or {}).get("joined_count")) == 4,
      (st.get("group") or {}).get("joined_count"))
notown = call("/api/agent/gplan-begin", {"gid": gid, "self": who[0], "when": "сб 19:00"})
check("план начинает только создатель", notown.get("error") == "NOT_ORGANIZER", notown)

START = time.time() + 24 * 3600
p = call("/api/agent/gplan-begin", {"gid": gid, "self": OWN, "when": "сб 19:00",
                                    "place": "Nomad Coffee", "starts_at": START,
                                    "idem": "pb%d" % S})
PID = ((p or {}).get("plan") or {}).get("id")
pl = (p or {}).get("plan") or {}
check("план предложен всему составу", bool(PID), p)
check("предложивший считается подтвердившим", pl.get("confirmed_count") == 1, pl.get("confirmed"))
check("ждём остальных троих", pl.get("needs") == 3, pl.get("needs"))
dup = call("/api/agent/gplan-begin", {"gid": gid, "self": OWN, "when": "вс"})
check("второй план на тот же интент не создать", dup.get("error") == "PLAN_EXISTS", dup)

print()
print("=" * 76)
print("2. ВСТРЕЧНОЕ ПРЕДЛОЖЕНИЕ ОБНУЛЯЕТ УТВЕРЖДЕНИЕ")
print("=" * 76)
call("/api/agent/gplan-respond", {"id": PID, "self": who[0], "action": "confirm"})
mid = call("/api/agent/gplan-respond", {"id": PID, "self": who[1], "action": "counter",
                                        "when": "сб 20:00"})
pl = (mid or {}).get("plan") or {}
check("встречное предложение принято", mid.get("countered") is True, mid.get("error"))
check("время заменено", pl.get("when") == "сб 20:00", pl.get("when"))
check("версия выросла", pl.get("version") == 2, pl.get("version"))
check("прежние подтверждения обнулены — согласие было на другой вечер",
      pl.get("confirmed_count") == 1 and pl.get("confirmed") == [who[1]], pl.get("confirmed"))
check("план снова на утверждении", pl.get("state") == "proposed", pl.get("state"))

print()
print("=" * 76)
print("3. ПОДТВЕРЖДАЮТ ВСЕ — МОЛЧАЩЕГО ЖДУТ, А НЕ ВЫБРАСЫВАЮТ")
print("=" * 76)
# Борд GR.26: «Waiting for everyone», «The plan starts when all three confirm». Раньше здесь
# проверялось обратное — что трёх достаточно и четвёртый в состав не попадает (правило дейлика).
# Борд новее и действует: молчащего ждут, а закрывает согласование организатор (раздел 3b).
r1 = call("/api/agent/gplan-respond", {"id": PID, "self": OWN, "action": "confirm"})
check("после двух подтверждений план ещё не создан",
      ((r1.get("plan") or {}).get("state")) == "proposed", (r1.get("plan") or {}).get("state"))
r2 = call("/api/agent/gplan-respond", {"id": PID, "self": who[0], "action": "confirm",
                                       "idem": "pc%d" % S})
pl = (r2 or {}).get("plan") or {}
check("трёх из четверых МАЛО — ждём последнего", pl.get("state") == "proposed", pl.get("state"))
check("и сказано, скольких ждём", pl.get("needs") == 1, pl.get("needs"))
check("молчащий числится в ожидаемых", who[2] in (pl.get("waiting") or []), pl.get("waiting"))
outsider = call("/api/agent/gplan-respond", {"id": PID, "self": "Посторонний%d" % S,
                                             "action": "confirm"})
check("посторонний план не подтверждает", outsider.get("error") == "NOT_A_MEMBER", outsider)
last = call("/api/agent/gplan-respond", {"id": PID, "self": who[2], "action": "confirm"})
pl = (last or {}).get("plan") or {}
check("подтвердил последний — план встал сам", pl.get("state") == "confirmed", pl.get("state"))
check("в составе все четверо", len(pl.get("confirmed") or []) == 4, pl.get("confirmed"))

print()
print("=" * 76)
print("3b. РАУНДЫ: ИХ ТРИ, ДАЛЬШЕ ФИКСИРУЕТ ОРГАНИЗАТОР (GR.28–GR.31)")
print("=" * 76)
gidR, whoR = group(3, tag="r")
pr = call("/api/agent/gplan-begin", {"gid": gidR, "self": OWN, "when": "чт 19:00",
                                     "starts_at": time.time() + 30 * 3600, "idem": "pr%d" % S})
PR = ((pr or {}).get("plan") or {}).get("id")
check("раунд первый", ((pr or {}).get("plan") or {}).get("round") == 1,
      ((pr or {}).get("plan") or {}).get("round"))
check("потолок раундов назван", ((pr or {}).get("plan") or {}).get("max_rounds") == 3)
c2 = call("/api/agent/gplan-respond", {"id": PR, "self": whoR[0], "action": "counter", "when": "чт 20:00"})
check("второй раунд", ((c2 or {}).get("plan") or {}).get("round") == 2, (c2.get("plan") or {}).get("round"))
c3 = call("/api/agent/gplan-respond", {"id": PR, "self": whoR[1], "action": "counter", "when": "чт 20:30"})
pl3 = (c3 or {}).get("plan") or {}
check("третий раунд — последний", pl3.get("round") == 3 and pl3.get("rounds_used_up") is True,
      [pl3.get("round"), pl3.get("rounds_used_up")])
c4 = call("/api/agent/gplan-respond", {"id": PR, "self": whoR[2], "action": "counter", "when": "чт 21:00"})
check("четвёртое встречное предложение отклонено", c4.get("error") == "ROUNDS_USED_UP", c4)
check("и время осталось прежним",
      ((call("/api/agent/gplans?self=%s" % OWN).get("plans") or [{}]) and
       next((x for x in call("/api/agent/gplans?self=%s" % OWN).get("plans") or []
             if x.get("id") == PR), {}).get("when")) == "чт 20:30")
# Фиксация: раунды исчерпаны, согласен не только сам организатор, и делает это он один.
notown = call("/api/agent/gplan-fix", {"id": PR, "self": whoR[0]})
check("фиксирует только организатор", notown.get("error") == "NOT_ORGANIZER", notown)
alone = call("/api/agent/gplan-fix", {"id": PR, "self": OWN})
check("в одиночку закрепить нельзя — это был бы указ, а не план",
      alone.get("error") == "ALONE", alone)
call("/api/agent/gplan-respond", {"id": PR, "self": OWN, "action": "confirm"})
call("/api/agent/gplan-respond", {"id": PR, "self": whoR[0], "action": "confirm"})
fx = call("/api/agent/gplan-fix", {"id": PR, "self": OWN, "idem": "fx%d" % S})
plf = (fx or {}).get("plan") or {}
check("организатор закрепил план", fx.get("ok") is True and plf.get("state") == "confirmed", fx)
check("не подтвердившие названы, но НЕ выброшены",
      whoR[2] in (fx.get("unconfirmed") or []) and whoR[2] in
      [m for m in (call("/api/agent/gintent?gid=%s&self=%s" % (gidR, OWN)).get("group") or {}).get("members", [])
       and [x.get("name") for x in (call("/api/agent/gintent?gid=%s&self=%s" % (gidR, OWN)).get("group") or {}).get("members", [])]],
      fx.get("unconfirmed"))
check("повтор фиксации по ключу — тот же ответ",
      call("/api/agent/gplan-fix", {"id": PR, "self": OWN, "idem": "fx%d" % S}).get("ok") is True)

# «Остаться или выйти» (GR.31): фиксация не выбрасывает молчавшего, а СПРАШИВАЕТ его.
mine = call("/api/agent/gplans?self=%s" % whoR[2])
plq = next((x for x in (mine.get("plans") or []) if x.get("id") == PR), {})
check("молчавшему предложен выбор «остаться или выйти»", plq.get("stay_or_leave") is True, plq)
others = call("/api/agent/gplans?self=%s" % whoR[0])
plo = next((x for x in (others.get("plans") or []) if x.get("id") == PR), {})
check("остальным этого выбора не показывают", not plo.get("stay_or_leave"), plo.get("stay_or_leave"))
stay = call("/api/agent/gplan-respond", {"id": PR, "self": whoR[2], "action": "confirm"})
check("«остаться» — это обычное подтверждение",
      whoR[2] in ((stay.get("plan") or {}).get("confirmed") or []), stay.get("plan"))
check("и выбор снят", not (stay.get("plan") or {}).get("stay_or_leave"))

print()
print("=" * 76)
print("4. ГОЛОСОВАНИЕ СОВЕЩАТЕЛЬНОЕ: СЧИТАЕТ ГРУППА, РЕШАЕТ ОРГАНИЗАТОР (GR.35–38)")
print("=" * 76)
# Борд говорит это трижды и разными словами: «The result is advice — Marc makes the final call»
# (GR.35), «Your answer is advice» (GR.36), «On Kleal the vote is advice — the organiser decides»
# (GR.38). До этой правки большинство само отменяло и само переносило встречу.
v = call("/api/agent/gplan-vote-open", {"id": PID, "self": who[0], "kind": "cancel",
                                        "idem": "vo%d" % S})
VID = ((v or {}).get("vote") or {}).get("id")
vv = (v or {}).get("vote") or {}
check("голосование открыто", bool(VID), v)
check("созвавший уже проголосовал за", vv.get("yes") == 1, vv)
check("срок назван — шесть часов", vv.get("closes_at") and
      5.9 * 3600 < vv["closes_at"] - time.time() <= 6 * 3600, vv.get("closes_at"))
second = call("/api/agent/gplan-vote-open", {"id": PID, "self": OWN, "kind": "edit"})
check("второе голосование одновременно нельзя", second.get("error") == "VOTE_IN_PROGRESS", second)
call("/api/agent/gplan-vote", {"id": VID, "self": OWN, "yes": False})
res = call("/api/agent/gplan-vote", {"id": VID, "self": who[1], "yes": False})
vv = (res or {}).get("vote") or {}
check("голоса посчитаны", (vv.get("yes"), vv.get("no")) == (1, 2), [vv.get("yes"), vv.get("no")])
last = call("/api/agent/gplan-vote", {"id": VID, "self": who[2], "yes": True})
vv = (last or {}).get("vote") or {}
check("высказались все — голосование закрылось", vv.get("state") == "closed", vv.get("state"))
check("при 2:2 совет — оставить как есть", vv.get("advice") == "keep",
      [vv.get("yes"), vv.get("no"), vv.get("advice")])
check("но само оно ничего не сделало — решения ещё нет", not vv.get("decided"), vv.get("decided"))
plan_now = next((x for x in (call("/api/agent/gplans?self=%s" % OWN).get("plans") or [])
                 if x.get("id") == PID), None)
check("план не тронут", bool(plan_now) and plan_now.get("state") == "confirmed",
      plan_now and plan_now.get("state"))
notown = call("/api/agent/gplan-vote-decide", {"id": VID, "self": who[0], "apply": True})
check("решает только организатор", notown.get("error") == "NOT_ORGANIZER", notown)
seen = call("/api/agent/gplans?self=%s" % OWN)
check("закрытое, но нерешённое голосование видно организатору",
      any(x.get("id") == VID and x.get("awaiting_decision") for x in (seen.get("votes") or [])),
      seen.get("votes"))
kept = call("/api/agent/gplan-vote-decide", {"id": VID, "self": OWN, "apply": False,
                                             "idem": "vd%d" % S})
check("организатор оставил план как есть", ((kept.get("vote") or {}).get("decided")) == "kept", kept)
gone = call("/api/agent/gplans?self=%s" % OWN)
check("решённое голосование больше не висит", not any(x.get("id") == VID for x in (gone.get("votes") or [])),
      gone.get("votes"))

print()
print("=" * 76)
print("5. СОВЕТ «ПЕРЕНЕСТИ» — И ОРГАНИЗАТОР, КОТОРЫЙ ЕГО НЕ ПОСЛУШАЛ (GR.38)")
print("=" * 76)
v2 = call("/api/agent/gplan-vote-open", {"id": PID, "self": OWN, "kind": "edit",
                                         "when": "вс 12:00", "place": "Парк"})
V2 = ((v2 or {}).get("vote") or {}).get("id")
for n in (who[0], who[1]):
    call("/api/agent/gplan-vote", {"id": V2, "self": n, "yes": True})
r = call("/api/agent/gplan-vote", {"id": V2, "self": who[2], "yes": False})
vv = (r or {}).get("vote") or {}
check("трое за перенос, один против", (vv.get("yes"), vv.get("no")) == (3, 1), vv)
check("совет группы — менять", vv.get("advice") == "change", vv.get("advice"))
call("/api/agent/gplan-vote-decide", {"id": V2, "self": OWN, "apply": False})
plan_now = next((x for x in (call("/api/agent/gplans?self=%s" % OWN).get("plans") or [])
                 if x.get("id") == PID), None)
check("время НЕ перенесено — большинство просило, организатор оставил",
      plan_now and plan_now.get("when") == "сб 20:00", plan_now and plan_now.get("when"))
check("и состав не порезан — против переноса больше никого не выбрасывает",
      plan_now and len(plan_now.get("confirmed") or []) == 4, plan_now and plan_now.get("confirmed"))

print()
print("=" * 76)
print("5b. ТОТ ЖЕ СОВЕТ, ПРИНЯТЫЙ: ПЕРЕНОС И «ПРИНЯТЬ ИЛИ ВЫЙТИ» (GR.37→33)")
print("=" * 76)
v3 = call("/api/agent/gplan-vote-open", {"id": PID, "self": who[1], "kind": "edit",
                                         "when": "вс 12:00", "place": "Парк"})
V3 = ((v3 or {}).get("vote") or {}).get("id")
for n in (OWN, who[0], who[2]):
    call("/api/agent/gplan-vote", {"id": V3, "self": n, "yes": True})
ap = call("/api/agent/gplan-vote-decide", {"id": V3, "self": OWN, "apply": True})
check("организатор принял совет", ((ap.get("vote") or {}).get("decided")) == "applied", ap)
plan_now = next((x for x in (call("/api/agent/gplans?self=%s" % OWN).get("plans") or [])
                 if x.get("id") == PID), None)
check("время перенесено", plan_now and plan_now.get("when") == "вс 12:00",
      plan_now and plan_now.get("when"))
check("план остался живым — встреча не отменяется", plan_now.get("state") == "confirmed",
      plan_now.get("state"))
check("прежнее время сохранено для строки «было»",
      ((plan_now.get("update") or {}).get("was") or {}).get("when") == "сб 20:00",
      plan_now.get("update"))
check("подтверждения обнулены — каждый принимает заново",
      plan_now.get("confirmed") == [OWN], plan_now.get("confirmed"))
check("версия выросла", plan_now.get("version") == 3, plan_now.get("version"))
check("а РАУНД не вырос: правка сверху — не встречное предложение",
      plan_now.get("round") == 2 and plan_now.get("rounds_used_up") is False,
      [plan_now.get("round"), plan_now.get("rounds_used_up")])
mine = next((x for x in (call("/api/agent/gplans?self=%s" % who[0]).get("plans") or [])
             if x.get("id") == PID), {})
check("участнику предложено принять или выйти", mine.get("accept_or_leave") is True, mine)
own = next((x for x in (call("/api/agent/gplans?self=%s" % OWN).get("plans") or [])
            if x.get("id") == PID), {})
check("автору правки — не предложено", not own.get("accept_or_leave"), own.get("accept_or_leave"))
for n in who[:3]:
    acc = call("/api/agent/gplan-respond", {"id": PID, "self": n, "action": "confirm"})
plan_now = (acc or {}).get("plan") or {}
check("приняли все — правка закрыта", not plan_now.get("update"), plan_now.get("update"))
check("и снова четверо в составе", len(plan_now.get("confirmed") or []) == 4, plan_now.get("confirmed"))

print()
print("=" * 76)
print("5c. ОРГАНИЗАТОР ПРАВИТ ПЛАН САМ, БЕЗ ГОЛОСОВАНИЯ (GR/GRO.32)")
print("=" * 76)
gidU, whoU = group(3, tag="u")                   # четверо: чтобы уход одного не опускал ниже трёх
pu = call("/api/agent/gplan-begin", {"gid": gidU, "self": OWN, "when": "чт 19:00",
                                     "place": "Nømad", "starts_at": time.time() + 40 * 3600,
                                     "idem": "pu%d" % S})
PU = ((pu or {}).get("plan") or {}).get("id")
early = call("/api/agent/gplan-update", {"id": PU, "self": OWN, "when": "чт 21:00"})
check("пока план не утверждён — правки нет, есть встречное предложение",
      early.get("error") == "NOT_CONFIRMED", early)
for n in whoU:
    call("/api/agent/gplan-respond", {"id": PU, "self": n, "action": "confirm"})
notown = call("/api/agent/gplan-update", {"id": PU, "self": whoU[0], "when": "чт 21:00"})
check("правит только организатор", notown.get("error") == "NOT_ORGANIZER", notown)
empty = call("/api/agent/gplan-update", {"id": PU, "self": OWN})
check("правка без изменений отклонена", empty.get("error") == "NOTHING_TO_CHANGE", empty)
upd = call("/api/agent/gplan-update", {"id": PU, "self": OWN, "when": "чт 21:00",
                                       "idem": "up%d" % S})
plu = (upd or {}).get("plan") or {}
check("организатор перенёс время", plu.get("when") == "чт 21:00", plu.get("when"))
check("место не тронуто — меняли только время", plu.get("place") == "Nømad", plu.get("place"))
check("строка «было» собрана", ((plu.get("update") or {}).get("was") or {}).get("when") == "чт 19:00",
      plu.get("update"))
check("состав НЕ порезан — «the group carries on either way»",
      len((call("/api/agent/gintent?gid=%s&self=%s" % (gidU, OWN)).get("group") or {}).get("members") or []) == 4)
memb = next((x for x in (call("/api/agent/gplans?self=%s" % whoU[0]).get("plans") or [])
             if x.get("id") == PU), {})
check("участнику — принять или выйти", memb.get("accept_or_leave") is True, memb)
call("/api/agent/gplan-respond", {"id": PU, "self": whoU[0], "action": "confirm"})
left = call("/api/agent/gintent-leave", {"gid": gidU, "self": whoU[1], "idem": "lv%d" % S})
check("а кто не принял — выходит, и это не рушит план", left.get("ok") is True, left)
after = next((x for x in (call("/api/agent/gplans?self=%s" % OWN).get("plans") or [])
              if x.get("id") == PU), {})
# Пока идёт «принять или выйти», подтверждение ровно одно — организатора. Меряй план по ним, и
# он обрушился бы в below_quorum при троих живых людях, которые никуда не делись.
check("план жив: считаем по составу, а не по подтверждениям",
      after.get("state") == "confirmed", after.get("state"))
# А вот когда состав ДЕЙСТВИТЕЛЬНО падает ниже трёх — план и должен перестать быть групповым.
call("/api/agent/gintent-leave", {"gid": gidU, "self": whoU[2], "idem": "lv2%d" % S})
after2 = next((x for x in (call("/api/agent/gplans?self=%s" % OWN).get("plans") or [])
               if x.get("id") == PU), {})
check("а вот при двоих — уже не групповой план", after2.get("state") == "below_quorum",
      after2.get("state"))

print()
print("=" * 76)
print("5d. ОНЛАЙН БЕЗ ССЫЛКИ (GRO.25a)")
print("=" * 76)
co = call("/api/agent/gintent-create", {"self": OWN, "title": "Book club",
                                        "intent": {"topics": ["books"], "mode": "online"},
                                        "idem": "co%d" % S})
GO = ((co.get("group") or {}).get("gid"))
bo = call("/api/agent/gintent-invite", {"gid": GO, "self": OWN, "to": M[3:5], "idem": "io%d" % S})
for x in (bo.get("sent") or []):
    call("/api/agent/ginvite-respond", {"id": x["id"], "self": x["to"], "accept": True})
po = call("/api/agent/gplan-begin", {"gid": GO, "self": OWN, "when": "чт 20:30",
                                     "starts_at": time.time() + 50 * 3600, "idem": "po%d" % S})
PO = ((po or {}).get("plan") or {}).get("id")
plo = (po or {}).get("plan") or {}
check("план знает, что он онлайновый", plo.get("mode") == "online", plo.get("mode"))
check("и что ссылки нет", plo.get("needs_link") is True, plo.get("needs_link"))
bad = call("/api/agent/gplan-link", {"id": PO, "self": OWN, "link": "спрошу позже"})
check("текст вместо ссылки не сохраняется", bad.get("error") == "BAD_LINK", bad)
notown = call("/api/agent/gplan-link", {"id": PO, "self": M[3], "link": "https://meet.example/x"})
check("ссылку ставит организатор", notown.get("error") == "NOT_ORGANIZER", notown)
ok = call("/api/agent/gplan-link", {"id": PO, "self": OWN, "link": "https://meet.example/kleal",
                                    "idem": "lk%d" % S})
check("ссылка сохранена", ((ok.get("plan") or {}).get("link")) == "https://meet.example/kleal", ok)
check("и «нет ссылки» снято", ((ok.get("plan") or {}).get("needs_link")) is False, ok.get("plan"))
offl = call("/api/agent/gplan-link", {"id": PID, "self": OWN, "link": "https://x.example"})
check("офлайновому плану ссылка не нужна", offl.get("error") == "NOT_ONLINE", offl)

print()
print("=" * 76)
print("6. ДВА ЧАСА ДО ВСТРЕЧИ — ВСЁ ЗАМИРАЕТ")
print("=" * 76)
gid2, who2 = group(3, tag="c")
soon = time.time() + 3600                      # через час: уже внутри двухчасового окна
too_late = call("/api/agent/gplan-begin", {"gid": gid2, "self": OWN, "when": "через час",
                                           "starts_at": soon, "idem": "pl%d" % S})
check("план внутри окна не заводится — его некому подтвердить",
      too_late.get("error") == "TOO_LATE", too_late)

# Ровно на границе: план начинается через два часа с минутой, все подтверждают, затем время
# сдвигается внутрь окна — и всё замирает.
p2 = call("/api/agent/gplan-begin", {"gid": gid2, "self": OWN, "when": "сегодня",
                                     "starts_at": time.time() + 2 * 3600 + 600,
                                     "idem": "pb2%d" % S})
P2 = ((p2 or {}).get("plan") or {}).get("id")
check("а за границей окна — заводится", bool(P2), p2)
for n in who2:
    call("/api/agent/gplan-respond", {"id": P2, "self": n, "action": "confirm"})
pl2 = next((x for x in (call("/api/agent/gplans?self=%s" % OWN).get("plans") or [])
            if x.get("id") == P2), None)
check("план подтверждён всем составом", pl2 and pl2.get("state") == "confirmed",
      pl2 and pl2.get("state"))
late_upd = call("/api/agent/gplan-update", {"id": P2, "self": OWN, "when": "через час",
                                            "starts_at": soon})
check("перенести встречу внутрь окна нельзя даже организатору",
      late_upd.get("error") == "TOO_LATE", late_upd)
# Законный путь внутрь окна — голосование, принятое организатором: там срок проверяли на открытии.
v4 = call("/api/agent/gplan-vote-open", {"id": P2, "self": OWN, "kind": "edit",
                                         "when": "через час", "starts_at": soon})
V4 = ((v4 or {}).get("vote") or {}).get("id")
for n in who2:
    call("/api/agent/gplan-vote", {"id": V4, "self": n, "yes": True})
call("/api/agent/gplan-vote-decide", {"id": V4, "self": OWN, "apply": True})
late = call("/api/agent/gplan-respond", {"id": P2, "self": who2[2], "action": "confirm"})
check("после переноса внутрь окна подтвердить нельзя", late.get("error") == "LOCKED", late)
vlate = call("/api/agent/gplan-vote-open", {"id": P2, "self": OWN, "kind": "cancel"})
check("и отменить нельзя", vlate.get("error") == "LOCKED", vlate)
inv_late = call("/api/agent/gintent-invite", {"gid": gid2, "self": OWN, "to": M[4]})
check("новых людей больше не зовут", inv_late.get("error") == "LOCKED", inv_late)

print()
print("=" * 76)
print("7. ПОСЛЕ ВСТРЕЧИ — ОБРАТНАЯ СВЯЗЬ И ИСТОРИЯ")
print("=" * 76)
conf = [x for x in (call("/api/agent/gplans?self=%s" % OWN).get("plans") or []) if x.get("id") == PID]
parts = (conf[0].get("confirmed") if conf else []) or []
check("в плане четверо", len(parts) == 4, parts)
f1 = call("/api/agent/gplan-feedback", {"id": PID, "self": parts[0], "happened": True,
                                        "text": "хорошо посидели", "idem": "f1%d" % S})
check("первый ответил", f1.get("ok") is True, f1)
check("план ещё не в истории", (f1.get("answered"), f1.get("of")) == (1, 4),
      [f1.get("answered"), f1.get("of")])
nope = call("/api/agent/gplan-feedback", {"id": PID, "self": M[4], "happened": True})
check("не участник фидбэк не оставляет", nope.get("error") == "NOT_A_PARTICIPANT", nope)
for n in parts[1:]:
    last = call("/api/agent/gplan-feedback", {"id": PID, "self": n, "happened": False,
                                              "reason": "дождь"})
check("когда ответили все — план закрыт", ((last.get("plan") or {}).get("state")) == "done",
      (last.get("plan") or {}).get("state"))
hist = call("/api/agent/gplans?self=%s" % parts[0].replace(" ", "+"))
check("и уехал в историю", any(x.get("id") == PID for x in (hist.get("history") or [])),
      [x.get("id") for x in (hist.get("history") or [])])
check("из активных пропал", not any(x.get("id") == PID for x in (hist.get("plans") or [])))

# ---------------------------------------------------------------- GR.45a: «я опаздываю»
#
# Отличие от один-на-один принципиальное: там статус видит ОДИН человек, здесь — вся группа, и
# поэтому он обязан попасть в чат строкой. Человек, который смотрит переписку, а не план, иначе
# не узнал бы ничего — а выглядело бы это как работающая кнопка.
print()
print("=" * 76)
print("GR.45a. ОПОЗДАНИЕ ВИДИТ ВСЯ ГРУППА")
print("=" * 76)
gidL, whoL = group(2, 3, "late")
plL = call("/api/agent/gplan-begin", {"gid": gidL, "self": OWN, "when": "Thu 19:00",
                                      "place": "Barceloneta",
                                      "starts_at": int(time.time()) + 3 * 3600,
                                      "idem": "pbl%d" % S})
PIDL = (plL.get("plan") or {}).get("id")
check("план создан", bool(PIDL), plL)
check("встреча ещё не идёт", (plL.get("plan") or {}).get("started") is False)
for w in [OWN] + whoL:
    call("/api/agent/gplan-respond", {"id": PIDL, "self": w, "action": "confirm",
                                      "idem": "cl%s%d" % (w, S)})
late = call("/api/agent/gplan-status", {"id": PIDL, "self": whoL[0], "status": "late",
                                        "eta_min": 15, "idem": "lt%d" % S})
check("«опаздываю» принято", late.get("ok"), late)
lv = (late.get("plan") or {}).get("live") or {}
check("статус лежит в плане", any(v.get("status") == "late" for v in lv.values()), lv)
thL = call("/api/agent/gintent-thread?gid=%s&self=%s" % (gidL, OWN))
rowsL = [m for m in (thL.get("messages") or []) if (m.get("sys") or {}).get("code") == "running_late"]
check("группа узнала строкой в чате", bool(rowsL),
      [(m.get("sys") or {}).get("code") for m in (thL.get("messages") or [])][-3:])
check("строка несёт кто и на сколько", bool(rowsL) and rowsL[0]["sys"].get("eta") == 15, rowsL[:1])
check("посторонний не говорит за группу",
      call("/api/agent/gplan-status", {"id": PIDL, "self": "Чужой%d" % S, "status": "late",
                                       "idem": "lx%d" % S}).get("error") == "NOT_A_PARTICIPANT")
check("выдуманный статус отвергнут",
      call("/api/agent/gplan-status", {"id": PIDL, "self": whoL[0], "status": "выдумка",
                                       "idem": "ly%d" % S}).get("error") == "BAD_STATUS")

# ---------------------------------------------------------------- GR.40: третий выход с паузы
#
# Кадр предлагает три выхода, средний («перейти в один на один») не работал: проверка стояла на
# «есть ли план вообще», а на паузе он есть, и состояние самой группы тоже уходит в below_quorum,
# то есть вне открытых фаз. Обе проверки отвечали «нельзя», и кнопки просто не было.
print()
print("=" * 76)
print("GR.40. ИЗ ПАУЗЫ МОЖНО УЙТИ ВДВОЁМ")
print("=" * 76)
gidC, whoC = group(2, 3, "conv")
plC = call("/api/agent/gplan-begin", {"gid": gidC, "self": OWN, "when": "Thu 19:00",
                                      "place": "Barceloneta",
                                      "starts_at": int(time.time()) + 3 * 3600,
                                      "idem": "pbc%d" % S})
PIDC = (plC.get("plan") or {}).get("id")
for w in [OWN] + whoC:
    call("/api/agent/gplan-respond", {"id": PIDC, "self": w, "action": "confirm",
                                      "idem": "cc%s%d" % (w, S)})
# Живая встреча переход НЕ разрешает: увести из неё вдвоём значит отменить её молча.
alive = call("/api/agent/gintent-convert", {"gid": gidC, "self": OWN, "idem": "cv0%d" % S})
check("при живой встрече переход отклонён", not alive.get("ok"), alive)

call("/api/agent/gintent-leave", {"gid": gidC, "self": whoC[1], "idem": "lvc%d" % S})
gC = (call("/api/agent/gintent?gid=%s&self=%s" % (gidC, OWN)).get("group") or {})
check("план встал на паузу", (gC.get("plan") or {}).get("state") == "below_quorum",
      (gC.get("plan") or {}).get("state"))
check("кадр предлагает переход", gC.get("can_convert") is True, gC.get("can_convert"))

askC = call("/api/agent/gintent-convert", {"gid": gidC, "self": OWN, "idem": "cv1%d" % S})
check("организатор спросил, а не решил сам", askC.get("ok") and askC.get("asked") == whoC[0], askC)
seen = (call("/api/agent/gintent?gid=%s&self=%s" % (gidC, whoC[0])).get("group") or {})
check("второму видно, что его спросили", bool(seen.get("pending_1to1")), seen.get("pending_1to1"))
agr = call("/api/agent/gintent-convert-respond", {"gid": gidC, "self": whoC[0], "agree": True,
                                                  "idem": "cv2%d" % S})
check("второй согласился", agr.get("ok") and agr.get("agreed") is True, agr)
gC2 = (call("/api/agent/gintent?gid=%s&self=%s" % (gidC, OWN)).get("group") or {})
check("группа стала один-на-один", gC2.get("state") == "converted_1to1", gC2.get("state"))
# План обязан закрыться ВМЕСТЕ с группой: оставленный, он ссылается на группу, которой уже нет,
# и продолжает висеть среди живых — мусор, который потом никто не свяжет с этим переходом.
allC = call("/api/agent/gplans?self=%s" % OWN)
gone = [x for x in (allC.get("plans") or []) + (allC.get("history") or []) if x.get("id") == PIDC]
check("план закрыт вместе с группой", bool(gone) and gone[0].get("state") == "cancelled",
      [x.get("state") for x in gone])
check("и среди живых его нет", not any(x.get("id") == PIDC for x in (allC.get("plans") or [])))
thC = call("/api/agent/gintent-thread?gid=%s&self=%s" % (gidC, OWN))
codesC = [(m.get("sys") or {}).get("code") for m in (thC.get("messages") or [])]
check("в чате есть и вопрос, и ответ", "convert_asked" in codesC and "converted" in codesC, codesC[-4:])

print()
print("=" * 76)
print("РЕЗУЛЬТАТ: %d ok, %d проблем" % (R["ok"], R["fail"]))
for f in FAILED:
    print("   -", f)
sys.exit(1 if R["fail"] else 0)
