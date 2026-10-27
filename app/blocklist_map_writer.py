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

        # Native batching is optional; older libbpf versions remain supported.
        if hasattr(library, "bpf_map_update_batch"):
            library.bpf_map_update_batch.argtypes = [
                ctypes.c_int,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_uint32),
                ctypes.c_void_p,
            ]
            library.bpf_map_update_batch.restype = ctypes.c_int

        if hasattr(library, "bpf_map_delete_batch"):
            library.bpf_map_delete_batch.argtypes = [
                ctypes.c_int,
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_uint32),
                ctypes.c_void_p,
            ]
            library.bpf_map_delete_batch.restype = ctypes.c_int

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

    def _prepare(
        self, verdict: BlockVerdict
    ) -> tuple[str, bytes, bytes | None]:
        """Validate and encode a verdict without modifying the map."""
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

        if verdict.action == "unblock":
            return "unblock", address.packed, None

        expires_at_mono_ns = 0
        if verdict.expires_at_ns is not None:
            remaining_ns = verdict.expires_at_ns - time.time_ns()

            if remaining_ns <= 0:
                raise ValueError("Block verdict has expired")
            if remaining_ns > MAX_TTL_NS:
                raise ValueError("Block verdict TTL exceeds 30-day limit")

            expires_at_mono_ns = time.monotonic_ns() + remaining_ns
            if expires_at_mono_ns > UINT64_MAX:
                raise ValueError("Monotonic expiration exceeds uint64 range")

        return "block", address.packed, struct.pack("=Q", expires_at_mono_ns)

    def apply(self, verdict: BlockVerdict) -> None:
        """Apply one validated block or unblock verdict."""
        action, key_bytes, value_bytes = self._prepare(verdict)
        key = ctypes.create_string_buffer(key_bytes, len(key_bytes))

        if action == "unblock":
            result = self._lib.bpf_map_delete_elem(self._fd, key)
            if result == -errno.ENOENT:
                return
            if result < 0:
                self._raise_libbpf_error("Delete blocklist entry", result)
            return

        assert value_bytes is not None
        value = ctypes.create_string_buffer(value_bytes, len(value_bytes))
        result = self._lib.bpf_map_update_elem(self._fd, key, value, 0)
        if result < 0:
            self._raise_libbpf_error("Update blocklist entry", result)

    def apply_many(
        self, verdicts: list[BlockVerdict]
    ) -> list[Exception | None]:
        """Apply ordered verdicts using native batches when safely available.

        Results correspond to input order. None means success; an exception
        records a failed verdict. Batch failures fall back to individual writes.
        """
        results: list[Exception | None] = [None] * len(verdicts)
        prepared: list[
            tuple[str, bytes, bytes | None] | None
        ] = [None] * len(verdicts)

        for index, verdict in enumerate(verdicts):
            try:
                prepared[index] = self._prepare(verdict)
            except Exception as exc:
                results[index] = exc

        index = 0
        max_batch_size = 64

        while index < len(verdicts):
            operation = prepared[index]
            if operation is None:
                index += 1
                continue

            action = operation[0]
            group: list[int] = []
            keys_in_group: set[bytes] = set()
            cursor = index

            # Preserve order and never combine repeated keys in one batch.
            while cursor < len(verdicts) and len(group) < max_batch_size:
                candidate = prepared[cursor]
                if candidate is None or candidate[0] != action:
                    break

                key_bytes = candidate[1]
                if key_bytes in keys_in_group:
                    break

                keys_in_group.add(key_bytes)
                group.append(cursor)
                cursor += 1

            batch_fn = getattr(
                self._lib,
                "bpf_map_update_batch"
                if action == "block"
                else "bpf_map_delete_batch",
                None,
            )
            succeeded = False

            if len(group) >= 2 and batch_fn is not None:
                keys_data = b"".join(prepared[i][1] for i in group)
                keys_buffer = ctypes.create_string_buffer(
                    keys_data, len(keys_data)
                )
                count = ctypes.c_uint32(len(group))

                try:
                    if action == "block":
                        values_data = b"".join(
                            prepared[i][2] for i in group
                        )
                        values_buffer = ctypes.create_string_buffer(
                            values_data, len(values_data)
                        )
                        rc = batch_fn(
                            self._fd,
                            keys_buffer,
                            values_buffer,
                            ctypes.byref(count),
                            None,
                        )
                    else:
                        rc = batch_fn(
                            self._fd,
                            keys_buffer,
                            ctypes.byref(count),
                            None,
                        )

                    succeeded = rc == 0 and count.value == len(group)
                except Exception:
                    succeeded = False

            if not succeeded:
                # A failed batch may have partially succeeded. Individual
                # retries reconcile each entry and capture per-verdict errors.
                for item_index in group:
                    try:
                        self.apply(verdicts[item_index])
                    except Exception as exc:
                        results[item_index] = exc

            index += len(group)

        return results

    def close(self) -> None:
        if self._fd >= 0:
            fd, self._fd = self._fd, -1
            self._close_fd(fd)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False
