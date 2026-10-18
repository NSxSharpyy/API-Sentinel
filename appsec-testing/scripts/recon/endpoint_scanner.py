
#!/usr/bin/env python3
"""Black-box endpoint discovery for the local API-Sentinel lab."""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
WORDLIST_PATH = Path(__file__).resolve().parent / "wordlist.txt"
LOG_PATH = ROOT / "logs" / "discovery_scan.jsonl"
REPORT_PATH = ROOT / "logs" / "discovery_report.json"

SERVICES = {
    "auth": "http://127.0.0.1:5001",
    "user": "http://127.0.0.1:5002",
    "order": "http://127.0.0.1:5003",
    "billing": "http://127.0.0.1:5004",
}

# Public v2 route patterns only; the scanner does not read the manifest.
KNOWN_V2_PATTERNS = {
    "auth": ["/api/v2/auth/login", "/api/v2/auth/verify"],
    "user": ["/api/v2/users/me"],
    "order": ["/api/v2/orders", "/api/v2/orders/1"],
    "billing": [
        "/api/v2/billing/invoices",
        "/api/v2/billing/invoices/1",
    ],
}

METHODS = ["GET", "POST", "PUT", "DELETE"]


def log_probe(handle, **fields):
    fields["ts"] = datetime.now(timezone.utc).isoformat()
    handle.write(json.dumps(fields) + "\n")
    handle.flush()


def probe(session, base_url, path, method="GET"):
    url = base_url.rstrip("/") + "/" + path.lstrip("/")
    try:
        response = session.request(method, url, timeout=3)
        return response.status_code
    except requests.RequestException:
        return None


def load_wordlist():
    return [
        line.strip()
        for line in WORDLIST_PATH.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def phase1_wordlist_probe(session, handle, delay):
    discovered = {name: set() for name in SERVICES}
    candidates = load_wordlist()

    print(
        f"[Phase 1] Wordlist probe: {len(candidates)} candidates "
        f"x {len(SERVICES)} services"
    )

    for service, base_url in SERVICES.items():
        for candidate in candidates:
            path = "/" + candidate.lstrip("/")
            status = probe(session, base_url, path)
            found = status is not None and status != 404

            log_probe(
                handle,
                phase="wordlist",
                service=service,
                path=path,
                method="GET",
                status=status,
                discovered=found,
            )

            if found:
                discovered[service].add(path)
                print(f"  FOUND: {service}{path} -> {status}")

            time.sleep(max(0, delay))

    return discovered


def phase2_version_sibling_probe(session, handle, delay):
    discovered = {name: set() for name in SERVICES}
    print("\n[Phase 2] Version sibling probe")

    for service, patterns in KNOWN_V2_PATTERNS.items():
        for v2_path in patterns:
            for version in ("v1", "v3"):
                path = v2_path.replace("/api/v2/", f"/api/{version}/")
                status = probe(session, SERVICES[service], path)
                found = status is not None and status != 404

                log_probe(
                    handle,
                    phase="version_sibling",
                    service=service,
                    path=path,
                    method="GET",
                    status=status,
                    discovered=found,
                )

                if found:
                    discovered[service].add(path)
                    print(f"  FOUND: {service}{path} -> {status}")

                time.sleep(max(0, delay))

    return discovered



def phase2_legacy_shape_probe(session, handle, delay):
    """Probe generic versioned wordlist and legacy route-shape candidates."""
    discovered = {name: set() for name in SERVICES}
    candidates_by_service = {name: set() for name in SERVICES}

    # Probe wordlist candidates under versioned API prefixes.
    # This can discover routes such as /api/v1/login-status without
    # hardcoding that endpoint into the scanner.
    for service in SERVICES:
        for candidate in load_wordlist():
            candidate = candidate.strip("/")
            for version in ("v1", "v3"):
                candidates_by_service[service].add(
                    f"/api/{version}/{candidate}"
                )

    # Derive alternative legacy shapes from known public v2 patterns.
    for service, patterns in KNOWN_V2_PATTERNS.items():
        for v2_path in patterns:
            for version in ("v1", "v3"):
                sibling = v2_path.replace(
                    "/api/v2/", f"/api/{version}/"
                )
                candidates_by_service[service].add(sibling)

                parts = sibling.strip("/").split("/")
                route_parts = parts[2:]  # segments after api/<version>

                # Try replacing a self-service route with a numeric ID.
                if route_parts and route_parts[-1] == "me":
                    candidates_by_service[service].add(
                        "/" + "/".join(parts[:-1] + ["1"])
                    )

                # Try removing the first route namespace segment.
                # Example: /api/v1/billing/invoices/1 ->
                #          /api/v1/invoices/1
                if len(route_parts) >= 2:
                    shortened = parts[:2] + route_parts[1:]
                    candidates_by_service[service].add(
                        "/" + "/".join(shortened)
                    )

    print("\n[Phase 2b] Legacy route-shape probes")

    for service, candidates in candidates_by_service.items():
        for path in sorted(candidates):
            status = probe(session, SERVICES[service], path)
            found = status is not None and status != 404

            log_probe(
                handle,
                phase="legacy_shape",
                service=service,
                path=path,
                method="GET",
                status=status,
                discovered=found,
            )

            if found:
                discovered[service].add(path)
                print(f"  FOUND: {service}{path} -> {status}")

            time.sleep(max(0, delay))

    return discovered

def classify_endpoint(service, path):
    """Heuristically classify discoveries against the documented v2 baseline."""
    if path in KNOWN_V2_PATTERNS.get(service, []):
        return "documented_v2"

    # Debug/metrics routes are shadow candidates even when version-prefixed.
    if path.startswith("/api/v1/debug/"):
        return "shadow_candidate"

    # v0 is treated as legacy/deprecated; v1 routes are zombie candidates.
    if path.startswith("/api/v0/") or path.startswith("/api/v1/"):
        return "zombie_candidate"

    if path.startswith("/api/"):
        return "versioned_undocumented_candidate"

    return "shadow_candidate"

def phase3_method_enumeration(session, handle, paths_by_service, delay):
    results = {}
    print("\n[Phase 3] Method enumeration")

    for service, paths in paths_by_service.items():
        for path in sorted(paths):
            endpoint_key = f"{service}{path}"
            method_results = {}

            for method in METHODS:
                status = probe(session, SERVICES[service], path, method)

                if status is None:
                    classification = "no_response"
                elif 200 <= status < 300:
                    classification = "success_response"
                elif 300 <= status < 400:
                    classification = "redirect"
                elif status == 401:
                    classification = "authentication_required"
                elif status == 403:
                    classification = "forbidden"
                elif status == 404:
                    classification = "not_found"
                elif status == 405:
                    classification = "method_not_allowed"
                elif status == 429:
                    classification = "rate_limited"
                elif 500 <= status < 600:
                    classification = "server_error"
                else:
                    classification = "other_response"

                method_results[method] = {
                    "status": status,
                    "classification": classification,
                }

                log_probe(
                    handle,
                    phase="method_enum",
                    service=service,
                    path=path,
                    method=method,
                    status=status,
                    classification=classification,
                    discovered=status is not None and status != 404,
                )

                time.sleep(max(0, delay))

            results[endpoint_key] = method_results
            print(f"  {endpoint_key}: {method_results}")

    return results



def main():
    parser = argparse.ArgumentParser(
        description="Black-box endpoint discovery for the local API lab"
    )
    parser.add_argument(
        "--delay", type=float, default=0.05,
        help="Seconds between probes (default: 0.05)",
    )
    parser.add_argument(
        "--skip-method-enum", action="store_true",
        help="Skip the HTTP method enumeration phase",
    )
    args = parser.parse_args()

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Open in write mode to keep each run's evidence self-contained.
    with LOG_PATH.open("w", encoding="utf-8") as handle:
        with requests.Session() as session:

            wordlist_found = phase1_wordlist_probe(
                session, handle, args.delay
            )
            version_found = phase2_version_sibling_probe(
                session, handle, args.delay
            )
            legacy_found = phase2_legacy_shape_probe(
                session, handle, args.delay
            )

            all_discovered = {
                name: (
                    wordlist_found[name]
                    | version_found[name]
                    | legacy_found[name]
                )
                for name in SERVICES
            }


            if args.skip_method_enum:
                method_results = {}
            else:
                method_results = phase3_method_enumeration(
                    session, handle, all_discovered, args.delay
                )

    total = sum(len(paths) for paths in all_discovered.values())
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_discovered": total,
        "by_service": {
            name: sorted(paths) for name, paths in all_discovered.items()
        },
        "endpoint_classification": {
            service: {
                path: classify_endpoint(service, path)
                for path in sorted(paths)
            }
            for service, paths in all_discovered.items()
        },
        "methods_by_endpoint": method_results,
    }

    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n",
                           encoding="utf-8")

    print(f"\n{'=' * 50}")
    print(f"DISCOVERY COMPLETE: {total} candidate endpoints found")
    for service, paths in all_discovered.items():
        if paths:
            print(f"  {service}: {sorted(paths)}")
    print(f"Report: {REPORT_PATH}")
    print(f"Probe log: {LOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
