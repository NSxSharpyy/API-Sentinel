#!/usr/bin/env python3
"""End-to-end Phase 1 validation for API-Sentinel."""
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
APPSEC = ROOT / "appsec-testing"
SCRIPTS = APPSEC / "scripts"
LOGS = APPSEC / "logs"
DOCS = ROOT / "docs"
BASE = "http://127.0.0.1"
PASSWORD = "Password123!"
SERVICES = {
    "auth": f"{BASE}:5001/health",
    "user": f"{BASE}:5002/health",
    "order": f"{BASE}:5003/health",
    "billing": f"{BASE}:5004/health",
}

LOGS.mkdir(parents=True, exist_ok=True)
DOCS.mkdir(parents=True, exist_ok=True)
RUN_DIR = LOGS / ("phase1-run-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
RUN_DIR.mkdir(parents=True, exist_ok=True)
REPORT_PATH = LOGS / "phase1_freeze_report.json"
checks = []
server = None
server_log = None


def record(name, passed, details=None):
    item = {
        "name": name,
        "status": "PASS" if passed else "FAIL",
        "details": details or {},
    }
    checks.append(item)
    print(f"[{item['status']}] {name}")
    if details:
        print("       " + json.dumps(details, default=str))


def command(name, args, log_path, cwd=ROOT, timeout=180, env=None):
    """Run a command, save full output, and return its result."""
    try:
        result = subprocess.run(
            args, cwd=cwd, env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        Path(log_path).write_text(result.stdout, encoding="utf-8")
        record(
            name, result.returncode == 0,
            {
                "returncode": result.returncode,
                "log": str(log_path),
                "output_tail": result.stdout[-1800:],
            },
        )
        return result
    except (OSError, subprocess.TimeoutExpired) as exc:
        record(name, False, {"error": str(exc), "log": str(log_path)})
        return None


def database_counts():
    query = r'''
import sqlite3, json
conn = sqlite3.connect("/app/data/shop.db")
try:
    counts = {
        "customers": conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0],
        "orders": conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        "invoices": conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0],
        "foreign_key_errors": len(conn.execute("PRAGMA foreign_key_check").fetchall()),
    }
    # Pick two users with both an order and an invoice for runtime authorization tests.
    users = conn.execute("""
        SELECT c.id, c.username
        FROM customers c
        WHERE EXISTS (SELECT 1 FROM orders o WHERE o.user_id = c.id)
          AND EXISTS (SELECT 1 FROM invoices i WHERE i.owner_id = c.id)
        ORDER BY c.id LIMIT 2
    """).fetchall()
    counts["test_users"] = [{"id": row[0], "username": row[1]} for row in users]
    print(json.dumps(counts))
finally:
    conn.close()
'''
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "order", "python", "-c", query],
        cwd=ROOT, capture_output=True, text=True, timeout=20,
    )
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return json.loads(result.stdout.strip().splitlines()[-1])


def login(username):
    response = requests.post(
        f"{BASE}:5001/api/v2/auth/login",
        json={"username": username, "password": PASSWORD},
        timeout=5,
    )
    response.raise_for_status()
    body = response.json()
    return body["user_id"], {"Authorization": f"Bearer {body['token']}"}


def check_bola(users):
    """Prove the lab's billing BOLA and the order service's access control."""
    if len(users) < 2:
        raise RuntimeError("Need two seeded users with orders and invoices.")

    alice, bob = users
    alice_id, alice_headers = login(alice["username"])
    bob_id, bob_headers = login(bob["username"])

    if alice_id == bob_id:
        raise RuntimeError("Selected users did not resolve to distinct IDs.")

    invoices = requests.get(
        f"{BASE}:5004/api/v2/billing/invoices",
        headers=bob_headers, timeout=5,
    )
    invoices.raise_for_status()
    bob_invoices = invoices.json().get("invoices", [])
    target_invoice = next(
        (item for item in bob_invoices if item.get("owner_id") == bob_id), None
    )
    if not target_invoice:
        raise RuntimeError("Could not find an invoice owned by the second user.")

    exploited = requests.get(
        f"{BASE}:5004/api/v2/billing/invoices/{target_invoice['id']}",
        headers=alice_headers, timeout=5,
    )
    billing_pass = (
        exploited.status_code == 200
        and exploited.json().get("owner_id") == bob_id
        and bob_id != alice_id
    )
    record("Intentional billing BOLA remains demonstrable", billing_pass, {
        "requester_id": alice_id,
        "invoice_id": target_invoice["id"],
        "actual_owner_id": exploited.json().get("owner_id")
            if exploited.headers.get("content-type", "").startswith("application/json")
            else None,
        "http_status": exploited.status_code,
        "expected_lab_behavior": "cross-user invoice request returns 200",
    })

    orders = requests.get(
        f"{BASE}:5003/api/v2/orders",
        headers=bob_headers, timeout=5,
    )
    orders.raise_for_status()
    bob_orders = orders.json().get("orders", [])
    target_order = next(
        (item for item in bob_orders if item.get("user_id") == bob_id), None
    )
    if not target_order:
        raise RuntimeError("Could not find an order owned by the second user.")

    blocked = requests.get(
        f"{BASE}:5003/api/v2/orders/{target_order['id']}",
        headers=alice_headers, timeout=5,
    )
    record("Order service blocks cross-user object access",
           blocked.status_code == 404, {
               "requester_id": alice_id,
               "order_id": target_order["id"],
               "http_status": blocked.status_code,
               "expected_status": 404,
           })


def start_receiver(capture_path):
    global server, server_log
    env = os.environ.copy()
    env["CAPTURES_PATH"] = str(capture_path)
    env["MOCK_DROP_RATE"] = "0"
    log_path = RUN_DIR / "mock_ingestion_pipeline.log"
    server_log = open(log_path, "w", encoding="utf-8")
    server = subprocess.Popen(
        [sys.executable, str(SCRIPTS / "pipeline/mock_ingestion_pipeline.py")],
        cwd=APPSEC, env=env, stdout=server_log, stderr=subprocess.STDOUT,
    )
    for _ in range(40):
        if server.poll() is not None:
            raise RuntimeError(f"Mock ingestion process exited; inspect {log_path}")
        try:
            response = requests.get(f"{BASE}:5099/health", timeout=1)
            if response.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.25)
    raise RuntimeError(f"Mock ingestion receiver did not become healthy; inspect {log_path}")


def forward(source, label):
    return command(
        f"Forward {label} requests to mock ingestion",
        [
            sys.executable, str(SCRIPTS / "pipeline/mock_packet_forwarder.py"),
            "--source", str(source),
            "--receiver", f"{BASE}:5099/capture",
        ],
        RUN_DIR / f"forward-{label}.log",
        cwd=APPSEC,
        timeout=180,
    )


def audit(sent_path, capture_path):
    audit_json = RUN_DIR / "pipeline_audit.json"
    result = command(
        "Pipeline capture audit",
        [
            sys.executable, str(SCRIPTS / "pipeline/pipeline_audit.py"),
            "--sent-source", str(sent_path),
            "--captures-source", str(capture_path),
            "--output", str(audit_json),
        ],
        RUN_DIR / "pipeline_audit.log",
        cwd=APPSEC,
    )
    details = {}
    if audit_json.exists():
        try:
            details = json.loads(audit_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            details = {"report_parse_error": True}
    rate = details.get("capture_rate", details.get("capture_rate_percent"))
    if rate is None:
        rate = details.get("capture_rate_pct")
    # Auditor's successful exit means its own capture-integrity checks passed.
    passed = result is not None and result.returncode == 0
    if rate is not None:
        passed = passed and float(rate) == 100.0
    record("Pipeline audit confirms 100% capture", passed, {
        "audit_report": str(audit_json),
        "audit_details": details,
        "exit_code": result.returncode if result else None,
    })


def main():
    try:
        # 1. API health
        health = {}
        for name, url in SERVICES.items():
            try:
                response = requests.get(url, timeout=3)
                health[name] = {
                    "status": response.status_code,
                    "body": response.json(),
                }
            except (requests.RequestException, ValueError) as exc:
                health[name] = {"error": str(exc)}
        record("All four API services healthy",
               all(v.get("status") == 200 and
                   v.get("body", {}).get("status") == "ok"
                   for v in health.values()),
               health)

        # 2. Seeded database and referential integrity
        try:
            db = database_counts()
            db_pass = (
                db["customers"] >= 50
                and db["orders"] >= 147
                and db["invoices"] >= 147
                and db["foreign_key_errors"] == 0
            )
            record("Seeded database integrity", db_pass, db)
            if db_pass:
                check_bola(db["test_users"])
            else:
                record("Runtime BOLA and ownership checks", False,
                       {"reason": "Database integrity check failed"})
        except Exception as exc:
            record("Database and runtime authorization checks", False,
                   {"error": repr(exc)})

        # 3. Authenticated API performance gate: 10 VUs for 15 seconds.
        # The legacy login-inclusive benchmark remains diagnostic evidence;
        # its historical measurements are documented in benchmark-baseline.md.
        command(
            "Authenticated API benchmark (10 VUs, 15s)",
            [
                "bash",
                str(APPSEC / "benchmarks/run_authenticated_benchmark.sh"),
                "10",
                "15s",
            ],
            RUN_DIR / "authenticated-benchmark.log",
            cwd=ROOT,
            timeout=180,
        )

        # 4. Start isolated capture receiver and generate both traffic types
        capture_path = RUN_DIR / "captures.jsonl"
        sent_traffic = RUN_DIR / "legitimate/sent_requests.jsonl"
        sent_load = RUN_DIR / "sustained/sent_requests.jsonl"
        (RUN_DIR / "legitimate").mkdir(parents=True, exist_ok=True)
        (RUN_DIR / "sustained").mkdir(parents=True, exist_ok=True)

        try:
            start_receiver(capture_path)
            command(
                "Legitimate traffic generator (20 seconds)",
                [
                    sys.executable, str(SCRIPTS / "traffic/traffic_generator.py"),
                    "--duration", "20",
                    "--output-dir", str(RUN_DIR / "legitimate"),
                    "--base-url", BASE,
                    "--seed", "42",
                ],
                RUN_DIR / "legitimate-traffic.log",
                cwd=ROOT,
                timeout=60,
            )
            command(
                "Sustained load generator (500 requests, 20 req/s)",
                [
                    sys.executable, str(SCRIPTS / "pipeline/sustained_load.py"),
                    "--count", "500", "--rate", "20",
                    "--base-url", BASE, "--output", str(sent_load),
                ],
                RUN_DIR / "sustained-load.log",
                cwd=ROOT,
                timeout=120,
            )

            sources = [p for p in (sent_traffic, sent_load) if p.exists()]
            if len(sources) != 2:
                record("Traffic evidence files exist", False, {
                    "expected": [str(sent_traffic), str(sent_load)],
                    "found": [str(p) for p in sources],
                })
            else:
                combined = RUN_DIR / "sent_requests.jsonl"
                with combined.open("w", encoding="utf-8") as out:
                    for source in sources:
                        with source.open(encoding="utf-8") as src:
                            shutil.copyfileobj(src, out)

                record("Traffic evidence files contain requests",
                       combined.stat().st_size > 0, {
                           "sources": [str(p) for p in sources],
                           "combined_bytes": combined.stat().st_size,
                       })
                for label, source in (("legitimate", sent_traffic),
                                      ("sustained", sent_load)):
                    forward(source, label)
                audit(combined, capture_path)

        except Exception as exc:
            record("Mock ingestion and capture pipeline", False, {
                "error": repr(exc),
            })

        # 5. Full test suite
        command(
            "Full pytest suite",
            [sys.executable, "-m", "pytest", "-q", "appsec-testing/tests"],
            RUN_DIR / "pytest.log",
            cwd=ROOT,
            timeout=240,
        )

    finally:
        if server is not None and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
        if server_log is not None:
            server_log.close()

        passed = sum(c["status"] == "PASS" for c in checks)
        failed = sum(c["status"] == "FAIL" for c in checks)
        report = {
            "project": "API-Sentinel",
            "milestone": "Phase 1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "status": "PASS" if failed == 0 and checks else "FAIL",
            "summary": {
                "total_checks": len(checks),
                "passed": passed,
                "failed": failed,
            },
            "run_directory": str(RUN_DIR),
            "checks": checks,
        }
        REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        archive = DOCS / "phase1-freeze-report.json"
        print(f"\nPhase 1 status: {report['status']}")
        print(f"Checks: {passed} passed, {failed} failed")
        print(f"Report: {REPORT_PATH}")
        print(f"Run artifacts: {RUN_DIR}")

        if report["status"] == "PASS":
            shutil.copy2(REPORT_PATH, archive)
            print(f"Freeze archive: {archive}")
        else:
            print("Freeze archive NOT updated: validation did not pass.")
            print("Any existing archive must not be treated as passing evidence.")

        if failed:
            sys.exit(1)


if __name__ == "__main__":
    main()
