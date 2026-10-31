#!/usr/bin/env python3
"""TEMPORARY MOCK — not a real eBPF sidecar.

Adds a configurable delay and forwards HTTP requests to one upstream API.
Replace this proxy with the real sidecar when it is delivered.
"""
import os
import time
import threading
import requests
from flask import Flask, Response, jsonify, request

try:
    SIDECAR_OVERHEAD_MS = float(os.getenv("SIDECAR_OVERHEAD_MS", "2.0"))
except ValueError as exc:
    raise SystemExit("SIDECAR_OVERHEAD_MS must be a non-negative number") from exc

if SIDECAR_OVERHEAD_MS < 0:
    raise SystemExit("SIDECAR_OVERHEAD_MS must be non-negative")

UPSTREAM_URL = os.environ.get("UPSTREAM_URL", "").rstrip("/")
if not UPSTREAM_URL:
    raise SystemExit("UPSTREAM_URL is required")

try:
    LISTEN_PORT = int(os.environ.get("LISTEN_PORT", ""))
except ValueError as exc:
    raise SystemExit("LISTEN_PORT must be an integer") from exc

if not 1 <= LISTEN_PORT <= 65535:
    raise SystemExit("LISTEN_PORT must be between 1 and 65535")

app = Flask("mock-ebpf-sidecar")
_thread_local = threading.local()


def get_session():
    if not hasattr(_thread_local, "session"):
        _thread_local.session = requests.Session()
    return _thread_local.session

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


@app.get("/health")
def health():
    return jsonify(
        service="mock-ebpf-sidecar",
        status="ok",
        mock=True,
        overhead_ms=SIDECAR_OVERHEAD_MS,
        upstream=UPSTREAM_URL,
    ), 200


@app.route(
    "/",
    defaults={"path": ""},
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
@app.route(
    "/<path:path>",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
)
def proxy(path):
    # Deliberate mock delay, not a measurement of real eBPF overhead.
    time.sleep(SIDECAR_OVERHEAD_MS / 1000.0)

    upstream_url = f"{UPSTREAM_URL}/{path}"
    request_headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
        and key.lower() not in {"host", "content-length"}
    }

    try:
        upstream_response = get_session().request(
            method=request.method,
            url=upstream_url,
            headers=request_headers,
            data=request.get_data(),
            params=request.args,
            timeout=10,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        app.logger.warning("Mock sidecar upstream request failed: %s", exc)
        return jsonify(
            error="upstream_unavailable",
            service="mock-ebpf-sidecar",
        ), 502

    response_headers = {
        key: value
        for key, value in upstream_response.headers.items()
        if key.lower() not in HOP_BY_HOP_HEADERS
        and key.lower() not in {"content-length", "content-encoding"}
    }

    return Response(
        upstream_response.content,
        status=upstream_response.status_code,
        headers=response_headers,
    )


if __name__ == "__main__":
    from waitress import serve

    threads = int(os.environ.get("SIDECAR_THREADS", "8"))
    if threads < 1:
        raise SystemExit("SIDECAR_THREADS must be a positive integer")

    serve(
        app,
        host="0.0.0.0",
        port=LISTEN_PORT,
        threads=threads,
    )
