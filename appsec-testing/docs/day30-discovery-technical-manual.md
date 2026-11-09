# Day 30 — Discovery Technical Manual

## 1. Overview

This manual documents API-Sentinel's discovery-related implementation, based on the source modules reviewed during Day 30.

The documented components are:
- Dynamic OpenAPI schema generation
- Contract diffing
- Live Shadow API discovery
- OpenAPI specification export
- Runtime parameter drift detection

The objective is to compare observed runtime API behavior with the officially documented API contract and identify endpoints or payload fields that require security review.

## 2. Dynamic OpenAPI Schema Generation

Source: `src/schema_generator.py`

### 2.1 Purpose

The dynamic schema generator builds OpenAPI 3.0-compatible schemas from observed JSON request and response payloads.

### 2.2 Schema inference

The `infer_schema()` function maps Python values to schema types:

| Python value | Inferred schema |
|---|---|
| `None` | `nullable: true` |
| Boolean | `type: boolean` |
| Integer | `type: integer` |
| Float | `type: number` |
| String | `type: string` |
| List | `type: array` with inferred items |
| Dictionary | `type: object` with properties |

For dictionaries, the inferred schema includes a `properties` object and initially marks all observed properties as required.

### 2.3 Schema merging

The `merge_schemas()` function merges schemas from multiple observations.

- Empty schemas are handled by returning a copy of the other schema.
- Type mismatches return an empty schema.
- Object properties are merged using the union of property names.
- Object required fields are merged using the intersection of required keys.
- Array item schemas are recursively merged.
- For matching scalar types, the first schema is retained.

### 2.4 OpenAPI generation

The `generate_openapi_spec()` function:
1. Normalizes the HTTP method to uppercase.
2. Validates the method against supported HTTP methods.
3. Normalizes the endpoint path.
4. Infers request and response schemas.
5. Merges schemas when repeated observations exist.
6. Generates an OpenAPI 3.0.0 specification.

The generated specification uses the title `API-Sentinel Dynamic API` and version `1.0.0`.

The `merge_observed_endpoint()` helper appends an observed endpoint containing its method, path, response, and optional request payload.

### 2.5 Limitations

- Empty arrays produce an unconstrained item schema.
- Incompatible schema types result in `{}`.
- Inferred required properties are based on observed payloads and may not represent every valid request.
- Generated response operations use a default HTTP 200 response.

## 3. Contract Diffing Algorithm

Source: `src/contract_differ.py`

### 3.1 Purpose

The `ContractDiffEngine` compares route sets extracted from the official OpenAPI contract and a live-generated specification.

### 3.2 Route extraction

Routes are represented as `(HTTP method, path)` pairs. The engine extracts supported HTTP operations from the `paths` object.

### 3.3 Comparison operations

Let:
- `O` = official routes
- `L` = live routes

The engine calculates:

| Result | Algorithm | Meaning |
|---|---|---|
| Live-only | `L - O` | Routes observed in the live specification but absent from the official contract |
| Official-only | `O - L` | Routes documented officially but absent from the live specification |
| Common | `O ∩ L` | Routes present in both specifications |
| Zombie | Deprecated official routes intersected with live routes | Deprecated routes that remain present in the live specification |

The `diff()` method returns summary counts and detailed differences.

### 3.4 Route classification helper

The `compare_route_to_contract()` function returns:
- `OFFICIAL_API`
- `SHADOW_API`
- `ZOMBIE_API`

A route absent from the official contract is classified as `SHADOW_API`. A matching path containing a deprecated HTTP operation is classified as `ZOMBIE_API`.

### 3.5 Limitations

- Contract diffing compares route identity, not request or response schema compatibility.
- `compare_route_to_contract()` matches by path and checks deprecated operations at that path; it does not receive a specific HTTP method.
- A route marked deprecated is considered zombie only when it is also present in the live route set in `diff_routes()`.

## 4. Live Shadow API Discovery

Source: `src/live_discovery.py`

### 4.1 Purpose

The `LiveShadowDiscovery` class classifies observed runtime routes against the official API contract.

### 4.2 Input formats

The route normalizer supports:
- String: `/users`
- Tuple: `("GET", "/users")`
- Dictionary: `{"method": "GET", "route": "/users"}`
- Dictionary: `{"method": "GET", "path": "/users"}`

### 4.3 Matching logic

The discovery engine:
1. Extracts declared routes from the official contract.
2. Normalizes the observed method and path.
3. Compares observed routes against declared routes.
4. Supports OpenAPI path parameters such as `/users/{id}`.
5. Classifies the observed route.

Classification:

| Condition | Status |
|---|---|
| No matching contract route | `SHADOW_API` |
| Matching route marked deprecated or inactive | `ZOMBIE_API` |
| Matching active, non-deprecated route | `OFFICIAL_API` |

### 4.4 Discovery filters and risk scoring

The class provides:
- `discover_shadow_apis()` — returns Shadow API findings only.
- `discover_zombie_apis()` — returns Zombie API findings only.
- `discover_with_risk_scoring()` — attaches endpoint risk scores through `EndpointRiskScorer`.

### 4.5 Limitations

- Invalid observed route inputs are skipped during discovery.
- String-only route input does not include a method; matching can therefore ignore HTTP method.
- Route matching is based on path segments and does not validate request or response schemas.
- Deprecated or inactive status is recognized when its value is exactly `True`.

## 5. OpenAPI Specification Export

Source: `src/openapi_exporter.py`

### 5.1 Purpose

The `OpenAPIExporter` converts discovered routes into an OpenAPI specification.

### 5.2 Export behavior

- Uses OpenAPI version `3.0.3`.
- Default title: `API-Sentinel Generated API`.
- Default version: `1.0.0`.
- Normalizes methods to lowercase.
- Ensures paths begin with `/`.
- Adds a default `200 Successful response` operation.
- Skips routes with empty method or path values.

The `export()` method returns a specification dictionary.

The `export_json()` method writes the specification to a JSON file using indentation of two spaces.

### 5.3 Limitations

The reviewed exporter generates basic route definitions. It does not export request or response schemas, authentication requirements, parameters, or observed HTTP status codes.

## 6. Runtime Parameter Drift Detection

Source: `src/parameter_drift.py`

### 6.1 Purpose

The parameter drift detection engine compares observed runtime request and response JSON payloads with schemas in the official OpenAPI specification.

Only officially documented endpoints are evaluated.

### 6.2 Path normalization and matching

- Query strings are removed.
- Paths are normalized to begin with `/`.
- Trailing slashes are removed except for the root path.
- OpenAPI path parameters are converted into regex segments.
- Matching uses the HTTP method and normalized path.

### 6.3 Schema extraction

The module extracts JSON schemas from `application/json` content for:
- Request bodies
- Successful responses (2xx status codes or `2XX`)

Local OpenAPI component references beginning with `#/` are resolved.

### 6.4 Undocumented field detection

The `find_undocumented_fields()` function recursively inspects observed JSON objects.

If an observed field is not present in the official schema's `properties`, a finding is generated with:
- Field path
- Location (`request` or `response`)
- Drift type (`undocumented_field`)

Findings are returned with the status `needs_review`.

### 6.5 Output summary

The detection result contains:
- `total_runtime_events_checked`
- `total_drift_findings`
- `undocumented_request_fields`
- `undocumented_response_fields`
- Detailed findings

### 6.6 Limitations

- Undocumented fields are reported for review; they are not automatically confirmed vulnerabilities.
- The reviewed function does not report missing required fields.
- It does not perform full type validation for observed fields.
- Events without the relevant payload or without a matching official operation are skipped.
- The comparison focuses on undocumented JSON fields.

## 7. Integrated Discovery Workflow

The reviewed modules support the following conceptual workflow:

1. Collect observed runtime endpoint and payload information.
2. Infer dynamic schemas from observed JSON payloads.
3. Generate a live OpenAPI specification.
4. Export discovered routes into OpenAPI format where required.
5. Compare live routes against the official API contract.
6. Classify observed endpoints as official, shadow, or zombie.
7. Compare documented request and response payload schemas against runtime payloads.
8. Produce findings for security review.
9. Apply endpoint risk scoring through the discovery risk-scoring integration when used.

This workflow describes the relationship among the reviewed modules. It does not assert that every component is automatically orchestrated in a single runtime pipeline.

## 8. Security Interpretation

- Shadow API findings identify observed routes that are not represented in the official contract.
- Zombie API findings identify routes associated with deprecated or inactive contract operations that remain observed.
- Parameter drift findings identify observed JSON fields absent from documented schemas.
- Findings should be validated before being treated as confirmed vulnerabilities.
- Discovery results should be reviewed in the context of authorization, business logic, exposure, and operational requirements.

## 9. Source Modules Reviewed

| Module | Responsibility |
|---|---|
| `src/schema_generator.py` | Dynamic schema inference, merging, and OpenAPI generation |
| `src/contract_differ.py` | Official/live route comparison and classification |
| `src/live_discovery.py` | Runtime route classification and optional risk scoring |
| `src/openapi_exporter.py` | Export discovered routes to OpenAPI JSON |
| `src/parameter_drift.py` | Runtime request/response undocumented field detection |

## 10. Conclusion

API-Sentinel's reviewed discovery modules provide a foundation for identifying undocumented endpoints, observing deprecated or inactive APIs, generating OpenAPI specifications from runtime observations, and detecting undocumented JSON fields.

The discovery outputs are intended to support security assessment and review. Their results must be validated against the actual target environment and the intended API contract before final risk conclusions are made.
