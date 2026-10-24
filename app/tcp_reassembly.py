from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TCPStreamReassembler:
    """
    Reassemble TCP payloads relative to a known initial sequence number.

    The caller must provide the first expected payload sequence number.
    Segments arriving ahead of that position are buffered until gaps fill.
    """

    max_buffered_bytes: int = 1_048_576
    next_sequence: int | None = None
    pending: dict[int, bytes] = field(default_factory=dict)
    pending_timestamps: dict[int, datetime | None] = field(
        default_factory=dict
    )
    buffered_bytes: int = 0

    def __post_init__(self) -> None:
        if self.max_buffered_bytes <= 0:
            raise ValueError("max_buffered_bytes must be positive")

    def reset(self, initial_sequence: int | None = None) -> None:
        """Reset the stream, optionally setting its initial sequence."""
        if initial_sequence is not None and initial_sequence < 0:
            raise ValueError("initial_sequence must be non-negative")

        self.next_sequence = initial_sequence
        self.pending.clear()
        self.pending_timestamps.clear()
        self.buffered_bytes = 0

    def feed(self, sequence_number: int, payload: bytes) -> bytes:
        """Return newly contiguous payload bytes."""
        chunks = self.feed_with_timestamps(sequence_number, payload, None)
        return b"".join(data for data, _ in chunks)

    def feed_with_timestamps(
        self,
        sequence_number: int,
        payload: bytes,
        captured_at: datetime | None,
    ) -> list[tuple[bytes, datetime | None]]:
        """Return contiguous payload chunks with their capture timestamps."""
        if sequence_number < 0:
            raise ValueError("sequence_number must be non-negative")

        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")

        if not payload:
            return []

        if self.next_sequence is None:
            raise ValueError(
                "Initial expected sequence number must be set before feed()"
            )

        if sequence_number + len(payload) <= self.next_sequence:
            return []

        if sequence_number < self.next_sequence:
            trim = self.next_sequence - sequence_number
            payload = payload[trim:]
            sequence_number = self.next_sequence

        if sequence_number == self.next_sequence:
            output = [(payload, captured_at)]
            self.next_sequence += len(payload)
            self._drain_pending_with_timestamps(output)
            return output

        existing = self.pending.get(sequence_number)
        if existing is not None:
            return []

        if self.buffered_bytes + len(payload) > self.max_buffered_bytes:
            raise BufferError("TCP out-of-order buffer limit exceeded")

        self.pending[sequence_number] = payload
        self.pending_timestamps[sequence_number] = captured_at
        self.buffered_bytes += len(payload)
        return []

    def _drain_pending_with_timestamps(
        self,
        output: list[tuple[bytes, datetime | None]],
    ) -> None:
        """Release buffered segments with their original timestamps."""
        while self.next_sequence is not None and self.pending:
            candidate_sequence = None

            for start, payload in sorted(self.pending.items()):
                if start <= self.next_sequence < start + len(payload):
                    candidate_sequence = start
                    break
                if start > self.next_sequence:
                    break

            if candidate_sequence is None:
                return

            payload = self.pending.pop(candidate_sequence)
            captured_at = self.pending_timestamps.pop(candidate_sequence, None)
            self.buffered_bytes -= len(payload)

            trim = self.next_sequence - candidate_sequence
            contiguous = payload[trim:]

            if contiguous:
                output.append((contiguous, captured_at))
                self.next_sequence += len(contiguous)
