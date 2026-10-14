#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"

cd "$ROOT_DIR"

BASE_URL="${API_BASE_URL:-http://127.0.0.1}"
VUS="${1:-${VUS:-10}}"
DURATION="${2:-${DURATION:-30s}}"
DB_FILE="${DB_PATH:-$ROOT_DIR/data/shop.db}"

mkdir -p "$RESULTS_DIR"

STAMP="$(date +%Y%m%d_%H%M%S)"
RESULT_FILE="$RESULTS_DIR/baseline_${STAMP}.json"
LOG_FILE="$RESULTS_DIR/console_${STAMP}.log"

echo "=========================================="
echo " API-Sentinel Baseline Benchmark"
echo "=========================================="
echo "Virtual users: $VUS"
echo "Duration: $DURATION"
echo "Database: $DB_FILE"
echo "Results: $RESULT_FILE"
echo "eBPF sidecar: must be absent"
echo

command -v k6 >/dev/null 2>&1 || {
    echo "ERROR: k6 is not installed or not in PATH." >&2
    exit 1
}

command -v python >/dev/null 2>&1 || {
    echo "ERROR: python is not installed or not in PATH." >&2
    exit 1
}

[[ "$VUS" =~ ^[1-9][0-9]*$ ]] || {
    echo "ERROR: VUS must be a positive integer." >&2
    exit 1
}

[[ "$DURATION" =~ ^[1-9][0-9]*(s|m|h)$ ]] || {
    echo "ERROR: DURATION must look like 30s, 2m, or 1h." >&2
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

if [[ -z "$USERNAMES" ]]; then
    echo "ERROR: No usernames were exported." >&2
    exit 1
fi

USERNAME_COUNT="$(printf '%s' "$USERNAMES" | awk -F',' '{print NF}')"
echo "Exported usernames: $USERNAME_COUNT"

echo
echo "Running k6..."
set +e
API_BASE_URL="$BASE_URL" \
AUTH_URL="${AUTH_URL:-http://127.0.0.1:5001}" \
USER_URL="${USER_URL:-http://127.0.0.1:5002}" \
ORDER_URL="${ORDER_URL:-http://127.0.0.1:5003}" \
BILLING_URL="${BILLING_URL:-http://127.0.0.1:5004}" \
DEMO_PASSWORD="${DEMO_PASSWORD:-Password123!}" \
USERNAMES="$USERNAMES" \
VUS="$VUS" \
DURATION="$DURATION" \
k6 run --summary-export "$RESULT_FILE" \
    "$SCRIPT_DIR/baseline.js" 2>&1 | tee "$LOG_FILE"
K6_STATUS=${PIPESTATUS[0]}
set -e

if [[ "$K6_STATUS" -ne 0 ]]; then
    echo
    echo "ERROR: k6 exited with status $K6_STATUS."
    echo "Check: $LOG_FILE"
    echo "Inspect: $RESULT_FILE"
    exit "$K6_STATUS"
fi

echo
echo "=========================================="
echo " Benchmark Summary"
echo "=========================================="

python - "$RESULT_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as file:
    report = json.load(file)

metrics = report.get("metrics", {})

def value(name, field, default=0):
    return metrics.get(name, {}).get(field, default)

rows = [
    ("Requests/sec", "http_reqs", "rate", "req/s"),
    ("Request count", "http_reqs", "count", "requests"),
    ("Average latency", "http_req_duration", "avg", "ms"),
    ("P50 latency", "http_req_duration", "med", "ms"),
    ("P95 latency", "http_req_duration", "p(95)", "ms"),
    ("P99 latency", "http_req_duration", "p(99)", "ms"),
    ("Maximum latency", "http_req_duration", "max", "ms"),
]

print(f"{'Metric':<24} {'Value':>14}  Unit")
print("-" * 52)

for label, metric, field, unit in rows:
    result = value(metric, field)
    print(f"{label:<24} {result:>14.3f}  {unit}")

print(f"{'Failed request rate':<24} {value('http_req_failed', 'value') * 100:>14.3f}  %")
print(f"{'Check pass rate':<24} {value('checks', 'value') * 100:>14.3f}  %")

print("\nPer-endpoint latency:")
for name in (
    "login_duration_ms",
    "verify_duration_ms",
    "profile_duration_ms",
    "orders_duration_ms",
    "invoice_duration_ms",
):
    if name not in metrics:
        print(f"  {name}: no data")
        continue

    item = metrics[name]
    counter_name = name.replace("_duration_ms", "_samples")
    counter = metrics.get(counter_name, {})
    count = counter.get("count", counter.get("value", 0))
    print(
        f"  {name:<24} avg={item.get('avg', 0):.2f} ms, "
        f"P95={item.get('p(95)', 0):.2f} ms, "
        f"count={count}"
    )

print("\nThresholds:")
for name, condition, passed in (
    ("http_req_failed", "rate<0.01", value("http_req_failed", "value") < 0.01),
    ("benchmark_errors", "rate<0.01", value("benchmark_errors", "value") < 0.01),
    ("checks", "rate>0.99", value("checks", "value") > 0.99),
    ("http_req_duration", "p(95)<50 ms", value("http_req_duration", "p(95)") < 50),
):
    print(f"  {'PASS' if passed else 'FAIL'}: {name} ({condition})")
PY

echo
echo "JSON summary: $RESULT_FILE"
echo "Console log:  $LOG_FILE"
echo "Benchmark finished."
