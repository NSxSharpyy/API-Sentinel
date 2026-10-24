import logging

from sqlalchemy.orm import sessionmaker

from app.database import Base, engine, SessionLocal
from app.models import TransactionLog, utc_now
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


class TransactionStore:
    """Persist completed HTTP transactions."""

    def __init__(self, session_factory: sessionmaker = SessionLocal):
        self.session_factory = session_factory
        self.bola_detector = BOLADetector()

    def save(self, transaction: HTTPTransaction) -> int:
        """Save a completed transaction and return its database ID."""
        request = transaction.request
        response = transaction.response

        source_ip, destination_ip = _request_endpoint_ips(
            request.connection_id
        )

        record = TransactionLog(
            timestamp=request.captured_at or utc_now(),
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

        with self.session_factory() as session:
            try:
                session.add(record)
                session.flush()
                outcome = self.bola_detector.inspect(
                    transaction, record.id, session, source_ip
                )
                session.commit()
                session.refresh(record)
                self.bola_detector.after_commit(outcome)
                return record.id
                session.refresh(record)
                return record.id
            except Exception:
                session.rollback()
                logger.exception("Failed to persist HTTP transaction")
                raise
