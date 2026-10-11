
"""MOCK Order Service: secure object-level authorization control."""
import os

from flask import g, jsonify

from mock_data import get_order, list_orders_for_user
from security import require_auth
from service_base import create_service

app, logger = create_service("order-service")


@app.get("/api/v2/orders")
@require_auth
def list_orders():
    return jsonify(orders=list_orders_for_user(g.user_id))


@app.get("/api/v2/orders/<int:order_id>")
@require_auth
def get_order_by_id(order_id):
    order = get_order(order_id)

    if order is None or order["user_id"] != g.user_id:
        return jsonify(error="not_found"), 404

    return jsonify(order)


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5003")),
        debug=False,
    )
