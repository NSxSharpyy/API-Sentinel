# API-Sentinel — Final Validation Status

**Date:** 10 November 2026
**Branch:** backend-parser
**Backend commit:** b6cbee7

## 1. Verified implementation

- FastAPI asynchronous ingestion and packet-processing pipeline.
- TCP stream reassembly and HTTP transaction correlation.
- Bounded asynchronous persistence.
- REST APIs for endpoints, alerts and metrics.
- BOLA detection, alerting and controlled eBPF enforcement.
- Transaction and alert WebSocket interfaces.
- Parser lifecycle handling and aggregate diagnostics.
- React dashboard source and production build.

## 2. Automated validation

| Check | Result |
|---|---|
| Backend regression | 340 passed |
| Python 3.13 CI | Passed |
| Python 3.14 CI | Passed |
| Frontend ESLint | Passed |
| Frontend Vite production build | Passed |
| Alert/API/WebSocket targeted tests | 20 passed |
| Isolated runtime smoke test | Passed |
| SQLite integrity | Passed |
| Graceful shutdown | Passed |

GitHub Actions run: 42757695680.

## 3. Live capture validation

### Run A — 60 seconds, concurrency 8

- Successful HTTP requests: 9,905
- Newly persisted transactions: 9,200
- Accepted packets: 58,730
- Packet rejections/drops: 0
- TCP stream-limit rejections: 1,406
- TCP reassembly overflows: 1
- HTTP correlator drops: 5 at soak completion
- Persistence failures/rejections: 0
- Final queues: drained
- RSS growth: 24.5 MiB
- Result: FAIL

### Run B — 30 seconds, concurrency 2

- Successful HTTP requests: 5,309
- Newly persisted transactions: 5,309
- Accepted packets: 31,859
- Packet rejections/drops: 0
- TCP stream-limit rejections: 0
- TCP reassembly overflows: 0
- HTTP correlator drops: 1
- Persistence failures/rejections: 0
- Final queues: drained
- RSS growth: 18.4 MiB
- Result: FAIL under strict zero-drop acceptance.

Both runs used WSL2 loopback capture and isolated SQLite. These are not physical-NIC or production-database benchmarks.

The concurrency-8 run showed TCP capacity pressure. The lower-concurrency run eliminated TCP stream rejections and overflow, but one HTTP request was still dropped.

During the second run, repeated HTTP header-size parser errors were observed on traffic involving TCP port 5557. The interaction between captured ZeroMQ traffic and HTTP parsing requires investigation.

## 4. Cleanup verification

- Uvicorn stopped.
- Ring-reader and loader processes were no longer running.
- API-Sentinel pinned BPF map was absent.
- No API-Sentinel TC ingress filter remained on loopback.
- Isolated SQLite database integrity check returned `ok`.
- Combined persisted transaction row count: 14,511.

## 5. Outstanding acceptance items

1. Resolve the live-capture TCP stream-limit and HTTP drop findings.
2. Investigate port 5557 parser noise and capture filtering.
3. Complete long-duration queue/persistence and physical-NIC testing.
4. Complete the 24-hour memory/leak soak.
5. Establish the Day 15 sub-millisecond serialization acceptance criteria using the required measurement boundary.
6. Validate IPv6 and fragmented IPv4 handling or document the accepted scope.
7. Complete browser-level frontend integration verification.
8. Complete authentication, authorization and comprehensive PII-boundary review.
9. Obtain external integration confirmation and formal acceptance.

## 6. Final assessment

Core implementation, automated testing, CI, frontend lint/build, and controlled lab functionality have been verified.

Live-capture performance acceptance remains open. The project is not certified production-ready, and no external sign-off is claimed.
