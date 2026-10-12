"""Day 3 tests for SQLite schema, seed data, and relationships."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from werkzeug.security import check_password_hash

ROOT = Path(__file__).resolve().parents[2]
SEED_SCRIPT = ROOT / "appsec-testing/services/_shared/seed_db.py"


@pytest.fixture(scope="module")
def seeded_db(tmp_path_factory):
    """Seed a disposable database, never the shared application database."""
    db_path = tmp_path_factory.mktemp("day3") / "shop.db"
    env = os.environ.copy()
    env["DB_PATH"] = str(db_path)

    subprocess.run(
        [sys.executable, str(SEED_SCRIPT)],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    return db_path


def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_seed_creates_expected_tables_and_indexes(seeded_db):
    with connect(seeded_db) as conn:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        indexes = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }

    assert {"customers", "orders", "invoices"} <= tables
    assert {
        "idx_orders_user",
        "idx_invoices_owner",
        "idx_invoices_order",
    } <= indexes


def test_seed_creates_50_customers(seeded_db):
    with connect(seeded_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]

    assert count == 50


def test_seed_creates_expected_order_volume(seeded_db):
    with connect(seeded_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]

    # Each of the 50 customers should receive between 2 and 4 orders.
    assert 100 <= count <= 200


def test_each_order_has_one_invoice(seeded_db):
    with connect(seeded_db) as conn:
        orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        invoices = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
        unmatched = conn.execute(
            """
            SELECT COUNT(*)
            FROM orders o
            LEFT JOIN invoices i ON i.order_id = o.id
            WHERE i.id IS NULL
            """
        ).fetchone()[0]

    assert invoices == orders
    assert unmatched == 0


def test_customer_usernames_are_unique_and_expected_user_exists(seeded_db):
    with connect(seeded_db) as conn:
        total = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        distinct_names = conn.execute(
            "SELECT COUNT(DISTINCT username) FROM customers"
        ).fetchone()[0]
        alice = conn.execute(
            "SELECT id, username FROM customers WHERE username = ?",
            ("alice.anderson1",),
        ).fetchone()

    assert total == distinct_names
    assert alice is not None
    assert alice["id"] == 1


def test_seeded_password_is_hashed(seeded_db):
    with connect(seeded_db) as conn:
        row = conn.execute(
            "SELECT password_hash FROM customers WHERE username = ?",
            ("alice.anderson1",),
        ).fetchone()

    assert row is not None
    assert row["password_hash"] != "Password123!"
    assert check_password_hash(row["password_hash"], "Password123!")


def test_all_orders_reference_existing_customers(seeded_db):
    with connect(seeded_db) as conn:
        invalid = conn.execute(
            """
            SELECT COUNT(*)
            FROM orders o
            LEFT JOIN customers c ON c.id = o.user_id
            WHERE c.id IS NULL
            """
        ).fetchone()[0]

    assert invalid == 0


def test_invoices_match_their_order_owner(seeded_db):
    with connect(seeded_db) as conn:
        invalid = conn.execute(
            """
            SELECT COUNT(*)
            FROM invoices i
            JOIN orders o ON o.id = i.order_id
            WHERE i.owner_id != o.user_id
            """
        ).fetchone()[0]

    assert invalid == 0


def test_reseeding_preserves_seeded_records(seeded_db):
    def snapshot():
        with connect(seeded_db) as conn:
            customers = [
                tuple(row)
                for row in conn.execute(
                    """
                    SELECT id, username, full_name, email, created_at
                    FROM customers ORDER BY id
                    """
                )
            ]
            orders = [
                tuple(row)
                for row in conn.execute(
                    """
                    SELECT id, user_id, item, total, status, created_at
                    FROM orders ORDER BY id
                    """
                )
            ]
            invoices = [
                tuple(row)
                for row in conn.execute(
                    """
                    SELECT id, order_id, owner_id, amount, currency, status,
                           card_last4, billing_address, created_at
                    FROM invoices ORDER BY id
                    """
                )
            ]
            return customers, orders, invoices

    before = snapshot()

    env = os.environ.copy()
    env["DB_PATH"] = str(seeded_db)
    subprocess.run(
        [sys.executable, str(SEED_SCRIPT)],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    after = snapshot()
    assert after == before
