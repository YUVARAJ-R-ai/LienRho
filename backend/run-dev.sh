#!/usr/bin/env bash
# Start the API detached, capped to 12 cores at low priority so it doesn't
# compete with an editor / dev server on the same laptop.
#
# setsid and taskset are Linux-only. On macOS they are simply absent, and the
# script used to report "started (pid N)" for a process that had already died
# on a command-not-found — leaving a stale pidfile and a port with nothing on
# it. Both are now optional: the niceness still applies everywhere, and CPU
# pinning is skipped where the OS has no equivalent.
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
    # Built as one array. Expanding a possibly-empty array under `set -u` is
    # an error on the bash 3.2 macOS still ships, and `command -v X && ...`
    # would trip `set -e` when X is absent — which is the normal case here.
    cmd=()
    if command -v setsid >/dev/null 2>&1; then cmd+=(setsid); fi
    cmd+=(nohup nice -n 10)
    if command -v taskset >/dev/null 2>&1; then cmd+=(taskset -c 0-11); fi
    cmd+=(env VIRTUAL_ENV= uv run uvicorn app.main:app --port 8000)

    "${cmd[@]}" >"$LOGFILE" 2>&1 </dev/null &
    pid=$!
    echo "$pid" >"$PIDFILE"

    # Confirm it is actually listening rather than trusting the fork. A crash
    # on startup (a bad DATABASE_URL, a missing signing key) otherwise looks
    # identical to a clean start.
    for _ in $(seq 1 40); do
      if curl -sf -o /dev/null http://localhost:8000/health; then
        echo "started (pid $pid), log: $LOGFILE"
        exit 0
      fi
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.5
    done

    rm -f "$PIDFILE"
    echo "failed to start — last lines of $LOGFILE:" >&2
    tail -20 "$LOGFILE" >&2
    exit 1
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
