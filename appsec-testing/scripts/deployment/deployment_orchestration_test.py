#!/usr/bin/env python3
"""Day 29: guarded, project-scoped deployment orchestration validation."""

import argparse
import json
import subprocess
import sys
import time
import os
from datetime import datetime, timezone
from pathlib import Path

import requests


REPO_ROOT = Path(__file__).resolve().parents[3]
PROJECT = "api-sentinel-recovery"
PROJECT_LABEL = f"com.docker.compose.project={PROJECT}"
REPORT_PATH = (
    REPO_ROOT / "appsec-testing" / "logs"
    / "deployment_orchestration_report.json"
)

SERVICES = {
    "auth": "http://127.0.0.1:5101",
    "user": "http://127.0.0.1:5102",
    "order": "http://127.0.0.1:5103",
    "billing": "http://127.0.0.1:5104",
}

DEPLOYMENT_ENV = {
    "AUTH_HOST_PORT": "5101",
    "USER_HOST_PORT": "5102",
    "ORDER_HOST_PORT": "5103",
    "BILLING_HOST_PORT": "5104",
}

SEED_USERNAME = "alice.anderson1"
SEED_PASSWORD = "Password123!"

HEALTH_TIMEOUT_SECONDS = 120
HEALTH_REQUEST_TIMEOUT_SECONDS = 3
COMMAND_TIMEOUT_SECONDS = 900


def run_command(args, timeout=60, env=None):
    """Run a command from the repository root and return its result."""
    command_env = os.environ.copy()
    if env:
        command_env.update(env)

    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=command_env,
    )

def require_success(result, description):
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            f"{description} failed (exit {result.returncode}): {detail[-2000:]}"
        )
    return result


def parse_timestamp(value):
    """Parse a Docker RFC3339 timestamp; reject empty/zero timestamps."""
    if not isinstance(value, str) or not value or value.startswith("0001-"):
        raise ValueError(f"Invalid or missing container timestamp: {value!r}")

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def project_inventory():
    """Return project-labeled resources; never inspect or prune other projects."""
    commands = {
        "containers": [
            "docker", "ps", "-aq", "--filter", f"label={PROJECT_LABEL}"
        ],
        "volumes": [
            "docker", "volume", "ls", "-q", "--filter", f"label={PROJECT_LABEL}"
        ],
        "networks": [
            "docker", "network", "ls", "-q", "--filter", f"label={PROJECT_LABEL}"
        ],
        "images": [
            "docker", "image", "ls", "-q", "--filter", f"label={PROJECT_LABEL}"
        ],
    }

    inventory = {}
    for resource, command in commands.items():
        result = require_success(
            run_command(command, timeout=30),
            f"List project {resource}",
        )
        inventory[resource] = [
            line.strip() for line in result.stdout.splitlines() if line.strip()
        ]
    return inventory


def verify_clean_state():
    inventory = project_inventory()
    leftovers = {
        name: identifiers
        for name, identifiers in inventory.items()
        if identifiers
    }
    if leftovers:
        raise RuntimeError(
            f"Project resources remain after teardown: {leftovers}"
        )
    return inventory


def inspect_deployment_timestamps(timeout_seconds=60):
    """Wait for container metadata, then verify seed-before-app startup."""
    names = [
        "api-sentinel-seed",
        "api-sentinel-auth",
        "api-sentinel-user",
        "api-sentinel-order",
        "api-sentinel-billing",
    ]
    deadline = time.monotonic() + timeout_seconds
    containers = None
    last_error = "container metadata not available"

    while time.monotonic() < deadline:
        result = run_command(
            ["docker", "inspect", *names],
            timeout=30,
        )

        if result.returncode == 0:
            try:
                candidate = json.loads(result.stdout)
                by_name = {
                    item.get("Name", "").lstrip("/"): item
                    for item in candidate
                }

                if set(names).issubset(by_name):
                    seed_state = by_name["api-sentinel-seed"].get("State", {})
                    app_states = [
                        by_name[f"api-sentinel-{service}"].get("State", {})
                        for service in ("auth", "user", "order", "billing")
                    ]

                    metadata_ready = (
                        bool(seed_state.get("FinishedAt"))
                        and all(state.get("StartedAt") for state in app_states)
                    )
                    if metadata_ready:
                        containers = candidate
                        break
                last_error = "expected containers or timestamps not ready"
            except (json.JSONDecodeError, AttributeError, TypeError):
                last_error = "docker inspect returned incomplete or invalid JSON"
        else:
            last_error = (
                result.stderr or result.stdout or
                f"docker inspect exited {result.returncode}"
            ).strip()[-1000:]

        time.sleep(min(1, max(0, deadline - time.monotonic())))

    if containers is None:
        raise RuntimeError(
            f"Container metadata was not ready within {timeout_seconds}s: "
            f"{last_error}"
        )

    by_name = {
        item.get("Name", "").lstrip("/"): item
        for item in containers
    }

    seed_state = by_name["api-sentinel-seed"].get("State", {})
    if seed_state.get("Status") != "exited" or seed_state.get("ExitCode") != 0:
        raise RuntimeError(
            "Seed container did not exit successfully: "
            f"status={seed_state.get('Status')!r}, "
            f"exit_code={seed_state.get('ExitCode')!r}"
        )

    seed_finished = parse_timestamp(seed_state.get("FinishedAt"))
    ordering = {}

    for service in ("auth", "user", "order", "billing"):
        container_name = f"api-sentinel-{service}"
        state = by_name[container_name].get("State", {})
        app_started = parse_timestamp(state.get("StartedAt"))

        if seed_finished > app_started:
            raise RuntimeError(
                f"Seed finished after {container_name} started"
            )

        ordering[service] = {
            "seed_finished_at": seed_finished.isoformat(),
            "app_started_at": app_started.isoformat(),
            "ordering_valid": True,
        }

    return {
        "seed_exit_code": 0,
        "seed_finished_at": seed_finished.isoformat(),
        "application_start_order": ordering,
    }


def wait_for_health(timeout_seconds=HEALTH_TIMEOUT_SECONDS):
    """Poll all four health endpoints until healthy or the deadline expires."""
    deadline = time.monotonic() + timeout_seconds
    pending = set(SERVICES)
    last_results = {}

    while pending and time.monotonic() < deadline:
        for service in list(pending):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            url = f"{SERVICES[service]}/health"
            try:
                response = requests.get(
                    url,
                    timeout=min(HEALTH_REQUEST_TIMEOUT_SECONDS, remaining),
                )
                try:
                    body = response.json()
                except ValueError:
                    body = {}

                healthy = (
                    response.status_code == 200
                    and isinstance(body, dict)
                    and body.get("status") == "ok"
                )
                last_results[service] = {
                    "status_code": response.status_code,
                    "healthy": healthy,
                }
                if healthy:
                    pending.remove(service)
            except requests.RequestException as exc:
                last_results[service] = {
                    "healthy": False,
                    "error": type(exc).__name__,
                }

        if pending:
            time.sleep(min(1, max(0, deadline - time.monotonic())))

    if pending:
        raise RuntimeError(
            f"Health check deadline expired; pending={sorted(pending)}, "
            f"last_results={last_results}"
        )

    return last_results


def run_end_to_end_smoke_test():
    """Exercise login, profile, orders and invoices for the seeded account."""
    login = requests.post(
        f"{SERVICES['auth']}/api/v2/auth/login",
        json={
            "username": SEED_USERNAME,
            "password": SEED_PASSWORD,
        },
        timeout=5,
    )
    if login.status_code != 200:
        raise RuntimeError(f"Seeded-user login returned HTTP {login.status_code}")

    login_body = login.json()
    token = login_body.get("token")
    user_id = login_body.get("user_id")

    if not token or not isinstance(user_id, int):
        raise RuntimeError("Login response lacks a token or integer user_id")
    if login_body.get("token_type") != "Bearer":
        raise RuntimeError("Login response token_type is not Bearer")

    headers = {"Authorization": f"Bearer {token}"}

    verify = requests.get(
        f"{SERVICES['auth']}/api/v2/auth/verify",
        headers=headers,
        timeout=5,
    )
    if verify.status_code != 200:
        raise RuntimeError(f"Token verification returned HTTP {verify.status_code}")
    verify_body = verify.json()
    if verify_body.get("valid") is not True or verify_body.get("user_id") != user_id:
        raise RuntimeError("Token verification did not confirm the logged-in user")

    profile = requests.get(
        f"{SERVICES['user']}/api/v2/users/me",
        headers=headers,
        timeout=5,
    )
    if profile.status_code != 200:
        raise RuntimeError(f"Profile endpoint returned HTTP {profile.status_code}")
    profile_body = profile.json()

    if profile_body.get("id") != user_id:
        raise RuntimeError("Profile ID does not match the authenticated user")
    if "password_hash" in profile_body:
        raise RuntimeError("Profile response exposed password_hash")

    orders_response = requests.get(
        f"{SERVICES['order']}/api/v2/orders",
        headers=headers,
        timeout=5,
    )
    if orders_response.status_code != 200:
        raise RuntimeError(
            f"Orders endpoint returned HTTP {orders_response.status_code}"
        )
    orders = orders_response.json().get("orders")
    if not isinstance(orders, list) or not orders:
        raise RuntimeError("Orders response is missing a non-empty orders array")
    if any(order.get("user_id") != user_id for order in orders):
        raise RuntimeError("Orders response contains a record for another user")

    invoices_response = requests.get(
        f"{SERVICES['billing']}/api/v2/billing/invoices",
        headers=headers,
        timeout=5,
    )
    if invoices_response.status_code != 200:
        raise RuntimeError(
            f"Invoices endpoint returned HTTP {invoices_response.status_code}"
        )
    invoices = invoices_response.json().get("invoices")
    if not isinstance(invoices, list) or not invoices:
        raise RuntimeError(
            "Invoices response is missing a non-empty invoices array"
        )
    if any(invoice.get("owner_id") != user_id for invoice in invoices):
        raise RuntimeError("Invoices response contains a record for another user")

    # Deliberately exclude credentials, tokens and personal record contents.
    return {
        "login": "PASS",
        "token_verification": "PASS",
        "profile": "PASS",
        "profile_password_hash_excluded": True,
        "orders": "PASS",
        "orders_count": len(orders),
        "orders_owner_check": "PASS",
        "invoices": "PASS",
        "invoices_count": len(invoices),
        "invoices_owner_check": "PASS",
        "authenticated_user_id": user_id,
    }


def new_report():
    return {
        "day": 29,
        "project": PROJECT,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "overall": "FAIL",
        "steps": {},
    }


def record_step(report, name, operation):
    started = time.monotonic()
    try:
        details = operation()
        report["steps"][name] = {
            "status": "PASS",
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "details": details,
        }
        return True
    except Exception as exc:
        report["steps"][name] = {
            "status": "FAIL",
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "error": f"{type(exc).__name__}: {exc}",
        }
        return False


def mark_skipped(report, names, reason):
    for name in names:
        report["steps"][name] = {
            "status": "SKIPPED",
            "reason": reason,
        }


def execute_deployment():
    report = new_report()
    deployment_started = time.monotonic()

    teardown_ok = record_step(
        report,
        "aggressive_teardown",
        lambda: require_success(
            run_command(
                [
                    "docker", "compose", "-p", PROJECT, "down",
                    "-v", "--remove-orphans", "--rmi", "local",
                ],
                timeout=180,
            ),
            "Project-scoped Compose teardown",
        ).stdout[-2000:],
    )

    clean_ok = False
    if teardown_ok:
        clean_ok = record_step(
            report, "post_teardown_inventory", verify_clean_state
        )
    else:
        mark_skipped(
            report, ["post_teardown_inventory"],
            "Teardown failed; clean-state verification not attempted",
        )

    deploy_ok = False
    if clean_ok:
        def deploy():
            started = time.monotonic()
            result = require_success(
                run_command(
                    [
                        "docker", "compose", "-p", PROJECT,
                        "up", "--build", "-d",
                    ],
                    timeout=COMMAND_TIMEOUT_SECONDS,
                    env=DEPLOYMENT_ENV,
                ),
                "Cold deployment",
            )
            return {
                "command": f"docker compose -p {PROJECT} up --build -d",
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "stdout_tail": result.stdout[-2000:],
            }

        deploy_ok = record_step(report, "cold_deployment", deploy)
    else:
        mark_skipped(
            report, ["cold_deployment"],
            "Teardown and clean-state verification must pass first",
        )

    if deploy_ok:
        timestamps_ok = record_step(
            report, "seed_and_startup_order",
            inspect_deployment_timestamps,
        )
    else:
        timestamps_ok = False
        mark_skipped(
            report, ["seed_and_startup_order"],
            "Cold deployment did not pass",
        )

    if timestamps_ok:
        health_ok = record_step(
            report, "service_health", wait_for_health
        )
    else:
        health_ok = False
        mark_skipped(
            report, ["service_health"],
            "Seed and application startup ordering did not pass",
        )

    if health_ok:
        record_step(
            report, "end_to_end_smoke_test",
            run_end_to_end_smoke_test,
        )
    else:
        mark_skipped(
            report, ["end_to_end_smoke_test"],
            "All four health endpoints must pass first",
        )

    statuses = [
        step["status"] for step in report["steps"].values()
    ]
    report["overall"] = (
        "PASS" if statuses and all(s == "PASS" for s in statuses) else "FAIL"
    )
    report["elapsed_seconds"] = round(
        time.monotonic() - deployment_started, 3
    )
    report["finished_at"] = datetime.now(timezone.utc).isoformat()

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))
    print(f"\nReport written to: {REPORT_PATH}")
    return 0 if report["overall"] == "PASS" else 1


def main():
    parser = argparse.ArgumentParser(
        description="Day 29 deployment validation (destructive; guarded)."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Authorize project-scoped teardown and cold deployment.",
    )
    args = parser.parse_args()

    if not args.execute:
        parser.error(
            "No actions were performed. Re-run with --execute only when "
            "you explicitly approve teardown and cold deployment."
        )

    print(
        "WARNING: This will remove containers, volumes and locally built "
        f"images for Compose project {PROJECT!r}, then rebuild and start it."
    )
    return execute_deployment()


if __name__ == "__main__":
    sys.exit(main())
