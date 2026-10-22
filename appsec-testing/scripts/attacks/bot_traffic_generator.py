#!/usr/bin/env python3
"""Bounded, concurrent bot-traffic simulation for the API-Sentinel lab.

Targets only this project's local mock services. Supports resource flood
and credential-stuffing modes. Intended for authorized lab testing only.
"""
import argparse
import random
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "traffic"))

from attack_logger import AttackLogger
from customer_pool import build_customer_pool, DEMO_PASSWORD

AUTH_URL = "http://127.0.0.1:5001"
ORDER_URL = "http://127.0.0.1:5003"
MAX_CONCURRENCY = 50
MAX_DURATION = 60
MAX_ATTEMPTS_PER_WORKER = 100
REQUEST_TIMEOUT = 3

COMMON_PASSWORD_GUESSES = (
    "123456", "password", "Password123!", "qwerty", "letmein",
    "admin123", "welcome1", "P@ssw0rd", "changeme", "football",
)


def validate_local_url(url, allow_proxy=False):
    """Reject non-loopback targets and unexpected ports by default."""
    parsed = urlparse(url)
    allowed_ports = {5001, 5003}
    if allow_proxy:
        allowed_ports.update({7001, 7003})
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.port not in allowed_ports
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Target must be a local API-Sentinel URL on an explicitly allowed port."
        )
    return url.rstrip("/")


class SafeAttackLogger:
    """Serialize log writes so concurrent workers retain unique sequence IDs."""

    def __init__(self, logger):
        self._logger = logger
        self._lock = threading.Lock()

    @property
    def path(self):
        return self._logger.path

    def log(self, **fields):
        with self._lock:
            self._logger.log(**fields)


def request_and_log(session, logger, *, run_id, mode, worker_id,
                    method, url, payload=None, headers=None, username=None):
    started = time.perf_counter()
    timestamp = time.time()
    status = None
    error = None
    success = False

    try:
        response = session.request(
            method,
            url,
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        status = response.status_code
        success = status == 200
    except requests.RequestException as exc:
        error = type(exc).__name__

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    record = {
        "run_id": run_id,
        "mode": mode,
        "worker_id": worker_id,
        "method": method,
        "endpoint": urlparse(url).path,
        "ts_epoch": timestamp,
        "status": status,
        "duration_ms": duration_ms,
        "success": success,
        "error": error,
    }
    if username is not None:
        record["username"] = username

    logger.log(**record)
    return {"status": status, "success": success, "error": error}


def flood_worker(worker_id, target_url, method, duration, logger,
                 stop_event, run_id, token=None, payload=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    count = 0
    deadline = time.monotonic() + duration

    with requests.Session() as session:
        while time.monotonic() < deadline and not stop_event.is_set():
            request_and_log(
                session, logger,
                run_id=run_id, mode="flood", worker_id=worker_id,
                method=method, url=target_url,
                payload=payload, headers=headers,
            )
            count += 1

    return count


def run_flood(target_url, method, concurrency, duration, logger,
              run_id, token=None, payload=None):
    stop_event = threading.Event()
    print(f"[flood] {concurrency} workers -> {method} {target_url} "
          f"for up to {duration}s")

    total = 0
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(
                flood_worker, i, target_url, method, duration,
                logger, stop_event, run_id, token, payload,
            )
            for i in range(concurrency)
        ]
        try:
            for future in as_completed(futures):
                total += future.result()
        except Exception:
            stop_event.set()
            raise

    return total


def creds_stuff_worker(
    worker_id, attempts, customers, logger, run_id, seed, auth_url=AUTH_URL
):
    """Use deterministic mixtures; include valid and invalid credential pairs."""
    rng = random.Random(seed + worker_id)
    real = [customer.username for customer in customers]
    fake = [f"fabricated{worker_id}_{i}@mail.test" for i in range(20)]
    candidates = real + fake
    results = []

    with requests.Session() as session:
        for index in range(attempts):
            # One valid seeded pair in every ten attempts when possible;
            # all other attempts use incorrect passwords or fake usernames.
            if index % 10 == 0:
                username = real[(worker_id + index) % len(real)]
                password = DEMO_PASSWORD
            else:
                username = rng.choice(candidates)
                password = rng.choice(
                    [p for p in COMMON_PASSWORD_GUESSES if p != DEMO_PASSWORD]
                )

            outcome = request_and_log(
                session, logger,
                run_id=run_id, mode="creds_stuff", worker_id=worker_id,
                method="POST", url=f"{auth_url}/api/v2/auth/login",
                payload={"username": username, "password": password},
                username=username,
            )
            results.append(outcome)

    return results



def run_creds_stuff(
    concurrency, attempts_per_worker, customers, logger, run_id, seed,
    auth_url=AUTH_URL,
):
    """Run bounded credential-stuffing workers and collect their outcomes."""
    if not customers:
        raise ValueError("Customer pool is empty; cannot run credential simulation.")

    results = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(
                creds_stuff_worker,
                worker_id,
                attempts_per_worker,
                customers,
                logger,
                run_id,
                seed,
                auth_url,
            )
            for worker_id in range(concurrency)
        ]
        for future in as_completed(futures):
            results.extend(future.result())

    return results


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def bounded_int(maximum):
    def parse(value):
        number = positive_int(value)
        if number > maximum:
            raise argparse.ArgumentTypeError(f"must not exceed {maximum}")
        return number
    return parse


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Concurrent bot-traffic simulator for the local API-Sentinel lab."
    )
    parser.add_argument("--mode", choices=["flood", "creds_stuff"], required=True)
    parser.add_argument("--concurrency", type=bounded_int(MAX_CONCURRENCY), default=20)
    parser.add_argument("--duration", type=bounded_int(MAX_DURATION), default=15)
    parser.add_argument(
        "--attempts-per-worker",
        type=bounded_int(MAX_ATTEMPTS_PER_WORKER),
        default=10,
    )
    parser.add_argument("--target", choices=["orders", "login"], default="orders")
    parser.add_argument(
        "--use-proxy",
        action="store_true",
        help="Explicitly route attack traffic through local mock rate-limit proxies.",
    )
    parser.add_argument("--seed", type=int, default=1701)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args(argv)
    auth_url = "http://127.0.0.1:7001" if args.use_proxy else AUTH_URL
    order_url = "http://127.0.0.1:7003" if args.use_proxy else ORDER_URL

    run_id = str(uuid.uuid4())
    logger = SafeAttackLogger(AttackLogger("bot_traffic", output_dir=args.output_dir))

    try:
        start = time.monotonic()

        if args.mode == "flood":
            if args.target == "orders":
                customers = build_customer_pool()
                login = requests.post(
                    f"{auth_url}/api/v2/auth/login",
                    json={
                        "username": customers[0].username,
                        "password": customers[0].password,
                    },
                    timeout=REQUEST_TIMEOUT,
                )
                if login.status_code != 200:
                    raise RuntimeError(
                        f"Could not authenticate flood user (HTTP {login.status_code})."
                    )
                token = login.json().get("token")
                if not token:
                    raise RuntimeError("Login response did not contain a token.")

                target = validate_local_url(
                    f"{order_url}/api/v2/orders", allow_proxy=args.use_proxy
                )
                method, payload = "GET", None
            else:
                token = None
                target = validate_local_url(
                    f"{auth_url}/api/v2/auth/login", allow_proxy=args.use_proxy
                )
                # Intentionally invalid credentials: unauthenticated login flood.
                method = "POST"
                payload = {"username": "invalid-bot@mail.test", "password": "wrong"}

            total = run_flood(
                target, method, args.concurrency, args.duration,
                logger, run_id, token=token, payload=payload,
            )
            elapsed = max(time.monotonic() - start, 0.001)
            print("\n=== FLOOD COMPLETE ===")
            print(f"Run ID: {run_id}")
            print(f"Requests attempted: {total}")
            print(f"Elapsed: {elapsed:.2f}s")
            print(f"Achieved rate: {total / elapsed:.1f} req/s")

        else:
            customers = build_customer_pool()
            results = run_creds_stuff(
                args.concurrency, args.attempts_per_worker,
                customers, logger, run_id, args.seed, auth_url=auth_url,
            )
            elapsed = max(time.monotonic() - start, 0.001)
            successes = sum(item["success"] for item in results)
            print("\n=== CREDENTIAL STUFFING COMPLETE ===")
            print(f"Run ID: {run_id}")
            print(f"Attempts: {len(results)}")
            print(f"HTTP 200 responses: {successes}")
            print(f"Success rate: {successes / len(results) * 100:.1f}%")
            print(f"Elapsed: {elapsed:.2f}s")
            print(f"Achieved rate: {len(results) / elapsed:.1f} req/s")
            print(f"Request errors: {sum(item['error'] is not None for item in results)}")

        print(f"Log: {logger.path}")
        return 0
    finally:
        logger._logger.close()


if __name__ == "__main__":
    raise SystemExit(main())
