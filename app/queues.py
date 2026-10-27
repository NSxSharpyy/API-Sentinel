
import asyncio
import math
import os
from collections import deque

from app.schemas import HeaderData, PacketMetadata, RawPacketChunk

class QueueWaitMetrics:
    """Track enqueue-to-dequeue latency with bounded recent samples."""

    def __init__(self, sample_capacity: int = 10_000) -> None:
        if sample_capacity <= 0:
            raise ValueError("sample_capacity must be positive")
        self.queue_wait_count = 0
        self.total_queue_wait_ns = 0
        self.last_queue_wait_ms = 0.0
        self.max_queue_wait_ms = 0.0
        self._samples_ns: deque[int] = deque(maxlen=sample_capacity)

    def record(self, elapsed_ns: int) -> None:
        """Record one wait duration in nanoseconds."""
        elapsed_ns = max(0, elapsed_ns)
        elapsed_ms = elapsed_ns / 1_000_000
        self.queue_wait_count += 1
        self.total_queue_wait_ns += elapsed_ns
        self.last_queue_wait_ms = elapsed_ms
        self.max_queue_wait_ms = max(self.max_queue_wait_ms, elapsed_ms)
        self._samples_ns.append(elapsed_ns)

    def snapshot(self) -> dict[str, int | float]:
        """Return lifetime counters and recent-window p95 latency."""
        sample_count = len(self._samples_ns)
        p95_ms = 0.0
        if sample_count:
            ordered = sorted(self._samples_ns)
            index = max(0, math.ceil(0.95 * sample_count) - 1)
            p95_ms = ordered[index] / 1_000_000

        average_ms = (
            self.total_queue_wait_ns / self.queue_wait_count / 1_000_000
            if self.queue_wait_count else 0.0
        )
        return {
            "queue_wait_count": self.queue_wait_count,
            "queue_wait_sample_count": sample_count,
            "last_queue_wait_ms": self.last_queue_wait_ms,
            "average_queue_wait_ms": average_ms,
            "max_queue_wait_ms": self.max_queue_wait_ms,
            "p95_queue_wait_ms": p95_ms,
        }


def _positive_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


QUEUE_MAX_SIZE = _positive_int_env("API_SENTINEL_QUEUE_MAX_SIZE", 10000)
BLOCK_VERDICT_QUEUE_MAX_SIZE = _positive_int_env(
    "API_SENTINEL_BLOCK_VERDICT_QUEUE_MAX_SIZE", 1024
)

# Explicit block/unblock verdicts only. Detection incidents do not enter this
# queue automatically; a policy component must submit validated verdict data.
blocklist_verdict_queue: asyncio.Queue[object] = asyncio.Queue(
    maxsize=BLOCK_VERDICT_QUEUE_MAX_SIZE
)

raw_packet_queue: asyncio.Queue[RawPacketChunk] = asyncio.Queue(
    maxsize=QUEUE_MAX_SIZE
)
header_queue: asyncio.Queue[HeaderData] = asyncio.Queue(
    maxsize=QUEUE_MAX_SIZE
)
metadata_queue: asyncio.Queue[PacketMetadata] = asyncio.Queue(
    maxsize=QUEUE_MAX_SIZE
)

raw_packet_queue_wait_metrics = QueueWaitMetrics()

# Highest raw packet queue depth observed after a successful consumer enqueue.
raw_packet_queue_max_depth = 0


def record_raw_packet_queue_depth() -> None:
    """Record the highest observed raw packet queue depth."""
    global raw_packet_queue_max_depth
    raw_packet_queue_max_depth = max(
        raw_packet_queue_max_depth,
        raw_packet_queue.qsize(),
    )

# Packet-event counters
dropped_packet_count = 0
accepted_packet_count = 0
rejected_packet_count = 0
accepted_tcp_event_count = 0
accepted_udp_event_count = 0

# TCP stream rejection and reassembly counters
tcp_stream_limit_rejection_count = 0
tcp_reassembly_buffer_overflow_count = 0

# TCP packet-processing diagnostic counters
tcp_packets_processed_count = 0
tcp_syn_packets_count = 0
tcp_payload_packets_count = 0
tcp_payload_bytes_count = 0
tcp_packets_without_stream_count = 0

# TCP payload delivery to the HTTP pipeline
tcp_payload_delivered_to_http_count = 0
tcp_payload_bytes_delivered_to_http_count = 0
