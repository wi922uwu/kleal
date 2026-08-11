# -*- coding: utf-8 -*-
"""Group intents, layer 1: individual invites and ONE shared chat.

    python3 tools/gintents_smoke.py [http://127.0.0.1:7074]

These are the spec's own acceptance criteria (§25) turned into requests, not a tour of the happy
path. The ones that matter most are the ones a screenshot would never show: that a seat cannot be
claimed twice under a race, that an invite sent before the room filled is refused after it fills,
and that a person who is not in the room cannot read the room.
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7074").rstrip("/")
R = {"ok": 0, "fail": 0}
FAILED = []
# Two runs started inside the same second would otherwise share names AND idempotency keys, and
# each would see the other's groups — which looks exactly like a race bug in the product.
STAMP = int(time.time() * 1000) % 100000000 + os.getpid()
OWNER = "GiOwner%d" % STAMP
GUESTS = ["GiGuest%d_%d" % (STAMP, i) for i in range(6)]


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


print("=" * 76)
print("1. ГРУППОВОЙ ИНТЕНТ ОТКРЫТ — СОЗДАТЕЛЬ УЖЕ УЧАСТНИК")
print("=" * 76)
c = call("/api/agent/gintent-create", {"self": OWNER, "title": "Падел в субботу",
                                       "intent": {"topics": ["padel"], "type": "sport",
                                                  "time": "сб 18:00", "place": "Gràcia"},
                                       "idem": "gi-c-%d" % STAMP})
g = (c or {}).get("group") or {}
GID = g.get("gid")
check("интент создан", bool(GID), c)
check("создатель считается участником с самого начала", g.get("joined_count") == 1, g.get("joined_count"))
check("минимум — три человека", g.get("min_total") == 3, g.get("min_total"))
check("план пока недоступен", g.get("planning_allowed") is False, g.get("planning_allowed"))
check("сказано, скольких не хватает", g.get("need_more") == 2, g.get("need_more"))
same = call("/api/agent/gintent-create", {"self": OWNER, "idem": "gi-c-%d" % STAMP})
check("повтор с тем же ключом не создаёт второй интент",
      ((same or {}).get("group") or {}).get("gid") == GID, (same.get("group") or {}).get("gid"))

print()
print("=" * 76)
print("2. ПРИГЛАШЕНИЯ — ПО ОДНОМУ, С ПРОВЕРКАМИ")
print("=" * 76)
inv = {}
r = call("/api/agent/gintent-invite", {"gid": GID, "self": OWNER, "to": GUESTS[0],
                                       "idem": "gi-i0-%d" % STAMP})
inv[0] = ((r or {}).get("invite") or {}).get("id")
check("приглашение ушло", bool(inv[0]), r)
dup = call("/api/agent/gintent-invite", {"gid": GID, "self": OWNER, "to": GUESTS[0]})
check("повторное приглашение тому же человеку отклонено", dup.get("error") == "ALREADY_INVITED", dup)
notme = call("/api/agent/gintent-invite", {"gid": GID, "self": GUESTS[1], "to": GUESTS[2]})
check("приглашать может только создатель", notme.get("error") == "NOT_ORGANIZER", notme)
myself = call("/api/agent/gintent-invite", {"gid": GID, "self": OWNER, "to": OWNER})
check("себя пригласить нельзя", not myself.get("ok"), myself)

for i in (1, 2):
    r = call("/api/agent/gintent-invite", {"gid": GID, "self": OWNER, "to": GUESTS[i],
                                           "idem": "gi-i%d-%d" % (i, STAMP)})
    inv[i] = ((r or {}).get("invite") or {}).get("id")
check("три приглашения в воздухе", all(inv.get(i) for i in (0, 1, 2)), inv)
# Борд GR.14/GR.15: «3 open invites at a time on Free». Раньше здесь проверялось обратное
# («batch разрешён», кап 20 был предохранителем) — правило дейлика; борд новее и действует.
cap = call("/api/agent/gintent-invite", {"gid": GID, "self": OWNER, "to": GUESTS[3]})
check("четвёртое открытое приглашение упирается в кап борда",
      cap.get("error") == "INVITE_CAP" and cap.get("cap") == 3, cap)

print()
print("=" * 76)
print("2b. ОТМЕНА ПРИГЛАШЕНИЯ — GR.17 Cancel, выход из капа по GR.15")
print("=" * 76)
notmine = call("/api/agent/gintent-invite-cancel", {"id": inv[2], "self": GUESTS[1]})
check("отменяет только создатель", notmine.get("error") == "NOT_ORGANIZER", notmine)
cx = call("/api/agent/gintent-invite-cancel", {"id": inv[2], "self": OWNER,
                                               "idem": "gi-cx-%d" % STAMP})
check("открытое приглашение отозвано", cx.get("ok") is True, cx)
check("отзыв освободил кап — приглашение по нему снова уходит",
      (call("/api/agent/gintent-invite", {"gid": GID, "self": OWNER, "to": GUESTS[3],
                                          "idem": "gi-i3-%d" % STAMP}) or {}).get("ok") is True)
dead = call("/api/agent/ginvite-respond", {"id": inv[2], "self": GUESTS[2], "accept": True})
check("по отозванному приглашению войти нельзя, и причина названа",
      dead.get("error") == "WITHDRAWN", dead)
replayc = call("/api/agent/gintent-invite-cancel", {"id": inv[2], "self": OWNER,
                                                    "idem": "gi-cx-%d" % STAMP})
check("повтор отмены по тому же ключу — тот же ответ", replayc.get("ok") is True, replayc)
# Кап снова полон (inv0, inv1, GUESTS[3]) — освобождаем место и возвращаем GUESTS[2] живое
# приглашение: дальше секции 3–4 работают с ним.
call("/api/agent/gintent-invite-cancel", {"id": ((call("/api/agent/gintent?gid=%s&self=%s"
     % (GID, OWNER.replace(" ", "+"))).get("group") or {}).get("invites") or [{}])[-1].get("id"),
     "self": OWNER, "idem": "gi-cx2-%d" % STAMP})
r = call("/api/agent/gintent-invite", {"gid": GID, "self": OWNER, "to": GUESTS[2],
                                       "idem": "gi-i2b-%d" % STAMP})
inv[2] = ((r or {}).get("invite") or {}).get("id")
check("GUESTS[2] снова приглашён — для секций ниже", bool(inv[2]), r)
own_view = (call("/api/agent/gintent?gid=%s&self=%s" % (GID, OWNER.replace(" ", "+")))
            .get("group") or {})
check("организатор видит список открытых приглашений (GR.17)",
      sorted(x.get("to") for x in (own_view.get("invites") or []))
      == sorted([GUESTS[0], GUESTS[1], GUESTS[2]]), own_view.get("invites"))
check("и кап назван в самой группе", own_view.get("invite_cap") == 3, own_view.get("invite_cap"))

print()
print("=" * 76)
print("3. ПРИНЯЛ — СРАЗУ В ОБЩЕМ ЧАТЕ (лобби нет)")
print("=" * 76)
a0 = call("/api/agent/ginvite-respond", {"id": inv[0], "self": GUESTS[0], "accept": True,
                                         "idem": "gi-a0-%d" % STAMP})
g = (a0 or {}).get("group") or {}
check("вошёл", a0.get("ok") is True, a0)
check("в комнате двое", g.get("joined_count") == 2, g.get("joined_count"))
check("при двоих план ещё недоступен", g.get("planning_allowed") is False, g.get("planning_allowed"))
check("и сказано, что нужен ещё один", g.get("need_more") == 1, g.get("need_more"))
check("участник списка приглашений НЕ видит — он только у организатора (GR.16/GR.17)",
      "invites" not in ((a0 or {}).get("group") or {}), list(((a0 or {}).get("group") or {}).keys())[:8])
th = call("/api/agent/gintent-thread?gid=%s&self=%s" % (GID, GUESTS[0].replace(" ", "+")))
check("чат открыт сразу, без ожидания", th.get("ok") is True, th.get("error"))
check("вход записан в историю",
      any("joined" in str(m.get("text", "")) for m in (th.get("messages") or [])),
      [m.get("text") for m in (th.get("messages") or [])][:3])

stranger = call("/api/agent/gintent-thread?gid=%s&self=%s" % (GID, GUESTS[4].replace(" ", "+")))
check("посторонний чат не читает", stranger.get("error") == "NOT_A_MEMBER", stranger)
post_bad = call("/api/agent/gintent-post", {"gid": GID, "self": GUESTS[4], "text": "привет"})
check("и не пишет в него", post_bad.get("error") == "NOT_A_MEMBER", post_bad)

a1 = call("/api/agent/ginvite-respond", {"id": inv[1], "self": GUESTS[1], "accept": True,
                                         "idem": "gi-a1-%d" % STAMP})
g = (a1 or {}).get("group") or {}
check("третий вошёл в ТОТ ЖЕ чат", a1.get("ok") is True and g.get("joined_count") == 3, g.get("joined_count"))
check("теперь план доступен", g.get("planning_allowed") is True, g.get("planning_allowed"))
th = call("/api/agent/gintent-thread?gid=%s&self=%s" % (GID, GUESTS[1].replace(" ", "+")))
check("новичок видит историю до своего прихода", len(th.get("messages") or []) >= 2,
      len(th.get("messages") or []))
check("и объявлено, что людей достаточно",
      any("enough people" in str(m.get("text", "")) for m in (th.get("messages") or [])),
      [m.get("text") for m in (th.get("messages") or [])][-3:])

print()
print("=" * 76)
print("4. ОТКАЗ И ПОВТОРЫ")
print("=" * 76)
d = call("/api/agent/ginvite-respond", {"id": inv[2], "self": GUESTS[2], "accept": False,
                                        "idem": "gi-d2-%d" % STAMP})
check("отказ принят", d.get("ok") is True, d)
again = call("/api/agent/ginvite-respond", {"id": inv[2], "self": GUESTS[2], "accept": True})
check("после отказа принять уже нельзя", not again.get("ok"), again)
replay = call("/api/agent/ginvite-respond", {"id": inv[0], "self": GUESTS[0], "accept": True,
                                             "idem": "gi-a0-%d" % STAMP})
check("повтор принятия по тому же ключу — тот же ответ", replay.get("ok") is True, replay)
foreign = call("/api/agent/ginvite-respond", {"id": inv[1], "self": GUESTS[3], "accept": True})
check("чужое приглашение принять нельзя", foreign.get("error") == "NOT_YOURS", foreign)

print()
print("=" * 76)
print("5. ГОНКА ЗА ПОСЛЕДНЕЕ МЕСТО")
print("=" * 76)
# max_total=3 -> одно место, двое принимают одновременно. Ровно один должен войти.
c2 = call("/api/agent/gintent-create", {"self": OWNER, "title": "Тесная группа",
                                        "intent": {"topics": ["coffee"]},
                                        "min_total": 3, "max_total": 3,
                                        "idem": "gi-c2-%d" % STAMP})
G2 = ((c2 or {}).get("group") or {}).get("gid")
iv = []
for i in (4, 5):
    r = call("/api/agent/gintent-invite", {"gid": G2, "self": OWNER, "to": GUESTS[i],
                                           "idem": "gi-r%d-%d" % (i, STAMP)})
    iv.append((((r or {}).get("invite") or {}).get("id"), GUESTS[i]))
# Одно свободное место (создатель + 1 = 2 из 3) и ДВА живых приглашения на него. Именно этот
# случай спека называет обязательным (§20): приглашения мест не резервируют, иначе второе
# приглашение выдать бы не удалось и гонку было бы нечем воспроизвести.
first = call("/api/agent/ginvite-respond", {"id": iv[0][0], "self": iv[0][1], "accept": True})
check("второй участник вошёл", first.get("ok") is True, first)
r = call("/api/agent/gintent-invite", {"gid": G2, "self": OWNER, "to": GUESTS[3]})
last = ((r or {}).get("invite") or {}).get("id")
check("на одно место выдано два приглашения", bool(last) and bool(iv[1][0]), r)

res = []
start = threading.Barrier(2)
def grab(inv_id, who):
    start.wait()                      # оба потока стартуют в один момент, иначе это не гонка
    res.append(call("/api/agent/ginvite-respond", {"id": inv_id, "self": who, "accept": True}))

ts = [threading.Thread(target=grab, args=(iv[1][0], iv[1][1])),
      threading.Thread(target=grab, args=(last, GUESTS[3]))]
[t.start() for t in ts]
[t.join() for t in ts]
check("оба претендента дошли до ответа", len(res) == 2, len(res))
won = [x for x in res if x.get("ok")]
lost = [x for x in res if not x.get("ok")]
st = call("/api/agent/gintent?gid=%s&self=%s" % (G2, OWNER.replace(" ", "+")))
final = ((st or {}).get("group") or {}).get("joined_count")
check("состав не превысил потолок", final == 3, final)
check("ровно один из гонки вошёл, остальным отказ",
      len(won) <= 1 and (len(lost) == len(res) - len(won)), [len(won), len(lost)])
check("ровно один выиграл", len(won) == 1, len(won))
check("проигравшему сказали, что группа полна",
      all(x.get("error") == "GROUP_FULL" for x in lost), lost[:1])
blocked = call("/api/agent/gintent-invite", {"gid": G2, "self": OWNER, "to": GUESTS[2]})
check("в полную группу больше не приглашают", blocked.get("error") == "GROUP_FULL", blocked)

print()
print("=" * 76)
print("6. ВЫХОД — ЕДИНСТВЕННЫЙ СПОСОБ УМЕНЬШИТЬ СОСТАВ")
print("=" * 76)
gone = call("/api/agent/gintent-leave", {"gid": GID, "self": GUESTS[1], "idem": "gi-l-%d" % STAMP})
g = (gone or {}).get("group") or {}
check("участник вышел сам", gone.get("ok") is True, gone)
check("состав пересчитан", g.get("joined_count") == 2, g.get("joined_count"))
check("ниже минимума план снова недоступен", g.get("planning_allowed") is False, g.get("planning_allowed"))
th = call("/api/agent/gintent-thread?gid=%s&self=%s" % (GID, OWNER.replace(" ", "+")))
check("выход виден в истории нейтральным сообщением",
      any("left the group" in str(m.get("text", "")) for m in (th.get("messages") or [])),
      [m.get("text") for m in (th.get("messages") or [])][-2:])
after = call("/api/agent/gintent-thread?gid=%s&self=%s" % (GID, GUESTS[1].replace(" ", "+")))
check("вышедший больше не читает чат", after.get("error") == "NOT_A_MEMBER", after)

print()
print("=" * 76)
print("7. СПИСОК СВОИХ ГРУПП И ВХОДЯЩИХ")
print("=" * 76)
mine = call("/api/agent/gintents?self=%s" % OWNER.replace(" ", "+"))
check("создатель видит свои группы", len(mine.get("groups") or []) >= 2, len(mine.get("groups") or []))
inbox = call("/api/agent/gintents?self=%s" % GUESTS[2].replace(" ", "+"))
check("отказавшийся не числится ни в группе, ни во входящих",
      not (inbox.get("groups") or []) and not (inbox.get("invites") or []),
      [len(inbox.get("groups") or []), len(inbox.get("invites") or [])])

print()
print("=" * 76)
print("8. BATCH-ИНВАЙТЫ — ВСЕЙ ВЫДАЧЕ СРАЗУ (регламент)")
print("=" * 76)
cb = call("/api/agent/gintent-create", {"self": OWNER, "title": "Батч",
                                        "intent": {"topics": ["coffee"]}, "max_total": 6,
                                        "idem": "gi-cb-%d" % STAMP})
GB = ((cb or {}).get("group") or {}).get("gid")
batch = call("/api/agent/gintent-invite", {"gid": GB, "self": OWNER,
                                           "to": GUESTS[:4] + [OWNER, GUESTS[0]],
                                           "idem": "gi-b-%d" % STAMP})
check("батч ушёл одним вызовом", batch.get("ok") is True, len(batch.get("sent") or []))
# Кап борда режет и батч: тремя открытыми всё и заканчивается, четвёртому — INVITE_CAP поимённо.
check("ушли первые трое — дальше кап", len(batch.get("sent") or []) == 3, batch.get("sent"))
check("негодные названы поимённо, а не срезали батч",
      len(batch.get("refused") or []) == 3, batch.get("refused"))
check("четвёртому названа причина — кап",
      any(x.get("error") == "INVITE_CAP" for x in (batch.get("refused") or [])),
      batch.get("refused"))
check("себя в батче не приглашает",
      any(x.get("to") == OWNER for x in (batch.get("refused") or [])), batch.get("refused"))
check("повтор батча по ключу — тот же ответ",
      len((call("/api/agent/gintent-invite", {"gid": GB, "self": OWNER, "to": GUESTS[:4],
                                              "idem": "gi-b-%d" % STAMP}).get("sent") or [])) == 3)

print()
print("=" * 76)
print("9. НА ЭТАПЕ ПЛАНА — ЧЕРЕЗ АПРУВ СОЗДАТЕЛЯ")
print("=" * 76)
ids = {x["to"]: x["id"] for x in (batch.get("sent") or [])}
for nm in list(ids)[:2]:
    call("/api/agent/ginvite-respond", {"id": ids[nm], "self": nm, "accept": True})
st = call("/api/agent/gintent?gid=%s&self=%s" % (GB, OWNER.replace(" ", "+")))
gb = (st or {}).get("group") or {}
check("трое в чате — план доступен", gb.get("planning_allowed") is True, gb.get("joined_count"))
# Организатор начинает план — после этого вход только через апрув.
#
# Это место было холостым. Эндпоинт назывался «/api/agent/gintent-plan-begin», а такого нет: план
# начинает «gplan-begin». Вызов всегда падал, печаталось «этап плана ещё не реализован — слой 2»
# (неправда, слой 2 давно есть), группа оставалась в открытой фазе, вход шёл автоматически — и весь
# раздел отчитывался запасной веткой. Три проверки апрува не выполнялись НИ РАЗУ, а тест был зелёный.
call("/api/agent/gintent-post", {"gid": GB, "self": OWNER, "text": "давайте в субботу"})
mark = call("/api/agent/gplan-begin", {"gid": GB, "self": OWNER, "when": "суббота 19:00",
                                       "place": "Gracia", "starts_at": time.time() + 48 * 3600,
                                       "idem": "gi-pb-%d" % STAMP})
check("организатор начал план", mark.get("ok") is True, mark)
third = list(ids)[2]
acc = call("/api/agent/ginvite-respond", {"id": ids[third], "self": third, "accept": True})
# Без ветвления: если апрув снова перестанет требоваться, это должно упасть, а не тихо перейти
# на другую проверку.
check("принявший на этапе плана ждёт апрува", acc.get("awaiting_approval") is True, acc)
ap = call("/api/agent/gintent-approve", {"gid": GB, "self": third, "who": third})
check("апрувить может только создатель", ap.get("error") == "NOT_ORGANIZER", ap)
ap = call("/api/agent/gintent-approve", {"gid": GB, "self": OWNER, "who": third,
                                         "idem": "gi-ap-%d" % STAMP})
check("создатель заапрувил — человек в группе", ap.get("ok") is True, ap)

print()
print("=" * 76)
print("10. УДАЛЕНИЕ УЧАСТНИКА — ТОЛЬКО С ПРИЧИНОЙ (регламент)")
print("=" * 76)
victim = list(ids)[0]
nore = call("/api/agent/gintent-remove", {"gid": GB, "self": OWNER, "who": victim})
check("без причины удалить нельзя", nore.get("error") == "REASON_REQUIRED", nore)
notown = call("/api/agent/gintent-remove", {"gid": GB, "self": victim, "who": list(ids)[1],
                                            "reason": "не нравится"})
check("удалять может только создатель", notown.get("error") == "NOT_ORGANIZER", notown)
self_rm = call("/api/agent/gintent-remove", {"gid": GB, "self": OWNER, "who": OWNER,
                                             "reason": "x"})
check("себя создатель не удаляет", self_rm.get("error") == "CANNOT_REMOVE_ORGANIZER", self_rm)
rm = call("/api/agent/gintent-remove", {"gid": GB, "self": OWNER, "who": victim,
                                        "reason": "слал непристойности", "idem": "gi-rm-%d" % STAMP})
check("удалён с причиной", rm.get("ok") is True, rm)
gone = call("/api/agent/gintent-thread?gid=%s&self=%s" % (GB, victim.replace(" ", "+")))
check("удалённый теряет доступ к чату", gone.get("error") == "NOT_A_MEMBER", gone)
th = call("/api/agent/gintent-thread?gid=%s&self=%s" % (GB, OWNER.replace(" ", "+")))
last = [m.get("text") for m in (th.get("messages") or [])][-1:]
check("группе сказано нейтрально, без причины и без имени удалившего",
      any("no longer in the group" in str(t) for t in last)
      and not any("непристойн" in str(t) for t in last), last)

print()
print("=" * 76)
print("РЕЗУЛЬТАТ: %d ok, %d проблем" % (R["ok"], R["fail"]))
for f in FAILED:
    print("   -", f)
sys.exit(1 if R["fail"] else 0)
