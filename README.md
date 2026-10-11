
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
- Configurable maximum header and body sizes.
- Validation of `Content-Length` values.
- Rejection of `Transfer-Encoding` because chunked transfer decoding is not implemented.

The parser is an initial implementation for ordered byte streams. It is not yet a production-grade TCP reassembly engine.

### 3. ZeroMQ Message Broker

The backend includes a ZeroMQ publisher and subscriber.

- Topic: `http.transaction`
- Message payload: UTF-8 encoded JSON.
- Request bodies are Base64-encoded in the JSON event.
- The HTTP pipeline passes incoming byte chunks to the parser and publishes each completed message.

The current broker uses ZeroMQ PUB/SUB. Messages are not durably stored, and subscribers can miss messages if they are not ready or connected when events are published.

The existing request event format contains:

- `event_type`
- `method`
- `uri`
- `version`
- `headers`
- `body_base64`

## Project Structure

```text
API-Sentinel/
├── app/
│   ├── main.py
│   ├── http_reassembly.py
│   ├── message_broker.py
│   └── http_pipeline.py
├── tests/
│   ├── test_http_reassembly.py
│   └── test_message_broker.py
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
- `http://127.0.0.1:8001/queue-status` — queue status.
- `http://127.0.0.1:8001/docs` — interactive API documentation.

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

- **Real eBPF integration is pending.** The parser and pipeline have not yet been connected to a real eBPF Ring Buffer producer.
- The current parser expects ordered TCP payload chunks. TCP sequence-number handling, retransmissions, out-of-order segments, and connection lifecycle management are not implemented.
- HTTP chunked transfer encoding is not supported.
- HTTP parsing currently focuses on basic HTTP/1.x framing. Special response cases, such as responses to `HEAD` requests and bodyless status codes, need additional handling.
- The pipeline and broker are components; a complete live traffic-capture-to-analysis workflow is not yet implemented.
- ZeroMQ PUB/SUB delivery is not durable.
- Production hardening, observability, and broader protocol testing remain future work.

## Development Status

API-Sentinel is an active development project. The current backend provides an initial parsing and event-publishing foundation. Further integration and validation are required before it can be considered production-ready.
