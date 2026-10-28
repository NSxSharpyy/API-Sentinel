#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"

cd "$ROOT_DIR"

VUS="${1:-${VUS:-10}}"
DURATION="${2:-${DURATION:-15s}}"
DB_FILE="${DB_PATH:-$ROOT_DIR/data/shop.db}"

mkdir -p "$RESULTS_DIR"

STAMP="$(date +%Y%m%d_%H%M%S)"
RESULT_FILE="$RESULTS_DIR/authenticated_${STAMP}.json"
LOG_FILE="$RESULTS_DIR/authenticated_console_${STAMP}.log"

echo "=========================================="
echo " API-Sentinel Authenticated API Benchmark"
echo "=========================================="
echo "Virtual users: $VUS"
echo "Duration: $DURATION"
echo "Database: $DB_FILE"
echo "Results: $RESULT_FILE"
echo "eBPF sidecar: must be absent"
echo "Acceptance: authenticated API P95 < 50 ms"
echo "Login: measured separately as bootstrap"
echo

command -v k6 >/dev/null 2>&1 || {
    echo "ERROR: k6 is not installed or not in PATH." >&2
    exit 1
}
command -v python >/dev/null 2>&1 || {
    echo "ERROR: python is not installed or not in PATH." >&2
    exit 1
}
command -v curl >/dev/null 2>&1 || {
    echo "ERROR: curl is not installed or not in PATH." >&2
    exit 1
}

[[ "$VUS" =~ ^[1-9][0-9]*$ ]] || {
    echo "ERROR: VUS must be a positive integer." >&2
    exit 1
}
[[ "$DURATION" =~ ^[1-9][0-9]*(s|m|h)$ ]] || {
    echo "ERROR: DURATION must look like 15s, 2m, or 1h." >&2
    exit 1
}
[[ -f "$DB_FILE" ]] || {
    echo "ERROR: SQLite database not found: $DB_FILE" >&2
    exit 1
}

echo "Checking service health..."
for entry in "5001:auth" "5002:user" "5003:order" "5004:billing"; do
    port="${entry%%:*}"
    name="${entry##*:}"

    if ! curl --silent --show-error --fail \
        --max-time 3 "http://127.0.0.1:${port}/health" >/dev/null; then
        echo "ERROR: $name service is not healthy on port $port." >&2
        exit 1
    fi
    echo "[OK] $name"
done

echo
echo "Exporting seeded customer usernames..."
USERNAMES="$(DB_PATH="$DB_FILE" \
    python "$SCRIPT_DIR/export_usernames.py")"

USERNAME_COUNT="$(printf '%s' "$USERNAMES" | awk -F',' '{print NF}')"
[[ -n "$USERNAMES" && "$USERNAME_COUNT" -ge "$VUS" ]] || {
    echo "ERROR: Need at least as many seeded usernames as VUs." >&2
    echo "Exported: ${USERNAME_COUNT:-0}; VUs: $VUS" >&2
    exit 1
}
echo "Exported usernames: $USERNAME_COUNT"

echo
echo "Running authenticated API workload..."
set +e
AUTH_URL="${AUTH_URL:-http://127.0.0.1:5001}" \
USER_URL="${USER_URL:-http://127.0.0.1:5002}" \
ORDER_URL="${ORDER_URL:-http://127.0.0.1:5003}" \
BILLING_URL="${BILLING_URL:-http://127.0.0.1:5004}" \
DEMO_PASSWORD="${DEMO_PASSWORD:-Password123!}" \
USERNAMES="$USERNAMES" \
VUS="$VUS" \
DURATION="$DURATION" \
k6 run --summary-export "$RESULT_FILE" \
    "$SCRIPT_DIR/authenticated.js" 2>&1 | tee "$LOG_FILE"
K6_STATUS=${PIPESTATUS[0]}
set -e

echo
echo "=========================================="
echo " Authenticated Benchmark Result"
echo "=========================================="
echo "k6 exit status: $K6_STATUS"
echo "JSON summary:   $RESULT_FILE"
echo "Console log:    $LOG_FILE"
echo
echo "Review the k6 output for:"
echo "  - http_req_duration{workload:authenticated}: p(95)<50"
echo "  - http_req_failed: rate<0.01"
echo "  - benchmark_errors: rate<0.01"
echo "  - checks: rate>0.99"
echo "  - login_duration_ms: reported separately"
echo

if [[ "$K6_STATUS" -ne 0 ]]; then
    echo "Benchmark FAILED: k6 reported a threshold or execution failure." >&2
    exit "$K6_STATUS"
fi

echo "Benchmark PASSED: all configured k6 thresholds passed."
