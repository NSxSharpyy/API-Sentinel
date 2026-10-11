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
