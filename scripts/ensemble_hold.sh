#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ZK_SERVER="$(brew --prefix zookeeper)/bin/zkServer"
export JAVA_HOME="$(brew --prefix openjdk@17)/libexec/openjdk.jdk/Contents/Home"
export PATH="$JAVA_HOME/bin:$PATH"
export ZOO_LOG_DIR="$ROOT/logs"
mkdir -p "$ROOT/logs" "$ROOT/data/server-1" "$ROOT/data/server-2" "$ROOT/data/server-3"
for id in 1 2 3; do
  printf '%s\n' "$id" > "$ROOT/data/server-$id/myid"
  "$ZK_SERVER" start-foreground "$ROOT/config/zoo-$id.cfg" > "$ROOT/logs/zk-$id.log" 2>&1 &
  echo $! > "$ROOT/logs/zk-$id.pid"
  echo "zk$id started pid=$(cat "$ROOT/logs/zk-$id.pid") port=$((2180 + id)) myid=$id"
done
stop_all() {
  for id in 1 2 3; do
    pidfile="$ROOT/logs/zk-$id.pid"
    if [[ -f "$pidfile" ]]; then
      kill -TERM "$(cat "$pidfile")" 2>/dev/null || true
      rm -f "$pidfile"
    fi
  done
}
trap stop_all EXIT INT TERM
wait
