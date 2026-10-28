"""Unit tests for Day 9 horizontal privilege-escalation testing."""

import json
import sys
from pathlib import Path

import pytest
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.attacks.privesc_attack import (
    PrivEscAttack,
    TARGETS,
    VECTORS,
    classify_collection,
    classify_object,
)
from scripts.attacks.bola_attack import validate_base_url


class FakeResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("No JSON")
        return self._body


class FakeSession:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def _next(self, method, url, kwargs):
        self.calls.append((method, url, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected HTTP request")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def get(self, url, **kwargs):
        return self._next("GET", url, kwargs)

    def post(self, url, **kwargs):
        return self._next("POST", url, kwargs)


@pytest.mark.parametrize(
    ("status", "body", "attacker", "expected"),
    [
        (200, {"owner_id": 2}, 1, "ESCALATION_SUCCESS"),
        (200, {"owner_id": 1}, 1, "OWN_DATA_OR_IGNORED"),
        (401, {}, 1, "BLOCKED"),
        (403, {}, 1, "BLOCKED"),
        (404, {}, 1, "BLOCKED"),
        (500, {}, 1, "ERROR"),
        (200, {"unexpected": True}, 1, "ERROR"),
    ],
)
def test_object_verdicts(status, body, attacker, expected):
    assert classify_object(status, body, attacker, "owner_id") == expected


def test_order_owner_field_is_user_id():
    assert classify_object(
        200, {"user_id": 2}, 1, "user_id"
    ) == "ESCALATION_SUCCESS"


def test_collection_with_only_attacker_objects_is_ignored():
    target = TARGETS["billing"]
    body = {"invoices": [{"id": 5, "owner_id": 1}]}
    assert classify_collection(200, body, 1, target) == "OWN_DATA_OR_IGNORED"


def test_collection_with_foreign_object_is_escalation():
    target = TARGETS["billing"]
    body = {"invoices": [{"id": 5, "owner_id": 2}]}
    assert classify_collection(200, body, 1, target) == "ESCALATION_SUCCESS"


def test_collection_error_status_is_blocked():
    assert classify_collection(
        404, {}, 1, TARGETS["order"]
    ) == "BLOCKED"


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1",
        "http://example.com",
        "http://127.0.0.1:5004",
        "http://localhost/path",
    ],
)
def test_remote_or_nonstandard_target_rejected(url):
    with pytest.raises(ValueError):
        validate_base_url(url)


def test_body_tamper_is_logged_as_not_applicable(tmp_path):
    attack = PrivEscAttack(output_dir=tmp_path, session=FakeSession())
    try:
        result = attack._not_applicable("billing", 1, 2)
        log_path = attack.logger.path
    finally:
        attack.close()

    assert result["verdict"] == "NOT_APPLICABLE"
    assert result["http_status"] is None
    assert result["reason"]
    record = json.loads(Path(log_path).read_text().splitlines()[0])
    assert record["vector"] == "body_tamper"
    assert record["attack_type"] == "privesc_attack"


def test_matrix_runs_eight_cases_and_uses_victim_owned_ids(tmp_path):
    # Per target: victim collection, path attack, query tamper, header tamper.
    session = FakeSession([
        FakeResponse(200, {"orders": [{"id": 21, "user_id": 2}]}),
        FakeResponse(404, {"error": "not_found"}),
        FakeResponse(200, {"orders": [{"id": 11, "user_id": 1}]}),
        FakeResponse(200, {"orders": [{"id": 11, "user_id": 1}]}),
        FakeResponse(200, {"invoices": [{"id": 31, "owner_id": 2}]}),
        FakeResponse(200, {"id": 31, "owner_id": 2}),
        FakeResponse(200, {"invoices": [{"id": 12, "owner_id": 1}]}),
        FakeResponse(200, {"invoices": [{"id": 12, "owner_id": 1}]}),
    ])
    attack = PrivEscAttack(output_dir=tmp_path, session=session)

    try:
        results = attack.run_matrix(
            1,
            {"Authorization": "Bearer attacker"},
            2,
            {"Authorization": "Bearer victim"},
        )
        log_path = attack.logger.path
    finally:
        attack.close()

    assert len(results) == 8
    assert {r["vector"] for r in results} == set(VECTORS)
    assert {r["target"] for r in results} == {"order", "billing"}

    cells = {(r["target"], r["vector"]): r["verdict"] for r in results}
    assert cells[("order", "path_id")] == "BLOCKED"
    assert cells[("billing", "path_id")] == "ESCALATION_SUCCESS"
    assert cells[("order", "query_param")] == "OWN_DATA_OR_IGNORED"
    assert cells[("billing", "query_param")] == "OWN_DATA_OR_IGNORED"
    assert cells[("order", "header_x_user_id")] == "OWN_DATA_OR_IGNORED"
    assert cells[("billing", "header_x_user_id")] == "OWN_DATA_OR_IGNORED"
    assert cells[("order", "body_tamper")] == "NOT_APPLICABLE"
    assert cells[("billing", "body_tamper")] == "NOT_APPLICABLE"

    records = [json.loads(line) for line in Path(log_path).read_text().splitlines()]
    assert len(records) == 8
    assert [r["attack_sequence"] for r in records] == list(range(8))
    assert all(r["traffic_label"] == "ATTACK" for r in records)
    assert session.calls[1][1].endswith("/api/v2/orders/21")
    assert session.calls[5][1].endswith("/api/v2/billing/invoices/31")
