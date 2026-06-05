# project/orchestrators/network_orch.py
from modules.vpc_builder import VPCBuilder


class NetworkOrchestrator:
    def __init__(self, graphql_url: str, state_manager):
        self.url = graphql_url
        self.state = state_manager

    def run(self, target_networks: list):
        """[CREATE] Converges infrastructure based on declarative graph definitions."""
        for net_cfg in target_networks:
            name = net_cfg["name"]
            cidr = net_cfg["cidr"]
            region = net_cfg["region"]

            print(f"\n--> Converging Topology Node: {name} in {region}")

            vpc_builder = VPCBuilder(cidr=cidr, name=name, region=region)
            vpc_meta = vpc_builder.build()

            self.state.record_resource(
                domain_name="network", resource_id=vpc_meta["VpcId"], metadata=vpc_meta
            )

    def update_state(self):
        """[UPDATE] Reconciles and validates current in-memory status against live AWS."""
        network_state = self.state.get_domain_state("network")
        if not network_state:
            print("No tracked network infrastructure found to update.")
            return

        for vpc_id, metadata in list(network_state.items()):
            print(f"  -> Reconciling state validation for tracking block: {vpc_id}")
            vpc_builder = VPCBuilder(
                cidr=metadata["CidrBlock"],
                name=metadata["Name"],
                region=metadata["Region"],
            )

            # Verify if resource still exists on AWS
            if not vpc_builder.exists(vpc_id):
                print(
                    f"    [DRIFT DETECTED] {vpc_id} was removed externally. Purging tracking token."
                )
                self.state.purge_resource(domain_name="network", resource_id=vpc_id)
            else:
                print(
                    f"    [OK] Resource {vpc_id} matches local matrix configuration state."
                )

    def destroy(self):
        """[DESTROY] Tears down tracked components in strict historical reverse order."""
        network_state = self.state.get_domain_state("network")
        if not network_state:
            print(
                "No tracked network infrastructure matching local state signature found to destroy."
            )
            return

        # Deleting items safely by pulling keys
        for vpc_id, metadata in list(network_state.items()):
            print(
                f"\n--> Destructive Phase: Deleting VPC Node '{metadata['Name']}' ({vpc_id})"
            )

            vpc_builder = VPCBuilder(
                cidr=metadata["CidrBlock"],
                name=metadata["Name"],
                region=metadata["Region"],
            )
            success = vpc_builder.destroy(vpc_id)

            if success:
                self.state.purge_resource(domain_name="network", resource_id=vpc_id)
