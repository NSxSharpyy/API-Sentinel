# Results and Evidence

## 1. Overview
The API-Sentinel security assessment project evaluates API endpoints using OpenAPI specifications and runtime traffic logs. The testing focuses on identifying Shadow APIs and Zombie APIs.

## 2. Observed Traffic OpenAPI Generation
The system processed 364 runtime traffic events.

Results:
- Total runtime events processed: 364
- Unique HTTP method-route pairs: 7
- Generated OpenAPI file: reports/observed_openapi.json

The generated schema provides an inventory of API routes observed during runtime testing.

## 3. Shadow API Detection
Shadow API detection was evaluated using the approved API inventory.

Results:
- Shadow API findings: 7
- Risk classification: HIGH
- OWASP API9 findings related to Shadow APIs: 7

Shadow APIs are endpoints observed in runtime traffic but not present in the approved API inventory.

## 4. Zombie API Detection
Controlled synthetic traffic was used to validate Zombie API detection.

Test endpoints:
- GET /api/v1/legacy/users
- GET /api/v1/legacy/orders

Test configuration:
- /api/v1/legacy/users: deprecated=true
- /api/v1/legacy/orders: inactive=true

Results:
- Runtime observations: 2
- Zombie API findings: 2
- HIGH severity alerts: 2
- OWASP API9 Zombie findings: 2

## 5. Parameter Drift Testing
Parameter drift analysis was executed against runtime traffic.

Synthetic Zombie test run:
- Runtime events checked: 2
- Parameter drift findings: 0

## 6. Evidence Files
The project contains the following evidence artifacts:

- observed_openapi.json
- zombie_alerts.json
- owasp_api9_findings.json
- api_inventory.json
- api_inventory.csv
- zombie_classification_logic.md

## 7. Conclusion
API-Sentinel demonstrated the ability to generate an observed OpenAPI schema from runtime traffic and identify Shadow API and Zombie API findings in controlled test scenarios.

The Zombie API results were validated using synthetic test traffic. These findings should not be interpreted as confirmed vulnerabilities in a production environment.
