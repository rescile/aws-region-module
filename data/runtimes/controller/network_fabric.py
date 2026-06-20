# project/orchestrators/network_fabric.py

import time

import boto3
from gql import Client, gql
from gql.transport.exceptions import TransportError
from gql.transport.requests import RequestsHTTPTransport
from modules.firewall_builder import FirewallBuilder
from modules.subnet_builder import SubnetBuilder
from modules.vpc_builder import VPCBuilder


class NetworkController:
    def __init__(
        self,
        graphql_url: str,
        state_manager,
        region: str = "eu-central-2",
        scope: str = "transit",
    ):
        self.url = graphql_url
        self.state = state_manager
        self.domain = "network"
        self.region = region
        self.scope = scope

        transport = RequestsHTTPTransport(url=self.url, verify=True, retries=3)
        self.gql_client = Client(transport=transport, fetch_schema_from_transport=False)

    def _fetch_topology_blueprint(self) -> dict:
        query = gql("""
        query GetTopology($scope: String!) {
            network(filter: { function: $scope }) {
                description
                name
                function
                cidr
                created
                subnet {
                    node {
                        public
                        name
                        cidr
                        fault_domain
                        description
                        original_name
                        function
                        created
                    }
                }
                firewall {
                    node {
                        function
                        description
                        created
                        name
                    }
                }
            }
        }
        """)

        params = {"scope": self.scope}

        try:
            result = self.gql_client.execute(query, variable_values=params)
            return result if result is not None else {}
        except TransportError as te:
            print(
                f"[{self.domain.upper()} TRANSPORT ERROR] Failed to pull graph properties: {te}"
            )
            return {}
        except Exception as e:
            print(
                f"\n[{self.domain.upper()} CONTROLLER: GRAPHQL EXECUTION ERROR] Server returned execution faults or bad query: {e}"
            )
            return {}

    def run(self) -> str:
        """[CREATE] Graph-driven loop mapping core network primitives."""
        blueprint_data = self._fetch_topology_blueprint()
        target_networks = blueprint_data.get("network", []) or []

        if not target_networks:
            print(f"No configurations discovered for domain: {self.domain}")
            return "ConfigSkippedOrNotRequired"

        print(
            f"\n=== [{self.domain.upper()} CONTROLLER: PROVISIONING CORE VIRTUAL FABRIC ==="
        )

        primary_vpc_id = None

        # Pre-seed primary VPC ID from state if it already exists
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
                        self.domain,
                        sub_meta["SubnetId"],
                        {
                            **sub_meta,
                            "Type": "Subnet",
                            "Name": sub_node["name"],
                        },
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
        return "ConfigApplied"

    def update_state(self):
        """[UPDATE] Dynamically reconciles live state status for all local core components."""
        network_state = self.state.get_domain_state(self.domain)
        if not network_state:
            return

        print(f"\n=== [{self.domain.upper()} CONTROLLER: RUNNING DRIFT DISCOVERY ===")
        for res_id, metadata in list(network_state.items()):
            if metadata.get("Type") in [
                "NetworkLoadBalancer",
                "VpcEndpointServiceConfiguration",
            ]:
                print(f"    [OK] Skipped unmanaged out-of-band dynamic node: {res_id}")
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
            else:
                builder = VPCBuilder(
                    cidr=metadata["CidrBlock"],
                    name=metadata["Name"],
                    region=metadata["Region"],
                )

            if not builder.exists(res_id):
                print(
                    f"    [{self.domain.upper()} CONTROLLER: DRIFT DETECTED] {res_id} vanished from AWS. Purging token."
                )
                self.state.purge_resource(self.domain, res_id)
            else:
                print(f"    [OK] Resource {res_id} verified.")

    def destroy(self):
        """[DESTROY] Tears down elements safely based on inverse dependency cascades."""
        network_state = self.state.get_domain_state(self.domain)
        if not network_state:
            print(f"No active state found to tear down for domain: {self.domain}")
            return

        print(
            f"\n=== [{self.domain.upper()} CONTROLLER: INITIALIZING COMPONENT TEARDOWN ==="
        )

        # Categorize resources present in our localized tracking layer
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

        # Step 1: Drop Custom Firewalls / Security Groups
        for sg_id, metadata in firewalls.items():
            if metadata.get("Name") == "default" or metadata.get("IsDefault", False):
                print(f"\n--> Skipping Managed Default Security Group: {sg_id}")
                self.state.purge_resource(self.domain, sg_id)
                continue

            print(f"\n--> Evicting Security Group: {sg_id}")
            builder = FirewallBuilder(
                vpc_id=metadata["VpcId"],
                name=metadata.get("Name", "Target-SG"),
                description="",
                region=metadata["Region"],
            )
            try:
                builder.ec2.delete_security_group(GroupId=sg_id)
                self.state.purge_resource(self.domain, sg_id)
                print(f"✅ Security Group {sg_id} deleted.")
            except Exception as e:
                print(
                    f"    [{self.domain.upper()} CONTROLLER: AWS TEARDOWN FAILURE] Could not drop security group: {e}"
                )

        # Step 2: Clear Subnet Fabrics with Attachment Safety Waiter
        for subnet_id, metadata in subnets.items():
            print(f"\n--> Evicting Subnet Fabric: {subnet_id}")
            builder = SubnetBuilder(
                vpc_id=metadata["VpcId"],
                cidr=metadata["CidrBlock"],
                name=metadata.get("Name", "Target-Subnet"),
                region=metadata["Region"],
            )

            print(
                f"⏳ Verification: Checking for lingering external attachments on {subnet_id}..."
            )
            retries = 6
            while retries > 0:
                interfaces = builder.ec2.describe_network_interfaces(
                    Filters=[{"Name": "subnet-id", "Values": [subnet_id]}]
                ).get("NetworkInterfaces", [])

                if not interfaces:
                    break
                print(
                    f"    [Asynchronous Attachment Delay] {len(interfaces)} interface(s) still live. Retrying in 10s..."
                )
                time.sleep(10)
                retries -= 1

            try:
                builder.ec2.delete_subnet(SubnetId=subnet_id)
                self.state.purge_resource(self.domain, subnet_id)
                print(f"✅ Subnet {subnet_id} deleted.")
            except Exception as e:
                print(
                    f"    [{self.domain.upper()} CONTROLLER: AWS TEARDOWN FAILURE] Could not drop subnet {subnet_id}: {e}"
                )

        # Step 3: Dissolve Base VPC Structures
        for vpc_id, metadata in vpcs.items():
            print(f"\n--> Dissolving Base VPC Enclosure: {vpc_id}")
            builder = VPCBuilder(
                cidr=metadata["CidrBlock"],
                name=metadata.get("Name", "Target-VPC"),
                region=metadata["Region"],
            )
            try:
                builder.ec2.delete_vpc(VpcId=vpc_id)
                self.state.purge_resource(self.domain, vpc_id)
                print(f"✅ VPC {vpc_id} completely dissolved.")
            except Exception as e:
                print(
                    f"    [{self.domain.upper()} CONTROLLER: AWS TEARDOWN FAILURE] Could not drop VPC: {e}"
                )
