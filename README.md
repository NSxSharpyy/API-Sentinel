# AppSec, Attack Simulation & Testing Lead (Member 6)

Mock e-commerce microservices for validating the eBPF API security project.


## Quick Start

### Configure the authentication secret

Generate a cryptographically random secret:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Create a `.env` file in the repository root containing:

```text
TOKEN_SECRET=PASTE_GENERATED_SECRET_HERE
```

Replace the placeholder with the generated value. Keep `.env` local and never commit it.

Start the services from the repository root:

```bash
./scripts/run_all.sh
```

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
