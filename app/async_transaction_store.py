"""Async SQLAlchemy transaction persistence, retaining existing BOLA behavior."""
from __future__ import annotations

from collections import deque
import logging
import math
import time
from datetime import timezone

from app.database import AsyncSessionLocal, Base, async_engine
from app.models import TransactionLog, utc_now
from app.security_detection import redact_body, redact_headers
from app.transaction_store import (
    TransactionStore,
    _as_utc,
    _endpoint_identity,
    _request_endpoint_ips,
)

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

        # Separate pre-commit preparation from the final database commit.
        # Percentiles use the most recent bounded sample window.
        self.batch_preparation_duration_count = 0
        self.total_batch_preparation_duration_ns = 0
        self.max_batch_preparation_duration_ms = 0.0
        self._batch_preparation_duration_samples_ns: deque[int] = deque(
            maxlen=10_000
        )

        self.batch_commit_duration_count = 0
        self.total_batch_commit_duration_ns = 0
        self.max_batch_commit_duration_ms = 0.0
        self._batch_commit_duration_samples_ns: deque[int] = deque(
            maxlen=10_000
        )

    @staticmethod
    def _p95_duration_ms(samples: deque[int]) -> float:
        if not samples:
            return 0.0
        ordered = sorted(samples)
        index = max(0, math.ceil(0.95 * len(ordered)) - 1)
        return ordered[index] / 1_000_000

    def _record_batch_preparation_duration_ns(self, elapsed_ns: int) -> None:
        elapsed_ns = max(0, elapsed_ns)
        elapsed_ms = elapsed_ns / 1_000_000
        self.batch_preparation_duration_count += 1
        self.total_batch_preparation_duration_ns += elapsed_ns
        self.max_batch_preparation_duration_ms = max(
            self.max_batch_preparation_duration_ms, elapsed_ms
        )
        self._batch_preparation_duration_samples_ns.append(elapsed_ns)

    def _record_batch_commit_duration_ns(self, elapsed_ns: int) -> None:
        elapsed_ns = max(0, elapsed_ns)
        elapsed_ms = elapsed_ns / 1_000_000
        self.batch_commit_duration_count += 1
        self.total_batch_commit_duration_ns += elapsed_ns
        self.max_batch_commit_duration_ms = max(
            self.max_batch_commit_duration_ms, elapsed_ms
        )
        self._batch_commit_duration_samples_ns.append(elapsed_ns)

    @property
    def average_batch_preparation_duration_ms(self) -> float:
        if self.batch_preparation_duration_count == 0:
            return 0.0
        return (
            self.total_batch_preparation_duration_ns
            / self.batch_preparation_duration_count
            / 1_000_000
        )

    @property
    def p95_batch_preparation_duration_ms(self) -> float:
        return self._p95_duration_ms(
            self._batch_preparation_duration_samples_ns
        )

    @property
    def average_batch_commit_duration_ms(self) -> float:
        if self.batch_commit_duration_count == 0:
            return 0.0
        return (
            self.total_batch_commit_duration_ns
            / self.batch_commit_duration_count
            / 1_000_000
        )

    @property
    def p95_batch_commit_duration_ms(self) -> float:
        return self._p95_duration_ms(self._batch_commit_duration_samples_ns)

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
        endpoint_cache = {}
        async with self.session_factory() as session:
            try:
                preparation_started_ns = time.perf_counter_ns()
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

                    endpoint_identity = _endpoint_identity(
                        transaction, destination_ip
                    )
                    if endpoint_identity is None:
                        endpoint = None
                    else:
                        endpoint = endpoint_cache.get(endpoint_identity)
                        if endpoint is None:
                            endpoint = await session.run_sync(
                                lambda sync_session: self._upsert_endpoint(
                                    sync_session,
                                    transaction,
                                    destination_ip,
                                    observed_at,
                                )
                            )
                            if endpoint is not None:
                                endpoint_cache[endpoint_identity] = endpoint
                        else:
                            last_seen = _as_utc(endpoint.last_seen)
                            if _as_utc(observed_at) > last_seen:
                                endpoint.last_seen = observed_at

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

                preparation_ns = (
                    time.perf_counter_ns() - preparation_started_ns
                )
                self._record_batch_preparation_duration_ns(preparation_ns)

                commit_started_ns = time.perf_counter_ns()
                try:
                    await session.commit()
                finally:
                    commit_ns = time.perf_counter_ns() - commit_started_ns
                    self._record_batch_commit_duration_ns(commit_ns)
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
