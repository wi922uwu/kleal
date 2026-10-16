#!/bin/bash
# Наполнение пула сценариев до цели. Запускается и петлёй службы (по чуть-чуть каждый круг),
# и руками, когда нужно набрать сразу: KLEAL_POOL_TARGET=1200 bash tools/pool_fill.sh
set -u
TARGET="${KLEAL_POOL_TARGET:-1200}"
POOL=/root/kleal-archive/scenarios.jsonl
cd /opt/kleal/kleal-ms
while :; do
  N=$(wc -l < "$POOL" 2>/dev/null || echo 0)
  [ "$N" -ge "$TARGET" ] && { echo "пул набран: $N"; break; }
  timeout 600 python3 tools/scenario_gen.py 12 >/dev/null 2>&1
  M=$(wc -l < "$POOL" 2>/dev/null || echo 0)
  echo "[$(date +%H:%M:%S)] пул: $M / $TARGET"
  [ "$M" -le "$N" ] && sleep 5   # ничего не добавилось — не крутить вхолостую
done
