#!/usr/bin/env python3
"""Isolated Day 23 concurrent TCP SYN drop verification on loopback."""

import concurrent.futures
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "appsec-testing/scripts/enforcement/day23_concurrent_syn_drop.c"
REPORT = ROOT / "appsec-testing/logs/day23_kernel_blocking_at_scale_report.json"

INTERFACE = "lo"
TEST_PORT = 5084
FILTER_PREF = 49153
PIN_DIR = Path("/sys/fs/bpf/day23_concurrent_syn_drop")
CONCURRENCY = 50
ATTEMPTS = 100
SOCKET_TIMEOUT = 0.7
SOURCE_PORT_START = 40000
SOURCE_PORTS = tuple(
    range(SOURCE_PORT_START, SOURCE_PORT_START + ATTEMPTS)
)

def command(args, timeout=10):
    try:
        result = subprocess.run(
            [str(x) for x in args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "returncode": 124,
            "stdout": "",
            "stderr": f"{type(exc).__name__}: {exc}",
        }


def require_ok(result, label):
    if result["returncode"] != 0:
        raise RuntimeError(
            f"{label} failed: {result['stderr'] or result['stdout']}"
        )


def read_tc_state():
    qdisc = command(["tc", "qdisc", "show", "dev", INTERFACE])
    ingress = command(["tc", "filter", "show", "dev", INTERFACE, "ingress"])
    egress = command(["tc", "filter", "show", "dev", INTERFACE, "egress"])
    require_ok(qdisc, "Inspect loopback qdisc")
    require_ok(ingress, "Inspect loopback ingress filters")
    require_ok(egress, "Inspect loopback egress filters")
    return qdisc["stdout"], ingress["stdout"], egress["stdout"]

def read_tc_filter_details():
    """Read structured ingress filter details; fail if state is unknown."""
    result = command([
        "tc", "-j", "-details", "filter", "show",
        "dev", INTERFACE, "ingress",
    ])
    require_ok(result, "Inspect detailed TC ingress filters")

    filters = json.loads(result["stdout"])
    if not isinstance(filters, list):
        raise RuntimeError("Unexpected TC filter JSON structure")
    return filters


def pinned_program_id():
    """Return the ID of our pinned BPF program."""
    result = command([
        "bpftool", "-j", "prog", "show",
        "pinned", PIN_DIR / "program",
    ])
    require_ok(result, "Inspect pinned Day 23 BPF program")

    data = json.loads(result["stdout"])
    if isinstance(data, list):
        if len(data) != 1:
            raise RuntimeError("Expected exactly one pinned BPF program")
        data = data[0]

    if not isinstance(data, dict) or isinstance(data.get("id"), bool):
        raise RuntimeError("Could not establish pinned BPF program identity")

    program_id = data.get("id")
    if not isinstance(program_id, int) or program_id <= 0:
        raise RuntimeError("Invalid pinned BPF program ID")

    return program_id


def day23_filter_state(filters, program_id):
    """Return 'owned', 'absent', or 'ambiguous' for our TC preference."""
    matches = []

    def visit(value):
        if isinstance(value, dict):
            pref = value.get("pref")

            try:
                pref = int(pref)
            except (TypeError, ValueError):
                pref = None

            if pref == FILTER_PREF:
                matches.append(value)

            for child in value.values():
                visit(child)

        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(filters)

    if not matches:
        return "absent"

    # Every entry at our preference must identify a BPF filter.
    if any(item.get("kind") != "bpf" for item in matches):
        return "ambiguous"

    # tc can return both a summary and a detailed entry.
    detailed = [
        item for item in matches
        if isinstance(item.get("options"), dict)
    ]

    if len(detailed) != 1:
        return "ambiguous"

    item = detailed[0]
    options = item["options"]
    prog = options.get("prog")

    observed_id = options.get("id")

    if observed_id is None and isinstance(prog, dict):
        observed_id = prog.get("id")

    if (
        observed_id == program_id
        and options.get("direct-action") is True
    ):
        return "owned"

    return "ambiguous"

def port_is_free():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", TEST_PORT))
            return True
        except OSError:
            return False

def source_ports_are_free():
    sockets = []

    try:
        for source_port in SOURCE_PORTS:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", source_port))
            sockets.append(sock)
        return True
    except OSError:
        return False
    finally:
        for sock in sockets:
            sock.close()

def attempt_connection(index, source_port, start_event):
    result = {
        "id": index,
        "source_port": source_port,
        "outcome": "not_started",
        "elapsed_ms": None,
        "error": None,
    }

    start_event.wait()
    started = time.monotonic()

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(SOCKET_TIMEOUT)

            # Give every connection attempt a unique source port.
            sock.bind(("127.0.0.1", source_port))
            sock.connect(("127.0.0.1", TEST_PORT))

        result["outcome"] = "connected"

    except socket.timeout:
        result["outcome"] = "timeout"

    except ConnectionRefusedError:
        result["outcome"] = "connection_refused"

    except OSError as exc:
        result["outcome"] = "socket_error"
        result["error"] = f"{type(exc).__name__}: {exc}"

    result["elapsed_ms"] = round(
        (time.monotonic() - started) * 1000, 3
    )
    return result

def dump_counters():
    map_path = PIN_DIR / "day23_stats_map"
    result = command([
        "bpftool", "-j", "-p", "map", "dump", "pinned", map_path
    ])
    require_ok(result, "Read pinned BPF statistics map")

    entries = json.loads(result["stdout"])
    if not isinstance(entries, list) or len(entries) != 1:
        raise RuntimeError("Expected exactly one BPF array-map entry")

    entry = entries[0]
    if not isinstance(entry, dict):
        raise RuntimeError("Unexpected BPF map entry format")

    names = ("seen", "matched", "dropped")
    formatted = entry.get("formatted")
    if isinstance(formatted, dict):
        formatted_value = formatted.get("value")
        if isinstance(formatted_value, dict) and all(
            name in formatted_value for name in names
        ):
            values = {}
            for name in names:
                value = formatted_value[name]
                if isinstance(value, bool):
                    raise RuntimeError(f"Invalid Boolean counter: {name}")
                try:
                    values[name] = int(value)
                except (TypeError, ValueError) as exc:
                    raise RuntimeError(
                        f"Invalid formatted counter: {name}"
                    ) from exc
                if values[name] < 0:
                    raise RuntimeError(f"Negative counter: {name}")
            return values

    raw_value = entry.get("value")
    if not isinstance(raw_value, list) or len(raw_value) != 24:
        raise RuntimeError("Expected exactly 24 raw BPF counter bytes")

    try:
        raw = bytes(
            int(item, 16) if isinstance(item, str) else int(item)
            for item in raw_value
        )
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Invalid raw BPF map bytes") from exc

    seen, matched, dropped = struct.unpack("<QQQ", raw)
    return {"seen": seen, "matched": matched, "dropped": dropped}

def decode_map_bytes(value, expected_length, label):
    if not isinstance(value, list) or len(value) != expected_length:
        raise RuntimeError(f"Invalid {label} byte array")

    decoded = []

    for item in value:
        if isinstance(item, bool):
            raise RuntimeError(f"Boolean byte in {label}")

        if isinstance(item, str):
            try:
                number = (
                    int(item, 16)
                    if item.lower().startswith("0x")
                    else int(item, 10)
                )
            except ValueError as exc:
                raise RuntimeError(
                    f"Invalid byte in {label}: {item}"
                ) from exc
        elif isinstance(item, int):
            number = item
        else:
            raise RuntimeError(f"Unsupported byte format in {label}")

        if not 0 <= number <= 255:
            raise RuntimeError(f"Out-of-range byte in {label}")

        decoded.append(number)

    return bytes(decoded)


def dump_source_port_hits():
    map_path = PIN_DIR / "source_port_hits"

    result = command([
        "bpftool", "-j", "-p", "map", "dump", "pinned", map_path
    ])

    require_ok(result, "Read pinned BPF source-port map")

    entries = json.loads(result["stdout"])

    if not isinstance(entries, list):
        raise RuntimeError("Unexpected source-port map format")

    hits_by_port = {}

    for entry in entries:
        if not isinstance(entry, dict):
            raise RuntimeError("Invalid source-port map entry")

        key_raw = decode_map_bytes(
            entry.get("key"), 4, "source-port key"
        )
        value_raw = decode_map_bytes(
            entry.get("value"), 8, "source-port hit count"
        )

        source_port = struct.unpack("<I", key_raw)[0]
        hit_count = struct.unpack("<Q", value_raw)[0]

        if not 1 <= source_port <= 65535:
            raise RuntimeError(
                f"Invalid source port in BPF map: {source_port}"
            )

        if hit_count <= 0:
            raise RuntimeError(
                f"Invalid hit count for source port {source_port}"
            )

        if source_port in hits_by_port:
            raise RuntimeError(
                f"Duplicate source port in BPF map: {source_port}"
            )

        hits_by_port[source_port] = hit_count

    return hits_by_port

def main():
    report = {
        "schema_version": 1,
        "evidence_type": "kernel_drop",
        "kernel_drop_proof": False,
        "concurrency_evidence": False,
        "interface": INTERFACE,
        "destination_port": TEST_PORT,
        "requested_attempts": ATTEMPTS,
        "concurrency": CONCURRENCY,
        "socket_timeout_seconds": SOCKET_TIMEOUT,
        "workload": {"attempts_completed": 0, "outcomes": {}, "results": []},
        "kernel_counters": None,
        "source_port_evidence": None,
        "steps": {},
        "cleanup": {
            "filter_delete": {"status": "not_needed"},
            "qdisc_delete": {"status": "not_needed"},
            "pin_cleanup": {"status": "not_needed"},
            "complete": False,
        },
        "checks": {},
        "overall": "FAIL",
    }

    if os.geteuid() != 0:
        raise RuntimeError("Run this script with sudo; it will not self-escalate")
    if not all(shutil.which(tool) for tool in ("clang", "tc", "bpftool")):
        raise RuntimeError("Required tools clang, tc, and bpftool must be installed")
    if not SOURCE.is_file():
        raise RuntimeError(f"Missing BPF source: {SOURCE}")
    if PIN_DIR.exists():
        raise RuntimeError(f"Refusing to overwrite existing pin directory: {PIN_DIR}")
    if not port_is_free():
        raise RuntimeError(f"Port {TEST_PORT} is already in use")
    if not source_ports_are_free():
        raise RuntimeError(
            f"One or more source ports in "
            f"{SOURCE_PORT_START}-{SOURCE_PORT_START + ATTEMPTS - 1} "
            "are already in use"
        )

    qdisc_before, ingress_before, egress_before = read_tc_state()
    if "clsact" in qdisc_before or ingress_before or egress_before:
        raise RuntimeError(
            "Loopback qdisc/filter state is not empty; refusing to alter it"
        )

    temp_object = None
    created_pin_dir = False
    created_qdisc = False
    qdisc_add_attempted = False
    attached_filter = False
    filter_state = "absent"
    program_id = None
    run_error = None
    source_port_hits = {}

    try:
        with tempfile.NamedTemporaryFile(suffix=".o", delete=False) as obj:
            temp_object = Path(obj.name)

        result = command([
            "clang", "-O2", "-g", "-target", "bpf",
            "-I/usr/include/x86_64-linux-gnu",
            "-c", SOURCE, "-o", temp_object,
        ], timeout=30)
        report["steps"]["compile"] = result
        require_ok(result, "Compile Day 23 BPF classifier")

        PIN_DIR.mkdir(mode=0o700)
        created_pin_dir = True

        result = command([
            "bpftool", "prog", "load", temp_object,
            PIN_DIR / "program", "type", "classifier",
            "pinmaps", PIN_DIR,
        ], timeout=20)
        report["steps"]["load"] = result
        require_ok(result, "Load and pin Day 23 BPF classifier")
        program_id = pinned_program_id()
        report["steps"]["pinned_program_id"] = program_id
        qdisc_add_attempted = True
        result = command(["tc", "qdisc", "add", "dev", INTERFACE, "clsact"])
        report["steps"]["add_qdisc"] = result
        require_ok(result, "Add loopback clsact qdisc")
        created_qdisc = True

        result = command([
            "tc", "filter", "add", "dev", INTERFACE, "ingress",
            "pref", FILTER_PREF, "bpf", "da", "pinned", PIN_DIR / "program",
        ])
        report["steps"]["add_filter"] = result

        # A failed command may still have changed kernel state.
        # Cleanup will inspect actual TC state before deleting anything.
        attached_filter = True
        require_ok(result, "Attach Day 23 ingress filter")

        # Confirm and record filter ownership before generating traffic.
        filters_now = read_tc_filter_details()
        filter_state = day23_filter_state(filters_now, program_id)

        report["steps"]["filter_ownership"] = {
            "state": filter_state,
            "program_id": program_id,
            "verified": filter_state == "owned",
        }

        if filter_state != "owned":
            raise RuntimeError(
                f"Could not verify Day 23 filter ownership: {filter_state}"
            )

        start_event = threading.Event()
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=CONCURRENCY
        ) as executor:
            futures = [
                executor.submit(
                    attempt_connection,
                    i,
                    SOURCE_PORTS[i],
                    start_event,
                )
                for i in range(ATTEMPTS)
             ]
            start_event.set()
            results = [future.result() for future in futures]

        report["workload"]["results"] = results
        report["workload"]["attempts_completed"] = len(results)
        outcomes = {}
        for item in results:
            outcomes[item["outcome"]] = outcomes.get(item["outcome"], 0) + 1
        report["workload"]["outcomes"] = outcomes

        report["kernel_counters"] = dump_counters()

        source_port_hits = dump_source_port_hits()

        report["source_port_evidence"] = {
            "expected_source_ports": list(SOURCE_PORTS),
            "observed_source_ports": sorted(source_port_hits),
            "hit_counts": {
                str(port): count
                for port, count in sorted(source_port_hits.items())
             },
         }
    except Exception as exc:
        run_error = f"{type(exc).__name__}: {exc}"
        report["error"] = run_error

    finally:
        # Never delete a filter based on preference alone.
        if attached_filter:
            try:
                filters_before_delete = read_tc_filter_details()
                current_state = day23_filter_state(
                    filters_before_delete, program_id
                )

                if current_state == "absent":
                    filter_state = "absent"
                    report["cleanup"]["filter_delete"] = {
                        "status": "not_needed",
                        "reason": "Day 23 filter is already absent",
                    }

                elif current_state == "owned":
                    result = command([
                        "tc", "filter", "del", "dev", INTERFACE,
                        "ingress", "pref", FILTER_PREF,
                    ])
                    report["cleanup"]["filter_delete"] = result

                    if result["returncode"] == 0:
                        filters_after_delete = read_tc_filter_details()
                        verified_state = day23_filter_state(
                            filters_after_delete, program_id
                        )

                        if verified_state == "absent":
                            filter_state = "absent"
                            report["cleanup"]["filter_delete"]["status"] = "ok"
                        else:
                            filter_state = "ambiguous"
                            report["cleanup"]["filter_delete"]["status"] = "error"
                            report["cleanup"]["filter_delete"]["reason"] = (
                                "Filter absence could not be verified"
                            )
                    else:
                        filter_state = "ambiguous"
                        report["cleanup"]["filter_delete"]["status"] = "error"

                else:
                    filter_state = "ambiguous"
                    report["cleanup"]["filter_delete"] = {
                        "status": "skipped",
                        "reason": (
                            "Filter ownership is ambiguous; "
                            "refusing to delete by preference"
                        ),
                    }

            except Exception as exc:
                filter_state = "ambiguous"
                report["cleanup"]["filter_delete"] = {
                    "status": "error",
                    "reason": f"{type(exc).__name__}: {exc}",
                }

        # Preserve the qdisc if ownership or filter state is uncertain.
        if qdisc_add_attempted:
            if not created_qdisc:
                try:
                    qdisc_after, _, _ = read_tc_state()

                    if "clsact" in qdisc_after:
                        report["cleanup"]["qdisc_delete"] = {
                            "status": "skipped",
                            "reason": (
                                "Qdisc creation did not confirm ownership; "
                                "preserving observed clsact qdisc"
                            ),
                        }
                    else:
                        report["cleanup"]["qdisc_delete"] = {
                            "status": "not_needed",
                            "reason": "No clsact qdisc is present",
                        }

                except Exception as exc:
                    report["cleanup"]["qdisc_delete"] = {
                        "status": "error",
                        "reason": f"{type(exc).__name__}: {exc}",
                    }

            elif filter_state == "ambiguous":
                report["cleanup"]["qdisc_delete"] = {
                    "status": "skipped",
                    "reason": "Filter state is ambiguous; preserving qdisc",
                }
            else:
                try:
                    _, ingress_after, egress_after = read_tc_state()

                    if ingress_after.strip() or egress_after.strip():
                        report["cleanup"]["qdisc_delete"] = {
                            "status": "skipped",
                            "reason": "Filters remain; preserving qdisc",
                        }
                    else:
                        result = command([
                            "tc", "qdisc", "del",
                            "dev", INTERFACE, "clsact",
                        ])
                        report["cleanup"]["qdisc_delete"] = result
                        report["cleanup"]["qdisc_delete"]["status"] = (
                            "ok" if result["returncode"] == 0 else "error"
                        )

                except Exception as exc:
                    report["cleanup"]["qdisc_delete"] = {
                        "status": "error",
                        "reason": f"{type(exc).__name__}: {exc}",
                    }

        # Never remove pins while a filter might still reference the program.
        if created_pin_dir:
            if filter_state == "ambiguous":
                report["cleanup"]["pin_cleanup"] = {
                    "status": "skipped",
                    "reason": (
                        "Filter state is ambiguous; preserving BPF pins "
                        "for manual inspection"
                    ),
                }
            else:
                try:
                    shutil.rmtree(PIN_DIR)
                    report["cleanup"]["pin_cleanup"] = {"status": "ok"}
                except OSError as exc:
                    report["cleanup"]["pin_cleanup"] = {
                        "status": "error",
                        "reason": str(exc),
                    }

        report["cleanup"]["complete"] = all(
            report["cleanup"][key].get("status") in ("ok", "not_needed")
            for key in ("filter_delete", "qdisc_delete", "pin_cleanup")
        )

        if temp_object:
            try:
                temp_object.unlink(missing_ok=True)
            except OSError:
                pass

    counters = report["kernel_counters"] or {}
    outcomes = report["workload"]["outcomes"]
    report["checks"] = {
        "workload_completed": (
            report["workload"]["attempts_completed"] == ATTEMPTS
            and sum(outcomes.values()) == ATTEMPTS
        ),
        "all_attempts_timed_out": (
            outcomes.get("timeout", 0) == ATTEMPTS
        ),
        "drop_accuracy_passed": (
            counters.get("matched", 0) > 0
            and counters.get("dropped", 0) == counters.get("matched", 0)
        ),
        "source_port_coverage_passed": (
            set(source_port_hits) == set(SOURCE_PORTS)
            and all(
                isinstance(count, int)
                and not isinstance(count, bool)
                and count > 0
                for count in source_port_hits.values()
            )
            and len(report["workload"]["results"]) == ATTEMPTS
            and {
                item.get("source_port")
                for item in report["workload"]["results"]
            } == set(SOURCE_PORTS)
        ),
        "cleanup_complete": report["cleanup"]["complete"],
        "no_runtime_error": run_error is None,
    }
    report["overall"] = (
        "PASS"
        if all(report["checks"].values())
        else "FAIL"
    )
    report["kernel_drop_proof"] = report["overall"] == "PASS"
    report["concurrency_evidence"] = report["overall"] == "PASS"

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"\nReport written to: {REPORT}")
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
