
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

for svc in auth user order billing; do
  cp services/_shared/service_base.py \
     services/_shared/security.py \
     services/_shared/db.py \
     services/_shared/mock_data.py \
     services/_shared/seed_db.py \
     services/_shared/requirements.txt \
     services/_shared/Dockerfile \
     services/_shared/.dockerignore \
     "services/${svc}_service/"

  echo "synced -> ${svc}_service"
done
