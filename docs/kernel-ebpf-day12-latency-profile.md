# API-Sentinel — Day 12 Latency Profile

## Objective

Measure the average execution time of the API-Sentinel
in-kernel HTTP classifier using BPF program runtime counters.

## Test Environment

- Interface: ens33
- BPF program ID: 60
- Program: api_sentinel_http_classifier
- Test traffic: 20 HTTP requests using curl
- Destination: 91.189.91.58:80

## Counter Measurements

| Metric | Before | After |
|---|---:|---:|
| Run count | 129 | 249 |
| Runtime (ns) | 565497 | 1040018 |

## Calculations

Runtime delta:

1,040,018 - 565,497 = 474,521 ns

Run-count delta:

249 - 129 = 120 executions

Average execution time:

474,521 / 120 = 3,954.34 ns

Average = approximately 3.95 microseconds.

## Result

The measured average execution time was below the
project's 100-microsecond target for this sample.

## Limitations

- The run counter measures classifier executions,
  not the number of HTTP requests.
- Background packets may affect the counters.
- This average does not establish worst-case latency.
- The measurement covers the HTTP classifier only;
  it does not establish the latency of every BPF program.
- A repeated controlled test would improve confidence.
