# Day 13 — Throughput and Response-Time Impact Verification

## Objective
Compare HTTP response time with API-Sentinel monitoring enabled and disabled.

## Environment
- OS: Ubuntu 24.04 VM
- Interface: ens33
- Test endpoint: http://example.com/
- Requests per condition: 5
- Response size: 577 bytes per request

## Results

| Metric | Monitoring ON | Monitoring OFF |
|---|---:|---:|
| Average response time | 204.231 ms | 215.275 ms |
| Minimum | 115.121 ms | 99.139 ms |
| Maximum | 392.351 ms | 551.794 ms |
| Bytes per response | 577 | 577 |

## Conclusion
The five-run sample did not show higher average response time with monitoring enabled. However, the external endpoint and network variability affect the results. This is a preliminary HTTP response-time comparison, not a controlled throughput benchmark. No claim of zero overhead or improved throughput can be made from these results.

## Limitations
- Small sample size.
- External network and server latency can vary.
- No dedicated throughput measurement was performed.
- A controlled local or repeatable network benchmark is needed to estimate monitoring overhead reliably.
