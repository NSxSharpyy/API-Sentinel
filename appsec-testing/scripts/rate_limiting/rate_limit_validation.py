#!/usr/bin/env python3
"""Validate Day 18 evidence against the authorized local mock rate limiter."""
import argparse
import hashlib
import json
import secrets
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def load_jsonl(path):
    records = []
    with Path(path).open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{path}:{line_number}: invalid JSON: {exc}"
                ) from exc
            if not isinstance(record, dict):
                raise ValueError(
                    f"{path}:{line_number}: each JSONL record must be an object"
                )
            records.append(record)

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
                return None
    return None


def summarize(path):
    records = load_jsonl(path)
    statuses = Counter()
    errors = 0

    for record in records:
        status = status_of(record)
        if status is None or status == 0:
            errors += 1
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


def token_identity_hash(token):
    """Match the limiter's identity hashing without exposing the token."""
    return hashlib.sha256(("token:" + token).encode("utf-8")).hexdigest()


def request_record(base_url, path, token, timeout):
    started_at = utc_now()
    started = time.monotonic()
    identity_hash = token_identity_hash(token)

    record = {
        "timestamp_started": started_at,
        "identity_sha256": identity_hash,
        "method": "GET",
        "path": path,
        "status_code": None,
        "timestamp_finished": None,
        "elapsed_seconds": None,
        "error": None,
    }

    try:
        response = requests.get(
            base_url.rstrip("/") + path,
            headers={"Authorization": "Bearer " + token},
            timeout=timeout,
            allow_redirects=False,
        )
        record["status_code"] = response.status_code
    except requests.RequestException as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        record["timestamp_finished"] = utc_now()
        record["elapsed_seconds"] = round(time.monotonic() - started, 6)

    return record


def read_limiter_config(base_url, timeout):
    """Read actual active limiter configuration from its health endpoint."""
    response = requests.get(
        base_url.rstrip("/") + "/health",
        timeout=timeout,
        allow_redirects=False,
    )
    response.raise_for_status()
    data = response.json()

    limit = data.get("limit")
    window = data.get("window_seconds")
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or limit < 1
        or isinstance(window, bool)
        or not isinstance(window, (int, float))
        or window <= 0
    ):
        raise ValueError(
            "Limiter /health did not return a valid positive limit and window_seconds."
        )

    return {
        "component": data.get("component"),
        "temporary": data.get("temporary"),
        "limit": limit,
        "window_seconds": float(window),
    }


def run_recovery_check(base_url, path, limit, window, timeout):
    """Trigger a real 429, wait out its window, and make a recovery request."""
    token = secrets.token_urlsafe(24)
    trigger_requests = [
        request_record(base_url, path, token, timeout)
        for _ in range(limit + 1)
    ]
    observed_429 = any(r["status_code"] == 429 for r in trigger_requests)

    wait_seconds = window + 0.1 if observed_429 else 0.0
    if observed_429:
        time.sleep(wait_seconds)

    recovery_request = request_record(base_url, path, token, timeout)
    status = recovery_request["status_code"]
    recovery_ok = (
        observed_429
        and recovery_request["error"] is None
        and status is not None
        and 200 <= status < 500
        and status != 429
    )

    return {
        "pass": recovery_ok,
        "identity_sha256": token_identity_hash(token),
        "trigger_requests": trigger_requests,
        "observed_trigger_429": observed_429,
        "window_seconds_from_health": window,
        "waited_seconds": wait_seconds,
        "post_window_request": recovery_request,
        "post_window_status": status,
        "evidence_source": "HTTP requests executed by this validator",
    }


def run_negative_control(base_url, path, limit, requested_count, timeout):
    """Exercise a fresh identity below its configured request limit."""
    token = secrets.token_urlsafe(24)
    count = min(requested_count, limit)
    records = [
        request_record(base_url, path, token, timeout)
        for _ in range(count)
    ]

    completed = sum(r["status_code"] is not None for r in records)
    blocked = sum(r["status_code"] == 429 for r in records)
    errors = sum(r["error"] is not None for r in records)
    rate = blocked / completed if completed else 1.0
    statuses_acceptable = all(
        r["status_code"] is not None
        and r["error"] is None
        and 200 <= r["status_code"] < 500
        and r["status_code"] != 429
        for r in records
    )

    return {
        "pass": (
            count > 0
            and completed == count
            and errors == 0
            and blocked == 0
            and statuses_acceptable
        ),
        "identity_sha256": token_identity_hash(token),
        "requested_requests": count,
        "completed_requests": completed,
        "http_429": blocked,
        "transport_errors": errors,
        "blocked_rate": rate,
        "requests": records,
        "evidence_source": "HTTP requests executed by this validator",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flood-jsonl", required=True)
    parser.add_argument("--credentials-jsonl", required=True)
    parser.add_argument("--legitimate-jsonl", required=True)
    parser.add_argument(
        "--base-url", default="http://127.0.0.1:7001",
        help="Local mock limiter URL; default is listener 7001.",
    )
    parser.add_argument(
        "--probe-path", default="/",
        help="Path forwarded through the limiter for active HTTP checks.",
    )
    parser.add_argument("--request-timeout", type=float, default=3.0)
    parser.add_argument("--negative-control-requests", type=int, default=3)
    parser.add_argument("--out", default="logs/rate_limit_effectiveness_report.json")
    parser.add_argument("--flood-threshold", type=float, default=0.50)
    parser.add_argument("--legitimate-threshold", type=float, default=0.95)
    parser.add_argument(
        "--negative-control-max-block-rate", type=float, default=0.50
    )
    args = parser.parse_args()

    parsed = urlparse(args.base_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.port not in {7001, 7002, 7003, 7004}
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        parser.error("--base-url must target a local mock limiter on port 7001–7004.")
    if (
        not args.probe_path.startswith("/")
        or args.probe_path.startswith("//")
        or "://" in args.probe_path
        or any(c in args.probe_path for c in "\r\n")
    ):
        parser.error("--probe-path must be a local absolute path, not a URL.")
    if args.request_timeout <= 0 or args.negative_control_requests < 1:
        parser.error("Timeout must be positive and negative-control requests >= 1.")
    if not 0 <= args.flood_threshold <= 1:
        parser.error("--flood-threshold must be between 0 and 1.")
    if not 0 <= args.legitimate_threshold <= 1:
        parser.error("--legitimate-threshold must be between 0 and 1.")
    if not 0 <= args.negative_control_max_block_rate <= 1:
        parser.error("--negative-control-max-block-rate must be between 0 and 1.")

    flood = summarize(args.flood_jsonl)
    credentials = summarize(args.credentials_jsonl)
    legitimate = summarize(args.legitimate_jsonl)

    active_checks = {}
    config = None
    active_error = None
    try:
        config = read_limiter_config(args.base_url, args.request_timeout)
        active_checks["negative_control"] = run_negative_control(
            args.base_url, args.probe_path, config["limit"],
            args.negative_control_requests, args.request_timeout,
        )
        active_checks["recovery"] = run_recovery_check(
            args.base_url, args.probe_path, config["limit"],
            config["window_seconds"], args.request_timeout,
        )
    except (
        requests.RequestException, ValueError, json.JSONDecodeError
    ) as exc:
        active_error = f"{type(exc).__name__}: {exc}"

    negative = active_checks.get("negative_control", {
        "pass": False, "completed_requests": 0, "http_429": 0,
        "blocked_rate": 1.0, "transport_errors": 0, "requests": [],
        "evidence_source": "missing: active HTTP check failed",
    })
    recovery = active_checks.get("recovery", {
        "pass": False, "post_window_status": None,
        "evidence_source": "missing: active HTTP check failed",
    })

    checks = {
        "flood_blocking": {
            "pass": (
                flood["completed_http_responses"] > 0
                and flood["transport_or_missing_status_errors"] == 0
                and flood["blocked_rate"] >= args.flood_threshold
            ),
            "observed_rate": flood["blocked_rate"],
            "required_minimum": args.flood_threshold,
        },
        "legitimate_success": {
            "pass": (
                legitimate["completed_http_responses"] > 0
                and legitimate["transport_or_missing_status_errors"] == 0
                and legitimate["success_rate"] >= args.legitimate_threshold
            ),
            "observed_rate": legitimate["success_rate"],
            "required_minimum": args.legitimate_threshold,
        },
        "recovery": recovery,
        "negative_control": {
            **negative,
            "pass": (
                negative.get("pass", False)
                and negative.get("completed_requests", 0) > 0
                and negative.get("blocked_rate", 1.0)
                    < args.negative_control_max_block_rate
            ),
            "required_maximum_exclusive": args.negative_control_max_block_rate,
        },
    }

    report = {
        "schema_version": 2,
        "generated_at": utc_now(),
        "scope": "authorized local API-Sentinel lab; temporary mock limiter",
        "validation_class": "local integration test; not production validation",
        "limiter_config_observed_from_health": config,
        "configured_thresholds": {
            "flood_block_rate_minimum": args.flood_threshold,
            "legitimate_success_rate_minimum": args.legitimate_threshold,
            "negative_control_block_rate_exclusive_maximum":
                args.negative_control_max_block_rate,
        },
        "runs": {
            "flood": flood,
            "credential_stuffing": credentials,
            "legitimate": legitimate,
            "negative_control": negative,
            "recovery": recovery,
        },
        "checks": checks,
        "active_check_error": active_error,
        "overall": "PASS" if all(
            item.get("pass", False) for item in checks.values()
        ) and active_error is None else "FAIL",
        "note": (
            "Credential-stuffing metrics are reported separately. "
            "HTTP checks prove behavior only for this local mock configuration; "
            "they do not establish production effectiveness."
        ),
    }

    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "report": str(output),
        "overall": report["overall"],
        "checks": checks,
        "credential_stuffing": credentials,
        "active_check_error": active_error,
    }, indent=2))
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
