# Day 25: Plaintext PII Leakage Inspection

## 1. Executive summary

The Day25 controlled audit completed successfully using 50 deterministic synthetic
PII test payloads generated for Day24.

The inspection recorded **202 marker/location matches** across API responses and
SQLite fields. These are grouped observations, not 202 distinct exposed values.

The audit demonstrated:
- PII payloads returned by authenticated API responses.
- Cross-user invoice access through the authenticated invoice endpoint.
- Invoice data returned by a legacy endpoint without authentication.
- Synthetic PII stored in plaintext SQLite fields.
- No synthetic payload matches in the inspected service-log sample.

All inserted audit records were removed. The final cleanup check reported zero
remaining audit customers, orders, and invoices.

All test values were synthetic. No real customer PII was intentionally inserted
or used by this audit.

## 2. Objective

Inspect controlled synthetic PII across:
1. API response bodies.
2. Selected SQLite fields at rest.
3. Recent Docker service logs.

This task was an inspection exercise. It did not implement application
remediation or encryption changes.

## 3. Methodology

The scanner loaded the Day24 fixture containing 50 deterministic synthetic
payloads across five categories:
- Credit-card test values.
- SSN test values.
- Bearer-token test strings.
- Email addresses.
- Phone numbers.

A dedicated audit customer, order, and invoice were inserted using reserved
audit identifiers after checking for identifier collisions.

The scanner then:
- Authenticated as the dedicated audit account.
- Authenticated as a separate seeded account for the cross-user access check.
- Requested the audit profile and invoice API responses.
- Requested the invoice using a different authenticated account.
- Requested the legacy invoice route without an authorization token.
- Queried the audit customer's email and invoice fields in SQLite.
- Inspected the latest 1,000 log lines from each of four services.
- Removed the exact audit invoice, order, and customer records.

Session tokens were held in memory and were not written to the report.

## 4. Results

### 4.1 API response inspection

All four API checks returned HTTP 200 and passed their expected-status checks.

| API check | Authentication | HTTP status | Payload matches |
|---|---|---:|---:|
| Audit profile | Audit account | 200 | 1 |
| Audit invoice | Audit account | 200 | 50 |
| Foreign invoice | Different seeded account | 200 | 50 |
| Legacy invoice | None | 200 | 50 |
| **Total** | | | **151** |

The foreign-invoice result demonstrates that a different authenticated account
could retrieve the audit invoice. This is evidence of cross-user invoice access
for the tested request.

The legacy route returned the invoice without an authorization token. This is
evidence of unauthenticated access for the tested request.

### 4.2 Database inspection

The scanner queried the dedicated audit records while they existed.

| Database field | Record | Payload matches |
|---|---|---:|
| `customers.email` | Audit customer | 1 |
| `invoices.billing_address` | Audit invoice | 50 |
| `invoices.card_last4` | Audit invoice | 0 |
| **Total** | | **51** |

The invoice's `billing_address` field contained the serialized synthetic
payload collection. The `card_last4` field was also inspected; no complete
fixture payload matched that field. This does not mean the field is suitable
for storing full payment-card data.

SQLite reported journal mode `delete`, and the database WAL file was absent at
the time of inspection. WAL file contents and raw database disk blocks were
not scanned.

### 4.3 Service-log inspection

| Service | Latest lines inspected |
|---|---:|
| Auth | 1,000 |
| User | 1,000 |
| Order | 1,000 |
| Billing | 1,000 |
| **Total** | **4,000** |

- Log inspection completed successfully.
- Synthetic payload matches: **0**.

This result applies only to the latest 1,000 lines inspected per service. It
does not establish that all historical logs are free of sensitive data.

### 4.4 Findings by category

| Category | Recorded matches |
|---|---:|
| Credit cards | 40 |
| SSNs | 40 |
| Bearer tokens | 40 |
| Emails | 42 |
| Phone numbers | 40 |
| **Total** | **202** |

The 202 total is a count of marker/location matches. The same synthetic value
can be observed in more than one location, so this must not be interpreted as
202 unique PII values.

### 4.5 Findings by location

| Location | Recorded matches |
|---|---:|
| Audit profile API response | 1 |
| Authenticated audit invoice API response | 50 |
| Foreign authenticated invoice API response | 50 |
| Unauthenticated legacy invoice API response | 50 |
| `customers.email` | 1 |
| `invoices.billing_address` | 50 |
| Service logs | 0 |
| **Total** | **202** |

## 5. Security impact

The test results identify the following risks:

1. **Excessive data exposure:** Invoice responses included the full synthetic
   payload collection placed in the billing-address field.
2. **Broken object-level authorization:** A separate authenticated account
   could retrieve the audit invoice through the tested invoice endpoint.
3. **Unauthenticated legacy access:** The tested legacy invoice route returned
   the invoice without an authorization token.
4. **Plaintext storage:** Synthetic PII values were retrievable from the
   inspected SQLite customer and invoice fields.

These observations demonstrate risks in the tested application paths. They
do not establish that real customer records were exposed during this audit.

## 6. Cleanup and data safety

The audit used dedicated identifiers:
- Customer ID: `9001`
- Username: `pii-audit-9001`
- Order ID: `99001`
- Invoice ID: `99001`

The final cleanup report recorded:

| Record type | Deleted | Remaining |
|---|---:|---:|
| Customer | 1 | 0 |
| Order | 1 | 0 |
| Invoice | 1 | 0 |

An independent database verification also confirmed that the three audit
records were absent after cleanup.

The report contains marker, category, location, and match-count metadata.
It does not contain raw fixture payload values.

## 7. Recommendations

1. Enforce object ownership checks on every invoice read. Return an appropriate
   authorization error when the requesting user does not own the invoice.
2. Remove the legacy invoice route if it is no longer required, or protect it
   with authentication and the same ownership authorization as the current API.
3. Use explicit response schemas and return only fields required by the caller.
   Do not serialize free-text billing fields containing unrelated sensitive data.
4. Minimize sensitive data collection and avoid placing unrelated PII or
   credentials in free-text database fields.
5. Apply appropriate encryption and access controls to sensitive data at rest.
6. Mask sensitive values in responses wherever full values are not operationally
   necessary.
7. Continue log-redaction testing and ensure request/response bodies and
   credentials are not written to application logs.
8. Add regression tests for cross-user invoice access and unauthenticated
   legacy-route access.

These are recommendations for subsequent remediation work; they were not
implemented as part of this inspection task.

## 8. Scope limitations

- API response bodies were inspected; this was not a packet capture.
- SQLite fields were queried; raw disk blocks were not scanned.
- Only the latest 1,000 lines per selected service were inspected.
- WAL presence and journal mode were recorded; WAL bytes were not separately
  scanned.
- The audit used synthetic fixture data and a dedicated temporary customer,
  order, and invoice.
- The findings describe the tested application behavior and audit environment.
  They are not proof that production customer data was exposed.

## 9. Final status

**Day25 audit status: COMPLETE**

- Synthetic payloads tested: 50
- Recorded marker/location matches: 202
- API checks: 4 passed
- Database inspection: passed
- Service logs: 4,000 lines inspected, 0 payload matches
- Cleanup: complete, 0 audit records remaining
- Raw fixture values in report: none

The machine-readable evidence is stored in
`appsec-testing/logs/pii_leakage_report.json`.
