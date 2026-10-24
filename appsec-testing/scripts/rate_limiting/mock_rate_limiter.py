#!/usr/bin/env python3
"""MOCK DATA — TEMPORARY shared-state rate-limiting reverse proxy."""
import hashlib
import os
import sqlite3
import time
from urllib.parse import urlparse

import requests
from flask import Flask, Response, jsonify, request

UPSTREAM_URL = os.getenv("UPSTREAM_URL", "")
LISTEN_PORT = int(os.getenv("LISTEN_PORT", "7001"))
LIMIT = int(os.getenv("RATE_LIMIT_MAX", "20"))
WINDOW = float(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "5"))
DB_PATH = os.getenv(
    "RATE_LIMIT_DB",
    os.path.abspath("logs/rate_limit_state.sqlite3"),
)
TIMEOUT = 3
HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate",
    "proxy-authorization", "te", "trailers", "transfer-encoding",
    "upgrade", "host", "content-length",
}

app = Flask(__name__)


def validate_config():
    parsed = urlparse(UPSTREAM_URL)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.port not in {5001, 5002, 5003, 5004}
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or LIMIT < 1
        or WINDOW <= 0
    ):
        raise ValueError("Invalid local upstream or rate-limit configuration.")


def connect_db():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.execute("""
        CREATE TABLE IF NOT EXISTS request_windows (
            identity TEXT NOT NULL,
            timestamp REAL NOT NULL
        )
    """)
    db.execute("""
        CREATE INDEX IF NOT EXISTS idx_request_windows_identity_time
        ON request_windows(identity, timestamp)
    """)
    return db


def client_identity():
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer ") and authorization[7:].strip():
        raw_identity = "token:" + authorization[7:].strip()
    else:
        raw_identity = "ip:" + (request.remote_addr or "unknown")
    return hashlib.sha256(raw_identity.encode("utf-8")).hexdigest()


def check_and_record(identity, now=None):
    """Atomically admit a request against the shared sliding window."""
    now = time.time() if now is None else now
    cutoff = now - WINDOW
    db = connect_db()
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "DELETE FROM request_windows WHERE timestamp <= ?",
            (cutoff,),
        )
        rows = db.execute(
            "SELECT timestamp FROM request_windows "
            "WHERE identity = ? AND timestamp > ? ORDER BY timestamp",
            (identity, cutoff),
        ).fetchall()

        if len(rows) >= LIMIT:
            retry_after = max(0, int(rows[0][0] + WINDOW - now + 0.999))
            db.commit()
            return False, retry_after

        db.execute(
            "INSERT INTO request_windows(identity, timestamp) VALUES (?, ?)",
            (identity, now),
        )
        db.commit()
        return True, 0
    finally:
        db.close()


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "component": "mock-rate-limiter",
        "temporary": True,
        "limit": LIMIT,
        "window_seconds": WINDOW,
    })


@app.route("/", defaults={"path": ""}, methods=[
    "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"
])
@app.route("/<path:path>", methods=[
    "GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"
])
def proxy(path):
    allowed, retry_after = check_and_record(client_identity())
    if not allowed:
        response = jsonify({
            "error": "rate_limited",
            "retry_after_seconds": retry_after,
        })
        response.status_code = 429
        response.headers["Retry-After"] = str(retry_after)
        return response

    upstream = UPSTREAM_URL.rstrip("/") + "/" + path
    if request.query_string:
        upstream += "?" + request.query_string.decode("latin-1")

    headers = {
        key: value for key, value in request.headers.items()
        if key.lower() not in HOP_HEADERS
    }

    try:
        upstream_response = requests.request(
            method=request.method,
            url=upstream,
            headers=headers,
            data=request.get_data(),
            timeout=TIMEOUT,
            allow_redirects=False,
        )
    except requests.RequestException:
        return jsonify({"error": "upstream_unavailable"}), 502

    response_headers = [
        (key, value)
        for key, value in upstream_response.headers.items()
        if key.lower() not in HOP_HEADERS
        and key.lower() != "content-encoding"
    ]
    return Response(
        upstream_response.content,
        status=upstream_response.status_code,
        headers=response_headers,
    )


if __name__ == "__main__":
    validate_config()
    app.run(host="127.0.0.1", port=LISTEN_PORT, threaded=True)
