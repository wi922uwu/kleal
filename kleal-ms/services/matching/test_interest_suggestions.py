# -*- coding: utf-8 -*-
"""Focused contract for repeated-interest evidence; no network or production data."""
import os
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from interest_suggestions import COOLDOWN_SECONDS, InterestSuggestionTracker


FAIL = []
TOTAL = 0


def check(name, condition):
    global TOTAL
    TOTAL += 1
    print(("  ok  " if condition else " FAIL ") + name)
    if not condition:
        FAIL.append(name)


def signal(tracker, number, topic="crypto", **extra):
    return tracker.record("user", "event-%s" % number, [topic], now=float(number), **extra)


def run():
    store = {}
    saves = []
    tracker = InterestSuggestionTracker(store, save=lambda: saves.append(1))

    for n in range(1, 6):
        out = signal(tracker, n, "crypto" if n % 2 else "криптовалютами")
    check("5 -> no popup", out["suggestion"] is None)
    out = signal(tracker, 6, "cryptocurrency")
    check("6 -> popup", bool(out["suggestion"] and out["suggestion"]["evidence_count"] == 6))
    check("synonyms share canonical counter", len(store["users"]["user"]["interests"]) == 1)

    before = out["suggestion"]["evidence_count"]
    duplicate = signal(tracker, 6, "crypto")
    check("duplicate event id does not increment", duplicate["suggestion"]["evidence_count"] == before)

    repeated_store = {}
    repeated = InterestSuggestionTracker(repeated_store)
    repeated.record("user", "repeated-word", ["crypto", "крипта", "cryptocurrency", "crypto"], now=1)
    repeated_count = next(iter(repeated_store["users"]["user"]["interests"].values()))["count"]
    check("one event counts one canonical interest once", repeated_count == 1)
    check("raw topic text is not persisted", "cryptocurrency" not in repr(repeated_store))

    neg_store = {}
    neg = InterestSuggestionTracker(neg_store)
    neg.record("user", "neg-1", ["crypto"], negative_topics=["криптовалюта"], now=1)
    check("negated topic is excluded", not neg_store["users"]["user"]["interests"])

    existing_store = {}
    existing = InterestSuggestionTracker(existing_store)
    for n in range(1, 7):
        existing.record("user", "existing-%s" % n, ["crypto"], profile_interests=["крипта"], now=n)
    check("existing profile interest suppresses popup", existing.pending("user", ["crypto"], now=7) is None)

    sid = out["suggestion"]["id"]
    check("dismiss is accepted", tracker.act("user", sid, "dismiss", now=10)["ok"])
    for n in (7, 8, 9):
        out = signal(tracker, n)
    check("new evidence inside cooldown does not spam", out["suggestion"] is None)
    out = tracker.record("user", "event-10", ["crypto"], now=10 + COOLDOWN_SECONDS + 1)
    check("reoffer follows cooldown plus new evidence", bool(out["suggestion"]))
    check("confirm is explicit terminal action", tracker.act("user", out["suggestion"]["id"], "confirm", now=50)["ok"])
    check("confirmed interest is not proposed again", signal(tracker, 11)["suggestion"] is None)

    concurrent_store = {}
    concurrent = InterestSuggestionTracker(concurrent_store)
    threads = [threading.Thread(target=lambda: concurrent.record("user", "same-event", ["padel"], now=1))
               for _ in range(12)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    count = next(iter(concurrent_store["users"]["user"]["interests"].values()))["count"]
    check("concurrent duplicate delivery counts once", count == 1)

    forgotten = tracker.forget("user")
    check("profile-data deletion can erase evidence", forgotten["removed"] and "user" not in store["users"])
    check("state is persisted through supplied store writer", bool(saves))

    # Integration boundary: only a launched, idempotently identified intent reaches evidence.
    import app as matching_app
    matching_app.SESSION = {"_intents": [], "_interest_suggestions": {}}
    matching_app._save_store = lambda: None
    matching_app._INTEREST_TRACKER = InterestSuggestionTracker(
        matching_app.SESSION["_interest_suggestions"], matching_app._STORE_LOCK, lambda: None)
    draft = matching_app.save_intent("integration-user", {"topics": ["crypto"]}, "draft",
                                     launched=False, event_id="draft-event")
    check("draft intent is not evidence", "interest_suggestion" not in draft and
          not matching_app.SESSION["_interest_suggestions"]["users"])
    for number in range(1, 7):
        launched = matching_app.save_intent(
            "integration-user", {"topics": ["крипта"]}, "search", launched=True,
            event_id="launch-%s" % number, profile_interests=[])
    check("sixth launched intent returns suggestion in API result",
          launched.get("interest_suggestion", {}).get("evidence_count") == 6)

    print("\ninterest suggestions: %d passed, %d failed" % (TOTAL - len(FAIL), len(FAIL)))
    return not FAIL


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
