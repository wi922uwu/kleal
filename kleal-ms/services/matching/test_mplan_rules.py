#!/usr/bin/env python3
"""Правила сделки 1:1: python3 services/matching/test_mplan_rules.py

Модуль чистый, поэтому здесь ни стора, ни сервера, ни разбора исходника app.py — таблица
проверяется напрямую. Закреплено то, чего смоук `tools/mplan_smoke.py` не видит вовсе: он
назначает встречи на +48 и +72 часа и ни разу не попадает в заморозку T−2ч, а именно там правила
у ручек расходились. И отдельно — что каждый переход, который совершают ручки, есть ребро машины
«plan» из спеки §14 (`kleal_states`), чтобы хранимые состояния и спека не разъехались молча.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mplan_rules as R           # noqa: E402
import kleal_states as ks         # noqa: E402

_fails = []


def check(name, ok, got=""):
    print(("  ok  " if ok else "FAIL  ") + name + ("" if ok else "  -> %s" % (got,)))
    if not ok:
        _fails.append(name)


def F(state="confirmed", **kw):
    """Факты плана: по умолчанию подтверждённая встреча вживую, без встречного времени."""
    f = {"state": state, "frozen": False, "pending": False, "pending_mine": False,
         "mode": "offline", "link": False, "place": False, "my_answer": None}
    f.update(kw)
    return f


def code(action, facts):
    r = R.refusal(action, facts)
    return None if r is None else r.get("error")


print("-- открытый план: всё, что не требует условий, возможно")
for st in ("proposed", "confirmed"):
    for a in ("confirm", "decline", "counter", "address", "cancel"):
        check("%s @%s" % (a, st), code(a, F(st)) is None, code(a, F(st)))

print("-- закрытый план закрыт для всех, и код — тот, что был у ручки")
for st in ("cancelled", "done"):
    for a in ("confirm", "decline", "counter", "accept_change", "reject_change", "address",
              "ask_place", "ask_link", "cancel", "move_to_call", "side_call", "side_in_person"):
        r = R.refusal(a, F(st))
        check("%s @%s -> NOT_OPEN" % (a, st), r and r["error"] == "NOT_OPEN" and r["state"] == st, r)
check("status @proposed -> NOT_CONFIRMED", code("status", F("proposed")) == "NOT_CONFIRMED")
check("status @done -> NOT_CONFIRMED", code("status", F("done")) == "NOT_CONFIRMED")
check("feedback @proposed -> NOT_YET", code("feedback", F("proposed")) == "NOT_YET")
check("feedback @done is allowed (второй ответ об исходе)", code("feedback", F("done")) is None)
check("feedback @cancelled -> NOT_YET", code("feedback", F("cancelled")) == "NOT_YET")

print("-- заморозка T-2ч: правки заперты, ответы и действия в момент встречи — нет")
fz = F(frozen=True, mode="hybrid", link=True, place=True, pending=True)
for a in ("counter", "accept_change", "reject_change", "address", "cancel"):
    r = R.refusal(a, fz)
    check("%s in freeze -> LOCKED" % a, r and r["error"] == "LOCKED" and r.get("note") == R.FREEZE_NOTE, r)
for a in ("ask_place", "ask_link"):
    check("%s in freeze -> LOCKED" % a, code(a, F(frozen=True)) == "LOCKED", code(a, F(frozen=True)))
for a in ("decline", "move_to_call", "side_call", "side_in_person", "status", "feedback"):
    check("%s in freeze is allowed" % a, code(a, F(frozen=True, mode="hybrid", link=True, place=True)) is None,
          code(a, F(frozen=True, mode="hybrid", link=True, place=True)))
check("confirm in freeze is allowed (ответ, не правка)", code("confirm", F("proposed", frozen=True)) is None)
check("decline in freeze is allowed — ручка превращает его в «не смогу»",
      code("decline", F(frozen=True)) is None)

print("-- условия")
check("confirm while a counter hangs -> PENDING_CHANGE", code("confirm", F(pending=True)) == "PENDING_CHANGE")
check("accept_change without a counter -> NO_PENDING_CHANGE",
      code("accept_change", F()) == "NO_PENDING_CHANGE")
check("reject_change without a counter -> NO_PENDING_CHANGE",
      code("reject_change", F()) == "NO_PENDING_CHANGE")
check("accepting your own counter -> YOUR_OWN_CHANGE",
      code("accept_change", F(pending=True, pending_mine=True)) == "YOUR_OWN_CHANGE")
check("withdrawing your own counter is allowed", code("reject_change", F(pending=True, pending_mine=True)) is None)
check("accepting their counter is allowed", code("accept_change", F(pending=True)) is None)
check("ask_place when the place is set -> ALREADY_SET", code("ask_place", F(place=True)) == "ALREADY_SET")
check("ask_link when the link is set -> ALREADY_SET", code("ask_link", F(link=True)) == "ALREADY_SET")
r = R.refusal("move_to_call", F(mode="offline", link=True))
check("move_to_call on an offline plan -> NOT_HYBRID with the mode",
      r and r["error"] == "NOT_HYBRID" and r.get("mode") == "offline", r)
check("move_to_call without a link -> NO_LINK", code("move_to_call", F(mode="hybrid")) == "NO_LINK")
check("side_call without a link -> NO_LINK", code("side_call", F(mode="hybrid")) == "NO_LINK")
check("side_in_person without a place -> NO_PLACE", code("side_in_person", F(mode="hybrid", link=True)) == "NO_PLACE")
check("side_call on an online plan -> NOT_HYBRID", code("side_call", F(mode="online", link=True)) == "NOT_HYBRID")

print("-- порядок: закрытый сильнее заморозки, заморозка сильнее условий")
check("cancelled + frozen -> NOT_OPEN", code("address", F("cancelled", frozen=True)) == "NOT_OPEN")
check("frozen + pending -> LOCKED for accept_change",
      code("accept_change", F(frozen=True, pending=True)) == "LOCKED")
r = R.refusal("dance", F())
check("unknown action -> BAD_ACTION with the list", r and r["error"] == "BAD_ACTION" and "confirm" in r["allowed"], r)

print("-- что предлагать на экране")
g = R.offered(F("proposed"))
check("guest, not yet answered: confirm/decline/counter/address/cancel",
      all(a in g for a in ("confirm", "decline", "counter", "address", "cancel"))
      and not any(a in g for a in ("accept_change", "reject_change", "status", "feedback", "move_to_call")), g)
check("ask_place is offered while the place is empty", "ask_place" in g, g)
check("ask_link is offered on a call plan while the link is empty",
      "ask_link" in R.offered(F("proposed", mode="online")), R.offered(F("proposed", mode="online")))
g = R.offered(F("proposed", my_answer="confirmed"))
check("after my confirmation there is no confirm button", "confirm" not in g and "counter" in g, g)
g = R.offered(F(pending=True))
check("their counter hangs: accept/reject, no confirm", "accept_change" in g and "reject_change" in g
      and "confirm" not in g, g)
g = R.offered(F(pending=True, pending_mine=True))
check("my own counter hangs: withdraw only", "reject_change" in g and "accept_change" not in g, g)
g = R.offered(F(frozen=True))
check("frozen confirmed plan: status/decline/feedback, no counter/cancel/address",
      all(a in g for a in ("status", "decline", "feedback"))
      and not any(a in g for a in ("counter", "cancel", "address", "ask_place")), g)
print("-- показ учитывает вид встречи, а право — нет")
check("офлайну не предлагают попросить ссылку", "ask_link" not in R.offered(F(mode="offline")))
check("но ручка ask_link офлайну по-прежнему не отказывает", R.refusal("ask_link", F(mode="offline")) is None)
check("звонку не предлагают попросить место", "ask_place" not in R.offered(F(mode="online")))
check("но ручка ask_place звонку по-прежнему не отказывает", R.refusal("ask_place", F(mode="online")) is None)
check("гибриду предлагают обе просьбы",
      all(a in R.offered(F(mode="hybrid")) for a in ("ask_place", "ask_link")), R.offered(F(mode="hybrid")))

g = R.offered(F("done"))
check("done: only feedback", g == ["feedback"], g)
check("cancelled: nothing", R.offered(F("cancelled")) == [], R.offered(F("cancelled")))
check("offered follows the table order", R.offered(F("proposed")) == [a for a in R.RULES if a in R.offered(F("proposed"))])

print("-- раунды до подтверждения (борд 1:1 new layout, 06.10.2026)")
check("counter in round 2 of 3 allowed", code("counter", F("proposed", round=2, max_rounds=3)) is None)
check("counter after round 3 -> NO_ROUNDS_LEFT", code("counter", F("proposed", round=3, max_rounds=3)) == "NO_ROUNDS_LEFT")
check("reschedule after confirm ignores rounds", code("counter", F("confirmed", round=3, max_rounds=3)) is None)
check("fix: host after round 3", code("fix", F("proposed", round=3, max_rounds=3, is_host=True)) is None)
check("fix: not before round 3", code("fix", F("proposed", round=2, max_rounds=3, is_host=True)) == "ROUNDS_NOT_DONE")
check("fix: guest refused", code("fix", F("proposed", round=3, max_rounds=3)) == "HOST_ONLY")
check("fix: not on confirmed", code("fix", F("confirmed", round=3, is_host=True)) == "NOT_OPEN")
check("fix: locked in freeze", code("fix", F("proposed", round=3, is_host=True, frozen=True)) == "LOCKED")
check("fix: refused once already fixed", code("fix", F("proposed", round=3, is_host=True, final=True)) == "ALREADY_FIXED")
check("stay/leave need a fixed plan", code("stay", F("proposed")) == "NOT_FIXED" and code("leave", F("proposed")) == "NOT_FIXED")
check("stay/leave guest only", code("stay", F("proposed", final=True, is_host=True)) == "GUEST_ONLY")
check("stay works in freeze", code("stay", F("proposed", final=True, frozen=True)) is None)
g = R.offered(F("proposed", final=True, round=3))
check("fixed plan: guest offered stay/leave, not confirm/decline/counter",
      "stay" in g and "leave" in g and not any(a in g for a in ("confirm", "decline", "counter")), g)

print("-- спека §14: каждый переход ручек — ребро машины «plan»")
for a, b in R.TRANSITIONS:
    check("%s -> %s is a spec edge %s -> %s" % (a, b, R.SPEC_STATE[a], R.SPEC_STATE[b]),
          ks.can_transition("plan", R.SPEC_STATE[a], R.SPEC_STATE[b]))
check("every stored state is mapped", set(R.SPEC_STATE) == {"proposed", "confirmed", "cancelled", "done"})
check("every mapped spec state exists", all(s in ks.STATE_MACHINES["plan"]["states"] for s in R.SPEC_STATE.values()))
check("terminal states are terminal in the spec too",
      all(ks.is_terminal("plan", R.SPEC_STATE[s]) for s in ("cancelled", "done")))
check("every need in the table is defined", all(n in R.NEEDS for r in R.RULES.values() for n in r.needs))

print()
print("FAILED %d: %s" % (len(_fails), ", ".join(_fails)) if _fails else "ALL PASS")
sys.exit(1 if _fails else 0)
