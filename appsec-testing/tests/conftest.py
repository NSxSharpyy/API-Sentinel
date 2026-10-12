"""Isolated, deterministic SQLite database for pytest."""
import os
import sqlite3
from pathlib import Path

from werkzeug.security import generate_password_hash

TEST_DB = Path(__file__).resolve().parent / ".test_shop.db"

# Set these before the tests import any service modules.
os.environ["DB_PATH"] = str(TEST_DB)
os.environ["TOKEN_SECRET"] = "test-only-secret-for-local-tests"

# Recreate only the dedicated test database, never the application DB.
if TEST_DB.exists():
    TEST_DB.unlink()

conn = sqlite3.connect(TEST_DB)
conn.execute("PRAGMA foreign_keys = ON")

conn.executescript("""
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES customers(id),
    item TEXT NOT NULL,
    total REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE invoices (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL UNIQUE REFERENCES orders(id),
    owner_id INTEGER NOT NULL REFERENCES customers(id),
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL,
    card_last4 TEXT NOT NULL,
    billing_address TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_orders_user ON orders(user_id);
CREATE INDEX idx_invoices_owner ON invoices(owner_id);
CREATE INDEX idx_invoices_order ON invoices(order_id);
""")

password_hash = generate_password_hash("Password123!")
created = "2026-01-01T00:00:00+00:00"

conn.executemany(
    """
    INSERT INTO customers
        (id, username, full_name, email, password_hash, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """,
    [
        (1, "alice", "Alice Example", "alice@example.test",
         password_hash, created),
        (2, "bob", "Bob Example", "bob@example.test",
         password_hash, created),
    ],
)

conn.executemany(
    """
    INSERT INTO orders
        (id, user_id, item, total, status, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """,
    [
        (101, 1, "Test Item A", 100.00, "paid", created),
        (102, 1, "Test Item B", 200.00, "shipped", created),
        (103, 2, "Test Item C", 300.00, "paid", created),
    ],
)

conn.executemany(
    """
    INSERT INTO invoices
        (id, order_id, owner_id, amount, currency, status,
         card_last4, billing_address, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    [
        (1, 101, 1, 100.00, "INR", "paid", "1234",
         "Alice Test Address", created),
        (2, 102, 1, 200.00, "INR", "paid", "5678",
         "Alice Test Address", created),
        (3, 103, 2, 300.00, "INR", "paid", "1881",
         "Bob Test Address", created),
    ],
)

conn.commit()
conn.close()

print(f"Isolated test database prepared: {TEST_DB}")
