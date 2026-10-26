"""Day 21 test-only billing enforcement adapter.

This is an application-layer simulation for verifying concurrent traffic,
explicit attack denials, and legitimate-request success. It is NOT an eBPF
program and must not be reported as proof of kernel-level packet drops.
"""

import os
import threading
import time
from collections import deque
from urllib.parse import urlsplit

import requests
from flask import Flask, Response, jsonify, request

UPSTREAM_URL = os.environ.get(
    "DAY21_BILLING_UPSTREAM_URL", "http://127.0.0.1:5004"
).rstrip("/")
LISTEN_HOST = os.environ.get("DAY21_ENFORCER_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("DAY21_ENFORCER_PORT", "8004"))
THRESHOLD = int(os.environ.get("DAY21_ATTACK_THRESHOLD", "3"))
WINDOW_SECONDS = float(os.environ.get("DAY21_ATTACK_WINDOW_SECONDS", "10"))
BLOCK_SECONDS = float(os.environ.get("DAY21_ATTACK_BLOCK_SECONDS", "20"))
CONNECT_TIMEOUT = float(os.environ.get("DAY21_CONNECT_TIMEOUT", "0.5"))
READ_TIMEOUT = float(os.environ.get("DAY21_READ_TIMEOUT", "3.0"))

if THRESHOLD < 1 or WINDOW_SECONDS <= 0 or BLOCK_SECONDS <= 0:
    raise ValueError("Threshold and enforcement durations must be positive")

parsed_upstream = urlsplit(UPSTREAM_URL)
if (
    parsed_upstream.scheme != "http"
    or parsed_upstream.hostname not in {"127.0.0.1", "localhost", "::1"}
    or parsed_upstream.username is not None
    or parsed_upstream.password is not None
    or parsed_upstream.query
    or parsed_upstream.fragment
):
    raise ValueError("Day 21 upstream must be a local HTTP URL")

app = Flask(__name__)
_lock = threading.Lock()
_attack_paths = deque()
_blocked_until = 0.0
_counters = {
    "attack_requests": 0,
    "attack_blocked": 0,
    "legitimate_requests": 0,
    "legitimate_forwarded": 0,
    "upstream_errors": 0,
}


@app.get("/__enforcer_health")
def enforcer_health():
    return jsonify({
        "status": "ok",
        "component": "day21_test_simulation",
        "enforcement_mode": "application_layer_simulation",
    })


@app.get("/__day21_stats")
def day21_stats():
    with _lock:
        return jsonify({
            **_counters,
            "currently_blocked": time.monotonic() < _blocked_until,
            "threshold": THRESHOLD,
            "window_seconds": WINDOW_SECONDS,
            "block_seconds": BLOCK_SECONDS,
            "evidence_type": "application_layer_simulation",
        })


@app.route(
    "/",
    defaults={"path": ""},
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
@app.route(
    "/<path:path>",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
)
def forward(path):
    global _blocked_until

    full_path = "/" + path
    is_invoice = full_path.startswith("/api/v2/billing/invoices/")
    traffic_class = request.headers.get("X-Day21-Traffic-Class", "").lower()

    if is_invoice and traffic_class == "attack":
        now = time.monotonic()
        with _lock:
            _counters["attack_requests"] += 1

            while _attack_paths and now - _attack_paths[0][0] > WINDOW_SECONDS:
                _attack_paths.popleft()

            if now < _blocked_until:
                _counters["attack_blocked"] += 1
                return jsonify({
                    "error": "day21_test_enforcement_block",
                    "evidence_type": "application_layer_simulation",
                }), 403, {"X-Day21-Enforcement": "blocked"}

            # Count distinct invoice paths in the active window.
            if not any(existing_path == full_path for _, existing_path in _attack_paths):
                _attack_paths.append((now, full_path))

            if len({item_path for _, item_path in _attack_paths}) >= THRESHOLD:
                _blocked_until = now + BLOCK_SECONDS
                _counters["attack_blocked"] += 1
                return jsonify({
                    "error": "day21_test_enforcement_block",
                    "evidence_type": "application_layer_simulation",
                }), 403, {"X-Day21-Enforcement": "blocked"}

    if is_invoice and traffic_class == "legitimate":
        with _lock:
            _counters["legitimate_requests"] += 1

    target = f"{UPSTREAM_URL}{full_path}"
    if request.query_string:
        target += "?" + request.query_string.decode("latin-1")

    try:
        upstream = requests.request(
            method=request.method,
            url=target,
            headers={
                key: value
                for key, value in request.headers
                if key.lower() not in {
                    "host", "content-length", "connection",
                    "x-day21-traffic-class",
                }
            },
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        )
    except requests.RequestException:
        with _lock:
            _counters["upstream_errors"] += 1
        return jsonify({"error": "upstream_unavailable"}), 502

    if is_invoice and traffic_class == "legitimate" and upstream.status_code < 400:
        with _lock:
            _counters["legitimate_forwarded"] += 1

    excluded_headers = {"content-encoding", "content-length", "transfer-encoding", "connection"}
    headers = [
        (key, value)
        for key, value in upstream.headers.items()
        if key.lower() not in excluded_headers
    ]
    headers.append(("X-Day21-Enforcement", "forwarded"))
    headers.append(("X-Day21-Evidence-Type", "application-layer-simulation"))

    return Response(
        upstream.content,
        status=upstream.status_code,
        headers=headers,
    )


if __name__ == "__main__":
    app.run(host=LISTEN_HOST, port=LISTEN_PORT, threaded=True)
