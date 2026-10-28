#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."

mkdir -p logs
DB_PATH="$(pwd)/logs/rate_limit_state.sqlite3"
PID_FILE="$(pwd)/logs/rate_limiters.pids"

if [[ -e "$PID_FILE" ]]; then
  echo "ERROR: PID file exists: $PID_FILE"
  echo "Inspect it before starting another instance."
  exit 1
fi

for port in 7001 7002 7003 7004; do
  if ss -ltn 2>/dev/null | grep -qE "[:.]${port}[[:space:]]"; then
    echo "ERROR: port $port is already listening; refusing to start."
    exit 1
  fi
done

declare -a pids=()
cleanup() {
  local pid
  for pid in "${pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  rm -f "$PID_FILE"
}

on_startup_error() {
  local exit_code=$?
  trap - ERR
  cleanup
  exit "$exit_code"
}

trap on_startup_error ERR

start_one() {
  local port="$1" upstream_port="$2"
  UPSTREAM_URL="http://127.0.0.1:${upstream_port}" \
  LISTEN_PORT="$port" \
  RATE_LIMIT_MAX="${RATE_LIMIT_MAX:-20}" \
  RATE_LIMIT_WINDOW_SECONDS="${RATE_LIMIT_WINDOW_SECONDS:-5}" \
  RATE_LIMIT_DB="$DB_PATH" \
    nohup python scripts/rate_limiting/mock_rate_limiter.py \
      >"logs/rate_limiter_${port}.log" 2>&1 &
  pids+=("$!")
}

start_one 7001 5001
start_one 7002 5002
start_one 7003 5003
start_one 7004 5004
printf '%s\n' "${pids[@]}" > "$PID_FILE"

sleep 2
for port in 7001 7002 7003 7004; do
  if ! curl --silent --show-error --fail \
      "http://127.0.0.1:${port}/health" >/dev/null; then
    echo "ERROR: listener $port failed health check. Logs:"
    for log in logs/rate_limiter_*.log; do
      echo "=== $log ==="
      tail -30 "$log"
    done
    trap - ERR
    cleanup
    exit 1
  fi
done

echo "All four temporary mock listeners are healthy."
for port in 7001 7002 7003 7004; do
  curl --silent "http://127.0.0.1:${port}/health"
  echo
done
echo "Shared rate-limit database: $DB_PATH"
