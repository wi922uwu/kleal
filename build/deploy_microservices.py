# -*- coding: utf-8 -*-
# Deploy the Kleal MICROSERVICES to the pod under /root/kleal-ms/, preserving the existing cloudflared
# tunnel on :7080 (so the public URL is unchanged). Ships 8 files (5 services + 3 shared) via chunked
# gzip+base64 over PTY-only SSH, verifies sha256 + ast, kills the old monolith, and launches all 5
# services with the secret boundary intact (SELF_* only on llm-service). Pipe:
#   python build/deploy_microservices.py && ssh -tt ... < build/_deploy_ms.sh
import gzip, base64, hashlib, os

ROOT = r"C:\Projects\.dating"
# (local path, remote relative path under /root/kleal-ms/, shell var)
FILES = [
    ("shared/llm_client.py",          "shared/llm_client.py",          "f_llmc"),
    ("shared/kleal_lib.py",           "shared/kleal_lib.py",           "f_klib"),
    ("shared/http_util.py",           "shared/http_util.py",           "f_http"),
    ("services/llm/app.py",           "services/llm/app.py",           "f_llm"),
    ("services/onboarding/app.py",    "services/onboarding/app.py",    "f_onb"),
    ("services/profile/app.py",       "services/profile/app.py",       "f_prof"),
    ("services/matching/app.py",      "services/matching/app.py",      "f_match"),
    ("services/filtration/app.py",    "services/filtration/app.py",    "f_filter"),
    ("services/buddy/app.py",         "services/buddy/app.py",         "f_buddy"),
    ("services/gateway/app.py",       "services/gateway/app.py",       "f_gw"),
]
CH = 1800
L = ["stty -echo 2>/dev/null",
     "mkdir -p /root/kleal-ms/shared /root/kleal-ms/services/gateway /root/kleal-ms/services/llm "
     "/root/kleal-ms/services/onboarding /root/kleal-ms/services/matching /root/kleal-ms/services/filtration "
     "/root/kleal-ms/services/buddy /root/kleal-ms/services/profile"]

shas = {}
for local, remote, var in FILES:
    data = open(os.path.join(ROOT, local.replace("/", os.sep)), "rb").read()
    shas[var] = hashlib.sha256(data).hexdigest()
    b64 = base64.b64encode(gzip.compress(data, 9)).decode("ascii")
    L.append(": > /tmp/%s.b64.gz" % var)
    for i in range(0, len(b64), CH):
        L.append("printf '%%s' '%s' >> /tmp/%s.b64.gz" % (b64[i:i+CH], var))
    L.append("base64 -d /tmp/%s.b64.gz | gunzip > /root/kleal-ms/%s.new" % (var, remote))

L.append("echo '===VERIFY==='")
checks = []
for local, remote, var in FILES:
    L.append('G=$(sha256sum /root/kleal-ms/%s.new | cut -d" " -f1); '
             '[ "$G" = "%s" ] && echo "sha_ok %s" || echo "SHA_FAIL %s"' % (remote, shas[var], var, var))
    L.append('python3 -c "import ast; ast.parse(open(\'/root/kleal-ms/%s.new\').read())" '
             '&& echo "ast_ok %s" || echo "AST_FAIL %s"' % (remote, var, var))

# all-good gate: verify every sha matches, then swap
cond = " && ".join('[ "$(sha256sum /root/kleal-ms/%s.new | awk \'{print $1}\')" = "%s" ]' % (remote, shas[var])
                   for local, remote, var in FILES)
L.append("if %s; then" % cond)
for local, remote, var in FILES:
    L.append("  mv /root/kleal-ms/%s.new /root/kleal-ms/%s" % (remote, remote))
L.append("  echo '===SWAPPED==='")
# stop old monolith + any previous microservices
L.append("  pkill -9 -f kleal_v2.py 2>/dev/null; pkill -9 -f kleal_profile.py 2>/dev/null; pkill -9 -f kleal_hub.py 2>/dev/null")
L.append("  pkill -9 -f 'services/.*app.py' 2>/dev/null; sleep 2")   # matches the relative launch cmdline (python3 -u services/<name>/app.py)
# read the EXISTING tunnel URL (do NOT touch cloudflared)
L.append("  HUB=$(grep -Eo 'https://[a-z0-9-]+\\.trycloudflare\\.com' /root/cf7080.log | head -1)")
L.append('  echo "HUB=$HUB"')
L.append("  cd /root/kleal-ms")
# llm-service — the ONLY one with SELF_* (points at the self-hosted vLLM on :8002)
L.append("  LLM_PORT=7071 SELF_BASE=http://localhost:8002/v1 SELF_KEY=x "
         "nohup setsid python3 -u services/llm/app.py > /root/ms_llm.log 2>&1 < /dev/null &")
L.append("  sleep 3")
# onboarding + matching: LLM_URL only, NO keys
L.append('  ONBOARDING_PORT=7072 LLM_URL=http://localhost:7071 V2_MODEL=llama_self KLEAL_USERS=/root/kleal-ms/users.json PROFILE_URL="$HUB/profile" '
         "nohup setsid python3 -u services/onboarding/app.py > /root/ms_onboarding.log 2>&1 < /dev/null &")
L.append("  PROFILE_PORT=7073 nohup setsid python3 -u services/profile/app.py > /root/ms_profile.log 2>&1 < /dev/null &")
L.append("  MATCHING_PORT=7074 LLM_URL=http://localhost:7071 V2_MODEL=llama_self KLEAL_USERS=/root/kleal-ms/users.json "
         "nohup setsid python3 -u services/matching/app.py > /root/ms_matching.log 2>&1 < /dev/null &")
L.append("  FILTER_PORT=7076 LLM_URL=http://localhost:7071 V2_MODEL=llama_self "
         "nohup setsid python3 -u services/filtration/app.py > /root/ms_filtration.log 2>&1 < /dev/null &")
L.append("  sleep 3")
# buddy (conversational) — needs llm + matching + filtration up first
L.append("  BUDDY_PORT=7075 LLM_URL=http://localhost:7071 MATCH_URL=http://localhost:7074 FILTER_URL=http://localhost:7076 V2_MODEL=llama_self "
         "nohup setsid python3 -u services/buddy/app.py > /root/ms_buddy.log 2>&1 < /dev/null &")
L.append("  sleep 2")   # NB: the admin panel is deployed separately via build/deploy_admin.py (own tunnel)
# gateway LAST on :7080 (same port the tunnel already targets)
L.append("  HUB_PORT=7080 HUB_ONB=http://127.0.0.1:7072 HUB_PROF=http://127.0.0.1:7073 HUB_MATCH=http://127.0.0.1:7074 "
         "HUB_BUDDY=http://127.0.0.1:7075 HUB_FILTER=http://127.0.0.1:7076 "
         "nohup setsid python3 -u services/gateway/app.py > /root/ms_gateway.log 2>&1 < /dev/null &")
L.append("  sleep 5")
L.append("  echo '===HEALTH==='")
L.append('  curl -s -m6 -o /dev/null -w "llm=%{http_code}\\n" localhost:7071/llm/models')
L.append('  curl -s -m6 -o /dev/null -w "onb=%{http_code}\\n" localhost:7072/')
L.append('  curl -s -m6 -o /dev/null -w "prof=%{http_code}\\n" localhost:7073/')
L.append('  curl -s -m6 -o /dev/null -w "match=%{http_code}\\n" localhost:7074/api/agent/weights')
L.append('  curl -s -m6 -o /dev/null -w "filter=%{http_code}\\n" localhost:7076/')
L.append('  curl -s -m6 -o /dev/null -w "buddy=%{http_code}\\n" localhost:7075/')
L.append('  curl -s -m6 -o /dev/null -w "gw_root=%{http_code}\\n" localhost:7080/')
L.append('  curl -s -m8 -o /dev/null -w "gw_profile=%{http_code}\\n" localhost:7080/profile')
L.append('  curl -s -m8 -o /dev/null -w "gw_agent=%{http_code}\\n" localhost:7080/api/agent/weights')
L.append('  echo "===FINAL_URL==="; echo "$HUB"')
L.append("else echo SHA_MISMATCH; fi")
L.append("echo '===DONE==='")
L.append("exit")

out = os.path.join(ROOT, "build", "_deploy_ms.sh")
open(out, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
print("files:", len(FILES), "| lines:", len(L))
print("script:", out)
