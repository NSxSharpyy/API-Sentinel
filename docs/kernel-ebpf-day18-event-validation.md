# Day 18 — eBPF Event Validation

## Objective
Validate HTTP request event capture during repeated live traffic.

## Build Check
`cargo check` completed successfully. An unused workspace dependency warning for `clap` was reported.

## Test
Sent five HTTP GET requests to example.com using curl while API-Sentinel was running on ens33.

## Results
- Five HTTP_REQUEST GET events were observed in the provided loader output.
- Client identification was reported as client_id=1001.
- Traffic direction was reported as NORTH-SOUTH.
- TCP lifecycle events were observed.
- All displayed ring_buffer_dropped_events readings were zero.

## Limitations
This test did not verify backend ingestion, database persistence, dashboard delivery, or BOLA detection. It also did not force ring-buffer overflow.
