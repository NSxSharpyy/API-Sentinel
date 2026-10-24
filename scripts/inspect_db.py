#!/usr/bin/env python3
"""Read-only inspection of the API-Sentinel SQLite database."""

import os
import sqlite3
from pathlib import Path

DB_PATH = Path(
    os.environ.get("DB_PATH", str(Path(__file__).resolve().parents[1] / "data" / "shop.db"))
).resolve()

if not DB_PATH.is_file():
    raise SystemExit(f"Database not found: {DB_PATH}")

# URI mode=ro prevents this helper from creating or modifying the database.
uri = DB_PATH.as_uri() + "?mode=ro"

with sqlite3.connect(uri, uri=True) as conn:
    conn.row_factory = sqlite3.Row
    tables = [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        )
    ]

    print(f"Database: {DB_PATH}")
    for table in tables:
        # Table names come from sqlite_master, not user input.
        count = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        print(f"\n{table}: {count} rows")

        if table in {"customers", "orders", "invoices"}:
            columns = [
                row["name"]
                for row in conn.execute(f'PRAGMA table_info("{table}")')
            ]
            # Avoid printing password hashes or other customer details.
            safe_columns = {
                "customers": ["id", "username", "full_name"],
                "orders": ["id", "user_id", "item", "total", "status"],
                "invoices": ["id", "order_id", "owner_id", "amount", "currency", "status"],
            }[table]
            selected = [col for col in safe_columns if col in columns]
            if selected:
                query = (
                    f'SELECT {", ".join(chr(34) + col + chr(34) for col in selected)} '
                    f'FROM "{table}" ORDER BY id LIMIT 5'
                )
                for row in conn.execute(query):
                    print("  " + " | ".join(f"{key}={row[key]}" for key in selected))
