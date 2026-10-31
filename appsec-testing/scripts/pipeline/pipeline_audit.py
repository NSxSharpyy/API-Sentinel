"""Audit sent-request and mock-capture JSONL files."""

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def load_jsonl(path):
    records = []
    errors = []

    with Path(path).open(encoding="utf-8") as file:
        for number, line in enumerate(file, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ValueError("Expected JSON object")
                records.append(item)
            except (json.JSONDecodeError, ValueError) as exc:
                errors.append({"line": number, "error": str(exc)})

    return records, errors


def audit_pipeline(sent_source, captures_source):
    sent, sent_errors = load_jsonl(sent_source)
    captured, capture_errors = load_jsonl(captures_source)

    def ids(records):
        return [
            record["request_id"]
            for record in records
            if isinstance(record.get("request_id"), str)
            and record["request_id"].strip()
        ]

    sent_ids = ids(sent)
    captured_ids = ids(captured)

    sent_counts = Counter(sent_ids)
    capture_counts = Counter(captured_ids)
    sent_unique = set(sent_ids)
    capture_unique = set(captured_ids)

    matched = sum(
        min(count, capture_counts.get(request_id, 0))
        for request_id, count in sent_counts.items()
    )
    rate = round(matched / len(sent_ids) * 100, 2) if sent_ids else 0.0

    missing = sorted(sent_unique - capture_unique)
    unexpected = sorted(capture_unique - sent_unique)
    duplicate_sent = sorted(
        request_id for request_id, count in sent_counts.items()
        if count > 1
    )
    duplicate_captured = sorted(
        request_id for request_id, count in capture_counts.items()
        if count > 1
    )

    failures = []

    if not sent_ids:
        failures.append("No valid sent request IDs found")
    if len(sent) != len(sent_ids):
        failures.append("Some sent records have missing or invalid request IDs")
    if len(captured) != len(captured_ids):
        failures.append("Some capture records have missing or invalid request IDs")
    if missing:
        failures.append("Some sent requests were not captured")
    if unexpected:
        failures.append("Unexpected capture request IDs were found")
    if duplicate_sent:
        failures.append("Duplicate sent request IDs were found")
    if duplicate_captured:
        failures.append("Duplicate capture request IDs were found")
    if sent_errors:
        failures.append("Sent-request JSONL contains parse errors")
    if capture_errors:
        failures.append("Capture JSONL contains parse errors")

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sent_source": str(sent_source),
        "captures_source": str(captures_source),
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "sent_records": len(sent),
        "sent_records_without_valid_id": len(sent) - len(sent_ids),
        "captured_records": len(captured),
        "captured_records_without_valid_id": len(captured) - len(captured_ids),
        "unique_sent_request_ids": len(sent_unique),
        "unique_captured_request_ids": len(capture_unique),
        "matched_unique_request_ids": len(sent_unique & capture_unique),
        "captured_sent_transactions": matched,
        "capture_rate_percent": rate,
        "missing_request_ids": missing,
        "unexpected_capture_request_ids": unexpected,
        "duplicate_sent_request_ids": duplicate_sent,
        "duplicate_capture_request_ids": duplicate_captured,
        "sent_parse_errors": sent_errors,
        "capture_parse_errors": capture_errors,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sent-source", default="logs/sent_requests.jsonl")
    parser.add_argument("--captures-source", default="logs/captures.jsonl")
    parser.add_argument("--output", default="logs/audit_report.json")
    args = parser.parse_args()

    try:
        report = audit_pipeline(args.sent_source, args.captures_source)
    except OSError as exc:
        parser.exit(2, f"Audit input error: {exc}\n")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )

    print("Audit status:", report["status"])
    print("Sent records:", report["sent_records"])
    print("Captured records:", report["captured_records"])
    print("Capture rate:", f'{report["capture_rate_percent"]}%')
    print("Missing request IDs:", len(report["missing_request_ids"]))
    print("Duplicate capture IDs:", len(report["duplicate_capture_request_ids"]))
    print("Audit report:", output)

    for failure in report["failures"]:
        print("FAIL:", failure)

    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
