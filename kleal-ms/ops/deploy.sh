#!/usr/bin/env bash
# Deploy the restored matching + the shared config to the pod.
# Uploads only — nothing is restarted, so a bad upload can never take a service down. Restart with
#   ops/run.sh restart <service>   (locally)  /  kill by listening-socket PID then start (pod)
#
# Order is load-bearing: shared/config.py must land BEFORE any service that imports it is
# restarted, or that service dies on import with an empty log.
#
# Each file: base64 over stdin (RunPod SSH is PTY-only, no scp) -> sha256 compare -> ast.parse
# for .py -> timestamped backup -> atomic mv. Nothing is restarted here; restarts are a separate
# step so a bad upload never takes a service down.
set -u
# Override for another box: KLEAL_SSH="ssh ... root@host" ops/deploy.sh
SSH="${KLEAL_SSH:-ssh -o ConnectTimeout=25 -o BatchMode=yes -i $HOME/.ssh/id_ed25519 -p 24309 root@195.26.233.30}"
LOCAL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_ROOT="/root/kleal-ms"
STAMP="$(date +%Y%m%d_%H%M%S)"

# One path per line, no comments and no blanks — the loop below word-splits this string, so anything
# that is not a path becomes a "MISSING LOCALLY" failure.
#
# The kleal_* modules ARE the matching service; app.py is a dispatcher over them. They were absent
# from this list, so editing kleal_intent.py uploaded nothing and prod ran a new app.py against the
# old engine, with no error anywhere to say so.
FILES="
shared/config.py
shared/contracts.md
shared/llm_client.py
shared/http_util.py
shared/kleal_lib.py
config/Kleal_Matching_Core_Config_v2.yaml
matching_core/config/validator.py
matching_core/group_formation/constraints.py
matching_core/group_formation/former.py
matching_core/group_formation/utility.py
services/matching/core_v2.py
services/matching/matching_core_engine.py
services/matching/kleal_candidates.py
services/matching/kleal_completion.py
services/matching/kleal_contract_registry.py
services/matching/kleal_contracts.py
services/matching/kleal_groups.py
services/matching/kleal_intent.py
services/matching/kleal_ml_boundary.py
services/matching/kleal_protocol.py
services/matching/kleal_states.py
services/matching/kleal_taxonomy.py
services/matching/app.py
services/gateway/app.py
services/llm/app.py
services/onboarding/app.py
services/buddy/app.py
services/filtration/app.py
services/admin/app.py
services/profile/app.py
services/admin/test_admin.py
services/buddy/test_buddy.py
services/filtration/test_filtration.py
tools/e2e_smoke.py
tools/flows_smoke.py
tools/age_range_test.js
tools/card_tags_test.js
tools/gsize_test.js
tools/talks_test.js
tools/meetups_tabs_test.js
tools/groups_smoke.py
ops/run.sh
"

fail=0
for rel in $FILES; do
  src="$LOCAL_ROOT/$rel"
  dst="$REMOTE_ROOT/$rel"
  [ -f "$src" ] || { echo "MISSING LOCALLY: $rel"; fail=1; continue; }
  want="$(shasum -a 256 "$src" | cut -d' ' -f1)"
  bytes="$(wc -c < "$src" | tr -d ' ')"

  out=$(base64 < "$src" | $SSH "
    set -e
    mkdir -p \$(dirname '$dst')
    base64 -d > '$dst.new'
    got=\$(sha256sum '$dst.new' | cut -d' ' -f1)
    if [ \"\$got\" != '$want' ]; then echo \"SHA_MISMATCH got=\$got\"; rm -f '$dst.new'; exit 1; fi
    case '$rel' in
      *.py) python3 -c \"import ast,sys; ast.parse(open('$dst.new',encoding='utf-8').read())\" || { echo PARSE_FAIL; rm -f '$dst.new'; exit 1; } ;;
      *.sh) bash -n '$dst.new' || { echo BASH_SYNTAX_FAIL; rm -f '$dst.new'; exit 1; } ;;
    esac
    [ -f '$dst' ] && cp -p '$dst' '$dst.bak_$STAMP'
    mv '$dst.new' '$dst'
    echo OK \$(stat -c%s '$dst')
  " 2>&1)

  if echo "$out" | grep -q "^OK"; then
    printf "  ok    %-42s %8s bytes\n" "$rel" "$bytes"
  else
    printf "  FAIL  %-42s %s\n" "$rel" "$(echo "$out" | tr '\n' ' ' | cut -c1-100)"
    fail=1
  fi
done

echo
if [ "$fail" -ne 0 ]; then
  echo "UPLOAD FAILED — nothing restarted, pod still serving the previous bytes."
  exit 1
fi
echo "all files uploaded and verified (backups: *.bak_$STAMP)"
