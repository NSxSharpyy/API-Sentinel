"""libbpf adapter for the API-Sentinel Day 17 blocklist map."""
from __future__ import annotations

import ctypes
import ctypes.util
import errno
import ipaddress
import os
import struct
import time

from app.blocklist_sync import BlockVerdict

MAP_PIN = "/sys/fs/bpf/api_sentinel_day17_blocklist"
MAP_NAME = "api_sntl_bl17"
MAP_TYPE_HASH = 1
MAP_KEY_SIZE = 4
MAP_VALUE_SIZE = 8
MAP_MAX_ENTRIES = 4096
MAX_TTL_NS = 30 * 24 * 60 * 60 * 1_000_000_000
UINT64_MAX = (1 << 64) - 1


class LibbpfBlocklistMapWriter:
    """Update a previously initialized and ABI-validated pinned hash map.

    This adapter does not create, pin, attach, or remove eBPF objects.
    The explicit C utility is responsible for map initialization.
    """

    def __init__(
        self,
        pin_path: str = MAP_PIN,
        *,
        library=None,
        close_fd=None,
    ) -> None:
        self.pin_path = pin_path
        self._close_fd = close_fd or os.close

        if library is None:
            library = self._load_libbpf()
            self._configure_functions(library)

        self._lib = library
        self._fd = -1

        encoded_path = os.fsencode(pin_path)
        fd = self._lib.bpf_obj_get(encoded_path)
        if fd < 0:
            code = -fd
            raise OSError(code, os.strerror(code), pin_path)

        self._fd = fd
        try:
            self._validate_map()
        except Exception:
            self.close()
            raise

    @staticmethod
    def _load_libbpf():
        library_name = ctypes.util.find_library("bpf")
        if not library_name:
            raise RuntimeError("libbpf could not be found")

        try:
            return ctypes.CDLL(library_name, use_errno=True)
        except OSError as exc:
            raise RuntimeError("Unable to load libbpf") from exc

    @staticmethod
    def _configure_functions(library) -> None:
        library.bpf_obj_get.argtypes = [ctypes.c_char_p]
        library.bpf_obj_get.restype = ctypes.c_int

        library.bpf_obj_get_info_by_fd.argtypes = [
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        library.bpf_obj_get_info_by_fd.restype = ctypes.c_int

        library.bpf_map_update_elem.argtypes = [
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint64,
        ]
        library.bpf_map_update_elem.restype = ctypes.c_int

        library.bpf_map_delete_elem.argtypes = [
            ctypes.c_int,
            ctypes.c_void_p,
        ]
        library.bpf_map_delete_elem.restype = ctypes.c_int

    def _validate_map(self) -> None:
        # bpf_map_info begins with six uint32 fields, followed by name[16].
        # We need only that documented prefix, not later kernel-specific fields.
        info = ctypes.create_string_buffer(256)
        info_len = ctypes.c_uint32(ctypes.sizeof(info))

        result = self._lib.bpf_obj_get_info_by_fd(
            self._fd, info, ctypes.byref(info_len)
        )
        if result < 0:
            self._raise_libbpf_error("Read blocklist map metadata", result)

        map_type, _map_id, key_size, value_size, capacity, _flags = (
            struct.unpack_from("=6I", info.raw, 0)
        )
        map_name = info.raw[24:40].split(b"\0", 1)[0].decode(
            "ascii", errors="replace"
        )

        expected = (
            MAP_TYPE_HASH,
            MAP_KEY_SIZE,
            MAP_VALUE_SIZE,
            MAP_MAX_ENTRIES,
            MAP_NAME,
        )
        actual = (map_type, key_size, value_size, capacity, map_name)

        if actual != expected:
            raise ValueError(
                "Incompatible blocklist map: "
                f"type={map_type}, key_size={key_size}, "
                f"value_size={value_size}, capacity={capacity}, "
                f"name={map_name!r}"
            )

    @staticmethod
    def _raise_libbpf_error(operation: str, result: int) -> None:
        code = -result
        raise OSError(code, f"{operation}: {os.strerror(code)}")

    def apply(self, verdict: BlockVerdict) -> None:
        """Apply a validated block or unblock verdict."""
        if self._fd < 0:
            raise RuntimeError("Blocklist map writer is closed")

        if not isinstance(verdict.source_ip, ipaddress.IPv4Address):
            raise ValueError("Only IPv4 block verdicts are supported")

        address = verdict.source_ip
        if (
            address.is_loopback
            or address.is_unspecified
            or address.is_multicast
            or address == ipaddress.IPv4Address("255.255.255.255")
        ):
            raise ValueError("IPv4 address is not eligible for blocking")

        if verdict.action not in ("block", "unblock"):
            raise ValueError("Unsupported blocklist action")

        # The map key must match the four bytes of IPv4 ip->saddr.
        key = ctypes.create_string_buffer(verdict.source_ip.packed, 4)

        if verdict.action == "unblock":
            result = self._lib.bpf_map_delete_elem(self._fd, key)
            if result == -errno.ENOENT:
                return  # Idempotent removal: absence is already the desired state.
            if result < 0:
                self._raise_libbpf_error("Delete blocklist entry", result)
            return

        expires_at_mono_ns = 0  # Zero means permanent.
        if verdict.expires_at_ns is not None:
            # Verdict timestamps are wall-clock nanoseconds. The kernel map
            # stores a CLOCK_MONOTONIC deadline instead.
            remaining_ns = verdict.expires_at_ns - time.time_ns()

            if remaining_ns <= 0:
                raise ValueError("Block verdict has expired")
            if remaining_ns > MAX_TTL_NS:
                raise ValueError("Block verdict TTL exceeds 30-day limit")

            expires_at_mono_ns = time.monotonic_ns() + remaining_ns
            if expires_at_mono_ns > UINT64_MAX:
                raise ValueError("Monotonic expiration exceeds uint64 range")

        value_bytes = struct.pack("=Q", expires_at_mono_ns)
        value = ctypes.create_string_buffer(value_bytes, len(value_bytes))

        result = self._lib.bpf_map_update_elem(
            self._fd, key, value, 0  # BPF_ANY
        )
        if result < 0:
            self._raise_libbpf_error("Update blocklist entry", result)

    def close(self) -> None:
        if self._fd >= 0:
            fd, self._fd = self._fd, -1
            self._close_fd(fd)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False
