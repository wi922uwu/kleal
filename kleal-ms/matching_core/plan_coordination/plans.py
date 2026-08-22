# -*- coding: utf-8 -*-
"""§14 (Plan) + §21.2 POST /plans — координация плана с version-check.

Состояния плана меняются ТОЛЬКО через assert_transition + optimistic version (§14.2, §23.2 п.13).
Точное место раскрывается лишь после нужного уровня согласия (§8.4). Плана либо place, либо room.
"""
from ..contracts import plan as PL
from ..orchestrator import state_machines as SM
from ..orchestrator import concurrency as CC

# соответствие «нижних» состояний контракта верхним состояниям автомата §14.1.
_MACHINE_STATE = {"proposed": "PROPOSED", "partially_confirmed": "PARTIALLY_CONFIRMED",
                  "confirmed": "CONFIRMED", "changed": "CHANGED", "completed": "COMPLETED",
                  "cancelled": "CANCELLED", "no_show": "NO_SHOW", "draft": "DRAFT"}


class PlanCoordinator:
    def __init__(self):
        self.store = CC.VersionedStore()

    def create(self, plan_id, participants, *, time=None, place=None, room=None, match_id=None, created_at=None):
        p = PL.build_plan(plan_id, participants, time=time, place=place, room=room, match_id=match_id,
                          state="proposed", created_at=created_at, version=1)
        return self.store.put(plan_id, p)

    def transition(self, plan_id, to_state, expected_version, *, updates=None):
        """Смена состояния плана с проверкой перехода (§14.1) и версии (§14.2). Возвращает {ok, code, plan}."""
        p = self.store.get(plan_id)
        if p is None:
            return {"ok": False, "code": "NOT_FOUND", "plan": None}
        frm, to = _MACHINE_STATE.get(p["state"]), _MACHINE_STATE.get(to_state)
        if to is None:
            return {"ok": False, "code": "BAD_STATE", "plan": None}
        try:
            SM.assert_transition("plan", frm, to)
        except SM.InvalidTransition:
            return {"ok": False, "code": "INVALID_TRANSITION", "plan": None}
        try:
            patch = dict(updates or {}); patch["state"] = to_state
            updated = self.store.compare_and_swap(plan_id, expected_version, patch)
        except CC.VersionConflict:
            return {"ok": False, "code": "VERSION_CONFLICT", "plan": None}
        return {"ok": True, "code": "OK", "plan": updated}
