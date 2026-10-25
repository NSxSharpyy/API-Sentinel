
# API-Sentinel

Runtime BOLA and Shadow API Detection Engine.

API-Sentinel is being developed to support runtime API traffic ingestion, HTTP message parsing, and event delivery for security analysis. The backend is under active development.

## Current Backend Capabilities

### 1. FastAPI Ingestion Foundation

- FastAPI application and status endpoints.
- `RawPacketChunk`, `HeaderData`, and `PacketMetadata` schemas.
- In-memory asynchronous queues for raw packets, headers, and metadata.
- Root and queue-status endpoints.

### 2. HTTP Stream Parsing

The HTTP stream parser currently supports:

- HTTP/1.x request parsing.
- HTTP/1.x response parsing, including status codes and reason phrases.
- HTTP headers and `Content-Length` bodies.
- Requests and responses split across ordered byte chunks.
- Multiple complete messages in a single input chunk.
- `Transfer-Encoding: chunked` body decoding, including fragmented chunks,
  extensions and bounded trailer validation. Conflicting `Content-Length` and
  `Transfer-Encoding` headers are rejected.
- Configurable maximum header and decoded-body sizes.
- Validation of `Content-Length` values and malformed chunk framing.
- Query strings are preserved in the request target. Multipart form bodies are
  preserved as bytes; the parser does not extract multipart fields.
- Bodyless responses for 1xx/204/304 and cross-direction handling for `HEAD`
  requests, including interim 1xx responses.

The parser is an initial implementation for ordered byte streams. It is not yet a production-grade TCP reassembly engine.

### 3. ZeroMQ Message Broker

The backend includes a ZeroMQ publisher and topic-selectable subscriber.

- `http.transaction` is the backward-compatible per-message topic; each event
  represents one parsed request or response.
- `discovery.http.transaction` and `heuristics.http.transaction` carry complete
  correlated request/response pairs for the downstream analysis services.
- Payloads are UTF-8 JSON; HTTP bodies are Base64-encoded to preserve arbitrary
  bytes.

The HTTP pipeline sends each parsed message to the legacy topic and publishes a
completed transaction to both downstream topics only after the correlator has a
matching request and final response. The complete event has `message_type` set
to `completed_transaction`, a `connection_key`, and nested `request` and
`response` objects. This makes the downstream contract explicit and prevents a
request-only event from being mistaken for a completed transaction.

The broker uses ZeroMQ PUB/SUB and is best-effort, not durable. Subscribers can
miss messages if they have not connected and completed the subscription
handshake before an event is published. Consumer acknowledgements and replay are
not implemented. Actual Member 3/4 deployments still need to confirm that their
consumers use these topics and the documented JSON contract.

## Project Structure

```text
API-Sentinel/
├── app/
│   ├── main.py
│   ├── http_reassembly.py / tcp_reassembly.py
│   ├── http_pipeline.py / packet_worker.py
│   ├── message_broker.py / transaction_correlator.py
│   ├── transaction_store.py / persistence_worker.py
│   ├── alert_bus.py / alert_dedup.py / api_v1.py
│   └── blocklist_* (Day 17 verdict, policy and map synchronization)
├── ebpf-day16/                 # packet capture and ring-buffer loader
├── ebpf-day17/                 # blocklist map, experimental TC enforcement
├── benchmarks/                 # synthetic and queue/SQLite benchmarks
├── docs/                       # daily progress and acceptance evidence
├── tests/                      # unit, API, broker and integration tests
├── requirements.txt
└── README.md
```

Other application modules and tests may also be present in the repository.

## Prerequisites

- Python 3.14.3 or a compatible Python version.
- pip.
- Git.

ZeroMQ support is provided by the `pyzmq` dependency listed in `requirements.txt`.

## Setup on Windows

Open PowerShell in the project directory.

Install dependencies using your active Python environment:

```powershell
python -m pip install -r requirements.txt
```

If using a virtual environment, activate it before installing dependencies.

For example, if your virtual environment is located at `.venv` inside the project:

```powershell
.\.venv\Scripts\Activate.ps1
```

The development environment may instead use a virtual environment outside the repository.

## Run the Backend

Start the FastAPI application with:

```powershell
python -m uvicorn app.main:app --reload --port 8001
```

Port `8001` is used here to avoid conflicts with services that may already occupy port `8000`.

When the server starts successfully, visit:

- `http://127.0.0.1:8001/` — root endpoint.
- `http://127.0.0.1:8001/queue-status` — ingestion and processing queues.
- `http://127.0.0.1:8001/api/v1/endpoints` — discovered endpoints.
- `http://127.0.0.1:8001/api/v1/alerts` — persisted security incidents.
- `http://127.0.0.1:8001/api/v1/metrics` — runtime metrics.
- `ws://127.0.0.1:8001/ws/alerts` — JSON events for committed security incidents.
- `http://127.0.0.1:8001/openapi.json` — generated OpenAPI schema.
- `http://127.0.0.1:8001/docs` — interactive API documentation.

## Automated Python checks

The `.github/workflows/python-tests.yml` workflow runs on pushes and pull
requests targeting `backend-parser`. It tests Python 3.13 and 3.14, compiles
`app/`, `tests/`, and `benchmarks/`, then runs the full pytest suite. This
workflow verifies Python code and tests only; it does not build the eBPF C
programs or run privileged WSL packet-drop tests. A green result must be
confirmed from the GitHub Actions run after the workflow is pushed.

## Run Tests

Run the complete test suite from the project root:

```powershell
python -m pytest -v
```

Compile the application and test modules:

```powershell
python -m compileall -q app tests
```

The tests cover the currently implemented components, including HTTP request and response parsing, fragmented messages, body-size validation, JSON serialization, and ZeroMQ delivery.

## Current Limitations and Pending Work

- The eBPF capture path has been exercised in a controlled WSL loopback BOLA lab. This limited runtime evidence does not establish production readiness.
- TCP reassembly components and tests exist; broader stream handling and failure-recovery behavior still require validation beyond the controlled lab.
- HTTP parsing supports the single `chunked` transfer coding only; stacked or unsupported transfer codings are rejected. Multipart form bodies are preserved but not decoded into fields.
- HTTP/1.x parsing does not support HTTP/2, TLS decryption, WebSocket framing, or connection-tunnel decoding. Broader protocol coverage remains future work.
- The live capture-to-analysis path has been exercised for a controlled local BOLA scenario, but broader protocol coverage and operational reliability remain unverified.
- ZeroMQ PUB/SUB delivery is not durable.
- The alert bus and `/ws/alerts` stream are process-local and non-durable; bounded subscriber queues can drop notifications when full, and reconnecting clients do not receive replay.
- Persisting a completed transaction now upserts `DiscoveredEndpoint` by normalized host, method, and path (query strings are not part of the endpoint identity); transaction rows and BOLA incidents reference that endpoint when an identity can be derived.
- The v1 APIs currently lack authentication and authorization; keep the service on loopback or a trusted development network.
- The Day 17 map does not drop packets by itself. A separate experimental TC
  classifier and loader can enforce entries on explicitly named `api-sntl-*` lab
  interfaces when manually opted in. This is not automatically attached by the
  FastAPI application and is not production enforcement.
- The lab BOLA policy can submit an allowlisted verdict to the local receiver and
  synchronization worker when both opt-ins are enabled. Additional detection
  modules and the complete automatic detection-to-kernel-drop path still require
  integration/runtime verification.
- Synthetic application and queue benchmarks are not substitutes for line-rate
  eBPF capture, production database, sustained-load or memory-soak validation.
- Production hardening, observability, and broader protocol testing remain future work.

## Development Status

API-Sentinel is an active development project. The current backend provides an initial parsing and event-publishing foundation. Further integration and validation are required before it can be considered production-ready.
