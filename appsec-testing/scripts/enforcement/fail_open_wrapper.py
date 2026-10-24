#!/usr/bin/env python3
"""Day 20 fail-open HTTP wrapper for controlled lab verification.

When the test enforcer is healthy, requests pass through it.
When it is unavailable, requests bypass it and go directly to billing.

This is an application-layer simulation, not an eBPF enforcement component.
"""

import os

import requests
from flask import Flask, Response, jsonify, request

app = Flask(__name__)

ENFORCER_URL = os.environ.get(
    "DAY20_ENFORCER_URL", "http://127.0.0.1:8004"
).rstrip("/")
DIRECT_UPSTREAM_URL = os.environ.get(
    "DAY20_DIRECT_UPSTREAM_URL", "http://127.0.0.1:5004"
).rstrip("/")

CONNECT_TIMEOUT = float(os.environ.get("DAY20_CONNECT_TIMEOUT", "0.3"))
READ_TIMEOUT = float(os.environ.get("DAY20_READ_TIMEOUT", "3.0"))

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


def enforcer_is_healthy():
    """Check the enforcer's dedicated health endpoint."""
    try:
        result = requests.get(
            f"{ENFORCER_URL}/__enforcer_health",
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        )
        return result.status_code == 200
    except requests.RequestException:
        return False


def filtered_headers(headers):
    """Remove hop-by-hop headers before forwarding a response."""
    return {
        name: value
        for name, value in headers.items()
        if name.lower() not in HOP_BY_HOP_HEADERS
    }


@app.get("/__wrapper_health")
def wrapper_health():
    """Report wrapper health and current enforcer availability."""
    healthy = enforcer_is_healthy()
    return jsonify({
        "status": "ok",
        "enforcer_healthy": healthy,
        "routing_mode": "enforced" if healthy else "fail_open",
    }), 200


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
    """Forward via the enforcer when healthy; otherwise bypass it."""
    healthy = enforcer_is_healthy()
    upstream = ENFORCER_URL if healthy else DIRECT_UPSTREAM_URL

    target = f"{upstream}/{path}"
    if request.query_string:
        target += f"?{request.query_string.decode('latin-1')}"

    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in HOP_BY_HOP_HEADERS
    }

    try:
        upstream_response = requests.request(
            method=request.method,
            url=target,
            headers=headers,
            data=request.get_data(),
            allow_redirects=False,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        )

    except requests.RequestException:
        # The enforcer may have crashed after the health check but
        # before the request reached it. Recheck before failing the
        # legitimate request.
        if healthy and not enforcer_is_healthy():
            direct_target = f"{DIRECT_UPSTREAM_URL}/{path}"
            if request.query_string:
                direct_target += f"?{request.query_string.decode('latin-1')}"

            try:
                upstream_response = requests.request(
                    method=request.method,
                    url=direct_target,
                    headers=headers,
                    data=request.get_data(),
                    allow_redirects=False,
                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                )
                healthy = False
            except requests.RequestException:
                return jsonify({
                    "error": "upstream_unavailable",
                    "routing_mode": "fail_open",
                }), 502
        else:
            return jsonify({
                "error": "upstream_unavailable",
                "routing_mode": "enforced" if healthy else "fail_open",
            }), 502


    response = Response(
        upstream_response.content,
        status=upstream_response.status_code,
    )
    for name, value in filtered_headers(upstream_response.headers).items():
        response.headers[name] = value

    response.headers["X-Enforcement-Active"] = (
        "true" if healthy else "false"
    )
    response.headers["X-Fail-Open-Mode"] = (
        "enforced" if healthy else "bypass"
    )
    return response


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("DAY20_WRAPPER_PORT", "8005")),
        threaded=True,
        use_reloader=False,
    )
