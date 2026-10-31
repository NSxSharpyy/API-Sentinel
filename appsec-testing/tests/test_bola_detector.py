import json
from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.detection.bola_detector import analyze_event, detect_file


def access_event(**overrides):
    record = {
        "message": "invoice accessed",
        "request_id": "req-123",
        "method": "GET",
        "path": "/api/v2/billing/invoices/12",
        "invoice_id": 12,
        "requester_id": 1,
        "owner_id": 2,
        "cross_user_access": False,
        "verdict": "OWN_DATA",
    }
    record.update(overrides)
    return record


def completion_event(**overrides):
    record = {
        "message": "request",
        "request_id": "req-123",
        "method": "GET",
        "path": "/api/v2/billing/invoices/12",
        "status": 200,
    }
    record.update(overrides)
    return record


def test_cross_owner_success_generates_independent_alert():
    alert = analyze_event(access_event(), [completion_event()])
    assert alert is not None
    assert alert["rule_id"] == "BOLA-LOG-001"
    assert alert["severity"] == "HIGH"
    assert alert["requester_id"] == 1
    assert alert["owner_id"] == 2
    assert alert["invoice_id"] == 12
    assert alert["request_id"] == "req-123"


def test_compatibility_route_is_supported():
    access = access_event(
        message="INTENTIONAL BOLA accessed",
        path="/api/v1/billing/12",
        invoice_id=None,
        billing_id=12,
    )
    access.pop("invoice_id")
    completion = completion_event(path="/api/v1/billing/12")
    alert = analyze_event(access, [completion])
    assert alert is not None
    assert alert["invoice_id"] == 12


def test_owner_access_does_not_generate_alert():
    assert analyze_event(
        access_event(requester_id=2, owner_id=2), [completion_event()]
    ) is None


def test_non_access_event_is_ignored():
    assert analyze_event(
        access_event(message="request"), [completion_event()]
    ) is None


def test_missing_matching_request_fails_closed():
    assert analyze_event(access_event(), []) is None


def test_mismatched_request_id_fails_closed():
    assert analyze_event(
        access_event(), [completion_event(request_id="other")]
    ) is None


def test_mismatched_path_fails_closed():
    assert analyze_event(
        access_event(), [completion_event(path="/health")]
    ) is None


@pytest.mark.parametrize("status", [301, 400, 403, 404, 500])
def test_non_successful_response_does_not_alert(status):
    assert analyze_event(
        access_event(), [completion_event(status=status)]
    ) is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"request_id": None},
        {"method": ""},
        {"path": "relative/path"},
        {"requester_id": None},
        {"owner_id": "2"},
        {"invoice_id": True},
        {"requester_id": 0},
    ],
)
def test_invalid_access_evidence_is_rejected(overrides):
    with pytest.raises(ValueError):
        analyze_event(access_event(**overrides), [completion_event()])


def test_invalid_correlated_status_is_rejected():
    with pytest.raises(ValueError):
        analyze_event(
            access_event(), [completion_event(status="200")]
        )


def test_jsonl_detection_correlates_records_and_writes_only_alerts(tmp_path):
    source = tmp_path / "billing_events.jsonl"
    output = tmp_path / "bola_detection_alerts.jsonl"
    source.write_text(
        json.dumps(access_event()) + "\n"
        + json.dumps(completion_event()) + "\n"
        + json.dumps(access_event(
            request_id="req-owner",
            requester_id=2,
            owner_id=2,
        )) + "\n"
        + json.dumps(completion_event(
            request_id="req-owner",
        )) + "\n"
        + "not-json\n",
        encoding="utf-8",
    )

    summary = detect_file(source, output)
    alerts = [
        json.loads(line)
        for line in output.read_text(encoding="utf-8").splitlines()
    ]

    assert summary["events_read"] == 5
    assert summary["events_processed"] == 4
    assert summary["alerts_generated"] == 1
    assert summary["invalid_events"] == 1
    assert summary["access_events"] == 2
    assert summary["correlated_access_events"] == 2
    assert len(alerts) == 1
    assert alerts[0]["requester_id"] != alerts[0]["owner_id"]


def test_missing_input_file_is_reported(tmp_path):
    summary = detect_file(
        tmp_path / "missing.jsonl",
        tmp_path / "alerts.jsonl",
    )
    assert summary["errors"] == ["input_file_missing"]
    assert summary["alerts_generated"] == 0
