"""MOCK User Management Service. Placeholder routes; real logic arrives on Day 2."""
import os

from service_base import create_service, not_implemented

app, logger = create_service("user-service")


@app.get("/api/v2/users/me")
def get_profile():
    return not_implemented("profile: implemented Day 2")


if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5002")))
