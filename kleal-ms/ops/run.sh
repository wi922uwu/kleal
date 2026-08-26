#!/usr/bin/env bash
# Start Kleal services. Replaces the seven identical /root/start_<svc>.sh scripts that lived only
# on the pod — the run recipe was operational knowledge with no copy in the repo, so a rebuilt box
# could not be brought up from a checkout alone.
#
#   ops/run.sh <service>      run one in the FOREGROUND (what a start script does)
#   ops/run.sh start <svc>    start ONE detached, log in ops/logs/ — use this to restart a single
#                             service after an edit; the bare form above dies with its caller
#   ops/run.sh all            start every service detached, logs in ops/logs/
#   ops/run.sh restart <svc>  stop then start one, detached
#   ops/run.sh stop [svc]     stop one, or all
#   ops/run.sh status         what is listening, and on which port
#   ops/run.sh tunnel         print the public address; `tunnel restart` gets a NEW one
#
# Ports come from shared/config.py, so this script has no port table of its own to drift.
# Services are started with cwd = <kleal-ms> because each one resolves `shared/` relative to
# its own file but writes its store relative to the project root.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGS="$ROOT/ops/logs"
PY="${PYTHON:-python3}"

# Dependency order: llm first (everyone reaches models through it), gateway last (it is the public
# door and should not be open before what it proxies to is up).
ALL="llm filtration matching buddy onboarding profile admin gateway"

# §15 group formation. Off by default in the spec (post-pilot); set KLEAL_GROUPS=0 to switch the
# whole feature back off in one place — matching then still ranks people for a group request, it
# just does not assemble anyone.
export KLEAL_GROUPS="${KLEAL_GROUPS:-1}"

port_of() {
  "$PY" - "$1" <<'EOF'
import sys, os
sys.path.insert(0, os.path.join(os.environ["KLEAL_ROOT"], "shared"))
import config
print(config.PORTS[sys.argv[1]])
EOF
}

usage() { sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

start_one() {
  local svc="$1" bg="$2"
  local app="$ROOT/services/$svc/app.py"
  [ -f "$app" ] || { echo "no such service: $svc" >&2; return 1; }
  if [ "$bg" = "bg" ]; then
    mkdir -p "$LOGS"
    # setsid + </dev/null: without them the process dies when the SSH session closes, and it dies
    # leaving an EMPTY log, which reads like a crash that never happened. macOS has no setsid, so
    # detach with nohup alone there — the pod (Linux) is where the SSH-close problem actually bites.
    local SETSID=""
    command -v setsid >/dev/null 2>&1 && SETSID="setsid"
    ( cd "$ROOT" && nohup $SETSID "$PY" -u "services/$svc/app.py" \
        > "$LOGS/$svc.log" 2>&1 < /dev/null & )
    echo "started $svc  (log: ops/logs/$svc.log)"
  else
    cd "$ROOT" && exec "$PY" -u "services/$svc/app.py"
  fi
}

stop_one() {
  local svc="$1"
  local port
  port="$(KLEAL_ROOT="$ROOT" port_of "$svc" 2>/dev/null)" || { echo "unknown service: $svc" >&2; return 1; }
  # Kill the process holding the LISTENING socket, not everything matching the name: a deploy that
  # pkill'd by pattern killed the bash wrapper and left the python child serving the old bytes.
  local pid
  pid="$(ss -lntpH "sport = :$port" 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)"
  if [ -z "${pid:-}" ]; then
    pid="$(lsof -ti tcp:"$port" -sTCP:LISTEN 2>/dev/null | head -1)"
  fi
  if [ -n "${pid:-}" ]; then
    kill -9 "$pid" 2>/dev/null && echo "stopped $svc (pid $pid, port $port)"
  else
    echo "$svc not running (port $port free)"
  fi
}

case "${1:-}" in
  ""|-h|--help|help) usage ;;
  start)
    [ $# -ge 2 ] || { echo "usage: ops/run.sh start <service>" >&2; exit 1; }
    start_one "$2" bg
    ;;
  restart)
    [ $# -ge 2 ] || { echo "usage: ops/run.sh restart <service>" >&2; exit 1; }
    stop_one "$2"; sleep 1; start_one "$2" bg
    ;;
  all)
    for s in $ALL; do start_one "$s" bg; sleep 0.4; done
    echo; echo "waiting for listeners…"; sleep 3
    exec "$0" status
    ;;
  stop)
    if [ $# -ge 2 ]; then stop_one "$2"; else for s in $ALL; do stop_one "$s"; done; fi
    ;;
  status)
    printf "%-12s %-6s %s\n" SERVICE PORT STATE
    for s in $ALL; do
      p="$(KLEAL_ROOT="$ROOT" port_of "$s")"
      if (ss -lntH "sport = :$p" 2>/dev/null | grep -q .) || lsof -ti tcp:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
        state="listening"
      else
        state="-"
      fi
      printf "%-12s %-6s %s\n" "$s" "$p" "$state"
    done
    ;;
  tunnel)
    # The public address of the gateway. The tunnel is ephemeral: the name lives as long as the
    # process, and a dead one NEVER comes back by itself — it needs a new process and a new address
    # written into kleal-app/src/api.ts. Hence `restart` is a separate word: the bare form only
    # reports, so checking the address can never cost you the one you already had.
    CF="${CLOUDFLARED:-/root/cloudflared-linux-amd64}"
    p="$(KLEAL_ROOT="$ROOT" port_of gateway)"
    LOG="${CF_LOG:-/root/cf$p.log}"
    match="[t]unnel .*--url http://localhost:$p"
    if [ "${2:-}" = "restart" ]; then
      [ -x "$CF" ] || { echo "no cloudflared at $CF" >&2; exit 1; }
      # NOT `pkill -f` on a string containing the port. Typed as an ssh one-liner, that pattern also
      # matches the command line of the very shell running it, so pkill kills itself before reaching
      # the start — which reads as a flaky connection, not as a bug. Living in a file is what makes
      # this safe: the shell's argv is just `bash ops/run.sh tunnel restart`.
      ps ax -o pid=,args= | grep "$match" | awk '{print $1}' | while read -r pid; do kill "$pid"; done
      sleep 2
      : > "$LOG"
      # --protocol http2 on purpose: the default is QUIC over UDP 7844, and where UDP is filtered the
      # tunnel comes up and falls apart seconds later.
      SETSID=""; command -v setsid >/dev/null 2>&1 && SETSID="setsid"
      ( cd /root && nohup $SETSID "$CF" tunnel --protocol http2 --url "http://localhost:$p" \
          >> "$LOG" 2>&1 < /dev/null & )
      sleep 20
    fi
    url="$(grep -ho 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" | head -1)"
    [ -n "$url" ] || { echo "no address in $LOG — read the log" >&2; exit 1; }
    echo "$url"
    echo "processes: $(ps ax -o args= | grep -c "$match")   (more than 1 means leftovers from retries)"
    echo "put it in kleal-app/src/api.ts → DEFAULT_BASE"
    ;;
  *) start_one "$1" fg ;;
esac
