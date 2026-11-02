"""Tests for the Day 26 OWASP regression runner."""

import importlib.util
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "compliance"
    / "owasp_top10_regression.py"
)

SPEC = importlib.util.spec_from_file_location(
    "owasp_top10_regression", SCRIPT
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def test_taxonomy_contains_exactly_ten_unique_owasp_categories():
    categories = runner.CATEGORY_DEFINITIONS

    assert len(categories) == 10
    assert [item["id"] for item in categories] == [
        f"API{i}" for i in range(1, 11)
    ]
    assert len({item["name"] for item in categories}) == 10


def test_taxonomy_uses_correct_owasp_2023_category_names():
    expected = [
        "Broken Object Level Authorization",
        "Broken Authentication",
        "Broken Object Property Level Authorization",
        "Unrestricted Resource Consumption",
        "Broken Function Level Authorization",
        "Unrestricted Access to Sensitive Business Flows",
        "Server Side Request Forgery",
        "Security Misconfiguration",
        "Improper Inventory Management",
        "Unsafe Consumption of APIs",
    ]

    assert [item["name"] for item in runner.CATEGORY_DEFINITIONS] == expected


def test_day24_file_overwriting_cli_test_is_deselected():
    assert runner.DESELECTED_TESTS == [
        "tests/test_day24_pii_payloads.py::test_cli_run_produces_expected_output_file"
    ]


def test_all_expected_existing_test_modules_are_selected():
    assert len(runner.TEST_MODULES) == 9

    for module in runner.TEST_MODULES:
        assert (runner.APPSEC_ROOT / module).is_file(), module


def test_junit_parser_counts_pass_fail_error_and_skip(tmp_path):
    report = tmp_path / "results.xml"
    report.write_text(
        """<?xml version="1.0"?>
        <testsuite tests="4" failures="1" errors="1" skipped="1">
          <testcase classname="tests.test_day2_auth_bola" name="passed"/>
          <testcase classname="tests.test_day2_auth_bola" name="failed">
            <failure message="assertion failed"/>
          </testcase>
          <testcase classname="tests.test_day2_auth_bola" name="errored">
            <error message="exception"/>
          </testcase>
          <testcase classname="tests.test_day2_auth_bola" name="skipped">
            <skipped message="not available"/>
          </testcase>
        </testsuite>
        """,
        encoding="utf-8",
    )

    parsed = runner.parse_junit(report)

    assert parsed["test_day2_auth_bola.py"] == {
        "passed": 1,
        "failed": 1,
        "errors": 1,
        "skipped": 1,
    }


def test_coverage_score_excludes_out_of_scope_categories():
    categories = [
        {"status": "COVERED"},
        {"status": "PARTIAL"},
        {"status": "NOT_RUN"},
        {"status": "OUT_OF_SCOPE"},
    ]

    result = runner.calculate_coverage(categories)

    assert result["in_scope_categories"] == 3
    assert result["out_of_scope_categories"] == 1
    assert result["weighted_score"] == 1.5
    assert result["maximum_score"] == 3
    assert result["percentage"] == 50.0


def test_coverage_score_is_zero_when_all_in_scope_categories_are_unrun():
    result = runner.calculate_coverage([
        {"status": "NOT_RUN"},
        {"status": "BLOCKED"},
        {"status": "OUT_OF_SCOPE"},
    ])

    assert result["percentage"] == 0.0
    assert result["not_run"] == 1
    assert result["blocked"] == 1


def test_category_evaluation_marks_module_failure_as_failed():
    results = {
        "modules": {
            "test_day10_shadow_zombie.py": {
                "passed": 10,
                "failed": 1,
                "errors": 0,
                "skipped": 0,
            }
        }
    }

    categories = runner.evaluate_categories(results, {})
    api5 = next(item for item in categories if item["id"] == "API5")

    assert api5["status"] == "FAILED"

def test_api1_bola_regression_is_marked_failed():
    results = {
        "modules": {
            "test_day2_auth_bola.py": {
                "passed": 10,
                "failed": 0,
                "errors": 0,
                "skipped": 0,
            },
            "test_day8_bola_attack.py": {
                "passed": 9,
                "failed": 1,
                "errors": 0,
                "skipped": 0,
            },
            "test_day10_shadow_zombie.py": {
                "passed": 10,
                "failed": 0,
                "errors": 0,
                "skipped": 0,
            },
        }
    }

    categories = runner.evaluate_categories(results, {})
    api1 = next(item for item in categories if item["id"] == "API1")

    assert api1["status"] == "FAILED"
    assert api1["test_execution_status"] == "FAILED"

def test_category_evaluation_marks_missing_test_results_as_blocked():
    categories = runner.evaluate_categories({"modules": {}}, {})
    api1 = next(item for item in categories if item["id"] == "API1")

    assert api1["status"] == "BLOCKED"


def test_out_of_scope_categories_are_not_marked_as_passed():
    categories = runner.evaluate_categories({"modules": {}}, {})

    for category_id in ("API6", "API7", "API10"):
        item = next(
            category for category in categories
            if category["id"] == category_id
        )
        assert item["status"] == "OUT_OF_SCOPE"


def test_historical_evidence_missing_file_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(
        runner,
        "EVIDENCE_PATHS",
        {"missing_report": tmp_path / "missing.json"},
    )

    evidence = runner.load_historical_evidence()

    assert evidence["missing_report"]["available"] is False
    assert evidence["missing_report"]["status"] == "MISSING"


def test_historical_evidence_malformed_json_is_reported(tmp_path, monkeypatch):
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not valid json", encoding="utf-8")

    monkeypatch.setattr(
        runner,
        "EVIDENCE_PATHS",
        {"bad_report": malformed},
    )

    evidence = runner.load_historical_evidence()

    assert evidence["bad_report"]["status"] == "UNREADABLE"
    assert evidence["bad_report"]["error_type"] == "JSONDecodeError"


def test_report_is_written_as_valid_json_atomically(tmp_path):
    destination = tmp_path / "nested" / "report.json"
    report = {"overall": "PARTIAL", "day": 26}

    runner.write_report(report, destination)

    assert json.loads(destination.read_text(encoding="utf-8")) == report
    assert not destination.with_suffix(".json.tmp").exists()


def test_junit_parser_rejects_malformed_xml(tmp_path):
    report = tmp_path / "broken.xml"
    report.write_text("<testsuite>", encoding="utf-8")

    with pytest.raises(ET.ParseError):
        runner.parse_junit(report)


def test_category_evaluation_preserves_skipped_test_status():
    results = {
        "modules": {
            "test_day10_shadow_zombie.py": {
                "passed": 10,
                "failed": 0,
                "errors": 0,
                "skipped": 2,
            }
        }
    }

    categories = runner.evaluate_categories(results, {})
    api5 = next(item for item in categories if item["id"] == "API5")

    assert api5["status"] == "COVERED"
    assert api5["test_execution_status"] == "PASS_WITH_SKIPS"
    assert api5["test_modules"]["test_day10_shadow_zombie.py"]["skipped"] == 2


def test_category_is_blocked_when_required_historical_evidence_is_missing():
    results = {
        "modules": {
            "test_day25_pii_leakage.py": {
                "passed": 13,
                "failed": 0,
                "errors": 0,
                "skipped": 0,
            }
        }
    }

    categories = runner.evaluate_categories(results, {
        "day25_pii": {"status": "MISSING", "available": False}
    })
    api3 = next(item for item in categories if item["id"] == "API3")

    assert api3["status"] == "BLOCKED"
    assert "day25_pii" in api3["limitations"][-1]


def test_successful_test_execution_does_not_imply_full_coverage():
    categories = [
        {"status": "COVERED"},
        {"status": "PARTIAL"},
        {"status": "OUT_OF_SCOPE"},
    ]

    coverage = runner.calculate_coverage(categories)

    assert coverage["percentage"] == 75.0
    assert not all(item["status"] == "COVERED" for item in categories)



def test_live_orchestration_blocks_all_scans_when_health_fails(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(runner, "LOG_ROOT", tmp_path)
    monkeypatch.setattr(
        runner,
        "check_live_health",
        lambda: {
            "status": "BLOCKED",
            "services": {
                "auth": {"healthy": True},
                "user": {"healthy": False},
                "order": {"healthy": True},
                "billing": {"healthy": True},
            },
        },
    )

    def unexpected_scan(*args, **kwargs):
        pytest.fail("A live scan ran despite failed health preflight")

    monkeypatch.setattr(runner, "run_live_command", unexpected_scan)

    result = runner.run_live_orchestration(timeout=10)

    assert result["status"] == "BLOCKED"
    assert "skipped" in result["reason"]
    assert result["scans"] == {}
    evidence_path = Path(result["evidence_directory"])
    if not evidence_path.is_absolute():
        evidence_path = runner.APPSEC_ROOT / evidence_path
    assert evidence_path.is_dir()
    assert tmp_path in evidence_path.parents


def test_live_orchestration_records_isolated_evidence_and_observations(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(runner, "LOG_ROOT", tmp_path)
    monkeypatch.setattr(
        runner,
        "check_live_health",
        lambda: {
            "status": "PASS",
            "services": {
                service: {"healthy": True}
                for service in runner.LIVE_SERVICES
            },
        },
    )
    monkeypatch.setattr(
        runner,
        "run_api5_observation",
        lambda: {
            "observed": True,
            "http_status": 200,
            "response": '{"status":"cache reset"}',
        },
    )

    executed = []

    def fake_command(name, command, evidence_dir, timeout):
        executed.append(name)

        if name in (
            "day08_bola_sweep",
            "day17_credential_stuffing",
            "day17_invalid_login_flood",
        ):
            output_dir = Path(command[command.index("--output-dir") + 1])
            output_dir.mkdir(parents=True, exist_ok=True)

            if name == "day08_bola_sweep":
                records = [
                    {
                        "label": "BOLA_SUCCESS",
                        "status_code": 200,
                        "cross_user_access": True,
                    },
                    {
                        "label": "BOLA_SUCCESS",
                        "status_code": 200,
                        "cross_user_access": False,
                    },
                    {
                        "label": "BOLA_SUCCESS",
                        "status_code": 200,
                    },
                    {
                        "label": "BLOCKED",
                        "status_code": 403,
                        "cross_user_access": True,
                    },
                ]

                (output_dir / "bola_attack.jsonl").write_text(
                    "".join(json.dumps(item) + "\n" for item in records),
                    encoding="utf-8",
                )
            else:
                (output_dir / "bot_traffic.jsonl").write_text(
                    json.dumps({
                        "label": "BOLA_SUCCESS",
                        "status_code": 429,
                    }) + "\n",
                    encoding="utf-8",
                )
        elif name == "day11_safe_endpoint_inventory":
            output_dir = Path(command[command.index("--output-dir") + 1])
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "discovery_report.json").write_text(
                json.dumps({
                    "total_discovered": 3,
                    "endpoint_classification": {
                        "auth": {
                            "/api/v2/login": "documented_v2",
                            "/api/v1/legacy": "zombie_candidate",
                        },
                        "billing": {
                            "/internal/debug": "shadow_candidate",
                        },
                    },
                }),
                encoding="utf-8",
            )

        elif name == "day25_pii_audit":
            report_path = Path(command[command.index("--report") + 1])
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(
                json.dumps({
                    "status": "COMPLETE",
                    "finding_count": 2,
                    "cleanup": {
                        "attempted": True,
                        "complete": True,
                    },
                }),
                encoding="utf-8",
            )

        return {
            "name": name,
            "status": "COMPLETED",
            "exit_code": 0,
        }

    monkeypatch.setattr(runner, "run_live_command", fake_command)

    result = runner.run_live_orchestration(timeout=10)

    assert result["status"] == "COMPLETED"
    assert len(executed) == 5
    assert len(set(executed)) == 5

    bola = result["observations"]["day08_bola"]
    assert bola["labels"]["BOLA_SUCCESS"] == 3
    assert bola["labels"]["BLOCKED"] == 1
    assert bola["cross_user_bola_successes"] == 1

    inventory = result["observations"]["day11_inventory"]
    assert inventory["total_discovered"] == 3
    assert inventory["classification_counts"] == {
        "documented_v2": 1,
        "zombie_candidate": 1,
        "shadow_candidate": 1,
    }
    assert inventory["undocumented_or_legacy_candidates"] == 2

    assert result["observations"]["day25_pii"]["cleanup_complete"] is True
    assert result["observations"]["api5_admin_route"]["observed"] is True


def test_live_orchestration_fails_closed_when_day25_report_missing(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(runner, "LOG_ROOT", tmp_path)
    monkeypatch.setattr(
        runner,
        "check_live_health",
        lambda: {
            "status": "PASS",
            "services": {
                service: {"healthy": True}
                for service in runner.LIVE_SERVICES
            },
        },
    )
    monkeypatch.setattr(runner, "run_api5_observation", lambda: {
        "observed": False,
        "http_status": 404,
    })

    def fake_command(name, command, evidence_dir, timeout):
        return {
            "name": name,
            "status": "COMPLETED",
            "exit_code": 0,
        }

    monkeypatch.setattr(runner, "run_live_command", fake_command)

    result = runner.run_live_orchestration(timeout=10)

    assert result["status"] == "FAILED"
    assert result["observations"]["day25_pii"]["report_available"] is False
    assert "cleanup" in result["reason"].lower()


def test_jsonl_summary_counts_labels_statuses_and_malformed_lines(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(
        json.dumps({"label": "BLOCKED", "status_code": 429}) + "\n"
        + "{invalid json\n"
        + json.dumps({"label": "OWN_DATA", "status_code": 200}) + "\n",
        encoding="utf-8",
    )

    result = runner.read_jsonl_summary(path)

    assert result["available"] is True
    assert result["records"] == 2
    assert result["errors"] == 1
    assert result["labels"] == {"BLOCKED": 1, "OWN_DATA": 1}
    assert result["http_statuses"] == {"429": 1, "200": 1}

def test_jsonl_summary_counts_only_verified_cross_user_bola(tmp_path):
    path = tmp_path / "bola.jsonl"
    records = [
        {"label": "BOLA_SUCCESS", "cross_user_access": True},
        {"label": "BOLA_SUCCESS", "cross_user_access": False},
        {"label": "BOLA_SUCCESS"},
        {"label": "BLOCKED", "cross_user_access": True},
    ]
    path.write_text(
        "".join(json.dumps(item) + "\n" for item in records),
        encoding="utf-8",
    )

    result = runner.read_jsonl_summary(path)

    assert result["labels"]["BOLA_SUCCESS"] == 3
    assert result["cross_user_bola_successes"] == 1

def test_live_evidence_directory_does_not_overwrite_existing_directory(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(runner, "LOG_ROOT", tmp_path)
    class FixedDateTime:
        @staticmethod
        def now(tz=None):
            return __import__("datetime").datetime(
                2026, 11, 1, tzinfo=__import__("datetime").timezone.utc
            )

    monkeypatch.setattr(runner, "datetime", FixedDateTime)

    first = runner.create_live_evidence_dir()
    second = runner.create_live_evidence_dir()

    assert first != second
    assert first.is_dir()
    assert second.is_dir()
