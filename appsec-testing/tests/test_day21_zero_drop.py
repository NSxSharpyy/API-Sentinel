"""Unit tests for Day 21 zero-drop acceptance criteria."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.enforcement.zero_drop_verification import evaluate_report


def base_report():
    return {
        "legitimate_request_count": 100,
        "legitimate_success_rate": 1.0,
        "legitimate_failure_count": 0,
        "attacker_blocked_count": 5,
        "enforcement_was_active": True,
    }


def test_all_acceptance_criteria_pass():
    report = evaluate_report(base_report())
    assert report["overall"] == "PASS"
    assert all(report["checks"].values())


def test_empty_legitimate_run_fails():
    report = base_report()
    report["legitimate_request_count"] = 0
    report["legitimate_success_rate"] = 0.0
    report = evaluate_report(report)
    assert report["overall"] == "FAIL"
    assert report["checks"]["legitimate_traffic_observed"] is False


def test_any_legitimate_failure_fails():
    report = base_report()
    report["legitimate_failure_count"] = 1
    report["legitimate_success_rate"] = 0.99
    report = evaluate_report(report)
    assert report["overall"] == "FAIL"
    assert report["checks"]["zero_legitimate_failures"] is False


def test_no_attacker_denials_fails():
    report = base_report()
    report["attacker_blocked_count"] = 0
    report = evaluate_report(report)
    assert report["overall"] == "FAIL"
    assert report["checks"]["attacker_blocked"] is False


def test_inactive_enforcement_fails():
    report = base_report()
    report["enforcement_was_active"] = False
    report = evaluate_report(report)
    assert report["overall"] == "FAIL"
    assert report["checks"]["enforcement_was_active"] is False
