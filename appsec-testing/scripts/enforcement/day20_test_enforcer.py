
#!/usr/bin/env python3
"""Day 20 simulated HTTP enforcer for fail-open verification.

This is a lab-only HTTP proxy, not the real TC/eBPF enforcer.
It forwards application requests to the existing billing service.
"""

import os

import requests
from flask import Flask, Response, jsonify, request

app = Flask(__name__)

UPSTREAM_URL = os.environ.get(
    "DAY20_ENFORCER_UPSTREAM_URL",
    "http://127.0.0.1:5004",
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


@app.get("/__enforcer_health")
def health():
    """Dedicated health endpoint used by the fail-open wrapper."""
    return jsonify({"status": "ok", "component": "day20-test-enforcer"}), 200


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
    """Forward application requests to billing."""
    target = f"{UPSTREAM_URL}/{path}"
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
        return jsonify({"error": "billing_upstream_unavailable"}), 502

    response = Response(
        upstream_response.content,
        status=upstream_response.status_code,
    )

    for name, value in upstream_response.headers.items():
        if name.lower() not in HOP_BY_HOP_HEADERS:
            response.headers[name] = value

    response.headers["X-Day20-Test-Enforcer"] = "active"
    return response


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=int(os.environ.get("DAY20_ENFORCER_PORT", "8004")),
        threaded=True,
        use_reloader=False,
    )
