
"""Temporary synthetic data for the API-Sentinel lab.

Day 3 will replace these dictionaries with database queries while keeping
the same function interfaces.
"""
from werkzeug.security import generate_password_hash

DEMO_PASSWORD = "Password123!"


def _user(user_id, username, full_name):
    return {
        "id": user_id,
        "username": username,
        "full_name": full_name,
        "email": f"{username}@example.test",
        "password_hash": generate_password_hash(
            DEMO_PASSWORD, method="pbkdf2:sha256"
        ),
    }


USERS = {
    1: _user(1, "alice", "Alice Anderson"),
    2: _user(2, "bob", "Bob Brown"),
    3: _user(3, "carol", "Carol Clark"),
}

ORDERS = {
    101: {"id": 101, "user_id": 1, "item": "Laptop sleeve", "total": 29.99},
    102: {"id": 102, "user_id": 1, "item": "USB-C hub", "total": 49.50},
    103: {"id": 103, "user_id": 2, "item": "Mechanical keyboard", "total": 89.00},
    104: {"id": 104, "user_id": 3, "item": "Monitor stand", "total": 35.00},
    105: {"id": 105, "user_id": 3, "item": "Webcam", "total": 59.90},
}

INVOICES = {
    1: {
        "id": 1, "owner_id": 1, "order_id": 101, "amount": 29.99,
        "currency": "USD", "status": "paid", "card_last4": "4242",
        "billing_address": "1 Test Lane, Testville",
    },
    2: {
        "id": 2, "owner_id": 1, "order_id": 102, "amount": 49.50,
        "currency": "USD", "status": "paid", "card_last4": "4242",
        "billing_address": "1 Test Lane, Testville",
    },
    3: {
        "id": 3, "owner_id": 2, "order_id": 103, "amount": 89.00,
        "currency": "USD", "status": "paid", "card_last4": "1881",
        "billing_address": "22 Sample Road, Mockton",
    },
    4: {
        "id": 4, "owner_id": 3, "order_id": 104, "amount": 35.00,
        "currency": "USD", "status": "pending", "card_last4": "0005",
        "billing_address": "9 Demo Street, Faketown",
    },
    5: {
        "id": 5, "owner_id": 3, "order_id": 105, "amount": 59.90,
        "currency": "USD", "status": "paid", "card_last4": "0005",
        "billing_address": "9 Demo Street, Faketown",
    },
}


def find_user_by_username(username):
    return next(
        (user for user in USERS.values()
         if user["username"] == username),
        None,
    )


def get_user(user_id):
    return USERS.get(user_id)


def public_user(user):
    return {key: value for key, value in user.items()
            if key != "password_hash"}


def list_orders_for_user(user_id):
    return [order for order in ORDERS.values()
            if order["user_id"] == user_id]


def get_order(order_id):
    return ORDERS.get(order_id)


def list_invoices_for_user(user_id):
    return [invoice for invoice in INVOICES.values()
            if invoice["owner_id"] == user_id]


def get_invoice(invoice_id):
    return INVOICES.get(invoice_id)
