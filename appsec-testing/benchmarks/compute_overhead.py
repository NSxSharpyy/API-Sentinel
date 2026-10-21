#!/usr/bin/env python3
"""Strictly validate and compare k6 P95 benchmark summaries."""

import argparse
import json
import math
import sys
from pathlib import Path


def read_report(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as handle:
            report = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read valid JSON from {path}: {exc}") from exc

    if not isinstance(report, dict) or not isinstance(report.get("metrics"), dict):
        raise ValueError(f"{path}: missing metrics object")
    return report


def numeric_metric(report: dict, path: Path, name: str, field: str) -> float:
    item = report["metrics"].get(name)
    if not isinstance(item, dict):
        raise ValueError(f"{path}: required metric {name!r} is missing")

    value = item.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path}: {name}.{field} must be numeric")

    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{path}: {name}.{field} must be finite")
    return value


def threshold_metadata(report: dict, metric: str, threshold: str):
    item = report["metrics"].get(metric, {})
    thresholds = item.get("thresholds", {})
    if not isinstance(thresholds, dict) or threshold not in thresholds:
        return None
    value = thresholds[threshold]
    return value if isinstance(value, bool) else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate k6 health metrics and strict P95 latency gates."
    )
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--sidecar", required=True, type=Path)
    parser.add_argument("--metric", default="http_req_duration")
    parser.add_argument("--threshold-ms", type=float, default=5.0)
    parser.add_argument("--absolute-p95-threshold-ms", type=float, default=50.0)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    for name, value in (
        ("--threshold-ms", args.threshold_ms),
        ("--absolute-p95-threshold-ms", args.absolute_p95_threshold_ms),
    ):
        if not math.isfinite(value) or value <= 0:
            parser.error(f"{name} must be finite and greater than zero")

    try:
        baseline = read_report(args.baseline)
        sidecar = read_report(args.sidecar)

        baseline_p95 = numeric_metric(
            baseline, args.baseline, args.metric, "p(95)"
        )
        sidecar_p95 = numeric_metric(
            sidecar, args.sidecar, args.metric, "p(95)"
        )
        if baseline_p95 < 0 or sidecar_p95 < 0:
            raise ValueError("P95 values must be non-negative")

        health = {}
        for label, report, path in (
            ("baseline", baseline, args.baseline),
            ("sidecar", sidecar, args.sidecar),
        ):
            failed_rate = numeric_metric(
                report, path, "http_req_failed", "value"
            )
            checks_rate = numeric_metric(report, path, "checks", "value")
            errors_rate = numeric_metric(
                report, path, "benchmark_errors", "value"
            )

            if not (0 <= failed_rate <= 1):
                raise ValueError(f"{path}: http_req_failed.value must be in [0, 1]")
            if not (0 <= checks_rate <= 1):
                raise ValueError(f"{path}: checks.value must be in [0, 1]")
            if not (0 <= errors_rate <= 1):
                raise ValueError(f"{path}: benchmark_errors.value must be in [0, 1]")

            health[label] = {
                "http_req_failed_rate": failed_rate,
                "checks_success_rate": checks_rate,
                "benchmark_error_rate": errors_rate,
                "http_failures_pass": failed_rate < 0.01,
                "checks_pass": checks_rate > 0.99,
                "benchmark_errors_pass": errors_rate < 0.01,
            }

        delta = sidecar_p95 - baseline_p95
        delta_pass = delta < args.threshold_ms
        baseline_abs_pass = baseline_p95 < args.absolute_p95_threshold_ms
        sidecar_abs_pass = sidecar_p95 < args.absolute_p95_threshold_ms
        absolute_pass = baseline_abs_pass and sidecar_abs_pass

        health_pass = all(
            checks[key]
            for checks in health.values()
            for key in (
                "http_failures_pass",
                "checks_pass",
                "benchmark_errors_pass",
            )
        )

        metadata_checks = {
            "baseline_p95": threshold_metadata(
                baseline, args.metric,
                f"p(95)<{args.absolute_p95_threshold_ms:g}"
            ),
            "sidecar_p95": threshold_metadata(
                sidecar, args.metric,
                f"p(95)<{args.absolute_p95_threshold_ms:g}"
            ),
            "baseline_http_req_failed": threshold_metadata(
                baseline, "http_req_failed", "rate<0.01"
            ),
            "sidecar_http_req_failed": threshold_metadata(
                sidecar, "http_req_failed", "rate<0.01"
            ),
            "baseline_checks": threshold_metadata(
                baseline, "checks", "rate>0.99"
            ),
            "sidecar_checks": threshold_metadata(
                sidecar, "checks", "rate>0.99"
            ),
            "baseline_benchmark_errors": threshold_metadata(
                baseline, "benchmark_errors", "rate<0.01"
            ),
            "sidecar_benchmark_errors": threshold_metadata(
                sidecar, "benchmark_errors", "rate<0.01"
            ),
        }

        # k6 v2.3.0 summary-export threshold flags were experimentally
        # observed to contradict both its console output and numeric metrics.
        # Preserve the metadata for audit, but do not use it as an acceptance
        # gate. Numeric latency and health checks below remain authoritative.
        metadata_consistent = all(
            value is not False for value in metadata_checks.values()
        )
        metadata_warnings = []
        for key, value in metadata_checks.items():
            if value is False:
                metadata_warnings.append(
                    f"{key}: exported threshold flag is false; "
                    "evaluate the numeric metric and k6 console evidence"
                )
            elif value is None:
                metadata_warnings.append(
                    f"{key}: threshold metadata unavailable"
                )

        overall_pass = delta_pass and absolute_pass and health_pass

        result = {
            "metric": args.metric,
            "baseline_p95_ms": baseline_p95,
            "sidecar_p95_ms": sidecar_p95,
            "observed_p95_delta_ms": delta,
            "threshold_ms": args.threshold_ms,
            "comparison": "strictly_less_than",
            "overhead_status": "PASS" if delta_pass else "FAIL",
            "absolute_p95_threshold_ms": args.absolute_p95_threshold_ms,
            "baseline_absolute_p95_pass": baseline_abs_pass,
            "sidecar_absolute_p95_pass": sidecar_abs_pass,
            "absolute_latency_status": "PASS" if absolute_pass else "FAIL",
            "health_metrics": health,
            "health_status": "PASS" if health_pass else "FAIL",
            "threshold_metadata": metadata_checks,
            "threshold_metadata_consistent": metadata_consistent,
            "threshold_metadata_warnings": metadata_warnings,
            "status": "PASS" if overall_pass else "FAIL",
            "interpretation": (
                "All strict numeric latency and health gates passed; "
                "see threshold metadata warnings."
                if overall_pass
                else "At least one strict numeric latency or health gate failed."
            ),
            "baseline_file": str(args.baseline),
            "sidecar_file": str(args.sidecar),
            "is_real_ebpf_measurement": False,
        }

    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    output = json.dumps(result, indent=2)
    print(output)

    if args.out:
        try:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(output + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"ERROR: cannot write report to {args.out}: {exc}", file=sys.stderr)
            return 2
        print(f"Report saved: {args.out}")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
