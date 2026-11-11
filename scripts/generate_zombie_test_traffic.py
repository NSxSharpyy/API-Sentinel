import json
from datetime import datetime, timezone

events = [
    {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": "GET",
        "path": "/api/v1/legacy/users",
        "status_code": 200,
        "request": {},
        "response": {},
    },
    {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": "GET",
        "path": "/api/v1/legacy/orders",
        "status_code": 200,
        "request": {},
        "response": {},
    },
]

with open("logs/zombie_test_traffic.jsonl", "w", encoding="utf-8") as f:
    for event in events:
        f.write(json.dumps(event) + "\n")

print("Zombie test traffic created.")
