#!/usr/bin/env bash
# Дев-сервер Expo с публичным адресом — и сторож, который поднимает его заново, когда адрес умрёт.
#
# ЗАЧЕМ. Бесплатный анонимный туннель trycloudflare живёт несколько часов, после чего Cloudflare
# удаляет его у себя. Процесс при этом ОСТАЁТСЯ ЖИВ и бесконечно стучится в имя, которого больше
# нет («Unauthorized: Tunnel not found»), — снаружи это выглядит как «Could not connect to
# development server» на телефоне, а в `ps` всё в порядке. За сутки это случилось трижды.
#
# Скрипт закрывает ровно эту дыру: он проверяет адрес СНАРУЖИ, а не по процессу, и при смерти
# поднимает и туннель, и expo заново — второе обязательно, потому что EXPO_PACKAGER_PROXY_URL
# читается один раз на старте и старый адрес остаётся зашит в манифест.
#
#   ops/expo-tunnel.sh            запустить (держит терминал; сторож работает, пока он жив)
#   ops/expo-tunnel.sh --once     поднять и выйти, без сторожа
#   cat ops/.expo-url             текущий адрес, всегда актуальный
#
# Чего скрипт НЕ делает: адрес всё равно новый после каждой смерти. Постоянное имя даёт только
# именованный туннель Cloudflare, а он требует одноразового `cloudflared tunnel login` в браузере
# владельца аккаунта — сделать это за него нельзя.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${EXPO_PORT:-8081}"
CF_LOG="$ROOT/ops/.cloudflared.log"
EXPO_LOG="$ROOT/ops/.expo.log"
URL_FILE="$ROOT/ops/.expo-url"
EVERY="${WATCH_EVERY:-60}"          # как часто щупать адрес снаружи, секунд

log() { printf '%s  %s\n' "$(date +%H:%M:%S)" "$*"; }

stop_all() {
  pkill -f "cloudflared tunnel --protocol http2 --url http://localhost:$PORT" 2>/dev/null
  # Убиваем ИМЕННО node-процесс expo, а не обёртку npm: обёртка умирает, дочерний сервер остаётся
  # держать порт, и следующий запуск падает на «port already in use».
  pkill -f "expo start --port $PORT" 2>/dev/null
  sleep 2
}

start_all() {
  stop_all
  : > "$CF_LOG"
  nohup cloudflared tunnel --protocol http2 --url "http://localhost:$PORT" > "$CF_LOG" 2>&1 &
  # Ждём адрес, а не «сколько-нибудь секунд»: на медленной сети 15 секунд не хватает, на быстрой
  # это лишнее ожидание.
  local url="" i
  for i in $(seq 1 40); do
    url="$(grep -ho 'https://[a-z0-9-]*\.trycloudflare\.com' "$CF_LOG" | head -1)"
    [ -n "$url" ] && break
    sleep 1
  done
  if [ -z "$url" ]; then log "cloudflared не отдал адрес — смотри $CF_LOG"; return 1; fi

  printf '%s\n' "$url" > "$URL_FILE"
  ( cd "$ROOT" && EXPO_PACKAGER_PROXY_URL="$url" nohup npx expo start --port "$PORT" > "$EXPO_LOG" 2>&1 & )

  # Готовность проверяем СНАРУЖИ, через сам туннель: локальный порт отвечает и тогда, когда
  # телефон уже ничего не видит.
  for i in $(seq 1 40); do
    if curl -s -m 5 -o /dev/null -H "expo-platform: ios" "$url/"; then
      log "поднят: ${url/https:\/\//exp://}"
      return 0
    fi
    sleep 2
  done
  log "адрес есть, но манифест снаружи не отвечает — смотри $EXPO_LOG"
  return 1
}

alive() {
  local url; url="$(cat "$URL_FILE" 2>/dev/null)"
  [ -n "$url" ] || return 1
  curl -s -m 8 -o /dev/null -H "expo-platform: ios" "$url/"
}

# Первая попытка может не удаться — и это НЕ повод выходить: trycloudflare иногда отдаёт имя,
# которое не резолвится публично (проверено: cloudflared пишет «Registered tunnel connection», а
# хоста нет ни у curl, ни у телефона). Лечится сменой имени, то есть следующим кругом сторожа.
start_all || log "первая попытка неудачна — сторож сменит имя на следующем круге"
if [ "${1:-}" = "--once" ]; then alive || exit 1; exit 0; fi

log "сторож включён: проверка каждые ${EVERY}с. Ctrl-C чтобы выйти."
trap 'log "выхожу"; stop_all; exit 0' INT TERM
while sleep "$EVERY"; do
  # Две неудачи подряд, а не одна: разовый обрыв сети — не смерть туннеля, и перезапускать из-за
  # него значит менять адрес на ровном месте.
  if ! alive && ! alive; then
    log "адрес не отвечает — поднимаю заново"
    start_all || log "не получилось, попробую на следующем круге"
  fi
done
