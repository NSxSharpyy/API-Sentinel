
#!/usr/bin/env python3
"""Evaluate Day 23 concurrency and kernel-certification evidence.

This module does not attach eBPF programs or modify kernel/network state.
Application-layer simulation is never accepted as kernel-drop proof.
"""

import argparse
import json
from pathlib import Path



def cleanup_is_valid(cleanup, required_operations):
    """Require explicit successful evidence for every cleanup operation."""
    if not isinstance(cleanup, dict) or cleanup.get("complete") is not True:
        return False

    successful_statuses = {"ok", "not_needed"}

    for name in required_operations:
        operation = cleanup.get(name)
        if not isinstance(operation, dict):
            return False

        if operation.get("skipped") is True or "error" in operation:
            return False

        has_returncode = "returncode" in operation
        has_status = "status" in operation

        # Every operation must provide explicit success evidence.
        if not has_returncode and not has_status:
            return False

        if has_returncode:
            code = operation["returncode"]
            if isinstance(code, bool) or not isinstance(code, int) or code != 0:
                return False

        if has_status:
            status = operation["status"]
            if not isinstance(status, str):
                return False
            if status.lower() not in successful_statuses:
                return False

    return not bool(cleanup.get("pin_cleanup_errors"))

def evaluate_evidence(day19, concurrency):
    """Return independently evaluated concurrency and kernel gates."""
    day19 = day19 if isinstance(day19, dict) else {}
    concurrency = concurrency if isinstance(concurrency, dict) else {}

    day19_steps = day19.get("steps")
    day19_steps = day19_steps if isinstance(day19_steps, dict) else {}
    counters_step = day19_steps.get("map_dump")
    counters_step = counters_step if isinstance(counters_step, dict) else {}
    counters = counters_step.get("counters")
    counters = counters if isinstance(counters, dict) else {}
    cleanup = day19.get("cleanup")
    cleanup = cleanup if isinstance(cleanup, dict) else {}

    matched = counters.get("matched")
    dropped = counters.get("dropped")
    counter_types_valid = (
        isinstance(matched, int)
        and not isinstance(matched, bool)
        and isinstance(dropped, int)
        and not isinstance(dropped, bool)
    )
    day19_assertions = day19_steps.get("assertions")
    day19_assertions = (
        day19_assertions if isinstance(day19_assertions, dict) else {}
    )

    required_day19_assertions = {
        "map_dump_succeeded",
        "matched_packets_positive",
        "dropped_packets_positive",
        "matched_equals_dropped",
        "client_response_timed_out",
        "no_http_response_received",
    }

    day19_assertions_valid = (
        required_day19_assertions.issubset(day19_assertions.keys())
        and all(
           day19_assertions[name] is True
           for name in required_day19_assertions
       )
    )

    day19_client = day19_steps.get("client")
    day19_client = (
        day19_client if isinstance(day19_client, dict) else {}
    )

    day19_client_valid = (
    day19_client.get("received_response") is False
    and day19_client.get("error") == "response_timeout"
    )
    map_dump_returncode = counters_step.get("returncode")
    map_dump_succeeded = (
        isinstance(map_dump_returncode, int)
        and not isinstance(map_dump_returncode, bool)
        and map_dump_returncode == 0
    )
    day19_observation_valid = (
        day19.get("overall") == "OBSERVED"
        and counter_types_valid
        and matched > 0
        and dropped > 0
        and matched == dropped
        and map_dump_succeeded
        and cleanup.get("complete") is True
        and day19_assertions_valid
        and day19_client_valid
    )

    # Require explicit evidence that this workload was tested with
    # kernel enforcement, rather than trusting a generic PASS label.
    concurrency_kernel_proof = (
        concurrency.get("evidence_type") == "kernel_drop"
        and concurrency.get("kernel_drop_proof") is True
        and concurrency.get("concurrency_evidence") is True
    )

    workload_checks = concurrency.get("checks")
    workload_checks = (
        workload_checks if isinstance(workload_checks, dict) else {}
    )

    required_workload_checks = {
        "workload_completed",
        "all_attempts_timed_out",
        "drop_accuracy_passed",
        "source_port_coverage_passed",
        "cleanup_complete",
        "no_runtime_error",
    }
    required_checks_present = required_workload_checks.issubset(
        workload_checks.keys()
    )

    source_evidence = concurrency.get("source_port_evidence")
    source_evidence = (
        source_evidence if isinstance(source_evidence, dict) else {}
    )

    requested = concurrency.get("requested_attempts")
    expected_ports = source_evidence.get("expected_source_ports")
    observed_ports = source_evidence.get("observed_source_ports")
    hit_counts = source_evidence.get("hit_counts")

    workload = concurrency.get("workload")
    workload = workload if isinstance(workload, dict) else {}
    results = workload.get("results")
    # Independently validate counters collected during concurrent enforcement.
    kernel_counters = concurrency.get("kernel_counters")
    kernel_counters = (
        kernel_counters if isinstance(kernel_counters, dict) else {}
    )

    concurrent_matched = kernel_counters.get("matched")
    concurrent_dropped = kernel_counters.get("dropped")

    concurrent_counter_types_valid = (
        isinstance(concurrent_matched, int)
        and not isinstance(concurrent_matched, bool)
        and isinstance(concurrent_dropped, int)
        and not isinstance(concurrent_dropped, bool)
    )

    concurrent_kernel_counters_valid = (
        concurrent_counter_types_valid
        and concurrent_matched > 0
        and concurrent_dropped > 0
        and concurrent_matched == concurrent_dropped
    )

    # Independently validate workload cardinality and outcomes.
    attempts_completed = workload.get("attempts_completed")
    outcomes = workload.get("outcomes")
    concurrency_level = concurrency.get("concurrency")

    workload_totals_valid = (
        isinstance(attempts_completed, int)
        and not isinstance(attempts_completed, bool)
        and attempts_completed == requested
        and isinstance(outcomes, dict)
        and all(
            isinstance(count, int)
            and not isinstance(count, bool)
            and count >= 0
            for count in outcomes.values()
        )
        and sum(outcomes.values()) == requested
        and outcomes.get("timeout") == requested
        and isinstance(concurrency_level, int)
        and not isinstance(concurrency_level, bool)
        and 1 <= concurrency_level <= requested
    )

    source_port_evidence_valid = (
        isinstance(requested, int)
        and not isinstance(requested, bool)
        and requested > 0
        and isinstance(expected_ports, list)
        and len(expected_ports) == requested
        and all(
            isinstance(port, int)
            and not isinstance(port, bool)
            and 1 <= port <= 65535
            for port in expected_ports
        )
        and len(set(expected_ports)) == requested
        and isinstance(observed_ports, list)
        and all(
            isinstance(port, int)
            and not isinstance(port, bool)
            for port in observed_ports
        )
        and len(observed_ports) == requested
        and len(set(observed_ports)) == requested
        and set(observed_ports) == set(expected_ports)
        and isinstance(hit_counts, dict)
        and set(hit_counts) == {str(port) for port in expected_ports}
        and all(
            isinstance(count, int)
            and not isinstance(count, bool)
            and count > 0
            for count in hit_counts.values()
        )
        and isinstance(results, list)
        and len(results) == requested
        and all(
            isinstance(item, dict)
            and item.get("source_port") in expected_ports
            and item.get("outcome") == "timeout"
            for item in results
        )
        and len({
            item["source_port"]
            for item in results
            if isinstance(item, dict)
            and isinstance(item.get("source_port"), int)
            and not isinstance(item.get("source_port"), bool)
        }) == requested
    )

    concurrency_passed = (
        concurrency.get("overall") == "PASS"
        and required_checks_present
        and source_port_evidence_valid
        and concurrent_kernel_counters_valid
        and workload_totals_valid
        and all(
            workload_checks[name] is True
            for name in required_workload_checks
        )
        and all(value is True for value in workload_checks.values())
    )

    day19_cleanup_complete = cleanup_is_valid(
        cleanup, ("filter_delete", "qdisc_delete")
    )

    concurrency_cleanup = concurrency.get("cleanup")
    concurrency_cleanup_complete = cleanup_is_valid(
        concurrency_cleanup,
        ("filter_delete", "qdisc_delete", "pin_cleanup"),
    )

    cleanup_complete = day19_cleanup_complete

    checks = {
        "day19_kernel_observation_valid": day19_observation_valid,
        "day19_cleanup_complete": day19_cleanup_complete,
        "day23_concurrency_cleanup_complete": concurrency_cleanup_complete,
        "concurrency_workload_passed": concurrency_passed,
        "concurrent_kernel_drop_proof_present": concurrency_kernel_proof,
        "concurrent_source_port_evidence_valid": source_port_evidence_valid,
        "concurrent_kernel_counters_valid": (
            concurrent_kernel_counters_valid
        ),
        "concurrent_workload_totals_valid": workload_totals_valid,
    }

    # A Day 19 single-connection observation cannot substitute for
    # kernel evidence gathered during the concurrent workload itself.
    kernel_certification = (
        "PASS"
        if (
           checks["day19_kernel_observation_valid"]
           and day19_cleanup_complete
           and concurrency_passed
           and concurrency_kernel_proof
           and concurrency_cleanup_complete
        )
        else "FAIL"
    )

    return {
        "schema_version": 1,
        "evidence_type": "day23_evidence_evaluation",
        "kernel_drop_proof": kernel_certification == "PASS",
        "concurrency_status": "PASS" if concurrency_passed else "FAIL",
        "kernel_certification": kernel_certification,
        "checks": checks,
        "concurrent_source_port_evidence_valid": source_port_evidence_valid,
        "concurrent_kernel_counters_valid": (
            concurrent_kernel_counters_valid
        ),
        "concurrent_workload_totals_valid": workload_totals_valid,
        "overall": kernel_certification,
        "limitations": [
            "Day 19 packet counters alone do not establish per-request blocking.",
            "Concurrent kernel-drop evidence must be collected during the "
            "concurrent workload.",
            "Application-layer simulation is not kernel-drop proof.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--day19-report", required=True, type=Path)
    parser.add_argument("--concurrency-report", required=True, type=Path)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("appsec-testing/logs/kernel_blocking_at_scale_report.json"),
    )
    args = parser.parse_args()

    try:
        with args.day19_report.open(encoding="utf-8") as handle:
            day19 = json.load(handle)
        with args.concurrency_report.open(encoding="utf-8") as handle:
            concurrency = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: unable to read input report: {exc}")
        return 2

    report = evaluate_evidence(day19, concurrency)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
