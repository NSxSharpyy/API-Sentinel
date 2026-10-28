"""Day 12 tests for Shadow/Zombie API discovery verification."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "scripts/recon/verify_discovery.py"
MOCK = ROOT / "scripts/recon/mock_member3_discovery_output.json"
MANIFEST = ROOT / "docs/shadow_zombie_manifest.md"
CONTRACT = ROOT / "scripts/recon/discovery_output_contract.md"

GROUND_TRUTH = [
    ("auth", "GET", "/debug/dump-tokens", "shadow"),
    ("auth", "GET", "/api/v1/login-status", "zombie"),
    ("user", "GET", "/internal/config", "shadow"),
    ("user", "GET", "/api/v1/users/1", "zombie"),
    ("order", "GET", "/api/v1/orders/1", "zombie"),
    ("billing", "POST", "/_admin/reset-cache", "shadow"),
    ("billing", "GET", "/api/v1/invoices/1", "zombie"),
]

DOCUMENTED_ROUTE = {
    "service": "user",
    "method": "GET",
    "path": "/api/v2/users/me",
    "classification": "documented",
    "confidence": 0.99,
}


def finding(service, method, path, classification, confidence=0.95):
    return {
        "service": service,
        "method": method,
        "path": path,
        "classification": classification,
        "confidence": confidence,
    }


def perfect_report():
    return {
        "scan_timestamp": "2026-10-19T09:00:00Z",
        "findings": [
            finding(service, method, path, category)
            for service, method, path, category in GROUND_TRUTH
        ],
    }


def run_verifier(tmp_path, report, *extra_args):
    report_path = tmp_path / "discovery.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    return subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--discovery-output", str(report_path),
            "--manifest", str(MANIFEST),
            "--skip-day11",
            "--out", str(tmp_path / "verification.json"),
            *extra_args,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_perfect_discovery_passes(tmp_path):
    result = run_verifier(tmp_path, perfect_report())
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Endpoint recall: 100.0%" in result.stdout
    assert "Precision: 100.0%" in result.stdout
    assert "RESULT: PASS" in result.stdout


def test_empty_findings_fail_with_zero_recall(tmp_path):
    report = {"scan_timestamp": "2026-10-19T09:00:00Z", "findings": []}
    result = run_verifier(tmp_path, report)
    assert result.returncode == 1
    assert "Endpoint recall: 0.0%" in result.stdout
    assert "RESULT: FAIL" in result.stdout


def test_partial_discovery_reports_four_of_seven(tmp_path):
    report = perfect_report()
    report["findings"] = report["findings"][:4]

    result = run_verifier(tmp_path, report)
    assert result.returncode == 1
    assert "Endpoints found: 4/7" in result.stdout
    assert "Endpoint recall: 57.1%" in result.stdout


def test_missing_exact_endpoint_is_reported(tmp_path):
    report = perfect_report()
    report["findings"] = [
        item for item in report["findings"]
        if item["path"] != "/api/v1/users/1"
    ]

    result = run_verifier(tmp_path, report)
    assert result.returncode == 1
    assert "user GET /api/v1/users/1" in result.stdout


def test_documented_route_classified_as_unknown_is_false_positive(tmp_path):
    report = perfect_report()
    report["findings"].append({
        **DOCUMENTED_ROUTE,
        "classification": "unknown",
    })

    result = run_verifier(tmp_path, report)
    assert result.returncode == 1
    assert "False positives: 1" in result.stdout
    assert "/api/v2/users/me (documented route)" in result.stdout


def test_correctly_classified_documented_route_is_not_false_positive(tmp_path):
    report = perfect_report()
    report["findings"].append(DOCUMENTED_ROUTE)

    result = run_verifier(tmp_path, report)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "False positives: 0" in result.stdout
    assert "RESULT: PASS" in result.stdout


def test_intentionally_imperfect_mock_fails_as_expected(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--discovery-output", str(MOCK),
            "--manifest", str(MANIFEST),
            "--skip-day11",
            "--out", str(tmp_path / "verification.json"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Endpoint recall: 85.7%" in result.stdout
    assert "Precision: 85.7%" in result.stdout
    assert "Classification errors: 0" in result.stdout
    assert "RESULT: FAIL" in result.stdout


def test_method_mismatch_does_not_count_as_ground_truth_match(tmp_path):
    report = perfect_report()
    target = next(
        item for item in report["findings"]
        if item["path"] == "/debug/dump-tokens"
    )
    target["method"] = "POST"

    result = run_verifier(tmp_path, report)
    assert result.returncode == 1
    assert "Endpoints found: 6/7" in result.stdout
    assert "False positives: 1" in result.stdout


def test_wrong_ground_truth_classification_fails(tmp_path):
    report = perfect_report()
    report["findings"][0]["classification"] = "unknown"

    result = run_verifier(tmp_path, report)
    assert result.returncode == 1
    assert "Classification errors: 1" in result.stdout
    assert "RESULT: FAIL" in result.stdout


def test_duplicate_finding_is_a_validation_error(tmp_path):
    report = perfect_report()
    report["findings"].append(dict(report["findings"][0]))

    result = run_verifier(tmp_path, report)
    assert result.returncode == 1
    assert "Validation errors: 1" in result.stdout
    assert "duplicate endpoint tuple" in result.stdout


def test_invalid_confidence_fails_validation(tmp_path):
    report = perfect_report()
    report["findings"][0]["confidence"] = 1.5

    result = run_verifier(tmp_path, report)
    assert result.returncode == 1
    assert "Validation errors: 1" in result.stdout
    assert "confidence must be a number" in result.stdout


def test_contract_documents_all_four_classifications():
    text = CONTRACT.read_text(encoding="utf-8")
    for classification in ("shadow", "zombie", "documented", "unknown"):
        assert f"`{classification}`" in text


def test_parameterized_order_route_matches_different_numeric_id(tmp_path):
    report = perfect_report()
    order_finding = next(
        item for item in report["findings"]
        if item["service"] == "order"
    )
    order_finding["path"] = "/api/v1/orders/101"

    result = run_verifier(tmp_path, report)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Endpoints found: 7/7" in result.stdout
    assert "Endpoint recall: 100.0%" in result.stdout
    assert "RESULT: PASS" in result.stdout


def test_parameterized_route_duplicate_ids_are_rejected(tmp_path):
    report = perfect_report()
    report["findings"].append(
        finding("order", "GET", "/api/v1/orders/101", "zombie")
    )

    result = run_verifier(tmp_path, report)
    assert result.returncode == 1
    assert "duplicate endpoint tuple" in result.stdout
    assert "RESULT: FAIL" in result.stdout

def test_json_report_contains_metrics_and_verdict(tmp_path):
    result = run_verifier(tmp_path, perfect_report())
    report_path = tmp_path / "verification.json"

    assert result.returncode == 0, result.stdout + result.stderr
    assert report_path.is_file()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["verdict"] == "PASS"
    assert report["exit_code"] == 0
    assert report["ground_truth_endpoints"] == 7
    assert report["matched_endpoints"] == 7
    assert report["recall"] == 1.0
    assert report["precision"] == 1.0
    assert report["missed_endpoints"] == []
    assert report["false_positives"] == []
    assert len(report["per_endpoint"]) == 7


def test_json_report_is_written_for_failed_discovery(tmp_path):
    empty_report = {
        "scan_timestamp": "2026-10-19T10:00:00Z",
        "findings": [],
    }
    result = run_verifier(tmp_path, empty_report)
    report_path = tmp_path / "verification.json"

    assert result.returncode == 1
    assert report_path.is_file()

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["verdict"] == "FAIL"
    assert report["exit_code"] == 1
    assert report["matched_endpoints"] == 0
    assert report["recall"] == 0.0
    assert len(report["missed_endpoints"]) == 7
