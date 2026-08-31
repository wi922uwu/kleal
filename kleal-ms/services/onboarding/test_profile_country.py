#!/usr/bin/env python3
"""Country persistence needed by privacy-safe online intent discovery."""
import json
import os
import sys
import tempfile


FAILS = []


def check(name, ok, got=None):
    print(("  ok  " if ok else "FAIL  ") + name + ("" if ok else " -> %r" % (got,)))
    if not ok:
        FAILS.append(name)


with tempfile.TemporaryDirectory() as td:
    users_path = os.path.join(td, "users.json")
    accounts_path = os.path.join(td, "accounts.json")
    with open(users_path, "w", encoding="utf-8") as fh:
        json.dump({"users": []}, fh)
    with open(accounts_path, "w", encoding="utf-8") as fh:
        json.dump({}, fh)
    os.environ["KLEAL_USERS"] = users_path
    os.environ["KLEAL_ACCOUNTS"] = accounts_path
    os.environ["KLEAL_DB"] = "json"
    os.environ["KLEAL_MQ"] = "none"

    here = os.path.dirname(os.path.abspath(__file__))
    shared = os.path.join(os.path.dirname(os.path.dirname(here)), "shared")
    for path in (here, shared):
        if path not in sys.path:
            sys.path.insert(0, path)
    import app as onboarding

    profile = {
        "name": "Ana", "age": 29, "country": " Spain ", "city": "Barcelona",
        "geo": {"comfortableAreas": ["Barcelona"], "coarseLat": 41.4, "coarseLon": 2.1},
        "languages": {"comfortable": ["English"]}, "interests": {"explicit": ["coffee"]},
    }
    row = onboarding._profile_to_user(profile)
    check("registration projection preserves confirmed country", row.get("country") == "Spain", row)

    with open(users_path, "w", encoding="utf-8") as fh:
        json.dump({"users": [row]}, fh)
    result = onboarding.update_user("Ana", {"country": " Portugal "})
    check("profile API accepts a bounded country update",
          result.get("ok") is True and result.get("user", {}).get("country") == "Portugal", result)
    rejected = onboarding.update_user("Ana", {"country": {"prompt": "junk"}})
    check("profile API rejects non-string country payload",
          rejected.get("ok") is False and rejected.get("error") == "no editable fields in patch", rejected)


print()
if FAILS:
    print("FAILED %d: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("ALL PASS (%d checks)" % 3)
