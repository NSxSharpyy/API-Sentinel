"""Unit tests for Day 22 mixed-stress acceptance criteria."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.enforcement.mixed_stress_test import (
    evaluate_legitimate_ratio,
    evaluate_metrics,
    memory_to_mb,
    parse_docker_stats_row,
    percentile,
    summarize_resources,
)


def base_report():
    return {
        "workload_request_count": 2000,
        "legitimate_request_count": 1800,
        "legitimate_success_count": 1780,
        "adversarial_request_count": 200,
        "adversarial_blocked_count": 60,
        "latency_probe_count": 20,
        "latency_probe_failure_count": 0,
        "resource_sample_count": 10,
        "resource_sampling_error_count": 0,
        "enforcement_was_active": True,
    }


def test_normal_workload_passes_acceptance():
    report = evaluate_metrics(base_report())
    assert report["overall"] == "PASS"
    assert all(report["checks"].values())
    assert report["metrics"]["legitimate_ratio"] == 0.9
    assert report["metrics"]["adversarial_block_rate"] == 0.3


def test_skewed_50_50_traffic_fails_ratio_validation():
    result = evaluate_legitimate_ratio(1000, 2000)
    assert result["ratio"] == 0.5
    assert result["passes"] is False


def test_ratio_at_lower_boundary_passes():
    assert evaluate_legitimate_ratio(1700, 2000)["passes"] is True


def test_ratio_above_upper_boundary_fails():
    assert evaluate_legitimate_ratio(1920, 2000)["passes"] is False


def test_wrong_total_request_count_fails():
    report = base_report()
    report["workload_request_count"] = 1999
    assert evaluate_metrics(report)["checks"]["exact_workload_count"] is False


def test_legitimate_success_below_98_percent_fails():
    report = base_report()
    report["legitimate_success_count"] = 1763
    result = evaluate_metrics(report)
    assert result["checks"]["legitimate_success_rate_at_least_98_percent"] is False
    assert result["overall"] == "FAIL"


def test_block_rate_below_30_percent_fails():
    report = base_report()
    report["adversarial_blocked_count"] = 59
    result = evaluate_metrics(report)
    assert result["checks"]["adversarial_block_rate_at_least_30_percent"] is False
    assert result["overall"] == "FAIL"


def test_failed_latency_probe_fails_acceptance():
    report = base_report()
    report["latency_probe_failure_count"] = 1
    assert evaluate_metrics(report)["overall"] == "FAIL"


def test_missing_resource_samples_fail_acceptance():
    report = base_report()
    report["resource_sample_count"] = 0
    assert evaluate_metrics(report)["overall"] == "FAIL"


def test_inactive_enforcement_fails_acceptance():
    report = base_report()
    report["enforcement_was_active"] = False
    assert evaluate_metrics(report)["overall"] == "FAIL"


def test_skewed_counts_fail_full_acceptance_evaluation():
    report = base_report()
    report["legitimate_request_count"] = 1000
    report["legitimate_success_count"] = 1000
    report["adversarial_request_count"] = 1000
    report["adversarial_blocked_count"] = 300

    result = evaluate_metrics(report)

    assert result["overall"] == "FAIL"
    assert result["checks"]["exact_legitimate_count"] is False
    assert result["checks"]["exact_adversarial_count"] is False
    assert result["checks"]["legitimate_ratio_in_range"] is False


def test_resource_sampling_errors_fail_acceptance():
    report = base_report()
    report["resource_sampling_error_count"] = 1

    result = evaluate_metrics(report)

    assert result["overall"] == "FAIL"
    assert result["checks"]["resource_sampling_errors_absent"] is False



def test_percentile_reports_p50_and_p95():
    values = list(range(1, 101))
    assert percentile(values, 50) == 50
    assert percentile(values, 95) == 95
    assert percentile([], 95) is None


def test_memory_units_convert_to_megabytes():
    assert memory_to_mb("1MiB") == 1.049
    assert memory_to_mb("1GiB") == 1073.742
    assert memory_to_mb("2GB") == 2000.0


def test_docker_stats_json_row_is_parsed():
    row = (
        '{"Name":"api-user","CPUPerc":"12.50%",'
        '"MemUsage":"25.00MiB / 1GiB"}'
    )
    parsed = parse_docker_stats_row(row)
    assert parsed["name"] == "api-user"
    assert parsed["cpu_percent"] == 12.5
    assert parsed["memory_used_mb"] == 26.214
    assert parsed["memory_limit_mb"] == 1073.742


def test_invalid_docker_memory_value_is_rejected():
    import pytest

    with pytest.raises(ValueError):
        memory_to_mb("not-a-memory-value")


def test_resource_summary_tracks_peaks_per_container():
    samples = [
        {"containers": [
            {"name": "api-user", "cpu_percent": 10.0,
             "memory_used_mb": 20.0, "memory_limit_mb": 100.0},
            {"name": "api-billing", "cpu_percent": 30.0,
             "memory_used_mb": 50.0, "memory_limit_mb": 200.0},
        ]},
        {"containers": [
            {"name": "api-user", "cpu_percent": 45.0,
             "memory_used_mb": 35.0, "memory_limit_mb": 100.0},
        ]},
    ]
    summary = summarize_resources(samples)
    assert summary["container_peaks"]["api-user"]["max_cpu_percent"] == 45.0
    assert summary["container_peaks"]["api-user"]["max_memory_used_mb"] == 35.0
    assert summary["max_cpu_percent_across_containers"] == 45.0
    assert summary["max_memory_used_mb_across_containers"] == 50.0


def test_custom_50_50_workload_fails_only_the_ratio_guard():
    report = base_report()
    report.update({
        "workload_request_count": 1000,
        "legitimate_request_count": 500,
        "legitimate_success_count": 500,
        "adversarial_request_count": 500,
        "adversarial_blocked_count": 150,
    })

    result = evaluate_metrics(
        report,
        expected_legitimate_count=500,
        expected_adversarial_count=500,
    )

    assert result["checks"]["exact_workload_count"] is True
    assert result["checks"]["exact_legitimate_count"] is True
    assert result["checks"]["exact_adversarial_count"] is True
    assert result["checks"]["legitimate_ratio_in_range"] is False
    assert result["overall"] == "FAIL"
