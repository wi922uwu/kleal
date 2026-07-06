# -*- coding: utf-8 -*-
# Generate a remote bash script that deploys Kleal Onboarding V2 to the pod:
#   - reconstruct /root/kleal_v2.py from gzip+base64 chunks (RunPod proxy SSH is PTY-only, no scp)
#   - verify sha256 + ast.parse
#   - cp /root/llm_demo_app.py -> /root/llm_demo_local.py  (kleal_v2 imports llm_demo_local; the two
#     files are byte-identical locally, so the already-deployed master serves as the dependency)
#   - run V2 on :7072 against the self-hosted Llama at localhost:8002 (does NOT touch the :7070 demo)
#   - open a cloudflared quick-tunnel for :7072 and print the public URL
# Pipe the generated script to `ssh -tt ... < build/_deploy_v2.sh`.
import gzip, base64, hashlib

fp = r"C:\Projects\.dating\kleal_v2.py"
data = open(fp, "rb").read()
sha = hashlib.sha256(data).hexdigest()
b64 = base64.b64encode(gzip.compress(data, 9)).decode("ascii")
CH = 1800
chunks = [b64[i:i+CH] for i in range(0, len(b64), CH)]

L = ["stty -echo 2>/dev/null", ": > /tmp/v2.b64.gz"]
for c in chunks:
    L.append("printf '%%s' '%s' >> /tmp/v2.b64.gz" % c)
L += [
    "base64 -d /tmp/v2.b64.gz | gunzip > /root/kleal_v2.py.new",
    "echo '===SHA==='",
    'GOT=$(sha256sum /root/kleal_v2.py.new | cut -d" " -f1)',
    'echo "got=$GOT"; echo "exp=%s"' % sha,
    'if [ "$GOT" = "%s" ]; then' % sha,
    "  python3 -c \"import ast; ast.parse(open('/root/kleal_v2.py.new').read())\" && echo V2_PARSE_OK || echo V2_PARSE_FAIL",
    "  cp /root/llm_demo_app.py /root/llm_demo_local.py",
    "  mv /root/kleal_v2.py.new /root/kleal_v2.py",
    "  pkill -9 -f kleal_v2.py 2>/dev/null; sleep 2",
    "  cd /root && V2_PORT=7072 V2_MODEL=llama_self SELF_BASE=http://localhost:8002/v1 SELF_KEY=x DEMO_PORT=0 nohup setsid python3 -u /root/kleal_v2.py > /root/kleal_v2.log 2>&1 < /dev/null &",
    "  sleep 6",
    "  echo '===V2LOG==='; tail -n 8 /root/kleal_v2.log",
    '  echo "===HTTP7072==="; curl -s -m6 -o /dev/null -w "root=%{http_code}\\n" localhost:7072/',
    "  echo '===STATE==='; curl -s -m8 -X POST localhost:7072/api/v2/state -H 'Content-Type: application/json' -d '{\"profile\":{}}'; echo",
    '  pkill -f "cloudflared.*7072" 2>/dev/null; sleep 1',
    "  nohup /root/cloudflared-linux-amd64 tunnel --url http://localhost:7072 > /root/cf7072.log 2>&1 & disown",
    "  sleep 10",
    "  echo '===CF7072==='; grep -Eo 'https://[a-z0-9-]+\\.trycloudflare\\.com' /root/cf7072.log | head -1",
    "else echo SHA_MISMATCH; fi",
    "echo '===DEPLOYEND==='",
    "exit",
]
out = r"C:\Projects\.dating\build\_deploy_v2.sh"
open(out, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
print("kleal_v2.py bytes:", len(data), "| gz+b64 len:", len(b64), "| chunks:", len(chunks))
print("sha:", sha)
print("script:", out, "| lines:", len(L))
