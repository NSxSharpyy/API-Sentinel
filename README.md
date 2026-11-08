# API-Sentinel
### In-Kernel API Traffic Classification & Security Engine

![Rust](https://img.shields.io/badge/Rust-Programming_Language-orange?logo=rust)
![eBPF](https://img.shields.io/badge/eBPF-Kernel_Technology-blue)
![Linux](https://img.shields.io/badge/Linux-Platform-black?logo=linux)
![Aya](https://img.shields.io/badge/Aya-eBPF_Framework-purple)
![License](https://img.shields.io/badge/License-Check_Repository-lightgrey)

**API-Sentinel** is a Linux kernel-level network security and telemetry project built using **eBPF, Rust, and Aya**.

It inspects supported IPv4/TCP traffic, classifies HTTP requests, associates network activity with client identifiers, and enforces IP-based blocklist rules directly inside the Linux kernel using the Traffic Control (TC) subsystem.

The project aims to provide low-overhead network monitoring, kernel-level packet filtering, and asynchronous event delivery to userspace through a BPF Ring Buffer.

---

## Table of Contents

- [Features](#features)
- [System Architecture](#system-architecture)
- [How It Works](#how-it-works)
- [Technology Stack](#technology-stack)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Build](#build)
- [Running API-Sentinel](#running-api-sentinel)
- [Testing](#testing)
- [BPF Maps](#bpf-maps)
- [Project Structure](#project-structure)
- [Performance and Limitations](#performance-and-limitations)
- [Security Considerations](#security-considerations)
- [Contributing](#contributing)
- [License](#license)
- [Author](#author)

---

## Features

### 1. Kernel-Level Blocklist Enforcement
- IPv4-based traffic filtering inside the Linux kernel.
- Fast BPF HashMap lookups.
- Packet rejection using `TC_ACT_SHOT`.
- Reduces unnecessary userspace packet-processing overhead.

### 2. HTTP Traffic Classification
- Inspection of supported IPv4/TCP packets.
- HTTP request metadata extraction.
- Identification of supported HTTP methods and URIs.
- Client identification using BPF maps.

### 3. Asynchronous Event Telemetry
- Kernel-to-userspace event delivery using `BPF Ring Buffer`.
- Shared event structure between kernel and userspace.
- Event-drop monitoring.
- Userspace event consumption and decoding.

### 4. Process and Client Identification
- Socket-to-process TGID association.
- IPv4-to-client identifier mapping.
- Network activity attribution.

### 5. Isolated Testing Environment
- Linux Network Namespaces.
- Virtual Ethernet (`veth`) interfaces.
- Isolated traffic generation.
- Blocklist and HTTP classification testing.

### 6. Safety Mechanisms
- Test-mode support.
- Isolated network testing.
- Configurable network interface.
- Reduced risk of affecting host network traffic during testing.

---

## System Architecture

```text
        Incoming / Outgoing Network Traffic
                       |
                       v
       +-----------------------------------+
       |       Linux Kernel Subsystem      |
       |                                   |
       |        TC (clsact) Hook           |
       |                                   |
       |     IPv4/TCP Packet Parsing       |
       |                 |                 |
       |          +------+-------+         |
       |          |              |        |
       |          v              v        |
       |      BLOCKLIST     HTTP Classifier|
       |          |              |        |
       |          v              v        |
       |      TC_ACT_SHOT   CLIENT MAP     |
       |                         |         |
       |                         v         |
       |                    BPF Ring Buffer|
       +-------------------------+---------+
                                 |
                                 v
       +-----------------------------------+
       |       Userspace Telemetry         |
       |                                   |
       |  - Event Consumption              |
       |  - Event Decoding                 |
       |  - Client Identification          |
       |  - Telemetry Logging              |
       |  - BPF Map Management             |
       +-----------------------------------+
```

---

## How It Works

1. Network packets reach the configured Linux Traffic Control hook.
2. The eBPF classifier processes supported IPv4/TCP traffic.
3. The packet source IP is checked against the `BLOCKLIST` map.
4. If the IP is blocked, the packet can be rejected using `TC_ACT_SHOT`.
5. Eligible HTTP traffic is inspected for supported request metadata.
6. Client identifiers are retrieved from the `CLIENT_IDENTIFIERS` map.
7. Event metadata is submitted to the `EVENTS` ring buffer.
8. Userspace consumes and processes available events.

**Note:** Actual packet direction, supported formats, and event behavior depend on the active eBPF program configuration.

---

## Technology Stack

| Technology | Purpose |
|---|---|
| Rust | Userspace application and eBPF development |
| Aya | Rust eBPF framework |
| eBPF | Kernel-level packet processing |
| Linux TC | Traffic classification and enforcement |
| BPF Maps | Runtime state and rule storage |
| BPF Ring Buffer | Kernel-to-userspace event delivery |
| bpftool | eBPF program and map inspection |
| iproute2 | Network interface and namespace management |
| Cargo | Rust build system |

---

## Prerequisites

Before installing API-Sentinel, ensure your system has:

| Component | Requirement |
|---|---|
| Operating System | Ubuntu 22.04/24.04 or compatible Linux distribution |
| Kernel | Linux 5.8+ recommended |
| Rust | Stable Rust toolchain |
| Clang | eBPF compilation support |
| LLVM | Compiler infrastructure |
| bpftool | BPF inspection and management |
| iproute2 | Network configuration |
| Git | Repository management |
| Privileges | Root or appropriate Linux capabilities |

**Important:** Kernel compatibility depends on the eBPF program types, helpers, map types, and features used by the implementation.

---

## Installation

### Step 1: Update Your System

```bash
sudo apt-get update
sudo apt-get upgrade -y
```

### Step 2: Install Dependencies

```bash
sudo apt-get install -y \
    clang \
    llvm \
    libelf-dev \
    linux-headers-$(uname -r) \
    bpftool \
    iproute2 \
    curl \
    build-essential \
    git
```

### Step 3: Install Rust

Install Rust using Rustup:

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

Load the Rust environment:

```bash
source "$HOME/.cargo/env"
```

Verify installation:

```bash
rustc --version
cargo --version
```

### Step 4: Clone the Repository

```bash
git clone https://github.com/NSxSharpyy/API-Sentinel.git
```

Navigate to the project:

```bash
cd API-Sentinel
```

---

## Build

Build the project in release mode:

```bash
cargo build --release
```

The expected executable location is:

```text
target/release/api-sentinel-ebpf
```

The exact output location depends on the Cargo workspace and binary configuration.

---

## Running API-Sentinel

First, identify your network interface:

```bash
ip link show
```

Run API-Sentinel with the selected interface:

```bash
sudo env API_SENTINEL_INTERFACE=ens33 \
./target/release/api-sentinel-ebpf
```

Replace `ens33` with your actual network interface name.

**Warning:** Running an eBPF agent with elevated privileges can affect network traffic. Use a dedicated test interface or isolated environment during development.

---

## Testing

API-Sentinel development includes isolated network testing using Linux Network Namespaces and virtual Ethernet interfaces.

The functional testing workflow is intended to validate:

- eBPF program loading.
- TCP monitoring.
- HTTP request classification.
- Client identifier mapping.
- Blocklist enforcement.
- Ring-buffer event delivery.
- Event-drop counters.

### Run Functional Tests

If the repository contains `tests/run_functional_tests.sh`, execute:

```bash
chmod +x tests/run_functional_tests.sh
```

Then:

```bash
sudo ./tests/run_functional_tests.sh
```

Inspect the script before execution to understand its network setup, cleanup operations, and required privileges.

### Example Expected Results

```text
[*] Cleaning up stale test environment...

[1/5] Setting up isolated network namespace...

[2/5] Starting API-Sentinel in test mode...

[3/5] Verifying blocklist enforcement...

[+] PASSED: Blocked IP traffic dropped successfully.

[4/5] Starting mock HTTP receiver...

[5/5] Testing HTTP classification and ring-buffer telemetry...

[+] PASSED: HTTP request classified successfully.

===========================================
       FUNCTIONAL TESTS COMPLETED
===========================================

[+] Cleanup complete.
```

*The output above is illustrative. Actual results depend on the implementation and test environment.*

---

## BPF Maps

API-Sentinel uses the following BPF maps:

| Map | Purpose |
|---|---|
| `SOCKET_TGID` | Associates socket information with process TGIDs |
| `CLIENT_IDENTIFIERS` | Maps IPv4 addresses to client identifiers |
| `BLOCKLIST` | Stores IPv4 addresses selected for blocking |
| `EVENTS` | Ring buffer for kernel-to-userspace events |
| `EVENT_DROPS` | Tracks events that could not be submitted |
| `BLOCKLIST_DROPS` | Tracks packets rejected by blocklist enforcement |

---

## Project Structure

```text
API-Sentinel/
│
├── api-sentinel-ebpf/
│   └── src/
│       └── main.rs
│
├── api-sentinel-ebpf-common/
│   └── src/
│       └── lib.rs
│
├── api-sentinel-ebpf-ebpf/
│   └── src/
│       └── main.rs
│
├── docs/
│   ├── architecture.md
│   ├── CHANGELOG.md
│   ├── kernel-ebpf-day30-architecture.md
│   └── ...
│
├── tests/
│   └── ...
│
├── Cargo.toml
└── README.md
```

*This is a simplified project structure. Additional backend, frontend, testing, and deployment components may exist in the repository.*

---

## Development & Validation

### Check Rust Formatting

```bash
cargo fmt --all -- --check
```

### Check Git Whitespace Errors

```bash
git diff --check
```

### Build Release Version

```bash
cargo build --release
```

### Check Git Status

```bash
git status -sb
```

---

## Performance and Limitations

API-Sentinel is designed for low-overhead kernel-level packet processing.

Actual performance depends on:

- Linux kernel version and configuration.
- CPU and network hardware.
- Packet size and traffic volume.
- BPF map lookup and update frequency.
- Ring-buffer capacity.
- Userspace event-consumption rate.
- Packet parsing and classification logic.

### Technical Limitations

- Normal HTTP inspection does not reveal encrypted HTTPS/TLS application data.
- IPv4/TCP support does not imply support for every network protocol.
- Ring-buffer events can be dropped if userspace cannot consume them quickly enough.
- Blocklist behavior depends on packet direction and matching logic.
- Kernel and userspace event structures must remain ABI-compatible.
- Performance measurements must specify their measurement methodology.

---

## Security Considerations

API-Sentinel is intended for authorized network monitoring, security research, and defensive testing.

- Deploy only on systems and networks you own or are authorized to monitor.
- Use isolated lab environments for packet-filtering experiments.
- Verify eBPF program attachments before production deployment.
- Protect telemetry because network metadata can contain sensitive information.
- Apply appropriate access controls to runtime configuration.
- Avoid testing blocklist enforcement on production interfaces.

---

## Contributing

Contributions, bug reports, and suggestions are welcome.

To contribute:

1. Fork the repository.
2. Create a feature branch.
3. Implement your changes.
4. Run formatting and build checks.
5. Submit a Pull Request with a clear description.

Example:

```bash
git checkout -b feature/your-feature
```

Validate your changes:

```bash
cargo fmt --all -- --check
cargo build --release
```

---

## License

The project license should match the license files included in the repository.

If the project uses dual licensing under `Apache-2.0` and `MIT`, include the corresponding license files and clarify the licensing terms.

---

## Author

**API-Sentinel**

Developed as a collaborative cybersecurity engineering project using:

- Rust
- Aya
- eBPF
- Linux Networking
- Traffic Control (TC)

**GitHub Profile:**  
https://github.com/NSxSharpyy

**Project Repository:**  
https://github.com/NSxSharpyy/API-Sentinel

---

<p align="center">
  <b>Building Kernel-Level Network Visibility & Defensive Security with eBPF.</b>
</p>
