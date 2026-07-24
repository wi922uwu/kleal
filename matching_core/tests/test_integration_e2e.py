# -*- coding: utf-8 -*-
"""Аудит P1#17 — FULL END-TO-END integration tests.

Не unit-точность отдельных модулей, а прогон ПОЛЬЗОВАТЕЛЬСКОГО FLOW через авторитетные entrypoints:
7 сценариев аудита — intent→search→invite→(policy change→revalidation)→accept→plan; friendship→dating
leakage; blocked-after-search; two concurrent accepts; multiple active intents; T4 event fallback;
no-exact→consented expansion. Доказывают, что исправления реально защищают flow, а не лежат отдельно.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.config import validator as V
from matching_core.orchestrator import pipeline as P
from matching_core.orchestrator import transitions as TR
from matching_core.orchestrator import intent_set as ISET
from matching_core.policy_engine import revalidation as REV
from matching_core.plan_coordination import plans as PLC
from matching_core.feedback_learning import feedback as FBK

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def _raises(fn):
    try:
        fn(); return False
    except P.PipelineError:
        return True


def run():
    cfg = V.load_config()
    me = {"name": "me", "interests": ["dota2"], "vibe": "calm", "langs": ["en"]}
    games = lambda **kw: dict({"type": "games", "topics": ["dota2"], "mode": "online", "version": 1}, **kw)

    # ===== СЦЕНАРИЙ 1: intent → search → invite → accept → plan =====
    cand = {"name": "c1", "interests": ["dota2"], "intents": [{"topics": ["dota2"]}], "open": True,
            "langs": ["en"], "vibe": "calm", "accountStatus": "active", "visibility": "public"}
    intent = games()
    res = P.run_search(intent, me, [cand], cfg, now=1.0, search_id="s1")
    item = next((x for x in res["slate"] if x["name"] == "c1"), None)
    check("E2E1 search нашёл кандидата + baseline + trace", item is not None and "revalidation_baseline" in item and res["traces"] >= 1)
    snd = P.authorize_and_send(candidate=cand, intent=intent, cfg=cfg, now=2.0,
                               baseline=item["revalidation_baseline"], gate_ctx={"blocked": set()})
    check("E2E1 invite: authorization + revalidation before_send -> SENT", snd["sent"] and snd["code"] == "SENT")
    orc = TR.Orchestrator()
    orc.register_proposal({"proposal_id": "p1", "from": "me", "to": "c1", "status": "SENT", "expires_at": 1e9, "version": 1})
    acc = orc.accept_proposal("p1", "c1", "k1", candidate=cand, intent=intent,
                              baseline=REV.capture_baseline(cand, intent), ctx={"blocked": set()}, now=3.0)
    check("E2E1 accept -> match (транзакция)", acc["ok"] and acc["code"] == "ACCEPTED")
    pc = PLC.PlanCoordinator()
    plan = pc.create("pl1", ["me", "c1"], match_id=acc["match"]["match_id"], time={"windows": [["20:00", "22:00"]]})
    t1 = pc.transition("pl1", "confirmed", plan["version"])
    t2 = pc.transition("pl1", "completed", t1["plan"]["version"])
    check("E2E1 plan proposed->confirmed->completed", t1["ok"] and t2["ok"] and t2["plan"]["state"] == "completed")

    # ===== СЦЕНАРИЙ 2: friendship → dating leakage =====
    check("E2E2 generic dating search ЗАПРЕЩЁН (нет утечки в dating-контур)",
          _raises(lambda: P.run_search({"type": "dating", "topics": ["coffee"], "version": 1}, me, [], cfg, now=1.0, search_id="d")))
    fr_cand = {"name": "f1", "interests": ["coffee"], "open": True, "langs": ["en"], "vibe": "chill", "datingOk": True}
    fr = P.run_search({"type": "social", "topics": ["coffee"], "mode": "offline", "version": 1},
                      {"name": "me", "interests": ["coffee"], "vibe": "chill", "langs": ["en"]}, [fr_cand], cfg, now=1.0, search_id="fr")
    check("E2E2 friendship-поиск: purpose=friendship И datingOk-кандидат РЕАЛЬНО в slate КАК friendship",
          fr["purpose"] == "friendship" and any(x["name"] == "f1" for x in fr["slate"]))
    store = {}
    FBK.record_outcome(store, "f1", "safety", "block", scope="dating")
    check("E2E2 dating-feedback НЕ протекает в friendship scope",
          len(FBK.get_scoped_feedback(store, "f1", "friendship")) == 0 and len(FBK.get_scoped_feedback(store, "f1", "dating")) >= 1)

    # ===== СЦЕНАРИЙ 3: blocked candidate after search =====
    res3 = P.run_search(games(), me, [dict(cand, name="b1")], cfg, now=1.0, search_id="s3")
    it3 = next((x for x in res3["slate"] if x["name"] == "b1"), None)
    check("E2E3 кандидат найден до блокировки", it3 is not None)
    snd3 = P.authorize_and_send(candidate=dict(cand, name="b1", blocksMe=True), intent=games(), cfg=cfg, now=2.0,
                                baseline=it3["revalidation_baseline"], gate_ctx={"blocked": set()})
    check("E2E3 blocked-after-search -> НЕ отправлено (fail-closed)", snd3["sent"] is False)

    # ===== СЦЕНАРИЙ 4: two concurrent accepts (последний слот) =====
    orc4 = TR.Orchestrator()
    c4 = {"name": "x", "age": 30, "verified": True, "langs": ["en"], "km": 2, "open": True}
    i4 = {"type": "social_meet", "mode": "offline", "time": {}, "version": 1}
    b4 = REV.capture_baseline(c4, i4)
    orc4.register_proposal({"proposal_id": "pa", "from": "a", "to": "x", "status": "SENT", "expires_at": 1e9, "version": 1})
    orc4.register_proposal({"proposal_id": "pb", "from": "b", "to": "x", "status": "SENT", "expires_at": 1e9, "version": 1})
    ra = orc4.accept_proposal("pa", "x", "ka", candidate=c4, intent=i4, baseline=b4, ctx={"blocked": set()}, now=1.0, resource="slot:x", capacity_max=1)
    rb = orc4.accept_proposal("pb", "x", "kb", candidate=c4, intent=i4, baseline=b4, ctx={"blocked": set()}, now=1.0, resource="slot:x", capacity_max=1)
    check("E2E4 два accept последнего слота: один ok, второй CAPACITY_EXCEEDED",
          (ra["ok"] and not rb["ok"] and rb["code"] == "CAPACITY_EXCEEDED") or (rb["ok"] and not ra["ok"] and ra["code"] == "CAPACITY_EXCEEDED"))

    # ===== СЦЕНАРИЙ 5: multiple active intents =====
    gi, di = {"type": "games", "domain": "games", "topics": ["dota2"]}, {"type": "dating", "domain": "dating", "topics": ["coffee"]}
    sel = ISET.select_for_reverse_reciprocity({"type": "games"}, [gi, di])
    check("E2E5 обратная взаимность берёт СОВМЕСТИМЫЙ по purpose intent (games, не dating)", sel is gi)
    kept, over = ISET.enforce_limit([dict(gi) for _ in range(7)])
    check("E2E5 лимит активных intent = 5", len(kept) == 5 and len(over) == 2)

    # ===== СЦЕНАРИЙ 6: T4 event fallback =====
    res6 = P.run_search(games(expansion_policy="event_fallback_allowed"), me,
                        [{"name": "Ev", "kind": "event", "topics": ["dota2"], "category": "games",
                          "capacity": {"current": 0, "max": 10}, "access": "open"}], cfg, now=1.0, search_id="s6")
    check("E2E6 T4 event fallback -> в alternatives (typed model, не person top-N)",
          any(a["name"] == "Ev" and a["tier"] == "T4" for a in res6["alternatives"])
          and all(x["name"] != "Ev" for x in res6["slate"]))

    # ===== СЦЕНАРИЙ 7: no exact results → consented expansion =====
    lol = {"name": "lol1", "interests": ["lol"], "open": True, "langs": ["en"], "vibe": "calm"}
    r_exact = P.run_search(games(expansion_policy="exact_only"), me, [lol], cfg, now=1.0, search_id="s7a")
    check("E2E7 exact_only + только parent(lol) -> пусто (adjacent без consent не показываем)", len(r_exact["slate"]) == 0)
    r_family = P.run_search(games(expansion_policy="allow_family"), me, [lol], cfg, now=1.0, search_id="s7b")
    check("E2E7 allow_family -> parent(lol T2) появляется (consented expansion)",
          any(x["name"] == "lol1" for x in r_family["slate"]))

    print("\nАудит P1#17 (full end-to-end integration): %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
