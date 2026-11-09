import json
import io

from scripts.recon.endpoint_scanner import (
    phase3_method_enumeration,
    build_verifier_findings,
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


def test_build_verifier_findings_keeps_heuristic_candidates_unknown():
    report = {
        "endpoint_classification": {
            "auth": {
                "/debug/dump-tokens": "shadow_candidate",
                "/api/v1/login-status": "zombie_candidate",
            }
        },
        "methods_by_endpoint": {
            "auth/debug/dump-tokens": {
                "GET": {
                    "status": 200,
                    "classification": "success_response",
                }
            },
            "auth/api/v1/login-status": {
                "GET": {
                    "status": 200,
                    "classification": "success_response",
                }
            },
        },
    }

    findings = build_verifier_findings(report)

    assert len(findings) == 2
    assert all(item["classification"] == "unknown" for item in findings)
    assert all(item["confidence"] == 0.30 for item in findings)
    assert all(
        0 <= item["confidence"] <= 1
        for item in findings
    )


def test_http_status_alone_does_not_prove_shadow_or_zombie():
    report = {
        "endpoint_classification": {
            "user": {
                "/api/v0/users/export": "zombie_candidate",
                "/api/v1/debug/metrics": "shadow_candidate",
            }
        },
        "methods_by_endpoint": {
            "user/api/v0/users/export": {
                "GET": {
                    "status": 200,
                    "classification": "success_response",
                }
            },
            "user/api/v1/debug/metrics": {
                "GET": {
                    "status": 200,
                    "classification": "success_response",
                }
            },
        },
    }

    findings = build_verifier_findings(report)

    assert len(findings) == 2
    assert all(item["classification"] == "unknown" for item in findings)
    assert all(item["confidence"] == 0.30 for item in findings)
