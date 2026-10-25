# API v1 and Alerting Guide

## API routes

FastAPI generates the OpenAPI schema from registered routes.

### GET /api/v1/endpoints

Lists discovered endpoints.

| Parameter | Default | Constraint |
|---|---:|---|
| limit | 50 | 1–100 |
| offset | 0 | 0 or greater |

The response contains `items`, `total`, `limit` and `offset`.
Endpoint items include `id`, `host`, `method`, `path`, `first_seen`
and `last_seen`.

Example:

    curl "http://127.0.0.1:8001/api/v1/endpoints?limit=20&offset=0"

### GET /api/v1/alerts

Lists persisted security incidents. Supports `limit`, `offset`, and
optional exact-match `severity` and `status` filters.

Each item follows the shared `SecurityIncidentSchema`:

| Field | Meaning |
|---|---|
| `incident_id` | Persisted incident ID |
| `detected_at` | Incident detection timestamp |
| `severity` | Assigned severity |
| `title` | Incident title |
| `description` | Optional explanation |
| `source_ip` | Optional source IP |
| `transaction_id` | Optional related transaction |
| `endpoint_id` | Optional related endpoint |
| `status` | Incident status |

The database attribute remains `id`; the shared schema maps it to
`incident_id`. No database migration is required for this mapping.

Completed transaction persistence also upserts `DiscoveredEndpoint` using a
normalized Host header, uppercase method, and URL path. Query parameters are
preserved in the transaction log but excluded from endpoint identity, so
`/users?page=1` and `/users?page=2` map to the same `/users` endpoint. The
transaction and any BOLA incident reference the endpoint row when one can be
identified.

Example:

    curl "http://127.0.0.1:8001/api/v1/alerts?severity=high&status=open&limit=20"

### GET /api/v1/metrics

Returns runtime snapshots grouped as:

- `ingestion`: queue depths, packet counters and capture state.
- `persistence`: queue depth and persisted, failed and rejected counts.
- `processing`: completed transactions and processing-latency metrics.
- `detection`: BOLA detector metrics when initialized.
- `alerts`: alert-bus counters and total/open incident counts.
- `database`: endpoint, transaction and incident record counts.

These are current snapshots, not durable time-series metrics.

### WebSocket `/ws/alerts`

Streams canonical JSON `SecurityIncidentSchema` events to connected frontend
clients after the database transaction commits. The first message is a security
incident event, not a heartbeat. A client must reconnect after disconnecting;
the endpoint does not replay older alerts. Each connection consumes one bounded
process-local alert-bus queue, and queue-full deliveries can be dropped and are
counted in metrics.

Example JavaScript:

```javascript
const socket = new WebSocket("ws://127.0.0.1:8001/ws/alerts");
socket.onmessage = (message) => {
  const incident = JSON.parse(message.data);
  console.log(incident.incident_id, incident.severity, incident.title);
};
```

This endpoint does not implement authentication/authorization. Expose it only
on loopback or a trusted development network until access controls exist.

## Alert bus and deduplication

The alert bus is process-local and not durable across restarts. Each subscriber
has a bounded queue. If a subscriber queue is full, that subscriber's copy
may be dropped, and the delivery-drop counter is incremented.

The default sliding deduplication window is 60 seconds, with up to 10,000
tracked signatures. The fingerprint uses severity, title, source IP, endpoint
ID and status. Incident and transaction IDs are excluded. Repeated matches
refresh the suppression window.

Deduplication suppresses notifications; it does not delete or merge persisted
security incident records. Alerts without enough identifying context are not
grouped indiscriminately.

## OpenAPI and tests

- Interactive documentation: `/docs`
- Generated OpenAPI schema: `/openapi.json`
- Router: `app/api_v1.py`
- Shared incident schema: `app/schemas.py`
- Alert bus: `app/alert_bus.py`
- Deduplicator: `app/alert_dedup.py`

Run the API and OpenAPI contract tests:

    python -m pytest -q tests/test_api_v1.py tests/test_openapi_contract.py

## Security and operational limitations

The v1 routes do not currently implement authentication or authorization.
Keep the service on loopback or a trusted development network until access
controls are implemented and tested.

The blocklist receiver defaults to `tcp://127.0.0.1:5558`. For an isolated
local test, `API_SENTINEL_BLOCKLIST_VERDICT_ENDPOINT` can select another
loopback TCP port. The receiver rejects non-loopback bind addresses, and the
sender connects to the receiver's actual bound endpoint.

The BOLA detector is a lab-scoped heuristic that associates identity with an
observed successful login response and token fingerprint. It does not
independently verify the token signature.

A detected incident must not automatically become a block verdict. Actual
packet enforcement requires a separately implemented and tested eBPF program
that consumes the documented Day 17 map ABI.
