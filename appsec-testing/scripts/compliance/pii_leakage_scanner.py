#!/usr/bin/env python3
"""Day 25: Controlled plaintext PII leakage inspection."""

import argparse
import base64
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests


APPSEC_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = APPSEC_ROOT.parent
FIXTURE_PATH = APPSEC_ROOT / "data" / "pii_test_payloads.json"
REPORT_PATH = APPSEC_ROOT / "logs" / "pii_leakage_report.json"

CUSTOMER_ID = 9001
USERNAME = "pii-audit-9001"
ORDER_ID = 99001
INVOICE_ID = 99001
AUDIT_PASSWORD = "Day25-Audit-Only-2026!"

SERVICES = {
    "auth": "http://127.0.0.1:5001",
    "user": "http://127.0.0.1:5002",
    "order": "http://127.0.0.1:5003",
    "billing": "http://127.0.0.1:5004",
}


def load_fixture():
    with FIXTURE_PATH.open("r", encoding="utf-8") as handle:
        fixture = json.load(handle)

    payloads = []
    for category, entries in fixture["categories"].items():
        for entry in entries:
            marker = entry.get("marker")
            value = entry.get("value")
            if not isinstance(marker, str) or not marker:
                raise ValueError("Fixture contains an invalid marker.")
            if not isinstance(value, str) or not value:
                raise ValueError("Fixture contains an invalid payload value.")
            payloads.append({
                "category": category,
                "marker": marker,
                "value": value,
            })

    if len(payloads) != fixture.get("total_payloads"):
        raise ValueError("Fixture total_payloads does not match its contents.")

    if len({item["marker"] for item in payloads}) != len(payloads):
        raise ValueError("Fixture contains duplicate markers.")

    if len({item["value"] for item in payloads}) != len(payloads):
        raise ValueError("Fixture contains duplicate values.")

    return fixture, payloads


def scan_text(content, payloads, location):
    """Return marker-only findings. Never return the matched value."""
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, default=str)

    findings = []
    for item in payloads:
        count = content.count(item["value"])
        if count:
            findings.append({
                "location": location,
                "category": item["category"],
                "marker": item["marker"],
                "match_count": count,
            })
    return findings


def docker_python(source):
    encoded = base64.b64encode(source.encode("utf-8")).decode("ascii")
    command = [
        "docker", "exec", "api-sentinel-billing",
        "python", "-c",
        "import base64; exec(base64.b64decode('" + encoded + "'))",
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError("Database container operation failed.")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Database operation returned invalid output.") from exc


def preflight():
    source = r'''
import json, sqlite3
c = sqlite3.connect("/app/data/shop.db")
checks = {
    "customer_id": c.execute(
        "SELECT COUNT(*) FROM customers WHERE id=?", (9001,)
    ).fetchone()[0],
    "username": c.execute(
        "SELECT COUNT(*) FROM customers WHERE username=?",
        ("pii-audit-9001",)
    ).fetchone()[0],
    "order_id": c.execute(
        "SELECT COUNT(*) FROM orders WHERE id=?", (99001,)
    ).fetchone()[0],
    "invoice_id": c.execute(
        "SELECT COUNT(*) FROM invoices WHERE id=?", (99001,)
    ).fetchone()[0],
}
c.close()
print(json.dumps(checks))
'''
    checks = docker_python(source)
    if any(value != 0 for value in checks.values()):
        raise RuntimeError("Audit ID collision detected; no records were inserted.")
    return checks


def insert_audit_records(payloads):
    # Values are passed to the container only through base64-encoded source.
    billing_payload = json.dumps(
        {item["marker"]: item["value"] for item in payloads},
        separators=(",", ":"),
    )
    email = next(item["value"] for item in payloads
                 if item["category"] == "emails")
    card_last4 = next(item["value"][-4:] for item in payloads
                      if item["category"] == "credit_cards")

    data = {
        "billing_payload": billing_payload,
        "email": email,
        "card_last4": card_last4,
        "password": AUDIT_PASSWORD,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    encoded_data = base64.b64encode(
        json.dumps(data).encode("utf-8")
    ).decode("ascii")

    source = r'''
import base64, json, sqlite3
from werkzeug.security import generate_password_hash

d = json.loads(base64.b64decode("''' + encoded_data + r'''"))
c = sqlite3.connect("/app/data/shop.db")
c.execute("PRAGMA foreign_keys=ON")
try:
    c.execute("BEGIN IMMEDIATE")
    c.execute(
        """INSERT INTO customers
           (id, username, full_name, email, password_hash, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (9001, "pii-audit-9001", "Day25 Synthetic Audit",
         d["email"], generate_password_hash(d["password"]), d["created_at"])
    )
    c.execute(
        """INSERT INTO orders
           (id, user_id, item, total, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (99001, 9001, "Day25 synthetic audit item", 1.0,
         "audit", d["created_at"])
    )
    c.execute(
        """INSERT INTO invoices
           (id, order_id, owner_id, amount, currency, status,
            card_last4, billing_address, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (99001, 99001, 9001, 1.0, "USD", "audit",
         d["card_last4"], d["billing_payload"], d["created_at"])
    )
    c.commit()
    print(json.dumps({"inserted": True}))
except Exception:
    c.rollback()
    raise
finally:
    c.close()
'''
    return docker_python(source)


def cleanup_audit_records():
    source = r'''
import json, sqlite3
c = sqlite3.connect("/app/data/shop.db")
c.execute("PRAGMA foreign_keys=ON")
try:
    c.execute("BEGIN IMMEDIATE")
    invoice = c.execute(
        "DELETE FROM invoices WHERE id=? AND order_id=? AND owner_id=?",
        (99001, 99001, 9001)
    ).rowcount
    order = c.execute(
        "DELETE FROM orders WHERE id=? AND user_id=?",
        (99001, 9001)
    ).rowcount
    customer = c.execute(
        "DELETE FROM customers WHERE id=? AND username=?",
        (9001, "pii-audit-9001")
    ).rowcount
    c.commit()
    remaining = {
        "customer": c.execute(
            "SELECT COUNT(*) FROM customers WHERE id=? AND username=?",
            (9001, "pii-audit-9001")
        ).fetchone()[0],
        "order": c.execute(
            "SELECT COUNT(*) FROM orders WHERE id=? AND user_id=?",
            (99001, 9001)
        ).fetchone()[0],
        "invoice": c.execute(
            "SELECT COUNT(*) FROM invoices WHERE id=? AND order_id=? AND owner_id=?",
            (99001, 99001, 9001)
        ).fetchone()[0],
    }
    print(json.dumps({
        "deleted": {"invoice": invoice, "order": order, "customer": customer},
        "remaining": remaining,
        "complete": all(value == 0 for value in remaining.values())
    }))
except Exception:
    c.rollback()
    raise
finally:
    c.close()
'''
    return docker_python(source)


def login(username, password):
    response = requests.post(
        SERVICES["auth"] + "/api/v2/auth/login",
        json={"username": username, "password": password},
        timeout=10,
    )
    if response.status_code != 200:
        raise RuntimeError("Login request failed.")
    body = response.json()
    token = body.get("token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Login response did not contain a token.")
    return token


def inspect_api(payloads):
    results = []
    findings = []

    # The seeded account is used only to inspect the known cross-owner BOLA.
    seeded = docker_python(r'''
import json, sqlite3
c = sqlite3.connect("/app/data/shop.db")
row = c.execute("SELECT username FROM customers WHERE id=1").fetchone()
c.close()
print(json.dumps({"username": row[0] if row else None}))
''')
    if not seeded.get("username"):
        raise RuntimeError("Could not identify the seeded audit comparison account.")

    audit_token = login(USERNAME, AUDIT_PASSWORD)
    seeded_token = login(seeded["username"], "Password123!")

    checks = [
        ("audit_profile", "GET", SERVICES["user"] + "/api/v2/users/me",
         {"Authorization": "Bearer " + audit_token}, 200),
        ("audit_invoice_authenticated", "GET",
         SERVICES["billing"] + "/api/v2/billing/invoices/99001",
         {"Authorization": "Bearer " + audit_token}, 200),
        ("foreign_invoice_authenticated", "GET",
         SERVICES["billing"] + "/api/v2/billing/invoices/99001",
         {"Authorization": "Bearer " + seeded_token}, 200),
        ("legacy_invoice_unauthenticated", "GET",
         SERVICES["billing"] + "/api/v1/invoices/99001", {}, 200),
    ]

    for name, method, url, headers, expected_status in checks:
        response = requests.request(
            method, url, headers=headers, timeout=10
        )
        body_text = response.text
        matches = scan_text(body_text, payloads, "api_response:" + name)
        findings.extend(matches)
        results.append({
            "check": name,
            "http_status": response.status_code,
            "expected_status": expected_status,
            "passed": response.status_code == expected_status,
            "payload_matches": len(matches),
        })

    # Do not return or persist either session token.
    del audit_token, seeded_token
    return results, findings


def inspect_database(payloads):
    source = r'''
import json, sqlite3
c = sqlite3.connect("/app/data/shop.db")
c.row_factory = sqlite3.Row
journal = c.execute("PRAGMA journal_mode").fetchone()[0]
customer = c.execute(
    "SELECT email FROM customers WHERE id=? AND username=?",
    (9001, "pii-audit-9001")
).fetchone()
invoice = c.execute(
    """SELECT card_last4, billing_address FROM invoices
       WHERE id=? AND order_id=? AND owner_id=?""",
    (99001, 99001, 9001)
).fetchone()
import os
result = {
    "journal_mode": journal,
    "wal_file_present": os.path.exists("/app/data/shop.db-wal"),
    "customer_found": customer is not None,
    "invoice_found": invoice is not None,
    "customer_email": customer["email"] if customer else None,
    "card_last4": invoice["card_last4"] if invoice else None,
    "billing_address": invoice["billing_address"] if invoice else None,
}
c.close()
print(json.dumps(result))
'''
    result = docker_python(source)
    findings = []
    if result["customer_found"]:
        findings.extend(scan_text(
            result["customer_email"], payloads, "database:customers.email"
        ))
    if result["invoice_found"]:
        findings.extend(scan_text(
            result["card_last4"], payloads, "database:invoices.card_last4"
        ))
        findings.extend(scan_text(
            result["billing_address"], payloads,
            "database:invoices.billing_address"
        ))

    # Never return stored payload-bearing field contents to the report.
    result.pop("customer_email", None)
    result.pop("card_last4", None)
    result.pop("billing_address", None)
    return result, findings


def inspect_logs(payloads):
    containers = {
        "auth": "api-sentinel-auth",
        "user": "api-sentinel-user",
        "order": "api-sentinel-order",
        "billing": "api-sentinel-billing",
    }

    log_text = []
    total_lines = 0

    for service, container in containers.items():
        result = subprocess.run(
            ["docker", "logs", "--tail", "1000", container],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise RuntimeError("Container log inspection failed.")

        service_output = result.stdout + result.stderr
        log_text.append(service_output)
        total_lines += len(service_output.splitlines())

    findings = scan_text(
        "\n".join(log_text), payloads, "service_logs"
    )

    return {
        "command_succeeded": True,
        "lines_inspected": total_lines,
        "payload_matches": len(findings),
        "services_inspected": list(containers),
        "line_limit_per_service": 1000,
    }, findings



def write_report(report, destination=None):
    destination = destination if destination is not None else REPORT_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(destination)


def run_audit(report_path=None):
    destination = report_path if report_path is not None else REPORT_PATH
    fixture, payloads = load_fixture()
    report = {
        "day": 25,
        "title": "Plaintext PII Leakage Inspection",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "fixture_payload_count": len(payloads),
        "fixture_categories": dict(Counter(
            item["category"] for item in payloads
        )),
        "audit_scope": [
            "API response bodies",
            "SQLite customer and invoice fields",
            "Docker Compose service logs",
        ],
        "findings": [],
        "checks": {},
        "status": "INCOMPLETE",
        "cleanup": {"attempted": False, "complete": False},
        "limitations": [
            "API response bodies were inspected; this was not a packet capture.",
            "SQLite database fields were queried; raw disk blocks were not scanned.",
            "Only the latest 1000 lines per selected service were inspected.",
            "WAL presence and journal mode were recorded; WAL bytes were not separately scanned.",
        ],
    }

    cleanup_required = False
    audit_error = None
    try:
        report["checks"]["preflight"] = preflight()
        # The insert command may commit even if Docker times out before
        # returning its result. Ensure the finally block still attempts cleanup.
        cleanup_required = True
        insert_audit_records(payloads)
        report["checks"]["insertion"] = {"passed": True}

        api_results, api_findings = inspect_api(payloads)
        report["checks"]["api"] = api_results
        report["findings"].extend(api_findings)

        db_result, db_findings = inspect_database(payloads)
        report["checks"]["database"] = db_result
        report["findings"].extend(db_findings)

        log_result, log_findings = inspect_logs(payloads)
        report["checks"]["logs"] = log_result
        report["findings"].extend(log_findings)

    except Exception as exc:
        # Avoid exception text: it may contain request or database values.
        audit_error = type(exc).__name__
        report["error_type"] = audit_error
    finally:
        if cleanup_required:
            report["cleanup"]["attempted"] = True
            try:
                cleanup = cleanup_audit_records()
                report["cleanup"].update(cleanup)
            except Exception as exc:
                report["cleanup"]["error_type"] = type(exc).__name__
                report["cleanup"]["complete"] = False

    api_ok = bool(report["checks"].get("api")) and all(
        item["passed"] for item in report["checks"]["api"]
    )
    db_ok = report["checks"].get("database", {}).get("invoice_found", False)
    db_ok = db_ok and report["checks"].get("database", {}).get("customer_found", False)
    logs_ok = report["checks"].get("logs", {}).get("command_succeeded", False)
    cleanup_ok = report["cleanup"].get("complete", False)

    report["completed_at"] = datetime.now(timezone.utc).isoformat()
    report["finding_count"] = len(report["findings"])
    report["status"] = (
        "COMPLETE" if not audit_error and api_ok and db_ok and logs_ok and cleanup_ok
        else "INCOMPLETE"
    )
    report["interpretation"] = (
        "Payload matches indicate plaintext exposure at the recorded locations."
        if report["findings"]
        else "No fixture matches were recorded in the inspected sources."
    )
    write_report(report, destination)

    try:
        display_report_path = str(destination.relative_to(APPSEC_ROOT))
    except ValueError:
        display_report_path = str(destination)

    print(json.dumps({
        "status": report["status"],
        "payloads_tested": len(payloads),
        "finding_count": report["finding_count"],
        "api_checks": report["checks"].get("api", []),
        "database": report["checks"].get("database", {}),
        "logs": report["checks"].get("logs", {}),
        "cleanup": report["cleanup"],
        "report_path": display_report_path,
    }, indent=2))

    return 0 if report["status"] == "COMPLETE" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Insert dedicated synthetic audit records and run live inspection.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Optional output report path; defaults to the standard Day 25 report.",
    )
    args = parser.parse_args()

    report_path = args.report
    if report_path is not None and not report_path.is_absolute():
        report_path = APPSEC_ROOT / report_path

    try:
        fixture, payloads = load_fixture()
        if not args.execute:
            print("DRY RUN: PASS")
            print(f"Loaded {len(payloads)} synthetic payloads.")
            print("No live API requests or database modifications were made.")
            return 0
        return run_audit(report_path=report_path)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
