API-Sentinel: In-Kernel API Traffic Classification & Security Engine
API-Sentinel is a high-performance in-kernel network security and telemetry daemon built using eBPF and Rust. By attaching to the Linux Traffic Control (TC) subsystem (clsact), API-Sentinel performs wire-speed IP blocklist enforcement and captures Layer-7 HTTP metadata via an asynchronous eBPF ring buffer, bypassing heavy userspace packet inspection overhead.

System Architecture & Workflow
Plaintext
[ Incoming / Outgoing Traffic ]
               │
               ▼
   ┌───────────────────────────────────────────────┐
   │         Linux Kernel Subsystem (TC)           │
   │                                               │
   │   clsact (Egress / Ingress Hook)              │
   │      │                                        │
   │      ├──► Lookup BLOCKLIST Map ──────► Drop (TC_ACT_SHOT)
   │      │                                        │
   │      └──► Parse HTTP & Lookup CLIENT_MAP      │
   │               │                               │
   │               ▼ (Stream Event Metadata)       │
   │         BPF Ring Buffer                       │
   └───────────────┬───────────────────────────────┘
                   │
                   ▼ (Zero-Copy Polling)
   ┌───────────────────────────────────────────────┐
   │         Userspace Telemetry Daemon            │
   │                                               │
   │  - Event Decoding (Method, URI, Client ID)    │
   │  - Telemetry Logging & Metric Aggregation     │
   │  - Dynamic Rule & Map Management              │
   └───────────────────────────────────────────────┘
Key Features
Kernel-Level Enforcement: Zero-overhead packet drops using TC_ACT_SHOT directly inside the kernel datapath.

Low-Latency Map Lookups: Hash maps (BLOCKLIST, CLIENT_IDENTIFIERS) optimized for microsecond-level rule evaluations.

HTTP Payload Telemetry: In-kernel parsing of HTTP methods and URIs with asynchronous streaming to userspace via BPF ring buffers.

Isolated Testing Harness: Built-in regression test suite utilizing Linux network namespaces (netns) and virtual Ethernet (veth) pairs for non-intrusive validation.

Safety Guards: Safe development and test modes preventing accidental attachment to production host interfaces.

Prerequisites
Ensure the deployment system meets the following requirements:

Operating System: Linux (Ubuntu 20.04/22.04/24.04 LTS or Debian 11/12 recommended)

Kernel Version: >= 5.8 (Required for eBPF ring buffer support and modern TC helpers)

Required Privileges: Root or capabilities CAP_BPF, CAP_NET_ADMIN, CAP_SYS_ADMIN

Compiler & Tools: Clang, LLVM, Kernel Headers, bpftool, and Rust Toolchain

Quickstart: Installation & Build
1. Install System Dependencies
Bash
sudo apt-get update
sudo apt-get install -y clang llvm libelf-dev linux-headers-$(uname -r) bpftool iproute2 curl build-essential git
2. Install Rust Toolchain
Bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"
3. Clone the Repository
Bash
git clone https://github.com/NSxSharpyy/API-Sentinel.git
cd API-Sentinel
4. Build the Project
Bash
cargo build --release
The resulting compiled binary will be located at ./target/release/api-sentinel-ebpf.

Verification & Testing
API-Sentinel includes an automated integration test suite that sets up an isolated network namespace, generates traffic, validates blocklist drops, and confirms telemetry delivery without affecting host traffic.

Run Automated Tests
Bash
chmod +x tests/run_functional_tests.sh
sudo ./tests/run_functional_tests.sh
Expected Output
Plaintext
[*] Cleaning up any stale test environment...
[1/5] Setting up isolated network namespace...
[2/5] Starting API-Sentinel in test mode...
[3/5] Verifying blocklist drop enforcement...
[+] PASSED: Blocked IP traffic dropped cleanly.
[4/5] Starting mock HTTP receiver in namespace...
[5/5] Testing HTTP classification and ring buffer telemetry...
[+] PASSED: HTTP request classified and client ID mapped successfully.

===========================================
  ALL FUNCTIONAL & KERNEL TESTS PASSED!    
===========================================
[+] Cleanup complete.
Running API-Sentinel
To monitor traffic on a specific network interface (e.g., eth0, ens33):

Bash
sudo env API_SENTINEL_INTERFACE=eth0 ./target/release/api-sentinel-ebpf
Optional: System-Wide Installation
Copy the compiled binary to the system binary directory:

Bash
sudo install -m 755 ./target/release/api-sentinel-ebpf /usr/local/bin/api-sentinel
Run directly from anywhere:

Bash
sudo env API_SENTINEL_INTERFACE=eth0 api-sentinel
Project Structure
Plaintext
API-Sentinel/
├── bpf/                        # Kernel-space eBPF programs
│   ├── sentinel_classifier.bpf.c
│   └── maps.bpf.h
├── src/                        # Userspace daemon code (Rust)
│   ├── main.rs                 # Lifecycle, CLI flags, signal handling
│   ├── loader.rs               # BPF program & map loader
│   └── telemetry.rs            # Ring buffer consumer & event parser
├── tests/
│   └── run_functional_tests.sh # Automated namespace regression harness
├── Cargo.toml                  # Rust project manifest & dependencies
└── README.md                   # Project documentation
eBPF Maps Overview
Map Name	Type	Purpose
BLOCKLIST	BPF_MAP_TYPE_HASH	Stores blocked IPv4 addresses. Matching packets are dropped immediately.
CLIENT_IDENTIFIERS	BPF_MAP_TYPE_HASH	Maps client IP addresses to internal tenant/service IDs.
BLOCKLIST_DROPS	BPF_MAP_TYPE_PERCPU_ARRAY	High-speed counters tracking drops per CPU core.
EVENTS	BPF_MAP_TYPE_RINGBUF	Asynchronous buffer streaming HTTP request events to userspace.
License
This project is licensed under the Apache-2.0 / MIT License.
