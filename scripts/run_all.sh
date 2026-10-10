#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

pids=()
trap 'kill "${pids[@]}" 2>/dev/null || true' EXIT INT TERM

for entry in auth:5001 user:5002 order:5003 billing:5004; do
  name="${entry%%:*}"; port="${entry##*:}"
  PORT="$port" python "services/${name}_service/app.py" &
  pids+=($!)
  echo "started ${name}_service on port ${port}"
done
wait
