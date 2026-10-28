"""Synthetic data only. Never place real customer records here."""

USERS = {
    "alice": {
        "id": "u1",
        "username": "alice",
        "password": "alice-lab-pass",
        "name": "Alice Example",
    },
    "bob": {
        "id": "u2",
        "username": "bob",
        "password": "bob-lab-pass",
        "name": "Bob Example",
    },
}

ORDERS = {
    101: {"id": 101, "owner_id": "u1", "item": "Keyboard", "total": 45.00},
    201: {"id": 201, "owner_id": "u2", "item": "Mouse", "total": 20.00},
}

INVOICES = {
    1: {"id": 1, "owner_id": "u1", "amount": 45.00, "status": "paid"},
    3: {"id": 3, "owner_id": "u2", "amount": 20.00, "status": "pending"},
}
