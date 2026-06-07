# project/orchestrators/network_orch.py
import requests
from modules.dns_builder import DNSZoneBuilder
from modules.firewall_builder import FirewallBuilder
from modules.subnet_builder import SubnetBuilder
from modules.vpc_builder import VPCBuilder


class NetworkOrchestrator:
    def __init__(self, graphql_url: str, state_manager):
        self.url = graphql_url
        self.state = state_manager
        self.domain = "network"

    def _fetch_topology_blueprint(self) -> dict:
        """Queries the graph for the multi-layer setup including 3-tier DNS architectures."""
        query = """
        query GetCompleteNetworkAndDNSBlueprint {
            network {
                name
                cidr
                description
                subnet {
                    node {
                        name
                        cidr
                        fault_domain
                    }
                }
                firewall {
                    node {
                        name
                        description
                        filter {
                            node {
                                name
                                protocol
                                from_port
                                to_port
                                description
                            }
                        }
                    }
                }
            }
            resolver {
                name
                description
                zone {
                    node {
                        name
                        description
                        record {
                            node {
                                name
                                type
                                is_alias
                                description
                            }
                        }
                    }
                }
            }
        }
        """

        try:
            response = requests.post(self.url, json={"query": query})
            response.raise_for_status()

            payload = response.json()

            # If the server sent back explicit schema execution errors, surface them immediately
            if "errors" in payload:
                print(f"\n[GRAPHQL SCHEMA ERROR] Server returned execution faults:")
                for err in payload["errors"]:
                    print(f"  -> {err.get('message')}")

            # Defend against 'data': null/None combinations
            data_content = payload.get("data")
            return data_content if data_content is not None else {}

        except Exception as e:
            print(
                f"[{self.domain.upper()} TRANSPORT ERROR] Failed to pull graph properties: {e}"
            )
            return {}

    def run(self):
        """[CREATE] Graph-driven loop mapping network primitives followed by DNS layers."""
        blueprint_data = self._fetch_topology_blueprint()

        # Explicit dictionary payload defensive structure validations
        target_networks = blueprint_data.get("network", []) or []
        target_resolvers = blueprint_data.get("resolver", []) or []

        if not target_networks and not target_resolvers:
            print(f"No configurations discovered for domain: {self.domain}")
            return

        print(
            f"\n=== [DOMAIN: {self.domain.upper()}] PROVISIONING MULTI-LAYER TOPOLOGY ==="
        )

        primary_vpc_id = None
        global_region = "eu-central-2"

        # Look up existing recorded state if we are tracking an active infrastructure inventory
        current_state = self.state.get_domain_state(self.domain) or {}
        for res_id, meta in current_state.items():
            if (
                "VpcId" in meta
                and "SubnetId" not in meta
                and "SecurityGroupId" not in meta
            ):
                primary_vpc_id = meta["VpcId"]
                break

        for net in target_networks:
            global_region = net.get("region", "eu-central-2")

            # Step 1: Converge Base VPC
            print(f"\n--> Structural Node: Converging VPC '{net['name']}'")
            vpc_builder = VPCBuilder(
                cidr=net["cidr"], name=net["name"], region=global_region
            )
            vpc_meta = vpc_builder.build()
            self.state.record_resource(self.domain, vpc_meta["VpcId"], vpc_meta)

            if not primary_vpc_id:
                primary_vpc_id = vpc_meta["VpcId"]

            # Step 2: Sequence Subnets
            subnet_relations = net.get("subnet", []) or []
            for relation in subnet_relations:
                sub_node = relation.get("node")
                if sub_node:
                    print(f"  -> Dependent Subnet Node: '{sub_node['name']}'")
                    sub_builder = SubnetBuilder(
                        vpc_id=vpc_meta["VpcId"],
                        cidr=sub_node["cidr"],
                        name=sub_node["name"],
                        az=sub_node.get("fault_domain"),
                        region=global_region,
                    )
                    sub_meta = sub_builder.build()
                    self.state.record_resource(
                        self.domain, sub_meta["SubnetId"], sub_meta
                    )

            # Step 3: Sequence Firewall Containers
            fw_relations = net.get("firewall", []) or []
            for fw_relation in fw_relations:
                fw_node = fw_relation.get("node")
                if fw_node:
                    print(f"  -> Structural Firewall Node: '{fw_node['name']}'")
                    fw_builder = FirewallBuilder(
                        vpc_id=vpc_meta["VpcId"],
                        name=fw_node["name"],
                        description=fw_node["description"],
                        region=global_region,
                    )
                    fw_meta = fw_builder.build()
                    self.state.record_resource(
                        self.domain, fw_meta["SecurityGroupId"], fw_meta
                    )

                    filter_relations = fw_node.get("filter", []) or []
                    ip_permissions = []
                    for f_relation in filter_relations:
                        f_node = f_relation.get("node")
                        if f_node:
                            proto = f_node["protocol"].lower()
                            if proto == "all":
                                proto = "-1"
                            ip_permissions.append(
                                {
                                    "IpProtocol": proto,
                                    "FromPort": int(f_node["from_port"]),
                                    "ToPort": int(f_node["to_port"]),
                                    "IpRanges": [
                                        {
                                            "CidrIp": "0.0.0.0/0",
                                            "Description": f_node["description"],
                                        }
                                    ],
                                }
                            )
                    if ip_permissions:
                        fw_builder.authorize_filters(
                            fw_meta["SecurityGroupId"], ip_permissions
                        )

        # ==============================================================================
        # Step 4: Sequence 3-Tier Private DNS Layers
        # ==============================================================================
        if target_resolvers:
            if not primary_vpc_id:
                print(
                    f"\n[ORCHESTRATION WARNING] Target resolvers found, but no active primary VPC ID is available to link Private DNS Zones. Skipping block."
                )
                return

            print(
                f"\n=== [DOMAIN: {self.domain.upper()}] INITIALIZING PRIVATE DNS LAYER ==="
            )
            vpce_dns_endpoint = f"vpce-mock-target.{global_region}.vpce.amazonaws.com"

            for resolver in target_resolvers:
                print(f"\n--> Processing DNS Resolver context: '{resolver['name']}'")

                zone_relations = resolver.get("zone", []) or []
                for z_relation in zone_relations:
                    z_node = z_relation.get("node")
                    if not z_node:
                        continue

                    target_region = z_node.get("region") or global_region
                    print(
                        f"  -> Structural Zone Node: '{z_node['name']}' using region '{target_region}'"
                    )

                    dns_builder = DNSZoneBuilder(
                        zone_name=z_node["name"], region=target_region
                    )
                    zone_meta = dns_builder.build(
                        vpc_id=primary_vpc_id,
                        comment=z_node.get("description", ""),
                    )

                    zone_id = zone_meta["HostedZoneId"]
                    self.state.record_resource(
                        self.domain,
                        zone_id,
                        {
                            "HostedZoneId": zone_id,
                            "Name": z_node["name"],
                            "Region": target_region,
                            "Type": "PrivateHostedZone",
                        },
                    )

                    record_relations = z_node.get("record", []) or []
                    for r_relation in record_relations:
                        r_node = r_relation.get("node")
                        if r_node:
                            dns_builder.upsert_record(
                                zone_id=zone_id,
                                record_node=r_node,
                                default_target=vpce_dns_endpoint,
                            )

    def update_state(self):
        """[UPDATE] Dynamically reconciles live state status for all components including DNS."""
        network_state = self.state.get_domain_state(self.domain)
        if not network_state:
            return

        print(f"\n=== [DOMAIN: {self.domain.upper()}] RUNNING DRIFT DISCOVERY ===")
        for res_id, metadata in list(network_state.items()):
            if "SubnetId" in metadata:
                builder = SubnetBuilder(
                    vpc_id=metadata["VpcId"],
                    cidr=metadata["CidrBlock"],
                    name=metadata["Name"],
                    region=metadata["Region"],
                )
            elif "SecurityGroupId" in metadata:
                builder = FirewallBuilder(
                    vpc_id=metadata["VpcId"],
                    name=metadata["Name"],
                    description="",
                    region=metadata["Region"],
                )
            elif "HostedZoneId" in metadata:
                builder = DNSZoneBuilder(
                    zone_name=metadata["Name"], region=metadata["Region"]
                )
            else:
                builder = VPCBuilder(
                    cidr=metadata["CidrBlock"],
                    name=metadata["Name"],
                    region=metadata["Region"],
                )

            if not builder.exists(res_id):
                print(
                    f"    [DRIFT DETECTED] {res_id} vanished from AWS. Purging token."
                )
                self.state.purge_resource(self.domain, res_id)
            else:
                print(f"    [OK] Resource {res_id} verified.")

    def destroy(self):
        """[DESTROY] Tears down elements safely based on inverse dependency cascades."""
        network_state = self.state.get_domain_state(self.domain)
        if not network_state:
            return

        print(
            f"\n=== [DOMAIN: {self.domain.upper()}] INITIALIZING COMPONENT TEARDOWN ==="
        )

        zones = {k: v for k, v in network_state.items() if "HostedZoneId" in v}
        firewalls = {k: v for k, v in network_state.items() if "SecurityGroupId" in v}
        subnets = {k: v for k, v in network_state.items() if "SubnetId" in v}
        vpcs = {
            k: v
            for k, v in network_state.items()
            if "SubnetId" not in v
            and "SecurityGroupId" not in v
            and "HostedZoneId" not in v
        }

        # Step 1: Wipe DNS Zones
        for zone_id, metadata in zones.items():
            print(
                f"\n--> Terminating DNS Hosted Zone: '{metadata['Name']}' ({zone_id})"
            )
            builder = DNSZoneBuilder(
                zone_name=metadata["Name"], region=metadata["Region"]
            )
            if builder.destroy(zone_id):
                self.state.purge_resource(self.domain, zone_id)

        # Step 2: Wipe Firewall Containers
        for sg_id, metadata in firewalls.items():
            print(
                f"\n--> Terminating Firewall Container: '{metadata['Name']}' ({sg_id})"
            )
            builder = FirewallBuilder(
                vpc_id=metadata["VpcId"],
                name=metadata["Name"],
                description="",
                region=metadata["Region"],
            )
            if builder.destroy(sg_id):
                self.state.purge_resource(self.domain, sg_id)

        # Step 3: Wipe Subnets
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

        # Step 4: Wipe Parent VPC structures
        for vpc_id, metadata in vpcs.items():
            print(f"\n--> Terminating Parent VPC: '{metadata['Name']}' ({vpc_id})")
            builder = VPCBuilder(
                cidr=metadata["CidrBlock"],
                name=metadata["Name"],
                region=metadata["Region"],
            )
            if builder.destroy(vpc_id):
                self.state.purge_resource(self.domain, vpc_id)
