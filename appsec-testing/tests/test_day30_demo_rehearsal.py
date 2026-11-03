import json
import sys
import time
from pathlib import Path

import pytest

APPSEC_ROOT = Path(__file__).resolve().parents[1]
if str(APPSEC_ROOT) not in sys.path:
    sys.path.insert(0, str(APPSEC_ROOT))

from scripts.demo.demo_rehearsal import (
    SEGMENT_BUDGETS,
    extract_path,
    read_json,
    read_jsonl,
    segment_record,
    service_ports,
    write_json,
)


def test_service_ports_use_rehearsal_defaults():
    ports = service_ports({})
    assert ports == {
        "auth": 5101,
        "user": 5102,
        "order": 5103,
        "billing": 5104,
    }


def test_service_ports_accept_explicit_overrides():
    ports = service_ports({
        "AUTH_SERVICE_PORT": "6101",
        "USER_SERVICE_PORT": "6102",
        "ORDER_SERVICE_PORT": "6103",
        "BILLING_SERVICE_PORT": "6104",
    })
    assert ports["auth"] == 6101
    assert ports["billing"] == 6104


@pytest.mark.parametrize("value", ["abc", "0", "65536", "-1"])
def test_service_ports_reject_invalid_values(value):
    with pytest.raises(ValueError):
        service_ports({"AUTH_SERVICE_PORT": value})


def test_read_jsonl_reads_structured_attack_records(tmp_path):
    path = tmp_path / "bola_attack.jsonl"
    path.write_text(
        '{"label":"BOLA_SUCCESS","cross_user_access":true}\n'
        '{"label":"OWN_DATA","cross_user_access":false}\n',
        encoding="utf-8",
    )

    records = read_jsonl(path)

    compromised = [
        row for row in records
        if row.get("label") == "BOLA_SUCCESS"
        and row.get("cross_user_access") is True
    ]
    assert len(records) == 2
    assert len(compromised) == 1


def test_read_jsonl_rejects_malformed_records(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"valid":true}\nnot-json\n', encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSONL"):
        read_jsonl(path)


def test_read_json_rejects_non_object_json(tmp_path):
    path = tmp_path / "array.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON object"):
        read_json(path)


def test_write_json_creates_parent_and_round_trips(tmp_path):
    path = tmp_path / "nested" / "report.json"
    expected = {"overall": "PASS", "count": 3}

    write_json(path, expected)

    assert json.loads(path.read_text(encoding="utf-8")) == expected
    assert not path.with_suffix(".json.tmp").exists()


def test_extract_path_reads_day20_report_message(tmp_path):
    report = tmp_path / "fail_open_report_example.json"
    output = f"some output\nReport written to: {report}\n"

    assert extract_path(output, r"Report written to:\s*(.+)") == report


def test_extract_path_returns_none_when_missing():
    assert extract_path("no report path here", r"Report written to:\s*(.+)") is None


def test_segment_record_applies_time_budget():
    result = segment_record(
        "platform_health",
        {"status": "PASS"},
        time.monotonic() - 0.1,
    )

    assert result["budget_seconds"] == SEGMENT_BUDGETS["platform_health"]
    assert result["within_budget"] is True


def test_segment_budget_is_twelve_minutes_with_buffer():
    assert sum(SEGMENT_BUDGETS.values()) == 630
    assert 720 - sum(SEGMENT_BUDGETS.values()) == 90


def test_health_segment_exposes_status_for_summary(tmp_path, monkeypatch):
    from scripts.demo import demo_rehearsal

    monkeypatch.setattr(
        demo_rehearsal,
        "check_health",
        lambda env: {
            "overall": "PASS",
            "services": {},
        },
    )

    rehearsal = demo_rehearsal.Rehearsal(1, tmp_path / "run", {})
    assert rehearsal.segment_health() is True
    assert rehearsal.segments["platform_health"]["status"] == "PASS"


def test_manual_bola_segment_exposes_status_for_summary(tmp_path, monkeypatch):
    from scripts.demo import demo_rehearsal

    def fake_run_command(command, *, env, timeout, cwd=None, output_path):
        evidence_dir = output_path.parent / output_path.stem
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "bola_attack.jsonl").write_text(
            '{"label":"BOLA_SUCCESS","cross_user_access":true}\n',
            encoding="utf-8",
        )
        return {
            "status": "PASS",
            "exit_code": 0,
            "duration_seconds": 0.01,
            "command": command,
            "output_file": str(output_path),
            "output_tail": "",
        }

    monkeypatch.setattr(demo_rehearsal, "run_command", fake_run_command)

    rehearsal = demo_rehearsal.Rehearsal(1, tmp_path / "run", {})
    result = rehearsal.segment_manual_bola()

    assert result["status"] == "PASS"
    assert rehearsal.segments["manual_bola"]["status"] == "PASS"
