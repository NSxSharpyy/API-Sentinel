# API-Sentinel Backend Configuration Reference

## 1. Configuration overview

API-Sentinel reads configuration from environment variables.

The `.env.example` file is a reference configuration. It is not automatically loaded by Python. For local development, copy it to `.env` and explicitly export its values into the shell, or configure the variables through the deployment environment.

Do not commit real credentials, secrets, or production database connection strings.

## 2. Database configuration

| Variable | Default | Description |
|---|---|---|
| DATABASE_URL | sqlite:///./api_sentinel.db | Synchronous database connection URL. |
| ASYNC_DATABASE_URL | Derived from DATABASE_URL when unset | Asynchronous database connection URL. |

The database layer supports SQLite and PostgreSQL connection URLs. The asynchronous URL uses the corresponding asynchronous driver.

Examples:

    DATABASE_URL=sqlite:///./api_sentinel.db
    ASYNC_DATABASE_URL=sqlite+aiosqlite:///./api_sentinel.db

PostgreSQL example:

    DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE

Use environment-specific credentials. Do not place real passwords in committed files.

## 3. Capture configuration

| Variable | Default | Description |
|---|---|---|
| API_SENTINEL_CAPTURE_ENABLED | 1 | Enables or disables the packet-capture supervisor. |

Supported values are:

- Enabled: 1, true, yes, on
- Disabled: 0, false, no, off

Values are case-insensitive. An unrecognized value causes startup configuration to fail.

When disabled, the backend runs in API-only mode. The capture supervisor is not started, and readiness does not require packet capture to be running. Persistence and pipeline readiness are still required.

Enabling capture does not install eBPF programs or grant the required kernel permissions.

## 4. Queue and persistence configuration

The following variables accept positive integer values.

| Variable | Default | Description |
|---|---:|---|
| API_SENTINEL_QUEUE_MAX_SIZE | 10000 | Maximum raw/application queue capacity. |
| API_SENTINEL_BLOCK_VERDICT_QUEUE_MAX_SIZE | 1024 | Maximum block-verdict queue capacity. |
| API_SENTINEL_PERSISTENCE_QUEUE_MAX_SIZE | 12000 | Maximum persistence queue capacity. |
| API_SENTINEL_PERSISTENCE_BATCH_MAX_SIZE | 32 | Maximum persistence batch size. |

Increasing queue capacity can absorb larger temporary bursts, but it also increases potential memory usage. Larger persistence batches can change write throughput and latency. Measure the effect under representative traffic instead of increasing limits blindly.

## 5. ZeroMQ configuration

The following variables accept positive integer values.

| Variable | Default | Description |
|---|---:|---|
| API_SENTINEL_ZMQ_SNDHWM | 1000 | ZeroMQ publisher send high-water mark. |
| API_SENTINEL_ZMQ_RCVHWM | 1000 | ZeroMQ receiver receive high-water mark. |

These settings limit queued ZeroMQ messages. They are not a guarantee of end-to-end delivery or persistence.

The current transaction publisher uses a local loopback endpoint. Its endpoint is not configurable through these variables.

## 6. Blocklist configuration

| Variable | Default | Description |
|---|---|---|
| API_SENTINEL_BLOCKLIST_DROP_AUDIT_ENABLED | Disabled | Enables blocklist drop-audit integration. |
| API_SENTINEL_BLOCKLIST_SYNC_ENABLED | Disabled | Enables blocklist synchronization. |
| API_SENTINEL_BLOCKLIST_POLICY_ENABLED | Disabled | Enables the additional blocklist policy gate. |
| API_SENTINEL_BLOCKLIST_BATCH_SIZE | 5 | Batch size used when synchronization is enabled. |
| API_SENTINEL_BLOCKLIST_VERDICT_ENDPOINT | tcp://127.0.0.1:5558 | Blocklist verdict receiver endpoint. |
| API_SENTINEL_BLOCKLIST_ALLOWED_SOURCE_IPS | Empty | Comma-separated exact source-IP allowlist. |
| API_SENTINEL_BLOCKLIST_VERDICT_TTL_SECONDS | 60 | Verdict time-to-live in seconds. |

Enable the boolean settings with 1, true, or yes. They are disabled by default.

Configuration constraints:

- Drop-audit integration requires the `ebpf-day17/blocklist_drop_reader` executable to exist.
- Policy integration requires synchronization to be enabled.
- Policy integration also requires a non-empty exact source-IP allowlist.
- The verdict receiver enforces a loopback bind address. Do not configure it as an externally accessible listener.
- Configure the allowlist deliberately. Do not assume that an empty allowlist means all sources are trusted.

Blocklist integration is optional. Keep it disabled unless its required components and dependencies have been configured and tested.

## 7. Memory profiling configuration

| Variable | Default | Description |
|---|---|---|
| API_SENTINEL_MEMORY_PROFILE_ENABLED | Disabled | Enables periodic memory profiling. |
| API_SENTINEL_TRACEMALLOC_ENABLED | Disabled | Enables Python tracemalloc collection. |
| API_SENTINEL_TRACEMALLOC_FRAMES | 10 | Number of traceback frames; accepted range is 1 through 25. |
| API_SENTINEL_MEMORY_PROFILE_INTERVAL_SECONDS | 60 | Interval between memory-profile samples. |
| API_SENTINEL_MEMORY_PROFILE_DRAIN_TIMEOUT_SECONDS | 120 | Maximum configured drain timeout in seconds. |
| API_SENTINEL_MEMORY_PROFILE_QUIET_PERIOD_SECONDS | 2 | Configured quiet period in seconds. |
| API_SENTINEL_MEMORY_PROFILE_OUTPUT_DIR | artifacts/day28 | Directory used for memory-profile output. |

Enable the profiling boolean settings with 1, true, or yes.

Enabling memory profiling also enables tracemalloc. Profiling adds runtime overhead and should be used deliberately during development and performance investigations.

The output directory must be writable by the backend process.

## 8. Example local API-only configuration

A typical local API-only environment can use:

    API_SENTINEL_CAPTURE_ENABLED=0
    DATABASE_URL=sqlite:///./api_sentinel.db
    ASYNC_DATABASE_URL=sqlite+aiosqlite:///./api_sentinel.db
    API_SENTINEL_QUEUE_MAX_SIZE=10000
    API_SENTINEL_BLOCK_VERDICT_QUEUE_MAX_SIZE=1024
    API_SENTINEL_PERSISTENCE_QUEUE_MAX_SIZE=12000
    API_SENTINEL_PERSISTENCE_BATCH_MAX_SIZE=32
    API_SENTINEL_ZMQ_SNDHWM=1000
    API_SENTINEL_ZMQ_RCVHWM=1000

Leave optional blocklist and profiling integrations disabled unless you are intentionally testing them.

## 9. Applying configuration

For local WSL development, copy the example file and export its values:

    cp .env.example .env
    set -a
    source .env
    set +a

Start the backend after loading the environment:

    python -m uvicorn app.main:app --host 127.0.0.1 --port 8001

For Docker Compose, configuration is declared in `compose.yaml`. The current Compose configuration explicitly sets API-only mode and its database environment. Do not assume that creating a `.env` file automatically overrides values explicitly configured in the Compose service.

## 10. Security and operational guidance

- Keep secrets out of source control.
- Use least-privilege database credentials.
- Keep API and WebSocket access restricted to trusted clients; the current service does not implement API authentication or authorization.
- Keep the blocklist verdict receiver on loopback.
- Do not expose profiling or diagnostic output to untrusted users.
- Avoid increasing queue sizes without measuring memory consumption and queue latency.
- Verify the effective runtime configuration and readiness after changing environment variables.
