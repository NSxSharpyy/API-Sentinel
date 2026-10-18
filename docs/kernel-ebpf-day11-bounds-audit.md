# API-Sentinel — Day 11 Bounds Audit

## Scope
Review of the eBPF packet parser, fixed-size reads, URI loop,
client identifier map lookup, and Ring Buffer event output.

## Source checks
- IPv4 declared total-length and fragmentation checks are present.
- IPv4 and TCP header lengths have explicit bounds.
- Payload offset and available packet length are checked.
- URI extraction uses a fixed 16-byte bounded loop.
- Client identifier lookup and typed Ring Buffer output are present.

## Runtime evidence
- Build completed successfully after the bounds changes.
- HTTP GET detection was observed with client_id=1001.
- HTTP HEAD detection was observed with client_id=1001.

## Limitations
- The parser inspects individual packets; TCP stream reassembly is not implemented.
- IPv4 fragments are skipped rather than reassembled.
- The current parser requires a 64-byte payload prefix, so shorter segments
  may not be inspected.
- HTTPS payload decryption is not implemented.
- These checks are not proof that every possible packet is verifier-safe;
  kernel loading and runtime tests remain important.

## Status
Source markers, build, and the recorded GET/HEAD tests have been checked.
Review the final diff before committing.
