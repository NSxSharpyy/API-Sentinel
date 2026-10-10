# AppSec, Attack Simulation & Testing Lead (Member 6)

Mock e-commerce microservices for validating the eBPF API security project.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./scripts/run_all.sh
```

## Documentation

See [docs/architecture.md](docs/architecture.md) for the service architecture, ports, logging conventions, and planned lab vulnerabilities.

## Testing

Run `pytest -v` to execute the scaffold tests.

Run `python scripts/check_health.py` while the services are running to verify their health.# API-Sentinel
Runtime BOLA &amp; Shadow API Detection Engine
