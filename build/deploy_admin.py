# -*- coding: utf-8 -*-
# Deploy ONLY the admin panel (+ the store-aware matching) to the pod, on its OWN cloudflared tunnel.
# Minimal blast radius for the shared 2-dev pod: it restarts ONLY matching (~5s) and starts a NEW,
# independent tunnel for admin on :7077 — it does NOT touch llm/onboarding/profile/buddy/filtration/
# gateway or the main :7080 app tunnel. Admin has NO token; its protection is the separate obscure URL.
#   python build/deploy_admin.py && ssh -tt ... < build/_deploy_admin.sh
import gzip, base64, hashlib, os

ROOT = r"C:\Projects\.dating"
# ADMIN_ONLY=1  -> ship ONLY admin/app.py and restart ONLY admin (matching + tunnel untouched).
ADMIN_ONLY = os.environ.get("ADMIN_ONLY") == "1"
_ALL = [
    ("shared/llm_client.py",       "shared/llm_client.py",       "a_llmc"),
    ("shared/kleal_lib.py",        "shared/kleal_lib.py",        "a_klib"),
    ("shared/http_util.py",        "shared/http_util.py",        "a_http"),
    ("shared/kleal_contracts.py",  "shared/kleal_contracts.py",  "a_kcon"),   # §4 contracts — admin AND the restarted matching import it
    ("shared/kleal_intent.py",     "shared/kleal_intent.py",     "a_kint"),   # §5 intent compiler — the restarted matching imports it
    ("shared/kleal_taxonomy.py",   "shared/kleal_taxonomy.py",   "a_ktax"),   # §6 taxonomy layer — the restarted matching imports it
    ("shared/kleal_completion.py", "shared/kleal_completion.py", "a_kcmp"),   # §10.2 completion factors — the restarted matching imports it
    ("shared/kleal_ml_boundary.py","shared/kleal_ml_boundary.py","a_kmlb"),   # §10.3 ML boundary — the restarted matching imports it
    ("shared/kleal_protocol.py",   "shared/kleal_protocol.py",   "a_kprot"),  # §13 typed agent protocol — the restarted matching imports it
    ("shared/kleal_states.py",     "shared/kleal_states.py",     "a_kstate"), # §14 transaction state machines — the restarted matching imports it
    ("shared/kleal_groups.py",     "shared/kleal_groups.py",     "a_kgrp"),   # §15 group formation core (pilot-disabled) — the restarted matching imports it
    ("shared/kleal_candidates.py", "shared/kleal_candidates.py", "a_kcand"),  # §16 event/room/venue candidate types (pilot-disabled) — the restarted matching imports it
    ("shared/kleal_contract_registry.py", "shared/kleal_contract_registry.py", "a_kreg"),  # §22.2.0/§23.4.1 registry — the restarted matching imports it
    ("services/matching/app.py",   "services/matching/app.py",   "a_match"),
    ("services/admin/app.py",      "services/admin/app.py",      "a_admin"),
]
# ADMIN_ONLY still ships the NEW shared deps (§4 contracts, §5 intent, §6 taxonomy, §10 completion + ML-boundary):
# unlike http_util/kleal_lib (already on the pod from prior full deploys), all are imported by the matching
# process this script restarts, so a solo admin deploy must carry them or matching fails to import on relaunch.
FILES = [f for f in _ALL if f[2] in ("a_admin", "a_kcon", "a_kint", "a_ktax", "a_kcmp", "a_kmlb", "a_kprot", "a_kstate", "a_kgrp", "a_kcand", "a_kreg")] if ADMIN_ONLY else _ALL
CH = 1800
L = ["stty -echo 2>/dev/null",
     "mkdir -p /root/kleal-ms/shared /root/kleal-ms/services/matching /root/kleal-ms/services/admin"]

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
for local, remote, var in FILES:
    L.append('python3 -c "import ast; ast.parse(open(\'/root/kleal-ms/%s.new\').read())" && echo "ast_ok %s" || echo "AST_FAIL %s"' % (remote, var, var))

cond = " && ".join('[ "$(sha256sum /root/kleal-ms/%s.new | awk \'{print $1}\')" = "%s" ]' % (remote, shas[var])
                   for local, remote, var in FILES)
L.append("if %s; then" % cond)
for local, remote, var in FILES:
    L.append("  mv /root/kleal-ms/%s.new /root/kleal-ms/%s" % (remote, remote))
L.append("  echo '===SWAPPED==='")
L.append("  cd /root/kleal-ms")
if not ADMIN_ONLY:
    # restart ONLY matching (targeted) so it picks up the shared user store; everything else untouched
    L.append("  pkill -9 -f 'services/matching/app.py' 2>/dev/null; sleep 1")
    L.append("  MATCHING_PORT=7074 LLM_URL=http://localhost:7071 V2_MODEL=llama_self KLEAL_USERS=/root/kleal-ms/users.json "
             "nohup setsid python3 -u services/matching/app.py > /root/ms_matching.log 2>&1 < /dev/null &")
    L.append("  sleep 3")
# (re)start admin on :7077 — standalone, no token
L.append("  pkill -9 -f 'services/admin/app.py' 2>/dev/null; sleep 1")
L.append("  ADMIN_PORT=7077 MATCH_URL=http://localhost:7074 KLEAL_USERS=/root/kleal-ms/users.json "
         "nohup setsid python3 -u services/admin/app.py > /root/ms_admin.log 2>&1 < /dev/null &")
L.append("  sleep 3")
# start a SEPARATE cloudflared tunnel for admin (:7077) if not already up — never touches the main :7080 tunnel
L.append("  if ! pgrep -f 'cloudflared.*localhost:7077' >/dev/null 2>&1; then")
L.append("    nohup /root/cloudflared-linux-amd64 tunnel --url http://localhost:7077 > /root/cf_admin.log 2>&1 & disown")
L.append("    sleep 8")
L.append("  fi")
L.append("  echo '===HEALTH==='")
L.append('  curl -s -m6 -o /dev/null -w "matching=%{http_code}\\n" localhost:7074/api/agent/weights')
L.append('  curl -s -m6 -o /dev/null -w "pool=%{http_code}\\n" localhost:7074/api/agent/pool')
L.append('  curl -s -m6 -o /dev/null -w "admin=%{http_code}\\n" localhost:7077/admin')
L.append('  curl -s -m6 -w "admin_users(count) -> " localhost:7077/api/admin/users | python3 -c "import sys,json;print(json.load(sys.stdin).get(\\"count\\"))" 2>/dev/null')
L.append("  AURL=$(grep -Eo 'https://[a-z0-9-]+\\.trycloudflare\\.com' /root/cf_admin.log | head -1)")
L.append('  echo "===ADMIN_URL==="; echo "$AURL/admin"')
L.append("else echo SHA_MISMATCH; fi")
L.append("echo '===DONE==='")
L.append("exit")

out = os.path.join(ROOT, "build", "_deploy_admin.sh")
open(out, "w", encoding="utf-8", newline="\n").write("\n".join(L) + "\n")
print("admin deploy files:", len(FILES), "| lines:", len(L))
print("script:", out)
print("NOTE: restarts ONLY matching (~5s) + starts admin + a separate admin tunnel. Main app untouched.")
