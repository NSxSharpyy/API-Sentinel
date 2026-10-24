"""Day 7 tests for the revised Phase 1 authenticated API benchmark."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APPSEC = ROOT / "appsec-testing"
AUTH_JS = APPSEC / "benchmarks" / "authenticated.js"
AUTH_RUNNER = APPSEC / "benchmarks" / "run_authenticated_benchmark.sh"
BASELINE_JS = APPSEC / "benchmarks" / "baseline.js"
VALIDATOR = APPSEC / "scripts" / "validate_phase1.py"
DOCS = APPSEC / "docs" / "benchmark-baseline.md"


def test_authenticated_benchmark_has_scoped_50ms_p95_threshold():
    content = AUTH_JS.read_text()
    assert "'http_req_duration{workload:authenticated}'" in content
    assert "'p(95)<50'" in content
    assert "workload: 'authenticated'" in content
    assert "workload: 'bootstrap'" in content


def test_login_latency_is_reported_separately():
    content = AUTH_JS.read_text()
    assert "new Trend('login_duration_ms')" in content
    assert "loginDuration.add(login.timings.duration)" in content


def test_authenticated_runner_is_executable_and_exports_seeded_users():
    content = AUTH_RUNNER.read_text()
    assert os.access(AUTH_RUNNER, os.X_OK)
    assert 'DB_PATH="$DB_FILE"' in content
    assert 'python "$SCRIPT_DIR/export_usernames.py"' in content
    assert 'k6 run --summary-export "$RESULT_FILE"' in content
    assert '"$SCRIPT_DIR/authenticated.js"' in content


def test_phase1_validator_uses_authenticated_runner_as_performance_gate():
    content = VALIDATOR.read_text()
    assert "run_authenticated_benchmark.sh" in content
    assert "Authenticated API benchmark (10 VUs, 15s)" in content


def test_original_login_inclusive_baseline_is_preserved():
    content = BASELINE_JS.read_text()
    assert "http_req_duration" in content
    assert "'p(95)<50'" in content


def test_documentation_records_revised_scope_and_login_metric():
    content = DOCS.read_text()
    assert "Formal Phase 1 Acceptance Thresholds" in content
    assert "workload:authenticated" in content
    assert "login_duration_ms" in content
    assert "authenticated_20261016_072011.json" in content
