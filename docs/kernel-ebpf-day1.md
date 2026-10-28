# API-Sentinel — Kernel eBPF Day 1

## Objective

Set up the Rust/Aya eBPF development environment and compile a baseline tracepoint program.

## Environment

* OS: Ubuntu 24.04 VM
* Kernel: `7.0.3-generic`
* eBPF framework: Aya (Rust)
* Tools: Rust/Cargo, Clang/LLVM, bpftool, bpf-linker

## Implementation

* Generated the Aya eBPF workspace.
* Configured the workspace for a `sched/sched_switch` tracepoint.
* Built the userspace loader and eBPF program.
* Integrated the project into the `kernel-ebpf` branch of the team repository.

## Validation

* `cargo build` completed successfully in the team repository.
* The eBPF artifact was identified as an ELF relocatable eBPF file.
* `bpftool` previously showed the program loaded as a tracepoint program.
* `bpftool link show` previously confirmed attachment to `sched_switch`.

## Outcome

The baseline Aya eBPF project builds successfully. The tracepoint program was loaded and attached successfully in the initial development workspace.

## Next Steps

* Review the repository changes.
* Commit the Day 1 implementation on `kernel-ebpf`.
* Proceed to Day 2 socket lifecycle tracing after Day 1 is finalized.
