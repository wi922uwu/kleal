# -*- coding: utf-8 -*-
"""§4 Plan — согласованная активность (время, место/room, участники, состояние).

Состояния меняются через version-check write (§21.2 POST /plans, §23.2 п.13). Раскрытие точного места —
только после соответствующего уровня взаимного согласия (§8.4).
"""

PLAN_STATE = ("proposed", "confirmed", "rescheduled", "cancelled", "completed", "no_show")


def build_plan(plan_id, participants, *, time=None, place=None, room=None, state="proposed",
               created_at=None, version=1, match_id=None):
    if state not in PLAN_STATE:
        raise ValueError("bad plan state: %r" % state)
    if place is not None and room is not None:
        raise ValueError("plan has either a place OR a room, not both")
    return {"plan_id": plan_id, "participants": list(participants), "time": time,
            "place": place, "room": room, "state": state, "match_id": match_id,
            "created_at": created_at, "version": int(version)}
