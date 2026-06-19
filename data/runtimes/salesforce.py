# transithub/salesforce.py
import os
import sys

# Force Python to look inside the 'project' folder for modules and orchestrators
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from controller.dns_resolver import ResolverOrchestrator
from controller.ingress_service import IngressFabricController
from controller.network_fabric import NetworkOrchestrator

# The specialized Salesforce PrivateLink controller
from controller.salesforce_endpoint import SalesforceSyncOrchestrator
from state.manager import StateManager


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "create"
    state_mgr = StateManager(filename="state/salesforce.json")
    gql_endpoint = "http://localhost:7600/graphql"
    region = "eu-central-2"
    scope = "salesforce"

    # Initialize Orchestrators
    sf_net_orch = NetworkOrchestrator(
        graphql_url=gql_endpoint, state_manager=state_mgr, region=region, scope=scope
    )

    # ADJUSTMENT 1 (Cont.): Initialize the Salesforce endpoint orchestrator
    sf_endpoint_orch = SalesforceSyncOrchestrator(
        state_manager=state_mgr, region=region
    )

    sf_ingress_orch = IngressFabricController(
        graphql_url=gql_endpoint, state_manager=state_mgr, region=region, scope=scope
    )
    sf_dns_orch = ResolverOrchestrator(
        graphql_url=gql_endpoint, state_manager=state_mgr, region=region, scope=scope
    )

    if action == "create":
        print("=== [SALESFORCE] BUILDING EXTENSION VPC ===")
        # 1. Provision the dedicated Salesforce VPC and its TGW attachments
        sf_net_status = sf_net_orch.run()
        print(f"[SALESFORCE] Network Fabric status: {sf_net_status}")

        # 2. Build Ingress Fabric (NLB/ALB and the PrivateLink VPCE Service)
        print("\n--> Deploying Ingress Fabric and creating Endpoint Service...")
        ingress_status = sf_ingress_orch.run()
        print(f"[SALESFORCE] Ingress Fabric Convergence status: {ingress_status}")

        # 3. DYNAMIC STATE RETRIEVAL FOR SALESFORCE SYNC
        # Pull the live Ingress domain data out of your tracking snapshot
        ingress_state = state_mgr.get_domain_state("ingress") or {}

        # Extract the VPC Endpoint Service Name dynamically from the state metadata.
        # Note: Match the exact key ("ServiceName" or "EndpointServiceId") your IngressFabricController uses.
        aws_service_name = next(
            (
                meta.get("ServiceName")
                for res_id, meta in ingress_state.items()
                if "ServiceName" in meta
            ),
            None,
        )

        if not aws_service_name:
            print(
                "❌ [ORCHESTRATION ERROR] Could not find an active VPC Endpoint Service inside ingress state. Halting Salesforce Sync."
            )
            sys.exit(1)

        print(f"\n--> Provisioning Private Endpoints (PrivateLink) using target service: {aws_service_name}...")
        endpoint_status = sf_endpoint_orch.run(aws_service_name=aws_service_name)
        print(f"[SALESFORCE] Private Endpoint status: {endpoint_status}")

        # 4. Create Private Route53 Zones/Records mapping to the Ingress Load Balancer
        print("\n--> Mapping Salesforce Private DNS Records to Ingress Fabric...")
        dns_status = sf_dns_orch.run()
        print(f"[SALESFORCE] Inbound DNS mapping complete: {dns_status}")

    elif action == "update_state":
        print(f"\n=== [SALESFORCE: RECONCILE] RE-EVALUATING GRAPH STATE ===")
        sf_net_orch.update_state()
        if hasattr(sf_endpoint_orch, "update_state"):
            sf_endpoint_orch.update_state()
        if hasattr(sf_ingress_orch, "update_state"):
            sf_ingress_orch.update_state()
        if hasattr(sf_dns_orch, "update_state"):
            sf_dns_orch.update_state()

    elif action == "destroy":
        print("\n=== [SALESFORCE: TEARDOWN] INITIATING EXTENSION DESTRUCTION ===")

        # 1. Strip the DNS zones first so traffic routing safely stops targeting the endpoints
        print("\n--> Evicting Private DNS zones...")
        if hasattr(sf_dns_orch, "destroy"):
            sf_dns_orch.destroy()

        # 2. Tear down the Ingress Load Balancers to free up target bindings
        print("\n--> Tearing down Ingress Fabric Load Balancers...")
        if hasattr(sf_ingress_orch, "destroy"):
            sf_ingress_orch.destroy()

        # ADJUSTMENT 3: Delete Salesforce Private Endpoints before wiping subnets
        print("\n--> Evicting Private Endpoints...")
        if hasattr(sf_endpoint_orch, "destroy"):
            sf_endpoint_orch.destroy()
        else:
            print(
                "[SALESFORCE] WARNING: The Salesforce controller does not explicitly expose a destroy method."
            )

        # 4. Remove the Salesforce VPC and detach it from the Transit Gateway
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
