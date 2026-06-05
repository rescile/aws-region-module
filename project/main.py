# project/main.py
import argparse
import sys

import requests

from core.state_manager import StateManager
from orchestrators.network_orch import NetworkOrchestrator

GRAPHQL_URL = "http://localhost:7600/graphql"


def fetch_network_blueprint() -> list:
    """Queries the graph for all declared network targets."""
    query = """
    query GetNetworkBlueprint {
        network {
            name
            cidr
            region
            description
        }
    }
    """
    try:
        response = requests.post(GRAPHQL_URL, json={"query": query})
        response.raise_for_status()
        return response.json().get("data", {}).get("network", [])
    except Exception as e:
        print(f"[GRAPHQL ERROR] Failed to fetch topology requirements: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Rescile NextGen Automation Engine")
    parser.add_argument(
        "action",
        choices=["create", "update", "destroy"],
        help="Lifecycle action to execute against target infrastructure.",
    )
    args = parser.parse_args()

    # Initialize our state manager
    state = StateManager()
    network_orch = NetworkOrchestrator(graphql_url=GRAPHQL_URL, state_manager=state)

    if args.action == "create":
        networks = fetch_network_blueprint()
        if not networks:
            print("No network configurations found in the knowledge graph blueprint.")
            return
        print(f"Found {len(networks)} topologies. Initiating Provisioning Sequence...")
        network_orch.run(target_networks=networks)

    elif args.action == "update":
        print("Initiating State Drift Synchronization Layer...")
        network_orch.update_state()

    elif args.action == "destroy":
        print("Initiating Reverse Lifecycle Teardown Sequence...")
        network_orch.destroy()


if __name__ == "__main__":
    main()
