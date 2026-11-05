import pytest

from app.tcp_reassembly import TCPStreamReassembler


def new_stream(initial_sequence=100, max_buffered_bytes=1_048_576):
    """Create a stream with a known initial expected sequence number."""
    stream = TCPStreamReassembler(
        max_buffered_bytes=max_buffered_bytes,
    )
    stream.reset(initial_sequence=initial_sequence)
    return stream


def test_in_order_segments():
    stream = new_stream()

    assert stream.feed(100, b"Hello ") == b"Hello "
    assert stream.feed(106, b"World") == b"World"


def test_out_of_order_segments_are_buffered():
    stream = new_stream()

    assert stream.feed(106, b"World") == b""
    assert stream.buffered_bytes == 5

    assert stream.feed(100, b"Hello ") == b"Hello World"
    assert stream.buffered_bytes == 0


def test_duplicate_retransmission_is_ignored():
    stream = new_stream()

    assert stream.feed(100, b"Hello") == b"Hello"
    assert stream.feed(100, b"Hello") == b""
    assert stream.feed(105, b" World") == b" World"


def test_partial_retransmission_discards_delivered_prefix():
    stream = new_stream()

    assert stream.feed(100, b"Hello") == b"Hello"
    assert stream.feed(103, b"lo World") == b" World"


def test_empty_payload_is_ignored():
    stream = TCPStreamReassembler()

    assert stream.feed(100, b"") == b""
    assert stream.next_sequence is None


def test_negative_sequence_number_is_rejected():
    stream = new_stream()

    with pytest.raises(ValueError):
        stream.feed(-1, b"data")


def test_buffer_limit_is_enforced():
    stream = new_stream(max_buffered_bytes=4)

    assert stream.feed(100, b"A") == b"A"

    with pytest.raises(BufferError):
        stream.feed(110, b"12345")


def test_reset_clears_state():
    stream = new_stream()

    stream.feed(100, b"A")
    stream.feed(105, b"BC")

    stream.reset()

    assert stream.next_sequence is None
    assert stream.pending == {}
    assert stream.buffered_bytes == 0


def test_feed_requires_initial_sequence():
    stream = TCPStreamReassembler()

    with pytest.raises(ValueError, match="Initial expected sequence"):
        stream.feed(100, b"data")


def test_overlapping_out_of_order_segments_do_not_duplicate_bytes():
    stream = new_stream(initial_sequence=100)

    assert stream.feed(106, b"GHI") == b""
    assert stream.feed(108, b"IJK") == b""
    assert stream.feed(100, b"ABCDEF") == b"ABCDEFGHIJK"


def test_overlapping_segments_with_different_start_positions():
    stream = new_stream(initial_sequence=100)

    assert stream.feed(108, b"IJKL") == b""
    assert stream.feed(106, b"GHIJ") == b""
    assert stream.feed(100, b"ABCDEF") == b"ABCDEFGHIJKL"


def test_out_of_order_segments_preserve_capture_timestamps():
    from datetime import datetime, timezone

    stream = new_stream(initial_sequence=100)
    earlier = datetime(2026, 10, 24, 10, 0, tzinfo=timezone.utc)
    later = datetime(2026, 10, 24, 10, 1, tzinfo=timezone.utc)

    # The later bytes arrive first and must wait for the sequence gap.
    assert stream.feed_with_timestamps(106, b"World", later) == []

    # Filling the gap releases both segments with their own timestamps.
    chunks = stream.feed_with_timestamps(100, b"Hello ", earlier)

    assert chunks == [
        (b"Hello ", earlier),
        (b"World", later),
    ]


def test_pending_segment_count_limit_is_enforced():
    stream = TCPStreamReassembler(max_pending_segments=2)
    stream.reset(initial_sequence=100)

    assert stream.feed(110, b"A") == b""
    assert stream.feed(120, b"B") == b""
    assert len(stream.pending) == 2

    with pytest.raises(BufferError, match="pending segment count limit"):
        stream.feed(130, b"C")

    assert len(stream.pending) == 2
    assert stream.buffered_bytes == 2


def test_pending_segment_count_limit_allows_drain_and_reuse():
    stream = TCPStreamReassembler(max_pending_segments=1)
    stream.reset(initial_sequence=100)

    assert stream.feed(105, b"world") == b""
    assert len(stream.pending) == 1

    # Filling the gap drains the pending segment and frees its slot.
    assert stream.feed(100, b"hello") == b"helloworld"
    assert len(stream.pending) == 0
    assert stream.buffered_bytes == 0

    # A new out-of-order segment can now be buffered.
    assert stream.feed(115, b"!") == b""
    assert len(stream.pending) == 1


def test_pending_segment_limit_must_be_positive():
    with pytest.raises(ValueError, match="max_pending_segments"):
        TCPStreamReassembler(max_pending_segments=0)


def test_reset_clears_pending_segment_count():
    stream = TCPStreamReassembler(max_pending_segments=1)
    stream.reset(initial_sequence=100)

    stream.feed(110, b"A")
    assert len(stream.pending) == 1

    stream.reset(initial_sequence=200)

    assert len(stream.pending) == 0
    assert stream.pending_timestamps == {}
    assert stream.buffered_bytes == 0

    assert stream.feed(210, b"B") == b""
