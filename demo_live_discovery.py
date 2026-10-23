import json

from src.live_discovery import LiveShadowDiscovery


def load_contract(path):
    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def load_live_traffic(path):
    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def main():

    contract = load_contract(
        "samples/openapi.json"
    )

    traffic = load_live_traffic(
        "samples/live_traffic.json"
    )

    observed_routes = [
        event["path"]
        for event in traffic
        if isinstance(event, dict)
        and isinstance(event.get("path"), str)
    ]

    discovery = LiveShadowDiscovery(
        contract
    )

    results = discovery.discover(
        observed_routes
    )

    print("\n=== LIVE SHADOW API DISCOVERY ===\n")

    for result in results:
        print(
            f'{result["route"]:<30} '
            f'{result["status"]}'
        )

    shadows = discovery.discover_shadow_apis(
        observed_routes
    )

    zombies = discovery.discover_zombie_apis(
        observed_routes
    )

    print("\n=== SUMMARY ===")
    print(f"Observed routes : {len(results)}")
    print(f"Shadow APIs     : {len(shadows)}")
    print(f"Zombie APIs     : {len(zombies)}")


if __name__ == "__main__":
    main()