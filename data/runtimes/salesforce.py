# transithub/salesforce.py
import os
import sys

# Force Python to look inside the 'project' folder for modules and orchestrators
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.state_manager import StateManager
from orchestrators.dns_resolver import ResolverOrchestrator
from orchestrators.ingress_controller import IngressFabricController
from orchestrators.network_fabric import NetworkOrchestrator


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "create"

    state_mgr = StateManager()
    gql_endpoint = "http://localhost:7600/graphql"
    region = "eu-central-2"

    # Using a dedicated scope so it queries/isolated state for the Salesforce edge
    scope = "salesforce"

    # Initialize Orchestrators explicitly targeted or scoped for the Salesforce edge
    sf_net_orch = NetworkOrchestrator(
        graphql_url=gql_endpoint, state_manager=state_mgr, region=region, scope=scope
    )
    sf_ingress_orch = IngressFabricController(
        graphql_url=gql_endpoint, state_manager=state_mgr, region=region, scope=scope
    )
    sf_dns_orch = ResolverOrchestrator(
        graphql_url=gql_endpoint, state_manager=state_mgr, region=region, scope=scope
    )

    if action == "create":
        print("=== [SALESFORCE EDGE] BUILDING SALESFORCE EXTENSION VPC ===")
        # 1. Provision the dedicated Salesforce VPC and its TGW attachments
        sf_net_status = sf_net_orch.run()
        print(f"[ORCHESTRATION] Salesforce Network Fabric status: {sf_net_status}")

        # 2. Build Ingress Fabric (NLB/ALB, PrivateLink/VPC Endpoints targeting Salesforce)
        print("\n--> Deploying Ingress Fabric and Private Endpoints...")
        ingress_status = sf_ingress_orch.run()
        print(f"[ORCHESTRATION] Ingress Fabric Convergence status: {ingress_status}")

        # 3. Create Private Route53 Zones/Records mapping to the Ingress Load Balancer
        print("\n--> Mapping Salesforce Private DNS Records to Ingress Fabric...")
        dns_status = sf_dns_orch.run()
        print(f"[ORCHESTRATION] Salesforce Inbound DNS mapping complete: {dns_status}")

    elif action == "update_state":
        print(f"\n=== [SALESFORCE EDGE: RECONCILE] RE-EVALUATING GRAPH STATE ===")
        sf_net_orch.update_state()
        if hasattr(sf_ingress_orch, "update_state"):
            sf_ingress_orch.update_state()
        if hasattr(sf_dns_orch, "update_state"):
            sf_dns_orch.update_state()

    elif action == "destroy":
        print("\n=== [SALESFORCE EDGE: TEARDOWN] INITIATING EXTENSION DESTRUCTION ===")

        # 1. Strip the DNS zones first so traffic routing safely stops targeting the endpoints
        print("\n--> Evicting Salesforce Private DNS zones...")
        if hasattr(sf_dns_orch, "destroy"):
            sf_dns_orch.destroy()

        # 2. Tear down the Ingress Load Balancers and Endpoint allocations
        print("\n--> Tearing down Ingress Fabric & Private Endpoints...")
        if hasattr(sf_ingress_orch, "destroy"):
            sf_ingress_orch.destroy()

        # 3. Remove the Salesforce VPC and detach it from the Transit Gateway
        print("\n--> Removing Salesforce VPC and TGW Attachments...")
        sf_net_orch.destroy()
        print(
            "\n⚡ Salesforce Extension teardown complete. Core Transit remains intact. ⚡"
        )

    else:
        print(f"Unknown action: '{action}'")
        sys.exit(1)


if __name__ == "__main__":
    main()
