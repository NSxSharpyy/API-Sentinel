# API-Sentinel Backend Deployment Guide

## 1. Deployment modes

| Mode | Purpose | Packet capture |
|---|---|---|
| WSL/Python | Local development and optional eBPF capture | Optional |
| Docker Compose | API-only backend deployment | Disabled |

The Docker Compose deployment runs the API, processing components, and persistence worker without starting the eBPF packet-capture pipeline.

## 2. Prerequisites

### WSL/Python
- Ubuntu under WSL 2 or another compatible Linux environment.
- A Python version supported by the project.
- Git and pip.
- Project dependencies from requirements.txt.

### Docker
- Docker Desktop with the WSL 2 engine enabled.
- WSL integration enabled for Ubuntu.
- Docker Compose v2 or later.

## 3. Local WSL/Python deployment

Run these commands from the project root:

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt

Create and load the local environment configuration:

    cp .env.example .env
    set -a
    source .env
    set +a

Start the API:

    python -m uvicorn app.main:app --host 127.0.0.1 --port 8001

Available endpoints:

- API root: http://127.0.0.1:8001/
- Health: http://127.0.0.1:8001/healthz
- Readiness: http://127.0.0.1:8001/readyz
- OpenAPI documentation: http://127.0.0.1:8001/docs

The example configuration uses API-only mode with packet capture disabled.

To enable packet capture, use a compatible Linux environment and configure the required eBPF components and permissions. Enabling the capture flag alone does not install or configure those components.

## 4. Docker Compose deployment

First verify that Docker Desktop is running and its Linux engine is available.

Validate the Compose configuration:

    docker compose config

Build and start the backend:

    docker compose up --build -d

Check container status:

    docker compose ps

Review backend logs:

    docker compose logs -f api

Check service health:

    curl -i http://127.0.0.1:8001/healthz

Check readiness:

    curl -i http://127.0.0.1:8001/readyz

The Compose configuration uses API-only mode. Packet capture and blocklist integration are disabled.

## 5. Persistence

Docker Compose stores the SQLite database in the named volume api_sentinel_data, mounted at /data.

Restart containers without deleting the volume:

    docker compose restart

Stop and remove containers and the network:

    docker compose down

The named volume remains available after this command.

WARNING: The following command also deletes the database volume and its contents:

    docker compose down -v

Do not use the -v option when persisted data must be preserved.

## 6. Troubleshooting

### Docker engine unavailable

Check Docker connectivity:

    docker info

If server information cannot be retrieved, start Docker Desktop and verify that its Linux engine and WSL integration are enabled.

### Port 8001 already in use

Identify the process listening on port 8001:

    sudo ss -ltnp | grep ':8001'

Identify the conflicting process before stopping or reconfiguring it.

### Backend is not ready

Inspect both health and readiness:

    curl -i http://127.0.0.1:8001/healthz
    curl -i http://127.0.0.1:8001/readyz

For Docker deployments, inspect recent logs:

    docker compose logs --tail=100 api

A healthy process does not necessarily mean all backend dependencies are ready. Use /readyz to check application readiness.

## 7. Operational and security notes

- The documented Docker deployment is API-only, not a packet-capture deployment.
- Current API and WebSocket endpoints do not provide authentication or authorization.
- Keep the service bound to loopback or an appropriately controlled trusted network.
- Do not expose diagnostic endpoints to untrusted clients.
- Protect database files, environment files, and logs.
- Do not commit credentials or secrets.
- Validate readiness and inspect logs before treating a deployment as operational.
