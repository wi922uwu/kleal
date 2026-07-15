# -*- coding: utf-8 -*-
# Deploy ONE app service to the pod and restart ONLY it — minimal blast radius for the shared 2-dev pod
# (no kill-all, other services + tunnels untouched). Ships services/<SERVICE>/app.py, sha+ast verifies,
# then pkills just that one process and relaunches it with the right env.
#   SERVICE=onboarding python build/deploy_one.py && ssh -tt ... < build/_deploy_one.sh
import gzip, base64, hashlib, os

ROOT = r"C:\Projects\.dating"
SERVICE = os.environ.get("SERVICE", "").strip()

# per-service (port, launch command run from /root/kleal-ms). $HUB is the public app URL (from cf7080.log).
SVC = {
    "onboarding": (7072, 'ONBOARDING_PORT=7072 LLM_URL=http://localhost:7071 V2_MODEL=llama_self PROFILE_URL="$HUB/profile" '
                         'nohup setsid python3 -u services/onboarding/app.py > /root/ms_onboarding.log 2>&1 < /dev/null &'),
    "buddy":      (7075, 'BUDDY_PORT=7075 LLM_URL=http://localhost:7071 MATCH_URL=http://localhost:7074 FILTER_URL=http://localhost:7076 V2_MODEL=llama_self '
                         'nohup setsid python3 -u services/buddy/app.py > /root/ms_buddy.log 2>&1 < /dev/null &'),
    "filtration": (7076, 'FILTER_PORT=7076 LLM_URL=http://localhost:7071 V2_MODEL=llama_self '
                         'nohup setsid python3 -u services/filtration/app.py > /root/ms_filtration.log 2>&1 < /dev/null &'),
    "profile":    (7073, 'PROFILE_PORT=7073 nohup setsid python3 -u services/profile/app.py > /root/ms_profile.log 2>&1 < /dev/null &'),
    "matching":   (7074, 'MATCHING_PORT=7074 LLM_URL=http://localhost:7071 V2_MODEL=llama_self KLEAL_USERS=/root/kleal-ms/users.json '
                         'nohup setsid python3 -u services/matching/app.py > /root/ms_matching.log 2>&1 < /dev/null &'),
}
if SERVICE not in SVC:
    raise SystemExit("Set SERVICE to one of: %s" % ", ".join(SVC))
port, launch = SVC[SERVICE]

data = open(os.path.join(ROOT, "services", SERVICE, "app.py"), "rb").read()
sha = hashlib.sha256(data).hexdigest()
b64 = base64.b64encode(gzip.compress(data, 9)).decode("ascii")
CH = 1800
L = ["stty -echo 2>/dev/null", "mkdir -p /root/kleal-ms/services/%s" % SERVICE, ": > /tmp/one.b64.gz"]
for i in range(0, len(b64), CH):
    L.append("printf '%%s' '%s' >> /tmp/one.b64.gz" % b64[i:i+CH])
L.append("base64 -d /tmp/one.b64.gz | gunzip > /root/kleal-ms/services/%s/app.py.new" % SERVICE)
L.append('python3 -c "import ast; ast.parse(open(\'/root/kleal-ms/services/%s/app.py.new\').read())" && echo ast_ok || echo AST_FAIL' % SERVICE)
L.append('if [ "$(sha256sum /root/kleal-ms/services/%s/app.py.new | awk \'{print $1}\')" = "%s" ]; then' % (SERVICE, sha))
L.append("  mv /root/kleal-ms/services/%s/app.py.new /root/kleal-ms/services/%s/app.py" % (SERVICE, SERVICE))
L.append("  echo SWAPPED")
L.append("  cd /root/kleal-ms")
L.append("  HUB=$(grep -Eo 'https://[a-z0-9-]+\\.trycloudflare\\.com' /root/cf7080.log | head -1)")
L.append("  pkill -9 -f 'services/%s/app.py' 2>/dev/null; sleep 1" % SERVICE)
L.append("  " + launch)
L.append("  sleep 3")
L.append('  curl -s -m6 -o /dev/null -w "%s=%%{http_code}\\n" localhost:%d/' % (SERVICE, port))
L.append('  curl -s -m8 -o /dev/null -w "via_gateway=%{http_code}\\n" localhost:7080/')
L.append("else echo SHA_MISMATCH; fi")
L.append("echo ===DONE===; exit")

out = os.path.join(ROOT, "build", "_deploy_one.sh")
open(out, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
print("service:", SERVICE, "| port:", port, "| lines:", len(L))
print("script:", out)
