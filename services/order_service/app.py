"""MOCK Order Processing Service. Placeholder routes; real logic arrives on Day 2."""
import os

from service_base import create_service, not_implemented

app, logger = create_service("order-service")


@app.get("/api/v2/orders")
def list_orders():
    return not_implemented("list orders: implemented Day 2")


@app.get("/api/v2/orders/<int:order_id>")
def get_order(order_id):
    return not_implemented("get order: implemented Day 2")


if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5003")))
