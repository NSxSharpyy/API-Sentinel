
"""MOCK Order Service: secure object-level authorization control."""
import os

from flask import g, jsonify, request

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



# Day 10 ZOMBIE API: legacy lookup accepts any non-empty Authorization value.
@app.get("/api/v1/orders/<int:order_id>")
def v1_get_order(order_id):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.strip():
        return jsonify(error="unauthorized"), 401

    # Intentionally does not verify the token signature.
    logger.warning(
        "ZOMBIE API accessed",
        extra={"fields": {
            "endpoint": "/api/v1/orders/<id>",
            "order_id": order_id,
            "auth_header_present": True,
            "signature_checked": False,
        }},
    )
    order = get_order(order_id)
    if order is None:
        return jsonify(error="not_found"), 404
    return jsonify(order)


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5003")),
        debug=False,
    )
