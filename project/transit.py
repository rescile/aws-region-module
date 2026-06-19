# transithub/transit.py
import os
import sys

# Force Python to look inside the 'project' folder for modules and orchestrators
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from controller.dns_resolver import ResolverOrchestrator
from controller.network_fabric import NetworkOrchestrator
from state.manager import StateManager


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "create"
    state_mgr = StateManager(filename="state/transit.json")
    gql_endpoint = "http://localhost:7600/graphql"
    region = "eu-central-2"
    scope = "transit"

    # Initialize Core Orchestrators
    net_orch = NetworkOrchestrator(
        graphql_url=gql_endpoint, state_manager=state_mgr, region=region, scope=scope
    )
    res_orch = ResolverOrchestrator(
        graphql_url=gql_endpoint, state_manager=state_mgr, region=region
    )

    if action == "create":
        print("=== [TRANSIT] CONVERGING BASE NETWORK FABRIC ===")
        aws_service_name = net_orch.run()

        if aws_service_name and aws_service_name != "ConfigSkippedOrNotRequired":
            print(f"[TRANSIT] Base Network build succeeded: {aws_service_name}")
        elif aws_service_name == "ConfigSkippedOrNotRequired":
            print("[TRANSIT] Base Network configuration up-to-date.")
        else:
            print("[TRANSIT] ERROR: Base Network phase failed.")
            sys.exit(1)

        print("\n--> Mapping Core DNS Layers and Route53 Resolver Rules...")
        dns_status = res_orch.run()
        print(f"[ORCHESTRATION] Core DNS Convergence complete. Status: {dns_status}")

    elif action == "update_state":
        print(f"\n=== [TRANSIT: RECONCILE] RE-EVALUATING GRAPH STATE ===")
        net_orch.update_state()
        if hasattr(res_orch, "update_state"):
            res_orch.update_state()

    elif action == "destroy":
        print("\n=== [TRANSIT: TEARDOWN] INITIATING DESTRUCTION ===")
        print("\n--> Evicting Core DNS Zones and Resolver rules...")
        if hasattr(res_orch, "destroy"):
            res_orch.destroy()

        print("\n--> Dropping Core Network Fabric (TGW, Firewalls, Transit VPC)...")
        net_orch.destroy()
        print("\n⚡ Core Transit teardown complete. ⚡")

    else:
        print(f"Unknown action: '{action}'")
        sys.exit(1)


if __name__ == "__main__":
    main()
