# -*- coding: utf-8 -*-
# Deploy the Kleal onboarding + profile BUNDLE to the pod (PTY-only SSH, gzip+base64 chunks):
#   /root/kleal_profile.py  -> served on :7073 (static, no LLM) behind its own cloudflared tunnel
#   /root/kleal_v2.py       -> served on :7072 (uses self-hosted Llama at localhost:8002) behind its tunnel
# The onboarding "My Profile" handoff needs the profile app's PUBLIC url, so the remote script starts the
# profile tunnel FIRST, greps its trycloudflare url, then launches kleal_v2 with PROFILE_URL=<that url>.
# kleal_v2 imports llm_demo_local -> cp the already-deployed /root/llm_demo_app.py (byte-identical) into place.
# Pipe to: ssh -tt ... < build/_deploy_bundle.sh
import gzip, base64, hashlib

def chunks_for(path, var):
    data = open(path, "rb").read()
    sha = hashlib.sha256(data).hexdigest()
    b64 = base64.b64encode(gzip.compress(data, 9)).decode("ascii")
    CH = 1800
    lines = [": > /tmp/%s.b64.gz" % var]
    for i in range(0, len(b64), CH):
        lines.append("printf '%%s' '%s' >> /tmp/%s.b64.gz" % (b64[i:i+CH], var))
    return sha, lines, len(b64)

pv2, cv2, n2 = chunks_for(r"C:\Projects\.dating\kleal_v2.py", "v2")
ppr, cpr, np = chunks_for(r"C:\Projects\.dating\kleal_profile.py", "prof")

L = ["stty -echo 2>/dev/null"]
L += cpr + cv2
L += [
    "base64 -d /tmp/prof.b64.gz | gunzip > /root/kleal_profile.py.new",
    "base64 -d /tmp/v2.b64.gz  | gunzip > /root/kleal_v2.py.new",
    "echo '===SHA==='",
    'PG=$(sha256sum /root/kleal_profile.py.new | cut -d" " -f1); echo "prof_got=$PG"; echo "prof_exp=%s"' % ppr,
    'VG=$(sha256sum /root/kleal_v2.py.new | cut -d" " -f1); echo "v2_got=$VG"; echo "v2_exp=%s"' % pv2,
    'if [ "$PG" = "%s" ] && [ "$VG" = "%s" ]; then' % (ppr, pv2),
    "  python3 -c \"import ast; ast.parse(open('/root/kleal_profile.py.new').read())\" && echo PROF_PARSE_OK || echo PROF_PARSE_FAIL",
    "  python3 -c \"import ast; ast.parse(open('/root/kleal_v2.py.new').read())\" && echo V2_PARSE_OK || echo V2_PARSE_FAIL",
    "  cp /root/llm_demo_app.py /root/llm_demo_local.py",
    "  mv /root/kleal_profile.py.new /root/kleal_profile.py",
    "  mv /root/kleal_v2.py.new /root/kleal_v2.py",
    "  pkill -9 -f kleal_profile.py 2>/dev/null; pkill -9 -f kleal_v2.py 2>/dev/null; sleep 2",
    # profile app :7073
    "  cd /root && PROFILE_PORT=7073 nohup setsid python3 -u /root/kleal_profile.py > /root/kleal_profile.log 2>&1 < /dev/null &",
    "  sleep 4",
    '  echo "===PROFLOG==="; tail -n 3 /root/kleal_profile.log',
    '  echo "===HTTP7073==="; curl -s -m6 -o /dev/null -w "prof=%{http_code}\\n" localhost:7073/',
    # tunnel for :7073 -> capture its public url
    '  pkill -f "cloudflared.*7073" 2>/dev/null; sleep 1',
    "  nohup /root/cloudflared-linux-amd64 tunnel --url http://localhost:7073 > /root/cf7073.log 2>&1 & disown",
    "  sleep 11",
    "  PURL=$(grep -Eo 'https://[a-z0-9-]+\\.trycloudflare\\.com' /root/cf7073.log | head -1)",
    '  echo "===PROFILE_URL==="; echo "$PURL"',
    # onboarding :7072 with the profile url baked into the handoff
    '  cd /root && V2_PORT=7072 V2_MODEL=llama_self SELF_BASE=http://localhost:8002/v1 SELF_KEY=x DEMO_PORT=0 PROFILE_URL="$PURL" nohup setsid python3 -u /root/kleal_v2.py > /root/kleal_v2.log 2>&1 < /dev/null &',
    "  sleep 5",
    '  echo "===V2LOG==="; tail -n 4 /root/kleal_v2.log',
    '  echo "===HTTP7072==="; curl -s -m6 -o /dev/null -w "onb=%{http_code}\\n" localhost:7072/',
    '  pkill -f "cloudflared.*7072" 2>/dev/null; sleep 1',
    "  nohup /root/cloudflared-linux-amd64 tunnel --url http://localhost:7072 > /root/cf7072.log 2>&1 & disown",
    "  sleep 11",
    "  OURL=$(grep -Eo 'https://[a-z0-9-]+\\.trycloudflare\\.com' /root/cf7072.log | head -1)",
    '  echo "===ONBOARD_URL==="; echo "$OURL"',
    "else echo SHA_MISMATCH; fi",
    "echo '===DEPLOYEND==='",
    "exit",
]
out = r"C:\Projects\.dating\build\_deploy_bundle.sh"
open(out, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
print("kleal_v2 gz+b64:", n2, "| kleal_profile gz+b64:", np, "| lines:", len(L))
print("v2 sha:", pv2)
print("prof sha:", ppr)
print("script:", out)
