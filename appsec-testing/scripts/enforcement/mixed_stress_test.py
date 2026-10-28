"""Day 22 mixed-traffic stress test.

LOCAL LAB ONLY. The Day 21 adapter is an application-layer simulation,
not proof of eBPF or kernel packet drops.
"""
import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = REPO_ROOT / "appsec-testing"
LOG_DIR = PROJECT_ROOT / "logs"
REPORT_PATH = LOG_DIR / "mixed_stress_report.json"

AUTH_URL = "http://127.0.0.1:5001"
BILLING_URL = "http://127.0.0.1:5004"
ENFORCER_URL = "http://127.0.0.1:8004"
WRAPPER_URL = "http://127.0.0.1:8005"

LEGITIMATE_COUNT = 1800
ATTACK_COUNT = 200
MIN_LEGITIMATE_RATIO = 0.85
MAX_LEGITIMATE_RATIO = 0.95
MIN_LEGITIMATE_SUCCESS_RATE = 0.98
MIN_ATTACK_BLOCK_RATE = 0.30


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def evaluate_legitimate_ratio(legitimate_count, total_count):
    """Validate the legitimate share using observed request counts."""
    ratio = legitimate_count / total_count if total_count else 0.0
    return {
        "ratio": ratio,
        "passes": MIN_LEGITIMATE_RATIO <= ratio <= MAX_LEGITIMATE_RATIO,
    }


def percentile(values, percent):
    """Return a nearest-rank percentile, or None when no samples exist."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, int((percent / 100) * len(ordered) + 0.999999))
    return ordered[min(rank - 1, len(ordered) - 1)]


def evaluate_metrics(
    report,
    expected_legitimate_count=LEGITIMATE_COUNT,
    expected_adversarial_count=ATTACK_COUNT,
):
    """Evaluate observed traffic against the planned request counts."""
    total = report.get("workload_request_count", 0)
    legitimate = report.get("legitimate_request_count", 0)
    attacks = report.get("adversarial_request_count", 0)
    legit_successes = report.get("legitimate_success_count", 0)
    attack_blocks = report.get("adversarial_blocked_count", 0)
    probes = report.get("latency_probe_count", 0)
    failed_probes = report.get("latency_probe_failure_count", 0)

    expected_total = expected_legitimate_count + expected_adversarial_count
    ratio_result = evaluate_legitimate_ratio(legitimate, total)
    ratio = ratio_result["ratio"]
    legit_rate = legit_successes / legitimate if legitimate else 0.0
    block_rate = attack_blocks / attacks if attacks else 0.0

    checks = {
        "exact_workload_count": total == expected_total,
        "exact_legitimate_count": legitimate == expected_legitimate_count,
        "exact_adversarial_count": attacks == expected_adversarial_count,
        "legitimate_ratio_in_range": ratio_result["passes"],
        "legitimate_success_rate_at_least_98_percent": (
            legit_rate >= MIN_LEGITIMATE_SUCCESS_RATE
        ),
        "adversarial_block_rate_at_least_30_percent": (
            block_rate >= MIN_ATTACK_BLOCK_RATE
        ),
        "latency_probes_observed": probes > 0,
        "zero_failed_latency_probes": failed_probes == 0,
        "resource_samples_observed": report.get("resource_sample_count", 0) > 0,
        "resource_sampling_errors_absent": (
            report.get("resource_sampling_error_count", 0) == 0
        ),
        "enforcement_adapter_active": report.get("enforcement_was_active") is True,
    }

    report["metrics"] = {
        "expected_workload_count": expected_total,
        "expected_legitimate_count": expected_legitimate_count,
        "expected_adversarial_count": expected_adversarial_count,
        "legitimate_ratio": ratio,
        "legitimate_success_rate": legit_rate,
        "adversarial_block_rate": block_rate,
    }
    report["checks"] = checks
    report["overall"] = "PASS" if all(checks.values()) else "FAIL"
    return report


def wait_for_health(url, process, timeout=12):
    deadline = time.monotonic() + timeout
    last_error = "health endpoint not ready"

    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Child process exited early ({process.returncode}): {url}"
            )
        try:
            response = requests.get(url, timeout=0.5)
            if response.ok:
                return response.json()
            last_error = f"HTTP {response.status_code}"
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(0.2)

    raise RuntimeError(f"Health check failed for {url}: {last_error}")


def login(username, password):
    response = requests.post(
        f"{AUTH_URL}/api/v2/auth/login",
        json={"username": username, "password": password},
        timeout=5,
    )
    response.raise_for_status()
    token = response.json().get("token")
    if not isinstance(token, str) or not token:
        raise RuntimeError(f"Login returned no token for {username}")
    return token


def prepare_customers():
    """Use the existing customer pool and actual owner-scoped invoice lists."""
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    from scripts.traffic.customer_pool import build_customer_pool

    pool = build_customer_pool()
    customers = []
    all_invoices = []

    for customer in pool:
        token = login(customer.username, customer.password)
        response = requests.get(
            f"{BILLING_URL}/api/v2/billing/invoices",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        response.raise_for_status()
        invoices = response.json().get("invoices", [])
        invoice_ids = [
            row["id"] for row in invoices
            if isinstance(row, dict) and isinstance(row.get("id"), int)
        ]
        customers.append({
            "username": customer.username,
            "token": token,
            "invoice_ids": invoice_ids,
        })
        all_invoices.extend(invoice_ids)

    if not customers:
        raise RuntimeError("No customers were available for the workload.")

    if not all_invoices:
        raise RuntimeError("No seeded invoices were found.")

    # Use a customer with invoices as the adversarial requester.
    attacker = next((c for c in customers if c["invoice_ids"]), None)
    if attacker is None:
        raise RuntimeError("No customer has an invoice for attack setup.")

    owned = set(attacker["invoice_ids"])
    foreign_ids = sorted(set(all_invoices) - owned)
    if not foreign_ids:
        raise RuntimeError(
            "No invoices owned by other customers were available."
        )

    return customers, attacker, foreign_ids


def workload_request(kind, index, customers, attacker, foreign_ids):
    started = time.monotonic()

    if kind == "legitimate":
        customer = customers[index % len(customers)]
        # Every legitimate target is selected from that customer's own list.
        if customer["invoice_ids"]:
            invoice_id = customer["invoice_ids"][
                index % len(customer["invoice_ids"])
            ]
            path = f"/api/v2/billing/invoices/{invoice_id}"
        else:
            path = "/api/v2/billing/invoices"
        token = customer["token"]
        traffic_class = "legitimate"
    else:
        invoice_id = foreign_ids[index % len(foreign_ids)]
        path = f"/api/v2/billing/invoices/{invoice_id}"
        token = attacker["token"]
        traffic_class = "attack"

    try:
        response = requests.get(
            f"{WRAPPER_URL}{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Day21-Traffic-Class": traffic_class,
                "X-Request-ID": f"day22-{kind}-{index:05d}",
            },
            timeout=5,
        )
        elapsed_ms = (time.monotonic() - started) * 1000
        blocked = (
            response.status_code == 403
            and response.headers.get("X-Day21-Enforcement") == "blocked"
        )
        return {
            "kind": kind,
            "index": index,
            "status_code": response.status_code,
            "latency_ms": round(elapsed_ms, 3),
            "blocked_by_enforcement": blocked,
            "error": None,
        }
    except requests.RequestException as exc:
        return {
            "kind": kind,
            "index": index,
            "status_code": None,
            "latency_ms": round((time.monotonic() - started) * 1000, 3),
            "blocked_by_enforcement": False,
            "error": type(exc).__name__,
        }


def sample_latency(stop_event, samples, failures):
    """Probe the wrapper independently, approximately once per second."""
    while not stop_event.is_set():
        started = time.monotonic()
        try:
            response = requests.get(
                f"{WRAPPER_URL}/__wrapper_health", timeout=1.5
            )
            elapsed = (time.monotonic() - started) * 1000
            if response.ok:
                samples.append({
                    "timestamp": utc_now(),
                    "latency_ms": round(elapsed, 3),
                    "status_code": response.status_code,
                })
            else:
                failures.append({
                    "timestamp": utc_now(),
                    "status_code": response.status_code,
                    "error": "non_success_status",
                })
        except requests.RequestException as exc:
            failures.append({
                "timestamp": utc_now(),
                "error": type(exc).__name__,
            })

        stop_event.wait(max(0, 1.0 - (time.monotonic() - started)))


def memory_to_mb(value):
    """Convert a Docker memory value such as 23.64MiB or 1.2GiB to MB."""
    match = re.fullmatch(
        r"\s*(\d+(?:\.\d+)?)\s*([KMGT]?i?B)\s*",
        value,
        flags=re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"Unrecognized Docker memory value: {value!r}")

    amount = float(match.group(1))
    unit = match.group(2).lower()
    factors = {
        "b": 1 / 1_000_000,
        "kb": 1 / 1_000,
        "kib": 1024 / 1_000_000,
        "mb": 1,
        "mib": 1024**2 / 1_000_000,
        "gb": 1_000,
        "gib": 1024**3 / 1_000_000,
        "tb": 1_000_000,
        "tib": 1024**4 / 1_000_000,
    }
    return round(amount * factors[unit], 3)


def parse_docker_stats_row(row):
    """Parse one JSON-formatted docker stats row into numeric metrics."""
    item = json.loads(row)
    cpu_text = str(item.get("CPUPerc", "")).strip().removesuffix("%")
    memory_text = str(item.get("MemUsage", ""))
    parts = memory_text.split("/")
    if len(parts) != 2:
        raise ValueError(f"Unrecognized Docker memory usage: {memory_text!r}")

    return {
        "name": item.get("Name") or item.get("Container"),
        "cpu_percent": float(cpu_text),
        "memory_used_mb": memory_to_mb(parts[0]),
        "memory_limit_mb": memory_to_mb(parts[1]),
    }


def sample_resources(stop_event, samples, errors):
    """Collect structured container CPU/memory metrics approximately every 2s."""
    command = ["docker", "stats", "--no-stream", "--format", "{{json .}}"]

    while not stop_event.is_set():
        try:
            result = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=8,
            )
            rows = [
                line.strip() for line in result.stdout.splitlines()
                if line.strip()
            ]
            if not rows:
                raise RuntimeError("docker stats returned no containers")

            containers = []
            for row in rows:
                try:
                    containers.append(parse_docker_stats_row(row))
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    errors.append({
                        "timestamp": utc_now(),
                        "error": f"Unable to parse docker stats row: {exc}",
                        "row": row,
                    })

            if not containers:
                raise RuntimeError("docker stats returned no parseable containers")

            samples.append({
                "timestamp": utc_now(),
                "containers": containers,
            })
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            errors.append({
                "timestamp": utc_now(),
                "error": f"{type(exc).__name__}: {exc}",
            })

        stop_event.wait(2.0)


def summarize_resources(samples):
    """Summarize peak CPU and memory for each container across all samples."""
    peaks = {}

    for sample in samples:
        for container in sample.get("containers", []):
            name = container.get("name")
            if not name:
                continue

            peak = peaks.setdefault(name, {
                "max_cpu_percent": None,
                "max_memory_used_mb": None,
                "max_memory_limit_mb": None,
            })
            for source_key, target_key in (
                ("cpu_percent", "max_cpu_percent"),
                ("memory_used_mb", "max_memory_used_mb"),
                ("memory_limit_mb", "max_memory_limit_mb"),
            ):
                value = container.get(source_key)
                if isinstance(value, (int, float)):
                    previous = peak[target_key]
                    peak[target_key] = (
                        value if previous is None else max(previous, value)
                    )

    all_cpu = [
        row["max_cpu_percent"] for row in peaks.values()
        if row["max_cpu_percent"] is not None
    ]
    all_memory = [
        row["max_memory_used_mb"] for row in peaks.values()
        if row["max_memory_used_mb"] is not None
    ]

    return {
        "container_peaks": peaks,
        "max_cpu_percent_across_containers": max(all_cpu, default=None),
        "max_memory_used_mb_across_containers": max(all_memory, default=None),
    }


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--total-requests", type=int, default=None)
    parser.add_argument("--legit-workers", type=int, default=15)
    parser.add_argument("--adversarial-workers", type=int, default=5)
    parser.add_argument("--legit-ratio", type=float, default=0.90)
    parser.add_argument(
        "--exploratory",
        action="store_true",
        help="Run a separate 6,000-request exploratory workload.",
    )
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    if args.total_requests is not None and args.total_requests < 1:
        parser.error("--total-requests must be at least 1")
    if args.legit_workers < 1 or args.adversarial_workers < 1:
        parser.error("worker counts must be at least 1")
    if not 0 <= args.legit_ratio <= 1:
        parser.error("--legit-ratio must be between 0 and 1")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    default_total = 6000 if args.exploratory else LEGITIMATE_COUNT + ATTACK_COUNT
    total_target = (
        args.total_requests if args.total_requests is not None else default_total
    )
    legitimate_target = round(total_target * args.legit_ratio)
    attack_target = total_target - legitimate_target

    default_report_path = (
        LOG_DIR / "mixed_stress_exploratory_report.json"
        if args.exploratory else REPORT_PATH
    )
    report_path = args.report or default_report_path

    report = {
        "day": 22,
        "started_at": utc_now(),
        "evidence_type": "application_layer_simulation",
        "kernel_drop_proof": False,
        "workload_mode": (
            "exploratory" if args.exploratory
            else "acceptance" if (
                args.total_requests is None and args.legit_ratio == 0.90
            )
            else "custom"
        ),
        "planned_legitimate_ratio": args.legit_ratio,
        "legitimate_workers": args.legit_workers,
        "adversarial_workers": args.adversarial_workers,
        "planned_legitimate_count": legitimate_target,
        "planned_adversarial_count": attack_target,
        "planned_workload_count": total_target,
        "overall": "FAIL",
    }

    processes = []
    streams = []
    stop_sampling = threading.Event()
    latency_samples = []
    latency_failures = []
    resource_samples = []
    resource_errors = []
    results = []

    try:
        customers, attacker, foreign_ids = prepare_customers()
        report["customer_count"] = len(customers)
        report["foreign_invoice_target_count"] = len(foreign_ids)

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["DAY21_ENFORCER_HOST"] = "127.0.0.1"
        env["DAY21_ENFORCER_PORT"] = "8004"
        env["DAY21_ATTACK_THRESHOLD"] = "3"
        env["DAY21_ATTACK_WINDOW_SECONDS"] = "10"
        env["DAY21_ATTACK_BLOCK_SECONDS"] = "20"
        env["DAY21_BILLING_UPSTREAM_URL"] = BILLING_URL
        env["DAY20_ENFORCER_URL"] = ENFORCER_URL
        env["DAY20_DIRECT_UPSTREAM_URL"] = BILLING_URL
        env["DAY20_WRAPPER_PORT"] = "8005"

        for name, script in (
            ("day22-enforcer.log", "day21_test_enforcer.py"),
            ("day22-wrapper.log", "fail_open_wrapper.py"),
        ):
            stream = (LOG_DIR / name).open("w", encoding="utf-8")
            streams.append(stream)
            process = subprocess.Popen(
                [sys.executable, str(PROJECT_ROOT / "scripts/enforcement" / script)],
                cwd=REPO_ROOT,
                env=env,
                stdout=stream,
                stderr=subprocess.STDOUT,
            )
            processes.append(process)
            if script == "day21_test_enforcer.py":
                report["enforcer_health"] = wait_for_health(
                    f"{ENFORCER_URL}/__enforcer_health", process
                )
            else:
                report["wrapper_health"] = wait_for_health(
                    f"{WRAPPER_URL}/__wrapper_health", process
                )

        latency_thread = threading.Thread(
            target=sample_latency,
            args=(stop_sampling, latency_samples, latency_failures),
            daemon=True,
        )
        resource_thread = threading.Thread(
            target=sample_resources,
            args=(stop_sampling, resource_samples, resource_errors),
            daemon=True,
        )
        latency_thread.start()
        resource_thread.start()

        # Separate pools let the configured worker counts control concurrency.
        futures = []
        with (
            ThreadPoolExecutor(max_workers=args.legit_workers) as legit_executor,
            ThreadPoolExecutor(
                max_workers=args.adversarial_workers
            ) as attack_executor,
        ):
            for index in range(legitimate_target):
                futures.append(legit_executor.submit(
                    workload_request, "legitimate", index,
                    customers, attacker, foreign_ids,
                ))
            for index in range(attack_target):
                futures.append(attack_executor.submit(
                    workload_request, "attack", index,
                    customers, attacker, foreign_ids,
                ))

            for future in as_completed(futures):
                results.append(future.result())

        # Keep sampling alive briefly to capture a final sample.
        time.sleep(1.1)
        stats_response = requests.get(
            f"{ENFORCER_URL}/__day21_stats", timeout=3
        )
        stats_response.raise_for_status()
        report["adapter_stats"] = stats_response.json()

    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        stop_sampling.set()
        for thread_name in ("latency_thread", "resource_thread"):
            thread = locals().get(thread_name)
            if thread is not None:
                thread.join(timeout=10)

        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

        for stream in streams:
            stream.close()

    legitimate = [r for r in results if r["kind"] == "legitimate"]
    attacks = [r for r in results if r["kind"] == "attack"]
    legitimate_successes = [
        r for r in legitimate
        if isinstance(r["status_code"], int)
        and 200 <= r["status_code"] < 400
    ]
    attack_blocks = [r for r in attacks if r["blocked_by_enforcement"]]

    report.update({
        "finished_at": utc_now(),
        "workload_request_count": len(results),
        "legitimate_request_count": len(legitimate),
        "legitimate_success_count": len(legitimate_successes),
        "legitimate_failure_count": len(legitimate) - len(legitimate_successes),
        "adversarial_request_count": len(attacks),
        "adversarial_blocked_count": len(attack_blocks),
        "adversarial_non_blocked_count": len(attacks) - len(attack_blocks),
        "latency_probe_count": len(latency_samples),
        "latency_probe_failure_count": len(latency_failures),
        "latency_probe_failures": latency_failures,
        "latency_probe_ms": {
            "min": min((s["latency_ms"] for s in latency_samples), default=None),
            "p50": percentile(
                [s["latency_ms"] for s in latency_samples], 50
            ),
            "median": (
                statistics.median(s["latency_ms"] for s in latency_samples)
                if latency_samples else None
            ),
            "p95": percentile(
                [s["latency_ms"] for s in latency_samples], 95
            ),
            "max": max((s["latency_ms"] for s in latency_samples), default=None),
        },
        "latency_timeline": latency_samples,
        "resource_sample_count": len(resource_samples),
        "resource_sampling_error_count": len(resource_errors),
        "resource_sampling_errors": resource_errors,
        "resource_samples": resource_samples,
        "resource_summary": summarize_resources(resource_samples),
        "workload_error_count": sum(1 for r in results if r["error"]),
        "workload_errors": [r for r in results if r["error"]][:20],
        "enforcement_was_active": (
            report.get("adapter_stats", {}).get("attack_blocked", 0) > 0
        ),
    })

    # The exploratory run is deliberately not evaluated as the 2,000-request
    # acceptance run. Its metrics are still recorded separately.
    if args.exploratory:
        # Exploratory runs are not acceptance runs, but still report execution
        # failures instead of unconditionally presenting a successful exit.
        report["checks"] = {
            "planned_workload_completed": (
                report["workload_request_count"] == report["planned_workload_count"]
            ),
            "no_workload_errors": report["workload_error_count"] == 0,
            "latency_probes_observed": report["latency_probe_count"] > 0,
            "zero_failed_latency_probes": (
                report["latency_probe_failure_count"] == 0
            ),
            "resource_samples_observed": report["resource_sample_count"] > 0,
            "resource_sampling_errors_absent": (
                report["resource_sampling_error_count"] == 0
            ),
        }
        report["overall"] = (
            "EXPLORATORY"
            if all(report["checks"].values()) and "error" not in report
            else "EXPLORATORY_FAIL"
        )
    else:
        evaluate_metrics(
            report,
            expected_legitimate_count=legitimate_target,
            expected_adversarial_count=attack_target,
        )

    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))
    print(f"\nReport written to: {report_path}")
    return 0 if report["overall"] in {"PASS", "EXPLORATORY"} else 1


if __name__ == "__main__":
    raise SystemExit(run())
