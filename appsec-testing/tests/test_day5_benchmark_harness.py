"""Day 5 tests: benchmark harness supporting code is correct."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APPSEC_ROOT = ROOT / "appsec-testing"
EXPORT_SCRIPT = APPSEC_ROOT / "benchmarks" / "export_usernames.py"
BASELINE_JS = APPSEC_ROOT / "benchmarks" / "baseline.js"
RUNNER = APPSEC_ROOT / "benchmarks" / "run_benchmark.sh"
SEED_SCRIPT = APPSEC_ROOT / "services" / "_shared" / "seed_db.py"


@pytest.fixture(scope="module")
def seeded_db(tmp_path_factory):
    """Create test data in a disposable database, never the live database."""
    db_path = tmp_path_factory.mktemp("day5_db") / "bench_test.db"
    env = os.environ.copy()
    env["DB_PATH"] = str(db_path)

    subprocess.run(
        [sys.executable, str(SEED_SCRIPT)],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return db_path


def test_export_usernames_returns_50_unique_names(seeded_db):
    env = os.environ.copy()
    env["DB_PATH"] = str(seeded_db)

    result = subprocess.run(
        [sys.executable, str(EXPORT_SCRIPT)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    usernames = result.stdout.strip().split(",")

    assert len(usernames) == 50
    assert all(usernames)
    assert len(set(usernames)) == len(usernames)


def test_export_usernames_fails_on_empty_database(tmp_path):
    empty_db = tmp_path / "empty.db"
    env = os.environ.copy()
    env["DB_PATH"] = str(empty_db)

    result = subprocess.run(
        [sys.executable, str(EXPORT_SCRIPT)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0


def test_baseline_js_exists_and_is_nonempty():
    assert BASELINE_JS.exists()
    assert BASELINE_JS.stat().st_size > 500


def test_baseline_js_contains_required_thresholds():
    content = BASELINE_JS.read_text()

    assert "thresholds" in content
    assert "http_req_failed" in content
    assert "http_req_duration" in content


def test_baseline_js_uses_only_the_authenticated_users_invoice():
    content = BASELINE_JS.read_text()

    assert "ownedInvoices" in content
    assert "invoice.owner_id" in content
    assert "String(userId)" in content
    assert "invoice.id" in content
    assert "/billing/invoices/1`" not in content
    assert "/billing/invoices/2`" not in content


def test_run_benchmark_script_is_executable():
    assert RUNNER.exists()
    assert os.access(RUNNER, os.X_OK), (
        "Run chmod +x appsec-testing/benchmarks/run_benchmark.sh"
    )


def test_runner_summary_uses_strict_50ms_p95_threshold():
    content = RUNNER.read_text()

    assert '"p(95)<50 ms"' in content
    assert 'value("http_req_duration", "p(95)") < 50' in content
    assert '"p(95)<100 ms"' not in content
