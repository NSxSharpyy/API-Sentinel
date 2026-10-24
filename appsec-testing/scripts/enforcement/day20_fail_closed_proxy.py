#!/usr/bin/env python3
"""Day 20 simulated fail-closed HTTP proxy.

Lab-only application-layer simulation. This is not a real TC/eBPF enforcer.
Unlike the fail-open wrapper, this proxy NEVER bypasses the enforcer.
"""

import os

import requests
from flask import Flask, Response, jsonify, request

app = Flask(__name__)

ENFORCER_URL = os.environ.get(
    "DAY20_FAIL_CLOSED_ENFORCER_URL",
    "http://127.0.0.1:8004",
).rstrip("/")

CONNECT_TIMEOUT = float(os.environ.get("DAY20_CONNECT_TIMEOUT", "0.5"))
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
    """Check whether the simulated enforcement service is available."""
    try:
        response = requests.get(
            f"{ENFORCER_URL}/__enforcer_health",
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
        )
        return response.status_code == 200
    except requests.RequestException:
        return False


@app.get("/__fail_closed_proxy_health")
def proxy_health():
    """Report proxy process health independently of enforcer availability."""
    return jsonify({
        "status": "ok",
        "component": "day20-fail-closed-proxy",
        "mode": "fail-closed",
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
    """Forward only through the enforcer; never connect directly to billing."""
    if not enforcer_is_healthy():
        response = jsonify({
            "error": "enforcement_unavailable",
            "mode": "fail-closed",
        })
        response.status_code = 503
        response.headers["X-Fail-Closed-Mode"] = "reject"
        response.headers["X-Enforcement-Active"] = "false"
        return response

    target = f"{ENFORCER_URL}/{path}"
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
        # The enforcer may have failed after the health check.
        # Never fall back to billing.
        response = jsonify({
            "error": "enforcement_upstream_unavailable",
            "mode": "fail-closed",
        })
        response.status_code = 503
        response.headers["X-Fail-Closed-Mode"] = "reject"
        response.headers["X-Enforcement-Active"] = "false"
        return response

    response = Response(
        upstream_response.content,
        status=upstream_response.status_code,
    )

    for name, value in upstream_response.headers.items():
        if name.lower() not in HOP_BY_HOP_HEADERS:
            response.headers[name] = value

    response.headers["X-Fail-Closed-Mode"] = "enforced"
    response.headers["X-Enforcement-Active"] = "true"
    return response


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("DAY20_FAIL_CLOSED_PORT", "8006")),
        threaded=True,
        use_reloader=False,
    )
