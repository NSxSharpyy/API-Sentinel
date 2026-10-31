#!/usr/bin/env python3
"""Guarded Day 19 TC/eBPF packet-drop integration experiment."""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PREFLIGHT = HERE / "kernel_drop_preflight.py"
SOURCE = HERE / "day19_request_drop.c"
INTERFACE = "lo"
SOURCE_PORT = 50355
DESTINATION_PORT = 5004
PIN_ROOT = Path("/sys/fs/bpf/day19_request_drop_run")


def parse_stats(raw_output):
    """Parse bpftool JSON map output into the three uint64 counters."""
    entries = json.loads(raw_output)
    if not isinstance(entries, list) or len(entries) != 1:
        raise ValueError("Expected exactly one array-map entry")

    entry = entries[0]
    if not isinstance(entry, dict):
        raise ValueError("Unexpected BPF map entry format")

    formatted = entry.get("formatted")
    if isinstance(formatted, dict):
        formatted_value = formatted.get("value")
        if isinstance(formatted_value, dict):
            names = ("seen", "matched", "dropped")
            if all(name in formatted_value for name in names):
                try:
                    return {
                        name: int(formatted_value[name])
                        for name in names
                    }
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "Invalid formatted BPF counter value"
                    ) from exc

    raw_value = entry.get("value")
    if not isinstance(raw_value, list) or len(raw_value) != 24:
        raise ValueError("Unexpected BPF map value format")

    try:
        values = bytes(
            int(item, 16) if isinstance(item, str) else int(item)
            for item in raw_value
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid raw BPF map bytes") from exc

    counters = [
        int.from_bytes(values[offset:offset + 8], "little")
        for offset in (0, 8, 16)
    ]
    return dict(zip(("seen", "matched", "dropped"), counters))


def command(args, timeout=10):
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )

def filter_preference_present(raw_output, preference=49152):
    """Return whether tc JSON output contains the target filter preference."""
    try:
        filters = json.loads(raw_output)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not parse TC filter JSON") from exc

    if not isinstance(filters, list):
        raise ValueError("Unexpected TC filter JSON structure")

    def contains_preference(item):
        if isinstance(item, dict):
            if item.get("pref") == preference:
                return True
            return any(contains_preference(value) for value in item.values())
        if isinstance(item, list):
            return any(contains_preference(value) for value in item)
        return False

    return contains_preference(filters)

def preflight():
    result = command(
        [sys.executable, str(PREFLIGHT), "--interface", INTERFACE]
    )
    print(result.stdout, end="")
    return result.returncode == 0


def dry_run():
    print(json.dumps({
        "mode": "dry-run",
        "interface": INTERFACE,
        "source_port": SOURCE_PORT,
        "destination_port": DESTINATION_PORT,
        "source": str(SOURCE),
        "will_attach_filter": False,
        "overall": "PREFLIGHT_ONLY",
    }, indent=2))
    return 0 if preflight() else 1


def cleanup_succeeded(cleanup):
    """Return whether every attempted cleanup operation succeeded."""
    for name in ("filter_delete", "qdisc_delete", "pin_cleanup"):
        item = cleanup.get(name)
        if item is not None and (
            item.get("skipped")
            or "error" in item
            or item.get("returncode") != 0
        ):
            return False

    return not bool(cleanup.get("pin_cleanup_errors"))

def observation_succeeded(
    stats_returncode,
    parsed_stats,
    client_error,
    received_response,
):
    """Return True only when packet-drop evidence meets every assertion."""
    if stats_returncode != 0 or not isinstance(parsed_stats, dict):
        return False

    try:
        matched = parsed_stats["matched"]
        dropped = parsed_stats["dropped"]
    except (KeyError, TypeError):
        return False

    return (
        isinstance(matched, int)
        and not isinstance(matched, bool)
        and isinstance(dropped, int)
        and not isinstance(dropped, bool)
        and matched > 0
        and dropped > 0
        and matched == dropped
        and client_error == "response_timeout"
        and received_response is False
    )


def execute():
    if os.geteuid() != 0:
        print("ERROR: --execute requires root; use sudo.", file=sys.stderr)
        return 2

    if not all(shutil.which(tool) for tool in ("clang", "tc", "bpftool")):
        print("ERROR: required tool is missing.", file=sys.stderr)
        return 2

    token = os.environ.get("DAY19_AUTH_TOKEN", "").strip()
    if not token:
        print(
            "ERROR: set DAY19_AUTH_TOKEN to a valid lab access token; "
            "the token will not be printed or included in the report.",
            file=sys.stderr,
        )
        return 2

    if not SOURCE.is_file():
        print(f"ERROR: BPF source not found: {SOURCE}", file=sys.stderr)
        return 2

    if PIN_ROOT.exists():
        print(
            f"ERROR: pin directory already exists: {PIN_ROOT}; "
            "refusing to overwrite it.",
            file=sys.stderr,
        )
        return 2

    if not preflight():
        print("ERROR: preflight failed; no network changes made.", file=sys.stderr)
        return 2

    output = {
        "schema_version": 1,
        "interface": INTERFACE,
        "source_port": SOURCE_PORT,
        "destination_port": DESTINATION_PORT,
        "steps": {},
        "cleanup": {},
    }

    qdisc_created = False
    filter_created = False
    filter_add_attempted = False
    filter_state_ambiguous = False
    program_pinned = False
    pin_root_created = False
    temp_object = None

    try:
        with tempfile.TemporaryDirectory(prefix="day19-ebpf-") as temp_dir:
            temp_object = str(Path(temp_dir) / "day19_request_drop.o")

            build = command([
                "clang", "-O2", "-g", "-target", "bpf",
                "-I/usr/include/x86_64-linux-gnu",
                "-c", str(SOURCE), "-o", temp_object,
            ])
            output["steps"]["compile"] = {
                "returncode": build.returncode,
                "stderr": build.stderr[-2000:],
            }
            if build.returncode != 0:
                raise RuntimeError("BPF compilation failed")

            PIN_ROOT.mkdir(mode=0o700, exist_ok=False)
            pin_root_created = True
            (PIN_ROOT / "maps").mkdir(mode=0o700, exist_ok=False)

            load = command([
                "bpftool", "prog", "load", temp_object,
                str(PIN_ROOT / "prog"), "type", "classifier",
                "pinmaps", str(PIN_ROOT / "maps"),
            ])
            output["steps"]["load"] = {
                "returncode": load.returncode,
                "stderr": load.stderr[-2000:],
            }
            if load.returncode != 0:
                raise RuntimeError("BPF program load failed")
            program_pinned = True

            # Recheck immediately before creating the qdisc.
            if not preflight():
                raise RuntimeError(
                    "Preflight changed before attachment; aborting"
                )

            add_qdisc = command(["tc", "qdisc", "add", "dev", INTERFACE, "clsact"])
            output["steps"]["add_qdisc"] = {
                "returncode": add_qdisc.returncode,
                "stderr": add_qdisc.stderr[-2000:],
            }
            if add_qdisc.returncode != 0:
                raise RuntimeError("Could not create clsact qdisc")
            qdisc_created = True

            filter_add_attempted = True
            add_filter = command([
                "tc", "filter", "add", "dev", INTERFACE, "ingress",
                "protocol", "ip", "pref", "49152", "bpf", "da",
                "pinned", str(PIN_ROOT / "prog"), "skip_hw",
            ])
            output["steps"]["add_filter"] = {
                "returncode": add_filter.returncode,
                "stderr": add_filter.stderr[-2000:],
            }
            if add_filter.returncode != 0:
                # The failed command may have changed kernel state. Inspect
                # before cleanup; never delete an unverified filter by pref.
                try:
                    listing = command([
                        "tc", "-j", "-details", "filter", "show",
                        "dev", INTERFACE, "ingress",
                    ])
                    if listing.returncode != 0:
                        raise RuntimeError(
                            f"TC filter inspection failed: {listing.stderr[-1000:]}"
                        )

                    matching_preference = filter_preference_present(listing.stdout)


                    output["cleanup"]["filter_add_failure_inspection"] = {
                        "returncode": listing.returncode,
                        "matching_preference_detected": matching_preference,
                    }


                    if matching_preference:
                        filter_state_ambiguous = True
                        output["cleanup"]["manual_intervention_required"] = (
                            "Filter attachment state is ambiguous. Inspect TC ingress filters "
                            "before removing the filter, qdisc, or BPF pins."
                    )
                    output["cleanup"].setdefault("pin_cleanup_errors", []).append(
                        "Filter attachment failed and kernel state is ambiguous; "
                        "inspect TC filters manually."
                    )
                except Exception as exc:
                    filter_state_ambiguous = True
                    output["cleanup"]["manual_intervention_required"] = (
                        "Could not verify TC state after filter-add failure. "
                        "Inspect TC ingress filters before cleanup."
                    )
                    output["cleanup"].setdefault(
                        "pin_cleanup_errors", []
                    ).append(
                        "Could not inspect TC state after filter-add failure: "
                        f"{type(exc).__name__}: {exc}"
                    )
                raise RuntimeError("Could not attach BPF filter")
            filter_created = True

            # Use a fresh TCP connection with the classifier's fixed source port.
            received_response = False
            client_error = None
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                    client.settimeout(2.0)
                    client.bind(("127.0.0.1", SOURCE_PORT))
                    client.connect(("127.0.0.1", DESTINATION_PORT))
                    request_bytes = (
                        b"GET /api/v2/billing/invoices/3 HTTP/1.1\r\n"
                        b"Host: localhost\r\n"
                        + b"Authorization: Bearer "
                        + token.encode("ascii")
                        + b"\r\nConnection: close\r\n\r\n"
                    )
                    client.sendall(request_bytes)
                    try:
                        received_response = bool(client.recv(128))
                    except socket.timeout:
                        client_error = "response_timeout"
            except OSError as exc:
                client_error = type(exc).__name__ + ": " + str(exc)

            time.sleep(0.2)
            stats_path = PIN_ROOT / "maps" / "day19_stats_map"
            stats = command([
                "bpftool", "-j", "map", "dump",
                "pinned", str(stats_path),
            ])
            parsed_stats = None
            stats_parse_error = None
            if stats.returncode == 0:
                try:
                    parsed_stats = parse_stats(stats.stdout)
                except (ValueError, TypeError, KeyError) as exc:
                    stats_parse_error = str(exc)

            output["steps"]["map_dump"] = {
                "returncode": stats.returncode,
                "counters": parsed_stats,
                "parse_error": stats_parse_error,
                "stderr": stats.stderr[-1000:],
            }
            output["steps"]["client"] = {
                "received_response": received_response,
                "error": client_error,
            }
            response_timed_out = client_error == "response_timeout"

            observation_ok = observation_succeeded(
                stats.returncode,
                parsed_stats,
                client_error,
                received_response,
            )
            output["steps"]["assertions"] = {
                "map_dump_succeeded": stats.returncode == 0,
                "matched_packets_positive": (
                    parsed_stats["matched"] > 0
                    if parsed_stats is not None else False
                ),
                "dropped_packets_positive": (
                    parsed_stats["dropped"] > 0
                    if parsed_stats is not None else False
                ),
                "matched_equals_dropped": (
                    parsed_stats["matched"] == parsed_stats["dropped"]
                    if parsed_stats is not None else False
                ),
                "client_response_timed_out": response_timed_out,
                "no_http_response_received": not received_response,
            }
            output["overall"] = (
                "OBSERVED" if observation_ok else "INCONCLUSIVE"
            )
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        output["error"] = str(exc)
        output["overall"] = "FAIL"
    finally:
        # Record cleanup errors but continue attempting all owned cleanup.
        def cleanup_command(name, args):
            try:
                result = command(args)
                output["cleanup"][name] = {
                    "returncode": result.returncode,
                    "stderr": result.stderr[-1000:],
                }
            except Exception as exc:
                output["cleanup"][name] = {
                    "error": f"{type(exc).__name__}: {exc}",
                }

        # Remove only the filter this runner attempted to create.
        if filter_created:
            cleanup_command("filter_delete", [
                "tc", "filter", "del", "dev", INTERFACE,
                "ingress", "pref", "49152",
            ])

        # Preserve clsact if attachment state is ambiguous. A later empty
        # listing must not override an earlier failed ownership inspection.
        if qdisc_created and filter_state_ambiguous:
            output["cleanup"]["qdisc_delete"] = {
                "skipped": True,
                "reason": "TC attachment state is ambiguous",
            }
        # Do not delete clsact if other filters are present or queries fail.
        elif qdisc_created:
            try:
                ingress = command([
                    "tc", "filter", "show", "dev", INTERFACE, "ingress"
                ])
                egress = command([
                    "tc", "filter", "show", "dev", INTERFACE, "egress"
                ])
                if (
                    ingress.returncode == 0 and egress.returncode == 0
                    and not ingress.stdout.strip()
                    and not egress.stdout.strip()
                ):
                    cleanup_command("qdisc_delete", [
                        "tc", "qdisc", "del", "dev", INTERFACE, "clsact"
                    ])
                else:
                    output["cleanup"]["qdisc_delete"] = {
                        "skipped": True,
                        "reason": "Other filters detected or filter query failed",
                    }
            except Exception as exc:
                output["cleanup"]["qdisc_delete"] = {
                    "error": f"{type(exc).__name__}: {exc}",
                }

        # Preserve pins if a possibly attached filter could still reference
        # this program. Manual inspection is safer than removing its pins.
        if filter_state_ambiguous:
            output["cleanup"]["pin_cleanup"] = {
                "skipped": True,
                "reason": "TC attachment state is ambiguous",
            }

        # Remove only pins created under this runner's unique directory.
        elif pin_root_created:
            try:
                paths = sorted(PIN_ROOT.rglob("*"), reverse=True)
            except OSError as exc:
                paths = []
                output["cleanup"].setdefault("pin_cleanup_errors", []).append(
                    f"Could not enumerate {PIN_ROOT}: {exc}"
                )

            for path in paths:
                try:
                    if path.is_file() or path.is_symlink():
                        path.unlink()
                    elif path.is_dir():
                        path.rmdir()
                except OSError as exc:
                    output["cleanup"].setdefault("pin_cleanup_errors", []).append(
                        f"{path}: {exc}"
                    )

            try:
                PIN_ROOT.rmdir()
            except OSError as exc:
                output["cleanup"].setdefault("pin_cleanup_errors", []).append(
                    f"{PIN_ROOT}: {exc}"
                )

    cleanup_ok = cleanup_succeeded(output["cleanup"])
    output["cleanup"]["complete"] = cleanup_ok
    if not cleanup_ok:
        output["overall"] = "FAIL"

    print(json.dumps(output, indent=2))
    return 0 if output.get("overall") == "OBSERVED" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="explicitly run the privileged packet-drop experiment",
    )
    args = parser.parse_args()

    if not args.execute:
        return dry_run()
    return execute()


if __name__ == "__main__":
    raise SystemExit(main())
