"""Checks that all four mock services are up. Exit code 0 = all healthy."""
import sys

import requests

SERVICES = {
    "auth": "http://127.0.0.1:5001/health",
    "user": "http://127.0.0.1:5002/health",
    "order": "http://127.0.0.1:5003/health",
    "billing": "http://127.0.0.1:5004/health",
}


def main():
    failures = 0
    for name, url in SERVICES.items():
        try:
            resp = requests.get(url, timeout=2)
            ok = resp.status_code == 200 and resp.json().get("status") == "ok"
        except requests.RequestException as exc:
            print(f"[FAIL] {name:8} {url} -> {exc.__class__.__name__}")
            failures += 1
            continue
        print(f"[{'OK' if ok else 'FAIL'}]   {name:8} {url} -> {resp.status_code}")
        failures += 0 if ok else 1
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
