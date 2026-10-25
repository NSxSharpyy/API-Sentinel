#!/usr/bin/env python3
"""Day 17 application-lifecycle E2E test for a disposable WSL lab.

It exercises the real FastAPI lifespan, HTTP parser/correlator, persistence
worker, BOLA policy, loopback verdict receiver, synchronizer and pinned kernel
map. The capture supervisor is stubbed only in this test process to avoid
launching the machine's capture reader; input HTTP bytes are synthetic. The
actual packet-drop classifier must already be attached to the isolated
api-sntl-test0 interface.

Run with sudo and .venv/bin/python after preparing the disposable veth lab.
Never target eth0 or lo.
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

IFACE = "api-sntl-test0"
NETNS = "api-sntl-testns"
BLOCKED_IP = "198.18.0.2"
BLOCK_TARGET = "198.18.0.1"
OTHER_IP = "198.18.0.6"
OTHER_TARGET = "198.18.0.5"
MAP_PIN = "/sys/fs/bpf/api_sentinel_day17_blocklist"
TTL_SECONDS = 20


def command(args: list[str], timeout: float = 8.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        check=False, timeout=timeout,
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def verify_disposable_lab() -> None:
    require(os.geteuid() == 0, "Run with sudo and the repository virtualenv Python.")
    require(Path(MAP_PIN).exists(), f"Pinned blocklist map is missing: {MAP_PIN}")
    require(IFACE not in {"eth0", "lo"}, "Refusing to run on a non-disposable interface.")

    namespaces = command(["ip", "netns", "list"])
    require(
        namespaces.returncode == 0
        and any(row.split() and row.split()[0] == NETNS for row in namespaces.stdout.splitlines()),
        f"Disposable namespace {NETNS} is missing.",
    )
    link = command(["ip", "-details", "link", "show", IFACE])
    require(link.returncode == 0, f"Disposable interface {IFACE} is missing.")
    require(f"link-netns {NETNS}" in link.stdout,
            f"Refusing: {IFACE} is not paired with {NETNS}.")

    addresses = command(["ip", "-brief", "addr", "show", IFACE])
    require("198.18.0.1/24" in addresses.stdout and "198.18.0.5/24" in addresses.stdout,
            "Host-side test destinations do not match the expected lab IPs.")
    peer = command(["ip", "netns", "exec", NETNS, "ip", "-brief", "addr"])
    require("198.18.0.2/24" in peer.stdout and "198.18.0.6/24" in peer.stdout,
            "Namespace test sources do not match the expected lab IPs.")
    tc = command(["tc", "filter", "show", "dev", IFACE, "ingress"])
    require(tc.returncode == 0 and "0xa517" in tc.stdout and "49151" in tc.stdout,
            "Attach the experimental filter (handle 0xa517, priority 49151) to api-sntl-test0 first.")


def ping(source: str, target: str) -> subprocess.CompletedProcess[str]:
    result = command(
        ["ip", "netns", "exec", NETNS, "ping", "-I", source, "-c", "2", "-W", "1", target],
        timeout=6,
    )
    print(result.stdout.strip())
    return result


def build_http_transaction_bytes(
    method: str,
    path: str,
    headers: dict[str, str],
    body: bytes,
    *,
    source_ip: str,
    source_port: int,
    destination_ip: str,
    destination_port: int,
) -> tuple[str, str, bytes, bytes]:
    request_headers = dict(headers)
    request_headers.setdefault("Host", f"{destination_ip}:{destination_port}")
    if body:
        request_headers.setdefault("Content-Type", "application/json")
        request_headers["Content-Length"] = str(len(body))
    else:
        request_headers.pop("Content-Length", None)

    request_line = f"{method} {path} HTTP/1.1\r\n".encode("ascii")
    raw_request = request_line + b"".join(
        f"{key}: {value}\r\n".encode("latin-1") for key, value in request_headers.items()
    ) + b"\r\n" + body

    connection = (
        f"TCP|{source_ip}:{source_port}->{destination_ip}:{destination_port}"
    )
    reverse_connection = (
        f"TCP|{destination_ip}:{destination_port}->{source_ip}:{source_port}"
    )
    return connection, reverse_connection, raw_request, body


def raw_response(body: bytes) -> bytes:
    headers = (
        b"HTTP/1.1 200 OK\r\n"
        b"Content-Type: application/json\r\n"
        + f"Content-Length: {len(body)}\r\n".encode("ascii")
        + b"Connection: keep-alive\r\n\r\n"
    )
    return headers + body


async def idle_capture_supervisor(_command, stop_event, on_status=None):
    """Do not start the external ring-buffer reader during this synthetic test."""
    if on_status is not None:
        on_status("test_stubbed")
    await stop_event.wait()


def choose_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


async def run_application_test() -> None:
    from app import main as main_module
    from app.database import SessionLocal, engine
    from app.models import SecurityIncident, TransactionLog
    from sqlalchemy import select

    # Avoid conflicts with a separately running local publisher. This is an
    # actual publisher instance but uses an ephemeral loopback TCP port.
    real_publisher_class = main_module.HTTPTransactionPublisher
    main_module.HTTPTransactionPublisher = lambda: real_publisher_class(
        endpoint="tcp://127.0.0.1:*"
    )
    # The test injects raw HTTP bytes directly into the real parser. The
    # external eBPF/ring-reader supervisor is intentionally not launched here.
    main_module.supervise_capture = idle_capture_supervisor

    map_ctl = str(REPO / "ebpf-day17" / "blocklist_map_ctl")
    result = command([map_ctl, "unblock", BLOCKED_IP])
    require(result.returncode == 0, f"Could not clear stale lab entry: {result.stdout}")

    require(ping(BLOCKED_IP, BLOCK_TARGET).returncode == 0,
            "Blocked-source baseline ping must pass before the test.")
    require(ping(OTHER_IP, OTHER_TARGET).returncode == 0,
            "Unrelated-source baseline ping must pass before the test.")

    app = main_module.app
    try:
        async with main_module.lifespan(app):
            require(app.state.blocklist_sync_enabled is True,
                    "Application blocklist sync was not enabled.")
            require(app.state.blocklist_policy is not None and app.state.blocklist_policy.enabled,
                    "Application blocklist policy was not enabled.")
            require(app.state.blocklist_verdict_receiver_task is not None
                    and not app.state.blocklist_verdict_receiver_task.done(),
                    "Application verdict receiver task did not start.")
            require(app.state.blocklist_sync_task is not None
                    and not app.state.blocklist_sync_task.done(),
                    "Application synchronizer task did not start.")

            pipeline = app.state.http_pipeline
            persistence = app.state.persistence_worker
            started_at = datetime.now(timezone.utc)

            print("===== FEED SYNTHETIC HTTP LOGIN INTO REAL PIPELINE =====")
            login_body = json.dumps({
                "username": "day17-lab-user", "password": "day17-lab-password"
            }, separators=(",", ":")).encode("utf-8")
            login_conn, login_rev, login_request, _ = build_http_transaction_bytes(
                "POST", "/api/v2/auth/login",
                {"Content-Type": "application/json"}, login_body,
                source_ip=BLOCKED_IP, source_port=41000,
                destination_ip=BLOCK_TARGET, destination_port=5001,
            )
            login_response_body = json.dumps({
                "token": "api-sentinel-day17-lifecycle-token",
                "user_id": 41,
                "token_type": "Bearer",
            }, separators=(",", ":")).encode("utf-8")
            pipeline.feed(login_request, connection_id=login_conn, captured_at=started_at)
            pipeline.feed(raw_response(login_response_body), connection_id=login_rev,
                          captured_at=datetime.now(timezone.utc))

            deadline = asyncio.get_running_loop().time() + 5.0
            while persistence.persisted_count < 1 and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.02)
            require(persistence.persisted_count == 1 and persistence.failed_count == 0,
                    f"Login transaction persistence failed: {persistence.persisted_count=}, {persistence.failed_count=}")

            print("===== FEED CROSS-OWNER INVOICE REQUEST INTO REAL PIPELINE =====")
            invoice_body = json.dumps({
                "id": 3, "owner_id": 99, "status": "paid"
            }, separators=(",", ":")).encode("utf-8")
            invoice_conn, invoice_rev, invoice_request, _ = build_http_transaction_bytes(
                "GET", "/api/v2/billing/invoices/3",
                {"Authorization": "Bearer api-sentinel-day17-lifecycle-token"}, b"",
                source_ip=BLOCKED_IP, source_port=41001,
                destination_ip=BLOCK_TARGET, destination_port=5004,
            )
            pipeline.feed(invoice_request, connection_id=invoice_conn,
                          captured_at=datetime.now(timezone.utc))
            pipeline.feed(raw_response(invoice_body), connection_id=invoice_rev,
                          captured_at=datetime.now(timezone.utc))

            deadline = asyncio.get_running_loop().time() + 5.0
            while persistence.persisted_count < 2 and asyncio.get_running_loop().time() < deadline:
                await asyncio.sleep(0.02)
            require(persistence.persisted_count == 2 and persistence.failed_count == 0,
                    f"Invoice persistence did not complete: {persistence.persisted_count=}, {persistence.failed_count=}")

            with SessionLocal() as session:
                incidents = list(session.scalars(select(SecurityIncident)).all())
                transactions = list(session.scalars(select(TransactionLog)).all())
            require(len(transactions) == 2, f"Expected 2 persisted HTTP transactions, found {len(transactions)}")
            require(len(incidents) == 1, f"Expected one lab BOLA incident, found {len(incidents)}")
            require(incidents[0].source_ip == BLOCKED_IP,
                    f"Incident source mismatch: {incidents[0].source_ip}")
            require(incidents[0].endpoint_id is not None,
                    "BOLA incident was not associated with discovered endpoint.")
            print(f"PASS: persisted BOLA incident {incidents[0].id} for {BLOCKED_IP}; endpoint_id={incidents[0].endpoint_id}")

            deadline = asyncio.get_running_loop().time() + 5.0
            while asyncio.get_running_loop().time() < deadline:
                receiver_metrics = app.state.blocklist_verdict_receiver.snapshot()
                sync_metrics = app.state.blocklist_synchronizer.snapshot()
                if (receiver_metrics["receiver_messages_accepted"] >= 1
                        and sync_metrics["applied_count"] >= 1):
                    break
                await asyncio.sleep(0.02)
            await asyncio.wait_for(app.state.blocklist_verdict_producer.verdict_queue.join(), timeout=2.0)

            policy_metrics = app.state.blocklist_policy.snapshot()
            receiver_metrics = app.state.blocklist_verdict_receiver.snapshot()
            sync_metrics = app.state.blocklist_synchronizer.snapshot()
            print("Policy:", policy_metrics)
            print("Receiver:", receiver_metrics)
            print("Synchronizer:", sync_metrics)
            require(policy_metrics["submitted_count"] == 1 and policy_metrics["failed_count"] == 0,
                    "Application policy did not submit exactly one successful verdict.")
            require(receiver_metrics["receiver_messages_accepted"] == 1
                    and receiver_metrics["receiver_messages_rejected"] == 0,
                    "Application receiver did not accept exactly one verdict without rejection.")
            require(sync_metrics["applied_count"] == 1 and sync_metrics["failed_count"] == 0,
                    "Application synchronizer did not apply exactly one map update.")

            map_result = command([map_ctl, "show", BLOCKED_IP])
            print("===== APPLICATION-LIFECYCLE KERNEL MAP =====")
            print(map_result.stdout.strip())
            require(map_result.returncode == 0 and "expires in approximately" in map_result.stdout,
                    "Temporary block entry is not visible in the pinned kernel map.")

            print("===== ACTIVE VERDICT PACKET TEST =====")
            blocked = ping(BLOCKED_IP, BLOCK_TARGET)
            require(blocked.returncode != 0 and "0 received" in blocked.stdout,
                    "Active application-lifecycle verdict did not drop matching traffic.")
            unrelated = ping(OTHER_IP, OTHER_TARGET)
            require(unrelated.returncode == 0 and "2 received" in unrelated.stdout,
                    "Unrelated traffic was not allowed while the block was active.")

            print(f"===== WAIT {TTL_SECONDS + 2}s FOR EXPIRY =====")
            await asyncio.sleep(TTL_SECONDS + 2)
            expired = ping(BLOCKED_IP, BLOCK_TARGET)
            require(expired.returncode == 0 and "2 received" in expired.stdout,
                    "Traffic did not recover after verdict expiry.")
            print("DAY 17 APP-LIFECYCLE RUNTIME E2E: PASS")
    finally:
        cleanup = command([map_ctl, "unblock", BLOCKED_IP])
        print("Map cleanup:", cleanup.stdout.strip())
        engine.dispose()


def main() -> None:
    verify_disposable_lab()
    with tempfile.TemporaryDirectory(prefix="api-sentinel-day17-") as temp_dir:
        os.environ["DATABASE_URL"] = f"sqlite:///{Path(temp_dir) / 'day17-e2e.db'}"
        os.environ["API_SENTINEL_BLOCKLIST_SYNC_ENABLED"] = "1"
        os.environ["API_SENTINEL_BLOCKLIST_POLICY_ENABLED"] = "1"
        os.environ["API_SENTINEL_BLOCKLIST_ALLOWED_SOURCE_IPS"] = BLOCKED_IP
        os.environ["API_SENTINEL_BLOCKLIST_VERDICT_TTL_SECONDS"] = str(TTL_SECONDS)
        os.environ["API_SENTINEL_BLOCKLIST_VERDICT_ENDPOINT"] = f"tcp://127.0.0.1:{choose_loopback_port()}"
        asyncio.run(run_application_test())


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"DAY 17 APP-LIFECYCLE E2E: FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
