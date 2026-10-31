import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.simulation import multi_threat_simulation as sim


def test_jsonl_integrity_counts_valid_objects_and_bad_lines(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_text(
        '{"request_id":"r1"}\n'
        'not-json\n'
        '["not", "an", "object"]\n'
        '\n'
        '{"request_id":"r2"}\n',
        encoding="utf-8",
    )

    result = sim.jsonl_integrity(path)

    assert result["lines"] == 4
    assert result["valid_objects"] == 2
    assert len(result["errors"]) == 2


def test_jsonl_integrity_reports_missing_file(tmp_path):
    result = sim.jsonl_integrity(tmp_path / "missing.jsonl")

    assert result["lines"] == 0
    assert result["valid_objects"] == 0
    assert result["errors"] == ["file_missing"]


def test_jsonl_integrity_accepts_empty_file(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.touch()

    result = sim.jsonl_integrity(path)

    assert result["lines"] == 0
    assert result["valid_objects"] == 0
    assert result["errors"] == []


def test_scanner_outputs_are_preserved_and_restored(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    scan_log = logs / "discovery_scan.jsonl"
    report_file = logs / "discovery_report.json"
    scan_log.write_text("original scan\n", encoding="utf-8")
    report_file.write_text('{"original": true}\n', encoding="utf-8")

    monkeypatch.setattr(sim, "ROOT", tmp_path)
    evidence = tmp_path / "run"
    evidence.mkdir()

    saved = sim.preserve_scanner_outputs(evidence)

    scan_log.write_text("new scan\n", encoding="utf-8")
    report_file.write_text('{"new": true}\n', encoding="utf-8")

    sim.restore_scanner_outputs(saved)

    assert scan_log.read_text(encoding="utf-8") == "original scan\n"
    assert json.loads(report_file.read_text(encoding="utf-8")) == {
        "original": True
    }
    assert (evidence / "preexisting_scanner_outputs" /
            "discovery_scan.jsonl").exists()


def test_scanner_outputs_created_during_run_are_removed_on_restore(
    tmp_path, monkeypatch
):
    logs = tmp_path / "logs"
    logs.mkdir()
    monkeypatch.setattr(sim, "ROOT", tmp_path)

    evidence = tmp_path / "run"
    evidence.mkdir()
    saved = sim.preserve_scanner_outputs(evidence)

    (logs / "discovery_scan.jsonl").write_text(
        "temporary\n", encoding="utf-8"
    )
    (logs / "discovery_report.json").write_text(
        "{}\n", encoding="utf-8"
    )

    sim.restore_scanner_outputs(saved)

    assert not (logs / "discovery_scan.jsonl").exists()
    assert not (logs / "discovery_report.json").exists()


def test_health_snapshot_records_all_four_services(monkeypatch):
    def fake_get(url, timeout):
        response = Mock()
        response.status_code = 200 if "5003" not in url else 503
        return response

    monkeypatch.setattr(sim.requests, "get", fake_get)

    result = sim.health_snapshot()

    assert set(result["services"]) == {"auth", "user", "order", "billing"}
    assert result["services"]["auth"]["healthy"] is True
    assert result["services"]["order"]["healthy"] is False


def test_health_snapshot_records_connection_errors(monkeypatch):
    def fake_get(url, timeout):
        if "5002" in url:
            raise sim.requests.ConnectionError("service unavailable")
        response = Mock()
        response.status_code = 200
        return response

    monkeypatch.setattr(sim.requests, "get", fake_get)

    result = sim.health_snapshot()

    assert result["services"]["user"]["healthy"] is False
    assert "error" in result["services"]["user"]


def test_base_url_argument_rejects_non_local_target(tmp_path):
    with pytest.raises(SystemExit) as exc:
        import sys
        old_argv = sys.argv
        try:
            sys.argv = [
                "multi_threat_simulation.py",
                "--base-url", "http://example.com",
                "--output-root", str(tmp_path / "runs"),
            ]
            sim.main()
        finally:
            sys.argv = old_argv

    assert exc.value.code == 2
    assert not (tmp_path / "runs").exists()


def test_collect_billing_evidence_writes_valid_jsonl_and_separate_results(
    tmp_path, monkeypatch
):
    import subprocess

    events = [
        {
            "ts": "2026-10-20T12:00:00Z",
            "service": "billing-service",
            "message": "invoice accessed",
            "request_id": "req-1",
            "method": "GET",
            "path": "/api/v2/billing/invoices/1",
            "invoice_id": 1,
            "requester_id": 2,
            "owner_id": 1,
        },
        {
            "ts": "2026-10-20T12:00:00Z",
            "service": "billing-service",
            "message": "request",
            "request_id": "req-1",
            "method": "GET",
            "path": "/api/v2/billing/invoices/1",
            "status": 200,
        },
    ]
    stdout = "".join(
        "api-sentinel-billing  | " + json.dumps(event) + "\n"
        for event in events
    )

    monkeypatch.setattr(
        sim.subprocess, "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout, ""
        ),
    )

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    result = sim.collect_billing_evidence(
        run_dir, "2026-10-20T12:00:00+00:00"
    )

    lines = (run_dir / "billing_events.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()
    parsed = [json.loads(line) for line in lines]

    assert len(parsed) == 2
    assert parsed[0]["message"] == "invoice accessed"
    assert parsed[1]["message"] == "request"
    assert result["log_collection"] == "OK"
    assert result["detector"]["alerts_generated"] == 1
    assert result["status"] == "PASS"
    assert (run_dir / "billing_container_logs.txt").exists()
    assert (run_dir / "bola_detection_alerts.jsonl").exists()
    assert (run_dir / "bola_detection_summary.json").exists()


def test_collect_billing_evidence_fails_when_no_bola_alert_is_generated(
    tmp_path, monkeypatch
):
    import subprocess

    events = [
        {
            "service": "billing-service",
            "message": "invoice accessed",
            "request_id": "req-owner",
            "method": "GET",
            "path": "/api/v2/billing/invoices/1",
            "invoice_id": 1,
            "requester_id": 1,
            "owner_id": 1,
        },
        {
            "service": "billing-service",
            "message": "request",
            "request_id": "req-owner",
            "method": "GET",
            "path": "/api/v2/billing/invoices/1",
            "status": 200,
        },
    ]
    stdout = "".join(
        "api-sentinel-billing  | " + json.dumps(event) + "\n"
        for event in events
    )

    monkeypatch.setattr(
        sim.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout, ""
        ),
    )

    run_dir = tmp_path / "legitimate-only"
    run_dir.mkdir()

    result = sim.collect_billing_evidence(
        run_dir, "2026-10-20T12:00:00+00:00"
    )

    alerts_path = run_dir / "bola_detection_alerts.jsonl"

    assert result["log_collection"] == "OK"
    assert result["detector"]["alerts_generated"] == 0
    assert result["status"] == "FAIL"
    assert alerts_path.exists()
    assert alerts_path.read_text(encoding="utf-8") == ""
    assert (run_dir / "bola_detection_summary.json").exists()


def test_collect_billing_evidence_fails_when_log_collection_fails(
    tmp_path, monkeypatch
):
    import subprocess

    monkeypatch.setattr(
        sim.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 1, "", "simulated billing log collection failure"
        ),
    )

    run_dir = tmp_path / "collection-failure"
    run_dir.mkdir()

    result = sim.collect_billing_evidence(
        run_dir, "2026-10-20T12:00:00+00:00"
    )

    assert result["log_collection"] == "NOT_RUN"
    assert "billing_log_collection_exit_1" in result["errors"]
    assert result["detector"]["alerts_generated"] == 0
    assert result["status"] == "FAIL"
    assert (run_dir / "billing_events.jsonl").exists()
    assert (run_dir / "bola_detection_alerts.jsonl").exists()
    assert (run_dir / "bola_detection_summary.json").exists()
