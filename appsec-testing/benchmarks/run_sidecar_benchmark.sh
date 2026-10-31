#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
RESULTS_DIR="$SCRIPT_DIR/results"
DAY15_DIR="$RESULTS_DIR/day15"
DEFAULT_SIDECAR_LAUNCHER="$SCRIPT_DIR/sidecar_proxy/mock_ebpf_sidecar.py"

cd "$ROOT_DIR"

VUS="${1:-5}"
DURATION="${2:-30s}"
SIDECAR_LAUNCHER="${SIDECAR_LAUNCHER:-$DEFAULT_SIDECAR_LAUNCHER}"
SIDECAR_KIND="${SIDECAR_KIND:-mock}"
MOCK_DELAY_MS="${SIDECAR_OVERHEAD_MS:-2.0}"
THRESHOLD_MS="${SIDECAR_THRESHOLD_MS:-5}"

BASELINE_RESULT=""
SIDECAR_RESULT=""

mkdir -p "$DAY15_DIR"

[[ "$VUS" =~ ^[1-9][0-9]*$ ]] || {
    echo "ERROR: VUS must be a positive integer." >&2
    exit 2
}
[[ "$DURATION" =~ ^[1-9][0-9]*(s|m|h)$ ]] || {
    echo "ERROR: DURATION must look like 30s, 2m, or 1h." >&2
    exit 2
}
[[ "$SIDECAR_KIND" == "mock" || "$SIDECAR_KIND" == "real" ]] || {
    echo "ERROR: SIDECAR_KIND must be mock or real." >&2
    exit 2
}

python - "$MOCK_DELAY_MS" "$THRESHOLD_MS" <<'PY'
import math
import sys

for name, value, allow_zero in (
    ("SIDECAR_OVERHEAD_MS", sys.argv[1], True),
    ("SIDECAR_THRESHOLD_MS", sys.argv[2], False),
):
    try:
        number = float(value)
    except ValueError:
        raise SystemExit(f"ERROR: {name} must be numeric.")
    if not math.isfinite(number) or number < 0 or (not allow_zero and number == 0):
        raise SystemExit(f"ERROR: invalid {name} value.")
PY

command -v k6 >/dev/null 2>&1 || {
    echo "ERROR: k6 is not installed." >&2
    exit 1
}

if [[ "$SIDECAR_LAUNCHER" == *.py ]]; then
    [[ -f "$SIDECAR_LAUNCHER" ]] || {
        echo "ERROR: Python sidecar launcher not found: $SIDECAR_LAUNCHER" >&2
        exit 1
    }
    SIDECAR_CMD=(python "$SIDECAR_LAUNCHER")
else
    [[ -x "$SIDECAR_LAUNCHER" ]] || {
        echo "ERROR: sidecar launcher must be executable: $SIDECAR_LAUNCHER" >&2
        exit 1
    }
    SIDECAR_CMD=("$SIDECAR_LAUNCHER")
fi

declare -a SIDECAR_PIDS=()

cleanup() {
    local pid
    for pid in "${SIDECAR_PIDS[@]:-}"; do
        kill "$pid" 2>/dev/null || true
    done
    for pid in "${SIDECAR_PIDS[@]:-}"; do
        wait "$pid" 2>/dev/null || true
    done
}
trap cleanup EXIT INT TERM

latest_baseline_json() {
    find "$RESULTS_DIR" -maxdepth 1 -type f -name 'baseline_*.json' \
        -printf '%T@ %p\n' |
        sort -nr |
        head -n 1 |
        cut -d' ' -f2-
}

run_existing_benchmark() {
    local label="$1"
    shift
    local before after source_json stamp

    before="$(latest_baseline_json || true)"

    echo
    echo "=== Running $label benchmark ==="
    if env "$@" bash "$SCRIPT_DIR/run_benchmark.sh" "$VUS" "$DURATION"; then
        :
    else
        echo "WARNING: existing benchmark runner reported a threshold or runtime failure." >&2
    fi

    after="$(latest_baseline_json || true)"
    if [[ -z "$after" || "$after" == "$before" ]]; then
        echo "ERROR: no new benchmark JSON was produced for $label." >&2
        return 1
    fi

    stamp="$(date +%Y%m%d_%H%M%S)"
    source_json="$DAY15_DIR/day15_${label}_${stamp}.json"
    cp -- "$after" "$source_json"
    echo "Saved $label result: $source_json"

    case "$label" in
        baseline) BASELINE_RESULT="$source_json" ;;
        mock_sidecar|real_sidecar) SIDECAR_RESULT="$source_json" ;;
        *)
            echo "ERROR: unexpected benchmark label: $label" >&2
            return 2
            ;;
    esac
}

echo "Day 15 latency comparison"
echo "Virtual users: $VUS"
echo "Duration: $DURATION"
echo "Sidecar kind: $SIDECAR_KIND"
echo "Sidecar launcher: $SIDECAR_LAUNCHER"
echo "Configured mock delay: ${MOCK_DELAY_MS} ms (mock only)"
echo "Required observed P95 delta: strictly less than ${THRESHOLD_MS} ms"

if [[ "$SIDECAR_KIND" == "mock" ]]; then
    echo "NOTICE: this is a temporary application-layer mock, not real eBPF."
fi

echo
echo "=== Checking direct services ==="
python "$SCRIPT_DIR/../scripts/check_health.py"

run_existing_benchmark baseline \
    AUTH_URL=http://127.0.0.1:5001 \
    USER_URL=http://127.0.0.1:5002 \
    ORDER_URL=http://127.0.0.1:5003 \
    BILLING_URL=http://127.0.0.1:5004

declare -a PORTS=(6001 6002 6003 6004)
declare -a UPSTREAMS=(5001 5002 5003 5004)
declare -a NAMES=(auth user order billing)

echo
echo "=== Starting four ${SIDECAR_KIND} sidecars ==="
for i in "${!PORTS[@]}"; do
    port="${PORTS[$i]}"
    upstream="${UPSTREAMS[$i]}"
    name="${NAMES[$i]}"

    if ss -ltn | grep -qE "127\\.0\\.0\\.1:${port}|0\\.0\\.0\\.0:${port}|\\[::\\]:${port}"; then
        echo "ERROR: port $port is already in use; refusing to interfere with another process." >&2
        exit 1
    fi

    SIDECAR_OVERHEAD_MS="$MOCK_DELAY_MS" \
    UPSTREAM_URL="http://127.0.0.1:${upstream}" \
    LISTEN_PORT="$port" \
        "${SIDECAR_CMD[@]}" \
        >"/tmp/api-sentinel-day15-${name}.log" 2>&1 &

    SIDECAR_PIDS+=("$!")
done

echo "Waiting for sidecar health checks..."
for i in "${!PORTS[@]}"; do
    port="${PORTS[$i]}"
    ready=0

    for attempt in $(seq 1 30); do
        if curl --silent --show-error --fail --max-time 1 \
            "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
            ready=1
            break
        fi
        sleep 0.25
    done

    if [[ "$ready" -ne 1 ]]; then
        echo "ERROR: sidecar on port $port failed health check." >&2
        cat "/tmp/api-sentinel-day15-${NAMES[$i]}.log" >&2 || true
        exit 1
    fi

    echo "[OK] ${NAMES[$i]} sidecar on port $port"
done

if [[ "$SIDECAR_KIND" == "mock" ]]; then
    SIDECAR_LABEL="mock_sidecar"
else
    SIDECAR_LABEL="real_sidecar"
fi

run_existing_benchmark "$SIDECAR_LABEL" \
    AUTH_URL=http://127.0.0.1:6001 \
    USER_URL=http://127.0.0.1:6002 \
    ORDER_URL=http://127.0.0.1:6003 \
    BILLING_URL=http://127.0.0.1:6004

stamp="$(date +%Y%m%d_%H%M%S)"
overhead_json="$DAY15_DIR/day15_overhead_report_${stamp}.json"
milestone_md="$DAY15_DIR/day15_milestone_${stamp}.md"

echo
echo "=== Strict P95 overhead gate ==="
comparison_status=0
if python "$SCRIPT_DIR/compute_overhead.py" \
    --baseline "$BASELINE_RESULT" \
    --sidecar "$SIDECAR_RESULT" \
    --metric http_req_duration \
    --threshold-ms "$THRESHOLD_MS" \
    --absolute-p95-threshold-ms "${ABSOLUTE_P95_THRESHOLD_MS:-50}" \
    --out "$overhead_json"; then
    comparison_status=0
else
    comparison_status=$?
fi

if [[ "$comparison_status" -gt 1 ]]; then
    echo "ERROR: overhead calculator failed with status $comparison_status." >&2
    exit "$comparison_status"
fi

python - "$overhead_json" "$milestone_md" "$SIDECAR_KIND" \
    "$SIDECAR_LAUNCHER" "$MOCK_DELAY_MS" "$THRESHOLD_MS" <<'PY'
import json
import sys
from datetime import date
from pathlib import Path

report_path, markdown_path, kind, launcher, delay, threshold = sys.argv[1:]
data = json.loads(Path(report_path).read_text(encoding="utf-8"))

if kind == "mock":
    milestone_status = "pipeline-validated-pending-real-hardware"
    caveat = (
        "This result uses a temporary application-layer mock proxy. "
        "It does not measure real eBPF overhead."
    )
else:
    milestone_status = "real-component-run-pending-review"
    caveat = (
        "The launcher was configured as a real component, but this script "
        "cannot independently certify that it is an eBPF implementation. "
        "Review component identity and deployment evidence."
    )

content = f"""# Day 15 Latency Milestone Report

- **Date:** {date.today().isoformat()}
- **Milestone status:** `{milestone_status}`
- **Sidecar kind configured:** `{kind}`
- **Launcher:** `{launcher}`
- **Configured mock delay:** {delay} ms (ignored by compatible real components)
- **Gate:** observed aggregate HTTP P95 delta strictly less than {threshold} ms
- **Overhead gate result:** **{data['status']}**
- **Absolute P95 target:** strictly less than {data['absolute_p95_threshold_ms']:.3f} ms
- **Baseline absolute P95:** {"PASS" if data['baseline_absolute_p95_pass'] else "FAIL"}
- **Sidecar absolute P95:** {"PASS" if data['sidecar_absolute_p95_pass'] else "FAIL"}
- **Combined absolute-latency result:** **{data['absolute_latency_status']}**

## Measurements

- Baseline aggregate P95: {data['baseline_p95_ms']:.6f} ms
- Sidecar aggregate P95: {data['sidecar_p95_ms']:.6f} ms
- Observed P95 delta: {data['observed_p95_delta_ms']:.6f} ms
- Required threshold: {data['threshold_ms']:.3f} ms

## Evidence

- Baseline JSON: `{data['baseline_file']}`
- Sidecar JSON: `{data['sidecar_file']}`
- Machine-readable comparison: `{report_path}`

## Interpretation

{caveat}

A configured delay is not the same as observed end-to-end overhead. Workload
variability and proxy/component costs can affect the measured delta. A FAIL is
preserved as a failure; it is not converted to a PASS.

## Real-sidecar handoff

A replacement launcher must accept `UPSTREAM_URL` and `LISTEN_PORT`, forward
HTTP traffic to its upstream, and serve a successful `GET /health` response.
The mock additionally consumes `SIDECAR_OVERHEAD_MS`. The real component must
be validated against this contract before claiming a zero-code-change swap.
"""
Path(markdown_path).write_text(content, encoding="utf-8")
print(f"Saved dated milestone report: {markdown_path}")
PY

echo
echo "=== Day 15 result files ==="
find "$DAY15_DIR" -maxdepth 1 -type f \
    \( -name 'day15_*.json' -o -name 'day15_milestone_*.md' \) \
    -printf '%f\n' | sort

if [[ "$comparison_status" -eq 1 ]]; then
    echo
    echo "GATE FAIL: observed P95 delta is not strictly below ${THRESHOLD_MS} ms." >&2
    exit 1
fi

echo
echo "GATE PASS: observed P95 delta is strictly below ${THRESHOLD_MS} ms."
