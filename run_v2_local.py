# Local launcher for Kleal Onboarding V2 preview (port 7072).
# Points the self-hosted model at the pod's :8002 cloudflared tunnel (for the interests chat step).
# Refresh SELF_BASE if the tunnel/pod restarts.
import os
# Point SELF_BASE at your pod's :8002 cloudflared tunnel (or set it via env). Placeholder below.
os.environ.setdefault("SELF_BASE", "https://YOUR-8002-TUNNEL.trycloudflare.com/v1")
os.environ.setdefault("SELF_KEY", "x")
os.environ.setdefault("V2_PORT", "7072")
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "kleal_v2.py"), encoding="utf-8").read()
exec(compile(_src, "kleal_v2.py", "exec"))
