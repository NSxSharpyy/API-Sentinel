# Day 15 — HTTP Serialization Benchmark

## Purpose

Measure the latency of `serialize_http_message()` independently of
HTTP parsing, queue waiting, ZeroMQ delivery, and database persistence.

The acceptance threshold used for this benchmark is aggregate p95
serialization latency below 1 millisecond for each tested payload profile.

## Environment

- Python: 3.14.4
- Platform: Linux on WSL2
- Kernel reported by Python: 6.18.54.1-microsoft-standard-WSL2
- Serializer: `app.message_broker.serialize_http_message`
- Benchmark: `benchmarks/benchmark_http_serialization.py`
- Measurement clock: `time.perf_counter_ns()`

## Method

Each run used 300 warm-up calls, followed by 5 measured repetitions of
2,000 calls per payload size. Each measured call includes the full
`serialize_http_message()` invocation and the surrounding timing-clock
calls.

The serialized output size is calculated separately from the timed calls.
The test payloads are synthetic HTTP requests with fixed headers and a
fixed timestamp, with body sizes of 0, 1,024, 8,192, and 32,768 bytes.

The serializer converts the event dictionary to compact JSON, Base64-encodes
the body, formats the timestamp when present, and encodes the JSON as UTF-8.

## Results

| Body bytes | Output bytes | Run 1 median (µs) | Run 1 aggregate p95 (µs) | Run 2 median (µs) | Run 2 aggregate p95 (µs) |
|---:|---:|---:|---:|---:|---:|
| 0 | 494 | 4.820 | 5.336 | 4.741 | 5.302 |
| 1,024 | 1,873 | 8.104 | 8.870 | 8.072 | 9.162 |
| 8,192 | 11,429 | 28.864 | 33.567 | 28.732 | 33.191 |
| 32,768 | 44,198 | 100.008 | 127.214 | 100.474 | 157.764 |

Both benchmark invocations reported aggregate p95 below 1,000 microseconds
for all four synthetic payload profiles.

The second run's 32 KiB profile showed greater tail latency. Its fourth
repetition reported p95 of 204.438 microseconds, although that individual
repetition remained below the 1 ms threshold.

## Validation evidence

- Python syntax compilation of the benchmark script succeeded.
- Existing message-broker tests: 14 passed.
- Full test suite after the second benchmark: 167 passed, with one
  Starlette deprecation warning.
- `git diff --check` passed.

## Measurement boundaries and limitations

These results measure serialization only. They do not establish queue-wait
latency, queue saturation behavior, ZeroMQ delivery latency, persistence
latency, total request-processing latency, or production throughput.

Payloads are synthetic and use a limited set of request profiles. The
timing samples include the overhead of calling the performance clock around
each serializer call. Measurements are specific to the reported Python and
WSL2 environment and have not been established under concurrent production
load.

The sub-millisecond result is supported for the tested serialization
profiles, not for the entire backend pipeline.

## Day 15 status

Serialization threshold: demonstrated in two benchmark invocations for
the four tested synthetic payload sizes.

Queue latency audit: outstanding.

Overall Day 15: partial until queue latency is measured and documented.
