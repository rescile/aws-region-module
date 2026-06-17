# project/orchestrators/ingress_controller.py

import time

import boto3
import botocore.exceptions
from gql import Client, gql
from gql.transport.exceptions import TransportError
from gql.transport.requests import RequestsHTTPTransport
from modules.nlb_builder import NetworkLoadBalancerBuilder
from modules.vpc_endpoint_builder import VPCEndpointServiceBuilder
from modules.zone_builder import (
    DNSZoneBuilder,  # For configuring local zone alias records
)


class IngressFabricController:
    def __init__(
        self,
        graphql_url: str,
        state_manager,
        region: str = "eu-central-2",
        scope: str = "ingress",
    ):
        self.url = graphql_url
        self.state = state_manager
        self.domain = (
            "network"  # Keeps sync alignment with the primary resource state domain
        )
        self.region = region
        self.scope = scope

        # Initialize the permanent GQL client transport layer
        transport = RequestsHTTPTransport(url=self.url, verify=True, retries=3)
        self.gql_client = Client(transport=transport, fetch_schema_from_transport=False)

    def _fetch_ingress_blueprint(self) -> dict:
        """Queries the Universal Configuration Server for edge ingress architecture."""
        query = gql("""
        query GetIngressTopology($scope: String!) {
            network(filter: { function: $scope }) {
                name
                function
                region
                load_balancer {
                    node {
                        name
                        function
                        description
                        scope
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
                f"[INGRESS TRANSPORT ERROR] Failed to pull edge graph properties: {te}"
            )
            return {}
        except Exception as e:
            print(f"[GRAPHQL EXECUTION ERROR] Bad intent syntax or query error: {e}")
            return {}

    def run(self) -> str:
        """[CREATE] Converges intentional load balancers and PrivateLink endpoints into actual AWS runtimes."""
        discovered_services = {}
        blueprint_data = self._fetch_ingress_blueprint()
        target_networks = blueprint_data.get("network", []) or []

        if not target_networks:
            print(f"No explicit ingress targets discovered for scope: {self.scope}")
            return "ConfigSkippedOrNotRequired"

        print(f"\n=== [INGRESS FABRIC] CONVERGING EDGE DELIVERY ROUTE PLANE ===")
        global_region = self.region

        for net in target_networks:
            global_region = net.get("region", self.region)
            lb_relations = net.get("load_balancer", []) or []
            if not lb_relations:
                continue

            # Fetch fresh state context so we can resolve structural VPC and Subnet dependencies
            # provisioned earlier by the Core Network Orchestrator
            network_state = self.state.get_domain_state(self.domain) or {}

            # Trace and resolve active physical VPC ID matching the blueprint network token name
            current_vpc_id = None
            for res_id, meta in network_state.items():
                if (
                    meta.get("Name") == net["name"]
                    and "VpcId" in meta
                    and "SubnetId" not in meta
                    and "SecurityGroupId" not in meta
                ):
                    current_vpc_id = res_id
                    break

            if not current_vpc_id:
                print(
                    f"⚠️  [INGRESS SKIP] Underlying Core VPC state not yet discovered/created for: '{net['name']}'"
                )
                continue

            # Dynamically aggregate active physical subnets tracking under this specific VPC context
            assigned_subnet_ids = []
            for res_id, meta in network_state.items():
                if meta.get("Type") == "Subnet" and meta.get("VpcId") == current_vpc_id:
                    assigned_subnet_ids.append(res_id)

            if len(assigned_subnet_ids) < 2:
                print(
                    f"❌ [INGRESS ERROR] Cannot safely bind multi-AZ load balancers in {net['name']}. "
                    f"Insufficient subnets found in current state (Found: {len(assigned_subnet_ids)}/2 required)."
                )
                continue

            # Process Intentional Load Balancer Definitions
            for lb_relation in lb_relations:
                lb_node = lb_relation.get("node")
                if not lb_node:
                    continue

                raw_lb_name = lb_node["name"]
                lb_name = raw_lb_name.replace("_", "-")

                print(f"\n--> Carving Edge Load Balancer Fabric: '{lb_name}'")
                nlb_builder = NetworkLoadBalancerBuilder(region=global_region)
                nlb_meta = nlb_builder.build(
                    name=lb_name,
                    vpc_id=current_vpc_id,
                    subnet_ids=assigned_subnet_ids,
                )

                self.state.record_resource(
                    self.domain,
                    nlb_meta["LoadBalancerArn"],
                    {
                        "LoadBalancerArn": nlb_meta["LoadBalancerArn"],
                        "DNSName": nlb_meta.get("DNSName") or nlb_meta.get("DnsName"),
                        "CanonicalHostedZoneNameID": (
                            nlb_meta.get("CanonicalHostedZoneId")
                            or nlb_meta.get("CanonicalHostedZoneNameID")
                        ),
                        "Region": global_region,
                        "Type": "NetworkLoadBalancer",
                        "Name": lb_name,
                    },
                )

                # Resolve Private DNS Alias Route mapping over the newly allocated carrier NLB
                target_dns = nlb_meta.get("DNSName") or nlb_meta.get("DnsName")
                nlb_canonical_zone_id = nlb_meta.get(
                    "CanonicalHostedZoneId"
                ) or nlb_meta.get("CanonicalHostedZoneNameID")

                if target_dns and nlb_canonical_zone_id:
                    target_private_fqdn = "salesforce-ingress.internal.rescile.ch"
                    zones = {
                        k: v for k, v in network_state.items() if "HostedZoneId" in v
                    }

                    for zone_id, zone_meta in zones.items():
                        print(
                            f"   [AWS API] Mapping Route 53 Intent Endpoint Alias -> NLB Plane ({target_dns})"
                        )
                        zone_manager = DNSZoneBuilder(
                            zone_name=zone_meta["Name"], region=zone_meta["Region"]
                        )
                        zone_manager.upsert_alias_record(
                            zone_id=zone_id,
                            record_name=target_private_fqdn,
                            target_dns=target_dns,
                            hosted_zone_id=nlb_canonical_zone_id,
                        )

                        self.state.record_resource(
                            self.domain,
                            f"dns-rec-{target_private_fqdn}",
                            {
                                "Type": "DnsRecordSet",
                                "Name": target_private_fqdn,
                                "ZoneId": zone_id,
                                "Region": zone_meta["Region"],
                                "Target": target_dns,
                            },
                        )

                # Establish PrivateLink Ingress Service configurations
                print(
                    f"   [AWS API] Binding PrivateLink Service Endpoint Architecture for {lb_name}..."
                )
                service_builder = VPCEndpointServiceBuilder(
                    service_name_tag=f"{lb_name}-service",
                    region=global_region,
                )
                service_meta = service_builder.build(
                    nlb_arns=[nlb_meta["LoadBalancerArn"]]
                )

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

                discovered_services[net["name"]] = service_meta["ServiceName"]

        if discovered_services:
            return list(discovered_services.values())[0]

        return "ConfigSkippedOrNotRequired"

    def update_state(self):
        """[UPDATE] Reconciles running drift parameters for active ingress fabric tokens."""
        network_state = self.state.get_domain_state(self.domain)
        if not network_state:
            return

        print(f"\n=== [INGRESS FABRIC] RUNNING DRIFT DISCOVERY ===")
        for res_id, metadata in list(network_state.items()):
            # Only handle ingress primitives owned explicitly by this controller sub-scope
            if metadata.get("Type") in [
                "NetworkLoadBalancer",
                "VpcEndpointServiceConfiguration",
            ]:
                print(
                    f"    [OK] Verified pipeline tracking state for dynamic ingress node: {res_id}"
                )

    def destroy(self):
        """[DESTROY] Drops endpoint services and carrier gateway infrastructure sequentially to guarantee clean teardowns."""
        network_state = self.state.get_domain_state(self.domain)
        if not network_state:
            return

        print(f"\n=== [INGRESS FABRIC] TEARING DOWN CONNECTIVITY FABRICS ===")

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

        # Step 1: Drop PrivateLink Configurations First
        for svc_id, metadata in services.items():
            print(f"\n--> Dissolving PrivateLink Ingress Service: {svc_id}")
            builder = VPCEndpointServiceBuilder(
                service_name_tag="sf-inbound-service", region=metadata["Region"]
            )
            try:
                builder.ec2.delete_vpc_endpoint_service_configurations(
                    ServiceIds=[svc_id]
                )

                print(
                    "⏳ Waiting for Endpoint Service Configuration state matrix to completely clear..."
                )
                while True:
                    try:
                        desc = builder.ec2.describe_vpc_endpoint_service_configurations(
                            ServiceIds=[svc_id]
                        )
                        if desc.get("ServiceConfigurations"):
                            time.sleep(5)
                    except botocore.exceptions.ClientError as e:
                        if "invalid" in str(e).lower() or "not found" in str(e).lower():
                            print(
                                "✅ PrivateLink Ingress Service Configuration cleared safely."
                            )
                            break
                        raise e
                self.state.purge_resource(self.domain, svc_id)
            except Exception as e:
                print(
                    f"    [AWS TEARDOWN FAILURE] Could not drop endpoint configuration: {e}"
                )

        # Step 2: Clear Carrier Load Balancers
        for nlb_arn, metadata in nlbs.items():
            print(f"\n--> Terminating Edge Ingress NLB Carrier: {nlb_arn}")
            elbv2 = boto3.client("elbv2", region_name=metadata["Region"])
            try:
                elbv2.delete_load_balancer(LoadBalancerArn=nlb_arn)

                print(
                    "⏳ Waiting for carrier network allocations to unbind completely (approx. 1-2 mins)..."
                )
                while True:
                    try:
                        desc = elbv2.describe_load_balancers(LoadBalancerArns=[nlb_arn])
                        state = desc["LoadBalancers"][0].get("State", {}).get("Code")
                        if state == "deleting":
                            time.sleep(10)
                    except botocore.exceptions.ClientError as e:
                        if "LoadBalancerNotFound" in str(e):
                            print("✅ NLB edge gateway completely evaporated.")

                            # Clean up lingering Elastic Network Interfaces to protect downstream VPC deletions
                            print(
                                "⏳ Polling subnet allocations for lingering ELB network interfaces..."
                            )
                            ec2 = boto3.client("ec2", region_name=metadata["Region"])

                            vpc_subnets = [
                                k
                                for k, v in network_state.items()
                                if v.get("Type") == "Subnet"
                                and "salesforce" in v.get("Name", "").lower()
                            ]

                            if vpc_subnets:
                                start_time = time.time()
                                timeout = 120
                                while time.time() - start_time < timeout:
                                    interfaces = ec2.describe_network_interfaces(
                                        Filters=[
                                            {
                                                "Name": "subnet-id",
                                                "Values": vpc_subnets,
                                            },
                                            {
                                                "Name": "attachment.status",
                                                "Values": [
                                                    "attaching",
                                                    "attached",
                                                    "detaching",
                                                ],
                                            },
                                        ]
                                    ).get("NetworkInterfaces", [])

                                    elb_enis = [
                                        eni
                                        for eni in interfaces
                                        if "ELB" in eni.get("Description", "")
                                        or eni.get("RequesterId") == "amazon-elb"
                                    ]

                                    if not elb_enis:
                                        print(
                                            "✅ All platform network interface attachments detached safely by AWS."
                                        )
                                        break
                                    print(
                                        f"   [AWS Async Delay] {len(elb_enis)} ENI(s) still clearing out... Retrying in 10s."
                                    )
                                    time.sleep(10)
                            break
                self.state.purge_resource(self.domain, nlb_arn)
            except Exception as e:
                print(
                    f"    [AWS TEARDOWN FAILURE] Could not detach NLB fabric gateway: {e}"
                )
