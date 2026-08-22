# -*- coding: utf-8 -*-
"""§19 feedback/learning — outcome taxonomy, isolation (C#13), bias (§23.3)."""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
from matching_core.feedback_learning import feedback as FB

R = {"pass": 0, "fail": 0}


def check(name, cond):
    R["pass" if cond else "fail"] += 1
    print(("  ok  " if cond else " FAIL ") + name)


def run():
    store = {}
    FB.record_outcome(store, "bob", "completion", "completed", scope="default")
    FB.record_outcome(store, "bob", "quality", "would_repeat", scope="default")
    ev = FB.scoped_events(store, "bob", "default")
    check("FB1 record + scoped events", len(ev) == 2)
    check("FB2 completed positive (нет safety-neg)", FB.is_completed_positive(ev))
    FB.record_outcome(store, "bob", "safety", "report", scope="default")
    check("FB3 safety report -> НЕ completed positive", not FB.is_completed_positive(FB.scoped_events(store, "bob", "default")))

    # §19.2 правила обновления профиля
    check("FB4 explicit -> update stable", FB.profile_update_rule("x", explicit=True) == "update_stable_preference")
    check("FB5 одно поведение -> нет вечного вывода", FB.profile_update_rule("x", repeat_count=1) == "no_permanent_inference")
    check("FB6 повтор -> suggestion", FB.profile_update_rule("x", repeat_count=3) == "create_suggestion")
    check("FB7 sensitive повтор -> подтверждение", FB.profile_update_rule("x", repeat_count=3, sensitive=True) == "suggestion_pending_confirmation")

    # C#13: dating decline НЕ виден friendship-ранкеру (isolation)
    dstore = {}
    FB.record_outcome(dstore, "alice", "proposal", "decline", scope="dating")
    check("C#13 dating scope содержит decline", len(FB.get_scoped_feedback(dstore, "alice", "dating")) == 1)
    check("C#13 friendship scope НЕ видит dating decline", len(FB.get_scoped_feedback(dstore, "alice", "friendship")) == 0)

    # §19.3 bias
    check("FB8 timeout != личное несовпадение", FB.classify_nonresponse({"signal": "timeout"}) == "not_a_personal_mismatch")
    check("FB9 не обучаться на timeout как на отказе", FB.should_train_on({"stage": "proposal", "signal": "timeout"}) is False)
    check("FB10 «не увидел» != «отказал»",
          FB.classify_nonresponse({"signal": "skip"}) == "not_seen" and FB.classify_nonresponse({"signal": "decline"}) == "declined")
    g = FB.bias_guardrails()
    check("FB11 safety/fairness отдельно от uplift", g["safety_fairness_checked_separately"])

    print("\n§19 feedback: %d passed, %d failed" % (R["pass"], R["fail"]))
    return R["fail"] == 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
