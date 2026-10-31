"""MOCK Auth Service. Placeholder routes; real logic arrives on Day 2."""
import os

from service_base import create_service, not_implemented

app, logger = create_service("auth-service")


@app.post("/api/v2/auth/login")
def login():
    return not_implemented("login: implemented Day 2")


@app.get("/api/v2/auth/verify")
def verify():
    return not_implemented("verify: implemented Day 2")


if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5001")))
