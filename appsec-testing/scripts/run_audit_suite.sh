#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APPSEC_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PYTHON="${PYTHON:-python}"

if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "ERROR: Python executable '$PYTHON' was not found." >&2
    echo "Activate the project virtual environment or set PYTHON." >&2
    exit 127
fi

LOG_DIR="$APPSEC_DIR/logs"
mkdir -p "$LOG_DIR"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_FILE="$LOG_DIR/audit-suite-$RUN_ID.log"

run_validator() {
    local label="$1"
    local validator="$2"

    echo
    echo "============================================================"
    echo "START: $label"
    echo "Validator: $validator"
    echo "============================================================"

    if "$PYTHON" "$SCRIPT_DIR/$validator"; then
        echo "RESULT: PASS — $label"
    else
        local status=$?
        echo "RESULT: FAIL — $label (exit code $status)"
        echo "Stopping audit suite; later validators will not run."
        return "$status"
    fi
}

{
    echo "API-Sentinel Audit Suite"
    echo "Started UTC: $RUN_ID"
    echo "App directory: $APPSEC_DIR"
    echo "Python: $PYTHON"

    run_validator "Phase 1 validation" "validate_phase1.py" || exit $?
    run_validator "Phase 2 validation" "validate_phase2.py" || exit $?

    echo
    echo "AUDIT SUITE RESULT: PASS"
    echo "Both Phase 1 and Phase 2 validators passed."
} 2>&1 | tee "$LOG_FILE"

status=${PIPESTATUS[0]}
echo
echo "Audit suite exit code: $status"
echo "Combined log: $LOG_FILE"
exit "$status"
