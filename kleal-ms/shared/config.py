# -*- coding: utf-8 -*-
"""Kleal topology — the single source of truth for ports, inter-service URLs and file paths.

Why this file exists. Every one of these values used to be written out again in each service
that needed it, and the copies drifted:

  * The user store was resolved independently by onboarding, matching and admin. One of them
    defaulted to `services/matching/users.json` while the others defaulted to `<kleal-ms>/users.json`,
    so a restart without KLEAL_USERS silently SPLIT the store — the admin panel edited one file
    while the matcher ranked people out of another, and nothing anywhere said so. Both copies have
    since been hand-patched to agree; this file makes agreeing the only possible outcome.
  * The same service was reachable under two env-var names (`HUB_FILTER` in the gateway,
    `FILTER_URL` in buddy and onboarding), so setting one of them moved half the traffic.

Rules:
  - Ports and URLs are derived from ONE port table. A URL is never typed out by hand.
  - Every value stays environment-overridable, and the OLD variable names keep working, so a
    running pod does not need its environment rewritten to take this change.
  - Paths resolve against <kleal-ms>/ regardless of which service imports this, so a service
    started from any working directory still finds the same store.

No secrets and no network live here. Model endpoints/keys belong to llm-service alone.
"""
import os

# <kleal-ms>/ — this file is <kleal-ms>/shared/config.py, so two levels up is the project root.
# Deliberately derived from __file__ and not from the caller's cwd: services are started by
# `cd /root/kleal-ms && python3 services/<name>/app.py`, but tests and tools are not.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _env(names, default):
    """First set variable among `names` wins; `names[0]` is the current spelling, the rest are
    older ones kept alive so an already-running box does not need its environment changed."""
    for n in names:
        v = os.environ.get(n)
        if v not in (None, ""):
            return v
    return default


# ---------------------------------------------------------------- ports
# The whole topology in one table. Everything below is derived from it.
PORTS = {
    "llm":         int(_env(["LLM_PORT"], 7071)),
    "onboarding":  int(_env(["ONBOARDING_PORT"], 7072)),
    "profile":     int(_env(["PROFILE_PORT"], 7073)),
    "matching":    int(_env(["MATCHING_PORT"], 7074)),
    "buddy":       int(_env(["BUDDY_PORT"], 7075)),
    "filtration":  int(_env(["FILTER_PORT"], 7076)),
    "admin":       int(_env(["ADMIN_PORT"], 7077)),
    "gateway":     int(_env(["HUB_PORT", "GATEWAY_PORT"], 7080)),
}

# Explicit URL overrides, per service. The first name is the current spelling; the HUB_* forms are
# what the gateway used to call the same thing and are still honoured.
_URL_ENV = {
    "llm":        ["LLM_URL"],
    "onboarding": ["ONBOARDING_URL", "HUB_ONB"],
    "profile":    ["PROFILE_SVC_URL", "HUB_PROF"],
    "matching":   ["MATCH_URL", "HUB_MATCH"],
    "buddy":      ["BUDDY_URL", "HUB_BUDDY"],
    "filtration": ["FILTER_URL", "HUB_FILTER"],
    "admin":      ["ADMIN_URL"],
}


def url(service):
    """Base URL of a service: an explicit override if set, otherwise derived from its port.
    Always without a trailing slash — callers concatenate paths onto it."""
    return _env(_URL_ENV.get(service, []), "http://127.0.0.1:%d" % PORTS[service]).rstrip("/")


LLM_URL = url("llm")
ONBOARDING_URL = url("onboarding")
PROFILE_URL = url("profile")
MATCH_URL = url("matching")
BUDDY_URL = url("buddy")
FILTER_URL = url("filtration")
ADMIN_URL = url("admin")

# Services bind loopback only; the gateway is the single process on a public interface.
BIND_HOST = os.environ.get("KLEAL_BIND", "127.0.0.1")
GATEWAY_BIND_HOST = os.environ.get("KLEAL_GATEWAY_BIND", "0.0.0.0")


# ---------------------------------------------------------------- data files
# THE shared user store. Onboarding is its only writer; matching ranks out of it and admin edits it.
# Every service must resolve this to the same file — see the split-store incident above.
USERS = _env(["KLEAL_USERS"], os.path.join(ROOT, "users.json"))
ACCOUNTS = _env(["KLEAL_ACCOUNTS"], os.path.join(ROOT, "accounts.json"))
ADMIN_TOKEN_FILE = _env(["KLEAL_ADMIN_TOKEN_FILE"], os.path.join(ROOT, "admin_token.txt"))

# Per-service private state. Unlike USERS these are NOT shared and never read by anyone else.
BUDDY_STORE = _env(["BUDDY_STORE"], os.path.join(ROOT, "services", "buddy", "buddy_store.json"))
MATCHING_STORE = _env(["KLEAL_STORE"], os.path.join(ROOT, "services", "matching", "kleal_store.json"))

# Configuration read at startup.
TAXONOMY = _env(["KLEAL_TAXONOMY"], os.path.join(ROOT, "config", "kleal_taxonomy_v1.json"))
MATCHING_CONFIG = _env(["KLEAL_MATCHING_CONFIG"],
                       os.path.join(ROOT, "config", "Kleal_Matching_Core_Config_v2.yaml"))


# ---------------------------------------------------------------- models
# An id from llm-service's MODELS table, not a provider model name. llm-service resolves it.
MODEL_ID = _env(["V2_MODEL"], "llama_self")


def describe():
    """One-line-per-value dump, for a service's startup banner and the admin health view."""
    return {
        "root": ROOT,
        "ports": dict(PORTS),
        "urls": {k: url(k) for k in _URL_ENV},
        "users": os.path.abspath(USERS),
        "accounts": os.path.abspath(ACCOUNTS),
        "taxonomy": os.path.abspath(TAXONOMY),
        "matching_config": os.path.abspath(MATCHING_CONFIG),
        "model": MODEL_ID,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(describe(), indent=2, ensure_ascii=False))
