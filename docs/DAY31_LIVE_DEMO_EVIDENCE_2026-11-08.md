# Day 31 — Final Review & Live Demo Evidence

**Evidence date:** 2026-11-08
**Planned Day 31 date:** 2026-11-07
**Workstream:** Member 2 — Backend & Traffic Parsing Engineer
**Branch:** `backend-parser`

## 1. Executive summary

A controlled live demonstration of the API-Sentinel backend capture pipeline was completed in WSL2 using the loopback interface (`lo`).

The eBPF producer captured local TCP traffic, the ring-buffer reader delivered packet events to the backend, the HTTP pipeline reconstructed transactions, and the persistence worker saved completed transactions to the isolated Day 31 SQLite database.

A synthetic POST containing an email address, phone number, valid test card number, and password was captured and persisted. The stored record was inspected directly. PII was masked, the password was redacted, and none of the raw synthetic values were found.

**Result:** The controlled local capture, HTTP reconstruction, persistence, and synthetic PII-redaction checks passed.

This result does not establish production readiness, 24-hour stability, or external team acceptance.

## 2. Test environment and configuration

- Environment: Ubuntu under WSL2
- Kernel: `6.18.54.1-microsoft-standard-WSL2`
- Capture interface: `lo` (loopback, interface index 1)
- Backend bind address: `127.0.0.1:8001`
- Capture configuration: `API_SENTINEL_CAPTURE_ENABLED=1`
- Blocklist drop-audit integration: disabled for this demonstration
- Database: `/tmp/api_sentinel_day31_demo.db`
- eBPF map: `/sys/fs/bpf/api_sentinel_day16_events`
- Map type: ring buffer
- Map capacity: 16 MiB

The Day 16 BPF object compiled successfully using the project's Makefile. The loader reported that the producer was active on `lo` and that the ring-buffer map was pinned at the expected path.

The backend started successfully. Its capture supervisor launched the reader, which logged:

`JSON reader listening on /sys/fs/bpf/api_sentinel_day16_events`

## 3. Controlled HTTP probes

Two local HTTP requests were generated.

| Probe | Request | Observed result |
|---|---|---:|
| Health probe | `GET /healthz?day31_capture_probe=1` | HTTP 200 |
| Synthetic PII probe | `POST /__day31_capture_probe` | HTTP 404 |

The POST targeted a deliberately nonexistent endpoint. The 404 response was expected and avoided intentionally modifying application data.

The POST body contained synthetic test values only:
- Email: `day31.capture@example.test`
- Phone: `+1-202-555-0147`
- Card: `4111111111111111`
- Password: `DAY31-SYNTHETIC-PASSWORD`

## 4. Capture and ingestion evidence

The backend readiness endpoint reported:

- Overall status: `ready`
- Capture enabled: `true`
- Capture running: `true`
- Persistence worker running: `true`
- HTTP pipeline initialized: `true`

The queue-status and metrics endpoints were inspected at separate points in time. Their packet counters were therefore recorded as separate snapshots:

| Metric | Queue-status snapshot | API metrics snapshot |
|---|---:|---:|
| Accepted TCP events | 32 | 37 |
| Rejected packets | 0 | 0 |
| Dropped packets | 0 | 0 |
| Completed HTTP transactions | 3 | 3 |
| Persisted transactions | 3 | 3 |
| Persistence failures | 0 | 0 |

Additional API metrics from the later snapshot:

- TCP payload packets: 19
- TCP payload bytes: 1,913
- TCP payload delivered to HTTP: 19 packets / 1,913 bytes
- Persistence queue depth at inspection: 0
- Persistence rejected count: 0
- HTTP unmatched response count: 0
- Discovered endpoints: 3
- Transaction log rows: 3

The packet counters are operational snapshots, not a cumulative benchmark report.

## 5. Persistence and PII verification

The isolated Day 31 database contained three transaction records after the controlled probes.

A read-only SQL query located the specific synthetic POST:

| Field | Stored value |
|---|---|
| Transaction ID | `2` |
| Method | `POST` |
| URI | `/__day31_capture_probe` |
| Response status | `404` |

Assertions against this exact stored record passed:

- PII mask `***MASKED***` present in the request body.
- Credential marker `[REDACTED]` present for the password.
- Raw email, phone, card number, and password values absent from the inspected record.

The aggregate check also inspected all three persisted records:
- Records containing the PII mask: 3
- Records containing the credential-redaction marker: 1
- Raw synthetic values found: none

All test values were synthetic. The database was opened read-only for inspection.

## 6. Performance observations

These are small-sample observations from the controlled run, not repeatable performance benchmarks.

| Measurement | Samples | Observed result |
|---|---:|---:|
| HTTP message serialization | 8 | Average 348.639 µs; maximum 713.038 µs; 8/8 below 1 ms |
| HTTP transaction serialization | 3 | Average 426.551 µs; maximum 635.434 µs; 3/3 below 1 ms |
| Transaction processing latency | 3 | Average 0.638 ms; maximum 0.947 ms |
| Capture-to-publish latency | 7 | Average 2.533 ms; maximum 5.064 ms |
| Ring-buffer read-to-queue dispatch | 37 | Average 102.928 µs; 36/37 below 1 ms |

One ring-buffer dispatch sample exceeded 1 ms (maximum 1,216.557 µs). The sample does not support a claim that every capture-to-queue dispatch is below 1 ms.

The readiness snapshot reported process RSS of approximately 85.1 MB. Python `tracemalloc` was disabled.

## 7. Regression test evidence

The focused security and persistence test command completed successfully:

```text
73 passed in 5.34s
```

The selected test modules were:

- `tests/test_data_masking.py`
- `tests/test_async_transaction_store.py`
- `tests/test_transaction_store.py`
- `tests/test_transaction_websocket.py`
- `tests/test_message_broker.py`
- `tests/test_bola_detection.py`

This is regression evidence for the selected modules. It is not a substitute for the live capture demonstration or sustained-load testing.

## 8. Limitations and outstanding acceptance items

The following items remain unverified or incomplete:

1. **24-hour memory stability:** No 24-hour capture soak test was completed as part of this demonstration.
2. **Memory leak acceptance:** `tracemalloc` was disabled in the live run; no leak conclusion can be drawn from the RSS snapshot.
3. **Production protocol coverage:** The current Day 16 producer is scoped to IPv4 TCP. IPv6 and fragmented IPv4 packets are ignored. This demonstration used loopback traffic only.
4. **Sustained performance:** The serialization and latency samples are small and do not prove sustained throughput or the full set of performance targets.
5. **BOLA event in this demonstration:** The metrics snapshot showed zero BOLA detections and zero capture-to-detection events. The live run verified packet ingestion and persistence, not a successful BOLA alert.
6. **External acceptance:** No external team sign-off is recorded in this evidence.

## 9. Final status

| Acceptance area | Day 31 evidence status |
|---|---|
| eBPF producer loaded and attached to loopback | Passed |
| Ring-buffer reader connected | Passed |
| Local TCP packet ingestion observed | Passed |
| HTTP transaction reconstruction observed | Passed |
| Persistence worker saved completed transactions | Passed |
| Specific synthetic POST persisted | Passed |
| PII and password redaction verified in stored POST | Passed |
| Focused regression tests | Passed |
| 24-hour soak and memory stability | Not verified |
| Production-wide protocol coverage | Not verified |
| External team acceptance | Not recorded |

**Conclusion:** The controlled Day 31 live demonstration passed for local IPv4/TCP capture, HTTP transaction processing, database persistence, and verification of PII redaction before storage. Broader stability, performance, protocol-coverage, and external acceptance requirements remain open.
