#!/bin/bash
# БАТАРЕЯ ВЫКЛЮЧЕНА ВЛАДЕЛЬЦЕМ 23.09.2026 (удваивала задержку живых ответов: 3,5 с -> 1,6 с без неё).
# Эталон возвращает её, ТОЛЬКО если она работала до него, иначе любой прогон тихо вернул бы нагрузку.
WAS_ON=0; systemctl is-active --quiet kleal-battery && WAS_ON=1
# ЭТАЛОННЫЙ ПРОГОН, НЕ ЛОМАЯ ЖИВОЙ КРУГ.
#
# ЗАЧЕМ. Эталон требует остановить `kleal-battery` — иначе он делит модель с боевым кругом и мерит
# не то. Но `systemctl stop` посреди круга рвёт его: 17.09.2026 шесть кругов из восьми в истории
# оказались обрезанными (64, 294, 195, 391, 66, 217, 364 сбоя), и в панели это выглядит поломкой
# продукта, хотя виноват замер. Поэтому ждём ГРАНИЦЫ круга: строка в battery-rounds.jsonl
# появляется ровно тогда, когда круг закончился, — в этот момент останавливаться безопасно.
#
# Использование: tools/bench.sh <файл-набора> <куда-журнал> [потоков]
set -u
POOL="${1:-/root/kleal-archive/bench-500.jsonl}"
LOG="${2:-/root/kleal-archive/bench.log}"
WORKERS="${3:-40}"
ROUNDS=/root/kleal-archive/battery-rounds.jsonl
CD=/opt/kleal/kleal-ms

if systemctl is-active --quiet kleal-battery; then
    N0=$(wc -l < "$ROUNDS")
    echo "жду конца круга (сейчас кругов $N0, не больше 8 минут)"
    T=0
    while [ "$T" -lt 480 ]; do
        N=$(wc -l < "$ROUNDS")
        [ "$N" -gt "$N0" ] && break
        sleep 15; T=$((T+15))
    done
    echo "круг закрыт через $T с — останавливаю батарею"
    systemctl stop kleal-battery
    sleep 4
fi

cd "$CD" || exit 1
KLEAL_BATTERY_FIXED="$POOL" KLEAL_BATTERY_WORKERS="$WORKERS" \
    timeout 2400 python3 -u tools/buddy_battery.py http://127.0.0.1:7080 "$LOG"
RC=$?
[ "$WAS_ON" = 1 ] && systemctl start kleal-battery
echo "батарея снова запущена (код эталона $RC)"
