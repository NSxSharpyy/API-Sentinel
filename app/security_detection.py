"""Lab-scoped BOLA detection and sensitive-field redaction."""
from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from urllib.parse import urlsplit

from app.models import SecurityIncident
from app.schemas import SecurityIncidentSchema

REDACTED = "[REDACTED]"
SENSITIVE = {
    "authorization", "proxy_authorization", "cookie", "set_cookie",
    "password", "passwd", "token", "access_token", "refresh_token",
    "client_secret", "secret", "api_key", "apikey",
}
INVOICE_PATH = re.compile(r"^/api/v2/billing/invoices/([0-9]+)$")


def _key(value):
    return str(value).strip().lower().replace("-", "_")


def _json_object(value):
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            result = json.loads(value)
            return result if isinstance(result, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def redact_headers(value):
    if not isinstance(value, dict):
        return {}
    return {
        key: REDACTED if _key(key) in SENSITIVE else child
        for key, child in value.items()
    }


def _redact_tree(value):
    if isinstance(value, dict):
        return {
            key: REDACTED if _key(key) in SENSITIVE else _redact_tree(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_redact_tree(item) for item in value]
    return value


def redact_body(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if not isinstance(value, str):
        value = str(value)
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value
    return json.dumps(
        _redact_tree(parsed), separators=(",", ":"), ensure_ascii=False
    )


class BOLADetector:
    """Heuristic detector for the local BOLA training lab.

    A token fingerprint is associated with user_id from an observed successful
    login response. The sensor does NOT independently verify the token's HMAC.
    Do not treat this lab heuristic as production identity verification.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._token_users = {}
        self.detection_count = 0
        self.capture_to_detection_count = 0
        self.last_capture_to_detection_latency_ms = 0.0
        self.total_capture_to_detection_latency_ms = 0.0
        self.max_capture_to_detection_latency_ms = 0.0
        self.last_detection_at = None

    @staticmethod
    def _fingerprint(headers):
        if not isinstance(headers, dict):
            return None
        auth = next(
            (v for k, v in headers.items() if _key(k) == "authorization"),
            None,
        )
        if not isinstance(auth, str):
            return None
        parts = auth.strip().split(None, 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None
        return hashlib.sha256(parts[1].encode("utf-8")).hexdigest()

    @staticmethod
    def requires_ordered_processing(transaction):
        """Identify routes whose processing depends on BOLA detector state."""
        request = transaction.request
        method = (request.method or "").upper()
        try:
            path = urlsplit(request.uri or "").path
        except ValueError:
            return True
        if method == "POST" and path == "/api/v2/auth/login":
            return True
        return method == "GET" and INVOICE_PATH.fullmatch(path) is not None

    def inspect(
        self, transaction, transaction_id, session, source_ip,
        endpoint_id: int | None = None,
    ):
        request = transaction.request
        response = transaction.response
        method = (request.method or "").upper()
        path = urlsplit(request.uri or "").path
        status = response.status_code or 0
        # Learn a lab identity from a successful login response.
        if method == "POST" and path == "/api/v2/auth/login":
            if not 200 <= status < 300:
                return None

            resp_body = _json_object(response.body)
            if resp_body is None:
                return None
            token = resp_body.get("token")
            user_id = resp_body.get("user_id")
            if (
                isinstance(token, str) and token
                and isinstance(user_id, int)
                and not isinstance(user_id, bool)
                and user_id > 0
            ):
                return {
                    "fingerprint": hashlib.sha256(
                        token.encode("utf-8")
                    ).hexdigest(),
                    "user_id": user_id,
                }
            return None

        match = INVOICE_PATH.fullmatch(path)
        if method != "GET" or match is None or not 200 <= status < 300:
            return None

        resp_body = _json_object(response.body)
        if resp_body is None:
            return None

        requested_id = int(match.group(1))
        invoice_id = resp_body.get("id")
        owner_id = resp_body.get("owner_id")
        if (
            isinstance(invoice_id, bool) or not isinstance(invoice_id, int)
            or invoice_id != requested_id
            or isinstance(owner_id, bool) or not isinstance(owner_id, int)
        ):
            return None

        fingerprint = self._fingerprint(request.headers)
        if fingerprint is None:
            return None

        with self._lock:
            requester_id = self._token_users.get(fingerprint)

        if requester_id is None or requester_id == owner_id:
            return None

        detected_at = datetime.now(timezone.utc)
        captured_at = request.captured_at
        latency_ms = None
        if captured_at is not None:
            if captured_at.tzinfo is None or captured_at.utcoffset() is None:
                captured_at = captured_at.replace(tzinfo=timezone.utc)
            elapsed = (
                detected_at - captured_at.astimezone(timezone.utc)
            ).total_seconds() * 1000
            if elapsed >= 0:
                latency_ms = elapsed

        incident = SecurityIncident(
            endpoint_id=endpoint_id,
            transaction_id=transaction_id,
            detected_at=detected_at,
            severity="high",
            title="Potential BOLA: cross-user invoice access (lab heuristic)",
            description=(
                f"Observed login associated with user_id={requester_id}; "
                f"GET {path} returned invoice_id={invoice_id}, owner_id={owner_id}. "
                "The sensor associates identity using an observed login response "
                "and matching token fingerprint; it does not independently "
                "verify the token signature."
            ),
            source_ip=source_ip,
            status="open",
        )
        session.add(incident)
        session.flush()
        incident_payload = SecurityIncidentSchema.from_model(
            incident
        ).model_dump(mode="python")
        return {
            "detected": True,
            "detected_at": detected_at.isoformat(),
            "latency_ms": latency_ms,
            "incident": incident_payload,
        }

    def after_commit(self, outcome):
        if not isinstance(outcome, dict):
            return
        with self._lock:
            fingerprint = outcome.get("fingerprint")
            user_id = outcome.get("user_id")
            if isinstance(fingerprint, str) and isinstance(user_id, int):
                if len(self._token_users) >= 10000 and fingerprint not in self._token_users:
                    self._token_users.pop(next(iter(self._token_users)))
                self._token_users[fingerprint] = user_id

            if not outcome.get("detected"):
                return
            self.detection_count += 1
            self.last_detection_at = outcome.get("detected_at")
            latency = outcome.get("latency_ms")
            if isinstance(latency, (int, float)) and not isinstance(latency, bool):
                self.capture_to_detection_count += 1
                self.last_capture_to_detection_latency_ms = float(latency)
                self.total_capture_to_detection_latency_ms += float(latency)
                self.max_capture_to_detection_latency_ms = max(
                    self.max_capture_to_detection_latency_ms, float(latency)
                )

    def snapshot(self):
        with self._lock:
            count = self.capture_to_detection_count
            return {
                "detection_rule": "lab_scoped_bola_invoice_owner_mismatch",
                "identity_source": (
                    "observed successful login response; token signature "
                    "not independently verified"
                ),
                "bola_detection_count": self.detection_count,
                "capture_to_detection_count": count,
                "last_capture_to_detection_latency_ms":
                    self.last_capture_to_detection_latency_ms,
                "average_capture_to_detection_latency_ms":
                    self.total_capture_to_detection_latency_ms / count if count else 0.0,
                "max_capture_to_detection_latency_ms":
                    self.max_capture_to_detection_latency_ms,
                "last_detection_at": self.last_detection_at,
            }
