import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.pipeline.mock_ingestion_pipeline import record_capture
from scripts.pipeline.pipeline_audit import audit_pipeline


def write_jsonl(path, records):
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record) + "\n")


def test_all_requests_captured(tmp_path):
    sent = tmp_path / "sent.jsonl"
    captures = tmp_path / "captures.jsonl"

    write_jsonl(sent, [
        {"request_id": "r1", "method": "GET"},
        {"request_id": "r2", "method": "POST"},
    ])
    write_jsonl(captures, [
        {"request_id": "r1"},
        {"request_id": "r2"},
    ])

    report = audit_pipeline(sent, captures)

    assert report["capture_rate_percent"] == 100.0
    assert report["missing_request_ids"] == []


def test_missing_request_is_reported(tmp_path):
    sent = tmp_path / "sent.jsonl"
    captures = tmp_path / "captures.jsonl"

    write_jsonl(sent, [
        {"request_id": "r1"},
        {"request_id": "r2"},
    ])
    write_jsonl(captures, [{"request_id": "r1"}])

    report = audit_pipeline(sent, captures)

    assert report["capture_rate_percent"] == 50.0
    assert report["missing_request_ids"] == ["r2"]


def test_duplicate_capture_is_reported(tmp_path):
    sent = tmp_path / "sent.jsonl"
    captures = tmp_path / "captures.jsonl"

    write_jsonl(sent, [{"request_id": "r1"}])
    write_jsonl(captures, [
        {"request_id": "r1"},
        {"request_id": "r1"},
    ])

    report = audit_pipeline(sent, captures)

    assert report["capture_rate_percent"] == 100.0
    assert report["duplicate_capture_request_ids"] == ["r1"]


def test_mock_capture_writes_jsonl(tmp_path):
    captures = tmp_path / "captures.jsonl"

    record = record_capture(
        "r1",
        {"method": "GET", "path": "/health"},
        output_path=captures,
    )

    saved = json.loads(captures.read_text(encoding="utf-8"))

    assert saved["request_id"] == "r1"
    assert saved["capture_source"] == "mock"
    assert saved["method"] == "GET"
    assert record == saved


def test_malformed_jsonl_is_reported(tmp_path):
    sent = tmp_path / "sent.jsonl"
    captures = tmp_path / "captures.jsonl"

    sent.write_text('{"request_id":"r1"}\nnot-json\n', encoding="utf-8")
    write_jsonl(captures, [{"request_id": "r1"}])

    report = audit_pipeline(sent, captures)

    assert len(report["sent_parse_errors"]) == 1
    assert report["capture_rate_percent"] == 100.0


def run_audit_cli(sent, captures, output):
    import subprocess

    script = ROOT / "scripts" / "pipeline" / "pipeline_audit.py"
    return subprocess.run(
        [
            sys.executable,
            str(script),
            "--sent-source", str(sent),
            "--captures-source", str(captures),
            "--output", str(output),
        ],
        capture_output=True,
        text=True,
    )


def test_cli_empty_logs_fail_without_crashing(tmp_path):
    sent = tmp_path / "sent.jsonl"
    captures = tmp_path / "captures.jsonl"
    output = tmp_path / "report.json"
    sent.write_text("", encoding="utf-8")
    captures.write_text("", encoding="utf-8")

    result = run_audit_cli(sent, captures, output)
    report = json.loads(output.read_text(encoding="utf-8"))

    assert result.returncode == 1
    assert report["status"] == "FAIL"


def test_cli_missing_capture_returns_nonzero(tmp_path):
    sent = tmp_path / "sent.jsonl"
    captures = tmp_path / "captures.jsonl"
    output = tmp_path / "report.json"
    write_jsonl(sent, [{"request_id": "req-1"}])
    captures.write_text("", encoding="utf-8")

    result = run_audit_cli(sent, captures, output)
    report = json.loads(output.read_text(encoding="utf-8"))

    assert result.returncode == 1
    assert report["status"] == "FAIL"
    assert report["missing_request_ids"] == ["req-1"]


def test_cli_clean_capture_returns_zero(tmp_path):
    sent = tmp_path / "sent.jsonl"
    captures = tmp_path / "captures.jsonl"
    output = tmp_path / "report.json"
    write_jsonl(sent, [{"request_id": "req-1"}])
    write_jsonl(captures, [{"request_id": "req-1"}])

    result = run_audit_cli(sent, captures, output)
    report = json.loads(output.read_text(encoding="utf-8"))

    assert result.returncode == 0
    assert report["status"] == "PASS"
    assert report["capture_rate_percent"] == 100.0
