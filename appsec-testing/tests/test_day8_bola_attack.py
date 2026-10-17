"""Unit tests for the Day 8 BOLA attack harness."""

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from scripts.attacks.bola_attack import (
    BOLAAttack,
    classify_invoice_response,
    print_summary,
    validate_base_url,
)


class FakeResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("No JSON body")
        return self._body


class FakeSession:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected GET request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected POST request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.parametrize(
    ("status", "body", "attacker_id", "expected"),
    [
        (200, {"owner_id": 2}, 1, "BOLA_SUCCESS"),
        (200, {"owner_id": 1}, 1, "OWN_DATA"),
        (401, {"error": "unauthorized"}, 1, "AUTH_FAILED"),
        (403, {"error": "forbidden"}, 1, "BLOCKED"),
        (404, {"error": "not_found"}, 1, "BLOCKED"),
        (200, {"invoice": 3}, 1, "ERROR"),
        (200, {"owner_id": "2"}, 1, "ERROR"),
        (500, {"error": "internal_error"}, 1, "ERROR"),
    ],
)
def test_invoice_verdict_classification(status, body, attacker_id, expected):
    assert classify_invoice_response(status, body, attacker_id) == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://127.0.0.1",
        "http://127.0.0.1:5004",
        "http://localhost/some/path",
        "http://user:pass@localhost",
    ],
)
def test_remote_or_nonstandard_targets_rejected(url):
    with pytest.raises(ValueError):
        validate_base_url(url)


@pytest.mark.parametrize("url", ["http://127.0.0.1", "http://localhost"])
def test_local_targets_accepted(url):
    assert validate_base_url(url) == url


def test_targeted_repeated_requests_log_verified_bola(tmp_path):
    session = FakeSession(
        [
            FakeResponse(200, {"owner_id": 2, "id": 3}),
            FakeResponse(200, {"owner_id": 2, "id": 3}),
        ]
    )

    attack = BOLAAttack(session=session, output_dir=tmp_path, delay=0)
    try:
        results = attack.run_targeted(
            attacker_id=1,
            headers={"Authorization": "Bearer test-token"},
            invoice_id=3,
            repeats=2,
        )
        log_path = attack.logger.path
    finally:
        attack.close()

    assert [item["label"] for item in results] == [
        "BOLA_SUCCESS", "BOLA_SUCCESS"
    ]
    assert all(item["actual_owner_id"] == 2 for item in results)
    assert all(item["cross_user_access"] is True for item in results)
    assert all(item["verdict"] == item["label"] for item in results)
    assert all(item["owner_id"] == item["actual_owner_id"] for item in results)
    assert all(item["status"] == item["http_status"] == 200 for item in results)

    records = [
        json.loads(line)
        for line in Path(log_path).read_text().splitlines()
    ]
    assert len(records) == 2
    assert [item["attack_sequence"] for item in records] == [0, 1]
    assert all(item["traffic_label"] == "ATTACK" for item in records)


def test_own_invoice_is_not_reported_as_bola(tmp_path):
    session = FakeSession([FakeResponse(200, {"owner_id": 1, "id": 3})])
    attack = BOLAAttack(session=session, output_dir=tmp_path, delay=0)

    try:
        result = attack.test_invoice(
            attacker_id=1,
            headers={"Authorization": "Bearer test-token"},
            invoice_id=3,
            mode="targeted",
        )
    finally:
        attack.close()

    assert result["label"] == "OWN_DATA"
    assert result["cross_user_access"] is False


def test_network_error_is_logged_as_error(tmp_path):
    import requests

    session = FakeSession([requests.Timeout("simulated timeout")])
    attack = BOLAAttack(session=session, output_dir=tmp_path, delay=0)

    try:
        result = attack.test_invoice(
            attacker_id=1,
            headers={"Authorization": "Bearer test-token"},
            invoice_id=3,
            mode="targeted",
        )
    finally:
        attack.close()

    assert result["label"] == "ERROR"
    assert result["http_status"] is None
    assert result["error"] == "Timeout"

def test_sweep_summary_reports_cross_user_invoices(capsys):
    results = [
        {
            "label": "BOLA_SUCCESS",
            "invoice_id": 3,
            "actual_owner_id": 2,
            "cross_user_access": True,
        },
        {
            "label": "OWN_DATA",
            "invoice_id": 1,
            "actual_owner_id": 1,
            "cross_user_access": False,
        },
        {
            "label": "BLOCKED",
            "invoice_id": 999,
            "actual_owner_id": None,
            "cross_user_access": False,
        },
    ]

    print_summary(results, "sweep")
    output = capsys.readouterr().out

    assert "Requests tested: 3" in output
    assert "Invoices compromised (belonging to OTHER users): 1" in output
    assert "Invoice 3 (owner ID 2)" in output

