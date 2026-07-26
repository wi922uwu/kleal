# -*- coding: utf-8 -*-
"""§14.3/§14.4 + Приложение B.2 — транзакционный accept + одновременные принятия + гонки.

`Orchestrator.accept_proposal` реализует B.2 в одной транзакции: idempotency → assert_transition →
policy.revalidate → capacity CAS → version CAS → create match → outbox. Каждая гонка (§14.4) завершается
детерминированным кодом и не раскрывает лишней информации (§14.4).
"""
import threading
from . import state_machines as SM
from . import concurrency as CC
from ..policy_engine import revalidation as REV
from ..policy_engine.engine import ALLOW

# §14.3 — политика одновременных принятий по типу intent.
CONCURRENT_ACCEPT_POLICY = {
    "1to1_fixed_time": "after_first_match_withdraw_or_choose",
    "multiple_conversations": "hold_several_mutual_no_auto_plan",
    "group_formation": "accept_creates_reservation_final_after_quorum",
    "event": "capacity_transaction_then_waitlist",
    "dating": "no_auto_commit_user_confirms_each",
}

# §14.4 — восемь критических гонок → детерминированный код (без утечки данных).
RACE_CODES = {
    "privacy_changed_before_accept": "POLICY_CHANGED",
    "both_took_last_slot": "CAPACITY_EXCEEDED",
    "intent_cancelled_delayed_notif": "INTENT_CANCELLED",
    "blocked_after_mutual": "POLICY_CHANGED",
    "counter_after_expiry": "EXPIRED",
    "two_waves_duplicate_pair": "DUPLICATE_PAIR",
    "notification_repeated": "DEDUPED",
    "timezone_made_slot_impossible": "SLOT_INFEASIBLE",
}


def resolve_race(case, ctx=None):
    """Детерминированный исход гонки (§14.4). Возвращает {code, leak:false}."""
    if case not in RACE_CODES:
        raise ValueError("unknown race case: %r" % case)
    return {"code": RACE_CODES[case], "leak": False}


class Outbox:
    """Transactional outbox (§14.2): retry-safe, dedup по event_id (C: notification service repeat)."""
    def __init__(self):
        self._seen = set()
        self.events = []

    def publish(self, event_id, kind, payload):
        with CC._LOCK:
            if event_id in self._seen:
                return False              # уже опубликовано — идемпотентно
            self._seen.add(event_id)
            self.events.append({"event_id": event_id, "kind": kind, "payload": payload})
            return True


class Orchestrator:
    def __init__(self):
        self.proposals = CC.VersionedStore()
        self.matches = CC.VersionedStore()
        self.idem = CC.IdempotencyStore()
        self.pairs = CC.UniquePairRegistry()
        self.capacity = CC.CapacityLedger()
        self.outbox = Outbox()
        self._lock = threading.RLock()

    def register_proposal(self, proposal):
        self.proposals.put(proposal["proposal_id"], proposal)
        return proposal

    def accept_proposal(self, proposal_id, actor_id, idem_key, *, candidate, intent, baseline,
                        ctx=None, now=0.0, resource=None, capacity_max=1, intent_type=None,
                        dating_confirmed=False):
        """B.2 + §14.3. Возвращает {ok, code, match, withdrawn}. Коды: EXPIRED / POLICY_CHANGED /
        CAPACITY_EXCEEDED / INVALID_TRANSITION / DATING_CONFIRM_REQUIRED. Повтор idem_key -> тот же результат (C#7).
        §14.3: dating без dating_confirmed не авто-коммитит; 1:1 fixed-time withdraw-ит прочие предложения искателя."""
        with self._lock:
            hit, res = self.idem.assert_or_return(idem_key)
            if hit:
                return res                                    # C#7 идемпотентность

            p = self.proposals.get(proposal_id)
            if p is None:
                return self._fail(idem_key, "NOT_FOUND")

            it_type = intent_type or (intent.get("type") if isinstance(intent, dict) else None)
            if it_type == "dating" and not dating_confirmed:
                # §14.3: dating — никаких auto-commit; требуется явное подтверждение (НЕ мемоизируем,
                # чтобы повтор с подтверждением прошёл)
                return {"ok": False, "code": "DATING_CONFIRM_REQUIRED", "match": None, "withdrawn": []}

            # C#9 expired нельзя принять
            exp = p.get("expires_at")
            if exp is not None and float(now) >= float(exp):
                return self._fail(idem_key, "EXPIRED")

            # переход допустим? (C#10 counter/withdrawn -> нельзя ACCEPT)
            try:
                SM.assert_transition("proposal", p["status"], "ACCEPTED")
            except SM.InvalidTransition:
                return self._fail(idem_key, "INVALID_TRANSITION")

            # policy revalidation в той же транзакции (C#6 privacy между SENT и ACCEPT)
            rv = REV.revalidate(baseline, candidate, intent, ctx, checkpoint="on_accept")
            if not rv["ok"]:
                return self._fail(idem_key, "POLICY_CHANGED")

            # capacity CAS (C#8 два accept последнего слота)
            if resource is not None:
                ok, _cur = self.capacity.claim_slot(resource, capacity_max)
                if not ok:
                    return self._fail(idem_key, "CAPACITY_EXCEEDED")

            # version CAS обновление proposal -> ACCEPTED
            try:
                self.proposals.compare_and_swap(proposal_id, p["version"], {"status": "ACCEPTED"})
            except CC.VersionConflict:
                if resource is not None:
                    self.capacity.release_slot(resource)
                return self._fail(idem_key, "VERSION_CONFLICT")

            # create/advance match + outbox
            mid = "match:%s" % proposal_id
            match = {"match_id": mid, "participants": [p.get("from"), p.get("to")],
                     "status": "MUTUAL", "version": 1}
            self.matches.put(mid, match)
            self.outbox.publish("evt:%s:accepted" % proposal_id, "match_state_changed", match)

            # §14.3: 1:1 fixed-time -> withdraw остальные активные предложения искателя
            withdrawn = []
            if it_type in ("1to1_fixed_time", "1to1"):
                frm = p.get("from")
                for pid2, p2 in self.proposals.items():
                    if pid2 != proposal_id and p2.get("from") == frm and \
                            p2.get("status") in ("SENT", "VIEWED", "CREATED", "RESERVED"):
                        try:
                            self.proposals.compare_and_swap(pid2, p2["version"], {"status": "WITHDRAWN"})
                            withdrawn.append(pid2)
                        except CC.VersionConflict:
                            pass

            result = {"ok": True, "code": "ACCEPTED", "match": match, "withdrawn": withdrawn}
            self.idem.store_result(idem_key, result)
            return result

    def _fail(self, idem_key, code):
        result = {"ok": False, "code": code, "match": None}
        self.idem.store_result(idem_key, result)             # тот же код при повторе (детерминизм)
        return result
