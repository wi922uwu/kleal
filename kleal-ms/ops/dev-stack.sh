#!/usr/bin/env bash
# Изолированный стенд рядом с продом — второй полный экземпляр Kleal на том же сервере.
#
#   ops/dev-stack.sh create           поднять стенд: копия кода, свои данные, свои порты
#   ops/dev-stack.sh sync             обновить в стенде ТОЛЬКО код из прод-дерева, данные не трогать
#   ops/dev-stack.sh start|stop|restart [сервис]
#   ops/dev-stack.sh status           кто слушает и на чём
#   ops/dev-stack.sh tunnel           публичный адрес стенда (cloudflare, эфемерный)
#   ops/dev-stack.sh seed             перезалить пул людей из прода, стор обнулить
#   ops/dev-stack.sh nuke             снести стенд целиком (спросит подтверждение)
#
# ПОЧЕМУ НЕ DOCKER. Просили отдельный контейнер — на этом поде это невозможно, и проверено, а не
# предположено: под сам является Docker-контейнером (`/.dockerenv`, cgroup `/docker/4a3a3559...`),
# в его наборе прав нет `cap_sys_admin`, поэтому docker-in-docker не стартует; rootless-обходы тоже
# отпадают — `unshare --user` отвечает «Operation not permitted», а podman/lxc/nspawn не установлены.
#
# Что при этом реально давал бы контейнер и что даёт этот скрипт:
#
#   изоляция данных        ДА  — свои users.json, kleal_store.json, accounts.json, photos/
#   изоляция процессов     ДА  — свои порты, свои PID, свои логи
#   независимый деплой     ДА  — KLEAL_SSH/цель указывают на дерево стенда
#   сломать, не задев род  ДА  — прод-дерево этим скриптом не пишется НИКОГДА
#   изоляция зависимостей  не нужна — сервисы на голой стандартной библиотеке, pip-пакетов нет
#   изоляция ОС и ядра     НЕТ — этого без контейнера не получить
#   лимиты CPU/памяти      НЕТ — то же самое
#
# То есть теряется только то, чем этот проект не пользуется. Если однажды понадобится настоящая
# изоляция ОС — это отдельный под, а не докер внутри этого.
set -u

# Абсолютный путь к самому себе: скрипт вызывает себя, а вызов может прийти из любой cwd.
SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"

SRC="${KLEAL_SRC:-/root/kleal-ms}"          # прод-дерево, откуда берём код (только чтение)
DEV="${KLEAL_DEV:-/root/kleal-dev}"         # стенд
OFFSET="${KLEAL_PORT_OFFSET:-100}"          # 7071 -> 7171, 7080 -> 7180

# Данные стенда живут отдельно. Список ровно тот, что сервисы пишут — если появится новый писатель,
# добавить сюда, иначе `sync` затрёт данные стенда прод-копией.
DATA_PATHS="users.json accounts.json loadtest_index.json services/matching/kleal_store.json photos ops/logs backups"

env_block() {
  cat <<EOF
export LLM_PORT=$((7071 + OFFSET))
export ONBOARDING_PORT=$((7072 + OFFSET))
export PROFILE_PORT=$((7073 + OFFSET))
export MATCHING_PORT=$((7074 + OFFSET))
export BUDDY_PORT=$((7075 + OFFSET))
export FILTER_PORT=$((7076 + OFFSET))
export ADMIN_PORT=$((7077 + OFFSET))
export HUB_PORT=$((7080 + OFFSET))
export KLEAL_GROUPS=1
export KLEAL_ENV=dev
EOF
}

require_dev() {
  [ -d "$DEV" ] || { echo "стенда нет — сначала: ops/dev-stack.sh create"; exit 1; }
}

# Ни одна ветка не пишет в \$SRC. Единственное обращение к нему — чтение при create/sync/seed.
guard_src() {
  case "$(cd "$1" 2>/dev/null && pwd)" in
    "$SRC"|"$SRC"/*) echo "ОТКАЗ: попытка записи в прод-дерево $SRC"; exit 2 ;;
  esac
}

case "${1:-}" in
create)
  [ -d "$SRC" ] || { echo "нет исходного дерева: $SRC"; exit 1; }
  [ -e "$DEV" ] && { echo "стенд уже существует: $DEV (обновить код — sync, снести — nuke)"; exit 1; }
  guard_src "$(dirname "$DEV")"
  mkdir -p "$DEV"
  echo "копирую код $SRC -> $DEV (без данных, без .git)"
  ( cd "$SRC" && tar cf - \
      --exclude=.git --exclude=backups --exclude=photos --exclude=ops/logs \
      --exclude=users.json --exclude=accounts.json --exclude=loadtest_index.json \
      --exclude=services/matching/kleal_store.json --exclude='*.bak_*' --exclude=__pycache__ \
      . ) | ( cd "$DEV" && tar xf - )
  mkdir -p "$DEV/photos" "$DEV/ops/logs" "$DEV/backups"
  env_block > "$DEV/ops/dev.env"
  echo '{}' > "$DEV/services/matching/kleal_store.json"
  # через bash, а не напрямую: файл заливается деплоем без бита на исполнение
  bash "$SELF" seed
  echo
  echo "стенд поднят: $DEV"
  echo "порты: llm $((7071+OFFSET)) · онбординг $((7072+OFFSET)) · профиль $((7073+OFFSET)) · матчинг $((7074+OFFSET))"
  echo "       бадди $((7075+OFFSET)) · фильтрация $((7076+OFFSET)) · админка $((7077+OFFSET)) · шлюз $((7080+OFFSET))"
  echo "запустить: ops/dev-stack.sh start"
  ;;

sync)
  require_dev
  echo "обновляю ТОЛЬКО код (данные стенда не трогаю)"
  ( cd "$SRC" && tar cf - \
      --exclude=.git --exclude=backups --exclude=photos --exclude=ops/logs \
      --exclude=users.json --exclude=accounts.json --exclude=loadtest_index.json \
      --exclude=services/matching/kleal_store.json --exclude='*.bak_*' --exclude=__pycache__ \
      . ) | ( cd "$DEV" && tar xf - )
  env_block > "$DEV/ops/dev.env"      # порты могли поменяться вместе со скриптом
  echo "код обновлён. рестарт: ops/dev-stack.sh restart"
  ;;

seed)
  require_dev
  if [ -f "$SRC/users.json" ]; then
    cp "$SRC/users.json" "$DEV/users.json"
    echo "пул людей скопирован: $(python3 -c "
import json;d=json.load(open('$DEV/users.json'));print(len(d.get('users',d) if isinstance(d,dict) else d))" 2>/dev/null || echo '?') профилей"
  fi
  [ -f "$SRC/accounts.json" ] && cp "$SRC/accounts.json" "$DEV/accounts.json"
  echo '{}' > "$DEV/services/matching/kleal_store.json"
  echo "стор стенда обнулён — приглашения, планы и блокировки прода сюда не переезжают"
  ;;

start|stop|restart|status)
  require_dev
  # shellcheck disable=SC1090
  . "$DEV/ops/dev.env"
  export KLEAL_ROOT="$DEV"
  cd "$DEV" || exit 1
  # run.sh различает «all» (всё скопом) и «start <сервис>» (один); «start all» он не понимает.
  svc="${2:-}"
  case "$1" in
    status)  bash ops/run.sh status ;;
    stop)    if [ -n "$svc" ]; then bash ops/run.sh stop "$svc"; else bash ops/run.sh stop; fi ;;
    start)   if [ -n "$svc" ]; then bash ops/run.sh start "$svc"; else bash ops/run.sh all; fi ;;
    restart) if [ -n "$svc" ]; then bash ops/run.sh restart "$svc"
             else bash ops/run.sh stop; sleep 1; bash ops/run.sh all; fi ;;
  esac
  ;;

tunnel)
  require_dev
  # shellcheck disable=SC1090
  . "$DEV/ops/dev.env"
  CF="${CLOUDFLARED:-/root/cloudflared-linux-amd64}"
  LOG="/root/cf${HUB_PORT}_dev.log"
  [ -x "$CF" ] || { echo "нет cloudflared: $CF"; exit 1; }
  # НЕ через `pgrep -f` по строке с портом: шаблон совпадает с собственной командой оболочки,
  # и проверка радостно находит саму себя, отвечая «уже поднят» на пустом месте.
  if ps ax -o args= | grep -v grep | grep -q "tunnel --url http://localhost:$HUB_PORT"; then
    echo "туннель уже поднят:"
  else
    nohup "$CF" tunnel --url "http://localhost:$HUB_PORT" > "$LOG" 2>&1 &
    sleep 15
  fi
  grep -ho 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" | head -1
  echo "(адрес эфемерный: умирает вместе с процессом, после рестарта поднимать заново)"
  ;;

nuke)
  require_dev
  guard_src "$DEV"
  echo "снесёт стенд ЦЕЛИКОМ, вместе с его данными: $DEV"
  printf "напиши YES для подтверждения: "
  read -r a
  [ "$a" = "YES" ] || { echo "отменено"; exit 1; }
  bash "$SELF" stop >/dev/null 2>&1
  rm -rf "$DEV"
  echo "снесено"
  ;;

*)
  sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//'
  exit 1 ;;
esac
