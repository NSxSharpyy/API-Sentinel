# Day 23 — Blocklist Regression Test

**Date:** 2026-11-01  
**Role:** M1 — Kernel & eBPF Engineer  
**Environment:** Ubuntu 24.04 VMware, isolated network namespace and veth pair  
**Branch:** kernel-ebpf

## 1. Objective

Validate that the API-Sentinel eBPF classifier:

- Drops packets destined for a blocklisted IPv4 address.
- Drops packets originating from a blocklisted IPv4 address.
- Allows traffic when neither source nor destination IP is blocklisted.
- Increments the BLOCKLIST_DROPS per-CPU counter.
- Uses an isolated test interface without modifying ens33.

## 2. Test Environment

| Component | Configuration |
|---|---|
| Host interface | as-test-host |
| Host IP | 10.20.20.1/24 |
| Network namespace | apisentinel-test |
| Namespace interface | as-test-peer |
| Blocklisted destination | 10.20.20.2 |
| Allowed destination | 10.20.20.3 |

The namespace peer interface was configured with both 10.20.20.2 and 10.20.20.3.

## 3. Build Verification

Command:

    cd ~/API-Sentinel-team/api-sentinel-ebpf
    cargo build

Result: Userspace and eBPF components built successfully.

A non-blocking unused workspace dependency warning for clap was observed.

## 4. Test Mode and Safety

The application was started with:

    API_SENTINEL_TEST_MODE=1
    API_SENTINEL_INTERFACE=as-test-host
    API_SENTINEL_BLOCKLIST_IP=10.20.20.2
    cargo run -p api-sentinel-ebpf

Observed:

- Test mode enabled.
- Interface restricted to as-test-host.
- Global tracepoint and kprobe attachments disabled.
- clsact configured on the isolated interface.
- HTTP classifier attached to as-test-host egress.
- Client identifier map verified.
- Blocklist read-back verified.

TCX attachment was also verified using bpftool net.

## 5. Test Case 1 — Destination IP Blocking

Configured blocklisted destination: 10.20.20.2

Command:

    ping -I as-test-host -c 5 -W 1 10.20.20.2

Observed:

- 5 packets transmitted.
- 0 packets received.
- 100% packet loss.
- sendmsg: No buffer space available.

BLOCKLIST map contained the entry for 10.20.20.2 with value 1.

BLOCKLIST_DROPS observed values:

- CPU 0: 2
- CPU 1: 10
- Total observed: 12

Result: PASS

Note: Counter was not captured immediately before and after the five ping attempts. Therefore, 12 is the observed counter total, not an exact count of those five attempts.

## 6. Test Case 2 — Allowed IP Traffic

Allowed destination: 10.20.20.3

Command:

    ping -I as-test-host -c 3 -W 1 10.20.20.3

Observed:

- 3 packets transmitted.
- 3 packets received.
- 0% packet loss.

BLOCKLIST_DROPS remained unchanged:

- CPU 0: 2
- CPU 1: 10
- Total: 12

Result: PASS

Allowed traffic passed without an observed increase in the blocklist drop counter.

## 7. Test Case 3 — Source IP Blocking

The application was restarted with source IP 10.20.20.1 configured as the blocklisted IP.

Configuration:

    API_SENTINEL_TEST_MODE=1
    API_SENTINEL_INTERFACE=as-test-host
    API_SENTINEL_BLOCKLIST_IP=10.20.20.1
    cargo run -p api-sentinel-ebpf

Observed:

- Test mode enabled.
- Interface restricted to as-test-host.
- Classifier attached to test-interface egress.
- Client identifier map verified.
- Blocklist read-back verified for 10.20.20.1.

Ping command:

    ping -I as-test-host -c 5 -W 1 10.20.20.3

Observed:

- 5 packets transmitted.
- 0 packets received.
- 100% packet loss.
- sendmsg: No buffer space available.

BLOCKLIST_DROPS map ID: 26

Observed per-CPU values:

- CPU 0: 5
- CPU 1: 2
- Total: 7

Result: PASS

The source IP was configured as blocklisted. Traffic to the otherwise allowed peer was dropped, and the drop counter recorded 7 events.

## 8. Regression Test Summary

| Test | Expected | Observed | Result |
|---|---|---|---|
| Blocklisted destination | Drop | 100% packet loss | PASS |
| Allowed destination | Allow | 3/3 replies | PASS |
| Blocklisted source | Drop | 100% packet loss | PASS |
| BLOCKLIST_DROPS | Increment | Non-zero values observed | PASS |
| Interface isolation | Use test interface | as-test-host | PASS |

## 9. Evidence Notes

- BLOCKLIST_DROPS is a per-CPU array.
- Destination test observed total counter value 12.
- Allowed traffic passed and the observed counter remained unchanged.
- Source test observed total counter value 7.
- EVENT_DROPS and BLOCKLIST_DROPS are separate counters.
- Ping failure and counter evidence are consistent with TC_ACT_SHOT behavior.
- ens33 was not used as the test interface.

## 10. Conclusion

Day 23 isolated blocklist regression tests completed successfully.

Destination-IP blocking, source-IP blocking, allowed traffic forwarding, and BLOCKLIST_DROPS accounting were verified.

Overall result: PASS
