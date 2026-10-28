# API-Sentinel Vulnerability Register

## Lab Scope

API-Sentinel is a local security testing lab for learning and validating
API authorization controls. The intentionally vulnerable endpoint must
remain restricted to localhost and authorized testing.

## VULN-001: Broken Object Level Authorization (BOLA)

- **Affected service:** Billing
- **Endpoint:** GET /api/v2/billing/invoices/{invoice_id}
- **Category:** Broken Object Level Authorization (BOLA)
- **Severity:** High for a real system; this is an intentional lab weakness
- **Authentication:** Required

### Description

The billing endpoint verifies that a request has a valid bearer token,
but does not verify that the requested invoice belongs to the authenticated
user. An authenticated user may therefore change the invoice ID in the URL
and retrieve another user's invoice.

### Local reproduction

1. Start the services using `sudo docker compose up -d`.
2. Log in as Alice using the local test credentials.
3. Save the returned bearer token.
4. Request Alice's invoice using that token.
5. Request invoice ID 3 using the same token. Invoice 3 belongs to Bob.
6. Compare the responses and review the billing service logs.

Example login request:

    curl -sS -X POST http://127.0.0.1:5001/api/v2/auth/login \
      -H 'Content-Type: application/json' \
      -d '{"username":"alice","password":"Password123!"}'

Use the token returned by the login response:

    curl -i http://127.0.0.1:5004/api/v2/billing/invoices/3 \
      -H 'Authorization: Bearer YOUR_TOKEN_HERE'

### Expected lab result

The intentionally vulnerable billing endpoint returns invoice 3 even
though the authenticated user is Alice and the invoice belongs to Bob.
The response and structured logs should identify the requester and invoice
owner, including the cross-user access ground-truth flag.

### Secure control group

The order service checks resource ownership. An attempt by Alice to access
Bob's order should return 404 rather than expose the order.

### Mitigation

- Enforce object-level authorization on every invoice lookup.
- Compare the invoice owner with the authenticated user, or apply a
  policy that explicitly grants access.
- Deny unauthorized requests without disclosing protected invoice data.
- Add automated tests for cross-user access attempts.
- Log authorization failures and monitor suspicious object-ID enumeration.

### Safety

This vulnerability is intentional for local, authorized testing only.
Do not expose the vulnerable billing endpoint to public or untrusted
networks.
