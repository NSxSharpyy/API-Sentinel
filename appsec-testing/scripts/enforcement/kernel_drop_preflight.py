#!/usr/bin/env python3
"""Non-destructive preflight checks for the Day 19 TC/eBPF lab."""
import argparse
import json
import shutil
import subprocess


REQUIRED_TOOLS = ("clang", "tc", "bpftool")


def inspect_preflight(
    interface,
    available_tools,
    qdisc_output,
    qdisc_returncode=0,
):
    """Evaluate supplied observations without changing system state."""
    missing_tools = [
        tool for tool in REQUIRED_TOOLS
        if tool not in available_tools
    ]
    clsact_present = any(
        line.lstrip().startswith("qdisc clsact ")
        or line.lstrip() == "qdisc clsact"
        for line in qdisc_output.splitlines()
    )

    checks = {
        "required_tools_available": not missing_tools,
        "qdisc_query_succeeded": qdisc_returncode == 0,
        "interface_has_no_existing_clsact": (
            qdisc_returncode == 0 and not clsact_present
        ),
    }

    return {
        "schema_version": 1,
        "interface": interface,
        "checks": checks,
        "missing_tools": missing_tools,
        "existing_clsact_detected": clsact_present,
        "overall": "PASS" if all(checks.values()) else "FAIL",
        "scope": "read-only preflight; no system changes performed",
    }


def run_preflight(interface):
    available_tools = {
        tool for tool in REQUIRED_TOOLS if shutil.which(tool)
    }

    if not shutil.which("tc"):
        qdisc_output = ""
        returncode = 127
    else:
        try:
            result = subprocess.run(
                ["tc", "qdisc", "show", "dev", interface],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            qdisc_output = result.stdout
            returncode = result.returncode
        except (OSError, subprocess.TimeoutExpired):
            qdisc_output = ""
            returncode = 1

    return inspect_preflight(
        interface=interface,
        available_tools=available_tools,
        qdisc_output=qdisc_output,
        qdisc_returncode=returncode,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interface", default="lo")
    args = parser.parse_args()

    report = run_preflight(args.interface)
    print(json.dumps(report, indent=2))
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
