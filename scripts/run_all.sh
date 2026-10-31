#!/usr/bin/env bash
set -euo pipefail

# Locate the repository root
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Change to the repository root
cd "$ROOT_DIR"

# Require the root .env file
if [[ ! -f "$ROOT_DIR/.env" ]]; then
  echo "Missing .env file. Configure TOKEN_SECRET first."
  exit 1
fi

# Load and export environment variables
set -a
source "$ROOT_DIR/.env"
set +a

# Validate TOKEN_SECRET
: "${TOKEN_SECRET:?TOKEN_SECRET must be configured}"

# Launch the nested startup script using Bash
exec bash "$ROOT_DIR/appsec-testing/scripts/run_all.sh"


