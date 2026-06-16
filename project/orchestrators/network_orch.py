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

    def _fetch_topology_blueprint(self) -> dict:
        """Queries the graph for the multi-layer setup including 3-tier DNS architectures."""
        query = """
        query {
          network (filter: { function: "transit" }) {
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
                load_balancer {
                    node {
                        description
                        name
                        function
                        created
                    }
                }
            }
            firewall {
                function
                description
                created
                name
            }
            resolver {
                name
                created
                public
                function
                description
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

                    # Merge existing metadata with custom tracking attributes
                    self.state.record_resource(
                        self.domain,
                        sub_meta["SubnetId"],
                        {
                            **sub_meta,  # Unpacks existing AWS attributes safely
                            "Type": "Subnet",  # Required for Phase 3 filtering
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
                # --- Phase 3: Ingress Delivery Plumbing (Graph-Driven) ---
                print(
                    f"\n=== [DOMAIN: {self.domain.upper()}] PROVISIONING INGRESS ROUTE PLANE ==="
                )

                live_service_name = None

                # 1. Outer Loop: Iterate through your target networks defined by the GraphQL blueprint query
                for net in target_networks:
                    # Fetch relations for the *current* network iteration
                    lb_relations = net.get("load_balancer", []) or []
                    if not lb_relations:
                        continue

                    # Force a fresh state lookup so subnets built in Phase 1 are visible right now
                    network_state = self.state.get_domain_state(self.domain) or {}

                    # 2. Look up the live physical AWS resource token for this specific network node
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
                            f"⚠️  [ORCHESTRATION SKIP] Cannot verify live VPC state for network configuration: '{net['name']}'"
                        )
                        continue

                    # 3. Dynamic Subnet Aggregation Block
                    assigned_subnet_ids = []
                    for res_id, meta in network_state.items():
                        if (
                            meta.get("Type") == "Subnet"
                            and meta.get("VpcId") == current_vpc_id
                        ):
                            assigned_subnet_ids.append(res_id)

                    if len(assigned_subnet_ids) < 2:
                        print(
                            f"❌ [ORCHESTRATION ERROR] Skipping Load Balancer allocation for {net['name']}: "
                            f"Insufficient subnets found in tracked state context (Found: {len(assigned_subnet_ids)}/2 required)."
                        )
                        continue

                    # 4. Inner Loop: Process all load balancers configured for this network profile inside the graph
                    for lb_relation in lb_relations:
                        lb_node = lb_relation.get("node")
                        if not lb_node:
                            continue

                        raw_lb_name = lb_node["name"]
                        lb_name = raw_lb_name.replace("_", "-")

                        print(
                            f"\n--> Carving Graph-Defined Load Balancer: '{lb_name}' (Source Token: '{raw_lb_name}', Scope: {lb_node.get('scope', 'internal')})"
                        )

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
                                "DNSName": nlb_meta.get("DNSName")
                                or nlb_meta.get("DnsName"),
                                # Try both variations of the Hosted Zone ID token safely:
                                "CanonicalHostedZoneNameID": (
                                    nlb_meta.get("CanonicalHostedZoneId")
                                    or nlb_meta.get("CanonicalHostedZoneNameID")
                                ),
                                "Region": global_region,
                                "Type": "NetworkLoadBalancer",
                                "Name": lb_name,
                            },
                        )

                        # ─── PROVISION PRIVATE DNS ALIAS POINTING TO NLB (INDENT 24 SPACES) ───
                        # Extract the target DNS routing metadata directly out of your fresh nlb_meta instance
                        target_dns = nlb_meta.get("DNSName") or nlb_meta.get("DnsName")
                        nlb_canonical_zone_id = nlb_meta.get(
                            "CanonicalHostedZoneId"
                        ) or nlb_meta.get("CanonicalHostedZoneNameID")

                        if target_dns and nlb_canonical_zone_id:
                            print(
                                "\n=== [DOMAIN: NETWORK] PROVISIONING PRIVATE DNS ENDPOINT RECORD ==="
                            )
                            target_private_fqdn = (
                                "salesforce-ingress.internal.rescile.ch"
                            )

                            # Pull active zones mapped in current network domain state context
                            zones = {
                                k: v
                                for k, v in network_state.items()
                                if "HostedZoneId" in v
                            }

                            for zone_id, zone_meta in zones.items():
                                print(
                                    f"    [AWS API] Mapping Inbound Route 53 Alias -> NLB Plane ({target_dns})"
                                )
                                zone_manager = DNSZoneBuilder(
                                    zone_name=zone_meta["Name"],
                                    region=zone_meta["Region"],
                                )

                                # Map the custom record directly to the NLB Core Ingress target
                                zone_manager.upsert_alias_record(
                                    zone_id=zone_id,
                                    record_name=target_private_fqdn,
                                    target_dns=target_dns,
                                    hosted_zone_id=nlb_canonical_zone_id,
                                )

                                # Record tracking to state cache so destroy handles it cleanly
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

                        # 5. Graph-Driven PrivateLink Ingress Service Plane Provisioning
                        network_function = net.get("function")
                        lb_function = lb_node.get("function")

                        if (
                            (
                                lb_function
                                and network_function
                                and lb_function == network_function
                            )
                            or lb_function == "ingress"
                            or "ingress" in lb_name.lower()
                        ):
                            print(
                                f"    [AWS API] Initializing PrivateLink Service Endpoint Configuration for {lb_name}..."
                            )

                            fresh_vpc_id = current_vpc_id

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

                            # Cleanly return the live identifier out to the master engine loop
                            return service_meta["ServiceName"]

                # Fallback exit point if loops run empty without initializing an Ingress target line
                return None

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
                        if state == "deleting":
                            time.sleep(10)
                    except botocore.exceptions.ClientError as e:
                        if "LoadBalancerNotFound" in str(e):
                            print(
                                "✅ NLB carrier completely evaporated from infrastructure plane."
                            )

                            # ─── DETERMINISTIC DYNAMIC ENI WAITER BLOCK ───
                            print(
                                "⏳ Polling subnet attachments for lingering ELB network interfaces..."
                            )
                            ec2 = boto3.client("ec2", region_name=metadata["Region"])

                            network_state = (
                                self.state.get_domain_state(self.domain) or {}
                            )

                            # Method A: Match subnets directly tracking the "salesforce" scope name string
                            vpc_subnets = [
                                k
                                for k, v in network_state.items()
                                if v.get("Type") == "Subnet"
                                and (
                                    "salesforce" in v.get("Name", "").lower()
                                    or "salesforce" in str(v.get("VpcId", "")).lower()
                                )
                            ]

                            # Fallback Method B: Trace the VPC via string key to grab its ID if name matching missed
                            if not vpc_subnets:
                                target_vpc_id = None
                                for res_id, v_meta in network_state.items():
                                    if v_meta.get("Name") == "zurich_salesforce":
                                        target_vpc_id = res_id
                                        break
                                if target_vpc_id:
                                    vpc_subnets = [
                                        k
                                        for k, v in network_state.items()
                                        if v.get("Type") == "Subnet"
                                        and v.get("VpcId") == target_vpc_id
                                    ]

                            if vpc_subnets:
                                start_time = time.time()
                                timeout = 120  # 2-minute safety ceiling

                                while time.time() - start_time < timeout:
                                    # Filter interfaces matching our specific subnets and owned by ELB
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

                                    # Double check description tokens to ensure we don't block on unrelated ENIs
                                    elb_enis = [
                                        eni
                                        for eni in interfaces
                                        if "ELB" in eni.get("Description", "")
                                        or eni.get("RequesterId") == "amazon-elb"
                                    ]

                                    if not elb_enis:
                                        print(
                                            "✅ All network attachments successfully dropped by AWS."
                                        )
                                        break

                                    print(
                                        f"   [Asynchronous AWS Delay] {len(elb_enis)} ENI(s) still clearing... Retrying in 10s."
                                    )
                                    time.sleep(10)
                                else:
                                    print(
                                        "⚠️ [TIMEOUT] Moving to next phase. Some ENIs may require manual scavenging."
                                    )
                            break
                        raise e

                self.state.purge_resource(self.domain, nlb_arn)
            except Exception as e:
                print(f"    [AWS TEARDOWN FAILURE] Could not drop load balancer: {e}")

        # Step 3: Wipe DNS Zones
        for zone_id, metadata in zones.items():
            print(
                f"\n--> Purging custom managed DNS records from Hosted Zone: {zone_id}"
            )
            route53 = boto3.client("route53", region_name=metadata["Region"])

            # Scan state for any records bound to this zone
            custom_records = {
                k: v
                for k, v in network_state.items()
                if v.get("Type") == "DnsRecordSet" and v.get("ZoneId") == zone_id
            }

            for rec_id, rec_meta in custom_records.items():
                print(
                    f"    [AWS API] Stripping active Alias Record: {rec_meta['Name']}"
                )
                try:
                    # To delete an Alias record, we have to pass the exact matching block architecture
                    # We can fetch the live record data or pass an matching inverse target payload
                    # For maximum resilience, we fetch the current record sets to match values precisely
                    rrsets = route53.list_resource_record_sets(HostedZoneId=zone_id)[
                        "ResourceRecordSets"
                    ]
                    target_set = next(
                        (
                            r
                            for r in rrsets
                            if r["Name"].rstrip(".") == rec_meta["Name"].rstrip(".")
                        ),
                        None,
                    )

                    if target_set:
                        route53.change_resource_record_sets(
                            HostedZoneId=zone_id,
                            ChangeBatch={
                                "Changes": [
                                    {
                                        "Action": "DELETE",
                                        "ResourceRecordSet": target_set,
                                    }
                                ]
                            },
                        )
                    self.state.purge_resource(self.domain, rec_id)
                except Exception as dns_err:
                    print(
                        f"    ⚠️ Failed to drop record context {rec_meta['Name']}: {dns_err}"
                    )

            # ─── CONTINUATION OF YOUR EXISTING CODE ───
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
