#!/usr/bin/env bash
# Отправить НАЗВАННЫЕ файлы приложения на под, где крутится Metro.
#
#   ops/sync-to-pod.sh app/group.tsx src/groups.ts     явные файлы
#   ops/sync-to-pod.sh --list groups                   готовый набор (см. ниже)
#   ops/sync-to-pod.sh --deps                          + переставить node_modules и перезапустить
#   ops/sync-to-pod.sh --ops                           обновить сами скрипты (с перезапуском сторожа)
#
# ПОЧЕМУ ТОЛЬКО ПО ИМЕНАМ, А НЕ ВЕСЬ КАТАЛОГ. Раньше скрипт лил `kleal-app` целиком. Пока над
# проектом работал один человек, это было удобно; как только рядом появился второй агент (голосовой
# ввод), это стало механизмом порчи: чей tar приехал последним, того файлы и живут. Проверено
# вживую 2026-08-11 — на поде не оказалось моих `src/home.ts` и `CardStack.tsx` вовсе, а `home.tsx`
# и `api.ts` были чужих версий. Час ушёл на отладку кода, которого на устройстве не было.
#
# Теперь снести чужое можно только назвав чужой файл руками. Список того, что везём, — решение
# автора правки, а не следствие того, что лежит в каталоге.
#
# Источник правды остаётся в репозитории. На поде — рабочая копия: править там нельзя, следующая
# синхронизация того файла затрёт.
set -eu

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
POD_SSH="ssh -o BatchMode=yes -o ConnectTimeout=25 -i $HOME/.ssh/id_ed25519 -p 24309 root@195.26.233.30"
POD_DIR="/root/kleal-app"

# Наборы файлов по темам — чтобы не перечислять руками каждый раз и не промахнуться мимо нового.
list_groups() {
  cat <<'EOF'
src/api.ts
src/groups.ts
src/gplan.ts
src/ginvites.ts
src/messages.ts
src/home.ts
src/components/CardStack.tsx
app/group.tsx
app/gplan.tsx
app/ginvite.tsx
app/results.tsx
app/messages.tsx
app/home.tsx
EOF
}

FILES=()
case "${1:-}" in
  --ops)
    # ops/ обновляется отдельно и с перезапуском: bash дочитывает исполняемый скрипт по ходу, и
    # перезапись expo-tunnel.sh под работающим сторожем убивает его вместе с Metro.
    echo "→ обновляю ops/ и перезапускаю сторож"
    PIDS="$($POD_SSH "ps -eo pid,command | grep -E 'expo-tunnel|expo start --port|cloudflared .*localhost:19000' | grep -v grep | awk '{print \$1}' | tr '\n' ' '")"
    [ -n "$PIDS" ] && $POD_SSH "for p in $PIDS; do kill -9 \$p 2>/dev/null; done; sleep 3"
    COPYFILE_DISABLE=1 tar -czf - -C "$ROOT" ./ops | $POD_SSH "tar -xzf - -C $POD_DIR && chmod +x $POD_DIR/ops/*.sh"
    $POD_SSH "cd $POD_DIR && nohup setsid ./ops/expo-tunnel.sh > /root/expo-pod.log 2>&1 < /dev/null &" || true
    echo "  сторож поднят заново, адрес будет НОВЫЙ"
    exit 0 ;;
  --list)
    [ $# -ge 2 ] || { echo "какой набор? сейчас есть: groups" >&2; exit 1; }
    case "$2" in
      groups) while IFS= read -r l; do FILES+=("$l"); done < <(list_groups) ;;
      *) echo "неизвестный набор: $2" >&2; exit 1 ;;
    esac ;;
  --deps)
    echo "→ переставляю зависимости"
    COPYFILE_DISABLE=1 tar -czf - -C "$ROOT" ./package.json ./package-lock.json | $POD_SSH "tar -xzf - -C $POD_DIR"
    $POD_SSH "cd $POD_DIR && npm ci --no-audit --no-fund 2>&1 | tail -3"
    echo "  зависимости встали; Metro перезапусти через --ops, если понадобится"
    exit 0 ;;
  "")
    echo "нечего везти: назови файлы или --list groups" >&2
    echo "  (каталог целиком больше не синхронизируется — см. шапку)" >&2
    exit 1 ;;
  *) FILES=("$@") ;;
esac

# Проверяем, что все файлы на месте, ДО отправки: половина приехавшего набора хуже, чем ничего.
for f in "${FILES[@]}"; do
  [ -f "$ROOT/$f" ] || { echo "нет такого файла: $f" >&2; exit 1; }
done

echo "→ везу ${#FILES[@]} файл(ов) в $POD_DIR"
# COPYFILE_DISABLE=1 обязателен: без него macOS-tar кладёт рядом «._имя» (AppleDouble), на Linux это
# обычные файлы, и Metro падает, пытаясь собрать «app/._done.tsx».
COPYFILE_DISABLE=1 tar -czf - -C "$ROOT" "${FILES[@]}" | $POD_SSH "tar -xzf - -C $POD_DIR"

# Сверяем sha КАЖДОГО: молчаливо недоехавший файл — это отладка кода, которого на устройстве нет.
BAD=0
for f in "${FILES[@]}"; do
  L=$(shasum -a 256 "$ROOT/$f" | awk '{print $1}')
  R=$($POD_SSH "sha256sum $POD_DIR/$f 2>/dev/null | awk '{print \$1}'")
  if [ "$L" = "$R" ]; then printf '  ok  %s\n' "$f"; else printf '  РАЗОШЛОСЬ  %s\n' "$f"; BAD=1; fi
done
$POD_SSH "find $POD_DIR -name '._*' -not -path '$POD_DIR/node_modules/*' -delete" || true
[ "$BAD" = 0 ] || { echo "часть файлов не доехала — Metro отдаст старое" >&2; exit 1; }

echo
echo "адрес для Expo Go:"
$POD_SSH "cat $POD_DIR/ops/.expo-url" | sed 's|https://|  exp://|'
echo
echo "Правки в app/ и src/ Metro подхватывает сам."
