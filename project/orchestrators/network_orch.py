# project/orchestrators/network_orch.py
import requests
from modules.subnet_builder import SubnetBuilder
from modules.vpc_builder import VPCBuilder


class NetworkOrchestrator:
    def __init__(self, graphql_url: str, state_manager):
        self.url = graphql_url
        self.state = state_manager
        self.domain = "network"

    def _fetch_topology_blueprint(self) -> list:
        """Queries the graph for the complete VPC structure with nested Subnet components."""
        query = """
        query GetNetworkAndSubnetBlueprint {
            network {
                name
                cidr
                region
                description
                subnet {
                    node {
                        name
                        cidr
                        fault_domain
                        public
                    }
                }
            }
        }
        """
        try:
            response = requests.post(self.url, json={"query": query})
            response.raise_for_status()
            return response.json().get("data", {}).get("network", [])
        except Exception as e:
            print(
                f"[{self.domain.upper()} TRANSPORT ERROR] Failed to pull graph properties: {e}"
            )
            return []

    def run(self):
        """[CREATE] Graph-driven execution loop traversing VPC -> Subnet edges."""
        target_networks = self._fetch_topology_blueprint()
        if not target_networks:
            print(f"No configurations discovered for domain: {self.domain}")
            return

        print(
            f"\n=== [DOMAIN: {self.domain.upper()}] PROVISIONING RELATIONAL TOPOLOGY ==="
        )

        for net in target_networks:
            vpc_name = net["name"]
            vpc_cidr = net["cidr"]
            region = net["region"]

            # Step 1: Converge Base VPC
            print(f"\n--> Structural Node: Converging VPC '{vpc_name}'")
            vpc_builder = VPCBuilder(cidr=vpc_cidr, name=vpc_name, region=region)
            vpc_meta = vpc_builder.build()

            self.state.record_resource(self.domain, vpc_meta["VpcId"], vpc_meta)

            # Step 2: Unpack and loop through optional subnets mapped to this network
            subnet_relations = net.get("subnet", []) or []
            for relation in subnet_relations:
                sub_node = relation.get("node")
                if not sub_node:
                    continue

                sub_name = sub_node["name"]
                sub_cidr = sub_node["cidr"]
                az = sub_node.get(
                    "fault_domain"
                )  # Map graph's domain tag cleanly to your AWS driver

                print(
                    f"  -> Dependent Node: Converging Subnet '{sub_name}' inside {vpc_meta['VpcId']}"
                )
                sub_builder = SubnetBuilder(
                    vpc_id=vpc_meta["VpcId"],
                    cidr=sub_cidr,
                    name=sub_name,
                    az=az,
                    region=region,
                )
                sub_meta = sub_builder.build()

                # Append resource tracking independently to the network slice
                self.state.record_resource(self.domain, sub_meta["SubnetId"], sub_meta)

    def update_state(self):
        """[UPDATE] Reconciles tracking maps for both VPCs and subnets independently."""
        network_state = self.state.get_domain_state(self.domain)
        if not network_state:
            print(f"No active state matrix loaded for domain: {self.domain}")
            return

        print(f"\n=== [DOMAIN: {self.domain.upper()}] RUNNING DRIFT DISCOVERY ===")
        for res_id, metadata in list(network_state.items()):
            # Branch reconciliation checking based on tracking signature keys
            if "SubnetId" in metadata:
                builder = SubnetBuilder(
                    vpc_id=metadata["VpcId"],
                    cidr=metadata["CidrBlock"],
                    name=metadata["Name"],
                    region=metadata["Region"],
                )
            else:
                builder = VPCBuilder(
                    cidr=metadata["CidrBlock"],
                    name=metadata["Name"],
                    region=metadata["Region"],
                )

            if not builder.exists(res_id):
                print(
                    f"    [DRIFT DETECTED] {res_id} ({metadata['Name']}) vanished. Purging token."
                )
                self.state.purge_resource(self.domain, res_id)
            else:
                print(f"    [OK] Resource {res_id} verified.")

    def destroy(self):
        """[DESTROY] Tears down elements safely based on dependencies."""
        network_state = self.state.get_domain_state(self.domain)
        if not network_state:
            print(f"No active footprints recorded for domain: {self.domain}")
            return

        print(
            f"\n=== [DOMAIN: {self.domain.upper()}] INITIALIZING COMPONENT TEARDOWN ==="
        )

        # Split items into distinct buckets to clear lower elements first
        subnets = {k: v for k, v in network_state.items() if "SubnetId" in v}
        vpcs = {k: v for k, v in network_state.items() if "SubnetId" not in v}

        # Step 1: Liquidate all child subnets
        for sub_id, metadata in subnets.items():
            print(f"\n--> Terminating Subnet: '{metadata['Name']}' ({sub_id})")
            builder = SubnetBuilder(
                vpc_id=metadata["VpcId"],
                cidr=metadata["CidrBlock"],
                name=metadata["Name"],
                region=metadata["Region"],
            )
            if builder.destroy(sub_id):
                self.state.purge_resource(self.domain, sub_id)

        # Step 2: Liquidate parent VPC structures now that interfaces are clear
        for vpc_id, metadata in vpcs.items():
            print(f"\n--> Terminating Parent VPC: '{metadata['Name']}' ({vpc_id})")
            builder = VPCBuilder(
                cidr=metadata["CidrBlock"],
                name=metadata["Name"],
                region=metadata["Region"],
            )
            if builder.destroy(vpc_id):
                self.state.purge_resource(self.domain, vpc_id)
