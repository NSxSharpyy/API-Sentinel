# API-Sentinel Threat Dashboard

## 1. Project Overview

API-Sentinel is a frontend dashboard for API threat monitoring and security incident visualization.

The current frontend includes:
- A shared dashboard layout with desktop and mobile navigation.
- Security overview cards and illustrative security alerts.
- Severity badges for Critical, High, Medium, and Low incidents.
- A telemetry status banner.
- A reusable WebSocket client and React hook for receiving telemetry.
- Mock telemetry for development when the backend is unavailable.

**Important:** Mock events are simulated data, not real security detections. Live backend connectivity has not yet been verified.

## 2. Requirements

Install the following before running the project:

- Node.js: a version supported by the installed Vite release.
- npm: included with Node.js.
- Git, if you need to clone the repository.

Check your installed versions:

```bash
node --version
npm --version
```

## 3. Installation

Open a terminal in the `threat-dashboard` directory.

Install the dependencies recorded in the project's lockfile:

```bash
npm ci
```

If installation fails, check the Node.js and npm versions and read the error before trying other installation commands.

## 4. Environment Configuration

The project uses Vite environment variables to configure telemetry.

Create your local environment file by copying the example:

```powershell
Copy-Item .env.example .env
```

The example configuration is:

```env
VITE_TELEMETRY_MODE=mock
VITE_TELEMETRY_WS_URL=ws://localhost:8000/ws/telemetry
```

### Environment variables

| Variable | Purpose |
|---|---|
| `VITE_TELEMETRY_MODE` | Selects mock or WebSocket telemetry mode. |
| `VITE_TELEMETRY_WS_URL` | WebSocket endpoint used in live mode. |

Keep `VITE_TELEMETRY_MODE=mock` while developing without a connected backend.

The WebSocket URL above is a placeholder. Confirm the actual endpoint with the backend team before enabling live mode.

Do not commit your local `.env` file or put secrets in frontend environment variables. Variables prefixed with `VITE_` are exposed to client-side code.

## 5. Run the Development Server

Start the frontend:

```bash
npm run dev
```

Open the local URL printed by Vite, usually:

http://localhost:5173/

To stop the server, press `Ctrl+C` in the terminal.

## 6. Mock Telemetry and Live WebSocket Mode

### Mock mode

Set the following in `.env`:

```env
VITE_TELEMETRY_MODE=mock
```

Mock mode generates simulated telemetry events periodically. The dashboard should display **Mock telemetry active** and a warning that the events are simulated.

This mode allows frontend development without a running telemetry backend.

### Live WebSocket mode

Live mode requires a running backend with a compatible WebSocket endpoint.

After confirming the endpoint with the backend team, configure `.env`:

```env
VITE_TELEMETRY_MODE=websocket
VITE_TELEMETRY_WS_URL=ws://localhost:8000/ws/telemetry
```

Replace the example URL if the backend team provides a different endpoint. Use `wss://` when required by the deployed environment.

Restart the Vite development server after changing environment variables.

Live mode also requires the backend's message format and any authentication requirements to match the frontend implementation. A successful frontend build alone does not prove that the WebSocket connection works.

Automatic reconnection is not currently implemented in this client.

## 7. Linting and Production Build

Check the code with ESLint:

```bash
npm run lint
```

Create a production build:

```bash
npm run build
```

Vite writes the production output to the `dist` directory.

## 8. Current Implementation Status

Implemented:
- Dashboard layout and navigation.
- Security overview and illustrative incident cards.
- Severity badges.
- Configurable telemetry client and React hook.
- Mock telemetry status display.

Still dependent on backend integration:
- Confirmed live WebSocket connectivity.
- Agreement on the telemetry message schema.
- Any required backend authentication and connection settings.

Use mock-data labels appropriately when presenting the dashboard before live telemetry has been verified.
