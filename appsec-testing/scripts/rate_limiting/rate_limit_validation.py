#!/usr/bin/env python3
"""Grade Day 18 rate-limiter evidence from local API-Sentinel JSONL logs."""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def load_jsonl(path):
    records = []
    with Path(path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path}:{line_number}: invalid JSON: {exc}"
                ) from exc
    if not records:
        raise ValueError(f"No records found in {path}")
    return records


def status_of(record):
    for key in ("status_code", "status", "http_status", "response_status"):
        value = record.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                break
    return None


def summarize(path):
    records = load_jsonl(path)
    statuses = Counter()
    errors = 0

    for record in records:
        status = status_of(record)
        if status is None or status == 0:
            if record.get("error") or record.get("exception") or status in (None, 0):
                errors += 1
            else:
                statuses["unknown"] += 1
        else:
            statuses[str(status)] += 1

    completed = sum(statuses.values())
    blocked = statuses.get("429", 0)
    successful = sum(
        count for status, count in statuses.items()
        if status.isdigit() and 200 <= int(status) < 300
    )
    upstream_5xx = sum(
        count for status, count in statuses.items()
        if status.isdigit() and 500 <= int(status) < 600
    )

    return {
        "source": str(path),
        "records": len(records),
        "completed_http_responses": completed,
        "transport_or_missing_status_errors": errors,
        "status_counts": dict(sorted(statuses.items())),
        "http_2xx": successful,
        "http_429": blocked,
        "http_5xx": upstream_5xx,
        "blocked_rate": blocked / completed if completed else 0.0,
        "success_rate": successful / completed if completed else 0.0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flood-jsonl", required=True)
    parser.add_argument("--credentials-jsonl", required=True)
    parser.add_argument("--legitimate-jsonl", required=True)
    parser.add_argument("--recovery-status", required=True, type=int)
    parser.add_argument("--negative-control-completed", required=True, type=int)
    parser.add_argument("--negative-control-429", required=True, type=int)
    parser.add_argument("--out", default="logs/rate_limit_effectiveness_report.json")
    parser.add_argument("--flood-threshold", type=float, default=0.50)
    parser.add_argument("--legitimate-threshold", type=float, default=0.95)
    parser.add_argument("--negative-control-max-block-rate", type=float, default=0.50)
    args = parser.parse_args()

    flood = summarize(args.flood_jsonl)
    credentials = summarize(args.credentials_jsonl)
    legitimate = summarize(args.legitimate_jsonl)

    neg_completed = args.negative_control_completed
    neg_blocked = args.negative_control_429
    if neg_completed < 0 or neg_blocked < 0 or neg_blocked > neg_completed:
        parser.error("Negative-control counts are inconsistent.")

    negative_rate = neg_blocked / neg_completed if neg_completed else 1.0
    checks = {
        "flood_blocking": {
            "pass": flood["blocked_rate"] >= args.flood_threshold,
            "observed_rate": flood["blocked_rate"],
            "required_minimum": args.flood_threshold,
        },
        "legitimate_success": {
            "pass": legitimate["success_rate"] >= args.legitimate_threshold,
            "observed_rate": legitimate["success_rate"],
            "required_minimum": args.legitimate_threshold,
        },
        "recovery": {
            "pass": 200 <= args.recovery_status < 500
                    and args.recovery_status != 429,
            "observed_status": args.recovery_status,
            "requirement": "post-window response is not 429 or 5xx",
        },
        "negative_control": {
            "pass": neg_completed > 0
                    and negative_rate < args.negative_control_max_block_rate,
            "completed_requests": neg_completed,
            "http_429": neg_blocked,
            "observed_block_rate": negative_rate,
            "required_maximum_exclusive": args.negative_control_max_block_rate,
        },
    }

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "authorized local API-Sentinel lab; temporary mock limiter",
        "thresholds": {
            "flood_block_rate_minimum": args.flood_threshold,
            "legitimate_success_rate_minimum": args.legitimate_threshold,
            "negative_control_block_rate_exclusive_maximum":
                args.negative_control_max_block_rate,
        },
        "runs": {
            "flood": flood,
            "credential_stuffing": credentials,
            "legitimate": legitimate,
            "negative_control": {
                "completed_requests": neg_completed,
                "http_429": neg_blocked,
                "blocked_rate": negative_rate,
                "evidence_source": "manually supplied from terminal-observed test results",
            },
            "recovery": {
                "post_window_status": args.recovery_status,
                "evidence_source": "manually supplied from terminal-observed test result",
            },
        },
        "checks": checks,
        "overall": "PASS" if all(item["pass"] for item in checks.values()) else "FAIL",
        "note": "Credential-stuffing metrics are reported separately; production effectiveness is not implied.",
    }

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "report": str(output),
        "overall": report["overall"],
        "checks": checks,
        "credential_stuffing": credentials,
    }, indent=2))
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
