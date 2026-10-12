
"""SQLite-backed synthetic data access for the API-Sentinel lab.

Preserves the Day 2 function interfaces while using the Day 3 database.
"""

try:
    from .db import get_connection, row_to_dict
except ImportError:
    from db import get_connection, row_to_dict


def find_user_by_username(username):
    """Return a user by username, or None if not found."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM customers WHERE username = ?",
            (username,),
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def get_user(user_id):
    """Return a user by ID, or None if not found."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM customers WHERE id = ?",
            (user_id,),
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def public_user(user):
    """Remove sensitive authentication data from a user dictionary."""
    if user is None:
        return None
    return {
        key: value
        for key, value in user.items()
        if key != "password_hash"
    }


def list_orders_for_user(user_id):
    """Return all orders belonging to a user."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
        return [row_to_dict(row) for row in rows]
    finally:
        conn.close()


def get_order(order_id):
    """Return an order by ID, or None if not found."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM orders WHERE id = ?",
            (order_id,),
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()


def list_invoices_for_user(user_id):
    """Return all invoices belonging to a user."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM invoices WHERE owner_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
        return [row_to_dict(row) for row in rows]
    finally:
        conn.close()


def get_invoice(invoice_id):
    """Return an invoice by ID, or None if not found."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM invoices WHERE id = ?",
            (invoice_id,),
        ).fetchone()
        return row_to_dict(row)
    finally:
        conn.close()
