"""Async SQLAlchemy transaction persistence, retaining existing BOLA behavior."""
from __future__ import annotations

import logging
import time
from datetime import timezone

from app.database import AsyncSessionLocal, Base, async_engine
from app.models import TransactionLog, utc_now
from app.security_detection import redact_body, redact_headers
from app.transaction_store import TransactionStore, _request_endpoint_ips

logger = logging.getLogger(__name__)


async def initialize_async_database() -> None:
    """Create missing model tables through the asynchronous engine."""
    async with async_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


class AsyncTransactionStore(TransactionStore):
    """Persist transactions and BOLA incidents through AsyncSession."""

    def __init__(
        self,
        session_factory=AsyncSessionLocal,
        alert_bus=None,
    ) -> None:
        super().__init__(
            session_factory=session_factory,
            alert_bus=alert_bus,
        )

    async def save_batch_async(self, transactions) -> list[int]:
        """Persist ordinary transactions in one async database transaction."""
        transactions = list(transactions)
        if not transactions:
            return []
        if not self.can_batch(transactions):
            raise ValueError(
                "BOLA-sensitive transactions must be persisted individually"
            )

        durations = []
        async with self.session_factory() as session:
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

                    endpoint = await session.run_sync(
                        lambda sync_session: self._upsert_endpoint(
                            sync_session,
                            transaction,
                            destination_ip,
                            observed_at,
                        )
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
                await session.commit()
                commit_ns = time.perf_counter_ns() - commit_started_ns
            except Exception:
                await session.rollback()
                raise

        commit_share_ns = commit_ns // len(transactions)
        return [duration + commit_share_ns for duration in durations]

    async def save_async(self, transaction) -> int:
        """Persist one transaction and its BOLA outcome atomically."""
        request = transaction.request
        response = transaction.response
        source_ip, destination_ip = _request_endpoint_ips(
            request.connection_id
        )

        observed_at = request.captured_at or utc_now()
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        observed_at = observed_at.astimezone(timezone.utc)

        async with self.session_factory() as session:
            try:
                endpoint = await session.run_sync(
                    lambda sync_session: self._upsert_endpoint(
                        sync_session,
                        transaction,
                        destination_ip,
                        observed_at,
                    )
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
                await session.flush()
                transaction_id = record.id

                outcome = await session.run_sync(
                    lambda sync_session: self.bola_detector.inspect(
                        transaction,
                        transaction_id,
                        sync_session,
                        source_ip,
                        endpoint_id=record.endpoint_id,
                    )
                )

                await session.commit()
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

                return int(transaction_id)
            except Exception:
                await session.rollback()
                logger.exception("Failed to persist HTTP transaction asynchronously")
                raise
