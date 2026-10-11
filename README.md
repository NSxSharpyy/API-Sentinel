# AppSec, Attack Simulation & Testing Lead (Member 6)

Mock e-commerce microservices for validating the eBPF API security project.


## Quick Start

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate

python -m pip install -r appsec-testing/requirements.txt

./scripts/run_all.sh
```

Open another terminal from the repository root and check service health:

```bash
python scripts/check_health.py
```

The authentication, user, order, and billing services should respond successfully.
