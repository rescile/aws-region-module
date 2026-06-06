# project/orchestrators/network_orch.py
import sys

import requests
from modules.vpc_builder import VPCBuilder


class NetworkOrchestrator:
    def __init__(self, graphql_url: str, state_manager):
        self.url = graphql_url
        self.state = state_manager
        self.domain = "network"

    def _fetch_topology_blueprint(self) -> list:
        """Queries the knowledge graph for domain-specific network criteria."""
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
            response = requests.post(self.url, json={"query": query})
            response.raise_for_status()
            payload = response.json()

            if "errors" in payload:
                print(f"[{self.domain.upper()} GRAPH ERROR] Query rejected:")
                for err in payload["errors"]:
                    print(f"  -> {err.get('message')}")
                return []

            return payload.get("data", {}).get("network", [])
        except Exception as e:
            print(
                f"[{self.domain.upper()} TRANSPORT ERROR] Failed to hit graph endpoint: {e}"
            )
            return []

    def run(self):
        """[CREATE] Gathers graph properties and coordinates the structural deployment order."""
        target_networks = self._fetch_topology_blueprint()
        if not target_networks:
            print(f"No configurations discovered for domain: {self.domain}")
            return

        print(
            f"\n=== [DOMAIN: {self.domain.upper()}] INITIALIZING PROVISIONING SEQUENCE ==="
        )

        for net in target_networks:
            name = net["name"]
            cidr = net["cidr"]
            region = net["region"]

            print(f"\n--> Structural Step 1: Converging Base VPC Node '{name}'")
            vpc_builder = VPCBuilder(cidr=cidr, name=name, region=region)
            vpc_meta = vpc_builder.build()

            # Record tracking metadata securely to local state matrix
            self.state.record_resource(
                domain_name=self.domain,
                resource_id=vpc_meta["VpcId"],
                metadata=vpc_meta,
            )

            # --> Structural Step 2: (Subnets / Security Groups go here next, using vpc_meta['VpcId'])

    def update_state(self):
        """[UPDATE] Reconciles current in-memory status against live AWS."""
        network_state = self.state.get_domain_state(self.domain)
        if not network_state:
            print(f"No tracked tracking matrices found for domain: {self.domain}")
            return

        print(f"\n=== [DOMAIN: {self.domain.upper()}] RECONCILING DRIFT STATUS ===")
        for vpc_id, metadata in list(network_state.items()):
            vpc_builder = VPCBuilder(
                cidr=metadata["CidrBlock"],
                name=metadata["Name"],
                region=metadata["Region"],
            )

            if not vpc_builder.exists(vpc_id):
                print(
                    f"    [DRIFT DETECTED] {vpc_id} vanished from AWS cloud layer. Purging state token."
                )
                self.state.purge_resource(domain_name=self.domain, resource_id=vpc_id)
            else:
                print(f"    [OK] Resource {vpc_id} verified.")

    def destroy(self):
        """[DESTROY] Tears down tracked components in strict reverse hierarchy order."""
        network_state = self.state.get_domain_state(self.domain)
        if not network_state:
            print(
                f"No active tracking footprint found to destroy for domain: {self.domain}"
            )
            return

        print(f"\n=== [DOMAIN: {self.domain.upper()}] STARTING LIFECYCLE TEARDOWN ===")

        # In a larger structure, you'd drop dependent components (Subnets, SGs) here FIRST
        for vpc_id, metadata in list(network_state.items()):
            print(
                f"\n--> Structural Step: Terminating VPC '{metadata['Name']}' ({vpc_id})"
            )
            vpc_builder = VPCBuilder(
                cidr=metadata["CidrBlock"],
                name=metadata["Name"],
                region=metadata["Region"],
            )

            if vpc_builder.destroy(vpc_id):
                self.state.purge_resource(domain_name=self.domain, resource_id=vpc_id)
