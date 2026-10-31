import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "benchmarks" / "compute_overhead.py"


def write_summary(path: Path, p95: float) -> Path:
    path.write_text(
        json.dumps(
            {
                "metrics": {
                    "http_req_duration": {
                        "p(95)": p95,
                    },
                    "http_req_failed": {"value": 0},
                    "checks": {"value": 1},
                    "benchmark_errors": {"value": 0},
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def run_calculator(tmp_path: Path, baseline_p95: float, sidecar_p95: float):
    baseline = write_summary(tmp_path / "baseline.json", baseline_p95)
    sidecar = write_summary(tmp_path / "sidecar.json", sidecar_p95)
    report = tmp_path / "overhead.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--baseline",
            str(baseline),
            "--sidecar",
            str(sidecar),
            "--out",
            str(report),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return result, report


def test_delta_below_five_ms_passes(tmp_path):
    result, report = run_calculator(tmp_path, 10.0, 14.999)

    assert result.returncode == 0, result.stderr
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["status"] == "PASS"
    assert data["observed_p95_delta_ms"] < 5.0
    assert data["is_real_ebpf_measurement"] is False


def test_delta_above_five_ms_fails(tmp_path):
    result, report = run_calculator(tmp_path, 10.0, 15.001)

    assert result.returncode == 1
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["status"] == "FAIL"
    assert data["observed_p95_delta_ms"] > 5.0


def test_delta_exactly_five_ms_fails(tmp_path):
    result, report = run_calculator(tmp_path, 10.0, 15.0)

    assert result.returncode == 1
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["status"] == "FAIL"
    assert data["observed_p95_delta_ms"] == 5.0
    assert data["comparison"] == "strictly_less_than"


def test_negative_delta_passes(tmp_path):
    result, report = run_calculator(tmp_path, 12.0, 11.0)

    assert result.returncode == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["status"] == "PASS"
    assert data["observed_p95_delta_ms"] == -1.0


def test_missing_metric_fails_safely(tmp_path):
    baseline = tmp_path / "baseline.json"
    sidecar = tmp_path / "sidecar.json"
    baseline.write_text('{"metrics": {}}', encoding="utf-8")
    write_summary(sidecar, 10.0)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--baseline",
            str(baseline),
            "--sidecar",
            str(sidecar),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "missing" in result.stderr.lower()
def test_absolute_latency_gate_is_reported_separately(tmp_path):
    result, report = run_calculator(tmp_path, 10.0, 14.0)

    assert result.returncode == 0, result.stderr
    data = json.loads(report.read_text(encoding="utf-8"))

    # Overall status passes only when every required gate passes.
    assert data["status"] == "PASS"
    assert data["overhead_status"] == "PASS"
    assert data["absolute_p95_threshold_ms"] == 50.0
    assert data["baseline_absolute_p95_pass"] is True
    assert data["sidecar_absolute_p95_pass"] is True
    assert data["absolute_latency_status"] == "PASS"


def test_absolute_latency_gate_fails_if_either_p95_reaches_50_ms(tmp_path):
    result, report = run_calculator(tmp_path, 49.0, 50.0)

    # Delta passes, but reaching 50 ms fails the absolute gate.
    assert result.returncode == 1
    data = json.loads(report.read_text(encoding="utf-8"))

    assert data["overhead_status"] == "PASS"
    assert data["status"] == "FAIL"
    assert data["baseline_absolute_p95_pass"] is True
    assert data["sidecar_absolute_p95_pass"] is False
    assert data["absolute_latency_status"] == "FAIL"
