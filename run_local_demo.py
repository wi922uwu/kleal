# Local demo launcher for preview (port 7071): points the self-hosted model at the pod's
# cloudflared tunnel so the 7th model (llama_self) works in local preview too, not only on
# the pod (:7070). NOTE: the trycloudflare URL is ephemeral — when the tunnel/pod restarts,
# refresh SELF_BASE below (URL comes from /root/cf8002.log on the pod). The 6 aitunnel models
# work without this. Self-hosted model = Llama-3.3-70B-Instruct AWQ on our A100 via vLLM :8002.
import os

# Point SELF_BASE at your pod's :8002 cloudflared tunnel (or set it via env). Placeholder below.
os.environ.setdefault("SELF_BASE", "https://YOUR-8002-TUNNEL.trycloudflare.com/v1")
os.environ.setdefault("SELF_KEY", "x")
os.environ.setdefault("DEMO_PORT", "7071")

# Run the master demo file as-is (its __main__ block starts the server).
_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm_demo_local.py"), encoding="utf-8").read()
exec(compile(_src, "llm_demo_local.py", "exec"))
