# project/main.py
import argparse

from core.state_manager import StateManager
from orchestrators.network_orch import NetworkOrchestrator

GRAPHQL_URL = "http://localhost:7600/graphql"  # Updated to your running graph port


def main():
    parser = argparse.ArgumentParser(description="Rescile NextGen Automation Engine")
    parser.add_argument(
        "action",
        choices=["create", "update", "destroy"],
        help="Lifecycle action to execute against target infrastructure.",
    )
    args = parser.parse_args()

    # Pure State Engine Initialization
    state = StateManager()

    # Core Domain Router Mapping
    # (As you add Storage and Compute, you simply instantiate them here)
    domains = {
        "network": NetworkOrchestrator(graphql_url=GRAPHQL_URL, state_manager=state)
    }

    print(f"Executing '{args.action}' lifecycle across active resource domains...")

    # Route execution down to the domain orchestrators sequentially
    for domain_name, orchestrator in domains.items():
        if args.action == "create":
            orchestrator.run()
        elif args.action == "update":
            orchestrator.update_state()
        elif args.action == "destroy":
            orchestrator.destroy()


if __name__ == "__main__":
    main()
