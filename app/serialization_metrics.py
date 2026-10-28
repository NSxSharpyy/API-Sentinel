"""Bounded latency statistics for serialization operations."""
import math
from collections import deque


class SerializationLatencyMetrics:
    """Track serialization duration with bounded recent samples."""

    def __init__(self, sample_capacity: int = 10_000) -> None:
        if sample_capacity <= 0:
            raise ValueError("sample_capacity must be positive")
        self.count = 0
        self.total_duration_ns = 0
        self.last_duration_ns = 0
        self.max_duration_ns = 0
        self._samples_ns: deque[int] = deque(maxlen=sample_capacity)

    def record(self, elapsed_ns: int) -> None:
        elapsed_ns = max(0, elapsed_ns)
        self.count += 1
        self.total_duration_ns += elapsed_ns
        self.last_duration_ns = elapsed_ns
        self.max_duration_ns = max(self.max_duration_ns, elapsed_ns)
        self._samples_ns.append(elapsed_ns)

    def snapshot(self) -> dict[str, int | float]:
        samples = sorted(self._samples_ns)
        sample_count = len(samples)

        def percentile(fraction: float) -> float:
            if not samples:
                return 0.0
            index = max(0, math.ceil(fraction * len(samples)) - 1)
            return samples[index] / 1_000

        under_1ms = sum(value < 1_000_000 for value in samples)

        return {
            "count": self.count,
            "sample_count": sample_count,
            "last_latency_us": self.last_duration_ns / 1_000,
            "average_latency_us": (
                self.total_duration_ns / self.count / 1_000
                if self.count else 0.0
            ),
            "max_latency_us": self.max_duration_ns / 1_000,
            "p50_latency_us": percentile(0.50),
            "p95_latency_us": percentile(0.95),
            "p99_latency_us": percentile(0.99),
            "under_1ms_sample_count": under_1ms,
            "under_1ms_sample_percent": (
                under_1ms / sample_count * 100
                if sample_count else 0.0
            ),
        }


http_message_serialization_metrics = SerializationLatencyMetrics()
http_transaction_serialization_metrics = SerializationLatencyMetrics()
