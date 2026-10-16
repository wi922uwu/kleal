#!/bin/bash
# Батарея без перерыва: гоняет сценарии, копит историю, чистит старые журналы.
#
# ЗАЧЕМ ПАУЗА, ЕСЛИ «БЕЗ ПЕРЕРЫВА». Модель на поде одна на всех: пока батарея говорит с ней, живой
# человек в приложении ждёт в той же очереди. Минута между прогонами — это уступка живому человеку,
# а не экономия. Сменить: KLEAL_BATTERY_GAP=0 для сплошной нагрузки.
set -u
GAP="${KLEAL_BATTERY_GAP:-60}"
BASE="${KLEAL_BATTERY_BASE:-http://127.0.0.1:7080}"
cd /opt/kleal/kleal-ms
while true; do
  TS=$(date +%Y%m%d_%H%M%S)
  LOG="/root/kleal-archive/battery/buddy-battery-$TS.log"
  mkdir -p /root/kleal-archive/battery
  echo "[$(date '+%F %T')] прогон -> $LOG"
  # БЕЗ `| tail`: он копит вывод до конца процесса, и живой поток не доходит до журнала — прогон
  # выглядел молчащим все две минуты. `-u` у питона по той же причине: буфер строкой, а не блоком.
  # Каждый круг подсыпаем в пул новых сценариев: набор должен расти и меняться, иначе батарея
  # выучивает сама себя — те же тридцать разговоров ловят только те же тридцать бед.
  timeout 300 python3 tools/scenario_gen.py 36 >/dev/null 2>&1 &
  timeout 7200 python3 -u tools/buddy_battery.py "$BASE" "$LOG" 2>&1
  wait
  # Журналы старше недели не нужны: история живёт в таблице, а разговоры нужны только свежие.
  find /root/kleal-archive/battery -name 'buddy-battery-*.log' -mtime +7 -delete 2>/dev/null
  sleep "$GAP"
done
