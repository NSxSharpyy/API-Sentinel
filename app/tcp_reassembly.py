from dataclasses import dataclass, field


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
        self.buffered_bytes = 0

    def feed(self, sequence_number: int, payload: bytes) -> bytes:
        """Return newly contiguous payload bytes."""
        if sequence_number < 0:
            raise ValueError("sequence_number must be non-negative")

        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")

        if not payload:
            return b""

        # Without an initial sequence, we cannot know whether the first
        # observed segment has an earlier missing predecessor.
        if self.next_sequence is None:
            raise ValueError(
                "Initial expected sequence number must be set before feed()"
            )

        if sequence_number + len(payload) <= self.next_sequence:
            return b""

        if sequence_number < self.next_sequence:
            trim = self.next_sequence - sequence_number
            payload = payload[trim:]
            sequence_number = self.next_sequence

        if sequence_number == self.next_sequence:
            output = bytearray(payload)
            self.next_sequence += len(payload)
            self._drain_pending(output)
            return bytes(output)

        existing = self.pending.get(sequence_number)

        if existing is not None:
            if existing == payload:
                return b""
            return b""

        if self.buffered_bytes + len(payload) > self.max_buffered_bytes:
            raise BufferError("TCP out-of-order buffer limit exceeded")

        self.pending[sequence_number] = payload
        self.buffered_bytes += len(payload)
        return b""

    def _drain_pending(self, output: bytearray) -> None:
        """Append buffered segments that have become contiguous."""
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
            self.buffered_bytes -= len(payload)

            trim = self.next_sequence - candidate_sequence
            contiguous = payload[trim:]

            if contiguous:
                output.extend(contiguous)
                self.next_sequence += len(contiguous)
