# project/main.py
import os
import sys

# Force Python to look inside the 'project' folder for modules and orchestrators
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.state_manager import StateManager
from orchestrators.network_orch import NetworkOrchestrator


def main():
    # Capture the operational intent, default to 'create' if unassigned
    action = sys.argv[1] if len(sys.argv) > 1 else "create"

    state = StateManager()
    graphql_url = "http://localhost:7600/graphql"
    region = "eu-central-2"
    scope = "transit"

    # Instantiate the domain orchestrators
    net_orch = NetworkOrchestrator(graphql_url, state, region=region, scope=scope)

    if action == "create":
        # 1. Converge full AWS Network stack and capture the resulting PrivateLink Service Name string
        aws_service_name = net_orch.run()

        # 2. Handoff the authentic cloud token directly to the Salesforce Tooling API session
        if aws_service_name:
            print(
                f"[ORCHESTRATION] AWS Network build succeeded. ServiceName: {aws_service_name}."
            )
        else:
            print(
                "[ORCHESTRATION] AWS Network phase failed to yield a valid ServiceName."
            )

    elif action == "update_state":
        print(f"\n=== [LIFECYCLE: RECONCILE DRIFT] RE-EVALUATING GRAPH STATE ===")
        net_orch.update_state()

    elif action == "destroy":
        print("\n=== [LIFECYCLE: TEARDOWN] INITIATING CASCADING DESTRUCTION ===")
        # 2. Drop the core network fabrics (NLBs, Services, Subnets, VPCs)
        net_orch.destroy()
        print("\n⚡ Cascading teardown complete. Environment is clean. ⚡")

    else:
        print(f"Unknown action lifecycle token: '{action}'")
        print("Usage: python main.py [create|update_state|destroy]")
        sys.exit(1)


if __name__ == "__main__":
    main()
