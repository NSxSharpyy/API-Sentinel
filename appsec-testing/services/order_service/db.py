
"""SQLite connection helper and schema for the mock e-commerce database."""
import os
import sqlite3

DB_PATH = os.getenv("DB_PATH", "/app/data/shop.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES customers(id),
    item TEXT NOT NULL,
    total REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS invoices (
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

CREATE INDEX IF NOT EXISTS idx_orders_user
    ON orders(user_id);

CREATE INDEX IF NOT EXISTS idx_invoices_owner
    ON invoices(owner_id);

CREATE INDEX IF NOT EXISTS idx_invoices_order
    ON invoices(order_id);
"""


def get_connection():
    directory = os.path.dirname(DB_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def row_to_dict(row):
    return dict(row) if row is not None else None
