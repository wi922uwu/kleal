#!/usr/bin/env bash
# Выпустить сертификат и включить HTTPS. Запускать, когда A-запись уже смотрит сюда:
# certbot проверяет владение доменом через порт 80, и до этого момента выпуск обречён.
set -e
D=aiopenware.com
for name in "$D" "www.$D" "api.$D"; do
  ip=$(getent hosts "$name" | awk '{print $1}' | head -1)
  echo "  $name -> ${ip:-не разрешается}"
done
MY=$(curl -s --max-time 10 https://api.ipify.org)
echo "  этот сервер: $MY"
certbot --nginx -d "$D" -d "www.$D" -d "api.$D" \
        --non-interactive --agree-tos -m admin@"$D" --redirect
systemctl reload nginx
echo "--- проверка снаружи ---"
curl -s -o /dev/null -w "  https меню: %{http_code}\n" --max-time 20 "https://$D/menu"
curl -s -o /dev/null -w "  https api:  %{http_code}\n" --max-time 20 "https://$D/api/agent/groups?self=test"
certbot certificates 2>/dev/null | grep -E "Certificate Name|Domains|Expiry" | sed 's/^/  /'
