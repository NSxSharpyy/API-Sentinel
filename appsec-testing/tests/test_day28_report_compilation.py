import importlib.util
import json
import os
import time
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "reporting"
    / "compile_report.py"
)

SPEC = importlib.util.spec_from_file_location("compile_report", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_load_json_reads_valid_object(tmp_path):
    path = tmp_path / "valid.json"
    path.write_text('{"overall": "PASS"}', encoding="utf-8")

    data, status = MODULE.load_json(path)

    assert data == {"overall": "PASS"}
    assert status == "available"


def test_load_json_handles_missing_file(tmp_path):
    data, status = MODULE.load_json(tmp_path / "missing.json")

    assert data is None
    assert status == "missing"


def test_load_json_handles_malformed_json(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text('{"overall": ', encoding="utf-8")

    data, status = MODULE.load_json(path)

    assert data is None
    assert status.startswith("unreadable:")


def test_load_json_rejects_non_object_json(tmp_path):
    path = tmp_path / "array.json"
    path.write_text('[1, 2, 3]', encoding="utf-8")

    data, status = MODULE.load_json(path)

    assert data is None
    assert status.startswith("invalid:")


def test_latest_json_selects_newest_report(tmp_path):
    older = tmp_path / "older.json"
    newer = tmp_path / "newer.json"
    older.write_text("{}", encoding="utf-8")
    newer.write_text("{}", encoding="utf-8")

    old_time = time.time() - 100
    new_time = time.time()
    os.utime(older, (old_time, old_time))
    os.utime(newer, (new_time, new_time))

    assert MODULE.latest_json(tmp_path, "*.json") == newer


def test_empty_project_generates_report_without_crashing(tmp_path):
    report = MODULE.build_report(tmp_path)

    assert "# API-Sentinel Performance and Security Validation Report" in report
    assert "Evidence availability by day" in report
    assert "Unavailable" in report
    assert "production" in report.lower()


def test_day18_rerun_metrics_are_reported_from_evidence(tmp_path):
    logs = tmp_path / "logs" / "day18_20261031_120756"
    logs.mkdir(parents=True)
    source = logs / "rate_limit_effectiveness_report_rerun.json"

    source.write_text(
        json.dumps({
            "overall": "PASS",
            "runs": {
                "flood": {"blocked_rate": 0.98},
                "legitimate": {"success_rate": 1.0},
                "credential_stuffing": {"blocked_rate": 0.16},
            },
            "checks": {
                "flood_blocking": {"pass": True},
                "legitimate_success": {"pass": True},
            },
        }),
        encoding="utf-8",
    )

    report = MODULE.build_report(tmp_path)

    assert "Rerun overall status: **PASS**" in report
    assert "98.00%" in report
    assert "100.00%" in report
    assert "temporary local mock limiter" in report


def test_application_simulation_is_not_described_as_kernel_proof(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "zero_drop_report.json").write_text(
        json.dumps({
            "overall": "PASS",
            "evidence_type": "application_layer_simulation",
            "kernel_drop_proof": False,
            "adapter_stats": {
                "legitimate_requests": 100,
                "legitimate_success": 100,
                "evidence_type": "application_layer_simulation",
                "kernel_drop_proof": False,
            },
        }),
        encoding="utf-8",
    )

    report = MODULE.build_report(tmp_path)

    assert "application_layer_simulation" in report
    assert "not kernel packet-drop proof" in report


def test_interrupted_endurance_run_is_not_called_six_hour_certification(tmp_path):
    path = tmp_path / "logs" / "day27" / "run_6h"
    path.mkdir(parents=True)
    (path / "endurance_report.json").write_text(
        json.dumps({
            "status": "INTERRUPTED",
            "evidence_type": "legitimate_traffic_endurance",
            "target_duration_seconds": 21600,
            "observed_duration_seconds": 2119.1,
            "checkpoint_count": 40,
            "sample_count": 37,
            "sampling_error_count": 0,
            "interrupted": True,
        }),
        encoding="utf-8",
    )

    report = MODULE.build_report(tmp_path)

    assert "Status: **INTERRUPTED**" in report
    assert "not a completed six-hour endurance certification" in report

def test_completed_six_hour_endurance_is_reported_correctly(tmp_path):
    path = tmp_path / "logs" / "day27" / "run_6h_final"
    path.mkdir(parents=True)
    (path / "endurance_report.json").write_text(
        json.dumps({
            "status": "COMPLETED",
            "evidence_type": "legitimate_traffic_endurance",
            "target_duration_seconds": 21600,
            "observed_duration_seconds": 21605,
            "checkpoint_count": 361,
            "sample_count": 361,
            "sampling_error_count": 0,
            "interrupted": False,
        }),
        encoding="utf-8",
    )

    report = MODULE.build_report(tmp_path)

    assert "Status: **COMPLETED**" in report
    assert "The six-hour endurance target was completed." in report


def test_short_completed_status_is_not_six_hour_certification(tmp_path):
    path = tmp_path / "logs" / "day27" / "short_run"
    path.mkdir(parents=True)
    (path / "endurance_report.json").write_text(
        json.dumps({
            "status": "COMPLETED",
            "target_duration_seconds": 21600,
            "observed_duration_seconds": 1800,
            "checkpoint_count": 31,
            "sample_count": 30,
            "sampling_error_count": 0,
            "interrupted": False,
        }),
        encoding="utf-8",
    )

    report = MODULE.build_report(tmp_path)

    assert "Status: **COMPLETED**" in report
    assert "does not establish completion of the six-hour endurance target" in report
    assert "The six-hour endurance target was completed." not in report

def test_day5_benchmark_scope_and_thresholds_are_distinguished(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "benchmark-baseline.md").write_text(
        "# Benchmark documentation",
        encoding="utf-8",
    )

    report = MODULE.build_report(tmp_path)

    assert "117.511 ms" in report
    assert "failed the required less-than-50-ms threshold" in report
    assert "12.50 ms" in report
    assert "561.34 ms" in report
    assert "Bootstrap login P95" in report


def test_early_security_tests_are_not_claimed_as_historical_runs(tmp_path):
    tests = tmp_path / "tests"
    tests.mkdir()

    for filename in (
        "test_day2_auth_bola.py",
        "test_day8_bola_attack.py",
        "test_day9_privesc_attack.py",
        "test_day10_shadow_zombie.py",
    ):
        (tests / filename).write_text("# test source\n", encoding="utf-8")

    report = MODULE.build_report(tmp_path)

    assert "Days 2, 8, 9 and 10" in report
    assert "do not establish that a historical attack campaign was executed" in report
    assert "Day 8" in report
    assert "Day 10" in report


def test_phase3_conditional_freeze_is_reported(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()

    (logs / "phase3_freeze_report.json").write_text(
        json.dumps({
            "phase3_freeze_status": "CONDITIONAL",
            "kernel_certification": "PASS",
            "checks": {
                "phase1": {
                    "status": "HISTORICAL_PASS",
                    "source": "docs/phase1-freeze-report.json",
                    "check_count": 13,
                },
                "phase2": {
                    "status": "DOCUMENTED_PASS_UNVERIFIED",
                    "source": "docs/phase2-freeze.md",
                    "reported_checks": {
                        "total": 9,
                        "passed": 9,
                    },
                },
                "day15": {
                    "status": "FAIL",
                    "measured_deltas_ms": [36.6647671, 8.727258],
                },
            },
            "limitations": [
                "Phase 2 machine-readable report is missing."
            ],
        }),
        encoding="utf-8",
    )

    report = MODULE.build_report(tmp_path)

    assert "Phase 3 overall freeze status: **CONDITIONAL**" in report
    assert "Kernel certification status: **PASS**" in report
    assert "DOCUMENTED_PASS_UNVERIFIED" in report
    assert "9/9 checks are documented" in report
    assert "36.6647671" in report


def test_empty_project_includes_methodology_and_recommendations(tmp_path):
    report = MODULE.build_report(tmp_path)

    assert "## Executive summary" in report
    assert "## Methodology" in report
    assert "## 6. Recommendations and next steps" in report
    assert "Phase 3 overall freeze status" not in report


def test_artifact_inventory_discovers_all_json_and_markdown(tmp_path):
    logs = tmp_path / "logs" / "nested"
    docs = tmp_path / "docs" / "nested"
    logs.mkdir(parents=True)
    docs.mkdir(parents=True)

    (logs / "valid.json").write_text('{"overall": "PASS"}', encoding="utf-8")
    (logs / "broken.json").write_text('{"overall": ', encoding="utf-8")
    (docs / "evidence.md").write_text("# Evidence", encoding="utf-8")

    artifacts = MODULE.discover_artifacts(tmp_path)

    assert ("logs/nested/valid.json", "available") in artifacts
    assert any(
        name == "logs/nested/broken.json" and status.startswith("invalid:")
        for name, status in artifacts
    )
    assert ("docs/nested/evidence.md", "available") in artifacts


def test_report_contains_complete_inventory_and_invalid_json_status(tmp_path):
    logs = tmp_path / "logs"
    docs = tmp_path / "docs"
    logs.mkdir()
    docs.mkdir()

    (logs / "bad.json").write_text("{broken", encoding="utf-8")
    (docs / "notes.md").write_text("# Notes", encoding="utf-8")

    report = MODULE.build_report(tmp_path)

    assert "Complete evidence artifact inventory" in report
    assert "`logs/bad.json`" in report
    assert "`docs/notes.md`" in report
    assert "Invalid JSON artifacts: **1**" in report


def test_report_includes_separate_latency_graphs_and_source_context(tmp_path):
    report = MODULE.build_report(tmp_path)

    assert "Latency comparisons" in report
    assert "75.761, 117.511, 12.50" in report
    assert "85.7661309, 122.430898" in report
    assert "561.34 ms" in report
    assert "36.6647671 ms" in report
    assert "not a real eBPF overhead measurement" in report


def test_report_discloses_missing_vulnerability_register(tmp_path):
    report = MODULE.build_report(tmp_path)

    assert "docs/vulnerabilities.md" in report
    assert "does not claim to provide a complete vulnerability register" in report
