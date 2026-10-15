import logging

from sqlalchemy.orm import sessionmaker

from app.database import Base, engine, SessionLocal
from app.models import TransactionLog
from app.transaction_correlator import HTTPTransaction

logger = logging.getLogger(__name__)


def initialize_database() -> None:
    """Create missing tables for the registered SQLAlchemy models."""
    Base.metadata.create_all(bind=engine)


class TransactionStore:
    """Persist completed HTTP transactions."""

    def __init__(self, session_factory: sessionmaker = SessionLocal):
        self.session_factory = session_factory

    def save(self, transaction: HTTPTransaction) -> int:
        """Save a completed transaction and return its database ID."""
        request = transaction.request
        response = transaction.response

        record = TransactionLog(
            request_method=request.method,
            request_uri=request.uri,
            response_status=response.status_code,
            request_headers=request.headers,
            response_headers=response.headers,
            request_body=request.body.decode(
                "utf-8", errors="replace"
            ) if isinstance(request.body, bytes) else request.body,
            response_body=response.body.decode(
                "utf-8", errors="replace"
            ) if isinstance(response.body, bytes) else response.body,
        )

        with self.session_factory() as session:
            try:
                session.add(record)
                session.commit()
                session.refresh(record)
                return record.id
            except Exception:
                session.rollback()
                logger.exception("Failed to persist HTTP transaction")
                raise
