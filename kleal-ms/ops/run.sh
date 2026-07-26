#!/usr/bin/env bash
# Start Kleal services. Replaces the seven identical /root/start_<svc>.sh scripts that lived only
# on the pod — the run recipe was operational knowledge with no copy in the repo, so a rebuilt box
# could not be brought up from a checkout alone.
#
#   ops/run.sh <service>      run one in the FOREGROUND (what a start script does)
#   ops/run.sh all            start every service detached, logs in ops/logs/
#   ops/run.sh stop [svc]     stop one, or all
#   ops/run.sh status         what is listening, and on which port
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

port_of() {
  "$PY" - "$1" <<'EOF'
import sys, os
sys.path.insert(0, os.path.join(os.environ["KLEAL_ROOT"], "shared"))
import config
print(config.PORTS[sys.argv[1]])
EOF
}

usage() { sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

start_one() {
  local svc="$1" bg="$2"
  local app="$ROOT/services/$svc/app.py"
  [ -f "$app" ] || { echo "no such service: $svc" >&2; return 1; }
  if [ "$bg" = "bg" ]; then
    mkdir -p "$LOGS"
    # setsid + </dev/null: without them the process dies when the SSH session closes, and it dies
    # leaving an EMPTY log, which reads like a crash that never happened.
    ( cd "$ROOT" && nohup setsid "$PY" -u "services/$svc/app.py" \
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
  *) start_one "$1" fg ;;
esac
