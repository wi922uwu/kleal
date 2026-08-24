# -*- coding: utf-8 -*-
"""Regression checks at the matching-service entrypoints (no network or production data)."""
import importlib.util
import os
import sys


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)
spec = importlib.util.spec_from_file_location("matching_taxonomy_app", os.path.join(HERE, "app.py"))
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

FAIL = []


def check(name, condition):
    print(("  ok  " if condition else " FAIL ") + name)
    if not condition:
        FAIL.append(name)


def run():
    candidate = {
        "name": "Soisaoi", "age": 23,
        "interests": ["night driving", "hiking", "trading forex", "nasdaq"],
        "open": True, "langs": ["ru", "en"], "vibe": "calm", "verified": True,
        "accountStatus": "active", "visibility": "public", "pending": 0,
    }
    M.load_candidates = lambda: [candidate]
    M._users_cache = {"mtime": None, "list": None}
    M.PHRASE_TOPICS["поговорить про крипту"] = {"bitcoin", "blockchain", "crypto", "cryptocurrency"}
    intent = {"type": "social", "topics": ["crypto", "project"], "phrase": "Поговорить про крипту",
              "_query": "Поговорить про крипту", "mode": "online", "adjacentAllowed": True}
    profile = {"name": "Сява", "age": 25, "interests": ["crypto"], "langs": ["ru"]}
    ctx = {"uid": "syava"}

    cards = M.match_candidates(intent, profile, ctx)
    card = next((c for c in cards if c.get("name") == "Soisaoi"), None)
    check("production regression reaches a personal semantic tier", bool(card and card.get("tier") == "T2"))

    report = M.explain_match(intent, profile, ctx)
    explained = next((c for c in report.get("matched", []) + report.get("considered", [])
                      if c.get("name") == "Soisaoi"), None)
    check("slate explain has semantic parity with match", bool(explained and explained.get("tier") == "T2"))

    with M._matching_topic_context(intent) as effective:
        trace = M._core.explain(effective, profile, dict(ctx, now=1.0, received24={}), candidate,
                                M._H, M._CORE_CFG)
    semantic = next((s for s in trace.get("steps", []) if s.get("step") == "semantic tier"), {})
    check("pair explain has semantic parity with match", semantic.get("ok") is True and "T2" in semantic.get("detail", ""))

    # Learned aliases still work through the repaired core bridge, including a compound profile interest.
    M.PHRASE_TOPICS["поговорить про опционы"] = {"finance", "investing", "options", "stock"}
    M.PHRASE_TOPICS["trading forex"] = {"finance", "investing", "trading", "forex"}
    learned = dict(intent, topics=["options"], phrase="поговорить про опционы",
                   _query="поговорить про опционы")
    with M._matching_topic_context(learned) as effective:
        learned_tier = M._core.assign_tier(effective, candidate)
    check("learned phrase bridge reaches matching_core", learned_tier != "T5")

    print("\nmatching taxonomy service: %d passed, %d failed" % (4 - len(FAIL), len(FAIL)))
    return not FAIL


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
