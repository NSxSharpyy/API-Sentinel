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

## Operational and diagnostic endpoints

These endpoints expose application status and diagnostic information. They are
intended for local development and trusted operational access.

### GET /

Returns basic service information:

- `service`
- `version`
- `environment`
- `status`

Example:

    curl http://127.0.0.1:8001/

### GET /healthz

Returns a basic process health response.

Example:

    curl http://127.0.0.1:8001/healthz

Expected response:

    {"status":"ok"}

This endpoint is not a substitute for checking application readiness.

### GET /readyz

Checks whether the backend is ready to serve requests.

Readiness requires:

- The persistence worker is running.
- The HTTP processing pipeline is initialized.
- Packet capture is running when capture is enabled.

When packet capture is disabled through `API_SENTINEL_CAPTURE_ENABLED=0`,
capture readiness is considered satisfied. Persistence and pipeline checks
still apply.

The endpoint returns HTTP 200 when ready and HTTP 503 when not ready.

The response includes capture state, memory information, and queue depths.

Example:

    curl -i http://127.0.0.1:8001/readyz

### GET /queue-status

Returns runtime queue and ingestion diagnostics, including queue depths and
packet-processing counters.

Example:

    curl http://127.0.0.1:8001/queue-status

The response is a current diagnostic snapshot. It is not a durable metrics
history or a guarantee that every queued event has been persisted.

### GET /debug/http-parsers

Returns HTTP parser and TCP stream diagnostic information, including parser
counts, parser buffers, request and response counts, completed transactions,
pending and unmatched data, and stream diagnostics.

Example:

    curl http://127.0.0.1:8001/debug/http-parsers

This is a diagnostic endpoint. Do not expose it to untrusted clients.

### GET /detection-status

Returns the current BOLA detection status and available detector metrics.

Possible states include:

- `not_initialized`: the detector has not been initialized.
- `running`: the detector is initialized and running.

Example:

    curl http://127.0.0.1:8001/detection-status

A not-initialized detector must not be interpreted as proof that no suspicious
activity exists.

### GET /blocklist-status

Returns blocklist integration status, including whether integration is
enabled, verdict queue information, receiver status, and the configured
eBPF map path.

The status may indicate disabled, running, stopped, or not initialized,
depending on the integration lifecycle.

The response also exposes `packet_drop_enforcement_configured`.

The current backend reports packet-drop enforcement as not configured.
Blocklist status or synchronization must not be interpreted as proof that
packets are being dropped by the kernel.

Example:

    curl http://127.0.0.1:8001/blocklist-status

## WebSocket /ws/transactions

Streams normalized completed HTTP transactions to connected clients.

Example JavaScript:

    const socket = new WebSocket("ws://127.0.0.1:8001/ws/transactions");

    socket.onmessage = (message) => {
      const event = JSON.parse(message.data);
      console.log(event.event_type, event.message_type);
      console.log(event.connection_key);
      console.log(event.request, event.response);
    };

The transaction event contains:

- `event_type`: `http.transaction`
- `message_type`: `completed_transaction`
- `connection_key`: connection identifier
- `request`: normalized request information
- `response`: normalized response information

The normalized request and response objects contain only the supported
message fields, such as message type, capture timestamp, method, URI, and
status code. The URI is reduced to its path. Raw HTTP headers and bodies are
not included in this WebSocket event.

Each WebSocket client has a bounded queue with a default size of 100 messages.
When the queue is full, the oldest queued item is discarded so that a newer
item can be inserted.

This stream is best-effort. It does not provide durable delivery, historical
replay, or guaranteed processing by connected clients. Clients must reconnect
after a disconnect and should not treat this stream as a durable transaction
store.

The endpoint does not implement authentication or authorization.

## Metrics groups

The `/api/v1/metrics` response also includes a `serialization` group for
serialization-related runtime measurements.

All metric groups represent current runtime snapshots. They are not a
replacement for a time-series monitoring system or durable audit records.

## CORS and access restrictions

The current application has a fixed development CORS allowlist:

- `http://localhost:5173`
- `http://127.0.0.1:5173`
- `http://localhost:5175`
- `http://127.0.0.1:5175`

These origins are configured in the application; there is currently no
environment variable for changing the CORS allowlist.

CORS is not authentication. The API and both WebSocket endpoints do not
implement authentication or authorization. Keep access restricted to
loopback or a trusted development network.

## Current API route inventory

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Basic service information |
| GET | `/healthz` | Basic health check |
| GET | `/readyz` | Application readiness |
| GET | `/queue-status` | Queue and ingestion diagnostics |
| GET | `/api/v1/endpoints` | Discovered endpoint records |
| GET | `/api/v1/alerts` | Persisted security incidents |
| GET | `/api/v1/metrics` | Runtime metrics snapshots |
| GET | `/debug/http-parsers` | HTTP parser diagnostics |
| GET | `/detection-status` | Detection subsystem status |
| GET | `/blocklist-status` | Blocklist integration status |
| WS | `/ws/transactions` | Completed transaction stream |
| WS | `/ws/alerts` | Security incident stream |

The route inventory describes the currently documented backend interface.
Check the generated OpenAPI schema and runtime route registration when
validating a particular build.
