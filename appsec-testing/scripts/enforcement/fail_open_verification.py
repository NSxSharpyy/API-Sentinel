
#!/usr/bin/env python3
"""Day 20 fail-open and fail-closed verification.

The HTTP enforcer and fail-closed proxy are lab simulations.
This does not prove real TC/eBPF enforcement behavior.
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
LOGS = PROJECT / "logs"
REPORT = LOGS / "fail_open_report.json"

ENFORCER_SCRIPT = HERE / "day20_test_enforcer.py"
WRAPPER_SCRIPT = HERE / "fail_open_wrapper.py"
FAIL_CLOSED_SCRIPT = HERE / "day20_fail_closed_proxy.py"

ENFORCER_URL = "http://127.0.0.1:8004"
WRAPPER_URL = "http://127.0.0.1:8005"
FAIL_CLOSED_URL = "http://127.0.0.1:8006"
BILLING_URL = "http://127.0.0.1:5004"

STARTUP_TIMEOUT = 8.0
REQUEST_TIMEOUT = 4.0
POLL_INTERVAL = 0.15


def port_is_free(port):
    """Check whether a local TCP port can be bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def wait_for(predicate, timeout=STARTUP_TIMEOUT):
    """Poll a condition until it succeeds or the deadline expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(POLL_INTERVAL)
    return False


def http_health(url):
    """Return a health response when an endpoint returns HTTP 200."""
    try:
        response = requests.get(url, timeout=REQUEST_TIMEOUT)
        return response if response.status_code == 200 else None
    except requests.RequestException:
        return None


def record_check(report, name, passed, details):
    """Record one verification result."""
    report["checks"][name] = {
        "passed": bool(passed),
        "details": details,
    }


def traffic_probe_worker(state, records, lock):
    """Continuously probe the fail-open wrapper and record responses."""
    while not state["stop"]:
        phase = state["phase"]
        started = time.monotonic()

        record = {
            "phase": phase,
            "started": started,
            "status_code": None,
            "enforcement_active": None,
            "routing_mode": None,
            "test_enforcer_header": False,
            "error": None,
            "elapsed_ms": None,
        }

        try:
            response = requests.get(
                f"{WRAPPER_URL}/health",
                timeout=(0.5, 1.5),
            )
            record.update({
                "status_code": response.status_code,
                "enforcement_active": response.headers.get(
                    "X-Enforcement-Active"
                ),
                "routing_mode": response.headers.get(
                    "X-Fail-Open-Mode"
                ),
                "test_enforcer_header": (
                    response.headers.get("X-Day20-Test-Enforcer")
                    == "active"
                ),
            })
        except requests.RequestException as exc:
            record["error"] = type(exc).__name__

        record["elapsed_ms"] = round(
            (time.monotonic() - started) * 1000,
            2,
        )

        with lock:
            records.append(record)

        # Avoid overwhelming the lab services.
        time.sleep(0.05)


def summarize_phase(records, phase):
    """Summarize continuous probes recorded during one phase."""
    selected = [item for item in records if item["phase"] == phase]
    successful = [
        item for item in selected if item["status_code"] == 200
    ]
    failed = [
        item for item in selected if item["status_code"] != 200
    ]

    return {
        "requests_total": len(selected),
        "requests_200": len(successful),
        "requests_failed_or_non_200": len(failed),
        "enforced_responses": sum(
            item["routing_mode"] == "enforced"
            and item["test_enforcer_header"]
            for item in selected
        ),
        "bypass_responses": sum(
            item["routing_mode"] == "bypass"
            and item["enforcement_active"] == "false"
            and not item["test_enforcer_header"]
            for item in selected
        ),
        "request_errors": sum(
            item["error"] is not None for item in selected
        ),
        "max_request_latency_ms": max(
            (item["elapsed_ms"] for item in selected),
            default=None,
        ),
    }


def main():
    LOGS.mkdir(parents=True, exist_ok=True)

    report = {
        "schema_version": 1,
        "test": "day20_fail_open_simulation",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "architecture": (
            "Application-layer HTTP simulation; not proof of real "
            "TC/eBPF daemon failure behavior."
        ),
        "ports": {
            "billing": 5004,
            "test_enforcer": 8004,
            "fail_open_wrapper": 8005,
            "fail_closed_proxy": 8006,
        },
        "checks": {},
        "timings_ms": {},
        "overall": "FAIL",
    }

    # Initialize process and log handles so cleanup is safe on early failure.
    enforcer = None
    wrapper = None
    fail_closed_proxy = None

    enforcer_log = None
    wrapper_log = None
    fail_closed_log = None

    probe_state = {"phase": "starting", "stop": False}
    probe_records = []
    probe_lock = threading.Lock()
    probe_thread = None

    try:
        # Do not interfere with processes already using these ports.
        for port in (8004, 8005, 8006):
            if not port_is_free(port):
                raise RuntimeError(
                    f"Port {port} is already in use; refusing to continue."
                )

        # Confirm that the existing billing service is healthy.
        billing_response = http_health(f"{BILLING_URL}/health")

        record_check(
            report,
            "billing_preflight",
            billing_response is not None,
            {
                "url": f"{BILLING_URL}/health",
                "status_code": (
                    billing_response.status_code
                    if billing_response else None
                ),
            },
        )

        if billing_response is None:
            raise RuntimeError(
                "Billing health check failed; start the existing services first."
            )

        # Open separate logs for each process.
        enforcer_log = open(
            LOGS / "day20_test_enforcer.log",
            "w",
            encoding="utf-8",
        )
        wrapper_log = open(
            LOGS / "day20_fail_open_wrapper.log",
            "w",
            encoding="utf-8",
        )
        fail_closed_log = open(
            LOGS / "day20_fail_closed_proxy.log",
            "w",
            encoding="utf-8",
        )

        # Start the simulated HTTP enforcer on port 8004.
        enforcer = subprocess.Popen(
            [sys.executable, str(ENFORCER_SCRIPT)],
            cwd=PROJECT,
            stdout=enforcer_log,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
        )

        enforcer_ready = wait_for(
            lambda: http_health(
                f"{ENFORCER_URL}/__enforcer_health"
            ) is not None
        )

        record_check(
            report,
            "test_enforcer_started",
            enforcer_ready,
            {"pid": enforcer.pid, "port": 8004},
        )

        if not enforcer_ready:
            raise RuntimeError("Simulated test enforcer did not become healthy.")

        # Start the fail-closed proxy on port 8006 while the enforcer is healthy.
        fail_closed_proxy = subprocess.Popen(
            [sys.executable, str(FAIL_CLOSED_SCRIPT)],
            cwd=PROJECT,
            stdout=fail_closed_log,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
        )

        fail_closed_ready = wait_for(
            lambda: http_health(
                f"{FAIL_CLOSED_URL}/__fail_closed_proxy_health"
            ) is not None
        )

        record_check(
            report,
            "fail_closed_proxy_started",
            fail_closed_ready,
            {
                "pid": fail_closed_proxy.pid,
                "port": 8006,
            },
        )

        if not fail_closed_ready:
            raise RuntimeError("Fail-closed proxy did not become healthy.")

        # Start the existing fail-open wrapper on port 8005.
        wrapper = subprocess.Popen(
            [sys.executable, str(WRAPPER_SCRIPT)],
            cwd=PROJECT,
            stdout=wrapper_log,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
        )

        wrapper_ready = wait_for(
            lambda: http_health(
                f"{WRAPPER_URL}/__wrapper_health"
            ) is not None
        )

        record_check(
            report,
            "wrapper_started",
            wrapper_ready,
            {"pid": wrapper.pid, "port": 8005},
        )

        if not wrapper_ready:
            raise RuntimeError("Fail-open wrapper did not become healthy.")

        # Verify the fail-closed proxy enforces when the enforcer is healthy.
        try:
            response = requests.get(
                f"{FAIL_CLOSED_URL}/health",
                timeout=REQUEST_TIMEOUT,
            )

            fail_closed_healthy_pass = (
                response.status_code == 200
                and response.headers.get(
                    "X-Day20-Test-Enforcer"
                ) == "active"
                and response.headers.get(
                    "X-Fail-Closed-Mode"
                ) == "enforced"
                and response.headers.get(
                    "X-Enforcement-Active"
                ) == "true"
            )

            healthy_details = {
                "status_code": response.status_code,
                "enforcer_header": response.headers.get(
                    "X-Day20-Test-Enforcer"
                ),
                "routing_mode": response.headers.get(
                    "X-Fail-Closed-Mode"
                ),
                "enforcement_active": response.headers.get(
                    "X-Enforcement-Active"
                ),
            }

        except requests.RequestException as exc:
            fail_closed_healthy_pass = False
            healthy_details = {"error": type(exc).__name__}

        record_check(
            report,
            "fail_closed_proxy_enforces_when_available",
            fail_closed_healthy_pass,
            healthy_details,
        )

        # Start continuous probes through the fail-open wrapper.
        probe_state["phase"] = "healthy"
        probe_thread = threading.Thread(
            target=traffic_probe_worker,
            args=(probe_state, probe_records, probe_lock),
            daemon=True,
        )
        probe_thread.start()

        # Phase 1: normal traffic should pass through the live enforcer.
        time.sleep(1.0)

        with probe_lock:
            healthy_results = [
                item for item in probe_records
                if item["phase"] == "healthy"
            ]

        healthy_pass = (
            bool(healthy_results)
            and any(
                item["status_code"] == 200
                and item["routing_mode"] == "enforced"
                and item["test_enforcer_header"]
                for item in healthy_results
            )
        )

        record_check(
            report,
            "legitimate_traffic_through_enforcer",
            healthy_pass,
            summarize_phase(probe_records, "healthy"),
        )

        # Phase 2: stop only the simulated HTTP enforcer.
        failure_time = time.monotonic()
        enforcer.kill()
        enforcer.wait(timeout=3)
        probe_state["phase"] = "failure"

        report["enforcer_termination"] = {
            "method": "SIGKILL via subprocess.kill()",
            "exit_code": enforcer.returncode,
            "target": "Day 20 simulated HTTP enforcer process only",
        }

        # Wait for the fail-open wrapper to bypass to billing successfully.
        fail_open_deadline = time.monotonic() + STARTUP_TIMEOUT
        fail_open_observed_at = None

        while time.monotonic() < fail_open_deadline:
            with probe_lock:
                observed = any(
                    item["phase"] == "failure"
                    and item["status_code"] == 200
                    and item["routing_mode"] == "bypass"
                    and item["enforcement_active"] == "false"
                    and not item["test_enforcer_header"]
                    for item in probe_records
                )

            if observed:
                fail_open_observed_at = time.monotonic()
                break

            time.sleep(POLL_INTERVAL)

        report["timings_ms"]["fail_open_transition"] = (
            round(
                (fail_open_observed_at - failure_time) * 1000,
                2,
            )
            if fail_open_observed_at is not None else None
        )

        # Collect more samples in the failure phase.
        time.sleep(0.5)
        failure_summary = summarize_phase(probe_records, "failure")

        fail_open_pass = (
            fail_open_observed_at is not None
            and failure_summary["bypass_responses"] > 0
        )

        record_check(
            report,
            "legitimate_traffic_survives_enforcer_failure",
            fail_open_pass,
            failure_summary,
        )

        # Negative control: the fail-closed proxy must reject requests while
        # the enforcer is stopped. It must not bypass to billing.
        try:
            control_response = requests.get(
                f"{FAIL_CLOSED_URL}/health",
                timeout=(0.3, 1.0),
            )

            control_status = control_response.status_code
            control_routing_mode = control_response.headers.get(
                "X-Fail-Closed-Mode"
            )
            control_enforcement_active = control_response.headers.get(
                "X-Enforcement-Active"
            )

            try:
                control_body = control_response.json()
                control_error = control_body.get("error")
            except (ValueError, AttributeError):
                control_error = None

            control_failed_closed = (
                control_status == 503
                and control_routing_mode == "reject"
                and control_enforcement_active == "false"
            )

            control_details = {
                "description": (
                    "Separate simulated fail-closed proxy rejects "
                    "requests when the test enforcer is stopped. "
                    "Application-layer simulation only; not proof "
                    "of real TC/eBPF behavior."
                ),
                "status_code": control_status,
                "routing_mode": control_routing_mode,
                "enforcement_active": control_enforcement_active,
                "error": control_error,
            }

        except requests.RequestException as exc:
            # An unreachable proxy is not evidence of fail-closed behavior.
            control_failed_closed = False
            control_details = {
                "description": (
                    "The fail-closed proxy must remain reachable and "
                    "return HTTP 503 when enforcement is unavailable."
                ),
                "error": type(exc).__name__,
            }

        record_check(
            report,
            "stopped_enforcer_negative_control",
            control_failed_closed,
            control_details,
        )

        # Phase 3: restart the simulated enforcer and verify recovery.
        probe_state["phase"] = "restart_transition"
        recovery_start = time.monotonic()

        enforcer = subprocess.Popen(
            [sys.executable, str(ENFORCER_SCRIPT)],
            cwd=PROJECT,
            stdout=enforcer_log,
            stderr=subprocess.STDOUT,
            env=os.environ.copy(),
        )

        enforcer_ready = wait_for(
            lambda: http_health(
                f"{ENFORCER_URL}/__enforcer_health"
            ) is not None
        )

        record_check(
            report,
            "test_enforcer_restarted",
            enforcer_ready,
            {"pid": enforcer.pid, "port": 8004},
        )

        if enforcer_ready:
            # Observe recovery only after the enforcer is healthy.
            probe_state["phase"] = "recovery"

        recovery_deadline = time.monotonic() + STARTUP_TIMEOUT
        enforcement_recovered_at = None

        while enforcer_ready and time.monotonic() < recovery_deadline:
            with probe_lock:
                recovered = any(
                    item["phase"] == "recovery"
                    and item["status_code"] == 200
                    and item["routing_mode"] == "enforced"
                    and item["enforcement_active"] == "true"
                    and item["test_enforcer_header"]
                    for item in probe_records
                )

            if recovered:
                enforcement_recovered_at = time.monotonic()
                break

            time.sleep(POLL_INTERVAL)

        report["timings_ms"]["enforcement_recovery"] = (
            round(
                (enforcement_recovered_at - recovery_start) * 1000,
                2,
            )
            if enforcement_recovered_at is not None else None
        )

        time.sleep(0.5)
        recovery_summary = summarize_phase(probe_records, "recovery")

        recovery_pass = (
            enforcement_recovered_at is not None
            and recovery_summary["enforced_responses"] > 0
        )

        record_check(
            report,
            "enforcement_resumes_after_restart",
            recovery_pass,
            recovery_summary,
        )

        # Stop the worker and summarize all recorded traffic phases.
        probe_state["phase"] = "finished"
        time.sleep(0.1)
        probe_state["stop"] = True
        probe_thread.join(timeout=3)

        report["traffic_summary"] = {
            phase: summarize_phase(probe_records, phase)
            for phase in (
                "healthy",
                "failure",
                "restart_transition",
                "recovery",
            )
        }

        # Verify the existing billing service remains healthy.
        billing_after = http_health(f"{BILLING_URL}/health")

        record_check(
            report,
            "billing_remains_healthy",
            billing_after is not None,
            {
                "status_code": (
                    billing_after.status_code
                    if billing_after else None
                ),
            },
        )

        # Every required check must pass for the overall gate to pass.
        required_checks = (
            "billing_preflight",
            "test_enforcer_started",
            "fail_closed_proxy_started",
            "wrapper_started",
            "fail_closed_proxy_enforces_when_available",
            "legitimate_traffic_through_enforcer",
            "legitimate_traffic_survives_enforcer_failure",
            "stopped_enforcer_negative_control",
            "test_enforcer_restarted",
            "enforcement_resumes_after_restart",
            "billing_remains_healthy",
        )

        report["required_checks"] = list(required_checks)
        report["overall"] = (
            "PASS"
            if all(
                report["checks"].get(name, {}).get("passed", False)
                for name in required_checks
            )
            else "FAIL"
        )

    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["overall"] = "FAIL"

    finally:
        # Always stop only the child processes created by this script.
        probe_state["stop"] = True

        if probe_thread is not None and probe_thread.is_alive():
            probe_thread.join(timeout=3)

        for process in (wrapper, fail_closed_proxy, enforcer):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)

        for handle in (wrapper_log, fail_closed_log, enforcer_log):
            if handle is not None:
                handle.close()

        report["finished_at_utc"] = datetime.now(
            timezone.utc
        ).isoformat()

        REPORT.write_text(
            json.dumps(report, indent=2) + "\n",
            encoding="utf-8",
        )

        print(json.dumps(report, indent=2))
        print(f"\nReport written to: {REPORT}")

    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
