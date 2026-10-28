"""Load demo customer credentials from the seeded Docker database."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

DEMO_PASSWORD = "Password123!"
PROJECT_ROOT = Path(__file__).resolve().parents[3]

DATABASE_QUERY = """
import json
import sqlite3

conn = sqlite3.connect("file:/app/data/shop.db?mode=ro", uri=True)
try:
    rows = conn.execute(
        "SELECT username FROM customers ORDER BY id"
    ).fetchall()
    print(json.dumps([row[0] for row in rows]))
finally:
    conn.close()
"""


@dataclass(frozen=True)
class Customer:
    username: str
    password: str


def build_customer_pool():
    """Load actual seeded usernames from the shared Docker database."""
    try:
        result = subprocess.run(
            [
                "docker", "compose", "exec", "-T", "order",
                "python", "-c", DATABASE_QUERY,
            ],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Docker CLI was not found.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Timed out reading the customer database.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(
            f"Could not read seeded customers. Is Docker running? {detail}"
        ) from exc

    try:
        usernames = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "Invalid customer data returned by Docker."
        ) from exc

    if not isinstance(usernames, list) or not usernames:
        raise RuntimeError("The seeded database contains no customers.")

    if any(not isinstance(name, str) or not name.strip()
           for name in usernames):
        raise RuntimeError("The database contains an invalid username.")

    if len(set(usernames)) != len(usernames):
        raise RuntimeError("Duplicate customer usernames found in the database.")

    return [
        Customer(username=name, password=DEMO_PASSWORD)
        for name in usernames
    ]


if __name__ == "__main__":
    pool = build_customer_pool()
    print(f"Customer credentials loaded from database: {len(pool)}")
    for customer in pool:
        print(customer.username)
