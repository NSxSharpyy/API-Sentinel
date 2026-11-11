# Zombie API Classification Logic

## Objective
Identify deprecated or inactive API endpoints that continue receiving runtime traffic.

## Classification Conditions
An endpoint is classified as a Zombie API when:

1. The endpoint exists in the official OpenAPI contract.
2. The observed HTTP method matches the declared method.
3. The operation is explicitly marked deprecated=true or inactive=true.
4. Runtime traffic is observed for that endpoint.

## Detection Workflow
Runtime Route
    |
    v
Match OpenAPI Path Template
    |
    v
Match HTTP Method
    |
    v
Check deprecated / inactive flag
    |
    v
Generate ZOMBIE_API Finding
    |
    v
Generate HIGH Severity Alert

## Path Matching
Dynamic OpenAPI parameters such as {id}, {userId}, and {orderId} match one non-empty path segment.

Example:
Declared: /api/v1/users/{id}
Observed: /api/v1/users/123
Result: MATCH

Static route segments must match exactly.

## Shadow API Distinction
Undocumented endpoints are ignored by ZombieAPIDetector.
They are classified separately by ShadowAPIDetector.

## Test Evidence
Synthetic test routes:
- GET /api/v1/legacy/users (deprecated=true)
- GET /api/v1/legacy/orders (inactive=true)

Runtime observations: 2
Zombie findings: 2
HIGH severity alerts: 2

Note: Results are from controlled synthetic testing, not production traffic.
