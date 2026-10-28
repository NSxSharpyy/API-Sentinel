# Day 17 — Live HTTP Traffic Validation

## Objective
Verify that API-Sentinel captures TCP lifecycle events and HTTP requests during live traffic.

## Test
Sent an HTTP GET request to example.com using curl while API-Sentinel was running on ens33.

## Results
- TCP lifecycle events were observed.
- HTTP GET request event was observed.
- Client identification was verified as client_id=1001.
- Traffic direction was reported as NORTH-SOUTH.
- All displayed ring_buffer_dropped_events metric readings were zero.

## Conclusion
Live TCP and HTTP event capture was observed successfully.

## Limitations
This test did not verify backend ingestion, database persistence, dashboard delivery, or BOLA anomaly detection.
