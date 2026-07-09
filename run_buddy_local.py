# Local launcher for the Buddy API (:8090).
# Points the LLM at the pod's :8002 cloudflared tunnel (refresh when the tunnel/pod restarts).
# Seeds a few demo profiles into a local SQLite so matching returns something.
import os

os.environ.setdefault("LLM_BASE", os.environ.get("SELF_BASE", "https://YOUR-8002-TUNNEL.trycloudflare.com/v1"))
os.environ.setdefault("LLM_KEY", "x")
os.environ.setdefault("LLM_MODEL", "llama-3.3-70b")
os.environ.setdefault("BUDDY_TOOL_MODE", "prompt")
os.environ.setdefault("BUDDY_PORT", "8090")
os.environ.setdefault("BUDDY_DB", "buddy_local.db")

from buddy import api, store as store_mod

if not api.store.list_profiles():
    store_mod.seed_demo(api.store)
    print("seeded %d demo profiles" % len(api.store.list_profiles()))

api.serve()
