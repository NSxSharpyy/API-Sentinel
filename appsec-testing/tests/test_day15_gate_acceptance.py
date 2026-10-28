"""Deterministic acceptance checks for the strict Day 15 P95 gate.

These tests validate calculator behavior using controlled JSON summaries.
They are not real sidecar benchmark measurements.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CALCULATOR = ROOT / "benchmarks" / "compute_overhead.py"


def compare(tmp_path, delta_ms):
    baseline = tmp_path / "baseline.json"
    sidecar = tmp_path / "sidecar.json"

    def summary(p95):
        return {
            "metrics": {
                "http_req_duration": {"p(95)": p95},
                "http_req_failed": {"value": 0},
                "checks": {"value": 1},
                "benchmark_errors": {"value": 0},
            }
        }

    baseline.write_text(json.dumps(summary(10.0)), encoding="utf-8")
    sidecar.write_text(json.dumps(summary(10.0 + delta_ms)), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable, str(CALCULATOR),
            "--baseline", str(baseline),
            "--sidecar", str(sidecar),
            "--metric", "http_req_duration",
            "--threshold-ms", "5",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result


def test_two_ms_delta_passes(tmp_path):
    result = compare(tmp_path, 2.0)
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "PASS"


def test_eight_ms_delta_fails(tmp_path):
    result = compare(tmp_path, 8.0)
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "FAIL"


def test_exact_five_ms_boundary_fails(tmp_path):
    result = compare(tmp_path, 5.0)
    assert result.returncode == 1, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["observed_p95_delta_ms"] == 5.0
    assert report["comparison"] == "strictly_less_than"
    assert report["status"] == "FAIL"
