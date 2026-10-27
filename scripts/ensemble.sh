#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ZK_SERVER="$(brew --prefix zookeeper)/bin/zkServer"
export JAVA_HOME="$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home"
export PATH="$JAVA_HOME/bin:$PATH"
export ZOO_LOG_DIR="$ROOT/logs"
mkdir -p "$ROOT/logs" "$ROOT/data/server-1" "$ROOT/data/server-2" "$ROOT/data/server-3"
case "${1:-}" in
  start)
    for id in 1 2 3; do
      printf '%s\n' "$id" > "$ROOT/data/server-$id/myid"
      pidfile="$ROOT/logs/zk-$id.pid"
      if [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
        echo "zk$id already running pid=$(cat "$pidfile")"
        continue
      fi
      "$ZK_SERVER" start-foreground "$ROOT/config/zoo-$id.cfg" > "$ROOT/logs/zk-$id.log" 2>&1 &
      echo $! > "$pidfile"
      echo "zk$id started pid=$(cat "$pidfile") port=$((2180 + id)) myid=$id"
      sleep 0.5
    done
    ;;
  stop)
    for id in 1 2 3; do
      pidfile="$ROOT/logs/zk-$id.pid"
      if [[ -f "$pidfile" ]]; then
        pid="$(cat "$pidfile")"
        if kill -0 "$pid" 2>/dev/null; then
          kill -TERM "$pid"
          echo "zk$id stopped pid=$pid"
        else
          echo "zk$id already stopped"
        fi
        rm -f "$pidfile"
      fi
    done
    ;;
  status)
    python3 "$ROOT/scripts/status.py"
    ;;
  *)
    echo "Usage: $0 start|stop|status" >&2
    exit 2
    ;;
esac
