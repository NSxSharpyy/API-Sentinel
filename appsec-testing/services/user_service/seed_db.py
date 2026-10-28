
"""Seed the SQLite database with deterministic synthetic shop data."""

import os
import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash

# Allow this script to import db.py when run from the project root.
SHARED_DIR = os.path.dirname(os.path.abspath(__file__))
if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)

from db import get_connection, init_schema


SEED = 42
CUSTOMER_COUNT = 50
DEMO_PASSWORD = "Password123!"

FIRST_NAMES = [
    "Alice", "Bob", "Charlie", "Diana", "Ethan",
    "Fatima", "Grace", "Henry", "Isha", "James",
    "Kavya", "Liam", "Maya", "Noah", "Olivia",
    "Priya", "Rahul", "Sara", "Thomas", "Zoya",
]

LAST_NAMES = [
    "Anderson", "Brown", "Clark", "Davis", "Evans",
    "Fernandes", "Gupta", "Harris", "Iyer", "Johnson",
    "Khan", "Lewis", "Miller", "Nair", "Patel",
    "Roberts", "Sharma", "Taylor", "Wilson", "Young",
]

ITEMS = [
    ("Wireless Mouse", 599.00),
    ("Mechanical Keyboard", 2499.00),
    ("USB-C Hub", 1299.00),
    ("Laptop Stand", 899.00),
    ("Webcam", 1899.00),
    ("Headphones", 1599.00),
    ("External SSD", 4999.00),
    ("Monitor", 10999.00),
    ("Ethernet Adapter", 499.00),
    ("USB Flash Drive", 399.00),
]

ORDER_STATUSES = ["pending", "processing", "shipped", "delivered"]
INVOICE_STATUSES = ["paid", "pending", "paid", "paid"]
CITIES = [
    "Kolkata", "Delhi", "Mumbai", "Chennai", "Bengaluru",
    "Hyderabad", "Pune", "Jaipur", "Lucknow", "Guwahati",
]


def seed_database():
    """Create a fresh, repeatable set of customers, orders, and invoices."""
    conn = get_connection()
    rng = random.Random(SEED)

    try:
        init_schema(conn)

        # Keep IDs and relationships predictable across repeated seed runs.
        conn.execute("DELETE FROM invoices")
        conn.execute("DELETE FROM orders")
        conn.execute("DELETE FROM customers")

        now = datetime(2026, 10, 1, tzinfo=timezone.utc)
        password_hash = generate_password_hash(DEMO_PASSWORD)

        customer_rows = []
        order_rows = []
        invoice_rows = []

        order_id = 1
        invoice_id = 1

        for customer_id in range(1, CUSTOMER_COUNT + 1):
            first = FIRST_NAMES[(customer_id - 1) % len(FIRST_NAMES)]
            last = LAST_NAMES[(customer_id - 1) % len(LAST_NAMES)]
            username = f"{first.lower()}.{last.lower()}{customer_id}"
            full_name = f"{first} {last}"
            email = f"{username}@example.test"
            customer_created = (
                now - timedelta(days=rng.randint(1, 365))
            ).isoformat()

            customer_rows.append(
                (
                    customer_id,
                    username,
                    full_name,
                    email,
                    password_hash,
                    customer_created,
                )
            )

            number_of_orders = rng.randint(2, 4)

            for _ in range(number_of_orders):
                item, price = rng.choice(ITEMS)
                total = round(price * rng.uniform(1.0, 1.15), 2)
                status = rng.choice(ORDER_STATUSES)
                created_at = (
                    now - timedelta(days=rng.randint(0, 180))
                ).isoformat()

                order_rows.append(
                    (
                        order_id,
                        customer_id,
                        item,
                        total,
                        status,
                        created_at,
                    )
                )

                invoice_status = rng.choice(INVOICE_STATUSES)
                city = rng.choice(CITIES)
                card_last4 = f"{rng.randint(0, 9999):04d}"
                billing_address = (
                    f"{rng.randint(1, 999)} Example Road, {city}"
                )

                invoice_rows.append(
                    (
                        invoice_id,
                        order_id,
                        customer_id,
                        total,
                        "INR",
                        invoice_status,
                        card_last4,
                        billing_address,
                        created_at,
                    )
                )

                order_id += 1
                invoice_id += 1

        conn.executemany(
            """
            INSERT INTO customers
            (id, username, full_name, email, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            customer_rows,
        )

        conn.executemany(
            """
            INSERT INTO orders
            (id, user_id, item, total, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            order_rows,
        )

        conn.executemany(
            """
            INSERT INTO invoices
            (id, order_id, owner_id, amount, currency, status,
             card_last4, billing_address, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            invoice_rows,
        )

        conn.commit()

        print("Database seeded successfully.")
        print(f"Customers: {len(customer_rows)}")
        print(f"Orders:    {len(order_rows)}")
        print(f"Invoices:  {len(invoice_rows)}")
        print(f"Demo username: alice.anderson1")
        print(f"Demo password: {DEMO_PASSWORD}")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    seed_database()
