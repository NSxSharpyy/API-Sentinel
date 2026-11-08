# Day 24 — Kernel Codebase Cleanup & Pruning

**Date:** 2026-11-02
**Role:** M1 — Kernel & eBPF Engineer
**Project:** API-Sentinel

## 1. Objective
Clean up the kernel/eBPF codebase, inspect debugging output, remove unused dependencies, configure release optimization, and validate existing functionality.

## 2. Debugging and Logging Inspection
Inspected:
- api-sentinel-ebpf/src
- api-sentinel-ebpf-ebpf/src
- api-sentinel-ebpf-common/src

Searches covered bpf_printk, println!, eprintln!, dbg!, TODO and FIXME.

Findings:
- No bpf_printk statements found.
- No eprintln! or dbg! statements found.
- No TODO/FIXME markers found in inspected source directories.
- Operational println! messages retained for runtime status.
- Existing warning/debug logging retained for error reporting.

## 3. Dependency Cleanup
Removed unused dependencies:
- aya-log
- aya-log-ebpf
- clap

Cargo.lock updated accordingly.

## 4. Release Optimization
Updated root Cargo.toml:

    [profile.release.package.api-sentinel-ebpf-ebpf]
    opt-level = 3
    debug = 2
    codegen-units = 1
    strip = false

## 5. eBPF Test Configuration
The eBPF binary has test = false and bench = false to prevent ordinary test and benchmark harness generation for the no_std/no_main binary.

The binary name remains api-sentinel-ebpf because the userspace loader expects OUT_DIR/api-sentinel-ebpf.

## 6. Build Validation

Targeted build:
    cargo build --release -p api-sentinel-ebpf

Result: PASS.

Workspace build:
    cargo build --release --workspace

Result: NOT PASS.

Issues:
- Duplicate binary output filename.
- Direct host compilation of the no_std eBPF binary failed due to unsupported unwinding.

## 7. Cargo Test Validation

Command:
    cargo test --workspace

Result: PASS.

Limitation: Zero tests were executed. This validates build/test-harness completion, not functional unit-test coverage.

## 8. Blocklist Regression Validation

Environment:
- Host interface: as-test-host
- Namespace: apisentinel-test
- Host IP: 10.20.20.1
- Blocklisted destination: 10.20.20.2
- Allowed destination: 10.20.20.3

### Test A — Blocklisted destination
Command:
    ping -I as-test-host -c 5 -W 1 10.20.20.2

Result: 5 transmitted, 0 received, 100% packet loss.
PASS — destination traffic blocked.

### Test B — Allowed destination
Command:
    ping -I as-test-host -c 3 -W 1 10.20.20.3

Result: 3 transmitted, 3 received, 0% packet loss.
PASS — allowed traffic passed.

### Test C — Blocklisted source
The application was restarted with 10.20.20.1 configured as the blocked source.

Command:
    ping -I as-test-host -c 5 -W 1 10.20.20.3

Result: 5 transmitted, 0 received, 100% packet loss.
PASS — traffic from configured blocked source dropped.

Counter limitation:
BLOCKLIST_DROPS showed an observed total of 6 on CPU 1. No before-and-after baseline was captured, so this is not claimed as an exact packet-drop delta.

## 9. Git Validation

Command:
    git diff --check

Result: PASS — no whitespace errors.

Modified files:
- Cargo.toml
- Cargo.lock
- api-sentinel-ebpf/Cargo.toml
- api-sentinel-ebpf-ebpf/Cargo.toml

## 10. Final Status

| Activity | Result |
|---|---|
| Debugging/logging inspection | PASS |
| Unused dependency cleanup | PASS |
| Release optimization | PASS |
| Targeted release build | PASS |
| Cargo workspace tests | PASS — 0 tests |
| Workspace release build | NOT PASS — documented |
| Destination blocklist test | PASS |
| Allowed destination test | PASS |
| Source blocklist test | PASS |
| Git diff check | PASS |

## 11. Conclusion

Day 24 focused on removing unused dependencies, reviewing debugging output, and configuring release optimization without intentionally changing eBPF classifier logic.

The targeted release build and three previously executed blocklist regression checks passed.

The workspace release-build limitation and absence of executed unit tests remain documented.
