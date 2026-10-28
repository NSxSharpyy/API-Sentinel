"""Shared structured logger for attack and audit scripts (Days 8+).

Each attack type writes JSON Lines records to logs/<attack_name>.jsonl.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

LOGS_DIR = Path(__file__).resolve().parents[2] / "logs"


class AttackLogger:
    """Write structured records for one attack run."""

    def __init__(self, attack_name, output_dir=None):
        if not attack_name or Path(attack_name).name != attack_name:
            raise ValueError("attack_name must be a non-empty filename stem")

        self.attack_name = attack_name
        log_dir = Path(output_dir) if output_dir is not None else LOGS_DIR
        log_dir.mkdir(parents=True, exist_ok=True)
        self.path = log_dir / f"{attack_name}.jsonl"
        self._handle = self.path.open("a", encoding="utf-8")
        self._count = 0

    def log(self, **fields):
        record = dict(fields)
        record["attack_type"] = self.attack_name
        record["ts"] = datetime.now(timezone.utc).isoformat()
        record["attack_sequence"] = self._count

        self._handle.write(json.dumps(record) + "\n")
        self._handle.flush()
        self._count += 1

    def close(self):
        if not self._handle.closed:
            self._handle.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False
