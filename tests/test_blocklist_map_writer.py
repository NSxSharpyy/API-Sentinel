import ctypes
import errno
import ipaddress
import struct
import time

import pytest

from app.blocklist_map_writer import (
    MAP_MAX_ENTRIES,
    MAP_NAME,
    MAP_TYPE_HASH,
    MAP_VALUE_SIZE,
    LibbpfBlocklistMapWriter,
)
from app.blocklist_sync import BlockVerdict


class FakeLibbpf:
    def __init__(self, *, map_type=MAP_TYPE_HASH, map_name=MAP_NAME):
        self.map_type = map_type
        self.map_name = map_name
        self.entries = {}
        self.update_result = 0
        self.delete_result = 0
        self.closed = []
        self.opened_path = None

    def bpf_obj_get(self, path):
        self.opened_path = path
        return 73

    def bpf_obj_get_info_by_fd(self, fd, info, info_len):
        assert fd == 73
        name = self.map_name.encode("ascii")[:15]
        name = name + b"\0" * (16 - len(name))
        raw = struct.pack(
            "=6I",
            self.map_type,
            123,
            4,
            MAP_VALUE_SIZE,
            MAP_MAX_ENTRIES,
            0,
        ) + name
        ctypes.memmove(ctypes.addressof(info), raw, len(raw))
        info_len._obj.value = len(raw)
        return 0

    def bpf_map_update_elem(self, fd, key, value, flags):
        assert fd == 73
        assert flags == 0
        if self.update_result < 0:
            return self.update_result
        self.entries[ctypes.string_at(key, 4)] = struct.unpack(
            "=Q", ctypes.string_at(value, 8)
        )[0]
        return 0

    def bpf_map_delete_elem(self, fd, key):
        assert fd == 73
        if self.delete_result < 0:
            return self.delete_result
        self.entries.pop(ctypes.string_at(key, 4), None)
        return 0


def make_verdict(
    *, action="block", expires_at_ns=None, source_ip="198.51.100.25"
):
    now = time.time_ns()
    return BlockVerdict(
        verdict_id="verdict-1",
        action=action,
        source_ip=ipaddress.IPv4Address(source_ip),
        rule_id="rule-1",
        issued_at_ns=now,
        expires_at_ns=expires_at_ns,
    )


def build_writer(fake):
    return LibbpfBlocklistMapWriter(
        library=fake,
        close_fd=fake.closed.append,
    )


def test_writer_validates_map_and_updates_permanent_entry():
    fake = FakeLibbpf()
    writer = build_writer(fake)

    try:
        writer.apply(make_verdict())

        key = ipaddress.IPv4Address("198.51.100.25").packed
        assert fake.entries[key] == 0
    finally:
        writer.close()

    assert fake.closed == [73]


def test_writer_converts_wall_expiration_to_monotonic_deadline():
    fake = FakeLibbpf()
    writer = build_writer(fake)

    try:
        now_wall = time.time_ns()
        writer.apply(make_verdict(expires_at_ns=now_wall + 5_000_000_000))
        now_mono = time.monotonic_ns()
        key = ipaddress.IPv4Address("198.51.100.25").packed

        expiration = fake.entries[key]
        assert expiration > now_mono
        assert expiration <= now_mono + 5_000_000_000
    finally:
        writer.close()


def test_writer_removes_entry():
    fake = FakeLibbpf()
    writer = build_writer(fake)
    key = ipaddress.IPv4Address("198.51.100.25").packed

    try:
        fake.entries[key] = 0
        writer.apply(make_verdict(action="unblock"))
        assert key not in fake.entries
    finally:
        writer.close()


def test_writer_rejects_wrong_map_abi():
    fake = FakeLibbpf(map_type=2)

    with pytest.raises(ValueError, match="Incompatible blocklist map"):
        build_writer(fake)

    assert fake.closed == [73]


def test_writer_reports_kernel_update_errors():
    fake = FakeLibbpf()
    fake.update_result = -errno.ENOSPC
    writer = build_writer(fake)

    try:
        with pytest.raises(OSError) as exc:
            writer.apply(make_verdict())
        assert exc.value.errno == errno.ENOSPC
    finally:
        writer.close()


def test_writer_rejects_expired_verdict():
    fake = FakeLibbpf()
    writer = build_writer(fake)

    try:
        with pytest.raises(ValueError, match="expired"):
            writer.apply(make_verdict(expires_at_ns=time.time_ns() - 1))
    finally:
        writer.close()


def test_writer_treats_missing_entry_unblock_as_success():
    fake = FakeLibbpf()
    fake.delete_result = -errno.ENOENT
    writer = build_writer(fake)

    try:
        writer.apply(make_verdict(action="unblock"))
    finally:
        writer.close()


@pytest.mark.parametrize(
    "source_ip",
    ["127.0.0.1", "0.0.0.0", "224.0.0.1", "255.255.255.255"],
)
def test_writer_rejects_ineligible_address_even_for_direct_verdict(source_ip):
    fake = FakeLibbpf()
    writer = build_writer(fake)

    try:
        with pytest.raises(ValueError, match="not eligible"):
            writer.apply(make_verdict(source_ip=source_ip))
        assert fake.entries == {}
    finally:
        writer.close()
