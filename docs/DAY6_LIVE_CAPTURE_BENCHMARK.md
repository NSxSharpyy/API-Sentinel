# Day 6 — Live WSL Capture Acceptance Test

The synthetic benchmark measures parser/correlator/serialization behavior only.
This run measures a controlled loopback workload through the actual capture
loader, ring-buffer reader, raw packet queue, TCP/HTTP pipeline and persistence
worker. It is not a physical NIC line-rate benchmark.

## Safe test prerequisites

- Run only in the WSL development lab on `lo` and `127.0.0.1`.
- Confirm the Day 16 BPF loader ABI matches the installed ring-buffer reader.
- Ensure no other load test is running.
- Keep Day 17 packet-drop enforcement disabled for this test. This benchmark
  makes only GET requests to `/` and `/queue-status`; it does not create BOLA
  events or block addresses.
- The capture program must already be attached to loopback and the FastAPI
  service must report `capture_running: true`.

Follow the setup and stop order in `ebpf-day16/README.md`: start the producer
first, then the backend; stop the backend before stopping the producer.

## Run

From WSL, with the project virtual environment active, find the Uvicorn PID:

```bash
ps -eo pid,ppid,args | grep -E '[u]vicorn.*app.main:app'
```

Use the PID of the process serving requests. With `--reload`, include both the
worker and reloader PID in the benchmark if you want aggregate RSS sampling.

```bash
python benchmarks/benchmark_live_capture.py \
  --base-url http://127.0.0.1:8001 \
  --requests 500 \
  --concurrency 8 \
  --pid <UVICORN_PID>
```

The benchmark reports request latency percentiles, actual persisted-transaction
rate, capture/queue/persistence counter deltas, and sampled RSS growth. It fails
if requests fail, capture stops, transactions do not drain, queue/worker failure
counters increase, or RSS growth exceeds the configured limit (128 MiB by
default). Rejected/dropped packets during a run indicate the configured load
exceeded the current queue/capture capacity and must not be hidden in the report.

## Acceptance interpretation

- A zero-drop, zero-failure run with the expected transaction count and stable
  RSS is evidence for this controlled loopback workload.
- Repeat at increasing request counts/concurrency and record every result; a
  single run is not evidence of stable performance.
- A loopback WSL test cannot prove physical NIC line rate. If the assignment
  requires literal line-rate capture, that acceptance test must run on an
  appropriately provisioned Linux host/interface and include hardware/kernel
  capture-drop telemetry.
