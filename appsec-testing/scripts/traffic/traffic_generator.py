"""Generate legitimate synthetic background traffic for the API-Sentinel lab."""

import argparse
import asyncio
import csv
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import aiohttp

try:
    from .sent_requests_log import SentRequestsLogger
except ImportError:
    from sent_requests_log import SentRequestsLogger

try:
    from .customer_pool import build_customer_pool
except ImportError:
    from customer_pool import build_customer_pool


BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1")
DEFAULT_JITTER = 0.4
REQUEST_TIMEOUT = 5

LOG_FIELDS = [
    "timestamp",
    "request_id",
    "legitimate",
    "username",
    "action",
    "method",
    "path",
    "status_code",
    "latency_ms",
]


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat()


class TrafficLogger:
    """Write one record per request to JSONL and CSV files."""

    def __init__(self, output_dir):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.jsonl_path = self.output_dir / f"traffic_{stamp}.jsonl"
        self.csv_path = self.output_dir / f"traffic_{stamp}.csv"

        self.jsonl_file = self.jsonl_path.open(
            "a", encoding="utf-8"
        )
        self.csv_file = self.csv_path.open(
            "a", newline="", encoding="utf-8"
        )
        self.csv_writer = csv.DictWriter(
            self.csv_file, fieldnames=LOG_FIELDS
        )
        self.csv_writer.writeheader()

    def write(self, record):
        self.jsonl_file.write(json.dumps(record) + "\n")
        self.jsonl_file.flush()

        self.csv_writer.writerow(record)
        self.csv_file.flush()

    def close(self):
        self.jsonl_file.close()
        self.csv_file.close()


class TrafficGenerator:
    """Make authenticated, customer-scoped API requests."""

    def __init__(
        self,
        base_url=BASE_URL,
        output_dir="logs",
        min_delay=0.6,
        max_delay=1.4,
        seed=None,
        concurrency=10,
    ):
        if min_delay < 0 or max_delay < min_delay:
            raise ValueError("Delay values must satisfy 0 <= min <= max")
        if not isinstance(concurrency, int) or isinstance(concurrency, bool) or concurrency < 1:
            raise ValueError("Concurrency must be a positive integer")

        self.base_url = base_url.rstrip("/")
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.concurrency = concurrency
        self.rng = random.Random(seed)
        self.customers = None
        self.logger = TrafficLogger(output_dir)
        self.sent_logger = SentRequestsLogger(
            Path(output_dir) / "sent_requests.jsonl"
        )
        self.session = requests.Session()
        self.current_customer = None
        self.action_count = 0

    def request(self, method, path, action, **kwargs):
        """Send and log a request, including network errors."""
        if path.startswith("/api/v2/auth/"):
            port = 5001
        elif path.startswith("/api/v2/users/"):
            port = 5002
        elif path.startswith("/api/v2/orders"):
            port = 5003
        elif path.startswith("/api/v2/billing/"):
            port = 5004
        else:
            raise ValueError(f"Unknown API service path: {path}")

        url = f"{self.base_url}:{port}{path}"
        request_id = self.sent_logger.new_request_id()
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["X-Request-ID"] = request_id
        kwargs["headers"] = headers

        start = time.perf_counter()
        status_code = 0
        error = None

        try:
            response = self.session.request(
                method,
                url,
                timeout=REQUEST_TIMEOUT,
                **kwargs,
            )
            status_code = response.status_code
            return response
        except requests.RequestException as exc:
            error = type(exc).__name__
            raise
        finally:
            latency_ms = round(
                (time.perf_counter() - start) * 1000, 2
            )
            customer_name = (
                self.current_customer.username
                if self.current_customer
                else "unknown"
            )
            self.logger.write(
                {
                    "timestamp": utc_timestamp(),
                    "request_id": request_id,
                    "legitimate": True,
                    "username": customer_name,
                    "action": action,
                    "method": method.upper(),
                    "path": path,
                    "status_code": status_code,
                    "latency_ms": latency_ms,
                }
            )
            self.sent_logger.record(
                request_id,
                method,
                path,
                source="traffic_generator",
                legitimate=True,
                username=customer_name,
                action=action,
                status_code=status_code,
                latency_ms=latency_ms,
                error=error,
            )
            self.action_count += 1

    def authenticate(self, customer):
        """Log in as a demo customer and use that customer's token."""
        self.current_customer = customer
        self.session.headers.pop("Authorization", None)

        response = self.request(
            "POST",
            "/api/v2/auth/login",
            "login",
            json={
                "username": customer.username,
                "password": customer.password,
            },
        )
        response.raise_for_status()

        payload = response.json()
        token = payload.get("token")
        if not token:
            raise RuntimeError(
                f"Login response did not contain a token for "
                f"{customer.username}"
            )

        self.session.headers["Authorization"] = f"Bearer {token}"

        verify = self.request(
            "GET",
            "/api/v2/auth/verify",
            "verify_token",
        )
        verify.raise_for_status()

        if verify.json().get("valid") is not True:
            raise RuntimeError("Token verification did not succeed")

        return payload.get("user_id")

    def get_list(self, path, key, action):
        response = self.request("GET", path, action)
        response.raise_for_status()

        payload = response.json()
        items = payload.get(key)
        if not isinstance(items, list):
            raise RuntimeError(
                f"Expected a list in field {key!r} from {path}"
            )
        return items

    def customer_cycle(self, customer):
        """Perform safe read-only actions for one authenticated customer."""
        user_id = self.authenticate(customer)

        if user_id is None:
            raise RuntimeError(
                "Login response did not identify the authenticated user"
            )
        self.request(
            "GET", "/api/v2/users/me", "get_my_profile"
        ).raise_for_status()

        orders = self.get_list(
            "/api/v2/orders", "orders", "list_my_orders"
        )
        invoices = self.get_list(
            "/api/v2/billing/invoices",
            "invoices",
            "list_my_invoices",
        )

        # Never guess, enumerate, or reuse IDs from another customer.
        if user_id is not None:
            for order in orders:
                if order.get("user_id") != user_id:
                    raise RuntimeError(
                        "Order list contained an order for another user"
                    )
            for invoice in invoices:
                if invoice.get("owner_id") != user_id:
                    raise RuntimeError(
                        "Invoice list contained an invoice for another user"
                    )

        if orders:
            order = self.rng.choice(orders)
            order_id = order.get("id")
            if order_id is not None:
                self.request(
                    "GET",
                    f"/api/v2/orders/{int(order_id)}",
                    "get_my_order",
                ).raise_for_status()

        if invoices:
            invoice = self.rng.choice(invoices)
            invoice_id = invoice.get("id")
            if invoice_id is not None:
                self.request(
                    "GET",
                    f"/api/v2/billing/invoices/{int(invoice_id)}",
                    "get_my_invoice",
                ).raise_for_status()

    async def async_request(self, session, customer, method, path, action, token=None, **kwargs):
        """Send one asynchronous request and log it with explicit customer identity."""
        if path.startswith("/api/v2/auth/"):
            port = 5001
        elif path.startswith("/api/v2/users/"):
            port = 5002
        elif path.startswith("/api/v2/orders"):
            port = 5003
        elif path.startswith("/api/v2/billing/"):
            port = 5004
        else:
            raise ValueError(f"Unknown API service path: {path}")

        url = f"{self.base_url}:{port}{path}"
        request_id = self.sent_logger.new_request_id()
        headers = dict(kwargs.pop("headers", {}) or {})
        headers["X-Request-ID"] = request_id
        if token:
            headers["Authorization"] = f"Bearer {token}"

        start = time.perf_counter()
        status_code = 0
        error = None

        try:
            async with session.request(
                method,
                url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                **kwargs,
            ) as response:
                status_code = response.status
                response.raise_for_status()
                if response.content_type == "application/json":
                    return await response.json()
                body = await response.text()
                return {"text": body}
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            error = type(exc).__name__
            raise
        finally:
            latency_ms = round((time.perf_counter() - start) * 1000, 2)
            username = customer.username if customer else "unknown"
            self.logger.write({
                "timestamp": utc_timestamp(),
                "request_id": request_id,
                "legitimate": True,
                "username": username,
                "action": action,
                "method": method.upper(),
                "path": path,
                "status_code": status_code,
                "latency_ms": latency_ms,
            })
            self.sent_logger.record(
                request_id,
                method,
                path,
                source="traffic_generator",
                legitimate=True,
                username=username,
                action=action,
                status_code=status_code,
                latency_ms=latency_ms,
                error=error,
            )
            self.action_count += 1

    async def async_customer_cycle(self, session, customer):
        """Run one customer cycle without sharing credentials with other workers."""
        login = await self.async_request(
            session, customer, "POST", "/api/v2/auth/login", "login",
            json={"username": customer.username, "password": customer.password},
        )
        token = login.get("token")
        user_id = login.get("user_id")
        if not token:
            raise RuntimeError(
                f"Login response did not contain a token for {customer.username}"
            )
        if user_id is None:
            raise RuntimeError(
                "Login response did not identify the authenticated user"
            )

        verify = await self.async_request(
            session, customer, "GET", "/api/v2/auth/verify",
            "verify_token", token=token,
        )
        if verify.get("valid") is not True:
            raise RuntimeError("Token verification did not succeed")

        await self.async_request(
            session, customer, "GET", "/api/v2/users/me",
            "get_my_profile", token=token,
        )

        orders_payload = await self.async_request(
            session, customer, "GET", "/api/v2/orders",
            "list_my_orders", token=token,
        )
        orders = orders_payload.get("orders")
        if not isinstance(orders, list):
            raise RuntimeError("Expected a list in field 'orders' from /api/v2/orders")

        invoices_payload = await self.async_request(
            session, customer, "GET", "/api/v2/billing/invoices",
            "list_my_invoices", token=token,
        )
        invoices = invoices_payload.get("invoices")
        if not isinstance(invoices, list):
            raise RuntimeError(
                "Expected a list in field 'invoices' from /api/v2/billing/invoices"
            )

        # Never guess, enumerate, or reuse IDs from another customer.
        for order in orders:
            if order.get("user_id") != user_id:
                raise RuntimeError("Order list contained an order for another user")
        for invoice in invoices:
            if invoice.get("owner_id") != user_id:
                raise RuntimeError("Invoice list contained an invoice for another user")

        if orders:
            order_id = self.rng.choice(orders).get("id")
            if order_id is not None:
                await self.async_request(
                    session, customer, "GET",
                    f"/api/v2/orders/{int(order_id)}",
                    "get_my_order", token=token,
                )

        if invoices:
            invoice_id = self.rng.choice(invoices).get("id")
            if invoice_id is not None:
                await self.async_request(
                    session, customer, "GET",
                    f"/api/v2/billing/invoices/{int(invoice_id)}",
                    "get_my_invoice", token=token,
                )

    async def _async_worker(self, worker_id, deadline):
        """Run a bounded worker with its own HTTP session."""
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while deadline is None or asyncio.get_running_loop().time() < deadline:
                customer = self.rng.choice(self.customers)
                try:
                    if deadline is None:
                        await self.async_customer_cycle(session, customer)
                    else:
                        remaining = deadline - asyncio.get_running_loop().time()
                        if remaining <= 0:
                            break
                        # Prevent a multi-request customer cycle from extending
                        # a duration-limited run by several request timeouts.
                        async with asyncio.timeout(remaining):
                            await self.async_customer_cycle(session, customer)
                except (
                    aiohttp.ClientError,
                    asyncio.TimeoutError,
                    ValueError,
                    RuntimeError,
                ) as exc:
                    logging.warning(
                        "Worker %s customer cycle failed for %s: %s",
                        worker_id, customer.username, exc,
                    )

                if deadline is not None and asyncio.get_running_loop().time() >= deadline:
                    break

                delay = self.rng.uniform(self.min_delay, self.max_delay)
                if deadline is not None:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        break
                    delay = min(delay, remaining)
                await asyncio.sleep(delay)

    async def _run_async(self, duration_seconds):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + duration_seconds if duration_seconds is not None else None

        print(f"Traffic logs: {self.logger.jsonl_path}")
        print(f"CSV logs:     {self.logger.csv_path}")
        if deadline is None:
            print(f"Generating traffic continuously with {self.concurrency} workers. Press Ctrl+C to stop.")
        else:
            print(f"Generating traffic for {duration_seconds:g} seconds with {self.concurrency} workers...")

        workers = [
            asyncio.create_task(self._async_worker(i + 1, deadline))
            for i in range(self.concurrency)
        ]
        await asyncio.gather(*workers)

    def run(self, duration_seconds=None):
        if duration_seconds is not None and duration_seconds <= 0:
            raise ValueError("Duration must be greater than zero")

        try:
            if self.customers is None:
                self.customers = build_customer_pool()
            asyncio.run(self._run_async(duration_seconds))
        except KeyboardInterrupt:
            print("\\nStop requested; shutting down gracefully.")
        finally:
            self.session.close()
            self.logger.close()

        print(f"Requests logged: {self.action_count}")
        print("Traffic generation finished.")

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate legitimate API-Sentinel demo traffic."
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Run for this many seconds; omit to run until Ctrl+C",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=0.6,
        help="Minimum delay between customer cycles (default: 0.6)",
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=1.4,
        help="Maximum delay between customer cycles (default: 1.4)",
    )
    parser.add_argument(
        "--output-dir",
        default="logs",
        help="Log directory (default: logs)",
    )
    parser.add_argument(
        "--base-url",
        default=BASE_URL,
        help="Service base URL (default: http://127.0.0.1)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional random seed for reproducible customer selection",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help="Number of concurrent traffic workers (default: 10)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    try:
        generator = TrafficGenerator(
            base_url=args.base_url,
            output_dir=args.output_dir,
            min_delay=args.min_delay,
            max_delay=args.max_delay,
            seed=args.seed,
            concurrency=args.concurrency,
        )
        generator.run(args.duration)
    except (ValueError, OSError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
