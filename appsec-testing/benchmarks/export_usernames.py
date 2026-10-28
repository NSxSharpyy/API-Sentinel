#!/usr/bin/env python3
"""Export seeded customer usernames for the k6 benchmark."""

import os
import sys
from pathlib import Path

SHARED_DIR = (
    Path(__file__).resolve().parents[1] / "services" / "_shared"
)
sys.path.insert(0, str(SHARED_DIR))

from db import get_connection  # noqa: E402


def main():
    if not os.environ.get("DB_PATH"):
        print(
            "ERROR: Set DB_PATH to the intended SQLite database.",
            file=sys.stderr,
        )
        return 2

    conn = get_connection()

    try:
        rows = conn.execute(
            "SELECT username FROM customers ORDER BY id"
        ).fetchall()
        usernames = [row["username"] for row in rows]
    finally:
        conn.close()

    if not usernames:
        print("ERROR: No customer usernames found in the database.",
              file=sys.stderr)
        return 1

    if len(usernames) != len(set(usernames)):
        print("ERROR: Duplicate usernames found.", file=sys.stderr)
        return 1

    print(",".join(usernames))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
