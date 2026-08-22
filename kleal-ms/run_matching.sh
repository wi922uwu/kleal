#!/bin/bash
# matching-service powered by matching_core (clean-rebuild). Restart ONLY matching (no kill-all, tunnel untouched).
# Rollback options:
#   - KLEAL_ENGINE=core_v2 here (Dev B engine; core_v2.py is shipped alongside), OR
#   - restore Dev B's live service dir: mv services/_matching_removed_20260722-2232 -> services/matching
# NOTE: KLEAL_CORE_CONFIG must point at the 21505ccb config (matching_core PINNED_SHA); the pod's
# config/Kleal_Matching_Core_Config_v2.yaml is a DIFFERENT sha (d804df8e) and will fail the pin.
cd /root/kleal-ms || exit 1
pkill -f "services/matching/app.py" 2>/dev/null
sleep 1
MATCHING_PORT=7074 LLM_URL=http://localhost:7071 V2_MODEL=llama_self \
  KLEAL_USERS=/root/kleal-ms/users.json \
  KLEAL_ENGINE=matching_core \
  KLEAL_CORE_CONFIG=/root/kleal-ms/services/matching/Kleal_Matching_Core_Config_v2.yaml \
  nohup setsid python3 -u services/matching/app.py > /root/ms_matching.log 2>&1 < /dev/null &
sleep 3
echo "matching (matching_core) started on :7074"
tail -3 /root/ms_matching.log
