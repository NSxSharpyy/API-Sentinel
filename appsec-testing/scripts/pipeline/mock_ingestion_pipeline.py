"""Temporary mock HTTP receiver for simulated pipeline captures."""

import json
import os
import random
import threading
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request


DEFAULT_OUTPUT = "logs/captures.jsonl"
CAPTURE_OUTPUT = os.environ.get("CAPTURES_PATH", DEFAULT_OUTPUT)
MOCK_DROP_RATE = float(os.environ.get("MOCK_DROP_RATE", "0"))
if not 0 <= MOCK_DROP_RATE <= 1:
    raise ValueError("MOCK_DROP_RATE must be between 0 and 1")

app = Flask(__name__)
_rng = random.Random()
_rng_lock = threading.Lock()
_capture_lock = threading.Lock()


def record_capture(request_id, metadata, output_path=DEFAULT_OUTPUT):
    """Append one simulated capture to a JSONL file."""
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError("request_id must be a non-empty string")
    if not isinstance(metadata, dict):
        raise TypeError("metadata must be a dictionary")

    record = {
        **metadata,
        "request_id": request_id,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "capture_source": "mock",
    }

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with _capture_lock:
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, separators=(",", ":")) + "\n")
            file.flush()

    return record


@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "capture_output": CAPTURE_OUTPUT,
        "mock_drop_rate": MOCK_DROP_RATE,
    }), 200


@app.post("/capture")
def capture():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "Expected a JSON object"}), 400

    request_id = payload.get("request_id")
    if not isinstance(request_id, str) or not request_id.strip():
        return jsonify({"error": "request_id must be a non-empty string"}), 400

    metadata = {
        key: payload[key]
        for key in ("service", "method", "path", "source")
        if key in payload
    }

    with _rng_lock:
        should_drop = _rng.random() < MOCK_DROP_RATE

    if should_drop:
        return jsonify({
            "status": "dropped",
            "request_id": request_id,
        }), 202

    try:
        record = record_capture(
            request_id,
            metadata,
            output_path=CAPTURE_OUTPUT,
        )
    except (OSError, TypeError, ValueError) as exc:
        app.logger.exception("Could not record capture")
        return jsonify({"error": str(exc)}), 500

    return jsonify({
        "status": "captured",
        "request_id": record["request_id"],
    }), 201


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5099, threaded=True)
