"""Shared request IDs and sent-request JSONL logging for API-Sentinel."""

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


class SentRequestsLogger:
    """Record outgoing requests with unique IDs in JSONL format."""

    def __init__(self, output_path="logs/sent_requests.jsonl"):
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    @staticmethod
    def new_request_id():
        """Return a unique UUID for an outgoing request."""
        return str(uuid.uuid4())

    def record(self, request_id, method, path, source, **metadata):
        """Append one sent-request record to the JSONL log."""
        record = {
            "request_id": str(request_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "method": method.upper(),
            "path": path,
            "source": source,
            **metadata,
        }

        if not record["request_id"]:
            raise ValueError("request_id cannot be empty")

        line = json.dumps(record, separators=(",", ":"))

        with self._lock:
            with self.output_path.open("a", encoding="utf-8") as log_file:
                log_file.write(line + "\n")
                log_file.flush()

        return record
