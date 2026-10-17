import io
import json

from scripts.recon import endpoint_scanner as scanner


def read_log(handle):
    return [json.loads(line) for line in handle.getvalue().splitlines()]


def test_wordlist_has_unique_candidates_and_intentional_misses():
    candidates = scanner.load_wordlist()

    assert candidates
    assert len(candidates) == len(set(candidates))
    assert any("definitely-not-a-real-route" not in item for item in candidates)

    # Confirm the list contains both known candidate paths and ordinary probes.
    assert "debug/dump-tokens" in candidates
    assert "_admin/reset-cache" in candidates
    assert "debug" in candidates


def test_phase1_discovers_non_404_and_logs_misses(monkeypatch):
    monkeypatch.setattr(
        scanner, "SERVICES", {"auth": "http://auth.test"}
    )
    monkeypatch.setattr(
        scanner, "load_wordlist", lambda: ["debug", "missing"]
    )

    def fake_probe(session, base_url, path, method="GET"):
        return {"/debug": 200, "/missing": 404}[path]

    monkeypatch.setattr(scanner, "probe", fake_probe)
    handle = io.StringIO()

    result = scanner.phase1_wordlist_probe(None, handle, delay=0)

    assert result == {"auth": {"/debug"}}
    records = read_log(handle)
    assert len(records) == 2
    assert records[0]["discovered"] is True
    assert records[1]["discovered"] is False
    assert records[1]["status"] == 404


def test_phase2_probes_v1_and_v3_siblings(monkeypatch):
    monkeypatch.setattr(
        scanner, "SERVICES", {"auth": "http://auth.test"}
    )
    monkeypatch.setattr(
        scanner,
        "KNOWN_V2_PATTERNS",
        {"auth": ["/api/v2/auth/verify"]},
    )
    probed = []

    def fake_probe(session, base_url, path, method="GET"):
        probed.append(path)
        return 200 if path == "/api/v1/auth/verify" else 404

    monkeypatch.setattr(scanner, "probe", fake_probe)
    handle = io.StringIO()

    result = scanner.phase2_version_sibling_probe(None, handle, delay=0)

    assert probed == ["/api/v1/auth/verify", "/api/v3/auth/verify"]
    assert result == {"auth": {"/api/v1/auth/verify"}}
    records = read_log(handle)
    assert len(records) == 2
    assert all(record["phase"] == "version_sibling" for record in records)


def test_phase3_classifies_post_only_admin_route(monkeypatch):
    monkeypatch.setattr(
        scanner, "SERVICES", {"billing": "http://billing.test"}
    )
    statuses = {"GET": 405, "POST": 200, "PUT": 405, "DELETE": 405}

    def fake_probe(session, base_url, path, method="GET"):
        return statuses[method]

    monkeypatch.setattr(scanner, "probe", fake_probe)
    handle = io.StringIO()

    results = scanner.phase3_method_enumeration(
        None, handle, {"billing": {"/_admin/reset-cache"}}, delay=0
    )

    endpoint = results["billing/_admin/reset-cache"]
    assert endpoint["POST"] == {
        "status": 200,
        "classification": "success_response",
    }
    for method in ("GET", "PUT", "DELETE"):
        assert endpoint[method]["classification"] == "method_not_allowed"

    records = read_log(handle)
    assert len(records) == 4
    assert {record["method"] for record in records} == {
        "GET", "POST", "PUT", "DELETE"
    }


def test_phase3_classifies_authentication_and_no_response(monkeypatch):
    monkeypatch.setattr(
        scanner, "SERVICES", {"order": "http://order.test"}
    )

    def fake_probe(session, base_url, path, method="GET"):
        return 401 if method == "GET" else None

    monkeypatch.setattr(scanner, "probe", fake_probe)
    handle = io.StringIO()

    results = scanner.phase3_method_enumeration(
        None, handle, {"order": {"/api/v1/orders/1"}}, delay=0
    )

    endpoint = results["order/api/v1/orders/1"]
    assert endpoint["GET"]["classification"] == "authentication_required"
    assert endpoint["POST"]["classification"] == "no_response"
    assert endpoint["POST"]["status"] is None


def test_documented_v2_routes_are_not_added_as_version_sibling_findings(
    monkeypatch,
):
    monkeypatch.setattr(
        scanner, "SERVICES", {"auth": "http://auth.test"}
    )
    monkeypatch.setattr(
        scanner,
        "KNOWN_V2_PATTERNS",
        {"auth": ["/api/v2/auth/verify"]},
    )
    probed = []

    def fake_probe(session, base_url, path, method="GET"):
        probed.append(path)
        return 404

    monkeypatch.setattr(scanner, "probe", fake_probe)
    handle = io.StringIO()

    result = scanner.phase2_version_sibling_probe(None, handle, delay=0)

    assert result == {"auth": set()}
    assert "/api/v2/auth/verify" not in probed
    assert all("/api/v2/" not in path for path in result["auth"])
