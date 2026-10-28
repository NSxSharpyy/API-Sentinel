"""Independent, request-correlated log-based BOLA detector."""

import json
from datetime import datetime, timezone
from pathlib import Path

RULE_ID = "BOLA-LOG-001"
ACCESS_MESSAGES = {"invoice accessed", "INTENTIONAL BOLA accessed"}


def _positive_int(event, name):
    value = event.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def analyze_event(event, request_events=None):
    """Alert only when a successful request matches a cross-owner access event."""
    if not isinstance(event, dict):
        raise ValueError("event must be a JSON object")

    if event.get("message") not in ACCESS_MESSAGES:
        return None

    request_id = event.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("request_id must be a non-empty string")

    method = event.get("method")
    path = event.get("path")
    if not isinstance(method, str) or not method:
        raise ValueError("method must be a non-empty string")
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("path must be a valid absolute URL path")

    requester_id = _positive_int(event, "requester_id")
    owner_id = _positive_int(event, "owner_id")
    invoice_id = event.get("invoice_id", event.get("billing_id"))
    if isinstance(invoice_id, bool) or not isinstance(invoice_id, int) or invoice_id < 1:
        raise ValueError("invoice_id/billing_id must be a positive integer")

    # The access event itself has no authoritative status. Require a matching
    # completion event; never assume success if correlation evidence is absent.
    matches = [
        record for record in (request_events or [])
        if isinstance(record, dict)
        and record.get("message") == "request"
        and record.get("request_id") == request_id
        and record.get("method") == method
        and record.get("path") == path
    ]
    if not matches:
        return None

    statuses = []
    for record in matches:
        status = record.get("status")
        if isinstance(status, bool) or not isinstance(status, int):
            raise ValueError("correlated request status must be an integer")
        statuses.append(status)

    # Conflicting completions for one request ID are ambiguous; fail closed.
    if len(set(statuses)) != 1:
        return None

    status = statuses[0]
    if not 200 <= status < 300 or requester_id == owner_id:
        return None

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "rule_id": RULE_ID,
        "severity": "HIGH",
        "detection_type": "BOLA",
        "source": "billing-service-log",
        "message": "Successful invoice access by a non-owner",
        "request_id": request_id,
        "invoice_id": invoice_id,
        "requester_id": requester_id,
        "owner_id": owner_id,
        "endpoint": path,
        "evidence": {
            "http_status": status,
            "identity_mismatch": True,
            "correlated_request": True,
        },
    }


def detect_file(input_path, output_path):
    """Correlate JSONL access events with request completion events."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    summary = {
        "input_file": str(input_path),
        "alerts_file": str(output_path),
        "events_read": 0,
        "events_processed": 0,
        "alerts_generated": 0,
        "invalid_events": 0,
        "errors": [],
        "access_events": 0,
        "correlated_access_events": 0,
    }

    if not input_path.exists():
        summary["errors"].append("input_file_missing")
        output_path.write_text("", encoding="utf-8")
        return summary

    records = []
    with input_path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            summary["events_read"] += 1
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("event must be a JSON object")
                records.append((line_number, record))
                summary["events_processed"] += 1
            except (json.JSONDecodeError, ValueError) as exc:
                summary["invalid_events"] += 1
                summary["errors"].append({
                    "line": line_number,
                    "error": str(exc),
                })

    request_events = [
        record for _, record in records
        if record.get("message") == "request"
    ]

    with output_path.open("w", encoding="utf-8") as alerts:
        for line_number, event in records:
            if event.get("message") not in ACCESS_MESSAGES:
                continue

            summary["access_events"] += 1
            request_id = event.get("request_id")
            correlated = any(
                record.get("request_id") == request_id
                and record.get("method") == event.get("method")
                and record.get("path") == event.get("path")
                for record in request_events
            )
            if correlated:
                summary["correlated_access_events"] += 1

            try:
                alert = analyze_event(event, request_events)
                if alert is not None:
                    alerts.write(json.dumps(alert) + "\n")
                    summary["alerts_generated"] += 1
            except ValueError as exc:
                summary["invalid_events"] += 1
                summary["errors"].append({
                    "line": line_number,
                    "error": str(exc),
                })

    return summary
