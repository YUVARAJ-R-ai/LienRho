#!/usr/bin/env bash
# Start the API detached, capped to 12 cores at low priority so it doesn't
# compete with an editor / dev server on the same laptop.
#
# Usage:  ./run-dev.sh start | stop | status
set -euo pipefail

cd "$(dirname "$0")"
PIDFILE=/tmp/lienrho-api.pid
LOGFILE=/tmp/lienrho-api.log

case "${1:-start}" in
  start)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "already running (pid $(cat "$PIDFILE"))"
      exit 0
    fi
    setsid nohup nice -n 10 taskset -c 0-11 \
      env VIRTUAL_ENV= uv run uvicorn app.main:app --port 8000 \
      >"$LOGFILE" 2>&1 </dev/null &
    echo $! >"$PIDFILE"
    echo "started (pid $!), log: $LOGFILE"
    ;;
  stop)
    if [ -f "$PIDFILE" ]; then
      pkill -P "$(cat "$PIDFILE")" 2>/dev/null || true
      kill "$(cat "$PIDFILE")" 2>/dev/null || true
      rm -f "$PIDFILE"
      echo "stopped"
    else
      echo "not running"
    fi
    ;;
  status)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "running (pid $(cat "$PIDFILE"))"
    else
      echo "not running"
    fi
    ;;
esac
