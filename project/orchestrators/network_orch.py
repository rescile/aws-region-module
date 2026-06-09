# project/orchestrators/network_orch.py
import time

import boto3
import botocore.exceptions
import requests

# from core.state_manager import StateManager
from modules.firewall_builder import FirewallBuilder
from modules.nlb_builder import NetworkLoadBalancerBuilder
from modules.subnet_builder import SubnetBuilder
from modules.vpc_builder import VPCBuilder
from modules.vpc_endpoint_builder import VPCEndpointServiceBuilder
from modules.zone_builder import DNSZoneBuilder


class NetworkOrchestrator:
    def __init__(self, graphql_url: str, state_manager, region: str = "eu-central-2"):
        self.url = graphql_url
        self.state = state_manager
        self.domain = "network"
        self.region = region

    def _fetch_topology_blueprint(self) -> dict:
        """Queries the graph for the multi-layer setup including 3-tier DNS architectures."""
        query = """
        query GetCompleteNetworkAndDNSBlueprint {
            network {
                name
                cidr
                description
                region
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

            if "errors" in payload:
                print(f"\n[GRAPHQL SCHEMA ERROR] Server returned execution faults:")
                for err in payload["errors"]:
                    print(f"  -> {err.get('message')}")

            data_content = payload.get("data")
            return data_content if data_content is not None else {}
        except Exception as e:
            print(
                f"[{self.domain.upper()} TRANSPORT ERROR] Failed to pull graph properties: {e}"
            )
            return {}

    def run(self) -> str:
        """[CREATE] Graph-driven loop mapping network primitives followed by DNS layers."""
        blueprint_data = self._fetch_topology_blueprint()

        target_networks = blueprint_data.get("network", []) or []
        target_resolvers = blueprint_data.get("resolver", []) or []

        if not target_networks and not target_resolvers:
            print(f"No configurations discovered for domain: {self.domain}")
            return None

        print(
            f"\n=== [DOMAIN: {self.domain.upper()}] PROVISIONING MULTI-LAYER TOPOLOGY ==="
        )

        primary_vpc_id = None
        global_region = self.region

        current_state = self.state.get_domain_state(self.domain) or {}
        for res_id, meta in current_state.items():
            if (
                "VpcId" in meta
                and "SubnetId" not in meta
                and "SecurityGroupId" not in meta
            ):
                primary_vpc_id = meta["VpcId"]
                break

        # --- Phase 1: Core Virtual Fabrics ---
        for net in target_networks:
            global_region = net.get("region", self.region)

            print(f"\n--> Structural Node: Converging VPC '{net['name']}'")
            vpc_builder = VPCBuilder(
                cidr=net["cidr"], name=net["name"], region=global_region
            )
            vpc_meta = vpc_builder.build()
            self.state.record_resource(self.domain, vpc_meta["VpcId"], vpc_meta)

            if not primary_vpc_id:
                primary_vpc_id = vpc_meta["VpcId"]

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

        # --- Phase 2: Core DNS Systems ---
        if target_resolvers:
            if not primary_vpc_id:
                print(
                    f"\n[ORCHESTRATION WARNING] Target resolvers found, but no active primary VPC ID is available. Skipping block."
                )
            else:
                print(
                    f"\n=== [DOMAIN: {self.domain.upper()}] INITIALIZING PRIVATE DNS LAYER ==="
                )
                for resolver in target_resolvers:
                    print(
                        f"\n--> Processing DNS Resolver context: '{resolver['name']}'"
                    )
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
                            vpc_id=primary_vpc_id, comment=z_node.get("description", "")
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

        # --- Phase 3: Ingress Delivery Plumbing ---
        print(
            f"\n=== [DOMAIN: {self.domain.upper()}] PROVISIONING INGRESS ROUTE PLANE ==="
        )

        # 1. Pull the live tracking state dictionary for the network domain
        network_state = self.state.get_domain_state(self.domain) or {}

        transit_vpc_id = None
        subnet_a = None
        subnet_b = None

        # 2. Map physical AWS tokens back to their logical configuration names
        for res_id, meta in network_state.items():
            meta_name = meta.get("Name")
            if (
                meta_name == "zurich_transit"
                and "VpcId" in meta
                and "SubnetId" not in meta
            ):
                transit_vpc_id = res_id
            elif meta_name == "transit_subnet_a":
                subnet_a = res_id
            elif meta_name == "transit_subnet_b":
                subnet_b = res_id

        # 3. Defensive guard validation check
        if not transit_vpc_id or not subnet_a or not subnet_b:
            print(
                "❌ [ORCHESTRATION ERROR] Cannot provision Ingress Plane: Missing structural state definitions."
            )
            print(f"    -> Found Transit VPC: {transit_vpc_id}")
            print(f"    -> Found Subnet A:    {subnet_a}")
            print(f"    -> Found Subnet B:    {subnet_b}")
            return None

        # Execute NLB Allocation pass
        nlb_builder = NetworkLoadBalancerBuilder(region=global_region)
        nlb_meta = nlb_builder.build(
            name="sf-ingress-nlb",
            vpc_id=transit_vpc_id,
            subnet_ids=[subnet_a, subnet_b],
        )
        self.state.record_resource(
            self.domain,
            nlb_meta["LoadBalancerArn"],
            {
                "LoadBalancerArn": nlb_meta["LoadBalancerArn"],
                "DNSName": nlb_meta["DNSName"],
                "Region": global_region,
                "Type": "NetworkLoadBalancer",
            },
        )

        # Execute Endpoint Service Generation pass
        service_builder = VPCEndpointServiceBuilder(
            service_name_tag="sf-inbound-service", region=global_region
        )
        service_meta = service_builder.build(nlb_arns=[nlb_meta["LoadBalancerArn"]])

        self.state.record_resource(
            self.domain,
            service_meta["ServiceId"],
            {
                "ServiceId": service_meta["ServiceId"],
                "ServiceName": service_meta["ServiceName"],
                "Region": global_region,
                "Type": "VpcEndpointServiceConfiguration",
            },
        )

        return service_meta["ServiceName"]

    def update_state(self):
        """[UPDATE] Dynamically reconciles live state status for all components including routing endpoints."""
        network_state = self.state.get_domain_state(self.domain)
        if not network_state:
            return

        print(f"\n=== [DOMAIN: {self.domain.upper()}] RUNNING DRIFT DISCOVERY ===")
        for res_id, metadata in list(network_state.items()):
            # Safe skip structural entries added dynamically during executions
            if metadata.get("Type") in [
                "NetworkLoadBalancer",
                "VpcEndpointServiceConfiguration",
            ]:
                print(
                    f"    [OK] Checked pipeline tracking layer for dynamic node: {res_id}"
                )
                continue

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

        # Filter out tracking allocations by data map features
        services = {
            k: v
            for k, v in network_state.items()
            if v.get("Type") == "VpcEndpointServiceConfiguration"
        }
        nlbs = {
            k: v
            for k, v in network_state.items()
            if v.get("Type") == "NetworkLoadBalancer"
        }
        zones = {k: v for k, v in network_state.items() if "HostedZoneId" in v}
        firewalls = {k: v for k, v in network_state.items() if "SecurityGroupId" in v}
        subnets = {k: v for k, v in network_state.items() if "SubnetId" in v}
        vpcs = {
            k: v
            for k, v in network_state.items()
            if "SubnetId" not in v
            and "SecurityGroupId" not in v
            and "HostedZoneId" not in v
            and v.get("Type")
            not in ["NetworkLoadBalancer", "VpcEndpointServiceConfiguration"]
        }

        # Step 1: Dismantle Endpoint Services
        for svc_id, metadata in services.items():
            print(f"\n--> Dissolving PrivateLink Service: {svc_id}")
            builder = VPCEndpointServiceBuilder(
                service_name_tag="sf-inbound-service", region=metadata["Region"]
            )
            try:
                builder.ec2.delete_vpc_endpoint_service_configurations(
                    ServiceIds=[svc_id]
                )

                # --- Synchronous Wait for Service Dissolution ---
                print(
                    "⏳ Waiting for Endpoint Service Configuration to fully dissolve..."
                )
                while True:
                    try:
                        desc = builder.ec2.describe_vpc_endpoint_service_configurations(
                            ServiceIds=[svc_id]
                        )
                        if desc.get("ServiceConfigurations"):
                            time.sleep(5)
                    except botocore.exceptions.ClientError as e:
                        # When the service is fully purged, describe will throw an InvalidServiceId / ClientError
                        if "invalid" in str(e).lower() or "not found" in str(e).lower():
                            print("✅ PrivateLink Service Configuration cleared.")
                            break
                        raise e

                self.state.purge_resource(self.domain, svc_id)
            except Exception as e:
                print(
                    f"    [AWS TEARDOWN FAILURE] Could not drop endpoint configuration: {e}"
                )

        # Step 2: Dismantle Load Balancer Gateway Planes
        for nlb_arn, metadata in nlbs.items():
            print(f"\n--> Terminating Ingress NLB Carrier: {nlb_arn}")
            elbv2 = boto3.client("elbv2", region_name=metadata["Region"])
            try:
                elbv2.delete_load_balancer(LoadBalancerArn=nlb_arn)

                # --- Synchronous Wait for NLB Deletion ---
                print(
                    "⏳ Waiting for NLB network interfaces to unbind (this can take 1-2 minutes)..."
                )
                while True:
                    try:
                        desc = elbv2.describe_load_balancers(LoadBalancerArns=[nlb_arn])
                        state = desc["LoadBalancers"][0].get("State", {}).get("Code")
                        # State options include: 'active', 'provisioning', 'failed', 'deleting'
                        if state == "deleting":
                            time.sleep(10)
                    except botocore.exceptions.ClientError as e:
                        if "LoadBalancerNotFound" in str(e):
                            print(
                                "✅ NLB carrier completely evaporated from infrastructure plane."
                            )
                            # Defensive 10s cooldown padding block allowing AWS internal ENIs to cleanly detach from subnets
                            print("⏳ Cooling down to allow ENIs to drop completely...")
                            time.sleep(10)
                            break
                        raise e

                self.state.purge_resource(self.domain, nlb_arn)
            except Exception as e:
                print(f"    [AWS TEARDOWN FAILURE] Could not drop load balancer: {e}")

        # Step 3: Wipe DNS Zones
        for zone_id, metadata in zones.items():
            print(
                f"\n--> Terminating DNS Hosted Zone: '{metadata['Name']}' ({zone_id})"
            )
            builder = DNSZoneBuilder(
                zone_name=metadata["Name"], region=metadata["Region"]
            )
            if builder.destroy(zone_id):
                self.state.purge_resource(self.domain, zone_id)

        # Step 4: Wipe Firewall Containers
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

        # Step 5: Wipe Subnets (Now safe from DependencyViolations)
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

        # Step 6: Wipe Parent VPC structures
        for vpc_id, metadata in vpcs.items():
            print(f"\n--> Terminating Parent VPC: '{metadata['Name']}' ({vpc_id})")
            builder = VPCBuilder(
                cidr=metadata["CidrBlock"],
                name=metadata["Name"],
                region=metadata["Region"],
            )
            if builder.destroy(vpc_id):
                self.state.purge_resource(self.domain, vpc_id)
