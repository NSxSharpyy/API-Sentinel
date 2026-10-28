import json
import io

from scripts.recon.endpoint_scanner import (
    phase3_method_enumeration,
)


class FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class FakeSession:
    def __init__(self, statuses):
        self.statuses = statuses

    def request(self, method, url, timeout):
        return FakeResponse(self.statuses[method])


def test_method_enumeration_classifies_http_responses():
    statuses = {
        "GET": 200,
        "POST": 401,
        "PUT": 405,
        "DELETE": 500,
    }
    session = FakeSession(statuses)

    log = io.StringIO()
    results = phase3_method_enumeration(
        session,
        log,
        {"auth": {"/debug/dump-tokens"}},
        delay=0,
    )

    endpoint = results["auth/debug/dump-tokens"]

    assert endpoint["GET"]["classification"] == "success_response"
    assert endpoint["POST"]["classification"] == "authentication_required"
    assert endpoint["PUT"]["classification"] == "method_not_allowed"
    assert endpoint["DELETE"]["classification"] == "server_error"

    records = [
        json.loads(line)
        for line in log.getvalue().splitlines()
    ]
    assert len(records) == 4
    assert all("classification" in record for record in records)
