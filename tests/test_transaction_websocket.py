from app.transaction_websocket import normalize_transaction


def valid_event():
    return {
        "message_type": "completed_transaction",
        "connection_key": "test-connection",
        "request": {
            "message_type": "request",
            "captured_at": "2026-11-05T10:00:00Z",
            "method": "GET",
            "uri": "http://localhost/api/v1/accounts/123?token=secret",
        },
        "response": {
            "message_type": "response",
            "captured_at": "2026-11-05T10:00:01Z",
            "status_code": 200,
            "uri": "http://localhost/api/v1/accounts/123",
        },
    }


def test_normalize_transaction_keeps_safe_metadata_only():
    result = normalize_transaction(valid_event())

    assert result is not None
    assert result["event_type"] == "http.transaction"
    assert result["request"]["uri"] == "/api/v1/accounts/123"
    assert result["response"]["status_code"] == 200
    assert "token" not in str(result)
    assert "headers" not in result["request"]
    assert "body" not in result["request"]


def test_normalize_transaction_rejects_wrong_event_type():
    event = valid_event()
    event["message_type"] = "unexpected"

    assert normalize_transaction(event) is None


def test_normalize_transaction_rejects_missing_request():
    event = valid_event()
    event["request"] = None

    assert normalize_transaction(event) is None


def test_normalize_transaction_rejects_invalid_status_code():
    event = valid_event()
    event["response"]["status_code"] = "200"

    assert normalize_transaction(event) is None


def test_normalize_transaction_rejects_wrong_request_type():
    event = valid_event()
    event["request"]["message_type"] = "unexpected"

    assert normalize_transaction(event) is None
