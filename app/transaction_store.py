import logging
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.alert_bus import AlertBus, AlertEvent
from app.database import Base, engine, SessionLocal
from app.models import DiscoveredEndpoint, TransactionLog, utc_now
from app.transaction_correlator import HTTPTransaction
from app.security_detection import BOLADetector, redact_body, redact_headers

logger = logging.getLogger(__name__)


def initialize_database() -> None:
    """Create missing tables for the registered SQLAlchemy models."""
    Base.metadata.create_all(bind=engine)


def _request_endpoint_ips(
    connection_id: str | None,
) -> tuple[str | None, str | None]:
    """Extract source and destination IPs from a directional connection ID."""
    if not connection_id or "|" not in connection_id:
        return None, None

    try:
        _, endpoints = connection_id.split("|", 1)
        source, destination = endpoints.split("->", 1)
        source_ip, _ = source.rsplit(":", 1)
        destination_ip, _ = destination.rsplit(":", 1)
    except ValueError:
        return None, None

    if not source_ip or not destination_ip:
        return None, None

    return source_ip, destination_ip


def _as_utc(value: datetime) -> datetime:
    """Normalize SQLite-naive and timezone-aware timestamps for comparisons."""
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _endpoint_identity(transaction: HTTPTransaction, destination_ip: str | None):
    """Derive a stable host/method/path key from a completed HTTP request."""
    request = transaction.request
    method = (request.method or "").strip().upper()
    uri = request.uri or ""
    try:
        parsed_uri = urlsplit(uri)
    except ValueError:
        return None

    path = parsed_uri.path or ("*" if uri == "*" else "/")
    raw_host = next(
        (str(value).strip() for key, value in (request.headers or {}).items()
         if str(key).strip().lower() == "host" and str(value).strip()),
        None,
    )
    if not raw_host:
        raw_host = parsed_uri.netloc or destination_ip

    if not method or not raw_host or not path:
        return None

    host = raw_host.strip().lower()
    if host.endswith("."):
        host = host[:-1]
    if (
        not host
        or len(host) > 255
        or len(path) > 2048
        or any(ord(char) < 32 or ord(char) == 127 for char in host)
        or "/" in host
        or "\\" in host
    ):
        return None

    return host, method, path


class TransactionStore:
    """Persist completed HTTP transactions."""

    def __init__(
        self,
        session_factory: sessionmaker = SessionLocal,
        alert_bus: AlertBus | None = None,
    ):
        self.session_factory = session_factory
        self.bola_detector = BOLADetector()
        self.alert_bus = alert_bus
        self.blocklist_policy = None

    def _upsert_endpoint(
        self, session, transaction: HTTPTransaction, destination_ip: str | None,
        observed_at: datetime,
    ) -> DiscoveredEndpoint | None:
        """Create or refresh the endpoint index entry for a request."""
        identity = _endpoint_identity(transaction, destination_ip)
        if identity is None:
            return None
        host, method, path = identity
        endpoint = session.scalar(
            select(DiscoveredEndpoint).where(
                DiscoveredEndpoint.host == host,
                DiscoveredEndpoint.method == method,
                DiscoveredEndpoint.path == path,
            )
        )
        if endpoint is None:
            candidate = DiscoveredEndpoint(
                host=host, method=method, path=path,
                first_seen=observed_at, last_seen=observed_at,
            )
            try:
                # The savepoint handles concurrent captures of the same route
                # without poisoning the surrounding transaction.
                with session.begin_nested():
                    session.add(candidate)
                    session.flush()
                endpoint = candidate
            except IntegrityError:
                endpoint = session.scalar(
                    select(DiscoveredEndpoint).where(
                        DiscoveredEndpoint.host == host,
                        DiscoveredEndpoint.method == method,
                        DiscoveredEndpoint.path == path,
                    )
                )
                if endpoint is None:
                    raise

        last_seen = _as_utc(endpoint.last_seen)
        if _as_utc(observed_at) > last_seen:
            endpoint.last_seen = observed_at
        return endpoint

    def _publish_alert(self, outcome: dict | None) -> None:
        """Publish a committed incident without masking persistence success."""
        if (
            self.alert_bus is None
            or not isinstance(outcome, dict)
            or not outcome.get("detected")
        ):
            return

        incident_payload = outcome.get("incident")
        if not isinstance(incident_payload, dict):
            logger.error(
                "Detected incident has no canonical payload; alert not published"
            )
            return

        incident_id = incident_payload.get("incident_id")
        try:
            event = AlertEvent(**incident_payload)
            _, dropped = self.alert_bus.publish(event)
            if dropped:
                logger.warning(
                    "Security incident persisted but alert delivery was dropped "
                    "(incident_id=%s, dropped=%d)",
                    event.incident_id,
                    dropped,
                )
        except Exception:
            logger.exception(
                "Security incident persisted but alert publication failed "
                "(incident_id=%s)",
                incident_id,
            )

    def can_batch(self, transactions: list[HTTPTransaction]) -> bool:
        """Batch only transactions that cannot affect BOLA state."""
        return all(
            not self.bola_detector.requires_ordered_processing(transaction)
            for transaction in transactions
        )

    def save_batch(self, transactions: list[HTTPTransaction]) -> list[int]:
        """Persist ordinary transactions in one database transaction.

        BOLA-sensitive login and invoice requests must use save() individually.
        Returned durations are preparation time plus an equal share of commit
        time, in nanoseconds, for the worker's existing metrics.
        """
        transactions = list(transactions)
        if not transactions:
            return []
        if not self.can_batch(transactions):
            raise ValueError(
                "BOLA-sensitive transactions must be persisted individually"
            )

        durations = []
        with self.session_factory() as session:
            try:
                for transaction in transactions:
                    started_ns = time.perf_counter_ns()
                    request = transaction.request
                    response = transaction.response
                    source_ip, destination_ip = _request_endpoint_ips(
                        request.connection_id
                    )

                    observed_at = request.captured_at or utc_now()
                    if (
                        observed_at.tzinfo is None
                        or observed_at.utcoffset() is None
                    ):
                        observed_at = observed_at.replace(tzinfo=timezone.utc)
                    observed_at = observed_at.astimezone(timezone.utc)

                    endpoint = self._upsert_endpoint(
                        session, transaction, destination_ip, observed_at
                    )
                    record = TransactionLog(
                        endpoint_id=endpoint.id if endpoint is not None else None,
                        timestamp=observed_at,
                        source_ip=source_ip,
                        destination_ip=destination_ip,
                        request_method=request.method,
                        request_uri=request.uri,
                        response_status=response.status_code,
                        request_headers=redact_headers(request.headers),
                        response_headers=redact_headers(response.headers),
                        request_body=redact_body(request.body),
                        response_body=redact_body(response.body),
                    )
                    session.add(record)
                    durations.append(time.perf_counter_ns() - started_ns)

                commit_started_ns = time.perf_counter_ns()
                session.commit()
                commit_ns = time.perf_counter_ns() - commit_started_ns
            except Exception:
                session.rollback()
                raise

        share_ns = commit_ns // len(transactions)
        return [duration + share_ns for duration in durations]

    def save(self, transaction: HTTPTransaction) -> int:
        """Save a completed transaction and return its database ID."""
        request = transaction.request
        response = transaction.response

        source_ip, destination_ip = _request_endpoint_ips(
            request.connection_id
        )

        observed_at = request.captured_at or utc_now()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        observed_at = observed_at.astimezone(timezone.utc)

        with self.session_factory() as session:
            try:
                endpoint = self._upsert_endpoint(
                    session, transaction, destination_ip, observed_at
                )
                record = TransactionLog(
                    endpoint_id=endpoint.id if endpoint is not None else None,
                    timestamp=observed_at,
                    source_ip=source_ip,
                    destination_ip=destination_ip,
                    request_method=request.method,
                    request_uri=request.uri,
                    response_status=response.status_code,
                    request_headers=redact_headers(request.headers),
                    response_headers=redact_headers(response.headers),
                    request_body=redact_body(request.body),
                    response_body=redact_body(response.body),
                )
                session.add(record)
                session.flush()
                transaction_id = record.id
                outcome = self.bola_detector.inspect(
                    transaction, transaction_id, session, source_ip,
                    endpoint_id=record.endpoint_id,
                )
                session.commit()
                self.bola_detector.after_commit(outcome)
                self._publish_alert(outcome)
                if (
                    self.blocklist_policy is not None
                    and isinstance(outcome, dict)
                    and outcome.get("detected")
                ):
                    try:
                        self.blocklist_policy.evaluate(outcome)
                    except Exception:
                        logger.exception(
                            "Blocklist policy evaluation failed after transaction commit"
                        )
                return transaction_id
            except Exception:
                session.rollback()
                logger.exception("Failed to persist HTTP transaction")
                raise
