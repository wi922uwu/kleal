# -*- coding: utf-8 -*-
# Kleal dev orchestrator — boots all five microservices as subprocesses (stdlib only, no docker).
#   python run_all.py            # start everything; open http://127.0.0.1:7080
#   python run_all.py --no-llm   # skip llm-service (front-end only iteration)
#
# Secret boundary is enforced HERE: only the llm-service child receives the API keys from .env.
# The other four children run with those keys SCRUBBED from their environment.
import os
import sys
import time
import signal
import threading
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
NO_LLM = "--no-llm" in sys.argv

SECRET_KEYS = ("AITUNNEL_KEY", "AITUNNEL_BASE", "SELF_BASE", "SELF_KEY",
               "RUNPOD_KEY", "RUNPOD_BASE", "ALIA_BASE")


def load_env(path):
    d = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    d[k.strip()] = v.strip()
    return d


secrets = load_env(os.path.join(HERE, ".env"))          # keys live only here
model = secrets.get("V2_MODEL", os.environ.get("V2_MODEL", "llama_self"))
profile_url = os.environ.get("PROFILE_URL", "")          # onboarding -> profile hand-off (blank = local)
users_path = os.path.join(HERE, "services", "matching", "users.json")   # shared user store (admin writes, matching reads)

# (name, script, extra_env, gets_secrets)
SERVICES = [
    ("llm",        "services/llm/app.py",        {"LLM_PORT": "7071"}, True),
    ("onboarding", "services/onboarding/app.py", {"ONBOARDING_PORT": "7072", "LLM_URL": "http://127.0.0.1:7071",
                                                  "V2_MODEL": model, "PROFILE_URL": profile_url}, False),
    ("profile",    "services/profile/app.py",    {"PROFILE_PORT": "7073"}, False),
    ("matching",   "services/matching/app.py",   {"MATCHING_PORT": "7074", "LLM_URL": "http://127.0.0.1:7071",
                                                  "V2_MODEL": model, "KLEAL_USERS": users_path}, False),
    ("filtration", "services/filtration/app.py", {"FILTER_PORT": "7076", "LLM_URL": "http://127.0.0.1:7071",
                                                  "V2_MODEL": model}, False),
    ("buddy",      "services/buddy/app.py",      {"BUDDY_PORT": "7075", "LLM_URL": "http://127.0.0.1:7071",
                                                  "MATCH_URL": "http://127.0.0.1:7074",
                                                  "FILTER_URL": "http://127.0.0.1:7076", "V2_MODEL": model}, False),
    ("admin",      "services/admin/app.py",      {"ADMIN_PORT": "7077", "MATCH_URL": "http://127.0.0.1:7074",
                                                  "KLEAL_USERS": users_path}, False),   # standalone (own URL, no gateway route)
    ("gateway",    "services/gateway/app.py",    {"HUB_PORT": "7080", "HUB_ONB": "http://127.0.0.1:7072",
                                                  "HUB_PROF": "http://127.0.0.1:7073",
                                                  "HUB_MATCH": "http://127.0.0.1:7074",
                                                  "HUB_BUDDY": "http://127.0.0.1:7075",
                                                  "HUB_FILTER": "http://127.0.0.1:7076"}, False),
]

procs = []


def stream(name, p):
    for line in iter(p.stdout.readline, b""):
        sys.stdout.write("[%-10s] %s" % (name, line.decode("utf-8", "replace")))
        sys.stdout.flush()


def stop(*_a):
    for _n, p in procs:
        try:
            p.terminate()
        except Exception:
            pass
    sys.exit(0)


signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)

for name, script, extra, gets_secrets in SERVICES:
    if name == "llm" and NO_LLM:
        print("[run_all] skipping llm-service (--no-llm)")
        continue
    env = dict(os.environ)
    for k in SECRET_KEYS:                 # scrub inherited secrets from EVERY child by default
        env.pop(k, None)
    if gets_secrets:                      # ...then give them back ONLY to llm-service
        env.update({k: v for k, v in secrets.items() if k in SECRET_KEYS})
    env.update(extra)
    p = subprocess.Popen([sys.executable, "-u", os.path.join(HERE, script)],
                         env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    procs.append((name, p))
    threading.Thread(target=stream, args=(name, p), daemon=True).start()
    time.sleep(0.6)                       # let each bind its port before the next (gateway last)

print("\n  Kleal is up →  http://127.0.0.1:7080   (Ctrl-C to stop)\n")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    stop()
