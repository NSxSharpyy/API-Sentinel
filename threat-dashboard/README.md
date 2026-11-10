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
- System latency visualization.
- Alert responsiveness monitoring.
- A demo-only global enforcement control.
- A simulated blocked-attacks event stream.
- A blocked-transaction inspection drawer.
- A demo rate-limiting configuration interface.
- Virtualized incident list rendering.
- High-priority toast notifications and warning banners.

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

Use a Node.js version supported by the installed Vite version and the project's dependency requirements.

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

Run:

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

Mock telemetry should remain clearly identified in the dashboard.

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

The system latency widget and alert responsiveness monitor provide frontend visualization and measurement capabilities. They do not independently verify eBPF sidecar processing overhead or the complete backend alert delivery pipeline.

Mock values must remain clearly labelled as simulated.

## 12. Enforcement Control

The current `EnforcementToggle` component changes local demo state only.

It does not enable or disable actual traffic blocking. Backend integration, authorization, confirmed server state, and error handling are required before this can become a real enforcement control.

The interface may display monitoring and enforcement states for demonstration purposes. Such labels must not be interpreted as confirmation that real enforcement is active.

## 13. Blocked Attacks Stream and Metrics

The blocked-attacks stream displays illustrative demo events for frontend development and review.

The interface includes:

- Simulated blocked-attack event entries.
- HTTP method, endpoint, and severity details.
- A severity filter.
- An inspection action for viewing event details.
- Explicit demo-data labels and limitations.

**Important:** These events do not confirm that a packet was dropped or a request was blocked by the kernel, eBPF sidecar, or backend.

Real blocked-connection metrics require a verified backend event source, documented event semantics, and a confirmed data contract. Metrics must not be presented as real production counts when they are generated from static demo events.

## 14. Blocked Transaction Inspection Drawer

The blocked-transaction inspection drawer provides a detailed view of a selected demo event.

The interface displays available event fields, including:

- Event identifier.
- Event timestamp.
- HTTP method and endpoint.
- Severity.
- Illustrative reason for the event.
- Event status.
- Sanitized request metadata.

Sensitive values, including authorization and cookie information, must remain redacted. The demo interface does not require actual credentials or sensitive request bodies.

The drawer supports closing through its close button, backdrop interaction, and Escape key.

**Backend limitation:** Exact kernel drop timestamps, access-control rules, and actual dropped-request details require verified backend telemetry. Illustrative drawer values must not be treated as confirmed kernel or server events.

## 15. Rate-Limiting Configuration

The Rate Limiting Configuration page provides a frontend interface for editing demo rate-limit rules.

The interface supports local rule editing, numeric input validation, and changes to the displayed configuration state.

The current validation includes:

- Request limits must be integers from 1 through 100,000.
- Time windows must be integers from 1 through 86,400 seconds.

These limits describe the current frontend validation rules and are not a substitute for server-side validation.

Current limitations:

- Settings are maintained in frontend state.
- Changes are not persisted across page reloads unless persistence is implemented separately.
- No real API rate limiting or anomaly detection is enforced by this interface.
- Server-side validation, authorization, persistence, and enforcement require backend integration.

Do not describe a locally updated configuration as an active production rate limit.

## 16. Virtualized Incident List

The dashboard includes a virtualized incident list intended to reduce the rendering workload when displaying large incident feeds.

Virtualization renders the visible portion of a list rather than rendering every row at once. This can improve responsiveness when the number of displayed incidents increases.

The implementation should be evaluated with representative incident volumes and browser performance measurements.

A 60 FPS target must be validated through measurement under representative traffic loads before it can be claimed as achieved.

The virtualization library and its configuration should be verified against the installed project dependencies before documenting library-specific implementation details.

## 17. High-Priority Toast and Banner Notifications

The dashboard includes high-priority toast notifications and warning banners for security-related events.

The notification interface supports transient toast messages and independently dismissible warning banners for highlighting important events.

The current demo notifications help demonstrate how the frontend can communicate potentially critical security conditions.

**Important:** Demo notifications do not confirm that a real BOLA, BFLA, or other security attack has been detected. Live alerts require a verified backend event source, a documented alert contract, and suitable handling of duplicate events and delivery failures.

## 18. Enforcement Controls Code Freeze Audit

The enforcement and system configuration UI modules were reviewed as part of the Phase 3 code-freeze audit.

The audit covered the frontend behavior of enforcement controls, rate-limit configuration, blocked-transaction inspection, and related dashboard functionality.

### Validation performed

- ESLint validation.
- Production build validation.
- Git whitespace validation.
- Manual browser checks of dashboard notifications.
- Manual checks of enforcement controls.
- Manual checks of rate-limit input validation.
- Manual checks of transaction drawer behavior.

Run the following commands to repeat the code checks:

```bash
npm run lint
npm run build
git diff --check
```

These checks confirm frontend code quality and buildability at the time they are run. They do not verify backend connectivity, kernel enforcement, production performance, or real-world attack detection.

A code freeze means that the reviewed UI implementation is ready for review; it does not mean that unverified backend integrations are production-ready.

## 19. Application Routes

The frontend provides the following routes under the current router configuration:

| Route | Purpose |
|---|---|
| `/dashboard` | Security overview, telemetry indicators, metrics, and dashboard widgets. |
| `/incidents` | Security incident listing and incident investigation. |
| `/api-surface` | API endpoint inventory, search, and filters. |
| `/settings` | Demo rate-limit configuration. |

Unknown routes redirect to `/dashboard` under the current router configuration.

The blocked-attacks stream and notification components are dashboard UI features rather than separate routes unless the router is changed.

## 20. Quality Checks

Run from the `threat-dashboard` directory.

Install dependencies:

```bash
npm ci
```

Run lint:

```bash
npm run lint
```

Create a production build:

```bash
npm run build
```

Check Git whitespace errors in tracked changes:

```bash
git diff --check
```

The project currently defines lint and production build scripts. It does not define a dedicated automated test script in the supplied project configuration.

Record actual command results and manually verify the dashboard in mock mode. Test live mode only when the backend endpoint and message schema have been confirmed.

A successful production build establishes that the frontend can be bundled; it does not establish that backend integration or runtime behavior is correct.

## 21. Implementation Status

### Implemented in the frontend

- Dashboard layout and navigation.
- Mock telemetry generation.
- WebSocket client and reconnection logic.
- Telemetry validation against the frontend's expected schema.
- API Attack Surface search and filters.
- Demo incident summaries.
- Demo attack distribution chart.
- Browser receipt-to-render measurement.
- System latency visualization.
- Alert responsiveness monitoring.
- Demo-only global enforcement control.
- Simulated blocked-attacks event stream.
- Blocked-transaction inspection drawer.
- Demo rate-limiting configuration interface.
- Virtualized incident list.
- High-priority toast notifications and warning banners.
- Frontend validation, production build, and code-freeze checks.

### Requires backend integration or verification

- Confirmed live WebSocket connectivity and authentication.
- Agreement on the backend telemetry schema.
- Live incident API and severity semantics.
- Live API endpoint discovery and classification.
- Real attack-event aggregation.
- Verified backend processing and alert delivery latency.
- Confirmed eBPF sidecar processing overhead.
- Verified kernel drop timestamps and access-control rule details.
- Actual enforcement API and confirmed server-side state.
- Persistent rate-limit configuration and server-side enforcement.
- Live security event delivery for high-priority notifications.
- Performance validation under representative high-load conditions.

A successful frontend build does not establish that any backend integration is working.

## 22. Phase 3 Summary

Phase 3 covers the frontend work for system latency visualization, alert responsiveness measurement, global enforcement controls, blocked-attack visualization, transaction inspection, rate-limit configuration, virtualized incident rendering, high-priority notifications, and the enforcement controls code-freeze audit.

The dashboard provides interfaces and demo behavior for these capabilities. Backend-dependent features must remain explicitly identified as unverified until integration, data contracts, authorization, and runtime behavior have been tested and confirmed.

The frontend must not claim actual packet drops, active traffic enforcement, real attack detections, verified kernel processing overhead, or production rate limiting solely from simulated data or local UI state.
