# PII Test Payload Register — Day 24

## Purpose

This register documents the synthetic, format-valid test payload library
used by Day 25's data-sanitization leakage audit.

The library is generated deterministically and contains no real personal
information or functional credentials.

## Categories and safety basis

| Category | Count | Safety basis |
|---|---:|---|
| Credit cards | 10 | Published payment-processor test numbers; Luhn-valid |
| SSN-shaped values | 10 | Invalid SSA 900-series area numbers; never validly issued SSNs |
| Bearer tokens | 10 | Random opaque token-shaped strings; synthetic and nonfunctional |
| Emails | 10 | `example.test` reserved test domain |
| Phone numbers | 10 | NANP fictional `555-0100`–`555-0199` range |

## Payload file

`appsec-testing/data/pii_test_payloads.json`

Each payload has a unique marker, such as `PII-TEST-CARD-003`, and a
separate value field. Day 25 can use the marker to identify the record and
search for the corresponding value in responses, logs, and database
contents.

## Regeneration

From the `appsec-testing` directory:

    python scripts/compliance/pii_payload_generator.py

The generator uses a fixed seed and fixed test-card fixtures. The output
contains no generation timestamp, so repeated runs produce byte-identical
JSON.

## Format validity and safety

- Card values use published processor test fixtures and pass Luhn checks.
- SSN-shaped values match `###-##-####`, but use invalid 900-series area
  numbers. They are not valid SSNs and are not described as an SSA testing
  allocation.
- Bearer-token-shaped values are randomly generated and are not accepted
  credentials.
- Emails use the reserved `.test` domain.
- Phone numbers use the fictional NANP 555-01xx range.

Format validity helps exercise sanitization patterns. Synthetic values
reduce the risk of introducing real personal information into test
systems.

## Scope

Day 24 performs payload generation only. It does not send requests to
services, inspect logs, scan responses, or query databases. Those leakage
checks belong to Day 25.
