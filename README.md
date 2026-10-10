# API-Sentinel

Runtime BOLA \& Shadow API Detection Engine



\## Backend Ingestion Foundation â€” Day 1



\### Components



\- FastAPI application

\- RawPacketChunk, HeaderData, and PacketMetadata schemas

\- AsyncIO queues for raw packets, headers, and metadata

\- Root and queue-status endpoints



\### Prerequisites



\- Python 3.14.3 (current development environment)

\- pip



\### Setup



Create and activate a virtual environment:



```powershell

python -m venv .venv

.\\.venv\\Scripts\\Activate.ps1

```



Install dependencies:



```powershell

python -m pip install -r requirements.txt

```



Run the backend:



```powershell

python -m uvicorn app.main:app --reload --port 8001

```



\### API endpoints



\- `GET /` â€” service information

\- `GET /queue-status` â€” in-memory queue sizes

\- `/docs` â€” interactive API documentation



\### Tests



```powershell

python -m pytest -v

```



Day 1 tests cover schemas, validation, queue operations, API endpoints, and a 1,000-object queue burst.



\### Current limitations



The queues are in-memory and are not yet connected to the eBPF Ring Buffer. HTTP stream reassembly and external message routing are future milestones.
