#!/usr/bin/env python3
"""Guarded Day 17 BOLA -> verdict -> kernel-map -> packet-drop lab test."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
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
TTL = 20


def cmd(args, timeout=8):
    return subprocess.run(
        args, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, check=False, timeout=timeout
    )


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def ping(source, target):
    result = cmd([
        "ip", "netns", "exec", NETNS, "ping",
        "-I", source, "-c", "2", "-W", "1", target
    ], timeout=6)
    print(result.stdout.strip())
    return result


def verify_lab():
    require(os.geteuid() == 0, "Run with sudo and the project virtualenv Python.")
    require(Path(MAP_PIN).exists(), f"Pinned map missing: {MAP_PIN}")

    namespaces = cmd(["ip", "netns", "list"])
    require(
        namespaces.returncode == 0
        and any(line.split() and line.split()[0] == NETNS
                for line in namespaces.stdout.splitlines()),
        f"Disposable namespace {NETNS} is missing."
    )

    details = cmd(["ip", "-details", "link", "show", IFACE])
    require(details.returncode == 0, f"Disposable interface {IFACE} is missing.")
    require("link-netns " + NETNS in details.stdout,
            f"Refusing: {IFACE} does not show the expected namespace peer.")

    addresses = cmd(["ip", "-brief", "addr", "show", IFACE])
    require("198.18.0.1/24" in addresses.stdout,
            f"Refusing: unexpected address on {IFACE}.")

    peer = cmd(["ip", "netns", "exec", NETNS, "ip", "-brief", "addr"])
    require(
        peer.returncode == 0
        and "198.18.0.2/24" in peer.stdout
        and "198.18.0.6/24" in peer.stdout,
        "Namespace is missing the expected test IP addresses."
    )

    filt = cmd(["tc", "filter", "show", "dev", IFACE, "ingress"])
    require(
        filt.returncode == 0 and "0xa517" in filt.stdout
        and "49151" in filt.stdout,
        "The experimental ingress filter (handle 0xa517, priority 49151) "
        "must already be attached to the disposable test interface."
    )
    require(IFACE not in ("eth0", "lo"), "Unsafe interface; refusing to run.")


def make_transaction(method, uri, headers, request_body, response_body,
                     source_port, service_port):
    from app.http_reassembly import HTTPMessage
    from app.transaction_correlator import HTTPTransaction

    source = f"{BLOCKED_IP}:{source_port}"
    destination = f"198.18.0.1:{service_port}"
    request = HTTPMessage(
        version="HTTP/1.1",
        headers=headers,
        body=request_body,
        message_type="request",
        method=method,
        uri=uri,
        connection_id=f"TCP|{source}->{destination}",
        captured_at=datetime.now(timezone.utc) - timedelta(milliseconds=10),
    )
    response = HTTPMessage(
        version="HTTP/1.1",
        headers={"content-type": "application/json"},
        body=response_body,
        message_type="response",
        status_code=200,
        reason_phrase="OK",
        connection_id=f"TCP|{destination}->{source}",
    )
    return HTTPTransaction(
        connection_key=f"TCP|{source}<->{destination}",
        request=request,
        response=response,
    )


async def main():
    verify_lab()

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.blocklist_map_writer import LibbpfBlocklistMapWriter
    from app.blocklist_policy import BlocklistPolicy, ThreadOwnedVerdictSender
    from app.blocklist_sync import BlocklistSynchronizer
    from app.blocklist_verdict_client import BlocklistVerdictSender
    from app.blocklist_verdict_receiver import BlocklistVerdictReceiver
    from app.blocklist_verdicts import BlocklistVerdictProducer
    from app.database import Base
    from app.models import SecurityIncident
    from app.transaction_store import TransactionStore

    print("===== BASELINE CONNECTIVITY =====")
    require(ping(BLOCKED_IP, BLOCK_TARGET).returncode == 0,
            "Blocked-source baseline ping failed.")
    require(ping(OTHER_IP, OTHER_TARGET).returncode == 0,
            "Unrelated-source baseline ping failed.")

    cleanup = cmd([str(REPO / "ebpf-day17" / "blocklist_map_ctl"),
                   "unblock", BLOCKED_IP])
    require(cleanup.returncode == 0, cleanup.stdout)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)

    queue = asyncio.Queue(maxsize=8)
    producer = BlocklistVerdictProducer(queue, enabled=True)
    receiver = BlocklistVerdictReceiver(
        producer, endpoint="tcp://127.0.0.1:*", poll_interval_ms=10
    )
    writer = LibbpfBlocklistMapWriter(pin_path=MAP_PIN)
    synchronizer = BlocklistSynchronizer(
        queue, writer, poll_interval_s=0.01
    )
    receiver_stop = asyncio.Event()
    synchronizer_stop = asyncio.Event()
    receiver_task = asyncio.create_task(receiver.run(receiver_stop))
    synchronizer_task = asyncio.create_task(synchronizer.run(synchronizer_stop))

    sender = None
    try:
        sender = ThreadOwnedVerdictSender(
            lambda: BlocklistVerdictSender(endpoint=receiver.endpoint)
        )
        policy = BlocklistPolicy(
            sender, [BLOCKED_IP], enabled=True, ttl_seconds=TTL
        )
        store = TransactionStore(session_factory=sessions)
        store.blocklist_policy = policy

        # Allow the loopback PUSH/PULL connection to establish.
        await asyncio.sleep(0.25)

        print("===== TRIGGER CONTROLLED BOLA DETECTION =====")
        login = make_transaction(
            "POST", "/api/v2/auth/login",
            {"host": "198.18.0.1:5001", "content-type": "application/json"},
            json.dumps({"username": "lab-user", "password": "lab-password"}).encode(),
            json.dumps({
                "token": "api-sentinel-day17-runtime-token",
                "user_id": 1,
                "token_type": "Bearer",
            }).encode(),
            41000, 5001,
        )
        await asyncio.to_thread(store.save, login)

        invoice = make_transaction(
            "GET", "/api/v2/billing/invoices/3",
            {
                "host": "198.18.0.1:5004",
                "Authorization": "Bearer api-sentinel-day17-runtime-token",
            },
            b"",
            json.dumps({"id": 3, "owner_id": 2, "status": "paid"}).encode(),
            41001, 5004,
        )
        await asyncio.to_thread(store.save, invoice)

        with sessions() as session:
            incidents = list(session.scalars(select(SecurityIncident)).all())
        require(len(incidents) == 1,
                f"Expected one lab BOLA incident; found {len(incidents)}.")
        require(incidents[0].source_ip == BLOCKED_IP,
                f"Unexpected incident source IP: {incidents[0].source_ip}")
        print(f"PASS: persisted incident id={incidents[0].id}, "
              f"source={incidents[0].source_ip}")

        # Poll metrics instead of assuming queue.join() waits for future arrivals.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 5.0
        while loop.time() < deadline:
            rm = receiver.snapshot()
            sm = synchronizer.snapshot()
            if (rm["receiver_messages_accepted"] >= 1
                    and sm["applied_count"] >= 1):
                break
            await asyncio.sleep(0.02)

        await asyncio.wait_for(queue.join(), timeout=2.0)
        rm, sm, pm = receiver.snapshot(), synchronizer.snapshot(), policy.snapshot()
        print("Policy:", pm)
        print("Receiver:", rm)
        print("Synchronizer:", sm)

        require(pm["submitted_count"] == 1, "Policy did not submit one verdict.")
        require(rm["receiver_messages_accepted"] == 1,
                "Receiver did not accept exactly one verdict.")
        require(sm["applied_count"] == 1 and sm["failed_count"] == 0,
                "Kernel synchronizer did not apply one verdict successfully.")

        shown = cmd([str(REPO / "ebpf-day17" / "blocklist_map_ctl"),
                     "show", BLOCKED_IP])
        print("===== REAL PINNED MAP =====")
        print(shown.stdout.strip())
        require(shown.returncode == 0 and "expires in approximately" in shown.stdout,
                "Temporary source entry not found in the pinned kernel map.")

        print("===== ACTIVE VERDICT MUST DROP TRAFFIC =====")
        blocked = ping(BLOCKED_IP, BLOCK_TARGET)
        require(blocked.returncode != 0 and "0 received" in blocked.stdout,
                "Blocked source unexpectedly received ping replies.")
        print("PASS: active verdict caused test traffic to be dropped.")

        print("===== UNRELATED SOURCE MUST PASS =====")
        unrelated = ping(OTHER_IP, OTHER_TARGET)
        require(unrelated.returncode == 0 and "2 received" in unrelated.stdout,
                "Unrelated source was not allowed.")
        print("PASS: unrelated source continued to pass.")

        wait_seconds = TTL + 2
        print(f"===== WAIT {wait_seconds}s FOR EXPIRY =====")
        await asyncio.sleep(wait_seconds)
        expired = ping(BLOCKED_IP, BLOCK_TARGET)
        require(expired.returncode == 0 and "2 received" in expired.stdout,
                "Expired verdict still blocks traffic, or test network failed.")
        print("PASS: expired verdict no longer blocks test traffic.")
        print("DAY 17 RUNTIME E2E: PASS")

    finally:
        if sender is not None:
            sender.close()

        receiver_stop.set()
        try:
            await asyncio.wait_for(receiver_task, timeout=1.5)
        except asyncio.TimeoutError:
            receiver_task.cancel()
            await asyncio.gather(receiver_task, return_exceptions=True)
        finally:
            receiver.close()

        synchronizer_stop.set()
        try:
            await asyncio.wait_for(synchronizer_task, timeout=2.0)
        except asyncio.TimeoutError:
            synchronizer_task.cancel()
            await asyncio.gather(synchronizer_task, return_exceptions=True)

        writer.close()
        engine.dispose()
        final_cleanup = cmd([
            str(REPO / "ebpf-day17" / "blocklist_map_ctl"),
            "unblock", BLOCKED_IP
        ])
        print("Cleanup:", final_cleanup.stdout.strip())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f"DAY 17 RUNTIME E2E: FAIL: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        raise
