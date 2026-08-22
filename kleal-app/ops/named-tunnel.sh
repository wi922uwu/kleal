#!/usr/bin/env bash
# ПОСТОЯННЫЙ адрес вместо туннеля, который живёт несколько часов.
#
#   ops/named-tunnel.sh <домен>        например: ops/named-tunnel.sh kleal.app
#
# Что получится на выходе (два имени, один туннель):
#   https://metro.<домен>  → Metro на 19000   — его сканирует Expo Go: exp://metro.<домен>
#   https://api.<домен>    → шлюз на 7080     — его пишем в EXPO_PUBLIC_API
#
# ПОЧЕМУ CNAME, А НЕ A-ЗАПИСЬ. A-запись указывает на IP, а у пода нет своего публичного IP:
# 195.26.233.30 — это адрес ХОСТА RunPod, общего для многих подов, и наружу от нашего пода
# проброшен ровно один порт, 22 → 24309. Проверено запросами: на :7080 по этому IP ответа нет
# вовсе, на :19000 отвечает чужой сервис. Домен, направленный туда A-записью, попал бы на машину,
# которая нам не принадлежит.
#
# Именованный туннель обходит это тем, что соединение идёт ИЗНУТРИ НАРУЖУ: cloudflared сам
# подключается к Cloudflare, входящие порты не нужны совсем. DNS-запись при этом — CNAME на
# <UUID>.cfargotunnel.com, и `tunnel route dns` создаёт её сам.
#
# ЧТО НУЖНО СДЕЛАТЬ РУКАМИ ОДИН РАЗ (за тебя нельзя — нужен браузер и твой аккаунт):
#   1. домен должен обслуживаться Cloudflare (NS-серверы домена указывают на Cloudflare);
#   2. на поде:  /root/cloudflared-linux-amd64 tunnel login
#      команда напечатает ссылку — открой её у себя, выбери зону, подтверди.
#      После этого появится /root/.cloudflared/cert.pem, и дальше всё делает этот скрипт.
set -eu

DOMAIN="${1:-}"
[ -n "$DOMAIN" ] || { echo "укажи домен: ops/named-tunnel.sh kleal.app" >&2; exit 1; }

NAME="${TUNNEL_NAME:-kleal}"
METRO_PORT="${METRO_PORT:-19000}"
API_PORT="${API_PORT:-7080}"
CFD="$(command -v cloudflared 2>/dev/null || true)"
[ -n "$CFD" ] || for c in /root/cloudflared-linux-amd64 /usr/local/bin/cloudflared; do
  [ -x "$c" ] && CFD="$c" && break
done
[ -n "$CFD" ] || { echo "cloudflared не найден" >&2; exit 1; }

CFG_DIR="${CFD_HOME:-/root/.cloudflared}"
[ -f "$CFG_DIR/cert.pem" ] || {
  echo "нет $CFG_DIR/cert.pem — сначала: $CFD tunnel login" >&2
  echo "команда напечатает ссылку; открой её в браузере и выбери зону $DOMAIN" >&2
  exit 1
}

# Туннель заводим ОДИН раз. Повторный create падает с «already exists», и это не ошибка —
# значит всё уже сделано, и надо просто взять его UUID.
if ! "$CFD" tunnel list | awk '{print $2}' | grep -qx "$NAME"; then
  echo "→ создаю туннель $NAME"
  "$CFD" tunnel create "$NAME"
fi
UUID="$("$CFD" tunnel list | awk -v n="$NAME" '$2==n {print $1}' | head -1)"
[ -n "$UUID" ] || { echo "не нашёл UUID туннеля $NAME" >&2; exit 1; }
echo "  UUID: $UUID"

# Правила маршрутизации. Последняя строка обязательна: без неё cloudflared не стартует, а запрос
# на неизвестное имя должен получать честный 404, а не попадать в первый попавшийся сервис.
cat > "$CFG_DIR/config.yml" <<YAML
tunnel: $UUID
credentials-file: $CFG_DIR/$UUID.json

ingress:
  - hostname: metro.$DOMAIN
    service: http://localhost:$METRO_PORT
  - hostname: api.$DOMAIN
    service: http://localhost:$API_PORT
  - service: http_status:404
YAML
echo "→ конфиг записан: $CFG_DIR/config.yml"

# Создаёт в зоне CNAME metro.<домен> → <UUID>.cfargotunnel.com, проксированную (оранжевое облако).
# Руками это делать не нужно; если всё же захочется — параметры записи ровно такие.
for h in "metro.$DOMAIN" "api.$DOMAIN"; do
  echo "→ маршрут DNS: $h"
  "$CFD" tunnel route dns "$NAME" "$h" || echo "  (запись уже есть — это нормально)"
done

echo
echo "готово. запуск:"
echo "  nohup setsid $CFD tunnel run $NAME > /root/named-tunnel.log 2>&1 < /dev/null &"
echo
echo "после запуска Metro поднимать с ПОСТОЯННЫМ адресом:"
echo "  EXPO_PACKAGER_PROXY_URL=https://metro.$DOMAIN npx expo start --port $METRO_PORT"
echo "приложению в src/api.ts или переменной:"
echo "  EXPO_PUBLIC_API=https://api.$DOMAIN"
echo
echo "телефон: exp://metro.$DOMAIN"
echo
echo "ЧЕГО ЖДАТЬ. Бесплатный тариф Cloudflare рвёт проксированный запрос на 100 секундах (ошибка"
echo "524). Бандл 8,9 МБ уезжает за 2 с — ему всё равно; а вот ответ 70B под нагрузкой в этот срок"
echo "укладывается не всегда, и у /api/buddy это будет выглядеть как обрыв. Тот же предел был и у"
echo "временных туннелей, так что хуже не станет — но знать стоит."
