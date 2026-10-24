"""Generate sustained, authenticated e-commerce traffic for pipeline auditing."""

import argparse
import random
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.traffic.customer_pool import build_customer_pool
from scripts.traffic.sent_requests_log import SentRequestsLogger

DEFAULT_BASE_URL = "http://127.0.0.1"
SERVICE_PORTS = {"auth": 5001, "order": 5003}


class SustainedLoad:
    def __init__(self, base_url, output_path):
        self.base_url = base_url.rstrip("/")
        self.logger = SentRequestsLogger(output_path)
        self.sessions = {}
        self.customers = []

    def request(self, service, method, path, session, username, **kwargs):
        request_id = self.logger.new_request_id()
        headers = dict(kwargs.pop("headers", {}))
        headers["X-Request-ID"] = request_id
        url = (
            f"{self.base_url}:{SERVICE_PORTS[service]}{path}"
        )

        status_code = None
        error = None
        started = time.perf_counter()

        try:
            response = session.request(
                method,
                url,
                headers=headers,
                timeout=10,
                **kwargs,
            )
            status_code = response.status_code
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            error = str(exc)
            raise
        finally:
            self.logger.record(
                request_id,
                method,
                path,
                source="sustained_load",
                service=service,
                username=username,
                status_code=status_code,
                latency_ms=round(
                    (time.perf_counter() - started) * 1000, 2
                ),
                error=error,
            )

    def get_session(self, customer):
        if customer.username in self.sessions:
            return self.sessions[customer.username]

        session = requests.Session()

        response = self.request(
            "auth",
            "POST",
            "/api/v2/auth/login",
            session,
            customer.username,
            json={
                "username": customer.username,
                "password": customer.password,
            },
        )
        payload = response.json()
        token = payload.get("token")

        if not token:
            session.close()
            raise RuntimeError(
                f"Login returned no token for {customer.username}"
            )

        session.headers["Authorization"] = f"Bearer {token}"

        self.sessions[customer.username] = session
        return session

    def run(self, count, rate):
        self.customers = build_customer_pool()
        rng = random.Random(42)
        interval = 1.0 / rate if rate > 0 else 0
        started = time.perf_counter()
        succeeded = 0
        failed = 0

        print(f"Loaded {len(self.customers)} seeded customers.")
        print(f"Target: {count} order requests at {rate:g}/second.")
        print("Press Ctrl+C to stop.")

        try:
            for index in range(count):
                request_started = time.perf_counter()
                customer = rng.choice(self.customers)

                try:
                    session = self.get_session(customer)
                    response = self.request(
                        "order",
                        "GET",
                        "/api/v2/orders",
                        session,
                        customer.username,
                    )
                    succeeded += 1
                    print(
                        f"[{index + 1}/{count}] "
                        f"{customer.username}: HTTP {response.status_code}"
                    )
                except (requests.RequestException, RuntimeError, ValueError) as exc:
                    failed += 1
                    print(
                        f"[{index + 1}/{count}] "
                        f"{customer.username}: FAILED ({exc})"
                    )

                remaining = interval - (
                    time.perf_counter() - request_started
                )
                if remaining > 0 and index + 1 < count:
                    time.sleep(remaining)

        except KeyboardInterrupt:
            print("\nStopped by user.")
        finally:
            for session in self.sessions.values():
                session.close()

        elapsed = time.perf_counter() - started
        print("\n===== Sustained-load summary =====")
        print(f"Order requests succeeded: {succeeded}")
        print(f"Order requests failed:    {failed}")
        print(f"Elapsed seconds:           {elapsed:.2f}")
        print(f"Sent-request log:          {self.logger.output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate authenticated API-Sentinel traffic."
    )
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--rate", type=float, default=20.0)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument(
        "--output",
        default="logs/sent_requests.jsonl",
    )
    args = parser.parse_args()

    if args.count < 1:
        parser.error("--count must be at least 1")
    if args.rate <= 0:
        parser.error("--rate must be greater than 0")

    SustainedLoad(args.base_url, args.output).run(args.count, args.rate)


if __name__ == "__main__":
    main()
