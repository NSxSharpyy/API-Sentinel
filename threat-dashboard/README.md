
# API-Sentinel Threat Dashboard

## 1. Project Overview

API-Sentinel is a React frontend for API threat monitoring and security incident visualization.

The dashboard includes:

- Shared dashboard layout and responsive navigation.
- Security overview cards and illustrative incident alerts.
- Severity badges.
- Telemetry connection status.
- A WebSocket telemetry client with exponential-backoff reconnection.
- Mock telemetry for frontend development.
- API Attack Surface search and combined filters.
- An illustrative attack distribution chart.
- Browser receipt-to-render responsiveness measurement.
- A demo-only enforcement control.

**Important:** Mock data is simulated and must not be treated as a real security detection. Live backend integration has not been verified merely by building or running the frontend.

## 2. Requirements

Install:

- Node.js compatible with the project's Vite version.
- npm.
- Git, if you need repository access.

Check versions:

```bash
node --version
npm --version
```

## 3. Installation

Run from the `threat-dashboard` directory:

```bash
npm ci
```

If installation fails, inspect the error and verify the Node.js version and lockfile before making dependency changes.

## 4. Environment Configuration

Create the local environment file from the example:

```powershell
Copy-Item .env.example .env
```

Example configuration:

```env
VITE_TELEMETRY_MODE=mock
VITE_TELEMETRY_WS_URL=ws://localhost:8000/ws/telemetry
```

| Variable | Purpose |
|---|---|
| `VITE_TELEMETRY_MODE` | Selects mock or WebSocket telemetry mode. |
| `VITE_TELEMETRY_WS_URL` | WebSocket URL used in live mode. |

Keep mock mode enabled while the backend endpoint and event contract remain unconfirmed.

The WebSocket URL above is a placeholder. Confirm the correct URL and authentication requirements with the backend team.

Environment variables prefixed with `VITE_` are exposed to client-side code. Never store secrets in them or commit a local `.env` file.

Restart Vite after changing environment variables.

## 5. Run the Development Server

```bash
npm run dev
```

Open the local URL printed by Vite, usually:

http://localhost:5173/

Stop the server with `Ctrl+C`.

## 6. Mock Telemetry

Set:

```env
VITE_TELEMETRY_MODE=mock
```

The frontend generates simulated telemetry periodically.

Mock events are for interface development only. They do not prove that an API endpoint exists, that an attack occurred, or that a security control is active.

## 7. Live WebSocket Telemetry

Live mode requires a running backend with a compatible WebSocket endpoint.

Example configuration, only after confirming the actual endpoint:

```env
VITE_TELEMETRY_MODE=websocket
VITE_TELEMETRY_WS_URL=ws://localhost:8000/ws/telemetry
```

Use `wss://` when required by the deployed environment.

### Reconnection behavior

The client attempts to reconnect after an unexpected socket closure or a socket-construction failure.

The current reconnection strategy uses exponential backoff:

- Initial delay: 1 second.
- Subsequent delays increase exponentially.
- Maximum delay: 30 seconds.
- Only one reconnect timer is scheduled at a time.
- A successful connection resets the retry counter.
- An intentional disconnect cancels pending reconnection and closes the client.

If the WebSocket URL is missing, the client reports a configuration error instead of repeatedly attempting a connection.

This behavior must still be tested against the target browser and backend before being considered verified in production.

### Telemetry message validation

The current frontend validator expects an event payload containing:

- Event ID: `id`, `eventId`, or `event_id`.
- HTTP method: `method`.
- Endpoint: `endpoint` or `path`.
- HTTP status code: `statusCode` or `status_code`.
- Latency: `latencyMs` or `latency_ms`.
- Timestamp: `timestamp` or `timestampUtc`.

The method must be a supported HTTP method, the status code must be an integer from 100 through 599, latency must be finite and non-negative, and the timestamp must be parseable.

**Backend contract status:** These expectations are based on the current frontend implementation. The backend team must confirm the actual schema and timestamp semantics before live integration is declared verified.

Invalid messages are rejected from the transaction table and reported through the telemetry error state.

## 8. Incident Data

The dashboard currently uses illustrative incident data from `mockIncidents`.

Critical and High incident counts are counts within that demo dataset, not verified live detections.

A live incident feed requires a confirmed backend API or documented incident event contract, including severity definitions and error handling.

## 9. API Attack Surface

The endpoint inventory currently comes from `mockApiEndpoints`.

The existing search, source filter, classification filter, HTTP method filter, and combined filtering behavior are frontend features.

Endpoint entries and Official, Shadow, and Zombie classifications are illustrative examples, not verified discovery findings.

Live inventory requires a confirmed backend discovery service and a documented response schema. The demo warning must remain until this integration has been verified.

## 10. Attack Distribution Chart

The attack distribution chart uses `mockAttackDistribution` sample values.

These values are illustrative and are not measured attack-event aggregates.

Live aggregation requires a confirmed backend endpoint, documented attack categories, a time range, and an aggregation interval. Empty results and request failures must be handled explicitly.

## 11. Latency Measurement Boundaries

The dashboard distinguishes the following concepts:

- **Telemetry latency value:** A latency field supplied by the latest valid event. Its measurement boundary must be confirmed with the backend.
- **Browser receipt-to-render latency:** An elapsed-time measurement between browser event receipt and the associated UI render measurement.
- **Backend processing latency:** Requires a documented backend measurement.
- **End-to-end alert delivery latency:** Requires defined pipeline boundaries and trustworthy timestamps or tracing.

These values are not interchangeable. Browser rendering time does not establish backend processing time or end-to-end delivery time.

Mock values must remain clearly labelled as simulated.

## 12. Enforcement Control

The current `EnforcementToggle` component changes local demo state only.

It does not enable or disable actual traffic blocking. Backend integration, authorization, confirmed server state, and error handling are required before this can become a real enforcement control.

## 13. Quality Checks

Run from the `threat-dashboard` directory:

```bash
npm ci
npm run lint
npm run build
```

The project currently defines lint and production build scripts. It does not define a dedicated test script in the supplied `package.json`.

Record actual command results and manually verify the dashboard in mock mode. Test live mode only when the backend endpoint and message schema have been confirmed.

## 14. Implementation Status

### Implemented in the frontend

- Dashboard layout and navigation.
- Mock telemetry generation.
- WebSocket client and reconnection logic.
- Telemetry validation against the frontend's expected schema.
- API Attack Surface search and filters.
- Demo incident summaries.
- Demo attack distribution chart.
- Browser receipt-to-render measurement.
- Demo-only enforcement control.

### Requires backend integration or verification

- Confirmed live WebSocket connectivity and authentication.
- Agreement on the backend telemetry schema.
- Live incident API and severity semantics.
- Live API endpoint discovery and classification.
- Real attack-event aggregation.
- Verified backend processing and alert delivery latency.
- Actual enforcement API and confirmed server-side state.

A successful frontend build does not establish that any backend integration is working.
