"""Day 25 tests: synthetic PII leakage scanner."""

import importlib.util
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest


APPSEC_ROOT = Path(__file__).resolve().parents[1]
SCANNER_PATH = (
    APPSEC_ROOT / "scripts" / "compliance" / "pii_leakage_scanner.py"
)

spec = importlib.util.spec_from_file_location("day25_scanner", SCANNER_PATH)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


def test_fixture_contains_50_unique_payloads():
    fixture, payloads = scanner.load_fixture()

    assert fixture["total_payloads"] == 50
    assert len(payloads) == 50
    assert len({item["marker"] for item in payloads}) == 50
    assert len({item["value"] for item in payloads}) == 50
    assert set(Counter(item["category"] for item in payloads).values()) == {10}


def test_fixture_payloads_have_required_fields():
    _, payloads = scanner.load_fixture()

    for item in payloads:
        assert set(item) == {"category", "marker", "value"}
        assert item["category"]
        assert item["marker"]
        assert item["value"]


@pytest.mark.parametrize(
    "fixture_data",
    [
        {"total_payloads": 1, "categories": {"emails": [
            {"marker": "", "value": "test@example.test"}
        ]}},
        {"total_payloads": 1, "categories": {"emails": [
            {"marker": "EMAIL_1", "value": ""}
        ]}},
        {"total_payloads": 2, "categories": {"emails": [
            {"marker": "EMAIL_1", "value": "test@example.test"}
        ]}},
        {"total_payloads": 2, "categories": {"emails": [
            {"marker": "EMAIL_1", "value": "same"},
            {"marker": "EMAIL_2", "value": "same"},
        ]}},
        {"total_payloads": 2, "categories": {"emails": [
            {"marker": "EMAIL_1", "value": "one"},
            {"marker": "EMAIL_1", "value": "two"},
        ]}},
    ],
)
def test_fixture_rejects_invalid_payloads(tmp_path, monkeypatch, fixture_data):
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(json.dumps(fixture_data), encoding="utf-8")
    monkeypatch.setattr(scanner, "FIXTURE_PATH", fixture_path)

    with pytest.raises(ValueError):
        scanner.load_fixture()


def test_scan_text_returns_redacted_findings():
    secret_value = "synthetic-private-value-123"
    payloads = [{
        "category": "emails",
        "marker": "EMAIL_TEST_1",
        "value": secret_value,
    }]

    findings = scanner.scan_text(
        f"response={secret_value}; again={secret_value}",
        payloads,
        "test_response",
    )

    assert findings == [{
        "location": "test_response",
        "category": "emails",
        "marker": "EMAIL_TEST_1",
        "match_count": 2,
    }]
    assert secret_value not in json.dumps(findings)


def test_scan_text_returns_empty_list_when_no_match():
    payloads = [{
        "category": "emails",
        "marker": "EMAIL_TEST_1",
        "value": "synthetic-private-value",
    }]

    assert scanner.scan_text(
        "no matching data here", payloads, "test"
    ) == []


def test_scan_text_handles_non_string_content():
    payloads = [{
        "category": "emails",
        "marker": "EMAIL_TEST_1",
        "value": "synthetic@example.test",
    }]

    findings = scanner.scan_text(
        {"email": "synthetic@example.test"},
        payloads,
        "json_response",
    )

    assert len(findings) == 1
    assert findings[0]["match_count"] == 1


def test_inspect_logs_checks_each_service(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(
            returncode=0,
            stdout="ordinary service log line\n",
            stderr="",
        )

    monkeypatch.setattr(scanner.subprocess, "run", fake_run)

    result, findings = scanner.inspect_logs([])

    assert result["command_succeeded"] is True
    assert result["lines_inspected"] == 4
    assert result["payload_matches"] == 0
    assert result["services_inspected"] == [
        "auth", "user", "order", "billing"
    ]
    assert result["line_limit_per_service"] == 1000
    assert len(calls) == 4
    assert all(call[:3] == ["docker", "logs", "--tail"] for call in calls)
    assert findings == []


def test_inspect_logs_detects_payload_without_returning_value(monkeypatch):
    secret_value = "synthetic-log-secret-987"
    payloads = [{
        "category": "bearer_tokens",
        "marker": "TOKEN_TEST_1",
        "value": secret_value,
    }]

    def fake_run(command, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=f"request contained {secret_value}\n",
            stderr="",
        )

    monkeypatch.setattr(scanner.subprocess, "run", fake_run)

    result, findings = scanner.inspect_logs(payloads)

    assert result["payload_matches"] == 1
    assert findings[0]["marker"] == "TOKEN_TEST_1"
    assert secret_value not in json.dumps(findings)


def test_inspect_logs_fails_if_docker_logs_fails(monkeypatch):
    def fake_run(command, **kwargs):
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    monkeypatch.setattr(scanner.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="Container log inspection failed"):
        scanner.inspect_logs([])


def test_inspect_logs_uses_bounded_tail_and_timeout(monkeypatch):
    captured = []

    def fake_run(command, **kwargs):
        captured.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(scanner.subprocess, "run", fake_run)
    scanner.inspect_logs([])

    assert len(captured) == 4
    for command, kwargs in captured:
        assert command[2:4] == ["--tail", "1000"]
        assert kwargs["timeout"] == 30
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True


def test_write_report_writes_valid_json_atomically(tmp_path, monkeypatch):
    report_path = tmp_path / "nested" / "report.json"
    monkeypatch.setattr(scanner, "REPORT_PATH", report_path)

    report = {"status": "COMPLETE", "finding_count": 0}
    scanner.write_report(report)

    assert json.loads(report_path.read_text()) == report
    assert not report_path.with_suffix(".json.tmp").exists()


def test_cleanup_is_attempted_if_insert_command_times_out(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(scanner, "APPSEC_ROOT", tmp_path)
    report_path = tmp_path / "logs" / "report.json"
    monkeypatch.setattr(scanner, "REPORT_PATH", report_path)
    monkeypatch.setattr(scanner, "preflight", lambda: {
        "customer_id": 0,
        "username": 0,
        "order_id": 0,
        "invoice_id": 0,
    })

    def simulated_insert_timeout(payloads):
        # Simulate a Docker timeout after the database may have committed.
        raise scanner.subprocess.TimeoutExpired(
            cmd="docker exec", timeout=120
        )

    cleanup_calls = []

    def simulated_cleanup():
        cleanup_calls.append(True)
        return {
            "deleted": {"customer": 1, "order": 1, "invoice": 1},
            "remaining": {"customer": 0, "order": 0, "invoice": 0},
            "complete": True,
        }

    monkeypatch.setattr(
        scanner, "insert_audit_records", simulated_insert_timeout
    )
    monkeypatch.setattr(
        scanner, "cleanup_audit_records", simulated_cleanup
    )

    result = scanner.run_audit()

    assert result == 1
    assert cleanup_calls == [True]

    report = json.loads(report_path.read_text())
    assert report["status"] == "INCOMPLETE"
    assert report["error_type"] == "TimeoutExpired"
    assert report["cleanup"]["attempted"] is True
    assert report["cleanup"]["complete"] is True
